"""격자 구역 어디에도 속하지 않은 앞면 패 = 도라 표시패? (2026-11-03, API 없음). metrics 표 1-54.

사용자 제안: 리치 화료의 표시패는 사람마다 놓는 자리가 달라 "2장 붙은 짝" 규칙이 놓친다(165614·170105). 손패·울기 띠(선에서 가운데 쪽으로
seatReadGrow 40 만큼 넓힌 것)·강 띠(lastZone, 폭 0.6)·리치봉 상자에 들지 않는 앞면 패를 전부 표시패 후보로 보면 어떤가.
10-31 화료 원본 19장(저장 격자) + 자체 모델(그 사진을 학습하지 않은 나눔 모델) 검출·분류.

  python -I -X utf8 experiments/tile_classifier/dora_outside.py
결과 data/dora_outside/result.json, 그림 overlay_<사진>.jpg (밖 = 빨강, 띠 안 = 파랑)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "speed"))
import wall_frames as wf  # noqa: E402
import seat_grow as sg  # noqa: E402
from app import local_read as lr  # noqa: E402

OUT = HERE / "data" / "dora_outside"
TRUTH = json.loads((wf.ROOT / "experiments/visit_20261031/truth.json").read_text(encoding="utf-8"))["scenes"]
import os
SEAT_GROW, BAND = int(os.environ.get("SEAT_GROW", "40")), 0.6  # SEAT_GROW: 자리 띠를 선에서 가운데 쪽으로 넓힌 폭(음수면 패산까지 가운데로)
# 강 구역을 "기기 상자 변에서 바깥으로 RIVER_DEPTH(1000 분율, 패 3줄 + 틈)" 으로 좁힌다. 띠 0.6 은 선까지 뻗어 패산 위·옆 표시패까지 덮었다
# (165614: 화료자가 도라·뒷도라를 패산 끝에 그대로 둠). 폭은 기기 상자 폭 + 양쪽 RIVER_SIDE.
RIVER_DEPTH, RIVER_SIDE = 130, 30
OCCLUDED = {"172424", "174020"}


def zone_of(u: float, v: float, g: dict) -> str:
    """패 가운데(1000 분율 u=x, v=y)가 어느 구역인가: seat / river / sticks / outside."""
    x1, x2, y1, y2 = g["x1"], g["x2"], g["y1"], g["y2"]
    if not (x1 + SEAT_GROW <= u <= x2 - SEAT_GROW and y1 + SEAT_GROW <= v <= y2 - SEAT_GROW):
        return "seat"
    if g.get("sticks"):
        ymin, xmin, ymax, xmax = g["sticks"]
        if xmin <= u <= xmax and ymin <= v <= ymax:
            return "sticks"
    if g.get("sticks"):
        ymin, xmin, ymax, xmax = g["sticks"]
        tall = ymin - RIVER_DEPTH <= v <= ymax + RIVER_DEPTH and xmin - RIVER_SIDE <= u <= xmax + RIVER_SIDE  # 아래·위 강
        wide = xmin - RIVER_DEPTH <= u <= xmax + RIVER_DEPTH and ymin - RIVER_SIDE <= v <= ymax + RIVER_SIDE  # 왼·오른 강
        return "river" if tall or wide else "outside"
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    hw, hh = (x2 - x1) * BAND / 2, (y2 - y1) * BAND / 2
    if cx - hw <= u <= cx + hw or cy - hh <= v <= cy + hh:  # 기기 상자가 없을 때만: 세로 띠(아래·위 강) 또는 가로 띠(왼·오른 강)
        return "river"
    return "outside"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    grids = {s["name"]: s["grid"] for s in sg.scenes() if s["set"] == "visit"}
    readers = {"a": lr.LocalReader(det_model=wf.MODELS / "det_fold_a.onnx", cls_model=wf.MODELS / "cls_pm.onnx"),
               "b": lr.LocalReader(det_model=wf.MODELS / "det_fold_b.onnx", cls_model=wf.MODELS / "cls_am.onnx")}
    rows = []
    for name, t in sorted(TRUTH.items()):
        g = grids.get(name)
        if g is None:
            print(name, "격자 없음")
            continue
        im = Image.open(wf.CAPS / name / "original.jpg").convert("RGB")
        rgb = np.asarray(im)
        W, H = im.size
        rd = readers["b" if name[9:11] < "14" else "a"]
        faces = rd.detect(rgb)
        d = ImageDraw.Draw(im)
        outside = []
        tw = float(np.median([f[2] for f in faces])) if faces else 1.0
        th = float(np.median([f[3] for f in faces])) if faces else 1.0
        for b in faces:  # (x, y, w, h)
            x0, y0, bw, bh = b
            u, v = (x0 + bw / 2) / W * 1000, (y0 + bh / 2) / H * 1000
            z = zone_of(u, v, g)
            d.rectangle((x0, y0, x0 + bw, y0 + bh), outline="red" if z == "outside" else ("yellow" if z == "sticks" else "blue"), width=6 if z == "outside" else 2)
            if z == "outside":
                tile, conf = rd.read_turned(rgb, b, tw, th) if os.environ.get("TURNED") else rd.read_any(rgb, b)  # TURNED=1: 15° 단위로 돌려 읽기(비스듬히 내놓은 짝, 170105)
                outside.append(dict(tile=tile, conf=round(conf, 3), u=round(u), v=round(v)))
        got = sorted(o["tile"] for o in outside)
        truth = sorted(t["indicators"])
        exact = got == truth
        contains = all(x in got for x in truth)
        extra = len(got) - sum(1 for x in truth if x in got)
        rows.append(dict(name=name[-6:], riichi=t["riichi"], truth=truth, outside=outside, exact=exact, contains=contains, extra=extra, faces=len(faces), occluded=name[-6:] in OCCLUDED))
        im.save(OUT / f"overlay_{name[-6:]}.jpg", quality=80)
        print(name[-6:], "리치" if t["riichi"] else "    ", "정답", truth, "밖", got, [(o["conf"], o["u"], o["v"]) for o in outside], "정확" if exact else ("포함+여분%d" % extra if contains else "빠짐"), "가림" if name[-6:] in OCCLUDED else "", flush=True)
    ok = [r for r in rows if not r["occluded"]]
    summ = {}
    for label, sel in (("리치", [r for r in ok if r["riichi"]]), ("리치 아님", [r for r in ok if not r["riichi"]]), ("전체", ok)):
        summ[label] = dict(n=len(sel), exact=sum(r["exact"] for r in sel), contains=sum(r["contains"] for r in sel), none_outside=sum(1 for r in sel if not r["outside"]),
                           two_plus_exact=sum(r["exact"] for r in sel if len(r["outside"]) >= 2), two_plus=sum(1 for r in sel if len(r["outside"]) >= 2),
                           extra_total=sum(r["extra"] for r in sel))
    print(json.dumps(summ, ensure_ascii=False))
    (OUT / f"result_grow{SEAT_GROW}{'_turned' if os.environ.get('TURNED') else ''}.json").write_text(json.dumps(dict(summary=summ, rows=rows, rule=dict(seat_grow=SEAT_GROW, band=BAND, river_depth=RIVER_DEPTH, river_side=RIVER_SIDE)), ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
