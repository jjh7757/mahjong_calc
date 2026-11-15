"""녹화 프레임(rec1496) 최종 라벨 일관성 검사(2026-11-15, 녹화 세트 3단계 6). 고치지 않고 목록만 → data/v1114rec/dr/check.json.
v1114rec_dr_final.py·v1114rec_dr_final_pair.py 다음에.

v1114_dr_check.py 의 ①·②·⑤ 를 세 갈래(pair·mid·new)에 걸쳐:
① scene: 같은 scene_round 안에서 녹화 시각(pair = rec_ms, mid·new = ms) 순으로 이웃한 두 그림(갈래가 달라도) 모든 쌍을, 카메라 밀림(v1114_draft.shift_between,
   2992 기준 값이라 좌표 ×2 로 계산)을 빼고 앞면 중심 거리 < 0.4 × 짧은 변으로 짝지어 역할 또는 주인이 다른 상자. role_use 그림만.
   ※ v1114_dr_check ① 은 화료 사진이 낀 쌍만 봤다(그 세트 프레임 간격이 넓어서). 녹화 세트는 mid 가 기존 두 프레임 사이에 끼므로 모든 이웃 쌍을 본다 —
     판 중에 패가 옮겨지면(버림 뒤 정리·울기) 맞는 갈림도 나온다. 쌍마다 win_or_end(한쪽이 화료·공개 장면인지)를 같이 적는다.
② rules: 자리별 hand > 14, 그림에 pair 1장, loose ≥ 2, 주인 없는 hand·meld·river·loose, 주인 있는 wall·pair·other. role_use 그림만.
⑤ overlap: 같은 그림 상자 둘의 회전 상자 겹침이 작은 쪽 넓이의 50% 이상(한 패에 상자 둘 의심). 모든 그림(use 칸에 det_use).
  python -X utf8 experiments/tile_classifier/v1114rec_dr_check.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from v1114rec_dr_common import DR, OWNED, final_all, inter, jsave  # noqa: E402
from v1114_draft import shift_between  # noqa: E402


def cen(b):
    return np.mean(b["pts"], axis=0)


def t_of(im) -> int:
    return im["rec_ms"] if im["part"] == "pair" else im["ms"]


def main():
    ims = final_all()
    out = {"scene": [], "rules": [], "overlap": []}
    by_scene: dict = {}
    for im in ims:
        if im["role_use"]:
            by_scene.setdefault(im["scene_round"], []).append(im)
    n_pairs = Counter()
    for sr, L in sorted(by_scene.items()):
        L.sort(key=t_of)
        for A, B in zip(L, L[1:]):
            fa = [b for b in A["boxes"] if b["cls"] == "face"]
            fb = [b for b in B["boxes"] if b["cls"] == "face"]
            if len(fa) < 5 or len(fb) < 5:
                continue
            n_pairs[f"{A['part']}-{B['part']}"] += 1
            tile = float(np.median([min(b["rect"][1]) for b in fa])) * 2
            pa, pb = np.array([cen(b) for b in fa]) * 2, np.array([cen(b) for b in fb]) * 2
            dx, dy, sup = shift_between(pa, pb, tile)
            used = set()
            wend = "win" in (A["kind"], B["kind"]) or "end" in (A["phase"], B["phase"])
            for i, b in enumerate(fa):
                dd = np.hypot(pb[:, 0] - dx - pa[i, 0], pb[:, 1] - dy - pa[i, 1])
                j = int(np.argmin(dd))
                if dd[j] >= 0.4 * tile or j in used:
                    continue
                used.add(j)
                c = fb[j]
                if (b["role"], b["seat"]) != (c["role"], c["seat"]):
                    out["scene"].append({"scene_round": sr, "a": A["id"], "a_part": A["part"], "a_box": b["id"], "a_label": f"{b['role']}/{b['seat']}",
                                         "b": B["id"], "b_part": B["part"], "b_box": c["id"], "b_label": f"{c['role']}/{c['seat']}",
                                         "win_or_end": wend, "dt_s": round((t_of(B) - t_of(A)) / 1000, 1), "shift_1496": [round(dx / 2), round(dy / 2), sup]})
    for im in ims:
        iid = im["id"]
        faces = [b for b in im["boxes"] if b["cls"] == "face"]
        if im["role_use"]:
            hs = Counter(b["seat"] for b in faces if b["role"] == "hand")
            for s, n in hs.items():
                if n > 14:
                    out["rules"].append({"id": iid, "part": im["part"], "what": f"hand {s} {n}장 > 14"})
            if sum(b["role"] == "pair" for b in faces) == 1:
                out["rules"].append({"id": iid, "part": im["part"], "what": "pair 1장", "boxes": [b["id"] for b in faces if b["role"] == "pair"]})
            nl = [b["id"] for b in faces if b["role"] == "loose"]
            if len(nl) >= 2:
                out["rules"].append({"id": iid, "part": im["part"], "what": f"loose {len(nl)}장", "boxes": nl})
            for b in faces:
                if b["role"] in OWNED and not b["seat"]:
                    out["rules"].append({"id": iid, "part": im["part"], "what": f"주인 없는 {b['role']}", "boxes": [b["id"]]})
                if b["role"] not in OWNED and b["seat"]:
                    out["rules"].append({"id": iid, "part": im["part"], "what": f"주인 있는 {b['role']}({b['seat']})", "boxes": [b["id"]]})
        bs = im["boxes"]
        for i in range(len(bs)):
            for j in range(i + 1, len(bs)):
                a, b = bs[i], bs[j]
                if np.hypot(*(cen(a) - cen(b))) > max(max(a["rect"][1]), max(b["rect"][1])):
                    continue
                v = inter(a["pts"], b["pts"])
                small = min(cv2.contourArea(np.array(a["pts"], np.float32)), cv2.contourArea(np.array(b["pts"], np.float32)))
                if small > 0 and v / small >= 0.5:
                    out["overlap"].append({"id": iid, "part": im["part"], "a": a["id"], "a_cls": a["cls"], "b": b["id"], "b_cls": b["cls"],
                                           "frac": round(v / small, 2), "use": im["det_use"]})
    summ = {k: len(v) for k, v in out.items()}
    summ["scene_by_parts"] = dict(Counter(f"{r['a_part']}-{r['b_part']}" for r in out["scene"]))
    summ["scene_win_or_end"] = sum(r["win_or_end"] for r in out["scene"])
    summ["scene_neighbor_pairs_checked"] = dict(n_pairs)
    summ["rules_by_what"] = dict(Counter(" ".join(r["what"].split(" ")[:2]) for r in out["rules"]))
    summ["rules_by_part"] = dict(Counter(r["part"] for r in out["rules"]))
    summ["overlap_by_part"] = dict(Counter(r["part"] for r in out["overlap"]))
    jsave(DR / "check.json", {"_note": "일관성 검사(고치지 않음). v1114rec_dr_check.py 머리말 참고", "summary": summ, **out})
    print(json.dumps(summ, ensure_ascii=False, indent=1))
    for k in out:
        for r in out[k][:8]:
            print(k, json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
