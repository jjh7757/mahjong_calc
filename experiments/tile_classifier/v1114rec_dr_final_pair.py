"""녹화 프레임 짝(pair) 186장 최종 라벨(2026-11-15, 녹화 세트 3단계 2). v1114rec_pair.py(pairs.json)·짝 눈 확인(pair/review) 다음에. 다시 돌려도 같은 결과.

짝 = 기존 세트(data/v1114) 그림과 같은 순간의 헤드 녹화 프레임(1496²). 라벨은 기존 최종 라벨(data/v1114/dr/final, 2992 좌표)을 ×0.5 로 옮긴다
  (rect 중심·크기 ×0.5·각도 그대로, pts ×0.5, box 는 pts 에서 다시). 상자 id·종류·역할·주인·tile(분류기 세트 종류)·role_src·src 그대로.
  그림 칸 phase·winner·winner_src·flags·det_use·role_use·excluded_why·split_final·scene_round·scene·kind·format 그대로, felt.quad·device(cx cy hd) ×0.5,
  grid_est 는 천분율이라 그대로.
눈 확인 반영(pair/review/answers_NN.json + _key.json, 상자 차이 box_diff > 7 인 478칸):
  occluded → 그 상자를 뺀다(dropped_pair_review). same → 그대로. moved·different·unsure → 이 스크립트는 그대로 두고, 고침은 pair/overrides.json 에서만.
pair/overrides.json(그림 id → {reason, boxes: {상자 id: {op: drop | move | flip, rect(move 일 때, 1496), note}}, adds: [{aid, cls, rect, fit, role, seat, note}]})
  를 읽어 적용 — moved 가 나온 세 그림을 계획 세션 지시대로 직접 고친 것(v1114rec_dr_pairfix.py 로 맞추고 전·후 그림 pair/fix/) +
  4단계(2026-11-15) 독립 검토(dr/audit)·검출기 헛검출 전수 확인(dr/unmatched_review.json)에서 더한 상자(adds, id = pN — 기존 세트의 aN 과 안 겹치게,
  src add_pair, edit add, pair_fix.op add)와 지운 상자. 더하기는 v1114rec_dr_pairfix.py add 로(마스크 맞춤 + 확인 그림).
pairs.json status no_rec(짝 없음) 3장은 라벨을 만들지 않고 _summary.json 에 이름만.
그 밖 칸: part = "pair", src_id = 기존 그림 id(이 그림 id 와 같음), pre_game = phase play 이고 강(river) 앞면 0(표시만 — 짝은 role_use 를 기존 세트에서
  물려받으므로 이것으로 빼지 않는다, mid·new 와 같은 기준이라 쓰는 쪽에서 거를 수 있음), pre_game_info = 같은 값(옛 이름), between = false(짝은 표시 안 함).
  상자마다 pair_review = 짝 눈 확인 판정(없으면 null), pair_fix = overrides 적용(move·drop, 없으면 null), box_diff_pairs = pairs.json 의 box_diff.
  python -X utf8 experiments/tile_classifier/v1114rec_dr_final_pair.py
결과 data/v1114rec/dr/final_pair/<판>.json, final_pair/_summary.json
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from v1114rec_dr_common import DR, R, V, box_of, half_box_rec, jload, jsave, rect_pts  # noqa: E402

OUT = DR / "final_pair"
PR = R / "pair"


def verdicts() -> dict:
    """(그림 id, 상자 id 문자열) → {verdict, note, sheet, cell, reviewer}"""
    key = jload(PR / "review" / "_key.json")["sheets"]
    out = {}
    for s, cells in key.items():
        a = jload(PR / "review" / f"answers_{s}.json")
        assert set(a["cells"]) == set(cells), s
        for n, k in cells.items():
            v = a["cells"][n]
            out[(k["id"], str(k["box_id"]))] = {"verdict": v["verdict"], "note": v.get("note", ""), "sheet": s, "cell": n, "reviewer": a.get("reviewer")}
    return out


def overrides() -> dict:
    p = PR / "overrides.json"
    return jload(p)["images"] if p.exists() else {}


def old_finals() -> dict:
    out = {}
    for p in sorted((V / "dr" / "final").glob("r*.json")):
        for im in jload(p)["images"]:
            out[im["id"]] = im
    return out


def pair_image(pe: dict, F: dict, vd: dict, ov: dict | None, use_overrides=True) -> tuple[dict, Counter]:
    """짝 항목 pe(pairs.json) + 기존 최종 그림 F → 녹화 그림 라벨."""
    c = Counter()
    W, H = 1496, 1496
    pb = {str(b["box_id"]): b for b in pe["boxes"]}
    ovb = (ov or {}).get("boxes", {}) if use_overrides else {}
    boxes = []
    for b in F["boxes"]:
        sid = str(b["id"])
        h = half_box_rec(b, W, H)
        if sid in pb:  # pairs.json 의 ×0.5 와 같은지(같은 원천)
            d = float(np.abs(np.array(pb[sid]["pts_1496"]) - np.array(h["pts"])).max())
            c["pts_check_max_x100"] = max(c["pts_check_max_x100"], int(round(d * 100)))
        v = vd.get((F["id"], sid))
        nb = {k: b.get(k) for k in ("id", "cls", "src", "tile", "role", "seat", "role_src", "edit")}
        nb.update(h)
        if b.get("role_missing"):
            nb["role_missing"] = True
        nb["pair_review"] = {"verdict": v["verdict"], "note": v["note"]} if v else None
        nb["box_diff_pairs"] = pb.get(sid, {}).get("box_diff")
        nb["pair_fix"] = None
        if v:
            c[f"review_{v['verdict']}"] += 1
        o = ovb.get(sid)
        if o is not None:
            nb["pair_fix"] = {"op": o["op"], "note": o.get("note", "")}
            if o["op"] == "drop":
                c[f"override_drop_{b['cls']}"] += 1
                continue
            if o["op"] == "flip":
                nb["cls"] = "back" if b["cls"] == "face" else "face"
                if nb["cls"] == "back":
                    nb["role"] = nb["seat"] = nb["role_src"] = None
                    nb["tile"] = None
                c[f"override_flip_{b['cls']}"] += 1
                if o.get("rect") is None:
                    boxes.append(nb)
                    continue
            rc = o["rect"]
            nb["rect"] = [[float(rc[0][0]), float(rc[0][1])], [float(rc[1][0]), float(rc[1][1])], float(rc[2])]
            nb["pts"] = rect_pts(nb["rect"])
            nb["box"] = box_of(nb["pts"], W, H)
            c[f"override_move_{b['cls']}"] += 1
        elif v and v["verdict"] == "occluded":
            c[f"dropped_occluded_{b['cls']}"] += 1
            continue
        boxes.append(nb)
    for sid in ovb:
        assert any(str(b["id"]) == sid for b in F["boxes"]), (F["id"], sid)
    for a in ((ov or {}).get("adds") or []) if use_overrides else []:
        assert a["aid"].startswith("p") and all(str(b["id"]) != a["aid"] for b in boxes), (F["id"], a["aid"])
        rc = a["rect"]
        rect = [[float(rc[0][0]), float(rc[0][1])], [float(rc[1][0]), float(rc[1][1])], float(rc[2])]
        pts = rect_pts(rect)
        face = a["cls"] == "face"
        assert not face or a.get("role"), (F["id"], a["aid"], "앞면은 역할")
        boxes.append({"id": a["aid"], "cls": a["cls"], "src": "add_pair", "tile": None, "role": a.get("role") if face else None,
                      "seat": a.get("seat") if face else None, "role_src": "review" if face else None, "edit": "add",
                      "rect": rect, "pts": pts, "box": box_of(pts, W, H), "pair_review": None, "box_diff_pairs": None,
                      "pair_fix": {"op": "add", "note": a.get("note", ""), "fit": a.get("fit")}})
        c[f"override_add_{a['cls']}"] += 1
    faces = [b for b in boxes if b["cls"] == "face"]
    n_river = sum(1 for b in faces if b["role"] == "river")
    dv = F["device"]
    felt = dict(F["felt"])
    if felt.get("quad"):
        felt["quad"] = [[round(x * 0.5, 1), round(y * 0.5, 1)] for x, y in felt["quad"]]
    im = {"id": F["id"], "part": "pair", "src_id": F["id"], "name": F["name"], "kind": F["kind"], "format": F["format"], "at": F["at"],
          "rec_ms": pe["rec_ms"], "rec_file": pe["rec_file"], "rec_dir": pe["rec_dir"], "dt_ms": pe.get("dt_ms"),
          "split_final": F["split_final"], "scene_round": F["scene_round"], "scene": F.get("scene"),
          "path": f"images/rec1496/{pe['folder']}/{pe['name']}", "size": [W, H],
          "felt": felt, "device": {k: (round(v * 0.5, 1) if k in ("cx", "cy", "hd") else v) for k, v in dv.items()}, "grid_est": F["grid_est"],
          "winner": F["winner"], "winner_src": F["winner_src"], "flags": F["flags"], "phase": F["phase"],
          "pre_game": F["phase"] == "play" and n_river == 0, "pre_game_info": F["phase"] == "play" and n_river == 0, "between": False, "n_river": n_river,
          "det_use": F["det_use"], "role_use": F["role_use"], "excluded_why": list(F["excluded_why"]),
          "review_notes": F.get("review_notes", ""), "pair_override": (ov or {}).get("reason") if use_overrides else None,
          "boxes": boxes}
    return im, c


def build(use_overrides=True, only: str | None = None) -> tuple[dict, Counter, list]:
    pairs = jload(PR / "pairs.json")["pairs"]
    F = old_finals()
    vd = verdicts()
    ov = overrides()
    assert set(ov) <= {p["id"] for p in pairs if p["status"] == "paired"}, set(ov)
    by_round, cnt, norec = {}, Counter(), []
    for pe in pairs:
        if only and pe["id"] != only:
            continue
        if pe["status"] != "paired":
            norec.append({"id": pe["id"], "status": pe["status"], "split_final": pe["split_final"]})
            continue
        im, c = pair_image(pe, F[pe["id"]], vd, ov.get(pe["id"]), use_overrides)
        cnt.update({k: v for k, v in c.items() if k != "pts_check_max_x100"})
        cnt["pts_check_max_x100"] = max(cnt["pts_check_max_x100"], c["pts_check_max_x100"])
        by_round.setdefault(pe["round"], []).append(im)
    return by_round, cnt, norec


def main():
    by_round, cnt, norec = build()
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("r*.json"):
        old.unlink()
    summ = Counter()
    for rid, ims in sorted(by_round.items()):
        ims.sort(key=lambda x: x["at"])
        jsave(OUT / f"{rid}.json", {"round": rid, "part": "pair",
                                     "_note": "짝(pair) 최종 라벨(v1114rec_dr_final_pair.py). 좌표 = 녹화 1496 원래 픽셀. 기존 data/v1114/dr/final 라벨 ×0.5 "
                                              "− 짝 눈 확인 occluded 상자 + pair/overrides.json 고침(drop·move·flip·adds). 상자 칸은 기존 final 과 같고 pair_review·pair_fix·box_diff_pairs 를 더함.",
                                     "images": ims}, indent=0)
        for im in ims:
            summ["images"] += 1
            summ[f"{im['split_final']}_images"] += 1
            summ[f"phase_{im['phase']}"] += 1
            summ["det_use"] += im["det_use"]
            summ["role_use"] += im["role_use"]
            summ["pre_game"] += im["pre_game"]
            summ["pre_game_role_use"] += im["pre_game"] and im["role_use"]
            for b in im["boxes"]:
                summ[f"box_{b['cls']}"] += 1
    s = {**dict(summ), **{f"review_{k}" if not k.startswith(("review_", "override_", "dropped_", "pts_")) else k: v for k, v in cnt.items()},
         "no_rec": norec,
         "_note": "pts_check_max_x100 = pairs.json pts_1496 과 여기서 ×0.5 한 pts 의 최대 차(×100 px). review_* = 판정 칸 수(occluded 는 상자를 뺌), "
                  "dropped_occluded_* = 뺀 상자, override_* = overrides.json 적용 수."}
    jsave(OUT / "_summary.json", s)
    print(s)


if __name__ == "__main__":
    main()
