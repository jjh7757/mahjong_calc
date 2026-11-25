"""앱 버림 기록이 그때 앱 격자 그대로였다면 어땠나 — 11-14 2반장 아홉 판(2026-11-25, metrics 표 12-128).

  python -X utf8 experiments/paifu_frames/apptrust_check.py          (저장소 루트에서, LLM 0 — 쓰는 곳은 results/apptrust_check/ 뿐)

11-24 의 2반장 "앱 기록"(results/auto_h2_1114/app/<판>/paifu_app.json)은 추적 프레임 zip 을 앱 기록기로 재생한 것이다.
겹쳐 보기 출력(overlay_dump.json)은 그때 앱 격자선(B: x 346 ~ 852 · y 206 ~ 711)으로 만든 것이지만, 재생의 --sticks 는 사람이 바로잡은
리치봉 구역(424,425,618,622 · r11 · r12 는 425,426,619,621)이었다. 그날 태블릿에 실제로 들어 있던 리치봉 구역은 355,495,562,703
(frames.json grid.sticks — 실제 가운데 기기보다 오른쪽 위)이다. 여기서는 --sticks 만 그때 값으로 바꿔 다시 재생하고 사건을 견준다.
  견줌 ①: 그때 값 재생 ↔ 바로잡은 값 재생(자리별 버림 줄 · 울기 수 · 리치 자리)
  견줌 ②: 두 재생의 선(dealer) · 사건 수
주의: 11-14 에는 앱의 판 중 버림 기록이 꺼져 있었다 — 이것은 "켜져 있었다면" 의 재생이지 실제 기록이 아니다.
"""
import difflib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import app_record as ar  # noqa: E402

SRC = HERE / "results" / "auto_h2_1114"
OUT = HERE / "results" / "apptrust_check"
LIVE_STICKS = "355,495,562,703"


def seat_rows(events):
    d = {}
    for e in events:
        if e.get("type") == "discard":
            d.setdefault(e["seat"], []).append(e["tile"] + ("r" if e.get("riichi") else ""))
    return d


def main():
    w = sys.stdout.buffer.write
    exe = SRC / "_bin" / "replay_recorder.exe"
    rounds = ar.jl(SRC / "app_rounds.json")["rounds"]
    rows, tot = [], {"cells": 0, "same": 0, "games_same": 0}
    for r in rounds:
        src = r["discard_source"]
        fixed = ar.jl(SRC / "app" / r["id"] / "paifu_app.json")
        live = ar.replay_track(exe, ROOT / src["dump"], src["dealer_side"], src["bottom_seat"], LIVE_STICKS, OUT / r["id"])
        A, B = seat_rows(fixed.get("events") or []), seat_rows(live.get("events") or [])
        cells = sum(len(v) for v in A.values())
        same = 0
        for s in set(A) | set(B):
            sm = difflib.SequenceMatcher(None, A.get(s, []), B.get(s, []), autojunk=False)
            same += sum(b.size for b in sm.get_matching_blocks())
        ca = sum(1 for e in fixed["events"] if e.get("type") == "call")
        cb = sum(1 for e in live["events"] if e.get("type") == "call")
        ok = A == B and ca == cb
        row = {"id": r["id"], "round": r["round_label"], "sticks_fixed": src["sticks"], "cells_fixed": cells, "cells_live": sum(len(v) for v in B.values()),
               "same": same, "calls_fixed": ca, "calls_live": cb, "dealer_fixed": fixed.get("dealer"), "dealer_live": live.get("dealer"), "all_same": ok}
        rows.append(row)
        tot["cells"] += cells
        tot["same"] += same
        tot["games_same"] += ok
        w((f"{row['id']} {row['round']:10s} 바로잡은 값 {cells:3d}칸 · 그때 값 {row['cells_live']:3d}칸 · 같은 칸 {same:3d} · 울기 {ca}/{cb} · "
           f"선 {row['dealer_fixed']}/{row['dealer_live']} · {'같음' if ok else '다름'}\n").encode())
    w(f"합: 같은 칸 {tot['same']}/{tot['cells']} · 통째로 같은 판 {tot['games_same']}/{len(rows)}\n".encode())
    ar.wj(OUT / "summary.json", {"_note": __doc__.splitlines()[0], "live_sticks": LIVE_STICKS, "rows": rows, "total": tot})


if __name__ == "__main__":
    main()
