"""녹화 프레임(rec1496) 독립 검토용 그림·양식(2026-11-15, 녹화 세트 3단계 7). v1114rec_dr_final*.py 다음에. 다시 돌려도 같은 결과.

v1114_dr_audit.py 와 같은 구성(최종 라벨만 그림 — 초안·지운 상자·고침 표시·모델 답 없음), 크기만 1496 에 맞춤:
대상(det_use 그림만, 씨앗 SEED = 20261115):
  ① mid·new 의 개발 그림 전부
  ② mid·new 의 학습 그림에서 판마다 2장(random.Random(SEED), 판에 2장 미만이면 있는 만큼)
  ③ pair 24장: 짝 고침 세 그림(pair/overrides.json) + 짝 눈 확인 occluded 로 상자를 뺀 그림 전부 + 나머지는 random.Random(SEED) 무작위
그림마다 dr/audit/<판>/<그림 이름>/:
  det_all.jpg    녹화 원래 크기(1배), 하늘 앞면 · 자홍 뒷면, 번호 = 최종 boxes[].id, 눈금 = 1496 좌표.
  det_q1~q4.jpg  네 조각(겹침 30px)을 2배로.
  role.jpg       앞면 = 역할 색 테두리, 꼬리표 = 번호 + 주인(B R T L -), 4/3배. 오른쪽 띠에 그림 종류·phase·화료자(기록 값)·범례만.
목록 dr/audit/_list.json, 몫 dr/audit/_shares.json(A1·A2·A3 — 개발 그림을 먼저 돌려 나누고 그다음 학습 그림, 그림 수 비슷하게),
빈 양식 dr/audit/_review_<몫>.json(그림마다 seen·missed[{x,y,cls}]·not_tile[번호]·wrong_cls[번호]·wrong_role{번호:{role,seat}}·bad_box[번호]·flags_wrong·notes).
  python -X utf8 experiments/tile_classifier/v1114rec_dr_audit.py
"""
from __future__ import annotations

import random
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import v1114_dr_sheets as sh  # noqa: E402
import v1114rec_dr_final_pair as FP  # noqa: E402
from v1114rec_dr_common import DR, R, final_all, jsave  # noqa: E402

OUT = DR / "audit"
SEED = 20261115
PER_ROUND = 2
N_PAIR = 24
SHARES = ("A1", "A2", "A3")
OV = 30
ROLE_S = 4 / 3


def draw_role(rgb: Image.Image, im: dict, boxes: list, path: Path):
    W, H = im["size"]
    s = ROLE_S
    part = rgb.resize((int(W * s), int(H * s)), Image.LANCZOS)
    PANEL = 440
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
    sh.ticks(d, 0, 0, W, H, s, 50, 250, sh.font(13))
    X, y = part.width + 2 * M + 8, M
    kind = "화료 사진" if im["kind"] == "win" else ("공개 장면" if im["format"] == "end" else "판 중 프레임")
    for t in (im["id"], f"{im['part']} · {kind} · phase {im['phase']}", f"화료자(기록) {im['winner'] or '-'}",
              f"그림 표시 {', '.join(im['flags']) or '정상'}"):
        d.text((X, y), t, fill=(0, 0, 0), font=fks)
        y += 20
    y += 6
    for r, c in sh.ROLE_COL.items():
        d.rectangle((X, y + 3, X + 26, y + 15), outline=c, width=3)
        d.text((X + 34, y), r, fill=(0, 0, 0), font=fks)
        y += 19
    for t in ("꼬리표 = 번호+주인(B아래 R오른쪽 T위 L왼쪽 -없음)", "흰 얇은 선 = 뒷면(역할 없음)", "눈금 = 1496 좌표"):
        d.text((X, y), t, fill=(0, 0, 0), font=fks)
        y += 18
    can.save(path, quality=88)


def pick() -> list[tuple[dict, str]]:
    ims = [im for im in final_all() if im["det_use"]]
    rng = random.Random(SEED)
    out = []
    rounds: dict = {}
    for im in ims:
        if im["part"] in ("mid", "new"):
            rounds.setdefault(im["id"].split("/")[0], []).append(im)
    for rid in sorted(rounds):
        L = sorted(rounds[rid], key=lambda x: x["ms"])
        out += [(im, "mid_new_dev") for im in L if im["split_final"] == "dev"]
        tr = [im for im in L if im["split_final"] == "train"]
        out += [(im, "mid_new_train_sample") for im in rng.sample(tr, min(PER_ROUND, len(tr)))]
    pair = sorted((im for im in ims if im["part"] == "pair"), key=lambda x: x["id"])
    ov = set(FP.overrides())
    occl = {k[0] for k, v in FP.verdicts().items() if v["verdict"] == "occluded"}
    must = [im for im in pair if im["id"] in ov] + [im for im in pair if im["id"] in occl and im["id"] not in ov]
    rest = [im for im in pair if im["id"] not in ov and im["id"] not in occl]
    out += [(im, "pair_override" if im["id"] in ov else "pair_occluded") for im in must]
    out += [(im, "pair_random") for im in random.Random(SEED).sample(rest, max(0, N_PAIR - len(must)))]
    return out


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    picked = pick()
    lst = []
    for im, why in picked:
        rid = im["id"].split("/")[0]
        out = OUT / rid / Path(im["name"]).stem
        out.mkdir(parents=True, exist_ok=True)
        rgb = Image.open(R / im["path"]).convert("RGB")
        W, H = im["size"]
        boxes = [dict(b, status="keep", src="final", edited=None) for b in im["boxes"]]
        img = {"felt": {}, "device": {"cx": -9999, "cy": -9999, "hd": 0}}
        sh.draw_det(rgb, img, boxes, (0, 0, W, H), 1.0, out / "det_all.jpg", 50, 250, 11, f"{im['id']} 전체(녹화 1496, 1배) — 하늘 앞면 · 자홍 뒷면 · 눈금 1496 좌표")
        for k, rg in enumerate([(0, 0, W // 2 + OV, H // 2 + OV), (W // 2 - OV, 0, W, H // 2 + OV), (0, H // 2 - OV, W // 2 + OV, H), (W // 2 - OV, H // 2 - OV, W, H)], 1):
            sh.draw_det(rgb, img, boxes, rg, 2.0, out / f"det_q{k}.jpg", 25, 50, 15, f"{im['id']} 조각 q{k} {rg} (2배, 눈금 = 1496 좌표)")
        draw_role(rgb, im, boxes, out / "role.jpg")
        lst.append({"id": im["id"], "part": im["part"], "split": im["split_final"], "kind": im["kind"], "phase": im["phase"], "why": why,
                    "dir": out.relative_to(DR).as_posix(), "faces": sum(b["cls"] == "face" for b in im["boxes"]),
                    "backs": sum(b["cls"] == "back" for b in im["boxes"])})
        print(im["id"], why, flush=True)
    # 몫: 개발 먼저 돌려 나누고 그다음 학습(그림 수·개발 수 고르게)
    order = sorted(lst, key=lambda x: (x["split"] != "dev", x["part"], x["id"]))
    shares = {s: [] for s in SHARES}
    for k, x in enumerate(order):
        shares[SHARES[k % len(SHARES)]].append(x["id"])
    sh_of = {i: s for s, L in shares.items() for i in L}
    for x in lst:
        x["share"] = sh_of[x["id"]]
    jsave(OUT / "_list.json", {"_note": f"독립 검토 대상(v1114rec_dr_audit.py, 씨앗 {SEED}): mid·new 개발 전부 + mid·new 학습 판마다 {PER_ROUND}장 + pair {N_PAIR}장"
                                         "(고친 세 그림 + occluded 로 상자 뺀 그림 전부 + 무작위). why = 고른 까닭.", "images": lst})
    jsave(OUT / "_shares.json", {"_note": "몫별 그림 id. 개발 그림을 먼저 세 몫에 돌려 나눔.",
                                 **{s: {"n": len(L), "dev": sum(1 for i in L if next(x for x in lst if x["id"] == i)["split"] == "dev"), "images": L}
                                    for s, L in shares.items()}})
    fmt = {"seen": "그림의 모든 상자와 놓친 패를 다 봤으면 true",
           "missed": "상자가 없는 패 [{x, y, cls: face|back}] — x·y = 녹화 1496 좌표(그림 가장자리 눈금), 패 가운데",
           "not_tile": "패가 아닌 상자 번호(두 번 잡힌 상자·반쪽 상자 포함, 메모에 이유)",
           "wrong_cls": "앞면·뒷면이 틀린 상자 번호",
           "wrong_role": "{번호: {role, seat}} — 역할 hand meld river wall pair loose other, seat bottom right top left 또는 null(wall·pair·other)",
           "bad_box": "패는 맞지만 상자가 크게 어긋난 번호(패 넓이의 절반 가까이 벗어남)",
           "flags_wrong": "그림 단위 표시(phase·between·흔들림 등)가 틀렸으면 맞는 값을 글로, 맞으면 null",
           "notes": "메모",
           "rules": "data/v1114rec/dr/review/_FORMAT.json 의 labels 절과 같은 정의(뚜렷이 절반 넘게 보일 때만 상자, 손에 들린 패 포함, 화면 속 패는 패 아님)"}
    for s, L in shares.items():
        jsave(OUT / f"_review_{s}.json", {"_format": fmt, "share": s, "reviewer": None,
                                          "images": {i: {"seen": False, "missed": [], "not_tile": [], "wrong_cls": [], "wrong_role": {}, "bad_box": [],
                                                         "flags_wrong": None, "notes": ""} for i in L}})
    from collections import Counter
    print(len(lst), "장", dict(Counter(x["why"] for x in lst)), {s: len(L) for s, L in shares.items()})


if __name__ == "__main__":
    main()
