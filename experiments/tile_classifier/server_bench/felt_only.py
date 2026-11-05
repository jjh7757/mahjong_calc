"""검출 전에 초록 펠트 밖을 지우는 시험(2026-11-05, 사용자 "초록펠트만 자르는거 간단하게 시험해봐", 노트북, API 없음).

검출기에 넣는 그림만 바꾼다: det_backs.felt_mask 의 가장 큰 덩어리를 감싸는 최소 회전 사각형(MARGIN 만큼 키움) 바깥을 회색(114, 검출기 패딩 색)으로.
분류기 크롭·틀 규칙은 원본 그림 그대로. 흰 테두리 위 울기(모서리 白 퐁 등)는 지워지므로 그 손해까지 같이 잰다.
  install(bench, lr)   — bench.Det._detect 와 app.local_read.LocalReader.detect 를 감싼다(obb_detect.install 뒤에 불러도 된다)
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from det_backs import felt_mask  # noqa: E402

MARGIN = 0.0  # 펠트 껍질을 중심에서 키우는 비율(0 = 펠트 경계 그대로)


def only_felt(rgb: np.ndarray) -> np.ndarray:
    bgr = np.ascontiguousarray(rgb[..., ::-1])
    fm = felt_mask(bgr)
    n, lab, st, _ = cv2.connectedComponentsWithStats(fm)
    if n <= 1:
        return rgb
    big = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    pts = np.column_stack(np.nonzero(lab == big))[:, ::-1].astype(np.float32)
    # 펠트는 사각형이다: 보이는 펠트 덩어리를 감싸는 최소 회전 사각형(손·패가 가려도 펠트 네 변까지). 볼록 껍질은 손에 가린 귀퉁이가 깎였다
    (cx, cy), (w, h), a = cv2.minAreaRect(pts)
    rect = cv2.boxPoints(((cx, cy), (w * (1 + MARGIN), h * (1 + MARGIN)), a))
    m = np.zeros(rgb.shape[:2], np.uint8)
    cv2.fillPoly(m, [np.round(rect).astype(np.int32)], 1)
    out = rgb.copy()
    out[m == 0] = 114
    return out


def install(bench, lr) -> None:
    det_old, lr_old = bench.Det._detect, lr.LocalReader.detect

    def mark(rgb):  # 회전 상자 어댑터가 쓰면 원본 지문을 넘긴다(분류 크롭은 원본 그림에서 찾으므로)
        if "obb_detect" in sys.modules:
            od = sys.modules["obb_detect"]
            od.FP_NEXT.append(od.fingerprint(rgb))

    def det_new(self, rgb):
        mark(rgb)
        return det_old(self, only_felt(rgb))

    def lr_new(self, rgb, low=True):
        mark(rgb)
        return lr_old(self, only_felt(rgb), low)

    bench.Det._detect = det_new
    lr.LocalReader.detect = lr_new
