"""검출·역할 초안 확인 그림(2026-11-15, 검출·역할 세트 1단계 B). v1114_dr_draft.py 다음에(그리고 v1114_dr_fit.py 로 고친 뒤 다시).

그림마다 data/v1114/dr/sheets/<판>/<그림 이름>/ 에 6장:
  det_all.jpg      그림 전체(0.5배) — 앞면 = 하늘색, 뒷면 = 자홍, 지운 초안 앞면 = 회색 점선(번호 뒤 x). 번호 = draft boxes[].id.
                   번호 뒤 + = 조각 검출에서만 나온 앞면(새로 더함), * = not_tile 앞면을 뒷면으로 바꾼 것. 노란 얇은 선 = 찾은 펠트, 흰 사각형 = 찾은 기기.
  det_q1~q4.jpg    네 조각(왼위·오른위·왼아래·오른아래, 겹침 120px)을 원래 크기(det_all 의 2배)로. 작은 패·붙은 패 구분용.
  role.jpg         앞면 상자를 역할 색 테두리로(0.67배), 꼬리표 = 번호 + 주인 자리 글자(B 아래 R 오른쪽 T 위 L 왼쪽, - 없음).
                   빨간 꼬리표 = 규칙·모델이 갈린 상자, 두꺼운 빨간 고리 = 정답(label.json)과 어긋난 상자. 오른쪽 띠에 범례·갈린 상자 목록.
모든 그림 가장자리 띠에 2992 좌표 눈금(놓친 패 좌표를 적을 때). 상자 선은 얇게, 번호는 상자 왼쪽 위 안쪽 귀퉁이에 작게(패 무늬는 가운데).
review/<판>.json 이 있으면 그 고침(지움·종류 바꿈·다시 맞춤·더함·역할)을 반영해 그린다(고친 상자는 번호 뒤 ~, 더한 상자 번호 a1·a2…).
  python -X utf8 experiments/tile_classifier/v1114_dr_sheets.py [판 id ...] [--image 그림 id]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
V = HERE / "data" / "v1114"
DR = V / "dr"
FACE, BACK, DROP = (0, 210, 255), (255, 40, 210), (150, 150, 150)
ROLE_COL = {"hand": (40, 110, 255), "meld": (0, 230, 230), "river": (255, 150, 0), "wall": (230, 30, 30), "pair": (255, 0, 255),
            "loose": (255, 240, 0), "other": (170, 170, 170)}
SEAT_CH = {"bottom": "B", "right": "R", "top": "T", "left": "L", None: "-"}
MARGIN = 56


def font(sz: int, kr: bool = False):
    for f in (["malgun.ttf", "C:/Windows/Fonts/malgun.ttf"] if kr else ["arial.ttf"]):
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            pass
    return ImageFont.load_default()


def apply_review(img: dict, rv: dict | None) -> list[dict]:
    """초안 상자 + review 고침 → 그릴 상자 목록(복사). 고침 꼴은 review/_FORMAT.json."""
    boxes = [dict(b) for b in img["boxes"]]
    if not rv:
        return boxes
    by = {b["id"]: b for b in boxes}
    for sid, ed in (rv.get("box_edits") or {}).items():
        b = by.get(int(sid))
        if b is None:
            continue
        op = ed.get("op")
        if op == "drop":
            b["status"] = "drop"
        elif op == "restore":
            b["status"] = "keep"
        elif op == "flip":
            b["cls"] = "back" if b["cls"] == "face" else "face"
            b["status"] = "keep"
        elif op == "refit":
            b["pts"], b["box"] = ed["pts"], ed["box"]
        b["edited"] = op
    for sid, rr in (rv.get("roles") or {}).items():
        b = by.get(int(sid))
        if b is not None and b.get("rule") is not None:
            b["final_role"] = rr
            b["edited"] = b.get("edited") or "role"
    for a in rv.get("adds") or []:
        boxes.append({"id": a["aid"], "cls": a["cls"], "status": "keep", "box": a["box"], "pts": a["pts"], "src": "add", "edited": "add",
                      "final_role": {"role": a.get("role"), "seat": a.get("seat")} if a.get("role") else None})
    return boxes


def ticks(d: ImageDraw.ImageDraw, x0: int, y0: int, w: int, h: int, scale: float, step: int, major: int, fnt):
    """그림(왼위 = 2992 좌표 (x0, y0), 크기 w×h 원본 px, 배율 scale) 둘레 띠에 눈금."""
    W, H = int(w * scale), int(h * scale)
    for v in range((x0 // step) * step, x0 + w + 1, step):
        if v < x0:
            continue
        X = MARGIN + (v - x0) * scale
        L = 14 if v % major == 0 else 7
        d.line((X, MARGIN - L, X, MARGIN), fill=(0, 0, 0), width=1)
        d.line((X, MARGIN + H, X, MARGIN + H + L), fill=(0, 0, 0), width=1)
        if v % major == 0:
            d.text((X + 2, 2), str(v), fill=(0, 0, 0), font=fnt)
            d.text((X + 2, MARGIN + H + 16), str(v), fill=(0, 0, 0), font=fnt)
    for v in range((y0 // step) * step, y0 + h + 1, step):
        if v < y0:
            continue
        Y = MARGIN + (v - y0) * scale
        L = 14 if v % major == 0 else 7
        d.line((MARGIN - L, Y, MARGIN, Y), fill=(0, 0, 0), width=1)
        d.line((MARGIN + W, Y, MARGIN + W + L, Y), fill=(0, 0, 0), width=1)
        if v % major == 0:
            d.text((2, Y + 2), str(v), fill=(0, 0, 0), font=fnt)
            d.text((MARGIN + W + 16, Y + 2), str(v), fill=(0, 0, 0), font=fnt)


def dashed_poly(d, pts, fill, width, dash=6):
    for i in range(len(pts)):
        (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % len(pts)]
        L = float(np.hypot(x2 - x1, y2 - y1))
        n = max(1, int(L / dash))
        for k in range(0, n, 2):
            a, b = k / n, min(1, (k + 1) / n)
            d.line((x1 + (x2 - x1) * a, y1 + (y2 - y1) * a, x1 + (x2 - x1) * b, y1 + (y2 - y1) * b), fill=fill, width=width)


def tag(d, x, y, text, fnt, bg=(0, 0, 0), fg=(255, 255, 255)):
    l, t, r, b = d.textbbox((x, y), text, font=fnt)
    d.rectangle((l - 1, t - 1, r + 1, b + 1), fill=bg)
    d.text((x, y), text, fill=fg, font=fnt)


def label_of(b: dict) -> str:
    s = str(b["id"])
    if b["src"] == "quad":
        s += "+"
    if b["src"] == "from_face":
        s += "*"
    if b.get("edited"):
        s += "~"
    if b["status"] == "drop":
        s += "x"
    return s


def draw_det(rgb: Image.Image, img: dict, boxes: list, region, scale: float, path: Path, step: int, major: int, fs: int, title: str):
    x0, y0, x1, y1 = region
    w, h = x1 - x0, y1 - y0
    part = rgb.crop((x0, y0, x1, y1))
    if scale != 1.0:
        part = part.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    can = Image.new("RGB", (part.width + 2 * MARGIN, part.height + 2 * MARGIN), (255, 255, 255))
    can.paste(part, (MARGIN, MARGIN))
    d = ImageDraw.Draw(can, "RGBA")
    fnt, ft = font(fs), font(13)
    T = lambda p: (MARGIN + (p[0] - x0) * scale, MARGIN + (p[1] - y0) * scale)
    q = img["felt"].get("quad")
    if q:
        d.line([T(p) for p in q + [q[0]]], fill=(255, 255, 0, 160), width=1)
    dv = img["device"]
    d.rectangle((*T((dv["cx"] - dv["hd"], dv["cy"] - dv["hd"])), *T((dv["cx"] + dv["hd"], dv["cy"] + dv["hd"]))), outline=(255, 255, 255, 200), width=1)
    for b in boxes:
        bx = b["box"]
        if bx[0] + bx[2] < x0 or bx[0] > x1 or bx[1] + bx[3] < y0 or bx[1] > y1:
            continue
        pts = [T(p) for p in b["pts"]]
        if b["status"] == "drop":
            dashed_poly(d, pts, DROP, 2)
        else:
            d.polygon(pts, outline=FACE if b["cls"] == "face" else BACK, width=2)
        tx, ty = T((bx[0], bx[1]))
        col = FACE if b["cls"] == "face" else BACK
        tag(d, tx + 2, ty + 1, label_of(b), fnt, bg=(0, 0, 0, 150), fg=DROP if b["status"] == "drop" else col)
    ticks(d, x0, y0, w, h, scale, step, major, ft)
    d.text((MARGIN + 4, MARGIN + part.height + 32), title, fill=(0, 0, 0), font=font(16, True))
    can.save(path, quality=88)


def draw_role(rgb: Image.Image, img: dict, boxes: list, path: Path):
    W, H = img["size"]
    s = 2 / 3
    part = rgb.resize((int(W * s), int(H * s)), Image.LANCZOS)
    PANEL = 520
    can = Image.new("RGB", (part.width + 2 * MARGIN + PANEL, part.height + 2 * MARGIN), (255, 255, 255))
    can.paste(part, (MARGIN, MARGIN))
    d = ImageDraw.Draw(can, "RGBA")
    fnt, fk, fks = font(13), font(15, True), font(13, True)
    T = lambda p: (MARGIN + p[0] * s, MARGIN + p[1] * s)
    dv = img["device"]
    d.rectangle((*T((dv["cx"] - dv["hd"], dv["cy"] - dv["hd"])), *T((dv["cx"] + dv["hd"], dv["cy"] + dv["hd"]))), outline=(255, 255, 255, 220), width=2)
    lines = []
    for b in boxes:
        if b["status"] != "keep":
            continue
        pts = [T(p) for p in b["pts"]]
        if b["cls"] == "back":
            d.polygon(pts, outline=(255, 255, 255, 110), width=1)
            continue
        fr = b.get("final_role") or b.get("rule") or {}
        role, seat = fr.get("role"), fr.get("seat")
        col = ROLE_COL.get(role, (255, 255, 255))
        if b.get("label_mismatch"):
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            d.rectangle((min(xs) - 5, min(ys) - 5, max(xs) + 5, max(ys) + 5), outline=(255, 0, 0), width=4)
        d.polygon(pts, outline=col, width=3)
        split = bool(b.get("split")) and not b.get("final_role")
        bx = b["box"]
        tx, ty = T((bx[0], bx[1]))
        tag(d, tx + 2, ty + 1, f"{b['id']}{SEAT_CH.get(seat, '?')}", fnt, bg=(220, 0, 0, 230) if split else (0, 0, 0, 150), fg=(255, 255, 255) if split else col)
        if split:
            m = b["model"]
            lines.append(f"{b['id']}: 규칙 {b['rule']['role']}/{SEAT_CH[b['rule']['seat']]} · 모델 {m['role']}/{SEAT_CH.get(m['seat'], '-')}"
                         f"({m['conf']:.2f}) · D {m['d_role']}/{SEAT_CH[m['d_seat']]}")
        for why in b.get("label_mismatch") or []:
            lines.append(f"{b['id']}: 정답 어긋남 — {why}")
    ticks(d, 0, 0, W, H, s, 100, 500, font(13))
    # 오른쪽 띠
    X = part.width + 2 * MARGIN + 8
    y = MARGIN
    d.text((X, y), f"{img['id']}", fill=(0, 0, 0), font=fk)
    y += 22
    d.text((X, y), f"{'화료 사진' if img['format'] == 'win' else '판 중 프레임'} · 화료자 {img.get('winner') or '-'}({img.get('winner_src') or ''})", fill=(0, 0, 0), font=fks)
    y += 20
    d.text((X, y), f"그림 표시 짐작: {', '.join(img['flags_guess']) or '정상'}", fill=(0, 0, 0), font=fks)
    y += 20
    d.text((X, y), f"기기: {img['device']['src']}  펠트 {img['felt']['area_frac']}", fill=(0, 0, 0), font=fks)
    y += 26
    for r, c in ROLE_COL.items():
        d.rectangle((X, y + 3, X + 26, y + 15), outline=c, width=3)
        d.text((X + 34, y), r, fill=(0, 0, 0), font=fks)
        y += 19
    d.text((X, y), "꼬리표 = 번호+주인(B아래 R오른쪽 T위 L왼쪽 -없음)", fill=(0, 0, 0), font=fks)
    y += 18
    d.text((X, y), "빨간 꼬리표 = 규칙·모델 갈림, 빨간 고리 = 정답 어긋남", fill=(0, 0, 0), font=fks)
    y += 18
    d.text((X, y), "흰 얇은 선 = 뒷면(역할 없음), 흰 사각형 = 기기", fill=(0, 0, 0), font=fks)
    y += 26
    lc = img.get("label_check")
    if lc:
        d.text((X, y), f"정답({lc['label_src']}) 손패 {lc['label']['closed']}", fill=(0, 0, 0), font=fks)
        y += 18
        d.text((X, y), f"  울기 {lc['label']['melds']} 표시패 {lc['label']['dora_indicators']}+{lc['label']['ura_indicators']}", fill=(0, 0, 0), font=fks)
        y += 18
        for s_ in lc["issues"]:
            d.text((X, y), "! " + s_, fill=(200, 0, 0), font=fks)
            y += 18
        y += 6
    for ln in lines:
        if y > can.height - 24:
            d.text((X, y), f"… 그 밖 {len(lines)} 줄 중 나머지는 draft json", fill=(200, 0, 0), font=fks)
            break
        d.text((X, y), ln, fill=(0, 0, 0), font=fks)
        y += 17
    can.save(path, quality=88)


def sheets_for(rid: str, only: str | None = None) -> int:
    dj = json.loads((DR / "draft" / f"{rid}.json").read_text(encoding="utf-8"))
    rp = DR / "review" / f"{rid}.json"
    rv = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else {}
    n = 0
    for img in dj["images"]:
        if only and img["id"] != only:
            continue
        out = DR / "sheets" / rid / Path(img["name"]).stem
        out.mkdir(parents=True, exist_ok=True)
        rgb = Image.open(V / img["path"]).convert("RGB")
        W, H = img["size"]
        boxes = apply_review(img, (rv.get("images") or {}).get(img["id"]))
        draw_det(rgb, img, boxes, (0, 0, W, H), 0.5, out / "det_all.jpg", 100, 500, 12, f"{img['id']} 전체(0.5배) — 하늘 앞면 · 자홍 뒷면 · 회색 점선 지운 앞면(x) · + 조각 검출 · * 앞→뒤 · ~ 고침")
        ov = 60
        quads = [(0, 0, W // 2 + ov, H // 2 + ov), (W // 2 - ov, 0, W, H // 2 + ov), (0, H // 2 - ov, W // 2 + ov, H), (W // 2 - ov, H // 2 - ov, W, H)]
        for k, rg in enumerate(quads, 1):
            draw_det(rgb, img, boxes, rg, 1.0, out / f"det_q{k}.jpg", 50, 100, 17, f"{img['id']} 조각 q{k} {rg} (원래 크기, 눈금 = 2992 좌표)")
        draw_role(rgb, img, boxes, out / "role.jpg")
        n += 1
    return n


def main():
    args = sys.argv[1:]
    only = None
    if "--image" in args:
        k = args.index("--image")
        only = args[k + 1]
        args = args[:k] + args[k + 2:]
        args = args or [only.split("/")[0]]
    rids = args or sorted(p.stem for p in (DR / "draft").glob("r*.json"))
    tot = 0
    for rid in rids:
        tot += sheets_for(rid, only)
        print(rid, flush=True)
    print("그림", tot)


if __name__ == "__main__":
    main()
