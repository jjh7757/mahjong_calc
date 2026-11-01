"""넓은 구역 판독(/v2/seatwide)의 묶인 낱장(lone=false)이 탁자에 내놓은 도라·뒷도라 표시패와 맞나(2026-11-01 저녁).

매장 습관: 리치 화료면 표시패 두 장을 탁자 위 빈 곳에 내놓는다(리치 아니면 왕패에 그대로). 넓은 판독이 이제 화료 장면마다 미리 가므로
(metrics 표 1-11) 그 답의 묶인 낱장을 리치 화료의 표시패로 쓸 수 있는지 본다. 정답은 truth.json 의 indicators(매장만, B·C·D 는 표시패 정답 없음).

  python -X utf8 experiments/speed/wide_indicators.py            로컬 서버 8030 에 절반 크롭을 보내 results/seatwide_half.json 에 저장
  python -X utf8 experiments/speed/wide_indicators.py --show     저장된 답으로 채점만
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import seat_grow as sg  # noqa: E402
from wide_seat import half_box  # noqa: E402

OUT = Path(__file__).parent / "results" / "seatwide_half.json"
TRUTH = json.loads((Path(__file__).resolve().parents[2] / "experiments/visit_20261031/truth.json").read_text(encoding="utf-8"))["scenes"]
URL = "http://127.0.0.1:8030/v2/seatwide"


def post(jpg: bytes) -> dict:
    t0 = time.perf_counter()
    r = requests.post(URL, files={"image": ("seatwide.jpg", jpg, "image/jpeg")}, timeout=180)
    return {"status": r.status_code, "s": round(time.perf_counter() - t0, 1), "data": r.json() if r.status_code == 200 else r.text[:200]}


def run(sleep: float) -> None:
    out = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    for s in sg.scenes():
        if s["name"] in out:
            continue
        im = Image.open(s["path"]).convert("RGB")
        jpg = sg.jpeg(sg.crop(im, half_box(s["grid"], s["side"]), s["side"]))
        res = post(jpg)
        out[s["name"]] = {"set": s["set"], "side": s["side"], **res}
        d = res["data"] if isinstance(res["data"], dict) else {}
        print(s["name"][-6:], res["status"], f"{res['s']}초", "줄", len(d.get("row") or []), "낱장", [(x["tile"], x["lone"]) for x in d.get("singles") or []], "울기", [m["tiles"] for m in d.get("melds") or []])
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        time.sleep(sleep)


def show() -> None:
    out = json.loads(OUT.read_text(encoding="utf-8"))
    tally = Counter()
    for name, r in sorted(out.items()):
        if r["set"] != "visit" or not isinstance(r["data"], dict):
            continue
        t = TRUTH.get(name) or {}
        inds, riichi = t.get("indicators"), t.get("riichi")
        grouped = sorted(x["tile"] for x in r["data"].get("singles") or [] if x.get("pair"))  # 표시패 짝(서버 pair, 2026-11-01 저녁부터)
        lone = sorted(x["tile"] for x in r["data"].get("singles") or [] if x["lone"])
        ok = inds is not None and sorted(inds) == grouped
        sub = inds is not None and all(grouped.count(i) >= 1 for i in inds) and len(grouped) > len(inds)
        if riichi:
            tally["리치"] += 1
            tally["리치 묶음=표시패"] += ok
            tally["리치 묶음⊃표시패"] += sub
            tally["리치 묶음 없음"] += not grouped
        else:
            tally["리치 아님"] += 1
            tally["리치 아님인데 묶음 있음"] += bool(grouped)
        print(name[-6:], "리치" if riichi else "    ", "정답", inds, "| 묶음", grouped, "외톨이", lone, "→", "맞음" if ok else ("포함" if sub else ""))
    print(dict(tally))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--sleep", type=float, default=5)
    a = ap.parse_args()
    show() if a.show else (run(a.sleep), show())
