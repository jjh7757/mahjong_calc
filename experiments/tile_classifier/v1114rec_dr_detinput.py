"""녹화 프레임(rec1496) 역할 입력 + 검출 수(2026-11-15, 녹화 세트 3단계 5). v1114rec_dr_final*.py 다음에.

v1114_dr_detinput.py 와 같은 방식: 녹화 그림(1496², 키우지 않음)에 운영 검출기 tile-obb-r8.onnx 를 겹쳐 보기와 같은 전체 프레임 경로로 한 번 돌린다
  — lr.decode_rgb(JPEG 바이트) → LocalReader._seat_raw(긴 변 1280 레터박스, 조각 없음, 앞면만 obb.slivers). 안깡 짝은 따로 안 더함.
  검출 좌표는 이미 1496 이라 그대로 최종 라벨(1496)과 맞댄다: 같은 종류, 회전 상자 다각형 IoU ≥ 0.5, 욕심 1:1(v1114_dr_detinput.match 그대로).
흉내 q1496 과 나란히: 기존 data/v1114/role/det_input/_dets.json 의 q1496 검출(같은 검출기, 2992 그림을 2×2 평균한 1496 그림)을 pts2992 × 0.5 로 옮겨
  짝(pair) 그림의 같은 최종 라벨(짝 라벨 = 기존 ×0.5 − occluded + overrides)과 맞댄다 → 같은 순간·같은 라벨에서 흉내 vs 녹화.
  (참고로 기존 counts.json 의 q1496 수 = 기존 2992 라벨 전체 187장 기준도 같이 옮겨 적는다.)
결과:
  role/det_input/rec1496/labels_{train,dev}.json  역할 세트 그림(role_use)만, 그림마다 part·items(맞은 앞면 검출: box·pts·score·label_id·iou·role·seat)·
     backs·unmatched·missed — v1114 det_input 꼴(좌표 하나뿐이라 pts2992 대신 pts).
  role/det_input/_dets.json  녹화 검출 저장(다시 돌릴 때 씀 — 검출기는 결정적).
  role/det_input/counts.json  검출 세트 그림(det_use) 기준: part(pair/mid/new) × split × 종류별 라벨·맞음·놓침·헛검출, 그리고 pair 의 흉내 q1496 같은 수.
  ※ 한계: mid·new 라벨 초안은 "녹화를 2배 키운 그림 + 같은 검출기(전체 + 네 조각)" 에서 나왔다 — 그 검출기가 못 잡은 패는 눈 확인에서 더한 것만 있으므로
    mid·new 의 놓침 수는 낮게(재현율은 높게) 나올 수 있다. pair 라벨은 2992 원본 초안 + 눈 확인이라 이 영향이 덜하다.
  python -X utf8 experiments/tile_classifier/v1114rec_dr_detinput.py
"""
from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from v1114rec_dr_common import PARTS, Q, R, V, final_all, jload, jsave  # noqa: E402
from v1114_dr_detinput import match  # noqa: E402

sys.path.insert(0, r"C:\Users\jjh7757\dev\mahjong-recognizer")
from app import local_read as lr  # noqa: E402
from app import obb  # noqa: E402

OUT = R / "role" / "det_input"


def as_match(dets: list) -> list:
    """match() 는 검출의 pts2992 칸을 본다 — 여기 좌표(1496)를 그 칸에 넣어 그대로 쓴다."""
    return [dict(x, pts2992=x["pts"]) for x in dets]


def tally(cnt, key, im, dets):
    res = {"items": [], "backs": [], "unmatched": [], "missed": {}}
    for cls in ("face", "back"):
        L = [b for b in im["boxes"] if b["cls"] == cls]
        D = as_match([x for x in dets if x["cls"] == cls])
        m = match(L, D)
        mj = {j for _, j, _ in m}
        mi = {i for i, _, _ in m}
        for i, j, v in m:
            e = {k: D[j][k] for k in ("cls", "box", "pts", "score")} | {"label_id": L[i]["id"], "iou": round(v, 3)}
            if cls == "face":
                e.update(role=L[i]["role"], seat=L[i]["seat"])
                res["items"].append(e)
            else:
                res["backs"].append(e)
        res["unmatched"] += [{k: D[j][k] for k in ("cls", "box", "pts", "score")} for j in range(len(D)) if j not in mj]
        res["missed"][cls] = len(L) - len(m)
        res["missed"][f"{cls}_ids"] = [L[i]["id"] for i in range(len(L)) if i not in mi]
        if im["det_use"]:
            cnt[key + (cls, "labels")] += len(L)
            cnt[key + (cls, "detected")] += len(m)
            cnt[key + (cls, "false_pos")] += len(D) - len(m)
    return res


def table(cnt, nimg, keys) -> dict:
    out = {}
    for key in keys:
        r = {"images": nimg[key]}
        for cls in ("face", "back"):
            lab, det, fp = cnt[key + (cls, "labels")], cnt[key + (cls, "detected")], cnt[key + (cls, "false_pos")]
            r[cls] = {"labels": lab, "detected": det, "missed": lab - det, "false_pos": fp,
                      "recall": round(det / lab, 4) if lab else None, "precision": round(det / (det + fp), 4) if det + fp else None}
        out["|".join(key)] = r
    return out


def main():
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    cache_p = OUT / "_dets.json"
    cache = jload(cache_p) if cache_p.exists() else {}
    rd = lr.LocalReader(threads=4)
    rd._sessions()
    old = jload(V / "role" / "det_input" / "_dets.json")
    files = {"train": [], "dev": []}
    cnt, nimg, stat = Counter(), Counter(), Counter()
    for im in final_all():
        sp, part = im["split_final"], im["part"]
        if im["id"] in cache:
            dets = cache[im["id"]]["dets"]
            stat["cached"] += 1
        else:
            rgb = lr.decode_rgb((R / im["path"]).read_bytes())
            assert rgb.shape[:2] == (1496, 1496), im["id"]
            faces, backs, _, sc = rd._seat_raw(rgb)
            dets = []
            for c, res in ((0, faces), (1, backs)):
                for bb, rc in res:
                    pts = obb.corners(rc)
                    dets.append({"cls": "face" if c == 0 else "back", "box": [int(v) for v in bb],
                                 "pts": [[round(float(x), 1), round(float(y), 1)] for x, y in pts], "score": sc.get(bb) if c == 0 else None})
            cache[im["id"]] = {"size": [1496, 1496], "dets": dets}
            stat["ran"] += 1
        r = tally(cnt, (Q, part, sp), im, dets)
        if im["det_use"]:
            nimg[(Q, part, sp)] += 1
            nimg[(Q, "all", sp)] += 1
        # 전체 합(all) 도 같이
        if im["det_use"]:
            for cls in ("face", "back"):
                L = sum(b["cls"] == cls for b in im["boxes"])
                det = len(r["items"]) if cls == "face" else len(r["backs"])
                fp = sum(u["cls"] == cls for u in r["unmatched"])
                cnt[(Q, "all", sp, cls, "labels")] += L
                cnt[(Q, "all", sp, cls, "detected")] += det
                cnt[(Q, "all", sp, cls, "false_pos")] += fp
        # 흉내 q1496(짝만)
        if part == "pair":
            ok = old.get(f"q1496|{im['id']}")
            if ok is not None:
                dq = [{"cls": x["cls"], "box": x["box"], "pts": [[p[0] * 0.5, p[1] * 0.5] for p in x["pts2992"]], "score": x.get("score")} for x in ok["dets"]]
                tally(cnt, ("q1496_sim", "pair", sp), im, dq)
                if im["det_use"]:
                    nimg[("q1496_sim", "pair", sp)] += 1
            else:
                stat["q1496_missing"] += 1
        if im["role_use"]:
            files[sp].append({"id": im["id"], "part": part, "kind": im["kind"], "format": im["format"], "phase": im["phase"], "scene_round": im["scene_round"],
                              "winner": im["winner"], "winner_src": im["winner_src"], "size": [1496, 1496], "grid_est": im["grid_est"],
                              "device": {k: im["device"][k] for k in ("cx", "cy", "hd", "src") if k in im["device"]}, **r})
    jsave(cache_p, cache, indent=None)
    for sp in ("train", "dev"):
        jsave(OUT / Q / f"labels_{sp}.json", {"_note": "녹화 rec1496 그림 운영 검출 상자에 최종 라벨 역할·주인을 옮김(v1114rec_dr_detinput.py). 좌표 = 1496.",
                                              "images": files[sp]}, indent=0)
    keys = [(Q, p, s) for p in PARTS + ("all",) for s in ("train", "dev")] + [("q1496_sim", "pair", s) for s in ("train", "dev")]
    res = table(cnt, nimg, keys)
    oldc = jload(V / "role" / "det_input" / "counts.json")
    cond = {"model": Path(rd.seat_model).name, "model_path": str(rd.seat_model),
            "path": "lr.decode_rgb(JPEG) → LocalReader._seat_raw(전체 프레임 1회, 조각 없음, 녹화 1496 그대로 — 키우지 않음)",
            "input": f"긴 변 {lr.IMG} 레터박스", "conf": obb.CONF, "nms_iou_axis": obb.IOU, "slivers": "앞면만 obb.slivers", "kan_pairs": "따로 안 더함",
            "match": "같은 종류, 회전 상자 다각형 IoU ≥ 0.5, 욕심 1:1(v1114_dr_detinput.match)",
            "label": "data/v1114rec/dr/final(mid·new) + final_pair(pair), 1496 좌표",
            "images": "검출 세트 그림(det_use)", "q1496_sim": "pair 만: 기존 _dets.json 의 q1496 검출(pts2992 × 0.5)을 같은 짝 라벨과 맞댐 — 같은 순간·같은 라벨에서 흉내 vs 녹화",
            "limit": "mid·new 라벨 초안은 녹화를 2배 키운 그림에 같은 검출기(전체 + 네 조각)를 돌린 것 — 검출기가 못 잡은 패는 눈 확인에서 더한 것만 있어 "
                     "mid·new 의 놓침은 낮게 나올 수 있다(pair 라벨은 2992 원본 초안 기반).",
            "dets_source": f"저장 {stat['cached']} + 이번에 돌림 {stat['ran']}", "q1496_missing": stat["q1496_missing"], "sec": round(time.time() - t0, 1)}
    jsave(OUT / "counts.json", {"conditions": cond, "counts": res,
                                "v1114_q1496_all187": {"_note": "기존 data/v1114/role/det_input/counts.json 의 q1496(흉내, 기존 2992 라벨 ×0.5, 187장)", **oldc["counts"]["q1496"]}})
    import json
    for k, v in res.items():
        print(k, json.dumps(v, ensure_ascii=False))
    print(cond["dets_source"], cond["sec"])


if __name__ == "__main__":
    main()
