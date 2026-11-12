"""테스트 세트 40장(seat_grow.eval_scenes)을 헤드 방식 해상도 둘로: 1020 = 긴 변 1020 이 되게 건너뛰기(헤드 /preview),
2040 = 면적 평균으로 긴 변 2040(헤드 녹화). 펠트 감시를 1020 대신 녹화 2040 으로 해도 되는지(2026-11-12).

  python -I experiments/speed/mk_res_eval40.py <출력 폴더>
"""
import json, os, sys
from pathlib import Path
from PIL import Image, ImageOps
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import seat_grow as sg

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
names = []
for s in sg.eval_scenes():
    im = ImageOps.exif_transpose(Image.open(s["path"])).convert("RGB")
    a = np.asarray(im)
    long = max(im.size)
    step = max(1, long // 1020)
    Image.fromarray(a[::step, ::step]).save(f"{out}/{s['name']}_1020.jpg", quality=75)
    k = long / 2040
    im2 = im.reduce(round(k)) if k > 1 and abs(k - round(k)) < 0.05 else (im.resize((round(im.width / k), round(im.height / k)), Image.BOX) if k > 1 else im)
    im2.save(f"{out}/{s['name']}_2040.jpg", quality=85)
    names.append(s["name"])
json.dump(names, open(f"{out}/names.json", "w"))
print(len(names))
