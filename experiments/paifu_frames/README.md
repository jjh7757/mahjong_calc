# 판 중 패보 시험 (2026-11-09)

추적 기록 프레임(`*_track/frames_##.zip`, 1020×764, 약 3초 간격)으로 한 판의 **버림 순서 + 패 + 울어 간 패**를 만든다.
손패·쯔모는 안 보이므로 불완전 패보다. 결과·해석: `docs/metrics.md` 표 12, `docs/problem_log.md` 50번.

- `paifu_frames.py <track 폴더> results --name R2 [--t0 --t1] [--dealer-side top --flip --tag _v2]`
  - 1단계 검출: 처음 실행 때 `results/<name>/det.json` 을 만든다(서버 저장소 `mahjong-recognizer` 의 `app/local_read.py` 를 import).
  - 2단계: `slot_<tag>.json`(자리별 칸)과 `paifu_slot<tag>.txt`(한 판 순서)를 낸다.
- `score.py results/<name>/slot_v2.json truth.json <name>`: 강 패·울어 감·한 판 순서를 채점한다.
- `run_all.sh`: R2·R3a·R4 를 v1·v2 로 돌려 채점한다.
- `truth.json`: 사람이 만든 정답이다. 판마다 `seq`(차례대로, `*` = 강에서 빠짐)와 `taken` 을 둔다.
- 도움 스크립트:
  - `dump_side.py`: 프레임별 한 자리 읽기를 본다.
  - `live_counts.py`: 앱 실시간 추적이 같은 판에 남긴 버림 수를 센다.
  - `debug_det.py`: 검출 수를 진단한다.

판: R2 = 11-07 15:30:46~15:33:07(화료 153311), R3a = 15:33:37~15:36:37(153638), R4 = 15:39:58~15:44:15(154417).
R4 는 v1 을 고정한 뒤 처음 채점한 시험 판이다. v2 는 R4 실패를 보고 만들었으므로, 세 판 모두 개발 판이다.
