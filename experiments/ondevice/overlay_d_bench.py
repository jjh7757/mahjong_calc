"""겹쳐 보기 D 경로 태블릿 확인 준비(실험 5b, 2026-11-12, `docs/role_owner_plan_1111.md` 5단계). 5a 에서는 make 만 돌렸다(기기·adb 안 씀).

  python -I -X utf8 experiments/ondevice/overlay_d_bench.py make [TAG]     build/bench/manifest_<TAG>.json 만 쓴다(기본 TAG ovd1, adb 안 씀)
  python -I -X utf8 experiments/ondevice/overlay_d_bench.py run [TAG]      manifest 올림 → 브로드캐스트 → 결과 받기 → score (device_bench.run 과 같은 절차)
  python -I -X utf8 experiments/ondevice/overlay_d_bench.py score <결과.json>

manifest = `ondevice.bench` 형식 {"tag", "items": [{"name", "kind": "overlay", "images": [기기 경로], "query": {…}}]}. 40장(device_bench.scenes(),
테스트 세트 원본 = PC 확인과 같은 바이트)마다 두 항목을 이어서: "<이름>"(role 없음 = 지금 A, 4회) → "<이름>#d"(role=d, D 1회).
질의 = 저장 격자 x1·x2·y1·y2 만(앱 _runOverlay·manifest_ov1 과 같음, sticks·side 없음). 재저장 = 기기 기본(skip).
사진은 `device_bench.py push` 가 사본 앱 폴더(/sdcard/Android/data/dev.jjh.mahjong_calc.ondevice/files/bench)에 올린 것을 쓴다.

score 기준(계획서 5b): ① 기기 D 답이 PC(`results/overlay_d_check_1112.json` 의 tiles_D, ONNX)와 상자 순서대로 b·t·r·s 같음 — 40장 모두,
rc 다름 수·최대 차, 표 4-2 기기 일치 방식(IoU > 0.5 짝)으로 종류·역할·주인 다름 수. ② 역할 단계 시간 ms.roles: 기기 A(4회) 대 D(1회)
중앙 / p90 / 최대(첫 D 항목은 D 세션 만들기가 들어가 따로 적음). 참고: 기기 D 답의 장면 채점(overlay_score.scene_score).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "experiments" / "speed"))
import device_bench as db  # noqa: E402  (ADB·PKG·CLS·DEV_DIR·STAGE·scenes — import 만, adb 는 run 에서만)

PC = HERE / "results" / "overlay_d_check_1112.json"


def iou(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    i = ix * iy
    return i / (aw * ah + bw * bh - i + 1e-12)


def make(tag: str = "ovd1") -> Path:
    items = []
    for s, _ in db.scenes():
        g = s["grid"]
        q = {k: str(g[k]) for k in ("x1", "x2", "y1", "y2")}
        img = [f"{db.DEV_DIR}/{s['name']}.jpg"]
        items.append({"name": s["name"], "kind": "overlay", "images": img, "query": q})
        items.append({"name": s["name"] + "#d", "kind": "overlay", "images": img, "query": dict(q, role="d")})
    db.STAGE.mkdir(parents=True, exist_ok=True)
    p = db.STAGE / f"manifest_{tag}.json"
    p.write_text(json.dumps({"tag": tag, "items": items}, ensure_ascii=False), encoding="utf-8")
    print(f"항목 {len(items)}(장면 {len(items) // 2} × A·D) → {p}")
    return p


def run(tag: str = "ovd1") -> None:
    """device_bench.run 과 같은 절차(그쪽은 manifest.json(localroles)을 읽어 쓰므로 overlay 용으로 따로)."""
    p = db.STAGE / f"manifest_{tag}.json"
    if not p.exists():
        p = make(tag)
    db.adb("push", str(p), f"{db.DEV_DIR}/manifest_{tag}.json")
    db.adb("shell", "am", "start", "-n", f"{db.PKG}/{db.CLS}.MainActivity")
    time.sleep(3)
    db.adb("logcat", "-c")
    db.adb("shell", "am", "broadcast", "-n", f"{db.PKG}/{db.CLS}.OnDeviceBenchReceiver", "--es", "manifest", f"manifest_{tag}.json")
    t0 = time.time()
    while time.time() - t0 < 1800:
        log = db.adb("logcat", "-d", "-s", "ondevice-bench:*", "python.stderr:*", "AndroidRuntime:E", check=False)
        if "done {" in log or "failed" in log:
            print(log[-3000:])
            break
        time.sleep(5)
    else:
        raise SystemExit("30분 안에 안 끝남")
    out = HERE / "results" / f"device_{tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    db.adb("pull", f"{db.DEV_DIR}/result_{tag}.json", str(out))
    score(out)


def score(path: Path) -> dict:
    import numpy as np

    import overlay_score as osc  # 장면 채점(서버·android python 경로를 넣음)

    res = json.loads(Path(path).read_text(encoding="utf-8"))
    pc = json.loads(PC.read_text(encoding="utf-8"))["scenes"]
    sc_by = {s["name"]: s for s, _ in db.scenes()}
    by = {}
    for it in res["items"]:
        by[it["name"]] = it
    rows, ms_a, ms_d, err = {}, [], [], []
    first_d = next((it["name"] for it in res["items"] if it["name"].endswith("#d")), None)
    n_same = n_box = rc_n = 0
    rc_max = 0.0
    par = {"pairs": 0, "t": 0, "r": 0, "s": 0, "unmatched": 0}
    for name, s in sc_by.items():
        a, d = by.get(name), by.get(name + "#d")
        if not a or not d or a["err"] or d["err"] or not d["res"]:
            err.append(name)
            continue
        ms_a.append(a["res"]["ms"]["roles"])
        if d["name"] != first_d:
            ms_d.append(d["res"]["ms"]["roles"])
        dev, ref = d["res"]["tiles"], pc[name]["tiles_D"]
        hard = len(dev) != len(ref) or any(p[k] != q[k] for p, q in zip(dev, ref) for k in ("b", "t", "r", "s"))
        n_same += not hard
        n_box += len(dev)
        for p, q in zip(dev, ref):
            if p["rc"] != q["rc"]:
                rc_n += 1
                rc_max = max(rc_max, abs(p["rc"] - q["rc"]))
        for t in ref:  # 표 4-2 기기 일치 방식: PC 상자마다 IoU 가장 큰 기기 상자(> 0.5)
            j = max(range(len(dev)), key=lambda k: iou(t["b"], dev[k]["b"]), default=None)
            if j is None or iou(t["b"], dev[j]["b"]) <= 0.5:
                par["unmatched"] += 1
                continue
            par["pairs"] += 1
            for k in ("t", "r", "s"):
                par[k] += t[k] != dev[j][k]
        ss = osc.scene_score(dev, s)
        rows[name] = {"same": not hard, "n": [len(dev), len(ref)], "scene_ok": ss["ok"], "other_hand_max": ss["other_hand_max"], "hit": ss["hit"],
                      "want": ss["want"], "ms_A": a["res"]["ms"], "ms_D": d["res"]["ms"], "secs_A": a["secs"], "secs_D": d["secs"]}

    def q(v):
        v = np.asarray(v, float)
        return {"median": round(float(np.median(v)), 1), "p90": round(float(np.percentile(v, 90)), 1), "max": round(float(v.max()), 1), "n": int(len(v))} if len(v) else None

    out = {"result": str(path), "warmup": res.get("warmup"), "prep": res.get("prep"), "total_s": res.get("total_s"), "errors": err,
           "d_vs_pc": {"same_scenes": f"{n_same}/{len(rows)}", "boxes": n_box, "rc_diff": rc_n, "rc_max": round(rc_max, 4), "parity": par},
           "roles_ms": {"A_4calls": q(ms_a), "D_1call": q(ms_d), "D_first_item": by[first_d]["res"]["ms"]["roles"] if first_d and by[first_d]["res"] else None},
           "scene_D": {"ok": sum(r["scene_ok"] for r in rows.values()), "other_hand_scenes": sum(r["other_hand_max"] > 0 for r in rows.values()),
                       "hit": sum(r["hit"] for r in rows.values()), "want": sum(r["want"] for r in rows.values())},
           "rows": rows}
    p = Path(path).with_name(Path(path).stem + "_score.json")
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, ensure_ascii=False, indent=1))
    print("→", p)
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    os.environ.setdefault("MSYS_NO_PATHCONV", "1")
    cmd = sys.argv[1]
    if cmd == "make":
        make(sys.argv[2] if len(sys.argv) > 2 else "ovd1")
    elif cmd == "run":
        run(sys.argv[2] if len(sys.argv) > 2 else "ovd1")
    elif cmd == "score":
        score(Path(sys.argv[2]))
    else:
        raise SystemExit(__doc__)
