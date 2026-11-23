"""11-14 추적 프레임을 태블릿의 기기 판독(`ondevice.overlay`, 사본 앱 OnDeviceBenchReceiver)으로 다시 읽혀 버림 기록기를 채점한다(2026-11-17).

PC 재생(표 12-29, `overlay_dump.py` → `replay_recorder.dart` → `heldout_1114.py score`)과 입력 · 기록기 · 채점이 같고, 판독을 돌리는 곳만 태블릿이다.
저장소 루트에서:
  python -X utf8 experiments/paifu_frames/device_replay.py make            프레임을 꺼내 놓고 목록 · manifest 를 만든다(adb 안 씀)
  python -X utf8 experiments/paifu_frames/device_replay.py pc [묶음…]      같은 manifest 를 PC 파이썬 `ondevice.bench` 로(절차 확인용)
  python -X utf8 experiments/paifu_frames/device_replay.py push            프레임을 사본 앱 bench 폴더에 올린다(이미 있는 것은 건너뜀)
  python -X utf8 experiments/paifu_frames/device_replay.py run [묶음…]     묶음마다 manifest → 브로드캐스트 → 결과 받기, 30초마다 발열 · 배터리
  python -X utf8 experiments/paifu_frames/device_replay.py score device|pc 결과 → overlay_dump 꼴 → 기록기 재생 → 채점
  python -X utf8 experiments/paifu_frames/device_replay.py pace  device    앞 판독이 안 끝났을 때 온 프레임은 건너뛴 것으로 치고 다시 채점(실제 속도 흉내)

묶음 = 추적 폴더 하나(앱이 받은 그대로 — 지난 국 끝 탁자에서 시작한 r12 · r14 · r19 는 자르지 않은 full). 긴 변 1600 미만 프레임은 앱이 안 읽으므로 뺀다.
`heldout_1114.py` · `replay_recorder.dart` · `overlay_dump.py` 는 고치지 않는다(가져다 쓰기만). 결과는 `results/device_1117/`.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "experiments" / "ondevice"))
os.environ.setdefault("MSYS_NO_PATHCONV", "1")

import heldout_1114 as ho  # noqa: E402  (판 정의 · 채점 — import 만)

OUT = HERE / "results" / "device_1117"
STAGE = ROOT / "experiments" / "ondevice" / "build" / "bench" / "p1114"
DART = "C:/Users/jjh7757/flutter/bin/dart.bat"
PRE = "p1114_"  # 기기 bench 폴더 안의 파일 이름 머리(폴더를 셸이 만들면 앱이 못 읽어 한 폴더에 편다)

# 묶음: 잘라 쓴 세 판은 full 이름으로(프레임이 더 많은 쪽), 나머지는 그대로. 참고 판 h08 은 뺀다.
UNITS = [k.replace("_", "full_", 1) if k in ho.T0 else k for k in ho.EVAL]


def jl(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def dump(p, o):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(o, ensure_ascii=False), encoding="utf-8")


def unit_frames(unit: str):
    """overlay_dump.py 와 같은 고르기(t0 · t1) + 긴 변 1600 이상만. → [(zip 격자, 프레임 정보, 바이트)]"""
    from PIL import Image

    r = jl(ho.OUT / "truth_heldout.json")[unit]
    track = (HERE / r["track"]).resolve()
    t0, t1 = r.get("t0"), r.get("t1")
    for z in sorted(track.glob("frames_*.zip")):
        zf = zipfile.ZipFile(z)
        meta = json.loads(zf.read("frames.json"))
        for f in meta["frames"]:
            hms = f["at"][11:19]
            if (t0 and hms < t0) or (t1 and hms > t1):
                continue
            raw = zf.read(f["file"])
            w, h = Image.open(io.BytesIO(raw)).size
            if max(w, h) < 1600:
                continue
            yield meta["grid"], dict(file=f["file"], at=f["at"], w=w, h=h), raw


def make():
    STAGE.mkdir(parents=True, exist_ok=True)
    import device_bench as db

    index, n, nbytes = {}, 0, 0
    for u in UNITS:
        frames, items_dev, items_pc, grid0 = [], [], [], None
        for grid, f, raw in unit_frames(u):
            grid0 = grid0 or grid
            fn = f"{PRE}{u}__{f['file'].replace('/', '_')}"
            p = STAGE / fn
            if not p.exists() or p.stat().st_size != len(raw):
                p.write_bytes(raw)
            q = {k: str(grid[k]) for k in ("x1", "x2", "y1", "y2")}
            frames.append(dict(f, stage=fn))
            items_dev.append({"name": f["file"], "kind": "overlay", "images": [f"{db.DEV_DIR}/{fn}"], "query": q})
            items_pc.append({"name": f["file"], "kind": "overlay", "images": [str(p)], "query": q})
            n += 1
            nbytes += len(raw)
        index[u] = {"grid": grid0, "frames": frames}
        dump(STAGE / f"manifest_{PRE}{u}.json", {"tag": f"{PRE}{u}", "items": items_dev})
        dump(STAGE / f"manifest_pc_{PRE}{u}.json", {"tag": f"pc_{PRE}{u}", "items": items_pc})
        print(u, len(frames), "장")
    dump(STAGE / "index.json", index)
    print(f"합 {n}장 {nbytes / 1e6:.0f}MB → {STAGE}")


def pc(units):
    sys.path.insert(0, "C:/Users/jjh7757/dev/mahjong-recognizer")
    sys.path.append(str(ROOT / "android/app/src/main/python"))
    import ondevice

    for u in units or UNITS:
        m = STAGE / f"manifest_pc_{PRE}{u}.json"
        r = json.loads(ondevice.bench(str(m)))
        (OUT / "raw").mkdir(parents=True, exist_ok=True)
        shutil.move(r["path"], OUT / "raw" / f"pc_{u}.json")
        print(u, r["n"], "장", r["total_s"], "초")


def push():
    import device_bench as db

    db.adb("shell", "am", "start", "-n", f"{db.PKG}/{db.CLS}.MainActivity")
    time.sleep(3)
    db.adb("shell", "am", "broadcast", "-n", f"{db.PKG}/{db.CLS}.OnDeviceBenchReceiver")
    time.sleep(1)
    have = {}
    for line in db.adb("shell", "ls", "-l", db.DEV_DIR, check=False).splitlines():
        p = line.split()
        if len(p) >= 8 and p[-1].startswith(PRE):
            have[p[-1]] = int(p[4])
    idx = jl(STAGE / "index.json")
    todo = [f["stage"] for u in UNITS for f in idx[u]["frames"] if have.get(f["stage"]) != (STAGE / f["stage"]).stat().st_size]
    print(f"올릴 것 {len(todo)}장(이미 있음 {sum(len(idx[u]['frames']) for u in UNITS) - len(todo)})", flush=True)
    t0 = time.time()
    for i, fn in enumerate(todo):
        db.adb("push", str(STAGE / fn), f"{db.DEV_DIR}/{fn}")
        if i % 50 == 49:
            print(f"  {i + 1}/{len(todo)} {time.time() - t0:.0f}초", flush=True)
    print("올림 끝", f"{time.time() - t0:.0f}초")


def heat_line(db) -> dict:
    th = db.adb("shell", "dumpsys", "thermalservice", check=False)
    cur = th.split("Current cooling")[0].split("Current temperatures from HAL")[-1]
    temps = {m.group(2): float(m.group(1)) for m in re.finditer(r"Temperature\{mValue=([\d.]+), mType=\d+, mName=(\w+)", cur)}
    st = re.search(r"Thermal Status: (\d+)", th)
    b = db.adb("shell", "dumpsys", "battery", check=False)

    def g(k):
        m = re.search(rf"\n\s*{k}: (-?\d+)", b)
        return int(m.group(1)) if m else None

    return dict(at=datetime.now().isoformat(timespec="seconds"), status=int(st.group(1)) if st else None, temps=temps,
                level=g("level"), bat_temp=g("temperature"), plugged=g("AC powered") or g("USB powered"), raw_status=g("status"))


def run(units):
    import device_bench as db

    (OUT / "raw").mkdir(parents=True, exist_ok=True)
    heat = OUT / "heat_device.jsonl"

    def note(extra):
        with open(heat, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(heat_line(db), **extra), ensure_ascii=False) + "\n")

    for u in units or UNITS:
        tag = f"{PRE}{u}"
        db.adb("push", str(STAGE / f"manifest_{tag}.json"), f"{db.DEV_DIR}/manifest_{tag}.json")
        db.adb("shell", "rm", "-f", f"{db.DEV_DIR}/result_{tag}.json", check=False)
        db.adb("shell", "input", "keyevent", "KEYCODE_WAKEUP", check=False)
        db.adb("shell", "am", "start", "-n", f"{db.PKG}/{db.CLS}.MainActivity")
        time.sleep(3)
        db.adb("logcat", "-c")
        note({"unit": u, "ev": "start"})
        db.adb("shell", "am", "broadcast", "-n", f"{db.PKG}/{db.CLS}.OnDeviceBenchReceiver", "--es", "manifest", f"manifest_{tag}.json")
        t0 = last = time.time()
        while time.time() - t0 < 3600:
            log = db.adb("logcat", "-d", "-s", "ondevice-bench:*", "python.stderr:*", "AndroidRuntime:E", check=False)
            if "done {" in log or "failed" in log:
                print(u, log.strip().splitlines()[-1][-300:], flush=True)
                break
            if time.time() - last >= 30:
                last = time.time()
                note({"unit": u})
            time.sleep(5)
        else:
            raise SystemExit(f"{u}: 60분 안에 안 끝남")
        note({"unit": u, "ev": "end", "secs": round(time.time() - t0)})
        db.adb("pull", f"{db.DEV_DIR}/result_{tag}.json", str(OUT / "raw" / f"device_{u}.json"))


def heat(out: str, secs: str):
    """30초마다 발열 · 배터리 한 줄. 거치 화면은 화면을 켜 두지 않으므로(헤드 화면만 켜 둠) 5분마다 깨움 키를 보내 화면 꺼짐(30분)을 막는다."""
    import device_bench as db

    end, last_key = time.time() + float(secs), 0.0
    while time.time() < end:
        t = time.time()
        extra = {}
        if t - last_key >= 300:
            # KEYCODE_WAKEUP 은 켜진 화면의 꺼짐 타이머를 못 되돌린다(11-17 에 그래서 꺼짐). shift(59)는 되돌린다(dumpsys power lastUserActivityTime 로 확인).
            db.adb("shell", "input", "keyevent", "59", check=False)
            last_key, extra = t, {"ev": "shift_key"}
        pw = db.adb("shell", "dumpsys", "power", check=False)
        m = re.search(r"mWakefulness=(\w+)", pw)
        with open(out, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(heat_line(db), wake=m.group(1) if m else None, **extra), ensure_ascii=False) + "\n")
        time.sleep(max(0.0, 30 - (time.time() - t)))


def to_dumps(src: str, root: Path, keep=None) -> dict:
    """결과 → `overlay_dump.json` 꼴(판 이름마다). keep(unit, [프레임+결과]) 이 있으면 그것이 남길 프레임을 고른다."""
    idx = jl(STAGE / "index.json")
    stats = {}
    for u in UNITS:
        p = OUT / "raw" / f"{src}_{u}.json"
        if not p.exists():
            print(u, "결과 없음")
            continue
        by = {it["name"]: it for it in jl(p)["items"]}
        frames, errs = [], 0
        for f in idx[u]["frames"]:
            it = by.get(f["file"])
            if it is None or it["err"] or it["res"] is None:
                errs += 1
                continue
            frames.append({"file": f["file"], "at": f["at"], "w": f["w"], "h": f["h"], "tiles": it["res"]["tiles"], "ms": it["res"]["ms"], "secs": it["secs"]})
        all_n = len(frames)
        if keep:
            frames = keep(u, frames)
        stats[u] = dict(n=all_n, kept=len(frames), err=errs, secs=[f["secs"] for f in frames])
        dump(root / "results" / u / "overlay_dump.json", {"grid": idx[u]["grid"], "frames": frames})
        base = u.replace("full_", "_", 1)
        if base != u:  # 잘라 쓴 판: t0 부터(프레임마다 따로 읽으므로 거르기만 하면 된다 — heldout_1114.cut 과 같음)
            cutf = [f for f in frames if f["at"][11:19] >= ho.T0[base]]
            dump(root / "results" / base / "overlay_dump.json", {"grid": idx[u]["grid"], "frames": cutf})
    return stats


def replay_and_score(root: Path, label: str, stats: dict):
    rounds = {k: v for k, v in jl(ho.OUT / "rounds.json").items() if k not in ho.REF}
    dump(root / "heldout" / "rounds.json", rounds)
    for name, e in rounds.items():
        d = root / "results" / name / "overlay_dump.json"
        if not d.exists():
            continue
        r = subprocess.run([DART, "run", "experiments/paifu_frames/replay_recorder.dart", "overlay", str(d), e["dealer_side"],
                            str(root / "results" / name / "dart_overlay.json"), "--sticks", ",".join(map(str, e["sticks"]))],
                           cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise SystemExit(f"{name}: 재생 실패\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    ho.HERE, ho.OUT = root, root / "heldout"
    ho.score()
    s = jl(root / "heldout" / "summary.json")
    secs = sorted(x for v in stats.values() for x in v["secs"])
    s["measured"] = {"label": label, "at": datetime.now().isoformat(timespec="minutes"), "frames": {u: {k: v[k] for k in ("n", "kept", "err")} for u, v in stats.items()}}
    if secs:
        q = lambda f: secs[round((len(secs) - 1) * f)]  # noqa: E731
        s["measured"]["secs"] = dict(n=len(secs), median=statistics.median(secs), p90=q(0.9), max=secs[-1])
        print(f"프레임 {len(secs)}장 판독 시간 중앙 {statistics.median(secs):.2f} / p90 {q(0.9):.2f} / 최대 {secs[-1]:.2f}초")
    dump(root / "heldout" / "summary.json", s)


def score(src: str):
    root = OUT / src
    replay_and_score(root, src, to_dumps(src, root))


def pace(src: str):
    """앱은 앞 판독이 도는 동안(_overlayBusy) 온 프레임을 읽지 않는다 — 저장된 시각과 기기 판독 시간으로 그 건너뜀을 흉내 낸다."""
    def keep(u, frames):
        out, busy = [], None
        for f in frames:
            t = datetime.fromisoformat(f["at"]).timestamp()
            if busy is not None and t < busy:
                continue
            out.append(f)
            busy = t + f["secs"]
        return out

    root = OUT / f"{src}_pace"
    st = to_dumps(src, root, keep)
    print("건너뜀:", {u: f"{v['n'] - v['kept']}/{v['n']}" for u, v in st.items()})
    replay_and_score(root, f"{src}_pace", st)


def live():
    """거치 화면 실시간 재생(`integration_test/paifu_live_replay_test.dart` + `replay_head.py`) 결과를 같은 채점에 넣고 로그를 센다."""
    src, root = OUT / "live", OUT / "live_score"
    stats = {}
    for u in UNITS:
        p = src / f"{u}.json"
        if not p.exists():
            print(u, "결과 없음")
            continue
        r = jl(p)
        stats[u] = r.pop("_live")
        for name in {u, u.replace("full_", "_", 1)}:  # 앱은 추적 그대로 받았다 — 잘라 쓴 이름에도 같은 결과를 둔다(정답이 같음)
            dump(root / "results" / name / "dart_overlay.json", r)
            shutil.copy(OUT / "pc" / "results" / name / "overlay_dump.json", root / "results" / name / "overlay_dump.json")  # 틀림 진단용(PC 가 읽은 것)
    dump(root / "heldout" / "rounds.json", {k: v for k, v in jl(ho.OUT / "rounds.json").items() if k not in ho.REF})
    ho.HERE, ho.OUT = root, root / "heldout"
    ho.score()
    # 헤드 로그: 묶음별 요청 수(기본 = 3초 미리보기, 2400 = 기록용 고화질, 2992 = 겹쳐 보기)와 겹쳐 보기가 읽은 서로 다른 프레임 수
    idx = jl(STAGE / "index.json")
    rows = [json.loads(x) for x in (src / "head_log.jsonl").read_text(encoding="utf-8").splitlines()]
    last_ctl = {}
    for i, r in enumerate(rows):
        if r.get("path") == "/ctl":
            last_ctl[r["unit"]] = i  # 같은 묶음을 여러 번 돌렸으면 마지막 것만
    # logcat: [overlay] 줄의 total ms (시각 순, 묶음 구분은 [paifu-live] 줄)
    ov = {}
    for lf in sorted(src.glob("logcat_*.txt")):
        cur = []
        for line in lf.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.search(r"\[overlay\] \d+장 \{.*total: (\d+)\}", line)
            if m:
                cur.append(int(m.group(1)))
            m = re.search(r"\[paifu-live\] (\S+) ", line)
            if m:
                ov[m.group(1)], cur = cur, []
    summ = {}
    for u, st in stats.items():
        seg = [r for r in rows[last_ctl[u]:] if r.get("unit") == u and r.get("path") == "/preview"]
        w = lambda v: [r for r in seg if r.get("w") == v]  # noqa: E731
        full = [r for r in seg if (r.get("w") or 0) >= 1600]  # 원본 크기로 받은 것(기록용 2400 요청 + 겹쳐 보기 2992 요청 — 둘 다 저장 바이트 그대로)
        ms = sorted(ov.get(u, []))
        q = lambda f: ms[round((len(ms) - 1) * f)] if ms else None  # noqa: E731
        summ[u] = dict(secs=st["secs"], resets=st["resets"], dealer_side=st["dealer_side"], frames=len(idx[u]["frames"]), preview=len(w(None)), hi2400=len(w(2400)),
                       full=len(full), full_distinct=len({r["i"] for r in full}), overlays=len(ms), overlay_ms=dict(median=q(0.5), p90=q(0.9), max=ms[-1] if ms else None))
        print(u, summ[u])
    allms = sorted(x for u in stats for x in ov.get(u, []))
    if allms:
        print(f"겹쳐 보기 {len(allms)}번 중앙 {allms[len(allms) // 2] / 1000:.2f} / p90 {allms[round((len(allms) - 1) * .9)] / 1000:.2f} / 최대 {allms[-1] / 1000:.2f}초",
              "· 읽은 서로 다른 프레임", sum(v["full_distinct"] for v in summ.values()), "/", sum(v["frames"] for v in summ.values()))
    for hp in sorted(src.glob("heat_live*.jsonl")):  # 실행마다 파일 하나(11-17 밤 r20 · r12 ~ r15, 11-18 아침 r16 ~ r19)
        h = [json.loads(x) for x in hp.read_text(encoding="utf-8").splitlines()]
        print(hp.name, "발열 최고 단계", max(r["status"] or 0 for r in h), "AP 최고", max(r["temps"].get("AP", 0) for r in h), "SKIN 최고", max(r["temps"].get("SKIN", 0) for r in h),
              "배터리", h[0]["level"], "→", h[-1]["level"], f"({h[0]['at'][11:16]}~{h[-1]['at'][11:16]})", "배터리 온도", h[0]["bat_temp"], "→ 최고", max(r["bat_temp"] for r in h),
              "화면 상태", sorted({r.get("wake") for r in h}))
    s = jl(root / "heldout" / "summary.json")
    s["measured"] = {"label": "live", "at": datetime.now().isoformat(timespec="minutes"), "units": summ}
    dump(root / "heldout" / "summary.json", s)


def diff():
    """기기 답 ↔ PC 답(같은 프레임 · 같은 질의)을 프레임마다 견준다: 상자 짝(IoU > 0.5) · 종류 · 역할 · 주인 다름 수."""
    def iou(a, b):
        ix = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
        iy = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
        return ix * iy / (a[2] * a[3] + b[2] * b[3] - ix * iy + 1e-12)

    tot = dict(frames=0, same=0, pairs=0, t=0, r=0, s=0, only_dev=0, only_pc=0)
    for u in UNITS:
        pd, pp = OUT / "raw" / f"device_{u}.json", OUT / "raw" / f"pc_{u}.json"
        if not (pd.exists() and pp.exists()):
            continue
        bp = {it["name"]: it for it in jl(pp)["items"]}
        c = dict.fromkeys(tot, 0)
        for it in jl(pd)["items"]:
            o = bp.get(it["name"])
            if not o or it["err"] or o["err"]:
                continue
            a, b = it["res"]["tiles"], list(o["res"]["tiles"])
            c["frames"] += 1
            bad = 0
            for x in a:
                j = max(range(len(b)), key=lambda k: iou(x["b"], b[k]["b"]), default=None)
                if j is None or iou(x["b"], b[j]["b"]) <= 0.5:
                    c["only_dev"] += 1
                    bad += 1
                    continue
                y = b.pop(j)
                c["pairs"] += 1
                for k in ("t", "r", "s"):
                    if x.get(k) != y.get(k):
                        c[k] += 1
                        bad += 1
            c["only_pc"] += len(b)
            c["same"] += bad == 0 and not b
        print(u, c)
        for k in tot:
            tot[k] += c[k]
    print("합", tot)
    dump(OUT / "diff_device_pc.json", tot)


if __name__ == "__main__":
    cmd, rest = sys.argv[1], sys.argv[2:]
    {"make": make, "diff": diff, "live": live, "heat": lambda: heat(*rest), "push": push, "pc": lambda: pc(rest), "run": lambda: run(rest), "score": lambda: score(rest[0]), "pace": lambda: pace(rest[0])}[cmd]()
