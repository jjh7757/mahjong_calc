"""자리 크롭을 패가 있는 곳만 잘라 수평으로 펴서(기울기 보정) 보내면 생각·오독이 줄어드나(1번), 패 크기와 생각·오독의 관계(2번).

  python -I experiments/speed/seat_focus.py show                      펴기 결과 그림(results/seat_focus/*.jpg), 평가 밖 A·E 도 참고로
  python -I experiments/speed/seat_focus.py read --conds base,focus,focus_up --runs 10
  python -I experiments/speed/seat_focus.py size --scales 1,0.7,0.5,0.35 --runs 5
  python -I experiments/speed/seat_focus.py stats

요청은 운영 서버(131275a) 자리 판독 한 번과 같다: 받은 사진(긴 변 3072 이하) + 같은 사진 세 토막(ULTRA_HIGH) + 참고표,
SEAT_PROMPT_V2, gemini-3.8-flash thinking=low. 만장일치(3번 동시)는 빼고 한 번 읽기 기준으로 잰다.
펴기는 기기(앱)가 업로드 전에 할 일이라 서버는 바뀌지 않는다.

펴기(focus): 흰 앞면 픽셀 덩어리 중 안에 무늬(갇힌 구멍)가 있는 것만 패로 본다. 크롭 폭 60% 넘게 이어지거나 높이 40% 를
넘는 덩어리(테이블 테두리)는 뺀다. 가장 큰 덩어리(손패 줄)의 주축으로 기울기를 재 수평으로 돌리고, 남은 덩어리 전체를
패 높이 0.7 배 여백으로 자른다. 무늬 없는 白 한 장만 떨어져 있으면 빠질 수 있다(손패 줄 안의 白 은 이웃과 붙어 남는다).
"""
from __future__ import annotations

import argparse
import io
import json
import math
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).parent))
import bench as b  # noqa: E402  (Gemini 클라이언트·정답·판정)

from app import observe as ob  # noqa: E402
from app.recognizer import REF_SHEET, prepare_image, zoom_strips  # noqa: E402

OUT = b.OUT / "seat_focus"
SEATS = {"B": "hand_right", "C": "hand_left", "D": "hand_bottom", "A": "hand_top", "E": "hand_left"}


# ---------------------------------------------------------------- 펴기

def face_mask(rgb: np.ndarray) -> np.ndarray:
    """흰 앞면: 밝고 채도 낮음. 크롭 밝기에 맞춰 밝기 문턱은 상위 밝기의 비율로."""
    f = rgb.astype(np.float32)
    mx, mn = f.max(2), f.min(2)
    sat = (mx - mn) / np.maximum(mx, 1)
    v_hi = np.percentile(mx, 99)
    return (mx > 0.62 * v_hi) & (sat < 0.22)


def tile_blobs(rgb: np.ndarray):
    """[(마스크, 채운 넓이, 무늬 비율)] — 무늬가 든 흰 덩어리만."""
    H, W = rgb.shape[:2]
    m = ndimage.binary_opening(face_mask(rgb), iterations=2)
    lab, n = ndimage.label(m)
    out = []
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if h * w < (H * W) * 0.0008 or w > 0.6 * W or h > 0.4 * H:
            continue
        comp = lab[sl] == i
        filled = ndimage.binary_fill_holes(comp)
        holes = filled & ~comp
        ink = holes.sum() / max(filled.sum(), 1)
        if ink < 0.03:  # 무늬 없음(테두리 조각·반사)
            continue
        full = np.zeros((H, W), bool)
        full[sl] = filled
        out.append((full, int(filled.sum()), round(float(ink), 3)))
    return out


def row_angle(mask: np.ndarray) -> float:
    ys, xs = np.nonzero(mask)
    xs, ys = xs - xs.mean(), ys - ys.mean()
    cov = np.cov(np.stack([xs, ys]))
    w, v = np.linalg.eigh(cov)
    vx, vy = v[:, -1]
    a = math.degrees(math.atan2(vy, vx))
    if a > 90:
        a -= 180
    if a < -90:
        a += 180
    return a


def _rot(mask: np.ndarray, ang: float) -> np.ndarray:
    return np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).rotate(ang, expand=True)) > 127


def focus(img: Image.Image, upscale_to: int | None = None) -> tuple[Image.Image | None, dict]:
    rgb = np.asarray(img.convert("RGB"))
    blobs = [m for m, _, _ in tile_blobs(rgb)]
    if not blobs:
        return None, {"reason": "no tiles"}
    # 손패 줄 = 가까운 덩어리끼리 묶은 무리 중 가장 큰 것(패가 한 장씩 떨어져 잡히기도 하고 줄 전체가 한 덩어리이기도 함)
    sizes = []
    for m in blobs:
        ys, xs = np.nonzero(m)
        sizes.append(min(np.ptp(ys), np.ptp(xs)) + 1)
    unit = float(np.median(sizes))
    union = np.zeros(blobs[0].shape, bool)
    for m in blobs:
        union |= m
    glab, _ = ndimage.label(ndimage.binary_dilation(union, iterations=max(2, round(unit * 0.25))))
    gid = [int(np.bincount(glab[m]).argmax()) for m in blobs]
    main_g = max(set(gid), key=lambda g: sum(blobs[i].sum() for i in range(len(blobs)) if gid[i] == g))
    members = [blobs[i] for i in range(len(blobs)) if gid[i] == main_g]
    if len(members) >= 3:  # 한 장씩 잡힌 줄: 패 중심들을 지나는 직선
        cs = np.array([ndimage.center_of_mass(m)[::-1] for m in members])
        k = np.polyfit(cs[:, 0], cs[:, 1], 1)[0]
        ang = math.degrees(math.atan(k))
    else:
        main = np.zeros_like(union)
        for m in members:
            main |= m
        ang = row_angle(main)
    ang = max(-25.0, min(25.0, ang))
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    rot = img.rotate(ang, resample=Image.BICUBIC, expand=True, fillcolor=tuple(int(v) for v in np.median(border, 0)))
    mm = np.zeros(rot.size[::-1], bool)
    for m in members:
        mm |= _rot(m, ang)
    rows = np.nonzero(mm.any(1))[0]
    tile_h = rows.max() - rows.min() + 1
    # 돌린 뒤 패 크기에 못 미치는 덩어리(반사·바닥 무늬)는 뺀다
    keep = np.zeros_like(mm)
    for m in blobs:
        r = _rot(m, ang)
        ys, xs = np.nonzero(r)
        if np.ptp(ys) + 1 >= 0.4 * tile_h and r.sum() >= 0.15 * tile_h * tile_h:
            keep |= r
    ys, xs = np.nonzero(keep | mm)
    pad = round(0.7 * tile_h)
    # 울기는 크롭 오른쪽 모서리(흰 테두리에 붙어 픽셀로 못 가림) → 오른쪽은 사진 끝까지, 아래는 손패 줄 아래 패 1.6 장 높이까지
    content = _rot(np.ones(rgb.shape[:2], bool), ang)
    top = max(0, min(ys.min() - pad, rows.min() - round(0.8 * tile_h)))
    bottom = min(rot.height, max(ys.max() + pad, rows.max() + round(1.6 * tile_h)))
    band = content[top:bottom]
    right = int(np.nonzero(band.any(0))[0].max()) + 1
    box = (max(0, xs.min() - pad), top, right, bottom)
    out = rot.crop(box)
    info = {"angle": round(ang, 1), "tile_h": int(tile_h), "blobs": len(blobs), "row": len(members),
            "box": [int(v) for v in box], "size": list(out.size), "orig": list(img.size)}
    if upscale_to:
        s = upscale_to / max(out.size)
        if s > 1:
            out = out.resize((round(out.width * s), round(out.height * s)), Image.LANCZOS)
            info["tile_h_sent"] = round(tile_h * s)
    info.setdefault("tile_h_sent", int(tile_h))
    return out, info


def jpeg(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=92)
    return buf.getvalue()


def show() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for s, photos in b.PHOTOS.items():
        for p in photos:
            img = Image.open(b.G / s / p / f"{SEATS[s]}.jpg")
            out, info = focus(img)
            tag = "" if s in "BCD" else " [참고·평가 밖]"
            print(s, p, info, tag)
            if out is not None:
                out.save(OUT / f"{s}_{p}.jpg", quality=85)
                # 덩어리 표시
                rgb = np.asarray(img.convert("RGB")).copy()
                for m, _, _ in tile_blobs(rgb):
                    rgb[m] = (rgb[m] * 0.5 + np.array([255, 0, 0]) * 0.5).astype(np.uint8)
                Image.fromarray(rgb).save(OUT / f"{s}_{p}_blobs.jpg", quality=70)


# ---------------------------------------------------------------- 판독

def seat_request(data: bytes, strips_from: bytes | None = None) -> dict:
    """운영 서버 자리 판독 한 번과 같은 요청. strips_from 이 있으면 확대 토막만 그 사진(펴서 자른 띠)에서."""
    jpg = prepare_image(data, 3072)
    src = prepare_image(strips_from, 3072) if strips_from else jpg
    extra = [b.image_part(z, "ULTRA_HIGH") for z in zoom_strips(src, ob.SEAT_ZOOM_STRIPS)]
    extra.append(b.image_part(REF_SHEET.read_bytes(), None))
    return b.call(jpg, ob.SEAT_PROMPT_V2, ob.SEAT_SCHEMA_V2, "gemini-3.8-flash", "low", "ULTRA_HIGH", extra=extra)


def image_for(cond: str, s: str, p: str) -> tuple[bytes, dict]:
    img = Image.open(b.G / s / p / f"{SEATS[s]}.jpg").convert("RGB")
    if cond == "base":
        return jpeg(img), {"tile_h_sent": None}
    if cond.startswith("scale"):  # scale0.5: 크롭을 줄여 패를 작게(2번)
        k = float(cond[5:])
        _, info = focus(img)
        im = img.resize((round(img.width * k), round(img.height * k)), Image.LANCZOS) if k != 1 else img
        return jpeg(im), {"tile_h_sent": round(info.get("tile_h", 0) * k), "scale": k}
    out, info = focus(img, upscale_to=3072 if cond == "focus_up" else None)
    if out is None:
        return jpeg(img), info | {"fallback": True}
    if cond == "strips":  # 전체 사진은 그대로, 확대 토막만 펴서 자른 띠에서
        return jpeg(img), info | {"strips": jpeg(out)}
    return jpeg(out), info


def read(conds: list[str], runs: int, workers: int, scenes: str, tag: str) -> None:
    imgs = {(c, s, p): image_for(c, s, p) for c in conds for s in scenes for p in b.PHOTOS[s]}
    # 같은 시각에 조건을 섞어 보낸다(시간대 차이 제거)
    jobs = [(c, s, p) for _ in range(runs) for s in scenes for p in b.PHOTOS[s] for c in conds]

    def one(job):
        c, s, p = job
        data, info = imgs[job]
        r = seat_request(data, info.get("strips"))
        row = {"cond": c, "scene": s, "photo": p, "tile_h_sent": info.get("tile_h_sent"),
               **{k: r.get(k) for k in ("s", "in", "out", "think", "error")}}
        if "data" in r:
            row.update(b.judge(s, r["data"]))
        print(f"{c:9s} {s} {p} {row.get('s')}s think {row.get('think')} "
              f"{'OK' if row.get('hand_ok') and row.get('melds_ok') else 'X ' + str(row.get('hand')) + ' ' + str(row.get('melds')) if 'hand' in row else row.get('error')}",
              flush=True)
        return row

    with ThreadPoolExecutor(workers) as ex:
        rows = list(ex.map(one, jobs))
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"{tag}.json"
    old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    f.write_text(json.dumps(old + rows, ensure_ascii=False, indent=1), encoding="utf-8")
    stats_rows(old + rows)


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(math.ceil(q * len(v))) - 1)]


def stats_rows(rows: list[dict]) -> None:
    for c in dict.fromkeys(r["cond"] for r in rows):
        rs = [r for r in rows if r["cond"] == c]
        good = [r for r in rs if not r.get("error")]
        ok = [r for r in good if r.get("hand_ok") and r.get("melds_ok")]
        t = [r["s"] for r in good] or [0]
        th = [r["think"] or 0 for r in good] or [0]
        per = " ".join(f"{s} {sum(1 for r in ok if r['scene'] == s)}/{sum(1 for r in rs if r['scene'] == s)}"
                       for s in "ABCDE" if any(r["scene"] == s for r in rs))
        hs = sorted({r["tile_h_sent"] for r in rs if r.get("tile_h_sent")})
        print(f"{c:10s} 정답 {len(ok)}/{len(rs)} ({per})  시간 중앙 {statistics.median(t):.1f} p90 {pct(t, .9):.1f} 최대 {max(t):.1f}s  "
              f"생각한 호출 {sum(1 for x in th if x > 0)}/{len(good)} 생각 평균 {statistics.mean(th):.0f} 최대 {max(th)}  "
              f"입력 {statistics.mean(r['in'] or 0 for r in good):.0f}" + (f"  패 높이 {hs}" if hs else "")
              + (f"  오류 {len(rs) - len(good)}" if len(rs) > len(good) else ""))
        for s in "BCD":
            sr = [r for r in good if r["scene"] == s]
            if sr:
                st = [r["s"] for r in sr]
                print(f"    {s}: 정답 {sum(1 for r in sr if r.get('hand_ok') and r.get('melds_ok'))}/{len(sr)} "
                      f"중앙 {statistics.median(st):.1f} p90 {pct(st, .9):.1f}s 생각 {sum(1 for r in sr if (r['think'] or 0) > 0)}/{len(sr)}")
        bad = {}
        for r in good:
            if not (r.get("hand_ok") and r.get("melds_ok")):
                k = f"{r['scene']} {r['photo']}: {r['hand']} | {r['melds']}"
                bad[k] = bad.get(k, 0) + 1
        for k, v in bad.items():
            print(f"    틀림 ×{v} {k}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["show", "read", "size", "stats"])
    ap.add_argument("--conds", default="base,focus,focus_up")
    ap.add_argument("--scales", default="1,0.7,0.5,0.35")
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--scenes", default="BCD")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    if a.mode == "show":
        show()
    elif a.mode == "read":
        read(a.conds.split(","), a.runs, a.workers, a.scenes, a.tag or "read")
    elif a.mode == "size":
        read([f"scale{k}" for k in a.scales.split(",")], a.runs, a.workers, a.scenes, a.tag or "size")
    else:
        for f in sorted(OUT.glob("*.json")):
            print(f"== {f.stem}")
            stats_rows([r for r in json.loads(f.read_text(encoding="utf-8")) if r["scene"] in a.scenes])


if __name__ == "__main__":
    main()
