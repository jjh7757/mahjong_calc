"""손 관절 덧그림 영상(2026-11-20) — handcheck.py 의 확인 그림(낱장)과 같은 덧그림을 한 차례 통째로 mp4 로.

  python -X utf8 handvideo.py r16_d03,L16_d05 [--png 135,142] [--fps 5] [--width 1280] [--xray]
  → _work/handvideo_1120/<id>.mp4(+ 확인용 <id>_fNNN.png) · --xray 면 <id>_xray.mp4(+ <id>_xray_fNNN.png)

입력: _work/hands_1120/<id>/ov_GPU_w220.json(프레임별 손 관절, band2 좌표) · frames_w220.json(ms · 넓힌 띠 · side · dx · dy).
  프레임 그림은 handcheck 처럼 hc.band_crop(hc.load(ms), band, side) 로 프레임마다 다시 자름(초당 10장 전부).
덧그림(넓힌 띠 원본 위에 반투명으로 하나만):
  칸 틀 = handevents.grid_src(tid)(줄 위 · 아래 선, 칸 경계 세로선, 칸 번호 1 ~ n · 바깥 0 · n+1 은 회색),
  그 사람 손(handevents 규칙 — handcheck.own_rows 로 고른 손 번호, frame_states 와 같은지 check_same 으로 확인) = 노랑 뼈대,
  다른 손 = 회색, 그 사람 손 검지 끝(8) 빨간 점 · 엄지 끝(4) 파란 점, 지난 10프레임(1초) 검지 끝 궤적 = 빨간 꼬리.
  위 띠: 차례 · 프레임 번호 · 시각 · 검지 끝 상태(frame_states(tid, "_w220", "index"))와 칸.
  아래 띠: 손끝 사건(handevents.events) · 칸 틀 사건(slotgrid events — 패 검출 상자 기준, 칸 번호는 slotgrid 틀)
    중 시작 시각이 지금부터 2초 안인 줄(한 줄씩, 넘치면 자름).
재생: 원본 초당 10장을 --fps(기본 5)로 — 2배 느리게. 인코딩은 imageio-ffmpeg 의 ffmpeg 로 libx264 · yuv420p(그림은 파이프로 넘겨 중간 파일 없음).
--xray(11-20): 손에 가린 손패를 보이게 — 기억 조각(마지막으로 깨끗이 보인 화소, 반투명 · 점선 · "기억 n.n초") ·
  손가락 틈의 패 등 색 화소 강조 · 위 띠 셋째 줄에 장수 세기(줄에 보임 a · 손 밑 기억 b · 합). 규칙은 xray.py 머리글.
  뼈대는 더 얇고 옅게(기억 조각을 가리지 않게). 지어내지 않음 — 영상 복원 · 생성 모델 없음.
정답은 읽지 않음.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import handcheck as hk  # noqa: E402
import handevents as he  # noqa: E402
import htcommon as hc  # noqa: E402
import xray as xr  # noqa: E402

SRC = hc.WORK / "hands_1120"
OUT = hc.WORK / "handvideo_1120"
TAG = "_w220"
TRAIL = 10          # 지난 1초(초당 10장)
SHOW_SEC = 2.0      # 사건 줄을 보여 주는 시간
FONT = "C:/Windows/Fonts/malgun.ttf"
FONT_B = "C:/Windows/Fonts/malgunbd.ttf"
TOP_H, LINE_H, BOT_LINES = 58, 22, 4


def font(size: int, bold: bool = False):
    try:
        return ImageFont.truetype(FONT_B if bold else FONT, size)
    except OSError:
        return ImageFont.truetype(FONT, size)


def sec_of_hour(s: str) -> float:
    mm, ss = s.split(":")
    return int(mm) * 60 + float(ss)


def slot_name(k, n) -> str:
    if k is None:
        return ""
    if k == 0:
        return "왼쪽 밖(0)"
    if k == n + 1:
        return f"끝 옆({n + 1})"
    return f"{k}번 칸"


def grid_events(tid: str) -> list:
    """slotgrid events 출력 → [(시각 초(시간 안), 글)]. 머리 줄 · 끝 줄 · 맺음 괄호 줄은 뺌."""
    import slotgrid as sg
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sg.cmd_events(argparse.Namespace(ids=[tid], count=False))
    out = []
    for ln in buf.getvalue().splitlines():
        m = re.match(r"\s+(\d{2}:\d{2}\.\d)(?:\(프레임 \d+\))?\s+(.*)$", ln)
        if m:
            out.append((sec_of_hour(m.group(1)), "칸 틀 " + m.group(1) + "  " + m.group(2).strip()))
    return out


def hand_events(tid: str):
    """handevents.events 출력 → [(시작 프레임, 글)] · frame_states 의 rows · n."""
    n, rows, _, _, _ = he.frame_states(tid, TAG, "index")
    out = []
    for ln in he.events(rows, n):
        m = re.match(r"(\d{3})~(\d{3})\(SAM 2 [^,]+, ([^)]+)\)\s+(.*)$", ln)
        if not m:
            raise RuntimeError(f"{tid}: 손끝 사건 줄 꼴이 다름 — {ln}")
        out.append((int(m.group(1)), f"손끝 {m.group(1)}~{m.group(2)}({m.group(3)})  {m.group(4)}"))
    return out, rows, n


def fit(d: ImageDraw.ImageDraw, s: str, f, w: int) -> str:
    if d.textlength(s, font=f) <= w:
        return s
    while s and d.textlength(s + "…", font=f) > w:
        s = s[:-1]
    return s + "…"


def render(rgb: np.ndarray, scale: float, grid: tuple, n: int, dxy: tuple, hands: list, own, trail: list,
           head1: str, head2: str, lines: list, xray: bool = False, head3: str | None = None) -> Image.Image:
    left0, pitch, top, bot, _ = grid
    dx, dy = dxy
    H, W = rgb.shape[:2]
    Ws, Hs = int(round(W * scale)) // 2 * 2, int(round(H * scale))
    base = Image.fromarray(rgb).resize((Ws, Hs), Image.LANCZOS).convert("RGBA")
    lay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)

    def P(x, y):   # band2 그림 좌표 → 넓힌 띠 · 줄인 그림 화소
        return ((x - dx) * scale, (y - dy) * scale)

    # 칸 틀(얇은 흰 선, 반투명)
    gx0, gx1 = P(left0 - pitch, 0)[0], P(left0 + (n + 1) * pitch, 0)[0]
    for yy in (top, bot):
        y = P(0, yy)[1]
        d.line([(gx0, y), (gx1, y)], fill=(255, 255, 255, 120), width=1)
    for k in range(n + 1):
        x = P(left0 + k * pitch, 0)[0]
        d.line([(x, P(0, top)[1]), (x, P(0, bot)[1])], fill=(255, 255, 255, 120), width=1)
    fs = font(max(10, int(round(12 * max(scale, 0.9)))))
    ytxt = P(0, top)[1] - fs.size - 3
    for k in range(n + 2):
        cx = P(left0 + (k - 0.5) * pitch, 0)[0]
        s = str(k)
        tw = d.textlength(s, font=fs)
        col = (255, 255, 255, 200) if 1 <= k <= n else (160, 160, 160, 200)
        d.text((cx - tw / 2 + 1, ytxt + 1), s, font=fs, fill=(0, 0, 0, 160))
        d.text((cx - tw / 2, ytxt), s, font=fs, fill=col)
    # 손 — 다른 손 먼저, 그 사람 손을 맨 위에
    lw = max(1, int(round(1.6 * scale))) if not xray else 1
    dot = max(1.5, 1.6 * scale) if not xray else 1.0
    order = [j for j in range(len(hands)) if j != own] + ([own] if own is not None else [])
    for j in order:
        pts = [P(x, y) for x, y in hands[j]["lm"]]
        mine = j == own
        col = ((255, 230, 0, 170) if mine else (170, 170, 170, 140)) if not xray else ((255, 230, 0, 95) if mine else (170, 170, 170, 70))
        for a, b in hk.CONN:
            d.line([pts[a], pts[b]], fill=col, width=lw)
        for x, y in pts:
            d.ellipse([x - dot, y - dot, x + dot, y + dot], fill=col)
    # 검지 끝 꼬리(지난 1초, 오래된 것일수록 옅게)
    m = len(trail)
    for q in range(1, m):
        a, b = trail[q - 1], trail[q]
        if a is None or b is None:
            continue
        al = int(60 + 160 * q / max(1, m - 1))
        d.line([P(*a), P(*b)], fill=(255, 40, 40, al), width=max(2, lw))
    if own is not None:
        pts = [P(x, y) for x, y in hands[own]["lm"]]
        r = max(3.0, 3.2 * scale)
        for t, c in ((4, (40, 120, 255, 230)), (8, (255, 40, 40, 230))):
            x, y = pts[t]
            d.ellipse([x - r, y - r, x + r, y + r], fill=c, outline=(0, 0, 0, 200))
    img = Image.alpha_composite(base, lay).convert("RGB")
    # 위 · 아래 글 띠
    bot_h = BOT_LINES * LINE_H + 8
    top_h = TOP_H + (LINE_H + 2 if head3 else 0)
    canvas = Image.new("RGB", (Ws, top_h + Hs + bot_h), (16, 16, 16))
    canvas.paste(img, (0, top_h))
    c = ImageDraw.Draw(canvas)
    c.text((8, 4), fit(c, head1, font(20, True), Ws - 16), font=font(20, True), fill=(255, 255, 255))
    c.text((8, 32), fit(c, head2, font(15), Ws - 16), font=font(15), fill=(200, 200, 200))
    if head3:
        c.text((8, 55), fit(c, head3, font(17, True), Ws - 16), font=font(17, True), fill=(255, 190, 60))
    fe = font(15)
    y0 = top_h + Hs + 4
    for q, (kind, s) in enumerate(lines[-BOT_LINES:]):
        col = (255, 220, 120) if kind == "hand" else (150, 210, 255)
        c.text((8, y0 + q * LINE_H), fit(c, s, fe, Ws - 16), font=fe, fill=col)
    if canvas.size[1] % 2:
        canvas = canvas.crop((0, 0, canvas.size[0], canvas.size[1] - 1))
    return canvas


def make(tid: str, fps: float, width: int, png: list | None, ff: str, xray: bool = False) -> dict:
    n, grid, rows, meta, src = hk.own_rows(tid)
    hk.check_same(tid, rows)
    hev, st_rows, n2 = hand_events(tid)
    assert n2 == n
    gev = grid_events(tid)
    fj = hc.jload(SRC / tid / f"frames{TAG}.json")
    band, side, dxy = fj["band"], fj["side"], (fj["dx"], fj["dy"])
    N = len(rows)
    # 확인 프레임: 지정 없으면 마지막 "강 쪽" 시작 · 그 3프레임 앞(줄에 머묾) · 가장 긴 1 ~ n 칸 머묾의 가운데 · 첫 강 쪽
    if png is None:
        river = [a for a, s in hev if "강 쪽" in s]
        dwell = []
        for a, s in hev:
            mm = re.search(r"(\d{3})~(\d{3}).*줄 위 (\d+)번 칸에 머묾", s)
            if mm:
                dwell.append((int(mm.group(2)) - int(mm.group(1)), (int(mm.group(1)) + int(mm.group(2))) // 2))
        png = []
        if river:
            png += [river[-1], max(0, river[-1] - 3)]
            if len(river) > 1:
                png.append(river[0])
        if dwell:
            png.append(max(dwell)[1])
        png = sorted(set(png))[:4]
    OUT.mkdir(parents=True, exist_ok=True)
    suf = "_xray" if xray else ""
    out = OUT / f"{tid}{suf}.mp4"
    X = xr.XRay(tid, fj, n) if xray else None
    counts = []
    proc = None
    size = None
    trail_pts: list = []
    for k, r in enumerate(rows):
        ms = meta[r["i"]]["ms"]
        assert r["i"] == k
        rgb = hc.band_crop(hc.load(ms), band, side)
        scale = min(1.0, width / rgb.shape[1])
        tip = r["hands"][r["own"]]["lm"][8] if r["own"] is not None else None
        trail_pts.append(tip)
        trail = trail_pts[-(TRAIL + 1):]
        st = r["state"] or "없음"
        sl = slot_name(r["slot_index"], n) if r["state"] else ""
        head1 = f"{tid}  프레임 {k:03d}/{N - 1:03d}  {r['t']}  검지 끝: {st}" + (f" · {sl}" if sl else "")
        head2 = (f"손 {len(r['hands'])}개 · 노랑 = 그 사람 손 · 회색 = 다른 손 · 빨강 = 검지 끝(꼬리 1초) · 파랑 = 엄지 끝"
                 f" · 칸 틀 {src} · 0.5배속")
        head3 = None
        if X is not None:
            rgb, info = X.step(k, ms, rgb, r["hands"])
            counts.append(info["a"] + info["b"])
            head3 = (f"시작 {n}장 · 줄에 보임 {info['a']} · 손 밑 기억 {info['b']} · 합 {info['a'] + info['b']}"
                     f"   (주황 점선 = 기억: 가리기 전 마지막 모습 · 하늘색 = 손가락 틈으로 지금 보이는 패 등)")
        now = (ms / 1000) % 3600
        lines = []
        for a, s in hev:   # (지난 초, 종류, 글) — 오래된 것이 위, 새것이 아래
            if 0 <= (k - a) / 10 < SHOW_SEC:
                lines.append(((k - a) / 10, "hand", s))
        for t, s in gev:
            dt = (now - t + 1800) % 3600 - 1800
            if -0.05 <= dt < SHOW_SEC:
                lines.append((dt, "grid", s))
        lines.sort(key=lambda x: -x[0])
        img = render(rgb, scale, grid, n, dxy, r["hands"], r["own"], trail, head1, head2, [(kd, s) for _, kd, s in lines],
                     xray=X is not None, head3=head3)
        if proc is None:
            size = img.size
            proc = subprocess.Popen([ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                     "-s", f"{size[0]}x{size[1]}", "-r", str(fps), "-i", "-",
                                     "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20",
                                     "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)
        assert img.size == size, (img.size, size)
        proc.stdin.write(img.tobytes())
        if k in png:
            img.save(OUT / f"{tid}{suf}_f{k:03d}.png")
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"{tid}: ffmpeg 실패({proc.returncode})")
    res = {"id": tid, "mp4": out.as_posix(), "frames": N, "fps": fps, "sec": round(N / fps, 1), "size": size,
           "bytes": out.stat().st_size, "png": [(OUT / f"{tid}{suf}_f{k:03d}.png").as_posix() for k in png],
           "hand_events": len(hev), "grid_events": len(gev), "grid_src": src}
    if X is not None:
        runs = []
        for k, c in enumerate(counts):   # 합 장수가 이어진 구간 [합, 첫 프레임, 끝 프레임]
            if runs and runs[-1][0] == c:
                runs[-1][2] = k
            else:
                runs.append([c, k, k])
        res["xray"] = {"color": X.color, "count_runs": runs, "off_n_n1": sum(c not in (n, n + 1) for c in counts),
                       "gap_px_med": float(np.median(X.stats["gap_px"])), "gap_px_outband_med": float(np.median(X.stats["gap_px_outband"])),
                       "gap_px_outband_max": int(max(X.stats["gap_px_outband"]))}
    print(res)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids")
    ap.add_argument("--fps", type=float, default=5.0, help="재생 초당 장수(원본 초당 10장 — 5 면 2배 느리게)")
    ap.add_argument("--width", type=int, default=1280, help="가로가 이보다 크면 줄임(키우지는 않음)")
    ap.add_argument("--png", default=None, help="확인용으로 남길 프레임 번호(쉼표) — 없으면 손끝 사건으로 골라 서너 장")
    ap.add_argument("--xray", action="store_true", help="손에 가린 손패 보이게(기억 조각 · 틈 강조 · 장수 세기) → <id>_xray.mp4")
    a = ap.parse_args()
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    png = [int(x) for x in a.png.split(",")] if a.png else None
    for tid in a.ids.split(","):
        make(tid, a.fps, a.width, png, ff, a.xray)


if __name__ == "__main__":
    main()
