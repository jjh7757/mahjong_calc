"""11-14 검출기 세트(2026-11-15, 검출·역할 세트 3단계 2). v1114_dr_final.py 다음에.

대상 = final 그림 중 det_use(흔들림·탁자 아님 표시 2장 뺌 — 목록 det/list.json 에 이유와 함께 남김). 큰 가림은 넣는다.
종류 0 앞면 · 1 뒷면, 회전 상자. 라벨은 2992 에서 한 번 만들고 화질마다 manifest rules.scale 로 비율만 바꾼다(정규화 = 점 × scale / 그 화질 그림 크기).
  det/<q>/{train,dev}/images/<판>__<그림>.jpg   하드링크(안 되면 복사) — data/v1114/images/<q> 의 그림 그대로
  det/<q>/{train,dev}/labels/<판>__<그림>.txt   YOLO OBB: "종류 x1 y1 x2 y2 x3 y3 x4 y4"(0~1, 그림 밖은 0~1 로 자름)
  det/<q>/data.yaml                              ultralytics 꼴(names 0 face 1 back)
  det/build_input/                               기존 det_build.py --obb --backs 입력 꼴(q2992), det_build 의 OUT(= data/det) 과 같은 배치:
                                                   boxes_final.json            {이름: {path, boxes}}(앞면 축 상자)
                                                   backs/r2/boxes_r2fb.json    {이름: {backs}}
                                                   obb/rects.json              {이름: {path, items[{cls, box, key, status, rect}]}}(모든 상자 status fixed = 회전 상자를 그대로 씀)
                                                   split.json                  {이름: train|dev}(det_build 는 안 읽음 — 나눔용)
                                                 det_build 의 OUT 을 이 폴더로 바꾸면(DS 도 이 아래·scratch 로) 그대로 읽는다(2026-11-15 확인, v1114_load.det_build_input).
                                                 det_build 의 토막 크기(2040×1530)는 2992 그림에 맞아 그대로 돈다.
  det/edge_list.json                             사진 가장자리에서 절반 미만만 보이는(사진 안 면적 / 상자 면적 < 0.5) 상자·넓이 거의 0(짧은 변 < 8px) 상자 — 지우지 않고 목록만
  python -X utf8 experiments/tile_classifier/v1114_dr_det.py
"""
from __future__ import annotations

import json
import os
import shutil
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
V = HERE / "data" / "v1114"
DR = V / "dr"
OUT = V / "det"
QS = ("q2992", "q1496", "q997")


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


def main():
    man = json.loads((V / "manifest.json").read_text(encoding="utf-8"))
    scale = man["rules"]["scale"]
    if OUT.exists():
        shutil.rmtree(OUT)
    lst, edge, how = [], [], Counter()
    bi_faces, bi_backs, bi_rects, bi_split = {}, {}, {}, {}
    cnt = Counter()
    for p in sorted((DR / "final").glob("r*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        for im in d["images"]:
            stem = f"{d['round']}__{Path(im['name']).stem}"
            sp = im["split_final"]
            lst.append({"id": im["id"], "file": stem, "split": sp, "use": im["det_use"], "why": im["excluded_why"] if not im["det_use"] else [],
                        "flags": im["flags"], "faces": sum(b["cls"] == "face" for b in im["boxes"]), "backs": sum(b["cls"] == "back" for b in im["boxes"])})
            W0, H0 = im["size"]
            for b in im["boxes"]:
                fr = inside_frac(b["pts"], W0, H0)
                short = min(b["rect"][1])
                if fr < 0.5 or short < 8:
                    edge.append({"id": im["id"], "box": b["id"], "cls": b["cls"], "inside_frac": round(fr, 3), "short_side": round(short, 1), "use": im["det_use"]})
            if not im["det_use"]:
                cnt["excluded"] += 1
                continue
            cnt[f"{sp}_images"] += 1
            for b in im["boxes"]:
                cnt[f"{sp}_{b['cls']}"] += 1
            for q in QS:
                src = V / im["paths"][q]
                from PIL import Image
                Wq, Hq = Image.open(src).size
                s = scale[q]
                lines = []
                for b in sorted(im["boxes"], key=lambda b: (b["cls"] != "face", str(b["id"]))):
                    pts = np.clip(np.array(b["pts"], float) * s / [Wq, Hq], 0, 1)
                    lines.append(f"{0 if b['cls'] == 'face' else 1} " + " ".join(f"{v:.6f}" for v in pts.reshape(-1)))
                how[link(src, OUT / q / sp / "images" / f"{stem}.jpg")] += 1
                lp = OUT / q / sp / "labels" / f"{stem}.txt"
                lp.parent.mkdir(parents=True, exist_ok=True)
                lp.write_text("\n".join(lines) + "\n", encoding="utf-8")
            # 기존 det_build 입력 꼴(q2992)
            path = str((V / im["paths"]["q2992"]).resolve())
            faces = [b for b in im["boxes"] if b["cls"] == "face"]
            backs = [b for b in im["boxes"] if b["cls"] == "back"]
            bi_faces[stem] = {"path": path, "boxes": [list(map(int, b["box"])) for b in faces]}
            bi_backs[stem] = {"backs": [list(map(int, b["box"])) for b in backs]}
            items, seen = [], set()
            for c, bs in ((0, faces), (1, backs)):
                for b in bs:
                    key = tuple(int(v) for v in b["box"])
                    if (c, key) in seen:
                        cnt["build_dup_key"] += 1
                    seen.add((c, key))
                    items.append({"cls": c, "box": list(key), "key": f"{stem}|{c}|{','.join(map(str, key))}", "status": "fixed",
                                  "rect": [[float(b["rect"][0][0]), float(b["rect"][0][1])], [float(b["rect"][1][0]), float(b["rect"][1][1])], float(b["rect"][2])],
                                  "why": "v1114 최종 라벨 회전 상자"})
            bi_rects[stem] = {"path": path, "items": items}
            bi_split[stem] = sp
    for q in QS:
        (OUT / q / "data.yaml").write_text(f"path: {(OUT / q).as_posix()}\ntrain: train/images\nval: dev/images\nnames:\n  0: face\n  1: back\n", encoding="utf-8")
    bi = OUT / "build_input"
    bi.mkdir(parents=True, exist_ok=True)
    # det_build.py 가 OUT 아래에서 읽는 자리 그대로(OUT/boxes_final.json, OUT/backs/r2/boxes_r2fb.json, OUT/obb/rects.json)
    for n, obj in (("boxes_final.json", bi_faces), ("backs/r2/boxes_r2fb.json", bi_backs), ("obb/rects.json", bi_rects), ("split.json", bi_split)):
        (bi / n).parent.mkdir(parents=True, exist_ok=True)
        (bi / n).write_text(json.dumps(obj, ensure_ascii=False, indent=0), encoding="utf-8")
    (OUT / "list.json").write_text(json.dumps({"_note": "검출 세트 그림 목록. use=false 는 뺀 그림(이유 why). v1114_dr_det.py", "images": lst}, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "edge_list.json").write_text(json.dumps({"_note": "지우지 않은 의심 상자: inside_frac < 0.5(사진 가장자리에서 절반 미만만 보임) 또는 short_side < 8px", "boxes": edge},
                                                   ensure_ascii=False, indent=1), encoding="utf-8")
    import v1114_dr_final as fin
    summ = {"counts": dict(cnt), "files": dict(how), "edge_boxes": len(edge), "edge_boxes_in_use": sum(e["use"] for e in edge),
            "excluded_images": [{"id": x["id"], "why": x["why"]} for x in lst if not x["use"]], "process": fin.PROCESS, "review_edits": fin.review_edits(),
            "classes": {"0": "face(앞면)", "1": "back(뒷면)"}, "label_format": "YOLO OBB: 종류 x1 y1 x2 y2 x3 y3 x4 y4(0~1), 2992 라벨 × manifest rules.scale ÷ 그 화질 그림 크기"}
    for q in QS:
        for sp in ("train", "dev"):
            fs = list((OUT / q / sp / "images").glob("*.jpg"))
            summ[f"{q}_{sp}_images"] = len(fs)
            summ[f"{q}_{sp}_labels"] = len(list((OUT / q / sp / "labels").glob("*.txt")))
            summ[f"{q}_{sp}_MB"] = round(sum(f.stat().st_size for f in fs) / 2**20, 1)
    (OUT / "summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summ, ensure_ascii=False))


if __name__ == "__main__":
    main()
