"""白(5z) 후보 상자를 YOLO11(nikmomo-s, 37종에 白 있음)로 만든다(2026-11-04, 노트북 CPU, API 없음). metrics 표 1-62.

왜: 우리 YOLO26 검출기 라벨(boxes_final.json)은 YOLO11 상자를 "무늬 있음" 조건으로 걸러 만든 것이라 白 이 거의 없고, 라벨 없는 白 은 배경으로 학습됐다.
YOLO11 은 白 을 잡으므로(헛검출도 많다) 그 상자 중 기존 라벨과 안 겹치고 · 크기·비율이 그 사진 패와 맞고 · 무늬가 없고 · 흰 비율이 높은 것만 후보로 모아 사람이 고른다.
  python -I -X utf8 experiments/tile_classifier/det_blank_cands.py
결과 data/det/blank/cands.json(이름 → [{box, conf, ink, white}]), check/<이름>.jpg(후보 번호, 기존 라벨 회색), sheet.jpg(후보 크롭 모음)
고른 뒤: data/det/blank/review.json {"이름": [번호, ...]} → det_build.py 가 boxes_final + 고른 白 로 데이터셋을 만든다.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, os.environ.get("RECOGNIZER_REPO", "C:/Users/jjh7757/dev/mahjong-recognizer"))
from app import river as rv  # noqa: E402
from app import seat as st  # noqa: E402
from det_backs import fixed_faces  # noqa: E402

DET = HERE / "data" / "det"
OUT = DET / "blank"
W_NIK = Path("C:/Users/jjh7757/dev/_downloads/nikmomo/mahjong-yolos-best.onnx")
CLASSES = ["1m", "1p", "1s", "1z", "2m", "2p", "2s", "2z", "3m", "3p", "3s", "3z", "4m", "4p", "4s", "4z", "5m", "5p", "5s", "5z", "6m", "6p", "6s", "6z",
           "7m", "7p", "7s", "7z", "8m", "8p", "8s", "9m", "9p", "9s", "0m", "0p", "0s"]
TILE, STRIDE = 1020, 510
CONF = 0.2
INK_MAX = 0.02  # 白 무늬 상한(서버 BLANK 0.01, 정답 白 0.0; 옆면 줄이 조금 들어오는 것 허용)
WHITE_MIN = 0.6


def iou(a, b) -> float:
    ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    i = ix * iy
    return i / (a[2] * a[3] + b[2] * b[3] - i + 1e-9)


def detect_5z(model, im: Image.Image) -> list[tuple]:
    W, H = im.size
    out = []
    xs = list(range(0, max(1, W - TILE) + 1, STRIDE))
    ys = list(range(0, max(1, H - TILE) + 1, STRIDE))
    if xs[-1] + TILE < W:
        xs.append(W - TILE)
    if ys[-1] + TILE < H:
        ys.append(H - TILE)
    for y0 in ys:
        for x0 in xs:
            r = model.predict(im.crop((x0, y0, x0 + TILE, y0 + TILE)), conf=CONF, imgsz=640, verbose=False)[0]
            for b in r.boxes:
                if CLASSES[int(b.cls)] != "5z":
                    continue
                a, c, d, e = b.xyxy[0].tolist()
                if (a < 3 and x0 > 0) or (c < 3 and y0 > 0) or (d > TILE - 3 and x0 + TILE < W) or (e > TILE - 3 and y0 + TILE < H):
                    continue  # 토막 끝에 걸린 상자
                out.append((a + x0, c + y0, d - a, e - c, float(b.conf)))
    out.sort(key=lambda t: -t[4])
    keep: list = []
    for b in out:
        if all(iou(b, k) < 0.5 for k in keep):
            keep.append(b)
    return keep


def main() -> None:
    from ultralytics import YOLO

    sys.stdout.reconfigure(encoding="utf-8")
    (OUT / "check").mkdir(parents=True, exist_ok=True)
    model = YOLO(str(W_NIK), task="detect")
    rows = json.loads((DET / "boxes_final.json").read_text(encoding="utf-8"))
    cands, crops = {}, []
    for name, r in rows.items():
        im = Image.open(r["path"]).convert("RGB")
        rgb = np.asarray(im)
        faces = fixed_faces(name, r["boxes"])
        tw = statistics.median(min(b[2], b[3]) for b in faces)
        th = statistics.median(max(b[2], b[3]) for b in faces)
        white = rv.white_mask(rgb)
        got = []
        for x, y, w, h, c in detect_5z(model, im):
            b = (round(x), round(y), round(w), round(h))
            if any(iou(b, f) >= 0.3 for f in faces):
                continue
            if not (0.7 * tw <= min(w, h) <= 1.4 * tw and 0.7 * th <= max(w, h) <= 1.4 * th and 1.1 <= max(w, h) / min(w, h) <= 1.7):
                continue
            ink = float(st.ink(rgb, b))
            wh = float(white[b[1]:b[1] + b[3], b[0]:b[0] + b[2]].mean())
            if ink > INK_MAX or wh < WHITE_MIN:
                continue
            got.append(dict(box=list(b), conf=round(c, 3), ink=round(ink, 4), white=round(wh, 3)))
        cands[name] = got
        d = ImageDraw.Draw(im)
        for f in faces:
            d.rectangle((f[0], f[1], f[0] + f[2], f[1] + f[3]), outline=(160, 160, 160), width=3)
        for i, g in enumerate(got):
            x, y, w, h = g["box"]
            d.rectangle((x, y, x + w, y + h), outline="red", width=6)
            d.text((x, y - 30), f"{i}", fill="red")
            crops.append((f"{name[-6:]}#{i}", im.crop((x - w // 2, y - h // 2, x + w + w // 2, y + h + h // 2)).resize((150, 180))))
        im.resize((im.width // 2, im.height // 2)).save(OUT / "check" / f"{name}.jpg", quality=80)
        print(name, "후보", len(got), flush=True)
    (OUT / "cands.json").write_text(json.dumps(cands, ensure_ascii=False, indent=1), encoding="utf-8")
    cols = 8
    rows_n = -(-len(crops) // cols)
    sheet = Image.new("RGB", (cols * 160, max(1, rows_n) * 200), "black")
    d = ImageDraw.Draw(sheet)
    for i, (tag, c) in enumerate(crops):
        sheet.paste(c, ((i % cols) * 160, (i // cols) * 200))
        d.text(((i % cols) * 160 + 2, (i // cols) * 200 + 182), tag, fill="yellow")
    sheet.save(OUT / "sheet.jpg", quality=85)
    print("후보 합계", len(crops))


if __name__ == "__main__":
    main()
