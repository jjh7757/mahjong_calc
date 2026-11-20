"""강에 새로 놓인 패를 SAM 2 로 시간을 거꾸로 따라가 쯔모기리(T) / 손에서 냄(H) 가르기(2026-11-19, 계획서 3단계 "추가 51"). API 호출 없음.

사용자 "sam 2로 기준을 정할수 없을까" → "거꾸로 추적 시험". 앞으로 추적(sam2track — 첫 프레임 줄 n장)은 버린 패의 마스크가 강까지
안 따라가 끝 상태로는 쯔모기리와 끝 붙임이 같아 보인다 → 끝 프레임의 강 패 하나를 찍고 거꾸로 돌려, 차례 첫 프레임에 그 패가
손패 줄 안에 있었나를 본다.

  python -X utf8 sam2back.py prep [--ids a,b]                    # SAM 2 없이: 자름 · 찍을 상자 · 프레임 수, <id>/prompt.jpg
  <venv>/python -X utf8 sam2back.py run [--ids a,b] [--device xpu|cpu] [--force]
  python -X utf8 sam2back.py score [--ids a,b]                   # 판정표(정답은 표시 · 셈에만) → score.json
  python -X utf8 sam2back.py show <id> [--every 5]               # 마스크 겹친 프레임 띠

프레임 = 저장된 앞으로 추적 _work/sam2_1118/<id>_t_xpu/track.json 의 frames · plan 그대로(plan() 을 다시 부르지 않음 — 번호를 맞추려고).
자름 = 원본 좌표에서 설정 river ∪ plan band2 상자, band_crop 으로 대국자 시점.
찍을 상자 = results/h<판>/overlay_dump.json(앱 겹쳐 보기, 약 3초 간격). "뒤" = e_ms 뒤 가장 가까운 프레임.
            "앞" = 버림 시각(차례 cut.discard − BEFORE_MARGIN ms, 없으면 a_ms)보다 앞인 프레임 중 내 강 상자 수가 정확히 (뒤 − 1) 인 가장 늦은 것
            (11-19 고침 — 전에는 a_ms 앞 가장 가까운 프레임이라 검출이 통째로 빠진 프레임 · 기록 시작 전 차례에서 못 찾았음). 없으면 "상자 못 찾음(앞 프레임 없음)".
            뒤의 내 강(설정 river 안 — 상자 가운데로) 상자 중 앞의 강 상자와 IoU < IOU_NEW 인 것. 정확히 하나가 아니면 "상자 못 찾음"(추측으로 고르지 않음).
            b = [왼쪽, 위, 폭, 높이] / 그 프레임 크기(996 또는 2992) — head_rec 1496 원본에 곱해 그대로 맞음(11-19 r12 4순 그림으로 확인).
판정(judge, 정답 안 씀) = 추가 51 의 문턱 그대로(아래 상수, 바꾸지 말 것).
SAM 2 venv = C:\\Users\\jjh7757\\dev\\venvs\\sam2_xpu. 결과 = results/handtrack/_work/sam2back_1119/<id>/(frames · prompt.jpg · track.json · masks.npz) · score.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import sam2track as s1  # noqa: E402
import turncut as tc  # noqa: E402

OUT = hc.WORK / "sam2back_1119"
FWD = hc.WORK / "sam2_1118"          # 앞으로 추적(읽기만)
IDS = "r16_d03,r16_d04,r16_d06,r16_d12,r16_d05,r16_d07,r16_d09,r16_d10,r17_d02,r17_d07,r12_d04,r17_d04"
DEV = ("r12", "r16", "r17")           # 개발 판만 — r19 · r13 은 다루지 않음
IOU_NEW = 0.3                         # 차례 앞 강 상자와 이보다 덜 겹치면 "새 상자"
BEFORE_MARGIN = 500                   # "앞" 프레임은 버림 시각 − 500ms 보다 앞(패가 강에 놓이기 전)

# ---- 판정 문턱(추가 51 에 추적 전에 적은 값 — 바꾸지 말 것)
JUDGE_FRAMES = 3                      # 프레임 0 ~ 2
ROW_Y = 0.6                           # 가운데 y 가 시작 줄 높이 ± 0.6 × 패 높이
ROW_X_PAD = 1.0                       # x 가 줄 범위 ± 패 한 칸
AREA_LO, AREA_HI = 0.3, 3.0           # 면적이 시작 줄 상자 면적 중앙값의 0.3 ~ 3배
IN_ROW_MIN = 2                        # "줄 안" 프레임이 둘 이상이면 H


# ------------------------------------------------------------------ 입력
def fwd_track(tid: str) -> dict:
    return hc.jload(FWD / f"{tid}_t_xpu" / "track.json")


def ids_of(a) -> list:
    ids = (a.ids or IDS).split(",")
    bad = [t for t in ids if t[:3] not in DEV]
    if bad:
        raise SystemExit(f"개발 판(r12 · r16 · r17) 차례만: {bad}")
    return ids


def crop_of(gid: str, p: dict) -> list:
    r, b = hc.config(gid)["river"], p["band2"]
    return [max(0, min(r[0], b[0])), max(0, min(r[1], b[1])), min(1496, max(r[2], b[2])), min(1496, max(r[3], b[3]))]


def box_to_view(box: list, crop: list, side: str) -> list:
    """원본 [x0, y0, x1, y1] → 자름 시점 [x0, y0, x1, y1]."""
    ps = [hc.to_view_xy(p, crop, side) for p in ((box[0], box[1]), (box[2], box[3]))]
    xs, ys = [q[0] for q in ps], [q[1] for q in ps]
    return [min(xs), min(ys), max(xs), max(ys)]


def band2_to_view(box: list, band2: list, crop: list, side: str) -> list:
    """plan a_boxes(band2 시점 [x0, y0, x1, y1]) → 원본 → 자름 시점 [x0, y0, x1, y1]."""
    ps = [s1.from_view_xy(p, band2, side) for p in ((box[0], box[1]), (box[2], box[3]))]
    xs, ys = [q[0] for q in ps], [q[1] for q in ps]
    return box_to_view([min(xs), min(ys), max(xs), max(ys)], crop, side)


_OD: dict = {}


def overlay(gid: str):
    """overlay_dump 프레임과 epoch ms(turncut.build_game 과 같은 셈 — 'at' 은 현지 시각, 시간대 없음)."""
    if gid not in _OD:
        fr = json.load(open(tc.rec_dir(gid) / "overlay_dump.json", encoding="utf-8"))["frames"]
        _OD[gid] = (fr, [int(dt.datetime.fromisoformat(f["at"]).timestamp() * 1000) for f in fr])
    return _OD[gid]


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - ix * iy
    return ix * iy / u if u > 0 else 0.0


def river_boxes(f: dict, river: list) -> list:
    """겹쳐 보기 한 프레임의 상자 중 가운데가 설정 river 안인 것 → [(원본 [x0, y0, x1, y1], 검출)]."""
    out = []
    for t in f["tiles"]:
        x, y, w, h = t["b"]
        b = [x * 1496, y * 1496, (x + w) * 1496, (y + h) * 1496]
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        if river[0] <= cx <= river[2] and river[1] <= cy <= river[3]:
            out.append((b, t))
    return out


def same_tile(a: str, b: str) -> bool:
    n = lambda s: (s or "").replace("0", "5")[:2]  # noqa: E731  (붉은 5 표기 0 → 5)
    return n(a) == n(b)


def find_prompt(tid: str) -> dict:
    """찍을 상자 — 정답 안 씀. ok False 면 why."""
    gid, t = s1.turn_of(tid)
    tr = fwd_track(tid)
    p = tr["plan"]
    river = hc.config(gid)["river"]
    fr, ft = overlay(gid)
    a_ms, e_ms = p["a_ms"], p["e_ms"]
    out = {"id": tid, "gid": gid, "tile": t["tile"], "ok": False}
    ia = min((k for k in range(len(ft)) if ft[k] >= e_ms), default=None)
    if ia is None:
        out["why"] = "뒤 프레임 없음"
        return out
    after = river_boxes(fr[ia], river)
    disc = (t.get("cut") or {}).get("discard")
    if disc:
        d_ms = s1.ms_of(disc, a_ms)
        limit, rule = d_ms - BEFORE_MARGIN, f"버림 {hc.mss(d_ms)} − {BEFORE_MARGIN}ms 앞"
    else:
        d_ms, limit, rule = None, a_ms, "버림 시각 없음 → a_ms 이전"
    want = len(after) - 1
    ib = max((k for k in range(len(ft)) if ft[k] < limit and len(river_boxes(fr[k], river)) == want), default=None)
    out.update(before_rule=rule, discard_ms=d_ms, before_limit_ms=limit, n_after=len(after), after_file=fr[ia]["file"], after_ms=ft[ia])
    if ib is None:
        out["why"] = f"앞 프레임 없음(강 상자 {want}장인 프레임이 그 앞에 없음)"
        return out
    out["before_vs_a"] = "a_ms 앞" if ft[ib] <= a_ms else "a_ms ~ 버림 사이"
    before = river_boxes(fr[ib], river)
    new = [(b, d, max((iou(b, q) for q, _ in before), default=0.0)) for b, d in after]
    new = [x for x in new if x[2] < IOU_NEW]
    out.update(before_file=fr[ib]["file"], before_ms=ft[ib], after_file=fr[ia]["file"], after_ms=ft[ia],
               n_before=len(before), n_after=len(after), n_new=len(new),
               new=[{"box": [round(v, 1) for v in b], "t": d["t"], "t2": d.get("t2"), "r": d["r"], "iou": round(m, 3)} for b, d, m in new])
    if len(new) != 1:
        out["why"] = f"새 상자 {len(new)}개"
        return out
    b, d, _ = new[0]
    crop = crop_of(gid, p)
    out.update(ok=True, box=[round(v, 1) for v in b], crop=crop, side=p["side"], box_view=[round(v, 1) for v in box_to_view(b, crop, p["side"])],
               t=d["t"], t2=d.get("t2"), name_ok=same_tile(d["t"], t["tile"]) or same_tile(d.get("t2"), t["tile"]))
    return out


# ------------------------------------------------------------------ prep
def draw_boxes(dr, boxes, col, w=1):
    for b in boxes:
        dr.rectangle([b[0], b[1], b[2], b[3]], outline=col, width=w)


def cmd_prep(a):
    print("차례 | 프레임 | 자름(원본) → 크기 | 차례 앞/뒤 겹쳐 보기(강 상자 수) | 새 상자 | 패(차례 / t / t2) | 이름")
    for tid in ids_of(a):
        tr = fwd_track(tid)
        p, F = tr["plan"], len(tr["frames"])
        q = find_prompt(tid)
        crop = crop_of(q["gid"], p)
        sz = f"{crop[2] - crop[0]}×{crop[3] - crop[1]}"
        head = f"{tid} | {F} | {crop} → {sz} | {hc.mss(q.get('before_ms', 0)) if 'before_ms' in q else '-'}({q.get('n_before', '-')}, {q.get('before_vs_a', '-')}) / {hc.mss(q['after_ms']) if 'after_ms' in q else '-'}({q.get('n_after', '-')})"
        d = OUT / tid
        d.mkdir(parents=True, exist_ok=True)
        hc.jsave(d / "prompt.json", q)
        # 확인 그림: 위 = 끝 프레임(e_ms) 자름에 찍을 상자(빨강) · 옮긴 시작 줄 상자(노랑), 아래 = 차례 뒤 겹쳐 보기 시각의 원본 프레임 자름에 새 상자 후보(빨강) · 차례 앞 강 상자(파랑)
        side = p["side"]
        top = Image.fromarray(hc.band_crop(hc.load(p["e_ms"]), crop, side))
        dr = ImageDraw.Draw(top)
        draw_boxes(dr, [band2_to_view(b, p["band2"], crop, side) for b in p["a_boxes"]], (255, 255, 0))
        if q["ok"]:
            draw_boxes(dr, [q["box_view"]], (255, 0, 0), 2)
        dr.text((4, 4), f"e #{F - 1} {hc.mss(p['e_ms'])}", fill=(255, 255, 0))
        tiles = [top]
        if "after_ms" in q:
            bot = Image.fromarray(hc.band_crop(hc.load(hc.nearest(q["after_ms"])), crop, side))
            dr = ImageDraw.Draw(bot)
            fr, ft = overlay(q["gid"])
            ib = ft.index(q["before_ms"])
            draw_boxes(dr, [box_to_view(b, crop, side) for b, _ in river_boxes(fr[ib], hc.config(q["gid"])["river"])], (0, 128, 255))
            draw_boxes(dr, [box_to_view(x["box"], crop, side) for x in q["new"]], (255, 0, 0), 2)
            dr.text((4, 4), f"after {hc.mss(q['after_ms'])} (blue = before {hc.mss(q['before_ms'])})", fill=(255, 255, 0))
            tiles.append(bot)
        W, H = top.size
        sheet = Image.new("RGB", (W, H * len(tiles)))
        for i, im in enumerate(tiles):
            sheet.paste(im, (0, i * H))
        sheet.save(d / "prompt.jpg", quality=90)
        if q["ok"]:
            print(f"{head} | 1 {q['box']} | {q['tile']} / {q['t']} / {q['t2']} | {'맞음' if q['name_ok'] else '**다름**'}")
        else:
            print(f"{head} | 상자 못 찾음({q['why']}) {[(x['t2'], x['iou']) for x in q.get('new', [])]} | {q['tile']} | -")


# ------------------------------------------------------------------ run
def cmd_run(a):
    import torch
    from sam2.build_sam import build_sam2_video_predictor
    torch.set_num_threads(16)
    if a.device == "xpu":
        assert torch.xpu.is_available(), "XPU 없음 — venvs/sam2_xpu 의 python 으로 돌릴 것"
    cfg, ck = s1.CFG["t"]
    pred = None
    for tid in ids_of(a):
        d = OUT / tid
        if (d / "track.json").exists() and not a.force:
            print(tid, "이미 있음 — 건너뜀(--force 로 다시)")
            continue
        q = find_prompt(tid)
        if not q["ok"]:
            print(tid, "상자 못 찾음 —", q["why"])
            continue
        tr = fwd_track(tid)
        p, fl = tr["plan"], tr["frames"]
        fd = d / "frames"
        fd.mkdir(parents=True, exist_ok=True)
        for i, ms in enumerate(fl):
            f = fd / f"{i:05d}.jpg"
            if not f.exists():
                Image.fromarray(hc.band_crop(hc.load(ms), q["crop"], p["side"])).save(f, quality=95)
        if pred is None:
            pred = build_sam2_video_predictor(cfg, str(s1.CKPT / ck), device=a.device)
        F = len(fl)
        t0 = time.time()
        rec, keep = {}, {}
        with torch.inference_mode():
            st = pred.init_state(video_path=str(fd), offload_video_to_cpu=True, offload_state_to_cpu=True)
            pred.add_new_points_or_box(st, frame_idx=F - 1, obj_id=1, box=np.array(q["box_view"], np.float32))
            for fi, oids, logits in pred.propagate_in_video(st, start_frame_idx=F - 1, reverse=True):
                row = {}
                for oid, lg in zip(oids, logits):
                    m = (lg[0] > 0).cpu().numpy()
                    ys, xs = np.nonzero(m)
                    row[int(oid)] = [int(m.sum()), float(xs.mean()) if len(xs) else None, float(ys.mean()) if len(ys) else None]
                    keep[f"{int(fi)}_{int(oid)}"] = np.packbits(m)
                rec[int(fi)] = row
                if fi % 20 == 0:
                    print(f"  {tid} {fi}/{F} {time.time() - t0:.0f}s", flush=True)
        sec = round(time.time() - t0, 1)
        shape = list(np.asarray(Image.open(fd / "00000.jpg")).shape[:2])
        np.savez_compressed(d / "masks.npz", **keep)
        hc.jsave(d / "track.json", {"id": tid, "plan": p, "crop": q["crop"], "side": p["side"], "prompt": q, "box_view": q["box_view"],
                                    "frames": fl, "shape": shape, "model": "t", "device": a.device, "sec": sec, "rec": rec}, indent=None)
        print(f"{tid} 끝 {sec:.0f}s ({F}프레임 · {sec / F:.2f}초/프레임)", flush=True)


# ------------------------------------------------------------------ judge(정답 안 씀)
def row_ref(tr: dict) -> dict:
    p = tr["plan"]
    av = [band2_to_view(b, p["band2"], tr["crop"], tr["side"]) for b in p["a_boxes"]]
    return {"a_view": av,
            "yc": float(np.median([(b[1] + b[3]) / 2 for b in av])),
            "hh": float(p["hh"]),
            "w": float(np.median([b[2] - b[0] for b in av])),
            "area": float(np.median([(b[2] - b[0]) * (b[3] - b[1]) for b in av])),
            "x_lo": float(min(b[0] for b in av)), "x_hi": float(max(b[2] for b in av))}


def judge(tr: dict) -> dict:
    R = row_ref(tr)
    rec = tr["rec"]
    per = []
    for fi in range(JUDGE_FRAMES):
        a, x, y = (rec.get(str(fi)) or {}).get("1", [0, None, None])
        ratio = a / R["area"]
        dy = None if y is None else y - R["yc"]
        inrow = (y is not None and x is not None and abs(dy) <= ROW_Y * R["hh"]
                 and R["x_lo"] - ROW_X_PAD * R["w"] <= x <= R["x_hi"] + ROW_X_PAD * R["w"]
                 and AREA_LO <= ratio <= AREA_HI)
        per.append({"fi": fi, "area": a, "ratio": round(ratio, 3), "x": None if x is None else round(x, 1),
                    "dy": None if dy is None else round(dy, 1), "dy_hh": None if dy is None else round(dy / R["hh"], 2), "in_row": bool(inrow)})
    n_in = sum(r["in_row"] for r in per)
    k = None
    if n_in >= IN_ROW_MIN:
        verdict = "H"
        x0 = per[0]["x"]
        if x0 is not None:
            k = int(np.argmin([abs((b[0] + b[2]) / 2 - x0) for b in R["a_view"]])) + 1
    elif all(r["ratio"] > AREA_HI for r in per):
        verdict = "모름"
    else:
        verdict = "T"
    return {"verdict": verdict, "k": k, "n_in_row": n_in, "frames": per,
            "ref": {kk: round(v, 1) for kk, v in R.items() if kk != "a_view"}}


def route(v: str) -> str:
    return "쉬움" if v == "T" else "어려움"


# ------------------------------------------------------------------ score
def dev_truth() -> dict:
    """정답 — 표시 · 셈에만. 개발 판 차례만 남김(확인 판 r19 · r13 은 버림)."""
    t = hc.jload(tc.BASE / "truth_final.json")
    return {k: v for k, v in t.items() if k[:3] in DEV}


def cmd_score(a):
    import routesig as rs
    truth = dev_truth()
    rows = []
    print("차례 | 정답(까닭 · k) | 판정 | 보냄 | 줄 안 프레임 · 면적 비 / y 차(×패 높이) / x (프레임 0 · 1 · 2) | 추적")
    for tid in ids_of(a):
        u = truth.get(tid, {})
        lab, why = rs.difficulty(u) if u else ("-", "정답 없음")
        tk = u.get("k_id") if u.get("kind") != "tsumogiri" else None
        f = OUT / tid / "track.json"
        if not f.exists():
            q = hc.jload(OUT / tid / "prompt.json") if (OUT / tid / "prompt.json").exists() else find_prompt(tid)
            st = "상자 못 찾음(" + q.get("why", "") + ")" if not q.get("ok") else "추적 안 함"
            rows.append({"id": tid, "truth_kind": u.get("kind"), "why": why, "truth_k": tk, "verdict": None, "status": st})
            print(f"{tid:8s} | {why}{' · k ' + str(tk) if tk else ''} | {st}")
            continue
        tr = hc.jload(f)
        j = judge(tr)
        F = len(tr["frames"])
        vals = " · ".join(f"{'○' if r['in_row'] else '×'} {r['ratio']}/{r['dy_hh']}/{r['x']}" for r in j["frames"])
        kk = f"H({j['k']})" if j["verdict"] == "H" else j["verdict"]
        rows.append({"id": tid, "truth_kind": u.get("kind"), "why": why, "truth_k": tk, **j, "route": route(j["verdict"]),
                     "sec": tr["sec"], "n_frames": F, "sec_per_frame": round(tr["sec"] / F, 2), "device": tr.get("device")})
        print(f"{tid:8s} | {why}{' · k ' + str(tk) if tk else ''} | {kk} | {route(j['verdict'])} | {j['n_in_row']} · {vals} | {F}프레임 {tr['sec']:.0f}초({tr['sec'] / F:.2f}초/프레임)")
    done = [r for r in rows if r.get("verdict")]
    tsu = [r for r in done if r["truth_kind"] == "tsumogiri"]
    hand = [r for r in done if r["truth_kind"] not in (None, "tsumogiri")]
    tail = [r for r in hand if r["why"] == "끝 붙임"]
    hk = [r for r in hand if r["verdict"] == "H"]
    cnt = {"done": len(done), "all": len(rows),
           "tail_T": sum(r["verdict"] == "T" for r in tail), "tail_n": len(tail),
           "hand_T": sum(r["verdict"] == "T" for r in hand), "hand_n": len(hand),
           "tsumo_T": sum(r["verdict"] == "T" for r in tsu), "tsumo_n": len(tsu),
           "H_k_ok": sum(r["k"] == r["truth_k"] for r in hk), "H_n": len(hk),
           "unknown": sum(r["verdict"] == "모름" for r in done)}
    print(f"\n추적한 차례 {cnt['done']}/{cnt['all']} · 끝 붙임 중 T {cnt['tail_T']}/{cnt['tail_n']} (손에서 낸 전체 중 T {cnt['hand_T']}/{cnt['hand_n']}) · "
          f"쯔모기리 중 T {cnt['tsumo_T']}/{cnt['tsumo_n']} · H 의 k 맞음 {cnt['H_k_ok']}/{cnt['H_n']} · 모름 {cnt['unknown']}")
    if cnt["done"] == len(IDS.split(",")) and not a.ids:
        v = "❌ 기준 못 됨(끝 붙임이 T 로 샘)" if cnt["tail_T"] >= 1 else ("✅ 갈린다" if cnt["tsumo_T"] >= 6 else "△ 안전하지만 적게 보냄")
        print("추가 51 기준:", v)
        cnt["criterion"] = v
    else:
        print("추가 51 기준: 12차례가 다 추적되지 않아(또는 --ids 로 골라서) 판정 안 함")
    hc.jsave(OUT / "score.json", {"thresholds": {"JUDGE_FRAMES": JUDGE_FRAMES, "ROW_Y": ROW_Y, "ROW_X_PAD": ROW_X_PAD, "AREA": [AREA_LO, AREA_HI], "IN_ROW_MIN": IN_ROW_MIN},
                                  "counts": cnt, "rows": rows})


# ------------------------------------------------------------------ show
def cmd_show(a):
    d = OUT / a.id
    tr = hc.jload(d / "track.json")
    H, W = tr["shape"]
    M = np.load(d / "masks.npz")
    av = row_ref(tr)["a_view"]
    F = len(tr["frames"])
    picks = sorted(set(list(range(0, F, a.every)) + [1, 2, F - 1]))
    col = np.array([255, 60, 200], np.float32)
    tiles = []
    for fi in picks:
        im = np.asarray(Image.open(d / "frames" / f"{fi:05d}.jpg").convert("RGB")).astype(np.float32)
        key = f"{fi}_1"
        cent = None
        if key in M:
            m = np.unpackbits(M[key])[: H * W].reshape(H, W).astype(bool)
            im[m] = 0.45 * im[m] + 0.55 * col
            ys, xs = np.nonzero(m)
            if len(xs):
                cent = (xs.mean(), ys.mean(), int(m.sum()))
        img = Image.fromarray(im.astype(np.uint8))
        dr = ImageDraw.Draw(img)
        draw_boxes(dr, av, (255, 255, 0))
        if fi == F - 1:
            draw_boxes(dr, [tr["box_view"]], (255, 0, 0), 2)
        if cent:
            dr.ellipse([cent[0] - 3, cent[1] - 3, cent[0] + 3, cent[1] + 3], outline=(255, 255, 255), width=2)
        dr.text((4, 4), f"#{fi} {hc.mss(tr['frames'][fi])}" + (f" area {cent[2]}" if cent else " (no mask)"), fill=(255, 255, 0))
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
        p = sp.add_parser(name)
        if name == "show":
            p.add_argument("id")
            p.add_argument("--every", type=int, default=5)
        else:
            p.add_argument("--ids")
        if name == "run":
            p.add_argument("--device", default="xpu", help="xpu(Intel 내장 그래픽, venvs/sam2_xpu) | cpu")
            p.add_argument("--force", action="store_true")
    a = ap.parse_args()
    {"prep": cmd_prep, "run": cmd_run, "score": cmd_score, "show": cmd_show}[a.cmd](a)


if __name__ == "__main__":
    main()
