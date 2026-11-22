"""설계용 확인 — 자리별 버림 순서와 울기만으로(시각을 안 쓰고) 차례 규칙대로 엮으면 끝까지 맞아떨어지나.

자리별 강 순서는 믿을 만하다(578/578). 차례는 친부터 다음 자리로 돌고, 울려 나간 패는 가져간 자리로 넘어간다.
끝까지 엮이면(남는 버림 0) 자리 사이 순서는 시각 없이 정해진다. 막히면 그 자리가 곧 '기록이 틀린 곳' 이다.
"""
import json
import os
import sys

G = r'C:\Users\jjh7757\dev\mahjong_calc\experiments\paifu_frames\results\ghost_slot_1121'
RJ = json.load(open(r'C:\Users\jjh7757\dev\mahjong_calc\experiments\paifu_frames\results\heldout_1114\rounds.json', encoding='utf-8'))
SIDES = ['bottom', 'right', 'top', 'left']
DEALER = {'R2': 'top', 'R3a': 'left', 'R4': 'bottom', 'r11': 'top'}
GAMES = ['R2', 'R3a', 'R4', 'r11', 'h12_131655', 'h13_132644', 'h14_133610', 'h15_134151', 'h16_135321', 'h17_140450', 'h18_141259', 'h19_142013', 'h20_143236']

cond = sys.argv[1] if len(sys.argv) > 1 else 'C'
ok_games = 0
for g in GAMES:
    d = json.load(open(os.path.join(G, cond, g, 'dart_overlay.json'), encoding='utf-8'))
    seq = {}
    for s in SIDES:
        seq[s] = d[s]['slots'] if isinstance(d[s], dict) else d[s]
    dealer = DEALER.get(g) or RJ[g]['dealer_side']
    p = {s: 0 for s in SIDES}
    cur = dealer
    steps = 0
    note = ''
    while True:
        if p[cur] >= len(seq[cur]):
            break
        sl = seq[cur][p[cur]]
        p[cur] += 1
        steps += 1
        if sl.get('taken_at'):
            by = sl.get('called_by')
            if by:
                cur = by
                continue
            note += f' [가져간 자리 모르는 울려 나감 {cur} {sl["tile"]}]'
        cur = SIDES[(SIDES.index(cur) + 1) % 4]
    left = {s: len(seq[s]) - p[s] for s in SIDES}
    total = sum(len(seq[s]) for s in SIDES)
    good = all(v == 0 for v in left.values())
    ok_games += good
    stuck = '' if good else f' · 막힌 자리 {cur}(그 자리 버림 {len(seq[cur])}장 다 씀) · 남은 버림 {left}'
    print(f'{g:<12} 친 {dealer:<6} 버림 {total:3d} · 엮인 {steps:3d} · {"끝까지 맞음" if good else "막힘"}{stuck}{note}')
print(f'[{cond}] 끝까지 맞은 판 {ok_games}/{len(GAMES)}')
