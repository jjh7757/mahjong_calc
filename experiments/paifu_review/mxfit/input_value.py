"""입력 가림 0단계 — 기준과 가린 결과를 (game, kyoku, seat, k) 로 맞붙여 "답이 얼마나 바뀌나" 를 센다 (2026-11-22).

설계서 docs/paifu_fill_scores_tsumogiri_design_1122.md 3절 · "0단계 명세". 판정 줄은 내지 않는다(숫자만).

S42 쪽(가림마다 — scores · tsumogiri · both 중 준 것)
- 대상 = 기준 · 가린 쪽 둘 다 trigger == 'tsumo' 이고 s42Discard 가 있는 결정.
- 바뀜 = 가린 쪽 s42Discard ≠ 기준 s42Discard(둘 다 적5 를 5 로 접은 우리 코드 — s42_batch.code()).
- 손해 = 기준 줄의 q 에서 (가린 쪽이 고른 패의 Q − 기준 첫째 패의 Q). 패의 Q 는 그 종류로 접히는 행동(5m · 5mr)의 가장 높은
  Q(baseline.tile_q — s42_batch._decision 이 s42Discard 를 고르는 규칙과 같다). 그래서 손해 ≤ 0, 바뀌지 않은 결정은 0.
- 나눔(값은 모두 기준 값 뽑기 줄에서 — joined.jsonl.gz 의 같은 칸과 같은 값):
  - 위협: riskSeats 가 비었나(맞추기 실험 fit.py 구간 · baseline.py decision()['threat'] 과 같은 칸). riskSeats =
    엔진 위험표에서 (리치 또는 안깡 아닌 울기) 이고 텐파이율 > 15 인 남의 자리(tool/tenhou6_features.dart riskSeatsOf).
  - 남 리치: riichiSeats 가 비었나(이 버림 앞에 리치 선언패를 낸 남의 자리 — 설계서의 "다른 자리가 리치 선언한 뒤").
  - 국: kyokuNum(log[0][0], 동1 = 0 … 남4 = 7, 서장 8~) — 동장 0~3 / 남1 · 남2 4 · 5 / 끝 묶음 6 이상 / 그중 오라스 7 이상.
  - 국 시작 순위(점수 가림에만 표로): 기준 scores(log[1]) 에서 hero 보다 점수가 높은 자리 수 + 1, 동점은 자리 번호가 작은 쪽
    (기가 0 에 가까운 쪽)이 위 — 1등 / 2 · 3등 / 4등.
엔진 쪽(--masked-features, 쯔모기리 가림)
- 대상 = 두 쪽 다 candidates 가 있는 줄(hero 리치 뒤 아님). 묶음: 위협(기준 riskSeats) 있음 · 남 리치(기준 riichiSeats) 있음.
- 단계 = safeAll 이면 '안전', 아니면 risk(%) 가 3 미만 낮음 · 8 미만 보통 · 18 미만 높음 · 그 이상 매우 높음
  (lib/paifu/agent_facts.dart riskLevel). risk = 엔진 mixed34(위협 자리만 합친 %), safeAll = safeForAll34(세 자리 모두에게 안전).
- 가장 안전한 패 묶음 = risk 가 가장 낮은 패들(차 1e-9 안). 실제 버린 패(actual)의 단계도 비교.
부트스트랩: 비율마다 판 단위 2,000번, 씨 20261122(비율마다 새로 씨를 줌). 그 묶음에 결정이 하나라도 있는 판에서 뽑는다.

쓰기:
  python -X utf8 input_value.py --base-s42 stage1/s42.jsonl --masked scores=a.jsonl tsumogiri=b.jsonl both=c.jsonl \\
      --base-features stage1/features --masked-features <쯔모기리 가림 features 폴더> --out-md x.md --out-json x.json
  [--games id1,id2]  # 기준을 이 판으로만 줄인다(연습용). 없으면 기준 s42 에 있는 판 전부.
"""
from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
import sys  # noqa: E402

sys.path.insert(0, str(HERE))
from baseline import tile_q  # noqa: E402

SEED = 20261122
NB = 2000
MASKS = ('scores', 'tsumogiri', 'both')
LEVELS = ['안전', '낮음', '보통', '높음', '매우 높음']
EPS = 1e-9


def key(r: dict) -> tuple:
    return (r['game'], r['kyoku'], r['seat'], r['k'])


def read_lines(path: Path):
    op = gzip.open(path, 'rt', encoding='utf-8') if path.name.endswith('.gz') else open(path, encoding='utf-8')
    with op as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def feature_files(d: Path, games: set[str] | None) -> list[Path]:
    files = sorted(d.glob('*.jsonl')) + sorted(d.glob('*.jsonl.gz'))
    stems = [f.name.removesuffix('.gz').removesuffix('.jsonl') for f in files]
    dup = {x for x in stems if stems.count(x) > 1}
    if dup:
        raise SystemExit(f'{d}: .jsonl 과 .jsonl.gz 가 둘 다 있음: {sorted(dup)[:5]}')
    return [f for f, s in zip(files, stems) if games is None or s in games]


def read_features(d: Path, games: set[str] | None) -> tuple[dict, list]:
    """값 뽑기 줄 → 열쇠 → 필요한 칸만(메모리 줄이기). 요약 줄도 돌려준다."""
    out, summaries = {}, []
    dup = 0
    for f in feature_files(d, games):
        for o in read_lines(f):
            if 'summary' in o:
                summaries.append(o['summary'])
                continue
            k = key(o)
            dup += k in out
            cands = o.get('candidates')
            out[k] = {
                'actual': o['actual'], 'kyokuNum': o['kyokuNum'], 'scores': o['scores'],
                'riskSeats': o.get('riskSeats'), 'riichiSeats': o.get('riichiSeats') or [],
                'afterRiichi': bool(o.get('afterRiichi')),
                'cands': None if cands is None else {c['tile']: (c.get('risk'), bool(c.get('safeAll'))) for c in cands},
            }
    if dup:
        raise SystemExit(f'{d}: 겹친 열쇠 {dup}')
    return out, summaries


def read_s42(path: Path, games: set[str] | None) -> dict:
    out = {}
    for r in read_lines(path):
        if games is not None and r['game'] not in games:
            continue
        k = key(r)
        if k in out:
            raise SystemExit(f'{path}: 겹친 열쇠 {k}')
        out[k] = r
    return out


# ---------- 나눔 ----------

def kyoku_groups(kn: int) -> list[str]:
    g = ['동장'] if kn <= 3 else (['남1·남2'] if kn <= 5 else ['끝 묶음'])
    if kn >= 7:
        g.append('오라스')
    return g


def rank_of(scores: list[int], seat: int) -> int:
    return 1 + sum(1 for s in range(4) if s != seat and (scores[s] > scores[seat] or (scores[s] == scores[seat] and s < seat)))


def rank_group(rank: int) -> str:
    return {1: '1등', 2: '2·3등', 3: '2·3등', 4: '4등'}[rank]


def groups_of(f: dict | None, seat: int, with_rank: bool) -> list[str]:
    """한 결정이 들어가는 묶음 이름들('전체' 포함). 기준 값 뽑기 줄이 없으면 '전체' 만."""
    g = ['전체']
    if f is None:
        return g
    if f['riskSeats'] is not None:
        g.append('위협 있음' if f['riskSeats'] else '위협 없음')
    g.append('남 리치 있음' if f['riichiSeats'] else '남 리치 없음')
    g += kyoku_groups(f['kyokuNum'])
    if with_rank:
        g.append('순위 ' + rank_group(rank_of(f['scores'], seat)))
    return g


ORDER_S42 = ['전체', '위협 있음', '위협 없음', '남 리치 있음', '남 리치 없음', '동장', '남1·남2', '끝 묶음', '오라스',
             '순위 1등', '순위 2·3등', '순위 4등']


# ---------- 부트스트랩 ----------

def boot_ratio(pairs: list[tuple[str, float, float]]) -> list[float] | None:
    """(판, 분자, 분모) 목록 → 판 단위 2,000번 비율 95% 구간."""
    num, den = defaultdict(float), defaultdict(float)
    for g, a, b in pairs:
        num[g] += a
        den[g] += b
    games = sorted(den)
    if not games:
        return None
    A = np.array([num[g] for g in games])
    B = np.array([den[g] for g in games])
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(games), (NB, len(games)))
    a, b = A[idx].sum(1), B[idx].sum(1)
    with np.errstate(invalid='ignore', divide='ignore'):
        r = np.where(b > 0, a / np.where(b > 0, b, 1), np.nan)
    if np.all(np.isnan(r)):
        return None
    return [float(np.nanpercentile(r, 2.5)), float(np.nanpercentile(r, 97.5))]


def rate_cell(pairs: list[tuple[str, float, float]]) -> dict:
    a = sum(x[1] for x in pairs)
    b = sum(x[2] for x in pairs)
    return {'num': a, 'den': b, 'rate': (a / b) if b else None, 'ci95': boot_ratio(pairs),
            'games': len({x[0] for x in pairs})}


# ---------- S42 ----------

def s42_compare(base: dict, masked: dict, feats: dict, with_rank: bool) -> dict:
    only_base = [k for k in base if k not in masked]
    only_masked = [k for k in masked if k not in base]
    actual_diff, trigger_diff, no_feat, q_missing = [], [], 0, 0
    per = defaultdict(list)  # 묶음 → [(판, 바뀜, 손해)]
    examples = []
    for k in sorted(set(base) & set(masked)):
        b, m = base[k], masked[k]
        if b['actual'] != m['actual']:
            actual_diff.append(k)
            continue
        if b.get('trigger') != m.get('trigger'):
            trigger_diff.append(k)
            continue
        if b.get('trigger') != 'tsumo' or not b.get('s42Discard') or not m.get('s42Discard'):
            continue
        tq = tile_q(b['q'])
        bs, ms = b['s42Discard'], m['s42Discard']
        if bs not in tq or ms not in tq:
            q_missing += 1
            continue
        changed = bs != ms
        loss = tq[ms] - tq[bs]
        f = feats.get(k)
        if f is None:
            no_feat += 1
        for g in groups_of(f, k[2], with_rank):
            per[g].append((k[0], changed, loss))
        if changed and len(examples) < 20:
            examples.append({'key': list(k), 'base': bs, 'masked': ms, 'loss': loss})
    groups = {}
    for g in sorted(per, key=lambda x: ORDER_S42.index(x)):
        xs = per[g]
        ch = [x for x in xs if x[1]]
        groups[g] = {
            'n': len(xs),
            'changed': rate_cell([(x[0], float(x[1]), 1.0) for x in xs]),
            'lossMeanChanged': float(np.mean([x[2] for x in ch])) if ch else None,
            'lossMeanAll': float(np.mean([x[2] for x in xs])) if xs else None,
        }
    return {'onlyBase': len(only_base), 'onlyMasked': len(only_masked), 'actualDiff': len(actual_diff),
            'triggerDiff': len(trigger_diff), 'noBaseFeature': no_feat, 'qMissing': q_missing,
            'onlyBaseList': [list(k) for k in only_base[:20]], 'onlyMaskedList': [list(k) for k in only_masked[:20]],
            'actualDiffList': [list(k) for k in actual_diff[:20]], 'groups': groups, 'examples': examples}


# ---------- 엔진 ----------

def level(risk: float | None, safe: bool) -> str | None:
    if safe:
        return LEVELS[0]
    if risk is None:
        return None
    if risk < 3.0:
        return LEVELS[1]
    if risk < 8.0:
        return LEVELS[2]
    if risk < 18.0:
        return LEVELS[3]
    return LEVELS[4]


def safest(cands: dict) -> frozenset | None:
    rs = [r for r, _ in cands.values()]
    if any(r is None for r in rs):
        return None
    lo = min(rs)
    return frozenset(t for t, (r, _) in cands.items() if r - lo <= EPS)


def engine_compare(base: dict, masked: dict) -> dict:
    only_base = [k for k in base if k not in masked]
    only_masked = [k for k in masked if k not in base]
    actual_diff, cand_diff, none_risk = [], [], 0
    subsets = {'위협 있음': lambda f: bool(f['riskSeats']), '남 리치 있음': lambda f: bool(f['riichiSeats'])}
    acc = {s: {'cand': [], 'safest': [], 'actual': [], 'riskSeats': [], 'n': 0, 'trans': Counter()} for s in subsets}
    for k in sorted(set(base) & set(masked)):
        b, m = base[k], masked[k]
        if b['actual'] != m['actual']:
            actual_diff.append(k)
            continue
        if b['cands'] is None or m['cands'] is None:
            continue
        if set(b['cands']) != set(m['cands']):
            cand_diff.append(k)
            continue
        for s, pred in subsets.items():
            if not pred(b):
                continue
            a = acc[s]
            a['n'] += 1
            g = k[0]
            ch = 0
            for t in b['cands']:
                lb, lm = level(*b['cands'][t]), level(*m['cands'][t])
                ch += lb != lm
                a['trans'][f'{lb}→{lm}'] += lb != lm
            a['cand'].append((g, float(ch), float(len(b['cands']))))
            sb, sm = safest(b['cands']), safest(m['cands'])
            if sb is None or sm is None:
                if s == '위협 있음':
                    none_risk += 1
            else:
                a['safest'].append((g, float(sb != sm), 1.0))
            at = b['actual']
            if at in b['cands']:
                a['actual'].append((g, float(level(*b['cands'][at]) != level(*m['cands'][at])), 1.0))
            a['riskSeats'].append((g, float(sorted(b['riskSeats'] or []) != sorted(m['riskSeats'] or [])), 1.0))
    out = {'onlyBase': len(only_base), 'onlyMasked': len(only_masked), 'actualDiff': len(actual_diff),
           'candidateSetDiff': len(cand_diff), 'riskNoneDecisions': none_risk,
           'onlyBaseList': [list(k) for k in only_base[:20]], 'onlyMaskedList': [list(k) for k in only_masked[:20]],
           'subsets': {}}
    for s, a in acc.items():
        out['subsets'][s] = {'n': a['n'], 'candidateLevelChanged': rate_cell(a['cand']),
                             'safestSetChanged': rate_cell(a['safest']), 'actualLevelChanged': rate_cell(a['actual']),
                             'riskSeatsChanged': rate_cell(a['riskSeats']),
                             'levelTransitions': dict(sorted((x, n) for x, n in a['trans'].items() if n))}
    return out


# ---------- 보고서 ----------

def pct(x):
    return '-' if x is None else f'{100 * x:.2f}%'


def ci(c):
    return '-' if not c else f'{100 * c[0]:.2f} ~ {100 * c[1]:.2f}%'


def num(x):
    return '-' if x is None else f'{x:.4f}'


def cell_txt(c: dict) -> str:
    return f"{int(c['num'])}/{int(c['den'])} ({pct(c['rate'])})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base-s42', required=True)
    ap.add_argument('--masked', nargs='+', default=[], help='scores=<파일> tsumogiri=<파일> both=<파일> (있는 것만)')
    ap.add_argument('--base-features', required=True)
    ap.add_argument('--masked-features', help='쯔모기리 가림 값 뽑기 폴더(없으면 엔진 쪽 생략)')
    ap.add_argument('--games', help='기준을 이 판들로만(쉼표). 없으면 기준 s42 의 판 전부')
    ap.add_argument('--out-md', required=True)
    ap.add_argument('--out-json', required=True)
    ap.add_argument('--title', default='개발 200판')
    a = ap.parse_args()
    masked_paths = {}
    for x in a.masked:
        name, _, p = x.partition('=')
        if name not in MASKS or not p:
            raise SystemExit(f'--masked 는 scores=… · tsumogiri=… · both=… : {x}')
        masked_paths[name] = Path(p)
    games = set(a.games.split(',')) if a.games else None
    base = read_s42(Path(a.base_s42), games)
    if games is None:
        games = {k[0] for k in base}
    feats, base_summ = read_features(Path(a.base_features), games)
    res = {'title': a.title, 'games': len(games), 'baseS42Rows': len(base), 'baseFeatureRows': len(feats),
           'seed': SEED, 'bootstrap': NB, 's42': {}, 'engine': None,
           'baseFeatureErrors': sum(s['errors'] for s in base_summ)}
    for name in MASKS:
        if name not in masked_paths:
            continue
        mrows = read_s42(masked_paths[name], None)
        extra_games = sorted({k[0] for k in mrows} - games)
        r = s42_compare(base, mrows, feats, with_rank=name in ('scores', 'both'))
        r['maskedRows'] = len(mrows)
        r['maskedGamesOutsideBase'] = extra_games[:20]
        res['s42'][name] = r
    if a.masked_features:
        mfeats, m_summ = read_features(Path(a.masked_features), None)
        e = engine_compare(feats, mfeats)
        e['maskedFeatureRows'] = len(mfeats)
        e['maskedFeatureErrors'] = sum(s['errors'] for s in m_summ)
        e['maskedSummaryFlag'] = sorted({bool(s.get('maskTsumogiri')) for s in m_summ})
        res['engine'] = e
    Path(a.out_json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8', newline='\n')

    L = [f'# 입력 가림 0단계 — {a.title}', '',
         '설계서 docs/paifu_fill_scores_tsumogiri_design_1122.md 3절. 판정 없음(숫자만). '
         f'부트스트랩 = 판 단위 {NB:,}번 · 씨 {SEED}.', '',
         '## 맞붙이기 확인(0 이어야 정상)', '',
         '| 쪽 | 가린 쪽 줄 | 기준에만 | 가린 쪽에만 | actual 다름 | trigger 다름 | 기준 값 뽑기 줄 없음 | 기준 q 에 패 없음 |',
         '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for name, r in res['s42'].items():
        L.append(f"| S42 {name} | {r['maskedRows']} | {r['onlyBase']} | {r['onlyMasked']} | {r['actualDiff']} | "
                 f"{r['triggerDiff']} | {r['noBaseFeature']} | {r['qMissing']} |")
    if res['engine']:
        e = res['engine']
        L.append(f"| 엔진 tsumogiri | {e['maskedFeatureRows']} | {e['onlyBase']} | {e['onlyMasked']} | {e['actualDiff']} | "
                 f"후보 묶음 다름 {e['candidateSetDiff']} | - | - |")
    L += ['', f"판 {res['games']} · 기준 S42 줄 {res['baseS42Rows']} · 기준 값 뽑기 줄 {res['baseFeatureRows']} "
          f"(값 뽑기 오류 기준 {res['baseFeatureErrors']}"
          + (f" · 가림 {res['engine']['maskedFeatureErrors']}" if res['engine'] else '') + ')', '']
    L += ['## S42 첫째 버림', '',
          '대상 = 두 쪽 다 trigger tsumo · s42Discard 있음. 손해 = 기준 q 에서 Q(가린 쪽 패) − Q(기준 첫째 패) ≤ 0.',
          '위협 = 기준 riskSeats 있음(맞추기 구간과 같은 칸) · 남 리치 = 기준 riichiSeats 있음 · 국 = kyokuNum.', '']
    for name, r in res['s42'].items():
        L += [f'### 가림 {name}', '', '| 묶음 | n | 바뀜 | 95% 구간 | 바뀐 곳 평균 손해 | 전체 평균 손해 |',
              '| --- | --- | --- | --- | --- | --- |']
        for g, s in r['groups'].items():
            L.append(f"| {g} | {s['n']} | {cell_txt(s['changed'])} | {ci(s['changed']['ci95'])} | "
                     f"{num(s['lossMeanChanged'])} | {num(s['lossMeanAll'])} |")
        L.append('')
    if res['engine']:
        e = res['engine']
        L += ['## 엔진(쯔모기리 가림)', '',
              '단계 = 안전(safeAll) / 낮음 <3 / 보통 <8 / 높음 <18 / 매우 높음(risk %). 가장 안전한 패 묶음 = risk 최저인 패들.',
              f"risk 가 null 인 후보가 있어 가장 안전한 패를 셀 수 없던 결정(위협 있음): {e['riskNoneDecisions']}", '',
              '| 묶음 | 결정 n | 후보 패 단계 바뀜 | 95% 구간 | 가장 안전한 패 묶음 바뀜 | 95% 구간 | 실제 버린 패 단계 바뀜 | 95% 구간 | riskSeats 바뀜 | 95% 구간 |',
              '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
        for s, v in e['subsets'].items():
            L.append(f"| {s} | {v['n']} | {cell_txt(v['candidateLevelChanged'])} | {ci(v['candidateLevelChanged']['ci95'])} | "
                     f"{cell_txt(v['safestSetChanged'])} | {ci(v['safestSetChanged']['ci95'])} | "
                     f"{cell_txt(v['actualLevelChanged'])} | {ci(v['actualLevelChanged']['ci95'])} | "
                     f"{cell_txt(v['riskSeatsChanged'])} | {ci(v['riskSeatsChanged']['ci95'])} |")
        L.append('')
        for s, v in e['subsets'].items():
            if v['levelTransitions']:
                L.append(f"- {s} 후보 단계 옮김(기준→가림): " + ', '.join(f'{x} {n}' for x, n in v['levelTransitions'].items()))
    Path(a.out_md).write_text('\n'.join(L) + '\n', encoding='utf-8', newline='\n')
    print('\n'.join(L))


if __name__ == '__main__':
    main()
