"""[참고·평가 밖] 매장 사진 판독 결과 채점: 화료자·손패(울기 포함)·방총자·점수, 시간, 자동 반영.
정답은 NOTES "촬영별"(사진 확인·label.json). F1400·F1434 는 역이 사진만으로 안 정해져(리치 여부 모름) 점수는 채점 안 함."""
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
rows = []
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    m = re.search(r"TIMING (\{.*\})", line)
    if m:
        rows.append(json.loads(m.group(1)))

print(f"runs {len(rows)}")
stats = Counter()
for r in rows:
    side, loser, hand, melds, pts = TRUTH[r["scene"]]
    mg = r.get("merge") or {}
    ok_side = r.get("winner") == side
    ok_hand = ok_side and Counter(mg.get("closed", [])) == Counter(hand.split()) and sorted(mg.get("melds", [])) == sorted(melds)
    ok_loser = mg.get("loser") == loser
    ok_pts = None if pts is None else r.get("points") == pts
    auto = r.get("auto_block") is None and "error" not in r
    wrong_auto = auto and not (ok_hand and ok_loser and ok_pts is not False)
    stats.update(side=ok_side, hand=ok_hand, loser=ok_loser, pts=bool(ok_pts), pts_n=pts is not None, auto=auto, wrong_auto=wrong_auto)
    st = r.get("stages_ms") or {}
    print(f"  {r['scene']} {r['photo']}: {r['total_ms'] / 1000:5.1f}s 화료자 {r.get('winner')}{'✓' if ok_side else '✗'} "
          f"손패 {'✓' if ok_hand else '✗'} 방총 {mg.get('loser')}{'✓' if ok_loser else '✗'} 점수 {r.get('points')}"
          f"{'' if ok_pts is None else ('✓' if ok_pts else '✗')} | 자동 {'예' if auto else r.get('auto_block') or r.get('error', '')[:80]}")
    if not ok_hand and mg:
        print(f"      읽음 {' '.join(mg.get('closed', []))} {mg.get('melds')} flags={r.get('flags')}")
tot = [r["total_ms"] for r in rows if "error" not in r]
if tot:
    print(f"시간: 중앙 {statistics.median(tot) / 1000:.1f}s 최대 {max(tot) / 1000:.1f}s")
    for k in ("shrink", "analyze", "crop", "read"):
        xs = [r["stages_ms"][k] for r in rows if k in (r.get("stages_ms") or {})]
        if xs:
            print(f"  {k}: 중앙 {statistics.median(xs) / 1000:.2f}s 최대 {max(xs) / 1000:.2f}s")
n = len(rows)
print(f"화료자 {stats['side']}/{n}, 손패(울기 포함) {stats['hand']}/{n}, 방총자 {stats['loser']}/{n}, "
      f"점수 {stats['pts']}/{stats['pts_n']}, 자동 반영 {stats['auto']}(틀린 반영 {stats['wrong_auto']})")
