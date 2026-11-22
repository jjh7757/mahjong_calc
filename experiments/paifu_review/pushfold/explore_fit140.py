"""밀기 · 접기 설계용 탐색 — 맞춤 140판(개발 200판의 ID 순 앞 140)만 본다. 검증 · 시험 판은 안 본다."""
import gzip
import json
from collections import Counter, defaultdict

D = r'C:\Users\jjh7757\dev\mahjong_calc\experiments\paifu_review\results\mxfit\stage1'
NON = {'Riichi', 'Hora', 'Kan', 'Ryukyoku', 'Pass', 'Chi(low)', 'Chi(mid)', 'Chi(high)', 'Pon'}
HON = {'E': '1z', 'S': '2z', 'W': '3z', 'N': '4z', 'P': '5z', 'F': '6z', 'C': '7z'}


def fold(t):
    if t in HON:
        return HON[t]
    return ('5' + t[1]) if t[0] == '0' else t[:2]


rows, games = [], set()
with gzip.open(D + r'\joined.jsonl.gz', 'rt', encoding='utf-8') as f:
    for line in f:
        r = json.loads(line)
        games.add(r['game'])
        rows.append(r)
fit = set(sorted(games)[:140])
dec = []
for r in rows:
    if r['game'] not in fit or r.get('afterRiichi') or r.get('afterCall') or not r.get('s42') or len(r['candidates']) < 2:
        continue
    if not r.get('riichiSeats'):
        continue  # 남이 리치한 차례만
    risk = {fold(c['tile']): (c.get('risk') or 0.0) for c in r['candidates']}
    rmin = min(risk.values())
    b1 = fold(r['mhForwardBest'] or r['mhBest'])
    s42 = fold(r['s42']['s42Discard'])
    act = fold(r['actual'])
    q = {}
    for name, v in r['s42']['q'].items():
        if name not in NON:
            t = fold(name)
            q[t] = max(q.get(t, -1e9), v)
    dec.append(dict(sh=min(max(r['shantenBefore'], 0), 3), gB1=risk[b1] - rmin, gS=risk[s42] - rmin, gA=risk[act] - rmin, rmin=rmin,
                    reg=q[s42] - q[act], nri=len(r['riichiSeats']), wall=r['wallLeft'], top_riichi=r['s42']['topAction'] == 'Riichi'))
print('남이 리치한 차례(맞춤 140판, 주 묶음):', len(dec))
print('S42 첫째 행동이 리치:', sum(d['top_riichi'] for d in dec))


def pct(xs, f):
    return 100 * sum(1 for x in xs if f(x)) / max(len(xs), 1)


print('\n효율 패(B1)의 위험이 가장 안전한 패보다 얼마나 높은가 — 갈리는 차례의 비율')
for th in (1, 3, 5, 8):
    print(f'  차이 ≥ {th}%p: {pct(dec, lambda d: d["gB1"] >= th):.0f}%')
print('\n샹텐별 (갈리는 차례 = B1 위험 − 최소 위험 ≥ 5%p)')
print('  샹텐   전체   갈림   S42 접음(차이<2)  S42 밂(차이≥5)  사이   | 플레이어 접음  밂   | 접은 S42 때 플레이어가 민 비율')
for sh in range(4):
    g = [d for d in dec if d['sh'] == sh]
    c = [d for d in g if d['gB1'] >= 5]
    sf = [d for d in c if d['gS'] < 2]
    print(f'  {sh}{"+" if sh == 3 else " "}  {len(g):6d} {len(c):6d}   {pct(c, lambda d: d["gS"] < 2):5.0f}%           {pct(c, lambda d: d["gS"] >= 5):5.0f}%        {pct(c, lambda d: 2 <= d["gS"] < 5):4.0f}%  |  {pct(c, lambda d: d["gA"] < 2):5.0f}%     {pct(c, lambda d: d["gA"] >= 5):4.0f}% |  {pct(sf, lambda d: d["gA"] >= 5):5.0f}% ({sum(1 for d in sf if d["gA"] >= 5)}/{len(sf)})')
c_all = [d for d in dec if d['gB1'] >= 5]
print('\n갈리는 차례에서 S42 접음 비율 — 샹텐 × 효율 패의 위험 차이')
print('  샹텐 \\ 차이   5~8      8~12     12~18    18+')
for sh in range(4):
    cells = []
    for lo, hi in ((5, 8), (8, 12), (12, 18), (18, 999)):
        g = [d for d in c_all if d['sh'] == sh and lo <= d['gB1'] < hi]
        cells.append(f'{pct(g, lambda d: d["gS"] < 2):3.0f}% ({len(g)})'.ljust(10))
    print(f'  {sh}{"+" if sh == 3 else " "}          ' + ''.join(cells))
print('\n플레이어가 민 차례(gA ≥ 5) 의 Q 손해 — S42 가 접었을 때 / 밀었을 때')
for name, f in (('S42 접음', lambda d: d['gS'] < 2), ('S42 밂', lambda d: d['gS'] >= 5)):
    g = sorted(d['reg'] for d in dec if d['gA'] >= 5 and f(d))
    if g:
        print(f'  {name}: n {len(g)} · 중앙 {g[len(g) // 2]:.2f} · 평균 {sum(g) / len(g):.2f} · 90백분위 {g[int(len(g) * 0.9)]:.2f}')
g = sorted(d['reg'] for d in dec)
print(f'  (참고) 리치 차례 전체 플레이어 Q 손해: 중앙 {g[len(g) // 2]:.2f} · 평균 {sum(g) / len(g):.2f} · 90백분위 {g[int(len(g) * 0.9)]:.2f}')
print('\n가장 안전한 패의 위험(rmin) 분포:', {k: f'{pct(dec, f):.0f}%' for k, f in (('0', lambda d: d['rmin'] == 0), ('<1', lambda d: 0 < d['rmin'] < 1), ('1~3', lambda d: 1 <= d['rmin'] < 3), ('≥3', lambda d: d['rmin'] >= 3))})
