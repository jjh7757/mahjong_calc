"""흔들기 회귀 세트(개선 계획 3단계, 2026-11-05, 노트북, API 없음). 변형 목록·세기·물리 근거·격자 처리·지표·고정 기록은 experiments/speed/ROBUST.md.

개발 사진 26장(seat_grow.eval_scenes, B·C·D 무게 2 → /32 회)에 고정 씨드 변형을 입혀 서버 코드 app.roles.read_roles(hybrid, /v2/localroles 와 같은 경로)를
프로세스 안에서 부른다. 모델은 fold(그 사진을 안 배운 조합, experiments/tile_classifier/README.md 끝 절) 또는 prod(서버 assets = 운영).
맞추는 대상이 아니라 안전망이다 — 변형별 결과로 서버 규칙·문턱을 고치지 않는다.
세기 고정(2026-11-05, metrics 표 1-91): BASE 에서 jpeg60 대신 STRONG 의 jpeg35(유일하게 판별력이 없던 묶음) — 고정 세트 21개는 ROBUST.md "고정" 줄. 이후 바꾸지 않는다.
채택 판단(변경마다): 고정 세트 전부에서 unsafe·틀린 자동이 안 늘고 패 단위가 기준 −2% 이내. fold·prod 를 변경 전후 같은 시각에 연달아.

  python -I -X utf8 experiments/speed/robust_suite.py make [--only v1,v2]      → experiments/speed/robust/<변형>/<사진>.jpg, robust/meta.json, robust/felt_in.json
  flutter test tool/robust_felt_grid_test.dart                                 → robust/felt_out.json(회전·felt0 의 앱 펠트 격자)
  python -I -X utf8 experiments/speed/robust_suite.py run --models fold|prod --tag <TAG> [--only ...] [--set dev|field]
                                                                               → experiments/speed/results/robust_<models>_<TAG>.json
  python -I -X utf8 experiments/speed/robust_suite.py report <결과 JSON> [<결과 JSON> ...]   변형별 표(markdown)

--set field: 테스트 15장 편 사진(field_20261024/captures/*/rectified.jpg, 1단계)에 회전·원근을 뺀 같은 변형(make --set field). 채점은 field_bench 와 같은
"자리 정답 = 화료패 뺀 13장"·표준 격자, 모델은 prod(= 테스트 사진의 홀드아웃). 기록만 한다.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import random
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SB = ROOT / "experiments" / "tile_classifier" / "server_bench"
MODELS = SB / "models"
REPO = Path(os.environ.get("RECOGNIZER_REPO", "C:/Users/jjh7757/dev/mahjong-recognizer"))
for p in (HERE, ROOT / "experiments" / "tile_classifier", ROOT / "experiments" / "yolo", SB, REPO):
    sys.path.insert(0, str(p))
import seat_grow as sg  # noqa: E402

RB = HERE / "robust"
RES = HERE / "results"
SEED = 20261105
FIELD = ROOT / "experiments" / "field_20261024" / "captures"

# ---------------------------------------------------------------- 변형 정의(ROBUST.md 표와 같아야 한다)
ROT = {"rot_p3": 3, "rot_m3": -3, "rot_p10": 10, "rot_m10": -10, "rot_p25": 25, "rot_m25": -25}
SCALE = {"scale08": 0.8, "scale06": 0.6}
BLUR = {"blur1": 1.5, "blur2": 3.0}  # σ px, 긴 변 4000 기준
EV = {"ev_p1": 1.0, "ev_m1": -1.0}
WB = {"wb_tung": (1.25, 1.0, 0.62), "wb_fluo": (0.90, 1.10, 0.95)}  # 선형 RGB 배율(휘도 보존으로 정규화)
JPEG = {"jpeg60": 60}
HAND = {"hand": (1, 2)}  # 타원 개수 범위
RECOLOR = {"rc_gray": ("felt", (175, 175, 175)), "rc_dgreen": ("felt", (30, 80, 35)), "rc_redframe": ("frame", (20, 20, 225))}  # BGR
# 세기 고정 규칙(ROBUST.md): 묶음 전체가 추가 실패 0 이면 아래 한 단계 센 수준을 한 번만 더한다. --strong 으로 만들고 돌린다.
STRONG = {"rot_p35": ("rot", 35), "rot_m35": ("rot", -35), "scale045": ("scale", 0.45), "blur3": ("blur", 5.0), "ev_p15": ("ev", 1.5), "ev_m15": ("ev", -1.5),
          "wb_tung2": ("wb", (1.45, 1.0, 0.45)), "wb_fluo2": ("wb", (0.85, 1.18, 0.90)), "jpeg35": ("jpeg", 35), "hand2": ("hand", (3, 4))}
GEOM = set(ROT) | {k for k, v in STRONG.items() if v[0] == "rot"}
FELT_GRID = GEOM | {"felt0"}  # 앱 펠트 격자로 다시 잡는 변형
BASE = ["orig", "felt0", *ROT, *SCALE, *BLUR, *EV, *WB, *JPEG, *HAND, *RECOLOR]
FIXED = [("jpeg35" if v == "jpeg60" else v) for v in BASE]  # 고정 세트(2026-11-05, 표 1-91): jpeg60 → jpeg35, 나머지 첫 세기
GROUP = {**{k: "회전" for k in ROT}, **{k: "축소" for k in SCALE}, **{k: "흐림" for k in BLUR}, **{k: "노출" for k in EV}, **{k: "화이트밸런스" for k in WB},
         **{k: "JPEG" for k in JPEG}, **{k: "가림" for k in HAND}, **{k: "재색칠" for k in RECOLOR}, "orig": "기준", "felt0": "대조",
         **{k: {"rot": "회전", "scale": "축소", "blur": "흐림", "ev": "노출", "wb": "화이트밸런스", "jpeg": "JPEG", "hand": "가림"}[v[0]] for k, v in STRONG.items()}}

# 피해야 하는 색(BGR): 테스트 세트(make_recolor_test.py) + 8회차 학습 재색칠 팔레트(det_build_fb.py BACKS·FELTS·FRAMES)
TEST_COLORS = [(25, 25, 25), (140, 70, 30), (40, 170, 240)]
MIN_COLOR_DIST = 45


def check_colors() -> None:
    import det_build_fb as fb

    used = [c for c in fb.BACKS + fb.FELTS + fb.FRAMES if c is not None] + TEST_COLORS
    for k, (_, c) in RECOLOR.items():
        d = min(math.dist(c, u) for u in used)
        if d < MIN_COLOR_DIST:
            raise SystemExit(f"{k} 색 {c} 이 학습·테스트 색과 가깝다(거리 {d:.0f})")
        print(f"{k} {c} 가장 가까운 학습·테스트 색까지 {d:.0f}")


# ---------------------------------------------------------------- 사진 변형
def load_rgb(path: Path) -> np.ndarray:
    return np.asarray(ImageOps.exif_transpose(Image.open(path)).convert("RGB"))


def save(rgb: np.ndarray, path: Path, q: int = 95) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb).save(path, "JPEG", quality=q)


def to_lin(rgb: np.ndarray) -> np.ndarray:
    c = rgb.astype(np.float32) / 255
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(lin: np.ndarray) -> np.ndarray:
    c = np.clip(lin, 0, 1)
    s = np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)
    return np.clip(np.round(s * 255), 0, 255).astype(np.uint8)


def ev(rgb: np.ndarray, k: float) -> np.ndarray:
    return to_srgb(to_lin(rgb) * (2.0 ** k))


def wb(rgb: np.ndarray, gains) -> np.ndarray:
    g = np.array(gains, np.float32)
    g = g / float(np.dot(g, [0.2126, 0.7152, 0.0722]))  # 흰색 휘도 보존
    return to_srgb(to_lin(rgb) * g)


def blur(rgb: np.ndarray, sigma4000: float) -> np.ndarray:
    s = sigma4000 * max(rgb.shape[:2]) / 4000
    return cv2.GaussianBlur(rgb, (0, 0), s)


def scale(rgb: np.ndarray, f: float) -> np.ndarray:
    h, w = rgb.shape[:2]
    return cv2.resize(rgb, (round(w * f), round(h * f)), interpolation=cv2.INTER_AREA)


def rotate(rgb: np.ndarray, deg: float) -> tuple[np.ndarray, np.ndarray]:
    """시계 방향 +deg 회전, 캔버스를 넓혀 내용을 잃지 않음(빈 곳 114). (그림, 원래 px → 새 px 2×3 행렬)."""
    h, w = rgb.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), -deg, 1.0)  # cv2 는 + 가 반시계
    c, s = abs(M[0, 0]), abs(M[0, 1])
    W, H = int(math.ceil(w * c + h * s)), int(math.ceil(w * s + h * c))
    M[0, 2] += W / 2 - w / 2
    M[1, 2] += H / 2 - h / 2
    return cv2.warpAffine(rgb, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(114, 114, 114)), M


def move_grid(g: dict, M: np.ndarray, src: tuple[int, int], dst: tuple[int, int]) -> dict:
    """(a) 변환 행렬로 저장 격자 네 꼭짓점과 리치봉 상자를 옮겨 감싸는 축 상자로."""
    w, h = src
    W, H = dst

    def aabb(xs, ys):
        pts = np.array([[x * w / 1000, y * h / 1000, 1] for x, y in zip(xs, ys)], np.float64) @ M.T
        return pts[:, 0] * 1000 / W, pts[:, 1] * 1000 / H

    px, py = aabb([g["x1"], g["x2"], g["x2"], g["x1"]], [g["y1"], g["y1"], g["y2"], g["y2"]])
    out = {"x1": int(round(px.min())), "x2": int(round(px.max())), "y1": int(round(py.min())), "y2": int(round(py.max()))}
    if g.get("sticks"):
        y0, x0, y1, x1 = g["sticks"]
        sx, sy = aabb([x0, x1, x1, x0], [y0, y0, y1, y1])
        out["sticks"] = [int(round(sy.min())), int(round(sx.min())), int(round(sy.max())), int(round(sx.max()))]
    for k in ("x1", "x2", "y1", "y2"):
        out[k] = min(999, max(1, out[k]))
    return out


def hands(rgb: np.ndarray, g: dict, side: str, n_range, rng: random.Random) -> tuple[np.ndarray, list]:
    """살색 타원 1~2개(n_range), 화료자 자리 크롭(roles.seat_box) 밖에만. 반지름 = 안쪽 칸 폭의 0.11 × 0.21."""
    from app import roles

    h, w = rgb.shape[:2]
    ymin, xmin, ymax, xmax = roles.seat_box(g, side)
    sx0, sy0, sx1, sy1 = xmin * w / 1000, ymin * h / 1000, xmax * w / 1000, ymax * h / 1000
    inner = (g["x2"] - g["x1"]) * w / 1000
    ax, ay = 0.11 * inner, 0.21 * inner
    cx0, cx1 = max(0, g["x1"] * w / 1000 - 0.35 * inner), min(w, g["x2"] * w / 1000 + 0.35 * inner)
    cy0, cy1 = max(0, g["y1"] * h / 1000 - 0.35 * inner), min(h, g["y2"] * h / 1000 + 0.35 * inner)
    out = rgb.copy()
    placed = []
    for _ in range(rng.randint(*n_range)):
        for _try in range(300):
            cx, cy, ang = rng.uniform(cx0, cx1), rng.uniform(cy0, cy1), rng.uniform(0, 180)
            poly = cv2.ellipse2Poly((int(cx), int(cy)), (int(ax), int(ay)), int(ang), 0, 360, 10)
            bx0, by0 = poly.min(axis=0)
            bx1, by1 = poly.max(axis=0)
            pad = 0.01 * w
            if bx1 < sx0 - pad or bx0 > sx1 + pad or by1 < sy0 - pad or by0 > sy1 + pad:
                break
        else:
            continue
        # 타원 둘레 상자 안에서만 섞는다(사진 전체 배열을 안 만듦)
        pad = int(0.3 * ax) + 2
        X0, Y0 = max(0, int(bx0) - pad), max(0, int(by0) - pad)
        X1, Y1 = min(w, int(bx1) + pad), min(h, int(by1) + pad)
        if X1 <= X0 or Y1 <= Y0:
            continue
        m = np.zeros((Y1 - Y0, X1 - X0), np.uint8)
        cv2.fillPoly(m, [poly - [X0, Y0]], 255)
        a = cv2.GaussianBlur(m, (0, 0), 0.08 * ax).astype(np.float32)[..., None] / 255
        base = np.array([215, 170, 140], np.float32) + rng.uniform(-15, 15)
        yy, xx = np.mgrid[Y0:Y1, X0:X1]
        t = np.cos(math.radians(ang)) * (xx - cx) + np.sin(math.radians(ang)) * (yy - cy)
        shade = (1.0 - 0.18 * np.clip(np.abs(t) / ax, 0, 1))[..., None]  # 가운데가 밝고 가장자리가 어두운 그늘
        part = out[Y0:Y1, X0:X1].astype(np.float32)
        out[Y0:Y1, X0:X1] = (part * (1 - a) + base * shade * a).astype(np.uint8)
        placed.append([round(cx), round(cy), round(ax), round(ay), round(ang)])
    return out, placed


_det = None


def recolor_masks(bgr: np.ndarray) -> dict:
    """make_recolor_test.py 와 같은 마스크: 펠트(최대 덩어리 껍질 안 펠트색), 테두리(껍질 1.2%~14% 바깥 흰 띠, 패 상자 +8px 뺌)."""
    global _det
    from det_backs import felt_mask

    if _det is None:
        from ultralytics import YOLO

        _det = YOLO(str(ROOT / "experiments" / "tile_classifier" / "data" / "det" / "kaggle_out_fb2" / "out" / "final.pt"))

    def ring(hull, grow):
        c = hull.mean(axis=0)
        m = np.zeros(bgr.shape[:2], np.uint8)
        cv2.fillPoly(m, [np.round(c + (hull - c) * (1 + grow)).astype(np.int32)], 255)
        return m

    fm = felt_mask(bgr)
    n, lab, st, _ = cv2.connectedComponentsWithStats(fm)
    big = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    pts = np.column_stack(np.nonzero(lab == big))[:, ::-1].astype(np.float32)
    hull = cv2.convexHull(pts).reshape(-1, 2)
    felt = cv2.bitwise_and(fm, ring(hull, 0.0))
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    white = ((hsv[..., 1] < 55) & (hsv[..., 2] > 120)).astype(np.uint8) * 255
    frame = cv2.bitwise_and(white, cv2.bitwise_and(ring(hull, 0.14), cv2.bitwise_not(ring(hull, 0.012))))
    r = _det.predict(bgr, imgsz=1280, conf=0.25, verbose=False, device="cpu")[0]
    for x0, y0, x1, y1 in r.boxes.xyxy.tolist():
        frame[max(0, int(y0) - 8):int(y1) + 8, max(0, int(x0) - 8):int(x1) + 8] = 0
    return {"felt": felt, "frame": frame}


def recolor(rgb: np.ndarray, masks: dict, part: str, bgr_color) -> tuple[np.ndarray, float]:
    import det_build_fb as fb

    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    fb.repaint(lab, masks[part], bgr_color)
    out = cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2BGR)
    return cv2.cvtColor(out, cv2.COLOR_BGR2RGB), float((masks[part] > 127).mean())


def spec_of(v: str):
    if v in STRONG:
        return STRONG[v]
    for kind, table in (("rot", ROT), ("scale", SCALE), ("blur", BLUR), ("ev", EV), ("wb", WB), ("jpeg", JPEG), ("hand", HAND), ("recolor", RECOLOR)):
        if v in table:
            return kind, table[v]
    return v, None  # orig·felt0


# ---------------------------------------------------------------- 장면
def field_scenes() -> list[dict]:
    """테스트 15장 편 사진(1단계 rectified.jpg + 표준 격자, 없으면 원본 + 장면 격자). 정답은 field_bench 자리 채점(화료패 뺀 13장)."""
    import field_bench as fbn

    T, out = fbn.truth(), []
    for scene, (photos, scene_grid) in fbn.SCENES.items():
        t = T[scene]
        for ph in photos:
            folder = FIELD / f"20261024_{ph}"
            rect = folder / "rectified.jpg"
            path, grid = (rect, dict(fbn.STANDARD)) if rect.exists() else (folder / "original.jpg", dict(scene_grid))
            out.append(dict(name=f"20261024_{ph}", scene=scene, path=path, side=t["side"], grid=grid, hand=t["seat"], melds=t["melds"], w=1))
    return out


def scenes(which: str) -> list[dict]:
    if which == "field":
        return field_scenes()
    return [dict(s, w=1 if s["name"].startswith("2026") else 2) for s in sg.eval_scenes()]


def make(a) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    check_colors()
    names = [*FIXED, *([v for v in [*BASE, *STRONG] if v not in FIXED] if a.strong else [])]  # --strong: 기록용 jpeg60·센 수준까지
    if a.only:
        names = [v for v in names if v in a.only.split(",")]
    if a.set == "field":
        names = [v for v in names if v not in FELT_GRID]
    root = RB if a.set == "dev" else RB / "field"
    meta_p = root / "meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    felt_in = []
    for s in scenes(a.set):
        rgb = load_rgb(Path(s["path"]))
        h, w = rgb.shape[:2]
        masks = None
        for v in names:
            kind, arg = spec_of(v)
            rng = random.Random(f"{SEED}/{v}/{s['name']}")
            info: dict = {"size": [w, h]}
            dst = root / v / f"{s['name']}.jpg"
            if kind == "orig":
                info["src"] = str(s["path"])  # 원본 파일 그대로(다시 저장 안 함)
            elif kind == "felt0":
                info["src"] = str(s["path"])
            else:
                q = 95
                if kind == "rot":
                    out, M = rotate(rgb, arg)
                    info["grid_a"] = move_grid(s["grid"], M, (w, h), (out.shape[1], out.shape[0]))
                elif kind == "scale":
                    out = scale(rgb, arg)
                elif kind == "blur":
                    out = blur(rgb, arg)
                elif kind == "ev":
                    out = ev(rgb, arg)
                elif kind == "wb":
                    out = wb(rgb, arg)
                elif kind == "jpeg":
                    out, q = rgb, arg
                elif kind == "hand":
                    out, info["hands"] = hands(rgb, s["grid"], s["side"], arg, rng)
                elif kind == "recolor":
                    if masks is None:
                        masks = recolor_masks(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
                    out, info["mask_share"] = recolor(rgb, masks, *arg)
                else:
                    raise ValueError(v)
                save(out, dst, q)
                info["src"] = str(dst)
                info["size_out"] = [out.shape[1], out.shape[0]]
            if v in FELT_GRID:
                felt_in.append({"key": f"{v}/{s['name']}", "path": info["src"]})
            meta.setdefault(v, {})[s["name"]] = info
        print(s["name"], flush=True)
    meta_p.parent.mkdir(parents=True, exist_ok=True)
    meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    if felt_in:
        fi = root / "felt_in.json"
        old = json.loads(fi.read_text(encoding="utf-8")) if fi.exists() else []
        keys = {r["key"] for r in felt_in}
        fi.write_text(json.dumps([r for r in old if r["key"] not in keys] + felt_in, ensure_ascii=False, indent=1), encoding="utf-8")
    sheets(root, names, scenes(a.set))


def sheets(root: Path, names: list[str], ss: list[dict]) -> None:
    """확인 그림: 변형마다 사진 4장 썸네일(sheet_<변형>.jpg)."""
    pick = ss[:: max(1, len(ss) // 4)][:4]
    for v in names:
        if v in ("orig", "felt0"):
            continue
        th = []
        for s in pick:
            p = root / v / f"{s['name']}.jpg"
            if p.exists():
                im = Image.open(p).convert("RGB")
                im.thumbnail((640, 640))
                th.append(np.asarray(im.resize((640, 480))))
        if th:
            Image.fromarray(np.hstack(th)).save(root / f"sheet_{v}.jpg", quality=80)


# ---------------------------------------------------------------- 채점
FOLD_ROLE = {"bcd": "tile-roles-rot.onnx", "am": "tile-roles-rot_fold_am.onnx", "pmA": "tile-roles-rot_fold_pmA.onnx", "pmB": "tile-roles-rot_fold_pmB.onnx"}


def fold_of(name: str, meta: dict) -> tuple[str, str, str]:
    """(검출기 나눔 a|b, 분류기 나눔 bcd|am|pm, 역할 나눔 bcd|am|pmA|pmB) — README 끝 절 대응표."""
    p = next(x for x in meta["photos"] if x["name"] == name)
    if p["part"] == "bcd":
        role = "bcd"
    elif p["part"] == "am":
        role = "am"
    else:
        role = "pmB" if name >= "20261031_171245" else "pmA"
    return p["det"], p["part"], role


class Readers:
    def __init__(self, models: str, threads: int):
        from app import local_read as lr
        from app import roles

        self.lr, self.roles, self.models, self.threads = lr, roles, models, threads
        self.meta = json.loads((SB / "meta.json").read_text(encoding="utf-8"))
        self.cache: dict = {}

    def get(self, name: str):
        lr, roles = self.lr, self.roles
        if self.models == "prod" or not name.startswith(("k", "2026103")):
            key = ("prod",)
            if key not in self.cache:
                self.cache[key] = (lr.LocalReader(threads=self.threads), roles.RoleNet(roles.ROLE_MODEL, threads=self.threads))
            return self.cache[key], {"det": lr.DET_MODEL.name, "seat": lr.SEAT_MODEL.name, "cls": lr.CLS_MODEL.name, "role": roles.ROLE_MODEL.name}
        det, part, role = fold_of(name, self.meta)
        key = (det, part, role)
        files = {"det": f"det_fold_{det}.onnx", "seat": f"det_r8_fold_{det}.onnx", "cls": f"cls_{part}.onnx", "role": FOLD_ROLE[role]}
        if key not in self.cache:
            role_path = MODELS / files["role"] if "_fold_" in files["role"] else REPO / "app" / "assets" / files["role"]
            for f in (MODELS / files["det"], MODELS / files["seat"], MODELS / files["cls"], role_path):
                if not f.exists():
                    raise SystemExit(f"모델 없음: {f} — experiments/tile_classifier/README.md 끝 절 명령으로 다시 만든다")
            self.cache[key] = (lr.LocalReader(threads=self.threads, det_model=MODELS / files["det"], cls_model=MODELS / files["cls"], seat_model=MODELS / files["seat"]),
                               roles.RoleNet(role_path, threads=self.threads))
        return self.cache[key], files


def meld_tiles(ms: list[str]) -> list[str]:
    return [t for m in ms for t in m.split()]


def judge(hand: list[str], melds: list[str], block: bool, want_hand: list[str], want_melds: list[str]) -> dict:
    import hybrid as hy

    key = lambda ms: sorted(" ".join(sorted(m.split())) for m in ms)
    ok = bool(hand) and sorted(hand) == sorted(want_hand) and key(melds) == key(want_melds)
    passed = bool(hand) and hy.check(hand, [m.split() for m in melds])[0]
    have, want = Counter(hand + meld_tiles(melds)), Counter(want_hand + meld_tiles(want_melds))
    return {"ok": ok, "check": passed, "unsafe": passed and not ok, "bad_auto": passed and not ok and not block,
            "hit": sum((have & want).values()), "want": sum(want.values())}


def felt_grids(root: Path) -> dict:
    p = root / "felt_out.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def run(a) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    from app.recognizer import prepare_image

    root = RB if a.set == "dev" else RB / "field"
    meta = json.loads((root / "meta.json").read_text(encoding="utf-8"))
    felt = felt_grids(root)
    names = [v for v in ([*BASE, *STRONG] if a.only else FIXED) if v in meta]  # 기본은 고정 세트만
    if a.only:
        names = [v for v in names if v in a.only.split(",")]
    rd = Readers(a.models, a.threads)
    out_p = RES / f"robust_{a.models}{'_field' if a.set == 'field' else ''}_{a.tag}.json"
    res = json.loads(out_p.read_text(encoding="utf-8")) if out_p.exists() and a.resume else {}
    res.setdefault("_meta", {"models": a.models, "set": a.set, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "recognizer": git_sha()})
    ss = scenes(a.set)
    t_all = time.perf_counter()
    for v in names:
        if v in res and len(res[v]) == len(ss):
            continue
        rows = {}
        for s in ss:
            info = meta[v].get(s["name"])
            if info is None:
                continue
            grid, src = s["grid"], "saved"
            if v in FELT_GRID:
                fg = felt.get(f"{v}/{s['name']}")
                if fg and fg.get("grid"):
                    g = fg["grid"]
                    grid, src = {"x1": g["x1"], "x2": g["x2"], "y1": g["y1"], "y2": g["y2"]}, "felt"
                    if g.get("sticks"):
                        sk = g["sticks"]
                        grid["sticks"] = [sk["ymin"], sk["xmin"], sk["ymax"], sk["xmax"]] if isinstance(sk, dict) else list(sk)
                elif "grid_a" in info:
                    grid, src = info["grid_a"], "a"
                else:
                    src = "saved"  # felt0 에서 펠트를 못 찾음 → 저장 격자
            (reader, net), files = rd.get(s["name"])
            t0 = time.perf_counter()
            jpeg = prepare_image(Path(info["src"]).read_bytes(), 4080)
            try:
                o = rd.roles.read_roles(reader, jpeg, s["side"], grid, "hybrid", net=net)
                err = None
            except Exception as e:  # noqa: BLE001 — 한 장 실패가 전체를 멈추지 않게
                o, err = {"tiles": [], "separate_tile": None, "melds": [], "framed": False}, f"{type(e).__name__}: {e}"
            secs = time.perf_counter() - t0
            hand = [t["tile"] for t in o["tiles"]] + ([o["separate_tile"]["tile"]] if o.get("separate_tile") else [])
            melds = [" ".join(m["tiles"]) for m in o["melds"]]
            j = judge(hand, melds, o.get("block", False), s["hand"], s["melds"])
            rows[s["name"]] = dict(w=s["w"], hand=hand, melds=melds, block=o.get("block", False), framed=o.get("framed"), grid=grid, grid_src=src,
                                   s=round(secs, 2), err=err, models=files, **j)
            print(f"{v:12s} {s['name'][-6:]:>6s} {'O' if j['ok'] else 'X'}{' UNSAFE' if j['unsafe'] else ''}{' 자동틀림' if j['bad_auto'] else ''} "
                  f"{j['hit']}/{j['want']} {src} {secs:.1f}s {' '.join(hand)} {melds}{' ' + err if err else ''}", flush=True)
        res[v] = rows
        out_p.parent.mkdir(parents=True, exist_ok=True)
        res["_meta"]["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
        out_p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"--- {v}: {summary(rows)}", flush=True)
    print(f"끝 {time.perf_counter() - t_all:.0f}s → {out_p}")


def git_sha() -> str:
    import subprocess

    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        return "?"


def summary(rows: dict) -> dict:
    t = Counter()
    for r in rows.values():
        w = r["w"]
        t["n"] += w
        t["ok"] += w * r["ok"]
        t["hit"] += w * r["hit"]
        t["want"] += w * r["want"]
        t["unsafe"] += w * r["unsafe"]
        t["bad_auto"] += w * r["bad_auto"]
        t["err"] += w * bool(r.get("err"))
        t[f"grid_{r['grid_src']}"] += w
    return dict(t)


# ---------------------------------------------------------------- 표
def scene_major(rows: dict) -> int:
    """테스트 15장 장면 단위(2단계에서 고정한 정의: 장면의 사진 과반이 맞으면 1, /5)."""
    import field_bench as fbn

    n = 0
    for photos, _ in fbn.SCENES.values():
        hit = sum(bool(rows.get(f"20261024_{ph}", {}).get("ok")) for ph in photos)
        n += hit * 2 > len(photos)
    return n


def report(a) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    for path in a.files:
        res = json.loads(Path(path).read_text(encoding="utf-8"))
        m = res.get("_meta", {})
        print(f"\n### {Path(path).name} — 모델 {m.get('models')} · {m.get('set')} · 서버 {m.get('recognizer')} · {m.get('started')} ~ {m.get('finished')}\n")
        base = res.get("orig", {})
        ctrl = res.get("felt0", {})
        print("| 변형 | 묶음 | 장면 맞음 | 패 단위 | unsafe | 틀린 자동 | 기준 대비 새 실패 | 격자 | 판독 초(중앙) |")
        print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for v in [*BASE, *STRONG]:
            rows = res.get(v)
            if not rows:
                continue
            t = summary(rows)
            ref = ctrl if v in GEOM and ctrl else base
            new_fail = sum(r["w"] for k, r in rows.items() if k in ref and ref[k]["ok"] and not r["ok"])
            fixed = sum(r["w"] for k, r in rows.items() if k in ref and not ref[k]["ok"] and r["ok"])
            gs = ", ".join(f"{k[5:]} {n}" for k, n in sorted(t.items()) if k.startswith("grid_"))
            secs = sorted(r["s"] for r in rows.values())
            pct = 100 * t["hit"] / max(1, t["want"])
            sc = f" · 장면 {scene_major(rows)}/5" if m.get("set") == "field" else ""
            print(f"| `{v}` | {GROUP.get(v, '')} | {t['ok']}/{t['n']}{sc} | {t['hit']}/{t['want']} ({pct:.1f}%) | {t['unsafe']} | {t['bad_auto']} | "
                  f"{new_fail}{f' (+고침 {fixed})' if fixed else ''}{' ※felt0 대비' if v in GEOM else ''} | {gs} | {secs[len(secs) // 2]:.1f} |")
        if a.detail:
            for v in [*BASE, *STRONG]:
                for k, r in (res.get(v) or {}).items():
                    if not r["ok"]:
                        print(f"  {v} {k} {'UNSAFE' if r['unsafe'] else ''} {'자동틀림' if r['bad_auto'] else ''} {r['hit']}/{r['want']} {' '.join(r['hand'])} {r['melds']} {r['grid_src']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("--only", default="")
    m.add_argument("--strong", action="store_true", help="한 단계 센 수준(STRONG)도 만든다 — ROBUST.md 세기 조정 규칙대로 한 번만")
    m.add_argument("--set", default="dev", choices=["dev", "field"])
    r = sub.add_parser("run")
    r.add_argument("--models", required=True, choices=["fold", "prod"])
    r.add_argument("--tag", required=True)
    r.add_argument("--only", default="")
    r.add_argument("--threads", type=int, default=2)
    r.add_argument("--resume", action="store_true", help="같은 결과 JSON 에 이미 있는 변형은 건너뜀")
    r.add_argument("--set", default="dev", choices=["dev", "field"])
    p = sub.add_parser("report")
    p.add_argument("files", nargs="+")
    p.add_argument("--detail", action="store_true")
    a = ap.parse_args()
    {"make": make, "run": run, "report": report}[a.cmd](a)


if __name__ == "__main__":
    main()
