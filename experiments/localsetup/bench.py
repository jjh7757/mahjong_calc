"""서버 없는 자동 맞추기(`ondevice.py` localsetup) 채점: 테스트 장면 40장(experiments/draw_reveal/scenes.json = seat_grow.eval_scenes,
가림·사용자 문제 뺀 B·C·D + 10-31 + 11-07)에서 기기와 같은 코드로 격자를 잡아 장면 격자(저장·수동)와 선 차이(1000 분율)를 본다. PC, API 없음.
  python -X utf8 experiments/localsetup/bench.py   (mahjong-recognizer 를 RECOGNIZER_REPO 또는 옆 폴더에서)
"""
import json, os, statistics, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPO = Path(os.environ.get("RECOGNIZER_REPO", ROOT.parent / "mahjong-recognizer"))
# 기기용 onnxruntime·cv2 대리 모듈(java 브리지)이 같은 폴더에 있어 그 폴더는 맨 뒤에 둔다(PC 진짜 패키지가 먼저).
sys.path.insert(0, str(REPO))
sys.path.append(str(ROOT / "android/app/src/main/python"))
import ondevice  # noqa: E402

scenes = json.loads((ROOT / "experiments/draw_reveal/scenes.json").read_text(encoding="utf-8"))
ondevice.warmup()
rows = []
for s in scenes:
    data = Path(s["path"]).read_bytes()
    t0 = time.perf_counter()
    out = json.loads(ondevice.observe("localsetup", [data], {}))
    secs = time.perf_counter() - t0
    g, ref = out.get("grid"), s["grid"]
    d = None if not g else {k: g[k] - ref[k] for k in ("x1", "x2", "y1", "y2")}
    rows.append({"name": s["name"], "set": s["set"], "ref": ref, "grid": g, "diff": d,
                 "maxdiff": None if d is None else max(abs(v) for v in d.values()),
                 "source": (out.get("frame_info") or {}).get("source"), "error": out.get("frame_error"), "s": round(secs, 3)})
    print(s["name"], rows[-1]["source"], rows[-1]["maxdiff"], d, rows[-1]["error"] or "", f"{secs:.2f}s", flush=True)
(HERE / "results").mkdir(exist_ok=True)
(HERE / "results/bench.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
ok = [r for r in rows if r["grid"]]
md = sorted(r["maxdiff"] for r in ok)
print(f"격자 잡음 {len(ok)}/{len(rows)}, 기기 {sum(r['source']=='device' for r in ok)} · 패산 {sum(r['source']=='wall' for r in ok)}")
if md:
    print("선 최대 차(1000분율) 중앙/p90/최대", statistics.median(md), md[int(len(md) * 0.9)], md[-1],
          "· 20 이내", sum(m <= 20 for m in md), "· 40 이내", sum(m <= 40 for m in md))
ts = sorted(r["s"] for r in rows)
print("시간 중앙/p90/최대", statistics.median(ts), ts[int(len(ts) * 0.9)], ts[-1])
