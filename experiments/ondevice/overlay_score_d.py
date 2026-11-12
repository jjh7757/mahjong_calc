"""역할 모델 D 끝단 확인(d3, 2026-11-12, `docs/role_owner_plan_1111.md` 4-2 끝 "끝단 확인 (d3) 방법·기준 확정"). 학습 없음.

사진 → 검출(`detect_full`) → 종류 분류 → 역할 단계까지 겹쳐 보기와 같은 경로에서 지금 방식(A)과 새 모델(D)을 같은 시각·같은 상자 위에서 잰다.
세트·채점은 `overlay_score.py`(표 4-2)와 같다: `rs.scenes("dev")` 40장 + 저장 격자, `overlay_score.scene_score`·`box_score` 그대로.

역할 모델(그 사진을 안 배운 것):
  겹 = 이름이 2026… 이면 `role_v2_train.fold_of`(1031am·1031pm·1107am·1107pm), B·C·D(k##)는 역할 라벨에 없어 전부 학습 가중치.
  A = `data/role/v2/role_v2_nostaged_v3r15d_fold_<겹>.pt`(전부 = `_all.pt`)를 RoleNet 모양(`.feat` 11, `.predict` → 씨드 3 확률 평균의 argmax·max 소수 셋째 자리)
      으로 감싸 `roles.role_net` 자리에 끼우고 **`ondevice.overlay` 를 그대로** 부른다.
  D = `data/role/owner/role_D_fold_<겹>.pt`(전부 = `role_D_all.pt`). 겹쳐 보기 본체는 안 고치고, 이 파일의 `overlay_with(role_fn)` 이 overlay 의 흐름
      (디코딩 → detect_full → 방향 후보 분류 → 토큰 → 역할 → 출력 모양)을 옮긴 것. D 의 role_fn = `roles.tokens(…, "bottom", 11, pts, backs)` 1회 →
      역할 = 역할 확률 최대, 주인 = 주인 확률 최대(SIDES 이름, 모든 상자), 뒷면 토큰의 답은 버림.
  경로 점검 = `overlay_with` 에 A 의 규칙(네 side 토큰 + `_pick_role` + `side_of`)을 role_fn 으로 넣은 답이 `ondevice.overlay` 와 상자·종류·역할·자리가 같은가(40장).
사진마다 검출·분류는 `overlay_with` 안에서 한 번(`front`) 하고 A 규칙·D 가 나눠 쓴다. `ondevice.overlay` 는 A 의 공식 답 + 경로 점검용으로 따로 한 번 더 돈다
  (점검이 40/40 같으면 A 공식 답 = 나눠 쓴 상자 위의 A 답).
검출·분류 모델 = `--models fold`(B·C·D·10-31 나눔, 11-07 은 나눔이 없어 운영) | `--models prod`(운영) — `robust_suite.Readers` 그대로. 역할 모델은 fold 면 위 겹,
  prod 면 A·D 모두 전부 학습 가중치.

채점(더한 것):
  - 상자 주인(새 라벨 seat 직접 비교): 원본 사진에 라벨이 달린 25장, box_score 와 같은 맞춤(IoU 가장 큰 상자, > 0.5). "역할 + 주인" = 역할이 맞고,
    라벨 역할이 hand·meld·loose 면 답의 자리(s)가 라벨 seat 와 같음(강·그 밖은 역할만, 계획서 기준 보완 정의). A·D 따로.
  - 강 주인(D 만): 맞춘 라벨 river 상자(답 역할과 상관없이 맞춘 것 전부)에서 D 의 자리 대 seat. 같은 상자(검출 상자)에 사분면 참고선
    (`role_owner_eval.quadrant`, 장면 저장 격자 그대로 — sticks 가 있으면 sticks 가운데) 도. 참고로 sticks 를 뺀 격자(겹쳐 보기에 들어간 격자)의 사분면도 적는다.
  - 시간(PC 참고): 장면마다 공유 앞단(디코딩·검출·분류·꼭짓점·뒷면)과 역할 단계(A 4회 대 D 1회, 토큰 + 모델만).

  python -I -X utf8 experiments/ondevice/overlay_score_d.py --models fold --tag 1112 [--draw]
  python -I -X utf8 experiments/ondevice/overlay_score_d.py --models prod --tag 1112 [--draw]
결과 experiments/ondevice/results/overlay_score_d_<models>_<TAG>.json, 그림 build/overlay_score_d/<models>/<이름>_{A,D}.jpg(틀린 장면만).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TC = ROOT / "experiments" / "tile_classifier"
sys.path.insert(0, str(HERE))
import overlay_score as osc  # noqa: E402  (ROBUST_* 환경 변수·서버·speed·android python 경로를 넣는다)

sys.path.insert(0, str(TC))
import numpy as np  # noqa: E402
import torch  # noqa: E402

import role_owner_eval as roe  # noqa: E402  (v3r15d 환경 변수 · turn_tokens · side_of · quadrant)
import role_owner_train_d as rtd  # noqa: E402  (SetNetOwner · load_nets_d · probs_d)
import role_set as rset  # noqa: E402
import role_v2_train as rvt  # noqa: E402

ondevice = osc.ondevice  # overlay_score 가 쓰는 그 모듈(roles.role_net·_reader 를 바꿔 끼움)
rs = osc.rs
from app import local_read as lr  # noqa: E402
from app import obb, roles  # noqa: E402

SIDES = roles.SIDES
ROLES = roles.ROLES
assert list(ROLES) == list(rset.ROLES) and tuple(SIDES) == tuple(rtd.SIDES)
V2 = TC / "data" / "role" / "v2"
OWN = TC / "data" / "role" / "owner"
LABELS_OWNER = V2 / "labels_v2_owner.json"
HML = ("hand", "meld", "loose")


# ---------------------------------------------------------------- 역할 모델 감싸기
def role_fold(name: str) -> str:
    return rvt.fold_of(name) if name.startswith("2026") else "all"


def a_path(fold: str) -> Path:
    return V2 / ("role_v2_nostaged_v3r15d_all.pt" if fold == "all" else f"role_v2_nostaged_v3r15d_fold_{fold}.pt")


def d_path(fold: str) -> Path:
    return OWN / ("role_D_all.pt" if fold == "all" else f"role_D_fold_{fold}.pt")


class TorchRoleNet:
    """roles.RoleNet 과 같은 모양: .feat = 11, .predict(x) → (역할 목록, 확신 목록). 씨드 3 확률 평균(role_v2_train.probs_torch)의 argmax·max(소수 셋째 자리)."""

    feat = roles.FEAT_ROT

    def __init__(self, path: Path):
        self.path = path
        self.nets = rset.load_nets(path)
        assert all(n.inp[0].weight.shape[1] == self.feat for n in self.nets), path
        self.calls = 0

    def predict(self, x: np.ndarray) -> tuple[list[str], list[float]]:
        self.calls += 1
        if len(x) == 0:
            return [], []
        p = rvt.probs_torch(self.nets, np.asarray(x, np.float32))
        return [ROLES[int(i)] for i in p.argmax(1)], [round(float(v), 3) for v in p.max(1)]


class TorchRoleNetD:
    """D: 사진 기준 토큰 1회 → (역할 확률, 주인 확률) 씨드 3 평균(role_owner_train_d.probs_d)."""

    feat = roles.FEAT_ROT

    def __init__(self, path: Path):
        self.path = path
        self.nets = rtd.load_nets_d(path)
        assert all(rtd.has_owner(n) and n.inp[0].weight.shape[1] == self.feat for n in self.nets), path
        self.calls = 0

    def probs(self, x: np.ndarray):
        self.calls += 1
        return rtd.probs_d(self.nets, np.asarray(x, np.float32))


_cache: dict = {}


def net_a(fold: str) -> TorchRoleNet:
    k = ("A", fold)
    if k not in _cache:
        _cache[k] = TorchRoleNet(a_path(fold))
    return _cache[k]


def net_d(fold: str) -> TorchRoleNetD:
    k = ("D", fold)
    if k not in _cache:
        _cache[k] = TorchRoleNetD(d_path(fold))
    return _cache[k]


# ---------------------------------------------------------------- role_fn
def role_fn_a(net: TorchRoleNet):
    """A 의 규칙 그대로(ondevice.overlay 의 역할 단계): 네 side 토큰 → net.predict → _pick_role → 주인 = hand 면 그 side, 아니면 side_of(격자 칸)."""

    def f(boxes, W, H, grid, pts, backs):
        n = len(boxes)
        by_side = {}
        for side in SIDES:
            x = roles.tokens(boxes, W, H, grid, side, net.feat, pts, backs)
            r, c = net.predict(x)
            by_side[side] = (r[:n], c[:n])
        out = []
        for i, b in enumerate(boxes):
            role, conf, owner = ondevice._pick_role({s: (by_side[s][0][i], float(by_side[s][1][i])) for s in SIDES})
            out.append((role, conf, owner or roe.side_of(b, W, H, grid)))
        return out

    return f


def role_fn_d(net: TorchRoleNetD):
    """D: 사진 기준(side bottom) 토큰 1회 → 역할 = 역할 확률 최대, 주인 = 주인 확률 최대. 뒷면 토큰의 답은 버림."""

    def f(boxes, W, H, grid, pts, backs):
        n = len(boxes)
        if n == 0:
            return []
        x = roles.tokens(boxes, W, H, grid, "bottom", net.feat, pts, backs)
        pr, po = net.probs(x)
        return [(ROLES[int(pr[i].argmax())], round(float(pr[i].max()), 3), SIDES[int(po[i].argmax())]) for i in range(n)]

    return f


# ---------------------------------------------------------------- overlay 흐름 옮김
def front(image, query, reader) -> dict:
    """ondevice.overlay 의 역할 단계 앞까지(디코딩 → detect_full → 방향 후보 분류 → 꼭짓점·뒷면). 뒷면은 feat 11 일 때만 쓰는데 A·D 모두 11."""
    t0 = time.perf_counter()
    q = {str(k): str(v) for k, v in dict(query).items()}
    grid = ondevice._grid(q, False) or {"x1": 280, "x2": 745, "y1": 173, "y2": 713}
    jpeg = ondevice._prepare(bytes(image), 4080)
    with obb.session():
        full = lr.decode_rgb(jpeg)
        H, W = full.shape[:2]
        t1 = time.perf_counter()
        boxes = reader.detect_full(jpeg, full)
        t2 = time.perf_counter()
        crops, owner = [], []
        for i, b in enumerate(boxes):
            im = lr.cut(full, b)
            ts = (0, 2) if b[3] > 1.15 * b[2] else (1, 3) if b[2] > 1.15 * b[3] else (0, 1, 2, 3)
            for k in ts:
                crops.append(im.rotate(90 * k, expand=True))
                owner.append(i)
        best: dict = {}
        for s in range(0, len(crops), 64):
            p = reader.probs(crops[s:s + 64])
            for j, row in enumerate(p):
                i = owner[s + j]
                if i not in best or row.max() > best[i].max():
                    best[i] = row
        kinds = [lr.top2(best[i]) if i in best else ("?", 0.0, None, None) for i in range(len(boxes))]
        t3 = time.perf_counter()
        pts = [roles._pts_of(full, b) for b in boxes]
        backs = [(b, obb.corners(rc)) for b, rc in obb.backs_of(full)]
        t4 = time.perf_counter()
    return {"grid": grid, "W": W, "H": H, "boxes": boxes, "kinds": kinds, "pts": pts, "backs": backs,
            "ms": {"decode": round((t1 - t0) * 1000), "detect": round((t2 - t1) * 1000), "classify": round((t3 - t2) * 1000),
                   "pts_backs": round((t4 - t3) * 1000), "front": round((t4 - t0) * 1000)}}


def finish(fr: dict, role_fn) -> dict:
    """역할 단계 + overlay 와 같은 출력 모양."""
    W, H, boxes, kinds = fr["W"], fr["H"], fr["boxes"], fr["kinds"]
    t0 = time.perf_counter()
    rr = role_fn(boxes, W, H, fr["grid"], fr["pts"], fr["backs"])
    t1 = time.perf_counter()
    out = []
    for i, b in enumerate(boxes):
        role, conf, own = rr[i]
        k = kinds[i]
        out.append({"b": [round(b[0] / W, 4), round(b[1] / H, 4), round(b[2] / W, 4), round(b[3] / H, 4)], "t": k[0], "tc": round(float(k[1]), 3),
                    "r": role, "rc": round(conf, 3), "s": own})
    return {"tiles": out, "backs": len(fr["backs"]), "w": W, "h": H, "ms": dict(fr["ms"], roles=round((t1 - t0) * 1000, 1))}


def overlay_with(image, query, role_fn, reader=None) -> dict:
    """ondevice.overlay 의 흐름을 옮긴 것, 역할 단계만 role_fn(boxes, W, H, grid, pts, backs) → 상자마다 (역할, 확신, 주인)."""
    return finish(front(image, query, reader or ondevice._get_reader()), role_fn)


# ---------------------------------------------------------------- 경로 점검
def same_tiles(a: list, b: list) -> dict:
    if len(a) != len(b):
        return {"same": False, "n": [len(a), len(b)], "diff": ["상자 수"]}
    diff = []
    for i, (p, q) in enumerate(zip(a, b)):
        bad = [k for k in ("b", "t", "r", "s") if p[k] != q[k]]
        soft = [k for k in ("tc", "rc") if p[k] != q[k]]
        if bad or soft:
            diff.append({"i": i, "keys": bad + [f"~{k}" for k in soft], "ov": {k: p[k] for k in bad + soft}, "with": {k: q[k] for k in bad + soft}})
    return {"same": not any(not k.startswith("~") for d in diff for k in d["keys"]), "n": [len(a), len(b)], "diff": diff[:10], "n_diff": len(diff)}


# ---------------------------------------------------------------- 더한 채점
def match_rows(tiles: list, lab: dict) -> list[tuple[dict, int | None]]:
    """box_score 와 같은 맞춤: 라벨 상자마다 IoU 가장 큰 답 상자(> 0.5), 아니면 None(같은 답 상자를 여러 라벨이 가질 수 있음 — box_score 그대로)."""
    W, H = lab["size"]
    out = []
    for it in lab["items"]:
        x, y, w, h = it["box"]
        lb = [x / W, y / H, w / W, h / H]
        j = max(range(len(tiles)), key=lambda k: osc.iou(lb, tiles[k]["b"]), default=None)
        out.append((it, None if j is None or osc.iou(lb, tiles[j]["b"]) <= 0.5 else j))
    return out


def box_owner(tiles: list, lab_own: dict, grid_full: dict, river: bool) -> dict:
    """새 라벨 seat 대비 "역할 + 주인(hand·meld·loose 는 자리까지)". river=True 면 강 주인(답 자리 대 seat)·사분면 참고선도."""
    n = found = role_ok = ro_ok = 0
    wrong, by_role = [], Counter()
    riv = {"n": 0, "ok": 0, "role_river_n": 0, "role_river_ok": 0, "quad_ok": 0, "quad_nosticks_ok": 0, "wrong": [], "quad_wrong": []}
    g_ns = {k: grid_full[k] for k in ("x1", "x2", "y1", "y2")}
    for it, j in match_rows(tiles, lab_own):
        n += 1
        want, seat = it["role"], it.get("seat")
        if j is None:
            wrong.append({"box": it["box"], "want": want, "seat": seat, "got": None})
            by_role[(want, "miss")] += 1
            continue
        found += 1
        t = tiles[j]
        rok = t["r"] == want
        ok = rok and (want not in HML or seat is None or t["s"] == seat)
        role_ok += rok
        ro_ok += ok
        by_role[(want, "ok" if ok else ("role" if not rok else "seat"))] += 1
        if not ok:
            wrong.append({"box": it["box"], "want": want, "seat": seat, "got": t["r"], "s": t["s"], "t": t["t"]})
        if river and want == "river" and seat in SIDES:
            q = roe.quadrant(t["b"], 1, 1, grid_full)
            q2 = roe.quadrant(t["b"], 1, 1, g_ns)
            riv["n"] += 1
            riv["ok"] += t["s"] == seat
            riv["quad_ok"] += q == seat
            riv["quad_nosticks_ok"] += q2 == seat
            if t["r"] == "river":
                riv["role_river_n"] += 1
                riv["role_river_ok"] += t["s"] == seat
            if t["s"] != seat:
                riv["wrong"].append({"box": it["box"], "seat": seat, "got_s": t["s"], "got_r": t["r"], "t": t["t"]})
            if q != seat:
                riv["quad_wrong"].append({"box": it["box"], "seat": seat, "quad": q})
    res = {"n": n, "found": found, "role_ok": role_ok, "ro_ok": ro_ok, "wrong": wrong,
           "by_role": {f"{a}:{b}": c for (a, b), c in sorted(by_role.items())}}
    if river:
        res["river"] = riv
    return res


def wrong_line(sc: dict, tiles: list, side: str) -> str:
    """틀린 장면 한 줄: 손패(hand + loose)·울기의 빠짐/남음, 다른 자리 hand. 빠진 패는 같은 종류 상자가 무엇으로 답했는지(최대 3)."""
    parts = []
    have_h, want_h = Counter(sc["hand"] + sc["loose"]), Counter(sc["want_hand"])
    have_m, want_m = Counter(sc["meld"]), Counter(sc["want_meld"])

    def where(kind, roles_ok):
        c = [f"{t['r']}/{t['s']}" for t in tiles if t["t"] == kind and not (t["r"] in roles_ok and (t["r"] == "loose" or t["s"] == side))]
        return f"{kind}→{','.join(c[:3]) or '못 찾음'}"

    if have_h != want_h:
        miss, extra = want_h - have_h, have_h - want_h
        parts.append("손패 " + " ".join([f"빠짐 {where(k, ('hand', 'loose'))}" for k in sorted(miss.elements())] + [f"남음 {k}" for k in sorted(extra.elements())]))
    if have_m != want_m:
        miss, extra = want_m - have_m, have_m - want_m
        parts.append("울기 " + " ".join([f"빠짐 {where(k, ('meld',))}" for k in sorted(miss.elements())] + [f"남음 {k}" for k in sorted(extra.elements())]))
    if sc["other_hand"]:
        parts.append("헛 hand " + ",".join(f"{s}{n}" for s, n in sc["other_hand"].items()))
    return "; ".join(parts)


def arm_summary(rows: dict, arm: str) -> dict:
    """overlay_score.summary 를 팔(A·D)마다 + 세트 묶음(bcd+visit = B·C·D + 10-31 26장) + 상자 주인·강 주인·한 자리 최대 헛 hand."""
    rr = {n: dict(r[arm], set=r["set"]) for n, r in rows.items()}
    sm = osc.summary(rr)
    groups = {"all": list(rr), "bcd_visit1031": [n for n, r in rr.items() if r["set"] in ("bcd", "visit")], "visit1107": [n for n, r in rr.items() if r["set"] == "visit1107"]}
    sm["bcd_visit1031"] = osc.summary({n: rr[n] for n in groups["bcd_visit1031"]})["all"]
    for g, names in groups.items():
        sub = [rr[n] for n in names]
        bo = [r["box_owner"] for r in sub if r.get("box_owner")]
        conf = Counter()
        for r in sub:
            if r.get("box"):
                conf.update(r["box"]["conf"])
        extra = {"other_hand_max": max((r["other_hand_max"] for r in sub), default=0),
                 "box_owner": {"scenes": len(bo), "n": sum(b["n"] for b in bo), "found": sum(b["found"] for b in bo), "role_ok": sum(b["role_ok"] for b in bo),
                               "ro_ok": sum(b["ro_ok"] for b in bo)},
                 "conf_all": dict(sorted(conf.items(), key=lambda kv: -kv[1]))}
        br = Counter()
        for b in bo:
            br.update(b["by_role"])
        extra["box_owner"]["by_role"] = dict(sorted(br.items()))
        rv = [b["river"] for b in bo if "river" in b]
        if rv:
            extra["river_owner"] = {k: sum(v[k] for v in rv) for k in ("n", "ok", "role_river_n", "role_river_ok", "quad_ok", "quad_nosticks_ok")}
        sm.setdefault(g, {}).update(extra)
    return sm


# ---------------------------------------------------------------- 실행
def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True, choices=["prod", "fold"])
    ap.add_argument("--tag", required=True)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--draw", action="store_true")
    ap.add_argument("--smoke", type=int, default=0, help="앞 N장만, 경로 점검·오류만 찍고 점수는 안 찍음·결과 파일 안 씀(재기 전 동작 확인)")
    a = ap.parse_args()
    torch.set_num_threads(a.threads)
    t_all = time.time()
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"=== overlay_score_d --models {a.models} --tag {a.tag} 시작 {started}", flush=True)

    labels = json.loads(osc.LABELS.read_text(encoding="utf-8"))
    labels_own = json.loads(LABELS_OWNER.read_text(encoding="utf-8"))
    rd = rs.Readers(a.models, a.threads)
    rows, path_check = {}, {}
    sset = rs.scenes("dev")
    if a.smoke:
        sset = sset[: a.smoke]
    for s in sset:
        name = s["name"]
        (reader, _onnx_role), files = rd.get(name)
        rf = role_fold(name) if a.models == "fold" else "all"
        na, nd = net_a(rf), net_d(rf)
        ondevice._reader = reader
        roles.role_net = lambda na=na: na
        g = {k: str(s["grid"][k]) for k in ("x1", "x2", "y1", "y2")}
        img = Path(s["path"]).read_bytes()
        # A 공식 답: ondevice.overlay 그대로
        t0 = time.perf_counter()
        oA = json.loads(ondevice.overlay(img, g))
        secs_ov = time.perf_counter() - t0
        # 나눠 쓰는 앞단 한 번 → A 규칙(경로 점검)·D
        t1 = time.perf_counter()
        fr = front(img, g, reader)
        oA2 = finish(fr, role_fn_a(na))
        oD = finish(fr, role_fn_d(nd))
        secs_with = time.perf_counter() - t1
        pc = same_tiles(oA["tiles"], oA2["tiles"])
        path_check[name] = pc
        r = {"set": s["set"], "side": s["side"], "models": dict(files, role=None, role_A=a_path(rf).name, role_D=d_path(rf).name), "role_fold": rf,
             "secs_overlay": round(secs_ov, 2), "secs_front_AD": round(secs_with, 2),
             "ms": {"overlay_A": oA["ms"], "front": fr["ms"], "roles_A_shared": oA2["ms"]["roles"], "roles_D": oD["ms"]["roles"]},
             "path_same": pc["same"]}
        lab = labels.get(name)
        has_box = bool(lab and Path(lab["image"]).resolve() == Path(s["path"]).resolve())
        for arm, o in (("A", oA), ("D", oD)):
            sc = {"n": len(o["tiles"]), **osc.scene_score(o["tiles"], s), "tiles": o["tiles"]}
            if has_box:
                sc["box"] = osc.box_score(o["tiles"], lab, s["side"])
                sc["box_owner"] = box_owner(o["tiles"], labels_own[name], s["grid"], river=(arm == "D"))
            if not sc["ok"] or sc["other_hand"]:
                sc["wrong_line"] = wrong_line(sc, o["tiles"], s["side"])
            r[arm] = sc
        rows[name] = r
        if a.smoke:  # 점수는 안 찍는다
            print(name, "경로", "같음" if pc["same"] else f"다름 {pc['n_diff']} {pc['diff'][:3]}", "상자", pc["n"], "D 역할 수", dict(Counter(t["r"] for t in oD["tiles"])),
                  "D 자리", dict(Counter(t["s"] for t in oD["tiles"])), "box_owner" in r["D"], "역할 ms A", oA2["ms"]["roles"], "D", oD["ms"]["roles"], flush=True)
            continue
        A, D = r["A"], r["D"]
        bA, bD = A.get("box_owner"), D.get("box_owner")
        print(f"{name[-6:]:>6s} {s['side']:6s} 경로 {'=' if pc['same'] else '≠ ' + str(pc['n_diff'])} | A {'O' if A['ok'] else 'X'} {A['hit']}/{A['want']} 헛 {A['other_hand'] or '-'}"
              f" | D {'O' if D['ok'] else 'X'} {D['hit']}/{D['want']} 헛 {D['other_hand'] or '-'}"
              + (f" | 상자 A {bA['ro_ok']}/{bA['n']} D {bD['ro_ok']}/{bD['n']} 강주인 D {bD['river']['ok']}/{bD['river']['n']} 사분면 {bD['river']['quad_ok']}" if bA else "")
              + f" | 역할 ms A {oA2['ms']['roles']} D {oD['ms']['roles']} ({rf})", flush=True)
        for arm in ("A", "D"):
            if r[arm].get("wrong_line"):
                print(f"       {arm}: {r[arm]['wrong_line']}", flush=True)
        if a.draw:
            for arm, o in (("A", oA), ("D", oD)):
                sc = r[arm]
                b = sc.get("box")
                if not sc["ok"] or sc["other_hand"] or (b and (b["wrong"] or b["extra"])):
                    osc.draw(Path(s["path"]), o["tiles"], b, HERE / "build" / "overlay_score_d" / a.models / f"{name}_{arm}.jpg")

    if a.smoke:
        arm_summary(rows, "A"), arm_summary(rows, "D")  # 요약 코드가 도는지만
        print("smoke 끝: 경로 점검", sum(v["same"] for v in path_check.values()), "/", len(path_check), f"{round(time.time() - t_all, 1)}초")
        return
    smA, smD = arm_summary(rows, "A"), arm_summary(rows, "D")
    okA = {n for n, r in rows.items() if r["A"]["ok"]}
    okD = {n for n, r in rows.items() if r["D"]["ok"]}
    ohA = {n for n, r in rows.items() if r["A"]["other_hand_max"] > 0}
    ohD = {n for n, r in rows.items() if r["D"]["other_hand_max"] > 0}
    verdict = {"e1": {"A": len(okA), "D": len(okD), "ok": len(okD) >= len(okA)}, "e2": {"A": len(ohA), "D": len(ohD), "ok": len(ohD) <= len(ohA)}}
    verdict["all"] = verdict["e1"]["ok"] and verdict["e2"]["ok"]
    flips = {"D_new_ok": sorted(okD - okA), "D_new_wrong": sorted(okA - okD), "A_wrong": sorted(set(rows) - okA), "D_wrong": sorted(set(rows) - okD),
             "other_hand_A": sorted(ohA), "other_hand_D": sorted(ohD)}
    pc_same = sum(v["same"] for v in path_check.values())
    msA = [r["ms"]["roles_A_shared"] for r in rows.values()]
    msD = [r["ms"]["roles_D"] for r in rows.values()]
    msF = [r["ms"]["front"]["front"] for r in rows.values()]
    msOv = [r["ms"]["overlay_A"]["total"] for r in rows.values()]
    q = lambda v: {"median": round(float(np.median(v)), 1), "p90": round(float(np.percentile(v, 90)), 1), "max": round(float(np.max(v)), 1)}
    timing = {"roles_A_4calls_ms": q(msA), "roles_D_1call_ms": q(msD), "front_shared_ms": q(msF), "overlay_A_total_ms": q(msOv),
              "note": "PC(노트북 CPU), torch 씨드 3 평균, torch 스레드 = --threads. 역할 ms = 토큰 + 모델(꼭짓점·뒷면은 앞단에 포함). 태블릿(ONNX)과 다름"}
    meta = {"models": a.models, "tag": a.tag, "recognizer": rs.git_sha(), "started": started, "at": time.strftime("%Y-%m-%d %H:%M:%S"), "secs": round(time.time() - t_all, 1),
            "prep": ondevice.PREP, "threads": a.threads, "cmd": f"python -I -X utf8 experiments/ondevice/overlay_score_d.py --models {a.models} --tag {a.tag}" + (" --draw" if a.draw else ""),
            "role_weights": {"A": sorted({r['models']['role_A'] for r in rows.values()}), "D": sorted({r['models']['role_D'] for r in rows.values()})},
            "path_check": f"{pc_same}/{len(path_check)}",
            "defs": {"scene": "overlay_score.scene_score 그대로(화료자 자리 hand + loose = 정답 손패, 화료자 자리 meld = 정답 울기)",
                     "box": "overlay_score.box_score 그대로(labels_v2.json, 주인 = 손패·울기가 화료자 자리인가)",
                     "box_owner": "labels_v2_owner.json seat 직접: 역할 맞음 + (라벨 hand·meld·loose 면 답 자리 = seat). 강·그 밖은 역할만",
                     "river_owner": "D 만: 맞춘 라벨 river 상자 전부(답 역할 무관)의 D 자리 = seat. quad = roe.quadrant(검출 상자, 장면 저장 격자 — sticks 있으면 sticks 가운데), quad_nosticks = 겹쳐 보기에 들어간 격자(x1..y2)"}}
    out = {"_meta": meta, "verdict": verdict, "flips": flips, "timing": timing, "summary": {"A": smA, "D": smD},
           "path_check": {n: v for n, v in path_check.items() if not v["same"] or v["n_diff"]}, "scenes": rows}
    RES = HERE / "results"
    RES.mkdir(parents=True, exist_ok=True)
    p = RES / f"overlay_score_d_{a.models}_{a.tag}.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print("\n경로 점검", meta["path_check"])
    print("판정", json.dumps(verdict, ensure_ascii=False))
    print("장면 바뀜", json.dumps(flips, ensure_ascii=False))
    print("시간", json.dumps(timing, ensure_ascii=False))
    for arm, sm in (("A", smA), ("D", smD)):
        print(f"\n## {arm}")
        for k in ("all", "bcd_visit1031", "visit1107", "bcd", "visit"):
            if k in sm:
                v = sm[k]
                print(k, {kk: v.get(kk) for kk in ("scenes", "ok", "hand_ok", "meld_ok", "hit", "want", "other_hand_scenes", "other_hand_max", "box_n", "box_found",
                                                    "box_role_ok", "box_own_ok", "box_extra", "box_owner", "river_owner", "conf_wrong")})
    print("→", p, f"{meta['secs']}초")


if __name__ == "__main__":
    main()
