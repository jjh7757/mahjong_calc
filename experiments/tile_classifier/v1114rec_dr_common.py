"""녹화 프레임(rec1496) 검출·역할 세트 3단계 공용(2026-11-15). v1114rec_dr_{final,final_pair,pairfix,det,role,detinput,check,audit}.py 가 불러 쓴다.

좌표는 모두 녹화 원래 픽셀(1496). 기존 세트(data/v1114, 2992 좌표)를 옮길 때는 HALF(0.5)를 곱한다.
  final_all()  → [그림 dict] mid·new(dr/final) + pair(dr/final_pair), 그림마다 part 칸. 순서 = part(pair, mid, new) · 판 · 시각.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
R = HERE / "data" / "v1114rec"
V = HERE / "data" / "v1114"
DR = R / "dr"
Q = "rec1496"
HALF = 0.5
OWNED = ("hand", "loose", "meld", "river")
PARTS = ("pair", "mid", "new")


def jload(p: Path):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def jsave(p: Path, obj, indent=1):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=indent), encoding="utf-8")


def rect_pts(rc) -> list:
    p = cv2.boxPoints(((rc[0][0], rc[0][1]), (rc[1][0], rc[1][1]), rc[2]))
    return [[round(float(a), 1), round(float(b), 1)] for a, b in p]


def box_of(pts, W, H) -> list:
    p = np.array(pts, float)
    x_, y_ = max(0.0, float(p[:, 0].min())), max(0.0, float(p[:, 1].min()))
    return [int(x_), int(y_), int(min(W, p[:, 0].max()) - x_), int(min(H, p[:, 1].max()) - y_)]


def half_box_rec(b: dict, W=1496, H=1496) -> dict:
    """2992 최종 상자 → 1496: rect 중심·크기 ×0.5(각도 그대로), pts ×0.5, box 는 pts 에서 다시."""
    rc = b["rect"]
    rect = [[round(rc[0][0] * HALF, 2), round(rc[0][1] * HALF, 2)], [round(rc[1][0] * HALF, 2), round(rc[1][1] * HALF, 2)], rc[2]]
    pts = [[round(x * HALF, 2), round(y * HALF, 2)] for x, y in b["pts"]]
    return {"rect": rect, "pts": pts, "box": box_of(pts, W, H)}


def final_all(parts=PARTS) -> list[dict]:
    out = []
    for part in parts:
        d = DR / ("final_pair" if part == "pair" else "final")
        for p in sorted(d.glob("[nr]*.json")):
            f = jload(p)
            for im in f["images"]:
                if im["part"] == part:
                    out.append(im)
    return out


def inter(a, b) -> float:
    v, _ = cv2.intersectConvexConvex(np.array(a, np.float32), np.array(b, np.float32))
    return float(v)


def piou(a, b) -> float:
    a, b = np.array(a, np.float32), np.array(b, np.float32)
    i, _ = cv2.intersectConvexConvex(a, b)
    u = cv2.contourArea(a) + cv2.contourArea(b) - i
    return float(i / u) if u > 0 else 0.0
