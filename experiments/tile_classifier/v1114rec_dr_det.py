"""녹화 프레임(rec1496) 검출기 세트(2026-11-15, 녹화 세트 3단계 3). v1114rec_dr_final.py·v1114rec_dr_final_pair.py 다음에. 다시 돌려도 같은 결과.

v1114_dr_det.py 와 같은 꼴, 화질은 rec1496 하나:
  대상 = 세 갈래(pair·mid·new) 최종 그림 중 det_use(흔들림·탁자 아님 뺌). 큰 가림·between·pre_game 은 넣는다.
  det/rec1496/{train,dev}/images/<판>__<그림>.jpg   하드링크(안 되면 복사) — data/v1114rec/images/rec1496 의 녹화 그림 그대로.
                                                    pair 는 기존 세트(data/v1114/det/<q>)와 같은 파일 이름, mid·new 는 mid_<ms>·new_<ms> 이름이라 안 겹침.
  det/rec1496/{train,dev}/labels/<판>__<그림>.txt  YOLO OBB "종류 x1 y1 … x4 y4"(0~1, 그림 밖은 자름), 0 앞면 · 1 뒷면. 정규화 = 1496 좌표 ÷ 1496.
  det/rec1496/data.yaml                            ultralytics 꼴(names 0 face 1 back)
  나눔 = 그림의 split_final(pair = 기존 split_final, mid·new = manifest split).
  det/list.json  그림마다 id·part·file·split·scene_round·flags·phase·use·why(제외 사유)·faces·backs. pair 의 짝 없음(no_rec) 3장도 use=false 로.
  det/edge_list.json  사진 가장자리에서 절반 미만만 보이는 상자·짧은 변 < 4px 상자(지우지 않고 목록만, 기존 8px@2992 와 같은 크기).
  build_input(기존 det_build.py 입력 꼴)은 만들지 않았다(summary 에 적음).
  python -X utf8 experiments/tile_classifier/v1114rec_dr_det.py
"""
from __future__ import annotations

import os
import shutil
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from v1114rec_dr_common import DR, PARTS, Q, R, final_all, jload, jsave  # noqa: E402

OUT = R / "det"


def link(src: Path, dst: Path) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
        return "link"
    except OSError:
        shutil.copy2(src, dst)
        return "copy"


def inside_frac(pts, W, H) -> float:
    p = np.array(pts, np.float32)
    a = cv2.contourArea(p)
    if a <= 0:
        return 0.0
    clip = np.array([[0, 0], [W, 0], [W, H], [0, H]], np.float32)
    inter, _ = cv2.intersectConvexConvex(p, clip)
    return float(inter / a)


def stem_of(im: dict) -> str:
    return f"{im['id'].split('/')[0]}__{Path(im['name']).stem}"


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    lst, edge, how, cnt = [], [], Counter(), Counter()
    for im in final_all():
        stem, sp, part = stem_of(im), im["split_final"], im["part"]
        lst.append({"id": im["id"], "part": part, "file": stem, "split": sp, "scene_round": im["scene_round"], "kind": im["kind"], "phase": im["phase"],
                    "flags": im["flags"], "between": im.get("between", False), "pre_game": im.get("pre_game"), "use": im["det_use"],
                    "why": im["excluded_why"] if not im["det_use"] else [],
                    "faces": sum(b["cls"] == "face" for b in im["boxes"]), "backs": sum(b["cls"] == "back" for b in im["boxes"])})
        W, H = im["size"]
        for b in im["boxes"]:
            fr = inside_frac(b["pts"], W, H)
            short = min(b["rect"][1])
            if fr < 0.5 or short < 4:
                edge.append({"id": im["id"], "part": part, "box": b["id"], "cls": b["cls"], "inside_frac": round(fr, 3), "short_side": round(short, 1),
                             "use": im["det_use"]})
        if not im["det_use"]:
            cnt[f"excluded_{part}"] += 1
            continue
        cnt[f"{part}_{sp}_images"] += 1
        cnt[f"{sp}_images"] += 1
        for b in im["boxes"]:
            cnt[f"{part}_{sp}_{b['cls']}"] += 1
            cnt[f"{sp}_{b['cls']}"] += 1
        src = R / im["path"]
        lines = []
        for b in sorted(im["boxes"], key=lambda b: (b["cls"] != "face", str(b["id"]))):
            pts = np.clip(np.array(b["pts"], float) / [W, H], 0, 1)
            lines.append(f"{0 if b['cls'] == 'face' else 1} " + " ".join(f"{v:.6f}" for v in pts.reshape(-1)))
        how[link(src, OUT / Q / sp / "images" / f"{stem}.jpg")] += 1
        lp = OUT / Q / sp / "labels" / f"{stem}.txt"
        lp.parent.mkdir(parents=True, exist_ok=True)
        lp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for x in jload(DR / "final_pair" / "_summary.json")["no_rec"]:
        lst.append({"id": x["id"], "part": "pair", "file": None, "split": x["split_final"], "scene_round": None, "use": False,
                    "why": ["짝 녹화 프레임 없음(pairs.json status no_rec)"]})
        cnt["excluded_pair_no_rec"] += 1
    (OUT / Q).mkdir(parents=True, exist_ok=True)
    (OUT / Q / "data.yaml").write_text(f"path: {(OUT / Q).as_posix()}\ntrain: train/images\nval: dev/images\nnames:\n  0: face\n  1: back\n", encoding="utf-8")
    jsave(OUT / "list.json", {"_note": "검출 세트 그림 목록(v1114rec_dr_det.py). use=false 는 뺀 그림(이유 why). part = pair(기존 그림과 같은 순간)|mid(기존 판 안 새 순간)|new(녹화만 있는 판).",
                              "images": lst})
    jsave(OUT / "edge_list.json", {"_note": "지우지 않은 의심 상자: inside_frac < 0.5 또는 short_side < 4px(1496)", "boxes": edge})
    summ = {"counts": dict(cnt), "files": dict(how), "edge_boxes": len(edge), "edge_boxes_in_use": sum(e["use"] for e in edge),
            "excluded_images": [{"id": x["id"], "part": x["part"], "why": x["why"]} for x in lst if not x["use"]],
            "by_part_split": {f"{p}_{s}": {"images": cnt[f"{p}_{s}_images"], "face": cnt[f"{p}_{s}_face"], "back": cnt[f"{p}_{s}_back"]}
                              for p in PARTS for s in ("train", "dev")},
            "classes": {"0": "face(앞면)", "1": "back(뒷면)"}, "quality": Q,
            "label_format": "YOLO OBB: 종류 x1 y1 x2 y2 x3 y3 x4 y4(0~1), 1496 좌표 ÷ 1496",
            "build_input": "만들지 않음(기존 det_build.py --obb --backs 입력 꼴은 2992 그림 토막 크기에 맞춰 있어 1496 녹화에는 바로 안 맞음 — 필요하면 따로)",
            "process": {
                "source": "2026-11-14 매장 헤드 휴대폰 1:1 녹화(2992 스트림을 기기에서 2×2 평균, JPEG 85, 1496²). 세 갈래: pair = 기존 189장과 같은 순간 186장, "
                          "mid = 기존 판 안 두 그림 사이 새 순간 49장, new = 녹화만 있는 판 n01~n08 72장.",
                "pair_labels": "기존 최종 라벨(data/v1114/dr/final, 2992) ×0.5. 상자 차이 큰 478칸을 두 검토자가 판정 → occluded 19칸 상자 뺌, moved 세 그림(r20 win_143425 줄 9개 옮김, "
                               "r14 f0035 box19 뺌, r19 f0022 box73 옮김)은 pair/overrides.json. 나머지 짝 그림은 12장 표본 눈 확인(pair/overlay_check).",
                "mid_new_labels": "초안 = 녹화를 2배로 키운 그림에 운영 검출기 tile-obb-r8(전체 + 네 조각) → 눈 확인(121장 모두 seen, dr/review): 지움·뒤집음·다시 맞춤·더함·역할 고침.",
                "split": "pair = 기존 split_final, mid·new = manifest split(scene_round 기준, 학습·개발 공유 0).",
                "audit_stage4": "4단계(2026-11-15): 독립 검토 3몫 92장 지적 66건을 녹화 그림에서 다시 보고 반영(dr/audit/applied.json — 적용 20 · 미적용 46), "
                                "패 종류 쪽과 어긋난 13건 정리(dr/conflicts_resolved.json), 검출기 헛검출 108건 전수 확인해 7장 더함(dr/unmatched_review.json), "
                                "계획 세션 결정(n04 흰 테두리 이음매 지움, r02 box4 loose/right). 짝 고침은 pair/overrides.json(drop·move·flip·adds pN).",
                "box_rule": "상자 = 패 하나, 위에서 보이는 면에 맞춘 회전 상자. 뚜렷이 절반 넘게 보일 때만, 손에 들린 패 포함, 보이는 부분에 맞춤(기존 세트와 같음).",
            },
            "weaknesses": ["mid·new 초안은 2배 키운 그림에 운영 검출기를 돌린 것 — 검출기가 못 잡은 패는 눈 확인에서 더한 것만 있음",
                           "pair 라벨은 2992 그림에서 정한 상자를 옮긴 것 — 상자 차이 > 7 인 칸만 눈 확인, 나머지는 12장 표본",
                           "독립 검토는 92장(개발 그림 전부 + 학습 표본) — 나머지 학습 그림은 독립 검토 안 받음. 헛검출 전수 확인으로 검출기가 잡은 놓침은 다 봤지만 검출기도 못 잡은 놓침은 남아 있을 수 있음",
                           "'절반 넘게' 판정은 눈대중(대략 2/3 이상만 더함) — 손가락 밑 세운 손패 등 절반 안팎 패는 라벨이 없다"],
            "review_edits_mid_new": jload(DR / "final" / "_summary.json")["review_edits"]}
    for sp in ("train", "dev"):
        fs = list((OUT / Q / sp / "images").glob("*.jpg"))
        summ[f"{Q}_{sp}_images"] = len(fs)
        summ[f"{Q}_{sp}_labels"] = len(list((OUT / Q / sp / "labels").glob("*.txt")))
        summ[f"{Q}_{sp}_MB"] = round(sum(f.stat().st_size for f in fs) / 2**20, 1)
    jsave(OUT / "summary.json", summ)
    print(json_short(summ))


def json_short(s):
    import json
    return json.dumps({k: v for k, v in s.items() if k in ("counts", "files", "edge_boxes", "edge_boxes_in_use", "by_part_split")}, ensure_ascii=False)


if __name__ == "__main__":
    main()
