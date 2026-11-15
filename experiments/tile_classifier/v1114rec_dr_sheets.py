"""녹화 프레임(rec1496) 검출·역할 초안 확인 그림(2026-11-15, 녹화 세트 2단계 4). v1114rec_draft.py 다음에(그리고 v1114rec_dr_fit.py 로 고친 뒤 다시).

v1114_dr_sheets.py 와 같은 구성, 크기만 1496 에 맞춤(그리는 함수 draw_det·apply_review·ticks 등은 그 모듈 것을 불러 씀):
그림마다 data/v1114rec/dr/sheets/<판>/<그림 이름>/ 에 6장:
  det_all.jpg      그림 전체를 녹화 원래 크기(1496, 1배)로 — 앞면 = 하늘색, 뒷면 = 자홍, 지운 상자 = 회색 점선(번호 뒤 x). 번호 = dr/draft boxes[].id.
                   번호 뒤 + = 조각 검출에서만 나온 앞면, ~ = 고침. 노란 얇은 선 = 찾은 펠트, 흰 사각형 = 찾은 기기.
  det_q1~q4.jpg    네 조각(왼위·오른위·왼아래·오른아래, 겹침 60px)을 2배로 키워. 작은 패·붙은 패 구분용.
  role.jpg         앞면 상자를 역할 색 테두리로(4/3배). 색·꼬리표 = role_draft(나는 이웃 라벨이 있으면 그것, 없으면 규칙) 또는 고친 값.
                   꼬리표 = 번호 + 주인 자리 글자(B 아래 R 오른쪽 T 위 L 왼쪽, - 없음). 빨간 꼬리표 = 규칙·모델이 갈림, 보라 꼬리표 = 규칙과 이웃 라벨이 갈림.
                   오른쪽 띠에 그림 정보(part·phase 힌트·거치 중·이웃)·범례·갈린 상자 목록.
모든 그림 가장자리 띠의 눈금 = 녹화 1496 좌표(고침 도구 좌표와 같음).
review/<판>.json 이 있으면 그 고침을 반영해 그린다(고친 상자 번호 뒤 ~, 더한 상자 a1·a2…).
  python -X utf8 experiments/tile_classifier/v1114rec_dr_sheets.py [판 id ...] [--image 그림 id]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from v1114_dr_sheets import MARGIN, ROLE_COL, SEAT_CH, apply_review, draw_det, font, tag, ticks  # noqa: E402

R = HERE / "data" / "v1114rec"
DR = R / "dr"
OV = 30  # 조각 겹침(1496 px) — v1114_dr_sheets 의 60(2992)과 같은 범위
ROLE_S = 4 / 3
NBQ = (150, 0, 200)


def role_of(b: dict) -> dict:
    return b.get("final_role") or b.get("role_draft") or b.get("rule") or {}


def draw_role(rgb: Image.Image, img: dict, boxes: list, path: Path):
    W, H = img["size"]
    s = ROLE_S
    part = rgb.resize((int(W * s), int(H * s)), Image.LANCZOS)
    PANEL = 560
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
        fr = role_of(b)
        role, seat = fr.get("role"), fr.get("seat")
        col = ROLE_COL.get(role, (255, 255, 255))
        d.polygon(pts, outline=col, width=3)
        sp = [] if b.get("final_role") else (b.get("split") or [])
        bx = b["box"]
        tx, ty = T((bx[0], bx[1]))
        bg = (220, 0, 0, 230) if ("role" in sp or "seat" in sp) else (*NBQ, 230) if "nb" in sp else (0, 0, 0, 150)
        tag(d, tx + 2, ty + 1, f"{b['id']}{SEAT_CH.get(seat, '?')}", fnt, bg=bg, fg=(255, 255, 255) if sp else col)
        if ("role" in sp or "seat" in sp) and b.get("model"):
            m = b["model"]
            lines.append((f"{b['id']}: 규칙 {b['rule']['role']}/{SEAT_CH[b['rule']['seat']]} · 모델 {m['role']}/{SEAT_CH.get(m['seat'], '-')}"
                          f"({m['conf']:.2f}) · D {m['d_role']}/{SEAT_CH[m['d_seat']]}", (0, 0, 0)))
        if "nb" in sp:
            lines.append((f"{b['id']}: 규칙 {b['rule']['role']}/{SEAT_CH[b['rule']['seat']]} · 이웃({b.get('nb_role_from')}) {b.get('nb_role')}/{SEAT_CH.get(b.get('nb_seat'), '?')}"
                          + (" · 앞뒤 갈림" if b.get("nb_role_conflict") else ""), NBQ))
    ticks(d, 0, 0, W, H, s, 50, 250, font(13))
    X = part.width + 2 * MARGIN + 8
    y = MARGIN
    d.text((X, y), f"{img['id']}", fill=(0, 0, 0), font=fk)
    y += 22
    kind = "공개 장면(end)" if img["format"] == "end" else "프레임"
    d.text((X, y), f"{img['part']} · {kind} · phase 힌트 {img.get('phase_hint') or '-'} · 화료자 {img.get('winner') or '-'}({img.get('winner_src') or ''})",
           fill=(0, 0, 0), font=fks)
    y += 20
    if img.get("setup"):
        d.text((X, y), "카메라 거치 중 장면(setup)", fill=(200, 0, 0), font=fks)
        y += 20
    if img["part"] == "mid":
        for side in ("prev", "next"):
            ni = (img.get("nb_info") or {}).get(side) or {}
            txt = f"{side} {ni.get('id')}: " + (f"앞면 {ni.get('matched')}/{ni.get('nb_faces')} 맞댐, 밀림 {ni.get('shift_1496')}" if ni.get("used") else f"안 씀({ni.get('why')})")
            d.text((X, y), txt[:78], fill=(0, 0, 0), font=fks)
            y += 18
    d.text((X, y), f"그림 표시 짐작: {', '.join(img['flags_guess']) or '정상'}", fill=(0, 0, 0), font=fks)
    y += 20
    d.text((X, y), f"기기: {img['device']['src']}  펠트 {img['felt']['area_frac']}", fill=(0, 0, 0), font=fks)
    y += 26
    for r, c in ROLE_COL.items():
        d.rectangle((X, y + 3, X + 26, y + 15), outline=c, width=3)
        d.text((X + 34, y), r, fill=(0, 0, 0), font=fks)
        y += 19
    for t_ in ("꼬리표 = 번호+주인(B아래 R오른쪽 T위 L왼쪽 -없음)", "빨간 꼬리표 = 규칙·모델 갈림, 보라 = 규칙·이웃 라벨 갈림",
               "색 = 초안 역할(이웃 라벨 우선, 없으면 규칙)", "흰 얇은 선 = 뒷면(역할 없음), 흰 사각형 = 기기", "눈금 = 1496 좌표"):
        d.text((X, y), t_, fill=(0, 0, 0), font=fks)
        y += 18
    y += 8
    for ln, c in lines:
        if y > can.height - 24:
            d.text((X, y), f"… 그 밖 줄은 dr/draft json", fill=(200, 0, 0), font=fks)
            break
        d.text((X, y), ln, fill=c, font=fks)
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
        rgb = Image.open(R / img["path"]).convert("RGB")
        W, H = img["size"]
        boxes = apply_review(img, (rv.get("images") or {}).get(img["id"]))
        draw_det(rgb, img, boxes, (0, 0, W, H), 1.0, out / "det_all.jpg", 50, 250, 11,
                 f"{img['id']} 전체(녹화 원래 크기 1496) — 하늘 앞면 · 자홍 뒷면 · 회색 점선 지운 상자(x) · + 조각 검출 · ~ 고침 · 눈금 1496 좌표")
        quads = [(0, 0, W // 2 + OV, H // 2 + OV), (W // 2 - OV, 0, W, H // 2 + OV), (0, H // 2 - OV, W // 2 + OV, H), (W // 2 - OV, H // 2 - OV, W, H)]
        for k, rg in enumerate(quads, 1):
            draw_det(rgb, img, boxes, rg, 2.0, out / f"det_q{k}.jpg", 25, 50, 15, f"{img['id']} 조각 q{k} {rg} (2배로 키움, 눈금 = 1496 좌표)")
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
    rids = args or sorted(p.stem for p in (DR / "draft").glob("[rn]*.json"))
    tot = 0
    for rid in rids:
        tot += sheets_for(rid, only)
        print(rid, flush=True)
    print("그림", tot)


if __name__ == "__main__":
    main()
