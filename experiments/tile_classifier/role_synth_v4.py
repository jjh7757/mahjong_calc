"""합성 탁자 배치 생성기 v4(2026-11-12, `docs/role_owner_plan_1111.md` 3-4 · 4-2 "D 를 하기로 함"). v3(`role_synth_v3.py`)은 고치지 않고 따로 둔다.

v3 에 더한 것 둘:
  1. 상자마다 주인 자리 = 생성기 자리 번호 k(0 아래 · 1 오른쪽 · 2 위 · 3 왼쪽 = roles.SIDES 순서, v3 `Scene.to_felt` 의 돌림 방향).
     강·울기·손패·떼어 둔 패 앞면에만 단다. 패산(표시패 앞면 포함)·짝·외톨이 앞면(-2)·뒷면(세운 손패·안깡 뒷면 포함)은 −1.
     토큰·라벨과 같은 순서(v3 `Scene.tokens` 의 빠짐·반쪽 쪼개기·중복을 그대로 따라감). 장면 전체 회전(±15°)은 주인을 안 바꾼다.
  2. 장면 종류(따로 둔 난수 = default_rng([seed, 4]) 로 뽑음): 화료 1명 55% / 판 중 30% / 여럿 펼침 15%.
     win  : v3 그대로(같은 씨드 → 같은 토큰·라벨, 회귀 확인 ②).
     mid  : 자리 0 도 다른 자리처럼 세운 손패(뒷면 줄)·울기(울기 수 분포도 다른 자리 것). 떼어 둔 패·짝 없음, 표시패는 패산 위, 리치 화료 분기 없음
            (강의 리치 선언 눕힘은 네 자리 모두 다른 자리 규칙 20%). 외톨이 앞면은 네 자리 중 아무 데나.
     multi: 네 자리 중 2(60%)~3(40%) 자리가 손패를 펼침(자리 0 포함, 나머지는 무작위). 펼친 자리는 v3 화료자 손패와 같은 식
            (패산에서 거리·기울기·끝 2~4장 떨어짐 15%·울기 위치·울기 수 분포), 13 − 3×울기 장(14장째·떼어 둔 패·짝 없음).
            펼치지 않은 자리는 세운 손패·울기. 외톨이 앞면은 펼치지 않은 자리 쪽.
  강 장수·패산 길이(강 합계와 같이 움직임)·깡·울기 모양·거리·패 크기는 v3 그대로.
보완(2026-11-12 낮, 계획서 4-2 "생성기 v4 보완", 기본 켬 · legacy=True 면 끔 = 위 그대로, 화료 1명 고정 시 v3 과 같은 토큰):
  ① 울기 묶음 중심의 옆 위치를 MELD_CX(실제 p10~p90)에서 뽑아 묶음을 옆으로만 옮김(모든 종류, 앞 거리·한 줄/쌓기 그대로)
  ② 판 중 종류만 강 기준 장수 0~18(사람마다 −2~+2·패산 길이 규칙은 v3)
  ③ 세운 손패 줄 거리를 STAND_D(실제 세운 줄 p10~p90)에서(모든 종류). 남의 울기 앞 거리는 v3 값(0.66~0.72 + 0.05~0.12) 그대로

  python -I -X utf8 experiments/tile_classifier/role_synth_v4.py [--n 6] [--seed 123]   # 종류별 예시 그림(data/role/owner/synth_v4_{win,mid,multi}.jpg)
  (예시 그림 + 실제 장면 그림은 role_owner_train_d.py samples 가 같이 만든다)
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

if __name__ == "__main__":  # 따로 돌릴 때도 v3r15d 와 같은 환경 변수(role_owner_eval 이 넣는 값)
    for _k, _v in (("ROLE_OTHER_NEG", "1"), ("ROLE_DROP_SAFE", "1"), ("ROLE_LOOSE_SHIFT", "1"), ("ROLE_SYNTH_V3_ROT", "15")):
        os.environ.setdefault(_k, _v)

import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import role_synth_v3 as g  # noqa: E402

R = g.R
ROLES = g.ROLES
SIDE = g.SIDE
SIDES = ("bottom", "right", "top", "left")  # = roles.SIDES, 자리 번호 k 순서
KINDS = ("win", "mid", "multi")
P_KIND = {"win": 0.55, "mid": 0.30, "multi": 0.15}
OWNER_ROLES = (R["hand"], R["meld"], R["river"], R["loose"])
P_OPEN3 = 0.4  # 여럿 펼침에서 3자리가 펼칠 확률(나머지 2자리)
# 보완(2026-11-12 낮, 계획서 4-2 "생성기 v4 보완", legacy=False 일 때만). 실제 = 학습 라벨 33장(연출 뺌) + 프레임-개발(10-31) 토큰에서 잼.
MELD_CX = (0.66, 0.81)   # ① 울기 묶음 중심의 자리 기준 옆 위치(묶음 상자 중심 평균): 실제 57묶음 p10 0.661 · p90 0.807(화료자 0.714·남 0.710·프레임 0.750 중앙)
MID_BASE = (0, 19)       # ② 판 중 강 기준 장수 0~18(v3 = 5~18)
STAND_D = (0.565, 0.75)  # ③ 세운 손패 줄의 기기 중심 거리: 자리·장면마다 뒷면을 가장 큰 틈(≥ 0.03)으로 패산·세운 손패 줄로 나눈 뒤 세운 줄 중앙값 148줄의 p10 0.565 · p90 0.752
LAST: dict = {}


class Scene4(g.Scene):
    """v3 Scene + 상자마다 주인(items 의 8번째 칸)."""

    def put(self, x: float, d: float, w: float, h: float, back: bool, label: int, k: int, tilt: float = 0.0, force: bool = False) -> bool:
        u, v = self.to_felt(x, d, k)
        if k % 2:
            w, h = h, w
        if not force and any(g.box_iou((u, v, w, h), it[:4]) > 0.15 for it in self.items):
            return False
        self.items.append([u, v, w, h, back, label, tilt, (k % 4) if (not back and label in OWNER_ROLES) else -1])
        return True

    def tokens(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """v3 Scene.tokens 를 옮김(난수 사용 순서 같음) + 주인을 같은 순서로."""
        import role_set as rs

        rng = self.rng
        if g.ROT == "15":
            ang = rng.normal(0, 1.5) if rng.random() < 0.65 else rng.uniform(3, 15) * rng.choice([-1, 1])
        else:
            ang = rng.normal(0, 1.5) if rng.random() < 0.96 else rng.uniform(5, 13) * rng.choice([-1, 1])
        shift, scale = rng.normal(0, 0.012, 2), rng.uniform(0.96, 1.04)
        ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        T = lambda u, v: (0.5 + ((u - 0.5) * ca - (v - 0.5) * sa) * scale + shift[0], 0.5 + ((u - 0.5) * sa + (v - 0.5) * ca) * scale + shift[1])
        su, sv = T(self.su, self.sv)
        rows, labels, owners = [], [], []
        self.kanmask = []
        for idx, (u, v, w, h, back, label, tilt, own) in enumerate(self.items):
            if g.DROP_SAFE and not (back or label == R["river"]):
                pass
            elif rng.random() < (0.02 if label in (0, 1, 5) else 0.05):
                continue
            parts = [(u, v, w)]
            if not back and rng.random() < 0.03:
                parts = [(u - w / 4, v, w / 2), (u + w / 4, v, w / 2)]
            elif rng.random() < 0.02:
                parts = [(u, v, w)] * 2
            for pu, pv, pw in parts:
                uu, vv = T(pu, pv)
                uu, vv = uu + rng.normal(0, 0.003), vv + rng.normal(0, 0.003)
                ww, hh = pw * scale * rng.uniform(0.9, 1.1), h * scale * rng.uniform(0.9, 1.1)
                t = ((tilt + ang + rng.normal(0, 1.0) + 45) % 90) - 45
                if self.feat != "rot":
                    ww, hh = rs.axis_of(ww, hh, t)
                rows.append(rs.feat_row(uu, vv, ww, hh, back, su, sv, t, self.feat))
                labels.append(label)
                owners.append(own)
                self.kanmask.append(idx in self.kan)
        return (np.array(rows, np.float32).reshape(-1, rs.feat_dim(self.feat)), np.array(labels), np.array(owners, dtype=np.int64))


def melds(sc: Scene4, x0: float, d0: float, k: int, plan: list[str]) -> None:
    """v3 melds 를 옮김(난수 순서 같음). 가깡에 더한 1장도 주인 k."""
    rng = sc.rng
    stack = rng.random() < 0.5
    x, d = x0, d0
    for j, m in enumerate(plan):
        if m == "ankan":
            n, land, backs = 4, (), (0, 3)
        elif m == "kakan":
            n, land, backs = 3, (int(rng.integers(0, 3)),), ()
        else:
            n = 4 if m == "kan" else 3
            land, backs = (int(rng.integers(0, n)),) if rng.random() < 0.85 else (), ()
        if stack and j > 0:
            d -= sc.th * rng.uniform(1.02, 1.12)
            x = x_end - n * sc.tw * 1.02 - (sc.th - sc.tw if land else 0) + rng.normal(0, 0.15 * sc.tw)
        dm = d + rng.normal(0, 0.15 * sc.tw)
        i0 = len(sc.items)
        x_end_new = sc.row(x, dm, n, R["meld"], k, land=land, backs_at=backs, force=True)
        if m in ("kan", "kakan", "ankan"):
            sc.kan.update(range(i0, len(sc.items) + (1 if m == "kakan" else 0)))
        if m == "kakan":
            it = sc.items[-n + land[0]]
            uu, vv = it[0], it[1]
            du, dv = [(0, -1), (-1, 0), (0, 1), (1, 0)][k % 4]
            w, h = it[2], it[3]
            step = (h if k % 2 == 0 else w) * rng.uniform(1.0, 1.06)
            sc.items.append([uu + du * step, vv + dv * step, w, h, False, R["meld"], it[6] + rng.normal(0, 1.0), k % 4])
        if not stack or j == 0:
            x_end = x_end_new
        x = x_end_new + sc.tw * rng.uniform(0.1, 0.6)


SEAT_X = [(1, 0), (0, -1), (-1, 0), (0, 1)]  # 자리 k 의 옆 방향(+x)을 펠트 (u, v) 로(to_felt 와 같은 돌림)


def seat_x(sc: Scene4, u: float, v: float, k: int) -> float:
    ex, ey = SEAT_X[k % 4]
    return (u - sc.su) * ex + (v - sc.sv) * ey


def place_melds(sc: Scene4, x0: float, d0: float, k: int, plan: list[str], legacy: bool) -> None:
    """legacy 면 v3 melds 그대로. 아니면(보완 ①) 묶음 중심 옆 위치를 MELD_CX 에서 뽑아, v3 식으로 놓은 묶음(한 줄·쌓기 그대로)을
    옆 방향으로만 옮겨 묶음 상자 중심 평균이 그 값에 오게 한다. 앞 거리 d 는 그대로."""
    if legacy:
        melds(sc, x0, d0, k, plan)
        return
    target = sc.rng.uniform(*MELD_CX)
    i0 = len(sc.items)
    melds(sc, x0, d0, k, plan)
    if len(sc.items) == i0:
        return
    shift = target - float(np.mean([seat_x(sc, it[0], it[1], k) for it in sc.items[i0:]]))
    ex, ey = SEAT_X[k % 4]
    for it in sc.items[i0:]:
        it[0] += shift * ex
        it[1] += shift * ey
    LAST.setdefault("meld_cx", []).append(round(target, 3))


def open_hand(sc: Scene4, k: int, plan: list[str], side_d: dict, allow_loose: bool, legacy: bool = True) -> bool:
    """v3 의 화료자 손패·(14장째)·울기·떼어 둔 패를 자리 k 에. allow_loose=True 면 v3 그대로(난수 순서 같음, k=0 일 때 v3 와 같은 결과).
    False(여럿 펼침)면 떼어 둔 패·14장째 없음(13 − 3×울기)."""
    rng = sc.rng
    tw, th = sc.tw, sc.th
    n_hand = 13 - 3 * len(plan)
    loose = (rng.random() < 0.55) if allow_loose else False
    hd = side_d[k] + th * (rng.uniform(1.7, 3.0) if rng.random() < 0.75 else rng.uniform(3.0, 5.0))
    hx = -n_hand * tw / 2 + rng.normal(0, 0.06) - (0.08 if plan else 0)
    ht = rng.normal(0, 1.5)
    if rng.random() < 0.15 and n_hand >= 6:
        m = int(rng.integers(2, 5))
        x = sc.row(hx, hd, n_hand - m, R["hand"], k, tilt=ht, force=True)
        x = sc.row(x + tw * rng.uniform(0.3, 1.0), hd + rng.normal(0, 0.006), m, R["hand"], k, tilt=ht, force=True)
    else:
        x = sc.row(hx, hd, n_hand, R["hand"], k, tilt=ht, force=True)
    end = x
    if allow_loose and not loose:
        sc.row(end, hd, 1, R["hand"], k, tilt=ht, force=True)
        end += tw * 1.03
    if plan:
        place_melds(sc, max(end + tw * rng.uniform(1.0, 4.0), 0.45), hd + rng.uniform(0.0, 0.12), k, plan, legacy)
    if loose:
        lie = rng.random() < 0.3
        lw, lh = (th, tw) if lie else (tw, th)
        lt = rng.uniform(-45, 45) if rng.random() < 0.35 else rng.normal(0, 3)
        for _ in range(20):
            r = rng.random()
            if r < 0.8:
                lx, ld = end + tw * (0.5 + rng.uniform(0.8, 6.0)), hd + tw * float(np.clip(rng.normal(0, 1.5), -2.5, 3.5))
            elif r < 0.92:
                lx, ld = rng.uniform(hx, end), hd - tw * rng.uniform(1.8, 2.8)
            else:
                lx, ld = hx - tw * rng.uniform(1.0, 4.0), hd + tw * rng.normal(0, 1.0)
            if sc.put(lx, ld, lw, lh, False, R["loose"], k, lt):
                break
    return loose


def make(rng: np.random.Generator, feat: str = "rot", kind: str = "win", legacy: bool = False) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """v3 make 를 옮기고 종류로 가름. legacy=True 이고 kind="win" 이면 v3 make 와 난수 사용·결과가 같다.
    legacy=False(기본) = 보완 ①②③(MELD_CX·MID_BASE·STAND_D)."""
    assert kind in KINDS, kind
    sc = Scene4(rng, feat)
    tw, th = sc.tw, sc.th
    win = kind == "win"
    riichi_win = (rng.random() < 0.4) and win  # 난수는 종류와 상관없이 하나 씀
    n_kan = int(rng.choice([0, 1, 2, 3], p=[0.70, 0.22, 0.07, 0.01]))
    if win:
        opened = [0]
    elif kind == "mid":
        opened = []
    else:
        n_open = 3 if rng.random() < P_OPEN3 else 2
        opened = [0] + sorted(int(v) for v in rng.choice([1, 2, 3], n_open - 1, replace=False))
    plans: list[list[str]] = []
    for k in range(4):
        if k in opened:  # 펼친 손패(화료자 · 여럿 펼침) = v3 화료자 울기 수 분포
            n = 0 if riichi_win else int(rng.choice([0, 1, 2, 3, 4], p=[0.4, 0.25, 0.2, 0.12, 0.03]))
        else:
            n = int(rng.choice([0, 1, 2, 3, 4], p=[0.55, 0.25, 0.13, 0.06, 0.01]))
        plans.append([str(rng.choice(["pon", "chi"])) for _ in range(n)])
    for _ in range(n_kan):
        k = int(rng.integers(0, 4))
        kd = "ankan" if (k == 0 and riichi_win) else str(rng.choice(["ankan", "kan", "kakan"], p=[0.4, 0.3, 0.3]))
        if kd != "ankan" and plans[k] and rng.random() < 0.6:
            plans[k][int(rng.integers(0, len(plans[k])))] = kd
        else:
            plans[k].append(kd)
    plans = [p[:4] for p in plans]
    LAST.clear()
    LAST.update(kind=kind, opened=list(opened), kan=[f"{SIDES[k]} {m}" for k, p in enumerate(plans) for m in p if m in ("kan", "kakan", "ankan")])

    # 1) 강(v3 그대로). 리치 선언 눕힘: 화료자 = riichi_win, 나머지(판 중·여럿 펼침의 자리 0 포함) = 20%
    base = int(rng.integers(*MID_BASE)) if (kind == "mid" and not legacy) else int(rng.integers(5, 19))
    dw = 0.27 * rng.uniform(0.94, 1.06)
    rivers = [max(0, base + int(rng.integers(-2, 3))) for _ in range(4)]
    for k in range(4):
        n_r = rivers[k]
        d = dw / 2 + th * 0.55 + rng.normal(0, 0.008)
        left = -dw / 2 + rng.normal(0, 0.012)
        riichi_at = int(rng.integers(0, n_r)) if n_r and (riichi_win if (k == 0 and win) else rng.random() < 0.2) else -1
        i = 0
        while i < n_r:
            n = min(6, n_r - i)
            if i >= 12 and n_r - i > 6:
                n = n_r - i
            land = tuple(j for j in range(n) if i + j == riichi_at)
            sc.row(left, d, n, R["river"], k, land=land, force=True)
            if rng.random() < 0.2:
                it = sc.items[-1]
                it[6] = rng.uniform(5, 20) * rng.choice([-1, 1])
            d += th * rng.uniform(1.0, 1.06)
            i += n
    LAST["rivers"] = rivers

    # 2) 패산 고리(v3 그대로)
    seat_cw = [0, 3, 2, 1]
    dW = rng.uniform(0.42, 0.48)
    bw = tw * rng.uniform(0.98, 1.08)
    bh = tw * rng.uniform(1.5, 1.8)
    side_d = {k: dW + rng.normal(0, 0.012) for k in range(4)}
    side_off = {k: rng.normal(0, 0.02) for k in range(4)}
    side_tilt = {k: rng.normal(0, 1.2) for k in range(4)}

    def slot_pos(s: int) -> tuple[int, float, float]:
        k = seat_cw[(s // SIDE) % 4]
        j = s % SIDE
        x = side_off[k] + (SIDE / 2 - j - 0.5) * bw * 1.02
        return k, x, side_d[k]

    b = int(rng.integers(0, 4 * SIDE))
    total_river = sum(rivers)
    drawn = 26 + int(math.ceil((total_river + n_kan) / 2))
    remain_live = max(0, 61 - drawn)
    arc = [(b + 61 - remain_live + i) % (4 * SIDE) for i in range(remain_live + 7)]
    n_ind = 1 + n_kan
    ind_slots = {(b - 3 - i) % (4 * SIDE) for i in range(n_ind)}
    pairs_to_winner = riichi_win and rng.random() < 0.85
    for s in arc:
        k, x, d = slot_pos(s)
        if s in ind_slots and not pairs_to_winner:
            sc.put(x, d, tw, th, False, R["wall"], k, side_tilt[k] + rng.normal(0, 1.5), force=True)
        else:
            w = tw * rng.uniform(1.5, 1.7) if rng.random() < 0.08 else bw
            sc.put(x, d, w, bh, True, -1, k, side_tilt[k] + rng.normal(0, 0.8), force=True)

    # 3) 펼친 손패(화료자: v3 그대로 / 여럿 펼침: 떼어 둔 패·14장째 없음)
    LAST["loose"] = False
    for k in opened:
        lo = open_hand(sc, k, plans[k], side_d, allow_loose=win, legacy=legacy)
        LAST["loose"] |= lo

    # 4) 펼치지 않은 자리: 세운 손패(뒷면 줄) + 울기(v3 의 다른 자리 그대로)
    ods = {}
    for k in range(4):
        if k in opened:
            continue
        n = 13 - 3 * len(plans[k])
        od_v3 = rng.uniform(0.66, 0.72)  # v3 의 세운 손패 거리 — 보완 뒤에도 울기 앞 거리(od_v3 + 0.05~0.12)는 이 값으로(실제와 맞음)
        od = ods[k] = od_v3 if legacy else rng.uniform(*STAND_D)
        sc.row(-n * tw / 2 + rng.normal(0, 0.05), od, n, -1, k, backs_at=tuple(range(n)))
        if plans[k]:
            place_melds(sc, rng.uniform(0.28, 0.42), od_v3 + rng.uniform(0.05, 0.12), k, plans[k], legacy)

    # 5) 리치 화료 짝(화료 1명만, v3 그대로)
    if pairs_to_winner:
        for p in range(n_ind):
            for _ in range(30):
                px = rng.uniform(-0.35, 0.3)
                pd = (dW if rng.random() < 0.6 else dW - th * rng.uniform(1.2, 1.8)) + rng.normal(0, 0.01)
                pt = rng.normal(0, 4)
                u0, v0 = sc.to_felt(px + tw / 2, pd, 0)
                u1, v1 = sc.to_felt(px + tw * 1.55, pd, 0)
                if not any(g.box_iou((u, v, tw * 1.1, th * 1.1), it[:4]) > 0.02 for u, v in ((u0, v0), (u1, v1)) for it in sc.items):
                    sc.put(px + tw / 2, pd, tw, th, False, R["pair"], 0, pt, force=True)
                    sc.put(px + tw * 1.55, pd, tw, th, False, R["pair"], 0, pt + rng.normal(0, 2), force=True)
                    break
    # 6) 외톨이 앞면(-2, 주인 없음): 화료 1명 = v3 그대로(자리 1~3), 그 밖 = 펼치지 않은 자리 중 아무 데나
    if g.OTHER_NEG:
        cands = [k for k in range(4) if k not in opened]
        for _ in range(int(rng.choice([0, 1, 2], p=[0.6, 0.3, 0.1]))):
            k = int(rng.integers(1, 4)) if win else cands[int(rng.integers(0, len(cands)))]
            lie = rng.random() < 0.3
            ow, oh = (th, tw) if lie else (tw, th)
            ot = rng.uniform(-30, 30) if rng.random() < 0.4 else rng.normal(0, 3)
            for _ in range(30):
                ox = rng.uniform(-0.38, 0.38)
                od = rng.uniform(side_d[k] + 0.6 * th, ods[k] + 1.0 * th) if rng.random() < 0.8 else rng.uniform(side_d[k] - 1.6 * th, side_d[k] - 0.7 * th)
                u, v = sc.to_felt(ox, od, k)
                if any(not it[4] and math.hypot(it[0] - u, it[1] - v) < 1.6 * th for it in sc.items):
                    continue
                if sc.put(ox, od, ow, oh, False, -2, k, ot):
                    break
    out = sc.tokens()
    LAST["kanmask"] = sc.kanmask
    return out


def kind_picker(kinds, seed: int):
    """kinds: None = P_KIND, 문자열 = 고정, dict = 확률. 종류 난수는 장면 난수와 따로(default_rng([seed, 4]))."""
    if isinstance(kinds, str):
        assert kinds in KINDS, kinds
        return lambda: kinds
    p = dict(P_KIND if kinds is None else kinds)
    names = [k for k in KINDS if p.get(k, 0) > 0]
    pr = np.array([p[k] for k in names], float)
    pr = pr / pr.sum()
    krng = np.random.default_rng([seed, 4])
    return lambda: names[int(krng.choice(len(names), p=pr))]


def dataset(n: int, seed: int, feat: str = "rot", kinds=None, legacy: bool = False) -> list[dict]:
    """→ [{name, x, y, owner, kind, n_face}]. owner = 토큰 기준 자리 번호(0 bottom·1 right·2 top·3 left, 없음 −1).
    legacy=True·kinds="win" 이면 v3 dataset(n, seed, feat) 과 x·y 가 같다(회귀 확인 ②). 기본은 보완 켬."""
    rng = np.random.default_rng(seed)
    pick = kind_picker(kinds, seed)
    out = []
    for i in range(n):
        kind = pick()
        x, y, o = make(rng, feat, kind, legacy)
        out.append(dict(name=f"synth4_{i}", x=x, y=list(y), owner=[int(v) for v in o], kind=kind, n_face=len(x)))
    return out


# ---------------------------------------------------------------- 그림
OWNER_COL = {0: (30, 90, 230), 1: (20, 160, 40), 2: (220, 30, 30), 3: (230, 190, 0), -1: (140, 140, 140)}
ROLE_CH = {0: "h", 1: "m", 2: "r", 3: "w", 4: "p", 5: "l", -2: "o", -1: ""}


def draw_tokens(x: np.ndarray, y, owner, title: str, S: int = 520, font=None):
    """토큰 한 장면 그림. 상자 테 색 = 주인(아래 파랑·오른쪽 초록·위 빨강·왼쪽 노랑·없음 회색), 뒷면 = 회색 채움, 글자 = 역할 첫 글자
    (h hand·m meld·r river·w wall·p pair·l loose·o 역할 없는 앞면). 빨간 점 = 기기 중심, 옅은 네모 = 가운데 칸(0~1)."""
    from PIL import Image, ImageDraw, ImageFont

    if font is None:
        font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 14)
    small = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 9)
    im = Image.new("RGB", (S, S), (236, 246, 236))
    d = ImageDraw.Draw(im)
    LO, SPAN = -0.55, 2.1  # 그림 범위 u·v = −0.55 ~ 1.55
    P = lambda u, v: ((u - LO) / SPAN * S, (v - LO) / SPAN * S)
    d.rectangle((*P(0, 0), *P(1, 1)), outline=(190, 210, 190), width=1)
    for r, l, o in zip(x, y, owner):
        w, h = r[2] / 10 / SPAN * S, r[3] / 10 / SPAN * S
        a = math.atan2(r[9], r[10]) / 2 if len(r) > 10 else 0.0
        cx, cy = P(r[0], r[1])
        c, s_ = math.cos(a), math.sin(a)
        pts = [(cx + dx * c - dy * s_, cy + dx * s_ + dy * c) for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))]
        if r[4]:
            d.polygon(pts, fill=(150, 150, 150), outline=(90, 90, 90))
        else:
            col = OWNER_COL.get(int(o), OWNER_COL[-1])
            d.polygon(pts, fill=(255, 255, 255), outline=col)
            d.line(pts + [pts[0]], fill=col, width=2)
            ch = ROLE_CH.get(int(l), "?")
            if ch:
                d.text((cx, cy), ch, fill=(0, 0, 0), font=small, anchor="mm")
    cx, cy = P(x[0, 0] - x[0, 6], x[0, 1] - x[0, 7])
    d.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill="red")
    d.text((5, 4), title, fill="black", font=font)
    return im


def sheet(panels: list, out: Path, cols: int = 3, S: int = 520) -> Path:
    from PIL import Image

    rows = (len(panels) + cols - 1) // cols
    im_all = Image.new("RGB", (S * cols, S * rows), "white")
    for i, (title, x, y, o) in enumerate(panels):
        im_all.paste(draw_tokens(x, y, o, title, S), ((i % cols) * S, (i // cols) * S))
    out.parent.mkdir(parents=True, exist_ok=True)
    im_all.save(out, quality=90)
    return out


def kind_sheets(n: int = 6, seed: int = 123, out_dir: Path | None = None) -> list[Path]:
    out_dir = out_dir or HERE / "data" / "role" / "owner"
    paths = []
    for kind in KINDS:
        rng = np.random.default_rng([seed, KINDS.index(kind)])
        panels = []
        for i in range(n):
            x, y, o = make(rng, "rot", kind)
            tag = f"{kind} #{i + 1}"
            if LAST["opened"] and kind != "win":
                tag += " 펼침:" + ",".join(SIDES[k] for k in LAST["opened"])
            if LAST["kan"]:
                tag += " 깡:" + ",".join(m.replace(" ", "-") for m in LAST["kan"])
            if LAST.get("loose"):
                tag += " 떼어둔패"
            tag += f" 강{sum(LAST['rivers'])}"
            panels.append((tag, x, y, o))
        paths.append(sheet(panels, out_dir / f"synth_v4_{kind}.jpg"))
    return paths


if __name__ == "__main__":
    import argparse

    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--seed", type=int, default=123)
    a = ap.parse_args()
    for p in kind_sheets(a.n, a.seed):
        print(p)
