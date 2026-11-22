"""0단계 시간 정리 — 값 뽑기(A) · S42 채점(C) 시간 → timing.json, 400판(개발 200 + 시험 200) 예상 (2026-11-21).

예상 두 가지:
- 선형: 20판 벽시계 × 400 / 20 (20판은 판 수가 프로세스 수와 비슷해 끝에 노는 프로세스가 생김 → 위쪽 어림).
- 이상: (판마다 든 시간의 합) × 400 / 20 / 프로세스 수 (일을 고르게 나눴을 때 — 아래쪽 어림).

쓰기: python -X utf8 timing.py --features <features_timing.json> --s42 <s42_timing.json> --trials <s42_try_*.json …> --out timing.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

N_TARGET = 400


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--features', required=True)
    ap.add_argument('--s42', required=True)
    ap.add_argument('--trials', nargs='*', default=[])
    ap.add_argument('--single', nargs='*', default=[], help='1판 러너 비교 메모(이름=초)')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    fa = json.loads(Path(a.features).read_text(encoding='utf-8'))
    c = json.loads(Path(a.s42).read_text(encoding='utf-8'))
    g = fa['games']
    a_sum = sum(fa['gameWall'].values())
    c_task_wall = c['kyokuSeat']['sum']  # 국 · 자리 벽시계 합(한 프로세스 안)
    out = {
        'A_features': {
            'procs': fa['procs'], 'games': g, 'wall': fa['wall'], 'cpu': fa['cpu'],
            'kyokuSeat': fa['kyokuSeat'], 'gameWallSum': a_sum,
            'proj400': {'linear': fa['wall'] * N_TARGET / g, 'ideal': a_sum * N_TARGET / g / fa['procs'],
                        'cpuHours': fa['cpu'] * N_TARGET / g / 3600},
        },
        'C_s42': {
            'procs': c['procs'], 'threads': c['threads'], 'games': c['games'], 'wall': c['wall'], 'cpu': c['cpu'],
            'modelLoad': c['modelLoad'], 'kyokuSeat': c['kyokuSeat'], 'decision': c['decision'],
            'proj400': {'linear': c['wall'] * N_TARGET / c['games'],
                        'ideal': c_task_wall * N_TARGET / c['games'] / c['procs'],
                        'cpuHours': c['cpu'] * N_TARGET / c['games'] / 3600},
        },
        'C_trials_2games': [
            {k: t[k] for k in ('procs', 'threads', 'wall', 'cpu')} | {'decisionMedian': t['decision']['median']}
            for t in (json.loads(Path(p).read_text(encoding='utf-8')) for p in a.trials)
        ],
        'A_runner_1game': dict(x.split('=', 1) for x in a.single),
    }
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
