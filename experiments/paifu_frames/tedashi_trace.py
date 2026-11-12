"""데다시 흔적(손패 줄 빈칸·떨어진 쯔모 패)이 3초 간격 프레임에서 보이는 비율 세기.

  python tedashi_trace.py sheets R2|R3a|R4|all   대조표 + 사건 목록(events_<판>.json)
  python tedashi_trace.py probe  R2|R3a|R4|all   자르기 상자를 프레임 위에 그린 확인용 그림
  python tedashi_trace.py tally                   labels_<판>.json 을 모아 표 + summary.json

사건 = results/<판>/slot_v2.json 의 버림 하나(first_at = 강에서 처음 잡힌 프레임 = T).
대조표 = 그 자리 손패 띠를 T-2, T-1, T, T+1 네 프레임에서 같은 좌표로 잘라
줄이 가로(탁자 테두리 = 아래, 강 = 위)가 되게 돌리고 3배 키워 세로로 쌓은 것.
cv2 만 쓴다(서버 저장소 import 없음).
"""
import json
import re
import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "results" / "tedashi_trace"
CAP = HERE.parent / "visit_20261107" / "captures"
TRACKS = {"R2": "20261107_153128_track", "R3a": "20261107_153423_track",
          "R4": "20261107_154029_track"}
SIDES = ["bottom", "right", "top", "left"]
SCALE = 3

# 자리별 손패 띠 자르기 (x0, y0, x1, y1), 1020x764 프레임 좌표.
# 프레임을 직접 열어 손패 줄 위치를 보고 정함. 줄 양끝 바깥 패 3장(60px) 이상,
# 줄에서 탁자 테두리까지, 강 쪽으로 패 2장(40px) 이상을 넣는다.
CROPS = {
    "R2": {"bottom": (340, 595, 860, 745), "top": (360, 25, 800, 165),
           "left": (222, 175, 365, 625), "right": (795, 150, 948, 640)},
    "R3a": {"bottom": (330, 585, 850, 745), "top": (360, 22, 790, 160),
            "left": (222, 185, 360, 625), "right": (795, 175, 948, 635)},
    "R4": {"bottom": (360, 600, 850, 745), "top": (340, 30, 770, 165),
           "left": (228, 160, 365, 615), "right": (800, 185, 948, 640)},
}
# 돌리기: 탁자 테두리(자기 자리 쪽)가 아래로 오게.
ROT = {"bottom": None, "top": cv2.ROTATE_180,
       "left": cv2.ROTATE_90_COUNTERCLOCKWISE, "right": cv2.ROTATE_90_CLOCKWISE}


def hms_to_s(t):
    t = t.replace(":", "")
    return int(t[0:2]) * 3600 + int(t[2:4]) * 60 + int(t[4:6])


def load_frames(game):
    """[(sec, 'HHMMSS', zip path, member)] 시각 순."""
    out = []
    for z in sorted((CAP / TRACKS[game]).glob("frames_*.zip")):
        with zipfile.ZipFile(z) as zf:
            for n in zf.namelist():
                m = re.match(r"f\d+_(\d{6})\.jpg$", n)
                if m:
                    out.append((hms_to_s(m.group(1)), m.group(1), z, n))
    out.sort()
    t = json.loads((HERE / "truth.json").read_text(encoding="utf-8"))[game]
    if t.get("t0"):  # 판 구간 밖 프레임(R3a frames_02 등)은 쓰지 않음
        a, b = hms_to_s(t["t0"]), hms_to_s(t["t1"])
        out = [f for f in out if a <= f[0] <= b]
    return out


def read_frame(z, n):
    with zipfile.ZipFile(z) as zf:
        buf = np.frombuffer(zf.read(n), np.uint8)
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def truth_by_side(game):
    t = json.loads((HERE / "truth.json").read_text(encoding="utf-8"))[game]
    seq = t["seq"]
    taken = t.get("taken", [])
    per = {s: [] for s in SIDES}
    for i, e in enumerate(seq):
        side, tile = e.split()
        star = tile.endswith("*")
        tile = tile.rstrip("*")
        after_call = False
        if i > 0 and seq[i - 1].endswith("*"):
            ps, pt = seq[i - 1].split()
            pt = pt.rstrip("*")
            for tk in taken:
                if tk["side"] == ps and tk["tile"] == pt and tk.get("by") == side:
                    after_call = True
        per[side].append({"idx": i, "tile": tile, "taken": star,
                          "after_call": after_call})
    return per


def align(truth, slots):
    """자리 하나: truth 목록과 slot 목록을 순서대로 맞춤(편집 거리)."""
    n, m = len(truth), len(slots)
    D = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        D[i][0] = i
    for j in range(m + 1):
        D[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sub = 0 if truth[i - 1]["tile"] == slots[j - 1]["tile"] else 1
            D[i][j] = min(D[i - 1][j - 1] + sub, D[i - 1][j] + 1, D[i][j - 1] + 1)
    pairs, i, j = [], n, m
    while i > 0 or j > 0:
        # 같은 비용이면 뒤쪽 slot 을 헛 버림으로(먼저 잡힌 것을 사건으로) 본다.
        if j > 0 and D[i][j] == D[i][j - 1] + 1:
            pairs.append((None, j - 1)); j -= 1; continue
        if i > 0 and j > 0:
            sub = 0 if truth[i - 1]["tile"] == slots[j - 1]["tile"] else 1
            if D[i][j] == D[i - 1][j - 1] + sub:
                pairs.append((i - 1, j - 1)); i -= 1; j -= 1; continue
        pairs.append((i - 1, None)); i -= 1
    return pairs[::-1]


def build_events(game):
    slot = json.loads((HERE / "results" / game / "slot_v2.json").read_text(encoding="utf-8"))
    tru = truth_by_side(game)
    events, missing, spurious = [], [], []
    for side in SIDES:
        sl = slot[side]["slots"]
        for ti, sj in align(tru[side], sl):
            if sj is None:
                missing.append({"side": side, "truth_tile": tru[side][ti]["tile"],
                                "truth_idx": tru[side][ti]["idx"]})
                continue
            s = sl[sj]
            if ti is None:
                spurious.append({"side": side, "tile": s["tile"], "first_at": s["first_at"]})
                continue
            t = tru[side][ti]
            if not s.get("first_at"):
                missing.append({"side": side, "truth_tile": t["tile"], "truth_idx": t["idx"],
                                "why": "first_at 없음"})
                continue
            events.append({"side": side, "tile": s["tile"], "truth_tile": t["tile"],
                           "truth_idx": t["idx"], "T": s["first_at"],
                           "taken_at": s.get("taken_at"), "after_call": t["after_call"]})
    events.sort(key=lambda e: e["truth_idx"])
    for k, e in enumerate(events, 1):
        e["event"] = k
    return events, missing, spurious


def crop(img, game, side):
    x0, y0, x1, y1 = CROPS[game][side]
    c = img[y0:y1, x0:x1]
    if ROT[side] is not None:
        c = cv2.rotate(c, ROT[side])
    return cv2.resize(c, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_CUBIC)


def sheets(game):
    frames = load_frames(game)
    secs = [f[0] for f in frames]
    events, missing, spurious = build_events(game)
    od = OUT / game
    od.mkdir(parents=True, exist_ok=True)
    cache = {}

    def get(k):
        if k not in cache:
            cache[k] = read_frame(frames[k][2], frames[k][3])
        return cache[k]

    for e in events:
        ts = hms_to_s(e["T"])
        k = min(range(len(secs)), key=lambda i: abs(secs[i] - ts))
        if secs[k] != ts:
            e["T_frame_note"] = f"T 프레임 정확히 없음, {frames[k][1]} 사용"
        e["gap_sec"] = secs[k] - secs[k - 1] if k > 0 else None
        rows = []
        x0, y0, x1, y1 = CROPS[game][e["side"]]
        w, h = x1 - x0, y1 - y0
        if e["side"] in ("left", "right"):
            w, h = h, w
        W, H = w * SCALE, h * SCALE
        for off, name in ((-2, "T-2"), (-1, "T-1"), (0, "T"), (1, "T+1")):
            kk = k + off
            bar = np.full((34, W, 3), 255, np.uint8)
            if 0 <= kk < len(frames):
                c = crop(get(kk), game, e["side"])
                dt = secs[kk] - ts
                txt = f"{name}  {frames[kk][1][:2]}:{frames[kk][1][2:4]}:{frames[kk][1][4:]}  ({dt:+d}s)"
            else:
                c = np.full((H, W, 3), 80, np.uint8)
                txt = f"{name}  no frame"
            col = (0, 0, 220) if off == 0 else (0, 0, 0)
            cv2.putText(bar, txt, (8, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.8, col, 2)
            if off == 0:
                cv2.rectangle(c, (0, 0), (W - 1, H - 1), (0, 0, 255), 6)
            rows += [bar, c]
        head = np.full((40, W, 3), 230, np.uint8)
        cv2.putText(head, f"{game} e{e['event']:03d} {e['side']} {e['tile']} T={e['T']}"
                    f"{'  AFTER CALL' if e['after_call'] else ''}  (edge=bottom, river=top)",
                    (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
        sheet = np.vstack([head] + rows)
        fn = f"e{e['event']:03d}_{e['side']}_{e['T'].replace(':', '')}.jpg"
        e["sheet"] = fn
        cv2.imwrite(str(od / fn), sheet, [cv2.IMWRITE_JPEG_QUALITY, 92])
    (OUT / f"events_{game}.json").write_text(json.dumps(
        {"game": game, "events": events, "missing": missing, "spurious": spurious},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{game}: 사건 {len(events)}, 시각 없음/빠짐 {len(missing)}, 헛 버림 {len(spurious)}")
    for x in missing:
        print("  빠짐", x)
    for x in spurious:
        print("  헛", x)


def probe(game):
    frames = load_frames(game)
    od = OUT / "_probe"
    od.mkdir(parents=True, exist_ok=True)
    for k in (len(frames) // 5, len(frames) // 2, len(frames) * 4 // 5):
        img = read_frame(frames[k][2], frames[k][3])
        for side, (x0, y0, x1, y1) in CROPS[game].items():
            cv2.rectangle(img, (x0, y0), (x1, y1), (0, 0, 255), 2)
            cv2.putText(img, side, (x0 + 4, y0 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        cv2.imwrite(str(od / f"{game}_{frames[k][1]}.jpg"), img)


VERDICTS = ["tedashi_trace", "tsumogiri_like", "none", "occluded", "unclear"]


def tally():
    summary = {"games": {}, "total": None}
    allev = []
    for game in TRACKS:
        p = OUT / f"labels_{game}.json"
        if not p.exists():
            print(f"{game}: 라벨 없음")
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        evs = d["events"] if isinstance(d, dict) else d
        for e in evs:
            e["_game"] = game
        allev += evs
        summary["games"][game] = stat(evs)
        summary["games"][game]["by_side"] = {s: stat([e for e in evs if e["side"] == s])
                                             for s in SIDES}
        if isinstance(d, dict):
            summary["games"][game]["missing"] = len(d.get("missing", []))
            summary["games"][game]["spurious"] = len(d.get("spurious", []))
    summary["total"] = stat(allev)
    summary["total"]["by_side"] = {s: stat([e for e in allev if e["side"] == s]) for s in SIDES}
    rows = [(g, summary["games"][g]) for g in summary["games"]] + [("합계", summary["total"])]
    hdr = f"{'판':<6}{'사건':>5}{'울기뒤':>6}{'분모':>5} " + " ".join(f"{v:>16}" for v in VERDICTS) + f"{'low':>5}"
    print(hdr)
    for name, s in rows:
        print(fmt(name, s))
    print("\n자리별(합계)")
    print(hdr)
    for side in SIDES:
        print(fmt(side, summary["total"]["by_side"][side]))
    for g in summary["games"]:
        print(f"\n자리별 {g}")
        for side in SIDES:
            print(fmt(side, summary["games"][g]["by_side"][side]))
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                      encoding="utf-8")


def stat(evs):
    base = [e for e in evs if not e.get("after_call")]
    c = {v: sum(1 for e in base if e.get("verdict") == v) for v in VERDICTS}
    ac = {v: sum(1 for e in evs if e.get("after_call") and e.get("verdict") == v) for v in VERDICTS}
    n = len(base)
    return {"events": len(evs), "after_call": len(evs) - n, "denom": n, "counts": c,
            "pct": {v: round(100 * c[v] / n, 1) if n else None for v in VERDICTS},
            "after_call_counts": ac,
            "conf_low": sum(1 for e in base if e.get("conf") == "low")}


def fmt(name, s):
    cells = " ".join(f"{s['counts'][v]:>5} ({s['pct'][v] if s['pct'][v] is not None else 0:>5.1f}%)"
                     for v in VERDICTS)
    return f"{name:<6}{s['events']:>5}{s['after_call']:>6}{s['denom']:>5} {cells}{s['conf_low']:>5}"


if __name__ == "__main__":
    cmd = sys.argv[1]
    games = list(TRACKS) if len(sys.argv) < 3 or sys.argv[2] == "all" else [sys.argv[2]]
    if cmd == "sheets":
        for g in games:
            sheets(g)
    elif cmd == "probe":
        for g in games:
            probe(g)
    elif cmd == "tally":
        tally()
    else:
        raise SystemExit(__doc__)
