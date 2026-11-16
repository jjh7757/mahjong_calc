"""3단계: 정지 상태마다 화료자 강·울기 자리를 읽고, 활동 구간마다 "강에 새로 놓인 패"·"강에서 빠진 패"·울기 변화를 낸다.

  python -X utf8 river.py <판 id>
정지 구간마다 프레임 3장(처음·가운데·끝, 강 피부 비율이 낮은 것 우선)을 화료자 시점으로 돌려 검출·분류하고, 자리(중심 12px 안)별로
  종류를 다수결(같으면 확신 합)한다. 강 = config river 영역, 울기 = config meld 영역(원본 좌표).
활동 구간의 강 변화 = 앞 정지 상태와 뒤 정지 상태 비교: 뒤에만 있는 자리(패 폭 0.5 안에 앞 패가 없음) = 새로 놓임, 앞에만 있는 자리 = 빠짐(울려 감 또는 옮김),
  같은 자리인데 종류가 다르면 changed(대개 분류 흔들림). 가로 놓인 패(sideways)는 리치 선언 패로 본다.
결과 results/handtrack/<판>/river_states.json: {"still": {k: {ms, frames, river: [...], meld: [...]}}, "segments": {seg: {...}}}
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import vision as vz  # noqa: E402

SAME = 12  # 같은 자리로 볼 중심 거리(px, 1496 그림)


def vote(reads: list[list[dict]]) -> list[dict]:
    """여러 프레임의 같은 영역 읽기 → 자리별 다수결. 절반 넘는 프레임에 나온 자리만 남긴다."""
    groups: list[list[dict]] = []
    for r in reads:
        for t in r:
            for g in groups:
                if abs(g[0]["cx"] - t["cx"]) < SAME and abs(g[0]["cy"] - t["cy"]) < SAME:
                    g.append(t)
                    break
            else:
                groups.append([t])
    out = []
    for g in groups:
        if len(g) * 2 <= len(reads):
            continue
        c = Counter(t["tile"] for t in g)
        score = defaultdict(float)
        for t in g:
            score[t["tile"]] += t["conf"]
        best = max(c, key=lambda k: (c[k], score[k]))
        rep = max((t for t in g if t["tile"] == best), key=lambda t: t["conf"])
        e = dict(rep)
        e["cx"] = float(np.mean([t["cx"] for t in g]))
        e["cy"] = float(np.mean([t["cy"] for t in g]))
        e["votes"] = f"{c[best]}/{len(g)}"
        if len(c) > 1:
            e["others"] = dict(c)
        e["sideways"] = sum(t["sideways"] for t in g) * 2 > len(g)
        out.append(e)
    return out


def pick_frames(z, i0: int, i1: int, n: int = 3) -> list[int]:
    idx = np.arange(i0, i1 + 1)
    if len(idx) <= n:
        return list(idx)
    rs = z["river_skin"][idx] + z["band_skin"][idx]
    cand = [idx[0], idx[len(idx) // 2], idx[-1]]
    out = []
    for c in cand:  # 각 후보 근처 ±5장 안에서 피부가 가장 적은 프레임
        lo, hi = max(i0, c - 5), min(i1, c + 5)
        j = lo + int(np.argmin(rs[lo - i0:hi - i0 + 1]))
        if j not in out:
            out.append(j)
    return out


def read_state(ms_list: list[int], side: str, river_v: list, meld_v: list) -> dict:
    rr, mm = [], []
    for ms in ms_list:
        v = vz.view_full(hc.load(ms), side)
        faces = vz.detect(v)
        rr.append(vz.read_region(v, river_v, faces))
        mm.append(vz.read_region(v, meld_v, faces))
    river = vz.river_order(vote(rr))
    meld = sorted(vote(mm), key=lambda e: e["cx"])
    return {"frames": [hc.hms(m) for m in ms_list], "frames_ms": ms_list, "river": [vz.brief(t) for t in river], "meld": [vz.brief(t) for t in meld]}


def diff(a: list[dict], b: list[dict]) -> dict:
    """앞 상태 a 와 뒤 상태 b(강 패 목록) 비교."""
    if not a and not b:
        return {"new": [], "gone": [], "changed": []}
    tw = float(np.median([min(t["w"], t["h"]) for t in a + b]))
    used = set()
    new, changed = [], []
    for t in b:
        m = None
        for j, s in enumerate(a):
            if j not in used and abs(s["cx"] - t["cx"]) < 0.5 * tw and abs(s["cy"] - t["cy"]) < 0.5 * tw:
                m = j
                break
        if m is None:
            new.append(t)
        else:
            used.add(m)
            if a[m]["tile"] != t["tile"]:
                changed.append({"before": a[m]["tile"], "after": t["tile"], "row": t.get("row"), "col": t.get("col")})
    gone = [s for j, s in enumerate(a) if j not in used]
    return {"new": new, "gone": gone, "changed": changed}


def main():
    gid = sys.argv[1]
    cf = hc.config(gid)
    side = cf["side"]
    seg = hc.jload(hc.out_dir(gid) / "segments.json")
    z = np.load(hc.WORK / f"{gid}_feat.npz")
    off = seg["feat_index0"]
    ms_all = z["ms"]
    river_v, meld_v = vz.view_box(cf["river"], side), vz.view_box(cf["meld"], side)
    still = {}
    for s in seg["still"]:
        fr = pick_frames(z, s["i0"] + off, s["i1"] + off)
        still[s["k"]] = read_state([int(ms_all[i]) for i in fr], side, river_v, meld_v)
        st = still[s["k"]]
        print(f"정지 {s['k']:3d} {s['t0']}–{s['t1']} 강 {len(st['river']):2d} 울기 {len(st['meld'])} "
              + " ".join(t["tile"] + ("*" if t.get("sideways") else "") for t in st["river"]), flush=True)
    segs = {}
    for a in seg["active"]:
        pv, nx = a["prev_still"], a["next_still"]
        if pv is None or nx is None:
            segs[a["seg"]] = {"prev_still": pv, "next_still": nx, "note": "앞 또는 뒤 정지 상태 없음"}
            continue
        A, B = still[pv], still[nx]
        d = diff(A["river"], B["river"])
        md = diff(A["meld"], B["meld"])
        segs[a["seg"]] = {"prev_still": pv, "next_still": nx,
                          "river_new": [{"tile": t["tile"], "conf": t["conf"], "row": t.get("row"), "col": t.get("col"), "sideways": bool(t.get("sideways"))}
                                        for t in d["new"]],
                          "river_gone": [{"tile": t["tile"], "row": t.get("row"), "col": t.get("col")} for t in d["gone"]],
                          "river_changed": d["changed"],
                          "river_count": [len(A["river"]), len(B["river"])],
                          "meld_new": [t["tile"] for t in md["new"]], "meld_gone": [t["tile"] for t in md["gone"]],
                          "meld_count": [len(A["meld"]), len(B["meld"])]}
        x = segs[a["seg"]]
        if x["river_new"] or x["river_gone"] or x["river_changed"] or x["meld_new"] or x["meld_gone"]:
            print(f"구간 {a['seg']:3d} {a['t0']}–{a['t1']} 강 +{[t['tile'] + ('*' if t['sideways'] else '') for t in x['river_new']]} "
                  f"-{[t['tile'] for t in x['river_gone']]} 바뀜 {x['river_changed']} 울기 +{x['meld_new']} -{x['meld_gone']}")
    hc.jsave(hc.out_dir(gid) / "river_states.json", {"id": gid, "river_view": river_v, "meld_view": meld_v, "still": still, "segments": segs})


if __name__ == "__main__":
    main()
