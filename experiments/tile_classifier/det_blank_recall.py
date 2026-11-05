"""검출기가 라벨의 白(무늬 없는 상자)을 얼마나 잡는지 — 회차별 비교(2026-11-04, 노트북 CPU, API 없음). metrics 표 1-62.

사진마다 그 사진을 학습하지 않은 fold 모델(오전 = fold_b, 오후·B·C·D = fold_a)로 det_relabel.detect(통째 + 9토막) 하고,
라벨 상자 중 白(det_build.is_blank) 이 IoU 0.5 이상으로 잡혔는지 센다. 무늬 있는 상자의 재현율과 헛검출(라벨과 안 겹치는 상자)도 같이(白 증강이 다른 패를 해치거나 흰 것을 패로 잡지 않는지).
  python -I -X utf8 experiments/tile_classifier/det_blank_recall.py r2 r3
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import det_build as dbd  # noqa: E402
import det_relabel as dr  # noqa: E402
from det_backs import fixed_faces  # noqa: E402

DET = HERE / "data" / "det"


def iou(a, b) -> float:
    ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    i = ix * iy
    return i / (a[2] * a[3] + b[2] * b[3] - i + 1e-9)


def main() -> None:
    from ultralytics import YOLO

    sys.stdout.reconfigure(encoding="utf-8")
    rows = json.loads((DET / "boxes_final.json").read_text(encoding="utf-8"))
    labels = {}
    for name, r in rows.items():
        rgb = np.asarray(Image.open(r["path"]).convert("RGB"))
        faces = fixed_faces(name, r["boxes"])
        labels[name] = (faces, [dbd.is_blank(rgb, b) for b in faces])
    print("라벨 白", sum(sum(bl) for _, bl in labels.values()), "/ 전체", sum(len(f) for f, _ in labels.values()), flush=True)
    for tag in sys.argv[1:]:
        out = DET / f"kaggle_out_{tag}" / "out"
        models = {k: YOLO(str(out / f"fold_{k}.pt")) for k in "ab"}
        hit_b = n_b = hit_i = n_i = fp = fp_big = 0
        per = []
        for name, r in rows.items():
            am = name.startswith("2026") and name < "20261031_14"
            det = dr.detect(models["b" if am else "a"], Image.open(r["path"]).convert("RGB"))
            boxes = [(x0, y0, x1 - x0, y1 - y0) for x0, y0, x1, y1, _ in det]
            faces, blank = labels[name]
            hb = nb = 0
            for f, is_b in zip(faces, blank):
                found = any(iou(f, b) >= 0.5 for b in boxes)
                if is_b:
                    nb += 1
                    hb += found
                else:
                    n_i += 1
                    hit_i += found
            hit_b += hb
            n_b += nb
            # 헛검출: 어느 라벨과도 IoU 0.3 미만인 상자(라벨이 빠뜨린 진짜 패도 섞일 수 있다 — 회차끼리 비교용)
            fp += sum(all(iou(b, f) < 0.3 for f in faces) for b in boxes)
            fp_big += sum(all(iou(b, f) < 0.3 for f in faces) and max(b[2], b[3]) > 1.6 * sorted(max(f[2], f[3]) for f in faces)[len(faces) // 2] for b in boxes)
            if nb:
                per.append(f"{name[-6:]} {hb}/{nb}")
        print(f"[{tag}] 白 재현 {hit_b}/{n_b}  무늬 패 재현 {hit_i}/{n_i}  헛검출 {fp}(그중 패의 1.6배 초과 {fp_big}) | 사진별 白:", " ".join(per), flush=True)


if __name__ == "__main__":
    main()
