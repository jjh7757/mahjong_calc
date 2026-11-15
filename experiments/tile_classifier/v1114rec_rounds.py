"""11-14 헤드 녹화에만 있는 구간(14:46:54~15:47:17) 판 나누기·프레임 고르기(2026-11-15, 학습·개발 자료 1단계 B).

녹화 `experiments/visit_20261114/head_rec/rec_20261114_125617/` 는 읽기만 한다(f_<epoch ms>.jpg, 1496², 초당 10장).
판 경계 시각은 사람이 대조표를 눈으로 보고 정해 아래 ROUNDS 표에 적었다(new/rounds_manual.json 으로도 내보냄).
이 표만 있으면 고르기·복사·결과 파일을 처음부터 다시 만든다.

규칙(미리 정함 — 결과를 보고 바꾸지 않는다):
  - 시각 넷: t_start = 첫 버림이 나오기 직전, t_end_play = 마지막 버림 뒤·공개 시작 전, t_reveal = 공개 손패가 가장 온전히 보이는
    프레임(눈으로 고름, 없으면 None), t_clear = 패를 밀어 넣기 시작한 때(없으면 None).
  - 진행 중: t_start~t_end_play 를 np.linspace 8개(양 끝 포함) → 가장 가까운 녹화 프레임. 손·흔들림이 있어도 바꾸지 않는다.
  - 공개: t_reveal 프레임 1장.
  - 판 id n01_<HHMMSS(t_start)> 부터 시간순.
  - 나눔: 진행 시간 >= 90초 인 판만 18번부터 이어 세어 4의 배수 번째 = dev, 나머지와 90초 미만 = train.
  - scene_round: 고른 프레임에 앞 판 탁자가 남아 있으면 앞 판(SCENE_OVERRIDE 에 적음). 이번에는 없음.
  - 복사: data/v1114rec/images/rec1496/<split>/<판>/new_<ms>.jpg (바이트 그대로).

  python -X utf8 experiments/tile_classifier/v1114rec_rounds.py
결과 data/v1114rec/new/{rounds.json, rounds_manual.json, picks.json, overview_<판>.jpg, timeline.jpg}
"""
from __future__ import annotations

import bisect
import datetime as dt
import json
import os
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REC = ROOT / "experiments" / "visit_20261114" / "head_rec" / "rec_20261114_125617"
OUT = HERE / "data" / "v1114rec"
NEW = OUT / "new"
IMG = OUT / "images" / "rec1496"
KST = dt.timezone(dt.timedelta(hours=9))
SEG_FROM, SEG_TO = "14:46:54.5", "15:47:17.1"  # 태블릿 기록 끝(r22 마지막 화료 사진) ~ 녹화 끝
PICK = 8
MIN_PLAY_SEC = 90.0
FIRST_NUM = 18  # 기존 세트가 17번까지 셌다
DEV_EVERY = 4

# 눈으로 정한 값(대조표 data/v1114rec/new/_work/). 시각은 한국 시각 2026-11-14.
ROUNDS = [
    dict(t_start="14:47:48.5", t_end_play="14:55:12.4", t_reveal="14:55:30.0", t_clear="14:55:52.5", back="분홍", result="화료(쯔모/론 모름)",
         note="아래 자리 공개. 첫 버림(위 자리 14:47:49.4) 때 왼쪽·아래 손패가 아직 덜 세워짐. 14:46:54~14:47:04 은 r22 탁자(보라, 왼쪽 공개)가 남은 구간, 14:47:05 밀어 넣기, 14:47:13 새 패산"),
    dict(t_start="14:56:25.0", t_end_play="15:04:18.6", t_reveal="15:04:29.9", t_clear="15:04:44.5", back="보라", result="화료(쯔모/론 모름)",
         note="위 자리 공개. 첫 버림(왼쪽 14:56:25.5) 때 아래·왼쪽 손패 아직 세우는 중"),
    dict(t_start="15:05:28.2", t_end_play="15:13:13.6", t_reveal="15:13:28.0", t_clear="15:13:40.0", back="분홍", result="화료(쯔모 추정)",
         note="왼쪽 자리 공개(15:13:20 무렵), 점봉이 여러 자리에서 감. 첫 버림(아래 15:05:28.8) 때 아래 손패 덜 세움. 공개 앞 15:13:14~19 왼쪽 아래 손이 패를 다룸 — t_end_play 를 위 자리 버림 뒤로 잡음(경계 약간 애매)"),
    dict(t_start="15:14:10.2", t_end_play="15:18:08.6", t_reveal="15:18:11.7", t_clear="15:19:01.5", back="보라", result="화료(쯔모/론 모름)",
         note="오른쪽 자리 공개(15:18:10). 첫 버림 오른쪽 15:14:10.4~12.6 — 같은 때 위 자리 팔이 가운데로 뻗음(도라 표시 뒤집기로 봄), 아래 손패는 아직 놓는 중"),
    dict(t_start="15:19:53.5", t_end_play="15:24:49.0", t_reveal="15:24:53.0", t_clear="15:25:04.0", back="분홍", result="화료(쯔모/론 모름)",
         note="위 자리 공개(15:24:51). 첫 버림 위 자리 15:19:54.1"),
    dict(t_start="15:25:45.5", t_end_play="15:29:07.0", t_reveal="15:29:19.0", t_clear="15:29:36.0", back="보라", result="쯔모(추정)",
         note="위 자리 공개(15:29:09.6). 오른쪽 버림(15:29:05.2) 뒤 위 자리가 패산에서 뽑고 공개, 노란 봉이 세 자리에서 감 → 쯔모 추정"),
    dict(t_start="15:30:10.3", t_end_play="15:37:15.4", t_reveal="15:37:20.0", t_clear="15:37:35.0", back="분홍", result="화료(쯔모/론 모름)",
         note="아래 자리 공개(15:37:17.8), 울기 있음. 첫 버림 위 자리 15:30:10.9"),
    dict(t_start="15:38:25.6", t_end_play="15:44:52.0", t_reveal="15:45:07.0", t_clear=None, back="보라", result="화료(쯔모/론 모름)",
         note="왼쪽 자리 공개(15:44:53.6), 점봉 많이 오감. 밀어 넣기 없음 — 15:45:35 부터 왼쪽이 패를 흩고 15:46 부터 휴대폰·태블릿을 탁자 위에서 다룸, "
              "15:47:02 부터 카메라를 들어 올림(판 아님, 안 넣음)"),
]
SCENE_OVERRIDE: dict[str, str] = {}  # 그림 id → 앞 판 id (앞 판 탁자가 남은 프레임). 이번에는 없음.


def tms(s: str) -> int:
    h, m, sec = s.split(":")
    base = dt.datetime(2026, 11, 14, int(h), int(m), 0, tzinfo=KST)
    return int(round(base.timestamp() * 1000 + float(sec) * 1000))


def hms(ms: int, nd: int = 1) -> str:
    s = dt.datetime.fromtimestamp(ms / 1000, KST).strftime("%H:%M:%S.%f")
    return s[: 9 + nd] if nd else s[:8]


def iso(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, KST).isoformat(timespec="milliseconds")


def scan() -> list[int]:
    return sorted(int(e.name[2:-4]) for e in os.scandir(REC) if e.name.startswith("f_") and e.name.endswith(".jpg"))


def nearest(ms: list[int], t: int) -> int:
    i = bisect.bisect_left(ms, t)
    c = [ms[j] for j in (i - 1, i) if 0 <= j < len(ms)]
    return min(c, key=lambda x: abs(x - t))


def font(px: int):
    try:
        return ImageFont.truetype("malgun.ttf", px)
    except OSError:
        return ImageFont.load_default()


def thumb(m: int, th: int) -> Image.Image:
    im = Image.open(REC / f"f_{m}.jpg")
    im.draft("RGB", (th * 2, th * 2))
    return im.convert("RGB").resize((th, th))


def main():
    NEW.mkdir(parents=True, exist_ok=True)
    ms = scan()
    (NEW / "rounds_manual.json").write_text(json.dumps({"made_by": "눈 확인(대조표 new/_work/)", "rounds": ROUNDS}, ensure_ascii=False, indent=1), encoding="utf-8")
    rounds, picks = [], []
    num = FIRST_NUM - 1
    for k, r in enumerate(ROUNDS, 1):
        a, b = tms(r["t_start"]), tms(r["t_end_play"])
        assert a < b
        rid = f"n{k:02d}_{hms(a, 0).replace(':', '')}"
        play = (b - a) / 1000
        if play >= MIN_PLAY_SEC:
            num += 1
            n90, split = num, ("dev" if num % DEV_EVERY == 0 else "train")
        else:
            n90, split = None, "train"
        want = [("play", int(round(t))) for t in np.linspace(a, b, PICK)]
        if r["t_reveal"]:
            want.append(("end", tms(r["t_reveal"])))
        got = []
        for ph, t in want:
            m = nearest(ms, t)
            pid = f"{rid}/new_{m}"
            got.append({"id": pid, "round": rid, "rec_file": f"f_{m}.jpg", "ms": m, "at": iso(m), "want_at": iso(t),
                        "off_ms": m - t, "phase": ph, "scene_round": SCENE_OVERRIDE.get(pid, rid)})
        assert len({g["ms"] for g in got}) == len(got), rid
        rounds.append({"id": rid, "num90": n90, "split": split, "play_sec": round(play, 1), "back": r["back"], "result": r["result"],
                       "t_start": iso(a), "t_end_play": iso(b), "t_reveal": iso(tms(r["t_reveal"])) if r["t_reveal"] else None,
                       "t_clear": iso(tms(r["t_clear"])) if r["t_clear"] else None, "note": r["note"], "picked": len(got)})
        picks += got
    rs = {r["id"]: r["split"] for r in rounds}
    for p in picks:
        p["split"] = rs[p["scene_round"]]
        src = REC / p["rec_file"]
        dst = IMG / p["split"] / p["round"] / f"new_{p['ms']}.jpg"
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            shutil.copyfile(src, dst)
        p["path"] = dst.relative_to(OUT).as_posix()
    # 다른 판 폴더에 남은 옛 복사본(표를 고친 뒤 다시 돌린 경우) 정리 — n.. 폴더만
    keep = {p["path"] for p in picks}
    for d in IMG.glob("*/n*"):
        for f in d.glob("new_*.jpg"):
            if f.relative_to(OUT).as_posix() not in keep:
                f.unlink()
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    meta = {"source": REC.relative_to(ROOT).as_posix(), "segment": [SEG_FROM, SEG_TO], "rules": {
        "pick_play": "t_start~t_end_play np.linspace 8개(양 끝 포함), 가장 가까운 프레임, 바꾸지 않음", "pick_end": "t_reveal 1장",
        "split": f"진행 >= {MIN_PLAY_SEC:.0f}초 판만 {FIRST_NUM}번부터, {DEV_EVERY}의 배수 = dev", "script": "v1114rec_rounds.py"},
        "not_rounds": [
            {"from": "14:46:54.5", "to": "14:47:48.5", "what": "r22 탁자(보라, 왼쪽 손패 공개)가 14:47:04 까지 남음 → 14:47:05 밀어 넣기 → 14:47:13 새 패산 → 배패"},
            {"from": "15:45:35", "to": "15:47:17.1", "what": "n08 공개 뒤 패를 흩음, 휴대폰·태블릿 다룸, 15:47:02 부터 카메라를 들어 옮김"}],
        "rounds": rounds}
    (NEW / "rounds.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    (NEW / "picks.json").write_text(json.dumps(picks, ensure_ascii=False, indent=1), encoding="utf-8")
    # 판별 대조표: 고른 9장
    th, f = 420, font(26)
    for r in rounds:
        ps = [p for p in picks if p["round"] == r["id"]]
        cols = 3
        S = Image.new("RGB", (cols * th, ((len(ps) + cols - 1) // cols) * th + 40), "black")
        ImageDraw.Draw(S).text((6, 6), f"{r['id']}  {r['split']}  {r['back']}  play {r['play_sec']}s  {r['result']}", fill="white", font=f)
        for i, p in enumerate(ps):
            im = thumb(p["ms"], th)
            d = ImageDraw.Draw(im)
            d.rectangle([0, 0, th, 34], fill="black")
            d.text((4, 3), f"{i + 1} {p['phase']} {hms(p['ms'])} new_{p['ms']}"[:40], fill="yellow" if p["phase"] == "play" else "cyan", font=font(20))
            S.paste(im, ((i % cols) * th, 40 + (i // cols) * th))
        S.save(NEW / f"overview_{r['id']}.jpg", quality=85)
    # 구간 전체 대조표: 15초마다, 판 진행=초록 테두리, 공개~치움=하늘, 그 밖=빨강
    a0, a1 = tms(SEG_FROM), tms(SEG_TO)
    step, th, cols = 15000, 160, 16
    ts = list(range(a0, a1, step))
    spans = []
    for r, raw in zip(rounds, ROUNDS):
        s0, s1 = tms(raw["t_start"]), tms(raw["t_end_play"])
        e1 = tms(raw["t_clear"]) if raw["t_clear"] else a1
        spans.append((r["id"], s0, s1, e1))
    rows = (len(ts) + cols - 1) // cols
    S = Image.new("RGB", (cols * th, rows * th + 30), "black")
    ImageDraw.Draw(S).text((4, 4), "15s step | green=play(t_start~t_end_play) cyan=end(~t_clear) red=not round | label=round id at t_start",
                           fill="white", font=font(18))
    for i, t in enumerate(ts):
        m = nearest(ms, t)
        im = thumb(m, th)
        d = ImageDraw.Draw(im)
        col, lab = "red", ""
        for rid, s0, s1, e1 in spans:
            if s0 <= m <= s1:
                col, lab = "lime", rid[:3]
            elif s1 < m <= e1:
                col, lab = "cyan", rid[:3] + " end"
        d.rectangle([0, 0, th - 1, th - 1], outline=col, width=5)
        d.rectangle([5, 5, 120, 24], fill="black")
        d.text((7, 6), f"{hms(m, 0)} {lab}", fill="yellow", font=font(13))
        S.paste(im, ((i % cols) * th, 30 + (i // cols) * th))
    for rid, s0, s1, e1 in spans:  # 판 시작 칸에 큰 표시
        i = (s0 - a0) // step
        x, y = (i % cols) * th, 30 + (i // cols) * th
        ImageDraw.Draw(S).text((x + 8, y + th - 30), f"> {rid}", fill="white", font=font(18))
    S.save(NEW / "timeline.jpg", quality=80)
    print(json.dumps({"rounds": [{k: r[k] for k in ("id", "num90", "split", "play_sec", "back", "result", "picked")} for r in rounds],
                      "picks": len(picks), "by_split": {s: sum(p["split"] == s for p in picks) for s in ("train", "dev")},
                      "max_off_ms": max(abs(p["off_ms"]) for p in picks)}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
