"""白(5z)는 무늬가 없어 harvest.py 의 무늬 거르기에 빠진다. 무늬 적은 앞면 상자만 따로 모아 눈으로 고른다(2026-11-01). API 없음.
  python -I experiments/tile_classifier/harvest_blank.py
결과 data/harvest/blank/{*.jpg, index.json, sheet_*.jpg}
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harvest as hv  # noqa: E402
from harvest import rv, st  # noqa: E402

OUT = hv.OUT / "blank"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    det = rv.TileDetector(conf=0.1)
    photos = sorted(hv.EXP.glob("visit_20261031/captures/*/original.jpg"), key=lambda p: p.parent.name)
    rows = []
    for p in photos:
        im = Image.open(p).convert("RGB")
        if im.width < 3000:
            continue
        rgb = np.asarray(im)
        H, W = rgb.shape[:2]
        ws, hs = W // hv.GRID, H // hv.GRID
        out = []
        for yy in range(0, H - hs + 1, hs // 2):
            for xx in range(0, W - ws + 1, ws // 2):
                out += [(int(x + xx), int(y + yy), int(w), int(h)) for x, y, w, h in det.detect(np.ascontiguousarray(rgb[yy:yy + hs, xx:xx + ws]))]
        bs = rv.dedupe(rv.keep_faces(out, rv.white_mask(rgb)))
        if not bs:
            continue
        short = statistics.median(min(b[2], b[3]) for b in bs)
        bs = [b for b in st.on_table(bs, rgb, st.TABLE_REACH * short * 1.3)
              if st.ink(rgb, b) < 0.05 and 0.6 * short <= min(b[2], b[3]) <= 1.5 * short and max(b[2], b[3]) <= 2.2 * short]
        for b in bs:
            f = f"b{len(rows):04d}.jpg"
            hv.cut(rgb, b).save(OUT / f, quality=92)
            rows.append(dict(id=f[:-4], file=f, photo=p.parent.name, day=p.parent.name[:8], box=list(b)))
        print(p.parent.name, len(bs), flush=True)
    (OUT / "index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    cell, cols = 76, 16
    for k in range(0, len(rows), cols * 9):
        part = rows[k:k + cols * 9]
        s = Image.new("RGB", (cols * cell, (len(part) // cols + 1) * (cell + 14)), "white")
        d = ImageDraw.Draw(s)
        for i, r in enumerate(part):
            t = Image.open(OUT / r["file"])
            t.thumbnail((cell, cell))
            x, y = (i % cols) * cell, (i // cols) * (cell + 14)
            s.paste(t, (x, y))
            d.text((x + 1, y + cell), r["id"], fill="blue")
        s.save(OUT / f"sheet_{k // (cols * 9)}.jpg", quality=88)
    print("합계", len(rows))


if __name__ == "__main__":
    main()
