"""펠트 격자 과적합 점검 표(2026-11-02, API 없음). tool/felt_grid_robust_test.dart·dart_check 다음에. 이 결과로 규칙을 고치지 않는다.
  python -X utf8 experiments/zone_points/robust_check.py [삼각대 그림 앞이름]
① 10-24 삼각대 사진 판독·그림 ② 밝기·색 파생 ③ 가운데 경계 값 민감도 ④ 이동 감지 값 민감도
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zones as z  # noqa: E402
from propose import DATA, load  # noqa: E402

FIELD15 = {"122922", "124007", "125053", "130533", "131210", "132647", "133011", "133620", "134323", "135148", "135912", "140302", "140750", "140918", "143443"}


def field(prefix: str | None) -> None:
    rows = json.loads((DATA / "robust.json").read_text(encoding="utf-8"))["field"]
    print("[① 10-24 삼각대] 이름 ok span 기기 격자")
    names = sorted(rows)
    n15 = [n for n in names if n[-6:] in FIELD15]
    for n in names:
        r = rows[n]
        tag = "테스트" if n[-6:] in FIELD15 else "그 밖"
        print(f" {n[-6:]} {tag} ok={r.get('ok')} span={r.get('span', 0):.2f} dev={r.get('device', 0):.2f} {[r['grid'][k] for k in ('x1', 'x2', 'y1', 'y2')] if r.get('grid') else None}")
    print(" 테스트 15장 통과", sum(bool(rows[n].get("ok")) for n in n15), "/", len(n15), "· 그 밖 통과", sum(bool(rows[n].get("ok")) for n in names if n not in n15), "/", len(names) - len(n15))
    if not prefix:
        return
    cols, tw, th = 5, 480, 360
    for page, part in enumerate((n15, [n for n in names if n not in n15])):
        sh = Image.new("RGB", (cols * tw, ((len(part) + cols - 1) // cols) * th))
        for i, n in enumerate(part):
            r = rows[n]
            im = load(r["src"]).resize((tw, th))
            d = ImageDraw.Draw(im)
            if r.get("felt"):
                draw = lambda q, col: d.polygon([(x * tw, y * th) for x, y in q], outline=col)
                draw(r["felt"], (255, 230, 0))
                p = z.polygons(r["felt"])
                draw(p["river"], (0, 255, 255))
                draw(p["device"], (255, 0, 255))
                g = r.get("grid")
                if g:
                    for x in (g["x1"], g["x2"]):
                        d.line((x * tw / 1000, 0, x * tw / 1000, th), fill=(255, 255, 255))
                    for y in (g["y1"], g["y2"]):
                        d.line((0, y * th / 1000, tw, y * th / 1000), fill=(255, 255, 255))
            d.rectangle((0, 0, 170, 13), fill="black")
            d.text((2, 1), f"{n[-6:]} ok={r.get('ok')} s{r.get('span', 0):.2f} d{r.get('device', 0):.2f}", fill="white")
            sh.paste(im, ((i % cols) * tw, (i // cols) * th))
        path = f"{prefix}_{page}.jpg"
        sh.save(path, quality=85)
        print(" 그림", path)


def derived() -> None:
    d = json.loads((DATA / "robust.json").read_text(encoding="utf-8"))["derived"]
    labels = json.loads((DATA / "labels.json").read_text(encoding="utf-8"))
    print("\n[② 파생 사진 35장] 통과, 통과분 최악 오차 중앙/최대(사진 폭 %), 패 폭(2.2%) 넘게 틀린 채 통과")
    for k, rows in d.items():
        errs = []
        for n, r in rows.items():
            if not (r and r["ok"]):
                continue
            lab = labels[n]
            W, H = lab["size"]
            vis = np.array(lab["vis"][:4]) > 0
            e = (np.array(r["felt"]) - np.array(lab["felt"])) * [1.0, H / W]
            errs.append(float(np.hypot(e[:, 0], e[:, 1])[vis].max()))
        a = np.array(errs) if errs else np.array([np.nan])
        print(f" {k}: 통과 {len(errs)}/35, 중앙 {np.median(a) * 100:.2f} 최대 {a.max() * 100:.2f}, 틀린 채 통과 {int((a > 0.022).sum())}")


def boundary() -> None:
    print("\n[③ 가운데 경계 값] 강 패가 칸 밖 / 손패·울기 패가 칸 안(사진 31장, 설치별 중앙값 격자)")
    labels, rows = z.tables()
    boxes = json.loads((DATA.parent / "det" / "boxes_final.json").read_text(encoding="utf-8"))
    for reach in (0.24, 0.26, 0.28, 0.30, 0.32, 0.34, 0.36):
        z.RIVER = reach
        river_out = hand_in = n_r = n_h = 0
        for n in z.scene_list():
            if n not in boxes:
                continue
            r = labels[n]
            g = z.grid_of(r["felt"])
            W, H = r["size"]
            c = np.array([[x + w / 2, y + h / 2] for x, y, w, h in boxes[n]["boxes"]], np.float32)
            uv = z.project(np.linalg.inv(z.to_image(r["felt"])), (c / [W, H]).tolist())
            rr = np.abs(uv - 0.5).max(1)
            inside = (c[:, 0] / W * 1000 > g["x1"]) & (c[:, 0] / W * 1000 < g["x2"]) & (c[:, 1] / H * 1000 > g["y1"]) & (c[:, 1] / H * 1000 < g["y2"])
            river_out += int(((rr < 0.25) & ~inside).sum())
            n_r += int((rr < 0.25).sum())
            hand_in += int(((rr > 0.32) & inside).sum())
            n_h += int((rr > 0.32).sum())
        print(f" {reach:.2f}: 강 밖 {river_out}/{n_r}, 손패 안 {hand_in}/{n_h}")
    z.RIVER = 0.30


def same(a: np.ndarray, b: np.ndarray, near: float) -> bool:
    return int((np.abs(a - b).max(1) < near).sum()) >= 3


def watch() -> None:
    print("\n[④ 이동 감지] 프레임 순서대로, 판정 수(실제 설치 8곳)")
    rows = json.loads((DATA / "proposals.json").read_text(encoding="utf-8"))
    dart = json.loads((DATA / "dart_felt.json").read_text(encoding="utf-8"))
    names = sorted((n for n, r in rows.items() if r["kind"] == "frame"), key=lambda n: rows[n]["at"])
    seq = [np.array(dart[n]["felt"]) if dart[n] and dart[n]["ok"] else None for n in names]
    print(" 간격\\연속  " + "".join(f"{c}장(0.012)   " for c in (2, 3, 4, 5)) + "3장(0.008) 3장(0.020)")
    for step in (1, 2, 3, 4):
        cells = []
        for confirm, near in ((2, 0.012), (3, 0.012), (4, 0.012), (5, 0.012), (3, 0.008), (3, 0.020)):
            basis, pend, events = None, [], 0
            for q in seq[::step]:
                if q is None:
                    continue
                if basis is not None and same(q, basis, near):
                    pend = []
                    continue
                pend = (pend + [q])[-8:]
                if len(pend) < confirm:
                    continue
                recent = pend[-confirm:]
                mid = np.median(np.stack(recent), 0)
                if all(same(p, mid, near) for p in recent):
                    basis, pend = mid, []
                    events += 1
            cells.append(f"{events:<11d}")
        print(f" {step}장마다   " + " ".join(cells))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    field(sys.argv[1] if len(sys.argv) > 1 else None)
    derived()
    boundary()
    watch()
