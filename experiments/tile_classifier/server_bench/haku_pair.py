"""모서리 白 퐁: 白 이 2장 이상 잡히면 3장 퐁으로(2026-11-05, 사용자 "그냥 모서리 백 퐁 2개이상 잡히면 3개로 취급하자", 노트북, API 없음).

서버 local_read.corner_blank 는 펠트 경계의 계단 모양으로 白 퐁 3장을 찾는데, 그 자리에 검출된 상자가 하나라도 겹치면 포기한다
(8회차가 白 을 2장 잡은 164501 이 그래서 틀렸다, 표 1-68·1-69). 원래 방법이 실패하면: 손패 줄 오른쪽(울기 자리)의 떨어진 패 중
무늬 없는(st.ink < BLANK) 상자가 이웃해서(중심 거리 ≤ 1.6 × 패 긴 변) 2장 이상이면 白 퐁으로 본다 — 3장이면 그대로, 2장이면
같은 간격으로 한 칸 더 간 자리에 세 번째 상자를 둔다. 퐁은 3장이라는 규칙에서 나온 것이라 사진에 맞춘 값이 아니다.
돌려준 상자는 부르는 쪽(fill·roles.frame_from_roles)이 채운 白(FILLED_CONF, 자동 반영 안 됨)으로 다룬다.
  install(lr)  — app.local_read.corner_blank 를 감싼다(fill 과 roles 가 모두 이것을 부른다)
"""
from __future__ import annotations

import numpy as np


def pair_pon(rgb: np.ndarray, fr, faces: list, st, blank: float) -> list | None:
    """후보 = 검출 상자 중 손패·울기에 안 쓰인 것(역할 모델 경로는 2장 묶음을 떨어진 패에도 안 넣고 버린다)."""
    if not fr.hand:
        return None
    hand_right = max(b[0] + b[2] for b in fr.hand)
    used = {tuple(b) for b in fr.hand} | {tuple(b) for m in fr.melds for b in m} | ({tuple(fr.separate)} if fr.separate else set())
    cand = [b for b in faces if tuple(b) not in used and b[0] > hand_right and st.ink(rgb, tuple(b)) < blank]
    if len(cand) < 2:
        return None
    big = 1.6 * max(fr.tw, fr.th)
    cen = lambda b: np.array([b[0] + b[2] / 2, b[1] + b[3] / 2], float)
    groups: list[list] = []
    for b in sorted(cand, key=lambda b: b[0]):
        for g in groups:
            if any(np.linalg.norm(cen(b) - cen(x)) <= big for x in g):
                g.append(b)
                break
        else:
            groups.append([b])
    g = max(groups, key=len)
    if len(g) < 2:
        return None
    g = sorted(g, key=lambda b: b[0])[:3]
    if len(g) == 2:
        a, b = g
        d = cen(b) - cen(a)
        c = cen(b) + d
        g.append((int(round(c[0] - b[2] / 2)), int(round(c[1] - b[3] / 2)), b[2], b[3]))
    return [tuple(int(v) for v in x) for x in g]


def install(lr) -> None:
    from app import seat as st

    old = lr.corner_blank

    def corner_blank(rgb, fr, faces):
        got = old(rgb, fr, faces)
        return got if got else pair_pon(rgb, fr, faces, st, lr.BLANK)

    lr.corner_blank = corner_blank
