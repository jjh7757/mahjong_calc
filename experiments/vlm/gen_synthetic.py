"""CC0 패 이미지(FluffyStuff/riichi-mahjong-tiles)로 정답을 아는 합성 손패 사진을 만든다.

    python gen_synthetic.py <출력 폴더> [--count 12] [--seed 1]

출력: NN.jpg + labels.json ({"01.jpg": "123m456p0s11z..."})
실제 사진 대용이므로 녹색 매트, 기울기, 원근, 블러, 조명 차이를 조금씩 넣는다.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

TILE_DIR = Path(__file__).parent / "tiles"

NAMES = {
    **{f"{n}m": f"Man{n}" for n in range(1, 10)},
    **{f"{n}p": f"Pin{n}" for n in range(1, 10)},
    **{f"{n}s": f"Sou{n}" for n in range(1, 10)},
    "1z": "Ton", "2z": "Nan", "3z": "Shaa", "4z": "Pei", "5z": "Haku", "6z": "Hatsu", "7z": "Chun",
    "0m": "Man5-Dora", "0p": "Pin5-Dora", "0s": "Sou5-Dora",
}
ALL_CODES = list(NAMES)


def tile_image(code: str, width: int) -> Image.Image:
    front = Image.open(TILE_DIR / "Front.png").convert("RGBA")
    face = Image.open(TILE_DIR / f"{NAMES[code]}.png").convert("RGBA")
    img = Image.alpha_composite(front, face)
    h = round(width * img.height / img.width)
    return img.resize((width, h), Image.LANCZOS)


def random_hand(rng: random.Random, n: int) -> list[str]:
    """4장 제한을 지키는 무작위 손패. 절반은 '그럴듯한' 손패(순자 위주)."""
    counts: dict[str, int] = {}
    hand: list[str] = []

    def add(code: str) -> bool:
        base = "5" + code[1] if code[0] == "0" else code
        if counts.get(base, 0) >= 4:
            return False
        if code[0] == "0" and any(c == code for c in hand):
            return False
        counts[base] = counts.get(base, 0) + 1
        hand.append(code)
        return True

    plausible = rng.random() < 0.5
    while len(hand) < n:
        if plausible and rng.random() < 0.6 and n - len(hand) >= 3:
            suit = rng.choice("mps")
            start = rng.randint(1, 7)
            seq = [f"{start + i}{suit}" for i in range(3)]
            if rng.random() < 0.25 and "5" + suit in seq:
                seq[seq.index("5" + suit)] = "0" + suit
            if all(counts.get("5" + c[1] if c[0] == "0" else c, 0) < 4 for c in seq):
                for c in seq:
                    add(c)
            continue
        add(rng.choice(ALL_CODES))
    return hand


def felt_background(w: int, h: int, rng: random.Random) -> Image.Image:
    g = rng.randint(90, 130)
    bg = Image.new("RGB", (w, h), (rng.randint(20, 50), g, rng.randint(40, 70)))
    draw = ImageDraw.Draw(bg)
    for _ in range(4000):  # 천 질감 비슷한 점 노이즈
        x, y = rng.randrange(w), rng.randrange(h)
        d = rng.randint(-12, 12)
        px = bg.getpixel((x, y))
        draw.point((x, y), tuple(max(0, min(255, c + d)) for c in px))
    return bg


def perspective(img: Image.Image, strength: float, rng: random.Random) -> Image.Image:
    """위쪽이 살짝 좁아 보이는 카메라 각도."""
    w, h = img.size
    dx = int(w * strength * rng.uniform(0.5, 1.0))
    dy = int(h * strength * rng.uniform(0.0, 0.5))
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    dst = [(dx, dy), (w - dx, dy), (w, h), (0, h)]
    coeffs = _find_coeffs(dst, src)
    fill = img.getpixel((5, h - 5))
    return img.transform((w, h), Image.PERSPECTIVE, coeffs, Image.BICUBIC, fillcolor=fill)


def _find_coeffs(pa, pb):
    import numpy as np
    matrix = []
    for p1, p2 in zip(pa, pb):
        matrix.append([p1[0], p1[1], 1, 0, 0, 0, -p2[0] * p1[0], -p2[0] * p1[1]])
        matrix.append([0, 0, 0, p1[0], p1[1], 1, -p2[1] * p1[0], -p2[1] * p1[1]])
    a = np.array(matrix, dtype=float)
    b = np.array(pb, dtype=float).reshape(8)
    return tuple(np.linalg.solve(a, b))


def render(hand: list[str], rng: random.Random, gap_after: int | None) -> Image.Image:
    tile_w = rng.randint(80, 120)
    tiles = [tile_image(c, tile_w) for c in hand]
    tile_h = tiles[0].height
    spacing = rng.randint(2, 8)
    gap = tile_w // 2 if gap_after else 0
    total_w = sum(t.width + spacing for t in tiles) + gap
    canvas_w = total_w + rng.randint(200, 400)
    canvas_h = tile_h + rng.randint(250, 450)
    bg = felt_background(canvas_w, canvas_h, rng)

    x = (canvas_w - total_w) // 2
    y = (canvas_h - tile_h) // 2
    for i, t in enumerate(tiles):
        angle = rng.uniform(-4, 4)
        rotated = t.rotate(angle, resample=Image.BICUBIC, expand=True)
        jitter_y = rng.randint(-4, 4)
        # 그림자
        shadow = Image.new("RGBA", rotated.size, (0, 0, 0, 0))
        alpha = rotated.split()[3]
        shadow.paste((0, 0, 0, 90), mask=alpha)
        bg.paste(shadow, (x + 6, y + jitter_y + 8), shadow)
        bg.paste(rotated, (x, y + jitter_y), rotated)
        x += t.width + spacing
        if gap_after is not None and i + 1 == gap_after:
            x += gap

    img = bg
    if rng.random() < 0.8:
        img = perspective(img, rng.uniform(0.03, 0.12), rng)
    img = ImageEnhance.Brightness(img).enhance(rng.uniform(0.75, 1.15))
    img = ImageEnhance.Contrast(img).enhance(rng.uniform(0.85, 1.1))
    if rng.random() < 0.5:
        img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 1.2)))
    # 색온도 살짝
    r, g, b = img.split()
    r = r.point(lambda v: min(255, int(v * rng.uniform(0.95, 1.1))))
    b = b.point(lambda v: min(255, int(v * rng.uniform(0.9, 1.05))))
    return Image.merge("RGB", (r, g, b))


def to_notation(hand: list[str]) -> str:
    return "".join(hand)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--count", type=int, default=12)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    labels: dict[str, str] = {}
    for i in range(1, args.count + 1):
        n = rng.choice([13, 14, 14, 14, 11, 8])
        hand = random_hand(rng, n)
        hand_sorted = rng.random() < 0.7
        if hand_sorted:
            hand.sort(key=lambda c: ("mpsz".index(c[1]), 5 if c[0] == "0" else int(c[0])))
        gap_after = rng.choice([None, None, n - 3, n - 1]) if n >= 8 else None
        img = render(hand, rng, gap_after)
        name = f"{i:02d}.jpg"
        img.save(args.out / name, quality=rng.randint(70, 92))
        labels[name] = " ".join(hand)
        print(name, n, "장", labels[name])
    (args.out / "labels.json").write_text(json.dumps(labels, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
