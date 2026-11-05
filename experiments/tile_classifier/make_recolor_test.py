"""색 바꾼 테스트 15장(다른 탁자 대용, metrics 표 1-69)을 만든다(2026-11-04, 노트북, API 없음).

테스트 사진(10/24 삼각대)의 테두리·펠트·뒷면을 **8회차 학습 재색칠에서 뺀 색**으로 칠한다: 테두리 검정 BGR (25,25,25), 펠트 파랑 (140,70,30),
뒷면 노랑 (40,170,240). 칠하는 방법은 det_build_fb.recolor 그대로. 테스트 사진엔 마스크 라벨이 없어 색으로 찾는다:
펠트 = det_backs.felt_mask 의 가장 큰 덩어리(볼록 껍질), 뒷면 = back_mask(loose) 중 탁자 안, 테두리 = 펠트 껍질 1.2%~14% 바깥 띠의 흰색.
테두리 위 패는 칠하지 않게 표 1-54 2종 검출기(final, 테스트 사진 학습 안 함)의 상자(+8px)를 뺀다.
  python -I -X utf8 experiments/tile_classifier/make_recolor_test.py   → experiments/field_20261024/captures_recolor/20261024_<시각>/original.jpg, 확인 그림 sheet.jpg
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import det_build_fb as fb  # noqa: E402
from det_backs import back_mask, felt_mask  # noqa: E402

FIELD = HERE.parent / "field_20261024" / "captures"
OUT = HERE.parent / "field_20261024" / "captures_recolor"
PHOTOS = ["122922", "124007", "125053", "130533", "131210", "132647", "133011", "133620", "134323", "135148", "135912", "140302", "140750", "140918", "143443"]
fb.BACKS, fb.FELTS, fb.FRAMES = [(40, 170, 240)], [(140, 70, 30)], [(25, 25, 25)]  # 시험용 색만(학습 재색칠에서 뺀 색)


def ring(shape, hull: np.ndarray, grow: float) -> np.ndarray:
    c = hull.mean(axis=0)
    m = np.zeros(shape[:2], np.uint8)
    cv2.fillPoly(m, [np.round(c + (hull - c) * (1 + grow)).astype(np.int32)], 255)
    return m


def main() -> None:
    from ultralytics import YOLO

    sys.stdout.reconfigure(encoding="utf-8")
    det = YOLO(str(HERE / "data" / "det" / "kaggle_out_fb2" / "out" / "final.pt"))
    import random

    rng = random.Random(0)
    thumbs = []
    for ph in PHOTOS:
        src = FIELD / f"20261024_{ph}" / "original.jpg"
        bgr = cv2.imread(str(src), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
        H, W = bgr.shape[:2]
        fm = felt_mask(bgr)
        n, lab, st, _ = cv2.connectedComponentsWithStats(fm)
        big = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
        pts = np.column_stack(np.nonzero(lab == big))[:, ::-1].astype(np.float32)
        hull = cv2.convexHull(pts).reshape(-1, 2)
        felt = cv2.bitwise_and(fm, ring(bgr.shape, hull, 0.0))
        table = ring(bgr.shape, hull, 0.14)
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        white = ((hsv[..., 1] < 55) & (hsv[..., 2] > 120)).astype(np.uint8) * 255
        frame = cv2.bitwise_and(white, cv2.bitwise_and(table, cv2.bitwise_not(ring(bgr.shape, hull, 0.012))))
        back = cv2.bitwise_and(back_mask(bgr, loose=True), table)
        r = det.predict(bgr, imgsz=1280, conf=0.25, verbose=False, device="cpu")[0]
        for x0, y0, x1, y1 in r.boxes.xyxy.tolist():
            frame[max(0, int(y0) - 8):int(y1) + 8, max(0, int(x0) - 8):int(x1) + 8] = 0
        out = fb.recolor(bgr, back, felt, frame, rng)
        d = OUT / f"20261024_{ph}"
        d.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(d / "original.jpg"), out, [cv2.IMWRITE_JPEG_QUALITY, 92])
        thumbs.append(cv2.resize(out, (510, 383)))
        print(ph, flush=True)
    while len(thumbs) % 4:
        thumbs.append(np.zeros_like(thumbs[0]))
    cv2.imwrite(str(OUT / "sheet.jpg"), np.vstack([np.hstack(thumbs[i:i + 4]) for i in range(0, len(thumbs), 4)]), [cv2.IMWRITE_JPEG_QUALITY, 80])


if __name__ == "__main__":
    main()
