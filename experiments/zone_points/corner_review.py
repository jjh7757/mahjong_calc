"""라벨 8점을 한 점씩 확대해 눈으로 보는 그림(2026-11-02, API 없음). 줄마다 구간(또는 갤러리 사진) 하나, 칸마다 점 하나, 칸 격자선은 칸 폭의 1/4.
  python -I experiments/zone_points/corner_review.py <입력 json> <출력 앞이름> [--half 0.04] [--per 8]
입력 json: 이름 → {src, felt, device}. 사진 밖 점은 칸을 어둡게 하고 좌표를 적는다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from propose import load  # noqa: E402

CELL = 150
LABEL = 90


def cell(im: Image.Image, x: float, y: float, half: float, col: tuple) -> Image.Image:
    W, H = im.size
    r = half * W
    cx, cy = x * W, y * H
    crop = im.crop((round(cx - r), round(cy - r), round(cx + r), round(cy + r))).resize((CELL, CELL), Image.BILINEAR)
    d = ImageDraw.Draw(crop)
    for k in (CELL // 4, 3 * CELL // 4):
        d.line((k, 0, k, CELL), fill=(255, 255, 255), width=1)
        d.line((0, k, CELL, k), fill=(255, 255, 255), width=1)
    m = CELL // 2
    d.line((m - 12, m, m + 12, m), fill=col, width=1)
    d.line((m, m - 12, m, m + 12), fill=col, width=1)
    if not (0 <= x <= 1 and 0 <= y <= 1):
        d.rectangle((0, 0, CELL, 14), fill="black")
        d.text((2, 1), f"out {x:.2f},{y:.2f}", fill="red")
    d.rectangle((0, 0, CELL - 1, CELL - 1), outline=(80, 80, 80))
    return crop


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("json")
    ap.add_argument("out")
    ap.add_argument("--half", type=float, default=0.04)
    ap.add_argument("--per", type=int, default=8)
    a = ap.parse_args()
    rows = json.loads(Path(a.json).read_text(encoding="utf-8"))
    names = list(rows)
    for page in range(0, len(names), a.per):
        part = names[page : page + a.per]
        sh = Image.new("RGB", (LABEL + 8 * CELL, len(part) * CELL), (20, 20, 20))
        d = ImageDraw.Draw(sh)
        for j, n in enumerate(part):
            r = rows[n]
            d.text((2, j * CELL + 4), n.replace("20261031_", "")[:14], fill="white")
            d.text((2, j * CELL + 20), "felt 0-3", fill=(255, 230, 0))
            d.text((2, j * CELL + 34), "dev 4-7", fill=(255, 0, 255))
            im = load(r["src"]).convert("RGB")
            for i, (key, col) in enumerate((("felt", (255, 230, 0)), ("device", (255, 0, 255)))):
                for k, pt in enumerate(r.get(key) or []):
                    sh.paste(cell(im, pt[0], pt[1], a.half if key == "felt" else a.half * 0.75, col), (LABEL + (i * 4 + k) * CELL, j * CELL))
        p = f"{a.out}_{page // a.per}.jpg"
        sh.save(p, quality=88)
        print(p, len(part))


if __name__ == "__main__":
    main()
