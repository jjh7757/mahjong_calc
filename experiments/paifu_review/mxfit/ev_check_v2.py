"""기대값 식 그대로: EV(후보) = 국수지(화료율 × 점수 쪽) − 방총 위험% / 100 × 5172 × m  (m = 1 이 식 그대로).
검증 40판(표 16-6 과 같은 결정)에서 S42 첫째 버림과 같은 비율. 맞추는 것 없음. 동률은 B1 순서로 가른다.
"""
import gzip
import json
from collections import Counter, defaultdict

D = r'C:\Users\jjh7757\dev\mahjong_calc\experiments\paifu_review\results\mxfit\stage1'
LOSS = 5172.0  # lib/engine/risk_data.dart ronPointRiichiHiIppatsu — 엔진의 위험%는 이 점수 기준으로 맞춰져 있다
MS = [0, 1, 2, 3, 5, 10]


def fold(t):
    return ('5' + t[1]) if t[0] == '0' else t[:2]


rows, games = [], set()
with gzip.open(D + r'\joined.jsonl.gz', 'rt', encoding='utf-8') as f:
    for line in f:
        r = json.loads(line)
        games.add(r['game'])
        rows.append(r)
val = set(sorted(games)[-40:])
n = Counter()
hit = defaultdict(Counter)
zero_round = Counter()
for r in rows:
    if r['game'] not in val or r.get('afterRiichi') or r.get('afterCall') or not r.get('s42'):
        continue
    cands = r['candidates']
    if len(cands) < 2:
        continue
    b1 = fold(r['mhForwardBest'] or r['mhBest'])
    order = [b1] + [fold(t) for t in r['mhOrder'] if fold(t) != b1]
    rank = {t: i for i, t in enumerate(order)}
    s42 = fold(r['s42']['s42Discard'])
    sh = min(max(r['shantenBefore'], 0), 3)
    thr = '위협 있음' if r.get('riskSeats') else '위협 없음'
    groups = ('전체', thr, f'{sh}샹텐/{thr[-2:]}')
    allzero = all(not c.get('roundPoint') for c in cands)
    picks = {'B1': b1}
    ms = min(c['shanten'] for c in cands)
    for m in MS:
        best = max(cands, key=lambda c: ((0.0 if c['shanten'] > ms else (c.get('roundPoint') or 0.0)) - (c.get('risk') or 0.0) / 100 * LOSS * m, -rank.get(fold(c['tile']), 99)))
        picks[f'EV×{m}'] = fold(best['tile'])
    for g in groups:
        n[g] += 1
        zero_round[g] += allzero
        for k, v in picks.items():
            hit[g][k] += v == s42
cols = ['B1'] + [f'EV×{m}' for m in MS]
print('묶음'.ljust(14), 'n'.rjust(6), '국수지 전부 0'.rjust(10), ' '.join(c.rjust(8) for c in cols))
for g in ['전체', '위협 없음', '위협 있음'] + sorted(x for x in n if '샹텐' in x):
    print(g.ljust(14), str(n[g]).rjust(6), f'{100 * zero_round[g] / n[g]:.0f}%'.rjust(10), ' '.join(f'{100 * hit[g][c] / n[g]:.1f}%'.rjust(8) for c in cols))
print('맞은 수(전체):', {c: hit['전체'][c] for c in cols})
print('맞은 수(위협 있음):', {c: hit['위협 있음'][c] for c in cols}, n['위협 있음'])
