"""거치 점검(lib/table/mount_check.dart) 결과를 저장된 판독 결과와 맞대 본다(2026-11-13, API 없음, 새 판독 없음).

  flutter test tool/mount_check_measure_test.dart      → results/mount_check.json {변형: {사진: 점검}}
  python -X utf8 experiments/speed/mount_check_report.py

판독 쪽은 이미 잰 회귀 세트 결과를 그대로 읽는다(다시 돌리지 않음):
  정사각형 자르기 orig·sq·sqfit = results/robust_{prod,fold}_sq3_1113.json(표 1-167, 서버 348f0f9)
  회전·축소 orig·rot_*·scale*   = results/robust_prod_meldfix_skip_after_1111.json(서버 348f0f9, 11-11 15:03)
장면 맞음 = 화료자 손패·울기가 정답과 같음(robust_suite.judge 의 ok). 채점 장면 = seat_grow.eval_scenes()(40장).
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import seat_grow as sg  # noqa: E402

R = Path(__file__).parent / "results"
mc = json.loads((R / "mount_check.json").read_text(encoding="utf-8"))
truth = {s["name"]: s for s in sg.eval_scenes()}


def key(ms):
    return sorted(" ".join(sorted(m.split())) for m in ms)


def ok(r, t):
    return bool(r.get("hand")) and sorted(r["hand"]) == sorted(t["hand"]) and key(r.get("melds") or []) == key(t["melds"])


def load(name):
    return json.loads((R / name).read_text(encoding="utf-8"))


SQ = {"prod": load("robust_prod_sq3_1113.json"), "fold": load("robust_fold_sq3_1113.json")}
FULL = {"prod": load("robust_prod_meldfix_skip_after_1111.json")}


def tally(variants, src, item):
    """항목(item) 판정별 [장면 수, 틀린 수]. item=None 이면 전체 판정."""
    out = {}
    for v in variants:
        for n, r in mc.get(v, {}).items():
            if v not in src or n not in src[v] or n not in truth:
                continue
            lv = r["level"] if item is None else r["items"].get(item, "—")
            a = out.setdefault(lv, [0, 0])
            a[0] += 1
            a[1] += not ok(src[v][n], truth[n])
    return {k: f"{v[1]}/{v[0]}" for k, v in sorted(out.items())}


print("== 변형별 전체 판정 수")
for v, rows in mc.items():
    c = {}
    for r in rows.values():
        c[r["level"]] = c.get(r["level"], 0) + 1
    print(f"  {v:10s} {dict(sorted(c.items()))}")

print("== 탁자 전체(frame) 판정별 틀린 장면/장면 — orig·sq·sqfit(표 1-167 결과)")
for m in ("prod", "fold"):
    for vs in (["orig"], ["sq"], ["sqfit"], ["orig", "sq", "sqfit"]):
        print(f"  {m} {'+'.join(vs):14s} {tally(vs, SQ[m], 'frame')}")

ROT = ["orig", "rot_p3", "rot_m3", "rot_p10", "rot_m10", "rot_p25", "rot_m25"]
print("== 기울기(tilt) 판정별 — orig + 회전 6종(prod 11-11)")
print("  ", tally(ROT, FULL["prod"], "tilt"))
for v in ROT:
    print(f"   {v:8s} {tally([v], FULL['prod'], 'tilt')}")

print("== 패 크기(size) 판정별 — orig·scale08·scale06(prod 11-11)")
for v in ("orig", "scale08", "scale06"):
    px = [r["felt_px"] for r in mc[v].values() if r.get("felt_px")]
    print(f"   {v:8s} {tally([v], FULL['prod'], 'size')} 펠트 px {min(px)}~{max(px)}")

print("== 전체 판정별(위 변형 모두, prod)")
print("  ", tally(["sq", "sqfit"], SQ["prod"], None), "(sq·sqfit)")
print("  ", tally(ROT + ["scale08", "scale06"], FULL["prod"], None), "(orig·회전·축소)")

ms = sorted(r["ms"] for rows in mc.values() for r in rows.values())
print(f"== 점검 시간(PC, 디코딩 뺌) 중앙 {statistics.median(ms)} / p90 {ms[int(len(ms) * 0.9)]} / 최대 {ms[-1]} ms, n={len(ms)}")
if len(sys.argv) > 1:
    for n, r in mc[sys.argv[1]].items():
        print(n, r["level"], r["items"], r["touch"], r["room"], r.get("tilt"), r.get("felt_px"))
