"""서로 다른 두 판독기(Gemini 차례 읽기 · Opus 두 번째 읽기)가 갈리는 차례만 사람이 본다면(2026-11-17, 새 호출 없음 — 저장된 답만).

  python -X utf8 ensemble.py
두 답은 이 물음을 떠올리기 전에 만들어진 것이라 여기에 맞춰 고친 것이 없다. 정답 = truth_final.json(2반장 24차례).
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402

BASE = hc.WORK / "testtruth_1116"


def closed(k, j):
    if j is None or k is None:
        return None
    return j if j <= k else (k if j == k + 1 else j - 1)


def main():
    truth = hc.jload(BASE / "truth_final.json")
    gem, opus = {}, {}
    for f in (hc.WORK / "gemturn_1117" / "answers").glob("*_r1.json"):
        for r in hc.jload(f)["rows"]:
            gem[r["id"]] = {"kind": r["kind"], "k": r.get("k"), "jc": r.get("j")}
    for f in (BASE / "second").glob("read_*.json"):
        for t in hc.jload(f)["turns"]:
            opus[t["id"]] = {"kind": t["kind"], "k": t.get("k"), "jc": closed(t.get("k"), t.get("j")), "unsure": bool(t.get("unsure"))}
    c = Counter()
    print("차례 | 정답 | Gemini | Opus 둘째 읽기 | 둘이 | 사람이 보면")
    for i, u in truth.items():
        g, o = gem[i], opus[i]

        def right(a, strict_k):
            if a["kind"] != u["kind"]:
                return False
            if u["kind"] != "hand":
                return True
            kok = a["k"] == u["k_id"] if strict_k else a["k"] in (u["k_id"], u["k_pos"])
            return kok and a["jc"] == u["j_closed"]
        gr, orr = right(g, True), right(o, False)
        same = g["kind"] == o["kind"] and (g["kind"] != "hand" or (g["k"] == o["k"] and g["jc"] == o["jc"]))
        flag = (not same) or o["unsure"]
        c["Gemini 맞음"] += gr
        c["Opus 맞음(자리 기준 허용)"] += orr
        c["갈리거나 확신 없음 → 사람"] += flag
        c["사람에게 간 것 중 Gemini 가 틀렸던 것"] += flag and not gr
        c["안 갈렸는데 Gemini 가 틀림(조용한 틀림)"] += (not flag) and not gr
        c["끝 결과 맞음(갈린 차례는 사람이 맞힌다고 봄)"] += flag or gr
        show = lambda a: f"{a['kind']}" + (f" {a['k']} {a['jc']}" if a["kind"] == "hand" else "")
        tr = u["kind"] + (f" {u['k_id']}{'/' + str(u['k_pos']) if u['k_pos'] != u['k_id'] else ''} {u['j_closed']}" if u["kind"] == "hand" else "")
        print(f"{i} | {tr} | {show(g)} {'✓' if gr else '✗'} | {show(o)}{' ?' if o['unsure'] else ''} {'✓' if orr else '✗'} | {'같음' if same else '갈림'} | {'사람' if flag else '-'}")
    print(f"차례 {len(truth)} · " + " · ".join(f"{k} {v}" for k, v in c.items()))


if __name__ == "__main__":
    main()
