"""2단계 채점(2026-11-16, `docs/role_pair_plan_1116.md` 4-2·4-3·5절 2단계). 학습 없음. 0단계 `role_pair_eval.py` 를 고치지 않고 불러 쓴다
(장면·정답 읽기 load_scenes, 4겹 끼우개 CvNet, 규칙 상수 PAIR_MIN·PAIR_MAX·CONF_MIN, 판정 judge·norm(적5 = 5), E1 cv_roles, git_sha·learned·dump).

본 채점(학습이 끝난 뒤, 저장소 루트에서 이 순서로):
  python -I -X utf8 experiments/tile_classifier/role_pair_eval2.py run     # A(서버 read_wall 새로) → M0 → M1 → M2(화료자 기준 1회 read_roles → pair) → E3 토큰
  python -I -X utf8 experiments/tile_classifier/role_pair_eval2.py rule    # flutter test tool/role_pair_rule_test.dart(ROLE_PAIR_DIR=step2) → rule_answers.json
  python -I -X utf8 experiments/tile_classifier/role_pair_eval2.py score   # E1·E2·E4·E3·부트스트랩·판정 → step2_result.json, scene_table.md, step2_table.md
결과: data/role/pair/step2/(gitignore). 이미 있는 결과 파일은 덮지 않고 멈춘다. run 은 가중치·cv 파일이 하나라도 없으면 아무것도 돌리지 않는다.

연기 시험(--smoke): run 은 장면 2개(E2 하나·E4 하나) + E3 개발 장면 2개, 모델은 A + M0 만 → step2/smoke/. score --dir 로 다른 폴더(예: step0)를 넣어 표만 확인할 수 있다
(M1 이 없으면 M0 를 M1 자리에 넣어 부트스트랩·판정 코드만 돌리고 "연기 — 판정 아님" 으로 적는다). 연기 모드는 M1·M2 파일을 열지 않는다.

모델 고르기(0단계와 같음): 검출·분류 = robust_suite.Readers("fold", 2). 역할 = 10-31·11-07 은 role_v2_train.fold_of(이름) 겹의 fold_*.pt(그 사진을 안 배움),
B·C·D(k*) 는 all.pt. 태그 M0 = _v3r15d_rerun1116(0단계에서 지금 라벨로 다시 돌린 v3r15d), M1 = _pairM1, M2 = _pairM2.
pair → 표시패 규칙은 0단계 cmd_run 의 M0 토막과 글자 그대로(2~4장, read_turned, 확신 0.7). 다른 점: 장면마다 detect_other(tw·th)를 한 번만 재서
세 모델이 같이 쓴다(결정적 계산이라 값은 같다).
E2 판정 = role_pair_scenes.json 의 eval E2 이면서 리치(18장면). 연출 k25·k28(리치 아님)은 따로 적기만. E4 = 그 파일의 E4 20장면(0단계 그대로).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import role_pair_eval as rpe  # noqa: E402  (환경 변수 ROBUST_*·ROLE_* 와 sys.path 를 0단계와 같게 맞춘다)

ROOT = rpe.ROOT
V2 = rpe.V2
PAIR = HERE / "data" / "role" / "pair"
STEP2 = PAIR / "step2"
SMOKE = STEP2 / "smoke"
LABELS = V2 / "labels_v2.json"
FLUTTER = Path(r"C:\Users\jjh7757\flutter\bin\flutter.bat")
TAGS = {"M0": "_v3r15d_rerun1116", "M1": "_pairM1", "M2": "_pairM2"}
SMOKE_SCENES = ("20261031_133826", "20261031_181209")  # E2 하나 · E4 하나(0단계 표에서 M0 가 pair 2장·4장을 낸 장면 — 읽기 토막까지 지나가게)
ROLES6 = ["hand", "meld", "river", "wall", "pair", "loose"]
# 판정 분모(4-2 고정 줄 · 0단계 기준선). 다르면 라벨이 바뀐 것 → 판정하지 않는다.
DENOM = {"pair": 28, "loose": 8, "seat": 26, "hand": 284, "meld": 110, "river": 1121, "E2": 18, "E4": 20}
P1_PAIR, P2_WRONG_HMR, P2_LOOSE, P2_SEAT = 23, 3, 6, 24


def files_of(out: Path) -> dict:
    return {"wall": out / "wall_responses.json", "roles": out / "role_responses.json", "e3": out / "e3_preds.json",
            "rule": out / "rule_answers.json", "result": out / "step2_result.json", "table": out / "scene_table.md", "summary": out / "step2_table.md"}


def weight_files(tag: str) -> list[Path]:
    import role_v2_train as t

    return [V2 / f"cv_nostaged{tag}.json", V2 / f"role_v2_nostaged{tag}_all.pt", *(V2 / f"role_v2_nostaged{tag}_fold_{f}.pt" for f in t.FOLDS)]


def role_weights(name: str, tag: str) -> tuple[Path, str]:
    """rpe.role_weights 와 같은 고르기, 태그만 바꿈."""
    import role_v2_train as t

    if name.startswith("k"):
        return V2 / f"role_v2_nostaged{tag}_all.pt", "all(B·C·D 는 역할 라벨에 없음)"
    f = t.fold_of(name)
    return V2 / f"role_v2_nostaged{tag}_fold_{f}.pt", f"fold_{f}(시험 겹 {f} 를 뺀 학습)"


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- run
def cmd_run(a) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    out = SMOKE if a.smoke else STEP2
    F = files_of(out)
    models = ["M0"] if a.smoke else ["M0", "M1", "M2"]
    missing = [str(p) for m in models for p in weight_files(TAGS[m]) if not p.exists()]
    if missing:
        raise SystemExit("가중치·cv 파일이 없음 — 아무것도 돌리지 않음:\n  " + "\n  ".join(missing))
    exist = [str(p) for k, p in F.items() if p.exists()]
    if exist:
        raise SystemExit("결과 파일이 이미 있음 — 덮지 않고 멈춤:\n  " + "\n  ".join(exist))

    import torch

    torch.set_num_threads(2)
    import robust_suite as rsu
    import role_set as rs
    import role_v2_train as t
    from app import local_read as lr
    from app import obb
    from app import roles
    from app.recognizer import prepare_image

    truth, scenes = rpe.load_scenes()
    if a.smoke:
        scenes = [s for s in scenes if s["name"] in SMOKE_SCENES]
        assert {s["truth"]["eval"] for s in scenes} == {"E2", "E4"}, [s["name"] for s in scenes]
    rd = rsu.Readers("fold", 2)
    t_all = time.perf_counter()
    meta = {"started": now(), "smoke": a.smoke, "recognizer": rpe.git_sha(rpe.REC), "scenes_file_made": truth["made"],
            "scenes_file_mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(rpe.SCENES.stat().st_mtime)),
            "env": {k: os.environ.get(k) for k in ("ROBUST_CLS", "ROBUST_SEAT", "WALL_FRAME", "WALL_FRAME_GRID_SRC", "LOCAL_OTHER_DET")},
            "rule": {"pair_min": rpe.PAIR_MIN, "pair_max": rpe.PAIR_MAX, "conf_min": rpe.CONF_MIN},
            "weights": {m: [{"file": p.name, "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))} for p in weight_files(TAGS[m])]
                        for m in models}}
    # ---- A: 서버 read_wall 응답(장면마다 저장) — rpe.cmd_run 의 A 토막과 같음
    wall = {"_meta": meta, "scenes": {}}
    meta["A_start"] = now()
    jpegs = {}
    for s in scenes:
        n = s["name"]
        (reader, _), files = rd.get(n)
        jpegs[n] = prepare_image(Path(s["path"]).read_bytes(), 4080)
        t0 = time.perf_counter()
        o = reader.read_wall(jpegs[n], None, dict(s["grid"]), "saved")
        wall["scenes"][n] = {"winner": s["side"], "grid": s["grid"], "wall": o, "models": {k: files[k] for k in ("det", "seat", "cls")},
                             "secs": round(time.perf_counter() - t0, 2)}
        rpe.dump(F["wall"], wall)
        print("A", n, "pairs", [[p["tile"] for p in g] for g in o["pairs"]], "패산", [i["tile"] for i in o["indicators"]], flush=True)
    meta["A_end"] = now()
    rpe.dump(F["wall"], wall)

    # ---- M0·M1·M2: 화료자 기준 1회 read_roles → pair 상자 → 표시패(rpe.cmd_run 의 M0 토막과 같은 규칙)
    res = {"_meta": meta, "models": {}}
    faces_cache: dict = {}
    for m in models:
        tag = TAGS[m]
        nets: dict = {}
        res["models"][m] = {"tag": tag, "start": now(), "scenes": {}}
        for s in scenes:
            n = s["name"]
            (reader, _), files = rd.get(n)
            wpath, note = role_weights(n, tag)
            if wpath not in nets:
                nets[wpath] = rpe.CvNet(wpath)
            net = nets[wpath]
            jpeg = jpegs[n]
            t0 = time.perf_counter()
            o = roles.read_roles(reader, jpeg, s["side"], dict(s["grid"]), "hybrid", net=net, grid_src="saved")
            prs = [r for r in o["roles"] if r["role"] == "pair"]
            if n not in faces_cache:
                rgb = lr.decode_rgb(jpeg)
                with obb.session():
                    faces = reader.detect_other(rgb)
                tw = statistics.median(min(f[2], f[3]) for f in faces) if faces else 1
                th = statistics.median(max(f[2], f[3]) for f in faces) if faces else 1
                faces_cache[n] = (rgb, tw, th)
            rgb, tw, th = faces_cache[n]
            reads, ans, why = [], None, None
            if rpe.PAIR_MIN <= len(prs) <= rpe.PAIR_MAX:
                reads = [reader.read_turned(rgb, tuple(r["box"]), tw, th) for r in prs]
                if all(c >= rpe.CONF_MIN for _, c in reads):
                    ans = [t_ for t_, _ in reads]
                else:
                    why = "확신 0.7 미만"
            else:
                why = {0: "pair 0장", 1: "pair 1장(떼어 둔 패 후보)"}.get(len(prs), f"pair {len(prs)}장(5장 이상)")
            res["models"][m]["scenes"][n] = {
                "n_pair": len(prs), "pairs": prs, "reads": [{"tile": t_, "conf": c} for t_, c in reads], "answer": ans, "why": why,
                "tw_th": [tw, th], "role_weights": wpath.name, "models": {k: files[k] for k in ("det", "seat", "cls")},
                "learned": rpe.learned(n, files, note), "separate_tile": o.get("separate_tile"), "counts": o.get("counts"),
                "wall_frame": o.get("wall_frame"), "secs": round(time.perf_counter() - t0, 2)}
            rpe.dump(F["roles"], res)
            print(m, n, "pair", len(prs), "→", ans, why or "", [(t_, c) for t_, c in reads], flush=True)
        res["models"][m]["end"] = now()
        rpe.dump(F["roles"], res)

    # ---- E3(참고): 11-14 개발 쪽 공개 장면, 라벨 상자 토큰, 전체 가중치(all.pt)
    import v1114_load as vl

    e3s = [s for s in vl.role_scenes("dev", "all") if s["phase"] == "end"]
    if a.smoke:
        e3s = e3s[:2]
    e3 = {"_meta": {"start": now(), "src": 'v1114_load.role_scenes("dev", "all"), phase == "end", 토큰 자리 = 화료자(없으면 bottom)',
                    "n_scenes": len(e3s)}, "models": {}, "scenes": {}}
    for s in e3s:
        assert s["fold"] == "v1114_dev", (s["name"], s["fold"])
        e3["scenes"][s["name"]] = {"side": s["side"], "winner": s["winner"], "scene_round": s["scene_round"], "n_face": s["n_face"],
                                   "roles": s["roles"], "owners": s["owners"]}
    for m in models:
        wpath = V2 / f"role_v2_nostaged{TAGS[m]}_all.pt"
        nets = rs.load_nets(wpath)
        e3["models"][m] = {"weights": wpath.name, "pred": {}}
        for s in e3s:
            p = t.probs_torch(nets, s["x"])
            e3["models"][m]["pred"][s["name"]] = {"pred": [t.ROLES[int(i)] for i in p.argmax(1)][: s["n_face"]],
                                                   "conf": [round(float(v), 3) for v in p.max(1)][: s["n_face"]]}
        print("E3", m, len(e3s), "장면", flush=True)
    e3["_meta"]["end"] = now()
    rpe.dump(F["e3"], e3)
    meta["ended"] = now()
    meta["secs"] = round(time.perf_counter() - t_all, 1)
    rpe.dump(F["wall"], wall)
    rpe.dump(F["roles"], res)
    print("끝", meta["ended"], f"{meta['secs']}초 →", out)


# ---------------------------------------------------------------- rule(Dart 앱 규칙)
def cmd_rule(a) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    out = SMOKE if a.smoke else STEP2
    if a.dir:  # 확인용: 다른 폴더의 wall_responses.json(data/role/pair 기준 상대 또는 절대)
        out = Path(a.dir) if Path(a.dir).is_absolute() else PAIR / a.dir
    F = files_of(out)
    if not F["wall"].exists():
        raise SystemExit(f"입력 없음: {F['wall']}")
    if F["rule"].exists():
        raise SystemExit(f"이미 있음 — 덮지 않음: {F['rule']}")
    tl = subprocess.run(["tasklist"], capture_output=True, text=True, errors="replace").stdout.lower()
    if "flutter_tester" in tl:
        raise SystemExit("다른 flutter test(flutter_tester)가 돌고 있음 — 끝난 뒤 다시")
    rel = out.relative_to(ROOT).as_posix()
    env = dict(os.environ, ROLE_PAIR_DIR=rel)
    t0 = time.perf_counter()
    started = now()
    r = subprocess.run([str(FLUTTER), "test", "tool/role_pair_rule_test.dart"], cwd=ROOT, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    log = out / "log_rule.txt"
    # 앱 규칙은 작업 트리의 lib/ 를 쓴다(다른 세션이 고치는 중일 수 있음) — 규칙 파일의 커밋·변경 여부·해시를 남긴다
    import hashlib

    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    libs = []
    for f in ("lib/table/observation.dart", "lib/table/grid_zones.dart", "tool/role_pair_rule_test.dart"):
        p = ROOT / f
        dirty = bool(subprocess.run(["git", "-C", str(ROOT), "status", "--short", "--", f], capture_output=True, text=True).stdout.strip())
        libs.append(f"{f} sha256 {hashlib.sha256(p.read_bytes()).hexdigest()[:12]} 수정 {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(p.stat().st_mtime))}"
                    f"{' (커밋 전 변경)' if dirty else ''}")
    log.write_text(f"시작 {started} ROLE_PAIR_DIR={rel} 앱 HEAD {head}\n" + "\n".join(libs) + f"\n{r.stdout}\n{r.stderr}\nexit {r.returncode} {round(time.perf_counter() - t0, 1)}초\n", encoding="utf-8")
    print(r.stdout[-1500:], r.stderr[-1500:], "exit", r.returncode)
    if r.returncode != 0 or not F["rule"].exists():
        raise SystemExit(f"flutter test 실패 또는 출력 없음 — {log}")
    rule = json.loads(F["rule"].read_text(encoding="utf-8"))
    wall = json.loads(F["wall"].read_text(encoding="utf-8"))
    assert Path(rule["source"]).as_posix() == f"{rel}/wall_responses.json", rule["source"]
    assert set(rule["scenes"]) == set(wall["scenes"]), "장면 목록이 다름"
    print("rule_answers", len(rule["scenes"]), "장면 →", F["rule"])


# ---------------------------------------------------------------- 채점
def e1_scenes(path: Path) -> tuple[dict, dict]:
    """rpe.cv_roles 와 같은 셈을 장면별로: {장면: {역할: (맞음, 전체)}}, {장면: seat_ok}. 합계가 cv_roles 와 같은지 확인."""
    cv = json.loads(path.read_text(encoding="utf-8"))
    lab = json.loads(LABELS.read_text(encoding="utf-8"))
    per, seat = {}, {}
    for name, p in cv["per"].items():
        if not p["eval"]:
            continue
        seat[name] = bool(p["seat_ok"])
        items = lab[name]["items"]
        c = {r: [0, 0] for r in ROLES6}
        for i, pr in enumerate(p["pred"]):
            r = items[i]["role"]
            if r not in ROLES6:
                continue
            c[r][1] += 1
            c[r][0] += pr == r
        per[name] = c
    return per, seat


def boot_sum(diff: dict, n: int = 1000, seed: int = 0, level: float = 0.95) -> dict:
    """장면 묶음 부트스트랩(experiments/speed/stats.bootstrap_diff 와 같은 뽑기: 이름 정렬, random.Random(seed).choices(k=묶음 수), 분위 색인 같음).
    stats 는 비율(장면 평균·패 비율)을 내므로, 상자 수 차이(장면마다 수가 다름)를 합으로 내려고 같은 방식으로 직접 셈."""
    names = sorted(diff)
    rng = random.Random(seed)
    est = sum(diff[c] for c in names)
    draws = sorted(sum(diff[c] for c in rng.choices(names, k=len(names))) for _ in range(n))
    lo_q, hi_q = (1 - level) / 2, 1 - (1 - level) / 2
    lo, hi = draws[int(lo_q * (n - 1))], draws[int(round(hi_q * (n - 1)))]
    return {"est": est, "lo": lo, "hi": hi, "zero_in": lo <= 0 <= hi, "clusters": len(names), "n": n, "seed": seed}


def boot_check_stats(a_ok: dict, b_ok: dict, mine: dict) -> dict:
    """E2 차이를 stats.bootstrap_diff(장면 지표 × 장면 수)로 다시 내 같은지 확인."""
    import stats

    ra = [dict(key=(k, 1), cluster=k, ok=bool(v), hit=0, want=0, bad_auto=False, sec=0) for k, v in a_ok.items()]
    rb = [dict(key=(k, 1), cluster=k, ok=bool(v), hit=0, want=0, bad_auto=False, sec=0) for k, v in b_ok.items()]
    r = stats.bootstrap_diff(ra, rb)
    k = len(a_ok)
    got = {"est": r["scene"]["est"] * k, "lo": r["scene"]["lo"] * k, "hi": r["scene"]["hi"] * k}
    return {"stats_bootstrap_diff": got, "same": all(abs(got[x] - mine[x]) < 1e-9 for x in got)}


def e3_score(e3: dict, m: str) -> dict:
    ok, n = Counter(), Counter()
    pair_eq = pair_lab = nopair = nopair_2 = 0
    eq_names, bad_names, false_names = [], [], []
    for name, s in e3["scenes"].items():
        pred = e3["models"][m]["pred"][name]["pred"]
        lab = s["roles"]
        assert len(pred) == len(lab) == s["n_face"], name
        for r, p in zip(lab, pred):
            if r in ROLES6:
                n[r] += 1
                ok[r] += p == r
        lp = {i for i, r in enumerate(lab) if r == "pair"}
        pp = {i for i, p in enumerate(pred) if p == "pair"}
        if lp:
            pair_lab += 1
            if lp == pp:
                pair_eq += 1
                eq_names.append(name)
            else:
                bad_names.append([name, len(lp), len(pp), len(lp & pp)])
        else:
            nopair += 1
            if len(pp) >= 2:
                nopair_2 += 1
                false_names.append([name, len(pp)])
    return {"weights": e3["models"][m]["weights"], "n_scenes": len(e3["scenes"]), "roles": {r: f"{ok[r]}/{n[r]}" for r in ROLES6},
            "pair_set_equal": f"{pair_eq}/{pair_lab}", "nopair_pair2plus": f"{nopair_2}/{nopair}", "pair_set_bad": bad_names, "nopair_false": false_names}


def frac(s: str) -> tuple[int, int]:
    a, b = s.split("/")
    return int(a), int(b)


def judge_p(m: str, e1: dict, tot: dict) -> dict:
    """4-2 (p1)~(p4) 를 모델 m 에 대해. 분모가 고정값과 다르면 판정하지 않는다."""
    r = e1[m]["roles"]
    got = {k: frac(r[k])[1] for k in ("pair", "loose", "hand", "meld", "river")}
    got["seat"] = frac(e1[m]["seat"])[1]
    got["E2"] = tot["A"]["E2"]
    got["E4"] = tot["A"]["E4"]
    bad = {k: [got[k], v] for k, v in DENOM.items() if got[k] != v}
    out = {"model": m, "denominators": got}
    if bad:
        out["judged"] = False
        out["denominator_mismatch"] = bad
        return out
    pair_ok = frac(r["pair"])[0]
    wrong_hmr = sum(e1[m]["wrong"][k] for k in ("hand", "meld", "river"))
    loose_ok = frac(r["loose"])[0]
    seat_ok = frac(e1[m]["seat"])[0]
    A, M, MA = tot["A"], tot[m], tot[m + "+A"]
    p = {"p1": {"ok": pair_ok >= P1_PAIR, "why": f"E1 pair {pair_ok}/28 ≥ {P1_PAIR}"},
         "p2": {"ok": wrong_hmr <= P2_WRONG_HMR and loose_ok >= P2_LOOSE and seat_ok >= P2_SEAT,
                "why": f"hand·meld·river 틀림 합 {wrong_hmr} ≤ {P2_WRONG_HMR}, loose {loose_ok}/8 ≥ {P2_LOOSE}, 화료자 쪽 장면 {seat_ok}/26 ≥ {P2_SEAT}"},
         "p3": {"ok": M["ok"] >= A["ok"] and MA["ok"] > A["ok"], "why": f"E2 모델만 {M['ok']} ≥ A {A['ok']} 그리고 합친 값 {MA['ok']} > A {A['ok']}"},
         "p4": {"ok": M["false"] <= A["false"], "why": f"E4 헛 표시패 {M['false']} ≤ A {A['false']}"}}
    rows = []
    if all(v["ok"] for v in p.values()):
        rows.append("M 이 (p1)~(p4) 모두 충족 → 채택 후보 → 3단계")
    if p["p1"]["ok"] and p["p2"]["ok"] and not p["p3"]["ok"] and MA["ok"] == A["ok"]:
        rows.append("(p1)·(p2) 충족, (p3) 에서 A 와 같음(합친 값 = A) → 역할 모델만 갈아 끼울지 사용자가 정함, 표시패는 규칙 그대로")
    if not p["p2"]["ok"]:
        rows.append("(p2) 미달 → ❌ 미채택(지금 맞는 것을 깨뜨림)")
    if not p["p1"]["ok"]:
        rows.append("(p1) 미달 → ❌ 미채택")
    if not rows:
        rows.append("결정표에 딱 맞는 줄 없음 — " + ", ".join(k for k, v in p.items() if not v["ok"]) + " 미달")
    out.update(judged=True, p=p, decision_rows=rows)
    return out


def cmd_score(a) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    src = Path(a.dir) if a.dir else STEP2
    src = src if src.is_absolute() else (PAIR / src)
    dst = Path(a.out) if a.out else src
    dst = dst if dst.is_absolute() else (PAIR / dst)
    final = src == STEP2 and dst == STEP2
    S, D = files_of(src), files_of(dst)
    if dst.resolve() in {(PAIR / "step0").resolve(), (PAIR / "step1").resolve()}:
        raise SystemExit("step0·step1 에는 쓰지 않는다 — --out 을 다른 곳으로")
    for k in ("result", "table", "summary"):
        if D[k].exists():
            raise SystemExit(f"이미 있음 — 덮지 않음: {D[k]}")
    truth = json.loads(rpe.SCENES.read_text(encoding="utf-8"))
    rule = json.loads(S["rule"].read_text(encoding="utf-8"))
    wall = json.loads(S["wall"].read_text(encoding="utf-8"))
    if S["roles"].exists():
        rr = json.loads(S["roles"].read_text(encoding="utf-8"))
        run_meta = rr["_meta"]
        resp = {m: v["scenes"] for m, v in rr["models"].items()}
        model_times = {m: [v["start"], v["end"]] for m, v in rr["models"].items()}
    else:  # 0단계 산출물(m0_responses.json) — 표 모양 확인용
        m0 = json.loads((src / "m0_responses.json").read_text(encoding="utf-8"))
        run_meta = m0["_meta"]
        resp = {"M0": m0["scenes"]}
        model_times = {"M0": [m0["_meta"].get("M0_start"), m0["_meta"].get("M0_end")]}
    models = [m for m in ("M0", "M1", "M2") if m in resp]
    names = [r["name"] for r in truth["scenes"] if r["name"] in resp[models[0]]]

    # ---- E2·E4
    keys = ["A"] + models + [m + "+A" for m in models]
    tot = {k: Counter() for k in keys}
    staged = {k: Counter() for k in keys}
    rows = []
    for r in truth["scenes"]:
        n = r["name"]
        if n not in names:
            continue
        ra = rule["scenes"][n]
        a_ans = [x["tile"] for x in ra["tiles"]] or None
        row = {"name": n, "eval": r["eval"], "riichi": r["riichi"], "winner": r["winner"], "truth_pair": r["table_pair"], "truth_wall": r["wall"],
               "judged": r["eval"] == "E4" or (r["eval"] == "E2" and r["riichi"]),
               "A": rpe.judge(a_ans, r), "A_pairs": ra["pairs"], "A_has_sticks": ra["has_sticks"],
               "wall_server": [i["tile"] for i in wall["scenes"][n]["wall"]["indicators"]]}
        for m in models:
            x = resp[m][n]
            row[m] = rpe.judge(x["answer"], r)
            row[m + "_n_pair"] = x["n_pair"]
            row[m + "_reads"] = x["reads"]
            row[m + "_why"] = x["why"]
            row[m + "_weights"] = x["role_weights"]
            row[m + "_learned"] = x["learned"]
            row[m + "+A"] = rpe.judge(x["answer"] if x["answer"] is not None else a_ans, r)
        rows.append(row)
        bucket = tot if row["judged"] else staged
        for k in keys:
            c = bucket[k]
            c[r["eval"]] += 1
            if r["eval"] == "E2":
                c["ok"] += row[k]["ok"]
                c["ok_strict"] += row[k]["ok_strict"]
                c["wrong"] += row[k]["wrong"]
                c["none"] += row[k]["answer"] is None
            else:
                c["false"] += row[k]["false"]
                if k in models:
                    c["pair2plus"] += row[k + "_n_pair"] >= 2
                if k == "A":
                    c["pair2plus"] += bool(row["A_pairs"])  # A: read_wall 짝 묶음이 하나라도 있었던 장면(규칙 전, 참고)
            c["answered"] += row[k]["answer"] is not None
    summary = {k: {"E2_ok": f"{c['ok']}/{c['E2']}", "E2_ok_strict": f"{c['ok_strict']}/{c['E2']}", "E2_wrong": c["wrong"], "E2_none": c["none"],
                   "E4_false": f"{c['false']}/{c['E4']}", "E4_pair2plus_raw": c["pair2plus"] if (k in models or k == "A") else None} for k, c in tot.items()}
    staged_sum = {k: {"ok": f"{c['ok']}/{c['E2']}", "wrong": c["wrong"], "none": c["none"]} for k, c in staged.items()}

    # ---- E1
    e1, e1_per = {}, {}
    for m in models:
        p = V2 / f"cv_nostaged{TAGS[m]}.json"
        if not p.exists():
            continue
        e1[m] = rpe.cv_roles(p, LABELS)
        per, seat = e1_scenes(p)
        e1_per[m] = per
        for r6 in ROLES6:  # 장면별 합 = cv_roles
            assert f"{sum(v[r6][0] for v in per.values())}/{sum(v[r6][1] for v in per.values())}" == e1[m]["roles"][r6], (m, r6)
        assert f"{sum(seat.values())}/{len(seat)}" == e1[m]["seat"]

    # ---- E3
    e3 = {}
    if S["e3"].exists():
        e3d = json.loads(S["e3"].read_text(encoding="utf-8"))
        e3 = {m: e3_score(e3d, m) for m in models if m in e3d["models"]}
        e3["_meta"] = e3d["_meta"]

    # ---- 부트스트랩(장면 묶음 1,000회, 씨드 0)
    smoke = "M1" not in models
    M1 = "M1" if not smoke else "M0"  # 연기: M0 를 M1 자리에 — 코드만 지나가게, 판정 아님
    M2 = "M2" if "M2" in models else M1
    boot = {"_note": "연기 — M1·M2 자리에 M0, 판정 아님" if smoke else "장면 묶음 복원 추출 1,000회, 씨드 0, 95% 구간(stats.bootstrap_diff 와 같은 뽑기)"}

    def e1_pair_diff(b, a_):
        return {n: e1_per[b][n]["pair"][0] - e1_per[a_][n]["pair"][0] for n in e1_per[a_]}

    if M1 in e1_per and "M0" in e1_per:
        boot["E1_pair_M1-M0"] = boot_sum(e1_pair_diff(M1, "M0"))
    if M2 in e1_per and M1 in e1_per:
        boot["E1_pair_M2-M1"] = boot_sum(e1_pair_diff(M2, M1))
    e2rows = [r for r in rows if r["judged"] and r["eval"] == "E2"]
    a_ok = {r["name"]: int(r["A"]["ok"]) for r in e2rows}
    for lab, k in (("E2_M1-A", M1), ("E2_M1+A-A", M1 + "+A")):
        b_ok = {r["name"]: int(r[k]["ok"]) for r in e2rows}
        boot[lab] = boot_sum({n: b_ok[n] - a_ok[n] for n in a_ok})
        boot[lab]["check"] = boot_check_stats(a_ok, b_ok, boot[lab])

    # ---- 판정
    decision = {"_note": boot["_note"]}
    if M1 in e1:
        decision["M1"] = judge_p(M1, e1, tot)
        if smoke:
            decision["M1"]["stand_in"] = "M0"
    m2_better = "E1_pair_M2-M1" in boot and not smoke and boot["E1_pair_M2-M1"]["lo"] > 0
    decision["M2_better_than_M1"] = {"value": m2_better, "why": "조건 = E1 pair M2 − M1 구간 하한 > 0" if "E1_pair_M2-M1" in boot else "M2 없음",
                                     "interval": boot.get("E1_pair_M2-M1")}
    if m2_better:
        decision["M2"] = judge_p("M2", e1, tot)
    decision["judged_model"] = "M2" if m2_better else M1

    res = {"made": now(), "final": final and not smoke, "src": str(src), "run_meta": run_meta, "model_times": model_times, "rule_made": rule["made"],
           "rule_source": rule["source"], "rule": {"pair_min": rpe.PAIR_MIN, "pair_max": rpe.PAIR_MAX, "conf_min": rpe.CONF_MIN},
           "summary": summary, "staged_k25_k28": staged_sum, "e1": e1, "e3": e3, "bootstrap": boot, "decision": decision, "rows": rows,
           "learned_any": [r["name"] for r in rows for m in models
                           if not r[m + "_learned"]["role"].startswith("아니오") or not r[m + "_learned"]["det_cls"].startswith("아니오")]}
    dst.mkdir(parents=True, exist_ok=True)
    rpe.dump(D["result"], res)
    D["table"].write_text(scene_table(rows, models), encoding="utf-8")
    D["summary"].write_text(summary_table(res, models), encoding="utf-8")
    print(D["summary"].read_text(encoding="utf-8"))
    print("→", D["result"], D["table"], D["summary"])


# ---------------------------------------------------------------- 표
def _mark(x: dict, ev: str) -> str:
    if ev == "E2":
        return "✅" if x["ok"] else ("❌ 틀림" if x["wrong"] else "— 답 없음")
    return "⚠ 헛 표시패" if x["false"] else "·"


def _ts(ts) -> str:
    return " ".join(ts) if ts else "-"


def scene_table(rows: list, models: list) -> str:
    head = ["장면", "E", "화료자·리치", "탁자 위 짝 정답", "패산 위 정답", "A 답", "A"]
    for m in models:
        head += [f"{m} pair 수", f"{m} 답(읽기 확신)", m, f"{m}+A"]
    out = ["| " + " | ".join(head) + " |", "| " + " | ".join("---" for _ in head) + " |"]
    for r in rows:
        ev = r["eval"] + ("" if r["judged"] else " 연출(판정 밖)")
        cells = [r["name"], ev, f"{r['winner']}·{'리치' if r['riichi'] else '-'}", _ts(r["truth_pair"]), _ts(r["truth_wall"]),
                 _ts(r["A"]["answer"]) if r["A"]["answer"] else "없음", _mark(r["A"], r["eval"])]
        for m in models:
            rd = ", ".join(f"{x['tile']} {x['conf']:.2f}" for x in r[m + "_reads"])
            ans = (_ts(r[m]["answer"]) + f" ({rd})") if r[m]["answer"] else ((r[m + "_why"] or "") + (f" ({rd})" if rd else ""))
            cells += [str(r[m + "_n_pair"]), ans, _mark(r[m], r["eval"]), _mark(r[m + "+A"], r["eval"])]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


def summary_table(res: dict, models: list) -> str:
    L = [f"# 2단계 채점 표 ({res['made']}, {'본 채점' if res['final'] else '연기·확인용 — 판정 아님'})", ""]
    rm = res["run_meta"]
    L.append(f"- 실행: 시작 {rm.get('started')} · A {rm.get('A_start')}~{rm.get('A_end')} · "
             + " · ".join(f"{m} {a}~{b}" for m, (a, b) in res["model_times"].items()) + f" · 끝 {rm.get('ended', '-')} · 서버 {rm.get('recognizer')}")
    L.append(f"- 규칙: pair {res['rule']['pair_min']}~{res['rule']['pair_max']}장, 확신 {res['rule']['conf_min']}, 적5 = 5. A = `{res['rule_source']}` 에 localPairIndicators ({res['rule_made']})")
    L.append("")
    L.append("## E1 테스트 겹 상자(4겹 나눔, 26장면)")
    L.append("")
    L.append("| 모델 | cv 파일 | " + " | ".join(ROLES6) + " | hand·meld·river 틀림 합 | 화료자 쪽 장면 |")
    L.append("| --- | --- | " + " | ".join("---" for _ in ROLES6) + " | --- | --- |")
    for m, v in res["e1"].items():
        L.append(f"| {m} | {v['file']} | " + " | ".join(v["roles"][r] for r in ROLES6)
                 + f" | {sum(v['wrong'][k] for k in ('hand', 'meld', 'river'))} | {v['seat']} |")
    L.append("")
    L.append("## E2(리치 화료 + 탁자 위 짝, 18장면)·E4(짝 없는 장면)")
    L.append("")
    L.append("| 답 | E2 맞음 | E2 맞음(적5 가름) | E2 틀린 답 | E2 답 없음 | E4 헛 표시패 | E4 규칙 전 참고(모델: pair 2장 이상 낸 장면 · A: read_wall 짝 묶음이 있던 장면) |")
    L.append("| --- | --- | --- | --- | --- | --- | --- |")
    for k, v in res["summary"].items():
        L.append(f"| {k} | {v['E2_ok']} | {v['E2_ok_strict']} | {v['E2_wrong']} | {v['E2_none']} | {v['E4_false']} | {'' if v['E4_pair2plus_raw'] is None else v['E4_pair2plus_raw']} |")
    L.append("")
    L.append("연출 k25·k28(리치 아님, 판정 밖): " + " · ".join(f"{k} {v['ok']}(틀림 {v['wrong']}, 없음 {v['none']})" for k, v in res["staged_k25_k28"].items()))
    L.append("")
    if res["e3"]:
        L.append(f"## E3 11-14 개발 공개 장면(참고, 판정에 안 씀 — 라벨 상자 토큰, all.pt, {res['e3']['_meta']['n_scenes']}장면)")
        L.append("")
        L.append("| 모델 | " + " | ".join(ROLES6) + " | pair 집합 = 라벨 | 짝 라벨 없는 장면에서 pair ≥ 2 |")
        L.append("| --- | " + " | ".join("---" for _ in ROLES6) + " | --- | --- |")
        for m in models:
            if m in res["e3"]:
                v = res["e3"][m]
                L.append(f"| {m} | " + " | ".join(v["roles"][r] for r in ROLES6) + f" | {v['pair_set_equal']} | {v['nopair_pair2plus']} |")
        L.append("")
    L.append(f"## 부트스트랩 ({res['bootstrap']['_note']})")
    L.append("")
    L.append("| 차이 | 점 추정 | 95% 구간 | 0 포함 | 묶음 |")
    L.append("| --- | --- | --- | --- | --- |")
    for k, v in res["bootstrap"].items():
        if k.startswith("_"):
            continue
        chk = "" if "check" not in v else (" (stats 와 같음)" if v["check"]["same"] else " (stats 와 다름!)")
        L.append(f"| {k} | {v['est']:+d} | [{v['lo']:+d}, {v['hi']:+d}] | {'예' if v['zero_in'] else '아니오'} | {v['clusters']}{chk} |")
    L.append("")
    d = res["decision"]
    L.append(f"## 판정 ({d['_note']})")
    L.append("")
    L.append(f"- M2 가 E1 에서 M1 보다 나음(구간 0 미포함): {d['M2_better_than_M1']['value']} — {d['M2_better_than_M1']['why']}. 판정 모델: {d['judged_model']}")
    for m in ("M1", "M2"):
        if m not in d:
            continue
        j = d[m]
        L.append(f"- **{m}{' (자리에 ' + j['stand_in'] + ')' if j.get('stand_in') else ''}**")
        if not j["judged"]:
            L.append(f"  - 판정 안 함 — 분모가 다름: {j['denominator_mismatch']}")
            continue
        for k, v in j["p"].items():
            L.append(f"  - ({k}) {'참' if v['ok'] else '거짓'}: {v['why']}")
        for row in j["decision_rows"]:
            L.append(f"  - 결정표: {row}")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "rule", "score"])
    ap.add_argument("--smoke", action="store_true", help="run·rule: 장면 2개, A + M0 만, step2/smoke/")
    ap.add_argument("--dir", help="score: 읽을 폴더(data/role/pair 기준 상대 또는 절대, 기본 step2)")
    ap.add_argument("--out", help="score: 쓸 폴더(기본 --dir 과 같음)")
    a = ap.parse_args()
    {"run": cmd_run, "rule": cmd_rule, "score": cmd_score}[a.cmd](a)
