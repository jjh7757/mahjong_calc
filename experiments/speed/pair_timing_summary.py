"""read_grid_timing_test 의 PAIR_RECTIFY(또는 ALT_URL) 로그 → 조건(server)별 정답·자동 반영·시간 + 같은 장면·회차 짝 차이.

  python -I -X utf8 experiments/speed/pair_timing_summary.py <로그> [조건a,조건b]   (기본 rect,plain)
"""
import json
import re
import statistics
import sys

TRUTH = {"B": "12000", "C": "16000", "D": "18000"}
rows = [json.loads(m.group(1)) for line in open(sys.argv[1], encoding="utf-8", errors="replace")
        if (m := re.search(r"TIMING (\{.*\})", line))]
A, B = (sys.argv[2] if len(sys.argv) > 2 else "rect,plain").split(",")


def p90(xs):
    xs = sorted(xs)
    return xs[int(0.9 * (len(xs) - 1))]


def summ(rs):
    ok = [r for r in rs if "error" not in r]
    t = [r["total_ms"] / 1000 for r in ok]
    auto = [r for r in ok if r.get("auto_block") is None]
    if not t:
        return f"{len(rs)}회 — 결과 없음, 오류 {len(rs)}"
    return (f"{len(rs)}회 정답 {sum(r.get('points') == TRUTH[r['scene']] for r in rs)} "
            f"자동 {len(auto)} 틀린자동 {sum(r.get('points') != TRUTH[r['scene']] for r in auto)} "
            f"확인 {len(ok) - len(auto)} 오류 {len(rs) - len(ok)} | "
            f"{statistics.median(t):.1f}/{p90(t):.1f}/{max(t):.1f}초")


for scene in ["BCD", "B", "C", "D"]:
    for c in (A, B):
        print(f"{c:6s} {scene:3s} {summ([r for r in rows if r['server'] == c and r['scene'] in scene])}")
for c in (A, B):
    keys = sorted({k for r in rows if r["server"] == c for k in (r.get("stages_ms") or {})})
    st = {k: statistics.median(r["stages_ms"][k] for r in rows if r["server"] == c and k in (r.get("stages_ms") or {}))
          for k in keys}
    print(f"{c} 단계 중앙(ms) {st}")
key = lambda r: (r["photo"], r["run"])  # noqa: E731
a = {key(r): r for r in rows if r["server"] == A and "error" not in r}
b = {key(r): r for r in rows if r["server"] == B and "error" not in r}
for scene in ["BCD", "B", "C", "D"]:
    d = [(a[k]["total_ms"] - b[k]["total_ms"]) / 1000 for k in a if k in b and a[k]["scene"] in scene]
    if d:
        print(f"짝 차이 {scene} ({A} − {B}): 중앙 {statistics.median(d):+.1f}초, {A} 이 빠름 {sum(x < 0 for x in d)}/{len(d)}")
for r in rows:
    if r.get("points") != TRUTH[r["scene"]] or r.get("auto_block") is not None or "error" in r:
        print(f"  {r['server']:5s} {r['scene']} {r['photo']}#{r['run']} 점수 {r.get('points')} 막음 {r.get('auto_block')} "
              f"경고 {r.get('warnings')} 오류 {r.get('error', '')[:120]}")
