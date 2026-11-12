"""역할 + 주인 자리 채점기(2026-11-12, `docs/role_owner_plan_1111.md` 4절 평가·"기준 보완", 5절 2단계). 학습 없음.

장면 표현(사진 기준) = {name, W, H, grid, x0, n_face, boxes, labels, fold, phase, winner}
  x0     = 사진 기준(= side "bottom" 으로 만든) 11칸 토큰(앞면 n_face 개 뒤에 뒷면). 서버 `roles.tokens` 와 같은 칸.
  boxes  = 앞면 상자 픽셀 [x, y, w, h], labels = 앞면마다 {role, seat, score, owner}(owner = E1 의 winner/other, E3 은 None).
예측기 = 장면 → 앞면마다 {role, conf, owner}(owner = bottom|right|top|left|center). 뒤 단계 C·D 도 같은 꼴로 끼운다(`PREDICTORS`).
  A(지금 방식) = 네 side 마다 `turn_tokens(x0, k)` → 역할 모델(씨드 3 확률 평균) → 상자마다 `ondevice._pick_role` 그대로 →
                 주인은 hand 면 그 side, 아니면 `ondevice.overlay` 의 `side_of`(격자 칸, grow 0, 없으면 center).
  사분면 참고선(강 주인 잣대, 계획서 기준 보완) = 기기 중심(sticks 가운데, 없으면 가운데 칸 가운데)에서 상자 중심까지를
                 가운데 칸 반폭·반높이로 나눠 |가로| > |세로| 면 left/right, 아니면 top/bottom.
평가 세트
  E1 화료 상자: data/role/v2/labels_v2_owner.json, 채점 장면 = role_v2_train.is_eval(v3r15d 환경 변수 → 26장). 입력 = 옮기지 않은 원래 x 를
     turn_tokens 로 사진 기준으로 되돌린 것. 모델 = 그 장면 겹을 안 배운 role_v2_nostaged_v3r15d_fold_<겹>.pt.
  E3 판 중 상자: data/role/frames/labels_{test,dev}.json. 토큰 = roles.tokens(side bottom, 11칸). 회전 상자는 검출기를 다시 돌려(det_cache 에는
     축 상자만 있음) IoU 로 맞춤(role_set.match_rects, 0.3). 결과 캐시 data/role/owner/frames_rects.json. 시험 = fold_1107pm, 개발 = fold_of(이름).
     score=false 상자는 입력엔 넣고 채점에서 뺌.
  E4 회전 일치: E1 장면을 90·180·270° 돌린 장면(토큰·상자·격자·W·H·라벨 자리 모두)에 예측기 → 자리를 되돌린 답이 원본 답과 같은 상자 비율.

  python -I -X utf8 experiments/tile_classifier/role_owner_eval.py test      # turn_tokens 단위 테스트만
  python -I -X utf8 experiments/tile_classifier/role_owner_eval.py detect    # 프레임 회전 상자 캐시(검출기 다시 돌림, 한 번)
  python -I -X utf8 experiments/tile_classifier/role_owner_eval.py run       # 점검 + E1·E3·E4 → data/role/owner/eval_A.json
환경 변수(ROLE_OTHER_NEG·ROLE_DROP_SAFE·ROLE_LOOSE_SHIFT=1, ROLE_SYNTH_V3_ROT=15)는 이 스크립트가 v3r15d 와 같게 직접 넣는다.
"""
from __future__ import annotations

import os

# role_v3r15d_run.py 와 같은 환경 변수(이 값으로 role_v2_train.load()·is_eval 이 26장을 고른다). 다른 값으로 돌지 않게 덮어쓴다.
for _k, _v in (("ROLE_OTHER_NEG", "1"), ("ROLE_DROP_SAFE", "1"), ("ROLE_LOOSE_SHIFT", "1"), ("ROLE_SYNTH_V3_ROT", "15"), ("ROLE_EVAL_COMPOSITE", "1")):
    os.environ[_k] = _v
os.environ.pop("ROLE_NONE", None)
os.environ.pop("ROLE_LABELS", None)

import argparse  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from collections import Counter, defaultdict  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import torch  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import role_set as rs  # noqa: E402
import role_v2_train as t  # noqa: E402
import role_owner_draft as rod  # noqa: E402

REC = Path(r"C:\Users\jjh7757\dev\mahjong-recognizer")
sys.path.insert(0, str(REC))
from app import roles  # noqa: E402  (읽기만)


def _load_ondevice():
    """ondevice.py 를 파일로 직접 읽는다(읽기만 — _pick_role 을 그대로 부름). 그 폴더를 sys.path 에 넣으면 기기용 onnxruntime 껍데기(java 다리)가
    진짜 onnxruntime 을 가려서 안 넣는다."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("ondevice", ROOT / "android" / "app" / "src" / "main" / "python" / "ondevice.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ondevice = _load_ondevice()

V2 = HERE / "data" / "role" / "v2"
FR = HERE / "data" / "role" / "frames"
OWN = HERE / "data" / "role" / "owner"
RECTS_CACHE = OWN / "frames_rects.json"
SIDES = roles.SIDES  # ("bottom", "right", "top", "left")
ROLES = rs.ROLES
HML = ("hand", "meld", "loose")
assert ROLES == ["hand", "meld", "river", "wall", "pair", "loose"], ROLES
assert ondevice.HAND_MIN == 0.8
assert t.SHIFT_ON and rs.OTHER_NEG and rs.DROP_SAFE


# ---------------------------------------------------------------- 토큰 회전
def turn_tokens(x: np.ndarray, k: int) -> np.ndarray:
    """토큰을 k×90° 돌린다: side s 기준 토큰 → side SIDES[(s+k)%4] 기준 토큰(사진 기준 x0 이면 = roles.tokens(..., side=SIDES[k])).
    (u, v)[칸 0·1]와 리치봉 위치(u−칸6, v−칸7)에 roles.turn, k 홀수면 칸 2·3 맞바꿈, 칸 5(눕힘 = 폭 > 높이×1.15) 다시 계산,
    칸 6·7 다시 뺌. 칸 4·8·9·10 은 그대로(기울기는 원본 사진 좌표에서 잰 값이라 자리와 무관)."""
    k %= 4
    x = np.asarray(x, np.float64)
    if k == 0:
        return x.astype(np.float32)
    side = SIDES[k]
    u, v = x[:, 0], x[:, 1]
    su, sv = u - x[:, 6], v - x[:, 7]
    u2, v2, swap = roles.turn(u, v, side)
    su2, sv2, _ = roles.turn(su, sv, side)
    out = x.copy()
    out[:, 0], out[:, 1] = u2, v2
    if swap:
        out[:, 2], out[:, 3] = x[:, 3], x[:, 2]
    out[:, 5] = (out[:, 2] > out[:, 3] * 1.15).astype(np.float64)
    out[:, 6], out[:, 7] = u2 - su2, v2 - sv2
    return out.astype(np.float32)


def unit_test(n: int = 300, seed: int = 0) -> dict:
    """무작위 상자·회전 꼭짓점·뒷면·격자(sticks 있음·없음)로 roles.tokens 를 네 side 로 부른 값 = turn_tokens(x_bottom, k)(1e-5),
    네 번 돌리면 원래대로, 아무 side 에서 시작해도 turn_tokens(x_s, k) = x_{s+k}."""
    import cv2

    rng = np.random.default_rng(seed)
    worst = {"vs_tokens": 0.0, "four_turns": 0.0, "from_any_side": 0.0}
    fails = []
    n_rows = 0
    lie_flip = 0
    for it in range(n):
        W, H = int(rng.integers(800, 4200)), int(rng.integers(600, 3200))
        x1, y1 = int(rng.integers(150, 400)), int(rng.integers(120, 350))
        g = {"x1": x1, "x2": int(x1 + rng.integers(300, 550)), "y1": y1, "y2": int(y1 + rng.integers(350, 600))}
        if it % 2 == 0:  # sticks [y0, x0, y1, x1] 1000 분율
            cy, cx = rng.uniform(g["y1"], g["y2"]), rng.uniform(g["x1"], g["x2"])
            g["sticks"] = [cy - 60, cx - 50, cy + 60, cx + 50]
        nb, nbk = int(rng.integers(1, 40)), int(rng.integers(0, 30))

        def rbox():
            w, h = rng.uniform(0.01, 0.05) * W, rng.uniform(0.01, 0.05) * H
            return (float(rng.uniform(-0.05, 1.0) * W), float(rng.uniform(-0.05, 1.0) * H), float(w), float(h))

        def rpts(b):
            if rng.random() < 0.25:
                return None
            rect = ((b[0] + b[2] / 2, b[1] + b[3] / 2), (float(rng.uniform(0.5, 1.5) * b[2]), float(rng.uniform(0.5, 1.5) * b[3])), float(rng.uniform(-90, 90)))
            return cv2.boxPoints(rect)

        boxes = [rbox() for _ in range(nb)]
        pts = [rpts(b) for b in boxes]
        backs = [(b, rpts(b)) for b in (rbox() for _ in range(nbk))]
        xs = [roles.tokens(boxes, W, H, g, s, roles.FEAT_ROT, pts, backs) for s in SIDES]
        n_rows += len(xs[0])
        for k in range(4):
            d = np.abs(turn_tokens(xs[0], k) - xs[k])
            # 눕힘 칸이 문턱(1.15)에 딱 걸려 float32 반올림으로 뒤집힌 줄은 따로 센다
            lie = d[:, 5] > 0.5
            lie_flip += int(lie.sum())
            dd = float(np.delete(d, 5, axis=1).max()) if d.size else 0.0
            dd = max(dd, float(d[~lie, 5].max()) if (~lie).any() else 0.0)
            worst["vs_tokens"] = max(worst["vs_tokens"], dd)
            if dd > 1e-5:
                fails.append(("vs_tokens", it, k, dd))
            for s in range(4):
                d2 = float(np.abs(turn_tokens(xs[s], k) - xs[(s + k) % 4]).max())
                worst["from_any_side"] = max(worst["from_any_side"], d2)
                if d2 > 1e-5:
                    fails.append(("from_any_side", it, s, k, d2))
        y = xs[0]
        for _ in range(4):
            y = turn_tokens(y, 1)
        d3 = float(np.abs(y - xs[0]).max())
        worst["four_turns"] = max(worst["four_turns"], d3)
        if d3 > 1e-5:
            fails.append(("four_turns", it, d3))
    return dict(cases=n, rows=n_rows, worst=worst, lie_flip=lie_flip, fails=fails[:20], n_fail=len(fails), ok=not fails)


# ---------------------------------------------------------------- 예측기 A
def side_of(b, W: int, H: int, grid: dict) -> str:
    """`android/app/src/main/python/ondevice.py` overlay 안의 side_of 를 글자 그대로 옮김(닫힌 변수 W·H·grid 를 인자로)."""
    cx, cy = (b[0] + b[2] / 2) / W * 1000, (b[1] + b[3] / 2) / H * 1000
    for s in roles.SIDES:
        y0, x0, y1, x1 = roles.seat_box(grid, s, grow=0)
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            return s
    return "center"


def quadrant(b, W: int, H: int, grid: dict) -> str:
    """사분면 참고선(계획서 4-2 기준 보완). 조정 없음."""
    cx, cy = (b[0] + b[2] / 2) / W * 1000, (b[1] + b[3] / 2) / H * 1000
    s = grid.get("sticks")
    if s:
        ox, oy = (s[1] + s[3]) / 2, (s[0] + s[2]) / 2
    else:
        ox, oy = (grid["x1"] + grid["x2"]) / 2, (grid["y1"] + grid["y2"]) / 2
    du, dv = (cx - ox) / ((grid["x2"] - grid["x1"]) / 2), (cy - oy) / ((grid["y2"] - grid["y1"]) / 2)
    if abs(du) > abs(dv):
        return "right" if du > 0 else "left"
    return "bottom" if dv > 0 else "top"


class FoldNets:
    """겹 이름 → 씨드 3 가중치(role_v2_nostaged_v3r15d_fold_<겹>.pt). probs = 씨드 확률 평균(role_v2_train.probs_torch)."""

    def __init__(self, tag: str = "nostaged_v3r15d"):
        self.tag, self.nets = tag, {}

    def path(self, fold: str) -> Path:
        return V2 / f"role_v2_{self.tag}_fold_{fold}.pt"

    def probs(self, fold: str, x: np.ndarray) -> np.ndarray:
        if fold not in self.nets:
            self.nets[fold] = rs.load_nets(self.path(fold))
        return t.probs_torch(self.nets[fold], np.asarray(x, np.float32))


class PredictorA:
    """지금 방식(겹쳐 보기 ondevice.overlay 의 역할 단계): 네 side 4회 + _pick_role + side_of. 규칙·문턱 그대로."""

    name = "A"

    def __init__(self, nets: FoldNets):
        self.nets = nets

    def __call__(self, sc: dict) -> list[dict]:
        nf = sc["n_face"]
        by_side = {}
        for k, s in enumerate(SIDES):
            p = self.nets.probs(sc["fold"], turn_tokens(sc["x0"], k))
            # RoleNet.predict 와 같게: 역할 = argmax, 확신 = max 를 소수 셋째 자리로 반올림
            by_side[s] = ([ROLES[int(i)] for i in p.argmax(1)][:nf], [round(float(v), 3) for v in p.max(1)][:nf])
        out = []
        for i in range(nf):
            per = {s: (by_side[s][0][i], float(by_side[s][1][i])) for s in SIDES}
            role, conf, owner = ondevice._pick_role(per)
            out.append({"role": role, "conf": round(float(conf), 4), "owner": owner or side_of(sc["boxes"][i], sc["W"], sc["H"], sc["grid"]),
                        "per_side": {s: [r, c] for s, (r, c) in per.items()}})
        return out


# ---------------------------------------------------------------- 장면 만들기
def e1_scenes(all_scenes: bool = False) -> tuple[list[dict], dict]:
    """E1 채점 장면(is_eval). 입력 = labels_v2_owner.json 의 원래 x(옮기지 않음)를 사진 기준으로 되돌림."""
    own = json.loads((V2 / "labels_v2_owner.json").read_text(encoding="utf-8"))
    base = json.loads((V2 / "labels_v2.json").read_text(encoding="utf-8"))
    G = rod.grids()
    loaded = {s["name"]: s for s in t.load()}
    out, info = [], {"x_same_as_labels_v2": True, "n_all": len(own)}
    for name, s in own.items():
        L = loaded[name]
        if not all_scenes and not t.is_eval(L):
            continue
        if s["x"] != base[name]["x"]:
            info["x_same_as_labels_v2"] = False
        x = np.array(s["x"], np.float32)
        j = SIDES.index(s["side"])
        x0 = turn_tokens(x, (4 - j) % 4)
        W, H = s["size"]
        labels = [{"role": it["role"], "seat": it.get("seat"), "score": True, "owner": it.get("owner")} for it in s["items"]]
        out.append(dict(name=name, W=W, H=H, grid=G[name], x0=x0, x_side=x, n_face=s["n_face"], boxes=[list(it["box"]) for it in s["items"]],
                        backs=[list(b) for b in s["backs"]], labels=labels, fold=t.fold_of(name), phase="win", winner=s["side"], kind=s["kind"],
                        eval=t.is_eval(L)))
    return out, info


def unrotate_check(scenes: list[dict]) -> dict:
    """되돌림 검증: 상자·격자·side 로 roles.tokens 를 직접 불러(축 상자) 칸 0·1·6·7 이 x(그 side 기준)와, side bottom 이 x0 와 같은지."""
    per, bad_rows = {}, []
    worst = 0.0
    for sc in scenes:
        side = sc["winner"]
        backs = [(b, None) for b in sc["backs"]]
        direct = roles.tokens(sc["boxes"], sc["W"], sc["H"], sc["grid"], side, roles.FEAT_ROT, None, backs)
        direct0 = roles.tokens(sc["boxes"], sc["W"], sc["H"], sc["grid"], "bottom", roles.FEAT_ROT, None, backs)
        if direct.shape != sc["x_side"].shape:
            per[sc["name"]] = {"shape": [list(direct.shape), list(sc["x_side"].shape)]}
            continue
        d = np.abs(direct[:, [0, 1, 6, 7]] - sc["x_side"][:, [0, 1, 6, 7]]).max(1)
        d0 = np.abs(direct0[:, [0, 1, 6, 7]] - sc["x0"][:, [0, 1, 6, 7]]).max(1)
        worst = max(worst, float(d.max()))
        rows = [int(i) for i in np.where(d > 1e-3)[0]]
        per[sc["name"]] = {"max_side": round(float(d.max()), 6), "max_bottom": round(float(d0.max()), 6), "rows_over_1e-3": rows}
        for i in rows:
            bad_rows.append({"scene": sc["name"], "row": i, "face": i < sc["n_face"], "diff": round(float(d[i]), 5),
                             "role": sc["labels"][i]["role"] if i < sc["n_face"] else "back"})
    return {"scenes": per, "worst_all_rows": round(worst, 6), "rows_over_1e-3": bad_rows}


def _letter_tiles(W: int, H: int, ov: int = 60):
    return [(0, 0, W // 2 + ov, H // 2 + ov), (W // 2 - ov, 0, W, H // 2 + ov), (0, H // 2 - ov, W // 2 + ov, H), (W // 2 - ov, H // 2 - ov, W, H)]


def detect_rects(names: list[str]) -> dict:
    """role_frames_draft.detect 와 같은 두 갈래(프레임 전체 + 네 조각 2배)로 검출기를 돌려 회전 상자를 모두 남긴다(맞추기 후보)."""
    from PIL import Image
    from app.local_read import LocalReader

    rd = LocalReader(threads=4)
    rd._sessions()
    assert rd._seat is not None, "자리 판독 검출기(seat_model)가 없음"
    out = {"_model": str(rd.seat_model)}
    for nm in names:
        rgb = np.asarray(Image.open(FR / "images" / f"{nm}.jpg").convert("RGB"))
        H, W = rgb.shape[:2]
        f1, b1, _, _ = rd._seat_raw(rgb)
        rec = {"faces": [[list(b), [list(rc[0]), list(rc[1]), rc[2]], "full"] for b, rc in f1],
               "backs": [[list(b), [list(rc[0]), list(rc[1]), rc[2]], "full"] for b, rc in b1]}
        s = 2
        for x0, y0, x1, y1 in _letter_tiles(W, H):
            c = Image.fromarray(rgb[y0:y1, x0:x1]).resize(((x1 - x0) * s, (y1 - y0) * s), Image.LANCZOS)
            f, b, _, _ = rd._seat_raw(np.asarray(c))
            cw, chh = (x1 - x0) * s, (y1 - y0) * s
            for key, res in (("faces", f), ("backs", b)):
                for (bx, by, bw, bh), rc in res:
                    if bx <= 2 or by <= 2 or bx + bw >= cw - 2 or by + bh >= chh - 2:  # 조각 끝에 잘린 것(role_frames_draft 와 같음)
                        continue
                    box = [round(bx / s + x0, 1), round(by / s + y0, 1), round(bw / s, 1), round(bh / s, 1)]
                    rect = [[rc[0][0] / s + x0, rc[0][1] / s + y0], [rc[1][0] / s, rc[1][1] / s], rc[2]]
                    rec[key].append([box, rect, "up"])
        out[nm] = rec
        print("검출", nm, len(rec["faces"]), len(rec["backs"]), flush=True)
    return out


def e3_scenes(split: str, rects_all: dict) -> tuple[list[dict], dict]:
    import cv2

    d = json.loads((FR / f"labels_{split}.json").read_text(encoding="utf-8"))
    cache = json.loads((FR / "det_cache.json").read_text(encoding="utf-8"))
    out = []
    st = Counter()
    ious = []
    for fr in d["frames"]:
        nm = fr["name"]
        W, H = fr["size"]
        rr = rects_all[nm]
        fpool = [(b, tuple(map(tuple, r[:2])) + (r[2],)) for b, r, _ in rr["faces"]]
        bpool = [(b, tuple(map(tuple, r[:2])) + (r[2],)) for b, r, _ in rr["backs"]]
        items = fr["items"]
        boxes = [list(it["box"]) for it in items]
        pts = []
        for it, b in zip(items, boxes):
            if it.get("src") == "added":
                pts.append(None)
                st["face_added"] += 1
                continue
            m = rs.match_rects([b], fpool)[0]
            best = max((rs.iou(c[0], b) for c in fpool), default=0.0)
            if m is None:
                pts.append(None)
                st["face_unmatched"] += 1
            else:
                pts.append(cv2.boxPoints(m))
                st["face_matched"] += 1
                ious.append(best)
        backs = []
        for b in fr["backs"]:
            m = rs.match_rects([b], bpool)[0]
            backs.append((list(b), None if m is None else cv2.boxPoints(m)))
            st["back_matched" if m is not None else "back_unmatched"] += 1
        # 재검출이 det_cache(라벨 상자의 출처)와 같은 상자를 냈는지(같은 검출기면 축 상자가 같다)
        for f in cache[nm]["faces"]:
            st["cache_face"] += 1
            st["cache_face_iou99"] += max((rs.iou(c[0], f["box"]) for c in fpool), default=0.0) >= 0.99
        x0 = roles.tokens(boxes, W, H, fr["grid"], "bottom", roles.FEAT_ROT, pts, backs)
        labels = [{"role": it["role"], "seat": it.get("seat"), "score": bool(it.get("score", True)), "owner": None, "src": it.get("src")} for it in items]
        fold = "1107pm" if split == "test" else t.fold_of(nm)
        out.append(dict(name=nm, W=W, H=H, grid=fr["grid"], x0=x0, n_face=len(items), boxes=boxes, labels=labels, fold=fold, phase=fr["phase"],
                        winner=None, kind="frame"))
    ious = np.array(ious)
    st = dict(st)
    st["match_iou_hist"] = {"≥0.95": int((ious >= 0.95).sum()), "0.8~0.95": int(((ious >= 0.8) & (ious < 0.95)).sum()),
                            "0.5~0.8": int(((ious >= 0.5) & (ious < 0.8)).sum()), "0.3~0.5": int(((ious >= 0.3) & (ious < 0.5)).sum())}
    st["folds"] = dict(Counter(s["fold"] for s in out))
    return out, st


# ---------------------------------------------------------------- 회전 장면(E4)
def _rot_pt(px, py, W, H, k):
    a, b, _ = roles.turn(px / W, py / H, SIDES[k])
    W2, H2 = (H, W) if k % 2 else (W, H)
    return a * W2, b * H2


def rotate_scene(sc: dict, k: int) -> dict:
    """사진을 돌려 SIDES[k] 자리가 아래로 오게 한 장면. 토큰 = turn_tokens(x0, k), 상자·격자·W·H·라벨 자리도 같이."""
    W, H = sc["W"], sc["H"]
    W2, H2 = (H, W) if k % 2 else (W, H)

    def rbox(b):
        ps = [_rot_pt(px, py, W, H, k) for px, py in ((b[0], b[1]), (b[0] + b[2], b[1]), (b[0], b[1] + b[3]), (b[0] + b[2], b[1] + b[3]))]
        xs, ys = [p[0] for p in ps], [p[1] for p in ps]
        return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]

    g = sc["grid"]
    gp = [_rot_pt(g[a], g[b], 1000, 1000, k) for a, b in (("x1", "y1"), ("x2", "y2"))]
    g2 = {"x1": min(p[0] for p in gp), "x2": max(p[0] for p in gp), "y1": min(p[1] for p in gp), "y2": max(p[1] for p in gp)}
    if g.get("sticks"):
        y0, x0, y1, x1 = g["sticks"]
        sp = [_rot_pt(x0, y0, 1000, 1000, k), _rot_pt(x1, y1, 1000, 1000, k)]
        g2["sticks"] = [min(p[1] for p in sp), min(p[0] for p in sp), max(p[1] for p in sp), max(p[0] for p in sp)]
    rs_ = lambda s: None if s is None else SIDES[(SIDES.index(s) - k) % 4]
    labels = [dict(l, seat=rs_(l["seat"])) for l in sc["labels"]]
    return dict(sc, name=f"{sc['name']}@{90 * k}", W=W2, H=H2, grid=g2, x0=turn_tokens(sc["x0"], k), boxes=[rbox(b) for b in sc["boxes"]],
                backs=[rbox(b) for b in sc.get("backs", [])], labels=labels, winner=rs_(sc["winner"]), rot=k)


def rotate_check(scenes: list[dict]) -> dict:
    """돌린 장면의 상자·격자·W·H 로 roles.tokens(bottom, 축 상자)를 직접 부른 칸 0·1·6·7 = 돌린 x0(turn_tokens) 인지, 그리고
    라벨 자리·side_of·사분면이 돌림과 맞물리는지(되돌린 자리가 원본과 같음)."""
    worst = 0.0
    seat_bad = sideof_bad = quad_bad = 0
    for sc in scenes:
        for k in (1, 2, 3):
            r = rotate_scene(sc, k)
            d = roles.tokens(r["boxes"], r["W"], r["H"], r["grid"], "bottom", roles.FEAT_ROT, None, [(b, None) for b in r["backs"]])
            worst = max(worst, float(np.abs(d[:, [0, 1, 6, 7]] - r["x0"][:, [0, 1, 6, 7]]).max()))
            back = lambda s: s if s in (None, "center") else SIDES[(SIDES.index(s) + k) % 4]
            for i in range(sc["n_face"]):
                seat_bad += back(r["labels"][i]["seat"]) != sc["labels"][i]["seat"]
                sideof_bad += back(side_of(r["boxes"][i], r["W"], r["H"], r["grid"])) != side_of(sc["boxes"][i], sc["W"], sc["H"], sc["grid"])
                quad_bad += back(quadrant(r["boxes"][i], r["W"], r["H"], r["grid"])) != quadrant(sc["boxes"][i], sc["W"], sc["H"], sc["grid"])
    return {"tokens_worst_cols_0167": round(worst, 7), "seat_mismatch": seat_bad, "side_of_mismatch": sideof_bad, "quadrant_mismatch": quad_bad}


# ---------------------------------------------------------------- 채점
def score_scene(sc: dict, pred: list[dict]) -> list[dict]:
    recs = []
    for i, (lab, p) in enumerate(zip(sc["labels"], pred)):
        r = {"i": i, "role": lab["role"], "seat": lab["seat"], "owner_kind": lab.get("owner"), "score": lab["score"],
             "pr": p["role"], "pc": p["conf"], "po": p["owner"], "quad": quadrant(sc["boxes"][i], sc["W"], sc["H"], sc["grid"])}
        if lab["score"] and lab["role"] in ROLES:
            r["role_ok"] = p["role"] == lab["role"]
            r["ro_ok"] = r["role_ok"] and (lab["role"] not in HML or p["owner"] == lab["seat"])
        if "per_side" in p:
            r["per_side"] = p["per_side"]
        recs.append(r)
    return recs


def _frac(a, b) -> str:
    return f"{a}/{b}"


def aggregate(scenes: list[dict], recs_by: dict, e1: bool) -> dict:
    conf = {r: Counter() for r in ROLES}
    other_to_hml, n_other = 0, 0
    ro_ok = ro_n = 0
    ro_by_role = {r: [0, 0] for r in ROLES}
    own = defaultdict(lambda: [0, 0])  # 역할 맞은 hand·meld·loose 의 주인
    riv_a, riv_q, riv_n = 0, 0, 0
    riv_a_dist = Counter()
    false_hand = 0
    pred_hand = 0
    fh_scene = 0  # E1: 화료자 아닌 자리에 hand / E3: 라벨 hand 아닌 상자를 hand 로 답한 상자가 있는 프레임
    fh_max = 0
    fh_box_scene = 0
    fh_box_max = 0
    scene_all_ok = 0
    for sc in scenes:
        recs = recs_by[sc["name"]]
        ok_all = True
        seat_fh = Counter()
        seat_fh_box = Counter()
        for r in recs:
            if not r["score"]:
                continue
            lr_ = r["role"]
            if r["pr"] == "hand":
                pred_hand += 1
                if e1 and r["po"] != sc["winner"]:
                    seat_fh[r["po"]] += 1
            if lr_ != "hand" and r["pr"] == "hand":
                false_hand += 1
                seat_fh_box[r["po"]] += 1
            if lr_ == "other":
                n_other += 1
                other_to_hml += r["pr"] in HML
                continue
            if lr_ not in ROLES:
                continue
            conf[lr_][r["pr"]] += 1
            ro_n += 1
            ro_ok += r["ro_ok"]
            ro_by_role[lr_][1] += 1
            ro_by_role[lr_][0] += r["ro_ok"]
            ok_all &= r["ro_ok"]
            if lr_ in HML and r["role_ok"]:
                key = lr_ if lr_ != "meld" or not e1 else ("meld_winner" if r["owner_kind"] == "winner" else "meld_other")
                own[key][1] += 1
                own[key][0] += r["po"] == r["seat"]
                own["all"][1] += 1
                own["all"][0] += r["po"] == r["seat"]
            if lr_ == "river" and r["seat"]:
                riv_n += 1
                riv_a += r["po"] == r["seat"]
                riv_q += r["quad"] == r["seat"]
                riv_a_dist[r["po"]] += 1
        scene_all_ok += ok_all
        if seat_fh:
            fh_scene += 1
            fh_max = max(fh_max, max(seat_fh.values()))
        if seat_fh_box:
            fh_box_scene += 1
            fh_box_max = max(fh_box_max, max(seat_fh_box.values()))
    role_ok = {r: _frac(conf[r][r], sum(conf[r].values())) for r in ROLES}
    tot_ok = sum(conf[r][r] for r in ROLES)
    tot_n = sum(sum(c.values()) for c in conf.values())
    hmr_wrong = sum(sum(conf[r].values()) - conf[r][r] for r in ("hand", "meld", "river"))
    res = {
        "n_scenes": len(scenes),
        "role": {"total": _frac(tot_ok, tot_n), "wrong": tot_n - tot_ok, "by_role": role_ok, "hand_meld_river_wrong": hmr_wrong,
                 "confusion": {r: dict(conf[r]) for r in ROLES if conf[r]}},
        "other": {"n": n_other, "answered_hand_meld_loose": other_to_hml},
        "role_owner": {"ok": _frac(ro_ok, ro_n), "wrong": ro_n - ro_ok, "by_role": {r: _frac(*v) for r, v in ro_by_role.items() if v[1]},
                       "scenes_all_ok": _frac(scene_all_ok, len(scenes))},
        "owner_hml_given_role_ok": {k: _frac(*v) for k, v in own.items()},
        "river_owner": {"A": _frac(riv_a, riv_n), "quadrant": _frac(riv_q, riv_n), "A_answer_dist": dict(riv_a_dist),
                        "A_wrong": riv_n - riv_a, "quadrant_wrong": riv_n - riv_q},
        "false_hand": {"boxes_label_not_hand_pred_hand": false_hand, "pred_hand_total": pred_hand,
                       "scenes_with_false_hand_box": fh_box_scene, "max_false_hand_one_seat": fh_box_max},
    }
    if e1:
        res["false_hand"].update({"scenes_hand_at_non_winner_seat": fh_scene, "max_hand_one_non_winner_seat": fh_max})
    return res


def run_set(scenes: list[dict], pred_fn) -> dict:
    recs = {}
    for sc in scenes:
        recs[sc["name"]] = score_scene(sc, pred_fn(sc))
    return recs


def e4(scenes: list[dict], pred_fn, base_recs: dict) -> dict:
    out = {"by_k": {}, "diff": []}
    tot = Counter()
    for k in (1, 2, 3):
        c = Counter()
        for sc in scenes:
            r0 = base_recs[sc["name"]]
            rot = rotate_scene(sc, k)
            pr = pred_fn(rot)
            for i, (a, b) in enumerate(zip(r0, pr)):
                back = b["owner"] if b["owner"] == "center" else SIDES[(SIDES.index(b["owner"]) + k) % 4]
                same_r = a["pr"] == b["role"]
                same_ro = same_r and a["po"] == back
                c["n"] += 1
                c["role"] += same_r
                c["role_owner"] += same_ro
                q_back = SIDES[(SIDES.index(quadrant(rot["boxes"][i], rot["W"], rot["H"], rot["grid"])) + k) % 4]
                c["quad"] += q_back == a["quad"]
                if not same_ro:
                    out["diff"].append({"scene": sc["name"], "k": k, "i": i, "orig": [a["pr"], a["pc"], a["po"]], "rot": [b["role"], b["conf"], back]})
        out["by_k"][90 * k] = {"role": _frac(c["role"], c["n"]), "role_owner": _frac(c["role_owner"], c["n"]), "quadrant": _frac(c["quad"], c["n"])}
        tot += c
    out["total"] = {"role": _frac(tot["role"], tot["n"]), "role_owner": _frac(tot["role_owner"], tot["n"]), "quadrant": _frac(tot["quad"], tot["n"]),
                    "role_pct": round(100 * tot["role"] / tot["n"], 3), "role_owner_pct": round(100 * tot["role_owner"] / tot["n"], 3)}
    return out


def cv_consistency(scenes: list[dict], recs: dict) -> dict:
    """A 의 화료자 side 답(per_side[winner])이 cv_nostaged_v3r15d.json 의 화료자 기준 1회 pred 와 같은지(같은 가중치·같은 토큰이면 같아야 함)."""
    cv = json.loads((V2 / "cv_nostaged_v3r15d.json").read_text(encoding="utf-8"))["per"]
    n = same = 0
    bad = []
    for sc in scenes:
        p = cv[sc["name"]]["pred"]
        for r in recs[sc["name"]]:
            n += 1
            mine = r["per_side"][sc["winner"]][0]
            same += mine == p[r["i"]]
            if mine != p[r["i"]]:
                bad.append((sc["name"], r["i"], p[r["i"]], mine))
    return {"same": _frac(same, n), "diff": bad[:30]}


# ---------------------------------------------------------------- 표
def table(title: str, res: dict, e1: bool) -> str:
    L = [f"\n## {title} (장면 {res['n_scenes']})"]
    rr = res["role"]
    L.append(f"역할 전체 {rr['total']} (틀림 {rr['wrong']}, hand·meld·river 틀림 {rr['hand_meld_river_wrong']})")
    L.append("  역할별 " + " · ".join(f"{k} {v}" for k, v in rr["by_role"].items() if not v.endswith("/0")))
    L.append("  혼동(라벨→답) " + "; ".join(f"{k}→{ {p: c for p, c in v.items() if p != k} }" for k, v in rr["confusion"].items() if any(p != k for p in v)))
    L.append(f"other {res['other']['n']}개 중 hand·meld·loose 로 답함 {res['other']['answered_hand_meld_loose']}")
    ro = res["role_owner"]
    L.append(f"역할+주인 {ro['ok']} (틀림 {ro['wrong']}), 모든 상자 맞은 장면 {ro['scenes_all_ok']}")
    L.append("  역할별 " + " · ".join(f"{k} {v}" for k, v in ro["by_role"].items()))
    L.append("hand·meld·loose 주인(역할 맞은 것 중) " + " · ".join(f"{k} {v}" for k, v in res["owner_hml_given_role_ok"].items()))
    rv = res["river_owner"]
    L.append(f"강 주인 A {rv['A']} (답 분포 {rv['A_answer_dist']}) / 사분면 참고선 {rv['quadrant']}")
    fh = res["false_hand"]
    s = f"헛 hand 상자 {fh['boxes_label_not_hand_pred_hand']} (있는 장면 {fh['scenes_with_false_hand_box']}, 한 자리 최대 {fh['max_false_hand_one_seat']}), hand 로 답한 상자 {fh['pred_hand_total']}"
    if e1:
        s += f"; 화료자 아닌 자리 hand 장면 {fh['scenes_hand_at_non_winner_seat']}, 한 자리 최대 {fh['max_hand_one_non_winner_seat']}"
    L.append(s)
    return "\n".join(L)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["test", "detect", "check", "run"])
    a = ap.parse_args()
    torch.set_num_threads(4)
    OWN.mkdir(parents=True, exist_ok=True)
    if a.cmd == "test":
        print(json.dumps(unit_test(), ensure_ascii=False, indent=1))
        return
    if a.cmd == "detect":
        names = [fr["name"] for sp in ("test", "dev") for fr in json.loads((FR / f"labels_{sp}.json").read_text(encoding="utf-8"))["frames"]]
        RECTS_CACHE.write_text(json.dumps(detect_rects(names), ensure_ascii=False), encoding="utf-8")
        print(RECTS_CACHE)
        return
    t0 = time.time()
    checks = {"unit_test": unit_test()}
    print("단위 테스트", {k: checks["unit_test"][k] for k in ("cases", "rows", "worst", "lie_flip", "n_fail", "ok")}, flush=True)
    all1, info1 = e1_scenes(all_scenes=True)
    checks["unrotate"] = unrotate_check(all1)
    checks["unrotate"]["x_same_as_labels_v2"] = info1["x_same_as_labels_v2"]
    print("되돌림 검증 최대", checks["unrotate"]["worst_all_rows"], "1e-3 넘는 줄", len(checks["unrotate"]["rows_over_1e-3"]), flush=True)
    s1 = [s for s in all1 if s["eval"]]
    checks["rotate"] = rotate_check(s1)
    print("회전 장면 점검", checks["rotate"], flush=True)
    rects_all = json.loads(RECTS_CACHE.read_text(encoding="utf-8"))
    s3t, st_t = e3_scenes("test", rects_all)
    s3d, st_d = e3_scenes("dev", rects_all)
    checks["frames_rects"] = {"test": st_t, "dev": st_d, "detector": rects_all.get("_model")}
    print("프레임 회전 상자", checks["frames_rects"], flush=True)
    if a.cmd == "check":  # 예측기를 안 돌리는 점검만(장면 수·되돌림·회전·프레임 상자 맞춤)
        print("E1 장면", len(s1), Counter(s["fold"] for s in s1), "E3 시험", len(s3t), "개발", len(s3d))
        print(json.dumps(checks["unrotate"]["rows_over_1e-3"], ensure_ascii=False))
        print({k: v for k, v in checks["unrotate"]["scenes"].items() if k in {s["name"] for s in s1}})
        return
    nets = FoldNets()
    A = PredictorA(nets)
    models = {"E1": {s["name"]: nets.path(s["fold"]).name for s in s1}, "E3_test": sorted({nets.path(s["fold"]).name for s in s3t}),
              "E3_dev": dict(Counter(nets.path(s["fold"]).name for s in s3d))}
    r1 = run_set(s1, A)
    checks["cv_consistency"] = cv_consistency(s1, r1)
    print("cv 대조(화료자 side 답 = cv_nostaged_v3r15d pred)", checks["cv_consistency"]["same"], flush=True)
    r3t = run_set(s3t, A)
    r3d = run_set(s3d, A)
    res = {"E1": aggregate(s1, r1, True), "E3_test": aggregate(s3t, r3t, False), "E3_dev": aggregate(s3d, r3d, False)}
    for nm, ss, rr in (("E3_test", s3t, r3t), ("E3_dev", s3d, r3d)):
        res[nm + "_by_phase"] = {ph: aggregate([s for s in ss if s["phase"] == ph], rr, False) for ph in ("early", "mid", "late", "open")}
        res[nm + "_open_vs_not"] = {g: aggregate([s for s in ss if (s["phase"] == "open") == (g == "open")], rr, False)["false_hand"] for g in ("open", "not_open")}
    res["E4"] = e4(s1, A, r1)
    meta = {"date": time.strftime("%Y-%m-%d %H:%M"), "predictor": "A", "cmd": "python -I -X utf8 experiments/tile_classifier/role_owner_eval.py run",
            "env": {k: os.environ.get(k) for k in ("ROLE_OTHER_NEG", "ROLE_DROP_SAFE", "ROLE_LOOSE_SHIFT", "ROLE_SYNTH_V3_ROT", "ROLE_EVAL_COMPOSITE")},
            "models": models, "e1_scenes": [s["name"] for s in s1], "secs": None,
            "defs": {
                "role": "라벨 역할이 ROLES 6종이고 score 인 상자. other 는 빼고 hand·meld·loose 로 답한 수만 셈",
                "role_owner": "역할 맞음 + 라벨이 hand·meld·loose 면 주인(owner 답) = 라벨 seat. 강·wall·pair 는 역할만. other·score=false 뺌",
                "owner_hml": "라벨 hand·meld·loose 이고 역할이 맞은 상자 중 주인 맞음. E1 울기는 라벨 owner winner/other 로 나눔",
                "river_owner": "라벨 river(seat 있음) 전부(역할 답과 무관): A = 예측기 owner 답(side_of → 대부분 center), 사분면 참고선",
                "false_hand": "라벨이 hand 아닌(other 포함) score 상자를 hand 로 답한 수. E1 은 hand 답의 주인이 화료자 아닌 자리인 장면 수·한 자리 최대도",
                "conf": "RoleNet.predict 처럼 확신을 소수 셋째 자리로 반올림한 뒤 _pick_role(hand ≥ 0.8)",
                "E4": "원본 답과 회전 장면 답(주인 자리를 되돌림)이 같은 앞면 상자 비율(전 앞면, 라벨 무관)"}}
    sum_out = {"meta": meta, "checks": checks, "summary": res,
               "scenes": {"E1": {s["name"]: {"fold": s["fold"], "winner": s["winner"], "boxes": r1[s["name"]]} for s in s1},
                          "E3_test": {s["name"]: {"fold": s["fold"], "phase": s["phase"], "boxes": r3t[s["name"]]} for s in s3t},
                          "E3_dev": {s["name"]: {"fold": s["fold"], "phase": s["phase"], "boxes": r3d[s["name"]]} for s in s3d}}}
    meta["secs"] = round(time.time() - t0, 1)
    (OWN / "eval_A.json").write_text(json.dumps(sum_out, ensure_ascii=False, default=float), encoding="utf-8")
    print(table("E1 화료 상자", res["E1"], True))
    print(table("E3 시험(11-07 오후)", res["E3_test"], False))
    for ph, r in res["E3_test_by_phase"].items():
        print(table(f"E3 시험 — {ph}", r, False))
    print("E3 시험 헛 hand 펼침/아님", res["E3_test_open_vs_not"])
    print(table("E3 개발(10-31)", res["E3_dev"], False))
    for ph, r in res["E3_dev_by_phase"].items():
        print(table(f"E3 개발 — {ph}", r, False))
    print("E3 개발 헛 hand 펼침/아님", res["E3_dev_open_vs_not"])
    print("\n## E4 회전 일치", json.dumps(res["E4"]["by_k"], ensure_ascii=False), res["E4"]["total"], "다른 상자", len(res["E4"]["diff"]))
    for dd in res["E4"]["diff"][:20]:
        print("  ", dd)
    print(OWN / "eval_A.json", f"{meta['secs']}초")


if __name__ == "__main__":
    main()
