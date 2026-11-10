"""회귀 변형 한 장을 서버 read_roles 로 다시 돌려 역할 모델 전·후의 상자별 역할을 비교(2026-11-09, metrics 표 1-133 원인 보기).
  python -I -X utf8 experiments/tile_classifier/role_rot_debug.py rot_m10 k25 [prod|fold] tile-roles-rot tile-roles-v3r15
그림 data/role/v2/debug_rot/<변형>_<이름>_<모델>.jpg(색 = 역할, 굵은 테 = 자리 크롭 안), 콘솔에 두 모델이 다르게 본 상자.
"""
import io, json, os, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "speed"))
os.environ.setdefault("RECOGNIZER_REPO", "C:/Users/jjh7757/dev/mahjong-recognizer")
import robust_suite as rsu  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

v, name, mode = sys.argv[1], sys.argv[2], sys.argv[3]
models = sys.argv[4:]
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(rsu.REPO))
from app.recognizer import prepare_image  # noqa: E402
from app import roles, local_read as lr  # noqa: E402

meta = json.loads((rsu.RB / "meta.json").read_text(encoding="utf-8"))
felt = rsu.felt_grids(rsu.RB)
s = next(x for x in rsu.scenes("dev") if x["name"] == name)
info = meta[v][name]
grid = s["grid"]
if v in rsu.FELT_GRID:
    fg = felt.get(f"{v}/{name}")
    if fg and fg.get("grid"):
        g = fg["grid"]
        grid = {"x1": g["x1"], "x2": g["x2"], "y1": g["y1"], "y2": g["y2"]}
        if g.get("sticks"):
            sk = g["sticks"]
            grid["sticks"] = [sk["ymin"], sk["xmin"], sk["ymax"], sk["xmax"]] if isinstance(sk, dict) else list(sk)
    elif "grid_a" in info:
        grid = info["grid_a"]
jpeg = prepare_image(Path(info["src"]).read_bytes(), 4080)
print("정답 손패", s["hand"], "울기", s["melds"], "자리", s["side"], "격자", grid)
COL = {"hand": "blue", "meld": "cyan", "river": "orange", "wall": "red", "pair": "magenta", "loose": "yellow"}
outs = {}
for m in models:
    if mode == "prod":
        reader = lr.LocalReader(threads=4)
    else:
        rsu.ROLE_TAG = m
        rd = rsu.Readers("fold", 4)
        (reader, _), files = rd.get(name)
    path = rsu.MODELS / f"{m}.onnx" if (rsu.MODELS / f"{m}.onnx").exists() else rsu.REPO / "app/assets" / f"{m}.onnx"
    if mode == "fold":
        det, part, role = rsu.fold_of(name, rsu.Readers("fold", 1).meta)
        fr = rsu.FOLD_ROLE[role].replace("tile-roles-rot", m, 1)
        path = rsu.MODELS / fr if (rsu.MODELS / fr).exists() else path
    net = roles.RoleNet(path, threads=4)
    o = roles.read_roles(reader, jpeg, s["side"], grid, "hybrid", net=net)
    outs[m] = o
    hand = [t["tile"] for t in o["tiles"]] + ([o["separate_tile"]["tile"]] if o.get("separate_tile") else [])
    print(f"== {m} ({path.name}) 손패 {hand} 울기 {[m_['tiles'] for m_ in o['melds']]} block {o.get('block')}")
    im = Image.open(io.BytesIO(jpeg)).convert("RGB")
    d = ImageDraw.Draw(im)
    for i, x in enumerate(o["roles"]):
        bx, by, bw, bh = x["box"]
        d.rectangle((bx, by, bx + bw, by + bh), outline=COL.get(x["role"], "gray"), width=10 if x["in_seat"] else 4)
        d.text((bx, by - 28), str(i), fill="white")
    im.resize((im.width // 3, im.height // 3)).save(HERE / "data/role/v2/debug_rot" / f"{v}_{name}_{m}.jpg", quality=85)
a, b = models[0], models[1]
ra, rb = outs[a]["roles"], outs[b]["roles"]
print("상자 수", len(ra), len(rb))
for i, (x, y) in enumerate(zip(ra, rb)):
    if x["role"] != y["role"] or x["in_seat"] != y["in_seat"]:
        print(f"  {i} box {x['box']} in_seat {x['in_seat']} | {a}: {x['role']} {x.get('conf')} | {b}: {y['role']} {y.get('conf')}")
