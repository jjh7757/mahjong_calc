"""서버 app/local_read.py 가 벤치(표 1-26·1-28)와 같은 답인지 본다(노트북, API 없음). 시험 사진을 학습하지 않은 나눔 모델로.
  python -I -X utf8 experiments/tile_classifier/server_bench/local_check.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.argv = [sys.argv[0], "--r2"]
from rules_core import rv  # noqa: E402,F401  서버 코드 경로를 잡는다
from app import local_read as lr  # noqa: E402
from det_eval import hr, hy, sg  # noqa: E402

meta = json.loads((HERE / "meta.json").read_text(encoding="utf-8"))
base = json.loads((HERE.parent / "data" / "det" / "rules_r2.json").read_text(encoding="utf-8"))["+줄"]["photos"]
truth = {s["name"]: s for s in sg.eval_scenes() if s["hand"] is not None}  # 가림 사진 뺌
readers = {}
key = lambda melds: sorted(" ".join(sorted(m.split())) for m in melds)
same = ok = auto = bad = framed = 0
secs = []
for p in meta["photos"]:
    if p["name"] not in truth:
        continue
    k = (p["det"], p["part"])
    r = readers.setdefault(k, lr.LocalReader(det_model=HERE / "models" / f"det_fold_{p['det']}.onnx", cls_model=HERE / "models" / f"cls_{p['part']}.onnx"))
    o = r.read_seat((HERE / "crops" / f"{p['name']}.jpg").read_bytes(), p["frac"])
    b, s = base[p["name"]], truth[p["name"]]
    a = sorted(o["hand"]) == sorted(b["hand"].split()) and key(o["melds"]) == key(b["melds"]) and o["framed"] == b["framed"]
    w = 2 if not p["name"].startswith("2026") else 1
    y_ok = hr.same(o["hand"], o["melds"], s)
    y_pass = bool(o["hand"]) and not o["block"] and hy.check(o["hand"], [m.split() for m in o["melds"]])[0]
    same += a
    framed += o["framed"]
    ok += w * y_ok
    auto += w * y_pass
    bad += w * (y_pass and not y_ok)
    secs.append(o["ms"]["total"])
    if not a:
        print("다름", p["name"][-6:], o["framed"], " ".join(o["hand"]), o["melds"], "| 벤치", b["framed"], b["hand"], b["melds"])
print(f"벤치와 같은 사진 {same}/{len(secs)}, 틀 {framed}/{len(secs)}, 답 맞음 {ok}/37, 자동 {auto}(틀림 {bad}), 시간 중앙 {sorted(secs)[len(secs) // 2]}ms")
