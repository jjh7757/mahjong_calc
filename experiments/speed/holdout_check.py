"""평가 밖 사진으로 자리 판독 틀 규칙 확인(참고용, 2026-10-26 밤 사용자 허락: "A·E 와 매장 거치 사진을 틀 규칙 확인용(참고)으로만,
숫자 보고는 B·C·D 와 따로"). 틀 규칙은 B·C·D 로 만들었으므로 여기 사진은 한 번도 안 본 사진이다. 규칙을 이 결과로 고치지 않는다.

세트
  AE     갤러리 A(k20·k24, 위 자리, 울기는 양 끝 엎은 안깡)·E(k00·k04, 왼쪽 자리) — grid5_scenes 자리 크롭
  field  10/24 매장 카메라 헤드 사진에서 앱(locate)이 잘라 둔 화료자 손패 크롭 27장(captures/*/hand_*.jpg).
         장수 정답은 크롭을 눈으로 세어 적음(FIELD_TRUTH). 크롭에 울기가 안 들어간 것(10장)은 장수가 13·14 가 아니므로
         "지금 방식으로 넘김" 이 맞는 답이고, 통과하면 위험(unsafe).

  python -I experiments/speed/holdout_check.py [--augs]     결과 results/overfit/holdout*.json·txt
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
import bench as b  # noqa: E402
import overfit_check as oc  # noqa: E402
import seat_det_variants as dv  # noqa: E402
import seat_yolo as sy  # noqa: E402

CAP = b.G.parent / "captures"
# 크롭을 눈으로 센 (손패 줄 + 떨어진 한 장, [울기 묶음 장수]) — 크롭에 보이는 것 기준
FIELD_TRUTH = {
    "115559/hand_bottom": (13, []),   # 손패가 1·2·3·7장 무더기로 떨어져 있음, 크롭이 30° 기움
    "115801/hand_bottom": (13, []),   # 같은 손패
    "115929/hand_top": (10, [3]),     # 4·2·3·1(白) 무더기 + 모서리 發 퐁
    "120037/hand_right": (13, []),    # 白 3장 포함
    "120755/hand_right": (13, []),
    "122922/hand_right": (13, []),
    "124007/hand_top": (13, []),      # 白 3장 포함(화료패 2s 는 크롭에 없음)
    "124329/hand_top": (10, []),      # 울기가 크롭 밖 — 넘김이 정답
    "125053/hand_top": (10, [3]),     # + 따로 놓인 2장, 모서리 發 퐁
    "130533/hand_top": (10, []), "131210/hand_top": (10, []), "131823/hand_right": (10, []),
    "132647/hand_top": (10, []), "133011/hand_top": (10, []), "133620/hand_top": (10, []),
    "134323/hand_top": (10, []), "135148/hand_top": (10, []),
    "135912/hand_left": (13, []),     # 크롭이 35° 기움
    "140302/hand_left": (13, []), "140750/hand_left": (13, []),
    "140918/hand_left": (13, []),     # + 따로 놓인 2장(七万·東)
    "141941/hand_left": (10, []), "142236/hand_left": (10, []), "142430/hand_left": (10, []),
    "142711/hand_left": (10, []), "143328/hand_left": (10, []), "143443/hand_left": (10, []),
}


def items():
    out = []
    for s in "AE":
        for p in b.PHOTOS[s]:
            meld = [len(m.split()) for m in b.TRUTH[s][2]]
            out.append(("AE", f"{s}/{p}", str(b.G / s / p / b.TRUTH[s][0]), (len(b.TRUTH[s][1].split()), meld)))
    for k, t in FIELD_TRUTH.items():
        d, f = k.split("/")
        out.append(("field", k, str(CAP / f"20261024_{d}" / f"{f}.jpg"), t))
    return out


CONFIGS = {
    "처음(장수 검사만)": {"own": False, "ink": False, "safe": False},
    "조치 후": {"own": True, "ink": True, "safe": True},
}


def _job(job):
    set_name, key, path, truth, aug = job
    det = sy.rv.TileDetector(conf=0.04)
    rgb = np.asarray(oc.augment(Image.open(path).convert("RGB"), aug))
    white = sy.rv.white_mask(rgb)
    res = {}
    for name, c in CONFIGS.items():
        dv.OWN = c["own"]
        boxes = dv.mosaic(det, rgb, 4)[0]
        if boxes is None:
            res[name] = ("fallback", None)
            continue
        if c["ink"]:
            boxes = [x for x in boxes if sy.ink(rgb, x) >= sy.INK_MIN]
        st = oc.structure_cached(rgb, white, [tuple(x) for x in boxes], 0.35, 2.5)
        got = (len(st["hand"]) + (1 if st["separate"] else 0), [len(m) for m in st["melds"]]) if st else None
        if not sy.valid(st) or (c["safe"] and not sy.safe_ok(st, rgb)):
            res[name] = ("fallback", got)
        else:
            res[name] = ("correct" if tuple(got) == (truth[0], truth[1]) else "unsafe", got)
    return {"set": set_name, "key": key, "aug": aug, "truth": truth, "res": res}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--augs", action="store_true", help="흔든 사진 17종도")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    augs = oc.AUGS if a.augs else ["none"]
    jobs = [(s, k, p, t, g) for s, k, p, t in items() for g in augs]
    with ProcessPoolExecutor(a.workers) as ex:
        rows = list(ex.map(_job, jobs))
    out = oc.OUT / f"holdout{'_augs' if a.augs else ''}.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    for set_name in ("AE", "field"):
        sub = [r for r in rows if r["set"] == set_name]
        reachable = sum(1 for r in sub if r["truth"][0] + 3 * len(r["truth"][1]) in (13, 14))
        print(f"\n[{set_name}] 크롭×흔들기 {len(sub)}개 (장수가 13·14 라 맞힐 수 있는 것 {reachable})")
        for name in CONFIGS:
            c = {k: sum(1 for r in sub if r["res"][name][0] == k) for k in ("correct", "fallback", "unsafe")}
            print(f"   {name:12s} correct {c['correct']:3d}  fallback {c['fallback']:3d}  unsafe {c['unsafe']:3d}")
        if not a.augs:
            for r in sub:
                print(f"     {r['key']:22s} 정답 {r['truth']}  " + "  ".join(
                    f"{n[:2]}: {v[0]}{'' if v[1] is None else ' ' + str(tuple(v[1]))}" for n, v in r["res"].items()))
        else:
            for name in CONFIGS:
                bad = sorted({(r["key"], r["aug"]) for r in sub if r["res"][name][0] == "unsafe"})
                print(f"   {name} unsafe: {bad[:12]}{' …' if len(bad) > 12 else ''}")


if __name__ == "__main__":
    main()
