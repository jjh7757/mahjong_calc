"""합성 탁자 배치 생성기(2026-11-03). role_set.py 가 학습 전 사전학습에 쓴다.

실제 25장(표 1-57)의 분포에 맞춰 펠트 기준 0~1 좌표로 상자를 놓는다(화료자 = 아래 자리). 패 폭 약 0.048·높이 0.066.
놓는 것: 화료자 손패 줄(13~14장 − 울기, 두 덩이로 갈라짐·화료패 떼어 둠 포함), 울기 0~4(치·퐁 3, 깡 4, 눕힌 1장), 네 자리 강(6장 줄·눕힌 리치패),
패산(뒷면 상자, 줄마다 빠진 구간·왕패)과 패산 위 표시패(앞면 낱장), 리치 화료의 탁자 위 짝, 다른 자리 손패(뒷면 낱장 줄)·울기(앞면, 라벨 없음).
검출 흉내: 누락 5%·중복 2%·좌표 지터·격자 추정 오차(이동·배율·작은 회전).
출력 = role_set.scene_tokens 과 같은 (x[N,9], y[N]) — 라벨 -1 = 뒷면 또는 other.

  python -I -X utf8 experiments/tile_classifier/role_synth.py [--n 12] [--seed 0]   # data/role/synth_check/<k>.png 로 눈 확인
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROLES = ["hand", "meld", "river", "wall", "pair", "loose"]
R = {r: i for i, r in enumerate(ROLES)}
TW, TH = 0.048, 0.066  # 펠트 폭 기준 패 폭·높이(세운 모습)


def rot(u: float, v: float, k: int) -> tuple[float, float]:
    """펠트 가운데 기준 90°×k 회전(아래 자리 → 다른 자리)."""
    for _ in range(k % 4):
        u, v = 1 - v, u
    return u, v


class Scene:
    def __init__(self, rng: np.random.Generator):
        self.rng = rng
        self.items: list[tuple[float, float, float, float, bool, int]] = []  # u, v, w, h, back, label
        s = rng.uniform(0.9, 1.12)
        self.tw, self.th = TW * s, TH * s

    def add(self, u: float, v: float, w: float, h: float, back: bool, label: int, k: int = 0) -> None:
        u, v = rot(u, v, k)
        if k % 2:
            w, h = h, w
        self.items.append((u, v, w, h, back, label))

    def row(self, u0: float, v: float, n: int, label: int, k: int = 0, back: bool = False, land: list[int] | None = None, gap: float = 1.0) -> float:
        """왼쪽 u0 에서 오른쪽으로 n 장. 눕힌 장(land)은 폭·높이를 바꾼다. 다음 u 를 돌려준다."""
        u = u0
        for i in range(n):
            w, h = (self.th, self.tw) if land and i in land else (self.tw, self.th)
            self.add(u + w / 2, v, w, h, back, label, k)
            u += w * gap * self.rng.uniform(1.0, 1.06)
        return u

    def tokens(self, su: float, sv: float) -> tuple[np.ndarray, np.ndarray]:
        rng = self.rng
        rows, labels = [], []
        ang = math.radians(rng.normal(0, 1.5))
        shift = rng.normal(0, 0.012, 2)
        scale = rng.uniform(0.96, 1.04)
        for u, v, w, h, back, label in self.items:
            if rng.random() < 0.05:  # 누락
                continue
            reps = 2 if rng.random() < 0.02 else 1  # 중복 검출
            for _ in range(reps):
                du, dv = u - 0.5, v - 0.5
                uu = 0.5 + (du * math.cos(ang) - dv * math.sin(ang)) * scale + shift[0] + rng.normal(0, 0.003)
                vv = 0.5 + (du * math.sin(ang) + dv * math.cos(ang)) * scale + shift[1] + rng.normal(0, 0.003)
                ww, hh = w * rng.uniform(0.9, 1.1), h * rng.uniform(0.9, 1.1)
                rows.append([uu, vv, ww * 10, hh * 10, float(back), float(ww > hh * 1.15), uu - su, vv - sv, 1.0])
                labels.append(label)
        return np.array(rows, np.float32), np.array(labels)


def make(rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    sc = Scene(rng)
    tw, th = sc.tw, sc.th
    su, sv = 0.5 + rng.normal(0, 0.02), 0.47 + rng.normal(0, 0.02)  # 리치봉 기기 중심
    dw, dh = 0.21 * rng.uniform(0.9, 1.1), 0.21 * rng.uniform(0.9, 1.1)  # 기기는 펠트 폭의 약 1/5
    riichi_win = rng.random() < 0.35
    n_meld = rng.choice([0, 0, 0, 1, 1, 2, 3, 4], p=[0.3, 0.1, 0.1, 0.2, 0.1, 0.1, 0.07, 0.03])

    # 자리마다: 강·패산·(다른 자리) 손패 뒷면 줄·울기
    for k in range(4):
        # 강: 기기 아래부터 6장씩, 눕힌 리치패 가능. 아래 자리 기준으로 만들고 k 회전
        n_river = int(rng.integers(0, 22))
        v = sv + dh / 2 + th * 0.55 + rng.normal(0, 0.01)
        left = su - dw / 2 + rng.normal(0, 0.015)  # 기기 왼쪽 끝에서 시작(네 자리가 바람개비)
        riichi_at = int(rng.integers(0, n_river)) if n_river and rng.random() < 0.3 else -1
        i = 0
        while i < n_river:
            n = min(6, n_river - i)
            if n_river - i > 6 and rng.random() < 0.3:
                n = int(rng.integers(6, min(9, n_river - i) + 1))  # 마지막 줄은 길어지기도
            land = [j for j in range(n) if i + j == riichi_at]
            sc.row(left, v, n, R["river"], k, land=land)
            v += th * rng.uniform(1.0, 1.08)
            i += n
        # 패산: 자리 앞 뒷면 상자 줄(한 겹 또는 두 겹 쌓인 묶음 = 상자 하나), 빠진 구간·왕패 표시패
        wv = 0.88 + rng.normal(0, 0.04)  # 패산은 펠트 가장자리 가까이
        n_wall = int(rng.integers(4, 18))
        wl = 0.5 - n_wall * tw / 2 + rng.normal(0, 0.05)
        bw, bh = tw * rng.uniform(1.0, 1.35), th * rng.uniform(0.75, 0.95)
        gap_at = int(rng.integers(0, n_wall)) if rng.random() < 0.5 else -1
        dora_at = int(rng.integers(0, n_wall)) if rng.random() < 0.6 else -1  # 보강: 0.35 → 0.6
        u = wl
        for j in range(n_wall):
            if j == gap_at:
                u += tw * rng.uniform(1, 4)
            if j == dora_at:
                sc.add(u + bw / 2, wv, tw, th, False, R["wall"], k)
                if rng.random() < 0.4:  # 깡 뒤 표시패 2장
                    u += bw * 1.03
                    sc.add(u + bw / 2, wv, tw, th, False, R["wall"], k)
            else:
                sc.add(u + bw / 2, wv, bw, bh, True, -1, k)
            u += bw * rng.uniform(1.0, 1.05)
        if rng.random() < 0.15:  # 보강: 패산 줄 끝에서 조금 떨어진 표시패(왕패 조각)
            sc.add(u + tw * rng.uniform(0.5, 2.5), wv + rng.normal(0, 0.01), tw, th, False, R["wall"], k)
        if k:
            # 다른 자리 손패: 세운 뒷면 낱장 줄(자리 밖 v≈1.05)
            n = int(rng.integers(8, 15))
            sc.row(0.5 - n * tw / 2 + rng.normal(0, 0.1), 1.0 + rng.uniform(0.0, 0.15), n, -1, k, back=True)
            # 다른 자리 울기(앞면, other)
            if rng.random() < 0.35:
                u = 0.85 + rng.uniform(0, 0.4)
                for _ in range(int(rng.integers(1, 3))):
                    m = int(rng.choice([3, 3, 4]))
                    u = sc.row(u, 1.0 + rng.uniform(0.05, 0.25), m, -1, k, land=[int(rng.integers(0, m))]) + tw * rng.uniform(0.3, 1.0)
            if rng.random() < 0.15:  # 다른 자리 떼어 둔 패·2장
                sc.row(rng.uniform(0.2, 0.9), 1.0 + rng.uniform(0.0, 0.2), int(rng.integers(1, 3)), -1, k)

    # 화료자(아래) 손패 줄
    n_hand = (14 if rng.random() < 0.5 else 13) - 3 * n_meld
    hv = 1.05 + rng.normal(0, 0.05)
    hu = 0.46 - n_hand * tw / 2 + rng.normal(0, 0.1)
    loose = rng.random() < 0.55  # 화료패 떼어 둠(보강: 0.3 → 0.55)
    if loose:
        n_hand -= 1
    if rng.random() < 0.3 and n_hand >= 6:  # 두 덩이
        a = int(rng.integers(3, n_hand - 2))
        u = sc.row(hu, hv, a, R["hand"])
        sc.row(u + tw * rng.uniform(0.5, 2.5), hv + rng.normal(0, 0.01), n_hand - a, R["hand"])
    else:
        if rng.random() < 0.35:  # 보강 2: 줄 안에 작은 틈 한두 개(패 0.2~0.6개) — 실제 손패 줄 끝 2장이 살짝 떨어진 경우
            u, left = hu, n_hand
            while left > 0:
                m = left if rng.random() < 0.5 else int(rng.integers(1, left + 1))
                u = sc.row(u, hv, m, R["hand"], gap=rng.uniform(1.0, 1.1)) + tw * rng.uniform(0.2, 0.6)
                left -= m
        else:
            sc.row(hu, hv, n_hand, R["hand"], gap=rng.uniform(1.0, 1.15))
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
        sc.add(lu, lv, lw, lh, False, R["loose"])
    # 울기: 손패 오른쪽
    u = max(end, 0.72) + tw * rng.uniform(0.5, 3)
    for _ in range(n_meld):
        m = int(rng.choice([3, 3, 3, 4]))
        u = sc.row(u, hv + rng.normal(0, 0.1), m, R["meld"], land=[int(rng.integers(0, m))] if rng.random() < 0.7 else None) + tw * rng.uniform(0.3, 1.2)  # 보강 2: 눕힌 패 없는 울기 15% → 30%
    # 리치 화료의 탁자 위 표시패 짝
    if riichi_win:
        sc.row(rng.uniform(0.25, 0.8), 0.89 + rng.normal(0, 0.06), 2, R["pair"])  # 패산이 빠진 자리나 그 앞
    return sc.tokens(su, sv)


def dataset(n: int, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        x, y = make(rng)
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
        d.rectangle((o + (u - w / 2) * 600, o + (v - h / 2) * 600, o + (u + w / 2) * 600, o + (v + h / 2) * 600), fill=c, outline=col[int(lab)], width=2)
    im.save(path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    out = HERE / "data" / "role" / "synth_check"
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(a.seed)
    for i in range(a.n):
        x, y = make(rng)
        draw(x, y, out / f"{i}.png")
    print("저장", out)
