"""갤러리 B·C·D(개발 세트) 사진을 합성으로 기울인다 — 비스듬히 거치한 카메라 흉내(기울기 보정 개발용, 2026-10-27).

변형 셋(사진마다): 사진 가운데를 축으로 돌리고(탁자 기울기) 한쪽을 좁혀(원근) 줄인 뒤 회색 바닥 위에 놓는다.
  a: +25° 회전 + 위쪽 좁힘 12%   (매장 삼각대 사진 비슷 — 오른쪽 뒤 모서리에서 내려다봄)
  b: −18° 회전 + 왼쪽 좁힘 10%
  c: +10° 회전 + 아래쪽 좁힘 15%
매장 사진(테스트 세트)은 보지 않고 정한 값이다. 출력: experiments/field_20261024/kakao_photos/tilted/<사진>_<변형>.jpg

  python -I experiments/rectify/make_tilted.py
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "field_20261024" / "kakao_photos"
OUT = SRC / "tilted"
PHOTOS = ["k25", "k28", "k15", "k26", "k12", "k16"]  # B·C·D
VARIANTS = {"a": (25, "top", 0.12), "b": (-18, "left", 0.10), "c": (10, "bottom", 0.15)}
SHRINK = 0.78  # 돌려도 탁자가 사진 안에 남게


def warp(img: np.ndarray, deg: float, side: str, pinch: float) -> np.ndarray:
    h, w = img.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = src.copy()
    # 원근: 한 변을 가운데 쪽으로 좁힘
    dx, dy = pinch * w / 2, pinch * h / 2
    if side == "top":
        dst[0, 0] += dx; dst[1, 0] -= dx
    elif side == "bottom":
        dst[3, 0] += dx; dst[2, 0] -= dx
    elif side == "left":
        dst[0, 1] += dy; dst[3, 1] -= dy
    # 줄이고 돌리기(사진 가운데 기준)
    c = np.float32([w / 2, h / 2])
    th = np.deg2rad(deg)
    R = np.float32([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    dst = (dst - c) * SHRINK @ R.T + c
    H = cv2.getPerspectiveTransform(src, dst.astype(np.float32))
    return cv2.warpPerspective(img, H, (w, h), flags=cv2.INTER_LINEAR, borderValue=(90, 90, 90))


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for p in PHOTOS:
        img = cv2.imdecode(np.fromfile(str(SRC / f"{p}.jpg"), np.uint8), cv2.IMREAD_COLOR)
        for k, (deg, side, pinch) in VARIANTS.items():
            out = warp(img, deg, side, pinch)
            cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tofile(str(OUT / f"{p}_{k}.jpg"))
            print(OUT / f"{p}_{k}.jpg", out.shape)


if __name__ == "__main__":
    main()
