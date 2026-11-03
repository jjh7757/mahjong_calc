"""앱 흐름 로그의 리치를 정답과 대조한다(표 3-3). flow_visit.py 는 손패만 봐서 리치를 놓친 자동 반영을 못 잡는다.
자리별 정답 = B·C·D 는 river_sideways26.BCD_YES, 매장은 river_truth.json(눈 정답, "?자리" 는 모름). 화료자는 merge.riichi, 나머지는 merge.riichi_seats_photo.
  python -I -X utf8 experiments/speed/flow_riichi.py <로그 앞부분>...   예: results/log_flow_ld_only  → <앞부분>_{bcd,am,pm}.txt
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRUTH = json.loads((ROOT / "experiments/tile_classifier/river_truth.json").read_text(encoding="utf-8"))
BCD_YES = {"k25": {"bottom", "left"}, "k28": {"bottom", "left"}, "k15": {"left"}, "k26": {"left"}, "k12": {"top", "bottom"}, "k16": {"top", "bottom"}}
SIDES = ["bottom", "right", "top", "left"]


def rows(prefix: str) -> list[dict]:
    out = []
    for part in ("bcd", "am", "pm"):
        for line in Path(f"{prefix}_{part}.txt").read_text(encoding="utf-8", errors="replace").splitlines():
            i = line.find("TIMING {")
            if i >= 0:
                r = json.loads(line[i + 7:])
                if r["photo"] in BCD_YES or r["photo"] in TRUTH:
                    r["part"] = part
                    out.append(r)
    return out


def main(prefix: str) -> None:
    tally = dict(n=0, win_yes=0, win_yes_ok=0, win_no=0, win_no_ok=0, other_extra=0, auto=0, auto_bad=0)
    print("==", prefix)
    for r in rows(prefix):
        m = r.get("merge") or {}
        if not m:
            continue
        marks = BCD_YES[r["photo"]] if r["photo"] in BCD_YES else TRUTH[r["photo"]]
        win = m.get("winner")
        win_side = SIDES[win] if win is not None else None
        photo = {SIDES[i] for i in m.get("riichi_seats_photo") or []}
        tally["n"] += 1
        bad = []
        # 울린 손패는 리치가 불가능해 앱이 무시한다(B·C·D 는 연출이라 강에 눕힌 패가 있어도 운다). 화료자 대조에서 뺀다
        if win_side and f"?{win_side}" not in marks and not m.get("melds"):
            want = win_side in marks
            tally["win_yes" if want else "win_no"] += 1
            ok = bool(m.get("riichi")) == want
            tally["win_yes_ok" if want else "win_no_ok"] += ok
            if not ok:
                bad.append(f"화료자 리치 답 {m.get('riichi')} 정답 {want}")
        extra = sorted(s for s in photo if s != win_side and s not in marks and f"?{s}" not in marks)
        tally["other_extra"] += len(extra)
        if extra:
            bad.append(f"헛 리치 자리 {extra}")
        auto = r.get("auto_block") is None and "error" not in r
        tally["auto"] += auto
        tally["auto_bad"] += auto and bool(bad)
        if bad:
            print(" ", r["photo"], r["run"], "자동" if auto else r.get("auto_block"), "|", "; ".join(bad))
    print(" ", tally)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for p in sys.argv[1:]:
        main(p)
