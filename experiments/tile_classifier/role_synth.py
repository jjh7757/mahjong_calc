"""합성 탁자 배치 생성기(2026-11-03). role_set.py 가 학습 전 사전학습에 쓴다.

실제 25장(표 1-57)의 분포에 맞춰 펠트 기준 0~1 좌표로 상자를 놓는다(화료자 = 아래 자리). 패 폭 약 0.048·높이 0.066.
놓는 것: 화료자 손패 줄(13~14장 − 울기, 두 덩이로 갈라짐·화료패 떼어 둠 포함), 울기 0~4(치·퐁 3, 깡 4, 눕힌 1장), 네 자리 강(6장 줄·눕힌 리치패),
패산(뒷면 상자, 줄마다 빠진 구간·왕패)과 패산 위 표시패(앞면 낱장), 리치 화료의 탁자 위 짝, 다른 자리 손패(뒷면 낱장 줄)·울기(앞면, 라벨 없음).
검출 흉내: 누락 5%·중복 2%·좌표 지터·격자 추정 오차(이동·배율·작은 회전).
출력 = role_set.scene_tokens 과 같은 (x[N,9 또는 11], y[N]) — 라벨 -1 = 뒷면 또는 other.

보강(2026-11-05, 회전 상자 특징과 같이): 상자마다 기울기(줄 기울기 + 낱장 지터, 강의 비스듬히 버린 패 5~20°, 떼어 둔 패 최대 45°, 사진 전체 ±3°),
  손패 줄 끝에서 살짝 떨어진 2~4장(손패, 124654 유형), 안깡(앞면 2 + 양끝 뒷면 2 = 울기), 다른 자리 울기·짝에도 기울기.
  feat="old" 면 기운 패를 감싸는 축 상자 크기로(축 상자 검출기 흉내), "rot" 면 패에 맞는 크기 + sin·cos(2×기울기).

v2(2026-11-08, 사용자가 합성 그림의 겹침·누운 패·크기를 지적 → role_synth_audit.py 로 실제 25장과 비교해 고침). 예전 생성기는 ROLE_SYNTH_V1=1:
  - 강을 기기 중심 기준으로 돌림(예전엔 펠트 가운데 기준이라 기기 중심이 0.47 이면 옆 자리 강과 포개짐). 기기 중심은 실제처럼 0.5 ± 0.035(u·v 모두).
  - 패산 상자를 실제 뒷면 상자 모양으로(폭 = 패 폭 × 0.95~1.2, 10% 는 두 묶음이 붙은 1.5~1.7, 높이 = 패 폭 × 1.5~1.85 — 실제 아래 패산 폭 중앙 1.07·높이 1.69),
    패산 길이 1~14 묶음·펠트 0.05~0.95 안(실제 길이 최대 0.67).
  - 사진 전체 큰 회전(5~13°) 25% → 10%(실제 25장 중 1장), 작은 회전 σ 3° → 1.5°(5° 넘게 기운 앞면 실제 14%).
  - 기기를 정사각형으로(가로·세로를 따로 뽑으면 바람개비 강이 옆 자리와 포개짐).
  - 패산 위 표시패를 한 패산에만(v1 은 패산마다 60% 로 따로 넣어 평균 2.4곳 — 11-03 에 효과 없음으로 미채택한 보강이 코드에 남아 있었음).
    리치 아닌 화료 90%·리치 화료 30%(대개 탁자 위 짝으로 옮김) 장면에 넣고, 그중 20% 는 줄 끝에서 떨어진 왕패 조각 위, 깡 뒤 2장 40% 는 그대로.
  - 위치를 실제 25장 입력에 맞춤(role_synth_audit·실제 대 합성 그림 비교, 사용자 지적 "실제 입력과 많이 달라 보인다"): 기기 0.21 → 0.27(강 첫 줄 거리 0.13 → 실제 0.17),
    패산 v 0.88 → 0.96(격자 네모 안 뒷면 47% → 실제 24%), 다른 자리 손패·울기 0.08 바깥, 화료자 울기 u ≥ 1.0·v +0.1(실제 u 중앙 1.26·v 1.17),
    화료자 손패는 자기 패산 바깥, 리치 짝 v 0.89 → 0.93.
  - 네 자리 강을 먼저 놓고, 역할 없는 상자(패산·다른 자리 손패·울기)가 이미 놓인 상자와 겹치면(IoU>0.15) 버림.

  python -I -X utf8 experiments/tile_classifier/role_synth.py [--n 12] [--seed 0]   # data/role/synth_check/<k>.png 로 눈 확인
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROLES = ["hand", "meld", "river", "wall", "pair", "loose"]
R = {r: i for i, r in enumerate(ROLES)}
TW, TH = 0.048, 0.066  # 펠트 폭 기준 패 폭·높이(세운 모습)
V1 = os.environ.get("ROLE_SYNTH_V1") == "1"  # 2026-11-08 이전 생성기(pre_synth8k*.pt 를 만든 것)


def rot(u: float, v: float, k: int, cu: float = 0.5, cv: float = 0.5) -> tuple[float, float]:
    """(cu, cv) 기준 90°×k 회전(아래 자리 → 다른 자리). 기본은 펠트 가운데."""
    u, v = u - cu, v - cv
    for _ in range(k % 4):
        u, v = -v, u
    return u + cu, v + cv


def box_iou(a: tuple, b: tuple) -> float:
    """(u, v, w, h) 두 축 상자의 IoU."""
    ix = min(a[0] + a[2] / 2, b[0] + b[2] / 2) - max(a[0] - a[2] / 2, b[0] - b[2] / 2)
    iy = min(a[1] + a[3] / 2, b[1] + b[3] / 2) - max(a[1] - a[3] / 2, b[1] - b[3] / 2)
    if ix <= 0 or iy <= 0:
        return 0.0
    inter = ix * iy
    return inter / (a[2] * a[3] + b[2] * b[3] - inter)


class Scene:
    def __init__(self, rng: np.random.Generator, feat: str = "old"):
        self.rng = rng
        self.feat = feat
        self.items: list[tuple[float, float, float, float, bool, int, float]] = []  # u, v, w, h, back, label, tilt°
        s = rng.uniform(0.9, 1.12)
        self.tw, self.th = TW * s, TH * s

        self.center = (0.5, 0.5)  # v2: 강을 놓는 동안만 기기 중심
        self.wall0: float | None = None  # v2: 화료자 패산의 바깥 끝 v

    def add(self, u: float, v: float, w: float, h: float, back: bool, label: int, k: int = 0, tilt: float = 0.0) -> None:
        u, v = rot(u, v, k, *self.center)
        if k % 2:
            w, h = h, w
        if not V1 and label == -1 and any(box_iou((u, v, w, h), it[:4]) > 0.15 for it in self.items):
            return  # v2: 역할 없는 상자가 이미 놓인 것과 포개지면 버림
        self.items.append((u, v, w, h, back, label, tilt))  # 90° 회전은 기울기(−45~45 로 접은 값)를 바꾸지 않는다

    def row(self, u0: float, v: float, n: int, label: int, k: int = 0, back: bool = False, land: list[int] | None = None, gap: float = 1.0,
            tilt: float | None = None, backs_at: list[int] | None = None, back_label: int = -1) -> float:
        """왼쪽 u0 에서 오른쪽으로 n 장. 눕힌 장(land)은 폭·높이를 바꾼다. backs_at 의 장은 뒷면(안깡 양끝). 줄 기울기 tilt(없으면 작은 값) + 낱장 지터. 다음 u 를 돌려준다."""
        rng = self.rng
        u = u0
        rt = rng.normal(0, 1.0) if tilt is None else tilt
        for i in range(n):
            w, h = (self.th, self.tw) if land and i in land else (self.tw, self.th)
            is_back = back or bool(backs_at and i in backs_at)
            self.add(u + w / 2, v, w, h, is_back, back_label if is_back else label, k, rt + rng.normal(0, 0.7))
            u += w * gap * rng.uniform(1.0, 1.06)
        return u

    def tokens(self, su: float, sv: float) -> tuple[np.ndarray, np.ndarray]:
        import role_set as rs

        rng = self.rng
        rows, labels = [], []
        ang = rng.normal(0, 3.0 if V1 else 1.5) if rng.random() < (0.75 if V1 else 0.9) else rng.uniform(5, 13) * rng.choice([-1, 1])  # 사진 전체 회전(격자 오차·기운 거치, 매장 사진 5~13°), 기울기에도 더해진다
        shift = rng.normal(0, 0.012, 2)
        scale = rng.uniform(0.96, 1.04)
        ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        for u, v, w, h, back, label, tilt in self.items:
            if rng.random() < 0.05:  # 누락
                continue
            reps = 2 if rng.random() < 0.02 else 1  # 중복 검출
            for _ in range(reps):
                du, dv = u - 0.5, v - 0.5
                uu = 0.5 + (du * ca - dv * sa) * scale + shift[0] + rng.normal(0, 0.003)
                vv = 0.5 + (du * sa + dv * ca) * scale + shift[1] + rng.normal(0, 0.003)
                ww, hh = w * rng.uniform(0.9, 1.1), h * rng.uniform(0.9, 1.1)
                t = ((tilt + ang + rng.normal(0, 1.0) + 45) % 90) - 45
                if self.feat != "rot":
                    ww, hh = rs.axis_of(ww, hh, t)  # 축 상자 검출기는 기운 패를 감싼다
                rows.append(rs.feat_row(uu, vv, ww, hh, back, su, sv, t, self.feat))
                labels.append(label)
        return np.array(rows, np.float32).reshape(-1, rs.feat_dim(self.feat)), np.array(labels)


def make(rng: np.random.Generator, feat: str = "old") -> tuple[np.ndarray, np.ndarray]:
    sc = Scene(rng, feat)
    tw, th = sc.tw, sc.th
    if V1:
        su, sv = 0.5 + rng.normal(0, 0.02), 0.47 + rng.normal(0, 0.02)  # 리치봉 기기 중심
    else:
        su, sv = 0.5 + rng.normal(0, 0.035), 0.5 + rng.normal(0, 0.035)  # 실제 25장: 화료자 기준으로 돌린 기기 중심 0.45~0.55
    dw, dh = 0.21 * rng.uniform(0.9, 1.1), 0.21 * rng.uniform(0.9, 1.1)  # 기기는 펠트 폭의 약 1/5
    if not V1:
        # 기기는 정사각형 — 가로·세로가 다르면 바람개비 강이 옆 자리와 포개진다.
        # 크기는 실제 25장의 강 첫 줄 거리(기기 중심에서 체비쇼프 0.17, v1 은 0.13)에 맞춤 — 강 한 줄(6장)이 기기 한 변과 비슷해 바람개비가 반듯하다.
        dw = 0.27 * rng.uniform(0.94, 1.06)
        dh = dw * rng.uniform(0.97, 1.03)
    riichi_win = rng.random() < 0.35
    n_meld = rng.choice([0, 0, 0, 1, 1, 2, 3, 4], p=[0.3, 0.1, 0.1, 0.2, 0.1, 0.1, 0.07, 0.03])
    dora_seat, dora_loose = -1, False
    if not V1:
        # v2: 표시패는 왕패가 있는 패산 한 곳에만(어느 패산인지는 주사위로 정해짐). 리치 화료면 대개 도라·뒷도라를 탁자 위 짝으로 옮겨 패산엔 드묾.
        if rng.random() < (0.3 if riichi_win else 0.9):
            dora_seat = int(rng.integers(0, 4))
            dora_loose = rng.random() < 0.2  # 패산 줄 끝에서 떨어진 왕패 조각 위

    # 자리마다: 강·패산·(다른 자리) 손패 뒷면 줄·울기
    def river(k: int) -> None:
        # 강: 기기 아래부터 6장씩, 눕힌 리치패 가능. 아래 자리 기준으로 만들고 k 회전
        n_river = int(rng.integers(0, 22))
        if not V1:
            sc.center = (su, sv)  # 강은 기기 둘레에 바람개비로 — 기기 중심 기준으로 돌린다
        v = sv + dh / 2 + th * 0.55 + rng.normal(0, 0.01)
        left = su - dw / 2 + rng.normal(0, 0.015)  # 기기 왼쪽 끝에서 시작(네 자리가 바람개비)
        riichi_at = int(rng.integers(0, n_river)) if n_river and rng.random() < 0.3 else -1
        i = 0
        while i < n_river:
            n = min(6, n_river - i)
            if n_river - i > 6 and rng.random() < 0.3:
                n = int(rng.integers(6, min(9, n_river - i) + 1))  # 마지막 줄은 길어지기도
            land = [j for j in range(n) if i + j == riichi_at]
            u0 = sc.row(left, v, n, R["river"], k, land=land)
            if rng.random() < 0.25:  # 비스듬히 버린 패 하나(강 끝)
                sc.items.pop()
                tl = rng.uniform(5, 20) * rng.choice([-1, 1])
                sc.add(u0 - tw * rng.uniform(0.4, 0.7), v + rng.normal(0, 0.006), tw, th, False, R["river"], k, tl)
            v += th * rng.uniform(1.0, 1.08)
            i += n
        sc.center = (0.5, 0.5)

    def rest(k: int) -> None:
        # 패산: 자리 앞 뒷면 상자 줄(한 겹 또는 두 겹 쌓인 묶음 = 상자 하나), 빠진 구간·왕패 표시패
        wv = (0.88 if V1 else 0.96) + rng.normal(0, 0.04 if V1 else 0.03)  # 패산은 펠트 가장자리 가까이(v2: 실제 뒷면 기기에서 거리 중앙 0.60·표시패 0.47, 격자 네모 안 뒷면 24%)
        if V1:
            n_wall = int(rng.integers(4, 18))
            wl = 0.5 - n_wall * tw / 2 + rng.normal(0, 0.05)
            bw, bh = tw * rng.uniform(1.0, 1.35), th * rng.uniform(0.75, 0.95)
        else:
            n_wall = int(rng.integers(1, 15))
            bw, bh = tw * rng.uniform(0.95, 1.2), tw * rng.uniform(1.5, 1.85)
            wl = float(np.clip(0.5 - n_wall * bw / 2 + rng.normal(0, 0.08), 0.05, max(0.05, 0.95 - n_wall * bw * 1.05)))
        if k == 0 and not V1:
            sc.wall0 = wv + bh / 2
        gap_at = int(rng.integers(0, n_wall)) if rng.random() < 0.5 else -1
        if V1:
            dora_at = int(rng.integers(0, n_wall)) if rng.random() < 0.6 else -1  # 보강: 0.35 → 0.6 (패산마다 따로 — 여러 패산에 동시에 생김)
        else:
            dora_at = int(rng.integers(0, n_wall)) if k == dora_seat and not dora_loose else -1
        u = wl
        for j in range(n_wall):
            if j == gap_at:
                u += tw * rng.uniform(1, 4)
            wj = bw
            if not V1 and rng.random() < 0.1:
                wj = tw * rng.uniform(1.5, 1.7)  # 두 묶음이 붙어 한 상자로 잡힘
            if j == dora_at:
                sc.add(u + wj / 2, wv, tw, th, False, R["wall"], k)
                if rng.random() < 0.4:  # 깡 뒤 표시패 2장
                    u += wj * 1.03
                    sc.add(u + wj / 2, wv, tw, th, False, R["wall"], k)
            else:
                sc.add(u + wj / 2, wv, wj, bh, True, -1, k)
            u += wj * rng.uniform(1.0, 1.05)
        if (rng.random() < 0.15) if V1 else (k == dora_seat and dora_loose):  # 패산 줄 끝에서 조금 떨어진 표시패(왕패 조각)
            sc.add(u + tw * rng.uniform(0.5, 2.5), wv + rng.normal(0, 0.01), tw, th, False, R["wall"], k)
        if k:
            # 다른 자리 손패: 세운 뒷면 낱장 줄(자리 밖 v≈1.05)
            n = int(rng.integers(8, 15))
            out = 0.0 if V1 else 0.08  # v2: 다른 자리 손패·울기를 실제처럼 더 바깥에(화료자 울기 실제 u 중앙 1.26·v 1.17)
            sc.row(0.5 - n * tw / 2 + rng.normal(0, 0.1), 1.0 + out + rng.uniform(0.0, 0.15), n, -1, k, back=True)
            # 다른 자리 울기(앞면, other) — 안깡(앞면 2 + 양끝 뒷면)도
            if rng.random() < 0.35:
                u = 0.85 + 2 * out + rng.uniform(0, 0.4)
                for _ in range(int(rng.integers(1, 3))):
                    if rng.random() < 0.2:
                        u = sc.row(u, 1.0 + out + rng.uniform(0.05, 0.25), 4, -1, k, backs_at=[0, 3]) + tw * rng.uniform(0.3, 1.0)
                    else:
                        m = int(rng.choice([3, 3, 4]))
                        u = sc.row(u, 1.0 + out + rng.uniform(0.05, 0.25), m, -1, k, land=[int(rng.integers(0, m))]) + tw * rng.uniform(0.3, 1.0)
            if rng.random() < 0.15:  # 다른 자리 떼어 둔 패·2장
                sc.row(rng.uniform(0.2, 0.9), 1.0 + out + rng.uniform(0.0, 0.2), int(rng.integers(1, 3)), -1, k)

    if V1:
        for k in range(4):
            river(k)
            rest(k)
    else:  # v2: 네 자리 강을 먼저 — 뒤 자리 강이 앞 자리 패산 위에 포개지지 않게(패산·남의 패가 강과 겹치면 버려짐)
        for k in range(4):
            river(k)
        for k in range(4):
            rest(k)

    # 화료자(아래) 손패 줄
    n_hand = (14 if rng.random() < 0.5 else 13) - 3 * n_meld
    hv = 1.05 + rng.normal(0, 0.05)
    if not V1 and sc.wall0 is not None:
        hv = max(hv, sc.wall0 + th * 0.5 + 0.005)  # v2: 화료자 손패는 자기 패산 앞(바깥)에
    hu = 0.46 - n_hand * tw / 2 + rng.normal(0, 0.1)
    loose = rng.random() < 0.55  # 화료패 떼어 둠(보강: 0.3 → 0.55)
    if loose:
        n_hand -= 1
    hand_tilt = rng.normal(0, 1.5)
    if rng.random() < 0.3 and n_hand >= 6:  # 두 덩이
        a = int(rng.integers(3, n_hand - 2))
        u = sc.row(hu, hv, a, R["hand"], tilt=hand_tilt)
        sc.row(u + tw * rng.uniform(0.5, 2.5), hv + rng.normal(0, 0.01), n_hand - a, R["hand"], tilt=hand_tilt)
    elif rng.random() < 0.4 and n_hand >= 6:  # 보강 3: 줄 끝(오른쪽 또는 왼쪽)에서 살짝 떨어진 2~4장 — 손패(124654 유형, 울기가 아니다)
        m = int(rng.integers(2, 5))
        g = tw * rng.uniform(0.3, 1.5)
        if rng.random() < 0.7:
            u = sc.row(hu, hv, n_hand - m, R["hand"], tilt=hand_tilt)
            sc.row(u + g, hv + rng.normal(0, 0.008), m, R["hand"], tilt=hand_tilt)
        else:
            u = sc.row(hu, hv, m, R["hand"], tilt=hand_tilt)
            sc.row(u + g, hv + rng.normal(0, 0.008), n_hand - m, R["hand"], tilt=hand_tilt)
    else:
        if rng.random() < 0.35:  # 보강 2: 줄 안에 작은 틈 한두 개(패 0.2~0.6개) — 실제 손패 줄 끝 2장이 살짝 떨어진 경우
            u, left = hu, n_hand
            while left > 0:
                m = left if rng.random() < 0.5 else int(rng.integers(1, left + 1))
                u = sc.row(u, hv, m, R["hand"], gap=rng.uniform(1.0, 1.1), tilt=hand_tilt) + tw * rng.uniform(0.2, 0.6)
                left -= m
        else:
            sc.row(hu, hv, n_hand, R["hand"], gap=rng.uniform(1.0, 1.15), tilt=hand_tilt)
    end = hu + n_hand * tw * 1.1
    if loose:
        side = rng.random()
        if side < 0.6:  # 줄 오른쪽
            lu, lv = end + tw * rng.uniform(0.6, 4), hv + rng.normal(0, 0.04)
        elif side < 0.8:  # 줄 왼쪽
            lu, lv = hu - tw * rng.uniform(0.8, 3), hv + rng.normal(0, 0.04)
        else:  # 줄 앞(탁자 쪽)
            lu, lv = rng.uniform(hu, end), hv - th * rng.uniform(0.8, 1.6)
        lw, lh = (th, tw) if rng.random() < 0.15 else (tw, th)
        sc.add(lu, lv, lw, lh, False, R["loose"], tilt=rng.uniform(-45, 45) if rng.random() < 0.5 else rng.normal(0, 3))  # 떼어 둔 패는 기울기 제각각(183627 36°)
    # 울기: 손패 오른쪽 — 안깡(앞면 2 + 양끝 뒷면 2)도 울기
    u = max(end, 0.72 if V1 else 1.0) + tw * rng.uniform(0.5, 3)  # v2: 실제 화료자 울기 u 1.14~1.49(중앙 1.26)
    mv = 0.0 if V1 else 0.1  # v2: 실제 울기 v 중앙 1.17(손패 1.05)
    for _ in range(n_meld):
        if rng.random() < 0.15:
            u = sc.row(u, hv + mv + rng.normal(0, 0.1), 4, R["meld"], backs_at=[0, 3]) + tw * rng.uniform(0.3, 1.2)
            continue
        m = int(rng.choice([3, 3, 3, 4]))
        u = sc.row(u, hv + mv + rng.normal(0, 0.1), m, R["meld"], land=[int(rng.integers(0, m))] if rng.random() < 0.7 else None) + tw * rng.uniform(0.3, 1.2)  # 보강 2: 눕힌 패 없는 울기 15% → 30%
    # 리치 화료의 탁자 위 표시패 짝
    if riichi_win:
        sc.row(rng.uniform(0.25, 0.8), (0.89 if V1 else 0.93) + rng.normal(0, 0.06), 2, R["pair"], tilt=rng.normal(0, 4))  # 패산이 빠진 자리나 그 앞
    return sc.tokens(su, sv)


def dataset(n: int, seed: int, feat: str = "old") -> list[dict]:
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        x, y = make(rng, feat)
        out.append(dict(name=f"synth{i}", x=x, y=list(y), n_face=len(x)))
    return out


def draw(x: np.ndarray, y: np.ndarray, path: Path) -> None:
    from PIL import Image, ImageDraw

    S = 900
    im = Image.new("RGB", (S, S), (20, 90, 50))
    d = ImageDraw.Draw(im)
    o = 150
    d.rectangle((o, o, o + 600, o + 600), outline="black")
    col = {0: "blue", 1: "cyan", 2: "orange", 3: "red", 4: "magenta", 5: "yellow", -1: "gray"}
    for row, lab in zip(x, y):
        u, v, w, h = row[0], row[1], row[2] / 10, row[3] / 10
        c = (200, 200, 230) if row[4] else "white"
        if len(row) > 9:  # 회전 상자 특징이면 기운 사각형으로
            t = math.atan2(row[9], row[10]) / 2
            cs, sn = math.cos(t), math.sin(t)
            pts = [(o + (u + dx * cs - dy * sn) * 600, o + (v + dx * sn + dy * cs) * 600) for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))]
            d.polygon(pts, fill=c, outline=col[int(lab)], width=2)
        else:
            d.rectangle((o + (u - w / 2) * 600, o + (v - h / 2) * 600, o + (u + w / 2) * 600, o + (v + h / 2) * 600), fill=c, outline=col[int(lab)], width=2)
    im.save(path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--feat", default="rot", choices=["old", "rot"])
    a = ap.parse_args()
    out = HERE / "data" / "role" / "synth_check"
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(a.seed)
    for i in range(a.n):
        x, y = make(rng, a.feat)
        draw(x, y, out / f"{i}.png")
    print("저장", out)
