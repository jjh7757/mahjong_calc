"""역할 모델 v2 라벨(41장, role_v2_apply.py → data/role/v2/labels_v2.json)로 학습·채점(2026-11-08, 노트북 CPU, API 없음). metrics 표 1-124 기준·1-125 결과.

입력 x 는 서버 roles.tokens 와 같은 11칸(labels_v2 의 x 그대로), 라벨 y 는 ROLES 인덱스(다른 사람 울기도 meld, other·뒷면 -1).
설정 두 벌(사용자 11-08 "연출 넣고 평가에서 빼고, 넣은 것·뺀 것 비교"):
  staged  : 41장 전부 학습(연출 8장 포함)
  nostaged: 연출(_flags 가 '연출' 로 시작) 8장 빼고 33장
나누기 = 4겹(10-31 오전 / 10-31 오후 / 11-07 오전 / 11-07 오후, 시각 14시 기준). 시험 fold 의 장면은 연출이든 아니든 학습에서 뺀다.
채점 = 실제 대국 사진만(kind=photo, 연출 아님, seat_grow.EXCLUDED 아님) 28장:
  (1) 화료자 쪽(다른 사람 것으로 라벨된 상자를 뺀 전부) 손패 수·울기 수가 라벨과 둘 다 같은 장면 수
  (2) 상자 정확도(다른 사람 울기 빼고 — 운영 모델은 그걸 other 로 배웠다) · (3) 전부
  (4) 테스트 15장(10-24 삼각대, role_field.tokens) 상자 정확도, 전부(41장 또는 33장)로 미세 조정한 모델
전 = 운영 tile-roles-rot.onnx: 10-31 사진은 그 사진을 안 배운 fold ONNX(tile-roles-rot_fold_*), 11-07 은 운영 전체(11-07 안 배움).
증강(학습 장면만, 씨드마다 사본 3개 + role_set.batch 의 온라인 지터): 탁자 전체 회전 σ2°(±5°), 앞면 상자 4% 반쪽 둘로 쪼개기
(검출기가 강 패·짝을 반쪽 상자로 잡던 증상, 132239·153029), 뒷면 상자 0~30% 빠짐.

  python -I -X utf8 experiments/tile_classifier/role_v2_train.py cv staged|nostaged [--pre pre_synth8k_rot_base2.pt] [--aug 3]
  python -I -X utf8 experiments/tile_classifier/role_v2_train.py base          # 운영 ONNX 로 같은 채점
결과 data/role/v2/cv_<설정>.json, 가중치 data/role/v2/role_v2_<설정>_{all,fold_*}.pt
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import role_field as rf  # noqa: E402
import role_set as rs  # noqa: E402

sg = rs.sg
V2 = HERE / "data" / "role" / "v2"
MODELS = HERE / "server_bench" / "models"
ROLES = rs.ROLES
FOLDS = ("1031am", "1031pm", "1107am", "1107pm")
OLD_FOLD = {"am": "am", "pmA": "pmA", "pmB": "pmB"}


def fold_of(name: str) -> str:
    return ("1031" if name.startswith("20261031") else "1107") + ("am" if name[9:11] < "14" else "pm")


def staged(s: dict) -> bool:
    return str(s.get("flags") or "").startswith("연출")


# 2026-11-09 사용자 "손패에서 거리를 둬서 떼어둔패로": 손패 줄 끝에 붙은 채 loose 로 라벨된 두 상자(틈 −0.04·−0.03장)를
# 손패 줄 바깥쪽으로 옮겨 틈 1장을 만든다(입력 토큰만, 라벨 loose 그대로). 이 두 장면은 입력을 고쳤으므로 채점(is_eval)에서 뺀다(표 1-134).
LOOSE_SHIFT = {"20261107_153939": 0, "20261107_154904": 14}
SHIFT_ON = os.environ.get("ROLE_LOOSE_SHIFT") == "1"


def shift_loose(name: str, x: np.ndarray, y: list, items: list) -> np.ndarray:
    i = LOOSE_SHIFT[name]
    assert y[i] == 5, (name, i, y[i])
    hand = [j for j, it in enumerate(items) if it["role"] == "hand" and it.get("owner") == "winner"]
    j = min(hand, key=lambda h: abs(x[h, 0] - x[i, 0]) + abs(x[h, 1] - x[i, 1]))
    tw = float(np.median(x[hand, 2])) / 10
    gap_now = abs(x[i, 0] - x[j, 0]) - (x[i, 2] + x[j, 2]) / 20
    du = np.sign(x[i, 0] - x[j, 0]) * (1.0 * tw - gap_now)
    x = x.copy()
    x[i, 0] += du
    x[i, 6] += du
    return x


def load() -> list[dict]:
    d = json.loads((V2 / "labels_v2.json").read_text(encoding="utf-8"))
    out = []
    for name, s in d.items():
        x = np.array(s["x"], np.float32)
        if SHIFT_ON and name in LOOSE_SHIFT:
            x = shift_loose(name, x, s["y"], s["items"])
        y = list(s["y"])
        if rs.OTHER_NEG:  # 역할 없는 앞면(other) → -2: "손패·울기·떼어 둔 패 아님" 손실(표 1-138)
            y = [-2 if i < s["n_face"] and s["items"][i]["role"] == "other" else v for i, v in enumerate(y)]
        out.append(dict(name=name, x=x, y=y, n_face=s["n_face"], items=s["items"],
                        kind=s["kind"], staged=staged(s), fold=fold_of(name)))
    return out


# 2026-11-09 사용자 "28장 그대로 채점": 165614·181209 는 표시패 자리만 합성(리치 + 깡 표시패 4장을 화료자 쪽 짝으로, role_v2_pair_synth2.py)
# 이고 나머지는 실제 사진이라 채점에 그대로 둔다. 표 1-134(v3r15b)는 이 결정 전이라 두 장면을 뺀 24장 — 그걸 다시 재려면 ROLE_EVAL_COMPOSITE=0.
EVAL_COMPOSITE = {"20261031_165614", "20261031_181209"} if os.environ.get("ROLE_EVAL_COMPOSITE", "1") == "1" else set()


def is_eval(s: dict) -> bool:
    return ((s["kind"] == "photo" or s["name"] in EVAL_COMPOSITE) and not s["staged"] and s["name"] not in sg.EXCLUDED
            and not (SHIFT_ON and s["name"] in LOOSE_SHIFT))


def augment(s: dict, rng: np.random.Generator) -> dict:
    """실제 입력 변형 한 벌: 탁자 회전 · 반쪽 상자 쪼개기 · 뒷면 빠짐. 라벨은 상자를 따라간다."""
    x, y = s["x"].copy(), list(s["y"])
    # 1) 탁자 전체 회전(펠트 가운데 기준). 그림 좌표(v 아래)에서 양수 = 시계 방향 = 패 기울기도 +θ
    th = float(np.clip(rng.normal(0, 2.0), -5, 5))
    t = np.radians(th)
    c, sn = np.cos(t), np.sin(t)
    su, sv = x[:, 0] - x[:, 6], x[:, 1] - x[:, 7]

    def rot(u, v):
        return 0.5 + (u - 0.5) * c - (v - 0.5) * sn, 0.5 + (u - 0.5) * sn + (v - 0.5) * c

    u2, v2 = rot(x[:, 0], x[:, 1])
    su2, sv2 = rot(su, sv)
    x[:, 0], x[:, 1], x[:, 6], x[:, 7] = u2, v2, u2 - su2, v2 - sv2
    tl = np.arctan2(x[:, 9], x[:, 10]) / 2 + t
    x[:, 9], x[:, 10] = np.sin(2 * tl), np.cos(2 * tl)
    # 2) 앞면 4% 를 패 폭 방향 반쪽 둘로(같은 라벨)
    rows, labs = [], []
    for i in range(len(x)):
        r = x[i]
        if r[4] == 0 and rng.random() < 0.04:
            for sgn in (-1, 1):
                q = r.copy()
                q[2] = r[2] / 2
                q[0] = r[0] + sgn * r[2] / 40  # 폭/4 (특징 폭은 ×10)
                q[6] = r[6] + sgn * r[2] / 40
                q[5] = float(q[2] > q[3] * 1.15)
                rows.append(q)
                labs.append(y[i])
        else:
            rows.append(r)
            labs.append(y[i])
    x, y = np.array(rows, np.float32), labs
    # 3) 뒷면 0~30% 빠짐
    p = rng.uniform(0, 0.3)
    keep = (x[:, 4] == 0) | (rng.random(len(x)) > p)
    x, y = x[keep], [l for l, k in zip(y, keep) if k]
    face = x[:, 4] == 0
    order = np.r_[np.where(face)[0], np.where(~face)[0]]  # 앞면 → 뒷면 순 유지
    return dict(name=s["name"] + "#aug", x=x[order], y=[y[i] for i in order], n_face=int(face.sum()))


WIN_ROLES = (0, 1, 5)  # hand·meld·loose


def win_idx(s: dict) -> list[int]:
    """화료자 묶음(owner winner 이고 손패·울기·떼어 둔 패) 앞면 번호."""
    return [i for i, it in enumerate(s["items"]) if it.get("owner") == "winner" and s["y"][i] in WIN_ROLES]


def swap_winner(a: dict, b: dict, rng: np.random.Generator) -> dict | None:
    """a 의 화료자 묶음을 지우고 b 의 화료자 묶음을 a 의 손패 자리에 옮겨 놓는다(손패 중앙을 맞추고 패 크기 비로 늘이고 줄임).
    남은 a 앞면과 패 0.6장 안으로 겹치면 None."""
    ia, ib = win_idx(a), win_idx(b)
    ha = [i for i in ia if a["y"][i] == 0]
    hb = [i for i in ib if b["y"][i] == 0]
    if len(ha) < 4 or len(hb) < 4:
        return None
    xa, xb = a["x"], b["x"]
    ca, cb = np.median(xa[ha, :2], 0), np.median(xb[hb, :2], 0)
    sa, sb = np.median(xa[ha, 2:4], 0), np.median(xb[hb, 2:4], 0)
    r = float(np.clip(np.mean(sa / np.maximum(sb, 1e-3)), 0.8, 1.25))
    su, sv = float(np.median(xa[:, 0] - xa[:, 6])), float(np.median(xa[:, 1] - xa[:, 7]))
    new = xb[ib].copy()
    new[:, :2] = ca + (new[:, :2] - cb) * r
    new[:, 2:4] *= r
    new[:, 6], new[:, 7] = new[:, 0] - su, new[:, 1] - sv
    keep_a = [i for i in range(len(xa)) if i not in set(ia)]
    rest = xa[keep_a]
    tile = float(np.mean(sa)) / 10
    face_rest = rest[rest[:, 4] == 0]
    if len(face_rest):
        d = np.sqrt(((new[:, None, :2] - face_rest[None, :, :2]) ** 2).sum(-1))
        if d.min() < 0.6 * tile:
            return None
    # 뒷면 상자가 새 묶음과 겹치면 뺀다(a 의 옛 손패 자리 근처 뒷면 등)
    back_rest = rest[:, 4] == 1
    if back_rest.any():
        d = np.sqrt(((rest[:, None, :2] - new[None, :, :2]) ** 2).sum(-1)).min(1)
        ok = ~(back_rest & (d < 0.6 * tile))
    else:
        ok = np.ones(len(rest), bool)
    ya = [a["y"][i] for i in keep_a]
    x = np.r_[new, rest[ok]]
    y = [b["y"][i] for i in ib] + [l for l, k in zip(ya, ok) if k]
    face = x[:, 4] == 0
    order = np.r_[np.where(face)[0], np.where(~face)[0]]
    return dict(name=f"{a['name']}+{b['name'][-6:]}", x=x[order], y=[y[i] for i in order], n_face=int(face.sum()))


def synth_variant(a: dict, pool: list[dict], rng: np.random.Generator) -> dict:
    """실제 입력 기반 합성 한 장면(2026-11-08 사용자 "연출 뺌 사진 기반으로 합성 배치 5000장면, 사전학습 없이 새로"):
    50% 다른 학습 사진의 화료자 묶음으로 바꿔 끼우기 → 50% 강 패 0~40% 빼기(판 초반) → augment(회전·반쪽 쪼개기·뒷면 빠짐) →
    탁자 크기·위치 지터(배율 0.92~1.08, 이동 ±0.02)."""
    s = dict(a)
    s["items"] = a["items"]
    if rng.random() < 0.5:
        for _ in range(3):
            b = pool[int(rng.integers(len(pool)))]
            if b["name"] == a["name"]:
                continue
            sw = swap_winner(a, b, rng)
            if sw is not None:
                s = sw
                break
    x, y = s["x"].copy(), list(s["y"])
    if rng.random() < 0.5:
        p = rng.uniform(0, 0.4)
        keep = np.array([not (l == 2 and rng.random() < p) for l in y])
        x, y = x[keep], [l for l, k in zip(y, keep) if k]
    s = augment(dict(name=s["name"], x=x, y=y, n_face=int((x[:, 4] == 0).sum())), rng)
    x = s["x"]
    sc, sh = rng.uniform(0.92, 1.08), rng.uniform(-0.02, 0.02, 2)
    su, sv = x[:, 0] - x[:, 6], x[:, 1] - x[:, 7]
    x[:, 0:2] = (x[:, 0:2] - 0.5) * sc + 0.5 + sh
    x[:, 2:4] *= sc
    su, sv = (su - 0.5) * sc + 0.5 + sh[0], (sv - 0.5) * sc + 0.5 + sh[1]
    x[:, 6], x[:, 7] = x[:, 0] - su, x[:, 1] - sv
    return s


def synth_set(pool: list[dict], n: int, seed: int) -> list[dict]:
    """원본 + 합성으로 모두 n 장면. 재료는 pool(그 fold 의 학습 사진)뿐."""
    rng = np.random.default_rng(30_000 + seed)
    out = [dict(name=s["name"], x=s["x"], y=s["y"], n_face=s["n_face"]) for s in pool]
    while len(out) < n:
        out.append(synth_variant(pool[int(rng.integers(len(pool)))], pool, rng))
    return out


def train_set(scenes: list[dict], k: int, seed: int) -> list[dict]:
    rng = np.random.default_rng(20_000 + seed)
    out = [dict(name=s["name"], x=s["x"], y=s["y"], n_face=s["n_face"]) for s in scenes]
    for s in scenes:
        out += [augment(s, rng) for _ in range(k)]
    return out


def probs_torch(nets, x: np.ndarray) -> np.ndarray:
    X, _, pad = rs.batch([dict(x=x, y=[-1] * len(x))], None)
    with torch.no_grad():
        return np.mean([torch.softmax(n(X, pad)[0], 1).numpy() for n in nets], 0)


class Onnx:
    def __init__(self, path: Path):
        import onnxruntime as ort

        self.s = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])

    def __call__(self, x: np.ndarray) -> np.ndarray:
        return self.s.run(None, {"x": x[None].astype(np.float32)})[0][0]


def score_scene(s: dict, p: np.ndarray) -> dict:
    pred = [ROLES[int(i)] for i in p.argmax(1)]
    nf = s["n_face"]
    lab = [it["role"] for it in s["items"]]
    own = [it.get("owner") for it in s["items"]]
    ok = Counter()
    wrong = []
    for i in range(nf):
        r = lab[i]
        if r not in ROLES:
            continue
        ok["n"] += 1
        ok["ok"] += pred[i] == r
        if not (r == "meld" and own[i] == "other"):
            ok["n_fair"] += 1
            ok["ok_fair"] += pred[i] == r
        if own[i] == "winner":
            ok["n_win"] += 1
            ok["ok_win"] += pred[i] == r
        if pred[i] != r:
            wrong.append((i, r, pred[i]))
    # 화료자 쪽 = 다른 사람 것(owner other)으로 라벨된 상자를 뺀 전부. crop_mask(v ≥ 0.94)는 서버 토큰에서 144348 손패 둘을 잘라 쓰지 않는다
    crop = [o != "other" for o in own]
    cnt = lambda rs_: Counter(r for r, k in zip(rs_, crop) if k)
    cl, cp = cnt(lab), cnt(pred[:nf])
    seat_ok = cl["hand"] == cp["hand"] and cl["meld"] == cp["meld"]
    return dict(**ok, seat_ok=seat_ok, hand=(cl["hand"], cp["hand"]), meld=(cl["meld"], cp["meld"]), wrong=wrong, pred=pred[:nf])


def summarize(per: dict) -> dict:
    ev = {k: v for k, v in per.items() if v["eval"]}
    f = lambda key, n: f"{sum(v[key] for v in ev.values())}/{sum(v[n] for v in ev.values())}"
    conf = {r: Counter() for r in ROLES}
    return dict(n_eval=len(ev), seat=f"{sum(v['seat_ok'] for v in ev.values())}/{len(ev)}", fair=f("ok_fair", "n_fair"), all=f("ok", "n"), winner=f("ok_win", "n_win"),
                seat_bad=sorted(k for k, v in ev.items() if not v["seat_ok"]))


def field_tokens() -> list[dict]:
    boxes = json.loads((rf.OUT / "boxes.json").read_text(encoding="utf-8"))
    labels = json.loads((rf.OUT / "labels.json").read_text(encoding="utf-8"))
    rects = rf.field_rects()
    out = []
    for name, rec in boxes.items():
        x, y = rf.tokens(rec, labels[name], True, "rot", rects.get(name))
        out.append(dict(name=name, x=x, items=labels[name]["items"]))
    return out


def score_field(fs: list[dict], pfun) -> dict:
    conf = {r: Counter() for r in ROLES}
    per = {}
    for s in fs:
        p = pfun(s["x"])
        pred = [ROLES[int(i)] for i in p.argmax(1)]
        ok = n = 0
        for i, it in enumerate(s["items"]):
            if it["role"] in ROLES:
                conf[it["role"]][pred[i]] += 1
                n += 1
                ok += pred[i] == it["role"]
        per[s["name"]] = f"{ok}/{n}"
    tot = {r: f"{conf[r][r]}/{sum(conf[r].values())}" for r in ROLES}
    return dict(total=f"{sum(conf[r][r] for r in ROLES)}/{sum(sum(c.values()) for c in conf.values())}", roles=tot, per=per,
                confusion={r: dict(c) for r, c in conf.items()})


def base() -> None:
    scenes = load()
    fold_names = rs.folds(sorted(json.loads((rs.OUT / "labels.json").read_text(encoding="utf-8"))))
    old_fold = {n: {"오전": "am", "오후A": "pmA", "오후B": "pmB"}[f] for f, ns in fold_names.items() for n in ns}
    full = Onnx(MODELS / "tile-roles-rot.onnx")
    folds = {k: Onnx(MODELS / f"tile-roles-rot_fold_{k}.onnx") for k in ("am", "pmA", "pmB")}
    per = {}
    for s in scenes:
        m = folds[old_fold[s["name"]]] if s["name"] in old_fold else (full if s["name"].startswith("20261107") else None)
        if m is None:  # 10-31 인데 운영 25장에 없던 사진(FIX1031): 시각으로 fold 를 정한다
            m = folds["am" if s["name"][9:11] < "14" else ("pmA" if s["name"] < "20261031_171500" else "pmB")]
        per[s["name"]] = dict(score_scene(s, m(s["x"])), eval=is_eval(s), fold=s["fold"], staged=s["staged"], kind=s["kind"])
    res = dict(cfg="base", cv=summarize(per), field=score_field(field_tokens(), full), per=per)
    (V2 / f"cv_base{'_shift' if SHIFT_ON else ''}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("운영", res["cv"], "\n테스트 15장", res["field"]["total"], res["field"]["roles"])


def cv(cfg: str, pre_file: str, k: int, epochs: int, synth: int = 0, seeds: int = 3, tag_extra: str = "", seed_off: int = 0) -> None:
    """synth > 0 이면 사전학습 없이 새로: fold 마다 그 학습 사진만으로 합성 배치(synth_set) synth 장면을 만들어 lr 1e-3 으로 epochs 만큼."""
    torch.set_num_threads(8)
    scenes = load()
    pool = scenes if cfg == "staged" else [s for s in scenes if not s["staged"]]
    pre = rs.load_nets(rs.OUT / pre_file) if not synth else [None] * seeds
    tag = cfg + (f"_syn{synth}" if synth else "") + tag_extra

    def fit(tr):
        if synth:
            return [rs.train(synth_set(tr, synth, seed), epochs, seed, None, 1e-3) for seed in range(seeds)]
        return [rs.train(train_set(tr, k, seed + seed_off), epochs, seed + seed_off, pre[seed], 3e-4) for seed in range(len(pre))]  # seed_off: 잡음 측정(표 1-144)
    t0 = time.time()
    per = {}
    for fold in FOLDS:
        tr = [s for s in pool if s["fold"] != fold]
        te = [s for s in scenes if s["fold"] == fold]
        nets = fit(tr)
        torch.save([n.state_dict() for n in nets], V2 / f"role_v2_{tag}_fold_{fold}.pt")
        for s in te:
            per[s["name"]] = dict(score_scene(s, probs_torch(nets, s["x"])), eval=is_eval(s), fold=fold, staged=s["staged"], kind=s["kind"])
        print(fold, "학습", len(tr), "시험", len(te), f"{round(time.time() - t0)}초", flush=True)
    nets = fit(pool)
    torch.save([n.state_dict() for n in nets], V2 / f"role_v2_{tag}_all.pt")
    res = dict(cfg=tag, synth=synth, pre=None if synth else pre_file, aug=k, epochs=epochs, n_train=len(pool), cv=summarize(per), field=score_field(field_tokens(), lambda x: probs_torch(nets, x)), per=per)
    (V2 / f"cv_{tag}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(tag, res["cv"], "\n테스트 15장", res["field"]["total"], res["field"]["roles"], f"{round(time.time() - t0)}초")


def sample(n: int = 12) -> None:
    """합성 예시 n 장 그림(색 = 역할, 회색 = 뒷면/other, 빨간 점 = 리치봉 기기 중심). 맨 앞 넷은 원본."""
    from PIL import Image, ImageDraw

    col = {0: "blue", 1: "cyan", 2: "orange", 3: "red", 4: "magenta", 5: "yellow", -1: "gray"}
    pool = [s for s in load() if not s["staged"]]
    rng = np.random.default_rng(7)
    picks = [pool[i] for i in (0, 10, 20, 30)]
    scenes = [dict(name=p["name"], x=p["x"], y=p["y"]) for p in picks] + [synth_variant(picks[i % 4], pool, rng) for i in range(n - 4)]
    S = 360
    sheet = Image.new("RGB", (S * 4, S * ((len(scenes) + 3) // 4)), "white")
    for k, s in enumerate(scenes):
        im = Image.new("RGB", (S, S), (235, 245, 235))
        d = ImageDraw.Draw(im)
        P = lambda u, v: ((u + 0.35) / 1.9 * S, (v + 0.35) / 1.9 * S)
        for r, l in zip(s["x"], s["y"]):
            w, h = r[2] / 10 / 1.9 * S, r[3] / 10 / 1.9 * S
            cx, cy = P(r[0], r[1])
            fill = (120, 120, 120) if r[4] else None
            d.rectangle((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), outline=col[l] if not r[4] else "black", fill=fill, width=2)
        cx, cy = P(s["x"][0, 0] - s["x"][0, 6], s["x"][0, 1] - s["x"][0, 7])
        d.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill="red")
        d.text((4, 4), ("원본 " if k < 4 else "합성 ") + s["name"][-20:], fill="black")
        sheet.paste(im, ((k % 4) * S, (k // 4) * S))
    sheet.save(V2 / "synth_samples.jpg", quality=90)
    print(V2 / "synth_samples.jpg")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["cv", "base"])
    ap.add_argument("cfg", nargs="?", default="staged", choices=["staged", "nostaged"])
    ap.add_argument("--pre", default="pre_synth8k_rot_base2.pt")
    ap.add_argument("--aug", type=int, default=3)
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--synth", type=int, default=0, help="합성 배치 장면 수(사전학습 없이 새로)")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--sample", action="store_true", help="학습 없이 합성 예시 그림만(v2/synth_samples.jpg)")
    a = ap.parse_args()
    if a.sample:
        sample()
    else:
        base() if a.cmd == "base" else cv(a.cfg, a.pre, a.aug, a.epochs, a.synth, a.seeds)
