"""S6 "5 패 빨강" 이 회귀 변형에서 적5 를 놓치는지(miss)·보통 5 를 적5 로 보는지(2026-11-06, 개선 계획 7-1 의 1(나), 5단계 검토 ②).

모델 재실행 없음: 5단계 회귀 결과 robust_{fold,prod}_1105sig.json 에 저장된 signals.red(분류가 5x·0x 인 크롭의 붉은 잉크 비율)를 다시 센다.
크롭 정답: 그 행에서 색마다 읽은 0x·5x 장수가 정답과 같으면(분류기가 적5/보통 5 를 맞힘) 분류 = 정답으로 본다. 다르면 "혼동 행" 으로 따로 센다.
문턱 = 5단계 select_thresholds 가 고른 값(results/thresholds_sel1105.json, 만 0.659·통 0.507·삭 0.469). 이 결과로 문턱을 고치지 않는다(기록만).

  python -I -X utf8 experiments/speed/red_variants.py [JSON ...]
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
sys.path.insert(0, str(HERE))
import robust_suite as rs  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    files = sys.argv[1:] or [str(RES / "robust_fold_1105sig.json"), str(RES / "robust_prod_1105sig.json")]
    th = json.loads((RES / "thresholds_sel1105.json").read_text(encoding="utf-8"))["red"]["thresholds"]
    print("문턱", th)
    for path in files:
        res = json.loads(Path(path).read_text(encoding="utf-8"))
        print(f"\n### {Path(path).name} — 모델 {res['_meta']['models']}\n")
        print("| 변형 | 적5 크롭 | 적5 miss(< 문턱) | 적5 비율 중앙 | 보통5 크롭 | 보통5 헛(≥ 문턱) | 보통5 비율 중앙 | 비율 없음 | 적5·5 혼동 행 |")
        print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        tot = Counter()
        for v in rs.FIXED:
            rows = res.get(v) or {}
            c, vals = Counter(), defaultdict(list)
            for r in rows.values():
                red = (r.get("signals") or {}).get("red") or []
                if not red or "want_hand" not in r:
                    continue
                have = Counter(r["hand"] + rs.meld_tiles(r["melds"]))
                want = Counter(r["want_hand"] + rs.meld_tiles(r["want_melds"]))
                for x in red:
                    t, q = x["tile"], x.get("ratio")
                    s = t[1]
                    if s not in th:
                        continue
                    if have[f"0{s}"] != want[f"0{s}"] or have[f"5{s}"] != want[f"5{s}"]:
                        c["confused"] += r["w"]
                        continue
                    if q is None:
                        c["none"] += r["w"]
                        continue
                    kind = "red" if t[0] == "0" else "plain"
                    c[kind] += r["w"]
                    vals[kind] += [q] * r["w"]
                    if kind == "red" and q < th[s]:
                        c["miss"] += r["w"]
                    if kind == "plain" and q >= th[s]:
                        c["false"] += r["w"]
            med = lambda xs: f"{statistics.median(xs):.2f}" if xs else "–"
            print(f"| `{v}` | {c['red']} | {c['miss']} | {med(vals['red'])} | {c['plain']} | {c['false']} | {med(vals['plain'])} | {c['none']} | {c['confused']} |")
            tot += c
        print(f"| **합계** | {tot['red']} | {tot['miss']} | | {tot['plain']} | {tot['false']} | | {tot['none']} | {tot['confused']} |")


if __name__ == "__main__":
    main()
