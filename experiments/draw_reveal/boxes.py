"""유국 공개 합성 1단계: 평가 장면 40장(seat_grow.eval_scenes, scenes.json)의 네 자리 손패 상자를 픽셀로 잡는다(API 없음).

- 펠트 = 초록(g > r+20, g > b, 앱 fixed_layout 과 같은 식) 가장 큰 덩어리의 볼록 껍질. 손패는 펠트 위라 껍질 안.
- 패 화소 = 껍질 안 & 초록 아님. 자리 손패 칸(grid_zones.handCell) 안에서 줄 방향으로 이어 붙여 가장 큰 덩어리의 상자.
- 결과 boxes.json(긴 변 1024 축소본 좌표가 아니라 원본 픽셀), 눈 검수용 boxes_sheet.jpg.
  python -I -X utf8 experiments/draw_reveal/boxes.py
"""
import json
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
SIDES = ["bottom", "right", "top", "left"]


def hand_cell(g, side):  # NormBox(ymin, xmin, ymax, xmax), 0~1000
    return {"bottom": (g["y2"], g["x1"], 1000, g["x2"]), "right": (g["y1"], g["x2"], g["y2"], 1000),
            "top": (0, g["x1"], g["y1"], g["x2"]), "left": (g["y1"], 0, g["y2"], g["x1"])}[side]


def felt_hull(im):
    b, g, r = [im[..., i].astype(np.int16) for i in range(3)]
    green = ((g > r + 20) & (g > b)).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(green, 8)
    k = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    pts = cv2.findNonZero((lab == k).astype(np.uint8))
    hull = np.zeros_like(green)
    cv2.fillConvexPoly(hull, cv2.convexHull(pts), 1)
    return green.astype(bool), hull.astype(bool)


def detect(path, grid, s=1024):
    full = cv2.imread(str(path))
    H, W = full.shape[:2]
    f = s / max(H, W)
    im = cv2.resize(full, (round(W * f), round(H * f)), interpolation=cv2.INTER_AREA)
    h, w = im.shape[:2]
    green, hull = felt_hull(im)
    hull = cv2.erode(hull.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)  # 흰 테두리 경계 한 줄 빼기
    tile = hull & ~green
    out = {}
    for side in SIDES:
        y0, x0, y1, x1 = hand_cell(grid, side)
        Y0, X0, Y1, X1 = int(y0 * h / 1000), int(x0 * w / 1000), int(y1 * h / 1000), int(x1 * w / 1000)
        m = np.zeros((h, w), np.uint8)
        m[Y0:Y1, X0:X1] = tile[Y0:Y1, X0:X1]
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        horiz = side in ("bottom", "top")
        k = np.ones((3, 25), np.uint8) if horiz else np.ones((25, 3), np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k)
        n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
        if n < 2:
            out[side] = None
            continue
        i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
        x, y, bw, bh = st[i, :4]
        out[side] = [int(x / f), int(y / f), int((x + bw) / f), int((y + bh) / f)]  # 원본 픽셀 x0,y0,x1,y1
    return out, im, f


def main():
    scenes = json.loads((HERE / "scenes.json").read_text(encoding="utf-8"))
    res, thumbs = {}, []
    for sc in scenes:
        boxes, im, f = detect(sc["path"], sc["grid"])
        res[sc["name"]] = boxes
        t = im.copy()
        for side, b in boxes.items():
            if b:
                col = (0, 0, 255) if side == sc["side"] else (255, 255, 0)
                cv2.rectangle(t, (int(b[0] * f), int(b[1] * f)), (int(b[2] * f), int(b[3] * f)), col, 3)
        cv2.putText(t, sc["name"], (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        thumbs.append(cv2.resize(t, (480, 360)))
    (HERE / "boxes.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    cols = 5
    rows = [np.hstack(thumbs[i:i + cols] + [np.zeros_like(thumbs[0])] * (cols - len(thumbs[i:i + cols]))) for i in range(0, len(thumbs), cols)]
    cv2.imwrite(str(HERE / "boxes_sheet.jpg"), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 80])
    print(len(res), "장", sum(b is None for v in res.values() for b in v.values()), "자리 못 잡음")


if __name__ == "__main__":
    main()
