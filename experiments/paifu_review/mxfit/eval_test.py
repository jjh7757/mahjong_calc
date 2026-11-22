"""2단계 채점 — 시험 200판에 1단계의 얼린 모델을 한 번 적용 (2026-11-21, 설계서 12절 · 5-3).

1단계 산출물(stage1/weights.json 의 F · Fsoft, u_model.pt)은 읽기만 한다. 다시 맞추기 · 고르기 없음.
값 · 점수 · 지표는 1단계와 같은 함수를 import 해서 쓴다(복사 아님):
  fit.load_pack · fit.Data(= fit.make_values · bin_index · context) · fit.predict_linear · fit.UNet · fit.u_scores
  eval_val.linear_from_json · per_decision · base_decision · summ · bootstrap(판 단위 1,000번, 씨 20261121)
B0 · B1 · B2 · 플레이어 실제의 맞음 · Q 손해 · B0 동률은 pack.py 가 baseline.decision() 에서 옮긴 것.

적는 것(12절): B0 · B1 · B2 · F · F 부드러운 정답 · U · 실제의 첫째 일치(맞은 수/전체) · 둘째 안 · Q 손해,
구간별(샹텐 × 위협) · 위협 없음 / 있음 묶음, 부트스트랩 95% 구간: F − B1 · U − F · 위협 묶음별 F − B1.
덧붙임: 1단계 검증 40판(stage1/val.json)과 나란히 놓은 표, 5-3 기준에 댄 줄(사실만).

쓰기: python -X utf8 eval_test.py --pack stage2/pack.jsonl.gz --model-dir stage1 --out-dir stage2
      (--part val --out-dir <다른 폴더> 로 1단계 검증 40판에 돌리면 val.json 과 같은 숫자가 나와야 한다 — 자기 확인용)
산출: test.md · test.json · preds_test.jsonl (out-dir)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fit as F  # noqa: E402
import eval_val as EV  # noqa: E402

NAMES = ['B0', 'B1', 'B2', 'F', 'Fsoft', 'U', 'P']
BASE = ('B0', 'B1', 'B2', 'P')


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pc(x):
    return '-' if x is None else f'{100 * x:.1f}%'


def pp(x):
    return '-' if x is None else f'{100 * x:+.1f}%p'


def judge_5_3(diff: float, lo: float, hi: float, thr_f: float, thr_b1: float, u_minus_f: float) -> dict:
    """5-3 표의 어느 칸 조건에 드는지 — 사실만(판정 문구는 사용자가 정한 표의 칸 이름 그대로)."""
    if diff >= 0.05 and lo > 0.02:
        cell = '+5%p 이상이고 구간 아래 끝 > +2%p (표의 "가치 있음" 칸)'
    elif diff >= 0.05:
        cell = '점 추정은 +5%p 이상이나 구간 아래 끝이 +2%p 이하 (표의 "가치 있음" 칸 조건 중 하나만 맞음)'
    elif diff >= 0.02:
        cell = '+2 ~ +5%p (표의 "사이" 칸)'
    else:
        cell = '+2%p 미만 (표의 "접음" 칸)'
    return {'F-B1': diff, 'ci95': [lo, hi], 'cell': cell,
            'threatF<B1': thr_f < thr_b1, 'threatF': thr_f, 'threatB1': thr_b1,
            'U-F': u_minus_f, 'U-F>=10%p': u_minus_f >= 0.10}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pack', required=True)
    ap.add_argument('--model-dir', required=True, help='1단계 산출 폴더(읽기만): weights.json · u_model.pt · val.json')
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--part', default='test', help="pack 의 part(기본 'test'; 'val' 은 1단계 재현 확인용)")
    a = ap.parse_args()
    t_all = time.perf_counter()
    torch.set_num_threads(16)
    md = Path(a.model_dir)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    assert out.resolve() != md.resolve(), '1단계 폴더에 쓰지 않는다'
    model_hash = {f: sha256(md / f) for f in ('weights.json', 'u_model.pt')}
    W = json.loads((md / 'weights.json').read_text(encoding='utf-8'))
    val = json.loads((md / 'val.json').read_text(encoding='utf-8'))
    rows = F.load_pack(a.pack, {a.part})
    parts = {r['part'] for r in rows}
    assert parts == {a.part}, parts
    d = F.Data(rows)
    n = len(d.y)

    models = {'F': EV.linear_from_json(W['F']), 'Fsoft': EV.linear_from_json(W['Fsoft'])}
    scores = {k: F.predict_linear(m, d) for k, m in models.items()}
    net = F.UNet(len(F.VALUES) + len(F.CTX_NAMES))
    net.load_state_dict(torch.load(md / 'u_model.pt'))
    net.eval()
    scores['U'] = F.u_scores(net, d)

    res = {k: EV.per_decision(d, S) for k, S in scores.items()}
    for k in BASE:
        res[k] = EV.base_decision(d, k)

    bins = np.array([F.BINS[b] for b in d.bin])
    threat = np.array([bool(r['riskSeats']) for r in d.rows])
    shb = np.array([F.SH_BINS[b // 2] for b in d.bin])
    games = sorted(set(d.games))
    oj = {'part': a.part, 'n': n, 'games': len(games), 'gameIds': games,
          'model': {'dir': str(md), 'sha256': model_hash, 'F_l2': W['F']['l2'], 'Fsoft_tau': W['Fsoft']['tau'],
                    'U_bestStep': W['U']['bestStep']},
          'main': {k: EV.summ(res[k]) for k in NAMES},
          'byBin': {b: {k: EV.summ(res[k], bins == b) for k in NAMES} for b in F.BINS},
          'byThreat': {t: {k: EV.summ(res[k], threat == (t == '있음')) for k in NAMES} for t in ('없음', '있음')},
          'byShanten': {s: {k: EV.summ(res[k], shb == s) for k in NAMES} for s in F.SH_BINS}}
    hits = {k: res[k]['hit'] for k in NAMES}
    pairs = [('F', 'B1'), ('U', 'F'), ('Fsoft', 'F'), ('F', 'B0'), ('U', 'B1')]
    bs = EV.bootstrap(d.games, hits, pairs)
    for t in ('없음', '있음'):
        s = threat == (t == '있음')
        bs[f'F-B1 위협 {t}'] = EV.bootstrap([g for g, x in zip(d.games, s) if x],
                                           {'F': res['F']['hit'][s], 'B1': res['B1']['hit'][s]},
                                           [('F', 'B1')])['F-B1']
    oj['bootstrap95'] = bs
    m = oj['main']
    thr = oj['byThreat']['있음']
    oj['judge5_3'] = judge_5_3(m['F']['rate'] - m['B1']['rate'], bs['F-B1'][0], bs['F-B1'][1],
                               thr['F']['rate'], thr['B1']['rate'], m['U']['rate'] - m['F']['rate'])
    oj['model']['sha256After'] = {f: sha256(md / f) for f in ('weights.json', 'u_model.pt')}
    assert oj['model']['sha256After'] == model_hash
    oj['secs'] = time.perf_counter() - t_all
    (out / f'{a.part}.json').write_text(json.dumps(oj, ensure_ascii=False, indent=1), encoding='utf-8')

    # preds_<part>.jsonl — preds_val.jsonl 과 같은 꼴
    with open(out / f'preds_{a.part}.jsonl', 'w', encoding='utf-8', newline='\n') as f:
        for i, r in enumerate(d.rows):
            c = len(r['cands'])
            f.write(json.dumps({'game': r['game'], 'kyoku': r['kyoku'], 'seat': r['seat'], 'k': r['k'],
                                'bin': F.BINS[d.bin[i]], 'tiles': d.tiles[i],
                                'scoresF': [float(x) for x in scores['F'][i, :c]],
                                'pickF': d.tiles[i][res['F']['pick'][i]],
                                'pickFsoft': d.tiles[i][res['Fsoft']['pick'][i]],
                                'pickU': d.tiles[i][res['U']['pick'][i]],
                                's42': r['s42'], 'B1': r['base']['pick']['B1']}, ensure_ascii=False) + '\n')

    # ---------------------------------------------------------------- md
    title = '시험 200판' if a.part == 'test' else f'part {a.part}'
    lab = {'B0': 'B0 지금 평가기', 'B1': 'B1 mh 후퇴 끔', 'B2': 'B2 mh 원본', 'F': 'F 맞춘 가중합',
           'Fsoft': f"F 부드러운 정답(τ {W['Fsoft']['tau']:g})", 'U': 'U 자유 모델', 'P': '플레이어 실제'}
    L = [f'# mxfit 2단계 {title} — S42 첫째 버림과의 일치(얼린 1단계 모델, 한 번 적용)', '',
         f"{title} {oj['games']}판({games[0]} ~ {games[-1]}) · 주 묶음 {n}결정(설계서 11-2 · 12절). "
         f"모델 = `{md.name}/weights.json` 의 F(L2 {W['F']['l2']:g}) · Fsoft(τ {W['Fsoft']['tau']:g}) · "
         f"`u_model.pt`(멈춤 걸음 {W['U']['bestStep']}) — 읽기만(sha256 앞뒤 같음).", '',
         '## 주 묶음', '', '| | 첫째 일치 | 둘째 안 | 동률 포함 | Q 손해 평균 | Q 손해 90백분위 |',
         '| --- | --- | --- | --- | --- | --- |']
    for k in NAMES:
        s = m[k]
        t2 = f"{s['top2']} ({pc(s['top2Rate'])})" if 'top2' in s else '-'
        tie = f"{s['tie']} ({pc(s['tieRate'])})" if 'tie' in s else '-'
        lm = '-' if s['lossMean'] is None else f"{s['lossMean']:.3f}"
        lp = '-' if s['lossP90'] is None else f"{s['lossP90']:.3f}"
        L.append(f"| {lab[k]} | {s['hit']}/{s['n']} ({pc(s['rate'])}) | {t2} | {tie} | {lm} | {lp} |")
    L += ['', '## 판 단위 부트스트랩 95% 구간(1,000번, 씨 20261121)', '', '| | 점 추정 | 95% 구간 |', '| --- | --- | --- |']
    for k in ('B1', 'F', 'U'):
        L.append(f"| {k} | {pc(m[k]['rate'])} | {pc(bs[k][0])} ~ {pc(bs[k][1])} |")
    for x, y in pairs:
        dd = m[x]['rate'] - m[y]['rate']
        L.append(f"| **{x} − {y}** | {pp(dd)} | {100 * bs[f'{x}-{y}'][0]:+.1f} ~ {100 * bs[f'{x}-{y}'][1]:+.1f}%p |")
    for t in ('없음', '있음'):
        sub = oj['byThreat'][t]
        dd = sub['F']['rate'] - sub['B1']['rate']
        k = f'F-B1 위협 {t}'
        L.append(f"| F − B1 (위협 {t}) | {pp(dd)} | {100 * bs[k][0]:+.1f} ~ {100 * bs[k][1]:+.1f}%p |")
    L += ['', '## 구간별(버리기 전 샹텐 / 위협) 첫째 일치', '',
          '| 구간 | n | B0 | B1 | F | F − B1 | Fsoft | U | 실제 |', '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']

    def brow(label, sub):
        if sub['F']['n'] == 0:
            return f'| {label} | 0 | | | | | | | |'
        dd = sub['F']['rate'] - sub['B1']['rate']
        return (f"| {label} | {sub['F']['n']} | {pc(sub['B0']['rate'])} | {sub['B1']['hit']} ({pc(sub['B1']['rate'])}) | "
                f"{sub['F']['hit']} ({pc(sub['F']['rate'])}) | {pp(dd)} | {pc(sub['Fsoft']['rate'])} | "
                f"{pc(sub['U']['rate'])} | {pc(sub['P']['rate'])} |")
    for b in F.BINS:
        L.append(brow(b, oj['byBin'][b]))
    for t in ('없음', '있음'):
        L.append(brow(f'위협 {t}', oj['byThreat'][t]))
    for s in F.SH_BINS:
        L.append(brow(f'샹텐 {s}', oj['byShanten'][s]))

    # 1단계 검증 40판과 나란히
    vm, vbs = val['main'], val['bootstrap95']
    L += ['', f"## 1단계 검증 40판(stage1/val.json, {val['n']}결정)과 나란히", '',
          f"| | 검증 40판 첫째 | {title} 첫째 | 검증 둘째 안 | 시험 둘째 안 | 검증 Q 손해 평균 / 90 | 시험 Q 손해 평균 / 90 |",
          '| --- | --- | --- | --- | --- | --- | --- |']
    for k in NAMES:
        v, s = vm[k], m[k]
        L.append(f"| {lab[k]} | {v['hit']}/{v['n']} ({pc(v['rate'])}) | {s['hit']}/{s['n']} ({pc(s['rate'])}) | "
                 f"{pc(v.get('top2Rate'))} | {pc(s.get('top2Rate'))} | "
                 f"{v['lossMean']:.3f} / {v['lossP90']:.3f} | {s['lossMean']:.3f} / {s['lossP90']:.3f} |")
    L += ['', f'| 차 | 검증 40판 [95%] | {title} [95%] |', '| --- | --- | --- |']
    for x, y in pairs:
        key = f'{x}-{y}'
        L.append(f"| {x} − {y} | {pp(vm[x]['rate'] - vm[y]['rate'])} [{100 * vbs[key][0]:+.1f}, {100 * vbs[key][1]:+.1f}] | "
                 f"{pp(m[x]['rate'] - m[y]['rate'])} [{100 * bs[key][0]:+.1f}, {100 * bs[key][1]:+.1f}] |")
    for t in ('없음', '있음'):
        key = f'F-B1 위협 {t}'
        vs, ts = val['byThreat'][t], oj['byThreat'][t]
        L.append(f"| F − B1 (위협 {t}) | {pp(vs['F']['rate'] - vs['B1']['rate'])} [{100 * vbs[key][0]:+.1f}, {100 * vbs[key][1]:+.1f}] | "
                 f"{pp(ts['F']['rate'] - ts['B1']['rate'])} [{100 * bs[key][0]:+.1f}, {100 * bs[key][1]:+.1f}] |")
    L += ['', f'| 구간 | 검증 n | 검증 B1 | 검증 F | 검증 F − B1 | 시험 n | 시험 B1 | 시험 F | 시험 F − B1 |',
          '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for label, vsub, tsub in ([(b, val['byBin'][b], oj['byBin'][b]) for b in F.BINS] +
                              [(f'위협 {t}', val['byThreat'][t], oj['byThreat'][t]) for t in ('없음', '있음')]):
        cells = []
        for sub in (vsub, tsub):
            if sub['F']['n'] == 0:
                cells += ['0', '', '', '']
            else:
                cells += [str(sub['F']['n']), pc(sub['B1']['rate']), pc(sub['F']['rate']),
                          pp(sub['F']['rate'] - sub['B1']['rate'])]
        L.append(f'| {label} | ' + ' | '.join(cells) + ' |')

    j = oj['judge5_3']
    L += ['', '## 5-3 기준에 댄 줄(사실만)', '',
          f"- 주 판정 지표 = {title} 첫째 일치 F − B1 = **{100 * j['F-B1']:+.2f}%p**, 판 단위 95% 구간 "
          f"[{100 * j['ci95'][0]:+.2f}, {100 * j['ci95'][1]:+.2f}]%p → {j['cell']}.",
          f"- 덧붙이는 조건 ①: 위협 있는 차례 F {pc(j['threatF'])} · B1 {pc(j['threatB1'])} → "
          f"F 가 B1 보다 {'낮음' if j['threatF<B1'] else '낮지 않음'}.",
          f"- 덧붙이는 조건 ②: U − F = {100 * j['U-F']:+.2f}%p → 10%p {'이상' if j['U-F>=10%p'] else '미만'}.",
          f"- 따로 적는 것(판정을 바꾸지 않음, 12절): 위협 있는 차례만의 F − B1 = "
          f"{pp(thr['F']['rate'] - thr['B1']['rate'])} [{100 * bs['F-B1 위협 있음'][0]:+.1f}, {100 * bs['F-B1 위협 있음'][1]:+.1f}]"
          f" (1단계 검증 {pp(val['byThreat']['있음']['F']['rate'] - val['byThreat']['있음']['B1']['rate'])}).",
          '', f"채점 벽시계 {oj['secs']:.1f}초."]
    (out / f'{a.part}.md').write_text('\n'.join(L) + '\n', encoding='utf-8', newline='\n')
    print('\n'.join(L))


if __name__ == '__main__':
    main()
