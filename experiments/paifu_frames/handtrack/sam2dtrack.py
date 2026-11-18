"""뽑은 패 D 도 SAM 2 로 따라가기(2026-11-18 저녁, 계획서 3단계 "추가 31").

r13 2순에서 Gemini 가 틀린 까닭: v1 추적(sam2track.py)은 시작 줄 13장에만 번호를 붙여 D 는 "색 없는 패" 로만 남는다.
손 밑에서 번호가 한 칸 밀리면 원래 패가 색을 잃고 D 가 번호를 얻어, "색 없음 = D" 로 읽으면 한 칸 틀린다(사용자 확인).
→ D 가 줄 끝에 처음 붙은 프레임(줄 높이 상자가 n+1 개인 첫 프레임의 끝 상자)에서 D 를 따로 찍어 그 뒤로 따라간다.
v1 의 13개 마스크는 그대로 두고 D 만 따로 돌린다(물체끼리 독립이라 함께 돌린 것과 같은 마스크 — v1 을 다시 안 돌려도 됨).

  <venv>/python -X utf8 sam2dtrack.py find [--ids a,b|new17|hard8]          # D 프롬프트 프레임 · 상자만(빠름)
  <venv>/python -X utf8 sam2dtrack.py run  [--ids …] [--device cpu|xpu]     # → <v1 실행 폴더>/dtrack.json · dmasks.npz
v1 실행 폴더 = sam2track.run_dir(<id>, model t · device xpu) — 그 폴더의 frames/ 를 그대로 쓴다(같은 프레임).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import sam2track as s1  # noqa: E402
import slotgrid as sg  # noqa: E402

V1 = argparse.Namespace(model="t", device="xpu")
HARD8 = ["r12_d02", "r13_d02", "r16_d01", "r16_d02", "r16_d13", "r16_d16", "r17_d03", "r17_d08"]
NEW17 = ["r12_d03b", "r12_d06", "r16_d03", "r16_d04", "r16_d06", "r16_d08", "r16_d12", "r17_d10", "r17_d11",
         "r19_d03", "r19_d03b", "r19_d07", "r13_d03", "r13_d04", "r13_d05", "r13_d08", "r13_d09"]


def ids_of(s: str | None) -> list:
    return {"new17": NEW17, "hard8": HARD8, None: HARD8 + NEW17}.get(s) or s.split(",")


def d_prompt(tid: str) -> dict:
    """줄 높이 상자가 n+1 개인 첫 프레임 — 시작 줄 오른쪽 끝보다 오른쪽으로 삐져나온 끝 상자, 아니면 왼쪽으로 삐져나온 끝 상자가 D."""
    d = s1.run_dir(tid, V1)
    tr = hc.jload(d / "track.json")
    p, fl = tr["plan"], tr["frames"]
    det = {int(k): v for k, v in hc.jload(sg.OUT / f"det_{p['gid']}.json").items()}
    a = p["a_boxes"]
    yc = float(np.median([(b[1] + b[3]) / 2 for b in a]))
    hh = float(np.median([b[3] - b[1] for b in a]))
    lo, hi = min(b[0] for b in a), max(b[2] for b in a)
    for fi, ms in enumerate(fl):
        if ms not in det:
            continue
        bs = [s1.remap_box(b, p["band"], p["band2"], p["side"]) for b in det[ms]["b"]]
        bs = sorted([b for b in bs if abs((b[1] + b[3]) / 2 - yc) <= 0.6 * hh], key=lambda b: b[0])
        if len(bs) != p["n"] + 1:
            continue
        if bs[-1][0] > hi - 0.3 * hh:
            return {"ok": True, "fi": fi, "ms": ms, "side": "R", "box": [float(v) for v in bs[-1]]}
        if bs[0][2] < lo + 0.3 * hh:
            return {"ok": True, "fi": fi, "ms": ms, "side": "L", "box": [float(v) for v in bs[0]]}
    return {"ok": False, "why": "n+1 상자 프레임 없음"}


def cmd_find(a):
    for tid in ids_of(a.ids):
        q = d_prompt(tid)
        print(tid, q if not q["ok"] else f"프레임 {q['fi']} · {q['side']} · 상자 {[round(v) for v in q['box']]}")


def cmd_run(a):
    import torch
    from sam2.build_sam import build_sam2_video_predictor
    torch.set_num_threads(16)
    if a.device == "xpu":
        assert torch.xpu.is_available(), "XPU 없음 — venvs/sam2_xpu 의 python 으로 돌릴 것"
    cfg, ck = s1.CFG["t"]
    pred = build_sam2_video_predictor(cfg, str(s1.CKPT / ck), device=a.device)
    for tid in ids_of(a.ids):
        d = s1.run_dir(tid, V1)
        if (d / "dtrack.json").exists() and not a.force:
            print(tid, "있음 — 건너뜀")
            continue
        q = d_prompt(tid)
        if not q["ok"]:
            print(tid, q["why"])
            continue
        tr = hc.jload(d / "track.json")
        F = len(tr["frames"])
        t0 = time.time()
        rec, keep = {}, {}
        with torch.inference_mode():
            st = pred.init_state(video_path=str(d / "frames"), offload_video_to_cpu=True, offload_state_to_cpu=True)
            pred.add_new_points_or_box(st, frame_idx=q["fi"], obj_id=1, box=np.array(q["box"], np.float32))
            for fi, oids, logits in pred.propagate_in_video(st, start_frame_idx=q["fi"]):
                m = (logits[0][0] > 0).cpu().numpy()
                ys, xs = np.nonzero(m)
                rec[int(fi)] = [int(m.sum()), float(xs.mean()) if len(xs) else None, float(ys.mean()) if len(ys) else None]
                keep[int(fi)] = np.packbits(m)
                if fi % 20 == 0:
                    print(f"  {tid} {fi}/{F} {time.time() - t0:.0f}s", flush=True)
        np.savez_compressed(d / "dmasks.npz", **{str(fi): v for fi, v in keep.items()})
        hc.jsave(d / "dtrack.json", {"id": tid, "prompt": q, "frames": F, "device": a.device, "sec": round(time.time() - t0, 1), "rec": rec}, indent=None)
        print(f"{tid} 끝 {time.time() - t0:.0f}s (D 프레임 {q['fi']} → {F - 1})", flush=True)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("find", "run"):
        q = sp.add_parser(name)
        q.add_argument("--ids")
        if name == "run":
            q.add_argument("--device", default="cpu")
            q.add_argument("--force", action="store_true")
    a = ap.parse_args()
    {"find": cmd_find, "run": cmd_run}[a.cmd](a)


if __name__ == "__main__":
    main()
