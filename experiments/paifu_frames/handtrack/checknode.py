"""마지막 점검 노드가 틀린 "들어간 칸" 읽기를 잡아내나(2026-11-16 밤, 사용자 "랭그래프로 마지막에 점검하는 노드").
정답 가지에서 손에서 낸 차례 하나의 들어간 칸만 ±1 · ±2칸 틀리게 넣고(나머지는 정답), 점검 = "시작 줄 + 버린 패 · 나간 칸 + 끝 손패 순서와
모순 없이 굴러가나"(inferslot 조건 D, 뽑은 패 종류는 자유)를 돌린다. 모순이면 잡음, 아니면 못 잡음(손패가 정답과 같으면 해 없음).
  python -X utf8 checknode.py <판 id> <고친 판정 파일…> [--sort]     (--sort = 점검에 "정렬 자리" 도 넣음)
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import inferslot as isl  # noqa: E402
import replay2 as r2  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game")
    ap.add_argument("judgments", nargs="+")
    ap.add_argument("--sort", action="store_true")
    a = ap.parse_args()
    od = hc.OUT / a.game
    game, index = hc.jload(od / "game.json"), hc.jload(od / "index.json")
    jud, meta, pre = r2.load_judgments(a.judgments, a.game)
    eng = r2.Engine(game, index, r2.build_plan(index, jud, list(pre), []), game.get("start_tiles") or 13, False, r2.LIMIT)
    eng.errors, eng.warns = [], []
    br = eng.run()
    var = "G" if a.sort else "D"
    tot = {d: Counter() for d in (1, 2)}
    by_turn: dict = {}
    n_in = 0
    for b in br:
        tr = isl.truth_of(eng, b)
        if any(not isl.in_model(s) for s in tr["steps"]) or any("?" in s["row"] for s in tr["steps"]):
            continue
        hand = [s for s in tr["steps"] if s["kind"] == "hand"]
        truth = {s["t"]: isl.model_js(s["row"], s["k"], s["draw"], s["after"]) for s in hand}
        base = isl.infer(tr, var, truth)
        if not base["feasible"]:
            continue  # 정답이 점검에 걸림(정렬 가정이 틀린 가지)
        n_in += 1
        for s in hand:
            js, n = truth[s["t"]], len(s["after"])
            for delta in (-2, -1, 1, 2):
                jp = (min(js) + delta) if delta < 0 else (max(js) + delta)
                if not 1 <= jp <= n:
                    continue
                res = isl.infer(tr, var, truth | {s["t"]: [jp]})
                if not res["feasible"]:
                    out = "잡음"
                elif all(x["only_truth"] for x in res["turns"]):
                    out = "못 잡음(손패 같음)"
                else:
                    out = "못 잡음(손패 다름)"
                tot[abs(delta)][out] += 1
                by_turn.setdefault((s["t"], abs(delta)), Counter())[out] += 1
    print(f"{a.game} · 점검 = {'D + 정렬 자리' if a.sort else 'D'} · 정답이 점검을 지나는 가지 {n_in}/{len(br)}")
    for d in (1, 2):
        c = tot[d]
        n = sum(c.values())
        print(f"  ±{d}칸 틀린 읽기 {n}건: " + " · ".join(f"{k} {v} ({v / n:.0%})" for k, v in c.most_common()) if n else f"  ±{d}칸: 없음")
    for (t, d), c in sorted(by_turn.items()):
        if d == 1:
            print(f"    {t}순 ±1: {dict(c)}")


if __name__ == "__main__":
    main()
