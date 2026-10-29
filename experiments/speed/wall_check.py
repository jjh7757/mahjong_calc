"""서버 `/v2/wall` 프롬프트(판 시작 전용, observe.WALL_PROMPT_V2)로 가진 사진 전부에서 왕패 상자를 찾아 그려 본다.

  python -I -X utf8 experiments/speed/wall_check.py [--runs 2]

사진: B·C·D(개발, 정답 상자 = dora_locate.TRUTH), A·E 4장(참고), 10/24 매장 카메라 헤드 28장(평가 밖·테스트 세트 포함 —
한 번만 재고 프롬프트를 고치지 않는다). 가진 사진은 모두 판 끝(화료) 장면이라 판 시작 장면은 없다.
결과: results/wall_check.json, results/wall_check_<묶음>.jpg (초록 = 정답, 빨강/주황 = 회차별 찾은 상자).
"""
from __future__ import annotations

import argparse
import io
import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

sys.path.insert(0, str(Path(__file__).parent))
from bench import call  # noqa: E402
from dora_locate import TRUTH, area, inter  # noqa: E402

from app import observe as ob  # noqa: E402

ROOT = Path(__file__).parent
FIELD = ROOT.parent / "field_20261024"
OUT = ROOT / "results"

SETS = {
    "bcd": {p: FIELD / "kakao_photos" / f"{p}.jpg" for p in ["k25", "k28", "k15", "k26", "k12", "k16"]},
    "ae": {p: FIELD / "kakao_photos" / f"{p}.jpg" for p in ["k20", "k24", "k00", "k04"]},
    "field": {d.name[9:]: d / "original.jpg" for d in sorted((FIELD / "captures").iterdir()) if (d / "original.jpg").exists()},
}
COLORS = [(255, 60, 60), (255, 170, 0), (200, 0, 255)]


def load(path: Path) -> Image.Image:
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


def jpeg(im: Image.Image, side: int = 1568) -> bytes:
    im = im.copy()
    im.thumbnail((side, side))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=90)
    return b.getvalue()


def one(name: str, run: int, data: bytes) -> dict:
    c = call(data, ob.WALL_PROMPT_V2, ob.WALL_SCHEMA_V2, "gemini-3.8-flash", "low", None)
    row = {"photo": name, "run": run, "s": c["s"], "think": c.get("think")}
    if "error" in c:
        return {**row, "error": c["error"]}
    w = ob.normalize_wall_v2(c["data"])
    row.update(found=w["found"], box=w["box"], side=w["side"], notes=w["notes"][:160])
    if w["box"] and name in TRUTH:
        t, b = TRUTH[name], w["box"]
        i = inter(b, t)
        row.update(iou=round(i / (area(b) + area(t) - i), 2), cover=round(i / area(t), 2))
    return row


def sheet(name: str, ims: dict[str, Image.Image], rows: list[dict]) -> Path:
    tiles = []
    for p, im in ims.items():
        t = im.copy()
        t.thumbnail((640, 640))
        w, h = t.size
        d = ImageDraw.Draw(t)
        if p in TRUTH:
            y0, x0, y1, x1 = TRUTH[p]
            d.rectangle((x0 * w / 1000, y0 * h / 1000, x1 * w / 1000, y1 * h / 1000), outline=(0, 255, 0), width=4)
        for r in rows:
            if r["photo"] == p and r.get("box"):
                y0, x0, y1, x1 = r["box"]
                d.rectangle((x0 * w / 1000, y0 * h / 1000, x1 * w / 1000, y1 * h / 1000), outline=COLORS[(r["run"] - 1) % 3], width=3)
        found = "".join("O" if r.get("found") else "x" for r in rows if r["photo"] == p)
        d.rectangle((0, 0, 170, 24), fill=(0, 0, 0))
        d.text((6, 5), f"{p} {found}", fill=(255, 255, 0))
        tiles.append(t)
    cols = 4
    tw = max(t.width for t in tiles)
    th = max(t.height for t in tiles)
    canvas = Image.new("RGB", (tw * cols, th * ((len(tiles) + cols - 1) // cols)), "white")
    for i, t in enumerate(tiles):
        canvas.paste(t, ((i % cols) * tw, (i // cols) * th))
    out = OUT / f"wall_check_{name}.jpg"
    canvas.save(out, quality=85)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=2)
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    all_rows = []
    for name, photos in SETS.items():
        ims = {p: load(path) for p, path in photos.items()}
        data = {p: jpeg(im) for p, im in ims.items()}
        jobs = [(p, r) for r in range(1, a.runs + 1) for p in photos]
        with ThreadPoolExecutor(6) as ex:
            rows = list(ex.map(lambda j: one(j[0], j[1], data[j[0]]), jobs))
        all_rows += [{**r, "set": name} for r in rows]
        ok = [r for r in rows if "error" not in r]
        s = [r["s"] for r in ok] or [0]
        p90 = sorted(s)[int(0.9 * (len(s) - 1))]
        msg = f"{name:6s} {len(photos)}장×{a.runs}: 찾음 {sum(bool(r.get('found')) for r in rows)}/{len(rows)}, 오류 {len(rows) - len(ok)}"
        truth = [r for r in rows if r["photo"] in TRUTH]
        if truth:
            msg += f", 정답과 맞음(덮음≥0.8·IoU≥0.5) {sum(r.get('cover', 0) >= 0.8 and r.get('iou', 0) >= 0.5 for r in truth)}/{len(truth)}"
        print(f"{msg} | {statistics.median(s):.1f}/{p90:.1f}/{max(s):.1f}초 → {sheet(name, ims, rows)}")
    (OUT / "wall_check.json").write_text(json.dumps(all_rows, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in all_rows:
        if not r.get("found"):
            print(f"  못 찾음 {r['set']} {r['photo']}#{r['run']} {r.get('error', '')[:80]} {r.get('notes', '')}")


if __name__ == "__main__":
    main()
