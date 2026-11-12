"""역할 모델 후보 R(회전만) 학습·채점(2026-11-12, `docs/role_owner_plan_1111.md` 4-2 "후보 R" · "R 만 학습하기로 함 + 기준 확정").

R = v3r15d 와 같은 재료·설정(생성기 v3 8,000장면 × 씨드 3, 3 epoch 사전학습 → 실제 연출 뺀 장면 + 변형 사본 3, 100 epoch, lr 3e-4, 씨드 3, 4겹 + 전부)
    에서 하나만 바꿈: 학습 묶음에 장면을 넣을 때마다(뽑힐 때마다) 0·90·180·270° 중 하나를 무작위로 골라 `role_owner_eval.turn_tokens` 로 x 를 돌린다.
    라벨 y 는 그대로. 회전 난수는 따로 둔 생성기(사전학습 40_000 + 씨드, 미세 조정 50_000 + 씨드)라 회전을 꺼도 나머지 난수 흐름은 `role_set.train` 과 같다.
예측기 R = 사진 기준 토큰 x0 를 한 번 → 역할 = 확률 최대(확신 = 소수 셋째 자리 반올림), 주인 = `role_owner_eval.side_of`(모든 역할), 겹 가중치 role_R_fold_<겹>.pt.

  python -I -X utf8 experiments/tile_classifier/role_owner_train.py regress   # 회전 끔 + pre_synth8k_v3r15d.pt → cv_nostaged_v3r15d.json 상자별 답 재현 확인
  python -I -X utf8 experiments/tile_classifier/role_owner_train.py train     # R 사전학습 + 4겹 + 전부 → data/role/owner/{pre_synth8k_R,role_R_fold_*,role_R_all}.pt
  python -I -X utf8 experiments/tile_classifier/role_owner_train.py eval      # E1·E3·E4 + A 와 짝 비교 → data/role/owner/eval_R.json
로그는 data/role/owner/log_<명령>.txt 에 같이 적는다. 환경 변수(v3r15d 와 같음)는 role_owner_eval 을 import 할 때 그 스크립트가 넣는다.

regress 의 라벨: cv_nostaged_v3r15d.json(11-09 13:57)은 153311 라벨을 고치기 전(11-10, 표 1-156·1-157)의 labels_v2 로 학습한 결과라
  재현 확인은 그때 라벨(`labels_v2_before_153311fix.json`)로 한다. R 학습(train)은 지금 라벨(`role_v2_train.load()` = labels_v2.json)을 쓴다.
"""
from __future__ import annotations

import copy
import json
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import role_owner_eval as roe  # noqa: E402  (환경 변수를 v3r15d 와 같게 넣은 뒤 role_set·role_v2_train 을 import 한다)

import numpy as np  # noqa: E402
import torch  # noqa: E402
from torch import nn  # noqa: E402

import role_set as rs  # noqa: E402
import role_synth_v3 as g  # noqa: E402
import role_v2_train as t  # noqa: E402

sys.path.insert(0, str(HERE.parent / "speed"))
import stats  # noqa: E402

OWN = roe.OWN
V2 = t.V2
ROLES = rs.ROLES
assert t.SHIFT_ON and g.ROT == "15" and g.DROP_SAFE and rs.DROP_SAFE and g.OTHER_NEG and rs.OTHER_NEG and not rs.NONE, "환경 변수가 v3r15d 와 다름"
PRE_ROT_SEED, FT_ROT_SEED = 40_000, 50_000


class Tee:
    def __init__(self, path: Path):
        self.f = open(path, "a", encoding="utf-8")
        self.out = sys.stdout

    def write(self, s):
        self.out.write(s)
        self.f.write(s)
        self.f.flush()

    def flush(self):
        self.out.flush()
        self.f.flush()


# ---------------------------------------------------------------- 학습 고리
def train(scenes: list[dict], epochs: int, seed: int, net: nn.Module | None = None, lr: float = 1e-3, rot_rng: np.random.Generator | None = None) -> nn.Module:
    """`role_set.train`(relbias 없음)을 옮김: 같은 옵티마이저(AdamW wd 0.01)·코사인 스케줄·가중 교차 엔트로피(라벨 평활 0.05)·OTHER_NEG 손실·
    배치 8·`rs.batch` 온라인 지터·씨드 사용 순서. 더한 것은 rot_rng 하나 — 주면 묶음에 넣는 장면마다 rot_rng 로 0~3 을 골라 turn_tokens."""
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    net = rs.SetNet(feat=scenes[0]["x"].shape[1]) if net is None else copy.deepcopy(net)
    freq = Counter((6 if (rs.NONE and r == -2) else r) for s in scenes for r in s["y"] if r >= 0 or (rs.NONE and r == -2))
    w = torch.tensor([1 / np.sqrt(max(freq[i], 1)) for i in range(len(ROLES))], dtype=torch.float32)
    w = w / w.mean()
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=0.01)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)
    loss_fn = nn.CrossEntropyLoss(weight=w, ignore_index=-1, label_smoothing=0.05)
    net.train()
    for _ in range(epochs):
        order = rng.permutation(len(scenes))
        for k in range(0, len(order), 8):
            picked = [scenes[i] for i in order[k:k + 8]]
            if rot_rng is not None:  # 후보 R: 뽑힐 때마다 90° 단위 회전(라벨 그대로)
                picked = [dict(s, x=roe.turn_tokens(s["x"], int(rot_rng.integers(4)))) for s in picked]
            X, Y, pad = rs.batch(picked, rng)
            opt.zero_grad()
            logits = net(X, pad).reshape(-1, len(ROLES))
            Yf = Y.reshape(-1)
            if rs.NONE:
                Yf = torch.where(Yf == -2, torch.full_like(Yf, 6), Yf)
            loss = loss_fn(logits, Yf.clamp(min=-1))
            neg = Yf == -2
            if rs.OTHER_NEG and neg.any():
                pw = torch.softmax(logits[neg], 1)[:, rs.WIN_IDX].sum(1)
                loss = loss - torch.log((1 - pw).clamp_min(1e-4)).mean()
            loss.backward()
            opt.step()
        sched.step()
    return net.eval()


def load_labels(path: Path) -> list[dict]:
    """`role_v2_train.load` 를 옮김(라벨 파일만 인자로). regress 에서 153311 고치기 전 라벨을 읽으려고."""
    d = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for name, s in d.items():
        x = np.array(s["x"], np.float32)
        if t.SHIFT_ON and name in t.LOOSE_SHIFT:
            x = t.shift_loose(name, x, s["y"], s["items"])
        y = list(s["y"])
        if rs.OTHER_NEG:
            y = [-2 if i < s["n_face"] and s["items"][i]["role"] == "other" else v for i, v in enumerate(y)]
        out.append(dict(name=name, x=x, y=y, n_face=s["n_face"], items=s["items"], kind=s["kind"], staged=t.staged(s), fold=t.fold_of(name)))
    return out


def finetune(pool: list[dict], pre: list, rot: bool) -> list:
    """`role_v2_train.cv` 의 fit(사전학습 있음): 씨드마다 train_set(tr, 3, seed) → 100 epoch, lr 3e-4."""
    return [train(t.train_set(pool, 3, seed), 100, seed, pre[seed], 3e-4, np.random.default_rng(FT_ROT_SEED + seed) if rot else None) for seed in range(len(pre))]


def cmd_regress() -> None:
    t0 = time.time()
    lab = V2 / "labels_v2_before_153311fix.json"
    scenes = load_labels(lab)
    assert scenes and [s for s in scenes if s["name"] == "20261107_153311"][0]["items"][6]["role"] == "hand"
    pool = [s for s in scenes if not s["staged"]]
    pre = rs.load_nets(rs.OUT / "pre_synth8k_v3r15d.pt")
    cv = json.loads((V2 / "cv_nostaged_v3r15d.json").read_text(encoding="utf-8"))["per"]
    print("회귀 확인: 라벨", lab.name, "장면", len(scenes), "학습 풀", len(pool), "사전학습 씨드", len(pre), flush=True)
    tot = Counter()
    diffs = []
    per_fold = {}
    for fold in t.FOLDS:
        tr = [s for s in pool if s["fold"] != fold]
        te = [s for s in scenes if s["fold"] == fold]
        nets = finetune(tr, pre, rot=False)
        torch.save([n.state_dict() for n in nets], OWN / f"regress_v3r15d_fold_{fold}.pt")
        c = Counter()
        for s in te:
            p = t.probs_torch(nets, s["x"])
            pred = [ROLES[int(i)] for i in p.argmax(1)][: s["n_face"]]
            ref = cv[s["name"]]["pred"]
            assert len(ref) == len(pred), (s["name"], len(ref), len(pred))
            for i, (a, b) in enumerate(zip(pred, ref)):
                c["n"] += 1
                c["same"] += a == b
                if a != b:
                    diffs.append((s["name"], i, b, a))
        per_fold[fold] = f"{c['same']}/{c['n']}"
        tot += c
        print(fold, "학습", len(tr), "시험", len(te), "같은 상자", per_fold[fold], f"{round(time.time() - t0)}초", flush=True)
    res = dict(date=time.strftime("%Y-%m-%d %H:%M"), labels=lab.name, same=f"{tot['same']}/{tot['n']}", per_fold=per_fold, diffs=diffs,
               ok=tot["same"] == tot["n"], secs=round(time.time() - t0))
    (OWN / "regress_v3r15d.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("회귀 확인", res["same"], "통과" if res["ok"] else "실패", diffs[:20], f"{res['secs']}초", flush=True)


def cmd_train() -> None:
    reg = json.loads((OWN / "regress_v3r15d.json").read_text(encoding="utf-8"))
    assert reg["ok"], "회귀 확인이 통과하지 않음 — R 학습을 시작하지 않는다"
    t0 = time.time()
    pf = OWN / "pre_synth8k_R.pt"
    assert not pf.exists(), f"{pf} 가 이미 있음(학습은 한 번)"
    pre = []
    for seed in range(3):
        pre.append(train(g.dataset(8000, 100 + seed), 3, seed, rot_rng=np.random.default_rng(PRE_ROT_SEED + seed)))
        print("R 사전학습 씨드", seed, f"{round(time.time() - t0)}초", flush=True)
    torch.save([n.state_dict() for n in pre], pf)
    pre = rs.load_nets(pf)  # role_v2_train.cv 처럼 저장한 파일에서 읽어 미세 조정
    scenes = t.load()  # 지금 라벨(labels_v2.json)
    pool = [s for s in scenes if not s["staged"]]
    print("미세 조정 풀", len(pool), "(연출 뺌)", flush=True)
    for fold in t.FOLDS:
        tr = [s for s in pool if s["fold"] != fold]
        nets = finetune(tr, pre, rot=True)
        torch.save([n.state_dict() for n in nets], OWN / f"role_R_fold_{fold}.pt")
        print(fold, "학습", len(tr), f"{round(time.time() - t0)}초", flush=True)
    nets = finetune(pool, pre, rot=True)
    torch.save([n.state_dict() for n in nets], OWN / "role_R_all.pt")
    print("전부", len(pool), f"{round(time.time() - t0)}초", "끝", flush=True)


# ---------------------------------------------------------------- 채점
class FoldNetsR(roe.FoldNets):
    def __init__(self):
        super().__init__("R")

    def path(self, fold: str) -> Path:
        return OWN / f"role_R_fold_{fold}.pt"


class PredictorR:
    """사진 기준 토큰 1회 → 역할 = argmax, 확신 = max(소수 셋째 자리), 주인 = side_of(모든 역할)."""

    name = "R"

    def __init__(self, nets: FoldNetsR):
        self.nets = nets

    def __call__(self, sc: dict) -> list[dict]:
        nf = sc["n_face"]
        p = self.nets.probs(sc["fold"], sc["x0"])[:nf]
        return [{"role": ROLES[int(r.argmax())], "conf": round(float(r.max()), 3), "owner": roe.side_of(sc["boxes"][i], sc["W"], sc["H"], sc["grid"])}
                for i, r in enumerate(p)]


def wrong_counts(recs_by: dict, key: str) -> dict:
    return {nm: sum(1 for r in recs if key in r and not r[key]) for nm, recs in recs_by.items()}


def boot(a_recs: dict, b_recs: dict, key: str, cluster_of=lambda n: n, n: int = 1000, seed: int = 0) -> dict:
    """장면 묶음 부트스트랩(stats.bootstrap_diff): 행 = 장면, ok 칸에 틀린 상자 수. 묶음마다 행 수가 같으면 scene 지표 × 장면 수 = Σ틀림 차(R − A)."""
    wa, wb = wrong_counts(a_recs, key), wrong_counts(b_recs, key)
    A = [dict(key=nm, cluster=cluster_of(nm), ok=wa[nm], hit=0, want=0, bad_auto=0) for nm in wa]
    B = [dict(key=nm, cluster=cluster_of(nm), ok=wb[nm], hit=0, want=0, bad_auto=0) for nm in wb]
    r = stats.bootstrap_diff(A, B, n, seed)
    if r["pairs"] == r["clusters"]:
        k = r["pairs"]
        sc = r["scene"]
        return dict(A=sum(wa.values()), R=sum(wb.values()), diff=round(sc["est"] * k, 3), lo=round(sc["lo"] * k, 3), hi=round(sc["hi"] * k, 3),
                    zero_in=sc["same"], clusters=r["clusters"], scenes=r["pairs"])
    # 묶음 하나에 장면 여럿(E3 판 단위): 묶음째 뽑아 Σ틀림 차를 직접 다시 잰다(stats 와 같은 뽑기·백분위)
    import random

    groups: dict = {}
    for nm in wa:
        groups.setdefault(cluster_of(nm), []).append(wb[nm] - wa[nm])
    names = sorted(groups)
    rng = random.Random(seed)
    draws = sorted(sum(sum(groups[c]) for c in rng.choices(names, k=len(names))) for _ in range(n))
    lo, hi = draws[int(0.025 * (n - 1))], draws[int(round(0.975 * (n - 1)))]
    return dict(A=sum(wa.values()), R=sum(wb.values()), diff=sum(wb.values()) - sum(wa.values()), lo=lo, hi=hi, zero_in=lo <= 0 <= hi,
                clusters=len(names), scenes=len(wa))


def flips(a_recs: dict, b_recs: dict, key: str) -> dict:
    """R 이 A 보다 새로 틀린(A 맞음·R 틀림) / 새로 맞힌(A 틀림·R 맞음) 상자 수, 라벨 역할별."""
    new_wrong, new_right = Counter(), Counter()
    for nm, ra in a_recs.items():
        for a, b in zip(ra, b_recs[nm]):
            assert a["i"] == b["i"] and a["role"] == b["role"] and a["seat"] == b["seat"]
            if key not in a:
                continue
            if a[key] and not b[key]:
                new_wrong[a["role"]] += 1
            if not a[key] and b[key]:
                new_right[a["role"]] += 1
    return {"new_wrong": dict(new_wrong), "new_wrong_total": sum(new_wrong.values()), "new_right": dict(new_right), "new_right_total": sum(new_right.values())}


def same_as_saved(saved: dict, recs_by: dict) -> dict:
    """다시 잰 A 가 eval_A.json 의 상자별 기록과 같은지(pr·pc·po·role_ok·ro_ok)."""
    n = same = 0
    bad = []
    for nm, recs in recs_by.items():
        for a, b in zip(saved[nm]["boxes"], recs):
            n += 1
            ok = all(a.get(k) == b.get(k) for k in ("i", "role", "seat", "pr", "pc", "po", "role_ok", "ro_ok"))
            same += ok
            if not ok:
                bad.append((nm, a["i"]))
    return {"same": f"{same}/{n}", "diff": bad[:20]}


def cmd_eval() -> None:
    t0 = time.time()
    s1all, _ = roe.e1_scenes(all_scenes=True)
    s1 = [s for s in s1all if s["eval"]]
    rects_all = json.loads(roe.RECTS_CACHE.read_text(encoding="utf-8"))
    s3t, _ = roe.e3_scenes("test", rects_all)
    s3d, _ = roe.e3_scenes("dev", rects_all)
    print("E1", len(s1), "E3 시험", len(s3t), "개발", len(s3d), flush=True)
    saved_A = json.loads((OWN / "eval_A.json").read_text(encoding="utf-8"))
    assert [s["name"] for s in s1] == saved_A["meta"]["e1_scenes"]
    # A 다시 재기(같은 시각 나란히) → eval_A.json 과 같은지
    A = roe.PredictorA(roe.FoldNets())
    a1, a3t, a3d = roe.run_set(s1, A), roe.run_set(s3t, A), roe.run_set(s3d, A)
    checks = {"A_rerun_vs_eval_A": {"E1": same_as_saved(saved_A["scenes"]["E1"], a1), "E3_test": same_as_saved(saved_A["scenes"]["E3_test"], a3t),
                                    "E3_dev": same_as_saved(saved_A["scenes"]["E3_dev"], a3d)}}
    print("A 다시 잰 것 = eval_A.json", {k: v["same"] for k, v in checks["A_rerun_vs_eval_A"].items()}, flush=True)
    nets = FoldNetsR()
    R = PredictorR(nets)
    models = {"E1": {s["name"]: nets.path(s["fold"]).name for s in s1}, "E3_test": sorted({nets.path(s["fold"]).name for s in s3t}),
              "E3_dev": dict(Counter(nets.path(s["fold"]).name for s in s3d))}
    r1, r3t, r3d = roe.run_set(s1, R), roe.run_set(s3t, R), roe.run_set(s3d, R)
    res = {"E1": roe.aggregate(s1, r1, True), "E3_test": roe.aggregate(s3t, r3t, False), "E3_dev": roe.aggregate(s3d, r3d, False)}
    for nm, ss, rr in (("E3_test", s3t, r3t), ("E3_dev", s3d, r3d)):
        res[nm + "_by_phase"] = {ph: roe.aggregate([s for s in ss if s["phase"] == ph], rr, False) for ph in ("early", "mid", "late", "open")}
        res[nm + "_open_vs_not"] = {g_: roe.aggregate([s for s in ss if (s["phase"] == "open") == (g_ == "open")], rr, False)["false_hand"] for g_ in ("open", "not_open")}
    res["E4"] = roe.e4(s1, R, r1)
    # A 와 짝 비교(A 는 eval_A.json 의 상자별 기록)
    A_rec = {k: {nm: v["boxes"] for nm, v in saved_A["scenes"][k].items()} for k in ("E1", "E3_test", "E3_dev")}
    R_rec = {"E1": r1, "E3_test": r3t, "E3_dev": r3d}
    game = lambda nm: nm.split("_f")[0]
    cmp = {}
    for k in ("E1", "E3_test", "E3_dev"):
        cmp[k] = {"role_owner": boot(A_rec[k], R_rec[k], "ro_ok"), "role_only": boot(A_rec[k], R_rec[k], "role_ok"),
                  "flips_role_owner": flips(A_rec[k], R_rec[k], "ro_ok"), "flips_role": flips(A_rec[k], R_rec[k], "role_ok")}
        if k != "E1":
            cmp[k]["role_owner_game_cluster"] = boot(A_rec[k], R_rec[k], "ro_ok", game)
    sA = saved_A["summary"]
    e1, e3 = res["E1"], res["E3_test"]
    nh = res["E3_test_open_vs_not"]["not_open"]["pred_hand_total"]
    verdict = {
        "r1": dict(ok=e1["role_owner"]["wrong"] < sA["E1"]["role_owner"]["wrong"] and cmp["E1"]["role_owner"]["hi"] < 0,
                   R_wrong=e1["role_owner"]["wrong"], A_wrong=sA["E1"]["role_owner"]["wrong"], ci=[cmp["E1"]["role_owner"]["lo"], cmp["E1"]["role_owner"]["hi"]]),
        "r2": dict(ok=e1["role"]["hand_meld_river_wrong"] <= sA["E1"]["role"]["hand_meld_river_wrong"] + 2, R=e1["role"]["hand_meld_river_wrong"],
                   limit=sA["E1"]["role"]["hand_meld_river_wrong"] + 2),
        "r4": dict(ok=e3["role_owner"]["wrong"] <= sA["E3_test"]["role_owner"]["wrong"] + 2 and nh == 0, R_wrong=e3["role_owner"]["wrong"],
                   limit=sA["E3_test"]["role_owner"]["wrong"] + 2, not_open_pred_hand=nh),
        "r5": dict(ok=res["E4"]["total"]["role_pct"] >= 99.0, role_pct=res["E4"]["total"]["role_pct"], role=res["E4"]["total"]["role"]),
    }
    verdict["all"] = all(v["ok"] for v in verdict.values())
    meta = {"date": time.strftime("%Y-%m-%d %H:%M"), "predictor": "R", "cmd": "python -I -X utf8 experiments/tile_classifier/role_owner_train.py eval",
            "env": {k: __import__("os").environ.get(k) for k in ("ROLE_OTHER_NEG", "ROLE_DROP_SAFE", "ROLE_LOOSE_SHIFT", "ROLE_SYNTH_V3_ROT", "ROLE_EVAL_COMPOSITE")},
            "models": models, "e1_scenes": [s["name"] for s in s1], "secs": None,
            "defs": dict(saved_A["meta"]["defs"], predictor_R="사진 기준 x0 1회 → 역할 argmax, 확신 max 소수 셋째 자리, 주인 side_of(모든 역할)",
                         bootstrap="장면 묶음(E1 사진, E3 프레임) 1,000회 seed 0, stats.bootstrap_diff, R − A 틀린 상자 수. E3 은 판 묶음도 참고로",
                         flips="역할 + 주인(ro_ok) 정의로 A 맞음·R 틀림 = new_wrong, A 틀림·R 맞음 = new_right, 라벨 역할별")}
    out = {"meta": meta, "checks": checks, "summary": res, "compare_vs_A": cmp, "verdict": verdict,
           "scenes": {"E1": {s["name"]: {"fold": s["fold"], "winner": s["winner"], "boxes": r1[s["name"]]} for s in s1},
                      "E3_test": {s["name"]: {"fold": s["fold"], "phase": s["phase"], "boxes": r3t[s["name"]]} for s in s3t},
                      "E3_dev": {s["name"]: {"fold": s["fold"], "phase": s["phase"], "boxes": r3d[s["name"]]} for s in s3d}}}
    meta["secs"] = round(time.time() - t0, 1)
    (OWN / "eval_R.json").write_text(json.dumps(out, ensure_ascii=False, default=float), encoding="utf-8")
    print(roe.table("E1 화료 상자 — R", res["E1"], True))
    print(roe.table("E3 시험(11-07 오후) — R", res["E3_test"], False))
    for ph, r in res["E3_test_by_phase"].items():
        print(roe.table(f"E3 시험 — {ph} — R", r, False))
    print("E3 시험 헛 hand 펼침/아님", res["E3_test_open_vs_not"])
    print(roe.table("E3 개발(10-31) — R", res["E3_dev"], False))
    for ph, r in res["E3_dev_by_phase"].items():
        print(roe.table(f"E3 개발 — {ph} — R", r, False))
    print("E3 개발 헛 hand 펼침/아님", res["E3_dev_open_vs_not"])
    print("\n## E4 회전 일치 — R", json.dumps(res["E4"]["by_k"], ensure_ascii=False), res["E4"]["total"], "다른 상자", len(res["E4"]["diff"]))
    print("\n## R − A", json.dumps(cmp, ensure_ascii=False, indent=1))
    print("\n## 판정", json.dumps(verdict, ensure_ascii=False))
    print(OWN / "eval_R.json", f"{meta['secs']}초")


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["regress", "train", "eval"])
    a = ap.parse_args()
    OWN.mkdir(parents=True, exist_ok=True)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout = Tee(OWN / f"log_{a.cmd}.txt")
    torch.set_num_threads(8)
    print(f"=== {a.cmd} 시작 {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    {"regress": cmd_regress, "train": cmd_train, "eval": cmd_eval}[a.cmd]()


if __name__ == "__main__":
    main()
