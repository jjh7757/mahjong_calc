"""자리 판독 검출(seat_yolo.py)을 빠르게: 창 크기·겹침·모델·손패 띠만 돌리기 변형별로 B·C·D 6장 틀 정답과 검출 시간(노트북, 2스레드).
Gemini 호출 없음. 운영 서버(t4g.small)는 노트북의 약 3배(NOTES 19: 강 틀 3장 1.5~1.6초 vs 0.4~0.66초).

  python -I experiments/speed/seat_det_variants.py
"""
from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
import bench as b  # noqa: E402
import seat_yolo as sy  # noqa: E402

rv = sy.rv


def windows(H: int, W: int, side: int, step: float, y_range=(0, None)):
    y0r, y1r = y_range[0], (y_range[1] if y_range[1] is not None else H)

    def starts(lo, hi):
        n = hi - lo
        if n <= side:
            return [max(0, min(lo, H - side))] if hi <= H else [lo]
        xs = list(range(lo, hi - side + 1, max(1, int(side * step))))
        if xs[-1] + side < hi:
            xs.append(hi - side)
        return xs

    ys = starts(y0r, y1r) if y1r - y0r > side else [max(0, min(y0r - (side - (y1r - y0r)) // 2, H - side))]
    return [(x, y) for y in ys for x in starts(0, W)]


def run(det, rgb, side, step, y_range=(0, None)):
    H, W = rgb.shape[:2]
    side = min(side, H, W)
    boxes, n = [], 0
    for x0, y0 in windows(H, W, side, step, y_range):
        n += 1
        for bx in det.detect(rgb[y0:y0 + side, x0:x0 + side]):
            boxes.append((bx[0] + x0, bx[1] + y0, bx[2], bx[3]))
    return boxes, n


def band(det, rgb, half: float = 1.5):
    """한 번 통째로(640 letterbox) 돌려 패 면 상자의 세로 범위 → 손패 줄 띠. 못 찾으면 None."""
    faces = rv.dedupe(rv.keep_faces(det.detect(rgb), rv.white_mask(rgb)))
    if len(faces) < 3:
        return None
    th = statistics.median(f[3] for f in faces)
    # 가장 많은 상자가 모인 띠(높이 2패) — 손패 줄
    cys = sorted(f[1] + f[3] / 2 for f in faces)
    best = max(cys, key=lambda c: sum(abs(c - d) < th for d in cys))
    return int(best - half * th), int(best + half * th), th


OWN = True  # 토막마다 자기 몫(겹친 부분의 가운데까지)에 가운데가 있는 상자만 — 겹친 곳의 같은 패 두 번 잡기 방지(타일 추론의 일반 처리)


def mosaic(det, rgb, k: int | None = None, pad: float = 1.5, half: float = 1.5):
    """손패 띠(통째 한 번으로 찾음)를 가로로 k 토막(이웃과 패 1.5개 겹침)으로 잘라 세로로 쌓아 한 번에 추론 → 원래 좌표로.
    추론 2번(띠 찾기 + 모자이크)."""
    got = band(det, rgb, half)
    if got is None:
        return None, 1
    y0, y1, th = got
    H, W = rgb.shape[:2]
    y0, y1 = max(0, int(y0 - 0.5 * th)), min(H, int(y1 + 0.5 * th))
    h = y1 - y0
    k = k or max(1, round((W / h) ** 0.5))
    ov = int(pad * th * 0.75)  # 패 너비 ≈ 높이 × 0.75
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
            continue  # 토막 경계를 넘은 상자
        if OWN:  # 이웃 토막과 겹친 구간의 가운데를 경계로(원본 좌표)
            cx = xs[i] + bx[0] + bx[2] / 2
            lo = 0 if i == 0 else (xs[i] + xs[i - 1] + seg) / 2
            hi = W if i == k - 1 else (xs[i + 1] + xs[i] + seg) / 2
            if not lo <= cx < hi:
                continue
        boxes.append((bx[0] + xs[i], max(0, yy) + y0, bx[2], min(bx[3], h - max(0, yy))))
    return boxes, 2


def main():
    dets = sy.detectors(0.04, "sm")
    det = dict(dets)
    imgs = {}
    for s in "BCD":
        for p in b.PHOTOS[s]:
            imgs[p] = (s, np.asarray(Image.open(b.G / s / p / b.TRUTH[s][0]).convert("RGB")))
    # 한 번 추론 시간
    rgb = imgs["k12_1"][1][:861, :861]
    for m in "sm":
        det[m].detect(rgb)
        t0 = time.perf_counter()
        for _ in range(5):
            det[m].detect(rgb)
        print(f"추론 1회 {m}: {(time.perf_counter() - t0) / 5:.3f}초")

    def truth_ok(s, st):
        th, tm = len(b.TRUTH[s][1].split()), [len(x.split()) for x in b.TRUTH[s][2]]
        return st is not None and (len(st["hand"]) + (1 if st["separate"] else 0), [len(m) for m in st["melds"]]) == (th, tm)

    variants = []
    for m in "sm":
        for k in (0, 2, 3, 4):
            variants.append((f"{m} mosaic k{k or 'auto'}", m, k, 0, "mosaic"))
    for m in "sm":
        for win in (1.0, 1.25, 1.5):
            for step in (0.5, 0.75, 1.0):
                variants.append((f"{m} win{win} step{step}", m, win, step, False))
        for win in (0.5, 0.7, 1.0):
            for step in (0.5, 0.75):
                variants.append((f"{m} band×{win} step{step}", m, win, step, True))
    if "--mosaic" in sys.argv:
        variants = [v for v in variants if v[4] == "mosaic"]
    for name, m, win, step, use_band in variants:
        res = []
        for p, (s, rgb) in imgs.items():
            H, W = rgb.shape[:2]
            t0 = time.perf_counter()
            if use_band == "mosaic":
                boxes, n = mosaic(det[m], rgb, win or None)
                if boxes is None:
                    res.append((p, False, False, n, time.perf_counter() - t0))
                    continue
            elif use_band:
                got = band(det[m], rgb)
                if got is None:
                    res.append((p, False, False, 1, time.perf_counter() - t0))
                    continue
                y0, y1, th = got
                side = int(H * win)
                boxes, n = run(det[m], rgb, side, step, (max(0, y0), min(H, y1)))
                n += 1
            else:
                boxes, n = run(det[m], rgb, int(H * win), step)
            st = sy.structure(rgb, boxes)
            res.append((p, sy.valid(st), truth_ok(s, st), n, time.perf_counter() - t0))
        ok = sum(r[2] for r in res)
        bad = sum(r[1] and not r[2] for r in res)  # 장수 검사는 통과했는데 틀린 틀(위험)
        print(f"{name:22s} 틀 정답 {ok}/6 검사통과·틀림 {bad}  추론 {[r[3] for r in res]}  "
              f"시간 {[round(r[4], 2) for r in res]}  " + " ".join(p for p, v, o, *_ in res if o), flush=True)


if __name__ == "__main__":
    main()
