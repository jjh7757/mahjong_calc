"""틀 규칙(frame_rules.py 표 1-23)에서 torch 없이 쓰는 부분. 서버 벤치(server_bench/bench.py)와 같이 쓴다. 서버 app.seat 를 고치지 않은 복사본 + 규칙."""
from __future__ import annotations

import os
import statistics
import sys

import numpy as np

sys.path.insert(0, os.environ.get("RECOGNIZER_REPO", "C:/Users/jjh7757/dev/mahjong-recognizer"))
from app import river as rv  # noqa: E402
from app import seat as st  # noqa: E402

BLANK = 0.01  # 이보다 무늬가 적으면 白 후보(정답 있는 白 상자는 0.0)
LOW_INK = 0.015
ABOVE = 1.5  # 손패 줄보다 패 몇 개 위까지 울기 후보로 보나
STRAY_UP, STRAY_DOWN = 1.0, 3.5  # 떼어 둔 패: 손패 줄 기준 패 몇 개 위·아래까지
ANGLES = range(0, 360, 15)


def line_of(hand: list) -> tuple[float, float]:
    a, c = np.polyfit([x[0] + x[2] / 2 for x in hand], [x[1] + x[3] / 2 for x in hand], 1)
    return float(a), float(c)


def split2(rgb: np.ndarray, faces: list, split: int, o: set):
    """st.structure_split 복사본에 '이웃'·'두단' 만 더했다."""
    if not faces:
        return None
    W = rgb.shape[1]
    up = [x for x in faces if x[3] > x[2]] or faces
    tw = statistics.median(x[2] for x in up)
    th = statistics.median(x[3] for x in up)
    faces = st.on_table(faces, rgb, st.TABLE_REACH * th)
    hand_side = [f for f in faces if f[0] + f[2] / 2 < split + st.SPLIT_MARGIN * W]
    line = st.fit_line(hand_side)
    if line is None:
        return None
    a, c = line
    on = sorted([f for f in hand_side if abs(f[1] + f[3] / 2 - (a * (f[0] + f[2] / 2) + c)) < 0.5 * th and f[3] > f[2]], key=lambda x: x[0])
    if not on:
        return None
    runs = [[on[0]]]
    for f in on[1:]:
        if f[0] - (runs[-1][-1][0] + runs[-1][-1][2]) > st.RUN_GAP * tw:
            runs.append([f])
        else:
            runs[-1].append(f)
    hand = max(runs, key=len)
    after = runs[runs.index(hand) + 1:]
    hx1 = hand[-1][0] + hand[-1][2]
    sep = after[0][0] if after and len(after[0]) == 1 and after[0][0][0] - hx1 < st.SEP_DIST * tw else None
    used = set(hand) | ({sep} if sep else set())
    rest = [f for f in faces if f not in used and f[0] > hand[0][0]]
    loose = [f for f in faces if f not in used and f not in rest]
    if "이웃" in o:
        far = [f for f in rest if f[1] + f[3] / 2 < a * (f[0] + f[2] / 2) + c - ABOVE * th]
        loose += far
        rest = [f for f in rest if f not in far]
    melds = []
    for g in st.cluster(rest, tw * st.GAP, th * 0.5):
        g = sorted(g, key=lambda x: x[0])
        if len(g) in (3, 4):
            melds.append(g)
        elif len(g) in st.SPLIT_MELD:
            k = st.SPLIT_MELD[len(g)][0]
            by_y = sorted(g, key=lambda x: x[1] + x[3] / 2)
            if "두단" in o and by_y[k][1] + by_y[k][3] / 2 - (by_y[k - 1][1] + by_y[k - 1][3] / 2) > 0.4 * th:
                melds += [sorted(by_y[:k], key=lambda x: x[0]), sorted(by_y[k:], key=lambda x: x[0])]
            else:
                melds += [g[:k], g[k:]]
        else:
            loose.extend(g)
    melds.sort(key=lambda m: m[0][0])
    return st.SeatFrame(hand, sep, melds, loose, tw, th, len(faces), split=True)


def strict2(fr, tol: float) -> bool:
    """st.strict_ok 에서 직선 허용만 바꾼 것."""
    hand = fr.hand
    if len(hand) < 4:
        return False
    hs, ws = [x[3] for x in hand], [x[2] for x in hand]
    mh, mw = statistics.median(hs), statistics.median(ws)
    if any(abs(h - mh) > 0.25 * mh for h in hs) or any(abs(w - mw) > 0.25 * mw for w in ws):
        return False
    xs = np.array([x[0] + x[2] / 2 for x in hand], float)
    ys = np.array([x[1] + x[3] / 2 for x in hand], float)
    a, c = np.polyfit(xs, ys, 1)
    if np.max(np.abs(ys - (a * xs + c))) > tol * mh:
        return False
    steps = np.diff(xs)
    return bool(np.all(steps > 0.6 * mw) and np.all(steps < 1.4 * mw))


def ok2(fr, rgb: np.ndarray, o: set) -> bool:
    """st.valid + st.safe_ok, 무늬 검사만 규칙에 따라 다르다."""
    if not st.valid(fr) or not strict2(fr, 0.30 if "줄" in o else 0.25):
        return False
    th = statistics.median(x[3] for x in fr.hand)
    for m in fr.melds:
        for a, c in zip(m, m[1:]):
            if a[0] + a[2] - c[0] > 0.3 * min(a[2], c[2]):
                return False
        if any(not 0.5 * th <= x[3] <= 1.3 * th for x in m):
            return False
    blank = lambda x: "백" in o and st.ink(rgb, x) < BLANK
    low = LOW_INK if "옅음" in o else st.INK_MIN
    if sum(blank(x) for x in fr.hand) > 4:
        return False
    for x in fr.hand + ([fr.separate] if fr.separate else []):
        if st.ink(rgb, x) < low and not blank(x):
            return False
    for m in fr.melds:
        if any(blank(x) for x in m) and not all(blank(x) for x in m):
            return False
        for x in m:
            if st.ink(rgb, x) < low and not blank(x):
                return False
    return True


def strays(fr, faces: list, rgb: np.ndarray) -> list:
    """손패 줄 오른쪽, 탁자 위에 홀로 놓인 앞면 패."""
    a, c = line_of(fr.hand)
    used = set(fr.hand) | {x for m in fr.melds for x in m}
    hx1 = fr.hand[-1][0] + fr.hand[-1][2]
    out = []
    table = st.on_table(faces, rgb, st.TABLE_REACH * fr.th)
    for g in st.cluster([f for f in table if f not in used], fr.tw * st.GAP, fr.th * 0.5):
        if len(g) != 1:
            continue
        f = g[0]
        cx, cy = f[0] + f[2] / 2, f[1] + f[3] / 2
        if cx > hx1 and -STRAY_UP * fr.th < cy - (a * cx + c) < STRAY_DOWN * fr.th:
            out.append(f)
    return out
