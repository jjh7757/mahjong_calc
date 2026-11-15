"""최종 라벨 일관성 검사(2026-11-15, 검출·역할 세트 3단계 5). 고치지 않고 목록만 → data/v1114/dr/check.json. v1114_dr_final.py 다음에.

① scene: 같은 scene_round 안에서 시간순으로 이웃한 두 그림 중 하나라도 화료 사진인 쌍(화료 사진 여러 장, 마지막 프레임 ↔ 화료 사진,
   앞 판 탁자가 남은 첫 프레임 ↔ 앞 판 화료 사진)을, 카메라 밀림(v1114_draft.shift_between)을 빼고 앞면 중심 거리 < 0.4 × 짧은 변으로 짝지어
   역할 또는 주인이 다른 상자. tidy·흔들림·탁자 아님 그림은 뺀다.
② rules: 자리별 hand > 14, 그림에 pair 가 1장, loose ≥ 2, 주인 없는 hand·meld·river·loose, 주인 있는 wall·pair·other.
③ both_differ: 최종 역할·주인이 규칙 초안(draft rule)과도 모델 답(draft model: 운영 역할 + D 주인)과도 다른 상자(더한 상자 제외).
④ win_hand: 화료 사진의 화료자 hand+loose 수 ≠ 정답(label.json closed, 론이면 closed−1 도 허용).
⑤ overlap: 같은 그림 상자 둘의 회전 상자 겹침이 작은 쪽 넓이의 50% 이상(한 패에 상자 둘 의심).
  python -X utf8 experiments/tile_classifier/v1114_dr_check.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
DR = HERE / "data" / "v1114" / "dr"
sys.path.insert(0, str(HERE))
from v1114_draft import shift_between  # noqa: E402

OWNED = ("hand", "loose", "meld", "river")


def cen(b):
    return np.mean(b["pts"], axis=0)


def inter(a, b) -> float:
    v, _ = cv2.intersectConvexConvex(np.array(a, np.float32), np.array(b, np.float32))
    return float(v)


def main():
    finals, drafts = {}, {}
    for p in sorted((DR / "final").glob("r*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        for im in d["images"]:
            finals[im["id"]] = im
    for p in sorted((DR / "draft").glob("r*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        for im in d["images"]:
            drafts[im["id"]] = im
    out = {"scene": [], "rules": [], "both_differ": [], "win_hand": [], "overlap": []}
    # ① 장면
    by_scene: dict = {}
    for im in finals.values():
        if im["role_use"]:
            by_scene.setdefault(im["scene_round"], []).append(im)
    for sr, ims in by_scene.items():
        ims.sort(key=lambda x: x["at"])
        for A, B in zip(ims, ims[1:]):
            if "win" not in (A["kind"], B["kind"]):
                continue
            fa = [b for b in A["boxes"] if b["cls"] == "face"]
            fb = [b for b in B["boxes"] if b["cls"] == "face"]
            if len(fa) < 5 or len(fb) < 5:
                continue
            tile = float(np.median([min(b["rect"][1]) for b in fa]))
            pa, pb = np.array([cen(b) for b in fa]), np.array([cen(b) for b in fb])
            dx, dy, sup = shift_between(pa, pb, tile)
            used = set()
            n_pair = 0
            for i, b in enumerate(fa):
                dd = np.hypot(pb[:, 0] - dx - pa[i, 0], pb[:, 1] - dy - pa[i, 1])
                j = int(np.argmin(dd))
                if dd[j] >= 0.4 * tile or j in used:
                    continue
                used.add(j)
                n_pair += 1
                c = fb[j]
                if (b["role"], b["seat"]) != (c["role"], c["seat"]):
                    out["scene"].append({"scene_round": sr, "a": A["id"], "a_box": b["id"], "a_label": f"{b['role']}/{b['seat']}", "b": B["id"], "b_box": c["id"],
                                         "b_label": f"{c['role']}/{c['seat']}", "tile_a": b.get("tile"), "tile_b": c.get("tile"), "shift": [round(dx), round(dy), sup]})
    # ②③④⑤
    for iid, im in finals.items():
        faces = [b for b in im["boxes"] if b["cls"] == "face"]
        if im["role_use"]:
            hs = Counter(b["seat"] for b in faces if b["role"] == "hand")
            for s, n in hs.items():
                if n > 14:
                    out["rules"].append({"id": iid, "what": f"hand {s} {n}장 > 14"})
            npair = sum(b["role"] == "pair" for b in faces)
            if npair == 1:
                out["rules"].append({"id": iid, "what": "pair 1장", "boxes": [b["id"] for b in faces if b["role"] == "pair"]})
            nl = [b["id"] for b in faces if b["role"] == "loose"]
            if len(nl) >= 2:
                out["rules"].append({"id": iid, "what": f"loose {len(nl)}장", "boxes": nl})
            for b in faces:
                if b["role"] in OWNED and not b["seat"]:
                    out["rules"].append({"id": iid, "what": f"주인 없는 {b['role']}", "boxes": [b["id"]]})
                if b["role"] not in OWNED and b["seat"]:
                    out["rules"].append({"id": iid, "what": f"주인 있는 {b['role']}({b['seat']})", "boxes": [b["id"]]})
            dbox = {b["id"]: b for b in drafts[iid]["boxes"]}
            for b in faces:
                dbx = dbox.get(b["id"])
                if dbx is None or not dbx.get("rule") or not dbx.get("model"):
                    continue
                r, m = dbx["rule"], dbx["model"]
                fin = (b["role"], b["seat"] if b["role"] in OWNED else None)
                ru = (r["role"], r["seat"] if r["role"] in OWNED else None)
                mo = (m["role"], m["seat"] if m["role"] in OWNED else None)
                if fin != ru and fin != mo:
                    out["both_differ"].append({"id": iid, "box": b["id"], "final": f"{fin[0]}/{fin[1]}", "rule": f"{ru[0]}/{ru[1]}", "model": f"{mo[0]}/{mo[1]}",
                                               "d": f"{m['d_role']}/{m['d_seat']}", "tile": b.get("tile")})
            lc = drafts[iid].get("label_check")
            if im["kind"] == "win" and lc and im["winner"]:
                lab = lc["label"]
                closed = len(lab.get("closed") or [])
                ok = {closed} if lab.get("is_tsumo") else {closed, closed - 1}
                n = sum(1 for b in faces if b["role"] in ("hand", "loose") and b["seat"] == im["winner"])
                if n not in ok:
                    out["win_hand"].append({"id": iid, "winner": im["winner"], "hand_loose": n, "closed": closed, "tsumo": lab.get("is_tsumo"), "label_src": lc["label_src"]})
        bs = im["boxes"]
        for i in range(len(bs)):
            for j in range(i + 1, len(bs)):
                a, b = bs[i], bs[j]
                if np.hypot(*(cen(a) - cen(b))) > max(max(a["rect"][1]), max(b["rect"][1])):
                    continue
                v = inter(a["pts"], b["pts"])
                small = min(cv2.contourArea(np.array(a["pts"], np.float32)), cv2.contourArea(np.array(b["pts"], np.float32)))
                if small > 0 and v / small >= 0.5:
                    out["overlap"].append({"id": iid, "a": a["id"], "a_cls": a["cls"], "b": b["id"], "b_cls": b["cls"], "frac": round(v / small, 2), "use": im["det_use"]})
    summ = {k: len(v) for k, v in out.items()}
    summ["rules_by_what"] = dict(Counter(r["what"].split(" ")[0] + " " + (r["what"].split(" ")[1] if len(r["what"].split(" ")) > 1 else "") for r in out["rules"]))
    (DR / "check.json").write_text(json.dumps({"_note": "일관성 검사(고치지 않음). v1114_dr_check.py 머리말 참고", "summary": summ, **out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summ, ensure_ascii=False, indent=1))
    for k in out:
        for r in out[k][:6]:
            print(k, json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
