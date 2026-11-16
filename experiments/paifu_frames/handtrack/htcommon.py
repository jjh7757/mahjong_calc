"""손패 번호 추적 실험(handtrack) 공통: 녹화 프레임 목록 캐시·시각 변환·프레임 읽기·판 설정 읽기·띠 잘라 돌리기.

녹화: experiments/visit_20261114/head_rec/rec_*/f_<epoch ms>.jpg (1496×1496, 초당 10장).
판 설정(손으로 정한 값): handtrack/config/<판 id>.json — README 참고.
결과: experiments/paifu_frames/results/handtrack/<판 id>/ , 캐시·임시는 results/handtrack/_work/.
"""
from __future__ import annotations

import json
import os
from bisect import bisect_left
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]  # mahjong_calc
EXP = ROOT / "experiments"
REC_ROOT = EXP / "visit_20261114" / "head_rec"
RECS = ["rec_20261114_113107", "rec_20261114_125617"]
OUT = EXP / "paifu_frames" / "results" / "handtrack"
WORK = OUT / "_work"
CONFIG = HERE / "config"
KST = timezone(timedelta(hours=9))
ROT = {"bottom": 0, "left": 90, "top": 180, "right": 270}  # 대국자 시점으로 돌리는 각도(반시계, np.rot90 k = 각도 // 90)
# left 자리(그림 왼쪽에 앉은 사람)는 반시계 90° 돌리면 그림 왼쪽 가장자리가 아래로 와서 그 사람이 그림 아래, 그 사람 왼손 쪽이 그림 왼쪽이 된다.

_FRAMES: dict[str, np.ndarray] = {}


def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def jsave(p, obj, indent=1):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=indent), encoding="utf-8")


def frames(rec: str) -> np.ndarray:
    """녹화 폴더의 프레임 epoch ms 목록(정렬). 처음 한 번 scandir 해 _work/frames_<rec>.json 에 캐시."""
    if rec in _FRAMES:
        return _FRAMES[rec]
    cache = WORK / f"frames_{rec}.json"
    if cache.exists():
        ms = jload(cache)
    else:
        ms = sorted(int(e.name[2:-4]) for e in os.scandir(REC_ROOT / rec) if e.name.startswith("f_") and e.name.endswith(".jpg"))
        jsave(cache, ms, indent=None)
    _FRAMES[rec] = np.array(ms, np.int64)
    return _FRAMES[rec]


def rec_of(ms: int) -> str:
    for rec in RECS:
        f = frames(rec)
        if f[0] - 1000 <= ms <= f[-1] + 1000:
            return rec
    raise KeyError(f"녹화 밖 시각 {ms} ({hms(ms)})")


def to_ms(t: str) -> int:
    """'2026-11-14T15:05:28.200+09:00' 또는 '15:05:28.2'(11-14 KST) → epoch ms."""
    if "T" not in t:
        t = "2026-11-14T" + t
    d = datetime.fromisoformat(t)
    if d.tzinfo is None:
        d = d.replace(tzinfo=KST)
    return int(round(d.timestamp() * 1000))


def hms(ms: int, date: bool = False) -> str:
    d = datetime.fromtimestamp(ms / 1000, KST)
    s = d.strftime("%H:%M:%S") + f".{d.microsecond // 100000}"
    return d.strftime("%Y-%m-%d ") + s if date else s


def mss(ms: int) -> str:
    """그림에 쓰는 짧은 시각 '분:초.0.1초'."""
    d = datetime.fromtimestamp(ms / 1000, KST)
    return d.strftime("%M:%S") + f".{d.microsecond // 100000}"


def frame_range(t0: int, t1: int) -> list[int]:
    rec = rec_of(t0)
    f = frames(rec)
    i, j = bisect_left(f, t0), bisect_left(f, t1 + 1)
    return [int(x) for x in f[i:j]]


def nearest(ms: int) -> int:
    f = frames(rec_of(ms))
    i = min(max(bisect_left(f, ms), 1), len(f) - 1)
    return int(f[i] if abs(f[i] - ms) < abs(f[i - 1] - ms) else f[i - 1])


def path_of(ms: int) -> Path:
    return REC_ROOT / rec_of(ms) / f"f_{ms}.jpg"


def load(ms: int) -> np.ndarray:
    return np.asarray(Image.open(path_of(ms)).convert("RGB"))


def config(gid: str) -> dict:
    return jload(CONFIG / f"{gid}.json")


def out_dir(gid: str) -> Path:
    d = OUT / gid
    d.mkdir(parents=True, exist_ok=True)
    return d


def band_crop(rgb: np.ndarray, band: list, side: str) -> np.ndarray:
    """band = [x0, y0, x1, y1](원본 1496 좌표) 를 잘라 대국자 시점으로 돌린다(화소 그대로, 줄이지 않음)."""
    x0, y0, x1, y1 = band
    c = rgb[y0:y1, x0:x1]
    k = ROT[side] // 90
    return np.ascontiguousarray(np.rot90(c, k))


def to_view_xy(pt, band: list, side: str) -> tuple[float, float]:
    """원본 좌표 점 → band_crop 그림 좌표."""
    x0, y0, x1, y1 = band
    x, y = pt[0] - x0, pt[1] - y0
    w, h = x1 - x0, y1 - y0
    k = ROT[side] // 90 % 4
    for _ in range(k):  # np.rot90 반시계 한 번: (x, y) → (y, w - 1 - x), 크기 (w,h) → (h,w)
        x, y, w, h = y, w - 1 - x, h, w
    return x, y
