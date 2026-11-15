"""정사각형 거치 흉내용: 사진마다 모든 패 상자(역할 판독 전체 상자)를 감싸는 범위를 잰다(2026-11-13, 사용자 "제대로 거치했을 경우만").
robust_suite.py make --only sqfit 가 이 값으로 '탁자 전체가 들어오게 넓혀 자른 뒤 짧은 변으로 줄인' 정사각형을 만든다.

  python -X utf8 experiments/speed/sq_extent.py   → experiments/speed/robust/sq_extent.json
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, os.environ.get("RECOGNIZER_REPO", "C:/Users/jjh7757/dev/mahjong-recognizer"))
import seat_grow as sg  # noqa: E402
from app import local_read as lr  # noqa: E402
from app import roles  # noqa: E402
from app.recognizer import prepare_image  # noqa: E402

reader = lr.LocalReader()
out = {}
for s in sg.eval_scenes(with_1107=True):
    jpeg = prepare_image(Path(s["path"]).read_bytes(), 4080)
    o = roles.read_roles(reader, jpeg, s["side"], s["grid"], "hybrid")
    bx = [r["box"] for r in o["roles"]]
    x0 = min(b[0] for b in bx); y0 = min(b[1] for b in bx)
    x1 = max(b[0] + b[2] for b in bx); y1 = max(b[1] + b[3] for b in bx)
    out[s["name"]] = {"tiles_bbox": [x0, y0, x1, y1], "n": len(bx)}
    print(s["name"], out[s["name"]], flush=True)
(HERE / "robust" / "sq_extent.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
