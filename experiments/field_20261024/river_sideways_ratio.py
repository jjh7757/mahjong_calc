"""강 크롭마다 패 상자의 가로/세로 비율을 뽑아, 눕힌 패 기준값(app/river.py 1.15)을 눈으로 확인할 그림을 만든다. Gemini 호출 없음.

사용: python river_sideways_ratio.py <mahjong-recognizer 경로> <last3yolo_scenes 폴더> <그림 경로> [하한]
비율이 하한(기본 0.9) 넘는 상자를 모두 잘라 한 장에 붙인다. 정답은 이 그림을 보고 정한다.
"""
import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, sys.argv[1])
from app.river import RiverLocator  # noqa: E402

root, out = Path(sys.argv[2]), Path(sys.argv[3])
floor = float(sys.argv[4]) if len(sys.argv) > 4 else 0.9
loc = RiverLocator()
cells, ratios = [], []
for p in sorted(root.rglob("last_*.jpg")):
    if not p.parent.name.endswith("_1"):  # 같은 사진을 2회 잘라 둔 것이라 하나만 본다
        continue
    f, rgb = loc.locate(p.read_bytes())
    if f is None:
        print(p.relative_to(root), "틀 못 잡음")
        continue
    im = Image.open(io.BytesIO(p.read_bytes())).convert("RGB")
    for i, (x, y, w, h) in enumerate(b for r in f.rows for b in r):
        ratio = w / h
        ratios.append(ratio)
        if ratio >= floor:
            label = f"{p.parent.parent.name} {p.parent.name[:3]} {p.stem[5:]} #{i} {ratio:.2f}"
            print(label)
            c = im.crop((x, y, x + w, y + h)).resize((180, 180 * h // w))
            cell = Image.new("RGB", (240, 200), "white")
            cell.paste(c, (30, 30))
            ImageDraw.Draw(cell).text((4, 4), label, fill="black")
            cells.append(cell)

ratios.sort()
print("상자", len(ratios), "비율 구간 수:", {f"{a:.1f}~{a + 0.1:.1f}": sum(a <= r < a + 0.1 for r in ratios) for a in [i / 10 for i in range(5, 14)]})
cols = 5
sheet = Image.new("RGB", (cols * 240, (len(cells) + cols - 1) // cols * 200), "white")
for i, c in enumerate(cells):
    sheet.paste(c, (i % cols * 240, i // cols * 200))
sheet.save(out, quality=92)
