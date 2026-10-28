"""울기 추적 + 손패 전용 경로가 조각 읽기와 합치면 얼마나 빨라지나: 세 방식을 같은 순간에 나란히.

  python -I -X utf8 experiments/speed/handonly_compare.py --runs 15      (로컬 서버 "recognizer" 8030 + "recognizer-handframe" 8032)
  python -I -X utf8 experiments/speed/handonly_compare.py --show
  운영: --a https://mahjong.ai-agent-develop.cloud --f 같은 주소 --key-file .recognizer_key --out handonly_prod.json

  seat        지금 운영: /v2/seat, 자리 크롭(손패 + 울기), YOLO 틀 + 조각 읽기. 손패 + 울기가 맞아야 정답.
  hand_whole  지금 손패 전용: /v2/handonly, 울기 잘라 낸 크롭, 통째 읽기(서버 8030 = HANDONLY_FRAME 꺼짐).
  hand_frame  합친 것(실험): /v2/handonly, 같은 크롭, YOLO 틀 + 조각 읽기(서버 8032 = HANDONLY_FRAME=1).
손패 전용 둘은 손패가 맞고 울기를 지어내지 않아야(빈 배열) 정답. 울기는 판 상태 추적이 맞게 확정했다고 친다.

울기가 있는 장면 B·D(사진 4장)만 — 울기가 없는 자리는 추적이 확정하지 않아 늘 seat 로 간다. 울기를 자르는 위치는
seat_nomeld.py 와 같다(B 0.79, D 0.65). 세 요청 모두 자리 판독 3번 동시 + 만장일치라 장면마다 Gemini 9호출 —
두 로컬 서버가 같은 키를 쓰므로 분당 20 을 넘지 않게 장면 시작 간격을 [--gap] 초(기본 30) 이상으로 둔다.
"""
from __future__ import annotations

import argparse
import io
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import bench as b  # noqa: E402

OUT = b.OUT / "handonly_compare.json"
SEATS = {"B": "hand_right", "D": "hand_bottom"}
CUT = {"B": 0.79, "D": 0.65}
CONDS = ("seat", "hand_whole", "hand_frame")


# 앱이 실제로 자르는 곳(GridZones.handCell = 자리 칸 − 모서리 칸)의 자리 크롭 폭 비율. 장면 격자(read_grid_timing_test)에서:
# B 오른쪽 (y2 − y1) / y2 = 590/727, D 아래 (x2 − x1) / (1000 − x1) = 465/720.
APP_CUT = {"B": 590 / 727, "D": 465 / 720}


def crops(scene: str, photo: str, cut_at: dict[str, float] = CUT) -> tuple[bytes, bytes]:
    im = Image.open(b.G / scene / photo / f"{SEATS[scene]}.jpg").convert("RGB")
    cut = im.crop((0, 0, round(im.width * cut_at[scene]), im.height))
    out = []
    for x in (im, cut):
        buf = io.BytesIO()
        x.save(buf, "JPEG", quality=92)
        out.append(buf.getvalue())
    return out[0], out[1]


KEY = ""  # 운영 서버 API 키(--key-file). 로컬은 비움.


def post(url: str, path: str, jpeg: bytes) -> dict:
    t0 = time.perf_counter()
    r = requests.post(f"{url}{path}", files={"image": ("seat.jpg", jpeg, "image/jpeg")},
                      headers={"X-Api-Key": KEY} if KEY else {}, timeout=180)
    secs = time.perf_counter() - t0
    if r.status_code != 200:
        return {"error": f"{r.status_code} {r.text[:100]}", "s": secs}
    return {"data": r.json(), "s": secs}


def judge(scene: str, cond: str, d: dict) -> dict:
    hand = [t["tile"] for t in d["tiles"]] + ([d["separate_tile"]["tile"]] if d.get("separate_tile") else [])
    melds = sorted(" ".join(sorted(m["tiles"])) for m in d.get("melds") or [])
    th = b.TRUTH[scene][1].split()
    tm = [] if cond != "seat" else sorted(" ".join(sorted(m.split())) for m in b.TRUTH[scene][2])
    return {"hand": " ".join(hand), "melds": melds, "ok": sorted(hand) == sorted(th) and melds == tm,
            "unanimous": d["agreement"]["unanimous"], "method": d.get("method"),
            "in": d["usage"]["input_tokens"], "server_ms": d.get("latency_ms")}


def run(runs: int, a: str, f: str, gap: float, conds: tuple[str, ...] = CONDS, cut_at: dict[str, float] = CUT,
        out: Path = OUT) -> list[dict]:
    rows = []
    items = [(s, p, *crops(s, p, cut_at)) for s in "BD" for p in b.PHOTOS[s]]
    with ThreadPoolExecutor(3) as ex:
        for i in range(runs):
            for scene, photo, full, cut in items:
                t_start = time.time()
                # hand_frame 은 추적이 확정한 울기 수(정답 울기 수)를 함께 보낸다 — 틀의 장수 검사(13·14)에 더해진다.
                # hand_whole 은 울기 수 없이(예전 앱) — 운영(71b43cd~)에선 틀 검사를 못 넘어 통째 읽기가 된다.
                q = f"/v2/handonly?melds={len(b.TRUTH[scene][2])}"
                jobs = {"seat": (a, "/v2/seat", full), "hand_whole": (a, "/v2/handonly", cut), "hand_frame": (f, q, cut)}
                jobs = {k: v for k, v in jobs.items() if k in conds}
                results = dict(zip(jobs, ex.map(lambda j: post(*j), jobs.values())))
                for cond, r in results.items():
                    row = {"run": i, "cond": cond, "scene": scene, "photo": photo, "s": round(r["s"], 2)}
                    row.update({"error": r["error"]} if "error" in r else judge(scene, cond, r["data"]))
                    rows.append(row)
                    print(f"{cond:10s} {scene} {photo} #{i} {row['s']:5.1f}s {row.get('method') or row.get('error')} "
                          f"{'OK' if row.get('ok') else 'X ' + str(row.get('hand'))}"
                          f"{'' if row.get('unanimous', True) else ' (엇갈림)'}", flush=True)
                time.sleep(max(0.0, gap - (time.time() - t_start)))
    old = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
    out.write_text(json.dumps(old + rows, ensure_ascii=False, indent=0), encoding="utf-8")
    return old + rows


def show(rows: list[dict]) -> None:
    def p90(t: list[float]) -> float:
        return t[int(.9 * (len(t) - 1))]

    for cond in CONDS:
        for label, rs in [("B·D", [r for r in rows if r["cond"] == cond])] + \
                [(s, [r for r in rows if r["cond"] == cond and r["scene"] == s]) for s in "BD"]:
            good = [r for r in rs if "error" not in r]
            if not good:
                continue
            t = sorted(r["s"] for r in good)
            print(f"{cond:10s} {label:3s} 정답 {sum(r['ok'] for r in good)}/{len(good)}  만장일치 {sum(r['unanimous'] for r in good)}  "
                  f"중앙 {statistics.median(t):.1f} / p90 {p90(t):.1f} / 최대 {t[-1]:.1f}초  "
                  f"입력 {statistics.median(r['in'] for r in good) / 1000:.1f}k  틀 {sum(r.get('method') == 'frame' for r in good)}  "
                  f"오류 {len(rs) - len(good)}")
    # 같은 장면 짝 차이(seat 대비).
    by = {}
    for r in rows:
        if "error" not in r:
            by.setdefault((r["run"], r["photo"]), {})[r["cond"]] = r["s"]
    for cond in ("hand_whole", "hand_frame"):
        d = [v[cond] - v["seat"] for v in by.values() if cond in v and "seat" in v]
        if d:
            print(f"{cond} − seat 짝 차이 중앙 {statistics.median(d):+.1f}초, 빠른 장면 {sum(x < 0 for x in d)}/{len(d)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=15)
    ap.add_argument("--a", default="http://127.0.0.1:8030", help="seat·hand_whole 서버(HANDONLY_FRAME 꺼짐)")
    ap.add_argument("--f", default="http://127.0.0.1:8032", help="hand_frame 서버(HANDONLY_FRAME=1)")
    ap.add_argument("--gap", type=float, default=30.0, help="장면 시작 간격(초) — 9호출/30초 = 분당 18")
    ap.add_argument("--conds", default=",".join(CONDS), help="잴 조건만(쉼표)")
    ap.add_argument("--app-cut", action="store_true", help="울기 자르는 곳을 앱 격자 handCell 비율로(APP_CUT)")
    ap.add_argument("--out", default=OUT.name, help="results/ 아래 결과 파일 이름")
    ap.add_argument("--key-file", default="", help="X-Api-Key 로 보낼 키 파일(운영 서버, 예: .recognizer_key)")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    if args.key_file:
        KEY = Path(args.key_file).read_text(encoding="utf-8").strip()
    out = b.OUT / args.out
    show(json.loads(out.read_text(encoding="utf-8")) if args.show else
         run(args.runs, args.a, args.f, args.gap, tuple(args.conds.split(",")), APP_CUT if args.app_cut else CUT, out))
