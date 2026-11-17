"""사용자 답(answers_user.json)과 두 번째 읽기(second/read_<판>_<몫>.json)를 차례마다 맞대기(2026-11-17, 계획서 "추가 8").
두 번째 읽기가 다 끝난 뒤에만 돌린다(그 전에 사용자 답을 화면에 찍지 않으려고).

  python -X utf8 truthcompare.py <판 id> [--out 파일]
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402

BASE = hc.WORK / "testtruth_1116"
KIND = {"tsumogiri": "쯔모기리", "hand": "손에서", "call": "울기 뒤", "unseen": "안 보임", "bad": "구간 이상", None: "안 적음"}


def closed(k, j):
    if j is None or k is None:
        return None
    return j if j <= k else (k if j == k + 1 else j - 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game")
    ap.add_argument("--out")
    a = ap.parse_args()
    g = next(x for x in hc.jload(BASE / "turns.json")["games"] if x["id"] == a.game)
    user = hc.jload(BASE / "answers_user.json")
    second = {}
    for f in sorted((BASE / "second").glob(f"read_{a.game[:3]}_*.json")):
        for t in hc.jload(f)["turns"]:
            second[t["id"]] = t
    c = Counter()
    rows = []
    for t in g["turns"]:
        u, s = dict(user.get(t["id"]) or {}), second.get(t["id"])
        if u.get("insert_first") and u.get("k") is not None and u.get("j") is not None:
            # 사용자가 "먼저 넣고 버림" 으로 적은 차례: 나간 칸은 넣은 패까지 센 번호 → 넣은 패를 뺀 번호로, 들어간 칸은 버린 뒤 번호로 견줌
            u["k_seen"], u["k"] = u["k"], (u["k"] - 1 if u["j"] < u["k"] else u["k"])
            u["_closed"] = u["j"] if u["j"] < u["k_seen"] else u["j"] - 1
        if not u.get("kind") or s is None:
            c["한쪽 없음"] += 1
            rows.append({"id": t["id"], "state": "한쪽 없음", "user": bool(u.get("kind")), "second": s is not None})
            continue
        diff = []
        if u["kind"] != s.get("kind"):
            diff.append("종류")
        else:
            if u["kind"] in ("hand", "call") and u.get("k") != s.get("k"):
                diff.append("나간 칸")
            if u["kind"] == "hand" and u.get("_closed", closed(u.get("k"), u.get("j"))) != closed(s.get("k"), s.get("j")):  # 빈칸을 메운 뒤 번호로 견줌
                diff.append("들어간 칸")
            if u["kind"] == "call" and sorted(u.get("meld_pos") or []) != sorted(s.get("meld_pos") or []):
                diff.append("울기로 뺀 칸")
        state = "갈림" if diff else "같음"
        c[state] += 1
        c["종류 같음"] += u["kind"] == s.get("kind")
        if u["kind"] == s.get("kind") == "hand":
            c["손에서(둘 다)"] += 1
            c["나간 칸 같음"] += u.get("k") == s.get("k")
            c["들어간 칸 같음"] += "들어간 칸" not in diff
        rows.append({"id": t["id"], "state": state, "diff": diff,
                     "user": {k: u.get(k) for k in ("kind", "k", "j", "meld_pos", "unsure", "note")},
                     "second": {k: s.get(k) for k in ("kind", "k", "j", "meld_pos", "unsure", "why")}})
    print(f"{a.game} · 차례 {len(g['turns'])} · " + " · ".join(f"{k} {v}" for k, v in c.items()))
    for r in rows:
        if r["state"] == "같음":
            u = r["user"]
            print(f"  {r['id']} 같음: {KIND[u['kind']]}" + (f" k={u['k']} j={u['j']}" if u["kind"] == "hand" else "") + (f" 뺀 칸 {u['meld_pos']} k={u['k']}" if u["kind"] == "call" else ""))
        elif r["state"] == "갈림":
            u, s = r["user"], r["second"]
            print(f"  {r['id']} 갈림({', '.join(r['diff'])}):")
            print(f"      사용자: {KIND[u['kind']]} k={u['k']} j={u['j']} 뺀 칸 {u['meld_pos']}{' (확신 없음)' if u['unsure'] else ''} | {u['note']}")
            print(f"      둘째:   {KIND.get(s['kind'], s['kind'])} k={s['k']} j={s['j']} 뺀 칸 {s['meld_pos']}{' (확신 없음)' if s['unsure'] else ''} | {s['why']}")
        else:
            print(f"  {r['id']} 한쪽 없음: 사용자 {'있음' if r['user'] else '없음'} · 둘째 {'있음' if r['second'] else '없음'}")
    if a.out:
        hc.jsave(Path(a.out), {"game": a.game, "count": dict(c), "rows": rows})


if __name__ == "__main__":
    main()
