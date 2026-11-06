# 탁자 8점 찾기 (2026-11-02 시작, 학습 전)

사진에서 펠트 네 모서리와 리치봉 기기 네 모서리를 찾고, 손패·산·울기·리치봉·강 구역은 이 점들로 계산한다. 구역을 모델에 직접 가르치지 않는다.

## 점 정의

- 사진 기준 왼위부터 시계 방향으로 번호를 매긴다. `felt` 0~3, `device` 0~3.
- 펠트 모서리 = 초록 면의 모서리. 패가 덮고 있으면 보이는 변을 이어 만나는 점.
- 기기 모서리 = 남색 기기 사각형의 모서리. 패가 덮고 있으면 같은 방식.
- 좌표는 원본 비율(0~1). 사진 밖이면 0 이나 1 을 넘는다. `vis` 0 = 학습에 안 씀, 2 = 씀. `vis` 순서는 펠트 4개 다음 기기 4개.

## 재료와 나눔

| 묶음 | 재료 | 비고 |
| --- | --- | --- |
| am | 10-31 매장 구간 0·1·3·4·5·8·10 | 시각이 아니라 구간으로 나눔 |
| pm | 10-31 매장 구간 11·13·14 | 구간 11 은 13:49 에 시작 |
| gal | 갤러리 k00·k04·k12·k15·k16·k20·k24·k25·k26·k28 | 구간 없이 사진별 값 |

**쓰지 않는 것:** 10-24 삼각대 15장(테스트 세트), 10-29·10-30 기록(갤러리를 다시 읽은 것·천장 사진), 구간에 들지 못한 프레임.

학습 나눔: 카메라 설치 8개와 갤러리를 하나씩 뺀다(9 fold, 검증은 다른 설치 하나, `kernel/train_pose.py`). B·C·D 숫자는 갤러리 fold 모델로만 낸다.

## 결과 (2026-11-02, `docs/metrics.md` 표 1-39)

YOLO26n-pose 는 기기 점 중앙 0.56% 로 쓸 만하지만 펠트 점 중앙 2.55%(패 폭 약 2.2%), 8점이 전부 1% 안인 사진 0/358 이라 채택하지 않는다. 학습한 설치에서도 펠트 점이 안쪽으로 쏠린다.

색 판독 펠트 네 점으로 격자를 계산하면(`zones.py`, 표 1-40) 사람이 맞춘 저장 격자와 같은 30/34, 자동 13(점수 틀림 0)이고 사진 한 장만으로도 같다. 기본 격자는 28/34, 점수 틀린 자동 3. 앱 코드는 `lib/table/felt_grid.dart`(커밋 전, 표 1-41)이고 실제 다른 색 펠트 사진은 없다. 과적합 점검(표 1-42)에서 안 본 삼각대 사진 통과 10 중 3 이 틀려, 펠트 색을 사진에서 재고 변 바깥·기기 바깥 띠를 검사하도록 고쳤다(표 1-44, `felt_gate.py`). 삼각대 사진을 본 뒤 고쳤으니 평가는 다음 매장 사진으로 한다.

구역별 상한·하한은 `zone_bounds.py`, 사진 좌표 고정 격자는 `fixed_grid.py`(표 1-43). 고정 격자는 앱 흐름 28/34·틀린 자동 2, 처음 보는 카메라에서 20/34 라 쓰지 않는다.

## 만드는 순서

```
python -I experiments/zone_points/propose.py     # 색으로 초안, data/zone_points/proposals.json
python -I experiments/zone_points/segments.py    # 카메라 설치 구간과 구간별 중앙값, segments.json
python -I experiments/zone_points/labels.py      # 뺄 구간·기기 값·안 보이는 점 반영, 프레임 뽑기, labels.json
python -I experiments/zone_points/build_ds.py    # YOLO pose 데이터셋 ds/
python -I experiments/zone_points/score.py       # kaggle_out/ 를 받은 뒤 설치별 점 오차
```

결과는 `experiments/tile_classifier/data/zone_points/`(커밋 안 함). 사람이 고친 값은 `labels.py` 맨 위 표(`DROP_SEGS`·`SAME_AS`·`DEVICE_FIX`·`EXTRA_PHOTOS`·`HIDDEN`)와 `moved()`, `build_ds.py` `NEG_SKIP` 이다. 근거는 `label_review.md`. 살린 프레임 목록은 `review_lists.json`.

## 눈으로 보는 도구

```
python -I experiments/zone_points/overlay.py <json> <출력 앞이름> [--names a,b] [--kind photo|frame] [--cols 6] [--tw 400]
python -I experiments/zone_points/corner_review.py <json> <출력 앞이름> [--half 0.04] [--per 8]
```

`labels.json` 을 그대로 넣을 수 있다. `overlay.py` 는 전체 그림, `corner_review.py` 는 점 하나씩 확대한 그림이다.

## 패 단위 구역표와 기준점 로더 (8b-2, 2026-11-06, `docs/metrics.md` 표 1-103)

8b "탁자 독립 격자" 의 구역은 사진 좌표 선 4개가 아니라 **기준점**(가운데 기기 가운데·방향 θ·패 한 장 짧은 변 u·기기 반폭 D)과 **패 단위 구역표**로 만든다. 기준점 찾기는 8b-1 `wall_frame.py`(화료 = 기기, 배패 = 패산이 올라온 첫 프레임, 표 1-101).

- 구역표 `assets/table_frame/zones.json` — `rules`(규칙 몫, 탁자 무관: 바람개비 자리·가운데 R = D + 6u, 손패 띠 ±8u·깊이 6u, 울기 모서리, 강, 리치봉 상자·띠, 왕패 칸 8~13u, 표시패 탐색 칸, 거치 이동 1u·3°)과 `profiles.amos`(기종 값: 패산/기기 3.85, 뒷면 → u 0.87). 기종이 바뀌면 프로필만 더한다. 값은 8b-1 상수 그대로.
- 로더 두 벌이 같은 파일을 읽는다: 앱 `lib/table/table_frame.dart`, 서버용 `table_frame.py`(표준 라이브러리만 — 서버 `app/` 로 옮길 것). `TableFrame`(JSON 왕복·`scaled_to`·`from_wall`·`moved_from`) → `TableZones(table, frame, W, H)` → `seat/hand/corner/river/stick_strip/dead_wall(side)`·`center/device/sticks/dora_search(except)` = `RotRect`(네 점·`angle_deg`·`bbox`·`norm`), `zone_of(x, y)`(바람개비 칸), `inside(name, side, x, y)`.
- 같은 답 확인: 예제 `test/fixtures/table_frame.json`(실제 기준점 10 + 손 경계 사례 9, 상자 532). 구역표나 로더를 고치면 `--make-fixture` 로 기대 출력을 다시 만들고 둘 다 돌린다.

```
python -I -X utf8 experiments/zone_points/table_frame.py --test          # Python
flutter test test/table_frame_test.dart                                   # Dart(같은 예제)
python -I -X utf8 experiments/zone_points/table_frame.py --make-fixture  # 기대 출력 다시 만들기(wall_frame.json 필요)
python -I -X utf8 experiments/zone_points/table_frame_score.py           # 8b-1 채점을 새 로더로(wall_frame.py·결과·라벨 필요)
```

재채점 결과(표 1-103): 점마다 판정이 8b-1 과 같고(차이 0) 틀린 수 개발 10·테스트 7·색 바꾼 7 그대로, 표시패 제 칸(가운데 ∪ 왕패 칸) 26/26. 왕패 칸은 손패와 겹쳐(개발 손패 57%) 표시패/손패 구분은 역할 모델 몫이다. `wall_frame.py` 가 이 폴더에 없으면 `WALL_FRAME_DIR`(기본 본 체크아웃)에서 읽기만 한다.
