"""4단계: game.json — 화료자 자리·판 구간·영역·회전·리치·쯔모/론·끝 손패(자리 순서)·강·울기, 라벨과 비교.

  python -X utf8 game.py <판 id>
끝 손패는 공개 프레임(config reveal_frame 과 앞뒤 0.5초, 3장 다수결)을 화료자 시점으로 돌려 읽는다:
  reveal_region 안 앞면 패 → 세로 중심이 같은 줄(패 높이 0.5 안)로 묶어 가장 긴 줄 = 손패 줄 → 왼쪽부터 정렬,
  줄 안에서 틈(패 폭 0.6 넘게)으로 끊어 가장 긴 덩어리 = 닫힌 손패, 같은 줄의 나머지 = 떼어 둔 패(화료패 후보), 줄 밖 = other(표시패 등).
라벨 비교: label.json(태블릿 기록 판) 과 역할 세트 라벨(data/v1114rec·v1114 role labels, 공개 장면, 화료자 쪽 hand·loose·river·meld) —
  다르면 compare 에 다르다고 적는다(고치지 않음).
river_states.json(river.py) 이 있으면 리치 시각(가로 놓인 패가 처음 나온 구간)·울려 간 버림·판 구간 전 버림도 넣는다.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import river as rv  # noqa: E402
import vision as vz  # noqa: E402

TC = hc.EXP / "tile_classifier" / "data"
CAP = hc.EXP / "visit_20261114" / "captures"


def norm(t: str) -> str:
    return {"0m": "5m", "0p": "5p", "0s": "5s"}.get(t, t)


def hand_line(tiles: list[dict]) -> dict:
    if not tiles:
        return {"closed": [], "detached": [], "other": []}
    tw = float(np.median([min(t["w"], t["h"]) for t in tiles]))
    th = tw * 1.3
    lines: list[list[dict]] = []
    for t in sorted(tiles, key=lambda e: e["cy"]):
        if lines and abs(t["cy"] - np.median([u["cy"] for u in lines[-1]])) < 0.5 * th:
            lines[-1].append(t)
        else:
            lines.append([t])
    line = max(lines, key=len)
    other = [t for ln in lines if ln is not line for t in ln]
    line.sort(key=lambda e: e["cx"])
    runs = [[line[0]]]
    for a, b in zip(line, line[1:]):
        if b["cx"] - a["cx"] - tw > 0.6 * tw:
            runs.append([b])
        else:
            runs[-1].append(b)
    main = max(runs, key=len)
    det = [t for r in runs if r is not main for t in r]
    # 줄 끝에 가로로 붙여 놓은 패(세운 패들 사이 가로 1장)는 화료패로 떼어 본다(r18: 4m 을 줄 오른쪽 끝에 가로로 붙임)
    for end in (-1, 0):
        t = main[end] if main else None
        if t is not None and len(main) > 3 and t.get("sideways") and sum(u.get("sideways", False) for u in main) == 1:
            main.remove(t)
            t["attached_sideways"] = True
            det.append(t)
    for t in det:
        t["where"] = "right" if t["cx"] > main[-1]["cx"] else "left"
        t["gap_tiles"] = round(((t["cx"] - main[-1]["cx"]) if t["where"] == "right" else (main[0]["cx"] - t["cx"])) / tw - 1, 2)
    return {"closed": main, "detached": det, "other": other, "tile_w": tw}


def role_scenes(gid: str, side: str) -> list[dict]:
    out = []
    for set_, scale in (("v1114rec", 1.0), ("v1114", 0.5)):
        for sp in ("train", "dev"):
            p = TC / set_ / "role" / f"labels_{sp}.json"
            if not p.exists():
                continue
            for im in hc.jload(p)["images"]:
                if not im["id"].startswith(gid + "/") or im.get("phase") != "end" or im.get("winner") != side:
                    continue
                W, H = im["size"]
                items = []
                for it in im["items"]:
                    b = it["box"]
                    c = hc.to_view_xy(((b[0] + b[2] / 2) * scale, (b[1] + b[3] / 2) * scale), [0, 0, 1496, 1496], side)
                    items.append({"role": it["role"], "seat": it.get("seat"), "tile": it.get("tile"), "vx": c[0], "vy": c[1]})
                out.append({"set": set_, "split": sp, "id": im["id"], "items": items})
    return out


def role_summary(sc: dict, side: str) -> dict:
    its = sc["items"]
    hand = sorted([i for i in its if i["role"] == "hand" and i["seat"] == side], key=lambda e: e["vx"])
    loose = sorted([i for i in its if i["role"] == "loose" and i["seat"] == side], key=lambda e: e["vx"])
    meld = sorted([i for i in its if i["role"] == "meld" and i["seat"] == side], key=lambda e: e["vx"])
    river = vz.river_order([dict(i, cx=i["vx"], cy=i["vy"], w=40, h=52) for i in its if i["role"] == "river" and i["seat"] == side])
    return {"set": sc["set"], "id": sc["id"], "hand": [i["tile"] for i in hand], "loose": [i["tile"] for i in loose],
            "meld": [i["tile"] for i in meld], "river": [i["tile"] for i in river]}


def label_json(gid: str) -> dict | None:
    if not gid.startswith("r"):
        return None
    man = hc.jload(TC / "v1114" / "manifest.json")
    rd = next((r for r in man["rounds"] if r["id"] == gid), None)
    if rd is None or not rd.get("label_dirs"):
        return None
    d = rd["label_dirs"][-1]
    lab = hc.jload(CAP / d / "label.json")
    meta = hc.jload(CAP / d / "meta.json") if (CAP / d / "meta.json").exists() else {}
    return {"dir": d, "label": lab, "meta_winner_side": meta.get("winner_side"), "meta_game": meta.get("game"),
            "round": {k: rd.get(k) for k in ("round", "first_at", "last_at", "wins")}}


def rounds_note(gid: str) -> dict | None:
    p = TC / "v1114rec" / "new" / "rounds.json"
    for r in hc.jload(p)["rounds"]:
        if r["id"] == gid:
            return {k: r.get(k) for k in ("result", "t_start", "t_end_play", "t_reveal", "t_clear", "note", "back")}
    return None


def cmp_list(a: list, b: list) -> dict:
    a2, b2 = [norm(x) for x in a], [norm(x) for x in b]
    return {"same_order": a2 == b2, "same_set": Counter(a2) == Counter(b2), "only_read": list((Counter(a2) - Counter(b2)).elements()),
            "only_label": list((Counter(b2) - Counter(a2)).elements())}


def main():
    gid = sys.argv[1]
    cf = hc.config(gid)
    side = cf["side"]
    od = hc.out_dir(gid)
    # 공개 프레임 읽기(3장 다수결)
    ms0 = hc.nearest(hc.to_ms(cf["reveal_frame"]))
    f = hc.frames(hc.rec_of(ms0))
    i0 = int(np.searchsorted(f, ms0))
    fr = [int(f[i]) for i in (i0 - 5, i0, i0 + 5)]
    rr, hh, mm = [], [], []
    rv_v, rg_v, md_v = vz.view_box(cf["river"], side), vz.view_box(cf["reveal_region"], side), vz.view_box(cf["meld"], side)
    for ms in fr:
        v = vz.view_full(hc.load(ms), side)
        faces = vz.detect(v)
        rr.append(vz.read_region(v, rv_v, faces))
        hh.append(vz.read_region(v, rg_v, faces))
        mm.append(vz.read_region(v, md_v, faces))
    river = vz.river_order(rv.vote(rr))
    hl = hand_line(rv.vote(hh))
    meld = sorted(rv.vote(mm), key=lambda e: e["cx"])
    closed = [vz.brief(t) for t in hl["closed"]]
    det = [dict(vz.brief(t), where=t["where"], gap_tiles=t["gap_tiles"], attached_sideways=t.get("attached_sideways", False)) for t in hl["detached"]]
    final = {"frame": f"f_{ms0}.jpg", "frame_time": hc.hms(ms0), "frames_voted": [f"f_{m}.jpg" for m in fr], "rec": hc.rec_of(ms0),
             "closed": [t["tile"] for t in closed], "closed_detail": closed,
             "win_tile": det[0]["tile"] if len(det) == 1 else None, "detached": det,
             "other_in_region": [vz.brief(t) for t in hl["other"]],
             "melds": [t["tile"] for t in meld], "meld_detail": [vz.brief(t) for t in meld],
             "order_note": "closed = 대국자 왼쪽 → 오른쪽(화료자 시점 그림 왼쪽 → 오른쪽). 화료패(떼어 둔 패)·울기는 따로."}
    if len(det) != 1:
        final["win_tile_note"] = f"손패 줄 옆에 떼어 둔 패가 {len(det)}장 — 화료패를 자동으로 못 정함"
    river_final = [vz.brief(t) for t in river]
    # 강 상태 기록에서 리치·울려 간 버림
    rs_p = od / "river_states.json"
    riichi_seen, called_away, before_ready = None, [], None
    seg = hc.jload(od / "segments.json")
    if rs_p.exists():
        rs = hc.jload(rs_p)
        first = rs["still"].get("0") or rs["still"].get(0)
        before_ready = [t["tile"] for t in first["river"]] if first else None
        for a in seg["active"]:
            x = rs["segments"].get(str(a["seg"])) or {}
            for t in x.get("river_new", []):
                if t.get("sideways") and riichi_seen is None:
                    riichi_seen = {"seg": a["seg"], "t0": a["t0"], "t1": a["t1"], "tile": t["tile"]}
            for t in x.get("river_gone", []):
                called_away.append({"seg": a["seg"], "t0": a["t0"], "t1": a["t1"], "tile": t["tile"], "row": t["row"], "col": t["col"]})
    # 라벨
    lj = label_json(gid)
    rn = rounds_note(gid)
    roles = [role_summary(s, side) for s in role_scenes(gid, side)]
    compare = {}
    if lj:
        lab = lj["label"]
        lc = list(lab["closed"])
        # label closed 에 화료패가 들어 있음(울기 포함 14장). 11-16 시험 판: 론 판도 closed 에 화료패가 들어 있어 쯔모 조건을 장수 조건으로 바꿈
        # (r18 처럼 쯔모·울기 없는 판은 결과가 같다)
        if lab.get("win_tile") in lc and len(lc) + 3 * len(lab.get("melds") or []) == 14:
            lc2 = lc.copy()
            lc2.reverse()
            lc2.remove(lab["win_tile"])
            lc2.reverse()
        else:
            lc2 = lc
        compare["label_json"] = {"dir": lj["dir"], "closed_vs_label_without_win": cmp_list(final["closed"], lc2),
                                 "win_tile": [final["win_tile"], lab.get("win_tile")], "win_tile_same": final["win_tile"] == lab.get("win_tile"),
                                 "melds_read": final["melds"], "melds_label": lab.get("melds"), "riichi_label": lab.get("riichi"),
                                 "riichi_seen_in_river": riichi_seen, "is_tsumo_label": lab.get("is_tsumo"),
                                 "winner_seat_label": lab.get("winner"), "meta_winner_side": lj["meta_winner_side"],
                                 "note": "label closed 는 정렬된 목록일 수 있어 순서 비교(same_order)는 참고만"}
    for r in roles:
        compare.setdefault("role_labels", []).append({
            "id": f"{r['set']}:{r['id']}", "hand": cmp_list(final["closed"], r["hand"]), "hand_label": r["hand"],
            "loose_label": r["loose"], "win_tile_vs_loose": final["win_tile"] in [norm(x) for x in r["loose"]] if final["win_tile"] else None,
            "meld": cmp_list(final["melds"], r["meld"]), "river": cmp_list([t["tile"] for t in river_final], r["river"]), "river_label": r["river"]})
    W = cf["band"][2] - cf["band"][0], cf["band"][3] - cf["band"][1]
    game = {
        "id": gid, "winner_side": side,
        "winner_side_how": cf.get("winner_side_how", ""),
        "rotate_ccw_deg": hc.ROT[side], "rotate_note": "np.rot90(원본, rotate_ccw_deg/90) → 화료자가 그림 아래, 화료자 왼쪽이 그림 왼쪽",
        "interval": {"t_ready": cf["t_ready"], "t_end": seg["params"]["t_end"], "t_start_round": cf.get("t_start"), "t_reveal": cf["t_reveal"],
                     "ready_note": cf.get("ready_note", "")},
        "regions_orig": {k: cf[k] for k in ("band", "river", "meld", "reveal_region", "wide")},
        "band_view_size": [W[1], W[0]] if hc.ROT[side] in (90, 270) else [W[0], W[1]],
        "result": cf.get("result"), "result_how": cf.get("result_how", ""),
        "riichi": cf.get("riichi"), "riichi_seen_in_river": riichi_seen,
        "final_hand": final,
        "river_final": [t["tile"] for t in river_final], "river_final_detail": river_final,
        "river_before_ready": before_ready, "river_called_away": called_away,
        "label_sources": {"label_json": lj, "rounds_note": rn}, "compare": compare,
        "manual_notes": cf.get("notes", []),
    }
    hc.jsave(od / "game.json", game)
    print(f"{gid} 끝 손패 {' '.join(final['closed'])} | 화료패 {final['win_tile']} | 떼어 둔 패 {[d['tile'] for d in det]} | 울기 {final['melds']}")
    print(f"  강 {len(river_final)}장: {' '.join(t['tile'] + ('*' if t.get('sideways') else '') for t in river_final)}")
    print(f"  판 구간 전 강 {before_ready} · 울려 간 버림 {called_away} · 리치 {riichi_seen}")
    for k, v in compare.items():
        print(" ", k, v)


if __name__ == "__main__":
    main()
