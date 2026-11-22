"""엔진의 "방총 위험 %"(mixed34)가 실제 방총 비율과 맞나 — 개발 200판, 남이 리치한 차례의 내 버림.

  python -X utf8 experiments/paifu_review/pushfold/risk_calibration.py     (저장소 뿌리에서)

버림마다: 그 패의 엔진 위험% 와, 그 버림으로 실제 론당했는가(그 국의 내 마지막 버림이고 결과가 론 · 방총자가 나).
천봉 로그는 split.log_path(개발 판만 열림)로 연다. 시험 판은 안 본다. (2026-11-22, 복기 에이전트 수비 확장 설계용)
"""
import gzip
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'mxfit'))
import split  # noqa: E402

D = os.path.join(os.path.dirname(HERE), 'results', 'mxfit', 'stage1')
HON = {'E': '1z', 'S': '2z', 'W': '3z', 'N': '4z', 'P': '5z', 'F': '6z', 'C': '7z'}


def fold(t):
    if t in HON:
        return HON[t]
    return ('5' + t[1]) if t[0] == '0' else t[:2]


rows = defaultdict(list)
with gzip.open(os.path.join(D, 'joined.jsonl.gz'), 'rt', encoding='utf-8') as f:
    for line in f:
        r = json.loads(line)
        rows[r['game']].append(r)

recs = []
for game, rs in rows.items():
    log = json.load(open(split.log_path(game), encoding='utf-8'))['log']
    for r in rs:
        if not r.get('riichiSeats') or r.get('afterRiichi'):
            continue
        kyoku = log[r['kyoku']]
        seat = r['seat']
        n_disc = len(kyoku[6 + 3 * seat])
        res = kyoku[-1]
        dealt = False
        if r['k'] == n_disc - 1 and res and res[0] == '和了':
            for i in range(2, len(res), 2):  # [점수 변화], [화료자, 방총자, 화료자, ...] 가 되풀이(더블 론)
                info = res[i]
                if info[0] != info[1] and info[1] == seat:
                    dealt = True
        risk = {fold(c['tile']): (c.get('risk') or 0.0) for c in r['candidates']}
        act = fold(r['actual'])
        recs.append(dict(risk=risk[act], rmin=min(risk.values()), dealt=dealt, sh=min(max(r['shantenBefore'], 0), 3), nri=len(r['riichiSeats']),
                         safe=any(fold(c['tile']) == act and c.get('safeAll') for c in r['candidates'])))

n = len(recs)
d = sum(x['dealt'] for x in recs)
print(f'남이 리치한 차례의 내 버림 {n} · 실제 방총 {d} ({100 * d / n:.2f}%) · 엔진 위험 평균 {sum(x["risk"] for x in recs) / n:.2f}%')
print('\n엔진 위험% 구간별 실제 방총')
print('  구간          버림     방총   실제 방총률   구간 안 엔진 위험 평균')
for lo, hi in ((0, 0.0001), (0.0001, 1), (1, 3), (3, 5), (5, 8), (8, 12), (12, 18), (18, 999)):
    g = [x for x in recs if lo <= x['risk'] < hi]
    if not g:
        continue
    dd = sum(x['dealt'] for x in g)
    name = '0' if hi <= 0.0001 else (f'{lo:g}~{hi:g}' if hi < 999 else f'{lo:g}+')
    print(f'  {name:<10} {len(g):7d} {dd:6d}   {100 * dd / len(g):6.2f}%        {sum(x["risk"] for x in g) / len(g):6.2f}%')
g = [x for x in recs if x['safe']]
print(f'\n"모두에게 안전패" 로 표시된 버림 {len(g)} 중 방총 {sum(x["dealt"] for x in g)}')
print('\n리치 인원별: ' + ' · '.join(f'{k}명 {len(g)}건 실제 {100 * sum(x["dealt"] for x in g) / len(g):.2f}% / 엔진 평균 {sum(x["risk"] for x in g) / len(g):.2f}%'
                                 for k in (1, 2) for g in [[x for x in recs if min(x['nri'], 2) == k]] if g))
# 순서가 맞나: 위험이 높은 쪽이 실제로 더 쏘이나(같은 차례 안 비교는 못 하니 전체 순위 상관만)
srt = sorted(recs, key=lambda x: x['risk'])
q = len(srt) // 5
print('엔진 위험 순 5분위별 실제 방총률: ' + ' · '.join(f'{100 * sum(x["dealt"] for x in srt[i * q:(i + 1) * q if i < 4 else len(srt)]) / max(len(srt[i * q:(i + 1) * q if i < 4 else len(srt)]), 1):.2f}%' for i in range(5)))
