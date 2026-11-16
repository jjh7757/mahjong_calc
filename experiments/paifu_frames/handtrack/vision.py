"""검출·분류(운영 모델, CPU ONNX) — 서버 저장소 mahjong-recognizer 의 app/local_read.LocalReader 를 불러 쓴다(고치지 않음).

프레임을 먼저 화료자 시점으로 돌린 뒤(htcommon.band_crop 과 같은 회전) 회전 상자 검출기(tile-obb-r8, _seat_raw 앞면)로 패를 찾고,
상자를 세워 자른 크롭을 긴 변 96 미만이면 96 으로 키워(서버 read_small 과 같은 식) 분류한다. 방향 후보는 v1114rec_draft.read_faces 와 같게
상자가 세로로 길면 0°·180°, 가로로 길면 90°·270°, 그 밖은 네 방향 중 확신 최대.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

REC = Path(r"C:\Users\jjh7757\dev\mahjong-recognizer")
sys.path.insert(0, str(REC))
from app import local_read as lr  # noqa: E402
from app import obb  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402

_READER = None


def reader() -> lr.LocalReader:
    global _READER
    if _READER is None:
        _READER = lr.LocalReader(threads=4)
        _READER._sessions()
    return _READER


def view_full(rgb: np.ndarray, side: str) -> np.ndarray:
    return np.ascontiguousarray(np.rot90(rgb, hc.ROT[side] // 90))


def view_box(box: list, side: str, W: int = 1496, H: int = 1496) -> list:
    """원본 좌표 직사각형 [x0,y0,x1,y1] → 화료자 시점 전체 그림 좌표 직사각형."""
    pts = [hc.to_view_xy((x, y), [0, 0, W, H], side) for x in (box[0], box[2]) for y in (box[1], box[3])]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [min(xs), min(ys), max(xs), max(ys)]


def detect(v: np.ndarray) -> list[dict]:
    """화료자 시점 그림 v 에서 앞면 패. [{box(x,y,w,h), rect, cx, cy, w, h(세운 기준이 아니라 그림 축 기준 폭·높이), score}]"""
    rd = reader()
    res, backs, pairs, scores = rd._seat_raw(v)
    out = []
    for b, rc in res:
        (cx, cy), (rw, rh), a = rc
        out.append({"box": [int(t) for t in b], "rect": ((float(cx), float(cy)), (float(rw), float(rh)), float(a)),
                    "cx": float(b[0] + b[2] / 2), "cy": float(b[1] + b[3] / 2), "w": int(b[2]), "h": int(b[3])})
    return out


def classify(v: np.ndarray, faces: list[dict]) -> None:
    crops, owner = [], []
    for i, e in enumerate(faces):
        im = obb.upright(v, e["rect"], lr.PAD)
        if max(im.size) < lr.SMALL_TILE:
            s = lr.SMALL_TILE / max(im.size)
            im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.BICUBIC)
        b = e["box"]
        ts = (0, 2) if b[3] > 1.15 * b[2] else (1, 3) if b[2] > 1.15 * b[3] else (0, 1, 2, 3)
        for k in ts:
            crops.append(im.rotate(90 * k, expand=True))
            owner.append((i, k))
    best: dict = {}
    for s in range(0, len(crops), 64):
        p = reader().probs(crops[s:s + 64])
        for j, row in enumerate(p):
            i, k = owner[s + j]
            if i not in best or row.max() > best[i][0].max():
                best[i] = (row, k)
    for i, (row, k) in best.items():
        t, c, t2, c2 = lr.top2(row)
        faces[i].update(tile=t, conf=c, alt=t2, conf2=c2, turn=k * 90, sideways=bool(faces[i]["w"] > 1.15 * faces[i]["h"]))


def read_region(v: np.ndarray, region_view: list, faces: list[dict] | None = None) -> list[dict]:
    """region_view = 화료자 시점 좌표 [x0,y0,x1,y1] 안에 중심이 있는 앞면 패를 읽는다."""
    if faces is None:
        faces = detect(v)
    x0, y0, x1, y1 = region_view
    sel = [dict(e) for e in faces if x0 <= e["cx"] <= x1 and y0 <= e["cy"] <= y1]
    if sel:
        classify(v, sel)
    return sel


def river_order(tiles: list[dict]) -> list[dict]:
    """화료자 시점 강: 위(기기 쪽)부터 줄, 줄 안에서는 왼쪽부터. 줄은 세로 중심이 패 높이 0.6 안이면 같은 줄."""
    if not tiles:
        return []
    th = float(np.median([min(t["w"], t["h"]) for t in tiles])) * 1.35  # 세운 패 높이 짐작(짧은 변 × 1.35)
    rows: list[list[dict]] = []
    for t in sorted(tiles, key=lambda e: e["cy"]):
        if rows and abs(t["cy"] - np.mean([u["cy"] for u in rows[-1]])) < 0.6 * th:
            rows[-1].append(t)
        else:
            rows.append([t])
    out = []
    for r, row in enumerate(rows):
        for c, t in enumerate(sorted(row, key=lambda e: e["cx"])):
            t["row"], t["col"] = r + 1, c + 1
            out.append(t)
    return out


def brief(t: dict) -> dict:
    d = {"tile": t["tile"], "conf": t["conf"], "cx": round(t["cx"], 1), "cy": round(t["cy"], 1), "w": t["w"], "h": t["h"]}
    if t.get("conf", 1) < 0.9:
        d["alt"], d["conf2"] = t["alt"], t["conf2"]
    if t.get("sideways"):
        d["sideways"] = True
    if "row" in t:
        d["row"], d["col"] = t["row"], t["col"]
    return d
