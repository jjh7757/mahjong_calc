"""합성 탁자 배치 생성기 v3(2026-11-08). role_synth.py(v1·v2)를 고치지 않고 따로 둔다 — v2 사전학습 파일을 다시 만들 수 있게.

사용자 규칙(11-08, v2 예시 그림을 보고):
  1. 강은 사람마다 울기 횟수에 따라 장수가 달라도 3~4장 차이 → 판마다 기준 장수 하나 + 사람마다 −2~+2.
  2. 같은 사람의 울기는 완전히 떨어져 있지 않고 어느 정도 붙어 있다 → 손패 오른쪽에 한 줄로 이어 놓거나, 모서리에서 위로 쌓은 덩어리.
  3. 패산은 처음 네모(ㄷ자)였다가 한 방향으로 없어진다 — 중간만 빠지지 않는다 → 남은 패산은 고리 위 한 덩어리(호).
v2 예시에서 Claude 가 짚은 것도 같이: 손패 줄 중간 틈 없앰(끝 2~4장 살짝 떨어짐만 15%), 짝은 패산 위가 아니라 빈 펠트에, 다른 사람 울기도 meld(v2 라벨 결정).

배치(화료자 = 아래, 기기 중심 (su, sv) 기준. 거리는 기기 중심에서 체비쇼프 — 실제 33장(연출 뺌) 입력에서 잼):
  강 첫 줄 0.17~0.21 · 패산 0.42~0.50 · 화료자 손패 0.55~0.62 · 다른 자리 세운 손패(뒷면) 0.68~0.72 · 울기 0.72~0.80.
패산 = 시계 방향 68칸 고리(자리마다 17묶음). 주사위 자리 b, 왕패 = b 앞 7묶음, 표시패 = b 에서 3번째 묶음(깡이면 4·5번째에 더).
  실제 사진 11장 중 7장에서 표시패가 남은 패산 호의 시계 방향 끝에서 3번째(깡이면 3·4번째)였다 → 뽑기는 b 부터 시계 방향.
  뽑힌 묶음 = 배패 26 + (강 합계 + 깡)/2 → 남은 호 = 그다음 칸부터 b−1 까지(왕패 포함). 강 장수와 패산 길이가 같이 움직인다.
리치 화료면 85% 는 표시패(+깡 표시패)와 뒷도라를 화료자 쪽 펠트에 짝으로(매장 습관), 15% 는 패산에 그대로·뒷도라 없음(165614 처럼).

  python -I -X utf8 experiments/tile_classifier/role_synth_v3.py [--n 8] [--seed 123]   # v2/synth_v3_samples.jpg (실제 4장 + v3)
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
SIDE = 17  # 자리마다 패산 묶음 수
LAST: dict = {}  # 마지막 장면의 깡·떼어 둔 패(예시 그림 제목용)
DROP_SAFE = __import__("os").environ.get("ROLE_DROP_SAFE") == "1"  # 표 1-136
OTHER_NEG = __import__("os").environ.get("ROLE_OTHER_NEG") == "1"  # 표 1-138: 외톨이 앞면(-2) 넣기
ROT = __import__("os").environ.get("ROLE_SYNTH_V3_ROT", "base")  # "15" = 사진 전체 회전 ±15° 까지 35%(표 1-132), 기본 = 실제 비율(큰 회전 4%)


def box_iou(a, b) -> float:
    ix = min(a[0] + a[2] / 2, b[0] + b[2] / 2) - max(a[0] - a[2] / 2, b[0] - b[2] / 2)
    iy = min(a[1] + a[3] / 2, b[1] + b[3] / 2) - max(a[1] - a[3] / 2, b[1] - b[3] / 2)
    if ix <= 0 or iy <= 0:
        return 0.0
    i = ix * iy
    return i / (a[2] * a[3] + b[2] * b[3] - i)


class Scene:
    """자리 좌표(아래 자리 기준: x = 기기 중심에서 오른쪽, d = 기기 중심에서 아래 거리)로 놓고 k×90° 돌려 펠트 좌표로."""

    def __init__(self, rng: np.random.Generator, feat: str):
        self.rng, self.feat = rng, feat
        self.tw = 0.050 * rng.uniform(0.94, 1.08)  # 실제 앞면 폭 중앙 0.0535(상자 지터 ±10% 포함)
        self.th = self.tw * rng.uniform(1.32, 1.42)
        self.su, self.sv = 0.5 + rng.normal(0, 0.03), 0.5 + rng.normal(0, 0.03)
        self.items: list[list] = []  # u, v, w, h, back, label, tilt
        self.kan: set[int] = set()  # 깡 묶음 상자 번호(그림용)

    def to_felt(self, x: float, d: float, k: int) -> tuple[float, float]:
        for _ in range(k % 4):  # 아래 → 오른쪽 → 위 → 왼쪽(시계 반대로 90°씩: (x, d) → (d, −x))
            x, d = d, -x
        return self.su + x, self.sv + d

    def put(self, x: float, d: float, w: float, h: float, back: bool, label: int, k: int, tilt: float = 0.0, force: bool = False) -> bool:
        u, v = self.to_felt(x, d, k)
        if k % 2:
            w, h = h, w
        if not force and any(box_iou((u, v, w, h), it[:4]) > 0.15 for it in self.items):
            return False
        self.items.append([u, v, w, h, back, label, tilt])
        return True

    def row(self, x0: float, d: float, n: int, label: int, k: int, land=(), backs_at=(), tilt: float | None = None, gap=(1.0, 1.03), force=False) -> float:
        """x0 에서 오른쪽으로 n 장(자리 좌표). 다음 x 를 돌려준다."""
        rng = self.rng
        rt = rng.normal(0, 1.0) if tilt is None else tilt
        x = x0
        for i in range(n):
            w, h = (self.th, self.tw) if i in land else (self.tw, self.th)
            back = i in backs_at
            dd = d + (self.th - self.tw) / 2 if i in land else d  # 눕힌 패는 줄 바깥쪽 선에 맞춤
            self.put(x + w / 2, dd, w, h, back, -1 if back else label, k, rt + rng.normal(0, 0.7), force)
            x += w * rng.uniform(*gap)
        return x

    def tokens(self) -> tuple[np.ndarray, np.ndarray]:
        import role_set as rs

        rng = self.rng
        if ROT == "15":  # 2026-11-09 사용자 "±15° 정도만 넣어서": 65% 는 실제처럼 σ1.5°, 35% 는 3~15° (회귀 ±10° 를 덮고 ±25° 는 안 넣음)
            ang = rng.normal(0, 1.5) if rng.random() < 0.65 else rng.uniform(3, 15) * rng.choice([-1, 1])
        else:
            ang = rng.normal(0, 1.5) if rng.random() < 0.96 else rng.uniform(5, 13) * rng.choice([-1, 1])  # 큰 회전 4%(실제 25장 중 1장)
        shift, scale = rng.normal(0, 0.012, 2), rng.uniform(0.96, 1.04)
        ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        T = lambda u, v: (0.5 + ((u - 0.5) * ca - (v - 0.5) * sa) * scale + shift[0], 0.5 + ((u - 0.5) * sa + (v - 0.5) * ca) * scale + shift[1])
        su, sv = T(self.su, self.sv)
        rows, labels = [], []
        self.kanmask = []
        for idx, (u, v, w, h, back, label, tilt) in enumerate(self.items):
            if DROP_SAFE and not (back or label == R["river"]):  # 2026-11-09 사용자: 손패·울기·떼어 둔 패·표시패·짝은 누락시키지 않음(표 1-136)
                pass
            elif rng.random() < (0.02 if label in (0, 1, 5) else 0.05):  # 검출 누락(손패·울기·떼어 둔 패는 잘 잡혀 2%)
                continue
            parts = [(u, v, w)]
            if not back and rng.random() < 0.03:  # 반쪽 상자 둘(검출기가 강 패·짝을 반쪽으로 잡던 증상)
                parts = [(u - w / 4, v, w / 2), (u + w / 4, v, w / 2)]
            elif rng.random() < 0.02:  # 중복 검출
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
                self.kanmask.append(idx in self.kan)
        return np.array(rows, np.float32).reshape(-1, rs.feat_dim(self.feat)), np.array(labels)


def melds(sc: Scene, x0: float, d0: float, k: int, plan: list[str]) -> None:
    """한 사람의 울기를 붙여서: 한 줄로 이어(50%) 또는 모서리에서 위로 쌓은 덩어리(50%).
    plan 항목 = 'pon'|'chi'|'kan'(명깡: 앞면 4, 1장 눕힘)|'kakan'(가깡: 퐁 3 + 눕힌 패 안쪽에 눕힌 1장 더)|'ankan'(안깡: 뒷면-앞면-앞면-뒷면, 매장 165614·181209)."""
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
        if stack and j > 0:  # 앞 울기 위(탁자 안쪽)로 한 줄 쌓기, 오른쪽 끝을 맞춤
            d -= sc.th * rng.uniform(1.02, 1.12)
            x = x_end - n * sc.tw * 1.02 - (sc.th - sc.tw if land else 0) + rng.normal(0, 0.15 * sc.tw)
        x_start = x
        dm = d + rng.normal(0, 0.15 * sc.tw)
        i0 = len(sc.items)
        x_end_new = sc.row(x, dm, n, R["meld"], k, land=land, backs_at=backs, force=True)
        if m in ("kan", "kakan", "ankan"):
            sc.kan.update(range(i0, len(sc.items) + (1 if m == "kakan" else 0)))
        if m == "kakan":  # 더한 1장: 눕힌 패의 탁자 안쪽(d −)에 눕혀 붙임
            it = sc.items[-n + land[0]]
            uu, vv = it[0], it[1]
            # 펠트 좌표의 자리 안쪽 방향 = 자리 k 의 −d
            du, dv = [(0, -1), (-1, 0), (0, 1), (1, 0)][k % 4]
            w, h = it[2], it[3]
            step = (h if k % 2 == 0 else w) * rng.uniform(1.0, 1.06)
            sc.items.append([uu + du * step, vv + dv * step, w, h, False, R["meld"], it[6] + rng.normal(0, 1.0)])
        if not stack or j == 0:
            x_end = x_end_new
        x = x_end_new + sc.tw * rng.uniform(0.1, 0.6)  # 한 줄: 다음 울기와 틈 조금
        _ = x_start


def make(rng: np.random.Generator, feat: str = "rot") -> tuple[np.ndarray, np.ndarray]:
    sc = Scene(rng, feat)
    tw, th = sc.tw, sc.th
    riichi_win = rng.random() < 0.4
    # 깡: 탁자 위 깡 수(누구 것이든)
    n_kan = int(rng.choice([0, 1, 2, 3], p=[0.70, 0.22, 0.07, 0.01]))  # 사용자 "깡도 어느정도 학습" — 장면 30% 에 깡(실제 33장 중 2장보다 많게)
    # 울기 계획: 자리 0 = 화료자
    plans: list[list[str]] = []
    for k in range(4):
        if k == 0:
            n = 0 if riichi_win else int(rng.choice([0, 1, 2, 3, 4], p=[0.4, 0.25, 0.2, 0.12, 0.03]))
        else:
            n = int(rng.choice([0, 1, 2, 3, 4], p=[0.55, 0.25, 0.13, 0.06, 0.01]))
        plans.append([str(rng.choice(["pon", "chi"])) for _ in range(n)])
    for _ in range(n_kan):  # 깡을 누군가의 울기로(리치 화료자는 안깡만)
        k = int(rng.integers(0, 4))
        kind = "ankan" if (k == 0 and riichi_win) else str(rng.choice(["ankan", "kan", "kakan"], p=[0.4, 0.3, 0.3]))
        if kind != "ankan" and plans[k] and rng.random() < 0.6:
            plans[k][int(rng.integers(0, len(plans[k])))] = kind
        else:
            plans[k].append(kind)
    plans = [p[:4] for p in plans]
    LAST.clear()
    LAST["kan"] = [f"{'화료자' if k == 0 else '자리' + str(k)} {m}" for k, p in enumerate(plans) for m in p if m in ("kan", "kakan", "ankan")]

    # 1) 강: 기준 장수 + 사람마다 −2~+2(사용자: 3~4장 차이)
    base = int(rng.integers(5, 19))
    dw = 0.27 * rng.uniform(0.94, 1.06)  # 기기 한 변
    rivers = [max(0, base + int(rng.integers(-2, 3))) for _ in range(4)]
    for k in range(4):
        n_r = rivers[k]
        d = dw / 2 + th * 0.55 + rng.normal(0, 0.008)
        left = -dw / 2 + rng.normal(0, 0.012)
        riichi_at = int(rng.integers(0, n_r)) if n_r and (riichi_win if k == 0 else rng.random() < 0.2) else -1
        i = 0
        while i < n_r:
            n = min(6, n_r - i)
            if i >= 12 and n_r - i > 6:
                n = n_r - i  # 셋째 줄부터는 길어짐
            land = tuple(j for j in range(n) if i + j == riichi_at)
            x = sc.row(left, d, n, R["river"], k, land=land, force=True)
            if rng.random() < 0.2:  # 비스듬히 버린 마지막 패
                it = sc.items[-1]
                it[6] = rng.uniform(5, 20) * rng.choice([-1, 1])
            d += th * rng.uniform(1.0, 1.06)
            i += n
        _ = x

    # 2) 패산 고리(시계 방향 68칸). 화면 시계 방향 = 아래 자리 오른쪽→왼쪽 → 왼쪽 자리 아래→위 → 위 자리 왼쪽→오른쪽 → 오른쪽 자리 위→아래.
    #    자리 k(아래 0·오른쪽 1·위 2·왼쪽 3) 의 줄을 자리 좌표 오른쪽→왼쪽(= 화면 시계 방향)으로 17칸.
    seat_cw = [0, 3, 2, 1]  # 고리 순서: 아래 → 왼쪽 → 위 → 오른쪽
    dW = rng.uniform(0.42, 0.48)
    bw = tw * rng.uniform(0.98, 1.08)
    bh = tw * rng.uniform(1.5, 1.8)
    side_d = {k: dW + rng.normal(0, 0.012) for k in range(4)}
    side_off = {k: rng.normal(0, 0.02) for k in range(4)}
    side_tilt = {k: rng.normal(0, 1.2) for k in range(4)}

    def slot_pos(s: int) -> tuple[int, float, float]:
        k = seat_cw[(s // SIDE) % 4]
        j = s % SIDE
        x = side_off[k] + (SIDE / 2 - j - 0.5) * bw * 1.02  # 오른쪽(j=0)에서 왼쪽으로
        return k, x, side_d[k]

    b = int(rng.integers(0, 4 * SIDE))
    total_river = sum(rivers)
    drawn = 26 + int(math.ceil((total_river + n_kan) / 2))
    remain_live = max(0, 61 - drawn)
    arc = [(b + 61 - remain_live + i) % (4 * SIDE) for i in range(remain_live + 7)]  # 남은 산 → 왕패(b−7 … b−1)
    n_ind = 1 + n_kan
    ind_slots = {(b - 3 - i) % (4 * SIDE) for i in range(n_ind)}
    pairs_to_winner = riichi_win and rng.random() < 0.85
    for s in arc:
        k, x, d = slot_pos(s)
        if s in ind_slots and not pairs_to_winner:
            sc.put(x, d, tw, th, False, R["wall"], k, side_tilt[k] + rng.normal(0, 1.5), force=True)
        else:
            w = tw * rng.uniform(1.5, 1.7) if rng.random() < 0.08 else bw  # 두 묶음이 한 상자로
            sc.put(x, d, w, bh, True, -1, k, side_tilt[k] + rng.normal(0, 0.8), force=True)

    # 3) 화료자 손패·떼어 둔 패·울기
    n_meld0 = len(plans[0])
    n_hand = 13 - 3 * n_meld0
    loose = rng.random() < 0.55
    # 손패 줄 ↔ 자기 패산 중심 거리: 실제 18장 패 높이 × 1.6~5.2(중앙 2.1) — 너무 붙이지 않음(사용자)
    hd = side_d[0] + th * (rng.uniform(1.7, 3.0) if rng.random() < 0.75 else rng.uniform(3.0, 5.0))
    hx = -n_hand * tw / 2 + rng.normal(0, 0.06) - (0.08 if n_meld0 else 0)
    ht = rng.normal(0, 1.5)
    if rng.random() < 0.15 and n_hand >= 6:  # 줄 끝 2~4장이 살짝 떨어짐(124654 유형)
        m = int(rng.integers(2, 5))
        x = sc.row(hx, hd, n_hand - m, R["hand"], 0, tilt=ht, force=True)
        x = sc.row(x + tw * rng.uniform(0.3, 1.0), hd + rng.normal(0, 0.006), m, R["hand"], 0, tilt=ht, force=True)
    else:
        x = sc.row(hx, hd, n_hand, R["hand"], 0, tilt=ht, force=True)
    end = x
    if not loose:
        sc.row(end, hd, 1, R["hand"], 0, tilt=ht, force=True)  # 쯔모·론 패를 줄에 붙여 둠(14장째)
        end += tw * 1.03
    if plans[0]:
        melds(sc, max(end + tw * rng.uniform(1.0, 4.0), 0.45), hd + rng.uniform(0.0, 0.12), 0, plans[0])
    LAST["loose"] = loose
    if loose:
        # 떼어 둔 화료패: 실제 9장(손패 끝 기준, 패 폭 단위) — 오른쪽 1~6.5장 떨어짐 7, 손패 앞(강 쪽) 2.4장 1, 줄 앞뒤 −2.4~+3.3,
        # 눕힘 3/9, 크게 기움(13~40°) 3/9. 오른쪽 80% · 손패 앞 12% · 왼쪽 8%, 울기·다른 패와 겹치면 다시 뽑음.
        lie = rng.random() < 0.3
        lw, lh = (th, tw) if lie else (tw, th)
        lt = rng.uniform(-45, 45) if rng.random() < 0.35 else rng.normal(0, 3)
        for _ in range(20):
            r = rng.random()
            if r < 0.8:
                # 손패 끝과 틈 0.8~6장(가장자리 기준). 11-09: 예전엔 중심 기준 1~7장(틈 0.5장부터) — 손패에 붙은 채 loose 로 라벨된
                # 153939·154904(틈 0장, 사용자 지적으로 1장 간격으로 고침)가 재료에 섞여 하한이 낮았다. 고친 실제 최소 틈 0.74장(171505)
                lx, ld = end + tw * (0.5 + rng.uniform(0.8, 6.0)), hd + tw * float(np.clip(rng.normal(0, 1.5), -2.5, 3.5))
            elif r < 0.92:
                lx, ld = rng.uniform(hx, end), hd - tw * rng.uniform(1.8, 2.8)
            else:
                lx, ld = hx - tw * rng.uniform(1.0, 4.0), hd + tw * rng.normal(0, 1.0)
            if sc.put(lx, ld, lw, lh, False, R["loose"], 0, lt):
                break

    # 4) 다른 자리: 세운 손패(뒷면 줄) + 울기(meld, 붙여서 오른쪽 모서리)
    ods = {}
    for k in (1, 2, 3):
        n = 13 - 3 * len(plans[k])
        od = ods[k] = rng.uniform(0.66, 0.72)
        sc.row(-n * tw / 2 + rng.normal(0, 0.05), od, n, -1, k, backs_at=tuple(range(n)))
        if plans[k]:
            melds(sc, rng.uniform(0.28, 0.42), od + rng.uniform(0.05, 0.12), k, plans[k])

    # 5) 리치 화료 짝: 화료자 쪽 빈 펠트(패산 줄 높이에서 빈 곳, 없으면 그 앞), (1 + 깡) 짝
    if pairs_to_winner:
        for p in range(n_ind):
            for _ in range(30):
                px = rng.uniform(-0.35, 0.3)
                pd = (dW if rng.random() < 0.6 else dW - th * rng.uniform(1.2, 1.8)) + rng.normal(0, 0.01)
                pt = rng.normal(0, 4)
                u0, v0 = sc.to_felt(px + tw / 2, pd, 0)
                u1, v1 = sc.to_felt(px + tw * 1.55, pd, 0)
                if not any(box_iou((u, v, tw * 1.1, th * 1.1), it[:4]) > 0.02 for u, v in ((u0, v0), (u1, v1)) for it in sc.items):
                    sc.put(px + tw / 2, pd, tw, th, False, R["pair"], 0, pt, force=True)
                    sc.put(px + tw * 1.55, pd, tw, th, False, R["pair"], 0, pt + rng.normal(0, 2), force=True)
                    break
    # 6) 역할 없는 외톨이 앞면(라벨 -2, 표 1-138): 화료자 아닌 자리 쪽 — 실제 3장 = 패산 앞에 나온 패(155553), 세운 손패 앞(154417),
    #    손에 든 패(144348). 80% 는 패산 ~ 세운 손패 사이·조금 바깥, 20% 는 패산 안쪽(강 쪽). 다른 앞면과 1.6장 안에 붙지 않게.
    if OTHER_NEG:
        for _ in range(int(rng.choice([0, 1, 2], p=[0.6, 0.3, 0.1]))):
            k = int(rng.integers(1, 4))
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


def dataset(n: int, seed: int, feat: str = "rot") -> list[dict]:
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        x, y = make(rng, feat)
        out.append(dict(name=f"synth3_{i}", x=x, y=list(y), n_face=len(x)))
    return out


def sheet(n: int, seed: int) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    import role_v2_train as t

    font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 15)
    col = {0: "blue", 1: "cyan", 2: "orange", 3: "red", 4: "magenta", 5: "yellow", -1: "gray", -2: "white"}
    pool = [s for s in t.load() if not s["staged"]]
    real = [pool[i] for i in (0, 10, 20, 30)]
    rng = np.random.default_rng(seed)
    syn, want_kan, want_loose = [], n // 2, n // 2  # 깡 있는 장면 절반, 떼어 둔 패 있는 장면 절반을 골라 보여 줌
    while len(syn) < n:
        x, y = make(rng)
        kan, lo = bool(LAST["kan"]), LAST["loose"]
        if (kan and want_kan > 0) or (lo and not kan and want_loose > 0):
            want_kan -= kan
            want_loose -= lo and not kan
            tag = (" 깡:" + ",".join(m.split()[1] for m in LAST["kan"]) if kan else "") + (" 떼어둔패" if lo else "")
            syn.append((f"v3 #{len(syn) + 1}" + tag, x, y, list(LAST["kanmask"])))
    scenes = [("실제 " + p["name"][-15:], p["x"], p["y"], [False] * len(p["x"])) for p in real] + syn
    S = 360
    rows = (len(scenes) + 3) // 4
    im_all = Image.new("RGB", (S * 4, S * rows), "white")
    for k, (title, x, y, km) in enumerate(scenes):
        im = Image.new("RGB", (S, S), (235, 245, 235))
        d = ImageDraw.Draw(im)
        P = lambda u, v: ((u + 0.35) / 1.9 * S, (v + 0.35) / 1.9 * S)
        for r, l, kk in zip(x, y, km):
            w, h = r[2] / 10 / 1.9 * S, r[3] / 10 / 1.9 * S
            a = math.atan2(r[9], r[10]) / 2
            cx, cy = P(r[0], r[1])
            c, s_ = math.cos(a), math.sin(a)
            pts = [(cx + dx * c - dy * s_, cy + dx * s_ + dy * c) for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))]
            if r[4]:
                d.polygon(pts, fill=(120, 120, 120), outline="black")
            else:
                d.line(pts + [pts[0]], fill=col[int(l)], width=3 if int(l) == 5 else 2)
                if int(l) == 5:
                    d.polygon(pts, fill=(255, 230, 0))
        # 깡 묶음: 패 색은 그대로(안깡 = 뒷면 회색 2 + 울기 하늘색 2), 묶음 바깥에 분홍 테. 가까운 깡 상자끼리 한 묶음으로
        kb = [P(r[0], r[1]) + (r[2] / 10 / 1.9 * S, r[3] / 10 / 1.9 * S) for r, kk in zip(x, km) if kk]
        groups: list[list] = []
        for b in kb:
            for g in groups:
                if any(abs(b[0] - c[0]) < 2.2 * max(b[2], b[3]) and abs(b[1] - c[1]) < 2.2 * max(b[2], b[3]) for c in g):
                    g.append(b)
                    break
            else:
                groups.append([b])
        for g in groups:
            x0 = min(c[0] - c[2] / 2 for c in g) - 4
            x1 = max(c[0] + c[2] / 2 for c in g) + 4
            y0 = min(c[1] - c[3] / 2 for c in g) - 4
            y1 = max(c[1] + c[3] / 2 for c in g) + 4
            d.rectangle((x0, y0, x1, y1), outline=(230, 0, 140), width=3)
        cx, cy = P(x[0, 0] - x[0, 6], x[0, 1] - x[0, 7])
        d.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill="red")
        d.text((5, 4), title, fill="black", font=font)
        im_all.paste(im, ((k % 4) * S, (k // 4) * S))
    out = t.V2 / "synth_v3_samples.jpg"
    im_all.save(out, quality=90)
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--seed", type=int, default=123)
    a = ap.parse_args()
    print(sheet(a.n, a.seed))
