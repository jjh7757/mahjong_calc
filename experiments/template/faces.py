"""패 크롭(격자로 대충 자른 것)에서 가운데 패의 흰 면만 잘라 똑바로 세운다. 순수 opencv(학습 없음).

크롭 모음: tile_tool 의 tiles_raw(손패) · river_ok.txt(강) · more_ok.txt(매장 촬영 Q), speed/tileset2(집 패 정면).
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

EXP = Path(__file__).resolve().parent.parent
TOOL = EXP / "tile_tool"
SET2 = EXP / "speed" / "tileset2" / "tiles"


def read(path: Path) -> np.ndarray:
    # 한글 경로 대비 imdecode
    return cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)


def store_crops() -> list[dict]:
    """매장 패 크롭: {path, code, group}. group 은 장면 글자(A~E) 또는 Q(매장 촬영)."""
    rows = []
    for p in sorted((TOOL / "tiles_raw").glob("*.png")):
        rows.append({"path": p, "code": p.stem.split("_")[-1], "src": "hand"})
    for name, folder, src in (("river_ok.txt", "river_raw", "river"), ("more_ok.txt", "more_raw", "more")):
        for line in (TOOL / name).read_text(encoding="utf-8").split():
            f, code = line.split(":")
            rows.append({"path": TOOL / folder / f, "code": code, "src": src})
    for r in rows:
        r["group"] = r["path"].name[0]
        r["photo"] = "_".join(r["path"].name.split("_")[:2])
    return rows


def set2_crops() -> list[dict]:
    return [{"path": p, "code": p.stem.split("_")[0], "group": "S", "src": "set2", "photo": "set2"}
            for p in sorted(SET2.glob("*.png")) if not p.stem.startswith("fl")]


def white_mask(im: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    s, v = hsv[..., 1], hsv[..., 2]
    # 상대 밝기: 사진마다 조명이 달라 크롭 안 밝은 쪽 기준
    vt = max(110, int(np.percentile(v, 90)) - 60)
    return ((s < 55) & (v > vt)).astype(np.uint8)


def face(im: np.ndarray, out=(48, 64)) -> tuple[np.ndarray, dict]:
    """가운데 패 흰 면(무늬 구멍 메움)을 찾아 기울기를 바로잡고 out 크기로. 못 찾으면 크롭 전체."""
    h, w = im.shape[:2]
    m = white_mask(im)
    # 이웃 패와 붙은 흰 면을 떼려고 깎는다(패 사이 회색 틈)
    k = max(1, round(min(h, w) * 0.04))
    er = cv2.erode(m, np.ones((k, k), np.uint8))
    n, lab, stats, cent = cv2.connectedComponentsWithStats(er, 8)
    best, score = None, -1.0
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        if a < 0.04 * h * w:
            continue
        cx, cy = cent[i]
        d = ((cx - w / 2) / w) ** 2 + ((cy - h / 2) / h) ** 2
        sc = a / (h * w) - 2.0 * d  # 크고 가운데
        if sc > score:
            best, score = i, sc
    info = {"found": best is not None}
    if best is None:
        return cv2.resize(im, out, interpolation=cv2.INTER_AREA), info
    comp = (lab == best).astype(np.uint8)
    comp = cv2.dilate(comp, np.ones((k, k), np.uint8)) & m
    # 무늬 구멍 메우기: 바깥 윤곽 채우기
    cs, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = max(cs, key=cv2.contourArea)
    (cx, cy), (rw, rh), ang = cv2.minAreaRect(c)
    # 세로로 긴 쪽이 높이가 되게
    if rw > rh:
        rw, rh, ang = rh, rw, ang + 90
    if ang > 45:
        ang -= 90
    if ang < -45:
        ang += 90
    info.update(angle=round(ang, 1), aspect=round(rw / max(rh, 1), 2))
    M = cv2.getRotationMatrix2D((cx, cy), ang, 1.0)
    rot = cv2.warpAffine(im, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    x0, y0 = int(round(cx - rw / 2)), int(round(cy - rh / 2))
    x1, y1 = int(round(cx + rw / 2)), int(round(cy + rh / 2))
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    if x1 - x0 < 5 or y1 - y0 < 5:
        info["found"] = False
        return cv2.resize(im, out, interpolation=cv2.INTER_AREA), info
    f = rot[y0:y1, x0:x1]
    return cv2.resize(f, out, interpolation=cv2.INTER_AREA), info


def sheet(rows: list[dict], faces: list[np.ndarray], path: Path, cols: int = 20) -> None:
    fh, fw = faces[0].shape[:2]
    lab = 14
    n = len(faces)
    img = np.full((((n + cols - 1) // cols) * (fh + lab), cols * fw, 3), 255, np.uint8)
    for i, (r, f) in enumerate(zip(rows, faces)):
        y, x = (i // cols) * (fh + lab), (i % cols) * fw
        img[y:y + fh, x:x + fw] = f
        cv2.putText(img, f"{r['code']}{r['group']}", (x + 2, y + fh + 11), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 200), 1)
    cv2.imencode(".png", img)[1].tofile(str(path))


if __name__ == "__main__":
    rows = store_crops() + set2_crops()
    fs, bad = [], 0
    for r in rows:
        f, info = face(read(r["path"]))
        fs.append(f)
        bad += not info["found"]
    print(len(rows), "크롭, 흰 면 못 찾음", bad)
    sheet(rows, fs, Path(__file__).parent / "faces_sheet.png", cols=24)
