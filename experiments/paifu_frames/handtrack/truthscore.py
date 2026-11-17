"""저장된 자동 판정(testrun run.json = pixtrack 거르기 + inplace 들어간 칸)을 사용자 정답과 맞대기(2026-11-17).

  python -X utf8 truthscore.py <판 id>
자동 차례 = 강이 정확히 1장 는 손 움직임 구간. 정답 차례와는 "버림" 구간 번호로 잇는다. 정답의 칸은 k_orig(뽑은 패를 뺀 번호) · j_closed(메운 뒤 번호).
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402

BASE = hc.WORK / "testtruth_1116"
MODE = {"tsumogiri": "쯔모기리", "hand": "손에서"}


def main():
    gid = sys.argv[1]
    g = next(x for x in hc.jload(BASE / "turns.json")["games"] if x["id"] == gid)
    ans = hc.jload(BASE / "truth_final.json")  # truthnorm.py
    auto = {r["seg"]: r for r in hc.jload(hc.WORK / "testrun_1116" / "run.json")["rows"] if r["game"] == gid}
    c = Counter()
    print("차례 | 정답(종류 k j) | 화소 규칙(종류 k j) | 들어간 칸 규칙 j | 판정")
    for t in g["turns"]:
        a = ans.get(t["id"]) or {}
        own = next(s["seg"] for s in t["segs"] if s["role"] == "버림")
        r = auto.get(own)
        tk = a.get("k_id") if a.get("kind") == "hand" else None
        tj = a.get("j_closed") if a.get("kind") == "hand" else None
        truth = f"{MODE.get(a.get('kind'), a.get('kind'))} {tk or ''} {tj or ''}".strip()
        c["정답 차례"] += 1
        if r is None or t["same_seg"] != 1:
            c["자동 차례로 안 잡힘"] += 1
            print(f"{t.get('label', t['i']):>3} | {truth} | (자동 차례 없음 — 구간 {own} 강 {t['same_seg']}장) | |")
            continue
        mode = r.get("mode")
        kind_ok = mode == MODE.get(a.get("kind"))
        c["종류: " + ("맞음" if kind_ok else ("모름" if mode in ("모름", "N 못 잼") else "틀림"))] += 1
        note = []
        if a.get("kind") == "hand":
            c["손에서(정답)"] += 1
            kp, jp, ji = r.get("k_pix"), r.get("j_pix"), r.get("j")
            c["나간 칸: " + ("맞음" if kp == tk else ("없음" if kp is None else "틀림"))] += 1
            c["들어간 칸(화소 규칙): " + ("맞음" if jp == tj else ("없음" if jp is None else "틀림"))] += 1
            c["들어간 칸(제자리 세기): " + ("맞음" if ji == tj else ("없음" if ji is None else "틀림"))] += 1
            c["차례 전체 맞음"] += kind_ok and kp == tk and jp == tj
        else:
            c["쯔모기리(정답)"] += 1
            if r.get("j") is not None:
                note.append("쯔모기리인데 들어간 칸을 답함")
            c["차례 전체 맞음"] += kind_ok
        print(f"{t.get('label', t['i']):>3} | {truth} | {mode} {r.get('k_pix') or ''} {r.get('j_pix') or ''} (N {r.get('n')}) | {r.get('j') or ''} | {'종류 ' + ('✓' if kind_ok else '✗')} {' '.join(note)}")
    print(" · ".join(f"{k} {v}" for k, v in c.items()))


if __name__ == "__main__":
    main()
