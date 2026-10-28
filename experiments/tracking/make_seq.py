"""장면 D(k16, 격자 initial, 아래 자리 치 [6m 7m 8m])로 추적 시퀀스 프레임을 합성한다.
f0 울기 전(모서리를 펠트색으로 덮음) → f1 손(소매 덩어리) → f2 울기 후(원본) → f3 화료(원본).
"""
import os, sys
from PIL import Image, ImageDraw

src, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
im = Image.open(src).convert("RGB")
W, H = im.size
# 치가 놓인 곳(썸네일 1200px 기준 x 1020~1160, y 770~830 → 원본 ×3.333). 조금 넉넉히.
box = (3330, 2500, 3960, 2830)
felt = im.getpixel((3200, 2450))
print("felt", felt)

f0 = im.copy()
d = ImageDraw.Draw(f0)
d.rectangle(box, fill=felt)
f0.save(f"{out}/f0.jpg", quality=92)

f1 = f0.copy()
d = ImageDraw.Draw(f1)
d.ellipse((3380, 2420, 3950, 2900), fill=(214, 176, 146))  # 손·소매
f1.save(f"{out}/f1.jpg", quality=92)

im.save(f"{out}/f2.jpg", quality=92)
im.save(f"{out}/f3.jpg", quality=92)
for n in ("f0", "f1", "f2"):
    Image.open(f"{out}/{n}.jpg").crop(box).resize((420, 220)).save(f"{out}/{n}_corner_thumb.jpg", quality=85)
print("ok", W, H)
