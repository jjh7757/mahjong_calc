"""판 중 배경 프레임(추적 기록 frames_##.zip, 1020×764)으로 불완전 패보(자리별 버림 순서·패·울어 간 패)를 만드는 시험.

2026-11-09 사용자 질문 "게임 1판했을 때 배패순서 기록 가능하니 (플레이어1: 3만 버림, 플레이어2: 4만 버림, 플레이어3: 56만 치)".
앱의 실시간 강 추적(river_tracker.dart, 흰 면적만 봄)은 패 종류를 모르고 실제 대국에서 버림을 많이 놓쳐서(동3국 6분에 17번),
여기서는 서버 자체 모델(검출 tile-yolo26n + 분류 read_small)을 프레임마다 돌려 강 패를 자리별로 추적한다.

1단계 detect: 프레임마다 가운데(기계 둘레)만 잘라 검출 → 흰 면 거르기 → 기계 기준 바람개비 규칙으로 자리 배정 → 패마다 read_small.
   결과는 <out>/<round>/det.json(다시 돌리지 않게).
2단계 track: 자리마다 위치로 프레임 사이 같은 패를 잇고(2프레임 이상 보이면 버림), 끝까지 다시 안 보이면 울어 감(taken).
   패 = 프레임 읽기의 확신도 합 투표. 자리 안 순서 = 강 위치(줄·칸), 자리 사이 순서 = 처음 보인 시각.
사용: python paifu_frames.py <track 폴더> <out> [--rounds R3a ...]  (rounds.json 에 판 정의)
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

REC = Path(r"C:\Users\jjh7757\dev\mahjong-recognizer")
sys.path.insert(0, str(REC))
from app import river as rv  # noqa: E402
from app.local_read import LocalReader  # noqa: E402

SIDES = ("bottom", "right", "top", "left")
HERE = Path(__file__).parent


def to_side(side: str, dx: float, dy: float) -> tuple[float, float]:
    """이미지 기준 기계 중심 상대 좌표 → 그 자리 기준 (u = 강이 늘어나는 쪽, v = 바깥쪽)."""
    return {"bottom": (dx, dy), "right": (-dy, dx), "top": (-dx, -dy), "left": (dy, -dx)}[side]


def device_box(rgb: np.ndarray, cx: float, cy: float, r: int = 160) -> tuple[float, float, float]:
    """기계(어두운 사각형)의 중심·반 크기. 펠트(초록)도 패(흰)도 아닌 어두운 화소의 분위수로."""
    H, W = rgb.shape[:2]
    x0, y0, x1, y1 = int(max(0, cx - r)), int(max(0, cy - r)), int(min(W, cx + r)), int(min(H, cy + r))
    a = rgb[y0:y1, x0:x1].astype(int)
    dark = (a.max(2) < 90) & ~((a[..., 1] > a[..., 0] + 25) & (a[..., 1] > a[..., 2]))
    ys, xs = np.nonzero(dark)
    if len(xs) < 500:
        return cx, cy, 70.0
    lx, hx = np.percentile(xs, [3, 97])
    ly, hy = np.percentile(ys, [3, 97])
    return x0 + (lx + hx) / 2, y0 + (ly + hy) / 2, ((hx - lx) + (hy - ly)) / 4


def assign(cx, cy, hd, box) -> tuple[str, float, float] | None:
    """패 상자 → (자리, u, v). 기계 바깥 한 변 띠(v > hd·0.8)에 들고 u 가 기계 폭 안팎이면. 모서리는 u 넘침이 작은 쪽."""
    bx, by = box[0] + box[2] / 2 - cx, box[1] + box[3] / 2 - cy
    best = None
    for s in SIDES:
        u, v = to_side(s, bx, by)
        if v < hd * 0.8 or v > hd * 2.6 or u < -hd * 1.3 or u > hd * 1.7:
            continue
        over = max(0.0, abs(u) - hd) if u < 0 else max(0.0, u - hd * 1.05)
        key = (over, v)
        if best is None or key < best[0]:
            best = (key, s, u, v)
    return None if best is None else (best[1], best[2], best[3])


def frames_of(track: Path, t0: str | None, t1: str | None):
    for z in sorted(track.glob("frames_*.zip")):
        zf = zipfile.ZipFile(z)
        meta = json.loads(zf.read("frames.json"))
        for f in meta["frames"]:
            hhmmss = f["at"][11:19]
            if (t0 and hhmmss < t0) or (t1 and hhmmss > t1):
                continue
            yield f, meta["grid"], zf.read(f["file"])


def detect_round(reader: LocalReader, track: Path, t0, t1, out: Path) -> dict:
    # 기계 위치는 판마다 한 번: 프레임마다 재면 패 무늬·손이 어두운 화소로 끼어 커진다(첫 실행 hd 67 → 97).
    # 가장 작게 잰 값들(최소의 1.08배 안)의 중앙값 = 강이 비었거나 덜 찬 프레임.
    est = []
    for f, grid, jpg in frames_of(track, t0, t1):
        rgb = np.asarray(Image.open(io.BytesIO(jpg)).convert("RGB"))
        H, W = rgb.shape[:2]
        est.append(device_box(rgb, (grid["x1"] + grid["x2"]) / 2000 * W, (grid["y1"] + grid["y2"]) / 2000 * H))
    m = min(e[2] for e in est)
    good = [e for e in est if e[2] <= m * 1.08]
    cx, cy, hd = (float(np.median([e[i] for e in good])) for i in range(3))
    print(f"기계 {cx:.1f},{cy:.1f} 반 {hd:.1f} ({len(good)}/{len(est)} 프레임)")
    res = []
    for f, grid, jpg in frames_of(track, t0, t1):
        rgb = np.asarray(Image.open(io.BytesIO(jpg)).convert("RGB"))
        H, W = rgb.shape[:2]
        R = int(hd * 3.2)
        x0, y0 = int(max(0, cx - R)), int(max(0, cy - R))
        crop = rgb[y0:int(min(H, cy + R)), x0:int(min(W, cx + R))]
        boxes = rv.dedupe(rv.keep_faces(reader.detect(crop, low=False), rv.white_mask(crop), 0.45))
        tiles = []
        for b in boxes:
            gb = (b[0] + x0, b[1] + y0, b[2], b[3])
            a = assign(cx, cy, hd, gb)
            if a is None:
                continue
            t, c = reader.read_small(rgb, gb)
            tiles.append({"box": gb, "side": a[0], "u": round(a[1], 1), "v": round(a[2], 1), "t": t, "c": c})
        res.append({"file": f["file"], "at": f["at"], "dev": [round(cx, 1), round(cy, 1), round(hd, 1)], "tiles": tiles})
        print(f["file"], len(tiles), {s: sum(1 for t in tiles if t["side"] == s) for s in SIDES}, flush=True)
    out.mkdir(parents=True, exist_ok=True)
    (out / "det.json").write_text(json.dumps(res, ensure_ascii=False, indent=0), encoding="utf-8")
    return {"frames": res}


def overlay(track: Path, det: list, out: Path, files: list[str]):
    want = set(files)
    col = {"bottom": "red", "right": "yellow", "top": "cyan", "left": "magenta"}
    by = {d["file"]: d for d in det}
    for f, grid, jpg in frames_of(track, None, None):
        if f["file"] not in want or f["file"] not in by:
            continue
        im = Image.open(io.BytesIO(jpg)).convert("RGB")
        dr = ImageDraw.Draw(im)
        d = by[f["file"]]
        cx, cy, hd = d["dev"]
        dr.rectangle((cx - hd, cy - hd, cx + hd, cy + hd), outline="white")
        for t in d["tiles"]:
            x, y, w, h = t["box"]
            dr.rectangle((x, y, x + w, y + h), outline=col[t["side"]], width=2)
            dr.text((x, y - 10), t["t"], fill=col[t["side"]])
        R = int(hd * 3.2)
        im = im.crop((int(cx - R), int(cy - R), int(cx + R), int(cy + R)))
        im = im.resize((im.width * 2, im.height * 2))
        im.save(out / f"ov_{f['file']}")


# ------------------------------------------------------------------ 2단계: 추적


def track_round(det: list, min_seen: int = 2, gone_frames: int = 3) -> dict:
    """자리마다 위치로 잇기. 반환: {side: [ {first, last, seen, u, v, votes, taken} ...]}"""
    out = {}
    hd_all = [d["dev"][2] for d in det]
    hd = float(np.median(hd_all))
    tol = hd * 0.17  # 패 폭(기계 반 크기의 약 0.3)의 절반 남짓
    times = [d["at"] for d in det]
    for s in SIDES:
        tracks: list[dict] = []
        for fi, d in enumerate(det):
            cur = [t for t in d["tiles"] if t["side"] == s]
            used = set()
            for t in cur:
                best, bd = None, tol
                for k, tr in enumerate(tracks):
                    if k in used:
                        continue
                    dd = ((tr["u"] - t["u"]) ** 2 + (tr["v"] - t["v"]) ** 2) ** 0.5
                    if dd < bd:
                        best, bd = k, dd
                if best is None:
                    tracks.append({"first": fi, "last": fi, "seen": [fi], "u": t["u"], "v": t["v"], "reads": [(t["t"], t["c"])]})
                    used.add(len(tracks) - 1)
                else:
                    tr = tracks[best]
                    used.add(best)
                    tr["last"] = fi
                    tr["seen"].append(fi)
                    n = len(tr["seen"])
                    tr["u"] = (tr["u"] * (n - 1) + t["u"]) / n
                    tr["v"] = (tr["v"] * (n - 1) + t["v"]) / n
                    tr["reads"].append((t["t"], t["c"]))
        last = len(det) - 1
        keep = []
        for tr in tracks:
            if len(tr["seen"]) < min_seen and tr["first"] < last:
                continue
            votes: dict = {}
            for t, c in tr["reads"]:
                votes[t] = votes.get(t, 0) + c
            tr["tile"] = max(votes, key=votes.get)
            tr["vote"] = round(votes[tr["tile"]] / sum(votes.values()), 2)
            tr["last_read"] = tr["reads"][-1][0]
            tr["first_at"] = times[tr["first"]][11:19]
            tr["taken"] = tr["last"] <= last - gone_frames
            keep.append(tr)
        # 줄(바깥쪽 v)·칸(u) 순서
        th = hd * 0.4  # 패 높이 어림
        if keep:
            v0 = min(t["v"] for t in keep)
            for t in keep:
                t["row"] = int(round((t["v"] - v0) / th))
        keep.sort(key=lambda t: (t["row"], t["u"]))
        out[s] = keep
    return out


def order_tiles(tiles: list, hd: float) -> list:
    """한 프레임 한 자리의 패를 강 순서로: v(바깥쪽)로 줄을 나누고(틈 > 패 높이 0.55) 줄 안은 u 순."""
    th = hd * 0.42
    ts = sorted(tiles, key=lambda t: t["v"])
    rows, cur = [], []
    for t in ts:
        if cur and t["v"] - cur[-1]["v"] > th * 0.55:
            rows.append(cur)
            cur = []
        cur.append(t)
    if cur:
        rows.append(cur)
    return [t for r in rows for t in sorted(r, key=lambda t: t["u"])]


def seq_round(det: list, gone: int = 3, win: int = 2) -> dict:
    """강 안 순번 방식. 자리마다 프레임별 장수 c_f 를 앞뒤 [win] 프레임 최댓값으로 다듬은 n_f(손 가림은 장수를 줄이기만 하므로)를 쓴다.
    - 버림: n 이 k → k+1 이 된 첫 프레임(그 패가 처음 보인 시각).
    - 울어 감: n 이 줄고 [gone] 프레임 넘게 다시 안 늘어남 → 마지막 순번의 패.
    - 패: 그 순번이 보인 프레임(c_f == n_f 인 온전한 프레임만)의 read_small 확신도 합 투표."""
    hd = float(np.median([d["dev"][2] for d in det]))
    out = {}
    for s in SIDES:
        seqs = [order_tiles([t for t in d["tiles"] if t["side"] == s], hd) for d in det]
        c = [len(q) for q in seqs]
        F = len(c)
        n = [max(c[max(0, i - win):i + win + 1]) for i in range(F)]
        # 다듬은 장수가 줄었다 늘었다 하는 것(가림 + 헛 검출)을 단조에 가깝게: 오른쪽에서 본 최솟값과 왼쪽 최댓값 사이 중앙
        events, slots = [], []  # slots[i] = {"votes":{}, "first":f, "taken_at":f|None}
        k = 0
        f = 0
        while f < F:
            if n[f] > k:
                for j in range(k, n[f]):
                    slots.append({"votes": {}, "first": f, "taken": None})
                    events.append(("discard", f, j))
                k = n[f]
            elif n[f] < k:
                # 다시 k 로 돌아오나?
                back = any(n[g] >= k for g in range(f, min(F, f + gone + 1)))
                if not back:
                    for j in range(k - 1, n[f] - 1, -1):
                        slots[j]["taken"] = f
                        events.append(("taken", f, j))
                    k = n[f]
            f += 1
        # 투표: 온전한 프레임에서 그때 살아 있는 슬롯 수와 장수가 같을 때만
        for f in range(F):
            alive = [i for i, sl in enumerate(slots) if sl["first"] <= f and (sl["taken"] is None or sl["taken"] > f)]
            if len(alive) != c[f] or c[f] != n[f]:
                continue
            for i, t in zip(alive, seqs[f]):
                v = slots[i]["votes"]
                v[t["t"]] = v.get(t["t"], 0) + t["c"]
        rows = []
        for i, sl in enumerate(slots):
            v = sl["votes"]
            tile = max(v, key=v.get) if v else "?"
            rows.append({"i": i + 1, "tile": tile, "share": round(v[tile] / sum(v.values()), 2) if v else 0,
                         "first_at": det[sl["first"]]["at"][11:19],
                         "taken_at": det[sl["taken"]]["at"][11:19] if sl["taken"] is not None else None,
                         "nvotes": round(sum(v.values()), 1)})
        out[s] = {"slots": rows, "counts": c}
    return out


def side_of_seat(seat: int, bottom_seat: int) -> str:
    return SIDES[(seat - bottom_seat) % 4]


def slot_round(det: list, streak_need: int = 2, min_new: int = 1, dealer_side: str | None = None, flip: bool = False) -> dict:
    """강 칸(슬롯) 방식. 칸마다 마지막 위치를 기억하고 프레임마다 위치로 잇는다(강을 통째로 밀어도 따라가게 먼저 평균 이동량을 뺀다).
    - 새 패: 어느 칸에도 안 붙는 패 → 새 칸(끝에 붙임). [min_new] 프레임 이상 보여야.
    - 울어 감: **마지막 칸만** 안 보이고 나머지 칸은 다 보이는 프레임이 [streak_need] 번 → 그 패를 가져감. 다른 칸도 안 보이면 가림이라 건너뜀.
      (seq_round 는 장수만 봐서, 울어 간 자리에 다음 패가 놓이면 같은 칸으로 이어 버렸다 — R3a 위 1s.)
    - 패: 이어진 프레임의 read_small 확신도 합 투표."""
    hd = float(np.median([d["dev"][2] for d in det]))
    tol = hd * 0.2
    out = {}
    # 선의 첫 버림 전 프레임은 패 나누는 중 → 다른 자리 새 패는 안 받는다(R4 15:40:03 오른쪽 1s). 선 자리에서 처음 2프레임 이어 보인 프레임.
    start = 0
    if dealer_side:
        start = len(det)
        for f in range(len(det) - 1):
            if any(t["side"] == dealer_side for t in det[f]["tiles"]) and any(t["side"] == dealer_side for t in det[f + 1]["tiles"]):
                start = f
                break
    for s in SIDES:
        slots: list[dict] = []
        pend: list[dict] = []
        for f, d in enumerate(det):
            if f < start:
                continue
            T = [t for t in d["tiles"] if t["side"] == s]
            alive = [sl for sl in slots if sl["taken"] is None]
            # 이동량: (0,0) 과 모든 (패 − 칸) 차이를 후보로, 그만큼 옮겼을 때 tol 안에 붙는 칸 수(같은 패로 읽힌 것은 +0.5)가
            # 가장 많은 것. 강을 1.5장 밀어도(R3a 아래 f0040→f0044) 따라간다. 같으면 작은 이동.
            def score(du, dv):
                sc = 0.0
                for sl in alive:
                    for t in T:
                        if ((t["u"] - du - sl["u"]) ** 2 + (t["v"] - dv - sl["v"]) ** 2) ** 0.5 < tol:
                            sc += 1 + (0.5 if t["t"] in sl["votes"] else 0)
                            break
                return sc
            cands = [(0.0, 0.0)] + [(t["u"] - sl["u"], t["v"] - sl["v"]) for sl in alive for t in T]
            ou, ov = max(cands, key=lambda c: (score(*c), -abs(c[0]) - abs(c[1])))
            pairs = sorted(((((t["u"] - ou - sl["u"]) ** 2 + (t["v"] - ov - sl["v"]) ** 2) ** 0.5, i, j)
                            for i, sl in enumerate(alive) for j, t in enumerate(T)))
            ms, mt = {}, {}
            for dist, i, j in pairs:
                if dist > tol or i in ms or j in mt:
                    continue
                ms[i], mt[j] = j, i
            for i, j in list(ms.items()):
                sl, t = alive[i], T[j]
                # 같은 자리 바뀜: 마지막 칸이 확실히 A 였는데 확실한 B 로 2프레임 연속 읽힘 → A 는 울어 갔고 그 자리에 다음 패가 놓였다
                # (R4 아래 白 → 發: 칸이 비는 프레임이 없었다).
                if flip and i == len(alive) - 1 and sl["votes"]:
                    a = max(sl["votes"], key=sl["votes"].get)
                    # A 는 한 번이라도 0.9 넘게 읽혔어야(낮은 확신 표가 쌓인 것은 아님 — R3a 왼쪽 4p 를 1s 0.3~0.4 로 여러 번)
                    if sl.get("best", {}).get(a, 0) >= 0.9 and t["t"] != a and t["c"] >= 0.9:
                        if sl.get("flip_to") == t["t"]:
                            sl["taken"] = sl["flip_from"]
                            slots.append({"u": t["u"], "v": t["v"], "first": sl["flip_from"], "last": f, "taken": None, "streak": 0,
                                          "votes": {t["t"]: t["c"] + sl["flip_c"]}, "n": 2})
                            continue
                        sl["flip_to"], sl["flip_from"], sl["flip_c"] = t["t"], f, t["c"]
                        sl["u"], sl["v"], sl["last"] = t["u"], t["v"], f
                        continue
                    sl.pop("flip_to", None)
                sl["u"], sl["v"], sl["last"] = t["u"], t["v"], f
                sl["votes"][t["t"]] = sl["votes"].get(t["t"], 0) + t["c"]
                sl.setdefault("best", {})[t["t"]] = max(sl.get("best", {}).get(t["t"], 0), t["c"])
                sl["n"] += 1
            # 마지막 칸만 빠짐?
            if alive:
                missing = [i for i in range(len(alive)) if i not in ms]
                if missing == [len(alive) - 1]:
                    sl = alive[-1]
                    sl["streak"] += 1
                    if sl["streak"] == 1:
                        sl["miss_from"] = f
                    if sl["streak"] >= streak_need:
                        sl["taken"] = sl["miss_from"]
                elif not missing:
                    alive[-1]["streak"] = 0
            # 새 패 후보: 안 붙은 패(기존 후보와 이어 보고 [min_new] 프레임이면 칸으로)
            new_pend = []
            for j, t in enumerate(T):
                if j in mt:
                    continue
                # 혼자 옮겨진 패: 지금 안 보이는(마지막 아닌) 칸 중 같은 패로 가장 많이 읽힌 칸이 있으면 그 칸을 옮긴다(R3a 아래 8s).
                lost = [alive[i] for i in range(len(alive) - 1) if i not in ms and alive[i]["votes"]
                        and max(alive[i]["votes"], key=alive[i]["votes"].get) == t["t"]]
                if lost:
                    sl = lost[0]
                    sl["u"], sl["v"], sl["last"] = t["u"], t["v"], f
                    sl["votes"][t["t"]] += t["c"]
                    sl["n"] += 1
                    ms[alive.index(sl)] = j
                    continue
                p = next((p for p in pend if ((p["u"] - t["u"]) ** 2 + (p["v"] - t["v"]) ** 2) ** 0.5 < tol), None)
                if p is None:
                    p = {"u": t["u"], "v": t["v"], "first": f, "seen": 0, "votes": {}}
                p["u"], p["v"] = t["u"], t["v"]
                p["seen"] += 1
                p["votes"][t["t"]] = p["votes"].get(t["t"], 0) + t["c"]
                p.setdefault("best", {})[t["t"]] = max(p.get("best", {}).get(t["t"], 0), t["c"])
                if p["seen"] >= min_new:
                    slots.append({"u": p["u"], "v": p["v"], "first": p["first"], "last": f, "taken": None, "streak": 0,
                                  "votes": p["votes"], "best": p["best"], "n": p["seen"]})
                else:
                    new_pend.append(p)
            pend = new_pend
        # 순서: 남은 칸은 강 위치(줄·칸)로, 울어 간 칸은 처음 보인 시각으로 그 앞뒤 사이에 끼운다.
        alive = order_tiles([sl for sl in slots if sl["taken"] is None], hd)
        ordered = list(alive)
        for sl in sorted((sl for sl in slots if sl["taken"] is not None), key=lambda s: s["first"]):
            k = 0
            for i, a in enumerate(ordered):
                if a["first"] <= sl["first"]:
                    k = i + 1
            ordered.insert(k, sl)
        # 한 자리의 버림은 강 순서 = 시각 순서다. 칸이 엇갈려 이어지면(R2 아래: 비스듬히 놓은 9p 를 고쳐 놓는 사이 白 칸과 바뀜)
        # 칸의 첫 시각이 뒤바뀌므로, 처음 보인 시각들을 정렬해 강 순서대로 다시 붙인다.
        firsts = sorted(sl["first"] for sl in ordered)
        rows = []
        for i, sl in enumerate(ordered):
            v = sl["votes"]
            tile = max(v, key=v.get)
            rows.append({"i": i + 1, "tile": tile, "share": round(v[tile] / sum(v.values()), 2), "n": sl["n"],
                         "first_at": det[firsts[i]]["at"][11:19],
                         "taken_at": det[sl["taken"]]["at"][11:19] if sl["taken"] is not None else None})
        out[s] = {"slots": rows, "counts": [sum(1 for t in d["tiles"] if t["side"] == s) for d in det]}
    return out


NEXT = {"bottom": "right", "right": "top", "top": "left", "left": "bottom"}  # 반시계 차례(위에서 본 화면)


def interleave(seq: dict) -> list:
    """자리별 버림·울어 감을 한 줄로. 같은 프레임에서 여럿이면 차례(반시계)로 잇는다."""
    ev = []
    for s, v in seq.items():
        for r in v["slots"]:
            ev.append((r["first_at"], "discard", s, r))
            if r["taken_at"]:
                ev.append((r["taken_at"], "taken", s, r))
    ev.sort(key=lambda e: (e[0], e[1] != "discard"))
    out, last = [], None
    i = 0
    while i < len(ev):
        j = i
        while j < len(ev) and ev[j][0] == ev[i][0]:
            j += 1
        group = ev[i:j]
        ds = [e for e in group if e[1] == "discard"]
        if last is not None and len(ds) > 1:
            ordr, cur = [], last
            pool = list(ds)
            for _ in range(4):
                cur = NEXT[cur]
                ordr += [e for e in pool if e[2] == cur]
            ds = ordr
        out += ds + [e for e in group if e[1] != "discard"]
        if ds:
            last = ds[-1][2]
        i = j
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("track", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--name", required=True)
    ap.add_argument("--t0")
    ap.add_argument("--t1")
    ap.add_argument("--overlay", default="")
    ap.add_argument("--redetect", action="store_true")
    ap.add_argument("--mode", default="slot", choices=["slot", "seq"])
    ap.add_argument("--min-new", type=int, default=1)
    ap.add_argument("--streak", type=int, default=2)
    ap.add_argument("--dealer-side", default=None, help="선 자리(이미지 기준). 주면 선의 첫 버림 전 프레임을 버린다")
    ap.add_argument("--flip", action="store_true", help="마지막 칸이 다른 패로 바뀌면 울어 감으로")
    ap.add_argument("--tag", default="", help="결과 파일 이름 꼬리")
    a = ap.parse_args()
    out = a.out / a.name
    p = out / "det.json"
    if a.redetect or not p.exists():
        reader = LocalReader(threads=4)
        detect_round(reader, a.track, a.t0, a.t1, out)
    det = json.loads(p.read_text(encoding="utf-8"))
    if a.overlay:
        overlay(a.track, det, out, a.overlay.split(","))
    sq = seq_round(det) if a.mode == "seq" else slot_round(det, a.streak, a.min_new, a.dealer_side, a.flip)
    a.mode += a.tag
    (out / f"{a.mode}.json").write_text(json.dumps(sq, ensure_ascii=False, indent=1), encoding="utf-8")
    for s, v in sq.items():
        print(f"{s:6s}", " ".join(f"{r['tile']}{'*' if r['taken_at'] else ''}" for r in v["slots"]), "| 장수", "".join(str(min(9, x)) for x in v["counts"]))
    lines = []
    for at, kind, s, r in interleave(sq):
        lines.append(f"{at} {s:6s} {'버림' if kind == 'discard' else '울어 감'} {r['tile']}" + (f" ({r['share']:.2f})" if kind == "discard" else ""))
    (out / f"paifu_{a.mode}.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
