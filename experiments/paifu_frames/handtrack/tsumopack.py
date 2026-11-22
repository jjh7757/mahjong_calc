"""남의 쯔모기리 B1 — 읽기 에이전트용 꾸러미 · 사용자 확인 영상(2026-11-22, 설계서 paifu_fill_scores_tsumogiri_design_1122.md 5절 B1). LLM 호출 없음.

  python -X utf8 tsumopack.py build [--workers 6]          # 꾸러미 _work/tsumo_b1_1122/ + 열쇠 _work/tsumo_b1_1122_key/key_private.json
  python -X utf8 tsumopack.py check                        # 꾸러미에 판 · 자리 이름 · 판정 낱말이 새지 않았나(grep 꼴)
  python -X utf8 tsumopack.py clip <id …> --out <폴더>     # 확인 영상(mp4, H.264 · yuv420p) — tsumokind.py clip 도 같은 것

대상: 시험 자리 여섯(tsumokind.SEATS)의 버림 중 규칙 차례(그 자리 리치 뒤 · 울기 직후)를 뺀 전부(코드 확정 · 불가 차례도 넣음)
     + 정답 아는 hero 12(tsumo_b0_1122/hero_rows.json 의 규칙 · 안 보임 · 울기 뺀 86 에서 씨 20261122: 쯔모기리 = 코드 확정 3 + 읽기인데 정답 쯔모기리 3,
       손에서 냄 = 오른 2 · 아래 2 · 왼 2). 차례 창 · T0 은 모두 같은 길(tsumokind.seat_turns — 기록기 새 기본값 강, T0 = 기록기가 강에서 처음 본 겹쳐 보기 프레임).
       hero 의 줄 장수 n 은 turncut 차례 값(L16 은 기록기가 추적 전 울기를 몰라 13 으로 셈 — 실제 10).
자르기(원본 좌표 → 대국자 시점으로 돌림 → 2배 LANCZOS): 줄 방향 = sheet_band 양끝 ± PAD_ROW, 깊이 = band + 탁자 가운데 쪽 PAD_CENTER · 대국자 쪽 PAD_PLAYER.
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import slotgrid as sg  # noqa: E402
import tsumokind as tk  # noqa: E402
import turncut as tc  # noqa: E402

PACK = hc.WORK / "tsumo_b1_1122"
KEYD = hc.WORK / "tsumo_b1_1122_key"            # 꾸러미 밖(읽는 쪽에게 주지 않음)
SEED = 20261122
PAD_ROW, PAD_CENTER, PAD_PLAYER = 80, 80, 20     # 원본 px(패 한 장 폭 약 40px): 줄 양끝 밖 sheet_band 여유 40 · 100 + 80 → 약 3 ~ 4.5장, 탁자 가운데 쪽 약 2장
SCALE = 2.0
SHEET_SCALE = 1.0                               # 표 줄은 1배(2배면 한 장이 1,900 × 5,000px 넘음) — 낱장은 2배
SHEET_ROWS = 12
POST_MS = 3000
DENSE_MS = 10000                                # T0 − 10초 ~ T0 + 3초는 초당 5장, 그 앞은 초당 2장
CHUNK = 7


def font(sz: int):
    for f in ("arial.ttf", "C:/Windows/Fonts/arial.ttf"):
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            continue
    return ImageFont.load_default()


# ------------------------------------------------------------------ 항목 고르기
def test_items() -> list:
    out = []
    for name, (gid, side, _) in tk.SEATS.items():
        for t in hc.jload(tk.OUTD / f"turns_{name}.json")["turns"]:
            if t["riichi_after"] or t["call"]:
                continue
            out.append({"src": "test", "seat": name, "cfg": name, "game": gid, "side": side, "turn": t["id"], "n": t["n_calc"], "tile": t["tile"],
                        "w0": sg.window(t)[0], "t0": t["first_seen_ms"], "pre_record": t["pre_record"]})
    return out


def hero_pool() -> dict:
    """hero 86 → 범주별 후보(차례 id 정렬). 기록기 길로 맞춘 차례가 없거나 녹화 전이면 뺌."""
    rows = hc.jload(tk.OUTD / "hero_rows.json")
    pool = {"T_code": [], "T_read": [], "H_right": [], "H_bottom": [], "H_left": []}
    for r in rows:
        if r["judge"].startswith("규칙") or r["sig"] is None or r["truth"] not in ("tsumogiri", "hand"):
            continue
        if r["truth"] == "tsumogiri":
            pool["T_code" if r["judge"] == "쯔모기리 확정" else "T_read"].append(r)
        else:
            pool[f"H_{r['side']}"].append(r)
    return {k: sorted(v, key=lambda r: r["id"]) for k, v in pool.items()}


def hero_seat_turn(gid: str, tid: str):
    """turncut 차례 tid ↔ 기록기 길(새 기본값) 차례를 패 순서로 맞춰 그 차례를 돌려줌(tsumokind.attach_first_seen 과 같은 맞춤)."""
    import difflib
    side = hc.config(gid)["side"]
    ref = tk.turns_for(gid)
    mine = tk.seat_turns_named(tk.real_game(gid), side, "new")
    sm = difflib.SequenceMatcher(None, [t["tile"] for t in ref], [m["tile"] for m in mine], autojunk=False)
    pair = {}
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            pair[blk.a + k] = blk.b + k
    i = next(k for k, t in enumerate(ref) if t["id"] == tid)
    return (ref[i], mine[pair[i]]) if i in pair else (ref[i], None)


def known_items() -> list:
    rnd = random.Random(SEED)
    pool = hero_pool()
    want = {"T_code": 3, "T_read": 3, "H_right": 2, "H_bottom": 2, "H_left": 2}
    out = []
    for cat, k in want.items():
        cand = list(pool[cat])
        rnd.shuffle(cand)
        got = 0
        for r in cand:
            if got == k:
                break
            ref, m = hero_seat_turn(r["game"], r["id"])
            if m is None or m["pre_record"]:
                continue
            out.append({"src": "known", "cat": cat, "truth": r["truth"], "cfg": r["game"], "game": tk.real_game(r["game"]), "side": hc.config(r["game"])["side"],
                        "turn": r["id"], "seat_turn": m["id"], "n": ref["n_calc"], "tile": m["tile"], "w0": sg.window(m)[0], "t0": m["first_seen_ms"],
                        "pre_record": False, "code_judge": r["judge"]})
            got += 1
        if got < k:
            raise SystemExit(f"{cat}: 후보 모자람 {got}/{k}")
    return out


# ------------------------------------------------------------------ 자르기 · 그림
def crop_box(cfg: dict) -> list:
    """원본 좌표 [x0, y0, x1, y1]. 탁자 가운데 쪽: 아래 = 위(y 작음), 위 = 아래, 왼 = 오른쪽(x 큼), 오른 = 왼쪽."""
    side, (bx0, by0, bx1, by1), (sx0, sy0, sx1, sy1) = cfg["side"], cfg["band"], cfg["sheet_band"]
    if side == "bottom":
        b = [sx0 - PAD_ROW, by0 - PAD_CENTER, sx1 + PAD_ROW, by1 + PAD_PLAYER]
    elif side == "top":
        b = [sx0 - PAD_ROW, by0 - PAD_PLAYER, sx1 + PAD_ROW, by1 + PAD_CENTER]
    elif side == "left":
        b = [bx0 - PAD_PLAYER, sy0 - PAD_ROW, bx1 + PAD_CENTER, sy1 + PAD_ROW]
    else:
        b = [bx0 - PAD_CENTER, sy0 - PAD_ROW, bx1 + PAD_PLAYER, sy1 + PAD_ROW]
    return [max(0, b[0]), max(0, b[1]), min(1496, b[2]), min(1496, b[3])]


def view(ms: int, cfg: dict, scale: float) -> Image.Image:
    v = hc.band_crop(hc.load(ms), crop_box(cfg), cfg["side"])
    im = Image.fromarray(v)
    if scale != 1.0:
        im = im.resize((int(round(im.width * scale)), int(round(im.height * scale))), Image.LANCZOS)
    return im


def fname(dt_ms: int) -> str:
    return f"t_{round(dt_ms / 1000, 2) + 0.0:+07.2f}.jpg"


def sheet_times(frames: list, t0: int, w0: int) -> list:
    """표에 넣을 프레임: T0 − 10초 앞은 0.5초마다, 그 뒤 T0 + 3초까지 0.2초마다(가장 가까운 프레임, 겹치면 하나)."""
    want, t = [], w0
    while t < t0 - DENSE_MS:
        want.append(t)
        t += 500
    t = max(w0, t0 - DENSE_MS)
    while t <= t0 + POST_MS:
        want.append(t)
        t += 200
    fa = np.array(frames)
    pick = []
    for w in want:
        m = int(fa[int(np.argmin(np.abs(fa - w)))])
        if not pick or pick[-1] != m:
            pick.append(m)
    return pick


def build_item(it: dict) -> dict:
    cfg = hc.config(it["cfg"])
    d = PACK / "items" / it["id"]
    (d / "frames").mkdir(parents=True, exist_ok=True)
    t0, w0 = it["t0"], it["w0"]
    frames = hc.frame_range(w0, t0 + POST_MS)
    pick = sheet_times(frames, t0, w0)
    keep = set(pick)
    names, seen = [], set()
    imgs, fsize = {}, None
    for ms in frames:
        nm = fname(ms - t0)
        if nm in seen:
            nm = nm[:-4] + "b.jpg"
        seen.add(nm)
        im = view(ms, cfg, SCALE)
        im.save(d / "frames" / nm, quality=90)
        fsize = list(im.size)
        names.append((ms, nm))
        if ms in keep:                              # 표에 쓸 것만 1배로 줄여 들고 있음(메모리)
            imgs[ms] = im.resize((int(im.width * SHEET_SCALE / SCALE), int(im.height * SHEET_SCALE / SCALE)), Image.LANCZOS)
    k = -(-len(pick) // SHEET_ROWS)
    per = -(-len(pick) // k)
    sheets, f_lab, f_big = [], font(22), font(26)
    t0_row = next((m for m in pick if m >= t0), None)
    for s in range(k):
        part = pick[s * per:(s + 1) * per]
        rows = [imgs[m] for m in part]
        LW, GAP = 130, 6
        W = LW + max(r.width for r in rows)
        H = sum(r.height + GAP for r in rows)
        sh = Image.new("RGB", (W, H), (25, 25, 25))
        dr = ImageDraw.Draw(sh)
        y = 0
        for m, r in zip(part, rows):
            sh.paste(r, (LW, y))
            dt = round((m - t0) / 1000, 1) + 0.0
            if m == t0_row:
                dr.rectangle([0, y, W - 1, y + r.height - 1], outline=(255, 40, 40), width=6)
                dr.text((8, y + 8), "T0 >>", fill=(255, 60, 60), font=f_big)
                dr.text((8, y + 44), f"{dt:+.1f}s", fill=(255, 255, 255), font=f_lab)
            else:
                dr.text((8, y + 12), f"{dt:+.1f}s", fill=(230, 230, 230), font=f_lab)
            y += r.height + GAP
        nm = f"sheet_{s + 1:02d}.jpg"
        sh.save(d / nm, quality=90)
        sheets.append({"file": nm, "rows_s": [round((m - t0) / 1000, 2) for m in part], "size": [W, H]})
    info = {"id": it["id"], "n": it["n"], "discarded_tile": it["tile"], "range_s": [round((w0 - t0) / 1000, 2), POST_MS / 1000],
            "t0_note": "T0 = 이 버림 패가 강에 처음 보인 때(그 직전에 버렸다 — 몇 초 늦게 잡히기도 한다)",
            "n_frames": len(names), "n_sheets": len(sheets), "sheets": sheets,
            "frames": [{"t_s": round((m - t0) / 1000, 2), "file": f"frames/{nm}"} for m, nm in names],
            "image_note": f"대국자 시점(줄이 가로 · 아래가 그 사람 쪽 · 왼쪽이 그 사람 왼손 쪽). 낱장 {SCALE:g}배 · 표 {SHEET_SCALE:g}배"}
    (d / "item.json").write_bytes((json.dumps(info, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    return {"id": it["id"], "n_sheets": len(sheets), "n_frames": len(names), "sheet_size": sheets[0]["size"], "frame_size": fsize}


def chunks(ids: list, known: set, seed: int) -> list:
    """전 항목을 한 번씩 — 몫 수 = 정답 아는 항목 수 이하로 맞춰 몫마다 1 ~ 2개(몫 크기 7 안팎)."""
    rnd = random.Random(seed)
    kn, un = [i for i in ids if i in known], [i for i in ids if i not in known]
    rnd.shuffle(kn)
    rnd.shuffle(un)
    C = max(1, min(-(-len(ids) // CHUNK), len(kn))) if kn else -(-len(ids) // CHUNK)
    out = [[] for _ in range(C)]
    for q, i in enumerate(kn):
        out[q % C].append(i)
    q = 0
    for i in un:                                 # 가장 작은 몫부터 채움
        j = min(range(C), key=lambda c: (len(out[c]), c))
        out[j].append(i)
        q += 1
    for c in out:
        rnd.shuffle(c)
    rnd.shuffle(out)
    return [{"batch": f"{n + 1:02d}", "ids": c} for n, c in enumerate(out)]


def cmd_build(a):
    tests, knowns = test_items(), known_items()
    allit = tests + knowns
    rnd = random.Random(SEED)
    order = list(range(len(allit)))
    rnd.shuffle(order)
    for k, i in enumerate(order):
        allit[i]["id"] = f"i{k + 1:03d}"
    PACK.mkdir(parents=True, exist_ok=True)
    KEYD.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(a.workers) as ex:
        res = list(ex.map(build_item, sorted(allit, key=lambda x: x["id"])))
    ids = [r["id"] for r in res]
    hc.jsave(PACK / "index.json", {"items": res})
    known = {x["id"] for x in knowns}
    A, B = chunks(ids, known, SEED + 1), chunks(ids, known, SEED + 2)
    hc.jsave(PACK / "batches_A.json", A)
    hc.jsave(PACK / "batches_B.json", B)
    hc.jsave(KEYD / "key_private.json", {"note": "B1 꾸러미 열쇠 — 읽는 쪽에게 주지 않음. src = test(시험 자리) | known(정답 아는 hero). t0 = 기록기가 강에서 처음 본 겹쳐 보기 프레임(epoch ms)",
                                         "seed": SEED, "items": sorted(allit, key=lambda x: x["id"]),
                                         "known_per_batch": {nm: [[c["batch"], sum(x in known for x in c["ids"])] for c in L] for nm, L in (("A", A), ("B", B))}})
    ns, nf = [r["n_sheets"] for r in res], [r["n_frames"] for r in res]
    print(f"항목 {len(res)}(시험 {len(tests)} · 정답 아는 것 {len(knowns)}) · 묶음 A {len(A)}몫 · B {len(B)}몫 · 몫 크기 {sorted({len(c['ids']) for c in A + B})}"
          f" · 몫마다 정답 아는 것 A {sorted(sum(x in known for x in c['ids']) for c in A)} B {sorted(sum(x in known for x in c['ids']) for c in B)}")
    print(f"표 수 중앙 {np.median(ns):g} · 최대 {max(ns)} · 낱장 수 중앙 {np.median(nf):g} · 최대 {max(nf)}")
    sz = [tuple(r["sheet_size"]) for r in res]
    print("표 한 장 크기(첫 표) 예:", sorted(set(sz))[:3], "… 최대", max(sz, key=lambda s: s[0] * s[1]), "· 낱장 크기 예:", sorted({tuple(r["frame_size"]) for r in res})[:4])


# ------------------------------------------------------------------ 새는지 확인
LEAK = ["r1", "L16", "x_", "top", "bottom", "left", "right", "tsumogiri", "hand", "쯔모기리", "손에서", "V1", "확정", "읽어야", "불가", "규칙", "정답",
        "known", "test", "seat", "자리", "판 ", "game", "132644", "131655", "130921", "140450", "141259", "134151", "135321", "133610", "142013"]


def cmd_check(a):
    hits = []
    for p in PACK.rglob("*"):
        rel = str(p.relative_to(PACK))
        if p.name == "READER.md":
            continue
        for w in LEAK:
            if w in rel:
                hits.append(("이름", rel, w))
        if p.is_file() and p.suffix in (".json", ".txt", ".md"):
            s = p.read_text(encoding="utf-8")
            for w in LEAK:
                if w in s:
                    hits.append(("내용", rel, w))
    files = sum(1 for p in PACK.rglob("*") if p.is_file())
    print(f"꾸러미 파일 {files}개 · 찾은 낱말 {len(LEAK)}개 · 걸림 {len(hits)}")
    for h in hits[:40]:
        print("  ", h)


# ------------------------------------------------------------------ 확인 영상
def cmd_clip(a):
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    key = {x["id"]: x for x in hc.jload(KEYD / "key_private.json")["items"]}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    f_lab = font(30)
    for i in a.ids:
        it = key[i]
        cfg = hc.config(it["cfg"])
        t0 = it["t0"]
        frames = hc.frame_range(max(it["w0"], t0 - int(getattr(a, "pre", 12.0) * 1000)), t0 + POST_MS)   # --pre: 버림 앞 몇 초부터(차례 창 시작이 한도)
        fps = (len(frames) - 1) * 1000 / max(1, frames[-1] - frames[0])     # 평균 간격(녹화 간격이 고르지 않아 중앙값은 안 맞음)
        dst = out / f"{i}.mp4"
        proc, size = None, None
        for ms in frames:
            im = view(ms, cfg, SCALE)
            W, H = im.width + im.width % 2, im.height + 60 + (im.height + 60) % 2
            can = Image.new("RGB", (W, H), (20, 20, 20))
            can.paste(im, (0, 60))
            dr = ImageDraw.Draw(can)
            dt = round((ms - t0) / 1000, 1) + 0.0
            near = abs(ms - t0) <= 300
            dr.text((12, 12), f"{i}   T0 {dt:+.1f}s", fill=(255, 70, 70) if near or dt >= 0 else (240, 240, 240), font=f_lab)
            if near:
                dr.rectangle([0, 0, W - 1, H - 1], outline=(255, 40, 40), width=10)
            if proc is None:
                size = (W, H)
                proc = subprocess.Popen([ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                                         "-r", f"{fps:.3f}", "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20",
                                         "-movflags", "+faststart", str(dst)], stdin=subprocess.PIPE)
            proc.stdin.write(np.asarray(can.resize(size) if can.size != size else can).tobytes())
        proc.stdin.close()
        proc.wait()
        print(f"{dst} · {len(frames)}장 · {len(frames) / fps:.1f}초(초당 {fps:.2f}장 = 실제 속도) · {size[0]}x{size[1]} · {dst.stat().st_size / 1e6:.2f}MB")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("build")
    b.add_argument("--workers", type=int, default=6)
    sp.add_parser("check")
    c = sp.add_parser("clip")
    c.add_argument("ids", nargs="+")
    c.add_argument("--out", required=True)
    c.add_argument("--pre", type=float, default=12.0, help="버림(T0) 앞 몇 초부터 자를지 — 차례 창 시작보다 앞으로는 안 감")
    a = ap.parse_args()
    {"build": cmd_build, "check": cmd_check, "clip": cmd_clip}[a.cmd](a)


if __name__ == "__main__":
    main()
