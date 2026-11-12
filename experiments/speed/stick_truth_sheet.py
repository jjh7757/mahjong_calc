# 리치봉 홈 정답 달기용: 11-07 화료 원본에서 격자 리치봉 상자(sticks, 0~1000 [ymin,xmin,ymax,xmax])를 여유 있게 잘라 한 장에 모은다.
# 예측값은 넣지 않는다(정답을 먼저 달기 위해).
import json, sys, os
from PIL import Image, ImageDraw
root, out = sys.argv[1], sys.argv[2]
g = json.load(open(os.path.join(root, 'grids.json')))
tiles = []
for k, v in g.items():
    s = v['grid'].get('sticks')
    im = Image.open(os.path.join(root, 'captures', k, 'original.jpg')).convert('RGB')
    W, H = im.size
    y0, x0, y1, x1 = s
    py, px = (y1 - y0) * 0.15, (x1 - x0) * 0.15
    box = (int((x0 - px) / 1000 * W), int((y0 - py) / 1000 * H), int((x1 + px) / 1000 * W), int((y1 + py) / 1000 * H))
    c = im.crop(box)
    c.thumbnail((560, 560))
    d = ImageDraw.Draw(c); d.rectangle((0, 0, 200, 22), fill='black'); d.text((4, 4), k, fill='yellow')
    tiles.append(c)
cols = 4
w = max(t.size[0] for t in tiles); h = max(t.size[1] for t in tiles)
for part in range(0, len(tiles), 8):
    chunk = tiles[part:part + 8]
    rows = (len(chunk) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * w, rows * h), 'white')
    for i, t in enumerate(chunk):
        sheet.paste(t, ((i % cols) * w, (i // cols) * h))
    sheet.save(f"{out}_{part // 8 + 1}.jpg", quality=90)
