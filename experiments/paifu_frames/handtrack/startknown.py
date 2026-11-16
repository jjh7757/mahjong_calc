"""시작 손패를 안다면 — replay2 가지를 시작 손패(종류 묶음)로 묶어, 각 시작 후보가 정답이라고 치고 차례별 확정을 다시 센다(2026-11-16).
사용자 "끝까지 추적하면 알 수 있나?" 확인용. 시작 손패 정답은 기록이 없어 후보마다 따로 셈(어느 것이 정답인지 모름).
  python -X utf8 startknown.py <판 id> <판정 파일…> [--widen-place K]
"""
from __future__ import annotations

import argparse
import statistics
from collections import defaultdict

import htcommon as hc
import replay2 as r2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game")
    ap.add_argument("judgments", nargs="+")
    ap.add_argument("--widen-place", type=int, default=0)
    a = ap.parse_args()
    od = hc.OUT / a.game
    game, index = hc.jload(od / "game.json"), hc.jload(od / "index.json")
    jud, meta, pre = r2.load_judgments(a.judgments, a.game)
    plan = r2.build_plan(index, jud, list(pre), [])
    eng = r2.Engine(game, index, plan, game.get("start_tiles") or 13, False, r2.LIMIT, widen=a.widen_place)
    eng.errors, eng.warns = [], []
    br = eng.run()
    if eng.overflow:
        print("가지 넘침", eng.overflow)
        return
    if len(eng.chunks) != 1:
        print("덩어리", len(eng.chunks), "— 첫 덩어리만 시작 손패로 봄")
    groups = defaultdict(list)
    for i, (R, D, log) in enumerate(br):
        v = eng.view(log)
        st = tuple(sorted((eng.tt(v["types"], x) for x in eng.chunks[0]["ids"]), key=r2.tile_sort))
        groups[st].append(i)
    allsum = r2.summarize(r2.aggregate(eng, br, list(range(len(br))), {}), eng)
    print(f"{a.game} widen={a.widen_place} 가지 {len(br)} · 시작 후보 {len(groups)}")
    print(f"  시작 모름: 완전 확정 차례 {allsum['fully_confirmed']}/{allsum['turns']} · 확정 평균 {allsum['confirmed_mean']} 최소 {allsum['confirmed_min']}")
    rows = []
    for st, idx in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        agg = r2.aggregate(eng, br, idx, {})
        s = r2.summarize(agg, eng)
        amb = [(x["t"], x["distinct"]) for x in agg["turns"] if x["n"] and x["distinct"] > 1]
        rows.append((s["fully_confirmed"], s["turns"], s["confirmed_mean"]))
        print(f"  시작 {' '.join(t for t in st if t)} · 가지 {len(idx)} → 완전 확정 {s['fully_confirmed']}/{s['turns']} · 확정 평균 {s['confirmed_mean']} 최소 {s['confirmed_min']} · 남는 차례(가짓수) {amb}")
    fc = [r[0] for r in rows]
    print(f"  시작 후보를 정답으로 칠 때 완전 확정 차례: 중앙 {statistics.median(fc)} · 최소 {min(fc)} · 최대 {max(fc)} (차례 {rows[0][1]})")


if __name__ == "__main__":
    main()
