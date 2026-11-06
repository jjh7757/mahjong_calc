"""앱 흐름 로그 두 묶음(전·후)의 장면별 답이 같은지 + 응답 경로(wall_frame) 수 — 개선 계획 8b-3c(metrics 표 1-108 기준 (a) '답 동일').

  python -I -X utf8 experiments/speed/flow_same.py <전 로그>... -- <후 로그>...

TIMING 줄마다 (장면, 사진, 회차)로 짝짓고 merge 의 손패·화료패·울기·표시패·뒷도라·쯔모/방총자, 화료자, 점수, 자동 반영 막음이 같은지 본다.
경로는 TIMING 의 local_dora.wall_frame(앱 로그에 남는 것)만 센다 — localroles 경로는 서버 로그 'localroles … wall_frame=' 줄로 따로 센다.
"""
from __future__ import annotations

import json
import sys
from collections import Counter

KEYS = ("closed", "win_tile", "melds", "dora_indicators", "ura_indicators", "is_tsumo", "loser", "winner", "riichi")


def rows(paths: list[str]) -> dict:
    out = {}
    for p in paths:
        for line in open(p, encoding="utf-8", errors="replace"):
            if not line.startswith("TIMING "):
                continue
            j = json.loads(line[7:])
            k = (j.get("scene"), j.get("photo"), j.get("run"))
            m = j.get("merge") or {}
            out[k] = {"ans": {x: m.get(x) for x in KEYS} | {"points": j.get("points"), "seat": j.get("winner"),
                                                            "auto_block": j.get("auto_block"), "cautions": j.get("auto_cautions")},
                      "wf": (j.get("local_dora") or {}).get("wall_frame"), "cut": (j.get("local_dora") or {}).get("cut"),
                      "ms": j.get("total_ms")}
    return out


def main() -> None:
    a = sys.argv[1:]
    i = a.index("--")
    before, after = rows(a[:i]), rows(a[i + 1:])
    same = diff = 0
    for k in sorted(set(before) | set(after), key=str):
        b, f = before.get(k), after.get(k)
        if b is None or f is None:
            print("짝 없음", k, "전" if b else "", "후" if f else "")
            diff += 1
            continue
        if b["ans"] == f["ans"]:
            same += 1
        else:
            diff += 1
            print("다름", k, {x: (b["ans"][x], f["ans"][x]) for x in b["ans"] if b["ans"][x] != f["ans"][x]})
    print(f"같음 {same} · 다름 {diff} · 전 {len(before)} 행 · 후 {len(after)} 행")
    print("표시패 경로 전", dict(Counter((r["wf"], r["cut"]) for r in before.values())), "후", dict(Counter((r["wf"], r["cut"]) for r in after.values())))


if __name__ == "__main__":
    main()
