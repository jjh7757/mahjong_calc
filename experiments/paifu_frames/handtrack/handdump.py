"""손 관절 시험용 프레임 뽑기(2026-11-20, 사용자 "이 모델로 무슨 행동했는지 유추안되나" → "내장 gpu로 테스트해봐").

SAM 2 추적과 같은 띠(band2) · 같은 시점으로, 원본 초당 10장(SAM 2 는 5장)을 차례 창(plan a_ms ~ e_ms) 동안 잘라 저장.
  python -X utf8 handdump.py r16_d03,r16_d13,r17_d11
→ _work/hands_1120/<id>/frames/NNNNN.jpg · frames.json({i, ms, t, sam2_i}). 손 관절은 venvs/hands 의 handpose.py 가 읽음.
SAM 2 추적(track.json)이 없는 차례(11-20 새 23차례)는 sam2track.plan(tid) 로 같은 창 · 띠를 얻음(sam2_i 는 None).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import sam2track as s1  # noqa: E402

OUT = hc.WORK / "hands_1120"
V1 = argparse.Namespace(model="t", device="xpu")


def wide_of(band2: list, m: int) -> list:
    x0, y0, x1, y1 = band2
    return [max(0, x0 - m), max(0, y0 - m), min(1496, x1 + m), min(1496, y1 + m)]


def source(tid: str, force_plan: bool = False):
    """(plan, SAM 2 프레임 ms → 번호, 길). track.json 이 있으면 그 안의 plan(지금처럼), 없으면(또는 force_plan)
    sam2track.plan(tid) 로 a_ms · e_ms · band2 · side · n 을 얻음(11-20 새 23차례 — SAM 2 추적 없음, sam2_i 는 None)."""
    f = s1.run_dir(tid, V1) / "track.json"
    if f.exists() and not force_plan:
        tr = hc.jload(f)
        return tr["plan"], {ms: i for i, ms in enumerate(tr["frames"])}, "track"
    p = s1.plan(tid)
    if not p.get("ok"):
        raise RuntimeError(f"{tid}: plan 실패 — {p.get('why')}")
    return p, {}, "plan"


def geometry(p: dict, margin: int):
    """(자를 띠, 태그, dx, dy)."""
    band = wide_of(p["band2"], margin) if margin else p["band2"]
    tag = f"_w{margin}" if margin else ""
    ref = (p["band2"][0] + 5, p["band2"][1] + 5)
    a, b = hc.to_view_xy(ref, p["band2"], p["side"]), hc.to_view_xy(ref, band, p["side"])
    dx, dy = a[0] - b[0], a[1] - b[1]
    ref2 = (p["band2"][2] - 7, p["band2"][3] - 9)   # 평행 이동인지 다른 점으로 확인
    a2, b2 = hc.to_view_xy(ref2, p["band2"], p["side"]), hc.to_view_xy(ref2, band, p["side"])
    assert abs(a2[0] - b2[0] - dx) < 1e-6 and abs(a2[1] - b2[1] - dy) < 1e-6, "평행 이동이 아님"
    return band, tag, dx, dy


def dump(tid: str, margin: int = 0):
    """margin > 0 이면 band2 를 사방 margin 화소 넓혀 자름(11-20 "넓혀서 해 줘" — r17 판은 손이 띠 밖에서 들어옴).
    넓힌 그림 좌표 + (dx, dy) = 원래 band2 그림 좌표(같은 방향으로 돌린 자르기라 평행 이동뿐)."""
    p, sam, src = source(tid)
    fs = s1.frame_list(p, 1)
    band, tag, dx, dy = geometry(p, margin)
    d = OUT / tid / f"frames{tag}"
    d.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, ms in enumerate(fs):
        f = d / f"{i:05d}.jpg"
        if not f.exists():
            Image.fromarray(hc.band_crop(hc.load(ms), band, p["side"])).save(f, quality=95)
        rows.append({"i": i, "ms": ms, "t": hc.mss(ms), "sam2_i": sam.get(ms)})
    (OUT / tid / f"frames{tag}.json").write_text(json.dumps({"id": tid, "n": p["n"], "band": band, "band2": p["band2"], "side": p["side"],
                                                             "dx": dx, "dy": dy, "dir": f"frames{tag}", "src": src, "frames": rows}, ensure_ascii=False), encoding="utf-8")
    print(tid, len(fs), "장(초당 10) · 띠", band, f"(band2 + {margin}) · 원래 띠 좌표로 dx {dx} dy {dy} · {src} 길 →", d)


if __name__ == "__main__":
    m = int(sys.argv[sys.argv.index("--margin") + 1]) if "--margin" in sys.argv else 0
    for t in sys.argv[1].split(","):
        dump(t, m)
