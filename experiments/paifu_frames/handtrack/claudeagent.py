"""geminiagent.py 의 Claude 판 — 같은 지시문 · 재료 · 도구 5개로 손패 한 차례를 Claude API(Opus 5.5)가 읽게 하기(2026-11-19).

Gemini g3(표 12-62) · Pro(표 12-65)와 모델만 바꿔 견주려는 것: 지시문 = geminiagent.PROMPT(strip 줄 포함 g3 판), 재료 = geminiagent.Turn
(_work/opusread_1118/<id>/frames.txt · check/), 도구 = view · zoom · check · strip · answer(그림 만들기는 geminiagent 것을 그대로 씀),
첫 메시지 · 결과 꼴 · k·j 계산(sam2verify.from_order)도 같다.
refusal 에 fallbacks(다른 모델로 다시 돌리기)는 넣지 않는다 — 한 모델의 읽기를 재는 실험이라 다른 모델이 답하면 숫자가 섞인다.

  python -X utf8 claudeagent.py dry --ids r16_d13                    # API 를 부르지 않는 점검(키 없이 돎)
  python -X utf8 claudeagent.py run --ids r16_d13 [--tag c1] [--model claude-opus-5-5] [--effort high] [--max-steps 60] [--max-usd 5] [--workers 1] [--force] [--src opusread_1118]
  python -X utf8 claudeagent.py score --ids hard8 [--tag c1]
결과 _work/claudeagent_1119/<tag>/<id>.json — 정답 · 다른 판독 답은 안 넣음.

API 쪽은 claude-api 스킬 문서(python/claude-api/README.md · tool-use.md · streaming.md, shared/prompt-caching.md · tool-use-concepts.md ·
model-migration.md "Migrating to Claude Opus 5.5")와 설치된 anthropic 1.15.0 의 타입 정의대로 썼다:
- 수동 루프: 응답 content 전체(thinking 포함)를 assistant 로 그대로 붙이고, 한 응답의 tool_result 는 한 user 메시지에, 오류는 is_error.
- 캐싱: system 마지막 블록에 cache_control + 최상위 cache_control(자동 — 대화 끝 블록으로 따라감). 지시문 · 도구 · 모델 · effort 는 차례 안에서 안 바꿈.
- Opus 5.5: thinking 은 안 줌(= adaptive), 깊이는 output_config.effort, tool_choice 는 auto(기본), temperature · budget_tokens 없음.
- 그림: 요청에 그림이 20장을 넘으면 장마다 3000 화소 넘는 변이 거절됨(vision 문서 "many-image requests") → 긴 변이 LONG_EDGE(2576 —
  Opus 5.5 가 어차피 줄이는 크기)를 넘는 그림만 보내기 전에 줄임. 요청당 그림 600장 · 128MB 한도 앞에서 마지막 단계로 넘어감.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geminiagent as ga  # noqa: E402
import htcommon as hc  # noqa: E402
import sam2llm as m  # noqa: E402
import sam2track as s1  # noqa: E402
import sam2verify as sv  # noqa: E402

OUT = hc.WORK / "claudeagent_1119"
SRC = ga.SRC
MODEL = "claude-opus-5-5"
# 100만 토큰당 달러: (입력, 출력 — 생각 토큰 포함, 캐시 읽기, 캐시 쓰기 5분) — model-migration.md "Pricing" 과 같음
PRICE = {"claude-opus-5-5": (4.0, 20.0, 0.20, 5.0),
         "claude-sonnet-5-5": (2.0, 10.0, 0.10, 2.5)}
MAX_VIEW = ga.MAX_VIEW
LONG_EDGE = 2576            # Opus 5.5 · Sonnet 5.5 의 최대 원래 해상도(긴 변) — 넘는 그림은 API 가 줄임
MAX_IMAGES = 560            # 요청당 600장 한도 앞에서 멈춤
MAX_BYTES = 120 * 2 ** 20   # 요청 128MB 한도 앞에서 멈춤(base64 그림 바이트 합으로 어림)
ENV = "C:/Users/jjh7757/Downloads/부트캠프/.env"
FINAL_TEXT = "볼 수 있는 단계를 다 썼다. 지금까지 본 것으로 answer 를 불러라(확신이 낮으면 unsure 를 true 로)."
NUDGE_TEXT = "도구로 더 보거나, 다 봤으면 answer 를 불러라."
FIRST_TAIL = "도구로 필요한 프레임을 보며 읽고, 다 보면 answer 를 불러라."
FINAL_EXTRA = 2             # 마지막 단계 글을 넣은 뒤 answer 를 기다려 줄 호출 수(Gemini 는 tool_config ANY 로 강제했지만 Opus 5.5 는 forced tool_choice 가 400)

# --variant color(11-19 저녁, 사용자 "지시문을 sam 2출력의 오류를 잡아내는 거라 하고 받는 프레임을 color로만 제한"):
# 일 = SAM 2 출력의 추적 오류를 잡아 바로잡기, 그림 = color 만(도구에 kind 인자 없음 · 확인 그림은 가운데 원본 칸을 잘라 냄).
# 답 꼴 · 첫 메시지 · 한도 · 그 밖 문장은 base(g3) 와 맞춤 — 바뀐 곳만 견주려고.
PROMPT_COLOR = """너는 영상 추적 모델(SAM 2)의 출력에서 **추적 오류를 잡아내고 바로잡는다**. 재료는 위에서 내려다본 녹화의 한 차례, 마작 대국자 한 사람의 **세운 손패 줄** 부분이다. SAM 2 는 첫 프레임에서 줄의 {n}장에 왼쪽부터 숫자 1 ~ {n} 과 색을 붙이고, 그 뒤 프레임마다 "같은 패" 라고 본 곳에 같은 색 · 숫자를 칠했다. 패는 세워져 있어 위에서는 등(색 띠)과 흰 면만 보이고 **모든 패가 똑같이 생겼다** — SAM 2 도 너도 위치와 움직임으로만 패를 가린다.
이 차례 = 패산에서 한 장을 뽑아 오고(뽑은 패 = **D**, 숫자 없음), 한 장을 강에 버림. 차례를 시작할 때 줄은 **{n}장**이다. 그림은 그 사람 시점(그림 왼쪽 = 그 사람 왼손 쪽, 아래쪽 흰 띠 = 탁자 테두리). 다른 사람 팔이 지나가기도 한다.

## 재료(도구로 본다)
- 프레임 {F}장(초당 5장, 번호 0 ~ {last}). **모두 SAM 2 가 색 · 숫자를 칠한 그림이다 — 원본은 주지 않는다.** 칠이 없는 곳(손 · 탁자 · D · 추적이 놓친 패)은 화면 그대로 보인다.
- **확인 그림**(check): 코드가 찾은 "두 숫자가 한 패에 겹친 순간" 마다 위 = 차례 시작 줄 · 아래 = 그 순간(손패 줄 부분 2배). 겹침은 흔하다(추적이 맞는 차례에도) — 확인할 곳일 뿐이다.

## SAM 2 가 자주 틀리는 꼴
- 손에 들려 혼자 움직이는 패는 대체로 따라간다.
- 버린 패의 색은 이웃 패로 옮겨 붙는 일이 많다(한 패에 숫자 둘).
- 손이 줄을 덮은 동안 줄이 밀리거나 패가 끼워지면 숫자가 한 칸씩 밀려 앉거나 옛 자리로 뛰어 돌아온다 — 그러면 끝 프레임의 숫자는 가지런해 보여도 실제 패와 어긋나고, 숫자 없는 패가 D 가 아닐 수 있다.
- 손이 덮으면 칠이 사라지기도 하고, 숫자가 손 · 다른 패 같은 엉뚱한 곳에 붙기도 한다.

## 도구
- `view(frames)` — 프레임 여러 장(한 번에 {mv}장까지)을 본다.
- `zoom(frame, x0, x1, y0, y1)` — 한 프레임의 일부를 잘라 3배로 키워 본다(좌표는 그 프레임 그림의 화소, 그림 크기 {W} × {H}). y0 · y1 을 비우면 높이 전체.
- `check(name)` — 확인 그림 한 장을 본다.
- `strip(start, end, step, x0, x1, y0, y1)` — **같은 영역**을 start ~ end 프레임에서 step 장마다 잘라 시간순으로 위아래로 쌓아 본다(줄마다 왼쪽에 프레임 번호, 한 장에 {sr}줄씩 · 한 번에 {sm}줄까지). 숫자 하나가 손 밑에서 어떻게 옮겨 갔는지 이어서 볼 때 쓴다.
- `answer(...)` — 답을 낸다. 부르면 끝난다.

## 하는 법
- **숫자를 그대로 믿지 않는다.** 숫자 하나하나가 프레임 사이에 어떻게 옮겨 갔는지 따라가며 "이 이동이 실제 패의 움직임으로 말이 되나" 를 따진다. **패는 사라지지 않는다:** 줄의 패 수는 {n} → D 를 줄에 놓으면 {n}+1 → 한 장 버리면 {n}. 칠이 없는 패도 센다. 숫자가 손을 따라가지 않고 이웃 패로 건너뛰거나, 패가 움직이지 않았는데 숫자가 바뀌거나, 두 숫자가 한 패에 겹치거나, 숫자 없는 패가 생기거나 없어지면 오류 후보다 — 말로 넘기지 말고 그 앞뒤 프레임에서 확인한다.
- 먼저 프레임을 띄엄띄엄 훑어 언제 무슨 일이 있었는지 잡고, 손이 줄을 덮은 구간 · 숫자가 겹치거나 빠진 곳은 앞뒤 프레임을 촘촘히 보고 확대한다. 서둘러 답하지 말고 의심 가는 곳을 끝까지 본다.
- D 를 끝에 붙여 두고 한 장을 버리는 사람, 버린 뒤 D 를 다시 집어 안쪽에 끼우는 사람, D 를 먼저 안쪽에 끼우고 버리는 사람, 버리기 전에 패를 옮기거나 맞바꾸는 사람, 뽑은 패를 그대로 버리는 사람(쯔모기리)이 다 있다. 끝 프레임까지 본다.

## 답(answer 도구) — SAM 2 오류를 바로잡은 실제 결과
- kind: "hand"(줄에 있던 패를 버림) 또는 "tsumogiri"(D 를 그대로 버림, 줄의 패는 안 바뀜)
- k: 버린 패가 원래 줄 {n}장에서 왼쪽부터 몇 번째였나(D 는 세지 않음, tsumogiri 면 null)
- j: 차례가 끝났을 때 D 가 줄({n}장)의 왼쪽부터 몇 번째인가(끝 그대로면 {n}, tsumogiri 면 null)
- end_order: 끝 줄 왼쪽부터 실제 패 — 원래 번호 "1" ~ "{n}" 또는 "D"(tsumogiri 면 "1" ~ "{n}"). SAM 2 가 끝 프레임에 칠한 숫자가 아니라 바로잡은 것.
- unsure: 맞을 가능성 70% 밑이면 true · tracking_errors: SAM 2 가 틀린 곳(프레임 번호 · 어느 숫자가 어떻게 틀렸나, 없으면 "없음") · why: 근거 3 ~ 5문장(프레임 번호와 함께)
"""


# --variant fix(11-19 밤, 사용자 "그러면 원본도 쓸수있게 바꾸고 다시 돌려봐"): PROMPT_COLOR 에서 원본을 쓸 수 있다는 것만 되살림
# (재료 · 확인 그림 · 도구 인자 설명). "원본을 확대해 센다" 같은 c1 의 원본 쓰는 법 지시는 더하지 않음 — k1 과 그림만 다르게.
_FIX_SUBS = [
    ("**모두 SAM 2 가 색 · 숫자를 칠한 그림이다 — 원본은 주지 않는다.** 칠이 없는 곳(손 · 탁자 · D · 추적이 놓친 패)은 화면 그대로 보인다.",
     "프레임마다 두 가지 그림이 있다:\n  - **color** = SAM 2 가 색 · 숫자를 칠한 그림. 칠이 없는 곳(손 · 탁자 · D · 추적이 놓친 패)은 화면 그대로 보인다.\n  - **raw** = 같은 순간의 원본(색 없음)."),
    ("위 = 차례 시작 줄 · 아래 = 그 순간(손패 줄 부분 2배)", "위 = 차례 시작 줄 · 가운데 = 그 순간 원본 · 아래 = 그 순간 색(손패 줄 부분 2배)"),
    ("`view(frames)` — 프레임 여러 장(한 번에 {mv}장까지)을 본다.", "`view(frames, kind)` — 프레임 여러 장(한 번에 {mv}장까지)을 본다. kind = color | raw."),
    ("`zoom(frame, x0, x1, y0, y1)`", "`zoom(frame, x0, x1, y0, y1, kind)`"),
    ("`strip(start, end, step, x0, x1, y0, y1)`", "`strip(start, end, step, x0, x1, y0, y1, kind)`"),
]
PROMPT_FIX = PROMPT_COLOR
for _a, _b in _FIX_SUBS:
    assert PROMPT_FIX.count(_a) == 1, _a
    PROMPT_FIX = PROMPT_FIX.replace(_a, _b)


# --variant edit(11-19 밤, 사용자 "sam2출력을 수정해서 오퍼스가 올바른 sam2출력을 참고하게" → 1번 장치 확인(표 12-80) → "2번 돌려줘"):
# c1(g3) 지시문 · 도구 그대로에 edit 도구 하나 + 그림 kind "sam2"(고치기 전 그대로)를 더함. color 는 지금까지의 고침으로 다시 그린 그림.
# 고침 · 검사 · 끝 번호 순서 · k·j 는 relabel.py(저장된 마스크, SAM 2 다시 안 돌림).
EDIT_SECTION = """## SAM 2 출력 고치기(edit 도구)
- 추적이 틀린 곳을 찾으면 `edit(edits)` 로 **SAM 2 출력의 번호를 직접 고친다.** 고친 뒤 **color 그림은 고친 번호로 다시 그려진다**(D 는 흰 칠 · 빨간 글자 D). kind = **sam2** 는 고치기 전 SAM 2 출력 그대로다. 확인 그림(check)도 고치기 전 것이다.
- 고침은 SAM 2 의 **원래 번호**(sam2 그림의 숫자)로 적는다. edit 는 고침 목록 **전체**를 받는다 — 부를 때마다 앞 목록을 통째로 바꿔 끼우므로, 고침을 빼거나 바꾸려면 고친 목록 전체로 다시 부른다. 프레임 번호는 0 ~ {last}, end 를 null 로 두면 끝 프레임까지.
  - `{{"op": "relabel", "o": 원래 번호, "start": 프레임, "end": 프레임, "to": "D" 또는 "1" ~ "{n}"}}` — 그 구간에서 그 마스크의 번호를 바꿈
  - `{{"op": "drop", "o": 원래 번호, "start": …, "end": …}}` — 그 구간에서 그 마스크를 지움(엉뚱한 곳에 붙은 칠)
  - `{{"op": "box", "label": "D" 또는 "1" ~ "{n}", "start": …, "end": …, "box": [x0, y0, x1, y1]}}` — 칠이 없는 패에 상자로 번호를 붙임(좌표는 그림 화소)
- edit 는 고친 출력을 **코드로 검사한 결과**를 돌려준다: 프레임마다 같은 번호가 두 패 · 한 패에 번호 둘 · (D 를 정한 뒤) 번호 없는 패 · 줄 장수 초과, 그리고 끝 프레임의 번호 순서와 거기서 센 k · j. 검사는 패 검출 상자를 쓰므로 손에 든 패를 두 번 세는 등 거짓 경보가 있을 수 있고, 손이 덮은 프레임은 못 본다 — 걸린 프레임은 그림으로 확인한다.
- **D 를 포함해 끝 줄의 모든 패가 실제 번호를 갖도록** 고친다. 경보가 남으면 그 까닭을 그림으로 확인하고, 이야기가 틀렸으면 고침을 바꾼다. 다 고쳤으면 answer 를 부른다 — answer 의 end_order 는 고친 출력의 끝 번호 순서와 같아야 한다.

"""
_ANS = "## 답(answer 도구)"
assert ga.PROMPT.count(_ANS) == 1
PROMPT_EDIT = ga.PROMPT.replace(_ANS, EDIT_SECTION + _ANS)


# --variant motion(11-19 밤, 사용자 "81~89는 결국 패이동 한개도 없는건데 이것만 보게 된 이유가 뭐니" → "재 봐"):
# c1(g3) 그대로에 ① "패가 실제로 움직인 때부터" 절 ② 첫 메시지에 칸 틀 사건 목록(slotgrid events, 시각 옆에 프레임 번호)만 더함.
MOTION_SECTION = """## 패가 실제로 움직인 때부터
- 읽기 전에 **패가 실제로 움직인 때**(D 를 줄에 놓음 · 패를 뺌 · 버림 · 줄을 밂 · 끼움 · 옮김 · 맞바꿈)를 먼저 찾아 차례의 사건 순서를 세운다. 첫 메시지의 **칸 틀 사건 목록**(코드가 패 검출 상자로 칸이 차고 빈 때를 적은 것, 시각 옆 괄호가 프레임 번호)이 출발점이다. 목록은 손이 덮은 칸 밑을 못 보므로 손 가림 구간은 원본으로 확인한다.
- **패가 움직이지 않은 구간에서 SAM 2 숫자가 바뀌거나 · 칠이 빠지거나 · 겹치면 그것은 추적 오류다.** 숫자 바뀜을 설명하려고 움직임을 지어내지 않는다.
- 손이 덮은 동안 패를 옮겼다(끼움 · 맞바꿈)고 보려면 원본에서 그 동작의 흔적을 확인한다: 손이 패를 들고 움직임 · 칸이 비었다 참 · 끝 패가 그 자리에서 사라짐 · 줄 길이가 바뀜. 흔적을 못 찾으면 "움직이지 않음" 쪽에 무게를 두고, 그래도 옮겼다고 답하면 why 에 그 흔적을 프레임 번호로 적는다.

"""
PROMPT_MOTION = ga.PROMPT.replace(_ANS, MOTION_SECTION + _ANS)

# --variant motion2(11-19 밤, 사용자 "그러면 어떻게 해야 맞출수 잇을까" → "진행해봐"): motion 그대로에
# ① color 그림에서 위치를 못 믿을 숫자(처음 넓이의 40% 밑 — relabel.float_ids, 살색 기준은 판마다 패 색이 달라 끔)를 흐린 칠 + 회색 "숫자?" 로 다시 그림
# ② 절에 두 줄("숫자?" 뜻 · 숫자의 움직임은 패의 움직임이 아님). 확인 그림(check)은 표시 전 그대로.
MOTION2_EXTRA = """- color 그림에서 **흐린 칠 + 회색 "숫자?"** 는 그 마스크가 처음 넓이의 40% 밑으로 줄었다고 코드가 본 것이다 — 손 밑에 거의 가려졌거나 손에 끌려간 숫자라 **그 위치를 믿지 않는다.** 확인 그림(check)에는 이 표시가 없다.
- **숫자의 움직임은 패의 움직임이 아니다.** 패가 움직였다는 근거는 원본의 패(흰 면 · 등 띠)와 칸 틀 사건 목록(칸이 비었다 · 찼다)에서만 찾는다. 숫자가 손을 따라 움직였다고 그 패가 움직였다고 보지 않는다.

"""
assert MOTION_SECTION.endswith("\n\n")
PROMPT_MOTION2 = ga.PROMPT.replace(_ANS, MOTION_SECTION[:-1] + MOTION2_EXTRA + _ANS)


class FloatTurn(ga.Turn):
    """motion2 판: color 그림을 저장된 마스크로 다시 그리며 떠 있는 숫자를 표시(번호 고침 없음)."""

    def __init__(self, tid: str):
        super().__init__(tid)
        import relabel as rl
        self.rl = rl
        self.track = rl.Track(tid)
        assert self.track.F == len(self.rows), (self.track.F, len(self.rows))
        self._font = None
        self._cache: dict = {}
        self.float_log: dict = {}

    def img(self, i: int, kind: str) -> Image.Image:
        i = max(0, min(i, len(self.rows) - 1))
        if kind != "color":
            return super().img(i, kind)
        if i not in self._cache:
            from PIL import ImageFont
            self._font = self._font or ImageFont.truetype("arialbd.ttf", 15)
            items = self.rl.apply_edits_frame(self.track, i)
            fl = self.rl.float_ids(self.track, i)
            self.float_log[i] = sorted(fl)
            self._cache[i] = self.rl.render(self.track, items, i, self._font, {str(o) for o in fl})
        return self._cache[i].copy()


EVENTS: dict = {}   # 차례 id → 사건 목록 글. cmd_run 이 스레드를 띄우기 전에 차례마다 하나씩 채움(아래 주의)


def events_text(T: "ga.Turn") -> str:
    """slotgrid.py events 출력(글)을 받아 시각마다 가장 가까운 프레임 번호를 붙임.
    주의(11-19 밤 버그): redirect_stdout 은 프로세스 전체의 sys.stdout 을 바꿔서, 나란히 도는 스레드 안에서 부르면
    다른 차례의 목록 · 진행 줄이 섞이고 sys.stdout 이 엉뚱한 버퍼로 남는다(m1 · m2 첫 판이 이렇게 오염됨).
    그래서 스레드 안에서는 EVENTS 에 미리 만든 것만 쓰고, 없으면 예외."""
    if T.tid in EVENTS:
        return EVENTS[T.tid]
    import threading
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError(f"{T.tid}: 사건 목록을 스레드 안에서 만들려 함 — cmd_run 이 미리 채워야 함")
    import contextlib
    import re
    import slotgrid as sg
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sg.cmd_events(argparse.Namespace(ids=[T.tid], count=False))
    secs = []
    for i, t, _, _ in T.rows:
        mm, ss = t.split(":")
        secs.append((int(mm) * 60 + float(ss), i))

    def frame_of(m):
        mm, ss = m.group(1), m.group(2)
        s = int(mm) * 60 + float(ss)
        d, i = min((abs(((s - x + 1800) % 3600) - 1800), i) for x, i in secs)
        return f"{mm}:{ss}(프레임 {i:03d})" if d <= 0.6 else f"{mm}:{ss}(창 밖)"
    return re.sub(r"\b(\d{2}):(\d{2}\.\d)\b", frame_of, buf.getvalue().strip())


class EditTurn(ga.Turn):
    """edit 판: color 그림은 지금 고침으로 다시 그림(고침 없으면 저장된 color 그대로), sam2 는 저장된 color."""

    def __init__(self, tid: str):
        super().__init__(tid)
        import relabel as rl
        self.rl = rl
        self.track = rl.Track(tid)
        assert self.track.F == len(self.rows), (self.track.F, len(self.rows))
        self.edits: list = []
        self.res = None
        self._font = None
        self.history: list = []

    def img(self, i: int, kind: str) -> Image.Image:
        i = max(0, min(i, len(self.rows) - 1))
        if kind == "sam2" or (kind == "color" and not self.edits):
            return super().img(i, "color")
        if kind == "color":
            from PIL import ImageFont
            self._font = self._font or ImageFont.truetype("arialbd.ttf", 15)
            return self.rl.render(self.track, self.res["per"][i], i, self._font)
        return super().img(i, kind)

    def set_edits(self, edits) -> str:
        if not isinstance(edits, list):
            raise ValueError("edits 는 목록")
        bad = self.rl.check_edits(edits, self.n, len(self.rows))
        if bad:
            raise ValueError("고침 꼴 틀림(앞 고침 그대로 둠): " + " / ".join(bad))
        res = self.rl.analyze(self.track, edits)
        self.edits, self.res = edits, res
        self.history.append({"edits": edits, "end_order": res["end_order"], "kj": res["kj"], "flags": res["flags"]})
        return f"고침 {len(edits)}개 적용 — color 그림이 바뀜.\n" + self.rl.summary(res)


def tool_defs(variant: str = "base") -> list:
    """geminiagent.decls(strip=True) 와 같은 도구 · 같은 인자 · 같은 순서(strip, view, zoom, check, answer).
    variant color: 같은 도구에서 kind 인자만 뺌(늘 color)."""
    tools = _tool_defs_base()
    if variant == "edit":
        for t in tools:
            if t["name"] not in ("strip", "view", "zoom"):   # answer 의 kind(hand/tsumogiri)는 그대로(e1 은 이걸 빠뜨려 answer kind 가 color 꼴이 됨)
                continue
            t["input_schema"]["properties"]["kind"] = {"type": "string", "enum": ["color", "raw", "sam2"]}
        it, nint = {"type": "integer"}, {"anyOf": [{"type": "integer"}, {"type": "null"}]}
        tools.insert(len(tools) - 1, {
            "name": "edit", "description": "SAM 2 출력의 번호를 고친다(고침 목록 전체를 바꿔 끼움) — 고친 출력의 코드 검사 · 끝 번호 순서 · k·j 를 돌려줌",
            "input_schema": {"type": "object", "properties": {"edits": {"type": "array", "items": {
                "type": "object", "properties": {
                    "op": {"type": "string", "enum": ["relabel", "drop", "box"]}, "o": it, "start": it, "end": nint,
                    "to": {"type": "string"}, "label": {"type": "string"}, "box": {"type": "array", "items": it}},
                "required": ["op", "start"]}}}, "required": ["edits"], "additionalProperties": False}})
        return tools
    if variant == "color":
        for t in tools:
            if t["name"] not in ("strip", "view", "zoom"):   # answer 의 kind(hand/tsumogiri)는 그대로
                continue
            sch = t["input_schema"]
            sch["properties"].pop("kind", None)
            sch["required"] = [r for r in sch["required"] if r != "kind"]
    return tools


def _tool_defs_base() -> list:
    kind = {"type": "string", "enum": ["color", "raw"]}
    it = {"type": "integer"}
    nint = {"anyOf": [{"type": "integer"}, {"type": "null"}]}
    return [
        {"name": "strip", "description": "같은 영역을 여러 프레임에서 잘라 시간순으로 쌓아 본다",
         "input_schema": {"type": "object", "properties": {"start": it, "end": it, "step": it, "x0": it, "x1": it, "y0": it, "y1": it, "kind": kind},
                          "required": ["start", "end", "step", "x0", "x1", "kind"], "additionalProperties": False}},
        {"name": "view", "description": "프레임 여러 장을 본다",
         "input_schema": {"type": "object", "properties": {"frames": {"type": "array", "items": it}, "kind": kind},
                          "required": ["frames", "kind"], "additionalProperties": False}},
        {"name": "zoom", "description": "한 프레임의 일부를 잘라 3배로 키운다",
         "input_schema": {"type": "object", "properties": {"frame": it, "x0": it, "x1": it, "y0": it, "y1": it, "kind": kind},
                          "required": ["frame", "x0", "x1", "kind"], "additionalProperties": False}},
        {"name": "check", "description": "확인 그림 한 장을 본다",
         "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False}},
        {"name": "answer", "description": "답을 낸다(부르면 끝)", "strict": True,
         "input_schema": {"type": "object", "properties": {
             "kind": {"type": "string", "enum": ["hand", "tsumogiri"]}, "k": nint, "j": nint,
             "end_order": {"type": "array", "items": {"type": "string"}}, "unsure": {"type": "boolean"},
             "tracking_errors": {"type": "string"}, "why": {"type": "string"}},
             "required": ["kind", "k", "j", "end_order", "unsure", "tracking_errors", "why"], "additionalProperties": False}},
    ]


def system_text(T: "ga.Turn", variant: str = "base") -> str:
    """geminiagent.run_one 의 sys_prompt 와 같은 글(strip 줄 포함 = g3). variant color 는 PROMPT_COLOR."""
    F = len(T.rows)
    p = {"color": PROMPT_COLOR, "fix": PROMPT_FIX, "edit": PROMPT_EDIT, "motion": PROMPT_MOTION, "motion2": PROMPT_MOTION2}.get(variant, ga.PROMPT)
    return p.format(n=T.n, F=F, last=F - 1, mv=MAX_VIEW, W=T.W, H=T.H, sr=ga.STRIP_ROWS, sm=ga.STRIP_MAX)


def check_color_only(b: bytes) -> bytes:
    """확인 그림(sam2verify.check_image: 제목 40 + 칸 h × 3 + 틈 4 × 2, 위 시작 줄 · 가운데 원본 · 아래 색)에서 가운데 원본 칸을 뺌."""
    im = Image.open(io.BytesIO(b)).convert("RGB")
    bar = 40
    h = (im.height - bar - 8) // 3
    top = im.crop((0, 0, im.width, bar + h))
    bot = im.crop((0, bar + 2 * h + 8, im.width, im.height))
    out = Image.new("RGB", (im.width, top.height + 4 + bot.height), (255, 255, 255))
    out.paste(top, (0, 0))
    out.paste(bot, (0, top.height + 4))
    return ga.jpg(out)


def fit(b: bytes) -> bytes:
    """긴 변이 LONG_EDGE 를 넘는 jpeg 만 줄임(나머지는 바이트 그대로)."""
    im = Image.open(io.BytesIO(b))
    if max(im.size) <= LONG_EDGE:
        return b
    sc = LONG_EDGE / max(im.size)
    return ga.jpg(im.convert("RGB").resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.LANCZOS))


def img_block(b: bytes) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.standard_b64encode(fit(b)).decode("ascii")}}


def zoom_image(T: "ga.Turn", args: dict) -> tuple:
    """geminiagent.run_one 의 zoom 자르기와 같은 일(거기선 함수가 아니라 줄 안에 있어 같은 식을 옮김)."""
    im = T.img(int(args["frame"]), args.get("kind", "raw"))
    x0, x1 = sorted([max(0, int(args["x0"])), min(im.width, int(args["x1"]))])
    y0 = max(0, int(args.get("y0") or 0))
    y1 = min(im.height, int(args.get("y1") or im.height))
    cr = im.crop((x0, y0, max(x1, x0 + 8), max(y1, y0 + 8)))
    sc = min(3.0, 1600 / max(1, cr.width))
    cr = cr.resize((int(cr.width * sc), int(cr.height * sc)), Image.LANCZOS)
    return f"프레임 {int(args['frame']):03d} 확대 x {x0}~{x1} y {y0}~{y1}", ga.jpg(cr)


def run_tool(T: "ga.Turn", name: str, args: dict, variant: str = "base") -> list:
    """도구 하나 실행 → [(설명, jpeg 바이트)]. 실패하면 예외(부르는 쪽이 is_error 로). variant color 는 늘 color · 확인 그림 원본 칸 뺌."""
    F = len(T.rows)
    if variant == "color":
        args = {**args, "kind": "color"}
        if name == "check":
            return [(d, check_color_only(x)) for d, x in run_tool(T, name, args)]
    if name == "view":
        fr = [int(x) for x in (args.get("frames") or [])][:MAX_VIEW]
        return [(f"프레임 {i:03d} {T.rows[max(0, min(i, F - 1))][1]} {args.get('kind')}", ga.jpg(T.img(i, args.get("kind", "color")))) for i in fr]
    if name == "zoom":
        return [zoom_image(T, args)]
    if name == "strip":
        return ga.strip_images(T, args)
    if name == "check":
        p = SRC / T.tid / "check" / str(args.get("name"))
        if not p.exists() or p.parent != SRC / T.tid / "check":
            raise FileNotFoundError(f"확인 그림 없음: {args.get('name')}")
        return [(p.name, p.read_bytes())]
    raise ValueError(f"모르는 도구: {name}")


def first_content(T: "ga.Turn", variant: str = "base") -> list:
    F = len(T.rows)
    lst = "\n".join(f"{i:03d} {t}" for i, t, _, _ in T.rows)
    ev = f"\n\n칸 틀 사건 목록(코드가 패 검출로 만든 것):\n{events_text(T)}" if variant in ("motion", "motion2") else ""
    return [{"type": "text", "text": f"차례를 시작할 때 줄은 {T.n}장. 프레임 {F}장(번호 · 시각):\n{lst}{ev}\n\n확인 그림 이름: {', '.join(T.checks) or '없음'}\n\n첫 프레임(color):"},
            img_block(ga.jpg(T.img(0, "color"))),
            {"type": "text", "text": f"끝 프레임 {F - 1}(color):"},
            img_block(ga.jpg(T.img(F - 1, "color"))),
            {"type": "text", "text": FIRST_TAIL}]


def request_kw(T: "ga.Turn", a) -> dict:
    """매 호출에 같은 앞부분: 모델 · system(캐시 지점) · 도구 · effort · 자동 캐싱. messages 는 따로."""
    kw = {"model": a.model, "max_tokens": a.max_tokens,
          "system": [{"type": "text", "text": system_text(T, a.variant), "cache_control": {"type": "ephemeral"}}],
          "tools": tool_defs(a.variant),"output_config": {"effort": a.effort}, "cache_control": {"type": "ephemeral"}}
    if getattr(a, "show_thinking", False):
        kw["thinking"] = {"type": "adaptive", "display": "summarized"}
    return kw


def count_images(msgs: list) -> tuple:
    """대화 안 그림 장수 · base64 바이트 합(요청 한도 어림)."""
    n = size = 0

    def walk(blocks):
        nonlocal n, size
        if not isinstance(blocks, list):
            return
        for b in blocks:
            if isinstance(b, dict):
                if b.get("type") == "image":
                    n += 1
                    size += len(b["source"]["data"])
                elif b.get("type") == "tool_result":
                    walk(b.get("content"))
    for mm in msgs:
        walk(mm.get("content"))
    return n, size


def call(client, kw: dict, msgs: list):
    """스트리밍으로 부르고 최종 메시지. 429 · 5xx · 연결 오류만 바깥 3번(SDK 기본 재시도 2번은 그 안에서). 400 등은 바로 올림."""
    import anthropic
    last = None
    for attempt in range(3):
        try:
            with client.messages.stream(messages=msgs, **kw) as stream:
                return stream.get_final_message()
        except anthropic.APIConnectionError as e:
            last = e
        except anthropic.APIStatusError as e:
            if e.status_code != 429 and e.status_code < 500:
                raise
            last = e
        time.sleep(10 * (attempt + 1))
    raise last


def run_one(tid: str, a, client) -> dict:
    T = EditTurn(tid) if a.variant == "edit" else FloatTurn(tid) if a.variant == "motion2" else ga.Turn(tid)
    kw = request_kw(T, a)
    msgs = [{"role": "user", "content": first_content(T, a.variant)}]
    p_in, p_out, p_cr, p_cw = PRICE[a.model]
    log, ans, nudges, usd, final = [], None, 0, 0.0, False
    usage = {"in": 0, "cache_read": 0, "cache_write": 0, "out": 0, "calls": 0, "max_ctx": 0}
    res = {"id": tid, "model": a.model, "effort": a.effort, "src": a.src, "variant": a.variant}
    if a.variant in ("motion", "motion2"):
        res["events"] = EVENTS.get(tid)   # 첫 메시지에 실제로 넣은 사건 목록(감사용)
    t0 = time.perf_counter()
    step = -1
    while True:
        step += 1
        if step >= a.max_steps + FINAL_EXTRA:   # 마지막 단계 뒤에도 answer 를 안 부르면 끝(Claude 는 answer 를 강제할 수 없어 FINAL_EXTRA 번 더 줌)
            break
        n_img, n_bytes = count_images(msgs)
        why_final = ("단계" if step >= a.max_steps - 1 else "달러" if usd > a.max_usd else
                     "그림 장수" if n_img > MAX_IMAGES else "요청 크기" if n_bytes > MAX_BYTES else None)
        if why_final and not final:   # 마지막 단계: 지금까지 본 것으로 답하게(geminiagent 와 같은 글)
            final = True
            log.append({"step": step, "final": why_final})
            last = msgs[-1]
            if last["role"] == "user":   # tool_result 들 뒤에 글 블록으로(문서: 같은 user 메시지에 덧붙임)
                last["content"].append({"type": "text", "text": FINAL_TEXT})
            else:
                msgs.append({"role": "user", "content": [{"type": "text", "text": FINAL_TEXT}]})
        try:
            r = call(client, kw, msgs)
        except Exception as e:  # noqa: BLE001
            res.update({"error": f"{type(e).__name__}: {e}"[:400]})
            break
        u = r.usage
        ui, ucr, ucw, uo = u.input_tokens or 0, u.cache_read_input_tokens or 0, u.cache_creation_input_tokens or 0, u.output_tokens or 0
        usage["in"] += ui
        usage["cache_read"] += ucr
        usage["cache_write"] += ucw
        usage["out"] += uo
        usage["calls"] += 1
        usage["max_ctx"] = max(usage["max_ctx"], ui + ucr + ucw)
        usd += (ui * p_in + uo * p_out + ucr * p_cr + ucw * p_cw) * 1e-6
        msgs.append({"role": "assistant", "content": r.content})   # thinking 포함 그대로
        uses = [b for b in r.content if b.type == "tool_use"]
        texts = " ".join(b.text for b in r.content if b.type == "text")
        thinks = " ".join(getattr(b, "thinking", "") or "" for b in r.content if b.type == "thinking")
        ent = {"step": step, "stop": r.stop_reason, "in": ui, "cache_read": ucr, "cache_write": ucw, "out": uo}
        if texts:
            ent["text"] = texts[:300]
        if thinks:
            ent["thinking"] = thinks[:600]
        log.append(ent)
        print(f"  {tid} 단계 {step:02d} {','.join(b.name for b in uses) or r.stop_reason} 누적 {usd:.3f}달러 "
              f"(입력 {ui} · 캐시 읽기 {ucr} · 쓰기 {ucw} · 출력 {uo} · 그림 {n_img}장 {n_bytes / 2 ** 20:.1f}MB)", flush=True)
        if r.stop_reason == "refusal":
            sd = r.stop_details
            res.update({"error": "refusal", "stop_details": {"category": getattr(sd, "category", None), "explanation": getattr(sd, "explanation", None)} if sd else None})
            break
        if r.stop_reason == "max_tokens":   # 잘린 도구 입력은 돌리지 않음 — 단순하게 오류로
            res.update({"error": f"max_tokens({a.max_tokens})"})
            break
        if not uses:
            if final:   # 마지막 단계인데 글로만 답함 → 같은 글로 한 번 더(FINAL_EXTRA 안에서)
                msgs.append({"role": "user", "content": [{"type": "text", "text": FINAL_TEXT}]})
                continue
            nudges += 1
            if nudges > 2:
                break
            msgs.append({"role": "user", "content": [{"type": "text", "text": NUDGE_TEXT}]})
            continue
        results = []
        for b in uses:
            args = dict(b.input or {})
            log.append({"step": step, "tool": b.name, "args": args})
            if b.name == "answer":
                ans = args
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": "받음"})
                continue
            if final:   # 마지막 단계 뒤에는 더 보여 주지 않음
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": "볼 수 있는 단계를 다 썼다 — 이제 answer 만 부를 수 있다.", "is_error": True})
                continue
            if b.name == "edit" and isinstance(T, EditTurn):
                try:
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": T.set_edits(args.get("edits"))})
                except Exception as e:  # noqa: BLE001
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": str(e)[:400], "is_error": True})
                continue
            try:
                imgs = run_tool(T, b.name, args, a.variant)
            except Exception as e:  # noqa: BLE001
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": str(e)[:200], "is_error": True})
                continue
            results.append({"type": "tool_result", "tool_use_id": b.id,
                            "content": [{"type": "text", "text": " | ".join(t for t, _ in imgs)}] + [img_block(x) for _, x in imgs]})
        msgs.append({"role": "user", "content": results})
        if ans is not None:
            break
    res.update({"steps": usage["calls"], "s": round(time.perf_counter() - t0, 1), "usage": usage, "log": log})
    if isinstance(T, EditTurn):   # 마지막 고침 · 그 끝 번호 순서 · 코드가 센 k·j(answer 와 따로 채점)
        res.update({"edits": T.edits, "edit_history": T.history,
                    "edit_order": T.res["end_order"] if T.res else None, "edit_kj": T.res["kj"] if T.res else None})
    if ans:
        n = T.n
        kj = sv.from_order([str(x) for x in ans.get("end_order") or []], n)
        res.update({"answer": ans, "kind": ans.get("kind"), "unsure": ans.get("unsure"),
                    "k": (kj[0] if kj and ans.get("kind") == "hand" else ans.get("k")), "j": (kj[1] if kj and ans.get("kind") == "hand" else ans.get("j")),
                    "k_model": ans.get("k"), "j_model": ans.get("j"), "order_ok": kj is not None})
    else:
        res.update({"kind": None, "k": None, "j": None})
        res.setdefault("error", "answer 없음")
    res["usd"] = round(usd, 3)
    return res


def make_client():
    from dotenv import load_dotenv
    load_dotenv(ENV)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    import anthropic
    return anthropic.Anthropic()


def cmd_run(a):
    client = make_client()
    if client is None:
        print("ANTHROPIC_API_KEY 가 .env 에 없음")
        return
    od = OUT / a.tag
    od.mkdir(parents=True, exist_ok=True)
    ids = [t for t in sv.ids_of(a.ids) if a.force or not (od / f"{t}.json").exists()]
    print(f"{len(ids)}차례 · {a.model} · effort {a.effort} · 단계 {a.max_steps} · 차례당 {a.max_usd}달러 · 나란히 {a.workers}", flush=True)
    if a.variant in ("motion", "motion2"):   # 사건 목록은 스레드 전에 하나씩(redirect_stdout 이 프로세스 전체라서 — events_text 주의)
        for t in ids:
            EVENTS[t] = events_text(ga.Turn(t))
        assert sys.stdout is sys.__stdout__ or not isinstance(sys.stdout, io.StringIO), "sys.stdout 이 버퍼로 남음"
    with ThreadPoolExecutor(a.workers) as ex:
        for r in ex.map(lambda t: run_one(t, a, client), ids):
            r["at"] = hc.hms(int(time.time() * 1000), date=True)
            hc.jsave(od / f"{r['id']}.json", r)
            print(r["id"], r.get("kind"), r.get("k"), r.get("j"), f"단계 {r.get('steps')}", f"{r.get('s')}초", f"약 {r.get('usd')}달러", r.get("error", ""), flush=True)


def cmd_score(a):
    truth = s1.truth_all()
    T = quiet = noans = 0
    usd = 0.0
    ids = sv.ids_of(a.ids)
    for tid in ids:
        f = OUT / a.tag / f"{tid}.json"
        if not f.exists():
            print(tid, "없음")
            continue
        r = hc.jload(f)
        ok = m.right(m.norm(r), truth[tid])
        T += ok
        if r.get("kind") is None:
            noans += 1
        else:
            quiet += (not ok) and not r.get("unsure")
        usd += r.get("usd") or 0
        tools = {}
        for x in r.get("log", []):
            if x.get("tool"):
                tools[x["tool"]] = tools.get(x["tool"], 0) + 1
        print(f"{tid:9s} 정답 {truth[tid].get('kind')} {truth[tid].get('k_id')}·{truth[tid].get('j_closed')} | Claude {r.get('kind')} {r.get('k')}·{r.get('j')}{'?' if r.get('unsure') else ''} {'✓' if ok else '✗'} "
              f"| 단계 {r.get('steps')} · 도구 {tools} · {r.get('s')}초 · 약 {r.get('usd')}달러 {r.get('error', '')}")
    print(f"맞음 {T}/{len(ids)} · 답 없음(단계 다 씀) {noans} · 조용한 틀림 {quiet} · 합 약 {usd:.2f}달러")


def cmd_dry(a):
    """API 를 부르지 않고 첫 요청 · 도구 5개를 실제 Turn 으로 만들어 봄. 그림은 claudeagent_1119/dry/ 에."""
    od = OUT / "dry"
    od.mkdir(parents=True, exist_ok=True)
    for tid in sv.ids_of(a.ids):
        T = ga.Turn(tid)
        F = len(T.rows)
        kw = request_kw(T, a)
        msgs = [{"role": "user", "content": first_content(T, a.variant)}]
        n_img, n_bytes = count_images(msgs)
        body = json.dumps({**kw, "messages": msgs}, ensure_ascii=False)
        print(f"[{tid}] 줄 {T.n}장 · 프레임 {F}장 · 그림 {T.W}×{T.H} · 확인 그림 {len(T.checks)}장")
        print(f"  model {kw['model']} · effort {kw['output_config']['effort']} · max_tokens {kw['max_tokens']} · thinking {kw.get('thinking', '안 줌(adaptive)')} · 최상위 cache_control {kw['cache_control']}")
        print(f"  system {len(kw['system'][0]['text'])}자 (strip 줄 {'있음' if '- `strip(' in kw['system'][0]['text'] else '없음'}) · 도구 {[t['name'] for t in kw['tools']]} · strict {[t['name'] for t in kw['tools'] if t.get('strict')]}")
        print(f"  첫 메시지 블록 {[b['type'] for b in msgs[0]['content']]} · 그림 {n_img}장 base64 {n_bytes} 바이트 · 요청 본문 {len(body.encode('utf-8'))} 바이트")
        for i, b in enumerate(x for x in msgs[0]["content"] if x["type"] == "image"):
            raw = base64.standard_b64decode(b["source"]["data"])
            (od / f"{tid}_first{i}.jpg").write_bytes(raw)
        tests = [("view", {"frames": [0, 50], "kind": "color"}),
                 ("zoom", {"frame": 0, "x0": 0, "x1": T.W // 2, "kind": "raw"}),
                 ("strip", {"start": 40, "end": 60, "step": 1, "x0": 0, "x1": T.W, "kind": "raw"}),
                 ("check", {"name": T.checks[0] if T.checks else "없음.jpg"}),
                 ("check", {"name": "없는그림.jpg"})]
        for name, args in tests:
            try:
                imgs = run_tool(T, name, args, a.variant)
            except Exception as e:  # noqa: BLE001
                tr ={"type": "tool_result", "tool_use_id": "dry", "content": str(e)[:200], "is_error": True}
                print(f"  {name} {args} → is_error tool_result: {tr['content']}")
                continue
            blocks = [img_block(x) for _, x in imgs]
            sizes = []
            for k, ((desc, raw), blk) in enumerate(zip(imgs, blocks)):
                sent = base64.standard_b64decode(blk["source"]["data"])
                w0, h0 = Image.open(io.BytesIO(raw)).size
                w1, h1 = Image.open(io.BytesIO(sent)).size
                sizes.append(f"{w0}×{h0}" + (f"→{w1}×{h1}" if (w0, h0) != (w1, h1) else "") + f" {len(sent) // 1024}KB")
                (od / f"{tid}_{name}_{k}.jpg").write_bytes(sent)
            print(f"  {name} {args} → 그림 {len(imgs)}장 [{', '.join(sizes)}] · 글 '{' | '.join(t for t, _ in imgs)[:120]}'")
    print(f"그림 저장: {od}")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "score", "dry"):
        q = sp.add_parser(name)
        q.add_argument("--ids", default="hard8" if name != "dry" else "r16_d13")
        q.add_argument("--tag", default="c1")
        if name in ("run", "dry"):
            q.add_argument("--model", default=MODEL, choices=sorted(PRICE))
            q.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
            q.add_argument("--max-tokens", type=int, default=32000)
            q.add_argument("--show-thinking", action="store_true", help="thinking display=summarized — 생각 요약을 log 에 남김(값·행동 영향은 문서로 확인 못 함, 기본 끔)")
            q.add_argument("--variant", default="base", choices=["base", "color", "fix", "edit", "motion", "motion2"],
                           help="base = g3 지시문 · color/raw 둘 다 | color = SAM 2 오류 잡기 지시문 · color 그림만(11-19 저녁) | fix = 오류 잡기 지시문 · color/raw 둘 다")
            q.add_argument("--src", default="opusread_1118", help="읽을 재료 폴더(_work 아래 이름) — frames.txt · check/ (11-19: r19_d04 는 opusread_1119r)")
        if name == "run":
            q.add_argument("--max-steps", type=int, default=60)
            q.add_argument("--max-usd", type=float, default=5.0)
            q.add_argument("--workers", type=int, default=1)
            q.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if hasattr(a, "src"):   # 재료 폴더 바꾸기 — ga.Turn(frames.txt · check 이름)과 이 파일의 check 도구가 같은 폴더를 보게
        global SRC
        SRC = ga.SRC = hc.WORK / a.src
        if not SRC.is_dir():
            raise SystemExit(f"재료 폴더 없음: {SRC}")
    {"run": cmd_run, "score": cmd_score, "dry": cmd_dry}[a.cmd](a)


if __name__ == "__main__":
    main()
