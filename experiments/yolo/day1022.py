"""2026-10-22 첫날 실험 사진을 공개 YOLO11(nikmomo s·m)로 다시 읽어 본다(2026-11-08, 사용자 요청).

첫날엔 합성 사진으로 학습 중이던 자체 YOLO 와 Gemini 만 시험했다. 같은 사진에 공개 YOLO11 을 돌리면 어땠을지 확인.

세트:
  hand   눕힌 손패를 위에서 찍은 실제 사진 3장(정답 있음: samples_real_crop, samples_real2 labels.json)
  synth  합성 손패 12장(정답 있음: samples_synth/labels.json, CC0 패 그림)
  scene  정답 없는 사진(탁자 전경 table1·table2, 오른쪽 손패 크롭, 강 크롭, 방송 캡처, 폰 첫 촬영) — 잡은 수·목록만

채점(정답 있는 세트): run_yolo.score 와 같음. 패 = 정답과 예측의 다중집합 교집합, 통째 = 손패 전체 일치.
입력 크기 640(모델 기본)과 1280 둘 다.

python -I day1022.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_yolo as ry  # noqa: E402

VLM = HERE.parent / "vlm"


def parse(s: str) -> list[str]:
    """'234s789s45p77m0m43m' 또는 '3p 3p ...' → ['2s','3s',...]."""
    s = s.replace(" ", "")
    out, digits = [], ""
    for ch in s:
        if ch.isdigit():
            digits += ch
        else:
            out += [d + ch for d in digits]
            digits = ""
    return out


def load_labeled():
    sets = {"hand": [], "synth": []}
    for d in ("samples_real_crop", "samples_real2"):
        for name, truth in json.loads((VLM / d / "labels.json").read_text(encoding="utf-8")).items():
            sets["hand"].append((f"{d}/{name}", VLM / d / name, parse(truth)))
    for name, truth in json.loads((VLM / "samples_synth" / "labels.json").read_text(encoding="utf-8")).items():
        t = truth if isinstance(truth, str) else truth.get("tiles", truth)
        if isinstance(t, list):
            t = " ".join(t)
        sets["synth"].append((f"samples_synth/{name}", VLM / "samples_synth" / name, parse(t)))
    return sets


SCENE = ["samples_real/table1.jpg", "samples_real/table2.jpg", "samples_real_crop/hand_right.jpg",
         "samples_real_crop/discards_center.jpg", "samples_broadcast/full.jpg", "samples_broadcast/hand_bottom.jpg",
         "samples_phone/phone_shot1.jpg"]


def main():
    sets = load_labeled()
    models = [ry.Nikmomo("s"), ry.Nikmomo("m")]
    rows = []
    for m in models:
        for imgsz in (640, 1280):
            for set_name, items in sets.items():
                for key, path, truth in items:
                    img = cv2.imread(str(path))
                    t0 = time.perf_counter()
                    pred, _ = m.predict(img, imgsz=imgsz)
                    dt = time.perf_counter() - t0
                    names = [p[0] for p in ry.order(pred, horizontal=True)]
                    hit, hit_loose, exact = ry.score(names, truth)
                    rows.append(dict(model=m.name, imgsz=imgsz, set=set_name, photo=key, truth=len(truth),
                                     pred=len(names), hit=hit, hit_loose=hit_loose, exact=exact,
                                     sec=round(dt, 3), tiles=" ".join(names)))
            for key in SCENE:
                img = cv2.imread(str(VLM / key))
                pred, _ = m.predict(img, imgsz=imgsz)
                names = [p[0] for p in ry.order(pred, horizontal=True)]
                rows.append(dict(model=m.name, imgsz=imgsz, set="scene", photo=key, truth=None, pred=len(names),
                                 hit=None, hit_loose=None, exact=None, sec=None, tiles=" ".join(names),
                                 conf=[round(p[1], 2) for p in pred]))
    out = HERE / "results" / "day1022.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    print("| 모델 | 입력 | 세트 | 패 맞음 | 남는 패 | 손패 통째 | 사진당 초(중앙) |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for m in models:
        for imgsz in (640, 1280):
            for s in ("hand", "synth"):
                r = [x for x in rows if x["model"] == m.name and x["imgsz"] == imgsz and x["set"] == s]
                tot = sum(x["truth"] for x in r)
                hit = sum(x["hit"] for x in r)
                extra = sum(x["pred"] - x["hit"] for x in r)
                ex = sum(x["exact"] for x in r)
                secs = sorted(x["sec"] for x in r)
                print(f"| {m.name} | {imgsz} | {s} {len(r)}장 | {hit}/{tot} ({hit / tot:.0%}) | {extra} | {ex}/{len(r)} | {secs[len(secs) // 2]:.2f} |")
    print()
    for x in rows:
        if x["set"] != "synth":
            extra = "" if x["truth"] is None else f" 정답 {x['truth']} 맞음 {x['hit']} 통째 {x['exact']}"
            print(f"{x['model']} {x['imgsz']} {x['photo']}: {x['pred']}장{extra} | {x['tiles']}")


if __name__ == "__main__":
    main()
