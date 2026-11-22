"""에이전트에게 고르게 하기 채점 — 설계서 docs/mxplainer_fit_design_1121.md 13절 (답을 보기 전에 씀, 2026-11-22).

쓰기(저장소 뿌리에서):
  python -X utf8 experiments/paifu_review/mxfit/agent_score.py <답 폴더(batch_NN.json 들)> [--out results/mxfit/agent1/score.json]

같은 240결정에서 S42 첫째 버림과 같음: 에이전트 · B0 · B1 · B2 · F · U · 플레이어 실제.
전체 숫자는 검증 40판의 구간 비율로 가중. 짝지은 차이(에이전트 − F · 에이전트 − B1)는 구간 안에서 결정을 다시 뽑는 부트스트랩 2,000번.
"""
import argparse
import glob
import gzip
import json
import os
import random
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
S1 = os.path.join(ROOT, 'experiments', 'paifu_review', 'results', 'mxfit', 'stage1')
A1 = os.path.join(ROOT, 'experiments', 'paifu_review', 'results', 'mxfit', 'agent1')
NON = {'Riichi', 'Hora', 'Kan', 'Ryukyoku', 'Pass', 'Chi(low)', 'Chi(mid)', 'Chi(high)', 'Pon'}
HON = {'E': '1z', 'S': '2z', 'W': '3z', 'N': '4z', 'P': '5z', 'F': '6z', 'C': '7z'}
BINS = ['0/없음', '0/있음', '1/없음', '1/있음', '2/없음', '2/있음', '3+/없음', '3+/있음']
SEED = 20261122


def fold(t):
    t = t.strip()
    if t in HON:
        return HON[t]
    return ('5' + t[1]) if t[0] == '0' else t[:2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('answers')
    ap.add_argument('--out', default=os.path.join(A1, 'score.json'))
    a = ap.parse_args()

    key = json.load(open(os.path.join(A1, 'private', 'key.json'), encoding='utf-8'))
    want = {(v['game'], v['kyoku'], v['seat'], v['k']): d for d, v in key.items()}
    rows = {}
    with gzip.open(os.path.join(S1, 'joined.jsonl.gz'), 'rt', encoding='utf-8') as f:
        for line in f:
            r = json.loads(line)
            k = (r['game'], r['kyoku'], r['seat'], r['k'])
            if k in want:
                rows[want[k]] = r
    preds = {}
    val_bins = defaultdict(int)
    with open(os.path.join(S1, 'preds_val.jsonl'), encoding='utf-8') as f:
        for line in f:
            p = json.loads(line)
            val_bins[p['bin']] += 1
            k = (p['game'], p['kyoku'], p['seat'], p['k'])
            if k in want:
                preds[want[k]] = p
    assert len(rows) == len(key) == len(preds), (len(rows), len(key), len(preds))
    total = sum(val_bins.values())
    weight = {b: val_bins[b] / total for b in val_bins}

    ans = {}
    for fp in sorted(glob.glob(os.path.join(a.answers, 'batch_*.json'))):
        for it in json.load(open(fp, encoding='utf-8')):
            ans[it['id']] = it
    missing = sorted(set(key) - set(ans))

    recs = []
    for d in sorted(key):
        r, p = rows[d], preds[d]
        q = {}
        for name, v in r['s42']['q'].items():
            if name not in NON:
                t = fold(name)
                q[t] = max(q.get(t, -1e9), v)
        s42 = fold(r['s42']['s42Discard'])
        cands = {fold(c['tile']) for c in r['candidates']}
        it = ans.get(d)
        pick = None
        if it and isinstance(it.get('pick'), str) and it['pick'].strip():
            try:
                pick = fold(it['pick'])
            except Exception:
                pick = None
        valid = pick in cands
        picks = {'에이전트': pick if valid else None, 'B0': fold(r['b0Order'][0]), 'B1': fold(r['mhForwardBest'] or r['mhBest']),
                 'B2': fold(r['mhBest']), 'F': fold(p['pickF']), 'U': fold(p['pickU']), '실제': fold(r['actual'])}
        recs.append({'id': d, 'bin': p['bin'], 'threat': '있음' if r.get('riskSeats') else '없음', 'valid': valid, 's42': s42,
                     'hit': {k: int(v == s42) for k, v in picks.items()},
                     'regret': {k: (q[s42] - q[v]) if v in q else None for k, v in picks.items()},
                     'pick': picks, 'stance': (it or {}).get('stance'), 'reason': (it or {}).get('reason')})

    names = ['에이전트', 'B0', 'B1', 'B2', 'F', 'U', '실제']

    def weighted(rs, name, wts):
        tot = sum(wts[b] for b in {r['bin'] for r in rs})
        out = 0.0
        for b in {r['bin'] for r in rs}:
            g = [r for r in rs if r['bin'] == b]
            out += wts[b] / tot * sum(r['hit'][name] for r in g) / len(g)
        return out

    def boot(rs, f, n=2000):
        rng = random.Random(SEED)
        by = defaultdict(list)
        for r in rs:
            by[r['bin']].append(r)
        vals = []
        for _ in range(n):
            samp = []
            for b, g in by.items():
                samp += [g[rng.randrange(len(g))] for _ in g]
            vals.append(f(samp))
        vals.sort()
        return vals[int(0.025 * n)], vals[int(0.975 * n) - 1]

    out = {'n': len(recs), 'missing': missing, 'invalid': [r['id'] for r in recs if not r['valid']], 'weights': weight, 'groups': {}}
    groups = {'전체(구간 가중)': recs, '위협 없음': [r for r in recs if r['threat'] == '없음'], '위협 있음': [r for r in recs if r['threat'] == '있음']}
    print(f"결정 {len(recs)} · 답 없음 {len(missing)} · 후보 밖 답 {len(out['invalid'])}")
    print('묶음'.ljust(16) + ''.join(n_.rjust(9) for n_ in names) + '   에이전트 − F [95%]        에이전트 − B1 [95%]')
    for gname, rs in groups.items():
        row = {n_: weighted(rs, n_, weight) for n_ in names}
        dF = row['에이전트'] - row['F']
        dB = row['에이전트'] - row['B1']
        ciF = boot(rs, lambda s: weighted(s, '에이전트', weight) - weighted(s, 'F', weight))
        ciB = boot(rs, lambda s: weighted(s, '에이전트', weight) - weighted(s, 'B1', weight))
        reg = {n_: (lambda xs: sum(xs) / len(xs) if xs else None)([r['regret'][n_] for r in rs if r['regret'][n_] is not None]) for n_ in names}
        out['groups'][gname] = {'n': len(rs), 'match': row, 'agent_minus_F': [dF, *ciF], 'agent_minus_B1': [dB, *ciB], 'regret_mean_unweighted': reg,
                                'raw_hits': {n_: sum(r['hit'][n_] for r in rs) for n_ in names}}
        print(gname.ljust(16) + ''.join(f'{100 * row[n_]:.1f}%'.rjust(9) for n_ in names)
              + f'   {100 * dF:+.1f} [{100 * ciF[0]:+.1f}, {100 * ciF[1]:+.1f}]'.ljust(28) + f'{100 * dB:+.1f} [{100 * ciB[0]:+.1f}, {100 * ciB[1]:+.1f}]')
        print(' ' * 16 + ''.join((f'{reg[n_]:.3f}' if reg[n_] is not None else '-').rjust(9) for n_ in names) + '   ← Q 손해 평균(가중 안 함)')
    print('구간별 맞은 수(각 30):')
    out['bins'] = {}
    for b in BINS:
        rs = [r for r in recs if r['bin'] == b]
        hits = {n_: sum(r['hit'][n_] for r in rs) for n_ in names}
        out['bins'][b] = {'n': len(rs), 'hits': hits}
        print('  ' + b.ljust(10) + f'n {len(rs)}  ' + '  '.join(f'{n_} {hits[n_]}' for n_ in names))
    st = defaultdict(lambda: [0, 0])
    for r in recs:
        st[(r['threat'], r['stance'])][0] += 1
        st[(r['threat'], r['stance'])][1] += r['hit']['에이전트']
    out['stance'] = {f'{k[0]}/{k[1]}': v for k, v in st.items()}
    print('에이전트가 붙인 태도별(위협/태도: 수, 맞음):', dict(out['stance']))
    out['records'] = recs
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    open(a.out, 'wb').write(json.dumps(out, ensure_ascii=False, indent=1).encode('utf-8'))


if __name__ == '__main__':
    main()
