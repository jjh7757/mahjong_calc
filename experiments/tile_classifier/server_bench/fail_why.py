"""자체 모델(표 1-26 마지막 줄, 나눔 모델)이 틀 잡기에 실패한 사진을 어느 조건에서 왜 떨어졌는지 적는다(노트북, API 없음).
  python -I -X utf8 experiments/tile_classifier/server_bench/fail_why.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from rules_core import rv, st  # noqa: E402
from app import local_read as lr  # noqa: E402

meta = json.loads((HERE / "meta.json").read_text(encoding="utf-8"))
sys.stdout.reconfigure(encoding="utf-8")
readers = {}
for p in meta["photos"]:
    r = readers.setdefault(p["det"], lr.LocalReader(det_model=HERE / "models" / f"det_fold_{p['det']}.onnx", cls_model=HERE / "models" / f"cls_{p['part']}.onnx", threads=2))
    rgb = np.asarray(Image.open(HERE / "crops" / f"{p['name']}.jpg").convert("RGB"))
    faces = rv.dedupe(rv.keep_faces(r.detect(rgb), rv.white_mask(rgb)))
    fr = lr.split_frame(rgb, faces, int(rgb.shape[1] * p["frac"]))
    if fr is not None and lr.frame_ok(fr, rgb):
        continue
    if fr is None:
        print(p["name"][-6:], "틀 없음", "상자", len(faces))
        continue
    hx1 = fr.hand[-1][0] + fr.hand[-1][2]
    print(p["name"][-6:], "장수", fr.count, "손패", len(fr.hand), "떨어진", 1 if fr.separate else 0, "울기", [len(m) for m in fr.melds], "나머지", len(fr.loose), "상자", len(faces),
          "| 손패 무늬0", sum(st.ink(rgb, x) < lr.BLANK for x in fr.hand), "| 나머지 위치", [(x[0] - hx1, x[1], x[2], x[3]) for x in fr.loose][:6], "tw", round(fr.tw), "th", round(fr.th), "크롭", rgb.shape[:2])
