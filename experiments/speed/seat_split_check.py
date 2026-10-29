"""서버 app/seat.py 에 넣은 나눠 잡기(frame(hand_frac=))가 오프라인 실험(seat_zones.py frames)과 같은 틀을 내는지.

  python -I -X utf8 experiments/speed/seat_split_check.py

서버 코드를 그대로 부른다: 지금(hand_frac 없음) / 나눔 추가(hand_frac 있음 — 한 장 규칙이 못 잡을 때만 나눠 잡기).
TABLE=1 이면 "나눔 추가" 를 탁자 끝 밖을 지운 사진으로(seat.frame(table=True), 사용자 제안 10-28) — 그림도 탁자 밖을 어둡게.
사전 손패 줄(고정 카메라)은 서버에 없어 쓰지 않는다(seat_zones.py 의 USE_LINE=0 과 같은 조건).
"""
from __future__ import annotations

import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import seat_prior as sp  # noqa: E402
import seat_zones as sz  # noqa: E402

from app import seat  # noqa: E402  (seat_zones 가 서버 경로를 넣는다)

TABLE = os.environ.get("TABLE", "0") == "1"
seat.TABLE_PAD = float(os.environ.get("TABLE_PAD", seat.TABLE_PAD))  # 탁자 끝 여유(폭 비율) 바꿔 보기


def judge(fr, c) -> str:
    if fr is None:
        return "없음"
    right = len(fr.hand) == c["hand"] and fr.separate is None and len(fr.melds) == c["melds"]
    return ("OK" if right else "틀림") + ("(나눔)" if fr.split else "")


def draw(rgb, fr, frac: float, path: Path) -> None:
    """틀 그림: 파란 세로선 = 손패 칸·모서리 칸 경계, 초록 = 손패(번호), 노랑 = 떨어진 패, 주황·빨강 = 울기 묶음, 회색 = loose."""
    from PIL import Image, ImageDraw, ImageFont

    region = seat.table_region(rgb) if TABLE else None
    shown = rgb.copy()
    if region is not None:
        shown[~region] = (shown[~region] * 0.35).astype(shown.dtype)  # 탁자 밖(검출에서 지운 곳)은 어둡게
    im = Image.fromarray(shown)
    d = ImageDraw.Draw(im)
    lw = max(3, im.width // 400)
    size = max(20, im.height // 14)
    try:
        f = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", size)  # 한글 이름표
    except OSError:
        f = ImageFont.load_default(size=size)
    split = int(im.width * frac)
    d.line([split, 0, split, im.height], fill=(0, 140, 255), width=lw * 2)
    if fr is not None:
        for i, (x, y, w, h) in enumerate(fr.hand):
            d.rectangle([x, y, x + w, y + h], outline=(0, 200, 0), width=lw)
            d.text((x + 4, y - f.size - 2), str(i + 1), fill=(0, 200, 0), font=f)
        if fr.separate:
            x, y, w, h = fr.separate
            d.rectangle([x, y, x + w, y + h], outline=(255, 220, 0), width=lw)
        for j, m in enumerate(fr.melds):
            col = [(255, 140, 0), (230, 30, 30), (200, 0, 200), (120, 60, 0)][j % 4]
            for x, y, w, h in m:
                d.rectangle([x, y, x + w, y + h], outline=col, width=lw)
            d.text((m[0][0], m[0][1] + m[0][3] + 2), f"울기{j + 1}", fill=col, font=f)
        for x, y, w, h in fr.loose:
            d.rectangle([x, y, x + w, y + h], outline=(150, 150, 150), width=lw)
    im.thumbnail((1600, 1600))
    im.save(path)


def main(dump: Path | None = None) -> None:
    det = sp.detector()
    rows = []
    for c in sz.cases():
        if dump and "울기+" in c["name"]:
            continue
        rgb = c["rgb"]
        t0 = time.perf_counter()
        now = seat.frame(rgb, det)
        t1 = time.perf_counter()
        new = seat.frame(rgb, det, hand_frac=sz.HAND_FRAC[c["scene"]], table=TABLE)
        t2 = time.perf_counter()
        rows.append((c, judge(now, c), judge(new, c), t1 - t0, t2 - t1))
        if dump:
            stem = c["name"].replace(" ", "_")
            draw(rgb, new, sz.HAND_FRAC[c["scene"]], dump / f"{stem}_frame.png")
            if new is not None:
                (dump / f"{stem}_sheet.jpg").write_bytes(seat.sheet(rgb, new))
        print(f"{c['name']:18s} 손패 {c['hand']:2d}·울기 {c['melds']} | 지금 {rows[-1][1]:8s} {t1 - t0:.2f}s | 나눔 추가 "
              f"{rows[-1][2]:10s} {t2 - t1:.2f}s {new.summary() if new else ''}", flush=True)
    for i, lab in ((1, "지금"), (2, "나눔 추가")):
        orig = [r for r in rows if "울기+" not in r[0]["name"]]
        syn = [r for r in rows if "울기+" in r[0]["name"]]
        bad = sum(r[i].startswith("틀림") for r in rows)
        print(f"{lab}: 원본 {sum(r[i].startswith('OK') for r in orig)}/{len(orig)} · 울기 합성 "
              f"{sum(r[i].startswith('OK') for r in syn)}/{len(syn)} · 검사 통과한 틀린 틀 {bad}")
    print(f"틀 시간(노트북) 중앙 지금 {statistics.median(r[3] for r in rows):.2f}초 · 나눔 추가 "
          f"{statistics.median(r[4] for r in rows):.2f}초, 최대 {max(r[3] for r in rows):.2f} · {max(r[4] for r in rows):.2f}")


if __name__ == "__main__":
    # --dump 폴더: 원본 6장의 틀 그림(_frame.png)과 Gemini 에 보내는 조각 그림(_sheet.jpg)을 저장(울기 합성은 건너뜀).
    i = sys.argv.index("--dump") if "--dump" in sys.argv else -1
    out = Path(sys.argv[i + 1]) if i >= 0 else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    main(out)
