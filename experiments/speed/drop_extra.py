"""탁자 위 낱장까지 읽어 장수가 넘칠 때(예: 16장) 몇 장을 빼면 화료형이 하나로 정해지나(2026-11-01, 사용자 제안). API 호출 없음.

  1) 정답 패로: 표시패를 내놓은 장면에서 손패 + 표시패 전부를 놓고 k 장을 빼 화료형·텐파이가 되는 패 조합 수. 아무 패나 뺄 때 / 낱장만 뺄 때.
  2) 읽은 패로(wide_pieces.json 같은 순간): 줄 + 울기 + 낱장에서 낱장 일부를 받아 화료형(14)이 되는 조합이 하나면 그것, 없으면 낱장 없이 13장 텐파이, 여럿이면 답 없음.
     합침: 운영 답이 13장 + 검사 통과면 운영 줄에 낱장을 같은 규칙으로 더한다. 운영 답이 14장 + 검사 통과면 그대로, 실패면 조각 읽기.
  python -X utf8 experiments/speed/drop_extra.py
"""
from __future__ import annotations

import itertools
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import visit_truth_check as vc  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
# 손패 줄 밖의 손패(떼어 둔 패)
OFF = {"142535": ["0s", "5s"], "143104": ["7s"], "181209": ["9s"], "183022": ["3m", "4m", "0m"], "183627": ["4m"]}


def valid(ts: list[str], melds: int) -> bool:
    n = len(ts) + 3 * melds
    return (n == 14 and vc.is_win(ts)) or (n == 13 and bool(vc.waits(ts)))


def from_truth() -> None:
    truth = json.loads((ROOT / "experiments/visit_20261031/truth.json").read_text(encoding="utf-8"))["scenes"]
    print("-- 정답 패로")
    for n, s in truth.items():
        if not s.get("indicators_mixed"):
            continue
        k = n[-6:]
        hand = s["hand"].split()
        off = OFF.get(k, [])
        row = list((Counter(hand) - Counter(off)).elements())
        extra = off + s["indicators"]
        m = len(s["melds"])
        all_t = row + extra
        target = len(hand)
        anyp = {tuple(sorted(c)) for c in itertools.combinations(all_t, target) if valid(list(c), m)}
        only14 = {x for x in anyp}
        offp = set()
        for r in range(len(extra) + 1):
            for c in itertools.combinations(extra, r):
                ts = row + list(c)
                if len(ts) + 3 * m == target + 3 * m and valid(ts, m):
                    offp.add(tuple(sorted(ts)))
        print(k, f"읽은 {len(all_t) + 3 * m}장 → {target + 3 * m}장: 아무 패나 빼면 {len(only14)}개, 낱장만 빼면 {len(offp)}개", "정답 포함" if tuple(sorted(hand)) in offp else "정답 없음")


def choose(row: list[str], melds: int, singles: list[str]) -> tuple[list[str] | None, str]:
    wins = set()
    for r in range(1, len(singles) + 1):
        for c in itertools.combinations(singles, r):
            ts = row + list(c)
            if len(ts) + 3 * melds == 14 and vc.is_win(ts):
                wins.add(tuple(sorted(c)))
    if len(wins) == 1:
        return row + list(next(iter(wins))), "화료형 하나"
    if len(wins) > 1:
        return None, f"화료형 {len(wins)}개"
    if valid(row, melds):
        return row, "낱장 없이 텐파이"
    return None, "맞는 조합 없음"


def from_reads() -> None:
    sys.path.insert(0, str(Path(__file__).parent))
    import seat_grow as sg

    scenes = {s["name"]: s for s in sg.scenes()}
    rows = json.loads((ROOT / "experiments/speed/results/wide_pieces.json").read_text(encoding="utf-8"))
    melds_key = lambda ms: sorted(" ".join(sorted(m.split())) for m in ms)
    print("\n-- 읽은 패로")
    tally = {}
    for r in rows:
        s, sc, pc = r["seat"], scenes[r["name"]], r["pieces"]
        truth = sorted(sc["hand"]), melds_key(sc["melds"])
        singles = [t for t in pc.get("singles") or [] if t]
        ts = s.get("hand", []) + s.get("sep", [])
        n = len(ts) + 3 * len(s.get("melds", []))
        how = ""
        if n == 14 and vc.is_win(ts):
            ans, melds, how = ts, s["melds"], "운영 14"
        elif n == 13 and vc.waits(ts):
            melds = s["melds"]
            ans, how = choose(ts, len(melds), singles)
            how = "운영 + " + how
        elif pc.get("row") and all(pc["row"]):
            melds = pc["melds"]
            ans, how = choose(pc["row"], len(melds), singles)
            how = "조각 + " + how
        else:
            ans, melds, how = None, [], "못 읽음"
        part = "BCD" if r["set"] == "bcd" else "오전" if r["name"] < "20261031_14" else "오후"
        t = tally.setdefault(part, Counter())
        t["n"] += 1
        if ans is None:
            t["none"] += 1
            v = "답 없음"
        else:
            good = sorted(ans) == truth[0] and melds_key(melds) == truth[1]
            t["ok" if good else "wrong"] += 1
            v = "맞음" if good else "틀림 " + " ".join(ans)
        if part != "BCD":
            print(r["name"][-6:], how, "낱장", singles, v)
    print()
    for part, t in tally.items():
        print(part, f"정답 {t['ok']}/{t['n']} 틀린 답 {t['wrong']} 답 없음 {t['none']}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    from_truth()
    from_reads()
