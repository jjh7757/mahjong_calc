"""대국 뒤 자동 패보 — 상태 기계(설계서 docs/paifu_auto_agent_design_1124.md 3 · 4 · 5절, 1단계 = 8-1절)(2026-11-24).

헤드 녹화 → 한 반장 패보를 사람 없이 끝까지 돌린다. 판단(단계 순서 · 확정 · 다시 읽기 · 질문으로 올리기)은 이 스크립트가 하고,
LLM 이 필요한 곳(S1 판 경계 · S4 판 결과 · S6 손패 차례 · S7 다시 읽기)은 "읽을 꾸러미" 를 내놓고 멈춘다. 세션은 그 꾸러미마다
하위 에이전트(Opus · effort high)를 띄우고, 끝나면 다시 `next` 를 부른다(설계서 4절 (가)). 1단계에서는 LLM 을 부르지 않고
`replay` 가 11-23 3반장의 이미 있는 답을 꾸러미 자리에 넣는다.

  python -X utf8 experiments/paifu_frames/paifu_auto.py init   --hanchan <반장 설정 json> [--run <실행 폴더>] [--reuse <폴더>] [--hand-settings <폴더>] [--verify-dump <판 id>]
  python -X utf8 experiments/paifu_frames/paifu_auto.py next   --run <실행 폴더>        # 코드로 할 수 있는 단계를 다 돌리고, LLM 꾸러미가 있으면 pending.json + 표준 출력에 내고 멈춤
  python -X utf8 experiments/paifu_frames/paifu_auto.py replay --run <실행 폴더> --from <3반장 결과 폴더> [--before-user]   # 재생 읽기(LLM 0)
  python -X utf8 experiments/paifu_frames/paifu_auto.py apply  --run <실행 폴더> --answers <파일> [--answers <파일> …]   # 사용자 답 → S7 · S8 · S9 다시
  python -X utf8 experiments/paifu_frames/paifu_auto.py next   --run <실행 폴더> --redo S9   # 그 단계부터만 다시(S6 재료는 그대로)
  python -X utf8 experiments/paifu_frames/paifu_auto.py unapply --run <실행 폴더>        # 시험용: apply 전 답으로 되돌리고 S7 · S8 · S9 다시
  python -X utf8 experiments/paifu_frames/paifu_auto.py status --run <실행 폴더>
(저장소 루트에서. 실행 폴더 기본값 = experiments/paifu_frames/results/auto_<설정 id>/)

init 옵션
  --reuse <폴더>          S2 프레임 겹쳐 보기(overlay_dump_c2x.json · reveal_overlay_c2x.json)를 그 반장 결과 폴더에서 복사해 쓴다(재생 시험용 — 8-1절).
  --verify-dump <판 id>   --reuse 일 때 그 판 하나는 headrec_dump.py 로 실제로 다시 뽑아(_verify/) 복사본과 상자 · 종류가 같은지 본다.
  --hand-settings <폴더>  11-23 손 파일(rounds_meta.json · recorder_fix.json, 반장 설정의 paifu.event_fix · hand.call_turns)을 "설정" 으로 쓴다.
                          S5 는 늘 자동 규칙으로 따로 만들고 손 파일과 몇 칸 다른지 s5/compare.json · report.md 에 적는다(무인 흐름의 구멍 목록).
                          안 주면 자동 규칙이 낸 것을 그대로 쓴다.
  --s6-games <판,…>       시험용: S6 칸 틀 검출 · 차례 꾸러미를 그 판들만(차례 목록 · 차례 수 검사는 모든 판). S7 뒤로는 못 감.
  --s6a-rules             견줌용: S6a 를 옛 화소 규칙(handtrack_auto.py conf, 표 12-124)으로. 기본은 준비 읽기(설계서 8-8).
  --no-sup                판 supervisor 단계(S7s)를 끈다 — 끄면 단계 · 질문 규칙 v2 · 표본 판마다 2 가 이 옵션 전(설계서 8-17 4-① 전)과 같다.
  --sup-games <판,…>      시험용: supervisor 를 이 판들만 거치게(나머지 판은 S7s 에서 건너뜀 — 그 판의 unsure 차례는 질문으로).
replay 는 S1 · S4(3반장 result_read · 앱 유국 공개 읽기 s4/<판>/<a|b|c>/reveal_read.json) · S6a(<from>/s6a/<판>/answer.json ·
  <from>/<판>/answer.json · <from>/<판>.json 중 먼저 있는 것) · S6 · S7 꾸러미에 답을 넣는다.
  S7s 꾸러미는 <from>/sup/<판>/ 이 마감(decision.json)된 꾸러미면 paifu_sup.py replay(초안 · 다시 읽기 답을 가져옴) → done(같은 마감 검사)으로
  다시 적용한다(처음 답 칸 값이 다르면 거절 — 답 없음으로 둠).

단계(설계서 3절): S0 준비 · S1 판 경계(LLM) · S2 프레임 · S3 버림 기록 · S4 판 결과(LLM, 둘이 따로) · S5 대조 · 고침 ·
  S6 손패 차례 재료 + 읽기(LLM) · S7 앞뒤 검사 · 다시 읽기(LLM, 한 판 2회) · S7s 판 supervisor(LLM, 판당 하나) · S8 조립 · S9 질문 목록 · 영향 · 보고서.
S9 차례 질문(8-3절 v2): 답의 unsure 또는 확신 말(HEDGE_*)에 걸리면 질문(questions.jsonl 의 signal 칸), 안 걸린 차례는 영향을 재서
  판마다 위 2차례를 표본(samples.jsonl, signal sample:impact — 바뀌는 순 수 0 인 차례는 표본에서 뺌). 질문은 영향 0 · 사용자 답(apply) 숨김,
  표본은 사용자 답만 숨김. — supervisor 단계가 꺼진 실행(--no-sup · S7 이 이미 끝난 옛 실행 폴더)만 이렇다.
판 supervisor 단계 S7s(설계서 8-17 4-① · 3-10 · 3-11, 11-25 밤): 읽은 차례가 있는 판마다 paifu_sup.py pack → 판 꾸러미 하나(sup/<판>/TASK.md,
  끝난 표시 = sup/<판>/decision.json — supervisor 가 done 으로 씀. supervisor 가 다시 읽기 작업자를 스스로 띄우는 방식은 그대로)를 내고 멈춘다.
  모든 판이 마감되면 S8. 이 단계가 켜진 실행의 S9:
  - 차례 질문 = supervisor 의 ask(sup/<판>/questions_sup.jsonl, signal sup:ask) + supervisor 를 안 거친 판의 unsure 차례(signal unsure).
    낱말 규칙(v2)은 질문을 만들지 않고 "그 규칙이었다면" 수만 state signals.v2_compare · report.md 에. 그 밖의 질문(S0 ~ S6 · 판 결과)은 그대로.
  - 표본 = 반장당 SAMPLE_PER_HANCHAN(5): supervisor 가 직접 정한 차례(set) → 다시 읽기로 답이 바뀐 차례 → 영향 큰 순(바뀌는 순 수 0 은 뺌),
    같은 순위 안에서는 영향 큰 순 · 이른 순(판 순서 · 차례 번호). 질문에 오른 차례(숨김 포함)는 표본에 안 넣음.
  - 차례별 출처 파일 paifu_source/<판>.json(패보 형식은 안 바꿈): 손패 주인 버림마다 SOURCE_KINDS 가운데 하나와 근거 파일 이름.
  - report.md 에 판마다 간 길 · supervisor 가 손댄 차례 · 질문 출처(묶음별) · 숨긴 질문 수 · 질문 > 10 경고.
  사용자 답(apply)은 S7 · S8 · S9 만 다시 돈다 — supervisor 를 다시 띄우지 않는다(3-11 정한 것 3).
  옛 실행 폴더(state 에 sup 칸 없음): S7 이 이미 끝났으면 끈 것으로(옛 흐름 그대로), 아니면 켠 것으로 본다(S7s 는 "todo").
단계마다 결과 파일을 남기고 state.json 에 적는다 — 같은 명령을 다시 불러도 된 단계는 건너뛴다(멱등).
확인 페이지 · 답 반영(설계서 8-17 4-②, 11-25 밤): 페이지 · 근거 영상은 paifu_confirm.py(prep · serve · show — 답 = <실행>/answers_user.json 한 파일).
  질문 id 꼴 표 Q_FORMS(묶음 A 가린 확인 · B 후보 고르기 · C 알림)를 페이지와 apply 가 같이 쓴다. apply 는 차례 답(k = k_id) · 뒷도라(none = 없음) ·
  해저 · 강 한 칸 패 종류(_prep/rec/<판>/ 의 그 칸 — 사본 _before_apply/, 기록 user_record_fix.json)를 넣고, 덜 끝난 답 · unknown · unseen · bad · call 은
  까닭과 함께 건너뛰며, B · C 답은 report.md 에 "답 받음 · 반영 안 됨(손으로)" 로 적는다. unapply 가 강 칸까지 되돌린다.
실행기 · 답 반영 뒤 규칙(설계서 8-17 4-③, 11-25 밤): 설정에서 확인 페이지까지의 고리(start · go · page · answer)는 paifu_run.py. 이 파일에서 바뀐 것 둘:
  - apply 뒤의 S7 은 다시 읽기 꾸러미를 내지 않는다(state.user_final — 사용자 답은 최종, 3-11 정한 것 3). 걸린 판은 final_bad 로 그대로 남긴다.
    unapply 는 이 표시를 지운다(apply 전 흐름으로).
  - 검사에 걸린 채 남은 판(S7 final_bad · S8 check_fail)은 S9 가 판마다 알림 질문 하나 <판 앞 세 글자>_s7_check(kind check · 검사 글 그대로 ·
    반영 길 없음 · 영상 없음)로 questions.jsonl 에 올린다 — 답 반영 전의 S9 에서도 같다(전에는 상태에만 남았음).

앱 기록 우선(설계서 8-5 · 8-6 W1 ~ W5, 11-24 저녁) — 반장 설정에 app_record 칸이 있을 때만(없으면 위 흐름 그대로 · 3반장):
  S0  W1 · W2: app_record.build → app_rounds.json(판 목록 · 국 · 본장 · 선 · 아래 자리 · 화료/유국 · 닻 시각 · 결과 · 근거 폴더 · 버림 출처)
      + app/<판>/paifu_app.json(① 촬영 기록 paifu.json / ② 추적 프레임 앱 기록기 재생). 경고는 questions_s0(boundary).
  S1  판 경계를 코드로(꾸러미 없음, LLM 0): t_start = 앱 첫 버림 at − 3초, t_end_play = 앱 마지막 버림 at, t_reveal = min(앱 마지막 버림 at + 2초,
      끝 닻 − 1초)(추정 — 창은 닻 − 60초 ~ + 3초). 앱 버림에 at 이 없는 판이 있으면 판 목록 · 국 이름 · 창을 담은 S1 꾸러미(S1_APP_TASK).
  S3  헤드 녹화 기록기(--bottom-seat = 앱 아래 자리) 뒤 W5: 헤드 녹화 기록기 강 ↔ 앱 버림을 자리마다 맞춰 판 구간 · 시계 차(헤드 − 앱 중앙값 · 퍼짐) →
      w5/align.json · w5_questions.jsonl(둘이 다른 칸 = record 질문, 패 종류는 앱 기록을 따름). 기록기 선 ≠ 앱 선이면 앱 선으로 다시 돌려(rec_app_dealer/) 맞춤.
      W5 가 "덤프 창 첫 프레임부터 강을 봄" 이라 한 판은 창 시작을 앞당김(advance_windows — ADV_* : 15초 걸음으로 빈 탁자 눈금을 찾아
      그 판 S2 c2x · S3 play · W5 다시, 앞 판 끝 · 6걸음 · 2바퀴 한도) → s3/advance.json. 못 찾으면 app_start 질문을 그대로 둠.
  S4  화료(label.json 있음) = 앱 값을 result_read 꼴로(s4/<판>/app/result_read.json, 꾸러미 0). 유국 = 텐파이 자리를 적은 공개 손패 꾸러미(둘이 따로,
      APP_DRAW_TASK, 답 reveal_read.json). 앱 결과가 없는 판(label 없음 등)은 지금 꾸러미 그대로.
  S5  s5_app(W4): 고친 기록 = 앱 버림 기록(1차) + 헤드 녹화 기록기의 시각 · 앱 추적 전 칸(헤드 녹화로 채움) → _prep/rec/<판>/(han3 recfix 출력 꼴,
      han3 recfix 는 안 돌림) · recorder_fix.json(고침 기록) · rounds_meta.json(앱 선 · 아래 자리 · 국 · 결과, 손패 주인 = 화료자 / 유국 텐파이 —
      둘 이상이면 APP_HERO_RULE) · 앞뒤 검사(app_checks: 4장 · 론 패 · 리치 · 울기 묶음 · 엮임 · 사건 순서 · 5장) → 어긋나면 앱 값 둔 채 질문.
      W5 의 record 질문은 S5 질문(app5_*)으로 바꿈. 사건 순서가 차례 규칙과 어긋나고 헤드 순서는 맞으면 헤드 순서(order).
  S6a 손 추적 설정(설계서 8-8, 11-24 저녁 — 준비 읽기): 손 설정(handtrack/config/<판>.json + 판별 출력)이 공용 자리에 없는 판은
      S6a-1 꾸러미(handtrack_prep.py pack → s6a/<판>/TASK.md · 재료, pending.json 꾸러미 id s6a_<판>)를 내고 멈춘다 — 읽기 에이전트가 영역(band · river ·
      meld · reveal_region · search) · t_ready · 공개(t_reveal · reveal_frame, 유국 t_reveal 은 S4 값)를 정해 s6a/<판>/answer.json 에 쓴다.
      (8-9, 11-24 밤) 에이전트는 초안 답을 handtrack_prep.py try 로 그 꾸러미 안 시험 자리(s6a/<판>/try/<n>/)에서 판별 · 차례 나누기까지 돌려 보고
      고친다(판당 5번까지 — 답의 tries 칸). 이 흐름은 try 결과를 쓰지 않고 마지막 answer.json 만 아래 S6a-3 으로 다시 적용한다.
      S6a-3(handtrack_prep.py apply): 답 → 판별 설정(실행 폴더 handtrack/config) + features + 검사(t_ready 뒷면 상자 덩어리 = 닫힌 장수 · band 안,
      공개 프레임 앞면 상자 · reveal_region, 좌표 꼴, 시각 순서). 어긋남 · 답의 unsure 는 questions_s6a(값은 답 그대로). 설정이 바뀌면 그 판의 옛 판별 출력 ·
      칸 틀 캐시 · turn_fix 몫을 지움. 화소 규칙(handtrack_auto.py conf)은 견줌용으로만 남김(init --s6a-rules 일 때 s6a_rules). 손 설정이 다 있는 판(3반장)은 그대로 씀.
      결과는 실행 폴더 handtrack/(config · <판>/ · _work/) — 실행 설정 handtrack 칸으로 han3 · han3_paifu 가 경로를 돌림(handtrack/ht_redirect.py).
      (11-25 밤, 설계서 8-16) 답의 t_ready_late(늦은 후보)가 t_ready 보다 뒤면 apply 가 그것을 판별 설정 t_ready 로 쓴다 — 상태 games.<판>.ready_late 에
      답의 값 · 늦은 후보 · 쓴 값, report.md 에 표시(쓴 판은 질문 아님 · 그 뒤 버림이 0 이라 못 쓴 판은 검사 ready_late 질문).
  S6b 손 추적 판별: handtrack_auto.py run = segment · river · game(run.py 의 features 뒤, sheets 뺌) + bandfit --write(sheet_band). 있으면 건너뜀.
  S6  판별 설정 · 출력(손 설정 판은 공용 자리, S6a 판은 실행 폴더)이 없으면 멈춤. 칸 틀 캐시(det_<판>.json)도 S6a 판은 실행 폴더 handtrack/_work/slotgrid_1117.
      han3 turns · fix · turncut 뒤 차례 수 검사(s6_turn_check): 차례 목록(turn_fix 끼움 포함) ↔ 고친 기록의 손패 주인 버림 중 t_ready 뒤 것.
      차례 0 인 판이 있으면 멈춤(오류), 다르면 질문 <판>_s6_turns(questions_s6). init --s6-games 면(시험용) 칸 틀 검출 · 차례 꾸러미를 그 판만.
  (11-25, 설계서 8-13 — 구현 2-③) 앱 기록 반장(rec_path):
      S6b 는 강 읽기(river)를 안 돌림(handtrack_auto run --no-river). S6 차례 목록은 han3 turns · fix 대신 han3 rturns(고친 기록의 손패 주인 버림 · 울기 중
      t_ready 뒤 것 → 같은 꼴의 차례 목록 + turn_fix) → turncut build → han3 rcheck(3-9 검사: t_ready 앞 버림 · 창 프레임 · 겹침 · 창 안 band 움직임 0 =
      쯔모기리 후보 · 줄 장수 ↔ 울기 수 → <prep>/turns_record_check.json · state S6.record_check · report.md, 질문으로는 아직 안 올림).
      녹화 틀(frame)이 없는 설정(paifu_setup.py 자동 설정)은 S6a 가 손패 주인 쪽 화면 절반에서 손패 줄 후보를 찾아(handtrack_prep.py bandcand →
      s6a/_cand/<판>.json) wide = 화면 절반 · band · search = 후보 1위로 꾸러미를 낸다(2 · 3위는 그림 · 표에만, 공개 상자는 안 만듦 —
      spec regions_mode "half").
  (11-25, 설계서 8-14 — 구현 2-④) 녹화 틀 없는 설정의 강 · 울기 영역 = 반장 모든 판의 버림 기록기 덤프에서 자리마다 상자 하나(dump_regions.py →
      s6a/_dump_regions.json · report.md) — 준비 에이전트에 묻지 않고 그림에만, 답에 있어도 이 값. 설정에 reveal_region 이 없는 판은 S6b 가 game.json 을
      판 결과(result_read hand) · 기록(손패 주인 울기)에서 만든다(s6b_game_json — S6 뒤 걸음이 읽는 칸만).
  멈출 때마다(꾸러미 · 오류) report.md(진행 보고서: 앱 판 목록 · W5 · 창 앞당기기 · S5)를 씀.
기존 스크립트는 하위 프로세스로 부른다: headrec_dump.py · headrec_run.py(--hanchan) · handtrack/han3.py(--hanchan) · han3_paifu.py(--hanchan --out).
공용 모듈(htcommon · turncut · opusread · sam2track · rebuild_opus · paifu_examples · truthprep)은 고치지 않는다. 보호 폴더에는 쓰지 않는다:
  results/han3_1123/ · _work/rawread_han3_1123/ · assets/paifu_h3/ · _work/testtruth_1116/ · _work/slotgrid_1117/ 맨 위 캐시(칸 틀 캐시는 다 있으면 읽기만).
"""
from __future__ import annotations

import argparse
import copy
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HT = HERE / "handtrack"
sys.path.insert(0, str(HT))
import hanchan_cfg as hcfg  # noqa: E402
import dump_regions  # noqa: E402  (11-25, 설계서 8-14 (가)) 강 · 울기 영역을 버림 기록기 덤프에서

PY = sys.executable
KST = timezone(timedelta(hours=9))
SIDES = ["bottom", "right", "top", "left"]
STAGES = ["S0", "S1", "S2", "S3", "S4", "S5", "S6a", "S6b", "S6", "S7", "S7s", "S8", "S9"]
STAGE_NAME = {"S0": "준비", "S1": "판 경계", "S2": "프레임", "S3": "버림 기록", "S4": "판 결과", "S5": "대조 · 고침",
              "S6a": "손 추적 설정", "S6b": "손 추적 판별", "S6": "손패 차례", "S7": "앞뒤 검사 · 다시 읽기", "S7s": "판 supervisor",
              "S8": "조립", "S9": "질문 목록 · 보고서"}
SUP_PY = Path(__file__).resolve().parent / "paifu_sup.py"   # 판 supervisor 명령 한 벌(설계서 8-10) — 흐름은 하위 프로세스로 부름
SAMPLE_PER_HANCHAN = 5  # 설계서 8-17 4-① · 3-11 정한 것 1: supervisor 단계가 켜진 실행의 표본은 반장당 5(판마다 2 를 바꿈)
SAMPLE_TIERS = {0: "supervisor 가 직접 정함(set)", 1: "다시 읽기로 답이 바뀜", 2: "영향 큰 순"}
SOURCE_KINDS = ["첫 읽기 그대로", "다시 읽기와 일치", "supervisor 가 정함", "사용자 확인", "확인 안 된 추정", "코드 규칙", "복원 안 함"]   # 차례별 출처(4-①)
SLOT_KEYS = ("kind", "k", "j", "end_order", "gone")   # paifu_sup.slot 과 같은 칸(조립에 쓰는 칸 값)
MAX_REREAD = 2          # S7: 한 판 다시 읽기 횟수
GAP_S = 30              # S0: 이만큼 넘는 녹화 빈 구간은 보고서에
TOKENS_PER_HANCHAN = 15_000_000   # 11-23 3반장 손 작업 실측(하위 에이전트) — 예산 안내용
RESULT_KEYS = ["dealer_side", "end", "winner_side", "win_type", "loser_side", "win_tile", "hand", "melds", "riichi_cells",
               "dora_indicators", "ura_indicators", "rivers_final", "tenpai_revealed"]
V1114_ROUNDS = ROOT / "experiments" / "tile_classifier" / "data" / "v1114rec" / "new" / "rounds.json"   # 11-23 n01 ~ n08 판 경계의 출처(headrec_rounds.json)
SAMPLE_PER_GAME = 2     # 설계서 8-2절 신호 2(6절 · 9절 ② 를 바꿈): 판마다 질문에 안 오른 차례 중 영향이 큰 위 2차례를 표본으로(8-3: 바뀌는 순 수 0 은 뺌)
# 설계서 8-3절(v2) 신호 1 — 확신 말. 적용 전에 고정한 목록 · 기준(3반장 v1 결과를 보고 고친 것 — 판정은 4단계 안 본 반장). 결과를 보고 바꾸지 말 것.
# v1(8-2) 과 다른 점: 말 목록에서 "보인다" · "보임" · "듯" 을 뺌, 숫자 확신 "확신 · 확률 · % 앞뒤 20자 안 숫자 < 90" 을 (a) · (b) 로 바꿈.
HEDGE_CONF_KEY = "확신"                          # (a) "확신" 뒤 HEDGE_CONF_WIN 자 안에 HEDGE_CONF_LOW 중 하나
HEDGE_CONF_WIN = 10
HEDGE_CONF_LOW = ["낮", "중간", "약하", "없"]
HEDGE_PCT_RE = re.compile(r"(\d+(?:\.\d+)?) ?%")   # (b) 글 어디든 "숫자 %"(숫자와 % 사이 빈칸 0 ~ 1개), 숫자 < HEDGE_PCT_MAX
HEDGE_PCT_MAX = 90
HEDGE_WORDS = ["아마", "추정", "짐작", "것 같", "가능성", "애매", "불확실", "확실하지", "확실치", "단정", "어렵",
               "못 봤", "안 보", "가려", "또는", "혹은", "아니면",      # 짐작 말
               "다른 후보", "대안", "둘 중"]                             # 다른 답 말
# 앱 기록 우선(설계서 8-5 · 8-6) — app_record 칸이 있는 반장만
APP_START_LEAD_MS = 3000     # S1: t_start = 앱 첫 버림 at − 3초(앱 기록기는 3초 간격 미리보기 프레임에서 처음 봄 — 실제로 놓인 때는 그보다 앞)
APP_REVEAL_AFTER_MS = 2000   # S1: t_reveal(추정) = min(앱 마지막 버림 at + 2초, 끝 닻 − 1초)
APP_REVEAL_WIN_S = (-60, 3)  # 공개 시각 창 = 끝 닻 − 60초 ~ + 3초(설계서 8-5 — 닻은 공개보다 6 ~ 43초 늦은 저장 시각)
W5_SPREAD_WARN_MS = 6500     # W5: 판의 시계 차(헤드 − 앱) p90 − p10 이 이보다 크면 질문(boundary). 두 기록기 모두 3초 간격 프레임이라 ±3초 남짓은
                             # 자연스러운 퍼짐(2반장 첫 시험에서 3000 으로 두었더니 9판 중 7판이 3.0 ~ 3.4초로 걸림) → 프레임 두 간격 + 여유
W5_EDGE_MS = 1500            # W5: 헤드 녹화 기록기의 첫 맞은 칸이 덤프 창 첫 프레임(t_from)에서 이만큼 안이면 판 시작이 창 앞에 있다고 보고 질문
# S3 판 시작 창 앞당기기(W5 가 start_at_window_edge 라 한 판): t_from 을 ADV_STEP_S 씩 앞으로 옮기며 그 구간만 겹쳐 보기(c2x)로 훑어
# 강(역할 river) 상자가 ADV_EMPTY_RIVER 개 이하인 프레임(빈 탁자)을 찾는다. 찾으면 그 눈금을 새 t_from 으로 S2(c2x) · S3 play · W5 를 다시.
# 걸음은 덤프 눈금(3초)의 배수라 새 덤프의 눈금이 옛 덤프와 겹친다. 한도: 걸음 ADV_MAX_STEPS 번 · 앞 판 끝(앞 판 끝 닻(헤드 시계) · 앞 판 t_to 중 늦은 쪽)을 넘지 않음 ·
# 한 판 ADV_MAX_ROUNDS 바퀴. 못 찾으면 W5 의 app_start 질문을 그대로 둠.
ADV_STEP_S = 15
ADV_MAX_STEPS = 6
ADV_EMPTY_RIVER = 0
ADV_MAX_ROUNDS = 2
EXE_FALLBACK = HERE / "results" / "han3_1123" / "_bin" / "replay_recorder.exe"   # 기록기 exe 사본 출처(읽기만 — 보호 폴더)


# ------------------------------------------------------------------ 작은 도구
def jl(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def wj(p, o, indent=1):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(o, ensure_ascii=False, indent=indent))


def wt(p, s):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(s.encode("utf-8"))


def rel(p) -> str:
    p = Path(p).resolve()
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def to_ms(date: str, hms: str) -> int:
    hh, mm, ss = hms.split(":")
    sec = float(ss)
    d = datetime(*map(int, date.split("-")), int(hh), int(mm), int(sec), round((sec - int(sec)) * 1e6), tzinfo=KST)
    return round(d.timestamp() * 1000)


def hms_of(ms: int) -> str:
    d = datetime.fromtimestamp(ms / 1000, KST)
    return d.strftime("%H:%M:%S") + f".{d.microsecond // 100000}"


def secs(hms: str) -> float:
    a, b, c = hms.split(":")
    return int(a) * 3600 + int(b) * 60 + float(c)


def norm(t):
    return ("5" + t[1]) if t and t[0] == "0" else t


def run(args, log: Path | None = None, check=True, env=None) -> subprocess.CompletedProcess:
    """하위 프로세스(끝까지 기다림 — 남기지 않음). 표준 출력 · 오류를 log 에."""
    e = dict(os.environ, PYTHONIOENCODING="utf-8")
    if env:
        e.update(env)
    t0 = time.time()
    p = subprocess.run([str(a) for a in args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=e)
    if log:
        wt(log, " ".join(str(a) for a in args) + f"\n# rc {p.returncode} · {time.time() - t0:.1f}s\n" + p.stdout + ("\n--- stderr\n" + p.stderr if p.stderr else ""))
    if check and p.returncode != 0:
        raise SystemExit(f"실패: {' '.join(str(a) for a in args)}\n{p.stdout[-3000:]}\n{p.stderr[-3000:]}")
    return p


class Run:
    """실행 폴더 하나(state.json · hanchan.json · 단계별 결과)."""

    def __init__(self, d: Path):
        self.d = Path(d).resolve()
        self.state_f = self.d / "state.json"
        self.state = jl(self.state_f) if self.state_f.exists() else None

    # 경로
    @property
    def cfg_f(self):
        return self.d / "hanchan.json"

    @property
    def read(self):
        return self.d / "read"

    @property
    def prep(self):
        return self.d / "_prep"

    @property
    def paifu(self):
        return self.d / "paifu"

    def cfg(self):
        return hcfg.load(self.cfg_f)

    def save(self):
        wj(self.state_f, self.state)

    def stage(self, s):
        return self.state["stages"].setdefault(s, {"status": "todo"})

    def done(self, stage_id, **kw):
        st = self.stage(stage_id)
        st.update(kw)
        st["status"] = "done"
        st["done_at"] = now()
        self.save()

    def games(self):
        return list(self.state["game_ids"])

    def log(self, name):
        return self.d / "logs" / name

    # 앱 기록(app_record 칸이 있는 반장 — S0 가 만든 app_rounds.json)
    def app(self):
        f = self.d / "app_rounds.json"
        return jl(f) if f.exists() else None

    def app_round(self, g):
        a = self.app()
        return next((x for x in (a or {}).get("rounds") or [] if x["id"] == g), None)

    def app_events(self, g):
        f = self.d / "app" / g / "paifu_app.json"
        return jl(f)["events"] if f.exists() else None


# ------------------------------------------------------------------ init
def cmd_init(a):
    src_cfg = hcfg.load(a.hanchan)
    rd = Path(a.run).resolve() if a.run else HERE / "results" / f"auto_{src_cfg.id}"
    r = Run(rd)
    if r.state is not None:
        print(f"이미 있음: {rel(r.state_f)} — 그대로 둠(이어 가려면 next)")
        return
    if a.no_sup and a.sup_games:
        raise SystemExit("--no-sup 와 --sup-games 는 같이 못 씀")
    bad_g = [x for x in (a.sup_games or "").split(",") if x and x not in src_cfg.games]
    if bad_g:
        raise SystemExit(f"--sup-games: 반장 설정에 없는 판 {bad_g}")
    rd.mkdir(parents=True, exist_ok=True)
    raw = copy.deepcopy(src_cfg.raw)
    rid = f"auto_{src_cfg.id}" if not a.run else Path(a.run).name
    if rid == src_cfg.id:
        rid += "_run"
    hand = Path(a.hand_settings).resolve() if a.hand_settings else None
    cfg = {"_note": f"paifu_auto.py init 이 {rel(src_cfg.path)} 에서 만든 실행 설정({now()}). results_dir · prep_dir · read_root · 기록기 · 패보 출력만 실행 폴더로 바꿈. "
                    "hand.call_turns · hand.row_at · paifu.event_fix 는 원래 설정 값(설정) — S5 · S6 가 자동 규칙으로 따로 만든 것과 견줌.",
           # rerun_of = 반장 가족(원래 설정이 이미 다른 설정의 다시 돌리기면 그 가족 — 11-25 paifu_setup 자동 설정 · h3_1114 처럼 rerun_of 가 있는 설정에서 init 할 때
           # 실행 설정이 원래 설정 쪽과 겹침 검사 ④ 의 가족이 달라 멈추지 않게). rerun_of 없는 설정(h2_1114 · h3_1123)은 전과 같음(= 그 id)
           "id": rid, "rerun_of": src_cfg.rerun_of or src_cfg.id, "label": raw.get("label", src_cfg.label),
           "results_dir": rel(rd), "prep_dir": rel(rd / "_prep"), "read_root": (rd / "read").as_posix(),
           "recording": raw.get("recording"), "games": list(src_cfg.games), "turn_prefix": dict(src_cfg.turn_prefix),
           "replaces_base": list(src_cfg.replaces_base), "files": dict(raw.get("files") or {}),
           "recorder": {"exe": rel(rd / "_bin" / "replay_recorder.exe"), "sticks": src_cfg.sticks},
           "hand": copy.deepcopy(raw.get("hand") or {}),
           "paifu": {**{k: v for k, v in (raw.get("paifu") or {}).items() if k != "out_dir"}, "out_dir": rel(rd / "paifu")}}
    if not hand:   # 손 설정을 안 쓰면 판에 딸린 손 고침은 비운다(S5 · S6 자동 규칙이 채움)
        cfg["paifu"]["event_fix"] = {}
        cfg["hand"]["call_turns"] = []
    if raw.get("app_record"):   # 앱 기록 우선(설계서 8-5 · 8-6) — 칸이 없는 설정(3반장)은 실행 설정에도 넣지 않음
        cfg["app_record"] = copy.deepcopy(raw["app_record"])
    if raw.get("frame"):        # 녹화 틀(S6a 가 손 설정 없는 판의 판별 설정 영역으로 씀) — 칸이 없는 설정은 넣지 않음
        cfg["frame"] = copy.deepcopy(raw["frame"])
    wj(r.cfg_f, cfg)
    human = {"turns": list(src_cfg.truth_ids), "items": [{"id": x["id"], "kind": x["kind"], "game": x["game"]} for x in src_cfg.items]}
    r.state = {"_note": "paifu_auto.py 상태 — 단계 · 꾸러미 · 다시 읽기 · 질문", "created": now(), "source_cfg": rel(src_cfg.path),
               "game_ids": list(src_cfg.games), "reuse": rel(a.reuse) if a.reuse else None, "verify_dump": a.verify_dump,
               "hand_settings": rel(hand) if hand else None, "src_event_fix": (raw.get("paifu") or {}).get("event_fix") or {},
               "src_call_turns": list((raw.get("hand") or {}).get("call_turns") or []), "human_picked_1123": human,
               "stages": {s: {"status": "todo"} for s in STAGES if s != "S7s" or not a.no_sup}, "reread": {}, "timing": {}, "events": [],
               # 판 supervisor 단계(설계서 8-17 4-①): 기본 켬 · --no-sup 이면 끔(단계 목록에서 빠짐) · --sup-games 는 시험용(그 판들만 supervisor)
               "sup": {"on": not a.no_sup, "games": [x for x in (a.sup_games or "").split(",") if x] or None}}
    if a.s6_games:      # 시험용: S6 칸 틀 검출 · 차례 꾸러미를 이 판들만(차례 목록 · 차례 수 검사는 모든 판)
        r.state["s6_games"] = [x for x in a.s6_games.split(",") if x]
    if a.s6a_rules:     # 견줌용: S6a 를 옛 화소 규칙(handtrack_auto.py conf)으로 — 기본 흐름은 준비 읽기
        r.state["s6a_mode"] = "rules"
    if a.slotgrid_seed:   # 시험용(11-25, 설계서 8-14 끝 조건 4): 칸 틀 검출 캐시를 다른 실행에서 — 그 판의 side · band · sheet_band 가 같을 때만(slotgrid_seed)
        r.state["slotgrid_seed"] = rel(Path(a.slotgrid_seed).resolve())
    r.save()
    r.cfg()   # 겹침 검사
    print(f"→ {rel(r.d)} (state.json · hanchan.json) · 판 {len(r.games())}")


# ------------------------------------------------------------------ 꾸러미
def pkg(stage, pid, folder: Path, task: Path, answer: Path, parallel=True, **kw):
    return {"id": pid, "stage": stage, "dir": folder.as_posix(), "task": task.as_posix(), "answer": answer.as_posix(),
            "model": "opus", "effort": "high", "parallel": parallel, **kw}


def answered(p) -> bool:
    f = Path(p["answer"])
    if not f.exists():
        return False
    try:
        jl(f)
        return True
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False


# ------------------------------------------------------------------ 판 supervisor 단계(S7s) 켜짐 · 단계 목록(설계서 8-17 4-①)
def sup_on(r: Run) -> bool:
    """이 실행에서 S7s 가 켜졌나. init 이 state.sup.on 을 적는다(기본 켬, --no-sup 이면 끔).
    sup 칸이 없는 옛 실행 폴더: S7 이 이미 끝났으면 끔(옛 흐름 그대로 — 끝난 실행을 다시 부를 때 supervisor 가 끼지 않게), 아니면 켬."""
    s = r.state.get("sup")
    if s is not None:
        return bool(s.get("on"))
    return (r.state["stages"].get("S7") or {}).get("status") != "done"


def stage_list(r: Run) -> list:
    return STAGES if sup_on(r) else [s for s in STAGES if s != "S7s"]


def slot_of(a: dict) -> dict:
    """paifu_sup.slot 과 같은 셈(답의 칸 값 — 글 칸은 뺌)."""
    out = {}
    for k in SLOT_KEYS:
        v = a.get(k)
        if k in ("end_order", "gone") and v is not None:
            v = [str(x) for x in v]
        if k in ("k", "j") and v is not None:
            try:
                v = int(v)
            except (TypeError, ValueError):
                pass
        out[k] = v
    return out


def jlines(f: Path) -> list:
    return [json.loads(x) for x in Path(f).read_text(encoding="utf-8").splitlines() if x.strip()] if Path(f).exists() else []


# ------------------------------------------------------------------ S0 준비
def rec_frames(rec_dir: Path) -> list:
    ms = []
    with os.scandir(rec_dir) as it:
        for e in it:
            n = e.name
            if n.startswith("f_") and n.endswith(".jpg"):
                ms.append(int(n[2:-4]))
    ms.sort()
    return ms


def s0(r: Run):
    cfg = r.cfg()
    rc = cfg.recording or {}
    out = {"recs": []}
    for name in rc.get("recs") or []:
        d = hcfg._p(rc["root"]) / name
        ms = rec_frames(d)
        gaps = [(a, b) for a, b in zip(ms, ms[1:]) if b - a > GAP_S * 1000]
        dark = None
        out["recs"].append({"rec": name, "frames": len(ms), "first": hms_of(ms[0]) if ms else None, "last": hms_of(ms[-1]) if ms else None,
                            "fps": round(len(ms) / ((ms[-1] - ms[0]) / 1000), 2) if len(ms) > 1 else None,
                            "gaps_over_30s": [{"from": hms_of(a), "to": hms_of(b), "s": round((b - a) / 1000, 1)} for a, b in gaps],
                            "dark_check": dark})
    out["budget"] = {"tokens_estimate": TOKENS_PER_HANCHAN, "note": "11-23 3반장 손 작업 실측 약 1,500만 토큰(하위 에이전트). 무인은 S4 두 번 읽기 · S7 다시 읽기로 더 들 수 있음. 1단계 재생은 0"}
    out["note"] = "검은 프레임 검사는 1단계에서 안 함(dark_check null)"
    wj(r.d / "s0" / "recording.json", out)
    summary = {x["rec"]: f"{x['frames']}장 · {x['first']} ~ {x['last']} · 30초 넘는 빈 구간 {len(x['gaps_over_30s'])}" for x in out["recs"]}
    if cfg.app_record:
        summary["app_record"] = s0_app(r, cfg)
    r.done("S0", summary=summary)
    return []


def ensure_exe(r: Run):
    """기록기 exe(실행 설정 recorder.exe)가 없으면 --reuse 폴더의 _bin → 3반장 결과 _bin 에서 mtime 째 복사(headrec_run.build 가 다시 빌드하지 않게)."""
    exe = r.cfg().exe
    reuse = hcfg._p(r.state["reuse"]) if r.state.get("reuse") else None
    if not exe.exists():
        for c in ([reuse / "_bin" / "replay_recorder.exe"] if reuse else []) + [EXE_FALLBACK]:
            if c.exists():
                exe.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(c, exe)
                break
    return exe


def s0_app(r: Run, cfg) -> str:
    """W1 · W2(app_record.build): app_rounds.json + app/<판>/paifu_app.json. 경고 · 판 수 어긋남은 questions_s0(boundary)."""
    sys.path.insert(0, str(HERE))
    import app_record as ar
    exe = ensure_exe(r)
    t0 = time.time()
    o = ar.build(jl(r.cfg_f), r.d, exe=exe, exe_candidates=[EXE_FALLBACK], log=lambda s: print(s, flush=True))
    qs = []
    for w in o.get("warnings") or []:
        qs.append({"id": f"app_warn_{len(qs) + 1}", "kind": "boundary", "stage": "S0", "why": w})
    ids = [x["id"] for x in o["rounds"]]
    if ids != r.games():
        qs.append({"id": "app_games", "kind": "boundary", "stage": "S0", "current": {"games": r.games(), "app": ids},
                   "why": "설정 games 와 촬영 기록 판 목록이 다름"})
    for x in o["rounds"]:
        for k, w in enumerate(x.get("warnings") or [], 1):
            qs.append({"id": f"{x['id'][:3]}_app_warn_{k}", "kind": "boundary", "stage": "S0", "game": x["id"], "why": w})
    r.state["questions_s0"] = qs
    st = r.stage("S0")
    st["app"] = {x["id"]: {"round": x["round_label"], "end": x["end"], "dealer": x["dealer"], "bottom": x["bottom_seat"],
                           "result": x["result_source"], "end_folder": x["folders"]["end"], "track": x["folders"]["track"],
                           "discards": x["discard_source"].get("used"), "dropped": [d["folder"] for d in x["folders"]["dropped"]]} for x in o["rounds"]}
    st["app_s"] = round(time.time() - t0, 1)
    r.save()
    c = Counter(x["discard_source"].get("used") for x in o["rounds"])
    return f"앱 판 {len(o['rounds'])} · 화료 {sum(x['end'] == 'win' for x in o['rounds'])} · 유국 {sum(x['end'] == 'draw' for x in o['rounds'])} · 버림 출처 {dict(c)} · 질문 {len(qs)}"


# ------------------------------------------------------------------ S1 판 경계
S1_TASK = """# 반장 판 경계 읽기(헤드 녹화 프레임을 직접 보고 적는다)

녹화 폴더: {recs}
날짜: {date}. 프레임 이름 f_<epoch ms>.jpg 의 시각을 KST 로 바꾸면 그날 시각이다(초당 약 10장).
이 반장의 판 수(설정): {n}판 — 판 id 는 아래 목록을 쓴다(판 시작 시각 HHMMSS 로 지은 이름. 시작 시각이 다르게 보이면 why 에 적고 id 는 그대로).
{ids}

## 할 일
듬성한 프레임(10초 간격)으로 판이 바뀌는 곳을 찾고, 그 근처를 0.3 ~ 1초 간격으로 좁혀 판마다 아래 시각을 적는다(0.1초 단위).
정의: {definitions}

## 답
`{answer}` 한 파일만 쓴다(UTF-8 · LF):
{{"source": "<녹화 폴더>", "rounds": [{{"id", "t_deal_done", "t_start", "t_end_play", "t_reveal", "t_clear",
  "dealer_side": {{"first": "bottom|right|top|left", "first_t": "HH:MM:SS.s"}}, "end": "win|draw", "revealed_sides": [...],
  "win_type": "론|쯔모|null", "win_basis": "근거", "result": "한 줄", "note": "그 밖"}} …]}}
작업 그림은 `{work}` 아래에만 둔다. 다른 판의 결과 · 답 파일 · docs/ · HANDOFF.md 는 열지 않는다.
"""


S1_APP_TASK = """# 반장 판 경계 맞추기(앱 기록이 판 목록을 이미 정함 — 헤드 녹화 프레임을 직접 보고 시각만 적는다)

녹화 폴더: {recs}
날짜: {date}. 프레임 이름 f_<epoch ms>.jpg 의 시각을 KST 로 바꾸면 그날 시각이다(초당 약 10장).
판 수 · 순서 · 국 이름 · 선은 앱 촬영 기록(app_rounds.json)에서 왔다 — **세지 말고, 바꾸지 말 것.** 판 id 는 아래 목록 그대로 쓴다.
앱 시각(닻)은 태블릿 시계라 헤드 녹화 시계와 1초 안팎 다르고, 끝 닻은 화료 · 유국 창 저장 시각이라 공개보다 6 ~ 43초 늦다. 닻은 "근처" 만 가리킨다.

## 판 목록과 창(헤드 녹화 시각으로 찾을 곳)
{table}

## 할 일
판마다 위 창 안에서만 0.3 ~ 1초 간격으로 좁혀 아래 시각을 적는다(0.1초 단위). 창 밖에서 찾았으면 note 에 까닭을 적는다.
정의: {definitions}

## 답
`{answer}` 한 파일만 쓴다(UTF-8 · LF):
{{"source": "<녹화 폴더>", "rounds": [{{"id", "t_deal_done", "t_start", "t_end_play", "t_reveal", "t_clear",
  "dealer_side": {{"first": "bottom|right|top|left", "first_t": "HH:MM:SS.s"}}, "end": "win|draw", "revealed_sides": [...],
  "win_type": "론|쯔모|null", "win_basis": "근거", "result": "한 줄", "note": "그 밖"}} …]}}
작업 그림은 `{work}` 아래에만 둔다. 다른 판의 결과 · 답 파일 · docs/ · HANDOFF.md 는 열지 않는다.
"""


def s1_app(r: Run):
    """앱 기록이 있는 반장의 S1. 판마다 앱 버림 at 이 있으면 코드로 판 경계를 정하고(꾸러미 없음),
    하나라도 없으면 판 목록 · 국 이름 · 창을 담은 꾸러미(S1_APP_TASK)를 낸다. 돌려주는 것: 꾸러미 목록([] = 끝)."""
    cfg = r.cfg()
    date = cfg.recording["date"]
    d = r.d / "s1"
    ans = d / "answer.json"
    rows, lst, missing_at, track_win = [], [], [], []
    prev_end = None
    for g in r.games():
        a = r.app_round(g)
        sm = ((a or {}).get("discard_source") or {}).get("summary") or {}
        end_ms = to_ms(date, a["anchors"]["end"]) if a and a["anchors"].get("end") else None
        win = {"reveal": [hms_of(end_ms + APP_REVEAL_WIN_S[0] * 1000), hms_of(end_ms + APP_REVEAL_WIN_S[1] * 1000)] if end_ms else None,
               "start": [hms_of(prev_end) if prev_end else None, hms_of(sm["first_at_ms"]) if sm.get("first_at_ms") else None]}
        rows.append((g, a, win))
        how = "app"
        if not (a and sm.get("has_at")):
            # 8-12 (나): 앱 버림에 시각이 없는 판(빈 기록) — 추적 프레임의 처음 · 끝 시각과 끝 닻으로 판 구간을 코드로. 추적도 없을 때만 꾸러미
            tfa, tla = (a or {}).get("anchors", {}).get("track_first"), (a or {}).get("anchors", {}).get("track_last")
            if a and tfa and tla:
                how = "track"
                track_win.append(g)
            else:
                missing_at.append(g)
        if how == "track" or g not in missing_at:
            first, last = (sm["first_at_ms"], sm["last_at_ms"]) if how == "app" else (to_ms(date, tfa), to_ms(date, tla))
            t_rev = last + APP_REVEAL_AFTER_MS if end_ms is None else min(last + APP_REVEAL_AFTER_MS, end_ms - 1000)
            t_rev = max(t_rev, last + 300)
            res = a.get("result") or {}
            lst.append({"id": g, "t_deal_done": None, "t_start": hms_of(first - APP_START_LEAD_MS), "t_end_play": hms_of(last), "t_reveal": hms_of(t_rev),
                        "t_clear": None, "dealer_side": {"first": a["dealer_side"], "first_t": hms_of(first)}, "end": a["end"],
                        "revealed_sides": (res.get("tenpai_sides") or []) if a["end"] == "draw" else ([SIDES[(res["winner"] - a["bottom_seat"]) % 4]] if res.get("winner") is not None else []),
                        "win_type": {"ron": "론", "tsumo": "쯔모"}.get(res.get("type")), "win_basis": f"앱 {a.get('result_source')} {a['folders']['end']}",
                        "result": f"{a['round_label']} {a['end']}", "windows": win,
                        "source": "app_record(코드, LLM 0)" if how == "app" else "app_record 추적 프레임 시각(코드, LLM 0 — 앱 버림에 시각 없음)",
                        "note": (f"앱 닻(태블릿 시계): 첫 버림 at {hms_of(first)} · 마지막 버림 at {hms_of(last)} · 끝 폴더 {a['anchors'].get('end')}. "
                                 f"t_start = 첫 버림 at − {APP_START_LEAD_MS / 1000:g}초, t_reveal = min(마지막 버림 at + {APP_REVEAL_AFTER_MS / 1000:g}초, 끝 닻 − 1초)(추정)")
                                if how == "app" else
                                (f"앱 버림에 시각이 없음(빈 기록) — 추적 프레임 처음 {hms_of(first)} · 끝 {hms_of(last)} · 끝 폴더 {a['anchors'].get('end')}. "
                                 f"t_start = 추적 첫 프레임 − {APP_START_LEAD_MS / 1000:g}초, t_end_play = 추적 끝 프레임, t_reveal = min(추적 끝 + {APP_REVEAL_AFTER_MS / 1000:g}초, 끝 닻 − 1초)(추정)")})
        prev_end = end_ms
    qs = []
    if missing_at:
        # 앱 버림에 at 이 없는 판이 있음 → 판 목록 · 창을 담은 꾸러미(설계서 8-5 S1)
        if not ans.exists():
            rc = cfg.recording or {}
            defs = jl(HERE / "results" / "han3_1123" / "rounds_p.json").get("definitions", "")
            table = "\n".join(f"- `{g}` {a['round_label'] if a else '?'} · 선 {a['dealer_side'] if a else '?'} · 끝 {a['end'] if a else '?'}"
                              f" · 공개 시각 창 {win['reveal']} · 시작 시각 창(앞 판 끝 닻 ~ 이 판 첫 버림 at) {win['start']}" for g, a, win in rows)
            task = S1_APP_TASK.format(recs=", ".join(str(hcfg._p(rc.get("root", "")) / x) for x in rc.get("recs") or []), date=date, table=table,
                                      definitions=defs, answer=ans.as_posix(), work=(d / "work").as_posix())
            wt(d / "TASK.md", task)
            return [pkg("S1", "s1_rounds", d, d / "TASK.md", ans, parallel=False, app_rounds=len(rows), missing_at=missing_at)]
        lst = [x for x in jl(ans).get("rounds") or [] if x.get("id") in r.games()]
        src = "꾸러미 답(S1_APP_TASK)"
    else:
        src = "코드(앱 버림 at · 끝 닻)"
    rounds = {x["id"]: x for x in lst}
    missing = [g for g in r.games() if g not in rounds]
    if missing:
        qs.append({"id": "s1_rounds", "kind": "boundary", "stage": "S1", "current": {"missing": missing}, "why": "판 경계가 없는 판"})
    for g in track_win:
        qs.append({"id": f"s1_{g}_track_window", "kind": "boundary", "stage": "S1", "game": g, "current": {k: rounds[g].get(k) for k in ("t_start", "t_end_play", "t_reveal")} if g in rounds else None,
                   "why": "앱 버림에 시각이 없어(빈 기록) 판 구간을 추적 프레임 처음 · 끝 시각으로 잡음 — 판 시작 · 끝이 실제보다 넓거나 좁을 수 있음"})
    sys.path.insert(0, str(HERE))
    import headrec_dump as hd
    lst = [rounds[g] for g in r.games() if g in rounds]
    defs = hd.from_rounds_list(lst)
    order_ok = all(secs(defs[a]["t_start"]) < secs(defs[b]["t_start"]) for a, b in zip(r.games(), r.games()[1:]) if a in defs and b in defs)
    if not order_ok:
        qs.append({"id": "s1_order", "kind": "boundary", "stage": "S1", "why": "판 시작 시각이 games 순서와 다름"})
    rec = jl(r.d / "s0" / "recording.json")
    for x in rec["recs"]:
        for gp in x["gaps_over_30s"]:
            for g, dd in defs.items():
                if secs(gp["from"]) < secs(dd["t_to"]) and secs(gp["to"]) > secs(dd["t_from"]):
                    qs.append({"id": f"s1_{g}_gap", "kind": "boundary", "stage": "S1", "game": g, "why": f"녹화가 판 중간에 끊김 {gp}"})
        if x.get("first") and x.get("last"):
            for g, dd in defs.items():
                if secs(dd["t_from"]) < secs(x["first"]) - 1 or secs(dd["t_to"]) > secs(x["last"]) + 1:
                    if len(rec["recs"]) == 1:
                        qs.append({"id": f"s1_{g}_outside", "kind": "boundary", "stage": "S1", "game": g,
                                   "why": f"판 구간 {dd['t_from']} ~ {dd['t_to']} 이 녹화 {x['first']} ~ {x['last']} 밖"})
    wj(r.d / "rounds_defs.json", {"_note": f"S1 판 경계({src}) → headrec_dump.from_rounds_list(t_from = t_start − 15초, t_to = t_reveal − 0.3초)", **defs})
    wj(r.d / "s1" / "rounds.json", {"rounds": lst, "source": src})
    r.state["questions_s1"] = qs
    r.done("S1", games=len(defs), questions=len(qs), source=src)
    return []


def s1(r: Run):
    cfg = r.cfg()
    if cfg.app_record and r.app():
        return s1_app(r)
    d = r.d / "s1"
    ans = d / "answer.json"
    if not ans.exists():
        rc = cfg.recording or {}
        defs = jl(HERE / "results" / "han3_1123" / "rounds_p.json").get("definitions", "")
        task = S1_TASK.format(recs=", ".join(str(hcfg._p(rc.get("root", "")) / x) for x in rc.get("recs") or []), date=rc.get("date"),
                              n=len(r.games()), ids="\n".join(f"- {g}" for g in r.games()), definitions=defs,
                              answer=ans.as_posix(), work=(d / "work").as_posix())
        wt(d / "TASK.md", task)
        return [pkg("S1", "s1_rounds", d, d / "TASK.md", ans, parallel=False)]
    a = jl(ans)
    rounds = {x["id"]: x for x in a.get("rounds") or []}
    qs = []
    missing = [g for g in r.games() if g not in rounds]
    extra = [g for g in rounds if g not in r.games()]
    if missing or extra:
        qs.append({"id": "s1_rounds", "kind": "boundary", "stage": "S1", "current": {"missing": missing, "extra": extra},
                   "why": "판 경계 읽기의 판 목록이 설정 games 와 다름"})
    # 판 정의(headrec_dump 꼴) — t_from = t_start − 15초, t_to = t_reveal − 0.3초
    sys.path.insert(0, str(HERE))
    import headrec_dump as hd
    lst = [rounds[g] for g in r.games() if g in rounds]
    defs = hd.from_rounds_list(lst)
    for g in r.games():
        if g in defs and not rounds[g].get("t_reveal"):
            qs.append({"id": f"s1_{g}_reveal", "kind": "boundary", "stage": "S1", "game": g, "why": "공개 시각을 못 찾음"})
    order_ok = all(secs(defs[a]["t_start"]) < secs(defs[b]["t_start"]) for a, b in zip(r.games(), r.games()[1:]) if a in defs and b in defs)
    if not order_ok:
        qs.append({"id": "s1_order", "kind": "boundary", "stage": "S1", "why": "판 시작 시각이 games 순서와 다름"})
    # 녹화 빈 구간이 판에 걸리는지
    rec = jl(r.d / "s0" / "recording.json")
    for x in rec["recs"]:
        for gp in x["gaps_over_30s"]:
            for g, dd in defs.items():
                if secs(gp["from"]) < secs(dd["t_to"]) and secs(gp["to"]) > secs(dd["t_from"]):
                    qs.append({"id": f"s1_{g}_gap", "kind": "boundary", "stage": "S1", "game": g, "why": f"녹화가 판 중간에 끊김 {gp}"})
    wj(r.d / "rounds_defs.json", {"_note": "S1 판 경계 → headrec_dump.from_rounds_list(t_from = t_start − 15초, t_to = t_reveal − 0.3초)", **defs})
    wj(r.d / "s1" / "rounds.json", {"rounds": lst})
    r.state["questions_s1"] = qs
    r.done("S1", games=len(defs), questions=len(qs))
    return []


# ------------------------------------------------------------------ S2 프레임
DUMP_FILES = ["overlay_dump_c2x.json", "reveal_overlay_c2x.json"]


def dump_tiles(p) -> list:
    """겹쳐 보기 dump 에서 시간 · 실행 정보를 뺀 내용(프레임 · 상자 · 종류)."""
    o = jl(p)
    return [(f["file"], f["at"], [(t.get("b"), t.get("t"), t.get("tc"), t.get("t2"), t.get("tc2"), t.get("r")) for t in f["tiles"]]) for f in o["frames"]]


def s2(r: Run):
    cfg = r.cfg()
    st = r.stage("S2")
    reuse = hcfg._p(r.state["reuse"]) if r.state.get("reuse") else None
    defs = jl(r.d / "rounds_defs.json")
    got = {}
    t0 = time.time()
    for g in r.games():
        od = r.d / g
        od.mkdir(parents=True, exist_ok=True)
        if reuse:
            sd = reuse / g
            for f in DUMP_FILES:
                if (sd / f).exists() and not (od / f).exists():
                    shutil.copyfile(sd / f, od / f)
            # 복사본의 판 정의가 S1 판 정의와 같은지
            dd = jl(od / "overlay_dump_c2x.json")["def"]
            same = {k: dd.get(k) for k in ("t_from", "t_to")} == {k: defs[g].get(k) for k in ("t_from", "t_to")}
            got[g] = {"how": f"복사 {rel(sd)}", "def_same_as_S1": same}
        else:
            for mode in ("c2x", "reveal_c2x"):
                run([PY, "-X", "utf8", HERE / "headrec_dump.py", "dump", r.d / "rounds_defs.json", g, "--mode", mode, "--hanchan", r.cfg_f],
                    log=r.log(f"s2_dump_{g}_{mode}.log"))
            got[g] = {"how": "headrec_dump.py 로 뽑음"}
    st["copy_s"] = round(time.time() - t0, 1)
    vg = r.state.get("verify_dump")
    if reuse and vg and not st.get("verify"):
        vd = r.d / "_verify"
        t1 = time.time()
        res = {}
        for mode, f in (("c2x", "overlay_dump_c2x.json"), ("reveal_c2x", "reveal_overlay_c2x.json")):
            run([PY, "-X", "utf8", HERE / "headrec_dump.py", "dump", r.d / "rounds_defs.json", vg, "--mode", mode, "--hanchan", r.cfg_f,
                 "--out", vd], log=r.log(f"s2_verify_{vg}_{mode}.log"))
            a, b = dump_tiles(vd / vg / f), dump_tiles(r.d / vg / f)
            nb = sum(len(x[2]) for x in b)
            same_frames = sum(1 for x, y in zip(a, b) if x == y)
            res[f] = {"frames_new": len(a), "frames_copy": len(b), "frames_same": same_frames, "boxes_copy": nb, "all_same": a == b}
        st["verify"] = {"game": vg, "s": round(time.time() - t1, 1), **res}
        r.save()
    r.done("S2", games=got)
    return []


# ------------------------------------------------------------------ S3 버림 기록
def s3(r: Run):
    cfg = r.cfg()
    exe = cfg.exe
    reuse = hcfg._p(r.state["reuse"]) if r.state.get("reuse") else None
    src_exe = (reuse / "_bin" / "replay_recorder.exe") if reuse else None
    if not exe.exists():
        exe.parent.mkdir(parents=True, exist_ok=True)
        if src_exe and src_exe.exists():
            shutil.copy2(src_exe, exe)        # mtime 도 옮김 — headrec_run.build 가 소스보다 새로우면 다시 빌드 안 함
    t0 = time.time()
    bottom = "0"
    if cfg.app_record and r.app():   # 앱 기록 우선: 패보 자리 번호를 앱과 같게(헤드 녹화 쪽 이름 = 태블릿 쪽 이름 — 같은 화각, headrec_run.val 이 그대로 견줌)
        bs = sorted({x["bottom_seat"] for x in r.app()["rounds"] if x["id"] in r.games()})
        bottom = str(bs[0]) if bs else "0"
        if len(bs) > 1:
            r.state.setdefault("questions_w5", []).append({"id": "app_bottom", "kind": "boundary", "stage": "S3",
                                                          "why": f"판마다 아래 자리가 다름 {bs} — 헤드 녹화 기록기는 {bottom} 하나로 돌림"})
    run([PY, "-X", "utf8", HERE / "headrec_run.py", "play", "C", *r.games(), "--defs", r.d / "rounds_defs.json", "--bottom-seat", bottom,
         "--hanchan", r.cfg_f], log=r.log("s3_play_C.log"))
    cmp = {}
    if reuse:   # 재생 시험: 기존 출력과 같은가
        for g in r.games():
            row = {}
            for f in ("dart_overlay.json", "dart_overlay_timeline.json", "paifu_rec.json"):
                a, b = r.d / g / f, reuse / g / f
                if not (a.exists() and b.exists()):
                    row[f] = None
                elif f == "paifu_rec.json":   # 기록기가 id 칸에 겹쳐 보기 파일 경로를 적음 — 경로만 다르면 같음으로
                    ja, jb = jl(a), jl(b)
                    row[f] = "같음(id 경로만 다름)" if {**ja, "id": None} == {**jb, "id": None} else False
                else:
                    row[f] = sha(a) == sha(b)
            cmp[g] = row
    kw = {}
    if cfg.app_record and r.app():
        kw["w5_first"] = w5_align(r)
        adv = advance_windows(r, bottom)
        kw["advance"] = adv
        kw["w5"] = jl(r.d / "w5" / "align.json")["total"] if adv else kw["w5_first"]
    r.done("S3", s=round(time.time() - t0, 1), same_as_reuse=cmp, **kw)
    return []


def hms3(ms: int) -> str:
    d = datetime.fromtimestamp(ms / 1000, KST)
    return d.strftime("%H:%M:%S") + f".{d.microsecond // 1000:03d}"


def advance_windows(r: Run, bottom: str) -> dict:
    """W5 가 "헤드 녹화 기록기가 덤프 창 첫 프레임부터 강을 본다"(start_at_window_edge) 고 한 판의 덤프 창 시작(t_from)을 앞당긴다(위 ADV_* 규칙).
    빈 탁자 눈금을 찾으면 rounds_defs.json 의 t_from 을 바꾸고(옛 값은 t_from_before_advance), 그 판의 S2 c2x 덤프(--force) · S3 play C 를 다시 돌린 뒤
    W5 를 다시 맞춘다. 판마다 결과(걸음 · 강 상자 수 · 새 t_from · 질문 전후)를 돌려준다. 고친 판이 없으면 {}."""
    cfg = r.cfg()
    date = cfg.recording["date"]
    out = {}
    for rnd in range(1, ADV_MAX_ROUNDS + 1):
        w5 = jl(r.d / "w5" / "align.json")
        edge = [g for g in r.games() if (w5["rounds"].get(g) or {}).get("start_at_window_edge")
                and (out.get(g) or {}).get("status") not in ("못 찾음", "한도")]
        if not edge:
            break
        defs = jl(r.d / "rounds_defs.json")
        redo = []
        for g in edge:
            o = out.setdefault(g, {"rounds": [], "question_before": [q["id"] for q in r.state.get("questions_w5") or [] if q.get("game") == g]})
            k = r.games().index(g)
            cur = to_ms(date, defs[g]["t_from"])
            bound = None
            if k > 0:
                pg = r.games()[k - 1]
                pa = r.app_round(pg)
                poff = ((w5["rounds"].get(pg) or {}).get("clock") or {}).get("median_ms") or 0
                cands = [to_ms(date, defs[pg]["t_to"])] if defs.get(pg, {}).get("t_to") else []
                if pa and pa["anchors"].get("end"):
                    cands.append(to_ms(date, pa["anchors"]["end"]) + poff)
                bound = max(cands) if cands else None
            else:
                rec = jl(r.d / "s0" / "recording.json")["recs"]
                bound = to_ms(date, rec[0]["first"]) if rec and rec[0].get("first") else None
            row = {"round": rnd, "t_from_was": defs[g]["t_from"], "bound": hms3(bound) if bound else None, "steps": []}
            found = None
            for step in range(1, ADV_MAX_STEPS + 1):
                a0 = cur - ADV_STEP_S * 1000
                if bound is not None and a0 < bound:
                    row["stop"] = f"앞 판 끝 {hms3(bound)} 을 넘음"
                    break
                pd = r.d / "_advance" / g / f"r{rnd}_s{step}"
                pf = pd / "probe_defs.json"
                wj(pf, {g: {"t_from": hms3(a0), "t_to": hms3(cur - 100), "note": "판 시작 창 앞당기기 훑기(paifu_auto advance_windows)"}})
                run([PY, "-X", "utf8", HERE / "headrec_dump.py", "dump", pf, g, "--mode", "c2x", "--hanchan", r.cfg_f, "--out", pd, "--force"],
                    log=r.log(f"s3_advance_{g}_r{rnd}_s{step}.log"))
                fr = jl(pd / g / "overlay_dump_c2x.json")["frames"]
                rv = [(f["tick"], sum(1 for t in f["tiles"] if t.get("r") == "river")) for f in fr]
                row["steps"].append({"from": hms3(a0), "to": hms3(cur - 100), "river": [x[1] for x in rv]})
                empty = [tk for tk, n in rv if n <= ADV_EMPTY_RIVER]
                if empty:
                    found = to_ms(date, empty[-1][11:23])   # 빈 탁자 중 가장 늦은 눈금(판 시작 바로 앞)
                    break
                cur = a0
            else:
                row["stop"] = f"걸음 {ADV_MAX_STEPS}번 한도"
            o["rounds"].append(row)
            if found is None:
                o["status"] = "못 찾음" if "앞 판" in (row.get("stop") or "") else "한도"
                continue
            row["t_from_new"] = hms3(found)
            d = defs[g]
            d.setdefault("t_from_before_advance", d["t_from"])
            d["t_from"] = hms3(found)
            d["advance_note"] = (f"paifu_auto S3 판 시작 창 앞당기기: {d['t_from_before_advance']} → {d['t_from']}(빈 탁자 눈금 — 강 상자 ≤ {ADV_EMPTY_RIVER}, "
                                 f"걸음 {ADV_STEP_S}초 · 한도 {ADV_MAX_STEPS}번 · 앞 판 끝 {row['bound']})")
            o["status"] = "앞당김"
            redo.append(g)
        if not redo:
            continue
        wj(r.d / "rounds_defs.json", defs)
        for g in redo:
            od = r.d / g
            keep = od / "overlay_dump_c2x_before_advance.json"
            if not keep.exists():
                shutil.copyfile(od / "overlay_dump_c2x.json", keep)
            t1 = time.time()
            run([PY, "-X", "utf8", HERE / "headrec_dump.py", "dump", r.d / "rounds_defs.json", g, "--mode", "c2x", "--hanchan", r.cfg_f, "--force"],
                log=r.log(f"s2_dump_{g}_c2x_advance_r{rnd}.log"))
            for sub in ("rec_app_dealer",):   # W5 가 다시 만들게(있으면 옛 덤프로 돈 것)
                if (od / sub).exists():
                    shutil.rmtree(od / sub)
            run([PY, "-X", "utf8", HERE / "headrec_run.py", "play", "C", g, "--defs", r.d / "rounds_defs.json", "--bottom-seat", bottom,
                 "--hanchan", r.cfg_f], log=r.log(f"s3_play_C_{g}_advance_r{rnd}.log"))
            out[g]["rounds"][-1]["redo_s"] = round(time.time() - t1, 1)
        w5_align(r)
    if out:
        w5 = jl(r.d / "w5" / "align.json")
        for g, o in out.items():
            row = w5["rounds"].get(g) or {}
            o["question_after"] = [q["id"] for q in r.state.get("questions_w5") or [] if q.get("game") == g]
            o["head_first_after"] = (row.get("head_interval") or {}).get("first")
            o["t_from_after"] = jl(r.d / "rounds_defs.json")[g]["t_from"]
            o["still_edge"] = bool(row.get("start_at_window_edge"))
        wj(r.d / "s3" / "advance.json", {"_note": advance_windows.__doc__, **out})
    return out


# ------------------------------------------------------------------ W5 영상 구간 맞추기(앱 기록 우선)
def _pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def _spread(xs):
    if not xs:
        return {"n": 0}
    md = _pct(xs, 0.5)
    return {"n": len(xs), "median_ms": round(md), "p10_ms": round(_pct(xs, 0.1)), "p90_ms": round(_pct(xs, 0.9)),
            "min_ms": min(xs), "max_ms": max(xs), "mad_ms": round(_pct([abs(x - md) for x in xs], 0.5))}


def w5_align(r: Run) -> dict:
    """W5(설계서 8-6): 판마다 헤드 녹화 기록기(S3 — <판>/paifu_rec.json, 헤드 폰 시계) 버림 ↔ 앱 버림(S0 W2 — app/<판>/paifu_app.json, 태블릿 시계)을
    자리마다 패 줄로 맞춘다(difflib, 패 코드 그대로 — 적5 ↔ 5 도 다름). 같은 칸마다 (헤드 at − 앱 at) → 판 · 반장 시계 차(중앙값 · p10 · p90 · MAD).
    둘이 다른 칸 = record 질문(지금 답 = 앱 패, 후보 = 헤드 녹화 기록기 패 — 패 종류는 앱 기록을 따름). 울기 · 리치 자리도 견줌.
    기록기 선(S3 play 가 처음 본 자리로 고름) ≠ 앱 선이면 앱 선으로 다시 돌려(<판>/rec_app_dealer/) 그것을 맞춤.
    판 구간(헤드 녹화 시계) = 맞은 칸의 헤드 at 처음 · 끝. 시계 차는 두 기록기의 늦음 차(3초 간격 프레임)도 섞인 값이다."""
    cfg = r.cfg()
    date = cfg.recording["date"]
    sys.path.insert(0, str(HERE))
    import headrec_run as hr
    hr.use_hanchan(str(r.cfg_f))
    defs = jl(r.d / "rounds_defs.json")
    out = {"_note": w5_align.__doc__, "rounds": {}}
    qs = [q for q in r.state.get("questions_w5") or [] if q.get("id") == "app_bottom"]
    pooled = []
    for g in r.games():
        a = r.app_round(g)
        ev = r.app_events(g)
        row = {"app_round": (a or {}).get("round_label"), "app_dealer": (a or {}).get("dealer")}
        if not a or not ev:
            row["skip"] = "앱 버림 기록 없음(③ 헤드 녹화만)"
            out["rounds"][g] = row
            continue
        bottom = a["bottom_seat"]
        hp_f = r.d / g / "paifu_rec.json"
        hp = jl(hp_f)
        row["rec_dealer"] = hp.get("dealer")
        used = "paifu_rec.json(S3 play C)"
        if hp.get("dealer") != a["dealer"]:
            od = r.d / g / "rec_app_dealer"
            if not (od / "paifu_rec.json").exists():
                hr.replay("overlay", r.d / g / "overlay_dump_c2x.json", a["dealer_side"], od, [], paifu_bottom=bottom)
            hp = jl(od / "paifu_rec.json")
            used = f"rec_app_dealer/paifu_rec.json(기록기 선 {row['rec_dealer']} ≠ 앱 선 {a['dealer']} → 앱 선 {a['dealer_side']} 로 다시)"
        row["head_used"] = used
        dts, cells, diffs = [], 0, []
        h_first, h_last = None, None
        for seat in range(4):
            side = SIDES[(seat - bottom) % 4]
            A = [e for e in ev if e["type"] == "discard" and e["seat"] == seat]
            H = [e for e in hp["events"] if e["type"] == "discard" and e["seat"] == seat]
            sm = difflib.SequenceMatcher(None, [e["tile"] for e in A], [e["tile"] for e in H], autojunk=False)
            cells += len(A)
            for tag, a0, a1, b0, b1 in sm.get_opcodes():
                if tag == "equal":
                    for k in range(a1 - a0):
                        x, y = A[a0 + k], H[b0 + k]
                        if x.get("at") is not None and y.get("at") is not None:
                            dts.append(y["at"] - x["at"])
                            h_first = y["at"] if h_first is None else min(h_first, y["at"])
                            h_last = y["at"] if h_last is None else max(h_last, y["at"])
                    continue
                diffs.append({"seat": seat, "side": side, "tag": tag, "app": [e["tile"] for e in A[a0:a1]], "head": [e["tile"] for e in H[b0:b1]],
                              "app_index": [a0 + 1, a1], "head_index": [b0 + 1, b1],
                              "app_at": [hms_of(e["at"]) for e in A[a0:a1] if e.get("at")], "head_at": [hms_of(e["at"]) for e in H[b0:b1] if e.get("at")]})
        ca = sorted((e["seat"], e.get("from"), tuple(sorted(norm(t) for t in e.get("tiles") or []))) for e in ev if e["type"] == "call")
        ch = sorted((e["seat"], e.get("from"), tuple(sorted(norm(t) for t in e.get("tiles") or []))) for e in hp["events"] if e["type"] == "call")
        ra = sorted({e["seat"] for e in ev if e["type"] == "discard" and e.get("riichi")})
        rh = sorted({e["seat"] for e in hp["events"] if e["type"] == "discard" and e.get("riichi")})
        sp = _spread(dts)
        pooled += dts
        app_ats = [e["at"] for e in ev if e["type"] == "discard" and e.get("at") is not None]
        off = sp.get("median_ms") or 0
        row.update(cells_app=cells, cells_head=sum(1 for e in hp["events"] if e["type"] == "discard"), matched=len(dts), diff_cells=sum(max(len(x["app"]), len(x["head"])) for x in diffs),
                   diffs=diffs, clock=sp, calls_same=ca == ch, calls={"app": ca, "head": ch} if ca != ch else None, riichi_same=ra == rh,
                   riichi={"app": ra, "head": rh} if ra != rh else None,
                   head_interval={"first": hms_of(h_first) if h_first else None, "last": hms_of(h_last) if h_last else None},
                   app_interval_in_head_clock={"first": hms_of(min(app_ats) + off) if app_ats else None, "last": hms_of(max(app_ats) + off) if app_ats else None},
                   s1={k: defs.get(g, {}).get(k) for k in ("t_start", "t_end_play", "t_reveal", "t_from", "t_to")})
        if h_first and defs.get(g, {}).get("t_start"):
            row["s1_delta_s"] = {"t_start_vs_head_first": round((to_ms(date, defs[g]["t_start"]) - h_first) / 1000, 1),
                                 "t_end_play_vs_head_last": round((to_ms(date, defs[g]["t_end_play"]) - h_last) / 1000, 1) if defs[g].get("t_end_play") else None}
        if a["anchors"].get("end"):
            e = to_ms(date, a["anchors"]["end"]) + off
            row["end_anchor_head"] = hms_of(e)
            row["reveal_window_head"] = [hms_of(e + APP_REVEAL_WIN_S[0] * 1000), hms_of(e + APP_REVEAL_WIN_S[1] * 1000)]
        pre = cfg.prefix_of(g)
        for x in diffs:
            n = f"{x['app_index'][0]}" if x["app"] else f"h{x['head_index'][0]}"
            t = (x["head_at"] or x["app_at"] or [None])[0]
            clip = None
            if t:
                tm = to_ms(date, t) + (0 if x["head_at"] else off)
                clip = {"t0": hms_of(tm - 5000), "t1": hms_of(tm + 10000)}
            qs.append({"id": f"{pre}_app_{x['side']}_{n}", "kind": "record", "stage": "S3", "game": g, "current": x["app"] or None,
                       "candidates": [x["head"] or "없음"], "why": f"W5: 앱 버림 기록({x['side']} {x['app_index'][0]} ~ {x['app_index'][1] - 1 if x['app'] else '—'}번째 {x['app']})과 "
                                                                   f"헤드 녹화 기록기({x['head']})가 다름({x['tag']}) — 패보는 앱 기록을 따름",
                       "clip": clip, "covered_by_setting": False, "impact_summary": {"max_hand_turns": 0, "result_changed": False, "river_cells": max(len(x["app"]), len(x["head"])), "zero": False}})
        if ca != ch:
            qs.append({"id": f"{pre}_app_calls", "kind": "record", "stage": "S3", "game": g, "current": ca, "candidates": [ch],
                       "why": "W5: 울기(자리 · 준 자리 · 패)가 앱 기록과 헤드 녹화 기록기에서 다름 — 패보는 앱 기록을 따름", "covered_by_setting": False})
        if ra != rh:
            qs.append({"id": f"{pre}_app_riichi", "kind": "record", "stage": "S3", "game": g, "current": ra, "candidates": [rh],
                       "why": "W5: 리치 표시 자리가 앱 기록과 헤드 녹화 기록기에서 다름 — 패보는 앱 기록을 따름", "covered_by_setting": False})
        if h_first and defs.get(g, {}).get("t_from") and h_first - to_ms(date, defs[g]["t_from"]) <= W5_EDGE_MS:
            row["start_at_window_edge"] = True
            qs.append({"id": f"{pre}_app_start", "kind": "boundary", "stage": "S3", "game": g, "current": {"t_from": defs[g]["t_from"], "head_first": hms_of(h_first)},
                       "why": f"W5: 헤드 녹화 기록기가 덤프 창 첫 프레임({defs[g]['t_from']})부터 이미 강을 봄 — 판 시작이 창 앞에 있다(앱 첫 버림 at 이 늦음: "
                              f"추적이 판 중간에 시작됐을 수 있음). 앞 버림을 놓쳤을 수 있으니 t_start 를 앞당겨 S2 를 다시 돌릴지 확인", "covered_by_setting": False})
        if sp.get("n") and sp["p90_ms"] - sp["p10_ms"] > W5_SPREAD_WARN_MS:
            qs.append({"id": f"{pre}_app_clock", "kind": "boundary", "stage": "S3", "game": g, "current": sp,
                       "why": f"W5: 시계 차 퍼짐(p90 − p10) {sp['p90_ms'] - sp['p10_ms']}ms > {W5_SPREAD_WARN_MS}ms — 판 구간 · 맞춤 확인"})
        out["rounds"][g] = row
    out["clock"] = {"pooled": _spread(pooled), "sign": "헤드 녹화 기록기 at − 앱 기록기 at(ms). 양수 = 헤드 쪽이 늦게 봄(시계 차 + 두 기록기 늦음 차)"}
    ref = (cfg.app_record or {}).get("clock_ref")
    if ref:
        out["clock"]["ref"] = ref
        if pooled:
            out["clock"]["minus_ref_ms"] = round(_pct(pooled, 0.5) - ref["offset_ms"])
    # 다른 판 시각 자료와 견줌(설정 app_record.check_windows: 판 → headrec_rounds.json 키 — val_* 는 태블릿 추적 프레임 첫 · 끝 시각)
    cw = (cfg.app_record or {}).get("check_windows") or {}
    if cw:
        hrr = jl(HERE / "headrec_rounds.json")
        chk = {}
        for g, key in cw.items():
            v = hrr.get(key) or {}
            row = out["rounds"].get(g) or {}
            hi = row.get("head_interval") or {}
            if v and hi.get("first"):
                inside = secs(v["t_from"]) <= secs(hi["first"]) and secs(hi["last"]) <= secs(v["t_to"]) + 4
                chk[g] = {"key": key, "window": [v["t_from"], v["t_to"]], "head_interval": [hi["first"], hi["last"]], "inside": inside,
                          "first_minus_window_start_s": round(secs(hi["first"]) - secs(v["t_from"]), 1), "window_end_minus_last_s": round(secs(v["t_to"]) - secs(hi["last"]), 1)}
                # 같은 판을 val 창으로 돌린 헤드 녹화 기록기(results/han3_1123/val_<키>/rec_C) 와도 견줌(읽기만)
                vf = HERE / "results" / "han3_1123" / key / "rec_C" / "paifu_rec.json"
                if vf.exists():
                    vp = jl(vf)
                    hp = jl(r.d / g / ("rec_app_dealer" if "rec_app_dealer" in (row.get("head_used") or "") else "") / "paifu_rec.json")
                    same = [[e["tile"] for e in vp["events"] if e["type"] == "discard" and e["seat"] == s] == [e["tile"] for e in hp["events"] if e["type"] == "discard" and e["seat"] == s] for s in range(4)]
                    chk[g]["val_rec_C_same_rivers"] = all(same)
                    chk[g]["val_rec_C_per_seat_same"] = same
        out["check_windows"] = chk
    tot = {"rounds": sum(1 for v in out["rounds"].values() if "matched" in v), "matched": sum(v.get("matched", 0) for v in out["rounds"].values()),
           "cells_app": sum(v.get("cells_app", 0) for v in out["rounds"].values()), "diff_cells": sum(v.get("diff_cells", 0) for v in out["rounds"].values()),
           "questions": len(qs)}
    out["total"] = tot
    wj(r.d / "w5" / "align.json", out)
    wt(r.d / "w5_questions.jsonl", "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in qs))
    r.state["questions_w5"] = qs
    r.save()
    return {**tot, "clock_median_ms": out["clock"]["pooled"].get("median_ms"), "p10_ms": out["clock"]["pooled"].get("p10_ms"), "p90_ms": out["clock"]["pooled"].get("p90_ms")}


# ------------------------------------------------------------------ S4 판 결과
APP_DRAW_TASK = """# 유국 판 공개 손패 읽기(헤드 녹화 프레임을 직접 보고 적는다)

2026-11-14 매장 리치 마작(4인) 대국을 위에서 내려다본 헤드 폰 녹화다. 네게 주어진 **한 판(보통 유국)** 의 끝 장면에서 **텐파이 자리가 공개한 손패만** 읽어
아래 JSON 을 채운다. 프레임을 열어 보고 판단하는 일이다 — 코드는 프레임 고르기 · 자르기 · 키우기 · 돌리기 · 이어 붙이기에만 쓴다(패 인식 모델 · 서버 · API 를 부르지 않는다).

{materials}

{howto}

## 이 판 — 앱 기록에서 이미 정해진 것(다시 읽지 않는다)
- 판 id `{gid}` · {round_label} · 선 = {dealer_side} 쪽(자리 {dealer}) · 사진 아래 쪽 = 자리 {bottom}(자리 번호는 bottom → right → top → left 로 하나씩 늘어남)
- 끝: 보통 유국(황패). 앱 유국 창에서 고른 **텐파이 자리: {tenpai}** · 노텐: {noten}
- 강 · 울기 · 리치 · 도라는 앱 버림 기록에 있다 — 읽지 않는다. 노텐 자리가 손패를 보였어도 적지 않는다.

## 시각(헤드 녹화 시계)
- 앱 닻: 유국 창 저장 폴더 `{end_folder}`(태블릿 시계 {anchor}) → 헤드 녹화 시계로 약 {anchor_head}(W5 시계 차 {offset} — 두 기록기의 버림 시각을 맞춘 중앙값).
- **공개(텐파이 자리가 손패를 앞면으로 눕힌 때)는 {win0} ~ {win1} 사이에서 찾는다**(닻 − 60초 ~ + 3초). 창 밖에서 찾았으면 reveal_evidence 에 까닭을 적는다.
- 참고: 마지막 버림을 헤드 녹화 기록기가 처음 본 때 ≈ {last_head}.

## 손패 순서의 방향(사진 = 돌리지 않은 원본 프레임 기준) — 틀리면 안 된다
손패는 **그 사람 기준 왼쪽 → 오른쪽** 으로 적는다. 위에서 내려다본 사진에서 그 방향은 자리마다 아래와 같다(이 판의 텐파이 자리만):
{direction}
- 잘라서 돌려 읽었으면, 답을 적기 전에 **돌리기 전 사진 방향으로 다시 확인한다**(첫 패 · 끝 패가 사진의 어느 쪽 끝인지). 돌리는 방향을 헷갈리면 순서가 통째로 뒤집힌다.
- 답의 `order_basis` 에 자리마다 쓴 방향을 위 표의 말 그대로 적는다(예: "사진 아래 → 위").

## 할 일
텐파이 자리마다 공개된 손패를 그 사람 기준 왼쪽 → 오른쪽(위 방향) 놓인 순서 그대로 읽는다. 공개 직후 프레임 둘 이상에서 읽어 서로 같은지 본다.
장수(13 − 3×울기)와 텐파이 모양(한 장을 더하면 화료 모양이 되는 패가 있음)을 스스로 검산하고 기다림 패를 적는다. 안 맞는데 그대로 둘 때는 uncertain 에 적는다.
울기 묶음이 있으면 그 자리 앞 탁자 모서리의 묶음을 melds 에 적는다(없으면 []).

## 적을 것 — `{answer}`
```json
{{
  "id": "{gid}",
  "t_reveal": "HH:MM:SS.s",                 // 텐파이 자리 손패 앞면이 처음 보인 때(헤드 녹화 시계)
  "reveal_evidence": "어느 프레임에서 무엇을 봤는지",
  "hands": {hands_example},                  // 텐파이 자리마다 공개 손패(울기 묶음 빼고), 그 사람 기준 왼쪽 → 오른쪽
  "order_basis": {basis_example},            // 자리마다 hands 를 적은 사진 방향(위 "손패 순서의 방향" 의 말 그대로)
  "melds": {melds_example},                  // 자리마다 묶음 목록, 묶음 하나 = {{"type": "pon|chi|kan|ankan", "tiles": ["1z", "1z", "1z"]}}(이 꼴만 — 패 목록만 적지 않는다)
  "waits": {melds_example},                  // 자리마다 기다림 패(순서 상관없음)
  "hand_note": "공개하면서 순서를 바꿨는지 · 가려진 패",
  "uncertain": ["확신이 낮은 칸을 하나씩: 어느 자리 몇 번째 · 후보 둘 · 왜"]
}}
```
- 확신이 없는 것을 그럴듯하게 채우지 않는다. 모르면 `null` 을 쓰고 `uncertain` 에 까닭을 적는다.

## 지킬 것
- 그림 · 스크립트는 **네 작업 폴더**(`{work}`)에만 쓴다. 결과 JSON 은 위 경로 한 파일(UTF-8 · LF).
- 실행 폴더의 다른 파일 · 다른 판 폴더, 저장소의 다른 자료(라벨 · 패보 · 기록기 출력 · 앱 촬영 기록)는 **읽지 않는다** — 읽어도 되는 것은 이 문서, 프레임 폴더, 네 작업 폴더뿐.
  같은 판을 다른 하위 에이전트도 따로 읽는다(읽기 {ab}). 다른 읽기 폴더는 열지 않는다.
- 저장소 파일을 고치지 않는다. git 을 쓰지 않는다.
- 여러 줄 Python 은 파일로 써서 `python -X utf8 <파일>` 로 돌린다(`python -c` 여러 줄 · heredoc stdin 은 이 환경에서 멈춘다).
- 마지막 답은 세 줄 이내: 공개 시각 / 자리마다 손패 한 줄 / 확신 낮은 칸 수.
"""
DRAW_KEYS = ["hands", "melds", "waits"]
# 그 사람 기준 왼쪽 → 오른쪽 = 위에서 내려다본 원본 사진에서(left 자리의 오른손 쪽이 사진 아래 — w16 b 답의 울기 묶음 자리 · 2반장 예시 끝 손패 순서와 맞음)
DRAW_DIR = {"bottom": "사진 왼쪽 → 오른쪽", "right": "사진 아래 → 위", "top": "사진 오른쪽 → 왼쪽", "left": "사진 위 → 아래"}
DRAW_FILL_RULE = ("패 종류가 다수인 쪽(자리마다 손패 · 묶음의 패 종류 모음이 다른 읽기와 같은 수가 가장 많은 읽기, 같으면 c(새 지시문) → a → b) — "
                  "순서까지 셋이 다르면 그 읽기의 순서를 씀")


def draw_meld(m) -> dict:
    """공개 읽기 묶음 한 칸(옛 꼴 패 목록 · {"type"|"kind", "tiles"}) → {"type", "tiles"}. 종류가 없으면 패로 짐작(같은 패 넷 = kan · 셋 = pon · 그 밖 = chi)."""
    ts = list(m.get("tiles") or []) if isinstance(m, dict) else list(m or [])
    k = (m.get("type") or m.get("kind")) if isinstance(m, dict) else None
    k = {"minkan": "kan", "daiminkan": "kan", "kakan": "kan"}.get(k, k)
    if not k:
        n = len({norm(t) for t in ts})
        k = "kan" if len(ts) == 4 and n == 1 else ("pon" if len(ts) == 3 and n == 1 else "chi")
    return {"type": k, "tiles": ts}


def draw_norm(ans: dict) -> dict:
    """대조용 꼴: 손패 = 자리마다 패 줄(순서 그대로), 묶음 = (종류, 정렬한 패) 목록, 기다림 = 순서 없는 모음. 빈 자리 = 빈 값."""
    sides = set((ans.get("hands") or {})) | set((ans.get("melds") or {})) | set((ans.get("waits") or {}))
    return {"hands": {s: tuple((ans.get("hands") or {}).get(s) or []) for s in sides},
            "melds": {s: sorted((d["type"], tuple(sorted(norm(t) for t in d["tiles"]))) for d in map(draw_meld, (ans.get("melds") or {}).get(s) or [])) for s in sides},
            "waits": {s: sorted({norm(t) for t in (ans.get("waits") or {}).get(s) or []}) for s in sides}}


def draw_compare(x: dict, y: dict) -> dict:
    """두 공개 읽기를 꼴을 고르게 해 견줌. order_reversed = 패 종류는 같고 순서만 정반대인 자리."""
    nx, ny = draw_norm(x), draw_norm(y)
    sides = sorted(set(nx["hands"]) | set(ny["hands"]))
    sides = sorted(set(sides) | set(nx["melds"]) | set(ny["melds"]) | set(nx["waits"]) | set(ny["waits"]))
    diff = [k for k in DRAW_KEYS if any(list(nx[k].get(s) or []) != list(ny[k].get(s) or []) for s in sides)]
    rev = [s for s in sides if nx["hands"].get(s) and nx["hands"].get(s) != ny["hands"].get(s) and tuple(reversed(nx["hands"][s])) == tuple(ny["hands"].get(s) or ())]
    same_tiles = [s for s in sides if sorted(map(norm, nx["hands"].get(s) or ())) == sorted(map(norm, ny["hands"].get(s) or ()))]
    return {"same": not diff, "diff": diff, "order_reversed": rev, "same_tile_kinds_sides": same_tiles}


def _kinds_same(x: dict, y: dict) -> bool:
    nx, ny = draw_norm(x), draw_norm(y)
    sides = set(nx["hands"]) | set(ny["hands"])
    return all(sorted(map(norm, nx["hands"].get(s) or ())) == sorted(map(norm, ny["hands"].get(s) or ())) and (nx["melds"].get(s) or []) == (ny["melds"].get(s) or [])
               for s in sides)


def draw_pick(reads: dict):
    """공개 읽기 고르기. a · b 같음 → a. 셋째 읽기 c 가 있으면 둘이 같은 짝(꼴을 고르게 한 뒤)의 답 — c 가 짝에 들면 c(새 지시문 꼴), 아니면 a.
    셋 다 다르면 DRAW_FILL_RULE. 돌려주는 것: (고른 읽기, 어떻게, 자세히)."""
    if "c" not in reads:
        return "a", "a · b 같음", {}
    pairs = [(x, y) for x, y in (("a", "b"), ("a", "c"), ("b", "c")) if draw_compare(reads[x], reads[y])["same"]]
    det = {"pairs_same": [f"{x}={y}" for x, y in pairs], "a_b": draw_compare(reads["a"], reads["b"]), "a_c": draw_compare(reads["a"], reads["c"]),
           "b_c": draw_compare(reads["b"], reads["c"])}
    if pairs:
        mem = {z for p in pairs for z in p}
        pick = "c" if "c" in mem else "a"
        return pick, f"셋째 읽기로 정함({' · '.join(det['pairs_same'])})", det
    score = {x: sum(_kinds_same(reads[x], reads[y]) for y in reads if y != x) for x in reads}
    pick = max(["c", "a", "b"], key=lambda x: (score[x], -["c", "a", "b"].index(x)))
    det["kind_score"] = score
    return pick, "셋 다 다름", det


def app_draw_pkg(r: Run, g, a, ab, tp, tmpl, rec_dir, wr, off, end_ms, why=None):
    """유국 공개 손패 읽기 꾸러미 하나(APP_DRAW_TASK). 답이 이미 있으면 None."""
    d = r.d / "s4" / g / ab
    ans = d / "reveal_read.json"
    if ans.exists():
        return None
    mat = "\n".join(ln for ln in _md_section(tmpl, "자료").splitlines() if not ln.startswith("- 판 시각:"))   # 판 시각은 아래 "시각" 절
    if rec_dir is not None:
        mat = mat.replace("C:\\Users\\jjh7757\\dev\\mahjong_calc\\experiments\\visit_20261114\\head_rec\\rec_20261114_125617", str(rec_dir))
    t = APP_DRAW_TASK.format(
        materials=mat, howto=_md_section(tmpl, "탁자 읽는 법"), gid=g, round_label=a["round_label"], dealer_side=a["dealer_side"], dealer=a["dealer"],
        bottom=a["bottom_seat"], tenpai=(", ".join(f"{s}(자리 {(a['bottom_seat'] + SIDES.index(s)) % 4})" for s in tp) or "없음(모두 노텐)"),
        noten=", ".join(s for s in SIDES if s not in tp) or "없음", end_folder=a["folders"]["end"], anchor=a["anchors"]["end"],
        anchor_head=hms_of(end_ms + off), offset=f"{off / 1000:+.1f}초(헤드 − 앱)",
        win0=hms_of(end_ms + off + APP_REVEAL_WIN_S[0] * 1000), win1=hms_of(end_ms + off + APP_REVEAL_WIN_S[1] * 1000),
        last_head=(wr.get("head_interval") or {}).get("last") or "모름", answer=ans.as_posix(), work=(d / "work").as_posix(), ab=ab,
        direction="\n".join(f"- {s} 자리 = {DRAW_DIR[s]}" for s in tp) or "- (텐파이 자리 없음)",
        hands_example=json.dumps({s: ["…"] for s in tp}, ensure_ascii=False), basis_example=json.dumps({s: DRAW_DIR[s] for s in tp}, ensure_ascii=False),
        melds_example=json.dumps({s: [] for s in tp}, ensure_ascii=False))
    wt(d / "TASK.md", t)
    kw = {"third_read_why": {k: why[k] for k in ("diff", "order_reversed")}} if why else {}
    return pkg("S4", f"s4_{g}_{ab}", d, d / "TASK.md", ans, game=g, kind="app_draw_reveal", tenpai=tp, **kw)


def _md_section(md: str, head: str) -> str:
    """마크다운에서 '## head' 절(다음 '## ' 앞까지)."""
    i = md.find("## " + head)
    if i < 0:
        return ""
    j = md.find("\n## ", i + 3)
    return md[i:j if j >= 0 else len(md)].rstrip()


def s4_app(r: Run):
    """앱 기록 우선 S4(설계서 8-6 W3): 화료(label.json) = 앱 값 → s4/<판>/app/result_read.json(꾸러미 0), 유국(텐파이 자리 있음) = 공개 손패만 읽는
    꾸러미 둘(APP_DRAW_TASK → reveal_read.json), 앱 결과가 없는 판 = 지금 꾸러미(RESULT_TASK) 그대로."""
    sys.path.insert(0, str(HERE))
    import app_record as ar
    cfg = r.cfg()
    date = cfg.recording["date"]
    tmpl = (HERE / "results" / "han3_1123" / "RESULT_TASK.md").read_text(encoding="utf-8")
    defs = jl(r.d / "rounds_defs.json")
    rounds = {x["id"]: x for x in jl(r.d / "s1" / "rounds.json")["rounds"]}
    w5 = jl(r.d / "w5" / "align.json") if (r.d / "w5" / "align.json").exists() else {"rounds": {}, "clock": {"pooled": {}}}
    off_all = (w5["clock"].get("pooled") or {}).get("median_ms") or 0
    rc = cfg.recording or {}
    rec_dir = (hcfg._p(rc["root"]) / rc["recs"][-1]) if rc.get("root") and rc.get("recs") else None
    pend, how = [], {}
    for g in r.games():
        a = r.app_round(g)
        rr_app = ar.to_result_read(a, r.app_events(g)) if a else None
        if a and a["end"] == "win" and rr_app:
            f = r.d / "s4" / g / "app" / "result_read.json"
            if not f.exists():
                wj(f, rr_app)
            how[g] = "app"
            continue
        if a and a["end"] == "draw" and rr_app and rr_app.get("tenpai_revealed") is not None:
            how[g] = "app_draw"
            wr = w5["rounds"].get(g) or {}
            off = (wr.get("clock") or {}).get("median_ms")
            off = off_all if off is None else off
            end_ms = to_ms(date, a["anchors"]["end"])
            tp = rr_app["tenpai_revealed"]
            for ab in ("a", "b"):
                p_ = app_draw_pkg(r, g, a, ab, tp, tmpl, rec_dir, wr, off, end_ms)
                if p_:
                    pend.append(p_)
            continue
        how[g] = "read"   # 앱 결과 없음(label 없음 · 텐파이 모름 · 앱 판 없음) → 지금 꾸러미 그대로
        for ab in ("a", "b"):
            d = r.d / "s4" / g / ab
            ans = d / "result_read.json"
            if ans.exists():
                continue
            t = tmpl.replace("…/results/han3_1123/<판 id>/result_work/", (d / "work").as_posix() + "/").replace(
                "…/results/han3_1123/<판 id>/result_read.json", ans.as_posix())
            t += f"\n\n## 이 판\n- 판 id: `{g}`\n- 판 정의: `{json.dumps({**defs[g], 't_clear': rounds[g].get('t_clear')}, ensure_ascii=False)}`\n" \
                 f"- 읽기 {ab}: 같은 판을 다른 하위 에이전트도 따로 읽는다. 다른 읽기 폴더는 열지 않는다.\n"
            wt(d / "TASK.md", t)
            pend.append(pkg("S4", f"s4_{g}_{ab}", d, d / "TASK.md", ans))
    r.stage("S4")["how"] = how
    r.save()
    if pend:
        return pend
    qs, conf, third = [], {}, []
    for g in r.games():
        out = r.d / g / "result_read.json"
        if how[g] == "app":
            conf[g] = {"agree": True, "diff": [], "source": "앱 label.json(꾸러미 없음)"}
            if not out.exists():
                shutil.copyfile(r.d / "s4" / g / "app" / "result_read.json", out)
            continue
        if how[g] == "app_draw":
            reads = {ab: jl(r.d / "s4" / g / ab / "reveal_read.json") for ab in ("a", "b", "c") if (r.d / "s4" / g / ab / "reveal_read.json").exists()}
            cmp_ab = draw_compare(reads["a"], reads["b"])
            if not cmp_ab["same"] and "c" not in reads:
                # a · b 가 (꼴을 고르게 한 뒤에도) 다름 → 셋째 읽기(새 지시문). 채우지 않고 기다림
                a = r.app_round(g)
                wr = w5["rounds"].get(g) or {}
                off = (wr.get("clock") or {}).get("median_ms")
                off = off_all if off is None else off
                p_ = app_draw_pkg(r, g, a, "c", ar.to_result_read(a, r.app_events(g))["tenpai_revealed"], tmpl, rec_dir, wr, off, to_ms(date, a["anchors"]["end"]),
                                  why=cmp_ab)
                if p_:
                    third.append(p_)
                conf[g] = {"agree": False, "diff": cmp_ab["diff"], "order_reversed": cmp_ab["order_reversed"], "source": "앱 텐파이 자리 + 공개 손패 읽기 a · b 다름 → 셋째 읽기 c 기다림"}
                continue
            pick, how_pick, detail = draw_pick(reads)
            ch = reads[pick]
            conf[g] = {"agree": cmp_ab["same"], "diff": cmp_ab["diff"], "order_reversed": cmp_ab["order_reversed"], "picked": pick, "how": how_pick, **detail,
                       "source": "앱 텐파이 자리 + 공개 손패 읽기 " + " · ".join(reads)}
            if how_pick == "셋 다 다름":
                qs.append({"id": f"{cfg.prefix_of(g)}_reveal", "kind": "pick", "stage": "S4", "game": g,
                           "current": {k: ch.get(k) for k in ("hands", "melds", "waits")},
                           "candidates": [{k: reads[x].get(k) for k in ("hands", "melds", "waits")} for x in reads if x != pick],
                           "why": f"공개 손패 세 읽기가 모두 다름 — {DRAW_FILL_RULE}로 읽기 {pick} 로 채움", "detail": detail})
            rr = ar.to_result_read(r.app_round(g), r.app_events(g))
            tp = rr["tenpai_revealed"]
            rr.update(hands_revealed=ch.get("hands"), melds={**rr["melds"], **{s_: [draw_meld(m) for m in v or []] for s_, v in (ch.get("melds") or {}).items()}},
                      waits=ch.get("waits"), order_basis=ch.get("order_basis"), t_reveal_read=ch.get("t_reveal"),
                      hand=(ch.get("hands") or {}).get(tp[0]) if len(tp) == 1 else None,
                      uncertain=list(ch.get("uncertain") or []), reveal_read=f"s4/{g}/{pick}/reveal_read.json", reveal_pick=how_pick)
            wj(out, rr)   # 늘 다시 씀(셋째 읽기 · 대조 규칙이 바뀌면 고른 답이 바뀜 — S5 가 손패 주인 손패를 다시 채움)
            continue
        a_, b_ = jl(r.d / "s4" / g / "a" / "result_read.json"), jl(r.d / "s4" / g / "b" / "result_read.json")
        diff = [k for k in RESULT_KEYS if result_key(a_, k) != result_key(b_, k)]
        conf[g] = {"agree": not diff, "diff": diff, "source": "읽기 둘"}
        if diff:
            qs.append({"id": f"{cfg.prefix_of(g)}_result", "kind": "pick", "stage": "S4", "game": g, "current": {k: result_key(a_, k) for k in diff},
                       "candidates": [{k: result_key(b_, k) for k in diff}], "why": "두 읽기가 다름(읽기 a 로 채움)"})
        if not out.exists():
            shutil.copyfile(r.d / "s4" / g / "a" / "result_read.json", out)
    if third:
        r.stage("S4")["detail_wait"] = conf
        r.state["questions_s4"] = qs   # 지금까지 정한 판 몫(셋째 읽기를 기다리는 판은 아직 없음) — 옛 값이 남지 않게
        r.save()
        return third
    r.state["questions_s4"] = qs
    r.done("S4", agree=sum(v["agree"] for v in conf.values()), games=len(conf), detail=conf, how=how)
    return []


def s4(r: Run):
    if r.cfg().app_record and r.app():
        return s4_app(r)
    reuse_task = HERE / "results" / "han3_1123" / "RESULT_TASK.md"
    tmpl = reuse_task.read_text(encoding="utf-8")
    defs = jl(r.d / "rounds_defs.json")
    rounds = {x["id"]: x for x in jl(r.d / "s1" / "rounds.json")["rounds"]}
    pend = []
    for g in r.games():
        for ab in ("a", "b"):
            d = r.d / "s4" / g / ab
            ans = d / "result_read.json"
            if ans.exists():
                continue
            t = tmpl.replace("…/results/han3_1123/<판 id>/result_work/", (d / "work").as_posix() + "/").replace(
                "…/results/han3_1123/<판 id>/result_read.json", ans.as_posix())
            t += f"\n\n## 이 판\n- 판 id: `{g}`\n- 판 정의: `{json.dumps({**defs[g], 't_clear': rounds[g].get('t_clear')}, ensure_ascii=False)}`\n" \
                 f"- 읽기 {ab}: 같은 판을 다른 하위 에이전트도 따로 읽는다. 다른 읽기 폴더는 열지 않는다.\n"
            wt(d / "TASK.md", t)
            pend.append(pkg("S4", f"s4_{g}_{ab}", d, d / "TASK.md", ans))
    if pend:
        return pend
    qs, conf = [], {}
    for g in r.games():
        a, b = jl(r.d / "s4" / g / "a" / "result_read.json"), jl(r.d / "s4" / g / "b" / "result_read.json")
        diff = [k for k in RESULT_KEYS if result_key(a, k) != result_key(b, k)]
        conf[g] = {"agree": not diff, "diff": diff}
        if diff:
            qs.append({"id": f"{r.cfg().prefix_of(g)}_result", "kind": "pick", "stage": "S4", "game": g, "current": {k: result_key(a, k) for k in diff},
                       "candidates": [{k: result_key(b, k) for k in diff}], "why": "두 읽기가 다름(읽기 a 로 채움)"})
        out = r.d / g / "result_read.json"
        if not out.exists():
            shutil.copyfile(r.d / "s4" / g / "a" / "result_read.json", out)
    r.state["questions_s4"] = qs
    r.done("S4", agree=sum(v["agree"] for v in conf.values()), games=len(conf), detail=conf)
    return []


def result_key(rr, k):
    if k == "riichi_cells":
        return sorted((x["side"], x["river_index"]) for x in rr.get("riichi") or [])
    return rr.get(k)


# ------------------------------------------------------------------ S5 대조 · 고침(자동 규칙)
def visible_counts(dart, rr) -> Counter:
    """네 자리 기록기 강(울려 나간 칸 포함) + 눈 읽기 끝 손패 · 울기 · 표시패(같은 종류 5장 이상 = 헛 칸 · 틀린 종류의 증거)."""
    c = Counter()
    for s in SIDES:
        for x in dart[s]["slots"]:
            c[norm(x["tile"])] += 1
    for t in (rr.get("hand") or []):
        c[norm(t)] += 1
    for s, ms in (rr.get("melds") or {}).items():
        for m in ms or []:
            ts = list(m.get("tiles") or [])
            if m.get("called_tile") in ts:     # 받은 패는 남의 강 칸으로 이미 셈
                ts.remove(m["called_tile"])
            for t in ts:
                c[norm(t)] += 1
    for t in rr.get("dora_indicators") or []:
        c[norm(t)] += 1
    return c


def apply_ops_sim(dart, ops):
    """recorder_fix 꼴 고침을 dart 사본에 적용(검사용 — han3 recfix 와 같은 뜻)."""
    d = copy.deepcopy(dart)
    for o in ops:
        s = o.get("side")
        if o["op"] == "retile":
            next(x for x in d[s]["slots"] if x["i"] == o["i"])["tile"] = o["to"]
        elif o["op"] == "drop":
            d[s]["slots"] = [x for x in d[s]["slots"] if x["i"] != o["i"]]
        elif o["op"] == "add_last":
            sl = d[s]["slots"]
            sl.append({"i": (max(x["i"] for x in sl) + 1) if sl else 1, "tile": o["tile"], "share": None, "n": 0, "first_at": o["at"],
                       "taken_at": None, "sideways": False})
        elif o["op"] == "riichi":
            rem = [x for x in d[s]["slots"] if not x.get("taken_at")]
            rem[o["river_index"] - 1]["sideways"] = True
    return d


def river_rules(dart, rr, t_end_play):
    """기록기 남은 강 ↔ 눈 읽기 rivers_final 을 자리마다 맞춰 고침 후보를 낸다.
    규칙: ① 바뀜 1:1 — 기록기 종류가 5장째면 눈 읽기로 retile, 눈 읽기 종류가 5장째가 되면 기록기 그대로, 둘 다 아니면 불확실(기록기 그대로)
          ② 기록기에만 있는 칸 — 그 종류가 5장째이거나 본 장면 n ≤ 4 면 drop, 아니면 불확실
          ③ 눈 읽기에만 있는 칸 — 그 자리 강 끝(마지막 버림)이면 add_last(at = 진행 끝 시각, 기록기 first_at 꼴인 초 단위), 아니면 불확실
          ④ 가져간 자리 없는 '울려 나감' 칸 바로 뒤가 같은 종류 — 밀린 패의 헛 칸으로 drop
          ⑤ 눈 읽기 리치(river_index)인데 기록기 그 칸이 가로가 아님 — riichi
    돌려주는 것: (ops, unsure[], notes[])"""
    ops, unsure, notes = [], [], []
    cnt = visible_counts(dart, rr)
    for s in SIDES:
        sl = dart[s]["slots"]
        for k, x in enumerate(sl):
            if x.get("taken_at") and not x.get("called_by") and k + 1 < len(sl) and norm(sl[k + 1]["tile"]) == norm(x["tile"]):
                ops.append({"op": "drop", "side": s, "i": x["i"], "tile": x["tile"], "rule": "④ 가져간 자리 없는 울려 나감 + 바로 뒤 같은 패"})
        rem = [x for x in sl if not x.get("taken_at")]
        mine = [x["tile"] for x in rem]
        theirs = list((rr.get("rivers_final") or {}).get(s) or [])
        sm = difflib.SequenceMatcher(None, theirs, mine, autojunk=False)
        for tag, a0, a1, b0, b1 in sm.get_opcodes():
            if tag == "equal":
                continue
            if tag == "replace" and a1 - a0 == b1 - b0:
                for p in range(a1 - a0):
                    rt, mt, slot = theirs[a0 + p], mine[b0 + p], rem[b0 + p]
                    if cnt[norm(mt)] >= 5:
                        ops.append({"op": "retile", "side": s, "i": slot["i"], "from": mt, "to": rt, "rule": f"① 기록기 {mt} 가 {cnt[norm(mt)]}장째"})
                    elif cnt[norm(rt)] + 1 >= 5:
                        notes.append(f"{s} 칸 {slot['i']}: 기록기 {mt} · 눈 읽기 {rt} — 눈 읽기로 바꾸면 {rt} 5장 → 기록기 그대로(① 규칙)")
                    else:
                        unsure.append({"side": s, "i": slot["i"], "kind": "tile", "current": mt, "candidates": [rt],
                                       "why": f"기록기 {mt} · 눈 읽기 {rt} 가 다름, 5장 규칙으로 못 가름 — 기록기 그대로 둠"})
            elif tag == "insert" or (tag == "replace" and b1 - b0 > a1 - a0):
                for p in range(b0, b1):
                    slot = rem[p]
                    if tag == "replace" and p - b0 < a1 - a0:
                        unsure.append({"side": s, "i": slot["i"], "kind": "tile", "current": slot["tile"], "candidates": [theirs[a0 + p - b0]],
                                       "why": "여러 칸이 엇갈림"})
                        continue
                    if cnt[norm(slot["tile"])] >= 5 or (slot.get("n") or 99) <= 4:
                        ops.append({"op": "drop", "side": s, "i": slot["i"], "tile": slot["tile"],
                                    "rule": f"② 기록기에만 있는 칸 · {slot['tile']} {cnt[norm(slot['tile'])]}장 · n {slot.get('n')}"})
                    else:
                        unsure.append({"side": s, "i": slot["i"], "kind": "extra", "current": slot["tile"], "candidates": ["drop"],
                                       "why": f"기록기에만 있는 칸 n {slot.get('n')} — 5장 · n 규칙으로 못 가름(그대로 둠)"})
            else:   # delete — 눈 읽기에만 있음
                for p in range(a0, a1):
                    if p >= len(mine) + (a1 - a0) - 1 and a1 == len(theirs) and b0 == len(mine) and t_end_play:
                        at = t_end_play.split(".")[0]
                        ops.append({"op": "add_last", "side": s, "tile": theirs[p], "at": at,
                                    "rule": f"③ 눈 읽기 강 끝 {p + 1}번째를 기록기가 못 봄 — at = 진행 끝 {t_end_play} 의 초 단위(기록기 first_at 꼴)"})
                    else:
                        unsure.append({"side": s, "kind": "missing", "index": p + 1, "current": None, "candidates": [theirs[p]],
                                       "why": "눈 읽기에만 있는 칸(강 가운데)"})
    for x in rr.get("riichi") or []:
        s, ri = x["side"], x["river_index"]
        rem = [y for y in apply_ops_sim(dart, ops)[s]["slots"] if not y.get("taken_at")]
        if 0 < ri <= len(rem) and not rem[ri - 1].get("sideways"):
            ops.append({"op": "riichi", "side": s, "river_index": ri, "tile": rem[ri - 1]["tile"], "rule": "⑤ 눈 읽기 리치 칸이 기록기에선 가로 아님"})
    return ops, unsure, notes


def check_dart(dart, rr, dealer_side):
    import headrec_run as hr
    il = hr.interleave(dart, dealer_side)
    fv = hr.five(dart)
    diffs, ndiff = [], []
    for s in SIDES:
        mine = [x["tile"] for x in dart[s]["slots"] if not x.get("taken_at")]
        theirs = list((rr.get("rivers_final") or {}).get(s) or [])
        if mine != theirs:
            diffs.append(s)
        if len(mine) != len(theirs):
            ndiff.append(s)
    # 통과 = 엮임 · 5장 없음 · 자리마다 남은 강 장수가 눈 읽기와 같음(종류가 다른 칸은 눈 읽기가 틀릴 수도 있어 river_rules 의 불확실로 따로)
    return {"interleave": il["ok"], "five": fv, "river_diff_sides": diffs, "count_diff_sides": ndiff, "ok": il["ok"] and not fv and not ndiff}


def event_rules(gid, paifu_events, rr, bottom, dart_after):
    """조립 때 고침(paifu.event_fix 꼴) 자동 규칙: 기록기 사건 ↔ 눈 읽기의 리치 · 울기.
    unriichi — 기록기 리치 표시인데 눈 읽기에 그 자리 리치 없음 / recall — 기록기 울기 kind 'call'(종류 모름) 한 장, 눈 읽기에 같은 준 자리 ·
    같은 받은 패 묶음이 있음(묶음 순서: 왼쪽에서 받으면 받은 패 첫 칸 + 나머지 작은 패부터, 그 밖은 눈 읽기 순서) / kakan — 눈 읽기 가깡인데
    기록기에 퐁만 있음: 끼울 자리(어느 버림 앞)는 규칙으로 못 정함 → 불확실."""
    seat = lambda side: (bottom + SIDES.index(side)) % 4  # noqa: E731
    ops, unsure = [], []
    rr_riichi = {x["side"] for x in rr.get("riichi") or []}
    for e in paifu_events:
        if e["type"] == "discard" and e.get("riichi"):
            side = SIDES[(e["seat"] - bottom) % 4]
            if side not in rr_riichi:
                ops.append({"op": "unriichi", "side": side, "tile": e["tile"], "rule": "기록기 리치 표시 · 눈 읽기 리치 없음"})
    for side, ms in (rr.get("melds") or {}).items():
        for m in ms or []:
            fs = m.get("from_side")
            ct = m.get("called_tile")
            if m.get("kind") in ("chi", "pon"):
                calls = [e for e in paifu_events if e["type"] == "call" and e["seat"] == seat(side) and fs and e.get("from") == seat(fs)
                         and e.get("kind") == "call" and [norm(t) for t in e.get("tiles") or []] == [norm(ct)]]
                if len(calls) == 1:
                    rest = [t for t in m["tiles"]]
                    rest.remove(ct)
                    tiles = ([ct] + sorted(rest, key=lambda t: (t[1], int(norm(t)[0])))) if fs == "left" else list(m["tiles"])
                    ops.append({"op": "recall", "side": side, "from_side": fs, "old_kind": "call", "old_tiles": [calls[0]["tiles"][0]],
                                "kind": m["kind"], "tiles": tiles, "rule": "기록기 울기 종류 모름 → 눈 읽기 묶음"})
            elif m.get("kind") == "kakan":
                t = norm(ct or m["tiles"][0])
                has_k = any(e["type"] == "call" and e["seat"] == seat(side) and e.get("kind") == "kakan" for e in paifu_events)
                has_p = any(e["type"] == "call" and e["seat"] == seat(side) and e.get("kind") == "pon" and norm(e["tiles"][0]) == t for e in paifu_events)
                if has_p and not has_k:
                    unsure.append({"kind": "kakan_at", "side": side, "tile": t, "current": None,
                                   "why": "눈 읽기 가깡 · 기록기 퐁만 — 가깡을 끼울 버림(시각)을 규칙으로 못 정함(설정이 있으면 설정, 없으면 빠짐)"})
    return ops, unsure


def meta_rules(r: Run, recfix_final: dict):
    """rounds_meta.json 자동: 선 = 기록기 선(고침 뒤, use_run 이면 그 선) · 손패 주인 = 화료자(유국은 혼자 텐파이 공개) ·
    국 · 본장 = 첫 판 동1국 0본장에서 친 이동 규칙(친 화료 · 유국 친 텐파이면 연장 + 본장, 유국이면 본장 +1) · 공탁 = 앞 판에서 넘어온 리치봉
    (유국이면 그 판 리치 선언 수만큼 쌓임, 화료면 0). bottom_seat 0(설정 — 아래 자리 = 0)."""
    bottom = 0
    rows, qs = [], []
    winds = ["동", "남", "서", "북"]
    rnd, honba, pot = 0, 0, 0
    prev = None
    for g in r.games():
        p = jl(r.d / g / "paifu_rec.json")
        use = next((o for o in recfix_final.get(g, []) if o["op"] == "use_run"), None)
        dealer = SIDES.index(use["dealer"]) if use else p["dealer"]
        rr = jl(r.d / g / "result_read.json")
        if rr["end"] == "win":
            hero = (bottom + SIDES.index(rr["winner_side"])) % 4
            end = rr["win_type"]
        else:
            tp = [(bottom + SIDES.index(s)) % 4 for s in rr.get("tenpai_revealed") or []]
            hero = tp[0] if len(tp) == 1 else None
            end = "draw"
            if len(tp) != 1:
                qs.append({"id": f"{g}_hero", "kind": "pick", "stage": "S5", "game": g, "why": f"유국 텐파이 공개 {tp} — 손패 주인을 못 정함"})
        if prev is not None:
            pg, pdealer, pend, pwin, ptenpai, priichi = prev
            if (pend == "draw" and pdealer in ptenpai) or (pend != "draw" and pwin == pdealer):
                honba += 1
            else:
                rnd += 1
                honba = honba + 1 if pend == "draw" else 0
            pot = pot + priichi if pend == "draw" else 0
            want_dealer = rnd % 4
            if dealer != want_dealer:
                qs.append({"id": f"{g}_dealer", "kind": "boundary", "stage": "S5", "game": g,
                           "why": f"친 이동 규칙의 선 {want_dealer} ≠ 기록기 선 {dealer} — 판 경계 · 선을 확인"})
        else:
            rnd = dealer   # 첫 판의 선 = 동 dealer+1 국(설정 없이 아래 자리 0 = 동1국 선)
        name = f"{winds[rnd // 4]}{rnd % 4 + 1}국"
        n_riichi = len(rr.get("riichi") or [])
        rows.append({"id": g, "round": name, "honba": honba, "kyotaku": pot, "dealer": dealer, "hero": hero, "end": end})
        tenpai = [(bottom + SIDES.index(s)) % 4 for s in rr.get("tenpai_revealed") or []]
        winner = (bottom + SIDES.index(rr["winner_side"])) % 4 if rr["end"] == "win" else None
        prev = (g, dealer, end, winner, tenpai, n_riichi)
    return {"_note": "paifu_auto.py S5 자동 규칙(meta_rules)", "bottom_seat": bottom, "rounds": rows}, qs


def s5(r: Run):
    cfg = r.cfg()
    if cfg.app_record and r.app():
        return s5_app(r)
    sys.path.insert(0, str(HERE))
    import headrec_run as hr  # noqa: F401
    defs = jl(r.d / "rounds_defs.json")
    hand = hcfg._p(r.state["hand_settings"]) if r.state.get("hand_settings") else None
    auto_fix, unsure, notes, checks = {}, {}, {}, {}
    for g in r.games():
        dart = jl(r.d / g / "dart_overlay.json")
        rr = jl(r.d / g / "result_read.json")
        dealer = rr.get("dealer_side")
        ops, un, nt = river_rules(dart, rr, defs[g].get("t_end_play"))
        base = check_dart(apply_ops_sim(dart, ops), rr, dealer)
        rec_dealer = SIDES[jl(r.d / g / "paifu_rec.json")["dealer"]]
        chosen = {"run": "base", "check": base}
        if not base["ok"] or rec_dealer != dealer:
            # ⑥ 기록기 옵션 --river-role(패산 위 앞면 패를 강 칸에서 뺌) · 눈 읽기 선으로 다시 돌려 봄 — 고침 뒤 검사가 통과하면 그것을 씀(use_run)
            import headrec_run as hr2
            hr2.use_hanchan(str(r.cfg_f))
            od = r.d / g / "rec_ref_river_role"
            if not (od / "dart_overlay.json").exists():
                hr2.replay("overlay", r.d / g / "overlay_dump_c2x.json", dealer, od, ["--river-role"])
            dv = jl(od / "dart_overlay.json")
            ops2, un2, nt2 = river_rules(dv, rr, defs[g].get("t_end_play"))
            alt = check_dart(apply_ops_sim(dv, ops2), rr, dealer)
            chosen["river_role"] = alt
            if alt["ok"] and (not base["ok"] or rec_dealer != dealer):
                ops = [{"op": "use_run", "run": "rec_ref_river_role", "dealer": dealer,
                        "rule": f"⑥ 기본 실행 검사 {'통과' if base['ok'] else '실패'} · 기록기 선 {rec_dealer} / 눈 읽기 선 {dealer} → --river-role · 눈 읽기 선으로 다시 돌린 것이 검사 통과"}] + ops2
                un, nt = un2, nt2
                chosen["run"] = "rec_ref_river_role"
                chosen["base_check"], chosen["check"] = base, alt
        auto_fix[g] = ops
        unsure[g] = un
        notes[g] = nt
        checks[g] = chosen
    wj(r.d / "s5" / "auto_recorder_fix.json", {"_note": "paifu_auto.py S5 자동 규칙(river_rules) — rule 칸이 근거", **auto_fix})
    # 손 파일과 견주기
    cmp = {"recorder_fix": {}, "rounds_meta": {}, "event_fix": {}, "call_turns": {}}
    strip = lambda o: {k: v for k, v in o.items() if k not in ("why", "rule")}  # noqa: E731
    hand_fix = None
    if hand and (hand / "recorder_fix.json").exists():
        hand_fix = {k: v for k, v in jl(hand / "recorder_fix.json").items() if not k.startswith("_")}
        for g in r.games():
            A = [strip(o) for o in auto_fix.get(g, [])]
            H = [strip(o) for o in hand_fix.get(g, [])]
            only_a = [o for o in A if o not in H]
            only_h = [o for o in H if o not in A]
            cmp["recorder_fix"][g] = {"auto": len(A), "hand": len(H), "same": len(A) - len(only_a), "only_auto": only_a, "only_hand": only_h}
    final_fix = hand_fix if hand_fix is not None else {g: [{k: v for k, v in o.items() if k != "rule"} | {"why": o.get("rule", "")} for o in ops] for g, ops in auto_fix.items()}
    wj(r.d / cfg.recfix_file.name, {"_note": ("손 파일(설정) " + rel(hand / "recorder_fix.json")) if hand_fix is not None else "S5 자동 규칙", **final_fix})
    auto_meta, mq = meta_rules(r, final_fix)
    wj(r.d / "s5" / "auto_rounds_meta.json", auto_meta)
    if hand and (hand / "rounds_meta.json").exists():
        hm = jl(hand / "rounds_meta.json")
        for a_, h_ in zip(auto_meta["rounds"], hm["rounds"]):
            d = {k: (a_.get(k), h_.get(k)) for k in set(a_) | set(h_) if a_.get(k) != h_.get(k)}
            cmp["rounds_meta"][a_["id"]] = d
        cmp["rounds_meta"]["_bottom_seat"] = (auto_meta["bottom_seat"], hm["bottom_seat"])
        meta_final = hm
        meta_from = "손 파일(설정)"
    else:
        meta_final, meta_from = auto_meta, "자동 규칙"
    meta_same = all(not v for k, v in cmp["rounds_meta"].items() if not k.startswith("_"))
    if meta_from == "손 파일(설정)" and meta_same and cmp["rounds_meta"]["_bottom_seat"][0] == cmp["rounds_meta"]["_bottom_seat"][1]:
        meta_final, meta_from = auto_meta, "자동 규칙(손 파일과 칸이 모두 같음)"
    wj(r.d / cfg.meta_file.name, meta_final)
    # 기록기 고침 적용(han3 recfix) → _prep/rec
    run([PY, "-X", "utf8", HT / "han3.py", "recfix", "--hanchan", r.cfg_f], log=r.log("s5_recfix.log"))
    run([PY, "-X", "utf8", HT / "han3.py", "link", "--hanchan", r.cfg_f], log=r.log("s5_link.log"))
    # 조립 때 고침(event_fix) 자동 규칙 — 고친 기록기 사건(_prep/rec/<판>/paifu_rec.json)에 대해
    auto_ev, ev_unsure = {}, {}
    for g in r.games():
        p = jl(r.prep / "rec" / g / "paifu_rec.json")
        rr = jl(r.d / g / "result_read.json")
        ops, un = event_rules(g, p["events"], rr, meta_final["bottom_seat"], None)
        if ops:
            auto_ev[g] = ops
        if un:
            ev_unsure[g] = un
    wj(r.d / "s5" / "auto_event_fix.json", auto_ev)
    src_ev = r.state.get("src_event_fix") or {}
    for g in sorted(set(auto_ev) | set(src_ev)):
        A = [strip(o) for o in auto_ev.get(g, [])]
        H = [strip(o) for o in src_ev.get(g, [])]
        cmp["event_fix"][g] = {"auto": len(A), "hand": len(H), "same": sum(1 for o in A if o in H),
                               "only_auto": [o for o in A if o not in H], "only_hand": [o for o in H if o not in A]}
    if not hand:   # 손 설정 없음 → 자동 규칙을 실행 설정에 넣음
        c = jl(r.cfg_f)
        c["paifu"]["event_fix"] = {g: [{k: v for k, v in o.items() if k != "rule"} | {"why": o["rule"]} for o in ops] for g, ops in auto_ev.items()}
        wj(r.cfg_f, c)
    # 질문(기록 불확실) — 설정 손 파일이 그 칸을 덮었으면 "설정이 덮음" 으로 적음
    qs = list(mq)
    for g in r.games():
        for u in unsure[g]:
            covered = bool(hand_fix and any(o.get("side") == u.get("side") and o.get("i") == u.get("i") for o in hand_fix.get(g, [])))
            qs.append({"id": f"{cfg.prefix_of(g)}_rec_{u.get('side')}_{u.get('i') or u.get('index')}", "kind": "record", "stage": "S5", "game": g,
                       "current": u.get("current"), "candidates": u.get("candidates"), "why": u["why"], "covered_by_setting": covered})
        for u in ev_unsure.get(g, []):
            covered = bool(src_ev.get(g)) and bool(hand)
            qs.append({"id": f"{cfg.prefix_of(g)}_ev_{u['kind']}_{u['side']}", "kind": "record", "stage": "S5", "game": g,
                       "current": u.get("current"), "why": u["why"], "covered_by_setting": covered})
    wj(r.d / "s5" / "compare.json", {"_note": "S5 자동 규칙 ↔ 11-23 손 파일(설정). same = 칸(why · rule 빼고)까지 같은 고침 수", **cmp,
                                     "checks": checks, "unsure": unsure, "notes": notes, "event_unsure": ev_unsure,
                                     "recorder_fix_used": "손 파일(설정)" if hand_fix is not None else "자동 규칙", "rounds_meta_used": meta_from})
    r.state["questions_s5"] = qs
    r.done("S5", recorder_fix_used="손 파일(설정)" if hand_fix is not None else "자동 규칙", rounds_meta_used=meta_from,
           auto_ops=sum(len(v) for v in auto_fix.values()), unsure=sum(len(v) for v in unsure.values()))
    return []


# ------------------------------------------------------------------ S5 앱 기록 판(W4 — 설계서 8-6): 앱 기록이 1차, 헤드 녹화 기록기는 시각 · 맞춰 보기 · 구멍 채우기
# 빈 기록 검사(설계서 3-8 · 8-12 (나)): 결과가 있는 판인데 앱 버림이 0, 또는 자리별 버림 수의 차(최대 − 최소, 버림이 없는 자리는 0)가
# APP_EMPTY_SPREAD + APP_EMPTY_PER_CALL × 울기 수 를 넘으면 "앱 기록 못 씀". APP_EMPTY_SPREAD = 2 는 2반장 한 반장을 보고 정한 숫자다(맞는 기록 아홉 판의
# 차 0 ~ 2 — 2 는 울기 0 인 w16, 깨진 기록은 7 ~ 18). APP_EMPTY_PER_CALL = 1 은 규칙에서: 울기 하나가 건너뛴 자리들의 버림 수를 다른 자리보다 하나씩 줄인다.
APP_EMPTY_SPREAD = 2
APP_EMPTY_PER_CALL = 1


def app_empty_check(a: dict, A: list | None) -> dict:
    """앱 버림 기록이 쓸 만한가(빈 기록 검사) → {"ok", "why", "per_seat", "calls", "spread", "limit"}. 결과가 없는 판은 검사하지 않음(ok)."""
    ev = A or []
    per = [sum(1 for e in ev if e["type"] == "discard" and e["seat"] == s) for s in range(4)]
    calls = sum(1 for e in ev if e["type"] == "call" and e.get("kind") != "kakan")
    spread, limit = max(per) - min(per), APP_EMPTY_SPREAD + APP_EMPTY_PER_CALL * calls
    out = {"per_seat": per, "calls": calls, "spread": spread, "limit": limit, "ok": True, "why": ""}
    if not ((a.get("result") or {}).get("recorded")):
        out["note"] = "앱 결과 없음 — 검사 안 함"
        return out
    if A is None or sum(per) == 0:
        out.update(ok=False, why="결과가 있는 판인데 앱 버림이 0")
    elif spread > limit:
        out.update(ok=False, why=f"자리별 버림 수 {per} 의 차 {spread} > {APP_EMPTY_SPREAD} + {APP_EMPTY_PER_CALL}×울기 {calls} = {limit}")
    return out


APP_HERO_RULE = ("유국 텐파이가 둘 이상이면 하나만 손패 주인: 울기가 적은 자리(차례 읽기로 손패를 더 많이 복원) → 같으면 리치한 자리 → "
                 "같으면 선부터 차례 순서로 앞 자리. 나머지 텐파이 자리는 hero_skipped(못 한 것)")


def _sec(ms: int) -> str:
    """기록기 first_at 꼴(초 단위 HH:MM:SS — 버림)."""
    return datetime.fromtimestamp(ms / 1000, KST).strftime("%H:%M:%S")


def _call_from_hand(e, taken) -> list:
    """울기 사건에서 손에서 나온 패(norm). 치 · 퐁 · 명깡 = 묶음 − 받은 패(taken = 바로 앞 준 자리 버림 — 강 칸으로 이미 셈) 한 장,
    가깡 = 한 장, 암깡(from = 자기) = 넷."""
    ts = [norm(t) for t in e.get("tiles") or []]
    if e.get("kind") == "kakan":
        return ts[:1]
    if e.get("from") == e["seat"] or e.get("from") is None and e.get("kind") == "ankan":
        return ts
    t = norm(taken) if taken else None
    if t in ts:
        ts.remove(t)
    elif ts:
        ts = ts[1:]
    return ts


def _meld_tiles(m) -> list:
    """묶음 한 칸(앱 label · 공개 읽기 — 패 목록 또는 {"tiles"} 사전) → 패 목록."""
    if isinstance(m, dict):
        return list(m.get("tiles") or [])
    return list(m or [])


def _taken_call(F, k):
    """F[k](버림) 바로 뒤가 남의 울기(from = 그 자리)면 그 울기."""
    if k + 1 < len(F):
        n = F[k + 1]
        if n["type"] == "call" and n.get("from") == F[k]["seat"] and n["seat"] != F[k]["seat"]:
            return n
    return None


def turn_order_check(F, dealer):
    """사건 순서 = 차례 규칙인가(선부터 한 자리씩, 울기 뒤에는 운 자리가 버림, 가깡 · 암깡은 같은 자리가 이어 버림). 어긋난 첫 곳 · 수."""
    exp, bad = dealer, []
    for k, e in enumerate(F):
        if e["type"] == "call":
            exp = e["seat"]
            continue
        if e["type"] != "discard":
            continue
        if e["seat"] != exp:
            bad.append({"event": k, "seat": e["seat"], "tile": e["tile"], "expected": exp})
        c = _taken_call(F, k)
        exp = c["seat"] if c else (e["seat"] + 1) % 4
    return {"ok": not bad, "bad": bad[:5], "n_bad": len(bad)}


def app_merge(A, H, Hd, bottom, track_first_head, off, dealer):
    """앱 버림 기록 A(태블릿 시계) + 헤드 녹화 기록기 H(paifu_rec 사건) · Hd(dart, 헤드 시계) → 고친 기록.
    자리마다 패 줄로 맞춘다(difflib, 패 코드 그대로 — W5 와 같음):
      같음 → 앱 사건(시각은 헤드 at) / 다름 → 헤드 칸 중 at < 앱 추적 시작(track_first_head)인 것은 "앱 추적 전" — 헤드 녹화로 채움(pre),
      남은 헤드 칸과 앱 칸이 같은 수면 1:1 로 앱 패(retile), 아니면 헤드 칸은 뺌(drop) · 앱 칸은 더함(add, 시각 = 앱 at + 시계 차).
    울기는 (자리, 준 자리) 줄로 맞춤: 같은 자리면 앱 묶음(recall), 헤드에만 있는 울기는 받은 버림이 pre 면 pre, 아니면 drop, 앱에만 있으면 그대로.
    사건 순서 = 앱 순서, pre 사건은 그 뒤 헤드에서 맞은 첫 사건 바로 앞(앱 순서가 차례 규칙과 어긋나고 헤드 순서는 맞으면 헤드 순서). dart = 헤드 칸(first_at 헤드 시계)을 사건에 맞춰 바꾼 것.
    돌려주는 것: F(사건) · D(dart) · ops(고침 — why 와 함께) · stats."""
    A = [e for e in A if e["type"] in ("discard", "call")]
    HE = H
    Ai = {s: [k for k, e in enumerate(A) if e["type"] == "discard" and e["seat"] == s] for s in range(4)}
    Hi = {s: [k for k, e in enumerate(HE) if e["type"] == "discard" and e["seat"] == s] for s in range(4)}
    h2a, pre, drop, add = {}, set(), set(), set()
    ops = []
    tf = hms_of(track_first_head)
    for s in range(4):
        side = SIDES[(s - bottom) % 4]
        sm = difflib.SequenceMatcher(None, [A[k]["tile"] for k in Ai[s]], [HE[k]["tile"] for k in Hi[s]], autojunk=False)
        for tag, a0, a1, b0, b1 in sm.get_opcodes():
            if tag == "equal":
                for j in range(a1 - a0):
                    h2a[Hi[s][b0 + j]] = Ai[s][a0 + j]
                continue
            hs = [Hi[s][j] for j in range(b0, b1)]
            as_ = [Ai[s][j] for j in range(a0, a1)]
            hp = [h for h in hs if HE[h].get("at") is not None and HE[h]["at"] < track_first_head]
            hr = [h for h in hs if h not in hp]
            for h in hp:
                pre.add(h)
            if hr and len(hr) == len(as_):
                for h, a_ in zip(hr, as_):
                    h2a[h] = a_
                    ops.append({"op": "retile", "side": side, "seat": s, "nth": Hi[s].index(h) + 1, "from": HE[h]["tile"], "to": A[a_]["tile"],
                                "head_at": hms_of(HE[h]["at"]) if HE[h].get("at") else None,
                                "why": f"앱 추적 구간 안({tf} 뒤)에서 헤드 녹화 기록기 {HE[h]['tile']} · 앱 {A[a_]['tile']} — 앱 기록을 따름"})
            else:
                for h in hr:
                    drop.add(h)
                    ops.append({"op": "drop", "side": side, "seat": s, "nth": Hi[s].index(h) + 1, "tile": HE[h]["tile"],
                                "head_at": hms_of(HE[h]["at"]) if HE[h].get("at") else None,
                                "why": f"헤드 녹화 기록기에만 있는 칸(앱 추적 구간 안 — {tf} 뒤) — 앱 기록을 따라 뺌"})
                for a_ in as_:
                    add.add(a_)
                    ops.append({"op": "add", "side": side, "seat": s, "nth": Ai[s].index(a_) + 1, "tile": A[a_]["tile"],
                                "app_at": hms_of(A[a_]["at"]) if A[a_].get("at") else None,
                                "why": "앱 버림 기록에만 있는 칸 — 앱 기록을 따라 더함(시각 = 앱 at + 시계 차)"})
    # 울기: (자리, 준 자리) 줄로 맞춤
    Ac = [k for k, e in enumerate(A) if e["type"] == "call"]
    Hc = [k for k, e in enumerate(HE) if e["type"] == "call"]
    sm = difflib.SequenceMatcher(None, [(A[k]["seat"], A[k].get("from")) for k in Ac], [(HE[k]["seat"], HE[k].get("from")) for k in Hc], autojunk=False)

    def taken_h(h):
        f = HE[h].get("from")
        return next((j for j in range(h - 1, -1, -1) if HE[j]["type"] == "discard" and HE[j]["seat"] == f), None)
    for tag, a0, a1, b0, b1 in sm.get_opcodes():
        if tag == "equal":
            for j in range(a1 - a0):
                a_, h = Ac[a0 + j], Hc[b0 + j]
                h2a[h] = a_
                ka = (A[a_].get("kind"), sorted(norm(t) for t in A[a_].get("tiles") or []))
                kh = (HE[h].get("kind"), sorted(norm(t) for t in HE[h].get("tiles") or []))
                if ka != kh:
                    ops.append({"op": "recall", "side": SIDES[(A[a_]["seat"] - bottom) % 4], "seat": A[a_]["seat"],
                                "from_side": SIDES[(A[a_]["from"] - bottom) % 4] if A[a_].get("from") is not None else None,
                                "old_kind": HE[h].get("kind"), "old_tiles": list(HE[h].get("tiles") or []), "kind": A[a_].get("kind"), "tiles": list(A[a_].get("tiles") or []),
                                "why": "같은 자리 · 같은 준 자리의 울기인데 묶음이 다름 — 앱 기록을 따름"})
            continue
        for h in Hc[b0:b1]:
            td = taken_h(h)
            if td is not None and td in pre:
                pre.add(h)
            else:
                drop.add(h)
                ops.append({"op": "call_drop", "side": SIDES[(HE[h]["seat"] - bottom) % 4], "seat": HE[h]["seat"], "kind": HE[h].get("kind"),
                            "tiles": list(HE[h].get("tiles") or []), "why": "헤드 녹화 기록기에만 있는 울기(받은 버림이 앱 추적 구간 안) — 앱 기록을 따라 뺌"})
        for a_ in Ac[a0:a1]:
            add.add(a_)
            ops.append({"op": "call_add", "side": SIDES[(A[a_]["seat"] - bottom) % 4], "seat": A[a_]["seat"], "kind": A[a_].get("kind"),
                        "tiles": list(A[a_].get("tiles") or []), "why": "앱 버림 기록에만 있는 울기 — 앱 기록을 따름"})
    # 사건 순서
    F, src, emitted, pend = [], [], set(), []
    a2h = {a_: h for h, a_ in h2a.items()}

    def head_at(a_):
        h = a2h.get(a_)
        if h is not None and HE[h].get("at") is not None:
            return HE[h]["at"]
        return A[a_]["at"] + off if A[a_].get("at") is not None else None

    def emit_a(a_):
        if a_ in emitted:
            return
        emitted.add(a_)
        e = dict(A[a_])
        if e["type"] == "discard":
            e["at"] = head_at(a_)
        F.append(e)
        src.append(("m", a2h[a_], a_) if a_ in a2h else ("a", None, a_))

    def flush():
        for h in pend:
            F.append(dict(HE[h]))
            src.append(("p", h, None))
        pend.clear()
    ai = 0
    for h, e in enumerate(HE):
        if e["type"] not in ("discard", "call"):
            continue
        if h in h2a:
            t = h2a[h]
            flush()
            while ai <= t:
                emit_a(ai)
                ai += 1
        elif h in pre:
            pend.append(h)
    flush()
    while ai < len(A):
        emit_a(ai)
        ai += 1
    seqH = [h for h, e in enumerate(HE) if h in h2a]
    seqF = [x[1] for x in src if x[0] == "m"]
    moved = sum(max(a1 - a0, b1 - b0) for tag, a0, a1, b0, b1 in difflib.SequenceMatcher(None, seqH, seqF, autojunk=False).get_opcodes() if tag != "equal")
    order_note = None
    if moved:
        # 순서가 다르면 차례 규칙으로 고른다: 앱 순서가 맞으면 앱 순서, 앱 순서는 어긋나고 헤드 녹화 순서(맞은 사건 · 앞 채움은 헤드 순서,
        # 앱에만 있는 사건은 앱 순서의 바로 앞 사건 뒤)가 맞으면 헤드 순서(추적이 판 중간에 시작되면 앱 첫 프레임에 이미 놓인 칸들은 앱 순서가 뜻이 없음 — w17).
        # 둘 다 어긋나면 앱 순서(앞뒤 검사 turn_order 가 질문으로 올림).
        hs_src = [("m", h, h2a[h]) if h in h2a else ("p", h, None) for h, e in enumerate(HE) if h in h2a or h in pre]
        pos = {x[2]: n for n, x in enumerate(hs_src) if x[0] == "m"}
        for a_ in range(len(A)):
            if a_ in a2h:
                continue
            k = next((pos[b] for b in range(a_ - 1, -1, -1) if b in pos), -1)
            hs_src.insert(k + 1, ("a", None, a_))
            pos = {x[2]: n for n, x in enumerate(hs_src) if x[0] in ("m", "a")}
        FH = []
        for x in hs_src:
            if x[0] == "p":
                FH.append(dict(HE[x[1]]))
            else:
                e = dict(A[x[2]])
                if e["type"] == "discard":
                    e["at"] = head_at(x[2])
                FH.append(e)
        ok_a, ok_h = turn_order_check(F, dealer)["ok"], turn_order_check(FH, dealer)["ok"]
        if not ok_a and ok_h:
            F, src = FH, hs_src
            order_note = f"사건 순서 = 헤드 녹화 기록기 순서(앱 순서와 {moved}곳 다름 — 앱 순서는 차례 규칙과 어긋나고 헤드 순서는 맞음)"
        else:
            order_note = f"사건 순서 = 앱 기록 순서(헤드 녹화 기록기 순서와 {moved}곳 다름 — 차례 규칙: 앱 {'맞음' if ok_a else '어긋남'} · 헤드 {'맞음' if ok_h else '어긋남'})"
        ops.append({"op": "order", "moved": moved, "used": "head" if F is FH else "app", "why": order_note})
    for h in sorted(pre):
        e = HE[h]
        ops.append({"op": "keep_pre" if e["type"] == "discard" else "call_keep_pre", "side": SIDES[(e["seat"] - bottom) % 4], "seat": e["seat"],
                    **({"nth": Hi[e["seat"]].index(h) + 1, "tile": e["tile"], "head_at": hms_of(e["at"]) if e.get("at") else None} if e["type"] == "discard"
                       else {"kind": e.get("kind"), "from": e.get("from"), "tiles": list(e.get("tiles") or [])}),
                    "why": f"앱 추적 전 — 헤드 녹화로 채움(앱 추적 시작 ≈ 헤드 시계 {tf}, 앱 기록에 없는 {'버림' if e['type'] == 'discard' else '울기'})"})
    # riichi 표시: 맞은 칸은 앱 값. 헤드와 다르면 고침으로 적음
    for x in src:
        if x[0] == "m" and HE[x[1]]["type"] == "discard" and bool(HE[x[1]].get("riichi")) != bool(A[x[2]].get("riichi")):
            e = A[x[2]]
            ops.append({"op": "riichi" if e.get("riichi") else "unriichi", "side": SIDES[(e["seat"] - bottom) % 4], "seat": e["seat"], "tile": e["tile"],
                        "why": f"리치(가로) 표시: 헤드 녹화 기록기 {bool(HE[x[1]].get('riichi'))} · 앱 {bool(e.get('riichi'))} — 앱 기록을 따름"})
    # dart(헤드 시계)
    D = {}
    for s in range(4):
        side = SIDES[(s - bottom) % 4]
        hs = Hd[side]["slots"]
        slot_of = {h: hs[j] for j, h in enumerate(Hi[s])} if len(hs) == len(Hi[s]) else {}
        if len(hs) != len(Hi[s]):
            raise SystemExit(f"헤드 dart {side} 칸 {len(hs)} ≠ 헤드 사건 버림 {len(Hi[s])}")
        nxt_i = max([x["i"] for x in hs], default=0)
        slots = []
        for k, (e, x) in enumerate(zip(F, src)):
            if e["type"] != "discard" or e["seat"] != s:
                continue
            if x[0] in ("m", "p"):
                sl = copy.deepcopy(slot_of[x[1]])
                sl["tile"] = e["tile"]
            else:
                nxt_i += 1
                sl = {"i": nxt_i, "tile": e["tile"], "share": None, "n": 0, "first_at": _sec(e["at"]) if e.get("at") else None, "taken_at": None,
                      "sideways": False, "added_by": "paifu_auto S5 앱 기록 판(앱에만 있는 칸)"}
            sl["sideways"] = bool(e.get("riichi"))
            c = _taken_call(F, k)
            if c:
                sl["taken_at"] = sl.get("taken_at") or sl.get("first_at")
                sl["called_by"] = SIDES[(c["seat"] - bottom) % 4]
                sl["meld"] = {"kind": c.get("kind"), "tiles": list(c.get("tiles") or [])}
            else:
                sl["taken_at"] = None
                sl.pop("called_by", None)
                sl.pop("meld", None)
            if x[0] == "p":
                sl["filled_from_head"] = "앱 추적 전 — 헤드 녹화로 채움"
            slots.append(sl)
        # 더한 칸의 first_at 을 앞뒤 헤드 칸 사이로(turncut 은 first_at 순서로 차례를 그음)
        for j, sl in enumerate(slots):
            if sl.get("added_by"):
                lo = max((y["first_at"] for y in slots[:j] if y.get("first_at") and not y.get("added_by")), default=None)
                hi = min((y["first_at"] for y in slots[j + 1:] if y.get("first_at") and not y.get("added_by")), default=None)
                if sl["first_at"] is None or (lo and sl["first_at"] < lo):
                    sl["first_at"] = lo or sl["first_at"]
                if hi and sl["first_at"] and sl["first_at"] > hi:
                    sl["first_at"] = hi
        D[side] = {**{k: v for k, v in Hd[side].items() if k != "slots"}, "slots": slots}
    stats = {"app_events": len(A), "head_events": sum(1 for e in HE if e["type"] in ("discard", "call")), "final_events": len(F),
             "matched": sum(1 for x in src if x[0] == "m"), "app_only": sum(1 for x in src if x[0] == "a"), "pre_filled": sum(1 for x in src if x[0] == "p"),
             "dropped_head": len(drop), "order_moved": moved}
    return F, D, ops, src, stats


def app_checks(F, D, rr, a, bottom):
    """앞뒤 검사(코드): ① 같은 패 4장 한도(강 + 울기로 손에서 나간 패 + 끝 손패(화료 · 유국 공개) + 표시패) ② 론 화료패 = 방총자 마지막 버림
    ③ 리치 자리(앱 결과) = 강의 눕힌 패 자리 ④ 울기 묶음(앱 결과 · 유국 공개 읽기) = 판 중 울기 사건 ⑤ 차례 규칙: dart 엮임(headrec_run.interleave) ·
    사건 순서(turn_order_check) · 같은 종류 5장(headrec_run.five). 돌려주는 것: {이름: {"ok", "why", …}}."""
    import headrec_run as hr
    out = {}
    res = a.get("result") or {}
    c = Counter()
    for k, e in enumerate(F):
        if e["type"] == "discard":
            c[norm(e["tile"])] += 1
        elif e["type"] == "call":
            prv = F[k - 1] if k and F[k - 1]["type"] == "discard" and F[k - 1]["seat"] == e.get("from") else None
            for t in _call_from_hand(e, prv["tile"] if prv else None):
                c[t] += 1
    hands = {}
    if rr["end"] == "win":
        hands[rr["winner_side"]] = list(rr.get("hand") or []) + ([rr["win_tile"]] if rr.get("win_type") == "tsumo" and rr.get("win_tile") else [])
    else:
        hands = {s: list(v or []) for s, v in (rr.get("hands_revealed") or {}).items() if v}
    for s, ts in hands.items():
        for t in ts:
            if t:
                c[norm(t)] += 1
    for t in list(rr.get("dora_indicators") or []) + list(rr.get("ura_indicators") or []):
        c[norm(t)] += 1
    over = {k: v for k, v in c.items() if v > 4}
    out["four"] = {"ok": not over, "over": over, "why": "같은 패 5장 이상(강 + 울기 + 끝 손패 + 표시패)" if over else "",
                   "hands_from": "앱 label" if rr["end"] == "win" else ("S4 공개 손패 읽기" if hands else "없음")}
    if rr["end"] == "win" and rr.get("win_type") == "ron":
        ls = (bottom + SIDES.index(rr["loser_side"])) % 4 if rr.get("loser_side") else None
        last = next((e for e in reversed(F) if e["type"] == "discard" and e["seat"] == ls), None)
        ok = bool(last) and norm(last["tile"]) == norm(rr["win_tile"])
        out["ron_tile"] = {"ok": ok, "why": "" if ok else f"론 화료패 {rr['win_tile']} ≠ 방총자(자리 {ls}) 마지막 버림 {last and last['tile']}"}
    seats_r = sorted({e["seat"] for e in F if e["type"] == "discard" and e.get("riichi")})
    many = [s for s in range(4) if sum(1 for e in F if e["type"] == "discard" and e["seat"] == s and e.get("riichi")) > 1]
    if rr["end"] == "win":
        want = sorted(res.get("riichi_seats") or [])
        ok = want == seats_r and not many
        out["riichi"] = {"ok": ok, "app_result": want, "record": seats_r, "why": "" if ok else f"앱 결과 리치 자리 {want} · 강의 눕힌 패 자리 {seats_r}" + (f" · 두 번 눕힘 {many}" if many else "")}
    else:
        out["riichi"] = {"ok": not many, "record": seats_r, "why": f"한 자리에서 두 번 눕힘 {many}" if many else "", "note": "유국 판은 앱 결과에 리치 자리가 없음 — 기록 안 검사만"}

    def calls_of(seat):
        rows = []
        for e in F:
            if e["type"] == "call" and e["seat"] == seat:
                if e.get("kind") == "kakan":
                    t = norm(e["tiles"][0])
                    p = next((x for x in rows if x[0] == "pon" and x[1][0] == t), None)
                    if p:
                        rows.remove(p)
                    rows.append(("kakan", tuple(sorted(norm(x) for x in e["tiles"]))))
                    continue
                rows.append((e.get("kind"), tuple(sorted(norm(x) for x in e.get("tiles") or []))))
        return Counter(rows)
    mm = []
    for side, ms in (rr.get("melds") or {}).items():
        if side not in ([rr.get("winner_side")] if rr["end"] == "win" else (rr.get("tenpai_revealed") or [])):
            continue   # 결과가 묶음을 아는 자리만(화료자 · 유국 공개 자리) — 다른 자리의 빈 목록은 "모름"
        seat = (bottom + SIDES.index(side)) % 4
        got = calls_of(seat)
        if rr["end"] == "win":
            want = Counter((m.get("kind"), tuple(sorted(norm(x) for x in _meld_tiles(m)))) for m in ms or [])
            same = want == got
            wl, gl = sorted([k, list(t)] for k, t in want.elements()), sorted([k, list(t)] for k, t in got.elements())
        else:   # 공개 읽기의 묶음은 꼴이 제각각(패 목록 · {"type"|"kind", "tiles"}) — 패만 견줌
            want = Counter(tuple(sorted(norm(x) for x in _meld_tiles(m))) for m in ms or [])
            got = Counter(t for _, t in got.elements())
            same = want == got
            wl, gl = sorted(map(list, want.elements())), sorted(map(list, got.elements()))
        if not same:
            mm.append({"side": side, "result": wl, "record": gl})
    out["melds"] = {"ok": not mm, "diff": mm, "from": "앱 label melds" if rr["end"] == "win" else "S4 공개 읽기 melds(텐파이 자리)",
                    "why": "" if not mm else "울기 묶음이 결과와 판 중 울기 사건에서 다름 " + json.dumps(mm, ensure_ascii=False)}
    il = hr.interleave(D, a["dealer_side"])
    out["interleave"] = {"ok": il["ok"], "left": il["left"], "notes": il["notes"], "why": "" if il["ok"] else f"dart 엮임 막힘 {il['stuck_at']} {il['left']}"}
    to = turn_order_check(F, a["dealer"])
    out["turn_order"] = {**to, "why": "" if to["ok"] else f"사건 순서가 차례 규칙과 {to['n_bad']}곳 다름 — 첫 곳 {to['bad'][:1]}"}
    fv = hr.five(D)
    out["five"] = {"ok": not fv, "five": fv, "why": f"강에 같은 종류 5장 {fv}" if fv else ""}
    return out


def s5_app(r: Run):
    """앱 기록이 있는 반장의 S5(설계서 8-6 W4). 판마다:
    ① 고친 기록 = app_merge(앱 버림 기록 1차 + 헤드 녹화 기록기의 시각 · 앱 추적 전 칸) → _prep/rec/<판>/(paifu_rec.json · dart_overlay(_v2).json ·
       overlay_dump.json · recfix_check.json) — 3반장의 han3 recfix 출력과 같은 꼴(han3 recfix 는 돌리지 않음 — 그 ops 꼴로는 사건 순서를 못 바꿈).
       고침 목록 = recorder_fix.json(op · why, 기록용 — 이미 적용됨).
    ② rounds_meta.json = 앱 값(선 · 아래 자리 · 국 · 본장 · 결과), 손패 주인 = 화료자 / 유국 텐파이 자리(둘 이상이면 APP_HERO_RULE). 공탁은 meta_rules 와 같은 셈.
    ③ 앞뒤 검사(app_checks) — 어긋나면 앱 값을 둔 채 질문.
    질문: 앱 추적 전 칸(헤드 녹화로 채움) · 추적 구간 안 다른 칸(앱을 따름) · 앞뒤 검사 실패 · 손패 주인을 못 정함. W5 의 record 질문은 이 S5 질문으로 바꿈."""
    sys.path.insert(0, str(HERE))
    import headrec_run as hr
    hr.use_hanchan(str(r.cfg_f))
    cfg = r.cfg()
    date = cfg.recording["date"]
    w5 = jl(r.d / "w5" / "align.json")
    winds = ["동", "남", "서", "북"]
    bs = sorted({r.app_round(g)["bottom_seat"] for g in r.games() if r.app_round(g)})
    bottom = bs[0]
    qs, fixes, comp, rows, not_done = [], {}, {}, [], []
    if len(bs) > 1:
        qs.append({"id": "s5_app_bottom", "kind": "boundary", "stage": "S5", "why": f"판마다 아래 자리가 다름 {bs} — rounds_meta 는 {bottom} 하나", "covered_by_setting": False})
    prev = None
    rnd_rule, honba_rule, pot = None, 0, 0
    for g in r.games():
        a = r.app_round(g)
        A = r.app_events(g)
        pre = cfg.prefix_of(g)
        if not a:
            raise SystemExit(f"S5 앱: {g} 의 앱 판이 없다(app_rounds.json) — 앱 기록 없는 판의 S5 는 아직 없음")
        if a["bottom_seat"] != bottom:
            raise SystemExit(f"S5 앱: {g} 아래 자리 {a['bottom_seat']} ≠ {bottom}")
        wr = w5["rounds"].get(g) or {}
        off = (wr.get("clock") or {}).get("median_ms")
        off = (w5["clock"]["pooled"].get("median_ms") or 0) if off is None else off
        sub = "rec_app_dealer" if "rec_app_dealer" in (wr.get("head_used") or "") else ""
        hdir = r.d / g / sub if sub else r.d / g
        H = jl(hdir / "paifu_rec.json")
        Hd = jl(hdir / "dart_overlay.json")
        uncertain = []      # "탁자 기록 불확실"(설계서 8-12 (나)) — 질문으로
        sub_how = "W5 가"
        if H.get("dealer") != a["dealer"] and not sub:
            # 8-12 (나): W5 가 앱 버림이 없어 건너뛴 판 — 선은 앱 값(국 · 결과에서 온 값)으로 헤드 녹화 기록기를 다시 돌린다(전: SystemExit)
            od = r.d / g / "rec_app_dealer"
            if not (od / "paifu_rec.json").exists():
                hr.replay("overlay", r.d / g / "overlay_dump_c2x.json", a["dealer_side"], od, [], paifu_bottom=bottom)
            sub, hdir, sub_how = "rec_app_dealer", od, "S5 가(W5 가 앱 버림이 없어 건너뜀)"
            H, Hd = jl(od / "paifu_rec.json"), jl(od / "dart_overlay.json")
        if H.get("dealer") != a["dealer"]:
            uncertain.append(f"헤드 녹화 기록기 선 {H.get('dealer')} ≠ 앱 선 {a['dealer']}({rel(hdir)}) — 앱 선으로 다시 돌려도 안 맞음")
        rr_f = r.d / g / "result_read.json"
        rr = jl(rr_f)
        # 헤드 녹화 1차로 갈지(설계서 3-8 의 2-5 · 8-12 (나)): 격자 어긋남(펠트로도 못 고침) · 빈 기록 · 앞뒤 검사(앱 기록만으로) 실패 중 하나라도
        head_why = []
        gcv = ((cfg.app_record or {}).get("grid_check") or {}).get((a["folders"].get("track") or "_").split("_")[1])
        if gcv and str(gcv.get("flag") or "").startswith("앱 격자 어긋남") and not gcv.get("fixed_by_felt"):
            head_why.append(f"grid: {gcv['flag']}(앱 {gcv.get('app')} · gridShiftOf {gcv.get('shift') or gcv.get('shift_track')})")
        emp = app_empty_check(a, A)
        if not emp["ok"]:
            head_why.append(f"empty: 빈 기록 — {emp['why']}")
        chk_app = {}
        if A and emp["ok"] and (r.d / "app" / g / "dart_app.json").exists():
            F0 = [dict(e) for e in A if e["type"] in ("discard", "call")]
            chk_app = app_checks(F0, jl(r.d / "app" / g / "dart_app.json"), rr, a, bottom)
            bad_app = [k for k, v in chk_app.items() if not v.get("ok")]
            if bad_app:
                head_why.append("checks: 앱 기록만의 앞뒤 검사 실패 " + " · ".join(f"{k}({chk_app[k].get('why')})" for k in bad_app))
        tf_anchor = a["anchors"].get("track_first") or a["anchors"].get("discard_first")
        if head_why:
            F = [dict(e) for e in H["events"] if e["type"] in ("discard", "call")]
            D = Hd
            ops = [{"op": "head_primary", "why": "헤드 녹화 기록을 1차로(설계서 3-8 의 2-5 — 옆길 나와 같은 길): " + " / ".join(head_why)}]
            src = [["h", k] for k in range(len(F))]
            stats = {"app_events": len(A or []), "head_events": len(F), "final_events": len(F), "matched": 0, "app_only": 0, "pre_filled": 0,
                     "dropped_head": 0, "order_moved": 0, "head_primary": True}
            tf = to_ms(date, tf_anchor) + off if tf_anchor else (F[0]["at"] if F and F[0].get("at") else 0)
        else:
            tf = to_ms(date, tf_anchor) + off
            F, D, ops, src, stats = app_merge(A, H["events"], Hd, bottom, tf, off, a["dealer"])
        if sub:
            ops.insert(0, {"op": "use_run", "run": sub, "dealer": a["dealer_side"],
                           "why": f"S3 기록기 선 ≠ 앱 선 → {sub_how} 앱 선 {a['dealer_side']} 로 다시 돌린 헤드 녹화 기록기({sub})를 바탕으로"})
        # 손패 주인
        res = a.get("result") or {}
        n_calls = Counter(e["seat"] for e in F if e["type"] == "call" and e.get("kind") != "kakan")
        riichi_seats = {e["seat"] for e in F if e["type"] == "discard" and e.get("riichi")}
        hero_rule, skipped = None, []
        if a["end"] == "win":
            hero, end = res["winner"], res["type"]
            hero_rule = "화료자"
        else:
            end = "draw"
            tp = list(res.get("tenpai") or [])
            if len(tp) == 1:
                hero, hero_rule = tp[0], "유국 — 혼자 텐파이"
            elif tp:
                hero = sorted(tp, key=lambda s: (n_calls.get(s, 0), 0 if s in riichi_seats else 1, (s - a["dealer"]) % 4))[0]
                skipped = [s for s in tp if s != hero]
                hero_rule = APP_HERO_RULE
                not_done.append({"game": g, "what": "손패 주인 둘째 이후", "seats": skipped,
                                 "why": f"텐파이 {tp} 중 규칙으로 자리 {hero} 하나만 손패 주인(한 실행 = 판마다 손패 주인 하나 — 판을 나누려면 판 id · 차례 접두사 · S2 ~ S4 폴더를 손패 주인마다 따로 둬야 함)"})
            else:
                hero = None
                qs.append({"id": f"{pre}_app5_hero", "kind": "pick", "stage": "S5", "game": g, "current": None,
                           "why": "유국 텐파이 자리 없음(모두 노텐) — 손패 주인을 못 정함(손패 차례 읽기 없음)", "covered_by_setting": False})
        hero_side = SIDES[(hero - bottom) % 4] if hero is not None else None
        if a["end"] == "draw" and hero_side:
            hand = (rr.get("hands_revealed") or {}).get(hero_side)
            upd = {"hero_side": hero_side, "hero_rule": hero_rule}
            if rr.get("hand") is None and hand:
                upd["hand"] = list(hand)
                upd["hand_from"] = f"S4 공개 손패 읽기 a({hero_side}) — 손패 주인 규칙으로 고름"
            if any(rr.get(k) != v for k, v in upd.items()):
                keep = r.d / g / "result_read_s4.json"
                if not keep.exists():
                    shutil.copyfile(rr_f, keep)
                rr.update(upd)
                wj(rr_f, rr)
            if not rr.get("hand"):
                qs.append({"id": f"{pre}_app5_hero_hand", "kind": "record", "stage": "S5", "game": g, "current": None,
                           "why": f"손패 주인 {hero_side} 의 공개 손패 읽기가 없음", "covered_by_setting": False})
        chk = app_checks(F, D, rr, a, bottom)
        if head_why:
            bad_h = [k for k, v in chk.items() if not v.get("ok")]
            emp_h = app_empty_check(a, F)
            if not emp_h["ok"]:
                chk["empty"] = {"ok": False, "why": emp_h["why"], "detail": emp_h}
                bad_h.append("empty")
            if bad_h:
                uncertain.append("헤드 녹화 1차 기록도 앞뒤 검사 실패 " + " · ".join(f"{k}({chk[k].get('why')})" for k in bad_h))
        # 앱 기록만(채우기 전)의 엮임도 견줌 — 구멍 채우기가 차례 규칙을 맞췄는지
        F0 = [dict(A_) for A_ in A if A_["type"] in ("discard", "call")]
        chk["turn_order_app_only"] = {**turn_order_check(F0, a["dealer"]), "note": "참고: 앱 버림 기록만(헤드 녹화로 채우기 전) — 질문 안 함"}
        # 국 · 본장 · 공탁(meta_rules 와 같은 셈) — 앱 값과 견줌
        if prev is not None:
            pdealer, pend_, pwin, ptenpai, priichi = prev
            if (pend_ == "draw" and pdealer in ptenpai) or (pend_ != "draw" and pwin == pdealer):
                honba_rule += 1
            else:
                rnd_rule += 1
                honba_rule = honba_rule + 1 if pend_ == "draw" else 0
            pot = pot + priichi if pend_ == "draw" else 0
        else:
            rnd_rule, honba_rule = a["kyoku_index"], a["honba"]
        name_rule = f"{winds[rnd_rule // 4]}{rnd_rule % 4 + 1}국"
        if (name_rule, honba_rule) != (a["round"], a["honba"]) or rnd_rule % 4 != a["dealer"]:
            qs.append({"id": f"{pre}_app5_round", "kind": "boundary", "stage": "S5", "game": g, "current": {"round": a["round"], "honba": a["honba"], "dealer": a["dealer"]},
                       "candidates": [{"round": name_rule, "honba": honba_rule, "dealer": rnd_rule % 4}],
                       "why": "앱 국 · 본장 · 선이 앞 판 결과로 셈한 값과 다름(앱 값을 씀)", "covered_by_setting": False})
        rows.append({"id": g, "round": a["round"], "honba": a["honba"], "kyotaku": pot, "dealer": a["dealer"], "hero": hero, "end": end,
                     "hero_rule": hero_rule, "hero_skipped": skipped, "source": f"앱 {a.get('result_source')} {a['folders']['end']}"})
        prev = (a["dealer"], "draw" if a["end"] == "draw" else end, res.get("winner"), list(res.get("tenpai") or []), len(riichi_seats))
        # 고친 기록 쓰기(han3 recfix 출력 꼴)
        od = r.prep / "rec" / g
        log = [f"{o['op']} {o.get('side', '')} {o.get('tile') or o.get('to') or o.get('kind') or ''} — {o['why']}".strip() for o in ops]
        pr = {**{k: v for k, v in H.items() if k != "events"}, "dealer": a["dealer"], "hero": bottom, "events": F,
              "note": (H.get("note") or "") + (" · paifu_auto S5 앱 기록 판 — 헤드 녹화 1차: 사건 = 헤드 녹화 기록기(앱 기록을 안 씀) — " if head_why else
                                              " · paifu_auto S5 앱 기록 판: 사건 = 앱 버림 기록(시각은 헤드 녹화 시계) + 앱 추적 전 칸은 헤드 녹화로 채움 — ")
                      + ("; ".join(log) if log else "고침 없음")}
        wj(od / "paifu_rec.json", pr)
        wj(od / "dart_overlay.json", D)
        wj(od / "dart_overlay_v2.json", D)
        shutil.copyfile(r.d / g / "overlay_dump_c2x.json", od / "overlay_dump.json")
        rem = {s: [x["tile"] for x in D[s]["slots"] if not x.get("taken_at")] for s in SIDES}
        rdiff = [f"{s} 남은 강 {rem[s]} ≠ 결과 rivers_final {(rr.get('rivers_final') or {}).get(s)}" for s in SIDES
                 if (rr.get("rivers_final") or {}).get(s) is not None and rem[s] != rr["rivers_final"][s]]
        wj(od / "recfix_check.json", {"gid": g, "ops": log, "river_diffs": rdiff, "interleave": chk["interleave"]["ok"], "interleave_left": chk["interleave"]["left"],
                                      "five": chk["five"]["five"], "dealer_ok": True, "paifu_dealer": a["dealer"], "meta_dealer": a["dealer"],
                                      "count_ok": all(sum(1 for e in F if e["type"] == "discard" and e["seat"] == (bottom + SIDES.index(s)) % 4) == len(D[s]["slots"]) for s in SIDES),
                                      "riichi_rec": {s: [k + 1 for k, x in enumerate([y for y in D[s]["slots"] if not y.get("taken_at")]) if x.get("sideways")] for s in SIDES},
                                      "n_discards": sum(len(D[s]["slots"]) for s in SIDES), "by": "paifu_auto s5_app(han3 recfix 대신)"})
        wj(r.d / "s5" / "record" / f"{g}.json", {"_note": "S5 앱 기록 판의 고친 기록 — src: m = 앱 · 헤드 맞음(사건은 앱), a = 앱에만, p = 앱 추적 전(헤드 녹화로 채움)",
                                                 "events": F, "src": [list(x) for x in src], "track_first_head": hms_of(tf), "offset_ms": off})
        fixes[g] = ops
        comp[g] = {"stats": stats, "checks": chk, "ops": [o["op"] for o in ops], "hero": hero, "hero_rule": hero_rule, "hero_skipped": skipped,
                   "head_primary": bool(head_why), "head_primary_why": head_why, "empty_check": emp, "app_only_checks_failed": [k for k, v in chk_app.items() if not v.get("ok")],
                   "grid_check": gcv, "table_record_uncertain": uncertain,
                   "track_first_head": hms_of(tf), "offset_ms": off, "head": rel(hdir)}
        # 질문
        if head_why:
            qs.append({"id": f"{pre}_app5_head_primary", "kind": "record", "stage": "S5", "game": g, "signal": "head_primary", "current": "헤드 녹화 기록(1차)",
                       "candidates": ["앱 기록(1차)"], "why": next(o["why"] for o in ops if o["op"] == "head_primary"), "covered_by_setting": False,
                       "impact_summary": {"max_hand_turns": None, "result_changed": None, "zero": False}})
        if uncertain:
            qs.append({"id": f"{pre}_app5_uncertain", "kind": "record", "stage": "S5", "game": g, "signal": "table_record_uncertain", "current": "탁자 기록 불확실",
                       "why": " / ".join(uncertain), "covered_by_setting": False, "impact_summary": {"max_hand_turns": None, "result_changed": None, "zero": False}})
        for o in ops:
            if o["op"] in ("use_run", "order", "call_keep_pre", "head_primary"):
                continue
            hero_seat = o.get("seat") == hero
            red_only = o["op"] == "retile" and norm(o["from"]) == norm(o["to"])
            zero = red_only and not hero_seat
            t = o.get("head_at") or o.get("app_at")
            if not t and o["op"] in ("recall", "call_add", "call_drop"):   # 울기 사건은 시각이 없음 — 받은 버림(바로 앞 사건)의 헤드 시각
                kc = next((n for n, e in enumerate(F) if e["type"] == "call" and e["seat"] == o["seat"] and list(e.get("tiles") or []) == o["tiles"]), None)
                if kc and F[kc - 1].get("at"):
                    t = hms_of(F[kc - 1]["at"])
                    o.setdefault("head_at", t)
            clip = None
            if t:
                tm = to_ms(date, t) + (0 if o.get("head_at") else off)
                clip = {"t0": hms_of(tm - 5000), "t1": hms_of(tm + 10000)}
            if o["op"] == "keep_pre":
                # 받은 울기가 같이 채워졌으면 한 질문으로
                k = next((n for n, x in enumerate(src) if x[0] == "p" and F[n]["type"] == "discard" and F[n]["seat"] == o["seat"] and F[n]["tile"] == o["tile"]), None)
                cc = _taken_call(F, k) if k is not None else None
                cur = [o["tile"]] + ([f"{cc['kind']} {cc['tiles']}(자리 {cc['seat']})"] if cc and src[k + 1][0] == "p" else [])
                q = {"id": f"{pre}_app5_pre_{o['side']}_{o['nth']}", "kind": "record", "stage": "S5", "game": g, "signal": "app_pretrack", "current": cur,
                     "candidates": ["없음(앱 기록대로 뺌)"], "why": o["why"] + (" · 그 버림을 받은 울기도 헤드 녹화로 채움" if len(cur) > 1 else ""), "clip": clip}
            else:
                name = {"retile": "tile", "drop": "headonly", "add": "apponly", "recall": "call", "call_drop": "call_headonly", "call_add": "call_apponly",
                        "riichi": "riichi", "unriichi": "riichi"}[o["op"]]
                tag = o.get("nth") or (f"from_{o.get('from_side')}" if o["op"] == "recall" else None) or o.get("tile") or "_".join(o.get("tiles") or []) or len(qs)
                q = {"id": f"{pre}_app5_{name}_{o.get('side')}_{tag}", "kind": "record", "stage": "S5", "game": g,
                     "current": o.get("to") or (o.get("tiles") if o["op"] in ("recall", "call_add") else None) or ("없음" if o["op"] in ("drop", "call_drop") else o.get("tile")),
                     "candidates": [o.get("from") or (o.get("old_tiles") if o["op"] == "recall" else None) or (o.get("tiles") if o["op"] == "call_drop" else None)
                                    or (o.get("tile") if o["op"] == "drop" else "없음")],
                     "why": o["why"], "clip": clip}
            q.update(covered_by_setting=False, impact_summary={"max_hand_turns": None if hero_seat else 0, "result_changed": False, "river_cells": 1,
                                                               "zero": zero, "hero_seat": hero_seat})
            qs.append(q)
        for name, v in chk.items():
            if name == "turn_order_app_only" or v.get("ok"):
                continue
            qs.append({"id": f"{pre}_app5_chk_{name}", "kind": "record", "stage": "S5", "game": g, "current": "앱 값 그대로", "why": f"S5 앞뒤 검사 {name}: {v.get('why')}",
                       "detail": v, "covered_by_setting": False, "impact_summary": {"max_hand_turns": None, "result_changed": None, "zero": False}})
    meta = {"_note": "paifu_auto S5 앱 기록 판(s5_app) — 선 · 아래 자리 · 국 · 본장 · 결과는 앱 값, 손패 주인 = 화료자 / 유국 텐파이(둘 이상이면 hero_rule), "
                     "공탁은 앞 판 결과로 셈(meta_rules 와 같은 셈)", "bottom_seat": bottom, "rounds": rows}
    wj(r.d / cfg.meta_file.name, meta)
    wj(r.d / "s5" / "auto_rounds_meta.json", meta)
    wj(r.d / cfg.recfix_file.name, {"_note": "S5 앱 기록 판 고침 목록(기록용 — paifu_auto s5_app 이 _prep/rec/<판>/ 에 이미 적용함. han3 recfix 로 다시 돌리지 말 것: "
                                             "retile · drop 밖의 op 는 han3 recfix 가 모름). op: use_run · retile · drop · add · keep_pre · call_keep_pre · recall · "
                                             "call_drop · call_add · riichi · unriichi · order", **fixes})
    wj(r.d / "s5" / "auto_recorder_fix.json", {"_note": "= recorder_fix.json(앱 기록 판)", **fixes})
    run([PY, "-X", "utf8", HT / "han3.py", "link", "--hanchan", r.cfg_f], log=r.log("s5_link.log"))
    # W5 의 record 질문(둘이 다른 칸 · 울기 · 리치)은 S5 질문이 대신함 — boundary(판 시작 · 시계)만 남김
    w5q = r.state.get("questions_w5") or []
    w5f = r.d / "w5_questions.jsonl"   # W5 가 쓴 원본(S5 를 다시 돌려도 바뀐 목록을 같게 적으려고)
    replaced = [json.loads(x)["id"] for x in w5f.read_text(encoding="utf-8").splitlines() if x.strip() and json.loads(x).get("kind") == "record"] if w5f.exists() \
        else [q["id"] for q in w5q if q.get("kind") == "record"]
    r.state["questions_w5"] = [q for q in w5q if q.get("kind") != "record"]
    zero_q = [q for q in qs if (q.get("impact_summary") or {}).get("zero")]
    wj(r.d / "s5" / "compare.json", {"_note": "S5 앱 기록 판 — 판마다 맞춤 수 · 고침 · 앞뒤 검사 · 손패 주인", "games": comp, "not_done": not_done,
                                     "w5_record_questions_replaced": replaced, "questions": [q["id"] for q in qs], "zero_impact": [q["id"] for q in zero_q],
                                     "hero_rule": APP_HERO_RULE, "recorder_fix_used": "자동 규칙(s5_app)", "rounds_meta_used": "앱 기록(s5_app)"})
    r.state["questions_s5"] = qs
    r.state["s5_not_done"] = not_done
    r.done("S5", recorder_fix_used="자동 규칙(s5_app — 앱 기록 1차)", rounds_meta_used="앱 기록",
           auto_ops=sum(1 for v in fixes.values() for o in v if o["op"] not in ("use_run",)), questions=len(qs),
           pre_filled=sum(v["stats"]["pre_filled"] for v in comp.values()), checks_failed={g: [k for k, x in v["checks"].items() if not x.get("ok") and k != "turn_order_app_only"] for g, v in comp.items()},
           not_done=len(not_done))
    return []


# ------------------------------------------------------------------ S6a · S6b 손 추적 설정 · 판별(11-24 저녁)
# S6 재료(han3 turns → truthprep · turncut · slotgrid)는 판마다 손 추적 판별 설정(handtrack/config/<판>.json)과 그 판별 출력
# (results/handtrack/<판>/segments.json · river_states.json · game.json, _work/<판>_feat.npz)을 읽는다. 3반장은 11-23 에 손으로 만든 것이 공용 자리에 있다.
# 그것이 없는 판은 S6a 가 준비 읽기 꾸러미를 내고(handtrack_prep.py pack — 설계서 8-8), 읽기 답을 판별 설정으로 써 검사한 뒤(handtrack_prep.py apply)
# S6b 가 판별을 돌린다(handtrack_auto.py run). 옛 화소 규칙(handtrack_auto.py conf)은 s6a_rules 로 남김(견줌용 — init --s6a-rules 일 때만).
# 둘 다 실행 폴더 <실행>/handtrack/ 에 쓰고(공용 자리는 안 씀), 실행 설정 hanchan.json 의 handtrack 칸(dir · games)으로 han3 · han3_paifu 가
# 그 판의 경로를 실행 폴더로 돌린다(handtrack/ht_redirect.py). 손 설정이 공용 자리에 다 있는 판(3반장)은 그대로 쓴다.
HT_READY_LATE_S = 90    # (s6a_rules) t_ready 가 첫 버림(헤드 시계) 뒤 이만큼 넘으면 질문(2반장 손 설정은 +5 ~ +57초)
S6_TURN_NEAR_MS = 3000  # 차례 수 검사: t_ready 와 이만큼 안에 기록기가 처음 본 손패 주인 버림은 "경계에 걸침" 으로 질문 글에 적음(기록기는 3초 간격 프레임)


def ht_shared(g: str) -> list:
    """공용 자리의 손 설정 · 판별 출력 다섯(S6 가 읽는 것)."""
    o = HERE / "results" / "handtrack"
    return [HT / "config" / f"{g}.json", o / g / "segments.json", o / g / "river_states.json", o / g / "game.json", o / "_work" / f"{g}_feat.npz"]


def ht_run_files(r: Run, g: str) -> list:
    d = r.d / "handtrack"
    return [d / "config" / f"{g}.json", d / g / "segments.json", d / g / "river_states.json", d / g / "game.json", d / "_work" / f"{g}_feat.npz"]


def ht_spec(gid: str, mrow: dict, bottom: int, events: list, rr: dict, regions: dict, prev_last_ms, t_reveal_read_ms, frame_from: str,
            events_title: str) -> dict:
    """S6a 준비 꾸러미 · 답 적용에 쓰는 판 사실(handtrack_prep.py 머리말의 spec). events = 고친 기록(_prep/rec/<판>/paifu_rec.json — 시각은 헤드 녹화 시계)."""
    hero = mrow["hero"]
    side = SIDES[(hero - bottom) % 4]
    hd, calls, last_at, after_call = [], [], None, False
    for e in events:
        if e["type"] == "discard":
            if e.get("at") is not None:
                last_at = e["at"]
            if e["seat"] == hero:
                hd.append({"n": len(hd) + 1, "tile": e["tile"], "at": e.get("at"), "riichi": bool(e.get("riichi")), "after_call": after_call})
                after_call = False
        elif e["type"] == "call" and e["seat"] == hero:
            calls.append({"kind": e.get("kind"), "tiles": list(e.get("tiles") or []), "at": last_at})
            after_call = True
    ats = [e["at"] for e in events if e["type"] == "discard" and e.get("at") is not None]
    n_calls = sum(1 for c in calls if c["kind"] != "kakan")
    end = mrow["end"]
    return {"gid": gid, "round_label": f"{mrow.get('round', '')} {mrow.get('honba', 0)}본장", "side": side, "hero": hero, "bottom": bottom,
            "dealer": mrow.get("dealer"), "end": "draw" if end == "draw" else "win", "win_type": None if end == "draw" else end,
            "loser_side": rr.get("loser_side") if rr.get("loser_side") not in (None, "None") else None,
            "n_calls": n_calls, "n_closed_end": 13 - 3 * n_calls, "hero_riichi": any(x["riichi"] for x in hd),
            "regions": {k: list(regions[k]) for k in ("band", "river", "meld", "reveal_region", "wide", "search") if k in regions}, "frame_from": frame_from,
            "prev_last_ms": prev_last_ms, "first_ms": min(ats), "last_ms": max(ats), "hero_discards": hd, "hero_calls": calls,
            "t_reveal_read_ms": t_reveal_read_ms if end == "draw" else None, "events_title": events_title,
            "side_rule": f"rounds_meta 손패 주인 {hero}({mrow.get('hero_rule', '')}) − 아래 자리 {bottom} → {side}",
            "result_how": f"rounds_meta end {end} · {mrow.get('source', '')}"}


def s6a_frame(r: Run, cfg):
    frame, frame_from = cfg.frame, "실행 설정"
    if not frame:
        frame = hcfg.load(r.state["source_cfg"], check=False).frame
        frame_from = r.state["source_cfg"]
    if not frame:   # (11-25, 설계서 8-13 (다)) 녹화 틀이 없는 설정(paifu_setup.py 자동 설정) — 손패 줄 후보를 화면 절반에서(s6a_half_regions)
        frame_from = HALF_FROM
    return frame, frame_from


HALF_FROM = "화면 절반 손패 줄 후보(handtrack_prep.py bandcand — 설계서 8-13 (나) · (다))"


def S6A_DUMP_REGIONS(r) -> Path:
    """(11-25, 설계서 8-14 (가)) 기본 길 모드 강 · 울기 영역(dump_regions.make 출력) — 실행마다 한 번 만들고 그대로 씀(지우면 다시 만듦)."""
    return r.d / "s6a" / "_dump_regions.json"


def rec_path(r: Run, cfg) -> bool:
    """(11-25, 설계서 8-13 (가)) 앱 기록 반장 — S6 차례 목록을 고친 기록에서(han3 rturns), S6b 는 강 읽기를 안 돌림. 3반장(app_record 없음)은 옛 흐름."""
    return bool(cfg.app_record and r.app())


def ht_need(r: Run, cfg, g: str) -> list:
    """S6 가 읽는 판별 설정 · 출력. 앱 기록 반장의 실행 폴더 판은 river_states.json 을 안 만들고(강 읽기 안 함), 설정에 reveal_region 이 없으면
    game.json 도 없다(공개 손패를 영역으로 안 읽음)."""
    if g not in set(cfg.ht_games):
        return ht_shared(g)
    fs = ht_run_files(r, g)
    if rec_path(r, cfg):
        fs = [p for p in fs if p.name != "river_states.json"]
        c = fs[0]
        # (11-25, 설계서 8-14 (나)) reveal_region 이 없으면 S6b 가 game.json 을 판 결과 · 기록에서 만든다 — 판 결과에 끝 손패가 없으면 못 만듦(옛 그대로 안 봄)
        if c.exists() and "reveal_region" not in jl(c) and not result_hand(r, g):
            fs = [p for p in fs if p.name != "game.json"]
    return fs


def result_hand(r: Run, g: str):
    f = r.d / g / "result_read.json"
    return list(jl(f).get("hand") or []) if f.exists() else []


def s6b_game_json(r: Run, g: str) -> dict:
    """(11-25, 설계서 8-14 (나)) 설정에 reveal_region 이 없는 판(기본 길 모드 — 공개 읽기 game.py 를 안 돌림): S6 뒤 걸음이 읽는 칸만 든 game.json 을
    판 결과 · 기록에서 만든다. 읽히는 칸(칸 표 — results/_setup_dev/f_report.md): final_hand.closed(rebuild_opus.rebuild · han3_paifu · han3 HAN3_FINAL) ·
    final_hand.meld_detail(rebuild_opus.call_hand_tiles — turn_fix 에 call_hand 가 있으면 han3 가 그것을 씀).
    끝 손패 = <판>/result_read.json 의 hand, 울기 = S5 가 확정한 기록(_prep/rec/<판>/paifu_rec.json)의 손패 주인 울기(시각 순 — n 번째 울기 = meld_detail
    [3(n−1) : 3n] 몫, 받은 패 = 준 자리의 바로 앞 버림 → sideways). 판 결과에 끝 손패가 없으면 안 만든다(None)."""
    hand = result_hand(r, g)
    if not hand:
        return None
    meta = {x["id"]: x for x in jl(r.d / r.cfg().meta_file.name)["rounds"]}
    hero = meta[g]["hero"]
    rec_f = r.prep / "rec" / g / "paifu_rec.json"
    ev = jl(rec_f)["events"]
    md, last, notes, n = [], {}, [], 0
    for e in ev:
        if e["type"] == "discard":
            last[e["seat"]] = e["tile"]
        elif e["type"] == "call" and e["seat"] == hero:
            n += 1
            got = last.get(e.get("from")) if e.get("from") not in (None, hero) else None
            k = next((i for i, t in enumerate(e.get("tiles") or []) if norm(t) == norm(got)), None) if got else None
            if got and k is None:
                notes.append(f"{e.get('kind')} {e.get('tiles')}: 준 자리 {e.get('from')} 의 바로 앞 버림 {got} 이 묶음에 없음 — 가로 패 없음")
            for i, t in enumerate(e.get("tiles") or []):
                md.append({"tile": t, "call": n, "kind": e.get("kind"), "from": e.get("from"), **({"sideways": True} if i == k else {})})
    out = {"id": g, "_source": "paifu_auto S6b — 공개 읽기(game.py) 없이 판 결과 · 기록에서(설계서 8-14 (나)): S6 뒤 걸음이 읽는 칸만",
           "final_hand": {"closed": hand, "closed_from": f"{rel(r.d / g / 'result_read.json')} hand",
                          "meld_detail": md, "meld_detail_from": f"{rel(rec_f)} 손패 주인({hero}) 울기 — 시각 순, 받은 패 = 준 자리의 바로 앞 버림(sideways)"}}
    if notes:
        out["final_hand"]["meld_notes"] = notes
    return out


def s6a_half_regions(r: Run, cfg, g: str, side: str, t0: int, t1: int) -> dict:
    """녹화 틀 없는 설정: 손패 줄 후보(handtrack_prep.py bandcand, 결과 s6a/_cand/<판>.json — 있으면 그대로) → 영역 wide · band · search + 후보 셋.
    후보가 없으면 멈춤(값을 지어내지 않음)."""
    f = r.d / "s6a" / "_cand" / f"{g}.json"
    if not f.exists():
        run([PY, "-X", "utf8", HERE / "handtrack_prep.py", "bandcand", "--cfg", r.cfg_f, "--side", side, "--t0", str(t0), "--t1", str(t1), "--out", f],
            log=r.log(f"s6a_bandcand_{g}.log"))
    c = jl(f)
    cs = c.get("candidates") or []
    if not cs:
        raise SystemExit(f"S6a 멈춤 — {g}: 녹화 틀이 없고 화면 절반({side})에서 손패 줄 후보를 못 찾음(뒷면 상자 줄 {c.get('rows')}) — {rel(f)}")
    return {"wide": c["wide"], "band": list(cs[0]["band"]), "search": list(cs[0]["band"]), "_cands": cs, "_picks": len(c.get("frames") or []), "_rule": c.get("rule")}


def s6a_setup(r: Run, cfg, auto: list):
    """S6a 공통 준비: 손패 주인 자리 · 녹화 틀 확인, 실행 설정에 handtrack 칸(dir · games) 쓰기. → (frame, frame_from, meta)."""
    frame, frame_from = s6a_frame(r, cfg)
    meta = jl(r.d / cfg.meta_file.name)
    bottom = meta["bottom_seat"]
    mrow = {x["id"]: x for x in meta["rounds"]}
    bad = []
    for g in auto:
        h = mrow[g].get("hero")
        if h is None:
            bad.append(f"{g}: 손패 주인 없음(rounds_meta hero null)")
            continue
        sd = SIDES[(h - bottom) % 4]
        if frame and sd not in (frame.get("sides") or {}):   # 틀이 아예 없으면(자동 설정) 화면 절반 후보로 — 틀이 있는데 그 자리만 빠졌으면 옛 그대로 멈춤
            bad.append(f"{g}: 손패 주인 자리 {sd} 의 녹화 틀 없음(반장 설정 frame.sides.{sd} — band · river · meld · reveal_region · wide · search)")
    if bad:
        raise SystemExit("S6a 멈춤 — " + "; ".join(bad))
    raw = jl(r.cfg_f)
    want = {"dir": rel(r.d / "handtrack"), "games": auto,
            "_note": "paifu_auto S6a: 이 판들의 손 추적 판별 설정 · 출력은 dir 아래(config/ · <판>/ · _work/) — handtrack/ht_redirect.py 가 실행 중에 경로를 돌림"}
    if raw.get("handtrack") != want or (frame and not raw.get("frame")):
        raw["handtrack"] = want
        if frame:
            raw.setdefault("frame", frame)
        wj(r.cfg_f, raw)
    return frame, frame_from, meta


def purge_fix(r: Run, cfg, g: str) -> int:
    """판별 설정이 바뀐 판의 turn_fix 몫(차례 id 칸 · __insert__)을 지운다 — han3 fix --write 는 칸을 덧붙이기만 해서 옛 kind 등이 남음."""
    f = cfg.fix_file
    if not f.exists():
        return 0
    fx = jl(f)
    n0 = len(fx) + len(fx.get("__insert__") or [])
    fx = {k: v for k, v in fx.items() if k.startswith("__") or not cfg.owns(k, g)}
    if "__insert__" in fx:
        fx["__insert__"] = [x for x in fx["__insert__"] if not cfg.owns(x["id"], g)]
    n1 = len(fx) + len(fx.get("__insert__") or [])
    if n1 != n0:
        wj(f, fx)
    return n0 - n1


def s6a(r: Run):
    """손 추적 설정 — 준비 읽기(설계서 8-8). 판마다: 공용 자리에 손 설정 · 판별 출력이 다 있으면 그대로(3반장). 아니면
    S6a-1 꾸러미(handtrack_prep.py pack, 꾸러미 id s6a_<판>) → 답(s6a/<판>/answer.json)이 다 오면 S6a-3(handtrack_prep.py apply): 판별 설정 + features + 검사.
    검사에 걸린 것 · 답의 unsure 는 questions_s6a(값은 답 그대로). 답 꼴이 틀린 판(시각 없음 등)은 멈춤 — 답 파일을 지우고 next 하면 같은 꾸러미가 다시 나옴."""
    if r.state.get("s6a_mode") == "rules":
        return s6a_rules(r)
    cfg = r.cfg()
    st = r.stage("S6a")
    hand = [g for g in r.games() if all(p.exists() for p in ht_shared(g))]
    auto = [g for g in r.games() if g not in hand]
    if not auto:
        r.done("S6a", hand_settings=hand, auto=[], note="판마다 공용 자리에 손 설정 · 판별 출력이 있음 — 그대로 씀(준비 읽기 안 함)")
        return []
    frame, frame_from, meta = s6a_setup(r, cfg, auto)
    bottom = meta["bottom_seat"]
    mrow = {x["id"]: x for x in meta["rounds"]}
    date = cfg.recording["date"]
    s1r = {x["id"]: x for x in jl(r.d / "s1" / "rounds.json")["rounds"]} if (r.d / "s1" / "rounds.json").exists() else {}
    title = "앱 기록에서 온 시각(헤드 녹화 시계로 바꾼 것)" if cfg.app_record and r.app() else "헤드 녹화 버림 기록기에서 온 시각(헤드 녹화 시계)"
    dreg = None
    if not frame:   # (11-25, 설계서 8-14 (가)) 강 · 울기 영역 — 반장 모든 판의 버림 기록기 덤프에서 자리마다 상자 하나(리치봉 값이 같은 판끼리)
        f = S6A_DUMP_REGIONS(r)
        if not f.exists():
            wj(f, dump_regions.make(r.d, r.games()))
        dreg = jl(f)
        st["dump_regions"] = {"file": rel(f), "lines": dump_regions.source_lines(dreg)}
    specs, prev_last = {}, None
    for g in r.games():
        ev = jl(r.prep / "rec" / g / "paifu_rec.json")["events"]
        ats = [e["at"] for e in ev if e["type"] == "discard" and e.get("at") is not None]
        if g in auto:
            rr = jl(r.d / g / "result_read.json")
            trr = None
            if mrow[g]["end"] == "draw":
                t = rr.get("t_reveal_read") or (s1r.get(g) or {}).get("t_reveal")
                trr = to_ms(date, t) if t else None
            sd = SIDES[(mrow[g]["hero"] - bottom) % 4]
            if frame:
                specs[g] = ht_spec(g, mrow[g], bottom, ev, rr, frame["sides"][sd], prev_last, trr, frame_from, title)
            else:   # 녹화 틀 없음(설계서 8-13 (다)): wide = 화면 절반, band · search = 손패 줄 후보 1위(2 · 3위는 꾸러미 그림 · 표에만), 공개 상자는 안 만듦
                hr = s6a_half_regions(r, cfg, g, sd, min(ats), max(ats))
                # (11-25, 설계서 8-14 (가)) 강 · 울기 = 버림 기록기 덤프에서 자리마다 상자 하나(반장 전체) — 묻지 않고 그림에만, 답 값보다 이 값
                hr.update(dump_regions.regions_for(dreg, g, sd))
                specs[g] = ht_spec(g, mrow[g], bottom, ev, rr, hr, prev_last, trr, frame_from, title)
                specs[g].update(regions_mode="half", band_candidates=hr["_cands"], band_candidates_picks=hr["_picks"], band_candidates_rule=hr["_rule"],
                                regions_code=["river", "meld"], regions_code_from=f"{rel(S6A_DUMP_REGIONS(r))} — dump_regions.py(설계서 8-14 (가))",
                                regions_code_src={k: dump_regions.source_of(dreg, g, sd, k) for k in ("river", "meld")})
            wj(r.d / "s6a" / "_spec" / f"{g}.json", specs[g])
        prev_last = max(ats) if ats else prev_last
    # S6a-1 꾸러미
    pend, packed = [], dict(st.get("packed") or {})
    for g in auto:
        d = r.d / "s6a" / g
        if not (d / "pack.json").exists():
            t0 = time.time()
            p = run([PY, "-X", "utf8", HERE / "handtrack_prep.py", "pack", "--cfg", r.cfg_f, "--spec", r.d / "s6a" / "_spec" / f"{g}.json", "--out", d],
                    log=r.log(f"s6a_pack_{g}.log"))
            o = json.loads(p.stdout[p.stdout.rindex("JSON") + 4:].strip())
            packed[g] = {"window_ready": o["window_ready"], "window_reveal": o["window_reveal"], "overview": len(o["overview"]), "backs_rows": o["backs_rows"],
                         "wall_s": round(time.time() - t0, 1)}
        p = pkg("S6a", f"s6a_{g}", d, d / "TASK.md", d / "answer.json", game=g, kind="ht_prep")
        if not answered(p):
            pend.append(p)
    st.update(packed=packed, auto=auto, hand_settings=hand, frame_from=frame_from, mode="read")
    if not frame:
        st["half"] = {g: {"band": specs[g]["regions"]["band"], "candidates": [c["band"] for c in specs[g]["band_candidates"]]} for g in auto}
    r.save()
    if pend:
        return pend
    # S6a-3 답 적용 · 검사
    qs, res, fatal = [], {}, []
    for g in auto:
        pre = cfg.prefix_of(g)
        out_f = r.d / "s6a" / "_applied" / f"{g}.json"
        t0 = time.time()
        p = run([PY, "-X", "utf8", HERE / "handtrack_prep.py", "apply", "--cfg", r.cfg_f, "--spec", r.d / "s6a" / "_spec" / f"{g}.json",
                 "--answer", r.d / "s6a" / g / "answer.json", "--out", out_f], log=r.log(f"s6a_apply_{g}.log"))
        o = jl(out_f)
        if o["fatal"]:
            fatal.append(f"{g}: {'; '.join(o['fatal'])}")
            continue
        purged_fix = purge_fix(r, cfg, g) if o.get("config_written") else 0
        for q in o["questions"]:
            qs.append({"id": f"{pre}_s6a_{q['check']}", "kind": "boundary", "stage": "S6a", "game": g, "current": o["config"].get("t_ready") if "ready" in q["check"] else None,
                       "why": q["why"], "clip": q.get("clip"), "covered_by_setting": False})
        for n, u in enumerate(o.get("unsure") or [], 1):
            what = u.get("what") if isinstance(u, dict) else None
            why = u.get("why") if isinstance(u, dict) else str(u)
            qs.append({"id": f"{pre}_s6a_unsure_{n}", "kind": "boundary", "stage": "S6a", "game": g, "signal": "unsure", "current": what,
                       "why": f"준비 읽기 unsure — {what}: {why}" if what else f"준비 읽기 unsure — {why}", "covered_by_setting": False})
        res[g] = {"side": o["config"]["side"], "t_ready": o["config"]["t_ready"], "t_reveal": o["config"]["t_reveal"], "reveal_frame": o["config"]["reveal_frame"],
                  "post_sec": o["config"]["post_sec"], "changed": o["changed_regions"], "failed": [c["name"] for c in o["checks"] if not c["ok"]],
                  "unsure": len(o.get("unsure") or []), "pre_ready": o.get("hero_discards_before_ready"), "config_written": o.get("config_written"),
                  "purged": len(o.get("purged") or []), "purged_fix": purged_fix, "wall_s": round(time.time() - t0, 1)}
        if o.get("ready_late"):   # (11-25 밤, 설계서 8-16) 답에 늦은 후보가 있던 판 — 답의 값 · 늦은 후보 · 쓴 값(늦은 쪽을 쓴 판은 질문 아님 · report 에 표시)
            res[g]["ready_late"] = o["ready_late"]
    if fatal:
        raise SystemExit("S6a 답 꼴 이상 — " + " / ".join(fatal) + " (그 판의 s6a/<판>/answer.json 을 지우고 next 하면 같은 꾸러미가 다시 나옴)")
    r.state["questions_s6a"] = qs
    r.done("S6a", mode="read", hand_settings=hand, auto=auto, games=res, frame_from=frame_from, questions=len(qs))
    return []


def s6a_rules(r: Run):
    """(견줌용 — 기본 흐름에서 안 씀, init --s6a-rules) 옛 화소 규칙 자동 설정(handtrack_auto.py conf, 표 12-124 — 3반장에서 t_ready 2/11).
    손 추적 설정. 판마다: 공용 자리에 손 설정 · 판별 출력이 다 있으면 그대로(3반장). 아니면 자동 설정(handtrack_auto.py conf):
    side = rounds_meta 손패 주인 − 아래 자리, 영역 = 반장 설정 frame.sides[side](없으면 멈춤), t_start · t_reveal · reveal_frame · t_ready = 규칙
    (handtrack_auto.py 머리말). 그 안에서 features 도 돈다(t_ready 규칙이 띠 특징을 씀). 못 찾은 것은 최선 값을 넣고 질문(questions_s6a)."""
    cfg = r.cfg()
    st = r.stage("S6a")
    hand = [g for g in r.games() if all(p.exists() for p in ht_shared(g))]
    auto = [g for g in r.games() if g not in hand]
    if not auto:
        r.done("S6a", hand_settings=hand, auto=[], note="판마다 공용 자리에 손 설정 · 판별 출력이 있음 — 그대로 씀(자동 준비 안 함)")
        return []
    if not (cfg.app_record and r.app()):
        raise SystemExit(f"S6a: 손 설정이 없는 판 {auto} — 자동 판별 설정은 지금 앱 기록 판(W5 헤드 시각)만 된다")
    frame = cfg.frame
    frame_from = "실행 설정"
    if not frame:
        frame = hcfg.load(r.state["source_cfg"], check=False).frame
        frame_from = r.state["source_cfg"]
    date = cfg.recording["date"]
    meta = jl(r.d / cfg.meta_file.name)
    bottom = meta["bottom_seat"]
    mrow = {x["id"]: x for x in meta["rounds"]}
    w5 = jl(r.d / "w5" / "align.json")["rounds"]
    s1r = {x["id"]: x for x in jl(r.d / "s1" / "rounds.json")["rounds"]}
    side_of, bad = {}, []
    for g in auto:
        h = mrow[g].get("hero")
        if h is None:
            bad.append(f"{g}: 손패 주인 없음(rounds_meta hero null)")
            continue
        side_of[g] = SIDES[(h - bottom) % 4]
        if not frame or side_of[g] not in (frame.get("sides") or {}):
            bad.append(f"{g}: 손패 주인 자리 {side_of[g]} 의 녹화 틀 없음(반장 설정 frame.sides.{side_of[g]} — band · river · meld · reveal_region · wide · search)")
    if bad:
        raise SystemExit("S6a 멈춤 — " + "; ".join(bad))
    raw = jl(r.cfg_f)
    want = {"dir": rel(r.d / "handtrack"), "games": auto,
            "_note": "paifu_auto S6a: 이 판들의 손 추적 판별 설정 · 출력은 dir 아래(config/ · <판>/ · _work/) — handtrack/ht_redirect.py 가 실행 중에 경로를 돌림"}
    if raw.get("handtrack") != want or not raw.get("frame"):
        raw["handtrack"] = want
        raw.setdefault("frame", frame)
        wj(r.cfg_f, raw)
    qs = [q for q in r.state.get("questions_s6a") or [] if q.get("game") not in auto]
    res = dict(st.get("games") or {})
    prev_last = None
    for g in r.games():
        wr = w5.get(g) or {}
        hi = wr.get("head_interval") or {}
        s1 = s1r.get(g) or {}
        first = to_ms(date, hi["first"]) if hi.get("first") else to_ms(date, s1["t_start"]) + APP_START_LEAD_MS
        last = to_ms(date, hi["last"]) if hi.get("last") else to_ms(date, s1["t_end_play"])
        if g in auto:
            out_f = r.d / "s6a" / f"{g}.json"
            if not (out_f.exists() and all(p.exists() for p in ht_run_files(r, g)[:1] + ht_run_files(r, g)[4:])):
                side = side_of[g]
                m = mrow[g]
                F = jl(r.d / "s5" / "record" / f"{g}.json")["events"]
                hero = m["hero"]
                calls = sum(1 for e in F if e["type"] == "call" and e["seat"] == hero and e.get("kind") != "kakan")
                riichi = any(e["type"] == "discard" and e["seat"] == hero and e.get("riichi") for e in F)
                rr = jl(r.d / g / "result_read.json")
                spec = {"gid": g, "side": side, "regions": {k: frame["sides"][side][k] for k in ("band", "river", "meld", "reveal_region", "wide", "search")},
                        "side_rule": f"rounds_meta 손패 주인 {hero}({m.get('hero_rule')}) − 아래 자리 {bottom} → {side}",
                        "prev_last_ms": prev_last, "first_ms": first, "last_ms": last,
                        "t_reveal_read_ms": to_ms(date, rr["t_reveal_read"]) if m["end"] == "draw" and rr.get("t_reveal_read") else None,
                        "n_closed": 13 - 3 * calls, "result": {"draw": "draw_tenpai"}.get(m["end"], m["end"]), "riichi": riichi,
                        "result_how": f"rounds_meta end {m['end']} · {m.get('source')}", "frame_from": frame_from}
                wj(r.d / "s6a" / f"{g}_spec.json", spec)
                t0 = time.time()
                p = run([PY, "-X", "utf8", HERE / "handtrack_auto.py", "conf", "--cfg", r.cfg_f, "--spec", r.d / "s6a" / f"{g}_spec.json"],
                        log=r.log(f"s6a_{g}.log"))
                o = json.loads(p.stdout[p.stdout.rindex("JSON") + 4:].strip())
                o["wall_s"] = round(time.time() - t0, 1)
                wj(out_f, o)
            o = jl(out_f)
            c, rd, rv = o["config"], o["ready"], o["reveal"]
            pre = cfg.prefix_of(g)
            if not rd["ok"] or to_ms(date, c["t_ready"]) - first > HT_READY_LATE_S * 1000:
                why = (f"t_ready 규칙이 못 찾음 — {rd['rule']}" if not rd["ok"] else
                       f"t_ready {c['t_ready']} 가 첫 버림 {hms_of(first)} 뒤 {HT_READY_LATE_S}초 넘음")
                qs.append({"id": f"{pre}_s6a_ready", "kind": "boundary", "stage": "S6a", "game": g, "current": c["t_ready"], "why": why,
                           "clip": {"t0": c["t_start"], "t1": hms_of(to_ms(date, c["t_ready"]) + 10000)}, "covered_by_setting": False})
            if rd.get("arrange_flag"):
                qs.append({"id": f"{pre}_s6a_ready_arrange", "kind": "boundary", "stage": "S6a", "game": g, "current": c["t_ready"],
                           "why": f"t_ready {c['t_ready']} 바로 뒤 활동({rd.get('after_until')} 까지)에서 손패 띠가 {rd.get('after_moved_s')}초 움직임 — "
                                  "배패 정리 전 줄을 t_ready 로 잡았을 수 있음(그러면 첫 차례 창에 정렬 동작이 들어감)",
                           "clip": {"t0": c["t_ready"], "t1": rd.get("after_until") or hms_of(to_ms(date, c["t_ready"]) + 30000)}, "covered_by_setting": False})
            if not rv["ok"]:
                qs.append({"id": f"{pre}_s6a_reveal", "kind": "boundary", "stage": "S6a", "game": g, "current": c["reveal_frame"],
                           "why": f"공개 프레임을 못 찾아 짐작 — {rv.get('why')}", "clip": {"t0": hms_of(last), "t1": hms_of(last + 30000)},
                           "covered_by_setting": False})
            res[g] = {"side": c["side"], "t_start": c["t_start"], "t_ready": c["t_ready"], "ready_rule": rd["rule"], "t_reveal": c["t_reveal"],
                      "reveal_frame": c["reveal_frame"], "post_sec": c["post_sec"], "timing": o["timing"], "wall_s": o.get("wall_s")}
        prev_last = last
    r.state["questions_s6a"] = qs
    r.done("S6a", hand_settings=hand, auto=auto, games=res, frame_from=frame_from, questions=len(qs))
    return []


def s6b(r: Run):
    """손 추적 판별(run.py 의 segment · river · game — features 는 S6a 가 돌림, sheets 는 대조표 그림이라 뺌) + bandfit --write(sheet_band).
    S6a 가 자동으로 설정을 만든 판만. 판마다 결과가 있으면 그 단계는 건너뜀(handtrack_auto.run_one)."""
    a = r.stage("S6a")
    cfg = r.cfg()
    no_river = rec_path(r, cfg)   # (11-25, 설계서 8-13 (가)) 앱 기록 반장은 강 읽기를 안 돌림 — 차례 목록은 S6 에서 기록으로
    res = dict(r.stage("S6b").get("games") or {})
    for g in a.get("auto") or []:
        t0 = time.time()
        p = run([PY, "-X", "utf8", HERE / "handtrack_auto.py", "run", "--cfg", r.cfg_f, g] + (["--no-river"] if no_river else []), log=r.log(f"s6b_{g}.log"))
        o = json.loads(p.stdout[p.stdout.rindex("JSON") + 4:].strip())
        o["wall_s"] = round(time.time() - t0, 1)
        if o["ran"] or g not in res:
            res[g] = o
        # (11-25, 설계서 8-14 (나)) 공개 읽기를 안 돈 판(설정에 reveal_region 없음): game.json 을 판 결과 · 기록에서
        gf = r.d / "handtrack" / g / "game.json"
        if "game" in (o.get("skipped") or {}) and not gf.exists():
            gj = s6b_game_json(r, g)
            res[g]["game_json"] = "판 결과 · 기록에서 만듦(설계서 8-14 (나))" if gj else "판 결과에 끝 손패 없음 — 안 만듦"
            if gj:
                wj(gf, gj)
        wj(r.d / "s6b" / f"{g}.json", res[g])
    miss = {g: [rel(p) for p in ht_need(r, cfg, g) if not p.exists()] for g in a.get("auto") or []}
    miss = {g: v for g, v in miss.items() if v}
    if miss:
        raise SystemExit(f"S6b: 판별 출력이 없음 {miss}")
    r.done("S6b", games={g: {"ran": v["ran"], "timing": v["timing"], "wall_s": v["wall_s"], "sheet_band": v["sheet_band"],
                             **({"skipped": v["skipped"]} if v.get("skipped") else {}),
                             **({"game_json": v["game_json"]} if v.get("game_json") else {})} for g, v in res.items()})
    return []


def ht_report_lines(r: Run) -> list:
    a, b = r.stage("S6a"), r.stage("S6b")
    if not a.get("auto"):
        return []
    if a.get("mode") == "read" or a.get("status") != "done":
        L = ["", "## S6a · S6b 손 추적 설정(준비 읽기 — 설계서 8-8) · 판별", "",
             f"- 손 설정(공용 자리) 그대로: {a.get('hand_settings')} · 준비 읽기: {a.get('auto')} · 틀 출처 {a.get('frame_from')} · S6a 상태 {a.get('status')}", "",
             "| 판 | 자리 | t_ready(읽기) | t_ready 앞 손패 주인 버림 | t_reveal | reveal_frame | 고친 영역 | 검사 실패 | unsure | S6b 초 | sheet_band |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
        for g, v in (a.get("games") or {}).items():
            bb = (b.get("games") or {}).get(g) or {}
            L.append(f"| {g} | {v['side']} | {v['t_ready']} | {v.get('pre_ready')} | {v['t_reveal']} | {v['reveal_frame']} | {v.get('changed')} | {v.get('failed')} | "
                     f"{v.get('unsure')} | {bb.get('wall_s', '')} | {bb.get('sheet_band', '')} |")
        late = {g: v["ready_late"] for g, v in (a.get("games") or {}).items() if v.get("ready_late")}
        if late:   # (11-25 밤, 설계서 8-16) 줄이 선 때의 늦은 후보 — 쓴 판은 표시(질문 아님), 못 쓴 판은 질문(검사 ready_late)
            L += ["", "- 줄이 선 때의 늦은 후보(설계서 8-16 — 답에 t_ready_late 가 있던 판):"]
            for g, rl in late.items():
                if rl.get("which") == "late":
                    L.append(f"  - **{g}: 줄이 선 때를 늦은 후보로 씀**(답 {rl['answer']} → 늦은 후보 {rl['late']}, 판별 설정 t_ready {rl['used']}) · "
                             f"그 사이 버림 {len(rl.get('not_restored') or [])}장은 차례로 복원하지 않음 {rl.get('not_restored') or []}")
                else:
                    L.append(f"  - {g}: 늦은 후보 {rl['late']} 안 씀 — {rl['note']}(t_ready {rl['used']})")
        if a.get("half"):   # (11-25, 설계서 8-13 (다)) 녹화 틀 없음 — band 는 화면 절반 손패 줄 후보 1위에서 시작
            diff = [g for g, v in (a.get("games") or {}).items() if "band" in (v.get("changed") or [])]
            L += ["", f"- 녹화 틀 없음 → band · search = 화면 절반 손패 줄 후보 1위(공개 상자는 안 만듦). 준비 답의 band 가 후보 1위와 다른 판 "
                      f"{len(diff)}/{len(a.get('games') or {})}: {diff} (답 쪽을 씀)",
                  "- 후보(1 ~ 3위): " + " · ".join(f"{g} {v['candidates']}" for g, v in a["half"].items())]
            fd = S6A_DUMP_REGIONS(r)
            if fd.exists():   # (11-25, 설계서 8-14 (가)) 강 · 울기 = 버림 기록기 덤프(묻지 않음 · 답 값보다 이 값)
                L += [f"- 강 · 울기 영역 = 버림 기록기 덤프에서 자리마다 상자 하나(`{rel(fd)}` — 원본 [x0, y0, x1, y1], 괄호 = 출처 · 관측 수):"]
                L += ["  " + x for x in dump_regions.source_lines(jl(fd))]
        if a.get("status") != "done" and a.get("packed"):
            L += ["", "꾸러미(답 기다림): " + ", ".join(f"{g}(프레임 {v['window_ready'][2]} + {v['window_reveal'][2]}, 그림 {v['overview']})" for g, v in a["packed"].items())]
        return L
    L = ["", "## S6a · S6b 손 추적 설정 · 판별(자동 — 옛 화소 규칙, 견줌용)", "", f"- 손 설정(공용 자리) 그대로: {a.get('hand_settings')} · 자동: {a.get('auto')} · 틀 출처 {a.get('frame_from')}", "",
         "| 판 | 자리 | t_start | t_ready(규칙) | t_reveal | reveal_frame | S6a 초 | S6b 초 | sheet_band |", "|---|---|---|---|---|---|---|---|---|"]
    for g, v in (a.get("games") or {}).items():
        bb = (b.get("games") or {}).get(g) or {}
        L.append(f"| {g} | {v['side']} | {v['t_start']} | {v['t_ready']}({v['ready_rule']}) | {v['t_reveal']} | {v['reveal_frame']} | {v.get('wall_s')} | "
                 f"{bb.get('wall_s', '')} | {bb.get('sheet_band', '')} |")
    return L


# ------------------------------------------------------------------ S6 손패 차례
def han3(r: Run, *args, log=None, check=True):
    return run([PY, "-X", "utf8", HT / "han3.py", *args, "--hanchan", r.cfg_f], log=log, check=check)


def read_plan(r: Run) -> dict:
    """판마다 읽을 차례(han3 ids = 리치 뒤 · 울기 · skip 뺌) + 울기 차례(turn_fix kind call)."""
    p = han3(r, "ids", log=r.log("s6_ids.log"))
    ids = {}
    for ln in p.stdout.splitlines():
        if not ln.strip():
            continue
        g, _, lst = ln.partition(" ")
        ids[g] = [x for x in lst.strip().split(",") if x]
    fix = jl(r.prep / r.cfg().fix_file.name)
    calls = [k for k, v in fix.items() if not k.startswith("__") and v.get("kind") == "call"]
    return {"hand": ids, "call": calls}


def slotgrid_todo(r: Run) -> dict:
    """칸 틀 검출 캐시(_work/slotgrid_1117/det_<판>.json)에 빠진 프레임 수 — 0 이면 detect 를 안 돌림(캐시는 읽기만)."""
    code = (
        "import sys, json\n"
        f"sys.path.insert(0, {str(HT)!r})\n"
        "import han3, hanchan_cfg as hcfg\n"
        f"han3.configure(hcfg.load({str(r.cfg_f)!r}))\n"
        "han3.patch()\n"
        "import htcommon as hc, slotgrid as sg, turncut as tc\n"
        "out = {}\n"
        "for gid in han3.H3:\n"
        "    f = sg.OUT / f'det_{gid}.json'\n"
        "    have = set(int(k) for k in hc.jload(f)) if f.exists() else set()\n"
        "    need = {ms for t in tc.turns_of(gid) for ms in hc.frame_range(*sg.window(t))[::2]}   # slotgrid detect --step 기본 2 와 같게\n"
        "    out[gid] = {'cache': f.exists(), 'missing': len(need - have), 'need': len(need)}\n"
        "print('JSON' + json.dumps(out))\n")
    p = run([PY, "-X", "utf8", "-c", code], log=r.log("s6_slotgrid_check.log"))
    s = p.stdout
    return json.loads(s[s.index("JSON") + 4:].strip())


def slotgrid_seed(r: Run, cfg, todo: dict) -> dict:
    """(시험용 — init --slotgrid-seed, 설계서 8-14 끝 조건 4) 캐시가 아직 없는 실행 폴더 판에, 다른 실행(seed)의 칸 틀 검출 캐시를 복사한다 —
    두 판별 설정의 side · band · sheet_band 가 같을 때만(검출 · 가림 열이 이 셋에 달림). 복사는 이 실행 폴더 쪽으로만. 빠진 프레임은 그 뒤 detect 가 셈."""
    seed = ROOT / r.state["slotgrid_seed"]
    out = {}
    dst_dir = (r.d / "handtrack" / "_work" / "slotgrid_1117").resolve()
    for g, v in todo.items():
        if g not in set(cfg.ht_games):
            out[g] = "실행 폴더 판 아님 — 안 함"
            continue
        if v.get("cache"):
            out[g] = "캐시 있음 — 안 함"
            continue
        src = seed / "handtrack" / "_work" / "slotgrid_1117" / f"det_{g}.json"
        a, b = seed / "handtrack" / "config" / f"{g}.json", r.d / "handtrack" / "config" / f"{g}.json"
        if not (src.exists() and a.exists() and b.exists()):
            out[g] = "seed 캐시 · 설정 없음 — 안 함"
            continue
        ca, cb = jl(a), jl(b)
        diff = [k for k in ("side", "band", "sheet_band") if ca.get(k) != cb.get(k)]
        if diff:
            out[g] = f"설정 다름 {diff} — 안 함(새로 detect)"
            continue
        dst = dst_dir / src.name
        assert r.d.resolve() in dst.parents, dst
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        out[g] = f"복사 {rel(src)} (side · band · sheet_band 같음)"
    return out


def turns_after_fix(cfg, g: str) -> list:
    """han3 차례 목록(cfg.turns_file 의 그 판) + turn_fix(칸 고침 · __insert__ 끼움) — han3.apply_fix 와 같은 셈(han3 를 이 프로세스에 import 하지 않으려고 따로)."""
    T = jl(cfg.turns_file) if cfg.turns_file.exists() else {"games": []}
    gg = next((x for x in T["games"] if x["id"] == g), None)
    if gg is None:
        return []
    fx = jl(cfg.fix_file) if cfg.fix_file.exists() else {}
    turns = [dict(t) for t in gg["turns"]]
    for ins in fx.get("__insert__") or []:
        if not cfg.owns(ins["id"], g) or any(t["id"] == ins["id"] for t in turns):
            continue
        k = next((i for i, t in enumerate(turns) if t["id"] == ins["after"]), None)
        if k is None:
            continue
        turns.insert(k + 1, {"id": ins["id"], "label": ins["id"].split("_d")[1], "tile": ins["tile"], "sideways": ins.get("sideways", False), "synthetic": True})
    for t in turns:
        f = fx.get(t["id"]) or {}
        for k in ("tile", "sideways"):
            if k in f:
                t[k] = f[k]
    return turns


def turn_check_one(g: str, turns: list, events: list, hero: int, t_ready_ms: int) -> dict:
    """차례 수 검사 한 판. 차례가 되는 손패 주인 버림 = 고친 기록의 손패 주인 버림 중 기록기가 처음 본 때가 t_ready 뒤인 것
    (truthprep: t_ready 때 강에 이미 있던 버림은 '판 구간 전' — 차례 아님 · 리치 뒤 버림도 차례(읽기만 안 함) · 울려 나간 버림은 han3 fix 가 끼움)."""
    hd = [e for e in events if e["type"] == "discard" and e["seat"] == hero]
    exp = [e for e in hd if e.get("at") is not None and e["at"] > t_ready_ms]
    near = [f"{e['tile']}@{hms_of(e['at'])}" for e in hd if e.get("at") is not None and abs(e["at"] - t_ready_ms) <= S6_TURN_NEAR_MS]
    no_at = [e["tile"] for e in hd if e.get("at") is None]
    tt = [norm(t.get("tile")) if t.get("tile") else None for t in turns]
    et = [norm(e["tile"]) for e in exp]
    return {"turns": len(turns), "expected": len(exp), "same": len(turns) == len(exp), "tiles_same": tt == et, "turn_tiles": tt, "expected_tiles": et,
            "hero_discards": len(hd), "before_ready": len(hd) - len(exp) - len(no_at), "near_ready": near, "no_at": no_at,
            "synthetic": [t["id"] for t in turns if t.get("synthetic")], "t_ready": hms_of(t_ready_ms)}


def s6_turn_check(r: Run) -> dict:
    """S6 뒤 차례 수 검사(설계서 8-8): 판마다 차례 목록(han3 turns + turn_fix) 수 ↔ 고친 기록(_prep/rec/<판>/paifu_rec.json)의 손패 주인 버림 중 t_ready 뒤 것의 수.
    0 이면 zero(멈춤), 다르면 질문 <판>_s6_turns."""
    cfg = r.cfg()
    date = cfg.recording["date"]
    meta = {x["id"]: x for x in jl(r.d / cfg.meta_file.name)["rounds"]}
    ht_games = set(cfg.ht_games)
    games, qs, zero = {}, [], []
    for g in r.games():
        hero = meta[g].get("hero")
        if hero is None:
            continue
        cf_p = (cfg.ht_dir / "config" / f"{g}.json") if g in ht_games else (HT / "config" / f"{g}.json")
        t_ready = to_ms(date, jl(cf_p)["t_ready"])
        ev = jl(r.prep / "rec" / g / "paifu_rec.json")["events"]
        v = turn_check_one(g, turns_after_fix(cfg, g), ev, hero, t_ready)
        v["config"] = rel(cf_p)
        games[g] = v
        if v["turns"] == 0:
            zero.append(g)
        elif not v["same"]:
            qs.append({"id": f"{cfg.prefix_of(g)}_s6_turns", "kind": "boundary", "stage": "S6", "game": g, "current": v["turns"], "candidates": [v["expected"]],
                       "why": f"차례 목록 {v['turns']}차례 ≠ 고친 기록의 손패 주인 버림 중 t_ready({v['t_ready']}) 뒤 {v['expected']}장"
                              + (f" · t_ready 앞뒤 {S6_TURN_NEAR_MS // 1000}초 안 버림 {v['near_ready']}" if v["near_ready"] else "")
                              + f" — 차례 패 {v['turn_tiles']} / 기록 {v['expected_tiles']}",
                       "clip": {"t0": hms_of(t_ready - 10000), "t1": hms_of(t_ready + 30000)}, "covered_by_setting": False})
    return {"games": games, "questions": qs, "zero": zero}


REC_CHECK_FILE = "turns_record_check.json"   # han3 rturns · rcheck 가 <prep>/ 에 씀


def rec_check_summary(r: Run) -> dict:
    """han3 rturns · rcheck 검사(설계서 3-9 검사 표 가운데 지금 낼 수 있는 것) 판마다 요약 — 질문으로 올리는 것은 구현 4번(여기는 보고만)."""
    f = r.prep / REC_CHECK_FILE
    if not f.exists():
        return {}
    out = {}
    for g, v in jl(f).items():
        if v.get("error"):
            out[g] = {"error": v["error"]}
            continue
        fl = v.get("flags") or {}
        out[g] = {"turns": v.get("turns"), "pre_ready": v.get("pre_ready"), "no_at": v.get("no_at"), "call_turns": v.get("call_turns"),
                  "seg_how": v.get("seg_how"), "empty_windows": fl.get("empty_windows"), "overlap_windows": fl.get("overlap_windows"),
                  "tsumogiri_candidates": fl.get("tsumogiri_candidates"), "rows_ok": not fl.get("rows_mismatch"), "rows": v.get("rows")}
    return out


def rec_report_lines(r: Run) -> list:
    st = r.stage("S6")
    rc = st.get("record_check")
    if not rc:
        return []
    L = ["", "## S6 차례 목록 — 기록에서(설계서 8-13 (가)) · 검사(3-9)", "",
         f"- 차례 목록 출처: {st.get('turn_source')} · 검사 파일 `{rel(r.prep / REC_CHECK_FILE)}`(질문으로는 아직 안 올림 — 구현 4번)", "",
         "| 판 | 차례 | t_ready 앞 손패 주인 버림 | 시각 없는 버림 | 울기 차례 | 빈 창 | 겹친 창 | 쯔모기리 후보(창 안 band 움직임 0) | 줄 장수 ↔ 울기 수 |",
         "|---|---|---|---|---|---|---|---|---|"]
    for g, v in rc.items():
        if v.get("error"):
            L.append(f"| {g} | 오류 {v['error']} | | | | | | | |")
            continue
        rw = v.get("rows") or {}
        L.append(f"| {g} | {v['turns']} | {len(v['pre_ready'] or [])} {v['pre_ready'] or ''} | {v['no_at'] or ''} | {v['call_turns'] or ''} | {v['empty_windows'] or ''} | "
                 f"{v['overlap_windows'] or ''} | {v['tsumogiri_candidates'] or ''} | {'맞음' if v['rows_ok'] else '**다름**'}"
                 f"(판 결과 끝 손패 {rw.get('result_hand')} · 13 − 3 × 울기 {rw.get('hero_calls_not_kakan')} = {rw.get('want_closed_end')}) |")
    return L


def s6(r: Run):
    cfg = r.cfg()
    st = r.stage("S6")
    if not st.get("prepared"):
        # S6 재료(han3 turns → truthprep · turncut · slotgrid)는 판마다 손 추적 판별 설정 · 출력을 읽는다 — 손 설정 판은 공용 자리, S6a 가 자동으로
        # 만든 판은 실행 폴더 handtrack/(실행 설정 handtrack 칸 — han3 가 경로를 돌림). 어느 쪽에도 없으면 멈춤.
        need = {g: [p for p in ht_need(r, cfg, g) if not p.exists()] for g in r.games()}
        miss = {g: [rel(p) for p in v] for g, v in need.items() if v}
        st.pop("missing_handtrack", None)
        if miss:
            st["missing_handtrack"] = miss
            r.save()
            raise SystemExit("S6 재료(손패 차례 나누기 · 칸 틀 · 차례 꾸러미)는 판마다 손 추적 판별 설정 · 출력이 있어야 한다 — 판 "
                             f"{len(miss)}/{len(r.games())} 에 없음: " + "; ".join(f"{g}: {', '.join(v)}" for g, v in miss.items())
                             + " — S6a · S6b(손 추적 설정 · 판별)를 먼저(next --redo S6a).")
        r.save()
    if not st.get("prepared"):
        t0 = time.time()
        if rec_path(r, cfg):   # (11-25, 설계서 8-13 (가)) 앱 기록 반장: 차례 목록 · turn_fix 를 고친 기록에서 바로 → turncut → 검사(3-9 표)
            han3(r, "rturns", log=r.log("s6_rturns.log"))
            han3(r, "turncut", "build", *r.games(), log=r.log("s6_turncut.log"))
            han3(r, "rcheck", log=r.log("s6_rcheck.log"))
            st["turn_source"] = "기록(han3 rturns)"
            st["record_check"] = rec_check_summary(r)
        else:
            han3(r, "turns", log=r.log("s6_turns.log"))
            han3(r, "fix", "--write", log=r.log("s6_fix.log"))
            han3(r, "turncut", "build", *r.games(), log=r.log("s6_turncut.log"))
        # 차례 수 검사(설계서 8-8 "S6 뒤 검사") — han3 fix 는 차례 목록이 빈 판을 조용히 건너뛰므로 여기서 드러냄
        tc = s6_turn_check(r)
        st["turn_check"] = tc["games"]
        r.state["questions_s6"] = tc["questions"]
        r.save()
        if tc["zero"]:
            raise SystemExit(f"S6 차례 수 검사: 차례 목록이 빈 판 {tc['zero']} — 판별 설정(t_ready · band · river)이 틀렸을 수 있음. "
                             + "; ".join(f"{g}: 차례 0 · 고친 기록의 손패 주인 버림(t_ready 뒤) {tc['games'][g]['expected']}" for g in tc["zero"])
                             + " (S6a 답을 고치고 next --redo S6a)")
        only = r.state.get("s6_games")   # 시험용(init --s6-games): 칸 틀 검출 · 차례 꾸러미를 이 판들만
        todo = slotgrid_todo(r)
        if r.state.get("slotgrid_seed"):   # 시험용(init --slotgrid-seed)
            st["slotgrid_seed"] = slotgrid_seed(r, cfg, todo)
            st["slotgrid_before_seed"] = todo
            todo = slotgrid_todo(r)
        st["slotgrid"] = todo
        miss = [g for g, v in todo.items() if v["missing"] and (not only or g in only)]
        if miss:   # 새 반장이면 detect 가 캐시 폴더(_work/slotgrid_1117)에 쓴다 — 3반장 재생에서는 0 이어야 함
            han3(r, "slotgrid", "detect", *miss, log=r.log("s6_slotgrid_detect.log"))
        plan = read_plan(r)
        if only:
            plan = {"hand": {g: v for g, v in plan["hand"].items() if g in only}, "call": [t for t in plan["call"] if cfg.game_of(t) in only], "only": only}
        all_hand = [t for g in r.games() for t in plan["hand"].get(g, [])]
        # 울기 차례: 설정 call_turns(손) ↔ turn_fix 의 kind call(자동)
        src_calls = r.state.get("src_call_turns") or []
        st["call_turns"] = {"auto": plan["call"], "setting": src_calls, "same": sorted(plan["call"]) == sorted(src_calls)}
        if all_hand:
            han3(r, "opusread", "prep", "--ids", ",".join(all_hand), "--root", r.read.as_posix(), "--nosam", "--fromplan", log=r.log("s6_opusread_prep.log"))
        if plan["call"]:
            han3(r, "callprep", "--ids", ",".join(plan["call"]), "--root", r.read.as_posix(), log=r.log("s6_callprep.log"))
        st["plan"] = plan
        st["prepared"] = True
        st["prep_s"] = round(time.time() - t0, 1)
        r.save()
    plan = st["plan"]
    pend = []
    for tid in [t for g in r.games() for t in plan["hand"].get(g, [])] + plan["call"]:
        d = r.read / tid
        p = pkg("S6", f"s6_{tid}", d, d / "TASK.md", d / "answer.json", game=cfg.game_of(tid), turn=tid, kind="call" if tid in plan["call"] else "hand")
        if not answered(p):
            pend.append(p)
    if pend:
        return pend
    r.done("S6", turns=sum(len(v) for v in plan["hand"].values()) + len(plan["call"]))
    return []


# ------------------------------------------------------------------ 하위 프로세스 안에서 도는 조립 · 검사(han3_paifu 를 import — 패치가 이 프로세스에만)
INNER = r'''
import json, os, sys, copy, traceback
from collections import Counter
sys.path.insert(0, {here!r}); sys.path.insert(0, {ht!r})
os.environ["HAN3_FINAL"] = "result"
import hanchan_cfg as hcfg
import han3_paifu as hp
import han3
spec = json.loads(open({spec!r}, encoding="utf-8").read())
cfg = hcfg.load({cfg!r})
hp.configure(cfg, spec.get("out"))
han3.patch()
meta_all = hp.jl(han3.META)
order = [(r["id"], han3.meta_of(r["id"])) for r in meta_all["rounds"]]
norm = lambda t: ("5" + t[1]) if t and t[0] == "0" else t

def hero_hands(out):
    h = out["hero"]
    rows = []
    for e in out["events"]:
        if e["seat"] != h or e.get("hand") is None:
            continue
        if e["type"] == "draw":
            rows.append(("draw", list(e["hand"]) + ([e["tile"]] if e.get("tile") else [])))
        elif e["type"] == "call":
            rows.append(("call", list(e["hand"])))
    return rows

def four_check(out):
    """손패 주인 손패(뽑기 사건 시점의 14장) + 그때까지의 네 자리 버림 + 울기에서 손에서 나간 패 + 도라 표시패 ≤ 4."""
    bad = []
    seen = Counter(norm(t) for t in out.get("dora_indicators") or [])
    last = {{}}
    for n, e in enumerate(out["events"]):
        if e["type"] == "discard":
            seen[norm(e["tile"])] += 1
            last[e["seat"]] = e["tile"]
        elif e["type"] == "call":
            ts = [norm(t) for t in e.get("tiles") or []]
            got = norm(last.get(e.get("from"))) if e.get("from") != e["seat"] else None
            if got in ts:
                ts.remove(got)
            for t in ts:
                seen[t] += 1
        if e["seat"] == out["hero"] and e.get("hand") is not None and e["type"] == "draw":
            c = Counter(norm(t) for t in e["hand"] + ([e["tile"]] if e.get("tile") else []))
            over = {{k: c[k] + seen[k] for k in c if c[k] + seen[k] > 4}}
            if over:
                bad.append({{"event": n, "over": over}})
    return bad

res = {{}}
mode = spec["mode"]
if mode == "check":
    for gid, meta in order:
        try:
            out, info = hp.build(gid, meta, True)
            res[gid] = {{"ok": True, "hands": info["hands"], "missing": info["missing_answers"], "hand_count_problems": info.get("hand_count_problems") or [],
                        "four": four_check(out) if info["hands"] else [], "call_log": info.get("call_log")}}
        except BaseException as e:
            res[gid] = {{"ok": False, "error": f"{{type(e).__name__}}: {{e}}"[:600]}}
elif mode == "impact":
    base_root = han3.READ_ROOT
    base_cache = {{}}   # 판마다 지금 답으로 조립한 것(차례 97 모두를 잴 때 판마다 한 번만 — 8-2절)
    for job in spec["jobs"]:
        gid = job["game"]
        meta = dict(order)[gid]
        if gid not in base_cache:
            han3.READ_ROOT = base_root
            base_cache[gid] = hp.build(gid, meta, True)[0]
        b = base_cache[gid]
        bh = hero_hands(b)
        rows = []
        for c in job["cands"]:
            han3.READ_ROOT = c["root"]
            try:
                o, inf = hp.build(gid, meta, True)
                if not inf["hands"]:
                    rows.append({{"cand": c["name"], "ok": False, "error": "손패 없음 " + str(inf["missing_answers"])}})
                    continue
                oh = hero_hands(o)
                if len(oh) != len(bh):
                    rows.append({{"cand": c["name"], "ok": False, "error": f"순 수 다름 {{len(oh)}} ≠ {{len(bh)}}"}})
                    continue
                set_diff = sum(1 for x, y in zip(bh, oh) if Counter(x[1]) != Counter(y[1]))
                row_diff = sum(1 for x, y in zip(bh, oh) if x[1] != y[1])
                same_json = json.dumps(o, ensure_ascii=False) == json.dumps(b, ensure_ascii=False)
                rows.append({{"cand": c["name"], "ok": True, "hand_turns_changed": set_diff, "row_order_changed": row_diff,
                             "result_changed": o["result"] != b["result"], "paifu_same": same_json, "four": four_check(o)}})
            except BaseException as e:
                rows.append({{"cand": c["name"], "ok": False, "error": f"{{type(e).__name__}}: {{e}}"[:400]}})
        res[job["qid"]] = rows
    han3.READ_ROOT = base_root
print("JSON" + json.dumps(res, ensure_ascii=False))
'''


def inner(r: Run, spec: dict, tag: str) -> dict:
    sf = r.d / "_inner" / f"{tag}_spec.json"
    wj(sf, spec)
    code = INNER.format(here=str(HERE), ht=str(HT), spec=str(sf), cfg=str(r.cfg_f))
    cf = r.d / "_inner" / f"{tag}.py"
    wt(cf, code)
    p = run([PY, "-X", "utf8", cf], log=r.log(f"inner_{tag}.log"))
    s = p.stdout
    return json.loads(s[s.rindex("JSON") + 4:].strip())


# ------------------------------------------------------------------ S7 앞뒤 검사 · 다시 읽기
def active_answer(r: Run, tid: str) -> Path:
    return r.read / tid / "answer.json"


def answer_form_error(a: dict):
    """읽기 답 꼴 검사 — 이상하면 까닭, 맞으면 None. hand: end_order = (1 ~ n 에서 k 뺀 것) + D, tsumogiri: 1 ~ n 순열, call: gone · k · end_order 가 1 ~ n 을 한 번씩."""
    eo = [str(x) for x in a.get("end_order") or []]
    kind = a.get("kind")
    try:
        if kind == "hand":
            n = len(eo)
            k = int(a["k"])
            want = sorted([str(i) for i in range(1, n + 1) if i != k] + ["D"])
            return None if 1 <= k <= n and sorted(eo) == want else f"hand end_order {eo} · k {k}"
        if kind == "tsumogiri":
            n = len(eo)
            return None if sorted(eo) == sorted(str(i) for i in range(1, n + 1)) else f"tsumogiri end_order {eo}"
        if kind == "call":
            n = len(eo) + 3
            lab = sorted(int(x) for x in eo + [str(g) for g in a.get("gone") or []] + [str(a["k"])])
            return None if lab == list(range(1, n + 1)) else f"call 번호 {lab}"
        return f"kind {kind}"
    except (TypeError, ValueError, KeyError) as e:
        return f"꼴 {e}"


def s7(r: Run):
    cfg = r.cfg()
    st = r.stage("S7")
    plan = r.stage("S6")["plan"]
    # 기다리던 다시 읽기 꾸러미가 있으면 그 답을 먼저 넣는다
    pend = []
    for g, rr_ in (st.get("waiting") or {}).items():
        ps = rr_["pkgs"]
        if not all(answered(p) for p in ps):
            pend += [p for p in ps if not answered(p)]
    if pend:
        return pend
    for g, rr_ in list((st.get("waiting") or {}).items()):
        k = rr_["round"]
        for p in rr_["pkgs"]:
            tid = p["turn"]
            a = active_answer(r, tid)
            keep = r.read / tid / "answer_r0.json"
            if not keep.exists():
                shutil.copyfile(a, keep)
            shutil.copyfile(p["answer"], r.read / tid / f"answer_r{k}.json")
            shutil.copyfile(p["answer"], a)     # 다시 읽은 답으로 바꿔 보고, 아래 검사에서 안 맞으면 어긋남이 적은 쪽을 고름
        st.setdefault("history", []).append({"game": g, "round": k, "turns": [p["turn"] for p in rr_["pkgs"]]})
        del st["waiting"][g]
    t0 = time.time()
    res = inner(r, {"mode": "check", "out": str(r.d / "_s7" / "paifu")}, f"s7_check_{len(st.get('history') or [])}")
    st.setdefault("checks", []).append({"at": now(), "s": round(time.time() - t0, 1), "result": res})
    # 답 꼴 검사(rebuild_opus.back 은 번호가 겹치거나 D 가 없는 end_order 도 오류 없이 받아 뽑은 패를 None 으로 둠 — 11-24 음성 시험에서 확인)
    for g in r.games():
        for tid in game_answer_ids(r, g):
            why = answer_form_error(jl(active_answer(r, tid)))
            if why and res.get(g, {}).get("ok"):
                res[g] = {**res[g], "ok": False, "error": f"{tid}: 답 꼴 이상 — {why}"}
    bad = {g: v for g, v in res.items() if not v["ok"] or v.get("missing") or v.get("hand_count_problems") or v.get("four")}
    if r.state.get("user_final"):
        # 설계서 8-17 4-③(3-11 정한 것 3): 사용자 답 반영(apply) 뒤의 S7 은 다시 읽기 꾸러미를 내지 않는다(LLM 0) — 사용자 답은 최종.
        # 걸린 판은 final_bad 로 그대로 남기고, S9 가 <판>_s7_check 알림 질문으로 올린다.
        st["final_bad"] = bad
        r.done("S7", bad=list(bad), rereads=dict(r.state["reread"]), after_user=True)
        return []
    new_wait = {}
    for g, v in bad.items():
        n = r.state["reread"].get(g, 0)
        if n >= MAX_REREAD:
            continue
        ids = [t for t in plan["hand"].get(g, [])] + [t for t in plan["call"] if cfg.game_of(t) == g]
        region = ids   # 어긋난 구간: 복원은 끝 손패에서 거꾸로 가므로 실패한 판의 읽은 차례 전부(1단계 단순화)
        m = re.search(r"([a-z]\d\d_d\d+\w*)", v.get("error") or "")
        if m and m.group(1) in ids:
            region = ids[ids.index(m.group(1)):]
        region = [t for t in region if t not in set(r.state.get("answered") or [])]   # 사용자 답(apply)은 다시 읽기로 덮지 않음
        k = n + 1
        pk = []
        for tid in region:
            src = r.read / tid
            d = r.d / f"read_r{k}" / tid
            if not (d / "TASK.md").exists():
                (d / "work").mkdir(parents=True, exist_ok=True)
                for f in ("TASK.md", "frames.txt", "events.txt"):
                    if (src / f).exists():
                        wt(d / f, (src / f).read_text(encoding="utf-8").replace(src.as_posix() + "/answer.json", (d / "answer.json").as_posix())
                           .replace(src.as_posix() + "/work", (d / "work").as_posix()))
            pk.append(pkg("S7", f"s7_r{k}_{tid}", d, d / "TASK.md", d / "answer.json", game=g, turn=tid, reread=k))
        r.state["reread"][g] = k
        new_wait[g] = {"round": k, "pkgs": pk, "why": v.get("error") or v}
    if new_wait:
        st["waiting"] = new_wait
        r.save()
        return [p for w in new_wait.values() for p in w["pkgs"]]
    st["final_bad"] = bad
    r.done("S7", bad=list(bad), rereads=dict(r.state["reread"]))
    return []


# ------------------------------------------------------------------ S7s 판 supervisor(설계서 8-17 4-① · 3-10 · 8-10)
def sup_plan(r: Run) -> dict:
    """읽은 차례가 있는 판 · 그 가운데 supervisor 를 거칠 판(--sup-games) · 건너뛸 판 · 차례 없는 판."""
    only = (r.state.get("sup") or {}).get("games")
    have = [g for g in r.games() if game_answer_ids(r, g)]
    run_g = [g for g in have if not only or g in only]
    return {"games": run_g, "skipped": [g for g in have if g not in run_g], "no_turns": [g for g in r.games() if g not in have]}


def s7s(r: Run):
    """판마다 paifu_sup.py pack(이미 있으면 그대로) → 꾸러미 하나(TASK.md · 끝난 표시 decision.json)를 내고 멈춘다. 모두 마감되면 끝.
    마감 검사 · 답 반영(read/<차례>/answer.json · answer_r0.json · sup.json) · 질문(questions_sup.jsonl)은 paifu_sup.py done 이 한다."""
    st = r.stage("S7s")
    sp = sup_plan(r)
    pend, made = [], []
    for g in sp["games"]:
        d = r.d / "sup" / g
        if not (d / "pack.json").exists():
            p = run([PY, "-X", "utf8", SUP_PY, "pack", "--run", r.d, "--game", g], log=r.log(f"s7s_pack_{g}.log"), check=False)
            if p.returncode != 0 or not (d / "pack.json").exists():
                raise SystemExit(f"S7s: {g} 판 꾸러미를 못 만듦(rc {p.returncode}) — {(p.stdout or '')[-1500:]} {(p.stderr or '')[-800:]}")
            made.append(g)
        pk = pkg("S7s", f"sup_{g}", d, d / "TASK.md", d / "decision.json", game=g, kind="supervisor",
                 note="판 supervisor 하나 — 다시 읽기 작업자는 supervisor 가 스스로 띄운다(TASK.md 6). 끝난 표시 = paifu_sup.py done 이 쓰는 decision.json")
        if not answered(pk):
            pend.append(pk)
    st.update(games=sp["games"], skipped=sp["skipped"], no_turns=sp["no_turns"])
    if made:
        st.setdefault("packed", []).extend(made)
    if pend:
        r.save()
        return pend
    dec = {}
    for g in sp["games"]:
        x = jl(r.d / "sup" / g / "decision.json")
        dec[g] = {"applied": x.get("applied") or [], "asks": len(x.get("asks") or []), "reverted_for_ask": x.get("reverted_for_ask") or [],
                  "touched": {t: v.get("how") for t, v in (x.get("turns") or {}).items() if v.get("how")}, "counts": x.get("counts"),
                  "replayed_from": (jl(r.d / "sup" / g / "draft.json").get("replayed_from"))}
    r.done("S7s", games=sp["games"], skipped=sp["skipped"], no_turns=sp["no_turns"], sup_decided=dec,
           applied=sum(len(v["applied"]) for v in dec.values()), asks=sum(v["asks"] for v in dec.values()))
    return []


def sup_turns(r: Run) -> dict:
    """마감된 판의 차례별 supervisor 기록: {차례: decision.turns[차례] + game}. 판별 질문 줄은 'asks'."""
    out = {"turns": {}, "asks": {}, "games": []}
    for g in (r.stage("S7s").get("games") or []):
        d = r.d / "sup" / g
        if not (d / "decision.json").exists():
            continue
        x = jl(d / "decision.json")
        out["games"].append(g)
        for t, v in (x.get("turns") or {}).items():
            out["turns"][t] = {**v, "game": g}
        for q in jlines(d / "questions_sup.jsonl"):
            out["asks"].setdefault(q["id"], []).append(q)
    return out


# ------------------------------------------------------------------ S8 조립
def s8(r: Run):
    t0 = time.time()
    p = run([PY, "-X", "utf8", HERE / "han3_paifu.py", "--hands", "--dump", "--hanchan", r.cfg_f, "--out", r.paifu], log=r.log("s8_han3_paifu.log"))
    chk = jl(r.paifu / "_check.json")
    fails = {g: v["check"] for g, v in chk.items() if v.get("check")}
    r.done("S8", s=round(time.time() - t0, 1), files=len(list(r.paifu.glob("*.json"))), check_fail=fails)
    return []


# ------------------------------------------------------------------ S9 질문 목록 · 영향 · 보고서
ALT_RE = re.compile(r"\b([kj])\s*=\s*(\d+)")


def alt_candidates(ans: dict, n: int) -> list:
    """차례 답의 다른 후보: why 에 적힌 k=· j= 중 고른 값과 다른 것, 없으면 k · j 의 ±1."""
    out = []
    why = ans.get("why") or ""
    for kj, v in ALT_RE.findall(why):
        v = int(v)
        cur = ans.get(kj)
        if cur is not None and v != cur and (kj, v) not in out:
            out.append((kj, v))
    src = "why 에 적힌 후보"
    if not out:
        src = "k · j ±1"
        for kj in ("k", "j"):
            cur = ans.get(kj)
            if cur is None:
                continue
            for v in (cur - 1, cur + 1):
                if 1 <= v <= (n if kj == "k" else n + 1) and (kj, v) not in out:
                    out.append((kj, v))
    return out, src


def variant_answer(ans: dict, kj: str, v: int):
    """end_order(시작 줄 번호 1 ~ n 과 D)를 후보로 바꾼 답. k: 버린 번호 k ↔ v 맞바꿈(끝 줄에서 v 자리에 k), j: D 를 끝 줄 v 번째로."""
    eo = [str(x) for x in ans.get("end_order") or []]
    a = dict(ans)
    if kj == "k":
        k = str(ans["k"])
        if str(v) not in eo:
            return None
        eo = [k if x == str(v) else x for x in eo]
        a["k"] = v
    else:
        if "D" not in eo:
            return None
        eo.remove("D")
        eo.insert(v - 1, "D")
        a["j"] = v
    a["end_order"] = eo
    return a


def game_answer_ids(r: Run, g: str) -> list:
    plan = r.stage("S6")["plan"]
    cfg = r.cfg()
    return list(plan["hand"].get(g, [])) + [t for t in plan["call"] if cfg.game_of(t) == g]


def turn_jobs(r: Run, tids: list, tag: str) -> dict:
    """차례마다 후보 답 폴더(_impact/<tag>/<차례>/<후보>/ — 그 판 답 사본 + 그 차례만 후보)를 만들고 영향 계산 꾸러미를 낸다."""
    cfg = r.cfg()
    jobs, meta = [], {}
    # 후보 답 폴더는 매번 새로 만든다 — 옛 코드는 "없을 때만 복사" 라서 apply 로 답이 바뀐 뒤에도 같은 판 다른 차례의 옛 답 사본이 남았다(8-2 구현 때 발견)
    if (r.d / "_impact" / tag).exists():
        shutil.rmtree(r.d / "_impact" / tag)
    for tid in tids:
        g = cfg.game_of(tid)
        ans = jl(active_answer(r, tid))
        n = len([x for x in ans.get("end_order") or [] if x != "D"]) + (1 if ans.get("kind") == "hand" else 0)
        if ans.get("kind") != "hand":
            meta[tid] = {"cands": [], "src": f"kind {ans.get('kind')} — 후보 규칙 없음"}
            continue
        cands, src = alt_candidates(ans, n)
        cj = []
        for kj, v in cands:
            va = variant_answer(ans, kj, v)
            if va is None:
                continue
            name = f"{kj}={v}"
            root = r.d / "_impact" / tag / tid / name.replace("=", "")
            for t in game_answer_ids(r, g):
                f = root / t / "answer.json"
                if not f.exists():
                    f.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(active_answer(r, t), f)
            wj(root / tid / "answer.json", va)
            cj.append({"name": name, "root": root.as_posix()})
        meta[tid] = {"cands": [c["name"] for c in cj], "src": src}
        if cj:
            jobs.append({"qid": tid, "game": g, "cands": cj})
    res = inner(r, {"mode": "impact", "jobs": jobs}, f"impact_{tag}") if jobs else {}
    return {tid: {**meta[tid], "impact": res.get(tid, [])} for tid in tids}


def clip_of_turn(r: Run, tid: str):
    f = r.read / tid / "frames.txt"
    if not f.exists():
        return None
    ls = [x.split() for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
    g = r.cfg().game_of(tid)
    h0 = jl(r.d / "rounds_defs.json")[g]["t_from"][:2]
    def full(mmss):
        for h in (int(h0), int(h0) + 1):
            return f"{h:02d}:{mmss}"
    t0, t1 = ls[0][1], ls[-1][1]
    a = full(t0)
    b = full(t1) if t1 >= t0 else f"{int(h0) + 1:02d}:{t1}"
    return {"t0": a, "t1": b, "frames": len(ls)}


def dora_of(t):
    t = norm(t)
    n, s = int(t[0]), t[1]
    if s == "z":
        return f"{n % 4 + 1}z" if n <= 4 else f"{(n - 5 + 1) % 3 + 5}z"
    return f"{n % 9 + 1}{s}"


def result_jobs(r: Run) -> list:
    """판 결과 질문(규칙: result_read.json 의 uncertain 에 '뒷도라 · ura' → 뒷도라 고르기, '해저' → 예/아니오). 영향 = 후보 패보를 han3_check.dart 로 다시 셈."""
    sys.path.insert(0, str(HERE))
    cfg = r.cfg()
    qs = []
    variants = []
    for g in r.games():
        rr = jl(r.d / g / "result_read.json")
        unc = rr.get("uncertain") or []
        base = jl(r.paifu / f"{g}.json")
        pre = cfg.prefix_of(g)
        if any(("ura" in u or "뒷도라" in u) for u in unc) and rr.get("ura_indicators"):
            # 후보 = 지금 읽은 표시패 말고 34종 모두 — 점수(총액 · 역)가 바뀌는 패만 후보로 남긴다(리치가 아니거나 어느 패든 같으면 영향 0)
            cur = rr["ura_indicators"][0]
            for t in [f"{i}{s}" for s in "mpsz" for i in range(1, 10 if s != "z" else 8)]:
                if t == norm(cur):
                    continue
                v = copy.deepcopy(base)
                v["id"] = f"{g}__ura_{t}"
                v["ura_indicators"] = [t] + list(v["ura_indicators"][1:])
                variants.append((f"{pre}_ura", t, v))
            qs.append({"id": f"{pre}_ura", "kind": "pick", "stage": "S4", "game": g, "current": cur,
                       "candidates": None, "why": next(u for u in unc if "ura" in u or "뒷도라" in u),
                       "rule": "uncertain 에 ura · 뒷도라 → 다른 34종 표시패로 점수를 다시 셈", "clip_def": "t_reveal ~ +15초"})
        if any("해저" in u for u in unc):
            v = copy.deepcopy(base)
            v["id"] = f"{g}__haitei_flip"
            chk = jl(r.paifu / "_check.json")[g]
            cur = chk.get("wall_left_end") == 0
            v["result"]["flags"] = {**(v["result"].get("flags") or {}), "last_tile": not cur}
            variants.append((f"{pre}_haitei", "아니오" if cur else "예", v))
            qs.append({"id": f"{pre}_haitei", "kind": "yesno", "stage": "S4", "game": g, "current": "예" if cur else "아니오",
                       "candidates": ["아니오" if cur else "예"], "why": next(u for u in unc if "해저" in u), "rule": "uncertain 에 해저",
                       "clip_def": "t_end_play − 25초 ~ t_reveal + 5초"})
    if not variants:
        return qs
    vd = r.d / "_impact" / "result"
    paths = []
    for qid, name, v in variants:
        f = vd / f"{v['id']}.json"
        wj(f, v)
        paths.append(f)
    import han3_paifu as hp   # dart_check 만 씀(모듈 값은 안 씀)
    chk = {}
    for i in range(0, len(paths), 20):   # dart.bat 명령 줄 길이(8191자) 때문에 20개씩, 저장소 기준 상대 경로로
        chk.update(hp.dart_check([Path(rel(x)) for x in paths[i:i + 20]]))
    base_chk = jl(r.paifu / "_check.json")
    byq = {q["id"]: q for q in qs}
    for qid, name, v in variants:
        q = byq[qid]
        g = v["id"].split("__")[0]
        b, c = base_chk[g], chk.get(v["id"], {})
        bs, cs = b.get("score") or {}, c.get("score") or {}
        q.setdefault("impact", []).append({"cand": name, "ok": "score" in c, "result_changed": (bs.get("total"), bs.get("yaku")) != (cs.get("total"), cs.get("yaku")),
                                           "score": {"now": bs.get("summary"), "cand": cs.get("summary")}, "hand_turns_changed": 0})
    for q in qs:
        if q["kind"] == "pick" and q["id"].endswith("_ura"):
            ch = [x for x in q["impact"] if x["result_changed"]]
            q["candidates"] = [x["cand"] for x in ch][:6] + ([f"… 그 밖 {len(ch) - 6}종"] if len(ch) > 6 else [])
            q["impact_note"] = f"34종 중 지금 표시패 말고 {len(q['impact'])}종을 넣어 봄 — 점수가 바뀌는 패 {len(ch)}종" + (f"(예: {ch[0]['cand']} → {ch[0]['score']['cand']})" if ch else "")
            q["impact"] = ch or q["impact"][:1]
    return qs


def summarize_impact(rows):
    ok = [x for x in rows if x.get("ok")]
    if not rows:
        return {"max_hand_turns": None, "result_changed": None, "zero": False}
    zero = bool(ok) and all(x.get("hand_turns_changed", 0) == 0 and not x.get("result_changed") and x.get("paifu_same", True) for x in ok) and len(ok) == len(rows)
    return {"max_hand_turns": max((x.get("hand_turns_changed", 0) for x in ok), default=0), "result_changed": any(x.get("result_changed") for x in ok), "zero": zero}


def text_fields(o, path=""):
    """답 안의 문자열 칸 모두(목록 · 사전 안까지) — (칸 경로, 글). apply 가 붙인 user_* 칸(사용자 글)은 읽기 답이 아니라서 뺀다."""
    if isinstance(o, str):
        yield path, o
    elif isinstance(o, dict):
        for k, v in o.items():
            if not str(k).startswith("user"):
                yield from text_fields(v, f"{path}.{k}" if path else str(k))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from text_fields(v, f"{path}[{i}]")


def snip(s: str, i: int, n: int, w: int = 20) -> str:
    return " ".join(s[max(0, i - w): i + n + w].split())


def hedge_hits(ans: dict) -> list:
    """8-3절(v2) 신호 1. 걸린 말마다 {word, field, snippet(앞뒤 20자), low? · num?}. 부정 꼴("가려지지 않아 확실")은 거르지 않음(규칙대로).
    word: (a) "확신"(뒤 10자 안 낮 · 중간 · 약하 · 없 — low 칸에 걸린 글자) · (b) "%"(숫자 % 의 숫자 < 90 — num 칸) · 그 밖은 말 목록의 말."""
    hits = []
    for field, s in text_fields(ans):
        for m in re.finditer(re.escape(HEDGE_CONF_KEY), s):
            after = s[m.end(): m.end() + HEDGE_CONF_WIN]
            low = [w for w in HEDGE_CONF_LOW if w in after]
            if low:
                hits.append({"word": HEDGE_CONF_KEY, "field": field, "snippet": snip(s, m.start(), len(HEDGE_CONF_KEY)), "low": low})
        for m in HEDGE_PCT_RE.finditer(s):
            v = float(m.group(1))
            if v < HEDGE_PCT_MAX:
                hits.append({"word": "%", "field": field, "snippet": snip(s, m.start(), m.end() - m.start()), "num": v})
        for w in HEDGE_WORDS:
            for m in re.finditer(re.escape(w), s):
                hits.append({"word": w, "field": field, "snippet": snip(s, m.start(), len(w))})
    return hits


def turn_signal(ans: dict):
    """질문으로 올릴 신호 목록(unsure · hedge:<말,…>)과 걸린 말 자세히."""
    sig = []
    if ans.get("unsure"):
        sig.append("unsure")
    hh = hedge_hits(ans)
    if hh:
        words = list(dict.fromkeys(h["word"] for h in hh))
        sig.append("hedge:" + ",".join(words))
    return sig, hh


def sig_field(sig: list):
    """질문 줄의 signal 칸: 하나면 글, 둘 이상(unsure + hedge)이면 목록."""
    return sig[0] if len(sig) == 1 else list(sig)


def turn_no(tid: str):
    m = re.search(r"_d(\d+)(\w*)$", tid)
    return (int(m.group(1)), m.group(2)) if m else (999, tid)


def s9(r: Run):
    cfg = r.cfg()
    plan = r.stage("S6")["plan"]
    t0 = time.time()
    defs = jl(r.d / "rounds_defs.json")
    all_ids = [t for g in r.games() for t in plan["hand"].get(g, [])] + plan["call"]
    answers = {t: jl(active_answer(r, t)) for t in all_ids}
    sigs = {t: turn_signal(answers[t]) for t in all_ids}
    raised = [t for t in all_ids if sigs[t][0]]       # 신호 1(확신 말) 또는 unsure — 8-2절 · 말 목록과 숫자 확신은 8-3(v2)
    human = r.state.get("human_picked_1123") or {}
    imp = turn_jobs(r, all_ids, "turns")              # 신호 2 를 위해 차례 모두에 영향(후보 규칙은 1단계 그대로)
    t_imp = round(time.time() - t0, 1)
    asked, hidden = [], []

    def turn_row(tid, **kw):
        a = answers[tid]
        m = imp[tid]
        return {"id": tid, "kind": "turn_slot", "stage": "S6", "game": cfg.game_of(tid), "turn": tid.split("_d")[1],
                "current": {"kind": a.get("kind"), "k": a.get("k"), "j": a.get("j")}, "candidates": m["cands"], "candidate_source": m["src"],
                "clip": clip_of_turn(r, tid), "impact": m["impact"], "impact_summary": summarize_impact(m["impact"]), **kw}

    sup = sup_on(r)   # 판 supervisor 단계(설계서 8-17 4-①)가 켜진 실행이면 차례 질문 출처 · 표본 규칙이 바뀜(끄면 아래 v2 그대로)
    su = sup_turns(r) if sup else None
    if not sup:
        for tid in raised:
            sig, hh = sigs[tid]
            q = turn_row(tid, signal=sig_field(sig), hedge_hits=hh,
                         rule=" · ".join(["답의 unsure: true" if s == "unsure" else f"8-3 신호 1 확신 말({s[6:]})" for s in sig]))
            (hidden if q["impact_summary"]["zero"] else asked).append(q)
    else:
        for q in sup_turn_questions(r, cfg, all_ids, answers, su, turn_row):
            (hidden if q["impact_summary"]["zero"] else asked).append(q)
    n_turn_asked = len(asked)   # 여기까지가 차례 질문 — 아래(판 결과 · S0 ~ S6 질문)는 두 길 모두 같음
    for q in result_jobs(r):
        g = q["game"]
        d = defs[g]
        if q["kind"] == "yesno":
            q["clip"] = {"t0": hms_of(to_ms(cfg.recording["date"], d["t_end_play"]) - 25000), "t1": hms_of(to_ms(cfg.recording["date"], d["t_reveal"]) + 5000)}
        else:
            q["clip"] = {"t0": d["t_reveal"], "t1": hms_of(to_ms(cfg.recording["date"], d["t_reveal"]) + 15000)}
        q["impact_summary"] = summarize_impact(q.get("impact") or [])
        (hidden if q["impact_summary"]["zero"] else asked).append(q)
    for key in ("questions_s0", "questions_s1", "questions_w5", "questions_s4", "questions_s5", "questions_s6a", "questions_s6"):   # s0 · w5 · s6a = 앱 기록 우선 반장만(3반장은 없음) · s6 = 차례 수 검사
        for q in r.state.get(key) or []:
            if q.get("kind") == "record" and "_rec_" in q["id"]:
                # 남의 강 한 칸 — 손패 주인 손패 · 결과 점수는 안 바뀌고 패보의 그 버림 한 칸만 바뀜. 영상 = 그 칸을 기록기가 처음 본 때 −5 ~ +10초
                side, i = q["id"].split("_rec_")[1].rsplit("_", 1)
                g = q["game"]
                use = next((o for o in jl(r.d / r.cfg().recfix_file.name).get(g, []) if o.get("op") == "use_run"), None)
                dart = jl(r.d / g / (use["run"] if use else "") / "dart_overlay.json") if use else jl(r.d / g / "dart_overlay.json")
                sl = next((x for x in dart[side]["slots"] if str(x["i"]) == i), None)
                if sl and sl.get("first_at"):
                    t = to_ms(cfg.recording["date"], sl["first_at"])
                    q["clip"] = {"t0": hms_of(t - 5000), "t1": hms_of(t + 10000)}
                q["impact_summary"] = {"max_hand_turns": 0, "result_changed": False, "river_cells": 1, "zero": False}
            if q.get("covered_by_setting"):
                hidden.append({**q, "hidden_reason": "설정(11-23 손 파일)이 덮음"})
            else:
                asked.append(q)
    asked += check_questions(r)   # 설계서 8-17 4-③: 검사에 걸린 채 남은 판 → 알림 질문 <판>_s7_check(걸린 판이 없으면 0 — 질문 파일은 전과 같음)
    for q in hidden:
        q.setdefault("hidden_reason", "hidden_zero_impact")

    def rank(q):
        s = q.get("impact_summary") or {}
        return (0 if s.get("result_changed") else 1, -(s.get("max_hand_turns") or 0), q["id"])
    n_other_asked = len(asked) - n_turn_asked
    if not sup:
        samples, no_impact, zero_pool = v2_samples(r, cfg, all_ids, set(raised), imp, turn_row)
    else:
        # 설계서 8-17 4-① 표본: 반장당 SAMPLE_PER_HANCHAN — set → 다시 읽기로 바뀜 → 영향 큰 순. 질문에 오른 차례(숨김 포함)는 뺌
        q_turns = {q["id"] for q in asked[:n_turn_asked] + hidden if q.get("kind") == "turn_slot"}
        cands, no_impact, zero_pool = sup_sample_cands(all_ids, r.games(), cfg.game_of, imp, su["turns"], q_turns)
        samples = []
        for rank_i, c in enumerate(sup_sample_pick(cands), 1):
            t = c["id"]
            samples.append(turn_row(t, sample=True, signal=["sample:sup_set", "sample:sup_reread", "sample:impact"][c["tier"]], sample_rank=rank_i,
                                    pool_size=len(cands), sample_tier=SAMPLE_TIERS[c["tier"]],
                                    sup=(su["turns"].get(t) or {}).get("how"),
                                    rule=f"8-17 4-① 표본(반장당 {SAMPLE_PER_HANCHAN}): {SAMPLE_TIERS[c['tier']]} — 후보 {len(cands)}차례 중 {rank_i}번째"))
        # 견줌용: 낱말 규칙(v2)이었다면 — 차례 질문(영향 0 숨김) + 그 밖의 질문(같음) + 표본(판마다 2)
        v2_turn = [t for t in raised if not summarize_impact(imp[t]["impact"])["zero"]]
        v2_samp, _, _ = v2_samples(r, cfg, all_ids, set(raised), imp, turn_row)
    done_ids = set(r.state.get("answered") or [])   # apply 로 사용자가 답한 칸은 다시 묻지 않음(보고서에 '사용자 답' 으로) — 표본에도 같게(8-2)
    for lst in (asked, samples):
        for q in [q for q in lst if q["id"] in done_ids]:
            lst.remove(q)
            hidden.append({**q, "hidden_reason": "사용자 답(apply)"})
    asked.sort(key=rank)
    wt(r.d / "questions.jsonl", "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in asked))
    wt(r.d / "samples.jsonl", "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in samples))
    wt(r.d / "questions_hidden.jsonl", "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in hidden))
    qids = {q["id"] for q in asked}
    sids = {q["id"] for q in samples}
    hid = {q["id"]: q for q in hidden}
    sig_count = Counter()
    for t in raised:
        s_ = sigs[t][0]
        sig_count["both" if len(s_) == 2 else ("unsure" if s_ == ["unsure"] else "hedge")] += 1
    if not sup:
        r.state["signals"] = {"turns_total": len(all_ids), "raised": len(raised), "by_signal": dict(sig_count),
                              "raised_ids": {t: sig_field(sigs[t][0]) for t in raised},
                              "asked_turns": sorted(t for t in raised if t in qids), "samples": [q["id"] for q in samples],
                              "no_impact": no_impact, "sample_zero_excluded": zero_pool, "impact_s": t_imp, "rule": "8-3 v2"}
    else:
        v2q = [t for t in v2_turn if t not in done_ids]
        other_q = [q for q in asked if q.get("kind") != "turn_slot"]
        v2s = [q["id"] for q in v2_samp if q["id"] not in done_ids]
        r.state["signals"] = {"turns_total": len(all_ids), "rule": "8-17 4-① supervisor", "sup_games": su["games"],
                              "sup_skipped": r.stage("S7s").get("skipped") or [],
                              "asked_turns": sorted(q["id"] for q in asked if q.get("kind") == "turn_slot"),
                              "asked_turns_by_signal": dict(Counter(str(q.get("signal")) for q in asked if q.get("kind") == "turn_slot")),
                              "samples": [q["id"] for q in samples], "sample_tiers": {q["id"]: q.get("sample_tier") for q in samples},
                              "sample_pool": len(cands), "no_impact": no_impact, "sample_zero_excluded": zero_pool, "impact_s": t_imp,
                              "v2_compare": {"raised": len(raised), "by_signal": dict(sig_count), "raised_ids": {t: sig_field(sigs[t][0]) for t in raised},
                                             "turn_questions": len(v2q), "turn_questions_ids": v2q,
                                             "turn_hidden_zero": [t for t in raised if summarize_impact(imp[t]["impact"])["zero"]],
                                             "other_questions": len(other_q), "questions": len(v2q) + len(other_q), "samples": len(v2s),
                                             "sample_ids": v2s, "total": len(v2q) + len(other_q) + len(v2s),
                                             "note": "낱말 규칙(8-3 v2)이 차례 질문을 만들고 표본이 판마다 2 였다면의 수(사용자 답 칸은 뺌) — 질문은 만들지 않음, 견줌용"},
                              "other_asked_before_user_hide": n_other_asked}
    r.state["human_compare"] = {"turns": {t: {**imp[t], "summary": summarize_impact(imp[t]["impact"]), "unsure": answers[t].get("unsure"),
                                              "signal": sig_field(sigs[t][0]) if sigs[t][0] else None,
                                              "in_asked": t in qids, "in_sample": t in sids, "in_hidden": t in hid,
                                              "hidden_reason": (hid.get(t) or {}).get("hidden_reason"),
                                              "hidden_sample": bool((hid.get(t) or {}).get("sample"))} for t in human.get("turns", [])}}
    r.state.pop("sample", None)   # 1단계의 무작위 표본(씨앗 1124)은 8-2 로 바꿈
    r.done("S9", asked=len(asked), samples=len(samples), hidden=len(hidden), s=round(time.time() - t0, 1))
    if not sup:
        write_report(r, asked, hidden, samples)
        return []
    src = write_sources(r, asked, hidden, su)
    r.stage("S9")["sources"] = src["totals"]
    r.save()
    write_report(r, asked, hidden, samples, sup={"su": su, "sources": src})
    return []


S7_CHECK_KEYS = ("ok", "error", "missing", "hand_count_problems", "four")   # S7 앞뒤 검사 결과에서 알림 질문 글에 옮기는 칸(hands · call_log 는 뺌)


def check_questions(r: Run) -> list:
    """설계서 8-17 4-③: 검사에 걸린 채 남은 판(S7 final_bad · S8 check_fail) → 판마다 알림 질문 하나 <판 앞 세 글자>_s7_check.
    why = 검사 글 그대로(S7 은 S7_CHECK_KEYS 칸만 · S8 은 han3_check.dart 의 check 값). 반영 길 · 영상(clip) 없음 — 확인 페이지 묶음 C."""
    s7b = r.stage("S7").get("final_bad") or {}
    s8b = r.stage("S8").get("check_fail") or {}
    out = []
    for g in r.games():
        if g not in s7b and g not in s8b:
            continue
        chk, parts = {}, []
        if g in s7b:
            chk["S7"] = {k: s7b[g][k] for k in S7_CHECK_KEYS if k in s7b[g] and (k == "ok" or s7b[g][k])}
            parts.append("S7 앞뒤 검사: " + json.dumps(chk["S7"], ensure_ascii=False))
        if g in s8b:
            chk["S8"] = s8b[g]
            parts.append("S8 조립 검사(han3_check.dart): " + json.dumps(s8b[g], ensure_ascii=False))
        out.append({"id": f"{g[:3]}_s7_check", "kind": "check", "stage": "S7" if g in s7b else "S8", "game": g, "why": " / ".join(parts),
                    "check": chk, "after_user": bool(r.state.get("user_final")),
                    "impact_summary": {"max_hand_turns": None, "result_changed": False, "zero": False},
                    "rule": "8-17 4-③ 검사에 걸린 채 남은 판 — 알림(반영 길 없음)"})
    return out


def v2_samples(r: Run, cfg, all_ids: list, raised_set: set, imp: dict, turn_row):
    """8-2 · 8-3(v2) 표본 — supervisor 단계가 꺼진 실행의 표본(켜진 실행에서는 견줌 수만).
    신호 2 — 영향 큰 차례 표본(8-2절): 질문에 안 오른 차례(신호 1 · unsure 아님) 모두, 후보 중 가장 큰 "바뀌는 순 수" 로 줄 세워 판마다 위 2차례.
    같으면 순이 이른 차례. 영향을 못 잰 차례(후보 규칙 없음 · 후보 모두 조립 실패)는 줄에 못 서므로 표본에서 빼고 보고서에 수 · 까닭.
    8-3(v2): 바뀌는 순 수가 0 인 차례는 줄에 못 선다(판마다 많아야 2 — 모자라면 모자란 대로). 뺀 수는 zero_pool 에."""
    samples, no_impact, zero_pool = [], {}, {}
    for g in r.games():
        pool = []
        for t in [t for t in all_ids if cfg.game_of(t) == g and t not in raised_set]:
            rows = imp[t]["impact"]
            ok = [x for x in rows if x.get("ok")]
            if not ok:
                why = imp[t]["src"] if not imp[t]["cands"] else "후보 조립 모두 실패 — " + "; ".join(sorted({str(x.get("error"))[:80] for x in rows}))
                no_impact[t] = why
                continue
            mx = max(x.get("hand_turns_changed", 0) for x in ok)
            if mx == 0:
                zero_pool.setdefault(g, []).append(t)
                continue
            pool.append((-mx, turn_no(t), t))
        for rank_i, (_, _, t) in enumerate(sorted(pool)[:SAMPLE_PER_GAME], 1):
            samples.append(turn_row(t, sample=True, signal="sample:impact", sample_rank=rank_i, pool_size=len(pool),
                                    rule=f"8-2 신호 2(8-3: 영향 0 뺌): 영향 큰 차례 표본(판마다 {SAMPLE_PER_GAME}, 줄 {len(pool)}차례 중 {rank_i}번째)"))
    return samples, no_impact, zero_pool


def sup_turn_questions(r: Run, cfg, all_ids: list, answers: dict, su: dict, turn_row) -> list:
    """supervisor 단계가 켜진 실행의 차례 질문(설계서 8-17 4-①): 마감된 판은 supervisor 의 ask(questions_sup.jsonl — 한 차례에 ask 가 여럿이면 한 줄),
    supervisor 를 안 거친 판(--sup-games 로 건너뜀 · 마감 전)은 답의 unsure 차례. 낱말 규칙은 질문을 만들지 않음."""
    out = []
    done_games = set(su["games"])
    for t in all_ids:
        g = cfg.game_of(t)
        if g in done_games:
            qs = su["asks"].get(t)
            if not qs:
                continue
            out.append(turn_row(t, stage="S7s", signal="sup:ask", sup_candidates=[q.get("candidates") for q in qs], sup_why=[q.get("why") for q in qs],
                                sup_draft=next((q.get("sup_draft") for q in qs if q.get("sup_draft")), None),
                                sup_file=rel(r.d / "sup" / g / "questions_sup.jsonl"),
                                rule="판 supervisor 의 ask(설계서 8-17 4-① — supervisor 가 못 푼 차례)"))
        elif answers[t].get("unsure"):
            out.append(turn_row(t, signal="unsure", rule="답의 unsure: true — supervisor 를 안 거친 판(설계서 8-17 4-①)"))
    return out


def sup_sample_cands(all_ids: list, games: list, game_of, imp: dict, sup_turn: dict, exclude: set):
    """표본 후보(설계서 8-17 4-①). tier 0 = supervisor 가 직접 정한 차례(마감 초안이 set), 1 = 다시 읽기로 답이 바뀐 차례(마감 초안이 r<n> 이고 반영됨),
    2 = 그 밖에서 영향(바뀌는 순 수 최대)이 0 보다 큰 차례. 질문에 오른 차례(exclude)는 뺌. tier 2 에 못 서는 차례: 영향을 못 잰 것(no_impact) · 0(zero).
    tier 0 · 1 은 영향이 0 이거나 못 재도 넣는다(supervisor 가 손댄 표시 — 3-10 정한 것 2 · 3-5)."""
    gi = {g: i for i, g in enumerate(games)}
    cands, no_impact, zero = [], {}, {}
    for t in all_ids:
        if t in exclude:
            continue
        rows = imp[t]["impact"]
        ok = [x for x in rows if x.get("ok")]
        mx = max(x.get("hand_turns_changed", 0) for x in ok) if ok else None
        v = sup_turn.get(t) or {}
        fr = str(v.get("from") or "")
        if fr == "set":
            tier = 0
        elif re.fullmatch(r"r\d+", fr) and v.get("applied"):
            tier = 1
        else:
            if not ok:
                no_impact[t] = imp[t]["src"] if not imp[t]["cands"] else "후보 조립 모두 실패 — " + "; ".join(sorted({str(x.get("error"))[:80] for x in rows}))
                continue
            if mx == 0:
                zero.setdefault(game_of(t), []).append(t)
                continue
            tier = 2
        cands.append({"id": t, "tier": tier, "mx": mx, "g": gi.get(game_of(t), len(gi)), "no": turn_no(t)})
    return cands, no_impact, zero


def sup_sample_pick(cands: list, n: int = SAMPLE_PER_HANCHAN) -> list:
    """채우는 순서: tier(set → 다시 읽기로 바뀜 → 영향) → 영향 큰 순 → 이른 순(판 순서 · 차례 번호)."""
    return sorted(cands, key=lambda c: (c["tier"], -(c["mx"] or 0), c["g"], c["no"]))[:n]


def write_sources(r: Run, asked: list, hidden: list, su: dict) -> dict:
    """차례별 출처 파일 paifu_source/<판>.json(설계서 8-17 4-① — 패보 형식은 안 바꿈). 손패 주인 버림(패보의 discard)마다 SOURCE_KINDS 가운데 하나와
    근거 파일(실행 폴더 기준 경로). 차례 목록(turns_after_fix)을 패보의 손패 주인 버림에 끝에서부터 맞춘다 — 앞에 남는 버림은 줄이 선 때 앞(복원 안 함).
    먼저 걸리는 것이 이김: 사용자 확인 → 확인 안 된 추정(질문 · 영향 0 숨김) → supervisor 가 정함 → 다시 읽기와 일치 → 첫 읽기 그대로 · 읽지 않은 차례는 코드 규칙."""
    cfg = r.cfg()
    answered_ = set(r.state.get("answered") or [])
    applied_files = [f for e in r.state.get("events") or [] if "apply" in e for f in (e.get("files") or [])]
    qrow = {q["id"]: ("questions.jsonl", q) for q in asked if q.get("kind") == "turn_slot"}
    for q in hidden:
        if q.get("kind") == "turn_slot" and q.get("hidden_reason") == "hidden_zero_impact" and not q.get("sample"):
            qrow.setdefault(q["id"], ("questions_hidden.jsonl", q))
    s7_rr = {}
    for h in r.stage("S7").get("history") or []:
        for t in h.get("turns") or []:
            s7_rr.setdefault(t, []).append(h.get("round"))
    fix = jl(r.prep / cfg.fix_file.name) if (r.prep / cfg.fix_file.name).exists() else {}
    out_d = r.d / "paifu_source"
    totals, per_game = Counter(), {}
    R = lambda p: Path(p).resolve().relative_to(r.d).as_posix()   # noqa: E731
    for g in r.games():
        pf = r.paifu / f"{g}.json"
        if not pf.exists():
            per_game[g] = {"error": "패보 없음"}
            continue
        P = jl(pf)
        hero = P.get("hero")
        disc = [e for e in P["events"] if e.get("seat") == hero and e.get("type") == "discard"]
        turns_all = turns_after_fix(cfg, g)
        read_ids = game_answer_ids(r, g)
        sg = g in set(su["games"])
        n_pre = len(disc) - len(turns_all)
        rows, warn = [], []
        if n_pre < 0:
            warn.append(f"패보의 손패 주인 버림 {len(disc)} < 차례 목록 {len(turns_all)} — 앞 {-n_pre}차례는 패보에 버림이 없어 줄에 없음")
        riichi_seen = False
        tmap = {}
        for k, t in enumerate(turns_all):
            tmap[t["id"]] = riichi_seen
            if t.get("sideways"):
                riichi_seen = True
        for i, e in enumerate(disc):
            k = i - n_pre
            t = turns_all[k] if 0 <= k < len(turns_all) else None
            row = {"jun": i + 1, "tile": e.get("tile"), "tsumogiri": e.get("tsumogiri"), "riichi": e.get("riichi"), "turn": t["id"] if t else None}
            if t is None:
                row.update(source="복원 안 함", files=[R(pf)], note="줄이 선 때(t_ready) 앞 버림 — 차례 목록에 없음(패보 짐작 순)" + ("" if e.get("guess") else " · 패보에 guess 표시 없음"))
            else:
                tid = t["id"]
                if norm(t.get("tile")) != norm(e.get("tile")):
                    warn.append(f"{tid}: 차례 목록 패 {t.get('tile')} ≠ 패보 버림 {e.get('tile')}")
                if tid not in read_ids:
                    fx = fix.get(tid) or {}
                    why = "리치 뒤 — 쯔모기리(코드)" if tmap.get(tid) else (f"turn_fix kind {fx.get('kind')}" if fx.get("kind") else "읽지 않음(코드로 정함)")
                    row.update(source="코드 규칙", files=[R(r.prep / cfg.fix_file.name)], note=why)
                elif tid in answered_:
                    fs = [R(r.read / tid / "answer.json")] + ([R(r.read / tid / "answer_before_apply.json")] if (r.read / tid / "answer_before_apply.json").exists() else [])
                    row.update(source="사용자 확인", files=fs + applied_files, note="apply 로 넣은 사용자 답(user: true)")
                elif tid in qrow:
                    fn, q = qrow[tid]
                    fs = [fn] + ([q["sup_file"]] if q.get("sup_file") else [])
                    row.update(source="확인 안 된 추정", files=fs, note=f"질문에 올랐으나 답 없음 — 신호 {q.get('signal')}" + (" · 영향 0 이라 숨김" if fn != "questions.jsonl" else ""))
                else:
                    v = (su["turns"].get(tid) or {}) if sg else {}
                    how = v.get("how") or []
                    cur = slot_of(jl(active_answer(r, tid)))
                    agree = []
                    if sg:
                        for f in sorted((r.d / "sup" / g / "reread").glob(f"{tid}_r*/answer.json")):
                            try:
                                if slot_of(jl(f)) == cur:
                                    agree.append(R(f))
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                pass
                    if v.get("from") == "set":
                        fs = [R(r.d / "sup" / g / "decision.json")] + ([R(r.read / tid / "sup.json")] if (r.read / tid / "sup.json").exists() else [])
                        row.update(source="supervisor 가 정함", files=fs, note=f"set — 근거 프레임: {v.get('evidence')}" + (" · 처음 답과 다름" if v.get("changed") else " · 처음 답과 같음"))
                    elif agree:
                        row.update(source="다시 읽기와 일치", files=agree + [R(r.d / "sup" / g / "decision.json")],
                                   note=f"supervisor 다시 읽기 {', '.join(h for h in how if h.startswith('reread'))} · 마감 초안 {v.get('from')}" + (" · 처음 답과 다름" if v.get("changed") else " · 처음 답과 같음"))
                    elif tid in s7_rr:
                        fs = [R(f) for f in sorted((r.read / tid).glob("answer_r*.json"))]
                        same0 = (r.read / tid / "answer_r0.json").exists() and slot_of(jl(r.read / tid / "answer_r0.json")) == cur
                        row.update(source="다시 읽기와 일치", files=fs, note=f"S7 다시 읽기(라운드 {s7_rr[tid]}) 답을 씀 · " + ("처음 답과 같음" if same0 else "처음 답과 다름(일치 확인 없음)"))
                    else:
                        f0 = r.read / tid / ("answer_r0.json" if (r.read / tid / "answer_r0.json").exists() else "answer.json")
                        row.update(source="첫 읽기 그대로", files=[R(f0)], note=("supervisor 판: " + ", ".join(how) if how else ("supervisor 판 — 손대지 않음" if sg else "supervisor 를 안 거친 판")))
            rows.append(row)
        c = Counter(x["source"] for x in rows)
        read_rows = sum(1 for x in rows if x.get("turn") in set(read_ids))
        chk = {"sum": sum(c.values()), "hero_discards": len(disc), "sum_ok": sum(c.values()) == len(disc),
               "turns_listed": len(turns_all), "read_turns": len(read_ids), "read_rows": read_rows, "read_ok": read_rows == len(read_ids)}
        doc = {"_note": "paifu_auto.py S9 — 차례별 출처(설계서 8-17 4-①). 패보 형식은 안 바꾸고 옆 파일로. files 는 실행 폴더 기준 경로(사용자 답 파일은 apply 에 준 경로).",
               "game": g, "paifu": R(pf), "hero": hero, "supervisor": "마감" if sg else ("건너뜀(시험 옵션)" if g in set(r.stage("S7s").get("skipped") or []) else "없음"),
               "counts": {k: c.get(k, 0) for k in SOURCE_KINDS}, "check": chk, "warnings": warn, "rows": rows}
        wj(out_d / f"{g}.json", doc)
        totals.update(c)
        per_game[g] = {"counts": doc["counts"], "check": chk, "warnings": warn}
    res = {"totals": {k: totals.get(k, 0) for k in SOURCE_KINDS}, "games": per_game,
           "all_ok": all(v.get("check", {}).get("sum_ok") and v.get("check", {}).get("read_ok") for v in per_game.values())}
    wj(out_d / "_summary.json", res)
    return res


# ------------------------------------------------------------------ 보고서
def q_bundle(q) -> str:
    """질문이 나온 묶음(설계서 3-1 · 3-11 표): 차례 칸 = 묶음 4, S0 = 묶음 1, S1 ~ S5(W5 포함 · 판 결과 S4) = 묶음 2, S6a · S6(차례 수 검사) = 묶음 3."""
    if q.get("kind") == "turn_slot":
        return "묶음 4(차례 읽기 · supervisor)"
    s = str(q.get("stage") or "")
    if s == "S0":
        return "묶음 1(모으기)"
    if s == "S4":
        return "묶음 2(판 결과 S4)"
    if s in ("S1", "S2", "S3", "S5", "W5", "w5"):
        return "묶음 2(탁자 기록)"
    if s in ("S6a", "S6"):
        return "묶음 3(손 추적 준비)"
    if q.get("kind") == "check":   # 8-17 4-③ <판>_s7_check — 검사에 걸린 채 남은 판
        return "묶음 4(앞뒤 검사 · 조립 검사)"
    return f"그 밖({s or '단계 없음'})"


def game_path(r: Run, g: str) -> str:
    """판마다 간 길(설계서 3-2): 앱 버림 출처가 촬영 기록 paifu.json = 기본 · 추적 프레임 재생 = 옆길 가 · 그 밖(앱 기록 없음 · 헤드 녹화) = 옆길 나."""
    x = r.app_round(g) if (r.cfg().app_record and r.app()) else None
    used = ((x or {}).get("discard_source") or {}).get("used")
    return {"paifu_json": "기본", "track_replay": "옆길 가"}.get(used, "옆길 나") + f"({used or '앱 기록 없음'})"


def sup_report_lines(r: Run, asked, hidden, samples, sup: dict) -> list:
    """supervisor 단계가 켜진 실행의 보고서 절(설계서 8-17 4-① — 3-11 '더할 것' 가운데 지금 낼 수 있는 것)."""
    su, src = sup["su"], sup["sources"]
    sg = r.state.get("signals") or {}
    v2 = sg.get("v2_compare") or {}
    s7s = r.stage("S7s")
    L = ["## 판마다 간 길 · 판 supervisor(S7s)", "",
         "| 판 | 길 | supervisor | 손댄 차례(어떻게 · 마감 초안 · 처음과 다름) | ask | 반영한 차례 | 출처(첫 읽기 · 다시 읽기 · supervisor · 사용자 · 추정 · 코드 · 복원 안 함) |",
         "|---|---|---|---|---|---|---|"]
    for g in r.games():
        dec = (s7s.get("sup_decided") or {}).get(g)
        state = ("마감" + (f"(재생: `{rel(dec['replayed_from'])}`)" if dec and dec.get("replayed_from") else "")) if dec else \
                ("건너뜀(시험 옵션 --sup-games)" if g in (s7s.get("skipped") or []) else "읽은 차례 없음")
        touched = "; ".join(f"{t} {'+'.join(v.get('how') or [])} · {v.get('from')}{' · 다름' if v.get('changed') else ''}"
                            for t, v in su["turns"].items() if v.get("game") == g and v.get("how")) or "—"
        c = (src["games"].get(g) or {}).get("counts") or {}
        L.append(f"| {g} | {game_path(r, g)} | {state} | {touched} | {dec['asks'] if dec else '—'} | {', '.join(dec['applied']) if dec and dec['applied'] else '—'} | "
                 f"{' · '.join(str(c.get(k, 0)) for k in SOURCE_KINDS)} |")
    for t, v in su["turns"].items():
        if v.get("from") == "set":
            L.append(f"- set {t}: 근거 {v.get('evidence')}")
    bc = Counter(q_bundle(q) for q in asked)
    L += ["", f"## 질문 출처(묶음별, `questions.jsonl` {len(asked)}개)", "", "| 묶음 | 질문 |", "|---|---|"]
    L += [f"| {k} | {n} |" for k, n in sorted(bc.items())] or ["| (없음) | 0 |"]
    ts = Counter(str(q.get("signal")) for q in asked if q.get("kind") == "turn_slot")
    L += ["", f"- 차례 질문 신호: " + (" · ".join(f"{k} {n}" for k, n in ts.items()) or "없음") + " (sup:ask = supervisor 가 못 푼 차례 · unsure = supervisor 를 안 거친 판의 unsure 차례)"]
    hc = Counter(q.get("hidden_reason") for q in hidden)
    L += [f"- 숨긴 질문 {len(hidden)}개: " + (" · ".join(f"{k} {n}" for k, n in hc.items()) or "없음")]
    L += ["", "## 낱말 규칙(v2)이었다면 — 견줌용(질문은 안 만듦)", "",
          f"- 차례 질문 {v2.get('turn_questions')} + 그 밖의 질문 {v2.get('other_questions')} = 질문 {v2.get('questions')} · 표본(판마다 {SAMPLE_PER_GAME}) {v2.get('samples')} → "
          f"**볼 양 {v2.get('total')}** (지금 규칙: 질문 {len(asked)} + 표본 {len(samples)} = {len(asked) + len(samples)})",
          f"- v2 가 올린 차례 {v2.get('raised')}(영향 0 숨김 {len(v2.get('turn_hidden_zero') or [])}): {', '.join(v2.get('turn_questions_ids') or []) or '—'}"]
    L += ["", f"## 표본(반장당 {SAMPLE_PER_HANCHAN}, `samples.jsonl` {len(samples)}개 — set → 다시 읽기로 바뀜 → 영향 큰 순)", "",
          "| 순위 | id | 고른 까닭 | 바뀌는 손패 순 최대 | 결과 | supervisor | 영상 구간 |", "|---|---|---|---|---|---|---|"]
    for q in samples:
        s = q.get("impact_summary") or {}
        c = q.get("clip") or {}
        L.append(f"| {q.get('sample_rank')} ({q.get('pool_size')}) | {q['id']} | {q.get('sample_tier')} | {s.get('max_hand_turns')} | {'바뀜' if s.get('result_changed') else '같음'} | "
                 f"{'+'.join(q.get('sup') or []) or '—'} | {c.get('t0')} ~ {c.get('t1')} |")
    L += [f"- 표본 후보 {sg.get('sample_pool')}차례 · 영향 0 이라 뺀 것 {sum(len(v) for v in (sg.get('sample_zero_excluded') or {}).values())} · 영향을 못 잰 것 {len(sg.get('no_impact') or {})}"]
    L += ["", f"## 차례별 출처(`paifu_source/<판>.json`) — 합 {sum(src['totals'].values())} · 검사 {'통과' if src['all_ok'] else '**어긋남**'}", "",
          "| " + " | ".join(SOURCE_KINDS) + " |", "|" + "---|" * len(SOURCE_KINDS), "| " + " | ".join(str(src["totals"].get(k, 0)) for k in SOURCE_KINDS) + " |"]
    for g, v in src["games"].items():
        for w in v.get("warnings") or []:
            L.append(f"- {g}: {w}")
    return L


def write_report(r: Run, asked, hidden, samples=None, sup=None):
    cfg = r.cfg()
    st = r.state["stages"]
    samples = samples or []
    sg = r.state.get("signals") or {}
    human_turns = set(((r.state.get("human_picked_1123") or {}).get("turns")) or [])
    L = [f"# 자동 패보 실행 보고서 — {cfg.label} (`{cfg.id}`)", "",
         f"- 실행 폴더: `{rel(r.d)}` · 원래 설정: `{r.state['source_cfg']}` · 만든 때 {r.state['created']} · 보고서 {now()}",
         f"- 재사용(S2): `{r.state.get('reuse')}` · 손 설정(S5): `{r.state.get('hand_settings')}`",
         f"- **사용자가 볼 양: 질문 {len(asked)}개 + 표본 {len(samples)}개 = {len(asked) + len(samples)}개**(`questions.jsonl` · `samples.jsonl` — 표본은 질문 수와 따로 셈, 설계서 8-2 · 8-3절)", ""]
    if sup is not None:   # 설계서 8-17 4-①: 질문이 10 을 넘으면 맨 위에 "질문이 많음 — 어느 묶음에서 몇 개"
        L[-1:-1] = [f"- 판 supervisor 단계 켬(설계서 8-17 4-①) · 표본 반장당 {SAMPLE_PER_HANCHAN} · 낱말 규칙(v2)이었다면 볼 양 {((sg.get('v2_compare') or {}).get('total'))}"]
        if len(asked) > 10:
            bc = Counter(q_bundle(q) for q in asked)
            L += [f"**질문이 많음({len(asked)}개 > 10) — " + " · ".join(f"{k} {n}개" for k, n in sorted(bc.items())) + "**(설계서 5절 실패 신호)", ""]
    elif len(asked) > 10:
        L += [f"**질문이 많음({len(asked)}개 > 10) — 원인:** 아래 질문 목록의 stage · rule · signal 칸을 볼 것(설계서 5절 실패 신호).", ""]
    L += ["## 단계", "", "| 단계 | 상태 | 요약 |", "|---|---|---|"]
    for s in stage_list(r):
        v = st.get(s) or {}
        keep = {k: v[k] for k in v if k not in ("status", "detail", "checks", "plan", "slotgrid", "history", "games", "same_as_reuse", "final_bad", "summary", "verify", "call_turns",
                                                 "sup_decided", "packed")}
        L.append(f"| {s} {STAGE_NAME[s]} | {v.get('status')} | {json.dumps(keep, ensure_ascii=False)[:300]} |")
    if sup is not None:
        L += [""] + sup_report_lines(r, asked, hidden, samples, sup)
    L += ["", "## 판마다", "", "| 판 | 읽은 차례 | 질문 | 표본 | 영향 0 숨김 | 사용자 답 숨김 | 기록 불확실(S5) | 다시 읽기 |", "|---|---|---|---|---|---|---|---|"]
    plan = st["S6"].get("plan") or {"hand": {}, "call": []}
    for g in r.games():
        n = len(plan["hand"].get(g, [])) + sum(1 for t in plan["call"] if cfg.game_of(t) == g)
        L.append(f"| {g} | {n} | {sum(1 for q in asked if q.get('game') == g)} | {sum(1 for q in samples if q.get('game') == g)} | "
                 f"{sum(1 for q in hidden if q.get('game') == g and q.get('hidden_reason') == 'hidden_zero_impact')} | "
                 f"{sum(1 for q in hidden if q.get('game') == g and q.get('hidden_reason') == '사용자 답(apply)')} | "
                 f"{sum(1 for q in asked + hidden if q.get('game') == g and q.get('kind') == 'record')} | {r.state['reread'].get(g, 0)} |")
    if sup is None:
        bs = sg.get("by_signal") or {}
        L += ["", "## 차례 질문 신호(설계서 8-3절 v2 — 규칙은 적용 전에 고정)", "",
              f"- 읽은 차례 {sg.get('turns_total')} 중 오른 것 {sg.get('raised')}: unsure 만 {bs.get('unsure', 0)} · hedge 만 {bs.get('hedge', 0)} · 둘 다 {bs.get('both', 0)}",
              f"- 그중 질문 목록에 남은 차례 {len(sg.get('asked_turns') or [])} (나머지는 영향 0 · 사용자 답으로 숨김)",
              f"- 영향 계산: 차례 {sg.get('turns_total')} 모두, {sg.get('impact_s')}초 · 영향을 못 잰 차례 {len(sg.get('no_impact') or {})}"
              + (": " + " · ".join(f"{k} {v}" for k, v in Counter(sg['no_impact'].values()).items()) if sg.get("no_impact") else ""), ""]
    else:
        L += [""]
    L += [f"## 질문 목록({len(asked)}개, `questions.jsonl`)", "", "| id | 종류 | 신호 | 지금 답 | 후보 | 영향(바뀌는 손패 순 최대 · 결과) | 영상 구간 | 근거 규칙 |", "|---|---|---|---|---|---|---|---|"]
    for q in asked:
        s = q.get("impact_summary") or {}
        c = q.get("clip") or {}
        L.append(f"| {q['id']} | {q['kind']} | {json.dumps(q.get('signal'), ensure_ascii=False) if q.get('signal') else '—'} | {json.dumps(q.get('current'), ensure_ascii=False)} | "
                 f"{json.dumps(q.get('candidates'), ensure_ascii=False)} | {s.get('max_hand_turns')} · {'바뀜' if s.get('result_changed') else '같음'} | {c.get('t0')} ~ {c.get('t1')} | {q.get('rule') or q.get('why')} |")
    if sup is None:   # supervisor 단계가 켜진 실행은 위 "표본(반장당 5)" 절에
        L += ["", f"## 영향 큰 차례 표본({len(samples)}개, `samples.jsonl` — 신호 2, 판마다 {SAMPLE_PER_GAME})", "",
              "| 판 | id | 줄 순위(줄 크기) | 바뀌는 손패 순 최대 | 결과 | 후보 | 영상 구간 |", "|---|---|---|---|---|---|---|"]
    for q in (samples if sup is None else []):
        s = q.get("impact_summary") or {}
        c = q.get("clip") or {}
        L.append(f"| {q['game']} | {q['id']} | {q.get('sample_rank')} ({q.get('pool_size')}) | {s.get('max_hand_turns')} | {'바뀜' if s.get('result_changed') else '같음'} | "
                 f"{json.dumps(q.get('candidates'), ensure_ascii=False)} | {c.get('t0')} ~ {c.get('t1')} |")
    hq = [q for q in asked + hidden if q.get("kind") == "turn_slot" and q.get("hedge_hits")]
    if hq:
        L += ["", f"## 확신 말(hedge)에 걸린 차례({len(hq)}개) — 걸린 말 · 그 문장", ""]
        for q in sorted(hq, key=lambda q: q["id"]):
            where = "질문" if q in asked else f"숨김({q.get('hidden_reason')})"
            mark = " · 11-23 사람이 고름" if q["id"] in human_turns else " · **11-23 사람이 안 고름(헛 경보 후보)**"
            L.append(f"- {q['id']} — {where}{mark} — 신호 {json.dumps(q.get('signal'), ensure_ascii=False)}")
            for h in q["hedge_hits"][:6]:
                L.append(f"  - `{h['word']}` ({h['field']}{', 숫자 ' + str(h['nums']) if 'nums' in h else ''}): …{h['snippet']}…")
            if len(q["hedge_hits"]) > 6:
                L.append(f"  - … {len(q['hedge_hits']) - 6}곳 더")
    L += ["", f"## 보고서에만(질문 · 표본 안 함, {len(hidden)}개, `questions_hidden.jsonl`)", ""]
    for q in hidden:
        L.append(f"- {q['id']} ({q['kind']}{', 표본' if q.get('sample') else ''}) — {q.get('hidden_reason')} · 신호 {q.get('signal')} · 후보 {q.get('candidates')} · {(q.get('why') or '')[:120]}")
    hc_ = (r.state.get("human_compare") or {}).get("turns") or {}
    if hc_:
        L += ["", "## 11-23 사람이 고른 차례와 견줌", "", "| 차례 | 답 unsure | 신호 | 어디로 | 후보(출처) | 후보별 영향(손패 순 · 패보 같음) |", "|---|---|---|---|---|---|"]
        for t, v in hc_.items():
            im = "; ".join(f"{x['cand']}: {x.get('hand_turns_changed') if x.get('ok') else x.get('error')} · {x.get('paifu_same')}" for x in v["impact"]) or "—"
            where = ("질문" if v["in_asked"] else "표본" if v.get("in_sample") else
                     f"숨김({v.get('hidden_reason')}{', 표본' if v.get('hidden_sample') else ''})" if v["in_hidden"] else "안 오름")
            L.append(f"| {t} | {v['unsure']} | {json.dumps(v.get('signal'), ensure_ascii=False) if v.get('signal') else '—'} | {where} | {v['cands']} ({v['src']}) | {im} |")
    if r.cfg().app_record and r.app():
        L += [""] + app_report_lines(r)
    L += user_answer_lines(r)
    L += ["", "## 정답", "", "정답 없음 — 읽기끼리의 일치와 앞뒤 검사. 재생은 LLM 호출 0 · 하위 에이전트 0 · 토큰 0.", ""]
    wt(r.d / "report.md", "\n".join(L))


def user_answer_lines(r: Run) -> list:
    """사용자 답(apply — 설계서 8-17 4-② (라))의 보고서 절: 반영함 · 건너뜀(까닭) · 답 받음 · 반영 안 됨(손으로, B · C 묶음) — 답 글과 함께.
    apply 를 한 적이 없으면 빈 목록(옛 보고서 그대로). 강 칸 고침(user_record_fix.json)이 S5 를 다시 돌려 사라졌으면 경고."""
    ua = r.state.get("user_answers") or {}
    L = []
    rf = r.d / "user_record_fix.json"
    lost = []
    if rf.exists():
        for qid, v in jl(rf).items():
            if qid.startswith("_"):
                continue
            try:
                sl = next(x for x in jl(r.prep / "rec" / v["game"] / "dart_overlay.json")[v["side"]]["slots"] if x.get("i") == v["i"])
                if norm(sl["tile"]) != norm(v["to"]):
                    lost.append(f"{qid}({v['side']} 칸 {v['i']}: 넣은 {v['to']} · 지금 {sl['tile']})")
            except (OSError, StopIteration, KeyError):
                lost.append(f"{qid}(칸을 못 찾음)")
    if not ua and not lost:
        return L
    def txt(v):
        return json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    L += ["", f"## 사용자 답(apply — 확인 페이지 답, 설계서 8-17 4-②) {len(ua)}칸", ""]
    if lost:
        L += [f"**경고: S5 를 다시 돌려 apply 가 넣은 강 칸 고침이 사라짐 — 같은 답 파일로 apply 를 다시 부를 것: {', '.join(lost)}**", ""]
    groups = [("applied", "반영함"), ("skipped", "건너뜀(넣지 않음)"), ("unapplied", "답 받음 · 반영 안 됨(손으로)")]
    for key, label in groups:
        rows = [(k, v) for k, v in ua.items() if v.get("result") == key]
        if not rows:
            continue
        L += [f"### {label} {len(rows)}칸", "", "| id | 묶음 · 꼴 | 답 | 메모 | 까닭 · 결과 | 답 파일 · 저장 |", "|---|---|---|---|---|---|"]
        for k, v in rows:
            res = ("전과 같음" if v.get("same_as_before") else "바뀜") + (f" · {v['log']}" if v.get("log") else "") if key == "applied" else (v.get("why") or "")
            ans = txt(v.get("value")) + (f"({v['value_name']})" if v.get("value_name") else "")
            note = (v.get("note") or "").replace("|", "/").replace("\n", " ")
            L.append(f"| {k} | {v.get('bundle')} · {v.get('form')} | {ans} | {note or '—'} | {res} | `{v.get('file')}` · {v.get('saved_at') or '—'} |")
        L.append("")
    return L


def app_report_lines(r: Run) -> list:
    """앱 기록 우선 반장의 보고서 절: 판 목록(W1) · 버림 출처(W2) · 판 결과 출처(W3) · W5 영상 구간 맞추기."""
    app = r.app()
    L = ["## 앱 기록(W1 · W2 · W3 — app_rounds.json)", "",
         f"- 촬영 기록 `{app['captures']}` · {app['date']} {app['from']} ~ {app['to']} · 판 {len(app['rounds'])} · 줄이기 규칙: {app['reduce_rule']}", "",
         "| 판 | 국 | 선 · 아래 | 끝 | 결과(앱) | 끝 닻(태블릿) | 근거 폴더 | 뺀 폴더 | 버림 출처 | 앱 버림 첫 · 끝 at | 경고 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for x in app["rounds"]:
        res = x.get("result") or {}
        rs = (f"{res.get('type')} 화료 {res.get('winner')} 방총 {res.get('loser')} {res.get('win_tile')}" if x["end"] == "win" and res.get("recorded")
              else f"텐파이 {res.get('tenpai')}" if x["end"] == "draw" else "기록 없음")
        ds = x["discard_source"]
        L.append(f"| {x['id']} | {x['round_label']} | {x['dealer']} · {x['bottom_seat']} | {x['end']} | {rs} | {x['anchors'].get('end')} | "
                 f"{x['folders']['end']} · {x['folders']['track']} | {', '.join(d['folder'] for d in x['folders']['dropped']) or '—'} | "
                 f"{ds.get('used')}{(' ' + ds.get('dump', '')) if ds.get('dump') else ''} | {x['anchors'].get('discard_first')} ~ {x['anchors'].get('discard_last')} | "
                 f"{'; '.join(x.get('warnings') or []) or '—'} |")
    s4h = r.stage("S4").get("how") or {}
    if s4h:
        L += ["", f"- S4 판 결과 출처: " + " · ".join(f"{g} {v}" for g, v in s4h.items()) + "(app = 앱 label.json, 꾸러미 0 · app_draw = 텐파이 자리는 앱, 공개 손패만 꾸러미 · read = 지금 꾸러미)"]
    f = r.d / "w5" / "align.json"
    if f.exists():
        w = jl(f)
        cp = w["clock"]["pooled"]
        L += ["", "## W5 영상 구간 맞추기(w5/align.json · w5_questions.jsonl)", "",
              f"- 반장 시계 차(헤드 녹화 기록기 at − 앱 기록기 at): 중앙값 {cp.get('median_ms')}ms · p10 {cp.get('p10_ms')} · p90 {cp.get('p90_ms')} · MAD {cp.get('mad_ms')} · "
              f"최소 {cp.get('min_ms')} · 최대 {cp.get('max_ms')} · 맞은 칸 {cp.get('n')}"
              + (f" · 다른 측정 {w['clock']['ref']['offset_ms']}ms({w['clock']['ref']['source']}) 과의 차 {w['clock'].get('minus_ref_ms')}ms" if w["clock"].get("ref") else ""),
              f"- 앱 버림 칸 {w['total']['cells_app']} 중 맞은 칸 {w['total']['matched']} · 다른 칸 {w['total']['diff_cells']} · 질문 {w['total']['questions']}", "",
              "| 판 | 헤드 녹화 기록기 | 앱 칸 · 헤드 칸 · 맞음 · 다름 | 시계 차 중앙 · p10 · p90(ms) | 판 구간(헤드 시계, 맞은 칸) | S1 t_start − 헤드 첫 · t_end_play − 헤드 끝(초) | 공개 창(헤드 시계) | 울기 · 리치 같음 |",
              "|---|---|---|---|---|---|---|---|"]
        for g, v in w["rounds"].items():
            if "matched" not in v:
                L.append(f"| {g} | {v.get('skip')} | | | | | | |")
                continue
            c = v["clock"]
            L.append(f"| {g} | {v['head_used']} | {v['cells_app']} · {v['cells_head']} · {v['matched']} · {v['diff_cells']} | {c.get('median_ms')} · {c.get('p10_ms')} · {c.get('p90_ms')} | "
                     f"{v['head_interval']['first']} ~ {v['head_interval']['last']} | {(v.get('s1_delta_s') or {}).get('t_start_vs_head_first')} · {(v.get('s1_delta_s') or {}).get('t_end_play_vs_head_last')} | "
                     f"{v.get('reveal_window_head')} | {v['calls_same']} · {v['riichi_same']} |")
        for g, v in w["rounds"].items():
            for x in v.get("diffs") or []:
                L.append(f"  - {g} {x['side']} {x['tag']}: 앱 {x['app']}({x['app_at']}) · 헤드 {x['head']}({x['head_at']})")
        if w.get("check_windows"):
            L += ["", "| 판 | 견준 자료 | 창(태블릿 추적 프레임 처음 · 끝) | 판 구간(헤드) | 안에 듦 | val 창 기록기(rec_C)와 강 같음 |", "|---|---|---|---|---|---|"]
            for g, v in w["check_windows"].items():
                L.append(f"| {g} | headrec_rounds.json `{v['key']}` | {v['window']} | {v['head_interval']} | {v['inside']} | {v.get('val_rec_C_same_rivers')} {v.get('val_rec_C_per_seat_same')} |")
    f = r.d / "s3" / "advance.json"
    if f.exists():
        adv = {k: v for k, v in jl(f).items() if not k.startswith("_")}
        L += ["", f"## 판 시작 창 앞당기기(S3 — s3/advance.json, 걸음 {ADV_STEP_S}초 · 한도 {ADV_MAX_STEPS}번 · 빈 탁자 = 강 상자 ≤ {ADV_EMPTY_RIVER})", "",
              "| 판 | 결과 | t_from 전 → 뒤 | 앞 판 끝(한도) | 걸음마다 강 상자 수 | 헤드 기록기 첫 칸(뒤) | 질문 전 → 뒤 |", "|---|---|---|---|---|---|---|"]
        for g, o in adv.items():
            rw = o["rounds"][-1] if o.get("rounds") else {}
            L.append(f"| {g} | {o.get('status')}{' · 아직 창 끝' if o.get('still_edge') else ''} | {(o['rounds'][0] if o.get('rounds') else {}).get('t_from_was')} → {o.get('t_from_after')} | "
                     f"{rw.get('bound')} | {' / '.join(str(s['river']) for x in o.get('rounds') or [] for s in x['steps'])} | {o.get('head_first_after')} | "
                     f"{o.get('question_before')} → {o.get('question_after')} |")
    f = r.d / "s5" / "compare.json"
    if f.exists() and (r.stage("S5").get("status") == "done"):
        c = jl(f)
        qs5 = r.state.get("questions_s5") or []
        L += ["", "## S5 앱 기록 판 대조 · 고침(W4 — s5/compare.json · recorder_fix.json · rounds_meta.json · _prep/rec/<판>/)", "",
              f"- 손패 주인 규칙: {c.get('hero_rule')}", f"- W5 record 질문 → S5 질문으로 바꿈: {c.get('w5_record_questions_replaced')}", "",
              "| 판 | 앱 · 헤드 · 고친 사건 | 맞음 · 앱에만 · 앱 추적 전 채움 · 헤드만(뺌) · 순서 다름 | 고침(op) | 손패 주인 | 앞뒤 검사 실패 | 질문 |", "|---|---|---|---|---|---|---|"]
        for g, v in c["games"].items():
            s_ = v["stats"]
            bad = [k for k, x in v["checks"].items() if not x.get("ok") and k != "turn_order_app_only"]
            L.append(f"| {g} | {s_['app_events']} · {s_['head_events']} · {s_['final_events']} | {s_['matched']} · {s_['app_only']} · {s_['pre_filled']} · {s_['dropped_head']} · {s_['order_moved']} | "
                     f"{dict(Counter(v['ops']))} | {v['hero']}({v['hero_rule'][:12] if v.get('hero_rule') else '—'}{' · 뺀 자리 ' + str(v['hero_skipped']) if v.get('hero_skipped') else ''}) | "
                     f"{bad or '—'} | {sum(1 for q in qs5 if q.get('game') == g)} |")
        for x in c.get("not_done") or []:
            L.append(f"- 못 한 것: {x['game']} {x['what']} {x['seats']} — {x['why']}")
        hp = {g: v for g, v in c["games"].items() if v.get("head_primary")}
        L += ["", f"- 헤드 녹화 1차(설계서 3-8 의 2-5): {len(hp)}판" + ("" if hp else " — 없음")]
        for g, v in hp.items():
            L.append(f"  - {g}: " + " / ".join(v.get("head_primary_why") or []))
        for g, v in c["games"].items():
            if v.get("table_record_uncertain"):
                L.append(f"- 탁자 기록 불확실 {g}: " + " / ".join(v["table_record_uncertain"]))
            em = v.get("empty_check") or {}
            if em and not em.get("ok"):
                L.append(f"- 빈 기록 {g}: {em.get('why')}")
            gc = v.get("grid_check") or {}
            if gc.get("flag"):
                L.append(f"- 격자 {g}: {gc['flag']} · 앱 {gc.get('app')} · 펠트 {gc.get('felt')} · gridShiftOf {gc.get('shift')} · 씀 {gc.get('used')}")
    return L


def write_progress_report(r: Run, stage: str, pend: list, error: str | None = None):
    """앱 기록 우선 반장이 LLM 꾸러미 · 오류에서 멈출 때의 진행 보고서(report.md — S9 가 끝나면 write_report 가 덮어씀)."""
    cfg = r.cfg()
    st = r.state["stages"]
    L = [f"# 자동 패보 진행 보고서 — {cfg.label} (`{cfg.id}`) — {stage}" + ("" if error else " 에서 꾸러미 기다림"), "",
         f"- 실행 폴더: `{rel(r.d)}` · 원래 설정: `{r.state['source_cfg']}` · 만든 때 {r.state['created']} · 보고서 {now()}",
         f"- 기다리는 꾸러미 {len(pend)}개(`pending.json`): " + ", ".join(p["id"] for p in pend)]
    if error:
        L += ["", "**멈춘 까닭:**", "", "```", error.strip()[:3000], "```"]
    L += ["", "## 단계", "", "| 단계 | 상태 | 요약 |", "|---|---|---|"]
    for s in stage_list(r):
        v = st.get(s) or {}
        keep = {k: v[k] for k in v if k not in ("status", "detail", "checks", "plan", "slotgrid", "history", "games", "same_as_reuse", "final_bad", "summary", "verify", "call_turns", "app", "how", "advance", "error",
                                                 "sup_decided", "packed")}
        L.append(f"| {s} {STAGE_NAME[s]} | {v.get('status')} | {json.dumps(keep, ensure_ascii=False)[:300]} |")
    qn = {k: len(r.state.get(k) or []) for k in ("questions_s0", "questions_s1", "questions_w5", "questions_s4", "questions_s5", "questions_s6a", "questions_s6")}
    L += ["", f"- 지금까지 질문 후보: {qn}(S9 에서 questions.jsonl 로 모음 — W5 것은 w5_questions.jsonl 에 먼저 씀, S5 가 W5 의 record 질문을 대신함)", ""]
    L += app_report_lines(r)
    L += ht_report_lines(r)
    L += rec_report_lines(r)
    L += ["", "## 정답", "", "정답 없음. 이 보고서까지 LLM 호출 0 · 하위 에이전트 0.", ""]
    wt(r.d / "report.md", "\n".join(L))


# ------------------------------------------------------------------ next · replay · apply · status
STEP = {"S0": s0, "S1": s1, "S2": s2, "S3": s3, "S4": s4, "S5": s5, "S6a": s6a, "S6b": s6b, "S6": s6, "S7": s7, "S7s": s7s, "S8": s8, "S9": s9}


def cmd_next(a):
    r = Run(a.run)
    if r.state is None:
        raise SystemExit("init 먼저")
    redo = getattr(a, "redo", None)
    stl = stage_list(r)   # 판 supervisor 단계가 꺼진 실행은 S7s 없이(옛 흐름 그대로)
    if redo:
        # --redo S9: 그 단계와 뒤 단계만 다시(앞 단계 결과 · S6 재료는 그대로 — S9 만 고쳤을 때 488초짜리 S6 를 다시 안 돌림)
        # (S7s 를 다시 해도 마감된 꾸러미(sup/<판>/decision.json)는 그대로 둔다 — supervisor 를 새로 돌리려면 그 판 sup/<판>/ 을 치울 것)
        if redo not in stl:
            raise SystemExit(f"--redo {redo}: 이 실행에 없는 단계(판 supervisor 단계가 꺼진 실행)")
        for s in stl[stl.index(redo):]:
            r.state["stages"][s] = {"status": "todo"}
            r.state["timing"].pop(s, None)
        r.state["events"].append({"at": now(), "redo": redo})
        r.save()
    for s in stl:
        if r.stage(s)["status"] == "done":
            continue
        t0 = time.time()
        try:
            pend = STEP[s](r)
        except SystemExit as ex:   # 앱 기록 반장은 멈춘 곳 · 까닭을 진행 보고서에도(S6 재료가 공용 판별 출력이 없어 막히는 등)
            if r.cfg().app_record and r.app():
                r.stage(s)["status"] = "error"
                r.stage(s)["error"] = str(ex)[:2000]
                r.save()
                write_progress_report(r, f"{s} 에서 멈춤(오류)", [], error=str(ex))
            raise
        r.state["timing"][s] = round(r.state["timing"].get(s, 0) + time.time() - t0, 1)
        r.save()
        if pend:
            wj(r.d / "pending.json", {"stage": s, "at": now(), "packages": pend})
            r.stage(s)["status"] = "waiting"
            r.save()
            if r.cfg().app_record and r.app():
                write_progress_report(r, s, pend)
            print(f"WAIT {s} {STAGE_NAME[s]} — 읽을 꾸러미 {len(pend)}개 → {rel(r.d / 'pending.json')}")
            for p in pend[:5]:
                print(f"  {p['id']}: {p['task']} → {p['answer']}")
            if len(pend) > 5:
                print(f"  … {len(pend) - 5}개 더")
            return
        print(f"{s} {STAGE_NAME[s]} 끝 ({r.state['timing'][s]}s)")
    if (r.d / "pending.json").exists():
        wj(r.d / "pending.json", {"stage": None, "at": now(), "packages": []})
    print("done")


def cmd_replay(a):
    """pending.json 의 꾸러미에 이미 있는 답을 넣는다(LLM 0) — 3반장 결과 폴더 · 다른 실행 폴더(S4 앱 유국 공개 읽기 · S6a 준비 읽기) · 답 폴더(S6a).
    답이 없는 꾸러미는 비워 두고 보고."""
    r = Run(a.run)
    src = hcfg._p(a.src)
    src_cfg = hcfg.load(r.state["source_cfg"], check=False)
    work = hcfg.WORK
    pend = jl(r.d / "pending.json")["packages"] if (r.d / "pending.json").exists() else []
    put, miss = 0, []
    for p in pend:
        dst = Path(p["answer"])
        if dst.exists():
            continue
        f = None
        if p["stage"] == "S1":
            rp = jl(src / "rounds_p.json")
            have = {x["id"]: x for x in rp["rounds"]}
            v = {x["id"]: x for x in jl(V1114_ROUNDS)["rounds"]}
            lst = [have.get(g) or v.get(g) for g in r.games()]
            if any(x is None for x in lst):
                miss.append(p["id"])
                continue
            wj(dst, {"source": rp.get("source"), "_replay": f"{rel(src / 'rounds_p.json')}(p 판) + {rel(V1114_ROUNDS)}(그 밖의 판 — 11-23 headrec_rounds.json 의 출처)",
                     "rounds": lst})
            put += 1
            continue
        if p["stage"] == "S7s":   # 판 supervisor 꾸러미: 다른 실행의 마감된 꾸러미(<from>/sup/<판>/)를 가져와 같은 마감을 다시 적용(설계서 8-17 4-①)
            q = src / "sup" / p["game"]
            if not (q / "decision.json").exists():
                miss.append(p["id"])
                continue
            why = None
            for cmd in (["replay", "--pack", p["dir"], "--from", q], ["done", "--pack", p["dir"]]):
                pr = run([PY, "-X", "utf8", SUP_PY, *cmd], log=r.log(f"replay_s7s_{p['game']}_{cmd[0]}.log"), check=False)
                if pr.returncode != 0:
                    why = f"paifu_sup {cmd[0]} rc {pr.returncode}: " + " ".join((pr.stdout or "").split())[-300:]
                    break
            if why or not answered(p):
                miss.append(f"{p['id']}({why or '마감 파일 없음'})")
                continue
            put += 1
            continue
        if p["stage"] == "S4" and p.get("kind") == "app_draw_reveal":   # 앱 유국 공개 손패 읽기(다른 실행 폴더의 s4/<판>/<a|b|c>/reveal_read.json)
            f = src / "s4" / p["game"] / p["id"].rsplit("_", 1)[1] / "reveal_read.json"
        elif p["stage"] == "S4":
            g = p["id"].split("_", 1)[1].rsplit("_", 1)[0]
            f = src / g / "result_read.json"
        elif p["stage"] == "S6a":   # 준비 읽기 답(다른 실행 폴더의 s6a/<판>/answer.json · 답 폴더의 <판>/answer.json · <판>.json)
            g = p["game"]
            f = next((c for c in (src / "s6a" / g / "answer.json", src / g / "answer.json", src / f"{g}.json") if c.exists()), None)
        elif p["stage"] in ("S6", "S7"):
            tid = p["turn"]
            d = work / src_cfg.read_root / tid
            f = d / "answer.json"
            if a.before_user:
                b = sorted(d.glob("answer_opus_before_user_*.json"))
                if b:
                    f = b[0]
        if f is None or not f.exists():
            miss.append(p["id"])
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, dst)
        put += 1
    r.state["events"].append({"at": now(), "replay": put, "missing": miss, "before_user": bool(a.before_user)})
    r.save()
    print(f"replay: 넣음 {put} · 답 없음 {len(miss)}{' ' + str(miss) if miss else ''}")


# ------------------------------------------------------------------ 확인 페이지 묶음 · 답 반영(설계서 8-17 4-②, 11-25 밤)
# 질문 id 꼴 표 하나 — paifu_confirm.py(페이지 · 영상)와 apply(반영)가 같이 쓴다. 위에서부터 먼저 맞는 줄이 이긴다. 맞는 줄이 없으면 C(알림).
# 칸: (꼴 이름, id 정규식(None = kind turn_slot), 묶음, 페이지 입력, 영상 구간 출처, apply)
#   묶음 A = 가린 확인(지금 값 · 후보 · why 를 안 보냄) · B = 후보 고르기(지금 값과 후보를 섞어 정해진 순서로 — 어느 것이 지금 값인지 안 보임)
#   · C = 알림(why 를 그대로 보임). "A?" = 지금 값과 후보가 모두 패 이름이면 A(패 종류), 아니면 B. B 인데 고를 것(지금 값 + 후보)이 둘 미만이면 C.
_P3 = r"[0-9a-z]{3}"
_SD = r"(?P<side>bottom|right|top|left)"
Q_FORMS = [
    ("turn_slot", None, "A", "차례 칸 정답 입력(프레임 묶음)", "read/<차례>/frames.txt 창 1초 앞부터 초당 10장", "반영 — 차례 답(k = k_id)"),
    ("ura", rf"^{_P3}_ura$", "A", "패 34종 + 안 깠다 + 모르겠다", "S9: t_reveal ~ +15초(확대 칸 없음)", "반영(unknown 건너뜀 · none = 뒷도라 없음)"),
    ("haitei", rf"^{_P3}_haitei$", "A", "예 · 아니오 · 모르겠다", "S9: t_end_play − 25초 ~ t_reveal + 5초(확대 칸 없음)", "반영(unknown 건너뜀)"),
    ("rec_cell", rf"^{_P3}_rec_{_SD}_(?P<pos>\d+)$", "A?", "패 34종 + 모르겠다(A) / 후보 고르기(B)", "S9: 기록기가 그 칸을 처음 본 때 −5 ~ +10초(칸 상자가 있으면 확대)", "A 면 반영 — _prep/rec/<판>/ 의 그 칸 패 종류"),
    ("app5_tile", rf"^{_P3}_app5_tile_{_SD}_(?P<pos>\w+)$", "A?", "패 34종 + 모르겠다(A) / 후보 고르기(B)", "S5: 그 고침의 헤드 · 앱 시각 −5 ~ +10초(칸 상자가 있으면 확대)", "A 면 반영 — 앱 기록 길 _prep/rec/<판>/ 의 그 칸 패 종류"),
    ("app_warn", r"^app_warn_\d+$", "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("app_games", r"^app_games$", "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("game_app_warn", rf"^{_P3}_app_warn_\d+$", "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("s1_rounds", r"^s1_rounds$", "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("s1_order", r"^s1_order$", "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("s1_track_window", r"^s1_\w+_track_window$", "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("s1_gap", r"^s1_\w+_gap$", "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("s1_outside", r"^s1_\w+_outside$", "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("s1_reveal", r"^s1_\w+_reveal$", "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("app_bottom", r"^app_bottom$", "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("app_start", rf"^{_P3}_app_start$", "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("app_clock", rf"^{_P3}_app_clock$", "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("dealer", r"^\w+_dealer$", "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("s5_app_bottom", r"^s5_app_bottom$", "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("app5_round", rf"^{_P3}_app5_round$", "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("app5_head_primary", rf"^{_P3}_app5_head_primary$", "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("app5_uncertain", rf"^{_P3}_app5_uncertain$", "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("app5_chk", rf"^{_P3}_app5_chk_\w+$", "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("s6a", rf"^{_P3}_s6a_\w+$", "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("s6_turns", rf"^{_P3}_s6_turns$", "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("reveal", rf"^{_P3}_reveal$", "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("result", rf"^{_P3}_result$", "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("s7_check", rf"^{_P3}_s7_check$", "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "없음", "안 함(보고서)"),   # 8-17 4-③
    ("ev", rf"^{_P3}_ev_\w+_{_SD}$", "B", "후보 고르기(섞음) + 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("w5_cell", rf"^{_P3}_app_{_SD}_\d+$", "B", "후보 고르기(섞음) + 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("w5_calls", rf"^{_P3}_app_calls$", "B", "후보 고르기(섞음) + 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("w5_riichi", rf"^{_P3}_app_riichi$", "B", "후보 고르기(섞음) + 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("app5_hero_hand", rf"^{_P3}_app5_hero_hand$", "B", "후보 고르기(섞음) + 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("app5_hero", rf"^{_P3}_app5_hero$", "B", "후보 고르기(섞음) + 모르겠다 + 메모", "없음", "안 함(보고서)"),
    ("app5_pre", rf"^{_P3}_app5_pre_{_SD}_\w+$", "B", "후보 고르기(섞음) + 모르겠다 + 메모", "S5: 헤드 시각 −5 ~ +10초", "안 함(보고서)"),
    ("app5_call_headonly", rf"^{_P3}_app5_call_headonly_{_SD}_\w+$", "B", "후보 고르기(섞음) + 모르겠다 + 메모", "S5: 받은 버림 헤드 시각 −5 ~ +10초", "안 함(보고서)"),
    ("app5_call_apponly", rf"^{_P3}_app5_call_apponly_{_SD}_\w+$", "B", "후보 고르기(섞음) + 모르겠다 + 메모", "S5: 받은 버림 헤드 시각 −5 ~ +10초", "안 함(보고서)"),
    ("app5_call", rf"^{_P3}_app5_call_{_SD}_\w+$", "B", "후보 고르기(섞음) + 모르겠다 + 메모", "S5: 받은 버림 헤드 시각 −5 ~ +10초", "안 함(보고서)"),
    ("app5_headonly", rf"^{_P3}_app5_headonly_{_SD}_\w+$", "B", "후보 고르기(섞음) + 모르겠다 + 메모", "S5: 헤드 시각 −5 ~ +10초", "안 함(보고서)"),
    ("app5_apponly", rf"^{_P3}_app5_apponly_{_SD}_\w+$", "B", "후보 고르기(섞음) + 모르겠다 + 메모", "S5: 앱 시각 + 시계 차 −5 ~ +10초", "안 함(보고서)"),
    ("app5_riichi", rf"^{_P3}_app5_riichi_{_SD}_\w+$", "B", "후보 고르기(섞음) + 모르겠다 + 메모", "S5: 시각이 있으면 −5 ~ +10초", "안 함(보고서)"),
    ("hero", r"^\w+_hero$", "B", "후보 고르기(섞음) + 모르겠다 + 메모", "없음", "안 함(보고서)"),
]
Q_FORM_UNKNOWN = ("unknown_form", None, "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "없음(clip 칸이 있으면 그 구간)", "안 함(보고서)")
TILES34 = [f"{i}{s}" for s in "mps" for i in range(1, 10)] + [f"{i}z" for i in range(1, 8)]
_TILE_RE = re.compile(r"^(?:[0-9][mps]|[1-7]z)$")


def is_tile(v) -> bool:
    return isinstance(v, str) and bool(_TILE_RE.match(v))


def b_options(q: dict) -> list:
    """B 묶음의 고를 것: 지금 값 + 후보를 한데 섞어 정해진 순서(글로 바꾼 JSON 의 사전 순)로 — 어느 것이 지금 값인지 안 보이게. 같은 것은 하나로."""
    vals = ([q["current"]] if q.get("current") is not None else []) + [c for c in (q.get("candidates") or []) if c is not None]
    seen = {}
    for v in vals:
        seen.setdefault(json.dumps(v, ensure_ascii=False, sort_keys=True), v)
    return [seen[k] for k in sorted(seen)]


def q_form(q: dict) -> dict:
    """질문 줄 → {"form", "bundle"(A · B · C), "input", "clip_src", "apply", "m"(정규식 맞음 — side · pos), "note"}. 모르는 꼴은 C(죽지 않음)."""
    qid = str(q.get("id") or "")
    row, m = None, None
    if q.get("kind") == "turn_slot":
        row = Q_FORMS[0]
    else:
        for f in Q_FORMS[1:]:
            m = re.match(f[1], qid)
            if m:
                row = f
                break
    row = row or Q_FORM_UNKNOWN
    name, _, bundle, inp, clip_src, ap = row
    note = None
    if bundle == "A?":
        cands = q.get("candidates") or []
        if is_tile(q.get("current")) and cands and all(is_tile(c) for c in cands):
            bundle, inp = "A", "패 34종 + 모르겠다"
        else:
            bundle, inp, note = "B", "후보 고르기(섞음) + 모르겠다 + 메모", "지금 값 · 후보가 패 이름이 아님 → B"
    if bundle == "B" and len(b_options(q)) < 2:
        bundle, inp, note = "C", "확인함 · 문제 있음 · 모르겠다 + 메모", "고를 것(지금 값 + 후보)이 둘 미만 → C"
    return {"form": name, "bundle": bundle, "input": inp, "clip_src": clip_src, "apply": ap, "m": m.groupdict() if m else {}, "note": note}


def q_rows(r: "Run") -> dict:
    """질문 id → 질문 줄(questions.jsonl · samples.jsonl · questions_hidden.jsonl · state 의 questions_* — 앞의 것이 이김). apply 가 꼴 · 지금 값을 본다."""
    out = {}
    for f in ("questions.jsonl", "samples.jsonl", "questions_hidden.jsonl"):
        for q in jlines(r.d / f):
            out.setdefault(q["id"], q)
    for k, v in r.state.items():
        if k.startswith("questions_") and isinstance(v, list):
            for q in v:
                if isinstance(q, dict) and q.get("id"):
                    out.setdefault(q["id"], q)
    return out


TURN_SKIP = {"unseen": "안 보임 · 모름(페이지 답) — 넣지 않음",
             "bad": "구간이 이상함(페이지 답) — 넣지 않음",
             "call": "울기 뒤 버림 — 페이지 답에 조립이 쓰는 칸(gone · end_order)이 없음(넣는 길은 아직 없음)"}


def _first(u: dict, keys):
    return next((u[k] for k in keys if u.get(k) is not None), None)


def turn_answer_problem(u: dict):
    """차례 답을 넣을 수 없으면 까닭(글), 넣을 수 있으면 None. 덜 끝난 답 = ops_error · ops_pending 이 있거나 손에서 냄인데 order · 버린 칸이 없음."""
    kd = u.get("kind")
    if kd in TURN_SKIP:
        return TURN_SKIP[kd]
    if kd not in ("hand", "tsumogiri"):
        return f"종류가 없거나 모르는 종류({kd}) — 넣지 않음"
    if u.get("ops_error"):
        return f"덜 끝난 답 — 칸 동작 오류: {u['ops_error']}"
    if u.get("ops_pending"):
        return f"덜 끝난 답 — 아직: {u['ops_pending']}"
    if kd == "hand" and not u.get("order"):
        return "덜 끝난 답 — 끝 줄(order)이 없음"
    if kd == "hand" and _first(u, ("k_id", "k_orig", "k")) is None:
        return "덜 끝난 답 — 버린 칸이 없음"
    return None


def rec_cell_locate(r: "Run", g: str, form: str, side: str, pos: str):
    """고친 기록(_prep/rec/<판>/)에서 그 칸 → (기록기 칸 i, 까닭). 3반장 길(rec_cell) = 칸 i 그대로(질문 id 의 숫자 = river_rules 의 slot i).
    앱 기록 길(app5_tile) = 질문 id 의 끝 = 헤드 녹화 기록기에서 그 자리 몇 번째 버림(app_merge 의 nth) → 헤드 dart(s5/compare.json 의 head 폴더) 그 칸의 i
    (s5_app 이 헤드 칸을 i 째 복사해 _prep/rec 의 dart 를 만듦)."""
    if form == "rec_cell":
        return int(pos), None
    try:
        nth = int(pos)
        head = jl(r.d / "s5" / "compare.json")["games"][g]["head"]
        hd = jl(hcfg._p(head) / "dart_overlay.json")
        return hd[side]["slots"][nth - 1]["i"], None
    except (OSError, KeyError, IndexError, ValueError, TypeError) as e:
        return None, f"앱 기록 길 칸을 못 찾음({type(e).__name__}: {e})"


REC_FIX_FILES = ("dart_overlay.json", "dart_overlay_v2.json", "paifu_rec.json", "recfix_check.json")


def rec_cell_fix(r: "Run", qid: str, g: str, form: str, side: str, pos: str, cur, new: str) -> tuple:
    """강 한 칸의 패 종류를 고친 기록(_prep/rec/<판>/ — 조립 S8 이 읽는 곳)에 넣는다 → ("applied" | "same" | "skip", 글).
    고치는 곳: dart_overlay.json · dart_overlay_v2.json(칸 tile · 울려 나간 칸이면 meld.tiles) · paifu_rec.json(그 자리 같은 순번 버림 사건 tile ·
    바로 뒤가 그 패를 받은 울기 사건이면 그 tiles 한 장) · recfix_check.json(ops 에 한 줄 — 패보 note 의 고침 목록). 처음 고치기 전 네 파일을
    _prep/rec/<판>/_before_apply/ 에 남김(unapply 가 되돌림). S5 는 다시 돌리지 않는다."""
    rd = r.prep / "rec" / g
    if not (rd / "paifu_rec.json").exists() or not (rd / "dart_overlay.json").exists():
        return "skip", f"고친 기록 {rel(rd)} 이 없음"
    i, why = rec_cell_locate(r, g, form, side, pos)
    if i is None:
        return "skip", why
    d = jl(rd / "dart_overlay.json")
    sl = d.get(side, {}).get("slots") or []
    k = next((n for n, x in enumerate(sl) if x.get("i") == i and not (form == "app5_tile" and x.get("added_by"))), None)
    if k is None:
        return "skip", f"{side} 칸 i={i} 이 고친 기록에 없음"
    pr = jl(rd / "paifu_rec.json")
    ev = pr["events"]
    seat = (pr["hero"] + SIDES.index(side)) % 4   # paifu_rec 의 hero = 아래 자리(replay_recorder bottomSeat · s5_app 도 같음)
    idx = [n for n, e in enumerate(ev) if e["type"] == "discard" and e["seat"] == seat]
    if len(idx) != len(sl):
        return "skip", f"{side} 칸 {len(sl)} ≠ 사건 버림 {len(idx)} — 칸과 사건을 못 맞춤"
    n = idx[k]
    old = sl[k]["tile"]
    if norm(old) != norm(ev[n]["tile"]):
        return "skip", f"칸 {old} ≠ 사건 {ev[n]['tile']} — 칸과 사건을 못 맞춤"
    if norm(old) == norm(new):
        return "same", f"{side} 칸 i={i} 이 이미 {old}"
    if cur is not None and norm(old) != norm(cur):
        return "skip", f"{side} 칸 i={i} 의 지금 값 {old} 이 질문의 지금 값 {cur} 과 다름 — 넣지 않음"
    bdir = rd / "_before_apply"
    if not bdir.exists():
        bdir.mkdir(parents=True)
        for name in REC_FIX_FILES:
            if (rd / name).exists():
                shutil.copyfile(rd / name, bdir / name)
    touched = []
    for name in ("dart_overlay.json", "dart_overlay_v2.json"):
        f = rd / name
        if not f.exists():
            continue
        dd = d if name == "dart_overlay.json" else jl(f)
        s2 = next(x for x in dd[side]["slots"] if x.get("i") == i)
        if norm(s2["tile"]) != norm(old):
            return "skip", f"{name} 의 칸 {s2['tile']} ≠ {old}"
        s2["tile"] = new
        if isinstance(s2.get("meld"), dict) and old in (s2["meld"].get("tiles") or []):
            t = list(s2["meld"]["tiles"])
            t[t.index(old)] = new
            s2["meld"]["tiles"] = t
        wj(f, dd)
        touched.append(name)
    ev[n] = {**ev[n], "tile": new}
    call = None
    if n + 1 < len(ev) and ev[n + 1]["type"] == "call" and ev[n + 1].get("from") == seat and old in (ev[n + 1].get("tiles") or []):
        t = list(ev[n + 1]["tiles"])
        t[t.index(old)] = new
        ev[n + 1] = {**ev[n + 1], "tiles": t}
        call = t
    wj(rd / "paifu_rec.json", pr)
    touched.append("paifu_rec.json")
    log = f"retile {side} {i} {old}→{new}(사용자 확인 {qid} — paifu_auto apply)"
    if (rd / "recfix_check.json").exists():
        rc = jl(rd / "recfix_check.json")
        rc["ops"] = list(rc.get("ops") or []) + [log]
        wj(rd / "recfix_check.json", rc)
        touched.append("recfix_check.json")
    rf = r.d / "user_record_fix.json"
    uf = jl(rf) if rf.exists() else {}
    uf.setdefault("_note", "paifu_auto apply 가 _prep/rec/<판>/ 에 넣은 강 칸 패 종류(사용자 답). S5 를 다시 돌리면 _prep/rec 를 새로 써서 사라진다 — "
                           "report.md 가 경고하고, 다시 넣으려면 같은 답 파일로 apply 를 다시 부른다.")
    uf[qid] = {"game": g, "side": side, "i": i, "seat": seat, "from": old, "to": new, "event": n, "call_tiles": call, "files": touched, "at": now()}
    wj(rf, uf)
    return "applied", log + (f" · 받은 울기 {call}" if call else "")


def turn_size(cur: dict) -> int:
    """차례가 끝난 뒤의 줄 장수 = 읽기 답 끝 줄 길이(손에서 냄은 D 를 한 장으로 셈 · 쯔모기리는 D 없음). 읽기 답에 끝 줄이 없으면 13."""
    return len(cur.get("end_order") or []) or 13


def tsumogiri_problem(u: dict, cur: dict):
    """쯔모기리 페이지 답을 넣을 수 없으면 까닭(글), 넣을 수 있으면 None(8-17 4-③ 덧붙임).
    끝 줄(order — 칸 판으로 적은 답)이 있으면: 길이가 줄 장수(turn_size)와 같고 1 … n 을 한 번씩. 그 답의 "줄 장수가 다르면" 칸(n)은 칸 판 크기에
    이미 들어가 끝 줄 길이로 드러나므로 따로 안 봄. 끝 줄이 없으면(쯔모기리만 고름): n 칸이 적혀 있고 줄 장수와 다를 때만 건너뜀 — n 으로 끝 줄을 만들지는 않음."""
    n = turn_size(cur)
    o = u.get("order")
    if o:
        o = [str(x) for x in o]
        if len(o) != n:
            return f"쯔모기리 끝 줄 {len(o)}장 ≠ 읽기 답 줄 장수 {n}장 — 넣지 않음"
        if sorted(o, key=lambda x: (len(x), x)) != [str(i) for i in range(1, n + 1)]:
            return f"쯔모기리 끝 줄이 1 … {n} 을 한 번씩 담지 않음({' '.join(o)}) — 넣지 않음"
        return None
    if u.get("n") not in (None, ""):
        try:
            un = int(u["n"])
        except (TypeError, ValueError):
            return f"줄 장수 칸 n {u['n']!r} 을 못 읽음 — 넣지 않음"
        if un != n:
            return f"페이지 '줄 장수가 다르면' {un}장 ≠ 읽기 답 줄 장수 {n}장(끝 줄 없는 쯔모기리) — 넣지 않음"
    return None


def user_turn_answer(u: dict, cur: dict) -> dict:
    """정답 입력 페이지 답(answers_user.json 한 칸) → 읽기 답 꼴(kind · k · j · end_order).
    k = k_id(원래 줄에서 몇 번째 — 읽기 답의 k 와 같은 뜻). 페이지의 k 는 k_pos(버리는 순간의 자리)라 쓰지 않는다(8-17 4-② (라)) — k_id 가 없는 옛 답은 k_orig · k."""
    out = {"id": cur.get("id"), "kind": u["kind"], "unsure": False, "user": True, "user_note": u.get("note"), "user_saved_at": u.get("saved_at")}
    if u["kind"] == "hand":
        out.update(k=_first(u, ("k_id", "k_orig", "k")), j=u.get("j_closed"), end_order=[str(x) for x in u["order"]])
    elif u["kind"] == "tsumogiri":
        # 11-25 밤(8-17 4-③ 덧붙임): 줄 장수 = 차례가 끝난 뒤의 줄 장수 = 읽기 답 끝 줄 길이(D 도 한 장). 옛 코드는 D 를 빼고 세어
        # 읽기 답이 "손에서 냄" 인 차례에 1 … 12 가 됐다. 페이지 끝 줄(order)이 있으면 그것(길이 · 순열 검사는 tsumogiri_problem — apply 가 먼저 봄)
        n = turn_size(cur)
        eo = [str(x) for x in u["order"]] if u.get("order") else [str(i) for i in range(1, n + 1)]
        out.update(k=None, j=None, end_order=eo)
    else:
        out.update({k: u.get(k) for k in ("k", "gone", "end_order")})
    return out


def cmd_apply(a):
    """사용자 답 파일(확인 페이지 answers_user.json — 차례 답 · 항목 답이 한 파일에 같이 있어도 되고, --answers 를 여러 번 줘도 됨) → 반영 → S7 · S8 · S9.
    가르기(설계서 8-17 4-② (라)): 값에 kind 가 있으면 차례 답(키 = 차례 id), value 가 있으면 항목 답 — 질문 id 꼴 표(Q_FORMS)로 묶음을 가름.
      반영: 차례 답(hand · tsumogiri — k = k_id) · 뒷도라(패 · none = 없음) · 해저(yes · no) · 강 한 칸 패 종류(A 묶음 rec_cell · app5_tile).
      건너뜀(까닭과 함께 — 죽지 않음): 덜 끝난 차례 답 · unseen · bad · call · unknown("모르겠다", 어느 꼴이든) · 모르는 값 · 칸을 못 찾음.
      B · C 묶음 답: 반영하지 않고 보고서에 "답 받음 · 반영 안 됨(손으로)" 로 답 글과 함께.
    반영한 칸만 state.answered(다음 S9 에서 질문 · 표본에서 숨김). supervisor(S7s)는 다시 띄우지 않는다."""
    r = Run(a.run)
    cfg = r.cfg()
    applied, notq = [], []
    qids = {q["id"] for q in jlines(r.d / "questions.jsonl")}
    sids = {q["id"] for q in jlines(r.d / "samples.jsonl")}
    rows = q_rows(r)
    ua = r.state.setdefault("user_answers", {})   # 질문 id → 이번까지의 마지막 처리(보고서 "사용자 답" 절)
    for af in a.answers:
        try:
            ans = jl(af)
        except (OSError, json.JSONDecodeError) as e:
            notq.append(f"{rel(af)}: 답 파일을 못 읽음({type(e).__name__})")
            continue
        for k, u in ans.items():
            if k.startswith("_"):
                continue
            base = {"id": k, "file": rel(af), "note": (u or {}).get("note") if isinstance(u, dict) else None,
                    "saved_at": (u or {}).get("saved_at") if isinstance(u, dict) else None}

            def skip(why, **kw):
                notq.append(f"{k}: {why}")
                ua[k] = {**base, "result": "skipped", "why": why, **kw}
            if not isinstance(u, dict):
                skip("답이 사전 꼴이 아님")
                continue
            if "kind" in u:   # 차례 답(칸 정답 입력 화면)
                why = turn_answer_problem(u)
                if why:
                    skip(why, bundle="A", form="turn_slot", value=u.get("kind"))
                    continue
                f = active_answer(r, k)
                if not f.exists():
                    skip("읽기 답 없음", bundle="A", form="turn_slot", value=u.get("kind"))
                    continue
                cur = jl(f)
                why = tsumogiri_problem(u, cur) if u.get("kind") == "tsumogiri" else None   # 8-17 4-③ 덧붙임: 쯔모기리 줄 장수
                if why:
                    skip(why, bundle="A", form="turn_slot", value=u.get("kind"))
                    continue
                keep = r.read / k / "answer_before_apply.json"
                if not keep.exists():
                    shutil.copyfile(f, keep)
                new = user_turn_answer(u, cur)
                same = [str(x) for x in (cur.get("end_order") or [])] == new["end_order"] and cur.get("kind") == new["kind"]
                wj(f, {**cur, **new})
                applied.append({"id": k, "kind": "turn", "same_as_before": same, "was_question": k in qids, "was_sample": k in sids})
                ua[k] = {**base, "result": "applied", "bundle": "A", "form": "turn_slot", "value": {"kind": new["kind"], "k": new.get("k"), "j": new.get("j")},
                         "same_as_before": same}
                continue
            if "value" not in u:
                skip("kind 도 value 도 없는 답")
                continue
            v = u["value"]
            row = rows.get(k) or {"id": k}
            fm = q_form(row)
            if k not in rows and u.get("bundle") in ("B", "C"):   # 이 실행의 질문 목록에 없는 id — 페이지가 저장한 묶음을 씀(꼴 표만으로는 후보 수를 모름)
                fm = {**fm, "bundle": u["bundle"]}
            if fm["bundle"] in ("B", "C"):
                ua[k] = {**base, "result": "unapplied", "bundle": fm["bundle"], "form": fm["form"], "value": v, "value_name": u.get("value_name"),
                         "why": "답 받음 · 반영 안 됨(손으로)" + ("" if k in rows else " — 이 실행의 질문 목록에 없는 id")}
                continue
            if v == "unknown":
                skip("모르겠다(unknown) — 넣지 않음(그 칸은 확인 안 된 추정으로 남음)", bundle="A", form=fm["form"], value=v)
                continue
            pre = k.split("_", 1)[0]
            g = cfg.game_of(pre)
            if g is None:
                skip(f"판을 못 찾음(접두사 {pre})", bundle="A", form=fm["form"], value=v)
                continue
            if fm["form"] in ("ura", "haitei"):
                if fm["form"] == "ura" and v != "none" and not is_tile(v):
                    skip(f"모르는 값 {v!r}", bundle="A", form=fm["form"], value=v)
                    continue
                if fm["form"] == "haitei" and v not in ("yes", "no"):
                    skip(f"모르는 값 {v!r}", bundle="A", form=fm["form"], value=v)
                    continue
                f = r.d / g / "result_read.json"
                rr = jl(f)
                keep = r.d / g / "result_read_before_apply.json"
                if not keep.exists():
                    shutil.copyfile(f, keep)
                if fm["form"] == "ura":
                    if v == "none":   # 뒷도라를 안 깠다 → 표시패 없음(조립은 빈 목록을 받음 — han3_paifu: list(rr.get("ura_indicators") or []))
                        same = not rr.get("ura_indicators")
                        if not same:
                            rr["ura_indicators"] = []
                    else:
                        same = (rr.get("ura_indicators") or [None])[0] == v
                        if not same:
                            rr["ura_indicators"] = [v] + list((rr.get("ura_indicators") or [])[1:])
                else:
                    chk = jl(r.paifu / "_check.json")[g]
                    cur = chk.get("wall_left_end") == 0
                    want = v == "yes"
                    same = cur == want
                    if not same:
                        rr["last_tile"] = want
                if not same:
                    wj(f, rr)
                applied.append({"id": k, "kind": fm["form"], "same_as_before": same, "was_question": k in qids, "was_sample": k in sids})
                ua[k] = {**base, "result": "applied", "bundle": "A", "form": fm["form"], "value": v, "same_as_before": same}
                continue
            if fm["form"] in ("rec_cell", "app5_tile"):
                if not is_tile(v):
                    skip(f"모르는 값 {v!r}", bundle="A", form=fm["form"], value=v)
                    continue
                st, why = rec_cell_fix(r, k, g, fm["form"], fm["m"]["side"], fm["m"]["pos"], row.get("current"), v)
                if st == "skip":
                    skip(why, bundle="A", form=fm["form"], value=v)
                    continue
                applied.append({"id": k, "kind": fm["form"], "same_as_before": st == "same", "was_question": k in qids, "was_sample": k in sids, "log": why})
                ua[k] = {**base, "result": "applied", "bundle": "A", "form": fm["form"], "value": v, "same_as_before": st == "same", "log": why}
                continue
            skip(f"A 묶음인데 반영 길이 없는 꼴 {fm['form']}", bundle="A", form=fm["form"], value=v)
    r.state["answered"] = sorted(set(r.state.get("answered") or []) | {x["id"] for x in applied})
    for s in ("S7", "S8", "S9"):
        r.state["stages"][s] = {"status": "todo"}
        r.state["timing"].pop(s, None)   # 걸린 시간은 이번 바퀴 것만(옛 코드는 누적)
    r.state["reread"] = {}
    # 설계서 8-17 4-③: 이 뒤의 S7 은 다시 읽기 꾸러미를 내지 않는다(사용자 답은 최종 — 걸린 판은 S9 의 <판>_s7_check 로)
    r.state["user_final"] = {"at": now(), "note": "apply 뒤 — S7 다시 읽기 안 함(설계서 8-17 4-③)"}
    unap = [x for x, v in ua.items() if v.get("result") == "unapplied"]
    r.state["events"].append({"at": now(), "apply": applied, "skipped": notq, "unapplied": unap, "files": [rel(x) for x in a.answers]})
    r.save()
    print(f"apply: {len(applied)}칸 (전과 같음 {sum(x['same_as_before'] for x in applied)}) · 건너뜀 {notq} · 답 받음 · 반영 안 됨(B · C) {len(unap)}")
    cmd_next(argparse.Namespace(run=a.run))


def cmd_unapply(a):
    """apply 를 되돌린다(시험용): read/<차례>/answer_before_apply.json · <판>/result_read_before_apply.json 을 지금 답 자리에 다시 놓고
    '사용자 답' 목록을 비운 뒤 S7 → S8 → S9 를 다시 돈다(S6 재료는 그대로). _before_apply 사본은 남겨 둬서 다음 apply 도 같은 '전' 을 본다."""
    r = Run(a.run)
    back = []
    for f in sorted(r.read.glob("*/answer_before_apply.json")):
        shutil.copyfile(f, f.parent / "answer.json")
        back.append(f.parent.name)
    for g in r.games():
        f = r.d / g / "result_read_before_apply.json"
        if f.exists():
            shutil.copyfile(f, r.d / g / "result_read.json")
            back.append(g)
        bdir = r.prep / "rec" / g / "_before_apply"   # 강 칸 패 종류(8-17 4-②) — 사본은 남김(다음 apply 도 같은 '전' 을 봄)
        if bdir.is_dir():
            for f in sorted(bdir.glob("*.json")):
                shutil.copyfile(f, bdir.parent / f.name)
            back.append(f"rec/{g}")
    rf = r.d / "user_record_fix.json"
    if rf.exists():
        old = {k: v for k, v in jl(rf).items() if not k.startswith("_")}
        wj(rf, {"_note": f"unapply({now()})로 되돌림 — 넣은 칸 없음", "_undone": old})
    r.state["events"].append({"at": now(), "unapply": back, "answered_was": r.state.get("answered"),
                              "user_answers_was": sorted((r.state.get("user_answers") or {}).keys())})
    r.state["answered"] = []
    r.state["user_answers"] = {}
    r.state.pop("user_final", None)   # 8-17 4-③ 표시도 지움 — apply 전 흐름(S7 다시 읽기 있음)으로
    for s in ("S7", "S8", "S9"):
        r.state["stages"][s] = {"status": "todo"}
        r.state["timing"].pop(s, None)
    r.state["reread"] = {}
    r.save()
    print(f"unapply: {len(back)}개 되돌림 {back}")
    cmd_next(argparse.Namespace(run=a.run))


def cmd_status(a):
    r = Run(a.run)
    on = sup_on(r)
    for s in STAGES:
        if s == "S7s" and not on:
            print(f"{s} {STAGE_NAME[s]:12s} {'끔':8s}")
            continue
        v = r.stage(s)
        print(f"{s} {STAGE_NAME[s]:12s} {v['status']:8s} {r.state['timing'].get(s, '')}")
    pf = r.d / "pending.json"
    if pf.exists():
        p = jl(pf)
        print("꾸러미", len(p["packages"]), "· 단계", p["stage"])
    for name, label in (("questions.jsonl", "질문"), ("samples.jsonl", "표본")):
        if (r.d / name).exists():
            print(label, sum(1 for x in (r.d / name).read_text(encoding="utf-8").splitlines() if x.strip()))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("init")
    p.add_argument("--hanchan", required=True)
    p.add_argument("--run")
    p.add_argument("--reuse")
    p.add_argument("--hand-settings")
    p.add_argument("--verify-dump")
    p.add_argument("--s6-games", help="시험용: S6 칸 틀 검출 · 차례 꾸러미를 이 판들만(쉼표) — 차례 목록 · 차례 수 검사는 모든 판")
    p.add_argument("--s6a-rules", action="store_true", help="견줌용: S6a 를 옛 화소 규칙(handtrack_auto.py conf)으로")
    p.add_argument("--slotgrid-seed", help="시험용: S6 칸 틀 검출 캐시(det_<판>.json)를 이 실행 폴더의 handtrack/_work/slotgrid_1117 에서 복사 — "
                                            "그 판 판별 설정의 side · band · sheet_band 가 같을 때만(새로 계산할 프레임만 detect)")
    p.add_argument("--no-sup", action="store_true", help="판 supervisor 단계(S7s)를 끔 — 단계 · 질문 규칙 v2 · 표본 판마다 2(설계서 8-17 4-① 전과 같음)")
    p.add_argument("--sup-games", help="시험용: 판 supervisor 를 이 판들만(쉼표) 거치게 — 나머지 판은 S7s 에서 건너뜀(그 판 unsure 차례는 질문으로)")
    for name in ("status", "unapply"):
        sp.add_parser(name).add_argument("--run", required=True)
    p = sp.add_parser("next")
    p.add_argument("--run", required=True)
    p.add_argument("--redo", choices=STAGES, help="그 단계부터 끝까지 다시(앞 단계 결과는 그대로 — 예: --redo S9)")
    p = sp.add_parser("replay")
    p.add_argument("--run", required=True)
    p.add_argument("--from", dest="src", required=True)
    p.add_argument("--before-user", action="store_true", help="사용자 확인 전 Opus 답(answer_opus_before_user_*.json)이 있으면 그것")
    p = sp.add_parser("apply")
    p.add_argument("--run", required=True)
    p.add_argument("--answers", action="append", required=True)
    a = ap.parse_args()
    {"init": cmd_init, "next": cmd_next, "replay": cmd_replay, "apply": cmd_apply, "unapply": cmd_unapply, "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    main()
