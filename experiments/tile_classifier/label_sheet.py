"""분류기 학습 크롭을 번호 붙인 그림으로(2026-11-07 라벨 감사, 사람/새 세션 검토용).

수확 크롭(review.extra, 라벨 = 예전 분류기 예측 + 일부 사람 수정)과 기본 크롭(data/index.json, 정답 기록에서 붙인 손패 라벨)을
종류 묶음별로 모은다. 크롭 방향은 제각각(뒤집힘·90°)이다.

  python -I -X utf8 experiments/tile_classifier/label_sheet.py --tiles 1m,2m,3m [--name manzu123]   # 수확 크롭 중 그 종류
  python -I -X utf8 experiments/tile_classifier/label_sheet.py --suit m --name full_m                 # 수확 크롭 만수 전부(0m 포함)
  python -I -X utf8 experiments/tile_classifier/label_sheet.py --src base --name full_base            # 기본 크롭 전부
→ data/label_audit/<name>_{index.json, sheet_*.jpg}
"""
import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import review as rw  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--src", default="extra", choices=["extra", "base"])
ap.add_argument("--tiles", default="", help="쉼표로 종류(예 1m,2m,3m)")
ap.add_argument("--suit", default="", help="m|p|s|z — 그 묶음 전부")
ap.add_argument("--name", default="manzu123")
a = ap.parse_args()
if a.src == "extra":
    pool = [dict(file=x["file"], photo=x["photo"], label=x["tile"], path=str(x["path"])) for x in rw.extra()]
else:
    crops = HERE / "data" / "crops"
    pool = [dict(file=x["file"], photo=x.get("photo"), label=x["tile"], path=str(crops / x["file"])) for x in json.loads((HERE / "data" / "index.json").read_text(encoding="utf-8"))]
want = set(a.tiles.split(",")) if a.tiles else None
rows = [r for r in pool if (want is None or r["label"] in want) and (not a.suit or r["label"].endswith(a.suit))]
rows.sort(key=lambda r: (r["label"], r["file"]))
out = HERE / "data" / "label_audit"
out.mkdir(parents=True, exist_ok=True)
for i, r in enumerate(rows):
    r["no"] = i
(out / f"{a.name}_index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
S, cols, per = 220, 8, 32
for k in range(0, len(rows), per):
    part = rows[k:k + per]
    nrow = (len(part) + cols - 1) // cols
    sheet = Image.new("RGB", (S * cols, (S + 24) * nrow), "white")
    d = ImageDraw.Draw(sheet)
    for i, r in enumerate(part):
        im = Image.open(r["path"]).convert("RGB")
        im.thumbnail((S, S))
        x, y = (i % cols) * S, (i // cols) * (S + 24)
        sheet.paste(im, (x, y))
        d.text((x + 4, y + S + 4), f"#{r['no']} label {r['label']}", fill="black")
    sheet.save(out / f"{a.name}_sheet_{k // per:02d}.jpg", quality=90)
print(a.name, "크롭", len(rows), "그림", (len(rows) + per - 1) // per, "저장", out)
