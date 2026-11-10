"""리치 화료인데 뒷도라를 안 뒤집고 찍은 사진(124654·130743·132239) → 매장 습관대로 '표시패를 패산에서 빼서 뒷도라와 함께 화료자 쪽 펠트에 짝으로'(2026-11-08 사용자).
패산 표시패 자리는 바로 옆 뒷면 묶음 윗면으로 덮고, 표시패 조각 + 뒷도라(같은 사진 강의 패, 다음 패가 손패에 없어 뒷도라 0판) 조각을 화료자 손패 안쪽에 나란히 붙인다.
짝 자리는 같은 날 실제 리치 화료(172424·183627 오른쪽 자리, 143104 아래 자리)의 짝 위치를 본떠 정함.
  python -I -X utf8 experiments/tile_classifier/role_v2_pair_synth.py → data/role/v2/images/<시각>_after.jpg"""
from pathlib import Path
import cv2, numpy as np
HERE = Path(__file__).resolve().parent
CAP = HERE.parent / "visit_20261031" / "captures"
OUT = HERE / "data" / "role" / "v2" / "images"
# 이름: (표시패 상자, 덮을 뒷면 묶음 좌상단, 뒷도라 출처 상자, 회전(None/ccw), 짝 상자 둘[x,y,w,h])
JOBS = {
    "20261031_124654": ([943, 1732, 119, 83], (943, 1645), [1623, 1191, 119, 87], None, [[2622, 762, 122, 88], [2624, 853, 122, 88]]),
    "20261031_132239": ([1660, 394, 96, 121], (1563, 394), [1936, 1150, 89, 114], "ccw", [[2522, 835, 124, 90], [2525, 928, 124, 90]]),
    "20261031_130743": ([2846, 378, 93, 104], (2747, 378), [2386, 2539, 96, 120], None, [[2955, 2160, 98, 126], [3056, 2163, 98, 126]]),
}


def paste(dst, src, x, y, feather=1.2):
    h, w = src.shape[:2]
    m = np.zeros((h, w), np.float32); m[2:-2, 2:-2] = 1; m = cv2.GaussianBlur(m, (0, 0), feather)[..., None]
    reg = dst[y:y + h, x:x + w].astype(np.float32)
    dst[y:y + h, x:x + w] = (src.astype(np.float32) * m + reg * (1 - m)).astype(np.uint8)


for name, (ind, back_xy, ura, rot, pairs) in JOBS.items():
    im = cv2.imread(str(CAP / name / "original.jpg")); o = im.copy()
    x, y, w, h = ind
    ind_crop = im[y:y + h, x:x + w].copy()
    bx, by = back_xy
    paste(o, im[by:by + h, bx:bx + w].copy(), x, y)  # 표시패 자리 → 옆 뒷면 묶음 윗면
    ux, uy, uw, uh = ura
    ura_crop = im[uy:uy + uh, ux:ux + uw].copy()
    for crop, (px, py, pw, ph) in zip((ind_crop, ura_crop), pairs):
        c = cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE) if rot == "ccw" else crop
        c = cv2.resize(c, (pw, ph), interpolation=cv2.INTER_AREA)
        # 펠트 위 낱장 그림자: 아래·오른쪽으로 살짝 어둡게
        sh = o[py + 4:py + ph + 6, px + 3:px + pw + 5].astype(np.float32) * 0.75
        o[py + 4:py + ph + 6, px + 3:px + pw + 5] = sh.astype(np.uint8)
        paste(o, c, px, py)
    cv2.imwrite(str(OUT / f"{name[-6:]}_after.jpg"), o, [cv2.IMWRITE_JPEG_QUALITY, 95])
    print(name, "표시패", ind, "→ 짝", pairs)
