"""11-14 헤드 녹화 프레임(rec1496) 상자별 라벨 + 패 종류 분류기 크롭 세트(2026-11-15, 녹화 세트 3단계). v1114_crops.py 와 같은 꼴·같은 규칙.

그림 세 갈래(part, 좌표는 모두 녹화 원래 픽셀 1496):
  pair = 기존 v1114 189장과 같은 순간의 녹화 프레임(pair/pairs.json, 186장 — no_rec 3장은 짝 없음).
  mid  = 기존 판 안 새 순간(49장), new = 녹화만 있는 판 n01~n08(72장). manifest.json.

라벨(사용자·계획 세션이 정함 — 자료와 안 맞으면 바꾸지 말고 보고):
  mid·new: 실물 패 verdict = review/<판>.json(v1114_crops.py 와 같은 규칙).
    ok    → 라벨 = 실물 패 초안. 그 상자 자체의 읽기(t)가 초안과 같을 때만, 다르면 "다시 볼 것"(ok_read_differs).
    fix   → 라벨 = 고친 종류. 그 상자 읽기가 실물 패 초안(틀린 쪽)과 같을 때만, 다르면 "다시 볼 것"(fix_read_differs).
    mixed → per_image 의 그림별 종류(not_tile 은 뺌). per_image 에 없는 그림의 상자는 "다시 볼 것"(mixed_no_per_image).
    not_tile·unsure → 뺌.
    note·image_notes 에 특정 그림의 가림이 적힌 상자 → "다시 볼 것"(note_occluded). 그림을 못 밝힌 가림 메모는 그 트랙 상자 전부(note_occluded_no_image).
      녹화 그림 이름은 mid_/new_<ms> 라 메모는 ms 끝 몇 자리(예: 987921)로 그림을 가리킨다 → 4자리 이상 숫자가 그림 이름 숫자의 끝과 같으면 그 그림.
    검출·역할 눈 확인 dr/review/<판>.json(상자 번호 = draft boxes[].i):
      drop, flip(앞면 → 뒷면) → 패 아님, 뺌. refit → 고친 rect 로 자름(refit_shape_changed 면 다시 볼 것 — 세운 꼴이 가로·세로 바뀜).
      두 눈 확인이 어긋나면(패 종류 쪽은 패라는데 검출 쪽 drop/flip, 또는 패 종류 쪽 not_tile 인데 검출 쪽 앞면 그대로) crops/conflicts.json, 크롭에서는 뺌.
      검출 쪽 앞면 adds(와 뒷면 → 앞면 flip)는 실물 패가 없어 라벨 없음 → crops/no_tile_adds.json 목록만.
      그림 단위 표시(flags: occluded·blur·between)는 규칙에 없어 빼지 않고 칸 img_flags 에만 남김.
  pair: 기존 data/v1114/crops/index.json 의 상자를 그 라벨·그 rot 그대로(rect × 0.5 — pairs.json 의 pts_1496 과 중심 0.1px 안에서 짝지음).
    기존 세트에서 빠진 상자는 여기서도 없음. 짝 녹화가 없는 그림(no_rec)의 상자는 뺌.
    pair/review/answers_NN.json + _key.json 에서 occluded 인 상자는 뺌. moved 는 앞면이면 빼고 보고(different·unsure 앞면은 "다시 볼 것").
크롭: 녹화 프레임에서 회전 상자를 서버 obb.upright(같은 PAD)로 세워 자르고 rot(90°×rot 반시계)로 돌림. 키우지 않음. JPEG 95.
  crops/rec1496/<split>/<종류>/<판>__<그림 이름>__<상자 번호>.jpg — pair 의 상자 번호는 기존 크롭과 같은 번호(파일 이름이 기존 크롭과 같음),
  mid·new 는 draft boxes[].i(= dr/draft 상자 번호). split = pair 는 split_final, mid·new 는 manifest split.
목록: crops/index.json(크롭마다 — 기존 칸 + part·draft_src·box_id·v1114_*·img_flags·sharp_rec), crops/rec1496/{train,dev}.json
  (harvest_obb index 꼴, 기존 v1114 와 같은 칸. 칸 part = split(기존과 같음), rec_part = pair|mid|new),
  {train,dev}_u1.json(실물 패 unit 당 한 장 = 녹화 크롭 Laplacian 분산 최대, 같으면 id 순 — pair 는 기존 unit, mid·new 는 rec#판#tid#scene_round#라벨),
  crops/review_todo.json, crops/conflicts.json, crops/no_tile_adds.json, crops/summary.json.
검토 반영(2026-11-15, E2 — 검출·역할 최종 라벨과 가린 독립 검토가 끝난 뒤):
  ① 최종 검출 라벨(dr/final = mid·new, dr/final_pair = pair, v1114rec_dr_common.final_all)과 맞춘다 — 크롭은 최종 라벨에서 앞면(cls face)으로
     남은 상자만 내고, 상자 좌표(rect·box)는 최종 라벨 것을 쓴다. 최종 라벨에서 지워졌거나(final_dropped) 뒷면으로 바뀐(final_back) 상자는 빼고
     crops/final_removed.json 에 사유와 함께(dr/conflicts_resolved.json 에 있으면 그 판정도). 회전 꼴(세운 꼴 가로·세로)이 바뀐 상자는 rot 이 안 맞아 뺀다(final_shape_changed).
  ② 두 눈 확인 어긋남(crops/conflicts.json)은 규칙 그대로 크롭에서 뺀다(패 종류 not_tile 이거나 검출 쪽이 지운 상자). 칸 resolved = conflicts_resolved 판정.
  ③ 가린 독립 검토 결정 blind/decisions.json: D·T·P 의 decision drop 크롭은 뺀다(blind_drop). R(다시 볼 것) 중 include 칸은 (그림, 상자 번호)로 찾아
     그 라벨로 넣는다(src blind_R). exclude 칸은 다시 볼 것 그대로(크롭 밖).
  ④ crops/no_tile_adds.json = 최종 라벨에서 새로 더해진 앞면(mid·new 의 src add, 뒷면→앞면 flip, pair 의 src add_pair = pN) 중 패 종류 라벨이 없는 것.
     crops/final_uncovered.json = 최종 앞면인데 크롭이 없는 상자 전부와 사유(대조용).
  ⑤ 끝에 크롭 ↔ 최종 앞면 상자 대조: 크롭마다 같은 그림의 최종 앞면 상자 중 중심이 가장 가까운 것이 같은 id 이고 rect 가 같은지, 한 상자에 크롭 둘이 없는지.
  python -X utf8 experiments/tile_classifier/v1114rec_crops.py
"""
from __future__ import annotations

import json
import re
import shutil
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, r"C:\Users\jjh7757\dev\mahjong-recognizer")
from app import local_read as lr  # noqa: E402

sys.path.insert(0, str(HERE))
from v1114_crops import cut, OCC, TID_TOK  # noqa: E402
from v1114rec_dr_common import final_all  # noqa: E402

R = HERE / "data" / "v1114rec"
OLD = HERE / "data" / "v1114"
CROPS = R / "crops"
Q = "rec1496"
CLASSES = lr.CLASSES
NUM_TOK = re.compile(r"(?<!\d)(\d{4,})(?!\d)")
JPEG_Q = 95
FEW = 5
SPLITS = ("train", "dev")
# 검토 반영 전(2026-11-15 크롭 단계 끝, crops/summary.json by_part_split) — 전·후 대조용
BEFORE = {"pair": {"train": [5703, 2014], "dev": [1938, 714]}, "mid": {"train": [1000, 733], "dev": [505, 304]},
          "new": {"train": [1781, 444], "dev": [822, 180]}, "all": {"train": [8484, 3191], "dev": [3265, 1198]}}


def blind_decisions() -> tuple[dict, dict, list]:
    """blind/decisions.json → (R include: (그림, 상자 번호) → 라벨, D·T·P drop: 크롭 id → 칸, 전체 칸)"""
    p = R / "blind" / "decisions.json"
    if not p.exists():
        return {}, {}, []
    cells = jl(p)["cells"]
    keep = {(c["image"], c["box_i"]): c["label"] for c in cells if c["bundle"] == "R" and c["decision"] == "include"}
    drop = {c["crop_id"]: c for c in cells if c["bundle"] != "R" and c["decision"] == "drop"}
    return keep, drop, cells




def jl(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


BLIND_KEEP, BLIND_DROP, BLIND_CELLS = blind_decisions()


def occluded(d: dict, rv: dict) -> tuple[dict, list]:
    """v1114_crops.occluded 와 같음. 그림을 가리키는 수 = 그림 이름 숫자의 끝 4자리 이상(녹화 이름 mid_/new_<ms>)."""
    out, log = {}, []
    apps = {t["tid"]: [a["image"] for a in t["apps"]] for t in d["tracks"]}
    digits = {im["id"]: re.sub(r"\D", "", Path(im["name"]).stem) for im in d["images"]}
    for t in rv["tracks"]:
        note = t.get("note") or ""
        if not OCC.search(note):
            continue
        hit = False
        for clause in re.split(r"[.,;]\s+|\.\s*$", note):
            if not OCC.search(clause):
                continue
            for tok in NUM_TOK.findall(clause):
                for img in apps[t["tid"]]:
                    if digits[img].endswith(tok):
                        out[(t["tid"], img)] = note
                        hit = True
        if not hit:
            out[(t["tid"], None)] = note
        log.append({"tid": t["tid"], "verdict": t["verdict"], "note": note, "images": [k[1] for k in out if k[0] == t["tid"]]})
    for n in rv.get("image_notes") or []:
        if not OCC.search(n["note"]) or n["image"] not in digits:
            continue
        for tid in TID_TOK.findall(n["note"]):
            if tid in apps and n["image"] in apps[tid]:
                out.setdefault((tid, n["image"]), n["note"])
                log.append({"tid": tid, "image_note": n["image"], "note": n["note"]})
    return out, log


def portrait(rect) -> bool:
    """obb.upright 가 세운 꼴이 세로인가(같은 각도 접기)."""
    (_, _), (w, h), a = rect
    a2 = ((a + 45) % 90) - 45
    if round((a - a2) / 90) % 2:
        w, h = h, w
    return h >= w


def sharp_of(im: Image.Image) -> float:
    g = cv2.cvtColor(np.asarray(im.convert("RGB")), cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


def mid_new_rows(man):
    """mid·new 상자별 라벨. → rows(크롭할 것), todo, conflicts, no_tile_adds, 셈."""
    items = {it["id"]: it for it in man["items"]}
    rows, todo, conflicts, adds = [], [], [], []
    dropped, dropped_tracks, verdicts = Counter(), Counter(), Counter()
    occ_log, bad_keys, dr_ops = [], [], Counter()
    for r in man["rounds"]:
        rid, part = r["id"], r["part"]
        d = jl(R / "draft" / f"{rid}.json")
        rv = jl(R / "review" / f"{rid}.json")
        drd = jl(R / "dr" / "draft" / f"{rid}.json")
        drv = jl(R / "dr" / "review" / f"{rid}.json")
        imgs = {im["id"]: im for im in d["images"]}
        dr_imgs = {im["id"]: im for im in drd["images"]}
        rvt = {t["tid"]: t for t in rv["tracks"]}
        assert set(rvt) == {t["tid"] for t in d["tracks"]}, rid
        assert set(drv["images"]) == set(imgs), rid
        occ, lg = occluded(d, rv)
        occ_log += [{"round": rid, **x} for x in lg]
        # 검출 쪽: 앞면 adds·뒷면→앞면 flip 목록
        for iid, e in drv["images"].items():
            dbx = {b["id"]: b for b in dr_imgs[iid]["boxes"]}
            for k, ed in e["box_edits"].items():
                dr_ops[(ed["op"], dbx[int(k)]["cls"])] += 1
                if ed["op"] == "flip" and dbx[int(k)]["cls"] == "back":
                    adds.append({"round": rid, "image": iid, "kind": "flip_back_to_face", "box_id": int(k), "rect": dbx[int(k)]["rect"],
                                 "note": ed.get("note") or "", "split": items[iid]["split"]})
            for a in e["adds"]:
                dr_ops[("add", a["cls"])] += 1
                if a["cls"] == "face":
                    adds.append({"round": rid, "image": iid, "kind": "add_face", "aid": a["aid"], "rect": a["rect"], "box": a["box"],
                                 "role": a.get("role"), "seat": a.get("seat"), "note": a.get("note") or "", "split": items[iid]["split"]})
        for t in d["tracks"]:
            v = rvt[t["tid"]]
            vd = v["verdict"]
            verdicts[vd] += 1
            if vd in ("not_tile", "unsure"):
                dropped_tracks[vd] += 1
            pi = v.get("per_image") or {}
            if vd == "mixed":
                apps = {a["image"] for a in t["apps"]}
                bad_keys += [{"round": rid, "tid": t["tid"], "key": k} for k in pi if k not in apps]
            for a in t["apps"]:
                b = imgs[a["image"]]["boxes"][a["i"]]
                assert b["i"] == a["i"], (rid, a)
                it = items[a["image"]]
                e = drv["images"][a["image"]]
                ed = e["box_edits"].get(str(b["i"]))
                dbox = {x["id"]: x for x in dr_imgs[a["image"]]["boxes"]}[b["i"]]
                assert dbox["cls"] == "face" and dbox["rect"] == b["rect"], (rid, a)
                op = ed["op"] if ed else None
                det_not_tile = op in ("drop", "flip")
                base = {"part": part, "round": rid, "tid": t["tid"], "image": a["image"], "i": a["i"], "box_id": b["i"], "read": b["t"], "read_c": b["c"],
                        "track_draft": t["draft"], "draft_src": t.get("draft_src"), "verdict": vd, "note": v.get("note") or "",
                        "split": it["split"], "scene_round": it["scene_round"], "scene": it["scene_round"],
                        "dr_op": op, "dr_note": (ed or {}).get("note") or "", "img_flags": e.get("flags") or [], "img_phase": e.get("phase")}
                # 패 종류 쪽 판단: 패(True) / 패 아님(False) / 모름(None)
                if vd in ("ok", "fix"):
                    tile_says = True
                elif vd == "mixed":
                    tile_says = pi.get(a["image"]) != "not_tile"
                elif vd == "not_tile":
                    tile_says = False
                else:
                    tile_says = None
                if tile_says is True and det_not_tile:
                    conflicts.append({**base, "kind": f"tile_says_tile_det_{op}", "per_image": pi.get(a["image"]) if vd == "mixed" else None,
                                      "fix_tile": v.get("tile") if vd == "fix" else None})
                    dropped[f"conflict_det_{op}"] += 1
                    continue
                if tile_says is False and not det_not_tile:
                    conflicts.append({**base, "kind": "tile_not_tile_det_keeps_face", "per_image": pi.get(a["image"]) if vd == "mixed" else None})
                    dropped["conflict_" + ("not_tile" if vd == "not_tile" else "mixed_not_tile")] += 1
                    continue
                if vd in ("not_tile", "unsure"):
                    dropped[vd + (f"+det_{op}" if det_not_tile else "")] += 1
                    continue
                if tile_says is False:  # mixed 의 per_image not_tile 이고 검출 쪽도 지움(두 쪽이 같은 판정)
                    dropped[f"mixed_not_tile+det_{op}"] += 1
                    continue
                if det_not_tile:  # unsure 는 위에서 빠짐 — 여기 오는 건 없어야 함
                    raise AssertionError((rid, t["tid"], vd, op))
                label, why = None, None
                if vd == "ok":
                    label, why = (t["draft"], None) if b["t"] == t["draft"] else (None, "ok_read_differs")
                elif vd == "fix":
                    label, why = (v["tile"], None) if b["t"] == t["draft"] else (None, "fix_read_differs")
                elif vd == "mixed":
                    pv = pi.get(a["image"])
                    if pv is None:
                        why = "mixed_no_per_image"
                    else:
                        label = pv
                else:
                    raise ValueError((rid, t["tid"], vd))
                if label is not None:
                    assert label in CLASSES, (rid, t["tid"], label)
                    on = occ.get((t["tid"], a["image"])) or occ.get((t["tid"], None))
                    if on is not None:
                        why = "note_occluded" if (t["tid"], a["image"]) in occ else "note_occluded_no_image"
                        base["label_if_kept"] = label
                        label = None
                rect, refit = b["rect"], False
                if op == "refit":
                    rect, refit = ed["rect"], True
                    if b["rect"] is not None and portrait(b["rect"]) != portrait(rect) and label is not None:
                        why, base["label_if_kept"], label = "refit_shape_changed", label, None
                if label is None and (a["image"], a["i"]) in BLIND_KEEP:
                    label, base["blind_r"] = BLIND_KEEP[(a["image"], a["i"])], why
                    vd_src = "blind_R"
                else:
                    vd_src = vd
                if label is None:
                    todo.append({**base, "why": why, "per_image": pi.get(a["image"]) if vd == "mixed" else None,
                                 "fix_tile": v.get("tile") if vd == "fix" else None, "rot": b["rot"], "rect": rect, "box": b["box"]})
                    continue
                stem = Path(imgs[a["image"]]["name"]).stem
                rows.append({**base, "id": f"{rid}__{stem}__{a['i']:03d}", "tile": label, "src": vd_src, "name": stem, "kind": imgs[a["image"]].get("kind", "frame"),
                             "rot": b["rot"], "turn": 90 * b["rot"], "conf": b["c"], "det": b.get("det"), "sharp": b.get("sharp"), "track_conf": t["conf"],
                             "prev": bool(imgs[a["image"]].get("prev_round_scene")), "track_prev": bool(t.get("prev_round_scene")),
                             "best": t["best"]["image"] == a["image"] and t["best"]["i"] == a["i"],
                             "unit": f"rec#{rid}#{t['tid']}#{it['scene_round']}#{label}", "own_unit": False,
                             "box": b["box"], "rect": rect, "refit": refit, "image_path": it["path"],
                             "v1114_crop_id": None, "v1114_unit": None, "v1114_file": None})
    stats = {"verdict_tracks": dict(verdicts), "dropped_tracks": dict(dropped_tracks), "dropped_boxes": dict(dropped),
             "dr_ops": {f"{a}_{b}": n for (a, b), n in sorted(dr_ops.items())}, "occlusion_notes": occ_log, "per_image_keys_unmatched": bad_keys}
    return rows, todo, conflicts, adds, stats


def pair_rows():
    pairs = {p["id"]: p for p in jl(R / "pair" / "pairs.json")["pairs"]}
    old = jl(OLD / "crops" / "index.json")
    key = jl(R / "pair" / "review" / "_key.json")["sheets"]
    rev = {}
    for s, cells in key.items():
        ans = jl(R / "pair" / "review" / f"answers_{s}.json")["cells"]
        for no, k in cells.items():
            a = ans.get(no) or {}
            rev[(k["id"], k["box_id"])] = {"verdict": a.get("verdict"), "note": a.get("note") or "", "sheet": s, "cell": no, "box_diff": k["box_diff"]}
    rows, todo, dropped, removed = [], [], Counter(), []
    match_d = []
    for x in old:
        p = pairs[x["image"]]
        if p["status"] != "paired":
            dropped["pair_no_rec"] += 1
            continue
        (rx, ry), (w, h), ang = x["rect"]
        rect = [[rx * 0.5, ry * 0.5], [w * 0.5, h * 0.5], ang]
        best = min(((float(np.hypot(*(np.mean(b["pts_1496"], axis=0) - (rx * 0.5, ry * 0.5)))), b) for b in p["boxes"] if b.get("pts_1496")),
                   key=lambda z: z[0])
        dd, pb = best
        match_d.append(dd)
        assert dd < 1.0 and pb["cls"] == "face", (x["id"], dd, pb)
        rv = rev.get((x["image"], pb["box_id"]))
        base = {"part": "pair", "round": x["round"], "tid": x["tid"], "image": x["image"], "i": x["i"], "box_id": pb["box_id"], "read": x["read"],
                "read_c": x["read_c"], "track_draft": x["track_draft"], "draft_src": "v1114", "verdict": x["verdict"], "note": x["note"],
                "split": p["split_final"], "scene_round": p["scene_round"], "scene": x["scene"], "box_diff": pb.get("box_diff"),
                "pair_review": rv, "v1114_crop_id": x["id"], "v1114_unit": x["unit"], "v1114_file": x["paths"]["q2992"].split("crops/q2992/", 1)[1]}
        assert x["split"] == p["split_final"] and x["scene_round"] == p["scene_round"], x["id"]
        if rv is not None and rv["verdict"] != "same":
            vd = rv["verdict"]
            if vd in ("occluded", "moved"):
                dropped[f"pair_{vd}"] += 1
                removed.append({**base, "tile": x["tile"], "why": f"pair_{vd}"})
                continue
            todo.append({**base, "why": f"pair_{vd}", "label_if_kept": x["tile"], "rot": x["rot"], "rect": rect, "box": [round(v * 0.5) for v in x["box"]]})
            continue
        rows.append({**base, "id": x["id"], "tile": x["tile"], "src": x["src"], "name": x["name"], "kind": x["kind"], "rot": x["rot"], "turn": x["turn"],
                     "conf": x["conf"], "det": x["det"], "sharp": x["sharp"], "track_conf": x["track_conf"], "prev": x["prev"], "track_prev": x["track_prev"],
                     "best": x["best"], "unit": x["unit"], "own_unit": x["own_unit"], "box": [round(v * 0.5) for v in x["box"]], "rect": rect, "refit": False,
                     "image_path": f"images/{Q}/{p['folder']}/{p['name']}", "dr_op": None, "dr_note": "", "img_flags": [], "img_phase": None})
    pr_counts = Counter(v["verdict"] for v in rev.values())
    return rows, todo, removed, dict(dropped), {"pair_review_cells": len(rev), "pair_review_verdicts": dict(pr_counts),
                                                "old_crops": len(old), "match_dist_max": max(match_d) if match_d else None}


def final_faces() -> tuple[dict, dict]:
    """최종 검출 라벨 → ((그림 id, 상자 id 문자열) → (상자, 그림)), 그림 id → 앞면 상자들."""
    by, faces = {}, defaultdict(list)
    for im in final_all():
        for b in im["boxes"]:
            by[(im["id"], str(b["id"]))] = (b, im)
            if b["cls"] == "face":
                faces[im["id"]].append(b)
    return by, faces


def final_reflect(rows: list, F: dict) -> tuple[list, list, Counter]:
    """최종 라벨에서 앞면으로 남은 상자만, 좌표는 최종 것으로. 독립 검토 drop 도 여기서 뺀다."""
    cr = {(x["image"], str(x["box_id"])): x for x in jl(R / "dr" / "conflicts_resolved.json")["items"]}
    keep, removed, c = [], [], Counter()
    for x in rows:
        k = (x["image"], str(x["box_id"]))
        fb = F.get(k)
        why = None
        if fb is None:
            why = "final_dropped"
        elif fb[0]["cls"] != "face":
            why = "final_back"
        elif x["rect"] is not None and portrait(x["rect"]) != portrait(fb[0]["rect"]):
            why = "final_shape_changed"
        if x["id"] in BLIND_DROP:
            why = (why + "+" if why else "") + "blind_drop"
        if why:
            c[f"{x['part']}_{why}"] += 1
            r = cr.get(k)
            bd = BLIND_DROP.get(x["id"])
            removed.append({"id": x["id"], "part": x["part"], "split": x["split"], "round": x["round"], "image": x["image"], "box_id": x["box_id"],
                            "tid": x["tid"], "tile": x["tile"], "why": why, "rect": x["rect"],
                            "conflict_resolved": {kk: r[kk] for kk in ("verdict", "det_after", "why")} if r else None,
                            "blind": {kk: bd[kk] for kk in ("bundle", "cell", "blind_read", "why")} if bd else None,
                            "final_edit": fb[0].get("edit") if fb else None})
            continue
        b = fb[0]
        moved = float(np.abs(np.array(b["rect"][0]) - np.array(x["rect"][0])).max()) if x["rect"] is not None else None
        if moved is None or moved > 0.06 or abs(b["rect"][2] - x["rect"][2]) > 0.06:
            c[f"{x['part']}_rect_from_final_changed"] += 1
        x["rect"], x["box"] = b["rect"], list(b["box"])
        keep.append(x)
    return keep, removed, c


def final_adds_uncovered(rows, todo, conflicts, premoved, F, faces, man) -> tuple[list, list]:
    """④ 새로 더한 앞면 중 라벨 없는 것 + 최종 앞면인데 크롭 없는 상자 전부(사유)."""
    have = {(x["image"], str(x["box_id"])) for x in rows}
    todo_w = {(x["image"], str(x["box_id"])): x["why"] for x in todo}
    conf_w = {(x["image"], str(x["box_id"])): x["kind"] for x in conflicts}
    prem = {(x["image"], str(x["box_id"])): x["why"] for x in premoved}
    trk = {}
    for r in man["rounds"]:
        d = jl(R / "draft" / f"{r['id']}.json")
        rv = {t["tid"]: t for t in jl(R / "review" / f"{r['id']}.json")["tracks"]}
        for t in d["tracks"]:
            v = rv[t["tid"]]
            for a in t["apps"]:
                pv = (v.get("per_image") or {}).get(a["image"]) if v["verdict"] == "mixed" else None
                trk[(a["image"], str(a["i"]))] = (t["tid"], v["verdict"] + (f":{pv}" if pv else ""))
    adds, unc = [], []
    for iid, bs in faces.items():
        im = F[(iid, str(bs[0]["id"]))][1]
        for b in bs:
            k = (iid, str(b["id"]))
            if k in have:
                continue
            is_add = b["src"] in ("add", "add_pair") and (im["part"] != "pair" or b["src"] == "add_pair")
            is_flip = b.get("edit") == "flip" or ((b.get("pair_fix") or {}).get("op") == "flip")
            ent = {"part": im["part"], "image": iid, "split": im["split_final"], "box_id": b["id"], "src": b["src"], "edit": b.get("edit"),
                   "role": b.get("role"), "seat": b.get("seat"), "tile": b.get("tile"), "rect": b["rect"], "det_use": im["det_use"], "role_use": im["role_use"]}
            if (is_add or is_flip) and not b.get("tile"):
                adds.append({**ent, "kind": "add_face" if is_add else "flip_back_to_face",
                             "note": ((b.get("pair_fix") or {}).get("note") or "")})
            if k in todo_w:
                why = "review_todo:" + todo_w[k]
            elif k in conf_w:
                why = "conflict:" + conf_w[k]
            elif k in prem:
                why = "pair_removed:" + prem[k]
            elif is_add or is_flip:
                why = "added_no_tile_label"
            elif im["part"] == "pair":
                why = "not_in_v1114_crops(" + ("tile null" if not b.get("tile") else "v1114 크롭 목록에 없음") + f", src {b['src']}, edit {b.get('edit')})"
            elif k in trk:
                why = "tile_review:" + trk[k][1]
            else:
                why = "no_tile_track"
            unc.append({**ent, "why": why, "tid": trk.get(k, (None,))[0]})
    return adds, unc


def final_match_check(rows, faces) -> dict:
    """⑤ 크롭 ↔ 최종 앞면 상자(좌표로): 같은 그림의 최종 앞면 중 중심이 가장 가까운 상자가 같은 id·같은 rect 인가, 한 상자에 크롭 하나인가."""
    c = Counter()
    seen = Counter()
    bad = []
    for x in rows:
        bs = faces.get(x["image"], [])
        cx, cy = x["rect"][0]
        d, b = min(((float(np.hypot(b["rect"][0][0] - cx, b["rect"][0][1] - cy)), b) for b in bs), key=lambda z: z[0])
        same_rect = d < 1e-6 and list(b["rect"][1]) == list(x["rect"][1]) and b["rect"][2] == x["rect"][2]
        ok = str(b["id"]) == str(x["box_id"]) and same_rect and b["cls"] == "face"
        c["ok" if ok else "bad"] += 1
        seen[(x["image"], str(b["id"]))] += 1
        if not ok:
            bad.append({"id": x["id"], "nearest": b["id"], "d": d})
    dup = [k for k, n in seen.items() if n > 1]
    return {"crops": len(rows), "match_same_id_same_rect": c["ok"], "mismatch": c["bad"], "mismatch_list": bad[:50],
            "final_boxes_with_2plus_crops": len(dup), "dup_list": [list(k) for k in dup[:50]],
            "final_face_boxes_total": sum(len(v) for v in faces.values()), "final_face_boxes_with_crop": len(seen)}


def pct(vals, ps=(10, 50, 90)):
    return [float(np.percentile(vals, p)) for p in ps] if vals else None


def main():
    man = jl(R / "manifest.json")
    mrows, mtodo, conflicts, adds, mstats = mid_new_rows(man)
    prows, ptodo, premoved, pdropped, pstats = pair_rows()
    rows = prows + mrows
    todo = ptodo + mtodo
    F, faces = final_faces()
    n_pre = len(rows)
    rows, final_removed, fstats = final_reflect(rows, F)
    adds, uncovered = final_adds_uncovered(rows, todo, conflicts, premoved, F, faces, man)
    cr = {(x["image"], str(x["box_id"])): x for x in jl(R / "dr" / "conflicts_resolved.json")["items"]}
    for x in conflicts:
        r = cr.get((x["image"], str(x["box_id"])))
        x["resolved"] = {kk: r[kk] for kk in ("verdict", "det_after", "why")} if r else None
    # 패 종류 쪽은 패라는데 최종 검출 라벨이 지운·뒤집은 상자(크롭 규칙상 conflicts 로 이미 빠짐)도 final_removed 목록에 함께 적는다
    for x in conflicts:
        if x["kind"].startswith("tile_says_tile_det_"):
            fb = F.get((x["image"], str(x["box_id"])))
            fw = "final_dropped" if fb is None else ("final_back" if fb[0]["cls"] != "face" else "final_face")
            bd = next((c for c in BLIND_CELLS if c["bundle"] != "R" and c["image"] == x["image"] and c["box_i"] == x["i"]), None)
            final_removed.append({"id": f"{x['round']}__{x['image'].split('/', 1)[1]}__{x['i']:03d}", "part": x["part"], "split": x["split"],
                                  "round": x["round"], "image": x["image"], "box_id": x["box_id"], "tid": x["tid"],
                                  "tile": x.get("fix_tile") or x.get("per_image") or x["track_draft"], "why": f"conflict({x['kind']})+{fw}",
                                  "rect": None, "conflict_resolved": x["resolved"],
                                  "blind": {kk: bd[kk] for kk in ("bundle", "cell", "blind_read", "decision", "why")} if bd else None,
                                  "final_edit": fb[0].get("edit") if fb else None})
            fstats[f"{x['part']}_conflict_{fw}"] += 1
    cr_status = []
    for k, r in cr.items():
        cr_status.append({"image": k[0], "box_id": r["box_id"], "tid": r["tid"], "verdict": r["verdict"], "det_after": r["det_after"],
                          "tile_side": r["tile_side"]["verdict"], "in_crops": any(x["image"] == k[0] and str(x["box_id"]) == k[1] for x in rows),
                          "in_conflicts_now": any((x["image"], str(x["box_id"])) == k for x in conflicts)})
    ids = [x["id"] for x in rows]
    assert len(ids) == len(set(ids))

    if CROPS.exists():
        shutil.rmtree(CROPS)
    by_img = defaultdict(list)
    for x in rows:
        by_img[x["image_path"]].append(x)
    for n, (path, xs) in enumerate(sorted(by_img.items())):
        rgb = np.asarray(Image.open(R / path).convert("RGB"))
        assert rgb.shape[:2] == (1496, 1496), path
        for x in xs:
            im = cut(rgb, {"rect": x["rect"], "box": x["box"], "rot": x["rot"]}, 1.0)
            rel = f"crops/{Q}/{x['split']}/{x['tile']}/{x['id']}.jpg"
            p = R / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            im.save(p, quality=JPEG_Q)
            x["paths"] = {Q: rel}
            x["size"] = {Q: [im.width, im.height]}
            x["sharp_rec"] = round(sharp_of(im), 1)
        if n % 40 == 0:
            print("크롭", n, "/", len(by_img), path, flush=True)
    keep = ["id", "part", "tile", "split", "round", "scene_round", "scene", "image", "name", "kind", "i", "box_id", "tid", "unit", "paths", "size", "conf",
            "read", "read_c", "track_draft", "track_conf", "draft_src", "src", "verdict", "note", "prev", "track_prev", "best", "own_unit", "rot", "turn",
            "det", "sharp", "sharp_rec", "box", "rect", "refit", "dr_op", "dr_note", "img_flags", "img_phase", "box_diff", "pair_review",
            "v1114_crop_id", "v1114_unit", "v1114_file", "image_path", "blind_r"]
    rows = [{k: x.get(k) for k in keep} for x in rows]
    CROPS.mkdir(parents=True, exist_ok=True)
    (CROPS / "index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8")
    for sp in SPLITS:
        lst = [{"id": x["id"], "file": x["paths"][Q].split(f"crops/{Q}/", 1)[1], "tile": x["tile"], "part": sp, "rec_part": x["part"], "photo": x["scene"],
                "scene": x["scene"], "scene_round": x["scene_round"], "round": x["round"], "tid": x["tid"], "unit": x["unit"], "src": "v1114rec_" + x["src"],
                "w": x["size"][Q][0], "h": x["size"][Q][1], "turn": x["turn"], "read": x["read"], "read_c": x["read_c"], "quality": Q,
                "v1114_crop_id": x["v1114_crop_id"]} for x in rows if x["split"] == sp]
        (CROPS / Q / f"{sp}.json").write_text(json.dumps(lst, ensure_ascii=False, indent=0), encoding="utf-8")
        sh = {x["id"]: x["sharp_rec"] for x in rows}
        pick = {}
        for e in sorted(lst, key=lambda e: (-sh[e["id"]], e["id"])):
            pick.setdefault(e["unit"], e)
        (CROPS / Q / f"{sp}_u1.json").write_text(json.dumps(sorted(pick.values(), key=lambda e: e["id"]), ensure_ascii=False, indent=0), encoding="utf-8")
    (CROPS / "review_todo.json").write_text(json.dumps(todo, ensure_ascii=False, indent=0), encoding="utf-8")
    (CROPS / "conflicts.json").write_text(json.dumps(conflicts, ensure_ascii=False, indent=0), encoding="utf-8")
    (CROPS / "no_tile_adds.json").write_text(json.dumps(adds, ensure_ascii=False, indent=0), encoding="utf-8")
    (CROPS / "pair_removed.json").write_text(json.dumps(premoved, ensure_ascii=False, indent=0), encoding="utf-8")
    (CROPS / "final_removed.json").write_text(json.dumps(final_removed, ensure_ascii=False, indent=0), encoding="utf-8")
    (CROPS / "final_uncovered.json").write_text(json.dumps(uncovered, ensure_ascii=False, indent=0), encoding="utf-8")
    mcheck = final_match_check(rows, faces)
    files = sorted(f.relative_to(CROPS / Q).as_posix() for f in (CROPS / Q).rglob("*.jpg"))
    assert len(files) == len(rows), (len(files), len(rows))

    # 요약
    sc_split = defaultdict(set)
    for x in rows:
        sc_split[x["scene_round"]].add(x["split"])
    shared = sorted(s for s, v in sc_split.items() if len(v) > 1)
    # 그림 단위(라벨 없는 그림 포함)로도 셈: manifest + pairs
    img_sc = defaultdict(set)
    for it in man["items"]:
        img_sc[it["scene_round"]].add(it["split"])
    for p in jl(R / "pair" / "pairs.json")["pairs"]:
        if p["status"] == "paired":
            img_sc[p["scene_round"]].add(p["split_final"])
    shared_img = sorted(s for s, v in img_sc.items() if len(v) > 1)
    unit_split = defaultdict(set)
    for x in rows:
        unit_split[x["unit"]].add(x["split"])
    by = {}
    for part in ("pair", "mid", "new", "all"):
        by[part] = {}
        for sp in SPLITS:
            xs = [x for x in rows if x["split"] == sp and (part == "all" or x["part"] == part)]
            ls = [max(x["size"][Q]) for x in xs]
            by[part][sp] = {"crops": len(xs), "units": len({x["unit"] for x in xs}), "images": len({x["image"] for x in xs}),
                            "rounds": len({x["round"] for x in xs}), "scene_rounds": len({x["scene_round"] for x in xs}),
                            "long_side_p10_p50_p90": pct(ls), "long_side_min_max": [min(ls), max(ls)] if ls else None}
    ls_all = [max(x["size"][Q]) for x in rows]
    hist = Counter(min(v // 10 * 10, 120) for v in ls_all)
    tiles = {}
    for c in CLASSES:
        ent = {}
        for sp in SPLITS:
            xs = [x for x in rows if x["tile"] == c and x["split"] == sp]
            ent[sp] = len(xs)
            ent[sp + "_units"] = len({x["unit"] for x in xs})
            ent[sp + "_by_part"] = dict(Counter(x["part"] for x in xs))
        ent["flags"] = [f for f, on in (("개발에 없음", not ent["dev"]), (f"학습 {FEW}장 미만", ent["train"] < FEW)) if on]
        tiles[c] = ent
    u1 = {sp: len(jl(CROPS / Q / f"{sp}_u1.json")) for sp in SPLITS}
    summ = {
        "made_by": "v1114rec_crops.py", "quality": Q,
        "by_part_split": by,
        "long_side_hist_10px": {f"{k}-{k + 9}" if k < 120 else "120+": hist[k] for k in sorted(hist)},
        "tiles": tiles,
        "tiles_missing_in_dev": [c for c, v in tiles.items() if not v["dev"]], "tiles_train_lt5": [c for c, v in tiles.items() if v["train"] < FEW],
        "mid_new": mstats,
        "pair": {**pstats, "dropped_boxes": pdropped, "removed_list": "crops/pair_removed.json",
                 "note": "기존 v1114 크롭 목록의 상자만 옮김 — 기존 세트에서 빠진 상자(not_tile·unsure·다시 볼 것 미결·덮어쓰기 drop)는 여기에도 없음. "
                         "pair 눈 확인은 box_diff > 7 인 상자만 봤음(그 밖은 same 으로 둠)."},
        "conflicts": {"n": len(conflicts), "by_kind": dict(Counter(x["kind"] for x in conflicts)), "file": "crops/conflicts.json"},
        "no_tile_adds": {"n": len(adds), "by_kind": dict(Counter(x["kind"] for x in adds)), "by_part": dict(Counter(x["part"] for x in adds)),
                         "file": "crops/no_tile_adds.json",
                         "rule": "최종 라벨에서 새로 더한 앞면(mid·new src add·뒷면→앞면 flip, pair src add_pair) 중 패 종류 라벨 없는 것 — 크롭 안 냄"},
        "reflect": {"before": BEFORE, "rows_before_final_filter": n_pre, "final_removed": len(final_removed), "final_removed_counts": dict(fstats),
                    "final_removed_file": "crops/final_removed.json",
                    "blind_decisions": "blind/decisions.json", "blind_r_included": sum(1 for x in rows if x["src"] == "blind_R"),
                    "blind_drop_ids": sorted(BLIND_DROP), "conflicts_resolved": cr_status,
                    "final_uncovered": len(uncovered), "final_uncovered_by_why": dict(Counter(x["why"].split("(")[0] for x in uncovered)),
                    "final_uncovered_file": "crops/final_uncovered.json", "match_check": mcheck},
        "review_todo_boxes": len(todo), "review_todo_by_why": dict(Counter(x["why"] for x in todo)),
        "review_todo_units": len({(x["round"], x["tid"], x["part"]) for x in todo}),
        "u1_counts": u1,
        "scene_round_shared_across_split": shared, "scene_round_shared_count": len(shared),
        "scene_round_shared_count_all_images": len(shared_img),
        "units_across_split": sorted(u for u, v in unit_split.items() if len(v) > 1),
        "img_flags_on_crops": dict(Counter("+".join(x["img_flags"]) for x in rows if x["img_flags"])),
        "limits": [
            "pair 와 mid 는 같은 판·같은 탁자라 같은 실물 패가 두 unit(기존 v1114 unit / rec#… unit)으로 들어간다 — 실물 패 수는 part 를 더하면 부풀려진다. "
            "_u1 도 part 마다 따로 한 장이라 같은 패가 두 장 들어갈 수 있다(나눔은 같은 scene_round 기준이라 학습·개발 사이로는 안 샘).",
            "pair 라벨은 2992 원본에서 단 것을 옮긴 것 — 녹화 화질에서 읽히는지는 독립 검토 P 묶음 표본으로만 본다. rot 도 2992 에서 분류기가 읽은 방향.",
            "mid·new 의 rot 은 1496 크롭 분류기 읽기 방향이라 거꾸로 선 크롭이 섞여 있다(기존 세트와 같음).",
            "검출 쪽 그림 표시(occluded·blur·between)는 규칙에 없어 상자를 빼지 않았다(칸 img_flags).",
            "new 판(n01~n08)은 태블릿 기록·정답이 없어 라벨은 눈 확인 + 가린 독립 검토(개발 D 전부, 학습 T 표본)뿐.",
            "가린 독립 검토는 mid·new 개발 unit 전부(D) + 학습 300 unit 표본(T) + pair 200장 표본(P) — 학습 나머지 크롭은 눈 확인 한 번뿐.",
            "탁자 모서리 흰 테두리 위의 백(5z) 울기는 테두리와 헷갈린다(독립 검토에서 not_tile 로 본 12칸 중 11칸은 백, 1칸은 이음매) — 5z 크롭에 테두리가 남았을 수 있다.",
            "최종 검출 라벨의 앞면 가운데 크롭이 없는 상자가 있다(crops/final_uncovered.json — 패 종류 not_tile·unsure·다시 볼 것·더한 상자 등). 검출·역할 세트의 앞면 수와 다르다.",
        ],
        "crops_total": len(rows), "folder_bytes": sum(f.stat().st_size for f in (CROPS / Q).rglob("*.jpg")),
    }
    (CROPS / "summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in summ["reflect"].items() if k != "conflicts_resolved"}, ensure_ascii=False)[:3000])
    print(json.dumps({k: summ[k] for k in ("by_part_split", "long_side_hist_10px", "tiles_missing_in_dev", "tiles_train_lt5", "conflicts", "no_tile_adds",
                                           "review_todo_boxes", "review_todo_by_why", "u1_counts", "scene_round_shared_count",
                                           "scene_round_shared_count_all_images", "units_across_split", "img_flags_on_crops", "crops_total")},
                     ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in mstats.items() if k != "occlusion_notes"}, ensure_ascii=False))
    print(json.dumps(summ["pair"], ensure_ascii=False))
    print({c: (v["train"], v["dev"], v["train_units"], v["dev_units"]) for c, v in tiles.items()})


if __name__ == "__main__":
    main()
