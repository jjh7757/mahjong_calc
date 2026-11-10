"""자리 크롭을 격자 선에서 가운데 쪽으로 넓히면 앞으로 내민 공개 손패가 온전히 읽히나(2026-10-31, 매장 오후 잘림 8/15).

운영 /v2/seat 에 grow 0·40·80(0~1000) 크롭을 같은 순간에 보낸다. 앱 `GridZones.seat` + `hand_frac` 와 같게 자른다.
격자는 매장 기록에 남은 것(setup_*.json·frames.json) 중 저장된 손패 크롭 크기와 맞는 것을 쓴다.

  python experiments/speed/seat_grow.py [--runs-bcd 2] [--runs-visit 1] [--grows 0,40,80]
  python experiments/speed/seat_grow.py --show        결과 experiments/speed/results/seat_grow.json

채점: B·C·D = bench.TRUTH, 매장 = visit_20261031/truth.json 이 있으면 그것, 없으면 label.json.
"""
from __future__ import annotations

import argparse
import io
import json
import statistics
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
VISIT = ROOT / "experiments/visit_20261031/captures"
KAKAO = ROOT / "experiments/field_20261024/kakao_photos"
OUT = ROOT / "experiments/speed/results/seat_grow.json"
URL = "https://mahjong.ai-agent-develop.cloud"
KEY = (ROOT / ".recognizer_key").read_text().strip()
ROT_CW = {"bottom": 0, "right": 90, "top": 180, "left": 270}

BCD = {
    "k25": ("right", dict(x1=272, x2=735, y1=137, y2=727), "7z 1m 1m 1m 9s 9s 9s 9p 9p 9p", ["6z 6z 6z"]),
    "k28": ("right", dict(x1=272, x2=735, y1=137, y2=727), "7z 1m 1m 1m 9s 9s 9s 9p 9p 9p", ["6z 6z 6z"]),
    "k15": ("left", dict(x1=320, x2=760, y1=142, y2=717), "1z 1z 1z 1m 2m 3m 4m 5m 6m 7m 8m 9m 2z", []),
    "k26": ("left", dict(x1=320, x2=760, y1=142, y2=717), "1z 1z 1z 1m 2m 3m 4m 5m 6m 7m 8m 9m 2z", []),
    "k12": ("bottom", dict(x1=280, x2=745, y1=173, y2=713), "1m 2m 3m 4m 0m 6m 7m 8m 9m 2z", ["6m 7m 8m"]),
    "k16": ("bottom", dict(x1=280, x2=745, y1=173, y2=713), "1m 2m 3m 4m 0m 6m 7m 8m 9m 2z", ["6m 7m 8m"]),
}
# label.json 이 없거나 틀린 장면의 정답(2026-11-01, 사진 눈 판독 + 사용자 답 + visit_truth_check.py)
TRUTH = json.loads((VISIT.parent / "truth.json").read_text(encoding="utf-8"))["scenes"]
# 손·팔이 패를 가린 사진. 어떤 방법으로도 맞출 수 없어 평가에서 뺀다(사용자 결정 2026-11-02). 학습 재료로는 그대로 쓴다.
# 채점하는 스크립트는 정답을 [eval_scenes] 에서 가져오거나 [EXCLUDED] 로 거른다([scenes] 는 학습·격자용). 새 가림 사진은 채점 전에 사진만 보고 여기에 더한다.
# 2026-11-07 매장: 151320 은 두 팔이 가운데로 뻗어 위(화료자) 손패를 가림(사진만 보고 판단).
OCCLUDED = {"20261031_172424", "20261031_174020", "20261107_151320"}
# 촬영·사용 규칙을 어긴 사진: 손패를 한 줄로 두지 않고 펠트 곳곳에 흩어 놓음(183022, 사용자 결정 2026-11-04 "사용자 문제"). 학습엔 그대로.
# 2026-11-05 추가(사용자 결정, 8회차 채점 뒤에 뺌 — metrics 표 1-70 메모): 142535 화료패 쪽을 2장(0s·5s) 떼어 놓음(떼어 둔 패는 1장 규칙 위반,
# 표시패 짝과 같은 모양). 175951 은 울기패를 손패 쪽으로 끌어와 섞음(사용자 판단 11-05, 11-04 "남김" 결정을 바꿈 — 울기 구분 근거가 없고
# truth 의 "울기 없음" 도 불확실).
# 2026-11-08 추가(사용자 결정): 20261107_153638 — 화료 직후 왼쪽 아래 모서리(흰 테두리 위)의 울기 두 묶음(치 567삭·123삭)을 손으로
# 손패 끝까지 끌어와 이어 붙임(3초 프레임 15:36:34 → :37 로 확인, 175951 과 같은 꼴). 합성으로 울기를 모서리에 둔 판은 따로 잰다.
USER_ERROR = {"20261031_183022", "20261031_142535", "20261031_175951", "20261107_153638"}
EXCLUDED = OCCLUDED | USER_ERROR  # 채점에서 빼는 전부


def seat_box(g: dict, side: str, grow: int) -> tuple[int, int, int, int]:
    """(ymin, xmin, ymax, xmax). 가운데 쪽 변만 grow 만큼 옮긴다."""
    x1, x2, y1, y2 = g["x1"], g["x2"], g["y1"], g["y2"]
    return {
        "bottom": (y2 - grow, x1, 1000, 1000),
        "right": (0, x2 - grow, y2, 1000),
        "top": (0, 0, y1 + grow, x2),
        "left": (y1, 0, 1000, x1 + grow),
    }[side]


def hand_frac(g: dict, side: str) -> float:
    x1, x2, y1, y2 = g["x1"], g["x2"], g["y1"], g["y2"]
    return {"bottom": (x2 - x1) / (1000 - x1), "right": (y2 - y1) / y2, "top": (x2 - x1) / x2, "left": (y2 - y1) / (1000 - y1)}[side]


def crop(im: Image.Image, box, side: str) -> Image.Image:
    w, h = im.size
    y0, x0, y1, x1 = box
    out = im.crop((round(x0 * w / 1000), round(y0 * h / 1000), round(x1 * w / 1000), round(y1 * h / 1000)))
    return out.rotate(-ROT_CW[side], expand=True) if ROT_CW[side] else out


def jpeg(im: Image.Image) -> bytes:
    b = io.BytesIO()
    im.save(b, "JPEG", quality=92)
    return b.getvalue()


def visit_grids() -> list[dict]:
    seen, out = set(), []
    for t in sorted(VISIT.glob("20261031_*_track")):
        cands = []
        for f in sorted(t.glob("setup_*.json")):
            j = json.loads(f.read_text(encoding="utf-8"))
            cands += [j.get("grid_before"), j.get("grid_proposed")]
        for z in sorted(t.glob("frames_*.zip")):
            with zipfile.ZipFile(z) as zf:
                cands.append(json.loads(zf.read("frames.json")).get("grid"))
        for g in cands:
            if not g:
                continue
            k = (g["x1"], g["x2"], g["y1"], g["y2"])
            if k not in seen:
                seen.add(k)
                out.append(g)
    return out


def find_grid(grids: list[dict], d: Path, side: str, size: tuple[int, int]) -> dict | None:
    stored = Image.open(next(d.glob(f"hand_{side}.jpg"))).size
    for g in reversed(grids):
        y0, x0, y1, x1 = seat_box(g, side, 0)
        w, h = round((x1 - x0) * size[0] / 1000), round((y1 - y0) * size[1] / 1000)
        if ROT_CW[side] in (90, 270):
            w, h = h, w
        if abs(w - stored[0]) <= 3 and abs(h - stored[1]) <= 3:
            return g
    return None


def scenes() -> list[dict]:
    rows = [dict(name=k, set="bcd", path=KAKAO / f"{k}.jpg", side=v[0], grid=v[1], hand=v[2].split(), melds=v[3]) for k, v in BCD.items()]
    grids = visit_grids()
    for d in sorted(VISIT.glob("20261031_1*")):
        if d.name.endswith("_track") or d.name < "20261031_12":
            continue
        m = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        side = m["winner_side"]
        size = Image.open(d / "original.jpg").size
        g = find_grid(grids, d, side, size)
        if g is None:
            print("격자 못 찾음", d.name, side)
            continue
        r = dict(name=d.name, set="visit", path=d / "original.jpg", side=side, grid=g, hand=None, melds=None)
        src = d / "label.json"
        if d.name in TRUTH:
            r["hand"], r["melds"] = TRUTH[d.name]["hand"].split(), TRUTH[d.name]["melds"]
        elif src.exists():
            lab = json.loads(src.read_text(encoding="utf-8"))
            closed = list(lab["closed"])
            if not lab["is_tsumo"]:
                closed.remove(lab["win_tile"])
            r["hand"], r["melds"] = closed, [x.strip("[]") for x in lab["melds"]]
        rows.append(r)
    return rows


def eval_scenes() -> list[dict]:
    """채점용 장면: [scenes] 에서 가림·사용자 문제 사진([EXCLUDED])을 뺀 것."""
    return [s for s in scenes() if s["name"] not in EXCLUDED]


def post(jpg: bytes, frac: float) -> dict:
    t0 = time.perf_counter()
    try:
        r = requests.post(f"{URL}/v2/seat", files={"image": ("seat.jpg", jpg, "image/jpeg")}, params={"hand_frac": f"{frac:.3f}"},
                          headers={"X-API-Key": KEY}, timeout=180)
    except requests.RequestException as e:
        return {"error": type(e).__name__, "s": time.perf_counter() - t0}
    secs = time.perf_counter() - t0
    return {"data": r.json(), "s": secs} if r.status_code == 200 else {"error": f"{r.status_code} {r.text[:120]}", "s": secs}


def judge(s: dict, res: dict) -> dict:
    if "error" in res:
        return {"error": res["error"], "s": round(res["s"], 1)}
    d = res["data"]
    hand = [t["tile"] for t in d.get("tiles") or []]
    sep = (d.get("separate_tile") or {}).get("tile")
    melds = [" ".join(m["tiles"]) for m in d.get("melds") or []]
    n = len(hand) + (1 if sep else 0) + 3 * len(melds)
    row = {"s": round(res["s"], 1), "hand": " ".join(hand), "sep": sep, "melds": melds, "n": n, "count_ok": n in (13, 14),
           "unanimous": (d.get("agreement") or {}).get("unanimous"), "method": d.get("method"), "face_up": d.get("face_up")}
    if s["hand"] is not None:
        got = sorted(hand + ([sep] if sep else []))
        row["ok"] = got == sorted(s["hand"]) and sorted(" ".join(sorted(m.split())) for m in melds) == sorted(" ".join(sorted(m.split())) for m in s["melds"])
    return row


def run(args) -> None:
    grows = [int(x) for x in args.grows.split(",")]
    rows = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    for s in scenes():
        im = Image.open(s["path"]).convert("RGB")
        frac = hand_frac(s["grid"], s["side"])
        jobs = {g: jpeg(crop(im, seat_box(s["grid"], s["side"], g), s["side"])) for g in grows}
        for i in range(args.runs_bcd if s["set"] == "bcd" else args.runs_visit):
            with ThreadPoolExecutor(len(grows)) as ex:
                res = dict(zip(grows, ex.map(lambda g: post(jobs[g], frac), grows)))
            row = {"name": s["name"], "set": s["set"], "side": s["side"], "grid": s["grid"], "run": i, "at": time.strftime("%H:%M:%S"),
                   "by_grow": {str(g): judge(s, r) for g, r in res.items()}}
            rows.append(row)
            OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
            print(s["name"], s["side"], {g: (v.get("n"), v.get("ok"), v.get("s"), v.get("error")) for g, v in row["by_grow"].items()}, flush=True)
            time.sleep(args.sleep)


def hand_cell(g: dict, side: str, grow: int) -> tuple[int, int, int, int]:
    """앱 `GridZones.handCell` 의 가운데 쪽 변만 grow 만큼 옮긴 것(/v2/handonly 에 보내는 크롭)."""
    x1, x2, y1, y2 = g["x1"], g["x2"], g["y1"], g["y2"]
    return {
        "bottom": (y2 - grow, x1, 1000, x2),
        "right": (y1, x2 - grow, y2, 1000),
        "top": (0, x1, y1 + grow, x2),
        "left": (y1, 0, y2, x1 + grow),
    }[side]


def handonly(args) -> None:
    """울기를 추적으로 아는 경우의 크롭도 넓혀도 되나 — B·C·D 만(울기 수를 안다)."""
    grows = [int(x) for x in args.grows.split(",")]
    tally = {g: {"ok": 0, "n": 0, "s": []} for g in grows}
    for s in [x for x in scenes() if x["set"] == "bcd"]:
        im = Image.open(s["path"]).convert("RGB")
        jobs = {g: jpeg(crop(im, hand_cell(s["grid"], s["side"], g), s["side"])) for g in grows}

        def go(g):
            t0 = time.perf_counter()
            r = requests.post(f"{URL}/v2/handonly", files={"image": ("hand.jpg", jobs[g], "image/jpeg")},
                              params={"melds": str(len(s["melds"]))}, headers={"X-API-Key": KEY}, timeout=180)
            return r, time.perf_counter() - t0

        for _ in range(args.runs_bcd):
            with ThreadPoolExecutor(len(grows)) as ex:
                res = dict(zip(grows, ex.map(go, grows)))
            line = {}
            for g, (r, secs) in res.items():
                d = r.json() if r.status_code == 200 else {}
                got = sorted([t["tile"] for t in d.get("tiles") or []] + ([d["separate_tile"]["tile"]] if d.get("separate_tile") else []))
                ok = got == sorted(s["hand"])
                tally[g]["ok"] += ok
                tally[g]["n"] += 1
                tally[g]["s"].append(secs)
                line[g] = (r.status_code, ok, d.get("method"), round(secs, 1))
            print(s["name"], line, flush=True)
            time.sleep(args.sleep)
    for g, v in tally.items():
        t = sorted(v["s"])
        print(f"handonly grow {g}: 정답 {v['ok']}/{v['n']} 시간 {statistics.median(t):.1f} / {t[min(len(t) - 1, int(.9 * len(t)))]:.1f} / {t[-1]:.1f}")


def show() -> None:
    rows = json.loads(OUT.read_text(encoding="utf-8"))
    for name, f in [("B·C·D", lambda r: r["set"] == "bcd"), ("매장 오전", lambda r: r["set"] == "visit" and r["name"] < "20261031_14"),
                    ("매장 오후", lambda r: r["set"] == "visit" and r["name"] >= "20261031_14")]:
        part = [r for r in rows if f(r)]
        if not part:
            continue
        print(f"-- {name} {len(part)}회")
        for g in sorted({k for r in part for k in r["by_grow"]}, key=int):
            v = [r["by_grow"][g] for r in part if g in r["by_grow"]]
            ok = [x for x in v if "ok" in x]
            t = sorted(x["s"] for x in v)
            print(f"grow {g}: 정답 {sum(x['ok'] for x in ok)}/{len(ok)} 장수 {sum(1 for x in v if x.get('count_ok'))}/{len(v)} "
                  f"만장일치 {sum(1 for x in v if x.get('unanimous'))} 오류 {sum(1 for x in v if 'error' in x)} "
                  f"시간 {statistics.median(t):.1f} / {t[min(len(t) - 1, int(.9 * len(t)))]:.1f} / {t[-1]:.1f}")
    print("-- 사진별(장수·정답)")
    for r in rows:
        print(r["name"][-6:], r["side"], {g: (v.get("n"), v.get("ok"), v.get("method")) for g, v in r["by_grow"].items()})


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--runs-bcd", type=int, default=2)
    p.add_argument("--runs-visit", type=int, default=1)
    p.add_argument("--grows", default="0,40,80")
    p.add_argument("--sleep", type=float, default=8)
    p.add_argument("--show", action="store_true")
    p.add_argument("--handonly", action="store_true")
    a = p.parse_args()
    show() if a.show else handonly(a) if a.handonly else run(a)
