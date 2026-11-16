"""1단계 학습 재료 연결(2026-11-16, `docs/role_pair_plan_1116.md` 3-1 끝 "1단계를 맡기기 전에 고정" · 5절 1단계).
v3r15d 와 같은 학습(role_v2_train.cv 본체를 그대로 부름)에 11-14 역할 세트 학습 쪽 장면만 더한 묶음을 만든다. role_v2_train.py 는 고치지 않는다.

  ROLE_OTHER_NEG=1 ROLE_DROP_SAFE=1 ROLE_LOOSE_SHIFT=1 ROLE_SYNTH_V3_ROT=15 python -I -X utf8 experiments/tile_classifier/role_pair_train.py pick
  … role_pair_train.py check          # 누출·수·토큰 꼴·관례·변형 사본·연기 시험(1 epoch, 버림)·그림 → data/role/pair/step1_report.md, 실패면 종료 코드 1
  … role_pair_train.py train m1|m2    # 2단계 진입점(1단계에서는 실행하지 않음). t.cv("nostaged", "pre_synth8k_v3r15d.pt", 3, 100, tag_extra="_pairM1|_pairM2")

고르기 규칙(계획서 3-1 그대로, 결과를 보기 전에 코드로 고정):
  출처  r판 = v1114_load.role_scenes("train", "all"), n판 = v1114rec_load.role_scenes("train", "all", parts=("new",)). v1114rec 의 pair·mid 갈래는 안 씀.
  공개 장면 = phase == "end", 판 중 장면 = phase == "play". 판 중은 강(river) 앞면 0장 그림을 먼저 뺀다.
  토큰 기준 자리 = 화료자(winner)가 있으면 그 자리, 없으면 "bottom"(= 로더 기본값 그대로).
  scene_round 안에서 시각순(이름에 든 시각: r판 끝 6자리 HHMMSS, n판 new_<ms>, 같으면 이름순)으로 늘어놓고 n ≤ 3 이면 전부, 아니면 색인 0 · n//2 · n−1.
    공개·판 중 따로. (계획서 "이름(시각)순" — 이름 문자열순은 win_ 사진이 같은 판 프레임 뒤로 가서 시각순과 다른 판이 있다. 시각을 따랐다 — 보고 "계획과 달라진 곳".)
  학습 묶음 = role_v2_train.load()(연출 뺌 33장, 순서 그대로) 뒤에 11-14 장면(M1 = 공개, M2 = 공개 + 판 중). 겹 이름 "v1114_train"(FOLDS 에 없음 → 모든 겹의 학습에만).
  other 앞면은 ROLE_OTHER_NEG=1 이면 −2(load 와 같음, 11-14 라벨에는 other 가 없다).
  사용자 결정(11-16, 학습 전 — 계획서 8절 ⑤): r08·r09·r10 은 같은 화료 탁자를 여러 번 찍은 것이라 공개 장면은 셋을 한 탁자로 묶어 **1장만** 쓴다 —
    울기(meld) 3상자이고 아래 자리가 아닌 곳의 공개 손패가 0인 후보 가운데 시각순 첫 장. 판 중 장면은 그대로.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import role_set as rs, role_synth_v3 as g, role_v2_train as t  # noqa: E401,E402
import v1114_load as vl, v1114rec_load as vr  # noqa: E401,E402

assert t.SHIFT_ON and g.ROT == "15" and g.DROP_SAFE and rs.DROP_SAFE and g.OTHER_NEG and rs.OTHER_NEG and not rs.NONE, \
    "ROLE_OTHER_NEG=1 ROLE_DROP_SAFE=1 ROLE_LOOSE_SHIFT=1 ROLE_SYNTH_V3_ROT=15 로 실행"

PICK = HERE / "role_pair_train_pick.json"
PAIR = HERE / "data" / "role" / "pair"
STEP1 = PAIR / "step1"
REPORT = PAIR / "step1_report.md"
FOLD_ADD = "v1114_train"
assert FOLD_ADD not in t.FOLDS
PRE = "pre_synth8k_v3r15d.pt"
TAGS = {"m1": "_pairM1", "m2": "_pairM2"}
SRC_FOLD = {"v1114": "v1114_train", "v1114rec": "v1114rec_train"}
RULE = [
    "출처: r판 v1114_load.role_scenes('train','all'), n판 v1114rec_load.role_scenes('train','all',parts=('new',)). v1114rec pair·mid 안 씀. dev 안 씀.",
    "공개 = phase=='end', 판 중 = phase=='play'. 판 중은 강(river) 앞면 0장 그림을 먼저 뺀다.",
    "토큰 기준 자리 = winner 있으면 winner, 없으면 bottom(로더 기본값).",
    "scene_round 안 시각순(r판 이름 끝 HHMMSS, n판 new_<ms>, 같으면 이름순), n<=3 전부, 아니면 색인 0, n//2, n-1. 공개·판 중 따로.",
    "묶음 = role_v2_train.load() 연출 뺌 33장(순서 그대로) 뒤에 M1 = 공개, M2 = 공개 + 판 중. 겹 'v1114_train'. other → -2(ROLE_OTHER_NEG).",
    "사용자 결정(11-16, 계획서 8절 ⑤): 공개 장면에서 r08·r09·r10 은 한 탁자로 묶어 1장만 — meld 3상자 · 아래 자리 아닌 곳의 공개 손패 0 인 후보 중 시각순 첫 장. 판 중은 그대로.",
]
SAME_TABLE = {"r08_125630": "r08-r10", "r09_125949": "r08-r10", "r10_130015": "r08-r10"}  # 공개 장면만 한 탁자로 묶음(사용자 11-16)


def other_open_hand(s: dict) -> int:
    """아래 자리가 아닌 곳의 공개 손패 상자 수(주인 other, 또는 주인 기록이 없고 자리가 bottom 이 아님)."""
    return sum(r == "hand" and (o == "other" or (o is None and st != "bottom")) for r, o, st in zip(s["roles"], s["owners"], s["seats"]))


# ------------------------------------------------------------------ 고르기
def time_key(name: str) -> tuple:
    leaf = name.split("/", 1)[1]
    if leaf.startswith("new_"):
        return (int(leaf[4:]), name)
    m = re.search(r"(\d{6})$", leaf)
    assert m, name
    return (int(m.group(1)), name)


def candidates() -> list[dict]:
    """학습 쪽 후보 장면 전부(r판 + n판 new). 출처 칸 src 를 붙인다."""
    out = []
    for s in vl.role_scenes("train", "all"):
        assert s["fold"] == "v1114_train", (s["name"], s["fold"])
        out.append(dict(s, src="v1114", part=None))
    for s in vr.role_scenes("train", "all", parts=("new",)):
        assert s["fold"] == "v1114rec_train" and s["part"] == "new", (s["name"], s["fold"], s["part"])
        out.append(dict(s, src="v1114rec"))
    return out


def pick_from(cands: list[dict]) -> dict:
    """규칙대로 고른다 → {"end": [장면], "play": [장면], "pre_game_dropped": [이름], "cand": {phase: {scene_round: n}}}."""
    res = {"end": [], "play": [], "pre_game_dropped": [], "cand_raw": {}, "cand": {}}
    for ph in ("end", "play"):
        groups: dict = {}
        for s in cands:
            if s["phase"] != ph:
                continue
            res["cand_raw"].setdefault(ph, Counter())[s["scene_round"]] += 1
            if ph == "play" and sum(r == "river" for r in s["roles"]) == 0:
                res["pre_game_dropped"].append(s["name"])
                continue
            sr = SAME_TABLE.get(s["scene_round"], s["scene_round"]) if ph == "end" else s["scene_round"]
            groups.setdefault((s["src"], sr), []).append(s)
        for key in sorted(groups, key=lambda k: (k[0] != "v1114", k[1])):
            lst = sorted(groups[key], key=lambda s: time_key(s["name"]))
            n = len(lst)
            if key[1] in SAME_TABLE.values():  # 한 탁자 묶음: 조건을 채우는 시각순 첫 장 하나
                ok = [i for i, s in enumerate(lst) if s["roles"].count("meld") == 3 and other_open_hand(s) == 0]
                assert ok, key
                idx = ok[:1]
            else:
                idx = list(range(n)) if n <= 3 else [0, n // 2, n - 1]
            res["cand"].setdefault(ph, {})[key[1]] = n
            for i in idx:
                res[ph].append(dict(lst[i], n_cand=n, idx=i))
    return res


def name_order_picks(cands: list[dict]) -> dict:
    """참고: 계획서 글자 그대로 "이름 문자열순" 으로 골랐다면(시각순과 다른 판만 보고에 적으려고)."""
    out = {}
    for ph in ("end", "play"):
        groups: dict = {}
        for s in cands:
            if s["phase"] != ph or (ph == "play" and sum(r == "river" for r in s["roles"]) == 0):
                continue
            if ph == "end" and s["scene_round"] in SAME_TABLE:  # 한 탁자 묶음은 색인 규칙을 안 쓴다
                continue
            groups.setdefault(s["scene_round"], []).append(s["name"])
        for sr, names in groups.items():
            a = sorted(names)
            b = [n for n in sorted(names, key=time_key)]
            n = len(a)
            idx = list(range(n)) if n <= 3 else [0, n // 2, n - 1]
            pa, pb = [a[i] for i in idx], [b[i] for i in idx]
            if pa != pb:
                out[f"{ph}:{sr}"] = {"name_order": pa, "time_order": pb}
    return out


def entry(s: dict) -> dict:
    return dict(name=s["name"], src=s["src"], scene_round=s["scene_round"], phase=s["phase"], kind=s["kind"], winner=s["winner"],
                side=s["side"], n_cand=s["n_cand"], idx=s["idx"], faces=dict(sorted(Counter(s["roles"]).items())),
                n_face=s["n_face"], n_back=len(s["y"]) - s["n_face"])


def pick_payload() -> dict:
    cands = candidates()
    p = pick_from(cands)
    return dict(
        note="계획서 docs/role_pair_plan_1116.md 3-1 의 고정 규칙으로 고른 11-14 학습 쪽 장면. 이 파일과 지금 규칙으로 다시 고른 목록이 다르면 train 이 멈춘다.",
        rule=RULE,
        candidates={ph: {"scenes": sum(p["cand_raw"][ph].values()), "scene_rounds": len(p["cand_raw"][ph])} for ph in ("end", "play")},
        pre_game_dropped=p["pre_game_dropped"],
        after_drop={ph: {"scenes": sum(p["cand"][ph].values()), "scene_rounds": len(p["cand"][ph])} for ph in ("end", "play")},
        picked={ph: len(p[ph]) for ph in ("end", "play")},
        end=[entry(s) for s in p["end"]],
        play=[entry(s) for s in p["play"]],
    )


def cmd_pick() -> int:
    pl = pick_payload()
    if PICK.exists():
        old = json.loads(PICK.read_text(encoding="utf-8"))
        old.pop("made_at", None)
        same = json.dumps(old, ensure_ascii=False, sort_keys=True) == json.dumps(pl, ensure_ascii=False, sort_keys=True)
        STEP1.mkdir(parents=True, exist_ok=True)
        (STEP1 / "pick_rerun.json").write_text(json.dumps(pl, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{PICK.name} 이미 있음 — 덮어쓰지 않음. 다시 고른 결과(made_at 뺌)와 {'같음' if same else '다름'} → step1/pick_rerun.json")
        return 0 if same else 1
    pl = dict(made_at=time.strftime("%Y-%m-%d %H:%M:%S"), **pl)
    PICK.write_text(json.dumps(pl, ensure_ascii=False, indent=1), encoding="utf-8")
    print("씀", PICK, "공개", pl["picked"]["end"], "판 중", pl["picked"]["play"], "만든 시각", pl["made_at"])
    return 0


# ------------------------------------------------------------------ 학습 묶음
def load_pick_checked() -> dict:
    """pick 파일을 읽고 지금 규칙으로 다시 고른 목록과 같은지 확인(다르면 멈춤)."""
    assert PICK.exists(), f"{PICK} 없음 — 먼저 pick"
    old = json.loads(PICK.read_text(encoding="utf-8"))
    now = pick_payload()
    for ph in ("end", "play"):
        a = [(e["name"], e["src"]) for e in old[ph]]
        b = [(e["name"], e["src"]) for e in now[ph]]
        if a != b:
            raise SystemExit(f"pick 파일의 {ph} 목록이 지금 규칙으로 다시 고른 목록과 다름 — 멈춤")
    return old


def to_train_scene(s: dict) -> dict:
    """11-14 장면 → role_v2_train.load 꼴(cv·train_set 이 읽는 칸 + items). 겹은 FOLD_ADD."""
    src_fold = (vl.role_fold if s["src"] == "v1114" else vr.role_fold)(s["name"])
    assert src_fold == SRC_FOLD[s["src"]], (s["name"], src_fold)
    nf = s["n_face"]
    y = list(s["y"])
    if rs.OTHER_NEG:
        y = [-2 if i < nf and s["roles"][i] == "other" else v for i, v in enumerate(y)]
    items = [dict(role=r, owner=o, box=b) for r, o, b in zip(s["roles"], s["owners"], s["boxes"])]
    return dict(name=s["name"], x=np.asarray(s["x"], np.float32), y=y, n_face=nf, items=items, kind=s["src"], staged=False,
                fold=FOLD_ADD, src=s["src"], src_fold=src_fold, phase=s["phase"], scene_round=s["scene_round"], winner=s["winner"],
                side=s["side"], image=s["image"], owners=s["owners"], roles=s["roles"], boxes=s["boxes"])


def added_scenes(which: str, pick: dict | None = None) -> list[dict]:
    """which = "m1"(공개) | "m2"(공개 + 판 중) | "play"(판 중만, 수 세기용). pick 파일 순서 그대로."""
    pick = pick or load_pick_checked()
    by = {(s["name"], s["src"]): s for s in candidates()}
    phases = {"m1": ("end",), "m2": ("end", "play"), "play": ("play",)}[which]
    out = [to_train_scene(by[(e["name"], e["src"])]) for ph in phases for e in pick[ph]]
    for s in out:
        assert s["fold"] not in t.FOLDS and s["src_fold"] not in t.FOLDS
    return out


def wrapped_load(add: list[dict]):
    base_load = t.load

    def load():
        return base_load() + [dict(s) for s in add]  # 기존 41장(연출 포함) 뒤에 — cv 가 nostaged 로 연출 8장을 뺀다
    return base_load, load


def cmd_train(which: str) -> None:
    tag = TAGS[which]
    for p in [t.V2 / f"cv_nostaged{tag}.json", t.V2 / f"role_v2_nostaged{tag}_all.pt", *(t.V2 / f"role_v2_nostaged{tag}_fold_{f}.pt" for f in t.FOLDS)]:
        assert not p.exists(), f"{p} 가 이미 있음 — 덮어쓰지 않음"
    add = added_scenes(which)
    print(which, "11-14 장면", len(add), dict(Counter(s["phase"] for s in add)), flush=True)
    base_load, load = wrapped_load(add)
    torch.set_num_threads(8)
    t0 = time.time()
    print("시작", time.strftime("%Y-%m-%d %H:%M:%S"), flush=True)
    t.load = load
    try:
        t.cv("nostaged", PRE, 3, 100, tag_extra=tag)
    finally:
        t.load = base_load
    print("끝", time.strftime("%Y-%m-%d %H:%M:%S"), f"{round(time.time() - t0)}초", flush=True)


# ------------------------------------------------------------------ check
COLS = ["u", "v", "w×10", "h×10", "back", "lie", "u−su", "v−sv", "1", "sin2θ", "cos2θ"]


def fold_tr(pool: list[dict], fold: str | None) -> list[dict]:
    """cv 의 tr 그대로(fold None = 전체 학습)."""
    return list(pool) if fold is None else [s for s in pool if s["fold"] != fold]


def pct(a: np.ndarray) -> str:
    if len(a) == 0:
        return "—"
    q = np.percentile(a, [0, 5, 50, 95, 100])
    return " / ".join(f"{v:.3g}" for v in q)


def form_check(scenes: list[dict]) -> dict:
    bad = Counter()
    ys = Counter()
    for s in scenes:
        x, y, nf = s["x"], s["y"], s["n_face"]
        bad["shape"] += not (x.ndim == 2 and x.shape[1] == 11)
        bad["dtype"] += x.dtype != np.float32
        bad["len_y"] += len(y) != len(x)
        bad["face_first"] += not (np.all(x[:nf, 4] == 0) and np.all(x[nf:, 4] == 1))
        bad["back_y"] += not all(v == -1 for v in y[nf:])
        bad["nan"] += not np.isfinite(x).all()
        ys.update(y)
    return dict(bad=dict(bad), yset=sorted(ys), ycount=dict(sorted(ys.items())), ok=sum(bad.values()) == 0 and set(ys) <= {-2, -1, 0, 1, 2, 3, 4, 5})


def win_hand_v(scenes: list[dict]) -> list[float]:
    out = []
    for s in scenes:
        for i, it in enumerate(s["items"][: s["n_face"]]):
            if it["role"] == "hand" and it.get("owner") == "winner":
                out.append(float(s["x"][i, 1]))
    return out


def role_counts(scenes: list[dict]) -> Counter:
    c = Counter()
    for s in scenes:
        nf = s["n_face"]
        for i, v in enumerate(s["y"]):
            c["back" if i >= nf else ({-2: "other(−2)", -1: "other(−1)"}.get(v) or rs.ROLES[v])] += 1
    return c


def same_scene(a: dict, b: dict) -> bool:
    return a["name"] == b["name"] and a["n_face"] == b["n_face"] and list(a["y"]) == list(b["y"]) and a["x"].shape == b["x"].shape and np.array_equal(a["x"], b["x"])


def draw_sheet(panels: list[tuple[str, dict]], out: Path) -> None:
    """role_v2_train.sample 과 같은 방식(색 = 역할, 뒷면 회색 채움, 빨간 점 = 리치봉 기기 중심). −2(other)도 회색 테두리."""
    from PIL import Image, ImageDraw
    col = {0: "blue", 1: "cyan", 2: "orange", 3: "red", 4: "magenta", 5: "yellow", -1: "gray", -2: "gray"}
    S = 360
    sheet = Image.new("RGB", (S * 4, S * ((len(panels) + 3) // 4)), "white")
    for k, (label, s) in enumerate(panels):
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
        d.text((4, 4), label, fill="black")
        d.text((4, 16), s["name"][-34:], fill="black")
        sheet.paste(im, ((k % 4) * S, (k // 4) * S))
    sheet.save(out, quality=90)


def dup_clusters(scenes: list[dict], thr: float = 0.95, eps: float = 0.01) -> list[list[int]]:
    """거의 같은 탁자 묶음: 두 장면의 앞면 상자(10장 이상) 중심이 서로 thr 이상 eps(펠트 비) 안에서 짝이 맞으면 같은 묶음(합집합)."""
    def frac(a, b):
        fa, fb = a["x"][: a["n_face"], :2], b["x"][: b["n_face"], :2]
        if len(fa) < 10 or len(fb) < 10:
            return 0.0
        return float((np.sqrt(((fa[:, None] - fb[None]) ** 2).sum(-1)).min(1) < eps).mean())
    par = list(range(len(scenes)))

    def root(i):
        while par[i] != i:
            i = par[i]
        return i
    for i in range(len(scenes)):
        for j in range(i + 1, len(scenes)):
            if min(frac(scenes[i], scenes[j]), frac(scenes[j], scenes[i])) >= thr:
                par[root(j)] = root(i)
    cl: dict = {}
    for i in range(len(scenes)):
        cl.setdefault(root(i), []).append(i)
    return [v for v in cl.values() if len(v) > 1]


def make_sheet(base: list[dict], m1_add: list[dict], play_add: list[dict]) -> tuple[list, list]:
    """tokens_sheet.jpg: 기존 4(색인 0·10·20·30) + 공개 8(n01·n02 먼저, 그다음 pair 있는 판마다 첫 장면) + 판 중 4(고른 순서에서 고르게). 글자는 ASCII(PIL 기본 글꼴)."""
    panels = [(f"base #{i} ({base[i]['kind']})", base[i]) for i in (0, 10, 20, 30)]
    must = [s for s in m1_add if s["scene_round"].split("_")[0] in ("n01", "n02")]
    pair_first = []
    seen = set(s["scene_round"] for s in must)
    for s in m1_add:
        if "pair" in s["roles"] and s["scene_round"] not in seen:
            pair_first.append(s)
            seen.add(s["scene_round"])
    end8 = (must + pair_first)[:8]
    if len(end8) < 8:
        end8 += [s for s in m1_add if s not in end8][: 8 - len(end8)]
    panels += [(f"1114 end {s['src']} side={s['side']}", s) for s in end8]
    plays = play_add[:: max(1, len(play_add) // 4)][:4]
    panels += [(f"1114 play {s['src']} side={s['side']}", s) for s in plays]
    draw_sheet(panels, STEP1 / "tokens_sheet.jpg")
    return end8, plays


def draw_pair_photo(s: dict, out: Path) -> list:
    """원본 사진 위 앞면 상자(색 = 역할, 가는 선)와 pair 상자(굵은 자홍 + 번호), 오른쪽에 pair 둘레 확대."""
    from PIL import Image, ImageDraw
    im = Image.open(s["image"]).convert("RGB")
    d = ImageDraw.Draw(im)
    pb = []
    for i, (r, b) in enumerate(zip(s["roles"], s["boxes"])):
        x, y, w, h = b
        if r == "pair":
            pb.append((i, b))
        else:
            d.rectangle((x, y, x + w, y + h), outline=rs.COLORS.get(r, "white"), width=1)
    for i, (x, y, w, h) in pb:
        d.rectangle((x - 2, y - 2, x + w + 2, y + h + 2), outline="magenta", width=4)
        d.text((x, y - 12), str(i), fill="magenta")
    xs = [b[0] for _, b in pb] + [b[0] + b[2] for _, b in pb]
    ys = [b[1] for _, b in pb] + [b[1] + b[3] for _, b in pb]
    m = 120
    crop = im.crop((max(0, min(xs) - m), max(0, min(ys) - m), min(im.width, max(xs) + m), min(im.height, max(ys) + m)))
    z = 3 if max(crop.size) < 400 else 2
    crop = crop.resize((crop.width * z, crop.height * z))
    full = im.resize((im.width * 700 // max(im.size), im.height * 700 // max(im.size)))
    H = max(full.height, crop.height)
    canvas = Image.new("RGB", (full.width + crop.width + 10, H), "white")
    canvas.paste(full, (0, 0))
    canvas.paste(crop, (full.width + 10, 0))
    ImageDraw.Draw(canvas).text((4, full.height - 14 if full.height > 14 else 0), f"{s['name']} winner={s['winner']} pair={len(pb)}", fill="red")
    canvas.save(out, quality=90)
    return [(i, list(b)) for i, b in pb]


def cmd_check() -> int:
    STEP1.mkdir(parents=True, exist_ok=True)
    fails = []
    L = []  # 보고 줄
    pr = lambda *a: (print(*a, flush=True), L.append(" ".join(str(x) for x in a)))
    t_start = time.strftime("%Y-%m-%d %H:%M:%S")
    pick = load_pick_checked()
    base_all = t.load()
    base = [s for s in base_all if not s["staged"]]
    m1_add = added_scenes("m1", pick)
    play_add = added_scenes("play", pick)
    m2_add = m1_add + play_add
    pools = {"base": base, "M1": base + m1_add, "M2": base + m2_add}
    # cv 와 같은 길로 만든 pool 이 위와 같은지(감싼 load → nostaged 거르기)
    for nm, add in (("M1", m1_add), ("M2", m2_add)):
        bl, ld = wrapped_load(add)
        pool_cv = [s for s in ld() if not s["staged"]]
        assert [s["name"] for s in pool_cv] == [s["name"] for s in pools[nm]], nm

    pr(f"# 1단계 보고 — 학습 재료 연결(학습 없음, 연기 시험 1 epoch 만), {t_start}")
    pr("")
    pr(f"계획서 `docs/role_pair_plan_1116.md` 3-1·5절 1단계. 스크립트 `experiments/tile_classifier/role_pair_train.py`, 고른 목록 `role_pair_train_pick.json`(만든 시각 {pick['made_at']}).")
    pr("")

    # ---- 고른 수
    pr("## 1. 고른 수")
    pr("")
    pr("| | 후보 장면(판) | 강 0장 뺀 뒤 | 고름 |")
    pr("| --- | --- | --- | --- |")
    for ph, nm in (("end", "공개"), ("play", "판 중")):
        c, a = pick["candidates"][ph], pick["after_drop"][ph]
        pr(f"| {nm} | {c['scenes']} ({c['scene_rounds']}) | {a['scenes']} ({a['scene_rounds']}) | {pick['picked'][ph]} |")
    for ph, nm in (("end", "공개"), ("play", "판 중")):
        by_src = Counter(e["src"] for e in pick[ph])
        pr(f"- {nm} 고른 출처: {dict(by_src)}")
    pr(f"- 판 중에서 강 0장으로 뺀 그림 {len(pick['pre_game_dropped'])}장.")
    nod = name_order_picks(candidates())
    pr(f"- 이름 문자열순으로 골랐다면 달라지는 판: {len(nod)} — " + ", ".join(f"{k}: 이름순 {[n.split('/')[1] for n in v['name_order']]} / 시각순 {[n.split('/')[1] for n in v['time_order']]}" for k, v in nod.items()))
    pr("")
    pr("판별 고른 공개 장면(후보 수 → 고른 색인, 토큰 기준 자리, 앞면 역할 수):")
    pr("")
    pr("| scene_round | 출처 | 이름 | 화료자 | 자리 | 후보 | 색인 | 앞면 역할 |")
    pr("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for e in pick["end"]:
        pr(f"| {e['scene_round']} | {e['src']} | {e['name']} | {e['winner']} | {e['side']} | {e['n_cand']} | {e['idx']} | {e['faces']} |")
    pr("")
    play_nc = {}
    for e in pick["play"]:
        play_nc.setdefault(e["scene_round"], [e["n_cand"], 0])[1] += 1
    pr("판 중(scene_round 후보 → 고름): " + ", ".join(f"{sr} {a}→{b}" for sr, (a, b) in play_nc.items()))
    pr("")

    # ---- 누출
    pr("## 2. 누출")
    pr("")
    dev_names = {s["name"] for s in vl.role_scenes("dev", "all")} | {s["name"] for s in vr.role_scenes("dev", "all")}
    dev_sr = {s["scene_round"] for s in vl.role_scenes("dev", "all")} | {s["scene_round"] for s in vr.role_scenes("dev", "all")}
    rec_part = {x["id"]: x["part"] for sp in vr.SPLITS for x in vr._json(vr.R / "role" / f"labels_{sp}.json")["images"]}
    pr("| 묶음 | 겹 | 학습 장면 | ① dev 이름 | ① dev scene_round | ② 시험 겹 사진 | ③ 11-14 인데 겹이 시험 겹 이름 | ④ rec pair·mid | ④ 같은 이름 두 번 | ④ 같은 토큰 두 번 |")
    pr("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    leak_tot = Counter()
    for nm in ("M1", "M2"):
        for fold in (*t.FOLDS, None):
            tr = fold_tr(pools[nm], fold)
            add = [s for s in tr if s["fold"] == FOLD_ADD]
            c1a = sum(s["name"] in dev_names for s in tr)
            c1b = sum(s.get("scene_round") in dev_sr for s in add)
            c2 = sum(1 for s in tr if s["name"].startswith("2026") and fold is not None and t.fold_of(s["name"]) == fold)
            c3 = sum(s["fold"] in t.FOLDS or s["src_fold"] in t.FOLDS for s in add)
            c4a = sum(1 for s in add if s["src"] == "v1114rec" and rec_part.get(s["name"]) != "new")
            names = [s["name"] for s in tr]
            c4b = len(names) - len(set(names))
            hs = [hashlib.sha1(s["x"].tobytes()).hexdigest() for s in tr]
            c4c = len(hs) - len(set(hs))
            for k, v in (("dev", c1a + c1b), ("test", c2), ("fold", c3), ("rec", c4a), ("dup", c4b + c4c)):
                leak_tot[k] += v
            pr(f"| {nm} | {fold or '전체'} | {len(tr)} | {c1a} | {c1b} | {c2} | {c3} | {c4a} | {c4b} | {c4c} |")
    # 이름 공간 겹침·출처 겹침(참고)
    v_names = {s["name"] for s in vl.role_scenes("train", "all")}
    rec_new_names = {s["name"] for s in vr.role_scenes("train", "all", parts=("new",))}
    pr("")
    pr(f"- v1114 학습 이름 ∩ v1114rec new 학습 이름: {len(v_names & rec_new_names)}. v1114rec new scene_round ∩ v1114 scene_round: "
       f"{len({s['scene_round'] for s in vr.role_scenes('train', 'all', parts=('new',))} & {s['scene_round'] for s in vl.role_scenes('train', 'all')})}.")
    sw = vr.split_with_v1114()
    pr(f"- 두 세트를 합친 scene_round 가 학습·개발에 함께 걸린 수(vr.split_with_v1114): {sw['scene_round_shared_count']}, 같은 그림 id 가 두 split: {len(sw['image_ids_with_two_splits'])}.")
    trap = Counter(t.fold_of(s["name"]) for s in m2_add)
    pr(f"- 함정 확인(쓰지 않음): 고른 11-14 {len(m2_add)}장을 role_v2_train.fold_of 에 넣으면 {dict(trap)} — role_fold 로는 전부 {dict(Counter(s['src_fold'] for s in m2_add))} → 묶음 겹 '{FOLD_ADD}'.")
    pr(f"- 시험 겹(te = fold == 시험 겹)에 들어간 11-14 장면: {sum(s['fold'] == f for s in m2_add for f in t.FOLDS)}. 각 겹 학습에 든 10-31·11-07 사진 수(기준과 같아야): "
       + ", ".join(f"{f} {sum(s['name'].startswith('2026') for s in fold_tr(pools['M2'], f))}/{len(fold_tr(base, f))}" for f in t.FOLDS))
    if sum(leak_tot.values()):
        fails.append(f"누출 {dict(leak_tot)}")
    pr(f"- 누출 합계: {dict(leak_tot)} → {'0 (통과)' if not sum(leak_tot.values()) else '실패'}")
    pr("")

    # ---- 수
    pr("## 3. 수")
    pr("")
    pr("겹마다 학습 장면 수(cv 의 tr 와 같게 만든 것):")
    pr("")
    pr("| 겹 | 기준 | M1 | M2 |")
    pr("| --- | --- | --- | --- |")
    for fold in (*t.FOLDS, None):
        pr(f"| {fold or '전체'} | {len(fold_tr(base, fold))} | {len(fold_tr(pools['M1'], fold))} | {len(fold_tr(pools['M2'], fold))} |")
    pr("")
    rc = {"기존 33장": role_counts(base), "M1 추가분(공개)": role_counts(m1_add), "M2 추가분(판 중)": role_counts(play_add)}
    keys = ["hand", "meld", "river", "wall", "pair", "loose", "other(−2)", "other(−1)", "back"]
    pr("| 역할 | " + " | ".join(rc) + " |")
    pr("| --- | " + " | ".join("---" for _ in rc) + " |")
    for k in keys:
        pr(f"| {k} | " + " | ".join(str(c.get(k, 0)) for c in rc.values()) + " |")
    pr(f"| 장면 | {len(base)} | {len(m1_add)} | {len(play_add)} |")
    pr("")
    # pair 판
    pr("pair 상자가 있는 판(학습 쪽 후보 전부 / 고른 장면):")
    pr("")
    pr("| scene_round | 출처 | 후보 공개 장면 수 · pair 상자 합 | 장면별 pair 수(후보) | 고른 공개 장면의 pair 상자 합 | 판 중 고른 장면 pair |")
    pr("| --- | --- | --- | --- | --- | --- |")
    cands = candidates()
    pair_sr = sorted({s["scene_round"] for s in cands if "pair" in s["roles"]})
    for sr in pair_sr:
        cs = [s for s in cands if s["scene_round"] == sr and s["phase"] == "end"]
        cp = [s for s in cands if s["scene_round"] == sr and s["phase"] == "play" and "pair" in s["roles"]]
        pk = [s for s in m1_add if s["scene_round"] == sr]
        pp = [s for s in play_add if s["scene_round"] == sr]
        pr(f"| {sr} | {cs[0]['src'] if cs else '-'} | {len(cs)} · {sum(r == 'pair' for s in cs for r in s['roles'])} | {[sum(r == 'pair' for r in s['roles']) for s in cs]} "
           f"| {sum(r == 'pair' for s in pk for r in s['roles'])} ({len(pk)}장) | {sum(r == 'pair' for s in pp for r in s['roles'])} |" + (f" (판 중 후보에 pair {len(cp)}장)" if cp else ""))
    pr("")
    pr(f"- pair 있는 판 {len(pair_sr)}개: {', '.join(pair_sr)}. 계획서 3-1 의 9판(r01·r12·r14·r17·r18·r20·r22·n06·n08)에 없는 것: "
       f"{sorted(set(sr.split('_')[0] for sr in pair_sr) - {'r01', 'r12', 'r14', 'r17', 'r18', 'r20', 'r22', 'n06', 'n08'})}.")
    pr("")

    dc = dup_clusters(m2_add)
    pr("거의 같은 탁자(앞면 상자 95% 이상이 펠트 1% 안에서 겹침) 묶음 — 참고, 규칙은 안 바꿈:")
    pr("")
    for v in dc:
        pr(f"- {len(v)}장: " + ", ".join(f"{m2_add[i]['phase']}:{m2_add[i]['name']}" for i in v) + (f" (scene_round {len({m2_add[i]['scene_round'] for i in v})}개에 걸침)" if len({m2_add[i]['scene_round'] for i in v}) > 1 else ""))
    pr(f"- M2 추가분 {len(m2_add)}장 중 서로 다른 탁자 수(이 기준): {len(m2_add) - sum(len(v) - 1 for v in dc)}. "
       f"M1 추가분 {len(m1_add)}장 중: {len(m1_add) - sum(len([i for i in v if i < len(m1_add)]) - 1 for v in dc if any(i < len(m1_add) for i in v))}.")
    pr("")

    # ---- 토큰 꼴
    pr("## 4. 토큰 꼴")
    pr("")
    fc = {"기존 33장": form_check(base), "M1 추가분": form_check(m1_add), "M2 추가분(판 중)": form_check(play_add)}
    pr("| 묶음 | 어긋난 장면(shape·dtype·len y·앞면 먼저·뒷면 y −1·NaN) | y 값 집합(수) | 통과 |")
    pr("| --- | --- | --- | --- |")
    for k, v in fc.items():
        pr(f"| {k} | {v['bad']} | {v['ycount']} | {'예' if v['ok'] else '아니오'} |")
        if not v["ok"]:
            fails.append(f"토큰 꼴 {k}")
    pr("")
    groups = {"기존 33장": base, "M1 추가분": m1_add, "M2 추가분": play_add}
    for face in (True, False):
        pr(f"칸별 최소 / 5% / 중앙 / 95% / 최대 — {'앞면' if face else '뒷면'}:")
        pr("")
        pr("| 칸 | " + " | ".join(groups) + " |")
        pr("| --- | " + " | ".join("---" for _ in groups) + " |")
        arrs = {k: np.concatenate([s["x"][: s["n_face"]] if face else s["x"][s["n_face"]:] for s in v]) for k, v in groups.items()}
        for c in range(11):
            pr(f"| {c} {COLS[c]} | " + " | ".join(pct(a[:, c]) for a in arrs.values()) + " |")
        pr("")
    wv = {k: win_hand_v(v) for k, v in groups.items()}
    pr("화료자 손패(hand, owner winner) 상자의 v: " + ", ".join(f"{k} 중앙 {np.median(a):.3f} (n={len(a)}, 최소 {min(a):.3f})" for k, a in wv.items() if a))
    # 패 크기(앞면 손패 w·h 중앙) · 기기 중심
    for k, v in groups.items():
        hw = np.concatenate([s["x"][[i for i in range(s["n_face"]) if s["y"][i] == 0]][:, 2:4] for s in v if any(s["y"][i] == 0 for i in range(s["n_face"]))]) if any(0 in s["y"] for s in v) else np.zeros((0, 2))
        rw = np.concatenate([s["x"][[i for i in range(s["n_face"]) if s["y"][i] == 2]][:, 2:4] for s in v if any(s["y"][i] == 2 for i in range(s["n_face"]))])
        suv = np.array([[s["x"][0, 0] - s["x"][0, 6], s["x"][0, 1] - s["x"][0, 7]] for s in v])
        pr(f"- {k}: 손패 w·h×10 중앙 {np.median(hw[:, 0]) if len(hw) else float('nan'):.3f}·{np.median(hw[:, 1]) if len(hw) else float('nan'):.3f}, "
           f"강 w·h×10 중앙 {np.median(rw[:, 0]):.3f}·{np.median(rw[:, 1]):.3f}, 기기 중심(su,sv) 중앙 {np.median(suv[:, 0]):.3f},{np.median(suv[:, 1]):.3f} "
           f"범위 u {suv[:, 0].min():.3f}~{suv[:, 0].max():.3f} v {suv[:, 1].min():.3f}~{suv[:, 1].max():.3f}")
    # 강 패: 선 패(lie 0)·눕힌 패(lie 1) 따로 — 중앙값이 둘의 섞임 비율에 끌리는지
    for k, v in groups.items():
        rv = np.concatenate([s["x"][[i for i in range(s["n_face"]) if s["y"][i] == 2]] for s in v])
        parts = []
        for lie in (0, 1):
            a = rv[rv[:, 5] == lie]
            parts.append(f"lie {lie}: {len(a)}장 w·h×10 중앙 {np.median(a[:, 2]):.3f}·{np.median(a[:, 3]):.3f}" if len(a) else f"lie {lie}: 0장")
        pr(f"- {k} 강 패 " + " / ".join(parts) + f", 눕힘 비율 {rv[:, 5].mean():.2f}")
    # 남의 손패
    oh = Counter((it["role"], it.get("owner"), s["y"][i]) for s in base for i, it in enumerate(s["items"][: s["n_face"]]) if it["role"] in ("hand", "loose", "pair"))
    oh2 = Counter((it["role"], it.get("owner"), s["y"][i]) for s in m2_add for i, it in enumerate(s["items"][: s["n_face"]]) if it["role"] in ("hand", "loose", "pair"))
    pr(f"- (역할, 주인, y) 손패·떼어 둔 패·짝: 기존 {dict(oh)} / 11-14 고른 것 {dict(oh2)}")
    pr("")

    # ---- 관례 확인
    pr("## 5. 관례 확인(학습 아님, 판정에 안 씀)")
    pr("")
    wpath = t.V2 / "role_v2_nostaged_v3r15d_rerun1116_all.pt"
    nets = rs.load_nets(wpath)
    pr(f"가중치 `{wpath.relative_to(HERE)}`(11-14 안 배움), `t.probs_torch` 씨드 3 평균. 고른 11-14 장면의 라벨 앞면(역할 있는 것)마다 argmax:")
    pr("")
    pr("| 묶음 | " + " | ".join(rs.ROLES) + " | 화료자 손패 | 전체 |")
    pr("| --- | " + " | ".join("---" for _ in rs.ROLES) + " | --- | --- |")
    conv = {}
    for k, v in (("공개(M1 추가분)", m1_add), ("판 중(M2 추가분)", play_add)):
        ok, n = Counter(), Counter()
        conf, hb = Counter(), Counter()
        for s in v:
            p = t.probs_torch(nets, s["x"]).argmax(1)
            for i in range(s["n_face"]):
                yv = s["y"][i]
                if yv < 0:
                    continue
                r = rs.ROLES[yv]
                n[r] += 1
                ok[r] += int(p[i]) == yv
                conf[(r, rs.ROLES[int(p[i])])] += 1
                if r == "hand" and s["owners"][i] == "winner":
                    n["win"] += 1
                    ok["win"] += int(p[i]) == yv
                if r == "hand":
                    hb[(s["owners"][i] or "없음", rs.ROLES[int(p[i])])] += 1
        conv[k] = dict(ok=dict(ok), n=dict(n), wrong={f"{a}→{b}": c for (a, b), c in conf.items() if a != b},
                       hand_by_owner={f"주인 {a} → {b}": c for (a, b), c in sorted(hb.items())})
        tot_ok = sum(ok[r] for r in rs.ROLES)
        tot_n = sum(n[r] for r in rs.ROLES)
        pr(f"| {k} | " + " | ".join(f"{ok[r]}/{n[r]}" for r in rs.ROLES) + f" | {ok['win']}/{n['win']} | {tot_ok}/{tot_n} |")
    for k, v in conv.items():
        pr(f"- {k} 틀림: {v['wrong']}")
        pr(f"- {k} 손패 라벨의 주인별 모델 답: {v['hand_by_owner']}")
    pr("- 참고: 11-14 개발 기준선 화료자 손패 169/169, 전체 1,862/1,942(metrics 표 6).")
    pr("")

    # ---- 변형 사본
    pr("## 6. 변형 사본 동일성(t.train_set(겹 학습 묶음, 3, seed))")
    pr("")
    pr("| 겹 | 씨드 | 기준 원본 n | 원본 같음 | 기존 장면 변형 사본 같음(M1) | 같음(M2) |")
    pr("| --- | --- | --- | --- | --- | --- |")
    aug_bad = 0
    for fold in (*t.FOLDS, None):
        for seed in (0, 1, 2):
            trb = fold_tr(base, fold)
            nb = len(trb)
            tsb = t.train_set(trb, 3, seed)
            res = []
            for nm in ("M1", "M2"):
                trm = fold_tr(pools[nm], fold)
                na = len(trm) - nb
                assert [s["name"] for s in trm[:nb]] == [s["name"] for s in trb]
                tsm = t.train_set(trm, 3, seed)
                o = sum(same_scene(a, b) for a, b in zip(tsb[:nb], tsm[:nb]))
                a_ = sum(same_scene(a, b) for a, b in zip(tsb[nb:], tsm[nb + na: nb + na + 3 * nb]))
                assert len(tsm) == (nb + na) * 4
                res.append((o, a_))
                aug_bad += (nb - o) + (3 * nb - a_)
            pr(f"| {fold or '전체'} | {seed} | {nb} | {res[0][0]}/{nb} · {res[1][0]}/{nb} | {res[0][1]}/{3 * nb} | {res[1][1]}/{3 * nb} |")
    if aug_bad:
        fails.append(f"변형 사본 다름 {aug_bad}")
    pr(f"- 다른 것 합계 {aug_bad}. (rs.train 의 섞기 순서·종류 가중치는 장면 수가 달라 기준과 다르다 — 바뀌는 재료 하나의 결과.)")
    pr("")

    # ---- 연기 시험
    pr("## 7. 연기 시험(1031am 겹 M1, 씨드 0, 1 epoch — 가중치 저장·채점 안 함)")
    pr("")
    torch.set_num_threads(8)
    pre = rs.load_nets(rs.OUT / PRE)
    trm = fold_tr(pools["M1"], "1031am")
    ts = t.train_set(trm, 3, 0)
    t0 = time.time()
    net = rs.train(ts, 1, 0, pre[0], 3e-4)
    dt = time.time() - t0
    del net
    trb = fold_tr(base, "1031am")
    n_fit = {nm: sum(len(fold_tr(pools[nm], f)) for f in (*t.FOLDS, None)) for nm in ("base", "M1", "M2")}
    est = {nm: dt / len(trm) * n_fit[nm] * 100 * 3 for nm in ("M1", "M2")}
    pr(f"- 시작 {time.strftime('%H:%M:%S', time.localtime(t0))}, 학습 장면 {len(trm)}(원본) → 변형 포함 {len(ts)}, 1 epoch {dt:.1f}초, 끝까지 돎.")
    pr(f"- 어림 1(이 1 epoch 로 비례): 본 학습 = 1 epoch 초 × (5번 학습의 원본 장면 합 / 이 겹 원본 장면) × 100 epoch × 씨드 3 → M1 {est['M1'] / 60:.0f}분, M2 {est['M2'] / 60:.0f}분.")
    pr(f"- 어림 2(0단계 828초를 장면 수로 비례, 장면 크기 차이 무시): 5번 학습 원본 장면 합 기준 {n_fit['base']} / M1 {n_fit['M1']} / M2 {n_fit['M2']} → M1 {828 * n_fit['M1'] / n_fit['base'] / 60:.0f}분, M2 {828 * n_fit['M2'] / n_fit['base'] / 60:.0f}분(+ 채점·field 몇 초).")
    pr("- 11-14 장면은 상자가 많아(뒷면 포함 장면당 중앙 " + f"{int(np.median([len(s['x']) for s in m1_add]))}, 기존 {int(np.median([len(s['x']) for s in base]))}) 배치 패딩이 커져 어림 2 보다 더 걸릴 수 있다.")
    pr("")

    # ---- 그림
    pr("## 8. 그림")
    pr("")
    end8, plays = make_sheet(base, m1_add, play_add)
    pr(f"- `data/role/pair/step1/tokens_sheet.jpg`: 기존 4(색인 0·10·20·30) + 공개 {len(end8)}({', '.join(s['name'] for s in end8)}) + 판 중 {len(plays)}({', '.join(s['name'] for s in plays)}).")
    for s in m1_add:
        if s["scene_round"].split("_")[0] in ("n01", "n02"):
            fn = STEP1 / f"{s['scene_round'].split('_')[0]}_pair_photo.jpg"
            pb = draw_pair_photo(s, fn)
            pr(f"- `{fn.relative_to(HERE)}`: {s['name']} 화료자 {s['winner']}, pair 상자 {len(pb)} (번호·상자 {pb})")
    pr("")
    pr("## 9. 판정")
    pr("")
    pr(f"- 실패 조건: {fails if fails else '없음'}")
    pr(f"- 끝 {time.strftime('%Y-%m-%d %H:%M:%S')}")
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")
    (STEP1 / "check_conv.json").write_text(json.dumps(conv, ensure_ascii=False, indent=1), encoding="utf-8")
    print("보고서", REPORT)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["pick", "check", "train"])
    ap.add_argument("which", nargs="?", choices=["m1", "m2"])
    a = ap.parse_args()
    if a.cmd == "pick":
        sys.exit(cmd_pick())
    if a.cmd == "check":
        sys.exit(cmd_check())
    assert a.which, "train m1|m2"
    cmd_train(a.which)
