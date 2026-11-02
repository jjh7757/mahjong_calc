"""labels.json 으로 YOLO pose 데이터셋을 만든다(2026-11-02, API 없음). 사진은 긴 변 1020 으로 다시 저장해 EXIF 를 없앤다.
vis 0 은 0 0 0 으로 쓰고(사진 밖 좌표가 있으면 ultralytics 가 그 장을 버린다), 상자는 사진 안으로 자른 펠트 사각형이다.
펠트를 못 찾은 프레임(바닥·손·렌즈 가림)은 눈으로 본 뒤 빈 라벨로 넣는다. 나눔은 kernel/train_pose.py 가 index.json 으로 정한다.
  python -I experiments/zone_points/build_ds.py [--neg-sheet 그림경로]
결과 tile_classifier/data/zone_points/ds/{images,labels,index.json,dataset-metadata.json}
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from propose import DATA, LONG, load  # noqa: E402

DS = DATA / "ds"
BCD = {"k25", "k28", "k15", "k26", "k12", "k16"}
# 음성에서 뺀다: 탁자가 일부 보여 "탁자 없음" 이 틀린 것 9장, 사람 얼굴·상반신이 찍혀 외부에 올리지 않는 것 4장.
NEG_SKIP = {"f125948_0195", "f125948_0197", "f125948_0202", "f133940_0031", "f133940_0032", "f133940_0041", "f141615_0224", "f141615_0226", "f170310_0732",
            "f125948_0074", "f125948_0075", "f125948_0076", "f170310_0726"}


def label_line(r: dict) -> str:
    pts = r["felt"] + r["device"]
    xs = [min(max(x, 0.0), 1.0) for x, _ in r["felt"]]
    ys = [min(max(y, 0.0), 1.0) for _, y in r["felt"]]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    kp = []
    for (x, y), v in zip(pts, r["vis"]):
        kp += [f"{x:.5f}", f"{y:.5f}", "2"] if v else ["0", "0", "0"]
    return " ".join(["0", f"{(x0 + x1) / 2:.5f}", f"{(y0 + y1) / 2:.5f}", f"{x1 - x0:.5f}", f"{y1 - y0:.5f}"] + kp)


def save(src, path: Path) -> None:
    im = load(src)
    W, H = im.size
    s = LONG / max(W, H)
    im.resize((round(W * s), round(H * s))).save(path, quality=90)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--neg-sheet", default="")
    a = ap.parse_args()
    labels = json.loads((DATA / "labels.json").read_text(encoding="utf-8"))
    rows = json.loads((DATA / "proposals.json").read_text(encoding="utf-8"))
    negs = [n for n, r in rows.items() if r["felt"] is None and n not in NEG_SKIP]
    if a.neg_sheet:
        cols, tw, th = 10, 240, 180
        nrow = (len(negs) + cols - 1) // cols
        sh = Image.new("RGB", (cols * tw, nrow * th))
        d = ImageDraw.Draw(sh)
        for i, n in enumerate(negs):
            x, y = (i % cols) * tw, (i // cols) * th
            sh.paste(load(rows[n]["src"]).resize((tw, th)), (x, y))
            d.text((x + 2, y + 2), n, fill="yellow")
        sh.save(a.neg_sheet, quality=85)
        print("음성 후보", len(negs), a.neg_sheet)
        return
    shutil.rmtree(DS, ignore_errors=True)
    (DS / "images").mkdir(parents=True)
    (DS / "labels").mkdir(parents=True)
    index = {}
    for n, r in labels.items():
        save(r["src"], DS / "images" / f"{n}.jpg")
        (DS / "labels" / f"{n}.txt").write_text(label_line(r) + "\n", encoding="utf-8")
        index[n] = {"setup": r["setup"], "group": r["group"], "kind": r["kind"], "bcd": n in BCD}
    for n in negs:
        save(rows[n]["src"], DS / "images" / f"{n}.jpg")
        (DS / "labels" / f"{n}.txt").write_text("", encoding="utf-8")
        index[n] = {"setup": "neg", "group": "neg", "kind": "frame", "bcd": False}
    (DS / "index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    (DS / "dataset-metadata.json").write_text(json.dumps({"title": "mahjong table points", "id": "jjh7757/mahjong-table-points", "licenses": [{"name": "unknown"}]}, indent=1), encoding="utf-8")
    size = sum(p.stat().st_size for p in DS.rglob("*") if p.is_file())
    print("이미지", len(index), "음성", len(negs), "MB", size // 2**20)


if __name__ == "__main__":
    main()
