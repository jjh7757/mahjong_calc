"""visit_20261031/truth.json 검사와, 저장된 판독을 그 정답으로 다시 채점(2026-11-01). API 호출 없음.

검사: 장수(비공개 + 울기×3 = 13·14), 13장이면 텐파이이고 win_tile 이 대기에 있음, 14장이면 화료형, win_tile 을 뺀 13장도 그 패를 기다림,
      같은 패 4장 이하(표시패 포함), 적5 는 종류마다 1장 이하.
채점: 앱이 낸 값 meta.json merge(손패·울기·표시패), Gemini /v2/seat 폭 40(seat_grow.json), YOLO26 rot90 새 묶기(assemble.json).
  python -I experiments/speed/visit_truth_check.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VISIT = ROOT / "experiments/visit_20261031"
TILES = [f"{n}{s}" for s in "mps" for n in range(1, 10)] + [f"{n}z" for n in range(1, 8)]


def norm(t: str) -> str:
    return "5" + t[1] if t[0] == "0" else t


def melds_only(c: Counter, need_pair: bool) -> bool:
    keys = sorted((t for t in c if c[t] > 0), key=TILES.index)
    if not keys:
        return not need_pair
    t = keys[0]
    if need_pair and c[t] >= 2:
        c[t] -= 2
        ok = melds_only(c, False)
        c[t] += 2
        if ok:
            return True
    if c[t] >= 3:
        c[t] -= 3
        ok = melds_only(c, need_pair)
        c[t] += 3
        if ok:
            return True
    if t[1] != "z" and int(t[0]) <= 7:
        a, b = f"{int(t[0]) + 1}{t[1]}", f"{int(t[0]) + 2}{t[1]}"
        if c[a] and c[b]:
            for x in (t, a, b):
                c[x] -= 1
            ok = melds_only(c, need_pair)
            for x in (t, a, b):
                c[x] += 1
            return ok
    return False


def is_win(ts: list[str]) -> bool:
    c = Counter(norm(t) for t in ts)
    if len(ts) == 14 and len(c) == 7 and all(v == 2 for v in c.values()):
        return True
    return len(ts) % 3 == 2 and melds_only(c, True)


def waits(ts: list[str]) -> list[str]:
    n = Counter(norm(t) for t in ts)
    return [t for t in TILES if n[t] < 4 and is_win(ts + [t])]


def check(name: str, s: dict) -> list[str]:
    hand, melds = s["hand"].split(), [m.split() for m in s["melds"]]
    bad, total = [], len(hand) + 3 * len(melds)
    if total not in (13, 14):
        bad.append(f"장수 {total}")
    win = s.get("win_tile")
    if total == 14 and not is_win(hand):
        bad.append("14장인데 화료형 아님")
    if total == 14 and win:
        rest = list(hand)
        rest.remove(win)
        if norm(win) not in waits(rest):
            bad.append(f"{win} 를 빼면 그 패를 안 기다림")
    if total == 13:
        w = waits(hand)
        if not w:
            bad.append("텐파이 아님")
        if win and norm(win) not in w:
            bad.append(f"{win} 가 대기 {w} 에 없음")
    all_t = hand + [t for m in melds for t in m] + s.get("indicators", []) + ([win] if win and total == 13 else [])
    over = {t: v for t, v in Counter(norm(t) for t in all_t).items() if v > 4}
    if over:
        bad.append(f"5장 이상 {over}")
    red = {t: v for t, v in Counter(t for t in all_t if t[0] == "0").items() if v > 1}
    if red:
        bad.append(f"적5 중복 {red}")
    return bad


def same(hand: list[str], melds: list[str], s: dict) -> bool:
    key = lambda ms: sorted(" ".join(sorted(m.split())) for m in ms)
    return sorted(hand) == sorted(s["hand"].split()) and key(melds) == key(s["melds"])


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    truth = json.loads((VISIT / "truth.json").read_text(encoding="utf-8"))["scenes"]
    fails = 0
    for n, s in truth.items():
        bad = check(n, s)
        fails += bool(bad)
        hand = s["hand"].split()
        w = waits(hand) if len(hand) + 3 * len(s["melds"]) == 13 else None
        print(n[-6:], "검사", "통과" if not bad else f"실패 {bad}", "" if w is None else f"대기 {w}")
    print(f"모양 검사 실패 {fails}/{len(truth)}\n")

    gem = {r["name"]: r["by_grow"].get("40") or {} for r in json.loads((ROOT / "experiments/speed/results/seat_grow.json").read_text(encoding="utf-8")) if r["set"] == "visit"}
    yolo = {r["name"]: r for r in json.loads((ROOT / "experiments/yolo/results/visit1031/assemble.json").read_text(encoding="utf-8")) if r["rule"] == "새"}
    tally = Counter()
    for n, s in truth.items():
        m = json.loads((VISIT / "captures" / n / "meta.json").read_text(encoding="utf-8"))["merge"]
        closed = list(m.get("closed") or [])
        app_ok = same(closed, [x.strip("[]") for x in m.get("melds") or []], s)
        if not app_ok and m.get("win_tile") and closed:  # 사진에 없는 론 패를 앱이 손패에 합친 경우
            rest = list(closed)
            rest.remove(m["win_tile"])
            app_ok = same(rest, [x.strip("[]") for x in m.get("melds") or []], s)
        dora_ok = Counter(m.get("dora_indicators") or []) == Counter(s["indicators"])
        g = gem.get(n, {})
        gem_ok = same((g.get("hand") or "").split() + ([g["sep"]] if g.get("sep") else []), g.get("melds") or [], s)
        y = yolo.get(n, {})
        yolo_ok = same(y.get("hand") or [], [" ".join(x) for x in y.get("melds") or []], s)
        part = "오전" if n < "20261031_14" else "오후"
        for k, v in (("앱 손패", app_ok), ("앱 표시패", dora_ok), ("Gemini40", gem_ok), ("YOLO26", yolo_ok)):
            tally[part, k] += v
        tally[part, "n"] += 1
        print(n[-6:], f"앱 {app_ok} 표시패 {dora_ok}({m.get('dora_indicators')}) Gemini40 {gem_ok} YOLO {yolo_ok}", "" if gem_ok else f"| Gemini {g.get('hand')} sep {g.get('sep')} {g.get('melds')}")
    print()
    for part in ("오전", "오후"):
        print(part, f"{tally[part, 'n']}장:", {k: tally[part, k] for k in ("앱 손패", "앱 표시패", "Gemini40", "YOLO26")})


if __name__ == "__main__":
    main()
