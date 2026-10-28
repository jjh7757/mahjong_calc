"""10/24 카메라 헤드 촬영 기록(다른 장면)의 손패·강·왕패·울기 크롭에서 바로 선 앞면 패를 잘라, 부족한 종류 후보를 모은다.
이름은 모델이 붙이고, 사람이 more_sheet.png 를 보고 맞는 것만 more_ok.txt 에 남긴다. 파일 이름은 Q_ 로 시작(시험 장면 A~E 와 겹치지 않음)."""
import io, json, os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
load_dotenv("C:/Users/jjh7757/Downloads/부트캠프/.env")
from google import genai
from google.genai import types
ROOT = Path(__file__).parent
CAP = ROOT.parent / "field_20261024" / "captures"
OUT = ROOT / "more_raw"; OUT.mkdir(exist_ok=True)
SHOTS = ["20261024_115559", "20261024_120037", "20261024_122922", "20261024_124007",
         "20261024_130533", "20261024_135912", "20261024_142236", "20261024_143443"]
TARGET = {f"{n}p" for n in (2, 3, 4, 5, 6, 7, 9)} | {f"{n}s" for n in range(1, 10)} | {"0p", "0s", "0m"}
PER_CODE = 8
CODES = [f"{n}{s}" for s in "mps" for n in range(1, 10)] + [f"{n}z" for n in range(1, 8)] + ["0m", "0p", "0s"]
SCHEMA = {"type": "object", "properties": {"tiles": {"type": "array", "items": {"type": "object", "properties": {
    "box": {"type": "array", "items": {"type": "integer"}}, "code": {"type": "string", "enum": CODES}},
    "required": ["box", "code"]}}}, "required": ["tiles"]}
PROMPT = """글자·무늬가 바로 서 보이는(위아래가 맞는) 앞면 마작패를 하나하나 찾아 상자 [ymin,xmin,ymax,xmax](0~1000)와 이름을 적어 주세요.
옆으로 돌아간 패, 거꾸로 된 패, 뒷면 패, 반 이상 잘린 패는 빼세요.
표기: 만 1m~9m, 통 1p~9p, 삭 1s~9s, 동남서북 1z~4z, 백 5z, 발 6z, 중 7z, 붉은 5 는 0m/0p/0s."""
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
files = [f for s in SHOTS for f in sorted((CAP / s).glob("*.jpg"))
         if f.name.startswith(("hand_", "river_", "wall", "meld_"))]

def cut(f):
    im = Image.open(f).convert("RGB")
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=92)
    part = types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")
    part.media_resolution = types.PartMediaResolution(level="MEDIA_RESOLUTION_ULTRA_HIGH")
    try:
        r = client.models.generate_content(model="gemini-3.8-flash", contents=[part, PROMPT],
            config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=SCHEMA,
                                               thinking_config=types.ThinkingConfig(thinking_level="low")))
        tiles = json.loads(r.text)["tiles"]
    except Exception as e:  # noqa: BLE001
        print("fail", f, e); return []
    W, H = im.size; out = []
    for i, t in enumerate(tiles):
        y0, x0, y1, x1 = t["box"]
        if t["code"] not in TARGET or x1 <= x0 or y1 <= y0:
            continue
        c = im.crop((x0 * W / 1000, y0 * H / 1000, x1 * W / 1000, y1 * H / 1000))
        if min(c.size) < 40:
            continue
        name = f"Q_{f.parent.name[9:]}_{f.stem}_{i:02d}_{t['code']}.png"
        c.save(OUT / name); out.append((name, t["code"]))
    return out

with ThreadPoolExecutor(8) as ex:
    found = [x for xs in ex.map(cut, files) for x in xs]
# 종류마다 촬영이 고르게 섞이도록 최대 PER_CODE 장
by = defaultdict(list)
for n, c in found:
    by[c].append(n)
pick = []
for c in sorted(by):
    shots = defaultdict(list)
    for n in by[c]:
        shots[n.split("_")[1]].append(n)
    order = [n for group in zip(*[iter(v) for v in shots.values()]) for n in group] if False else []
    rr = []
    while len(rr) < PER_CODE and any(shots.values()):
        for k in list(shots):
            if shots[k] and len(rr) < PER_CODE:
                rr.append(shots[k].pop(0))
    pick += [(n, c) for n in rr]
F = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 13)
cw, ch, cols = 100, 140, 12
rows = (len(pick) + cols - 1) // cols
sheet = Image.new("RGB", (cw * cols, ch * rows), "white"); d = ImageDraw.Draw(sheet)
for i, (n, c) in enumerate(pick):
    im = Image.open(OUT / n); im.thumbnail((cw - 6, ch - 30)); x, y = (i % cols) * cw, (i // cols) * ch
    sheet.paste(im, (x + 3, y + 3)); d.text((x + 3, y + ch - 26), f"{i} {c}", font=F, fill="red")
sheet.save(ROOT / "more_sheet.png")
json.dump(pick, open(ROOT / "more_index.json", "w"))
print("files", len(files), "found", len(found), "picked", len(pick), {c: len(v) for c, v in sorted(by.items())})
