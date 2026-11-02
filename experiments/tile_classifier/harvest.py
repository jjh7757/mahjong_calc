"""원본 사진의 앞면 패를 전부 잘라 임시 라벨을 붙인다(2026-11-01, 노트북 CPU, API 없음). build_crops.py 다음에.

상자: 운영 YOLO11 s 를 사진 4×4 토막(절반 겹침)에 돌려 앞면·무늬·탁자 안·크기로 거른다. 패 종류 출력은 안 쓴다.
임시 라벨: 라벨 크롭 259장 전부로 학습한 MobileNetV3 Small. 패 주인을 모르므로 상자 모양에 맞는 방향 중 확신이 가장 높은 쪽으로 돌린다.
같은 패: 같은 날 앞 사진들에 같은 자리·같은 임시 라벨이 있으면 dup 표시(10-24 은 같은 장면을 여러 번 찍었다).
HaseLab 은 라벨에 쓰지 않는다. 임시 라벨은 사람이 sheet_* 를 보고 고친 뒤에만 학습에 쓴다.
  python -I experiments/tile_classifier/harvest.py
결과 data/harvest/{crops/*.jpg, index.json, sheet_<종류>_<번호>.jpg}, data/model_259.pt
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import train as tr  # noqa: E402
from app import river as rv  # noqa: E402
from app import seat as st  # noqa: E402

DATA = HERE / "data"
OUT = DATA / "harvest"
CROPS = OUT / "crops"
EXP = ROOT / "experiments"
PAD = 0.12
GRID = 4
UNSURE = 0.6  # 이보다 확신이 낮으면 unsure 묶음


def boxes(det: rv.TileDetector, rgb: np.ndarray) -> list[tuple[int, int, int, int]]:
    H, W = rgb.shape[:2]
    ws, hs = W // GRID, H // GRID
    out = []
    for yy in range(0, H - hs + 1, hs // 2):
        for xx in range(0, W - ws + 1, ws // 2):
            part = np.ascontiguousarray(rgb[yy:yy + hs, xx:xx + ws])
            out += [(int(x + xx), int(y + yy), int(w), int(h)) for x, y, w, h in det.detect(part)]
    bs = rv.dedupe(rv.keep_faces(out, rv.white_mask(rgb)))
    bs = [b for b in bs if st.ink(rgb, b) >= st.INK_MIN]
    if not bs:
        return []
    short = statistics.median(min(b[2], b[3]) for b in bs)
    bs = [b for b in bs if 0.6 * short <= min(b[2], b[3]) <= 1.5 * short and max(b[2], b[3]) <= 2.2 * short]
    return st.on_table(bs, rgb, st.TABLE_REACH * short * 1.3)


def cut(rgb: np.ndarray, b: tuple[int, int, int, int]) -> Image.Image:
    x, y, w, h = b
    H, W = rgb.shape[:2]
    px, py = int(w * PAD), int(h * PAD)
    return Image.fromarray(rgb[max(0, y - py):min(H, y + h + py), max(0, x - px):min(W, x + w + px)])


def turns(w: int, h: int) -> tuple[int, ...]:
    if h > 1.15 * w:
        return (0, 2)
    if w > 1.15 * h:
        return (1, 3)
    return (0, 1, 2, 3)


def label(net, crop: Image.Image, w: int, h: int) -> tuple[str, float, int]:
    ts = turns(w, h)
    x = torch.stack([tr.PLAIN(tr.square(crop.rotate(90 * k, expand=True))) for k in ts])
    with torch.no_grad():
        p = torch.softmax(net(x), 1)
    best = p.max(1).values.argmax().item()
    return tr.CLASSES[p[best].argmax().item()], float(p[best].max()), ts[best]


def iou(a, b) -> float:
    ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    u = a[2] * a[3] + b[2] * b[3] - ix * iy
    return ix * iy / u if u else 0.0


def sheets(rows: list[dict], cell: int = 76, cols: int = 16, lines: int = 9) -> None:
    groups = defaultdict(list)
    for r in rows:
        if not r["dup"]:
            groups["unsure" if r["conf"] < UNSURE else r["pred"]].append(r)
    for g, v in groups.items():
        v.sort(key=lambda r: r["conf"])
        for k in range(0, len(v), cols * lines):
            part = v[k:k + cols * lines]
            im = Image.new("RGB", (cols * cell, (len(part) // cols + 1) * (cell + 14)), "white")
            d = ImageDraw.Draw(im)
            for i, r in enumerate(part):
                t = Image.open(CROPS / r["file"])
                t.thumbnail((cell, cell))
                x, y = (i % cols) * cell, (i // cols) * (cell + 14)
                im.paste(t, (x, y))
                d.text((x + 1, y + cell), f"{r['id']}" + (f" {r['pred']}" if g == "unsure" else ""), fill="blue")
            im.save(OUT / f"sheet_{g}_{k // (cols * lines)}.jpg", quality=88)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    torch.set_num_threads(12)
    CROPS.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    index = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
    images = {x["file"]: tr.square(Image.open(DATA / "crops" / x["file"]).convert("RGB")) for x in index}
    net = tr.train(index, images, 0)
    torch.save(net.state_dict(), DATA / "model_259.pt")
    print("모델 학습", round(time.perf_counter() - t0), "초", flush=True)

    photos = sorted(list((EXP / "visit_20261031/captures").glob("*/original.jpg")) + list((EXP / "field_20261024/captures").glob("*/original.jpg")), key=lambda p: p.parent.name)
    det = rv.TileDetector(conf=0.25)
    rows: list[dict] = []
    seen: dict[str, list[tuple]] = defaultdict(list)
    used = 0
    for p in photos:
        im = Image.open(p).convert("RGB")
        if im.width < 3000:
            print("건너뜀(저해상도)", p.parent.name, im.size, flush=True)
            continue
        used += 1
        rgb = np.asarray(im)
        day = p.parent.name[:8]
        bs = boxes(det, rgb)
        here = []
        for b in bs:
            crop = cut(rgb, b)
            pred, conf, k = label(net, crop, b[2], b[3])
            dup = any(pred == q and iou(b, c) > 0.5 for c, q in seen[day])
            i = len(rows)
            f = f"{i:05d}.jpg"
            crop.rotate(90 * k, expand=True).save(CROPS / f, quality=92)
            rows.append(dict(id=i, file=f, photo=p.parent.name, day=day, box=list(b), pred=pred, conf=round(conf, 3), turn=k, dup=dup))
            here.append((b, pred))
        seen[day] += here
        print(p.parent.name, im.size, "상자", len(bs), "새 패", sum(not r["dup"] for r in rows if r["photo"] == p.parent.name), round(time.perf_counter() - t0), "초", flush=True)
        (OUT / "index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    sheets(rows)
    new = [r for r in rows if not r["dup"]]
    print("사진", used, "상자", len(rows), "dup 뺀 패", len(new), "unsure", sum(r["conf"] < UNSURE for r in new))
    print("날짜별", Counter(r["day"] for r in new))
    print("종류별", dict(sorted(Counter(r["pred"] for r in new if r["conf"] >= UNSURE).items())))
    print("총", round(time.perf_counter() - t0), "초")


if __name__ == "__main__":
    main()
