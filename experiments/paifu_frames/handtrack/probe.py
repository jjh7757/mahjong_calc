"""설정 도움: 넓은 탐색 영역(config 의 search)에서 1초마다 '패 화소'(흰·분홍·보라, 피부 아님) 범위를 대국자 시점 좌표와 원본 좌표로 찍는다.
손패 띠(band)를 정할 때 줄이 판 동안 어디까지 움직이는지 보려는 것. 결과 _work/probe_<판>.json + 표준 출력.

  python -X utf8 probe.py <판 id> [간격 초=1]
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402


def tile_mask(rgb: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0].astype(int), hsv[..., 1].astype(int), hsv[..., 2].astype(int)
    white = (s < 45) & (v > 170)
    back = ((h >= 115) | (h <= 2)) & (s >= 35) & (v > 120)  # 분홍(170 안팎)·보라(130 안팎)
    return white | back


def skin_mask(rgb: np.ndarray) -> np.ndarray:
    """tile_classifier/det_backs.skin_mask 와 같은 기준(OpenCV HSV h 3~32, s>40, v>70), 팽창 없음."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    return (h >= 3) & (h < 32) & (s > 40) & (v > 70)


def main():
    gid = sys.argv[1]
    step = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    cf = hc.config(gid)
    side, srch = cf["side"], cf["search"]
    t0, t1 = hc.to_ms(cf["t_ready"]) - 20000, hc.to_ms(cf["t_reveal"]) + 5000
    rows = []
    t = t0
    while t <= t1:
        ms = hc.nearest(t)
        v = hc.band_crop(hc.load(ms), srch, side)
        m = tile_mask(v) & ~skin_mask(v)
        sk = skin_mask(v).mean()
        cols = np.flatnonzero(m.sum(0) >= 8)
        rws = np.flatnonzero(m.sum(1) >= 30)
        if len(cols) and len(rws):
            rows.append({"t": hc.hms(ms), "ms": ms, "x": [int(cols[0]), int(cols[-1])], "y": [int(rws[0]), int(rws[-1])], "skin": round(float(sk), 4)})
            print(f"{hc.hms(ms)} 띠 x {cols[0]:4d}-{cols[-1]:4d} y {rws[0]:4d}-{rws[-1]:4d} 피부 {sk:.3f}")
        t += int(step * 1000)
    hc.jsave(hc.WORK / f"probe_{gid}.json", rows)


if __name__ == "__main__":
    main()
