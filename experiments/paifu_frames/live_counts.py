"""앱 실시간 강 추적(river_tracker.dart)이 같은 판에서 남긴 버림·가져감 수(track.json 의 rivers.events). 비교용.
python live_counts.py <track 폴더> <t0> <t1>"""
import json
import sys
from pathlib import Path

t = json.loads((Path(sys.argv[1]) / "track.json").read_text(encoding="utf-8"))
ev = [e for e in t["rivers"]["events"] if sys.argv[2] <= e["at"][11:19] <= sys.argv[3]]
d = [e for e in ev if e["kind"] == "discard"]
k = [e for e in ev if e["kind"] == "taken"]
by = {}
for e in d:
    by[e["side"]] = by.get(e["side"], 0) + 1
print(f"버림 {len(d)} {by} · 가져감 {len(k)} {[e['side'] for e in k]}")
