"""모서리 白 퐁 찾기(local_read.corner_blank)의 흔들림 고치기 시험(2026-11-05, 사용자 "171245 원인 보기"·"재봐", 노트북, API 없음).

원래는 손패 아래 끝 + 패 높이(y_ref) 한 줄로 (1) 탁자 오른쪽 끝을 찾고 (2) 그 줄에서 아래로 펠트 경계 계단을 잰다. 白 퐁 맨 위 패가
그 줄에 닿으면 패 시작점을 탁자 끝으로 읽어 폭이 한 장 줄고 탈락한다(171245: 2회차 y_ref 370 통과, 8회차 374 탈락 — 白 위쪽 끝 373).
고친 것: (1) 탁자 끝 = 손패 바로 아래(y_top)부터 y_ref 까지 여러 줄 중 가장 오른쪽 끝, (2) 계단 재기는 y_top 에서 출발.
탁자 끝은 패에 가릴 수 있다는 사실에서 나온 수정이라 사진에 맞춘 값이 아니다(y_top = 손패 아래 끝 + 0.15 × 패 높이).
  install(lr)  — app.local_read.corner_blank 를 고친 판으로 바꾼다(haku_pair.install 보다 먼저)
"""
from __future__ import annotations

import inspect


def install(lr) -> None:
    src = inspect.getsource(lr.corner_blank)
    old_right = '''    cols = np.nonzero(felt[y_ref])[0]
    if not cols.size:
        return None
    # 오른쪽 탁자 끝 = 패 폭 2개 넘게 이어진 펠트 중 가장 오른쪽(테두리 너머 작은 조각을 안 잡게)
    runs = np.split(cols, np.nonzero(np.diff(cols) > 0.5 * fr.tw)[0] + 1)
    long_runs = [c for c in runs if c[-1] - c[0] >= 2 * fr.tw]
    if not long_runs:
        return None
    right = int(long_runs[-1][-1])'''
    new_right = '''    y_top = int(max(b[1] + b[3] for b in fr.hand) + 0.15 * fr.th)  # 손패 바로 아래(모서리 패 위)
    ends = []
    for yy in range(y_top, y_ref + 1, 3):  # 탁자 끝은 모서리 패에 가릴 수 있어 여러 줄 중 가장 오른쪽
        cols = np.nonzero(felt[yy])[0]
        if not cols.size:
            continue
        runs = np.split(cols, np.nonzero(np.diff(cols) > 0.5 * fr.tw)[0] + 1)
        long_runs = [c for c in runs if c[-1] - c[0] >= 2 * fr.tw]
        if long_runs:
            ends.append(int(long_runs[-1][-1]))
    if not ends:
        return None
    right = max(ends)'''
    old_edge = '''        if not felt[y_ref, x]:
            return -1  # 손·팔 등으로 가려진 줄
        stop = np.nonzero(~felt[y_ref:, x])[0]
        return y_ref + int(stop[0]) if stop.size else felt.shape[0]'''
    new_edge = '''        if not felt[y_top, x]:
            return -1  # 손·팔 등으로 가려진 줄
        stop = np.nonzero(~felt[y_top:, x])[0]
        return y_top + int(stop[0]) if stop.size else felt.shape[0]'''
    for a, b in ((old_right, new_right), (old_edge, new_edge)):
        assert src.count(a) == 1, a[:40]
        src = src.replace(a, b)
    ns = dict(vars(lr))
    exec(src, ns)
    lr.corner_blank = ns["corner_blank"]
