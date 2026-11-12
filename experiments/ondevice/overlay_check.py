"""가짜 헤드 시연(2026-11-11 15:37~15:41) 겹쳐 보기 재현: 가짜 헤드가 보낸 조건(긴 변 2400 thumbnail·q80)과 실제 헤드 조건(4080 원본)을
PC 에서 같은 ondevice.overlay 로 돌려 패마다 비교하고, 그림을 남긴다(experiments/ondevice/build/overlay_check/).
  python -X utf8 experiments/ondevice/overlay_check.py
"""
import io, json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, "C:/Users/jjh7757/dev/mahjong-recognizer")
sys.path.append(str(ROOT / "android/app/src/main/python"))
sys.path.insert(0, str(ROOT / "experiments/speed"))
import ondevice  # noqa: E402
import robust_suite as rs  # noqa: E402

SEQ = ["20261107_153311", "k25", "20261031_133826", "20261107_140015", "k12", "20261031_164501"]
OUT = ROOT / "experiments/ondevice/build/overlay_check"
OUT.mkdir(parents=True, exist_ok=True)
grids = {s["name"]: s["grid"] for s in rs.scenes("dev")}
COL = {"hand": (255, 220, 0), "meld": (255, 80, 200), "river": (80, 200, 255), "wall": (170, 170, 170), "pair": (255, 140, 0), "loose": (0, 255, 120)}


def q(g):
    return {k: str(g[k]) for k in ("x1", "x2", "y1", "y2")}


def iou(a, b):
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx)); iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    i = ix * iy
    return i / (aw * ah + bw * bh - i + 1e-12)


rows = {}
for name in SEQ:
    src = ROOT / f"experiments/ondevice/build/test_originals/{name}.jpg"
    raw = src.read_bytes()
    im = Image.open(src).convert("RGB"); im.thumbnail((2400, 2400))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=80); small = buf.getvalue()
    g = q(grids[name])
    a = json.loads(ondevice.overlay(raw, g))["tiles"]
    b = json.loads(ondevice.overlay(small, g))["tiles"]
    pairs, only_a, only_b, diff = [], [], list(range(len(b))), []
    for i, t in enumerate(a):
        j = max(range(len(b)), key=lambda j: iou(t["b"], b[j]["b"]), default=None)
        if j is not None and iou(t["b"], b[j]["b"]) > 0.5:
            pairs.append((i, j)); only_b.remove(j) if j in only_b else None
            if t["t"] != b[j]["t"] or t["r"] != b[j]["r"]:
                diff.append({"box": t["b"], "4080": (t["t"], t["tc"], t["r"]), "2400": (b[j]["t"], b[j]["tc"], b[j]["r"])})
        else:
            only_a.append({"box": t["b"], "4080": (t["t"], t["tc"], t["r"])})
    rows[name] = {"n4080": len(a), "n2400": len(b), "diff": diff, "only4080": only_a, "only2400": [{"box": b[j]["b"], "2400": (b[j]["t"], b[j]["tc"], b[j]["r"])} for j in only_b]}
    print(f"{name}: 4080 {len(a)}장 · 2400 {len(b)}장 · 종류·역할 다름 {len(diff)} · 4080 에만 {len(only_a)} · 2400 에만 {len(only_b)}")
    # 그림: 4080 원본에 4080 답(굵게)·2400 답(다르면 빨강)
    big = Image.open(src).convert("RGB"); W, H = big.size
    d = ImageDraw.Draw(big); f = ImageFont.truetype("arial.ttf", 40)
    for i, t in enumerate(a):
        x, y, w, h = t["b"]; c = COL.get(t["r"], (255, 255, 255))
        d.rectangle([x * W, y * H, (x + w) * W, (y + h) * H], outline=c, width=5)
        d.text((x * W, y * H - 44), t["t"], fill=c, font=f)
    for dd in diff:
        x, y, w, h = dd["box"]
        d.rectangle([x * W - 6, y * H - 6, (x + w) * W + 6, (y + h) * H + 6], outline=(255, 0, 0), width=6)
        d.text((x * W, (y + h) * H + 4), dd["2400"][0], fill=(255, 0, 0), font=f)
    big.save(OUT / f"{name}.jpg", quality=85)
(OUT / "diff.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
