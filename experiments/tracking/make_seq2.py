"""장면 D(k16, 격자 initial)로 강·리치봉 추적 시퀀스 프레임을 합성한다(패 없이 노트북에서 흐름 확인용).

  python experiments/tracking/make_seq2.py experiments/field_20261024/kakao_photos/k16.jpg <출력 폴더>

f0 아래 자리 강의 마지막 패를 펠트로 덮음(버리기 전) → f1 손(소매 덩어리가 강 위) → f2 원본(버림) → f3 원본(안정)
→ f4 아래 자리 리치봉 띠에 흰 막대 → f5 같음(안정) → f6 화료(원본 + 막대).
마지막 패는 격자 riverBand(bottom) 안 흰 덩어리 중 가장 아래 줄의 오른쪽 끝(그 사람 기준 마지막 자리)으로 고른다.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

src, out = sys.argv[1], sys.argv[2]
SIDE = sys.argv[sys.argv.index("--side") + 1] if "--side" in sys.argv else "bottom"  # bottom | right
os.makedirs(out, exist_ok=True)
im = Image.open(src).convert("RGB")
W, H = im.size

# GridZones.initial 과 riverBand/stickStrip 계산(0~1000).
x1, x2, y1, y2 = 280, 745, 173, 713
cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
hw, hh = (x2 - x1) / 2, (y2 - y1) / 2
bw, bh = round(hw * 0.6), round(hh * 0.6)
RIVER_START, STICK_START, STICK_END = 0.0, 0.0, 0.25  # grid_zones.dart 의 riverStart·stickStart·stickEnd
if SIDE == "bottom":
    band = (round(cx - bw), round(cy + hh * RIVER_START), round(cx + bw), y2)  # xmin, ymin, xmax, ymax (norm)
    strip = (round(cx - bw), round(cy + hh * STICK_START), round(cx + bw), round(cy + hh * STICK_END))
else:
    band = (round(cx + hw * RIVER_START), round(cy - bh), x2, round(cy + bh))
    strip = (round(cx + hw * STICK_START), round(cy - bh), round(cx + hw * STICK_END), round(cy + bh))


def px(box):
    return (box[0] * W // 1000, box[1] * H // 1000, box[2] * W // 1000, box[3] * H // 1000)


bx0, by0, bx1, by1 = px(band)
hsv = np.asarray(im.convert("HSV"))
white = (hsv[..., 1] < 50) & (hsv[..., 2] > 140)
sub = white[by0:by1, bx0:bx1]
h, w = sub.shape
th = int(0.044 * H)  # 패 긴 변(corner_change.tileFracOf 와 같은 기준), 짧은 변은 × 0.75
tw = int(th * 0.75)
if SIDE == "bottom":
    # 마지막 줄 = 흰 픽셀이 있는 가장 아래 y 에서 패 한 장 높이만큼 위, 마지막 패 = 그 줄의 오른쪽 끝.
    ys = np.nonzero(sub.sum(axis=1) > 0.05 * w)[0]
    if len(ys) == 0:
        raise SystemExit("강 패를 못 찾음")
    ry1 = int(ys.max()) + 1
    ry0 = max(0, ry1 - th)
    xr = int(np.max(np.nonzero(sub[ry0:ry1].sum(axis=0) > 0.3 * th)[0])) + 1
    box = (bx0 + xr - tw - 6, by0 + ry0 - 6, bx0 + xr + 6, by0 + ry1 + 6)
else:
    # 오른쪽 자리: 줄은 세로(기기에서 멀어질수록 오른쪽), 줄 안은 위→아래. 마지막 줄 = 흰 픽셀이 있는 가장 오른쪽 x 에서
    # 패 긴 변만큼 왼쪽, 마지막 패 = 그 줄의 가장 아래.
    xs = np.nonzero(sub.sum(axis=0) > 0.05 * h)[0]
    if len(xs) == 0:
        raise SystemExit("강 패를 못 찾음")
    cx1 = int(xs.max()) + 1
    cx0 = max(0, cx1 - th)
    yb = int(np.max(np.nonzero(sub[:, cx0:cx1].sum(axis=1) > 0.3 * th)[0])) + 1
    box = (bx0 + cx0 - 6, by0 + yb - tw - 6, bx0 + cx1 + 6, by0 + yb + 6)
print(SIDE, "마지막 패 상자(px)", box, "norm", tuple(round(v * 1000 / s) for v, s in zip(box, (W, H, W, H))))

felt = tuple(int(v) for v in np.asarray(im)[by1 - 5, bx0 + 5])
print("felt", felt)

f0 = im.copy()
ImageDraw.Draw(f0).rectangle(box, fill=felt)
f0.save(f"{out}/f0.jpg", quality=92)

f1 = f0.copy()
ImageDraw.Draw(f1).ellipse((box[0] - 200, box[1] - 120, box[2] + 150, box[3] + 300), fill=(214, 176, 146))
f1.save(f"{out}/f1.jpg", quality=92)

im.save(f"{out}/f2.jpg", quality=92)
im.save(f"{out}/f3.jpg", quality=92)

sx0, sy0, sx1, sy1 = px(strip)
f4 = im.copy()
d = ImageDraw.Draw(f4)
if SIDE == "bottom":
    smid = (sy0 + sy1) // 2
    d.rectangle((sx0 + (sx1 - sx0) // 3, smid - 8, sx1 - (sx1 - sx0) // 3, smid + 8), fill=(250, 250, 250))
    d.ellipse(((sx0 + sx1) // 2 - 6, smid - 6, (sx0 + sx1) // 2 + 6, smid + 6), fill=(220, 30, 30))
else:
    smid = (sx0 + sx1) // 2
    d.rectangle((smid - 8, sy0 + (sy1 - sy0) // 3, smid + 8, sy1 - (sy1 - sy0) // 3), fill=(250, 250, 250))
    d.ellipse((smid - 6, (sy0 + sy1) // 2 - 6, smid + 6, (sy0 + sy1) // 2 + 6), fill=(220, 30, 30))
f4.save(f"{out}/f4.jpg", quality=92)
f4.save(f"{out}/f5.jpg", quality=92)
f4.save(f"{out}/f6.jpg", quality=92)
for n in ("f0", "f1", "f2", "f4"):
    Image.open(f"{out}/{n}.jpg").crop((bx0, sy0, bx1, by1)).resize((400, int(400 * (by1 - sy0) / (bx1 - bx0)))).save(
        f"{out}/{n}_river_thumb.jpg", quality=85)
print("ok", W, H, "band", px(band), "strip", (sx0, sy0, sx1, sy1))
