"""역할 모델만 따로 — 정답 상자(labels_v2 토큰) → 역할, 홀드아웃·운영 모델, 토큰 변형(2026-11-10, 사용자 "역할 모델 성능 테스트해줘").

검출기·분류기 오류를 빼고 역할 모델만 본다(검출기 단독은 metrics 표 1-155, 판독 끝까지는 표 1-153).
세트 = role_v2_train.is_eval 장면(10-31 + 11-07 실제 대국, 연출·입력 고친 장면·seat_grow.EXCLUDED 뺌) — B·C·D 는 역할 라벨이 없다.
모델:
  holdout = 4겹 교차 검증 가중치(role_v2_nostaged_<tag>_fold_<fold>.pt), 장면마다 그 장면 fold 를 안 배운 것
  prod    = 운영 ONNX(tile-roles-<tag>.onnx, 이 장면들을 학습함 — 참고)
변형(토큰만, 결정적): 탁자 회전 ±3·±10·±25°(펠트 가운데 기준, role_v2_train.augment 1단계와 같은 식), 뒷면 15%·30% 빠짐(씨드 3벌 합).
채점 = role_v2_train.score_scene(장면 = 화료자 쪽 손패 수·울기 수 둘 다 맞음, 상자 = 다른 사람 울기 뺌).

  ROLE_OTHER_NEG=1 ROLE_DROP_SAFE=1 ROLE_LOOSE_SHIFT=1 python -I -X utf8 experiments/tile_classifier/role_eval.py [tag=v3r15d]
결과 data/role/v2/role_eval_<tag>.json
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import role_set as rs  # noqa: E402
import role_v2_train as t  # noqa: E402

ROLES = rs.ROLES


def rotate(x: np.ndarray, deg: float) -> np.ndarray:
    x = x.copy()
    a = np.radians(deg)
    c, sn = np.cos(a), np.sin(a)
    su, sv = x[:, 0] - x[:, 6], x[:, 1] - x[:, 7]

    def rot(u, v):
        return 0.5 + (u - 0.5) * c - (v - 0.5) * sn, 0.5 + (u - 0.5) * sn + (v - 0.5) * c

    u2, v2 = rot(x[:, 0], x[:, 1])
    su2, sv2 = rot(su, sv)
    x[:, 0], x[:, 1], x[:, 6], x[:, 7] = u2, v2, u2 - su2, v2 - sv2
    tl = np.arctan2(x[:, 9], x[:, 10]) / 2 + a
    x[:, 9], x[:, 10] = np.sin(2 * tl), np.cos(2 * tl)
    return x


def drop_backs(x: np.ndarray, n_face: int, p: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    keep = np.r_[np.ones(n_face, bool), rng.random(len(x) - n_face) > p]  # 앞면이 앞, 뒷면이 뒤(labels_v2 순서)
    return x[keep]


VARIANTS = [("orig", lambda s, k: s["x"])]
VARIANTS += [(f"rot_{'p' if d > 0 else 'm'}{abs(d)}", (lambda d: lambda s, k: rotate(s["x"], d))(d)) for d in (3, -3, 10, -10, 25, -25)]
VARIANTS += [(f"backdrop{int(p * 100)}", (lambda p: lambda s, k: drop_backs(s["x"], s["n_face"], p, k))(p)) for p in (0.15, 0.3)]
REPS = {"backdrop15": 3, "backdrop30": 3}


def run(tag: str) -> dict:
    scenes = [s for s in t.load() if t.is_eval(s)]
    hold = {f: rs.load_nets(t.V2 / f"role_v2_nostaged_{tag}_fold_{f}.pt") for f in t.FOLDS}
    prod = t.Onnx(t.MODELS / f"tile-roles-{tag}.onnx")
    models = {"holdout": lambda s, x: t.probs_torch(hold[s["fold"]], x), "prod": lambda s, x: prod(x)}
    out = {}
    for mname, mf in models.items():
        for vname, vf in VARIANTS:
            agg = Counter()
            conf = {r: Counter() for r in ROLES}
            bad, per = [], {}
            for s in scenes:
                for k in range(REPS.get(vname, 1)):
                    x = vf(s, k)
                    r = t.score_scene(s, mf(s, x))
                    agg["scene"] += r["seat_ok"]
                    agg["n_scene"] += 1
                    for key in ("ok_fair", "n_fair", "ok_win", "n_win"):
                        agg[key] += r.get(key, 0)
                    for i, it in enumerate(s["items"][: s["n_face"]]):
                        if it["role"] in ROLES and not (it["role"] == "meld" and it.get("owner") == "other"):
                            conf[it["role"]][r["pred"][i]] += 1
                    if not r["seat_ok"]:
                        bad.append(s["name"][-15:])
                    if k == 0:
                        per[s["name"]] = dict(seat_ok=r["seat_ok"], hand=r["hand"], meld=r["meld"], wrong=r["wrong"])
            res = dict(scene=f"{agg['scene']}/{agg['n_scene']}", box=f"{agg['ok_fair']}/{agg['n_fair']}", winner=f"{agg['ok_win']}/{agg['n_win']}",
                       recall={r: f"{c[r]}/{sum(c.values())}" for r, c in conf.items() if sum(c.values())},
                       confusion={r: dict(c) for r, c in conf.items()}, seat_bad=sorted(set(bad)), per=per)
            out[f"{mname}/{vname}"] = res
            print(f"{mname:8s} {vname:11s} 장면 {res['scene']:>6s}  상자 {res['box']:>11s}  화료자 {res['winner']:>9s}  틀린 장면 {res['seat_bad']}", flush=True)
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    tag = sys.argv[1] if len(sys.argv) > 1 else "v3r15d"
    assert t.SHIFT_ON and rs.OTHER_NEG, "ROLE_OTHER_NEG=1 ROLE_DROP_SAFE=1 ROLE_LOOSE_SHIFT=1 로 실행(학습 때와 같은 채점 세트)"
    res = run(tag)
    print("\n홀드아웃 orig 역할별 재현:", res["holdout/orig"]["recall"])
    print("홀드아웃 orig 혼동:", res["holdout/orig"]["confusion"])
    (t.V2 / f"role_eval_{tag}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
