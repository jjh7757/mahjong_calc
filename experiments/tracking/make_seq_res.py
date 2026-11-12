"""실제 11-07 원본 한 장으로 "버림 전 → 버림 → 리치봉" 시퀀스를 합성해 해상도 셋(1020 건너뛰기·2040 2×2 평균·4080)으로 쓴다.
판 상태 추적 입력을 2040 으로 바꾼 것(받기 켬)과 해상도가 판 중간에 바뀌는 경우를 replay_res.dart 로 확인하려고(2026-11-12).

  python -I experiments/tracking/make_seq_res.py <원본.jpg> <grid json 문자열 또는 파일> <출력 폴더> [river_side=bottom] [stick_side=top]

f0·f1 = 리치봉을 지우고(홈 색으로) river_side 강의 마지막 패를 펠트로 덮음 → f2·f3 = 패 놓임(버림) → f4~f6 = 원본(리치봉 꽂힘).
"""
import json, os, sys
import numpy as np
from PIL import Image, ImageDraw

src, gridarg, out = sys.argv[1], sys.argv[2], sys.argv[3]
RSIDE = sys.argv[4] if len(sys.argv) > 4 else "bottom"
SSIDE = sys.argv[5] if len(sys.argv) > 5 else "top"
g = json.load(open(gridarg)) if os.path.exists(gridarg) else json.loads(gridarg)
os.makedirs(out, exist_ok=True)
im = Image.open(src).convert("RGB"); a = np.asarray(im).copy(); H, W, _ = a.shape
x1, x2, y1, y2 = g["x1"], g["x2"], g["y1"], g["y2"]
cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
hw, hh = round((x2 - x1) * 0.6 / 2), round((y2 - y1) * 0.6 / 2)
assert RSIDE == "bottom"
band = (cx - hw, cy, cx + hw, y2)  # xmin,ymin,xmax,ymax (0~1000)
bx0, by0, bx1, by1 = band[0] * W // 1000, band[1] * H // 1000, band[2] * W // 1000, band[3] * H // 1000
hsv = np.asarray(im.convert("HSV")).astype(int)
white = (hsv[..., 1] < 50) & (hsv[..., 2] > 140)
sub = white[by0:by1, bx0:bx1]; h, w = sub.shape
th = int(0.044 * H); tw = int(th * 0.75)
ys = np.nonzero(sub.sum(axis=1) > 0.05 * w)[0]
ry1 = int(ys.max()) + 1; ry0 = max(0, ry1 - th)
xr = int(np.max(np.nonzero(sub[ry0:ry1].sum(axis=0) > 0.3 * th)[0])) + 1
tile = (bx0 + xr - tw - 6, by0 + ry0 - 6, bx0 + xr + 6, by0 + ry1 + 6)
felt = tuple(int(v) for v in np.median(a[by1 - 40:by1 - 5, bx0 + 5:bx0 + 60].reshape(-1, 3), axis=0))
print("마지막 패(px)", tile, "펠트", felt)

# 리치봉 지우기: sticks 상자에서 stick_side 쪽 30% 띠 안의 진한 색(채도·명도 높음, 초록 제외) 화소를 홈 색으로.
sy0, sx0, sy1, sx1 = g["sticks"]
bwid, bhei = sx1 - sx0, sy1 - sy0
strip = {"top": (sx0, sy0, sx1, sy0 + round(bhei * 0.3)), "bottom": (sx0, sy1 - round(bhei * 0.3), sx1, sy1),
         "left": (sx0, sy0, sx0 + round(bwid * 0.3), sy1), "right": (sx1 - round(bwid * 0.3), sy0, sx1, sy1)}[SSIDE]
px0, py0, px1, py1 = strip[0] * W // 1000, strip[1] * H // 1000, strip[2] * W // 1000, strip[3] * H // 1000
reg = hsv[py0:py1, px0:px1]
hue = reg[..., 0] * 360 / 255
col = (reg[..., 1] > 0.45 * 255) & (reg[..., 2] > 0.25 * 255) & ~((hue > 80) & (hue < 170))
# 봉은 길쭉한 큰 덩어리 — 작은 버튼(빨강)까지 지우지 않게 파랑·노랑만.
col &= ((hue > 190) & (hue < 260)) | ((hue > 35) & (hue < 70))
# 가장 큰 덩어리 하나만(위 패의 파란 무늬·파란 버튼까지 지우지 않게).
from scipy import ndimage
lab, n = ndimage.label(col)
sizes = ndimage.sum(col, lab, range(1, n + 1))
col = lab == (int(np.argmax(sizes)) + 1)
ys2, xs2 = np.nonzero(col)
print("봉 화소", len(ys2), "덩어리", n)
sb = (px0 + xs2.min() - 12, py0 + ys2.min() - 12, px0 + xs2.max() + 12, py0 + ys2.max() + 12)
dark = a[py0:py1, px0:px1][~col & (reg[..., 2] < 90)]
devc = tuple(int(v) for v in np.median(dark.reshape(-1, 3), axis=0))
print("봉 상자(px)", sb, "홈 색", devc)

nostick = Image.fromarray(a.copy()); ImageDraw.Draw(nostick).rectangle(sb, fill=devc)
before = nostick.copy(); ImageDraw.Draw(before).rectangle(tile, fill=felt)
frames = [before, before, nostick, nostick, im, im, im]


def save(img, name):
    arr = np.asarray(img)
    img.save(f"{out}/{name}_4080.jpg", quality=75)
    hh2, ww2 = arr.shape[0] // 2 * 2, arr.shape[1] // 2 * 2
    avg = arr[:hh2, :ww2].reshape(hh2 // 2, 2, ww2 // 2, 2, 3).mean(axis=(1, 3)).round().astype(np.uint8)
    Image.fromarray(avg).save(f"{out}/{name}_2040.jpg", quality=85)
    Image.fromarray(arr[::4, ::4]).save(f"{out}/{name}_1020.jpg", quality=75)


for i, f in enumerate(frames):
    save(f, f"f{i}")
json.dump(g, open(f"{out}/grid.json", "w"))
