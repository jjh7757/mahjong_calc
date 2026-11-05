"""축 맞춤 패 라벨 → 회전 상자(OBB) 라벨 초안(2026-11-04, 7회차 준비, 사용자 "2번 준비해줘", 노트북, API 없음).

왜: 축 맞춤 상자는 기운 패(강에 비스듬히 버린 패·떼어 둔 화료패)를 펠트째 감싸 흰 비율 거르기 같은 규칙을 패 모양마다 다시 맞춰야 한다(표 1-65 181209).
회전 상자는 기울기와 상관없이 패에 맞아 그런 예외 규칙이 필요 없다.

방법(상자마다): 라벨 상자 안 패 몸통 마스크(앞면 = 흰색, 뒷면 = 뒷면 색 | 흰색, det_backs 의 HSV 기준)를 열기 연산으로 이웃과 떼고,
가운데 덩어리의 cv2.minAreaRect 에서 기울기·방향만 얻는다. 크기는 라벨 상자에 내접하게 기하로 푼다(inscribed).
  axis      기울기 5° 미만 → 원래 축 상자 그대로(대부분). 10° 미만인데 내접 사각형 밖 귀퉁이가 패로 차 있으면(패산 줄·2단) 역시 axis
  rot       기울기 5° 이상, 귀퉁이 삼각형의 패 마스크 35% 이하(진짜 기운 패는 귀퉁이가 펠트), 안쪽 50% 이상, 패 모양(긴 변/짧은 변 1.1~1.75)
  uncertain 그 밖·45° 가까움(눈 검수 대상). 학습 데이터에는 축 상자로 들어간다.
  뒷면은 기울기 10° 이상·귀퉁이 25% 이하일 때만 rot(세워 둔 패는 윗면·옆면이 같이 보여 각도가 흔들림).
  row       패 하나로는 못 보는 줄(패산·손패) 기울기: 이어진 3개 이상이 한 직선 위면 그 직선 각도(row_angles). rot·fixed 는 그대로.
            단 내접 사각형이 축 상자보다 사진 속 반듯한 패 모양에 가까울 때만(계단처럼 비켜 놓은 반듯한 패는 축 상자 그대로).
라벨: 앞면 = det_backs.fixed_faces + 고른 白(blank/review.json), 뒷면 = 표 1-54 검수 2차(backs/r2/boxes_r2fb.json) 중 앞면에 절반 넘게 안 덮인 것 — det_build.py --backs 와 같다.
  python -I -X utf8 experiments/tile_classifier/det_obb.py           → data/det/obb/rects.json, 검수 그림 data/det/obb/review_<n>.jpg, review_list.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from det_backs import back_mask, fixed_backs, fixed_faces, white_mask  # noqa: E402

DET = HERE / "data" / "det"
OUT = DET / "obb"
MIN_ANGLE = 5.0
CORNER = 0.35  # 내접 사각형 밖 귀퉁이 중 패 마스크 비율 상한(진짜 기운 패는 펠트라 낮다)
# 뒷면(세워 둔 패산·2단)은 위에서 윗면·옆면이 같이 보여 각도가 흔들린다(검수 그림 확인) → 더 보수적으로
BACK_MIN_ANGLE, BACK_CORNER = 10.0, 0.25


def labels() -> dict:
    """{사진: dict(path, faces, backs)} — det_build.py --backs 와 같은 라벨."""
    rows = json.loads((DET / "boxes_final.json").read_text(encoding="utf-8"))
    blanks: dict = {}
    if (DET / "blank" / "review.json").exists():
        cands = json.loads((DET / "blank" / "cands.json").read_text(encoding="utf-8"))
        picked = json.loads((DET / "blank" / "review.json").read_text(encoding="utf-8"))
        blanks = {n: [cands[n][i]["box"] for i in idx] for n, idx in picked.items()}
    r2 = json.loads((DET / "backs" / "r2" / "boxes_r2fb.json").read_text(encoding="utf-8"))
    out = {}
    for name, r in rows.items():
        faces = [list(b) for b in fixed_faces(name, r["boxes"]) + blanks.get(name, [])]
        backs = [list(b) for b in fixed_backs(name, r2.get(name, {}).get("backs", []))
                 if max((max(0, min(b[0] + b[2], f[0] + f[2]) - max(b[0], f[0])) * max(0, min(b[1] + b[3], f[1] + f[3]) - max(b[1], f[1])) for f in faces), default=0)
                 <= 0.5 * b[2] * b[3]]
        out[name] = dict(path=r["path"], faces=faces, backs=backs)
    return out


def iou(a, b) -> float:
    ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    i = ix * iy
    return i / (a[2] * a[3] + b[2] * b[3] - i + 1e-9)


def inscribed(b: list, tilt: float, sign: float) -> tuple | None:
    """축 상자 b 에 내접하는, 기울기 tilt°(부호 sign) 의 사각형 ((cx, cy), (a, b), 각도). 패 두 변 a·b 는
    W = a·cosθ + b·sinθ, H = a·sinθ + b·cosθ 를 푼 값. θ 가 45° 에 가까우면(cos2θ 작음) 풀 수 없어 None."""
    x, y, w, h = b
    t = np.radians(tilt)
    c2 = np.cos(2 * t)
    if c2 < 0.2:
        return None
    a = (w * np.cos(t) - h * np.sin(t)) / c2
    bb = (h * np.cos(t) - w * np.sin(t)) / c2
    if a <= 0 or bb <= 0:
        return None
    return ((x + w / 2, y + h / 2), (float(a), float(bb)), float(sign * tilt))


def fit(mask: np.ndarray, b: list, min_angle: float = MIN_ANGLE, corner_max: float = CORNER) -> dict:
    """상자 b → {status, rect: ((cx, cy), (w, h), angle) 원본 좌표, angle(0~45° 기울기), why}.
    각도·방향은 마스크 덩어리의 minAreaRect 에서, 크기는 라벨 상자에 내접하게 기하로 푼다(마스크에 옆면·그림자가 섞여도 크기가 안 커진다).
    진짜 기운 패면 내접 사각형 밖 네 귀퉁이 삼각형이 펠트(마스크 거의 없음)이고, 반듯한 패가 이웃과 마스크가 이어진 것이면 귀퉁이도 패로 차 있다."""
    x, y, w, h = b
    sub = mask[y:y + h, x:x + w]
    axis = dict(status="axis", rect=((x + w / 2, y + h / 2), (float(w), float(h)), 0.0), angle=0.0, why="")
    if sub.size == 0:
        return dict(axis, status="uncertain", why="빈 상자")
    k = max(3, int(0.06 * min(w, h)) | 1)
    sub = cv2.morphologyEx(sub, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))  # 이웃 패와 이어진 가는 다리 끊기
    n, lab, stats, cent = cv2.connectedComponentsWithStats(sub)
    if n <= 1:
        return dict(axis, status="uncertain", why="마스크 없음")
    c = lab[h // 2, w // 2]
    if c == 0:  # 가운데가 무늬(검은 획)면 가장 큰 덩어리
        c = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    pts = np.column_stack(np.nonzero(lab == c))[:, ::-1].astype(np.float32)
    (mcx, mcy), (mw, mh), ang = cv2.minAreaRect(cv2.convexHull(pts))
    mask_rect = ((mcx + x, mcy + y), (float(mw), float(mh)), float(ang))  # 검수에서 고를 수 있는 둘째 안(마스크 그대로, 옆면이 섞이면 조금 큼)
    signed = ((ang + 45) % 90) - 45  # -45~45°
    tilt = abs(signed)
    if tilt < min_angle:
        return dict(axis, angle=round(tilt, 1))
    rect = inscribed(b, tilt, 1.0 if signed >= 0 else -1.0)
    if rect is None:
        return dict(axis, status="uncertain", angle=round(tilt, 1), why="45° 가까움", mask_rect=mask_rect, ins_rect=None)
    poly = np.zeros((h, w), np.uint8)
    cv2.fillPoly(poly, [np.round(cv2.boxPoints(((rect[0][0] - x, rect[0][1] - y), rect[1], rect[2]))).astype(np.int32)], 1)
    full = (mask[y:y + h, x:x + w] > 0)
    corner = float(full[poly == 0].mean()) if (poly == 0).any() else 1.0
    inside = float(full[poly == 1].mean()) if (poly == 1).any() else 0.0
    ratio = max(rect[1]) / max(1e-6, min(rect[1]))
    why = []
    if corner > corner_max:
        why.append(f"귀퉁이 패 {corner:.2f}")
    if inside < 0.5:
        why.append(f"안쪽 {inside:.2f}")
    if not 1.1 <= ratio <= 1.75:
        why.append(f"비율 {ratio:.2f}")
    if why and corner > corner_max and tilt < 10:  # 작은 기울기 + 귀퉁이가 차 있음 = 반듯한 패(패산 줄·2단) — 축 상자 그대로
        return dict(axis, angle=round(tilt, 1), why=", ".join(why))
    return dict(status="uncertain" if why else "rot", rect=rect if not why else axis["rect"], angle=round(tilt, 1), why=", ".join(why),
                corner=round(corner, 2), inside=round(inside, 2), mask_rect=mask_rect, ins_rect=rect)


def key(name: str, cls: int, b: list) -> str:
    return f"{name}|{cls}|{','.join(str(int(v)) for v in b)}"


import os

SHAPE_TEST = os.environ.get("OBB_SHAPE_TEST", "fallback")  # 줄 각도의 패 모양 비교: none(17:23 이전, g1·g4·g5 가 본 상태) / strict(17:23~, g2·g3 가 본 상태) / fallback(지금, 기준 없으면 줄 각도)


def row_angles(items: list, cls: int, shape_test: str | None = None) -> int:
    """줄 단위 각도: 패산·손패 줄은 패가 붙어 있어 패 하나의 귀퉁이 판정으로는 기울기를 못 본다(검수 그림 175951·171025).
    같은 종류 상자를 이웃(중심 거리 0.6~1.45 × 짧은 변 중앙값)으로 이어 3개 이상 줄을 만들고, 중심들이 한 직선 위(직선에서 짧은 변 0.45 배 이내)에 있으면
    그 직선의 기울기(5° 이상)를 줄의 모든 상자에 준다(크기는 inscribed). 이미 회전·검수된 상자는 건드리지 않는다. 고친 상자 수."""
    idx = [i for i, it in enumerate(items) if it["cls"] == cls]
    if len(idx) < 3:
        return 0
    # 이 사진에서 반듯한(패 하나 기울기 3° 미만) 같은 종류 패의 (짧은 변, 긴 변) — 회전이냐 계단 배치냐를 가르는 기준
    refs = np.array([sorted(items[i]["box"][2:]) for i in idx if items[i]["status"] == "axis" and items[i]["angle"] < 3], float)

    def shape_dist(s: tuple) -> float:
        """(짧은, 긴) 이 반듯한 패들의 모양과 얼마나 먼지: 가까운 5개까지 log 거리의 중앙값."""
        if len(refs) < 5:
            return 0.0
        d = np.abs(np.log(np.array(sorted(s), float) / refs)).sum(axis=1)
        return float(np.median(np.sort(d)[:5]))
    boxes = [items[i]["box"] for i in idx]
    tw = float(np.median([min(b[2], b[3]) for b in boxes]))
    c = np.array([[b[0] + b[2] / 2, b[1] + b[3] / 2] for b in boxes])
    d = np.linalg.norm(c[:, None] - c[None], axis=2)
    adj = (d >= 0.6 * tw) & (d <= 1.45 * tw)
    seen, n = set(), 0
    for s in range(len(idx)):
        if s in seen:
            continue
        comp, stack = [], [s]
        seen.add(s)
        while stack:
            k = stack.pop()
            comp.append(k)
            for j in np.nonzero(adj[k])[0]:
                if j not in seen:
                    seen.add(int(j))
                    stack.append(int(j))
        if len(comp) < 3:
            continue
        p = c[comp]
        mu = p.mean(axis=0)
        _, _, vt = np.linalg.svd(p - mu)
        dirv = vt[0]
        resid = np.abs((p - mu) @ vt[1])
        if resid.max() > 0.45 * tw:  # 한 직선이 아님(ㄱ자 모서리·강 여러 줄)
            continue
        ang = float(np.degrees(np.arctan2(dirv[1], dirv[0])))
        fa = ((ang + 45) % 90) - 45
        if abs(fa) < MIN_ANGLE:
            continue
        for k in comp:
            it = items[idx[k]]
            if it["status"] in ("rot", "fixed"):
                continue
            rect = inscribed(it["box"], abs(fa), 1.0 if fa >= 0 else -1.0)
            if rect is None:
                continue
            # 진짜 기운 줄이면 축 상자가 패보다 커지고 내접 사각형이 다른 반듯한 패 모양과 맞는다. 계단처럼 비켜 놓은 반듯한 패(구석 깡·퐁, 2단 패산 윗패)면
            # 축 상자가 이미 패 모양이라 내접 사각형이 더 작아져 멀어진다(전수 조사 g1) → 더 가까운 쪽을 고른다
            # 반듯한 패가 5개 미만이면(사진 전체가 돌아간 134815 처럼) 비교 기준이 없으니 줄 각도를 그대로 준다(전수 조사 g3)
            mode = shape_test or SHAPE_TEST
            if mode == "strict" and (len(refs) < 5 or shape_dist(rect[1]) >= shape_dist(it["box"][2:])):
                continue
            if mode == "fallback" and len(refs) >= 5 and shape_dist(rect[1]) >= shape_dist(it["box"][2:]):
                continue
            it.update(status="row", rect=rect, angle=round(abs(fa), 1), why=f"줄 {len(comp)}개 기울기 {fa:.1f}")
            n += 1
    return n


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    rows = labels()
    res, review = {}, []
    from collections import Counter

    tally = Counter()
    # 사람·독립 평가가 고른 값: {key: "axis" | "mask" | "inscribed" | {"angle": 각도}}. 고른 상자는 status "fixed"
    rf = OUT / "review_obb.json"
    picks = {k: v for k, v in json.loads(rf.read_text(encoding="utf-8")).items() if not k.startswith("_")} if rf.exists() else {}
    for name, r in rows.items():
        bgr = cv2.imread(r["path"])
        wm = white_mask(bgr)
        bm = cv2.bitwise_or(back_mask(bgr, loose=True), wm)
        items = []
        for cls, boxes, m in ((0, r["faces"], wm), (1, r["backs"], bm)):
            for b in boxes:
                f = fit(m, b) if cls == 0 else fit(m, b, BACK_MIN_ANGLE, BACK_CORNER)
                k = key(name, cls, b)
                pick = picks.get(k)
                if isinstance(pick, dict):  # {"angle": 부호 있는 각도} — 마스크가 섞여 각도를 못 잰 상자(겹친 패)에 사람이 각도를 준다
                    pick, f = "inscribed", dict(f, ins_rect=inscribed(b, abs(pick["angle"]), 1.0 if pick["angle"] >= 0 else -1.0))
                if pick:
                    src = {"axis": ((b[0] + b[2] / 2, b[1] + b[3] / 2), (float(b[2]), float(b[3])), 0.0), "mask": f.get("mask_rect"), "inscribed": f.get("ins_rect")}[pick]
                    if src is None:
                        raise SystemExit(f"{k}: {pick} 안이 없다")
                    f = dict(f, status="fixed", rect=src, why=f"검수 {pick}")
                f = {kk: v for kk, v in f.items() if kk not in ("mask_rect", "ins_rect")} | ({"mask_rect": f["mask_rect"], "ins_rect": f.get("ins_rect")} if "mask_rect" in f else {})
                items.append(dict(cls=cls, box=b, key=k, **f))
                tally[(cls, f["status"])] += 1 if f["status"] != "axis" else 0
                if f["status"] != "axis":
                    review.append(dict(key=k, name=name, cls=cls, box=b, status=f["status"], angle=f["angle"], why=f["why"], rect=f["rect"],
                                       mask_rect=f.get("mask_rect"), ins_rect=f.get("ins_rect")))
        for cls in (0, 1):
            row_angles(items, cls)
        for it in items:
            if it["status"] == "row":
                tally[(it["cls"], "row")] += 1
        res[name] = dict(path=r["path"], items=items)
        print(name, {s: sum(1 for i in items if i["status"] == s) for s in ("axis", "rot", "uncertain", "fixed", "row")}, flush=True)
    if os.environ.get("OBB_SHAPE_TEST"):  # 다른 모양 비교 방식으로 본 결과만 따로(검수 상태 고정용) — 검수 목록·그림은 안 쓴다
        (OUT / f"rects_{SHAPE_TEST}.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        print("rects_" + SHAPE_TEST, "줄", sum(1 for v in res.values() for it in v["items"] if it["status"] == "row"))
        return
    (OUT / "rects.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    (OUT / "review_list.json").write_text(json.dumps(review, ensure_ascii=False, indent=1), encoding="utf-8")
    # 검수 그림: 회전·불확실·고친 상자마다 주변 크롭. 노랑 = 원래 축 상자(axis), 초록 = 내접 회전(inscribed), 파랑 = 마스크 회전(mask),
    # 칸 위 글자 = 번호·앞(F)/뒤(B)·기울기·상태(r rot / u uncertain / f fixed). 한 장에 40칸
    cells = []
    for i, it in enumerate(review):
        bgr = cv2.imread(rows[it["name"]]["path"])
        x, y, w, h = it["box"]
        pad = int(0.6 * max(w, h))
        X0, Y0 = max(0, x - pad), max(0, y - pad)
        crop = bgr[Y0:y + h + pad, X0:x + w + pad].copy()
        cv2.rectangle(crop, (x - X0, y - Y0), (x - X0 + w, y - Y0 + h), (0, 255, 255), 2)
        for rr, col in ((it.get("ins_rect"), (0, 200, 0)), (it.get("mask_rect"), (255, 120, 0))):
            if rr:
                pts = cv2.boxPoints(((rr[0][0] - X0, rr[0][1] - Y0), rr[1], rr[2])).astype(np.int32)
                cv2.polylines(crop, [pts], True, col, 2)
        crop = cv2.resize(crop, (240, 240))
        cv2.putText(crop, f"{i} {'F' if it['cls'] == 0 else 'B'} {it['angle']:.0f} {it['status'][0]}", (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        cells.append(crop)
    for s in range(0, len(cells), 40):
        part = cells[s:s + 40]
        while len(part) % 8:
            part.append(np.zeros_like(part[0]))
        sheet = np.vstack([np.hstack(part[k:k + 8]) for k in range(0, len(part), 8)])
        cv2.imwrite(str(OUT / f"review_{s // 40}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 82])
    for name, v in res.items():
        tally.update((it["cls"], "axis") for it in v["items"] if it["status"] == "axis")
    print("합계", {f"{'앞면' if c == 0 else '뒷면'} {s}": n for (c, s), n in sorted(tally.items())}, "검수 그림", -(-len(cells) // 40), "장")


if __name__ == "__main__":
    main()
