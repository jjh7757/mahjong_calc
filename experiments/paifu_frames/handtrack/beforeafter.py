"""손에서 냄의 들어간 칸을 앞뒤 정지 프레임의 줄 비교로 찾기(2026-11-16, 계획서 3단계 "추가" — 규칙은 결과 전에 적음).

손이 들어오기 전 마지막 정지 프레임과 떠난 뒤 첫 정지 프레임에서 손패 줄의 패를 하나씩 잘라 "자세"(윗면 회색 높이·
흰 면 시작 높이·위·아래 끝·기울기·폭)를 재고, 나간 칸 k × 들어간 칸 j 가설마다 짝지은 패끼리 자세 차이를 견준다.
줄이 통째로 밀리면 위치는 패 폭 단위로만 뜻이 있어 x 위치는 쓰지 않는다.

  python -X utf8 beforeafter.py <판 id> [--replay <replay2 json>] [--draw]
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
from bandfit import tile_mask  # noqa: E402

N = 13
PAD_MS = 200  # 활동 구간 경계에서 이만큼 바깥 프레임 = 정지
TRIM = 0  # 처음 2 였으나 정지 줄 확인에서 이웃 칸 가설(짝 하나만 다름)의 차이를 지워 버려 0 으로(2026-11-16)


def row_band(m: np.ndarray) -> tuple[int, int] | None:
    frac = m.mean(1)
    rows = frac > 0.12
    best, cur = None, None
    for y, r in enumerate(rows):
        if r:
            cur = [y, y] if cur is None else [cur[0], y]
            if best is None or cur[1] - cur[0] > best[1] - best[0]:
                best = list(cur)
        else:
            cur = None
    return tuple(best) if best and best[1] - best[0] >= 20 else None


def tiles_in(v: np.ndarray) -> list[dict] | None:
    """돌린 띠 그림에서 줄의 패 칸 목록(왼→오). 실패면 None."""
    m = tile_mask(v)
    rb = row_band(m)
    if rb is None:
        return None
    y0, y1 = rb
    col = m[y0:y1 + 1].mean(0)
    gray = cv2.cvtColor(v, cv2.COLOR_RGB2GRAY).astype(float)
    # 틈은 어두운 세로 줄: 줄 아래 절반(흰 면) 밝기를 열마다 본다
    lo = gray[(y0 + y1) // 2:y1 + 1].mean(0)
    on = col > 0.5
    xs = np.flatnonzero(on)
    if len(xs) < 100:
        return None
    x_first, x_last = xs[0], xs[-1]
    prof = np.convolve(lo, np.ones(3) / 3, mode="same")
    # 틈 후보: 이웃보다 어두운 극소(패 폭 25px 이상 떨어짐)
    cand = [x for x in range(x_first + 15, x_last - 15) if prof[x] <= prof[x - 6:x + 7].min() + 1e-9]
    cuts = []
    for x in sorted(cand, key=lambda x: prof[x]):
        if all(abs(x - c) >= 25 for c in cuts):
            cuts.append(x)
    edges = [x_first] + sorted(cuts) + [x_last]
    widths = np.diff(edges)
    pitch = np.median(widths)
    # 너무 얕은 틈(밝기 차가 작은 것)이 쪼갠 칸은 다시 합친다
    out = []
    for a, b in zip(edges, edges[1:]):
        if b - a < 0.55 * pitch and out:
            out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    tiles = []
    hsv_all = cv2.cvtColor(v, cv2.COLOR_RGB2HSV)
    # 펠트(초록)가 아닌 화소 = 패(회색 윗면 포함). tile_mask 는 회색 윗면을 안 잡아 위 끝이 보라 줄로 잡혔다(첫 실행에서 발견).
    felt = (hsv_all[..., 0] >= 35) & (hsv_all[..., 0] <= 95) & (hsv_all[..., 1] > 50)
    body = ~felt
    for a, b in out:
        w = b - a
        c0, c1 = a + w // 4, b - w // 4
        sub = body[:, c0:c1 + 1]
        tops, bots, whites, idx = [], [], [], []
        hsv = hsv_all[:, c0:c1 + 1]
        white = (hsv[..., 1] < 45) & (hsv[..., 2] > 170)
        for i in range(sub.shape[1]):
            wy = np.flatnonzero(white[y0:y1 + 1, i])
            if len(wy) < 5:
                continue
            w0, w1 = y0 + wy[0], y0 + wy[-1]
            t_ = w0
            while t_ > max(0, y0 - 30) and sub[t_ - 1, i]:
                t_ -= 1
            b_ = w1
            while b_ < sub.shape[0] - 1 and sub[b_ + 1, i]:
                b_ += 1
            tops.append(t_)
            bots.append(b_)
            whites.append(w0)
            idx.append(i)
        if len(tops) < 3:
            return None
        tilt = np.polyfit(idx, tops, 1)[0] if len(set(tops)) > 1 else 0.0
        tiles.append({"x0": int(a), "x1": int(b), "w": float(w), "top": float(np.median(tops)), "bot": float(np.median(bots)),
                      "white": float(np.median(whites)), "tilt": float(tilt)})
    return tiles


def feat(t: dict) -> np.ndarray:
    # 회색 윗면 높이(white - top)는 앞뒤 기울기, top·bot 은 세로 자리, tilt 는 좌우 기울기(×20 으로 px 비슷한 크기), 폭
    return np.array([t["white"] - t["top"], t["top"], t["bot"], t["tilt"] * 20, t["w"]])


def mapping(k: int | None, j: int | None, n: int = N) -> list[tuple[int, int]]:
    """(after 칸, before 칸) 짝(1부터). k=None 이면 쯔모기리(줄 그대로). j 칸의 새 패는 짝 없음."""
    if k is None:
        return [(i, i) for i in range(1, n + 1)]
    pairs = []
    b = [i for i in range(1, n + 1) if i != k]  # 남은 before n-1장, 순서 그대로
    a = [i for i in range(1, n + 1) if i != j]
    return list(zip(a, b))


def score(A: list[dict], B: list[dict], pairs) -> float:
    d = np.array([feat(A[a - 1]) - feat(B[b - 1]) for a, b in pairs])
    d[:, 1:3] -= np.median(d[:, 1:3], 0)  # 줄 전체 세로 이동은 뺌
    e = np.abs(d).sum(1)
    e.sort()
    return float(e[:len(e) - TRIM].mean())


def turns_from_replay(rp: dict, sg: dict) -> list[dict]:
    """replay2 결과에서 차례마다 (첫 구간, 마지막 구간, 판정 요약)."""
    act = {a["seg"]: a for a in sg["active"]}
    plan = [p for p in rp["plan"] if p["events"]]
    out, cur = [], None
    for p in plan:
        ev = p["events"]
        if any(e.startswith("draw") for e in ev) or cur is None:
            if cur:
                out.append(cur)
            cur = {"segs": [p["seg"]], "events": list(ev)}
        else:
            cur["segs"].append(p["seg"])
            cur["events"] += ev
    if cur:
        out.append(cur)
    tmap = {t["seg"]: t for t in rp["turns"]}
    res = []
    for c in out:
        t = tmap.get(c["segs"][0])
        if not t or "reveal" in " ".join(c["events"]):
            continue
        # 버림 구간까지만(뒤 구간의 call 등은 그 차례에 넣지 않음 — 첫 discard 가 든 구간까지)
        last = next((s for s, p in zip(c["segs"], [x for x in plan if x["seg"] in c["segs"]]) if any(e.startswith("discard") for e in p["events"])), c["segs"][-1])
        res.append({"t": t["t"], "segs": c["segs"], "seg_end": last, "mode": t["mode"], "out": t["out_slots"], "in": t["in_slots"],
                    "events": c["events"], "ms_before": act[c["segs"][0]]["ms0"] - PAD_MS, "ms_after": act[last]["ms1"] + PAD_MS})
    return res


def run(gid: str, rp_path: str | None, draw: bool):
    cfg = hc.config(gid)
    sg = hc.jload(hc.OUT / gid / "segments.json")
    rp = hc.jload(rp_path or glob.glob(str(hc.OUT / gid / "replay2_B" / "*.json"))[0])
    rows = []
    for tr in turns_from_replay(rp, sg):
        fb, fa = hc.nearest(tr["ms_before"]), hc.nearest(tr["ms_after"])
        vb = hc.band_crop(hc.load(fb), cfg["sheet_band"], cfg["side"])
        va = hc.band_crop(hc.load(fa), cfg["sheet_band"], cfg["side"])
        B, A = tiles_in(vb), tiles_in(va)
        row = {"t": tr["t"], "segs": tr["segs"], "mode": tr["mode"], "judged_out": tr["out"], "judged_in": tr["in"], "events": tr["events"],
               "before": hc.hms(fb), "after": hc.hms(fa), "n_before": len(B) if B else None, "n_after": len(A) if A else None}
        if B and A and len(B) == len(A) and len(B) >= 8:  # 울기 뒤엔 10장 — 앞뒤 장수가 같으면 그 장수로
            n = len(B)
            # k=j 가설이 "줄 그대로"(쯔모기리)와 같은 짝이라 따로 두지 않는다(짝 수를 n-1 로 맞춤 — TRIM 0 과 함께 고침)
            hyp = [((k, j), score(A, B, mapping(k, j, n))) for k in range(1, n + 1) for j in range(1, n + 1)]
            hyp.sort(key=lambda x: x[1])
            (k, j), s0 = hyp[0]
            row.update(best_k=k, best_j=j, best=round(s0, 2), second=round(hyp[1][1], 2), second_kj=list(hyp[1][0]),
                       margin=round(hyp[1][1] - s0, 2),
                       # 판정의 나간 칸이 한 칸이면 그 k 를 고정했을 때 j 순위(검증과 따로 보는 참고)
                       top5=[[list(h[0]), round(h[1], 2)] for h in hyp[:5]])
            ks = [x for x in tr["out"] if isinstance(x, int)]
            if len(ks) == 1 and tr["mode"] == "손에서":
                fixed = sorted(((j_, s) for (k_, j_), s in hyp if k_ == ks[0]), key=lambda x: x[1])
                row["j_given_judged_k"] = [[j_, round(s, 2)] for j_, s in fixed[:4]]
        rows.append(row)
        if draw:
            dd = hc.out_dir(gid) / "beforeafter"
            dd.mkdir(exist_ok=True)
            pic = []
            for v, T in ((vb, B), (va, A)):
                v = v.copy()
                for i, t in enumerate(T or []):
                    cv2.rectangle(v, (t["x0"], int(t["top"])), (t["x1"], int(t["bot"])), (255, 0, 0), 1)
                    cv2.putText(v, str(i + 1), (t["x0"] + 3, int(t["top"]) - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
                pic.append(v)
            cv2.imwrite(str(dd / f"t{tr['t']:02d}.jpg"), cv2.cvtColor(np.concatenate(pic, 0), cv2.COLOR_RGB2BGR))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game")
    ap.add_argument("--replay")
    ap.add_argument("--draw", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    rows = run(a.game, a.replay, a.draw)
    for r in rows:
        print(json.dumps({k: r.get(k) for k in ("t", "segs", "mode", "judged_out", "judged_in", "n_before", "n_after", "best_k", "best_j", "best",
                                                  "second_kj", "margin", "j_given_judged_k")}, ensure_ascii=False))
    if a.out:
        hc.jsave(a.out, rows)


if __name__ == "__main__":
    main()
