"""10-31 매장 25회를 YOLO26(HaseLab)으로 읽어 화료자 손패·울기를 채점한다(2026-11-01). API 없음, 노트북 CPU.

방식(같은 사진을 차례로, 화료자 자리는 meta.json 의 winner_side 를 그대로 쓴다):
  rot90  화료자가 아래로 오게 90° 단위로 돌림 + 손패 윤곽 기울기 보정 → 구역 → 패 → 분류(README 5절의 mask+frag+nopad+line)
  grid   앱의 자리 크롭(격자 + 가운데 쪽 40) → 패 → 분류. 구역 모델 안 씀
  a24    15° 씩 24각도에서 손패가 가장 잘 잡힌 각도 + pick(패 YOLO 후보와 색 후보 중 검사로 고르기, README 5절)

채점: seat_grow.py 와 같은 정답(믿을 만한 7장, 나머지는 장수만). 비교값은 같은 사진의 Gemini /v2/seat 폭 40(seat_grow.json, 측정 시각 다름).
  python -I experiments/yolo/visit_yolo26.py [--modes rot90,grid,a24] [--only 1248]
  python -I experiments/yolo/visit_yolo26.py --show
결과 experiments/yolo/results/visit1031/rows.json, 그림 vis/
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "speed"))
import hybrid as hy  # noqa: E402
import run_yolo as ry  # noqa: E402
import seat_grow as sg  # noqa: E402
import yolo26_eval as ye  # noqa: E402

OUT = HERE / "results" / "visit1031"
TILE_CFG = {"mask", "frag", "nopad"}
TURN = {"bottom": 0, "right": -90, "top": 180, "left": 90}  # ye.rotate 는 반시계


def loose(ts: list[str]) -> list[str]:
    return ["5" + t[1] if t[0] == "0" else t for t in ts]


def to_dets(ds: list) -> list[dict]:
    return [dict(t=t[0], x=float(t[2][0]), y=float(t[2][1])) for t in ds]


def rot90_dets(y: ye.Y26, img: np.ndarray, side: str):
    """돌린 사진에서 화료자 손패. 돌려주는 것: dets, 돌린 사진, 찾은 구역 상자, 메모"""
    a = TURN[side]
    rot, m, boxes = y._predict_at(img, a)
    def low_hands(bs, h):
        return [t for t in bs.get("self_hand", []) if (t[1][1] + t[1][3]) / 2 > h * 0.5]
    hands = low_hands(boxes, rot.shape[0])
    if not hands:
        return [], rot, [], "손패 구역 없음"
    conf, box, poly = max(hands, key=lambda t: t[0])
    t = y.tilt(poly)
    if 2 <= abs(t) <= 30:
        rot2, m2, boxes2 = y._predict_at(img, a + t)
        h2 = low_hands(boxes2, rot2.shape[0])
        if h2:
            rot, m, boxes = rot2, m2, boxes2
            conf, box, poly = max(h2, key=lambda x: x[0])
    d = dict(boxes=boxes, rot=rot, hand=box, poly=poly)
    ye.Y26._finish({side: d}, {})
    regs = [d["hand"]] + d["melds"]
    return y.tiles(rot, regs, TILE_CFG, [d["poly"]] + d["meld_polys"]), rot, regs, f"구역 {conf:.2f} 기울기 {t:.0f}° 울기구역 {len(d['melds'])}"


def grid_dets(y: ye.Y26, path: Path, s: dict):
    """앱과 같은 자리 크롭에 패 모델을 바로."""
    im = Image.open(path).convert("RGB")
    crop = sg.crop(im, sg.seat_box(s["grid"], s["side"], 40), s["side"])
    arr = cv2.cvtColor(np.asarray(crop), cv2.COLOR_RGB2BGR)
    h, w = arr.shape[:2]
    return y.tiles(arr, [np.array([0, 0, w, h], float)], {"frag", "nopad"}), arr, [], ""


def a24_dets(y: ye.Y26, img: np.ndarray, n: str, side: str):
    hands, _ = y.regions_cached(img, "kakao", OUT / "regions_cache.json", n)
    d = hands.get(side)
    if not d:
        return [], img, [], f"{side} 손패 구역 없음(찾은 자리 {sorted(hands)})"
    cands = {"yolo": y.tiles(d["rot"], [d["hand"]] + d["melds"], TILE_CFG, [d["poly"]] + d["meld_polys"]),
             "cv": y.cv_hand(img, d, n, {}, set())}

    def rank(item):
        _, ds = item
        hh, mm, _ = hy.split(to_dets(ds), line_merge=True) if ds else ([], [], 0)
        return (hy.check(hh, mm)[0] if hh else False, -abs(len(hh) + 3 * len(mm) - 13), float(np.mean([t[1] for t in ds])) if ds else 0.0)

    picked, dets = max(cands.items(), key=rank)
    return dets, d["rot"], [d["hand"]] + d["melds"], f"{picked} @{d['angle']:.0f}°"


def vis(path: Path, rot: np.ndarray, dets: list, regs: list) -> None:
    im = rot.copy()
    for b in regs:
        cv2.rectangle(im, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])), (0, 200, 255), 3)
    for t in dets:
        c = (int(t[2][0]), int(t[2][1]))
        cv2.circle(im, c, 6, (0, 0, 255), -1)
        cv2.putText(im, t[0], (c[0] - 22, c[1] - 12), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 255), 3)
    if dets:
        xs = [t[2][0] for t in dets]; ys = [t[2][1] for t in dets]
        pad = 220
        im = im[max(0, int(min(ys)) - pad):int(max(ys)) + pad, max(0, int(min(xs)) - pad):int(max(xs)) + pad]
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tofile(str(path))


def judge(s: dict, dets: list) -> dict:
    face = [t for t in dets if t[0] != "back"]
    hand, melds, _ = hy.split(to_dets(face), line_merge=True) if face else ([], [], 0)
    n = len(hand) + 3 * len(melds)
    allt = hand + [t for m in melds for t in m]
    raw = [t[0] for t in face]  # hy.split 이 덩어리를 고르기 전, 구역 안에서 찾은 패 전부
    row = {"hand": " ".join(hand), "melds": [" ".join(m) for m in melds], "n": n, "count_ok": n in (13, 14), "backs": len(dets) - len(face),
           "check": bool(hand) and hy.check(hand, melds)[0], "raw": " ".join(raw), "raw_n": len(raw)}
    if s["hand"] is not None:
        truth = s["hand"] + [t for m in s["melds"] for t in m.split()]
        hit = sum((Counter(allt) & Counter(truth)).values())
        row.update(raw_hit=sum((Counter(raw) & Counter(truth)).values()), raw_exact=Counter(raw) == Counter(truth),
                   raw_missing=sorted((Counter(truth) - Counter(raw)).elements()), raw_extra=sorted((Counter(raw) - Counter(truth)).elements()))
        hit_loose = sum((Counter(loose(allt)) & Counter(loose(truth))).values())
        row.update(truth=" ".join(truth), hit=hit, hit_loose=hit_loose, total=len(truth), pred=len(allt), exact=Counter(allt) == Counter(truth),
                   missing=sorted((Counter(truth) - Counter(allt)).elements()), extra=sorted((Counter(allt) - Counter(truth)).elements()))
    return row


def run(a) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    y = ye.Y26()
    modes = a.modes.split(",")
    old = OUT / "rows.json"
    rows = [r for r in json.loads(old.read_text(encoding="utf-8")) if r["mode"] not in modes] if old.exists() else []
    for s in sg.scenes():
        if s["set"] != "visit" or (a.only and a.only not in s["name"]):
            continue
        img = ry.imread(s["path"])
        for mode in modes:
            t0 = time.perf_counter()
            try:
                if mode == "rot90":
                    dets, rot, regs, note = rot90_dets(y, img, s["side"])
                elif mode == "grid":
                    dets, rot, regs, note = grid_dets(y, s["path"], s)
                else:
                    dets, rot, regs, note = a24_dets(y, img, s["name"], s["side"])
            except Exception as e:  # 한 장 실패로 전체를 멈추지 않는다
                dets, rot, regs, note = [], img, [], f"오류 {type(e).__name__}: {e}"
            secs = time.perf_counter() - t0
            row = {"name": s["name"], "mode": mode, "side": s["side"], "s": round(secs, 2), "note": note, **judge(s, dets)}
            rows.append(row)
            vis(OUT / "vis" / f"{s['name'][9:]}_{mode}.jpg", rot, dets, regs)
            print(s["name"][9:], s["side"], mode, f"n={row['n']} 검사={row['check']} 통째={row.get('exact')} 맞음={row.get('hit')}/{row.get('total')} {secs:.1f}초 {note}", flush=True)
            (OUT / "rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def collect() -> None:
    """rot90 검출을 묶기 전 그대로 저장한다(B·C·D 포함). reg 0 = 손패 구역, 1 이상 = 울기 구역, -1 = 어느 구역도 아님."""
    y = ye.Y26()
    out = {}
    for s in sg.scenes():
        dets, _, regs, note = rot90_dets(y, ry.imread(s["path"]), s["side"])

        def region(t):
            x, yy = t[2]
            return next((i for i, b in enumerate(regs) if b[0] <= x <= b[2] and b[1] <= yy <= b[3]), -1)

        out[s["name"]] = {"set": s["set"], "side": s["side"], "note": note, "hand": s["hand"], "melds": s["melds"],
                          "dets": [dict(t=t[0], c=round(t[1], 3), x=float(t[2][0]), y=float(t[2][1]), s=round(t[3], 1), reg=region(t)) for t in dets]}
        print(s["name"], len(dets), note, flush=True)
    (OUT / "dets_rot90.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


def assemble(dets: list[dict]) -> tuple[list[str], list[list[str]], int]:
    """구역을 믿는 묶기: 손패 구역 안의 패는 틈이 있어도 다 손패, 울기는 울기 구역과 손패 줄 오른쪽 끝의 모양 맞는 덩어리만."""
    row = sorted((d for d in dets if d["reg"] == 0 and d["t"] != "back"), key=lambda d: d["x"])
    if not row:
        return [], [], len(dets)
    pitch = float(np.median([d["s"] for d in row]))
    cols: list[dict] = []
    for d in row:  # 한 칸에 둘이면(패 아래쪽을 한 장 더 잡음) 크고 확신 높은 쪽
        if cols and d["x"] - cols[-1]["x"] < pitch * 0.25:  # 마스크 중심이 칸마다 흔들려 0.5 면 옆 패를 지운다(131411·133826)
            if d["c"] * d["s"] > cols[-1]["c"] * cols[-1]["s"]:
                cols[-1] = d
            continue
        cols.append(d)

    def groups(ds: list[dict]) -> list[list[dict]]:
        out: list[list[dict]] = []
        for d in ds:
            if out and d["x"] - out[-1][-1]["x"] < pitch * 1.6:
                out[-1].append(d)
            else:
                out.append([d])
        return out

    melds: list[list[str]] = []
    gs = groups(cols)
    while len(gs) > 1:  # 울기는 화료자 오른쪽에 놓는다
        m = hy.meld_of([d["t"] for d in gs[-1]])
        if not m:
            break
        melds.insert(0, m)
        gs.pop()
    hand = [d["t"] for g in gs for d in g]
    dropped = 0
    for reg in sorted({d["reg"] for d in dets if d["reg"] > 0}):
        ds = sorted((d for d in dets if d["reg"] == reg), key=lambda d: d["x"])
        for g in groups(ds):
            ts = [d["t"] for d in g]
            m = hy.meld_of(ts) or hy.meld_of([t for t in ts if t != "5z"])  # 탁자 흰 테두리를 5z 로 읽는다
            if m and len(hand) + 3 * (len(melds) + 1) <= 14:
                melds.append(m)
            else:
                dropped += len(g)
    return hand, melds, dropped


def rescore() -> None:
    """같은 검출값에 옛 묶기(hy.split)·새 묶기를 적용해 비교. 예전 판독과 달리 호출이 없어 시각 차이가 없다."""
    data = json.loads((OUT / "dets_rot90.json").read_text(encoding="utf-8"))
    parts = [("B·C·D 6", lambda v: v["set"] == "bcd"),
             ("오전 10", lambda v: v["set"] == "visit" and v["_n"] < "20261031_14"),
             ("오후 15", lambda v: v["set"] == "visit" and v["_n"] >= "20261031_14")]
    rows = []
    for n, v in data.items():
        v["_n"] = n
        face = [d for d in v["dets"] if d["t"] != "back"]
        for rule, (hand, melds, _) in (("옛", hy.split(face, line_merge=True) if face else ([], [], 0)), ("새", assemble(v["dets"]))):
            total = len(hand) + 3 * len(melds)
            allt = hand + [t for m in melds for t in m]
            r = {"name": n, "rule": rule, "n": total, "count_ok": total in (13, 14), "check": bool(hand) and hy.check(hand, melds)[0], "hand": hand, "melds": melds}
            if v["hand"] is not None:
                truth = v["hand"] + [t for m in v["melds"] for t in m.split()]
                r.update(exact=Counter(allt) == Counter(truth), hit=sum((Counter(allt) & Counter(truth)).values()), total=len(truth), pred=len(allt),
                         struct=sorted(hand) == sorted(v["hand"]) and sorted(" ".join(sorted(m)) for m in melds) == sorted(" ".join(sorted(m.split())) for m in v["melds"]),
                         missing=sorted((Counter(truth) - Counter(allt)).elements()), extra=sorted((Counter(allt) - Counter(truth)).elements()))
            rows.append(r)
    (OUT / "assemble.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    for label, f in parts:
        names = {n for n, v in data.items() if f(v)}
        for rule in ("옛", "새"):
            v = [r for r in rows if r["name"] in names and r["rule"] == rule]
            k = [r for r in v if "exact" in r]
            print(f"{label} {rule}: 장수 {sum(r['count_ok'] for r in v)}/{len(v)} 검사통과 {sum(r['check'] for r in v)}"
                  + (f" | 패 정답 {sum(r['exact'] for r in k)}/{len(k)} 구조 정답 {sum(r['struct'] for r in k)} 재현 {sum(r['hit'] for r in k)}/{sum(r['total'] for r in k)}"
                     f" 정밀 {sum(r['hit'] for r in k)}/{sum(r['pred'] for r in k)} 틀린 채 검사통과 {sum(1 for r in k if r['check'] and not r['exact'])}" if k else ""))
    print("-- 사진별 새 묶기")
    for r in rows:
        if r["rule"] == "새":
            print(r["name"][-6:], r["n"], "검사", r["check"], "정답", r.get("exact"), "구조", r.get("struct"), "|", " ".join(r["hand"]), r["melds"], "빠짐", r.get("missing"), "더함", r.get("extra"))


def show() -> None:
    rows = json.loads((OUT / "rows.json").read_text(encoding="utf-8"))
    for mode in dict.fromkeys(r["mode"] for r in rows):
        for label, f in [("오전 10", lambda n: n < "20261031_14"), ("오후 15", lambda n: n >= "20261031_14")]:
            v = [r for r in rows if r["mode"] == mode and f(r["name"])]
            k = [r for r in v if "exact" in r]
            t = sorted(r["s"] for r in v)
            line = f"{mode} {label}: 장수 {sum(r['count_ok'] for r in v)}/{len(v)} 검사통과 {sum(r['check'] for r in v)}"
            if k:
                tot, pr = sum(r["total"] for r in k), sum(r["pred"] for r in k)
                line += (f" | 정답 {sum(r['exact'] for r in k)}/{len(k)} 재현 {sum(r['hit'] for r in k)}/{tot} 정밀 {sum(r['hit'] for r in k)}/{pr}"
                         f" (적5 구분 없이 {sum(r['hit_loose'] for r in k)}) 틀린 채 검사통과 {sum(1 for r in k if r['check'] and not r['exact'])}")
            print(line + f" | 시간 {statistics.median(t):.1f} / {t[min(len(t) - 1, int(.9 * len(t)))]:.1f} / {t[-1]:.1f}")
    gem = {r["name"]: r["by_grow"].get("40") for r in json.loads(sg.OUT.read_text(encoding="utf-8")) if r["set"] == "visit"}
    print("-- 사진별 (장수, 정답) / Gemini 폭 40")
    for name in dict.fromkeys(r["name"] for r in rows):
        part = {r["mode"]: (r["n"], r.get("exact")) for r in rows if r["name"] == name}
        g = gem.get(name) or {}
        print(name[9:], part, "Gemini", (g.get("n"), g.get("ok")))
    print("-- 정답 있는 사진의 차이")
    for r in rows:
        if "exact" in r and not r["exact"]:
            print(r["name"][9:], r["mode"], "빠짐", r["missing"], "더함", r["extra"], r["note"])


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--modes", default="rot90,grid,a24")
    p.add_argument("--only", default="")
    p.add_argument("--show", action="store_true")
    p.add_argument("--collect", action="store_true", help="rot90 검출을 묶기 전 그대로 저장")
    p.add_argument("--rescore", action="store_true", help="저장한 검출에 옛·새 묶기 적용")
    args = p.parse_args()
    collect() if args.collect else rescore() if args.rescore else show() if args.show else run(args)
