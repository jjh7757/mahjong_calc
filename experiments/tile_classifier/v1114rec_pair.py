"""11-14 헤드 폰 실제 녹화(1496², 초당 10장)로 v1114 세트에 네 번째 화질 rec1496 을 더한다(2026-11-15, 녹화 세트 1단계 A).

녹화 experiments/visit_20261114/head_rec/rec_*/f_<epoch ms>.jpg 는 읽기만(이름은 os.scandir 로만 읽는다).
기존 data/v1114/ 와 v1114_*.py 는 읽기만.

가. 짝 찾기(manifest selected 189장 → 같은 순간 녹화 프레임)
  - 태블릿 시각 at(KST, 시간대 없음)을 epoch ms 로. 녹화 폴더마다 고르게 CAL_N 장을 ±COARSE_S 초 전부 비교해
    시계 차이(녹화 ms − 태블릿 ms)의 중앙값을 그 폴더의 offset 으로.
  - 장마다 at+offset ±NARROW_S 초 창의 모든 녹화 프레임과 비교, 점수가 가장 작은 것 = 짝.
    화료 사진(kind=win)만 창 [−60초, +3초](at 이 찍은 순간이 아닌 저장 시각이라 — 1단계 A 검토 뒤 계획 세션 결정, 옛 ±3초 결과는 narrow_old).
  - box_diff > 7 상자 눈 확인 그림 pair/review/(sheet_NN.jpg·빈 answers_NN.json·_FORMAT·_key·_shares). 답이 채워져 있으면 다시 안 만든다.
  - mid: scene_ambiguous 7장은 MID_SCENE_DECIDED(계획 세션 결정, scene_decided_by=plan), 거치 중 2장 setup=true.
    점수 = 밝기(L) 평균 절대 차이(0~255), 두 그림 모두 JPEG draft 로 1/4(374²) 디코드해서 비교.
    흉내 쪽 = data/v1114/images/q1496/<folder>/<name>(2992 를 2×2 평균한 사본).
  - 예상 시각(at+offset)이 녹화 폴더 처음~끝 밖이면 no_rec.
  - 적는 것: 녹화 파일, 시각 차(짝 ms − (at+offset)), 최적 점수, 창 중앙값, ±1장(±0.1초)·±0.5초 프레임 점수.
    짝 판정 문턱은 정하지 않는다(분포만 낸다).
  - 상자별 box_diff: dr/final/<판>.json 의 상자 box(x,y,w,h, 2992 좌표) ×0.5 → 1496 원래 크기 밝기 평균 절대 차이.
  - 짝 그림은 바이트 그대로 data/v1114rec/images/rec1496/<folder>/<name>.
나. 새 순간 고르기(라벨 없음) — 규칙은 미리 정한 것(작업 지시 그대로):
  - 판마다 짝 찾은 kind=frame 을 짝 녹화 시각순으로, 이웃 둘의 짝 시각 중간 = 후보, 틈 30초 미만 버림.
  - 후보 > 3 이면 np.linspace(0, n-1, 3) 을 반올림한 색인, 아니면 전부. 후보 시각에 가장 가까운 녹화 프레임 그대로.
  - r07_123310 건너뜀. 양 이웃 scene_round 같으면 물려받고, 다르면 scene_ambiguous(뒤 이웃 split 폴더에 임시로).

  python -X utf8 experiments/tile_classifier/v1114rec_pair.py
결과 data/v1114rec/pair/{pairs.json,summary.json,check_*.jpg,boxdiff_sheet_*.jpg,score_hist.png,boxdiff_hist.png},
     data/v1114rec/mid/{picks.json,overview_*.jpg}, data/v1114rec/images/rec1496/...
"""
from __future__ import annotations

import filecmp
import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REC = ROOT / "experiments" / "visit_20261114" / "head_rec"
SRC = HERE / "data" / "v1114"
OUT = HERE / "data" / "v1114rec"
Q = "rec1496"
KST = timezone(timedelta(hours=9))
CAL_N = 8          # 폴더마다 시계 차이 재는 장 수
COARSE_S = 15.0    # 넓은 창(±초)
NARROW_S = 3.0     # 좁은 창(±초)
WIN_BEFORE_S = 60.0  # 화료 사진 창: 예상 시각 −60초 ~ +3초(at 이 저장 시각이라, 11-15 계획 세션 결정)
WIN_AFTER_S = 3.0
REVIEW_MIN = 7.0     # box_diff 가 이보다 큰 상자 = 눈 확인 대상(계획 세션 결정)
REVIEW_PER = 20      # 장마다 칸(5열 × 4줄)
REVIEW_SEED = 20261115
# scene_ambiguous 중간 프레임의 장면 결정(계획 세션이 그림을 보고 정함, 11-15). None = 앞 이웃 scene_round 그대로.
MID_SCENE_DECIDED = {
    "r02_114700/mid_1794624443548": ("r02_114700", "train"),
    "r03_115446/mid_1794624918153": ("r03_115446", "train"),
    "r04_120417/mid_1794625490571": ("r04_120417", "dev"),
    "r06_121933/mid_1794626423835": ("r06_121933", "train"),
    "r10_130015/mid_1794628908540": None,
    "r12_131655/mid_1794629842937": ("r12_131655", "train"),
    "r19_142013/mid_1794633604401": ("r19_142013", "dev"),
}
MID_SETUP = {"r01_112804/mid_1794623624640", "r01_112804/mid_1794623866127"}  # 카메라 거치 중(그림은 그대로)
MID_GAP_S = 30.0
MID_MAX = 3
SKIP_MID = {"r07_123310"}
SMALL = 374        # 점수 비교 크기(1496/4)


def font(sz: int):
    for p in ("C:/Windows/Fonts/malgun.ttf", "C:/Windows/Fonts/arial.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def tablet_ms(at: str) -> int:
    return int(datetime.fromisoformat(at).replace(tzinfo=KST).timestamp() * 1000)


def ms_str(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, KST).strftime("%H:%M:%S.%f")[:-3]


def scan_rec() -> list[dict]:
    out = []
    for d in sorted(p for p in REC.iterdir() if p.is_dir() and p.name.startswith("rec_")):
        ms = sorted(int(e.name[2:-4]) for e in os.scandir(d) if e.name.startswith("f_") and e.name.endswith(".jpg"))
        out.append({"dir": d, "name": d.name, "ms": np.array(ms, np.int64)})
    return out


def rec_path(r: dict, ms: int) -> Path:
    return r["dir"] / f"f_{ms}.jpg"


def load_small(p: Path) -> np.ndarray:
    im = Image.open(p)
    im.draft("L", (SMALL, SMALL))
    im = im.convert("L")
    if im.size != (SMALL, SMALL):
        im = im.resize((SMALL, SMALL), Image.BILINEAR)
    return np.asarray(im, np.float32)


_cache: dict = {}


def rec_small(r: dict, ms: int) -> np.ndarray:
    k = (r["name"], ms)
    if k not in _cache:
        if len(_cache) > 4000:
            _cache.clear()
        _cache[k] = load_small(rec_path(r, ms))
    return _cache[k]


def score(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a - b).mean())


def window(r: dict, t: int, half_s: float) -> np.ndarray:
    a = r["ms"]
    lo, hi = np.searchsorted(a, t - half_s * 1000), np.searchsorted(a, t + half_s * 1000, "right")
    return np.arange(lo, hi)


def rec_of(recs: list[dict], t: int) -> dict | None:
    for r in recs:
        if r["ms"][0] <= t <= r["ms"][-1]:
            return r
    return None


def mimic_path(it: dict) -> Path:
    return SRC / "images" / "q1496" / it["folder"] / it["name"]


def nearest_idx(a: np.ndarray, t: float) -> int:
    i = int(np.searchsorted(a, t))
    if i <= 0:
        return 0
    if i >= len(a):
        return len(a) - 1
    return i if a[i] - t < t - a[i - 1] else i - 1


# ---------------------------------------------------------------- 가. 짝
def calibrate(recs, sel):
    cal = {}
    for r in recs:
        cand = [it for it in sel if r["ms"][0] + 20000 <= tablet_ms(it["at"]) <= r["ms"][-1] - 20000]
        cand.sort(key=lambda it: it["at"])
        idx = np.unique(np.linspace(0, len(cand) - 1, CAL_N).round().astype(int))
        rows = []
        for i in idx:
            it = cand[i]
            t = tablet_ms(it["at"])
            m = load_small(mimic_path(it))
            w = window(r, t, COARSE_S)
            sc = np.array([score(m, rec_small(r, int(r["ms"][j]))) for j in w])
            b = int(w[sc.argmin()])
            rows.append({"id": it["id"], "kind": it["kind"], "tablet_ms": t, "best_ms": int(r["ms"][b]),
                         "offset_ms": int(r["ms"][b]) - t, "best": round(float(sc.min()), 3),
                         "median": round(float(np.median(sc)), 3)})
        off = int(np.median([x["offset_ms"] for x in rows]))
        cal[r["name"]] = {"offset_ms": off, "spread_ms": [min(x["offset_ms"] for x in rows), max(x["offset_ms"] for x in rows)],
                          "samples": rows}
        print(r["name"], "offset", off, [x["offset_ms"] for x in rows])
    return cal


def box_diffs(it, r, best_ms, final_boxes):
    a = np.asarray(Image.open(mimic_path(it)).convert("L"), np.float32)
    b = np.asarray(Image.open(rec_path(r, best_ms)).convert("L"), np.float32)
    H, W = a.shape
    out = []
    for bx in final_boxes:
        x, y, w, h = [v * 0.5 for v in bx["box"]]
        x0, y0 = max(0, int(round(x))), max(0, int(round(y)))
        x1, y1 = min(W, int(round(x + w))), min(H, int(round(y + h)))
        if x1 - x0 < 2 or y1 - y0 < 2:
            d = None
        else:
            d = round(float(np.abs(a[y0:y1, x0:x1] - b[y0:y1, x0:x1]).mean()), 3)
        out.append({"box_id": bx["id"], "cls": bx["cls"], "role": bx.get("role"), "tile": bx.get("tile"),
                    "box_1496": [x0, y0, x1, y1],
                    "pts_1496": [[round(px * 0.5, 1), round(py * 0.5, 1)] for px, py in bx["pts"]] if bx.get("pts") else None,
                    "box_diff": d})
    return out


def load_final():
    fin = {}
    for p in sorted((SRC / "dr" / "final").glob("r*.json")):
        for im in json.loads(p.read_text(encoding="utf-8"))["images"]:
            fin[im["id"]] = im
    return fin


def pair_all(recs, sel, cal, fin):
    pairs = []
    for n, it in enumerate(sorted(sel, key=lambda x: x["at"])):
        t = tablet_ms(it["at"])
        row = {"id": it["id"], "round": it["round"], "kind": it["kind"], "folder": it["folder"], "name": it["name"],
               "split_final": it["split_final"], "scene_round": it["scene_round"], "at": it["at"], "tablet_ms": t}
        # 어느 폴더의 offset 을 쓰나: offset 을 더해 그 폴더 안에 들어가는 쪽
        r, off = None, None
        for rr in recs:
            o = cal[rr["name"]]["offset_ms"]
            if rr["ms"][0] <= t + o <= rr["ms"][-1]:
                r, off = rr, o
        if r is None:
            row.update({"status": "no_rec", "expected_ms": None})
            pairs.append(row)
            continue
        exp = t + off
        m = load_small(mimic_path(it))
        if it["kind"] == "win":
            # 화료 사진 at 은 저장 시각(찍은 순간보다 뒤) → [−WIN_BEFORE_S, +WIN_AFTER_S] 창(계획 세션 결정, 1단계 A 검토)
            a_ = r["ms"]
            w = np.arange(np.searchsorted(a_, exp - WIN_BEFORE_S * 1000), np.searchsorted(a_, exp + WIN_AFTER_S * 1000, "right"))
            wn = window(r, exp, NARROW_S)
            sn = np.array([score(m, rec_small(r, int(r["ms"][j]))) for j in wn])
            row["narrow_old"] = {"half_s": NARROW_S, "best": round(float(sn.min()), 3),
                                 "rec_file": f"f_{int(r['ms'][wn[sn.argmin()]])}.jpg",
                                 "dt_ms": int(r["ms"][wn[sn.argmin()]]) - exp}
        else:
            w = window(r, exp, NARROW_S)
        sc = np.array([score(m, rec_small(r, int(r["ms"][j]))) for j in w])
        k = int(sc.argmin())
        b = int(w[k])
        best_ms = int(r["ms"][b])

        def sc_at(j):
            if 0 <= j < len(r["ms"]):
                return round(score(m, rec_small(r, int(r["ms"][j]))), 3)
            return None
        j_m5 = nearest_idx(r["ms"], best_ms - 500)
        j_p5 = nearest_idx(r["ms"], best_ms + 500)
        row.update({
            "status": "paired", "rec_dir": r["name"], "rec_file": f"f_{best_ms}.jpg", "rec_ms": best_ms,
            "rec_time": ms_str(best_ms), "offset_ms": off, "expected_ms": exp, "dt_ms": best_ms - exp,
            "best": round(float(sc[k]), 3), "win_median": round(float(np.median(sc)), 3), "win_n": int(len(w)),
            "at_edge": bool(k == 0 or k == len(w) - 1),
            "prev": sc_at(b - 1), "next": sc_at(b + 1), "prev_dt_ms": int(r["ms"][b - 1]) - best_ms if b > 0 else None,
            "next_dt_ms": int(r["ms"][b + 1]) - best_ms if b + 1 < len(r["ms"]) else None,
            "m05": sc_at(j_m5), "p05": sc_at(j_p5),
            "m05_dt_ms": int(r["ms"][j_m5]) - best_ms, "p05_dt_ms": int(r["ms"][j_p5]) - best_ms,
        })
        row["window_s"] = [-WIN_BEFORE_S, WIN_AFTER_S] if it["kind"] == "win" else [-NARROW_S, NARROW_S]
        fb = fin.get(it["id"])
        row["boxes"] = box_diffs(it, r, best_ms, fb["boxes"]) if fb else None
        row["final_found"] = fb is not None
        dst = OUT / "images" / Q / it["folder"] / it["name"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not (dst.exists() and filecmp.cmp(dst, rec_path(r, best_ms), shallow=False)):  # 같으면 다시 안 씀(다른 에이전트가 읽는 중)
            shutil.copyfile(rec_path(r, best_ms), dst)
        pairs.append(row)
        if n % 20 == 0:
            print(n, it["id"], row["best"], row["win_median"], row["dt_ms"])
    return pairs


def q(v, ps=(0, 10, 25, 50, 75, 90, 95, 99, 100)):
    v = np.asarray([x for x in v if x is not None], float)
    if not len(v):
        return None
    return {f"p{p}": round(float(np.percentile(v, p)), 3) for p in ps} | {"n": int(len(v)), "mean": round(float(v.mean()), 3)}


def plots(pairs):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    P = [p for p in pairs if p["status"] == "paired"]
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.5))
    bins = np.linspace(0, max(max(p["win_median"] for p in P), 1) * 1.05, 60)
    ax[0].hist([p["best"] for p in P], bins, alpha=.7, label="best")
    ax[0].hist([p["win_median"] for p in P], bins, alpha=.6, label="window median")
    ax[0].hist([p["prev"] for p in P if p["prev"] is not None] + [p["next"] for p in P if p["next"] is not None], bins,
               alpha=.4, label="±1 frame", histtype="step", lw=2)
    ax[0].set_xlabel("mean |ΔL| (374²)"); ax[0].legend(); ax[0].set_title("pair scores")
    for kind, c in (("frame", "C0"), ("win", "C3")):
        pp = [p for p in P if p["kind"] == kind]
        ax[1].scatter([p["best"] for p in pp], [p["win_median"] for p in pp], s=14, c=c, label=kind)
    ax[1].set_xlabel("best"); ax[1].set_ylabel("window median"); ax[1].legend(); ax[1].set_title("best vs window median")
    fig.tight_layout(); fig.savefig(OUT / "pair" / "score_hist.png", dpi=90); plt.close(fig)
    bd = [b["box_diff"] for p in P for b in (p["boxes"] or []) if b["box_diff"] is not None]
    fig, ax = plt.subplots(1, 1, figsize=(8, 4))
    ax.hist(bd, bins=np.linspace(0, max(bd), 100))
    ax.set_yscale("log"); ax.set_xlabel("box_diff mean |ΔL| (1496)"); ax.set_title(f"box_diff, n={len(bd)}")
    fig.tight_layout(); fig.savefig(OUT / "pair" / "boxdiff_hist.png", dpi=90); plt.close(fig)


def label(im: Image.Image, text: str, sz=22):
    d = ImageDraw.Draw(im)
    f = font(sz)
    d.rectangle([0, 0, im.width, sz + 8], fill=(0, 0, 0))
    d.text((4, 2), text, fill=(255, 255, 0), font=f)


def check_sheets(pairs, recs):
    P = [p for p in pairs if p["status"] == "paired"]
    rmap = {r["name"]: r for r in recs}
    wins = [p for p in P if p["kind"] == "win"]
    frames = [p for p in P if p["kind"] == "frame"]
    rounds = sorted({p["round"] for p in frames})
    pick = [wins[i] for i in np.unique(np.linspace(0, len(wins) - 1, 3).round().astype(int))]
    ri = np.unique(np.linspace(0, len(rounds) - 1, 9).round().astype(int))
    for i in ri:
        fr = [p for p in frames if p["round"] == rounds[i]]
        pick.append(fr[len(fr) // 2])
    pick.sort(key=lambda p: p["at"])
    S = 600
    for k in range(0, len(pick), 4):
        chunk = pick[k:k + 4]
        sheet = Image.new("RGB", (S * 3, S * len(chunk)), (40, 40, 40))
        for j, p in enumerate(chunk):
            a = Image.open(mimic_path({"folder": p["folder"], "name": p["name"]})).convert("RGB")
            b = Image.open(rec_path(rmap[p["rec_dir"]], p["rec_ms"])).convert("RGB")
            d = np.abs(np.asarray(a.convert("L"), np.int16) - np.asarray(b.convert("L"), np.int16))
            dimg = Image.fromarray(np.clip(d * 4, 0, 255).astype(np.uint8)).convert("RGB")
            for c, (im, t) in enumerate(((a, f"흉내 q1496 {p['id']}"), (b, f"녹화 {p['rec_file']} {p['rec_time']}"),
                                         (dimg, f"|차|×4 best {p['best']} med {p['win_median']} dt {p['dt_ms']}ms"))):
                im = im.resize((S, S), Image.BILINEAR)
                label(im, t, 15)
                sheet.paste(im, (c * S, j * S))
        sheet.save(OUT / "pair" / f"check_{k // 4 + 1}.jpg", quality=85)
    return [p["id"] for p in pick]


def boxdiff_sheets(pairs, recs):
    rmap = {r["name"]: r for r in recs}
    P = [p for p in pairs if p["status"] == "paired" and p["boxes"]]
    allb = [(b["box_diff"], p, b) for p in P for b in p["boxes"] if b["box_diff"] is not None]
    allb.sort(key=lambda x: -x[0])
    rng = np.random.default_rng(20261115)
    n = len(allb)
    frb = [x for x in allb if x[1]["kind"] == "frame"]
    nf = len(frb)
    sets = {
        "top": allb[:40],
        "top_frame": frb[:40],
        "p99_frame": [frb[i] for i in sorted(rng.choice(np.arange(int(nf * 0.005), int(nf * 0.02)), 30, replace=False))],
        "p99": [allb[i] for i in sorted(rng.choice(np.arange(int(n * 0.005), int(n * 0.02)), 30, replace=False))],
        "p90": [allb[i] for i in sorted(rng.choice(np.arange(int(n * 0.05), int(n * 0.10)), 30, replace=False))],
        "median": [allb[i] for i in sorted(rng.choice(np.arange(int(n * 0.45), int(n * 0.55)), 20, replace=False))],
    }
    imcache = {}

    def get(p):
        if p["id"] not in imcache:
            imcache.clear()
            imcache[p["id"]] = (Image.open(mimic_path(p)).convert("RGB"),
                                Image.open(rec_path(rmap[p["rec_dir"]], p["rec_ms"])).convert("RGB"))
        return imcache[p["id"]]
    C = 150
    out = {}
    for nm, rows in sets.items():
        cols = 5
        rows_n = (len(rows) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * (2 * C + 10), rows_n * (C + 30)), (30, 30, 30))
        d = ImageDraw.Draw(sheet)
        f = font(12)
        order = sorted(rows, key=lambda x: x[1]["id"])
        for i, (v, p, b) in enumerate(order):
            a, r = get(p)
            x0, y0, x1, y1 = b["box_1496"]
            m = max(x1 - x0, y1 - y0) // 4 + 6
            box = (max(0, x0 - m), max(0, y0 - m), min(1496, x1 + m), min(1496, y1 + m))
            ca = a.crop(box); cr = r.crop(box)
            s = C / max(ca.size)
            sz = (max(1, int(ca.width * s)), max(1, int(ca.height * s)))
            gx, gy = (i % cols) * (2 * C + 10), (i // cols) * (C + 30)
            sheet.paste(ca.resize(sz), (gx, gy + 28)); sheet.paste(cr.resize(sz), (gx + C, gy + 28))
            d.text((gx + 2, gy + 1), f"{p['id'].split('/')[0][:3]} {p['name'][:-4][-12:]} #{b['box_id']}", fill=(255, 255, 0), font=f)
            d.text((gx + 2, gy + 14), f"{b['cls']} {b['role'] or ''} {b['tile'] or ''} d={v}", fill=(160, 255, 160), font=f)
        path = OUT / "pair" / f"boxdiff_sheet_{nm}.jpg"
        sheet.save(path, quality=88)
        out[nm] = [{"id": p["id"], "box_id": b["box_id"], "box_diff": v} for v, p, b in order]
    return out


REVIEW_FORMAT = {
    "what": "box_diff > 7 인 상자 눈 확인. 칸 = [왼쪽] 흉내 q1496(라벨을 단 2992 그림을 2×2 평균) [오른쪽] 같은 순간 헤드 녹화 rec1496. "
            "노란 테두리 = 라벨 상자(왼쪽 그림 기준). 오른쪽 녹화에서 그 자리가 어떤지 판정한다.",
    "verdict": {
        "same": "녹화에도 같은 패가 상자 자리에 절반 넘게 보임 — 흐림·밝기 차이는 same",
        "occluded": "녹화에서 손 등에 절반 넘게 가렸거나 그 자리에 패가 없음",
        "moved": "같은 패가 보이지만 상자와 뚜렷이 어긋남",
        "different": "그 자리에 다른 패",
        "unsure": "판단 못 함(note 에 이유)",
    },
    "answers": "answers_NN.json 의 cells[칸 번호] = {verdict, note}. 칸 번호는 그림의 숫자. _key.json 은 열지 않는다.",
}


def review_sheets(pairs, recs):
    rmap = {r["name"]: r for r in recs}
    RV = OUT / "pair" / "review"
    RV.mkdir(parents=True, exist_ok=True)
    rows = sorted(((p, b) for p in pairs if p["status"] == "paired" and p["boxes"]
                   for b in p["boxes"] if b["box_diff"] is not None and b["box_diff"] > REVIEW_MIN),
                  key=lambda x: (x[0]["id"], str(x[1]["box_id"])))
    order = np.random.default_rng(REVIEW_SEED).permutation(len(rows))
    rows = [rows[i] for i in order]
    # 옛 sheet 지우기(답이 채워진 answers 가 있으면 멈춤)
    for f in RV.glob("answers_*.json"):
        if any(c.get("verdict") for c in json.loads(f.read_text(encoding="utf-8"))["cells"].values()):
            raise SystemExit(f"{f} 에 답이 있음 — review 를 다시 만들지 않는다")
    for f in list(RV.glob("sheet_*.jpg")) + list(RV.glob("answers_*.json")):
        f.unlink()
    PN, GAP, HEAD, COLS = 300, 8, 34, 5
    cw, ch = 2 * PN + GAP + 16, PN + HEAD + 12
    fnt = font(26)
    key, sheets = {}, []
    imc: dict = {}

    def get(p):
        if p["id"] not in imc:
            imc.clear()
            imc[p["id"]] = (Image.open(mimic_path(p)).convert("RGB"),
                            Image.open(rec_path(rmap[p["rec_dir"]], p["rec_ms"])).convert("RGB"))
        return imc[p["id"]]
    for s in range(0, len(rows), REVIEW_PER):
        nn = f"{s // REVIEW_PER + 1:02d}"
        chunk = rows[s:s + REVIEW_PER]
        nrow = (len(chunk) + COLS - 1) // COLS
        sheet = Image.new("RGB", (COLS * cw, nrow * ch), (25, 25, 25))
        d = ImageDraw.Draw(sheet)
        key[nn] = {}
        for i, (p, b) in enumerate(chunk):
            cell = i + 1
            a, r = get(p)
            x0, y0, x1, y1 = b["box_1496"]
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            half = 1.5 * max(x1 - x0, y1 - y0)
            crop = (int(cx - half), int(cy - half), int(cx + half), int(cy + half))
            sc = PN / (crop[2] - crop[0])
            gx, gy = (i % COLS) * cw + 8, (i // COLS) * ch + 4
            d.text((gx, gy), str(cell), fill=(255, 255, 0), font=fnt)
            pts = b.get("pts_1496") or [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
            poly = [((px - crop[0]) * sc, (py - crop[1]) * sc) for px, py in pts]
            for k, im in enumerate((a, r)):
                pan = im.crop(crop).resize((PN, PN), Image.BICUBIC)  # 그림 밖은 검게
                pd = ImageDraw.Draw(pan)
                pd.polygon(poly, outline=(255, 230, 0), width=2)
                sheet.paste(pan, (gx + k * (PN + GAP), gy + HEAD))
            key[nn][str(cell)] = {"id": p["id"], "kind": p["kind"], "box_id": b["box_id"], "box_diff": b["box_diff"],
                                  "cls": b["cls"], "role": b["role"], "tile": b["tile"], "rec_file": p["rec_file"]}
        sheet.save(RV / f"sheet_{nn}.jpg", quality=90)
        (RV / f"answers_{nn}.json").write_text(json.dumps({
            "sheet": f"sheet_{nn}.jpg", "reviewer": None,
            "cells": {str(c + 1): {"verdict": None, "note": ""} for c in range(len(chunk))}},
            ensure_ascii=False, indent=1), encoding="utf-8")
        sheets.append(nn)
    (RV / "_key.json").write_text(json.dumps({"_note": "검토자는 열지 않는다", "min_box_diff": REVIEW_MIN, "seed": REVIEW_SEED,
                                              "sheets": key}, ensure_ascii=False, indent=1), encoding="utf-8")
    (RV / "_FORMAT.json").write_text(json.dumps(REVIEW_FORMAT, ensure_ascii=False, indent=1), encoding="utf-8")
    h = (len(sheets) + 1) // 2
    (RV / "_shares.json").write_text(json.dumps({
        "A": {"sheets": [f"sheet_{n}.jpg" for n in sheets[:h]], "answers": [f"answers_{n}.json" for n in sheets[:h]]},
        "B": {"sheets": [f"sheet_{n}.jpg" for n in sheets[h:]], "answers": [f"answers_{n}.json" for n in sheets[h:]]},
        "rule": "검토자는 자기 몫 answers 파일만 쓴다. _key.json 은 열지 않는다. verdict 뜻은 _FORMAT.json."},
        ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    return {"n_boxes": len(rows), "n_sheets": len(sheets),
            "by_kind": dict(Counter(p["kind"] for p, b in rows)),
            "by_cls": dict(Counter(b["cls"] for p, b in rows)),
            "by_kind_cls": dict(Counter(f"{p['kind']}/{b['cls']}" for p, b in rows)),
            "n_images": len({p["id"] for p, b in rows})}


# ---------------------------------------------------------------- 나. 새 순간
def mids(pairs, recs):
    rmap = {r["name"]: r for r in recs}
    picks, notes = [], []
    by_round: dict[str, list] = {}
    for p in pairs:
        if p["kind"] == "frame" and p["status"] == "paired":
            by_round.setdefault(p["round"], []).append(p)
    for rd in sorted(by_round):
        if rd in SKIP_MID:
            continue
        fr = sorted(by_round[rd], key=lambda p: p["rec_ms"])
        cands = []
        for a, b in zip(fr, fr[1:]):
            gap = (b["rec_ms"] - a["rec_ms"]) / 1000
            if gap < MID_GAP_S:
                continue
            cands.append((a, b, (a["rec_ms"] + b["rec_ms"]) / 2, gap))
        if len(cands) > MID_MAX:
            idx = np.linspace(0, len(cands) - 1, MID_MAX).round().astype(int)
            chosen = [cands[i] for i in idx]
        else:
            chosen = cands
        for a, b, t, gap in chosen:
            r = rec_of(recs, int(t))
            if r is None or a["rec_dir"] != b["rec_dir"]:
                notes.append(f"{rd}: 중간 시각 {ms_str(int(t))} 이 녹화 폴더 밖이거나 이웃이 다른 폴더 — 건너뜀")
                continue
            j = nearest_idx(r["ms"], t)
            ms = int(r["ms"][j])
            amb = a["scene_round"] != b["scene_round"]
            split = b["split_final"] if amb else a["split_final"]
            if not amb and a["split_final"] != b["split_final"]:
                notes.append(f"{rd}: 이웃 scene_round 같은데 split 다름 {a['id']} {b['id']}")
            pid = f"{rd}/mid_{ms}"
            rel = f"images/{Q}/{split}/{rd}/mid_{ms}.jpg"
            dst = OUT / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists():  # 다른 에이전트가 읽는 중 — 있는 그림은 다시 쓰지 않는다
                shutil.copyfile(rec_path(r, ms), dst)
            pk = {"id": pid, "round": rd, "rec_dir": r["name"], "rec_file": f"f_{ms}.jpg", "rec_ms": ms,
                  "rec_time": ms_str(ms), "target_ms": int(round(t)), "dt_ms": int(ms - t), "gap_s": round(gap, 1),
                  "prev_id": a["id"], "next_id": b["id"], "prev_rec_ms": a["rec_ms"], "next_rec_ms": b["rec_ms"],
                  "scene_ambiguous": amb,
                  "scene_round": None if amb else a["scene_round"], "split": None if amb else a["split_final"],
                  "scene_round_prev": a["scene_round"], "scene_round_next": b["scene_round"],
                  "split_prev": a["split_final"], "split_next": b["split_final"],
                  "path": rel, "n_candidates": len(cands)}
            if amb and pid in MID_SCENE_DECIDED:
                dec = MID_SCENE_DECIDED[pid]
                pk["scene_round"], pk["split"] = dec if dec else (a["scene_round"], a["split_final"])
                pk["scene_decided_by"] = "plan"
            elif amb:
                notes.append(f"{pid}: scene_ambiguous 인데 MID_SCENE_DECIDED 에 없음")
            if pid in MID_SETUP:
                pk["setup"] = True
            picks.append(pk)
    return picks, notes


def mid_overview(picks):
    T = 360
    cols = 6
    for k in range(0, len(picks), 24):
        chunk = picks[k:k + 24]
        rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * T, rows * T), (30, 30, 30))
        for i, p in enumerate(chunk):
            im = Image.open(OUT / p["path"]).convert("RGB").resize((T, T), Image.BILINEAR)
            label(im, f"{p['id']}{' 모호' if p['scene_ambiguous'] else ''}", 13)
            sheet.paste(im, ((i % cols) * T, (i // cols) * T))
        sheet.save(OUT / "mid" / f"overview_{k // 24 + 1}.jpg", quality=85)


def main():
    (OUT / "pair").mkdir(parents=True, exist_ok=True)
    (OUT / "mid").mkdir(parents=True, exist_ok=True)
    man = json.loads((SRC / "manifest.json").read_text(encoding="utf-8"))
    sel = [it for it in man["items"] if it.get("selected")]
    recs = scan_rec()
    cal = calibrate(recs, sel)
    fin = load_final()
    pairs = pair_all(recs, sel, cal, fin)
    plots(pairs)
    checks = check_sheets(pairs, recs)
    bsheets = boxdiff_sheets(pairs, recs)
    review_info = review_sheets(pairs, recs)
    P =[p for p in pairs if p["status"] == "paired"]
    bd = [b["box_diff"] for p in P for b in (p["boxes"] or []) if b["box_diff"] is not None]
    per_img_max = [max((b["box_diff"] for b in p["boxes"] if b["box_diff"] is not None), default=None) for p in P if p["boxes"]]
    (OUT / "pair" / "pairs.json").write_text(json.dumps({
        "made": "v1114rec_pair.py", "quality": Q, "score": "mean |ΔL| 0~255, 374² (JPEG draft 1/4), 흉내 q1496 vs 녹화",
        "box_diff": "dr/final 상자 box ×0.5, 1496 원래 크기 mean |ΔL|", "calibration": cal,
        "coarse_s": COARSE_S, "narrow_s": NARROW_S, "pairs": pairs}, ensure_ascii=False, indent=1), encoding="utf-8")
    picks, notes = mids(pairs, recs)
    mid_overview(picks)
    (OUT / "mid" / "picks.json").write_text(json.dumps({
        "made": "v1114rec_pair.py", "rule": f"판마다 짝 찾은 frame 이웃 짝 시각 중간, 틈 <{MID_GAP_S}s 버림, >{MID_MAX} 이면 linspace 색인, "
                                             f"가장 가까운 녹화 프레임 그대로, {sorted(SKIP_MID)} 건너뜀",
        "notes": notes, "picks": picks}, ensure_ascii=False, indent=1), encoding="utf-8")
    summ = {
        "calibration": {k: {"offset_ms": v["offset_ms"], "spread_ms": v["spread_ms"],
                            "samples": [(s["id"], s["offset_ms"], s["best"], s["median"]) for s in v["samples"]]} for k, v in cal.items()},
        "n_selected": len(sel), "n_paired": len(P), "n_no_rec": len(pairs) - len(P),
        "no_rec": [p["id"] for p in pairs if p["status"] != "paired"],
        "paired_by_kind": {k: sum(1 for p in P if p["kind"] == k) for k in ("frame", "win")},
        "at_edge": [p["id"] for p in P if p["at_edge"]],
        "final_missing": [p["id"] for p in P if not p["final_found"]],
        "dist": {"best": q([p["best"] for p in P]), "win_median": q([p["win_median"] for p in P]),
                 "ratio_best_over_median": q([p["best"] / p["win_median"] for p in P if p["win_median"]]),
                 "prev": q([p["prev"] for p in P]), "next": q([p["next"] for p in P]),
                 "m05": q([p["m05"] for p in P]), "p05": q([p["p05"] for p in P]),
                 "dt_ms": q([p["dt_ms"] for p in P]),
                 "best_frame": q([p["best"] for p in P if p["kind"] == "frame"]),
                 "best_win": q([p["best"] for p in P if p["kind"] == "win"]),
                 "box_diff": q(bd, (0, 50, 75, 90, 95, 98, 99, 99.5, 99.9, 100)),
                 "box_diff_frame": q([b["box_diff"] for p in P if p["kind"] == "frame" for b in (p["boxes"] or [])
                                      if b["box_diff"] is not None], (0, 50, 75, 90, 95, 98, 99, 99.5, 99.9, 100)),
                 "box_diff_win": q([b["box_diff"] for p in P if p["kind"] == "win" for b in (p["boxes"] or [])
                                    if b["box_diff"] is not None], (0, 50, 75, 90, 95, 98, 99, 99.5, 99.9, 100)),
                 "box_diff_img_max": q(per_img_max)},
        # 움직임이 있는 프레임(창 중앙값이 best 의 3배 이상 = 시각이 뾰족하게 정해짐)의 dt — 시계 차이 검증용
        "sharp_frame_dt_ms": q([p["dt_ms"] for p in P if p["kind"] == "frame" and p["win_median"] >= 3 * p["best"]]),
        "sharp_frame_dt_by_rec": {rn: q([p["dt_ms"] for p in P if p["kind"] == "frame" and p["rec_dir"] == rn
                                         and p["win_median"] >= 3 * p["best"]]) for rn in cal},
        "win_pairs": [{"id": p["id"], "rec_file": p["rec_file"], "best": p["best"], "dt_ms": p["dt_ms"],
                       "win_median": p["win_median"], "at_edge": p["at_edge"], "narrow_old": p.get("narrow_old")}
                      for p in P if p["kind"] == "win"],
        "review": review_info,
        "worst_best": sorted([(p["id"], p["best"], p["win_median"], p["dt_ms"]) for p in P], key=lambda x: -x[1])[:15],
        "check_ids": checks, "boxdiff_sheets": bsheets,
        "mid": {"n": len(picks), "by_round": {rd: sum(1 for x in picks if x["round"] == rd) for rd in sorted({x["round"] for x in picks})},
                "ambiguous": [x["id"] for x in picks if x["scene_ambiguous"]], "notes": notes},
    }
    (OUT / "pair" / "summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: summ[k] for k in ("n_paired", "n_no_rec", "no_rec", "at_edge", "final_missing")}, ensure_ascii=False))
    print(json.dumps(summ["dist"], ensure_ascii=False))
    print(json.dumps(summ["mid"], ensure_ascii=False))


if __name__ == "__main__":
    main()
