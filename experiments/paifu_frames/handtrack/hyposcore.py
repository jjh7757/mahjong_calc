"""차례 끝 결과 가설을 한꺼번에 채점 — 쯔모기리 1 + (k, j) n×n 가설에 SAM 2 끝 근거 · 들림 · 자리를 매겨 고름(2026-11-20).

idsolve.py(프레임마다 번호 다시 붙이기)는 자리 거리 비용을 최소로 하니 "손 밑에서 D 를 줄 가운데 끼움" 이 늘 비싸 후보에도 못 든다.
여기서는 끝 결과(버린 k · D 의 끝 자리 j, 또는 쯔모기리)를 가설로 모두 세고, idsolve.Solver 를 한 번 돌린 실행 중 상태를 근거로 쓴다.
SAM 2 다시 안 돌림 · API 0 · 정답은 cmd_score 안에서만(s1.truth_all).

  python -X utf8 hyposcore.py one r16_d03            # 한 차례(정답 안 읽음) — 상위 5 가설 · 근거 · 굳은 번호 · 끝 창
  python -X utf8 hyposcore.py score [--ids a,b]      # idsolve.targets() 전부 → _work/hyposcore_1120/score.json · <id>.json

가설 h: 쯔모기리 = 끝 줄 [1..n], 손 (k, j) = [1..n] 에서 k 를 빼고 D 를 j 번째에 끼움. P_h 를 끝 상자(plan.e_boxes, x 순)에 왼쪽부터 대응.
근거:
  1. C_vis: Solver 실행 내내 vis 였던 번호(한 번도 hid · out · gone 이 아님)는 끝 상자 자리가 굳음 — 어기는 가설 탈락, k 도 못 됨.
     전부 탈락하면 이 제약을 빼고 풀고 unsure.
  2. S_sam: 끝 창(마지막 프레임 + 거꾸로 이어진, 가림 열이 줄 범위와 안 겹치고 줄 상자 n 개인 프레임, 최대 END_N) 프레임마다
     Σ_o w(o) · cov(o, P_h 의 o 상자)(믿을 마스크만) 의 평균. w = 1(안 끊김) · W_BROKEN(손 밑 · 떠남 · D 전 상태에서 한 번이라도 trust 밖).
     D 는 dmasks 가 있는 차례만, D 마스크가 처음 생긴 프레임 뒤의 끊김으로.
  3. S_lift: 버림 시각 ± DISCARD_WIN 의 들림 프레임 수 / LIFT_N(1 에서 자름). 손 = + W_LIFT · lift(k), 쯔모기리 = − W_LIFT · max_o lift(o).
  4. Pos: Σ_{o ≠ D} |끝 예상 상자 cx − 시작 상자 cx| / 장폭, 무게 W_POS.
  총점 = S_sam + S_lift − W_POS · Pos. unsure: 다른 결과의 최고점이 T_MARGIN 안 · 모순 ≥ 2 · C_vis 뺌.
무게 · 규칙은 정답 보기 전에 정함(바꾸지 않음). 떼어 보기(W_BROKEN × W_POS 9조합)는 참고.

idsolve 와 다르게 둔 것(규칙 해석 — 보고에 적음):
  - "떠남" 상태에 idsolve 의 gone(버림으로 정한 번호)도 넣음(idsolve 는 gone 을 out 처럼 outs 에 셈).
  - 끊김은 idsolve.step 이 broken 을 적는 때와 같이 그 프레임의 근거를 셀 때(앞 프레임 끝 상태 기준)에 셈.
  - 모순은 번호 o 마다 한 번(o 가 제 상자 아닌 끝 상자 하나라도 ≥ 0.5 덮으면 1), P_h 에 없는 번호(손 가설의 k, 쯔모기리의 D)는 어느 상자든 모순.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import idsolve as ids  # noqa: E402
import sam2track as s1  # noqa: E402

OUT = hc.WORK / "hyposcore_1120"

END_N = 5           # 끝 창 프레임 수 한도
W_BROKEN = 0.3      # 끊긴 번호의 SAM 2 끝 근거 무게
W_LIFT = 1.0        # 들림 무게
W_POS = 0.15        # 자리 무게(약하게)
T_MARGIN = 0.5      # 다른 결과 최고점이 이 안이면 unsure
CONTRA_COV = 0.5    # 모순: 안 끊긴 믿을 마스크가 제 상자 아닌 끝 상자를 이만큼 덮음
CONTRA_N = 2        # 모순 이만큼이면 unsure
LIFT_N = ids.LIFT_N
DISCARD_WIN = ids.DISCARD_WIN
LEFT_STATES = ("hid", "out", "gone")


class RecSt(dict):
    """Solver.st 를 감싸 상태가 한 번이라도 hid · out · gone 이 된 번호를 적음(한 step 안의 잠깐 바뀜도)."""

    def __init__(self, base: dict, left: set):
        super().__init__(base)
        self.left = left

    def __setitem__(self, k, v):
        if v in LEFT_STATES:
            self.left.add(k)
        super().__setitem__(k, v)


class RecSolver(ids.Solver):
    """idsolve.Solver 에 기록만 더함 — 프레임마다 줄 상자 · 근거, 한 번이라도 떠난 번호, 한 번이라도 끊긴 번호."""

    def __init__(self, U):
        super().__init__(U)
        self.left: set = set()
        self.st = RecSt(self.st, self.left)
        self.rows: dict = {}
        self.evs: dict = {}
        self.ever_broken: dict = {}
        self.d_first = None   # D 마스크가 처음 생긴 프레임

    def row_boxes(self, fi: int):
        r = super().row_boxes(fi)
        self.rows[fi] = r
        return r

    def evidence(self, fi: int, boxes: list):
        ev = super().evidence(fi, boxes)
        self.evs[fi] = ev
        if "D" in ev["bb"] and self.d_first is None:
            self.d_first = fi
        for o in self.ids:
            if o == "D":
                if self.d_first is None or fi <= self.d_first:
                    continue
                bad_state = self.st[o] in ("hid", "out", "pre", "gone")
            else:
                bad_state = self.st[o] in LEFT_STATES
            if bad_state and o not in ev["trust"]:
                self.ever_broken[o] = True
        return ev


# ------------------------------------------------------------------ 근거 모으기
def gather(tid: str) -> dict:
    t0 = time.time()
    U = ids.Turn(tid)
    S = RecSolver(U)
    r = S.run()
    n, F, p = U.n, U.F, U.pitch
    ab = U.p["a_boxes"]
    a_cx = [ids.cxb(b) for b in ab]
    warn = []
    if any(b > c for b, c in zip(a_cx, a_cx[1:])):
        warn.append("a_boxes 가 x 순이 아님")
    eb = sorted(U.p["e_boxes"], key=ids.cxb)
    if len(eb) != n:
        warn.append(f"끝 상자 {len(eb)} ≠ n {n}")
    e_cx = [ids.cxb(b) for b in eb]
    # C_vis: 내내 vis 였던 번호 → 끝 상자 자리
    locked = {}
    for o in range(1, n + 1):
        if o in S.left or S.st[o] != "vis":
            continue
        bi = int(np.argmin([abs(S.x[o] - c) for c in e_cx]))
        locked[o] = bi
    # 끝 창
    lo = min(b[0] for b in ab) - p
    hi = max(b[2] for b in ab) + p
    win = [F - 1]
    fi = F - 2
    while len(win) < END_N and fi >= 1:
        bs = S.rows.get(fi)
        if bs is None or len(bs) != n or fi not in S.evs:
            break
        if any(o1 > lo and o0 < hi for o0, o1 in U.occ[fi]):
            break
        win.append(fi)
        fi -= 1
    # 번호 무게
    has_d = U.DM is not None
    broken = {o: bool(S.ever_broken.get(o)) for o in S.ids}
    # 들림(버림 시각 둘레)
    lift = {}
    for o in S.ids:
        c = sum(1 for f in S.lift_frames[o] if DISCARD_WIN[0] <= U.ms[f] - U.disc_ms <= DISCARD_WIN[1])
        lift[o] = min(1.0, c / LIFT_N)
    # 끝 창 덮음: cw[fi][o][i] = 믿을 마스크 o 의 끝 상자 i 덮음
    cw = []
    for f in win:
        ev = S.evs[f]
        m = {}
        for o in S.ids:
            if o == "D" and not has_d:
                continue
            if o not in ev["trust"]:
                continue
            m[o] = [ev["cov"].get((o, i), 0.0) for i in range(len(eb))]
        cw.append(m)
    last = cw[0]
    # 가설
    hyps = []
    base = list(range(1, n + 1))
    cands = [("tsumogiri", None, None, base)]
    for k in range(1, n + 1):
        rest = [o for o in base if o != k]
        for j in range(1, n + 1):
            cands.append(("hand", k, j, rest[: j - 1] + ["D"] + rest[j - 1:]))
    max_lift = max(lift[o] for o in range(1, n + 1))
    for kind, k, j, P in cands:
        alive = all(i < len(P) and P[i] == o for o, i in locked.items())
        s_full = s_brk = 0.0
        for m in cw:
            for i, o in enumerate(P):
                if o not in m or i >= len(eb):
                    continue
                if broken[o]:
                    s_brk += m[o][i]
                else:
                    s_full += m[o][i]
        s_full /= len(cw)
        s_brk /= len(cw)
        s_lift = W_LIFT * lift[k] if kind == "hand" else -W_LIFT * max_lift
        pos = sum(abs(e_cx[i] - a_cx[o - 1]) / p for i, o in enumerate(P) if o != "D" and i < len(e_cx))
        where = {o: i for i, o in enumerate(P)}
        contra = []
        for o, cv in last.items():
            if broken[o]:
                continue
            bad = [i for i, c in enumerate(cv) if c >= CONTRA_COV and where.get(o) != i]
            if bad:
                contra.append([str(o), bad[0] + 1, round(cv[bad[0]], 2)])
        hyps.append({"kind": kind, "k": k, "j": j, "P": [str(o) for o in P], "alive": alive,
                     "s_full": s_full, "s_brk": s_brk, "s_lift": s_lift, "pos": pos, "contra": contra})
    return {"id": tid, "n": n, "hyps": hyps, "locked": {str(o): i + 1 for o, i in locked.items()},
            "win": win, "win_ms": [hc.mss(U.ms[f]) for f in win], "F": F,
            "broken": [str(o) for o, b in broken.items() if b], "has_d": has_d, "d_first": S.d_first,
            "lift": {str(o): v for o, v in lift.items() if v},
            "idsolve": {"kind": r["kind"], "k": r["k"], "j": r["j"], "unsure": r["unsure"], "unsure_why": r["unsure_why"]},
            "warn": warn, "sec": round(time.time() - t0, 1)}


# ------------------------------------------------------------------ 고르기(무게만 바꿔 다시 고를 수 있게)
def total(h: dict, wb: float, wp: float) -> float:
    return h["s_full"] + wb * h["s_brk"] + h["s_lift"] - wp * h["pos"]


def choose(G: dict, wb: float = W_BROKEN, wp: float = W_POS) -> dict:
    pool = [h for h in G["hyps"] if h["alive"]]
    relaxed = not pool
    if relaxed:
        pool = list(G["hyps"])
    sc = sorted(((total(h, wb, wp), h) for h in pool), key=lambda t: -t[0])
    best_s, best = sc[0]
    second = sc[1] if len(sc) > 1 else (None, None)
    why = []
    if second[1] is not None and best_s - second[0] < T_MARGIN:
        why.append(f"차점 {second[1]['kind'][:4]} {second[1]['k']}·{second[1]['j']} 이 {best_s - second[0]:.2f} 차(< {T_MARGIN})")
    if len(best["contra"]) >= CONTRA_N:
        why.append(f"모순 {len(best['contra'])}: " + ", ".join(f"{o}→상자{i}({c})" for o, i, c in best["contra"]))
    if relaxed:
        why.append("C_vis 로 모든 가설 탈락 — 제약 빼고 풂")
    return {"kind": best["kind"], "k": best["k"], "j": best["j"], "score": best_s, "unsure": bool(why), "unsure_why": why,
            "top": [(s, h) for s, h in sc[:10]], "relaxed": relaxed}


def hrow(s: float, h: dict, wb: float = W_BROKEN, wp: float = W_POS) -> dict:
    return {"kind": h["kind"], "k": h["k"], "j": h["j"], "total": round(s, 3), "S_sam": round(h["s_full"] + wb * h["s_brk"], 3),
            "s_full": round(h["s_full"], 3), "s_brk": round(h["s_brk"], 3), "S_lift": round(h["s_lift"], 3),
            "pos": round(h["pos"], 2), "pos_term": round(-wp * h["pos"], 3), "contra": h["contra"], "alive": h["alive"], "P": h["P"]}


def fmt_ans(x: dict) -> str:
    return f"{(x['kind'] or '-')[:4]} {x['k']}·{x['j']}"


# ------------------------------------------------------------------ 명령
def cmd_one(a):
    G = gather(a.id)
    c = choose(G)
    print(f"[{a.id}] n {G['n']} · 프레임 {G['F']} · {G['sec']}초 {' · 경고 ' + ' / '.join(G['warn']) if G['warn'] else ''}")
    print("C_vis 굳은 번호(번호→끝 상자):", " ".join(f"{o}→{i}" for o, i in G["locked"].items()) or "없음")
    print("끝 창 프레임:", ", ".join(f"{f}({m})" for f, m in zip(G["win"], G["win_ms"])))
    print("끊긴 번호:", " ".join(G["broken"]) or "없음", "| D 마스크:", "있음(첫 프레임 " + str(G["d_first"]) + ")" if G["has_d"] else "없음",
          "| 들림:", " ".join(f"{o}:{v:.1f}" for o, v in G["lift"].items()) or "없음")
    print("상위 5:")
    for s, h in c["top"][:5]:
        r = hrow(s, h)
        print(f"  {fmt_ans(r):16s} 총 {r['total']:+.3f} = S_sam {r['S_sam']:.3f}(안 끊김 {r['s_full']:.3f} · 끊김 {r['s_brk']:.3f}) + S_lift {r['S_lift']:+.2f}"
              f" − 자리 {r['pos']:.2f}×{W_POS} | 모순 {r['contra']}{'' if r['alive'] else ' | C_vis 탈락'}")
    print("hyposcore 답:", fmt_ans(c), "| unsure:", c["unsure_why"] or "아님")
    i = G["idsolve"]
    print("idsolve 답:", fmt_ans(i), "| unsure:", i["unsure"])
    OUT.mkdir(parents=True, exist_ok=True)
    hc.jsave(OUT / f"{a.id}.json", dump(G, c), indent=None)


def dump(G: dict, c: dict) -> dict:
    return {**{k: v for k, v in G.items() if k != "hyps"}, "answer": {k: c[k] for k in ("kind", "k", "j", "score", "unsure", "unsure_why", "relaxed")},
            "top10": [hrow(s, h) for s, h in c["top"]]}


ABL_WB = (0.0, 0.3, 1.0)
ABL_WP = (0.0, 0.15, 0.5)


def cmd_score(a):
    t_all = time.time()
    truth = s1.truth_all()
    OUT.mkdir(parents=True, exist_ok=True)
    tids = a.ids.split(",") if a.ids else ids.targets()
    rows, Gs = [], {}
    for tid in tids:
        u = truth.get(tid)
        if u is None or u["kind"] not in ("hand", "tsumogiri"):
            continue
        G = gather(tid)
        Gs[tid] = (G, u)
        c = choose(G)
        hc.jsave(OUT / f"{tid}.json", dump(G, c), indent=None)
        hk, hj = ids.grade(c, u)
        I = G["idsolve"]
        ik, ij = ids.grade(I, u)
        row = {"id": tid, "truth": [u["kind"], u.get("k_id"), u.get("j_closed")],
               "hyposcore": [c["kind"], c["k"], c["j"]], "k_ok": hk, "j_ok": hj, "both": hk and hj, "unsure": c["unsure"],
               "unsure_why": c["unsure_why"], "silent_wrong": (not c["unsure"]) and not (hk and hj),
               "idsolve": [I["kind"], I["k"], I["j"]], "i_k": ik, "i_j": ij, "i_both": ik and ij, "i_unsure": I["unsure"],
               "i_silent_wrong": (not I["unsure"]) and not (ik and ij),
               "agree": (not c["unsure"]) and (not I["unsure"]) and (c["kind"], c["k"], c["j"]) == (I["kind"], I["k"], I["j"]),
               "locked": G["locked"], "win": G["win"], "broken": G["broken"], "lift": G["lift"], "sec": G["sec"],
               "truth_rank": next((ri + 1 for ri, (s, h) in enumerate(sorted(((total(h, W_BROKEN, W_POS), h) for h in G["hyps"]), key=lambda t: -t[0]))
                                   if all(ids.grade(h, u))), None),
               "truth_alive": any(h["alive"] and all(ids.grade(h, u)) for h in G["hyps"])}
        rows.append(row)
        mk = lambda ok, un: "✓" if ok else ("?" if un else "✗")  # noqa: E731
        print(f"{tid:9s} 정답 {u['kind'][:4]} {u.get('k_id')}·{u.get('j_closed')} | idsolve {fmt_ans(I)} {mk(row['i_both'], I['unsure'])}"
              f" | hyposcore {fmt_ans(c)} {mk(row['both'], c['unsure'])} (정답 순위 {row['truth_rank']}{'' if row['truth_alive'] else ' · C_vis 탈락'})"
              f"{' unsure: ' + ' / '.join(c['unsure_why'])[:150] if c['unsure'] else ''} [{G['sec']}초]", flush=True)
    tot = {}
    groups = (("all", rows), ("hand", [r for r in rows if r["truth"][0] == "hand"]), ("tsumogiri", [r for r in rows if r["truth"][0] == "tsumogiri"]),
              ("r16_d03", [r for r in rows if r["id"] == "r16_d03"]), ("r16_d13", [r for r in rows if r["id"] == "r16_d13"]),
              ("r17_d11", [r for r in rows if r["id"] == "r17_d11"]))
    for name, sel in groups:
        tot[name] = {"n": len(sel),
                     "hyposcore": {"both": sum(r["both"] for r in sel), "k": sum(r["k_ok"] for r in sel), "j": sum(r["j_ok"] for r in sel),
                                   "unsure": sum(r["unsure"] for r in sel), "unsure_and_right": sum(r["unsure"] and r["both"] for r in sel),
                                   "silent_wrong": sum(r["silent_wrong"] for r in sel)},
                     "idsolve": {"both": sum(r["i_both"] for r in sel), "k": sum(r["i_k"] for r in sel), "j": sum(r["i_j"] for r in sel),
                                 "unsure": sum(r["i_unsure"] for r in sel), "unsure_and_right": sum(r["i_unsure"] and r["i_both"] for r in sel),
                                 "silent_wrong": sum(r["i_silent_wrong"] for r in sel)},
                     "agree": {"n": sum(r["agree"] for r in sel), "right": sum(r["agree"] and r["both"] for r in sel)}}
    for k_, v in tot.items():
        print(k_, v)
    # 떼어 보기
    abl = []
    for wb in ABL_WB:
        for wp in ABL_WP:
            hb = sw = un = 0
            for tid, (G, u) in Gs.items():
                c = choose(G, wb, wp)
                ok = all(ids.grade(c, u))
                hb += ok and u["kind"] == "hand"
                sw += (not c["unsure"]) and not ok
                un += c["unsure"]
            abl.append({"W_BROKEN": wb, "W_POS": wp, "hand_both": hb, "silent_wrong": sw, "unsure": un})
            print(f"W_BROKEN {wb} · W_POS {wp}: 손 둘 다 맞음 {hb} · 조용한 틀림 {sw} · unsure {un}")
    sec = round(time.time() - t_all, 1)
    print(f"걸린 시간 {sec}초")
    hc.jsave(OUT / "score.json", {"totals": tot, "rows": rows, "ablation": abl, "sec": sec,
                                  "consts": {k_: globals()[k_] for k_ in ("END_N", "W_BROKEN", "W_LIFT", "W_POS", "T_MARGIN", "CONTRA_COV", "CONTRA_N",
                                                                           "LIFT_N", "DISCARD_WIN")}}, indent=1)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    q = sp.add_parser("score")
    q.add_argument("--ids")
    q = sp.add_parser("one")
    q.add_argument("id")
    a = ap.parse_args()
    {"score": cmd_score, "one": cmd_one}[a.cmd](a)


if __name__ == "__main__":
    main()
