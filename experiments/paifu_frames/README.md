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

## 프레임 오독 원인 나누기 (2026-11-11)

`frame_split.py frames|scale|proxy` — 1020 프레임 오독을 검출 몫 / 분류 몫 / 줄이는 방식으로 나눈다. 결과: `docs/metrics.md` 표 12-1, `docs/problem_log.md` 56번(헤드가 4픽셀마다 한 픽셀만 뽑아 줄이는 것이 원인).
- `frames`: 저장된 `det.json` 을 정답과 프레임 단위로 대조(추론 없음).
- `scale`: 화료 사진을 여러 크기·방식(LANCZOS / 헤드식 건너뛰기 / 4×4 평균)으로 줄여 같은 판독.
- `proxy`: 평가 장면 34장 강 패로 넓힘(4080 확신 ≥0.9 답 기준).

## 프레임으로 이어 학습한 분류기 clsF (2026-11-11)

`frame_train.py harvest|sheets|merge|train A|B|extra` — 화료 사진 판독을 라벨로 프레임 크롭을 모으고(15판 616칸), 검토 결과(`clean_P*.json`)를 합쳐 운영 분류기에서 이어 학습한다. 채점은 `FS_CLS=<onnx> FS_TAG=_<이름> python frame_split.py frames|scale`. 결과: `docs/metrics.md` 표 12-2(기준)·12-3(결과).
- 자료·모델은 `experiments/tile_classifier/data/frames{,_eval}/`, `server_bench/models/clsF_{A,B}.onnx`(커밋 안 함).
- `frame_eval_extra.py`: 확장 평가 세트(11-07 오후 두 판) 수집 — 에이전트가 `frame_train.py` 를 복사해 만든 것.
- `truth.json` R3a 왼쪽 셋째 버림을 4p → 6p 로 고침(화료 사진 확인).
