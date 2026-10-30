"""화료자 자신의 강에서 눕힌 패를 찾는지 잰다(`last3` 묶음엔 화료자 강이 없다). Gemini 호출 없음.

사진을 `lastZone`(lib/table/grid_zones.dart)대로 잘라 그 사람 쪽이 아래로 오게 세운 뒤 RiverLocator 로 본다.
사용: python river_sideways_winner.py <mahjong-recognizer 경로> <kakao_photos 폴더> <크롭 저장 폴더>
"""
import io
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, sys.argv[1])
from app.river import RiverLocator  # noqa: E402

photos, out = Path(sys.argv[2]), Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
loc = RiverLocator()


def last_zone(g, side, band=0.6):
    x1, x2, y1, y2 = g
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    hw, hh = round((x2 - x1) * band / 2), round((y2 - y1) * band / 2)
    return {
        "bottom": (cx - hw, cy, cx + hw, y2),
        "top": (cx - hw, y1, cx + hw, cy),
        "left": (x1, cy - hh, cx, cy + hh),
        "right": (cx, cy - hh, x2, cy + hh),
    }[side]


# 그 사람 쪽을 사진 아래로 돌리는 반시계 각도.
TURN = {"bottom": 0, "right": 270, "top": 180, "left": 90}


def read(photo, grid, side):
    im = Image.open(photos / f"{photo}.jpg").convert("RGB")
    x0, y0, x1, y1 = last_zone(grid, side)
    w, h = im.size
    c = im.crop((x0 * w // 1000, y0 * h // 1000, x1 * w // 1000, y1 * h // 1000)).rotate(TURN[side], expand=True)
    c.save(out / f"{photo}_{side}.jpg", quality=92)
    buf = io.BytesIO()
    c.save(buf, "JPEG", quality=92)
    f, _ = loc.locate(buf.getvalue())
    if f is None:
        return "틀 못 잡음"
    return f"{f.count}장 줄 {[len(r) for r in f.rows]} 눕힘 {[i for i, s in enumerate(f.sideways) if s]}"


for spec in sys.argv[4:]:
    # 형식: 사진:x1,x2,y1,y2:자리
    photo, g, side = spec.split(":")
    grid = tuple(int(v) for v in g.split(","))
    print(photo, side, read(photo, grid, side))
