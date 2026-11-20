"""칸 틀 도구로 "쯔모기리 · 줄 그대로" 가르기 — 줄의 칸이 비어 보인 적 있나(2026-11-19 저녁, 계획서 3단계 "추가 52"). API 호출 없음 · 0달러.

  python -X utf8 slotroute.py dev   # 개발 판(r12 · r16 · r17)만: 차례별 신호 · 분포 · 규칙 후보 · "V == 0 AND O <= T" 표(확인 판은 계산도 안 함)
  python -X utf8 slotroute.py       # 전부: 개발 판 → 정한 규칙(아래 RULE 상수) → 확인 판(r19 · r13) 한 번. RULE 이 None 이면 거부

신호(정답 · LLM 답 안 씀, 검출 캐시 _work/slotgrid_1117/det_<판>.json 만): 창(slotgrid.window) 안 프레임 → anchor(시작 줄) → track(칸 0 ~ n+2 의 F · E · ?).
  V      칸 1 ~ n 중 한 칸이 'E' 로 두 프레임 이상 잇달은 run 의 수(칸별로 세어 합)
  V1     칸 1 ~ n 에 'E' 가 하나라도 있는 프레임 수
  O      칸 1 ~ n 중 한 칸이 잇달아 '?' 인 가장 긴 시간(ms) = run 의 끝 − 첫 프레임 시각 + 한 프레임 간격(차례 프레임 간격 중앙값). O_slot = 그 칸
  O_any  칸 1 ~ n 중 어느 칸이든 '?' 인 프레임이 잇달은 가장 긴 시간(ms, 같은 셈)
  X      칸 n+1 이 'F' 인 프레임 수     X2  칸 n+2 또는 0 이 'F' 인 프레임 수
  S      |drift| 최대(칸)     SL  slip 참인 프레임 수     U  칸이 전부 '?' 인 프레임 수(track 이 미끄러진 동안을 모름으로 돌린 것)
  OFF    뜬 상자(off)가 있는 프레임 수     NF  프레임 수(track 이 낸 것 = 시작 줄 프레임부터)
  견주기용(규칙 탐색에는 안 넣음): A · C = routesig(_work/routesig_1119/dev_signals.json), LIFT = flashshot.segments 의 lifted 와 같은 셈으로
  번호 · 프레임 합(저장된 앞으로 추적 _work/sam2_1118/<id>_t_xpu/track.json, 없으면 None — flashshot 은 geminiagent 를 끌어와 import 안 하고 같은 식을 옮김).
시작 줄을 못 잡은 차례(anchor None)는 늘 어려움.
정답 난이도(채점 · 표시용만 — routesig.difficulty 와 다름): 쉬움 = kind tsumogiri 이고 order 가 없거나 1..n 그대로 · moves 없음. 그 밖은 어려움(까닭 = routesig.difficulty 의 글).
결과 = _work/slotroute_1119/dev_signals.json · dev_report.txt (전체는 signals.json · report.txt)
"""
from __future__ import annotations

import sys
from itertools import combinations
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import routesig as rs  # noqa: E402
import sam2track as s1  # noqa: E402
import slotgrid as sg  # noqa: E402
import turncut as tc  # noqa: E402

OUTD = hc.WORK / "slotroute_1119"
DEV_GAMES = ["r12_131655", "r16_135321", "r17_140450"]
CHK_GAMES = ["r19_142013", "r13_132644"]
SIGS = ["V", "V1", "O", "O_any", "X", "X2", "S", "SL", "U", "OFF", "NF"]
CMP = ["A", "C", "LIFT"]          # 견주기용(탐색 밖)

# ---- 규칙(개발 판만 보고 정함 — 확인 판 신호를 보기 전에 여기 적는다). None 이면 전체 실행 거부.
# 꼴: [(신호, "<=", 문턱), ...] AND
# 11-19 정함(dev_report.txt 만 보고, 확인 판 계산 전): V1 <= 0 — 시작 줄 칸 1 ~ n 이 한 프레임이라도 빈 것으로 보이면 어려움.
#  - V <= 0 은 쉬움 16/16 · 어려움 0 이지만 어려움 최솟값이 1 이라 여유가 없음(추가 52 의 "빈 값 하나 이상" 을 못 채움).
#    V1 <= 0 은 쉬움 15/16(r17_d02 — 소매가 지나갈 때 줄 선이 기울게 다시 맞춰져 한 프레임 빔) · 어려움 최솟값 2(r16_d06 · d08) → 사이에 1 이 빔.
#  - O(가장 긴 가림)는 안 씀: 쉬움 0 ~ 3410ms · 어려움 799 ~ 17588ms 로 겹치고(패를 빼는 가림이 팔이 지나가는 가림보다 길지 않음),
#    개발 판에 "어려움인데 빈 칸이 안 보인" 차례가 없어 문턱을 댈 데가 없음 → "손 밑에서 빼고 바로 끼움" 구멍은 이 규칙으로 안 막힘(확인 판 · 다른 판에서 봐야 함).
RULE = [("V1", "<=", 0)]


# ------------------------------------------------------------------ 정답(표시 · 채점용만)
def load_truth(games: list) -> dict:
    pre = {g[:3] for g in games}
    t = hc.jload(tc.BASE / "truth_final.json")
    return {k: v for k, v in t.items() if k[:3] in pre}


def difficulty(u: dict, n: int) -> tuple[str, str]:
    why = rs.difficulty(u)[1]
    if u.get("kind") != "tsumogiri":
        return "어려움", why
    if u.get("moves"):
        return "어려움", f"쯔모기리 · 옮김 {u['moves']}"
    o = u.get("order")
    if o and [str(x) for x in o] != [str(i) for i in range(1, (u.get("n") or n) + 1)]:
        return "어려움", "쯔모기리 · 줄 바꿈"
    return "쉬움", why


# ------------------------------------------------------------------ 신호
def runs(flags: list) -> list:
    """참이 잇달은 구간 [(첫 번호, 끝 번호)]."""
    out, s = [], None
    for i, f in enumerate(flags):
        if f and s is None:
            s = i
        if not f and s is not None:
            out.append((s, i - 1))
            s = None
    if s is not None:
        out.append((s, len(flags) - 1))
    return out


def lift_count(tid: str):
    """flashshot.segments 의 lifted(fi, o) 를 fi 1 ~ F-1 · 번호 1 ~ n 에 걸쳐 센 합과 들린 프레임 수. 추적이 없으면 None."""
    f = s1.OUT / f"{tid}_t_xpu" / "track.json"
    if not f.exists():
        return None, None
    tr = hc.jload(f)
    p, rec = tr["plan"], tr["rec"]
    n, F = p["n"], len(tr["frames"])
    w = float(np.median([b[2] - b[0] for b in p["a_boxes"]]))
    yc = float(np.median([(b[1] + b[3]) / 2 for b in p["e_boxes"]]))
    a0 = {o: rec["0"][str(o)][0] for o in range(1, n + 1)}
    x0 = {o: rec["0"][str(o)][1] for o in range(1, n + 1)}

    def lifted(fi, o):
        a, x, y = rec[str(fi)].get(str(o), [0, None, None])
        if y is not None and abs(y - yc) > s1.GONE_Y * p["hh"]:
            return True
        return a < rs.GONE_AREA * a0[o] and x is not None and x0[o] is not None and abs(x - x0[o]) > w

    who = [[o for o in range(1, n + 1) if lifted(fi, o)] for fi in range(1, F)]
    return sum(len(x) for x in who), sum(bool(x) for x in who)


def signals(gid: str, t: dict, det: dict) -> dict | None:
    n = t["n_calc"]
    w0, w1 = sg.window(t)
    frs = [(ms, det[ms]) for ms in sorted(det) if w0 <= ms <= w1]
    an = sg.anchor(frs, n)
    if an is None:
        return None
    tr = sg.track(frs, n, an)
    ms = [f["ms"] for f in tr]
    step = float(np.median(np.diff(ms))) if len(ms) > 1 else 0.0
    dur = lambda a, b: int(ms[b] - ms[a] + step)  # noqa: E731
    V, empties, Os = 0, [], []
    for i in range(1, n + 1):
        for a, b in runs([f["st"][i] == "E" for f in tr]):
            V += b > a
            empties.append({"slot": i, "f0": a, "f1": b, "len": b - a + 1, "t0": hc.mss(ms[a]), "t1": hc.mss(ms[b])})
        for a, b in runs([f["st"][i] == "?" for f in tr]):
            Os.append((dur(a, b), i, a, b))
    O = max(Os, default=(0, None, None, None))
    oa = [(dur(a, b), a, b) for a, b in runs([any(f["st"][i] == "?" for i in range(1, n + 1)) for f in tr])]
    Oany = max(oa, default=(0, None, None))
    return {"V": V, "V1": sum(any(f["st"][i] == "E" for i in range(1, n + 1)) for f in tr),
            "O": O[0], "O_slot": O[1], "O_span": None if O[2] is None else [hc.mss(ms[O[2]]), hc.mss(ms[O[3]])],
            "O_any": Oany[0], "O_any_span": None if Oany[1] is None else [hc.mss(ms[Oany[1]]), hc.mss(ms[Oany[2]])],
            "X": sum(f["st"][n + 1] == "F" for f in tr), "X2": sum(f["st"][n + 2] == "F" or f["st"][0] == "F" for f in tr),
            "S": round(max((abs(f["drift"]) for f in tr), default=0.0), 2), "SL": sum(bool(f["slip"]) for f in tr),
            "U": sum(all(s == "?" for s in f["st"]) for f in tr), "OFF": sum(bool(f["off"]) for f in tr), "NF": len(tr),
            "step_ms": step, "anchor": hc.mss(an[4]), "empties": empties}


def collect(games: list, truth: dict, cmp_file: Path) -> list:
    raw = hc.jload(cmp_file) if cmp_file.exists() else []
    raw = raw if isinstance(raw, list) else raw.get("check", [])     # routesig signals.json = {"dev", "check", …}
    cmp = {r["id"]: r["sig"] for r in raw if r.get("sig") is not None}
    rows = []
    for gid in games:
        det = {int(k): v for k, v in hc.jload(sg.OUT / f"det_{gid}.json").items()}
        ts = {t["id"]: t for t in tc.turns_of(gid)}
        for tid in rs.targets(gid):
            t = ts[tid]
            lab, why = difficulty(truth[tid], t["n_calc"])
            sig = signals(gid, t, det)
            c = cmp.get(tid)
            lf, lff = lift_count(tid)
            extra = {"A": None if c is None else bool(c["A"]), "C": None if c is None else c["C"], "LIFT": lf, "LIFT_frames": lff}
            rows.append({"id": tid, "game": gid, "truth_kind": truth[tid].get("kind"), "difficulty": lab, "why": why, "sig": sig, "cmp": extra})
    return rows


# ------------------------------------------------------------------ 표 · 탐색
def route(sig: dict | None, rule) -> str:
    if sig is None:
        return "어려움"
    for name, op, th in rule:
        v = sig[name]
        if op == "==" and v != th:
            return "어려움"
        if op == "<=" and not v <= th:
            return "어려움"
    return "쉬움"


def show_rows(log, rows):
    log(f"{'차례':8s} {'정답':3s} {'까닭':18s} | " + " ".join(f"{s:>6s}" for s in SIGS) + " | " + " ".join(f"{s:>4s}" for s in CMP) + " | O 칸 · 빈 칸(칸@프레임 시각, 2장 이상만)")
    for r in rows:
        s, c = r["sig"], r["cmp"]
        cv = " ".join(f"{('-' if c[k] is None else ('O' if c[k] else 'x') if k == 'A' else c[k])!s:>4}" for k in CMP)
        if s is None:
            log(f"{r['id']:8s} {r['difficulty']:3s} {r['why']:18s} | 시작 줄 없음 → 늘 어려움 | {cv}")
            continue
        vals = " ".join(f"{s[k]!s:>6}" for k in SIGS)
        em = " ".join(f"{e['slot']}@{e['t0']}" + (f"~{e['t1']}" if e["f1"] > e["f0"] else "") for e in s["empties"] if e["len"] >= 2)
        log(f"{r['id']:8s} {r['difficulty']:3s} {r['why']:18s} | {vals} | {cv} | O칸 {s['O_slot']} · {em or '-'}")


def dist(log, rows):
    log("\n신호별 분포(쉬움 / 어려움: 최소 · 중앙 · 최대, 시작 줄 없는 차례 제외)")
    for k in SIGS + CMP:
        parts = []
        for lab in ("쉬움", "어려움"):
            v = [(r["cmp"] if k in CMP else r["sig"])[k] for r in rows if r["sig"] is not None and r["difficulty"] == lab]
            v = [x for x in v if x is not None]
            if not v:
                parts.append(f"{lab} -")
            elif k == "A":
                parts.append(f"{lab} 참 {sum(v)}/{len(v)}")
            else:
                parts.append(f"{lab} {min(v)} · {float(np.median(v)):g} · {max(v)}")
        log(f"  {k:5s} {' | '.join(parts)}")


def score(rows, rule):
    m = {(a, b): 0 for a in ("쉬움", "어려움") for b in ("쉬움", "어려움")}
    for r in rows:
        m[(r["difficulty"], route(r["sig"], rule))] += 1
    return m


def search(log, rows):
    """어려움 → 쉬움 0 을 지키며 쉬움을 가장 많이 보내는 단일 · 두 신호 AND(문턱 = 관측값, <= 꼴). 같은 신호 묶음은 가장 좋은 것 하나만."""
    tr = [r for r in rows if r["sig"] is not None]
    easy_n = sum(r["difficulty"] == "쉬움" for r in rows)
    hard_n = sum(r["difficulty"] == "어려움" for r in rows)
    singles = [[(k, "<=", th)] for k in SIGS if k != "NF" for th in sorted({r["sig"][k] for r in tr})]
    cands = list(singles) + [c1 + c2 for c1, c2 in combinations(singles, 2) if c1[0][0] != c2[0][0]]
    res = []
    for c in cands:
        m = score(rows, c)
        if m[("어려움", "쉬움")] == 0:
            res.append((m[("쉬움", "쉬움")], c))
    res.sort(key=lambda x: (-x[0], len(x[1])))
    log(f"\n규칙 후보(개발 판 · 어려움 → 쉬움 0 인 것 중 쉬움 보낸 수 순, 쉬움 {easy_n} · 어려움 {hard_n}, NF 는 뺌, 문턱 = 경계 값 그대로)")
    seen, shown = set(), 0
    for v, c in res:
        key = tuple(x[0] for x in c)
        if key in seen:
            continue
        seen.add(key)
        # 경계 여유: 각 문턱에서 다음으로 큰 어려움 값(이 규칙의 다른 조건을 통과한 어려움 중)
        gap = []
        for i, (k, _, th) in enumerate(c):
            others = c[:i] + c[i + 1:]
            hv = [r["sig"][k] for r in tr if r["difficulty"] == "어려움" and route(r["sig"], others) == "쉬움" and r["sig"][k] > th]
            gap.append(f"{k} 어려움 최소 {min(hv) if hv else '-'}")
        log(f"  쉬움 {v:2d}/{easy_n} ← " + " AND ".join(f"{a}{op}{th}" for a, op, th in c) + "   (" + " · ".join(gap) + ")")
        shown += 1
        if shown >= 25:
            break


def t_table(log, rows):
    """"V == 0 AND O <= T" 의 T 를 바꿔 가며. 견주기: 추가 44 규칙(A AND C <= 1) · 들림 0 과 각각 AND."""
    tr = [r for r in rows if r["sig"] is not None]
    Ts = sorted({r["sig"]["O"] for r in tr if r["sig"]["V"] == 0})
    easy_n = sum(r["difficulty"] == "쉬움" for r in rows)

    def cnt(pred):
        e = sum(1 for r in tr if r["difficulty"] == "쉬움" and pred(r))
        h = sum(1 for r in tr if r["difficulty"] == "어려움" and pred(r))
        return f"{e:2d} / {h}"

    a44 = lambda r: bool(r["cmp"]["A"]) and r["cmp"]["C"] is not None and r["cmp"]["C"] <= 1  # noqa: E731
    l0 = lambda r: r["cmp"]["LIFT"] == 0  # noqa: E731
    log(f"\n\"V == 0 AND O <= T\" (칸: 쉬움 보냄 / 어려움 → 쉬움, 쉬움 {easy_n})")
    log(f"  {'T(ms)':>7s} | {'V0 AND O<=T':>12s} | {'+ A AND C<=1':>12s} | {'+ 들림 0':>9s}")
    for T in Ts:
        base = lambda r, T=T: r["sig"]["V"] == 0 and r["sig"]["O"] <= T  # noqa: E731
        log(f"  {T:7d} | {cnt(base):>12s} | {cnt(lambda r: base(r) and a44(r)):>12s} | {cnt(lambda r: base(r) and l0(r)):>9s}")
    log(f"  견주기 — V 안 씀: 추가 44 규칙(A AND C<=1) {cnt(a44)} · 들림 0 {cnt(l0)} · 둘 다 {cnt(lambda r: a44(r) and l0(r))}")


def confusion(log, title, rows, rule):
    m = score(rows, rule)
    easy = m[("쉬움", "쉬움")] + m[("쉬움", "어려움")]
    log(f"\n{title} 혼동표(행 = 정답, 열 = 보냄)")
    log("            보냄 쉬움  보냄 어려움")
    log(f"  정답 쉬움      {m[('쉬움', '쉬움')]:3d}        {m[('쉬움', '어려움')]:3d}")
    log(f"  정답 어려움    {m[('어려움', '쉬움')]:3d}        {m[('어려움', '어려움')]:3d}")
    log(f"  잘못 보냄(어려움 → 쉬움) {m[('어려움', '쉬움')]} · 쉬움 보낸 비율 {m[('쉬움', '쉬움')]}/{easy} = {m[('쉬움', '쉬움')] / max(easy, 1):.0%}")
    return m


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode != "dev" and RULE is None:
        raise SystemExit("RULE 이 비어 있음 — 개발 판(dev)만 보고 정한 뒤 상수로 적을 것(확인 판은 그 뒤에만 계산)")
    log = rs.Log()
    log("== 개발 판(r12 · r16 · r17)")
    dev = collect(DEV_GAMES, load_truth(DEV_GAMES), rs.OUTD / "dev_signals.json")
    show_rows(log, dev)
    c = {lab: sum(r["difficulty"] == lab for r in dev) for lab in ("쉬움", "어려움")}
    log(f"개발 판 {len(dev)}차례: 쉬움 {c['쉬움']} · 어려움 {c['어려움']}(끝 붙임 {sum(r['why'] == '끝 붙임' for r in dev)}) · 시작 줄 없음 {sum(r['sig'] is None for r in dev)}")
    dist(log, dev)
    search(log, dev)
    t_table(log, dev)
    OUTD.mkdir(parents=True, exist_ok=True)
    if mode == "dev":
        hc.jsave(OUTD / "dev_signals.json", dev)
        (OUTD / "dev_report.txt").write_bytes(("\n".join(log.lines) + "\n").encode("utf-8"))
        return
    # ---- 아래는 RULE 을 정한 뒤에만(확인 판 r19 · r13 은 여기서 처음 계산)
    rtxt = " AND ".join(f"{a} {op} {th}" for a, op, th in RULE)
    log(f"\n== 정한 규칙(개발 판만 보고, 코드 상수): 쉬움으로 보냄 ⇔ {rtxt} · 시작 줄 없으면 어려움")
    for r in dev:
        r["route"] = route(r["sig"], RULE)
    md = confusion(log, "개발 판", dev, RULE)
    log("\n== 확인 판(r19 · r13) — 규칙을 정한 뒤 한 번")
    chk = collect(CHK_GAMES, load_truth(CHK_GAMES), rs.OUTD / "signals.json")
    for r in chk:
        r["route"] = route(r["sig"], RULE)
    show_rows(log, chk)
    log("보냄: " + " · ".join(f"{r['id']}→{r['route']}{'(✗)' if r['difficulty'] == '어려움' and r['route'] == '쉬움' else ''}" for r in chk))
    mc = confusion(log, "확인 판", chk, RULE)
    easy_c = mc[("쉬움", "쉬움")] + mc[("쉬움", "어려움")]
    verdict = ("✅ 어려움 → 쉬움 0 · 쉬움 보낸 비율 ≥ 50%" if mc[("어려움", "쉬움")] == 0 and mc[("쉬움", "쉬움")] >= 0.5 * easy_c else
               "❌ 어려움 → 쉬움 ≥ 1" if mc[("어려움", "쉬움")] else "△ 잘못 보냄 0 이지만 쉬움 보낸 비율 < 50%")
    log(f"\n판정(추가 52 확인 판 기준): {verdict}")
    hc.jsave(OUTD / "signals.json", {"rule": RULE, "dev": dev, "check": chk, "verdict": verdict,
                                      "confusion_dev": {f"{a}→{b}": v for (a, b), v in md.items()},
                                      "confusion_check": {f"{a}→{b}": v for (a, b), v in mc.items()}})
    (OUTD / "report.txt").write_bytes(("\n".join(log.lines) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
