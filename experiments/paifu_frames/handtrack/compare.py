"""두 판정(v2 사건 목록)을 구간마다 대조한다.

  python -X utf8 compare.py <판 id> --a <파일…> --b <파일…> [--out 폴더] [--name 이름]

판정 없는 구간은 replay2 와 같게 채운다(손 안 들어온 구간 = 사건 없음 / 강에 새 패면 자동 쯔모기리, 손 들어왔는데 판정 없음 = "판정 없음").
결과: <폴더 = results/handtrack/<판>>/compare_<이름>.json · .txt

구간마다:
  확정 일치 = 사건 종류 순서가 같고, 모든 칸이 한 값이며 서로 같고, end_hidden·shuffle·unknown 이 없음
  느슨한 일치 = 종류 순서 같음 / 버림이 D 인지 R 인지 같음 / 버린 칸(후보 집합) 같음 / 들어간 칸(후보 집합) 같음 / 후보 집합이 겹침
분모 = 화료자 차례가 있는 구간(둘 중 하나라도 draw·discard·call 이 있는 구간). 판 단위 "끊김 0" = 분모의 모든 구간이 확정 일치.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
from replay2 import build_plan, cands, ev_str, load_judgments, meld_cands  # noqa: E402

TURN_KINDS = {"draw", "discard", "call"}
METRICS = ["exact", "kinds", "dr", "out", "in", "overlap"]
METRIC_KO = {"exact": "확정 일치", "kinds": "종류 순서 같음", "dr": "버림 D/R 같음", "out": "버린 칸 같음", "in": "들어간 칸 같음",
             "overlap": "후보 겹침"}


def fields(e: dict) -> list[set]:
    """사건의 칸 값들을 후보 집합 목록으로."""
    k = e.get("kind")
    if k == "discard":
        s = set(cands(e.get("what")))
        if e.get("end_hidden"):
            s = {f"{x}+끝가림" for x in s}
        return [s]
    if k == "place":
        return [set(cands(e.get("pos")))]
    if k == "move":
        return [set(cands(e.get("from"))), set(cands(e.get("to")))]
    if k == "shuffle":
        return [set(cands(e.get("pos")))]  # shuffle 은 칸 목록 자체를 한 집합으로(겹침 비교용)
    if k == "call":
        return [{tuple(sorted(m)) for m in meld_cands(e.get("meld_pos"))}]
    return []


def dr(e: dict) -> frozenset:
    s = {"D" if x == "D" else "R" for x in cands(e.get("what"))}
    if e.get("end_hidden"):
        s.add("R")
    return frozenset(s)


def compare_seg(ea: list | None, eb: list | None) -> dict:
    if ea is None or eb is None:
        return {m: False for m in METRICS}
    ka, kb = [e.get("kind") for e in ea], [e.get("kind") for e in eb]
    kinds = ka == kb
    hard = any(e.get("kind") in ("shuffle", "unknown") or e.get("end_hidden") for e in ea + eb)
    exact = kinds and not hard
    overlap = kinds
    if kinds:
        for x, y in zip(ea, eb):
            fx, fy = fields(x), fields(y)
            for sx, sy in zip(fx, fy):
                if not (len(sx) == 1 and sx == sy):
                    exact = False
                if not (sx & sy):
                    overlap = False
    da = [dr(e) for e in ea if e.get("kind") == "discard"]
    db = [dr(e) for e in eb if e.get("kind") == "discard"]
    oa = [frozenset(fields(e)[0]) for e in ea if e.get("kind") == "discard"]
    ob = [frozenset(fields(e)[0]) for e in eb if e.get("kind") == "discard"]
    ia = [frozenset(fields(e)[0]) for e in ea if e.get("kind") == "place"]
    ib = [frozenset(fields(e)[0]) for e in eb if e.get("kind") == "place"]
    return {"exact": exact, "kinds": kinds, "dr": da == db, "out": oa == ob, "in": ia == ib, "overlap": overlap}


def plan_events(index, jud, label, errors):
    errs, warns = [], []
    plan = build_plan(index, jud, errs, warns)
    errors += [f"{label}: {e}" for e in errs]
    out = {}
    for sp in plan:
        out[sp["seg"]] = {"events": sp["events"], "source": sp["source"], "file": sp.get("file")}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game")
    ap.add_argument("--a", nargs="+", required=True)
    ap.add_argument("--b", nargs="+", required=True)
    ap.add_argument("--out")
    ap.add_argument("--name")
    a = ap.parse_args()
    od = hc.OUT / a.game
    index = hc.jload(od / "index.json")
    errors: list[str] = []
    ja, ma, ea = load_judgments(a.a, a.game)
    jb, mb, eb = load_judgments(a.b, a.game)
    errors += [f"A: {e}" for e in ea] + [f"B: {e}" for e in eb]
    pa = plan_events(index, ja, "A", errors)
    pb = plan_events(index, jb, "B", errors)
    rows, other = [], []
    for s in index["segments"]:
        no = s["seg"]
        A, B = pa[no], pb[no]
        evA = None if A["source"] == "missing" else A["events"]
        evB = None if B["source"] == "missing" else B["events"]
        turn = any(e.get("kind") in TURN_KINDS for e in (evA or []) + (evB or [])) or A["source"] == "missing" or B["source"] == "missing"
        if not turn:
            if not compare_seg(evA, evB)["exact"] and (evA or evB):
                other.append({"seg": no, "a": " · ".join(ev_str(e) for e in evA) or "(없음)", "b": " · ".join(ev_str(e) for e in evB) or "(없음)"})
            continue
        c = compare_seg(evA, evB)
        rows.append({"seg": no, **c, "a_source": A["source"], "b_source": B["source"],
                     "a": "판정 없음" if evA is None else " · ".join(ev_str(e) for e in evA) or "(없음)",
                     "b": "판정 없음" if evB is None else " · ".join(ev_str(e) for e in evB) or "(없음)"})
    n = len(rows)
    rates = {m: {"n": sum(r[m] for r in rows), "of": n, "rate": round(sum(r[m] for r in rows) / n, 3) if n else None} for m in METRICS}
    diff = [r for r in rows if not r["exact"]]
    res = {"game": a.game, "a_files": ma, "b_files": mb, "segments_with_turn": n, "rates": rates,
           "no_break": n > 0 and not diff, "differ": diff, "rows": rows, "other_differ": other, "errors": errors}
    name = a.name or ("+".join(Path(p).stem for p in a.a) + "__vs__" + "+".join(Path(p).stem for p in a.b))
    outd = Path(a.out) if a.out else od
    outd.mkdir(parents=True, exist_ok=True)
    hc.jsave(outd / f"compare_{name}.json", res)
    lines = [f"{a.game} 판정 대조 · A = {', '.join(Path(p).name for p in a.a)} · B = {', '.join(Path(p).name for p in a.b)}",
             f"화료자 차례가 있는 구간 {n}개 (둘 중 하나라도 draw·discard·call, 또는 한쪽 판정 없음)"]
    for m in METRICS:
        r = rates[m]
        lines.append(f"  {METRIC_KO[m]}: {r['n']}/{r['of']}" + (f" ({r['rate']:.0%})" if r["rate"] is not None else ""))
    lines.append(f"판 단위 끊김 0(모든 구간 확정 일치): {'예' if res['no_break'] else '아니오'}")
    lines.append("")
    lines.append("확정 일치가 아닌 구간 (느슨한 일치: 종류/DR/버린 칸/들어간 칸/겹침 — O·X)")
    for r in diff:
        flags = "".join("O" if r[m] else "X" for m in METRICS[1:])
        lines.append(f"구간 {r['seg']:3d} [{flags}]")
        lines.append(f"    A: {r['a']}")
        lines.append(f"    B: {r['b']}")
    if other:
        lines.append("")
        lines.append("차례 없는 구간(분모 밖)에서 다른 것 — move·shuffle 등, 손패 순서에는 영향")
        for r in other:
            lines.append(f"구간 {r['seg']:3d}  A: {r['a']}  |  B: {r['b']}")
    lines += [f"오류: {e}" for e in errors]
    (outd / f"compare_{name}.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n→ {outd / f'compare_{name}.json'}")


if __name__ == "__main__":
    main()
