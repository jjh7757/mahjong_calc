"""SAM 2 프롬프트 v2 — 기준 프레임 여러 장 · 뽑은 패 = 물체 N+1 · 나간 패 빼기(2026-11-18, 계획서 3단계 "추가 23"). API 호출 없음.

v1(sam2track.py)은 시작 프레임 한 장에만 상자를 줘서, 손에 가렸다 다시 보일 때 마스크가 "패" 가 아니라 "시작 프레임의 자리" 로 돌아갔다
(어려운 8차례 전부 못 정함 — 버린 패 마스크가 안 사라짐 · 손 밑에서 줄이 밀리면 이웃 패로 미끄러짐 · 뽑은 패에 떠돌던 마스크가 붙음).
v2 는 손이 줄에서 떨어진 깨끗한 프레임(닻)마다 SAM 2 상태를 새로 시작하고, 닻에서 물체 ↔ 상자 배정을 코드가 다시 한다:
  들린 물체는 마스크 자리로 · 안 들린 물체는 앞 닻의 순서 그대로 · 장수가 맞게 나간 패 하나를 빼고 · 남는 상자를 뽑은 패(물체 N+1)로.

  <venv>/python -X utf8 sam2track2.py prep [--ids a,b]                 # 닻만 찍음(SAM 2 안 돌림)
  <venv>/python -X utf8 sam2track2.py run [--ids a,b] [--device xpu] [--limit 40]
  python -X utf8 sam2track2.py score [--device xpu]
  python -X utf8 sam2track2.py show <id> [--every 6] [--device xpu]    # 마스크 겹친 프레임 띠(닻은 노란 테두리)

프레임 · 띠 · 시작/끝 줄 · 모델 · 초당 5장은 v1 그대로(s1.plan · s1.frame_list). 결과 = _work/sam2v2_1118/<id>_<모델>[_<장치>]/(track.json · masks.npz) · score_*.json
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import sam2track as s1  # noqa: E402
import slotgrid as sg  # noqa: E402

OUT = hc.WORK / "sam2v2_1118"
HARD8 = ["r12_d02", "r13_d02", "r16_d01", "r16_d02", "r16_d13", "r16_d16", "r17_d03", "r17_d08"]
ROW_Y, OCC_PAD, W_LO, W_HI, RUN_MIN = 1.0, 0.5, 0.6, 1.4, 2   # 닻: 줄 근처 상자 · 가림 여유(칸) · 상자 폭(시작 줄 상자 폭의 배) · 이어진 장수
LIFT_A, LIFT_Y = 0.4, 0.45                                    # 들림: 넓이 ≥ 구간 시작의 0.4, y 가 0.45 패 높이 넘게 벗어남
END_A, END_X, END_Y = 0.5, 0.5, 0.5                           # 끝 온전: 넓이 ≥ 0.5, 가장 가까운 상자까지 x 0.5칸 · y 0.5 패 높이
CO_A, CO_X, CO_Y = 0.3, 0.3, 0.3                              # 겹침: 둘 다 넓이 ≥ 0.3, 중심 x 0.3칸 · y 0.3 패 높이 안
PLACE_X = 0.6                                                 # 들린 물체 → 빈 상자: 0.6칸 안
CONF_X, CONF_GAP = 0.4, 0.6                                   # 뽑은 패 확신: 안 들린 물체 모두 0.4칸 안 · 둘째 합과 0.6칸 차


def run_dir(tid: str, a) -> Path:
    return OUT / (f"{tid}_{a.model}" + ("" if a.device == "cpu" else f"_{a.device}") + (f"_lim{a.limit}" if getattr(a, "limit", None) else ""))


def pitch_of(boxes: list) -> float:
    cx = sorted((b[0] + b[2]) / 2 for b in boxes)
    return float(np.median(np.diff(cx)))


# ------------------------------------------------------------------ 닻(깨끗한 프레임)
def anchors(p: dict, fl: list, final: bool = True) -> list:
    """→ [{fi, c, boxes(넓힌 띠 시점 [x0, y0, x1, y1], 왼쪽부터)}]. 첫 닻 = 시작 줄, final 이면 마지막 닻 = v1 끝 줄."""
    det = {int(k): v for k, v in hc.jload(sg.OUT / f"det_{p['gid']}.json").items()}
    n, hh, band, band2, side = p["n"], p["hh"], p["band"], p["band2"], p["side"]
    b0 = det[p["a_ms"]]["b"]
    yc = float(np.median([(b[2] + b[3]) / 2 for b in b0]))
    pw = float(np.median(np.diff(sorted((b[0] + b[1]) / 2 for b in b0))))
    bw = float(np.median([b[1] - b[0] for b in b0]))   # 상자 폭은 칸보다 조금 넓다(이웃과 겹침) → 폭 검사는 시작 줄 상자 폭 기준

    def clean(ms):
        d = det.get(ms)
        if d is None:
            return None
        row = sorted([b for b in d["b"] if abs((b[2] + b[3]) / 2 - yc) <= ROW_Y * hh], key=lambda b: b[0])
        if not (n - 1 <= len(row) <= n + 1) or any(not (W_LO * bw <= b[1] - b[0] <= W_HI * bw) for b in row):
            return None
        x0, x1 = row[0][0] - OCC_PAD * pw, max(b[1] for b in row) + OCC_PAD * pw
        if any(o[0] < x1 and o[1] > x0 for o in d["o"]):
            return None
        return row

    rows = [clean(ms) for ms in fl]
    out = [{"fi": 0, "c": n, "boxes": p["a_boxes"]}]
    i, F = 0, len(fl)
    while i < F:
        if rows[i] is None:
            i += 1
            continue
        j = i
        while j + 1 < F and rows[j + 1] is not None and len(rows[j + 1]) == len(rows[i]):
            j += 1
        if j - i + 1 >= RUN_MIN:
            fi = j if (j - i + 1 == 2 or j == F - 1) else j - 1
            if fi - out[-1]["fi"] >= 3:
                out.append({"fi": fi, "c": len(rows[fi]), "boxes": [s1.remap_box(b, band, band2, side) for b in rows[fi]]})
        i = j + 1
    if final:
        if out[-1]["fi"] > F - 4 and len(out) > 1:
            out.pop()
        out.append({"fi": F - 1, "c": n, "boxes": p["e_boxes"]})
    return out


# ------------------------------------------------------------------ 닻에서의 배정
def decide(order: list, removed, has_new: bool, seg: list, boxes: list, pitch: float, hh: float) -> dict:
    """order = 살아 있는 물체(앞 닻의 왼쪽 → 오른쪽), seg = 구간 시작 ~ 닻의 프레임별 {물체: [넓이, x, y, …]}, boxes = 닻의 줄 상자.
    → {valid, why, g, w, gone, assign{물체: 상자 번호(0부터)}, new_box, conf, cand, lifted, n_fix}"""
    first, last = seg[0], seg[-1]
    bx = [(b[0] + b[2]) / 2 for b in boxes]
    by = [(b[1] + b[3]) / 2 for b in boxes]
    c = len(boxes)
    info = {}
    for o in order:
        a0, _, y0 = first[o][:3]
        lifted = a0 > 0 and any(r[o][0] >= LIFT_A * a0 and r[o][2] is not None and abs(r[o][2] - y0) > LIFT_Y * hh for r in seg)
        a, x, y = last[o][:3]
        ok = False
        if x is not None and a0 > 0 and a >= END_A * a0:
            q = int(np.argmin([abs(x - v) for v in bx]))
            ok = abs(x - bx[q]) <= END_X * pitch and abs(y - by[q]) <= END_Y * hh
        info[o] = {"lifted": bool(lifted), "ok": bool(ok), "x": x, "y": y}

    def co(r, o1, o2):
        A, B = r[o1], r[o2]
        return (A[1] is not None and B[1] is not None and A[0] >= CO_A * first[o1][0] and B[0] >= CO_A * first[o2][0]
                and abs(A[1] - B[1]) <= CO_X * pitch and abs(A[2] - B[2]) <= CO_Y * hh)

    co_end = {o: [q for q in order if q != o and co(last, o, q)] for o in order}
    cand = [o for o in order if not info[o]["ok"] or (info[o]["lifted"] and co_end[o])]
    base = {"cand": cand, "lifted": [o for o in order if info[o]["lifted"]], "c": c, "alive": len(order),
            "co_end": sorted({tuple(sorted((o, q))) for o in order for q in co_end[o]})}

    def bad(why):
        return {"valid": False, "why": why, **base}

    d = c - len(order)
    opts = [(g, w) for g in (0, 1) for w in (0, 1) if w - g == d and (g == 0 or removed is None) and (w == 0 or not has_new)]
    if not opts:
        return bad(f"장수 안 맞음(상자 {c} · 물체 {len(order)})")
    if len(opts) == 2:
        if len(cand) > 1:
            return bad(f"나감 후보 {cand}")
        g, w = (1, 1) if len(cand) == 1 else (0, 0)
    else:
        g, w = opts[0]
    if g == 1 and len(cand) != 1:
        return bad(f"한 장 나갔는데 나감 후보 {cand}")
    if g == 0 and cand:
        return bad(f"장수는 그대로인데 나감 후보 {cand}")
    gone = cand[0] if g else None
    rest = [o for o in order if o != gone]
    free, assign = set(range(c)), {}
    for o in sorted([o for o in rest if info[o]["lifted"]], key=lambda o: min(abs(info[o]["x"] - v) for v in bx)):
        near = sorted(free, key=lambda i: abs(info[o]["x"] - bx[i]))
        if not near or abs(info[o]["x"] - bx[near[0]]) > PLACE_X * pitch:
            return bad(f"들린 물체 {o} 가 앉을 빈 상자 없음")
        assign[o] = near[0]
        free.discard(near[0])
    N = [o for o in rest if not info[o]["lifted"]]
    fb = sorted(free)
    if len(fb) != len(N) + w:
        return bad(f"남은 상자 {len(fb)} ≠ 안 들린 물체 {len(N)} + 새 패 {w}")
    new_box, conf, gap = None, None, None
    if w == 0:
        assign.update(zip(N, fb))
    else:
        costs = [sum(abs(info[o]["x"] - bx[i]) for o, i in zip(N, fb[:s] + fb[s + 1:])) for s in range(len(fb))]
        s = int(np.argmin(costs))
        assign.update(zip(N, fb[:s] + fb[s + 1:]))
        new_box = fb[s]
        gap = (sorted(costs)[1] - costs[s]) / pitch if len(costs) > 1 else 99.0
        within = all(abs(info[o]["x"] - bx[assign[o]]) <= CONF_X * pitch for o in N)
        co_seg = False
        for i1, o1 in enumerate(N):
            for o2 in N[i1 + 1:]:
                run = 0
                for r in seg:
                    run = run + 1 if co(r, o1, o2) else 0
                    if run >= 2:
                        co_seg = True
        conf = bool(within and gap >= CONF_GAP and not co_seg)
        base.update({"gap": round(gap, 2), "within": bool(within), "co_seg": co_seg})
    n_fix = sum(1 for o in rest if abs(info[o]["x"] - bx[assign[o]]) > 0.5 * pitch)
    return {"valid": True, "why": "", "g": g, "w": w, "gone": gone, "assign": assign, "new_box": new_box, "conf": conf, "n_fix": n_fix, **base}


# ------------------------------------------------------------------ 돌리기
def cmd_prep(a):
    for tid in (a.ids.split(",") if a.ids else HARD8):
        p = s1.plan(tid)
        if not p["ok"]:
            print(tid, p["why"])
            continue
        fl = s1.frame_list(p, a.step)
        an = anchors(p, fl)
        print(f"{tid} n={p['n']} 프레임 {len(fl)} · 닻 {len(an)}: " + " ".join(f"#{x['fi']}({x['c']})" for x in an))


def track_one(pred, tid: str, a) -> None:
    import torch
    p = s1.plan(tid)
    if not p["ok"]:
        print(tid, p["why"])
        return
    d = run_dir(tid, a)
    fd = d / "frames"
    fd.mkdir(parents=True, exist_ok=True)
    fl = s1.frame_list(p, a.step)
    if a.limit:
        fl = fl[:a.limit]
    for i, ms in enumerate(fl):
        f = fd / f"{i:05d}.jpg"
        if not f.exists():
            Image.fromarray(hc.band_crop(hc.load(ms), p["band2"], p["side"])).save(f, quality=95)
    an = anchors(p, fl, final=not a.limit)
    n, hh = p["n"], p["hh"]
    NEW = n + 1
    pitch = pitch_of(p["a_boxes"])
    order = list(range(1, n + 1))
    box_of = {o: p["a_boxes"][o - 1] for o in order}
    removed, has_new, new_conf = None, False, None
    rec, keep, log = {}, {}, [{"fi": 0, "valid": True, "why": "시작 줄", "order": list(order)}]
    seg_start, cur, restart = 0, -1, True
    t0 = time.time()
    with torch.inference_mode():
        st = pred.init_state(video_path=str(fd), offload_video_to_cpu=True, offload_state_to_cpu=True)
        for A in an[1:]:
            fb = A["fi"]
            if restart:
                pred.reset_state(st)
                for o in order:
                    pred.add_new_points_or_box(st, frame_idx=seg_start, obj_id=o, box=np.array(box_of[o], np.float32))
                start = seg_start
            else:
                start = cur + 1
            for fi, oids, logits in pred.propagate_in_video(st, start_frame_idx=start, max_frame_num_to_track=fb - start):
                row = {}
                for oid, lg in zip(oids, logits):
                    l = lg[0].float().cpu().numpy()
                    m = l > 0
                    ys, xs = np.nonzero(m)
                    row[int(oid)] = [int(m.sum()), float(xs.mean()) if len(xs) else None, float(ys.mean()) if len(ys) else None,
                                     round(float(l[m].mean()), 2) if len(xs) else None]
                    keep[(int(fi), int(oid))] = np.packbits(m)
                for o in list(k[1] for k in keep if k[0] == fi and k[1] not in row):   # 다시 시작한 닻 프레임: 빠진 물체의 옛 마스크를 지움
                    del keep[(fi, o)]
                rec[int(fi)] = row
                cur = int(fi)
                if fi % 20 == 0:
                    print(f"  {tid} {fi}/{len(fl)} {time.time() - t0:.0f}s", flush=True)
            dec = decide(order, removed, has_new, [rec[f] for f in range(seg_start, fb + 1)], A["boxes"], pitch, hh)
            entry = {"fi": fb, "seg_start": seg_start, **{k: v for k, v in dec.items() if k != "assign"}}
            if dec["valid"]:
                if dec["gone"] is not None:
                    removed = dec["gone"]
                asg = dict(dec["assign"])
                if dec["new_box"] is not None:
                    has_new, new_conf = True, dec["conf"]
                    asg[NEW] = dec["new_box"]
                order = sorted(asg, key=lambda o: asg[o])
                box_of = {o: A["boxes"][asg[o]] for o in order}
                entry["order"] = list(order)
                entry["assign"] = {str(o): asg[o] + 1 for o in order}
                seg_start, restart = fb, True
            else:
                restart = False
            log.append(entry)
            print(f"  {tid} 닻 #{fb}(상자 {A['c']}): " + (f"배정 · 나감 {dec['gone']} · 새 패 상자 {None if dec['new_box'] is None else dec['new_box'] + 1}"
                  f"{'' if dec['conf'] is None else ' 확신' if dec['conf'] else ' 확신 아님'} · 들림 {dec['lifted']} · 고침 {dec['n_fix']}" if dec["valid"] else f"못 정함 — {dec['why']}"), flush=True)
    final_ok = bool(log[-1]["valid"]) and not a.limit
    res = {"removed": removed, "has_new": has_new, "new_conf": new_conf, "final_ok": final_ok,
           "k": removed, "j": (order.index(NEW) + 1) if (has_new and final_ok) else None, "end_order": list(order)}
    shape = list(np.asarray(Image.open(fd / "00000.jpg")).shape[:2])
    np.savez_compressed(d / "masks.npz", **{f"{fi}_{oid}": v for (fi, oid), v in keep.items()})
    hc.jsave(d / "track.json", {"plan": p, "frames": fl, "shape": shape, "model": a.model, "device": a.device, "sec": round(time.time() - t0, 1),
                                "rec": {str(f): {str(o): v for o, v in r.items()} for f, r in rec.items()}, "anchors": log, "result": res}, indent=None)
    print(f"{tid} 끝 {time.time() - t0:.0f}s ({len(fl)}프레임 · 닻 {len(an)}) → k {res['k']} · j {res['j']} · 뽑은 패 확신 {new_conf} · 마지막 닻 {final_ok}", flush=True)


def cmd_run(a):
    import torch
    from sam2.build_sam import build_sam2_video_predictor
    torch.set_num_threads(16)
    if a.device == "xpu":
        assert torch.xpu.is_available(), "XPU 없음 — venvs/sam2_xpu 의 python 으로 돌릴 것"
    cfg, ck = s1.CFG[a.model]
    pred = build_sam2_video_predictor(cfg, str(s1.CKPT / ck), device=a.device)
    for tid in (a.ids.split(",") if a.ids else HARD8):
        if (run_dir(tid, a) / "track.json").exists() and not a.force:
            print(tid, "이미 있음(--force 로 다시)")
            continue
        track_one(pred, tid, a)


def verdict(res: dict, want) -> str:
    if res["removed"] is None or not res["has_new"] or not res["new_conf"] or not res["final_ok"] or res["j"] is None:
        return "못 정함"
    return "맞음" if (res["k"], res["j"]) == tuple(want) else "조용한 틀림"


def cmd_score(a):
    truth = s1.truth_all()
    rows = []
    suffix = f"_{a.model}" + ("" if a.device == "cpu" else f"_{a.device}")
    for d in sorted(OUT.glob(f"*{suffix}")):
        f = d / "track.json"
        if not f.exists():
            continue
        tr = hc.jload(f)
        tid, r = tr["plan"]["id"], tr["result"]
        want = (truth[tid]["k_id"], truth[tid]["j_closed"])
        v = verdict(r, want)
        an = tr["anchors"]
        rows.append({"id": tid, "truth": want, **r, "verdict": v, "sec": tr["sec"], "frames": len(tr["frames"]),
                     "anchors": len(an), "anchors_valid": sum(1 for x in an if x["valid"])})
        why = "" if v != "못 정함" else " ← " + ("나감 못 정함" if r["removed"] is None else "뽑은 패 못 찾음" if not r["has_new"] else "뽑은 패 확신 아님" if not r["new_conf"] else "마지막 닻 못 정함")
        print(f"{tid:8s} 정답 {want[0]}·{want[1]} → k {r['k']} · j {r['j']}(확신 {r['new_conf']}) → {v}{why} | 닻 {rows[-1]['anchors_valid']}/{len(an)} · {len(tr['frames'])}프레임 {tr['sec']:.0f}초")
    c = {k: sum(1 for x in rows if x["verdict"] == k) for k in ("맞음", "못 정함", "조용한 틀림")}
    print(f"합계 {len(rows)}차례: 맞음 {c['맞음']} · 못 정함 {c['못 정함']} · 조용한 틀림 {c['조용한 틀림']}")
    hc.jsave(OUT / f"score{suffix}.json", rows)


def cmd_show(a):
    d = run_dir(a.id, a)
    tr = hc.jload(d / "track.json")
    H, W = tr["shape"]
    M = np.load(d / "masks.npz")
    n = tr["plan"]["n"]
    rng = np.random.default_rng(3)
    col = rng.uniform(60, 255, (n + 2, 3)).astype(np.float32)
    col[n + 1] = (255, 255, 255)
    anc = {x["fi"]: x for x in tr["anchors"]}
    picks = sorted(set(range(0, len(tr["frames"]), a.every)) | set(anc))
    tiles = []
    for fi in picks:
        ov = np.asarray(Image.open(d / "frames" / f"{fi:05d}.jpg")).astype(np.float32)
        cents = []
        for oid in range(1, n + 2):
            key = f"{fi}_{oid}"
            if key not in M:
                continue
            m = np.unpackbits(M[key])[: H * W].reshape(H, W).astype(bool)
            if not m.any():
                continue
            ov[m] = 0.45 * ov[m] + 0.55 * col[oid]
            ys, xs = np.nonzero(m)
            cents.append((oid, xs.mean(), ys.mean()))
        img = Image.fromarray(ov.astype(np.uint8))
        dr = ImageDraw.Draw(img)
        for oid, x, y in cents:
            dr.text((x - 5, y - 6), "N" if oid == n + 1 else str(oid), fill=(255, 255, 255), stroke_width=1, stroke_fill=(0, 0, 0))
        tag = f"#{fi} {hc.mss(tr['frames'][fi])}"
        if fi in anc:
            x = anc[fi]
            tag += " [anchor " + ("ok" if x["valid"] else "skip") + (f" gone {x['gone']}" if x.get("gone") else "") + (f" new {x['new_box'] + 1}" if x.get("new_box") is not None else "") + "]"
            dr.rectangle([0, 0, W - 1, H - 1], outline=(255, 255, 0) if x["valid"] else (255, 80, 80), width=2)
        dr.text((4, 4), tag, fill=(255, 255, 0), stroke_width=1, stroke_fill=(0, 0, 0))
        tiles.append(img)
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
        q = sp.add_parser(name)
        q.add_argument("--model", default="t")
        q.add_argument("--step", type=int, default=2)
        q.add_argument("--device", default="cpu", help="cpu | xpu(Intel 내장 그래픽, venvs/sam2_xpu)")
        q.add_argument("--limit", type=int, default=0, help="앞 프레임만(동작 확인용 — 판정 안 함)")
        if name == "show":
            q.add_argument("id")
            q.add_argument("--every", type=int, default=6)
        else:
            q.add_argument("--ids")
        if name == "run":
            q.add_argument("--force", action="store_true")
    a = ap.parse_args()
    {"prep": cmd_prep, "run": cmd_run, "score": cmd_score, "show": cmd_show}[a.cmd](a)


if __name__ == "__main__":
    main()
