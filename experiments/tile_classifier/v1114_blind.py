"""11-14 크롭 세트 독립 검토용 가린 그림(2026-11-15, 3단계 C). v1114_crops.py 다음에.

  python -X utf8 experiments/tile_classifier/v1114_blind.py make      → data/v1114/blind/{D,T,R}_NN.jpg, answers_{D,T,R}.json(빈 양식), _key.json(정답 열쇠 — 검토자는 열지 않음)
  python -X utf8 experiments/tile_classifier/v1114_blind.py compare   → 채운 answers 와 열쇠를 맞대어 blind/compare.json(다른 칸·빈 칸 목록)

묶음(사용자가 정함):
  D = 개발 실물 패(unit) 전부, 한 unit 에 q2992 크롭 한 장 — 2단계 대조표에 실렸던 가장 선명한 그림(track best)이 아닌 그림의 상자(씨앗 고정 무작위), 그런 그림이 없으면 있는 것.
  T = 학습 unit 에서 종류별로 고르게 300개(종류마다 섞어 돌아가며 하나씩, r08_125630 은 최대 60개), 같은 방식으로 한 장씩.
  R = crops/review_todo.json("다시 볼 것") 상자 전부.
그림: 한 장 20칸(4×5). 칸 = 왼쪽 크롭(초안이 읽은 방향으로 세움) + 오른쪽 둘레 그림(원래 방향, 노란 테두리 = 그 상자). 글은 칸 번호만.
칸 순서는 종류와 무관하게 섞음(씨앗 고정). 번호는 묶음 안에서 1부터.
"""
from __future__ import annotations

import json
import random
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
OUT = HERE / "data" / "v1114"
BL = OUT / "blind"
SEED = 20261115
T_N, T_R08_MAX = 300, 60
COLS, ROWS = 4, 5
CW, CH = 420, 260
TILE_H = 220
FONTB = "C:/Windows/Fonts/arialbd.ttf"
ANS_HELP = ("칸 번호마다 tile 에 종류를 적는다: 1m~9m·1p~9p·1s~9s, 적5 = 0m·0p·0s, 1z 동 2z 남 3z 서 4z 북 5z 백 6z 발 7z 중. "
            "앞면 패가 아니면(뒷면·패 일부만·손·다른 물건) 'not_tile', 흐림·가림으로 모르겠으면 'unsure'(note 필수). "
            "왼쪽 크롭은 분류기가 읽은 방향이라 뒤집혀 보일 수 있다 — 오른쪽 둘레 그림(노란 테두리)이 원래 방향. 적5(빨간 5)와 그냥 5 를 꼭 가른다.")


def context(rgb: np.ndarray, box, side: int = 200) -> Image.Image:
    x, y, w, h = box
    H, W = rgb.shape[:2]
    R = int(max(w, h) * 1.5)
    cx, cy = x + w // 2, y + h // 2
    x0, y0 = max(0, cx - R), max(0, cy - R)
    part = Image.fromarray(rgb[y0:min(H, cy + R), x0:min(W, cx + R)]).copy()
    ImageDraw.Draw(part).rectangle((x - x0, y - y0, x - x0 + w, y - y0 + h), outline=(255, 230, 0), width=3)
    part.thumbnail((side, side))
    return part


def pick_crop(xs: list[dict], best: dict, rng: random.Random) -> dict:
    other = [x for x in xs if x["image"] != best["image"]]
    return rng.choice(sorted(other or xs, key=lambda x: x["id"]))


def make():
    from v1114_crops import cut
    from v1114_split import image_rel

    man = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    items = {it["id"]: it for it in man["items"]}
    rows = json.loads((OUT / "crops" / "index.json").read_text(encoding="utf-8"))
    todo = json.loads((OUT / "crops" / "review_todo.json").read_text(encoding="utf-8"))
    best = {}
    drafts = {}
    for r in man["rounds"]:
        d = json.loads((OUT / "draft" / f"{r['id']}.json").read_text(encoding="utf-8"))
        drafts[r["id"]] = d
        for t in d["tracks"]:
            best[(r["id"], t["tid"])] = t["best"]
    units = defaultdict(list)
    for x in rows:
        units[x["unit"]].append(x)
    rng = random.Random(SEED)
    # D
    dev_units = sorted(u for u, xs in units.items() if xs[0]["split"] == "dev")
    D = [pick_crop(units[u], best[(units[u][0]["round"], units[u][0]["tid"])], rng) for u in dev_units]
    # T: 종류별로 섞은 뒤 돌아가며
    by_tile = defaultdict(list)
    for u in sorted(u for u, xs in units.items() if xs[0]["split"] == "train"):
        by_tile[units[u][0]["tile"]].append(u)
    for k in sorted(by_tile):
        rng.shuffle(by_tile[k])
    T_units, n08 = [], 0
    while len(T_units) < T_N and any(by_tile.values()):
        for k in sorted(by_tile):
            while by_tile[k]:
                u = by_tile[k].pop()
                if u.startswith("r08_125630#"):
                    if n08 >= T_R08_MAX:
                        continue
                    n08 += 1
                T_units.append(u)
                break
            if len(T_units) >= T_N:
                break
    T = [pick_crop(units[u], best[(units[u][0]["round"], units[u][0]["tid"])], rng) for u in T_units]
    R = list(todo)
    if BL.exists():
        for f in BL.glob("*"):
            if f.name.startswith(("D_", "T_", "R_", "_key", "answers_")):
                f.unlink()
    BL.mkdir(parents=True, exist_ok=True)
    key, counts = {}, {}
    f_no = ImageFont.truetype(FONTB, 30)
    cache = {}

    def rgb_of(iid):
        if iid not in cache:
            if len(cache) > 6:
                cache.pop(next(iter(cache)))
            cache[iid] = np.asarray(Image.open(OUT / image_rel(items[iid], "q2992")).convert("RGB"))
        return cache[iid]

    for name, cells in (("D", D), ("T", T), ("R", R)):
        cells = list(cells)
        rng.shuffle(cells)
        key[name] = {}
        per = COLS * ROWS
        for s in range(0, len(cells), per):
            sheet = Image.new("RGB", (COLS * CW, ROWS * CH), (255, 255, 255))
            dr = ImageDraw.Draw(sheet)
            for k, c in enumerate(cells[s:s + per]):
                no = s + k + 1
                img = drafts[c["round"]]["images"]
                b = next(im for im in img if im["id"] == c["image"])["boxes"][c["i"]]
                rgb = rgb_of(c["image"])
                if name == "R":
                    tim = cut(rgb, b, 1.0)
                else:
                    tim = Image.open(OUT / c["paths"]["q2992"]).convert("RGB")
                ctx = context(rgb, b["box"])
                x0, y0 = (k % COLS) * CW, (k // COLS) * CH
                dr.rectangle((x0 + 2, y0 + 2, x0 + CW - 3, y0 + CH - 3), outline=(150, 150, 150), width=2)
                sc = min(TILE_H / tim.height, 170 / tim.width)
                tim = tim.resize((max(1, round(tim.width * sc)), max(1, round(tim.height * sc))), Image.LANCZOS)
                sheet.paste(tim, (x0 + 10 + (170 - tim.width) // 2, y0 + 30 + (TILE_H - 10 - tim.height) // 2))
                sheet.paste(ctx, (x0 + 200, y0 + 30 + (TILE_H - 10 - ctx.height) // 2))
                dr.text((x0 + 10, y0 + 2), str(no), fill=(0, 0, 0), font=f_no)
                if name == "R":
                    key[name][str(no)] = {"round": c["round"], "tid": c["tid"], "image": c["image"], "i": c["i"], "why": c["why"], "read": c["read"],
                                          "track_draft": c["track_draft"], "verdict": c["verdict"], "label_if_kept": c.get("label_if_kept"),
                                          "per_image": c.get("per_image"), "fix_tile": c.get("fix_tile"), "split": c["split"], "note": c["note"],
                                          "sheet": f"R_{s // per + 1:02d}.jpg"}
                else:
                    key[name][str(no)] = {"crop_id": c["id"], "unit": c["unit"], "label": c["tile"], "round": c["round"], "tid": c["tid"],
                                          "image": c["image"], "i": c["i"], "src": c["src"], "read": c["read"], "conf": c["conf"], "note": c["note"],
                                          "split": c["split"], "sheet": f"{name}_{s // per + 1:02d}.jpg"}
            sheet.save(BL / f"{name}_{s // per + 1:02d}.jpg", quality=90)
        counts[name] = {"cells": len(cells), "sheets": (len(cells) + per - 1) // per}
        ans = {"bundle": name, "how": ANS_HELP, "reviewer": None, "done": False,
               "sheets": [f"{name}_{i + 1:02d}.jpg" for i in range(counts[name]["sheets"])],
               "answers": {str(i + 1): {"tile": None, "note": ""} for i in range(len(cells))}}
        (BL / f"answers_{name}.json").write_text(json.dumps(ans, ensure_ascii=False, indent=1), encoding="utf-8")
    key["_meta"] = {"seed": SEED, "counts": counts, "T_tiles": dict(Counter(units[u][0]["tile"] for u in T_units)),
                    "T_r08": n08, "T_rounds": dict(Counter(u.split("#")[0] for u in T_units)),
                    "D_best_image_used": sum(1 for c in D if c["image"] == best[(c["round"], c["tid"])]["image"])}
    (BL / "_key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(key["_meta"], ensure_ascii=False, indent=1))


def compare():
    key = json.loads((BL / "_key.json").read_text(encoding="utf-8"))
    res = {}
    for name in ("D", "T", "R"):
        p = BL / f"answers_{name}.json"
        if not p.exists():
            continue
        ans = json.loads(p.read_text(encoding="utf-8"))["answers"]
        diff, blank, same = [], [], 0
        for no, k in key[name].items():
            a = ans.get(no) or {}
            got = a.get("tile")
            want = k.get("label") if name != "R" else (k.get("label_if_kept") or k.get("per_image") or k.get("fix_tile") or k.get("track_draft"))
            if got in (None, ""):
                blank.append(no)
            elif got == want:
                same += 1
            else:
                diff.append({"no": no, "answer": got, "answer_note": a.get("note", ""), "key": want, **k})
        res[name] = {"cells": len(key[name]), "same": same, "diff": len(diff), "blank": len(blank), "blank_nos": blank,
                     "diff_by_answer": dict(Counter(d["answer"] for d in diff)), "diffs": diff}
        if name == "R":
            res[name]["note"] = "R 의 key 는 정답이 아니라 규칙이 막지 않았다면 붙었을 라벨(또는 per_image·fix·초안) — 다른 칸이 곧 틀림은 아님"
        print(name, {k: v for k, v in res[name].items() if k not in ("diffs", "blank_nos")})
    (BL / "compare.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    {"make": make, "compare": compare}[sys.argv[1] if len(sys.argv) > 1 else "make"]()
