"""시간 창의 손패 띠 프레임을 대국자 시점으로 나란히 붙여 보기(2026-11-16, 넣은 칸 정답을 눈으로 다시 확인하는 데 씀).

  python -X utf8 stripview.py <판 id> <시작 HH:MM:SS.s> <끝> [--step 2] [--scale 0.9] [--cols 2] [--rows 12] [--pad 40 60] --out <폴더/머리말>
띠는 config 의 sheet_band 를 줄 수직 방향으로 pad(먼 쪽·대국자 쪽 px) 만큼 넓혀 자른다(손·뺀 패가 띠 밖으로 나가서).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402


def font(sz):
    for p in ("C:/Windows/Fonts/malgunbd.ttf", "C:/Windows/Fonts/malgun.ttf"):
        try:
            return ImageFont.truetype(p, sz)
        except OSError:
            pass
    return ImageFont.load_default()


def wide_band(cfg: dict, far: int, near: int) -> list:
    x0, y0, x1, y1 = cfg["sheet_band"]
    side = cfg["side"]
    if side == "left":  # 대국자가 그림 왼쪽 → 대국자 쪽 = x 작은 쪽
        return [max(0, x0 - near), y0, x1 + far, y1]
    if side == "right":
        return [x0 - far, y0, min(1496, x1 + near), y1]
    if side == "bottom":
        return [x0, y0 - far, x1, min(1496, y1 + near)]
    return [x0, max(0, y0 - near), x1, y1 + far]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game")
    ap.add_argument("t0")
    ap.add_argument("t1")
    ap.add_argument("--step", type=int, default=2)
    ap.add_argument("--scale", type=float, default=0.9)
    ap.add_argument("--cols", type=int, default=2)
    ap.add_argument("--rows", type=int, default=12)
    ap.add_argument("--pad", type=int, nargs=2, default=[40, 60], help="먼 쪽·대국자 쪽 여유(px)")
    ap.add_argument("--xr", type=int, nargs=2, help="돌린 그림에서 가로 범위만 자르기(px)")
    ap.add_argument("--title", help="그림 맨 위에 적을 글(| 로 줄 나눔) — 사용자 확인용")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cfg = hc.config(a.game)
    band = wide_band(cfg, *a.pad)
    mss = hc.frame_range(hc.to_ms(a.t0), hc.to_ms(a.t1))[::a.step]
    f = font(15)
    cells = []
    for ms in mss:
        v = hc.band_crop(hc.load(ms), band, cfg["side"])
        if a.xr:
            v = v[:, a.xr[0]:a.xr[1]]
        im = Image.fromarray(v)
        im = im.resize((round(im.width * a.scale), round(im.height * a.scale)), Image.LANCZOS)
        d = ImageDraw.Draw(im)
        t = hc.hms(ms)[3:]
        d.rectangle([0, 0, 78, 20], fill=(0, 0, 0))
        d.text((3, 1), t, fill=(255, 255, 0), font=f)
        cells.append(im)
    if not cells:
        print("프레임 없음")
        return
    cw, ch = cells[0].size
    per = a.cols * a.rows
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    for pi in range(0, len(cells), per):
        part = cells[pi:pi + per]
        rows = -(-len(part) // a.cols)
        sheet = Image.new("RGB", (a.cols * cw + (a.cols - 1) * 4, rows * (ch + 4)), (30, 30, 30))
        for i, im in enumerate(part):  # 세로로 먼저 채움(위→아래가 시간 순)
            c, r = divmod(i, rows)
            sheet.paste(im, (c * (cw + 4), r * (ch + 4)))
        if a.title:
            lines = a.title.split("|")
            tf, sf = font(26), font(19)
            hh = 44 + 28 * (len(lines) - 1) + 10
            top = Image.new("RGB", (sheet.width, hh), (20, 20, 20))
            d = ImageDraw.Draw(top)
            d.text((10, 6), lines[0], fill=(255, 255, 255), font=tf)
            for li, ln in enumerate(lines[1:]):
                d.text((10, 44 + 28 * li), ln, fill=(255, 220, 90), font=sf)
            both = Image.new("RGB", (sheet.width, hh + sheet.height), (20, 20, 20))
            both.paste(top, (0, 0))
            both.paste(sheet, (0, hh))
            sheet = both
        p = out.parent / f"{out.name}_{pi // per + 1:02d}.jpg"
        sheet.save(p, quality=88)
        print(p, sheet.size, hc.hms(mss[pi]), "~", hc.hms(mss[min(pi + per, len(mss)) - 1]))


if __name__ == "__main__":
    main()
