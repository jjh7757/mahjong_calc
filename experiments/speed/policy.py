"""정확도를 올리되 시간은 늘리지 않는 '여러 번 동시에 읽고 고르기' 정책을 쌓인 결과로 시뮬레이션한다(추가 호출 없음).

  python -I experiments/speed/policy.py [결과 이름 ...]     기본: seat_zr_set2_v3a

검사(정답을 모르고 코드가 할 수 있는 것):
  sane   앞면이고 손패 + 울기(깡도 3장) 13~14장, 같은 패 5장 이상 없음
  tenpai 13장이면 텐파이, 14장이면 화료 형태(4몸통 1머리·치또이·국사)
정책(같은 사진 n 번을 동시에 보냈다고 보고, 실측 지연에서 뽑음):
  first        n=1
  race_check   n=2, 먼저 온 답이 검사 통과면 그것, 아니면 다른 답
  agree2       n=3, 먼저 같은 답이 두 번 나온 순간 그 답(셋 다 다르면 검사 통과한 것 중 먼저 온 것)
  agree2_check n=3, agree2 와 같되 검사 통과한 답끼리만 맞춰 봄
"""
from __future__ import annotations

import json
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

R = Path(__file__).parent / "results"
SCENES = "BCD"  # 화료패가 사진에 없는 A·E 는 평가에서 뺀다(2026-10-25 사용자 결정)
SUITS = "mps"


def norm(t: str) -> str:
    return "5" + t[1] if t[0] == "0" else t


def is_agari(counts: Counter) -> bool:
    tiles = sorted(counts.elements(), key=lambda t: (t[1], t[0]))
    n = len(tiles)
    if n % 3 != 2:
        return False
    if n == 14 and len(counts) == 7 and all(v == 2 for v in counts.values()):
        return True
    terminals = {f"{a}{s}" for s in SUITS for a in "19"} | {f"{i}z" for i in range(1, 8)}
    if n == 14 and set(counts) == terminals:
        return True
    for pair in [t for t, v in counts.items() if v >= 2]:
        c = counts.copy()
        c[pair] -= 2
        if sets_only(+c):
            return True
    return False


def sets_only(c: Counter) -> bool:
    if not c:
        return True
    t = min(c, key=lambda x: (x[1], int(x[0])))
    if c[t] >= 3:
        d = c.copy()
        d[t] -= 3
        if sets_only(+d):
            return True
    n, s = int(t[0]), t[1]
    if s != "z" and n <= 7:
        a, b = f"{n + 1}{s}", f"{n + 2}{s}"
        if c[a] and c[b]:
            d = c.copy()
            for x in (t, a, b):
                d[x] -= 1
            if sets_only(+d):
                return True
    return False


ALL = [f"{n}{s}" for s in SUITS for n in range(1, 10)] + [f"{n}z" for n in range(1, 8)]


def closed_counts(r: dict) -> Counter:
    return Counter(norm(t) for t in r["hand"].split())


def tenpai_or_agari(r: dict) -> bool:
    """울기는 이미 완성된 몸통으로 보고 닫힌 손패만 본다."""
    c = closed_counts(r)
    total = sum(c.values()) + 3 * len(r["melds"])
    if total == 14:
        return is_agari(c)
    if total == 13:
        return any(is_agari(c + Counter([t])) for t in ALL if c[t] < 4)
    return False


def sane(r: dict) -> bool:
    if r.get("error") or not r.get("face_up"):
        return False
    c = closed_counts(r)
    for m in r["melds"]:
        c.update(norm(t) for t in m.split())
    n = len(r["hand"].split()) + 3 * len(r["melds"])
    return n in (13, 14) and max(c.values()) <= 4


CHECKS = {"none": lambda r: True, "sane": sane, "tenpai": lambda r: sane(r) and tenpai_or_agari(r)}


def key(r: dict) -> str:
    return " ".join(sorted(r["hand"].split())) + " | " + " ".join(r["melds"])


def ok(r: dict) -> bool:
    return bool(r.get("hand_ok") and r.get("melds_ok"))


def pick(policy: str, rs: list[dict], check) -> tuple[dict, float]:
    rs = sorted(rs, key=lambda r: r["s"])
    if policy == "first":
        return rs[0], rs[0]["s"]
    if policy == "race_check":
        a, b = rs[0], rs[1]
        if check(a):
            return a, a["s"]
        return (b, b["s"]) if check(b) else (a, b["s"])
    # agree2: 도착 순서대로 보며 같은 답이 두 번 나오면 그 순간 확정
    pool = rs if policy == "agree2" else [r for r in rs if check(r)]
    seen: Counter = Counter()
    for r in pool:
        seen[key(r)] += 1
        if seen[key(r)] == 2:
            return r, r["s"]
    good = [r for r in rs if check(r)]
    r = good[0] if good else rs[0]
    return r, rs[-1]["s"]  # 합의가 없으면 셋 다 기다린 셈


def main() -> None:
    names = sys.argv[1:] or ["seat_zr_set2_v3a"]
    rows = [r for n in names for r in json.loads((R / f"{n}.json").read_text(encoding="utf-8"))
            if not r.get("error") and r["scene"] in SCENES]
    by_photo: dict[str, list[dict]] = {}
    for r in rows:
        by_photo.setdefault(r["photo"], []).append(r)
    print(f"결과 {names}: {len(rows)}회, 사진당 {min(map(len, by_photo.values()))}~{max(map(len, by_photo.values()))}회")
    bad = [r for r in rows if not ok(r)]
    print(f"틀린 답 {len(bad)}개 중 검사에 걸리는 것: sane {sum(not sane(r) for r in bad)}, "
          f"sane+텐파이 {sum(not CHECKS['tenpai'](r) for r in bad)}  (맞는 답이 검사에 걸리는 것 {sum(not CHECKS['tenpai'](r) for r in rows if ok(r))})")
    for r in bad:
        print(f"   {r['photo']}: {r['hand']} | {r['melds']}  sane={sane(r)} 텐파이/화료={sane(r) and tenpai_or_agari(r)}")
    rnd = random.Random(0)
    print("\n정책            검사     정답      장면 시간 중앙 / p90   (사진마다 2000번 뽑기)")
    for policy, n in (("first", 1), ("race_check", 2), ("agree2", 3), ("agree2_check", 3)):
        for cname in (("none",) if policy in ("first", "agree2") else ("sane", "tenpai")):
            hits, times, total = 0, [], 0
            for rs in by_photo.values():
                for _ in range(2000):
                    r, t = pick(policy, rnd.sample(rs, n), CHECKS[cname])
                    hits += ok(r)
                    times.append(t)
                    total += 1
            times.sort()
            print(f"  {policy:13s} {cname:7s} {hits / total:6.1%}   {statistics.median(times):5.1f} / {times[int(.9 * len(times))]:5.1f}초  호출 ×{n}")


def accept_or_ask(by_photo: dict[str, list[dict]], n: int, need: int, rnd: random.Random) -> None:
    """n 개 동시. 검사(sane+텐파이) 통과한 답 중 need 개가 같아지는 순간 자동 반영, 끝까지 안 되면 사용자에게 확인."""
    auto_ok = auto_bad = ask = 0
    times = []
    for rs in by_photo.values():
        for _ in range(2000):
            got = sorted(rnd.sample(rs, n), key=lambda r: r["s"])
            seen: Counter = Counter()
            done = None
            for r in got:
                if CHECKS["tenpai"](r):
                    seen[key(r)] += 1
                    if seen[key(r)] == need:
                        done = r
                        times.append(r["s"])
                        break
            if done is None:
                ask += 1
                times.append(got[-1]["s"])
            elif ok(done):
                auto_ok += 1
            else:
                auto_bad += 1
    total = auto_ok + auto_bad + ask
    times.sort()
    print(f"  {n}개 중 {need}개 일치  자동 반영 {(auto_ok + auto_bad) / total:6.1%} (그중 틀림 {auto_bad / total:.2%})  "
          f"확인 묻기 {ask / total:5.1%}   시간 중앙 {statistics.median(times):.1f} / p90 {times[int(.9 * len(times))]:.1f}초")


if __name__ == "__main__":
    main()
    print("\n일치하면 자동 반영, 아니면 확인 묻기")
    names = sys.argv[1:] or ["seat_zr_set2_v3a"]
    by_photo: dict[str, list[dict]] = {}
    for n in names:
        for r in json.loads((R / f"{n}.json").read_text(encoding="utf-8")):
            if not r.get("error") and r["scene"] in SCENES:
                by_photo.setdefault(r["photo"], []).append(r)
    rnd = random.Random(1)
    for n, need in ((2, 2), (3, 2), (4, 2), (3, 3)):
        accept_or_ask(by_photo, n, need, rnd)
