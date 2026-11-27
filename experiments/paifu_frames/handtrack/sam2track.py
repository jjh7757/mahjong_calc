"""패마다 SAM 2 로 따라가 나간 칸 · 들어간 칸 읽기(2026-11-18, 계획서 3단계 "추가 22"). API 호출 없음 · CPU.

사용자 "외부 모델 중에 쓸 만한 거 없니" → "SAM 2 돌려 봐". 칸 참/빔(slotgrid · opsfill)은 "어느 패가 움직였나" 를 못 가른다 →
패 하나하나를 영상 분할 추적으로 따라가면 갈리나(가능성만 — 본 판, 시험 아님).

  <venv>/python -X utf8 sam2track.py prep            # 차례마다 프레임 수 · 시작/끝 줄 시각만
  <venv>/python -X utf8 sam2track.py run [--ids a,b] [--model t|s] [--step 2]
  python -X utf8 sam2track.py score                  # 저장된 추적 → k · j 판정
  python -X utf8 sam2track.py show <id> [--every 5]  # 마스크 겹친 프레임 띠(판정 뒤 원인 보기용)

SAM 2 는 공식 저장소(facebookresearch/sam2)를 C:\\Users\\jjh7757\\dev\\venvs\\sam2_meta 에 설치, 가중치는 venvs\\sam2_ckpt.
결과 = results/handtrack/_work/sam2_1118/<id>/(프레임 jpg · track.json) · score.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import slotgrid as sg  # noqa: E402
import turncut as tc  # noqa: E402

OUT = hc.WORK / "sam2_1118"
CKPT = Path(r"C:\Users\jjh7757\dev\venvs\sam2_ckpt")
CFG = {"t": ("configs/sam2.1/sam2.1_hiera_t.yaml", "sam2.1_hiera_tiny.pt"), "s": ("configs/sam2.1/sam2.1_hiera_s.yaml", "sam2.1_hiera_small.pt")}
TURNS = {"r16_d16": "어려움", "r13_d02": "어려움", "r12_d02": "어려움", "r16_d08": "쉬움", "r13_d04": "쉬움"}
GONE_AREA, GONE_Y = 0.30, 0.6


def ms_of(tstr: str, ref: int) -> int:
    """'mm:ss.s' → ref 와 가장 가까운 시각(ms) — edgecount.ms_of 와 같음."""
    h = int(hc.hms(ref)[:2])
    return min((hc.to_ms(f"{x:02d}:{tstr}") for x in (h - 1, h, h + 1) if 0 <= x < 24), key=lambda m: abs(m - ref))


def truth_all() -> dict:
    t = dict(hc.jload(tc.BASE / "truth_final.json"))
    t.update(hc.jload(hc.WORK / "slotgrid_1117" / "truth_r13.json"))
    fx = hc.WORK / "slotgrid_1117" / "truth_fix_1120.json"   # 11-20 사용자가 영상으로 고친 칸(r16_d13 옮김 하나 더) — 그 전 표의 숫자는 옛 정답 기준
    for k, v in (hc.jload(fx) if fx.exists() else {}).items():
        t[k] = {**t[k], **v}
    return t


GAMES = ("r12_131655", "r16_135321", "r17_140450", "r19_142013", "r13_132644", "r15_134151", "L16_135321", "r18_141259")   # 11-19: r15 · L16 더함(L16 = r16 판의 왼쪽 자리)


def turn_of(tid: str):
    gid = next((g for g in GAMES if g[:3] == tid[:3]), None)
    if gid is None:
        raise KeyError(f"{tid}: sam2track.GAMES 에 이 앞글자({tid[:3]})의 판이 없다")
    t = next((t for t in tc.turns_of(gid) if t["id"] == tid), None)
    if t is None:
        raise KeyError(f"{tid}: {gid} 의 새 묶음 차례에 없다")
    return gid, t


# ------------------------------------------------------------------ 좌표: sheet_band 시점 ↔ 원본 ↔ 넓힌 띠 시점
def wide_band(band: list) -> list:
    x0, y0, x1, y1 = band
    w, h = x1 - x0, y1 - y0
    if w < h:
        e = max(0, (h // 2 - w) // 2)
        return [max(0, x0 - e), y0, min(1496, x1 + e), y1]
    e = max(0, (w // 2 - h) // 2)
    return [x0, max(0, y0 - e), x1, min(1496, y1 + e)]


def from_view_xy(pt, band: list, side: str):
    """band_crop 그림 좌표 → 원본 좌표(to_view_xy 의 거꾸로)."""
    x0, y0, x1, y1 = band
    k = hc.ROT[side] // 90 % 4
    w, h = (x1 - x0, y1 - y0)
    sizes = [(w, h)]
    for _ in range(k):
        w, h = h, w
        sizes.append((w, h))
    x, y = pt
    for i in range(k, 0, -1):          # (x, y) ← (W−1−y', x') 로 한 번씩 되돌림, W = 돌리기 전 폭
        W = sizes[i - 1][0]
        x, y = W - 1 - y, x
    return x + x0, y + y0


def remap_box(b, band: list, band2: list, side: str):
    """sheet_band 시점 상자 [x0, x1, y0, y1] → 넓힌 띠 시점 [x0, y0, x1, y1]."""
    ps = [hc.to_view_xy(from_view_xy(p, band, side), band2, side) for p in ((b[0], b[2]), (b[1], b[3]))]
    xs, ys = [p[0] for p in ps], [p[1] for p in ps]
    return [min(xs), min(ys), max(xs), max(ys)]


def plan_start(tid: str):
    """plan 의 앞 절반(시작 줄) → (gid, t, cfg, det, n, w0, w1, frs, a). a = slotgrid.anchor(창 안 캐시 프레임), 없으면 None.
    8-28(11-27): slotgrid detect --ends 도 이것 · end_dms · end_n 을 불러 끝 줄 조건을 plan 과 같게 씀(규칙을 둘로 베끼지 않음)."""
    gid, t = turn_of(tid)
    cfg = hc.config(gid)
    det = {int(k): v for k, v in hc.jload(sg.OUT / f"det_{gid}.json").items()}
    n = t["n_calc"]
    w0, w1 = sg.window(t)
    frs = [(ms, det[ms]) for ms in sorted(det) if w0 <= ms <= w1]
    return gid, t, cfg, det, n, w0, w1, frs, sg.anchor(frs, n)


def end_dms(t: dict, a) -> int:
    """끝 줄을 찾기 시작하는 시각 = 버림 + 1초(a = 시작 줄 — 시각의 시 자리를 고르는 기준)."""
    return ms_of(t["cut"]["discard"], a[4]) + 1000


def end_n(d: dict, n: int, yc: float, hh: float) -> bool:
    """끝 줄 첫 규칙: 시작 줄 높이(yc ± 0.5·hh)의 상자가 정확히 n 개(가림은 따지지 않음)."""
    return sum(abs((b[2] + b[3]) / 2 - yc) <= 0.5 * hh for b in d["b"]) == n


def plan(tid: str) -> dict:
    gid, t, cfg, det, n, w0, w1, frs, a = plan_start(tid)
    if a is None:
        return {"id": tid, "gid": gid, "ok": False, "why": "시작 줄 없음"}
    # 끝 줄: 버림 + 1초 뒤, 창 끝에서 거꾸로, 줄 높이 상자가 N개인 첫 프레임(가림은 따지지 않음 — 손이 줄 끝 옆에 머무는 사람이 있다)
    dms = end_dms(t, a)
    yc, hh = a[2], a[3]
    e = next(((ms, d) for ms, d in frs[::-1] if ms >= dms and end_n(d, n, yc, hh)), None)
    rule, line, e_row = "fixed", None, None
    if e is None:   # 보조 규칙(11-19): 버린 뒤 줄을 앞으로 밀고 비스듬히 놓은 사람(r19 4순) — 같은 프레임 순서로 기운 줄 선을 다시 맞춤
        e = next(((ms, d) for ms, d in frs[::-1] if ms >= dms and end_row_refit(d["b"], n, yc, hh) is not None), None)
        if e is not None:
            rule = "refit"
            e_row, line = end_row_refit(e[1]["b"], n, yc, hh)
    if e is None:
        return {"id": tid, "gid": gid, "ok": False, "why": "끝 줄 없음"}
    e = (None, None, None, None, e[0])
    band, side = cfg["sheet_band"], cfg["side"]
    band2 = wide_band(band)
    pick = lambda ms: sorted([b for b in det[ms]["b"] if abs((b[2] + b[3]) / 2 - yc) <= 0.5 * hh], key=lambda b: b[0])  # noqa: E731
    out = {"id": tid, "gid": gid, "ok": True, "n": n, "side": side, "band": band, "band2": band2, "w0": w0, "w1": w1,
           "a_ms": a[4], "e_ms": e[4], "hh": a[3],
           "a_boxes": [remap_box(b, band, band2, side) for b in pick(a[4])],
           "e_boxes": [remap_box(b, band, band2, side) for b in (pick(e[4]) if e_row is None else e_row)],
           "e_rule": rule}
    if line is not None:
        out["e_line"] = line   # sheet_band 시점(det 상자 좌표) 줄 가운데 선 y = a + b·x
    return out


REFIT_BAND, REFIT_ROW, REFIT_BMAX = 1.5, 0.5, 0.15   # 넓은 띠(× hh) · 줄 선 둘레(× hh) · 기울기 한도
REFIT_GAP = (0.7, 1.4)                               # 이웃 가운데 간격 / 패 폭 중앙값 — 다른 사람 소매 · 손 상자 거르기


def end_row_refit(bs: list, n: int, yc: float, hh: float):
    """끝 줄 보조 규칙: yc ± 1.5·hh 상자로 줄 선 y = a + b·x 를 맞추고(두 번 — 잔차 1.0·hh 넘는 것 빼고 다시, 0.5·hh 로 한 번 더),
    선 ± 0.5·hh 안 상자가 정확히 n 개 · |b| ≤ 0.15 · 이웃 간격이 패 폭의 0.7 ~ 1.4배면 (x 순 상자, [a, b]) — 아니면 None.
    상자 = det 의 [x0, x1, y0, y1](sheet_band 시점)."""
    cx = lambda x: (x[0] + x[1]) / 2  # noqa: E731
    cy = lambda x: (x[2] + x[3]) / 2  # noqa: E731
    cand = [x for x in bs if abs(cy(x) - yc) <= REFIT_BAND * hh]
    if len(cand) < n:
        return None
    a, b = yc, 0.0
    inl = cand
    for thr in (1.0, REFIT_ROW, REFIT_ROW):
        if len(inl) < 2 or len({cx(x) for x in inl}) < 2:
            return None
        b, a = (float(v) for v in np.polyfit([cx(x) for x in inl], [cy(x) for x in inl], 1))
        inl = [x for x in cand if abs(cy(x) - (a + b * cx(x))) <= thr * hh]
    if abs(b) > REFIT_BMAX:
        return None
    row = sorted([x for x in bs if abs(cy(x) - (a + b * cx(x))) <= REFIT_ROW * hh], key=lambda x: x[0])
    if len(row) != n:
        return None
    w = float(np.median([x[1] - x[0] for x in row]))
    gaps = [cx(q) - cx(p) for p, q in zip(row, row[1:])]
    if not all(REFIT_GAP[0] * w <= g <= REFIT_GAP[1] * w for g in gaps):
        return None
    return row, [round(a, 3), round(b, 5)]


def run_dir(tid: str, a) -> Path:
    """결과 폴더 — CPU 는 <id>_<모델>(처음 잰 것), 다른 장치는 뒤에 _<장치>."""
    return OUT / (f"{tid}_{a.model}" + ("" if a.device == "cpu" else f"_{a.device}"))


def frame_list(p: dict, step: int) -> list:
    fs = [int(x) for x in hc.frames(hc.rec_of(p["a_ms"])) if p["a_ms"] <= x <= p["e_ms"]]
    out = fs[::step]
    if out[-1] != p["e_ms"]:
        out.append(p["e_ms"])
    return out


def cmd_prep(a):
    for tid in (a.ids.split(",") if a.ids else TURNS):
        p = plan(tid)
        if not p["ok"]:
            print(tid, p["why"])
            continue
        fl = frame_list(p, a.step)
        print(f"{tid} {TURNS.get(tid, '')} n={p['n']} 시작 {hc.mss(p['a_ms'])} 끝 {hc.mss(p['e_ms'])} 프레임 {len(fl)} · 띠 {p['band2']} · 상자 {len(p['a_boxes'])}/{len(p['e_boxes'])}")


def cmd_run(a):
    import torch
    from sam2.build_sam import build_sam2_video_predictor
    torch.set_num_threads(16)
    if a.device == "xpu":
        assert torch.xpu.is_available(), "XPU 없음 — venvs/sam2_xpu 의 python 으로 돌릴 것"
    cfg, ck = CFG[a.model]
    pred = build_sam2_video_predictor(cfg, str(CKPT / ck), device=a.device)
    for tid in (a.ids.split(",") if a.ids else TURNS):
        p = plan(tid)
        if not p["ok"]:
            print(tid, p["why"])
            continue
        d = run_dir(tid, a)
        fd = d / "frames"
        fd.mkdir(parents=True, exist_ok=True)
        fl = frame_list(p, a.step)
        for i, ms in enumerate(fl):
            f = fd / f"{i:05d}.jpg"
            if not f.exists():
                Image.fromarray(hc.band_crop(hc.load(ms), p["band2"], p["side"])).save(f, quality=95)
        t0 = time.time()
        with torch.inference_mode():
            st = pred.init_state(video_path=str(fd), offload_video_to_cpu=True, offload_state_to_cpu=True)
            for oid, b in enumerate(p["a_boxes"], 1):
                pred.add_new_points_or_box(st, frame_idx=0, obj_id=oid, box=np.array(b, np.float32))
            rec = {}
            masks_keep = {}
            for fi, oids, logits in pred.propagate_in_video(st):
                row = {}
                for oid, lg in zip(oids, logits):
                    m = (lg[0] > 0).cpu().numpy()
                    ys, xs = np.nonzero(m)
                    row[int(oid)] = [int(m.sum()), float(xs.mean()) if len(xs) else None, float(ys.mean()) if len(ys) else None]
                    masks_keep.setdefault(fi, {})[int(oid)] = np.packbits(m)
                rec[int(fi)] = row
                if fi % 20 == 0:
                    print(f"  {tid} {fi}/{len(fl)} {time.time() - t0:.0f}s", flush=True)
        shape = list(np.asarray(Image.open(fd / "00000.jpg")).shape[:2])
        np.savez_compressed(d / "masks.npz", **{f"{fi}_{oid}": v for fi, r in masks_keep.items() for oid, v in r.items()})
        hc.jsave(d / "track.json", {"plan": p, "frames": fl, "shape": shape, "model": a.model, "device": a.device, "sec": round(time.time() - t0, 1), "rec": rec}, indent=None)
        print(f"{tid} 끝 {time.time() - t0:.0f}s ({len(fl)}프레임)", flush=True)


def judge(tr: dict) -> dict:
    p, rec = tr["plan"], tr["rec"]
    first, last = rec["0"], rec[str(len(tr["frames"]) - 1)]
    eb = p["e_boxes"]
    yc = float(np.median([(b[1] + b[3]) / 2 for b in eb]))
    gone, stay = [], []
    for oid in range(1, p["n"] + 1):
        a0, l = first[str(oid)][0], last[str(oid)]
        if l[0] < GONE_AREA * a0 or l[2] is None or abs(l[2] - yc) > GONE_Y * p["hh"]:
            gone.append(oid)
        else:
            stay.append(oid)
    k = gone[0] if len(gone) == 1 else None
    cx = [(b[0] + b[2]) / 2 for b in eb]
    used: dict = {}
    for oid in stay:
        bi = int(np.argmin([abs(last[str(oid)][1] - c) for c in cx]))
        used.setdefault(bi, []).append(oid)
    free = [i + 1 for i in range(len(eb)) if i not in used]
    clash = {i + 1: v for i, v in used.items() if len(v) > 1}
    j = free[0] if len(free) == 1 and not clash else None
    return {"gone": gone, "free": free, "clash": clash, "k": k, "j": j}


def cmd_score(a):
    truth = truth_all()
    rows = []
    for d in sorted(OUT.glob(f"*_{a.model}" + ("" if a.device == "cpu" else f"_{a.device}"))):
        f = d / "track.json"
        if not f.exists():
            continue
        tr = hc.jload(f)
        tid = tr["plan"]["id"]
        u = truth[tid]
        r = judge(tr)
        want = (u["k_id"], u["j_closed"])
        v = "못 정함" if r["k"] is None or r["j"] is None else "맞음" if (r["k"], r["j"]) == want else "조용한 틀림"
        rows.append({"id": tid, "class": TURNS.get(tid), "truth": want, **r, "verdict": v, "sec": tr["sec"], "frames": len(tr["frames"])})
        print(f"{tid:8s} {TURNS.get(tid, ''):3s} 정답 {want[0]}·{want[1]} → k {r['k']} (사라진 물체 {r['gone']}) · j {r['j']} (짝 없는 상자 {r['free']}{' · 겹침 ' + str(r['clash']) if r['clash'] else ''}) → {v} | {len(tr['frames'])}프레임 {tr['sec']:.0f}초")
    hc.jsave(OUT / (f"score_{a.model}" + ("" if a.device == "cpu" else f"_{a.device}") + ".json"), rows)


def cmd_show(a):
    d = run_dir(a.id, a)
    tr = hc.jload(d / "track.json")
    H, W = tr["shape"]
    M = np.load(d / "masks.npz")
    n = tr["plan"]["n"]
    rng = np.random.default_rng(3)
    col = (rng.uniform(60, 255, (n + 1, 3))).astype(np.uint8)
    picks = list(range(0, len(tr["frames"]), a.every))
    if picks[-1] != len(tr["frames"]) - 1:
        picks.append(len(tr["frames"]) - 1)
    tiles = []
    for fi in picks:
        im = np.asarray(Image.open(d / "frames" / f"{fi:05d}.jpg")).astype(np.float32)
        lab = Image.new("RGB", (W, H))
        ov = im.copy()
        cents = []
        for oid in range(1, n + 1):
            key = f"{fi}_{oid}"
            if key not in M:
                continue
            m = np.unpackbits(M[key])[: H * W].reshape(H, W).astype(bool)
            ov[m] = 0.45 * ov[m] + 0.55 * col[oid]
            ys, xs = np.nonzero(m)
            if len(xs):
                cents.append((oid, xs.mean(), ys.mean()))
        img = Image.fromarray(ov.astype(np.uint8))
        dr = ImageDraw.Draw(img)
        for oid, x, y in cents:
            dr.text((x - 4, y - 6), str(oid), fill=(255, 255, 255))
        dr.text((4, 4), f"#{fi} {hc.mss(tr['frames'][fi])}", fill=(255, 255, 0))
        tiles.append(img)
        del lab
    sheet = Image.new("RGB", (W, H * len(tiles)))
    for i, t in enumerate(tiles):
        sheet.paste(t, (0, i * H))
    out = d / f"show_every{a.every}.jpg"
    sheet.save(out, quality=88)
    print(out)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("prep", "run", "score", "show"):
        p = sp.add_parser(name)
        p.add_argument("--model", default="t")
        p.add_argument("--step", type=int, default=2)
        p.add_argument("--device", default="cpu", help="cpu | xpu(Intel 내장 그래픽, venvs/sam2_xpu)")
        if name == "show":
            p.add_argument("id")
            p.add_argument("--every", type=int, default=5)
        else:
            p.add_argument("--ids")
    a = ap.parse_args()
    {"prep": cmd_prep, "run": cmd_run, "score": cmd_score, "show": cmd_show}[a.cmd](a)


if __name__ == "__main__":
    main()
