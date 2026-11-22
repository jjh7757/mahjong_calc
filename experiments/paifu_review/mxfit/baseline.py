"""0단계 기준선 — S42 첫째 버림과 B0 · B1 · B2 · 플레이어 실제의 일치 · Q 손해 (2026-11-21, 설계서 5-1 · 5-2 · 6절).

정의
- S42 첫째 버림 = 그 결정(hero tsumo / chi / pon 뒤)의 합법 행동 중 리치 · 화료 · 깡 · 유국 · 패스를 뺀 Q 최고 패(적5 접음).
- B0 = b0Order[0](지금 평가기 discardOptions 첫째), B1 = mhForwardBest(후퇴 권장 끈 mahjong-helper),
  B2 = mhBest(mahjong-helper 원본), 실제 = 플레이어가 버린 패.
- 주 묶음 = afterRiichi 아님 · afterCall 아님 · 후보 패 종류 ≥ 2 · S42 결정 있음.
- 둘째 안: B0 는 b0Order[:2], mh(B2)는 mhOrder[:2]. 덧붙여 B1 순서(mhOrder 를 지키는 버림 → 물러나는 버림으로 안정 분할)의 [:2].
- Q 손해 = Q(s42Discard) − Q(고른 패). 패의 Q 는 그 결정의 Q 중 같은 패로 접히는 것(5m · 5mr)의 큰 값.
  플레이어가 리치했으면 실제 패의 Q 는 tsumo 결정의 "다마로 그 패를 버림" Q 다.
- 부트스트랩: 판 단위 1,000번, 씨 20261121.

쓰기: python -X utf8 baseline.py --joined joined.jsonl --out-md baseline.md --out-json baseline.json
"""
from __future__ import annotations

import argparse
import gzip
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

HON = {'E': '1z', 'S': '2z', 'W': '3z', 'N': '4z', 'P': '5z', 'F': '6z', 'C': '7z'}
SEED = 20261121
NB = 1000


def code(n: str) -> str | None:
    if n in HON:
        return HON[n]
    if len(n) >= 2 and n[0].isdigit() and n[1] in 'mps':
        return n[:2]
    return None


def tile_q(q: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    for n, v in q.items():
        c = code(n)
        if c is None:
            continue
        out[c] = max(out.get(c, -1e18), v)
    return out


def b1_order(r: dict) -> list[str]:
    back = {c['tile']: bool(c.get('backward')) for c in r['candidates']}
    order = r.get('mhOrder') or []
    return [t for t in order if not back.get(t)] + [t for t in order if back.get(t)]


def decision(r: dict) -> dict | None:
    s = r['s42']
    if not s or not s.get('q') or not s.get('s42Discard'):
        return None
    tq = tile_q(s['q'])
    sd = s['s42Discard']
    picks = {'B0': r['b0Order'][0], 'B1': r['mhForwardBest'], 'B2': r['mhBest'], 'P': r['actual']}
    d = {'game': r['game'], 's': sd, 'hit': {}, 'loss': {}}
    for name, t in picks.items():
        d['hit'][name] = t == sd
        d['loss'][name] = (tq[sd] - tq[t]) if (t in tq and sd in tq) else None
    d['top2'] = {'B0': sd in r['b0Order'][:2], 'B2': sd in (r.get('mhOrder') or [])[:2], 'B1': sd in b1_order(r)[:2]}
    cand = {c['tile']: c for c in r['candidates']}
    b0 = cand[r['b0Order'][0]]
    sc = cand.get(sd)
    d['b0Tie'] = sc is not None and sc['b0Shanten'] == b0['b0Shanten'] and sc['b0Ukeire'] == b0['b0Ukeire']
    d['threat'] = bool(r.get('riskSeats'))
    sh = r['shantenBefore']
    d['shBin'] = '-1' if sh < 0 else ('3+' if sh >= 3 else str(sh))
    j = r['junme']
    d['junBin'] = '1~6' if j <= 6 else ('7~12' if j <= 12 else '13+')
    d['topRiichi'] = s.get('topAction') == 'Riichi'
    d['recBack'] = bool(r.get('recommendBackward'))
    d['recBackHit'] = d['recBack'] and sd == r['mhBest']
    return d


def summarize(ds: list[dict]) -> dict:
    n = len(ds)
    out = {'n': n}
    if n == 0:
        return out
    for name in ('B0', 'B1', 'B2', 'P'):
        h = sum(d['hit'][name] for d in ds)
        ls = [d['loss'][name] for d in ds if d['loss'][name] is not None]
        out[name] = {'hit': h, 'rate': h / n, 'lossMean': float(np.mean(ls)) if ls else None,
                     'lossP90': float(np.percentile(ls, 90)) if ls else None, 'lossN': len(ls)}
    for name in ('B0', 'B1', 'B2'):
        h = sum(d['top2'][name] for d in ds)
        out[name]['top2'] = h
        out[name]['top2Rate'] = h / n
    t = sum(d['b0Tie'] for d in ds)
    out['B0']['tieHit'] = t
    out['B0']['tieRate'] = t / n
    out['topRiichi'] = sum(d['topRiichi'] for d in ds)
    out['recBack'] = sum(d['recBack'] for d in ds)
    out['recBackHit'] = sum(d['recBackHit'] for d in ds)
    return out


def bootstrap(ds: list[dict]) -> dict:
    by = defaultdict(list)
    for d in ds:
        by[d['game']].append(d)
    games = sorted(by)
    hits = {name: np.array([sum(d['hit'][name] for d in by[g]) for g in games], float) for name in ('B0', 'B1', 'B2')}
    ns = np.array([len(by[g]) for g in games], float)
    rng = np.random.default_rng(SEED)
    res = {k: [] for k in ('B0', 'B1', 'B2', 'B1-B0')}
    for _ in range(NB):
        idx = rng.integers(0, len(games), len(games))
        n = ns[idx].sum()
        r = {name: hits[name][idx].sum() / n for name in hits}
        for name in hits:
            res[name].append(r[name])
        res['B1-B0'].append(r['B1'] - r['B0'])
    return {k: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] for k, v in res.items()}


def pct(x):
    return '-' if x is None else f'{100 * x:.1f}%'


def num(x, f='{:.3f}'):
    return '-' if x is None else f.format(x)


def md_row(label: str, s: dict) -> str:
    if s['n'] == 0:
        return f'| {label} | 0 | | | | |'
    cells = [f"{s[k]['hit']} ({pct(s[k]['rate'])})" for k in ('B0', 'B1', 'B2', 'P')]
    return f"| {label} | {s['n']} | " + ' | '.join(cells) + ' |'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--joined', required=True)
    ap.add_argument('--out-md', required=True)
    ap.add_argument('--out-json', required=True)
    ap.add_argument('--title', default='0단계')
    a = ap.parse_args()
    if a.joined.endswith('.gz'):  # 1단계 joined.jsonl.gz
        with gzip.open(a.joined, 'rt', encoding='utf-8') as fi:
            rows = [json.loads(x) for x in fi if x.strip()]
    else:
        rows = [json.loads(x) for x in Path(a.joined).read_text(encoding='utf-8').splitlines() if x.strip()]
    excl = {'afterRiichi': 0, 'candidates<2': 0, 'noS42Decision': 0}
    main_ds, call_ds = [], []
    for r in rows:
        if r.get('afterRiichi'):
            excl['afterRiichi'] += 1
            continue
        if len(r.get('candidates') or []) < 2:
            excl['candidates<2'] += 1
            continue
        d = decision(r)
        if d is None:
            excl['noS42Decision'] += 1
            continue
        if r.get('afterCall'):
            call_ds.append(d)
        else:
            main_ds.append(d)
    games = sorted({d['game'] for d in main_ds})
    res = {'rows': len(rows), 'excluded': dict(excl), 'games': len(games), 'main': summarize(main_ds),
           'afterCall': summarize(call_ds), 'bootstrap95': bootstrap(main_ds), 'split': {}}
    for label, f in (('threat', lambda d: '있음' if d['threat'] else '없음'),
                     ('shantenBefore', lambda d: d['shBin']), ('junme', lambda d: d['junBin'])):
        groups = defaultdict(list)
        for d in main_ds:
            groups[f(d)].append(d)
        order = ['없음', '있음', '-1', '0', '1', '2', '3+', '1~6', '7~12', '13+']
        res['split'][label] = {k: summarize(groups[k]) for k in sorted(groups, key=order.index)}
    Path(a.out_json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')

    m = res['main']
    bs = res['bootstrap95']
    L = [f'# mxfit {a.title} 기준선 — S42 첫째 버림과의 일치', '',
         f"개발 판 {res['games']}판 · 맞붙인 줄 {res['rows']} · 뺀 줄 {res['excluded']}", '',
         '주 묶음 = 리치 뒤 아님 · 울기 뒤 아님 · 후보 패 종류 ≥ 2 · S42 결정 있음. 일치 = 고른 패가 S42 첫째 버림(적5 접음).', '',
         '## 첫째 일치', '',
         '| 묶음 | n | B0 지금 평가기 | B1 mh 후퇴 끔 | B2 mh 원본 | 플레이어 실제 |', '| --- | --- | --- | --- | --- | --- |',
         md_row('주 묶음', m)]
    for label, title in (('threat', '위협'), ('shantenBefore', '버리기 전 샹텐'), ('junme', '순목(hero 버림 번호)')):
        for k, s in res['split'][label].items():
            L.append(md_row(f'{title} {k}', s))
    L.append(md_row('울기 뒤(따로)', res['afterCall']))
    L += ['', '## 판 단위 부트스트랩 95% 구간(주 묶음, 1,000번, 씨 20261121)', '',
          '| | 점 추정 | 95% 구간 |', '| --- | --- | --- |']
    for k in ('B0', 'B1', 'B2'):
        L.append(f"| {k} | {pct(m[k]['rate'])} | {pct(bs[k][0])} ~ {pct(bs[k][1])} |")
    L.append(f"| B1 − B0 | {100 * (m['B1']['rate'] - m['B0']['rate']):+.1f}%p | "
             f"{100 * bs['B1-B0'][0]:+.1f} ~ {100 * bs['B1-B0'][1]:+.1f}%p |")
    L += ['', '## 둘째 안 · 동률 · Q 손해(주 묶음)', '',
          '| | 첫째 | 둘째 안 | Q 손해 평균 | Q 손해 90백분위 |', '| --- | --- | --- | --- | --- |']
    for k, t2 in (('B0', 'b0Order[:2]'), ('B1', 'B1 순서[:2]'), ('B2', 'mhOrder[:2]'), ('P', None)):
        top2 = f"{m[k]['top2']} ({pct(m[k]['top2Rate'])}) {t2}" if t2 else '-'
        L.append(f"| {k} | {pct(m[k]['rate'])} | {top2} | {num(m[k]['lossMean'])} | {num(m[k]['lossP90'])} |")
    L += ['', f"- B0 동률 포함 일치(S42 패의 b0Shanten · b0Ukeire 가 B0 최선과 같음): {m['B0']['tieHit']}/{m['n']} ({pct(m['B0']['tieRate'])})",
          f"- S42 topAction 이 Riichi: {m['topRiichi']}/{m['n']} ({pct(m['topRiichi'] / m['n'])})",
          f"- recommendBackward 켜진 결정 {m['recBack']} · 그때 S42 가 그 후퇴 패(mhBest)를 고름 {m['recBackHit']}",
          f"- 울기 뒤 묶음 n {res['afterCall']['n']} 은 주 묶음 밖(따로 한 줄).",
          '', '## 6절 멈춤 조건', '',
          f"- B1 첫째 일치 {pct(m['B1']['rate'])} — 기준 85% 이상이면 접음 → "
          f"{'85% 이상: 접음 조건에 걸림' if m['B1']['rate'] >= 0.85 else '85% 미만: 접음 조건에 안 걸림'}"]
    Path(a.out_md).write_text('\n'.join(L) + '\n', encoding='utf-8', newline='\n')
    print('\n'.join(L))


if __name__ == '__main__':
    main()
