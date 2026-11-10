"""day1022 보조: 손패 사진 3장에서 손패 줄(가장 많이 모인 높이 ±0.6패)만 남겨 다시 채점.

kokushi.jpg 는 위쪽에 다른 패 9장이 같이 찍혀 있어 "남는 패" 가 손패 밖 진짜 패였다.
python -I day1022_rows.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import day1022 as d  # noqa: E402
import run_yolo as ry  # noqa: E402


def hand_row(pred, img_h):
    if not pred:
        return pred
    ys = np.array([p[2][1] for p in pred])
    band = img_h * 0.06
    best = max(ys, key=lambda y: int((np.abs(ys - y) < band).sum()))
    return [p for p in pred if abs(p[2][1] - best) < band]


def main():
    sets = d.load_labeled()
    for m in (ry.Nikmomo("s"), ry.Nikmomo("m")):
        for key, path, truth in sets["hand"]:
            img = cv2.imread(str(path))
            pred, _ = m.predict(img)
            row = ry.order(hand_row(pred, img.shape[0]), horizontal=True)
            names = [p[0] for p in row]
            hit, _, exact = ry.score(names, truth)
            print(f"{m.name} {key}: 줄 {len(names)}장 / 정답 {len(truth)} 맞음 {hit} 통째 {exact} | {' '.join(names)} | 정답 {' '.join(truth)}")


if __name__ == "__main__":
    main()
