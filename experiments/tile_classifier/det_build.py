"""검출기 학습 데이터셋을 만든다(2026-11-01). det_boxes.py 다음에. 사진은 다시 저장해 EXIF 를 없앤다. API 없음.

토막: 사진마다 통째(긴 변 2040) 1장 + 원본 2040×1530 토막 9장(절반 겹침). 토막에 절반 이상 들어온 상자만 넣는다.
파일 이름 <사진>__<토막>.jpg 로 나눔을 정한다: fold_a 시험 = 매장 오후·B·C·D, fold_b 시험 = 매장 오전·B·C·D. B·C·D 는 두 나눔 모두 시험, final 만 학습에 쓴다.
라벨: 1회차는 YOLO11 + 자체 분류기, 2회차는 1회차 YOLO26 검출을 눈으로 고친 값(boxes_final.json).
  python -I experiments/tile_classifier/det_build.py
결과 data/det/ds/{images,labels}, dataset-metadata.json
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "det"
DS = OUT / "ds"
TW, TH = 2040, 1530


def label_lines(boxes: list, x0: int, y0: int, w: int, h: int, scale: float = 1.0) -> list[str]:
    lines = []
    for bx, by, bw, bh in boxes:
        ix0, iy0, ix1, iy1 = max(bx, x0), max(by, y0), min(bx + bw, x0 + w), min(by + bh, y0 + h)
        if ix1 <= ix0 or iy1 <= iy0 or (ix1 - ix0) * (iy1 - iy0) < 0.5 * bw * bh:
            continue
        lines.append(f"0 {((ix0 + ix1) / 2 - x0) / w:.6f} {((iy0 + iy1) / 2 - y0) / h:.6f} {(ix1 - ix0) / w:.6f} {(iy1 - iy0) / h:.6f}")
    return lines


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    shutil.rmtree(DS, ignore_errors=True)
    (DS / "images").mkdir(parents=True)
    (DS / "labels").mkdir(parents=True)
    src = OUT / "boxes_final.json" if (OUT / "boxes_final.json").exists() else OUT / "boxes.json"  # 2회차부터 det_review.py 결과
    rows = json.loads(src.read_text(encoding="utf-8"))
    n = empty = 0
    for name, r in rows.items():
        im = Image.open(r["path"]).convert("RGB")
        W, H = im.size
        whole = im.resize((2040, round(H * 2040 / W)))
        whole.save(DS / "images" / f"{name}__w.jpg", quality=90)
        (DS / "labels" / f"{name}__w.txt").write_text("\n".join(label_lines(r["boxes"], 0, 0, W, H)), encoding="utf-8")
        n += 1
        for i, y0 in enumerate((0, (H - TH) // 2, H - TH)):
            for j, x0 in enumerate((0, (W - TW) // 2, W - TW)):
                lines = label_lines(r["boxes"], x0, y0, TW, TH)
                im.crop((x0, y0, x0 + TW, y0 + TH)).save(DS / "images" / f"{name}__{i}{j}.jpg", quality=90)
                (DS / "labels" / f"{name}__{i}{j}.txt").write_text("\n".join(lines), encoding="utf-8")
                n += 1
                empty += not lines
        print(name, flush=True)
    (DS / "dataset-metadata.json").write_text(json.dumps({"title": "mahjong tile faces", "id": "jjh7757/mahjong-tile-faces", "licenses": [{"name": "unknown"}]}, indent=1), encoding="utf-8")
    size = sum(p.stat().st_size for p in DS.rglob("*") if p.is_file())
    print("이미지", n, "상자 없는 토막", empty, "MB", size // 2**20)


if __name__ == "__main__":
    main()
