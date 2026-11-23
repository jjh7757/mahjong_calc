pushfold — 리치가 들어온 차례의 밀기 · 접기 판정 (설계서 docs/push_fold_design_1122.md)

파일
  pf_eval.py   결정 뽑기(3절) · R1 ~ R3 지표 1 ~ 5(5-2절) · 1단계 고르기 / 2단계 판정(5-3절) · 문구(6절).
               stage1  : 개발 select 20 + val 40 = 60판(기본) → results/pushfold/stage1.json · stage1.md · stage1_rows.jsonl
               stage1 --part fit --out-dir <딴 곳> : 자기 확인(맞춤 140판 — 설계서 2절 숫자 10,030 · R1 1,460 88% · R3 279 92%
                         · R1 플레이어가 민 132 중 41% 가 그대로 나와야 함)
               test2   : 시험 2 맞붙인 파일 → test2.json · test2.md · test2_rows.jsonl (고른 규칙은 stage1.json 에서 읽음)
               test2 --selftest-dev --joined <stage1 joined> --out-dir <딴 곳> : 코드 길 확인(판 목록만 개발 select+val 로 —
                         rules 가 stage1.json 과 같아야 함)
  pf_s42.py    S42 채점 래퍼. 시험 2 = split.test599_games() 의 ID 순 앞 200판만(test2_path — 밖이면 오류). s42_batch 의
               _init · run_kyoku_seat · has_kan · stats 를 import(s42_batch 는 안 고침), 출력 줄 · timing 형식은 s42_batch 와 같음.
               --selftest-dev : 개발 앞 2판(split.log_path 로 엶)을 같은 코드 길로 → stage1/s42.jsonl 의 같은 판 줄과 대조.
  pf_join.py   stage3/features(599판) 중 시험 2 200판 파일만 열어 join.py 와 같은 방식으로 S42 와 맞붙임(보고 칸도 같음 +
               판 수 · 파일 수 · 판 밖 S42 줄 수). --selftest-dev : stage1/features 일부 + S42 → stage1/joined.jsonl.gz 의 그 판
               줄과 같은지(s42.secs 만 뺀 대조도 냄).
  explore_fit140.py · explore_fit140_b.py   설계용 탐색(맞춤 140판).
  risk_calibrate.py · risk_calibration.py   위험 보정(다른 세션 — 이 판정과 무관, 고치지 않음).

1단계(2026-11-23, 개발 60판) — 돌림
  python -X utf8 experiments/paifu_review/pushfold/pf_eval.py stage1

2단계 — 아직 안 돌림(1단계에서 규칙을 골랐을 때만). 저장소 뿌리에서, 값 뽑기는 위험 보정 세션의 stage3/features 를 그대로 쓴다.
  P=experiments/paifu_review/pushfold
  O=experiments/paifu_review/results/pushfold
  F=experiments/paifu_review/results/mxfit/stage3/features
  python -X utf8 experiments/paifu_review/mxfit/split.py --check599
  python -X utf8 $P/pf_s42.py --selftest-dev                      # 개발 2판 · 약 15초 — pass true 여야 함
  python -X utf8 $P/pf_join.py --selftest-dev --n 3                # 개발 판 · 몇 초 — pass true
  python -X utf8 $P/pf_s42.py --procs 16 --threads 1 --out $O/test2_s42.jsonl --timing $O/test2_s42_timing.json
  python -X utf8 $P/pf_join.py --features $F --s42 $O/test2_s42.jsonl --out $O/test2_joined.jsonl.gz --report $O/test2_join_report.json
  python -X utf8 $P/pf_eval.py test2 --joined $O/test2_joined.jsonl.gz
  (join 보고에서 actualMismatch 0 · onlyFeaturesOther 0 · onlyS42 0 · s42RowsOutsideGames 0 · featureFiles 200 을 확인)

예상 시간(16 프로세스 × 1 스레드): S42 200판 실측 404초(mxfit 1단계 개발 200판) · 440초(mxfit 2단계 시험 200판) → 약 7 ~ 8분.
설계서 5-1 의 "200판에 40분 안팎" 은 값 뽑기(12 프로세스 2,737초)까지 든 숫자 — 값 뽑기는 stage3 에 이미 있어 이번엔 S42 만.
맞붙이기 · 채점은 1분 안. 값 뽑기 · S42 를 다른 무거운 일과 겹쳐 돌리지 않는다.
산출물(results/)은 커밋하지 않는다.
