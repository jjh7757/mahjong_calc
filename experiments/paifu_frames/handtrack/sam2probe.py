"""가림 구간 탐침 — 모델 크기 · 입력 해상도가 손 밑 미끄러짐에 듣는가(2026-11-18, 계획서 3단계 "추가 24"). API 호출 없음.

차례 전체가 아니라 v2(sam2track2.py)가 닻으로 잡은 구간 하나만 v1 방식(시작 닻 한 장에 상자, 앞으로만)으로 다시 돌린다.
팔 = 모델(t|s) × 띠(full | half = 가로 410px 창) (+ 입력 크기 1536 참고).

  <venv>/python -X utf8 sam2probe.py run [--arms t-full,s-full,t-half,s-half,t-full-1536] [--device xpu]
  python -X utf8 sam2probe.py read [--device xpu]          # 구간 끝 닻에서 빈 상자 · 겹침 읽기
  python -X utf8 sam2probe.py show <구간> <팔> [--device xpu]

결과 = _work/sam2probe_1118/<구간>_<팔>[_<장치>]/(frames · masks.npz · track.json) · read_*.json
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
import sam2track2 as s2  # noqa: E402

OUT = hc.WORK / "sam2probe_1118"
# 구간: 차례, 시작 닻 · 끝 닻(프레임 번호, v2 anchors 와 같음), 반쪽 띠 창(넓힌 띠 시점 x), 읽을 물체 · 상자, 기대(빈 상자 후보)
SEGS = {
    "r13_d02": {"f0": 15, "f1": 43, "win": (60, 470), "objs": 8, "boxes": 9, "look": 4, "want": {3}},
    "r16_d16": {"f0": 52, "f1": 88, "win": (20, 430), "objs": 8, "boxes": 9, "look": 9, "want": {7, 8}},
}
ARMS = ["t-full", "s-full", "t-half", "s-half", "t-full-1536"]


def arm_of(name: str):
    q = name.split("-")
    return q[0], q[1], int(q[2]) if len(q) > 2 else 1024


def run_dir(seg: str, arm: str, device: str) -> Path:
    return OUT / (f"{seg}_{arm}" + ("" if device == "cpu" else f"_{device}"))


def cmd_run(a):
    import torch
    from sam2.build_sam import build_sam2_video_predictor
    torch.set_num_threads(16)
    if a.device == "xpu":
        assert torch.xpu.is_available(), "XPU 없음 — venvs/sam2_xpu 의 python 으로 돌릴 것"
    arms = a.arms.split(",") if a.arms else ARMS
    preds = {}
    for arm in arms:
        model, crop, size = arm_of(arm)
        for seg, S in SEGS.items():
            if a.segs and seg not in a.segs.split(","):
                continue
            d = run_dir(seg, arm, a.device)
            if (d / "track.json").exists() and not a.force:
                print(seg, arm, "이미 있음")
                continue
            if (model, size) not in preds:
                preds.clear()                       # 한 번에 모델 하나만 올려 둔다
                cfg, ck = s1.CFG[model]
                extra = [f"++model.image_size={size}"] if size != 1024 else []
                preds[(model, size)] = build_sam2_video_predictor(cfg, str(s1.CKPT / ck), device=a.device, hydra_overrides_extra=extra)
            pred = preds[(model, size)]
            p = s1.plan(seg)
            fl = s1.frame_list(p, 2)
            an = {x["fi"]: x for x in s2.anchors(p, fl)}
            f0, f1 = S["f0"], S["f1"]
            x0, x1 = S["win"] if crop == "half" else (0, None)
            fd = d / "frames"
            fd.mkdir(parents=True, exist_ok=True)
            for i, fi in enumerate(range(f0, f1 + 1)):
                im = hc.band_crop(hc.load(fl[fi]), p["band2"], p["side"])
                Image.fromarray(im[:, x0:x1]).save(fd / f"{i:05d}.jpg", quality=95)
            H, W = np.asarray(Image.open(fd / "00000.jpg")).shape[:2]
            boxes = an[f0]["boxes"]
            objs = [o for o in range(1, len(boxes) + 1) if boxes[o - 1][0] >= x0 and boxes[o - 1][2] <= x0 + W] if crop == "half" else list(range(1, len(boxes) + 1))
            t0 = time.time()
            rec, keep = {}, {}
            with torch.inference_mode():
                st = pred.init_state(video_path=str(fd), offload_video_to_cpu=True, offload_state_to_cpu=True)
                for o in objs:
                    b = boxes[o - 1]
                    pred.add_new_points_or_box(st, frame_idx=0, obj_id=o, box=np.array([b[0] - x0, b[1], b[2] - x0, b[3]], np.float32))
                for fi, oids, logits in pred.propagate_in_video(st):
                    row = {}
                    for oid, lg in zip(oids, logits):
                        m = (lg[0] > 0).cpu().numpy()
                        ys, xs = np.nonzero(m)
                        row[str(int(oid))] = [int(m.sum()), float(xs.mean()) + x0 if len(xs) else None, float(ys.mean()) if len(ys) else None]
                        keep[f"{int(fi)}_{int(oid)}"] = np.packbits(m)
                    rec[str(int(fi))] = row
            sec = round(time.time() - t0, 1)
            np.savez_compressed(d / "masks.npz", **keep)
            hc.jsave(d / "track.json", {"seg": seg, "arm": arm, "f0": f0, "f1": f1, "x0": x0, "shape": [H, W], "objs": objs, "frames": fl[f0:f1 + 1],
                                        "boxes0": boxes, "boxes1": an[f1]["boxes"], "pitch": s2.pitch_of(boxes), "hh": p["hh"], "sec": sec, "rec": rec}, indent=None)
            print(f"{seg} {arm} 끝 {sec:.0f}s ({f1 - f0 + 1}프레임 · 물체 {len(objs)} · 입력 {W}x{H} → {size})", flush=True)


def read_one(tr: dict, S: dict) -> dict:
    rec, pitch = tr["rec"], tr["pitch"]
    first, last = rec["0"], rec[str(tr["f1"] - tr["f0"])]
    bx = [(b[0] + b[2]) / 2 for b in tr["boxes1"]][: S["boxes"]]
    seat, lost = {}, []
    for o in range(1, S["objs"] + 1):
        a0 = first[str(o)][0]
        a, x, _ = last[str(o)]
        if x is None or a < 0.5 * a0:
            lost.append(o)
            continue
        q = int(np.argmin([abs(x - v) for v in bx]))
        if abs(x - bx[q]) <= 0.5 * pitch:
            seat.setdefault(q + 1, []).append(o)
        else:
            lost.append(o)
    empty = [i for i in range(1, S["look"] + 1) if i not in seat]
    clash = {i: v for i, v in seat.items() if len(v) > 1 and i <= S["look"]}
    ok = len(empty) == 1 and empty[0] in S["want"] and (not clash or S["look"] == 4)
    return {"seat": {str(k): v for k, v in sorted(seat.items())}, "empty": empty, "clash": {str(k): v for k, v in clash.items()}, "lost": lost, "ok": bool(ok)}


def cmd_read(a):
    rows = []
    for seg, S in SEGS.items():
        for arm in ARMS:
            f = run_dir(seg, arm, a.device) / "track.json"
            if not f.exists():
                continue
            tr = hc.jload(f)
            r = read_one(tr, S)
            rows.append({"seg": seg, "arm": arm, **r, "sec": tr["sec"], "frames": tr["f1"] - tr["f0"] + 1, "objs": len(tr["objs"])})
            print(f"{seg} {arm:12s} 빈 상자(1~{S['look']}) {r['empty']} · 겹침 {r['clash']} · 못 앉은 물체 {r['lost']} → {'맞음/안 어긋남' if r['ok'] else '틀림'}"
                  f" | 앉은 자리 {r['seat']} | {tr['sec']:.0f}초")
    hc.jsave(OUT / ("read" + ("" if a.device == "cpu" else f"_{a.device}") + ".json"), rows)


def cmd_show(a):
    d = run_dir(a.seg, a.arm, a.device)
    tr = hc.jload(d / "track.json")
    H, W = tr["shape"]
    M = np.load(d / "masks.npz")
    rng = np.random.default_rng(3)
    col = rng.uniform(60, 255, (16, 3)).astype(np.float32)
    n = tr["f1"] - tr["f0"] + 1
    tiles = []
    for fi in sorted(set(range(0, n, a.every)) | {n - 1}):
        ov = np.asarray(Image.open(d / "frames" / f"{fi:05d}.jpg")).astype(np.float32)
        cents = []
        for o in tr["objs"]:
            key = f"{fi}_{o}"
            if key not in M:
                continue
            m = np.unpackbits(M[key])[: H * W].reshape(H, W).astype(bool)
            if not m.any():
                continue
            ov[m] = 0.45 * ov[m] + 0.55 * col[o]
            ys, xs = np.nonzero(m)
            cents.append((o, xs.mean(), ys.mean()))
        img = Image.fromarray(ov.astype(np.uint8))
        dr = ImageDraw.Draw(img)
        for o, x, y in cents:
            dr.text((x - 4, y - 6), str(o), fill=(255, 255, 255), stroke_width=1, stroke_fill=(0, 0, 0))
        dr.text((4, 4), f"#{tr['f0'] + fi} {hc.mss(tr['frames'][fi])}", fill=(255, 255, 0), stroke_width=1, stroke_fill=(0, 0, 0))
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
    for name in ("run", "read", "show"):
        q = sp.add_parser(name)
        q.add_argument("--device", default="cpu")
        if name == "run":
            q.add_argument("--arms")
            q.add_argument("--segs")
            q.add_argument("--force", action="store_true")
        if name == "show":
            q.add_argument("seg")
            q.add_argument("arm")
            q.add_argument("--every", type=int, default=3)
    a = ap.parse_args()
    {"run": cmd_run, "read": cmd_read, "show": cmd_show}[a.cmd](a)


if __name__ == "__main__":
    main()
