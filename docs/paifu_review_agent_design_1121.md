# 설계서 — 패보 복기 에이전트 (LangGraph 도구 호출, 2026-11-21)

계기: 2026-11-21 밤 사용자 "복기 에이전트 구현해봐". `docs/paifu_review_llm_design_1118.md` 8절 3단계("복기 에이전트 — 도구 호출 · LangGraph · 조건 검색, 따로 설계서")의 설계서입니다. 해설 2단계(평가)는 아직 안 했지만, 사용자가 에이전트를 먼저 해 보라고 했습니다.

형식은 지금까지와 같습니다: 설계 · 검토는 이 세션, 구현은 Opus 하위 에이전트(높음).

**진행(11-21 밤): 코드까지 됨, 실제 Gemini 호출 0, 커밋 전.**
- 앱: `lib/paifu/agent_facts.dart` · `tool/paifu_agent_facts.dart`(`--compact`) · `test/agent_facts_test.dart`(15개). 서버 worktree `mahjong-recognizer-review`(브랜치 `feat/review-explain`): `app/review_agent.py`(884줄, 도구 7 · `StateGraph` plan/act/verify/fallback · 지시문 a1, 해설 `app/review.py` 의 검증 함수 재사용) · `app/main.py` `POST /v2/review/ask` · `tests/test_review_agent.py`(99개, 대본 가짜 LLM) · `tests/fixtures/agent_facts/`(예시 11판) · `scripts/review_ask.py`(`--fake`) · `requirements.txt` `langgraph==1.2.11`.
- 설계와 달라진 것: `options[].tiles` 를 목록 대신 순서 있는 맵 `{"2m": 3}` 으로(목록 꼴은 r15 · r16 이 60KB 를 넘음 → 맵으로 가장 큰 판 32.6KB). LLM 에 보이는 도구 결과는 목록 꼴. 응답에 `retries` 칸을 더함. Gemini 예외는 대체 답이 아니라 502/429.
- **검토:** analyze 문제 없음 · 앱 test 1,374 통과 · 서버 pytest 390 통과(검토 쪽에서 다시 돌림). **따로 짠 Python 샹텐 계산(일반형 · 치또이 · 국사)으로 예시 11판 후보 1,398개의 샹텐 · 유효패 종류 · 합계 · 동률 최선 목록을 대조 — 불일치 0.** `--fake` 로 r19 · r11 흐름 확인(검증 실패 → 재시도 → verified).
- **검토에서 고친 것(11-21 오후 복기 화면 작업이 만든 문제):** 해설 라우트의 `STATUSES` 에 `guessed` 가 없어 지금 앱 해설 사실표를 전부 거절하고 있었음(구현 쪽이 찾음). `app/review.py` 에 `guessed` 를 넣고 `tests/test_review.py` 에 시험 하나를 더함. 실제 해설 사실표 r19 · r11 · r15 가 서버 검사를 통과하는 것을 확인.
- **첫 실제 호출(11-21 밤, 사용자 "돌려 봐", metrics 표 15-3):** 7절 질문 12개(본 판 r19 · r11 · r17 · r12, `experiments/paifu_review/agent_questions_1121.json` 에 돌리기 전에 적음), gemini-3.8-flash · low · a1. **검증 첫 통과 12/12 · 재시도 0 · 대체 0, 시간 중앙 6.0 / p90 12.4 / 최대 16.3초, 도구 21 · LLM 33회 · 입력 53,923 / 출력 2,220토큰.** 사람이 읽어 틀림 있는 답 2/12 — 둘 다 검증이 못 잡는 판단 · 빠뜨림:
  - f4 "14순에 3만을 버렸어도 같았어?" → "같다". 14순은 리치 중이라 고를 수 없다. `what_if` 결과에 상태가 없어 모델이 몰랐다.
  - g4 "북이 리치한 뒤에 나는 어떻게 했어?" → 리치 없는 8 · 9순에 `safe_tiles` 를 쓰다 도구 6회 한도에 닿아 10 · 13 · 14순을 빠뜨림.
  - **고침 · 다시 잼(같은 밤, 사용자 "고쳐서 다시 재", metrics 표 15-4 · problem_log 74번):** 아래 ① ② 를 넣고 지시문 a2(구현 Opus 하위 에이전트, pytest 411). 본 판 12 틀림 2 → 0, **안 본 판 12(질문 · 기준은 실행 전 `agent_questions_1121b.json`): 검증 12/12(재시도 1) · 대체 0 · 틀림 0 → 기준 통과, a2 채택.** 남은 말투: % 붙임 · 근거 없는 "안전하게" · 오타.
  - **고칠 거리(→ 위에서 ① ② 함, ③ 은 남이 쓴 질문만 남음):** ① `what_if` · `discard_options` 결과에 `status` 와 "리치 중이라 고를 수 없다" 같은 `note` 를 넣기 ② 여러 차례를 한 번에 보는 조건 — `find_turns` 에 `riichi_wind`(그 자리 리치 뒤) 조건과 차례마다 현물 여부를 돌려주기 ③ 고친 뒤에는 안 본 판과 남이 쓴 질문으로 다시 재기.
- 빈틈(구현 쪽 보고): 판단 · 모양 말은 검증 못 함, 숫자는 "evidence 안의 값인가" 만 봄, 차례 찾기는 `N순 · N번째` 정규식뿐(한글 수사 못 찾음), `langchain-core` 등 딸린 패키지는 범위로 들어옴. 가짜 LLM 은 흐름만 보이고 질문에 맞는 답을 하지 않는다 — 품질은 7절 실제 호출로만 잴 수 있다.

## 0. 요약

- 사용자가 패보 한 판을 보다가 **질문**합니다("6순에 왜 4만이 실수야?", "리치 받고 뭘 버렸어야 했어?", "이 판에서 제일 아까운 수는?"). 에이전트가 **도구로 사실을 찾아** 한국어로 답합니다.
- **도구는 계산하지 않고 찾기만 합니다.** 숫자는 전부 앱의 Dart 엔진이 미리 계산해 "에이전트 사실표"로 보냅니다. 서버에 엔진을 Python으로 옮기지 않습니다(두 구현이 어긋날 위험을 없앰 — 1118 설계서 6절의 "엔진 Python 이식"을 바꾼 것).
- 서버(`mahjong-recognizer`, 브랜치 `feat/review-explain` worktree)에 LangGraph 그래프 하나와 라우트 `POST /v2/review/ask` 를 둡니다. LLM은 이미 쓰는 Gemini(`GeminiTextGenerator`)입니다. **Claude API는 쓰지 않습니다.**
- 답은 해설과 같은 방식으로 **코드가 검증**합니다: 답 속 패 · 숫자가 사실표나 이번에 부른 도구 결과에 있어야 합니다. 틀리면 한 번 다시 시키고, 그래도 틀리면 "확인된 사실만" 대체 답을 냅니다.
- 이번 범위: 앱 사실표 + 서버 그래프 · 라우트 · 가짜 LLM 시험 + 한 판 돌려 보는 스크립트. **앱 화면(질문 창)과 운영 배포는 이번 범위가 아닙니다.** 실제 Gemini 호출은 사용자에게 묻고 합니다.

## 1. 왜 LangGraph인가 (1118 설계서 6절 그대로)

해설(1단계)은 생성 → 검증 → 재시도의 고정 3칸이라 함수로 충분했습니다. 에이전트는 질문마다 부를 도구와 횟수가 달라 **상태 · 분기 · 횟수 제한**이 필요합니다. 그래서 여기서만 LangGraph를 씁니다.

## 2. 에이전트 사실표 (앱, Dart)

해설 사실표(`reviewFacts`)는 해설할 차례만, 후보도 상위 3개만 담습니다. 에이전트는 아무 차례 · 아무 후보나 물을 수 있으니 따로 만듭니다.

`lib/paifu/agent_facts.dart` `agentFacts(Paifu p, PaifuReview r) → Map` (jsonEncode 가능):

```
{
  "version": 1,
  "game": { round, honba, hero_wind, dora_indicators, efficiency_pct, grades{...}, statuses{...}, result },
  "turns": [                      // hero 버림 전부(해설 사실표와 달리 거르지 않음)
    { "turn": 6, "step": 23,      // step = 재생 걸음(eventIndex + 1)
      "status": "graded", "grade": "mistake",
      "hand": ["1m","2m",...],    // 버리기 전 닫힌 패(없으면 null)
      "drawn": "4p", "discard": "4m", "tsumogiri": false, "melds": 0,
      "riichi_declared": false, "shanten_prev": 1, "shanten_before": 1,
      "shanten_loss": 0, "ukeire_loss": 5,
      "options": [                // 버릴 수 있는 종류 전부(엔진 순서), 숫자 없는 차례는 []
        { "discard": "3m", "shanten": 1, "total": 15, "kinds": 5,
          "tiles": [{"tile":"1m","left":3}, ...] }, ...
      ],
      "actual": "4m", "best": ["3m","3s"],   // best = 최선과 샹텐 · 유효패가 같은 후보 전부
      "riichi_winds": [], "genbutsu": null, "safe_tiles": []
    }, ...
  ],
  "others": [                     // 남의 큰 사건만(리치 · 울기 · 화료), 순서대로
    { "step": 31, "wind": "남", "kind": "riichi", "tile": "7s" }, ...
  ]
}
```

- 패 표기는 해설 규격 A-1(`Tiles.toCode`, 적5도 `5m`)과 같습니다.
- 플레이어 이름 · 패보 id · note 는 넣지 않습니다(해설 사실표와 같은 원칙).
- 뽑기만 한 걸음 · 남의 버림 하나하나는 넣지 않습니다(크기를 줄임). 예시 11판에서 한 판 크기를 재서 시험에 적습니다(목표: 60KB 이하).
- `tool/paifu_agent_facts.dart <패보.json> [출력.json]` 로 파일을 만들 수 있게 합니다(`tool/paifu_facts.dart` 와 같은 꼴).

## 3. 도구 (서버, Python — 사실표에서 찾기만)

| 도구 | 인자 | 돌려주는 것 |
| --- | --- | --- |
| `turn_info` | `turn` | 그 차례의 손패 · 뽑은 패 · 버린 패 · 상태 · 등급 · 샹텐 · 유효패(실제와 최선) |
| `discard_options` | `turn` | 후보 전부(버릴 패 · 샹텐 · 유효패 장수 · 종류 수), 실제 · 최선 표시 |
| `what_if` | `turn`, `tile` | 그 패를 버렸을 때의 샹텐 · 유효패 목록(패마다 남은 장수), 실제 버림과의 차이(이쪽에만 있는 유효패 · 저쪽에만 있는 유효패) |
| `safe_tiles` | `turn` | 리치한 자리 · 버린 패가 현물인가 · 손 안 현물 |
| `find_turns` | `grade?`, `status?`, `min_ukeire_loss?`, `tile?` | 조건에 맞는 차례 번호와 한 줄 요약(조건 검색 — 1118 6절 "임베딩보다 조건 검색") |
| `game_summary` | 없음 | 패효율 · 등급 개수 · 상태 개수 · 결과 · 남의 리치 · 울기 |
| `rule` | `name` | 용어 풀이(유효패 · 샹텐 · 현물 · 쯔모기리 · 등급 기준(임시 10 · 30%) · 패효율) — 서버에 적어 둔 짧은 글 |

- 없는 차례 · 손에 없는 패 · 숫자 없는 차례는 `{"error": "..."}` 를 돌려주고 그래프는 계속 갑니다(LLM이 다른 도구를 고르게).
- 도구 결과는 그래프 상태의 `evidence` 에 쌓습니다. 검증이 이것을 씁니다.

## 4. 그래프 (LangGraph `StateGraph`)

```
START → plan ──(tool)──→ act ──→ plan
          │                        (도구 횟수 ≥ 6 이면 answer 로 강제)
          └──(answer)──→ verify ──(통과)──→ END
                           │
                           └──(실패, 재시도 0회)──→ plan(검증 오류를 덧붙여)
                           └──(실패, 재시도 1회)──→ fallback ──→ END
```

- **상태**: `question`, `facts`, `messages`(LLM과 주고받은 줄), `evidence`(도구 결과 목록), `tool_calls`(횟수), `retries`, `answer`, `violations`, `outcome`(`verified` / `fallback`).
- **plan 노드**: Gemini에 JSON 스키마 응답을 받습니다 — `{"action": "tool", "tool": 이름, "args": {...}}` 또는 `{"action": "answer", "text": "..."}`. 제공자 고유의 함수 호출 기능 대신 JSON 스키마를 쓰는 까닭: 이미 `GeminiTextGenerator` 가 이 방식이고, 가짜 LLM으로 시험하기 쉽고, 나중에 다른 모델로 바꾸기 쉽습니다.
- **act 노드**: 도구 실행, `evidence` 에 붙임.
- **verify 노드**: 해설 검증(`app/review.py`)의 규칙을 다시 씁니다 — 패는 대괄호 `[3만]` 꼴만 패로 보고, 허용 패 = 사실표의 그 판 패 전부(손패 · 버림 · 후보 · 유효패 · 도라 표시패) 중 이번 답이 근거로 삼은 것: **evidence 에 나온 패**. 숫자 `N장` · `N샹텐` · `N%` · `N순` 은 evidence 안의 값이어야 합니다. 영어 칸 이름 금지, 해라체. 질문이 물은 차례가 evidence 에 없으면(도구를 안 부르고 답함) 위반.
- **fallback 노드**: LLM 없이 코드가 만듭니다 — 질문에서 차례 번호를 찾으면 그 차례의 `turn_info` 를 코드 문장(앱 3-8 문장 틀과 같은 뜻)으로, 못 찾으면 "확인할 수 있는 사실로 답하지 못했다" + `game_summary`.
- **한도**: 도구 6회, 재시도 1회, LLM 호출 최대 8회, 전체 60초. 넘으면 fallback.
- **지시문**: 역할(마작 복기 도우미, 패효율만 평가한다는 한계), 도구 목록과 인자, "숫자는 반드시 도구 결과에서", 대괄호 패 표기, 해라체, 3~5문장. `PROMPT_VERSION = "a1"`.

## 5. 라우트

`POST /v2/review/ask` — 요청 `{"facts": <에이전트 사실표>, "question": "...", "history": [{"q","a"}] (선택, 최대 4)}`, 응답 `{"answer", "outcome", "tool_calls": [{"tool","args"}], "violations": [...], "prompt_version", "model", "elapsed_s", "usage"}`.

- 인증 · 호출 제한은 해설 라우트(`/v2/review/explain`)와 같은 것을 씁니다.
- 요청 검사: `version == 1`, 크기 상한(200KB), 질문 1~300자.
- 운영 배포 안 함: 브랜치 `feat/review-explain` worktree(`C:\Users\jjh7757\dev\mahjong-recognizer-review`)에서만. master에 올리는 것은 평가 뒤 사용자 결정.

## 6. 의존성

`langgraph` 를 서버 `requirements.txt` 에 고정 판으로 더합니다(이 노트북의 Python 3.13에 1.2.11이 깔려 있음). 운영 이미지에는 master에 올릴 때 들어갑니다.

## 7. 평가 (재기 전에 적는 안)

- **기계 시험(가짜 LLM, 돈 0):** 그래프 분기(도구 → 답 · 검증 실패 → 재시도 → 대체 · 도구 6회 한도 · 없는 차례 오류), 도구마다 사실표 값 그대로 돌려주는지, 검증 규칙(없는 패 · 없는 숫자 · 영어 · 도구 없이 답함).
- **사실표 대조:** 예시 11판 전부에서 `options` 가 `reviewPaifu` 의 `options` 와 같고, `best` 목록이 최선과 같은 값의 후보 전부와 같은지(Dart 시험).
- **실제 호출(사용자 허락 뒤):** 질문 세트 12개(본 판 r19 · r11 · r17 · r12 에서 — 개발용, 3종: 한 차례 "왜" 4 · 대안 "만약" 4 · 판 전체 4)를 미리 적고, 기록할 것: 검증 첫 통과 · 재시도 뒤 · 대체 비율, 도구 호출 수, 시간, 토큰. 사람이 읽어 틀린 문장 수. 숫자는 metrics.md 에 새 표로 적습니다. 정확도를 "된다"고 말하려면 안 본 판(r15 · r16 · r18 · r20 · r13 · r14 · L16)으로 다시 재야 합니다.

## 8. 고칠 · 만들 파일

| 저장소 | 파일 | 하는 일 |
| --- | --- | --- |
| 앱 | `lib/paifu/agent_facts.dart` (새) | 2절 사실표 |
| 앱 | `tool/paifu_agent_facts.dart` (새) | 파일로 내보내기 |
| 앱 | `test/agent_facts_test.dart` (새) | 사실표 시험(예시 11판) |
| 서버 | `app/review_agent.py` (새) | 도구 · 그래프 · 검증 · 대체 · 지시문 |
| 서버 | `app/main.py` | `POST /v2/review/ask` |
| 서버 | `tests/test_review_agent.py` (새) | 가짜 LLM 시험 |
| 서버 | `scripts/review_ask.py` (새) | 서버 없이 한 판 · 한 질문(`--fake` 로 가짜 LLM) |
| 서버 | `requirements.txt` | `langgraph` 고정 |

## 9. 위험과 한계

1. **패효율만 아는 에이전트입니다.** "수비를 했어야 했나" 같은 질문에는 현물 여부까지만 답할 수 있습니다. 지시문에 한계를 적고, 모르는 것은 모른다고 하게 합니다.
2. **검증은 숫자 · 패만 잡습니다.** "이 모양이 더 좋다" 같은 판단 문장의 틀림은 사람이 읽어야 잡힙니다(해설과 같은 빈틈).
3. **짐작 손패 차례**(`guessed`)는 숫자가 없어 "모른다"로 답해야 합니다.
4. **Gemini 비용 · 지연:** 질문 하나에 LLM 2~8회. 실제 숫자는 7절 실제 호출에서 잽니다.
