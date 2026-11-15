"""녹화 프레임 mid(49장)·new(72장) 최종 라벨(2026-11-15, 녹화 세트 3단계 1). v1114rec_draft.py + 눈 확인(dr/review) 다음에. 다시 돌려도 같은 결과.

v1114_dr_final.py 와 같은 규칙, 좌표 = 녹화 1496:
  초안 dr/draft/<판>.json 상자 + dr/review/<판>.json 고침(읽기만):
    box_edits: drop → 뺌 / restore → 앞면으로 되살림 / flip → 앞면 ↔ 뒷면 / refit → rect·pts·box 바꿈.
    adds → 상자 더함(id = aN, src add). roles → 그 상자 역할·주인(role_src review).
    고침이 없는 앞면의 역할 = 초안 role_draft(나 = 이웃 라벨이 있으면 그것(role_src nb), 없으면 규칙(role_src rule); 다 = 규칙).
      ※ v1114_dr_final 은 규칙(rule) 답을 기본으로 썼지만, 녹화 세트 눈 확인 양식(_FORMAT.json roles)은 "role_draft 가 맞으면 적지 않는다" 였으므로 role_draft 를 쓴다.
    역할 없는 앞면(뒤집어 앞면이 된 상자·역할 안 적은 더한 앞면)은 role None + role_missing 으로 남기고 센다. 뒷면은 역할을 지운다.
  그림(계획 세션 2026-11-15 규칙):
    flags·phase = 눈 확인 값. pre_game = phase play 이고 강(river) 역할 앞면 0장(대국 시작 전·빈 탁자). between = flags 에 between.
    det_use = blur·not_table 아님. role_use = det_use 이고 between 아니고 pre_game 아님(between·pre_game 은 검출 세트에는 넣고 역할 세트에서만 뺌, 표시만).
    winner: phase end 그림 중 new 는 초안 값(winner·winner_src = rounds_note 등), mid 는 같은 scene_round 의 기존 화료 사진(data/v1114/dr/final kind win)
      화료자가 하나로 모이면 그것(winner_src same_scene_win). play 그림은 null.
      (4단계 계획 세션 결정) 그래도 비어 있는 end 그림은 hand 역할 앞면의 주인이 한 자리뿐이면 그 자리(winner_src hand_seat), 아니면 null.
  패 종류: tile = null(이 단계에서는 정하지 않음 — 패 종류는 crops/ 쪽 작업이 만들고 마지막에 합친다), tile_draft·tile_draft_src = 초안 값(눈 확인 안 됨).
  python -X utf8 experiments/tile_classifier/v1114rec_dr_final.py
결과 data/v1114rec/dr/final/<판>.json, final/_summary.json
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from v1114rec_dr_common import DR, V, jload, jsave  # noqa: E402

OUT = DR / "final"


def review_edits() -> dict:
    c = Counter()
    for p in sorted((DR / "review").glob("[nr]*.json")):
        for e in jload(p)["images"].values():
            c["seen"] += bool(e.get("seen"))
            for ed in (e.get("box_edits") or {}).values():
                c[f"box_{ed['op']}"] += 1
            for a in e.get("adds") or []:
                c[f"add_{a['cls']}_{a.get('fit')}"] += 1
            c["role_edits"] += len(e.get("roles") or {})
            fl = e.get("flags") or []
            c["flag_" + ("+".join(fl) if fl else "normal")] += 1
    return dict(c)


def final_boxes(img: dict, e: dict) -> list:
    boxes = []
    for b in img["boxes"]:
        rd = b.get("role_draft") or {}
        boxes.append({"id": b["id"], "cls": b["cls"], "keep": b["status"] == "keep", "box": list(b["box"]), "rect": b["rect"], "pts": b["pts"],
                      "src": b["src"], "tile": None, "tile_draft": b.get("tile"), "tile_draft_src": b.get("tile_src"),
                      "role": rd.get("role"), "seat": rd.get("seat"), "role_src": rd.get("src") if rd else None, "edit": None})
    by = {str(b["id"]): b for b in boxes}
    for sid, ed in (e.get("box_edits") or {}).items():
        b = by[sid]
        op = ed["op"]
        b["edit"] = op
        if op == "drop":
            b["keep"] = False
        elif op == "restore":
            b["keep"], b["cls"] = True, "face"
        elif op == "flip":
            b["keep"] = True
            was = b["cls"]
            b["cls"] = "back" if was == "face" else "face"
            if was == "back":  # 뒷면에서 앞면이 된 상자는 초안 역할이 없다
                b["role"] = b["seat"] = b["role_src"] = None
        elif op == "refit":
            b["rect"], b["pts"], b["box"] = ed["rect"], ed["pts"], ed["box"]
    for sid, rr in (e.get("roles") or {}).items():
        b = by[sid]
        b["role"], b["seat"], b["role_src"] = rr["role"], rr.get("seat"), "review"
    for a in e.get("adds") or []:
        boxes.append({"id": a["aid"], "cls": a["cls"], "keep": True, "box": a["box"], "rect": a["rect"], "pts": a["pts"], "src": "add",
                      "tile": None, "tile_draft": None, "tile_draft_src": None,
                      "role": a.get("role"), "seat": a.get("seat"), "role_src": "review" if a.get("role") else None, "edit": "add"})
    out = []
    for b in boxes:
        if not b.pop("keep"):
            continue
        if b["cls"] == "back":
            b["role"] = b["seat"] = b["role_src"] = None
            b["tile_draft"] = b["tile_draft_src"] = None
        elif b["role"] is None:
            b["role_missing"] = True
        out.append(b)
    return out


def scene_winners() -> dict:
    sw: dict = {}
    for p in sorted((V / "dr" / "final").glob("r*.json")):
        for im in jload(p)["images"]:
            if im["kind"] == "win" and im["winner"]:
                sw.setdefault(im["scene_round"], Counter())[im["winner"]] += 1
    return sw


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("[nr]*.json"):
        old.unlink()
    sw = scene_winners()
    summ = Counter()
    role_missing = []
    for p in sorted((DR / "draft").glob("[nr]*.json")):
        d = jload(p)
        rv = jload(DR / "review" / p.name)
        imgs = []
        for im in d["images"]:
            e = rv["images"][im["id"]]
            boxes = final_boxes(im, e)
            flags = list(e.get("flags") or [])
            phase = e["phase"]
            faces = [b for b in boxes if b["cls"] == "face"]
            n_river = sum(b["role"] == "river" for b in faces)
            pre_game = phase == "play" and n_river == 0
            between = "between" in flags
            winner = wsrc = None
            if phase == "end":
                if im["part"] == "new":
                    winner, wsrc = im.get("winner"), im.get("winner_src")
                else:
                    s = sw.get(im["scene_round"])
                    if s and len(s) == 1:
                        winner, wsrc = next(iter(s)), "same_scene_win"
                if winner is None:
                    hs = {b["seat"] for b in faces if b["role"] == "hand" and b["seat"]}
                    if len(hs) == 1:
                        winner, wsrc = next(iter(hs)), "hand_seat"
            det_use = not ({"blur", "not_table"} & set(flags))
            why = [] if det_use else ["흔들림·탁자 아님 표시: " + ",".join(flags)]
            role_use = det_use and not between and not pre_game
            if between:
                why.append("between(대국 중 아님)")
            if pre_game:
                why.append("pre_game(phase play, 강 앞면 0)")
            for b in boxes:
                if b.get("role_missing"):
                    role_missing.append({"id": im["id"], "box": b["id"], "edit": b["edit"]})
            imgs.append({k: im.get(k) for k in ("id", "name", "part", "kind", "format", "at", "ms", "scene_round", "setup", "path", "size",
                                                 "felt", "device", "grid_est", "prev_id", "next_id")}
                        | {"split_final": im["split"], "winner": winner, "winner_src": wsrc, "flags": flags, "phase": phase,
                           "pre_game": pre_game, "between": between, "n_river": n_river, "det_use": det_use, "role_use": role_use,
                           "excluded_why": why, "review_notes": e.get("notes", ""), "seen": e.get("seen"), "boxes": boxes})
            summ["images"] += 1
            summ[f"{im['part']}_{im['split']}"] += 1
            summ[f"phase_{phase}"] += 1
            summ["pre_game"] += pre_game
            summ["between"] += between
            summ["det_use"] += det_use
            summ["role_use"] += role_use
            summ["role_missing"] += sum(1 for b in boxes if b.get("role_missing"))
            if phase == "end":
                summ[f"end_winner_{wsrc or 'none'}"] += 1
            for b in boxes:
                summ[f"box_{b['cls']}"] += 1
        jsave(OUT / p.name, {"round": d["round"], "part": d["part"], "reviewer": rv.get("reviewer"), "done_all_seen": all(x["seen"] for x in imgs),
                             "_note": "최종 라벨(v1114rec_dr_final.py). 좌표 = 녹화 1496 원래 픽셀. boxes[]: id(draft 번호 또는 aN), cls face|back, rect, pts, box, "
                                      "src, tile(null — 패 종류는 나중에 합침), tile_draft(초안, 눈 확인 안 됨), role·seat(앞면만), role_src nb|rule|review, edit.",
                             "images": imgs}, indent=0)
    jsave(OUT / "_summary.json", {**dict(summ), "role_missing_list": role_missing, "review_edits": review_edits()})
    print(dict(summ))
    print("role_missing", role_missing)


if __name__ == "__main__":
    main()
