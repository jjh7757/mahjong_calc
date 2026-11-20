"""늘어남 규칙 — safetycheck 결과에서 "복원 손패 정렬 어긋남이 바로 뒤 차례보다 JUMP 이상 늘어난 차례" 를 찾음(2026-11-19, 계획서 "추가 49" 결과 뒤 단서 → "추가 50" ③).

  python -X utf8 jumprule.py [--file _work/safetycheck_1119/c1.json] [--jump 2]

결과를 본 뒤 고른 규칙(다섯 판에서 r16 13순만 걸림)이라, 다른 판(r15 · L16)에서 그대로 대 보는 용도. 정답은 안 씀(복원이 틀린 판인지 표시만 safetycheck 의 same_as_truth 에서).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(hc.WORK / "safetycheck_1119" / "c1.json"))
    ap.add_argument("--jump", type=int, default=2)
    a = ap.parse_args()
    d = hc.jload(Path(a.file))
    for gid, rows in d.items():
        hits = [rows[i]["id"] for i in range(len(rows) - 1) if rows[i]["S2"] - rows[i + 1]["S2"] >= a.jump]
        bad = not all(r["same_as_truth"] for r in rows)
        wrong = [r["id"] for r in rows if r["wrong_read"]]
        ok = bool(hits) == bad
        print(f"{gid}: 복원 {'다름' if bad else '같음'} · 틀린 읽기 {wrong} · 걸린 차례(+{a.jump}) {hits} → {'✓' if ok else '✗'}")


if __name__ == "__main__":
    main()
