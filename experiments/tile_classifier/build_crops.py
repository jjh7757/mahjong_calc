"""운영과 같은 YOLO11 자리 틀로 패 상자를 잡아, 정답과 순서를 맞춰 패 크롭 학습 데이터를 만든다(2026-11-01). API 없음.

입력: seat_grow.scenes() 의 정답 있는 31장(B·C·D 6 + 매장 25), 앱과 같은 자리 크롭(가운데 쪽 폭 40).
틀: 서버 app.seat.frame(운영 코드 그대로, 패 종류는 안 씀). 못 잡으면 "틀 없음".
라벨: 손패 + 떨어진 한 장 장수가 정답 손패 장수와 같으면 왼쪽부터 순서대로. 울기는 정답 울기 수·장수가 같고 전부 같은 패(퐁·깡)일 때만
      (치는 정답 문자열 순서가 놓인 순서가 아니고, 묶음이 둘 이상이면 어느 묶음인지 틀 크기만으로 고른다).
  python -I experiments/tile_classifier/build_crops.py
결과 experiments/tile_classifier/data/{crops/*.jpg, index.json, sheet_*.jpg}(커밋 안 함)
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "experiments/speed"))
sys.path.insert(0, r"C:\Users\jjh7757\dev\mahjong-recognizer")
import seat_grow as sg  # noqa: E402
from app import river as rv  # noqa: E402
from app import seat as st  # noqa: E402

OUT = HERE / "data"
CROPS = OUT / "crops"
PAD = 0.12  # 서버 조각과 같은 여백
# 눈 확인(sheet_*.jpg, 2026-11-01): 정답 끝의 화료패가 놓인 자리와 달라 순서가 밀린 장면, 손에 가려 못 쓰는 조각
ORDER = {"20261031_133826": "4p 5p 6p 2m 2m 3m 4m 5m 6s 5s 7s 8p 8p".split()}
SKIP = {("20261031_174020", 6), ("20261031_171505", 10)}  # 6s 손에 가림, 3m 눕혀 놓음


def part(name: str) -> str:
    return "bcd" if not name.startswith("2026") else "am" if name < "20261031_14" else "pm"


def cut(rgb: np.ndarray, b: tuple[int, int, int, int]) -> Image.Image:
    x, y, w, h = b
    H, W = rgb.shape[:2]
    px, py = int(w * PAD), int(h * PAD)
    return Image.fromarray(rgb[max(0, y - py):min(H, y + h + py), max(0, x - px):min(W, x + w + px)])


def candidates(rgb: np.ndarray, det, frac: float, prod):
    """운영 틀 → 검사를 뺀 한 장 규칙 → 검사를 뺀 나눠 잡기. 라벨은 장수가 정답과 맞을 때만 붙으므로 검사를 빼도 된다."""
    if prod is not None:
        yield "prod", prod
    white = rv.white_mask(rgb)
    got = st.mosaic(det, rgb, white)
    full = [x for x in got[0] if st.ink(rgb, x) >= st.INK_MIN] if got else []
    if full:
        fr = st.structure(rgb, full, white)
        if fr is not None:
            yield "loose", fr
    split = int(rgb.shape[1] * frac)
    faces = rv.dedupe(rv.keep_faces(st.hand_cell_boxes(det, rgb, split) + [x for x in full if x[0] + x[2] / 2 >= split], white))
    fr = st.structure_split(rgb, faces, split)
    if fr is not None:
        yield "split", fr


def fit(fr, hand: list[str]) -> list[str] | None:
    """틀의 손패 줄에 붙일 정답. 정답 끝 패가 떼어 둔 패인데 틀이 못 찾았으면(14장 정답, 줄 13장) 그 한 장만 빼고 붙인다."""
    n = len(fr.hand) + (1 if fr.separate else 0)
    if n == len(hand):
        return hand
    if len(hand) == 14 and n == 13 and not fr.separate:
        return hand[:13]
    return None


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    CROPS.mkdir(parents=True, exist_ok=True)
    det = rv.TileDetector()
    index, rows = [], []
    for s in sg.scenes():
        if s["hand"] is None:
            continue
        im = Image.open(s["path"]).convert("RGB")
        rgb = np.asarray(sg.crop(im, sg.seat_box(s["grid"], s["side"], 40), s["side"]))
        frac = sg.hand_frac(s["grid"], s["side"])
        prod = st.frame(rgb, det, hand_frac=frac)
        row = dict(name=s["name"], part=part(s["name"]), framed=prod is not None, how=None, n_truth=len(s["hand"]) + sum(len(m.split()) for m in s["melds"]))
        pieces: list[tuple[str, tuple, str]] = []
        fr, tiles = None, None
        for how, cand in candidates(rgb, det, frac, prod):
            tiles = fit(cand, ORDER.get(s["name"], s["hand"]))
            if tiles:
                fr = cand
                row["how"] = how
                break
        if fr is not None:
            line = list(fr.hand) + ([fr.separate] if fr.separate else [])
            row.update(n_line=len(line), n_truth_hand=len(s["hand"]), n_melds=len(fr.melds), n_truth_melds=len(s["melds"]))
            pieces += [("hand", b, t) for b, t in zip(line, tiles)]
            truth_melds = sorted((m.split() for m in s["melds"]), key=len)
            found = sorted(fr.melds, key=len)
            if len(found) == len(truth_melds) and [len(m) for m in found] == [len(m) for m in truth_melds]:
                for boxes, tiles in zip(found, truth_melds):
                    if len(set(tiles)) == 1:
                        pieces += [("meld", b, tiles[0]) for b in boxes]
        pieces = [p for i, p in enumerate(pieces) if (s["name"], i) not in SKIP]
        for i, (kind, b, t) in enumerate(pieces):
            f = CROPS / f"{s['name']}_{i:02d}.jpg"
            cut(rgb, b).save(f, quality=92)
            index.append(dict(file=f.name, scene=s["name"], part=row["part"], kind=kind, tile=t, w=int(b[2]), h=int(b[3]), upright=bool(b[3] > b[2]),
                              box=[int(v) for v in b], side=s["side"], seat_box=list(sg.seat_box(s["grid"], s["side"], 40)), photo=list(im.size)))
        row["labelled"] = len(pieces)
        rows.append(row)
        print(s["name"], row, flush=True)
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "scenes.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in ("bcd", "am", "pm"):
        v = [r for r in rows if r["part"] == p]
        print(f"{p}: 사진 {len(v)} 틀 잡음 {sum(r['framed'] for r in v)} 라벨된 사진 {sum(r['labelled'] > 0 for r in v)} 라벨 패 {sum(r['labelled'] for r in v)}/{sum(r['n_truth'] for r in v)}")
    c = Counter(x["tile"] for x in index)
    print("종류별", dict(sorted(c.items())))
    sheet(index)


def sheet(index: list[dict], cell: int = 92, per_row: int = 16) -> None:
    """사람이 라벨을 눈으로 확인하는 그림(사진별로 한 줄)."""
    scenes = list(dict.fromkeys(x["scene"] for x in index))
    for k in range(0, len(scenes), 10):
        part_scenes = scenes[k:k + 10]
        im = Image.new("RGB", (per_row * cell + 90, len(part_scenes) * (cell + 22)), "white")
        d = ImageDraw.Draw(im)
        for r, n in enumerate(part_scenes):
            d.text((2, r * (cell + 22) + 30), n[-6:], fill="black")
            for c, x in enumerate(y for y in index if y["scene"] == n):
                t = Image.open(CROPS / x["file"])
                t.thumbnail((cell, cell))
                im.paste(t, (90 + c * cell, r * (cell + 22)))
                d.text((90 + c * cell + 2, r * (cell + 22) + cell), x["tile"], fill="red" if x["kind"] == "meld" else "blue")
        im.save(OUT / f"sheet_{k // 10}.jpg", quality=88)


if __name__ == "__main__":
    main()
