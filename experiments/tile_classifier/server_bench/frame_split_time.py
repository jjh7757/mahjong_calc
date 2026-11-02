"""틀 잡기 시간을 YOLO 실행과 그 밖(리사이즈·NMS·규칙)으로 나눈다(2026-11-02, 노트북 2스레드, API 없음).
  python -I -X utf8 experiments/tile_classifier/server_bench/frame_split_time.py
"""
from __future__ import annotations

import json
import statistics
import sys
import time

import numpy as np

import bench as bn

meta = json.loads((bn.HERE / "meta.json").read_text(encoding="utf-8"))
sys.stdout.reconfigure(encoding="utf-8")


class Timed(bn.Det):
    def __init__(self, path, threads):
        super().__init__(path, threads)
        self.onnx = 0.0
        real = self.s.run

        def run(*a, **k):
            t = time.perf_counter()
            r = real(*a, **k)
            self.onnx += time.perf_counter() - t
            return r

        self.s = type("S", (), {"run": staticmethod(run), "get_inputs": staticmethod(self.s.get_inputs)})()
        self.whole = 0.0

    def _detect(self, rgb):
        t = time.perf_counter()
        r = super()._detect(rgb)
        self.whole += time.perf_counter() - t
        return r


det = Timed(bn.HERE / "models" / "det_final.onnx", 2)
cls = bn.Cls(bn.HERE / "models" / "cls_pm.onnx", meta, 2)
rows = []
for rep in range(2):
    for p in meta["photos"]:
        det.memo, det.runs, det.onnx, det.whole = {}, 0, 0.0, 0.0
        r = bn.one((bn.HERE / "crops" / f"{p['name']}.jpg").read_bytes(), det, cls, p["frac"])
        if rep:
            rows.append(dict(name=p["name"], framed=r["framed"], runs=det.runs, onnx=det.onnx * 1000, det=det.whole * 1000, frame=r["frame_ms"], read=r["read_ms"]))
m = lambda k, f=lambda x: True: round(statistics.median(x[k] for x in rows if f(x)))
for label, f in (("전체", lambda x: True), ("규칙 1번에 잡힘(검출 2번)", lambda x: x["runs"] <= 2), ("나눠 잡기까지(검출 3번 이상)", lambda x: x["runs"] > 2)):
    n = sum(f(x) for x in rows)
    if n:
        print(f"{label} {n}장: 틀 잡기 {m('frame', f)}ms = ONNX {m('onnx', f)}ms + 입력·NMS {m('det', f) - m('onnx', f)}ms + 규칙 약 {m('frame', f) - m('det', f)}ms, 검출 {m('runs', f)}번, 패 읽기 {m('read', f)}ms")
print("검출 횟수 분포", {k: sum(x["runs"] == k for x in rows) for k in sorted({x["runs"] for x in rows})})
