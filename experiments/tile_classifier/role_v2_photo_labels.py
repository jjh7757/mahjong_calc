"""labels_v2 를 사진 위에 그린다(역할별 색 상자, 뒷면 회색, 깡 묶음 굵은 흰 테두리). 화료자가 아래로 오게 돌림.
  python -X utf8 experiments/tile_classifier/role_v2_photo_labels.py [이름...] → data/role/base_review/photo_labels_XX.jpg"""
import json, sys
from pathlib import Path
import cv2
from PIL import Image, ImageDraw, ImageFont
HERE = Path(__file__).resolve().parent
L = json.loads((HERE / "data/role/v2/labels_v2.json").read_text(encoding="utf-8"))
OUT = HERE / "data/role/base_review"
COL = {"hand": (0, 70, 255), "meld": (0, 230, 255), "river": (255, 150, 0), "wall": (255, 0, 0), "pair": (255, 0, 255), "loose": (255, 255, 0), "other": (255, 255, 255)}
ROT = {"bottom": None, "right": Image.Transpose.ROTATE_270, "top": Image.Transpose.ROTATE_180, "left": Image.Transpose.ROTATE_90}  # PIL ROTATE_270 = 시계 방향
f = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 26)
names = sys.argv[1:] or list(L)
cells = []
for n in names:
    s = L[n]
    im = Image.open(s["image"]).convert("RGB"); d = ImageDraw.Draw(im)
    for b in s["backs"]:
        d.rectangle([b[0], b[1], b[0] + b[2], b[1] + b[3]], outline=(150, 150, 150), width=5)
    for it in s["items"]:
        x, y, w, h = it["box"]
        d.rectangle([x, y, x + w, y + h], outline=COL[it["role"]], width=6 if it["role"] == "river" else 11)
        if it.get("owner") == "other" and it["role"] == "meld":
            d.line([x, y, x + w, y + h], fill=COL["meld"], width=5)  # 다른 사람 울기 = 대각선
    for g in s.get("kan_groups", []):
        bx = [s["items"][i]["box"] for i in g["face_index"]] + [s["backs"][j] for j in g["back_index"]]
        x0 = min(b[0] for b in bx); y0 = min(b[1] for b in bx); x1 = max(b[0] + b[2] for b in bx); y1 = max(b[1] + b[3] for b in bx)
        d.rectangle([x0 - 14, y0 - 14, x1 + 14, y1 + 14], outline=(255, 60, 200), width=10)
    if ROT[s["side"]] is not None:
        im = im.transpose(ROT[s["side"]])
    im = im.resize((int(im.width * 700 / im.height), 700))
    c = Image.new("RGB", (im.width, 740), "white"); dd = ImageDraw.Draw(c); dd.text((4, 4), n + (" · " + s["flags"] if s.get("flags") else ""), font=f, fill=(0, 0, 0))
    c.paste(im, (0, 40)); cells.append(c)
per = 4
for k in range(0, len(cells), per):
    g = cells[k:k + per]; W = max(c.width for c in g)
    S = Image.new("RGB", (2 * W + 16, 60 + ((len(g) + 1) // 2) * 756), "white"); dd = ImageDraw.Draw(S)
    dd.text((6, 10), "파랑 손패 · 하늘 울기(대각선 = 다른 사람) · 주황 강 · 빨강 패산 위 표시패 · 자홍 짝 · 노랑 떼어 둔 화료패 · 흰 역할 없음 · 회색 뒷면 · 굵은 분홍 테 = 깡 묶음 (화료자가 아래)", font=f, fill=(0, 0, 0))
    for i, c in enumerate(g):
        S.paste(c, ((i % 2) * (W + 16), 60 + (i // 2) * 756))
    S.save(OUT / f"photo_labels_{k // per + 1:02d}.jpg", quality=85)
print(len(cells))
