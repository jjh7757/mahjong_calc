"""자리를 손패 칸·모서리 칸(격자 선, 사용자 제안 2026-10-28)으로 나눠 틀 잡기: 지금 규칙(한 장으로 추측)과 같은 사진으로 비교.

  python -I -X utf8 experiments/speed/seat_zones.py frames                    (API 없이 틀만)
  python -I -X utf8 experiments/speed/seat_zones.py read --runs 5 --gap 20    (틀 잡힌 것을 조각 그림으로 Gemini 에, 서버와 같은 문구)

나눈 방식:
  1. 자리 크롭을 격자 handCell 경계(장면 격자에서 계산한 폭 비율)로 손패 쪽·모서리 쪽으로 나눈다.
  2. 손패 쪽은 서버와 같은 모자이크 검출, 모서리 쪽은 따로 한 번 검출(작게 잘라 패가 커짐). 상자는 원래 좌표로 모은다.
  3. 손패 = 손패 쪽에서 직선(RANSAC)에 놓인 상자들, x 순. 마지막 한 장이 띄어 있으면 떨어진 패.
     울기 = 나머지(모서리 쪽 + 손패 줄에서 벗어난 상자)를 틈으로 묶은 3·4장(6 → 3+3, 8 → 4+4).
  4. 장수 검사: 손패 + 떨어진 패 + 울기 × 3 = 13·14, 무늬 검사(safe_ok). 못 넘으면 통째 읽기(지금처럼).
울기 합성(손패가 울기로 줄어든 자리): 지금 규칙으로 틀이 잡히는 C·D 원본에서 손패 끝 3m 장을 펠트색으로 지우고,
그 패 그림을 3장씩 m 묶음으로 **모서리 쪽 탁자 가장자리 줄**(D 는 원래 울기와 같은 높이, C 는 손패 줄보다 패 0.9개 아래)에
오른쪽 끝부터 왼쪽으로 놓는다. 모서리 칸에 다 안 들어가면 손패 쪽 아래로 이어진다(실제 탁자에서도 그렇다).
"""
from __future__ import annotations

import argparse
import io
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import bench as b  # noqa: E402
import seat_prior as sp  # noqa: E402

sys.path.insert(0, "C:/Users/jjh7757/dev/mahjong-recognizer")
from app import observe as ob  # noqa: E402
from app import river as rv  # noqa: E402
from app import seat  # noqa: E402

# 격자 handCell 이 자리 크롭(그 사람 방향으로 세운 것)에서 차지하는 폭 비율. 장면 격자(read_grid_timing_test):
# B 오른쪽 (y2−y1)/y2, C 왼쪽 (y2−y1)/(1000−y1), D 아래 (x2−x1)/(1000−x1).
HAND_FRAC = {"B": (727 - 137) / 727, "C": (717 - 142) / (1000 - 142), "D": (745 - 280) / (1000 - 280)}
MARGIN = 0.03  # 경계 양쪽으로 자리 폭의 3% 겹쳐 검출(선을 넘은 패)
SPLIT_MELD = {6: (3, 3), 8: (4, 4)}
CORNER_K = int(__import__("os").environ.get("CORNER_K", 2))  # 모서리 쪽 모자이크 토막 수(CORNER_DET=crop 일 때)
CORNER_DET = __import__("os").environ.get("CORNER_DET", "full")
USE_LINE = __import__("os").environ.get("USE_LINE", "1") == "1"
TABLE_ONLY = __import__("os").environ.get("TABLE_ONLY", "1") == "1"  # 테이블 밖(펠트에서 패 TABLE_REACH 개 넘게) 상자 버림
TABLE_REACH = 1.3
_RGB: np.ndarray | None = None  # structure_zones 가 볼 지금 사진(실험용 전역)  # 고정 카메라 사전 손패 줄(울기 합성에만 있음)  # full: 자리 전체 모자이크 상자 / crop: 모서리만 잘라 검출


def detect_zones(rgb: np.ndarray, frac: float, corner_det: str | None = None) -> tuple[list[seat.Box], int]:
    """손패 쪽(모자이크) + 모서리 쪽(한 번) 검출 → 원래 좌표 상자(앞면만, 겹침 제거), 경계 x."""
    H, W = rgb.shape[:2]
    split = int(W * frac)
    m = int(W * MARGIN)
    det = sp.detector()
    hand_rgb = rgb[:, : split + m]
    hw = rv.white_mask(hand_rgb)
    got = seat.mosaic(det, hand_rgb, hw)
    boxes = [x for x in (got[0] if got else []) if seat.ink(hand_rgb, x) >= seat.INK_MIN]
    # 모서리 쪽: 자리 전체 모자이크(서버 지금 방식)의 상자 중 경계 오른쪽 것. 모서리만 잘라 따로 검출하면
    # (한 번이든 모자이크든) 상자가 패보다 1.5~2배 커지고 서로 겹쳐 울기 모양 검사에 걸렸다(D k12·k16).
    if (corner_det or CORNER_DET) == "full":
        allw = rv.white_mask(rgb)
        got_f = seat.mosaic(det, rgb, allw)
        for bx in (got_f[0] if got_f else []):
            if bx[0] + bx[2] / 2 >= split and seat.ink(rgb, bx) >= seat.INK_MIN:
                boxes.append(bx)
    else:
        x0 = max(0, split - m)
        corner = np.ascontiguousarray(rgb[:, x0:])
        cw = rv.white_mask(corner)
        got_c = seat.mosaic(det, corner, cw, k=CORNER_K)
        for bx in (got_c[0] if got_c else []):
            nb = (bx[0] + x0, bx[1], bx[2], bx[3])
            if seat.ink(rgb, nb) >= seat.INK_MIN:
                boxes.append(nb)
    white = rv.white_mask(rgb)
    return rv.dedupe(rv.keep_faces(boxes, white)), split


def felt_mask(rgb: np.ndarray) -> np.ndarray:
    """펠트(초록~파랑, 채도 있는 면) 마스크. 앱의 findFeltQuad(rectify.dart)와 같은 생각 — 탁자 안쪽."""
    hsv = np.asarray(Image.fromarray(rgb).convert("HSV")).astype(int)
    h, sat, v = hsv[..., 0] * 360 // 255, hsv[..., 1], hsv[..., 2]
    return (h >= 70) & (h <= 250) & (sat > 60) & (v > 40)


def on_table(faces: list[seat.Box], rgb: np.ndarray, reach: float) -> list[seat.Box]:
    """테이블 위(펠트 + 흰 테두리)에 있는 상자만: 상자 가운데에서 [reach] px 안에 펠트가 있어야 한다.
    울기는 펠트 밖 흰 테두리에도 놓이므로(사용자 사진의 發 퐁) 펠트 끝이 아니라 패 1.3개 거리까지 둔다."""
    m = felt_mask(rgb)
    H, W = m.shape
    out = []
    for f in faces:
        cx, cy = int(f[0] + f[2] / 2), int(f[1] + f[3] / 2)
        r = int(reach)
        if m[max(0, cy - r):min(H, cy + r), max(0, cx - r):min(W, cx + r)].any():
            out.append(f)
    return out


def structure_zones(faces: list[seat.Box], split: int, W: int,
                    line: tuple[float, float] | None = None) -> seat.SeatFrame | None:
    """[line] 은 고정 카메라에서 예전 판에 알아 둔 손패 줄(가운데 y = a·x + c). 없으면 손패 쪽 상자로 직선을 맞춘다 —
    손패가 울기로 몇 장 안 남으면 울기 줄이 더 길어 그쪽을 손패로 잡는다."""
    if not faces:
        return None
    up = [x for x in faces if x[3] > x[2]] or faces
    tw = statistics.median(x[2] for x in up)
    th = statistics.median(x[3] for x in up)
    if TABLE_ONLY and _RGB is not None:
        faces = on_table(faces, _RGB, TABLE_REACH * th)
    hand_side = [f for f in faces if f[0] + f[2] / 2 < split + MARGIN * W]
    if line is not None:
        mk, kk = line
    else:
        fit = sp.fit_line(hand_side)
        if fit is None:
            return None
        mk, kk, _ = fit
    on = sorted([f for f in hand_side if abs(f[1] + f[3] / 2 - (mk * (f[0] + f[2] / 2) + kk)) < 0.5 * th
                 and f[3] > f[2]], key=lambda x: x[0])
    if not on:
        return None
    # 손패 줄: 왼쪽부터 틈 0.45 패 안으로 이어진 것. 그 뒤 한 장이 패 2.5 안에 있으면 떨어진 패.
    runs = [[on[0]]]
    for f in on[1:]:
        if f[0] - (runs[-1][-1][0] + runs[-1][-1][2]) > 0.45 * tw:
            runs.append([f])
        else:
            runs[-1].append(f)
    hand = max(runs, key=len)
    i = runs.index(hand)
    sep = None
    after = runs[i + 1:]
    hx1 = hand[-1][0] + hand[-1][2]
    if after and len(after[0]) == 1 and after[0][0][0] - hx1 < seat.SEP_DIST * tw:
        sep = after[0][0]
    used = set(map(tuple, hand)) | ({tuple(sep)} if sep else set())
    # 울기: 손패·떨어진 패가 아닌 나머지 중 손패 줄 왼쪽 시작보다 오른쪽에 있는 것.
    rest = [f for f in faces if tuple(f) not in used and f[0] > hand[0][0]]
    loose = [f for f in faces if tuple(f) not in used and f not in rest]
    melds = []
    for g in seat.cluster(rest, tw * 0.35, th * 0.5):
        g = sorted(g, key=lambda x: x[0])
        n = len(g)
        if n in (3, 4):
            melds.append(g)
        elif n in SPLIT_MELD:
            a, _ = SPLIT_MELD[n]
            melds += [g[:a], g[a:]]
        else:
            loose.extend(g)
    melds.sort(key=lambda m: m[0][0])
    return seat.SeatFrame(sorted(hand, key=lambda x: x[0]), sep, melds, loose, tw, th, len(faces))


# ---------------------------------------------------------------- 울기 합성(모서리 쪽 가장자리 줄)

def felt_fill(out: np.ndarray, rgb: np.ndarray, box: seat.Box) -> None:
    x, y, w, h = box
    top = max(0, y - int(0.5 * h))
    sample = rgb[top:max(top + 1, y - 2), x:x + w].reshape(-1, 3)
    color = np.median(sample, axis=0).astype(np.uint8)
    # 패 옆면·그림자까지: 아래로 0.3, 옆으로 0.08 넓힘.
    x0, x1 = max(0, x - int(0.08 * w)), min(out.shape[1], x + int(1.08 * w))
    out[y:min(out.shape[0], y + int(1.3 * h)), x0:x1] = color


def with_corner_melds(rgb: np.ndarray, fr: seat.SeatFrame, m: int) -> np.ndarray | None:
    hand = sorted(fr.hand, key=lambda x: x[0])
    if len(hand) - 3 * m < 1:
        return None
    keep, moved = hand[: len(hand) - 3 * m], hand[len(hand) - 3 * m:]
    out = rgb.copy()
    tw, th = fr.tw, fr.th
    patches = [rgb[y:y + h, x:x + w].copy() for x, y, w, h in moved]
    for bx in moved:
        felt_fill(out, rgb, bx)
    if fr.melds:  # 원래 울기 왼쪽으로 같은 높이에
        base = min(fr.melds, key=lambda g: g[0][0])
        y_base = int(statistics.median(x[1] + x[3] for x in base))
        cur = min(x[0] for x in base) - int(0.4 * tw)
    else:  # 손패 줄 끝 높이에서 패 0.9 개 아래(탁자 가장자리 쪽), 오른쪽 끝부터
        y_base = int(statistics.median(x[1] + x[3] for x in keep) + 0.9 * th)
        cur = rgb.shape[1] - int(0.3 * tw)
    for g in range(m):
        for k in reversed(range(3)):
            (x, y, w, h), patch = moved[3 * g + k], patches[3 * g + k]
            cur -= w + 2
            top = y_base - h
            if cur < 0 or top < 0 or top + h > out.shape[0]:
                return None
            out[top:top + h, cur:cur + w] = patch
        cur -= int(0.4 * tw)
    if cur < keep[-1][0] + keep[-1][2]:
        return None  # 울기가 손패 줄 아래까지 너무 와서 손패와 섞임 — 이 합성은 쓰지 않는다
    return out


def cases() -> list[dict]:
    out = []
    for s in "BCD":
        truth = b.TRUTH[s]
        for p in b.PHOTOS[s]:
            rgb = np.asarray(Image.open(b.G / s / p / f"{sp.SEATS[s]}.jpg").convert("RGB"))
            out.append({"name": f"{s} {p}", "scene": s, "rgb": rgb, "hand": len(truth[1].split()),
                        "melds": len(truth[2]), "hand_tiles": truth[1].split(), "meld_tiles": [m.split() for m in truth[2]]})
    for base in [c for c in out if c["scene"] in "CD"]:
        fr = seat.structure(base["rgb"], sp.faces_of(base["rgb"]))
        if fr is None or not seat.valid(fr):
            continue
        xs = np.array([x[0] + x[2] / 2 for x in fr.hand])
        ys = np.array([x[1] + x[3] / 2 for x in fr.hand])
        line = tuple(float(v) for v in np.polyfit(xs, ys, 1))
        for m in range(1, 5):
            if base["melds"] + m > 4:
                break
            img = with_corner_melds(base["rgb"], fr, m)
            if img is None:
                print(f"  {base['name']} 울기 +{m}: 자리 모자람·겹침, 건너뜀")
                continue
            n = base["hand"] - 3 * m
            moved = base["hand_tiles"][n:]
            out.append({"name": f"{base['name']} 울기+{m}", "scene": base["scene"], "rgb": img, "hand": n,
                        "melds": base["melds"] + m, "hand_tiles": base["hand_tiles"][:n],
                        "meld_tiles": [moved[3 * g:3 * g + 3] for g in range(m)][::-1] + base["meld_tiles"],
                        "synthetic": True, "line": line})
    return out


def safe_zones(fr: seat.SeatFrame, rgb: np.ndarray, line: tuple[float, float] | None) -> bool:
    """서버 safe_ok 와 같되, 손패가 4장 미만(울기 3~4번)이고 사전 손패 줄이 있으면 손패 줄 모양 검사(4장 이상일 때만
    뜻이 있는 직선·간격)를 사전 줄로 대신한다: 손패 패마다 가운데가 그 줄에서 패 높이 0.35 안, 크기는 울기 패와 비슷."""
    if len(fr.hand) >= 4 or line is None:
        return seat.safe_ok(fr, rgb)
    a, c = line
    th = fr.th
    if any(abs(x[1] + x[3] / 2 - (a * (x[0] + x[2] / 2) + c)) > 0.35 * th for x in fr.hand):
        return False
    if any(not 0.6 * th <= x[3] <= 1.4 * th for x in fr.hand):
        return False
    for m in fr.melds:
        for p, q in zip(m, m[1:]):
            if p[0] + p[2] - q[0] > 0.3 * min(p[2], q[2]):
                return False
        if any(not 0.5 * th <= x[3] <= 1.3 * th for x in m):
            return False
    return all(seat.ink(rgb, x) >= seat.INK_MIN for kind, x in fr.pieces() if kind != "loose")


def judge(fr: seat.SeatFrame | None, rgb: np.ndarray, c: dict, line=None) -> dict:
    if fr is None:
        return {"ok": False, "why": "구조 없음"}
    v, s = seat.valid(fr), safe_zones(fr, rgb, line)
    right = len(fr.hand) == c["hand"] and fr.separate is None and len(fr.melds) == c["melds"]
    return {"ok": v and s and right, "valid": v, "safe": s, "right": right, "sum": fr.summary()}


def frames(dump: Path | None = None) -> list[dict]:
    rows = []
    for c in cases():
        rgb = c["rgb"]
        t0 = time.perf_counter()
        now_fr = seat.structure(rgb, sp.faces_of(rgb))
        t_now = time.perf_counter() - t0
        t0 = time.perf_counter()
        # 모서리 검출 두 방식(자리 전체 모자이크 / 모서리만 모자이크)을 차례로 — 검사(장수·모양·무늬)를 넘는 첫 것.
        # 고정 카메라의 사전 손패 줄(c["line"], 울기 합성은 합성 전 원본의 손패 줄)이 있으면 그것으로.
        z_fr, faces, split = None, [], 0
        global _RGB
        _RGB = rgb
        for how in ("full", "crop"):
            faces, split = detect_zones(rgb, HAND_FRAC[c["scene"]], how)
            ln = c.get("line") if USE_LINE else None
            z_fr = structure_zones(faces, split, rgb.shape[1], ln)
            if z_fr is not None and seat.valid(z_fr) and safe_zones(z_fr, rgb, ln):
                break
        t_z = time.perf_counter() - t0
        now, z = judge(now_fr, rgb, c), judge(z_fr, rgb, c, c.get("line") if USE_LINE else None)
        rows.append({"name": c["name"], "now": now, "zones": z, "t_now": t_now, "t_zones": t_z, "case": c, "fr": z_fr})
        print(f"{c['name']:18s} 정답 손패 {c['hand']:2d}·울기 {c['melds']} | 지금 {'OK' if now['ok'] else 'X '} "
              f"{now.get('sum', now.get('why'))} | 나눔 {'OK' if z['ok'] else 'X '} {z.get('sum', z.get('why'))}", flush=True)
        if dump:
            im = Image.fromarray(rgb).copy()
            from PIL import ImageDraw
            d = ImageDraw.Draw(im)
            d.line([split, 0, split, im.height], fill=(0, 160, 255), width=6)
            for x, y, w, h in faces:
                d.rectangle([x, y, x + w, y + h], outline=(255, 0, 0), width=4)
            im.thumbnail((1400, 1400))
            im.save(dump / f"zones_{c['name'].replace(' ', '_').replace('+', 'p')}.png")
    for k, lab in (("now", "지금 규칙"), ("zones", "나눈 방식")):
        orig = [r for r in rows if "울기+" not in r["name"]]
        syn = [r for r in rows if "울기+" in r["name"]]
        bad = [r for r in rows if r[k].get("valid") and r[k].get("safe") and not r[k].get("right")]
        print(f"{lab}: 원본 {sum(r[k]['ok'] for r in orig)}/{len(orig)} · 울기 합성 {sum(r[k]['ok'] for r in syn)}/{len(syn)}"
              f" · 검사 통과했는데 틀린 구조 {len(bad)}")
    print(f"검출·틀 시간(노트북) 지금 {statistics.median(r['t_now'] for r in rows):.2f}초 · 나눔 "
          f"{statistics.median(r['t_zones'] for r in rows):.2f}초")
    (b.OUT / "seat_zones_frames.json").write_text(json.dumps(
        [{k: v for k, v in r.items() if k not in ("case", "fr")} for r in rows], ensure_ascii=False, indent=0),
        encoding="utf-8")
    return rows


# ---------------------------------------------------------------- Gemini 조각 읽기

def read(runs: int, gap: float) -> None:
    """나눈 방식으로 틀이 잡힌(검사 통과) 사진만, 서버 /v2/seat 조각 읽기와 같은 요청(조각 그림 + 참고표, ULTRA_HIGH,
    3번 동시 + 만장일치)으로 읽어 손패·울기 패 종류까지 정답인지. 서버 GeminiRecognizer 를 그대로 쓴다(키는 부트캠프 .env)."""
    import os

    from dotenv import load_dotenv

    from app.recognizer import REF_SHEET, GeminiRecognizer

    load_dotenv("C:/Users/jjh7757/Downloads/부트캠프/.env")
    r = GeminiRecognizer(os.environ["GEMINI_API_KEY"], thinking="low", seat_reads=3)
    rows = [x for x in frames() if x["zones"]["ok"]]
    print(f"\n틀 잡힌 {len(rows)}장 × {runs}회 읽기")
    out = []

    def one(x):
        fr, rgb, c = x["fr"], x["case"]["rgb"], x["case"]
        t0 = time.perf_counter()
        sheet = seat.sheet(rgb, fr)
        n = len(fr.pieces())
        calls = list(ThreadPoolExecutor(3).map(
            lambda _: r.call(sheet, ob.piece_prompt(n), ob.piece_schema(n), media_resolution="MEDIA_RESOLUTION_ULTRA_HIGH",
                             extra_images=[(REF_SHEET.read_bytes(), None)]),
            range(3)))
        reads = [seat.to_seat(fr, ob.normalize_pieces(cl.data, n)) for cl in calls]
        secs = time.perf_counter() - t0
        if any(rd is None for rd in reads):
            return {"name": c["name"], "s": secs, "ok": False, "why": "뒷면·빈 칸"}
        data = ob.agree_seats(reads)
        hand = [t["tile"] for t in data["tiles"]]
        melds = sorted(" ".join(sorted(m["tiles"])) for m in data["melds"])
        ok = sorted(hand) == sorted(c["hand_tiles"]) and melds == sorted(" ".join(sorted(m)) for m in c["meld_tiles"])
        return {"name": c["name"], "s": round(secs, 2), "ok": ok, "unanimous": data["agreement"]["unanimous"],
                "in": sum(cl.input_tokens for cl in calls)}

    for i in range(runs):
        for x in rows:
            t0 = time.time()
            res = one(x) | {"run": i}
            out.append(res)
            print(f"  {res['name']:18s} #{i} {res['s']:5.1f}s {'OK' if res['ok'] else 'X'}"
                  f"{'' if res.get('unanimous', True) else ' (엇갈림)'}", flush=True)
            time.sleep(max(0.0, gap - (time.time() - t0)))
    t = sorted(x["s"] for x in out)
    print(f"정답 {sum(x['ok'] for x in out)}/{len(out)} · 만장일치 {sum(x.get('unanimous', False) for x in out)} · "
          f"중앙 {statistics.median(t):.1f} / p90 {t[int(.9 * (len(t) - 1))]:.1f} / 최대 {t[-1]:.1f}초")
    (b.OUT / "seat_zones_read.json").write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["frames", "read"])
    ap.add_argument("--dump", default="", help="frames: 상자·경계 그림을 저장할 폴더")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--gap", type=float, default=20.0, help="read: 사진 사이 간격(초) — 3호출/20초 = 분당 9")
    a = ap.parse_args()
    if a.cmd == "frames":
        frames(Path(a.dump) if a.dump else None)
    else:
        read(a.runs, a.gap)
