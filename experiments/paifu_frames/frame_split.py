"""1020 프레임 판독 오류를 검출 몫 / 분류 몫으로 나눈다(2026-11-11, 사용자 "먼저 재 보기").

frames: 저장된 det.json(프레임마다 검출 + read_small)을 정답과 프레임 단위로 대조. 추론 없음.
  - 프레임 f 에 있어야 할 강 패 = slot_v2 칸(정답과 편집 거리로 맞춘 것) 중 first_at <= f < taken_at.
    칸의 first_at 은 검출이 처음 본 시각이라 "늦게 처음 잡힘"은 놓침으로 안 센다(놓침은 하한).
  - 그 프레임의 검출을 강 순서(order_tiles)로 세워 있어야 할 패와 편집 거리 정렬 → 맞음 / 오독 / 놓침 / 헛것.
scale: 같은 판의 12MP 화료 사진을 여러 크기로 줄여 같은 파이프라인(검출 → read_small)을 돌린다.
  - det: 그 크기에서 검출부터. cls: 4080 에서 찾은 상자를 줄여 그 크기 사진에서 분류만(상자 영향 빼기).
  - 1020 은 깨끗이 줄인 것 / 프레임과 같은 JPEG q75 로 다시 저장한 것 둘 다.
사용: python frame_split.py frames | python frame_split.py scale
"""
from __future__ import annotations

import io
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import paifu_frames as pf  # noqa: E402
from score import align  # noqa: E402

ROUNDS = ("R2", "R3a", "R4")
SIDES = pf.SIDES
TRUTH = json.loads((HERE / "truth.json").read_text(encoding="utf-8"))


TAG = os.environ.get("FS_TAG", "")  # 결과 파일 꼬리(다른 분류기로 다시 잴 때)
DEALER = {"R2": "top", "R3a": "left", "R4": "bottom"}  # run_all.sh 와 같음


def make_reader():
    """FS_CLS 가 있으면 그 분류기(ONNX)로 — 검출기는 운영 그대로."""
    cls = os.environ.get("FS_CLS")
    return pf.LocalReader(threads=4, cls_model=Path(cls)) if cls else pf.LocalReader(threads=4)


def reread(name: str, det: list, reader) -> list:
    """저장된 검출 상자는 그대로 두고 패 종류만 [reader] 로 다시 읽는다(프레임은 트랙 zip 에서)."""
    tr = HERE / TRUTH[name]["track"]
    imgs = {f["file"]: jpg for f, _, jpg in pf.frames_of(tr, TRUTH[name].get("t0"), TRUTH[name].get("t1"))}
    out = []
    for d in det:
        rgb = np.asarray(Image.open(io.BytesIO(imgs[d["file"]])).convert("RGB"))
        tiles = []
        for x in d["tiles"]:
            t, c = reader.read_small(rgb, tuple(x["box"]))
            tiles.append({**x, "t": t, "c": c})
        out.append({**d, "tiles": tiles})
    return out


def slot_score(name: str, det: list) -> dict:
    """패보 v2 규칙(표 12)으로 칸을 만들고 score.py 로 채점."""
    import contextlib
    import score as sc

    sq = pf.slot_round(det, 2, 1, DEALER[name], True)
    tmp = HERE / "results" / name / f"slot_v2{TAG or '_recheck'}.json"
    tmp.write_text(json.dumps(sq, ensure_ascii=False, indent=1), encoding="utf-8")
    argv = sys.argv
    sys.argv = ["score.py", str(tmp), str(HERE / "truth.json"), name]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return sc.main()
    finally:
        sys.argv = argv


def tseq(name):
    return [(x.split()[0], x.split()[1].rstrip("*"), x.endswith("*")) for x in TRUTH[name]["seq"]]


def suit(t):
    return "자패" if t[1] == "z" else {"m": "만수", "p": "통수", "s": "삭수"}[t[1]]


def score_side(expect: list[str], got: list[dict]):
    """expect(강 순서 정답) ↔ got(강 순서 검출). 반환: [(정답|None, 검출 dict|None)]"""
    al = align(expect, [g["t"] for g in got])
    return [(expect[i] if i is not None else None, got[j] if j is not None else None) for i, j in al]


def cmd_frames():
    rows = []  # (round, frame idx, side, slot key, truth, read|None, conf, n_expected_side, n_missing_side)
    extras = 0
    reader = make_reader() if os.environ.get("FS_CLS") else None
    slot_tot = {"tile_ok": 0, "truth": 0, "taken_ok": 0, "taken": 0, "taken_extra": 0, "missed": 0, "extra": 0}
    for name in ROUNDS:
        det = json.loads((HERE / "results" / name / "det.json").read_text(encoding="utf-8"))
        if reader is not None:
            det = reread(name, det, reader)
        ss = slot_score(name, det)
        for k in slot_tot:
            slot_tot[k] += ss[k]
        slot = json.loads((HERE / "results" / name / "slot_v2.json").read_text(encoding="utf-8"))
        hd = float(np.median([d["dev"][2] for d in det]))
        for s in SIDES:
            t = [x[1] for x in tseq(name) if x[0] == s]
            p = slot[s]["slots"]
            al = align(t, [r["tile"] for r in p])
            known = [(j, t[i]) for i, j in al if i is not None and j is not None]  # 칸 j ↔ 정답 패
            for fi, d in enumerate(det):
                at = d["at"][11:19]
                exp = [(j, tile) for j, tile in known if p[j]["first_at"] <= at and (p[j]["taken_at"] is None or at < p[j]["taken_at"])]
                got = pf.order_tiles([x for x in d["tiles"] if x["side"] == s], hd)
                pairs = score_side([tile for _, tile in exp], got)
                miss = sum(1 for a, b in pairs if a is not None and b is None)
                k = 0
                for a, b in pairs:
                    if a is None:
                        extras += 1
                        continue
                    j = exp[k][0]
                    k += 1
                    rows.append((name, fi, s, f"{name}/{s}/{j}", a, b["t"] if b else None, b["c"] if b else 0.0, len(exp), miss,
                                 min(b["box"][2], b["box"][3]) if b else 0))
    N = len(rows)
    det_ok = [r for r in rows if r[5] is not None]
    cls_ok = [r for r in det_ok if r[5] == r[4]]
    miss = [r for r in rows if r[5] is None]
    lone = [r for r in miss if r[8] == 1]  # 그 자리에서 혼자 빠진 것(가림보다 검출기 몫일 가능성)
    print(f"프레임×패 {N}  검출됨 {len(det_ok)} ({len(det_ok) / N:.3f})  놓침 {len(miss)} (그 자리에서 혼자 빠짐 {len(lone)}, 여럿이 같이 빠짐 {len(miss) - len(lone)})  헛것 {extras}")
    print(f"검출된 것 중 한 프레임 읽기 맞음 {len(cls_ok)}/{len(det_ok)} = {len(cls_ok) / len(det_ok):.3f}  오독 {len(det_ok) - len(cls_ok)}")
    for name in ROUNDS:
        a = [r for r in rows if r[0] == name]
        d = [r for r in a if r[5] is not None]
        print(f"  {name}: 프레임×패 {len(a)} 검출 {len(d)} 놓침 {len(a) - len(d)} 읽기 맞음 {sum(1 for r in d if r[5] == r[4])}/{len(d)}")
    print("무늬별 한 프레임 읽기:")
    for su in ("만수", "통수", "삭수", "자패"):
        d = [r for r in det_ok if suit(r[4]) == su]
        print(f"  {su}: {sum(1 for r in d if r[5] == r[4])}/{len(d)} = {sum(1 for r in d if r[5] == r[4]) / max(1, len(d)):.3f}")
    print("확신도별(검출된 것):")
    for lo, hi in ((0, 0.5), (0.5, 0.8), (0.8, 0.9), (0.9, 0.97), (0.97, 1.01)):
        d = [r for r in det_ok if lo <= r[6] < hi]
        print(f"  [{lo:.2f},{hi:.2f}) {len(d):5d}장  맞음 {sum(1 for r in d if r[5] == r[4]) / max(1, len(d)):.3f}")
    # 패(칸)별: 오독이 체계적인가
    by = defaultdict(list)
    for r in rows:
        by[r[3]].append(r)
    cat = Counter()
    bad = []
    for k, v in by.items():
        d = [r for r in v if r[5] is not None]
        if not d:
            cat["한 번도 안 읽힘"] += 1
            continue
        acc = sum(1 for r in d if r[5] == r[4]) / len(d)
        cat["전부 맞음" if acc == 1 else "대부분 맞음(≥0.8)" if acc >= 0.8 else "반반(0.5~0.8)" if acc >= 0.5 else "대부분 틀림(<0.5)"] += 1
        if acc < 1:
            wrong = Counter(r[5] for r in d if r[5] != r[4])
            bad.append((acc, k, v[0][4], len(d), dict(wrong), round(float(np.mean([r[6] for r in d if r[5] != r[4]])), 2)))
    print(f"패(칸) {len(by)}개:", dict(cat))
    print("오독이 있는 패(맞은 비율 낮은 순) — 칸, 정답, 읽힌 프레임 수, 오답 {패: 횟수}, 오답 평균 확신도:")
    for acc, k, t, n, w, c in sorted(bad):
        print(f"  {acc:.2f} {k:16s} {t} n={n:3d} {w} conf={c}")
    conf = Counter((r[4], r[5]) for r in det_ok if r[5] != r[4])
    print("혼동 상위:", ", ".join(f"{a}→{b}×{n}" for (a, b), n in conf.most_common(15)))
    print(f"칸 투표 뒤(패보 v2 규칙): 강 패 {slot_tot['tile_ok']}/{slot_tot['truth']} 빠짐 {slot_tot['missed']} 헛것 {slot_tot['extra']}"
          f" · 울어 감 {slot_tot['taken_ok']}/{slot_tot['taken']} 헛것 {slot_tot['taken_extra']}")
    hi = [r for r in det_ok if r[6] >= 0.9]
    print(f"확신 ≥0.9: {len(hi)}장 중 틀림 {sum(1 for r in hi if r[5] != r[4])}")
    out = {"n": N, "detected": len(det_ok), "missed": len(miss), "missed_lone": len(lone), "extra": extras,
           "read_ok": len(cls_ok), "slots": dict(cat), "slot_vote": slot_tot,
           "suit": {su: [sum(1 for r in det_ok if suit(r[4]) == su and r[5] == r[4]), sum(1 for r in det_ok if suit(r[4]) == su)] for su in ("만수", "통수", "삭수", "자패")},
           "conf90": [len(hi), sum(1 for r in hi if r[5] != r[4])]}
    (HERE / "results" / f"frame_split_frames{TAG}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- scale


def read_scene(reader, rgb, cx, cy, hd):
    """paifu_frames.detect_round 의 한 프레임 처리와 같다."""
    H, W = rgb.shape[:2]
    R = int(hd * 3.2)
    x0, y0 = int(max(0, cx - R)), int(max(0, cy - R))
    crop = rgb[y0:int(min(H, cy + R)), x0:int(min(W, cx + R))]
    boxes = pf.rv.dedupe(pf.rv.keep_faces(reader.detect(crop, low=False), pf.rv.white_mask(crop), 0.45))
    tiles = []
    for b in boxes:
        gb = (b[0] + x0, b[1] + y0, b[2], b[3])
        a = pf.assign(cx, cy, hd, gb)
        if a is None:
            continue
        t, c = reader.read_small(rgb, gb)
        tiles.append({"box": gb, "side": a[0], "u": a[1], "v": a[2], "t": t, "c": c})
    return tiles


def tally(expect: dict, tiles: list, hd: float):
    ok = wrong = miss = extra = 0
    errs = []
    for s in SIDES:
        for a, b in score_side(expect[s], pf.order_tiles([x for x in tiles if x["side"] == s], hd)):
            if a is None:
                extra += 1
            elif b is None:
                miss += 1
            elif a == b["t"]:
                ok += 1
            else:
                wrong += 1
                errs.append(f"{a}→{b['t']}({b['c']:.2f})")
    return ok, wrong, miss, extra, errs


def jpeg(rgb, q):
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, "JPEG", quality=q)
    return np.asarray(Image.open(io.BytesIO(buf.getvalue())).convert("RGB"))


def head_small(full_rgb: np.ndarray, step: int, mode: str, q: int = 75) -> np.ndarray:
    """헤드(HeadCamera.kt subsample)가 미리보기를 만드는 방식 흉내: NV21(밝기 전체 + 색 2×2 절반)에서
    mode="skip" 은 step 마다 한 픽셀만 뽑고(지금 헤드), "avg" 는 step×step 평균. 그 뒤 JPEG q(4:2:0)."""
    ycc = np.asarray(Image.fromarray(full_rgb).convert("YCbCr")).astype(np.float32)
    H, W = ycc.shape[:2]
    ow, oh = (W // step) & ~1, (H // step) & ~1
    Y = ycc[..., 0]
    C = ycc[:H // 2 * 2, :W // 2 * 2, 1:].reshape(H // 2, 2, W // 2, 2, 2).mean((1, 3))
    if mode == "skip":
        y = Y[::step, ::step][:oh, :ow]
        c = C[::step, ::step][:oh // 2, :ow // 2]
    else:
        y = Y[:oh * step, :ow * step].reshape(oh, step, ow, step).mean((1, 3))
        c = C[:oh // 2 * step, :ow // 2 * step].reshape(oh // 2, step, ow // 2, step, 2).mean((1, 3))
    out = np.dstack([y, np.repeat(np.repeat(c, 2, 0), 2, 1)]).round().clip(0, 255).astype(np.uint8)
    return jpeg(np.asarray(Image.fromarray(out, "YCbCr").convert("RGB")), q)


def last_frame(name, file):
    import zipfile
    for z in sorted((HERE / TRUTH[name]["track"]).glob("frames_*.zip")):
        zf = zipfile.ZipFile(z)
        if file in zf.namelist():
            return np.asarray(Image.open(io.BytesIO(zf.read(file))).convert("RGB"))
    raise FileNotFoundError(file)


def cmd_scale():
    reader = make_reader()
    cap = HERE.parent / "visit_20261107" / "captures"
    tot = defaultdict(lambda: [0, 0, 0, 0, 0])  # 조건 → ok, wrong, miss, extra, 정답 수
    allerr = defaultdict(list)
    for name in ROUNDS:
        det = json.loads((HERE / "results" / name / "det.json").read_text(encoding="utf-8"))
        expect = {s: [x[1] for x in tseq(name) if x[0] == s and not x[2]] for s in SIDES}
        n = sum(len(v) for v in expect.values())
        full = Image.open(cap / TRUTH[name]["win_photo"] / "original.jpg").convert("RGB")
        # 기계 위치는 프레임에서 고정한 값을 그대로(화료 사진과 마지막 프레임은 같은 화각 — 패 위치 중앙 어긋남 0.5px 이하로 확인.
        # 화료 사진에서 다시 재면 손·펼친 손패가 끼어 R3a 가 37px 어긋났다)
        cx, cy, hd = fcx, fcy, fhd = det[-1]["dev"]
        print(f"== {name} 화료 사진 {TRUTH[name]['win_photo']} 정답 강 {n}장")
        # 실제 마지막 프레임(저장된 det.json)
        r = tally(expect, det[-1]["tiles"], fhd)
        add(tot, allerr, "실제 프레임(마지막)", r, n)
        print(f"  실제 마지막 프레임           맞음 {r[0]:2d} 오독 {r[1]} 놓침 {r[2]} 헛것 {r[3]}  {' '.join(r[4])}")
        frame = last_frame(name, det[-1]["file"])
        ref = None
        for L, q in ((4080, None), (2040, None), (1360, None), (1020, None), (1020, 75), (765, None),
                     (1020, "skip"), (1020, "avg"), (2040, "skip"), (2040, "avg")):
            k = L / full.width
            if isinstance(q, str):
                rgb = head_small(np.asarray(full), full.width // L, q)
            else:
                rgb = np.asarray(full) if L == full.width else np.asarray(full.resize((L, round(full.height * k)), Image.LANCZOS))
                if q:
                    rgb = jpeg(rgb, q)
            tiles = read_scene(reader, rgb, cx * L / 1020, cy * L / 1020, hd * L / 1020)
            r = tally(expect, tiles, hd * L / 1020)
            label = f"사진→{L}" + ({"skip": " 건너뛰기", "avg": " 평균"}[q] if isinstance(q, str) else f" q{q}" if q else "")
            add(tot, allerr, label + " 검출부터", r, n)
            line = f"  {label:12s} 검출부터  맞음 {r[0]:2d} 오독 {r[1]} 놓침 {r[2]} 헛것 {r[3]}  {' '.join(r[4])}"
            if L == 4080:
                ref = tiles
            else:
                # 4080 상자를 줄여 분류만
                t2 = []
                for x in ref:
                    b = tuple(int(round(v * k)) for v in x["box"])
                    t, c = reader.read_small(rgb, b)
                    t2.append({**x, "box": b, "t": t, "c": c, "u": x["u"] * k, "v": x["v"] * k})
                r2 = tally(expect, t2, hd * L / 1020)
                add(tot, allerr, label + " 4080 상자로 분류만", r2, n)
                line += f"\n  {'':12s} 4080 상자   맞음 {r2[0]:2d} 오독 {r2[1]} 놓침 {r2[2]} 헛것 {r2[3]}  {' '.join(r2[4])}"
            print(line)
        # 실제 프레임: 다시 검출부터(det.json 재현 확인) / 4080 사진 상자로 분류만
        r = tally(expect, read_scene(reader, frame, cx, cy, hd), hd)
        add(tot, allerr, "실제 프레임 다시 검출부터", r, n)
        k = frame.shape[1] / full.width
        t2 = []
        for x in ref:
            b = tuple(int(round(v * k)) for v in x["box"])
            t, c = reader.read_small(frame, b)
            t2.append({**x, "box": b, "t": t, "c": c, "u": x["u"] * k, "v": x["v"] * k})
        r2 = tally(expect, t2, hd)
        add(tot, allerr, "실제 프레임 4080 상자로 분류만", r2, n)
        print(f"  실제 프레임 다시 검출부터    맞음 {r[0]:2d} 오독 {r[1]} 놓침 {r[2]} 헛것 {r[3]}  {' '.join(r[4])}")
        print(f"  실제 프레임 4080 상자       맞음 {r2[0]:2d} 오독 {r2[1]} 놓침 {r2[2]} 헛것 {r2[3]}  {' '.join(r2[4])}")
    print("== 합계(세 판)")
    for k, v in tot.items():
        print(f"  {k:28s} 맞음 {v[0]:3d}/{v[4]} 오독 {v[1]:2d} 놓침 {v[2]:2d} 헛것 {v[3]:2d}  {' '.join(allerr[k])}")
    (HERE / "results" / f"frame_split_scale{TAG}.json").write_text(
        json.dumps({k: {"ok": v[0], "wrong": v[1], "miss": v[2], "extra": v[3], "truth": v[4], "errs": allerr[k]} for k, v in tot.items()},
                   ensure_ascii=False, indent=1), encoding="utf-8")


def cmd_proxy():
    """정답 라벨 없이 넓게: 평가 장면(10-31·11-07 원본, 가림·사용자 문제 제외) 화료 사진의 가운데 칸(강)에서
    4080 판독이 확신 ≥0.9 인 패를 기준으로, 같은 상자를 줄인 사진에서 다시 읽어 같은 답인지 센다(분류만).
    검출은 줄인 사진에서 처음부터 돌려 기준 상자를 몇 개 다시 찾는지."""
    sys.path.insert(0, str(HERE.parent / "speed"))
    import seat_grow as sg
    reader = pf.LocalReader(threads=4)
    kinds = (("LANCZOS 1020", lambda a: np.asarray(Image.fromarray(a).resize((1020, 765), Image.LANCZOS))),
             ("건너뛰기 1020 q75(지금 헤드)", lambda a: head_small(a, 4, "skip")),
             ("4×4 평균 1020 q75", lambda a: head_small(a, 4, "avg")))
    tot = {k: [0, 0, 0, 0] for k, _ in kinds}  # 같은 답, 기준 수, 다시 찾은 상자, 헛 상자
    bys = {k: defaultdict(lambda: [0, 0]) for k, _ in kinds}
    flips = {k: Counter() for k, _ in kinds}
    n_sc = 0
    for sc in sg.eval_scenes():
        if sc["set"] == "bcd":
            continue
        full = np.asarray(Image.open(sc["path"]).convert("RGB"))
        if full.shape[1] != 4080:
            continue
        g = sc["grid"]
        H, W = full.shape[:2]
        x0, x1, y0, y1 = (round(g["x1"] * W / 1000), round(g["x2"] * W / 1000), round(g["y1"] * H / 1000), round(g["y2"] * H / 1000))
        crop = full[y0:y1, x0:x1]
        boxes = pf.rv.dedupe(pf.rv.keep_faces(reader.detect(crop, low=False), pf.rv.white_mask(crop), 0.45))
        ref = []
        for b in boxes:
            gb = (b[0] + x0, b[1] + y0, b[2], b[3])
            t, c = reader.read_small(full, gb)
            if c >= 0.9:
                ref.append((gb, t))
        if not ref:
            continue
        n_sc += 1
        for k, fn in kinds:
            small = fn(full)
            r = small.shape[1] / W
            sx0, sx1, sy0, sy1 = (round(v * r) for v in (x0, x1, y0, y1))
            scrop = small[sy0:sy1, sx0:sx1]
            found = [(b[0] + sx0 + b[2] / 2, b[1] + sy0 + b[3] / 2) for b in
                     pf.rv.dedupe(pf.rv.keep_faces(reader.detect(scrop, low=False), pf.rv.white_mask(scrop), 0.45))]
            used = set()
            for gb, t in ref:
                b = tuple(int(round(v * r)) for v in gb)
                t2, _ = reader.read_small(small, b)
                tot[k][1] += 1
                bys[k][suit(t)][1] += 1
                if t2 == t:
                    tot[k][0] += 1
                    bys[k][suit(t)][0] += 1
                else:
                    flips[k][(t, t2)] += 1
                hit = next((i for i, (fx, fy) in enumerate(found) if i not in used and b[0] <= fx <= b[0] + b[2] and b[1] <= fy <= b[1] + b[3]), None)
                if hit is not None:
                    used.add(hit)
                    tot[k][2] += 1
            tot[k][3] += len(found) - len(used)
    print(f"장면 {n_sc}")
    res = {}
    for k, _ in kinds:
        v = tot[k]
        print(f"  {k:26s} 분류 같은 답 {v[0]}/{v[1]} = {v[0] / v[1]:.3f}  다름 {v[1] - v[0]}  | 검출 다시 찾음 {v[2]}/{v[1]}, 기준 밖 상자 {v[3]}")
        print("     무늬별:", ", ".join(f"{s} {a}/{b}" for s, (a, b) in bys[k].items()), "| 바뀜 상위:", ", ".join(f"{a}→{b}×{n}" for (a, b), n in flips[k].most_common(8)))
        res[k] = {"same": v[0], "ref": v[1], "refound": v[2], "other_boxes": v[3], "suit": {s: ab for s, ab in bys[k].items()}}
    (HERE / "results" / "frame_split_proxy.json").write_text(json.dumps({"scenes": n_sc, **res}, ensure_ascii=False, indent=1), encoding="utf-8")


def add(tot, allerr, key, r, n):
    for i in range(4):
        tot[key][i] += r[i]
    tot[key][4] += n
    allerr[key] += r[4]


if __name__ == "__main__":
    {"frames": cmd_frames, "scale": cmd_scale, "proxy": cmd_proxy}[sys.argv[1]]()
