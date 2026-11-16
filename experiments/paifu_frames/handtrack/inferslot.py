"""들어간 칸을 안 보고 추론하기 — 시작 손패(칸 순서) + 버린 패 종류 · 쯔모기리 여부 · 나간 칸 + 끝 손패만으로
매 순 손패가 하나로 정해지나(2026-11-16 밤, 사용자 "첫 손패를 정하고 버린 패를 보고 몇 번째 버렸고 몇 번째에 넣었는지 추론").
계획서 3단계 "추가 6". 영상·모델·토큰 없음 — 계산만.

  python -X utf8 inferslot.py <판 id> <고친 판정 파일…> [--max-branches N] [--verbose]

정답 기록 = 판정을 replay2 로 굴린 가지. 시작 손패 정답이 없어 가지마다 "이것이 정답" 이라 치고 따로 센다(startknown.py 와 같은 가정 계산).
모형: 줄 = 종류의 순서 목록. 손에서 낸 차례는 관측한 칸 k 의 패가 버린 패 종류여야 하고, 뽑은 패는 아무 칸에나 들어갈 수 있다.
뽑은 패 종류는 "끝 손패 + 손에서 낸 버림 + 울기 몫 − 시작 손패" 묶음 안에서 아무거나. 뽑기 없이 옮기는 동작은 없다고 본다.
조건: B 종류 묶음만(시작·끝 손패 + 쯔모기리 여부) / C + 시작 줄 순서 + 나간 칸 / D + 끝 손패 공개 순서 / E2·E1·E0 D + 들어간 칸 정답 ±2·±1칸·정확히.
F·G(결과를 본 뒤 더함) = C·D + "뽑은 패는 양옆과 정렬이 맞는 자리에만 들어간다"(무늬 묶음 순서·숫자 방향은 시작 줄에서 읽음, 자패끼리는 순서 안 봄).
"""
from __future__ import annotations

import argparse
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import replay2 as r2  # noqa: E402

VARIANTS = ["B", "C", "D", "F", "G", "E2", "E1", "E0"]
HIST_CAP = 300_000


def unroll(log) -> list:
    ent = []
    while log is not None:
        log, e = log
        ent.append(e)
    ent.reverse()
    return ent


def truth_of(eng: r2.Engine, branch) -> dict:
    """가지 하나 → 시작 줄(종류) · 차례별 사건(관측 + 숨긴 정답) · 차례 뒤 줄 · 끝 줄."""
    R_end, D_end, log = branch
    v = eng.view(log)
    ty = {i: r2.norm(t) for i, t in v["types"].items()}
    melds = {e[1]: (e[2], e[3]) for e in unroll(log) if e[0] == "m"}
    T = len(eng.turns)
    rows = {t: tuple(ty.get(i, "?") for i in v["turnR"][t]) for t in v["turnR"]}
    final = tuple(ty.get(i, "?") for i in R_end)
    steps, notes = [], []
    for t in range(1, T + 1):
        row = v["turnR"][t]
        after = rows[t + 1] if t + 1 in rows else final
        discs = v["disc"].get(t, [])
        kind = eng.turns[t - 1]["kind"]
        st = {"t": t, "seg": eng.turns[t - 1]["seg"], "row": rows[t], "after": after}
        if kind == "call":
            ids, _ = melds[t]
            st["kind"] = "call"
            st["out"] = [(row.index(i) + 1, ty.get(i, "?")) for i in ids]
            rest = [i for i in row if i not in ids]
            if discs:
                _, i_, _, _ = discs[0]
                st["x"], st["k"] = ty.get(i_, "?"), rest.index(i_) + 1
        elif not discs:
            st["kind"] = "last"
        else:
            if len(discs) > 1:
                notes.append(f"{t}순 버림 {len(discs)}개 — 첫 것만 씀")
            di, i_, isD, slot = discs[0]
            tile = r2.norm(eng.discs[di]["tile"])
            if isD:
                st.update(kind="tg", x=tile)
            else:
                k = row.index(i_) + 1 if i_ in row else None
                if k is None:
                    notes.append(f"{t}순: 버린 번호가 차례 첫머리 줄에 없음")
                    k = slot
                elif k != slot:
                    notes.append(f"{t}순: 버릴 때 칸 {slot} ≠ 차례 첫머리 줄의 칸 {k}(버리기 전 옮김) — 첫머리 칸을 씀")
                st.update(kind="hand", x=tile, k=k, draw=ty.get(v["drawn"][t], "?"))
        steps.append(st)
    start = tuple(ty.get(i, "?") for i in eng.chunks[0]["ids"])
    return {"start": start, "steps": steps, "final": final, "notes": notes}


def scheme_of(start: tuple, final: tuple) -> dict:
    sch = r2.sort_scheme([t for t in start if t != "?"])
    for t in final:
        if t != "?" and t[1] not in sch["suit_order"]:
            sch["suit_order"].append(t[1])
    return sch


def skey(t: str, sch: dict):
    if t[1] not in sch["suit_order"]:
        return None
    n = 0 if t[1] == "z" else int(t[0])
    return (sch["suit_order"].index(t[1]), n if sch["ascending"] else -n)


def fits(c: str, base: tuple, j: int, sch: dict) -> bool:
    k = skey(c, sch)
    if k is None:
        return True
    if j > 0:
        kl = skey(base[j - 1], sch)
        if kl is not None and kl > k:
            return False
    if j < len(base):
        kr = skey(base[j], sch)
        if kr is not None and k > kr:
            return False
    return True


def in_model(s: dict) -> bool:
    """정답 차례가 모형(칸 k 를 빼고 뽑은 패를 한 칸에 넣기, 그 밖의 옮김 없음)으로 만들어지나."""
    row, after = s["row"], s["after"]
    if s["kind"] == "hand":
        return bool(model_js(row, s["k"], s["draw"], after))
    if s["kind"] == "call":
        ps = {p for p, _ in s["out"]}
        r = tuple(t for i, t in enumerate(row, 1) if i not in ps)
        if "x" in s:
            r = r[:s["k"] - 1] + r[s["k"]:]
        return r == after
    return row == after


def model_js(row: tuple, k: int, c: str, after: tuple) -> list[int]:
    """모형(칸 k 를 빼고 c 를 j칸에)으로 정답 다음 줄이 나오는 j 들. 없으면 모형 밖."""
    base = row[:k - 1] + row[k:]
    return [j + 1 for j in range(len(base) + 1) if base[:j] + (c,) + base[j:] == after]


def infer(tr: dict, variant: str, jfix: dict | None = None) -> dict:
    """jfix = {차례: [들어간 칸…]} 을 주면 그 차례의 들어간 칸을 그 값으로 못 박는다(checknode.py)."""
    steps, start, final = tr["steps"], tr["start"], tr["final"]
    slots = variant != "B"
    win = {"E2": 2, "E1": 1, "E0": 0}.get(variant)
    sch = scheme_of(start, final) if variant in ("F", "G") else None
    canon = (lambda r: r) if slots else (lambda r: tuple(sorted(r)))
    pool = Counter(s["draw"] for s in steps if s["kind"] == "hand")
    c_start = Counter(start)
    out = Counter()  # 지금까지 손에서 나간 패(버림·울기)
    layers = [{canon(start)}]
    edges = []  # edges[i][child] = {(parent, 뽑은 종류 또는 None)}
    for s in steps:
        cur, nxt = layers[-1], {}
        kind = s["kind"]
        if kind == "hand":
            x, k = s["x"], s["k"]
            js = model_js(s["row"], k, s["draw"], s["after"]) if win is not None else None
            for row in cur:
                if slots:
                    if k > len(row) or row[k - 1] != x:
                        continue
                    base = row[:k - 1] + row[k:]
                else:
                    if x not in row:
                        continue
                    i = row.index(x)
                    base = row[:i] + row[i + 1:]
                for c, n in pool.items():
                    if base.count(c) + out[c] + (x == c) - c_start[c] >= n:  # 이 종류는 이미 다 뽑음
                        continue
                    if not slots:
                        nxt.setdefault(tuple(sorted(base + (c,))), set()).add((row, c))
                        continue
                    if jfix is not None and s["t"] in jfix:
                        rng = [j - 1 for j in jfix[s["t"]] if 1 <= j <= len(base) + 1]
                    elif js is not None:
                        rng = range(max(0, min(js) - 1 - win), min(len(base), max(js) - 1 + win) + 1) if js else ()
                    else:
                        rng = range(len(base) + 1)
                    for j in rng:
                        if jfix is None and j and base[j - 1] == c:
                            continue  # 같은 종류 바로 오른쪽 = 왼쪽에 넣은 것과 같은 줄
                        if sch is not None and not fits(c, base, j, sch):
                            continue
                        nxt.setdefault(base[:j] + (c,) + base[j:], set()).add((row, c))
            out[x] += 1
        elif kind == "call":
            for row in cur:
                if slots:
                    if any(p > len(row) or row[p - 1] != t for p, t in s["out"]):
                        continue
                    ps = {p for p, _ in s["out"]}
                    r2_ = tuple(t for i, t in enumerate(row, 1) if i not in ps)
                else:
                    r2_ = list(row)
                    try:
                        for _, t in s["out"]:
                            r2_.remove(t)
                    except ValueError:
                        continue
                    r2_ = tuple(r2_)
                if "x" in s:
                    if slots:
                        if s["k"] > len(r2_) or r2_[s["k"] - 1] != s["x"]:
                            continue
                        r2_ = r2_[:s["k"] - 1] + r2_[s["k"]:]
                    else:
                        if s["x"] not in r2_:
                            continue
                        i = r2_.index(s["x"])
                        r2_ = r2_[:i] + r2_[i + 1:]
                nxt.setdefault(r2_, set()).add((row, None))
            for _, t in s["out"]:
                out[t] += 1
            if "x" in s:
                out[s["x"]] += 1
        else:  # 쯔모기리 · 마지막 뽑기
            for row in cur:
                nxt.setdefault(row, set()).add((row, None))
        edges.append(nxt)
        layers.append(set(nxt))
    # 끝 조건
    if variant in ("B", "C", "F"):
        accept = set(layers[-1])
    else:
        accept = {final} & layers[-1]
    alive = [None] * len(layers)
    alive[-1] = accept
    for i in range(len(steps) - 1, -1, -1):
        alive[i] = {p for ch in alive[i + 1] for p, _ in edges[i][ch]}
    n_states = sum(len(x) for x in layers)
    res = {"states": n_states, "feasible": bool(accept), "turns": []}
    for i, s in enumerate(steps):
        hands = {tuple(sorted(r)) for r in alive[i]}
        draws = {c for ch in alive[i + 1] for p, c in edges[i][ch] if p in alive[i]} if s["kind"] == "hand" else None
        res["turns"].append({"t": s["t"], "kind": s["kind"], "hands": len(hands), "rows": len(alive[i]),
                             "draws": sorted(draws) if draws else None,
                             "truth_in": canon(s["row"]) in alive[i], "only_truth": hands == {tuple(sorted(s["row"]))}})
    # 판 전체 가지 수(뽑은 종류 순서) — 살아남은 그래프에서만
    hist = {r: {()} for r in alive[0]}
    over = False
    for i in range(len(steps)):
        nh: dict = {}
        tot = 0
        for ch in alive[i + 1]:
            acc = set()
            for p, c in edges[i][ch]:
                if p in hist:
                    acc |= {h + (c,) for h in hist[p]} if c is not None else hist[p]
            nh[ch] = acc
            tot += len(acc)
        hist = nh
        if tot > HIST_CAP:
            over = True
            break
    res["orders"] = None if over else len(set().union(*hist.values())) if hist else 0
    return res


def summarize(res: dict) -> dict:
    tn = res["turns"]
    return {"turns": len(tn), "full": sum(x["hands"] == 1 for x in tn), "max_hands": max((x["hands"] for x in tn), default=0),
            "row_full": sum(x["rows"] == 1 for x in tn), "orders": res["orders"], "truth_in": all(x["truth_in"] for x in tn),
            "hand_turns": sum(x["kind"] == "hand" for x in tn),
            "draw_known": sum(x["kind"] == "hand" and x["draws"] is not None and len(x["draws"]) == 1 for x in tn),
            "states": res["states"]}


def med(v):
    v = [x for x in v if x is not None]
    return statistics.median(v) if v else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game")
    ap.add_argument("judgments", nargs="+")
    ap.add_argument("--max-branches", type=int, default=0)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    od = hc.OUT / a.game
    game, index = hc.jload(od / "game.json"), hc.jload(od / "index.json")
    jud, meta, pre = r2.load_judgments(a.judgments, a.game)
    plan = r2.build_plan(index, jud, list(pre), [])
    eng = r2.Engine(game, index, plan, game.get("start_tiles") or 13, False, r2.LIMIT)
    eng.errors, eng.warns = [], []
    br = eng.run()
    if eng.overflow or not br:
        print("가지 넘침 또는 없음")
        return
    if len(eng.chunks) != 1:
        print("끊김이 있어 못 잼")
        return
    if a.max_branches and len(br) > a.max_branches:
        step = len(br) / a.max_branches
        br = [br[int(i * step)] for i in range(a.max_branches)]
    print(f"{a.game} · 정답으로 칠 가지 {len(br)} · 차례 {len(eng.turns)}")
    allsum = {v: [] for v in VARIANTS}
    outside = 0
    rows_out = []
    shown = False
    for bi, b in enumerate(br):
        tr = truth_of(eng, b)
        bad = [s["t"] for s in tr["steps"] if not in_model(s)]
        if bad or any("?" in s["row"] for s in tr["steps"]):
            outside += 1
            if a.verbose:
                print(f"  가지 {bi}: 모형 밖(차례 {bad}) {tr['notes']}")
            continue
        line = {"branch": bi, "notes": tr["notes"]}
        for v in VARIANTS:
            res = infer(tr, v)
            sm = summarize(res)
            allsum[v].append(sm)
            line[v] = sm | {"per_turn": [(x["t"], x["kind"], x["hands"], x["rows"], x["draws"]) for x in res["turns"]]}
        rows_out.append(line)
        show = a.verbose or not shown
        shown = True
        if show:
            hand_t = [s for s in tr["steps"] if s["kind"] == "hand"]
            print(f"  가지 {bi}: 시작 {' '.join(tr['start'])} · 손에서 낸 차례 " + ", ".join(f"{s['t']}순 {s['x']}(k={s['k']}, 뽑음 {s['draw']})" for s in hand_t))
            for v in VARIANTS:
                sm = line[v]
                print(f"    {v}: 완전 확정 {sm['full']}/{sm['turns']} · 차례 최대 {sm['max_hands']}가지 · 판 전체 순서 {sm['orders']} · 줄까지 하나 {sm['row_full']} · 뽑은 패 확정 {sm['draw_known']}/{sm['hand_turns']} · 정답 살아 있음 {sm['truth_in']} · 상태 {sm['states']}")
                if show:
                    print("       차례별 손패 가지: " + " ".join(f"{t}:{h}" for t, _, h, _, _ in sm["per_turn"]))
    print(f"모형 밖 가지 {outside}/{len(br)} (뺌)")
    print("조건 | 완전 확정 차례 중앙(최소~최대)/차례 | 차례 최대 가지 중앙(최대) | 판 전체 하나인 가지 | 뽑은 패 확정 중앙/손에서 낸 차례 | 정답 살아 있음")
    for v in VARIANTS:
        S = allsum[v]
        if not S:
            continue
        full = [s["full"] for s in S]
        print(f"  {v:>2} | {med(full)} ({min(full)}~{max(full)}) / {S[0]['turns']} | {med([s['max_hands'] for s in S])} ({max(s['max_hands'] for s in S)}) | "
              f"{sum(s['orders'] == 1 for s in S)}/{len(S)} (순서 수 중앙 {med([s['orders'] for s in S])}) | "
              f"{med([s['draw_known'] for s in S])} / {med([s['hand_turns'] for s in S])} | {sum(s['truth_in'] for s in S)}/{len(S)}")
    if a.out:
        hc.jsave(Path(a.out), {"game": a.game, "branches": len(br), "outside": outside, "rows": rows_out})
        print("→", a.out)


if __name__ == "__main__":
    main()
