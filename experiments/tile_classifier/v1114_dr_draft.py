"""11-14 자료 → 검출기·역할 모델용 라벨 초안(2026-11-15, 검출·역할 세트 1단계 A). v1114_draft.py·v1114_split.py·v1114_crops.py 다음에.

대상 = manifest 의 고른 그림 189장(2992², split_final 그대로). 라벨은 2992 좌표로 한 번 달고, 세 화질은 manifest rules.scale 로 비율만 바꿔 쓴다.
격자(저장 grid)는 전혀 쓰지 않는다 — 2반장(13:07~14:27)은 저장 격자가 탁자와 어긋나 있다. 펠트·기기는 그림에서 직접 찾는다.

검출 상자(기존 규칙: det_backs.py·det_obb.py 머리말, data/det/obb/audit/BRIEF.md — 종류 0 앞면 / 1 뒷면, 상자 하나 = 패 하나, 회전 상자):
  앞면 = v1114 draft 상자(사진 전체 검출, 안깡 뒷면은 그때 뺌)에서 시작.
    분류기 세트 눈 확인(review + _overrides) 의 verdict 가 not_tile(또는 mixed 의 그 그림이 not_tile) 이면:
      같은 자리에 뒷면 검출 상자가 있으면 지움(drop, 뒷면은 그 상자로) / 상자 안 뒷면 색(det_backs.back_mask loose) ≥ BACK_FRAC 이면 뒷면으로(to_back) /
      그 밖은 지움(drop). 셋 다 2단계가 그림으로 확정한다(지운 상자도 확인 그림에 회색 점선으로 남김).
    unsure·가림으로 분류기 세트에서 뺀 상자(_overrides boxes drop 포함)는 앞면으로 남긴다.
  더한 앞면 = 그림을 네 조각(겹침 OV)으로 나눠 원래 크기로(전체 검출의 약 2.3배 해상도) 운영 검출기(tile-obb-r8)를 돌려 draft 의 어느 상자와도
    안 겹치는(IoU < 0.3, 중심이 안 들어감) 앞면 — 흰 비율 거르기(role_frames_draft 와 같음)를 지난 것만. src=quad, 표시 new.
  뒷면 = 전체 검출 + 네 조각 검출의 뒷면(cls 1)을 합침(role_frames_draft.detect 방식). 남긴 앞면과 상자 면적 40% 넘게 겹친 뒷면은 버린다(role_v2_apply.overlaps_face).
역할·주인 초안(판 중 프레임 = labels_{dev,test}.json 형식 / 화료 사진 = labels_v2_owner.json 형식, 앞면만, 뒷면은 역할 없음):
  규칙 = role_frames_draft.rule_roles 의 기하 규칙(기기 위치는 그림에서 직접 찾음). 화료 사진은 그 뒤 화료자 쪽 손패 = hand(주인 화료자),
    화료자 손패 앞 낱장 1장 = loose, 2·4장 묶음 = pair, 그래도 남은 펠트 안쪽 외톨이(1~2장 덩어리)를 모아 합 2·4장 = pair, 1장 = loose
    (사용자 규칙: 탁자 위 표시패는 2장 이상일 때만, 낱장 1장은 떼어 둔 화료패). 정답 대조의 손패 수 = closed − 1(론: 화료패는 쏜 사람 강) / closed(쯔모).
  모델 = 운영 역할 모델 tile-roles-v3r15d: 화료 사진은 화료자 기준 1회(서버 read_roles 와 같음), 프레임은 네 자리 기준 4회 + _pick_role
    (ondevice.overlay 와 같음). 주인 = 실험 모델 D(tile-roles-owner-d, 사진 기준 1회 역할 + 주인) — 운영 모델은 강 주인을 안 낸다. 토큰 격자 =
    그림에서 찾은 펠트 사각형으로 gridFromFelt(앱 felt_grid.dart)와 같은 계산(가운데 칸 0.2~0.8), 리치봉 상자 = 찾은 기기.
  갈림 = 규칙 역할 ≠ 모델 역할(role) 또는 둘 다 주인이 있는 역할인데 자리가 다름(seat). 정답 대조 = 화료 사진 label.json(자기 것, 없으면 같은 판 재촬영
    label_sibling)과 화료자 손패·울기·짝 수와 패 종류를 맞대어 어긋난 상자·그림에 표시만(덮어쓰지 않음).
그림 단위 표시 짐작: not_table(펠트 못 찾음·펠트 면적 < 25%) / blur(상자 안 선명도 중앙값 < 189장 중앙값 × BLUR_K, 또는 분류기 세트 메모에 흔들림)
  / occluded(펠트 안 살색 > OCC_FRAC, 또는 분류기 세트 image_notes 에 가림·팔) — 2단계가 확정. 표시가 있어도 목록에서 빼지 않는다.
기기 위치 = 그림에서 찾은 펠트 사각형의 편 좌표 가운데(앱 felt_grid 의 기기 크기 0.197×0.194), 리치봉 홈 네 막대가 보이면 그 가운데로 다듬음
  (기기 몸통은 어두운 청록이라 색으로는 펠트와 안 갈림). device.src = felt | felt+slots.

  python -X utf8 experiments/tile_classifier/v1114_dr_draft.py [판 id ...]     (전체 약 10분, CPU)
결과 data/v1114/dr/draft/<판>.json, data/v1114/dr/draft/_summary.json
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REC = Path(r"C:\Users\jjh7757\dev\mahjong-recognizer")
sys.path.insert(0, str(REC))
from app import local_read as lr  # noqa: E402
from app import obb, roles  # noqa: E402

sys.path.insert(0, str(HERE))
from det_backs import back_mask, felt_mask, skin_mask  # noqa: E402
from v1114_split import image_rel  # noqa: E402

V = HERE / "data" / "v1114"
OUT = V / "dr" / "draft"
CAP = HERE.parents[1] / "experiments" / "visit_20261114" / "captures"
D_MODEL = HERE / "server_bench" / "models" / "tile-roles-owner-d.onnx"
SIDES = ("bottom", "right", "top", "left")
OWNED = ("hand", "loose", "meld", "river")
OV = 60  # 조각 겹침(px, 2992)
BACK_FRAC = 0.15  # not_tile 앞면 상자 안 뒷면 색 비율이 이 이상이면 뒷면으로
BACK_ON_FACE = 0.4  # 뒷면 상자 면적 중 남긴 앞면과 겹친 비율이 이보다 크면 뒷면 버림
BLUR_K = 0.25  # 0.45 는 44장(2반장 프레임이 전반적으로 낮아 멀쩡한 그림까지 잡힘, r12 f0099 를 열어 봄)
OCC_FRAC = 0.06  # 0.03~0.04 는 탁자 끝 손 정도(그림 몇 장으로 봄)
SMALL = 748  # 펠트·기기 찾는 축소 크기
HAND_MIN = 0.8  # ondevice._pick_role


# ------------------------------------------------------------------ 기하 도우미
def iou(a, b) -> float:
    ix = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    i = ix * iy
    return i / (a[2] * a[3] + b[2] * b[3] - i + 1e-9)


def inter(a, b) -> float:
    ix = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    return ix * iy


def cen(b):
    return (b[0] + b[2] / 2, b[1] + b[3] / 2)


def inside(p, b) -> bool:
    return b[0] <= p[0] <= b[0] + b[2] and b[1] <= p[1] <= b[1] + b[3]


def same_place(a, b) -> bool:
    return iou(a, b) >= 0.3 or inside(cen(a), b) or inside(cen(b), a)


def rect_list(rc) -> list:
    return [[round(float(rc[0][0]), 1), round(float(rc[0][1]), 1)], [round(float(rc[1][0]), 1), round(float(rc[1][1]), 1)], round(float(rc[2]), 2)]


def corners(rc) -> list:
    return [[round(float(x), 1), round(float(y), 1)] for x, y in cv2.boxPoints(((rc[0][0], rc[0][1]), (rc[1][0], rc[1][1]), rc[2]))]


def axis_rect(b) -> list:
    return [[b[0] + b[2] / 2, b[1] + b[3] / 2], [float(b[2]), float(b[3])], 0.0]


# ------------------------------------------------------------------ 펠트·기기(그림에서 직접)
def felt_quad(rgb: np.ndarray) -> dict:
    """초록 펠트 가장 큰 덩어리의 볼록 껍질 → 네 꼭짓점(왼위부터 시계 방향, 2992 좌표). 못 찾으면 ok False."""
    H, W = rgb.shape[:2]
    k = SMALL / max(H, W)
    sm = cv2.resize(rgb, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    bgr = cv2.cvtColor(sm, cv2.COLOR_RGB2BGR)
    fm = felt_mask(bgr)
    fm = cv2.morphologyEx(fm, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(fm)
    if n <= 1:
        return {"ok": False, "why": "펠트 색 없음", "area_frac": 0.0}
    c = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    pts = np.column_stack(np.nonzero(lab == c))[:, ::-1].astype(np.float32)
    hull = cv2.convexHull(pts)
    area_frac = float(cv2.contourArea(hull)) / (sm.shape[0] * sm.shape[1])
    # 변마다 직선 맞추기(앱 felt_grid 처럼): 볼록 껍질의 최소 사각형 변 둘레 띠(변 길이 3%)에 든 펠트 윤곽 점만으로 fitLine →
    # 이웃 직선의 교점. 모서리 패·팔이 깎은 귀퉁이는 띠 밖이라 안 쓴다.
    cnts, _ = cv2.findContours((lab == c).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cpts = max(cnts, key=cv2.contourArea).reshape(-1, 2).astype(np.float64)
    box = cv2.boxPoints(cv2.minAreaRect(hull)).astype(np.float64)
    s, d = box.sum(1), box[:, 0] - box[:, 1]
    box = np.array([box[np.argmin(s)], box[np.argmax(d)], box[np.argmax(s)], box[np.argmin(d)]])
    lines = []
    for i in range(4):
        p, q2 = box[i], box[(i + 1) % 4]
        L = float(np.linalg.norm(q2 - p))
        u = (q2 - p) / max(L, 1e-6)
        nrm = np.array([-u[1], u[0]])
        rel = cpts - p
        t, dist = rel @ u, np.abs(rel @ nrm)
        sel = cpts[(dist < 0.03 * L) & (t > 0.08 * L) & (t < 0.92 * L)]
        if len(sel) >= 10:
            vx, vy, x0_, y0_ = cv2.fitLine(sel.astype(np.float32), cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
            lines.append((np.array([x0_, y0_], float), np.array([vx, vy], float)))
        else:
            lines.append((p, u))
    quad = []
    for i in range(4):
        (p1, d1), (p2, d2) = lines[i - 1], lines[i]
        A = np.array([d1, -d2]).T
        try:
            t1, _ = np.linalg.solve(A, p2 - p1)
            quad.append(p1 + t1 * d1)
        except np.linalg.LinAlgError:
            quad.append(box[i])
    quad = np.array(quad) / k
    ok = area_frac >= 0.25
    return {"ok": ok, "why": "" if ok else f"펠트 면적 {area_frac:.2f}", "area_frac": round(area_frac, 3),
            "quad": [[round(float(x), 1), round(float(y), 1)] for x, y in quad], "hull_small": hull.reshape(-1, 2).tolist(), "k": k}


def plane_of(quad) -> np.ndarray:
    src = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], np.float32)
    return cv2.getPerspectiveTransform(src, np.array(quad, np.float32))


def at(Hm, u, v):
    p = Hm @ np.array([u, v, 1.0])
    return p[0] / p[2], p[1] / p[2]


def find_device(rgb: np.ndarray, felt: dict) -> dict:
    """가운데 기기(검은 사각형): 펠트 가운데 둘레 창에서 어두운(최대 채널 < 90, 초록 아님) 가장 큰 덩어리의 3~97% 범위."""
    H, W = rgb.shape[:2]
    k = SMALL / max(H, W)
    sm = cv2.resize(rgb, None, fx=k, fy=k, interpolation=cv2.INTER_AREA).astype(int)
    if felt.get("quad"):
        Hm = plane_of(felt["quad"])
        fx, fy = at(Hm, 0.5, 0.5)
        side = float(np.mean([np.hypot(*np.subtract(felt["quad"][i], felt["quad"][(i + 1) % 4])) for i in range(4)]))
    else:
        fx, fy, side = W / 2, H / 2, 0.7 * W
    # 기기 몸통은 어두운 청록이라 펠트 색으로 잡힌다(펠트 덩어리에 포함). 그래서 앱 felt_grid.dart 와 같이 펠트 편 좌표 가운데·크기(0.197×0.194)로 잡고,
    # 리치봉 홈 넷(아주 어두운 막대, 최대 채널 < 75, 가로 2·세로 2)의 가운데로 중심만 다듬는다.
    hd0 = 0.0975 * side
    felt_dev = {"cx": round(fx, 1), "cy": round(fy, 1), "hd": round(hd0, 1)}
    cx, cy, r = fx * k, fy * k, 1.3 * hd0 * k
    x0, y0, x1, y1 = int(max(0, cx - r)), int(max(0, cy - r)), int(min(sm.shape[1], cx + r)), int(min(sm.shape[0], cy + r))
    a = sm[y0:y1, x0:x1]
    if a.size == 0:
        return {**felt_dev, "src": "felt", "why": "기기 자리가 사진 밖"}
    dark = (a.max(2) < 75).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(dark)
    bars = []
    for c in range(1, n):
        x, y, w, h, area = st[c]
        L, S = max(w, h), min(w, h)
        if L >= 0.5 * hd0 * k and L <= 1.6 * hd0 * k and S <= 0.35 * L:  # 리치봉 홈 = 가늘고 긴 막대
            bars.append((x + w / 2, y + h / 2, w > h))
    hor = [b for b in bars if b[2]]
    ver = [b for b in bars if not b[2]]
    if len(hor) >= 2 and len(ver) >= 2:
        hor.sort(key=lambda b: b[1])
        ver.sort(key=lambda b: b[0])
        dcx = (x0 + (ver[0][0] + ver[-1][0]) / 2) / k
        dcy = (y0 + (hor[0][1] + hor[-1][1]) / 2) / k
        off = float(np.hypot(dcx - fx, dcy - fy))
        if off < 0.6 * hd0:
            return {"cx": round(dcx, 1), "cy": round(dcy, 1), "hd": round(hd0, 1), "src": "felt+slots", "felt_off": round(off, 1), "felt_pred": felt_dev}
        return {**felt_dev, "src": "felt", "why": f"리치봉 홈 가운데가 펠트 가운데와 {off:.0f}px 어긋나 펠트 값을 씀"}
    return {**felt_dev, "src": "felt", "why": f"리치봉 홈을 못 찾음(가로 {len(hor)} 세로 {len(ver)})"}


def grid_of(felt: dict, dev: dict, W: int, H: int) -> dict | None:
    """앱 gridFromFelt 와 같은 가운데 칸(펠트 편 좌표 0.2~0.8) — 1000 분율. 리치봉 상자 = 찾은 기기 ± 반 크기(+ 여유 10)."""
    if not felt.get("quad"):
        return None
    Hm = plane_of(felt["quad"])
    lo, hi = 0.2, 0.8
    a, b, c, d = at(Hm, lo, lo), at(Hm, hi, lo), at(Hm, hi, hi), at(Hm, lo, hi)
    g = {"x1": round((a[0] + d[0]) / 2 / W * 1000), "x2": round((b[0] + c[0]) / 2 / W * 1000),
         "y1": round((a[1] + b[1]) / 2 / H * 1000), "y2": round((c[1] + d[1]) / 2 / H * 1000)}
    cx, cy, hd = dev["cx"], dev["cy"], dev["hd"]
    cl = lambda v: int(min(1000, max(0, v)))
    g["sticks"] = [cl((cy - hd) / H * 1000 - 10), cl((cx - hd) / W * 1000 - 10), cl((cy + hd) / H * 1000 + 10), cl((cx + hd) / W * 1000 + 10)]
    return g


# ------------------------------------------------------------------ 검출(전체 + 네 조각)
def detect_all(rd: lr.LocalReader, rgb: np.ndarray) -> dict:
    H, W = rgb.shape[:2]
    f1, b1, _, sc = rd._seat_raw(rgb)
    out = {"full_faces": [(list(b), r, sc.get(b)) for b, r in f1], "full_backs": [(list(b), r) for b, r in b1], "quad_faces": [], "quad_backs": []}
    for x0, y0, x1, y1 in [(0, 0, W // 2 + OV, H // 2 + OV), (W // 2 - OV, 0, W, H // 2 + OV), (0, H // 2 - OV, W // 2 + OV, H), (W // 2 - OV, H // 2 - OV, W, H)]:
        part = np.ascontiguousarray(rgb[y0:y1, x0:x1])
        f, b, _, s2 = rd._seat_raw(part)
        cw, ch = x1 - x0, y1 - y0

        def cut_edge(bb):  # 조각 안쪽 끝에 닿은 상자(잘린 패) — 사진 끝이면 그대로
            return ((bb[0] <= 2 and x0 > 0) or (bb[1] <= 2 and y0 > 0) or (bb[0] + bb[2] >= cw - 2 and x1 < W) or (bb[1] + bb[3] >= ch - 2 and y1 < H))

        for bb, rc in f:
            if not cut_edge(bb):
                out["quad_faces"].append(([bb[0] + x0, bb[1] + y0, bb[2], bb[3]], ((rc[0][0] + x0, rc[0][1] + y0), rc[1], rc[2]), s2.get(bb)))
        for bb, rc in b:
            if not cut_edge(bb):
                out["quad_backs"].append(([bb[0] + x0, bb[1] + y0, bb[2], bb[3]], ((rc[0][0] + x0, rc[0][1] + y0), rc[1], rc[2])))
    return out


def white_ok(rgb_hsv, b) -> tuple[bool, float]:
    x, y, w, h = (int(round(v)) for v in b)
    s, v = rgb_hsv[y:y + h, x:x + w, 1], rgb_hsv[y:y + h, x:x + w, 2]
    if s.size == 0:
        return False, 0.0
    wf = float(((s < 50) & (v > 140)).mean())
    sw = float(((s < 25) & (v > 170)).mean())
    return wf >= 0.25 and sw >= 0.2, round(wf, 2)


def poly_frac(mask: np.ndarray, rc) -> float:
    pts = np.round(cv2.boxPoints(((rc[0][0], rc[0][1]), (rc[1][0], rc[1][1]), rc[2]))).astype(np.int32)
    x0, y0 = max(0, pts[:, 0].min()), max(0, pts[:, 1].min())
    x1, y1 = min(mask.shape[1], pts[:, 0].max() + 1), min(mask.shape[0], pts[:, 1].max() + 1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    m = np.zeros((y1 - y0, x1 - x0), np.uint8)
    cv2.fillPoly(m, [pts - [x0, y0]], 1)
    sub = mask[y0:y1, x0:x1] > 0
    return float(sub[m > 0].mean()) if (m > 0).any() else 0.0


# ------------------------------------------------------------------ 역할 규칙(role_frames_draft.rule_roles 와 같은 기하)
def to_side(side, dx, dy):
    return {"bottom": (dx, dy), "right": (-dy, dx), "top": (-dx, -dy), "left": (dy, -dx)}[side]


def river_side(cx, cy, hd, box):
    bx, by = box[0] + box[2] / 2 - cx, box[1] + box[3] / 2 - cy
    cands = []
    for s in SIDES:
        u, v = to_side(s, bx, by)
        if v < hd * 0.6 or v > hd * 2.9 or u < -hd * 1.45 or u > hd * 1.9:
            continue
        over = max(0.0, abs(u) - hd) if u < 0 else max(0.0, u - hd * 1.05)
        fit = (box[3] >= box[2]) == (s in ("bottom", "top"))
        cands.append((not fit, over, v, s))
    return sorted(cands)[0][3] if cands else None


def groups(boxes, link):
    n = len(boxes)
    par = list(range(n))

    def f(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            a, b = cen(boxes[i]), cen(boxes[j])
            if np.hypot(a[0] - b[0], a[1] - b[1]) < link:
                par[f(i)] = f(j)
    g: dict = {}
    for i in range(n):
        g.setdefault(f(i), []).append(i)
    return list(g.values())


def near_side(cx, cy, box):
    bx, by = box[0] + box[2] / 2 - cx, box[1] + box[3] / 2 - cy
    return max(SIDES, key=lambda s: to_side(s, bx, by)[1] - abs(to_side(s, bx, by)[0]))


def rule_roles(faces: list, backs: list, dev, winner: str | None, felt_quad_pts=None) -> list[tuple[str, str | None, str]]:
    """앞면 축 상자마다 (역할, 자리, 근거). 판 중 규칙 = role_frames_draft.rule_roles. winner 가 있으면(화료 사진) 화료자 쪽을 더 본다."""
    cx, cy, hd = dev
    out: list = [None] * len(faces)
    if not faces:
        return out
    tl = float(np.median([max(f[2], f[3]) for f in faces]))
    rest = []
    for i, f in enumerate(faces):
        near = sum(1 for b in backs if np.hypot(cen(b)[0] - cen(f)[0], cen(b)[1] - cen(f)[1]) < tl * 1.25)
        s = river_side(cx, cy, hd, f)
        if near >= 2:
            out[i] = ("wall", None, f"뒷면 사이({near})")
        elif s:
            out[i] = ("river", s, "강 띠")
        else:
            rest.append(i)
    gs = []
    for g in groups([faces[i] for i in rest], tl * 1.5):
        idx = [rest[k] for k in g]
        gb = [faces[i] for i in idx]
        gcx = float(np.mean([cen(b)[0] for b in gb])) - cx
        gcy = float(np.mean([cen(b)[1] for b in gb])) - cy
        gs.append((idx, gb, gcx, gcy))
    # 화료 사진: 화료자 쪽 펼친 손패 줄(5장 이상)의 깊이 v — 그보다 안쪽(기기 쪽)에 떨어진 1장 = 떼어 둔 화료패, 2·4장 = 표시패 짝
    hand_v = None
    if winner:
        vs = [to_side(winner, gcx, gcy)[1] for idx, gb, gcx, gcy in gs if len(idx) >= 5 and near_side(cx, cy, [gcx + cx - 1, gcy + cy - 1, 2, 2]) == winner]
        hand_v = max(vs) if vs else None
    for idx, gb, gcx, gcy in gs:
        nb = sum(1 for b in backs if any(np.hypot(cen(b)[0] - cen(x)[0], cen(b)[1] - cen(x)[1]) < tl * 1.6 for x in gb))
        n = len(idx)
        gside = near_side(cx, cy, [gcx + cx - 1, gcy + cy - 1, 2, 2])
        wv = to_side(winner, gcx, gcy)[1] if winner else None
        front = winner is not None and hand_v is not None and hd * 1.0 < wv < hand_v - 0.8 * tl and gside == winner
        if winner and gside == winner and n >= 5:
            r = [("hand", winner, f"화료자 쪽 {n}장 줄")] * n
        elif front and n == 1:
            r = [("loose", winner, "화료자 손패 앞 낱장(떼어 둔 화료패)")]
        elif front and n in (2, 4):
            r = [("pair", None, f"화료자 손패 앞 {n}장(표시패 짝)")] * n
        elif n <= 2 and nb >= 1:
            r = [("wall", None, f"뒷면 줄에 붙음({nb})")] * n
        elif n >= 2 and abs(gcx) > hd * 1.6 and abs(gcy) > hd * 1.6:
            s = {(True, True): "bottom", (True, False): "right", (False, False): "top", (False, True): "left"}[(gcx > 0, gcy > 0)]
            r = [("meld", s, f"모서리 {n}장 묶음")] * n
        elif n >= 5:
            r = [("hand", near_side(cx, cy, b), f"{n}장 줄") for b in gb]
        else:
            r = [("other", None, f"{n}장 떨어짐")] * n
        for i, x in zip(idx, r):
            out[i] = x
    # 화료 사진: 남은 other 중 펠트 안쪽(테두리에서 패 긴 변 1.2배 넘게 떨어짐)의 1~2장 덩어리를 모아 합이 2·4장이면 짝, 1장이면 떼어 둔 화료패
    # (짝 두 장이 떨어져 놓여 각각 낱장으로 잡히던 것 — r18 win_141910)
    if winner and felt_quad_pts is not None:
        poly = np.array(felt_quad_pts, np.float32).reshape(-1, 1, 2)
        lone = []
        for idx, gb, gcx, gcy in gs:
            if len(idx) <= 2 and all(out[i][0] == "other" for i in idx):
                d = cv2.pointPolygonTest(poly, (float(gcx + cx), float(gcy + cy)), True)
                if d > 1.2 * tl:
                    lone += idx
        if len(lone) in (2, 4):
            for i in lone:
                out[i] = ("pair", None, f"화료 사진 펠트 안쪽 외톨이 {len(lone)}장(표시패 짝)")
        elif len(lone) == 1:
            out[lone[0]] = ("loose", winner, "화료 사진 펠트 안쪽 외톨이 1장(떼어 둔 화료패)")
    return out


# ------------------------------------------------------------------ 모델
class Models:
    def __init__(self):
        self.prod = roles.RoleNet(roles.ROLE_MODEL, threads=4)
        self.d = roles.RoleNet(D_MODEL, threads=4)

    def run(self, faces, pts, backs, grid, W, H, winner):
        n = len(faces)
        if n == 0 or grid is None:
            return [None] * n
        # 운영 모델: 화료 사진 = 화료자 기준 1회, 그 밖 = 네 자리 + _pick_role
        if winner:
            r, c = self.prod.predict(roles.tokens(faces, W, H, grid, winner, 11, pts, backs))
            prod = [(r[i], float(c[i]), winner if r[i] in ("hand", "loose") else None) for i in range(n)]
            how = f"v3r15d 화료자({winner}) 기준 1회"
        else:
            by = {s: self.prod.predict(roles.tokens(faces, W, H, grid, s, 11, pts, backs)) for s in SIDES}
            prod = []
            for i in range(n):
                per = {s: (by[s][0][i], float(by[s][1][i])) for s in SIDES}
                best = max(((c, s) for s, (r, c) in per.items() if r == "hand"), default=None)
                if best is not None and best[0] >= HAND_MIN:
                    prod.append(("hand", best[0], best[1]))
                    continue
                votes: dict = {}
                for r, c in per.values():
                    votes[r] = votes.get(r, 0.0) + c
                role = max(votes, key=votes.get)
                prod.append((role, votes[role] / 4, None))
            how = "v3r15d 네 자리 + _pick_role"
        pr, po = self.d._session().run(["role", "owner"], {"x": roles.tokens(faces, W, H, grid, "bottom", 11, pts, backs)[None]})
        out = []
        for i in range(n):
            role, conf, seat = prod[i]
            d_role = roles.ROLES[int(pr[0][i].argmax())]
            d_seat = SIDES[int(po[0][i].argmax())]
            out.append({"role": role, "conf": round(conf, 3), "seat": (seat or d_seat) if role in OWNED else None, "seat_src": "prod" if seat else "D",
                        "d_role": d_role, "d_conf": round(float(pr[0][i].max()), 3), "d_seat": d_seat, "how": how})
        return out


# ------------------------------------------------------------------ 정답 대조
def label_of(it: dict) -> tuple[dict | None, str | None, str | None]:
    if it.get("has_label"):
        return json.loads((CAP / it["src_dir"] / "label.json").read_text(encoding="utf-8")), "own", it["src_dir"]
    if it.get("label_sibling"):
        return json.loads((CAP / it["label_sibling"] / "label.json").read_text(encoding="utf-8")), "sibling", it["label_sibling"]
    return None, None, None


def label_check(lab: dict, boxes: list, winner: str) -> dict:
    """화료자 손패(hand+loose)·울기·짝 수와 패 종류를 정답과 맞댐. 어긋난 상자에 label_mismatch(이유) — 덮어쓰지 않음."""
    meld_tiles = [t for m in lab.get("melds", []) for t in re.findall(r"[0-9][mpsz]", m)]
    ind = list(lab.get("dora_indicators", [])) + list(lab.get("ura_indicators", []))
    # 론이면 화료패는 쏜 사람 강에 있다 → 사진의 화료자 손패 = closed - 1. 쯔모면 closed 그대로(떼어 둔 화료패 포함)
    exp = {"hand": len(lab.get("closed", [])) - (0 if lab.get("is_tsumo") else 1), "meld_max": len(meld_tiles), "pair": len(ind) if (lab.get("riichi") and len(ind) >= 2) else 0}
    hb = [b for b in boxes if b["cls"] == "face" and b["status"] == "keep" and b["rule"]["role"] in ("hand", "loose") and b["rule"]["seat"] == winner]
    mb = [b for b in boxes if b["cls"] == "face" and b["status"] == "keep" and b["rule"]["role"] == "meld" and b["rule"]["seat"] == winner]
    pb = [b for b in boxes if b["cls"] == "face" and b["status"] == "keep" and b["rule"]["role"] == "pair"]
    got = {"hand": len(hb), "meld": len(mb), "pair": len(pb)}
    issues = []
    if got["hand"] != exp["hand"]:
        issues.append(f"화료자 손패(hand+loose) {got['hand']}장 ≠ 정답 {exp['hand']}장")
    # 울기는 안깡이면 앞면 2장만 보이므로 최소 = 장수 - 안깡 몫, 최대 = 장수
    if not (len(lab.get("melds", [])) * 3 - 2 * sum(1 for m in lab.get("melds", []) if len(re.findall(r'[0-9][mpsz]', m)) == 4) <= got["meld"] <= exp["meld_max"]):
        issues.append(f"화료자 울기 {got['meld']}장, 정답 울기 {len(lab.get('melds', []))}개 {exp['meld_max']}장")
    if got["pair"] != exp["pair"]:
        issues.append(f"짝(pair) {got['pair']}장 ≠ 정답 표시패 {exp['pair']}장(리치 {lab.get('riichi')}, 표시패 {ind})")

    def excess(bs, want: Counter, why: str):
        have = Counter(b["tile"] for b in bs if b.get("tile"))
        for t, n in have.items():
            k = n - want.get(t, 0)
            if k > 0:
                for b in sorted([b for b in bs if b.get("tile") == t], key=lambda b: b.get("tile_conf") or 0)[:k]:
                    b.setdefault("label_mismatch", []).append(f"{why}: {t} 가 정답보다 {k}장 많음")

    excess(hb, Counter(lab.get("closed", [])), "화료자 손패")
    excess(mb, Counter(meld_tiles), "화료자 울기")
    if exp["pair"]:
        excess(pb, Counter(ind), "짝")
    marked = sum(1 for b in boxes if b.get("label_mismatch"))
    return {"expect": exp, "got": got, "issues": issues, "marked_boxes": marked}


# ------------------------------------------------------------------ 분류기 세트 결과
def classifier_info(round_id: str):
    rv = json.loads((V / "review" / f"{round_id}.json").read_text(encoding="utf-8"))
    ovf = json.loads((V / "review" / "_overrides.json").read_text(encoding="utf-8"))
    tracks = {t["tid"]: dict(t) for t in rv["tracks"]}
    for o in ovf["overrides"]:
        if o["round"] == round_id and o["tid"] in tracks:
            tracks[o["tid"]].update({k: o[k] for k in ("verdict", "tile", "per_image") if k in o})
            tracks[o["tid"]]["override"] = o.get("note", "")
    box_ov = {(b["image"], b["i"]): b for b in ovf.get("boxes", []) if b["round"] == round_id}
    notes = {}
    for n in rv.get("image_notes", []):
        notes.setdefault(n["image"], []).append(n["note"])
    return tracks, box_ov, notes


def main():
    t_all = time.time()
    man = json.loads((V / "manifest.json").read_text(encoding="utf-8"))
    want = set(sys.argv[1:])
    crops = {}
    for c in json.loads((V / "crops" / "index.json").read_text(encoding="utf-8")):
        crops[(c["image"], c["i"])] = c
    OUT.mkdir(parents=True, exist_ok=True)
    rd = lr.LocalReader(threads=4)
    rd._sessions()
    md = Models()
    summary = {"made": time.strftime("%Y-%m-%dT%H:%M:%S"), "models": {"det": Path(rd.seat_model).name, "role": roles.ROLE_MODEL.name, "role_owner": D_MODEL.name},
               "rounds": {}}
    sharp_all = []
    per_round = {}
    for r in man["rounds"]:
        if want and r["id"] not in want:
            continue
        t0 = time.time()
        d0 = json.loads((V / "draft" / f"{r['id']}.json").read_text(encoding="utf-8"))
        d_imgs = {im["id"]: im for im in d0["images"]}
        tracks, box_ov, cnotes = classifier_info(r["id"])
        its = sorted([it for it in man["items"] if it["round"] == r["id"] and it["selected"]], key=lambda it: it["at"])
        win_sides = [it.get("winner_side") for it in its if it["kind"] == "win" and it.get("winner_side")]
        images = []
        for it in its:
            p = V / image_rel(it, "q2992")
            rgb = np.asarray(Image.open(p).convert("RGB"))
            H, W = rgb.shape[:2]
            hsv = np.asarray(Image.fromarray(rgb).convert("HSV"))
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            bmask = back_mask(bgr, loose=True)
            felt = felt_quad(rgb)
            dev = find_device(rgb, felt)
            grid = grid_of(felt, dev, W, H)
            det = detect_all(rd, rgb)
            dimg = d_imgs[it["id"]]
            # ---- 앞면: v1114 draft 상자
            faces, notile = [], []
            for b in dimg["boxes"]:
                tr = tracks.get(b.get("track"), {})
                verdict = tr.get("verdict")
                pi = (tr.get("per_image") or {}).get(it["id"]) if verdict == "mixed" else None
                not_tile = verdict == "not_tile" or pi == "not_tile"
                rc = b["rect"] if b.get("rect") else axis_rect(b["box"])
                cr = crops.get((it["id"], b["i"]))
                e = {"cls": "face", "box": [int(v) for v in b["box"]], "rect": rc, "src": "v1114", "draft_i": b["i"], "track": b.get("track"),
                     "det": b.get("det"), "verdict": verdict, "per_image": pi, "read": b["t"], "read_c": b["c"],
                     "tile": cr["tile"] if cr else None, "tile_src": "crops" if cr else None, "tile_conf": b["c"], "flags": []}
                if (it["id"], b["i"]) in box_ov:
                    e["box_override"] = {k: box_ov[(it["id"], b["i"])].get(k) for k in ("action", "tile", "note")}
                if not cr and not not_tile:
                    e["flags"].append(f"분류기 세트 밖({verdict or '검토 없음'})")
                    if verdict == "fix":
                        e["tile"], e["tile_src"] = tr.get("tile"), "review_fix"
                    elif verdict == "ok":
                        e["tile"], e["tile_src"] = tr.get("draft"), "review_ok"
                    elif verdict == "mixed" and pi:
                        e["tile"], e["tile_src"] = pi, "review_mixed"
                (notile if not_tile else faces).append(e)
            # ---- 네 조각에서만 나온 앞면
            n_quad_white_drop = 0
            allf = [e["box"] for e in faces + notile] + [list(b) for b, _, _ in det["full_faces"]]
            for bb, rc, sc in det["quad_faces"]:
                if any(same_place(bb, o) for o in allf):
                    continue
                ok, wf = white_ok(hsv, bb)
                if not ok:
                    n_quad_white_drop += 1
                    continue
                allf.append(bb)
                faces.append({"cls": "face", "box": [int(v) for v in bb], "rect": rect_list(rc), "src": "quad", "det": sc, "verdict": None, "tile": None,
                              "flags": ["new: 조각 검출에서만 나옴"], "white": wf})
            # ---- 뒷면
            backs: list = []
            for bb, rc in det["full_backs"] + det["quad_backs"]:
                if any(same_place(bb, o["box"]) for o in backs):
                    continue
                backs.append({"cls": "back", "box": [int(v) for v in bb], "rect": rect_list(rc), "src": "det", "flags": []})
            n_back_on_face = 0
            kept_backs = []
            for b in backs:
                a = b["box"][2] * b["box"][3]
                if any(inter(b["box"], f["box"]) > BACK_ON_FACE * a for f in faces):
                    n_back_on_face += 1
                    continue
                kept_backs.append(b)
            backs = kept_backs
            # ---- not_tile 앞면 처리
            dropped = []
            for e in notile:
                hit = next((k for k, b in enumerate(backs) if same_place(e["box"], b["box"])), None)
                frac = poly_frac(bmask, e["rect"])
                e["back_frac"] = round(frac, 2)
                if hit is not None:
                    e.update(status="drop", action="drop", why=f"분류기 세트 not_tile, 같은 자리에 뒷면 검출 상자 있음")
                    e["same_back"] = hit
                    dropped.append(e)
                elif frac >= BACK_FRAC:
                    backs.append({"cls": "back", "box": e["box"], "rect": e["rect"], "src": "from_face", "draft_i": e["draft_i"], "track": e["track"],
                                  "flags": [f"앞면 → 뒷면(분류기 세트 not_tile, 뒷면 색 {frac:.2f})"], "verdict": e["verdict"], "note": tracks.get(e["track"], {}).get("note")})
                else:
                    e.update(status="drop", action="drop", why=f"분류기 세트 not_tile, 뒷면 색 {frac:.2f} — 패 아님으로 봄")
                    dropped.append(e)
            for e in faces:
                e["status"] = "keep"
            for b in backs:
                b["status"] = "keep"
            # ---- 번호(위치 순: 앞면 → 뒷면 → 지운 앞면)
            tile = float(np.median([min(e["box"][2], e["box"][3]) for e in faces])) if faces else 80.0
            key = lambda e: (int(cen(e["box"])[1] // max(8, tile / 2)), cen(e["box"])[0])
            faces.sort(key=key)
            backs.sort(key=key)
            dropped.sort(key=key)
            boxes = faces + backs + dropped
            for k, e in enumerate(boxes):
                e["id"] = k
                e["rect"] = [[round(float(e["rect"][0][0]), 1), round(float(e["rect"][0][1]), 1)], [round(float(e["rect"][1][0]), 1), round(float(e["rect"][1][1]), 1)], round(float(e["rect"][2]), 2)]
                e["pts"] = corners(e["rect"])
            for b in backs:  # 같은 자리 뒷면 번호
                pass
            for e in dropped:
                if "same_back" in e:
                    e["same_back"] = backs[e["same_back"]]["id"]
            # ---- 화료자
            winner, wsrc = None, None
            if it["kind"] == "win":
                if it.get("winner_side"):
                    winner, wsrc = it["winner_side"], "meta"
                elif win_sides:
                    winner, wsrc = Counter(win_sides).most_common(1)[0][0], "same_round_win"
            # ---- 역할
            fb = [e["box"] for e in faces]
            bb_ = [e["box"] for e in backs]
            devt = (dev["cx"], dev["cy"], dev["hd"])
            if it["kind"] == "win" and winner is None and faces:  # 화료자 모름(r22): 가장 긴 앞면 줄이 있는 쪽을 짐작
                rr = rule_roles(fb, bb_, devt, None)
                hs = Counter(s for (ro, s, _) in rr if ro == "hand")
                if hs:
                    winner, wsrc = hs.most_common(1)[0][0], "guess_longest_hand"
            rr = rule_roles(fb, bb_, devt, winner, felt.get("quad") if it["kind"] == "win" else None)
            mm = md.run(fb, [np.array(e["pts"]) for e in faces], [(e["box"], np.array(e["pts"])) for e in backs], grid, W, H, winner if it["kind"] == "win" else None)
            n_split = Counter()
            for e, r_, m_ in zip(faces, rr, mm):
                e["rule"] = {"role": r_[0], "seat": r_[1], "why": r_[2]}
                e["model"] = m_
                sp = []
                if m_ is not None:
                    if m_["role"] != r_[0]:
                        sp.append("role")
                    elif r_[0] in OWNED and m_["seat"] and r_[1] != m_["seat"]:
                        sp.append("seat")
                e["split"] = sp
                for s in sp:
                    n_split[s] += 1
            # ---- 정답 대조
            lab_chk = None
            if it["kind"] == "win":
                lab, lsrc, ldir = label_of(it)
                if lab is not None and winner:
                    lab_chk = {"label_src": lsrc, "label_dir": ldir, **label_check(lab, boxes, winner),
                               "label": {k: lab.get(k) for k in ("closed", "win_tile", "melds", "dora_indicators", "ura_indicators", "riichi", "is_tsumo", "winner")}}
            # ---- 그림 단위 표시 짐작
            gray = cv2.cvtColor(cv2.resize(rgb, (1496, 1496 * H // W), interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY).astype(np.float32)
            lap = cv2.Laplacian(gray, cv2.CV_32F)
            hull_m = np.zeros(gray.shape, np.uint8)
            if felt.get("hull_small"):
                kk = 1496 / W / felt["k"]
                cv2.fillPoly(hull_m, [np.round(np.array(felt["hull_small"]) * kk).astype(np.int32)], 1)
            if hull_m.sum() < 1000:
                hull_m[:] = 1
            # 선명도 = 남긴 상자(앞·뒤)마다 상자 안 라플라시안 분산(원본)의 중앙값 — 사진 전체 값은 패가 적은 그림에서 낮게 나와 못 씀
            g_full = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            bs_ = []
            for e in faces + backs:
                x, y, w, h = e["box"]
                cr = g_full[max(0, y):y + h, max(0, x):x + w]
                if cr.shape[0] > 8 and cr.shape[1] > 8:
                    e["sharp"] = round(float(cv2.Laplacian(cr, cv2.CV_32F).var()), 1)
                    bs_.append(e["sharp"])
            sharp = float(np.median(bs_)) if len(bs_) >= 5 else float(lap[hull_m > 0].var())
            sk = skin_mask(cv2.resize(bgr, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_AREA))
            skin = float((sk[hull_m > 0] > 0).mean())
            sharp_all.append(sharp)
            guess = []
            if not felt["ok"]:
                guess.append("not_table")
            if skin > OCC_FRAC or any(re.search(r"가림|가려|가린|팔|손이", n) for n in cnotes.get(it["id"], [])):
                guess.append("occluded")
            img = {"id": it["id"], "name": it["name"], "kind": it["kind"], "at": it["at"], "split_final": it["split_final"], "scene_round": it["scene_round"],
                   "scene": it.get("scene"), "path": image_rel(it, "q2992"), "paths": {q: image_rel(it, q) for q in ("q2992", "q1496", "q997")},
                   "size": [W, H], "format": "win" if it["kind"] == "win" else "frame",
                   "winner": winner, "winner_src": wsrc, "felt": {k: v for k, v in felt.items() if k not in ("hull_small", "k")}, "device": dev, "grid_est": grid,
                   "flags_guess": guess, "flag_stats": {"sharp": round(sharp, 1), "skin": round(skin, 4), "felt_area": felt["area_frac"]},
                   "classifier_notes": cnotes.get(it["id"], []), "prev_round_scene": dimg.get("prev_round_scene"),
                   "counts": {"face": len(faces), "back": len(backs), "dropped_face": len(dropped), "face_to_back": sum(1 for b in backs if b["src"] == "from_face"),
                              "quad_face_added": sum(1 for e in faces if e["src"] == "quad"), "quad_face_white_drop": n_quad_white_drop,
                              "back_on_face_drop": n_back_on_face, "split_role": n_split["role"], "split_seat": n_split["seat"],
                              "label_mismatch_boxes": sum(1 for b in boxes if b.get("label_mismatch"))},
                   "label_check": lab_chk, "boxes": boxes}
            images.append(img)
            print(it["id"], img["counts"], dev["src"], guess, f"sharp {sharp:.0f} skin {skin:.3f}", flush=True)
        per_round[r["id"]] = (r, images, round(time.time() - t0, 1))
    # 흔들림 짐작: 펠트 안 선명도 < 전체 중앙값 × BLUR_K
    med = float(np.median(sharp_all)) if sharp_all else 0.0
    for rid, (r, images, sec) in per_round.items():
        for img in images:
            if img["flag_stats"]["sharp"] < BLUR_K * med or any("흔들" in n for n in img["classifier_notes"]):
                img["flags_guess"].append("blur")
            img["flag_stats"]["sharp_median_all"] = round(med, 1)
        cnt = Counter()
        for img in images:
            for k, v in img["counts"].items():
                cnt[k] += v
        res = {"round": rid, "round_name": r["round"], "split_final": r.get("split_final", r["split"]),
               "_note": "검출·역할 라벨 초안(v1114_dr_draft.py). 좌표 = 2992 원본 픽셀(q1496 ×0.5, q997 ×1/3). boxes[]: id(그림 안 번호, 확인 그림 글자), cls face|back, "
                        "status keep|drop(지운 초안 앞면 — 라벨 아님, 2단계가 되살릴 수 있음), box [x,y,w,h] 축 상자, rect [[cx,cy],[w,h],각도°](cv2 minAreaRect 꼴), pts 네 꼭짓점, "
                        "src v1114(분류기 세트 초안 상자)|quad(조각 검출에서만)|det(뒷면 검출)|from_face(not_tile 앞면 → 뒷면), tile(분류기 세트 종류), "
                        "rule/model(역할·주인 초안, 앞면만), split(규칙·모델 갈림), label_mismatch(정답 대조).",
               "counts": dict(cnt), "sec": sec, "images": images}
        (OUT / f"{rid}.json").write_text(json.dumps(res, ensure_ascii=False, indent=0), encoding="utf-8")
        summary["rounds"][rid] = {"split_final": res["split_final"], "images": len(images), **dict(cnt), "sec": sec}
    if not want:
        summary["sharp_median_all"] = med
        summary["sec"] = round(time.time() - t_all, 1)
        (OUT / "_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print("끝", round(time.time() - t_all, 1), "초")


if __name__ == "__main__":
    main()
