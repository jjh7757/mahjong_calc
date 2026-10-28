"""out/ 의 미리보기를 한 장으로 모은다(눈 확인용). python -I sheet.py 이름접두… → out/sheet.jpg"""
import sys
from pathlib import Path

from PIL import Image

OUT = Path(__file__).parent / "out"
names = sys.argv[1:]
tiles = [Image.open(OUT / n).convert("RGB") for n in names]
W = 420
tiles = [t.resize((W, int(t.height * W / t.width))) for t in tiles]
cols = 4
rows = (len(tiles) + cols - 1) // cols
H = max(t.height for t in tiles)
sheet = Image.new("RGB", (W * cols, H * rows), (40, 40, 40))
for i, t in enumerate(tiles):
    sheet.paste(t, ((i % cols) * W, (i // cols) * H))
sheet.save(OUT / "sheet.jpg", quality=85)
print(OUT / "sheet.jpg")
