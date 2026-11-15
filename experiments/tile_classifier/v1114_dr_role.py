"""11-14 역할 모델 세트(2026-11-15, 검출·역할 세트 3단계 3). v1114_dr_final.py 다음에.

대상 = final 그림 중 role_use(흔들림·탁자 아님 2장, phase=tidy(r07 8장) 뺌). 나눔 = split_final.
역할은 앞면에만(hand meld river wall pair loose other), 주인 seat 은 hand·loose·meld·river 에만. 뒷면은 역할 없이 backs 로 같이 싣는다.
역할 모델 입력은 상자 좌표뿐이라(roles.tokens) 이 라벨은 화질과 무관하다 — 다른 화질에 쓰려면 좌표에 manifest rules.scale(q1496 0.5, q997 1/3)을 곱한다.
화질 차이를 담은 입력은 v1114_dr_detinput.py(role/det_input/).
내보내기:
  ① role/labels_{train,dev}.json  통합: 그림마다 id·kind·phase·scene_round·winner·winner_src·grid_est·device·size·items[{id,box,pts,rect,role,seat,role_src,src,tile}]·backs[{id,box,pts,rect}]
  ② role/frames_play_{train,dev}.json  phase=play 프레임만, 기존 data/role/frames/labels_*.json 꼴({_note, frames:[{image,size,grid,bottom_seat,phase,round_key,at,device,
     name,items[{id,box,role,seat,src,score}],backs[[x,y,w,h]]}]}) — box 는 축 상자, pts 를 더 붙임. grid = grid_est, phase 칸은 기존 early/mid/end 대신 "play".
  ③ role/win_{train,dev}.json  화료 사진만, 기존 data/role/v2/labels_v2_owner.json 꼴({이름: {side,size,image,kind,source,items[{box,role,owner,seat,seat_src}],
     backs,dropped_backs,x,y,n_face,roles,seat_center}}) — owner = pair 와 화료자 자리 hand·loose·meld 는 winner, 남의 hand·loose·meld 는 other, 그 밖 null.
     x = roles.tokens(앞면 + 뒷면, grid_est, 화료자 side, 11칸), y = 역할 번호(roles.ROLES 순서, other·뒷면 = -1).
  python -X utf8 experiments/tile_classifier/v1114_dr_role.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
V = HERE / "data" / "v1114"
DR = V / "dr"
OUT = V / "role"
sys.path.insert(0, r"C:\Users\jjh7757\dev\mahjong-recognizer")
from app import roles  # noqa: E402

OWNED = ("hand", "loose", "meld", "river")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    uni = {"train": [], "dev": []}
    frames = {"train": [], "dev": []}
    wins = {"train": {}, "dev": {}}
    cnt = Counter()
    skipped = []
    for p in sorted((DR / "final").glob("r*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        for im in d["images"]:
            sp = im["split_final"]
            if not im["role_use"]:
                skipped.append({"id": im["id"], "why": im["excluded_why"], "phase": im["phase"]})
                continue
            faces = [b for b in im["boxes"] if b["cls"] == "face"]
            backs = [b for b in im["boxes"] if b["cls"] == "back"]
            for b in faces:  # 정의 검사(어긋나면 세기만 — check 에서 목록)
                if (b["role"] in OWNED) != (b["seat"] is not None):
                    cnt["seat_rule_violation"] += 1
            items = [{"id": b["id"], "box": b["box"], "pts": b["pts"], "rect": b["rect"], "role": b["role"], "seat": b["seat"], "role_src": b["role_src"],
                      "src": b["src"], "tile": b.get("tile")} for b in faces]
            bk = [{"id": b["id"], "box": b["box"], "pts": b["pts"], "rect": b["rect"]} for b in backs]
            uni[sp].append({"id": im["id"], "kind": im["kind"], "phase": im["phase"], "scene_round": im["scene_round"], "scene": im["scene"],
                            "winner": im["winner"], "winner_src": im["winner_src"], "flags": im["flags"], "grid_est": im["grid_est"], "device": im["device"],
                            "size": im["size"], "image": im["paths"]["q2992"], "paths": im["paths"], "items": items, "backs": bk})
            cnt[f"{sp}_images"] += 1
            cnt[f"{sp}_{im['phase']}"] += 1
            cnt[f"{sp}_face"] += len(faces)
            cnt[f"{sp}_back"] += len(backs)
            for b in faces:
                cnt[f"role_{b['role']}"] += 1
                cnt[f"seat_{b['seat'] or '-'}"] += 1
            dv = im["device"]
            if im["kind"] == "frame" and im["phase"] == "play":
                frames[sp].append({"image": im["paths"]["q2992"], "size": im["size"], "grid": im["grid_est"], "bottom_seat": None, "phase": "play",
                                   "round_key": im["scene_round"], "at": im["at"], "device": [dv["cx"], dv["cy"], dv["hd"], dv["src"]], "name": im["id"],
                                   "items": [{"id": k, "box": b["box"], "pts": b["pts"], "role": b["role"], "seat": b["seat"], "src": "det" if b["src"] != "add" else "added",
                                              "draft_id": b["id"], "score": True} for k, b in enumerate(faces)],
                                   "backs": [b["box"] for b in backs]})
            if im["kind"] == "win" and im["winner"]:
                side = im["winner"]
                W, H = im["size"]
                g = im["grid_est"]
                x = roles.tokens([tuple(b["box"]) for b in faces], W, H, g, side, 11, [np.array(b["pts"]) for b in faces],
                                 [(tuple(b["box"]), np.array(b["pts"])) for b in backs])
                its = []
                for b in faces:
                    own = None
                    if b["role"] == "pair" or (b["role"] in ("hand", "loose", "meld") and b["seat"] == side):
                        own = "winner"
                    elif b["role"] in ("hand", "loose", "meld"):
                        own = "other"  # 남의 울기, 그리고 r05 처럼 앞 판에서 남은 남의 펼친 손패
                        cnt["win_nonwinner_" + b["role"]] += 1
                    its.append({"box": b["box"], "pts": b["pts"], "role": b["role"], "owner": own, "seat": b["seat"], "seat_src": b["role_src"], "id": b["id"]})
                y = [roles.ROLES.index(b["role"]) if b["role"] in roles.ROLES else -1 for b in faces] + [-1] * len(backs)
                wins[sp][im["id"]] = {"side": side, "winner_src": im["winner_src"], "size": im["size"], "image": str((V / im["paths"]["q2992"]).resolve()),
                                      "kind": "photo", "source": "v1114_dr", "items": its, "backs": [b["box"] for b in backs], "dropped_backs": 0,
                                      "x": [[round(float(v), 5) for v in r] for r in x], "y": y, "n_face": len(faces), "roles": [b["role"] for b in faces],
                                      "seat_center": [dv["cx"], dv["cy"], dv["src"]], "grid": g}
    note = "역할 라벨(v1114_dr_role.py). 좌표 2992 원본 픽셀 — 다른 화질은 manifest rules.scale 을 곱함(q1496 0.5, q997 1/3). 화질과 무관한 라벨."
    for sp in ("train", "dev"):
        (OUT / f"labels_{sp}.json").write_text(json.dumps({"_note": note, "images": uni[sp]}, ensure_ascii=False, indent=0), encoding="utf-8")
        (OUT / f"frames_play_{sp}.json").write_text(json.dumps({"_note": note + " 기존 data/role/frames/labels_*.json 꼴(phase=play 프레임만, grid = 그림에서 찾은 grid_est).",
                                                               "frames": frames[sp]}, ensure_ascii=False, indent=0), encoding="utf-8")
        (OUT / f"win_{sp}.json").write_text(json.dumps(wins[sp], ensure_ascii=False, indent=0), encoding="utf-8")
        cnt[f"{sp}_frames_play_file"] = len(frames[sp])
        cnt[f"{sp}_win_file"] = len(wins[sp])
    sys.path.insert(0, str(HERE))
    import v1114_dr_final as fin
    (OUT / "summary.json").write_text(json.dumps({"counts": dict(cnt), "skipped": skipped, "scale": json.loads((V / "manifest.json").read_text(encoding="utf-8"))["rules"]["scale"],
                                                  "process": fin.PROCESS, "review_edits": fin.review_edits(),
                                                  "det_input": "화질별 검출 상자에 역할을 옮긴 입력과 검출 수는 role/det_input/(v1114_dr_detinput.py, counts.json 에 조건)"},
                                                 ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(dict(cnt), ensure_ascii=False))
    print("뺌", [(s["id"], s["why"]) for s in skipped])


if __name__ == "__main__":
    main()
