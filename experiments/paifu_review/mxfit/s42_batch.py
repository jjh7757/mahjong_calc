"""Mortal-S42 일괄 채점 — tenhou6 판 × 국 × 자리 → hero 버림 결정마다 JSON 한 줄 (2026-11-21, 설계서 7절 2번).

mortal_local.py 의 to_mjai · decode · ACTION_NAMES 를 가져다 쓴다(복사 아님). 엔진은 프로세스마다 한 번만 읽는다.
깡이 든 국은 tool/tenhou6_features.dart 와 같은 규칙으로 건너뛴다(뽑기 줄에 'm' 든 문자열, 버림 줄에 'a' · 'k' 든 문자열).

줄 맞추기(k): hero 의 dahai 사건을 차례로 센다(리치 뒤 버림 포함 — 값 뽑기 쪽 k 와 같은 셈). 그 dahai 바로 앞의
hero tsumo / chi / pon 사건에서 나온 결정을 붙인다. 리치면 tsumo 결정이 본 결정이고 reach 사건의 결정이 reachQ.
hero 리치 성립 뒤 버림은 결정이 없어 줄을 내지 않는다.

쓰기:
  python -X utf8 s42_batch.py --stage0 [--first N] --procs P --threads T --out s42.jsonl --timing timing.json
  python -X utf8 s42_batch.py --games id1,id2 ...
  python -X utf8 s42_batch.py --dev ...        # 1단계: 개발 200판 전체
  python -X utf8 s42_batch.py --test200 ...    # 2단계: 시험 200판(split.test200_path 로만 연다)
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # experiments/paifu_review (mortal_local)
sys.path.insert(0, str(HERE))
from mortal_local import ACTION_NAMES, MORTAL, decode, to_mjai  # noqa: E402,F401
import split  # noqa: E402

HON = {'E': '1z', 'S': '2z', 'W': '3z', 'N': '4z', 'P': '5z', 'F': '6z', 'C': '7z'}
TILE_ACTIONS = set(ACTION_NAMES[:37])  # 34 종류 + 적5 셋
NON_DISCARD = {'Riichi', 'Chi(low)', 'Chi(mid)', 'Chi(high)', 'Pon', 'Kan', 'Hora', 'Ryukyoku', 'Pass'}


def code(mjai_tile: str) -> str:
    """mjai 패 → 우리 코드(적5 는 5 로 접음)."""
    if mjai_tile in HON:
        return HON[mjai_tile]
    return mjai_tile[:2]


def has_kan(log: list) -> bool:
    for p in range(4):
        if any(isinstance(t, str) and 'm' in t for t in log[5 + 3 * p]):
            return True
        if any(isinstance(d, str) and ('a' in d or 'k' in d) for d in log[6 + 3 * p]):
            return True
    return False


_ENGINE = None
_LOAD_SECS = None


def _init(threads: int):
    global _ENGINE, _LOAD_SECS
    import torch
    torch.set_num_threads(threads)
    sys.path.insert(0, str(MORTAL))
    from inference import load_engine  # noqa: E402
    t0 = time.perf_counter()
    _ENGINE = load_engine('cpu')
    _LOAD_SECS = time.perf_counter() - t0


def _decision(meta: dict) -> dict:
    cands = decode(meta)
    q = {n: v for n, v in cands}
    top = max(cands, key=lambda x: x[1])[0]
    best = None
    for n, v in cands:
        if n in NON_DISCARD or n not in TILE_ACTIONS:
            continue
        c = code(n)
        if best is None or v > best[1]:
            best = (c, v)
    return {'q': q, 'topAction': top, 's42Discard': best[0] if best else None,
            's42DiscardQ': best[1] if best else None, 'shanten': meta.get('shanten')}


def run_kyoku_seat(game: str, ki: int, log: list, seat: int) -> tuple[list[dict], dict]:
    from inference import Session  # noqa: E402  (_init 이 MORTAL 을 경로에 넣음)
    t0 = time.perf_counter()
    events = to_mjai(log, seat)
    s = Session(_ENGINE, seat)
    rows = []
    dec_secs = []
    pending = None   # (trigger, decision, secs)
    reach_dec = None
    k = 0
    hero_reached = False
    reach_seen = False  # 이 dahai 바로 앞 hero 사건이 reach
    for e in events:
        t1 = time.perf_counter()
        r = s.react(e)
        dt = time.perf_counter() - t1
        meta = r.get('meta') if r else None
        if meta is not None:
            dec_secs.append(dt)
        if e.get('actor') != seat:
            continue
        typ = e['type']
        if typ in ('tsumo', 'chi', 'pon'):
            pending = (typ, _decision(meta) if meta else None, dt if meta else None)
            reach_dec = None
            reach_seen = False
        elif typ == 'reach':
            reach_dec = _decision(meta) if meta else None
            reach_seen = True
        elif typ == 'dahai':
            riichi_decl = reach_seen
            if not hero_reached:
                trig, dec, secs = pending if pending else (None, None, None)
                row = {'game': game, 'kyoku': ki, 'seat': seat, 'k': k, 'trigger': trig,
                       'actual': code(e['pai']), 'actualRiichi': riichi_decl,
                       'q': dec['q'] if dec else None, 'topAction': dec['topAction'] if dec else None,
                       's42Discard': dec['s42Discard'] if dec else None,
                       's42DiscardQ': dec['s42DiscardQ'] if dec else None,
                       'reachQ': reach_dec['q'] if reach_dec else None,
                       'shanten': dec['shanten'] if dec else None, 'secs': secs}
                rows.append(row)
            if riichi_decl:
                hero_reached = True
            k += 1
            pending = None
            reach_dec = None
            reach_seen = False
    info ={'game': game, 'kyoku': ki, 'seat': seat, 'secs': time.perf_counter() - t0,
            'decisions': len(dec_secs), 'decSecs': dec_secs, 'rows': len(rows)}
    return rows, info


def _path_fn(which: str):
    """'dev' → split.log_path(개발 판만), 'test200' → split.test200_path(시험 200판만)."""
    return {'dev': split.log_path, 'test200': split.test200_path}[which]


def run_task(task: tuple) -> dict:
    """한 판의 한 국(네 자리). 작업 단위를 국으로 잘게 해 프로세스 여럿에 고르게 나눈다.
    task = (game, ki) 또는 (game, ki, which) — which 는 _path_fn 의 열쇠(없으면 'dev')."""
    game, ki = task[0], task[1]
    which = task[2] if len(task) > 2 else 'dev'
    t_cpu = time.process_time()
    t_wall = time.perf_counter()
    log = json.loads(_path_fn(which)(game).read_text(encoding='utf-8'))['log'][ki]
    rows, infos, errors = [], [], []
    kan = 0
    if has_kan(log):
        kan = 1
    else:
        for seat in range(4):
            try:
                r, info = run_kyoku_seat(game, ki, log, seat)
            except Exception as err:  # 변환 · 엔진 오류는 그 국 · 자리를 오류로 센다
                errors.append(f'{game} 국 {ki} 자리 {seat}: {type(err).__name__}: {err}')
                continue
            rows.extend(r)
            infos.append(info)
    return {'game': game, 'kyoku': ki, 'rows': rows, 'infos': infos, 'errors': errors, 'kyokus': 1,
            'kanSkipped': kan, 'cpu': time.process_time() - t_cpu, 'wall': time.perf_counter() - t_wall,
            'loadSecs': _LOAD_SECS, 'pid': os.getpid()}


def pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    i = min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))
    return xs[i]


def stats(xs: list[float]) -> dict:
    return {'n': len(xs), 'median': statistics.median(xs) if xs else None, 'p90': pct(xs, 0.9),
            'max': max(xs) if xs else None, 'sum': sum(xs)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stage0', action='store_true')
    ap.add_argument('--dev', action='store_true', help='개발 200판 전체(1단계)')
    ap.add_argument('--test200', action='store_true', help='시험 200판(2단계, 설계서 12절) — split.test200_path 로만 연다')
    ap.add_argument('--games')
    ap.add_argument('--first', type=int)
    ap.add_argument('--procs', type=int, default=1)
    ap.add_argument('--threads', type=int, default=16)
    ap.add_argument('--out')
    ap.add_argument('--timing')
    a = ap.parse_args()
    if a.test200:
        games, which = split.test200_games(), 'test200'
    else:
        games = split.stage0_games() if a.stage0 else (split.dev_games() if a.dev else a.games.split(','))
        which = 'dev'
    if a.first:
        games = games[:a.first]
    allowed = set(split.test200_games()) if which == 'test200' else set(split.dev_games())
    assert all(g in allowed for g in games), '개발 200판(또는 --test200 이면 시험 200판) 밖의 판'
    path_fn = _path_fn(which)
    tasks = [(g, ki) if which == 'dev' else (g, ki, which) for g in games
             for ki in range(len(json.loads(path_fn(g).read_text(encoding='utf-8'))['log']))]
    t0 = time.perf_counter()
    results = []
    if a.procs == 1:
        _init(a.threads)
        results = [run_task(t) for t in tasks]
    else:
        # 국 단위로 잘게 나눠 chunksize 1 로 돌린다(판 단위면 판 수보다 많은 프로세스가 놀았음).
        with ProcessPoolExecutor(a.procs, initializer=_init, initargs=(a.threads,)) as ex:
            results = list(ex.map(run_task, tasks, chunksize=1))
    wall = time.perf_counter() - t0
    results.sort(key=lambda r: (r['game'], r['kyoku']))
    if a.out:
        with open(a.out, 'w', encoding='utf-8', newline='\n') as f:
            for r in results:
                for row in r['rows']:
                    f.write(json.dumps(row, ensure_ascii=False) + '\n')
    ks = [i['secs'] for r in results for i in r['infos']]
    dec = [x for r in results for i in r['infos'] for x in i['decSecs']]
    loads = sorted({(r['pid'], r['loadSecs']) for r in results})
    timing = {'procs': a.procs, 'threads': a.threads, 'games': len(games), 'wall': wall,
              'cpu': sum(r['cpu'] for r in results),
              'modelLoad': [x for _, x in loads], 'kyokuSeat': stats(ks), 'decision': stats(dec),
              'rows': sum(len(r['rows']) for r in results),
              'kyokus': sum(r['kyokus'] for r in results), 'kanSkipped': sum(r['kanSkipped'] for r in results),
              'errors': sum(len(r['errors']) for r in results),
              'errorList': [e for r in results for e in r['errors']]}
    print(json.dumps({k: v for k, v in timing.items() if k != 'errorList'}, ensure_ascii=False))
    for e in timing['errorList']:
        print('  오류', e)
    if a.timing:
        Path(a.timing).write_text(json.dumps(timing, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
