"""1단계 검증 — 검증 40판에서 B0 · B1 · B2 · F · F(부드러운) · U · 실제 (2026-11-21, 설계서 11-5 · 11-6).

fit.py 가 맞춤 · 고르기 판만으로 정한 weights.json · u_model.pt 를 읽어 검증 판에 한 번 적용한다. 여기서는 아무것도 고르지 않는다.
값은 fit.make_values()(맞춤과 같은 코드). B0 · B1 · B2 · 실제의 맞음 · Q 손해 · B0 동률은 pack.py 가 baseline.decision() 에서 옮긴 것.

지표: 첫째 일치 · 둘째 안 · Q 손해(평균 / 90백분위) · 동률 포함(F 류: S42 패 점수 ≥ 최고 − 1e-9, B0: baseline 의 b0Tie).
구간별(샹텐 × 위협). 판 단위 부트스트랩 1,000번(씨 20261121) — F − B1, U − F 등의 95% 구간.

쓰기: python -X utf8 eval_val.py --pack pack.jsonl.gz --dir stage1
산출: val.md · val.json · preds_val.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fit as F  # noqa: E402

NB = 1000
BASE = ('B0', 'B1', 'B2', 'P')


def linear_from_json(j: dict) -> dict:
    return {'W': np.array(j['weights']), 'single': j['bins'] == ['전체']}


def per_decision(d: F.Data, S: np.ndarray) -> dict:
    pick = F.pick_from_scores(S)
    top2 = F.top2_from_scores(S)
    n = len(d.y)
    q = d.Q
    qs = q[np.arange(n), d.y]
    qp = q[np.arange(n), pick]
    loss = qs - qp
    best = S.max(axis=1)
    return {'pick': pick, 'hit': pick == d.y, 'top2': (top2 == d.y[:, None]).any(axis=1),
            'loss': loss, 'tie': S[np.arange(n), d.y] >= best - F.TIE_EPS}


def base_decision(d: F.Data, name: str) -> dict:
    hit = np.array([r['base']['hit'][name] for r in d.rows])
    loss = np.array([np.nan if r['base']['loss'][name] is None else r['base']['loss'][name] for r in d.rows])
    out = {'hit': hit, 'loss': loss}
    if name != 'P':
        out['top2'] = np.array([r['s42'] in r['base']['top2'][name] for r in d.rows])
    if name == 'B0':
        out['tie'] = np.array([r['base']['b0Tie'] for r in d.rows])
    return out


def summ(res: dict, sel: np.ndarray | None = None) -> dict:
    s = np.ones(len(res['hit']), bool) if sel is None else sel
    n = int(s.sum())
    out = {'n': n}
    if n == 0:
        return out
    out['hit'] = int(res['hit'][s].sum())
    out['rate'] = out['hit'] / n
    if 'top2' in res:
        out['top2'] = int(res['top2'][s].sum())
        out['top2Rate'] = out['top2'] / n
    if 'tie' in res:
        out['tie'] = int(res['tie'][s].sum())
        out['tieRate'] = out['tie'] / n
    ls = res['loss'][s]
    ls = ls[~np.isnan(ls)]
    out['lossMean'] = float(ls.mean()) if ls.size else None
    out['lossP90'] = float(np.percentile(ls, 90)) if ls.size else None
    out['lossN'] = int(ls.size)
    return out


def bootstrap(games: list[str], hits: dict[str, np.ndarray], pairs: list[tuple[str, str]]) -> dict:
    gs = sorted(set(games))
    gi = np.array([gs.index(g) for g in games])
    ns = np.bincount(gi, minlength=len(gs)).astype(float)
    H = {k: np.bincount(gi, weights=v.astype(float), minlength=len(gs)) for k, v in hits.items()}
    rng = np.random.default_rng(F.SEED)
    acc = defaultdict(list)
    for _ in range(NB):
        idx = rng.integers(0, len(gs), len(gs))
        n = ns[idx].sum()
        r = {k: H[k][idx].sum() / n for k in H}
        for k in H:
            acc[k].append(r[k])
        for a, b in pairs:
            acc[f'{a}-{b}'].append(r[a] - r[b])
    return {k: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] for k, v in acc.items()}


def pc(x):
    return '-' if x is None else f'{100 * x:.1f}%'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pack', required=True)
    ap.add_argument('--dir', required=True)
    a = ap.parse_args()
    torch.set_num_threads(16)
    out = Path(a.dir)
    W = json.loads((out / 'weights.json').read_text(encoding='utf-8'))
    fit_rep = json.loads((out / 'fit_report.json').read_text(encoding='utf-8'))
    d = F.Data(F.load_pack(a.pack, {'val'}))
    n = len(d.y)

    models = {'F': linear_from_json(W['F']), 'Fsoft': linear_from_json(W['Fsoft'])}
    for k, v in W['variants'].items():
        models[k] = linear_from_json(v)
    scores = {k: F.predict_linear(m, d) for k, m in models.items()}
    net = F.UNet(len(F.VALUES) + len(F.CTX_NAMES))
    net.load_state_dict(torch.load(out / 'u_model.pt'))
    net.eval()
    scores['U'] = F.u_scores(net, d)

    res = {k: per_decision(d, S) for k, S in scores.items()}
    for k in BASE:
        res[k] = base_decision(d, k)
    names = ['B0', 'B1', 'B2', 'F', 'Fsoft', 'U', 'P']
    vnames = list(W['variants'])

    bins = np.array([F.BINS[b] for b in d.bin])
    threat = np.array([bool(r['riskSeats']) for r in d.rows])
    shb = np.array([F.SH_BINS[b // 2] for b in d.bin])
    out_json = {'n': n, 'games': len(set(d.games)), 'main': {k: summ(res[k]) for k in names + vnames},
                'byBin': {b: {k: summ(res[k], bins == b) for k in names} for b in F.BINS},
                'byThreat': {t: {k: summ(res[k], threat == (t == '있음')) for k in names} for t in ('없음', '있음')},
                'byShanten': {s: {k: summ(res[k], shb == s) for k in names} for s in F.SH_BINS}}
    hits = {k: res[k]['hit'] for k in names + vnames}
    pairs = [('F', 'B1'), ('U', 'F'), ('Fsoft', 'F'), ('F', 'B0'), ('U', 'B1')] + [(v, 'F') for v in vnames]
    out_json['bootstrap95'] = bootstrap(d.games, hits, pairs)
    # 위협 있음 · 없음 따로 F − B1
    for t in ('없음', '있음'):
        s = threat == (t == '있음')
        out_json['bootstrap95'][f'F-B1 위협 {t}'] = bootstrap([g for g, x in zip(d.games, s) if x],
                                                               {'F': res['F']['hit'][s], 'B1': res['B1']['hit'][s]},
                                                               [('F', 'B1')])['F-B1']
    m = out_json['main']
    diff = m['F']['rate'] - m['B1']['rate']
    out_json['stopRule'] = {'F-B1': diff, 'rule': '6절: 검증 F − B1 < +2%p 면 시험 판을 열지 않고 접음',
                            'stop': diff < 0.02}
    (out / 'val.json').write_text(json.dumps(out_json, ensure_ascii=False, indent=1), encoding='utf-8')

    # preds_val.jsonl — 결정마다 열쇠 · 후보별 F 점수 · 고른 패 · S42 패
    with open(out / 'preds_val.jsonl', 'w', encoding='utf-8', newline='\n') as f:
        for i, r in enumerate(d.rows):
            c = len(r['cands'])
            f.write(json.dumps({'game': r['game'], 'kyoku': r['kyoku'], 'seat': r['seat'], 'k': r['k'],
                                'bin': F.BINS[d.bin[i]], 'tiles': d.tiles[i],
                                'scoresF': [float(x) for x in scores['F'][i, :c]],
                                'pickF': d.tiles[i][res['F']['pick'][i]],
                                'pickFsoft': d.tiles[i][res['Fsoft']['pick'][i]],
                                'pickU': d.tiles[i][res['U']['pick'][i]],
                                's42': r['s42'], 'B1': r['base']['pick']['B1']}, ensure_ascii=False) + '\n')

    # val.md
    bs = out_json['bootstrap95']
    fs = fit_rep['fitSelect']
    lab = {'B0': 'B0 지금 평가기', 'B1': 'B1 mh 후퇴 끔', 'B2': 'B2 mh 원본', 'F': 'F 맞춘 가중합',
           'Fsoft': f"F 부드러운 정답(τ {W['Fsoft']['tau']:g})", 'U': 'U 자유 모델', 'P': '플레이어 실제'}
    L = ['# mxfit 1단계 검증 40판 — S42 첫째 버림과의 일치', '',
         f"검증 {out_json['games']}판 · 주 묶음 {n}결정(설계서 11-2). F 의 L2 = {W['F']['l2']:g}, "
         f"F 부드러운 정답 τ = {W['Fsoft']['tau']:g} · U 멈춤 걸음 {W['U']['bestStep']} — 모두 고르기 20판에서 고름.", '',
         '## 주 묶음', '', '| | 첫째 일치 | 둘째 안 | 동률 포함 | Q 손해 평균 | Q 손해 90백분위 | (맞춤 140 / 고르기 20 첫째) |',
         '| --- | --- | --- | --- | --- | --- | --- |']
    for k in names:
        s = m[k]
        t2 = f"{s['top2']} ({pc(s['top2Rate'])})" if 'top2' in s else '-'
        tie = f"{s['tie']} ({pc(s['tieRate'])})" if 'tie' in s else '-'
        lm = '-' if s['lossMean'] is None else f"{s['lossMean']:.3f}"
        lp = '-' if s['lossP90'] is None else f"{s['lossP90']:.3f}"
        fsv = fs.get(k)
        fsx = f"{pc(fsv['fitFirst'])} / {pc(fsv['selFirst'])}" if fsv else '-'
        L.append(f"| {lab[k]} | {s['hit']}/{s['n']} ({pc(s['rate'])}) | {t2} | {tie} | {lm} | {lp} | {fsx} |")
    L += ['', '## 판 단위 부트스트랩 95% 구간(1,000번, 씨 20261121)', '', '| | 점 추정 | 95% 구간 |', '| --- | --- | --- |']
    for k in ('B1', 'F', 'U'):
        L.append(f"| {k} | {pc(m[k]['rate'])} | {pc(bs[k][0])} ~ {pc(bs[k][1])} |")
    for a_, b_ in (('F', 'B1'), ('U', 'F'), ('Fsoft', 'F'), ('F', 'B0'), ('U', 'B1')):
        dd = m[a_]['rate'] - m[b_]['rate']
        L.append(f"| **{a_} − {b_}** | {100 * dd:+.1f}%p | {100 * bs[f'{a_}-{b_}'][0]:+.1f} ~ {100 * bs[f'{a_}-{b_}'][1]:+.1f}%p |")
    for t in ('없음', '있음'):
        sub = out_json['byThreat'][t]
        dd = sub['F']['rate'] - sub['B1']['rate']
        k = f'F-B1 위협 {t}'
        L.append(f"| F − B1 (위협 {t}) | {100 * dd:+.1f}%p | {100 * bs[k][0]:+.1f} ~ {100 * bs[k][1]:+.1f}%p |")
    L += ['', '## 구간별(버리기 전 샹텐 / 위협) 첫째 일치', '',
          '| 구간 | n | B0 | B1 | F | F − B1 | Fsoft | U | 실제 |', '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']

    def brow(label, sub):
        if sub['F']['n'] == 0:
            return f'| {label} | 0 | | | | | | | |'
        dd = sub['F']['rate'] - sub['B1']['rate']
        return (f"| {label} | {sub['F']['n']} | {pc(sub['B0']['rate'])} | {pc(sub['B1']['rate'])} | {pc(sub['F']['rate'])} | "
                f"{100 * dd:+.1f}%p | {pc(sub['Fsoft']['rate'])} | {pc(sub['U']['rate'])} | {pc(sub['P']['rate'])} |")
    for b in F.BINS:
        L.append(brow(b, out_json['byBin'][b]))
    for t in ('없음', '있음'):
        L.append(brow(f'위협 {t}', out_json['byThreat'][t]))
    for s in F.SH_BINS:
        L.append(brow(f'샹텐 {s}', out_json['byShanten'][s]))
    vlab = {'minus_speed': '속도 묶음 뺌', 'minus_value': '타점 묶음 뺌', 'minus_defense': '수비 묶음 뺌',
            'minus_tile': '패 성질 묶음 뺌', 'tile_only': '패 성질만', 'single_bin': '구간 없음(한 벌)'}
    L += ['', '## 값 묶음 빼기 · 패 성질만 · 구간 없음(각자 L2 를 고르기 20판에서)', '',
          '| 변형 | L2 | 첫째 일치 | − F | 95% 구간 | Q 손해 평균 | (맞춤 / 고르기 첫째) |', '| --- | --- | --- | --- | --- | --- | --- |']
    L.append(f"| F(전부) | {W['F']['l2']:g} | {pc(m['F']['rate'])} | | | {m['F']['lossMean']:.3f} | "
             f"{pc(fs['F']['fitFirst'])} / {pc(fs['F']['selFirst'])} |")
    for v in vnames:
        s = m[v]
        dd = s['rate'] - m['F']['rate']
        g = next(x for x in fit_rep['variants'][v]['grid'] if x['l2'] == W['variants'][v]['l2'])
        L.append(f"| {vlab.get(v, v)} | {W['variants'][v]['l2']:g} | {pc(s['rate'])} | {100 * dd:+.1f}%p | "
                 f"{100 * bs[f'{v}-F'][0]:+.1f} ~ {100 * bs[f'{v}-F'][1]:+.1f}%p | {s['lossMean']:.3f} | "
                 f"{pc(g['fitFirst'])} / {pc(g['selFirst'])} |")
    sr = out_json['stopRule']
    L += ['', '## 6절 멈춤 조건', '',
          f"- 검증 F − B1 = {100 * sr['F-B1']:+.1f}%p → " +
          ('**+2%p 미만: 시험 판을 열지 않고 접음**' if sr['stop'] else '+2%p 이상: 멈춤 조건에 안 걸림(2단계 — 시험 판 — 는 사용자 결정)'),
          f"- U − F = {100 * (m['U']['rate'] - m['F']['rate']):+.1f}%p (5-3: 10%p 이상이면 \"섞는 식이 너무 단순\")"]
    (out / 'val.md').write_text('\n'.join(L) + '\n', encoding='utf-8', newline='\n')
    print('\n'.join(L))


if __name__ == '__main__':
    main()
