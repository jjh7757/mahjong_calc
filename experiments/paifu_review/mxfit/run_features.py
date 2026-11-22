"""값 뽑기(A) 여러 프로세스로 돌리기 — 판마다 `dart <tenhou6_features.dill> <판.json> --out <판>.jsonl` (2026-11-21).

0단계 측정: 1판에서 `dart run` 80초 · `dart compile exe` 134초 · `dart compile kernel`(.dill, JIT) 76초 → .dill 을 쓴다.
프로세스 CPU 시간은 psutil 로 잰다(끝나기 직전 값을 0.2초 간격으로 따라 읽음).

쓰기: python -X utf8 run_features.py --stage0 --procs 12 --dill <dill> --out-dir <features 폴더> --timing <timing.json>
      python -X utf8 run_features.py --dev --gzip ...   # 1단계: 개발 200판, 판마다 끝나면 <판>.jsonl.gz 로 압축(원본 지움)
      python -X utf8 run_features.py --test200 --gzip ...   # 2단계: 시험 200판(split.test200_path 로만 연다)
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import split  # noqa: E402

# flutter/bin/dart(.bat) 를 거치면 psutil 이 cmd.exe 를 재므로 SDK 의 dart.exe 를 바로 부른다.
DART = r'C:\Users\jjh7757\flutter\bin\cache\dart-sdk\bin\dart.exe'
if not Path(DART).exists():
    DART = shutil.which('dart.exe') or 'dart'


def run_one(game: str, dill: str, out_dir: Path, gz: bool = False, path_fn=split.log_path) -> dict:
    src = path_fn(game)
    out = out_dir / f'{game}.jsonl'
    t0 = time.perf_counter()
    p = subprocess.Popen([DART, dill, str(src), '--out', str(out)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ps = psutil.Process(p.pid)
    seen: dict[int, float] = {}  # pid → 마지막으로 읽은 CPU 초. dart.exe 는 VM 을 자식 프로세스로 띄우므로 자식까지 센다.
    while p.poll() is None:
        try:
            for q in [ps, *ps.children(recursive=True)]:
                try:
                    t = q.cpu_times()
                    seen[q.pid] = t.user + t.system
                except psutil.Error:
                    pass
        except psutil.Error:
            pass
        time.sleep(0.2)
    cpu = sum(seen.values())
    _, err = p.communicate()
    wall = time.perf_counter() - t0
    summary = None
    if out.exists():
        last = out.read_text(encoding='utf-8').rstrip('\n').rsplit('\n', 1)[-1]
        if last.startswith('{"summary"'):
            summary = json.loads(last)['summary']
        if gz and p.returncode == 0:
            with open(out, 'rb') as fi, gzip.open(out.with_name(out.name + '.gz'), 'wb', compresslevel=6) as fo:
                shutil.copyfileobj(fi, fo)
            out.unlink()
    return {'game': game, 'rc': p.returncode, 'wall': wall, 'cpu': cpu, 'stderr': err.decode('utf-8', 'replace')[-2000:],
            'summary': summary}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stage0', action='store_true')
    ap.add_argument('--dev', action='store_true', help='개발 200판 전체(1단계)')
    ap.add_argument('--test200', action='store_true', help='시험 200판(2단계, 설계서 12절) — split.test200_path 로만 연다')
    ap.add_argument('--gzip', action='store_true', help='판마다 끝나면 .jsonl.gz 로 압축')
    ap.add_argument('--games')
    ap.add_argument('--procs', type=int, default=12)
    ap.add_argument('--dill', required=True)
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--timing')
    a = ap.parse_args()
    path_fn = split.log_path
    if a.test200:
        games, path_fn = split.test200_games(), split.test200_path
    else:
        games = split.stage0_games() if a.stage0 else (split.dev_games() if a.dev else a.games.split(','))
    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    with ThreadPoolExecutor(a.procs) as ex:
        res = list(ex.map(lambda g: run_one(g, a.dill, out_dir, a.gzip, path_fn), games))
    wall = time.perf_counter() - t0
    ks = [x for r in res if r['summary'] for x in r['summary']['kyokuSeatSecs']]
    ks_sorted = sorted(ks)

    def q(p):
        return ks_sorted[min(len(ks_sorted) - 1, int(round(p * (len(ks_sorted) - 1))))] if ks_sorted else None

    timing = {'procs': a.procs, 'games': len(games), 'wall': wall, 'cpu': sum(r['cpu'] for r in res),
              'gameWall': {r['game']: r['wall'] for r in res}, 'gameCpu': {r['game']: r['cpu'] for r in res},
              'kyokuSeat': {'n': len(ks), 'median': statistics.median(ks) if ks else None, 'p90': q(0.9),
                            'max': max(ks) if ks else None, 'sum': sum(ks)},
              'failed': [{'game': r['game'], 'rc': r['rc'], 'stderr': r['stderr']} for r in res if r['rc'] != 0],
              'cpuCount': os.cpu_count()}
    print(json.dumps({k: v for k, v in timing.items() if k not in ('gameWall', 'gameCpu')}, ensure_ascii=False, indent=1))
    if a.timing:
        Path(a.timing).write_text(json.dumps(timing, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
