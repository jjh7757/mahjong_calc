"""패산 위 표시패 여러 장 읽기(서버 local_read.wall_run, 깡도라) 확인 — 화료 사진을 read_wall 로 읽어 사진 라벨과 맞댄다(2026-11-16).

  python -X utf8 experiments/tile_classifier/wall_run_check.py v1114     # 11-14 매장(개발): 사진 라벨 = data/v1114/role 의 wall 상자
  python -X utf8 experiments/tile_classifier/wall_run_check.py test      # 테스트 세트(B·C·D + 10-31 + 11-07, seat_grow.eval_scenes): 정답 = 장면의 dora

줄마다: 첫 장(고치기 전과 같은 답) / 더해진 장 / 사진의 패산 위 표시패. "더해진 장" 이 사진에 없으면 헛 추가.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REC = Path(r"C:\Users\jjh7757\dev\mahjong-recognizer")
sys.path.insert(0, str(REC))
sys.path.insert(0, str(ROOT / "experiments" / "speed"))
from app import local_read as lr  # noqa: E402


def v1114():
    cap = ROOT / "experiments" / "visit_20261114" / "captures"
    ims = {}
    for sp in ("train", "dev"):
        for im in json.loads((HERE / "data" / "v1114" / "role" / f"labels_{sp}.json").read_text(encoding="utf-8"))["images"]:
            if im["kind"] == "win":
                ims[im["id"].split("/")[1].replace("win_", "")] = im
    for t, im in sorted(ims.items()):
        d = cap / f"20261114_{t}"
        loc = json.loads((d / "locate.json").read_text(encoding="utf-8")) if (d / "locate.json").exists() else None
        if not loc or not loc.get("center"):
            continue
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        y1, x1, y2, x2 = loc["center"]["box"]
        yield t, (d / "original.jpg").read_bytes(), {"x1": x1, "x2": x2, "y1": y1, "y2": y2}, meta.get("grid_src"), sorted(it["tile"] or "?" for it in im["items"] if it["role"] == "wall")


def test():
    """테스트 세트. 패산 위 표시패 정답이 따로 없어, 참고로 앱이 저장한 label.json 의 표시패(리치 화료면 탁자 위 짝일 수 있음)를 옆에 적는다.
    여기서 볼 것은 '더해진 장' 이 생기는 장면 — 생기면 사진을 열어 본다."""
    import seat_grow as sg

    for s in sg.eval_scenes():
        lab = s["path"].parent / "label.json"
        ref = []
        if lab.exists():
            j = json.loads(lab.read_text(encoding="utf-8"))
            ref = list(j.get("dora_indicators") or []) + list(j.get("ura_indicators") or [])
            if j.get("riichi"):
                ref = ["(리치)"] + ref
        g = {k: s["grid"][k] for k in ("x1", "x2", "y1", "y2")}
        yield s["name"], s["path"].read_bytes(), g, "saved", ref


def run(rows) -> None:
    reader = lr.LocalReader()
    c = Counter()
    for name, jpeg, grid, src, truth in rows:
        o = reader.read_wall(jpeg, None, grid, src)
        got = [i["tile"] for i in o["indicators"]]
        first, extra = got[:1], got[1:]
        left = list(truth)
        for t in got:
            if t in left:
                left.remove(t)
        bad_extra = [t for t in extra if t not in truth or got.count(t) > truth.count(t)]
        c["n"] += 1
        c["extra_scenes"] += bool(extra)
        c["extra_false_scenes"] += bool(bad_extra)
        c["all_found"] += bool(truth) and not left and len(got) == len(truth)
        c["has_truth"] += bool(truth)
        c["multi_truth"] += len(truth) > 1
        c["multi_found"] += len(truth) > 1 and not left and len(got) == len(truth)
        print(f"{name:28s} 첫 장 {first} 더해진 장 {extra}{' ← 헛 추가 ' + str(bad_extra) if bad_extra else ''} | 사진 {truth}", flush=True)
    print(dict(c))


if __name__ == "__main__":
    run({"v1114": v1114, "test": test}[sys.argv[1]]())
