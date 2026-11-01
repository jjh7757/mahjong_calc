"""넓은 구역 낱장 찾기 점검(모델 호출 없음, 2026-11-01). 사진마다 낱장 수·외톨이 수, 떼어 둔 패가 필요한 장면 표시, 그림 results/wide_singles/.

  python -X utf8 experiments/speed/wide_singles.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
import wide_seat as ws  # noqa: E402
from wide_seat import sg  # noqa: E402
from app import river as rv  # noqa: E402
from app import seat_wide as sw  # noqa: E402

OUT = ws.OUT.parent / "wide_singles"
# 줄 밖에 떼어 둔 패가 있는 장면(truth.json 눈 판독). 외톨이 1개면 잡은 것.
WANT_LONE = {"143104": "7s", "165614": "7p", "181209": "9s", "183627": "4m"}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    det = rv.TileDetector(conf=0.04)
    thumbs = []
    for s in sg.scenes():
        k = s["name"][-6:] if s["set"] == "visit" else s["name"]
        im = Image.open(s["path"]).convert("RGB")
        half = sg.crop(im, ws.half_box(s["grid"], s["side"]), s["side"])
        # 앱처럼 JPEG 로 한 번 눌러서(서버가 받는 그림과 같게)
        half = Image.open(io.BytesIO(sg.jpeg(half))).convert("RGB")
        rgb = np.asarray(half)
        fr = sw.locate(rgb, det)
        if fr is None:
            print(k, "틀 못 잡음")
            continue
        print(k, s["side"], f"줄 {len(fr.row)} 낱장 {len(fr.singles)} 외톨이 {sum(fr.lone)}", f"(필요 {WANT_LONE[k]})" if k in WANT_LONE else "", flush=True)
        d = ImageDraw.Draw(half)
        for x in fr.row:
            d.rectangle((x[0], x[1], x[0] + x[2], x[1] + x[3]), outline=(255, 0, 0), width=6)
        for x, lone in zip(fr.singles, fr.lone):
            d.rectangle((x[0], x[1], x[0] + x[2], x[1] + x[3]), outline=(255, 220, 0) if lone else (0, 200, 255), width=10)
        if sum(fr.lone) or k in WANT_LONE:
            half.thumbnail((900, 500))
            d2 = ImageDraw.Draw(half)
            d2.text((5, 5), k, fill=(255, 255, 0), font_size=36)
            thumbs.append(half.copy())
    W = 900 * 2
    H = sum(max(t.height for t in thumbs[i:i + 2]) for i in range(0, len(thumbs), 2))
    sheet = Image.new("RGB", (W, H), (20, 20, 20))
    y = 0
    for i in range(0, len(thumbs), 2):
        pair = thumbs[i:i + 2]
        for j, t in enumerate(pair):
            sheet.paste(t, (j * 900, y))
        y += max(t.height for t in pair)
    sheet.save(OUT / "sheet.jpg", quality=85)


if __name__ == "__main__":
    main()
