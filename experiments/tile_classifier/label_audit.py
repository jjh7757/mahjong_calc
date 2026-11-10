"""학습 크롭 라벨 감사(2026-11-07): 축 크롭(data/index.json base + review.extra)을 그 크롭을 안 배운 나눔 분류기로 읽어 라벨과 다른 것을 뽑는다.

왜: review.extra(881장 수확 크롭)의 라벨은 사람이 아니라 예전 분류기 예측(r["pred"], conf ≥ 0.6)이라, 뒤집힌 3만을 2만으로 읽던 버릇이
라벨로 들어갔다(flip_check: 세운 크롭 00285·00614·00787 은 三萬, 00456 은 一萬인데 2m). 180° 뒤집기로 학습한 cls5 가 바로 세운 크롭에서
라벨과 다르게 읽은 것을 후보로 모아 사람(새 세션) 검토에 넘긴다.

  python -I -X utf8 experiments/tile_classifier/label_audit.py [--tags cls5,cls5_s1,cls4] → data/label_audit/{index.json, sheet_*.jpg}
"""
import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import review as rw  # noqa: E402
import train as tr  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--tags", default="cls5,cls5_s1,cls4")
a = ap.parse_args()
tags = a.tags.split(",")
base = json.loads((tr.DATA / "index.json").read_text(encoding="utf-8"))
add = rw.extra()
imgs = {x["file"]: Image.open(tr.CROPS / x["file"]).convert("RGB") for x in base}
imgs.update({x["file"]: Image.open(x["path"]).convert("RGB") for x in add})
preds: dict = {}
for part in ("bcd", "am", "pm"):
    held = [dict(x, src="base") for x in base if x["part"] == part] + [dict(x, src="extra", part=part) for x in add if x["half"] == part]
    for tag in tags:
        name = tag.replace("_s1", "") + f"_{part}" + ("_s1" if tag.endswith("_s1") else "")
        p = tr.onnx_pred(tr.MODELS / f"{name}.onnx", [imgs[x["file"]] for x in held])
        for x, y in zip(held, p):
            preds.setdefault(x["file"], {"file": x["file"], "photo": x.get("photo"), "src": x["src"], "part": part, "label": x["tile"]})[tag] = y
rows = [r for r in preds.values() if any(r[t] != r["label"] for t in tags if t.startswith("cls5"))]
out = tr.DATA / "label_audit"
out.mkdir(parents=True, exist_ok=True)
(out / "index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
print("크롭", len(preds), "cls5 가 라벨과 다른 것", len(rows))
for r in rows:
    print(r)
S, per = 220, 12
for k in range(0, len(rows), per):
    part = rows[k:k + per]
    sheet = Image.new("RGB", (S * min(per, len(part)), S + 60), "white")
    d = ImageDraw.Draw(sheet)
    for i, r in enumerate(part):
        im = imgs[r["file"]].copy()
        im.thumbnail((S, S))
        sheet.paste(im, (i * S, 0))
        d.text((i * S + 4, S + 4), f"#{k + i} label {r['label']}", fill="black")
        d.text((i * S + 4, S + 22), " ".join(f"{t}:{r[t]}" for t in tags), fill="blue")
    sheet.save(out / f"sheet_{k // per}.jpg", quality=90)
print("저장", out)
