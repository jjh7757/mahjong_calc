"""0단계 정답 확인 그림(2026-11-16): role_pair_scenes.json 의 user_check 장면마다 전체 + 표시패 주변 확대, 번호·읽은 패 표시.
상자는 사람이 사진을 보고 잡은 위치(labels_v2 의 pair 상자 또는 눈 위치) — 모델 출력 아님.
  python -X utf8 experiments/tile_classifier/role_pair_scenes_draw.py   → data/user_check_1116/pair_scenes/<장면>.jpg
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "experiments" / "speed"))
import seat_grow as sg  # noqa: E402

OUT = HERE / "data" / "user_check_1116" / "pair_scenes"
# 장면 → [(x, y, w, h 픽셀, 번호 글, 읽은 패)], 확대 범위(x0, y0, x1, y1 픽셀)
MARKS = {
    "k15": ([(870, 1860, 130, 105, "1", "7m"), (856, 1965, 140, 110, "2", "6s")], (700, 1500, 1800, 2250)),
    "k26": ([(850, 1866, 130, 100, "1", "7m"), (840, 1966, 140, 104, "2", "6s")], (680, 1500, 1800, 2250)),
    "20261107_122315": ([(1890, 2390, 94, 114, "1", "7s"), (1976, 2386, 95, 117, "2", "2s")], (1600, 2150, 2350, 2700)),
    "20261107_153029": ([(1553, 1748, 108, 129, "1", "8p"), (1597, 1834, 64, 114, "2", "6z")], (1250, 1500, 1950, 2100)),
    "20261031_133826": ([(1058, 2136, 124, 107, "1", "8m"), (1051, 2229, 126, 101, "2", "8p (고정 정답은 4p)")], (850, 1950, 1450, 2450)),
    "20261107_153939": ([(2657, 1903, 123, 130, "1", "6s"), (2746, 1939, 110, 123, "2", "7m"), (2990, 2250, 85, 170, "3", "? 기운 패")], (2450, 1750, 3350, 2500)),
}

# 정답 고정(11:13) 뒤, 채점 결과의 틀린 장면을 보다가 다시 확대해 발견한 것 — 고정 파일은 고치지 않고 그림·보고로만 알린다.
LATE = {"20261031_133826": "고정 정답 [8m, 4p] 는 label.json 을 그대로 옮긴 것. 다시 확대하니 2번은 8통(4개 × 2줄) — 고정 뒤 발견이라 파일은 안 고침"}


def font(n: int):
    for f in ("malgun.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(f, n)
        except OSError:
            continue
    return ImageFont.load_default()


def main() -> None:
    data = json.loads((HERE / "role_pair_scenes.json").read_text(encoding="utf-8"))
    rows = {r["name"]: r for r in data["scenes"]}
    paths = {s["name"]: s["path"] for s in sg.eval_scenes()}
    OUT.mkdir(parents=True, exist_ok=True)
    for name in data["user_check"] + [n for n in LATE if n not in data["user_check"]]:
        marks, (x0, y0, x1, y1) = MARKS[name]
        r = dict(rows[name])
        if name in LATE:
            r["user_check"] = LATE[name]
        im = ImageOps.exif_transpose(Image.open(paths[name])).convert("RGB")
        full = im.copy()
        d = ImageDraw.Draw(full)
        d.rectangle((x0, y0, x1, y1), outline=(255, 255, 0), width=14)
        full.thumbnail((1400, 1400))
        crop = im.crop((x0, y0, x1, y1))
        dc = ImageDraw.Draw(crop)
        f = font(max(28, (x1 - x0) // 22))
        for x, y, w, h, num, tile in marks:
            bx = (x - x0, y - y0, x - x0 + w, y - y0 + h)
            dc.rectangle(bx, outline=(255, 40, 40), width=5)
            dc.text((bx[2] + 8, bx[1]), f"{num}: {tile}", fill=(255, 255, 0), font=f, stroke_width=3, stroke_fill=(0, 0, 0))
        crop.thumbnail((1400, 1400))
        H = full.height + crop.height + 150
        sheet = Image.new("RGB", (max(full.width, crop.width), H), (255, 255, 255))
        ds = ImageDraw.Draw(sheet)
        fs = font(24)
        ds.text((10, 8), f"{name}  화료자 {r['winner']}  리치 {r['riichi']}  저장 정답 {r['stored']} ({r['stored_src']})", fill=(0, 0, 0), font=fs)
        ds.text((10, 40), f"사진대로 적은 정답: 탁자 위 짝 {r['table_pair']}  패산 위 {r['wall']}  → {r['eval']}", fill=(180, 0, 0), font=fs)
        ds.text((10, 72), f"확인할 것: {r['user_check']}", fill=(0, 0, 160), font=fs)
        sheet.paste(full, (0, 110))
        sheet.paste(crop, (0, 120 + full.height))
        p = OUT / f"{name}.jpg"
        sheet.save(p, quality=88)
        print(p)


if __name__ == "__main__":
    main()
