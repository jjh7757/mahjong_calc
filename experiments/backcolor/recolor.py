"""뒷면 색 과적합 확인용 합성 사진(2026-10-27, 사용자 요청): B·C·D 원본 6장의 연보라 뒷면 픽셀만 다른 색으로 바꾼다.

연보라 뒷면 = HSV 색상 112~165(OpenCV 0~180), 채도 26~139, 밝기 96 이상(가운데 남색 기기·파란 리치봉은 빠지게).
색 바꾸기: 밝기 비율(그림자·옆면 음영)은 그대로 두고 색상·채도를 목표색으로. 검정은 밝기를 낮춘다.
한계: 진짜 다른 세트는 앞면 색(상아색)·뒷면 질감·두께도 다르다 — 여기서는 "뒷면 색" 가정만 시험한다.

  python -I experiments/backcolor/recolor.py      → experiments/backcolor/photos/<색>/<사진>.jpg (+ mask 확인 그림)
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

EXP = Path(__file__).resolve().parent.parent
SRC = EXP / "field_20261024" / "kakao_photos"
OUT = Path(__file__).resolve().parent / "photos"
PHOTOS = ["k25", "k28", "k15", "k26", "k12", "k16"]  # B·C·D
# (색상, 채도, 밝기 배율) — OpenCV HSV
COLORS = {"blue": (106, 170, 0.85), "green": (62, 150, 0.75), "yellow": (27, 160, 1.0),
          "orange": (12, 190, 0.95), "black": (110, 30, 0.22)}


def back_mask(im: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    h, s, v = [hsv[..., i].astype(int) for i in range(3)]
    m = ((h >= 112) & (h <= 165) & (s > 25) & (s < 140) & (v >= 96)).astype(np.uint8)
    return cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))


def recolor(im: np.ndarray, m: np.ndarray, hue: int, sat: int, vk: float) -> np.ndarray:
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV).astype(np.float32)
    sel = m > 0
    # 원래 채도의 상대 변화(가장자리 흐림)를 살려 목표 채도로
    s0 = hsv[..., 1][sel]
    hsv[..., 0][sel] = hue
    hsv[..., 1][sel] = np.clip(s0 / max(1.0, float(np.median(s0))) * sat, 0, 255)
    hsv[..., 2][sel] = np.clip(hsv[..., 2][sel] * vk, 0, 255)
    out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    # 경계를 부드럽게: 마스크를 조금 흐려 섞는다
    a = cv2.GaussianBlur(m.astype(np.float32), (5, 5), 0)[..., None]
    return (out * a + im * (1 - a)).astype(np.uint8)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    checks = []
    for p in PHOTOS:
        im = cv2.imread(str(SRC / f"{p}.jpg"))
        m = back_mask(im)
        (OUT / "original").mkdir(exist_ok=True)
        cv2.imwrite(str(OUT / "original" / f"{p}.jpg"), im, [cv2.IMWRITE_JPEG_QUALITY, 95])
        row = [cv2.resize(im, (800, 600))]
        for name, (hue, sat, vk) in COLORS.items():
            r = recolor(im, m, hue, sat, vk)
            (OUT / name).mkdir(exist_ok=True)
            cv2.imwrite(str(OUT / name / f"{p}.jpg"), r, [cv2.IMWRITE_JPEG_QUALITY, 95])
            row.append(cv2.resize(r, (800, 600)))
        checks.append(np.hstack(row[:3]))
        checks.append(np.hstack(row[3:]))
        print(p, "뒷면 픽셀", f"{m.mean():.3%}")
    cv2.imwrite(str(OUT / "check.jpg"), np.vstack(checks[:4]), [cv2.IMWRITE_JPEG_QUALITY, 80])


if __name__ == "__main__":
    main()
