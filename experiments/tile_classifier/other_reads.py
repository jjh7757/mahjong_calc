"""강 끝·표시패를 Gemini 없이 읽을 수 있나(2026-11-02, 노트북 2스레드, onnxruntime, API 없음). 앱과 같은 크롭, 시험 사진을 학습하지 않은 모델.
강 끝: 자리 쪽으로 세운 크롭 → 검출(YOLO26 또는 운영 YOLO11) → 운영 rv.frame → 마지막 패 분류. 정답 = B·C·D 는 last3.py TRUTH(자리별), 매장은 론 패(방총자 강 끝).
표시패: 도라 크롭(화료자 쪽만 안 넓힘) → YOLO26 → 틈으로 묶어 2장 이하 덩어리 = 후보 → 4방향 분류. 정답 = truth.json indicators(리치면 뒷도라 포함).
저장된 Gemini 답은 표 1-27 로그(운영 85d152f, 시각 다름).
  python -I -X utf8 experiments/tile_classifier/other_reads.py
결과 data/det/other_reads.json
"""
from __future__ import annotations

import importlib.util
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "speed"))
import flow_visit as fv  # noqa: E402
import seat_grow as sg  # noqa: E402
from rules_core import rv, st  # noqa: E402

# experiments/speed/bench.py 와 이름이 같아 경로로 올린다
_spec = importlib.util.spec_from_file_location("tile_bench", HERE / "server_bench" / "bench.py")
bn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bn)

M = HERE / "server_bench" / "models"
SIDES = ["bottom", "right", "top", "left"]
BCD_TRUTH = {
    "B": {"bottom": "6s", "left": "3s", "top": "7z"},
    "C": {"bottom": "2z", "right": "6p", "top": "3z"},
    "D": {"right": "2z", "top": "3z", "left": "7z"},
}
BCD_SCENE = {"k25": "B", "k28": "B", "k15": "C", "k26": "C", "k12": "D", "k16": "D"}
BCD_RON = {"B": "top", "C": "bottom", "D": "right"}
LOGS = ["log_flow_prod_85d152f_bcd.txt", "log_flow_prod_85d152f_visit.txt"]


def last_zone(g: dict, side: str, band: float = 0.6) -> tuple:
    x1, x2, y1, y2 = g["x1"], g["x2"], g["y1"], g["y2"]
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    hw, hh = round((x2 - x1) * band / 2), round((y2 - y1) * band / 2)
    return {"bottom": (cy, cx - hw, y2, cx + hw), "top": (y1, cx - hw, cy, cx + hw), "left": (cy - hh, x1, cy + hh, cx), "right": (cy - hh, cx, cy + hh, x2)}[side]


def dora_zone(g: dict, winner: str, m: int = 40) -> tuple:
    grow = lambda s: 0 if s == winner else m
    return (max(0, g["y1"] - grow("top")), max(0, g["x1"] - grow("left")), min(1000, g["y2"] + grow("bottom")), min(1000, g["x2"] + grow("right")))


def read_any(cls: bn.Cls, rgb: np.ndarray, b) -> tuple[str, float]:
    """방향을 모르는 패: 상자 모양에 맞는 방향 중 확신이 가장 높은 값."""
    im = bn.cut(rgb, b)
    ts = (0, 2) if b[3] > 1.15 * b[2] else (1, 3) if b[2] > 1.15 * b[3] else (0, 1, 2, 3)
    p = cls.probs([im.rotate(90 * k, expand=True) for k in ts])
    i = int(p.max(1).argmax())
    return cls.classes[int(p[i].argmax())], float(p[i].max())


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    meta = json.loads((HERE / "server_bench" / "meta.json").read_text(encoding="utf-8"))
    y26 = {k: bn.Det(M / f"det_fold_{k}.onnx", 2) for k in "ab"}
    y11 = rv.TileDetector()
    clss = {k: bn.Cls(M / f"cls_{k}.onnx", meta, 2) for k in ("bcd", "am", "pm")}
    gem = {}
    for f in LOGS:
        for line in (HERE.parent / "speed" / "results" / f).read_text(encoding="utf-8", errors="replace").splitlines():
            i = line.find("TIMING {")
            if i >= 0:
                r = json.loads(line[i + 7:])
                gem.setdefault(r["photo"], r)
    scenes = {(s["name"] if s["set"] == "bcd" else s["name"][-6:]): s for s in sg.scenes() if s["hand"] is not None}
    rows, ind_rows = [], []
    for key, s in scenes.items():
        name = s["name"]
        part = "bcd" if not name.startswith("2026") else "am" if name < "20261031_14" else "pm"
        cls, d26 = clss[part], y26["b" if part == "am" else "a"]
        t = fv.truth_of(key, scenes)
        if part == "bcd":
            truth = BCD_TRUTH[BCD_SCENE[name]]
            ron = BCD_RON[BCD_SCENE[name]]
        else:
            ron = SIDES[t["loser"]] if t["tsumo"] is False and t["loser"] is not None else None
            truth = {ron: t["win"]} if ron else {}
        im = Image.open(s["path"]).convert("RGB")
        g = gem.get(key)
        for side in SIDES:
            if side == s["side"]:
                continue
            rgb = np.asarray(sg.crop(im, last_zone(s["grid"], side), side))
            row = dict(name=name, part=part, side=side, truth=truth.get(side), ron=side == ron, gemini=(g["center_read"]["last_discards"].get(side) if g else None))
            for label, det in (("y26", d26), ("y11", y11)):
                t0 = time.perf_counter()
                det.memo = {} if label == "y26" else None
                fr = rv.frame(rgb, det.detect(rgb))
                t1 = time.perf_counter()
                if fr is None:
                    tile, conf = None, 0.0
                else:
                    # 매장 강 패는 뒤집혀 놓이기도 해(눈 확인 124654·165614) 위아래 두 방향 중 확신 높은 쪽
                    tile, conf = read_any(cls, rgb, fr.last)
                    row[label + "_up"] = cls.read([bn.cut(rgb, fr.last)])[0]
                row[label] = tile
                row[label + "_ms"] = [round((t1 - t0) * 1000), round((time.perf_counter() - t1) * 1000)]
            rows.append(row)
        if t["inds"] is not None:
            rgb = np.asarray(sg.crop(im, dora_zone(s["grid"], s["side"]), "bottom"))
            d26.memo = {}
            t0 = time.perf_counter()
            faces = rv.dedupe(rv.keep_faces(d26.detect(rgb), rv.white_mask(rgb)))
            tw = statistics.median(min(f[2], f[3]) for f in faces) if faces else 1
            groups = st.cluster(faces, tw * 0.5, tw * 0.5)
            small = [f for g2 in groups if len(g2) <= 2 for f in g2]
            all_read = [read_any(cls, rgb, f)[0] for f in faces]
            cand = [read_any(cls, rgb, f)[0] for f in small]
            ms = round((time.perf_counter() - t0) * 1000)
            want = Counter(t["inds"])
            merged = g.get("merge", {}) if g else {}
            got_g = (merged.get("dora_indicators") or []) + (merged.get("ura_indicators") or [])
            ind_rows.append(dict(name=name, part=part, inds=t["inds"], faces=len(faces), small=len(small), cand=cand, ms=ms,
                                 in_all=not (want - Counter(all_read)), in_cand=not (want - Counter(cand)), exact=Counter(cand) == want, gemini=got_g, gem_ok=sorted(got_g) == sorted(t["inds"])))
    (HERE / "data" / "det" / "other_reads.json").write_text(json.dumps(dict(last=rows, ind=ind_rows), ensure_ascii=False, indent=1), encoding="utf-8")
    judged = [r for r in rows if r["truth"]]
    print("== 강 끝(정답 있는 자리)", len(judged), "/ 론 자리", sum(r["ron"] for r in judged))
    for label in ("y26", "y11"):
        ok, ron = sum(r[label] == r["truth"] for r in judged), [r for r in judged if r["ron"]]
        miss = sum(r[label] is None for r in judged)
        print(label, f"맞음 {ok}/{len(judged)}, 론 패 {sum(r[label] == r['truth'] for r in ron)}/{len(ron)}, 틀 못 잡음 {miss}, 검출·틀 {statistics.median(r[label + '_ms'][0] for r in rows)}ms, 읽기 {statistics.median(r[label + '_ms'][1] for r in rows)}ms(자리당 중앙)")
        for part in ("bcd", "am", "pm"):
            p = [r for r in judged if r["part"] == part]
            print("  ", part, f"{sum(r[label] == r['truth'] for r in p)}/{len(p)}")
    wg = [r for r in judged if r["gemini"]is not None or r["ron"]]
    print("Gemini", f"맞음 {sum(r['gemini'] == r['truth'] for r in judged)}/{len(judged)}, 론 패 {sum(r['gemini'] == r['truth'] for r in judged if r['ron'])}/{sum(r['ron'] for r in judged)}", len(wg))
    for label in ("y26", "y11"):
        both = [r for r in rows if r[label] and r["gemini"]]
        print(label, f"Gemini 와 같음(정답 없는 자리 포함) {sum(r[label] == r['gemini'] for r in both)}/{len(both)}")
    print("틀린 것")
    for r in judged:
        if r["y26"] != r["truth"] or r["y11"] != r["truth"] or r["gemini"] != r["truth"]:
            print(" ", r["name"][-6:], r["side"], "정답", r["truth"], "y26", r["y26"], "y11", r["y11"], "Gemini", r["gemini"])
    print("== 표시패", len(ind_rows))
    n = len(ind_rows)
    print(f"검출·분류에 들어 있음 {sum(r['in_all'] for r in ind_rows)}/{n}, 2장 이하 덩어리 안 {sum(r['in_cand'] for r in ind_rows)}/{n}, 후보 = 정답 {sum(r['exact'] for r in ind_rows)}/{n}, 후보 수 중앙 {statistics.median(r['small'] for r in ind_rows)}, 상자 수 중앙 {statistics.median(r['faces'] for r in ind_rows)}, Gemini 맞음 {sum(r['gem_ok'] for r in ind_rows)}/{n}, 시간 {statistics.median(r['ms'] for r in ind_rows)}ms")
    for r in ind_rows:
        print(" ", r["name"][-6:], "정답", r["inds"], "후보", r["cand"], "상자", r["faces"], "| Gemini", r["gemini"])


if __name__ == "__main__":
    main()
