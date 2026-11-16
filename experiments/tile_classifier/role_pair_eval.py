"""0단계 채점(2026-11-16, `docs/role_pair_plan_1116.md` 2절·4절·5절 0단계). 학습 없음. 정답 = role_pair_scenes.json(먼저 고정, 읽기만).

  python -I -X utf8 experiments/tile_classifier/role_pair_eval.py run     # A(서버 read_wall 응답 저장) → M0(read_roles pair) 를 같은 시각에 이어서
  flutter test tool/role_pair_rule_test.dart                               # A 의 앱 규칙(localPairIndicators) 답 → rule_answers.json
  python -I -X utf8 experiments/tile_classifier/role_pair_eval.py score   # A·M0·합친 값 E2·E4 + E1(cv 파일) → step0_result.json
결과·중간 산출물: data/role/pair/step0/(gitignore).

모델(robust_suite.Readers 와 같은 고르기, ROBUST_CLS=cls6·ROBUST_SEAT=det_r8 — 운영 분류기 v3·자리 검출 8회차의 나눔):
  검출(강·표시패 det_fold_*, 자리 det_r8_fold_*)·분류(cls6_<bcd|am|pm>) = B·C·D·10-31 은 그 사진을 안 배운 나눔, 11-07 은 운영(11-07 을 배운 적 없음).
  역할 = v3r15d 의 4겹 교차 검증 가중치(role_v2_nostaged_v3r15d_fold_<겹>.pt, 씨드 3 확률 평균) — 10-31·11-07 은 그 사진 겹을 안 배운 것,
         B·C·D 는 전부 학습 가중치(role_v2_nostaged_v3r15d_all.pt = 운영 tile-roles-v3r15d.onnx, B·C·D 는 역할 라벨에 없음).
  (robust_suite 는 10-31 에 3겹 운영 나눔 ONNX, 11-07 에 운영 전체(11-07 을 배움)를 쓴다 — 11-07 홀드아웃이 안 돼 4겹 가중치로 바꿈. metrics 표 4-8 과 같은 고르기.)
M0 규칙(계획서 2절, 결과를 보기 전에 고정): 화료자 기준 1회 read_roles 응답 roles 에서 role == "pair" 상자 2~4장이면 각 상자를
  LocalReader.read_turned(사진, 상자, tw, th)(tw·th = 사진 전체 detect_other 앞면 상자의 짧은·긴 변 중앙값, _read_wall 과 같음)로 읽어
  한 장이라도 확신 < 0.7 이면 답 없음, 1장·0장·5장 이상도 답 없음.
합친 값 = M0 답이 있으면 M0, 없으면 A.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

for _k, _v in (("ROBUST_CLS", "cls6"), ("ROBUST_SEAT", "det_r8"), ("ROBUST_ROLE", "tile-roles-v3r15d"),
               ("ROLE_OTHER_NEG", "1"), ("ROLE_DROP_SAFE", "1"), ("ROLE_LOOSE_SHIFT", "1"), ("ROLE_SYNTH_V3_ROT", "15"), ("ROLE_EVAL_COMPOSITE", "1")):
    os.environ[_k] = _v
os.environ.pop("ROLE_NONE", None)
os.environ.pop("ROLE_LABELS", None)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REC = Path(r"C:\Users\jjh7757\dev\mahjong-recognizer")
for p in (HERE, ROOT / "experiments" / "speed", REC):
    sys.path.insert(0, str(p))

OUT = HERE / "data" / "role" / "pair" / "step0"
SCENES = HERE / "role_pair_scenes.json"
WALL = OUT / "wall_responses.json"
M0 = OUT / "m0_responses.json"
RULE = OUT / "rule_answers.json"
RESULT = OUT / "step0_result.json"
V2 = HERE / "data" / "role" / "v2"
PAIR_MIN, PAIR_MAX, CONF_MIN = 2, 4, 0.7  # 계획서 2절 — 결과를 보고 바꾸지 않는다


def git_sha(repo: Path) -> str:
    r = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(repo), "status", "--short", "--", "app"], capture_output=True, text=True).stdout.split()
    return r + (" + 커밋 전 변경 " + " ".join(x for x in dirty if x != "M") if dirty else "")


class CvNet:
    """roles.RoleNet 자리에 끼우는 4겹 가중치(씨드 3 확률 평균 = role_v2_train.probs_torch). 역할 = argmax, 확신 = max 소수 셋째(RoleNet.predict 와 같음)."""

    def __init__(self, path: Path):
        import role_set as rs

        self.path, self.nets = path, rs.load_nets(path)

    feat = 11

    def predict_full(self, x):
        import role_v2_train as t

        p = t.probs_torch(self.nets, x)
        return [t.ROLES[int(i)] for i in p.argmax(1)], [round(float(v), 3) for v in p.max(1)], None

    def predict(self, x):
        return self.predict_full(x)[:2]


def role_weights(name: str) -> tuple[Path, str]:
    import role_v2_train as t

    if name.startswith("k"):
        return V2 / "role_v2_nostaged_v3r15d_all.pt", "all(33장 — B·C·D 는 라벨에 없음)"
    f = t.fold_of(name)
    return V2 / f"role_v2_nostaged_v3r15d_fold_{f}.pt", f"fold_{f}(시험 겹 {f} 를 뺀 학습)"


def learned(name: str, files: dict, role_note: str) -> dict:
    """그 사진을 배웠나(대응표: README '홀드아웃 조합' 절, metrics 표 4-8). 검출·분류는 robust_suite 대응표, 역할은 4겹."""
    is_prod = not name.startswith(("k", "2026103"))
    return {"det_cls": "아니오(운영 = 11-07 이전 학습·cls6 는 11-07 크롭 없음)" if is_prod else "아니오(나눔)",
            "role": "아니오(" + role_note + ")"}


def load_scenes() -> tuple[dict, list[dict]]:
    import seat_grow as sg

    truth = json.loads(SCENES.read_text(encoding="utf-8"))
    ss = {s["name"]: s for s in sg.eval_scenes()}
    assert set(ss) == {r["name"] for r in truth["scenes"]}
    return truth, [dict(ss[r["name"]], truth=r) for r in truth["scenes"]]


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    tmp.replace(path)


def cmd_run(a) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    import torch

    torch.set_num_threads(2)
    import robust_suite as rsu
    from app import local_read as lr
    from app import obb
    from app import roles
    from app.recognizer import prepare_image

    truth, scenes = load_scenes()
    rd = rsu.Readers("fold", 2)
    nets: dict = {}
    meta = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "recognizer": git_sha(REC), "scenes_file_made": truth["made"],
            "env": {k: os.environ.get(k) for k in ("ROBUST_CLS", "ROBUST_SEAT", "WALL_FRAME", "WALL_FRAME_GRID_SRC", "LOCAL_OTHER_DET")}}
    wall = {"_meta": meta, "scenes": {}}
    # ---- A: 서버 read_wall 응답(장면마다 저장)
    meta["A_start"] = time.strftime("%Y-%m-%d %H:%M:%S")
    jpegs = {}
    for s in scenes:
        n = s["name"]
        (reader, _), files = rd.get(n)
        jpegs[n] = prepare_image(Path(s["path"]).read_bytes(), 4080)
        t0 = time.perf_counter()
        o = reader.read_wall(jpegs[n], None, dict(s["grid"]), "saved")
        wall["scenes"][n] = {"winner": s["side"], "grid": s["grid"], "wall": o, "models": {k: files[k] for k in ("det", "seat", "cls")},
                             "secs": round(time.perf_counter() - t0, 2)}
        dump(WALL, wall)
        print("A", n, "pairs", [[p["tile"] for p in g] for g in o["pairs"]], "패산", [i["tile"] for i in o["indicators"]], flush=True)
    meta["A_end"] = time.strftime("%Y-%m-%d %H:%M:%S")
    dump(WALL, wall)
    # ---- M0: 화료자 기준 read_roles → pair 상자
    m0 = {"_meta": dict(meta, M0_start=time.strftime("%Y-%m-%d %H:%M:%S")), "scenes": {}}
    for s in scenes:
        n = s["name"]
        (reader, _), files = rd.get(n)
        wpath, note = role_weights(n)
        if wpath not in nets:
            nets[wpath] = CvNet(wpath)
        net = nets[wpath]
        jpeg = jpegs[n]
        t0 = time.perf_counter()
        o = roles.read_roles(reader, jpeg, s["side"], dict(s["grid"]), "hybrid", net=net, grid_src="saved")
        prs = [r for r in o["roles"] if r["role"] == "pair"]
        rgb = lr.decode_rgb(jpeg)
        with obb.session():
            faces = reader.detect_other(rgb)
        tw = statistics.median(min(f[2], f[3]) for f in faces) if faces else 1
        th = statistics.median(max(f[2], f[3]) for f in faces) if faces else 1
        reads, ans, why = [], None, None
        if PAIR_MIN <= len(prs) <= PAIR_MAX:
            reads = [reader.read_turned(rgb, tuple(r["box"]), tw, th) for r in prs]
            if all(c >= CONF_MIN for _, c in reads):
                ans = [t for t, _ in reads]
            else:
                why = "확신 0.7 미만"
        else:
            why = {0: "pair 0장", 1: "pair 1장(떼어 둔 패 후보)"}.get(len(prs), f"pair {len(prs)}장(5장 이상)")
        m0["scenes"][n] = {"n_pair": len(prs), "pairs": prs, "reads": [{"tile": t, "conf": c} for t, c in reads], "answer": ans, "why": why,
                           "tw_th": [tw, th], "role_weights": wpath.name, "models": {k: files[k] for k in ("det", "seat", "cls")},
                           "learned": learned(n, files, note), "separate_tile": o.get("separate_tile"), "counts": o.get("counts"),
                           "wall_frame": o.get("wall_frame"), "secs": round(time.perf_counter() - t0, 2)}
        dump(M0, m0)
        print("M0", n, "pair", len(prs), "→", ans, why or "", [(t, c) for t, c in reads], flush=True)
    m0["_meta"]["M0_end"] = time.strftime("%Y-%m-%d %H:%M:%S")
    dump(M0, m0)
    # 확인: 4겹 가중치 끼우개가 운영 ONNX 와 같은 답인지(전부 가중치 all.pt = tile-roles-v3r15d.onnx)
    s = scenes[0]
    (reader, _), _ = rd.get(s["name"])
    a1 = roles.read_roles(reader, jpegs[s["name"]], s["side"], dict(s["grid"]), "hybrid", net=nets[role_weights(s["name"])[0]], grid_src="saved")
    a2 = roles.read_roles(reader, jpegs[s["name"]], s["side"], dict(s["grid"]), "hybrid", net=roles.RoleNet(rsu.REPO / "app" / "assets" / "tile-roles-v3r15d.onnx"), grid_src="saved")
    same = sum(x["role"] == y["role"] for x, y in zip(a1["roles"], a2["roles"]))
    m0["_meta"]["wrapper_check"] = {"scene": s["name"], "same_roles": f"{same}/{len(a1['roles'])}", "max_conf_diff": max(abs(x["conf"] - y["conf"]) for x, y in zip(a1["roles"], a2["roles"]))}
    dump(M0, m0)
    print("끼우개 확인", m0["_meta"]["wrapper_check"], "끝", time.strftime("%H:%M:%S"))


# ---------------------------------------------------------------- 채점
def norm(ts, red5: bool) -> list[str]:
    return sorted(t.replace("0", "5") if red5 else t for t in ts)


def judge(ans, truth: dict) -> dict:
    """ans = 표시패 목록 또는 None(답 없음). E2: 정답과 같은 집합인가(적5=5 / 가름). E4: 답을 냈나(헛 표시패)."""
    want = truth["table_pair"]
    out = {"answer": ans}
    if truth["eval"] == "E2":
        out["ok"] = ans is not None and norm(ans, True) == norm(want, True)
        out["ok_strict"] = ans is not None and norm(ans, False) == norm(want, False)
        out["wrong"] = ans is not None and not out["ok"]
    else:
        out["false"] = ans is not None
    return out


def cv_roles(path: Path, labels: Path) -> dict:
    """cv 파일의 장면별 pred 와 라벨로 역할별 맞은 상자(채점 장면 = per[eval]), 화료자 쪽 장면(seat_ok)."""
    cv = json.loads(path.read_text(encoding="utf-8"))
    lab = json.loads(labels.read_text(encoding="utf-8"))
    roles6 = ["hand", "meld", "river", "wall", "pair", "loose"]
    ok, n = Counter(), Counter()
    ok_fair = Counter()
    seat = n_ev = 0
    for name, p in cv["per"].items():
        if not p["eval"]:
            continue
        n_ev += 1
        seat += bool(p["seat_ok"])
        items = lab[name]["items"]
        assert len(items) >= len(p["pred"]), name
        for i, pr in enumerate(p["pred"]):
            r = items[i]["role"]
            if r not in roles6:
                continue
            n[r] += 1
            ok[r] += pr == r
    return {"file": path.name, "labels": labels.name, "made": time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime)),
            "roles": {r: f"{ok[r]}/{n[r]}" for r in roles6}, "wrong": {r: n[r] - ok[r] for r in roles6},
            "seat": f"{seat}/{n_ev}", "summary": cv["cv"]}


def cmd_score(a) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    truth = json.loads(SCENES.read_text(encoding="utf-8"))
    wall = json.loads(WALL.read_text(encoding="utf-8"))
    m0 = json.loads(M0.read_text(encoding="utf-8"))
    rule = json.loads(RULE.read_text(encoding="utf-8"))
    rows, tot = [], {k: Counter() for k in ("A", "M0", "AM")}
    for r in truth["scenes"]:
        n = r["name"]
        ra = rule["scenes"][n]
        a_ans = [t["tile"] for t in ra["tiles"]] or None
        m = m0["scenes"][n]
        m_ans = m["answer"]
        am = m_ans if m_ans is not None else a_ans
        row = {"name": n, "eval": r["eval"], "winner": r["winner"], "riichi": r["riichi"], "truth_pair": r["table_pair"], "truth_wall": r["wall"],
               "A": judge(a_ans, r), "A_pairs": ra["pairs"], "A_has_sticks": ra["has_sticks"],
               "M0": judge(m_ans, r), "M0_n_pair": m["n_pair"], "M0_reads": m["reads"], "M0_why": m["why"],
               "AM": judge(am, r), "models": {**m["models"], "role": m["role_weights"]}, "learned": m["learned"],
               "wall_server": [i["tile"] for i in wall["scenes"][n]["wall"]["indicators"]]}
        rows.append(row)
        for k in ("A", "M0", "AM"):
            c = tot[k]
            c[r["eval"]] += 1
            if r["eval"] == "E2":
                c["ok"] += row[k]["ok"]
                c["ok_strict"] += row[k]["ok_strict"]
                c["wrong"] += row[k]["wrong"]
                c["none"] += row[k]["answer"] is None
            else:
                c["false"] += row[k]["false"]
            c["answered"] += row[k]["answer"] is not None
    summary = {k: {"E2_ok": f"{c['ok']}/{c['E2']}", "E2_ok_strict": f"{c['ok_strict']}/{c['E2']}", "E2_wrong": c["wrong"], "E2_none": c["none"],
                   "E4_false": f"{c['false']}/{c['E4']}", "answered": c["answered"]} for k, c in tot.items()}
    # E1: 세 씨드 파일(153311 고치기 전 라벨로 학습·채점) + v3r15dfix(고친 뒤) + 다시 돌린 값(지금 라벨)
    e1 = {}
    before = V2 / "labels_v2_before_153311fix.json"
    for tag, lab in (("v3r15d", before), ("v3r15d_s10", before), ("v3r15d_s20", before), ("v3r15dfix", V2 / "labels_v2.json"),
                     ("v3r15d_rerun1116", V2 / "labels_v2.json")):
        p = V2 / f"cv_nostaged_{tag}.json"
        if p.exists():
            e1[tag] = cv_roles(p, lab)
    if {"v3r15d", "v3r15d_s10", "v3r15d_s20"} <= set(e1):
        pr = [int(e1[t]["roles"]["pair"].split("/")[0]) for t in ("v3r15d", "v3r15d_s10", "v3r15d_s20")]
        e1["_pair_seed_spread"] = {"values": pr, "max_minus_min": max(pr) - min(pr), "p1_margin": 3, "exceeds_or_equal_3": max(pr) - min(pr) >= 3}
    if "v3r15d_rerun1116" in e1:
        rr = json.loads((V2 / "cv_nostaged_v3r15d_rerun1116.json").read_text(encoding="utf-8"))["per"]
        cmp = {}
        for tag in ("v3r15d", "v3r15dfix"):
            ref = json.loads((V2 / f"cv_nostaged_{tag}.json").read_text(encoding="utf-8"))["per"]
            same = tot_ = 0
            diffs = []
            for name, p in rr.items():
                for i, (x, y) in enumerate(zip(p["pred"], ref[name]["pred"])):
                    tot_ += 1
                    same += x == y
                    if x != y:
                        diffs.append([name, i, y, x])
            cmp[tag] = {"same_boxes": f"{same}/{tot_}", "diffs": diffs[:30]}
        e1["_rerun_vs"] = cmp
    res = {"made": time.strftime("%Y-%m-%d %H:%M:%S"), "run_meta": {"wall": wall["_meta"], "m0": m0["_meta"], "rule_made": rule["made"]},
           "rule": {"pair_min": PAIR_MIN, "pair_max": PAIR_MAX, "conf_min": CONF_MIN}, "summary": summary, "e1": e1, "rows": rows,
           "learned_any": [r["name"] for r in rows if not r["learned"]["role"].startswith("아니오") or not r["learned"]["det_cls"].startswith("아니오")]}
    dump(RESULT, res)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for r in rows:
        f = lambda x: ("O" if x.get("ok") else "X") if r["eval"] == "E2" else ("헛" if x.get("false") else "-")
        print(f"{r['eval']} {r['name']:16s} 정답 {r['truth_pair']} | A {r['A']['answer']} {f(r['A'])} | M0 n{r['M0_n_pair']} {r['M0']['answer']} {f(r['M0'])} {r['M0_why'] or ''} | 합 {f(r['AM'])}")
    print(json.dumps({k: v for k, v in e1.items()}, ensure_ascii=False, indent=1)[:4000])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "score"])
    a = ap.parse_args()
    {"run": cmd_run, "score": cmd_score}[a.cmd](a)
