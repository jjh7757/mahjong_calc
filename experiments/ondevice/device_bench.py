"""태블릿 앱 안 기기 판독(exp/on-device-read)을 테스트 세트로 잰다 — 앱 데이터는 건드리지 않는다(adb install -r 로 깐 실험 APK 전제).

  python -I -X utf8 experiments/ondevice/device_bench.py push           사진(B·C·D + 10-31 + 11-07 원본 40장)·manifest 를 앱 외부 파일 폴더에
  python -I -X utf8 experiments/ondevice/device_bench.py run <TAG>      앱을 띄우고 브로드캐스트 → 결과 기다려 받기 → 채점·PC 답과 비교
  python -I -X utf8 experiments/ondevice/device_bench.py flow <TAG> [반복]  앱 흐름(readGrid → 병합 → 점수)을 스위치 끔(운영 서버)·켬(기기) 번갈아

질의는 robust_suite run(prod, orig)과 같다: /v2/localroles side·격자(x1·x2·y1·y2)·mode=hybrid, frame·grid_src 없음.
비교 기준은 같은 사진의 PC 결과 experiments/speed/results/robust_prod_ondev_pc_1111.json(서버 348f0f9 코드·PC onnxruntime·진짜 cv2).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "speed"))
os.environ.setdefault("MSYS_NO_PATHCONV", "1")
ADB = "C:/Users/jjh7757/dev/android-sdk/platform-tools/adb.exe"
PKG = "dev.jjh.mahjong_calc.ondevice"  # 사본 앱(applicationIdSuffix .ondevice), 클래스는 원래 패키지
CLS = "dev.jjh.mahjong_calc"
DEV_DIR = f"/sdcard/Android/data/{PKG}/files/bench"
STAGE = HERE / "build" / "bench"
PC_REF = ROOT / "experiments" / "speed" / "results" / "robust_prod_ondev_pc_1111.json"


def adb(*a: str, check: bool = True) -> str:
    r = subprocess.run([ADB, *a], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise SystemExit(f"adb {' '.join(a)} 실패: {r.stderr.strip()}")
    return r.stdout


def scenes():
    import robust_suite as rs

    meta = json.loads((rs.RB / "meta.json").read_text(encoding="utf-8"))["orig"]
    return [(s, meta[s["name"]]) for s in rs.scenes("dev") if s["name"] in meta]


def push() -> None:
    STAGE.mkdir(parents=True, exist_ok=True)
    # 폴더는 앱이 만들어야 앱이 읽는다(셸이 만들면 셸 소유) — 앱을 띄우고 이름 없이 브로드캐스트.
    adb("shell", "am", "start", "-n", f"{PKG}/{CLS}.MainActivity")
    time.sleep(3)
    adb("shell", "am", "broadcast", "-n", f"{PKG}/{CLS}.OnDeviceBenchReceiver")
    time.sleep(1)
    items = []
    for s, info in scenes():
        src = Path(info["src"])
        name = s["name"]
        dev = f"{DEV_DIR}/{name}.jpg"
        adb("push", str(src), dev)
        g = s["grid"]
        q = {"side": s["side"], "x1": str(g["x1"]), "x2": str(g["x2"]), "y1": str(g["y1"]), "y2": str(g["y2"]), "mode": "hybrid"}
        if g.get("sticks"):
            q["sticks"] = ",".join(str(v) for v in g["sticks"])
        items.append({"name": name, "kind": "localroles", "images": [dev], "query": q})
    man = {"tag": "x", "items": items}
    (STAGE / "manifest.json").write_text(json.dumps(man, ensure_ascii=False), encoding="utf-8")
    print(f"사진 {len(items)}장 올림 → {DEV_DIR}")


def run(tag: str) -> None:
    man = json.loads((STAGE / "manifest.json").read_text(encoding="utf-8"))
    man["tag"] = tag
    if os.environ.get("PREP"):  # PREP=skip 이면 받은 JPEG 그대로(서버 prepare_image 재저장 생략)
        man["prep"] = os.environ["PREP"]
    if os.environ.get("PROFILE"):  # PROFILE=<장수> 면 앞 몇 장만 cProfile
        man["profile"], man["limit"] = True, int(os.environ["PROFILE"])
    p = STAGE / f"manifest_{tag}.json"
    p.write_text(json.dumps(man, ensure_ascii=False), encoding="utf-8")
    adb("push", str(p), f"{DEV_DIR}/manifest_{tag}.json")
    adb("shell", "am", "start", "-n", f"{PKG}/{CLS}.MainActivity")
    time.sleep(3)
    adb("logcat", "-c")
    adb("shell", "am", "broadcast", "-n", f"{PKG}/{CLS}.OnDeviceBenchReceiver", "--es", "manifest", f"manifest_{tag}.json")
    t0 = time.time()
    while time.time() - t0 < 1800:
        log = adb("logcat", "-d", "-s", "ondevice-bench:*", "python.stderr:*", "AndroidRuntime:E", check=False)
        if "done {" in log or "failed" in log:
            print(log[-3000:])
            break
        time.sleep(5)
    else:
        raise SystemExit("30분 안에 안 끝남")
    out = HERE / "results" / f"device_{tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    adb("pull", f"{DEV_DIR}/result_{tag}.json", str(out))
    if os.environ.get("PROFILE"):
        print(json.loads(out.read_text(encoding="utf-8")).get("profile", "")[:12000])
        return
    score(out)


def score(path: Path) -> None:
    import numpy as np
    import robust_suite as rs

    res = json.loads(path.read_text(encoding="utf-8"))
    ref = json.loads(PC_REF.read_text(encoding="utf-8"))["orig"]
    by = {it["name"]: it for it in res["items"]}
    n = ok = hit = want = unsafe = bad = diff = err = 0
    secs, work = [], []
    diffs = []
    for s, _ in scenes():
        it = by.get(s["name"])
        if it is None:
            continue
        w = s["w"]
        if it["err"] or it["res"] is None:
            err += 1
            continue
        o = it["res"]
        hand_t = o["tiles"] + ([o["separate_tile"]] if o.get("separate_tile") else [])
        hand = [t["tile"] for t in hand_t]
        melds = [" ".join(m["tiles"]) for m in o["melds"]]
        j = rs.judge(hand, melds, o.get("block", False), s["hand"], s["melds"])
        n += w
        ok += w * j["ok"]
        hit += w * j["hit"]
        want += w * j["want"]
        unsafe += w * j["unsafe"]
        bad += w * j["bad_auto"]
        r = ref.get(s["name"])
        if r and (r["hand"] != hand or r["melds"] != melds or bool(r["block"]) != bool(o.get("block", False))):
            diff += 1
            diffs.append((s["name"], r["hand"], hand, r["melds"], melds))
        secs.append(it["secs"])
        work.append(o.get("ondevice", {}).get("total_ms", 0) / 1000)

    def q(a):
        a = np.array(a)
        return f"{np.median(a):.2f} / {np.percentile(a, 90):.2f} / {a.max():.2f}" if len(a) else "-"

    print(f"warmup {res['warmup']}  전체 {res['total_s']}s")
    print(f"장면 맞음 {ok}/{n} · 패 {hit}/{want} · unsafe {unsafe} · 틀린 자동 {bad} · 오류 {err} · PC 와 답 다른 사진 {diff}/{len(secs) + err}")
    print(f"사진당 observe(디코딩 포함) {q(secs)} 초 · 그중 판독 {q(work)} 초")
    for d in diffs:
        print("  다름", d)



# ---------------------------------------------------------------- 앱 흐름(Dart readGrid → 병합 → 점수), 스위치 끔(운영 서버)·켬(기기) 번갈아
def flow(tag: str, repeat: int = 1, modes: tuple[str, ...] = ("server", "device")) -> None:
    """push 로 올린 사진(같은 40장)을 앱 흐름으로. 같은 사진을 server → device 순서로 바로 이어서(같은 시각 비교)."""
    items = []
    for s, _ in scenes():
        g = {k: s["grid"][k] for k in ("x1", "x2", "y1", "y2")}
        if s["grid"].get("sticks"):
            g["sticks"] = list(s["grid"]["sticks"])
        items.append({"name": s["name"], "path": f"/storage/emulated/0/Android/data/{PKG}/files/bench/{s['name']}.jpg", "grid": g})
    man = {"tag": tag, "repeat": repeat, "modes": list(modes), "items": items}
    p = STAGE / f"flow_{tag}.json"
    p.write_text(json.dumps(man, ensure_ascii=False), encoding="utf-8")
    adb("push", str(p), f"{DEV_DIR}/flow_{tag}.json")
    adb("shell", "am", "start", "-n", f"{PKG}/{CLS}.MainActivity")
    time.sleep(4)
    adb("logcat", "-c")
    adb("shell", "am", "broadcast", "-n", f"{PKG}/{CLS}.OnDeviceBenchReceiver", "--es", "flow", f"flow_{tag}.json")
    t0 = time.time()
    while time.time() - t0 < 3600:
        log = adb("logcat", "-d", "-s", "ondevice-bench:*", "flutter:I", check=False)
        if "flow done" in log or "flow failed" in log:
            print("\n".join(l for l in log.splitlines() if "ondevice-bench" in l)[-2000:])
            break
        time.sleep(10)
    else:
        raise SystemExit("1시간 안에 안 끝남")
    out = HERE / "results" / f"flow_device_{tag}.jsonl"
    adb("pull", f"{DEV_DIR}/flow_{tag}.jsonl", str(out))
    flow_score(out)


def flow_score(path: Path) -> None:
    import numpy as np
    import flow_visit as fv
    import seat_grow as sg

    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    ev = {(s["name"] if s["set"] == "bcd" else s["name"][-6:]): s for s in sg.eval_scenes()}
    by_name = {s["name"]: k for k, s in ev.items()}
    w = {s["name"]: s["w"] for s, _ in scenes()}
    stat: dict = {}
    ans: dict = {}
    for r in rows:
        mode = r["mode"]
        st = stat.setdefault(mode, {"n": 0, "ok": 0, "auto": 0, "bad_auto": 0, "err": 0, "t": [], "calls": {}})
        key = by_name.get(r["name"])
        m = r.get("merge") or {}
        if r.get("error") or key is None:
            st["err"] += 1
            print("오류", mode, r["name"], r.get("error"))
            continue
        t = fv.truth_of(key, ev)
        closed = sorted(m.get("closed") or [])
        melds = fv.norm_melds(m.get("melds") or [])
        valid = bool(m.get("hand_valid"))
        if t["win"] is None:
            rest = list(closed)
            if m.get("win_tile") in rest and len(closed) + 3 * len(melds) == 14:
                rest.remove(m["win_tile"])
            ok = melds == t["melds"] and valid and (closed == t["hand"] or rest == t["hand"])
        else:
            ok = melds == t["melds"] and valid and closed == t["closed"] and m.get("win_tile") == t["win"]
        wt = w.get(r["name"], 1)
        st["n"] += wt
        st["ok"] += wt * ok
        auto = r.get("auto_block") is None
        st["auto"] += wt * auto
        st["bad_auto"] += wt * (auto and not ok)
        st["t"].append(r["total_ms"] / 1000)
        for k, v in (r.get("call_ms") or {}).items():
            st["calls"].setdefault(k, []).append(v / 1000)
        ans.setdefault(r["name"], {})[mode] = (closed, melds, m.get("win_tile"), r.get("points"), sorted(m.get("dora_indicators") or []), r.get("auto_block"))

    def q(a):
        a = np.array(a)
        return f"{np.median(a):.2f} / {np.percentile(a, 90):.2f} / {a.max():.2f}" if len(a) else "-"

    for mode, st in stat.items():
        print(f"[{mode}] 맞음(손패·울기·화료패) {st['ok']}/{st['n']} · 자동 반영 {st['auto']} · 그중 틀림 {st['bad_auto']} · 오류 {st['err']} · 장면 {q(st['t'])} 초")
        for k, v in sorted(st["calls"].items()):
            print(f"    {k}: {q(v)}")
    modes = list(stat)
    for other in modes[1:]:
        diff = [n for n, d in ans.items() if modes[0] in d and other in d and str(d[modes[0]]) != str(d[other])]
        print(f"{modes[0]} 대 {other}: 답(손패·울기·화료패·점수·표시패·자동 막음) 다른 사진 {len(diff)}/{len(ans)}")
        for n in diff:
            print("  ", n, ans[n][modes[0]], ans[n][other])

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "push":
        push()
    elif cmd == "run":
        run(sys.argv[2])
    elif cmd == "score":
        score(Path(sys.argv[2]))
    elif cmd == "flow":  # flow <TAG> [반복] [모드,모드…]
        flow(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 1,
             tuple(sys.argv[4].split(",")) if len(sys.argv) > 4 else ("server", "device"))
    elif cmd == "flow_score":
        flow_score(Path(sys.argv[2]))
