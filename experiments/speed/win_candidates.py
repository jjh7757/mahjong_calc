"""손패만으로 가능한 화료패가 몇 개인가, 하나뿐이면 그걸 답으로 해도 되나(2026-11-01, 사용자 제안). API 호출 없음.

  정답 손패: 매장 25장 중 화료패를 아는 장면. 13장(화료패 뺌)의 대기 수, 정답 화료패가 대기에 있는지.
  실제 읽은 손패: wide_pieces.json 의 운영 /v2/seat 답(같은 순간 측정). 비공개 + 울기×3 이 13 이면 대기를 구한다.
    대기 하나 → 그 패를 답으로, 여럿 → 후보를 보여 준다. 답·후보에 정답 손패·화료패가 맞는지 본다.
울기와 표시패에 4장 다 보이는 패는 대기에서 뺀다.
  python -X utf8 experiments/speed/win_candidates.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
import visit_truth_check as vc  # noqa: E402

VISIT = ROOT / "experiments/visit_20261031"


def norm(ts):
    return [vc.norm(t) for t in ts]


def waits(hand: list[str], melds: list[str], seen: list[str]) -> list[str]:
    c = Counter(norm(hand + [t for m in melds for t in m.split()] + seen))
    return [t for t in vc.waits(hand) if c[t] < 4]


def truth_rows() -> list[dict]:
    truth = json.loads((VISIT / "truth.json").read_text(encoding="utf-8"))["scenes"]
    rows = []
    for d in sorted((VISIT / "captures").glob("20261031_1*")):
        if d.name.endswith("_track") or d.name < "20261031_12":
            continue
        if d.name in truth:
            t = truth[d.name]
            rows.append(dict(name=d.name, hand=t["hand"].split(), melds=t["melds"], win=t.get("win_tile"), tsumo=t.get("is_tsumo"), seen=t.get("indicators", [])))
        elif (d / "label.json").exists():
            lab = json.loads((d / "label.json").read_text(encoding="utf-8"))
            closed = list(lab["closed"])
            closed.remove(lab["win_tile"])
            rows.append(dict(name=d.name, hand=closed, melds=[x.strip("[]") for x in lab["melds"]], win=lab["win_tile"], tsumo=lab["is_tsumo"], seen=lab["dora_indicators"] + lab["ura_indicators"]))
    return rows


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = truth_rows()
    dist = Counter()
    print("-- 정답 손패 기준(화료패를 뺀 13장)")
    for r in rows:
        total = len(r["hand"]) + 3 * len(r["melds"])
        win = r["win"]
        hand = list(r["hand"])
        if total == 14:
            if not win:
                print(r["name"][-6:], "14장, 화료패 모름(건너뜀)")
                continue
            hand.remove(win)
        w = waits(hand, r["melds"], r["seen"])
        dist[len(w)] += 1
        r["hand13"], r["waits"] = hand, w
        print(r["name"][-6:], "대기", w, "정답", win, "포함" if win and vc.norm(win) in w else "모름" if not win else "없음!")
    print("대기 수 분포", dict(sorted(dist.items())), "\n")

    by = {r["name"]: r for r in rows}
    seat = [r for r in json.loads((ROOT / "experiments/speed/results/wide_pieces.json").read_text(encoding="utf-8")) if r["set"] == "visit"]
    print("-- 실제 읽은 손패 기준(운영 /v2/seat 답)")
    tally = Counter()
    for r in seat:
        t = by[r["name"]]
        s = r["seat"]
        hand = s.get("hand", []) + s.get("sep", [])
        n = len(hand) + 3 * len(s.get("melds", []))
        part = "오전" if r["name"] < "20261031_14" else "오후"
        tally[part, "n"] += 1
        if n != 13:
            tally[part, "13장 아님"] += 1
            print(r["name"][-6:], f"{n}장, 후보 안 냄")
            continue
        w = waits(hand, s["melds"], t["seen"])
        tkey = lambda ms: sorted(" ".join(sorted(m.split())) for m in ms)
        h13 = t.get("hand13")
        hand_ok = h13 is not None and sorted(hand) == sorted(h13) and tkey(s["melds"]) == tkey(t["melds"])
        win = t["win"]
        if not w:
            kind = "대기 0"
        elif len(w) == 1:
            kind = "하나 맞음" if hand_ok and win and vc.norm(win) == w[0] else "하나 틀림" if win or not hand_ok else "하나 모름"
        else:
            kind = "여럿 맞음" if hand_ok and win and vc.norm(win) in w else "여럿 틀림" if win or not hand_ok else "여럿 모름"
        tally[part, kind] += 1
        print(r["name"][-6:], "후보", w, "정답", win, "손패", "맞음" if hand_ok else "틀림", kind)
    print()
    for part in ("오전", "오후"):
        print(part, {k[1]: v for k, v in sorted(tally.items()) if k[0] == part})


if __name__ == "__main__":
    main()
