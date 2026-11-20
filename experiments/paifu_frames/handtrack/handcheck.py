"""손 관절점 확인 그림(2026-11-20) — MediaPipe Hands(OpenVINO GPU 판, handpose.py) 관절점이 실제 손끝에 맞게 찍히는지
사람 눈으로 판정할 그림 60장과 목록을 만든다. 판정은 따로(이 스크립트는 그림 · 목록만, 정답은 읽지 않음).

  python -X utf8 handcheck.py            # → _work/handcheck_1120/img/hNN.jpg · key.json · list.txt

입력: _work/hands_1120/<id>/ov_GPU_w220.json 이 있는 차례 전부(79차례: r12 · r13 · r15 · r16 · r17 · r19 · L16).
  관절점 lm 은 원래 band2 그림 좌표 → 넓힌 띠 그림 좌표 = lm − (dx, dy)(frames_w220.json 의 dx, dy).
  프레임 그림은 handdump.dump() 처럼 hc.band_crop(hc.load(ms), band, side) 로 그 프레임만 다시 자름.
칸 틀 · "그 사람 손": handevents.grid_src(tid) 의 칸 틀(left0 · pitch · top · bot, band2 좌표)과
  handevents.frame_states(tid, "_w220", "index") 의 규칙을 own_rows() 에 그대로 옮김(고른 손 번호를 알려고).
  옮긴 규칙이 같은 답을 내는지 차례마다 frame_states 와 (상태, 칸)을 견주어 다르면 멈춤.

표본 60장(random.Random(1120), 아래 순서대로 한 난수열):
  판 = 차례 id 앞 세 글자(7개). 판별 몫: 30 = 7 × 4 + 2 → 묶음마다 판 7개를 섞어 앞 2개 판이 5장, 나머지 4장.
  A 30장 — 사건 프레임: 그 사람 손이 잡혔고 상태(검지 끝 기준)가 "줄" 또는 "강 쪽" 인 프레임.
  B 30장 — 무작위 프레임: 79차례의 모든 프레임(손 없는 프레임 포함), A 에 뽑힌 프레임은 뺌.
  판 안에서 고르기(A · B 같음): 후보가 있는 차례를 섞고, 1바퀴째는 차례마다 1장씩(차례 안 후보에서 무작위),
    몫이 남으면 차례를 다시 섞어 2바퀴째 1장씩 더 — 그래서 한 차례에서 묶음당 2장을 넘지 않음.
  A 를 먼저 다 뽑고 B 를 뽑음. 60장을 섞어 h01 ~ h60 번호(판정하는 쪽이 A/B 를 모르게).
그림(표본마다 한 장): 왼쪽 = 넓힌 띠 원본, 오른쪽 = 같은 그림에 덧그림. 원본 긴 변이 1000 화소 이하면 2배, 넘으면 1.5배.
  위에 "hNN" 만. 덧그림: 칸 틀(줄 위 · 아래 가로선, 칸 경계 세로선 left0 + k·pitch, k = 0 … n — 얇은 흰색),
  잡힌 손 모두의 21점 · 뼈대(그 사람 손 = 노랑, 다른 손 = 회색), 그 사람 손의 검지 끝(8) = 빨간 원 · 엄지 끝(4) = 파란 원
  (반지름 pitch / 2 · 가운데 작은 점), 다른 손의 4 · 8 은 작은 점만, 그 사람 손의 엄지 · 검지 가운데 = 초록 작은 ×.
key.json(판정자에게 주지 않음): 번호 → {id, i, ms, set, hands, own, state, slot_index, slot_mid, pitch, pitch_img, ...}.
list.txt(판정자에게 줌): "hNN 그림경로" 줄만.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import handevents as he  # noqa: E402
import htcommon as hc  # noqa: E402

SRC = hc.WORK / "hands_1120"
OUT = hc.WORK / "handcheck_1120"
TAG = "_w220"
SEED = 1120
N_PER_SET = 30
EVENT_STATES = ("줄", "강 쪽")
CONN = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11), (11, 12),
        (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (0, 17), (17, 18), (18, 19), (19, 20)]   # MediaPipe HAND_CONNECTIONS
YELLOW, GRAY, RED, BLUE, GREEN, WHITE = (255, 230, 0), (170, 170, 170), (255, 40, 40), (40, 120, 255), (0, 230, 60), (255, 255, 255)


def own_rows(tid: str):
    """handevents.frame_states(tid, TAG, "index") 와 같은 규칙 — 프레임마다 고른 손 번호(f["hands"] 안 순번)도 남김.
    → (n, 칸 틀, rows[{i, t, hands, own, state, slot_index, slot_mid}], meta, band2 좌표의 hands 목록)."""
    (left0, pitch, top, bot, nbox), n, src = he.grid_src(tid)
    h = bot - top
    data = hc.jload(SRC / tid / f"ov_GPU{TAG}.json")["frames"]
    meta = {r["i"]: r for r in hc.jload(SRC / tid / f"frames{TAG}.json")["frames"]}
    rows = []
    prev_wrist = None
    for f in data:
        hs = f["hands"]
        own = [j for j, hd in enumerate(hs) if hd["lm"][0][1] > bot or hd["lm"][9][1] > top]
        if not own and prev_wrist is not None:
            own = [j for j, hd in enumerate(hs)
                   if np.hypot(hd["lm"][0][0] - prev_wrist[0], hd["lm"][0][1] - prev_wrist[1]) < 2.5 * np.hypot(hd["lm"][0][0] - hd["lm"][9][0], hd["lm"][0][1] - hd["lm"][9][1])]
        r = {"i": f["i"], "t": f["t"], "hands": hs, "own": None, "state": None, "slot_index": None, "slot_mid": None}
        if not own:
            rows.append(r)
            prev_wrist = None
            continue
        j = max(own, key=lambda q: hs[q]["lm"][0][1])   # max 는 같은 값이면 앞의 것 — frame_states 와 같음
        hd = hs[j]
        prev_wrist = hd["lm"][0]
        x, y = he.point_of(hd["lm"], "index")
        xm, _ = he.point_of(hd["lm"], "mid")
        knuckle_y = hd["lm"][9][1]
        if y < top - he.OFF_MARGIN * h:
            st = "위" if knuckle_y >= top else "강 쪽"
        elif y > bot + he.OFF_MARGIN * h:
            st = "몸 쪽"
        else:
            st = "줄"
        r.update(own=j, state=st, slot_index=he.slot_of(x, left0, pitch, n), slot_mid=he.slot_of(xm, left0, pitch, n))
        rows.append(r)
    for k, r in enumerate(rows):
        if r["state"] == "위":
            gone = all(q < len(rows) and rows[q]["state"] is None for q in (k + 1, k + 2))
            r["state"] = "강 쪽" if gone else "줄"
    return n, (left0, pitch, top, bot, nbox), rows, meta, src


def check_same(tid: str, rows: list):
    """옮긴 규칙이 handevents.frame_states 와 (상태, 검지 칸)이 같은지."""
    _, ref, _, _, _ = he.frame_states(tid, TAG, "index")
    assert len(ref) == len(rows), tid
    for a, b in zip(ref, rows):
        assert a[0] == b["i"] and a[2] == b["state"] and a[3] == b["slot_index"], (tid, a, b["i"], b["state"], b["slot_index"])


def quotas(rng: random.Random, boards: list) -> dict:
    order = boards[:]
    rng.shuffle(order)
    extra = N_PER_SET - 4 * len(order)
    return {b: 4 + (1 if k < extra else 0) for k, b in enumerate(order)}


def pick_set(rng: random.Random, cand: dict, quota: dict) -> list:
    """cand: 판 → {차례 → [프레임 i ...]}. 판마다 quota 장 — 차례마다 1장씩 두 바퀴까지."""
    out = []
    for b in sorted(cand):
        need = quota[b]
        taken = {t: [] for t in cand[b]}
        for _round in range(2):
            ts = sorted(t for t in cand[b] if len(cand[b][t]) > len(taken[t]))
            rng.shuffle(ts)
            for t in ts:
                if need == 0:
                    break
                left = [i for i in cand[b][t] if i not in taken[t]]
                i = rng.choice(left)
                taken[t].append(i)
                out.append((t, i))
                need -= 1
            if need == 0:
                break
        if need:
            raise RuntimeError(f"{b}: 후보 모자람({need}장 남음)")
    return out


def font(size: int):
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size)


def render(label: str, rgb: np.ndarray, grid: tuple, n: int, dxy: tuple, hands: list, own, scale: float) -> Image.Image:
    left0, pitch, top, bot, _ = grid
    dx, dy = dxy
    H, W = rgb.shape[:2]
    Ws, Hs = int(round(W * scale)), int(round(H * scale))
    base = Image.fromarray(rgb).resize((Ws, Hs), Image.LANCZOS)
    over = base.copy()
    d = ImageDraw.Draw(over)

    def P(x, y):   # band2 그림 좌표 → 넓힌 띠 · 키운 그림 화소
        return ((x - dx) * scale, (y - dy) * scale)

    lw = max(1, int(round(scale)))
    for yy in (top, bot):
        d.line([P(0 + dx, yy), P(W + dx, yy)], fill=WHITE, width=lw)
    for k in range(n + 1):
        x = left0 + k * pitch
        d.line([P(x, top), P(x, bot)], fill=WHITE, width=lw)
    rad = pitch / 2 * scale
    dot = max(2.5, 2 * scale)
    order = [j for j in range(len(hands)) if j != own] + ([own] if own is not None else [])   # 그 사람 손을 맨 위에
    for j in order:
        lm = hands[j]["lm"]
        pts = [P(x, y) for x, y in lm]
        mine = j == own
        col = YELLOW if mine else GRAY
        for a, b in CONN:
            d.line([pts[a], pts[b]], fill=col, width=max(2, int(round(1.5 * scale))))
        for x, y in pts:
            d.ellipse([x - dot, y - dot, x + dot, y + dot], fill=col)
        for t, c in ((8, RED), (4, BLUE)):
            x, y = pts[t]
            if mine:
                d.ellipse([x - rad, y - rad, x + rad, y + rad], outline=c, width=max(2, int(round(1.5 * scale))))
                d.ellipse([x - 1.3 * dot, y - 1.3 * dot, x + 1.3 * dot, y + 1.3 * dot], fill=c)
            else:
                d.ellipse([x - dot, y - dot, x + dot, y + dot], fill=c)
        if mine:
            mx, my = (pts[4][0] + pts[8][0]) / 2, (pts[4][1] + pts[8][1]) / 2
            s = 3 * scale
            d.line([(mx - s, my - s), (mx + s, my + s)], fill=GREEN, width=lw + 1)
            d.line([(mx - s, my + s), (mx + s, my - s)], fill=GREEN, width=lw + 1)
    head, gap = 34, 12
    canvas = Image.new("RGB", (2 * Ws + gap, Hs + head), (0, 0, 0))
    canvas.paste(base, (0, head))
    canvas.paste(over, (Ws + gap, head))
    ImageDraw.Draw(canvas).text((8, 4), label, fill=WHITE, font=font(24))
    return canvas


def main():
    tids = sorted(p.parent.name for p in SRC.glob(f"*/ov_GPU{TAG}.json"))
    print(len(tids), "차례")
    info = {}
    for tid in tids:
        n, grid, rows, meta, src = own_rows(tid)
        check_same(tid, rows)
        fj = hc.jload(SRC / tid / f"frames{TAG}.json")
        info[tid] = {"n": n, "grid": grid, "rows": {r["i"]: r for r in rows}, "meta": meta, "src": src,
                     "band": fj["band"], "side": fj["side"], "dx": fj["dx"], "dy": fj["dy"]}
    boards = sorted({t[:3] for t in tids})
    assert len(boards) == 7, boards
    rng = random.Random(SEED)
    # A: 사건 프레임
    qa = quotas(rng, boards)
    ca = {b: {} for b in boards}
    for tid, v in info.items():
        ii = [i for i, r in v["rows"].items() if r["own"] is not None and r["state"] in EVENT_STATES]
        if ii:
            ca[tid[:3]][tid] = sorted(ii)
    A = pick_set(rng, ca, qa)
    # B: 모든 프레임에서, A 뺌
    qb = quotas(rng, boards)
    aset = set(A)
    cb = {b: {} for b in boards}
    for tid, v in info.items():
        cb[tid[:3]][tid] = sorted(i for i in v["rows"] if (tid, i) not in aset)
    B = pick_set(rng, cb, qb)
    samples = [("A", t, i) for t, i in A] + [("B", t, i) for t, i in B]
    rng.shuffle(samples)
    (OUT / "img").mkdir(parents=True, exist_ok=True)
    key, lines = {}, []
    for k, (st, tid, i) in enumerate(samples, 1):
        name = f"h{k:02d}"
        v = info[tid]
        r = v["rows"][i]
        ms = v["meta"][i]["ms"]
        rgb = hc.band_crop(hc.load(ms), v["band"], v["side"])
        scale = 2.0 if max(rgb.shape[:2]) <= 1000 else 1.5
        img = render(name, rgb, v["grid"], v["n"], (v["dx"], v["dy"]), r["hands"], r["own"], scale)
        f = OUT / "img" / f"{name}.jpg"
        img.save(f, quality=92)
        left0, pitch, top, bot, nbox = v["grid"]
        e = {"id": tid, "i": i, "ms": ms, "t": r["t"], "set": st, "hands": len(r["hands"]), "own": r["own"],
             "state": r["state"], "slot_index": r["slot_index"], "slot_mid": r["slot_mid"], "n": v["n"],
             "pitch": round(pitch, 2), "pitch_img": round(pitch * scale, 2), "scale": scale,
             "grid_band2": {"left0": round(left0, 1), "top": round(top, 1), "bot": round(bot, 1)}, "grid_src": v["src"],
             "crop_wh": [rgb.shape[1], rgb.shape[0]], "img_wh": list(img.size)}
        if r["own"] is not None:   # 덧그림(오른쪽 절반 안, 머리 띠 뺀) 화소 — 판정 뒤 대조용
            lm = r["hands"][r["own"]]["lm"]
            e["tip8_img"] = [round((lm[8][0] - v["dx"]) * scale, 1), round((lm[8][1] - v["dy"]) * scale, 1)]
            e["tip4_img"] = [round((lm[4][0] - v["dx"]) * scale, 1), round((lm[4][1] - v["dy"]) * scale, 1)]
        key[name] = e
        lines.append(f"{name} {f.as_posix()}")
        print(name, st, tid, i, r["t"], "손", len(r["hands"]), "own", r["own"], r["state"], img.size)
    hc.jsave(OUT / "key.json", key)
    with open(OUT / "list.txt", "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    cnt = {}
    for st, tid, _ in samples:
        cnt.setdefault(tid[:3], {"A": 0, "B": 0})[st] += 1
    print("판별 A/B:", cnt)
    print("→", OUT)


if __name__ == "__main__":
    main()
