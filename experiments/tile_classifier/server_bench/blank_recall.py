"""2회차 검출기가 白(무늬 0 상자)을 얼마나 찾나(2026-11-02, 노트북, API 없음). 사진을 학습하지 않은 나눔 모델만.
정답 = boxes_final.json 의 무늬 0 상자. 사람이 더한 상자(det_review ADD)는 모델 답에서 온 것이 아니라 따로 센다. 통째 + 토막 9장 검출(det_relabel 과 같음).
  python -I -X utf8 experiments/tile_classifier/server_bench/blank_recall.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
TC = HERE.parent
sys.path.insert(0, str(TC))
from rules_core import st  # noqa: E402
from app import local_read as lr  # noqa: E402
import det_build as db  # noqa: E402
import det_review as dr  # noqa: E402

BCD = {"k25", "k28", "k15", "k26", "k12", "k16"}
AE = {"k00", "k04", "k20", "k24"}
rows = json.loads((TC / "data" / "det" / "boxes_final.json").read_text(encoding="utf-8"))
readers = {k: lr.LocalReader(det_model=HERE / "models" / f"det_fold_{k}.onnx", cls_model=HERE / "models" / "cls_pm.onnx") for k in "ab"}
added = {(n, tuple(b)) for n, bs in dr.ADD.items() for b in bs}


def boxes_of(r: lr.LocalReader, rgb: np.ndarray) -> list:
    H, W = rgb.shape[:2]
    out = list(r.detect(rgb))
    for y0 in (0, (H - db.TH) // 2, H - db.TH):
        for x0 in (0, (W - db.TW) // 2, W - db.TW):
            for x, y, w, h in r.detect(rgb[y0:y0 + db.TH, x0:x0 + db.TW]):
                out.append((x + x0, y + y0, w, h))
    return out


def hit(b, boxes) -> bool:
    for x, y, w, h in boxes:
        ix = max(0, min(b[0] + b[2], x + w) - max(b[0], x))
        iy = max(0, min(b[1] + b[3], y + h) - max(b[1], y))
        if ix * iy > 0.5 * b[2] * b[3]:
            return True
    return False


sys.stdout.reconfigure(encoding="utf-8")
tally: dict = {}
for name, r in rows.items():
    if name in AE:
        continue
    folds = "ab" if name in BCD else ("b" if name < "20261031_14" else "a")
    rgb = np.asarray(Image.open(r["path"]).convert("RGB"))
    for k in folds:
        found = boxes_of(readers[k], rgb)
        miss = []
        for b in r["boxes"]:
            blank = st.ink(rgb, tuple(b)) == 0
            kind = "손으로 더한 白" if (name, (b[0], b[1], b[0] + b[2], b[1] + b[3])) in added else "白" if blank else "무늬 패"
            t = tally.setdefault((k, "BCD" if name in BCD else "매장", kind), [0, 0])
            ok = hit(b, found)
            t[0] += ok
            t[1] += 1
            if kind != "무늬 패" and not ok:
                miss.append(kind)
        if miss:
            print(k, name[-6:], "놓침", miss, flush=True)
for key in sorted(tally):
    print(f"fold_{key[0]} {key[1]} {key[2]}: {tally[key][0]}/{tally[key][1]}")
