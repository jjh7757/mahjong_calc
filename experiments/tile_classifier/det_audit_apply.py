"""전수 조사 제안(audit/fix_g*.json) 모으기·확인 그림·반영(2026-11-04, 7회차).

  python -I -X utf8 experiments/tile_classifier/det_audit_apply.py check   → 제안마다 원본 크롭(지울 것 자홍, 더할 것 초록, 각도 고칠 것 노랑+회전 상자)
                                                                            audit/check_<n>.jpg, audit/check_list.json
  python -I -X utf8 experiments/tile_classifier/det_audit_apply.py apply [--skip 번호,...]
        → audit/fixes.json(det_backs 가 읽는 지우기·더하기) + obb/review_obb.json 에 각도 고치기 더함. 확인에서 뺄 제안은 --skip
그 뒤 det_obb.py → det_audit.py(다시 그림) → det_build.py --rim-blank --neg --backs --obb.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
OBB = HERE / "data" / "det" / "obb"
AUD = OBB / "audit"


def proposals() -> list[dict]:
    """[{n, name, op, box, cls, angle, src}] — op: remove / add / angle."""
    out = []
    rects = json.loads((OBB / "rects.json").read_text(encoding="utf-8"))
    for f in sorted(AUD.glob("fix_g*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for name, v in d.items():
            if name.startswith("_") or not isinstance(v, dict):
                continue
            for op, cls, kk in (("remove", 0, "face_remove"), ("add", 0, "face_add"), ("remove", 1, "back_remove"), ("add", 1, "back_add")):
                for b in v.get(kk, []):
                    out.append(dict(name=name, op=op, cls=cls, box=[int(round(x)) for x in b], src=f.stem))
            for k, a in v.get("angle", {}).items():
                if "|" in k:
                    _, c, bs = k.split("|")
                    box, cls = [int(x) for x in bs.split(",")], int(c)
                else:  # 새 상자 "x,y,w,h"(앞에 "새 상자 " 가 붙기도 한다) — 종류는 같은 제안의 add 에서 찾는다
                    box = [int(round(float(x))) for x in k.replace("새 상자", "").strip().split(",")]
                    cls = next((p["cls"] for p in out if p["name"] == name and p["op"] == "add" and p["box"] == box), 0)
                out.append(dict(name=name, op="angle", cls=cls, box=box, angle=a, src=f.stem))
    for i, p in enumerate(out):
        p["n"] = i
        p["path"] = rects[p["name"]]["path"]
    return out


def check(only: set[str] | None = None, tag: str = "") -> None:
    """only: 제안 파일 이름(fix_g2 등)만 그린다 — 그림 이름 check<tag>_<n>.jpg. 번호(n)는 전체 목록 번호 그대로."""
    ps = proposals()
    (AUD / "check_list.json").write_text(json.dumps(ps, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.path.insert(0, str(HERE))
    from det_obb import inscribed

    cells = []
    for p in [q for q in ps if not only or q["src"] in only]:
        bgr = cv2.imread(p["path"])
        x, y, w, h = p["box"]
        pad = int(1.2 * max(w, h))
        X0, Y0 = max(0, x - pad), max(0, y - pad)
        crop = bgr[Y0:y + h + pad, X0:x + w + pad].copy()
        col = {"remove": (255, 0, 255), "add": (0, 220, 0), "angle": (0, 255, 255)}[p["op"]]
        cv2.rectangle(crop, (x - X0, y - Y0), (x - X0 + w, y - Y0 + h), col, 2)
        if p["op"] == "angle" and p["angle"] != "axis":
            r = inscribed(p["box"], abs(float(p["angle"])), 1.0 if float(p["angle"]) >= 0 else -1.0)
            if r:
                pts = cv2.boxPoints(((r[0][0] - X0, r[0][1] - Y0), r[1], r[2])).astype(np.int32)
                cv2.polylines(crop, [pts], True, (0, 120, 255), 2)
        crop = cv2.resize(crop, (300, 300))
        lab = f"{p['n']} {p['op']} {'F' if p['cls'] == 0 else 'B'}" + (f" {p['angle']}" if p["op"] == "angle" else "")
        cv2.putText(crop, lab, (4, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(crop, p["name"][-6:], (4, 292), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cells.append(crop)
    for s in range(0, len(cells), 30):
        part = cells[s:s + 30]
        while len(part) % 6:
            part.append(np.zeros_like(part[0]))
        cv2.imwrite(str(AUD / f"check{tag}_{s // 30}.jpg"), np.vstack([np.hstack(part[k:k + 6]) for k in range(0, len(part), 6)]), [cv2.IMWRITE_JPEG_QUALITY, 85])
    from collections import Counter

    print("제안", len(ps), Counter((p["op"], p["cls"]) for p in ps), "그림", -(-len(cells) // 30), "장")


def apply(skip: set[int]) -> None:
    ps = [p for p in proposals() if p["n"] not in skip]
    fixes: dict = {}
    for p in ps:
        if p["op"] in ("remove", "add"):
            kind = ("FACE_" if p["cls"] == 0 else "BACK_") + p["op"].upper()
            fixes.setdefault(kind, {}).setdefault(p["name"], []).append(p["box"])
    (AUD / "fixes.json").write_text(json.dumps(dict(fixes, _note="전수 조사(det_audit_apply.py apply) 결과. det_backs 가 FACE_*·BACK_* 에 더해 읽는다"), ensure_ascii=False, indent=1), encoding="utf-8")
    rf = OBB / "review_obb.json"
    picks = json.loads(rf.read_text(encoding="utf-8"))
    for p in ps:
        if p["op"] == "angle":
            k = f"{p['name']}|{p['cls']}|{','.join(str(v) for v in p['box'])}"
            picks[k] = "axis" if p["angle"] == "axis" else {"angle": float(p["angle"])}
            picks.setdefault("_notes", {})[k] = f"전수 조사 {p['src']} #{p['n']}"
    rf.write_text(json.dumps(picks, ensure_ascii=False, indent=1), encoding="utf-8")
    print("반영", len(ps), "건(뺀 것", len(skip), ")", {k: sum(len(v) for v in d.values()) for k, d in fixes.items()})


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1] == "check":
        only = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else None
        check(only, "_" + "_".join(sorted(only)) if only else "")
    else:
        sk = set()
        if "--skip" in sys.argv:
            sk = {int(x) for x in sys.argv[sys.argv.index("--skip") + 1].split(",") if x}
        apply(sk)
