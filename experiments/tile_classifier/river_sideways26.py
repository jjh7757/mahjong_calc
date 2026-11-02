"""강의 눕힌 패(리치 선언패)를 자체 YOLO26 상자로 찾는지 잰다(2026-11-02, API 없음). 표 3-2. 운영 판정 app/river.py frame·sideways 그대로.

크롭 = 앱의 강 구역(lastZone, 폭 60%, 그 자리 쪽으로 세움), 네 자리 전부(화료자 자신의 강 포함). 검출기는 그 사진을 학습하지 않은 나눔 모델, 비교로 운영 YOLO11.
정답 = B·C·D 는 표 3-1, 매장은 사진을 눈으로 본 RIVER_TRUTH(모델 답을 보기 전, 사용자 확인 전). 보조로 label.json riichi_seats.
  python -I -X utf8 experiments/tile_classifier/river_sideways26.py --sheet   # 눈 확인용 강 크롭 시트(모델 안 돌림)
  python -I -X utf8 experiments/tile_classifier/river_sideways26.py           # 측정
결과 data/wall_frames/river_sideways.json, river_errors.jpg
"""
from __future__ import annotations

import argparse
import io
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "speed"))
from rules_core import rv  # noqa: E402
from app import local_read as lr  # noqa: E402
import seat_grow as sg  # noqa: E402

MODELS = HERE / "server_bench" / "models"
OUT = HERE / "data" / "wall_frames"
SIDES = ["bottom", "right", "top", "left"]
TURN = {"bottom": 0, "right": 270, "top": 180, "left": 90}  # 그 사람 쪽을 사진 아래로 돌리는 반시계 각도
BCD_YES = {"k25": {"bottom", "left"}, "k28": {"bottom", "left"}, "k15": {"left"}, "k26": {"left"}, "k12": {"top", "bottom"}, "k16": {"top", "bottom"}}
RIVER_TRUTH_FILE = HERE / "river_truth.json"  # {사진 끝 6자리: [눕힌 패가 있는 자리...]}, 안 보이면 "?자리"


def last_zone(g: dict, side: str, band: float = 0.6) -> tuple:
    x1, x2, y1, y2 = g["x1"], g["x2"], g["y1"], g["y2"]
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    hw, hh = round((x2 - x1) * band / 2), round((y2 - y1) * band / 2)
    return {"bottom": (cx - hw, cy, cx + hw, y2), "top": (cx - hw, y1, cx + hw, cy), "left": (x1, cy - hh, cx, cy + hh), "right": (cx, cy - hh, x2, cy + hh)}[side]


def crop(im: Image.Image, g: dict, side: str) -> Image.Image:
    x0, y0, x1, y1 = last_zone(g, side)
    w, h = im.size
    return im.crop((x0 * w // 1000, y0 * h // 1000, x1 * w // 1000, y1 * h // 1000)).rotate(TURN[side], expand=True)


def visit_scenes() -> list[dict]:
    return [s for s in sg.eval_scenes() if s["set"] == "visit"]


def sheet() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    scenes = visit_scenes()
    per, tw, th = 4, 720, 520
    for p in range(0, len(scenes), per):
        canvas = Image.new("RGB", (4 * tw, per * th))
        for r, s in enumerate(scenes[p:p + per]):
            im = ImageOps.exif_transpose(Image.open(s["path"])).convert("RGB")
            for c, side in enumerate(SIDES):
                k = crop(im, s["grid"], side)
                k.thumbnail((tw, th))
                d = ImageDraw.Draw(k)
                d.rectangle((0, 0, 170, 14), fill="black")
                d.text((2, 1), f"{s['name'][-6:]} {side}{' W' if s['side'] == side else ''}", fill="yellow")
                canvas.paste(k, (c * tw, r * th))
        canvas.save(OUT / f"river_sheet_{p // per}.jpg", quality=90)
    print("시트", (len(scenes) + per - 1) // per, [s["name"][-6:] for s in scenes])


def answer(fr) -> tuple[bool | None, int]:
    if fr is None:
        return None, 0
    return any(fr.sideways), fr.count


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", action="store_true")
    ap.add_argument("--height-max", type=float, help="눕힌 패 높이 상한(세운 패 높이 비율). 운영 기준 대신 이 값으로(YOLO26 상자용 시험)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.height_max:
        rv.SIDEWAYS_HEIGHT = (rv.SIDEWAYS_HEIGHT[0], a.height_max)
    if a.sheet:
        sheet()
        return
    truth = json.loads(RIVER_TRUTH_FILE.read_text(encoding="utf-8"))
    y26 = {k: lr.LocalReader(det_model=MODELS / f"det_fold_{k}.onnx", cls_model=MODELS / "cls_pm.onnx") for k in "ab"}
    y11 = rv.RiverLocator()
    rows, errs, ms = [], [], []
    for s in sg.eval_scenes():
        im = ImageOps.exif_transpose(Image.open(s["path"])).convert("RGB")
        bcd = s["set"] == "bcd"
        tag = s["name"] if bcd else s["name"][-6:]
        rd = y26["a" if bcd or tag >= "14" else "b"]
        marks = None if bcd else truth[tag]
        lab = {} if bcd or not (s["path"].parent / "label.json").exists() else json.loads((s["path"].parent / "label.json").read_text(encoding="utf-8"))
        for side in SIDES:
            k = crop(im, s["grid"], side)
            buf = io.BytesIO()
            k.save(buf, "JPEG", quality=92)
            rgb = np.asarray(k)
            t0 = time.perf_counter()
            f26 = rv.frame(rgb, rd.detect(rgb))
            ms.append((time.perf_counter() - t0) * 1000)
            f11, _ = y11.locate(buf.getvalue())
            want = (side in BCD_YES[tag]) if bcd else (None if f"?{side}" in marks else side in marks)
            g26, n26 = answer(f26)
            g11, n11 = answer(f11)
            row = dict(photo=tag, set=s["set"], side=side, winner=s["side"] == side, want=want, y26=g26, n26=n26, y11=g11, n11=n11,
                       label_riichi=(SIDES.index(side) in lab.get("riichi_seats", [])) if lab else None)
            rows.append(row)
            if want is not None and g26 != want:
                errs.append((row, k, f26))
                print("YOLO26", tag, side, "정답", want, "답", g26, n26, "| YOLO11", g11, n11, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "river_sideways.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    def score(rs: list[dict], m: str) -> str:
        y = [r for r in rs if r["want"] is True]
        n = [r for r in rs if r["want"] is False]
        return f"있음 {sum(r[m] is True for r in y)}/{len(y)} · 없음 {sum(r[m] is False for r in n)}/{len(n)} · 틀 못 잡음 {sum(r[m] is None for r in y + n)}"

    groups = {"B·C·D": lambda r: r["set"] == "bcd", "오전": lambda r: r["set"] == "visit" and r["photo"] < "14", "오후": lambda r: r["set"] == "visit" and r["photo"] >= "14", "전체": lambda r: True,
              "화료자 자신": lambda r: r["winner"], "화료자 아닌 자리": lambda r: not r["winner"]}
    for name, f in groups.items():
        rs = [r for r in rows if f(r)]
        print(name, "YOLO26", score(rs, "y26"), "| YOLO11", score(rs, "y11"))
    labelled = [r for r in rows if r["label_riichi"] is not None]
    for m in ("y26", "y11"):
        print("label riichi_seats", m, "리치 자리 눕힘", sum(r[m] is True for r in labelled if r["label_riichi"]), "/", sum(r["label_riichi"] for r in labelled), "리치 아닌 자리 안 눕힘", sum(r[m] is False for r in labelled if not r["label_riichi"]), "/", sum(not r["label_riichi"] for r in labelled))
    print("YOLO26 검출·틀 ms 중앙", round(statistics.median(ms)), "최대", round(max(ms)))
    if errs:
        tw, th = 560, 420
        canvas = Image.new("RGB", (4 * tw, ((len(errs) + 3) // 4) * th))
        for i, (row, k, fr) in enumerate(errs):
            c = k.copy()
            d = ImageDraw.Draw(c)
            if fr:
                seq = [b for r in fr.rows for b in r]
                for b, sw in zip(seq, fr.sideways):
                    d.rectangle((b[0], b[1], b[0] + b[2], b[1] + b[3]), outline="red" if sw else "cyan", width=6)
            c.thumbnail((tw, th))
            d = ImageDraw.Draw(c)
            d.rectangle((0, 0, 230, 14), fill="black")
            d.text((2, 1), f"{row['photo']} {row['side']} want {row['want']} got {row['y26']}", fill="yellow")
            canvas.paste(c, ((i % 4) * tw, (i // 4) * th))
        canvas.save(OUT / "river_errors.jpg", quality=88)


if __name__ == "__main__":
    main()
