"""role_eval.py 결과에서 틀린 장면을 그림으로(2026-11-10, 사용자 "틀린 장면 그림으로 보여줘").
장면마다 왼쪽 = 사진 전체(화료자 쪽 상자 영역 노란 틀), 오른쪽 = 화료자 쪽 확대. 상자 색 = 정답 역할, 굵은 빨간 틀 + 글자 = 틀린 상자(정답→예측).

  python -I -X utf8 experiments/tile_classifier/role_eval_sheet.py [tag=v3r15d] [key=holdout/orig]
결과 data/role/v2/overlay/role_eval_<tag>_wrong.jpg
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
V2 = HERE / "data" / "role" / "v2"
COL = {"hand": (40, 120, 255), "meld": (0, 200, 220), "river": (150, 150, 150), "wall": (255, 150, 0), "pair": (230, 0, 230), "loose": (255, 230, 0), "other": (90, 90, 90)}
KO = {"hand": "손패", "meld": "울기", "river": "강", "wall": "표시패", "pair": "짝", "loose": "떼어둔패", "other": "기타"}
FONT = "C:/Windows/Fonts/malgunbd.ttf"


def panel(name: str, s: dict, per: dict, H: int = 900) -> Image.Image:
    im = Image.open(s["image"]).convert("RGB")
    items = s["items"][: s["n_face"]]
    wrong = {i: (r, p) for i, r, p in per["wrong"]}
    focus = [it["box"] for i, it in enumerate(items) if it.get("owner") == "winner" or i in wrong]
    x0 = min(b[0] for b in focus); y0 = min(b[1] for b in focus)
    x1 = max(b[0] + b[2] for b in focus); y1 = max(b[1] + b[3] for b in focus)
    pad = 160
    x0, y0, x1, y1 = max(0, x0 - pad), max(0, y0 - pad), min(im.width, x1 + pad + 300), min(im.height, y1 + pad)  # 오른쪽은 글자 몫
    d = ImageDraw.Draw(im)
    for i, it in enumerate(items):
        x, y, w, h = it["box"]
        if i in wrong:
            continue
        d.rectangle([x, y, x + w, y + h], outline=COL.get(it["role"], (90, 90, 90)), width=6)
    f = ImageFont.truetype(FONT, 46)
    for k, (i, (r, p)) in enumerate(wrong.items()):
        x, y, w, h = items[i]["box"]
        d.rectangle([x - 6, y - 6, x + w + 6, y + h + 6], outline=(255, 0, 0), width=14)
        txt = f"{KO.get(r, r)}→{KO.get(p, p)}"
        tw = d.textlength(txt, font=f)
        above = (k % 2 == 0) and y - 62 > y0  # 이웃한 틀린 상자는 위·아래 번갈아
        ty = y - 62 if above else y + h + 10
        d.rectangle([x, ty, x + tw + 12, ty + 56], fill=(255, 0, 0))
        d.text((x + 6, ty), txt, fill="white", font=f)
    full = im.copy()
    ImageDraw.Draw(full).rectangle([x0, y0, x1, y1], outline=(255, 255, 0), width=18)
    full = full.resize((int(full.width * H / full.height), H))
    crop = im.crop((x0, y0, x1, y1))
    sc = min(H / crop.height, 1500 / crop.width)
    crop = crop.resize((int(crop.width * sc), int(crop.height * sc)))
    out = Image.new("RGB", (full.width + crop.width + 20, H + 90), "white")
    out.paste(full, (0, 90))
    out.paste(crop, (full.width + 20, 90))
    hd = ImageDraw.Draw(out)
    fh = ImageFont.truetype(FONT, 40)
    msg = f"{name}  화료자 쪽 손패 정답 {per['hand'][0]} · 예측 {per['hand'][1]}   울기 정답 {per['meld'][0]} · 예측 {per['meld'][1]}"
    hd.text((10, 20), msg, fill="black", font=fh)
    return out


def main(tag: str = "v3r15d", key: str = "holdout/orig") -> Path:
    labels = json.loads((V2 / "labels_v2.json").read_text(encoding="utf-8"))
    res = json.loads((V2 / f"role_eval_{tag}.json").read_text(encoding="utf-8"))[key]
    names = [n for n, v in res["per"].items() if not v["seat_ok"]]
    panels = [panel(n, labels[n], res["per"][n]) for n in names]
    W = max(p.width for p in panels)
    leg_h = 80
    sheet = Image.new("RGB", (W, sum(p.height for p in panels) + leg_h + 20 * len(panels)), "white")
    d = ImageDraw.Draw(sheet)
    f = ImageFont.truetype(FONT, 38)
    x = 10
    for r in ("hand", "meld", "river", "wall", "pair", "loose"):
        d.rectangle([x, 20, x + 50, 60], outline=COL[r], width=8)
        d.text((x + 60, 15), KO[r], fill="black", font=f)
        x += 80 + int(d.textlength(KO[r], font=f)) + 30
    d.rectangle([x, 20, x + 50, 60], outline=(255, 0, 0), width=12)
    d.text((x + 60, 15), f"틀림(정답→예측)   {tag} {key}", fill="black", font=f)
    y = leg_h
    for p in panels:
        sheet.paste(p, (0, y))
        y += p.height + 20
    out = V2 / "overlay" / f"role_eval_{tag}_wrong.jpg"
    sheet.save(out, quality=88)
    print(out, sheet.size)
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(*sys.argv[1:])
