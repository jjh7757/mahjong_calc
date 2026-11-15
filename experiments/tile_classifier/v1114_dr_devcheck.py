"""기기 위치 추정 의심 그림 훑기(2026-11-15, 검출·역할 세트 3단계). 고치지 않고 목록만 → data/v1114/dr/device_check.json.

draft 의 device(펠트 편 좌표 가운데, 리치봉 홈이 보이면 그 가운데로 다듬음)를 최종 라벨과 맞댄다:
  in_dev  = 앞면 상자 중심이 기기 사각형(cx±hd, cy±hd) 안에 든 수(강 패가 기기 위에 있을 리 없음) — 2개 이상이면 의심
  off     = 기기 중심 ↔ 펠트 사각형 가운데(felt_pred) 거리 / hd — 0.3 넘으면 의심(리치봉 홈으로 다듬은 값은 평소 0.1 안팎)
  river_c = 앞면 river 상자 중심의 가운데 ↔ 기기 중심 거리 / hd(강은 기기를 둘러싸므로 평소 작다) — 0.6 넘으면 의심
  felt    = 펠트 면적 비율(펠트를 잘못 잡으면 기기도 틀림) — 0.6 미만이면 의심
  python -X utf8 experiments/tile_classifier/v1114_dr_devcheck.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DR = HERE / "data" / "v1114" / "dr"


def main():
    rows = []
    for p in sorted((DR / "final").glob("r*.json")):
        for im in json.loads(p.read_text(encoding="utf-8"))["images"]:
            dv = im["device"]
            cx, cy, hd = dv["cx"], dv["cy"], dv["hd"]
            faces = [b for b in im["boxes"] if b["cls"] == "face"]
            cen = lambda b: np.mean(b["pts"], axis=0)
            in_dev = [b["id"] for b in faces if abs(cen(b)[0] - cx) < hd and abs(cen(b)[1] - cy) < hd]
            fp = dv.get("felt_pred") or {"cx": cx, "cy": cy}
            off = float(np.hypot(cx - fp["cx"], cy - fp["cy"]) / hd)
            riv = [cen(b) for b in faces if b["role"] == "river"]
            river_c = float(np.hypot(*(np.mean(riv, axis=0) - [cx, cy])) / hd) if len(riv) >= 8 else None
            why = []
            if len(in_dev) >= 2:
                why.append(f"기기 안 앞면 {len(in_dev)}")
            if off > 0.3:
                why.append(f"펠트 가운데와 {off:.2f}hd")
            if river_c is not None and river_c > 0.6:
                why.append(f"강 가운데와 {river_c:.2f}hd")
            if im["felt"]["area_frac"] < 0.6:
                why.append(f"펠트 면적 {im['felt']['area_frac']}")
            r = {"id": im["id"], "device": [cx, cy, hd, dv["src"]], "faces_in_device": in_dev, "felt_off_hd": round(off, 2),
                 "river_center_off_hd": None if river_c is None else round(river_c, 2), "felt_area": im["felt"]["area_frac"],
                 "role_use": im["role_use"], "why": why}
            if why:
                rows.append(r)
    (DR / "device_check.json").write_text(json.dumps({"_note": "기기 위치 의심 그림(고치지 않음). v1114_dr_devcheck.py 머리말 기준", "images": rows}, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    for r in rows:
        print(r["id"], r["device"], r["why"], "role_use" if r["role_use"] else "(역할 세트 밖)")
    print(len(rows), "장")


if __name__ == "__main__":
    main()
