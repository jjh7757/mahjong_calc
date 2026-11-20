"""판 단위 안전장치 — API Opus 답(claudeagent_1119/<tag>)으로 정답 없이 복원한 손패에서 틀린 읽기를 찾아내나(2026-11-19, 계획서 "추가 49", 0달러).

  python -X utf8 safetycheck.py [--tag c1] [--games a,b] [--ans 폴더] [--out 파일]
  (11-19: --games 기본 = rebuild_opus.GAMES 다섯 판 · --ans 기본 SRC/<tag>_as_answer · --out 기본 _work/safetycheck_1119/<tag>.json)

신호(정답 안 씀): S1 = 답의 unsure · S2 = 복원 시작 손패의 정렬 어긋남(rebuild_opus 의 sort_bad) > 0 ·
S3 = 복원 손패 + 그 사람 강(그 차례까지)에서 한 종류 > 4장. 정답은 채점(틀린 읽기 표시)과 S2 바닥값(정답 복원의 sort_bad)에만 쓴다.
rebuild_api.py 가 만든 <tag>_as_answer/ 를 그대로 읽는다(먼저 rebuild_api.py 를 돌릴 것).
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import rebuild_opus as ro  # noqa: E402
import sam2llm as m  # noqa: E402
import sam2track as s1  # noqa: E402
from replay import norm  # noqa: E402

SRC = hc.WORK / "claudeagent_1119"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="c1")
    ap.add_argument("--games", help="쉼표로(기본 = rebuild_opus.GAMES)")
    ap.add_argument("--ans", help="rebuild_api 가 옮겨 놓은 폴더(기본 SRC/<tag>_as_answer)")
    ap.add_argument("--out", help="결과 파일(기본 _work/safetycheck_1119/<tag>.json)")
    a = ap.parse_args()
    games = a.games.split(",") if a.games else ro.GAMES
    ro.OP = Path(a.ans) if a.ans else SRC / f"{a.tag}_as_answer"
    truth = s1.truth_all()
    flagged_games, out = [], {}
    tot = Counter()
    for gid in games:
        rf, _ = ro.rebuild(gid, "full")
        rt, _ = ro.rebuild(gid, "truth")
        g = next(x for x in hc.jload(hc.WORK / "testtruth_1116" / "turns.json")["games"] if x["id"] == gid)
        river = []
        rivers = {}
        for t in g["turns"]:
            river.append(norm(t["tile"]))
            rivers[t["id"]] = list(river)
        rows = []
        for o, t in zip(rf, rt):
            tid = o["id"]
            f = SRC / a.tag / f"{tid}.json"
            r = hc.jload(f) if f.exists() else {}
            wrong = bool(r) and not m.right(m.norm(r), truth[tid]) if r else False   # 정답(특수) · 규칙 차례는 답 파일이 없어 False
            s1f = bool(r.get("unsure"))
            s2f = o["sort_bad"] > 0
            cnt = Counter(norm(x) for x in o["before"] if x) + Counter(rivers[tid][:-1])   # 시작 손패 + 그 전 차례까지의 강
            over = sorted(k for k, v in cnt.items() if v > 4)
            s3f = bool(over)
            same = Counter(o["before"]) == Counter(t["before"]) and o["drawn"] == t["drawn"]
            rows.append({"id": tid, "src": o["src"], "wrong_read": wrong, "same_as_truth": same, "S1": s1f, "S2": o["sort_bad"], "S2_truth": t["sort_bad"], "S3": over})
            tot["turns"] += 1
            tot["S1"] += s1f
            tot["S2"] += s2f
            tot["S2_truth"] += t["sort_bad"] > 0
            tot["S3"] += s3f
            tot["wrong"] += wrong
        hit = [x for x in rows if x["S1"] or x["S2"] > 0 or x["S3"]]
        bad_game = not all(x["same_as_truth"] for x in rows)
        if hit:
            flagged_games.append(gid)
        out[gid] = rows
        print(f"\n== {gid}: 복원 {'다름' if bad_game else '같음'} · 걸린 차례 {len(hit)}")
        for x in rows:
            mark = []
            if x["S1"]:
                mark.append("S1 unsure")
            if x["S2"] > 0:
                mark.append(f"S2 정렬 {x['S2']}(정답 복원 {x['S2_truth']})")
            if x["S3"]:
                mark.append(f"S3 {x['S3']}")
            if mark or x["wrong_read"] or not x["same_as_truth"]:
                print(f"  {x['id']:9s} {x['src']:9s} 읽기 {'✗' if x['wrong_read'] else '✓'} · 복원 {'같음' if x['same_as_truth'] else '다름'} | {' · '.join(mark) or '—'}")
    print(f"\n걸린 판: {flagged_games} · 신호별 걸린 차례 S1 {tot['S1']} · S2 {tot['S2']} · S3 {tot['S3']} / {tot['turns']} · 틀린 읽기 {tot['wrong']}")
    print(f"S2 바닥(정답 복원에서 정렬 어긋남 > 0 인 차례): {tot['S2_truth']} / {tot['turns']}")
    hc.jsave(Path(a.out) if a.out else hc.WORK / "safetycheck_1119" / f"{a.tag}.json", out)


if __name__ == "__main__":
    main()
