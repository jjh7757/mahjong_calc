"""pgraph 그래프 + 패 옮김 점검 노드 E(2026-11-17, 계획서 3단계 "추가 12"). pgraph.py 는 r12 · r17 시험 기록이라 안 고치고 노드만 가져다 쓴다.

  python -X utf8 pgraph2.py run <판 id> [--readers AB]      # A · B 를 돌리고(있으면 안 부름), 판독기 일치로 확정될 차례에만 E 를 부름
  python -X utf8 pgraph2.py score <판 id…>                  # 저장된 읽기로 조합 AB · AB+E · BC · BC+E 채점(호출 없음)
그래프: 차례 → 판독기 A · B · C → 규칙 → 맞대기 → **옮김 점검 E** → 사람 → 복원.
E 는 답을 바꾸지 않는다. "판독기 일치" 로 확정된 차례에서 E 가 yes / unsure / 답 없음이면 그 차례를 사람 몫으로 옮길 뿐이다. 리치 뒤 규칙 차례는 안 본다.
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import endmove as em  # noqa: E402
import gemframes as gf  # noqa: E402
import htcommon as hc  # noqa: E402
import pgraph as pg  # noqa: E402

VER, STEP, CROP = 1, 2, 0.55
ARM = f"v{VER}_s{STEP}_c{int(CROP * 100)}"


class S2(pg.S, total=False):
    use_e: bool
    echeck: dict


def e_reads(gid: str, ids: list, call: bool) -> dict:
    """E 답을 읽는다. call 이면 없는 차례만 부른다."""
    have = em.load(gid, ARM)
    todo = [i for i in ids if not (have.get(i) or {}).get("moved")]
    if call and todo:
        from google.genai import types
        ts = {t["id"]: t for t in pg.turns_of(gid)}
        with ThreadPoolExecutor(3) as ex:
            rows = list(ex.map(lambda i: em.one(gf.client(), types, ts[i], VER, STEP, CROP), todo))
        for r in rows:
            have[r["id"]] = r
        order = {i: n for n, i in enumerate(ts)}
        hc.jsave(em.OUT / ARM / f"{gid}.json", {"game": gid, "model": em.MODEL, "arm": ARM, "at": hc.hms(int(time.time() * 1000), date=True),
                                                "rows": sorted(have.values(), key=lambda r: order[r["id"]])})
        print(f"E {gid}: 차례 {len(rows)} · 입력 {sum(r['in'] for r in rows):,} · 출력+생각 {sum(r['out'] + r['think'] for r in rows):,} · {em.dollars(rows):.2f}달러 · 오류 {sum('error' in r for r in rows)}")
    return have


def n_echeck(s: S2) -> dict:
    """판독기 일치로 확정된 차례만 E 에게 보이고, 옮김이 의심되면 사람 몫으로 옮긴다."""
    if not s.get("use_e"):
        return {"echeck": {}}
    ids = [i for i, d in s["decided"].items() if d["src"] == "판독기 일치"]
    E = e_reads(s["game"], ids, s.get("call", False))
    label = {t["id"]: t.get("label") for t in s["turns"]}
    decided, queue, rep = dict(s["decided"]), list(s["queue"]), {}
    for i in ids:
        f = em.flag(E.get(i))
        rep[i] = {"moved": (E.get(i) or {}).get("moved"), "where": (E.get(i) or {}).get("where"), "flag": f}
        if f is not False:
            d = decided.pop(i)
            queue.append({"id": i, "label": label[i], "why": ["옮김 의심(E)" if f else "E 답 없음"], "reads": d["reads"]})
    order = {t["id"]: n for n, t in enumerate(s["turns"])}
    queue.sort(key=lambda q: order[q["id"]])
    return {"decided": decided, "queue": queue, "echeck": rep}


def build():
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph
    g = StateGraph(S2)
    g.add_node("turns", pg.n_turns)
    for r in "ABC":
        g.add_node(f"read_{r}", pg.n_read(r))
    g.add_node("rules", pg.n_rules)
    g.add_node("reconcile", pg.n_reconcile)
    g.add_node("echeck", n_echeck)
    g.add_node("human", pg.n_human)
    g.add_node("rebuild", pg.n_rebuild)
    g.add_edge(START, "turns")
    for r in "ABC":
        g.add_edge("turns", f"read_{r}")
        g.add_edge(f"read_{r}", "rules")
    g.add_edge("rules", "reconcile")
    g.add_edge("reconcile", "echeck")
    g.add_edge("echeck", "human")
    g.add_edge("human", "rebuild")
    g.add_edge("rebuild", END)
    return g.compile(checkpointer=MemorySaver())


def run_graph(gid: str, readers: str, call: bool, use_e: bool, human=None) -> dict:
    from langgraph.types import Command
    app = build()
    cfg = {"configurable": {"thread_id": f"{gid}-{readers}-{'E' if use_e else 'x'}"}}
    st = app.invoke({"game": gid, "readers": readers, "call": call, "use_e": use_e}, cfg)
    if "__interrupt__" in st and human is not None:
        st = app.invoke(Command(resume=human(st["__interrupt__"][0].value["queue"])), cfg)
    return st


def cmd_run(a):
    st = run_graph(a.game, a.readers, True, True)
    q = st["__interrupt__"][0].value["queue"] if "__interrupt__" in st else []
    # 답은 찍지 않는다(사용자가 정답을 적는 중인 판에서도 돌리려고) — 수만 찍고 파일에 적는다.
    print(f"{a.game} · 판독기 {a.readers}+E · 차례 {len(st['turns'])} · 자동 확정 {len(st['decided'])} · 사람에게 {len(q)}"
          f"(그중 E 가 넘긴 것 {sum('E' in ' '.join(d['why']) for d in q)})")
    hc.jsave(pg.OUT / a.game / f"state_{a.readers}E.json", {"decided": st["decided"], "queue": q, "rules": st["rules"], "echeck": st["echeck"], "arm": ARM})


def cmd_score(a):
    truth = hc.jload(pg.BASE / "truth_final.json")
    tot: dict = {}
    for gid in a.games:
        ts = [t for t in pg.turns_of(gid) if t["id"] in truth]
        if not ts:
            print(gid, "정답 없음 — 건너뜀")
            continue
        reads = {"A": pg.load_a(gid, False), "B": pg.load_b(gid, False), "C": pg.load_c(gid)}
        print(f"\n== {gid} · 차례 {len(ts)} · 혼자 맞음: " + " · ".join(f"{r} {sum(pg.right(pg.norm(d.get(t['id'])), truth[t['id']]) for t in ts)}" for r, d in reads.items() if d))
        for combo in ("AB", "BC"):
            if any(reads[r] is None for r in combo):
                continue
            for use_e in (False, True):
                st = run_graph(gid, combo, False, use_e, human=lambda q: {d["id"]: {"kind": truth[d["id"]]["kind"], "k": truth[d["id"]].get("k_id"), "j": truth[d["id"]].get("j_closed")} for d in q})
                auto = {i: d for i, d in st["decided"].items() if i in truth}
                silent = [i for i, d in auto.items() if not pg.right(d, truth[i])]
                e_sent = [i for i, r in (st.get("echeck") or {}).items() if r["flag"] is not False]
                e_none = [i for i in e_sent if st["echeck"][i]["flag"] is None]
                nq = len(st["human"])
                end = sum(pg.right(st["final"][t["id"]], truth[t["id"]]) for t in ts)
                name = combo + ("+E" if use_e else "")
                print(f"  {name:5s}: 자동 확정 {len(auto)}/{len(ts)} · 조용한 틀림 {len(silent)} {silent or ''} · 사람에게 {nq}" + (f"(E 가 넘김 {len(e_sent)} {e_sent}" + (f" · E 답 없음 {e_none}" if e_none else "") + ")" if use_e else "") + f" · 끝 결과 {end}/{len(ts)}")
                c = tot.setdefault(name, {"n": 0, "auto": 0, "silent": 0, "human": 0, "end": 0, "e": 0})
                c["n"] += len(ts); c["auto"] += len(auto); c["silent"] += len(silent); c["human"] += nq; c["end"] += end; c["e"] += len(e_sent)
    print("\n합:")
    for k, v in tot.items():
        print(f"  {k:5s}: 자동 확정 {v['auto']}/{v['n']} · 조용한 틀림 {v['silent']} · 사람에게 {v['human']}({v['human'] / v['n']:.0%})" + (f" · E 가 넘김 {v['e']}" if k.endswith("E") else "") + f" · 끝 결과 {v['end']}/{v['n']}")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run")
    r.add_argument("game")
    r.add_argument("--readers", default="AB")
    c = sp.add_parser("score")
    c.add_argument("games", nargs="+")
    a = ap.parse_args()
    {"run": cmd_run, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    main()
