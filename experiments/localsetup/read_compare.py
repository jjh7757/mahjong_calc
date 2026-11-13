"""서버 없는 자동 맞추기 격자(results/bench.json 의 localsetup 격자)로 화료자 자리를 읽어, 장면 격자(저장·수동)로 읽은 것과 정답을 비교한다.
기기와 같은 코드(`ondevice.observe('localroles')`, PC), 테스트 장면 40장 = seat_grow.eval_scenes. 손패(떼어 둔 패 제외)와 울기 묶음이 정답과 같으면 맞음.
장면 격자 = grid_src saved, 자동 맞추기 격자 = 앱이 보낼 grid_src felt. 두 격자를 장면마다 번갈아 같은 시각에.
  python -X utf8 experiments/localsetup/read_compare.py
"""
import json, os, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPO = Path(os.environ.get("RECOGNIZER_REPO", ROOT.parent / "mahjong-recognizer"))
sys.path.insert(0, str(REPO))
sys.path.append(str(ROOT / "android/app/src/main/python"))  # 기기용 onnxruntime 대리 모듈보다 PC 패키지가 먼저
sys.path.insert(0, str(ROOT / "experiments/speed"))
import ondevice  # noqa: E402
import seat_grow as sg  # noqa: E402

bench = {r["name"]: r for r in json.loads((HERE / "results/bench.json").read_text(encoding="utf-8"))}
ondevice.warmup()


def read(path, side, g, src):
    q = {"side": side, "mode": "hybrid", "grid_src": src, **{k: str(g[k]) for k in ("x1", "x2", "y1", "y2")}}
    if g.get("sticks"):
        q["sticks"] = ",".join(str(v) for v in g["sticks"])
    t0 = time.perf_counter()
    o = json.loads(ondevice.observe("localroles", [Path(path).read_bytes()], q))
    return o, time.perf_counter() - t0


def ok(o, s):
    hand = sorted(t["tile"] for t in o.get("tiles") or [])
    melds = sorted(" ".join(sorted(m["tiles"])) for m in o.get("melds") or [])
    want = sorted(" ".join(sorted(m.split())) for m in s["melds"])
    return hand == sorted(s["hand"]) and melds == want, " ".join(hand), melds


rows = []
for s in sg.eval_scenes():
    b = bench[s["name"]]
    ref, (refok, refh, refm), tr = None, (None, None, None), None
    o1, t1 = read(s["path"], s["side"], s["grid"], "saved")
    r1 = ok(o1, s)
    if b["grid"]:
        o2, t2 = read(s["path"], s["side"], b["grid"], "felt")
        r2 = ok(o2, s)
    else:
        r2, t2 = (False, None, None), None
    rows.append({"name": s["name"], "set": s["set"], "maxdiff": b["maxdiff"], "saved_ok": r1[0], "local_ok": r2[0],
                 "saved": r1[1:], "local": r2[1:], "s": [round(t1, 2), t2 and round(t2, 2)]})
    print(s["name"], b["maxdiff"], "saved", r1[0], "local", r2[0], "" if r1[1:] == r2[1:] else f"| {r1[1]} {r1[2]} → {r2[1]} {r2[2]}", flush=True)
(HERE / "results/read_compare.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
for st in ("bcd", "visit1031", "visit1107", None):
    rs = [r for r in rows if st is None or r["set"] == st]
    if rs:
        print(st or "전체", f"장면 격자 {sum(r['saved_ok'] for r in rs)}/{len(rs)} · 자동 맞추기 격자 {sum(r['local_ok'] for r in rs)}/{len(rs)}",
              f"· 답 같음 {sum(r['saved'] == r['local'] for r in rs)}")
