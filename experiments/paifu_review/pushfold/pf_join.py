"""밀기 · 접기 2단계 맞붙이기 — stage3/features(599판) 중 시험 2(599판 ID 순 앞 200판)만 골라 S42 와 맞붙임 (2026-11-23).

mxfit/join.py 와 같은 방식이다(열쇠 (game, kyoku, seat, k) · actual 어긋남 뺌 · s42 칸 9개 · 보고 칸 같음). join.py 는 폴더 전체를
읽으므로, 여기서는 판 목록에 든 파일만 join.read_features(파일) 로 하나씩 읽고(파일 이름 순 — 폴더 읽기와 같은 순서) 나머지
파일은 열지 않는다. S42 줄도 판 목록 안의 것만 쓴다(밖의 줄 수는 보고에 적음 — 정상이면 0).

  python -X utf8 pf_join.py --features <results/mxfit/stage3/features> --s42 <results/pushfold/test2_s42.jsonl> \
      --out <results/pushfold/test2_joined.jsonl.gz> --report <results/pushfold/test2_join_report.json>
  python -X utf8 pf_join.py --selftest-dev [--n 3] [--s42 <stage1/s42.jsonl 또는 pf_s42 --selftest-dev 출력>]
      # 개발 판으로만: stage1/features 의 select+val 첫 n 판(+ pf_s42 자기 검사 2판) + S42 → stage1/joined.jsonl.gz 의 그 판 줄과
      #   줄 단위로 같은지(같은 순서 · json 문자열 같음). 시험 판은 열지 않는다.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
MX = HERE.parent / 'mxfit'
sys.path.insert(0, str(MX))
sys.path.insert(0, str(HERE))
import join as mxjoin  # noqa: E402
import split  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
S1 = ROOT / 'experiments' / 'paifu_review' / 'results' / 'mxfit' / 'stage1'
S42_FIELDS = ('trigger', 'actualRiichi', 'q', 'topAction', 's42Discard', 's42DiscardQ', 'reachQ', 'shanten', 'secs')


def feature_files(src: Path, games: list[str]) -> list[Path]:
    """판 목록의 파일만(이름으로 고름 — 다른 판 파일은 열지 않음). 판마다 .jsonl / .jsonl.gz 중 정확히 하나."""
    files = []
    for g in games:
        c = [p for p in (src / f'{g}.jsonl', src / f'{g}.jsonl.gz') if p.exists()]
        if len(c) != 1:
            raise SystemExit(f'{g}: features 파일 {len(c)}개')
        files.append(c[0])
    return sorted(files, key=lambda f: f.name)


def join_rows(files: list[Path], s42_path: Path, games: set[str]) -> tuple[list[dict], dict]:
    """join.main 과 같은 계산(입력만 파일 목록 · 판 목록)."""
    feats, summaries = [], []
    for f in files:
        r, s = mxjoin.read_features(f)
        feats += r
        summaries += s
    s42_all = [json.loads(x) for x in mxjoin.read_text(s42_path).splitlines() if x.strip()]
    s42 = [r for r in s42_all if r['game'] in games]
    key = mxjoin.key
    fa, dup_a = {}, 0
    for r in feats:
        dup_a += key(r) in fa
        fa[key(r)] = r
    fc, dup_c = {}, 0
    for r in s42:
        dup_c += key(r) in fc
        fc[key(r)] = r
    only_a = [k for k in fa if k not in fc]
    only_a_riichi = [k for k in only_a if fa[k].get('afterRiichi')]
    only_a_other = [k for k in only_a if not fa[k].get('afterRiichi')]
    only_c = [k for k in fc if k not in fa]
    mism, joined, riichi_flag_diff = [], [], []
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
        row['s42'] = {x: c.get(x) for x in S42_FIELDS}
        joined.append(row)
    rep = {
        'games': len(games), 'featureFiles': len(files), 's42RowsOutsideGames': len(s42_all) - len(s42),
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
    return joined, rep


def write(out: str, rows: list[dict]):
    with mxjoin.open_out(out) as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')


def selftest(n: int, s42_path: Path, extra_games: list[str]) -> bool:
    s1 = split.stage1_split()
    games = sorted(set(s1['select'][:n] + extra_games))
    assert all(g in set(split.dev_games()) for g in games)
    rows, rep = join_rows(feature_files(S1 / 'features', games), s42_path, set(games))
    import gzip

    def nosecs(r: dict) -> str:  # S42 를 새로 돌린 출력이면 s42.secs(걸린 시간)만 다르다 — 그 칸만 빼고도 대조
        r = dict(r)
        r['s42'] = {k: v for k, v in r['s42'].items() if k != 'secs'}
        return json.dumps(r, ensure_ascii=False)

    new_rows = rows
    with gzip.open(S1 / 'joined.jsonl.gz', 'rt', encoding='utf-8') as f:
        ref_rows = [o for o in (json.loads(x) for x in f if x.strip()) if o['game'] in set(games)]
    new = [json.dumps(r, ensure_ascii=False) for r in new_rows]
    ref = [json.dumps(r, ensure_ascii=False) for r in ref_rows]
    same = sum(a == b for a, b in zip(new, ref))
    same_ns = sum(nosecs(a) == nosecs(b) for a, b in zip(new_rows, ref_rows))
    ok = len(new) == len(ref) == same_ns
    print(json.dumps({'games': games, 's42': str(s42_path), 'newRows': len(new), 'refRows': len(ref), 'sameLines': same,
                      'sameLinesExceptS42Secs': same_ns,
                      'diffLines': max(len(new), len(ref)) - same_ns, 'actualMismatch': rep['actualMismatch'],
                      'onlyFeaturesOther': rep['onlyFeaturesOther'], 'onlyS42': rep['onlyS42'], 'pass': ok}, ensure_ascii=False))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--features')
    ap.add_argument('--s42')
    ap.add_argument('--out')
    ap.add_argument('--report')
    ap.add_argument('--selftest-dev', action='store_true')
    ap.add_argument('--n', type=int, default=3)
    ap.add_argument('--extra-dev-games', default='', help='자기 검사에 더할 개발 판(쉼표) — pf_s42 자기 검사 2판 등')
    a = ap.parse_args()
    if a.selftest_dev:
        s42 = Path(a.s42) if a.s42 else S1 / 's42.jsonl'
        extra = [g for g in a.extra_dev_games.split(',') if g]
        sys.exit(0 if selftest(a.n, s42, extra) else 1)
    import pf_s42  # 시험 2 판 목록(split.test599_games()[:200])
    games = pf_s42.test2_games()
    rows, rep = join_rows(feature_files(Path(a.features), games), Path(a.s42), set(games))
    write(a.out, rows)
    Path(a.report).write_text(json.dumps(rep, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({k: v for k, v in rep.items() if not k.endswith('List')}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
