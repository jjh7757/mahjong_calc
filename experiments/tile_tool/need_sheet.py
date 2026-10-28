import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
ROOT = Path(__file__).parent
NEED = {"1p", "2p", "6p", "7p", "8p", "0p", "4s", "5s", "0s", "3z", "4z", "5z"}
names = [n for n in json.load(open(ROOT / "river_index.json")) if n.rsplit("_", 1)[1][:-4] in NEED]
names.sort(key=lambda n: n.rsplit("_", 1)[1])
F = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 13)
cw, ch, cols = 100, 140, 12
rows = (len(names) + cols - 1) // cols
sheet = Image.new("RGB", (cw * cols, ch * rows), "white"); d = ImageDraw.Draw(sheet)
for i, n in enumerate(names):
    c = Image.open(ROOT / "river_raw" / n); c.thumbnail((cw - 6, ch - 30)); x, y = (i % cols) * cw, (i // cols) * ch
    sheet.paste(c, (x + 3, y + 3)); d.text((x + 3, y + ch - 26), f"{i} {n.rsplit('_', 1)[1][:-4]} {n[0]}", font=F, fill="red")
sheet.save(ROOT / "need_sheet.png")
json.dump(names, open(ROOT / "need_index.json", "w"))
print(len(names))
