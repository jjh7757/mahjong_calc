"""고친 들어간 칸(insert_truth_1116.json)을 판정 B 사본에 넣어 replay2 로 다시 굴려 보기(2026-11-16).

  python -X utf8 fixplace.py make            # results/handtrack/<판>/judge_fix1116/ 에 고친 판정 사본(원본은 안 건드림)
  python -X utf8 fixplace.py make --loose    # firm 아닌 칸(n03 13순)도 한 칸으로 넣은 사본(judge_fix1116_loose/)
그 뒤:  python -X utf8 replay2.py <판> <사본…> --sort-filter --out <폴더>
고치는 법: 그 구간의 place 후보·shuffle 을 지우고, 버리기 전 끝 붙임(place n+1)이 있으면 move (n)→j 를, 없으면 place j 를 넣는다.
이미 move →j 가 있으면 conf 만 high 로.
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402

TRUTH = hc.jload(Path(__file__).resolve().parent / "insert_truth_1116.json")


def fix_events(ev: list, j: int, n_after: int) -> list:
    out, attach, has_move = [], False, False
    for e in ev:
        e = copy.deepcopy(e)
        if e["kind"] == "shuffle":
            continue
        if e["kind"] == "place":
            if e.get("pos") == n_after + 1:  # 버리기 전 끝 붙임
                attach = True
                out.append(e)
            continue  # 한 칸·후보 place 는 아래에서 다시 넣음
        if e["kind"] == "move":
            if e.get("to") != j:
                continue
            e["conf"] = "high"
            has_move = True
        out.append(e)
    if not has_move:
        out.append({"kind": "move", "from": n_after, "to": j, "conf": "high"} if attach else {"kind": "place", "pos": j, "conf": "high"})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["make"])
    ap.add_argument("--loose", action="store_true")
    a = ap.parse_args()
    for gid, segs in TRUTH.items():
        if gid.startswith("_"):
            continue
        od = hc.OUT / gid / ("judge_fix1116_loose" if a.loose else "judge_fix1116")
        for p in sorted((hc.OUT / gid / "judge").glob("v2_B*.json")):
            J = hc.jload(p)
            by_seg = {int(v.get("event_seg", k)): v for k, v in segs.items()}  # r18 2순은 뽑기(구간 6)와 버림·넣기(구간 7)가 갈려 있다
            for jd in J["judgments"]:
                t = by_seg.get(jd["seg"])
                if t is None or not jd["events"] or not (t["firm"] or a.loose):
                    continue
                before = [(e["kind"], e.get("pos", e.get("what", e.get("to")))) for e in jd["events"]]
                jd["events"] = fix_events(jd["events"], t["j"], jd["n_after"])
                after = [(e["kind"], e.get("pos", e.get("what", e.get("to")))) for e in jd["events"]]
                print(gid, "구간", jd["seg"], before, "→", after)
            hc.jsave(od / p.name, J)


if __name__ == "__main__":
    main()
