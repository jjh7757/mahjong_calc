# 전체 판독(거치 촬영 모드) 설계 (2026-10-23)

폰을 테이블 위에 고정해 두고, 화료 때 사진 한 장으로 손패·울기·도라·리치·화료자·론/쯔모를 읽어 대국 기록과 합쳐 점수를 내는 기능. 사진 실험 세트가 없는 상태에서 코드부터 만들기 위한 구조 문서다.

## 결정 사항

| 항목 | 결정 | 이유 |
| --- | --- | --- |
| 구역 지정 | 매 촬영마다 Gemini 가 위치를 찾음(locate). 보정 화면 없음 | 사용자가 맞출 게 없음. `TableLayout` 은 저장 가능한 값으로 두어 나중에 재사용 최적화 가능 |
| 촬영 | `camera` 패키지. 앱 안 미리보기, 원본 해상도, 볼륨키 트리거 | image_picker 는 1600px 로 줄이고 가이드를 못 그림 |
| 크롭 | 폰에서 원본을 자르고 회전한 뒤 구역별로 전송 | 서버가 긴 변 1568px 로 줄이므로 전경을 보내면 패가 30px 이 됨. 패는 **100px 이상** 필요 |
| 읽는 범위 | 손패·울기·도라·리치·화료자·화료패·방총자 전부 1차 버전에 | 틀리면 결과 화면에서 고침 |
| 화료자 | 사진에서 추정(앞면으로 눕힌 자리). 둘 이상이면 물음 | 탭 한 번을 줄임 |
| 대국 연결 | 대국 기록 중에만 사용 | 자풍·장풍·본장·공탁·자리 배치를 기록에서 가져옴 |
| 결과 표시 | 바로 결과 화면. 결과 화면에서 "판독 수정" 으로 되돌아감 | 탭 수 최소 |
| 론/쯔모·방총자 | 사진에서 추정, 확신 낮으면 결과 화면에 선택 칩 표시 | 추정 규칙은 아래 |

## 화료 1회의 흐름

```
[촬영] 원본 JPEG (12MP+)
  │
  ├─ 줄인 사본(긴 변 1024) ──▶ POST /v1/locate ──▶ TableLayout (구역 좌표·회전·눕힌 자리)
  │                                                     │
  ├─ 원본에서 화료자 손패 구역 크롭·회전 ──▶ POST /v1/recognize ─┐
  │                                                              ├─ 병렬
  └─ 원본에서 중앙 구역 크롭 ───────────▶ POST /v1/table ────────┘
                                                        │
                                                  TableReading
                                                        │
                            대국 기록(Game) ──▶ merge ──▶ Hand + Situation + 추정(화료자·론/쯔모·방총자)
                                                        │
                                                  calculate() ──▶ ResultScreen (판독 수정·대국에 반영)
```

지연 예상: locate 5~10초 + 2차 두 호출 병렬 5~15초 = 화료당 15~25초. 화료자 추정이 둘 이상이면 2차 전에 한 줄 질문.

## 서버 API

기존 `/v1/recognize` 는 유지하고 스키마만 확장한다. 세 엔드포인트 모두 `X-Api-Key`, multipart `image`, JSON 응답, `notes`·`model`·`latency_ms` 공통.

### POST /v1/locate

입력: 테이블 전경(긴 변 1024 로 줄인 것). 출력 좌표는 0~1000 정규화(Gemini 경계 상자 관례, `[ymin, xmin, ymax, xmax]`).

```json
{
  "hands": [
    {"side": "bottom", "box": [820, 180, 960, 820], "face_up": true,  "confidence": 0.9},
    {"side": "right",  "box": [...],                "face_up": false, "confidence": 0.8},
    {"side": "top",    "box": [...],                "face_up": false, "confidence": 0.8},
    {"side": "left",   "box": [...],                "face_up": false, "confidence": 0.7}
  ],
  "rivers": [{"side": "bottom", "box": [...]}, ...],
  "dead_wall": {"box": [...], "confidence": 0.6},
  "center": {"box": [...]},
  "notes": ""
}
```

- `side` 는 **이미지 기준** 아래·오른쪽·위·왼쪽. 자리(동남서북)로 바꾸는 건 앱이 대국 기록으로 한다.
- `face_up` 이 true 인 자리가 화료자 후보. 손패 구역은 울기 그룹까지 포함해 잡으라고 프롬프트에 쓴다.
- `center` 는 강 4개와 왕패를 모두 덮는 상자. `/v1/table` 에 보낼 크롭이다.
- 회전각은 `side` 로 정해진다(bottom 0°, right 90°, top 180°, left 270°). 앱이 크롭 뒤 그만큼 돌려 글자를 바로 세운다.

### POST /v1/recognize (확장)

입력: 화료자 손패 크롭(바로 세운 것). 출력에 울기와 화료패를 분리한다.

```json
{
  "tiles": [{"code": "2m", "confidence": 0.95}, ...],
  "melds": [
    {"type": "chi|pon|kan_open|kan_closed", "tiles": ["4p","5p","6p"], "called_index": 1, "confidence": 0.8}
  ],
  "win_tile": {"code": "7s", "confidence": 0.7},
  "notes": ""
}
```

- `tiles` 는 손에 들고 있던 패(멘젠 부분)만. 울기는 `melds` 로, 손패 오른쪽에 떨어져 놓인 그룹에서 옆으로 눕힌 패가 있으면 울기로 판단.
- `win_tile` 은 손패에서 조금 떨어뜨려 놓은 한 장. 없으면 null. 있으면 `tiles` 에 포함하지 않는다.
- 기존 앱 호출과의 호환: `melds`·`win_tile` 이 없는 응답도 받아들인다(`HandEditor.setFromRecognition` 은 그대로).

### POST /v1/table

입력: 중앙 크롭. 출력:

```json
{
  "dora_indicators": [{"code": "3p", "confidence": 0.9}],
  "ura_dora_indicators": [],
  "riichi": {"bottom": true, "right": false, "top": false, "left": true},
  "last_discards": {"bottom": "7s", "right": "1z", "top": null, "left": "9m"},
  "notes": ""
}
```

- `riichi` 는 강에 옆으로 눕힌 패(횡치)가 있는지. 자동탁 리치봉 슬롯 표시등도 참고하라고 프롬프트에 쓴다.
- `last_discards` 는 각 강의 마지막 패. 방총자 추정에 쓴다.
- `ura_dora_indicators`(2026-10-23 추가): 리치 화료 뒤 공개한 뒷도라 표시패(도라 표시패 아랫단을 뒤집은 것. 아랫단에서 앞면이 보이거나 도라 표시패 옆·앞에 짝지어 놓임). 공개 전이면 빈 배열. 프롬프트는 같은 패를 도라와 겹쳐 넣지 말고, 깡도라인지 뒷도라인지 헷갈리면 notes 에 적게 한다. 게임 캡처에는 뒷도라가 안 보이므로 실제 패 사진으로 검증해야 한다.
- 중앙 크롭도 전체를 한 번에 읽기엔 패가 작을 수 있다. 1차 실험에서 안 읽히면 강 4개를 따로 잘라 4호출로 쪼개는 것을 대안으로 둔다(`rivers` 상자를 locate 가 이미 주므로 앱 쪽 변경만으로 가능).

### 서버 공통 변경

- `MAX_CONCURRENT` 2 → 4, `RATE_PER_MIN` 20 → 40 (화료 1회에 3호출).
- 로그에 tiles·notes 를 남긴다(10-23 반영, 배포 대기).
- 프롬프트 3종은 `app/prompts.py` 로 분리. 스키마는 `app/schemas.py`.
- 테스트: 각 엔드포인트를 가짜 recognizer 로 스키마 검증. 실제 사진 회귀 테스트는 `experiments/vlm/recognize_vlm.py` 에 `--mode locate|hand|table` 추가.

## 앱 구조

```
lib/
  services/recognizer_client.dart   [완료] recognize(File)/recognizeBytes → RecognizeResult(.reading: HandReading), locate(bytes) → TableLayout, readTable(bytes) → CenterReading
  table/
    table_layout.dart     [완료] Side, NormBox(0~1000 → PixelRect, pad), HandZone/SidedZone/Zone, TableLayout(fromJson/toJson, faceUpSides, singleFaceUp)
    cropper.dart          [완료] TableImage.decode → shrunkJpeg(locate 용) / cropImage·cropJpeg(box, side, pad). handCropPad 0.04, centerCropPad 0.05
    table_reading.dart    [완료] ReadTile(적도라→5+red), ReadMeld, HandReading(/v1/recognize), CenterReading(/v1/table), TableReading
    table_reader.dart     [완료] TableReader(client, ops).read(bytes, winnerSide?, pickWinner, onStage) : locate → 화료자 결정 → 크롭 → 병렬 2차 → TableReading(warnings). ImageOps 로 isolate 주입
    seat_map.dart         [완료] SeatMap(bottomSeat) : seatOf(Side) / sideOf(seat). 반시계: bottom→right→top→left
    merge.dart            [완료] mergeReading(hand, center, winnerSide, game, seats) → TableMerge(closed, melds, meldRed, situation, hand?, uncertain, flags[MergeIssue])
  ui/mount/
    mount_screen.dart     [완료] camera 미리보기, 촬영·갤러리 버튼, 볼륨키(MethodChannel), 직전 TableLayout 오버레이, 단계·경과 초 다이얼로그, 화료자 선택, 오류 다이얼로그. 더보기 "카메라 헤드 QR 스캔"·"원격 카메라 주소"(주소·토큰) 로 카메라 헤드에서 사진을 받는 모드(아래 "카메라 헤드")
    camera_head_screen.dart [완료] 카메라 헤드 화면: 화면 가득 미리보기(자르지 않음) + 줌 칩(1~4x, 촬영에도 적용, 기기 저장) + 반투명 QR·주소·상태 패널 + "새 QR"(토큰 재발급). 화면 꺼짐 방지(dev.jjh.mahjong_calc/screen 채널)
    qr_scan_screen.dart   [완료] mobile_scanner 로 카메라 헤드 QR 을 읽어 CameraHeadLink 를 돌려준다(카메라 헤드 QR 이 보이면 바로 닫힘)
    tile_guide.dart       [삭제 2026-10-27] 패 최소(원본 100px) 가이드 페인터. 고정 거치라 손으로 맞출 일이 없어 거치·헤드 화면 모두에서 뺌(사용자)
  services/camera_head.dart [완료] CameraHeadServer(dart:io HttpServer, GET /capture·/status, 토큰 인증, 촬영 직렬화) / CameraHeadLink(QR 문자열 만들기·해석) / generateHeadToken·tokenEquals / RemoteCamera(normalize, token, capture, status) / localIPv4Addresses
    (판독 수정)           [완료] 별도 시트 대신 HandEditor.setFromMerge 로 입력 화면을 채우고, ResultScreen 의 "판독 수정" 이 입력 화면으로 돌아간다. 플래그는 ResultScreen 상단 카드
```

### 자리 매핑

대국 시작 폼에 "화면 아래쪽에 앉은 사람" 선택을 추가한다(`GameSettings.bottomSeat`, 기본 0). 위에서 내려다본 사진에서 차례는 반시계 방향이므로 아래→오른쪽→위→왼쪽이 자리 순서다. `SeatMap.seatOf(Side)`, `SeatMap.sideOf(seat)`.

### merge 규칙

1. 화료자: `face_up` 인 side 가 정확히 1개면 그 자리. 0개면 "눕힌 손패를 못 찾음" 으로 중단(촬영 안내). 2개 이상이면 locate 직후 자리 선택 질문(더블론은 미지원, 한 명만 고름).
   **동시 론(2026-10-26, 격자 판독만):** 눕힌 손패가 2~3자리면 선택 창에 한 명씩 + "둘 다 론(더블론)"/"셋 다 론(트리플론)" 이 나온다. 대국 규칙(`GameSettings.multiRon`, 대국 시작 폼 "동시 론")이 더블론 인정·트리플론 유국(기본)이면 셋일 때 "트리플론 유국으로 기록"(`Game.abortiveDraw`: 점수 이동 없음, 친 유지, 본장 +1, 공탁 유지)이 바로 기록되고 판독을 멈춘다. 여럿을 고르면 `readGrid` 가 자리마다 `TableReading` 을 만들어(`others`) 화료자마다 merge 하고(`otherWinners` 는 방총자 후보에서 뺌), `pickRonWinners` 가 방총자 다음 차례부터 가까운 순으로 정렬해 규칙 인원만 남긴다(머리치기면 한 명, 쯔모로 읽힌 손패가 섞이면 첫 손패만). 결과 화면은 대표 화료자 + "함께 론한 사람" 카드, "대국에 반영" 은 화료 시트에 다른 화료자를 미리 채워 `Game.multiRon` 으로 한 번에 기록한다(화료자별 론 점수, 본장·공탁은 가까운 쪽, 친이 화료자 중에 있으면 연장). locate 판독은 지금처럼 한 명만.
2. 자풍·장풍·본장·공탁: `Game` 에서. 리치 여부는 사진 `riichi[side]` 와 기록 `riichiDeclared[seat]` 를 합쳐 하나라도 true 면 리치. 둘이 어긋나면 `flags` 에 "리치 불일치" 를 넣어 결과 화면에 칩으로 표시(한 줄 질문). 단 울린 손패(안깡 제외)는 리치가 불가능하므로 사진·기록의 리치를 버리고 `riichiImpossible` 플래그만 남긴다(2026-10-23 실기기 기록: 발 퐁 손패인데 중앙 판독이 리치 램프를 봄).
3. 도라 표시패: 사진 값. 뒷도라 표시패도 사진 값(`CenterReading.uraIndicators`)이며 리치 화료일 때만 `Situation.uraIndicators` 와 입력 화면 "뒷도라" 칸에 넣는다. 리치가 아닌데 보이면 버리고 `uraIgnored` 플래그. 뒷도라를 뒤집기 전에 찍었으면 비어 있으니 "판독 수정" 에서 넣는다(촬영 순서: 화료 → 손패 공개 → 리치면 뒷도라 뒤집기 → 촬영). 촬영 기록 meta.json 의 `merge.ura_indicators` 와 label.json 의 `ura_indicators` 를 집계 "뒷도라" 열(리치 화료만)이 비교한다.
   (2026-10-24 바뀜: 도라·뒷도라를 가르지 않고 보인 앞면 표시패를 모두 도라 표시패로 센다 — 리치 화료면 점수가 같다. `uraIgnored` 삭제.)
   **매장 관행(2026-10-26 사용자가 실제 매장에서 본 것):** 리치로 화료하면 화료자가 도라 표시패와 뒷도라 표시패를 **자기 자리(손패 옆)로 가져가** 점수를 계산하고, 리치 없이 화료하면 도라 표시패를 가져오지 않고(왕패 자리 그대로) 바로 계산한다.
   기록과도 맞는다: 갤러리 C·E(리치 화료)는 표시패 두~세 장이 화료자 손패 옆, 10/24 매장 12:00·13:05(리치)도 "손패 옆", 13:05 정답 도라 5s·뒷도라 9s 짝. D(치, 리치 없음)는 가운데 쪽.
   → **반영(2026-10-26):** `readGrid` 는 가운데 `/v2/dora` 결과(`CenterReading.doraIndicators`)와 화료자 자리의 따로 놓인 앞면 패(`handSideIndicators`, 없으면 울기 모양이 아닌 묶음)를 따로 넘기고, merge 가 리치 화료면 손패 옆을, 아니면 가운데를 먼저 쓰고 비었을 때만 다른 쪽을 쓴다. 깡이면 도라 2장·뒷도라 1장처럼 홀수일 수 있어 장수 짝 검사는 하지 않는다(사용자 결정).
4. 론/쯔모: `win_tile` 이 있고 어떤 side 의 `last_discards` 와 같으면 **론**, 그 side 가 방총자. 일치하는 side 가 0개면 **쯔모**. `win_tile` 이 null 이면 `tiles` 마지막 장을 화료패로 쓰고 "화료패 확인" 플래그.
   **후보가 2개 이상이면(2026-10-27):** 예전엔 14장 경로는 방총자를 비워 사용자에게 묻고, 13장 경로(강 끝에서 화료패 찾기)는 자리 순서로 찍었다. 지금은 두 경로 모두 **화료자 다음 차례부터 세어 가장 가까운 자리**를 방총자로 자동 결정한다(`_nearestAfterWinner`, `Game.ronOrder` 재사용). 근거는 동순 후리텐: 먼저 버린 패에는 론할 수 없고, 먼저 버린 사람은 화료 전까지 다음 차례가 오지 않아 강 끝이 그대로 남으므로, 같은 패가 두 강 끝에 있으면 나중에 버린(= 화료자 다음 차례에 가까운) 쪽이 방총자다. `loserAmbiguous` 플래그에 근거를 적어 결과 화면 십자판에서 바꿀 수 있다. 동시 론의 다른 화료자 강은 후보에서 미리 빠진다.
5. 손패: `tiles` + `melds` → `Hand`. 장수가 맞지 않으면(멘젠 부분 + 울기 3장씩 + 화료패 ≠ 14) 계산하지 않고 바로 "판독 수정" 으로 간다.
6. 확신도 0.7 미만 패는 `HandEditor.uncertain` 으로 넘겨 노란 테두리.

### 결과 화면 변경

`ResultScreen` 에 `onFix` 콜백과 상단 "판독 수정" 버튼. 플래그(리치 불일치·방총자 모호·화료패 확인)가 있으면 요약 카드 아래 칩 줄로 보여주고, 칩을 누르면 해당 항목만 바꿔 다시 계산한다. "대국에 반영" 은 기존 흐름 그대로(화료자·방총자·론/쯔모가 미리 채워짐).

### 볼륨키 촬영

`Focus` + `HardwareKeyboard` 로 `LogicalKeyboardKey.audioVolumeUp/Down` 을 받으면 촬영. Android 에서 볼륨키 이벤트가 Flutter 까지 오는지는 실기기에서 확인 필요(에뮬레이터는 `adb shell input keyevent 24`). 안 오면 `MethodChannel` 로 `MainActivity.onKeyDown` 을 넘긴다. 블루투스 셀카 리모컨은 대부분 볼륨 업 키코드를 보낸다.

## 패키지

- `camera` (미리보기·촬영·해상도 `ResolutionPreset.max`)
- `image` (크롭·회전·JPEG 인코딩. 12MP 디코딩이 1~2초 걸리므로 `compute()` 로 isolate 에서)
- `path_provider` (촬영 원본 임시 저장)

## 구현 순서 (사진 없이 할 수 있는 것부터)

1. ~~서버: 스키마·프롬프트 3종, 엔드포인트, 가짜 recognizer 테스트.~~ 2026-10-23 완료(`app/schemas.py`·`prompts.py`·`normalize.py`, 테스트 13개, 실제 사진으로 3종 호출 확인 → RESULTS.md 마지막 절). 배포는 커밋·푸시 대기.
2. ~~앱 순수 Dart: `table_layout`·`cropper`·`seat_map`·`merge` + 단위 테스트~~ 2026-10-23 완료. `lib/table/` 5개 파일(`table_reading.dart` 는 서버 응답 모델), `test/table_test.dart` 21개. `image` 패키지 추가, `GameSettings.bottomSeat` 추가. 회전 방향은 테스트로 고정(글자 윗부분이 중앙을 향한다는 전제).
3. ~~`recognizer_client` 확장 + 가짜 HTTP 로 테스트.~~ 2026-10-23 완료. `recognizeBytes`·`locate`·`readTable`(바이트 입력, 크롭을 바로 보냄), `RecognizeResult.reading`(HandReading), 400·502 메시지, 타임아웃 설정 가능. `test/recognizer_client_test.dart` 7개(MockClient).
4. ~~`mount_screen` + `table_reader` + 결과 화면 연결.~~ 2026-10-23 완료. 에뮬레이터에서 확인(`screenshots/mount_*.png`): 카메라 미리보기, 갤러리 사진(게임 캡처)으로 locate → "누가 났나요?" → 손패·중앙 병렬 → 장수 불일치면 입력 화면으로 복귀 + 토스트, 직전 구역 상자 오버레이, 볼륨키 촬영 → 서버 설명이 담긴 "읽지 못했습니다" 다이얼로그. `test/table_reader_test.dart` 6개.
   - 볼륨키는 Flutter `Focus`/`onKeyEvent` 로는 안 온다(시스템 볼륨 UI 가 가로챔). `MainActivity.onKeyDown` 에서 MethodChannel(`dev.jjh.mahjong_calc/volume`)로 넘기고, 거치 화면이 떠 있는 동안만 가로챈다(`lib/services/volume_keys.dart`).
   - 진행 다이얼로그가 스스로 닫히는 구조에서는 닫힘(`await showDialog`)을 기다린 뒤 다음 화면을 띄워야 한다. 안 그러면 다이얼로그의 pop 이 방금 띄운 결과 화면을 닫는다(겪은 버그).
   - 디코딩·크롭은 `compute()` 로 isolate 에서, 원본을 두 번 디코딩한다(locate 용 축소본, 크롭). 디버그 빌드 + WebP 2000px 에서 수 초. 실기기 릴리즈 + JPEG 는 더 빠를 것.
   - 아래쪽 자리는 거치 화면 AppBar 의 사람 아이콘 메뉴에서 바꾼다(`GameSettings.bottomSeat`, 대국과 함께 저장). 대국 시작 폼에는 아직 없음.
5. ~~합성 전경~~ 대신 게임 리플레이 캡처(`experiments/vlm/samples_game/`)로 `mahjong-recognizer/scripts/pipeline.py`(locate→크롭·회전→병렬 호출, 앱 로직의 PC 판)를 돌려 확인함(2026-10-23, RESULTS.md 마지막 절). 앱의 `cropper`·`table_reader` 는 이 스크립트를 Dart 로 옮기면 된다.
6. 실제 사진 세트(거치 높이 60·70·90cm, 줌 1x·2x)가 오면 `recognize_vlm.py --mode` 로 3종 정확도 측정. 기준: 손패 전부 정답, 도라 정답, 리치 4자리 정답.

## 매장 촬영 준비 (2026-10-23 추가)

- **촬영 기록 저장**: 거치 화면 더보기 메뉴의 "촬영 기록 저장"(기본 켜짐). 촬영마다 `Download/mahjong_calc/<yyyyMMdd_HHmmss>/` 에 `original.jpg`, `locate_input.jpg`, `hand_<side>.jpg`, `center.jpg`, `locate.json`, `hand.json`, `center.json`, `meta.json`(대국 상태·화료자·단계별 ms·병합 결과·플래그·오류) 를 남긴다. 읽기에 실패해도 원본과 locate 까지는 남는다. 구현: `TableReadTrace`(table_reader) → `CaptureLog`(services) → MainActivity 의 `dev.jjh.mahjong_calc/files` 채널(MediaStore Downloads, API 29+, 권한 불필요). 매장에서 돌아오면 폴더째 PC 로 복사해 `experiments/vlm/` 에서 정확도를 잰다.
- **정답 자동 저장(label.json)**: 거치 촬영을 시작할 때 기록 폴더 이름을 정하고 "정답 대기" 로 표시한다(`CaptureLog.setPending`, 국 키 = 국 이름#본장). 그 국에서 결과 화면의 "대국에 반영" 을 마치면(`ResultScreen.onWinRecorded` → `saveCaptureLabel`) 입력 화면의 확정 손패·화료패·울기·적도라·리치·도라와 화료 시트의 화료자·방총자·론/쯔모를 같은 폴더에 `label.json` 으로 쓴다. 바로 반영하든 "판독 수정" 으로 입력 화면에서 고친 뒤 반영하든 같다(화료 형태가 아닌 결과 화면에도 "판독 수정" 버튼이 있다). 국이 다르거나 20분이 지났거나 다음 촬영이 오면 붙이지 않는다. 키는 meta.json 의 `merge` 와 같다.
- **촬영 조건(setup)**: meta.json 의 `setup` 에 `source`(local/remote/gallery), `remote_url`, `zoom`(로컬 카메라 1, 원격은 카메라 헤드가 `X-Zoom` 응답 헤더로 알림), `height_cm`(거치 화면 더보기 "거치 높이", 기기 저장).
- **집계**: `experiments/vlm/score_captures.py <폴더> --adb <serial>` 이 기록을 받아 와 높이·줌별 정확도 표를 낸다(README 참조).
- **패 최소 크기 가이드**(2026-10-27 거치·헤드 화면 모두 제거 — 고정 거치라 손으로 맞출 일이 없음. 기준값 원본 100px 는 설계 수치로만 남김): 미리보기 왼쪽 아래 연두색 상자 = 원본 100px. 첫 촬영 전에는 긴 변 4000px 로 가정하고, 첫 촬영 뒤 실제 해상도로 다시 그린다. 패 한 장이 이 상자보다 크게 보이도록 거치 높이·줌을 맞춘다.
- **릴리즈 빌드**: `flutter build apk --release --dart-define=RECOGNIZER_API_KEY=...` (56MB, 디버그 키 서명이라 디버그 빌드 위에 덮어 설치됨). 순수 Dart 디코딩·크롭이 디버그보다 훨씬 빠르다.
- 체크리스트: 높이 60·70·90cm × 줌 1x·2x 로 한 세트씩. 세트마다 눕힌 화료 손패·울기·횡치·도라 표시패가 다 보이게. 앱 촬영과 폰 기본 카메라(고해상도) 둘 다. 거치대(구즈넥/붐암) 또는 삼각대·줄자 지참.

## 리치봉 자동 반영 (2026-10-23 추가)

목표는 터치 없는 기록이다. 플레이 중에 점수판에서 "리치" 를 누르지 않아도 화료 사진으로 리치봉을 맞춘다.

- `mergeReading` 이 중앙 판독의 `riichi[side]`(확신도 `autoRiichiMinConf` 0.6 이상)를 자리 번호로 바꿔 `TableMerge.photoRiichiSeats` 에 담는다(화료자 자리 포함). `HandEditor.photoRiichiSeats` 로 옮겨져 "판독 수정" 으로 입력 화면을 거쳐도 남는다.
- 화료 시트(`showWinSheet`)는 후보 = (사진 리치 자리 − 화료자) ∪ (계산한 손패가 리치면 화료자) − 점수판에 이미 있는 리치 − 점수 1000 미만 자리. 후보를 "리치봉 자동 반영" 칩으로 **켜 둔 채** 보여 주고, 기록할 때 켜진 자리마다 `declareRiichi(fromPhoto: true)` 로 1000점을 공탁에 넣은 뒤 `win` 한다. 공탁은 화료자가 가져간다. 사건 기록에는 "X 리치 (자동)" 으로 남는다. 틀렸으면 칩을 끄면 된다.
- 화료자 리치는 병합 규칙대로 울린 손패면 버려진다(`riichiImpossible`).
- 정답: label.json 의 `riichi_seats`(기록 직전 점수판 리치 ∪ 자동 반영), `auto_riichi_seats`. meta.json 의 `merge.riichi_seats_photo` 와 비교해 집계 표 "리치 4자리" 열이 된다. 주의: 점수판을 안 누르고 자동 반영에만 맡기면 정답이 사진 판독과 같아져 이 열은 항상 맞게 나온다. 실험 때 리치 4자리를 재려면 칩을 한 번 보고 틀린 것은 끈다.
- 남은 것: 유국 때 텐파이 판정·노텐 벌점도 사진으로, 자동 촬영, 자동 반영(취소 카운트다운 + 음성).

## 카메라 헤드 (2026-10-23 추가)

카메라와 조작 화면을 다른 기기로 나눈다. 테이블 위에 고정한 기기(폰, 나중엔 라즈베리파이)는 사진만 찍고, 태블릿·노트북이 판독·대국 기록을 맡는다. 거치한 폰 화면을 들여다보지 않아도 되고, 카메라가 안 움직이니 locate 재사용의 전제가 된다.

- **규약**: 같은 Wi-Fi 안 HTTP. `GET /capture` → `image/jpeg` 원본 한 장(동시 요청은 한 번에 하나씩), `GET /status` → `{"ok","auth","captures","last_capture"}`. 카메라가 준비 안 됐으면 503 + `{"error"}`. 기본 포트 8765. 라즈베리파이로 바꿀 때는 같은 두 엔드포인트와 토큰 규칙만 Python 으로 내면 앱은 그대로다.
- **토큰 인증(2026-10-23)**: `/capture` 는 토큰이 필요하다. 헤더 `X-Head-Token: <토큰>` 또는 쿼리 `?t=<토큰>`, 비교는 상수 시간(`tokenEquals`). 없거나 틀리면 401 `{"ok":false,"error":"token"}` 이고 찍지 않는다. `/status` 는 토큰 없이(또는 틀리면) `{"ok":true,"auth":false}` 만, 맞으면 `auth:true` 와 촬영 수·마지막 시각. 조작 기기는 QR 스캔·수동 저장 직후 `/status` 로 토큰까지 확인해 "연결했습니다" 또는 실패를 띄운다. 토큰은 카메라 헤드 화면을 처음 열 때 `Random.secure` 16바이트를 base64url(22자)로 만들어 기기에 저장(`cameraHead.token`)하므로 다시 열어도 같다 → 조작 기기는 한 번만 스캔하면 된다. AppBar "새 QR"(확인 후)로 바꾸면 이전 기기는 다음 촬영에서 401 → "QR 을 다시 스캔하세요" 스낵바(바로 "QR 스캔" 버튼). 평문 HTTP 라 같은 Wi-Fi 의 도청은 막지 못한다(토큰은 "남의 폰이 내 카메라를 찍는 것" 을 막는 정도).
- **QR 연결(2026-10-23)**: 카메라 헤드 정보 패널에 QR(`qr_flutter`) — 내용 `mahjongcam://<IP>:<포트>?t=<토큰>`(첫 번째 Wi-Fi 주소). 조작 기기는 거치 촬영 더보기 "카메라 헤드 QR 스캔"(또는 "원격 카메라 주소" 대화상자의 "QR 스캔")으로 `mobile_scanner` 스캐너를 열고, `mahjongcam://` 이고 토큰이 있는 QR 이 보이면 바로 닫혀 주소(`mount.remoteUrl`)·토큰(`mount.remoteToken`)을 저장한다. 스캐너가 카메라를 쓰므로 거치 화면의 로컬 카메라는 그동안 닫는다. 수동 입력은 남아 있다: 주소 칸에 `주소?t=토큰` 을 통째로 붙여 넣거나(헤드 화면에 그 꼴로 보임), 주소·토큰 칸을 따로 적는다. 해석은 `CameraHeadLink.parse`(수동, http/https/mahjongcam, 포트 기본 8765)·`fromQr`(스캔, mahjongcam + 토큰 필수). 휴대폰 기본 카메라 앱으로 찍으면 `mahjongcam://` 링크를 열 앱이 없다(딥링크는 아직 안 함).
- **카메라 헤드 기기**: 메인 메뉴 "카메라 헤드". 미리보기와 `http://<IP>:8765` 를 보여 주고 화면을 켜 둔다. `GET /preview`(2026-10-27): 셔터 없이 이미지 스트림(YUV420) 프레임을 긴 변 960 JPEG 로 바꿔 준다(`lib/services/yuv_jpeg.dart`, isolate). 조작 기기의 테이블 화면이 3초마다 받아 배경으로 쓴다. 스트림은 첫 요청에 켜고 30초 요청이 없으면 끄며, `/capture` 중에는 멈춰 사진 해상도를 지킨다. 예전 헤드 앱은 404 → 조작 기기는 더 묻지 않는다. 대국 기록과 무관하게 아무 기기에서나 켤 수 있다. 오른쪽 위 줌 칩(1·1.5·2·3·4x, 기기의 최대 줌까지만)은 촬영 사진에도 적용된다(90cm 높이면 2x 쯤, 패 앞면 폭이 원본 100px 이상이면 됨). 가로로 들면 미리보기가 더 커진다.
- **조작 기기**: 거치 촬영 더보기 → "원격 카메라 주소" 에 그 주소를 적는다(기기에 저장, 비우면 이 기기 카메라로 복귀). 이때 로컬 카메라는 열지 않고, "촬영" 이 카메라 헤드에서 사진을 받아 와 미리보기 자리에 띄운 뒤 평소처럼 locate → 크롭 → 읽기 → 병합으로 간다. 촬영 기록 저장은 조작 기기에 남는다(에뮬레이터면 에뮬레이터 안 Download).
- **노트북을 화면으로 쓰는 실험**: Windows 데스크톱 빌드는 Visual Studio C++ 구성요소가 없어 안 되고(`flutter doctor`), 웹은 `dart:io`·CORS 때문에 손이 더 간다. 대신 안드로이드 에뮬레이터(`pixel_api36`)에 같은 APK 를 깔아 조작 기기로 쓴다. 에뮬레이터는 LAN 으로 나가는 연결이 되므로 폰 IP 에 붙는다.
- **Android 설정**: 릴리즈 매니페스트에 `INTERNET` 권한이 없었다(디버그만 Flutter 가 넣어 줌). 추가했고, LAN 의 평문 HTTP 를 위해 `usesCleartextTraffic="true"`.
- 다음: 마작방 Wi-Fi 의 기기 간 통신 차단(AP isolation) 대비 — 핫스팟 안내 또는 서버 중계, 카메라 헤드가 원본을 자기 Download 에도 남기기(선택), `mahjongcam://` 딥링크(기본 카메라 앱으로 스캔해도 앱이 열려 저장), 라즈베리파이 헤드(picamera2 + 같은 두 엔드포인트 + 토큰).

## 알려진 위험

- 중앙 크롭 하나로 강 4개를 읽기엔 패가 작을 수 있다 → 강별 4호출 대안.
- locate 가 손패 상자를 울기까지 포함해 잡지 못할 수 있다 → 상자를 좌우로 15% 넓혀 자른다.
- 서버 1568px 축소는 크롭에는 영향 없지만, 손패 크롭이 1568px 를 넘으면 줄어든다. 14장 손패 크롭은 보통 1500px 이하라 괜찮다.
- 볼륨키가 Flutter 에 안 올 수 있다(위 참조).
- 론/쯔모 추정은 사진 조건(화료패를 떨어뜨려 놓는지, 마지막 버림패가 보이는지)에 크게 의존한다. 틀려도 결과 화면 칩으로 고칠 수 있어야 한다.
