"""리치봉 홈 판정을 색과 무관하게(파랑·노랑·빨강 봉) — Gemini 없이 픽셀만. 2026-11-10.

매장 리치봉은 파란 막대지만 모자라면 노랑·빨강 봉으로 대신 꽂는다(사용자 11-10). 그래서 색상(hue)이 아니라
"진한 색(채도 높음)의 가늘고 긴 덩어리가 기기 가장자리에 홈 방향으로 누워 있나" 로 본다.
  - 마스크: 채도 S ≥ s_min, 밝기 V ≥ v_min, 펠트 초록(hue 70~170°)은 뺌.
  - 덩어리: 연결 성분, 길이 ≥ 크롭 변의 len_min, 길이/두께 ≥ ratio_min.
  - 자리: 가로로 길면 위/아래(중심 y), 세로로 길면 왼/오른(중심 x). 가장자리 edge 안쪽에 있어야.
버튼(빨강·파랑 마름모·분홍), 주사위 점, LED 는 짧아서 빠진다.

정답 대용 = 같은 크롭의 Gemini `/v2/sticks` 답(captures/*_track/sticks_###.json). 노랑·빨강은 파란 화소의 색상만 돌린 합성.

  python -I experiments/tracking/stick_color_free.py [--dump 틀린 장면 그림 폴더]
"""
import argparse
import colorsys
import glob
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'visit_20261107', 'captures')
SIDES = ['bottom', 'right', 'top', 'left']


def hsv(arr):
    a = arr.astype(np.float32) / 255.0
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(-1), a.min(-1)
    d = mx - mn
    s = np.where(mx > 0, d / np.maximum(mx, 1e-6), 0)
    h = np.zeros_like(mx)
    m = d > 1e-6
    rc = np.where(m & (mx == r), ((g - b) / np.maximum(d, 1e-6)) % 6, 0)
    gc = np.where(m & (mx == g) & (mx != r), (b - r) / np.maximum(d, 1e-6) + 2, 0)
    bc = np.where(m & (mx == b) & (mx != r) & (mx != g), (r - g) / np.maximum(d, 1e-6) + 4, 0)
    h = (rc + gc + bc) * 60.0
    return h, s, mx


def recolor(arr, hue_to):
    """파란 화소(hue 190~260°, 채도 0.35 이상)의 색상만 hue_to 로 돌린다. 채도·밝기는 그대로."""
    h, s, v = hsv(arr)
    m = (h >= 190) & (h <= 260) & (s >= 0.35)
    out = arr.copy()
    ys, xs = np.nonzero(m)
    for y, x in zip(ys, xs):
        r, g, b = colorsys.hsv_to_rgb(hue_to / 360.0, float(s[y, x]), float(v[y, x]))
        out[y, x] = (int(r * 255), int(g * 255), int(b * 255))
    return out


def detect(arr, s_min=0.45, v_min=0.25, len_min=0.25, ratio_min=4.0, edge=0.30, debug=False):
    H, W = arr.shape[:2]
    h, s, v = hsv(arr)
    felt = (h >= 70) & (h <= 170)
    mask = (s >= s_min) & (v >= v_min) & ~felt
    mask = ndimage.binary_opening(mask, iterations=1)
    mask = ndimage.binary_closing(mask, iterations=2)
    lab, n = ndimage.label(mask)
    found = {k: False for k in SIDES}
    comps = []
    for i, sl in enumerate(ndimage.find_objects(lab), start=1):
        if sl is None:
            continue
        ys, xs = sl
        hh, ww = ys.stop - ys.start, xs.stop - xs.start
        cy, cx = (ys.start + ys.stop) / 2 / H, (xs.start + xs.stop) / 2 / W
        if ww >= hh:
            ok = ww >= len_min * W and ww / max(hh, 1) >= ratio_min
            side = ('top' if cy < edge else 'bottom' if cy > 1 - edge else None)
        else:
            ok = hh >= len_min * H and hh / max(ww, 1) >= ratio_min
            side = ('left' if cx < edge else 'right' if cx > 1 - edge else None)
        if debug and (ww > 0.1 * W or hh > 0.1 * H):
            comps.append((side, ww, hh, round(cx, 2), round(cy, 2), ok))
        if ok and side:
            found[side] = True
    return (found, comps) if debug else found


def load():
    out = []
    for js in sorted(glob.glob(os.path.join(ROOT, '*_track', 'sticks_*.json'))):
        jpg = js[:-5] + '.jpg'
        if not os.path.exists(jpg):
            continue
        r = json.load(open(js, encoding='utf-8'))['read']['riichi_sticks']
        out.append((os.path.relpath(jpg, ROOT), {k: bool(r.get(k)) for k in SIDES}))
    return out


def score(items, variant, params, dump=None):
    seat_ok = seat_n = pos_ok = pos_n = neg_ok = neg_n = img_ok = 0
    bad = []
    for path, truth in items:
        arr = np.array(Image.open(os.path.join(ROOT, path)).convert('RGB'))
        if variant == 'yellow':
            arr = recolor(arr, 50)
        elif variant == 'red':
            arr = recolor(arr, 0)
        got = detect(arr, **params)
        all_ok = True
        for k in SIDES:
            seat_n += 1
            if truth[k]:
                pos_n += 1
                pos_ok += got[k]
            else:
                neg_n += 1
                neg_ok += not got[k]
            if got[k] != truth[k]:
                all_ok = False
        seat_ok += sum(got[k] == truth[k] for k in SIDES)
        img_ok += all_ok
        if not all_ok:
            bad.append((path, [k for k in SIDES if truth[k]], [k for k in SIDES if got[k]]))
            if dump:
                os.makedirs(dump, exist_ok=True)
                Image.fromarray(arr).save(os.path.join(dump, f"{variant}_{path.replace(os.sep, '_')}"))
    return dict(variant=variant, images=f'{img_ok}/{len(items)}', seats=f'{seat_ok}/{seat_n}',
                stick=f'{pos_ok}/{pos_n}', empty=f'{neg_ok}/{neg_n}', bad=bad)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dump')
    ap.add_argument('--variants', default='blue,yellow,red')
    ap.add_argument('--s_min', type=float, default=0.45)
    ap.add_argument('--len_min', type=float, default=0.25)
    ap.add_argument('--ratio_min', type=float, default=4.0)
    a = ap.parse_args()
    params = dict(s_min=a.s_min, len_min=a.len_min, ratio_min=a.ratio_min)
    items = load()
    print(f'크롭 {len(items)}장, 봉 있는 자리 {sum(sum(t.values()) for _, t in items)}', params)
    for v in a.variants.split(','):
        r = score(items, v, params, a.dump)
        print(f"{v:6s} 크롭 통째 {r['images']} · 자리 {r['seats']} · 봉 있음 {r['stick']} · 봉 없음 {r['empty']}")
        for b in r['bad'][:15]:
            print('   ', b)
    sys.stdout.flush()


if __name__ == '__main__':
    main()
