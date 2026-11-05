"""프레임 사진에서 깡이 놓인 장면 후보를 찾는다(2026-11-04, 사용자 "프레임 사진에서 깡들어 있는거 가져와서 테스트해봐", 노트북, API 없음).

운영 검출기·분류기(app/assets)로 프레임마다 앞면 패를 읽고
  명깡·가깡 후보 = 같은 종류(적5 는 5 로) 4장이 이웃으로 이어진 묶음
  안깡 후보     = 같은 종류 2장이 붙어 있고, 그 줄 양끝 바로 옆이 패 뒷면 색
을 고른다. 손패 4장 같은 경우도 섞이므로 후보는 눈으로 확인한다.
  python -I -X utf8 experiments/tile_classifier/kan_scan.py [폴더...]
결과 data/kan/cands.json, 후보 그림 data/kan/cand_<n>.jpg(빨간 상자)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.environ.get("RECOGNIZER_REPO", "C:/Users/jjh7757/dev/mahjong-recognizer"))
from app import local_read as lr  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "data" / "kan"
DIRS = [ROOT / "visit_20261031" / "captures", ROOT / "tracking", ROOT / "tablet_20261103" / "captures"]


def norm(t: str) -> str:
    return "5" + t[1] if t[0] == "0" else t


def near(a, b, tw: float) -> bool:
    ax, ay = a[0] + a[2] / 2, a[1] + a[3] / 2
    bx, by = b[0] + b[2] / 2, b[1] + b[3] / 2
    return np.hypot(ax - bx, ay - by) <= 1.35 * tw


def groups(items: list, tw: float) -> list[list[int]]:
    """같은 종류끼리 이웃으로 이어진 묶음(인덱스)."""
    seen, out = set(), []
    for i in range(len(items)):
        if i in seen:
            continue
        stack, g = [i], []
        seen.add(i)
        while stack:
            k = stack.pop()
            g.append(k)
            for j in range(len(items)):
                if j not in seen and items[j][1] == items[k][1] and near(items[j][0], items[k][0], tw):
                    seen.add(j)
                    stack.append(j)
        out.append(g)
    return out


def backs_at_ends(rgb: np.ndarray, boxes: list) -> bool:
    """두 장 묶음의 줄 방향 양끝 바로 옆에 패 뒷면 색이 있나."""
    (a, b) = boxes
    ca = np.array([a[0] + a[2] / 2, a[1] + a[3] / 2])
    cb = np.array([b[0] + b[2] / 2, b[1] + b[3] / 2])
    d = cb - ca
    m = lr._back_mask(rgb)
    H, W = m.shape
    w, h = (a[2] + b[2]) / 2, (a[3] + b[3]) / 2
    hits = 0
    for c in (ca - d, cb + d):
        x0, y0 = int(c[0] - w * 0.35), int(c[1] - h * 0.35)
        x1, y1 = int(c[0] + w * 0.35), int(c[1] + h * 0.35)
        if x0 < 0 or y0 < 0 or x1 > W or y1 > H:
            continue
        hits += m[y0:y1, x0:x1].mean() >= 0.5
    return hits == 2


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    dirs = [Path(p) for p in sys.argv[1:]] or DIRS
    frames = sorted(p for d in dirs if d.exists() for p in d.rglob("*.jpg"))
    reader = lr.LocalReader()
    cands = []
    for n, p in enumerate(frames):
        try:
            rgb = np.asarray(Image.open(p).convert("RGB"))
        except Exception:
            continue
        if min(rgb.shape[:2]) < 300:
            continue
        boxes = reader.detect(rgb, low=False)
        if len(boxes) < 4:
            continue
        tw = float(np.median([min(b[2], b[3]) for b in boxes]))
        items = [(b, norm(reader.read_any(rgb, b)[0])) for b in boxes]
        for g in groups(items, tw):
            bs = [items[i][0] for i in g]
            kind = "4장" if len(g) >= 4 else "안깡?" if len(g) == 2 and backs_at_ends(rgb, bs) else None
            if kind:
                cands.append(dict(path=str(p), kind=kind, tile=items[g[0]][1], boxes=bs))
                print(len(cands), kind, items[g[0]][1], p.relative_to(ROOT), flush=True)
        if n % 100 == 0:
            print(f"-- {n}/{len(frames)}", flush=True)
    (OUT / "cands.json").write_text(json.dumps(cands, ensure_ascii=False, indent=1), encoding="utf-8")
    for i, c in enumerate(cands):
        im = Image.open(c["path"]).convert("RGB")
        dr = ImageDraw.Draw(im)
        for b in c["boxes"]:
            dr.rectangle([b[0], b[1], b[0] + b[2], b[1] + b[3]], outline=(255, 0, 0), width=6)
        xs = [b[0] for b in c["boxes"]] + [b[0] + b[2] for b in c["boxes"]]
        ys = [b[1] for b in c["boxes"]] + [b[1] + b[3] for b in c["boxes"]]
        pad = 3 * max(b[3] for b in c["boxes"])
        im.crop((max(0, min(xs) - pad), max(0, min(ys) - pad), min(im.width, max(xs) + pad), min(im.height, max(ys) + pad))).save(OUT / f"cand_{i}.jpg", quality=85)
    print("후보", len(cands), "프레임", len(frames))


if __name__ == "__main__":
    main()
