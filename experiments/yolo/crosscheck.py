"""Gemini 1회 + YOLO26 교차 확인이 Gemini 3회 동시 읽기(만장일치)를 대신할 수 있나 — 저장된 판독으로 시뮬레이션(2026-10-26).

Gemini: experiments/speed/results 의 자리 판독 기록(사진 10장 × 6회). 기본은 지금 서버와 같은 설정
        seat_zr_set2_v3a(확대 토막 + 다른 세트 참고표 + v3a 프롬프트, 55/60). --gemini 로 다른 파일도.
YOLO26: HaseLab 전경 파이프라인 검출(results/dets_hybrid.json) → hybrid.split(손패 줄 + 울기 모양만).

방식(모두 마지막에 장수·텐파이/화료형 검사, 실패면 사람 확인):
  base3   지금 서버: 3번 동시에 읽어 셋이 같고 검사 통과면 반영, 아니면 확인.
  one     Gemini 1번 + 검사만.
  x-*     Gemini 1번 + YOLO26 비교. 일치면 반영, 아니면 Gemini 2번 더 불러 base3 처럼(셋 만장일치) 판정.
    x-exact   YOLO 손패·울기 다중집합 == Gemini
    x-subN    YOLO 가 본 패가 전부 Gemini 답 안에 있고(모순 없음), YOLO 가 Gemini 장수의 N% 이상을 봤을 때
  two     Gemini 2번 동시. 둘이 같고 검사 통과면 반영, 아니면 1번 더 불러 셋 만장일치(YOLO 없음, 비교용).
  x2-sub0 Gemini 2번 동시 + YOLO. 둘이 같고 검사 통과하고 YOLO 와 모순이 없으면 반영, 아니면 1번 더 불러 셋 만장일치.
비교는 적5 를 5 와 같게 본다(YOLO 의 적5 구분은 학습 세트 차이로 약함). 정답 판정은 Gemini 기록의 hand_ok·melds_ok.

열거: 사진마다 첫 판독 6가지 × 추가 두 판독(나머지 5개 중 순서 없는 쌍 10가지), base3 은 3개 조합 20가지. 사진은 같은 가중치.
시간: Gemini 각 판독의 실측 지연 s. 동시 호출은 max, 추가 호출은 첫 답 뒤에 보냄(첫 답 + 둘의 max). YOLO 는 Gemini 와 동시에
      돌린다고 보고 --yolo-sec(기본 2초, 서버 CPU 추정. 노트북 0.6초)와의 max.
주의: 기록의 6회는 따로 보낸 호출이라 서로 독립에 가깝다. 실제 서버의 "같은 순간 3번"은 같은 쪽으로 틀린 적이 있다(problem_log 16).

python -I crosscheck.py [--gemini seat_zr_set2_v3a] [--yolo-sec 2]
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hybrid as hy  # noqa: E402

HERE = Path(__file__).resolve().parent
SPEED = HERE.parent / "speed" / "results"


def loose(tiles) -> Counter:
    return Counter(hy.norm(t) for t in tiles)


def gem_tiles(r) -> tuple[list[str], list[list[str]]]:
    hand = r["hand"].split() if r.get("hand") else []
    melds = [m.split() for m in (r.get("melds") or [])]
    return hand, melds


def key(r) -> tuple:
    h, m = gem_tiles(r)
    return tuple(sorted(h)), tuple(sorted(tuple(sorted(x)) for x in m))


def passes(r) -> bool:
    if r.get("error") or not r.get("face_up"):
        return False
    h, m = gem_tiles(r)
    return hy.check(h, m)[0]


def right(r) -> bool:
    return bool(r.get("hand_ok") and r.get("melds_ok"))


def unanimous(rs) -> tuple[bool, bool]:
    """(반영, 맞음)"""
    if all(passes(r) for r in rs) and len({key(r) for r in rs}) == 1:
        return True, right(rs[0])
    return False, False


def agree(rule: str, r, ytiles: Counter) -> bool:
    if not passes(r):
        return False
    h, m = gem_tiles(r)
    g = loose(h + [t for x in m for t in x])
    if rule == "x-exact":
        return ytiles == g
    n = int(rule.removeprefix("x-sub")) / 100
    return not (ytiles - g) and sum(ytiles.values()) >= n * sum(g.values())


def wq(pairs, q: float) -> float:
    """무게 있는 분위수."""
    pairs = sorted(pairs)
    total = sum(w for _, w in pairs)
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= q * total:
            return v
    return pairs[-1][0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gemini", default="seat_zr_set2_v3a")
    ap.add_argument("--yolo-sec", type=float, default=2.0)
    a = ap.parse_args()

    rows = []
    for name in a.gemini.split(","):
        rows += json.loads((SPEED / f"{name}.json").read_text(encoding="utf-8"))
    by_photo: dict[str, list] = {}
    for r in rows:
        if r["scene"] in hy.ry.EVAL_SCENES:
            by_photo.setdefault(f"{r['scene']}/{r['photo'].split('_')[0]}", []).append(r)

    dets = json.loads((HERE / "results" / "dets_hybrid.json").read_text(encoding="utf-8"))["haselab"]
    yolo = {}
    for sp in by_photo:
        h, m, _ = hy.split(dets[f"table/{sp}"])
        yolo[sp] = loose(h + [t for x in m for t in x])

    methods = ["base3", "one", "x-exact", "x-sub70", "x-sub0", "two", "x2-sub0"]
    out_lines = [f"# Gemini 1회 + YOLO26 교차 확인 시뮬레이션 (Gemini 기록: {a.gemini}, YOLO 시간 {a.yolo_sec}초)", ""]
    for scenes, label in ((hy.ry.EVAL_SCENES, "B·C·D 6장"),):
        out_lines += [f"## {label}", "",
                      "| 방식 | 자동 반영 | 틀린 채 반영 | 사람 확인 | Gemini 호출(평균) | 입력 토큰(평균) | 시간 중앙 / p90 |",
                      "| --- | --- | --- | --- | --- | --- | --- |"]
        for meth in methods:
            stats = []  # 사진마다 (반영, 맞음, 호출 수, 토큰, 시간) 평균
            times_all = []
            for sp, rs in by_photo.items():
                if sp[0] not in scenes:
                    continue
                trials = []
                if meth == "base3":
                    for tri in itertools.combinations(rs, 3):
                        auto, ok = unanimous(tri)
                        trials.append((auto, ok, 3, sum(r["in"] for r in tri), max(r["s"] for r in tri), 1))
                elif meth == "one":
                    for r in rs:
                        trials.append((passes(r), passes(r) and right(r), 1, r["in"], r["s"], 1))
                elif meth in ("two", "x2-sub0"):
                    for i, j in itertools.permutations(range(len(rs)), 2):
                        if i > j:
                            continue
                        r, q = rs[i], rs[j]
                        same = passes(r) and passes(q) and key(r) == key(q)
                        if same and (meth == "two" or agree("x-sub0", r, yolo[sp])):
                            # 가중치: 갈라진 쌍은 세 번째 후보 수만큼 시행이 생기므로, 반영된 쌍도 같은 무게로
                            trials.append((True, right(r), 2, r["in"] + q["in"], max(r["s"], q["s"], a.yolo_sec), len(rs) - 2))
                            continue
                        for k3, t in enumerate(rs):
                            if k3 in (i, j):
                                continue
                            auto, ok = unanimous((r, q, t))
                            trials.append((auto, ok, 3, r["in"] + q["in"] + t["in"], max(r["s"], q["s"], a.yolo_sec) + t["s"], 1))
                else:
                    for i, r in enumerate(rs):
                        others = rs[:i] + rs[i + 1:]
                        if agree(meth, r, yolo[sp]):
                            trials.append((True, right(r), 1, r["in"], max(r["s"], a.yolo_sec), len(others) * (len(others) - 1) // 2))
                            continue
                        for p, q in itertools.combinations(others, 2):
                            auto, ok = unanimous((r, p, q))
                            trials.append((auto, ok, 3, r["in"] + p["in"] + q["in"],
                                           max(r["s"], a.yolo_sec) + max(p["s"], q["s"]), 1))
                W = sum(t[5] for t in trials)
                stats.append(tuple(sum(t[k] * t[5] for t in trials) / W for k in range(4)))
                times_all += [(t[4], t[5] / W) for t in trials]  # 사진마다 무게 합 1
            k = len(stats)
            auto = sum(s[0] for s in stats) / k
            good = sum(s[1] for s in stats) / k
            calls = sum(s[2] for s in stats) / k
            tok = sum(s[3] for s in stats) / k
            out_lines.append(f"| {meth} | {100*auto:.0f}% | {100*(auto-good):.1f}% | {100*(1-auto):.0f}% | {calls:.2f} | {tok/1000:.1f}k |"
                             f" {wq(times_all, 0.5):.1f} / {wq(times_all, 0.9):.1f}초 |")
        out_lines.append("")

    out_lines.append("## 사진별 YOLO26 손패(후처리 뒤)와 Gemini 6회와의 일치")
    for sp, rs in by_photo.items():
        ag = {rule: sum(agree(rule, r, yolo[sp]) for r in rs) for rule in ("x-exact", "x-sub70", "x-sub0")}
        out_lines.append(f"- {sp}: YOLO {sum(yolo[sp].values())}장 [{' '.join(sorted(yolo[sp].elements()))}] | Gemini 정답 {sum(map(right, rs))}/6"
                         f" | 일치 exact {ag['x-exact']}/6, sub70 {ag['x-sub70']}/6, sub0 {ag['x-sub0']}/6")
    text = "\n".join(out_lines) + "\n"
    (HERE / "results" / f"crosscheck_{a.gemini.replace(',', '+')}.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
