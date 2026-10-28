"""flutter drive 로그의 TIMING {...} 줄을 정리: 장면별 시간·단계·정답·자동 반영."""
import json
import re
import statistics
import sys

TRUTH = {"B": "12000", "C": "16000", "D": "18000"}
rows = []
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    m = re.search(r"TIMING (\{.*\})", line)
    if m:
        rows.append(json.loads(m.group(1)))

def med(xs):
    return statistics.median(xs) if xs else None

print(f"runs {len(rows)}")
for r in rows:
    st = r.get("stages_ms") or {}
    ok = r.get("points") == TRUTH.get(r["scene"])
    print(f"  {r['scene']} {r['photo']}#{r['run']}: {r['total_ms'] / 1000:5.1f}s  ok={ok}  auto={'yes' if r.get('auto_block') is None and 'error' not in r else r.get('auto_block') or r.get('error')}  "
          f"stages={st}")
tot = [r["total_ms"] for r in rows if "error" not in r]
print(f"total: median {med(tot) / 1000:.1f}s  p90 {sorted(tot)[int(len(tot) * 0.9) - 1] / 1000 if tot else 0:.1f}s  max {max(tot) / 1000:.1f}s")
keys = sorted({k for r in rows for k in (r.get('stages_ms') or {})})
for k in keys:
    xs = [r["stages_ms"][k] for r in rows if k in (r.get("stages_ms") or {})]
    print(f"  stage {k}: median {med(xs) / 1000:.2f}s max {max(xs) / 1000:.2f}s")
print(f"correct {sum(r.get('points') == TRUTH.get(r['scene']) for r in rows)}/{len(rows)}, "
      f"auto {sum(r.get('auto_block') is None and 'error' not in r for r in rows)}, "
      f"auto wrong {sum(r.get('auto_block') is None and 'error' not in r and r.get('points') != TRUTH.get(r['scene']) for r in rows)}")
