"""1회차 YOLO26 검출을 2회차 상자 라벨로 만든다(2026-11-02, 노트북 CPU, API 없음). YOLO11 라벨(boxes.json)은 안 쓴다.

사진마다 그 사진을 학습하지 않은 모델: 오후·B·C·D = fold_a, 오전 = fold_b. A·E(k00·k04·k20·k24)는 두 모델 다 학습에 썼으므로 fold_a(표시만).
통째 + 토막 9장(det_build 와 같은 자름)을 검출해 겹친 상자는 확신 높은 것 하나만. 패가 잘리는 토막 끝 상자는 뺀다.
  python -I experiments/tile_classifier/det_relabel.py
결과 data/det/boxes_r2.json, data/det/check_r2/<이름>.jpg(라벨 번호 표시), review_r2.json 이 있으면 고친 값을 반영
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from ultralytics import YOLO

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import det_build as db  # noqa: E402

DET = HERE / "data" / "det"
MODELS = DET / "kaggle_out" / "out"
CONF = 0.25


def merge(boxes: list[tuple]) -> list[tuple]:
    """(x0, y0, x1, y1, conf) 를 확신 순으로 보며, 이미 고른 상자와 많이 겹치면 버린다."""
    keep: list[tuple] = []
    for b in sorted(boxes, key=lambda t: -t[4]):
        area = (b[2] - b[0]) * (b[3] - b[1])
        dup = False
        for k in keep:
            ix = max(0, min(b[2], k[2]) - max(b[0], k[0]))
            iy = max(0, min(b[3], k[3]) - max(b[1], k[1]))
            if ix * iy > 0.5 * min(area, (k[2] - k[0]) * (k[3] - k[1])):
                dup = True
                break
        if not dup:
            keep.append(b)
    return keep


def detect(model: YOLO, im: Image.Image) -> list[tuple]:
    """앞면(종류 0)만. 1종 모델은 종류가 0 하나라 같고, 2종(6회차 face·back)은 뒷면을 뺀다."""
    W, H = im.size
    out: list[tuple] = []
    bx = lambda r: r.boxes if r.boxes is not None else r.obb  # 회전 상자 모델(7회차~)은 r.obb — xyxy 는 감싸는 축 상자
    r = model.predict(im, imgsz=1280, conf=CONF, verbose=False, device="cpu", classes=[0])[0]
    out += [(*b, c) for b, c in zip(bx(r).xyxy.tolist(), bx(r).conf.tolist())]
    for y0 in (0, (H - db.TH) // 2, H - db.TH):
        for x0 in (0, (W - db.TW) // 2, W - db.TW):
            r = model.predict(im.crop((x0, y0, x0 + db.TW, y0 + db.TH)), imgsz=1280, conf=CONF, verbose=False, device="cpu", classes=[0])[0]
            for (a, b, c, d), s in zip(bx(r).xyxy.tolist(), bx(r).conf.tolist()):
                # 토막 끝에 닿은 상자는 잘린 패일 수 있다(사진 끝이면 그대로)
                if (a < 3 and x0 > 0) or (b < 3 and y0 > 0) or (c > db.TW - 3 and x0 + db.TW < W) or (d > db.TH - 3 and y0 + db.TH < H):
                    continue
                out.append((a + x0, b + y0, c + x0, d + y0, s))
    return merge(out)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    (DET / "check_r2").mkdir(parents=True, exist_ok=True)
    old = json.loads((DET / "boxes.json").read_text(encoding="utf-8"))
    a, b = YOLO(str(MODELS / "fold_a.pt")), YOLO(str(MODELS / "fold_b.pt"))
    rows = {}
    for name, r in old.items():
        am = name.startswith("2026") and name < "20261031_14"
        im = Image.open(r["path"]).convert("RGB")
        bs = detect(b if am else a, im)
        boxes = [[round(x0), round(y0), round(x1 - x0), round(y1 - y0)] for x0, y0, x1, y1, _ in bs]
        rows[name] = dict(path=r["path"], split=r["split"], size=r["size"], boxes=boxes, conf=[round(t[4], 3) for t in bs], oof=name not in {"k00", "k04", "k20", "k24"})
        v = im.copy()
        d = ImageDraw.Draw(v)
        for i, (x, y, w, h) in enumerate(boxes):
            d.rectangle((x, y, x + w, y + h), outline=(0, 220, 255), width=4)
            d.text((x + 4, y + 2), str(i), fill=(255, 0, 0))
        v.save(DET / "check_r2" / f"{name}.jpg", quality=88)
        print(name, "1회차", len(r["boxes"]), "2회차", len(boxes), flush=True)
    (DET / "boxes_r2.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("합계 1회차", sum(len(r["boxes"]) for r in old.values()), "2회차", sum(len(r["boxes"]) for r in rows.values()))


if __name__ == "__main__":
    main()
