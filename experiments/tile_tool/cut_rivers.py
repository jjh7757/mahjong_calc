"""강 끝 크롭(그 자리 방향으로 세운 것)에서 바로 선 버림패를 잘라 모델이 붙인 이름과 함께 판으로 만든다.
이름은 사람이 판을 보고 확인해 맞는 것만 river_ok.txt 에 남긴다(부족한 종류 채우기용)."""
import io, json, os
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
load_dotenv("C:/Users/jjh7757/Downloads/부트캠프/.env")
from google import genai
from google.genai import types
ROOT = Path(__file__).parent
G = ROOT.parent / "field_20261024" / "grid5_scenes"
OUT = ROOT / "river_raw"; OUT.mkdir(exist_ok=True)
CODES = [f"{n}{s}" for s in "mps" for n in range(1, 10)] + [f"{n}z" for n in range(1, 8)] + ["0m", "0p", "0s"]
SCHEMA = {"type": "object", "properties": {"tiles": {"type": "array", "items": {"type": "object", "properties": {
    "box": {"type": "array", "items": {"type": "integer"}}, "code": {"type": "string", "enum": CODES}},
    "required": ["box", "code"]}}}, "required": ["tiles"]}
PROMPT = """사진 아래쪽 플레이어의 버림패(글자가 바로 서 보이는 패)를 하나하나 찾아 상자 [ymin,xmin,ymax,xmax](0~1000)와
패 이름을 적어 주세요. 옆으로 돌아간 패, 거꾸로 된 패, 반 이상 잘린 패는 빼세요.
표기: 만 1m~9m, 통 1p~9p, 삭 1s~9s, 동남서북 1z~4z, 백 5z, 발 6z, 중 7z, 붉은 5 는 0m/0p/0s."""
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
cells = []
for scene, photos in {"B": ["k25_1"], "C": ["k15_1"], "D": ["k16_1"], "E": ["k00_1"], "A": ["k20_1"]}.items():
    for photo in photos:
        for f in sorted((G / scene / photo).glob("last_*.jpg")):
            im = Image.open(f).convert("RGB")
            buf = io.BytesIO(); im.save(buf, "JPEG", quality=92)
            part = types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")
            part.media_resolution = types.PartMediaResolution(level="MEDIA_RESOLUTION_ULTRA_HIGH")
            r = client.models.generate_content(model="gemini-3.8-flash", contents=[part, PROMPT],
                config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=SCHEMA))
            W, H = im.size
            for i, t in enumerate(json.loads(r.text)["tiles"]):
                y0, x0, y1, x1 = t["box"]
                if x1 <= x0 or y1 <= y0:
                    continue
                c = im.crop((x0 * W / 1000, y0 * H / 1000, x1 * W / 1000, y1 * H / 1000))
                name = f"{scene}_{photo}_{f.stem}_{i:02d}_{t['code']}.png"
                c.save(OUT / name); cells.append((name, c, t["code"]))
            print(scene, photo, f.stem, flush=True)
F = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 13)
cw, ch, cols = 90, 130, 14
rows = (len(cells) + cols - 1) // cols
sheet = Image.new("RGB", (cw * cols, ch * rows), "white"); d = ImageDraw.Draw(sheet)
for i, (name, c, code) in enumerate(cells):
    c = c.copy(); c.thumbnail((cw - 6, ch - 30)); x, y = (i % cols) * cw, (i // cols) * ch
    sheet.paste(c, (x + 3, y + 3)); d.text((x + 3, y + ch - 26), f"{i} {code}", font=F, fill="red")
sheet.save(ROOT / "river_sheet.png")
json.dump([n for n, _, _ in cells], open(ROOT / "river_index.json", "w"))
print("tiles", len(cells))
