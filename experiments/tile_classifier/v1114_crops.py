"""11-14 자료 상자별 라벨 + 화질별 크롭 세트(2026-11-15, 3단계 B). v1114_split.py 다음에.

라벨(사용자가 정함 — 안 맞으면 바꾸지 말고 보고):
  실물 패 verdict = review/<판>.json, review/_overrides.json 이 덮어씀.
  ok    → 라벨 = 실물 패 초안. 단 그 상자 자체의 읽기(t)가 실물 패 초안과 같을 때만, 다르면 "다시 볼 것"(ok_read_differs).
  fix   → 라벨 = 고친 종류. 그 상자 읽기가 실물 패 초안(틀린 쪽)과 같을 때만, 다르면 "다시 볼 것"(fix_read_differs).
  mixed → per_image 의 그림별 종류(not_tile 은 뺌). per_image 에 없는 그림의 상자는 "다시 볼 것"(mixed_no_per_image).
  not_tile·unsure → 뺌(수만).
  2단계 note·image_notes 에 특정 그림에서 "가림/가려/가린" 이 적힌 상자가 위 규칙을 지나 라벨을 받았으면 "다시 볼 것"(note_occluded).
  그림을 안 밝힌 가림 메모(트랙 전체)는 그 트랙 상자 전부(note_occluded_no_image).
크롭: 라벨 상자마다 세 화질 그림에서 같은 회전 상자(좌표 × manifest rules.scale)를 서버 obb.upright(같은 PAD)로 세워 자르고
  초안이 읽은 방향(rot, 90°×rot 반시계)으로 돌림. 키우지 않음. JPEG 95(harvest.py --obb 와 같음).
  crops/{q2992,q1496,q997}/<split>/<종류>/<판>__<그림 이름>__<상자 번호>.jpg — split = 그림의 split_final(v1114_split.py).
목록: crops/index.json(크롭마다), crops/{q}/{train,dev}.json(harvest_obb index 꼴: file 은 crops/{q}/ 기준), crops/review_todo.json, crops/summary.json.
  crops/{q}/{train,dev}_u1.json = 실물 패(unit)당 가장 선명한 상자 한 장(draft sharp 최대) — 같은 패가 여러 그림에 겹친 것을 줄여 쓸 때.
덮어쓰기: review/_overrides.json 의 overrides(트랙 verdict)와 boxes(상자 단위 add/drop — 독립 검토 R·D 결정). add 상자는 src=recheck,
  own_unit 이면 그 상자만 따로 unit(실물 패 라벨과 섞지 않음). blind_review 는 summary.json 으로 옮긴다.
실물 패 단위(unit) = 판#tid#scene#라벨 — mixed 로 한 id 에 다른 패가 섞인 것, r20 처럼 한 판에 두 탁자인 것은 따로 센다.
  python -X utf8 experiments/tile_classifier/v1114_crops.py
"""
from __future__ import annotations

import json
import re
import shutil
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, r"C:\Users\jjh7757\dev\mahjong-recognizer")
from app import local_read as lr  # noqa: E402
from app import obb  # noqa: E402

sys.path.insert(0, str(HERE))
from v1114_split import image_rel  # noqa: E402

OUT = HERE / "data" / "v1114"
CROPS = OUT / "crops"
QS = ("q2992", "q1496", "q997")
CLASSES = lr.CLASSES
OCC = re.compile(r"가림|가려|가린")
FRAME_TOK = re.compile(r"(?<!\d)f?(\d{4})(?!\d)")
TID_TOK = re.compile(r"#(\d{3})")
JPEG_Q = 95
FEW = 5


def load_all():
    man = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    ovf = json.loads((OUT / "review" / "_overrides.json").read_text(encoding="utf-8"))
    ov = (ovf["overrides"], ovf.get("boxes", []), ovf.get("blind_review"))
    rounds = []
    for r in man["rounds"]:
        d = json.loads((OUT / "draft" / f"{r['id']}.json").read_text(encoding="utf-8"))
        rv = json.loads((OUT / "review" / f"{r['id']}.json").read_text(encoding="utf-8"))
        rounds.append((r, d, rv))
    return man, ov, rounds


def occluded(d: dict, rv: dict) -> tuple[dict, list]:
    """2단계 메모에서 가림이 적힌 (tid, 그림 id) → 메모. 그림을 못 밝힌 트랙 메모는 (tid, None)."""
    out, log = {}, []
    apps = {t["tid"]: [a["image"] for a in t["apps"]] for t in d["tracks"]}
    names = {im["id"]: im["name"] for im in d["images"]}
    for t in rv["tracks"]:
        note = t.get("note") or ""
        if not OCC.search(note):
            continue
        hit = False
        for clause in re.split(r"[.,;]\s+|\.\s*$", note):
            if not OCC.search(clause):
                continue
            for tok in FRAME_TOK.findall(clause):
                for img in apps[t["tid"]]:
                    if f"_f{tok}_" in names[img]:
                        out[(t["tid"], img)] = note
                        hit = True
        if not hit:
            out[(t["tid"], None)] = note
        log.append({"tid": t["tid"], "verdict": t["verdict"], "note": note, "images": [k[1] for k in out if k[0] == t["tid"]]})
    for n in rv.get("image_notes") or []:
        if not OCC.search(n["note"]) or n["image"] not in names:
            continue
        for tid in TID_TOK.findall(n["note"]):
            if tid in apps and n["image"] in apps[tid]:
                out.setdefault((tid, n["image"]), n["note"])
                log.append({"tid": tid, "image_note": n["image"], "note": n["note"]})
    return out, log


def cut(rgb: np.ndarray, b: dict, s: float) -> Image.Image:
    if b["rect"] is not None:
        (cx, cy), (w, h), a = b["rect"]
        im = obb.upright(rgb, ((cx * s, cy * s), (w * s, h * s), a), lr.PAD)
    else:
        x, y, w, h = (v * s for v in b["box"])
        H, W = rgb.shape[:2]
        px, py = w * lr.PAD, h * lr.PAD
        im = Image.fromarray(rgb[max(0, int(y - py)):min(H, int(y + h + py)), max(0, int(x - px)):min(W, int(x + w + px))])
    return im.rotate(90 * b["rot"], expand=True) if b["rot"] else im


def main():
    man, ov, rounds = load_all()
    scale = man["rules"]["scale"]
    items = {it["id"]: it for it in man["items"]}
    ov, box_ov, blind_review = ov
    ovmap = {(o["round"], o["tid"]): o for o in ov}
    boxmap = {(o["round"], o["tid"], o["image"], o["i"]): o for o in box_ov}
    assert len(boxmap) == len(box_ov)
    used_ov, used_box, box_log = set(), set(), []
    verdict_raw, verdict_final = Counter(), Counter()
    rows, todo, dropped = [], [], Counter()
    dropped_tracks = Counter()
    occ_log, bad_keys = [], []
    for r, d, rv in rounds:
        rid = r["id"]
        imgs = {im["id"]: im for im in d["images"]}
        rvt = {t["tid"]: t for t in rv["tracks"]}
        assert set(rvt) == {t["tid"] for t in d["tracks"]}, rid
        occ, lg = occluded(d, rv)
        occ_log += [{"round": rid, **x} for x in lg]
        for t in d["tracks"]:
            v = dict(rvt[t["tid"]])
            verdict_raw[v["verdict"]] += 1
            if (rid, t["tid"]) in ovmap:
                o = ovmap[(rid, t["tid"])]
                used_ov.add((rid, t["tid"]))
                v.update({k: o.get(k) for k in ("verdict", "tile", "per_image")})
                v["note"] = (v.get("note") or "") + f" [덮어씀: {o['by']} {o['date']} — {o['note']}]"
            verdict_final[v["verdict"]] += 1
            if v["verdict"] in ("not_tile", "unsure"):
                dropped_tracks[v["verdict"]] += 1
            pi = v.get("per_image") or {}
            if v["verdict"] == "mixed":
                apps = {a["image"] for a in t["apps"]}
                bad_keys += [{"round": rid, "tid": t["tid"], "key": k} for k in pi if k not in apps]
            for a in t["apps"]:
                b = imgs[a["image"]]["boxes"][a["i"]]
                it = items[a["image"]]
                base = {"round": rid, "tid": t["tid"], "image": a["image"], "i": a["i"], "read": b["t"], "read_c": b["c"], "track_draft": t["draft"],
                        "verdict": v["verdict"], "note": v.get("note") or "", "split": it["split_final"], "scene_round": it["scene_round"], "scene": it["scene"]}
                vd = v["verdict"]
                label, why = None, None
                if vd in ("not_tile", "unsure"):
                    dropped[vd] += 1
                    continue
                if vd == "ok":
                    label, why = (t["draft"], None) if b["t"] == t["draft"] else (None, "ok_read_differs")
                elif vd == "fix":
                    label, why = (v["tile"], None) if b["t"] == t["draft"] else (None, "fix_read_differs")
                elif vd == "mixed":
                    pv = pi.get(a["image"])
                    if pv is None:
                        why = "mixed_no_per_image"
                    elif pv == "not_tile":
                        dropped["mixed_not_tile"] += 1
                        continue
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
                bo = boxmap.get((rid, t["tid"], a["image"], a["i"]))
                if bo is not None:
                    used_box.add((rid, t["tid"], a["image"], a["i"]))
                    box_log.append({"blind": bo.get("blind"), "round": rid, "tid": t["tid"], "image": a["image"], "i": a["i"], "action": bo["action"],
                                    "tile": bo.get("tile"), "was": "todo:" + why if label is None else "label:" + label})
                    if bo["action"] == "drop":
                        dropped["box_override_drop"] += 1
                        if label is None:
                            todo.append({**base, "why": why, "decision": "dropped", "decision_note": bo["note"]})
                        continue
                    assert bo["action"] == "add" and bo["tile"] in CLASSES, bo
                    if label is None:
                        todo.append({**base, "why": why, "decision": "added", "tile": bo["tile"], "decision_note": bo["note"]})
                    label, vd = bo["tile"], "recheck"
                    base["note"] = (base["note"] + " " if base["note"] else "") + f"[상자 덮어씀: {bo['by']} {bo['date']} — {bo['note']}]"
                if label is None:
                    todo.append({**base, "why": why, "per_image": pi.get(a["image"]) if vd == "mixed" else None,
                                 "fix_tile": v.get("tile") if vd == "fix" else None})
                    continue
                stem = Path(imgs[a["image"]]["name"]).stem
                cid = f"{it['round']}__{stem}__{a['i']:03d}"
                rows.append({**base, "id": cid, "tile": label, "src": vd, "name": stem, "kind": it["kind"], "rot": b["rot"], "turn": 90 * b["rot"],
                             "conf": b["c"], "det": b.get("det"), "sharp": b.get("sharp"), "track_conf": t["conf"],
                             "prev": bool(imgs[a["image"]].get("prev_round_scene")), "track_prev": bool(t.get("prev_round_scene")),
                             "best": t["best"]["image"] == a["image"] and t["best"]["i"] == a["i"],
                             "unit": (f"{rid}#{t['tid']}+{stem}_{a['i']:03d}#{it['scene']}#{label}" if bo is not None and bo.get("own_unit")
                                      else f"{rid}#{t['tid']}#{it['scene']}#{label}"),
                             "own_unit": bool(bo is not None and bo.get("own_unit")), "box": b["box"], "rect": b["rect"]})
    missing_ov = [k for k in ovmap if k not in used_ov] + [k for k in boxmap if k not in used_box]
    assert not missing_ov, missing_ov
    open_todo = [x for x in todo if not x.get("decision")]
    ids = [x["id"] for x in rows]
    assert len(ids) == len(set(ids))

    # 크롭
    if CROPS.exists():
        shutil.rmtree(CROPS)
    by_img = defaultdict(list)
    for x in rows:
        by_img[x["image"]].append(x)
    for n, (iid, xs) in enumerate(sorted(by_img.items())):
        it = items[iid]
        for q in QS:
            rgb = np.asarray(Image.open(OUT / image_rel(it, q)).convert("RGB"))
            for x in xs:
                b = {"rect": x["rect"], "box": x["box"], "rot": x["rot"]}
                im = cut(rgb, b, scale[q])
                rel = f"crops/{q}/{x['split']}/{x['tile']}/{x['id']}.jpg"
                p = OUT / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                im.save(p, quality=JPEG_Q)
                x.setdefault("paths", {})[q] = rel
                x.setdefault("size", {})[q] = [im.width, im.height]
        if n % 20 == 0:
            print("크롭", n, "/", len(by_img), iid, flush=True)
    for x in rows:
        assert len({Path(p).name for p in x["paths"].values()}) == 1
    keep = ["id", "tile", "split", "round", "scene_round", "scene", "image", "name", "kind", "i", "tid", "unit", "paths", "size", "conf", "read",
            "read_c", "track_draft", "track_conf", "src", "verdict", "note", "prev", "track_prev", "best", "own_unit", "rot", "turn", "det", "sharp", "box", "rect"]
    rows = [{k: x[k] for k in keep} for x in rows]
    (CROPS / "index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8")
    for q in QS:
        for sp in ("train", "dev"):
            lst = [{"id": k, "file": x["paths"][q].split(f"crops/{q}/", 1)[1], "tile": x["tile"], "part": sp, "photo": x["scene"], "scene": x["scene"],
                    "scene_round": x["scene_round"], "round": x["round"], "tid": x["tid"], "unit": x["unit"], "src": "v1114_" + x["src"],
                    "w": x["size"][q][0], "h": x["size"][q][1], "turn": x["turn"], "read": x["read"], "read_c": x["read_c"], "quality": q}
                   for k, x in ((x["id"], x) for x in rows) if x["split"] == sp]
            (CROPS / q / f"{sp}.json").write_text(json.dumps(lst, ensure_ascii=False, indent=0), encoding="utf-8")
            # 실물 패(unit)당 한 장: 가장 선명한 상자(draft 2992 크롭 Laplacian 분산 sharp 최대, 같으면 id 순) — 세 화질 같은 크롭
            sh = {x["id"]: (x["sharp"] or 0.0) for x in rows}
            pick = {}
            for e in sorted(lst, key=lambda e: (-sh[e["id"]], e["id"])):
                pick.setdefault(e["unit"], e)
            u1 = sorted(pick.values(), key=lambda e: e["id"])
            (CROPS / q / f"{sp}_u1.json").write_text(json.dumps(u1, ensure_ascii=False, indent=0), encoding="utf-8")
    (CROPS / "review_todo.json").write_text(json.dumps(todo, ensure_ascii=False, indent=0), encoding="utf-8")
    # 확인: 파일 수 = index 수(화질마다), 세 화질 이름 짝
    files = {q: sorted(f.relative_to(CROPS / q).as_posix() for f in (CROPS / q).rglob("*.jpg")) for q in QS}
    assert all(len(files[q]) == len(rows) for q in QS), {q: len(v) for q, v in files.items()}
    assert files["q2992"] == files["q1496"] == files["q997"]

    # 요약
    sc_split = defaultdict(set)
    for x in rows:
        sc_split[x["scene_round"]].add(x["split"])
    shared = sorted(s for s, v in sc_split.items() if len(v) > 1)
    unit_split, track_split = defaultdict(set), defaultdict(set)
    for x in rows:
        unit_split[x["unit"]].add(x["split"])
        track_split[f"{x['round']}#{x['tid']}"].add(x["split"])
    by_q = {}
    for q in QS:
        by_q[q] = {}
        for sp in ("train", "dev"):
            xs = [x for x in rows if x["split"] == sp]
            by_q[q][sp] = {"crops": len(xs), "units": len({x["unit"] for x in xs}), "rounds": len({x["round"] for x in xs}),
                           "scene_rounds": len({x["scene_round"] for x in xs}),
                           "long_side_median": statistics.median(max(x["size"][q]) for x in xs) if xs else None,
                           "long_side_p10_p90": [float(np.percentile([max(x["size"][q]) for x in xs], p)) for p in (10, 90)] if xs else None}
    tiles = {}
    for c in CLASSES:
        tr = [x for x in rows if x["tile"] == c and x["split"] == "train"]
        dv = [x for x in rows if x["tile"] == c and x["split"] == "dev"]
        tiles[c] = {"train": len(tr), "dev": len(dv), "train_units": len({x["unit"] for x in tr}), "dev_units": len({x["unit"] for x in dv}),
                    "flags": [f for f, on in (("개발에 없음", not dv), (f"학습 {FEW}장 미만", len(tr) < FEW)) if on]}
    per_round = {}
    for sp in ("train", "dev"):
        xs = [x for x in rows if x["split"] == sp]
        cr, un = Counter(x["round"] for x in xs), Counter()
        for u in {x["unit"] for x in xs}:
            un[u.split("#")[0]] += 1
        per_round[sp] = {rid: {"crops": cr[rid], "units": un[rid], "crop_share": round(cr[rid] / len(xs), 3), "unit_share": round(un[rid] / max(1, sum(un.values())), 3)}
                         for rid in sorted(cr)}
    tr_x = [x for x in rows if x["split"] == "train"]
    r08 = [x for x in tr_x if x["round"] == "r08_125630"]
    sizes = {q: sum(f.stat().st_size for f in (CROPS / q).rglob("*.jpg")) for q in QS}
    summ = {
        "made_by": "v1114_crops.py",
        "verdict_tracks_review": dict(verdict_raw), "verdict_tracks_after_overrides": dict(verdict_final),
        "overrides_applied": sorted(f"{a}#{b}" for a, b in used_ov), "per_image_keys_unmatched": bad_keys,
        "by_quality_split": by_q, "tiles": tiles,
        "tiles_missing_in_dev": [c for c, v in tiles.items() if not v["dev"]], "tiles_train_lt5": [c for c, v in tiles.items() if v["train"] < FEW],
        "per_round": per_round,
        "r08_125630": {"note": "12:55~12:58 카메라를 옮겨 같은 실물 패가 여러 id 로 들어감(draft scale/move_break). 게다가 r06~r10 은 r06 화료 탁자가 그대로(경계 대조: r07→r08 같은 자리 같은 종류 67/74).",
                       "train_crops": len(r08), "train_crop_share": round(len(r08) / len(tr_x), 3),
                       "train_units": len({x["unit"] for x in r08}), "train_unit_share": round(len({x["unit"] for x in r08}) / len({x["unit"] for x in tr_x}), 3)},
        "dropped_boxes": dict(dropped), "dropped_tracks": dict(dropped_tracks),
        "review_todo_boxes": len(todo), "review_todo_open": len(open_todo),
        "review_todo_decided": dict(Counter(x["decision"] for x in todo if x.get("decision"))),
        "box_overrides_applied": box_log, "blind_review": blind_review,
        "files_per_quality": {q: len(files[q]) for q in QS}, "file_names_paired": True,
        "u1_counts": {q: {sp: len(json.loads((CROPS / q / f"{sp}_u1.json").read_text(encoding="utf-8"))) for sp in ("train", "dev")} for q in QS}, "review_todo_by_why": dict(Counter(x["why"] for x in todo)),
        "review_todo_units": len({(x["round"], x["tid"]) for x in todo}),
        "occlusion_notes": occ_log,
        "scene_round_shared_across_split": shared, "scene_round_shared_count": len(shared),
        "units_across_split": sorted(u for u, v in unit_split.items() if len(v) > 1),
        "tracks_across_split": {"note": "같은 draft 실물 패 id 인데 앞 판 탁자 그림(scene_round 가 다른 split)의 상자만 다른 split 으로 간 것 — 다른 패(mixed)이거나 앞 판 탁자의 같은 패",
                                "tracks": sorted(u for u, v in track_split.items() if len(v) > 1)},
        "dev_rounds_final": sorted({r["id"] for r, _, _ in rounds if r.get("split_final") == "dev"}),
        "dev_scene_rounds": sorted({x["scene_round"] for x in rows if x["split"] == "dev"}),
        "folder_bytes": sizes, "crops_total": len(rows),
    }
    (CROPS / "summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: summ[k] for k in ("verdict_tracks_review", "verdict_tracks_after_overrides", "by_quality_split", "tiles_missing_in_dev", "tiles_train_lt5",
                                           "r08_125630", "dropped_boxes", "review_todo_open", "review_todo_decided", "u1_counts", "files_per_quality", "dropped_tracks", "review_todo_boxes", "review_todo_by_why", "scene_round_shared_count",
                                           "units_across_split", "tracks_across_split", "dev_rounds_final", "dev_scene_rounds", "folder_bytes", "per_image_keys_unmatched")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
