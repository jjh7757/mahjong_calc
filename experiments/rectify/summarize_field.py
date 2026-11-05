"""[테스트 세트] 10/24 삼각대 15장(장면 5개) 앱 흐름 결과 채점: 화료자·손패(울기 포함)·방총자·점수, 시간, 자동 반영.
정답은 NOTES "촬영별"(사진 확인·label.json). F1400·F1434 는 역이 사진만으로 안 정해져(리치 여부 모름) 점수는 채점 안 함.

  python -I -X utf8 experiments/rectify/summarize_field.py <로그>

보강(2026-11-05, 개선 계획 2단계):
- 패 단위 = 손패(화료패 포함)+울기 패 다중집합 교집합 / 정답 장수 합(/211, `server_bench/field_bench.py` `tiles_hit` 의 14장 채점과 같은 정의).
  판독 오류 행은 0장.
- 장면 단위 /5 = 장면(F1229·F1240·F대삼원·F1400·F1434)마다 사진의 과반이 손패 맞음이면 1. 15장은 독립 장면이 5개뿐이라
  (대삼원 8장·F1400 4장은 같은 판) 사진 단위 /15 만 보면 한 장면이 숫자를 끌고 간다(1단계 검토 ①).
- "경고 없는 틀린 자동" = 자동 반영인데 손패·방총자·점수 중 틀린 것이 있고 auto_cautions 가 빈 것(flow_visit.py 와 같은 이름).
행별 기록은 [records](experiments/speed/stats.py 부트스트랩이 쓴다, 묶음 = 장면).
"""
import json
import re
import statistics
import sys
from collections import Counter

TRUTH = {
    # 장면: (화료자 면, 방총자 자리, 손패(화료패 포함), 울기, 점수)
    "F1229": ("right", 2, "4m 0m 7m 8m 9m 1s 2s 3s 4p 4p 5z 5z 5z 3m", [], "12000"),
    "F1240": ("top", 0, "1s 3s 2s 3s 4s 5p 5p 7z 7z 7z 5z 5z 5z 2s", [], "6700"),
    "F대삼원": ("top", 3, "3s 4s 5p 5p 7z 7z 7z 5z 5z 5z 2s", ["[6z 6z 6z]"], "48000"),
    "F1400": ("left", 1, "3p 3p 4m 0m 6m 4s 4s 4s 6s 7s 8s 9s 9s 3p", [], None),
    "F1434": ("left", 1, "3p 3p 5p 5p 4m 5m 6m 6s 7s 8s 3p", ["(4s 4s 4s 4s)"], None),
}


def meld_tiles(ms) -> list:
    return [t for m in ms for t in re.sub(r"[\[\]()]", " ", m).split()]


def read_rows(path: str) -> list:
    rows = []
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re.search(r"TIMING (\{.*\})", line)
        if m:
            rows.append(json.loads(m.group(1)))
    return rows


def judge(r: dict) -> dict:
    side, loser, hand, melds, pts = TRUTH[r["scene"]]
    mg = r.get("merge") or {}
    ok_side = r.get("winner") == side
    ok_hand = ok_side and Counter(mg.get("closed", [])) == Counter(hand.split()) and sorted(mg.get("melds", [])) == sorted(melds)
    ok_loser = mg.get("loser") == loser
    ok_pts = None if pts is None else r.get("points") == pts
    auto = r.get("auto_block") is None and "error" not in r
    wrong_auto = auto and not (ok_hand and ok_loser and ok_pts is not False)
    want = Counter(hand.split() + meld_tiles(melds))
    have = Counter((mg.get("closed") or []) + meld_tiles(mg.get("melds") or []))
    return dict(ok_side=ok_side, ok_hand=ok_hand, ok_loser=ok_loser, ok_pts=ok_pts, auto=auto, wrong_auto=wrong_auto,
                bad_auto=wrong_auto and not (r.get("auto_cautions") or []), hit=sum((have & want).values()), want=sum(want.values()))


def records(path: str) -> list:
    """행별 채점: key=(사진, 회차), cluster=장면, ok=손패(울기 포함) 맞음, hit·want=패 단위, bad_auto=경고 없는 틀린 자동."""
    out = []
    for r in read_rows(path):
        j = judge(r)
        out.append(dict(key=(r["photo"], r.get("run", 1)), cluster=r["scene"], ok=j["ok_hand"], complete=j["ok_hand"] and j["ok_loser"] and j["ok_pts"] is not False,
                        hit=j["hit"], want=j["want"], bad_auto=j["bad_auto"], sec=r["total_ms"] / 1000))
    return out


def scene_unit(recs: list) -> tuple[int, int, dict]:
    """(과반 맞은 장면 수, 장면 수, 장면별 '맞음/사진')."""
    by: dict = {}
    for x in recs:
        by.setdefault(x["cluster"], []).append(x["ok"])
    return sum(sum(v) * 2 > len(v) for v in by.values()), len(by), {k: f"{sum(v)}/{len(v)}" for k, v in by.items()}


def main(path: str) -> None:
    rows = read_rows(path)
    print(f"runs {len(rows)}")
    stats = Counter()
    for r in rows:
        j = judge(r)
        mg = r.get("merge") or {}
        stats.update(side=j["ok_side"], hand=j["ok_hand"], loser=j["ok_loser"], pts=bool(j["ok_pts"]), pts_n=j["ok_pts"] is not None, auto=j["auto"],
                     wrong_auto=j["wrong_auto"], bad_auto=j["bad_auto"])
        stats["hit"] += j["hit"]
        stats["want"] += j["want"]
        ok_pts = j["ok_pts"]
        print(f"  {r['scene']} {r['photo']}: {r['total_ms'] / 1000:5.1f}s 화료자 {r.get('winner')}{'✓' if j['ok_side'] else '✗'} "
              f"손패 {'✓' if j['ok_hand'] else '✗'} 방총 {mg.get('loser')}{'✓' if j['ok_loser'] else '✗'} 점수 {r.get('points')}"
              f"{'' if ok_pts is None else ('✓' if ok_pts else '✗')} 패 {j['hit']}/{j['want']} | 자동 {'예' if j['auto'] else r.get('auto_block') or r.get('error', '')[:80]}"
              f"{' (경고 없는 틀린 자동)' if j['bad_auto'] else ''}")
        if not j["ok_hand"] and mg:
            print(f"      읽음 {' '.join(mg.get('closed', []))} {mg.get('melds')} flags={r.get('flags')}")
    tot = sorted(r["total_ms"] / 1000 for r in rows if "error" not in r)
    if tot:
        print(f"시간: 중앙 {statistics.median(tot):.2f} / p90 {tot[min(len(tot) - 1, int(.9 * len(tot)))]:.2f} / 최대 {tot[-1]:.2f}s")
        for k in ("shrink", "analyze", "crop", "rectify", "read"):
            xs = [r["stages_ms"][k] for r in rows if k in (r.get("stages_ms") or {})]
            if xs:
                print(f"  {k}: 중앙 {statistics.median(xs) / 1000:.2f}s 최대 {max(xs) / 1000:.2f}s")
    n = len(rows)
    sc, sn, per = scene_unit(records(path))
    print(f"화료자 {stats['side']}/{n}, 손패(울기 포함) {stats['hand']}/{n}, 방총자 {stats['loser']}/{n}, "
          f"점수 {stats['pts']}/{stats['pts_n']}, 자동 반영 {stats['auto']}(틀린 반영 {stats['wrong_auto']}, 경고 없는 틀린 {stats['bad_auto']})")
    print(f"장면 단위(과반 맞음) {sc}/{sn} {per} | 패 단위 {stats['hit']}/{stats['want']}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1])
