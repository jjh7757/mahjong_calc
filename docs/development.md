# mahjong_calc 개발 안내

앱을 빌드·시험하는 데 필요한 환경과 명령, 코드 구조, 화면 기능 정리다. 2026-11-09 까지 README.md 에 있던 내용을 옮겼다(README 는 프로젝트 소개·개발 과정 문서가 됨).

## 개발 환경 (PATH 미설정, 전체 경로로 호출)

- Flutter: `C:\Users\jjh7757\flutter\bin\flutter`
- JDK 17: `C:\Users\jjh7757\dev\jdk17`
- Android SDK: `C:\Users\jjh7757\dev\android-sdk` (API 36, build-tools 36.0.0, NDK 28.2, 에뮬레이터)
- AVD: `pixel_api36` (Pixel 7, Android 16 x86_64)

## 자주 쓰는 명령

```
C:\Users\jjh7757\flutter\bin\flutter test
C:\Users\jjh7757\flutter\bin\flutter analyze
C:\Users\jjh7757\dev\android-sdk\emulator\emulator.exe -avd pixel_api36
C:\Users\jjh7757\flutter\bin\flutter run -d emulator-5554
C:\Users\jjh7757\flutter\bin\flutter build apk --debug
C:\Users\jjh7757\dev\android-sdk\platform-tools\adb.exe install -r build\app\outputs\flutter-apk\app-debug.apk
```

## 구조

층·의존 방향·데이터 흐름 전체는 `ARCHITECTURE.md` 에 있다.

- `lib/engine/` 계산 엔진 (패, 묶음, 분해, 역, 부수, 점수)
- `lib/ui/` 입력·결과·설정 화면
- `test/engine_test.dart` 역·점수 테스트, `test/widget_test.dart` 화면 흐름 테스트

## 사진 인식 (2단계)

`lib/services/recognizer_client.dart` 가 인식 서버(https://mahjong.ai-agent-develop.cloud, 저장소
[mahjong-recognizer](https://github.com/jjh7757/mahjong-recognizer))에 사진을 보내고, 입력 화면의 "사진" 버튼이 결과로 손패를 채운다.
서버 키는 빌드 시 넣는다 (`.recognizer_key` 는 커밋하지 않는다):

```
C:\Users\jjh7757\flutter\bin\flutter build apk --debug --dart-define=RECOGNIZER_API_KEY=%키%
```

키 없이 빌드하면 버튼은 보이지만 "인식 서버 키가 설정되지 않은 빌드" 안내만 뜬다.

## 대기패 판정·대국 기록

- 손패가 13장이면 아래 버튼이 "대기패 보기"로 바뀐다. 각 대기패마다 론/쯔모 점수와 역을 보여준다(`lib/engine/waits.dart`).
- 앱바의 점수판 아이콘이 대국 기록이다(`lib/game/`, `lib/ui/game/`). 리치·화료·유국을 누르면 점수가 움직이고
  본장·공탁·친 교체가 자동이다. 정산은 우마·오카·오사육입을 반영하고, 끝난 대국은 기기에 저장된다.
- 결과 화면의 "대국에 반영" 버튼으로 계산기 결과를 현재 국에 바로 기록할 수 있다.
- 대국이 진행 중이면 입력 화면 "상황" 칸 위에 "누구 손패?" 선택이 뜬다. 자리를 고르면 자풍·장풍·본장·리치(그 국에
  리치한 자리면)가 점수판 값으로 채워지고(`HandEditor.syncFromGame`/`setGameSeat`), "대국에 반영"에서 화료자가 미리
  골라진다. 기록이 끝나면 손패가 비워진다. 국이 바뀌면 장풍·본장이 다시 채워지지만, 같은 국 안에서 손으로 고친 값은 유지된다.
- 대국 시작 폼의 "중간부터 기록 시작" 스위치를 켜면 장풍·국·본장·공탁·현재 점수를 넣고 그 시점부터 기록한다
  (`Game.resumed`, `GameStore.resume`). 친은 국 번호로 정해진다(자리 순서가 기동 동→남→서→북이므로). 점수 합이
  시작점×4 − 공탁과 다르면 경고만 하고 막지는 않는다.

## 점수표·연습 퀴즈

앱바 더보기 메뉴(⋮)에 있다.

- 점수표(`lib/ui/score_table_screen.dart`): 판×부 표, 자/친·론/쯔모 전환, 만관 이상 고정값. 룰 설정(끌어올림 만관)을 따른다.
- 점수 계산 연습(`lib/quiz/quiz_generator.dart`, `lib/ui/quiz_screen.dart`): 무작위 화료 손패(역 있음, 역만 제외, 30%는 울음)를 보고
  판 → 부 → 점수 순으로 맞힌다. 5판 이상이면 부수는 묻지 않는다. 해설에 역·부수 내역이 나오고 정답 수는 기기에 저장된다.
