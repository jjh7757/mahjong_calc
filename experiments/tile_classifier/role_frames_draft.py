"""판 중 프레임 역할·주인 평가 세트 — 초안 라벨(2026-11-11, `docs/role_owner_plan_1111.md` 3-1·3-3절, 5절 1단계).

입력: `data/role/frames/pick.json`(role_frames_pick.py 가 만듦), `data/role/frames/images/<이름>.jpg`.
출력: `labels_dev.draft.json`·`labels_test.draft.json`·`check/<이름>.jpg`·`draft_uncertain.json`·`draft_stats.json`.

상자: 운영 자리 판독 검출기(`LocalReader._seat_raw`, tile-obb-r8) — ① 프레임 전체(1020 → 1280 레터박스) ② 프레임을 네 조각(겹침 60px)으로
   잘라 2배로 키운 것. ① 을 기본으로 두고 ② 에서만 나온 앞면(①의 어느 상자와도 IoU < 0.3, 중심이 안 들어감)을 더한다(둘 다 src=det, det=full|up).
   뒷면도 같은 방식. 흰 비율(HSV S<50·V>140) 0.25 미만 또는 진한 흰색(S<25·V>170) 0.2 미만(연보라·분홍 뒷면) 앞면은 헛검출로 지운다(자동). 그 뒤 사람이 본 고침(FIXES)을 건다.
역할·주인(판 중 기준, 역할 모델은 쓰지 않음 — 기하 규칙 + 눈):
   - wall(먼저): 뒷면 상자 2개 이상이 1.25 × 패 긴 변 안에 있는 앞면.
   - river: 기기 변 바깥 강 띠(paifu_frames.assign 꼴)에 든 앞면. 주인 = 그 변의 자리(띠가 겹치는 모서리는 패 방향이 맞는 자리).
   - 그 밖 앞면은 이웃끼리 묶음(중심 거리 < 1.5 × 패 긴 변):
     · 뒷면(중심 거리 < 1.6 × 패 긴 변)에 붙은 1~2장 = wall(주인 없음)
     · 2장 이상 묶음이 기기에서 떨어진 모서리 쪽(가로·세로 모두 1.6 hd 밖) = meld(주인 = 그 모서리를 오른손 쪽에 둔 사람: 오른쪽 아래 = bottom, 오른쪽 위 = right, 왼쪽 위 = top, 왼쪽 아래 = left)
     · 그 밖의 5장 이상 = hand(주인 = 가까운 변 자리)
     · 나머지 = other(주인 없음)
   규칙 답은 확인 그림을 사람이 모두 보고 FIXES 로 고친다(다시 돌려도 같은 결과).

  python -I -X utf8 experiments/tile_classifier/role_frames_draft.py [--redetect] [--only 이름,...]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "experiments/tile_classifier/data/role/frames"
REC = Path(r"C:\Users\jjh7757\dev\mahjong-recognizer")
SIDES = ("bottom", "right", "top", "left")
SEAT = {"b": "bottom", "r": "right", "t": "top", "l": "left", "-": None}
COL = {"bottom": (40, 110, 255), "right": (0, 200, 60), "top": (240, 30, 30), "left": (255, 220, 0), None: (150, 150, 150)}


# ---------------------------------------------------------------- 검출(캐시)
def iou(a, b) -> float:
    ix = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    i = ix * iy
    return i / (a[2] * a[3] + b[2] * b[3] - i + 1e-9)


def inside(p, b) -> bool:
    return b[0] <= p[0] <= b[0] + b[2] and b[1] <= p[1] <= b[1] + b[3]


def cen(b):
    return (b[0] + b[2] / 2, b[1] + b[3] / 2)


def detect(rd, rgb: np.ndarray) -> dict:
    H, W = rgb.shape[:2]
    f1, b1, _, _ = rd._seat_raw(rgb)
    faces = [{"box": [round(v, 1) for v in b], "det": "full"} for b, _ in f1]
    backs = [{"box": [round(v, 1) for v in b], "det": "full"} for b, _ in b1]
    s, ov = 2, 60
    up_f, up_b = [], []
    for x0, y0, x1, y1 in [(0, 0, W // 2 + ov, H // 2 + ov), (W // 2 - ov, 0, W, H // 2 + ov), (0, H // 2 - ov, W // 2 + ov, H), (W // 2 - ov, H // 2 - ov, W, H)]:
        c = Image.fromarray(rgb[y0:y1, x0:x1]).resize(((x1 - x0) * s, (y1 - y0) * s), Image.LANCZOS)
        f, b, _, _ = rd._seat_raw(np.asarray(c))
        cw, chh = (x1 - x0) * s, (y1 - y0) * s
        for (bx, by, bw, bh), _ in f:
            if bx <= 2 or by <= 2 or bx + bw >= cw - 2 or by + bh >= chh - 2:  # 조각 끝에 잘린 것
                continue
            up_f.append([round(bx / s + x0, 1), round(by / s + y0, 1), round(bw / s, 1), round(bh / s, 1)])
        for (bx, by, bw, bh), _ in b:
            if bx <= 2 or by <= 2 or bx + bw >= cw - 2 or by + bh >= chh - 2:
                continue
            up_b.append([round(bx / s + x0, 1), round(by / s + y0, 1), round(bw / s, 1), round(bh / s, 1)])

    def merge(base: list, extra: list) -> list:
        out = list(base)
        for e in extra:
            if any(iou(e, o["box"]) >= 0.3 or inside(cen(e), o["box"]) or inside(cen(o["box"]), e) for o in out):
                continue
            out.append({"box": e, "det": "up"})
        return out

    faces = merge(faces, up_f)
    # 뒷면은 앞면과 겹치면 안 더함
    backs = merge(backs + [{"box": f["box"], "det": "_face"} for f in faces], up_b)
    backs = [b for b in backs if b["det"] != "_face"]
    return {"faces": faces, "backs": backs, "n_full": len(f1), "n_full_backs": len(b1)}


# ---------------------------------------------------------------- 기하 규칙
def to_side(side: str, dx: float, dy: float) -> tuple[float, float]:
    return {"bottom": (dx, dy), "right": (-dy, dx), "top": (-dx, -dy), "left": (dy, -dx)}[side]


def dark_device(rgb: np.ndarray, cx: float, cy: float, r: int = 150) -> tuple[float, float, float]:
    H, W = rgb.shape[:2]
    x0, y0, x1, y1 = int(max(0, cx - r)), int(max(0, cy - r)), int(min(W, cx + r)), int(min(H, cy + r))
    a = rgb[y0:y1, x0:x1].astype(int)
    dark = (a.max(2) < 90) & ~((a[..., 1] > a[..., 0] + 25) & (a[..., 1] > a[..., 2]))
    ys, xs = np.nonzero(dark)
    if len(xs) < 500:
        return cx, cy, 70.0
    lx, hx = np.percentile(xs, [3, 97])
    ly, hy = np.percentile(ys, [3, 97])
    return x0 + (lx + hx) / 2, y0 + (ly + hy) / 2, ((hx - lx) + (hy - ly)) / 4


def device(grid: dict, rgb: np.ndarray) -> tuple[float, float, float, str]:
    """기기 중심·반 크기. grid.sticks 를 기본으로, 어두운 사각형 중심이 25px 넘게 어긋나면(카메라가 움직임) 어두운 사각형."""
    H, W = rgb.shape[:2]
    if "sticks" in grid:
        y0, x0, y1, x1 = grid["sticks"]
        cx, cy = (x0 + x1) / 2000 * W, (y0 + y1) / 2000 * H
        hd = ((x1 - x0) / 1000 * W + (y1 - y0) / 1000 * H) / 4
        dx, dy, dh = dark_device(rgb, cx, cy)
        if abs(dx - cx) > 25 or abs(dy - cy) > 25:
            return dx, dy, dh, "dark"
        return cx, cy, hd, "sticks"
    cx, cy, hd = dark_device(rgb, (grid["x1"] + grid["x2"]) / 2000 * W, (grid["y1"] + grid["y2"]) / 2000 * H)
    return cx, cy, hd, "dark"


def upright(box) -> bool:
    return box[3] >= box[2]


def river_side(cx, cy, hd, box) -> str | None:
    bx, by = box[0] + box[2] / 2 - cx, box[1] + box[3] / 2 - cy
    cands = []
    for s in SIDES:
        u, v = to_side(s, bx, by)
        if v < hd * 0.6 or v > hd * 2.9 or u < -hd * 1.45 or u > hd * 1.9:
            continue
        over = max(0.0, abs(u) - hd) if u < 0 else max(0.0, u - hd * 1.05)
        fit = upright(box) == (s in ("bottom", "top"))
        cands.append((not fit, over, v, s))
    if not cands:
        return None
    cands.sort()
    return cands[0][3]


def groups(boxes: list, link: float) -> list[list[int]]:
    n = len(boxes)
    par = list(range(n))

    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            a, b = cen(boxes[i]), cen(boxes[j])
            if ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 < link:
                par[find(i)] = find(j)
    out: dict = {}
    for i in range(n):
        out.setdefault(find(i), []).append(i)
    return list(out.values())


def near_side(cx, cy, box) -> str:
    bx, by = box[0] + box[2] / 2 - cx, box[1] + box[3] / 2 - cy
    return max(SIDES, key=lambda s: to_side(s, bx, by)[1] - abs(to_side(s, bx, by)[0]))


def rule_roles(faces: list, backs: list, dev) -> list[tuple[str, str | None, str]]:
    """앞면마다 (역할, 자리, 규칙 근거)."""
    cx, cy, hd = dev
    out: list = [None] * len(faces)
    rest = []
    tl = float(np.median([max(f["box"][2], f["box"][3]) for f in faces]))
    for i, f in enumerate(faces):
        near = sum(1 for b in backs if ((cen(b)[0] - cen(f["box"])[0]) ** 2 + (cen(b)[1] - cen(f["box"])[1]) ** 2) ** 0.5 < tl * 1.25)
        s = river_side(cx, cy, hd, f["box"])
        if near >= 2:  # 뒷면 줄 사이에 낀 앞면 = 패산 위 표시패
            out[i] = ("wall", None, f"뒷면 사이({near})")
        elif s:
            out[i] = ("river", s, "강 띠")
        else:
            rest.append(i)
    if not rest:
        return out
    bb = [faces[i]["box"] for i in rest]
    for g in groups(bb, tl * 1.5):
        idx = [rest[k] for k in g]
        gb = [faces[i]["box"] for i in idx]
        gcx = float(np.mean([cen(b)[0] for b in gb])) - cx
        gcy = float(np.mean([cen(b)[1] for b in gb])) - cy
        nb = sum(1 for b in backs if any(((cen(b)[0] - cen(x)[0]) ** 2 + (cen(b)[1] - cen(x)[1]) ** 2) ** 0.5 < tl * 1.6 for x in gb))
        n = len(idx)
        if n <= 2 and nb >= 1:
            r = [("wall", None, f"뒷면 줄에 붙음({nb})")] * n
        elif n >= 2 and abs(gcx) > hd * 1.6 and abs(gcy) > hd * 1.6:
            # 울기는 운 사람의 오른손 쪽 모서리: 오른쪽 아래 = 아래, 오른쪽 위 = 오른쪽, 왼쪽 위 = 위, 왼쪽 아래 = 왼쪽
            s = {(True, True): "bottom", (True, False): "right", (False, False): "top", (False, True): "left"}[(gcx > 0, gcy > 0)]
            r = [("meld", s, f"모서리 {n}장 묶음")] * n
        elif n >= 5:
            r = [("hand", near_side(cx, cy, b), f"{n}장 줄") for b in gb]
        else:
            r = [("other", None, f"{n}장 떨어짐")] * n
        for i, x in zip(idx, r):
            out[i] = x
    return out


# ---------------------------------------------------------------- 사람이 본 고침
# 이름: {"device": [cx, cy, 반 크기], "drop": [번호], "set": {번호: "역할/자리"}, "add": [[x, y, w, h, "역할/자리"]], "drop_backs": [...], "add_backs": [[x, y, w, h]], "note": "..."}
# 자리 약자 b r t l -(없음). 번호 = 확인 그림의 상자 번호(검출 순서를 위치로 정렬한 것, 다시 돌려도 같음).
FIXES: dict[str, dict] = {
    # ---- 10-31 (dev)
    "20261031_133940_f0108": {"set": {38: "meld/l", 39: "meld/l"}, "note": "왼쪽 아래 모서리 흰 패 2장(白, 뒤 프레임에서 같은 자리에 5통 울기가 더해짐)"},
    "20261031_133940_f0132": {"set": {0: "other/-"}, "note": "위 테두리 오른쪽에 걸친 패 1장(사진 끝에 잘림), 누구 것인지 모름"},
    "20261031_141615_f0101": {"set": {20: "other/-"}, "note": "아래 사람 손패 앞 손에 든 앞면 1장(뒷면 줄 규칙이 wall 로 봄)"},
    "20261031_170310_f0153": {"drop": [1], "note": "1 = 왼쪽 패산 표시패 옆 뒷면 옆구리 조각(헛검출)"},
    "20261031_170310_f0173": {"set": {18: "river/r", 53: "other/-"}, "note": "18 = 오른쪽 강 리치 선언패(세로로 눕힘), 53 = 아래 사람이 손에 든 패"},
    "20261031_170310_f0177": {"set": {**{k: "hand/r" for k in (8, 15, 20, 23, 29, 35, 39, 47, 48, 55, 56, 63, 67)}, 0: "pair/-", 1: "pair/-"},
                              "note": "오른쪽 화료(172424) 손패 13장 펼침, 0·1 = 화료자 쪽으로 옮긴 표시패 짝(리치 화료)"},
    "20261031_170310_f0314": {"set": {22: "river/l"}, "note": "22 = 왼쪽 강 6번째 리치 선언패(세로, 기기 홈에 리치봉)"},
    "20261031_170310_f0622": {"set": {k: "hand/r" for k in (57, 65, 73, 81, 87, 95, 97)},
                              "note": "유국 텐파이 공개: 위·왼쪽·오른쪽 손패 펼침"},
    "20261031_170310_f0683": {"set": {47: "river/b"}, "note": "47 = 아래 강 둘째 줄 리치 선언패(가로)"},
    # ---- 11-07 (test)
    "20261107_140304_f0123": {"drop": [6, 82, 86, 87], "note": "6·82 = 세운 손패 윗면, 86·87 = 아래 사람 손가락·테두리(헛검출). 11·12 = 패산 위 표시패 2장"},
    "20261107_140304_f0215": {"drop": [44], "set": {48: "river/r"}, "note": "44 = 왼쪽 세운 손패 옆면(헛검출), 48 = 오른쪽 강 리치 선언패(세로)"},
    "20261107_140304_f0219": {"set": {54: "river/r"}, "note": "54 = 오른쪽 강 리치 선언패(세로). 오른쪽 손패 13장 펼침(유국 텐파이 공개)"},
    "20261107_140304_f0242": {"drop": [1], "note": "1 = 위쪽 패산 뒷면 윗면(헛검출)"},
    "20261107_140304_f0285": {"drop": [1], "note": "1 = 위쪽 패산 뒷면 윗면(헛검출)"},
    "20261107_140304_f0388": {"set": {9: "river/t"}, "note": "9 = 위 강 둘째 줄 끝(오른쪽 강으로 잘못 붙음)"},
    "20261107_140304_f0389": {"set": {23: "river/t", **{k: "hand/l" for k in (24, 31, 38, 42, 50, 61, 63)}},
                              "note": "유국 텐파이 공개: 위 13장 + 왼쪽 7장(울기 둘) 펼침. 23 = 위 강"},
    "20261107_140304_f0440": {"drop": [3], "note": "3 = 위 세운 손패 끝 윗면(헛검출)"},
    "20261107_140304_f0577": {"drop": [42], "note": "유국 텐파이 공개: 위·오른쪽 손패 펼침. 42 = 왼쪽 테두리에 세워 둔 패 옆면(헛검출)"},
    "20261107_140304_f0430": {"drop": [20], "note": "20 = 왼쪽 세운 손패 옆면(헛검출)"},
    "20261107_154029_f0066": {"set": {59: "other/-"}, "note": "위 화료(154417) 손패 13장 펼침. 59 = 아래 세운 손패 앞으로 쓰러진 흰 면 1장"},
    "20261107_155125_f0006": {"device": [580, 388, 69], "note": "카메라가 움직여 기기를 손으로 잼"},
    "20261107_155125_f0041": {"device": [617, 396, 70], "note": "카메라가 움직여 기기를 손으로 잼"},
    "20261107_155125_f0061": {"device": [632, 398, 70], "drop": [25], "note": "카메라가 움직여 기기를 손으로 잼. 25 = 오른쪽 테두리 흰 면(헛검출)"},
    "20261107_155125_f0073": {"device": [648, 401, 71], "drop": [79], "set": {13: "hand/r", 17: "hand/r", 80: "other/-"},
                              "note": "카메라가 움직여 기기를 손으로 잼. 오른쪽 화료(155553) 손패 펼침, 13·17 = 손패 줄 위 끝에 조금 떨어진 2장(손패로 봄). 79 = 아래 세운 손패 윗면(헛검출), 80 = 아래 세운 손패 앞에 눕힌 앞면 1장"},
    "20261107_154029_f0041": {"drop": [0], "note": "0 = 오른쪽 위 테두리 흰 면(헛검출)"},
    "20261107_154548_f0017": {"drop": [0], "note": "0 = 오른쪽 위 테두리 흰 면(헛검출)"},
    # TEST_FIXES
}
# 끝내 확신하지 못한 것: 이름: [(번호 또는 None, 무엇이 애매한지)]
UNSURE: dict[str, list] = {
    "20261031_133940_f0108": [(38, "흰 패 2장이 白 울기(왼쪽)인지 확신 못 함 — 셋째 장이 안 보임"), (39, "38 과 같음")],
    "20261031_133940_f0132": [(0, "위 테두리에 걸친 패, 사진 끝에서 잘려 누구 것·무슨 역할인지 모름(other 로 둠)")],
    "20261031_170310_f0622": [(57, "오른쪽 펼친 손패 첫 장 위에 손가락이 조금 걸침(프레임은 남김)")],
    "20261031_170310_f0177": [(0, "짝(pair)으로 봄 — 화료자 쪽으로 옮긴 도라·뒷도라 표시패로 추정"), (1, "0 과 같음")],
    "20261031_170310_f0173": [(18, "오른쪽 강 리치 선언패로 봄(세로 패가 오른쪽 강 첫 줄 끝) — 위 강 첫 장일 수도"),
                              (53, "아래 사람이 손에 든 패(other)로 봄 — 아래 강 버림 직전일 수도")],
    "20261031_141615_f0101": [(20, "아래 손패 앞 앞면 1장, 손에 든 패로 보고 other — 떼어 둔 패일 수도")],
    "20261107_140304_f0389": [(None, "왼쪽 펼친 손패 7장 + 왼쪽 아래 모서리 울기 6장: 손패 줄과 울기의 경계는 위치로만 나눔")],
    "20261107_140304_f0123": [(11, "패산 위 앞면 2장(11·12) — 도라 표시패 + 깡 도라로 보고 wall"), (12, "11 과 같음")],
    "20261107_154029_f0066": [(59, "아래 세운 손패 앞에 쓰러진 흰 면 — 白 앞면인지 쓰러진 패 옆면인지 확실하지 않음(other)")],
    "20261107_155125_f0073": [(13, "오른쪽 손패 줄 위 끝 2장(13·17)을 손패로 봄 — 떼어 둔 화료패·짝일 수도"), (17, "13 과 같음"),
                              (80, "아래 세운 손패 앞에 눕힌 앞면 1장(other)")],
    "20261107_155125_f0006": [(None, "카메라가 움직여 기기 위치를 손으로 잼(강 띠 판정에 씀)")],
    "20261107_155125_f0041": [(None, "카메라가 움직여 기기 위치를 손으로 잼")],
    "20261107_155125_f0061": [(None, "카메라가 움직여 기기 위치를 손으로 잼")],
    "20261107_153128_f0034": [(None, "아래 사람 손이 아래 패산 쪽에 있음(앞면은 안 가림)")],
    # TEST_UNSURE
}


def parse_rs(s: str) -> tuple[str, str | None]:
    r, st = s.split("/")
    return r, SEAT[st]


def font(sz):
    try:
        return ImageFont.truetype("arial.ttf", sz)
    except OSError:
        return ImageFont.load_default()


def draw(rgb: np.ndarray, items: list, backs: list, dev, path: Path, scale: int = 2):
    H, W = rgb.shape[:2]
    im = Image.fromarray(rgb).resize((W * scale, H * scale), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    fnt = font(13)
    cx, cy, hd = dev
    d.rectangle(((cx - hd) * scale, (cy - hd) * scale, (cx + hd) * scale, (cy + hd) * scale), outline=(255, 0, 255), width=1)
    for b in backs:
        x, y, w, h = b
        d.rectangle((x * scale, y * scale, (x + w) * scale, (y + h) * scale), outline=(255, 255, 255), width=1)
    for k, it in enumerate(items):
        x, y, w, h = it["box"]
        c = COL[it["seat"]]
        d.rectangle((x * scale, y * scale, (x + w) * scale, (y + h) * scale), outline=c, width=3 if it["src"] == "det" else 2)
        if it["src"] == "added":
            d.line((x * scale, y * scale, (x + w) * scale, (y + h) * scale), fill=c, width=1)
        t = f"{it['role'][0]}{it['id']}"
        tx, ty = x * scale, y * scale - 14
        d.rectangle((tx, ty, tx + 9 * len(t), ty + 13), fill=(0, 0, 0))
        d.text((tx + 1, ty), t, fill=c, font=fnt)
    im.save(path, quality=88)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--redetect", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--no-draw", action="store_true")
    a = ap.parse_args()
    pick = json.loads((OUT / "pick.json").read_text(encoding="utf-8"))
    cache_p = OUT / "det_cache.json"
    cache = json.loads(cache_p.read_text(encoding="utf-8")) if cache_p.exists() and not a.redetect else {}
    rd = None
    only = set(a.only.split(",")) if a.only else None
    labels = {"dev": [], "test": []}
    unsure, stats = [], {"frames": 0, "auto_drop": 0, "dup_drop": 0, "fix_drop": 0, "added": 0, "full_det": 0, "up_det": 0, "set": 0}
    (OUT / "check").mkdir(parents=True, exist_ok=True)
    per_frame = []
    for fr in pick["frames"]:
        nm = fr["name"]
        rgb = np.asarray(Image.open(OUT / "images" / f"{nm}.jpg").convert("RGB"))
        H, W = rgb.shape[:2]
        if nm not in cache:
            if rd is None:
                sys.path.insert(0, str(REC))
                from app.local_read import LocalReader

                rd = LocalReader(threads=4)
                rd._sessions()
            cache[nm] = detect(rd, rgb)
            cache_p.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        det = cache[nm]
        # 흰 비율 헛검출 지우기
        hsv = np.asarray(Image.fromarray(rgb).convert("HSV"))
        white = (hsv[..., 1] < 50) & (hsv[..., 2] > 140)
        strict = (hsv[..., 1] < 25) & (hsv[..., 2] > 170)
        faces = []
        for f in det["faces"]:
            x, y, w, h = (int(round(v)) for v in f["box"])
            wf = float(white[y:y + h, x:x + w].mean()) if w > 0 and h > 0 else 0.0
            # 진한 흰색(S<25·V>170) 비율이 0.2 미만 = 연보라·분홍 뒷면을 앞면으로 잡은 것(패산 표시패 옆 뒷면에서 자주)
            sw = float(strict[y:y + h, x:x + w].mean()) if w > 0 and h > 0 else 0.0
            if wf < 0.25 or sw < 0.2:
                stats["auto_drop"] += 1
                continue
            faces.append(dict(f, white=round(wf, 2)))
        # 같은 패에 겹친 상자(작은 쪽의 60% 이상이 겹침)는 큰 상자 하나만(river.dedupe 꼴)
        keep = []
        for f in sorted(faces, key=lambda f: -f["box"][2] * f["box"][3]):
            b = f["box"]
            if any(max(0, min(b[0] + b[2], k["box"][0] + k["box"][2]) - max(b[0], k["box"][0]))
                   * max(0, min(b[1] + b[3], k["box"][1] + k["box"][3]) - max(b[1], k["box"][1])) > 0.6 * min(b[2] * b[3], k["box"][2] * k["box"][3])
                   for k in keep):
                stats["dup_drop"] += 1
                continue
            keep.append(f)
        faces = keep
        # 번호: 위치 순(y 8px 띠, x)
        faces.sort(key=lambda f: (int(cen(f["box"])[1] // 8), cen(f["box"])[0]))
        backs = [b["box"] for b in det["backs"]]
        cx, cy, hd, dsrc = device(fr["grid"], rgb)
        if "device" in FIXES.get(nm, {}):  # 카메라가 움직여 격자의 기기 상자가 어긋난 프레임: 사람이 잰 값
            cx, cy, hd = FIXES[nm]["device"]
            dsrc = "manual"
        roles = rule_roles(faces, backs, (cx, cy, hd)) if faces else []
        fx = FIXES.get(nm, {})
        items = []
        for k, (f, r) in enumerate(zip(faces, roles)):
            if k in fx.get("drop", []):
                stats["fix_drop"] += 1
                continue
            role, seat, why = r
            if k in fx.get("set", {}):
                role, seat = parse_rs(fx["set"][k])
                why = "고침"
                stats["set"] += 1
            stats["full_det" if f["det"] == "full" else "up_det"] += 1
            items.append({"id": k, "box": [round(v, 1) for v in f["box"]], "role": role, "seat": seat, "src": "det", "det": f["det"], "why": why})
        for j, ad in enumerate(fx.get("add", [])):
            role, seat = parse_rs(ad[4])
            items.append({"id": 100 + j, "box": [float(v) for v in ad[:4]], "role": role, "seat": seat, "src": "added", "why": "손으로 더함"})
            stats["added"] += 1
        backs = [b for k, b in enumerate(backs) if k not in fx.get("drop_backs", [])] + [list(map(float, b)) for b in fx.get("add_backs", [])]
        stats["frames"] += 1
        lab = {"image": f"images/{nm}.jpg", "size": [W, H], "grid": fr["grid"], "bottom_seat": fr["bottom_seat"], "phase": fr["phase"],
               "round_key": fr["round_key"], "at": fr["at"], "device": [round(cx, 1), round(cy, 1), round(hd, 1), dsrc],
               "items": [{k: v for k, v in it.items() if k in ("id", "box", "role", "seat", "src")} for it in items],
               "backs": [[round(v, 1) for v in b] for b in backs]}
        labels[fr["split"]].append(lab)
        riv = {s: sum(1 for it in items if it["role"] == "river" and it["seat"] == s) for s in SIDES}
        per_frame.append({"name": nm, "split": fr["split"], "phase": fr["phase"], "river": riv, "spread": max(riv.values()) - min(riv.values()),
                          "roles": {r: sum(1 for it in items if it["role"] == r) for r in ("river", "meld", "wall", "hand", "other")},
                          "device": dsrc})
        for k, why in UNSURE.get(nm, []):
            unsure.append({"name": nm, "id": k, "why": why})
        if not a.no_draw and (only is None or nm in only):
            draw(rgb, items, backs, (cx, cy, hd), OUT / "check" / f"{nm}.jpg")
        print(nm, fr["phase"], "river", riv, "other", per_frame[-1]["roles"], dsrc, flush=True)
    if only is None and not a.no_draw:  # 고른 표에서 빠진 프레임의 옛 확인 그림 지우기
        keep = {fr["name"] for fr in pick["frames"]}
        for q in (OUT / "check").glob("*.jpg"):
            if q.stem not in keep:
                q.unlink()
    for sp in ("dev", "test"):
        (OUT / f"labels_{sp}.draft.json").write_text(json.dumps({"_note": "판 중 프레임 역할·주인 초안(role_frames_draft.py). box = [x, y, w, h] 픽셀(1020×764). "
                                                                  "seat = 사진 기준 자리(bottom·right·top·left, 없음 null). src = det(검출기) | added(손으로 더함).",
                                                                  "frames": labels[sp]}, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "draft_uncertain.json").write_text(json.dumps({"_note": "끝내 확신하지 못한 프레임·상자(id = 확인 그림 번호, null = 프레임 전체)", "items": unsure},
                                                         ensure_ascii=False, indent=1), encoding="utf-8")
    tot = {}
    for sp in ("dev", "test"):
        for lab in labels[sp]:
            for it in lab["items"]:
                key = f"{it['role']}/{it['seat']}"
                tot.setdefault(sp, {}).setdefault(key, 0)
                tot[sp][key] += 1
    stats["by_role_seat"] = tot
    stats["per_frame"] = per_frame
    (OUT / "draft_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in stats.items() if k != "per_frame"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
