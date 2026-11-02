"""실제 추적 프레임에서 라벨 패를 읽을 수 있나(2026-11-01). API 없음. build_crops.py 다음에.

화료 사진(폴더 이름 = 시각)의 라벨 상자를 원본 → 프레임 좌표로 옮겨, 그 사진 앞뒤 [WINDOW]초 안 프레임에서 잘라 HaseLab 분류기로 읽는다.
프레임 안에서 패가 옮겨졌거나 손에 가리면 틀리므로, 시각 차이별로 나눠 본다. 학습 전 분류기 값.
  python -I experiments/tile_classifier/frame_real_check.py
결과 data/frame_real.json, data/frame_real_sheet.jpg
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import torch
from PIL import Image, ImageDraw
from torchvision import transforms as T

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / "yolo"))
import run_yolo as ry  # noqa: E402

DATA = HERE / "data"
CAP = ROOT / "experiments/visit_20261031/captures"
WINDOW = 45
ROT_CW = {"bottom": 0, "right": 90, "top": 180, "left": 270}
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
PAD = 0.12


def to_photo(x: dict) -> tuple[float, float, float, float]:
    """자리 크롭(그 사람 쪽으로 돌린 것) 상자 → 원본 사진 상자 (x0, y0, x1, y1)."""
    W, H = x["photo"]
    ymin, xmin, ymax, xmax = x["seat_box"]
    x0, y0 = round(xmin * W / 1000), round(ymin * H / 1000)
    cw, ch = round(xmax * W / 1000) - x0, round(ymax * H / 1000) - y0
    u, v, w, h = x["box"]
    r = ROT_CW[x["side"]]
    if r == 0:
        px, py, pw, ph = u, v, w, h
    elif r == 180:
        px, py, pw, ph = cw - u - w, ch - v - h, w, h
    elif r == 90:  # 시계 90°: (x, y) → (ch - y, x)
        px, py, pw, ph = v, ch - u - w, h, w
    else:  # 시계 270°: (x, y) → (y, cw - x)
        px, py, pw, ph = cw - v - h, u, h, w
    return x0 + px, y0 + py, x0 + px + pw, y0 + py + ph


def cut(frame: Image.Image, x: dict) -> Image.Image:
    sx = frame.width / x["photo"][0]
    x0, y0, x1, y1 = to_photo(x)
    pw, ph = (x1 - x0) * PAD, (y1 - y0) * PAD
    c = frame.crop((round((x0 - pw) * sx), round((y0 - ph) * sx), round((x1 + pw) * sx), round((y1 + ph) * sx)))
    return c.rotate(-ROT_CW[x["side"]], expand=True) if ROT_CW[x["side"]] else c


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    index = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
    by_scene = defaultdict(list)
    for x in index:
        if x["scene"].startswith("2026") and x["photo"][0] == 4080:
            by_scene[x["scene"]].append(x)
    frames = []
    for z in CAP.glob("*_track/frames_*.zip"):
        with zipfile.ZipFile(z) as f:
            for fr in json.loads(f.read("frames.json")).get("frames", []):
                frames.append((datetime.fromisoformat(fr["at"]), z, fr["file"], fr.get("why")))
    net = ry.HaseLab().net
    tf = T.Compose([T.Resize((224, 224)), T.ToTensor(), T.Normalize(MEAN, STD)])
    rows, sheet_rows = [], []
    for scene, items in by_scene.items():
        t0 = datetime.strptime(scene, "%Y%m%d_%H%M%S")
        near = sorted((f for f in frames if abs((f[0] - t0).total_seconds()) <= WINDOW), key=lambda f: f[0])
        for at, z, name, why in near:
            with zipfile.ZipFile(z) as f:
                frame = Image.open(io.BytesIO(f.read(name))).convert("RGB")
            if abs(frame.width / frame.height - 4 / 3) > 0.02:
                continue
            crops = [cut(frame, x) for x in items]
            with torch.no_grad():
                preds = [ry.HASE_CLASSES[k] for k in net(torch.stack([tf(c) for c in crops])).argmax(1).tolist()]
            ok = sum(p == x["tile"] for p, x in zip(preds, items))
            d = round((at - t0).total_seconds())
            rows.append(dict(scene=scene, frame=name, dt=d, size=[frame.width, frame.height], ok=ok, n=len(items), preds=preds, truth=[x["tile"] for x in items]))
            print(scene[-6:], name, f"{d:+d}초", frame.size, f"{ok}/{len(items)}", why, flush=True)
            if not sheet_rows or sheet_rows[-1][0] != scene:
                sheet_rows.append((scene, d, crops, preds, [x["tile"] for x in items]))
    (DATA / "frame_real.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("== 시각 차이별")
    for lo, hi in ((-45, -15), (-15, -3), (-3, 3), (3, 15), (15, 45)):
        v = [r for r in rows if lo <= r["dt"] < hi]
        n, ok = sum(r["n"] for r in v), sum(r["ok"] for r in v)
        print(f"{lo}~{hi}초: 프레임 {len(v)} 패 {ok}/{n}" + (f" ({100 * ok / n:.1f}%)" if n else ""))
    best = {}
    for r in rows:
        if r["scene"] not in best or r["ok"] / r["n"] > best[r["scene"]]["ok"] / best[r["scene"]]["n"]:
            best[r["scene"]] = r
    print("장면", len(by_scene), "프레임 있는 장면", len(best), "장면별 최고", sum(r["ok"] for r in best.values()), "/", sum(r["n"] for r in best.values()))
    high = [r for r in rows if r["ok"] / r["n"] >= 0.8]
    print("80% 이상 맞는 프레임(패가 그대로 놓였다고 볼 만함)", len(high), "그 안 패", sum(r["ok"] for r in high), "/", sum(r["n"] for r in high))
    print("그 안 틀림", Counter((t, p) for r in high for t, p in zip(r["truth"], r["preds"]) if t != p).most_common(10))
    cell = 64
    im = Image.new("RGB", (70 + 14 * cell, max(1, len(sheet_rows)) * (cell + 18)), "white")
    d = ImageDraw.Draw(im)
    for i, (scene, dt, crops, preds, truth) in enumerate(sheet_rows):
        d.text((2, i * (cell + 18) + 20), f"{scene[-6:]}\n{dt:+d}s", fill="black")
        for j, c in enumerate(crops[:14]):
            t = c.resize((cell, cell))
            im.paste(t, (70 + j * cell, i * (cell + 18)))
            d.text((72 + j * cell, i * (cell + 18) + cell), f"{truth[j]} {preds[j]}", fill="blue" if truth[j] == preds[j] else "red")
    im.save(DATA / "frame_real_sheet.jpg", quality=90)


if __name__ == "__main__":
    main()
