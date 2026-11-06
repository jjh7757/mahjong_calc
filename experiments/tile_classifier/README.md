# 패 분류기 자체 학습 1단계 (2026-11-01, 노트북 CPU, API 없음)

운영 YOLO11 상자에 직접 학습한 분류기를 붙이면 패 종류를 읽을 수 있는지 보는 기준값. 표는 `docs/metrics.md` 표 1-18.

```
python -I experiments/tile_classifier/build_crops.py   # 크롭·라벨·확인 그림(data/, 커밋 안 함)
python -I experiments/tile_classifier/train.py         # 교차 검증, 약 20분. --base 면 비교값만
```

## 데이터

상자 = 서버 `app.seat.frame`(운영 코드 그대로), 안 되면 검사를 뺀 같은 규칙. 장수가 정답과 맞을 때만 왼쪽부터 라벨을 붙인다. 사진 23/31, 패 259/410, 4z·5z 는 0장.

눈 확인(`data/sheet_*.jpg`)에서 고친 것: 133826 은 정답 끝 화료패가 놓인 자리와 달라 순서가 밀림, 174020 손에 가린 6s·171505 눕힌 3m 은 뺌. HaseLab 분류기가 259장 중 258장을 같은 값으로 읽어 라벨이 맞다는 것을 따로 뒷받침한다(학습에는 안 씀).

## 결과

- 학습에 있는 종류만 보면 장면 분리 241/242(99.6%). 틀린 18장 중 17장은 그 종류가 학습에 없던 패다.
- 세트 분리는 학습에 있는 종류만 642/699(91.8%), 전체 642/777(82.6%). 시드마다 ±5% 넘게 흔들려(오전 94.5~100%) 데이터가 부족하다.
- 운영 틀 통과는 14/31 이고 매장은 8/25 다. 분류기보다 틀 잡기가 먼저 막힌다.

## 한계

- 잘 잡힌 패만 들어갔다. 틀을 못 잡은 8장은 평가에 없다.
- 장면 분리는 같은 날 같은 패 세트가 학습에 있어 낙관적이다. 242장에 1장 틀림이면 95% 구간 위쪽 오류율이 약 2.3% 라 목표(99.5%)를 넘었다고 말할 수 없다.
- 안 잰 것: 강 끝·표시패, 뒤집힌 방향 대응, 다른 매장 패, t4g.small 추론 시간, 점수까지의 흐름.

## 학습 재료 조사 (`frame_res_check.py`·`frame_real_check.py`, metrics 표 1-19)

노트북에 있는 10-31 기록 기준. 태블릿은 USB 장치로 잡히지 않아 못 봤다.

| 재료 | 양 | 패 크기 | 라벨 | 판단 |
| --- | --- | --- | --- | --- |
| 원본 사진의 앞면 패(강·울기·손패) | 사진 62장, 패 약 3,800장(11장 표본 어림, 저해상도 사진·헛검출 포함) | 약 88px | 없음 | 1순위 |
| 모서리 판독 | 울기 있는 판독 59건, 패 212장(같은 울기 반복) | 고해상 | Gemini 답, 확인 안 함 | 드문 종류 보충. 약관 확인 뒤 |
| 추적 프레임 | 2,259장, 장당 앞면 패 약 24장(1장 표본), 같은 패 반복 | 약 21px | 없음 | 저해상 대응·검출기·평가용 |

- 처음에 21px 은 패 종류 학습에 부적합하다고 적었는데 틀렸다. 합성 축소에서 255/259 가 나왔다. 다만 실제 프레임은 화료 패가 몇 초만 보이고 손·움직임이 있어 훨씬 낮다.
- 프레임의 손패는 공개 직후 몇 초뿐이라 화료패 라벨을 옮겨 얻는 양은 적다(잘 맞은 프레임 21장).

## 2차: 원본 사진에서 패 모으기 (`harvest.py`·`harvest_blank.py`·`review.py`, metrics 표 1-20)

```
python -I experiments/tile_classifier/harvest.py        # 임시 라벨, 종류별 그림
python -I experiments/tile_classifier/harvest_blank.py  # 白 후보(무늬 거르기에 빠짐)
python -I experiments/tile_classifier/review.py         # --count 수량, --leak 겹침 확인, --hard 검토 라벨 평가, --bcd 겹침 뺀 B·C·D
```

라벨 1,550장, 37종 전부. 세트 분리 777/777(겹침 뺀 B·C·D 포함), 표 1-18 의 642/777 에서 올랐다.

- **겹침을 찾았다:** 10-29 22:03·23:08 과 10-31 00:02 기록은 갤러리 k16·k28 을 앱으로 다시 읽은 것이다. 처음 B·C·D 100% 는 무효이고, 빼고 다시 재도 216/216 이었다. 10-30 23:58 은 k25 와 차이 18.1 로 같은 사진은 아니지만 같이 뺐다.
- 검토 라벨 전부로 평가하면 1,071/1,072(라벨 2건 고친 뒤). 라벨을 모델이 먼저 붙였으므로 독립 정답이 아니다.
- 드문 종류 채우기가 가장 큰 효과였다. 틀린 패 대부분이 학습에 없거나 적은 종류였다.
- 라벨 검토는 Claude 가 했고 사용자 확인 전이다. `model_round2.pt` 는 2114·2591 고치기 전 라벨로 학습했다.

## 3차: YOLO26n "앞면 패" 1종 검출기 (`det_boxes.py`·`det_build.py`·`det_kernel/`, 캐글 GPU T4, 진행 중)

사진 35장(10-31 매장 25, 카톡 10), 상자 2,088개. 라벨은 YOLO11 + 자체 분류기로 만든 임시 값이라 빠진 패가 있고(모서리 울기·일부 손패), 눈으로 고치지 않은 1회차다. 데이터셋은 토막 포함 350장, 다시 저장해 EXIF 없음. 비공개 데이터셋 `jjh7757/mahjong-tile-faces`, 비공개 노트북 `jjh7757/mahjong-tile-det`(2026-11-01 제출). 나눔 fold_a(시험 오후·B·C·D), fold_b(시험 오전·B·C·D), final(전부).

```
python -m kaggle kernels status jjh7757/mahjong-tile-det
python -m kaggle kernels output jjh7757/mahjong-tile-det -p experiments/tile_classifier/data/det/kaggle_out
```

결과가 오면: 검출값을 사진에 겹쳐 라벨에서 빠진 패를 찾아 고치고 다시 학습, 시험 나눔 모델로 `st.frame` 틀 통과를 표 1-18 의 14/31 과 비교한다.

**1회차 결과(`det_eval.py`, 2026-11-02, metrics 표 1-21):** 틀 통과 14/31 로 YOLO11 과 수가 같다. 단독 답 맞음 16/37(틀린 자동 3), 검사 실패를 Gemini 로 넘기면 26/37(Gemini 단독 25/37, 쓴 회 37 → 18), 시간 중앙 0.9초. 처음 값 12/37·쓴 회 22 와 패 종류 179/182 는 세운 손패를 뒤집어 읽던 평가 코드 버그가 있던 값이다. 모양 검사를 빼는 완화는 틀린 자동이 5건으로 늘어 안 쓴다. 검출기는 장수를 대부분 맞게 찾으므로 다음 병목은 묶기·떼어 둔 패·모서리 울기 규칙이다.

**2회차:** 1회차 검출값을 라벨로 바꾸고 눈으로 고쳐(`det_relabel.py`·`det_review.py`, 상자 2,241개) 제출했다. 결과는 `kaggle_out_r2` 로 받아 `det_eval.py --strict --r2` 로 잰다. **결과(metrics 표 1-26):** 틀 규칙(`frame_rules.py --r2`, 표 1-23)을 더해 단독 28/37, 틀린 자동 0, Gemini 먼저 29/37·쓴 회 9. 규칙·라벨을 같은 사진으로 정한 값이다. 164501·171245 모서리 白 퐁은 `fold_a` 학습에 든 白 이 그대로라 여전히 못 찾는다.

**白 을 코드로 채우기(`server_bench/blank_fill.py`, metrics 표 1-33, 앱·서버 미반영):** 학습 없이 손패 줄 빈칸과 모서리 펠트 경계로 白 을 찾는다. 가림 제외 28/35 → 31/35(채운 3장은 자동 반영 안 함), 틀린 답 0, 상자를 일부러 지운 헛발동 0/284. 실패 사진을 보고 만든 규칙이라 다음 매장 사진으로 고정해 잰다.

## 패산 위 표시패 찾기 (`wall_frames.py`·`wall_frames_read.py`, metrics 표 1-34)

추적 프레임 30장에서 앞면 패 상자의 앞뒤에 뒷면 색이 붙어 있는 정도로 표시패 한 장을 고른다. 추가 학습 없이 29/30(Gemini `/v2/wall` 도 29/30), 놓친 1장은 白. 프레임 크기로 읽기는 패를 키워도 6/8 이라 아직 부족하다.

화료 원본(`wall_photos.py`, metrics 표 1-35)에서는 리치 아닌 화료 9/9. 운영 왕패 경로(`wall_photos_gemini.py`)도 9/9 라 정확도는 같고 시간만 다르다. 리치 화료는 2장 묶음 규칙으로 5/10(틀림 1, 답 없음 4)이라 아직 부족하다.

## 다음

1. 틀 잡기: 매장 운영 틀 통과 8/25 가 다음 병목이다. 위 3차 결과로 판단한다.
2. 분류기를 틀과 이어 점수까지 잰다(표 1-17 방식, 지금 값은 낱장뿐).
3. 다음 매장 사진으로 처음 보는 날짜·패 상태를 평가한다. 34종 + 적5 를 순서대로 놓고 네 방향으로 찍으면 드문 종류도 보강된다.

## 판 중 도라 표시패 확정 (`dora_rounds.py`·`dora_resolution.py`, metrics 표 1-53, 2026-11-03)

화료 사진 한 장이 아니라 판 중 추적 프레임 여러 장의 투표로 표시패를 미리 정한다(앱 `lib/table/dora_tracker.dart`, 규칙은 두 곳이 같아야 한다).

```
python -I -X utf8 experiments/tile_classifier/dora_rounds.py        # 10-31 프레임 2,094장을 시각순으로 넣고 화료 기록 시각마다 확정값을 truth.json 과 대조, data/dora_rounds/online.json
python -I -X utf8 experiments/tile_classifier/dora_resolution.py    # 리치 아닌 화료 원본을 4080·2040·1360·1020 으로 줄여 read_wall 로 읽기(미리보기 크기 정하기)
python -I -X utf8 experiments/speed/flow_visit.py dora              # online.json → TRACKED_DORA(측정 테스트가 판 중 확정값으로 씀)
```

- 규칙: 서버 read_wall 의 1순위 상자(확신도 0.7 이상만 관측), 위치 묶음(패 1.5장), 지금 묶음 = 최근 20 관측에서 가장 많이 본 묶음, 확정 = 최근 5 관측 중 3 이상 같은 종류·확신도 합 60% 이상, 기록 때 비움(전판과 같은 자리·같은 패는 안 받음).
- 1020 프레임(패 약 25px)으로는 정답 19장 중 11 맞음·2 틀림·6 없음. 해상도를 보면 1020 은 4/8, 2040 은 6/8, 4080 은 8/8(틀림 0) 이라 앱은 리치봉 읽기와 같은 고해상 프레임(`_trackSource`)을 쓴다.
- `dora_outside.py`(metrics 표 1-54): 격자 구역(자리 띠·강·리치봉 상자) 밖의 앞면 패를 전부 표시패로 보면 어떤지. `SEAT_GROW=40|0|-40`, `TURNED=1`(돌려 읽기). 리치 9장 중 정확 3·포함 4·밖 없음 4(짝을 자리 띠 안에 둠), 리치 아님은 0(패산 표시패가 띠 안).

## 앞면 패 역할 분류기 가능성 확인 (`role_label.py`·`role_train.py`, metrics 표 1-56, 2026-11-03)

규칙으로 역할 라벨(손패 줄·울기·강·패산 위 표시패·탁자 위 짝·떼어 둔 패)을 자동 생성하고, 패 주변 패치(패 폭 8배, 160px)를 MobileNetV3 Small 로 분류해 사진 단위 3겹 교차 검증. 흔한 역할 95% 이상, 짝 5/16·떼어 둔 패 0/11 — 표본이 없어 규칙을 못 이긴다. 라벨이 쌓이면 다시.

```
python -I -X utf8 experiments/tile_classifier/role_label.py   # data/role/labels.json, check/<이름>.jpg(역할별 색), review.json 으로 고침
python -I -X utf8 experiments/tile_classifier/role_train.py   # data/role/cv.json
```

## 패 상자 배치만으로 역할 — 집합 Transformer (`role_set.py`, metrics 표 1-57, 2026-11-03)

그림 없이 상자 집합(앞면 + 뒷면 `data/det/backs/boxes.json`)만 넣어 상자마다 역할을 내는 Transformer 인코더. 좌표는 펠트 격자 기준 0~1 로 바꾸고 화료자 자리가 아래로 오게 돌린다. 학습 전에 라벨 독립 검토(확인 그림 25장, 확실한 오류 100개 → `data/role/review.json`, `labels.json` 의 `rule` 칸이 수정 전 규칙 값)를 받았다. 3겹 교차 검증 결과 전체 1,138/1,204 로 규칙 1,144 와 같은 수준, 손패 줄은 모델이 낫고 드문 역할(울기·패산 표시패·짝·떼어 둔 패)은 규칙이 낫다. 합성 레이아웃으로 드문 역할을 채우기 전에는 채택하지 않는다.

```
python -I -X utf8 experiments/tile_classifier/role_label.py                 # review.json 반영해 labels.json 다시
python -I -X utf8 experiments/tile_classifier/role_set.py [--epochs 300] [--seeds 3] [--no-backs]   # data/role/set_cv.json, set_wrong/<이름>.jpg
```

## 합성 배치로 사전학습 (`role_synth.py`, metrics 표 1-58, 2026-11-03)

`role_synth.py` 가 마작 규칙으로 탁자 배치(펠트 기준 좌표, 화료자 아래)를 만들고 검출 잡음을 섞는다. `role_set.py --synth N` 은 씨드마다 합성 N장으로 먼저 학습한 뒤 실제 겹으로 미세 조정하고, `--pre-file` 로 가중치를 저장·재사용, `--no-ft` 로 합성만 채점한다. 합성 8,000장 결과: 합성만 1,158/1,204, 미세 조정 1,172(규칙 1,144, 실제만 1,138). 울기·짝·패산 표시패가 올라가고 떼어 둔 패는 아직 못 배운다. 떼어 둔 패·표시패 비율을 올린 보강(`pre_synth8k_v2.pt`)은 1,170 으로 차이가 없어 채택 안 함.

```
python -I -X utf8 experiments/tile_classifier/role_synth.py --n 12          # data/role/synth_check/<k>.png 눈 확인
python -I -X utf8 experiments/tile_classifier/role_set.py --synth 8000 --synth-epochs 3 --epochs 100 --seeds 3 --pre-file pre_synth8k.pt --tag _synth_ft
python -I -X utf8 experiments/tile_classifier/role_set.py --synth 8000 --seeds 3 --pre-file pre_synth8k.pt --no-ft --tag _synth_only
```

## 테스트 세트 비교 (`role_field.py`, metrics 표 1-59, 2026-11-04)

10-24 삼각대 15장(기울고 원근 있음)으로 역할 모델 대 규칙을 한 번 쟀다. `build` 가 검출기·펠트 모서리·뒷면·규칙 라벨을 만들고(`data/role/field/`), 독립 검토를 `review.json` 으로 반영(`review`), `score` 가 `pre_synth8k.pt` 를 개발 25장 전부로 미세 조정해 채점한다(좌표는 펠트 네 모서리 호모그래피). 결과 모델 703/706(99.6%), 규칙 645/706(91.4%). 규칙은 대삼원 장면의 손패 줄 전부와 다른 자리 퐁에서 틀린다.

```
python -I -X utf8 experiments/tile_classifier/role_field.py build    # boxes.json, labels.json, check/
python -I -X utf8 experiments/tile_classifier/role_field.py review   # review.json 반영
python -I -X utf8 experiments/tile_classifier/role_field.py score    # score.json, pred/
```

## 자리 판독 벤치에 역할 모델 끼우기 (`server_bench/role_bench.py`, metrics 표 1-60, 2026-11-04)

서버 조건(자리 크롭만, 뒷면 없음)으로 다시 학습한 모델(`role_set.py --no-backs --crop`, `pre_synth8k_nbc2.pt` → `role_nbc_all.pt`)을 자리 판독 단독 벤치에 끼워 규칙과 같은 크롭·검출기·분류기로 쟀다. 모델 틀 20/37, 모델이 고른 상자만 서버 `split_frame` 에 넣는 혼합 28/37 = 규칙 28/37. 남은 실패는 검출(白·가림) 문제라 둘이 같다. 크롭에서는 모델의 이점(탁자 전체 맥락)이 사라지므로, 서버에 붙이려면 사진 전체 + 펠트 모서리를 받는 새 경로가 필요하다.

```
python -I -X utf8 experiments/tile_classifier/role_set.py --synth 8000 --synth-epochs 3 --epochs 100 --seeds 3 --no-backs --crop --pre-file pre_synth8k_nbc2.pt --tag _synth_ft_nbc2
python -I -X utf8 experiments/tile_classifier/server_bench/role_bench.py [--hybrid]    # data/role/bench/role_bench[_hybrid].json, <이름>.jpg
```

## 서버 새 경로 /v2/localroles (`role_export.py`·`run_roles_flow.sh`·`server_bench/role_full_bench.py`, metrics 표 1-61, 2026-11-04)

역할 모델을 서버에 붙인 경로. `role_export.py` 가 `role_nb_all.pt`(뒷면 없음, 실제 25장 전부 미세 조정) 3씨드를 ONNX 하나로(어텐션을 수동 계산으로 내보내 길이 N 가변), 서버 `app/roles.py` 가 사진 전체 + 격자 + 자리를 받아 역할 → hybrid 틀 → 분류·白 채우기. 앱은 `readGrid(useRoles:)`(측정 `ROLES=true`). 앱 흐름 29/34(규칙 30/34)에 틀린 자동 반영 1건이라 기본은 끔.

```
python -I -X utf8 experiments/tile_classifier/role_export.py data/role/role_nb_all.pt C:/Users/jjh7757/dev/mahjong-recognizer/app/assets/tile-roles.onnx
python -I -X utf8 experiments/tile_classifier/server_bench/role_full_bench.py      # 오프라인: 규칙 대 hybrid·model, data/role/bench/full_bench.json
bash experiments/tile_classifier/run_roles_flow.sh plain roles                      # 앱 흐름(로컬 서버 셋 + 사진 서버 둘 먼저)
```

## 검출기 3회차 — 白 붙여넣기 증강 (`det_blank_cands.py`·`det_build.py --blank-swap`·`det_blank_recall.py`, metrics 표 1-62, 2026-11-04)

라벨 白(무늬 없음) 크롭으로 학습 토막 상자 20% 를 덮은 사본(`__b`, 학습 전용)을 더해 캐글에서 다시 학습(`kaggle_out_r3`). 白 재현 68 → 71/80(183022 모서리 白 퐁 0 → 3/3)이지만 164501·171245 는 그대로 0/3, 서랍 속 종이를 패로 잡는 헛검출이 생겨 자리 판독은 1장 줄어 채택 안 함. `det_blank_cands.py` 는 YOLO11 로 라벨 밖 白 후보를 찾는 도구(후보 20개는 전부 탁자 흰 테두리·패산 면이라 쓰지 않음). 공개 YOLO11·HaseLab YOLO26 도 흰 테두리 위 白 퐁을 못 잡는다.

```
python -I -X utf8 experiments/tile_classifier/det_build.py --blank-swap       # data/det/ds + blank/bank_sheet.jpg(白 재료 확인)
python -m kaggle datasets version -p experiments/tile_classifier/data/det/ds -m "..." --dir-mode zip
python -m kaggle kernels push -p experiments/tile_classifier/det_kernel
python -m kaggle kernels output jjh7757/mahjong-tile-det -p experiments/tile_classifier/data/det/kaggle_out_r3
python -I -X utf8 experiments/tile_classifier/det_blank_recall.py r2 r3       # 白·무늬 패 재현
python -I -X utf8 experiments/tile_classifier/server_bench/role_full_bench.py --det det_r3 [--size-filter]   # 자리 판독(server_bench/models/det_r3_fold_*.onnx 먼저 복사)
```

**크기 거르기(표 1-63):** 검출 상자가 패 크기 중앙값의 1.6배를 넘으면 버린다(`role_full_bench.drop_oversize`). 2회차엔 해가 없고 3회차의 종이 헛검출을 없애 둘 다 규칙 28·새 경로 30/37 로 같다. 3회차는 142535 의 白 2장을 더 찾는다. 다음 매장 사진으로 회차를 정한다.

## 검출기 4회차 — 흰 테두리 위 白 증강, fold 별 재료 (`det_rim_aug.py`·`det_build.py --rim-blank`, metrics 표 1-64, 2026-11-04)

3회차의 누수(시험 사진 白 이 학습 사본에 붙음)를 막으려고 白 재료를 fold 별로 나눠 사본 `__ra`(fold_a 전용)·`__rb`(fold_b 전용)를 만들고, 커널이 fold 마다 다른 쪽을 뺀다. 白 은 실제 크롭의 패 몸통만 펠트 가장자리·흰 테두리에 1~4장씩 섞는다. 白 재현 68 → 79/80(흰 테두리 위 白 퐁 164501 3/3·171245 2/3)이지만 서랍 속 종이 헛검출로 자리 판독 1장 감소 — 보류, 다음은 "패 아닌 흰 물체" 음성 합성.

```
python -I -X utf8 experiments/tile_classifier/det_build.py --rim-blank      # data/det/ds, blank/rim_check/<이름>.jpg(새 白 빨간 상자)
python -m kaggle datasets version -p experiments/tile_classifier/data/det/ds -m "..." --dir-mode zip
# 데이터셋 처리가 끝난 뒤(datasets files 에 __ra 가 보일 때) 커널을 올린다 — 먼저 올리면 이전 버전으로 돈다
python -m kaggle kernels push -p experiments/tile_classifier/det_kernel
```
## 검출기 5회차 — 패 아닌 흰 물체 음성 합성 (`det_rim_aug.negative_patch`·`place_negatives`, `det_build.py --rim-blank --neg`, metrics 표 1-65, 2026-11-04)

4회차 증강 사본마다 라벨 없는 흰·베이지·분홍 종이 조각 4개(글줄·QR 무늬, 절반은 패보다 크고 길쭉, 절반은 패 크기지만 늘 무늬 있음)를 더해 "흰 것 = 패" 쏠림을 막는다. 白 재현 80/80(흰 테두리 白 퐁 전부), 서랍 속 종이 헛검출 사라짐, 큰 헛검출 3 → 1. 자리 판독 /34 규칙 28 → 29, hybrid 30 그대로. 다만 181209 의 45° 기운 화료패를 더 정확한(큰) 상자로 잡아 서버 `keep_faces`(상자 안 흰 비율 0.5 이상) 에 걸려 빠지고 규칙이 틀린 자동 반영 — 보류. 커널 로그의 "이미지 646 총 바이트 357787726" 이 로컬과 같은지 먼저 본다.

```
python -I -X utf8 experiments/tile_classifier/det_build.py --rim-blank --neg
python -I -X utf8 experiments/tile_classifier/det_blank_recall.py r4 r5
python -I -X utf8 experiments/tile_classifier/server_bench/role_full_bench.py --det det_r5 [--size-filter]
```


## 검출기 6회차 — 앞면·뒷면 2종 (`det_build.py --rim-blank --neg --backs`, `det_kernel_r6/`, metrics 표 1-67, 2026-11-04)

5회차 데이터에 표 1-54 검수 2차 뒷면 1,817개를 종류 1 로 더했다(白·음성 증강은 뒷면 위에 안 놓음 — `det_rim_aug.augment(avoid=)`, 재색칠은 비교를 위해 뺌). 새 데이터셋 `mahjong-tile-fb-r6`. 2종 ONNX 는 출력이 1×6×N(cx, cy, w, h, 앞면, 뒷면)이라 서버 `LocalReader.detect` 가 그대로 앞면만 읽는다. `det_relabel.detect` 는 `classes=[0]` 로 앞면만. 결과: 헛검출 30 → 26, 안깡 뒷면 4/4 지만 앞면 −3·白 −1, 자리 판독 hybrid 30 → 28 — 보류.

## 7회차 준비 — 회전 상자(OBB) 라벨과 전수 조사 (`det_obb.py`·`det_audit.py`·`det_audit_apply.py`, `det_build.py --obb`, `det_kernel_r7/`, 2026-11-04)

축 상자는 기운 패를 펠트째 감싸 흰 비율 거르기 같은 규칙을 패 모양마다 다시 맞춰야 한다(표 1-65 181209). 그래서 회전 상자로 바꾼다.

1. `det_obb.py`: 축 라벨 → 회전 상자 초안. 패 마스크의 minAreaRect 에서 각도만, 크기는 라벨 상자에 내접하게 기하로(`inscribed`). 진짜 기운 낱장은 내접 사각형 밖 귀퉁이가 펠트(rot). 줄(패산·손패)은 이어진 3개 이상이 한 직선이면 직선 각도(row) — 단 내접 사각형이 축 상자보다 사진 속 반듯한 패 모양에 가까울 때만(계단처럼 비켜 놓은 반듯한 패는 축). 뒷면 낱장은 10°·귀퉁이 25% 로 보수적. 고른 값은 `obb/review_obb.json`({key: axis|mask|inscribed|{"angle": 도}}, 각도 = 이미지 좌표 atan2(dy,dx) 를 −45~45 로 접은 값, 시계 방향 +).
2. 독립 검수(81개) → `review_obb.json`, 170105 두 장 묶음 상자 둘로 나눔.
3. 전수 조사: `det_audit.py` 가 사진마다 라벨 + 그 사진을 학습 안 한 2종 검출기(표 1-54)와 어긋난 곳(노랑 = 라벨 없는 검출, 자홍 = 검출 없는 라벨)을 그리고(`obb/audit/<사진>.jpg`), 하위 에이전트 5개(Opus, 7장씩, 지시 `obb/audit/BRIEF.md`)가 35장 상자 4,027개를 모두 확대해 보고 제안(`obb/audit/fix_g*.json`)을 썼다. `det_audit_apply.py check` 의 비교 그림(`check_*.jpg`)으로 389건을 전부 눈으로 확인한 뒤 `apply` → `obb/audit/fixes.json`(det_backs 가 FACE_*·BACK_* 에 더해 읽음, 더한 뒤 지움) + `review_obb.json`.
   - 고친 것: 앞면 더함 15·지움 10(빠진 패, 두 장 묶음, 주사위 버튼 헛 라벨, 옆면까지 넣은 白), 뒷면 더함 23·지움 22(세운 손패 보라 띠 잘림, 패산이 모서리 패까지 덮음, 절반 미만 보이는 아래층, 흐트러진 왕패 헛 상자), 각도 319.
   - 조사에서 나온 자동 규칙의 약점(새 사진에서 다시 볼 것): 줄 중간 앞면 표시패는 종류가 달라 줄에서 빠짐, 낱장 8~15° 가 귀퉁이 판정(옆면이 흼)으로 축에 남음, 도미노처럼 기운 줄은 중심선 각도 부호가 패와 반대, 사진 전체가 5~13° 돌아간 매장 사진(125839·130743·134815)은 5° 기준 근처에 몰림, 옆면을 상자에 넣는 기준이 섞임(안깡 뒷면·흰 판 위 白).
4. `det_build.py --rim-blank --neg --backs --obb` → `data/det/ds_r7`(YOLO OBB 라벨: 종류 + 네 꼭짓점), 커널 `det_kernel_r7/`(6회차 커널 + `yolo26n-obb.pt`), 새 데이터셋 `mahjong-tile-obb-r7`.

```
python -I -X utf8 experiments/tile_classifier/det_obb.py
python -I -X utf8 experiments/tile_classifier/det_audit.py            # 조사 그림
python -I -X utf8 experiments/tile_classifier/det_audit_apply.py check [fix_g2,...]
python -I -X utf8 experiments/tile_classifier/det_audit_apply.py apply [--skip 번호,...]
python -I -X utf8 experiments/tile_classifier/det_obb.py              # 반영 뒤 다시
python -I -X utf8 experiments/tile_classifier/det_build.py --rim-blank --neg --backs --obb
```

## 7·8회차 결과와 서버 정리 벤치 (`server_bench/obb_detect.py`·`haku_pair.py`·`corner_fix.py`·`loose_ctx.py`·`felt_only.py`·`field_bench.py`, `make_recolor_test.py`, metrics 표 1-68~1-70, 2026-11-05)

- 7회차(회전 상자) 와 8회차(+ 재색칠, `det_build.py --recolor`, 시험용 색 테두리 검정·펠트 파랑·뒷면 노랑은 학습에서 뺌)는 서버 코드가 축 상자를 가정해 그대로는 이득이 없다. `obb_detect.install(bench, lr, river, rot_white, rot_cut, sliver, kan)` 이 OBB ONNX(1×7×N)를 감싸는 축 상자로 바꿔 넘기고, `rot_cut` 이면 분류기 크롭을 회전 상자대로 세워 자른다(134815 −12° 2만: 축 8m 0.18 → 세움 2m 0.87).
- `role_full_bench.py` 옵션: `--obb --rot-cut --clean --haku2 --corner-fix --loose-ctx`(+ `--felt-only` 시험, 모서리 울기가 펠트 밖이라 멈춤). 8회차 + 전부 = 개발 34 hybrid 32 (틀린 자동 반영 0).
- 테스트 세트 벤치 `field_bench.py`(10/24 삼각대 15장, `--recolored` = `make_recolor_test.py` 색 바꾼 사본): 기운 탁자라 2회차·8회차 모두 0/15 — 판별력 없음.

```
python -I -X utf8 experiments/tile_classifier/det_build.py --rim-blank --neg --backs --obb --recolor   # ds_r8
python -I -X utf8 experiments/tile_classifier/server_bench/role_full_bench.py --det det_r8 --obb --rot-cut --clean --haku2 --corner-fix --loose-ctx
```

## 역할 모델 입력에 회전 상자·뒷면, 합성 보강, 라벨 수정 (`role_set.py --feat rot`·`role_synth.py`·`role_field.py score rot`, 서버 `app/roles.py`, metrics 표 1-78, 2026-11-05)

운영 역할 모델은 8회차 검출기의 회전 상자를 **감싸는 축 상자**로 받아 기운 패를 크고 정사각형으로 보고, 눕힘 플래그가 뒤집히며, 뒷면 상자는 늘 0 이었다. 한 번에 묶어 재학습:

- **특징 11칸(`--feat rot`):** 회전 상자의 변으로 잰 패 폭·높이·눕힘 + sin·cos(2×기울기, −45~45°). 실제 사진은 7회차 라벨 `data/det/obb/rects.json` 을 IoU 로 매칭(`scene_rects`·`match_rects`·`tile_geom`), 테스트 15장은 `det_r8_final.onnx` 검출 회전 상자(`field_rects`, `field/rects_r8.json`)를 펠트 호모그래피로 보낸 뒤 펠트 축 기준으로 잼. 예전 9칸은 `--feat old` 그대로. 가중치 파일은 첫 층 모양으로 칸 수를 안다(`load_nets`).
- **합성 보강:** 상자마다 기울기(줄 + 낱장 지터, 강 끝 비스듬한 패, 떼어 둔 패 ±45°, 사진 전체 ±3° 또는 5~13°), 손패 줄 끝의 떨어진 2~4장 = 손패, 안깡(앞면 2 + 양끝 뒷면 2) = 울기. `feat="old"` 면 기운 패를 감싸는 축 상자 크기로 낸다.
- **라벨 수정:** 124654·125839 의 손패 줄 끝 3장(truth 에 울기 없음)이 규칙 라벨에서 울기였다 → 손패(`review.json` `_note_20261105`). 표 1-61 틀린 자동 반영의 원인.
- **서버:** `obb.record` 가 뒷면 검출을 기록(`backs_of`), `roles.tokens` 가 모델 칸 수(ONNX 입력 모양, `RoleNet.feat`)에 따라 9/11칸을 만들고 11칸이면 회전 상자 꼭짓점(`unrotate_pts`)·뒷면 토큰을 넣는다. 응답에 `backs`·`feat`. 새 모델 `app/assets/tile-roles-rot.onnx`. **11-05 사용자 "11칸 서버 코드 변경" → 서버 기본값을 11칸으로(`roles.ROLE_MODEL`, 커밋·배포 전)**, 예전 9칸 `tile-roles.onnx` 는 되돌리기용으로 남겨 `LOCAL_ROLE_MODEL` 로 끼움.

결과(표 1-78): 교차 검증 /1,046 — 9칸 1,034 · 11칸 1,026(130743 강 8개 씨드 흔들림), 테스트 15장 /706 — 9칸 701 · **11칸 705**(표 1-59 는 703), 자리 판독 벤치 /32 — hybrid 둘 다 32(0), model 29 → 31. 운영 채택은 다음 매장 사진으로.

```
python -I -X utf8 experiments/tile_classifier/role_synth.py --n 6 --feat rot                                     # 합성 그림 눈 확인(synth_check/)
python -I -X utf8 experiments/tile_classifier/role_set.py --feat old --synth 8000 --synth-epochs 3 --epochs 100 --seeds 3 --pre-file pre_synth8k_v3old.pt --tag _synth3_old_fix
python -I -X utf8 experiments/tile_classifier/role_set.py --feat rot --synth 8000 --synth-epochs 3 --epochs 100 --seeds 3 --pre-file pre_synth8k_rot.pt --tag _synth3_rot_fix
python -I -X utf8 experiments/tile_classifier/role_field.py score rot pre_synth8k_rot.pt                         # 테스트 15장, data/role/role_all_rot.pt 저장
python -I -X utf8 experiments/tile_classifier/role_export.py data/role/role_all_rot.pt experiments/tile_classifier/server_bench/models/tile-roles-rot.onnx
LOCAL_ROLE_MODEL=.../tile-roles-rot.onnx python -I -X utf8 experiments/tile_classifier/server_bench/role_full_bench.py --det det_r8 --native
```

## 홀드아웃 조합 — 역할 모델 fold 별 ONNX와 나눔 대응표 (개선 계획 2단계, 2026-11-05)

운영 모델(8회차 final 검출기·분류기 `tile-cls-mnv3s`·11칸 역할 모델 `tile-roles-rot`)은 개발 사진을 전부 배워, 개발 세트에서 잰 숫자는 "배포 확인" 이지 채택 근거가 아니다. 개발 32회를 **그 사진을 안 배운 모델 셋**으로 재려고 역할 모델의 3겹 교차 검증 가중치를 fold 별로 저장·내보냈다.

- **다시 학습(한 번):** 3겹 가중치가 저장돼 있지 않아 같은 설정으로 다시 돌리며 저장했다(`role_set.py --save-folds`, 새 옵션). 결과는 저장된 `set_cv_synth3_rot_fix.json` 과 fold 별·합계 모두 같다(1,026/1,046) — 같은 씨드·같은 사전학습 `pre_synth8k_rot.pt` 라 재현됨.
- **내보내기:** `role_export.py` 로 fold 별 ONNX(3씨드 평균 한 그래프, 수동 계산 대 원래 최대 차 3e-7). 파일은 `server_bench/models/`(커밋 안 함).
- **서버:** `experiments/yolo/run_local_server.py --role-model tile-roles-rot_fold_<am|pmA|pmB>.onnx` 는 `server_bench/models/` 에서 찾는다(`_fold_` 가 든 이름). launch.json `recognizer-fold-*`.

대응표(✗ = 그 사진을 학습하지 않음 → 그 서버로 잰다):

| 사진 묶음 | 2회차 검출기(강·표시패) | 8회차 검출기(자리) | 분류기 | 역할 모델 | launch.json (포트) |
| --- | --- | --- | --- | --- | --- |
| B·C·D 6장 | `det_fold_a` ✗ | `det_r8_fold_a` ✗ | `cls_bcd` ✗ | `tile-roles-rot.onnx`(final — B·C·D 는 역할 라벨에 없어 원래 안 배움) ✗ | `recognizer-fold-bcd` (8033) |
| 매장 오전(~13:48, 10장) | `det_fold_b` ✗ | `det_r8_fold_b` ✗ | `cls_am` ✗ | `tile-roles-rot_fold_am`(오후 15장으로 학습) ✗ | `recognizer-fold-am` (8034) |
| 매장 오후A(142535~171025, 평가 6장) | `det_fold_a` ✗ | `det_r8_fold_a` ✗ | `cls_pm` ✗ | `tile-roles-rot_fold_pmA`(오전 + 오후B 로 학습) ✗ | `recognizer-fold-pmA` (8035) |
| 매장 오후B(171245~, 평가 4장) | `det_fold_a` ✗ | `det_r8_fold_a` ✗ | `cls_pm` ✗ | `tile-roles-rot_fold_pmB`(오전 + 오후A 로 학습) ✗ | `recognizer-fold-pmB` (8037) |
| 테스트 15장(10/24 삼각대) | final ✗ | final ✗ | 운영 ✗ | final ✗ | `recognizer-prodlike` (8036) |

- 검출기·분류기 나눔은 시간대 둘(오전/오후 + B·C·D)이고 역할 모델은 셋(오전/오후A/오후B, `role_set.folds` — 오후를 이름순 반으로)이라 오후는 서버 둘로 나눈다. 앱 흐름 `PHOTO_MIN`·`PHOTO_MAX` 경계는 171245(`experiments/speed/run_baseline.sh`).
- 역할 fold 모델은 실제 사진을 2/3 만 배운다(final 은 25장 전부) — 홀드아웃 숫자에는 "덜 배운 몫" 이 섞인다. 검출기·분류기 fold 도 같다.
- 역할 모델 교차 검증의 시험 사진은 EXCLUDED 5장을 포함한 25장이고(채점에서만 뺌), 앱 흐름 평가는 EXCLUDED 를 뺀 20장이다.

```
python -I -X utf8 experiments/tile_classifier/role_set.py --feat rot --synth 8000 --synth-epochs 3 --epochs 100 --seeds 3 --pre-file pre_synth8k_rot.pt --tag _synth3_rot_folds --save-folds
python -I -X utf8 experiments/tile_classifier/role_export.py data/role/role_fold_am_synth3_rot_folds.pt experiments/tile_classifier/server_bench/models/tile-roles-rot_fold_am.onnx --seeds-out   # pmA·pmB 도. --seeds-out(5단계 S4): 씨드별 둘째 출력, 평균은 같음
python -I -X utf8 experiments/tile_classifier/server_bench/prep_alt_cls.py   # 5단계 S3 두 번째 분류기 cls_{bcd,am,pm,all}_s1.onnx(씨드 1, 약 17분)
bash experiments/speed/run_baseline.sh dev <TAG>     # 홀드아웃 서버 넷 + exp-files
U_BCD=8036 U_AM=8036 U_PMA=8036 U_PMB=8036 bash experiments/speed/run_baseline.sh dev <TAG>   # 운영과 같은 모델
python -I -X utf8 experiments/speed/stats.py diff <A 로그들> <B 로그들>
```

## 7-1: 세워 자른 크롭으로 분류기·역할 모델 재학습 (`harvest.py --obb`·`train.py --obb`·`role_label.py --obb`, metrics 표 1-95 기준·1-96 결과, 2026-11-06, **미채택**)

운영은 8회차 회전 상자를 서버 `app/obb.upright()` 로 세워 자른 크롭을 분류기에 넣는데, 분류기는 축 상자 크롭으로 배웠다. 학습 크롭을 추론과 맞추고(같은 함수를 import, 같은 PAD), 역할 라벨을 7회차 전수 조사 상자로 다시 만들어 한 번씩 학습했다.

- **크롭 모으기:** 전수 조사 상자(`data/det/obb/rects.json`, 고침 반영) 앞면 2,245개에 기존 라벨 1,550개(`data/index.json` 259 + 검토 `review.extra` 1,254 + 白 37)를 상자 IoU ≥ 0.5 로 옮김 → **1,168 크롭**(같은 패 중복 162 합침, 종류 충돌 0). 못 옮김 220 = 전수 조사 밖 사진(10-29~10-31 자정 앱 다시 읽기 'other' 219) + IoU 1. 방향은 예전 크롭과 같게(자리 크롭 = 자리 방향, harvest = 그때 고른 turn, 白 = 세로). 눈 확인: 표본 50장(`sample50.jpg`) + 적5·보통 5 99장(`check_fives.jpg`) 틀린 라벨 0.
- **증강:** 예전 AUG 에 180° 회전(p 0.5)·JPEG 품질 q60~95(p 0.5, 정사각형으로 줄이기 전 패 해상도에서), 채도는 올리기만 (1.0, 1.2), 색상 0.02·±8°·밝기·대비·흐림·라벨 스무딩 그대로. 빨강 보존 확인(`train.py --red-check`, 서버 `signals.red_ratio`): 128px 가운데 잘라 재는 대리 지표는 채도 0.2·0·올리기만 모두 극값이 겹치고 차이는 잡음 수준 — 겹침은 밝기·대비·이동(예전부터 있던 증강) 몫(`data/harvest_obb/red_check_pct.json`).
- **역할 라벨:** `role_label.py --obb` → `data/role/labels_obb.json`(review.json 104건 IoU 로 옮김, 지운 상자 2건 못 옮김, 124654·125839 손패 13·울기 0 유지), 옛 라벨과 같은 상자 1,364개 역할 차이 0, 새 상자 25개는 그림(`check_obb/new_boxes.jpg`)으로 보고 7개 고침(`role_label.REVIEW_OBB`). 학습은 표 1-78 과 같은 설정(`pre_synth8k_rot.pt` 를 읽어 미세 조정).
- **결과(표 1-96):** 분류기 홀드아웃 세운 크롭 1,168/1,168 → 1,164(2m→3m·1m), 회귀 fold unsafe 26 → 43(B·C·D 울기 發→南, 축소 0.6 2p→5p — 분류기만 바꿔도 42), prod 17 → 20 → 기준 (b) 미충족, 운영 모델 그대로. 역할 모델만은 교차 검증 정답 대비 손패 장수 12 → 14/18·울기 16 → 17/18, 테스트 15장 705/706 그대로, 회귀 unsafe 26 → 27. F1400 적5만은 안 고쳐짐.

```
python -I -X utf8 experiments/tile_classifier/harvest.py --obb                 # data/harvest_obb/{crops,index.json,report.json,sheet_*,sample50.jpg}
python -I -X utf8 experiments/tile_classifier/train.py --red-check             # 증강 뒤 적5·보통 5 빨강 비율(red_check.json)
python -I -X utf8 experiments/tile_classifier/train.py --obb                   # cls2_{bcd,am,pm,all}{,_s1} → data/*.pt, server_bench/models/*.onnx, harvest_obb/results.json(약 30분)
python -I -X utf8 experiments/tile_classifier/train.py --obb --eval-only       # 홀드아웃 전(cls_*)·후(cls2_*) 세운 크롭·축 크롭
python -I -X utf8 experiments/tile_classifier/role_label.py --obb              # data/role/labels_obb.json, labels_obb_diff.json, check_obb/
ROLE_LABELS=labels_obb.json python -I -X utf8 experiments/tile_classifier/role_set.py --feat rot --synth 8000 --synth-epochs 3 --epochs 100 --seeds 3 --pre-file pre_synth8k_rot.pt --save-folds --tag _obb
ROLE_LABELS=labels_obb.json ROLE_TAG=_obb python -I -X utf8 experiments/tile_classifier/role_field.py score rot pre_synth8k_rot.pt   # role_all_rot_obb.pt, field/score_rot_obb.json
python -I -X utf8 experiments/tile_classifier/role_export.py <절대경로>/data/role/role_fold_am_obb.pt <절대경로>/server_bench/models/tile-roles-rot2_fold_am.onnx --seeds-out   # pmA·pmB, role_all_rot_obb.pt → tile-roles-rot2.onnx
bash experiments/speed/run_71.sh <TAG>          # 서버 단독: 회귀 fold·prod 전·후·분류기만·역할만 + 테스트 15장(서버 feat/cls-alt worktree ../mahjong-recognizer-s7)
U_BCD=8063 U_AM=8064 U_PMA=8065 U_PMB=8067 bash experiments/speed/run_baseline.sh dev <TAG>   # 앱 흐름 전: launch.json recognizer-fold1-*(같은 worktree, 지금 모델)
U_BCD=8073 U_AM=8074 U_PMA=8075 U_PMB=8077 bash experiments/speed/run_baseline.sh dev <TAG>   # 앱 흐름 후: recognizer-fold2-*(--cls-tag cls2, tile-roles-rot2*)
U_FIELD=8066|8076 [RECOLOR=1] bash experiments/speed/run_baseline.sh field <TAG>             # 테스트 15장: recognizer-prod1(지금) / recognizer-prod2(새)
```

## 7-2: 장면 합성으로 검출기·분류기 사전학습 (`scene_synth.py`·`det_kernel_r9/`·`train.py --synth-pre`, metrics 표 1-97 기준·1-98 결과, 2026-11-06, **미채택**)

실제 패 크롭을 펠트 위에 마작 규칙대로 놓고 카메라로 찍은 것처럼 만든 장면으로 검출기·분류기를 먼저 학습(사전학습)하고, 미세 조정은 운영 모델과 똑같이 했다. 바꾼 것은 사전학습 하나뿐.

- **재료(`scene_synth.py mat` → `data/synth/mat/`):** 앞면 = harvest_obb 1,168장(오전 415·오후 681·B·C·D 72)의 전수 조사 회전 상자를 서버 `upright(pad 0)` 로 몸통만 세워 자름, 뒷면 1,818장(rects.json 뒷면 상자, 긴 변 세로, 색 중앙값), 펠트 조각 429장(zone_points 펠트 사각형 안, 패 상자·살색·밝기 끝을 피한 256px, 사진당 최대 14). 재료마다 사진의 나눔(bcd·am·pm·other)을 적는다.
- **누수 금지 풀:** a = 오전 + other(앞면 415·뒷면 717·펠트 189, 사진 14) → 검출기 fold_a·분류기 cls_pm, b = 오후 + other(681·999·216, 19) → fold_b·cls_am, nobcd = 오전 + 오후(1,096·1,364·293, 25) → cls_bcd, all(1,168·1,818·429, 35) → final·cls_all. 홀드아웃 사진의 패·뒷면·펠트는 그 나눔 모델의 합성에 하나도 안 들어간다.
- **장면:** 화료자 손패 줄 13/14(화료패 틈 또는 ±30~60° 떼어 둠), 다른 자리 세운 뒷면 줄 0.6·공개 0.15·없음 0.25, 모서리 울기(퐁·치·명깡·안깡 뒷면 2, 한 장 눕힘), 강 6장 줄(리치 눕힘), 패산(옆면 두께 2배 한 장), 왕패 표시패, 떨어진 낱장, 기계·리치봉·종이(라벨 없음). 카메라 기울기 0~30°(반은 10° 안), 평면 회전, 크기 0.6~1.2, 옆면·그림자, 노출·기울기·비네팅·화이트밸런스 ±13%, 손 가림, 흐림 σ 0.3~3(반), 모션 흐림 10%, 노이즈, JPEG q35~95. 분류기 크롭만 15% "빨강 채도 ×0.3~0.7"(7-1 검토 ⑤). 팔레트에 시험용 색(검정 테두리·파랑 펠트·노랑 뒷면)은 없다(표 1-69). 먼 패부터 그려 이웃 옆면이 앞면을 덮지 않게 하고, 검출기 라벨은 절반 넘게 보이고 손 가림 절반 이하인 패만, 분류기 크롭은 95% 넘게 보이고 가림 5% 안인 앞면만.
- **표본 시트:** `data/synth/sheet_det.jpg`(12장, 빨강 앞면·파랑 뒷면·노랑 라벨 뺌)·`sheet_cls.jpg`. 노트북 한 프로세스 장면 0.5초·분류기 크롭 장면 1.3초.
- **검출기 9회차(`det_kernel_r9/train_det_r9.py`, 캐글 T4, ultralytics 8.4.202 고정):** 커널 안에서 풀마다 합성 8,000 + 검증 200(장면당 상자 약 61개) → `yolo26n-obb.pt` 에서 6에폭 사전학습(1280·배치 8·뒤집기·회전 8회차와 같음, close_mosaic 2, last.pt) → 8회차와 같은 데이터(`mahjong-tile-obb-r8`, 이미지 960 바이트 대조 일치)·나눔·설정(60에폭, patience 20)으로 미세 조정. 5시간 21분. 검증 mAP50-95 fold_a 0.928 → 0.934, fold_b 0.936 → 0.942, final 0.978 → 0.980. 받은 ONNX 는 `server_bench/models/det_r9_{fold_a,fold_b,final}.onnx`(커밋 안 함).
- **분류기(`train.py --synth-pre`):** 풀마다 합성 장면 8,000 × 3장 = 크롭 약 2.3만(37종 모두, 종류당 약 580~600)을 서버 `upright(PAD)` 로 자른 `data/synth/cls_<pool>.npz` → ImageNet MobileNetV3 small 에서 2에폭 사전학습(AdamW 5e-4·코사인·균형 뽑기·AUG) → 운영과 같은 묶음·AUG·40에폭·씨드로 미세 조정 `cls3_{bcd,am,pm,all}{,_s1}`(모델당 약 9분). 홀드아웃 세운 크롭 1,168 → 1,167(3z→1z), 씨드 1 1,167(1s→8p), 적5↔5 0.
- **결과(표 1-98):** 회귀 21변형 합계 unsafe fold 26 → 22·prod 17 → 7, 축소 0.6·흐림 σ3 가 크게 나아짐(fold 장면 15 → 31·6 → 25). 그런데 테스트 15장(펴기) 서버 단독 189 → 188/196(F1434 안깡 `4s` 4장을 `8s` 4장으로 — 검출기 몫), 색 바꾼 15장 145 → 139(앱 흐름 145 → 136/211) → 기준 (c) 미충족, 운영 모델 그대로. 개발 32회 앱 흐름 434/436·경고 없는 틀린 자동 0, 테스트 앱 흐름 198 → 200/211 은 그대로이거나 나음. 검출기만 바꾸면 회귀 fold unsafe 26 → 50, 분류기만은 22.

```
python -I -X utf8 experiments/tile_classifier/scene_synth.py mat                                   # data/synth/mat/{faces,backs,felt,index.json}
python -I -X utf8 experiments/tile_classifier/scene_synth.py sheet                                 # 표본 시트
OMP_NUM_THREADS=1 python -I -X utf8 experiments/tile_classifier/scene_synth.py cls --pool a --n 8000 --per 3 --workers 14   # b·nobcd·all 도(풀당 약 25분)
python -I -X utf8 experiments/tile_classifier/train.py --synth-pre [--only bcd] [--eval-only]      # cls3_* → data/cls3_*.pt, server_bench/models/cls3_*.onnx, data/synth/results.json
# 캐글: data/synth/kaggle_r9/(scene_synth.py + mat/, 데이터셋 jjh7757/mahjong-scene-synth-r9) + det_kernel_r9/ push → kernels output → det_r9_*.onnx
bash experiments/speed/run_72.sh <TAG>        # 서버 단독: 회귀 fold·prod 전·후·검출기만·분류기만 + 테스트 15장(서버 feat/cls-alt worktree ../mahjong-recognizer-s8)
U_BCD=8083 U_AM=8084 U_PMA=8085 U_PMB=8087 bash experiments/speed/run_baseline.sh dev <TAG>   # 앱 흐름 전: launch.json recognizer-fold3base-*
U_BCD=8093 U_AM=8094 U_PMA=8095 U_PMB=8097 bash experiments/speed/run_baseline.sh dev <TAG>   # 앱 흐름 후: recognizer-fold3-*(--seat-det det_r9 --cls-tag cls3)
U_FIELD=8086|8096 [RECOLOR=1] bash experiments/speed/run_baseline.sh field <TAG>             # 테스트 15장: recognizer-prod3base / recognizer-prod3
```

## 7-2a: 분류기만 합성 사전학습, 새 씨드 (`train.py --synth-pre --tag cls4 --seed-offset 10`, metrics 표 1-99 기준·1-100 결과, 2026-11-06, **채택 — 서버 feat/cls-alt 599473e, 운영 미반영**)

7-2 와 같은 코드·합성 크롭(`data/synth/cls_{nobcd,b,a,all}.npz`)·풀 대응(bcd→nobcd·am→b·pm→a·all→all)·사전학습 2에폭·미세 조정(축 크롭 1,550 + AUG 40에폭)에 **씨드만 새로**(주 10·두 번째 11, 사전학습 난수 1000 + 씨드). 검출기는 8회차 그대로.

- `--tag`(모델 이름 앞, 기본 cls3)·`--seed-offset`(실제 씨드 = 오프셋 + `--seeds` 번호, 이름 꼬리 `_s1` 은 번호로) 만 더함. 결과 `server_bench/models/cls4_*.onnx`(커밋 안 함)·`data/cls4_*.pt`·`data/synth/results_cls4.json`·`log_cls4.txt`. 8벌 1시간 26분(노트북 CPU).
- 결과(표 1-100): 회귀 21변형 unsafe/unsafe_app fold 26/10 → 22/3·prod 17/11 → 11/5(축소 0.6·흐림 σ3), 개발 앱 흐름 434 → 433/436·경고 없는 틀린 자동 0, 테스트 15장 서버 189·앱 198·색 바꾼 15장 서버 145·앱 145 모두 그대로, 서버 시간 같음 → 채택. 7-2 의 색 바꾼 하락·F1434 회귀는 검출기 몫이었다. F1400 적5만은 그대로.
- 운영용: `cls4_all.onnx` → 서버 `app/assets/tile-cls-mnv3s-v2.onnx`, `cls4_all_s1.onnx` → `tile-cls-alt-v2.onnx`, `local_read.CLS_MODEL`·`ALT_CLS_MODEL`·`signals.ALT_CLS_MODEL` 기본값 v2(옛 파일은 남김 — `LOCAL_CLS_MODEL`·`LOCAL_ALT_CLS_MODEL` 로 되돌림). push 안 함.

```
python -I -X utf8 experiments/tile_classifier/train.py --synth-pre --tag cls4 --seed-offset 10      # cls4_* 8벌
bash experiments/speed/run_72a.sh <TAG>       # 서버 단독: 회귀 fold·prod 전·후 + 테스트 15장·색 바꾼 15장 전·후(서버 feat/cls-alt worktree, RECOGNIZER_REPO)
U_BCD=8083 U_AM=8084 U_PMA=8085 U_PMB=8087 bash experiments/speed/run_baseline.sh dev <TAG>   # 앱 흐름 전: recognizer-fold3base-*
U_BCD=8103 U_AM=8104 U_PMA=8105 U_PMB=8107 bash experiments/speed/run_baseline.sh dev <TAG>   # 앱 흐름 후: recognizer-fold4-*(--cls-tag cls4)
U_FIELD=8086|8106 [RECOLOR=1] bash experiments/speed/run_baseline.sh field <TAG>             # 테스트 15장: recognizer-prod3base / recognizer-prod4
```
launch.json 의 `recognizer-fold3*`·`prod3*`·`fold4-*`·`prod4` 는 `--repo C:/Users/jjh7757/dev/mahjong-recognizer-s9`(측정 뒤 지웠음) — 다시 쓰려면 `git -C ../mahjong-recognizer worktree add ../mahjong-recognizer-s9 feat/cls-alt`. feat/cls-alt 가 이제 v2 기본이므로 "전"(운영 분류기)을 재려면 `prod3base` 에 `LOCAL_CLS_MODEL=…/tile-cls-mnv3s.onnx`·`LOCAL_ALT_CLS_MODEL=…/tile-cls-alt.onnx` 를 주거나 c4484dd 로 worktree 를 만든다.
