"""서버 새 경로(/v2/localroles = 사진 전체 + 격자 → 역할 모델 → 자리 판독)를 오프라인으로 잰다(2026-11-04, 노트북, API 없음). metrics 표 1-61.

서버 코드 app/roles.read_roles 를 그대로 부르되 모델은 벤치와 같은 fold ONNX(테스트 사진을 학습에 안 쓴 검출기·분류기)로.
비교: 규칙(bench.one, 자리 크롭) 대 새 경로 hybrid / model. 채점은 score.py 와 같다(B·C·D ×2, /37).
  python -I -X utf8 experiments/tile_classifier/server_bench/role_full_bench.py [--threads 2]
결과 data/role/bench/full_bench.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "speed"))
sys.path.insert(0, str(HERE.parents[1] / "yolo"))
sys.path.insert(0, os.environ.get("RECOGNIZER_REPO", "C:/Users/jjh7757/dev/mahjong-recognizer"))
import hybrid as hy  # noqa: E402
import seat_grow as sg  # noqa: E402
from app import local_read as lr  # noqa: E402
from app import roles  # noqa: E402

_spec = importlib.util.spec_from_file_location("server_bench_bench", HERE / "bench.py")
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)
OUT = HERE.parent / "data" / "role" / "bench"


def drop_oversize(boxes: list, k: float = 1.6) -> list:
    """패보다 너무 큰 상자 버리기: 상자 짧은 변·긴 변의 중앙값(패 폭·높이)의 k 배를 넘으면 패가 아니다(서랍 속 종이·기기 등, 표 1-63).
    눕힌 패는 긴 변·짧은 변으로 재므로 그대로 남는다. 상자가 3개 미만이면 기준을 못 세워 그대로."""
    if len(boxes) < 3:
        return boxes
    tw = sorted(min(b[2], b[3]) for b in boxes)[len(boxes) // 2]
    th = sorted(max(b[2], b[3]) for b in boxes)[len(boxes) // 2]
    return [b for b in boxes if max(b[2], b[3]) <= k * th and min(b[2], b[3]) <= k * tw]


def judge(hand: list[str], melds: list[str], block: bool, s: dict) -> tuple[bool, bool]:
    key = lambda ms: sorted(" ".join(sorted(m.split())) for m in ms)
    ok = bool(hand) and sorted(hand) == sorted(s["hand"]) and key(melds) == key(s["melds"])
    auto = bool(hand) and not block and hy.check(hand, [m.split() for m in melds])[0]
    return ok, auto


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--det", default="det", help="검출기 앞이름: det = 2회차(det_fold_a/b), det_r3 = 3회차 白 증강")
    ap.add_argument("--size-filter", action="store_true", help="검출 뒤 패보다 1.6배 넘게 큰 상자 버리기(규칙·새 경로 모두)")
    ap.add_argument("--obb", action="store_true", help="회전 상자(OBB) ONNX(7회차~): 감싸는 축 상자로 바꿔 서버 코드에 넘김(obb_detect.py)")
    ap.add_argument("--rot-white", action="store_true", help="--obb 와 함께: 흰 비율 거르기를 회전 상자 안에서")
    ap.add_argument("--rot-cut", action="store_true", help="--obb 와 함께: 분류기 크롭을 회전 상자대로 세워 자르기")
    ap.add_argument("--clean", action="store_true", help="--obb 와 함께: 서버 정리(가는 조각 버리기 + 안깡 묶기, 표 1-69)")
    ap.add_argument("--felt-only", action="store_true", help="검출 전에 초록 펠트 밖을 지움(felt_only.py)")
    ap.add_argument("--haku2", action="store_true", help="모서리 白 이 2장 이상 잡히면 퐁 3장으로(haku_pair.py)")
    ap.add_argument("--corner-fix", action="store_true", help="모서리 白 퐁 찾기 흔들림 고치기(corner_fix.py)")
    ap.add_argument("--loose-ctx", action="store_true", help="크롭 밖 떼어 둔 화료패를 역할 모델 판단으로(loose_ctx.py)")
    ap.add_argument("--native", action="store_true", help="어댑터 없이 서버 코드 그대로(11-05 반영판: 자리 검출기 = <det>_fold, 규칙 = LocalReader.read_seat)")
    a = ap.parse_args()
    if a.native and (a.obb or a.clean or a.haku2 or a.corner_fix or a.loose_ctx):
        ap.error("--native 는 어댑터 옵션과 같이 쓰지 않는다")
    if a.obb:
        import obb_detect

        from app import river

        obb_detect.install(bench, lr, river, a.rot_white, a.rot_cut, sliver=a.clean, kan=a.clean)
    if a.size_filter:
        _det, _lr = bench.Det.detect, lr.LocalReader.detect
        bench.Det.detect = lambda self, rgb, low=False: drop_oversize(_det(self, rgb, low))
        lr.LocalReader.detect = lambda self, rgb, low=True: drop_oversize(_lr(self, rgb, low))
    if a.loose_ctx:
        import loose_ctx

        loose_ctx.install(roles)
    if a.corner_fix:
        import corner_fix

        corner_fix.install(lr)
    if a.haku2:
        import haku_pair

        haku_pair.install(lr)
    if a.felt_only:
        import felt_only

        felt_only.install(bench, lr)
    sys.stdout.reconfigure(encoding="utf-8")
    meta = json.loads((HERE / "meta.json").read_text(encoding="utf-8"))
    scenes = {s["name"]: s for s in sg.eval_scenes()}  # 가림·사용자 문제 사진 뺌(seat_grow.EXCLUDED)
    readers: dict = {}
    dets, clss = {}, {}
    rows, tot = {}, Counter()
    for p in meta["photos"]:
        s = scenes.get(p["name"])
        if s is None or s["hand"] is None:
            continue
        w = 2 if not p["name"].startswith("2026") else 1
        key = (p["det"], p["part"])
        fold = HERE / "models" / f"{a.det}_fold_{p['det']}.onnx"
        reader = readers.setdefault(key, lr.LocalReader(threads=a.threads, det_model=fold, cls_model=HERE / "models" / f"cls_{p['part']}.onnx",
                                                        **({"seat_model": fold} if a.native else {"seat_model": None})))
        det = dets.setdefault(p["det"], bench.Det(HERE / "models" / f"{a.det}_fold_{p['det']}.onnx", a.threads))
        cls = clss.setdefault(p["part"], bench.Cls(HERE / "models" / f"cls_{p['part']}.onnx", meta, a.threads))
        det.memo = {}
        if a.native:
            rule = reader.read_seat((HERE / "crops" / f"{p['name']}.jpg").read_bytes(), p["frac"])
        else:
            rule = bench.one((HERE / "crops" / f"{p['name']}.jpg").read_bytes(), det, cls, p["frac"])
        r_ok, r_auto = judge(rule["hand"], rule["melds"], rule["block"], s)
        row = dict(w=w, rule=dict(hand=rule["hand"], melds=rule["melds"], ok=r_ok, auto=r_auto))
        tot["n"] += w
        tot["rule_ok"] += w * r_ok
        tot["rule_bad"] += w * (r_auto and not r_ok)
        jpeg = Path(s["path"]).read_bytes()
        line = f"{p['name'][-6:]} {s['side']} 규칙 {'O' if r_ok else 'X'}"
        for mode in ("hybrid", "model"):
            t0 = time.perf_counter()
            o = roles.read_roles(reader, jpeg, s["side"], s["grid"], mode)
            secs = time.perf_counter() - t0
            hand = [t["tile"] for t in o["tiles"]] + ([o["separate_tile"]["tile"]] if o["separate_tile"] else [])
            melds = [" ".join(m["tiles"]) for m in o["melds"]]
            ok, auto = judge(hand, melds, o.get("block", False), s)
            row[mode] = dict(hand=hand, melds=melds, ok=ok, auto=auto, counts=o["counts"], ms=o["ms"], s=round(secs, 2))
            tot[f"{mode}_ok"] += w * ok
            tot[f"{mode}_bad"] += w * (auto and not ok)
            tot[f"{mode}_framed"] += w * o["framed"]
            line += f" | {mode} {'O' if ok else 'X'} {' '.join(hand)} {melds} {o['counts']} {o['ms']['total']}ms"
        rows[p["name"]] = row
        print(line, flush=True)
    print(f"--- 정답 /{tot['n']}: 규칙 {tot['rule_ok']}(자동 틀림 {tot['rule_bad']}) | hybrid {tot['hybrid_ok']}(틀림 {tot['hybrid_bad']}, 틀 {tot['hybrid_framed']}) | model {tot['model_ok']}(틀림 {tot['model_bad']}, 틀 {tot['model_framed']})")
    (OUT / f"full_bench{'' if a.det == 'det' else '_' + a.det}{'_size' if a.size_filter else ''}{'_rotwhite' if a.rot_white else ''}{'_rotcut' if a.rot_cut else ''}{'_clean' if a.clean else ''}{'_feltonly' if a.felt_only else ''}{'_haku2' if a.haku2 else ''}{'_cornerfix' if a.corner_fix else ''}{'_loosectx' if a.loose_ctx else ''}{'_native' if a.native else ''}.json").write_text(json.dumps(dict(total=dict(tot), rows=rows), ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
