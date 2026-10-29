"""펴기 전·후 자리 크롭(tool/rect_crops_test.dart 결과)에서 서버 자리 틀이 잡은 패 크기(손패 패 폭·높이 중앙, px)와 틀 결과.

  python -I -X utf8 experiments/rectify/tile_size.py
"""
import io
import statistics
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, "C:/Users/jjh7757/dev/mahjong-recognizer")
from app import river as rv  # noqa: E402
from app import seat  # noqa: E402

D = Path(__file__).parent / "results" / "crops"
det = rv.TileDetector(conf=0.04)
for photo in ["k15", "k26", "k12", "k16"]:
    for tag in ["plain", "rect"]:
        jpeg = (D / f"{photo}_{tag}_seat.jpg").read_bytes()
        rgb = np.asarray(Image.open(io.BytesIO(jpeg)).convert("RGB"))
        fr = seat.frame(rgb, det)
        if fr is None:
            print(f"{photo} {tag:5s} 틀 없음 ({rgb.shape[1]}x{rgb.shape[0]})")
            continue
        tw = statistics.median(x[2] for x in fr.hand)
        th = statistics.median(x[3] for x in fr.hand)
        melds = [[(x[2], x[3]) for x in m] for m in fr.melds]
        print(f"{photo} {tag:5s} 손패 패 {tw:.0f}x{th:.0f}px  울기 상자 {melds}  틀 {fr.summary()}")

# 틀을 못 잡은 것: 검출 상자·구조·검사 단계별로
for photo in ["k12", "k16"]:
    jpeg = (D / f"{photo}_rect_seat.jpg").read_bytes()
    rgb = np.asarray(Image.open(io.BytesIO(jpeg)).convert("RGB"))
    white = rv.white_mask(rgb)
    got = seat.mosaic(det, rgb, white)
    if got is None:
        print(f"{photo} rect 띠 못 찾음")
        continue
    boxes = [x for x in got[0] if seat.ink(rgb, x) >= seat.INK_MIN]
    fr = seat.structure(rgb, boxes, white)
    print(f"{photo} rect 상자 {len(boxes)} 구조 {fr.summary() if fr else None} 손패 패 "
          f"{statistics.median(x[2] for x in fr.hand):.0f}x{statistics.median(x[3] for x in fr.hand):.0f} "
          f"장수 {seat.valid(fr)} 모양 {seat.strict_ok(fr)} 안전 {seat.safe_ok(fr, rgb)} 띠 {got[1]}")
    print("   손패 상자", [(x[0], x[1], x[2], x[3]) for x in fr.hand])
    print("   나머지", [[(x[0], x[1], x[2], x[3]) for x in m] for m in fr.melds], fr.loose)
