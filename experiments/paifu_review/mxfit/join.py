"""값 뽑기(A, tool/tenhou6_features.dart) × S42 채점(C, s42_batch.py) 맞붙이기 (2026-11-21).

열쇠 = (game, kyoku, seat, k). 실제 버린 패(actual)가 다르면 어긋남으로 세고 뺀다 — 정상이면 0.
한쪽에만 있는 열쇠도 센다. A 에만 있고 afterRiichi(hero 리치 성립 뒤 버림 — S42 는 줄을 안 냄)인 것은 따로 센다.

쓰기: python -X utf8 join.py --features <dir 또는 jsonl> --s42 <jsonl> --out joined.jsonl --report join_report.json
1단계: features 폴더의 *.jsonl.gz 도 읽는다(같은 판의 .jsonl 과 .jsonl.gz 가 둘 다 있으면 오류). --out 이 .gz 로 끝나면 gzip 으로 쓴다.
"""
from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path


def read_text(f: Path) -> str:
    """.gz 면 풀어서 읽는다."""
    if f.name.endswith('.gz'):
        with gzip.open(f, 'rt', encoding='utf-8') as fi:
            return fi.read()
    return f.read_text(encoding='utf-8')


def open_out(path: str):
    if path.endswith('.gz'):
        return gzip.open(path, 'wt', encoding='utf-8', newline='\n', compresslevel=6)
    return open(path, 'w', encoding='utf-8', newline='\n')


def read_features(src: Path) -> tuple[list[dict], list[dict]]:
    if src.is_dir():
        files = sorted(src.glob('*.jsonl')) + sorted(src.glob('*.jsonl.gz'))
        stems = [f.name.removesuffix('.gz') for f in files]
        dup = {x for x in stems if stems.count(x) > 1}
        if dup:
            raise SystemExit(f'.jsonl 과 .jsonl.gz 가 둘 다 있음: {sorted(dup)[:5]}')
        files.sort(key=lambda f: f.name)
    else:
        files = [src]
    rows, summaries = [], []
    for f in files:
        for line in read_text(f).splitlines():
            if not line.strip():
                continue
            o = json.loads(line)
            if 'summary' in o:
                summaries.append(o['summary'])
            else:
                rows.append(o)
    return rows, summaries


def key(r: dict) -> tuple:
    return (r['game'], r['kyoku'], r['seat'], r['k'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--features', required=True)
    ap.add_argument('--s42', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--report', required=True)
    a = ap.parse_args()
    feats, summaries = read_features(Path(a.features))
    s42 = [json.loads(x) for x in read_text(Path(a.s42)).splitlines() if x.strip()]
    fa = {}
    dup_a = 0
    for r in feats:
        dup_a += key(r) in fa
        fa[key(r)] = r
    fc = {}
    dup_c = 0
    for r in s42:
        dup_c += key(r) in fc
        fc[key(r)] = r
    only_a = [k for k in fa if k not in fc]
    only_a_riichi = [k for k in only_a if fa[k].get('afterRiichi')]
    only_a_other = [k for k in only_a if not fa[k].get('afterRiichi')]
    only_c = [k for k in fc if k not in fa]
    mism, joined = [], []
    riichi_flag_diff = []
    shanten_diff = Counter()
    for k in sorted(set(fa) & set(fc)):
        f, c = fa[k], fc[k]
        if f['actual'] != c['actual']:
            mism.append({'key': k, 'features': f['actual'], 's42': c['actual']})
            continue
        if bool(f.get('riichiDeclared')) != bool(c.get('actualRiichi')):
            riichi_flag_diff.append(k)
        if f.get('shantenBefore') is not None and c.get('shanten') is not None and f['shantenBefore'] != c['shanten']:
            shanten_diff[(f['shantenBefore'], c['shanten'])] += 1
        row = dict(f)
        row['s42'] = {x: c.get(x) for x in ('trigger', 'actualRiichi', 'q', 'topAction', 's42Discard', 's42DiscardQ',
                                             'reachQ', 'shanten', 'secs')}
        joined.append(row)
    with open_out(a.out) as f:
        for r in joined:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    rep = {
        'featuresRows': len(feats), 's42Rows': len(s42), 'duplicateKeys': {'features': dup_a, 's42': dup_c},
        'joined': len(joined), 'actualMismatch': len(mism), 'actualMismatchList': mism[:50],
        'onlyFeatures': len(only_a), 'onlyFeaturesAfterRiichi': len(only_a_riichi),
        'onlyFeaturesOther': len(only_a_other), 'onlyFeaturesOtherList': [list(k) for k in only_a_other[:50]],
        'onlyS42': len(only_c), 'onlyS42List': [list(k) for k in only_c[:50]],
        'riichiFlagDiff': len(riichi_flag_diff), 'riichiFlagDiffList': [list(k) for k in riichi_flag_diff[:50]],
        'shantenDiff(features,s42meta)': {f'{a_},{b_}': n for (a_, b_), n in sorted(shanten_diff.items())},
        'featureSummaries': {
            'games': len(summaries), 'kyokus': sum(s['kyokus'] for s in summaries),
            'kanSkipped': sum(s['kanSkipped'] for s in summaries),
            'kyokuSeats': sum(s['kyokuSeats'] for s in summaries), 'errors': sum(s['errors'] for s in summaries),
            'errorList': [e for s in summaries for e in s['errorList']],
        },
    }
    Path(a.report).write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: v for k, v in rep.items() if not k.endswith('List')}, ensure_ascii=False, indent=1))
    for m in mism[:20]:
        print('  어긋남', m)


if __name__ == '__main__':
    main()
