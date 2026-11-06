"""조용할 때 (e) 서버 시간: 회귀 `orig` prod 전·후 번갈아 3번(robust_suite --only orig)의 사진별 3번 중앙 → 중앙 / p90 / 최대, 사진별 차 중앙.

  python -I -X utf8 experiments/speed/e_time.py <전 JSON 3개> -- <후 JSON 3개>      (8b-3c, metrics 표 1-108 (e))
"""
from __future__ import annotations

import json
import statistics
import sys


def per_photo(paths: list[str]) -> dict[str, float]:
    runs = [json.load(open(p, encoding="utf-8"))["orig"] for p in paths]
    return {k: statistics.median(r[k]["s"] for r in runs) for k in runs[0]}


def summary(v: list[float]) -> str:
    v = sorted(v)
    return f"{statistics.median(v):.3f} / {v[min(len(v) - 1, int(round(0.9 * (len(v) - 1))))]:.3f} / {v[-1]:.3f}"


a = sys.argv[1:]
i = a.index("--")
b, f = per_photo(a[:i]), per_photo(a[i + 1:])
print(f"사진 {len(b)}장  전 {summary(list(b.values()))}  후 {summary(list(f.values()))}  (중앙 / p90 / 최대 초)")
print(f"중앙 차 {statistics.median(f.values()) - statistics.median(b.values()):+.3f}초, 사진별 차 중앙 {statistics.median(f[k] - b[k] for k in b):+.3f}초")
