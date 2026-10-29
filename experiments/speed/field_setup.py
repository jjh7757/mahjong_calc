"""[평가 밖·테스트 세트] 10/24 매장 삼각대 15장에 "자동 맞추기"(서버 `/v2/setup` 프롬프트)를 사진마다 한 번 → 그림 구조 틀
(손패+울기 바깥 띠 선 · 리치봉 상자, 앱 `proposeGrid` 와 같은 규칙 = setup_frames.strips) → read_grid_timing_test 의 FIELD_GRIDS.

  python -I -X utf8 experiments/speed/field_setup.py

테스트 세트는 방법을 다 만든 뒤 한 번만 잰다(규칙을 고치지 않는다, 사용자 2026-10-27). 결과: results/field_setup.json·field_setup.jpg
"""
from __future__ import annotations

import io
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

sys.path.insert(0, str(Path(__file__).parent))
from bench import call  # noqa: E402
from setup_frames import strips  # noqa: E402

from app import observe as ob  # noqa: E402

ROOT = Path(__file__).parent
CAP = ROOT.parent / "field_20261024" / "captures"
OUT = ROOT / "results"
PHOTOS = ["122922", "124007", "125053", "130533", "131210", "132647", "133011", "133620", "134323", "135148",
          "135912", "140302", "140750", "140918", "143443"]


def load(p: str) -> Image.Image:
    return ImageOps.exif_transpose(Image.open(CAP / f"20261024_{p}" / "original.jpg")).convert("RGB")


def one(p: str) -> dict:
    im = load(p)
    small = im.copy()
    small.thumbnail((1568, 1568))
    b = io.BytesIO()
    small.save(b, "JPEG", quality=90)
    c = call(b.getvalue(), ob.SETUP_PROMPT_V2, ob.SETUP_SCHEMA_V2, "gemini-3.8-flash", "low", None)
    if "error" in c:
        return {"photo": p, "s": c["s"], "error": c["error"]}
    st = strips(c["data"])
    return {"photo": p, "s": c["s"], "data": c["data"], "strips": st}


def main() -> None:
    with ThreadPoolExecutor(5) as ex:
        rows = list(ex.map(one, PHOTOS))
    OUT.mkdir(exist_ok=True)
    (OUT / "field_setup.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    grids = []
    tiles = []
    for r in rows:
        st = r.get("strips")
        print(r["photo"], f"{r['s']}초", st["grid"] if st else f"틀 못 냄 {r.get('error', '')[:80]}", st["sticks"] if st else "")
        if st:
            grids.append(r["photo"] + "=" + ",".join(map(str, list(st["grid"]) + st["sticks"])))
        im = load(r["photo"])
        im.thumbnail((560, 560))
        w, h = im.size
        d = ImageDraw.Draw(im)
        if st:
            x1, x2, y1, y2 = [v / 1000 for v in st["grid"]]
            for a, bb in [((x1 * w, y1 * h), (x1 * w, h)), ((x2 * w, 0), (x2 * w, y2 * h)),
                          ((0, y1 * h), (x2 * w, y1 * h)), ((x1 * w, y2 * h), (w, y2 * h))]:
                d.line([a, bb], fill=(0, 230, 255), width=3)
            s = st["sticks"]
            d.rectangle((s[1] * w / 1000, s[0] * h / 1000, s[3] * w / 1000, s[2] * h / 1000), outline=(255, 40, 40), width=3)
        for side in (r.get("data") or {}).get("seats") or []:
            hb = side.get("hand")
            if hb and len(hb) == 4:
                d.rectangle((hb[1] * w / 1000, hb[0] * h / 1000, hb[3] * w / 1000, hb[2] * h / 1000), outline=(255, 230, 0), width=2)
        d.text((6, 6), r["photo"] + ("" if st else " (틀 못 냄)"), fill=(255, 255, 0))
        tiles.append(im)
    tw, th = max(t.width for t in tiles), max(t.height for t in tiles)
    canvas = Image.new("RGB", (tw * 5, th * 3), "white")
    for i, t in enumerate(tiles):
        canvas.paste(t, ((i % 5) * tw, (i // 5) * th))
    canvas.save(OUT / "field_setup.jpg", quality=85)
    print(f"틀 나옴 {sum(bool(r.get('strips')) for r in rows)}/{len(rows)}")
    print("FIELD_GRIDS=" + ";".join(grids))


if __name__ == "__main__":
    main()
