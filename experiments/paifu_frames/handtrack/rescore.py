"""저장된 답(규칙 결과 json · LLM 답 json)을 옛 정답 / 고친 들어간 칸 정답(insert_truth_1116.json)으로 나란히 다시 채점(2026-11-16).

  python -X utf8 rescore.py [--out 파일]
새로 돌리는 판정은 없다 — 답은 그대로, 정답만 바뀐다. 맞음 · 틀림 · 없음(모름) 으로 통일해 셈.
"""
from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import pixtrack as pt  # noqa: E402

W = hc.WORK
L = W / "llmtext_1116"
RULES = [  # (이름, 파일)
    ("색 덩어리 규칙 v1", W / "pixtrack_v1.json"),
    ("색 덩어리 규칙 v5", W / "pixtrack_v5.json"),
    ("검출기 규칙 v5", W / "dettrack_rule.json"),
    ("색 덩어리 v6 규칙", W / "pixtrack_v6.json"),
    ("검출기 v6 규칙", W / "dettrack_rule_v6.json"),
    ("색 덩어리 v6 규칙 v7", W / "pixtrack_v7.json"),
    ("검출기 v6 규칙 v7", W / "dettrack_rule_v7.json"),
]
LLMS = [  # (이름, 폴더, 답 파일)
    ("색 덩어리 Haiku 글", L / "llm", "ans_haiku.json"),
    ("색 덩어리 Sonnet 글", L / "llm", "ans_sonnet.json"),
    ("검출기 Sonnet 글", L / "llmdet", "ans_sonnet.json"),
    ("색 덩어리 Sonnet 글 + 흐름", L / "llmflow", "ans_sonnet.json"),
]
_T = {}


def tmap(gid):
    if gid not in _T:
        rp = hc.jload(glob.glob(str(hc.OUT / gid / "replay2_B" / "*.json"))[0])
        _T[gid] = {t["t"]: t for t in rp["turns"]}
    return _T[gid]


def truth(gid, t, old):
    pt.OLD_TRUTH = old
    try:
        return pt.truth_of(gid, tmap(gid)[t])
    finally:
        pt.OLD_TRUTH = False


def score(pairs):
    """pairs = [(정답, 답, 꼬리표)] → 수 + 들어간 칸 낱낱."""
    c = dict(mode=[0, 0, 0], k=[0, 0, 0], j=[0, 0, 0], jc=[0, 0])
    detail = []

    def add(key, want, got):
        c[key][0 if got == want else 2 if got is None else 1] += 1

    for T, G, tag in pairs:
        if T["mode"]:
            add("mode", T["mode"], None if G.get("mode") == "모름" else G.get("mode"))
        if T["mode"] == "손에서" and T["k"]:
            add("k", T["k"], G.get("k"))
        if T["mode"] == "손에서" and T["j"]:
            add("j", T["j"], G.get("j"))
            detail.append(f"{tag} {T['j']}→{G.get('j')}")
        if T.get("j_cands"):
            c["jc"][1] += 1
            c["jc"][0] += G.get("j") in T["j_cands"]
            detail.append(f"{tag} {T['j_cands']}→{G.get('j')}")
    return c, detail


def fmt(c):
    f = lambda x: " · ".join(map(str, x)) + f" /{sum(x)}"  # noqa: E731
    return f"모드 {f(c['mode'])} | 나간 칸 {f(c['k'])} | 들어간 칸 {f(c['j'])} | 후보 안 {c['jc'][0]}/{c['jc'][1]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    a = ap.parse_args()
    res = []
    for name, f in RULES:
        if not f.exists():
            print(name, "— 파일 없음", f.name)
            continue
        rows = hc.jload(f)
        out = {}
        for old in (True, False):
            out[old] = score([(truth(r["game"], r["t"], old), r["got"], f"{r['game'][:3]}-{r['t']}") for r in rows])
        stored = score([(r["truth"], r["got"], "") for r in rows])[0]
        res.append({"name": name, "file": f.name, "old": out[True][0], "new": out[False][0], "new_j": out[False][1], "stored_same_as_old": stored == out[True][0]})
    for name, d, af in LLMS:
        idx = hc.jload(d / "index.json")
        ans = {x["id"]: x for x in hc.jload(d / af)}
        out = {}
        for old in (True, False):
            T = {i["id"]: truth(i["game"], i["t"], old) for i in idx}
            out[old] = score([(T[i["id"]], ans.get(i["id"], {"mode": "모름"}), f"{i['game'][:3]}-{i['t']}") for i in idx])
            if not old:
                hc.jsave(d / "truth_fix1116.json", T)
        stored_T = hc.jload(d / "truth.json")
        stored = score([(stored_T[i["id"]], ans.get(i["id"], {"mode": "모름"}), "") for i in idx])[0]
        res.append({"name": name, "file": f"{d.name}/{af}", "old": out[True][0], "new": out[False][0], "new_j": out[False][1], "stored_same_as_old": stored == out[True][0]})
    for r in res:
        print(f"{r['name']}  ({r['file']}){'' if r['stored_same_as_old'] else '  ※ 저장된 정답과 옛 정답 채점이 다름'}")
        print("   옛 정답:", fmt(r["old"]))
        print("   고친 정답:", fmt(r["new"]))
        print("   들어간 칸 낱낱(정답→답):", ", ".join(r["new_j"]))
    if a.out:
        hc.jsave(a.out, res)


if __name__ == "__main__":
    main()
