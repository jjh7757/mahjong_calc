"""지금 운영 틀(한 장 규칙) vs 새 틀(나눔 + 탁자 끝 밖 지우기)을 B·C·D 원본 6장에 나란히 그린다.

  python -I -X utf8 experiments/speed/seat_frame_side.py   → results/frame_side/<장면>.png, <장면>_sheet.png

틀 그림 위 = 지금, 아래 = 새(탁자 밖은 어둡게). 조각 그림도 위 = 지금, 아래 = 새.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
import seat_prior as sp  # noqa: E402
import seat_split_check as chk  # noqa: E402
import seat_zones as sz  # noqa: E402

from app import seat  # noqa: E402

OUT = Path(__file__).parent / "results" / "frame_side"
FONT = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 34)


def titled(im: Image.Image, title: str) -> Image.Image:
    out = Image.new("RGB", (im.width, im.height + 50), "white")
    ImageDraw.Draw(out).text((10, 6), title, fill=(0, 0, 0), font=FONT)
    out.paste(im, (0, 50))
    return out


def stack(ims: list[Image.Image]) -> Image.Image:
    w = max(i.width for i in ims)
    out = Image.new("RGB", (w, sum(i.height for i in ims) + 10 * (len(ims) - 1)), (200, 200, 200))
    y = 0
    for i in ims:
        out.paste(i, (0, y))
        y += i.height + 10
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    det = sp.detector()
    for c in sz.cases():
        if "울기+" in c["name"]:
            continue
        rgb, frac, stem = c["rgb"], sz.HAND_FRAC[c["scene"]], c["name"].replace(" ", "_")
        now = seat.frame(rgb, det)
        new = seat.frame(rgb, det, hand_frac=frac, table=True)
        frames, sheets = [], []
        for fr, table, lab in ((now, False, "지금(운영)"), (new, True, "새(나눔 + 탁자 지우기)")):
            chk.TABLE = table
            tmp = OUT / "_tmp.png"
            chk.draw(rgb, fr, frac, tmp)
            how = "틀 없음 → 통째 읽기" if fr is None else ("나눔 경로" if fr.split else "한 장 규칙") + f" {fr.summary()}"
            frames.append(titled(Image.open(tmp).convert("RGB"), f"{c['name']} {lab}: {how}"))
            if fr is not None:
                sheets.append(titled(Image.open(io.BytesIO(seat.sheet(rgb, fr))).convert("RGB"), f"{c['name']} {lab}"))
        stack(frames).save(OUT / f"{stem}.png")
        if sheets:
            stack(sheets).save(OUT / f"{stem}_sheet.png")
        print(stem, "지금", now.summary() if now else None, "| 새", new.summary() if new else None, flush=True)
    (OUT / "_tmp.png").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
