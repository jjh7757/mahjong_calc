"""bench.py 결과를 torch 판(frame_rules.py --r2, 표 1-26 마지막 줄)과 맞춰 보고 정답을 채점한다(노트북, API 없음).
  python -I -X utf8 experiments/tile_classifier/server_bench/score.py <bench 출력 파일>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.argv, path = [sys.argv[0], "--r2"], sys.argv[1]
from det_eval import hr, hy, sg  # noqa: E402

truth = {s["name"]: s for s in sg.eval_scenes() if s["hand"] is not None}  # 가림 사진 뺌
base = json.loads((HERE.parent / "data" / "det" / "rules_r2.json").read_text(encoding="utf-8"))["+줄"]["photos"]
key = lambda melds: sorted(" ".join(sorted(m.split())) for m in melds)
rows = {}
for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
    i = line.find("RESULT ")
    if i >= 0:
        r = json.loads(line[i + 7:])
        rows.setdefault(r["name"], r)
same = ok = auto = bad = framed = 0
for n, r in rows.items():
    if n not in truth:
        continue
    s, b = truth[n], base[n]
    a = sorted(r["hand"]) == sorted(b["hand"].split()) and key(r["melds"]) == key(b["melds"]) and r["framed"] == b["framed"]
    y_ok = hr.same(r["hand"], r["melds"], s)
    y_pass = bool(r["hand"]) and not r["block"] and hy.check(r["hand"], [m.split() for m in r["melds"]])[0]
    w = 2 if not n.startswith("2026") else 1
    same += a
    framed += r["framed"]
    ok += w * y_ok
    auto += w * y_pass
    bad += w * (y_pass and not y_ok)
    if not a:
        print("다름", n[-6:], "| ONNX", r["framed"], " ".join(r["hand"]), r["melds"], "| torch", b["framed"], b["hand"], b["melds"])
print(f"torch 판과 같은 사진 {same}/{len(rows)}, 틀 {framed}/{len(rows)}, 답 맞음 {ok}/37, 자동 {auto}(틀림 {bad})")
