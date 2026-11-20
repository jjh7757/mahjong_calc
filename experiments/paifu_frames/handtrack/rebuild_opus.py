"""Opus 확대 읽기(표 12-57 · 12-58)로 화료자 손패를 끝에서 거꾸로 복원 → 정답으로 복원한 것과 견주기(2026-11-18 밤, 계획서 3단계 "추가 38").

  python -X utf8 rebuild_opus.py [판 id …]        # 기본 = r12 · r16 · r17 · r19 · r13 (11-19: r15_134151 · L16_135321 도 넣을 수 있음 — 판 id 를 적어서)
  python -X utf8 rebuild_opus.py --json out.json  # 차례별 복원 손패를 파일로(패보 리뷰에 넣을 때)

차례마다 "끝 줄 순서"(시작 줄 번호 1 ~ n 과 뽑은 패 D 로 적은 차례 끝 줄)를 쓴다:
- Opus: answer.json 의 end_order(옮김 · 맞바꿈까지 들어 있음).
- 정답: truth_r13 의 order, 없으면 k_id · j_closed 로 짓고 moves(끝 줄 a ↔ b 맞바꿈)를 적용.
- Opus 가 안 읽은 차례(쯔모기리 · r19 4순)는 두 쪽 다 정답 순서 — 그래서 이 비교는 "손에서 낸 차례의 칸 읽기" 만 바꾼 효과다(종류는 정답을 씀).
거꾸로: 차례 끝 줄 after → 시작 줄 before[i] = after[i 가 선 자리], 버린 패(빠진 번호) 자리에 강의 패, D 자리의 패 = 뽑은 패.
정렬 검사: 끝 손패에서 읽은 정렬(replay.sort_scheme)로 시작 줄의 이웃 어긋남을 셈 — 복원이 틀리면 늘어나는 간접 증거.
11-19 특수 차례(추가 50): 정답 kind "call"(L16 2순 울기) — 끝 줄 10장 + 손에서 울기로 간 패(game.json meld_detail 의 가로 아닌 것) + 버린 패 → 시작 13장,
  뽑은 패 없음, 끼우는 자리는 정렬로 짐작(묶음만 확실). kind "unseen"(r15 3순 "처음부터 뽑은 상태임, 6번 버림") — 정답에 칸 순서가 없어
  순서 그대로(뽑은 패 = 버린 패)로 셈(묶음 "시작 + 뽑은 패" 만 확실, 시작 줄 · 뽑은 패를 가르는 건 짐작). --full 에선 둘 다 출처 "정답(특수)".
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import sam2track as s1  # noqa: E402
from replay import key, sort_scheme  # noqa: E402

GAMES = ["r12_131655", "r16_135321", "r17_140450", "r19_142013", "r13_132644"]
OP = hc.WORK / "opusread_1118"


def truth_order(u: dict, n: int) -> list:
    if u.get("order"):
        return [str(x) for x in u["order"]]
    if u.get("kind") != "hand":
        return [str(i) for i in range(1, n + 1)]
    lst = [str(i) for i in range(1, n + 1) if i != u["k_id"]]
    lst.insert(u["j_closed"] - 1, "D")
    for a, b in u.get("moves") or []:
        lst[a - 1], lst[b - 1] = lst[b - 1], lst[a - 1]
    return lst


def back(after: list, order: list, river: str):
    """차례 끝 줄 after(패) + 끝 줄 순서 → (시작 줄, 뽑은 패)."""
    n = len(after)
    before = [None] * n
    drawn = None
    for p, lab in enumerate(order):
        if lab == "D":
            drawn = after[p]
        else:
            before[int(lab) - 1] = after[p]
    gone = [i for i, v in enumerate(before) if v is None]
    if len(gone) == 1:                       # 손에서 냄: 빠진 번호 = 버린 패
        before[gone[0]] = river
    elif not gone and drawn is None:         # 쯔모기리(순서 그대로): 뽑은 패 = 버린 패
        drawn = river
    else:
        raise ValueError(f"끝 줄 순서가 온전하지 않음: {order}")
    return before, drawn


SPECIAL = ("call", "unseen")   # 11-19 r15 · L16: 정답 kind 가 이것이면 API · 하위 에이전트로 안 읽음 → 정답으로 채우고 src "정답(특수)"


def call_hand_tiles(game: dict, t: dict) -> list:
    """울기 차례 t 에서 손에서 나간 패 — game.json final_hand meld_detail 의 이 차례 몫(turns.json meld_tiles [앞, 뒤] 조각)에서
    가로로 놓인 1장(남의 강에서 받은 패)을 뺀 나머지. 퐁 · 치 = 2장, 다이밍캉 = 3장. 가로 패가 정확히 1장이 아니면 멈춤."""
    m0, m1 = t["meld_tiles"]
    md = game["final_hand"]["meld_detail"][m0:m1]
    side = [d for d in md if d.get("sideways")]
    if len(md) != m1 - m0 or len(side) != 1:
        raise ValueError(f"{t['id']}: 울기 조각 meld_detail[{m0}:{m1}] 가 {len(md)}장 · 가로 {len(side)}장 — 손에서 나간 패를 못 정함")
    return [d["tile"] for d in md if not d.get("sideways")]


def back_call(after: list, gone: list, sch: dict) -> list:
    """울기 차례 거꾸로: 차례 끝 줄 after(울기 · 버림 뒤) + 손에서 나간 패(울기로 간 패 + 버린 패) → 시작 줄.
    정답에 울기 차례의 칸 순서가 없어서(kind "call" · tile 만) 나간 패를 끝 손패 정렬(sort_scheme)이 놓을 자리에 끼운다 —
    이 순서는 짐작이고, 손패 묶음(Counter)만 확실하다. 정렬 키가 없는 패(그 무늬가 끝 손패에 없음 · 자패 등)는 줄 끝에."""
    row = list(after)
    for v in gone:
        k = key(v, sch)
        pos = len(row) if k is None else next((i for i, x in enumerate(row) if key(x, sch) is not None and key(x, sch) > k), len(row))
        row.insert(pos, v)
    return row


def rebuild(gid: str, src: str):
    truth = s1.truth_all()
    game = hc.jload(hc.OUT / gid / "game.json")
    g = next(x for x in hc.jload(hc.WORK / "testtruth_1116" / "turns.json")["games"] if x["id"] == gid)
    row = list(game["final_hand"]["closed"])
    sch = sort_scheme(row)
    rows = []
    rule = set()                       # 리치 선언(강에 가로) 뒤 차례 = 규칙상 쯔모기리 — 정답이 아니라 강 사진에서 온 값
    riichi = False
    for t in g["turns"]:
        if riichi:
            rule.add(t["id"])
        if t.get("sideways"):
            riichi = True
    for t in reversed(g["turns"]):
        u = truth.get(t["id"]) or {}
        f = OP / t["id"] / "answer.json"
        n = len(row)                   # 11-19: 차례 끝 줄 장수(울기 뒤면 10) — 전에는 끝 손패 장수로 고정
        if n != t["n_calc"] - ((t["meld_tiles"][1] - t["meld_tiles"][0]) if u.get("kind") == "call" else 0):   # 울기: 시작 − (울기 장수) = 끝
            raise ValueError(f"{t['id']}: 복원 줄 {n}장인데 turns.json n_calc {t['n_calc']}(kind {u.get('kind')})")
        used = "정답"
        if u.get("kind") == "call":    # 11-19 L16 2순: 울기(퐁 · 치) — 뽑기 없음, 손에서 울기 패 + 버린 패가 나감
            before = back_call(row, call_hand_tiles(game, t) + [t["tile"]], sch)
            ks = [key(v, sch) for v in before]
            bad = sum(1 for i in range(len(before) - 1) if ks[i] is not None and ks[i + 1] is not None and ks[i] > ks[i + 1])
            rows.append({"id": t["id"], "label": t.get("label"), "river": t["tile"], "drawn": None, "before": before, "after": list(row),
                         "src": "정답(특수)" if src == "full" else used, "order": None, "sort_bad": bad, "special": "call"})
            row = before
            continue
        if src == "full":              # 추가 39: 정답 없이 — 리치 뒤는 규칙, 나머지는 모두 Opus(종류까지)
            if t["id"] in rule:
                order, used = [str(i) for i in range(1, n + 1)], "규칙"
            elif u.get("kind") in SPECIAL:   # unseen(r15 3순) — 정답으로 채움(추가 50). 아래 truth_order 가 순서 그대로(뽑은 패 = 버린 패)로 셈
                order, used = truth_order(u, n), "정답(특수)"
            elif f.exists():
                ans = hc.jload(f)
                ident = [str(i) for i in range(1, n + 1)]
                eo = [str(x) for x in ans.get("end_order") or []]
                if ans.get("kind") == "hand":
                    order = eo
                elif ans.get("kind") == "tsumogiri" and sorted(eo, key=int if all(x.isdigit() for x in eo) else str) == ident:
                    order = eo         # 11-19(추가 50, 세션 결정): 쯔모기리하며 줄을 바꾼 차례(r15 14순) — end_order 가 1..n 온전한 순열(D 없음)이면 그 순서
                else:
                    order = ident
                used = "Opus" + ("" if ans.get("kind") == "hand" else "(쯔모)")
            else:
                raise SystemExit(f"{t['id']}: Opus 답 없음 — 정답 없이 복원 못 함")
        elif src == "opus" and f.exists():
            order = [str(x) for x in hc.jload(f)["end_order"]]
            used = "Opus"
        else:
            order = truth_order(u, n)
        before, drawn = back(row, order, t["tile"])
        ks = [key(v, sch) for v in before]
        bad = sum(1 for i in range(n - 1) if ks[i] is not None and ks[i + 1] is not None and ks[i] > ks[i + 1])
        r = {"id": t["id"], "label": t.get("label"), "river": t["tile"], "drawn": drawn, "before": list(before), "after": list(row), "src": used, "order": order, "sort_bad": bad}
        if u.get("kind") in SPECIAL:
            r["special"] = u["kind"]
        rows.append(r)
        row = before
    return list(reversed(rows)), sch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("games", nargs="*")
    ap.add_argument("--json")
    ap.add_argument("--full", action="store_true", help="추가 39: 정답 없이(리치 뒤 규칙 + 나머지 모두 Opus)")
    ap.add_argument("--root", default="opusread_1118", help="_work 아래 Opus 답 폴더(11-20: rawread_r15L16_1120 — SAM 2 없는 읽기)")
    a = ap.parse_args()
    global OP
    OP = hc.WORK / a.root
    out = {}
    tot = Counter()
    for gid in a.games or GAMES:
        ro, _ = rebuild(gid, "full" if a.full else "opus")
        rt, sch = rebuild(gid, "truth")
        out[gid] = {"opus": ro, "truth": rt}
        print(f"\n== {gid} (정렬 {sch})")
        print("순 | 읽기 | 뽑은 패 O/T | 시작 손패 같음(줄 · 패 묶음) | 정렬 어긋남 O/T | Opus 시작 손패")
        for o, t in zip(ro, rt):
            same_row = o["before"] == t["before"]
            same_set = Counter(o["before"]) == Counter(t["before"])
            tot["turns"] += 1
            tot["row"] += same_row
            tot["set"] += same_set
            tot["drawn"] += o["drawn"] == t["drawn"]
            tot["opus_turns"] += o["src"] == "Opus"
            print(f"{o['label']!s:>3} | {o['src']:4s} | {o['drawn']}/{t['drawn']}{'' if o['drawn'] == t['drawn'] else ' ✗'} | "
                  f"{'✓' if same_row else '✗'} · {'✓' if same_set else '✗'} | {o['sort_bad']}/{t['sort_bad']} | {' '.join(o['before'])}")
    print(f"\n합: 차례 {tot['turns']}(Opus 읽기를 쓴 차례 {tot['opus_turns']}) · 시작 손패 줄까지 같음 {tot['row']} · 패 묶음 같음 {tot['set']} · 뽑은 패 같음 {tot['drawn']}")
    if a.json:
        hc.jsave(Path(a.json), out)


if __name__ == "__main__":
    main()
