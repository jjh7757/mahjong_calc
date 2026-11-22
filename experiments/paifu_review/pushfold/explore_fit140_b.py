"""밀기 · 접기 설계용 탐색 2 — 맞춤 140판만. 2샹텐 이상 · 리치 차례 · 갈리는 차례에서 S42 가 미는 예외를 무엇이 가르나."""
import gzip
import json
from collections import defaultdict

D = r'C:\Users\jjh7757\dev\mahjong_calc\experiments\paifu_review\results\mxfit\stage1'
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
    if r['game'] not in fit or r.get('afterRiichi') or r.get('afterCall') or not r.get('s42') or len(r['candidates']) < 2 or not r.get('riichiSeats'):
        continue
    cs = r['candidates']
    risk = {fold(c['tile']): (c.get('risk') or 0.0) for c in cs}
    rmin = min(risk.values())
    b1 = fold(r['mhForwardBest'] or r['mhBest'])
    ms = min(c['shanten'] for c in cs)
    sc = r['scores']
    me = sc[r['seat']]
    rank = 1 + sum(1 for i, s in enumerate(sc) if s > me or (s == me and i < r['seat']))
    dec.append(dict(sh=min(max(r['shantenBefore'], 0), 3), gB1=risk[b1] - rmin, gS=risk[fold(r['s42']['s42Discard'])] - rmin, gA=risk[fold(r['actual'])] - rmin,
                    rmin=rmin, wall=r['wallLeft'], nri=len(r['riichiSeats']), dealer=bool(r['dealer']), melds=r['heroMelds'],
                    dora=sum((c.get('dora') or 0) * c['n'] + (1 if c.get('red') else 0) for c in cs),
                    rp=max((c.get('roundPoint') or 0.0) for c in cs if c['shanten'] == ms), rank=rank, last=r['kyokuNum'] >= 7))


def tab(title, g, keyf, labels):
    print(f'\n{title}')
    for lab in labels:
        s = [d for d in g if keyf(d) == lab]
        if not s:
            continue
        fo = sum(1 for d in s if d['gS'] < 2)
        pp = [d for d in s if d['gA'] >= 5]
        pf = sum(1 for d in pp if d['gS'] < 2)
        print(f'  {str(lab):<14} n {len(s):5d} · S42 접음 {100 * fo / len(s):3.0f}% · 플레이어가 민 {len(pp):4d} 중 S42 접음 {100 * pf / max(len(pp), 1):3.0f}%')


for name, cond in (('2샹텐 이상', lambda d: d['sh'] >= 2), ('1샹텐', lambda d: d['sh'] == 1), ('텐파이', lambda d: d['sh'] == 0)):
    g = [d for d in dec if cond(d) and d['gB1'] >= 5]
    fo = sum(1 for d in g if d['gS'] < 2)
    pp = [d for d in g if d['gA'] >= 5]
    print(f'\n##### {name} · 리치 차례 · 갈림(효율 패 위험 차 ≥ 5%p): n {len(g)} · S42 접음 {100 * fo / len(g):.0f}% · 플레이어가 민 {len(pp)} 중 S42 접음 {100 * sum(1 for d in pp if d["gS"] < 2) / max(len(pp), 1):.0f}%')
    tab('내 울기 수', g, lambda d: min(d['melds'], 2), [0, 1, 2])
    tab('손의 도라(적5 포함) 수', g, lambda d: min(d['dora'], 3), [0, 1, 2, 3])
    tab('국수지(지키는 후보 최고) 구간', g, lambda d: '0' if d['rp'] <= 0 else ('~2000' if d['rp'] < 2000 else ('~4000' if d['rp'] < 4000 else '4000+')), ['0', '~2000', '~4000', '4000+'])
    tab('남은 패산', g, lambda d: '40+' if d['wall'] >= 40 else ('20~39' if d['wall'] >= 20 else '~19'), ['40+', '20~39', '~19'])
    tab('리치한 사람 수', g, lambda d: min(d['nri'], 2), [1, 2])
    tab('내가 친', g, lambda d: d['dealer'], [False, True])
    tab('내 순위', g, lambda d: d['rank'], [1, 2, 3, 4])
    tab('가장 안전한 패의 위험', g, lambda d: '0' if d['rmin'] == 0 else ('<3' if d['rmin'] < 3 else '≥3'), ['0', '<3', '≥3'])
