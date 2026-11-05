"""7회차 라벨 전수 조사 그림(2026-11-04, 사용자 "라벨작업 전수조사해서 니 눈으로 확인하면서 고쳐", 노트북, API 없음).

사진마다 det_obb.py 의 rects.json 라벨을 원본에 그리고, 그 사진을 학습하지 않은 앞면·뒷면 2종 검출기(표 1-54 2차, 오전 사진 = fold_am,
오후 = fold_pm, k = fold_k)의 검출과 어긋난 곳을 표시한다. 그림은 사람이 보고 고치는 용도이고, 고친 값은 det_backs.py(FACE_*·BACK_*)와
obb/review_obb.json 에 넣는다.
  하늘색 = 앞면 축 상자, 빨강 = 뒷면 축 상자, 초록(굵게) = 회전 상자(rot·fixed·row)
  노랑 = 검출기는 찾았는데 같은 종류 라벨이 없음(IoU 0.3 미만) — 빠진 라벨 후보, 글자 F/B + 확신도
  자홍 = 라벨은 있는데 같은 종류 검출이 없음 — 헛 라벨·종류 틀림 후보
  python -I -X utf8 experiments/tile_classifier/det_audit.py [사진 이름 ...]
결과 data/det/obb/audit/<사진>.jpg(긴 변 3000), audit/diff.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
DET = HERE / "data" / "det"
OUT = DET / "obb" / "audit"
FB = DET / "kaggle_out_fb2" / "out"


def fold(name: str) -> str:
    if name.startswith("k"):
        return "fold_k"
    return "fold_am" if name < "20261031_14" else "fold_pm"


def iou(a, b) -> float:
    ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    i = ix * iy
    return i / (a[2] * a[3] + b[2] * b[3] - i + 1e-9)


def detect(model, bgr: np.ndarray) -> list:
    """통째 + 9토막(det_relabel.detect 와 같은 방식), 두 종류 모두. [(cls, x, y, w, h, conf)]."""
    H, W = bgr.shape[:2]
    TW, TH = 2040, 1530
    out = []
    for x0, y0, w, h in [(0, 0, W, H)] + [(x0, y0, TW, TH) for y0 in (0, (H - TH) // 2, H - TH) for x0 in (0, (W - TW) // 2, W - TW)]:
        r = model.predict(bgr[y0:y0 + h, x0:x0 + w], imgsz=1280, conf=0.25, verbose=False, device="cpu")[0]
        for (a, b, c, d), cl, s in zip(r.boxes.xyxy.tolist(), r.boxes.cls.tolist(), r.boxes.conf.tolist()):
            if w != W and ((a < 3 and x0 > 0) or (b < 3 and y0 > 0) or (c > TW - 3 and x0 + TW < W) or (d > TH - 3 and y0 + TH < H)):
                continue
            out.append((int(cl), a + x0, b + y0, c - a, d - b, s))
    keep = []  # 같은 종류끼리 겹치면 확신도 높은 것만
    for o in sorted(out, key=lambda o: -o[5]):
        if all(not (k[0] == o[0] and iou(k[1:5], o[1:5]) > 0.5) for k in keep):
            keep.append(o)
    return keep


def main() -> None:
    from ultralytics import YOLO

    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    rects = json.loads((DET / "obb" / "rects.json").read_text(encoding="utf-8"))
    names = sys.argv[1:] or list(rects)
    models = {}
    diff_f = OUT / "diff.json"
    diff = json.loads(diff_f.read_text(encoding="utf-8")) if diff_f.exists() else {}
    for name in names:
        r = rects[name]
        bgr = cv2.imread(r["path"])
        H, W = bgr.shape[:2]
        fo = fold(name)
        if fo not in models:
            models[fo] = YOLO(str(FB / f"{fo}.pt"))
        dets = detect(models[fo], bgr)
        labs = [(it["cls"], it["box"]) for it in r["items"]]
        miss = [d for d in dets if all(not (c == d[0] and iou(b, d[1:5]) >= 0.3) for c, b in labs)]
        extra = [(c, b) for c, b in labs if all(not (d[0] == c and iou(b, d[1:5]) >= 0.3) for d in dets)]
        img = bgr.copy()
        for it in r["items"]:
            x, y, w, h = it["box"]
            rotated = it["status"] in ("rot", "fixed", "row") and it["rect"][2] != 0.0
            col = (255, 255, 0) if it["cls"] == 0 else (0, 0, 255)
            if rotated:
                pts = cv2.boxPoints((tuple(it["rect"][0]), tuple(it["rect"][1]), it["rect"][2])).astype(np.int32)
                cv2.polylines(img, [pts], True, (0, 220, 0), 5)
                cv2.polylines(img, [pts], True, col, 2)
            else:
                cv2.rectangle(img, (x, y), (x + w, y + h), col, 3)
        for c, x, y, w, h, s in miss:
            cv2.rectangle(img, (int(x) - 6, int(y) - 6), (int(x + w) + 6, int(y + h) + 6), (0, 255, 255), 5)
            cv2.putText(img, f"{'F' if c == 0 else 'B'}{s:.2f}", (int(x), int(y) - 10), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 255), 3)
        for c, (x, y, w, h) in extra:
            cv2.rectangle(img, (x - 10, y - 10), (x + w + 10, y + h + 10), (255, 0, 255), 5)
        cv2.putText(img, f"{name}  miss {len(miss)}  extra {len(extra)}", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 2.5, (0, 255, 255), 6)
        s = 3000 / max(W, H)
        cv2.imwrite(str(OUT / f"{name}.jpg"), cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 85])
        diff[name] = dict(miss=[[c, round(x), round(y), round(w), round(h), round(sc, 2)] for c, x, y, w, h, sc in miss], extra=[[c, *b] for c, b in extra])
        print(name, "검출만", len(miss), "라벨만", len(extra), flush=True)
        diff_f.write_text(json.dumps(diff, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
