"""점검 → 다시 추론 고리를 끝까지 돌리면 정답에 닿나(2026-11-16 밤, 사용자 "점검 노드 결과를 보내서 추론 다시 하는 방식이면 랭그래프가 좋지 않니").
새로 보는 것 없이(다시 읽기 없음) 점검 결과만으로 고치는 고리의 상한을 모의 계산한다.
  - 읽기: 손에서 낸 차례마다 들어간 칸을 확률 q 로 한 칸 틀리게(±1), 나머지는 정답.
  - 고리의 끝: 읽은 칸 ±1 안에서 점검(시작 줄 + 버린 패 · 나간 칸 + 끝 손패 순서)을 지나는 가설 중 **읽기를 가장 적게 고친 것**.
    같은 수로 고친 가설이 여럿이면 고르게 뽑는다고 봄(정답일 확률 = 정답 수 / 가설 수). 이것이 "모순이 사라질 때까지 고친다" 의 가장 좋은 결과다.
  python -X utf8 loopsim.py <판 id> <고친 판정 파일…> [--n 표본 수] [--seed 0]
"""
from __future__ import annotations

import argparse
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import inferslot as isl  # noqa: E402
import replay2 as r2  # noqa: E402


def best_fix(tr: dict, reads: dict) -> tuple[int, float, int]:
    """(가장 적게 고친 칸 수, 그 가설들 중 정답 손패인 비율, 그 가설 수). 가설 = 줄의 차례별 순서."""
    steps, start, final = tr["steps"], tr["start"], tr["final"]
    pool = Counter(s["draw"] for s in steps if s["kind"] == "hand")
    c_start, out = Counter(start), Counter()
    layer = {start: {0: (1, 1)}}  # 줄 → {고친 수: (가설 수, 그중 정답 손패 수)}
    for s in steps:
        tm = tuple(sorted(s["after"]))
        nxt: dict = {}

        def put(new, cost, n, nt):
            d = nxt.setdefault(new, {})
            a, b = d.get(cost, (0, 0))
            d[cost] = (a + n, b + (nt if tuple(sorted(new)) == tm else 0))

        if s["kind"] == "hand":
            x, k, jr = s["x"], s["k"], reads[s["t"]]
            for row, val in layer.items():
                if k > len(row) or row[k - 1] != x:
                    continue
                base = row[:k - 1] + row[k:]
                trans: dict = {}
                for c, n in pool.items():
                    if base.count(c) + out[c] + (x == c) - c_start[c] >= n:
                        continue
                    for j in (jr - 1, jr, jr + 1):
                        if 1 <= j <= len(base) + 1:
                            new = base[:j - 1] + (c,) + base[j - 1:]
                            add = 0 if j == jr else 1
                            if add < trans.get(new, 9):
                                trans[new] = add
                for new, add in trans.items():
                    for cost, (n, nt) in val.items():
                        put(new, cost + add, n, nt)
            out[x] += 1
        elif s["kind"] == "call":
            ps = {p for p, _ in s["out"]}
            for row, val in layer.items():
                if any(p > len(row) or row[p - 1] != t for p, t in s["out"]):
                    continue
                r = tuple(t for i, t in enumerate(row, 1) if i not in ps)
                if "x" in s:
                    if s["k"] > len(r) or r[s["k"] - 1] != s["x"]:
                        continue
                    r = r[:s["k"] - 1] + r[s["k"]:]
                for cost, (n, nt) in val.items():
                    put(r, cost, n, nt)
            for _, t in s["out"]:
                out[t] += 1
            if "x" in s:
                out[s["x"]] += 1
        else:
            for row, val in layer.items():
                for cost, (n, nt) in val.items():
                    put(row, cost, n, nt)
        layer = nxt
    val = layer.get(final)
    if not val:
        return -1, 0.0, 0
    cost = min(val)
    n, nt = val[cost]
    return cost, nt / n, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game")
    ap.add_argument("judgments", nargs="+")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    od = hc.OUT / a.game
    game, index = hc.jload(od / "game.json"), hc.jload(od / "index.json")
    jud, meta, pre = r2.load_judgments(a.judgments, a.game)
    eng = r2.Engine(game, index, r2.build_plan(index, jud, list(pre), []), game.get("start_tiles") or 13, False, r2.LIMIT)
    eng.errors, eng.warns = [], []
    trs = []
    for b in eng.run():
        tr = isl.truth_of(eng, b)
        if all(isl.in_model(s) for s in tr["steps"]) and not any("?" in s["row"] for s in tr["steps"]):
            trs.append(tr)
    print(f"{a.game} · 모형 안 가지 {len(trs)} · 가지마다 표본 {a.n}")
    for q in (0.2, 0.5):
        rng = random.Random(a.seed)
        tot = Counter()
        after = after_err = fired_ok = 0.0
        for tr in trs:
            hand = [s for s in tr["steps"] if s["kind"] == "hand"]
            truth = {s["t"]: isl.model_js(s["row"], s["k"], s["draw"], s["after"]) for s in hand}
            for _ in range(a.n):
                reads, nerr = {}, 0
                for s in hand:
                    js, n = truth[s["t"]], len(s["after"])
                    jr = min(js)
                    if rng.random() < q:
                        opts = [j for j in (min(js) - 1, max(js) + 1) if 1 <= j <= n]
                        if opts:
                            jr = rng.choice(opts)
                            nerr += 1
                    reads[s["t"]] = jr
                cost, p, nh = best_fix(tr, reads)
                tot["표본"] += 1
                after += p
                if nerr:
                    tot["틀린 읽기"] += 1
                    after_err += p
                    if cost > 0:
                        tot["점검이 울림"] += 1
                        fired_ok += p
                    else:
                        tot["점검이 안 울림(조용한 오답)"] += 1
                else:
                    tot["읽기가 다 맞음"] += 1
        n, ne = tot["표본"], tot["틀린 읽기"]
        print(f"  한 칸 틀릴 확률 {q}: 고리 전 판 전체 맞음 {tot['읽기가 다 맞음'] / n:.0%} → 고리 뒤 {after / n:.0%}"
              f" · 틀린 읽기 {ne}건 중 점검이 울림 {tot['점검이 울림'] / ne:.0%} · 틀린 읽기가 고리 뒤 정답이 됨 {after_err / ne:.0%}"
              f" · 울린 것 중 정답으로 고침 {fired_ok / max(1, tot['점검이 울림']):.0%}")


if __name__ == "__main__":
    main()
