"""동시 론(더블론) 흐름 확인용 합성 사진.

갤러리 장면은 화료자가 한 명씩이라(C 왼쪽 k15, D 아래 k16) 두 손패가 눕혀진 사진이 없다.
격자 판독은 자리 칸을 따로 잘라 읽으므로, 한 사진의 자리 칸에 다른 사진의 **같은 자리** 칸을
크기 맞춰 붙이면 두 자리가 앞면인 사진이 된다(같은 자리끼리라 회전이 맞다).

- CD: D(k16, 아래 화료) 바탕 + C(k15) 왼쪽 칸 → 왼쪽·아래 둘 다 앞면. 격자는 D 것.
- DC: C(k15, 왼쪽 화료) 바탕 + D(k16) 아래 칸 → 격자는 C 것.

기능 확인용이다. B·C·D 정확도 숫자에는 넣지 않는다(합성).
실행: python experiments/multi_ron/compose.py  → photos/CD.jpg, DC.jpg, grids.json
"""
import json
from pathlib import Path

from PIL import Image

HERE = Path(__file__).parent
PHOTOS = HERE.parent / "field_20261024" / "kakao_photos"
OUT = HERE / "photos"

# 장면별 격자(0~1000, grid5_scenes/*/result.json 과 같다)와 화료자 자리.
SCENES = {
    "C": {"photo": "k15.jpg", "grid": {"x1": 320, "x2": 760, "y1": 142, "y2": 717}, "winner": "left"},
    "D": {"photo": "k16.jpg", "grid": {"x1": 280, "x2": 745, "y1": 173, "y2": 713}, "winner": "bottom"},
}


def seat_box(g, side):
    """GridZones.seat 와 같은 자리 칸(0~1000, (y0, x0, y1, x1))."""
    x1, x2, y1, y2 = g["x1"], g["x2"], g["y1"], g["y2"]
    return {
        "bottom": (y2, x1, 1000, 1000),
        "right": (0, x2, y2, 1000),
        "top": (0, 0, y1, x2),
        "left": (y1, 0, 1000, x1),
    }[side]


def px(box, w, h):
    y0, x0, y1, x1 = box
    return (x0 * w // 1000, y0 * h // 1000, x1 * w // 1000, y1 * h // 1000)


def compose(base_key, donor_key):
    base, donor = SCENES[base_key], SCENES[donor_key]
    bim = Image.open(PHOTOS / base["photo"]).convert("RGB")
    dim = Image.open(PHOTOS / donor["photo"]).convert("RGB")
    assert bim.size == dim.size, (bim.size, dim.size)
    w, h = bim.size
    side = donor["winner"]
    src = dim.crop(px(seat_box(donor["grid"], side), w, h))
    dst = px(seat_box(base["grid"], side), w, h)
    patch = src.resize((dst[2] - dst[0], dst[3] - dst[1]), Image.LANCZOS)
    out = bim.copy()
    out.paste(patch, (dst[0], dst[1]))
    return out, {"grid": base["grid"], "winners": sorted([base["winner"], side]), "base": base_key, "donor": donor_key}


def main():
    OUT.mkdir(exist_ok=True)
    grids = {}
    for name, (b, d) in {"CD": ("D", "C"), "DC": ("C", "D")}.items():
        im, meta = compose(b, d)
        im.save(OUT / f"{name}.jpg", quality=92)
        grids[name] = meta
        print(name, meta)
    (OUT / "grids.json").write_text(json.dumps(grids, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
