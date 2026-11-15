"""녹화 프레임(rec1496) 역할 모델 세트(2026-11-15, 녹화 세트 3단계 4). v1114rec_dr_final.py·v1114rec_dr_final_pair.py 다음에. 다시 돌려도 같은 결과.

v1114_dr_role.py 와 같은 꼴, 좌표 = 녹화 1496(역할 입력은 상자 좌표뿐이라 이 좌표를 그대로 쓴다). 그림마다 part(pair|mid|new) 칸을 더한다.
대상 = 최종 그림 중 role_use.
  pair = 기존 role_use 를 물려받음(흔들림·탁자 아님·tidy(r07)·final_overrides role_exclude). ※ pair 에는 between·pre_game 규칙을 다시 적용하지 않았다
    (4단계: 표시만 — 그림 칸 pre_game(phase play·강 앞면 0)·between(짝은 늘 false)으로 쓰는 쪽에서 거를 수 있다).
  mid·new = det_use 이고 between 아니고 pre_game(phase play·강 앞면 0) 아님.
역할은 앞면에만, 주인 seat 은 hand·loose·meld·river 에만. 뒷면은 backs 로.
앞면 tile(패 종류) + tile_src(2026-11-15 E2 — 크롭 세트 검토 반영 뒤 채움):
  pair = 기존 분류기 세트 값(최종 라벨 tile, tile_src "v1114"; 기존 값이 없으면 null·tile_src null).
  mid·new = 분류기 크롭 세트(crops/index.json)의 확정 라벨 — (그림, 상자 id)로 크롭이 있는 상자만(tile_src "crops"), 나머지는 null·tile_src null
    (패 종류 not_tile·unsure·다시 볼 것·두 눈 확인 어긋남·더한 상자 등 — crops/final_uncovered.json 이 사유). v1114rec_crops.py 를 먼저 돌릴 것.
내보내기:
  ① role/labels_{train,dev}.json  통합: 그림마다 id·part·kind·format·phase·pre_game·between·scene_round·winner·winner_src·flags·grid_est·device·size·image·items[]·backs[]
  ② role/frames_play_{train,dev}.json  kind frame·phase play 만, 기존 data/role/frames/labels_*.json 꼴(v1114_dr_role ② 와 같음), part 칸 더함.
  ③ role/win_{train,dev}.json  화료 장면만: format win(pair 의 화료 사진) + format end(new 의 공개 장면 — 초안이 화료 사진처럼 다룬 것), winner 있는 것.
     기존 labels_v2_owner 꼴(v1114_dr_role ③ 과 같음): owner = pair·화료자 자리 hand·loose·meld 는 winner, 남의 hand·loose·meld 는 other.
     x = roles.tokens(앞면 + 뒷면, grid_est, 화료자 side, 11칸), y = 역할 번호(other·뒷면 −1).
     ※ v1114_dr_role 은 kind win 만 넣었다(그 세트의 end 프레임은 format frame). 여기서는 format 이 win|end 인 것으로 — 같은 기준(format ≠ frame).
       mid 의 phase end 그림(format frame)은 기존 end 프레임처럼 labels 에만 있다.
  python -X utf8 experiments/tile_classifier/v1114rec_dr_role.py
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from v1114rec_dr_common import DR, OWNED, PARTS, R, final_all, jload, jsave  # noqa: E402

sys.path.insert(0, r"C:\Users\jjh7757\dev\mahjong-recognizer")
from app import roles  # noqa: E402

OUT = R / "role"


def crop_tiles() -> dict:
    """crops/index.json → (그림 id, 상자 id 문자열) → 라벨(mid·new 만)."""
    out = {}
    for x in jload(R / "crops" / "index.json"):
        if x["part"] in ("mid", "new"):
            k = (x["image"], str(x["box_id"]))
            assert k not in out, k
            out[k] = x["tile"]
    return out


def tile_of(im: dict, b: dict, ct: dict) -> tuple:
    if im["part"] == "pair":
        t = b.get("tile")
        return t, ("v1114" if t else None)
    t = ct.get((im["id"], str(b["id"])))
    return t, ("crops" if t else None)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    uni = {"train": [], "dev": []}
    frames = {"train": [], "dev": []}
    wins = {"train": {}, "dev": {}}
    cnt = Counter()
    skipped = []
    ct = crop_tiles()
    used = set()
    for im in final_all():
        sp, part = im["split_final"], im["part"]
        if not im["role_use"]:
            why = list(im["excluded_why"])
            skipped.append({"id": im["id"], "part": part, "why": why, "phase": im["phase"]})
            for w in why:
                cnt["skip_" + part + "_" + w.split("(")[0].split(":")[0].strip()] += 1
            continue
        faces = [b for b in im["boxes"] if b["cls"] == "face"]
        backs = [b for b in im["boxes"] if b["cls"] == "back"]
        for b in faces:
            if (b["role"] in OWNED) != (b["seat"] is not None):
                cnt["seat_rule_violation"] += 1
        tiles = [tile_of(im, b, ct) for b in faces]
        for b, (t, ts) in zip(faces, tiles):
            cnt[f"tile_{part}_{sp}_{'filled' if t else 'null'}"] += 1
            if ts == "crops":
                used.add((im["id"], str(b["id"])))
        items = [{"id": b["id"], "box": b["box"], "pts": b["pts"], "rect": b["rect"], "role": b["role"], "seat": b["seat"], "role_src": b["role_src"],
                  "src": b["src"], "tile": t, "tile_src": ts} for b, (t, ts) in zip(faces, tiles)]
        bk = [{"id": b["id"], "box": b["box"], "pts": b["pts"], "rect": b["rect"]} for b in backs]
        pre_game, between = bool(im.get("pre_game")), bool(im.get("between"))
        if pre_game:
            cnt[f"{part}_{sp}_pre_game_kept"] += 1
        uni[sp].append({"id": im["id"], "part": part, "kind": im["kind"], "format": im["format"], "phase": im["phase"],
                        "pre_game": pre_game, "between": between, "scene_round": im["scene_round"],
                        "winner": im["winner"], "winner_src": im["winner_src"], "flags": im["flags"], "grid_est": im["grid_est"], "device": im["device"],
                        "size": im["size"], "image": im["path"], "items": items, "backs": bk})
        cnt[f"{sp}_images"] += 1
        cnt[f"{part}_{sp}_images"] += 1
        cnt[f"{sp}_{im['phase']}"] += 1
        cnt[f"{part}_{sp}_{im['phase']}"] += 1
        cnt[f"{sp}_face"] += len(faces)
        cnt[f"{sp}_back"] += len(backs)
        for b in faces:
            cnt[f"role_{b['role']}"] += 1
            cnt[f"role_{part}_{b['role']}"] += 1
            cnt[f"seat_{b['seat'] or '-'}"] += 1
        dv = im["device"]
        if im["kind"] == "frame" and im["phase"] == "play":
            frames[sp].append({"image": im["path"], "size": im["size"], "grid": im["grid_est"], "bottom_seat": None, "phase": "play",
                               "round_key": im["scene_round"], "at": im["at"], "device": [dv["cx"], dv["cy"], dv["hd"], dv["src"]], "name": im["id"], "part": part,
                               "pre_game": pre_game, "between": between,
                               "items": [{"id": k, "box": b["box"], "pts": b["pts"], "role": b["role"], "seat": b["seat"], "src": "det" if b["src"] != "add" else "added",
                                          "draft_id": b["id"], "score": True, "tile": t, "tile_src": ts} for k, (b, (t, ts)) in enumerate(zip(faces, tiles))],
                               "backs": [b["box"] for b in backs]})
        if im["format"] in ("win", "end") and im["winner"]:
            side = im["winner"]
            W, H = im["size"]
            g = im["grid_est"]
            x = roles.tokens([tuple(b["box"]) for b in faces], W, H, g, side, 11, [np.array(b["pts"]) for b in faces],
                             [(tuple(b["box"]), np.array(b["pts"])) for b in backs])
            its = []
            for b, (t, ts) in zip(faces, tiles):
                own = None
                if b["role"] == "pair" or (b["role"] in ("hand", "loose", "meld") and b["seat"] == side):
                    own = "winner"
                elif b["role"] in ("hand", "loose", "meld"):
                    own = "other"
                    cnt["win_nonwinner_" + b["role"]] += 1
                its.append({"box": b["box"], "pts": b["pts"], "role": b["role"], "owner": own, "seat": b["seat"], "seat_src": b["role_src"], "id": b["id"], "tile": t, "tile_src": ts})
            y = [roles.ROLES.index(b["role"]) if b["role"] in roles.ROLES else -1 for b in faces] + [-1] * len(backs)
            wins[sp][im["id"]] = {"side": side, "winner_src": im["winner_src"], "size": im["size"], "image": str((R / im["path"]).resolve()), "part": part,
                                  "kind": "photo" if im["format"] == "win" else "reveal_frame", "source": "v1114rec_dr", "items": its,
                                  "backs": [b["box"] for b in backs], "dropped_backs": 0,
                                  "x": [[round(float(v), 5) for v in r] for r in x], "y": y, "n_face": len(faces), "roles": [b["role"] for b in faces],
                                  "seat_center": [dv["cx"], dv["cy"], dv["src"]], "grid": g}
            cnt[f"{part}_{sp}_win_file"] += 1
    note = ("역할 라벨(v1114rec_dr_role.py). 좌표 = 녹화 1496 원래 픽셀. part = pair|mid|new. 앞면 tile·tile_src: pair = 기존 값(v1114), "
            "mid·new = 분류기 크롭 세트 확정 라벨(crops — 크롭이 있는 상자만), 그 밖 null.")
    for sp in ("train", "dev"):
        jsave(OUT / f"labels_{sp}.json", {"_note": note, "images": uni[sp]}, indent=0)
        jsave(OUT / f"frames_play_{sp}.json", {"_note": note + " 기존 data/role/frames/labels_*.json 꼴(kind frame·phase play 만, grid = grid_est).",
                                                "frames": frames[sp]}, indent=0)
        jsave(OUT / f"win_{sp}.json", wins[sp], indent=0)
        cnt[f"{sp}_frames_play_file"] = len(frames[sp])
        cnt[f"{sp}_win_file"] = len(wins[sp])
    why_c = Counter()
    for s in skipped:
        for w in s["why"]:
            why_c[(s["part"], w.split("(")[0].split(":")[0].strip())] += 1
    jsave(OUT / "summary.json", {
        "counts": dict(cnt), "skipped": skipped,
        "skipped_by_reason": {f"{p}|{w}": n for (p, w), n in sorted(why_c.items())},
        "coords": "녹화 1496 원래 픽셀(기존 v1114 role 은 2992 — 섞어 쓰려면 기존 좌표 × 0.5)",
        "pre_game_note": (f"mid·new 는 pre_game·between 그림을 역할 세트에서 뺐고, pair 는 기존 세트대로 role_use 를 물려받아 강 앞면 0장(pre_game) 그림이 "
                          f"학습 {cnt['pair_train_pre_game_kept']}장·개발 {cnt['pair_dev_pre_game_kept']}장 남아 있다. labels_*·frames_play_* 의 그림 칸 "
                          f"pre_game(·between·part)으로 거를 수 있다(pair 의 between 은 표시하지 않아 늘 false)."),
        "tile_fill": {f"{pt}_{sp}": {"faces": cnt[f"tile_{pt}_{sp}_filled"] + cnt[f"tile_{pt}_{sp}_null"], "filled": cnt[f"tile_{pt}_{sp}_filled"],
                                     "rate": round(cnt[f"tile_{pt}_{sp}_filled"] / max(1, cnt[f"tile_{pt}_{sp}_filled"] + cnt[f"tile_{pt}_{sp}_null"]), 4)}
                      for pt in PARTS for sp in ("train", "dev")},
        "crop_tiles_mid_new": len(ct), "crop_tiles_used": len(used),
        "crop_tiles_not_in_role_set": "크롭은 있는데 역할 세트 그림이 아닌 것(role_use 아님 — pre_game·between·흔들림) = crop_tiles_mid_new − crop_tiles_used",
        "rules": {"pair": "기존 role_use 물려받음(between·pre_game 다시 안 봄 — pre_game 칸은 표시만)", "mid_new": "det_use 이고 between 아니고 pre_game(phase play, 강 앞면 0) 아님",
                  "win_file": "format win(pair 화료 사진) + format end(new 공개 장면), winner 있는 것", "tile": "pair 기존 값(tile_src v1114), mid·new 크롭 세트 확정 라벨(tile_src crops, 크롭 있는 상자만), 나머지 null"},
        "det_input": "녹화 프레임에서 운영 검출기를 돌린 상자에 역할을 옮긴 입력과 검출 수는 role/det_input/(v1114rec_dr_detinput.py)",
        "process": jload(R / "det" / "summary.json")["process"] if (R / "det" / "summary.json").exists() else None}, indent=1)
    print({k: v for k, v in cnt.items()})
    print("뺌 사유", dict(why_c))


if __name__ == "__main__":
    main()
