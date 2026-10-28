"""기기(에뮬레이터) 판독 시간 측정 결과(integration_test/read_grid_timing_test.dart 의 TIMING 줄)를 요약한다.

  python -I experiments/speed/device_timing.py <TIMING JSON 줄 파일>

단계: shrink(사진 줄이기) · analyze(앞면 판정) · crop(자르기) · read(서버 호출, 모두 동시) · pick · 병합·점수.
"""
from __future__ import annotations

import json
import statistics
import sys

POINTS = {"B": "12000", "C": "16000", "D": "18000"}


def main() -> None:
    rows = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8") if line.strip()]
    print(f"{len(rows)}회, 오류 {sum(1 for r in rows if r.get('error'))}, "
          f"점수 정답 {sum(1 for r in rows if r.get('points') == POINTS[r['scene']])}/{len(rows)}")
    stages = ["shrink", "analyze", "crop", "read", "pick"]
    print(f"{'':10s}" + "".join(f"{s:>9s}" for s in stages + ["merge", "total"]))
    for r in rows:
        st = r.get("stages_ms") or {}
        vals = [st.get(s, 0) for s in stages] + [r.get("merge_score_ms", 0), r["total_ms"]]
        print(f"{r['scene']} {r['photo']} #{r['run']}" + "".join(f"{v / 1000:9.2f}" for v in vals)
              + f"  {r.get('points')} {r.get('winner')} {r.get('error') or ''}")
    med = lambda k: statistics.median((r.get("stages_ms") or {}).get(k, 0) for r in rows) / 1000  # noqa: E731
    tot = sorted(r["total_ms"] / 1000 for r in rows)
    print("중앙값    " + "".join(f"{med(s):9.2f}" for s in stages)
          + f"{statistics.median(r.get('merge_score_ms', 0) for r in rows) / 1000:9.2f}{statistics.median(tot):9.2f}")
    print(f"전체 최소 {tot[0]:.1f}초, 최대 {tot[-1]:.1f}초. 기기 처리(read 뺀 것) 중앙 "
          f"{statistics.median((r['total_ms'] - (r.get('stages_ms') or {}).get('read', 0)) / 1000 for r in rows):.2f}초")


if __name__ == "__main__":
    main()
