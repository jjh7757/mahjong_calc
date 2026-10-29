"""판 시작 장면 흉내: B·C·D 사진의 왕패(연보라 L자 패산) 한 줄 윗면에 앞면 패(七萬) 한 장을 붙여 "도라를 뒤집은 왕패" 를 만든다.

  python -I -X utf8 experiments/speed/make_dora_wall.py      → kakao_photos/synth_wall/<사진>.jpg, 붙인 곳 확인용 synth_wall_check.jpg

붙이는 패: k15 의 도라 표시패 七萬(원본 픽셀 상자). 붙이는 곳: 왕패 정답 상자(dora_locate.TRUTH)를 폭 400 으로 줄인 크롭에서
손으로 고른 세로줄 2·3번째 줄 윗면(사용자 요청 2026-10-29 "도라 산에 도라 한 장 까져 있는 합성 사진").
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
from dora_locate import TRUTH  # noqa: E402

PHOTOS = Path(__file__).parent.parent / "field_20261024" / "kakao_photos"
OUT = PHOTOS / "synth_wall"

SOURCE = ("k15", (892, 1857, 1026, 1963))  # 七萬, 원본 픽셀 (x0, y0, x1, y1)
# 정답 상자를 폭 400 으로 줄인 크롭 좌표의 패산 윗면 (x0, y0, x1, y1)
FACE = {
    "k25": (12, 192, 103, 262),
    "k28": (15, 197, 105, 268),
    "k15": (93, 148, 165, 195),
    "k26": (95, 150, 165, 195),
    "k12": (20, 127, 130, 207),
    "k16": (35, 122, 145, 202),
}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    src_name, src_box = SOURCE
    tile = Image.open(PHOTOS / f"{src_name}.jpg").convert("RGB").crop(src_box)
    checks = []
    for name, face in FACE.items():
        im = Image.open(PHOTOS / f"{name}.jpg").convert("RGB")
        w, h = im.size
        y0, x0, y1, x1 = TRUTH[name]
        bx, by = x0 * w / 1000, y0 * h / 1000
        scale = 400 / ((x1 - x0) * w / 1000)
        fx0, fy0, fx1, fy1 = (bx + face[0] / scale, by + face[1] / scale, bx + face[2] / scale, by + face[3] / scale)
        t = tile.resize((int(fx1 - fx0), int(fy1 - fy0)))
        im.paste(t, (int(fx0), int(fy0)))
        im.save(OUT / f"{name}.jpg", quality=95)
        c = im.crop((int(bx), int(by), int(x1 * w / 1000), int(y1 * h / 1000)))
        c.thumbnail((400, 400))
        ImageDraw.Draw(c).text((8, 8), name, fill=(255, 255, 0))
        checks.append(c)
    sheet = Image.new("RGB", (400 * 3, 470 * 2), "white")
    for i, c in enumerate(checks):
        sheet.paste(c, ((i % 3) * 400, (i // 3) * 470))
    sheet.save(OUT / "synth_wall_check.jpg", quality=88)
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
