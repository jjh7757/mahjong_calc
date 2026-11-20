"""읽기 갈림이 차례별 14장 묶음(시작 13장 + 뽑은 패)을 바꾸는가 — 저장된 읽기만으로 세기(2026-11-20).

  python -X utf8 branchcount.py        # 콘솔 표 + _work/branchcount_1120/result.json

기준 가지 = rebuild_opus.rebuild(gid, "truth") 의 rows. 갈림 = (차례 id, 기준과 다른 끝 줄 순서) — 저장된 읽기에서 모음:
- <폴더>/<차례>/answer.json: opusread_1118 · rawread_1120 · rawhand_1120 · sonnetread_1118 · claudeagent_1119/c1_as_answer
- claudeagent_1119/<변형>/<차례>.json(dry* · c1_as_answer 빼고) · geminiagent_1118/<변형>/<차례>.json — 답은 "answer" 필드
- idsolve_1120/<차례>.json: end_order, alts(어느 프레임의 배정 후보 — perm 은 "고른 이름 → 후보 이름") 를 끝 줄에 이름 바꾸기로
  적용하고, 그렇게 만든 순서의 kind · k · j 가 alts 에 적힌 kind · k · j 와 같을 때만 넣음(다르면 건너뜀)
- 글 후보: unsure 답의 why 에 다른 순서가 분명히 적힌 것만 손으로 옮긴 표 TEXT_CANDS(아래, 근거 글 일부를 주석으로)
순서 고르기 = rebuild_opus.rebuild 의 src "full" 분기와 같음(hand → end_order, tsumogiri 인데 1..n 온전한 순열이면 그것, 아니면 순서 그대로).
갈림 하나마다 그 차례만 바꿔 끝 손패에서 거꾸로(rebuild_opus.back), 나머지 차례는 기준 order.
1순(r12 · r17 · r19 · r13): firstturn 의 drawn_slot(user_confirm 우선) = 2순 시작 줄 칸 번호 — 갈림 가지에도 같은 칸 번호.
  1순 14장 = 2순 시작 줄 + 1순 버린 패, 배패 13 = 2순 시작 줄 − 그 칸 + 1순 버린 패, 1순 뽑은 패 = 2순 시작 줄[칸 − 1].
  1순 갈림 = answer.json candidates 의 다른 칸(출처 "1순 후보"). 1순은 시작 줄 순서를 모르므로 (d) 는 1순에 안 셈.
비교(갈림 가지 대 기준, 차례마다): (a) 14장 묶음 (b) 시작 13장 묶음 (c) 뽑은 패 (d) 시작 줄 순서.
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import firstturn as ft  # noqa: E402
import rebuild_opus as ro  # noqa: E402

MAIN = ["r12_131655", "r17_140450", "r19_142013", "r13_132644"]
EXTRA = ["r16_135321"]
OUTD = hc.WORK / "branchcount_1120"
ANSWER_DIRS = ["opusread_1118", "rawread_1120", "rawhand_1120", "sonnetread_1118", "claudeagent_1119/c1_as_answer"]

A = "D 1 13 3 4 6 5 7 8 9 10 11 2".split()
B = "1 D 13 3 4 6 5 7 8 9 10 11 2".split()
C = "1 D 13 3 4 5 6 7 8 9 10 11 2".split()
# 글 후보: (출처 폴더, 차례, 후보 순서). unsure 답의 why 에 다른 순서가 분명히 적힌 것만.
TEXT_CANDS = [
    ("opusread_1118", "r16_d13", B),                 # "D 가 1 의 왼쪽인지 오른쪽인지 … 직접 보이지 않아 j=1 은 70% 남짓"
    ("claudeagent_1119/c1", "r16_d13", A),           # "D 가 1번째였는지 2번째였는지 … 확실하지 않고"
    ("claudeagent_1119/c1", "r16_d13", C),           # "… 원래 5·6 의 순서가 바뀌었는지도 확실하지 않다"
    ("claudeagent_1119/c2", "r16_d13", A),           # "D appears to go in between tiles 1 and 2 … hand hid this, so I'm not certain"
    ("claudeagent_1119/e1", "r16_d13", B),           # "tile 1 being slid left and D put second can't be ruled out, and then j would be 2"
    ("claudeagent_1119/e2", "r16_d13", B),           # "can't fully rule out D in 2nd place with tile 1 moved left"
    ("claudeagent_1119/k1", "r16_d13", B),           # "If it went between 1 and 2, … the order would start 1, D"
    ("claudeagent_1119/k2", "r16_d13", B),           # "1번이 왼쪽으로 밀리고 D가 그 자리에 들어갔을 가능성도 있다"
    ("claudeagent_1119/m1", "r16_d13", C),           # "could also have gone back to its original spot (row would then end …4, 5, 6, 7…)"
    ("claudeagent_1119/m2", "r16_d13", A),           # "hands cover the exact spot where D went in (54–59)" — 다른 쪽 = 맨 왼쪽
    ("claudeagent_1119/m2", "r16_d13", C),           # "… and the swap of 6 and 5 (169–176)" — 다른 쪽 = 안 바꿈
    ("claudeagent_1119/m2b", "r16_d13", C),          # "D가 1번 뒤에 들어갔을 가능성도 남아"
    ("claudeagent_1119/c2", "r16_d16", "1 2 3 4 5 6 D 7 8 9 10 11 12".split()),   # "096의 밀림을 직접 확인할 수는 없고"(080 줄 1~6,D,7~13)
    ("claudeagent_1119/e2", "r16_d08", "1 D 2 3 4 5 6 7 8 9 10 11 13".split()),   # "1번 패를 D 자리로 옮기고 D 를 1번 자리에 넣었을 가능성"
    ("claudeagent_1119/m2", "r16_d08", "1 D 2 3 4 5 6 7 8 9 10 11 13".split()),   # "D가 1번과 2번 사이에 끼워졌을 가능성"
    ("claudeagent_1119/m1", "r13_d02", "1 D 2 3 5 6 7 8 9 10 11 12 13".split()),  # "D 위치(j=3)는 추적 색이 가리키는 2번째 자리와 달라서"
    ("claudeagent_1119/m1", "r16_d01", "1 2 3 4 5 6 7 8 9 10 11 12 D".split()),   # "… 되돌림'이었다면 D는 13번째가 되므로"
    ("claudeagent_1119/m1b", "r16_d01", "1 2 3 4 5 6 7 8 9 10 12 D 11".split()),  # "끝 순서가 1~10, 12, D, 11이 된다"
]
# unsure 인데 다른 순서를 글에서 모호함 없이 못 만든 것(건너뜀)
TEXT_SKIPPED = [
    ("claudeagent_1119/c1", "r16_d08", "다른 자리를 안 적음(\"not certain\" 만)"),
    ("claudeagent_1119/c1", "r16_d13", "\"또는 1·2 를 함께 옮겼는지\" 부분 — 순서 안 적힘(나머지 두 후보는 넣음)"),
    ("claudeagent_1119/e2", "r13_d02", "j=3 이 70% 미만이라고만, 다른 자리 안 적음"),
    ("claudeagent_1119/k1", "r16_d16", "4·5·6 이 어떻게 움직였는지 모름 — 순서 안 적힘"),
    ("claudeagent_1119/m1", "r17_d11", "흐림으로 확신 없음 — 다른 순서 안 적힘"),
    ("claudeagent_1119/m1b", "r16_d08", "\"1번이 함께 움직였는지\" — 순서 안 적힘"),
    ("claudeagent_1119/m1b", "r16_d13", "unsure 인데 why 에 다른 순서 없음"),
    ("claudeagent_1119/smoke", "r16_d13", "버림 뒤를 안 봤다고만 — 순서 안 적힘"),
]


def family(src: str) -> str:
    if src == "1순 후보":
        return "1순 후보"
    if src.endswith(" 후보") and not src.startswith("idsolve"):
        return "글 후보"
    if src.startswith("idsolve"):
        return "idsolve(규칙 풀이)"
    if src.split("/")[0] in ("opusread_1118", "rawread_1120", "rawhand_1120"):
        return "Opus 하위 에이전트"
    if src.startswith("sonnetread"):
        return "Sonnet 하위 에이전트"
    if src.startswith("claudeagent"):
        return "Claude API"
    if src.startswith("geminiagent"):
        return "Gemini API"
    return "?"


def pick(ans: dict, n: int) -> list:
    """rebuild_opus.rebuild 의 src == "full" 분기와 같은 규칙."""
    ident = [str(i) for i in range(1, n + 1)]
    eo = [str(x) for x in ans.get("end_order") or []]
    if ans.get("kind") == "hand":
        return eo
    if ans.get("kind") == "tsumogiri" and sorted(eo, key=int if all(x.isdigit() for x in eo) else str) == ident:
        return eo
    return ident


def kkj(order: list, n: int):
    if "D" in order:
        nums = {x for x in order if x != "D"}
        miss = [i for i in range(1, n + 1) if str(i) not in nums]
        return "hand", (miss[0] if len(miss) == 1 else None), order.index("D") + 1
    return "tsumogiri", None, None


def valid(order: list, n: int) -> bool:
    if len(order) != n or len(set(order)) != n:
        return False
    ok = {str(i) for i in range(1, n + 1)} | {"D"}
    return set(order) <= ok and sum(1 for x in order if x != "D") >= n - 1


def back_all(gid: str, base: list, override: dict) -> list:
    """끝 손패에서 거꾸로 — override 의 차례만 그 순서, 나머지는 기준 order."""
    row = list(hc.jload(hc.OUT / gid / "game.json")["final_hand"]["closed"])
    out = []
    for r in reversed(base):
        order = override.get(r["id"], r["order"])
        if not valid(order, len(row)):
            raise ValueError(f"{r['id']}: 순서 꼴이 안 맞음 {order}")
        before, drawn = ro.back(row, order, r["river"])
        out.append({"id": r["id"], "label": str(r["label"]), "river": r["river"], "order": list(order),
                    "before": list(before), "drawn": drawn, "after": list(row)})
        row = before
    return list(reversed(out))


def first_turn(gid: str, rows: list, slot: int) -> dict:
    disc = ft.GAMES[gid][0]
    b2 = rows[0]["before"]
    return {"id": f"{gid[:3]}_d01(1순)", "label": "1", "drawn": b2[slot - 1],
            "start13": Counter(b2[:slot - 1] + b2[slot:] + [disc]), "set14": Counter(b2 + [disc]), "before": None}


def turn_sets(rows: list, gid: str, slot):
    out = []
    if slot is not None:
        out.append(first_turn(gid, rows, slot))
    for r in rows:
        out.append({"id": r["id"], "label": r["label"], "drawn": r["drawn"], "start13": Counter(r["before"]),
                    "set14": Counter(r["before"]) + Counter([r["drawn"]]), "before": r["before"]})
    return out


def compare(base_t: list, br_t: list) -> dict:
    res = {"a": [], "b": [], "c": [], "d": []}
    for x, y in zip(base_t, br_t):
        assert x["id"] == y["id"]
        if x["set14"] != y["set14"]:
            res["a"].append(x["label"])
        if x["start13"] != y["start13"]:
            res["b"].append(x["label"])
        if x["drawn"] != y["drawn"]:
            res["c"].append(x["label"])
        if x["before"] is not None and x["before"] != y["before"]:
            res["d"].append(x["label"])
    return res


def slots_for(gid: str):
    root = ft.ROOT
    uc = hc.jload(root / "user_confirm.json") if (root / "user_confirm.json").exists() else {}
    a = hc.jload(root / gid / "answer.json")
    base = int(uc[gid]) if gid in uc else int(a["drawn_slot"])
    cands = [int(s) for s in a.get("candidates") or [] if str(s).isdigit() and int(s) != base]
    return base, cands


def collect(base: dict, tid2g: dict):
    """저장된 읽기 → 항목 [(차례, 순서, 출처)], 건너뜀 [(출처, 차례, 이유)], kind 개수."""
    items, skipped, kinds, odd = [], [], Counter(), set()
    nof = {r["id"]: len(r["after"]) for rows in base.values() for r in rows}
    W = hc.WORK

    def add_ans(tid, ans, src):
        kinds[str(ans.get("kind"))] += 1
        if ans.get("kind") not in ("hand", "tsumogiri"):
            skipped.append((src, tid, f"kind {ans.get('kind')!r} — 규칙대로 순서 그대로로 셈(건너뛰지 않음, 참고)"))
            odd.add((tid, src))
        items.append((tid, pick(ans, nof[tid]), src))

    for d in ANSWER_DIRS:
        for f in sorted((W / d).glob("*/answer.json")):
            if f.parent.name in tid2g:
                add_ans(f.parent.name, hc.jload(f), d)
    for root, excl in (("claudeagent_1119", lambda v: v.startswith("dry") or v == "c1_as_answer"),
                       ("geminiagent_1118", lambda v: False)):
        for v in sorted(p for p in (W / root).iterdir() if p.is_dir()):
            if excl(v.name):
                continue
            for f in sorted(v.glob("*.json")):
                if f.stem not in tid2g:
                    continue
                ans = hc.jload(f).get("answer")
                if not isinstance(ans, dict):
                    skipped.append((f"{root}/{v.name}", f.stem, "answer 없음(null) — 읽기 실패"))
                    continue
                add_ans(f.stem, ans, f"{root}/{v.name}")
    for f in sorted((W / "idsolve_1120").glob("*.json")):
        tid = f.stem
        if tid not in tid2g:
            continue
        a = hc.jload(f)
        n = nof[tid]
        add_ans(tid, a, "idsolve_1120")
        eo = [str(x) for x in a.get("end_order") or []]
        for i, alt in enumerate(a.get("alts") or []):
            perm = {str(k): str(v) for k, v in alt["perm"].items()}
            new = [perm.get(x, x) for x in eo]           # 그 프레임부터 이름을 후보대로 바꿔 끝 줄에 적용
            kd, k, j = kkj(new, n)
            same = valid(new, n) and kd == alt.get("kind") and (kd != "hand" or (k == alt.get("k") and j == alt.get("j")))
            if not same:
                skipped.append(("idsolve 후보", tid, f"alts[{i}] perm 적용 → {kd} k{k} j{j}, 적힌 값 {alt.get('kind')} k{alt.get('k')} j{alt.get('j')} — 안 맞음"))
                continue
            if kd == "tsumogiri" and a.get("kind") == "tsumogiri" and sorted(new, key=int) == [str(x) for x in range(1, n + 1)]:
                pass                                       # 쯔모기리 순열 — pick 규칙과 같게 그대로
            items.append((tid, pick({"kind": kd, "end_order": new}, n), "idsolve 후보"))
    for src, tid, order in TEXT_CANDS:
        if tid in tid2g:
            items.append((tid, list(order), f"{src} 후보"))
    for src, tid, why in TEXT_SKIPPED:
        if tid in tid2g:
            skipped.append((f"{src} 글 후보", tid, why))
    return items, skipped, kinds, odd


def diff_note(base_r: dict, br_r: dict, n: int) -> str:
    kb, k1, j1 = kkj(base_r["order"], n)
    kx, k2, j2 = kkj(br_r["order"], n)
    parts = []
    if kb != kx:
        parts.append(f"종류 {kb}→{kx}")
    else:
        if k1 != k2:
            parts.append(f"k {k1}→{k2}")
        if j1 != j2:
            parts.append(f"j {j1}→{j2}")
    if not parts:
        parts.append("나머지 순서만")
    if base_r["drawn"] != br_r["drawn"]:
        parts.append(f"그 차례 뽑은 패 {base_r['drawn']}→{br_r['drawn']}")
    return " · ".join(parts)


def etype(base_r: dict, br_r: dict, n: int) -> str:
    """읽기 실수 꼴: 종류 / j(뽑은 패 값도 다름) / j(값은 같음) / k 만 / 나머지 순서만."""
    kb, k1, j1 = kkj(base_r["order"], n)
    kx, k2, j2 = kkj(br_r["order"], n)
    if kb != kx:
        return "종류 다름"
    if j1 != j2:
        return "j 다름(그 차례 뽑은 패 값 다름)" if base_r["drawn"] != br_r["drawn"] else "j 다름(뽑은 패 값 같음)"
    if k1 != k2:
        return "k 만 다름"
    return "나머지 패 순서만"


def main():
    OUTD.mkdir(parents=True, exist_ok=True)
    games = MAIN + EXTRA
    base = {}
    for gid in games:
        rows, _ = ro.rebuild(gid, "truth")
        sp = [r["id"] for r in rows if r.get("special")]
        if sp:
            raise SystemExit(f"{gid}: special 차례 {sp} — 멈춤")
        base[gid] = rows
    tid2g = {r["id"]: gid for gid in games for r in base[gid]}

    # 기준 대 기준 확인: 덮어쓰기 없이 거꾸로 돈 것이 rebuild 와 같아야 하고, 비교는 전부 0
    slots = {gid: slots_for(gid) for gid in MAIN}
    bt = {}
    for gid in games:
        mine = back_all(gid, base[gid], {})
        assert [(r["before"], r["drawn"]) for r in mine] == [(r["before"], r["drawn"]) for r in base[gid]], gid
        bt[gid] = turn_sets(mine, gid, slots[gid][0] if gid in slots else None)
        z = compare(bt[gid], turn_sets(mine, gid, slots[gid][0] if gid in slots else None))
        assert not any(z.values()), (gid, z)
    self_check = "기준 대 기준: 다섯 판 모두 a · b · c · d 0"

    items, skipped, kinds, odd = collect(base, tid2g)
    merged = defaultdict(list)
    for tid, order, src in items:
        if src not in merged[(tid, tuple(order))]:
            merged[(tid, tuple(order))].append(src)
    base_order = {r["id"]: tuple(r["order"]) for rows in base.values() for r in rows}
    same_as_base = Counter()
    branches = []
    for (tid, order), srcs in merged.items():
        if order == base_order[tid]:
            for s in srcs:
                same_as_base[family(s)] += 1
            continue
        branches.append({"turn": tid, "game": tid2g[tid], "order": list(order), "srcs": srcs})
    for gid in MAIN:
        for s in slots[gid][1]:
            branches.append({"turn": f"{gid[:3]}_d01(1순)", "game": gid, "order": None, "slot": s, "srcs": ["1순 후보"]})
    order_ix = {r["id"]: i for rows in base.values() for i, r in enumerate(rows)}
    branches.sort(key=lambda b: (games.index(b["game"]), order_ix.get(b["turn"], -1), b["srcs"][0]))

    results, unbuildable = [], []
    for b in branches:
        gid = b["game"]
        slot = slots[gid][0] if gid in slots else None
        if b["order"] is None:                       # 1순 후보: 기준 rows 에 칸만 바꿈
            rows = back_all(gid, base[gid], {})
            slot = b["slot"]
            label = "1"
            b["etype"], b["kind_odd_only"] = "1순 칸", False
            note = f"1순 칸 {slots[gid][0]}→{slot} · 1순 뽑은 패 {rows[0]['before'][slots[gid][0] - 1]}→{rows[0]['before'][slot - 1]}"
        else:
            try:
                rows = back_all(gid, base[gid], {b["turn"]: b["order"]})
            except ValueError as e:
                unbuildable.append({**b, "error": str(e)})
                continue
            i = order_ix[b["turn"]]
            label = base[gid][i]["label"]
            note = diff_note(base[gid][i], rows[i], len(base[gid][i]["after"]))
            b["etype"] = etype(base[gid][i], rows[i], len(base[gid][i]["after"]))
            b["kind_odd_only"] = all((b["turn"], s) in odd for s in b["srcs"])
        cmp_ = compare(bt[gid], turn_sets(rows, gid, slot))
        results.append({**b, "label": str(label), "note": note, "cmp": cmp_,
                        "n": {k: len(v) for k, v in cmp_.items()}, "families": sorted({family(s) for s in b["srcs"]})})

    # 출력
    def short(srcs):
        s = ", ".join(x.replace("claudeagent_1119/", "CA/").replace("geminiagent_1118/", "GA/") for x in srcs)
        return s if len(s) <= 70 else s[:67] + "…"

    print(self_check)
    print(f"\n갈림 {len(results)} (복원 불가 {len(unbuildable)}) — a 14장 묶음 · b 시작 13장 · c 뽑은 패 · d 시작 줄 순서")
    print("판 | 차례 | 출처 | 기준과 다른 점 | a b c d | a 차례 / c 차례 / d 차례")
    for r in results:
        n = r["n"]
        print(f"{r['game'][:3]} | {r['label']:>3} | {short(r['srcs'])} | {r['note']} | {n['a']} {n['b']} {n['c']} {n['d']} | "
              f"a[{' '.join(r['cmp']['a'])}] c[{' '.join(r['cmp']['c'])}] d[{' '.join(r['cmp']['d'])}]")
    for u in unbuildable:
        print(f"복원 불가: {u['turn']} {u['srcs']} {u['order']} — {u['error']}")

    summary = {}
    for name, gs in (("네 판", MAIN), ("r16", EXTRA)):
        rs = [r for r in results if r["game"] in gs]
        zero = [r for r in rs if r["n"]["a"] == 0]
        dist = Counter(r["n"]["a"] for r in rs if r["n"]["a"] > 0)
        fam = defaultdict(lambda: {"갈림": 0, "a0": 0})
        for r in rs:
            for f in r["families"]:
                fam[f]["갈림"] += 1
                fam[f]["a0"] += r["n"]["a"] == 0
        et = defaultdict(lambda: {"갈림": 0, "a0": 0})
        for r in rs:
            et[r["etype"]]["갈림"] += 1
            et[r["etype"]]["a0"] += r["n"]["a"] == 0
        rs2 = [r for r in rs if not r["kind_odd_only"]]
        summary[name] = {"갈림": len(rs), "복원 불가": sum(1 for u in unbuildable if u["game"] in gs),
                         "14장 묶음 안 바뀜": len(zero), "바뀌는 차례 수 분포": dict(sorted(dist.items())),
                         "출처 무리별": {k: dict(v) for k, v in sorted(fam.items())},
                         "실수 꼴별": {k: dict(v) for k, v in sorted(et.items())},
                         "kind 이상(color · sam2) 답만 낸 갈림 뺌": {"갈림": len(rs2), "14장 안 바뀜": sum(1 for r in rs2 if r["n"]["a"] == 0)}}
        print(f"\n== 요약 · {name}: 갈림 {len(rs)} · 복원 불가 {summary[name]['복원 불가']} · 14장 묶음이 한 차례도 안 바뀜 {len(zero)} · "
              f"바뀌는 갈림 {len(rs) - len(zero)}(바뀌는 차례 수: {dict(sorted(dist.items()))})")
        for k, v in sorted(fam.items()):
            print(f"   {k}: 갈림 {v['갈림']} · 14장 안 바뀜 {v['a0']}")
        print("   실수 꼴별:")
        for k, v in sorted(et.items()):
            print(f"     {k}: 갈림 {v['갈림']} · 14장 안 바뀜 {v['a0']}")
        x = summary[name]["kind 이상(color · sam2) 답만 낸 갈림 뺌"]
        print(f"   kind 이상(CA/e1 의 color · sam2) 답만 낸 갈림을 빼면: 갈림 {x['갈림']} · 14장 안 바뀜 {x['14장 안 바뀜']}")
    print(f"\n기준과 같은 순서라 갈림 아님(출처 무리별 읽기 수): {dict(same_as_base)}")
    print(f"읽기 kind 개수: {dict(kinds)}")
    print(f"건너뜀 {len(skipped)}:")
    for s in skipped:
        print(f"   {s[0]} · {s[1]} · {s[2]}")

    # 기대값
    def find(turn, src=None, slot=None):
        for r in results:
            if r["turn"] == turn and (src is None or src in r["srcs"]) and (slot is None or r.get("slot") == slot):
                return r
    exp = []
    r = find("r17_d08", "opusread_1118")
    if r:
        rows = back_all("r17_140450", base["r17_140450"], {"r17_d08": r["order"]})
        d1b = bt["r17_140450"][0]["drawn"]
        d1x = rows[0]["before"][slots["r17_140450"][0] - 1]
        ok = r["n"]["a"] == 0 and r["cmp"]["c"] == ["1"] and (d1b, d1x) == ("0s", "4s") and r["cmp"]["d"] == [str(x) for x in range(2, 9)]
        exp.append(("r17_d08 opusread 갈림", ok, f"a {r['n']['a']} · c {r['cmp']['c']} (1순 기준 {d1b} 대 {d1x}) · d {r['cmp']['d']}"))
    else:
        exp.append(("r17_d08 opusread 갈림", False, "갈림 없음"))
    for gid, s, want in (("r19_142013", 7, ("3s", "5s")), ("r13_132644", 1, ("1z", "1s"))):
        r = find(f"{gid[:3]}_d01(1순)", slot=s)
        b2 = bt[gid][1]["before"]
        got = (b2[slots[gid][0] - 1], b2[s - 1])
        ok = bool(r) and r["n"]["a"] == 0 and got == want
        exp.append((f"1순 후보 {gid[:3]} 칸 {s}", ok, f"뽑은 패 {got[0]} 대 {got[1]} · a {r['n']['a'] if r else '-'}"))
    exp.insert(0, ("기준 대 기준 전부 0", True, self_check))
    print("\n기대값:")
    for name, ok, why in exp:
        print(f"   {'맞음' if ok else '다름'} · {name} · {why}")

    def ser(x):
        return {k: v for k, v in x.items()}
    hc.jsave(OUTD / "result.json", {"summary": summary, "branches": [ser(r) for r in results], "unbuildable": unbuildable,
                                     "skipped": [list(s) for s in skipped], "same_as_base": dict(same_as_base),
                                     "kinds": dict(kinds), "expect": [list(e) for e in exp],
                                     "first_turn_slots": {g: {"base": s[0], "cands": s[1]} for g, s in slots.items()}})
    print(f"\n→ {OUTD / 'result.json'}")


if __name__ == "__main__":
    main()
