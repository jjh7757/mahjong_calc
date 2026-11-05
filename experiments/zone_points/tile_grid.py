"""펠트 색 없이 패 상자만으로 격자 선 4개를 만든다(2026-11-03, API 없음). 앱 흐름은 `run_flow.sh tile`(zones.py 의 tile 방식).
규칙은 앱 흐름 결과를 보기 전에 정했다:
  패 폭 s = 앞면 상자 짧은 변 중앙값. 화료자 손패 줄(tile_row.py 와 같은 가장 긴 곧은 사슬)을 뺀 앞면 패 가운데의 중앙값을 탁자 가운데 c 로 본다.
  네 변마다 c 를 지나는 띠(가운데가 c 에서 ±2.5s 안) 의 패를 c 에서 바깥쪽으로 차례로 본다. 처음 만나는 앞면 패부터 틈 0.8s 안으로 이어지는
  앞면 패(손패 줄 제외)를 강으로 보고, 그다음 패(뒷면·손패 줄·틈 넘은 앞면)와 강 끝 사이 틈의 가운데에 선을 둔다. 바깥 패가 없으면 강 끝 + 1.5s.
  그 변의 강이 없으면(첫 강 패가 네 변 첫 패 거리 중앙값보다 3s 넘게 멂) c 를 사이에 둔 반대 변과 대칭.
2판(같은 날, 1판 격자를 이 사진들에서 눈으로 보고 고침 — 개발 값): 1판은 31장 중 8장에서 c 가 강 패 위에 떨어져(울기·떼어 둔 패가 중앙값을 끌어감)
  선이 기기 한가운데를 지났다. c = 네 방향(띠 ±2.5s) 모두 앞면 패로 막히고 네 거리의 최대/최소가 2 이하인 점 중 가장 가까운 패가 가장 먼 점
  (강으로 둘러싸인 기기 자리, s/2 간격 탐색). 못 찾으면 1판 중앙값. 손패 줄은 7장 이상일 때만 강에서 뺀다(강 한 줄은 6장).
  3판(같은 날, 2판도 눈으로 보고 고침): 2판은 화료자 손패·울기와 강 사이 펠트를 기기 자리로 잡은 장면이 k12·k16·133826·143104·125839.
  빈자리 찾기에서 손패 줄을 뺀다.
검출은 그 사진을 학습하지 않은 2종 2차 나눔 모델(kaggle_out_fb2: 오전 fold_am, 오후 fold_pm, k fold_k), 사진 통째 1280, conf 0.25.
  python -I -X utf8 experiments/zone_points/tile_grid.py   → data/zone_points/tile_grid.json, 그림 data/zone_points/tile_grid/
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import ImageDraw
from ultralytics import YOLO

sys.path.insert(0, str(Path(__file__).resolve().parent))
from propose import DATA, load  # noqa: E402
from zones import scene_list  # noqa: E402

DET = DATA.parent / "det" / "kaggle_out_fb2" / "out"
BAND, GAP, LAST, FAR = 2.5, 0.8, 1.5, 3.0
BALANCE, ROW_MIN = 2.0, 7
OUT = DATA / "tile_grid"


def detect(model, im) -> tuple[np.ndarray, np.ndarray]:
    r = model.predict(np.asarray(im)[:, :, ::-1], imgsz=1280, conf=0.25, verbose=False, device="cpu")[0]
    b = np.array(r.boxes.xyxy.tolist()).reshape(-1, 4)
    cls = np.array(r.boxes.cls.tolist(), int)
    return b[cls == 0], b[cls == 1]


def longest_chain(b: np.ndarray) -> list[int]:
    """tile_row.py 와 같다: 수직 거리 0.35s·간격 2s 안으로 이어지는 가장 긴 곧은 줄."""
    c = (b[:, :2] + b[:, 2:]) / 2
    wh = b[:, 2:] - b[:, :2]
    s = np.median(np.minimum(wh[:, 0], wh[:, 1])) if len(b) else 0
    best: list[int] = []
    for i in range(len(b)):
        for j in range(i + 1, len(b)):
            d = c[j] - c[i]
            L = np.hypot(*d)
            if L < 1e-6 or L > s * 8:
                continue
            u = d / L
            n = np.array([-u[1], u[0]])
            idx = np.where(np.abs((c - c[i]) @ n) < 0.35 * s)[0]
            if len(idx) <= len(best):
                continue
            order = idx[np.argsort((c[idx] - c[i]) @ u)]
            t = (c[order] - c[i]) @ u
            run, cur = [order[0]], [order[0]]
            for k in range(1, len(order)):
                cur = cur + [order[k]] if t[k] - t[k - 1] < 2.0 * s else [order[k]]
                if len(cur) > len(run):
                    run = list(cur)
            if len(run) > len(best):
                best = run
    return best


def hole(faces: np.ndarray, s: float) -> np.ndarray | None:
    """네 방향 모두 앞면 패로 막히고 네 거리가 고른 점 중 가장 가까운 패가 가장 먼 점(기기 자리). 펠트 빈 곳은 줄 방향이 안 막혀 빠진다."""
    lo_xy, hi_xy = faces[:, :2].min(0), faces[:, 2:].max(0)
    P = np.stack(np.meshgrid(np.arange(lo_xy[0], hi_xy[0], s / 2), np.arange(lo_xy[1], hi_xy[1], s / 2)), -1).reshape(-1, 2)
    inside = ((P[:, None, 0] > faces[None, :, 0]) & (P[:, None, 0] < faces[None, :, 2]) & (P[:, None, 1] > faces[None, :, 1]) & (P[:, None, 1] < faces[None, :, 3])).any(1)
    P = P[~inside]
    D = []
    for axis in (0, 1):
        perp = 1 - axis
        mid = (faces[:, perp] + faces[:, perp + 2]) / 2
        band = np.abs(mid[None, :] - P[:, perp, None]) <= BAND * s
        for sign in (-1, 1):
            inner = faces[None, :, axis] - P[:, axis, None] if sign > 0 else P[:, axis, None] - faces[None, :, axis + 2]
            D.append(np.where(band & (inner >= 0), inner, np.inf).min(1))
    D = np.stack(D, 1)
    lo, hi = D.min(1), D.max(1)
    ok = np.isfinite(hi) & (hi <= BALANCE * np.maximum(lo, 1e-6))
    return P[np.argmax(np.where(ok, lo, -1))] if ok.any() else None


def walk(boxes: np.ndarray, river: np.ndarray, c: np.ndarray, axis: int, sign: int, s: float) -> tuple[float | None, float | None, float | None]:
    """c 에서 sign 쪽으로 (첫 패 안쪽 거리, 강 끝 거리, 다음 패 안쪽 거리). 거리는 c 에서 축 방향."""
    perp = 1 - axis
    mid = (boxes[:, perp] + boxes[:, perp + 2]) / 2
    if sign > 0:
        inner, outer = boxes[:, axis] - c[axis], boxes[:, axis + 2] - c[axis]
    else:
        inner, outer = c[axis] - boxes[:, axis + 2], c[axis] - boxes[:, axis]
    keep = (np.abs(mid - c[perp]) <= BAND * s) & (outer > 0)
    idx = np.where(keep)[0]
    idx = idx[np.argsort(np.maximum(inner[idx], 0))]
    first = float(max(inner[idx[0]], 0)) if len(idx) else None
    end = nxt = None
    for i in idx:
        lo = max(inner[i], 0)
        if end is None:
            if not river[i]:
                nxt = float(lo)
                break
            end = float(outer[i])
        elif river[i] and lo - end <= GAP * s:
            end = max(end, float(outer[i]))
        else:
            nxt = float(lo)
            break
    return first, end, nxt


def grid_of(faces: np.ndarray, backs: np.ndarray, W: int, H: int) -> tuple[dict | None, dict]:
    if len(faces) < 4:
        return None, dict(why="앞면 4개 미만")
    wh = faces[:, 2:] - faces[:, :2]
    s = float(np.median(wh.min(1)))
    row = longest_chain(faces)
    row = row if len(row) >= ROW_MIN else []
    c = hole(np.delete(faces, row, axis=0), s)  # 손패 줄을 빼야 손패·강 사이 펠트가 한쪽이 열려 빠진다
    found = c is not None
    if not found:
        rest = np.delete(faces, row, axis=0)
        c = np.median((rest[:, :2] + rest[:, 2:]) / 2, axis=0)
    boxes = np.vstack([faces, backs]) if len(backs) else faces
    river = np.zeros(len(boxes), bool)
    river[: len(faces)] = True
    river[row] = False
    sides = {"left": (0, -1), "right": (0, 1), "top": (1, -1), "bottom": (1, 1)}
    got = {k: walk(boxes, river, c, *v, s) for k, v in sides.items()}
    firsts = [g[0] for g in got.values() if g[0] is not None]
    near = float(np.median(firsts)) if firsts else 0
    dist = {}
    for k, (first, end, nxt) in got.items():
        if end is None or first is None or first > near + FAR * s:
            dist[k] = None  # 그 변 강 없음
        else:
            dist[k] = (end + nxt) / 2 if nxt is not None else end + LAST * s
    opp = {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}
    for k in sides:
        if dist[k] is None:
            dist[k] = dist[opp[k]]
    info = dict(s=round(s, 1), c=[round(float(v)) for v in c], hole=found, row=len(row), walk={k: [None if v is None else round(v) for v in g] for k, g in got.items()})
    if any(v is None for v in dist.values()):
        return None, info | dict(why="마주 보는 두 변 모두 강 없음")
    g = dict(x1=round((c[0] - dist["left"]) / W * 1000), x2=round((c[0] + dist["right"]) / W * 1000),
             y1=round((c[1] - dist["top"]) / H * 1000), y2=round((c[1] + dist["bottom"]) / H * 1000))
    g = {k: min(max(v, 1), 999) for k, v in g.items()}
    if not (g["x1"] < g["x2"] and g["y1"] < g["y2"]):
        return None, info | dict(why="선 순서 어긋남")
    return g, info


def model_for(name: str, models: dict) -> YOLO:
    if name.startswith("k"):
        return models["fold_k"]
    return models["fold_am"] if name < "20261031_14" else models["fold_pm"]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    labels = json.loads((DATA / "labels.json").read_text(encoding="utf-8"))
    models = {f: YOLO(str(DET / f"{f}.pt"), task="detect") for f in ("fold_am", "fold_pm", "fold_k")}
    OUT.mkdir(exist_ok=True)
    out = {}
    for n in scene_list():
        im = load(labels[n]["src"])
        W, H = im.size
        faces, backs = detect(model_for(n, models), im)
        g, info = grid_of(faces, backs, W, H)
        out[n] = dict(grid=g, **info)
        print(n, g, info.get("why", ""), "s", info.get("s"), "row", info.get("row"), flush=True)
        sm = im.copy()
        sm.thumbnail((1400, 1400))
        k = sm.width / W
        d = ImageDraw.Draw(sm)
        for x in faces:
            d.rectangle([v * k for v in x], outline=(255, 230, 0), width=1)
        for x in backs:
            d.rectangle([v * k for v in x], outline=(60, 140, 255), width=1)
        if g:
            for x in (g["x1"], g["x2"]):
                d.line((x * sm.width / 1000, 0, x * sm.width / 1000, sm.height), fill=(255, 40, 40), width=3)
            for y in (g["y1"], g["y2"]):
                d.line((0, y * sm.height / 1000, sm.width, y * sm.height / 1000), fill=(255, 40, 40), width=3)
        sm.save(OUT / f"{n}.jpg", quality=85)
    (DATA / "tile_grid.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("격자 나옴", sum(v["grid"] is not None for v in out.values()), "/", len(out))


if __name__ == "__main__":
    main()
