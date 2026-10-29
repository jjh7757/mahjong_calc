"""작탁 기울기만큼 사진을 돌려 탁자를 반듯하게 세운 뒤 "자동 맞추기"(서버 `/v2/setup` 프롬프트) → 그림 구조 틀(setup_frames.strips).
사용자 제안(2026-10-29): 수직 격자를 그대로 쓰지 말고 작탁 기울기를 확인해 이미지를 돌린 뒤 격자로 나눈다(원근은 펴지 않음).

  python -I -X utf8 experiments/speed/tilt_setup.py [--set tilt|field|bcd] [--runs 1]

기울기 = tool/tilt_check_test.dart 가 펠트 네 변으로 잰 값(experiments/rectify/results/tilt.json). |기울기| < MIN_TILT 이면 돌리지 않는다.
사진은 시계 반대로 기울기만큼 돌린다(PIL rotate 는 양수가 반시계, 기울기는 시계 +), 빈 곳은 회색. 결과: results/tilt_setup_<묶음>.json·jpg
"""
from __future__ import annotations

import argparse
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
FIELD = ROOT.parent / "field_20261024"
OUT = ROOT / "results"
TILT = json.loads((ROOT.parent / "rectify" / "results" / "tilt.json").read_text(encoding="utf-8"))
MIN_TILT = 3.0
SETS = {
    "bcd": {p: FIELD / "kakao_photos" / f"{p}.jpg" for p in ["k25", "k28", "k15", "k26", "k12", "k16"]},
    "tilt": {f"tilted/{p}_{v}": FIELD / "kakao_photos" / "tilted" / f"{p}_{v}.jpg"
             for p in ["k25", "k28", "k15", "k26", "k12", "k16"] for v in "abc"},
    "field": {p: FIELD / "captures" / f"20261024_{p}" / "original.jpg"
              for p in ["122922", "124007", "125053", "130533", "131210", "132647", "133011", "133620", "134323", "135148",
                        "135912", "140302", "140750", "140918", "143443"]},
}


def level(path: Path, key: str) -> tuple[Image.Image, float]:
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    t = TILT.get(key) or 0.0
    if abs(t) < MIN_TILT:
        return im, 0.0
    return im.rotate(t, resample=Image.BICUBIC, expand=True, fillcolor=(90, 90, 90)), t


def one(key: str, run: int, im: Image.Image) -> dict:
    small = im.copy()
    small.thumbnail((1568, 1568))
    b = io.BytesIO()
    small.save(b, "JPEG", quality=90)
    c = call(b.getvalue(), ob.SETUP_PROMPT_V2, ob.SETUP_SCHEMA_V2, "gemini-3.8-flash", "low", None)
    if "error" in c:
        return {"photo": key, "run": run, "s": c["s"], "error": c["error"]}
    return {"photo": key, "run": run, "s": c["s"], "data": c["data"], "strips": strips(c["data"])}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="field")
    ap.add_argument("--runs", type=int, default=1)
    a = ap.parse_args()
    ims = {}
    tilts = {}
    for k, path in SETS[a.set].items():
        ims[k], tilts[k] = level(path, k)
    jobs = [(k, r) for r in range(1, a.runs + 1) for k in ims]
    with ThreadPoolExecutor(6) as ex:
        rows = list(ex.map(lambda j: one(j[0], j[1], ims[j[0]]), jobs))
    for r in rows:
        r["tilt"] = round(tilts[r["photo"]], 1)
    OUT.mkdir(exist_ok=True)
    (OUT / f"tilt_setup_{a.set}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    tiles = []
    for k, im in ims.items():
        t = im.copy()
        t.thumbnail((520, 520))
        w, h = t.size
        d = ImageDraw.Draw(t)
        r = next((x for x in rows if x["photo"] == k), {})
        st = r.get("strips")
        for side in (r.get("data") or {}).get("seats") or []:
            hb = side.get("hand")
            if hb and len(hb) == 4:
                d.rectangle((hb[1] * w / 1000, hb[0] * h / 1000, hb[3] * w / 1000, hb[2] * h / 1000), outline=(255, 230, 0), width=2)
        if st:
            x1, x2, y1, y2 = [v / 1000 for v in st["grid"]]
            for p0, p1 in [((x1 * w, y1 * h), (x1 * w, h)), ((x2 * w, 0), (x2 * w, y2 * h)),
                           ((0, y1 * h), (x2 * w, y1 * h)), ((x1 * w, y2 * h), (w, y2 * h))]:
                d.line([p0, p1], fill=(0, 230, 255), width=3)
            s = st["sticks"]
            d.rectangle((s[1] * w / 1000, s[0] * h / 1000, s[3] * w / 1000, s[2] * h / 1000), outline=(255, 40, 40), width=3)
        d.rectangle((0, 0, 260, 18), fill=(0, 0, 0))
        d.text((4, 3), f"{k} {tilts[k]:+.1f}° {'O' if st else 'x'}", fill=(255, 255, 0))
        tiles.append(t)
    cols = 6 if len(tiles) > 10 else 3
    tw, th = max(x.width for x in tiles), max(x.height for x in tiles)
    canvas = Image.new("RGB", (tw * cols, th * ((len(tiles) + cols - 1) // cols)), "white")
    for i, x in enumerate(tiles):
        canvas.paste(x, ((i % cols) * tw, (i // cols) * th))
    canvas.save(OUT / f"tilt_setup_{a.set}.jpg", quality=85)
    ok = [r for r in rows if r.get("strips")]
    s = sorted(r["s"] for r in rows if "s" in r)
    print(f"{a.set}: 틀 나옴 {len(ok)}/{len(rows)}, 오류 {sum('error' in r for r in rows)} | {s[len(s) // 2]:.1f}/{s[int(0.9 * (len(s) - 1))]:.1f}/{s[-1]:.1f}초")
    print("FIELD_GRIDS=" + ";".join(r["photo"].split("/")[-1] + "=" + ",".join(map(str, list(r["strips"]["grid"]) + r["strips"]["sticks"]))
                                    for r in rows if r.get("strips") and r["run"] == 1))


if __name__ == "__main__":
    main()
