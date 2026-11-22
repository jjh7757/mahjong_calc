mxfit — Mortal-S42 버림을 mahjong-helper 틀로 맞추기 (설계서 docs/mxplainer_fit_design_1121.md)
0단계(2026-11-21): 개발 200판 중 ID 순 앞 20판으로 값 뽑기 · S42 채점 시간 재기 + B0 · B1 · B2 일치.

파일
  split.py         나눔(waitsuit.load_split() 과 같은 개발 200판, ID 순 앞 160 맞춤 · 뒤 40 검증, 앞 20 = 0단계).
                   log_path() 는 개발 판이 아니면 오류 — 시험 판 파일을 열지 않는다.
  run_features.py  값 뽑기(tool/tenhou6_features.dart 를 .dill 로 컴파일한 것)를 판마다 프로세스 하나로 병렬 실행.
  s42_batch.py     S42 채점(mortal_local.py 의 to_mjai · decode · ACTION_NAMES import). 작업 단위 = 판 × 국.
  join.py          (game, kyoku, seat, k) 로 맞붙이기. actual 어긋남 · 한쪽에만 있는 열쇠를 센다.
  baseline.py      주 묶음 B0 · B1 · B2 · 실제의 첫째 일치 · 둘째 안 · Q 손해 · 나눔별 · 판 단위 부트스트랩.
  timing.py        A · C 시간 → timing.json, 400판 예상.
  ../../../tool/tenhou6_features.dart   값 뽑기 본체(순수 Dart).
  ../../../test/tenhou6_features_test.dart  매장 4판 교차 검증(reviewPaifu(withEngine) 과 차례마다).

다시 돌리기(Git Bash, 저장소 뿌리에서; dart/flutter 는 PATH 에 없으니 먼저 export)
  export PATH=/c/Users/jjh7757/flutter/bin:$PATH
  O=experiments/paifu_review/results/mxfit/stage0
  M=experiments/paifu_review/mxfit
  mkdir -p $O/bin $O/features $O/logs

  # 0) 나눔 대조
  python -X utf8 $M/split.py --check

  # 1) 교차 검증 · 정적 검사
  flutter analyze lib test tool
  flutter test test/tenhou6_features_test.dart

  # 2) 값 뽑기(A): 러너 비교(1판) 뒤 .dill(JIT)로 12 프로세스
  dart compile kernel tool/tenhou6_features.dart -o $O/bin/tenhou6_features.dill
  #   (비교용) dart compile exe tool/tenhou6_features.dart -o $O/bin/tenhou6_features.exe
  #            time $O/bin/tenhou6_features.exe <판.json> --out x.jsonl ; time dart run tool/tenhou6_features.dart <판.json> --out y.jsonl
  python -X utf8 $M/run_features.py --stage0 --procs 12 --dill $O/bin/tenhou6_features.dill --out-dir $O/features --timing $O/logs/features_timing.json

  # 3) S42 채점(C): 2판으로 프로세스 × 스레드 비교 뒤 가장 빠른 16 × 1 로 20판
  for c in "1 16" "4 4" "8 2" "16 1"; do set -- $c; python -X utf8 $M/s42_batch.py --stage0 --first 2 --procs $1 --threads $2 --out $O/logs/s42_try_p$1t$2.jsonl --timing $O/logs/s42_try_p$1t$2.json; done
  python -X utf8 $M/s42_batch.py --stage0 --procs 16 --threads 1 --out $O/s42.jsonl --timing $O/logs/s42_timing.json

  # 4) 맞붙이기 → 기준선 → 시간
  python -X utf8 $M/join.py --features $O/features --s42 $O/s42.jsonl --out $O/joined.jsonl --report $O/join_report.json
  python -X utf8 $M/baseline.py --joined $O/joined.jsonl --out-md $O/baseline.md --out-json $O/baseline.json
  python -X utf8 $M/timing.py --features $O/logs/features_timing.json --s42 $O/logs/s42_timing.json --trials $O/logs/s42_try_p*.json --single dart_run=80 exe=134 dill=76 --out $O/timing.json

  A 와 C 는 시간을 재려고 따로(동시에 안) 돌렸다. 산출물(results/)은 커밋하지 않는다.

1단계(2026-11-21 밤, 설계서 11절): 개발 200판 값 뽑기 · S42 · 맞붙이기 → 묶음 → 맞추기(맞춤 140 · 고르기 20) → 검증 40.
  pack.py      joined → 주 묶음 결정만 맞추기 · 평가에 쓰는 칸만 추린 pack.jsonl.gz (B0 ~ 실제 맞음은 baseline.decision 그대로).
  fit.py       11-3 값(make_values 하나) · 11-4 F(구간별 가중합) · F 부드러운 정답 · U · 묶음 빼기 변형 · 다시 뽑기 안정성.
               맞춤 · 고르기 판만 연다(part 'val' 은 읽자마자 버림). → weights.json · weights.md · fit_report.* · u_model.pt
  eval_val.py  검증 40판에 한 번 적용(아무것도 고르지 않음) → val.md · val.json · preds_val.jsonl
  split.py     stage1_split(): ID 순 앞 140 fit / 다음 20 select / 뒤 40 val (뒤 40 = val_games()).

다시 돌리기(Git Bash, 저장소 뿌리에서)
  export PATH=/c/Users/jjh7757/flutter/bin:$PATH
  O=experiments/paifu_review/results/mxfit/stage1
  M=experiments/paifu_review/mxfit
  mkdir -p $O/bin $O/features $O/logs
  python -X utf8 $M/split.py --check
  dart compile kernel tool/tenhou6_features.dart -o $O/bin/tenhou6_features.dill
  python -X utf8 $M/run_features.py --dev --gzip --procs 12 --dill $O/bin/tenhou6_features.dill --out-dir $O/features --timing $O/logs/features_timing.json
  python -X utf8 $M/s42_batch.py --dev --procs 16 --threads 1 --out $O/s42.jsonl --timing $O/logs/s42_timing.json
  python -X utf8 $M/join.py --features $O/features --s42 $O/s42.jsonl --out $O/joined.jsonl.gz --report $O/join_report.json
  python -X utf8 $M/baseline.py --joined $O/joined.jsonl.gz --out-md $O/baseline_dev200.md --out-json $O/baseline_dev200.json --title "1단계 개발 200판"
  python -X utf8 $M/pack.py --joined $O/joined.jsonl.gz --out $O/pack.jsonl.gz --report $O/pack_report.json
  python -X utf8 $M/fit.py --pack $O/pack.jsonl.gz --out-dir $O
  python -X utf8 $M/eval_val.py --pack $O/pack.jsonl.gz --dir $O
  (fit.py 는 씨 20261121 · torch 스레드 16 고정 — 다시 돌리면 같은 weights.json 이 나와야 한다.)

2단계(2026-11-21 밤, 설계서 12절): 시험 200판(시험 799판 ID 순 앞 200) 한 번 — 1단계 모델을 얼린 채 적용.
  split.py      test_games() = 개발 200판을 뺀 799판(ID 순), test200_games() = 그 앞 200, test200_path() 는 그 200판만 연다
                (밖이면 오류). log_path() 의 개발 판 보호는 그대로. --check 가 교집합 0 · 앞 200 인지 출력.
  run_features.py · s42_batch.py · pack.py  --test200 옵션(시험 200판만, pack 의 part = 'test'). 다른 옵션의 동작은 그대로.
  eval_test.py  stage1 의 weights.json(F · Fsoft) · u_model.pt 를 읽기만 해 적용(다시 맞추기 · 고르기 없음).
                fit · eval_val 의 함수를 import. → test.md · test.json · preds_test.jsonl
                (--part val --pack stage1/pack.jsonl.gz --out-dir <딴 곳> 이면 stage1/val.json 과 같은 숫자 — 자기 확인)

다시 돌리기(Git Bash, 저장소 뿌리에서). 값 뽑기와 S42 는 겹쳐 돌리지 않는다.
  export PATH=/c/Users/jjh7757/flutter/bin:$PATH
  O=experiments/paifu_review/results/mxfit/stage2
  S1=experiments/paifu_review/results/mxfit/stage1
  M=experiments/paifu_review/mxfit
  mkdir -p $O/bin $O/features $O/logs
  python -X utf8 $M/split.py --check
  dart compile kernel tool/tenhou6_features.dart -o $O/bin/tenhou6_features.dill
  cmp $O/bin/tenhou6_features.dill $S1/bin/tenhou6_features.dill   # 1단계와 바이트가 같아야 함
  python -X utf8 $M/run_features.py --test200 --gzip --procs 12 --dill $O/bin/tenhou6_features.dill --out-dir $O/features --timing $O/logs/features_timing.json
  python -X utf8 $M/s42_batch.py --test200 --procs 16 --threads 1 --out $O/s42.jsonl --timing $O/logs/s42_timing.json
  python -X utf8 $M/join.py --features $O/features --s42 $O/s42.jsonl --out $O/joined.jsonl.gz --report $O/join_report.json
  python -X utf8 $M/pack.py --test200 --joined $O/joined.jsonl.gz --out $O/pack.jsonl.gz --report $O/pack_report.json
  python -X utf8 $M/eval_test.py --pack $O/pack.jsonl.gz --model-dir $S1 --out-dir $O

에이전트 문제지(2026-11-22, 설계서 13절): 검증 40판 주 묶음에서 구간 8 × 30 = 240결정(씨 20261122) → batches/batch_01~12.md, 열쇠 · 자기 검사는 private/.
  python -X utf8 experiments/paifu_review/mxfit/agent_packets.py --out-dir experiments/paifu_review/results/mxfit/agent1
