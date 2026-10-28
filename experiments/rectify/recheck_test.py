"""[테스트 세트, 한 번만] 매장 15장: 리치봉 3번 읽기 + 5 패 재확인이 틀린 자동 반영을 막는지(2026-10-27, 사용자 요청).
이 결과로 규칙을 고치지 않는다.

입력: 앱 흐름 로그(펴기, `read_grid_timing_test.dart` SET=field RECTIFY=true DUMP_DIR=…)와 그 실행이 판독에 보낸 크롭
(test_crops/<사진>/seat.jpg·sticks.jpg). 추가 판독은 개발 세트 실험(`speed/recheck.py`)과 같은 문구·방식:
  - 리치봉: 같은 프롬프트 + 판독 번호 표식으로 3번 동시 → 셋이 다르거나, 같아도 앱 흐름의 리치봉 답과 다르면 확인.
  - 5 패: "5 패와 빨간 5 여부만" 묻는 재확인 1번 → 앱 흐름 자리 판독의 5 패(무늬·빨강)와 다르면 확인.
새 자동 반영 = 기존 자동 반영 조건 통과 && 리치봉 확인 없음 && 5 패 확인 없음.

  python -X utf8 experiments/rectify/recheck_test.py <로그>
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent / "speed"))
import recheck as rc  # noqa: E402

from app import observe as ob  # noqa: E402

CROPS = ROOT / "test_crops"
# 정답(NOTES 30·summarize_field.py 와 같음): 화료자 면, 방총자, 손패(화료패 포함), 울기, 점수(모르면 None)
TRUTH = {
    "F1229": ("right", 2, "4m 0m 7m 8m 9m 1s 2s 3s 4p 4p 5z 5z 5z 3m", [], "12000"),
    "F1240": ("top", 0, "1s 3s 2s 3s 4s 5p 5p 7z 7z 7z 5z 5z 5z 2s", [], "6700"),
    "F대삼원": ("top", 3, "3s 4s 5p 5p 7z 7z 7z 5z 5z 5z 2s", ["[6z 6z 6z]"], "48000"),
    "F1400": ("left", 1, "3p 3p 4m 0m 6m 4s 4s 4s 6s 7s 8s 9s 9s 3p", [], None),
    "F1434": ("left", 1, "3p 3p 5p 5p 4m 5m 6m 6s 7s 8s 3p", ["(4s 4s 4s 4s)"], None),
}


def fives_truth(scene: str) -> Counter:
    side, loser, hand, melds, pts = TRUTH[scene]
    codes = hand.split() + [c for m in melds for c in re.sub(r"[\[\]()]", "", m).split()]
    return Counter((c[1], c[0] == "0") for c in codes if c[0] in "05" and c[1] in "mps")


def fives_of_read(h: dict | None) -> Counter:
    if not h:
        return Counter()
    codes = [t["tile"] for t in h.get("tiles") or []] + ([h["win_tile"]["tile"]] if h.get("win_tile") else [])
    codes += [c for m in h.get("melds") or [] for c in m.get("tiles") or []]
    return Counter((c[1], c[0] == "0") for c in codes if c[0] in "05" and c[1] in "mps")


def main() -> None:
    rows = [json.loads(m.group(1)) for line in open(sys.argv[1], encoding="utf-8", errors="replace")
            if (m := re.search(r"TIMING (\{.*\})", line))]
    jobs = []
    for r in rows:
        d = CROPS / r["photo"]
        if (d / "sticks.jpg").exists():
            data = (d / "sticks.jpg").read_bytes()
            for k in range(3):
                jobs.append(((r["photo"], "stick", k), [rc.b.image_part(data, None), ob.STICKS_PROMPT_V2 + f"\n\n(판독 {k + 1})"],
                             ob.STICKS_SCHEMA_V2, rc.sticks_of))
        if (d / "seat.jpg").exists():
            jobs.append(((r["photo"], "five", 0), rc.seat_contents((d / "seat.jpg").read_bytes(), rc.FIVES_PROMPT + "\n\n(판독 1)"),
                         rc.FIVES_SCHEMA, rc.fives_from_check))
    with ThreadPoolExecutor(12) as ex:
        res = dict(zip([j[0] for j in jobs], ex.map(lambda j: j[3](rc.ask(j[1], j[2])), jobs)))

    c = Counter()
    out = []
    for r in rows:
        scene, photo = r["scene"], r["photo"]
        side, loser, hand, melds, pts = TRUTH[scene]
        mg = r.get("merge") or {}
        ok = (r.get("winner") == side and Counter(mg.get("closed", [])) == Counter(hand.split())
              and sorted(mg.get("melds", [])) == sorted(melds) and mg.get("loser") == loser
              and (pts is None or r.get("points") == pts))
        auto_old = r.get("auto_block") is None and "error" not in r
        three = [res.get((photo, "stick", k)) for k in range(3)]
        app_sticks = frozenset(s for s, v in ((r.get("center_read") or {}).get("riichi") or {}).items() if v)
        stick_flag = None in three or len(set(three)) != 1 or three[0] != app_sticks
        seat_fives = fives_of_read(r.get("hand_read"))
        chk = res.get((photo, "five", 0))
        five_flag = chk is None or chk != seat_fives
        auto_new = auto_old and not stick_flag and not five_flag
        c.update(n=1, ok=ok, auto_old=auto_old, wrong_old=auto_old and not ok, auto_new=auto_new, wrong_new=auto_new and not ok,
                 stick_flag=stick_flag, five_flag=five_flag, seat_five_wrong=seat_fives != fives_truth(scene),
                 check_five_wrong=chk != fives_truth(scene))
        out.append(dict(photo=photo, scene=scene, ok=ok, auto_old=auto_old, auto_new=auto_new, app_sticks=sorted(app_sticks),
                        three=[sorted(x) if x is not None else None for x in three], stick_flag=stick_flag,
                        seat_fives=sorted([list(k), v] for k, v in seat_fives.items()),
                        check_fives=sorted([list(k), v] for k, v in chk.items()) if chk is not None else None, five_flag=five_flag))
        print(f"  {scene} {photo}: 정답 {'O' if ok else 'X'} | 자동 전 {'예' if auto_old else '-'} 후 {'예' if auto_new else '-'} | "
              f"리치봉 앱 {sorted(app_sticks)} 3번 {[sorted(x) if x is not None else None for x in three]} {'확인' if stick_flag else ''} | "
              f"5 패 자리 {dict(seat_fives)} 재확인 {dict(chk) if chk is not None else None} {'확인' if five_flag else ''}")
    (ROOT / "logs" / "recheck_test.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"n={c['n']} 정답 {c['ok']} | 자동 반영 전 {c['auto_old']}(틀림 {c['wrong_old']}) → 후 {c['auto_new']}(틀림 {c['wrong_new']}) | "
          f"리치봉 확인 {c['stick_flag']} · 5 패 확인 {c['five_flag']} | 5 패 틀림: 자리 판독 {c['seat_five_wrong']} · 재확인 {c['check_five_wrong']}")


if __name__ == "__main__":
    main()
