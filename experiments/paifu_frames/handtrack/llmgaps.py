"""llmtext 글(turns.txt)의 손에서 낸 차례마다 '한 장 폭 틈' 이 어디에 몇 줄 나왔고, 그때 틈 가장자리에 손이 닿아 있었는지 센다
(2026-11-16, 4단계 흐름 지시문에서 Sonnet 들어간 칸이 나빠진 원인 확인 — metrics 표 12-17, problem_log 66).

  python -X utf8 llmgaps.py <폴더>     # 폴더 안에 llm/(truth.json · ans_sonnet.json) 과 llmflow/(turns.txt · ans_sonnet.json)
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

S = Path(sys.argv[1])
PITCH = 40.0
truth = json.loads((S / "llm/truth.json").read_text(encoding="utf-8"))
orig = {x["id"]: x for x in json.loads((S / "llm/ans_sonnet.json").read_text(encoding="utf-8"))}
flow = {x["id"]: x for x in json.loads((S / "llmflow/ans_sonnet.json").read_text(encoding="utf-8"))}
txt = (S / "llmflow/turns.txt").read_text(encoding="utf-8")
RUN = re.compile(r"([\[\(])([\d.]+)@(\d+)([\]\)])")
HAND = re.compile(r"손 (\d+)~(\d+)")

for blk in re.split(r"^### ", txt, flags=re.M)[1:]:
    tid = blk[:3]
    T = truth[tid]
    if T["mode"] != "손에서":
        continue
    lines = blk.splitlines()[1:]
    ep = defaultdict(lambda: dict(n=0, flag=0, cover=0, t0=None, t1=None, ex=None))
    nframes = 0
    for ln in lines:
        runs = [(m[1] == "(", float(m[2]), int(m[3]), m[4] == ")") for m in RUN.finditer(ln)]
        if not runs:
            continue
        nframes += 1
        h = HAND.search(ln)
        hand = (int(h[1]), int(h[2])) if h else None
        left = 0.0
        for a, b in zip(runs, runs[1:]):
            left += a[1]
            g0, g1 = a[2] + a[1] * PITCH, b[2]
            w = (g1 - g0) / PITCH
            if 0.5 <= w <= 1.6 and b[1] >= 0.6:  # 한 장 폭 틈, 오른쪽에 패가 있음(줄 끝 틈 아님)
                key = round(left)
                e = ep[key]
                e["n"] += 1
                e["flag"] += a[3] or b[0]
                e["cover"] += bool(hand and hand[0] <= g0 + 5 and g1 - 5 <= hand[1])
                e["t0"] = e["t0"] or ln[:7]
                e["t1"] = ln[:7]
                e["ex"] = e["ex"] or ln.strip()
    print(f"\n{tid} 정답 k={T['k']} j={T['j']} 후보={T['j_cands']} | 원래 j={orig[tid]['j']} · 흐름 j={flow[tid]['j']}  ({nframes}줄, {lines[0][:7]}~{lines[-1][:7] if lines[-1] else lines[-2][:7]})")
    print("   흐름 근거:", flow[tid]["why"])
    for key in sorted(ep):
        e = ep[key]
        print(f"   틈 왼쪽 {key}장: {e['n']}줄 {e['t0']}~{e['t1']} · 틈 가장자리 손 닿음 {e['flag']}/{e['n']} · 손 범위 안 {e['cover']}/{e['n']} · 예) {e['ex']}")
