"""화료 원본의 리치 아닌 화료 9장을 운영 왕패 경로(/v2/wall → 10% 넓혀 원본 자르기 → /v2/walldora)로 읽는다(2026-11-02, API 18회). 표 1-35.
실제 앱은 판 시작 때 상자를 잡아 두지만 그 값이 기록에 없어(dora_box null) 화료 사진으로 상자를 잡는다.
  python -I -X utf8 experiments/tile_classifier/wall_photos_gemini.py
결과 data/wall_frames/photos_gemini.json
"""
from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

import requests
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
V = ROOT / "experiments" / "visit_20261031"
URL = "https://mahjong.ai-agent-develop.cloud"
ROTATE = {"bottom": 0, "right": -90, "top": 180, "left": 90}


def post(path: str, im: Image.Image, key: str) -> tuple[dict, float]:
    im = im.copy()
    im.thumbnail((1568, 1568))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    t0 = time.time()
    r = requests.post(f"{URL}{path}", headers={"X-API-Key": key}, files={"image": ("f.jpg", buf.getvalue(), "image/jpeg")}, timeout=120)
    return r.json(), round(time.time() - t0, 1)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    key = (ROOT / ".recognizer_key").read_text().strip()
    scenes = json.loads((V / "truth.json").read_text(encoding="utf-8"))["scenes"]
    res = {}
    for name, s in sorted(scenes.items()):
        if s.get("riichi") or not s.get("indicators"):
            continue
        im = Image.open(V / "captures" / name / "original.jpg").convert("RGB")
        w, h = im.size
        wall, s1 = post("/v2/wall", im, key)
        row = dict(want=s["indicators"], wall_s=s1, found=wall.get("found"), box=wall.get("box"), side=wall.get("side"), notes=wall.get("notes"), read=None, read_s=None)
        box = wall.get("box")
        if wall.get("found") and box:
            p = int(max(box[2] - box[0], box[3] - box[1]) * 0.1)
            y0, x0, y1, x1 = max(0, box[0] - p), max(0, box[1] - p), min(1000, box[2] + p), min(1000, box[3] + p)
            crop = im.crop((x0 * w // 1000, y0 * h // 1000, x1 * w // 1000, y1 * h // 1000)).rotate(ROTATE.get(wall.get("side") or "bottom", 0), expand=True)
            rd, s2 = post("/v2/walldora", crop, key)
            row.update(read=rd.get("indicators"), read_s=s2, read_raw={k: rd.get(k) for k in ("notes", "error", "detail")})
        tiles = [x["tile"] if isinstance(x, dict) else x for x in row["read"] or []]
        row["tiles"] = tiles
        row["ok"] = sorted(tiles) == sorted(s["indicators"])
        res[name] = row
        print(name[-6:], "정답", s["indicators"], "상자", row["side"], row["box"], row["wall_s"], "읽음", tiles, row["read_s"], "OK" if row["ok"] else "NO", (row["notes"] or "")[:50], flush=True)
        (HERE / "data" / "wall_frames" / "photos_gemini.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        time.sleep(2)
    print("맞음", sum(r["ok"] for r in res.values()), "/", len(res))


if __name__ == "__main__":
    main()
