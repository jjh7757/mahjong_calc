"""Opus 에이전트가 프레임을 스스로 골라 열고 · 확대해 읽기(2026-11-18 밤, 계획서 3단계 "추가 36").

Gemini Flash 는 지시 · 그림 · 답 꼴 · 생각 수준을 바꿔도 r13 2순 · r16 13 · 16순을 늘 같은 틀린 답으로 냈다(표 12-51 ~ 12-56).
"이 그림에서 추적 오류를 찾을 수 있는 모델이 있기는 한가" 를 본다 — 낱장을 골라 열고 잘라 키울 수 있는 에이전트(11-17 정답 둘째 읽기에서 24 중 23 ~ 24).

  python -X utf8 opusread.py prep  [--ids hard8]   # → _work/opusread_1118/<id>/ : TASK.md · frames.txt · check/*.jpg (정답 · 다른 답은 안 넣음)
  python -X utf8 opusread.py score [--ids hard8]   # answer.json 채점 + Gemini 꼴들과 나란히
읽는 쪽 = 하위 에이전트 하나가 차례 하나 — TASK.md 만 읽고 answer.json 하나만 쓴다.
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import sam2img as si  # noqa: E402
import sam2llm as m  # noqa: E402
import sam2track as s1  # noqa: E402
import sam2verify as sv  # noqa: E402

OUT = hc.WORK / "opusread_1118"

TASK = """# 손패 줄 한 차례 읽기 — 추적 오류를 찾아 바로잡기

너는 위에서 내려다본 녹화에서 마작 대국자 한 사람의 **세운 손패 줄**을 한 차례 읽는다. 패는 세워져 있어 위에서는 등(색 띠)과 흰 면만 보이고 **모든 패가 똑같이 생겼다** — 읽는 것은 위치뿐이다.
이 차례 = 패산에서 한 장을 뽑아 오고(뽑은 패 = **D**), 한 장을 강에 버림. 차례를 시작할 때 줄은 **{n}장**이다.

## 재료(이 폴더 밖의 파일은 아래 경로만 연다)
- `frames.txt` — 프레임 목록: `번호 · 시각 · 색 칠한 그림 경로 · 원본 그림 경로`. 초당 5장, {F}장. 그림은 그 사람 시점으로 돌려져 있다(그림 왼쪽 = 그 사람 왼손 쪽, 아래쪽 흰 띠 = 탁자 테두리). 다른 사람 팔이 지나가기도 한다.
- **색 칠한 그림:** 영상 추적 모델(SAM 2)이 첫 프레임에서 줄의 {n}장에 왼쪽부터 숫자 1 ~ {n} 을 붙이고, 그 뒤 프레임마다 "같은 패" 라고 본 곳에 같은 색 · 숫자를 칠했다. D 에는 숫자가 없다. **추적은 틀릴 수 있다:**
  - 손에 들려 혼자 움직이는 패는 대체로 따라간다.
  - 버린 패의 색은 이웃 패로 옮겨 붙는 일이 많다(한 패에 숫자 둘).
  - 손이 줄을 덮은 동안 줄이 밀리거나 패가 끼워지면, 숫자가 한 칸씩 밀려 앉거나 옛 자리로 뛰어 돌아온다. 그러면 끝 프레임의 숫자는 가지런해 보여도 실제 패와 어긋나고, 숫자 없는 패가 D 가 아닐 수 있다.
- `check/` — 코드가 찾은 **"두 숫자가 한 패에 겹친 순간"** 마다 확인 그림(위 = 차례 시작 줄 · 가운데 = 그 순간 원본 · 아래 = 그 순간 색 칠한 것, 손패 줄 부분만 2배). 파일 이름 = `m<순간>_<겹치기전|첫|풀림>_<프레임 번호>.jpg`. 겹침은 흔하다(추적이 맞는 차례에도 생긴다) — 확인할 곳일 뿐 틀린 곳이라는 뜻은 아니다.

## 하는 법
- 그림은 `Read` 로 연다. 필요하면 Python(PIL)으로 원본 그림을 잘라 키워서 `{work}` 아래에만 저장해 연다(다른 곳에 쓰지 않는다).
- **패는 사라지지 않는다.** 줄의 패 수는 {n} → D 를 줄에 놓으면 {n}+1 → 한 장 버리면 {n}. 손이 덮은 순간에는 원본을 확대해 손가락 밑 패까지 센다. 숫자 하나하나에 대해 "그 패는 지금 실제로 어디 있나" 를 원본에서 확인한다 — 말로 넘기지 않는다.
- D 를 끝에 붙여 두고 한 장을 버리는 사람, 버린 뒤 D 를 다시 집어 안쪽에 끼우는 사람, D 를 먼저 안쪽에 끼우고 버리는 사람, 버리기 전에 패를 옮기거나 맞바꾸는 사람이 다 있다. 끝 프레임까지 본다.

## 보면 안 되는 것(보면 이 읽기는 못 쓴다)
- 이 폴더(`{dir}`)의 `TASK.md` · `frames.txt` · `check/` 와 frames.txt 에 적힌 그림 파일, 그리고 네가 만든 `{work}` 말고는 아무 파일도 열거나 검색하지 않는다. 특히 `docs/` · `HANDOFF.md` · `truth*` · `answers*` · `read_*` · `sam2verify_1118` · `sam2stage_1118` · `sam2llm_1118` · 다른 차례 폴더는 열지 않는다. 화소 규칙 · 추적 스크립트를 돌려 답을 얻지 않는다 — 눈으로 읽는다.

## 답
`{dir}/answer.json` 한 파일만 쓴다:
```json
{{"id": "{tid}", "kind": "hand 또는 tsumogiri", "k": 버린 패가 원래 줄 {n}장에서 왼쪽부터 몇 번째였나(D 는 세지 않음, tsumogiri 면 null),
 "j": 차례가 끝났을 때 D 가 줄({n}장)의 왼쪽부터 몇 번째인가(끝 그대로면 {n}, tsumogiri 면 null),
 "end_order": ["끝 줄 왼쪽부터 실제 패 — 원래 번호 \\"1\\" ~ \\"{n}\\" 또는 \\"D\\""], "unsure": 맞을 가능성 70% 밑이면 true,
 "tracking_errors": "추적이 틀린 곳과 그렇게 본 근거(시각 · 프레임 번호)", "why": "근거 3 ~ 5문장(시각 · 프레임 번호와 함께)"}}
```
마지막 답변은 "k · j 와 확신 여부" 한 줄이면 된다.
"""


def prep(tid: str):
    d = OUT / tid
    (d / "check").mkdir(parents=True, exist_ok=True)
    (d / "work").mkdir(exist_ok=True)
    meta = hc.jload(si.frame_dir(tid, "M") / "meta.json")
    run = s1.run_dir(tid, si.V1)
    labs = [hc.mss(ms) for ms in meta["frames"]]
    lines = [f"{i:03d} {labs[i]} {(si.frame_dir(tid, 'M') / f'{i:05d}.jpg').as_posix()} {(run / 'frames' / f'{i:05d}.jpg').as_posix()}" for i in range(len(labs))]
    (d / "frames.txt").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    for k, mo in enumerate(sv.moments(tid), 1):
        pr = " · ".join(f"{a}·{b}" for a, b in mo["pairs"])
        for role, fi in (("겹치기전", mo["start"] - 1), ("첫", mo["start"]), ("풀림", mo["end"])):
            if fi < 0:
                continue
            title = f"확인 {k} — {labs[mo['start']]} 숫자 {pr} 한 패에 겹침 · 이 그림 = {role} {labs[fi]} (프레임 {fi:03d})"
            Image.open(io.BytesIO(sv.check_image(tid, fi, title))).save(d / "check" / f"m{k}_{role}_{fi:03d}.jpg", quality=90)
    task = TASK.format(n=meta["n"], F=len(labs), tid=tid, dir=d.as_posix(), work=(d / "work").as_posix())
    (d / "TASK.md").write_bytes(task.encode("utf-8"))
    print(tid, len(labs), "장 · 확인 그림", len(list((d / "check").glob("*.jpg"))), "장 →", d)


TASK_RAW_NOTE = """
## 이 차례만 다른 점(추가 39)
- 이 차례는 끝 줄을 코드가 못 찾아 **SAM 2 추적이 없다** — `frames.txt` 의 그림은 모두 **원본**(색 · 숫자 없음)이고 `check/` 도 없다. 위의 "색 칠한 그림" · "check/" 설명은 건너뛰고 원본만으로 읽는다. 프레임은 차례 시작 줄부터 차례 창 끝까지다.
"""


def prep_raw(tid: str):
    """SAM 2 계획이 실패한 차례(r19 4순 — 끝 줄 없음): 시작 줄부터 창 끝까지 원본 띠만 잘라 같은 꼴로."""
    import slotgrid as sg
    d = OUT / tid
    (d / "raw").mkdir(parents=True, exist_ok=True)
    (d / "work").mkdir(exist_ok=True)
    gid, t = s1.turn_of(tid)
    cfg = hc.config(gid)
    det = {int(k): v for k, v in hc.jload(sg.OUT / f"det_{gid}.json").items()}
    n = t["n_calc"]
    w0, w1 = sg.window(t)
    frs = [(ms, det[ms]) for ms in sorted(det) if w0 <= ms <= w1]
    a = sg.anchor(frs, n)
    band2 = s1.wide_band(cfg["sheet_band"])
    start = a[4]
    order = [x["id"] for x in next(g for g in hc.jload(hc.WORK / "testtruth_1116" / "turns.json")["games"] if g["id"] == gid)["turns"]]
    prev = order[order.index(tid) - 1] if order.index(tid) > 0 else None
    if prev and (s1.run_dir(prev, si.V1) / "track.json").exists():   # 앞 차례 끝 줄 뒤부터(창이 겹치면 앞 차례 버림이 섞임)
        start = max(start, hc.jload(s1.run_dir(prev, si.V1) / "track.json")["plan"]["e_ms"])
    fs = [int(x) for x in hc.frames(hc.rec_of(start)) if start <= x <= w1][::2]
    lines = []
    for i, ms in enumerate(fs):
        p = d / "raw" / f"{i:05d}.jpg"
        if not p.exists():
            Image.fromarray(hc.band_crop(hc.load(ms), band2, cfg["side"])).save(p, quality=95)
        lines.append(f"{i:03d} {hc.mss(ms)} {p.as_posix()} {p.as_posix()}")
    (d / "frames.txt").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    task = TASK.format(n=n, F=len(fs), tid=tid, dir=d.as_posix(), work=(d / "work").as_posix()) + TASK_RAW_NOTE
    (d / "TASK.md").write_bytes(task.encode("utf-8"))
    print(tid, len(fs), "장(원본만) →", d)


# 11-20 사용자 "Opus 에게 SAM 2 없이 원본과 사건 목록만 준 판 재봐" — 기준 = 이 파일의 prep(SAM 2 그림 + 원본 + 확인 그림, 11-18 하위 에이전트 25/25).
# 바뀐 것: SAM 2 색 그림 · 확인 그림을 빼고(원본은 이 폴더 raw/ 로 복사 — SAM 2 결과 폴더에 마스크가 같이 있어서), 칸 틀 사건 목록(events.txt)과
# claudeagent.MOTION_SECTION 의 "움직인 때부터" 규칙(SAM 2 숫자 말은 뺌)을 넣음. 답 꼴 · 보면 안 되는 것 · 하는 법의 나머지는 TASK 와 같음.
TASK_NOSAM = """# 손패 줄 한 차례 읽기

너는 위에서 내려다본 녹화에서 마작 대국자 한 사람의 **세운 손패 줄**을 한 차례 읽는다. 패는 세워져 있어 위에서는 등(색 띠)과 흰 면만 보이고 **모든 패가 똑같이 생겼다** — 읽는 것은 위치뿐이다.
이 차례 = 패산에서 한 장을 뽑아 오고(뽑은 패 = **D**), 한 장을 강에 버림. 차례를 시작할 때 줄은 **{n}장**이다. 첫 프레임의 줄 {n}장을 왼쪽부터 원래 번호 1 ~ {n} 으로 부른다.

## 재료(이 폴더 밖의 파일은 열지 않는다)
- `frames.txt` — 프레임 목록: `번호 · 시각 · 원본 그림 경로`(이 폴더의 `raw/`). 초당 5장, {F}장. 그림은 그 사람 시점으로 돌려져 있다(그림 왼쪽 = 그 사람 왼손 쪽, 아래쪽 흰 띠 = 탁자 테두리). 다른 사람 팔이 지나가기도 한다. 그림에 색 · 숫자는 없다.
- `events.txt` — **칸 틀 사건 목록**: 코드가 패 검출 상자로 줄의 칸이 차고 빈 때를 적은 것(시각 옆 괄호가 프레임 번호). 손이 덮은 칸 밑은 못 본다.

## 하는 법
- 그림은 `Read` 로 연다. 필요하면 Python(PIL)으로 원본 그림을 잘라 키워서 `{work}` 아래에만 저장해 연다(다른 곳에 쓰지 않는다).
- 읽기 전에 **패가 실제로 움직인 때**(D 를 줄에 놓음 · 패를 뺌 · 버림 · 줄을 밂 · 끼움 · 옮김 · 맞바꿈)를 먼저 찾아 차례의 사건 순서를 세운다. `events.txt` 가 출발점이다. 목록은 손이 덮은 칸 밑을 못 보므로 손 가림 구간은 원본으로 확인한다.
- **패는 사라지지 않는다.** 줄의 패 수는 {n} → D 를 줄에 놓으면 {n}+1 → 한 장 버리면 {n}. 손이 덮은 순간에는 원본을 확대해 손가락 밑 패까지 센다. 패 하나하나에 대해 "그 패는 지금 실제로 어디 있나" 를 원본에서 확인한다 — 말로 넘기지 않는다.
- 손이 덮은 동안 패를 옮겼다(끼움 · 맞바꿈)고 보려면 원본에서 그 동작의 흔적을 확인한다: 손이 패를 들고 움직임 · 칸이 비었다 참 · 끝 패가 그 자리에서 사라짐 · 줄 길이가 바뀜. 흔적을 못 찾으면 "움직이지 않음" 쪽에 무게를 두고, 그래도 옮겼다고 답하면 why 에 그 흔적을 프레임 번호로 적는다.
- D 를 끝에 붙여 두고 한 장을 버리는 사람, 버린 뒤 D 를 다시 집어 안쪽에 끼우는 사람, D 를 먼저 안쪽에 끼우고 버리는 사람, 버리기 전에 패를 옮기거나 맞바꾸는 사람이 다 있다. 끝 프레임까지 본다.

## 보면 안 되는 것(보면 이 읽기는 못 쓴다)
- 이 폴더(`{dir}`)의 `TASK.md` · `frames.txt` · `events.txt` · `raw/`, 그리고 네가 만든 `{work}` 말고는 아무 파일도 열거나 검색하지 않는다. 특히 `docs/` · `HANDOFF.md` · `truth*` · `answers*` · `read_*` · `opusread_1118` · `claudeagent_1119` · `geminiagent_1118` · `sam2*` 폴더 · 다른 차례 폴더는 열지 않는다. 화소 규칙 · 추적 스크립트를 돌려 답을 얻지 않는다 — 눈으로 읽는다.

## 답
`{dir}/answer.json` 한 파일만 쓴다:
```json
{{"id": "{tid}", "kind": "hand 또는 tsumogiri", "k": 버린 패가 원래 줄 {n}장에서 왼쪽부터 몇 번째였나(D 는 세지 않음, tsumogiri 면 null),
 "j": 차례가 끝났을 때 D 가 줄({n}장)의 왼쪽부터 몇 번째인가(끝 그대로면 {n}, tsumogiri 면 null),
 "end_order": ["끝 줄 왼쪽부터 실제 패 — 원래 번호 \\"1\\" ~ \\"{n}\\" 또는 \\"D\\""], "unsure": 맞을 가능성 70% 밑이면 true,
 "events_used": "사건 목록에서 쓴 줄과 원본으로 바로잡은 곳(프레임 번호)", "why": "근거 3 ~ 5문장(시각 · 프레임 번호와 함께)"}}
```
마지막 답변은 "k · j 와 확신 여부" 한 줄이면 된다.
"""


# 11-20 사용자 "단서로 붙여 봐" — TASK_NOSAM 에 손 관절 사건(hand_events.txt) 절 하나만 더함(--hands, --root rawhand_1120).
# 알려진 버릇(표 12-89, 53차례)을 함께 적어 그대로 믿지 않게 함.
TASK_HAND_SECTION = """
## 손 관절 사건(`hand_events.txt`) — 단서
- 코드가 손 관절 모델(MediaPipe Hands)로 그 사람 손의 **검지 끝**을 따라가 적은 것: 손끝이 줄의 어느 칸에 0.2초 넘게 머물렀나, 줄 위쪽(강 · 패산 쪽)이나 아래쪽(몸 쪽)으로 벗어났나. 프레임 번호는 frames.txt 와 같다. 칸 번호는 첫 프레임 줄 기준(1 ~ {n} = 시작 줄 자리, 0 = 왼쪽 밖, {n1} = 오른쪽 끝 옆)이라 줄이 밀리면 한 칸쯤 어긋난다.
- 알려진 버릇: 줄 끝 패를 바깥에서 쥐면 손끝이 칸 밖(0 · {n1})으로 잡힌다 · 손이 빠르게 강으로 나가면 "강 쪽" 이 빠질 수 있다 · "강 쪽" 은 패산에서 뽑아 올 때도 나온다 · 손이 화면 밖에서 오는 자리는 잡힌 프레임이 적다(맨 위 줄의 "손이 잡힌 프레임" 을 본다).
- 손 사건은 **어디를 볼지와 사건 순서를 세우는 단서**다. 손이 패를 옮긴 것처럼 보이면 그 프레임의 원본으로 확인한다. 손 사건과 원본이 다르면 원본을 따른다.
"""


def prep_nosam(tid: str, hands: bool = False):
    """SAM 2 없이 원본(SAM 2 에 넣은 것과 같은 띠 · 같은 프레임) + 사건 목록(+ hands 면 손 관절 사건). 원본은 이 폴더로 하드링크(안 되면 복사)."""
    import os
    import re
    import shutil
    import claudeagent as ca
    import geminiagent as ga
    d = OUT / tid
    (d / "raw").mkdir(parents=True, exist_ok=True)
    (d / "work").mkdir(exist_ok=True)
    meta = hc.jload(si.frame_dir(tid, "M") / "meta.json")
    run = s1.run_dir(tid, si.V1)
    labs = [hc.mss(ms) for ms in meta["frames"]]
    lines = []
    for i in range(len(labs)):
        p = d / "raw" / f"{i:05d}.jpg"
        if not p.exists():
            try:
                os.link(run / "frames" / f"{i:05d}.jpg", p)
            except OSError:
                shutil.copyfile(run / "frames" / f"{i:05d}.jpg", p)
        lines.append(f"{i:03d} {labs[i]} {p.as_posix()}")
    (d / "frames.txt").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    ev = ca.events_text(ga.Turn(tid))   # 메인 스레드에서 하나씩(redirect_stdout 주의)
    assert ev.startswith(f"== {tid} ·"), ev[:80]
    (d / "events.txt").write_bytes((ev + "\n").encode("utf-8"))
    task = TASK_NOSAM.format(n=meta["n"], F=len(labs), tid=tid, dir=d.as_posix(), work=(d / "work").as_posix())
    if hands:
        src = (hc.WORK / "hands_1120" / tid / "hand_events_w220.txt").read_text(encoding="utf-8")
        # "107~118(SAM 2 053~059, 58:44.6~58:45.8)" → "053~059(58:44.6~58:45.8)" — 읽는 쪽 프레임 번호(초당 5장)로
        txt = re.sub(r"\b\d{3}~\d{3}\(SAM 2 (\d{3})~(\d{3}), ([^)]+)\)", r"\1~\2(\3)", src)
        txt = txt.replace("초당 10장, 0.2초 넘게 이어진 것", "0.2초 넘게 이어진 것 · 프레임 번호는 frames.txt 와 같음")
        txt = re.sub(r" · 칸 틀: 왼쪽 끝 x \d+ · 한 장 폭 [\d.]+ · 줄 높이 y \d+~\d+ · 첫 프레임 상자 \d+", "", txt)
        assert "SAM 2" not in txt, txt[:200]
        (d / "hand_events.txt").write_bytes(txt.encode("utf-8"))
        task = task.replace("- `events.txt` — **칸 틀 사건 목록**", "- `hand_events.txt` — **손 관절 사건**(아래 절)\n- `events.txt` — **칸 틀 사건 목록**")
        task = task.replace("`TASK.md` · `frames.txt` · `events.txt` · `raw/`", "`TASK.md` · `frames.txt` · `events.txt` · `hand_events.txt` · `raw/`")
        task = task.replace("`opusread_1118` · `claudeagent_1119`", "`opusread_1118` · `rawread_1120` · `hands_1120` · `claudeagent_1119`")
        task = task.replace("\n## 보면 안 되는 것", TASK_HAND_SECTION.format(n=meta["n"], n1=meta["n"] + 1) + "\n## 보면 안 되는 것")
        assert task.count("hand_events.txt") >= 3
    (d / "TASK.md").write_bytes(task.encode("utf-8"))
    print(tid, len(labs), "장(원본만) · 사건 목록", len(ev), "자" + (" · 손 사건 있음" if hands else ""), "→", d)


def cmd_score(a):
    truth = s1.truth_all()
    T = 0
    for tid in sv.ids_of(a.ids):
        f = OUT / tid / "answer.json"
        if not f.exists():
            print(tid, "답 없음")
            continue
        r = hc.jload(f)
        ok = m.right(m.norm(r), truth[tid])
        T += ok
        kj = sv.from_order(r.get("end_order") or [], s1.turn_of(tid)[1]["n_calc"])   # 11-19: 13 고정 → 차례의 줄 장수(L16 울기 뒤 10)
        print(f"{tid:8s} 정답 {truth[tid].get('kind')} {truth[tid].get('k_id')}·{truth[tid].get('j_closed')} | Opus {r.get('kind')} {r.get('k')}·{r.get('j')}{'?' if r.get('unsure') else ''} {'✓' if ok else '✗'} | 끝 순서→{kj}")
    print(f"맞음 {T}/{len(sv.ids_of(a.ids))}")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("prep", "score"):
        q = sp.add_parser(name)
        q.add_argument("--ids", default="hard8")
        q.add_argument("--root", default="opusread_1118", help="_work 아래 폴더 — 다른 모델 읽기는 따로(추가 41: sonnetread_1118)")
        if name == "prep":
            q.add_argument("--raw", action="store_true", help="SAM 2 없이 원본 띠만(추가 39 — r19 4순)")
            q.add_argument("--nosam", action="store_true", help="SAM 2 없이 원본 + 칸 틀 사건 목록(11-20, --root rawread_1120)")
            q.add_argument("--hands", action="store_true", help="--nosam 에 손 관절 사건 더함(11-20, --root rawhand_1120)")
    a = ap.parse_args()
    global OUT
    OUT = hc.WORK / a.root
    if a.cmd == "prep":
        for tid in sv.ids_of(a.ids):
            if a.nosam:
                prep_nosam(tid, a.hands)
            elif a.raw:
                prep_raw(tid)
            else:
                prep(tid)
    else:
        cmd_score(a)


if __name__ == "__main__":
    main()
