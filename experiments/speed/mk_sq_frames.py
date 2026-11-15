"""헤드 1:1 일 때 추적 입력 흉내(2026-11-13, 사용자 "추적이랑 겹쳐 보기도 1:1 로 가능하니?").
표 12-9 와 같은 11-07 14장을 robust `sqfit`(탁자 전체가 들어가는 정사각형, 격자 중심) 으로 자르고 2992 로 맞춘 뒤 헤드처럼 줄인다:
  <키>_997.jpg  = 2992 를 3픽셀 건너뛰기(헤드 /preview 기본 960 요청, 4:3 의 1020 자리), 품질 75
  <키>_1496.jpg = 2992 의 2×2 평균(헤드 녹화, 4:3 의 2040 자리), 품질 85
격자는 자른 좌표로 옮김(dora 는 격자 기준 상대값이라 그대로).

  python -X utf8 experiments/speed/mk_sq_frames.py   → experiments/speed/results/res_frames_1107_sq/
"""
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
SRC = HERE / "results" / "res_frames_1107"
OUT = HERE / "results" / "res_frames_1107_sq"
meta = json.loads((HERE / "robust" / "meta.json").read_text(encoding="utf-8"))["sqfit"]
grids = json.loads((SRC / "grids.json").read_text())
OUT.mkdir(parents=True, exist_ok=True)
og = {}
for k, g in grids.items():
    a = np.asarray(Image.open(SRC / f"{k}_4080.jpg").convert("RGB"))
    H, W = a.shape[:2]
    c = meta[k]["crop"]
    x0, y0, side = c["x0"], c["y0"], c["side"]
    canvas = np.full((side, side, 3), 30, np.uint8)
    sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(W, x0 + side), min(H, y0 + side)
    canvas[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = a[sy0:sy1, sx0:sx1]
    sq = np.asarray(Image.fromarray(canvas).resize((2992, 2992), Image.BOX)) if side != 2992 else canvas
    Image.fromarray(sq[::3, ::3]).save(OUT / f"{k}_997.jpg", quality=75)
    h2 = sq.reshape(1496, 2, 1496, 2, 3).mean(axis=(1, 3)).round().astype(np.uint8)
    Image.fromarray(h2).save(OUT / f"{k}_1496.jpg", quality=85)

    def mx(x):
        return round((x * W / 1000 - x0) * 1000 / side)

    def my(y):
        return round((y * H / 1000 - y0) * 1000 / side)

    n = dict(g, x1=mx(g["x1"]), x2=mx(g["x2"]), y1=my(g["y1"]), y2=my(g["y2"]))
    if g.get("sticks"):
        s = g["sticks"]
        n["sticks"] = [my(s[0]), mx(s[1]), my(s[2]), mx(s[3])]
    og[k] = n
    print(k, side, n)
(OUT / "grids.json").write_text(json.dumps(og))
