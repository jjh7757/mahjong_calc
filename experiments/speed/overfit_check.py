"""자리 판독 틀 규칙(모자이크 검출 + structure)이 평가 사진 6장에 과적합됐는지 B·C·D 안에서 확인한다(2026-10-26 밤, 사용자 요청).
평가 세트는 B·C·D 만(사용자 결정) — 새 사진 없이 할 수 있는 세 가지:

  1) 민감도: 설정값(k·pad·half·gap·sep)을 넓게 바꿔도 결과가 같은가(뾰족한 한 점이면 과적합 신호)
  2) 장면 하나씩 빼기: 두 장면으로 설정을 고르고 남은 장면에 시험
  3) 흔든 사진: 크기·회전·밝기·대비·흐림·JPEG·자르기 위치를 바꾼 사진(다른 카메라·격자 조건 흉내)

결과마다 correct(틀 정답) / fallback(장수 검사 실패 → 지금 방식, 안전) / unsafe(검사 통과했는데 틀린 틀 — 위험).

  python -I experiments/speed/overfit_check.py detect [--tag own]     검출 상자 캐시 results/overfit/boxes_<tag>.json (몇 분)
  python -I experiments/speed/overfit_check.py analyze [--tag own] [--checks count|strict|safe]
"""
from __future__ import annotations

import argparse
import io
import itertools
import json
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
import bench as b  # noqa: E402
import seat_det_variants as dv  # noqa: E402
import seat_yolo as sy  # noqa: E402

OUT = ROOT / "results" / "overfit"
DEFAULT = {"k": 4, "pad": 1.5, "half": 1.5, "gap": 0.35, "sep": 2.5}
DET_GRID = {"k": [2, 3, 4, 5, 6], "pad": [1.0, 1.5, 2.0], "half": [1.0, 1.5, 2.0]}
STRUCT_GRID = {"gap": [0.25, 0.35, 0.45], "sep": [2.0, 2.5, 3.0]}
PHOTOS = [(s, p) for s in "BCD" for p in b.PHOTOS[s]]


def augment(im: Image.Image, name: str) -> Image.Image:
    W, H = im.size
    if name == "none":
        return im
    kind, v = name.split(":")
    v = float(v)
    if kind == "scale":
        return im.resize((round(W * v), round(H * v)), Image.LANCZOS)
    if kind == "rot":
        return im.rotate(v, resample=Image.BICUBIC, fillcolor=(114, 114, 114))
    if kind == "bright":
        return ImageEnhance.Brightness(im).enhance(v)
    if kind == "contrast":
        return ImageEnhance.Contrast(im).enhance(v)
    if kind == "blur":
        return im.filter(ImageFilter.GaussianBlur(v))
    if kind == "jpeg":
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=int(v))
        return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    if kind == "cut":  # 격자 선이 다르게 맞춰진 경우: 한쪽을 v 비율만큼 잘라 냄(L/R/T/B 를 v 부호·크기로)
        f = (v % 100) / 100
        side = {"1": (round(W * f), 0, W, H), "2": (0, 0, W - round(W * f), H),
                "3": (0, round(H * f), W, H), "4": (0, 0, W, H - round(H * f))}[str(int(v // 100))]
        return im.crop(side)
    if kind == "pad":  # 격자를 넓게 잡은 경우: 둘레에 펠트 비슷한 색 여백
        p = round(H * v)
        out = Image.new("RGB", (W + 2 * p, H + 2 * p), (30, 90, 60))
        out.paste(im, (p, p))
        return out
    raise ValueError(name)


# cut:1xx = 왼쪽 xx% 자름, 2xx = 오른쪽, 3xx = 위, 4xx = 아래
AUGS = ["none", "scale:0.7", "scale:1.3", "rot:-6", "rot:-3", "rot:3", "rot:6", "bright:0.7", "bright:1.3",
        "contrast:0.7", "blur:2", "jpeg:40", "cut:110", "cut:210", "cut:310", "cut:410", "pad:0.1"]


def _detect_job(job):
    scene, photo, aug = job
    det = sy.rv.TileDetector(conf=0.04)
    im = augment(Image.open(b.G / scene / photo / b.TRUTH[scene][0]).convert("RGB"), aug)
    rgb = np.asarray(im)
    out = {}
    for k, pad, half in itertools.product(*DET_GRID.values()):
        boxes = dv.mosaic(det, rgb, k, pad, half)[0]
        out[f"{k}|{pad}|{half}"] = [list(map(int, x)) for x in boxes] if boxes is not None else None
    print(f"{scene} {photo} {aug}", flush=True)
    return f"{photo}|{aug}", out


def detect(workers: int, tag: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"boxes_{tag}.json"
    cache = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    jobs = [(s, p, a) for s, p in PHOTOS for a in AUGS if f"{p}|{a}" not in cache]
    with ProcessPoolExecutor(workers) as ex:
        for key, out in ex.map(_detect_job, jobs):
            cache[key] = out
            f.write_text(json.dumps(cache), encoding="utf-8")


# ---------------------------------------------------------------- 채점

def truth(scene):
    return len(b.TRUTH[scene][1].split()), [len(m.split()) for m in b.TRUTH[scene][2]]


def analyze(checks: str, tag: str) -> None:
    cache = json.loads((OUT / f"boxes_{tag}.json").read_text(encoding="utf-8"))
    # structure 는 흰 면 거르기에 사진이 필요 → 흔든 사진을 다시 만든다(검출은 캐시)
    res = {}  # (photo, aug, params) → outcome
    for scene, photo in PHOTOS:
        base_im = Image.open(b.G / scene / photo / b.TRUTH[scene][0]).convert("RGB")
        want = truth(scene)
        for aug in AUGS:
            key = f"{photo}|{aug}"
            if key not in cache:
                continue
            rgb = np.asarray(augment(base_im, aug))
            white = sy.rv.white_mask(rgb)
            for dkey, boxes in cache[key].items():
                for gap, sep in itertools.product(*STRUCT_GRID.values()):
                    if boxes is None:
                        o = "fallback"
                    else:
                        bxs = [tuple(x) for x in boxes]
                        if checks == "ink":  # 무늬 없는 상자(테이블 테두리 등)는 틀을 나누기 전에 버린다
                            bxs = [x for x in bxs if sy.ink(rgb, x) >= sy.INK_MIN]
                        st = structure_cached(rgb, white, bxs, gap, sep)
                        if (not sy.valid(st) or (checks == "strict" and not sy.strict_ok(st))
                                or (checks in ("safe", "ink") and not sy.safe_ok(st, rgb))):
                            o = "fallback"
                        else:
                            got = (len(st["hand"]) + (1 if st["separate"] else 0), [len(m) for m in st["melds"]])
                            o = "correct" if got == want else "unsafe"
                    res[(scene, photo, aug, f"{dkey}|{gap}|{sep}")] = o
    params = sorted({k[3] for k in res})
    dflt = "|".join(str(DEFAULT[x]) for x in ("k", "pad", "half", "gap", "sep"))

    def tally(keys):
        c = {"correct": 0, "fallback": 0, "unsafe": 0}
        for k in keys:
            c[res[k]] += 1
        return c

    print(f"\n검사: {checks}  설정 조합 {len(params)}개 × 사진 6 × 흔들기 {len(AUGS)}")
    # 1) 민감도(흔들지 않은 사진): 조합별 C·D 정답 수 분포, 기본값 이웃
    print("\n1) 민감도 — 흔들지 않은 사진, 조합마다 6장 중 correct/unsafe")
    dist = {}
    for p in params:
        c = tally([(s, ph, "none", p) for s, ph in PHOTOS])
        dist.setdefault((c["correct"], c["unsafe"]), []).append(p)
    for (cor, uns), ps in sorted(dist.items(), key=lambda kv: (-kv[0][0], kv[0][1])):
        print(f"   correct {cor}/6 unsafe {uns}: 조합 {len(ps)}개 ({len(ps) / len(params):.0%})")
    c = tally([(s, ph, "none", dflt) for s, ph in PHOTOS])
    print(f"   기본값 {dflt}: {c}")
    for name in ("k", "pad", "half", "gap", "sep"):
        grid = (DET_GRID | STRUCT_GRID)[name]
        row = []
        for v in grid:
            d = dict(DEFAULT, **{name: v})
            p = "|".join(str(d[x]) for x in ("k", "pad", "half", "gap", "sep"))
            cc = tally([(s, ph, "none", p) for s, ph in PHOTOS])
            row.append(f"{v}→{cc['correct']}/{cc['unsafe']}")
        print(f"   {name:4s} 하나만 바꿈(correct/unsafe): " + "  ".join(row))

    # 2) 장면 하나씩 빼기: 나머지 두 장면(모든 흔들기)에서 correct − 5·unsafe 최대 조합 → 뺀 장면에 시험
    print("\n2) 장면 하나씩 빼기(고를 때 흔든 사진 포함, 점수 = correct − 5×unsafe)")
    for hold in "BCD":
        train = [(s, ph) for s, ph in PHOTOS if s != hold]
        test = [(s, ph) for s, ph in PHOTOS if s == hold]
        score = lambda p, ph_list: (lambda c: c["correct"] - 5 * c["unsafe"])(  # noqa: E731
            tally([(s, ph, a, p) for s, ph in ph_list for a in AUGS if (s, ph, a, p) in res]))
        best = max(params, key=lambda p: (score(p, train), p == dflt))
        ct = tally([(s, ph, a, best) for s, ph in test for a in AUGS if (s, ph, a, best) in res])
        cd = tally([(s, ph, a, dflt) for s, ph in test for a in AUGS if (s, ph, a, dflt) in res])
        print(f"   {hold} 뺌 → 고른 조합 {best}: {hold} 에서 {ct}   (기본값이면 {cd})")

    # 3) 흔든 사진: 기본값
    print(f"\n3) 흔든 사진 — 기본값 {dflt}")
    for aug in AUGS:
        cc = tally([(s, ph, aug, dflt) for s, ph in PHOTOS if (s, ph, aug, dflt) in res])
        bad = [ph for s, ph in PHOTOS if res.get((s, ph, aug, dflt)) == "unsafe"]
        print(f"   {aug:12s} correct {cc['correct']}/6 fallback {cc['fallback']} unsafe {cc['unsafe']} {bad if bad else ''}")
    allc = tally([k for k in res if k[3] == dflt])
    print(f"   합계: {allc}")
    allp = tally(list(res))
    print(f"   (모든 조합 × 모든 흔들기 합계: {allp})")
    (OUT / f"outcomes_{tag}_{checks}.json").write_text(json.dumps({"|".join(k): v for k, v in res.items()}), encoding="utf-8")


def structure_cached(rgb, white, boxes, gap, sep):
    # sy.structure 는 매번 흰 면 마스크를 다시 만든다 → 같은 일을 미리 만든 마스크로
    faces = sy.rv.dedupe(sy.rv.keep_faces(boxes, white))
    if not faces:
        return None
    orig = sy.rv.keep_faces
    sy.rv.keep_faces = lambda bx, w, min_white=0.5: bx  # noqa: E731
    orig_mask = sy.rv.white_mask
    sy.rv.white_mask = lambda _: white  # noqa: E731
    try:
        return sy.structure(rgb, faces, gap, sep)
    finally:
        sy.rv.keep_faces = orig
        sy.rv.white_mask = orig_mask


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["detect", "analyze"])
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--checks", default="count", choices=["count", "strict", "safe", "ink"])
    ap.add_argument("--tag", default="own", help="검출 캐시 이름: v1 = 처음(토막 몫 거르기 없음), own = 토막 몫 거르기")
    a = ap.parse_args()
    dv.OWN = a.tag != "v1"
    if a.mode == "detect":
        detect(a.workers, a.tag)
    else:
        analyze(a.checks, a.tag)
