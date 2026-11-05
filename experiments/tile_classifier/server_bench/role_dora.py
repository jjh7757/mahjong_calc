"""역할 모델의 wall(패산 위 앞면 표시패)·pair(탁자 위 표시패 짝) 판단으로 도라 표시패 찾기(2026-11-05, 사용자 "역할 모델의 wall·pair 판단을
표시패 찾기에 쓰고 테스트해봐", 노트북, API 없음, 앱·서버 미반영).

흐름: app.roles.read_roles(hybrid, 8회차 회전 상자 검출기 나눔 모델 + 서버 정리)가 돌려준 상자별 역할 중 wall·pair 를 모아 원본에서
read_turned(15° 단위로 돌려 읽기)로 읽는다. 안깡 거르기(규칙, 사진에 맞춘 값 아님): 이웃한(중심 거리 ≤ 1.35 × 패 짧은 변) wall 두 장이
같은 패로 읽히면 안깡(네 장이 같은 패)으로 보고 뺀다 — 왕패의 도라·깡도라 두 장이 같은 패일 확률은 낮다.
비교 = 같은 사진의 앱 흐름 로그(표 1-75 펠트 자동 격자)의 표시패. 정답 = visit_20261031/truth.json indicators(평가 장면).
  python -I -X utf8 experiments/tile_classifier/server_bench/role_dora.py [--no-kan] [--vis]
결과 data/role/bench/role_dora.json, 그림 data/role/bench/role_dora/<이름>.jpg(--vis)
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import role_full_bench as rfb  # noqa: E402  (경로·서버 모듈을 같이 올린다)

ROOT = HERE.parents[2]
OUT = HERE.parent / "data" / "role" / "bench"
LOG = ROOT / "experiments" / "speed" / "results" / "log_flow_zone_dart_1105c_{}.txt"
KAN_NEAR = 1.35
# B·C·D 갤러리 연출 사진의 표시패(2026-11-05 원본 확대 눈 판독): B 펠트 위 東·七萬, C 왼쪽 패산 옆 七萬·6s, D 펠트 위 4p·4p·七萬
BCD_IND = {"k25": ["1z", "7m"], "k28": ["1z", "7m"], "k15": ["6s", "7m"], "k26": ["6s", "7m"], "k12": ["4p", "4p", "7m"], "k16": ["4p", "4p", "7m"]}


def app_inds() -> dict:
    """표 1-75 펠트 자동 격자 앱 흐름의 표시패(사진 → [패])."""
    out = {}
    for part in ("bcd", "am", "pm"):
        for line in Path(str(LOG).format(part)).read_text(encoding="utf-8", errors="replace").splitlines():
            i = line.find("TIMING {")
            if i >= 0:
                r = json.loads(line[i + 7:])
                m = r.get("merge") or {}
                out.setdefault(r["photo"], sorted((m.get("dora_indicators") or []) + (m.get("ura_indicators") or [])))
    return out


BACK_FRAC = 0.4  # 앞면은 흰 바탕에 작은 무늬, 뒷면은 면 전체가 색이라 반을 기준으로(사진 보고 정한 값 아님)


def back_frac(rgb: np.ndarray, b) -> float:
    x, y, w, h = (int(v) for v in b)
    part = rgb[max(0, y + h // 5): y + h - h // 5, max(0, x + w // 5): x + w - w // 5]
    return float(rfb.lr._back_mask(part).mean()) if part.size else 0.0


def norm(t: str) -> str:
    return "5" + t[1] if t[0] == "0" else t  # 적5 표시패는 5 와 같은 도라


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-kan", action="store_true", help="안깡 거르기 끔")
    ap.add_argument("--keep-backs", action="store_true", help="뒷면 색 거르기 끔(첫 판)")
    ap.add_argument("--no-side", action="store_true", help="wall 에 '옆에 뒷면' 조건 끔(둘째 판)")
    ap.add_argument("--vis", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    import obb_detect
    from app import river

    obb_detect.install(rfb.bench, rfb.lr, river, False, True, sliver=True, kan=True)
    meta = {p["name"]: p for p in json.loads((HERE / "meta.json").read_text(encoding="utf-8"))["photos"]}
    truth = json.loads((ROOT / "experiments/visit_20261031/truth.json").read_text(encoding="utf-8"))["scenes"]
    app = app_inds()
    readers: dict = {}
    rows, tally = {}, dict(n=0, role_ok=0, app_ok=0)
    font = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 44)
    for s in rfb.sg.eval_scenes():
        p = meta.get(s["name"])
        if p is None:
            continue
        key = (p["det"], p["part"])
        reader = readers.setdefault(key, rfb.lr.LocalReader(threads=2, det_model=HERE / "models" / f"det_r8_fold_{p['det']}.onnx",
                                                            cls_model=HERE / "models" / f"cls_{p['part']}.onnx"))
        short = s["name"] if s["set"] == "bcd" else s["name"][-6:]
        jpeg = Path(s["path"]).read_bytes()
        o = rfb.roles.read_roles(reader, jpeg, s["side"], s["grid"], "hybrid")
        rgb = np.asarray(Image.open(s["path"]).convert("RGB"))
        cand = [r for r in o["roles"] if r["role"] in ("wall", "pair")]
        if not a.keep_backs:  # 뒷면 패는 표시패가 아니다: 상자 가운데 60% 의 뒷면 색 비율(서버 _back_mask)이 BACK_FRAC 넘으면 뺀다
            cand = [r for r in cand if back_frac(rgb, r["box"]) < BACK_FRAC]
        if not a.no_side:  # wall 의 정의 = 옆에 뒷면이 붙은 앞면 패(role_label.py). 다른 자리 울기·펠트 위 낱장은 역할 모델이 wall 로 몰아넣는다
            cand = [r for r in cand if r["role"] == "pair" or rfb.lr.wall_score(rgb, r["box"])[0] >= 1]
        boxes = [r["box"] for r in o["roles"]]
        tw = statistics.median(min(b[2], b[3]) for b in boxes) if boxes else 1
        th = statistics.median(max(b[2], b[3]) for b in boxes) if boxes else 1
        for r in cand:
            r["tile"], r["tconf"] = reader.read_turned(rgb, r["box"], tw, th)
        kan = set()
        if not a.no_kan:
            walls = [i for i, r in enumerate(cand) if r["role"] == "wall"]
            cen = lambda b: np.array([b[0] + b[2] / 2, b[1] + b[3] / 2])
            for x in walls:
                for y in walls:
                    if x < y and norm(cand[x]["tile"]) == norm(cand[y]["tile"]) and np.linalg.norm(cen(cand[x]["box"]) - cen(cand[y]["box"])) <= KAN_NEAR * tw:
                        kan |= {x, y}
        got = sorted(norm(r["tile"]) for i, r in enumerate(cand) if i not in kan)
        t =BCD_IND.get(short) or truth.get(s["name"], {}).get("indicators")
        want = sorted(norm(x) for x in t) if t else None
        app_got = sorted(norm(x) for x in app.get(short, []))
        row = dict(side=s["side"], got=got, app=app_got, truth=want, kan=[cand[i]["tile"] for i in sorted(kan)],
                   cand=[dict(role=r["role"], rconf=r["conf"], tile=r["tile"], tconf=r["tconf"], box=r["box"]) for r in cand])
        if want is not None:
            row["role_ok"], row["app_ok"] = got == want, app_got == want
            tally["n"] += 1
            tally["role_ok"] += row["role_ok"]
            tally["app_ok"] += row["app_ok"]
        rows[short] = row
        mark = "" if want is None else f" 역할 {'O' if row['role_ok'] else 'X'} 앱 {'O' if row['app_ok'] else 'X'}"
        print(f"{short:7s} 역할 {got} | 앱 {app_got} | 정답 {want}{mark} | 안깡으로 뺌 {row['kan']}", flush=True)
        if a.vis:
            im = Image.fromarray(rgb)
            d = ImageDraw.Draw(im)
            for i, r in enumerate(cand):
                x, y, w, h = r["box"]
                c = (150, 150, 150) if i in kan else ((220, 0, 220) if r["role"] == "pair" else (255, 60, 0))
                d.rectangle([x, y, x + w, y + h], outline=c, width=8)
                d.text((x, y - 50), f"{r['role']} {r['tile']}", fill=c, font=font)
            im.thumbnail((1600, 1600))
            (OUT / "role_dora").mkdir(parents=True, exist_ok=True)
            im.save(OUT / "role_dora" / f"{short}.jpg", quality=85)
    print("---", tally)
    (OUT / f"role_dora{'_nokan' if a.no_kan else ''}{'_backs' if a.keep_backs else ''}{'_noside' if a.no_side else ''}.json").write_text(json.dumps(dict(total=tally, rows=rows), ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
