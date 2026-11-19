"""쉬운 차례만 Flash 로 보내기 — 저장된 SAM 2 추적 신호로 어려운 차례를 빠짐없이 가를 수 있나(2026-11-19, 계획서 3단계 "추가 44"). API 호출 없음 · 0달러.

  python -X utf8 routesig.py dev   # 개발 판(r12 · r16 · r17)만: 정답 난이도 · 신호 분포 · 규칙 후보(확인 판 신호는 계산도 안 함)
  python -X utf8 routesig.py       # 전부: 개발 판 → 정한 규칙(아래 RULE 상수) → 확인 판(r19 · r13) 한 번

정답 난이도(신호 계산에는 안 씀): 쉬움 = 쯔모기리 / 손에서 냈고 j_closed == n · moves 없음 · order 가 있으면 "원래 순서에서 k 만 빠지고 D 가 끝".
신호(정답 · LLM 답 파일 없이, _work/sam2_1118/<id>_t_xpu/track.json · overlaps.json 만 읽음):
  A  judge_end      sam2track.judge 끝 상태가 "사라진 번호 없음 · 빈 칸 없음 · 겹침 없음"(쯔모기리 꼴) 또는 "사라진 번호 하나 · 빈 칸 하나 = 줄 끝(n) · 겹침 없음"
  B  order_breaks   남은 번호(judge 가 사라졌다고 본 번호 제외 · 그 프레임에 면적 30% 밑은 제외)의 x 순서가 첫 프레임 순서와 어긋난 프레임 수
                    (두 번호 x 차이가 패 폭 0.25 넘게 뒤집힌 것만 — 겹친 두 마스크의 중심이 몇 화소 흔들려 뒤집히는 것은 뺌). B0 = 허용 없이(0 화소)
  C  jumps          남은 번호의 x 가 이웃 프레임(둘 다 면적 30% 이상) 사이에 패 폭(plan a_boxes 폭 중앙값) 넘게 뛴 횟수
  C2 jumps_seen     C 와 같되 "바로 앞 프레임" 대신 "마지막으로 보인 프레임" 과 견줌(가려졌다 다른 자리에 나타난 것까지)
  D  overlap_frames 두 번호가 한 패에 겹친 프레임 수(overlaps.json — 작은 마스크의 50% 넘게 겹침)
  D2 overlap_nogone D 에서 사라진 번호가 낀 쌍을 뺀 것(버린 패 색이 이웃에 옮겨 붙는 흔한 겹침 제외)
  E  missing_frac   번호 · 프레임 중 면적이 첫 프레임의 30% 밑(가려짐)인 비율 — 사라진 번호는 사라진 뒤(끝까지 안 돌아오는 첫 프레임부터) 제외
  G  end_misplaced  끝 프레임에서 남은 번호가 앉은 상자 번호가 "쉬운 꼴"(k 앞은 제자리, k 뒤는 한 칸 왼쪽, 쯔모기리 꼴은 모두 제자리)과 다른 번호 수
                    (A 가 거짓이면 n). F = A 이고 G == 0
  NF n_frames       추적 프레임 수
추적이 없는 차례(r19_d04)는 늘 어려움으로 보냄.
결과 = _work/routesig_1119/signals.json · report.txt (dev 는 dev_report.txt)
"""
from __future__ import annotations

import sys
from itertools import combinations
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import sam2track as s1  # noqa: E402

OUTD = hc.WORK / "routesig_1119"
DEV_GAMES = ["r12_131655", "r16_135321", "r17_140450"]
CHK_GAMES = ["r19_142013", "r13_132644"]
GONE_AREA = 0.30       # E · 보임 판정: 첫 프레임 면적의 30%
B_TOL = 0.25           # B: 패 폭의 0.25 넘게 뒤집혀야 어긋남
SIGS = ["A", "F", "B", "B0", "C", "C2", "D", "D2", "E", "G", "NF"]
BOOL = {"A", "F"}

# ---- 규칙(개발 판만 보고 정함 — 확인 판 신호를 보기 전에 여기 적는다). None 이면 전부 실행 거부.
# 꼴: [(신호, "<=", 문턱), ...] AND, 불 신호는 (신호, "==", True)
# 11-19 정함(dev_report.txt 만 보고): A 참 AND C <= 1.
#  - A 거짓인 어려움 10 은 A 하나로 걸러짐. A 참인 어려움은 r16_d01 · d02(줄 끝 가까이 끼움 j=11 · 12 — 추적 번호가 그대로 밀려 끝 상태가 쯔모기리 꼴) 둘뿐,
#    둘 다 C = 3. A 참인 쉬움 19 의 C 는 0(17) · 1(r16_d04 · d06 — 손에서 낸 패의 마스크가 한 번 옮겨 앉는 것)뿐.
#  - 문턱은 정수라 1 과 3 사이엔 2 하나뿐 — 2 는 어려움 최솟값 바로 옆이라 안 쓰고, "버린 패의 한 번 뜀만 허용" 이라는 뜻이 있는 1 로(어려움 쪽에 두 칸 여유).
#  - 한 신호(B0 <= 0 · D <= 1 — 18/20)보다 하나 더 보내고, D <= 1 은 어려움 최솟값 2 에 붙어 있어 안 씀.
RULE = [("A", "==", True), ("C", "<=", 1)]


def targets(gid: str) -> list:
    """리치 선언(강에 가로) 뒤가 아닌 차례 — rebuild_opus.rebuild 와 같은 가르기."""
    g = next(x for x in hc.jload(hc.WORK / "testtruth_1116" / "turns.json")["games"] if x["id"] == gid)
    out, riichi = [], False
    for t in g["turns"]:
        if not riichi:
            out.append(t["id"])
        if t.get("sideways"):
            riichi = True
    return out


def difficulty(u: dict) -> tuple[str, str]:
    """정답 → (쉬움|어려움, 까닭). 신호 계산에는 쓰지 않는다."""
    if u.get("kind") == "tsumogiri":
        return "쉬움", "쯔모기리"
    n = u.get("n") or 13
    if u.get("kind") != "hand":
        return "어려움", f"kind={u.get('kind')}"
    if u.get("moves"):
        return "어려움", f"옮김 {u['moves']}"
    if u.get("j_closed") != n:
        return "어려움", f"안쪽 끼움 j={u.get('j_closed')}"
    if u.get("order"):
        want = [str(i) for i in range(1, n + 1) if i != u["k_id"]] + ["D"]
        if [str(x) for x in u["order"]] != want:
            return "어려움", "order 가 끝 붙임 꼴이 아님"
    return "쉬움", "끝 붙임"


def signals(tid: str) -> dict | None:
    d = s1.OUT / f"{tid}_t_xpu"
    if not (d / "track.json").exists():
        return None
    tr = hc.jload(d / "track.json")
    p, rec = tr["plan"], tr["rec"]
    n, F = p["n"], len(tr["frames"])
    w = float(np.median([b[2] - b[0] for b in p["a_boxes"]]))
    yc = float(np.median([(b[1] + b[3]) / 2 for b in p["e_boxes"]]))
    jd = s1.judge(tr)
    gone = set(jd["gone"])
    a0 = {o: rec["0"][str(o)][0] for o in range(1, n + 1)}

    def cell(fi, o):
        return rec[str(fi)].get(str(o), [0, None, None])

    def vis(fi, o):
        a, x, _ = cell(fi, o)
        return x is not None and a >= GONE_AREA * a0[o]

    def off(fi, o):  # judge 와 같은 "사라짐"(면적 · 줄 높이)
        a, x, y = cell(fi, o)
        return a < GONE_AREA * a0[o] or y is None or abs(y - yc) > s1.GONE_Y * p["hh"]

    gone_from = {}
    for o in gone:
        f = F
        while f > 0 and off(f - 1, o):
            f -= 1
        gone_from[o] = f
    stay = [o for o in range(1, n + 1) if o not in gone]
    x0 = {o: cell(0, o)[1] for o in stay}
    order0 = sorted(stay, key=lambda o: x0[o])

    # A · G · F
    A = (not jd["clash"]) and ((not gone and not jd["free"]) or (len(gone) == 1 and jd["free"] == [n]))
    if A:
        k = next(iter(gone)) if gone else None
        last = rec[str(F - 1)]
        cx = [(b[0] + b[2]) / 2 for b in p["e_boxes"]]
        G = 0
        for o in stay:
            bi = int(np.argmin([abs(last[str(o)][1] - c) for c in cx])) + 1
            G += bi != (o if k is None or o < k else o - 1)
    else:
        G = n
    # B · B0
    B = B0 = 0
    for fi in range(F):
        vs = [o for o in order0 if vis(fi, o)]
        xs = [cell(fi, o)[1] for o in vs]
        inv = [(xs[i] - xs[j]) for i in range(len(xs)) for j in range(i + 1, len(xs)) if xs[i] > xs[j]]
        B0 += bool(inv)
        B += any(v > B_TOL * w for v in inv)
    # C · C2
    C = C2 = 0
    for o in stay:
        seen = None
        for fi in range(F):
            if not vis(fi, o):
                continue
            x = cell(fi, o)[1]
            if fi > 0 and vis(fi - 1, o) and abs(x - cell(fi - 1, o)[1]) > w:
                C += 1
            if seen is not None and abs(x - seen) > w:
                C2 += 1
            seen = x
    # D · D2
    rows = hc.jload(d / "overlaps.json")["rows"]
    D = sum(bool(r) for r in rows)
    D2 = sum(any(a not in gone and b not in gone for a, b in r) for r in rows)
    # E
    tot = miss = 0
    for o in range(1, n + 1):
        for fi in range(F):
            if o in gone and fi >= gone_from[o]:
                continue
            tot += 1
            a, x, _ = cell(fi, o)
            miss += x is None or a < GONE_AREA * a0[o]
    return {"A": bool(A), "F": bool(A and G == 0), "B": B, "B0": B0, "C": C, "C2": C2, "D": D, "D2": D2,
            "E": round(miss / max(tot, 1), 4), "G": int(G), "NF": F,
            "judge": {"gone": sorted(gone), "free": jd["free"], "clash": jd["clash"], "k": jd["k"], "j": jd["j"]},
            "gone_from": {str(o): f for o, f in gone_from.items()}, "tile_w": w}


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


class Log:
    def __init__(self):
        self.lines = []

    def __call__(self, *a):
        s = " ".join(str(x) for x in a)
        print(s, flush=True)
        self.lines.append(s)


def collect(games: list, truth: dict) -> list:
    rows = []
    for gid in games:
        for tid in targets(gid):
            lab, why = difficulty(truth[tid])
            rows.append({"id": tid, "game": gid, "truth_kind": truth[tid].get("kind"), "difficulty": lab, "why": why, "sig": signals(tid)})
    return rows


def show_rows(log, rows):
    log(f"{'차례':9s} {'정답':4s} {'까닭':18s} | " + " ".join(f"{s:>6s}" for s in SIGS) + " | judge(사라짐 · 빈 칸 · 겹침)")
    for r in rows:
        s = r["sig"]
        if s is None:
            log(f"{r['id']:9s} {r['difficulty']:4s} {r['why']:18s} | 추적 없음 → 늘 어려움")
            continue
        vals = " ".join(f"{('O' if s[k] else 'x') if k in BOOL else s[k]!s:>6}" for k in SIGS)
        j = s["judge"]
        log(f"{r['id']:9s} {r['difficulty']:4s} {r['why']:18s} | {vals} | {j['gone']} · {j['free']}{' · ' + str(j['clash']) if j['clash'] else ''}")


def dist(log, rows):
    log("\n신호별 분포(쉬움 / 어려움: 최소 · 중앙 · 최대, 불 신호는 참 수/전체)")
    for k in SIGS:
        parts = []
        for lab in ("쉬움", "어려움"):
            v = [r["sig"][k] for r in rows if r["sig"] is not None and r["difficulty"] == lab]
            if k in BOOL:
                parts.append(f"{lab} 참 {sum(v)}/{len(v)}")
            else:
                parts.append(f"{lab} {min(v)} · {float(np.median(v)):g} · {max(v)}")
        log(f"  {k:3s} {' | '.join(parts)}")


def score(rows, rule):
    m = {(a, b): 0 for a in ("쉬움", "어려움") for b in ("쉬움", "어려움")}
    for r in rows:
        m[(r["difficulty"], route(r["sig"], rule))] += 1
    return m


def search(log, rows):
    """개발 판에서: 어려움 → 쉬움 0 을 지키며 쉬움을 가장 많이 보내는 규칙 후보(문턱 = 어려움 최솟값 바로 밑의 쉬움 값 — 경계에 딱 맞음, 그대로 쓰지 않음)."""
    tr = [r for r in rows if r["sig"] is not None]
    hard = [r for r in tr if r["difficulty"] == "어려움"]
    easy_n = sum(r["difficulty"] == "쉬움" for r in rows)
    cands = []
    for k in SIGS:
        if k in BOOL:
            cands.append([(k, "==", True)])
        else:
            for th in sorted({r["sig"][k] for r in tr}):
                cands.append([(k, "<=", th)])
    singles = list(cands)
    for c1, c2 in combinations(singles, 2):
        if c1[0][0] != c2[0][0]:
            cands.append(c1 + c2)
    res = []
    for c in cands:
        m = score(rows, c)
        if m[("어려움", "쉬움")] == 0:
            res.append((m[("쉬움", "쉬움")], c))
    res.sort(key=lambda x: (-x[0], len(x[1])))
    log(f"\n규칙 후보(개발 판 · 어려움 → 쉬움 0 인 것 중 쉬움 보낸 수 순, 쉬움 {easy_n} · 어려움 {len(hard) + sum(r['sig'] is None and r['difficulty'] == '어려움' for r in rows)})")
    seen = set()
    shown = 0
    for v, c in res:
        key = tuple(x[0] for x in c)
        if key in seen:
            continue
        seen.add(key)
        log(f"  쉬움 {v:2d}/{easy_n} ← " + " AND ".join(f"{a}{op}{th}" for a, op, th in c))
        shown += 1
        if shown >= 25:
            break


def confusion(log, title, rows, rule):
    m = score(rows, rule)
    easy = m[("쉬움", "쉬움")] + m[("쉬움", "어려움")]
    log(f"\n{title} 혼동표(행 = 정답, 열 = 보냄)")
    log(f"            보냄 쉬움  보냄 어려움")
    log(f"  정답 쉬움      {m[('쉬움', '쉬움')]:3d}        {m[('쉬움', '어려움')]:3d}")
    log(f"  정답 어려움    {m[('어려움', '쉬움')]:3d}        {m[('어려움', '어려움')]:3d}")
    log(f"  잘못 보냄(어려움 → 쉬움) {m[('어려움', '쉬움')]} · 쉬움 보낸 비율 {m[('쉬움', '쉬움')]}/{easy} = {m[('쉬움', '쉬움')] / easy:.0%}")
    return m


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    truth = s1.truth_all()
    log = Log()
    log("== 개발 판(r12 · r16 · r17)")
    dev = collect(DEV_GAMES, truth)
    show_rows(log, dev)
    c = {lab: sum(r["difficulty"] == lab for r in dev) for lab in ("쉬움", "어려움")}
    log(f"개발 판 {len(dev)}차례: 쉬움 {c['쉬움']}(쯔모기리 {sum(r['why'] == '쯔모기리' for r in dev)} · 끝 붙임 {sum(r['why'] == '끝 붙임' for r in dev)}) · 어려움 {c['어려움']}")
    dist(log, dev)
    search(log, dev)
    if mode == "dev":
        hc.jsave(OUTD / "dev_signals.json", dev)
        (OUTD / "dev_report.txt").write_bytes(("\n".join(log.lines) + "\n").encode("utf-8"))
        return
    if RULE is None:
        raise SystemExit("RULE 이 비어 있음 — 개발 판만 보고 정한 뒤 상수로 적을 것(확인 판은 그 뒤에만 계산)")
    rtxt = " AND ".join(f"{a} {op} {th}" for a, op, th in RULE)
    log(f"\n== 정한 규칙(개발 판만 보고, 코드 상수): 쉬움으로 보냄 ⇔ {rtxt} · 추적 없으면 어려움")
    for r in dev:
        r["route"] = route(r["sig"], RULE)
    md = confusion(log, "개발 판", dev, RULE)

    log("\n== 확인 판(r19 · r13) — 규칙을 정한 뒤 한 번")
    chk = collect(CHK_GAMES, truth)
    for r in chk:
        r["route"] = route(r["sig"], RULE)
    show_rows(log, chk)
    c = {lab: sum(r["difficulty"] == lab for r in chk) for lab in ("쉬움", "어려움")}
    log(f"확인 판 {len(chk)}차례: 쉬움 {c['쉬움']}(쯔모기리 {sum(r['why'] == '쯔모기리' for r in chk)} · 끝 붙임 {sum(r['why'] == '끝 붙임' for r in chk)}) · 어려움 {c['어려움']}")
    log("보냄: " + " · ".join(f"{r['id']}→{r['route']}{'(✗)' if r['difficulty'] == '어려움' and r['route'] == '쉬움' else ''}" for r in chk))
    mc = confusion(log, "확인 판", chk, RULE)
    alln = dev + chk
    ce = {lab: sum(r["difficulty"] == lab for r in alln) for lab in ("쉬움", "어려움")}
    log(f"\n정답 난이도 합: {len(alln)}차례 = 쉬움 {ce['쉬움']}(쯔모기리 {sum(r['why'] == '쯔모기리' for r in alln)} · 끝 붙임 {sum(r['why'] == '끝 붙임' for r in alln)}) · 어려움 {ce['어려움']}")
    easy_c = mc[("쉬움", "쉬움")] + mc[("쉬움", "어려움")]
    ok = mc[("어려움", "쉬움")] == 0 and mc[("쉬움", "쉬움")] >= 0.5 * easy_c
    verdict = ("✅ 코드로 가를 수 있다(확인 판 잘못 보냄 0 · 쉬움 보낸 비율 ≥ 50%)" if ok else
               "❌ 이 신호로는 못 가름(확인 판 잘못 보냄 ≥ 1)" if mc[("어려움", "쉬움")] else
               "△ 잘못 보냄 0 이지만 쉬움 보낸 비율 < 50%")
    log(f"\n판정(추가 44 기준): {verdict}")
    bad = [r for r in alln if r["difficulty"] == "어려움" and r["sig"] is not None and (r["sig"]["A"] or r["route"] == "쉬움")]
    if bad:
        log("\n어려움인데 쉬움 쪽 신호(A 참 또는 쉬움으로 보냄)를 보인 차례:")
        for r in bad:
            log(f"  {r['id']} ({r['why']}) 보냄 {r['route']} · " + " ".join(f"{k}={r['sig'][k]}" for k in SIGS))
    hc.jsave(OUTD / "signals.json", {"rule": RULE, "dev": dev, "check": chk,
                                      "confusion_dev": {f"{a}→{b}": v for (a, b), v in md.items()},
                                      "confusion_check": {f"{a}→{b}": v for (a, b), v in mc.items()}, "verdict": verdict})
    (OUTD / "report.txt").write_bytes(("\n".join(log.lines) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
