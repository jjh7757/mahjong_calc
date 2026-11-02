"""2회차 상자 라벨을 눈 검토로 고친다(2026-11-02, Claude 가 확대해 봄, 사용자 확인 전). det_relabel.py 다음에.

ADD = 검출기가 놓친 탁자 모서리 白 울기와 패산 옆 白 (x0, y0, x1, y1, 원본 좌표). REMOVE = 패 뒷면을 잡은 상자의 가운데 점.
  python -I experiments/tile_classifier/det_review.py
결과 data/det/boxes_final.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DET = Path(__file__).resolve().parent / "data" / "det"
ADD = {
    "20261031_164501": [(724, 2664, 824, 2784), (742, 2784, 850, 2860), (746, 2860, 858, 2932)],
    "20261031_171245": [(728, 2664, 848, 2760), (740, 2760, 836, 2860), (740, 2860, 844, 2936)],
    "20261031_165614": [(3434, 80, 3562, 172), (3462, 176, 3570, 304), (3422, 308, 3562, 412)],
    "20261031_183022": [(3486, 82, 3574, 208), (3450, 208, 3574, 304), (3450, 304, 3570, 420)],
    "20261031_124654": [(3116, 1152, 3248, 1252), (3118, 1236, 3232, 1320)],
    "20261031_142535": [(860, 1062, 980, 1184), (864, 1152, 1000, 1268)],
}
REMOVE = {"20261031_143104": [(1745, 797)], "20261031_183627": [(1737, 2376), (1813, 2354)]}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = json.loads((DET / "boxes_r2.json").read_text(encoding="utf-8"))
    removed = 0
    for name, pts in REMOVE.items():
        keep = []
        for b in rows[name]["boxes"]:
            hit = any(b[0] <= x <= b[0] + b[2] and b[1] <= y <= b[1] + b[3] for x, y in pts)
            removed += hit
            if not hit:
                keep.append(b)
        rows[name]["boxes"] = keep
    added = 0
    for name, bs in ADD.items():
        for x0, y0, x1, y1 in bs:
            rows[name]["boxes"].append([x0, y0, x1 - x0, y1 - y0])
            added += 1
    for r in rows.values():
        r.pop("conf", None)
    (DET / "boxes_final.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("뺌", removed, "더함", added, "합계", sum(len(r["boxes"]) for r in rows.values()))


if __name__ == "__main__":
    main()
