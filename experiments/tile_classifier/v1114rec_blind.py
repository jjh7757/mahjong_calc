"""녹화 프레임(rec1496) 크롭 세트 독립 검토용 가린 그림(2026-11-15, 녹화 세트 3단계). v1114rec_crops.py 다음에. v1114_blind.py 와 같은 꼴.

  python -X utf8 experiments/tile_classifier/v1114rec_blind.py make      → data/v1114rec/blind/{D,T,P,R}_NN.jpg, answers_{D,T,P,R}.json(빈 양식),
                                                                           _key.json(정답 열쇠 — 검토자는 열지 않음), _shares.json(검토자 둘 몫)
  python -X utf8 experiments/tile_classifier/v1114rec_blind.py compare   → 채운 answers 와 열쇠를 맞대어 blind/compare.json(다른 칸·빈 칸·못 읽음 칸)

묶음(계획 세션이 정함):
  D = mid·new 의 개발 실물 패(unit) 전부, 한 unit 에 크롭 한 장 — 눈 확인 대조표에 실렸던 그림(track best)이 아닌 그림의 상자(씨앗 고정 무작위), 없으면 있는 것.
  T = mid·new 의 학습 unit 에서 종류별로 고르게 300개(종류마다 섞어 돌아가며 하나씩). 한 종류 안에서는 new 가 절반 아래면 new 를 먼저 — new 가 모자라면 되는 만큼.
  P = pair 크롭에서 무작위 200장(개발 60 · 학습 140) — 2992 에서 단 라벨이 녹화 화질에서도 읽히는지.
  R = crops/review_todo.json("다시 볼 것") 상자 전부.
그림: 한 장 20칸(4×5). 칸 = 왼쪽 크롭(분류기가 읽은 방향으로 세움, 긴 변 화면 약 200px 로 키움) + 오른쪽 둘레 그림(원래 방향, 노란 테두리 = 그 상자, 220px 로 키움).
글은 칸 번호만. 칸 순서는 종류와 무관하게 섞음(씨앗 고정). 번호는 묶음 안에서 1부터.
몫: B1 = D + R, B2 = T + P(장 수가 비슷하면 그대로).
"""
from __future__ import annotations

import json
import random
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
R = HERE / "data" / "v1114rec"
BL = R / "blind"
Q = "rec1496"
SEED = 20261115
T_N, P_DEV, P_TRAIN = 300, 60, 140
COLS, ROWS = 4, 5
CW, CH = 470, 330
TILE_H, TILE_W = 250, 200
CTX = 220
FONTB = "C:/Windows/Fonts/arialbd.ttf"
BUNDLES = ("D", "T", "P", "R")
ANS_HELP = ("칸 번호마다 tile 에 종류를 적는다: 1m~9m·1p~9p·1s~9s, 적5 = 0m·0p·0s, 1z 동 2z 남 3z 서 4z 북 5z 백 6z 발 7z 중. "
            "앞면 패가 아니면(뒷면·패 일부만·손·다른 물건) 'not_tile', 앞면 패인데 흐림·가림·작아서 무늬로 종류를 가를 수 없으면 'unreadable'(note 에 이유). "
            "왼쪽 크롭은 분류기가 읽은 방향이라 뒤집혀 보일 수 있다 — 오른쪽 둘레 그림(노란 테두리)이 원래 방향. "
            "녹화 그림(1496)이라 패가 작다(원래 긴 변 약 65px를 키움). 적5(빨간 5)와 그냥 5 를 꼭 가른다.")


def jl(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def context(rgb: np.ndarray, rect, box, side: int = CTX) -> Image.Image:
    if rect is not None:
        pts = cv2.boxPoints((tuple(rect[0]), tuple(rect[1]), rect[2]))
        x, y = pts.min(axis=0)
        w, h = pts.max(axis=0) - (x, y)
    else:
        x, y, w, h = box
        pts = np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], float)
    H, W = rgb.shape[:2]
    Rr = int(max(w, h) * 1.5)
    cx, cy = int(x + w / 2), int(y + h / 2)
    x0, y0 = max(0, cx - Rr), max(0, cy - Rr)
    part = Image.fromarray(rgb[y0:min(H, cy + Rr), x0:min(W, cx + Rr)]).copy()
    sc = side / max(part.size)
    part = part.resize((max(1, round(part.width * sc)), max(1, round(part.height * sc))), Image.LANCZOS)
    ImageDraw.Draw(part).polygon([((px - x0) * sc, (py - y0) * sc) for px, py in pts], outline=(255, 230, 0), width=3)
    return part


def pick_crop(xs: list[dict], best: dict, rng: random.Random) -> dict:
    other = [x for x in xs if x["image"] != best["image"]]
    return rng.choice(sorted(other or xs, key=lambda x: x["id"]))


def make():
    from v1114_crops import cut

    rows = jl(R / "crops" / "index.json")
    todo = jl(R / "crops" / "review_todo.json")
    man = jl(R / "manifest.json")
    best = {}
    for r in man["rounds"]:
        for t in jl(R / "draft" / f"{r['id']}.json")["tracks"]:
            best[(r["id"], t["tid"])] = t["best"]
    units = defaultdict(list)
    for x in rows:
        if x["part"] in ("mid", "new"):
            units[x["unit"]].append(x)
    rng = random.Random(SEED)
    # D
    dev_units = sorted(u for u, xs in units.items() if xs[0]["split"] == "dev")
    D = [pick_crop(units[u], best[(units[u][0]["round"], units[u][0]["tid"])], rng) for u in dev_units]
    # T: 종류별로 섞은 뒤 돌아가며, 종류 안에서 new 를 절반 이상
    by_tile = defaultdict(lambda: {"new": [], "mid": []})
    for u in sorted(u for u, xs in units.items() if xs[0]["split"] == "train"):
        by_tile[units[u][0]["tile"]][units[u][0]["part"]].append(u)
    for k in sorted(by_tile):
        for p in ("new", "mid"):
            rng.shuffle(by_tile[k][p])
    T_units, n_part = [], Counter()
    while len(T_units) < T_N and any(v["new"] or v["mid"] for v in by_tile.values()):
        for k in sorted(by_tile):
            v = by_tile[k]
            order = ("new", "mid") if n_part["new"] <= n_part["mid"] else ("mid", "new")
            for p in order:
                if v[p]:
                    T_units.append(v[p].pop())
                    n_part[p] += 1
                    break
            if len(T_units) >= T_N:
                break
    T = [pick_crop(units[u], best[(units[u][0]["round"], units[u][0]["tid"])], rng) for u in T_units]
    # P
    pr = sorted((x for x in rows if x["part"] == "pair"), key=lambda x: x["id"])
    P = rng.sample([x for x in pr if x["split"] == "dev"], P_DEV) + rng.sample([x for x in pr if x["split"] == "train"], P_TRAIN)
    Rb = list(todo)
    if BL.exists():
        shutil.rmtree(BL)
    BL.mkdir(parents=True)
    key, counts = {}, {}
    f_no = ImageFont.truetype(FONTB, 30)
    cache = {}

    def rgb_of(path):
        if path not in cache:
            if len(cache) > 8:
                cache.pop(next(iter(cache)))
            cache[path] = np.asarray(Image.open(R / path).convert("RGB"))
        return cache[path]

    img_path = {it["id"]: it["path"] for it in man["items"]}
    for name, cells in (("D", D), ("T", T), ("P", P), ("R", Rb)):
        cells = list(cells)
        rng.shuffle(cells)
        key[name] = {}
        per = COLS * ROWS
        for s in range(0, len(cells), per):
            sheet = Image.new("RGB", (COLS * CW, ROWS * CH), (255, 255, 255))
            dr = ImageDraw.Draw(sheet)
            for k, c in enumerate(cells[s:s + per]):
                no = s + k + 1
                path = c.get("image_path") or img_path[c["image"]]
                rgb = rgb_of(path)
                if name == "R":
                    tim = cut(rgb, {"rect": c["rect"], "box": c["box"], "rot": c["rot"]}, 1.0)
                else:
                    tim = Image.open(R / c["paths"][Q]).convert("RGB")
                ctx = context(rgb, c["rect"], c["box"])
                x0, y0 = (k % COLS) * CW, (k // COLS) * CH
                dr.rectangle((x0 + 2, y0 + 2, x0 + CW - 3, y0 + CH - 3), outline=(150, 150, 150), width=2)
                sc = min(TILE_H / tim.height, TILE_W / tim.width)
                tim = tim.resize((max(1, round(tim.width * sc)), max(1, round(tim.height * sc))), Image.LANCZOS)
                sheet.paste(tim, (x0 + 10 + (TILE_W - tim.width) // 2, y0 + 40 + (TILE_H - tim.height) // 2))
                sheet.paste(ctx, (x0 + 20 + TILE_W + 10, y0 + 40 + (TILE_H - ctx.height) // 2))
                dr.text((x0 + 10, y0 + 4), str(no), fill=(0, 0, 0), font=f_no)
                sh = f"{name}_{s // per + 1:02d}.jpg"
                if name == "R":
                    key[name][str(no)] = {"part": c["part"], "round": c["round"], "tid": c["tid"], "image": c["image"], "i": c["i"], "why": c["why"],
                                          "read": c["read"], "track_draft": c["track_draft"], "verdict": c["verdict"], "label_if_kept": c.get("label_if_kept"),
                                          "per_image": c.get("per_image"), "fix_tile": c.get("fix_tile"), "split": c["split"], "note": c["note"], "sheet": sh}
                else:
                    key[name][str(no)] = {"crop_id": c["id"], "part": c["part"], "unit": c["unit"], "label": c["tile"], "round": c["round"], "tid": c["tid"],
                                          "image": c["image"], "i": c["i"], "src": c["src"], "draft_src": c["draft_src"], "read": c["read"], "conf": c["conf"],
                                          "note": c["note"], "split": c["split"], "v1114_crop_id": c["v1114_crop_id"], "sheet": sh}
            sheet.save(BL / f"{name}_{s // per + 1:02d}.jpg", quality=90)
        counts[name] = {"cells": len(cells), "sheets": (len(cells) + per - 1) // per}
        ans = {"bundle": name, "how": ANS_HELP, "reviewer": None, "done": False,
               "sheets": [f"{name}_{i + 1:02d}.jpg" for i in range(counts[name]["sheets"])],
               "answers": {str(i + 1): {"tile": None, "note": ""} for i in range(len(cells))}}
        (BL / f"answers_{name}.json").write_text(json.dumps(ans, ensure_ascii=False, indent=1), encoding="utf-8")
    key["_meta"] = {"seed": SEED, "counts": counts,
                    "T_tiles": dict(Counter(units[u][0]["tile"] for u in T_units)), "T_parts": dict(n_part),
                    "T_rounds": dict(Counter(u.split("#")[1] for u in T_units)),
                    "D_parts": dict(Counter(c["part"] for c in D)),
                    "D_best_image_used": sum(1 for c in D if c["image"] == best[(c["round"], c["tid"])]["image"]),
                    "P_split": dict(Counter(c["split"] for c in P)), "P_tiles": dict(Counter(c["tile"] for c in P)),
                    "R_why": dict(Counter(c["why"] for c in Rb))}
    (BL / "_key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    shares = {}
    for who, names in (("B1", ("D", "R")), ("B2", ("T", "P"))):
        shares[who] = {"bundles": list(names), "cells": sum(counts[n]["cells"] for n in names), "sheets_n": sum(counts[n]["sheets"] for n in names),
                       "sheets": [f"{n}_{i + 1:02d}.jpg" for n in names for i in range(counts[n]["sheets"])],
                       "answers": [f"answers_{n}.json" for n in names]}
    shares["_note"] = "검토자 둘 몫. 각자 자기 answers_<묶음>.json 만 채운다. _key.json 은 열지 않는다. 양식 설명은 answers 파일 how 칸."
    (BL / "_shares.json").write_text(json.dumps(shares, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(key["_meta"], ensure_ascii=False, indent=1))
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "sheets"} for k, v in shares.items() if k != "_note"}, ensure_ascii=False))


def compare():
    key = jl(BL / "_key.json")
    res = {}
    for name in BUNDLES:
        p = BL / f"answers_{name}.json"
        if not p.exists() or name not in key:
            continue
        ans = jl(p)["answers"]
        diff, blank, unread, same = [], [], [], 0
        for no, k in key[name].items():
            a = ans.get(no) or {}
            got = a.get("tile")
            want = k.get("label") if name != "R" else (k.get("label_if_kept") or k.get("per_image") or k.get("fix_tile") or k.get("track_draft"))
            if got in (None, ""):
                blank.append(no)
            elif got in ("unreadable", "unsure"):
                unread.append({"no": no, "answer": got, "answer_note": a.get("note", ""), "key": want, **k})
            elif got == want:
                same += 1
            else:
                diff.append({"no": no, "answer": got, "answer_note": a.get("note", ""), "key": want, **k})
        res[name] = {"cells": len(key[name]), "same": same, "diff": len(diff), "unreadable": len(unread), "blank": len(blank), "blank_nos": blank,
                     "diff_by_answer": dict(Counter(d["answer"] for d in diff)), "diffs": diff, "unreadables": unread}
        if name == "R":
            res[name]["note"] = "R 의 key 는 정답이 아니라 규칙이 막지 않았다면 붙었을 라벨(또는 per_image·fix·초안) — 다른 칸이 곧 틀림은 아님"
        print(name, {k: v for k, v in res[name].items() if k not in ("diffs", "blank_nos", "unreadables")})
    (BL / "compare.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    {"make": make, "compare": compare}[sys.argv[1] if len(sys.argv) > 1 else "make"]()
