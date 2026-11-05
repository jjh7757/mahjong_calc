"""[테스트 세트] 10/24 매장 삼각대 15장(장면 5개)으로 자리 판독을 잰다(2026-11-04, 노트북, API 없음). 8회차 최종 판정용.

**이 결과로 규칙·학습을 고치지 않는다.** 합격 기준은 docs/metrics.md 표 1-69 에 미리 적은 것만 쓴다.
정답·장면: experiments/rectify/recheck_test.py TRUTH(NOTES 30), 격자: read_grid_timing_test.dart `_field`(삼각대 위치별, 0~1000 단위).
13:18(131823)은 EXIF 회전이 다른 사진이라 앱 테스트와 같이 뺀다. 검출기는 개발 35장 전부로 학습한 final(테스트 사진은 학습에 없음),
분류기는 운영 것(app/assets, 테스트 사진 학습 안 함).
  규칙 = server_bench/bench.one(자리 크롭), 새 경로 = app.roles.read_roles(hybrid)
  python -I -X utf8 experiments/tile_classifier/server_bench/field_bench.py --det det_final [--obb --rot-cut] [--dry]
결과 data/role/bench/field_<det>[_obb][_rotcut].json. --dry 는 점수를 안 찍고 돌기만 확인.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "speed"))
sys.path.insert(0, str(HERE.parents[1] / "yolo"))
sys.path.insert(0, os.environ.get("RECOGNIZER_REPO", "C:/Users/jjh7757/dev/mahjong-recognizer"))
import hybrid as hy  # noqa: E402
import seat_grow as sg  # noqa: E402
from app import local_read as lr  # noqa: E402
from app import river, roles  # noqa: E402

_spec = importlib.util.spec_from_file_location("server_bench_bench", HERE / "bench.py")
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)
FIELD = HERE.parents[1] / "field_20261024" / "captures"
OUT = HERE.parent / "data" / "role" / "bench"
CLS = Path(os.environ.get("RECOGNIZER_REPO", "C:/Users/jjh7757/dev/mahjong-recognizer")) / "app" / "assets" / "tile-cls-mnv3s.onnx"

GRID_A = dict(x1=300, x2=690, y1=150, y2=830)
GRID_A2 = dict(x1=300, x2=720, y1=150, y2=830)
GRID_B1 = dict(x1=315, x2=760, y1=200, y2=740)
GRID_B2 = dict(x1=355, x2=760, y1=200, y2=740)
SCENES = {  # 장면: (사진들, 격자) — read_grid_timing_test.dart `_field` 와 같다
    "F1229": (["122922"], GRID_A),
    "F1240": (["124007"], GRID_A2),
    "F대삼원": (["125053", "130533", "131210", "132647", "133011", "133620", "134323", "135148"], GRID_A),
    "F1400": (["135912", "140302", "140750", "140918"], GRID_B1),
    "F1434": (["143443"], GRID_B2),
}


def truth() -> dict:
    src = (HERE.parents[1] / "rectify" / "recheck_test.py").read_text(encoding="utf-8")
    block = src[src.index("TRUTH = {"):src.index("}\n", src.index("TRUTH = {")) + 1]
    t = eval(block.split("=", 1)[1])  # 상수 dict 리터럴
    return {k: dict(side=v[0], hand=v[2].split(), melds=[re.sub(r"[\[\]()]", "", m) for m in v[3]]) for k, v in t.items()}


def judge(hand: list[str], melds: list[str], block: bool, s: dict) -> tuple[bool, bool]:
    key = lambda ms: sorted(" ".join(sorted(m.split())) for m in ms)
    ok = bool(hand) and sorted(hand) == sorted(s["hand"]) and key(melds) == key(s["melds"])
    auto = bool(hand) and not block and hy.check(hand, [m.split() for m in melds])[0]
    return ok, auto


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--det", required=True, help="server_bench/models/<det>.onnx (예: det_final, det_r7_final)")
    ap.add_argument("--obb", action="store_true")
    ap.add_argument("--rot-cut", action="store_true")
    ap.add_argument("--clean", action="store_true", help="서버 정리(가는 조각 버리기 + 안깡 묶기)")
    ap.add_argument("--dry", action="store_true", help="점수를 안 찍고 돌기만 확인")
    ap.add_argument("--recolored", action="store_true", help="색 바꾼 테스트(make_recolor_test.py, captures_recolor)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.obb:
        import obb_detect

        obb_detect.install(bench, lr, river, False, a.rot_cut, sliver=a.clean, kan=a.clean)
    meta = json.loads((HERE / "meta.json").read_text(encoding="utf-8"))
    det_path = HERE / "models" / f"{a.det}.onnx"
    reader = lr.LocalReader(det_model=det_path, cls_model=CLS)
    det = bench.Det(det_path, 2)
    cls = bench.Cls(CLS, meta, 2)
    T = truth()
    rows, tot = {}, dict(n=0, rule_ok=0, rule_bad=0, hyb_ok=0, hyb_bad=0)
    for scene, (photos, grid) in SCENES.items():
        s = T[scene]
        for ph in photos:
            path = (FIELD.parent / "captures_recolor" if a.recolored else FIELD) / f"20261024_{ph}" / "original.jpg"
            im = Image.open(path).convert("RGB")
            crop = sg.crop(im, sg.seat_box(grid, s["side"], 40), s["side"])
            import io

            buf = io.BytesIO()
            crop.save(buf, "JPEG", quality=92)
            det.memo = {}
            rule = bench.one(buf.getvalue(), det, cls, sg.hand_frac(grid, s["side"]))
            r_ok, r_auto = judge(rule["hand"], rule["melds"], rule["block"], s)
            o = roles.read_roles(reader, path.read_bytes(), s["side"], grid, "hybrid")
            hand = [t["tile"] for t in o["tiles"]] + ([o["separate_tile"]["tile"]] if o["separate_tile"] else [])
            melds = [" ".join(m["tiles"]) for m in o["melds"]]
            h_ok, h_auto = judge(hand, melds, o.get("block", False), s)
            rows[ph] = dict(scene=scene, rule=dict(hand=rule["hand"], melds=rule["melds"], ok=r_ok, auto=r_auto),
                            hybrid=dict(hand=hand, melds=melds, ok=h_ok, auto=h_auto, ms=o["ms"]))
            tot["n"] += 1
            tot["rule_ok"] += r_ok
            tot["rule_bad"] += r_auto and not r_ok
            tot["hyb_ok"] += h_ok
            tot["hyb_bad"] += h_auto and not h_ok
            if not a.dry:
                print(ph, scene, "규칙", "O" if r_ok else "X", "hybrid", "O" if h_ok else "X", flush=True)
    if a.dry:
        print("돌기 확인:", tot["n"], "장 처리(점수는 안 찍음)")
        return
    print(f"--- 테스트 /{tot['n']}: 규칙 {tot['rule_ok']}(틀린 자동 반영 {tot['rule_bad']}) | hybrid {tot['hyb_ok']}(틀린 자동 반영 {tot['hyb_bad']})")
    tag = a.det + ("_obb" if a.obb else "") + ("_rotcut" if a.rot_cut else "") + ("_clean" if a.clean else "") + ("_recolored" if a.recolored else "")
    (OUT / f"field_{tag}.json").write_text(json.dumps(dict(total=tot, rows=rows), ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
