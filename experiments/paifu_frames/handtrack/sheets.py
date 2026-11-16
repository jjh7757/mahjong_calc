"""5단계: 대조표 그림 — 활동 구간마다 손패 띠를 대국자 시점으로 돌려 초당 10장 전부(손이 없고 앞 줄과 거의 같은 줄만 생략) 시간순으로 쌓고,
구간마다 넓은 화면 한 장, 판 전체 정지 상태 목록, index.json 을 만든다.

  python -X utf8 sheets.py <판 id> [--out-sheets 폴더 이름]
결과 results/handtrack/<판>/sheets/:
  seg_<번호 3자리>_p<장>.jpg  손패 띠 대조표. 왼쪽 열 위→아래, 다음 오른쪽 열. 띠 = config sheet_band(없으면 band)를 대국자 시점으로 돌린 것.
      띠 폭(시점 가로)이 MAX_BAND_W(717px) 이하면 원본 화소 그대로, 넘으면 비율로 줄여 맞춤(MIN_SCALE 0.85 밑으로는 안 줄임 —
      그래도 넘으면 한 열로). 배율은 index.json sheet_scale.
      줄마다 왼쪽 칸에 시각(분:초.0.01초), #줄 번호. 파란 칸 = 직전 정지 상태(첫 줄), 주황 칸 = 직후 정지 상태(마지막 줄) —
      판 마지막 구간처럼 뒤 정지 상태가 없으면 마지막 줄을 주황으로 "끝(뒤 정지 없음)".
      생략: 그 프레임의 띠 피부 비율 < SKIP_SKIN(구간 문턱 segment.ACT_SKIN 과 같음) 이고, 바로 앞 남긴 줄과 1/4 축소 회색에서
      SKIP_LEVEL 넘게 다른 화소가 SKIP_FRAC 이하일 때만. 손이 띠에 있으면 늘 남긴다. 생략이 있으면 다음 남긴 줄 칸에 "생략 n장 시작~끝".
  seg_<번호>_wide.jpg       넓은 화면(대국자 시점, 화료자 손패 줄이 아래쪽): config wide 를 0.48 배로, 구간 안에서 고르게 WIDE_N 장(2열),
                             작은 그림마다 시각과 그 시각에 가장 가까운 띠 줄 번호(#).
  still_p<장>.jpg            판 전체 정지 상태 목록(정지 구간마다 가운데 프레임의 띠 한 줄, 시간순).
  ../index.json              구간 번호·시각·그림 목록·강 변화(river_states.json 에서 — 그림에는 적지 않음)·sheet_band·sheet_scale.
JPEG 품질 95·색 4:4:4.
v1(2026-11-16 처음 판) 과 달라진 점: 손이 있으면 생략 안 함, sheet_band(줄 방향으로 넓힌 띠)·배율, 끝 구간 마지막 줄 표시, 시각 0.01초,
  넓은 화면 머리글·줄 번호. 구간 나누기(segments.json)·강 읽기는 그대로.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import segment as sg  # noqa: E402

MAX_SIDE = 1560
COLS = 2
LABEL_W = 60
GAP = 4
COL_GAP = 6
HEADER = 26
MAX_BAND_W = (MAX_SIDE - COLS * LABEL_W - (COLS - 1) * COL_GAP) // COLS  # 717
MIN_SCALE = 0.85
SKIP_LEVEL = 12  # 1/4 축소 회색에서 이만큼 넘게 다른 화소를
SKIP_FRAC = 0.002  # 이 비율 넘게 가지면 새 줄로 남긴다(아니면 생략). v1 과 같은 값.
SKIP_SKIN = sg.ACT_SKIN  # 0.003 — 띠 피부 비율이 이 이상이면 생략하지 않는다
WIDE_N = 8
WIDE_SCALE = 0.48
FONT = "C:/Windows/Fonts/malgun.ttf"
BLUE, ORANGE, GRAY = (190, 215, 255), (255, 210, 160), (235, 235, 235)


def font(sz: int):
    try:
        return ImageFont.truetype(FONT, sz)
    except OSError:
        return ImageFont.load_default()


F12, F13, F15 = font(12), font(13), font(15)


def skin_frac(rgb: np.ndarray) -> float:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    return float(((h >= 3) & (h < 32) & (s > 40) & (v > 70)).mean())


def small_gray(rgb: np.ndarray) -> np.ndarray:
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    return cv2.resize(g, (max(1, g.shape[1] // 4), max(1, g.shape[0] // 4)), interpolation=cv2.INTER_AREA).astype(np.int16)


def layout(bw: int, bh: int) -> dict:
    """띠 시점 크기 → 배율·열 수·열당 줄 수·그림 폭."""
    if bw <= MAX_BAND_W:
        s, cols = 1.0, COLS
    elif MAX_BAND_W / bw >= MIN_SCALE:
        s, cols = MAX_BAND_W / bw, COLS
    else:
        s, cols = max(MIN_SCALE, min(1.0, (MAX_SIDE - LABEL_W) / bw)), 1
    sw, sh = round(bw * s), round(bh * s)
    width = cols * (LABEL_W + sw) + (cols - 1) * COL_GAP
    assert width <= MAX_SIDE, f"띠가 너무 넓다: {bw}px × {s:.3f} → 그림 폭 {width}"
    rows = (MAX_SIDE - HEADER) // (sh + GAP)
    return {"scale": round(s, 4), "cols": cols, "rows": rows, "sw": sw, "sh": sh, "width": width}


def scaled(v: np.ndarray, L: dict) -> np.ndarray:
    if L["scale"] == 1.0:
        return v
    return np.asarray(Image.fromarray(v).resize((L["sw"], L["sh"]), Image.LANCZOS))


def make_sheet(rows_data: list[dict], header: str, L: dict) -> Image.Image:
    per_col, sw, sh = L["rows"], L["sw"], L["sh"]
    used_rows = min(len(rows_data), per_col)
    H = HEADER + used_rows * (sh + GAP)
    im = Image.new("RGB", (L["width"], H), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.text((6, 4), header, fill=(0, 0, 0), font=F15)
    for i, r in enumerate(rows_data):
        c, k = divmod(i, per_col)
        x = c * (LABEL_W + sw + COL_GAP)
        y = HEADER + k * (sh + GAP)
        mark = r.get("mark")
        bg = BLUE if mark == "prev" else ORANGE if mark in ("next", "end") else GRAY
        d.rectangle([x, y, x + LABEL_W - 3, y + sh - 1], fill=bg)
        d.text((x + 2, y + 2), r["time"], fill=(0, 0, 0), font=F13)
        yy = y + 19
        if r.get("no") is not None:
            d.text((x + 2, yy), r["no"] if isinstance(r["no"], str) else f"#{r['no']}", fill=(0, 0, 0), font=F13)
            yy += 18
        if mark == "prev":
            d.text((x + 3, yy), "직전 정지", fill=(0, 0, 120), font=F12)
            yy += 16
        elif mark == "next":
            d.text((x + 3, yy), "직후 정지", fill=(120, 50, 0), font=F12)
            yy += 16
        elif mark == "end":
            d.text((x + 3, yy), "끝(뒤 정지", fill=(120, 50, 0), font=F12)
            d.text((x + 3, yy + 14), "  없음)", fill=(120, 50, 0), font=F12)
            yy += 30
        if r.get("skipped"):
            d.text((x + 3, yy), f"생략 {r['skipped']}장", fill=(150, 0, 0), font=F12)
            d.text((x + 3, yy + 15), f"{r['skip_from']}~", fill=(150, 0, 0), font=F12)
            d.text((x + 3, yy + 30), f"{r['skip_to']}", fill=(150, 0, 0), font=F12)
        if r.get("tag"):
            d.text((x + 3, y + sh - 18), r["tag"], fill=(60, 60, 60), font=F12)
        im.paste(Image.fromarray(r["img"]), (x + LABEL_W, y))
    return im


def save(im: Image.Image, p: Path):
    im.save(p, quality=95, subsampling=0)


def short(ms: int) -> str:
    """분:초.0.01초(같은 0.1초에 프레임이 둘 들어와도 겹치지 않게)."""
    d = hc.datetime.fromtimestamp(ms / 1000, hc.KST)
    return d.strftime("%M:%S") + f".{d.microsecond // 10000:02d}"


def main():
    gid = sys.argv[1]
    sheets_name = sys.argv[sys.argv.index("--out-sheets") + 1] if "--out-sheets" in sys.argv else "sheets"
    cf = hc.config(gid)
    side = cf["side"]
    sband = cf.get("sheet_band") or cf["band"]
    od = hc.out_dir(gid)
    sd = od / sheets_name
    sd.mkdir(exist_ok=True)
    for p in sd.glob("*.jpg"):
        p.unlink()
    seg = hc.jload(od / "segments.json")
    rs = hc.jload(od / "river_states.json") if (od / "river_states.json").exists() else {"segments": {}}
    z = np.load(hc.WORK / f"{gid}_feat.npz")
    off = seg["feat_index0"]
    ms_all = z["ms"]
    x0, y0, x1, y1 = sband
    bh, bw = (x1 - x0, y1 - y0) if hc.ROT[side] in (90, 270) else (y1 - y0, x1 - x0)
    L = layout(bw, bh)
    per_sheet = L["rows"] * L["cols"]
    still = {s["k"]: s for s in seg["still"]}
    index = {"id": gid, "version": "v2", "band": cf["band"], "sheet_band": sband, "side": side, "band_view_wh": [bw, bh],
             "sheet_scale": L["scale"], "sheet_cols": L["cols"], "rows_per_sheet": per_sheet, "sheets_dir": sheets_name,
             "skip": {"level": SKIP_LEVEL, "frac": SKIP_FRAC, "skin_below": SKIP_SKIN,
                      "on": "sheet_band 회색 1/4 축소, 마지막으로 남긴 줄과 비교. 띠 피부 비율이 skin_below 이상이면 생략 안 함"},
             "segments": [], "still_sheets": []}
    tot_rows = tot_frames = 0
    for a in seg["active"]:
        pv, nx = still.get(a["prev_still"]), still.get(a["next_still"])
        items = []  # (feat 인덱스, mark)
        if pv is not None:
            items.append((pv["i1"] + off, "prev"))
        items += [(i + off, None) for i in range(a["i0"], a["i1"] + 1)]
        if nx is not None:
            items.append((nx["i0"] + off, "next"))
        kept, last, skipped = [], None, []
        for j, (fi, mark) in enumerate(items):
            ms = int(ms_all[fi])
            v = hc.band_crop(hc.load(ms), sband, side)
            g = small_gray(v)
            sk = skin_frac(v)
            final = j == len(items) - 1
            if final and mark is None:
                mark = "end"  # 뒤 정지 상태가 없는 구간의 마지막 줄
            keep = mark is not None or last is None or final or sk >= SKIP_SKIN or (np.abs(g - last) > SKIP_LEVEL).mean() > SKIP_FRAC
            if keep:
                r = {"fi": fi, "ms": ms, "mark": mark, "img": scaled(v, L), "skin": round(sk, 4)}
                if skipped:
                    r["skipped"], r["skip_from"], r["skip_to"] = len(skipped), short(skipped[0]), short(skipped[-1])[3:]
                kept.append(r)
                skipped = []
                last = g
            else:
                skipped.append(ms)
        for n, r in enumerate(kept, 1):
            r["time"] = short(r["ms"])
            r["no"] = n
        files = []
        npages = (len(kept) + per_sheet - 1) // per_sheet
        for p in range(npages):
            part = kept[p * per_sheet:(p + 1) * per_sheet]
            sc = f" · 띠 {L['scale']}배" if L["scale"] != 1.0 else ""
            hdr = (f"{gid}  구간 {a['seg']}  {short(a['ms0'])}–{short(a['ms1'])} ({a['dur']}초)  장 {p + 1}/{npages}  "
                   f"줄 {p * per_sheet + 1}–{p * per_sheet + len(part)}/{len(kept)}  · 대국자 시점(아래 = 화료자, 왼쪽 = 화료자 왼손 쪽){sc}")
            im = make_sheet(part, hdr, L)
            fn = f"seg_{a['seg']:03d}_p{p + 1}.jpg"
            save(im, sd / fn)
            files.append(f"{sheets_name}/{fn}")
        # 넓은 화면
        idx = list(range(a["i0"], a["i1"] + 1))
        pick = [idx[int(round(t))] for t in np.linspace(0, len(idx) - 1, min(WIDE_N, len(idx)))]
        kms = np.array([r["ms"] for r in kept])
        thumbs, wide_rows = [], []
        for i in pick:
            ms = int(ms_all[i + off])
            near = kept[int(np.argmin(np.abs(kms - ms)))]
            v = hc.band_crop(hc.load(ms), cf["wide"], side)
            t = Image.fromarray(v).resize((round(v.shape[1] * WIDE_SCALE), round(v.shape[0] * WIDE_SCALE)), Image.LANCZOS)
            dd = ImageDraw.Draw(t)
            dd.rectangle([0, 0, 112, 18], fill=(255, 255, 255))
            dd.text((3, 1), f"{short(ms)}  #{near['no']}", fill=(0, 0, 0), font=F13)
            thumbs.append(t)
            wide_rows.append({"t": hc.hms(ms), "frame": f"f_{ms}.jpg", "nearest_row": near["no"]})
        tw, th = thumbs[0].size
        ncol = 2
        nr = (len(thumbs) + 1) // 2
        W = ncol * tw + 8
        wim = Image.new("RGB", (W, HEADER + nr * (th + 6)), (255, 255, 255))
        ImageDraw.Draw(wim).text((6, 4), f"{gid}  구간 {a['seg']}  넓은 화면 {len(thumbs)}장({WIDE_SCALE} 배 축소)  {short(a['ms0'])}–{short(a['ms1'])}"
                                 f"  · 대국자 시점 — 화료자 손패 줄이 아래쪽 · #n = 가장 가까운 띠 줄 번호", fill=(0, 0, 0), font=F15)
        for k, t in enumerate(thumbs):
            c, rr = k % 2, k // 2
            wim.paste(t, (c * (tw + 8), HEADER + rr * (th + 6)))
        assert max(wim.size) <= MAX_SIDE, wim.size
        wfn = f"seg_{a['seg']:03d}_wide.jpg"
        save(wim, sd / wfn)
        rv = rs["segments"].get(str(a["seg"]), {})
        index["segments"].append({
            "seg": a["seg"], "t0": a["t0"], "t1": a["t1"], "dur": a["dur"], "frames": a["n"], "rows": len(kept),
            "rows_skipped": a["n"] + (pv is not None) + (nx is not None) - len(kept), "sheets": files, "wide": f"{sheets_name}/{wfn}",
            "wide_rows": wide_rows,
            "prev_still": None if pv is None else {"k": pv["k"], "t0": pv["t0"], "t1": pv["t1"], "frame": f"f_{int(ms_all[pv['i1'] + off])}.jpg"},
            "next_still": None if nx is None else {"k": nx["k"], "t0": nx["t0"], "t1": nx["t1"], "frame": f"f_{int(ms_all[nx['i0'] + off])}.jpg"},
            "band_frames": a.get("band_frames"), "river_frames": a.get("river_frames"), "max_skin": a["max_skin"],
            "river": {k: rv.get(k) for k in ("river_new", "river_gone", "river_changed", "river_count", "meld_new", "meld_gone", "meld_count")} if rv else None,
            "row_list": [{"no": r["no"], "t": hc.hms(r["ms"]), "frame": f"f_{r['ms']}.jpg", "mark": r["mark"], "skipped_before": r.get("skipped", 0),
                          "skin": r["skin"]} for r in kept]})
        for r in kept:
            r.pop("img", None)
        tot_rows += len(kept)
        tot_frames += a["n"]
        print(f"구간 {a['seg']:3d} {a['t0']} {a['dur']:5.1f}s 프레임 {a['n']:4d} 줄 {len(kept):4d} 장 {npages}", flush=True)
    # 정지 상태 목록
    rows = []
    for s in seg["still"]:
        mid = (s["i0"] + s["i1"]) // 2 + off
        ms = int(ms_all[mid])
        nxt = [a["seg"] for a in seg["active"] if a["prev_still"] == s["k"]]
        rows.append({"ms": ms, "time": short(ms), "img": scaled(hc.band_crop(hc.load(ms), sband, side), L), "no": f"정지{s['k']}",
                     "tag": f"{s['dur']}s" + (f" →{nxt[0]}" if nxt else "")})
    npg = (len(rows) + per_sheet - 1) // per_sheet
    for p in range(npg):
        part = rows[p * per_sheet:(p + 1) * per_sheet]
        hdr = f"{gid}  정지 상태 목록 {p + 1}/{npg}  (정지 구간마다 가운데 프레임, 시간순, 왼쪽 열 먼저)"
        fn = f"still_p{p + 1}.jpg"
        save(make_sheet(part, hdr, L), sd / fn)
        index["still_sheets"].append(f"{sheets_name}/{fn}")
    index["still"] = [{"k": s["k"], "t0": s["t0"], "t1": s["t1"], "dur": s["dur"], "frame": f"f_{int(ms_all[(s['i0'] + s['i1']) // 2 + off])}.jpg"}
                      for s in seg["still"]]
    index["totals"] = {"segments": len(seg["active"]), "frames": tot_frames, "rows": tot_rows,
                       "sheets": sum(len(x["sheets"]) for x in index["segments"]), "wide": len(index["segments"]), "still_sheets": npg}
    hc.jsave(od / "index.json", index)
    print(index["totals"], "배율", L["scale"], "열", L["cols"], "장당 줄", per_sheet)


if __name__ == "__main__":
    main()
