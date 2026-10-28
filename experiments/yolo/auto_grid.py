"""첫 사진에서 YOLO26 구역 모델로 5구역 격자(선 4개)를 자동으로 정한다 — 사용자의 "구역 격자 맞추기" 대신(2026-10-26).

앱 격자(lib/table/grid_zones.dart): 세로선 x1·x2, 가로선 y1·y2(0~1000). 가운데 = (x1..x2, y1..y2),
자리는 바람개비: 아래 = (y2..1000, x1..1000), 오른쪽 = (0..y2, x2..1000), 위 = (0..y1, 0..x2), 왼쪽 = (y1..1000, 0..x1).

정하는 법:
  1) 사진 그대로 구역 모델 → 가운데에 들어가야 할 것 = 강 4개(discard_*) + 도라 + 리치봉 상자의 합집합.
  2) 사진을 90° 씩 돌려 자리마다 그 자리가 아래에 오게 → self_hand + 손패 쪽 meld_0 = 그 자리 상자(원본 좌표로 되돌림).
  3) 선마다 "가운데 내용의 끝"과 "그 쪽 자리 상자의 끝" 사이 빈 곳의 한가운데. 자리를 못 찾으면 가운데 끝 + 3%.
검사: 자리 상자가 자기 자리 구역 안에 들어간 넓이 비율, 가운데 내용이 가운데 구역 안에 든 비율. 수동 격자와 선 차이.

python -I auto_grid.py [--set kakao|field] [--save-vis]     (field 는 매장 삼각대 사진, 결과 results/auto_grid_field/)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_yolo as ry  # noqa: E402

MANUAL = {  # 장면별로 사용자가 맞춘 격자(grid5_scenes result.json)
    "A": dict(x1=278, x2=750, y1=177, y2=793), "B": dict(x1=272, x2=735, y1=137, y2=727),
    "C": dict(x1=320, x2=760, y1=142, y2=717), "D": dict(x1=280, x2=745, y1=173, y2=713),
    "E": dict(x1=285, x2=737, y1=147, y2=718),
}
ROT = {"bottom": None, "right": cv2.ROTATE_90_CLOCKWISE, "top": cv2.ROTATE_180, "left": cv2.ROTATE_90_COUNTERCLOCKWISE}


def unrotate_box(b, seat: str, W: int, H: int):
    """seat 가 아래에 오게 돌린 사진의 상자 → 원본 좌표 상자."""
    x0, y0, x1, y1 = b
    if seat == "bottom":
        return np.array([x0, y0, x1, y1])
    if seat == "top":  # 180°
        return np.array([W - x1, H - y1, W - x0, H - y0])
    if seat == "right":  # 시계 90°: 원본 (x, y) → (H-1-y, x). 거꾸로 (x', y') → (y', H-1-x')
        return np.array([y0, H - x1, y1, H - x0])
    # left, 반시계 90°: 원본 (x, y) → (y, W-1-x). 거꾸로 (x', y') → (W-1-y', x')
    return np.array([W - y1, x0, W - y0, x1])


def union(boxes):
    boxes = [b for b in boxes if b is not None]
    if not boxes:
        return None
    a = np.array(boxes)
    return np.array([a[:, 0].min(), a[:, 1].min(), a[:, 2].max(), a[:, 3].max()])


def inter_frac(b, zone) -> float:
    """상자 b 넓이 중 zone 안 비율."""
    ix = max(0.0, min(b[2], zone[2]) - max(b[0], zone[0]))
    iy = max(0.0, min(b[3], zone[3]) - max(b[1], zone[1]))
    area = max(1e-9, (b[2] - b[0]) * (b[3] - b[1]))
    return float(ix * iy / area)


def zones(g: dict, W: int, H: int) -> dict:
    x1, x2, y1, y2 = g["x1"] * W / 1000, g["x2"] * W / 1000, g["y1"] * H / 1000, g["y2"] * H / 1000
    return {"center": (x1, y1, x2, y2), "bottom": (x1, y2, W, H), "right": (x2, 0, W, y2),
            "top": (0, 0, x2, y1), "left": (0, y1, x1, H)}


class AutoGrid:
    def __init__(self):
        from ultralytics import YOLO

        self.region = YOLO(str(ry.W / "haselab" / "regions-yolo-26n.pt"))

    def _boxes(self, img):
        r = self.region.predict(img, conf=0.25, imgsz=1280, verbose=False)[0]
        out: dict[str, list] = {}
        for c, p, b in zip(r.boxes.cls, r.boxes.conf, r.boxes.xyxy):
            out.setdefault(self.region.names[int(c)], []).append((float(p), b.numpy()))
        return out

    def run(self, img: np.ndarray):
        H, W = img.shape[:2]
        b0 = self._boxes(img)
        # 가운데 내용은 강·리치봉만 먼저(도라 상자는 손패 끝·울기에 잘못 붙는 일이 있었다, k25)
        center_items = [b for name, lst in b0.items() if name.startswith(("discard_", "riichi_")) for p, b in lst if p > 0.3]
        center = union(center_items)
        seats = {}
        for seat, rot in ROT.items():
            im = img if rot is None else cv2.rotate(img, rot)
            bx = self._boxes(im)
            hand = max(bx.get("self_hand", []), key=lambda t: t[0], default=None)
            if hand is None:
                continue
            disc = max(bx.get("discard_0", []), key=lambda t: t[0], default=None)
            lim = disc[1][3] if disc else im.shape[0] * 0.6
            hb = hand[1]
            hh = hb[3] - hb[1]
            melds, loose = [], []
            for p, b in bx.get("meld_0", []):
                if p <= 0.3 or (b[1] + b[3]) / 2 <= lim:
                    continue
                # 울기는 손패와 같은 줄 높이(모서리)에 놓인다. 손패 줄보다 패 높이 이상 위에 있으면 도라 표시패 등(k16 의 4p 4p 7m)
                (melds if b[3] >= hb[1] - 0.5 * hh else loose).append(b)
            seats[seat] = dict(box=unrotate_box(union([hb] + melds), seat, W, H), conf=hand[0],
                               loose=[unrotate_box(b, seat, W, H) for b in loose])
        # 도라·손패 밖 패 무더기는 어느 자리 상자와도 겹치지 않을 때만 가운데에
        extra = [b for p, b in b0.get("dora", []) if p > 0.3] + [b for d in seats.values() for b in d["loose"]]
        for b in extra:
            if center is not None and all(inter_frac(b, d["box"]) < 0.05 for d in seats.values()):
                center = union([center, b])
        if center is None:
            return None, center, seats
        m = 0.03
        g = {}
        # 각 선: 가운데 끝과 자리 상자 끝 사이 한가운데
        g["y2"] = (center[3] + seats["bottom"]["box"][1]) / 2 if "bottom" in seats else center[3] + m * H
        g["y1"] = (center[1] + seats["top"]["box"][3]) / 2 if "top" in seats else center[1] - m * H
        g["x1"] = (center[0] + seats["left"]["box"][2]) / 2 if "left" in seats else center[0] - m * W
        g["x2"] = (center[2] + seats["right"]["box"][0]) / 2 if "right" in seats else center[2] + m * W
        # 손패가 잘리면 안 된다: 한가운데가 자리 상자 안으로 들어가면 자리 상자 끝(패 높이의 몇 % 앞)까지 물린다
        e = 0.005
        if "bottom" in seats:
            g["y2"] = min(g["y2"], seats["bottom"]["box"][1] - e * H)
        if "top" in seats:
            g["y1"] = max(g["y1"], seats["top"]["box"][3] + e * H)
        if "left" in seats:
            g["x1"] = max(g["x1"], seats["left"]["box"][2] + e * W)
        if "right" in seats:
            g["x2"] = min(g["x2"], seats["right"]["box"][0] - e * W)
        grid = {k: int(round(v / (W if k[0] == "x" else H) * 1000)) for k, v in g.items()}
        return grid, center, seats


def check(grid: dict, center, seats, W, H) -> dict:
    z = zones(grid, W, H)
    out = {"center": round(inter_frac(center, z["center"]), 3) if center is not None else None}
    for s, d in seats.items():
        out[s] = round(inter_frac(d["box"], z[s]), 3)
    return out


def draw(img, grid, center, seats, path, manual=None):
    H, W = img.shape[:2]
    vis = img.copy()
    for g, col, th in ((manual, (0, 255, 255), 6), (grid, (255, 0, 255), 10)):
        if not g:
            continue
        for k in ("x1", "x2"):
            x = int(g[k] * W / 1000); cv2.line(vis, (x, 0), (x, H), col, th)
        for k in ("y1", "y2"):
            y = int(g[k] * H / 1000); cv2.line(vis, (0, y), (W, y), col, th)
    if center is not None:
        cv2.rectangle(vis, tuple(int(v) for v in center[:2]), tuple(int(v) for v in center[2:]), (255, 255, 255), 6)
    for s, d in seats.items():
        b = d["box"].astype(int)
        cv2.rectangle(vis, tuple(b[:2]), tuple(b[2:]), (0, 200, 0), 8)
        cv2.putText(vis, s, (b[0], b[1] - 15), cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 200, 0), 8)
    vis = cv2.resize(vis, (W * 1200 // max(W, H), H * 1200 // max(W, H)))
    cv2.imencode(".jpg", vis)[1].tofile(str(path))


# [참고·평가 밖] 10/24 매장 삼각대 사진(captures/20261024_<시각>/original.jpg). 수동 = 2026-10-27 삼각대 위치별로 맞춘 격자
# (integration_test/read_grid_timing_test.dart 의 _gridA·A2·B1·B2). 탁자가 약 25° 기운 사진이다.
_FA, _FA2 = dict(x1=300, x2=690, y1=150, y2=830), dict(x1=300, x2=720, y1=150, y2=830)
_FB1, _FB2 = dict(x1=315, x2=760, y1=200, y2=740), dict(x1=355, x2=760, y1=200, y2=740)
FIELD = {"122922": _FA, "124007": _FA2, **{p: _FA for p in ["125053", "130533", "131210", "132647", "133011", "133620",
                                                             "134323", "135148"]},
         **{p: _FB1 for p in ["135912", "140302", "140750", "140918"]}, "143443": _FB2}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save-vis", action="store_true")
    ap.add_argument("--set", default="kakao", choices=["kakao", "field"])
    a = ap.parse_args()
    field = a.set == "field"
    out_dir = ry.HERE / "results" / ("auto_grid_field" if field else "auto_grid")
    out_dir.mkdir(parents=True, exist_ok=True)
    ag = AutoGrid()
    res = {}
    jobs = ({"F": list(FIELD)} if field else {s: ps for s, ps in ry.SEAT_PHOTOS.items() if s in ry.EVAL_SCENES})
    for scene, photos in jobs.items():
        for p in photos:
            if field:
                MANUAL["F"] = FIELD[p]
                img = ry.imread(ry.EXP / "field_20261024" / "captures" / f"20261024_{p}" / "original.jpg")
            else:
                img = ry.imread(ry.EXP / "field_20261024" / "kakao_photos" / f"{p}.jpg")
            H, W = img.shape[:2]
            t0 = time.perf_counter()
            grid, center, seats = ag.run(img)
            dt = time.perf_counter() - t0
            man = MANUAL[scene]
            diff = {k: grid[k] - man[k] for k in man} if grid else None
            ca, cm = (check(grid, center, seats, W, H) if grid else None), check(man, center, seats, W, H)
            res[f"{scene}/{p}"] = dict(grid=grid, manual=man, diff=diff, auto_check=ca, manual_check=cm, sec=round(dt, 2),
                                      seats={s: [int(v) for v in d["box"]] for s, d in seats.items()},
                                      center=[int(v) for v in center] if center is not None else None)
            print(f"{scene}/{p}: 자동 {grid} 수동 {man} 차이 {diff} {dt:.1f}초\n   포함(자동) {ca}\n   포함(수동) {cm}", flush=True)
            if a.save_vis:
                draw(img, grid, center, seats, out_dir / f"{scene}_{p}.jpg", man)
    (out_dir / "auto_grid.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
