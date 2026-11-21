# 패보 손패 복원 버튼 — Claude API(Opus 5.5) 도구 읽기를 앱 안으로 (2026-11-21 설계)

사용자 요청(11-21): "버림기록만 있는 패보에서 버튼을 누르면 손패를 복구하게 만드는 기능 넣어줘" → 방식 질문에 "구현은 claude api 쓰는걸로 해, 실제로 돌리지는 말고".
**실제 API 호출은 하지 않는다**(무료 토큰 소진 — 메모리 `no-claude-api-credits`). 시험은 전부 가짜 HTTP 응답으로.

## 0. 근거가 된 오프라인 흐름

`experiments/paifu_frames/handtrack/` — 차례 나누기 `turncut.py` → 쉬움 거르기 `slotroute.py` → 재료 `opusread.py prep --nosam --fromplan` → Opus 읽기(하위 에이전트, 또는 API 판 `claudeagent.py`) → 거꾸로 복원 `rebuild_opus.py --full`.
숫자(11-14 다섯 판, 평가 밖): API Opus 고정 도구 안 본 17 에서 16/17 · 판 복원 4/5 · 판당 약 3.2달러(metrics 표 12-71), SAM 2 없는 하위 에이전트 + 사건 목록 r15 · L16 32/32(표 12-103).

## 1. 앱으로 옮길 때 바뀌는 것(알려진 차이)

| 오프라인 | 앱 v1 | 영향 |
| --- | --- | --- |
| 헤드 휴대폰 녹화 10fps → 5fps 로 줄여 씀 | 태블릿 "헤드 녹화 받아 저장"(`RecordPuller`, `rec_pull/<폴더>/f_<ms>.jpg`) 프레임을 5fps 로 골라 씀 | 같은 원천. 녹화를 안 받았으면 버튼이 안 나옴 |
| 손패 띠 `config/<판>.json` 의 `sheet_band`(손으로 정함) | 격자 `GridZones.seat(side)`(hero 자리 손패 구역)를 패보에 남겨 잘라 돌림 | 띠가 넓을 수 있음 — 그림이 커지면 LONG_EDGE 로 줄임 |
| 차례 경계: 앱 재생 결과의 강 새 패 시각 + `river_skin` | 패보 사건 시각(`at`, 버림 기록기의 `firstAt`)으로 같은 규칙 | 버림 기록기 시각은 3초 미리보기 간격이라 ±3초 — 창 양끝에 여유를 둠 |
| 쉬움 거르기(검출기 칸 틀, V1 ≤ 0) | **없음** — 리치 뒤 차례만 규칙(쯔모기리)으로, 나머지는 다 API | 쯔모기리 차례도 돈이 듦(차례당 0.09 ~ 0.39달러, 표 12-71) |
| 사건 목록 `events.txt`(ONNX 검출기 + HSV 손 가림) | **없음**(v1) | SAM 2 없는 읽기의 출발점이 빠짐 — 정확도는 안 잼. v2 후보: 기기 안 검출기(OnDeviceReader)로 칸 틀 |
| 도구 view · zoom · strip · check · answer(kind 인자) | view · zoom · strip · answer(원본만 — kind · check 없음) | `TASK_NOSAM` 과 같은 재료 꼴 |

## 2. 패보 형식(버전 1 그대로, 칸만 더함 — 옛 패보 · 예시 11판이 그대로 읽혀야 함)

- `PaifuEvent.at`(int, epoch ms, 선택): 버림 기록기가 그 패를 처음 본 시각. `DiscardRecorder.toPaifu` 가 채운다.
- `Paifu.frames`(선택): `{"dir": rec_pull 폴더 절대 경로, "box": [xmin, ymin, xmax, ymax] 0~1000 사진 비율 — hero 자리 손패 구역, "side": "bottom|right|top|left" — hero 가 사진에서 앉은 쪽, "start_ms", "end_ms"}`. 거치 화면 `_savePaifu` 가 녹화를 받아 저장하는 중일 때만 채운다.
- 복원 결과: hero 의 draw · discard 사건 `hand`, `start_hand`, 그리고 `hand_source`(`"claude_api"`)와 차례별 `restore` 메모(답 · 확신 · 규칙 차례 표시). 짐작(울기 뒤 순서 등)은 오프라인과 같은 표시를 쓴다(이미 있는 `guess` 표시가 있으면 그것).

## 3. 흐름

1. **차례 목록**(`lib/paifu/hand_restore/turns.dart`, 순수 Dart): hero 버림마다 한 차례. 창 시작 = 그 버림 직전 다른 자리 버림 시각 − 1.5초(없으면 hero 앞 버림 + 1초, 첫 차례는 hero 버림 − 20초), 창 끝 = 다음 차례 창 시작(마지막은 hero 버림 + 8초), 창 길이 상한 60초(앞쪽을 자름). 리치 선언 다음 차례 = 규칙(쯔모기리, API 안 부름). 퐁 · 치 바로 뒤 버림 = 오프라인처럼 짐작으로 끼움(API 안 부름).
2. **프레임**(`frames.dart`): `HandFrameSource` 인터페이스(목록 · 바이트) — 실제는 폴더, 시험은 메모리. 창 안 프레임을 5fps(200ms 간격에 가장 가까운 것)로 고르고, `box` 로 잘라 hero 시점으로 돌린다(`image` 패키지, 아래 = 탁자 테두리). 작업은 `compute`.
3. **API 클라이언트**(`claude_client.dart`): `package:http` `Client` 주입. `POST https://api.anthropic.com/v1/messages`, 헤더 `x-api-key` · `anthropic-version: 2023-06-01` · `content-type`. 요청 꼴은 `claudeagent.py` `request_kw` · `call` 과 같게: model `claude-opus-5-5`, `max_tokens` 32000, `output_config: {effort: "high"}`, thinking 안 줌, system 마지막 블록 `cache_control: {type: ephemeral}` + 최상위 `cache_control`, 도구 정의 고정. 재시도: 429 · 5xx · 연결 오류만 3번(10 · 20 · 30초, 시험에서는 주입한 sleep). 응답 content(thinking 포함)는 assistant 로 그대로 붙이고, 한 응답의 tool_result 는 한 user 메시지에, 도구 오류는 `is_error`.
4. **한 차례 읽기**(`turn_agent.dart`): system = `TASK_NOSAM`(opusread.py:123-151)을 도구 판으로 고친 글(파일 경로 · Read · Python 대신 도구 이름, events.txt 문장 삭제, 답은 answer 도구). 첫 메시지 = 줄 장수 · 프레임 목록(번호 · 시각) + 첫 · 끝 프레임 그림 + "도구로 필요한 프레임을 보며 읽고, 다 보면 answer 를 불러라." 도구 4개: `view{frames:int[]}`(앞 6장), `zoom{frame,x0,x1,y0?,y1?}`(배율 min(3, 1600/폭)), `strip{start,end,step,x0,x1,y0?,y1?}`(한 장 8줄 · 32줄까지, 왼쪽에 번호), `answer`(strict — kind · k · j · end_order · unsure · why). 한도: 단계 60 + 마무리 2, 차례당 5달러, 그림 560장 · 120MB, 긴 변 2576 초과는 줄임, 글로만 답하면 재촉 세 번째에 멈춤. 비용 = usage × (입력 4 · 출력 20 · 캐시 읽기 0.20 · 캐시 쓰기 5 달러/100만).
   end_order 가 온전하면 k · j 는 `sam2verify.from_order` 처럼 거기서 계산.
5. **복원**(`rebuild.dart`, 순수 Dart): `rebuild_opus.py` `back()` 를 그대로 — 끝 손패(화료 결과 `hand` + 화료패, 쯔모면 마지막 뽑기)에서 뒤로, D = 뽑은 패, 숫자 i = 시작 줄 i번, 빈 번호 하나 = 강 패(손에서 버림), D 없고 빈 번호 없음 = 쯔모기리. 실패(답 없음 · 모순)면 그 차례부터 앞은 손패 없음으로 두고 이유를 남김.
6. **실행기**(`restorer.dart`): 차례를 하나씩(동시 1) 돌리고 진행 · 누적 비용을 알림, 판 전체 한도(기본 10달러)를 넘기 전에 멈춤, 취소. 끝나면 복원한 패보를 `PaifuStore.put`(같은 id 바꿔 끼움), 원본은 `paifu.orig.<gameId>.<id>` 에 남겨 되돌리기.
7. **화면**(`paifu_screen.dart`): 손패 없는 패보(`!hasHeroHands`) · 끝 손패 있음 · `frames` 있음일 때 "시작 손패 입력" 옆에 **"손패 복원 (Claude API)"**. 누르면 → API 키(앱 안에 저장, 없으면 입력 창 — APK 에 넣지 않음) → 확인 창(API 차례 수 · 규칙 차례 수 · 어림 비용 "차례당 0.1 ~ 1.7달러, 판당 약 3달러(11-14 실험)" · 한도) → 진행 창(차례 i/N · 누적 달러 · 취소) → 결과(복원 차례 · 실패 · 확신 낮은 차례 · 비용) → 다시 그림. 복원한 패보에는 "되돌리기". 예시 패보(asset)에는 안 나옴. 키 · 녹화 폴더가 없으면 버튼 대신 까닭 한 줄.

## 4. 시험(실제 호출 없음)

- 형식: `at` · `frames` 없는 옛 JSON 과 예시 11판이 그대로 읽히고 다시 쓰면 같음.
- 차례 나누기 · 프레임 고르기 · 자르기 회전(작은 합성 그림).
- 복원: 손패가 적힌 예시 판(r15 등)에서 손패를 지우고, 정답 손패로 만든 (end_order) 답을 넣으면 원래 손패가 그대로 나옴. 쯔모기리 · 리치 뒤 · 울기 · 모순 답.
- 도구 루프: `MockClient`(package:http/testing)로 view → zoom → answer 대본, 요청 본문 꼴(model · effort · cache_control · tool_result 묶음 · is_error), 재시도, 비용 한도, 글로만 답함, 마무리 단계.
- 화면: 버튼 보임 · 숨김 조건, 가짜 실행기로 진행 · 결과 · 되돌리기.

## 5. 남은 것 · 재지 않은 것

- **앱 v1 은 정확도를 잰 적이 없다**(사건 목록 없음 · 띠가 다름 · 시각 ±3초). 잴 때는 11-14 판 녹화를 폴더 원천으로 주고 실제 API 를 불러야 해 사용자 허락이 필요하다.
- 쉬움 거르기와 사건 목록은 검출기가 있어야 한다 — 기기 안 검출기로 옮기면 비용이 준다(쯔모기리 차례 몫).
