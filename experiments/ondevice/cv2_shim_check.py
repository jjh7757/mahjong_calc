"""기기용 cv2 흉내(android/app/src/main/python/cv2)를 진짜 OpenCV 와 비교한다(PC, 무작위 입력).

    python -I -X utf8 experiments/ondevice/cv2_shim_check.py
"""
import importlib.util
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("cv2shim", ROOT / "android/app/src/main/python/cv2/__init__.py")
shim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shim)
rng = np.random.default_rng(0)
worst = {"boxPoints": 0.0, "rot": 0.0, "aff": 0.0, "inv": 0.0}
px_bad = px_all = poly_bad = poly_all = 0
for i in range(300):
    rect = ((float(rng.uniform(0, 500)), float(rng.uniform(0, 500))), (float(rng.uniform(5, 80)), float(rng.uniform(5, 80))), float(rng.uniform(-90, 90)))
    worst["boxPoints"] = max(worst["boxPoints"], float(np.abs(cv2.boxPoints(rect) - shim.boxPoints(rect)).max()))
    c, a = (float(rng.uniform(0, 200)), float(rng.uniform(0, 200))), float(rng.uniform(-45, 45))
    M1, M2 = cv2.getRotationMatrix2D(c, a, 1.0), shim.getRotationMatrix2D(c, a, 1.0)
    worst["rot"] = max(worst["rot"], float(np.abs(M1 - M2).max()))
    s = np.float32(rng.uniform(0, 300, (3, 2)))
    d = np.float32([(0, 0), (rng.uniform(50, 200), 0), (0, rng.uniform(50, 200))])
    A1, A2 = cv2.getAffineTransform(s, d), shim.getAffineTransform(s, d)
    worst["aff"] = max(worst["aff"], float(np.abs(A1 - A2).max()))
    worst["inv"] = max(worst["inv"], float(np.abs(cv2.invertAffineTransform(A1) - shim.invertAffineTransform(A1)).max()))
    img = rng.integers(0, 256, (int(rng.integers(40, 160)), int(rng.integers(40, 160)), 3), dtype=np.uint8)
    M = M1 if i % 2 else A1
    size = (int(rng.integers(30, 150)), int(rng.integers(30, 150)))
    o1 = cv2.warpAffine(img, M, size, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(114, 114, 114))
    o2 = shim.warpAffine(img, M, size, flags=shim.INTER_LINEAR, borderMode=shim.BORDER_CONSTANT, borderValue=(114, 114, 114))
    px_bad += int((o1 != o2).any(axis=2).sum())
    px_all += o1.shape[0] * o1.shape[1]
    m1 = np.zeros((300, 300), np.uint8)
    m2 = np.zeros((300, 300), np.uint8)
    pts = [np.round(cv2.boxPoints(rect)).astype(np.int32)]
    cv2.fillPoly(m1, pts, 1)
    shim.fillPoly(m2, pts, 1)
    poly_bad += int((m1 != m2).sum())
    poly_all += int(max(m1.sum(), 1))
print("최대 차이", worst)
print(f"warpAffine 다른 픽셀 {px_bad}/{px_all}")
print(f"fillPoly 다른 픽셀 {poly_bad} (채운 픽셀 {poly_all})")
sys.exit(0)
