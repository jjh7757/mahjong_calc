"""쌓인 결과로 지연 분포와 '늦으면 같은 요청을 하나 더(헤지)' 시뮬레이션.

  python -I experiments/speed/latency.py

헤지: t 초 안에 답이 없으면 같은 요청을 하나 더 보내 먼저 온 답을 쓴다. 두 요청의 지연은 서로 독립이라 보고,
같은 조건의 다른 호출 지연을 무작위로 뽑아 두 번째 요청의 지연으로 쓴다(1만 번).
장면 = 자리 1호출 + 작은 호출 5개(scene_base.json 의 강 끝·리치봉·도라 지연에서 뽑음), 모두 동시.
"""
from __future__ import annotations

import json
import random
import statistics
from pathlib import Path

R = Path(__file__).parent / "results"
SCENES = "BCD"  # 화료패가 사진에 없는 A·E 는 평가에서 뺀다(2026-10-25 사용자 결정)


def load(name: str) -> list[float]:
    return [r["s"] for r in json.loads((R / f"{name}.json").read_text(encoding="utf-8"))
            if not r.get("error") and r["scene"] in SCENES]


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))]


def hedged(xs: list[float], t: float | None, rnd: random.Random) -> float:
    a = rnd.choice(xs)
    if t is None or a <= t:  # t=0 은 처음부터 두 개(경주)
        return a
    return min(a, t + rnd.choice(xs))


def main() -> None:
    rnd = random.Random(0)
    small = [c["s"] for r in json.loads((R / "scene_base.json").read_text(encoding="utf-8"))
             for k, c in r["calls"].items() if not k.startswith("seat") and not c.get("error")]
    print(f"작은 호출 {len(small)}개: 중앙 {statistics.median(small):.1f} p90 {pct(small, .9):.1f} 최대 {max(small):.1f}")
    for name in ("seat_base", "seat_zoom3u_ref"):
        xs = load(name)
        print(f"\n{name} {len(xs)}개: 중앙 {statistics.median(xs):.1f} p75 {pct(xs, .75):.1f} p90 {pct(xs, .9):.1f} "
              f"최대 {max(xs):.1f}  10초 넘음 {sum(x > 10 for x in xs)}/{len(xs)}")
        print("  헤지  | 장면 중앙  p90   p99  | 두 번째 요청 비율")
        for t in (None, 12, 10, 8, 6, 0):
            scenes, extra = [], 0
            for _ in range(10000):
                seat = hedged(xs, t, rnd)
                others = [hedged(small, t, rnd) for _ in range(5)]
                scenes.append(max([seat] + others))
            for _ in range(10000):
                extra += (t is not None and rnd.choice(xs) > t) or t == 0
            print(f"  {'없음' if t is None else '경주' if t == 0 else t:>5} | {statistics.median(scenes):6.1f} {pct(scenes, .9):5.1f} {pct(scenes, .99):5.1f} | "
                  f"{extra / 100:.0f}%")


def sane(r: dict) -> bool:
    """정답을 모르고도 코드가 볼 수 있는 검사: 앞면이고, 손패 + 울기(깡도 3장) 가 13장 또는 14장."""
    if r.get("error") or not r.get("face_up"):
        return False
    n = len(r["hand"].split()) + 3 * len(r["melds"])
    return n in (13, 14)


def race_pick(name: str) -> None:
    """경주로 받은 두 답 중 하나 고르기: 먼저 온 답이 검사를 통과하면 그것, 아니면 다른 답(그것도 안 되면 먼저 온 답)."""
    rows = [r for r in json.loads((R / f"{name}.json").read_text(encoding="utf-8")) if r["scene"] in SCENES]
    by_photo: dict[str, list[dict]] = {}
    for r in rows:
        by_photo.setdefault(r["photo"], []).append(r)
    ok = lambda r: bool(r.get("hand_ok") and r.get("melds_ok"))  # noqa: E731
    one = sum(ok(r) for r in rows) / len(rows)
    rnd, n, hit, fell = random.Random(1), 0, 0, 0
    for rs in by_photo.values():
        for _ in range(2000):
            a, b = rnd.sample(rs, 2)
            first, second = (a, b) if a["s"] <= b["s"] else (b, a)
            pick = first if sane(first) or not sane(second) else second
            fell += pick is second
            hit += ok(pick)
            n += 1
    print(f"\n{name}: 한 번 {one:.1%} → 경주 + 검사로 고르기 {hit / n:.1%} (늦게 온 답을 쓴 비율 {fell / n:.1%})")
    print("  검사를 통과하고도 틀린 답:", sum(1 for r in rows if sane(r) and not ok(r)), "/", len(rows),
          " 검사에 걸린 답:", sum(1 for r in rows if not sane(r)))


if __name__ == "__main__":
    main()
    race_pick("seat_base")
    race_pick("seat_zoom3u_ref")
    race_pick("seat_zr_set2")
    race_pick("seat_zoom3u")
    race_pick("seat_zr_set2_v3")
    race_pick("seat_zr_set2_v3a")
    for name in ("seat_zr_set2", "seat_zr_set2_v3", "seat_zr_set2_v3a"):
        xs = load(name)
        print(f"{name}: 중앙 {statistics.median(xs):.1f} p90 {pct(xs, .9):.1f} 최대 {max(xs):.1f}  10초 넘음 {sum(x > 10 for x in xs)}/{len(xs)}")
