"""설정용 도움: 시각마다 프레임을 줄여(또는 영역을 잘라) 저장해 눈으로 본다.

  python -X utf8 snap.py <출력 폴더> <시각> [<시각> ...] [--crop x0,y0,x1,y1] [--scale 0.5] [--side left]
시각 = '15:13:28.0' 꼴(11-14 KST). 가장 가까운 프레임을 쓴다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402


def main():
    a = sys.argv[1:]
    out = Path(a.pop(0))
    crop, scale, side = None, 0.5, None
    ts = []
    while a:
        x = a.pop(0)
        if x == "--crop":
            crop = [int(v) for v in a.pop(0).split(",")]
        elif x == "--scale":
            scale = float(a.pop(0))
        elif x == "--side":
            side = a.pop(0)
        else:
            ts.append(x)
    out.mkdir(parents=True, exist_ok=True)
    for t in ts:
        ms = hc.nearest(hc.to_ms(t))
        rgb = hc.load(ms)
        if crop:
            rgb = hc.band_crop(rgb, crop, side or "bottom")
        im = Image.fromarray(rgb)
        if scale != 1:
            im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
        if not crop:  # 100px 눈금(원본 좌표)
            d = ImageDraw.Draw(im)
            for v in range(0, 1496, 100):
                s = v * scale
                d.line([(s, 0), (s, 6)], fill=(255, 0, 0))
                d.line([(0, s), (6, s)], fill=(255, 0, 0))
                d.text((s + 1, 7), str(v // 100), fill=(255, 0, 0))
                d.text((7, s + 1), str(v // 100), fill=(255, 0, 0))
        name = f"{hc.hms(ms).replace(':', '')}.jpg"
        im.save(out / name, quality=90)
        print(out / name, ms)


if __name__ == "__main__":
    main()
