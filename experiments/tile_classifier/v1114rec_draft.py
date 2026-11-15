"""녹화 프레임(rec1496) 121장의 라벨 초안 — 검출(앞면·뒷면)·패 종류·역할/주인(2026-11-15, 녹화 세트 2단계 2). v1114rec_manifest.py 다음에.

좌표: 출력은 모두 녹화 원래 좌표(1496). 기존 초안 파이프라인(v1114_dr_draft: 전체 검출 + 네 조각 검출, 뒷면 색, 기하 규칙, 역할 모델)은 2992 그림에
  맞춰 있어서(조각 겹침 60px·펠트 찾는 축소 748·라플라시안 선명도·카메라 밀림 범위 400px 등이 2992 px 값), 녹화 프레임을 2배(BICUBIC)로 키워
  그 함수들을 그대로 돌리고 좌표를 ÷2 한다. 안쪽 계산(실물 패 잇기·이웃 맞대기 포함)은 모두 2992 공간에서 하고 쓸 때만 ÷2.
  (검출기는 어차피 긴 변 1280 으로 줄여 넣으므로 전체 검출은 1496 원본과 거의 같다. 네 조각 검출은 조각 1556px → 1280 이라 2배가 원래 의미 그대로.)
검출 = v1114_dr_draft 와 같은 규칙. 앞면 = 전체 검출 앞면(안깡 뒷면 상자는 처음부터 없음 — _seat_raw 앞면) + 네 조각에서만 나온 앞면(흰 비율 거르기, src quad).
  뒷면 = 전체 + 네 조각 뒷면 합침, 남긴 앞면과 면적 40% 넘게 겹친 뒷면 버림. 기존과 달리 분류기 세트 눈 확인(not_tile)이 아직 없어서 지운 초안 상자(drop)는 없다.
  격자 안 씀. 펠트·기기는 그림에서 직접(v1114_dr_draft.felt_quad·find_device).
패 종류 = v1114_draft 와 같은 방식: 운영 분류기, 회전 상자로 세운 크롭(PAD 0.12), 상자 모양에 맞는 방향 후보 중 확신 최대. 크롭은 녹화 원래 그림(1496)에서
  자르고 긴 변 96 미만이면 96 으로 BICUBIC 키워 읽는다(서버 read_small 과 같은 키워 읽기). 참고로 2배 그림 크롭 읽기도 t_x2 로 남긴다(투표에는 안 씀).
  실물 패 = 같은 판 그림(같은 part 끼리, 시간순)을 v1114_draft.link 로 잇기(카메라 밀림·크기 바뀜·큰 밀림 끊기 그대로) → 확신도 합 투표, SPLIT·LOW 표시.
  나(mid)는 더해서: 앞·뒤 이웃(기존 세트 최종 라벨 data/v1114/dr/final, 2992 좌표)과 카메라 밀림(v1114_draft.shift_between, 앞면+뒷면 중심)을 뺀 뒤
    중심 거리 < 패 짧은 변 × 0.5 인 이웃 앞면에 욕심 매칭(가까운 쌍부터, 하나씩) → 상자에 nb {prev, next}(이웃 종류·역할·주인·거리).
    이웃 그림이 기존 세트에서 흔들림·탁자 아님(det_use false)이면 그 이웃은 안 쓴다, 역할은 role_use false 면 안 옮긴다.
    상자 nb_tile = 앞·뒤가 같으면 그 값(from both), 한쪽만 있으면 그쪽, 둘이 다르면 분류기 읽기와 같은 쪽(없으면 앞) + 표시 nb_conflict.
    실물 패 초안 = 이웃 라벨이 붙은 상자가 있으면 그 nb_tile 다수결(draft_src nb), 없으면 분류기 투표(draft_src cls).
    NB? = 실물 패의 상자 중 분류기 1순위 ≠ nb_tile 인 것이 있거나, 앞·뒤 이웃 종류가 갈림.
    역할·주인도 같은 식: nb_role·nb_seat(앞·뒤 같으면 그 값, 다르면 앞, 표시 nb_role_conflict). role_draft = 이웃 값이 있으면 그것, 없으면 규칙.
    규칙 답과 이웃이 다르면 split 에 "nb" 를 더한다.
  다(new)는 이웃이 없어 분류기 투표뿐(같은 판 9장 사이 잇기는 함).
역할·주인 = v1114_dr_draft.rule_roles(기하 규칙) + Models(운영 v3r15d 네 자리 + _pick_role, 주인 = 실험 모델 D). 공개 장면(다의 phase end)은
  화료 사진처럼 다룬다: 화료자 = rounds.json 메모의 "… 자리 공개"(winner_src rounds_note, 없으면 가장 긴 앞면 줄 쪽 guess_longest_hand),
  규칙은 화료자 쪽 손패·짝·떼어 둔 패를 보고(rule_roles winner, 펠트 꼭짓점), 모델은 화료자 기준 1회. format = end. 나머지는 format frame.
그림 단위 표시 짐작(v1114_dr_draft 와 같은 기준, 선명도 중앙값은 이 121장 안에서 — 2배 키운 그림이라 기존 189장 값과 비교 못 함): not_table·blur·occluded.
  python -X utf8 experiments/tile_classifier/v1114rec_draft.py [판 id ...]
결과 data/v1114rec/draft/<판>.json(패 종류 초안, v1114 draft 꼴) · data/v1114rec/dr/draft/<판>.json(검출·역할 초안, v1114 dr/draft 꼴)
     · data/v1114rec/draft/_summary.json(수 세기). 판 id 를 주면 그 판만(요약은 안 씀).
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REC = Path(r"C:\Users\jjh7757\dev\mahjong-recognizer")
sys.path.insert(0, str(REC))
from app import local_read as lr  # noqa: E402
from app import obb, roles  # noqa: E402

sys.path.insert(0, str(HERE))
import v1114_dr_draft as DD  # noqa: E402
import v1114_draft as TD  # noqa: E402
from det_backs import skin_mask  # noqa: E402

R = HERE / "data" / "v1114rec"
V = HERE / "data" / "v1114"
UP = 2  # 녹화 1496 → 2992
OUT_T = R / "draft"
OUT_D = R / "dr" / "draft"


# ------------------------------------------------------------------ 좌표 ÷2
def half_rect(rc) -> list:
    return [[round(float(rc[0][0]) / UP, 1), round(float(rc[0][1]) / UP, 1)], [round(float(rc[1][0]) / UP, 1), round(float(rc[1][1]) / UP, 1)], round(float(rc[2]), 2)]


def half_box(b) -> list:
    return [int(round(b[0] / UP)), int(round(b[1] / UP)), max(1, int(round(b[2] / UP))), max(1, int(round(b[3] / UP)))]


def half_pt(p) -> list:
    return [round(float(p[0]) / UP, 1), round(float(p[1]) / UP, 1)]


# ------------------------------------------------------------------ 분류
def read_faces(reader: lr.LocalReader, nat: np.ndarray, big: np.ndarray, faces: list) -> None:
    """faces(2992 공간 rect)마다 1496 원본 크롭(96 미만 키워 읽기) 1순위·2순위 + 2배 그림 크롭 1순위(t_x2) 를 채운다."""
    crops, owner, crops2, owner2 = [], [], [], []
    for i, e in enumerate(faces):
        rc = e["rect"]
        h1 = half_rect(rc)
        im = obb.upright(nat, ((h1[0][0], h1[0][1]), (h1[1][0], h1[1][1]), h1[2]), lr.PAD)
        e["crop_long"] = max(im.size)
        if max(im.size) < lr.SMALL_TILE:
            s = lr.SMALL_TILE / max(im.size)
            im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.BICUBIC)
        b = e["box"]
        ts = (0, 2) if b[3] > 1.15 * b[2] else (1, 3) if b[2] > 1.15 * b[3] else (0, 1, 2, 3)
        e["sharp_c"] = round(TD.sharp(im), 1)
        im2 = obb.upright(big, ((rc[0][0], rc[0][1]), (rc[1][0], rc[1][1]), rc[2]), lr.PAD)
        for k in ts:
            crops.append(im.rotate(90 * k, expand=True))
            owner.append((i, k))
            crops2.append(im2.rotate(90 * k, expand=True))
            owner2.append((i, k))
    for cs, ow, key in ((crops, owner, ""), (crops2, owner2, "_x2")):
        best: dict = {}
        for s in range(0, len(cs), 64):
            p = reader.probs(cs[s:s + 64])
            for j, row in enumerate(p):
                i, k = ow[s + j]
                if i not in best or row.max() > best[i][0].max():
                    best[i] = (row, k)
        for i, (row, k) in best.items():
            t, c, t2, c2 = lr.top2(row)
            if key == "":
                faces[i].update(t=t, c=c, t2=t2, c2=c2, rot=k)
            else:
                faces[i].update(t_x2=t, c_x2=c)


# ------------------------------------------------------------------ 이웃(기존 세트 최종 라벨)
class Finals:
    def __init__(self):
        self.cache = {}

    def image(self, img_id: str) -> dict | None:
        rid = img_id.split("/")[0]
        if rid not in self.cache:
            p = V / "dr" / "final" / f"{rid}.json"
            self.cache[rid] = {im["id"]: im for im in json.loads(p.read_text(encoding="utf-8"))["images"]} if p.exists() else {}
        return self.cache[rid].get(img_id)


def match_neighbor(faces: list, backs: list, nb: dict) -> dict:
    """이웃 최종 라벨(2992)과 이 그림 상자(2992) 맞대기: 카메라 밀림을 빼고 앞면끼리 욕심 매칭. {face index: (nb box, 거리)}, 밀림."""
    nbb = [b for b in nb["boxes"]]
    nf = [b for b in nbb if b["cls"] == "face"]
    if not faces or not nf:
        return {"pairs": {}, "shift": [0.0, 0.0, 0]}
    cur = np.array([DD.cen(e["box"]) for e in faces + backs])
    prev = np.array([DD.cen(b["box"]) for b in nbb])
    tile = float(np.median([min(e["box"][2], e["box"][3]) for e in faces]))
    dx, dy, sup = TD.shift_between(prev, cur, tile)
    cand = []
    for i, e in enumerate(faces):
        cx, cy = DD.cen(e["box"])
        lim = TD.LINK * min(e["box"][2], e["box"][3])
        for j, b in enumerate(nf):
            bx, by = DD.cen(b["box"])
            d = float(np.hypot(cx - dx - bx, cy - dy - by))
            if d < lim:
                cand.append((d, i, j))
    cand.sort()
    ub, un, pairs = set(), set(), {}
    for d, i, j in cand:
        if i in ub or j in un:
            continue
        ub.add(i)
        un.add(j)
        pairs[i] = (nf[j], round(d, 1))
    return {"pairs": pairs, "shift": [round(dx, 1), round(dy, 1), sup]}


def neighbor_labels(it: dict, faces: list, backs: list, finals: Finals) -> dict:
    info = {}
    for side in ("prev", "next"):
        nid = it.get(f"{side}_id")
        nim = finals.image(nid) if nid else None
        if nim is None:
            info[side] = {"id": nid, "used": False, "why": "최종 라벨에 그림 없음"}
            continue
        if not nim.get("det_use", True):
            info[side] = {"id": nid, "used": False, "why": f"기존 세트에서 검출 제외({nim.get('excluded_why')})"}
            continue
        m = match_neighbor(faces, backs, nim)
        role_ok = bool(nim.get("role_use", True))
        for i, (b, d) in m["pairs"].items():
            faces[i].setdefault("nb", {})[side] = {"id": b["id"], "tile": b.get("tile"), "role": b.get("role") if role_ok else None,
                                                   "seat": b.get("seat") if role_ok else None, "dist": round(d / UP, 1)}
        info[side] = {"id": nid, "used": True, "role_used": role_ok, "matched": len(m["pairs"]),
                      "nb_faces": sum(1 for b in nim["boxes"] if b["cls"] == "face"), "shift_1496": [round(m["shift"][0] / UP, 1), round(m["shift"][1] / UP, 1), m["shift"][2]],
                      "phase": nim.get("phase"), "flags": nim.get("flags")}
    # 상자별 합치기
    for e in faces:
        nb = e.get("nb")
        if not nb:
            continue
        ts = {s: v["tile"] for s, v in nb.items() if v.get("tile")}
        if ts:
            vals = set(ts.values())
            if len(vals) == 1:
                e["nb_tile"], e["nb_from"] = next(iter(vals)), "both" if len(ts) == 2 else next(iter(ts))
            else:
                e["nb_conflict"] = True
                pick = next((s for s in ("prev", "next") if ts[s] == e.get("t")), "prev")
                e["nb_tile"], e["nb_from"] = ts[pick], pick
        rs = {s: (v["role"], v["seat"]) for s, v in nb.items() if v.get("role")}
        if rs:
            vals = set(rs.values())
            if len(vals) == 1:
                (e["nb_role"], e["nb_seat"]), e["nb_role_from"] = next(iter(vals)), "both" if len(rs) == 2 else next(iter(rs))
            else:
                e["nb_role_conflict"] = True
                s = "prev" if "prev" in rs else "next"
                (e["nb_role"], e["nb_seat"]), e["nb_role_from"] = rs[s], s
    return info


# ------------------------------------------------------------------ 한 그림
def draft_image(it: dict, rd: lr.LocalReader, md: DD.Models) -> dict:
    nat = np.asarray(Image.open(R / it["path"]).convert("RGB"))
    H1, W1 = nat.shape[:2]
    big = np.asarray(Image.fromarray(nat).resize((W1 * UP, H1 * UP), Image.BICUBIC))
    H, W = big.shape[:2]
    hsv = np.asarray(Image.fromarray(big).convert("HSV"))
    felt = DD.felt_quad(big)
    dev = DD.find_device(big, felt)
    grid = DD.grid_of(felt, dev, W, H)
    det = DD.detect_all(rd, big)
    faces = [{"cls": "face", "box": [int(v) for v in bb], "rect": DD.rect_list(rc), "src": "full", "det": None if sc is None else round(float(sc), 3), "flags": []}
             for bb, rc, sc in det["full_faces"]]
    n_white = 0
    allf = [e["box"] for e in faces]
    for bb, rc, sc in det["quad_faces"]:
        if any(DD.same_place(bb, o) for o in allf):
            continue
        ok, wf = DD.white_ok(hsv, bb)
        if not ok:
            n_white += 1
            continue
        allf.append(bb)
        faces.append({"cls": "face", "box": [int(v) for v in bb], "rect": DD.rect_list(rc), "src": "quad", "det": None if sc is None else round(float(sc), 3),
                      "flags": ["new: 조각 검출에서만 나옴"], "white": wf})
    backs: list = []
    for bb, rc in det["full_backs"] + det["quad_backs"]:
        if any(DD.same_place(bb, o["box"]) for o in backs):
            continue
        backs.append({"cls": "back", "box": [int(v) for v in bb], "rect": DD.rect_list(rc), "src": "det", "flags": []})
    kept, n_bof = [], 0
    for b in backs:
        a = b["box"][2] * b["box"][3]
        if any(DD.inter(b["box"], f["box"]) > DD.BACK_ON_FACE * a for f in faces):
            n_bof += 1
            continue
        kept.append(b)
    backs = kept
    tile = float(np.median([min(e["box"][2], e["box"][3]) for e in faces])) if faces else 80.0
    key = lambda e: (int(DD.cen(e["box"])[1] // max(8, tile / 2)), DD.cen(e["box"])[0])
    faces.sort(key=key)
    backs.sort(key=key)
    for k, e in enumerate(faces + backs):
        e["id"] = k
        e["status"] = "keep"
        e["pts"] = DD.corners(e["rect"])
    read_faces(rd, nat, big, faces)
    # 화료자(공개 장면만)
    end = it["part"] == "new" and it.get("phase") == "end"
    winner, wsrc = None, None
    fb, bb_ = [e["box"] for e in faces], [e["box"] for e in backs]
    devt = (dev["cx"], dev["cy"], dev["hd"])
    if end:
        if it.get("winner_hint"):
            winner, wsrc = it["winner_hint"], "rounds_note"
        elif faces:
            hs = Counter(s for (ro, s, _) in DD.rule_roles(fb, bb_, devt, None) if ro == "hand")
            if hs:
                winner, wsrc = hs.most_common(1)[0][0], "guess_longest_hand"
    rr = DD.rule_roles(fb, bb_, devt, winner, felt.get("quad") if end else None)
    mm = md.run(fb, [np.array(e["pts"]) for e in faces], [(e["box"], np.array(e["pts"])) for e in backs], grid, W, H, winner if end else None)
    for e, r_, m_ in zip(faces, rr, mm):
        e["rule"] = {"role": r_[0], "seat": r_[1], "why": r_[2]}
        e["model"] = m_
        sp = []
        if m_ is not None:
            if m_["role"] != r_[0]:
                sp.append("role")
            elif r_[0] in DD.OWNED and m_["seat"] and r_[1] != m_["seat"]:
                sp.append("seat")
        e["split"] = sp
    # 그림 단위 짐작(1496 축소 = 원본)
    gray = cv2.cvtColor(nat, cv2.COLOR_RGB2GRAY).astype(np.float32)
    hull_m = np.zeros(gray.shape, np.uint8)
    if felt.get("hull_small"):
        kk = W1 / W / felt["k"]
        cv2.fillPoly(hull_m, [np.round(np.array(felt["hull_small"]) * kk).astype(np.int32)], 1)
    if hull_m.sum() < 1000:
        hull_m[:] = 1
    g_big = cv2.cvtColor(big, cv2.COLOR_RGB2GRAY)
    bs_ = []
    for e in faces + backs:
        x, y, w, h = e["box"]
        cr = g_big[max(0, y):y + h, max(0, x):x + w]
        if cr.shape[0] > 8 and cr.shape[1] > 8:
            e["sharp"] = round(float(cv2.Laplacian(cr, cv2.CV_32F).var()), 1)
            bs_.append(e["sharp"])
    sharp = float(np.median(bs_)) if len(bs_) >= 5 else float(cv2.Laplacian(gray, cv2.CV_32F)[hull_m > 0].var())
    sk = skin_mask(cv2.cvtColor(nat, cv2.COLOR_RGB2BGR))
    skin = float((sk[hull_m > 0] > 0).mean())
    guess = []
    if not felt["ok"]:
        guess.append("not_table")
    if skin > DD.OCC_FRAC:
        guess.append("occluded")
    return {"it": it, "faces": faces, "backs": backs, "felt": felt, "device": dev, "grid": grid, "winner": winner, "winner_src": wsrc, "end": end,
            "guess": guess, "sharp": sharp, "skin": skin, "n_white": n_white, "n_bof": n_bof, "size": [W1, H1]}


# ------------------------------------------------------------------ 판 단위 마무리
def finish_round(rid: str, ims: list, finals: Finals) -> tuple[dict, dict]:
    # 이웃(나만)
    for d in ims:
        d["nb_info"] = neighbor_labels(d["it"], d["faces"], d["backs"], finals) if d["it"]["part"] == "mid" else None
        for e in d["faces"]:
            if e.get("nb_role"):
                e["role_draft"] = {"role": e["nb_role"], "seat": e["nb_seat"], "src": "nb"}
                if (e["nb_role"], e["nb_seat"]) != (e["rule"]["role"], e["rule"]["seat"]):
                    e["split"] = e["split"] + ["nb"]
            else:
                e["role_draft"] = {"role": e["rule"]["role"], "seat": e["rule"]["seat"], "src": "rule"}
    # 실물 패 잇기(2992 공간, 같은 판 안 시간순 — 판은 part 하나뿐)
    wrap = [{"boxes": d["faces"]} for d in ims]
    tracks = TD.link(wrap)
    out_tracks = []
    for t in tracks:
        reads = [ims[k]["faces"][j] for k, j in t["apps"]]
        votes = Counter()
        for b in reads:
            votes[b["t"]] += b["c"]
        cls_draft = max(votes, key=votes.get)
        win_reads = [b["c"] for b in reads if b["t"] == cls_draft]
        tops = Counter(b["t"] for b in reads)
        nbt = Counter(b["nb_tile"] for b in reads if b.get("nb_tile"))
        if nbt:
            draft, src = nbt.most_common(1)[0][0], "nb"
        else:
            draft, src = cls_draft, "cls"
        nb_q = bool(nbt) and (len(nbt) > 1 or any(b.get("nb_conflict") for b in reads) or any(b.get("nb_tile") and b["t"] != b["nb_tile"] for b in reads))
        best_k, best_j = max(t["apps"], key=lambda kj: ims[kj[0]]["faces"][kj[1]].get("sharp_c", 0))
        out_tracks.append({"tid": t["tid"], "draft": draft, "draft_src": src, "cls_draft": cls_draft, "share": round(votes[cls_draft] / sum(votes.values()), 3),
                           "conf": round(float(np.mean(win_reads)), 3), "n": len(reads), "reads": dict(tops), "nb_reads": dict(nbt),
                           "split": len(tops) > 1, "low": float(np.mean(win_reads)) < TD.LOW, "nb_q": nb_q,
                           "first": ims[t["apps"][0][0]]["it"]["id"], "last": ims[t["apps"][-1][0]]["it"]["id"],
                           "best": {"image": ims[best_k]["it"]["id"], "i": ims[best_k]["faces"][best_j]["id"]},
                           "apps": [{"image": ims[k]["it"]["id"], "i": ims[k]["faces"][j]["id"]} for k, j in t["apps"]], "label_mismatch": [],
                           "prev_round_scene": False})
        for b in reads:
            b["tile"], b["tile_src"] = draft, src
    by_tid = {t["tid"]: t for t in out_tracks}
    # ---- 쓰기(÷2)
    t_images, d_images = [], []
    for d, w in zip(ims, wrap):
        it = d["it"]
        tb = []
        for e in d["faces"]:
            tb.append({"i": e["id"], "box": half_box(e["box"]), "rect": half_rect(e["rect"]), "det": e["det"], "src": e["src"], "t": e["t"], "c": e["c"], "t2": e["t2"],
                       "c2": e["c2"], "rot": e["rot"], "t_x2": e.get("t_x2"), "c_x2": e.get("c_x2"), "crop_long": e["crop_long"], "sharp": e.get("sharp_c"),
                       "track": e["track"], "nb_tile": e.get("nb_tile"), "nb_from": e.get("nb_from"), "nb_conflict": bool(e.get("nb_conflict")),
                       "nb_q": bool(e.get("nb_tile") and (e["t"] != e["nb_tile"] or e.get("nb_conflict")))})
        base = {"id": it["id"], "name": Path(it["path"]).name, "part": it["part"], "kind": "frame", "at": it["at"], "ms": it["ms"], "split": it["split"],
                "scene_round": it["scene_round"], "setup": it.get("setup", False), "phase_hint": it.get("phase"), "path": it["path"], "size": d["size"]}
        t_images.append({**base, "boxes": tb, "shift": [round(w["shift"][0] / UP, 1), round(w["shift"][1] / UP, 1), w["shift"][2]],
                         **{k: w[k] for k in ("move_break", "scale_break") if k in w}, "nb_info": d["nb_info"]})
        boxes = []
        for e in d["faces"] + d["backs"]:
            o = {"id": e["id"], "cls": e["cls"], "status": "keep", "box": half_box(e["box"]), "rect": half_rect(e["rect"]), "pts": [half_pt(p) for p in e["pts"]],
                 "src": e["src"], "det": e.get("det"), "flags": e["flags"], "sharp": e.get("sharp")}
            if e["cls"] == "face":
                o.update({"track": e["track"], "tile": e["tile"], "tile_src": e["tile_src"], "read": e["t"], "read_c": e["c"], "white": e.get("white"),
                          "nb_tile": e.get("nb_tile"), "nb_from": e.get("nb_from"), "nb_conflict": bool(e.get("nb_conflict")),
                          "nb_role": e.get("nb_role"), "nb_seat": e.get("nb_seat"), "nb_role_from": e.get("nb_role_from"),
                          "nb_role_conflict": bool(e.get("nb_role_conflict")), "nb": e.get("nb"),
                          "rule": e["rule"], "model": e["model"], "split": e["split"], "role_draft": e["role_draft"]})
            boxes.append(o)
        felt = {k: v for k, v in d["felt"].items() if k not in ("hull_small", "k")}
        if felt.get("quad"):
            felt["quad"] = [half_pt(p) for p in felt["quad"]]
        dv = dict(d["device"])
        for k in ("cx", "cy", "hd", "felt_off"):
            if k in dv:
                dv[k] = round(dv[k] / UP, 1)
        if "felt_pred" in dv:
            dv["felt_pred"] = {k: round(v / UP, 1) for k, v in dv["felt_pred"].items()}
        faces = d["faces"]
        cnt = {"face": len(faces), "back": len(d["backs"]), "dropped_face": 0, "quad_face_added": sum(e["src"] == "quad" for e in faces),
               "quad_face_white_drop": d["n_white"], "back_on_face_drop": d["n_bof"],
               "split_role": sum("role" in e["split"] for e in faces), "split_seat": sum("seat" in e["split"] for e in faces),
               "split_nb": sum("nb" in e["split"] for e in faces), "nb_tile_boxes": sum(bool(e.get("nb_tile")) for e in faces),
               "nb_q_boxes": sum(bool(e.get("nb_tile") and (e["t"] != e["nb_tile"] or e.get("nb_conflict"))) for e in faces),
               "nb_role_boxes": sum(bool(e.get("nb_role")) for e in faces)}
        d_images.append({**base, "format": "end" if d["end"] else "frame", "winner": d["winner"], "winner_src": d["winner_src"], "felt": felt, "device": dv,
                         "grid_est": d["grid"], "flags_guess": d["guess"], "flag_stats": {"sharp_x2": round(d["sharp"], 1), "skin": round(d["skin"], 4),
                                                                                         "felt_area": d["felt"]["area_frac"]},
                         "prev_id": it.get("prev_id"), "next_id": it.get("next_id"), "nb_info": d["nb_info"], "counts": cnt, "label_check": None, "boxes": boxes})
    splits = sorted({d["it"]["split"] for d in ims})
    part = ims[0]["it"]["part"]
    tc = {"images": len(ims), "boxes": sum(len(d["faces"]) for d in ims), "tracks": len(out_tracks), "split_tracks": sum(t["split"] for t in out_tracks),
          "low": sum(t["low"] for t in out_tracks), "nb_q": sum(t["nb_q"] for t in out_tracks), "nb_tracks": sum(t["draft_src"] == "nb" for t in out_tracks),
          "single": sum(t["n"] == 1 for t in out_tracks)}
    note_t = ("패 종류 초안(v1114rec_draft.py). 좌표 = 녹화 1496 원래 픽셀. boxes[].i = dr/draft 상자 번호(앞면). t/c = 1496 크롭(96 미만 키워 읽기) 분류기 1순위, "
              "t_x2 = 2배 그림 크롭 읽기(참고). tracks[].draft = 실물 패 초안(draft_src nb = 이웃 최종 라벨 다수결 / cls = 분류기 투표), cls_draft = 분류기 투표, "
              "nb_q = 분류기와 이웃 라벨이 다르거나 앞·뒤 이웃이 갈림(NB?).")
    tdraft = {"round": rid, "part": part, "split": splits[0] if len(splits) == 1 else "+".join(splits), "splits": splits, "model": None, "low": TD.LOW, "link": TD.LINK,
              "_note": note_t, "counts": tc, "label_checks": [], "tracks": out_tracks, "images": t_images}
    dc = Counter()
    for im in d_images:
        dc.update(im["counts"])
    note_d = ("검출·역할 라벨 초안(v1114rec_draft.py). 좌표 = 녹화 1496 원래 픽셀(2배 키워 v1114_dr_draft 를 돌리고 ÷2). boxes[]: id(그림 안 번호, 확인 그림 글자), "
              "cls face|back, status keep, box [x,y,w,h], rect [[cx,cy],[w,h],각도°], pts, src full(전체 검출)|quad(조각 검출에서만)|det(뒷면), tile(실물 패 초안 종류), "
              "rule(규칙 역할·주인)/model(모델), split(role·seat = 규칙·모델 갈림, nb = 규칙과 이웃 라벨 갈림), role_draft(초안 역할 = 이웃 nb 가 있으면 그것, 없으면 규칙), "
              "nb_*(나 — 기존 세트 앞·뒤 이웃 최종 라벨에서 옮긴 값). format end = 공개 장면(화료자 winner 기준 규칙·모델).")
    ddraft = {"round": rid, "part": part, "split_final": tdraft["split"], "splits": splits, "_note": note_d, "counts": dict(dc), "images": d_images}
    return tdraft, ddraft


def main():
    t_all = time.time()
    man = json.loads((R / "manifest.json").read_text(encoding="utf-8"))
    want = set(sys.argv[1:])
    items = [it for it in man["items"] if it["part"] in ("mid", "new")]
    rids = sorted({it["round"] for it in items})
    OUT_T.mkdir(parents=True, exist_ok=True)
    OUT_D.mkdir(parents=True, exist_ok=True)
    rd = lr.LocalReader(threads=4)
    rd._sessions()
    md = DD.Models()
    finals = Finals()
    per = {}
    for rid in rids:
        if want and rid not in want:
            continue
        t0 = time.time()
        its = sorted([it for it in items if it["round"] == rid], key=lambda it: it["ms"])
        ims = []
        for it in its:
            d = draft_image(it, rd, md)
            ims.append(d)
            print(it["id"], "앞", len(d["faces"]), "뒤", len(d["backs"]), "조각+", sum(e["src"] == "quad" for e in d["faces"]), d["device"]["src"], d["guess"],
                  f"sharp {d['sharp']:.0f} skin {d['skin']:.3f}", flush=True)
        per[rid] = (ims, round(time.time() - t0, 1))
    # 흔들림 짐작: 이 121장 선명도 중앙값 × BLUR_K
    med = float(np.median([d["sharp"] for ims, _ in per.values() for d in ims])) if per else 0.0
    summ = {"made": time.strftime("%Y-%m-%dT%H:%M:%S"), "models": {"det": Path(rd.seat_model).name, "cls": Path(rd.cls_model).name, "role": roles.ROLE_MODEL.name,
                                                                  "role_owner": DD.D_MODEL.name},
            "how": "녹화 1496 → 2배 BICUBIC → v1114_dr_draft 검출·규칙·모델 → 좌표 ÷2. 분류 = 1496 크롭(96 미만 키움).", "sharp_median_x2": round(med, 1), "rounds": {}}
    for rid, (ims, sec) in per.items():
        for d in ims:
            if d["sharp"] < DD.BLUR_K * med:
                d["guess"].append("blur")
        td, ddr = finish_round(rid, ims, finals)
        for im in ddr["images"]:
            im["flag_stats"]["sharp_median_all_x2"] = round(med, 1)
        (OUT_T / f"{rid}.json").write_text(json.dumps(td, ensure_ascii=False, indent=0), encoding="utf-8")
        (OUT_D / f"{rid}.json").write_text(json.dumps(ddr, ensure_ascii=False, indent=0), encoding="utf-8")
        summ["rounds"][rid] = {"part": td["part"], "splits": td["splits"], **td["counts"], "sec": sec}
        print(rid, td["counts"], flush=True)
    if not want:
        summ["sec"] = round(time.time() - t_all, 1)
        (OUT_T / "_summary_run.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
    print("끝", round(time.time() - t_all, 1), "초")


if __name__ == "__main__":
    main()
