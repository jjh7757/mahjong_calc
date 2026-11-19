"""끼우는 시각은 판독기 B 의 글에서, 들어간 칸은 그 시각의 화소로 세기(2026-11-18, 계획서 3단계 "추가 20"). Gemini 호출 없음.

그림 판독기는 "언제 틈을 벌려 끼웠나" 는 말하지만 몇 번째 틈인지를 한 칸 틀린다(metrics 표 12-43 덧붙임).
  python -X utf8 edgecount.py run [--ids a,b] [--show]     # 저장된 B 답 + 화소 세기 → 채점 → _work/edgecount_1118/result.json
  python -X utf8 edgecount.py look <차례 id> [--t0 mm:ss.s --t1 mm:ss.s]   # 창 안 프레임별 줄 모양(패 / 펠트 / 모름)과 센 값(다듬기용)

방법: ① B 의 steps 글에서 "벌려 · 끼워 …" 바로 앞 시각으로 창을 만든다 ② 창 안 프레임(초당 10장)마다 줄의 먼 쪽 등 띠 행에서
열을 패(T) / 펠트(F) / 모름(U = 손 · 소매)으로 나눠 펠트로 보이는 줄 안쪽 틈을 찾는다 ③ 틈의 한쪽이 줄 끝까지 모름 없이 보이면 그쪽 패 수를 센다
④ 창 끝 + 1초까지 남는 틈(버린 자리)은 빼고 가장 늦게까지 보인 틈 = 끼운 자리 ⑤ 센 수 → 들어간 칸 j.
고정본 pixtrack.py · slotgrid.py · pgraph.py 는 불러 쓰기만 한다.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import pgraph as pg  # noqa: E402
import pixtrack as pt  # noqa: E402
import slotgrid as sg  # noqa: E402
import turncut as tc  # noqa: E402

OUT = hc.WORK / "edgecount_1118"
GAMES = ["r12_131655", "r16_135321", "r17_140450", "r19_142013", "r13_132644"]
LAST = {"r12_131655": "r12_d06", "r16_135321": "r16_d16", "r17_140450": "r17_d11", "r19_142013": "r19_d07", "r13_132644": "r13_d09"}
KEYS = ("벌려", "벌린", "끼워", "삽입", "빈틈을 만든", "틈으로")
TIME = re.compile(r"\d\d:\d\d\.\d")
PRE_MS, POST_MS, STAY_MS = 500, 800, 1000
GAP_MIN, FUZZ, RUN_MIN, RESID = 0.30, 0.20, 0.40, 0.35   # 한 장 폭 단위: 틈 최소 폭 · 무시할 모름 폭 · 패 덩어리 최소 폭 · 반올림 허용 오차
# v2(--v2) = v1 결과(잰 4차례는 다 맞지만 B 가 틀린 차례는 하나도 못 잼)와 r13 2순 · r12 6순의 줄 모양을 본 뒤 더한 것(본 판을 보고 만듦 — 시험 아님):
#   끼우는 순간 틈의 한쪽은 손이라 "양옆이 패인 펠트 틈" 이 없다 → 펠트에 닿은 새 덩어리 모서리(F|T · T|F)가 창 앞 줄의 패 경계와 맞고
#   그 덩어리 쪽 줄 끝이 제자리면(= 안 움직인 쪽) 그 경계 번호를 쓴다. 모서리와 줄 끝 사이의 손 가림은 건너뛴다(거리로 셈).
#   펠트 판정은 등 띠 행만으로(넓힌 창에서는 손가락 · 든 패가 걸려 틈이 모름이 됐다).
V2 = False
# v3(--v3, v2 포함) = v2 가 망친 둘(r17 3순 · r19 7순)을 보고 고친 것(역시 본 판을 보고):
#   ① 모서리 쪽 패 수를 창 앞 줄이 아니라 지금 프레임에서 모서리 ~ 줄 끝 거리(보이는 펠트는 빼고, 손 가림은 패로 침)로 센다 — 버린 자리가 그새 밀려 메워졌으면 창 앞 줄 기준은 한 장 틀린다
#   ② 모서리 바깥쪽에 패도 손도 없으면 줄 끝이지 틈이 아니다  ③ 틈 너머에 원래 패가 하나도 없으면(끝에 떨어져 선 뽑은 패) 끼울 틈이 아니다
V3 = False
# v4(--v4, v3 포함) = v3 가 망친 r19 7순을 보고: 뽑은 패를 끝에서 집어 든 순간 줄 끝이 "모서리 + 그 너머 손" 으로 보여 틈으로 셌다
#   → 틈 양쪽에 원래 패가 적어도 한 장씩 있어야 끼울 틈(줄 끝에 붙이는 것은 이 도구가 재는 일이 아니다)
V4 = False
ALIGN, END_TOL, EDGE_F = 0.20, 0.25, 3     # 경계 맞춤 허용(장) · 줄 끝 제자리 허용(장) · 모서리 옆 펠트 최소 폭(px)
END_FELT = 1.5                                            # 이만큼(장) 넓은 펠트가 나오면 줄이 끝난 것으로 본다
DISCARD_LEAD = 1200                                       # 강 위 손 시각보다 이만큼 앞이면 "버리기 전"


# ------------------------------------------------------------------ B 의 글 → 창
def ms_of(tstr: str, ref: int) -> int:
    """'mm:ss.s' → ref 와 가장 가까운 시각(ms)."""
    h = int(hc.hms(ref)[:2])
    return min((hc.to_ms(f"{x:02d}:{tstr}") for x in (h - 1, h, h + 1) if 0 <= x < 24), key=lambda m: abs(m - ref))


def insert_times(steps: str) -> list:
    """끼움 낱말 바로 앞의 시각(범위면 둘 다)."""
    out = []
    toks = [(m.start(), m.end(), m.group()) for m in TIME.finditer(steps or "")]
    for k in KEYS:
        for m in re.finditer(re.escape(k), steps or ""):
            before = [t for t in toks if t[1] <= m.start()]
            if not before:
                continue
            out.append(before[-1][2])
            if len(before) >= 2 and steps[before[-2][1]:before[-1][0]].strip() == "~":
                out.append(before[-2][2])
    return sorted(set(out))


# ------------------------------------------------------------------ 프레임 → 줄 모양
def segments(R: "pt.Row", v: np.ndarray, p: float) -> list:
    """줄의 먼 쪽 등 띠 행에서 열을 T(패) / F(펠트) / U(모름)로 → [(종류, x0, x1)] 왼쪽부터."""
    skin, felt, white, back = pt.masks(v)
    # 등 띠 행을 위아래로 조금 넓혀 본다(밀려서 앞뒤로 어긋난 패도 패로 — 띠 두께만큼의 등 색이 그 안에 있으면 패)
    m = max(6, round(0.3 * p))
    ys = slice(max(0, R.b0 - m), R.b1 + 1 + m)
    T = back[ys].sum(0) >= 0.45 * (R.b1 - R.b0 + 1)
    F = ((felt[R.b0:R.b1 + 1].mean(0) > 0.6) if V2 else (felt[ys].mean(0) > 0.8)) & ~T
    c = np.where(T, 0, np.where(F, 1, 2))

    def rle(a):
        out, x = [], 0
        while x < len(a):
            y = x
            while y < len(a) and a[y] == a[x]:
                y += 1
            out.append([int(a[x]), x, y])
            x = y
        return out

    for _ in range(3):
        runs = rle(c)
        for i, (k, a, b) in enumerate(runs):
            w = b - a
            lk = runs[i - 1][0] if i else None
            rk = runs[i + 1][0] if i + 1 < len(runs) else None
            if k != 0 and w < pt.MIN_GAP and lk == 0 and rk == 0:          # 패 사이 어두운 줄
                c[a:b] = 0
            elif k == 2 and w < FUZZ * p:                                   # 모서리 그림자 같은 가는 모름
                lw = runs[i - 1][2] - runs[i - 1][1] if i else 0
                rw = runs[i + 1][2] - runs[i + 1][1] if i + 1 < len(runs) else 0
                c[a:b] = (lk if lw >= rw else rk) if (lk is not None or rk is not None) else 2
            elif k == 0 and w < RUN_MIN * p:                                # 손톱 · 얼룩 같은 좁은 패 색
                c[a:b] = 2
    return [("TFU"[k], a, b) for k, a, b in rle(c)]


def turn_pitch(R: "pt.Row", t: dict) -> float:
    """차례 시작의 온전한 줄(패 n장 한 덩어리)로 한 장 폭을 다시 잰다 — 못 찾으면 판의 값."""
    n, p0 = t["n_calc"], R.pitch
    w0, w1 = sg.window(t)
    for ms in hc.frame_range(w0, min(w1, w0 + 6000)):
        s = segments(R, R.view(ms), p0)
        ts = [(a, b) for k, a, b in s if k == "T"]
        if len(ts) == 1 and not any(k == "U" and b > ts[0][0] - p0 and a < ts[0][1] + p0 for k, a, b in s) and abs((ts[0][1] - ts[0][0]) / p0 - n) <= 1.0:
            return (ts[0][1] - ts[0][0]) / n
    return p0


def count_side(segs: list, i: int, step: int, p: float):
    """틈 segs[i] 에서 step(+1 오른쪽 / -1 왼쪽) 방향으로 줄 끝까지 → (패 수, 줄 끝 x) 또는 None(모름이 끼었거나 끝이 안 보임)."""
    n, end, j = 0, None, i + step
    seen_t = False
    while 0 <= j < len(segs):
        k, a, b = segs[j]
        if k == "F" and seen_t and (b - a) >= END_FELT * p:                 # 넓은 펠트 = 줄 끝(그 너머의 남의 손 · 소매는 안 본다)
            break
        if k == "U":
            return None
        if k == "T":
            q = (b - a) / p
            if abs(q - round(q)) > RESID or round(q) < 1:
                return None
            n += round(q)
            end = b if step > 0 else a
            seen_t = True
        j += step
    return (n, end) if seen_t else None


def full_view(segs: list, p: float):
    """줄 전체가 모름 없이 보이면 (패 수, 왼쪽 끝 x, 오른쪽 끝 x)."""
    ts = [(a, b) for k, a, b in segs if k == "T"]
    if not ts:
        return None
    lo, hi = ts[0][0], ts[-1][1]
    if any(k == "U" and b > lo - p and a < hi + p for k, a, b in segs):
        return None
    qs = [(b - a) / p for a, b in ts]
    if any(abs(q - round(q)) > RESID for q in qs):
        return None
    return sum(round(q) for q in qs), lo, hi


def runs_view(segs: list, p: float):
    """full_view 가 되는 프레임의 덩어리 → [(x0, x1, 장수)]."""
    return [(a, b, round((b - a) / p)) for k, a, b in segs if k == "T"]


def row_ends(segs: list, p: float):
    """(왼쪽 끝 x 또는 None, 오른쪽 끝 x 또는 None) — 끝 너머가 넓은 펠트(또는 그림 끝)일 때만 안다."""
    ti = [i for i, (k, a, b) in enumerate(segs) if k == "T"]
    if not ti:
        return None, None

    def ok(i, step):
        j = i + step
        if not 0 <= j < len(segs):
            return True
        k, a, b = segs[j]
        return k == "F" and ((b - a) >= END_FELT * p or j in (0, len(segs) - 1))
    return (segs[ti[0]][1] if ok(ti[0], -1) else None), (segs[ti[-1]][2] if ok(ti[-1], 1) else None)


def edge_obs(segs: list, p: float, runs_prev: list) -> list:
    """새 모서리 → [(안 움직인 쪽 'L'|'R', 그쪽 패 수(창 앞 줄 기준), 모서리 x)]."""
    n_prev = sum(r[2] for r in runs_prev)
    lo_prev, hi_prev = runs_prev[0][0], runs_prev[-1][1]
    bounds, left = [], 0                       # (경계 x, 그 왼쪽 패 수)
    for a, b, c in runs_prev:
        for i in range(c + 1):
            bounds.append((a + (b - a) * i / c, left + i))
        left += c
    old = [r[0] for r in runs_prev] + [r[1] for r in runs_prev]
    lo, hi = row_ends(segs, p)
    out = []
    if V3:
        for i, (k, a, b) in enumerate(segs):
            if k != "T" or (b - a) < 0.5 * p:
                continue
            for x, j, side in ((a, i - 1, "R"), (b, i + 1, "L")):
                if not 0 <= j < len(segs) or segs[j][0] != "F" or (segs[j][2] - segs[j][1]) < EDGE_F:
                    continue
                end = hi if side == "R" else lo
                if end is None or any(abs(x - o) < 0.3 * p for o in old):
                    continue
                beyond = segs[:j] if side == "R" else segs[j + 1:]             # 틈 너머(모서리 바깥쪽)에 패나 손이 가까이 있어야 틈
                if not any(q[0] in "TU" and (q[2] - q[1]) >= 0.3 * p and (x - q[2] if side == "R" else q[1] - x) < 3 * p for q in beyond):
                    continue
                inner = segs[i:] if side == "R" else segs[:i + 1]
                felt_w = sum(q[2] - q[1] for q in inner if q[0] == "F" and min(x, end) <= q[1] and q[2] <= max(x, end))
                d = (abs(end - x) - felt_w) / p
                if abs(d - round(d)) <= END_TOL and round(d) >= 1:
                    out.append((side, round(d), x))
        return out
    for i, (k, a, b) in enumerate(segs):
        if k != "T" or (b - a) < 0.5 * p:
            continue
        for x, nb, side in ((a, segs[i - 1] if i else None, "R"), (b, segs[i + 1] if i + 1 < len(segs) else None, "L")):
            # side = 이 모서리를 가진 덩어리가 있는 쪽(모서리가 덩어리의 왼쪽 끝이면 덩어리는 오른쪽 = 'R')
            if nb is None or nb[0] != "F" or (nb[2] - nb[1]) < EDGE_F:
                continue
            if not lo_prev + 0.5 * p < x < hi_prev - 0.5 * p or any(abs(x - o) < 0.3 * p for o in old):
                continue
            end_ok = (hi is not None and abs(hi - hi_prev) < END_TOL * p) if side == "R" else (lo is not None and abs(lo - lo_prev) < END_TOL * p)
            if not end_ok:
                continue
            bx, idx = min(bounds, key=lambda q: abs(q[0] - x))
            if abs(bx - x) < ALIGN * p:
                out.append((side, (n_prev - idx) if side == "R" else idx, x))
    return out


def gaps(segs: list, p: float) -> list:
    """줄 안쪽의 펠트 틈(양옆이 패) → [(segs 번호, x0, x1)]."""
    out = []
    for i in range(1, len(segs) - 1):
        k, a, b = segs[i]
        if k == "F" and (b - a) >= GAP_MIN * p and segs[i - 1][0] == "T" and segs[i + 1][0] == "T":
            out.append((i, a, b))
    return out


# ------------------------------------------------------------------ 한 차례
def measure(gid: str, t: dict, b: dict, R: "pt.Row", verbose: bool = False) -> dict:
    n = t["n_calc"]
    w0, w1 = sg.window(t)
    ref = t["segs"][0]["frames"][0]
    times = insert_times(b.get("steps") or "")
    if not times:
        return {"why": "B 글에 끼움 없음"}
    p = turn_pitch(R, t)
    tms = [ms_of(x, ref) for x in times]
    a0, a1 = min(tms) - PRE_MS, max(tms) + POST_MS
    t_dis = ms_of(t["cut"]["discard"], ref) if t["cut"].get("discard") else None
    k = b.get("k")
    frs = hc.frame_range(max(w0, a0 - 6000), min(w1, a1 + STAY_MS))
    cache = {}

    def segs_of(ms):
        if ms not in cache:
            cache[ms] = segments(R, R.view(ms), p)
        return cache[ms]

    # 창 앞의 마지막 온전한 줄(패 수 · 양 끝) — 뽑은 패가 줄에 서 있는지 · 어느 끝인지
    prev, runs_prev = None, None
    for ms in [m for m in frs if m < a0][::-1]:
        fv = full_view(segs_of(ms), p)
        if fv:
            prev = (ms, *fv)
            runs_prev = runs_view(segs_of(ms), p)
            break
    obs = []
    for ms in [m for m in frs if a0 <= m <= a1 + STAY_MS]:
        s = segs_of(ms)
        before = t_dis is None or ms < t_dis - DISCARD_LEAD
        n_o = n if before else n - 1
        cands = [(ga, gb, {side: count_side(s, i, step, p) for side, step in (("R", 1), ("L", -1))}) for i, ga, gb in gaps(s, p)]
        if V2 and prev is not None:
            lo_now, hi_now = row_ends(s, p)
            cands += [(x, x, {side: (cnt, hi_now if side == "R" else lo_now)}) for side, cnt, x in edge_obs(s, p, runs_prev)]
        for ga, gb, sides in cands:
            js = {}
            for side in ("R", "L"):
                cs = sides.get(side)
                if cs is None:
                    continue
                cnt, end = cs
                d_here = 0
                if prev is not None:
                    _, n_prev, lo_prev, hi_prev = prev
                    n_o_prev = n if (t_dis is None or prev[0] < t_dis - DISCARD_LEAD) else n - 1
                    if n_prev == n_o_prev + 1:                                # 뽑은 패가 줄에 서 있었다 → 어느 끝인가
                        # 시작 줄보다 왼쪽으로 한 장 나와 있으면 왼쪽 끝, 아니면 오른쪽 끝(줄 폭으로 가름: 틈 없는 줄이면 양 끝 차이가 패 수와 같다)
                        at_left = lo_prev < R_left0(R, gid, t) - 0.5 * p
                        if (side == "L" and at_left) or (side == "R" and not at_left):
                            far_prev = lo_prev if side == "L" else hi_prev
                            d_here = 1 if abs(end - far_prev) < 0.5 * p else 0      # 그 끝 패가 아직 서 있나
                orig = cnt - d_here
                if V3 and orig <= 0:
                    continue
                l_orig = orig if side == "L" else n_o - orig
                if not 0 <= l_orig <= n_o or (V4 and not 1 <= l_orig <= n_o - 1):
                    continue
                js[side] = l_orig + 1 - (1 if (before and k is not None and k <= l_orig) else 0)
            if not js or len(set(js.values())) > 1:
                continue
            obs.append({"ms": ms, "j": next(iter(js.values())), "sides": "".join(sorted(js)), "x": (ga, gb)})
            if verbose:
                print(f"      {hc.hms(ms)[3:]} 틈 {ga}~{gb}px({(gb - ga) / p:.1f}장) → j {obs[-1]['j']} ({obs[-1]['sides']}){' · 버리기 전' if before else ''}")
    out = {"times": times, "window": [hc.hms(a0)[3:], hc.hms(a1)[3:]], "n_obs": len(obs), "prev": None if prev is None else {"t": hc.hms(prev[0])[3:], "n": prev[1]}}
    if not obs:
        return {**out, "why": "창 안에 셀 수 있는 틈 없음"}
    by = defaultdict(list)
    for o in obs:
        by[o["j"]].append(o["ms"])
    live = {j: v for j, v in by.items() if max(v) < a1 + STAY_MS - 250 and min(v) <= a1}   # 창 끝 + 1초까지 남은 틈 = 안 메워진 것(버린 자리)
    out["seen"] = {str(j): [len(v), hc.hms(max(v))[3:]] for j, v in sorted(by.items())}
    if not live:
        return {**out, "why": "틈이 창 뒤에도 남음"}
    strong = {j: v for j, v in live.items() if len(v) >= 2} or live
    out["j"] = max(strong, key=lambda j: max(strong[j]))
    return out


_LEFT0: dict = {}
_DET: dict = {}


def R_left0(R, gid: str, t: dict) -> float:
    """차례 시작 줄의 왼쪽 끝 x — 칸 틀 도구와 같은 틀(검출 상자), 없으면 화소로."""
    key = t["id"]
    if key not in _LEFT0:
        if gid not in _DET:
            f = sg.OUT / f"det_{gid}.json"
            _DET[gid] = {int(k): v for k, v in hc.jload(f).items()} if f.exists() else {}
        w0, w1 = sg.window(t)
        frs = [(ms, _DET[gid][ms]) for ms in sorted(_DET[gid]) if w0 <= ms <= w1]
        an = sg.anchor(frs, t["n_calc"]) if frs else None
        _LEFT0[key] = an[0] if an else 0.0
    return _LEFT0[key]


# ------------------------------------------------------------------ 자료 · 채점
def load_b(gid: str) -> dict:
    old = pg.load_b(gid, False) or {}
    f = hc.WORK / "turncut_1117" / f"{gid}_B.json"
    new = {}
    if f.exists():
        d = hc.jload(f)
        rows = d.get("rows", d) if isinstance(d, dict) else d
        new = rows if isinstance(rows, dict) else {x["id"]: x for x in rows if isinstance(x, dict) and "id" in x}
    return {**old, **new}


def truth_all() -> dict:
    u = dict(hc.jload(tc.BASE / "truth_final.json"))
    u.update(hc.jload(hc.WORK / "slotgrid_1117" / "truth_r13.json"))
    return u


def turns_all() -> list:
    out = []
    for gid in GAMES:
        for t in tc.turns_of(gid):
            out.append((gid, t))
            if t["id"] == LAST[gid]:
                break
    return out


def cmd_run(a):
    global V2, V3, V4
    V4 = bool(a.v4)
    V3 = bool(a.v3) or V4
    V2 = bool(a.v2) or V3
    truth = truth_all()
    ids = set(a.ids.split(",")) if a.ids else None
    rows, Rs, Bs = [], {}, {}
    for gid, t in turns_all():
        tid = t["id"]
        u = truth[tid]
        if u["kind"] != "hand" or (ids and tid not in ids):
            continue
        if gid not in Rs:
            Rs[gid], Bs[gid] = pt.Row(gid), load_b(gid)
        b = Bs[gid].get(tid)
        nb = pg.norm(b)
        if not nb or nb["kind"] != "hand":
            rows.append({"id": tid, "b_ok": False, "fin_ok": False, "measured": False, "why": "B 가 손에서 낸 차례로 안 읽음"})
            print(f"  {tid:9s} B 가 손에서 낸 차례로 안 읽음 — 그대로(틀림)")
            continue
        if a.show:
            print(f"  -- {tid}")
        m = measure(gid, t, b, Rs[gid], a.show)
        j_fin = m.get("j", nb["j"])
        b_ok = pg.right(nb, u)
        fin_ok = pg.right({**nb, "j": j_fin}, u)
        rows.append({"id": tid, "k_b": nb["k"], "j_b": nb["j"], "j_code": m.get("j"), "j_fin": j_fin, "k_true": u["k_id"], "j_true": u["j_closed"], "b_ok": b_ok, "fin_ok": fin_ok,
                     "measured": "j" in m, **{x: m[x] for x in ("times", "window", "n_obs", "seen", "why", "prev") if x in m}})
        mark = "" if "j" not in m else ("  ← 고침" if fin_ok and not b_ok else "  ← **망침**" if b_ok and not fin_ok else "")
        print(f"  {tid:9s} 정답 {u['k_id']}·{u['j_closed']} | B {nb['k']}·{nb['j']} {'✓' if b_ok else '✗'} | 코드 j {m.get('j', '-')}"
              f"{' (본 값 ' + str(m['seen']) + ')' if 'seen' in m else ''}{' — ' + m['why'] if 'why' in m else ''} | B+코드 {nb['k']}·{j_fin} {'✓' if fin_ok else '✗'}{mark}"
              + (f" | 창 {m['window'][0]}~{m['window'][1]}" if "window" in m else ""))
    n = len(rows)
    meas = [r for r in rows if r["measured"]]
    print(f"합: 손에서 낸 {n}차례 · B 혼자 맞음 {sum(r['b_ok'] for r in rows)} · B+코드 맞음 {sum(r['fin_ok'] for r in rows)}"
          f" · 코드가 잰 차례 {len(meas)}(j 가 정답과 같음 {sum(r['j_code'] == r['j_true'] for r in meas)})"
          f" · 고침 {sum(r['fin_ok'] and not r['b_ok'] for r in rows)} · 망침 {sum(r['b_ok'] and not r['fin_ok'] for r in rows)}")
    if not ids:
        OUT.mkdir(parents=True, exist_ok=True)
        hc.jsave(OUT / (a.out or "result.json"), {"v2": V2, "v3": V3, "v4": V4, "params": {"pre": PRE_MS, "post": POST_MS, "stay": STAY_MS, "gap_min": GAP_MIN, "fuzz": FUZZ, "run_min": RUN_MIN, "resid": RESID, "lead": DISCARD_LEAD}, "rows": rows})
        print("→", OUT / (a.out or "result.json"))


def cmd_look(a):
    global V2, V3, V4
    V4 = bool(a.v4)
    V3 = bool(a.v3) or V4
    V2 = bool(a.v2) or V3
    gid = sg.game_of(a.id)
    t = next(x for x in tc.turns_of(gid) if x["id"] == a.id)
    R = pt.Row(gid)
    p = turn_pitch(R, t)
    ref = t["segs"][0]["frames"][0]
    w0, w1 = sg.window(t)
    a0 = ms_of(a.t0, ref) if a.t0 else w0
    a1 = ms_of(a.t1, ref) if a.t1 else w1
    print(f"{a.id} 한 장 폭 {p:.1f}px · 등 띠 행 {R.b0}~{R.b1} · 시작 줄 왼쪽 끝 {R_left0(R, gid, t):.0f}px")
    for ms in hc.frame_range(a0, a1):
        s = segments(R, R.view(ms), p)
        line = " ".join(f"{k}{(b_ - a_) / p:.1f}" for k, a_, b_ in s if not (k == "F" and (a_ == 0 or b_ >= R.view(ms).shape[1] - 1)))
        print(f"  {hc.hms(ms)[3:]}  {line}")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("run")
    p.add_argument("--ids")
    p.add_argument("--show", action="store_true")
    p.add_argument("--out")
    p.add_argument("--v2", action="store_true")
    p.add_argument("--v3", action="store_true")
    p.add_argument("--v4", action="store_true")
    p = sp.add_parser("look")
    p.add_argument("id")
    p.add_argument("--t0")
    p.add_argument("--t1")
    p.add_argument("--v2", action="store_true")
    p.add_argument("--v3", action="store_true")
    p.add_argument("--v4", action="store_true")
    a = ap.parse_args()
    {"run": cmd_run, "look": cmd_look}[a.cmd](a)


if __name__ == "__main__":
    main()
