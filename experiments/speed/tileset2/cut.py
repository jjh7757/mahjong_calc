"""패 세트 정면 사진(full_set.webp, 4칸 상자)에서 패를 한 장씩 잘라 tiles/<code>_<줄>.png 로 저장.

상자마다 패 영역 네 모서리 사이를 고르게 나눈다. 확인용 그림은 cut_debug.png.
  python -I experiments/speed/tileset2/cut.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).parent
# 상자마다 패 영역의 네 모서리(왼위, 오른위, 왼아래, 오른아래 — 10px 격자를 겹쳐 눈으로 잡음)와 칸 이름.
# 상자가 조금 기울어 줄마다 시작 위치가 달라 네 모서리 사이를 고르게 나눈다.
# 오른쪽 아래는 東南西北中發白, 꽃패, 적5(위부터 0m 0p 0p 0s).
BOXES = {
    "man": (((55, 33), (402, 33), (45, 235), (402, 235)), [[f"{n}m" for n in range(1, 10)]] * 4),
    "pin": (((410, 35), (758, 35), (410, 237), (770, 237)), [[f"{n}p" for n in range(1, 10)]] * 4),
    "sou": (((40, 245), (400, 245), (20, 465), (402, 465)), [[f"{n}s" for n in range(1, 10)]] * 4),
    "hon": (((410, 247), (780, 247), (412, 465), (792, 465)),
            [["1z", "2z", "3z", "4z", "7z", "6z", "5z", "fl", r] for r in ("0m", "0p", "0p", "0s")]),
}


def point(corners, u: float, v: float) -> tuple[float, float]:
    (tl, tr, bl, br) = corners
    top = (tl[0] + (tr[0] - tl[0]) * u, tl[1] + (tr[1] - tl[1]) * u)
    bot = (bl[0] + (br[0] - bl[0]) * u, bl[1] + (br[1] - bl[1]) * u)
    return top[0] + (bot[0] - top[0]) * v, top[1] + (bot[1] - top[1]) * v


def main() -> None:
    im = Image.open(ROOT / "full_set.webp").convert("RGB")
    out = ROOT / "tiles"
    out.mkdir(exist_ok=True)
    dbg = im.copy()
    d = ImageDraw.Draw(dbg)
    for name, (corners, names) in BOXES.items():
        nr, nc = len(names), len(names[0])
        for r in range(nr):
            for c in range(nc):
                pts = [point(corners, (c + i) / nc, (r + j) / nr) for i in (0, 1) for j in (0, 1)]
                box = (round(min(x for x, _ in pts)) + 1, round(min(y for _, y in pts)) + 1,
                       round(max(x for x, _ in pts)) - 1, round(max(y for _, y in pts)) - 1)
                im.crop(box).save(out / f"{names[r][c]}_{name}{r}.png")
                d.rectangle(box, outline="red")
                d.text((box[0] + 2, box[1] + 2), names[r][c], fill="blue")
    dbg.save(ROOT / "cut_debug.png")


if __name__ == "__main__":
    main()
