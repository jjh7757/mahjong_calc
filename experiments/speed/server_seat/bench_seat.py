"""운영 서버(EC2 t4g.small)에서 자리 판독 검출 시간을 잰다(2026-10-26 밤). 운영 이미지(mahjong-recognizer)에 그대로 들어 있는
app/river.py(YOLO11s, onnxruntime 2스레드)를 쓰고, 틀 규칙은 experiments/speed/seat_yolo.py·seat_det_variants.py 를 옮긴 것.

  python bench_seat.py [--repeat 5] [--dir /bench]

재는 것(사진마다): 디코드, 흰 면 마스크, mosaic(띠 찾기 1번 + 모자이크 1번 + 틀), tiled(정사각 창 반 겹침, 지난 방식).
결과는 RESULT {...} 한 줄 + 표.
"""
from __future__ import annotations

import argparse
import io
import json
import platform
import resource
import statistics
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, "/srv/app")
from app import river as rv  # noqa: E402

TRUTH = {"k25_1": (10, [3]), "k28_1": (10, [3]), "k15_1": (13, []), "k26_1": (13, []), "k12_1": (10, [3]), "k16_1": (10, [3])}


def cluster(boxes, gx, gy):
    left, out = list(boxes), []
    while left:
        g = [left.pop()]
        i = 0
        while i < len(g):
            a = g[i]
            for x in left[:]:
                dx = max(0, max(a[0], x[0]) - min(a[0] + a[2], x[0] + x[2]))
                dy = max(0, max(a[1], x[1]) - min(a[1] + a[3], x[1] + x[3]))
                if dx < gx and dy < gy:
                    g.append(x)
                    left.remove(x)
            i += 1
        out.append(g)
    return out


def structure(white, boxes):
    faces = rv.dedupe(rv.keep_faces(boxes, white))
    if not faces:
        return None
    upright = [x for x in faces if x[3] > x[2]] or faces
    tw = statistics.median(x[2] for x in upright)
    th = statistics.median(x[3] for x in upright)
    groups = cluster(faces, tw * 0.35, th * 0.5)
    hand = sorted(max(groups, key=lambda g: (len(g), max(x[1] + x[3] for x in g))), key=lambda x: x[0])
    rest = [g for g in groups if g is not hand]
    hx1 = max(x[0] + x[2] for x in hand)
    hcy = statistics.mean(x[1] + x[3] / 2 for x in hand)
    sep = None
    near = [g for g in rest if len(g) == 1 and 0 <= g[0][0] - hx1 < 2.5 * tw and abs(g[0][1] + g[0][3] / 2 - hcy) < th * 0.6]
    if near:
        sep = min(near, key=lambda g: g[0][0])[0]
        rest = [g for g in rest if g[0] is not sep]
    melds = [g for g in rest if 3 <= len(g) <= 4 and min(x[0] for x in g) > hx1 - tw]
    return len(hand) + (1 if sep else 0), [len(m) for m in melds]


def valid(got):
    return got is not None and got[0] + 3 * len(got[1]) in (13, 14)


def band(det, rgb, white):
    faces = rv.dedupe(rv.keep_faces(det.detect(rgb), white))
    if len(faces) < 3:
        return None
    th = statistics.median(f[3] for f in faces)
    cys = sorted(f[1] + f[3] / 2 for f in faces)
    best = max(cys, key=lambda c: sum(abs(c - d) < th for d in cys))
    return int(best - 1.5 * th), int(best + 1.5 * th), th


def mosaic(det, rgb, white, k=4, pad=1.5):
    got = band(det, rgb, white)
    if got is None:
        return []
    y0, y1, th = got
    H, W = rgb.shape[:2]
    y0, y1 = max(0, int(y0 - 0.5 * th)), min(H, int(y1 + 0.5 * th))
    h = y1 - y0
    ov = int(pad * th * 0.75)
    seg = (W + ov * (k - 1)) // k + 1
    xs = [min(i * (seg - ov), W - seg) for i in range(k)]
    canvas = np.full((h * k, seg, 3), 114, np.uint8)
    for i, x in enumerate(xs):
        canvas[i * h:(i + 1) * h] = rgb[y0:y1, x:x + seg]
    boxes = []
    for bx in det.detect(canvas):
        i = min(k - 1, (bx[1] + bx[3] // 2) // h)
        yy = bx[1] - i * h
        if yy < -0.2 * bx[3] or yy + bx[3] > h + 0.2 * bx[3]:
            continue
        boxes.append((bx[0] + xs[i], max(0, yy) + y0, bx[2], min(bx[3], h - max(0, yy))))
    return boxes


def tiled(det, rgb):
    H, W = rgb.shape[:2]
    side = min(H, W)
    xs = list(range(0, max(1, W - side) + 1, side // 2))
    if xs[-1] + side < W:
        xs.append(W - side)
    boxes = []
    for x0 in xs:
        for bx in det.detect(rgb[:, x0:x0 + side]):
            boxes.append((bx[0] + x0, bx[1], bx[2], bx[3]))
    return boxes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=5)
    ap.add_argument("--dir", default=str(Path(__file__).parent))
    a = ap.parse_args()
    t0 = time.perf_counter()
    det = rv.TileDetector(conf=0.04)
    det.detect(np.zeros((640, 640, 3), np.uint8))  # 첫 추론(세션 준비)은 따로
    load_s = time.perf_counter() - t0
    data = {p.stem: p.read_bytes() for p in sorted(Path(a.dir, "photos").glob("*.jpg"))}
    rows = []
    for rep in range(a.repeat):
        for name, jpg in data.items():
            r = {"photo": name, "rep": rep}
            t = time.perf_counter()
            rgb = np.asarray(Image.open(io.BytesIO(jpg)).convert("RGB"))
            r["decode"] = time.perf_counter() - t
            t = time.perf_counter()
            white = rv.white_mask(rgb)
            r["white"] = time.perf_counter() - t
            t = time.perf_counter()
            got = structure(white, mosaic(det, rgb, white))
            r["mosaic"] = time.perf_counter() - t
            r["mosaic_ok"] = got == TRUTH[name]
            r["mosaic_valid"] = valid(got)
            t = time.perf_counter()
            got2 = structure(white, tiled(det, rgb))
            r["tiled"] = time.perf_counter() - t
            r["tiled_ok"] = got2 == TRUTH[name]
            rows.append(r)
            print(f"{name} #{rep} decode {r['decode']:.2f} white {r['white']:.2f} mosaic {r['mosaic']:.2f} "
                  f"({'OK' if r['mosaic_ok'] else ('검사통과' if r['mosaic_valid'] else '실패→통째')}) tiled {r['tiled']:.2f} "
                  f"({'OK' if r['tiled_ok'] else 'X'})", flush=True)
    maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    med = lambda k, ps=None: statistics.median(r[k] for r in rows if ps is None or r["photo"] in ps)  # noqa: E731
    mx = lambda k: max(r[k] for r in rows)  # noqa: E731
    summary = {"machine": platform.machine(), "load_s": round(load_s, 2), "maxrss_mb": round(maxrss),
               **{f"{k}_med": round(med(k), 3) for k in ("decode", "white", "mosaic", "tiled")},
               **{f"{k}_max": round(mx(k), 3) for k in ("decode", "white", "mosaic", "tiled")},
               "mosaic_CD_med": round(med("mosaic", {"k15_1", "k26_1", "k12_1", "k16_1"}), 3),
               "mosaic_B_med": round(med("mosaic", {"k25_1", "k28_1"}), 3),
               "mosaic_ok": sum(r["mosaic_ok"] for r in rows), "tiled_ok": sum(r["tiled_ok"] for r in rows), "n": len(rows)}
    print("RESULT " + json.dumps(summary))


if __name__ == "__main__":
    main()
