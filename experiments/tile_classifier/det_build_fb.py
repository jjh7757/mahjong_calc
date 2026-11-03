"""앞면·뒷면 2종 검출기 데이터셋을 만든다(2026-11-03, 노트북 CPU, API 없음). det_backs.py 다음에. 사진은 다시 저장해 EXIF 를 없앤다.

토막은 det_build.py 와 같다(통째 + 9토막, <사진>__<토막>.jpg). 뒷면 상자 가운데가 앞면 상자 안이면 뺀다(패산 위 표시패). review_backs.json 이 있으면 지우기·더하기를 반영한다.
학습 전용 재색칠본 <사진>__<토막>__c<번>.jpg: 토막마다 2장, 뒷면·펠트·탁자 테두리 색을 무작위로 바꾼다. 다른 탁자 흉내일 뿐이라 시험에 넣지 않는다(캐글 스크립트가 __c 를 시험에서 뺀다).
  python -I experiments/tile_classifier/det_build_fb.py
결과 data/det/ds_fb/{images,labels}, dataset-metadata.json, sample_recolor.jpg
"""
from __future__ import annotations

import json
import random
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from det_backs import poly_mask  # noqa: E402

DET = HERE / "data" / "det"
ZP = HERE / "data" / "zone_points"
DS = DET / "ds_fb"
TW, TH = 2040, 1530
SEED = 20261103
# 사진에서 본 다른 탁자 색(table1 파랑, table2 검정, 방송 노랑·주황)과 그 밖의 흔한 색. BGR
BACKS = [(200, 90, 30), (28, 25, 25), (40, 170, 240), (70, 130, 40), (40, 40, 170), (90, 40, 20), (40, 70, 110), (230, 180, 120), None]
FELTS = [(125, 120, 0), (140, 70, 30), (120, 50, 80), (40, 30, 130), (120, 120, 120), (35, 35, 35), (60, 85, 110), None]
FRAMES = [(25, 25, 25), (40, 60, 90), (60, 110, 170), (70, 70, 70), None]


def repaint(lab: np.ndarray, mask: np.ndarray, bgr) -> None:
    """mask 안 색을 목표 색으로. 밝기 무늬는 유지한다."""
    m = mask > 127
    if bgr is None or m.sum() < 50:
        return
    t = cv2.cvtColor(np.uint8([[bgr]]), cv2.COLOR_BGR2LAB)[0, 0].astype(np.float32)
    L = lab[..., 0]
    mean = float(np.median(L[m]))
    L[m] = np.clip((L[m] - mean) * (0.6 if t[0] < 60 else 1.0) + t[0], 0, 255)
    lab[..., 1][m] = t[1]
    lab[..., 2][m] = t[2]


def recolor(img: np.ndarray, back: np.ndarray, felt: np.ndarray, frame: np.ndarray, rng: random.Random) -> np.ndarray:
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    repaint(lab, back, rng.choice(BACKS))
    repaint(lab, felt, rng.choice(FELTS))
    repaint(lab, frame, rng.choice(FRAMES))
    return cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2BGR)


def label_lines(boxes: list, cls: int, x0: int, y0: int, w: int, h: int) -> list[str]:
    lines = []
    for bx, by, bw, bh in boxes:
        ix0, iy0, ix1, iy1 = max(bx, x0), max(by, y0), min(bx + bw, x0 + w), min(by + bh, y0 + h)
        if ix1 <= ix0 or iy1 <= iy0 or (ix1 - ix0) * (iy1 - iy0) < 0.5 * bw * bh:
            continue
        lines.append(f"{cls} {((ix0 + ix1) / 2 - x0) / w:.6f} {((iy0 + iy1) / 2 - y0) / h:.6f} {(ix1 - ix0) / w:.6f} {(iy1 - iy0) / h:.6f}")
    return lines


def clean_backs(name: str, backs: list, faces: list, review: dict) -> list:
    keep = []
    for b in backs:
        cx, cy = b[0] + b[2] / 2, b[1] + b[3] / 2
        if any(f[0] <= cx <= f[0] + f[2] and f[1] <= cy <= f[1] + f[3] for f in faces):
            continue
        keep.append(b)
    r = review.get(name, {})
    for px, py in r.get("remove", []):
        keep = [b for b in keep if not (b[0] <= px <= b[0] + b[2] and b[1] <= py <= b[1] + b[3])]
    return keep + [list(b) for b in r.get("add", [])]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    shutil.rmtree(DS, ignore_errors=True)
    (DS / "images").mkdir(parents=True)
    (DS / "labels").mkdir(parents=True)
    faces = json.loads((DET / "boxes_final.json").read_text(encoding="utf-8"))
    backs = json.loads((DET / "backs" / "boxes.json").read_text(encoding="utf-8"))
    labels = json.loads((ZP / "labels.json").read_text(encoding="utf-8"))
    rf = DET / "backs" / "review_backs.json"
    review = json.loads(rf.read_text(encoding="utf-8")) if rf.exists() else {}
    drop = set(review.get("_drop_photos", []))
    rng = random.Random(SEED)
    n = recol = nf = nb = 0
    samples = []
    final = {}
    for name, r in faces.items():
        if name in drop or name not in backs:
            print(name, "뺌")
            continue
        img = cv2.imread(r["path"])
        H, W = img.shape[:2]
        m = cv2.resize(cv2.imread(str(DET / "backs" / "masks" / f"{name}.png")), (W, H), interpolation=cv2.INTER_NEAREST)
        back, felt = m[..., 2], m[..., 1]
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        white = ((hsv[..., 1] < 55) & (hsv[..., 2] > 120)).astype(np.uint8) * 255
        fq = labels[name]["felt"]
        frame = cv2.bitwise_and(white, cv2.bitwise_and(poly_mask(img.shape, fq, 0.14), cv2.bitwise_not(poly_mask(img.shape, fq, 0.012))))
        bs = clean_backs(name, backs[name], r["boxes"], review)
        final[name] = dict(faces=r["boxes"], backs=bs)
        nf += len(r["boxes"])
        nb += len(bs)
        cuts = [("w", 0, 0, W, H)]
        for i, y0 in enumerate((0, (H - TH) // 2, H - TH)):
            for j, x0 in enumerate((0, (W - TW) // 2, W - TW)):
                cuts.append((f"{i}{j}", x0, y0, TW, TH))
        for tag, x0, y0, w, h in cuts:
            lines = label_lines(r["boxes"], 0, x0, y0, w, h) + label_lines(bs, 1, x0, y0, w, h)
            s = 2040 / w if tag == "w" else 1.0
            crop = lambda a: cv2.resize(a[y0:y0 + h, x0:x0 + w], None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
            part = crop(img)
            cv2.imwrite(str(DS / "images" / f"{name}__{tag}.jpg"), part, [cv2.IMWRITE_JPEG_QUALITY, 90])
            (DS / "labels" / f"{name}__{tag}.txt").write_text("\n".join(lines), encoding="utf-8")
            n += 1
            mb, mf, mr = crop(back), crop(felt), crop(frame)
            for c in range(2):
                out = recolor(part, mb, mf, mr, rng)
                cv2.imwrite(str(DS / "images" / f"{name}__{tag}__c{c}.jpg"), out, [cv2.IMWRITE_JPEG_QUALITY, 85])
                (DS / "labels" / f"{name}__{tag}__c{c}.txt").write_text("\n".join(lines), encoding="utf-8")
                recol += 1
                if tag == "w" and len(samples) < 12 and c == 0:
                    samples.append(cv2.resize(out, (680, 510)))
        print(name, "앞면", len(r["boxes"]), "뒷면", len(bs), flush=True)
    while len(samples) % 4:
        samples.append(np.zeros_like(samples[0]))
    grid = np.vstack([np.hstack(samples[i:i + 4]) for i in range(0, len(samples), 4)])
    cv2.imwrite(str(DET / "backs" / "sample_recolor.jpg"), grid, [cv2.IMWRITE_JPEG_QUALITY, 80])
    (DET / "backs" / "boxes_final_fb.json").write_text(json.dumps(final), encoding="utf-8")
    (DS / "dataset-metadata.json").write_text(json.dumps({"title": "mahjong tile face back", "id": "jjh7757/mahjong-tile-faceback", "licenses": [{"name": "unknown"}]}, indent=1), encoding="utf-8")
    size = sum(p.stat().st_size for p in DS.rglob("*") if p.is_file())
    print("원본 토막", n, "재색칠", recol, "앞면 상자", nf, "뒷면 상자", nb, "MB", size // 2**20)


if __name__ == "__main__":
    main()
