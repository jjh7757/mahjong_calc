"""프레임용 분류기 시험(2026-11-11, 사용자 "일단 학습해보고 생각하자"). frame_split.py(metrics 표 12-1) 다음.

harvest: 화료 사진이 바로 뒤따르는 추적 판에서 프레임 크롭 + 라벨을 모은다.
  라벨 = 같은 판 12MP 화료 사진의 가운데 영역(강) 앞면 패 판독(운영 분류기, 확신 ≥0.9). 화료 사진과 프레임은 같은 화각이라 사진 좌표로 잇는다.
  마지막 프레임에서 거꾸로 따라가며 같은 자리 검출을 그 패로 본다. 멈춤: 그 자리에 3프레임 넘게 없음 / 프레임 읽기가 라벨과 다른데 확신 ≥0.9
  (같은 자리에 전에 다른 패가 있었던 경우 — 울어 가고 다음 패가 놓임).
  시험 판(R2·R3a·R4 = 11-07 15:30~15:44 트랙)은 모으지 않는다.
sheets: 독립 검토용 — 패(칸)마다 [화료 사진 크롭 | 프레임 크롭] 을 라벨별로 늘어놓은 그림.
train A|B: 운영 분류기(cls6_all.pt)에서 이어 학습. A = 10-31 프레임만, B = 10-31 + 11-07(시험 판 뺀) 프레임. 기존 실제 크롭 1,548장도 같이.
결과물은 experiments/tile_classifier/data/frames/ (커밋 안 함), 모델 server_bench/models/clsF_<A|B>.onnx.
"""
from __future__ import annotations

import io
import json
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import paifu_frames as pf  # noqa: E402
import frame_split as fs  # noqa: E402

TC = HERE.parent / "tile_classifier"
OUT = TC / "data" / "frames"
MODELS = TC / "server_bench" / "models"

# (방문, 트랙, 화료 사진) — 마지막 프레임 뒤 120초 안에 화료 사진이 있는 판. 시험 판·N1(카메라 다름)·154548(사진이 2분 뒤)은 뺌.
ROUNDS = [
    ("visit_20261031", "20261031_122417_track", "20261031_123140"),
    ("visit_20261031", "20261031_123457_track", "20261031_124654"),
    ("visit_20261031", "20261031_124830_track", "20261031_125839"),
    ("visit_20261031", "20261031_125948_track", "20261031_131411"),
    ("visit_20261031", "20261031_131554_track", "20261031_132239"),
    ("visit_20261031", "20261031_132352_track", "20261031_132954"),
    ("visit_20261031", "20261031_133112_track", "20261031_133826"),
    ("visit_20261107", "20261107_120534_track", "20261107_121515"),
    ("visit_20261107", "20261107_121543_track", "20261107_122315"),
    ("visit_20261107", "20261107_122355_track", "20261107_123102"),
    ("visit_20261107", "20261107_123155_track", "20261107_123653"),
    ("visit_20261107", "20261107_123820_track", "20261107_124650"),
    ("visit_20261107", "20261107_124740_track", "20261107_125510"),
    ("visit_20261107", "20261107_125549_track", "20261107_130623"),
    ("visit_20261107", "20261107_130655_track", "20261107_140015"),
]
TEST_TRACKS = {"20261107_153128_track", "20261107_153423_track", "20261107_154029_track"}
assert not TEST_TRACKS & {r[1] for r in ROUNDS}
MAX_GAP = 3
PER_TILE = 8  # 학습 때 패(칸) 하나에서 뽑는 프레임 수 상한(3초 간격 프레임은 거의 같은 그림)


def upright(im: Image.Image, w: int, h: int, side: str) -> Image.Image:
    """read_small 이 방향을 고르는 것과 같은 기준으로 세운다(180° 는 학습 증강이 맡는다)."""
    k = 0 if h > 1.15 * w else 1 if w > 1.15 * h else (0 if side in ("bottom", "top") else 1)
    return im.rotate(90, expand=True) if k else im


def prep(im: Image.Image, w: int, h: int, side: str) -> Image.Image:
    """read_small 과 같게: 긴 변 SMALL_TILE(96)로 키우고 세움. 그 뒤 train.square 가 128 회색 바탕에 놓는다(_tensor 와 같음)."""
    from app.local_read import SMALL_TILE

    s = SMALL_TILE / max(im.size)
    im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.BICUBIC)
    return upright(im, w, h, side)


CROP_R = 0.235  # 가운데 영역 반 크기(사진 폭 비율). 1020 에서 240px — 강 전체(기계 반 68 × 2.6 ≈ 177 + 격자 중심 어긋남)를 덮는다
TOL = 12 / 1020  # 같은 패로 보는 중심 거리(사진 폭 비율, 1020 에서 12px ≈ 패 폭 절반)


def center_tiles(reader, rgb: np.ndarray, grid: dict) -> list[dict]:
    """격자 가운데 칸 중심 둘레의 앞면 패 전부(자리 배정 없음 — 기계 위치 추정이 10-31 한 판에서 100px 어긋나 강 패를 반 넘게 잃었다).
    방향이 모호한(정사각형에 가까운) 상자는 뺀다 — 세울 방향을 상자 모양으로만 정하므로."""
    H, W = rgb.shape[:2]
    cx, cy, R = (grid["x1"] + grid["x2"]) / 2000 * W, (grid["y1"] + grid["y2"]) / 2000 * H, CROP_R * W
    x0, y0 = int(max(0, cx - R)), int(max(0, cy - R))
    crop = rgb[y0:int(min(H, cy + R)), x0:int(min(W, cx + R))]
    out = []
    for b in pf.rv.dedupe(pf.rv.keep_faces(reader.detect(crop, low=False), pf.rv.white_mask(crop), 0.45)):
        if not (b[3] > 1.15 * b[2] or b[2] > 1.15 * b[3]):
            continue
        gb = (b[0] + x0, b[1] + y0, b[2], b[3])
        t, c = reader.read_small(rgb, gb)
        out.append({"box": gb, "x": (gb[0] + gb[2] / 2) / W, "y": (gb[1] + gb[3] / 2) / W, "t": t, "c": c, "side": "bottom"})
    return out


def cmd_harvest():
    from app.local_read import cut

    reader = pf.LocalReader(threads=4)
    (OUT / "crops").mkdir(parents=True, exist_ok=True)
    for f in (OUT / "crops").glob("*.png"):
        f.unlink()
    index, tiles_meta, log = [], [], []
    for visit, track, photo in ROUNDS:
        cap = HERE.parent / visit / "captures"
        t0 = time.perf_counter()
        frames = list(pf.frames_of(cap / track, None, None))
        grid = frames[-1][1]
        full = np.asarray(Image.open(cap / photo / "original.jpg").convert("RGB"))
        allref = center_tiles(reader, full, grid)
        ref = [t for t in allref if t["c"] >= 0.9]
        dets, rgbs = [], []
        for f, g, jpg in frames:
            rgb = np.asarray(Image.open(io.BytesIO(jpg)).convert("RGB"))
            dets.append(center_tiles(reader, rgb, g))
            rgbs.append(rgb)
        n_crops = n_match_last = 0
        for ti, r in enumerate(ref):
            tid = f"{photo}_{ti:03d}"
            px, py = r["x"], r["y"]
            gap, got = 0, []
            for fi in range(len(frames) - 1, -1, -1):
                cand = [(((d["x"] - px) ** 2 + (d["y"] - py) ** 2) ** 0.5, d) for d in dets[fi]]
                cand = [c for c in cand if c[0] < TOL]
                if not cand:
                    gap += 1
                    if gap > MAX_GAP:
                        break
                    continue
                d = min(cand, key=lambda c: c[0])[1]
                if d["t"] != r["t"] and d["c"] >= 0.9:
                    break
                gap = 0
                px, py = d["x"], d["y"]
                got.append((fi, d))
            if not got:
                continue
            n_match_last += got[0][0] >= len(frames) - 1 - MAX_GAP
            x, y, w, h = r["box"]
            cut(full, r["box"]).save(OUT / "crops" / f"p_{tid}.png")
            tiles_meta.append(dict(tid=tid, tile=r["t"], conf=r["c"], side=r["side"], visit=visit, track=track, photo=photo, pw=w, ph=h, n=len(got),
                                   agree=sum(1 for _, d in got if d["t"] == r["t"])))
            for fi, d in got:
                x, y, w, h = d["box"]
                name = f"f_{tid}_{fi:04d}.png"
                cut(rgbs[fi], d["box"]).save(OUT / "crops" / name)
                index.append(dict(file=name, tid=tid, tile=r["t"], side=r["side"], w=w, h=h, visit=visit, track=track, frame=frames[fi][0]["file"],
                                  read=d["t"], read_c=d["c"]))
                n_crops += 1
        line = (f"{track} 프레임 {len(frames)} | 화료 사진 가운데 앞면 {len(allref)}, 확신≥0.9 {len(ref)} → 프레임과 이어짐 {sum(1 for t in tiles_meta if t['photo'] == photo)}"
                f"(마지막 프레임 근처부터 {n_match_last}) | 크롭 {n_crops} | {time.perf_counter() - t0:.0f}초")
        print(line, flush=True)
        log.append(line)
        (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        (OUT / "tiles.json").write_text(json.dumps(tiles_meta, ensure_ascii=False, indent=0), encoding="utf-8")
    (OUT / "harvest.log").write_text(chr(10).join(log), encoding="utf-8")
    summary()


def summary():
    index = json.loads((OUT / "index.json").read_text(encoding="utf-8"))
    tiles = json.loads((OUT / "tiles.json").read_text(encoding="utf-8"))
    for v in ("visit_20261031", "visit_20261107"):
        ix = [x for x in index if x["visit"] == v]
        tl = [t for t in tiles if t["visit"] == v]
        print(f"{v}: 패(칸) {len(tl)} 크롭 {len(ix)} · 프레임 읽기(운영 분류기)가 라벨과 같음 {sum(x['read'] == x['tile'] for x in ix)}/{len(ix)}"
              f" · 패별 프레임 수 중앙 {int(np.median([t['n'] for t in tl])) if tl else 0}")
        c = Counter(t["tile"] for t in tl)
        print("   종류별 패 수:", " ".join(f"{k}:{c[k]}" for k in sorted(c, key=lambda t: (t[1], t[0]))))


def cmd_sheets():
    """검토용 그림: 라벨 순서로, 칸마다 [화료 사진 크롭 | 프레임 크롭(라벨과 가장 다르게 읽힌 것 우선)] + 라벨·tid 끝 번호."""
    index = json.loads((OUT / "index.json").read_text(encoding="utf-8"))
    tiles = json.loads((OUT / "tiles.json").read_text(encoding="utf-8"))
    by = defaultdict(list)
    for x in index:
        by[x["tid"]].append(x)
    order = [f"{n}{s}" for s in "mps" for n in range(1, 10)] + ["0m", "0p", "0s"] + [f"{n}z" for n in range(1, 8)]
    tiles.sort(key=lambda t: (order.index(t["tile"]), t["tid"]))
    (OUT / "sheets").mkdir(exist_ok=True)
    CW, CH, COLS, ROWS = 196, 150, 8, 7
    rows = []
    for i, t in enumerate(tiles):
        t["no"] = i
        rows.append(t)
    for p in range(0, len(rows), COLS * ROWS):
        im = Image.new("RGB", (CW * COLS, CH * ROWS), "white")
        dr = ImageDraw.Draw(im)
        for j, t in enumerate(rows[p:p + COLS * ROWS]):
            ox, oy = (j % COLS) * CW, (j // COLS) * CH
            a = upright(Image.open(OUT / "crops" / f"p_{t['tid']}.png"), t["pw"], t["ph"], t["side"])
            a.thumbnail((90, 120))
            fr = by[t["tid"]]
            pick = min(fr, key=lambda x: (x["read"] == x["tile"], x["read_c"] if x["read"] == x["tile"] else -x["read_c"]))
            b = upright(Image.open(OUT / "crops" / pick["file"]), pick["w"], pick["h"], pick["side"])
            s = 120 / max(b.size)
            b = b.resize((round(b.width * s), round(b.height * s)), Image.NEAREST)
            im.paste(a, (ox + 4, oy + 22))
            im.paste(b, (ox + 100, oy + 22))
            dr.text((ox + 4, oy + 4), f"#{t['no']} {t['tile']}  f:{pick['read']} {t['agree']}/{t['n']}", fill="black")
            dr.rectangle((ox, oy, ox + CW - 1, oy + CH - 1), outline=(200, 200, 200))
        im.save(OUT / "sheets" / f"sheet_{p // (COLS * ROWS):02d}.png")
    (OUT / "sheet_rows.json").write_text(json.dumps([{k: t[k] for k in ("no", "tid", "tile", "conf", "side", "n", "agree", "visit")} for t in rows],
                                                    ensure_ascii=False, indent=0), encoding="utf-8")
    print("그림", len(list((OUT / "sheets").glob("*.png"))), "패", len(rows))


def cmd_merge():
    """에이전트가 낸 clean_P*.json(패 고침·패 뺌·크롭 뺌·모름)을 labels.json 하나로. 모름(unsure)은 학습에서 뺀다."""
    index = json.loads((OUT / "index.json").read_text(encoding="utf-8"))
    files, tids = {x["file"] for x in index}, {x["tid"] for x in index}
    lab = {"drop": [], "fix": {}, "crop_drop": [], "unsure": [], "parts": {}}
    for f in sorted(OUT.glob("clean_P*.json")):
        c = json.loads(f.read_text(encoding="utf-8"))
        bad = [x for x in c.get("crop_drop", []) if x["file"] not in files] + [x for x in c.get("tile_drop", []) + c.get("tile_fix", []) if x["tid"] not in tids]
        lab["drop"] += [x["tid"] for x in c.get("tile_drop", [])]
        lab["fix"].update({x["tid"]: x["to"] for x in c.get("tile_fix", [])})
        lab["crop_drop"] += [x["file"] for x in c.get("crop_drop", [])]
        for x in c.get("unsure", []):
            lab["unsure"] += [v for v in x.values() if isinstance(v, str) and (v in files or v in tids)]
        lab["parts"][c.get("part", f.stem)] = dict(tile_fix=len(c.get("tile_fix", [])), tile_drop=len(c.get("tile_drop", [])), crop_drop=len(c.get("crop_drop", [])),
                                                   unsure=len(c.get("unsure", [])), unknown_ids=len(bad), reasons=dict(Counter(x.get("reason") for x in c.get("crop_drop", []))),
                                                   checked=c.get("checked"))
    # 검토 반영(자동 규칙): 반쪽 상자 — 프레임 상자 짧은 변이 화료 사진 상자(÷4)의 0.75배 미만. 에이전트 넷이 모두 가장 큰 오염원으로 꼽았고
    # 몫마다 몇 장씩 놓쳤다(P1 1·P2 1·P3 13). 기준을 패 중앙값이 아니라 화료 사진 상자로 둔 것은 크롭 대부분이 반쪽인 패가 있어서(P2 지적).
    tl = {t["tid"]: t for t in json.loads((OUT / "tiles.json").read_text(encoding="utf-8"))}
    have = set(lab["crop_drop"])
    auto = [x["file"] for x in index if min(x["w"], x["h"]) < 0.75 * min(tl[x["tid"]]["pw"], tl[x["tid"]]["ph"]) / 4 and x["file"] not in have]
    lab["crop_drop"] += auto
    lab["auto_small"] = auto
    (OUT / "labels.json").write_text(json.dumps(lab, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(lab["parts"], ensure_ascii=False, indent=1))
    print("자동(반쪽 상자) 추가로 뺌", len(auto))
    print("합계: 패 뺌", len(lab["drop"]), "패 고침", len(lab["fix"]), "크롭 뺌", len(lab["crop_drop"]), "모름", len(lab["unsure"]))


def clean_index(root: Path = OUT, lab: dict | None = None, keep_unsure: bool = False) -> list[dict]:
    """labels.json 을 반영한 크롭 목록(라벨 고침·뺄 것 반영)."""
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    if lab is None:
        lp = root / "labels.json"
        lab = json.loads(lp.read_text(encoding="utf-8")) if lp.exists() else {}
    drop, fix, cdrop = set(lab.get("drop", [])), lab.get("fix", {}), set(lab.get("crop_drop", []))
    uns = set() if keep_unsure else set(lab.get("unsure", []))
    out = []
    for x in index:
        if x["tid"] in drop or x["file"] in cdrop or x["tid"] in uns or x["file"] in uns:
            continue
        out.append({**x, "tile": fix.get(x["tid"], x["tile"])})
    return out


def frame_items(variant: str) -> tuple[list[dict], dict]:
    """학습용 프레임 크롭(검토 반영). 패마다 PER_TILE 장까지(씨드 고정)."""
    sys.path.insert(0, str(TC))
    import train as tr

    visits = {"A": ("visit_20261031",), "B": ("visit_20261031", "visit_20261107")}[variant]
    by = defaultdict(list)
    for x in clean_index():
        if x["visit"] in visits and x["track"] not in TEST_TRACKS:
            by[x["tid"]].append(x)
    rnd = random.Random(0)
    items, images = [], {}
    for tid, v in sorted(by.items()):
        for x in rnd.sample(v, min(PER_TILE, len(v))):
            items.append(dict(file=x["file"], tile=x["tile"], tid=tid))
            images[x["file"]] = tr.square(prep(Image.open(OUT / "crops" / x["file"]).convert("RGB"), x["w"], x["h"], x["side"]))
    return items, images


def read_crop(reader, im: Image.Image, w: int, h: int) -> tuple[str, float]:
    """저장된 크롭(cut 결과)을 서버 read_small 과 같게 읽는다(상자 모양으로 돌려 볼 방향을 고름)."""
    from app.local_read import CLASSES, SMALL_TILE

    s = SMALL_TILE / max(im.size)
    im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.BICUBIC)
    ts = (0, 2) if h > 1.15 * w else (1, 3) if w > 1.15 * h else (0, 1, 2, 3)
    p = reader.probs([im.rotate(90 * k, expand=True) for k in ts])
    i = int(p.max(1).argmax())
    return CLASSES[int(p[i].argmax())], round(float(p[i].max()), 3)


def cmd_extra():
    """확장 평가 세트(data/frames_eval, 에이전트가 수집·검증)를 FS_CLS 분류기로 한 프레임씩 읽어 채점. 모름(unsure)은 넣은 값·뺀 값 둘 다."""
    root = TC / "data" / "frames_eval"
    c = json.loads((root / "clean.json").read_text(encoding="utf-8"))
    lab = {"drop": [x["tid"] for x in c.get("tile_drop", [])], "fix": {x["tid"]: x["to"] for x in c.get("tile_fix", [])},
           "crop_drop": [x["file"] for x in c.get("crop_drop", [])], "unsure": [v for x in c.get("unsure", []) for v in x.values() if isinstance(v, str)]}
    reader = fs.make_reader()
    res = {}
    for keep in (True, False):
        rows = clean_index(root, lab, keep_unsure=keep)
        if keep:
            reads = {x["file"]: read_crop(reader, Image.open(root / "crops" / x["file"]).convert("RGB"), x["w"], x["h"]) for x in rows}
        per = defaultdict(lambda: [0, 0])
        for x in rows:
            per[x["track"]][1] += 1
            per[x["track"]][0] += reads[x["file"]][0] == x["tile"]
        ok, n = sum(v[0] for v in per.values()), sum(v[1] for v in per.values())
        key = "모름 포함" if keep else "모름 뺌"
        res[key] = {"ok": ok, "n": n, "tiles": len({x["tid"] for x in rows}), "per": dict(per)}
        print(f"{key}: 한 프레임 읽기 {ok}/{n} = {ok / max(1, n):.3f} (패 {res[key]['tiles']}칸) ", {k: f"{a}/{b}" for k, (a, b) in per.items()})
    same = sum(reads[x["file"]][0] == x["read"] for x in rows)
    print(f"(저장된 운영 판독과 같은 답 {same}/{len(rows)})")
    (HERE / "results" / f"frame_extra{fs.TAG}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


def cmd_train(variant: str, epochs: int = 20, alt: bool = False):
    """alt = 두 번째 분류기(불확실성 신호 S3 짝): 운영 두 번째 분류기(cls6_all_s1.pt)에서 씨드 21 로 같은 방식."""
    sys.path.insert(0, str(TC))
    import torch
    import review as rw
    import train as tr

    sys.stdout.reconfigure(encoding="utf-8")
    torch.set_num_threads(12)
    base = json.loads((tr.DATA / "index.json").read_text(encoding="utf-8"))
    add = rw.extra()
    images = {x["file"]: tr.square(Image.open(tr.CROPS / x["file"]).convert("RGB")) for x in base}
    images.update({x["file"]: tr.square(Image.open(x["path"]).convert("RGB")) for x in add})
    fitems, fimages = frame_items(variant)
    images.update(fimages)
    pool = base + add + fitems
    print(f"변형 {variant}: 기존 실제 크롭 {len(base) + len(add)} + 프레임 크롭 {len(fitems)}(패 {len({x['tid'] for x in fitems})}) = {len(pool)}", flush=True)
    tr.EPOCHS = epochs
    init_name, seed = ("cls6_all_s1.pt", 21) if alt else ("cls6_all.pt", 20)
    init = torch.load(tr.DATA / init_name, map_location="cpu")
    t0 = time.perf_counter()
    net = tr.train(pool, images, seed, tr.AUG_R180, init=init)
    name = f"clsF_{variant}" + ("_s1" if alt else "")
    torch.save(net.state_dict(), tr.DATA / f"{name}.pt")
    tr.export(net, MODELS / f"{name}.onnx")
    rec = dict(variant=variant, n=len(pool), frames=len(fitems), frame_tiles=len({x["tid"] for x in fitems}), epochs=epochs, seed=seed,
               init=init_name, aug="AUG_R180", secs=round(time.perf_counter() - t0), finished=time.strftime("%Y-%m-%d %H:%M:%S"),
               frame_class_count=dict(Counter(x["tile"] for x in fitems)))
    (OUT / f"train_{variant}{'_s1' if alt else ''}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(name, rec, flush=True)


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "harvest":
        cmd_harvest()
    elif c == "summary":
        summary()
    elif c == "sheets":
        cmd_sheets()
    elif c == "train":
        cmd_train(sys.argv[2], alt="--alt" in sys.argv)
    elif c == "merge":
        cmd_merge()
    elif c == "extra":
        cmd_extra()
