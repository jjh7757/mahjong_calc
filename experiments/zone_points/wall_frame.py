"""탁자 독립 격자 8b-1(2026-11-06, 사진만 읽음, API·서버 없음): 가운데 기기 + 패산으로 기준점(중심·방향·패 한 장 크기 u)을 찾고,
그 기준점에서 패 단위(u)로 만든 구역에 정답 패 상자가 제 구역으로 떨어지는지 잰다(표 1-40 방식). 격자 코드는 안 바꾼다.

기준점 찾기(색 안 씀 — 검출기 상자만):
  방향 θ  = 앞면·뒷면 회전 상자 각도(90° 주기) 평균                 u = 앞면 상자 짧은 변 중앙값(앞면이 적으면 뒷면)
  기기    = 앞면 패 무리 안의 "빈 정사각형"(강 첫 줄이 네 변에 붙는 곳) — 중심·반폭 D
  패산    = 기기 둘레 뒷면 줄 중 가장 안쪽 줄(변마다), 패산 반폭 W 로 중심을 다시 잡음(맞은편 두 줄이면 가운데, 한 줄이면 W 만큼 안쪽)
구역(패 단위, 앱 GridZones 와 같은 바람개비 5칸을 θ 로 돌리고 u 로 잰 것): 가운데 = |x|,|y| < R, 자리 = 그 변 + 오른쪽 모서리.
  세부(보고만): 손패 띠 = 변 가운데 14u±1u·깊이 R~R+5u, 모서리 울기 = 손패 띠 오른쪽, 강 = 기기 변에서 4줄, 리치봉 = 기기 가장자리.
펠트 색(보조): 기기 둘레 띠(패 상자 밖)에서 사진마다 잰 색과 가까운 픽셀 vs 초록 고정(앱 _isGreen) — 펠트 사각형을 덮는 비율·밖으로 샌 비율.

  python -I -X utf8 experiments/zone_points/wall_frame.py det        검출 캐시(사진마다 한 번, ONNX 2 스레드) data/zone_points/wall_frame_det.json
  python -I -X utf8 experiments/zone_points/wall_frame.py run        결과 experiments/zone_points/results/wall_frame.json
  python -I -X utf8 experiments/zone_points/wall_frame.py sheet      확인 그림 experiments/zone_points/results/wall_frame_*.jpg(커밋 안 함)
세트: dev(10-31 매장 20 + B·C·D 6, 방법을 여기서 고침) · rise(10-31 프레임: 패산이 막 올라온 14) · dealt(그 30초 뒤 14) ·
      carry(rise 기준점 ×4 를 같은 판 화료 사진 7장에) · test(10-24 삼각대 15, 한 번만) · recolor(같은 15 색 바꿈, 한 번만) · rc_gray·rc_dgreen·rc_redframe(회귀 재색칠, 개발 사진 26, 한 번만).
가림·사용자 문제 사진(seat_grow.EXCLUDED)은 뺀다.
"""
from __future__ import annotations

import io
import json
import math
import os
import sys
import time
import zipfile
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "2")
import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

cv2.setNumThreads(2)
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPO = Path(os.environ.get("RECOGNIZER_REPO", "C:/Users/jjh7757/dev/mahjong-recognizer"))
for p in (HERE, ROOT / "experiments" / "speed", REPO):
    sys.path.insert(0, str(p))
DATA = ROOT / "experiments" / "tile_classifier" / "data"
ZP = DATA / "zone_points"
CACHE = ZP / "wall_frame_det.json"
RES = HERE / "results"
OUT = RES / "wall_frame.json"
VISIT = ROOT / "experiments" / "visit_20261031" / "captures"
KAKAO = ROOT / "experiments" / "field_20261024" / "kakao_photos"
FIELD = ROOT / "experiments" / "field_20261024" / "captures"
ROBUST = ROOT / "experiments" / "speed" / "robust"
BCD = ["k25", "k28", "k15", "k26", "k12", "k16"]
RC = ["rc_gray", "rc_dgreen", "rc_redframe"]
# 10-31 프레임 중 "패산이 막 올라온" 순간(배경 프레임 흰·뒷면 색 비율로 고른 뒤 눈으로 확인, 2026-11-06) — rise. dealt = 같은 묶음 6장 뒤(약 30초, 배패 중·뒤).
RISE = [("20261031_124830", "01", "f0023_124837.jpg"), ("20261031_125948", "01", "f0017_130010.jpg"), ("20261031_125948", "01", "f0080_130334.jpg"),
        ("20261031_131554", "01", "f0020_131543.jpg"), ("20261031_132352", "01", "f0009_132358.jpg"), ("20261031_133112", "01", "f0012_133131.jpg"),
        ("20261031_141615", "01", "f0067_142131.jpg"), ("20261031_170310", "01", "f0038_170734.jpg"), ("20261031_170310", "04", "f0204_172646.jpg"),
        ("20261031_170310", "04", "f0275_173352.jpg"), ("20261031_170310", "06", "f0356_174846.jpg"), ("20261031_170310", "06", "f0424_175549.jpg"),
        ("20261031_170310", "07", "f0508_180658.jpg"), ("20261031_170310", "08", "f0626_182443.jpg")]
DEALT_STEP = 6
# 같은 카메라 설치 구간(segments.json)에서 패산이 올라온 프레임 → 그 판의 화료 사진. 8b 설계대로 배패 때 잡은 기준점을 화료 사진에 그대로 쓴다(carry).
# 프레임 1020×764 와 사진 4080×3060 은 같은 카메라 같은 화각(4배). 가림·사용자 문제 사진의 판(173352·174846·175549·182443)은 뺐다.
CARRY = [("rise/f0020_131543", "20261031_132239"), ("rise/f0009_132358", "20261031_132954"), ("rise/f0009_132358", "20261031_133030"),
         ("rise/f0012_133131", "20261031_133826"), ("rise/f0067_142131", "20261031_143104"), ("rise/f0038_170734", "20261031_171025"),
         ("rise/f0508_180658", "20261031_181209")]


# ---------------------------------------------------------------- 사진 목록

def frame_after(rec: str, zi: str, f: str, step: int) -> str:
    with zipfile.ZipFile(VISIT / f"{rec}_track" / f"frames_{zi}.zip") as zf:
        names = [x["file"] for x in json.loads(zf.read("frames.json"))["frames"]]
    return names[min(names.index(f) + step, len(names) - 1)]


def items() -> list[dict]:
    """세트별 사진: key·set·src(경로 또는 [zip, 파일])·geo(같은 기하의 원본 key — 정답·라벨은 그것으로)."""
    import seat_grow as sg  # noqa: PLC0415

    dev = [s["name"] for s in sg.eval_scenes()]
    out = []
    for n in dev:
        src = str(KAKAO / f"{n}.jpg") if n in BCD else str(VISIT / n / "original.jpg")
        out.append(dict(key=n, set="dev", src=src, geo=n))
    for rec, zi, f in RISE:
        z = str(VISIT / f"{rec}_track" / f"frames_{zi}.zip")
        out.append(dict(key=f"rise/{f[:-4]}", set="rise", src=[z, f], geo=f"rise/{f[:-4]}"))
        g = frame_after(rec, zi, f, DEALT_STEP)
        out.append(dict(key=f"dealt/{g[:-4]}", set="dealt", src=[z, g], geo=f"dealt/{g[:-4]}"))
    test = sorted(json.loads((DATA / "role" / "field" / "labels.json").read_text(encoding="utf-8")))
    for n in test:
        out.append(dict(key=n, set="test", src=str(FIELD / n / "original.jpg"), geo=n))
        out.append(dict(key=f"recolor/{n}", set="recolor", src=str(FIELD.parent / "captures_recolor" / n / "original.jpg"), geo=n))
    for v in RC:
        for n in dev:
            out.append(dict(key=f"{v}/{n}", set=v, src=str(ROBUST / v / f"{n}.jpg"), geo=n))
    return out


def load_rgb(src) -> np.ndarray:
    if isinstance(src, list):
        with zipfile.ZipFile(src[0]) as zf:
            return np.asarray(Image.open(io.BytesIO(zf.read(src[1]))).convert("RGB"))
    return np.asarray(Image.open(src).convert("RGB"))


# ---------------------------------------------------------------- 검출(캐시)

def det() -> None:
    import onnxruntime as ort  # noqa: PLC0415

    from app import obb  # noqa: PLC0415
    from app.local_read import _letterbox  # noqa: PLC0415

    o = ort.SessionOptions()
    o.intra_op_num_threads, o.inter_op_num_threads = 2, 1
    sess = ort.InferenceSession(str(REPO / "app" / "assets" / "tile-obb-r8.onnx"), sess_options=o, providers=["CPUExecutionProvider"])
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    t0 = time.time()
    for it in items():
        if it["key"] in cache:
            continue
        rgb = load_rgb(it["src"])
        H, W = rgb.shape[:2]
        x, r, left, top = _letterbox(rgb)
        out = sess.run(None, {sess.get_inputs()[0].name: x})[0][0]
        rec = {"size": [W, H]}
        for name, cls in (("faces", 0), ("backs", 1)):
            rec[name] = [[round(c[0], 1), round(c[1], 1), round(s[0], 1), round(s[1], 1), round(a, 2)] for _, (c, s, a) in obb.decode(out, r, left, top, W, H, cls=cls)]
        cache[it["key"]] = rec
        print(it["key"], len(rec["faces"]), len(rec["backs"]), flush=True)
    CACHE.write_text(json.dumps(cache), encoding="utf-8")
    print("검출", len(cache), f"{time.time() - t0:.0f}초")


# ---------------------------------------------------------------- 기준점 찾기

# 개발 세트(10-31 매장 20)에서 사람이 맞춘 기기 꼭짓점으로 잰 값: 기기 반폭 3.0~3.3u, 강 패 가운데 ρ ≤ 7.8u(98% 6.8u),
# 손패 ρ ≥ 10.3u, 패산 줄 ρ ≈ 11~12u(= 기기 반폭의 약 3.85배, 10-31 패산이 막 올라온 프레임).
ROW_BAND = (0.2, 1.4)  # 강 첫 줄 패 가운데가 기기 변에서 떨어진 거리(u)
RIVER_DEPTH = 6.0  # 가운데 칸 = 기기 반폭 D + 이만큼(강 4줄 ≈ 5.4u + 여유). R = D + RIVER_DEPTH
WALL_PER_D = 3.85  # 패산 반폭 / 기기 반폭(10-31 프레임 rise, 기종 값 — 다른 기종이면 다름)
U_BACK = 0.87  # 앞면 없는 프레임: u = 뒷면 짧은 변 × 이 값(10-31 rise 의 기기 반폭으로 맞춤)
HAND_A = 8.0  # 손패 띠 반폭(14u/2 + 1u)
HAND_DEPTH = 6.0  # 손패 띠 깊이(R 부터)
FELT_W = np.array([0.5, 1.0, 1.0])  # 펠트 색 거리: Lab 밝기 가중
FELT_K, FELT_TOL = 2.5, (14.0, 28.0)  # 허용 거리 = 띠 거리 75% × K, 범위 안으로


def rot_frame(theta: float) -> tuple[np.ndarray, np.ndarray]:
    return np.array([math.cos(theta), math.sin(theta)]), np.array([-math.sin(theta), math.cos(theta)])


def to_frame(pts: np.ndarray, c: np.ndarray, theta: float, u: float) -> np.ndarray:
    ex, ey = rot_frame(theta)
    d = np.asarray(pts, float) - c
    return np.stack([d @ ex, d @ ey], 1) / u


def from_frame(q: np.ndarray, c: np.ndarray, theta: float, u: float) -> np.ndarray:
    ex, ey = rot_frame(theta)
    q = np.asarray(q, float) * u
    return c + q[:, :1] * ex + q[:, 1:2] * ey


def orient(rects: np.ndarray) -> float:
    """회전 상자 각도(90° 주기)의 평균, 라디안 (-45°, 45°]."""
    a = np.radians(rects[:, 4]) * 4
    w = rects[:, 2] * rects[:, 3]
    return float(math.atan2((np.sin(a) * w).sum(), (np.cos(a) * w).sum()) / 4)


def side_coords(q: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """바람개비 자리(0 아래·1 오른쪽·2 위·3 왼쪽)와 그 자리 사람 기준 (a = 그 사람 오른쪽, r = 바깥)."""
    x, y = q[:, 0], q[:, 1]
    side = np.where(np.abs(y) >= np.abs(x), np.where(y >= 0, 0, 2), np.where(x >= 0, 1, 3))
    a = np.choose(side, [x, -y, -x, y])
    r = np.choose(side, [y, x, -y, -x])
    return side, a, r


def find_device(faces: np.ndarray, theta: float, u: float) -> dict | None:
    """앞면 패 무리 안 빈 정사각형: 네 변에 강 첫 줄이 붙고 안에는 패가 없는 곳."""
    if len(faces) < 6:
        return None
    c0 = np.median(faces[:, :2], 0)
    q = to_frame(faces[:, :2], c0, theta, u)
    best = None
    grid = np.arange(-6, 6.01, 0.25)
    DX = q[None, :, 0] - grid[:, None]  # (cx, 패)
    DY = q[None, :, 1] - grid[:, None]  # (cy, 패)
    for D in np.arange(2.0, 4.51, 0.25):
        dx, dy = DX[:, None, :], DY[None, :, :]  # (cx, cy, 패)
        rho = np.maximum(np.abs(dx), np.abs(dy))
        n_in = (rho < D - 0.15).sum(-1)
        s = np.zeros_like(n_in)
        sides = np.zeros_like(n_in)
        for t, a in ((dy, dx), (dx, -dy), (-dy, -dx), (-dx, dy)):
            k = ((t >= D + ROW_BAND[0]) & (t <= D + ROW_BAND[1]) & (np.abs(a) <= D + 1)).sum(-1)
            s += np.minimum(k, 6)
            sides += k > 0
        sc = np.where(n_in > 2, -99, s + sides - 3 * n_in)
        i, j = np.unravel_index(int(np.argmax(sc)), sc.shape)
        if best is None or sc[i, j] > best[0]:
            best = (int(sc[i, j]), float(grid[i]), float(grid[j]), float(D), int(sides[i, j]))
    score, cx, cy, D, sides = best
    if sides < 2 or score < 8:
        return None
    # 변마다 첫 줄 안쪽 끝으로 가운데·반폭을 다시 잡는다.
    dx, dy = q[:, 0] - cx, q[:, 1] - cy
    half_r = []  # 패의 바깥쪽 방향 반길이(u): 회전 상자의 두 축 중 r 방향 투영
    ex, ey = rot_frame(theta)
    for f in faces:
        ax = np.array([math.cos(math.radians(f[4])), math.sin(math.radians(f[4]))])
        ay = np.array([-ax[1], ax[0]])
        half_r.append((abs(ax @ ex) * f[2] + abs(ay @ ex) * f[3], abs(ax @ ey) * f[2] + abs(ay @ ey) * f[3]))
    half_r = np.array(half_r) / 2 / u  # [:,0] x 방향 반길이, [:,1] y 방향 반길이
    edge = {}
    for k, (t, a, h) in enumerate(((dy, dx, half_r[:, 1]), (dx, -dy, half_r[:, 0]), (-dy, -dx, half_r[:, 1]), (-dx, dy, half_r[:, 0]))):
        m = (t >= D + ROW_BAND[0] - 0.3) & (t <= D + ROW_BAND[1] + 0.3) & (np.abs(a) <= D + 1)
        if m.sum() >= 1:
            edge[k] = float(np.median((t - h)[m]))
    sx, sy, Ds = cx, cy, []
    if 0 in edge and 2 in edge:
        sy, Ds = cy + (edge[0] - edge[2]) / 2, Ds + [(edge[0] + edge[2]) / 2]
    if 1 in edge and 3 in edge:
        sx, Ds = cx + (edge[1] - edge[3]) / 2, Ds + [(edge[1] + edge[3]) / 2]
    Dn = float(np.mean(Ds)) if Ds else float(np.mean(list(edge.values())))
    c = from_frame(np.array([[sx, sy]]), c0, theta, u)[0]
    return {"c": c, "D": Dn, "score": int(score), "sides": int(sides), "edges": len(edge)}


def lying(backs: np.ndarray, theta: float, c0: np.ndarray, u: float) -> np.ndarray:
    """눕힌 뒷면(패산 더미)만: 긴 축이 가운데 쪽(바깥 방향)을 향하고 긴 변/짧은 변 ≥ 1.25. 세운 손패 뒷면은 긴 축이 줄을 따라 눕는다."""
    if not len(backs):
        return backs
    ex, ey = rot_frame(theta)
    q = to_frame(backs[:, :2], c0, theta, u)
    keep = []
    for b, (x, y) in zip(backs, q):
        a = math.radians(b[4])
        ax = np.array([math.cos(a), math.sin(a)]) if b[2] >= b[3] else np.array([-math.sin(a), math.cos(a)])
        radial = ey if abs(y) >= abs(x) else ex
        keep.append(max(b[2], b[3]) / max(min(b[2], b[3]), 1) >= 1.25 and abs(ax @ radial) > 0.7)
    return backs[np.array(keep, bool)]


def find_wall(backs: np.ndarray, theta: float, u: float, c0: np.ndarray, W_range: tuple[float, float], search: float) -> dict | None:
    """패산 사각형: 뒷면 상자 가운데가 둘레 |ρ − W| ≤ 0.6u 띠에 가장 많이 드는 (가운데, W). 변마다 줄 수도 센다."""
    backs = lying(backs, theta, c0, u)
    if len(backs) < 6:
        return None
    q = to_frame(backs[:, :2], c0, theta, u)
    best = None
    grid = np.arange(-search, search + 0.01, 0.25)
    DX = np.abs(q[None, :, 0] - grid[:, None])[:, None, :]
    DY = np.abs(q[None, :, 1] - grid[:, None])[None, :, :]
    rho = np.maximum(DX, DY)  # (cx, cy, 패)
    for W in np.arange(W_range[0], W_range[1] + 0.01, 0.25):
        cnt = (np.abs(rho - W) <= 0.6).sum(-1)
        i, j = np.unravel_index(int(np.argmax(cnt)), cnt.shape)
        if best is None or cnt[i, j] > best[0]:
            best = (int(cnt[i, j]), float(grid[i]), float(grid[j]), float(W))
    n, cx, cy, W = best
    side, a, r = side_coords(q - [cx, cy])
    on = np.abs(r - W) <= 0.6
    per = [int((on & (side == s)).sum()) for s in range(4)]
    rows = sum(p >= 4 for p in per)
    if n < 8 or rows < 1:
        return None
    # 맞은편 두 변이 다 있으면 그 축의 가운데는 정해진다, 한 변뿐이면 W(가정)에 기댄다.
    fixed = {"y": per[0] >= 4 and per[2] >= 4, "x": per[1] >= 4 and per[3] >= 4}
    c = from_frame(np.array([[cx, cy]]), c0, theta, u)[0]
    return {"c": c, "W": float(W), "n": n, "per_side": per, "rows": rows, "fixed": fixed}


def estimate(rec: dict) -> dict:
    """사진 한 장의 기준점. u·θ 는 상자에서, 가운데는 기기(앞면 빈 곳) → 없으면 패산."""
    faces = np.array(rec["faces"], float).reshape(-1, 5)
    backs = np.array(rec["backs"], float).reshape(-1, 5)
    allr = np.concatenate([faces, backs]) if len(faces) + len(backs) else faces
    if len(allr) < 6:
        return {"ok": False, "why": "상자 부족"}
    theta = orient(allr)
    if len(faces) >= 8:
        u, u_src = float(np.median(np.minimum(faces[:, 2], faces[:, 3]))), "faces"
    else:
        u, u_src = float(np.median(np.minimum(backs[:, 2], backs[:, 3]))) * U_BACK, "backs"
    dev = find_device(faces, theta, u)
    out = {"ok": True, "theta": theta, "u": u, "u_src": u_src, "device": None, "wall": None}
    if dev:
        out["device"] = {"c": dev["c"].tolist(), "D": dev["D"], "score": dev["score"], "sides": dev["sides"], "edges": dev["edges"]}
        W0 = WALL_PER_D * dev["D"]
        wall = find_wall(backs, theta, u, dev["c"], (W0 - 1.5, W0 + 1.5), 2.0)
    else:
        wall = find_wall(backs, theta, u, np.median(backs[:, :2], 0) if len(backs) else np.zeros(2), (6.0, 15.0), 4.0)
    if wall:
        out["wall"] = {"c": wall["c"].tolist(), "W": wall["W"], "n": wall["n"], "per_side": wall["per_side"], "rows": wall["rows"], "fixed": wall["fixed"]}
    if dev:
        out["c"], out["D"], out["src"] = dev["c"].tolist(), dev["D"], "device"
    elif wall:
        out["c"], out["D"], out["src"] = wall["c"].tolist(), wall["W"] / WALL_PER_D, "wall"
    else:
        out.update(ok=False, why="기기·패산 못 찾음")
    return out


# ---------------------------------------------------------------- 정답

def truth_tables() -> dict:
    L = json.loads((ZP / "labels.json").read_text(encoding="utf-8"))
    segs = json.loads((ZP / "segments.json").read_text(encoding="utf-8"))["segs"]
    rect = json.loads((ROOT / "experiments" / "rectify" / "results" / "field_rectify.json").read_text(encoding="utf-8"))["captures"]
    roles = json.loads((DATA / "role" / "labels.json").read_text(encoding="utf-8"))
    roles.update(json.loads((DATA / "role" / "field" / "labels.json").read_text(encoding="utf-8")))
    return {"L": L, "segs": segs, "rect": rect, "roles": roles}


def truth_device(T: dict, geo: str, size) -> dict | None:
    """사람이 맞춘 기기 꼭짓점(개발 사진) 또는 그 시각의 카메라 설치 구간 중앙값(프레임). 테스트 15장은 없음."""
    W, H = size
    dev = felt = None
    if geo in T["L"]:
        dev, felt = T["L"][geo]["device"], T["L"][geo]["felt"]
    elif geo.startswith(("rise/", "dealt/")):
        t = geo.split("_")[-1]
        for s in T["segs"]:
            if s["start"] <= t <= s["end"]:
                dev, felt = s["device"], s["felt"]
    elif geo in T["rect"]:
        q = T["rect"][geo]["quad"]
        felt = [q["tl"], q["tr"], q["br"], q["bl"]]
    if geo[-6:] in T["rect"]:
        q = T["rect"][geo[-6:]]["quad"]
        felt = [q["tl"], q["tr"], q["br"], q["bl"]]
    out = {"felt": (np.array(felt) * [W, H]).tolist() if felt else None, "device": None}
    if dev:
        d = np.array(dev) * [W, H]
        e = d[1] - d[0]
        out["device"] = {"c": d.mean(0).tolist(), "theta": math.atan2(e[1], e[0]),
                         "half": float(np.mean([np.linalg.norm(d[(i + 1) % 4] - d[i]) for i in range(4)]) / 2), "pts": d.tolist()}
    return out


def truth_tiles(T: dict, geo: str) -> list[dict]:
    """정답 패: (가운데 x, y, 역할, 자리). 매장·테스트 = 역할 라벨(role_label.py, 사람 수정 포함), B·C·D = 펠트 라벨 규칙(표 1-40 check 와 같은 기준: 편 좌표 ρ<0.25 강, >0.32 자리)."""
    sides = ["bottom", "right", "top", "left"]
    if geo in T["roles"]:
        out = []
        for it in T["roles"][geo]["items"]:
            x, y, w, h = it["box"]
            role = {"wall": "dora", "pair": "dora"}.get(it["role"], it["role"])
            if role in ("hand", "meld", "river", "dora"):
                out.append({"x": x + w / 2, "y": y + h / 2, "role": role, "seat": it.get("seat")})
        return out
    if geo in BCD:
        boxes = json.loads((DATA / "det" / "boxes_final.json").read_text(encoding="utf-8"))[geo]
        W, H = boxes["size"]
        felt = np.array(T["L"][geo]["felt"], np.float32) * [W, H]
        M = cv2.getPerspectiveTransform(felt.astype(np.float32), np.array([[0, 0], [1, 0], [1, 1], [0, 1]], np.float32))
        c = np.array([[x + w / 2, y + h / 2] for x, y, w, h in boxes["boxes"]], np.float32)
        uv = cv2.perspectiveTransform(c.reshape(-1, 1, 2), M).reshape(-1, 2) - 0.5
        side, _, r = side_coords(uv)
        out = []
        for (x, y), s, rr, d in zip(c, side, r, np.abs(uv).max(1)):
            if d < 0.25:
                out.append({"x": float(x), "y": float(y), "role": "river", "seat": None})
            elif d > 0.32:
                out.append({"x": float(x), "y": float(y), "role": "seatrule", "seat": sides[s]})
        return out
    return []


# ---------------------------------------------------------------- 구역·채점

SIDES = ["bottom", "right", "top", "left"]


def zone_frame(pts: np.ndarray, est: dict) -> tuple[list, list]:
    """u 좌표 바람개비 5칸(+ 세부 칸). 돌려주는 값: (큰 칸 이름, 세부 칸 이름)."""
    q = to_frame(pts, np.array(est["c"]), est["theta"], est["u"])
    D = est["D"]
    R = D + RIVER_DEPTH
    x, y = q[:, 0], q[:, 1]
    big = np.where((y > R) & (x > -R), "bottom", np.where((x > R) & (y < R), "right", np.where((y < -R) & (x < R), "top", np.where((x < -R) & (y > -R), "left", "center"))))
    side, a, r = side_coords(q)
    fine = []
    for s, aa, rr, b in zip(side, a, r, big):
        if b == "center":
            if rr < D:
                fine.append("device")
            elif rr <= D + 5.6 and -D - 0.5 <= aa <= D + 3:
                fine.append("river")
            else:
                fine.append("center_other")
        else:
            # 바람개비: 오른쪽 모서리는 그 사람 자리 — 큰 칸 자리 기준으로 다시 잰다.
            k = SIDES.index(b)
            qa = [x, -y, -x, y][k]
            qr = [y, x, -y, -x][k]
            i = len(fine)
            A, Rr = float(qa[i]), float(qr[i])
            if R <= Rr <= R + HAND_DEPTH and -HAND_A <= A <= HAND_A:
                fine.append("hand")
            elif HAND_A < A and Rr >= R - 1:
                fine.append("meld")
            else:
                fine.append("seat_other")
    return big.tolist(), fine


def zone_grid(pts: np.ndarray, g: dict, size) -> list:
    """앱 GridZones 바람개비(사진 좌표 0~1000 선 4개)."""
    W, H = size
    x, y = pts[:, 0] / W * 1000, pts[:, 1] / H * 1000
    x1, x2, y1, y2 = g["x1"], g["x2"], g["y1"], g["y2"]
    return np.where((y > y2) & (x > x1), "bottom", np.where((x > x2) & (y < y2), "right", np.where((y < y1) & (x < x2), "top", np.where((x < x1) & (y > y1), "left", "center")))).tolist()


def unrect(pts: np.ndarray, quad: dict, size, margin: float = 0.12) -> np.ndarray:
    """앱 rectify(image copyRectify = 네 모서리 쌍선형)의 역: 원본 픽셀 → 편 사진 0~1. 뉴턴 반복."""
    W, H = size
    c = np.array([quad[k] for k in ("tl", "tr", "br", "bl")]) * [W, H]
    m = c.mean(0)
    c = m + (c - m) * (1 + 2 * margin)
    tl, tr, br, bl = c
    out = []
    for p in pts:
        s = np.array([0.5, 0.5])
        for _ in range(30):
            u, v = s
            f = tl * (1 - u) * (1 - v) + tr * u * (1 - v) + bl * (1 - u) * v + br * u * v - p
            J = np.stack([(tr - tl) * (1 - v) + (br - bl) * v, (bl - tl) * (1 - u) + (br - tr) * u], 1)
            s = s - np.linalg.solve(J, f)
        out.append(s)
    return np.array(out)


def score(tiles: list[dict], big: list, fine: list | None = None) -> dict:
    """역할별: 제 구역 / 틀린 구역. 손패·울기(·B·C·D 자리 규칙) = 그 사람 자리 칸, 강 = 가운데 칸. 표시패는 가운데에 든 수만(보고)."""
    r = {k: [0, 0] for k in ("hand", "meld", "river", "seatrule")}
    r["dora_center"], r["dora_n"] = 0, 0
    f = {"hand_band": [0, 0], "meld_corner": [0, 0], "river_box": [0, 0]}
    for i, t in enumerate(tiles):
        z = big[i]
        if t["role"] == "dora":
            r["dora_n"] += 1
            r["dora_center"] += z == "center"
            continue
        ok = z == "center" if t["role"] == "river" else z == t["seat"]
        r[t["role"]][0 if ok else 1] += 1
        if fine is not None:
            fz = fine[i]
            if t["role"] == "hand":
                f["hand_band"][0 if (ok and fz == "hand") else 1] += 1
            elif t["role"] == "meld":
                f["meld_corner"][0 if (ok and fz in ("meld", "hand")) else 1] += 1
            elif t["role"] == "river":
                f["river_box"][0 if fz == "river" else 1] += 1
    r["right"] = sum(v[0] for k, v in r.items() if k in ("hand", "meld", "river", "seatrule"))
    r["wrong"] = sum(v[1] for k, v in r.items() if k in ("hand", "meld", "river", "seatrule"))
    if fine is not None:
        r["fine"] = f
    return r


# ---------------------------------------------------------------- 펠트 색(보조)

def felt_check(rgb: np.ndarray, est: dict | None, rec: dict, felt_quad) -> dict:
    """펠트 색을 기기 둘레 띠(패 상자 밖)에서 재서 펠트 덩어리를 찾고, 초록 고정(앱 _isGreen)과 같은 잣대로 비교.
    잣대: 펠트 사각형(정답) 덮은 비율 ≥ 0.85 · 밖으로 샌 넓이 ≤ 사각형의 0.10 이면 성공."""
    if felt_quad is None:
        return {}
    H, W = rgb.shape[:2]
    s = 400 / max(W, H)
    small = cv2.resize(rgb, (round(W * s), round(H * s)), interpolation=cv2.INTER_AREA)
    h, w = small.shape[:2]
    quad = np.zeros((h, w), np.uint8)
    cv2.fillPoly(quad, [np.round(np.array(felt_quad) * s).astype(np.int32)], 1)
    qa = max(int(quad.sum()), 1)

    def judge(mask: np.ndarray) -> dict:
        n, lab, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
        if n <= 1:
            return {"cover": 0.0, "spill": 0.0, "ok": False}
        k = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
        comp = (lab == k).astype(np.uint8)
        cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        filled = np.zeros_like(comp)
        cv2.drawContours(filled, cnts, -1, 1, -1)
        cover = float((filled & quad).sum() / qa)
        spill = float((filled & (1 - quad)).sum() / qa)
        return {"cover": round(cover, 3), "spill": round(spill, 3), "ok": cover >= 0.85 and spill <= 0.10}

    r, g, b = (small[..., i].astype(int) for i in range(3))
    green = (g > r + 20) & (g > b)
    out = {"green": judge(green)}
    if est and est.get("ok"):
        tiles = np.zeros((h, w), np.uint8)
        for f in rec["faces"] + rec["backs"]:
            box = cv2.boxPoints(((f[0] * s, f[1] * s), (f[2] * s * 1.3, f[3] * s * 1.3), f[4]))
            cv2.fillPoly(tiles, [np.round(box).astype(np.int32)], 1)
        yy, xx = np.mgrid[0:h, 0:w]
        q = to_frame(np.stack([xx.ravel() / s, yy.ravel() / s], 1), np.array(est["c"]), est["theta"], est["u"])
        rho = np.abs(q).max(1).reshape(h, w)
        D = est["D"]
        band = (rho > D + 0.5) & (rho < D + RIVER_DEPTH + 1) & (tiles == 0)
        if band.sum() < 50:
            out["measured"] = {"cover": 0.0, "spill": 0.0, "ok": False, "why": "띠 픽셀 부족"}
            return out
        lab_im = cv2.cvtColor(small, cv2.COLOR_RGB2LAB).astype(float)
        ref = np.median(lab_im[band], 0)
        d = np.sqrt((((lab_im - ref) * FELT_W) ** 2).sum(-1))  # 밝기는 덜 봄(조명 얼룩)
        tol = float(np.clip(np.percentile(d[band], 75) * FELT_K, FELT_TOL[0], FELT_TOL[1]))
        out["measured"] = {**judge(d < tol), "lab": [round(v, 1) for v in ref], "tol": round(tol, 1)}
    return out


# ---------------------------------------------------------------- 실행

def saved_grid(geo: str):
    import seat_grow as sg  # noqa: PLC0415

    if not hasattr(saved_grid, "m"):
        saved_grid.m = {s["name"]: s["grid"] for s in sg.scenes()}
        sys.path.insert(0, str(ROOT / "experiments" / "tile_classifier" / "server_bench"))
        src = (ROOT / "experiments" / "tile_classifier" / "server_bench" / "field_bench.py").read_text(encoding="utf-8")
        ns: dict = {}
        exec(src[src.index("STANDARD = dict"):src.index("\n\n\ndef truth")], ns)  # noqa: S102  상수 블록만
        for _, (photos, g) in ns["SCENES"].items():
            for ph in photos:
                saved_grid.m[f"20261024_{ph}"] = g
        saved_grid.std = ns["STANDARD"]
    return saved_grid.m.get(geo)


def run(sets: list[str] | None = None) -> None:
    """sets 를 주면 그 세트만(개발 중에는 dev·rise·dealt 만 — 테스트·색 바꾼·재색칠은 마지막에 한 번만)."""
    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    T = truth_tables()
    rows = {}
    t0 = time.time()
    for it in items():
        if sets and it["set"] not in sets:
            continue
        rec = cache[it["key"]]
        size = rec["size"]
        est = estimate(rec)
        tr = truth_device(T, it["geo"], size)
        row = {"set": it["set"], "geo": it["geo"], "est": est}
        # 기준점 오차(정답 기기가 있을 때): 가운데 거리(u), 방향(도), 기기 반폭 비
        if tr["device"] and est.get("ok"):
            td = tr["device"]
            uu = est["u"]
            row["err"] = {"c_u": float(np.linalg.norm(np.array(est["c"]) - td["c"]) / uu),
                          "theta_deg": float(abs((math.degrees(est["theta"] - td["theta"]) + 45) % 90 - 45)),
                          "half_ratio": float(est["D"] * uu / td["half"])}
            for k in ("device", "wall"):
                if est.get(k):
                    row["err"][f"{k}_c_u"] = float(np.linalg.norm(np.array(est[k]["c"]) - td["c"]) / uu)
            row["true_D_u"] = td["half"] / uu
        elif est.get("ok") is False and tr["device"]:
            row["err"] = None
        tiles = truth_tiles(T, it["geo"])
        if tiles:
            pts = np.array([[t["x"], t["y"]] for t in tiles])
            if est.get("ok"):
                big, fine = zone_frame(pts, est)
            else:  # 기준점을 못 찾으면 구역도 없다 — 그 사진 패는 전부 틀린 것으로 센다
                big, fine = ["none"] * len(tiles), ["none"] * len(tiles)
            row["zones_frame"] = score(tiles, big, fine)
            g = saved_grid(it["geo"])
            if g:
                row["zones_saved"] = score(tiles, zone_grid(pts, g, size))
            if it["geo"][-6:] in T["rect"] and it["set"] == "test":  # 펴기 + 표준 격자(1단계, 색 바꾼 쪽은 펠트를 못 찾아 못 폄 — 표 1-89)
                uv = unrect(pts, T["rect"][it["geo"][-6:]]["quad"], size) * 1000
                row["zones_std"] = score(tiles, zone_grid(uv, saved_grid.std, (1000, 1000)))
        rgb = load_rgb(it["src"]) if it["set"] not in ("rise", "dealt") else None
        row["felt"] = felt_check(rgb, est, rec, tr["felt"]) if it["set"] not in ("rise", "dealt") else {}  # 프레임은 팔·손이 펠트를 가려 정답 사각형으로 못 잼
        rows[it["key"]] = row
    for fr, ph in CARRY:
        if fr not in rows or ph not in rows or not rows[fr]["est"].get("ok"):
            continue
        e = rows[fr]["est"]
        k = cache[ph]["size"][0] / cache[fr]["size"][0]
        est = {"ok": True, "c": (np.array(e["c"]) * k).tolist(), "theta": e["theta"], "u": e["u"] * k, "D": e["D"], "src": "carry:" + fr}
        tr = truth_device(T, ph, cache[ph]["size"])
        td = tr["device"]
        row = {"set": "carry", "geo": ph, "est": est,
               "err": {"c_u": float(np.linalg.norm(np.array(est["c"]) - td["c"]) / est["u"]), "theta_deg": float(abs((math.degrees(est["theta"] - td["theta"]) + 45) % 90 - 45)),
                       "half_ratio": float(est["D"] * est["u"] / td["half"])}}
        tiles = truth_tiles(T, ph)
        pts = np.array([[t["x"], t["y"]] for t in tiles])
        big, fine = zone_frame(pts, est)
        row["zones_frame"] = score(tiles, big, fine)
        row["zones_saved"] = rows[ph]["zones_saved"]
        rows[f"carry/{ph}"] = row
    summ = summarize(rows)
    RES.mkdir(parents=True, exist_ok=True)

    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if isinstance(o, (np.floating, float)):
            return round(float(o), 4)
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.bool_):
            return bool(o)
        return o

    out_p = OUT if not sets else RES / ("wall_frame_" + "_".join(sets) + ".json")
    out_p.write_text(json.dumps(clean({"made": time.strftime("%Y-%m-%d %H:%M"), "params": dict(FELT_W=FELT_W.tolist(), FELT_K=FELT_K, FELT_TOL=FELT_TOL, ROW_BAND=ROW_BAND, RIVER_DEPTH=RIVER_DEPTH, WALL_PER_D=WALL_PER_D, U_BACK=U_BACK, HAND_A=HAND_A, HAND_DEPTH=HAND_DEPTH),
                                      "summary": summ, "rows": rows}), ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(clean(summ), ensure_ascii=False, indent=1))
    print(f"{time.time() - t0:.0f}초 →", out_p)


C_OK, TH_OK = 1.0, 3.0  # 성공: 가운데 오차 ≤ 1u, 방향 오차 ≤ 3°


def summarize(rows: dict) -> dict:
    out = {}
    for st in ["dev", "rise", "dealt", "carry", "test", "recolor", *RC]:
        rs = {k: r for k, r in rows.items() if r["set"] == st}
        if not rs:
            continue
        s = {"n": len(rs), "found": sum(r["est"].get("ok", False) for r in rs.values()),
             "device_found": sum(bool(r["est"].get("device")) for r in rs.values()),
             "wall_found": sum(bool(r["est"].get("wall")) for r in rs.values())}
        withtruth = [r for r in rs.values() if "err" in r]
        if withtruth:
            s["truth_n"] = len(withtruth)
            s["ok"] = sum(1 for r in withtruth if r["err"] and r["err"]["c_u"] <= C_OK and r["err"]["theta_deg"] <= TH_OK)
            for k in ("device", "wall"):
                s[f"{k}_ok"] = sum(1 for r in withtruth if r["err"] and r["err"].get(f"{k}_c_u", 99) <= C_OK and r["err"]["theta_deg"] <= TH_OK)
            errs = [r["err"]["c_u"] for r in withtruth if r["err"]]
            if errs:
                s["c_err_u"] = [float(np.median(errs)), float(np.percentile(errs, 90)), float(max(errs))]
                s["theta_err_deg_max"] = max(r["err"]["theta_deg"] for r in withtruth if r["err"])
        for z in ("zones_frame", "zones_saved", "zones_std"):
            zs = [r[z] for r in rs.values() if z in r]
            if not zs:
                continue
            agg = {"photos": len(zs), "right": sum(x["right"] for x in zs), "wrong": sum(x["wrong"] for x in zs),
                   "photos_wrong": sum(x["wrong"] > 0 for x in zs), "dora_center": sum(x["dora_center"] for x in zs), "dora_n": sum(x["dora_n"] for x in zs)}
            for role in ("hand", "meld", "river", "seatrule"):
                agg[role] = [sum(x[role][0] for x in zs), sum(x[role][1] for x in zs)]
            if z == "zones_frame":
                for k in ("hand_band", "meld_corner", "river_box"):
                    agg[k] = [sum(x["fine"][k][0] for x in zs), sum(x["fine"][k][0] + x["fine"][k][1] for x in zs)]
            s[z] = agg
        for k in ("green", "measured"):
            fs = [r["felt"][k] for r in rs.values() if k in r.get("felt", {})]
            if fs:
                s[f"felt_{k}"] = [sum(f["ok"] for f in fs), len(fs)]
                s[f"felt_{k}_cover85"] = [sum(f["cover"] >= 0.85 for f in fs), len(fs)]  # 테스트 정답 사각형은 앱 findFeltQuad 근사라 샌 비율은 원본 초록도 0.08~0.16
        out[st] = s
    # 색 바꾼 15장·재색칠은 원본과 기하가 같다: 기준점이 원본과 얼마나 같은가(u)
    for st in ["recolor", *RC]:
        d = []
        for k, r in rows.items():
            if r["set"] != st or not r["est"].get("ok"):
                continue
            base = next((b for b in rows.values() if b["set"] in ("dev", "test") and b["geo"] == r["geo"]), None)
            if base and base["est"].get("ok"):
                d.append(float(np.linalg.norm(np.array(r["est"]["c"]) - base["est"]["c"]) / base["est"]["u"]))
        if d and st in out:
            out[st]["same_as_orig_c_u"] = [float(np.median(d)), float(max(d)), sum(x <= C_OK for x in d), len(d)]
    return out


def sheet(res_path: Path, keys: list[str], out: Path, cols: int = 3, tw: int = 680) -> None:
    """기준점·구역을 사진 위에: 기기(자홍)·가운데 칸 R(노랑)·손패 띠(주황)·울기 모서리(빨강)·패산 사각형(하늘)·정답 기기(흰 가는 선),
    정답 패 가운데 점(초록 = 제 구역, 빨강 = 틀린 구역)."""
    d = json.loads(res_path.read_text(encoding="utf-8"))
    its = {it["key"]: it for it in items()}
    T = truth_tables()
    th = tw * 3 // 4
    sh = Image.new("RGB", (cols * tw, ((len(keys) + cols - 1) // cols) * th))
    for i, k in enumerate(keys):
        it, r = its[k], d["rows"][k]
        rgb = load_rgb(it["src"])
        H, W = rgb.shape[:2]
        s = min(tw / W, th / H)
        im = Image.fromarray(rgb).resize((round(W * s), round(H * s)))
        dr = ImageDraw.Draw(im)
        est = r["est"]

        def poly(qs, col, width=2, est=est):
            p = from_frame(np.array(qs), np.array(est["c"]), est["theta"], est["u"]) * s
            dr.polygon([tuple(x) for x in p], outline=col, width=width)

        tr = truth_device(T, it["geo"], (W, H))
        if tr["device"]:
            dr.polygon([tuple(np.array(x) * s) for x in tr["device"]["pts"]], outline=(255, 255, 255), width=1)
        if est.get("ok"):
            D = est["D"]
            R = D + RIVER_DEPTH
            sq = lambda h, cx=0, cy=0: [[cx - h, cy - h], [cx + h, cy - h], [cx + h, cy + h], [cx - h, cy + h]]  # noqa: E731
            poly(sq(D), (255, 0, 255), 3)
            poly(sq(R), (255, 255, 0))
            for k2 in range(4):
                band = [[-HAND_A, R], [HAND_A, R], [HAND_A, R + HAND_DEPTH], [-HAND_A, R + HAND_DEPTH]]
                meld = [[HAND_A, R - 1], [R + HAND_DEPTH, R - 1], [R + HAND_DEPTH, R + HAND_DEPTH], [HAND_A, R + HAND_DEPTH]]
                rotq = lambda qs, k2=k2: [[[a, r], [r, -a], [-a, -r], [-r, a]][k2] for a, r in qs]  # noqa: E731  (a, r) → (x, y)
                poly(rotq(band), (255, 140, 0))
                poly(rotq(meld), (255, 40, 40))
            if est.get("wall"):
                w = est["wall"]
                west = dict(est, c=w["c"])
                poly(sq(w["W"]), (0, 220, 255), 2, west)
        tiles = truth_tiles(T, it["geo"])
        if tiles and est.get("ok"):
            pts = np.array([[t["x"], t["y"]] for t in tiles])
            big, _ = zone_frame(pts, est)
            for t, b in zip(tiles, big):
                if t["role"] == "dora":
                    col = (0, 160, 255)
                else:
                    ok = b == "center" if t["role"] == "river" else b == t["seat"]
                    col = (0, 255, 0) if ok else (255, 0, 0)
                x, y = t["x"] * s, t["y"] * s
                dr.ellipse((x - 3, y - 3, x + 3, y + 3), fill=col)
        e = r.get("err") or {}
        label = f"{k[-22:]} {est.get('src', 'X')} c{e.get('c_u', -1):.2f}u θ{e.get('theta_deg', -1):.1f}"
        dr.rectangle((0, 0, 8 * len(label), 14), fill="black")
        dr.text((2, 1), label, fill="white")
        sh.paste(im, ((i % cols) * tw, (i // cols) * th))
    sh.save(out, quality=82)
    print(out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1]
    if cmd == "det":
        det()
    elif cmd == "sheet":  # sheet <결과 json> <출력 jpg> <key,key,...>
        sheet(Path(sys.argv[2]), sys.argv[4].split(","), Path(sys.argv[3]))
    elif cmd == "run":
        run(sys.argv[2].split(",") if len(sys.argv) > 2 else None)
