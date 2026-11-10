"""역할 모델 변형용 기본 입력 v2 — 초안 라벨 만들기(2026-11-08).

대상: 합성본 6장(data/role/v2/images — 151320 은 11-08 사용자 결정으로 폐기), 라벨 없이 살릴 10-31 3장(170105·164501·171245), 11-07 쓰기 22장.
운영 서버(RECOGNIZER_REPO, 641681b)의 app.roles.read_roles 를 그대로 돌려 검출 상자(앞면 = 자리 크롭 + 사진 전체, 뒷면)와
운영 역할 모델의 역할을 초안으로 저장하고, 사진 위에 번호·역할을 그린 검토 그림을 남긴다. 사람이 role_v2_review.json 으로 고친다.

  python -X utf8 experiments/tile_classifier/role_v2_draft.py            → data/role/v2/draft.json, overlay/<이름>.jpg
"""
import io, json, os, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = os.environ.get("RECOGNIZER_REPO", "C:/Users/jjh7757/dev/mahjong-recognizer")
sys.path.insert(0, REPO); sys.path.insert(0, str(HERE.parent / "speed"))
from PIL import Image, ImageDraw, ImageFont
from app import local_read as lr, roles
from app.recognizer import prepare_image
import seat_grow as sg

V2 = HERE / "data" / "role" / "v2"
E = HERE.parent
G = {s["name"]: (s["side"], s["grid"]) for s in sg.scenes()}
P = {p["name"]: p for p in json.load(open(E / "visit_20261107/review/pairs_1107.json", encoding="utf-8"))}
SIDE = {"left": "left", "right": "right", "top": "top", "bottom": "bottom"}
COMPOSITE = ["20261031_172424", "20261031_174020", "20261031_124654", "20261031_125839", "20261031_130743", "20261031_132239",
             "20261031_165614", "20261031_181209"]  # 165614·181209: 11-09 표시패 4장 짝 합성(role_v2_pair_synth2.py)으로 기존 라벨 → 합성본 초안
FIX1031 = ["20261031_170105", "20261031_164501", "20261031_171245"]
D1107 = ["20261107_121515", "20261107_122315", "20261107_123102", "20261107_123721", "20261107_124650", "20261107_125510", "20261107_130623",
         "20261107_131835", "20261107_135420", "20261107_135842", "20261107_140015", "20261107_142136", "20261107_142639", "20261107_143234",
         "20261107_144348", "20261107_145058", "20261107_153029", "20261107_153311", "20261107_153939", "20261107_154417", "20261107_154904", "20261107_155553"]


def scene(name):
    if name in G:
        side, grid = G[name]
    else:
        side, grid = SIDE[P[name]["winner"]], P[name]["grid"]
    if name in COMPOSITE:
        path, kind = V2 / "images" / f"{name[-6:]}_after.jpg", "composite"
    else:
        path, kind = E / f"visit_{name[:8]}" / "captures" / name / "original.jpg", "photo"
    return side, grid, path, kind


def main():
    cap = {}
    for fn in ("tokens", "tokens_frame"):
        o = getattr(roles, fn)
        def w(*a, _o=o, _fn=fn, **k):
            cap["args"], cap["kw"], cap["fn"] = a, k, _fn
            cap["x"] = _o(*a, **k)
            return cap["x"]
        setattr(roles, fn, w)
    reader = lr.LocalReader()
    out, font = {}, ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 26)
    color = {"hand": "blue", "meld": "cyan", "river": "orange", "wall": "red", "pair": "magenta", "loose": "yellow"}
    only = [n for n in os.environ.get("ONLY", "").split(",") if n]  # ONLY=이름,이름 → 그 장면만 다시 만들어 기존 draft.json 에 덮어씀
    if only:
        out = json.loads((V2 / "draft.json").read_text(encoding="utf-8"))
    for name in (only or COMPOSITE + FIX1031 + D1107):
        side, grid, path, kind = scene(name)
        jpeg = prepare_image(path.read_bytes(), 4080)
        r = roles.read_roles(reader, jpeg, side, grid, "hybrid", None, None, "saved")
        args, kw = cap["args"], cap["kw"]
        bi = 7 if cap["fn"] == "tokens" else 5  # tokens(allb, W, H, grid, side, feat, pts, backs) / tokens_frame(allb, tz, side, feat, pts, backs)
        backs = kw.get("backs") if "backs" in kw else (args[bi] if len(args) > bi else None)
        items = [dict(box=[int(v) for v in x["box"]], role=x["role"], conf=x["conf"], in_seat=x["in_seat"]) for x in r["roles"]]
        bk = [[int(v) for v in b[0]] for b in (backs or [])]
        im = Image.open(io.BytesIO(jpeg)).convert("RGB")
        assert len(cap["x"]) == len(items) + len(bk), (name, len(cap["x"]), len(items), len(bk))
        out[name] = dict(side=side, size=list(im.size), grid=grid, kind=kind, image=str(path), items=items, backs=bk, frame_mode=cap["fn"],
                         tokens=[[round(float(v), 5) for v in row] for row in cap["x"]])  # 서버가 역할 모델에 넣은 그대로(앞면 items 순서 → 뒷면 backs 순서)
        d = ImageDraw.Draw(im)
        for b in bk:
            d.rectangle([b[0], b[1], b[0] + b[2], b[1] + b[3]], outline=(150, 150, 150), width=3)
        for i, it in enumerate(items):
            x, y, w_, h = it["box"]
            d.rectangle([x, y, x + w_, y + h], outline=color[it["role"]], width=7)
            d.text((x + 3, y - 30), str(i), font=font, fill=color[it["role"]])
        im.save(V2 / "overlay" / f"{name}.jpg", quality=82)
        print(name, side, kind, "앞면", len(items), "뒷면", len(bk), {k: sum(1 for t in items if t["role"] == k) for k in color})
    (V2 / "draft.json").write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")


if __name__ == "__main__":
    main()
