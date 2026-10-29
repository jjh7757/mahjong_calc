"""거치 설치 때 한 번만: Gemini 가 전경 사진에서 작탁 바깥 끝 네 모서리와 격자 선 4개를 주면 얼마나 정확한가(사용자 제안 10-29).

  python -I -X utf8 experiments/rectify/gemini_grid.py [--runs 3]       → results/gemini_grid.json, 그림 results/gemini_grid/
  python -I -X utf8 experiments/rectify/gemini_grid.py --show

정답: 손으로 맞춘 격자(read_grid_timing_test.dart 의 B·C·D 격자). 작탁 모서리는 정답이 없어 그림으로만 본다.
기능 확인: Gemini 격자로 화료자 자리를 앱과 같게 잘라(그 사람 방향으로 세움) 서버 자리 틀(seat.frame, 나눔 포함)이
손패·울기·따로 놓인 패(C 는 도라 표시패 2장)를 맞게 잡는지 — 손 격자도 같이.
조건: low = thinking low + 기본 해상도(서버 판독과 같음) / high = thinking 기본 + ULTRA_HIGH(설치 때 한 번이라 최대로).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import statistics
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

sys.path.insert(0, "C:/Users/jjh7757/dev/mahjong-recognizer")
from app import river as rv  # noqa: E402
from app import seat  # noqa: E402

HERE = Path(__file__).parent
PHOTOS = HERE.parent / "field_20261024" / "kakao_photos"
OUT = HERE / "results" / "gemini_grid.json"
FIG = HERE / "results" / "gemini_grid"
# 손으로 맞춘 격자(정답)와 화료자 자리·정답 틀(손패, 울기 묶음 수, 따로 놓인 패 수).
SCENES = {
    "B": (["k25", "k28"], {"x1": 272, "x2": 735, "y1": 137, "y2": 727}, "right", (10, 1, 0)),
    "C": (["k15", "k26"], {"x1": 320, "x2": 760, "y1": 142, "y2": 717}, "left", (13, 0, 2)),
    "D": (["k12", "k16"], {"x1": 280, "x2": 745, "y1": 173, "y2": 713}, "bottom", (10, 1, 0)),
}
ROT_CW = {"bottom": 0, "right": 90, "top": 180, "left": 270}

PROMPT = """이 사진은 리치마작 자동탁을 위에서 내려다본 전경입니다. 패 종류는 읽지 말고 **위치만** 찾습니다.
좌표는 [y, x] 로, 이미지 높이·너비를 각각 1000 으로 본 정수입니다(왼쪽 위가 [0, 0]).

찾을 것:
- table_corners: 작탁(마작 테이블) 상판의 **바깥 끝** 네 모서리 — 초록 펠트가 아니라 펠트를 둘러싼 흰(또는 다른 색) 테두리의
  바깥 끝입니다. 바닥·의자·벽·사람은 밖입니다. 모서리가 둥글면 두 변을 이은 선이 만나는 점. 사진 밖으로 나갔으면 사진 끝 값.
  top_left·top_right·bottom_right·bottom_left 는 사진 기준입니다.
- grid: 사진을 다섯 구역으로 나눌 선 4개. 가로선 2개(top_y, bottom_y)와 세로선 2개(left_x, right_x), 모두 이미지 축에 평행.
  - 아래 자리 구역 = bottom_y 아래, 위 자리 = top_y 위, 왼쪽 자리 = left_x 왼쪽, 오른쪽 자리 = right_x 오른쪽, 가운데 = 네 선 안.
  - 각 자리 구역에는 그 플레이어의 손패 줄 전체, 울기 묶음, 손패 옆에 따로 놓인 앞면 패(도라 표시패 등)가 **통째로** 들어가야 합니다.
  - 가운데 구역에는 네 플레이어의 버림패 줄(강)과 가운데 기기가 들어가야 합니다.
  - 선이 어떤 패도 가로지르지 않게, 손패 쪽 패와 강 쪽 패 사이의 빈 펠트 한가운데에 둡니다. 패산(뒷면 벽패 줄)은 어느 쪽이든 괜찮습니다.
- notes: 판단이 애매했던 곳(짧게)."""

PT = {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2}
SCHEMA = {
    "type": "object",
    "properties": {
        "table_corners": {"type": "object", "properties": {k: PT for k in ("top_left", "top_right", "bottom_right", "bottom_left")},
                          "required": ["top_left", "top_right", "bottom_right", "bottom_left"]},
        "grid": {"type": "object", "properties": {k: {"type": "integer"} for k in ("left_x", "right_x", "top_y", "bottom_y")},
                 "required": ["left_x", "right_x", "top_y", "bottom_y"]},
        "notes": {"type": "string"},
    },
    "required": ["table_corners", "grid"],
}
CONDS = {"low": ("low", None), "high": ("default", "MEDIA_RESOLUTION_ULTRA_HIGH")}


def photo_rgb(p: str) -> np.ndarray:
    return np.asarray(ImageOps.exif_transpose(Image.open(PHOTOS / f"{p}.jpg")).convert("RGB"))


def jpeg_of(rgb: np.ndarray, long_side: int = 3072) -> bytes:
    im = Image.fromarray(rgb)
    im.thumbnail((long_side, long_side), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def seat_box(g: dict, side: str) -> tuple[int, int, int, int]:
    """GridZones.seat 와 같은 (ymin, xmin, ymax, xmax)."""
    return {"bottom": (g["y2"], g["x1"], 1000, 1000), "right": (0, g["x2"], g["y2"], 1000),
            "top": (0, 0, g["y1"], g["x2"]), "left": (g["y1"], 0, 1000, g["x1"])}[side]


def hand_frac(g: dict, side: str) -> float:
    return {"bottom": (g["x2"] - g["x1"]) / (1000 - g["x1"]), "right": (g["y2"] - g["y1"]) / g["y2"],
            "top": (g["x2"] - g["x1"]) / g["x2"], "left": (g["y2"] - g["y1"]) / (1000 - g["y1"])}[side]


def seat_crop(rgb: np.ndarray, g: dict, side: str) -> np.ndarray:
    H, W = rgb.shape[:2]
    y0, x0, y1, x1 = seat_box(g, side)
    im = Image.fromarray(rgb[y0 * H // 1000:-(-y1 * H // 1000), x0 * W // 1000:-(-x1 * W // 1000)])
    return np.asarray(im.rotate(-ROT_CW[side], expand=True))


def frame_check(det, rgb: np.ndarray, g: dict, side: str, truth: tuple[int, int, int]) -> dict:
    if not (0 < g["x1"] < g["x2"] < 1000 and 0 < g["y1"] < g["y2"] < 1000):
        return {"ok": False, "why": "선 순서가 틀림"}
    crop = seat_crop(rgb, g, side)
    fr = seat.frame(crop, det, hand_frac=hand_frac(g, side))
    if fr is None:
        return {"ok": False, "why": "틀 없음"}
    got = (len(fr.hand) + (1 if fr.separate else 0), len(fr.melds), len(fr.loose))
    return {"ok": got == truth, "got": got, "split": fr.split}


def ask(r, jpeg: bytes, cond: str) -> dict:
    thinking, res = CONDS[cond]
    t0 = time.perf_counter()
    c = r.call(jpeg, PROMPT, SCHEMA, thinking=thinking, media_resolution=res)
    d = c.data
    g = d["grid"]
    return {"grid": {"x1": g["left_x"], "x2": g["right_x"], "y1": g["top_y"], "y2": g["bottom_y"]},
            "corners": d["table_corners"], "notes": d.get("notes", ""), "s": round(time.perf_counter() - t0, 1),
            "in": c.input_tokens, "out": c.output_tokens}


def draw(rgb: np.ndarray, truth: dict, rows: list[dict], path: Path) -> None:
    im = Image.fromarray(rgb).copy()
    im.thumbnail((1400, 1400))
    w, h = im.size
    d = ImageDraw.Draw(im)

    def lines(g, col, width):
        for k in ("x1", "x2"):
            d.line([g[k] * w / 1000, 0, g[k] * w / 1000, h], fill=col, width=width)
        for k in ("y1", "y2"):
            d.line([0, g[k] * h / 1000, w, g[k] * h / 1000], fill=col, width=width)

    lines(truth, (0, 140, 255), 5)  # 손 격자
    for r in rows:
        lines(r["grid"], (255, 60, 60) if r["cond"] == "high" else (255, 200, 0), 2)
        c = r["corners"]
        pts = [(c[k][1] * w / 1000, c[k][0] * h / 1000) for k in ("top_left", "top_right", "bottom_right", "bottom_left")]
        d.line(pts + [pts[0]], fill=(200, 0, 255), width=3)
    im.save(path)


def show(rows: list[dict]) -> None:
    for cond in CONDS:
        rs = [r for r in rows if r["cond"] == cond and "error" not in r]
        if not rs:
            continue
        err = [abs(r["grid"][k] - r["truth"][k]) for r in rs for k in ("x1", "x2", "y1", "y2")]
        print(f"== {cond}: {len(rs)}회, 선 오차(0~1000) 중앙 {statistics.median(err):.0f} / p90 "
              f"{sorted(err)[int(.9 * (len(err) - 1))]} / 최대 {max(err)}, 시간 중앙 {statistics.median(r['s'] for r in rs):.1f}초, "
              f"기능 확인(자리 틀 맞음) {sum(r['check']['ok'] for r in rs)}/{len(rs)}")
        for p in sorted({r["photo"] for r in rs}):
            pr = [r for r in rs if r["photo"] == p]
            gs = "  ".join(f"{r['grid']['x1']},{r['grid']['x2']},{r['grid']['y1']},{r['grid']['y2']}"
                           f"[{'OK' if r['check']['ok'] else r['check'].get('got', r['check'].get('why'))}]" for r in pr)
            t = pr[0]["truth"]
            print(f"  {p} 손 {t['x1']},{t['x2']},{t['y1']},{t['y2']} | Gemini {gs}")
    hands = {r["photo"]: r["truth_check"] for r in rows if "truth_check" in r}
    print("손 격자 기능 확인:", {p: ("OK" if c["ok"] else c) for p, c in hands.items()})


def main(runs: int) -> None:
    from dotenv import load_dotenv

    from app.recognizer import GeminiRecognizer

    load_dotenv("C:/Users/jjh7757/Downloads/부트캠프/.env")
    r = GeminiRecognizer(os.environ["GEMINI_API_KEY"], thinking="low")
    det = rv.TileDetector(conf=0.04)
    FIG.mkdir(parents=True, exist_ok=True)
    rows = []
    for scene, (photos, truth, side, want) in SCENES.items():
        for p in photos:
            rgb = photo_rgb(p)
            jpeg = jpeg_of(rgb)
            truth_check = frame_check(det, rgb, truth, side, want)
            got = []
            for i in range(runs):
                for cond in CONDS:
                    try:
                        a = ask(r, jpeg, cond)
                    except Exception as e:  # noqa: BLE001
                        rows.append({"photo": p, "scene": scene, "cond": cond, "run": i, "error": repr(e)[:200]})
                        print(f"{p} {cond} #{i} 오류 {e!r}"[:200], flush=True)
                        continue
                    a.update(photo=p, scene=scene, cond=cond, run=i, truth=truth, truth_check=truth_check,
                             check=frame_check(det, rgb, a["grid"], side, want))
                    rows.append(a)
                    got.append(a)
                    g = a["grid"]
                    print(f"{p} {cond:4s} #{i} {a['s']:5.1f}s 격자 {g['x1']},{g['x2']},{g['y1']},{g['y2']} "
                          f"(손 {truth['x1']},{truth['x2']},{truth['y1']},{truth['y2']}) 틀 {a['check']}", flush=True)
            draw(rgb, truth, got, FIG / f"{p}.png")
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8")
    show(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--median", action="store_true", help="저장된 답의 중앙값 격자로 다시 확인(호출 없음)")
    a = ap.parse_args()
    if a.median:
        pass  # 아래 median_check
    elif a.show:
        show(json.loads(OUT.read_text(encoding="utf-8")))
    else:
        main(a.runs)


def median_check() -> None:
    """설치 때 여러 번 물어 선마다 중앙값을 쓰면? 저장된 답으로(추가 호출 없음) 조건별 3회 중앙값 격자의 오차·기능 확인."""
    rows = [r for r in json.loads(OUT.read_text(encoding="utf-8")) if "error" not in r]
    det = rv.TileDetector(conf=0.04)
    for cond in list(CONDS) + ["both"]:
        errs, oks = [], []
        for scene, (photos, truth, side, want) in SCENES.items():
            for p in photos:
                rs = [r for r in rows if r["photo"] == p and (cond == "both" or r["cond"] == cond)]
                g = {k: int(statistics.median(r["grid"][k] for r in rs)) for k in ("x1", "x2", "y1", "y2")}
                errs += [abs(g[k] - truth[k]) for k in g]
                c = frame_check(det, photo_rgb(p), g, side, want)
                oks.append(c["ok"])
                print(f"  {cond:4s} {p} 중앙값 격자 {g['x1']},{g['x2']},{g['y1']},{g['y2']} "
                      f"(손 {truth['x1']},{truth['x2']},{truth['y1']},{truth['y2']}) 틀 {c}")
        print(f"== {cond} 중앙값({'6' if cond == 'both' else '3'}회): 선 오차 중앙 {statistics.median(errs):.0f} / 최대 {max(errs)}, "
              f"기능 확인 {sum(oks)}/{len(oks)}")


if __name__ == "__main__" and "--median" in sys.argv:
    median_check()
