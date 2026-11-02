"""라벨 그림: 사진에 펠트(노랑)·기기(자홍) 네 모서리와 번호를 겹쳐 모음 그림으로 저장한다(2026-11-02, API 없음).
  python -I experiments/zone_points/overlay.py <json> <출력 앞이름> [--names a,b,c] [--kind photo|frame] [--cols 6] [--tw 400]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from propose import load  # noqa: E402


def draw(im: Image.Image, r: dict, tw: int) -> Image.Image:
    W, H = im.size
    th = round(tw * H / W)
    im = im.resize((tw, th))
    d = ImageDraw.Draw(im)
    for key, col in (("felt", (255, 230, 0)), ("device", (255, 0, 255))):
        q = r.get(key)
        if not q:
            continue
        pts = [(x * tw, y * th) for x, y in q]
        d.line(pts + pts[:1], fill=col, width=1)
        for i, (x, y) in enumerate(pts):
            d.ellipse((x - 2, y - 2, x + 2, y + 2), outline=col)
            if key == "felt":
                d.text((x + 3, y + 3), str(i), fill=col)
    return im


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("json")
    ap.add_argument("out")
    ap.add_argument("--names", default="")
    ap.add_argument("--kind", default="")
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--tw", type=int, default=400)
    ap.add_argument("--per", type=int, default=36)
    a = ap.parse_args()
    rows = json.loads(Path(a.json).read_text(encoding="utf-8"))
    names = a.names.split(",") if a.names else [n for n, r in rows.items() if not a.kind or r.get("kind") == a.kind]
    th = round(a.tw * 0.75)
    for page in range(0, len(names), a.per):
        part = names[page : page + a.per]
        nrow = (len(part) + a.cols - 1) // a.cols
        sh = Image.new("RGB", (a.cols * a.tw, nrow * th))
        d = ImageDraw.Draw(sh)
        for i, n in enumerate(part):
            x, y = (i % a.cols) * a.tw, (i // a.cols) * th
            sh.paste(draw(load(rows[n]["src"]).convert("RGB"), rows[n], a.tw).resize((a.tw, th)), (x, y))
            d.rectangle((x, y, x + 110, y + 13), fill="black")
            d.text((x + 2, y + 1), n.replace("20261031_", ""), fill="white")
        p = f"{a.out}_{page // a.per}.jpg"
        sh.save(p, quality=85)
        print(p, len(part))


if __name__ == "__main__":
    main()
