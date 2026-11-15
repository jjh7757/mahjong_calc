"""녹화 프레임(rec1496) 검출·역할 눈 확인 도우미(2026-11-15, 녹화 세트 2단계 6). v1114_dr_fit.py 와 같은 명령, 뿌리 data/v1114rec, 좌표 1496.
review/<판>.json 을 이 도구로 고친다(손으로 고쳐도 됨, 꼴은 data/v1114rec/dr/review/_FORMAT.json). 마스크 맞춤(fit_at)·회전 상자 기록(rect_rec)·
중앙값 크기(med_size)는 v1114_dr_fit 의 것을 그대로 불러 쓴다(크기를 그림 안 상자 중앙값으로 재서 해상도와 무관).

명령(그림 id = dr/draft 의 images[].id, 예 r01_112804/mid_1794624295353. 좌표 = 녹화 1496 원래 픽셀, 확인 그림 가장자리 눈금):
  add     <그림> <x> <y> face|back [--role R --seat S] [--note 글]   놓친 패: (x, y) 둘레 패 덩어리에 회전 상자를 맞춰 더함(id a1, a2 …)
  refit   <그림> <번호> [x y]                                      상자를 다시 맞춤(점을 주면 그 둘레, 없으면 지금 상자 가운데)
  drop    <그림> <번호> [--note 글]                                상자 지움(패 아님·두 번 잡힘 등). 더한 상자(aN)면 목록에서 뺌
  restore <그림> <번호>                                            지운 상자를 되살림(앞면으로)
  flip    <그림> <번호>                                            앞면 ↔ 뒷면
  addbox  <그림> cx cy w h 각도 face|back [--role R --seat S] [--note 글]   회전 상자를 그대로 넣음(fit=manual)
  nudge   <그림> <번호> dx dy [dw dh d각도]                         상자를 조금씩 옮기고 크기·각도 고침(초안 상자는 refit 고침으로 남음)
  near    <그림> x y [반지름=200]                                   (x, y) 둘레 상자 목록(고치지 않음)
  role    <그림> <번호> <역할> <자리|->                             역할·주인 고침. 역할 hand meld river wall pair loose other, 자리 bottom right top left 또는 -
  ok      <그림> <번호>                                            고침 하나를 지움(초안으로 되돌림)
  flag    <그림> normal | blur occluded not_table between …        그림 단위 표시(normal = 정상, 여럿 가능)
  phase   <그림> play|end                                          판 중 / 공개 장면
  note    <그림> <글>                                              그림 메모(덧붙임)
  seen    <그림>                                                   그림을 다 봤음(flag·phase 를 먼저 정해야 함)
  unseen  <그림>                                                   봤음 표시를 지움
  show    <그림>                                                   지금 고침을 반영해 그 그림 확인 그림(dr/sheets) 다시 그림
  status  <판>                                                    판의 봤음·표시·phase·고침 수
add·refit·addbox·nudge 확인 그림 = data/v1114rec/dr/fitcheck/<판>/<그림>__<명령>_<번호>.jpg(둘레를 4배로, 초록 굵은 선 = 새 상자, 얇은 선 = 다른 상자). 꼭 열어 볼 것.
  python -X utf8 experiments/tile_classifier/v1114rec_dr_fit.py add r01_112804/mid_1794624295353 1075 1105 face --role river --seat bottom
  python -X utf8 experiments/tile_classifier/v1114rec_dr_fit.py show r01_112804/mid_1794624295353
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from v1114_dr_fit import fit_at, rect_rec  # noqa: E402

R = HERE / "data" / "v1114rec"
DR = R / "dr"
ROLES = ("hand", "meld", "river", "wall", "pair", "loose", "other")
OWNED = ("hand", "loose", "meld", "river")
SIDES = ("bottom", "right", "top", "left")
FLAGS = ("blur", "occluded", "not_table", "between")
PHASES = ("play", "end")
CHECK_R, CHECK_Z = 130, 4  # 확인 그림 둘레 반지름(1496 px)·배율


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
    for k, v in (("box_edits", {}), ("adds", []), ("roles", {}), ("notes", ""), ("flags", None), ("phase", None), ("seen", False)):
        e.setdefault(k, v)
    return e


def cur_boxes(img: dict, e: dict) -> list[dict]:
    from v1114_dr_sheets import apply_review
    return apply_review(img, e)


def check_img(rgb: np.ndarray, boxes: list, new: dict, path: Path, label: str):
    cx, cy = np.mean(new["pts"], axis=0)
    H, W = rgb.shape[:2]
    x0, y0, x1, y1 = int(max(0, cx - CHECK_R)), int(max(0, cy - CHECK_R)), int(min(W, cx + CHECK_R)), int(min(H, cy + CHECK_R))
    im = Image.fromarray(rgb[y0:y1, x0:x1]).resize(((x1 - x0) * CHECK_Z, (y1 - y0) * CHECK_Z), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    T = lambda p: ((p[0] - x0) * CHECK_Z, (p[1] - y0) * CHECK_Z)
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
    return np.asarray(Image.open(R / img["path"]).convert("RGB"))


def check_role(role: str, seat):
    assert role in ROLES, f"역할 {ROLES}"
    assert (seat in SIDES) if role in OWNED else seat is None, "주인 있는 역할(hand meld river loose)은 자리, 나머지는 -"


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
            print(k, "봤음" if e.get("seen") else "안 봄", "표시", e.get("flags"), "phase", e.get("phase"), "고침", len(e.get("box_edits", {})),
                  "더함", len(e.get("adds", [])), "역할", len(e.get("roles", {})))
        return
    img_id = a.args[0]
    rid, img, rv, rp = load(img_id)
    e = ent(rv, img_id)
    boxes = cur_boxes(img, e)
    by = {str(b["id"]): b for b in boxes}
    out = None
    stem = Path(img["name"]).stem
    if a.cmd in ("add", "addbox"):
        if a.cmd == "add":
            x, y, cls = float(a.args[1]), float(a.args[2]), a.args[3]
            assert cls in ("face", "back"), "face 또는 back"
            r = fit_at(rgb_of(img), x, y, cls, boxes)
        else:
            cx, cy, w, h, ang, cls = float(a.args[1]), float(a.args[2]), float(a.args[3]), float(a.args[4]), float(a.args[5]), a.args[6]
            assert cls in ("face", "back"), "face 또는 back"
            x, y = cx, cy
            r = rect_rec(img, cx, cy, w, h, ang, "manual")
        aid = f"a{1 + max([int(q['aid'][1:]) for q in e['adds']] or [0])}"
        role, seat = a.role, (None if a.seat in (None, "-") else a.seat)
        if cls == "face" and role:
            check_role(role, seat)
        e["adds"].append({"aid": aid, "cls": cls, "click": [x, y], **r, "role": role if cls == "face" else None, "seat": seat if cls == "face" else None, "note": a.note})
        out = check_img(rgb_of(img), boxes, r, DR / "fitcheck" / rid / f"{stem}__{a.cmd}_{aid}.jpg", f"{aid} {cls}")
        if cls == "face" and not role:
            print("주의: 앞면은 역할도 적어야 함 → role", img_id, aid, "<역할> <자리|->")
    elif a.cmd == "nudge":
        bid = a.args[1]
        dv = [float(v) for v in a.args[2:]] + [0.0] * (5 - len(a.args[2:]))
        assert bid in by, f"상자 없음 {bid}"
        q = None
        if bid.startswith("a"):
            q = next(q for q in e["adds"] if q["aid"] == bid)
            rc = q["rect"]
        elif bid in e["box_edits"] and e["box_edits"][bid].get("op") == "refit":
            rc = e["box_edits"][bid]["rect"]
        else:
            rc = next(x for x in img["boxes"] if str(x["id"]) == bid)["rect"]
        r = rect_rec(img, rc[0][0] + dv[0], rc[0][1] + dv[1], rc[1][0] + dv[2], rc[1][1] + dv[3], rc[2] + dv[4], "manual")
        if q is not None:
            q.update(r)
        else:
            e["box_edits"][bid] = {"op": "refit", **r, "note": a.note or "nudge"}
        out = check_img(rgb_of(img), [x for x in boxes if str(x["id"]) != bid], r, DR / "fitcheck" / rid / f"{stem}__nudge_{bid}.jpg", f"{bid} nudge {dv}")
    elif a.cmd == "near":
        x, y = float(a.args[1]), float(a.args[2])
        Rr = float(a.args[3]) if len(a.args) > 3 else 200.0
        rows = []
        adds = {q["aid"]: q for q in e["adds"]}
        for b in boxes:
            if b["status"] != "keep":
                continue
            c = np.mean(b["pts"], axis=0)
            dd = float(np.hypot(c[0] - x, c[1] - y))
            if dd <= Rr:
                rr = b.get("rect")
                if b["id"] in adds:
                    rr = adds[b["id"]]["rect"]
                elif str(b["id"]) in e["box_edits"] and e["box_edits"][str(b["id"])].get("op") == "refit":
                    rr = e["box_edits"][str(b["id"])]["rect"]
                rows.append((dd, b["id"], b["cls"], rr, b.get("tile")))
        for dd, i, c, rr, t in sorted(rows, key=lambda t: t[0]):
            print(f"{i}\t{c}\t{t or ''}\t거리 {dd:.0f}\t중심 ({rr[0][0]:.0f}, {rr[0][1]:.0f})\t크기 {rr[1][0]:.0f}×{rr[1][1]:.0f}\t각도 {rr[2]:.1f}")
        return
    elif a.cmd == "refit":
        bid = a.args[1]
        assert bid in by, f"상자 없음 {bid}"
        b = by[bid]
        x, y = (float(a.args[2]), float(a.args[3])) if len(a.args) >= 4 else tuple(np.mean(b["pts"], axis=0))
        r = fit_at(rgb_of(img), x, y, b["cls"], boxes, skip_id=b["id"])
        if bid.startswith("a"):
            next(q for q in e["adds"] if q["aid"] == bid).update(r)
        else:
            e["box_edits"][bid] = {"op": "refit", **r, "note": a.note}
        out = check_img(rgb_of(img), boxes, r, DR / "fitcheck" / rid / f"{stem}__refit_{bid}.jpg", f"{bid} refit")
    elif a.cmd in ("drop", "restore", "flip"):
        bid = a.args[1]
        if bid.startswith("a"):
            assert any(q["aid"] == bid for q in e["adds"]), f"더한 상자 없음 {bid}"
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
        check_role(role, seat)
        if bid.startswith("a"):
            q = next(q for q in e["adds"] if q["aid"] == bid)
            q["role"], q["seat"] = role, seat
        else:
            assert bid in by, f"상자 없음 {bid}"
            e["roles"][bid] = {"role": role, "seat": seat, "note": a.note}
    elif a.cmd == "ok":
        bid = a.args[1]
        e["box_edits"].pop(bid, None)
        e["roles"].pop(bid, None)
    elif a.cmd == "flag":
        fl = [f for f in a.args[1:] if f != "normal"]
        assert all(f in FLAGS for f in fl), f"표시 {FLAGS} 또는 normal"
        e["flags"] = fl
    elif a.cmd == "phase":
        assert a.args[1] in PHASES, f"phase {PHASES}"
        e["phase"] = a.args[1]
    elif a.cmd == "note":
        e["notes"] = (e["notes"] + " / " if e["notes"] else "") + " ".join(a.args[1:])
    elif a.cmd == "seen":
        if e["flags"] is None:
            sys.exit("먼저 flag 로 그림 단위 표시(정상이면 normal)를 정하세요")
        if e["phase"] is None:
            sys.exit("먼저 phase 로 play|end 를 정하세요")
        e["seen"] = True
    elif a.cmd == "unseen":
        e["seen"] = False
    elif a.cmd == "show":
        import v1114rec_dr_sheets as sh
        sh.sheets_for(rid, img_id)
        print(DR / "sheets" / rid / stem)
        return
    else:
        sys.exit("명령: add addbox nudge near refit drop restore flip role ok flag phase note seen unseen show status (--help)")
    rv["done"] = all(x.get("seen") for x in rv["images"].values())
    save(rp, rv)
    print("고침 저장", rp.name, img_id, a.cmd, a.args[1:] if len(a.args) > 1 else "")
    if out:
        print("확인 그림", out)


if __name__ == "__main__":
    main()
