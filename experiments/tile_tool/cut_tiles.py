"""매장 사진의 자리 크롭(그 자리 방향으로 세운 것)에서 앞면 패를 한 장씩 잘라 참고 그림 후보를 만든다.

Gemini 에게 패 상자만 받고, 이름은 장면 정답(손패 순서)으로 붙인다. 장수가 안 맞으면 그 줄은 버린다.
결과: tiles_raw/<장면>_<사진>_<순번>_<패>.png 와 확인용 sheet.png. 사람이 sheet 를 보고 틀린 것을 지운다.

python experiments/tile_tool/cut_tiles.py   (Gemini 키는 부트캠프 .env)
"""
import io, json, os, sys
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

load_dotenv("C:/Users/jjh7757/Downloads/부트캠프/.env")
from google import genai
from google.genai import types

ROOT = Path(__file__).parent
G = ROOT.parent / "field_20261024" / "grid5_scenes"
OUT = ROOT / "tiles_raw"
OUT.mkdir(exist_ok=True)

# 장면별 정답: (크롭, 손패 줄 왼쪽부터, 울기 묶음들, 따로 놓인 패)
SCENES = {
    "A": ("hand_top.jpg", "3p 3p 5p 5p 4m 5m 6m 6s 7s 8s", [], []),
    "B": ("hand_right.jpg", "7z 1m 1m 1m 9s 9s 9s 9p 9p 9p", ["6z 6z 6z"], []),
    "C": ("hand_left.jpg", "1z 1z 1z 1m 2m 3m 4m 5m 6m 7m 8m 9m 2z", [], ["7m 6s"]),
    "D": ("hand_bottom.jpg", "1m 2m 3m 4m 0m 6m 7m 8m 9m 2z", ["6m 7m 8m"], []),
    "E": ("hand_left.jpg", "1z 1z 1z 7m 8m 9m 1s 2s 3s 7s 8s 7z 7z", [], ["4p 4p 7m"]),
}
PHOTOS = {"A": ["k20_1", "k24_1"], "B": ["k25_1", "k28_1"], "C": ["k15_1", "k26_1"], "D": ["k12_1", "k16_1"], "E": ["k00_1", "k04_1"]}

SCHEMA = {
    "type": "object",
    "properties": {
        "groups": {
            "type": "array",
            "description": "앞면 패 묶음. 첫째는 손패 줄, 그다음은 다른 묶음(울기·따로 놓인 패) 왼쪽부터",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["hand", "meld", "loose"]},
                    "boxes": {"type": "array", "description": "묶음 안의 앞면 패 상자를 왼쪽부터. [ymin,xmin,ymax,xmax] 0~1000",
                              "items": {"type": "array", "items": {"type": "integer"}}},
                },
                "required": ["kind", "boxes"],
            },
        }
    },
    "required": ["groups"],
}
PROMPT = """이 사진은 마작 테이블의 한 자리를 그 사람 쪽에서 본 방향으로 세운 것입니다.
앞면(그림이 보이는) 패 하나하나의 상자를 찾아 주세요. 손패 줄은 kind=hand, 3~4장 울기 묶음은 kind=meld,
1~3장 따로 놓인 패는 kind=loose. 각 묶음 안에서 왼쪽부터. 뒷면(연보라) 패와 테이블 가운데 버림패는 빼세요.
상자는 패 한 장을 꼭 맞게 감싸는 [ymin,xmin,ymax,xmax] (0~1000)."""

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
cells = []
for scene, (crop, hand, melds, loose) in SCENES.items():
    for photo in PHOTOS[scene]:
        im = Image.open(G / scene / photo / crop).convert("RGB")
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=92)
        part = types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")
        part.media_resolution = types.PartMediaResolution(level="MEDIA_RESOLUTION_ULTRA_HIGH")
        r = client.models.generate_content(
            model="gemini-3.8-flash", contents=[part, PROMPT],
            config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=SCHEMA))
        groups = json.loads(r.text)["groups"]
        want = {"hand": [hand.split()], "meld": [m.split() for m in melds], "loose": [l.split() for l in loose]}
        used = {k: 0 for k in want}
        for g in groups:
            k = g["kind"]
            if used[k] >= len(want[k]):
                continue
            codes = want[k][used[k]]
            if len(g["boxes"]) != len(codes):
                print(f"{scene} {photo} {k}: 상자 {len(g['boxes'])} != 정답 {len(codes)} → 버림", file=sys.stderr)
                continue
            used[k] += 1
            for i, (b, code) in enumerate(zip(g["boxes"], codes)):
                y0, x0, y1, x1 = b
                W, H = im.size
                pad = 0.04
                bw, bh = (x1 - x0) * pad, (y1 - y0) * pad
                box = (max(0, (x0 - bw) * W / 1000), max(0, (y0 - bh) * H / 1000), min(W, (x1 + bw) * W / 1000), min(H, (y1 + bh) * H / 1000))
                t = im.crop(box)
                name = f"{scene}_{photo}_{k}{i:02d}_{code}.png"
                t.save(OUT / name)
                cells.append((name, t, code))
        print(scene, photo, {k: v for k, v in used.items()}, flush=True)

# 확인용 판: 패마다 이름표
F = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 14)
cw, ch, cols = 110, 150, 12
rows = (len(cells) + cols - 1) // cols
sheet = Image.new("RGB", (cw * cols, ch * rows), "white")
d = ImageDraw.Draw(sheet)
for i, (name, t, code) in enumerate(cells):
    t = t.copy(); t.thumbnail((cw - 6, ch - 34))
    x, y = (i % cols) * cw, (i // cols) * ch
    sheet.paste(t, (x + 3, y + 3))
    d.text((x + 3, y + ch - 30), code, font=F, fill="red")
    d.text((x + 30, y + ch - 30), name.split("_")[0] + name.split("_")[1][1:3], font=F, fill="gray")
sheet.save(ROOT / "sheet.png")
print("tiles", len(cells))
