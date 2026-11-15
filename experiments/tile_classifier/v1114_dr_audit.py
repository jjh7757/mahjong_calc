"""독립 검토용 그림·양식(2026-11-15, 검출·역할 세트 3단계 6). v1114_dr_final.py 다음에.

대상 = 개발 그림 전부(흔들림·탁자 아님 뺀 46장) + 학습 그림에서 판마다 2장(random.Random(SEED), 흔들림·탁자 아님·r07 제외, 판에 2장 미만이면 있는 만큼).
그림마다 dr/audit/<판>/<그림 이름>/:
  det_all.jpg  최종 라벨(2단계 반영)만: 하늘 앞면 · 자홍 뒷면, 번호 = final boxes[].id. 2992 좌표 눈금. 초안·지운 상자·고침 표시 없음.
  det_q1~q4.jpg  네 조각 원래 크기(같은 모양).
  role.jpg     앞면 = 역할 색 테두리, 꼬리표 = 번호 + 주인(B R T L -). 규칙·모델 답·갈림·정답 글 없음. 오른쪽 띠에 범례와 그림 종류·화료자(기록 값)만.
목록 dr/audit/_list.json, 검토자가 채울 빈 양식 dr/audit/_review.json(그림마다 seen·missed[{x,y,cls}]·not_tile[번호]·wrong_cls[번호]·
  wrong_role{번호: {role, seat}}·notes).
  python -X utf8 experiments/tile_classifier/v1114_dr_audit.py
"""
from __future__ import annotations

import json
import random
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
V = HERE / "data" / "v1114"
DR = V / "dr"
OUT = DR / "audit"
sys.path.insert(0, str(HERE))
import v1114_dr_sheets as sh  # noqa: E402

SEED = 20261115
PER_ROUND = 2


def draw_role(rgb: Image.Image, im: dict, boxes: list, path: Path):
    W, H = im["size"]
    s = 2 / 3
    part = rgb.resize((int(W * s), int(H * s)), Image.LANCZOS)
    PANEL = 420
    M = sh.MARGIN
    can = Image.new("RGB", (part.width + 2 * M + PANEL, part.height + 2 * M), (255, 255, 255))
    can.paste(part, (M, M))
    d = ImageDraw.Draw(can, "RGBA")
    fnt, fks = sh.font(13), sh.font(13, True)
    T = lambda p: (M + p[0] * s, M + p[1] * s)
    for b in boxes:
        pts = [T(p) for p in b["pts"]]
        if b["cls"] == "back":
            d.polygon(pts, outline=(255, 255, 255, 110), width=1)
            continue
        col = sh.ROLE_COL.get(b["role"], (255, 255, 255))
        d.polygon(pts, outline=col, width=3)
        tx, ty = T((b["box"][0], b["box"][1]))
        sh.tag(d, tx + 2, ty + 1, f"{b['id']}{sh.SEAT_CH.get(b['seat'], '?')}", fnt, bg=(0, 0, 0, 150), fg=col)
    sh.ticks(d, 0, 0, W, H, s, 100, 500, sh.font(13))
    X, y = part.width + 2 * M + 8, M
    for t in (im["id"], f"{'화료 사진' if im['kind'] == 'win' else '판 중 프레임'} · 화료자(기록) {im['winner'] or '-'}"):
        d.text((X, y), t, fill=(0, 0, 0), font=fks)
        y += 20
    y += 6
    for r, c in sh.ROLE_COL.items():
        d.rectangle((X, y + 3, X + 26, y + 15), outline=c, width=3)
        d.text((X + 34, y), r, fill=(0, 0, 0), font=fks)
        y += 19
    for t in ("꼬리표 = 번호+주인(B아래 R오른쪽 T위 L왼쪽 -없음)", "흰 얇은 선 = 뒷면(역할 없음)"):
        d.text((X, y), t, fill=(0, 0, 0), font=fks)
        y += 18
    can.save(path, quality=88)


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    rng = random.Random(SEED)
    picked = []
    for p in sorted((DR / "final").glob("r*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        ok = [im for im in d["images"] if im["det_use"]]
        picked += [im for im in ok if im["split_final"] == "dev"]
        tr = [im for im in ok if im["split_final"] == "train" and d["round"] != "r07_123310"]
        picked += rng.sample(tr, min(PER_ROUND, len(tr)))
    lst, form = [], {}
    for im in picked:
        rid = im["id"].split("/")[0]
        out = OUT / rid / Path(im["name"]).stem
        out.mkdir(parents=True, exist_ok=True)
        rgb = Image.open(V / im["paths"]["q2992"]).convert("RGB")
        W, H = im["size"]
        boxes = [dict(b, status="keep", src="final", edited=None) for b in im["boxes"]]
        img = {"felt": {}, "device": {"cx": -9999, "cy": -9999, "hd": 0}}  # 기기·펠트 선은 그리지 않음
        sh.draw_det(rgb, img, boxes, (0, 0, W, H), 0.5, out / "det_all.jpg", 100, 500, 12, f"{im['id']} 전체(0.5배) — 하늘 앞면 · 자홍 뒷면")
        ov = 60
        for k, rg in enumerate([(0, 0, W // 2 + ov, H // 2 + ov), (W // 2 - ov, 0, W, H // 2 + ov), (0, H // 2 - ov, W // 2 + ov, H), (W // 2 - ov, H // 2 - ov, W, H)], 1):
            sh.draw_det(rgb, img, boxes, rg, 1.0, out / f"det_q{k}.jpg", 50, 100, 17, f"{im['id']} 조각 q{k} {rg} (원래 크기, 눈금 = 2992 좌표)")
        draw_role(rgb, im, boxes, out / "role.jpg")
        lst.append({"id": im["id"], "split": im["split_final"], "kind": im["kind"], "phase": im["phase"], "dir": out.relative_to(DR).as_posix(),
                    "faces": sum(b["cls"] == "face" for b in im["boxes"]), "backs": sum(b["cls"] == "back" for b in im["boxes"])})
        form[im["id"]] = {"seen": False, "missed": [], "not_tile": [], "wrong_cls": [], "wrong_role": {}, "notes": ""}
        print(im["id"], flush=True)
    (OUT / "_list.json").write_text(json.dumps({"_note": f"독립 검토 대상(개발 전부 + 학습 판마다 {PER_ROUND}장, 씨앗 {SEED}). v1114_dr_audit.py", "images": lst},
                                               ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "_review.json").write_text(json.dumps({
        "_format": {"seen": "그림의 모든 상자와 놓친 패를 다 봤으면 true",
                    "missed": "상자가 없는 패 [{x, y, cls: face|back}] — x·y = 2992 좌표(그림 가장자리 눈금), 패 가운데",
                    "not_tile": "패가 아닌 상자 번호(두 번 잡힌 상자·반쪽 상자 포함, 메모에 이유)",
                    "wrong_cls": "앞면·뒷면이 틀린 상자 번호",
                    "wrong_role": "{번호: {role, seat}} — 역할 hand meld river wall pair loose other, seat bottom right top left 또는 null(wall·pair·other)",
                    "notes": "메모",
                    "rules": "data/v1114/dr/review/_FORMAT.json 의 labels 절과 같은 정의"},
        "reviewer": None, "images": form}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(lst), "장")


if __name__ == "__main__":
    main()
