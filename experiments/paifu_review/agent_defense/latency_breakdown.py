"""복기 질문(/v2/review/ask) 시간 쪼개기 — 이미 잰 결과만 다시 모음(Gemini 호출 0). metrics 표 15-15.

python -X utf8 experiments/paifu_review/agent_defense/latency_breakdown.py [results 폴더]

1) results/agent_*/ 의 답 json(elapsed_s · usage.llm_calls · input_tokens)을 묶음 · 지시문 판마다 집계
2) 시간 = a + b × LLM 호출 수 + c × 입력 천 토큰 (최소제곱)
3) 운영 확인(prod_ask_1123_a8/runs.json)과 같은 질문 id 의 개발 서버 값 대조
4) 첫 도구를 질문 글만 보고 맞힐 수 있나 — a7 · a8 · tone 로그. 규칙은 이 질문들을 보고 만든 것이라
   맞힘 비율은 낙관값(안 본 질문으로 다시 재야 함).
"""
import glob
import json
import os
import re
import statistics as st
import sys
from collections import Counter, defaultdict

R = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "results")


def med(x):
    return round(st.median(x), 2) if x else None


def pct(x, q):
    x = sorted(x)
    return round(x[min(len(x) - 1, int(q * len(x)))], 2) if x else None


def load_rows():
    rows = []
    for d in sorted(glob.glob(os.path.join(R, "agent_*"))):
        if not os.path.isdir(d) or "fake" in d:
            continue
        for f in glob.glob(os.path.join(d, "**", "*.json"), recursive=True):
            try:
                j = json.load(open(f, encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(j, dict) or "elapsed_s" not in j or "usage" not in j:
                continue
            u = j["usage"] or {}
            rows.append(dict(dir=os.path.relpath(os.path.dirname(f), R), id=os.path.basename(f)[:-5], t=j["elapsed_s"],
                             calls=u.get("llm_calls"), inp=u.get("input_tokens"), out=u.get("output_tokens"),
                             retries=j.get("retries", 0), pv=j.get("prompt_version")))
    return rows


def lstsq(X, y):
    n = len(X[0])
    A = [[sum(x[i] * x[j] for x in X) for j in range(n)] for i in range(n)]
    b = [sum(x[i] * yy for x, yy in zip(X, y)) for i in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            f = A[j][i] / A[i][i]
            for k in range(n):
                A[j][k] -= f * A[i][k]
            b[j] -= f * b[i]
    s = [0.0] * n
    for i in reversed(range(n)):
        s[i] = (b[i] - sum(A[i][k] * s[k] for k in range(i + 1, n))) / A[i][i]
    return [round(v, 2) for v in s]


def guess_first_tool(q):
    turn = re.search(r"(\d+)\s*순", q)
    if re.search(r"총평", q) or re.search(r"점수|몇 등|등수|순위|몇 점", q):
        return "game_summary"
    if turn and re.search(r"버렸으면|버렸어도|대신|만약|였으면|했으면", q):
        return "what_if"
    if turn and re.search(r"위험|현물|안전|접|밀", q):
        return "defense_info"
    if turn and re.search(r"왜|실수|최선|뭘 버|무엇을 버|어떤 패", q):
        return "turn_info"
    if re.search(r"리치 뒤|리치한 뒤|리치 받|접는 자리|민 곳|제일|가장|아까운", q):
        return "find_turns"
    return None


def main():
    rows = [r for r in load_rows() if r["calls"] and r["inp"]]
    print("== 1) 묶음 · 지시문 판마다 (초 · 토큰)")
    g = defaultdict(list)
    for r in rows:
        g[(r["dir"].split(os.sep)[0], r["pv"])].append(r)
    print(f"{'dir':22} {'pv':3} {'n':>3} {'t_med':>6} {'p90':>6} {'max':>6} {'calls':>5} {'inp/q':>7} {'s/call':>6}")
    for k, v in sorted(g.items(), key=lambda kv: (kv[0][1] or "", kv[0][0])):
        t = [r["t"] for r in v]
        print(f"{k[0]:22} {k[1]:3} {len(v):3} {med(t):6} {pct(t, .9):6} {max(t):6} "
              f"{med([r['calls'] for r in v]):5} {med([r['inp'] for r in v]):7} {med([r['t'] / r['calls'] for r in v]):6}")

    print("\n== 2) 시간 회귀, n =", len(rows))
    y = [r["t"] for r in rows]
    print("t = a + b*calls + c*inp_k :", lstsq([[1, r["calls"], r["inp"] / 1000] for r in rows], y))
    print("t = a + b*calls           :", lstsq([[1, r["calls"]] for r in rows], y))
    by = defaultdict(list)
    for r in rows:
        by[r["calls"]].append(r["t"])
    for c in sorted(by):
        print(f"  LLM {c}회: n={len(by[c])} 중앙 {med(by[c])} / p90 {pct(by[c], .9)} / 최대 {max(by[c])}")
    spc = [r["t"] / r["calls"] for r in rows]
    print(f"  호출당 초: 중앙 {med(spc)} / p90 {pct(spc, .9)} / p99 {pct(spc, .99)} / 최대 {max(spc):.2f}")
    a78 = [r for r in rows if r["pv"] in ("a7", "a8")]
    print("  a7+a8 호출 수 분포", sorted(Counter(r["calls"] for r in a78).items()),
          "재시도 있음", sum(r["retries"] > 0 for r in a78), "/", len(a78))

    print("\n== 3) 운영 확인(표 15-14) ↔ 같은 질문의 개발 서버 a8(표 15-13)")
    p = os.path.join(R, "prod_ask_1123_a8", "runs.json")
    if os.path.exists(p):
        for r in json.load(open(p, encoding="utf-8")):
            m = re.search(r"retries: (\d+) · 서버 ([\d.]+)초", r.get("out", ""))
            dev = [(x["t"], x["calls"]) for x in rows if x["id"] == r["id"] and x["pv"] == "a8"]
            print(f"  {r['id']:4} 운영 {m.group(2) if m else '?':>7}초(재시도 {m.group(1) if m else '?'}) | 개발 a8 {dev}")

    print("\n== 4) 첫 도구를 질문 글로 맞히기(a7 · a8 · tone 로그, 사후 규칙 — 낙관값)")
    tot = hit = none = 0
    seqs = Counter()
    for d in ["agent_1123a7", "agent_1123a8", "agent_1123tone"]:
        for f in glob.glob(os.path.join(R, d, "**", "*.log"), recursive=True):
            txt = open(f, encoding="utf-8").read()
            q = re.search(r"질문: (.*)", txt)
            tools = re.findall(r"^\s*도구 (\w+)", txt, re.M)
            if not q or not tools:
                continue
            gt = guess_first_tool(q.group(1))
            tot += 1
            none += gt is None
            hit += gt == tools[0]
            seqs[len(tools)] += 1
    print(f"  질문 {tot} · 맞힘 {hit} · 못 정함 {none} · 틀림 {tot - hit - none}")
    print("  도구 횟수 분포", sorted(seqs.items()))


if __name__ == "__main__":
    main()
