"""한 프레임에서 검출기 원본 상자 수·흰 면 거르기 뒤 수를 크롭 배율별로 비교(paifu_frames 검출 놓침 진단)."""
import io, sys, zipfile, json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, r"C:\Users\jjh7757\dev\mahjong-recognizer")
from app import river as rv
from app.local_read import LocalReader
import app.local_read as lr

zpath, name, cx, cy, hd = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
rgb = np.asarray(Image.open(io.BytesIO(zipfile.ZipFile(zpath).read(name))).convert("RGB"))
r = LocalReader(threads=4)
for k in (2.4, 3.2):
    R = int(hd * k)
    x0, y0 = int(cx - R), int(cy - R)
    crop = rgb[y0:int(cy + R), x0:int(cx + R)]
    for conf in (0.25, 0.1):
        lr.CONF = conf
        raw = r.detect(crop, low=False)
        w = rv.white_mask(crop)
        kept = rv.keep_faces(raw, w, 0.45)
        print(f"R={k} conf={conf} raw={len(raw)} kept={len(kept)} dedupe={len(rv.dedupe(kept))}")
        if k == 2.4 and conf == 0.1:
            im = Image.fromarray(crop).resize((crop.shape[1] * 3, crop.shape[0] * 3))
            d = ImageDraw.Draw(im)
            for b in raw:
                d.rectangle([v * 3 for v in (b[0], b[1], b[0] + b[2], b[1] + b[3])], outline="red" if b in kept else "blue", width=2)
            im.save(Path(sys.argv[6]))
lr.CONF = 0.25
