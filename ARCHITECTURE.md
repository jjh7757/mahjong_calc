# 아키텍처 (2026-10-28 기준)

리치마작 점수 계산 앱의 구조 문서. **무엇이 어디에 있고, 무엇이 무엇에 의존하며, 데이터가 어떻게 흐르는지**만 적는다.
현황·다음 할 일은 `HANDOFF.md`, 각 기능의 결정 근거는 `docs/*_design.md` 와 `docs/problem_log.md` 에 있다.

## 1. 한눈에 보기

```
┌──────────────────────────────── 기기 (Flutter, Android 우선 · 웹 · Windows) ────────────────────────────────┐
│                                                                                                             │
│   lib/ui/            화면. 폰 = 계산기, 태블릿 가로 = 키오스크(로비·테이블·화료 연출)                          │
│      │  ▲                                                                                                   │
│      ▼  │ ChangeNotifier(HandEditor·GameStore) / 함수 호출                                                   │
│   lib/table/         거치 촬영 판독 파이프라인 (순수 Dart + image 패키지)                                      │
│   lib/game/          대국 기록 모델·저장 (순수 Dart)                                                          │
│   lib/quiz/          연습 퀴즈 생성 (순수 Dart)                                                               │
│   lib/services/      바깥 세계와의 접점: 인식 서버 HTTP, 카메라 헤드 HTTP, 음성, Android 채널                   │
│      │                                                                                                      │
│      ▼                                                                                                      │
│   lib/engine/        점수 계산 엔진 (순수 Dart, 의존 없음). 점수는 **항상 기기 안에서** 계산한다               │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
          │ HTTPS multipart (X-Api-Key)                       │ HTTP, 같은 Wi-Fi (X-Head-Token)
          ▼                                                    ▼
  인식 서버 mahjong-recognizer                         카메라 헤드 (같은 앱의 다른 기기)
  https://mahjong.ai-agent-develop.cloud               GET /capture · /preview · /status
  Gemini 비전 = 패 읽기, YOLO11 = 강 틀 위치만
```

원칙 세 가지.

1. **AI 는 사진을 읽기만 하고, 점수는 Dart 엔진이 낸다.** 서버 응답은 "모델이 본 것"(관찰 JSON)이고, 리치·울기 종류·론/쯔모 판단은 앱 코드(`lib/table/observation.dart`, `merge.dart`)가 한다.
2. **아래 층은 위 층을 모른다.** `engine` → 아무것도 안 봄. `game`·`quiz` → `engine` 만. `table` → `engine`·`game`·`services/recognizer_client`. `services` → `engine`·`game`·`table`(기록용). `ui` → 전부. Flutter 위젯은 `ui/` 와 `services/` 의 플랫폼 접점에만 있다.
3. **무거운 일은 isolate 로.** 12MP 디코딩·크롭·펠트 분석은 `compute()` 또는 전용 isolate(`IsolateShotImage`)에서 돌리고, 웹은 같은 스레드(`DirectShotImage`)로 돌아간다.

## 2. 층별 모듈

### 2.1 `lib/engine/` — 점수 계산 (순수 Dart, 외부 의존 없음)

| 파일 | 역할 |
| --- | --- |
| `tile.dart` | 패 표현. 0~33 정수, 문자열 코드(`5m` `1z` `0m`=적5). 모든 층이 이 표현을 공유한다 |
| `meld.dart` | 부른 묶음(치·펑·깡, 안깡은 `isOpen=false`) |
| `hand.dart` | `Hand`(닫힌 패 + 울기 + 화료패), `Situation`(자풍·장풍·리치·쯔모·본장 등), `RuleSet` |
| `decompose.dart` | 손패를 묶음 조합으로 분해(일반형·칠대자·국사) |
| `yaku.dart` | 역 목록과 판정. 멘젠/울음 판수, 역만 배수 |
| `fu.dart` | 부수 계산과 내역 |
| `score.dart` | 판·부 → 기본점(`basePoints`), 역만(`yakumanPoints`), 지불 분배(`payment`), 끌어올림 만관 |
| `calculator.dart` | 진입점. 가능한 분해마다 역·부를 내고 가장 높은 `ScoreResult` 를 고른다. 파오·첫 순 역만 처리 |
| `waits.dart` | 13장 손패의 대기패와 각 대기의 론/쯔모 점수 |

의존 방향: `tile` ← `meld` ← `hand` ← `decompose` ← `yaku`·`fu` ← `calculator` ← `waits`. `score` 는 `hand` 만 본다.

### 2.2 `lib/game/` — 대국 기록 (순수 Dart)

| 파일 | 역할 |
| --- | --- |
| `game.dart` | `GameSettings`(이름·시작점·우마·오카·반장/동풍), `GameEvent`(리치·화료·유국·정정), `GameCheckpoint`, `Game`(점수 이동·본장·공탁·친 교체·`Settlement`), `Game.resumed`(중간부터) |
| `game_store.dart` | `GameStore extends ChangeNotifier`. 진행 중 대국 + 끝난 대국 목록을 `shared_preferences` 에 저장. 전역 `gameStore` |

`game` 은 `engine/calculator`·`score` 만 본다(화료 점수 계산). 되돌리기는 체크포인트 방식(`ui/game/record_edit.dart`).

### 2.3 `lib/table/` — 거치 촬영 판독 파이프라인 (순수 Dart + `image`)

사진 한 장 → 계산 입력(`Hand` + `Situation`)까지. 설계: `docs/table_reading_design.md`, `docs/state_tracking_design.md`.

| 파일 | 역할 | 의존 |
| --- | --- | --- |
| `table_layout.dart` | 구역 모델(`TableLayout`, 이미지 기준 자리 `Side`). 좌표 0~1000 정규화 | — |
| `table_reading.dart` | 서버 판독 결과 모델(`HandReading`·`CenterReading`·`ReadTile`) | engine/tile |
| `observation.dart` | `/v2/*` 관찰 JSON 파서. 울기 종류·강 끝·리치봉 **판단**은 여기서 | table_reading |
| `seat_map.dart` | 이미지 자리(`Side`) ↔ 대국 자리(0~3) | table_layout |
| `cropper.dart` | 원본에서 구역 크롭·회전(`cropMany`), 축소(`shrinkForLocate`) | table_layout |
| `shot_image.dart` | 원본을 **한 번만 디코딩**해 두는 `ShotImage`(isolate 또는 직접) | cropper |
| `fixed_layout.dart` | 고정 카메라: 펠트 IoU 로 카메라 이동 감지, 앞면 손패·도라 표시패 픽셀 검출, 울기 모서리 | table_layout |
| `grid_zones.dart` | 사용자가 한 번 맞춘 격자 5구역(자리 4 + 가운데). locate 를 대체 | fixed_layout |
| `rectify.dart` | 기운 탁자 원근 보정(펠트 네 모서리 → 정사각형) | fixed_layout, grid_zones |
| `corner_change.dart` | 모서리 칸 픽셀 통계(`CornerStats`)와 변화 척도. 추적의 입력 | fixed_layout, grid_zones |
| `tracker.dart` | `MeldTracker`: 게임 중 자리별 울기 미리 읽기 상태 기계(idle→moving→changed→reading→confirmed/unconfirmed) | corner_change, observation |
| `table_reader.dart` | **오케스트레이터** `TableReader`. `read`(locate/fixed) · `readGrid`(격자). 구역별 크롭을 동시에 서버로 보내고 `TableReading` 으로 모음. `TableReadTrace` 에 단계별 시간·토큰 | services/recognizer_client, 위 전부 |
| `merge.dart` | `TableMerge`: 판독 + `Game` → `Hand`·`Situation` + 추정(화료자·론/쯔모·방총자) + `MergeFlag` 목록 | engine, game, seat_map |
| `auto_record.dart` | 사람 확인 없이 대국에 반영해도 되는지(`autoRecordBlocker`) | merge |

### 2.4 `lib/services/` — 바깥 접점

| 파일 | 역할 | 플랫폼 |
| --- | --- | --- |
| `recognizer_client.dart` | 인식 서버 HTTP 클라이언트. `/v1/recognize`·`/v1/locate`·`/v1/table`, `/v2/<kind>`(`seat`·`hand`·`handonly`·`meld`·`corner`·`dora`·`sticks`), `/v2/last3`(여러 장). 키는 `--dart-define=RECOGNIZER_API_KEY` | 전부 |
| `camera_head.dart` | 카메라 헤드 **서버**(`CameraHeadServer`: `/capture`·`/preview?w=`·`/status`, 토큰 인증)와 **클라이언트**(`RemoteCamera`), QR 링크(`CameraHeadLink`) | 전부(서버는 기기) |
| `capture_log.dart` | 촬영 기록 `Download/mahjong_calc/<시각>/`(원본·크롭·응답·병합·`meta.json`). "대국에 반영" 시 `label.json` 정답. 학습 데이터셋 축적 목적 | Android 채널 `…/files`, 데스크톱은 다운로드 폴더 |
| `yuv_jpeg.dart` | 미리보기 YUV420 → JPEG (isolate 용 바이트만) | 전부 |
| `announcer.dart`, `voice_lines.dart` | 화료 결과 음성. 미리 만든 mp3(`assets/voice/<목소리>/`) 우선, 없으면 기기 TTS | 전부 |
| `volume_keys.dart` | 볼륨키를 촬영 버튼으로 | Android 채널 `…/volume` |
| `screen_wake.dart` | 화면 꺼짐 방지 | Android 채널 `…/screen` |

Android 채널 세 개(`dev.jjh.mahjong_calc/{files,volume,screen}`)는 모두 `android/app/src/main/kotlin/dev/jjh/mahjong_calc/MainActivity.kt` 하나가 받는다. 채널이 없는 플랫폼에서는 조용히 아무 일도 하지 않는다.

### 2.5 `lib/quiz/` — 연습 퀴즈

`quiz_generator.dart` 가 무작위 화료 손패(역 있음, 역만 제외, 30% 울음)를 만들고 `engine` 으로 정답을 낸다.

### 2.6 `lib/ui/` — 화면

`main.dart` 의 `MahjongApp` 이 `HandEditor`(입력 상태)와 `gameStore` 를 만들고, 화면 폭으로 첫 화면을 고른다(`isKioskLayout`).

```
폰(세로)                              키오스크(태블릿 가로, kiosk.dart)
InputScreen ── 사진 ── PhotoInput      KioskLobby ──(대국 시작/이어 하기)──▶ MountScreen(테이블, 거치 촬영)
   │  메뉴: 점수표·퀴즈·설정·대국          │  메뉴: 계산기·점수표·퀴즈·설정            │ 화료 판독
   ▼                                     ▼                                        ▼
ResultScreen ──"대국에 반영"──▶ GameScreen(점수판) ──▶ SettlementScreen        ResultKiosk(화료 연출)
```

| 영역 | 파일 | 역할 |
| --- | --- | --- |
| 입력 상태 | `hand_editor.dart` | `HandEditor extends ChangeNotifier`. 손패·울기·도라·상황·룰. 대국과 동기화(`syncFromGame`·`setGameSeat`). 모든 입력 화면이 공유 |
| 계산기 | `input_screen.dart`, `kiosk_input.dart`, `meld_sheet.dart`, `waits_sheet.dart`, `photo_input.dart`, `tile_view.dart` | 패 팔레트·울기 시트·대기패 시트·사진 입력. 패 그림은 `assets/tiles/`(CC0) |
| 결과 | `result_screen.dart`, `result_kiosk.dart`, `score_cross.dart` | 역·부·점수·점수 이동판, 음성, "대국에 반영", "판독 수정". 키오스크는 1280 캔버스 연출 |
| 대국 | `game/game_screen.dart`, `win_sheet.dart`, `record_edit.dart`, `settlement_screen.dart`, `history_screen.dart` | 점수판(리치·화료·유국), 되돌리기·정정, 정산, 지난 대국 |
| 거치 촬영 | `mount/mount_screen.dart`(1700줄, 가장 큰 파일), `grid_editor.dart`, `score_panel.dart`, `capture_label.dart`, `camera_head_screen.dart`, `qr_scan_screen.dart` | 테이블 화면. 카메라/헤드 소스 선택, 격자 편집, 촬영→판독→병합→결과, 배경 미리보기 3초 폴링 + 울기 추적, 자동 반영(10초 뒤) |
| 기타 | `score_table_screen.dart`, `quiz_screen.dart`, `settings_screen.dart`(`RulesStore`), `kiosk_lobby.dart` | 점수표·퀴즈·룰 설정 저장·로비 |

## 3. 핵심 데이터 흐름

### 3.1 직접 입력 계산

```
팔레트 탭 ─▶ HandEditor(ChangeNotifier) ─▶ calculate(Hand, Situation, RuleSet) ─▶ ScoreResult ─▶ ResultScreen
                                                                                         └─"대국에 반영"─▶ Game.record → GameStore.save
```

### 3.2 사진 손패 입력 (2단계)

```
image_picker ─▶ RecognizerClient.recognize (/v1/recognize) ─▶ RecognizeResult ─▶ HandEditor 채움(확신 낮은 패는 노란 테두리)
```

### 3.3 거치 촬영 화료 판독 (격자 경로, 현재 기본)

```
촬영 (기기 camera 또는 RemoteCamera.capture /capture, 12MP JPEG)
  │
  ├─ CaptureLog: 원본 저장
  ▼
ShotImage.open (isolate, 한 번만 디코딩)
  │
  ├─ 축소본 ─▶ analyzeGridShot (펠트 IoU·앞면 자리·도라 덩어리, API 없음)  ─▶ 화료자 자리 후보
  │                                                                       (둘 이상이면 _pickWinners 로 물음)
  ▼
TableReader.readGrid(GridZones)   ── 구역별 크롭을 동시에 ──▶  /v2/seat (화료자 자리, 3회 동시 + 만장일치)
  │                                                          /v2/last3 (다른 자리 강 끝 패, 한 번에)
  │   tracked 자리는 /v2/handonly 로 손패만 ◀── MeldTracker      /v2/sticks (리치봉)   /v2/dora (가운데)
  │   (장수 ≠ 14 면 /v2/seat 로 복귀)
  ▼
TableReading (+ TableReadTrace: 단계 시간·토큰·usage)
  │
  ▼
TableMerge.merge(reading, Game, SeatMap)  ─▶ Hand + Situation + 화료자·론/쯔모·방총자 추정 + MergeFlag[]
  │                                               (자풍·장풍·본장은 기록에서, 도라는 사진에서, 리치는 둘 중 하나)
  ├─ CaptureLog: 크롭·응답·병합 결과 저장, 정답 대기(PendingCapture)
  ▼
calculate() ─▶ ResultScreen / ResultKiosk
  │   autoRecordBlocker == null 이면 10초 뒤 자동 반영, 아니면 플래그 카드 + "판독 수정"
  ▼
"대국에 반영" ─▶ Game.record ─▶ capture_label: label.json (같은 국, 20분 안이면)
```

locate 경로(`TableReader.read`, `/v1/locate` → `FixedTable` 재사용)는 격자를 안 맞춘 경우의 대체 경로로 남아 있다.

### 3.4 게임 중 울기 추적 (설계 `docs/state_tracking_design.md`)

```
RemoteCamera.preview (3초, 긴 변 960) ─▶ analyzeCorners (isolate, CornerStats) ─▶ MeldTracker.onFrame
                                                                                     │ TrackerAction(자리, 프레임)
                                                                                     ▼
                                                     모서리 칸 크롭 ─▶ /v2/corner ─▶ MeldTracker.onRead
                                                                                     │ 다른 프레임 두 번 일치 → confirmed
                                                                                     ▼
                                                                   ScorePanel 울기 칩 (살아 있음, 누르면 다시 읽기)
                                                                   화료 때 readGrid(tracked: …) 로 손패 전용 경로
```

### 3.5 카메라 헤드 (두 기기)

```
헤드 기기 (CameraHeadScreen)                         조작 기기 (MountScreen)
  camera 미리보기 ─▶ YUV→JPEG ─▶ CameraHeadServer     QR 스캔(QrScanScreen) ─▶ CameraHeadLink(주소+토큰)
  GET /preview?w=  (스트림 프레임)        ◀──────────── RemoteCamera.preview (3초 폴링, 추적·배경)
  GET /capture     (12MP 촬영)           ◀──────────── RemoteCamera.capture (화료 때)
  GET /status                            ◀──────────── 연결 확인
  ScreenWake 로 화면 유지
```

## 4. 바깥 시스템과의 계약

| 상대 | 위치 | 계약 |
| --- | --- | --- |
| 인식 서버 | `C:\Users\jjh7757\dev\mahjong-recognizer`, GitHub `jjh7757/mahjong-recognizer` | multipart `image`, 헤더 `X-Api-Key`, JSON 응답에 `notes`·`model`·`latency_ms`·`usage` 공통. `/v2/*` 는 관찰 JSON(`observation.dart` 주석에 스키마) |
| 로컬 인식 서버 | `experiments/yolo/run_local_server.py`, `.claude/launch.json` "recognizer"(8030) | 운영과 같은 코드를 노트북에서 |
| Gemini 키 | 서버 쪽 `.env` (앱에는 없음) | 앱은 서버 키만 가진다 |
| 저장소 | `shared_preferences` | 룰(`RulesStore`), 대국(`GameStore`), 퀴즈 정답 수, 촬영 기록 켬/끔, 자동 반영 켬/끔, 격자 |
| 파일 | Android MediaStore Downloads / 데스크톱 다운로드 폴더 | `mahjong_calc/<시각>/{original.jpg, *_crop.jpg, *.json, meta.json, label.json}` |

## 5. 테스트와 실험

| 위치 | 무엇 | 실행 |
| --- | --- | --- |
| `test/` (33개) | 엔진(`engine_test`), 대국(`undo`·`pao`·`tobi_abortive`·`multi_ron`…), 판독 파이프라인(`table_reader`·`merge`는 `table_test`, `tracker`, `corner_change`, `fixed_layout`, `grid_zones`, `rectify`, `shot_image`), 서비스(`recognizer_client`·`camera_head`·`announcer`·`capture_label`), 위젯 흐름(`widget_test`·`kiosk_*`·`result_screen`·`settlement_screen`) | `flutter test` |
| `integration_test/` | 에뮬레이터에서 판독 시간(`read_grid_timing_test`, `SET=field` 가 테스트 세트), 추적 흐름, 데스크톱 촬영 기록 | `flutter test integration_test -d …` |
| `tool/` | 음성 파일 생성(`make_voice.py` ← `dart run tool/voice_lines.dart`), 화료 연출 렌더, 대국 시드 | 수동 |
| `experiments/` | 날짜·주제별 실험(vlm, yolo, template, rectify, speed, tracking, field_20261024…). 결론은 `experiments/vlm/RESULTS.md` 와 `docs/problem_log.md` | Python/Dart 스크립트 |

평가 규칙(2026-10-27): 갤러리 B·C·D 6장 = 개발 세트, 10/24 매장 삼각대 15장 = 테스트 세트(규칙 고치는 데 안 쓰고 한 번만 잼). 실험 코드는 `lib/` 에 넣지 않는다.

## 6. 자주 헷갈리는 경계

- **`Side` vs 자리 번호**: `Side`(bottom/right/top/left)는 사진 기준, 0~3 은 대국 기준(기동 동 = 0). 변환은 `SeatMap` 만 한다.
- **`ReadTile` vs `HandTile` vs 정수 패**: 서버가 읽은 패(확신·적도라 플래그) → 병합 후 `MergedTile` → 입력 상태 `HandTile` → 엔진 정수. 적도라 코드 `0m` 은 엔진에서 5 + red 플래그.
- **관찰과 판단**: 서버 JSON 은 "앞면이다", "가로로 놓였다" 까지만. "리치다", "펑이다", "론이다" 는 앱이 정한다. 규칙을 고칠 때는 `observation.dart`·`merge.dart` 를 보고, 프롬프트는 서버 저장소를 본다.
- **`HandEditor` 는 하나**: `main.dart` 가 만들어 모든 화면에 넘긴다. 대국과의 동기화(국이 바뀌면 장풍·본장 재채움, 같은 국의 손수정은 유지)도 여기 안에 있다.
- **키오스크 판단은 폭으로만**(`isKioskLayout`). 같은 빌드가 폰과 태블릿에서 다른 첫 화면을 띄운다.
