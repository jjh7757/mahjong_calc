"""검출·역할 최종 라벨(2026-11-15, 검출·역할 세트 3단계 1). v1114_dr_draft.py + 2단계 review 다음에. 다시 돌려도 같은 결과.

최종 = draft/<판>.json 상자 + review/<판>.json 고침(읽기만):
  box_edits: drop → 뺌 / restore → 지운 초안 앞면을 앞면으로 / flip → 앞면 ↔ 뒷면 / refit → rect·pts·box 바꿈.
  adds → 상자 더함(id = a1…, src add). roles → 그 상자 역할·주인(role_src review), 없으면 초안 규칙 답(role_src rule).
  역할 없는 앞면(되살린·뒤집어 앞면이 된 상자에 역할 고침이 없음)은 role None + role_missing 로 남기고 센다.
  뒷면으로 바뀐 상자는 역할을 지운다.
그림: flags(review), phase = end(화료 사진 전부, 프레임 중 pair·loose 가 있거나 한 자리 hand ≥ 7) / tidy(r07 전부) / play(그 밖),
  winner = 화료 사진은 draft 값(winner_src), end 프레임은 같은 scene_round 화료 사진들의 화료자(하나로 모이면, src same_scene_win).
  det_use = blur·not_table 아님, role_use = det_use 이고 phase ≠ tidy.
  그림 단위 제외 결정은 dr/final_overrides.json(role_exclude = 역할 세트만 뺌, det_exclude = 둘 다 뺌, 이유 필수)에서 읽는다.
  python -X utf8 experiments/tile_classifier/v1114_dr_final.py
결과 data/v1114/dr/final/<판>.json, final/_summary.json
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DR = HERE / "data" / "v1114" / "dr"
OWNED = ("hand", "loose", "meld", "river")
TIDY_ROUNDS = {"r07_123310"}
# 만든 과정(det·role summary.json 에 그대로 옮긴다). 고침 수는 review 파일에서 다시 센다(review_edits).
PROCESS = {
    "source": "2026-11-14 매장 실제 대국(experiments/visit_20261114), 분류기 세트(data/v1114)와 같은 189장(프레임 162 + 화료 사진 27, 2992²). "
              "나눔 = 그림의 split_final(탁자 장면 scene_round 기준, 학습·개발이 같은 scene_round 를 공유하지 않음).",
    "draft": "초안 = 운영 검출기 tile-obb-r8 을 2992 그림에 돌린 것(앞면 = 분류기 세트 초안 상자, 뒷면 = 전체 + 네 조각 검출). 격자는 안 씀. "
             "한계: 검출기가 못 잡는 패는 눈 확인에서 사람이 더한 것만 들어 있다 — 이 라벨로 같은 검출기를 재면 부풀려진다.",
    "stage2": "2단계 눈 확인(Opus 5.5 4대, 189장 모두 seen): 확인 그림(전체 0.5배 + 네 조각 원래 크기 + 역할 그림)과 도우미 v1114_dr_fit.py. 고침 수 = review_edits.",
    "independent_review": "독립 검토 80장(개발 46 전부 + 학습 34 = 판마다 2장, 씨앗 20261115, dr/audit): 놓침 7건 지적 중 3건 반영·4건은 절반 안팎이라 미반영, "
                          "역할 틀림 2건 반영.",
    "supplement": "보충: 2단계·독립 검토 메모에 적힌 가림 자리 약 95곳을 다시 판정해 상자 5개를 더함(addbox, fit=manual — 손에 들린·일부 가린 패).",
    "plan_session_fixes": "계획 세션 고침: 일관성 검사 ① 5건(같은 장면 역할·주인 맞춤) + 역할 2건(r17 f0001 #1, r08 f0002 #56), 역할 세트 그림 제외 6장(final_overrides.json).",
    "box_rule": "상자 = 패 하나, 위에서 보이는 면에 맞춘 회전 상자. 뚜렷이 절반 넘게 보일 때만(손·팔·사진 끝에 가린 패 포함), 손에 들린 패 포함, 보이는 부분에 맞춤. "
                "앞면 0 = 무늬 면, 뒷면 1 = 패산(위에서 보이는 패마다)·세운 손패(한 장마다)·안깡 뒷면. 탁자 밖 물체·종이·화면 속 패는 패 아님.",
    "phase": "end = 화료 사진 전부 + 프레임 중 pair·loose 가 있거나 한 자리 hand ≥ 7 / tidy = r07 전부(패를 정리하는 장면, 역할 규칙이 안 맞음) / play = 그 밖(판 중).",
    "excluded": "검출 세트: 흔들림 r01 f0002, 탁자 아님+흔들림 r07 f0036. 역할 세트: 그 둘 + tidy(r07 나머지 7장) + final_overrides.json role_exclude 6장"
                "(r08 f0030 손가락 가림·기기 위치 틀림, r08 f0002·f0007·f0011·r04 f0025·r01 f0081 펠트·기기 위치 추정 불안정).",
    "weaknesses": ["학습 그림 107장은 독립 검토를 받지 않음(2단계 눈 확인뿐)", "독립 검토는 라벨을 가리지 않은 방식(최종 라벨 그림을 보고 틀린 것을 찾음)",
                   "초안이 tile-obb-r8 출력이라 그 검출기의 놓침은 사람이 찾은 만큼만 들어 있음",
                   "역할 토큰의 격자·기기 위치는 그림에서 찾은 펠트로 짐작한 값(grid_est·device) — 저장 격자는 2반장에서 어긋나 안 씀",
                   "학습 쪽 r06~r10 은 한 탁자를 여러 번 찍은 것에 가깝고 r05(개발)는 r04 화료 탁자 재촬영이 많음(분류기 세트와 같은 약점)"],
}


def review_edits() -> dict:
    c = Counter()
    for p in sorted((DR / "review").glob("r*.json")):
        for e in json.loads(p.read_text(encoding="utf-8"))["images"].values():
            c["seen"] += bool(e.get("seen"))
            for ed in (e.get("box_edits") or {}).values():
                c[f"box_{ed['op']}"] += 1
            for a in e.get("adds") or []:
                c[f"add_{a['cls']}_{a.get('fit')}"] += 1
            c["role_edits"] += len(e.get("roles") or {})
            fl = e.get("flags") or []
            c["flag_" + ("+".join(fl) if fl else "normal")] += 1
    return dict(c)


def final_image(img: dict, e: dict) -> dict:
    boxes = []
    for b in img["boxes"]:
        boxes.append({"id": b["id"], "cls": b["cls"], "keep": b["status"] == "keep", "box": list(b["box"]), "rect": b["rect"], "pts": b["pts"],
                      "src": b["src"], "tile": b.get("tile"), "role": (b.get("rule") or {}).get("role"), "seat": (b.get("rule") or {}).get("seat"),
                      "role_src": "rule" if b.get("rule") else None, "edit": None})
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
            b["cls"] = "back" if b["cls"] == "face" else "face"
        elif op == "refit":
            b["rect"], b["pts"], b["box"] = ed["rect"], ed["pts"], ed["box"]
    for sid, rr in (e.get("roles") or {}).items():
        b = by[sid]
        b["role"], b["seat"], b["role_src"] = rr["role"], rr.get("seat"), "review"
    for a in e.get("adds") or []:
        boxes.append({"id": a["aid"], "cls": a["cls"], "keep": True, "box": a["box"], "rect": a["rect"], "pts": a["pts"], "src": "add", "tile": None,
                      "role": a.get("role"), "seat": a.get("seat"), "role_src": "review" if a.get("role") else None, "edit": "add"})
    out = []
    for b in boxes:
        if not b["keep"]:
            continue
        b.pop("keep")
        if b["cls"] == "back":
            b["role"] = b["seat"] = b["role_src"] = None
        elif b["role"] is None:
            b["role_missing"] = True
        out.append(b)
    return out


def main():
    (DR / "final").mkdir(parents=True, exist_ok=True)
    ovp = DR / "final_overrides.json"
    ov = json.loads(ovp.read_text(encoding="utf-8")) if ovp.exists() else {}
    allr = {}
    for p in sorted((DR / "draft").glob("r*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        rv = json.loads((DR / "review" / f"{d['round']}.json").read_text(encoding="utf-8"))
        allr[d["round"]] = (d, rv)
    # 같은 scene_round 의 화료 사진 화료자
    scene_win: dict = {}
    for d, rv in allr.values():
        for im in d["images"]:
            if im["kind"] == "win" and im["winner"]:
                scene_win.setdefault(im["scene_round"], Counter())[im["winner"]] += 1
    summ = Counter()
    for rid, (d, rv) in allr.items():
        imgs = []
        for im in d["images"]:
            e = rv["images"][im["id"]]
            boxes = final_image(im, e)
            flags = list(e.get("flags") or [])
            faces = [b for b in boxes if b["cls"] == "face"]
            hand_seat = Counter(b["seat"] for b in faces if b["role"] == "hand")
            if rid in TIDY_ROUNDS:
                phase = "tidy"
            elif im["kind"] == "win" or any(b["role"] in ("pair", "loose") for b in faces) or (hand_seat and max(hand_seat.values()) >= 7):
                phase = "end"
            else:
                phase = "play"
            winner, wsrc = (im["winner"], im["winner_src"]) if im["kind"] == "win" else (None, None)
            if im["kind"] != "win" and phase == "end":
                sw = scene_win.get(im["scene_round"])
                if sw and len(sw) == 1:
                    winner, wsrc = next(iter(sw)), "same_scene_win"
            det_use = not ({"blur", "not_table"} & set(flags))
            why = [] if det_use else ["흔들림·탁자 아님 표시: " + ",".join(flags)]
            if im["id"] in ov.get("det_exclude", {}):
                det_use = False
                why.append("final_overrides det_exclude: " + ov["det_exclude"][im["id"]])
            role_use = det_use and phase != "tidy"
            if phase == "tidy":
                why.append("tidy(r07 패 정리 장면)")
            if im["id"] in ov.get("role_exclude", {}):
                role_use = False
                why.append("final_overrides role_exclude: " + ov["role_exclude"][im["id"]])
            imgs.append({k: im[k] for k in ("id", "name", "kind", "at", "split_final", "scene_round", "scene", "path", "paths", "size", "format",
                                            "felt", "device", "grid_est")}
                        | {"winner": winner, "winner_src": wsrc, "flags": flags, "phase": phase, "det_use": det_use, "role_use": role_use,
                           "excluded_why": why, "review_notes": e.get("notes", ""), "seen": e.get("seen"), "boxes": boxes})
            summ["images"] += 1
            summ[f"phase_{phase}"] += 1
            summ["role_missing"] += sum(1 for b in boxes if b.get("role_missing"))
        res = {"round": rid, "split_final": d["split_final"], "reviewer": rv.get("reviewer"), "done_all_seen": all(x["seen"] for x in imgs),
               "_note": "최종 라벨(v1114_dr_final.py). 좌표 2992 원본 픽셀. boxes[]: id(draft 번호 또는 aN), cls face|back, rect [[cx,cy],[w,h],각도], pts 네 꼭짓점, "
                        "box 감싸는 축 상자, src, tile(분류기 세트 종류), role·seat(앞면만), role_src rule|review, edit(2단계 고침).",
               "images": imgs}
        (DR / "final" / f"{rid}.json").write_text(json.dumps(res, ensure_ascii=False, indent=0), encoding="utf-8")
    (DR / "final" / "_summary.json").write_text(json.dumps({**dict(summ), "process": PROCESS, "review_edits": review_edits()}, ensure_ascii=False, indent=1),
                                                encoding="utf-8")
    print(dict(summ))


if __name__ == "__main__":
    main()
