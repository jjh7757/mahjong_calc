"""검출·역할 2단계 눈 확인 도우미(2026-11-15, 검출·역할 세트 1단계 C). review/<판>.json 을 이 도구로 고친다(손으로 고쳐도 됨, 꼴은 review/_FORMAT.json).

명령(그림 id = draft 의 images[].id, 예 r01_112804/win_114614. 좌표 = 2992 원본 픽셀, 확인 그림 가장자리 눈금):
  add     <그림> <x> <y> face|back [--role R --seat S] [--note 글]   놓친 패: (x, y) 둘레 패 덩어리에 회전 상자를 맞춰 더함(id a1, a2 …)
  refit   <그림> <번호> [x y]                                      상자를 다시 맞춤(점을 주면 그 둘레, 없으면 지금 상자 가운데)
  drop    <그림> <번호> [--note 글]                                상자 지움(패 아님·두 번 잡힘 등). 더한 상자(aN)면 목록에서 뺌
  restore <그림> <번호>                                            지운 초안 앞면(회색 점선 x)을 되살림 — 앞면으로
  flip    <그림> <번호>                                            앞면 ↔ 뒷면
  addbox  <그림> cx cy w h 각도 face|back [--role R --seat S] [--note 글]
                                                                   회전 상자를 그대로 넣음(마스크 맞춤 없음, fit=manual) — 손에 들린·손가락에 가린 패처럼
                                                                   add 가 엉뚱하게 맞출 때. cx cy = 패 가운데, w h = 변 길이, 각도 = cv2 minAreaRect 꼴(°)
  nudge   <그림> <번호> dx dy [dw dh d각도]                         상자(더한 aN 이든 초안 번호든)를 조금씩 옮기고 크기·각도 고침(초안 상자는 refit 고침으로 남음)
  near    <그림> x y [반지름=400]                                   (x, y) 둘레 상자 목록: 번호·종류·거리·중심·크기·각도(addbox 크기·각도 참고용, 고치지 않음)
  role    <그림> <번호> <역할> <자리|->                             역할·주인 고침. 역할 hand meld river wall pair loose other, 자리 bottom right top left 또는 -
  ok      <그림> <번호>                                            고침 하나를 지움(초안으로 되돌림)
  flag    <그림> normal | blur occluded not_table …                그림 단위 표시(normal = 정상, 여럿 가능)
  note    <그림> <글>                                              그림 메모(덧붙임)
  seen    <그림>                                                   그림을 다 봤음(모든 그림에 필요)
  show    <그림>                                                   지금 고침을 반영해 그 그림 확인 그림(sheets) 다시 그림
  status  <판>                                                    판의 봤음·표시·고침 수
add·refit 맞춤: 앞면 = 흰 몸통, 뒷면 = 뒷면 색|흰 몸통 마스크(det_backs 의 HSV 기준)에서 다른 상자 자리를 빼고, 열기 연산으로 이웃과 뗀 뒤 점을 품은
  (없으면 가까운) 덩어리의 minAreaRect(det_obb.fit 와 같은 마스크 생각). 크기가 그 그림 같은 종류 상자 중앙값의 0.6~1.5배가 아니면
  중앙값 크기 축 상자(방향 = 가장 가까운 같은 종류 상자)로 대신(fit=axis). 결과 확인 그림 = data/v1114/dr/fitcheck/<판>/<그림>__<명령>_<번호>.jpg
  (초록 굵은 선 = 새 상자, 얇은 선 = 다른 상자). 꼭 열어 보고 틀리면 다른 점으로 다시 하거나 drop.
  python -X utf8 experiments/tile_classifier/v1114_dr_fit.py add r01_112804/win_114614 2150 2210 face --role pair --seat -
  python -X utf8 experiments/tile_classifier/v1114_dr_fit.py near r01_112804/win_114614 2150 2210
  python -X utf8 experiments/tile_classifier/v1114_dr_fit.py addbox r01_112804/win_114614 2150 2210 80 105 12 face --role river --seat bottom
  python -X utf8 experiments/tile_classifier/v1114_dr_fit.py nudge r01_112804/win_114614 a1 5 -3 0 0 2
addbox·nudge 확인 그림 = fitcheck/<판>/<그림>__{addbox,nudge}_<번호>.jpg(둘레를 2배로, 초록 굵은 선 = 새 상자, 얇은 선 = 이웃 상자).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from det_backs import back_mask, white_mask  # noqa: E402

V = HERE / "data" / "v1114"
DR = V / "dr"
ROLES = ("hand", "meld", "river", "wall", "pair", "loose", "other")
OWNED = ("hand", "loose", "meld", "river")
SIDES = ("bottom", "right", "top", "left")
FLAGS = ("blur", "occluded", "not_table")


def load(img_id: str):
    rid = img_id.split("/")[0]
    dj = json.loads((DR / "draft" / f"{rid}.json").read_text(encoding="utf-8"))
    img = next((i for i in dj["images"] if i["id"] == img_id), None)
    if img is None:
        sys.exit(f"그림 없음: {img_id}")
    rp = DR / "review" / f"{rid}.json"
    rv = json.loads(rp.read_text(encoding="utf-8"))
    return rid, img, rv, rp


def save(rp: Path, rv: dict):
    rp.write_text(json.dumps(rv, ensure_ascii=False, indent=1), encoding="utf-8")


def ent(rv: dict, img_id: str) -> dict:
    e = rv["images"][img_id]
    for k, v in (("box_edits", {}), ("adds", []), ("roles", {}), ("notes", ""), ("flags", None), ("seen", False)):
        e.setdefault(k, v)
    return e


def cur_boxes(img: dict, e: dict) -> list[dict]:
    """지금 상태(초안 + 고침)의 상자 목록 — v1114_dr_sheets.apply_review 와 같다."""
    import v1114_dr_sheets as sh
    return sh.apply_review(img, e)


def med_size(boxes: list, cls: str) -> tuple[float, float]:
    s = [sorted(np.linalg.norm(np.subtract(b["pts"][i], b["pts"][(i + 1) % 4])) for i in (0, 1)) for b in boxes if b["cls"] == cls and b["status"] == "keep"]
    if not s:
        s = [sorted(np.linalg.norm(np.subtract(b["pts"][i], b["pts"][(i + 1) % 4])) for i in (0, 1)) for b in boxes if b["status"] == "keep"]
    if not s:
        return 80.0, 110.0
    a = np.array(s)
    return float(np.median(a[:, 0])), float(np.median(a[:, 1]))


def fit_at(rgb: np.ndarray, x: float, y: float, cls: str, boxes: list, skip_id=None) -> dict:
    S, L = med_size(boxes, cls)
    R = int(1.7 * L)
    H, W = rgb.shape[:2]
    x0, y0, x1, y1 = int(max(0, x - R)), int(max(0, y - R)), int(min(W, x + R)), int(min(H, y + R))
    bgr = cv2.cvtColor(np.ascontiguousarray(rgb[y0:y1, x0:x1]), cv2.COLOR_RGB2BGR)
    m = white_mask(bgr) if cls == "face" else cv2.bitwise_or(back_mask(bgr, loose=True), white_mask(bgr))
    for b in boxes:  # 다른 상자 자리는 뺀다
        if b["status"] != "keep" or b["id"] == skip_id:
            continue
        p = np.round(np.array(b["pts"]) - [x0, y0]).astype(np.int32)
        cv2.fillPoly(m, [p], 0)
    k = max(3, int(0.06 * S) | 1)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    n, lab, st, cen = cv2.connectedComponentsWithStats(m)
    px, py = int(x - x0), int(y - y0)
    c = lab[min(max(py, 0), lab.shape[0] - 1), min(max(px, 0), lab.shape[1] - 1)] if n > 1 else 0
    if c == 0 and n > 1:
        d = [(np.hypot(cen[i][0] - px, cen[i][1] - py), i) for i in range(1, n) if st[i][4] > 0.2 * S * S]
        if d and min(d)[0] < 0.6 * L:
            c = min(d)[1]
    res = None
    why = ""
    if c:
        pts = np.column_stack(np.nonzero(lab == c))[:, ::-1].astype(np.float32)
        (cx, cy), (w, h), ang = cv2.minAreaRect(cv2.convexHull(pts))
        s2, l2 = sorted((w, h))
        lo, hi = (0.6, 1.5) if cls == "face" else (0.5, 1.7)
        if lo * S <= s2 <= hi * S and lo * L <= l2 <= hi * L:
            res = {"rect": [[round(cx + x0, 1), round(cy + y0, 1)], [round(w, 1), round(h, 1)], round(ang, 2)], "fit": "mask"}
        else:
            why = f"덩어리 크기 {s2:.0f}×{l2:.0f} 가 중앙값 {S:.0f}×{L:.0f} 와 맞지 않음"
    else:
        why = "점 둘레에 패 색 덩어리 없음"
    if res is None:  # 가장 가까운 같은 종류 상자 방향의 축 상자
        near = min((b for b in boxes if b["cls"] == cls and b["status"] == "keep"), default=None,
                   key=lambda b: np.hypot(b["box"][0] + b["box"][2] / 2 - x, b["box"][1] + b["box"][3] / 2 - y))
        wide = near is not None and near["box"][2] > near["box"][3]
        w, h = (L, S) if wide else (S, L)
        res = {"rect": [[round(x, 1), round(y, 1)], [round(w, 1), round(h, 1)], 0.0], "fit": "axis", "why": why}
    rc = res["rect"]
    p = cv2.boxPoints(((rc[0][0], rc[0][1]), (rc[1][0], rc[1][1]), rc[2]))
    res["pts"] = [[round(float(a), 1), round(float(b), 1)] for a, b in p]
    x_, y_ = max(0.0, float(p[:, 0].min())), max(0.0, float(p[:, 1].min()))
    res["box"] = [int(x_), int(y_), int(min(W, p[:, 0].max()) - x_), int(min(H, p[:, 1].max()) - y_)]
    return res


def rect_rec(img: dict, cx, cy, w, h, ang, fit: str) -> dict:
    """손으로 준 회전 상자(2992 좌표, cv2 minAreaRect 꼴 ((cx, cy), (w, h), 각도°)) → review 상자 기록(rect·pts·box·fit)."""
    W, H = img["size"]
    p = cv2.boxPoints(((cx, cy), (w, h), ang))
    x_, y_ = max(0.0, float(p[:, 0].min())), max(0.0, float(p[:, 1].min()))
    return {"rect": [[round(cx, 1), round(cy, 1)], [round(w, 1), round(h, 1)], round(ang, 2)], "fit": fit,
            "pts": [[round(float(a), 1), round(float(b), 1)] for a, b in p],
            "box": [int(x_), int(y_), int(min(W, p[:, 0].max()) - x_), int(min(H, p[:, 1].max()) - y_)]}


def check_img(rgb: np.ndarray, boxes: list, new: dict, path: Path, label: str):
    cx, cy = np.mean(new["pts"], axis=0)
    R = 260
    H, W = rgb.shape[:2]
    x0, y0, x1, y1 = int(max(0, cx - R)), int(max(0, cy - R)), int(min(W, cx + R)), int(min(H, cy + R))
    im = Image.fromarray(rgb[y0:y1, x0:x1]).resize(((x1 - x0) * 2, (y1 - y0) * 2), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    T = lambda p: ((p[0] - x0) * 2, (p[1] - y0) * 2)
    for b in boxes:
        if b["status"] == "keep":
            d.polygon([T(p) for p in b["pts"]], outline=(0, 210, 255) if b["cls"] == "face" else (255, 40, 210), width=1)
    d.polygon([T(p) for p in new["pts"]], outline=(0, 255, 0), width=4)
    import v1114_dr_sheets as sh
    sh.tag(d, 6, 6, f"{label}  fit={new.get('fit')}  {new.get('why', '')}", sh.font(18, True), bg=(0, 0, 0), fg=(255, 255, 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, quality=90)
    return path


def rgb_of(img: dict) -> np.ndarray:
    return np.asarray(Image.open(V / img["path"]).convert("RGB"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd")
    ap.add_argument("args", nargs="*")
    ap.add_argument("--role")
    ap.add_argument("--seat")
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    if a.cmd == "status":
        rv = json.loads((DR / "review" / f"{a.args[0]}.json").read_text(encoding="utf-8"))
        for k, e in rv["images"].items():
            print(k, "봤음" if e.get("seen") else "안 봄", "표시", e.get("flags"), "고침", len(e.get("box_edits", {})), "더함", len(e.get("adds", [])),
                  "역할", len(e.get("roles", {})))
        return
    img_id = a.args[0]
    rid, img, rv, rp = load(img_id)
    e = ent(rv, img_id)
    boxes = cur_boxes(img, e)
    by = {str(b["id"]): b for b in boxes}
    out = None
    if a.cmd == "add":
        x, y, cls = float(a.args[1]), float(a.args[2]), a.args[3]
        assert cls in ("face", "back"), "face 또는 back"
        r = fit_at(rgb_of(img), x, y, cls, boxes)
        aid = f"a{1 + max([int(q['aid'][1:]) for q in e['adds']] or [0])}"
        role, seat = a.role, (None if a.seat in (None, "-") else a.seat)
        if cls == "face" and role:
            assert role in ROLES and (seat in SIDES if role in OWNED else seat is None), "역할·자리 확인(주인 있는 역할 = hand meld river loose)"
        e["adds"].append({"aid": aid, "cls": cls, "click": [x, y], **r, "role": role if cls == "face" else None, "seat": seat if cls == "face" else None, "note": a.note})
        out = check_img(rgb_of(img), boxes, r, DR / "fitcheck" / rid / f"{Path(img['name']).stem}__add_{aid}.jpg", f"{aid} {cls}")
        if cls == "face" and not role:
            print("주의: 앞면은 역할도 적어야 함 → role", img_id, aid, "<역할> <자리|->")
    elif a.cmd == "addbox":
        cx, cy, w, h, ang, cls = float(a.args[1]), float(a.args[2]), float(a.args[3]), float(a.args[4]), float(a.args[5]), a.args[6]
        assert cls in ("face", "back"), "face 또는 back"
        r = rect_rec(img, cx, cy, w, h, ang, "manual")
        aid = f"a{1 + max([int(q['aid'][1:]) for q in e['adds']] or [0])}"
        role, seat = a.role, (None if a.seat in (None, "-") else a.seat)
        if cls == "face" and role:
            assert role in ROLES and (seat in SIDES if role in OWNED else seat is None), "역할·자리 확인(주인 있는 역할 = hand meld river loose)"
        e["adds"].append({"aid": aid, "cls": cls, "click": [cx, cy], **r, "role": role if cls == "face" else None, "seat": seat if cls == "face" else None, "note": a.note})
        out = check_img(rgb_of(img), boxes, r, DR / "fitcheck" / rid / f"{Path(img['name']).stem}__addbox_{aid}.jpg", f"{aid} {cls}")
        if cls == "face" and not role:
            print("주의: 앞면은 역할도 적어야 함 → role", img_id, aid, "<역할> <자리|->")
    elif a.cmd == "nudge":
        bid = a.args[1]
        dv = [float(v) for v in a.args[2:]] + [0.0] * (5 - len(a.args[2:]))
        b = by[bid]
        rc = b["rect"] if b.get("rect") else None
        if bid.startswith("a"):
            q = next(q for q in e["adds"] if q["aid"] == bid)
            rc = q["rect"]
        elif str(bid) in e["box_edits"] and e["box_edits"][bid].get("op") == "refit":
            rc = e["box_edits"][bid]["rect"]
        else:
            rc = next(x for x in img["boxes"] if str(x["id"]) == bid)["rect"]
        r = rect_rec(img, rc[0][0] + dv[0], rc[0][1] + dv[1], rc[1][0] + dv[2], rc[1][1] + dv[3], rc[2] + dv[4], "manual")
        if bid.startswith("a"):
            q.update(r)
        else:
            e["box_edits"][bid] = {"op": "refit", **r, "note": a.note or "nudge"}
        out = check_img(rgb_of(img), [x for x in boxes if str(x["id"]) != bid], r, DR / "fitcheck" / rid / f"{Path(img['name']).stem}__nudge_{bid}.jpg",
                        f"{bid} nudge {dv}")
    elif a.cmd == "near":
        x, y = float(a.args[1]), float(a.args[2])
        R = float(a.args[3]) if len(a.args) > 3 else 400.0
        rows = []
        for b in boxes:
            if b["status"] != "keep":
                continue
            c = np.mean(b["pts"], axis=0)
            dd = float(np.hypot(c[0] - x, c[1] - y))
            if dd <= R:
                rr = b.get("rect")
                if b["id"] in [q["aid"] for q in e["adds"]]:
                    rr = next(q for q in e["adds"] if q["aid"] == b["id"])["rect"]
                elif str(b["id"]) in e["box_edits"] and e["box_edits"][str(b["id"])].get("op") == "refit":
                    rr = e["box_edits"][str(b["id"])]["rect"]
                rows.append((dd, b["id"], b["cls"], rr))
        for dd, i, c, rr in sorted(rows, key=lambda t: t[0]):
            if rr:
                print(f"{i}\t{c}\t거리 {dd:.0f}\t중심 ({rr[0][0]:.0f}, {rr[0][1]:.0f})\t크기 {rr[1][0]:.0f}×{rr[1][1]:.0f}\t각도 {rr[2]:.1f}")
            else:
                print(f"{i}\t{c}\t거리 {dd:.0f}\t(회전 상자 없음)")
        return
    elif a.cmd == "refit":
        bid = a.args[1]
        b = by[bid]
        x, y = (float(a.args[2]), float(a.args[3])) if len(a.args) >= 4 else tuple(np.mean(b["pts"], axis=0))
        r = fit_at(rgb_of(img), x, y, b["cls"], boxes, skip_id=b["id"])
        if bid.startswith("a"):
            q = next(q for q in e["adds"] if q["aid"] == bid)
            q.update(r)
        else:
            e["box_edits"][bid] = {"op": "refit", **r, "note": a.note}
        out = check_img(rgb_of(img), boxes, r, DR / "fitcheck" / rid / f"{Path(img['name']).stem}__refit_{bid}.jpg", f"{bid} refit")
    elif a.cmd in ("drop", "restore", "flip"):
        bid = a.args[1]
        if bid.startswith("a"):
            if a.cmd == "drop":
                e["adds"] = [q for q in e["adds"] if q["aid"] != bid]
            elif a.cmd == "flip":
                q = next(q for q in e["adds"] if q["aid"] == bid)
                q["cls"] = "back" if q["cls"] == "face" else "face"
        else:
            assert bid in by, f"상자 없음 {bid}"
            e["box_edits"][bid] = {"op": a.cmd, "note": a.note}
    elif a.cmd == "role":
        bid, role, seat = a.args[1], a.args[2], (None if a.args[3] == "-" else a.args[3])
        assert role in ROLES, f"역할 {ROLES}"
        assert (seat in SIDES) if role in OWNED else seat is None, "주인 있는 역할(hand meld river loose)은 자리, 나머지는 -"
        if bid.startswith("a"):
            q = next(q for q in e["adds"] if q["aid"] == bid)
            q["role"], q["seat"] = role, seat
        else:
            e["roles"][bid] = {"role": role, "seat": seat, "note": a.note}
    elif a.cmd == "ok":
        bid = a.args[1]
        e["box_edits"].pop(bid, None)
        e["roles"].pop(bid, None)
    elif a.cmd == "flag":
        fl = [f for f in a.args[1:] if f != "normal"]
        assert all(f in FLAGS for f in fl), f"표시 {FLAGS} 또는 normal"
        e["flags"] = fl
    elif a.cmd == "note":
        e["notes"] = (e["notes"] + " / " if e["notes"] else "") + " ".join(a.args[1:])
    elif a.cmd == "seen":
        if e["flags"] is None:
            sys.exit("먼저 flag 로 그림 단위 표시(정상이면 normal)를 정하세요")
        e["seen"] = True
    elif a.cmd == "show":
        import v1114_dr_sheets as sh
        sh.sheets_for(rid, img_id)
        print(DR / "sheets" / rid / Path(img["name"]).stem)
        return
    else:
        sys.exit("명령: add addbox nudge near refit drop restore flip role ok flag note seen show status (--help)")
    save(rp, rv)
    print("고침 저장", rp.name, img_id, a.cmd, a.args[1:] if len(a.args) > 1 else "")
    if out:
        print("확인 그림", out)


if __name__ == "__main__":
    main()
