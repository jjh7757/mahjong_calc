"""11-14 세트(data/v1114 · data/v1114rec)에서 지금 운영 모델의 기준선(2026-11-16, 학습 없음).

  python -X utf8 experiments/tile_classifier/v1114_baseline.py cls     # 분류기: 서버 LocalReader.probs(운영 ONNX) 그대로
  python -X utf8 experiments/tile_classifier/v1114_baseline.py role    # 역할 모델: 서버 RoleNet(운영 ONNX) 그대로, 후처리 규칙 없음

분류기 읽기 세 가지(크롭은 세트에 저장된 세운 크롭):
  up    = 긴 변 96 미만이면 96 으로 키워(서버 read_small 과 같은 식) 저장된 방향 그대로
  up2   = up 을 0°·180° 두 방향 중 확신 높은 쪽(서버 read_any 가 세로 상자에 하는 것)
  raw   = 키우지 않고 저장된 방향 그대로(저화질에서 키우기 효과를 보려는 대조)
저장된 방향은 2992 에서 운영 분류기가 고른 방향이다 — 저화질 줄의 up·raw 는 방향을 미리 아는 셈이라 up2 가 실제에 가깝다.
역할: 토큰은 로더가 만든 것(화료 사진은 화료자 자리 기준, 그 밖은 사진 아래 기준). all = 라벨 상자, det = 그 화질에서 검출기가 잡은 상자.
결과: data/v1114/baseline_1116_{cls,role}.json (gitignore).
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import v1114_load as vl  # noqa: E402
import v1114rec_load as vr  # noqa: E402
from app import local_read as lr  # noqa: E402
from app import roles  # noqa: E402

OUT = vl.V
CLASSES = lr.CLASSES


def read_set(reader, items: list[dict]) -> dict:
    ims = [Image.open(x["path"]).convert("RGB") for x in items]
    up = [vl.small_upscale(im, lr.SMALL_TILE) for im in ims]

    def probs(lst):
        return np.concatenate([reader.probs(lst[i:i + 256]) for i in range(0, len(lst), 256)])

    p0, p180, praw = probs(up), probs([im.rotate(180) for im in up]), probs(ims)
    best = np.where((p0.max(1) >= p180.max(1))[:, None], p0, p180)
    lab = np.array([CLASSES.index(x["tile"]) for x in items])
    out = {"n": len(items), "small": int(sum(max(im.size) < lr.SMALL_TILE for im in ims)), "long_side_median": float(np.median([max(im.size) for im in ims]))}
    for k, p in (("up", p0), ("up2", best), ("raw", praw)):
        pred = p.argmax(1)
        bad = np.flatnonzero(pred != lab)
        out[k] = {"ok": int(len(items) - len(bad)), "wrong_pairs": dict(Counter(f"{CLASSES[lab[i]]}>{CLASSES[pred[i]]}" for i in bad).most_common()),
                  "wrong": [{"id": items[i]["id"], "tile": items[i]["tile"], "pred": CLASSES[pred[i]], "conf": round(float(p[i].max()), 3), "part": items[i].get("part")}
                            for i in bad]}
        if k == "up2":
            out[k]["turned_180"] = int((p180.max(1) > p0.max(1)).sum())
            units = {}
            for i, x in enumerate(items):
                units.setdefault(x["unit"], []).append(bool(pred[i] == lab[i]))
            out[k]["units"] = len(units)
            out[k]["units_all_ok"] = int(sum(all(v) for v in units.values()))
    return out


def cls() -> None:
    reader = lr.LocalReader()
    res = {"model": str(lr.CLS_MODEL.name), "small_tile": lr.SMALL_TILE, "sets": {}}
    jobs = [(f"v1114/{q}/{sp}", vl.cls_items(q, sp)) for sp in ("dev", "train") for q in vl.QS]
    for sp in ("dev", "train"):
        its = vr.cls_items(sp)
        jobs.append((f"v1114rec/rec1496/{sp}", its))
        for part in ("pair", "mid", "new"):
            jobs.append((f"v1114rec/rec1496/{sp}/{part}", [x for x in its if x["part"] == part]))
    for name, items in jobs:
        r = read_set(reader, items)
        res["sets"][name] = r
        print(f"{name:32s} n {r['n']:5d} 작은 크롭 {r['small']:5d} 긴 변 {r['long_side_median']:.0f} | up {r['up']['ok']} up2 {r['up2']['ok']} raw {r['raw']['ok']} "
              f"| 실물 패 {r['up2']['units_all_ok']}/{r['up2']['units']} | up2 틀림 {list(r['up2']['wrong_pairs'].items())[:6]}", flush=True)
    (OUT / "baseline_1116_cls.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


def score(scenes: list[dict], net) -> dict:
    conf = {r: Counter() for r in vl.ROLES}
    c = Counter()
    bad_scenes = []
    for s in scenes:
        if s["n_face"] == 0:
            continue
        x = np.asarray(s["x"], np.float32)
        assert x.shape[1] == net.feat, (x.shape, net.feat)
        pred = net.predict(x)[0][:s["n_face"]]
        nbad = 0
        for r, o, p in zip(s["roles"], s["owners"], pred):
            if r not in vl.ROLES:
                if r == "unmatched":
                    c["unmatched"] += 1
                    c["unmatched_as_" + p] += 1
                continue
            conf[r][p] += 1
            c["n"] += 1
            c["ok"] += p == r
            nbad += p != r
            if o == "winner":
                c["n_win"] += 1
                c["ok_win"] += p == r
        if s.get("winner"):
            own = [o != "other" for o in s["owners"]]
            cl = Counter(r for r, k in zip(s["roles"], own) if k)
            cp = Counter(p for p, k in zip(pred, own) if k)
            c["win_scenes"] += 1
            ok = cl["hand"] == cp["hand"] and cl["meld"] == cp["meld"]
            c["win_seat_ok"] += ok
            if not ok:
                bad_scenes.append({"name": s["name"], "hand": [cl["hand"], cp["hand"]], "meld": [cl["meld"], cp["meld"]]})
        c["scenes"] += 1
        c["scenes_all_ok"] += nbad == 0
    return {"all": f"{c['ok']}/{c['n']}", "winner_side": f"{c['ok_win']}/{c['n_win']}", "win_seat_ok": f"{c['win_seat_ok']}/{c['win_scenes']}",
            "scenes_all_ok": f"{c['scenes_all_ok']}/{c['scenes']}", "roles": {r: f"{conf[r][r]}/{sum(conf[r].values())}" for r in vl.ROLES},
            "confusion": {r: dict(v) for r, v in conf.items()}, "unmatched": {k: v for k, v in c.items() if k.startswith("unmatched")}, "win_seat_bad": bad_scenes}


def role() -> None:
    net = roles.role_net()
    res = {"model": roles.ROLE_MODEL.name, "feat": net.feat, "sets": {}}
    jobs = []
    for sp in ("dev", "train"):
        jobs.append((f"v1114/all/{sp}", vl.role_scenes(sp, "all")))
        for ph in ("play", "end"):
            jobs.append((f"v1114/all/{sp}/{ph}", [s for s in vl.role_scenes(sp, "all") if s["phase"] == ph]))
        for q in vl.QS:
            jobs.append((f"v1114/det_{q}/{sp}", vl.role_det_scenes(q, sp, side="winner")))
        jobs.append((f"v1114rec/all/{sp}", vr.role_scenes(sp, "all")))
        for part in ("pair", "mid", "new"):
            jobs.append((f"v1114rec/all/{sp}/{part}", vr.role_scenes(sp, "all", parts=(part,))))
        jobs.append((f"v1114rec/det_rec1496/{sp}", vr.role_det_scenes(sp, side="winner")))
    for name, scenes in jobs:
        r = score(scenes, net)
        res["sets"][name] = r
        print(f"{name:30s} 상자 {r['all']:>11s} 화료자 쪽 {r['winner_side']:>9s} 화료 장면 손패·울기 수 {r['win_seat_ok']:>5s} 장면 전부 맞음 {r['scenes_all_ok']:>7s} | {r['roles']}", flush=True)
    (OUT / "baseline_1116_role.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    {"cls": cls, "role": role}[sys.argv[1]]()
