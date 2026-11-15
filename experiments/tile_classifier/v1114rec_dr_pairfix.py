"""짝(pair) 그림 상자 확인·고침 도우미(2026-11-15, 녹화 세트 3단계 2). v1114rec_dr_fit.py 를 짝 그림에 쓰는 얇은 판. 좌표 = 녹화 1496.

짝 그림의 상자 = v1114rec_dr_final_pair.build() 와 같은 것(기존 최종 ×0.5 − occluded, overrides 반영 여부 선택).
마스크 맞춤은 v1114_dr_fit.fit_at(크기를 그림 안 상자 중앙값으로 재서 해상도와 무관)을 그대로 쓴다. 고침은 손으로 pair/overrides.json 에 적는다.
명령:
  view   <그림> [x0 y0 x1 y1] [--hl 번호,…] [--after] [--out 이름]   녹화 그림에 상자를 얹어 2배로(영역 없으면 전체 1배). --after = overrides 반영.
                                                                 하늘 앞면 · 자홍 뒷면 · 노랑 굵게 = --hl 상자. 결과 pair/fix/<그림 이름>__<before|after>[_이름].jpg
  fit    <그림> <x> <y> face|back [--skip 번호]                     (x, y) 둘레 마스크 맞춤 회전 상자를 찍어 줌(고치지 않음)
  near   <그림> <x> <y> [반지름=100]                                둘레 상자 목록(중심·크기·각도)
  add    <그림> <x> <y> face|back [--role R --seat S] --note 글      (4단계) (x, y) 둘레 마스크 맞춤 상자를 overrides adds 에 더함(id p1, p2 …)
  addbox <그림> cx cy w h 각도 face|back [--role R --seat S] --note 글  (4단계) 회전 상자를 그대로 adds 에(fit=manual)
  drop   <그림> <번호> --note 글                                    (4단계) overrides boxes 에 drop(더한 pN 이면 adds 에서 뺌)
  flip   <그림> <번호> --note 글                                    (4단계) 앞면 ↔ 뒷면(overrides op flip)
  refit  <그림> <번호> [x y] --note 글                              (4단계) 마스크로 다시 맞춘 rect 로 move
  move   <그림> <번호> cx cy w h 각도 --note 글                      (4단계) rect 를 그대로 move
     add·addbox·refit·move 확인 그림 = pair/fix/check/<판>__<그림>__<명령>_<번호>.jpg(둘레 4배, 초록 = 새 상자). --reason 은 그림 reason 이 없을 때 넣음.
  fixsheets                                                       overrides 세 그림의 전·후 비교(위 흉내 q1496 · 아래 녹화, 같은 상자) → pair/fix/<판>__<그림>__{before,after}.jpg
  overlay                                                         그 밖 짝 그림 표본 12장(씨앗 20261115, overrides·occluded 그림 빼고)을
                                                                 pair/overlay_check/<판>__<그림>.jpg(전체 1배)·…_q<k>.jpg(네 조각 2배)로
  python -X utf8 experiments/tile_classifier/v1114rec_dr_pairfix.py view r20_143236/win_143425 550 100 950 230 --hl 35,36,37,38,39,40,41,42,43
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import v1114rec_dr_final_pair as FP  # noqa: E402
from v1114_dr_fit import fit_at  # noqa: E402
import v1114_dr_sheets as sh  # noqa: E402
from v1114rec_dr_common import R  # noqa: E402

SEED = 20261115
N_OVERLAY = 12


def get(img_id: str, after: bool) -> dict:
    by, _, _ = FP.build(use_overrides=after, only=img_id)
    ims = [im for v in by.values() for im in v]
    if not ims:
        sys.exit(f"짝 그림 없음: {img_id}")
    return ims[0]


def draw(im: dict, region, scale: float, hl: set, path: Path, title: str):
    rgb = Image.open(R / im["path"]).convert("RGB")
    x0, y0, x1, y1 = region
    part = rgb.crop((x0, y0, x1, y1))
    if scale != 1:
        part = part.resize((int((x1 - x0) * scale), int((y1 - y0) * scale)), Image.LANCZOS)
    M = sh.MARGIN
    can = Image.new("RGB", (part.width + 2 * M, part.height + 2 * M + 30), (255, 255, 255))
    can.paste(part, (M, M))
    d = ImageDraw.Draw(can, "RGBA")
    T = lambda p: (M + (p[0] - x0) * scale, M + (p[1] - y0) * scale)
    fnt = sh.font(13 if scale >= 2 else 11)
    for b in im["boxes"]:
        bx = b["box"]
        if bx[0] + bx[2] < x0 or bx[0] > x1 or bx[1] + bx[3] < y0 or bx[1] > y1:
            continue
        on = str(b["id"]) in hl
        col = (255, 230, 0) if on else sh.FACE if b["cls"] == "face" else sh.BACK
        d.polygon([T(p) for p in b["pts"]], outline=col, width=3 if on else 1 if scale < 2 else 2)
        tx, ty = T((bx[0], bx[1]))
        sh.tag(d, tx + 2, ty + 1, str(b["id"]) + ("~" if b.get("pair_fix") else ""), fnt, bg=(0, 0, 0, 150), fg=col)
    step, major = (25, 50) if scale >= 2 else (50, 250)
    sh.ticks(d, x0, y0, x1 - x0, y1 - y0, scale, step, major, sh.font(13))
    d.text((M + 4, M + part.height + 32), title, fill=(0, 0, 0), font=sh.font(15, True))
    path.parent.mkdir(parents=True, exist_ok=True)
    can.save(path, quality=90)
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd")
    ap.add_argument("args", nargs="*")
    ap.add_argument("--hl", default="")
    ap.add_argument("--after", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--skip", default=None)
    ap.add_argument("--role")
    ap.add_argument("--seat")
    ap.add_argument("--note", default="")
    ap.add_argument("--reason", default="")
    a = ap.parse_args()
    if a.cmd in ("add", "addbox", "drop", "flip", "refit", "move"):
        return edit(a)
    if a.cmd == "overlay":
        return overlay()
    if a.cmd == "fixsheets":
        return fixsheets()
    img_id = a.args[0]
    im = get(img_id, a.after)
    stem = Path(im["name"]).stem
    if a.cmd == "view":
        rg = tuple(int(v) for v in a.args[1:5]) if len(a.args) >= 5 else (0, 0, 1496, 1496)
        sc = 1.0 if rg == (0, 0, 1496, 1496) else 2.0
        hl = set(x for x in a.hl.split(",") if x)
        tag = ("after" if a.after else "before") + (f"_{a.out}" if a.out else "")
        p = draw(im, rg, sc, hl, R / "pair" / "fix" / f"{im['id'].split('/')[0]}__{stem}__{tag}.jpg",
                 f"{img_id} 녹화 rec1496 {'고친 뒤(overrides 반영)' if a.after else '고치기 전(기존 ×0.5 − occluded)'} {rg} ×{sc:g} · 노랑 = {a.hl or '-'}")
        print(p)
    elif a.cmd == "fit":
        x, y, cls = float(a.args[1]), float(a.args[2]), a.args[3]
        rgb = np.asarray(Image.open(R / im["path"]).convert("RGB"))
        boxes = [dict(b, status="keep") for b in im["boxes"]]
        skip = a.skip
        if skip is not None:
            boxes = [b for b in boxes if str(b["id"]) != skip]
        r = fit_at(rgb, x, y, cls, boxes)
        print(r)
    elif a.cmd == "near":
        x, y = float(a.args[1]), float(a.args[2])
        Rr = float(a.args[3]) if len(a.args) > 3 else 100.0
        for b in sorted(im["boxes"], key=lambda b: np.hypot(*(np.mean(b["pts"], 0) - [x, y]))):
            c = np.mean(b["pts"], 0)
            dd = float(np.hypot(c[0] - x, c[1] - y))
            if dd > Rr:
                break
            rc = b["rect"]
            print(f"{b['id']}\t{b['cls']}\t{b.get('role')}\t거리 {dd:.0f}\t중심 ({rc[0][0]:.1f}, {rc[0][1]:.1f})\t크기 {rc[1][0]:.1f}×{rc[1][1]:.1f}\t각도 {rc[2]:.2f}")


def edit(a):
    """overrides.json 고침(4단계). 상자는 overrides 반영 뒤(--after) 상자 기준."""
    import json
    from v1114_dr_fit import rect_rec
    from v1114rec_dr_fit import check_img, check_role
    img_id = a.args[0]
    im = get(img_id, True)
    p = R / "pair" / "overrides.json"
    ov = json.loads(p.read_text(encoding="utf-8"))
    e = ov["images"].setdefault(img_id, {"reason": a.reason or "4단계 독립 검토·헛검출 확인 반영", "boxes": {}})
    e.setdefault("boxes", {})
    rgb = np.asarray(Image.open(R / im["path"]).convert("RGB"))
    boxes = [dict(b, status="keep") for b in im["boxes"]]
    by = {str(b["id"]): b for b in boxes}
    stem = Path(im["name"]).stem
    new, tagid = None, None
    if a.cmd in ("add", "addbox"):
        if a.cmd == "add":
            x, y, cls = float(a.args[1]), float(a.args[2]), a.args[3]
            r = fit_at(rgb, x, y, cls, boxes)
        else:
            cx, cy, w, h, ang, cls = *[float(v) for v in a.args[1:6]], a.args[6]
            x, y = cx, cy
            r = rect_rec(im, cx, cy, w, h, ang, "manual")
        assert cls in ("face", "back")
        seat = None if a.seat in (None, "-") else a.seat
        if cls == "face":
            assert a.role, "앞면은 --role"
            check_role(a.role, seat)
        adds = e.setdefault("adds", [])
        aid = f"p{1 + max([int(q['aid'][1:]) for q in adds] or [0])}"
        adds.append({"aid": aid, "cls": cls, "click": [x, y], "rect": r["rect"], "fit": r["fit"], "why": r.get("why", ""),
                     "role": a.role if cls == "face" else None, "seat": seat if cls == "face" else None, "note": a.note})
        new, tagid = r, aid
    else:
        bid = a.args[1]
        if bid.startswith("p"):
            adds = e.get("adds") or []
            q = next(q for q in adds if q["aid"] == bid)
            if a.cmd == "drop":
                e["adds"] = [x for x in adds if x["aid"] != bid]
            elif a.cmd == "flip":
                q["cls"] = "back" if q["cls"] == "face" else "face"
            else:
                if a.cmd == "refit":
                    xy = (float(a.args[2]), float(a.args[3])) if len(a.args) >= 4 else tuple(np.mean(by[bid]["pts"], 0))
                    r = fit_at(rgb, *xy, q["cls"], boxes, skip_id=bid)
                else:
                    r = rect_rec(im, *[float(v) for v in a.args[2:7]], "manual")
                q["rect"], q["fit"] = r["rect"], r["fit"]
                new, tagid = r, bid
        else:
            assert bid in by, f"상자 없음 {bid}"
            if a.cmd in ("drop", "flip"):
                e["boxes"][bid] = {"op": a.cmd, "note": a.note}
            else:
                if a.cmd == "refit":
                    xy = (float(a.args[2]), float(a.args[3])) if len(a.args) >= 4 else tuple(np.mean(by[bid]["pts"], 0))
                    r = fit_at(rgb, *xy, by[bid]["cls"], boxes, skip_id=by[bid]["id"])
                else:
                    r = rect_rec(im, *[float(v) for v in a.args[2:7]], "manual")
                e["boxes"][bid] = {"op": "move", "rect": r["rect"], "fit": r["fit"], "note": a.note}
                new, tagid = r, bid
    if not e["boxes"]:
        e.pop("boxes")
        e["boxes"] = {}
    p.write_text(json.dumps(ov, ensure_ascii=False, indent=1), encoding="utf-8")
    print("고침 저장 overrides.json", img_id, a.cmd, a.args[1:])
    if new is not None:
        if "pts" not in new:
            new = rect_rec(im, new["rect"][0][0], new["rect"][0][1], new["rect"][1][0], new["rect"][1][1], new["rect"][2], new.get("fit", ""))
        out = check_img(rgb, [b for b in boxes if str(b["id"]) != tagid], new,
                        R / "pair" / "fix" / "check" / f"{img_id.split('/')[0]}__{stem}__{a.cmd}_{tagid}.jpg", f"{tagid} {a.cmd}")
        print("확인 그림", out, "fit", new.get("fit"), new.get("why", ""))


FIX_VIEWS = {  # 그림 → (영역 1496, 배율, 노랑 상자)
    "r20_143236/win_143425": ((540, 80, 930, 200), 3, "35,36,37,38,39,40,41,42,43"),
    "r14_133610/133610_f0035_133742": ((540, 380, 720, 520), 4, "19"),
    "r19_142013/142013_f0022_142036": ((780, 1300, 1180, 1410), 3, "73"),
}


def cmp_sheet(img_id: str, region, sc: int, hl: set, after: bool, path: Path):
    """위 = 흉내 q1496(라벨을 단 2992 그림의 2×2 평균), 아래 = 녹화 rec1496, 둘 다 같은 상자(전 또는 후)를 얹어 sc 배로."""
    im = get(img_id, after)
    F = FP.old_finals()[img_id]
    x0, y0, x1, y1 = region
    rows = []
    for name, p in (("q1496 (흉내)", FP.V / F["paths"]["q1496"]), ("rec1496 (녹화)", R / im["path"])):
        rgb = Image.open(p).convert("RGB").crop(region).resize(((x1 - x0) * sc, (y1 - y0) * sc), Image.LANCZOS)
        d = ImageDraw.Draw(rgb)
        for b in im["boxes"]:
            col = (255, 230, 0) if str(b["id"]) in hl else (sh.FACE if b["cls"] == "face" else sh.BACK)
            d.polygon([((q[0] - x0) * sc, (q[1] - y0) * sc) for q in b["pts"]], outline=col, width=2)
            d.text(((b["box"][0] - x0) * sc + 3, (b["box"][1] - y0) * sc + 3), str(b["id"]), fill=col)
        for v in range((x0 // 10 + 1) * 10, x1, 10):
            d.line(((v - x0) * sc, 0, (v - x0) * sc, 6 if v % 50 else 14), fill=(255, 0, 0))
            if v % 50 == 0:
                d.text(((v - x0) * sc + 2, 14), str(v), fill=(255, 0, 0))
        for v in range((y0 // 10 + 1) * 10, y1, 10):
            d.line((0, (v - y0) * sc, 6 if v % 50 else 14, (v - y0) * sc), fill=(255, 0, 0))
            if v % 50 == 0:
                d.text((16, (v - y0) * sc), str(v), fill=(255, 0, 0))
        d.text((4, rgb.height - 14), f"{name} {'after' if after else 'before'}", fill=(255, 255, 0))
        rows.append(rgb)
    can = Image.new("RGB", (rows[0].width, rows[0].height * 2 + 4), (255, 255, 255))
    can.paste(rows[0], (0, 0))
    can.paste(rows[1], (0, rows[0].height + 4))
    path.parent.mkdir(parents=True, exist_ok=True)
    can.save(path, quality=92)
    return path


def fixsheets():
    """세 그림의 고치기 전·후 비교 그림 pair/fix/<판>__<그림>__{before,after}.jpg"""
    for iid, (rg, sc, hl) in FIX_VIEWS.items():
        for after in (False, True):
            p = R / "pair" / "fix" / f"{iid.split('/')[0]}__{iid.split('/')[1]}__{'after' if after else 'before'}.jpg"
            print(cmp_sheet(iid, rg, sc, set(hl.split(",")), after, p))


def overlay():
    """overrides 그림·occluded 로 상자를 뺀 그림을 빼고 표본 12장."""
    by, _, _ = FP.build(use_overrides=True)
    ims = sorted((im for v in by.values() for im in v), key=lambda x: x["id"])
    ov = FP.overrides()
    skip = {im["id"] for im in ims if im["id"] in ov or any((b.get("pair_review") or {}).get("verdict") == "occluded" for b in im["boxes"])}
    occl_ids = {k[0] for k, v in FP.verdicts().items() if v["verdict"] == "occluded"}
    pool = [im for im in ims if im["id"] not in ov and im["id"] not in occl_ids]
    pick = random.Random(SEED).sample(pool, N_OVERLAY)
    out = R / "pair" / "overlay_check"
    out.mkdir(parents=True, exist_ok=True)
    W = H = 1496
    OVp = 30
    for im in pick:
        base = f"{im['id'].split('/')[0]}__{Path(im['name']).stem}"
        draw(im, (0, 0, W, H), 1.0, set(), out / f"{base}.jpg", f"{im['id']} 녹화 rec1496 + 짝 최종 라벨(×0.5) 전체 1배")
        for k, rg in enumerate([(0, 0, W // 2 + OVp, H // 2 + OVp), (W // 2 - OVp, 0, W, H // 2 + OVp), (0, H // 2 - OVp, W // 2 + OVp, H), (W // 2 - OVp, H // 2 - OVp, W, H)], 1):
            draw(im, rg, 2.0, set(), out / f"{base}_q{k}.jpg", f"{im['id']} 조각 q{k} {rg} ×2")
        print(im["id"], im["split_final"], len(im["boxes"]))
    import json
    (out / "_list.json").write_text(json.dumps({"_note": f"짝 그림 상자 표본(씨앗 {SEED}, overrides·occluded 그림 {len(skip)}장 빼고 {N_OVERLAY}장). v1114rec_dr_pairfix.py overlay",
                                                "images": [im["id"] for im in pick]}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
