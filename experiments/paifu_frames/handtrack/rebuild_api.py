"""API Opus 답(claudeagent_1119/<tag>/<id>.json)으로 다섯 판을 정답 없이 복원 — rebuild_opus.py --full 과 같은 셈, 답 폴더만 바꿈(2026-11-19, 계획서 "추가 47").

  python -X utf8 rebuild_api.py [--tag c1] [--games r15_134151,L16_135321] [--dst 폴더]
  (11-19: --games 기본 = rebuild_opus.GAMES 다섯 판 그대로 · --dst 기본 = _work/claudeagent_1119/<tag>_as_answer.
   정답 kind 가 call · unseen 인 차례(L16 2순 · r15 3순)는 API 로 안 읽음 → rebuild_opus 가 정답으로 채우고 출처 "정답(특수)" 로 셈)

API 답이 없는 차례(r19 4순 — color 그림이 없어 API 로 안 돌림)는 하위 에이전트 답(opusread_1118)을 쓰고 따로 센다.
API 답을 rebuild_opus 가 읽는 꼴(<폴더>/<id>/answer.json)로 _work/claudeagent_1119/<tag>_as_answer/ 에 옮겨 놓고 rebuild_opus.OP 를 그 폴더로 바꿔 부른다.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import rebuild_opus as ro  # noqa: E402

SRC = hc.WORK / "claudeagent_1119"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="c1")
    ap.add_argument("--games", help="쉼표로(기본 = rebuild_opus.GAMES)")
    ap.add_argument("--dst", help="옮겨 놓을 폴더(기본 SRC/<tag>_as_answer)")
    a = ap.parse_args()
    games = a.games.split(",") if a.games else ro.GAMES
    dst = Path(a.dst) if a.dst else SRC / f"{a.tag}_as_answer"
    dst.mkdir(parents=True, exist_ok=True)
    fill = []
    for gid in games:
        g = next(x for x in hc.jload(hc.WORK / "testtruth_1116" / "turns.json")["games"] if x["id"] == gid)
        for t in g["turns"]:
            tid = t["id"]
            f = SRC / a.tag / f"{tid}.json"
            (dst / tid).mkdir(exist_ok=True)
            if f.exists():
                r = hc.jload(f)
                ans = r.get("answer") or {}
                hc.jsave(dst / tid / "answer.json", {"id": tid, "kind": ans.get("kind"), "end_order": ans.get("end_order") or [], "src": "api"})
            elif (ro.OP / tid / "answer.json").exists():
                shutil.copyfile(ro.OP / tid / "answer.json", dst / tid / "answer.json")
                fill.append(tid)
    ro.OP = dst
    tot = Counter()
    games_ok = 0
    for gid in games:
        rf, _ = ro.rebuild(gid, "full")
        rt, _ = ro.rebuild(gid, "truth")
        ok_all = True
        for o, t in zip(rf, rt):
            s = Counter(o["before"]) == Counter(t["before"])
            d = o["drawn"] == t["drawn"]
            tot["turns"] += 1
            tot["set"] += s
            tot["drawn"] += d
            tot["row"] += o["before"] == t["before"]
            tot[o["src"]] += 1
            ok_all &= s and d
            if not (s and d):
                print(f"  {gid} {o['id']} 다름: 읽기 {o['src']} · 뽑은 패 {o['drawn']}/{t['drawn']}")
        games_ok += ok_all
        print(f"{gid}: {'판 전체 같음' if ok_all else '다른 차례 있음'}")
    print(f"하위 에이전트 답으로 채운 차례: {fill}")
    print(f"합: 차례 {tot['turns']} · 손패 묶음 같음 {tot['set']} · 뽑은 패 같음 {tot['drawn']} · 줄까지 같음 {tot['row']} · 판 전체 같음 {games_ok}/{len(games)}")
    print("읽기 출처:", {k: v for k, v in tot.items() if k not in ('turns', 'set', 'drawn', 'row')})


if __name__ == "__main__":
    main()
