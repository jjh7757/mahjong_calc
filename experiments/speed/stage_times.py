"""앱 흐름 로그(TIMING 줄)의 서버 단계별 시간과 호출별 시간을 표로(2026-11-02, API 없음). 표 1-25 아래·1-27.
  python -I -X utf8 experiments/speed/stage_times.py <로그>...
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path


def q(a: list) -> str:
    a = sorted(a)
    return f"{a[len(a) // 2]:.1f} / {a[min(len(a) - 1, int(.9 * len(a)))]:.1f} / {a[-1]:.1f}" if a else "—"


rows = []
for p in sys.argv[1:]:
    for line in Path(p).read_text(encoding="utf-8", errors="replace").splitlines():
        i = line.find("TIMING {")
        if i >= 0:
            rows.append(json.loads(line[i + 7:]))
for srv in sorted({r["server"] for r in rows}):
    part = [r for r in rows if r["server"] == srv]
    print("==", srv, len(part), "전체", q([r["total_ms"] / 1000 for r in part if "total_ms" in r]))
    d: dict = defaultdict(lambda: defaultdict(list))
    crit = Counter()
    for r in part:
        crit[max(r["call_ms"], key=r["call_ms"].get).split("_")[0]] += 1
        for name, t in (r.get("server_timing") or {}).items():
            k = name.split("_")[0]
            for s in ("decode_ms", "queue_ms", "prep_ms", "gate_ms", "handler_ms"):
                d[k][s].append(t.get(s, 0) / 1000)
            g = t.get("gemini_ms") or []
            d[k]["gem"].append(max(g, default=0) / 1000)
            d[k]["n"].append(len(g))
            d[k]["net"].append((r["call_ms"].get(name, 0) - t.get("handler_ms", 0)) / 1000)
    print("가장 느린 호출", dict(crit))
    for k, v in d.items():
        print(k, len(v["handler_ms"]), "서버 전체", q(v["handler_ms"]), "| 디코드", q(v["decode_ms"]), "| 대기", q(v["queue_ms"]), "| 전처리", q(v["prep_ms"]),
              "(게이트", q(v["gate_ms"]), ") | Gemini 최장", q(v["gem"]), "호출 수", round(statistics.mean(v["n"]), 1), "| 망·파싱", q(v["net"]))
