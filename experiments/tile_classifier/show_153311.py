"""153311 한 장면 그림(2026-11-10, 사용자 "153311 보여줘") — 원본·rc_gray 손패 쪽 확대 + 눕힌 4p 의 역할 확률(운영 v3r15d·v3r15dfix) + 회귀 판독.
  python -I -X utf8 experiments/tile_classifier/show_153311.py → data/role/v2/overlay/show_153311.jpg
"""
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
V2 = HERE / "data" / "role" / "v2"
M = HERE / "server_bench" / "models"
RES = HERE.parent / "speed" / "results"
N = "20261107_153311"
ROLES = ["hand", "meld", "river", "wall", "pair", "loose"]
KO = {"hand": "손패", "meld": "울기", "river": "강", "wall": "표시패", "pair": "짝", "loose": "떼어둔패"}
COL = {"hand": (40, 120, 255), "meld": (0, 200, 220), "wall": (255, 150, 0), "loose": (255, 210, 0)}
F = "C:/Windows/Fonts/malgunbd.ttf"

s = json.loads((V2 / "labels_v2.json").read_text(encoding="utf-8"))[N]
x = np.array(s["x"], np.float32)[None]
probs = {}
for tag, f in (("운영 v3r15d", "tile-roles-v3r15d.onnx"), ("고침 v3r15dfix", "tile-roles-v3r15dfix.onnx")):
    p = ort.InferenceSession(str(M / f), providers=["CPUExecutionProvider"]).run(None, {"x": x})[0][0]
    probs[tag] = p
reads = {}
for tag, f in (("운영 v3r15d", "robust_prod_v3r15dfix0_1110.json"), ("고침 v3r15dfix", "robust_prod_v3r15dfix1_1110.json")):
    d = json.loads((RES / f).read_text(encoding="utf-8"))
    reads[tag] = {v: d[v][N] for v in ("orig", "rc_gray")}

items = s["items"][: s["n_face"]]
win = [i for i, it in enumerate(items) if it.get("owner") == "winner"]
bx = [items[i]["box"] for i in win]
x0, y0 = min(b[0] for b in bx) - 120, min(b[1] for b in bx) - 200
x1, y1 = max(b[0] + b[2] for b in bx) + 120, max(b[1] + b[3] for b in bx) + 120


def crop(path, draw_roles):
    im = Image.open(path).convert("RGB")
    d = ImageDraw.Draw(im)
    if draw_roles:
        for i in win:
            bx_, by, bw, bh = items[i]["box"]
            r = items[i]["role"]
            d.rectangle([bx_, by, bx_ + bw, by + bh], outline=(255, 0, 0) if i == 6 else COL.get(r, (90, 90, 90)), width=12 if i == 6 else 6)
    c = im.crop((x0, y0, x1, y1))
    sc = 1600 / c.width
    return c.resize((1600, int(c.height * sc)))


fnt = ImageFont.truetype(F, 34)
fb = ImageFont.truetype(F, 40)
a = crop(s["image"], True)
g = crop(HERE.parent / "speed" / "robust" / "rc_gray" / f"{N}.jpg", False)
lines_a = ["원본 정답 — 파랑 손패·하늘 울기·주황 표시패", "빨간 틀 = 눕혀 둔 쯔모 화료패 4p(정답 떼어둔패), 이 상자의 역할 확률:"]
for tag, p in probs.items():
    top = sorted(range(6), key=lambda k: -p[6][k])[:3]
    lines_a.append(f"{tag}: " + " · ".join(f"{KO[ROLES[k]]} {p[6][k]:.2f}" for k in top))
lines_g = ["rc_gray(회색 재색칠) — 회귀 판독 손패", "정답 0s 5s 4p 4p 4s 4s 4s 4p (울기 東東東·西西西)"]
for tag, r in reads.items():
    for v in ("orig", "rc_gray"):
        lines_g.append(f"{tag} {v}: {'맞음' if r[v]['ok'] else '틀림'}  손패 {' '.join(r[v]['hand'])}")
H = lambda ls: 20 + 50 * len(ls)
sheet = Image.new("RGB", (1600, H(lines_a) + a.height + H(lines_g) + g.height + 20), "white")
d = ImageDraw.Draw(sheet)
y = 10
for k, t in enumerate(lines_a):
    d.text((10, y), t, fill="black", font=fb if k == 0 else fnt); y += 50
sheet.paste(a, (0, y)); y += a.height + 10
for k, t in enumerate(lines_g):
    d.text((10, y), t, fill=(200, 0, 0) if "틀림" in t else "black", font=fb if k == 0 else fnt); y += 50
sheet.paste(g, (0, y))
out = V2 / "overlay" / "show_153311.jpg"
sheet.save(out, quality=90)
print(out, sheet.size)
for tag, p in probs.items():
    print(tag, {ROLES[k]: round(float(p[6][k]), 3) for k in range(6)})
