"""자체 모델 확신도로 자동 반영을 막으면 얼마나 막히나(2026-11-02, 노트북, API 없음). 그 사진을 학습하지 않은 나눔 모델, `read_seat` 그대로(白 채우기 포함).
사진마다 가장 낮은 확신도(손패·떼어 둔 패·울기)와 정답 여부를 적고, 기준값별로 막히는 수를 센다. 채운 白 은 늘 막히므로 따로 센다.
  python -I -X utf8 experiments/tile_classifier/server_bench/conf_check.py
결과 data/det/conf_check.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.argv = [sys.argv[0], "--r2"]
from rules_core import rv, st  # noqa: E402,F401
from app import local_read as lr  # noqa: E402
from det_eval import hr, hy, sg  # noqa: E402

CUTS = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    meta = json.loads((HERE / "meta.json").read_text(encoding="utf-8"))
    truth = {s["name"]: s for s in sg.eval_scenes() if s["hand"] is not None}
    readers: dict = {}
    rows = []
    for p in meta["photos"]:
        s = truth.get(p["name"])
        if s is None:
            continue
        k = (p["det"], p["part"])
        r = readers.setdefault(k, lr.LocalReader(det_model=HERE / "models" / f"det_fold_{p['det']}.onnx", cls_model=HERE / "models" / f"cls_{p['part']}.onnx"))
        o = r.read_seat((HERE / "crops" / f"{p['name']}.jpg").read_bytes(), p["frac"])
        if not o["framed"]:
            print(p["name"][-6:], "틀 못 잡음", flush=True)
            continue
        confs = o["hand_conf"] + o["meld_conf"]
        ok = hr.same(o["hand"], o["melds"], s)
        shape = not o["block"] and hy.check(o["hand"], [m.split() for m in o["melds"]])[0]
        rows.append(dict(name=p["name"], w=2 if not p["name"].startswith("2026") else 1, low=min(confs), ok=ok, shape=shape, filled=o["filled"], confs=confs))
        print(p["name"][-6:], f"최저 {min(confs):.3f}", "맞음" if ok else "틀림", "형태" if shape else "형태 아님", f"채움 {o['filled']}" if o["filled"] else "", flush=True)
    plain = [x for x in rows if not x["filled"] and x["shape"]]
    n = sum(x["w"] for x in plain)
    print(f"\n틀 잡음 {len(rows)}장, 그중 안 채움·형태 통과 {len(plain)}장({n}회), 맞음 {sum(x['w'] * x['ok'] for x in plain)}회, 틀림 {sum(x['w'] * (not x['ok']) for x in plain)}회")
    for c in CUTS:
        blocked = [x for x in plain if x["low"] < c]
        print(f"기준 {c}: 막힘 {sum(x['w'] for x in blocked)}/{n}회(맞는 답 {sum(x['w'] * x['ok'] for x in blocked)}, 틀린 답 {sum(x['w'] * (not x['ok']) for x in blocked)})", [x["name"][-6:] for x in blocked])
    (HERE.parent / "data" / "det" / "conf_check.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
