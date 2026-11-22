"""1단계 묶음 파일 — joined.jsonl(.gz) 에서 주 묶음 결정만, 맞추기 · 평가에 쓰는 칸만 추린다 (2026-11-21, 설계서 11-2).

주 묶음 = baseline.py 와 같음(리치 뒤 아님 · 울기 뒤 아님 · 후보 패 종류 ≥ 2 · S42 결정 있음). 정답 = s42Discard.
B0 · B1 · B2 · 플레이어 실제의 맞음 · Q 손해 · B0 동률은 baseline.decision() 을 그대로 불러 옮긴다(정의가 같도록).
후보는 패 번호 순(1m..9m 1p..9p 1s..9s 1z..7z)으로 정렬한다 — 점수 동률은 이 순서의 앞 패로 가른다(11-4).
값(11-3)은 여기서 만들지 않는다 — fit.make_values() 하나가 맞춤 · 고르기 · 검증 모두에서 만든다.

쓰기: python -X utf8 pack.py --joined joined.jsonl.gz --out pack.jsonl.gz --report pack_report.json
      python -X utf8 pack.py --test200 ...   # 2단계: 시험 200판, part = 'test'
"""
from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
import sys  # noqa: E402

sys.path.insert(0, str(HERE))
import baseline  # noqa: E402
import split  # noqa: E402

CAND_FIELDS = ('tile', 'shanten', 'waits', 'improve', 'nextWaits', 'speed', 'agariRate', 'roundPoint', 'furitenRate',
               'risk', 'safeAll', 'dora', 'red', 'yakuhai', 'guestWind', 'terminal', 'honor', 'backward')


def tile_index(code: str) -> int:
    return 'mpsz'.index(code[1]) * 9 + int(code[0]) - 1


def iter_joined(path: str):
    op = gzip.open(path, 'rt', encoding='utf-8') if path.endswith('.gz') else open(path, encoding='utf-8')
    with op as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--joined', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--report', required=True)
    ap.add_argument('--test200', action='store_true', help="시험 200판(2단계) — part 'test'. 그 밖의 판이 섞이면 KeyError")
    a = ap.parse_args()
    if a.test200:
        part_of = {g: 'test' for g in split.test200_games()}
        games = {'test': set()}
    else:
        part_of = {g: k for k, v in split.stage1_split().items() for g in v}
        games = {k: set() for k in ('fit', 'select', 'val')}
    excl = Counter()
    n_out = Counter()
    with gzip.open(a.out, 'wt', encoding='utf-8', newline='\n', compresslevel=6) as fo:
        for r in iter_joined(a.joined):
            if r.get('afterRiichi'):
                excl['afterRiichi'] += 1
                continue
            if len(r.get('candidates') or []) < 2:
                excl['candidates<2'] += 1
                continue
            d = baseline.decision(r)
            if d is None:
                excl['noS42Decision'] += 1
                continue
            if r.get('afterCall'):
                excl['afterCall'] += 1
                continue
            sd = r['s42']['s42Discard']
            tq = baseline.tile_q(r['s42']['q'])
            cands = sorted(r['candidates'], key=lambda c: tile_index(c['tile']))
            if sd not in {c['tile'] for c in cands}:
                excl['s42NotInCandidates'] += 1
                continue
            part = part_of[r['game']]
            games[part].add(r['game'])
            row = {
                'game': r['game'], 'kyoku': r['kyoku'], 'seat': r['seat'], 'k': r['k'], 'part': part,
                'shantenBefore': r['shantenBefore'], 'riskSeats': r.get('riskSeats') or [], 'junme': r['junme'],
                'menzen': bool(r['menzen']), 'dealer': bool(r['dealer']), 'actual': r['actual'], 's42': sd,
                'q': [tq.get(c['tile']) for c in cands],
                'cands': [[c.get(f) for f in CAND_FIELDS] for c in cands],
                'base': {'pick': {'B0': r['b0Order'][0], 'B1': r['mhForwardBest'], 'B2': r['mhBest'], 'P': r['actual']},
                         'top2': {'B0': r['b0Order'][:2], 'B1': baseline.b1_order(r)[:2], 'B2': (r.get('mhOrder') or [])[:2]},
                         'hit': d['hit'], 'loss': d['loss'], 'b0Tie': d['b0Tie']},
            }
            fo.write(json.dumps(row, ensure_ascii=False) + '\n')
            n_out[part] += 1
    rep = {'candFields': list(CAND_FIELDS), 'excluded': dict(excl), 'decisions': dict(n_out),
           'decisionsTotal': sum(n_out.values()), 'games': {k: len(v) for k, v in games.items()}}
    Path(a.report).write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(rep, ensure_ascii=False))


if __name__ == '__main__':
    main()
