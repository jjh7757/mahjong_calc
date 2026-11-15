"""화질별 역할 입력 + 검출 수(2026-11-15, 검출·역할 세트 3단계 4). v1114_dr_final.py 다음에.

역할 모델은 상자 좌표만 받으므로, 화질 차이는 "그 화질에서 검출기가 내는 상자" 로만 들어온다. 그래서:
  세 화질 그림(data/v1114/images/<q>/…, q2992 원본 · q1496 2×2 평균 JPEG85 · q997 3픽셀 건너뛰기 JPEG75) 각각에 운영 검출기 tile-obb-r8.onnx 를
  겹쳐 보기(ondevice.overlay → reader.detect_full)와 같은 전체 프레임 경로로 한 번 돌린다: lr.decode_rgb(JPEG 바이트) → LocalReader._seat_raw
  = 긴 변 IMG(1280) 레터박스(짧은 변 32 배수 패딩 114) → ONNX → obb.decode 앞면(종류 0)·뒷면(종류 1) 점수 ≥ CONF(0.25), 감싸는 축 상자 IoU > 0.7 NMS
  → 앞면만 obb.slivers(사진 끝 2px 에 닿고 짧은 변 < 중앙값 절반인 조각 버림). 조각 키우기 없음. 안깡 짝(kans)은 따로 더하지 않는다
  (overlay 는 안깡 뒷면 상자를 앞면 목록에 덧붙이지만, 여기서는 그 상자가 뒷면 검출로 이미 들어 있다).
  검출 좌표 ÷ scale → 2992 좌표로 바꿔 최종 라벨과 맞댄다: 같은 종류끼리 회전 상자 다각형 IoU(cv2.intersectConvexConvex) ≥ MATCH_IOU(0.5),
  IoU 큰 쌍부터 한 대 한(욕심 매칭). 맞은 검출 = 라벨의 역할·주인을 옮김, 못 맞은 검출 = unmatched(헛검출), 못 맞은 라벨 = missed.
결과:
  role/det_input/<q>/labels_{train,dev}.json  역할 세트 그림(role_use)만. 그림마다 items(맞은 검출: 그 화질 좌표 box·pts, 2992 좌표 pts2992, score,
     label_id, iou, role, seat) · backs(맞은 뒷면 검출) · unmatched(종류·box·pts·score) · missed(종류별 수, 라벨 id)
  role/det_input/counts.json  화질별 × 나눔별 × 종류별 라벨 수·검출된 라벨 수·헛검출 수 — 검출 세트 그림(det_use, 흔들림·탁자 아님 2장 뺀 187장) 기준.
  python -X utf8 experiments/tile_classifier/v1114_dr_detinput.py
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
V = HERE / "data" / "v1114"
DR = V / "dr"
OUT = V / "role" / "det_input"
sys.path.insert(0, r"C:\Users\jjh7757\dev\mahjong-recognizer")
from app import local_read as lr  # noqa: E402
from app import obb  # noqa: E402

QS = ("q2992", "q1496", "q997")
MATCH_IOU = 0.5


def piou(a, b) -> float:
    a, b = np.array(a, np.float32), np.array(b, np.float32)
    inter, _ = cv2.intersectConvexConvex(a, b)
    u = cv2.contourArea(a) + cv2.contourArea(b) - inter
    return float(inter / u) if u > 0 else 0.0


def match(labels: list, dets: list) -> list[tuple[int, int, float]]:
    pairs = []
    for i, L in enumerate(labels):
        lc = np.mean(L["pts"], axis=0)
        r = max(L["rect"][1])
        for j, D in enumerate(dets):
            if np.hypot(*(np.mean(D["pts2992"], axis=0) - lc)) > 1.5 * r:
                continue
            v = piou(L["pts"], D["pts2992"])
            if v >= MATCH_IOU:
                pairs.append((v, i, j))
    pairs.sort(reverse=True)
    ui, uj, out = set(), set(), []
    for v, i, j in pairs:
        if i in ui or j in uj:
            continue
        ui.add(i)
        uj.add(j)
        out.append((i, j, v))
    return out


def relabel():
    """--relabel: 검출을 다시 돌리지 않고, 지난 결과(labels_*.json)의 맞은 상자에 지금 final 의 역할·주인을 다시 옮기고 role_use 가 아닌 그림을 뺀다.
    상자(위치·종류)가 바뀌지 않았을 때만 쓴다 — 상자가 바뀐 그림이 있으면 멈춘다. counts.json 은 상자 기준이라 그대로."""
    fin = {}
    for p in sorted((DR / "final").glob("r*.json")):
        for im in json.loads(p.read_text(encoding="utf-8"))["images"]:
            fin[im["id"]] = im
    ch = Counter()
    for q in QS:
        for sp in ("train", "dev"):
            f = OUT / q / f"labels_{sp}.json"
            d = json.loads(f.read_text(encoding="utf-8"))
            keep = []
            for im in d["images"]:
                F = fin[im["id"]]
                if not F["role_use"]:
                    ch[f"{q}_dropped_image"] += 1
                    continue
                lab = {str(b["id"]): b for b in F["boxes"]}
                for it in im["items"]:
                    L = lab.get(str(it["label_id"]))
                    if L is None or L["cls"] != "face":
                        raise SystemExit(f"상자가 바뀐 그림: {im['id']} {it['label_id']} — 검출부터 다시 돌릴 것")
                    if (it["role"], it["seat"]) != (L["role"], L["seat"]):
                        ch[f"{q}_relabeled"] += 1
                    it["role"], it["seat"] = L["role"], L["seat"]
                im["phase"], im["winner"], im["winner_src"] = F["phase"], F["winner"], F["winner_src"]
                keep.append(im)
            d["images"] = keep
            f.write_text(json.dumps(d, ensure_ascii=False, indent=0), encoding="utf-8")
    print(dict(ch))


def main():
    if "--relabel" in sys.argv:
        return relabel()
    t0 = time.time()
    man = json.loads((V / "manifest.json").read_text(encoding="utf-8"))
    scale = man["rules"]["scale"]
    rd = lr.LocalReader(threads=4)
    rd._sessions()
    # 검출 저장(_dets.json). 없으면 지난 labels_*.json 의 상자(맞은 앞면·뒷면 + unmatched = 그 그림 검출 전부)에서 되살린다.
    cache_p = OUT / "_dets.json"
    cache: dict = json.loads(cache_p.read_text(encoding="utf-8")) if cache_p.exists() else {}
    keys = ("cls", "box", "pts", "pts2992", "score")
    for q in QS:
        for sp in ("train", "dev"):
            f = OUT / q / f"labels_{sp}.json"
            if not f.exists():
                continue
            for im in json.loads(f.read_text(encoding="utf-8"))["images"]:
                k = f"{q}|{im['id']}"
                if k not in cache:
                    cache[k] = {"size": im["size"], "dets": [{x: e.get(x) for x in keys} for e in im["items"] + im["backs"] + im["unmatched"]], "from": "labels"}
    stat = Counter()
    files = {q: {"train": [], "dev": []} for q in QS}
    cnt = Counter()
    nimg = Counter()
    for p in sorted((DR / "final").glob("r*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        for im in d["images"]:
            sp = im["split_final"]
            for q in QS:
                s = scale[q]
                key = f"{q}|{im['id']}"
                if key in cache:  # 저장된 검출(검출기는 결정적이라 다시 돌린 것과 같다)
                    Wq, Hq = cache[key]["size"]
                    dets = cache[key]["dets"]
                    stat["cached"] += 1
                else:
                    rgb = lr.decode_rgb((V / im["paths"][q]).read_bytes())
                    Hq, Wq = rgb.shape[:2]
                    faces, backs, _, sc = rd._seat_raw(rgb)
                    dets = []
                    for c, res in ((0, faces), (1, backs)):
                        for bb, rc in res:
                            pts = obb.corners(rc)
                            dets.append({"cls": "face" if c == 0 else "back", "box": [int(v) for v in bb], "pts": [[round(float(x), 1), round(float(y), 1)] for x, y in pts],
                                         "pts2992": [[round(float(x) / s, 1), round(float(y) / s, 1)] for x, y in pts], "score": sc.get(bb) if c == 0 else None})
                    cache[key] = {"size": [Wq, Hq], "dets": dets}
                    stat["ran"] += 1
                items, bk, unmatched, missed = [], [], [], {"face": [], "back": []}
                for cls in ("face", "back"):
                    L = [b for b in im["boxes"] if b["cls"] == cls]
                    D = [x for x in dets if x["cls"] == cls]
                    m = match(L, D)
                    mi = {i for i, _, _ in m}
                    mj = {j for _, j, _ in m}
                    for i, j, v in m:
                        e = dict(D[j], label_id=L[i]["id"], iou=round(v, 3))
                        if cls == "face":
                            e.update(role=L[i]["role"], seat=L[i]["seat"])
                            items.append(e)
                        else:
                            bk.append(e)
                    unmatched += [D[j] for j in range(len(D)) if j not in mj]
                    missed[cls] = [L[i]["id"] for i in range(len(L)) if i not in mi]
                    if im["det_use"]:
                        cnt[(q, sp, cls, "labels")] += len(L)
                        cnt[(q, sp, cls, "detected")] += len(m)
                        cnt[(q, sp, cls, "false_pos")] += len(D) - len(m)
                        cnt[(q, sp, cls, "dets")] += len(D)
                if im["det_use"]:
                    nimg[(q, sp)] += 1
                if im["role_use"]:
                    files[q][sp].append({"id": im["id"], "kind": im["kind"], "phase": im["phase"], "scene_round": im["scene_round"], "winner": im["winner"],
                                         "winner_src": im["winner_src"], "size": [Wq, Hq], "scale": s, "grid_est": im["grid_est"],
                                         "device": {k: (round(v * s, 1) if k in ("cx", "cy", "hd") else v) for k, v in im["device"].items() if k in ("cx", "cy", "hd", "src")},
                                         "items": items, "backs": bk, "unmatched": unmatched,
                                         "missed": {"face": len(missed["face"]), "back": len(missed["back"]), "face_ids": missed["face"], "back_ids": missed["back"]}})
            print(im["id"], flush=True)
    cache_p.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    print("검출 저장에서", stat["cached"], "새로 돌림", stat["ran"])
    for q in QS:
        (OUT / q).mkdir(parents=True, exist_ok=True)
        for sp in ("train", "dev"):
            (OUT / q / f"labels_{sp}.json").write_text(json.dumps({"_note": f"{q} 그림 운영 검출 상자에 최종 라벨 역할·주인을 옮김(v1114_dr_detinput.py). box·pts = {q} 좌표, pts2992 = 원본 좌표.",
                                                                  "images": files[q][sp]}, ensure_ascii=False, indent=0), encoding="utf-8")
    res = {}
    for q in QS:
        for sp in ("train", "dev"):
            r = {"images": nimg[(q, sp)]}
            for cls in ("face", "back"):
                lab, det, fp = cnt[(q, sp, cls, "labels")], cnt[(q, sp, cls, "detected")], cnt[(q, sp, cls, "false_pos")]
                r[cls] = {"labels": lab, "detected": det, "missed": lab - det, "false_pos": fp, "dets": cnt[(q, sp, cls, "dets")],
                          "recall": round(det / lab, 4) if lab else None, "precision": round(det / (det + fp), 4) if det + fp else None}
            res.setdefault(q, {})[sp] = r
    cond = {"model": str(Path(rd.seat_model).name), "model_path": str(rd.seat_model),
            "path": "lr.decode_rgb(JPEG) → LocalReader._seat_raw(전체 프레임 1회, 조각 없음) — 겹쳐 보기 reader.detect_full 과 같은 검출",
            "input": f"긴 변 {lr.IMG} 레터박스(짧은 변 32 배수, 패딩 114), BILINEAR 축소", "conf": obb.CONF, "nms_iou_axis": obb.IOU,
            "slivers": "앞면만 obb.slivers", "kan_pairs": "따로 안 더함", "match": f"같은 종류, 회전 상자 다각형 IoU ≥ {MATCH_IOU}, 욕심 1:1",
            "label": "data/v1114/dr/final(2단계 눈 확인 반영 최종 라벨), 2992 좌표 — 검출 좌표 ÷ scale 로 맞댐",
            "images": "검출 세트 그림(det_use: 흔들림·탁자 아님 2장 뺌) 학습 141 · 개발 46 = 187장, 세 화질 같은 그림",
            "qualities": man["rules"]["qualities"], "scale": scale, "onnx_threads": 4, "sec": round(time.time() - t0, 1),
            "dets_source": f"저장된 검출 {stat['cached']}건(첫 실행 11-15 의 결과를 labels_*.json·_dets.json 에서 되살림) + 이번에 돌린 {stat['ran']}건 — 검출기는 결정적이라 다시 돌린 것과 같음",
            "label_version": "최종(2단계 + 독립 검토 반영 + 보충 addbox 5개 + 계획 세션 역할 고침, final_overrides 반영)"}
    (OUT / "counts.json").write_text(json.dumps({"conditions": cond, "counts": res}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
