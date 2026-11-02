"""10-31 추적 프레임(1020×764)에서 패산 위 도라 표시패 찾기(2026-11-02). 표 1-34.

정답 = 판마다 고른 프레임 30장을 Claude 가 눈으로 찾은 위치(사용자 확인 전), 1224 는 패산에 앞면 패 없음.
앞 12장으로 규칙을 맞추고 뒤 18장으로 잰다. 검출기·분류기는 그 시간대를 학습하지 않은 나눔 모델.
규칙: 앞면 패 상자의 앞뒤(한 축)에 패 뒷면 색이 붙어 있는 정도로 순위를 매겨 맨 위를 답으로 낸다.

  python -I -X utf8 experiments/tile_classifier/wall_frames.py             # 자체 모델, 고른 프레임 + 전체 프레임 다수결
  python -I -X utf8 experiments/tile_classifier/wall_frames.py --gemini    # 운영 /v2/wall 도 호출(API 30회)
결과 data/wall_frames/*.json, overlay.jpg
"""
from __future__ import annotations

import argparse
import collections
import io
import json
import statistics
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from rules_core import st  # noqa: E402,F401  서버 코드 경로를 잡는다
from app import local_read as lr  # noqa: E402

ROOT = HERE.parent.parent
CAPS = ROOT / "experiments" / "visit_20261031" / "captures"
OUT = HERE / "data" / "wall_frames"
MODELS = HERE / "server_bench" / "models"
TOL = 20  # 정답과 가운데 차이(px, 패 약 1장)

# 프레임 순번 → 표시패 가운데. None = 패산에 앞면 패 없음. 994 는 두 장이 나란해 둘 사이 어느 쪽이든 맞음.
TRUTH = {36: (464, 635), 156: (253, 444), 258: (289, 267), 429: (723, 108), 566: (427, 118), 692: (404, 117), 785: (554, 640),
         918: (366, 600), 994: (449, 218), 1067: (281, 372), 1133: (672, 323), 1167: (421, 204), 1224: None, 1276: (740, 327),
         1306: (700, 290), 1335: (702, 363), 1366: (426, 173), 1414: (705, 308), 1438: (602, 593), 1460: (312, 243), 1509: (304, 267),
         1586: (387, 151), 1661: (440, 172), 1739: (710, 536), 1798: (309, 382), 1826: (575, 590), 1889: (331, 445), 1938: (532, 618),
         2011: (485, 603), 2059: (336, 394)}
DEV = sorted(TRUTH)[:12]
# 분류기 답을 보기 전에 눈으로 확실히 읽은 패만
READ_TRUTH = {36: "5s", 566: "3p", 692: "7s", 785: "7m", 1067: "9p", 1276: "5p", 1335: "5z", 1586: "9s", 2011: "7m"}


def all_frames() -> list[dict]:
    rows = []
    for z in sorted(CAPS.glob("20261031_*_track/frames_*.zip")):
        with zipfile.ZipFile(z) as zf:
            for f in json.loads(zf.read("frames.json"))["frames"]:
                rows.append(dict(zip=str(z), file=f["file"], at=f["at"]))
    rows.sort(key=lambda r: r["at"])
    return rows


def load(r: dict) -> np.ndarray:
    with zipfile.ZipFile(r["zip"]) as zf:
        return np.asarray(Image.open(io.BytesIO(zf.read(r["file"]))).convert("RGB"))


def back_mask(rgb: np.ndarray) -> np.ndarray:
    """분홍·보라 패 뒷면(PIL HSV, 0~255)."""
    h, s, v = np.moveaxis(np.asarray(Image.fromarray(rgb).convert("HSV")), 2, 0)
    return (s >= 25) & (v >= 150) & (((h >= 160) & (h <= 195)) | ((h >= 225) & (h <= 250)))


def side_scores(mask: np.ndarray, b) -> tuple[list[float], list[float]]:
    """상자 바로 옆 네 칸의 뒷면 비율: [왼쪽, 오른쪽], [위, 아래]."""
    x, y, w, h = b
    H, W = mask.shape

    def frac(x0, y0, x1, y1):
        x0, y0, x1, y1 = max(0, int(x0)), max(0, int(y0)), min(W, int(x1)), min(H, int(y1))
        return float(mask[y0:y1, x0:x1].mean()) if x1 > x0 and y1 > y0 else 0.0

    g = 2
    return ([frac(x - g - w, y, x - g, y + h), frac(x + w + g, y, x + w + g + w, y + h)],
            [frac(x, y - g - h, x + w, y - g), frac(x, y + h + g, x + w, y + h + g + h)])


def candidates(rgb: np.ndarray, faces: list) -> list[dict]:
    mask = back_mask(rgb)
    out = []
    for b in faces:
        lr_, ud = side_scores(mask, b)
        pair = lr_ if sum(lr_) >= sum(ud) else ud
        n = sum(p >= 0.5 for p in pair)
        if n:
            out.append(dict(box=[int(v) for v in b], sides=n, score=round(n + sum(pair) / 2, 3)))
    return sorted(out, key=lambda c: -c["score"])


def center(b) -> tuple[float, float]:
    return b[0] + b[2] / 2, b[1] + b[3] / 2


def hit(c, t) -> bool:
    return abs(c[0] - t[0]) <= TOL and abs(c[1] - t[1]) <= TOL


def fold(at: str) -> tuple[str, str]:
    """오전(14시 전) 프레임은 오전을 학습 안 한 fold_b·cls_am, 오후는 fold_a·cls_pm."""
    return ("b", "am") if at[11:13] < "14" else ("a", "pm")


# 프레임을 판으로 나눈 시작 순번(표본 시트를 눈으로 봄). 마지막 값 뒤는 쓰지 않음.
ROUNDS = [0, 131, 174, 332, 542, 640, 734, 881, 972, 1043, 1098, 1167, 1208, 1260, 1289, 1328, 1355, 1397, 1427, 1440, 1473, 1566, 1634, 1713, 1789, 1814,
          1872, 1909, 1985, 2041, 2077]


def majority(rows: list[dict], readers: dict) -> dict:
    """판의 모든 프레임 답을 위치별로 모아 고른 프레임 쪽 카메라와 같을 때만 비교한다."""
    per_round = {}
    t0 = time.time()
    answers = []
    for i, r in enumerate(rows):
        rgb = load(r)
        k = fold(r["at"])
        c = candidates(rgb, readers[k[0]].detect(rgb))
        answers.append(center(c[0]["box"]) if c else None)
        if i % 300 == 0:
            print("  전체 프레임", i, round(time.time() - t0), flush=True)
    for t, truth in TRUTH.items():
        n = next((j for j, s in enumerate(ROUNDS) if s > t), len(ROUNDS)) - 1
        lo, hi = ROUNDS[n], ROUNDS[n + 1] if n + 1 < len(ROUNDS) else len(rows)
        # 카메라가 움직일 수 있어 고른 프레임 앞뒤 20장만
        lo, hi = max(lo, t - 20), min(hi, t + 21)
        cnt = collections.Counter()
        got = [a for a in answers[lo:hi] if a]
        for a in got:
            cnt[(round(a[0] / 20), round(a[1] / 20))] += 1
        top = None
        if cnt:
            key = cnt.most_common(1)[0][0]
            near = [a for a in got if abs(a[0] / 20 - key[0]) <= 1 and abs(a[1] / 20 - key[1]) <= 1]
            top = (statistics.median(a[0] for a in near), statistics.median(a[1] for a in near))
        same = sum(1 for a in answers[lo:hi] if a and truth and hit(a, truth))
        per_round[t] = dict(frames=hi - lo, answered=len(got), top=top, right=(top is None) if truth is None else bool(top and hit(top, truth)), same_as_truth=same)
    return per_round


def gemini(rows: list[dict]) -> dict:
    import requests

    key = (ROOT / ".recognizer_key").read_text().strip()
    res = {}
    for t in sorted(TRUTH):
        buf = io.BytesIO()
        Image.fromarray(load(rows[t])).save(buf, "JPEG", quality=90)
        t0 = time.time()
        try:
            r = requests.post("https://mahjong.ai-agent-develop.cloud/v2/wall", headers={"X-API-Key": key}, files={"image": ("f.jpg", buf.getvalue(), "image/jpeg")}, timeout=90)
            res[t] = dict(status=r.status_code, s=round(time.time() - t0, 1), body=r.json())
        except Exception as e:  # noqa: BLE001
            res[t] = dict(status=-1, s=round(time.time() - t0, 1), err=str(e))
        print(t, res[t]["status"], res[t]["s"], json.dumps(res[t].get("body"), ensure_ascii=False)[:160], flush=True)
        (OUT / "gemini.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        time.sleep(2)
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gemini", action="store_true")
    ap.add_argument("--no-all", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    rows = all_frames()
    if a.gemini:
        gemini(rows)
        return
    readers = {"a": lr.LocalReader(det_model=MODELS / "det_fold_a.onnx", cls_model=MODELS / "cls_pm.onnx"),
               "b": lr.LocalReader(det_model=MODELS / "det_fold_b.onnx", cls_model=MODELS / "cls_am.onnx")}
    res, tiles = {}, []
    for t, truth in sorted(TRUTH.items()):
        r = rows[t]
        rgb = load(r)
        rd = readers[fold(r["at"])[0]]
        t0 = time.time()
        faces = rd.detect(rgb)
        det_ms = (time.time() - t0) * 1000
        t0 = time.time()
        cs = candidates(rgb, faces)
        rule_ms = (time.time() - t0) * 1000
        top = cs[0] if cs else None
        ok = (top is None) if truth is None else bool(top and hit(center(top["box"]), truth))
        found = truth is not None and any(hit(center(f), truth) for f in faces)
        read = rd.read_any(rgb, top["box"]) if top else None
        res[t] = dict(at=r["at"][11:19], truth=truth, top=top, ok=ok, face_found=found, n_faces=len(faces), n_cands=len(cs), det_ms=round(det_ms), rule_ms=round(rule_ms, 1), read=read, read_truth=READ_TRUTH.get(t))
        print(t, "dev " if t in DEV else "test", "OK " if ok else "NO ", "검출" if found else "놓침", "후보", len(cs), top and top["box"], top and top["score"], "읽음", read, READ_TRUTH.get(t, ""), flush=True)
        im = Image.fromarray(rgb)
        d = ImageDraw.Draw(im)
        for f in faces:
            d.rectangle((f[0], f[1], f[0] + f[2], f[1] + f[3]), outline=(90, 200, 255))
        if top:
            b = top["box"]
            d.rectangle((b[0], b[1], b[0] + b[2], b[1] + b[3]), outline="red", width=3)
        if truth:
            d.ellipse((truth[0] - 5, truth[1] - 5, truth[0] + 5, truth[1] + 5), outline="yellow", width=2)
        d.rectangle((0, 0, 90, 13), fill="black")
        d.text((2, 1), f"#{t} {'OK' if ok else 'NO'}", fill="lime" if ok else "red")
        tiles.append(im.resize((510, 382)))
    (OUT / "picked.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    sheet = Image.new("RGB", (5 * 510, ((len(tiles) + 4) // 5) * 382))
    for k, im in enumerate(tiles):
        sheet.paste(im, ((k % 5) * 510, (k // 5) * 382))
    sheet.save(OUT / "overlay.jpg", quality=88)
    for name, ids in (("개발", [t for t in TRUTH if t in DEV]), ("평가", [t for t in TRUTH if t not in DEV])):
        print(name, "맞음", sum(res[t]["ok"] for t in ids), "/", len(ids), "상자에 있음", sum(res[t]["face_found"] for t in ids))
    rd_ok = [t for t in READ_TRUTH if res[t]["read"]]
    print("읽기(위치 맞은 곳)", sum(res[t]["read"][0] == READ_TRUTH[t] for t in rd_ok if res[t]["ok"]), "/", sum(res[t]["ok"] for t in rd_ok))
    print("시간 검출", statistics.median(r["det_ms"] for r in res.values()), "규칙", statistics.median(r["rule_ms"] for r in res.values()))
    if not a.no_all:
        m = majority(rows, readers)
        (OUT / "majority.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
        for name, ids in (("개발", [t for t in TRUTH if t in DEV]), ("평가", [t for t in TRUTH if t not in DEV])):
            print(name, "앞뒤 프레임 다수결 맞음", sum(m[t]["right"] for t in ids), "/", len(ids), "프레임별 맞음 합", sum(m[t]["same_as_truth"] for t in ids), "/", sum(m[t]["frames"] for t in ids))


if __name__ == "__main__":
    main()
