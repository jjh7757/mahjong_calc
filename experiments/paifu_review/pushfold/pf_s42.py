"""밀기 · 접기 2단계용 S42 채점 래퍼 — "시험 2"(split.test599_games() 의 ID 순 앞 200판)만 (2026-11-23).

설계서 docs/push_fold_design_1122.md 9절 "정함": 시험 판 = 안 연 599판의 ID 순 앞 200판(위험 보정 다시 재기와 같은 판).
mxfit/s42_batch.py 는 고치지 않는다(공유 파일) — 그 모듈의 _init · run_kyoku_seat · has_kan · stats 를 import 해서 쓰고,
작업 단위(판 × 국) · 출력 줄 형식 · timing 형식은 s42_batch.run_task / main 과 같게 둔다. 판 파일은 split.test599_path 로만
열고, 앞 200판 밖이면 오류(test2_path).

  python -X utf8 pf_s42.py --procs 16 --threads 1 --out <results/pushfold/test2_s42.jsonl> --timing <.../test2_s42_timing.json>
  python -X utf8 pf_s42.py --first 2 ...       # 앞 2판만(연습)
  python -X utf8 pf_s42.py --selftest-dev [--procs 16]
      # 개발 앞 2판(split.dev_games()[:2], split.log_path 로 엶)을 같은 코드 길로 채점 → stage1/s42.jsonl 의 같은 판 줄과 대조
      # (열쇠 집합 · 줄 순서 · secs 뺀 모든 칸 — 실수는 1e-4 안). 시험 판은 열지 않는다.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
MX = HERE.parent / 'mxfit'
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(MX))
import s42_batch  # noqa: E402
import split  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
STAGE1_S42 = ROOT / 'experiments' / 'paifu_review' / 'results' / 'mxfit' / 'stage1' / 's42.jsonl'
N_TEST2 = 200
TOL = 1e-4


def test2_games() -> list[str]:
    """시험 2 = 안 연 599판(split.test599_games(), ID 순)의 앞 200판."""
    return split.test599_games()[:N_TEST2]


def test2_path(game: str) -> Path:
    """시험 2 200판만 경로를 준다(599판의 나머지 399판 · 시험 200판 · 개발 판이면 오류)."""
    if game not in set(test2_games()):
        raise ValueError(f'시험 2(599판 앞 200판) 밖의 판: {game}')
    return split.test599_path(game)


PATH_FN = {'dev': split.log_path, 'test2': test2_path}


def run_task(task: tuple) -> dict:
    """s42_batch.run_task 와 같되 판 경로만 PATH_FN[which]. task = (game, ki, which)."""
    game, ki, which = task
    t_cpu = time.process_time()
    t_wall = time.perf_counter()
    log = json.loads(PATH_FN[which](game).read_text(encoding='utf-8'))['log'][ki]
    rows, infos, errors = [], [], []
    kan = 0
    if s42_batch.has_kan(log):
        kan = 1
    else:
        for seat in range(4):
            try:
                r, info = s42_batch.run_kyoku_seat(game, ki, log, seat)
            except Exception as err:  # s42_batch 와 같게: 그 국 · 자리를 오류로 센다
                errors.append(f'{game} 국 {ki} 자리 {seat}: {type(err).__name__}: {err}')
                continue
            rows.extend(r)
            infos.append(info)
    return {'game': game, 'kyoku': ki, 'rows': rows, 'infos': infos, 'errors': errors, 'kyokus': 1,
            'kanSkipped': kan, 'cpu': time.process_time() - t_cpu, 'wall': time.perf_counter() - t_wall,
            'loadSecs': s42_batch._LOAD_SECS, 'pid': __import__('os').getpid()}


def score(games: list[str], which: str, procs: int, threads: int) -> tuple[list[dict], dict]:
    allowed = set(test2_games()) if which == 'test2' else set(split.dev_games())
    assert all(g in allowed for g in games), f'{which} 밖의 판'
    tasks = [(g, ki, which) for g in games
             for ki in range(len(json.loads(PATH_FN[which](g).read_text(encoding='utf-8'))['log']))]
    t0 = time.perf_counter()
    if procs == 1:
        s42_batch._init(threads, None)
        results = [run_task(t) for t in tasks]
    else:
        with ProcessPoolExecutor(procs, initializer=s42_batch._init, initargs=(threads, None)) as ex:
            results = list(ex.map(run_task, tasks, chunksize=1))
    wall = time.perf_counter() - t0
    results.sort(key=lambda r: (r['game'], r['kyoku']))
    ks = [i['secs'] for r in results for i in r['infos']]
    dec = [x for r in results for i in r['infos'] for x in i['decSecs']]
    loads = sorted({(r['pid'], r['loadSecs']) for r in results})
    timing = {'procs': procs, 'threads': threads, 'games': len(games), 'wall': wall,
              'cpu': sum(r['cpu'] for r in results),
              'modelLoad': [x for _, x in loads], 'kyokuSeat': s42_batch.stats(ks), 'decision': s42_batch.stats(dec),
              'rows': sum(len(r['rows']) for r in results),
              'kyokus': sum(r['kyokus'] for r in results), 'kanSkipped': sum(r['kanSkipped'] for r in results),
              'errors': sum(len(r['errors']) for r in results),
              'errorList': [e for r in results for e in r['errors']], 'set': which}
    return [row for r in results for row in r['rows']], timing


def write_rows(path: str, rows: list[dict]):
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')


def same_val(x, y) -> bool:
    if isinstance(x, float) or isinstance(y, float):
        return x is not None and y is not None and abs(x - y) <= TOL
    if isinstance(x, dict) and isinstance(y, dict):
        return x.keys() == y.keys() and all(same_val(x[k], y[k]) for k in x)
    if isinstance(x, list) and isinstance(y, list):
        return len(x) == len(y) and all(same_val(a, b) for a, b in zip(x, y))
    return x == y


def selftest_dev(procs: int, threads: int, out: str | None) -> bool:
    games = split.dev_games()[:2]
    rows, timing = score(games, 'dev', procs, threads)
    if out:
        write_rows(out, rows)
    ref = [json.loads(x) for x in STAGE1_S42.read_text(encoding='utf-8').splitlines() if x.strip()]
    ref = [r for r in ref if r['game'] in set(games)]
    key = lambda r: (r['game'], r['kyoku'], r['seat'], r['k'])  # noqa: E731
    ka, kb = [key(r) for r in rows], [key(r) for r in ref]
    rb = {key(r): r for r in ref}
    same = diff = 0
    exact = 0
    diffs = []
    for r in rows:
        o = rb.get(key(r))
        if o is None:
            continue
        a_ = {k: v for k, v in r.items() if k != 'secs'}
        b_ = {k: v for k, v in o.items() if k != 'secs'}
        if same_val(a_, b_):
            same += 1
            exact += a_ == b_
        else:
            diff += 1
            diffs.append(key(r))
    ok = ka == kb and diff == 0 and timing['errors'] == 0
    print(json.dumps({'games': games, 'rows': len(rows), 'refRows': len(ref), 'sameKeyOrder': ka == kb,
                      'onlyNew': len(set(ka) - set(kb)), 'onlyRef': len(set(kb) - set(ka)),
                      'same(1e-4)': same, 'exactSame': exact, 'diff': diff, 'diffKeys': diffs[:10],
                      'wall': round(timing['wall'], 1), 'errors': timing['errors'], 'pass': ok}, ensure_ascii=False))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--first', type=int)
    ap.add_argument('--procs', type=int, default=16)
    ap.add_argument('--threads', type=int, default=1)
    ap.add_argument('--out')
    ap.add_argument('--timing')
    ap.add_argument('--selftest-dev', action='store_true', help='개발 앞 2판으로 stage1/s42.jsonl 과 대조(시험 판 안 엶)')
    a = ap.parse_args()
    if a.selftest_dev:
        sys.exit(0 if selftest_dev(a.procs, a.threads, a.out) else 1)
    if not a.out:
        raise SystemExit('--out 이 필요')
    games = test2_games()
    if a.first:
        games = games[:a.first]
    rows, timing = score(games, 'test2', a.procs, a.threads)
    write_rows(a.out, rows)
    print(json.dumps({k: v for k, v in timing.items() if k != 'errorList'}, ensure_ascii=False))
    for e in timing['errorList']:
        print('  오류', e)
    if a.timing:
        Path(a.timing).write_text(json.dumps(timing, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()
