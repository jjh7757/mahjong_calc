"""검출기 학습 데이터셋을 만든다(2026-11-01). det_boxes.py 다음에. 사진은 다시 저장해 EXIF 를 없앤다. API 없음.

토막: 사진마다 통째(긴 변 2040) 1장 + 원본 2040×1530 토막 9장(절반 겹침). 토막에 절반 이상 들어온 상자만 넣는다.
파일 이름 <사진>__<토막>.jpg 로 나눔을 정한다: fold_a 시험 = 매장 오후·B·C·D, fold_b 시험 = 매장 오전·B·C·D. B·C·D 는 두 나눔 모두 시험, final 만 학습에 쓴다.
라벨: 1회차는 YOLO11 + 자체 분류기, 2회차는 1회차 YOLO26 검출을 눈으로 고친 값(boxes_final.json), 3회차는 거기에 det_backs.fixed_faces 와 고른 白(blank/review.json).
  python -I experiments/tile_classifier/det_build.py [--blank-swap | --rim-blank]   --blank-swap: 白 붙여넣기 사본(__b, 3회차), --rim-blank: 흰 테두리 위 白 사본(__ra·__rb, 4회차, det_rim_aug.py), --neg: 거기에 패 아닌 흰 물체(5회차). 모두 학습 전용
  --obb: 7회차 회전 상자(YOLO OBB 라벨 = 종류 + 네 꼭짓점). --backs 와 같이 쓴다. 회전은 det_obb.py 의 rects.json(rot·fixed), 나머지·새 白 은 축 상자. 결과 data/det/ds_r7
  --recolor: 8회차(표 1-69) 재색칠 사본 __c(토막마다 1장, 학습 전용) — 테두리·펠트·뒷면 색을 det_build_fb 팔레트로 바꾸되 시험용 색
             (테두리 검정 (25,25,25)·펠트 파랑 (140,70,30)·뒷면 노랑 (40,170,240))은 뺀다. 난수는 따로 써서 白 증강은 7회차와 같다. 결과 data/det/ds_r8
  --backs: 6회차 앞면·뒷면 2종(뒷면 = 표 1-54 검수 2차 라벨 backs/r2/boxes_r2fb.json, 종류 1). 증강은 뒷면 위에 안 놓는다. 결과는 data/det/ds_r6
결과 data/det/ds/{images,labels}, dataset-metadata.json
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import random

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
OUT = HERE / "data" / "det"
BACKS = "--backs" in sys.argv  # 6회차(표 1-67): 앞면·뒷면 2종
OBB = "--obb" in sys.argv  # 7회차: 회전 상자
RECOLOR = "--recolor" in sys.argv  # 8회차: 재색칠 사본
DS = OUT / ("ds_r8" if RECOLOR else "ds_r7" if OBB else "ds_r6" if BACKS else "ds")
TEST_COLORS = dict(BACKS=(40, 170, 240), FELTS=(140, 70, 30), FRAMES=(25, 25, 25))  # 색 바꾼 테스트 전용(표 1-69) — 학습 재색칠에서 뺀다
TW, TH = 2040, 1530


def label_lines(boxes: list, x0: int, y0: int, w: int, h: int, scale: float = 1.0, cls: int = 0, rects: dict | None = None) -> list[str]:
    """YOLO 라벨 줄. rects 가 있으면(7회차 OBB) 'cls x1 y1 .. x4 y4' — 상자가 rects 에 있으면 그 회전 상자, 없으면 축 상자의 네 꼭짓점.
    어느 쪽이든 토막에 들어가는지는 축 상자로 판단하고(절반 이상), 꼭짓점은 토막 안으로 자른다."""
    lines = []
    for b in boxes:
        bx, by, bw, bh = b
        ix0, iy0, ix1, iy1 = max(bx, x0), max(by, y0), min(bx + bw, x0 + w), min(by + bh, y0 + h)
        if ix1 <= ix0 or iy1 <= iy0 or (ix1 - ix0) * (iy1 - iy0) < 0.5 * bw * bh:
            continue
        if rects is None:
            lines.append(f"{cls} {((ix0 + ix1) / 2 - x0) / w:.6f} {((iy0 + iy1) / 2 - y0) / h:.6f} {(ix1 - ix0) / w:.6f} {(iy1 - iy0) / h:.6f}")
            continue
        import cv2

        r = rects.get(tuple(int(v) for v in b))
        pts = cv2.boxPoints(r) if r else np.array([[bx, by], [bx + bw, by], [bx + bw, by + bh], [bx, by + bh]], np.float32)
        pts = np.clip((pts - [x0, y0]) / [w, h], 0, 1)
        lines.append(f"{cls} " + " ".join(f"{v:.6f}" for v in pts.reshape(-1)))
    return lines


def is_blank(rgb: np.ndarray, b) -> bool:
    """白 판정: 서버 st.ink(무늬 비율) < 0.02(정답 白 0.0, 서버 BLANK 0.01) 이고 안쪽 밝기 중앙 170 이상. 정답 5z 수와 맞는 기준(표 1-62)."""
    import os

    sys.path.insert(0, os.environ.get("RECOGNIZER_REPO", "C:/Users/jjh7757/dev/mahjong-recognizer"))
    from app import seat as st

    x, y, w, h = b
    inner = rgb[int(y + 0.2 * h):int(y + 0.8 * h), int(x + 0.2 * w):int(x + 0.8 * w)]
    if inner.size == 0:
        return False
    return float(st.ink(rgb, tuple(b))) < 0.005 and float(np.median(inner.mean(axis=2))) >= 170  # 0.02 는 옅은 무늬 패가 섞였다(bank_sheet 확인)


def blank_bank(rows: dict, blanks: dict) -> list[Image.Image]:
    """라벨 중 白 상자(무늬 없음)의 크롭. 붙여넣기 증강 재료. 세운 모양(세로가 길게)으로 맞춘다."""
    bank = []
    for name, r in rows.items():
        im = Image.open(r["path"]).convert("RGB")
        rgb = np.asarray(im)
        for b in list(r["boxes"]) + blanks.get(name, []):
            if is_blank(rgb, b):
                c = im.crop((b[0], b[1], b[0] + b[2], b[1] + b[3]))
                bank.append(c.rotate(90, expand=True) if c.width > c.height else c)
    return bank


def swap_blanks(im: Image.Image, boxes: list, bank: list, rng: random.Random, frac: float = 0.2) -> Image.Image:
    """상자의 [frac] 만큼을 白 크롭으로 덮는다(라벨은 그대로). 흰 테두리 위 울기·손패 줄 안의 白 을 흉내 낸다."""
    out = im.copy()
    for b in boxes:
        if rng.random() >= frac:
            continue
        c = rng.choice(bank)
        if b[2] > b[3]:
            c = c.rotate(90, expand=True)
        out.paste(c.resize((max(1, b[2]), max(1, b[3])), Image.BILINEAR), (b[0], b[1]))
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    shutil.rmtree(DS, ignore_errors=True)
    (DS / "images").mkdir(parents=True)
    (DS / "labels").mkdir(parents=True)
    src = OUT / "boxes_final.json" if (OUT / "boxes_final.json").exists() else OUT / "boxes.json"  # 2회차부터 det_review.py 결과
    rows = json.loads(src.read_text(encoding="utf-8"))
    # 3회차(2026-11-04): det_backs.fixed_faces(지우기·더하기) + 사람이 고른 白(det_blank_cands.py → blank/review.json {이름: [후보 번호]})
    from det_backs import fixed_backs, fixed_faces

    blank_dir = OUT / "blank"
    blanks: dict = {}
    if (blank_dir / "review.json").exists():
        cands = json.loads((blank_dir / "cands.json").read_text(encoding="utf-8"))
        picked = json.loads((blank_dir / "review.json").read_text(encoding="utf-8"))
        blanks = {name: [cands[name][i]["box"] for i in idx] for name, idx in picked.items()}
        print("白 더함", sum(len(v) for v in blanks.values()), "장", flush=True)
    # 3회차: 白 붙여넣기 증강(__b, 학습 전용). 라벨 白 은 2,241개 중 16개쯤이라 검출기가 못 배운다(표 1-62). 토막마다 상자 20% 를 白 크롭으로 덮은 사본을 더한다.
    swap = "--blank-swap" in sys.argv
    # 4회차(표 1-64): 펠트 가장자리·흰 테두리 위 白 증강(det_rim_aug, 실제 白 크롭을 모서리·홈째로, 펠트 경계 띠에 1~4장 새로).
    # 재료를 fold 별로 나눠 누수를 막는다: 사본 __ra(재료 오전+기타, fold_a 학습 전용), __rb(재료 오후+기타, fold_b 학습 전용). --blank-swap 대신 쓴다.
    rim = "--rim-blank" in sys.argv
    NEG = 4 if "--neg" in sys.argv else 0  # 5회차(표 1-65): 증강 사본마다 패 아닌 흰 물체 4개(라벨 없음)
    rim_banks: dict = {}
    if rim:
        import det_rim_aug as dra

        felts = {k: v["felt"] for k, v in json.loads((OUT.parent / "zone_points" / "labels.json").read_text(encoding="utf-8")).items() if v.get("felt")}
        (OUT / "blank" / "rim_check").mkdir(parents=True, exist_ok=True)
        rim_banks = dra.build_bank({k: dict(v, boxes=list(v["boxes"]) + blanks.get(k, [])) for k, v in rows.items()}, fixed_faces, is_blank)
        print("白 재료(부분별)", rim_banks["_count"], "fold_a 용", len(rim_banks["a"]), "fold_b 용", len(rim_banks["b"]), flush=True)
    bank = blank_bank(rows, blanks) if swap else []
    rng = random.Random(20261104)
    if swap:
        print("白 크롭 재료", len(bank), "장", flush=True)
        sheet = Image.new("RGB", (10 * 100, (-(-len(bank) // 10)) * 130), "black")
        for k, c in enumerate(bank):
            sheet.paste(c.resize((90, 120)), ((k % 10) * 100, (k // 10) * 130))
        (OUT / "blank").mkdir(exist_ok=True)
        sheet.save(OUT / "blank" / "bank_sheet.jpg", quality=85)
    r2fb = json.loads((OUT / "backs" / "r2" / "boxes_r2fb.json").read_text(encoding="utf-8")) if BACKS else {}
    rects7 = json.loads((OUT / "obb" / "rects.json").read_text(encoding="utf-8")) if OBB else {}
    n = empty = aug = nback = 0
    if RECOLOR:
        import cv2
        import det_build_fb as fb
        from det_backs import back_mask, poly_mask

        for k, c in TEST_COLORS.items():
            setattr(fb, k, [x for x in getattr(fb, k) if x != c])
        rng_rc = random.Random(20261108)
        zp = {k: v["felt"] for k, v in json.loads((OUT.parent / "zone_points" / "labels.json").read_text(encoding="utf-8")).items() if v.get("felt")}
        rc_dir = OUT / "obb" / "recolor_check"
        rc_dir.mkdir(parents=True, exist_ok=True)
    for name, r in rows.items():
        r = dict(r, boxes=fixed_faces(name, r["boxes"]) + blanks.get(name, []))
        backs = [list(b) for b in fixed_backs(name, r2fb.get(name, {}).get("backs", []))
                 if max((max(0, min(b[0] + b[2], f[0] + f[2]) - max(b[0], f[0])) * max(0, min(b[1] + b[3], f[1] + f[3]) - max(b[1], f[1])) for f in r["boxes"]), default=0)
                 <= 0.5 * b[2] * b[3]]  # 앞면에 절반 넘게 덮인 뒷면은 뺀다(det_build_fb.clean_backs 와 같은 기준)
        nback += len(backs)
        if OBB:
            items = rects7[name]["items"]
            rq = {c: {tuple(int(v) for v in it["box"]): (tuple(it["rect"][0]), tuple(it["rect"][1]), it["rect"][2]) for it in items if it["cls"] == c and it["status"] in ("rot", "fixed")} for c in (0, 1)}
        else:
            rq = {0: None, 1: None}
        back_lines = lambda x0, y0, w, h: label_lines(backs, x0, y0, w, h, cls=1, rects=rq[1])
        face_lines = lambda boxes, x0, y0, w, h: label_lines(boxes, x0, y0, w, h, rects=rq[0])
        im = Image.open(r["path"]).convert("RGB")
        W, H = im.size
        whole = im.resize((2040, round(H * 2040 / W)))
        whole.save(DS / "images" / f"{name}__w.jpg", quality=90)
        (DS / "labels" / f"{name}__w.txt").write_text("\n".join(face_lines(r["boxes"], 0, 0, W, H) + back_lines(0, 0, W, H)), encoding="utf-8")
        n += 1
        swapped = swap_blanks(im, r["boxes"], bank, rng) if swap and bank else None
        rim_copies: list = []  # (접미사, 그림, 상자)
        rim_n = 0
        if rim and name in felts:
            pt = dra.part(name)
            for tag, fold in (("ra", "a"), ("rb", "b")):
                # __ra 는 fold_a 학습(오전·기타)에만, __rb 는 fold_b 학습(오후·기타)에만 쓰이므로 그 사진만 만든다. B·C·D 는 늘 시험이라 안 만든다.
                if pt == "bcd" or (fold == "a" and pt == "pm") or (fold == "b" and pt == "am") or not rim_banks[fold]:
                    continue
                aug_im, aug_boxes, k = dra.augment(im, r["boxes"], felts[name], rim_banks[fold], rng, negatives=NEG, avoid=backs)
                rim_copies.append((tag, aug_im, aug_boxes))
                rim_n += k
                if len(rim_copies) == 1:
                    from PIL import ImageDraw

                    vis = aug_im.copy()
                    dv = ImageDraw.Draw(vis)
                    for b in aug_boxes[len(r["boxes"]):]:
                        dv.rectangle((b[0] - 6, b[1] - 6, b[0] + b[2] + 6, b[1] + b[3] + 6), outline="red", width=4)
                    vis.resize((W // 3, H // 3)).save(OUT / "blank" / "rim_check" / f"{name}.jpg", quality=80)
        recolored = None
        if RECOLOR and name in zp:  # 사진 한 장을 한 번 칠하고 토막마다 자른다(det_build_fb 와 같은 마스크: 뒷면·펠트·탁자 테두리 흰 띠)
            bgr = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)
            m = cv2.resize(cv2.imread(str(OUT / "backs" / "masks" / f"{name}.png")), (W, H), interpolation=cv2.INTER_NEAREST)
            inside = np.zeros((H, W), np.uint8)
            for x, y, w, h in backs:
                inside[max(0, y):y + h, max(0, x):x + w] = 255
            hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
            white = ((hsv[..., 1] < 55) & (hsv[..., 2] > 120)).astype(np.uint8) * 255
            frame = cv2.bitwise_and(white, cv2.bitwise_and(poly_mask(bgr.shape, zp[name], 0.14), cv2.bitwise_not(poly_mask(bgr.shape, zp[name], 0.012))))
            for x, y, w, h in list(r["boxes"]) + backs:  # 테두리에 놓인 패는 칠하지 않는다
                frame[max(0, y - 6):y + h + 6, max(0, x - 6):x + w + 6] = 0
            recolored = Image.fromarray(cv2.cvtColor(fb.recolor(bgr, cv2.bitwise_and(back_mask(bgr, loose=True), inside), m[..., 1], frame, rng_rc), cv2.COLOR_BGR2RGB))
            recolored.resize((W // 4, H // 4)).save(rc_dir / f"{name}.jpg", quality=80)
        for i, y0 in enumerate((0, (H - TH) // 2, H - TH)):
            for j, x0 in enumerate((0, (W - TW) // 2, W - TW)):
                lines = face_lines(r["boxes"], x0, y0, TW, TH)
                empty += not lines
                lines = lines + back_lines(x0, y0, TW, TH)
                im.crop((x0, y0, x0 + TW, y0 + TH)).save(DS / "images" / f"{name}__{i}{j}.jpg", quality=90)
                (DS / "labels" / f"{name}__{i}{j}.txt").write_text("\n".join(lines), encoding="utf-8")
                n += 1
                if recolored is not None:
                    recolored.crop((x0, y0, x0 + TW, y0 + TH)).save(DS / "images" / f"{name}__{i}{j}__c.jpg", quality=90)
                    (DS / "labels" / f"{name}__{i}{j}__c.txt").write_text("\n".join(lines), encoding="utf-8")
                    aug += 1
                if swapped is not None and len(lines) >= 3:
                    swapped.crop((x0, y0, x0 + TW, y0 + TH)).save(DS / "images" / f"{name}__{i}{j}__b.jpg", quality=90)
                    (DS / "labels" / f"{name}__{i}{j}__b.txt").write_text("\n".join(lines), encoding="utf-8")
                    aug += 1
                for tag, aug_im, aug_boxes in rim_copies:
                    rl = face_lines(aug_boxes, x0, y0, TW, TH)
                    if len(rl) >= 3:
                        rl = rl + back_lines(x0, y0, TW, TH)
                        aug_im.crop((x0, y0, x0 + TW, y0 + TH)).save(DS / "images" / f"{name}__{i}{j}__{tag}.jpg", quality=90)
                        (DS / "labels" / f"{name}__{i}{j}__{tag}.txt").write_text("\n".join(rl), encoding="utf-8")
                        aug += 1
        if rim:
            print(name, "테두리 白", rim_n, flush=True)
        else:
            print(name, flush=True)
    if swap or rim:
        print("白 증강 토막", aug, flush=True)
    meta = {"title": "mahjong tile obb r8", "id": "jjh7757/mahjong-tile-obb-r8"} if RECOLOR else {"title": "mahjong tile obb r7", "id": "jjh7757/mahjong-tile-obb-r7"} if OBB else {"title": "mahjong tile fb r6", "id": "jjh7757/mahjong-tile-fb-r6"} if BACKS else {"title": "mahjong tile faces", "id": "jjh7757/mahjong-tile-faces"}
    (DS / "dataset-metadata.json").write_text(json.dumps(dict(meta, licenses=[{"name": "unknown"}]), indent=1), encoding="utf-8")
    size = sum(p.stat().st_size for p in DS.rglob("*") if p.is_file())
    ims = list((DS / "images").iterdir())
    print("이미지", n, "상자 없는 토막", empty, "뒷면 상자", nback, "MB", size // 2**20, "| 커널 대조용 이미지", len(ims), "총 바이트", sum(p.stat().st_size for p in ims))


if __name__ == "__main__":
    main()
