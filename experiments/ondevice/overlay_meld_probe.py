"""겹쳐 보기(`ondevice.overlay`)로 판 중 울기를 셀 수 있나 — 추적 프레임 몇 장에 돌려 자리별 울기(meld) 상자 수를 찍는다(2026-11-16).

사용자 "겹쳐 보기를 켜면 울기를 감지할 수 있지 않나". 이 매장은 울기를 펠트 밖 흰 테두리 위에 놓아 픽셀(흰 면 넓이) 추적이 못 본다(metrics 표 11-3).
PC 에서 태블릿과 같은 `android/app/src/main/python/ondevice.py` 를 그대로 부른다(운영 모델).

  python -X utf8 experiments/ondevice/overlay_meld_probe.py <추적 폴더> <x1,x2,y1,y2> <hh:mm:ss>... [--draw <폴더>]
"""
import io
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, "C:/Users/jjh7757/dev/mahjong-recognizer")
sys.path.append(str(ROOT / "android/app/src/main/python"))
import ondevice  # noqa: E402

args = sys.argv[1:]
draw = None
if "--draw" in args:
    i = args.index("--draw")
    draw = Path(args[i + 1])
    draw.mkdir(parents=True, exist_ok=True)
    args = args[:i] + args[i + 2:]
track, grid, times = Path(args[0]), args[1].split(","), args[2:]
q = dict(zip(("x1", "x2", "y1", "y2"), grid))
frames = {}
for z in sorted(track.glob("frames_*.zip")):
    zf = zipfile.ZipFile(z)
    for f in json.loads(zf.read("frames.json").decode("utf-8"))["frames"]:
        frames[f["at"][11:19]] = (zf, f["file"])
for t in times:
    t = max((k for k in frames if k <= t), default=min(frames))  # 그 시각 또는 바로 앞 프레임
    zf, fn = frames[t]
    raw = zf.read(fn)
    o = json.loads(ondevice.overlay(raw, q))
    tiles = o["tiles"]
    roles = Counter(x["r"] for x in tiles)
    melds = {}
    for x in tiles:
        if x["r"] == "meld":
            melds.setdefault(x["s"], []).append(f'{x["t"]}({x["rc"]:.2f})')
    print(t, f"상자 {len(tiles)}", dict(roles), "울기:", melds or "없음", "ms", o.get("ms"))
    if draw:
        from PIL import Image, ImageDraw

        im = Image.open(io.BytesIO(raw)).convert("RGB")
        W, H = im.size
        d = ImageDraw.Draw(im)
        col = {"hand": (255, 220, 0), "meld": (255, 0, 200), "river": (80, 200, 255), "wall": (170, 170, 170), "pair": (255, 140, 0), "loose": (0, 255, 120)}
        for x in tiles:
            bx, by, bw, bh = x["b"]
            d.rectangle([bx * W, by * H, (bx + bw) * W, (by + bh) * H], outline=col.get(x["r"], (255, 255, 255)), width=max(3, W // 400))
        im.thumbnail((1400, 1400))
        im.save(draw / f"{track.name[9:15]}_{t.replace(':', '')}.jpg", quality=82)
