"""자체 YOLO26n(1회차) 틀 잡기가 어느 검사에서 왜 떨어지는지 사진마다 나눈다(2026-11-02, 노트북 CPU, API 없음). det_eval.py 와 같은 크롭·모델.

경로: A1 = 모자이크 + structure, A2·A3 = 손패 칸·모서리 칸(frame_split 의 두 후보), B = 크롭 통째 검출 + structure_split.
이유: 첫 번째로 걸린 검사와 그 값. 정답 장수와 틀 장수의 차이도 적는다.
  python -I experiments/tile_classifier/frame_diag.py
결과 data/det/diag/diag.json, data/det/diag/<이름>.jpg(손패 초록, 떨어진 패 노랑, 울기 파랑, 나머지 빨강)
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import det_eval as de  # noqa: E402
from det_eval import rv, sg, st  # noqa: E402

OUT = HERE / "data" / "det" / "diag"


def why(fr, rgb: np.ndarray) -> tuple[str, str]:
    """(검사 이름, 값). 통과면 ("통과", "")."""
    if fr is None:
        return "틀 없음", ""
    if not st.valid(fr):
        return "장수", f"{fr.count}(손패 {len(fr.hand)} 떨어진 {1 if fr.separate else 0} 울기 {[len(m) for m in fr.melds]} 나머지 {len(fr.loose)})"
    hand = fr.hand
    if len(hand) < 4:
        return "손패 4장 미만", str(len(hand))
    hs, ws = [x[3] for x in hand], [x[2] for x in hand]
    mh, mw = statistics.median(hs), statistics.median(ws)
    bad_h = [i for i, h in enumerate(hs) if abs(h - mh) > 0.25 * mh]
    bad_w = [i for i, w in enumerate(ws) if abs(w - mw) > 0.25 * mw]
    if bad_h:
        return "크기(높이)", f"{[(i, round(hs[i] / mh, 2)) for i in bad_h]}"
    if bad_w:
        return "크기(너비)", f"{[(i, round(ws[i] / mw, 2)) for i in bad_w]}"
    xs = np.array([x[0] + x[2] / 2 for x in hand], float)
    ys = np.array([x[1] + x[3] / 2 for x in hand], float)
    a, c = np.polyfit(xs, ys, 1)
    off = np.abs(ys - (a * xs + c))
    if off.max() > 0.25 * mh:
        return "한 줄", f"직선에서 {off.max() / mh:.2f}패, 기울기 {a:.3f}"
    steps = np.diff(xs) / mw
    if steps.min() <= 0.6:
        return "간격(겹침)", f"{steps.min():.2f}칸"
    if steps.max() >= 1.4:
        return "간격(틈)", f"{steps.max():.2f}칸"
    th = statistics.median(hs)
    for m in fr.melds:
        for p, q in zip(m, m[1:]):
            if p[0] + p[2] - q[0] > 0.3 * min(p[2], q[2]):
                return "울기 겹침", f"{(p[0] + p[2] - q[0]) / min(p[2], q[2]):.2f}"
        for x in m:
            if not 0.5 * th <= x[3] <= 1.3 * th:
                return "울기 높이", f"{x[3] / th:.2f}"
    low = [round(st.ink(rgb, x), 3) for kind, x in fr.pieces() if kind != "loose" and st.ink(rgb, x) < st.INK_MIN]
    if low:
        return "무늬", str(low)
    return "통과", ""


def draw(rgb: np.ndarray, fr, path: Path) -> None:
    im = Image.fromarray(rgb).copy()
    d = ImageDraw.Draw(im)
    def box(x, color):
        d.rectangle((x[0], x[1], x[0] + x[2], x[1] + x[3]), outline=color, width=4)
    if fr is not None:
        for x in fr.loose:
            box(x, (255, 40, 40))
        for m in fr.melds:
            for x in m:
                box(x, (40, 120, 255))
        for x in fr.hand:
            box(x, (40, 230, 60))
        if fr.separate:
            box(fr.separate, (255, 220, 0))
    im.thumbnail((1600, 1600))
    im.save(path, quality=85)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    dets = {"a": de.Det(de.OUT / "fold_a.pt"), "b": de.Det(de.OUT / "fold_b.pt")}
    rows = []
    for s in sg.eval_scenes():
        if s["hand"] is None:
            continue
        name = s["name"]
        am = name.startswith("2026") and name < "20261031_14"
        det = dets["b" if am else "a"]
        rgb = np.asarray(sg.crop(Image.open(s["path"]).convert("RGB"), sg.seat_box(s["grid"], s["side"], 40), s["side"]))
        split = int(rgb.shape[1] * sg.hand_frac(s["grid"], s["side"]))
        white = rv.white_mask(rgb)
        got = st.mosaic(det, rgb, white)
        boxes = [x for x in got[0] if st.ink(rgb, x) >= st.INK_MIN] if got else []
        a1 = st.structure(rgb, boxes, white) if got else None
        hand = st.hand_cell_boxes(det, rgb, split)
        a2 = st.structure_split(rgb, rv.dedupe(rv.keep_faces(hand + [x for x in boxes if x[0] + x[2] / 2 >= split], white)), split)
        a3 = st.structure_split(rgb, rv.dedupe(rv.keep_faces(hand + st.corner_cell_boxes(det, rgb, split), white)), split)
        faces = rv.dedupe(rv.keep_faces(det.detect(rgb), white))
        b = st.structure_split(rgb, faces, split) if faces else None
        cands = dict(A1=a1, A2=a2, A3=a3, B=b)
        reasons = {k: why(v, rgb) for k, v in cands.items()}
        want = len(s["hand"]) + 3 * len(s["melds"])
        row = dict(name=name, want=want, melds=len(s["melds"]), faces=len(faces), passed=[k for k, v in reasons.items() if v[0] == "통과"],
                   **{k: dict(why=reasons[k][0], val=reasons[k][1], count=cands[k].count if cands[k] else None) for k in cands})
        rows.append(row)
        print(name[-6:], "정답", want, "울기", len(s["melds"]), "통과", row["passed"] or "-", "| " + " | ".join(f"{k} {reasons[k][0]} {reasons[k][1]}" for k in cands), flush=True)
        best = next((cands[k] for k in ("B", "A1", "A2", "A3") if reasons[k][0] == "통과"), b or a1)
        draw(rgb, best, OUT / f"{name}.jpg")
    (OUT / "diag.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    fail = [r for r in rows if not r["passed"]]
    print(f"틀 통과 {len(rows) - len(fail)}/{len(rows)}")
    for k in ("A1", "A2", "A3", "B"):
        print(k, dict(Counter(r[k]["why"] for r in fail)))


if __name__ == "__main__":
    main()
