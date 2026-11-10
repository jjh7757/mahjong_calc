"""뒤집힌 패 혼동표: 라벨 있는 세운 크롭(data/harvest_obb, 1,168장)을 0°·180° 로 분류기에 넣는다(2026-11-07, 사용자 "먼저 재 줘").

왜: 11-07 매장 143234 강 끝 3만이 바로 세우면 3m 0.95 인데 180° 돌리면 2m 0.978 이라, 방향을 모르는 패를 0°·180° 중 확신 높은 쪽으로
고르는 서버 read_any(강 끝·표시패 등)가 2만을 골랐다. 다른 패도 뒤집으면 다른 패로 확신하는지 새 사진 없이 본다.

재는 것(크롭마다):
  - 0° 답 / 180° 답과 확신
  - read_any 규칙(둘 중 확신 높은 쪽)의 답 — 패가 바로 놓였을 때
  - 패가 거꾸로 놓였을 때(크롭을 180° 돌린 것을 입력으로) read_any 답 — 사실상 같은 두 확률의 다른 쪽 비교라 대칭

모델: 서버 기본(LOCAL_CLS_MODEL 없으면 app/assets/tile-cls-mnv3s-v2.onnx = cls4_all, 이 크롭을 세운 방향으로 학습함) — 운영이 실제로 쓰는 값.
--model 로 나눔 모델(server_bench/models/cls4_<part>.onnx, 그 part 를 안 배움)도 잰다.

  python -I -X utf8 experiments/tile_classifier/flip_check.py [--model 경로] [--out data/flip_check.json]
"""
import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
REPO = os.environ.get("RECOGNIZER_REPO", "C:/Users/jjh7757/dev/mahjong-recognizer")

ap = argparse.ArgumentParser()
ap.add_argument("--model", default="")
ap.add_argument("--out", default=str(HERE / "data" / "flip_check.json"))
a = ap.parse_args()
if a.model:
    os.environ["LOCAL_CLS_MODEL"] = a.model
sys.path.insert(0, REPO)

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from app import local_read as lr  # noqa: E402

idx = json.load(open(HERE / "data" / "harvest_obb" / "index.json", encoding="utf-8"))
reader = lr.LocalReader()
C = lr.CLASSES

rows = []
B = 64
for i in range(0, len(idx), B):
    part = idx[i:i + B]
    ims = [Image.open(HERE / "data" / "harvest_obb" / "crops" / x["file"]).convert("RGB") for x in part]
    p0 = reader.probs(ims)
    p180 = reader.probs([im.rotate(180, expand=True) for im in ims])
    for x, a0, a1 in zip(part, p0, p180):
        t0, c0 = C[int(a0.argmax())], float(a0.max())
        t1, c1 = C[int(a1.argmax())], float(a1.max())
        rows.append({"file": x["file"], "photo": x["photo"], "part": x["part"], "kind": x.get("kind"), "tile": x["tile"],
                     "up": t0, "up_conf": round(c0, 3), "flip": t1, "flip_conf": round(c1, 3), "up_true_p_flip": round(float(a1[C.index(x["tile"])]) if x["tile"] in C else -1, 3),
                     "any": t0 if c0 >= c1 else t1})

n = len(rows)
up_ok = sum(r["up"] == r["tile"] for r in rows)
flip_ok = sum(r["flip"] == r["tile"] for r in rows)
any_ok = sum(r["any"] == r["tile"] for r in rows)
any_wrong_by_flip = [r for r in rows if r["up"] == r["tile"] and r["any"] != r["tile"]]
conf = Counter((r["tile"], r["flip"]) for r in rows if r["flip"] != r["tile"])
by_tile = {}
for r in rows:
    d = by_tile.setdefault(r["tile"], {"n": 0, "flip_ok": 0, "any_wrong": 0})
    d["n"] += 1
    d["flip_ok"] += r["flip"] == r["tile"]
    d["any_wrong"] += r["up"] == r["tile"] and r["any"] != r["tile"]

print(f"크롭 {n}장, 모델 {lr.CLS_MODEL}")
print(f"바로 세운 방향 정답 {up_ok}/{n}")
print(f"180° 뒤집은 입력 정답 {flip_ok}/{n}")
print(f"read_any 규칙(0°·180° 중 확신 높은 쪽) 정답 {any_ok}/{n} — 바로 세우면 맞는데 뒤집은 쪽이 이겨 틀린 것 {len(any_wrong_by_flip)}")
print("뒤집으면 다른 패로 읽는 짝(정답 → 뒤집은 답: 수) 상위:")
for (t, f), k in conf.most_common(25):
    print(f"  {t} → {f}: {k}")
print("read_any 로 틀리는 크롭(바로 세우면 맞음):")
for r in sorted(any_wrong_by_flip, key=lambda r: -r["flip_conf"]):
    print(f"  {r['photo']} {r['file']} {r['tile']} 바로 {r['up_conf']} / 뒤집으면 {r['flip']} {r['flip_conf']}")
json.dump({"model": str(lr.CLS_MODEL), "n": n, "up_ok": up_ok, "flip_ok": flip_ok, "any_ok": any_ok,
           "any_wrong_by_flip": any_wrong_by_flip, "pairs": [[t, f, k] for (t, f), k in conf.most_common()], "by_tile": by_tile, "rows": rows},
          open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("저장", a.out)
