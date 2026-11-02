"""白 을 학습 없이 코드로 찾는 실험(2026-11-02, 노트북, API 없음). 서버 코드는 고치지 않는다. 시험 사진을 학습하지 않은 나눔 모델만.

뒷면이 색 있는 패 세트에서는 무늬 없는 흰 앞면 = 白 이라, 위치만 찾으면 종류가 정해진다. 틀이 실패하고 장수가 모자랄 때만 시도한다.
  빈칸: 손패 줄 간격으로 빠진 칸(틈·양 끝)을 계산해, 흰 면 0.7 이상·무늬 0.01 미만이면 白 으로 넣는다(seat_wide.fill_row 와 같은 생각).
  모서리: 3장이 모자라면 탁자 끝(펠트 아래쪽 경계)이 오른쪽 모서리에서 패 3장 폭만큼 올라와 있고, 그 안이 희고 무늬가 없을 때 白 퐁으로 본다.
채운 답은 자동 반영하지 않는다(block). 규칙을 실패 사진을 보고 정했으므로 회복 수는 일반화 숫자가 아니다.
헛발동 검사: 틀을 잡은 사진에서 무늬 패 상자를 일부러 지워 장수를 모자라게 만들어도 채우지 않아야 한다(지운 1장씩 / 손패 끝 3장 / 울기 묶음).
  python -I -X utf8 experiments/tile_classifier/server_bench/blank_fill.py
결과 data/det/blank_fill.json
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.argv = [sys.argv[0], "--r2"]
from rules_core import rv, st  # noqa: E402
from app import local_read as lr  # noqa: E402
from app import seat_wide as sw  # noqa: E402
from det_eval import hr, hy, sg  # noqa: E402

WHITE_MIN = 0.7  # seat_wide.FILL_WHITE 와 같은 값
RISE = 0.5  # 탁자 끝이 패 높이의 이만큼 넘게 올라오면 패가 놓인 곳
CORNER_W = (2.4, 3.9)  # 패 3장 폭(패 폭 배수)
CORNER_H = (0.6, 1.5)  # 올라온 높이(패 높이 배수)
CORNER_REACH = 1.0  # 오른쪽 탁자 끝에서 패 폭 1개 안에서 끝나야 모서리
WINDOW = 6  # 오른쪽 끝에서 패 몇 개 폭을 보나
SEAM_JUMP, SEAM_MIN = 0.12, 0.6  # 패 나누기: 위쪽 끝 꺾임 최소(패 폭 배수), 첫 패 최소 폭(패 폭 배수)
TILE_W_MAX, TILE_H = 1.3, 1.05  # 모서리 패 상자: 폭 상한(패 폭 배수), 높이(패 높이 배수)
EDGE = 0.1  # 모서리 무늬 검사에서 뺄 경계 폭(패 폭 배수)
CORNER_INK = 0.03  # 모서리 칸 무늬 비율 상한. 패 옆면 줄이 조금 들어와 낱장 기준 0.01 보다 넉넉히


def blank_at(rgb: np.ndarray, b) -> bool:
    return sw._white_at(rgb, b) >= WHITE_MIN and st.ink(rgb, b) < lr.BLANK


def overlaps(b, faces: list) -> bool:
    return any(min(b[0] + b[2], f[0] + f[2]) - max(b[0], f[0]) > 0.3 * b[2] and min(b[1] + b[3], f[1] + f[3]) - max(b[1], f[1]) > 0.3 * b[3] for f in faces)


def row_blanks(rgb: np.ndarray, faces: list, fr: st.SeatFrame, split: int) -> list:
    """손패 줄의 틈·양 끝에서 무늬 없는 흰 칸. 줄에 든 상자(앞뒤 덩어리 모두)로 간격을 잰다."""
    W = rgb.shape[1]
    line = st.fit_line([f for f in faces if f[0] + f[2] / 2 < split + st.SPLIT_MARGIN * W])
    if line is None:
        return []
    a, c = line
    on = sorted([f for f in faces if abs(f[1] + f[3] / 2 - (a * (f[0] + f[2] / 2) + c)) < 0.5 * fr.th and f[3] > f[2]], key=lambda x: x[0])
    if len(on) < 2:
        return []
    steps = [q[0] - p[0] for p, q in zip(on, on[1:]) if q[0] - p[0] < 1.4 * fr.tw]
    if not steps:
        return []
    pitch = statistics.median(steps)
    out = []
    for p, q in zip(on, on[1:]):
        k = round((q[0] - p[0]) / pitch)
        for i in range(1, k):
            out.append((round(p[0] + (q[0] - p[0]) * i / k), round(p[1] + (q[1] - p[1]) * i / k), p[2], p[3]))
    for e, step in ((on[0], -1), (on[-1], 1)):
        for i in range(1, 5):
            out.append((round(e[0] + step * i * pitch), round(e[1] + step * i * pitch * a), e[2], e[3]))
    # 끝쪽 후보는 안쪽부터 이어져야 한다(떨어진 흰 곳을 건너뛰어 잡지 않게)
    keep = [b for b in out if not overlaps(b, faces) and blank_at(rgb, b)]
    lo, hi = on[0][0], on[-1][0]
    inner = [b for b in keep if lo < b[0] < hi]
    left = [b for b in keep if b[0] <= lo and round((lo - b[0]) / pitch) <= 1 + sum(1 for x in keep if b[0] < x[0] <= lo)]
    right = [b for b in keep if b[0] >= hi and round((b[0] - hi) / pitch) <= 1 + sum(1 for x in keep if hi <= x[0] < b[0])]
    return inner + left + right


def first_seam(tops: np.ndarray, tw: float) -> int | None:
    """왼쪽 첫 패의 오른쪽 끝: 위쪽 경계의 큰 꺾임 두 곳 중 왼쪽. 나란히 놓여 안 꺾이면 None."""
    span = 24  # 패 모서리가 둥글어 꺾임이 약 30픽셀에 걸치기도 한다(171245)
    if len(tops) <= span:
        return None
    jump = np.abs(tops[span:].astype(int) - tops[:-span].astype(int))
    cuts: list[int] = []
    for i in np.argsort(-jump):
        c = int(i) + span // 2
        if jump[i] < SEAM_JUMP * tw or len(cuts) == 2:
            break
        if c >= SEAM_MIN * tw and len(tops) - c >= SEAM_MIN * tw and all(abs(c - k) >= SEAM_MIN * tw for k in cuts):
            cuts.append(c)
    return min(cuts) if cuts else None


def corner_blank(rgb: np.ndarray, fr: st.SeatFrame, faces: list) -> list | None:
    """오른쪽 모서리 白 퐁: 펠트 아래쪽 경계가 패 3장 폭만큼 올라온 곳. 세 상자(왼쪽부터) 또는 None."""
    felt = st.felt_mask(rgb)
    y_ref = int(max(b[1] + b[3] for b in fr.hand) + fr.th)  # 손패 줄 아래 펠트에서 아래로 내려가며 끝을 찾는다(탁자 밖 초록 옷·그늘을 안 잡게)
    if y_ref >= felt.shape[0]:
        return None
    cols = np.nonzero(felt[y_ref])[0]
    if not cols.size:
        return None
    # 오른쪽 탁자 끝 = 패 폭 2개 넘게 이어진 펠트 중 가장 오른쪽(테두리 너머 작은 조각을 안 잡게)
    runs = np.split(cols, np.nonzero(np.diff(cols) > 0.5 * fr.tw)[0] + 1)
    long_runs = [c for c in runs if c[-1] - c[0] >= 2 * fr.tw]
    if not long_runs:
        return None
    right = int(long_runs[-1][-1])
    x0 = max(0, int(right - WINDOW * fr.tw))

    def edge(x: int) -> int:
        if not felt[y_ref, x]:
            return -1  # 손·팔 등으로 가려진 줄
        stop = np.nonzero(~felt[y_ref:, x])[0]
        return y_ref + int(stop[0]) if stop.size else felt.shape[0]

    prof = np.array([edge(x) for x in range(x0, right + 1)])
    # 탁자 끝은 손패 줄과 나란하다. 그만큼 빼고 봐야 기운 사진의 비스듬한 끝을 패로 잘못 보지 않는다
    tilt = lr._line(fr.hand)[0] * np.arange(len(prof))
    level = prof - tilt
    seen = level[prof >= 0]
    if not seen.size:
        return None
    base = float(np.percentile(seen, 90))  # 모서리는 패가 절반 넘게 가려 높은 쪽으로 잡는다
    up = (prof >= 0) & (level < base - RISE * fr.th)
    idx = np.nonzero(up)[0]
    if not idx.size:
        return None
    end = int(idx.max())
    start = end
    while start > 0 and (up[start - 1] or (start >= 2 and up[start - 2])):
        start -= 1
    x1, x2 = x0 + start, x0 + end + 1
    if right - x2 > CORNER_REACH * fr.tw or not CORNER_W[0] * fr.tw <= x2 - x1 <= CORNER_W[1] * fr.tw:
        return None
    tops = prof[start:end + 1]
    if not CORNER_H[0] * fr.th <= base - float(np.median(level[start:end + 1])) <= CORNER_H[1] * fr.th:
        return None
    y2 = int(base + tilt[end])
    # 계단이라 칸마다 위쪽 끝이 달라 상자 대신 경계 안쪽 픽셀만 본다(펠트·패 옆면 줄 제외)
    hsv = np.asarray(Image.fromarray(rgb[:y2, x1:x2]).convert("HSV")).astype(int)
    trim = int(EDGE * fr.tw)
    inside = np.zeros(hsv.shape[:2], bool)
    for i, t in enumerate(tops):
        if trim <= i < len(tops) - trim and t + trim < y2 - trim:
            inside[t + trim:y2 - trim, i] = True
    if inside.sum() == 0:
        return None
    ink = ((hsv[..., 2] < 120) | (hsv[..., 1] > 80))[inside].mean()
    if ink >= CORNER_INK:
        return None
    # 패마다 상자. 오른쪽·아래는 흰 테두리 위에 걸쳐 경계가 안 보이므로, 폭은 첫 꺾임(없으면 손패 패 폭), 높이는 손패 패 높이로 정한다
    seam = first_seam(tops, fr.tw)
    pw = float(np.clip(seam if seam else fr.tw, fr.tw, TILE_W_MAX * fr.tw))
    boxes = []
    for i in range(3):
        col = tops[int(i * pw):int((i + 1) * pw)]
        top = int(np.median(col)) if col.size else boxes[-1][1]
        boxes.append((round(x1 + i * pw), top, round(pw), round(TILE_H * fr.th)))
    return None if any(overlaps(b, faces) for b in boxes) else boxes


def fill(rgb: np.ndarray, faces: list, split: int) -> tuple[st.SeatFrame | None, list]:
    """틀이 실패한 사진에 白 을 채워 다시 잡는다. (통과한 틀, 채운 상자) 또는 (None, [])."""
    fr = lr.split_frame(rgb, faces, split)
    if fr is None or fr.count >= 13:
        return None, []
    added = row_blanks(rgb, faces, fr, split)
    if fr.count + len(added) > 14:
        return None, []
    if added:
        fr = lr.split_frame(rgb, faces + added, split)
        if fr is None:
            return None, []
    if fr.count + 3 in (13, 14):
        boxes = corner_blank(rgb, fr, faces + added)
        if boxes:
            fr.melds = [*fr.melds, boxes]
            added = added + boxes
    return (fr, added) if added and lr.frame_ok(fr, rgb) else (None, [])


def read_filled(r: lr.LocalReader, rgb: np.ndarray, fr: st.SeatFrame) -> tuple[list, list]:
    def one(b) -> str:
        return "5z" if st.ink(rgb, b) < lr.BLANK else r.read([lr.cut(rgb, b)])[0]

    hand = [one(b) for b in fr.hand] + ([one(fr.separate)] if fr.separate else [])
    melds = [" ".join("5z" if st.ink(rgb, b) < lr.BLANK else r.read_meld_tile(rgb, b) for b in m) for m in fr.melds]
    return hand, melds


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    meta = json.loads((HERE / "meta.json").read_text(encoding="utf-8"))
    truth = {s["name"]: s for s in sg.eval_scenes() if s["hand"] is not None}
    readers: dict = {}
    rows = []
    neg = {"1장": [0, 0], "손패 끝 3장": [0, 0], "울기 묶음": [0, 0]}
    fires = []
    secs = []
    for p in meta["photos"]:
        s = truth.get(p["name"])
        if s is None:
            continue
        k = (p["det"], p["part"])
        r = readers.setdefault(k, lr.LocalReader(det_model=HERE / "models" / f"det_fold_{p['det']}.onnx", cls_model=HERE / "models" / f"cls_{p['part']}.onnx"))
        jpg = (HERE / "crops" / f"{p['name']}.jpg").read_bytes()
        base = r.read_seat(jpg, p["frac"])
        rgb = np.asarray(Image.open(HERE / "crops" / f"{p['name']}.jpg").convert("RGB"))
        faces = rv.dedupe(rv.keep_faces(r.detect(rgb), rv.white_mask(rgb)))
        split = int(rgb.shape[1] * p["frac"])
        w = 2 if not p["name"].startswith("2026") else 1
        b_pass = bool(base["hand"]) and not base["block"] and hy.check(base["hand"], [m.split() for m in base["melds"]])[0]
        row = dict(name=p["name"], w=w, base_framed=base["framed"], base_pass=b_pass, base_ok=hr.same(base["hand"], base["melds"], s), filled=False)
        if not base["framed"]:
            t0 = time.perf_counter()
            fr, added = fill(rgb, faces, split)
            secs.append(time.perf_counter() - t0)
            if fr is not None:
                hand, melds = read_filled(r, rgb, fr)
                row.update(filled=True, added=len(added), hand=" ".join(hand), melds=melds, ok=hr.same(hand, melds, s),
                           shape=hy.check(hand, [m.split() for m in melds])[0])
                print(p["name"][-6:], "채움", len(added), " ".join(hand), melds, "맞음", row["ok"], "형태", row["shape"], "| 정답", " ".join(s["hand"]), s["melds"], flush=True)
            else:
                print(p["name"][-6:], "채우지 않음", flush=True)
        else:
            fr0 = lr.split_frame(rgb, faces, split)
            inked = lambda b: st.ink(rgb, b) >= lr.BLANK

            def trial(kind: str, gone: list) -> None:
                neg[kind][0] += 1
                got, added = fill(rgb, [f for f in faces if f not in gone], split)
                if got is not None:
                    neg[kind][1] += 1
                    fires.append(dict(photo=p["name"], kind=kind, gone=gone, added=added))
                    print("  헛발동", p["name"][-6:], kind, gone, "→", added, flush=True)

            for b in fr0.hand:
                if inked(b):
                    trial("1장", [b])
            if len(fr0.hand) >= 3 and all(inked(b) for b in fr0.hand[-3:]):
                trial("손패 끝 3장", list(fr0.hand[-3:]))
            for m in fr0.melds:
                if all(inked(b) for b in m):
                    trial("울기 묶음", list(m))
        rows.append(row)
    n = sum(x["w"] for x in rows)
    fixed = [x for x in rows if x["filled"]]
    print(f"\n{n}회 | 기존 틀 {sum(x['base_framed'] for x in rows)}/{len(rows)}, 기존 자동 {sum(x['w'] * x['base_pass'] for x in rows)}(틀림 {sum(x['w'] * (x['base_pass'] and not x['base_ok']) for x in rows)})")
    print(f"채운 사진 {len(fixed)}: 맞음 {sum(x['ok'] for x in fixed)}, 틀림 {sum(not x['ok'] for x in fixed)} (전부 자동 반영 안 함)")
    print("헛발동(시험 수 → 채움):", neg)
    if secs:
        print(f"채우기 시간 중앙 {statistics.median(secs) * 1000:.0f}ms, 최대 {max(secs) * 1000:.0f}ms")
    (HERE.parent / "data" / "det" / "blank_fill.json").write_text(json.dumps(dict(rows=rows, neg=neg, fires=fires), ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
