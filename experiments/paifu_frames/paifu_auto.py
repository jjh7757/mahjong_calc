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

단계(설계서 3절): S0 준비 · S1 판 경계(LLM) · S2 프레임 · S3 버림 기록 · S4 판 결과(LLM, 둘이 따로) · S5 대조 · 고침 ·
  S6 손패 차례 재료 + 읽기(LLM) · S7 앞뒤 검사 · 다시 읽기(LLM, 한 판 2회) · S8 조립 · S9 질문 목록 · 영향 · 보고서.
S9 차례 질문(8-3절 v2): 답의 unsure 또는 확신 말(HEDGE_*)에 걸리면 질문(questions.jsonl 의 signal 칸), 안 걸린 차례는 영향을 재서
  판마다 위 2차례를 표본(samples.jsonl, signal sample:impact — 바뀌는 순 수 0 인 차례는 표본에서 뺌). 질문은 영향 0 · 사용자 답(apply) 숨김,
  표본은 사용자 답만 숨김.
단계마다 결과 파일을 남기고 state.json 에 적는다 — 같은 명령을 다시 불러도 된 단계는 건너뛴다(멱등).

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
  S6  앱 기록 판은 손 추적 판별 출력(handtrack/config/<판>.json · results/handtrack/<판>/ · _work/<판>_feat.npz)이 없으면 멈춤(공용 폴더에 안 씀).
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

PY = sys.executable
KST = timezone(timedelta(hours=9))
SIDES = ["bottom", "right", "top", "left"]
STAGES = ["S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9"]
STAGE_NAME = {"S0": "준비", "S1": "판 경계", "S2": "프레임", "S3": "버림 기록", "S4": "판 결과", "S5": "대조 · 고침",
              "S6": "손패 차례", "S7": "앞뒤 검사 · 다시 읽기", "S8": "조립", "S9": "질문 목록 · 보고서"}
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
    rd.mkdir(parents=True, exist_ok=True)
    raw = copy.deepcopy(src_cfg.raw)
    rid = f"auto_{src_cfg.id}" if not a.run else Path(a.run).name
    if rid == src_cfg.id:
        rid += "_run"
    hand = Path(a.hand_settings).resolve() if a.hand_settings else None
    cfg = {"_note": f"paifu_auto.py init 이 {rel(src_cfg.path)} 에서 만든 실행 설정({now()}). results_dir · prep_dir · read_root · 기록기 · 패보 출력만 실행 폴더로 바꿈. "
                    "hand.call_turns · hand.row_at · paifu.event_fix 는 원래 설정 값(설정) — S5 · S6 가 자동 규칙으로 따로 만든 것과 견줌.",
           "id": rid, "rerun_of": src_cfg.id, "label": raw.get("label", src_cfg.label),
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
    wj(r.cfg_f, cfg)
    human = {"turns": list(src_cfg.truth_ids), "items": [{"id": x["id"], "kind": x["kind"], "game": x["game"]} for x in src_cfg.items]}
    r.state = {"_note": "paifu_auto.py 상태 — 단계 · 꾸러미 · 다시 읽기 · 질문", "created": now(), "source_cfg": rel(src_cfg.path),
               "game_ids": list(src_cfg.games), "reuse": rel(a.reuse) if a.reuse else None, "verify_dump": a.verify_dump,
               "hand_settings": rel(hand) if hand else None, "src_event_fix": (raw.get("paifu") or {}).get("event_fix") or {},
               "src_call_turns": list((raw.get("hand") or {}).get("call_turns") or []), "human_picked_1123": human,
               "stages": {s: {"status": "todo"} for s in STAGES}, "reread": {}, "timing": {}, "events": []}
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
    rows, lst, missing_at = [], [], []
    prev_end = None
    for g in r.games():
        a = r.app_round(g)
        sm = ((a or {}).get("discard_source") or {}).get("summary") or {}
        end_ms = to_ms(date, a["anchors"]["end"]) if a and a["anchors"].get("end") else None
        win = {"reveal": [hms_of(end_ms + APP_REVEAL_WIN_S[0] * 1000), hms_of(end_ms + APP_REVEAL_WIN_S[1] * 1000)] if end_ms else None,
               "start": [hms_of(prev_end) if prev_end else None, hms_of(sm["first_at_ms"]) if sm.get("first_at_ms") else None]}
        rows.append((g, a, win))
        if not (a and sm.get("has_at")):
            missing_at.append(g)
        else:
            first, last = sm["first_at_ms"], sm["last_at_ms"]
            t_rev = last + APP_REVEAL_AFTER_MS if end_ms is None else min(last + APP_REVEAL_AFTER_MS, end_ms - 1000)
            t_rev = max(t_rev, last + 300)
            res = a.get("result") or {}
            lst.append({"id": g, "t_deal_done": None, "t_start": hms_of(first - APP_START_LEAD_MS), "t_end_play": hms_of(last), "t_reveal": hms_of(t_rev),
                        "t_clear": None, "dealer_side": {"first": a["dealer_side"], "first_t": hms_of(first)}, "end": a["end"],
                        "revealed_sides": (res.get("tenpai_sides") or []) if a["end"] == "draw" else ([SIDES[(res["winner"] - a["bottom_seat"]) % 4]] if res.get("winner") is not None else []),
                        "win_type": {"ron": "론", "tsumo": "쯔모"}.get(res.get("type")), "win_basis": f"앱 {a.get('result_source')} {a['folders']['end']}",
                        "result": f"{a['round_label']} {a['end']}", "windows": win, "source": "app_record(코드, LLM 0)",
                        "note": f"앱 닻(태블릿 시계): 첫 버림 at {hms_of(first)} · 마지막 버림 at {hms_of(last)} · 끝 폴더 {a['anchors'].get('end')}. "
                                f"t_start = 첫 버림 at − {APP_START_LEAD_MS / 1000:g}초, t_reveal = min(마지막 버림 at + {APP_REVEAL_AFTER_MS / 1000:g}초, 끝 닻 − 1초)(추정)"})
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
        if not a or A is None:
            raise SystemExit(f"S5 앱: {g} 의 앱 판 · 버림 기록이 없다 — 앱 기록 없는 판의 S5 는 아직 없음")
        if a["bottom_seat"] != bottom:
            raise SystemExit(f"S5 앱: {g} 아래 자리 {a['bottom_seat']} ≠ {bottom}")
        wr = w5["rounds"].get(g) or {}
        off = (wr.get("clock") or {}).get("median_ms")
        off = (w5["clock"]["pooled"].get("median_ms") or 0) if off is None else off
        sub = "rec_app_dealer" if "rec_app_dealer" in (wr.get("head_used") or "") else ""
        hdir = r.d / g / sub if sub else r.d / g
        H = jl(hdir / "paifu_rec.json")
        Hd = jl(hdir / "dart_overlay.json")
        if H.get("dealer") != a["dealer"]:
            raise SystemExit(f"S5 앱: {g} 헤드 녹화 기록기 선 {H.get('dealer')} ≠ 앱 선 {a['dealer']}({rel(hdir)})")
        tf = to_ms(date, a["anchors"]["track_first"]) + off if a["anchors"].get("track_first") else to_ms(date, a["anchors"]["discard_first"]) + off
        F, D, ops, src, stats = app_merge(A, H["events"], Hd, bottom, tf, off, a["dealer"])
        if sub:
            ops.insert(0, {"op": "use_run", "run": sub, "dealer": a["dealer_side"],
                           "why": f"S3 기록기 선 ≠ 앱 선 → W5 가 앱 선 {a['dealer_side']} 로 다시 돌린 헤드 녹화 기록기({sub})를 바탕으로"})
        rr_f = r.d / g / "result_read.json"
        rr = jl(rr_f)
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
              "note": (H.get("note") or "") + " · paifu_auto S5 앱 기록 판: 사건 = 앱 버림 기록(시각은 헤드 녹화 시계) + 앱 추적 전 칸은 헤드 녹화로 채움 — "
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
                   "track_first_head": hms_of(tf), "offset_ms": off, "head": rel(hdir)}
        # 질문
        for o in ops:
            if o["op"] in ("use_run", "order", "call_keep_pre"):
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


def s6(r: Run):
    cfg = r.cfg()
    st = r.stage("S6")
    if not st.get("prepared") and cfg.app_record and r.app():
        # S6 재료(han3 turns → truthprep · turncut · slotgrid)는 판마다 손 추적 판별 출력을 읽는다 — 공용 폴더(handtrack/config · results/handtrack/<판>/ ·
        # _work/<판>_feat.npz)에 있고 손으로 만든 판별 설정(손패 주인 자리 · 영역 · t_ready)에서 handtrack run.py 가 만든 것. 없으면 여기서 멈춤(공용 폴더에 쓰지 않음).
        need = {g: [p for p in (HT / "config" / f"{g}.json", HERE / "results" / "handtrack" / g / "segments.json",
                                HERE / "results" / "handtrack" / g / "river_states.json", HERE / "results" / "handtrack" / g / "game.json",
                                HERE / "results" / "handtrack" / "_work" / f"{g}_feat.npz") if not p.exists()] for g in r.games()}
        miss = {g: [rel(p) for p in v] for g, v in need.items() if v}
        if miss:
            st["missing_handtrack"] = miss
            r.save()
            raise SystemExit("S6 재료(손패 차례 나누기 · 칸 틀 · 차례 꾸러미)는 판마다 손 추적 판별 출력이 있어야 한다 — 판 "
                             f"{len(miss)}/{len(r.games())} 에 없음(공용 폴더 · 이 흐름이 만들지 않음): "
                             + "; ".join(f"{g}: {', '.join(v)}" for g, v in miss.items())
                             + " — 손패 주인 자리(rounds_meta hero)로 handtrack/config/<판>.json(판별 설정)을 만들고 handtrack run.py 를 돌리는 단계가 앱 기록 흐름에 아직 없다.")
    if not st.get("prepared"):
        t0 = time.time()
        han3(r, "turns", log=r.log("s6_turns.log"))
        han3(r, "fix", "--write", log=r.log("s6_fix.log"))
        han3(r, "turncut", "build", *r.games(), log=r.log("s6_turncut.log"))
        todo = slotgrid_todo(r)
        st["slotgrid"] = todo
        miss = [g for g, v in todo.items() if v["missing"]]
        if miss:   # 새 반장이면 detect 가 캐시 폴더(_work/slotgrid_1117)에 쓴다 — 3반장 재생에서는 0 이어야 함
            han3(r, "slotgrid", "detect", *miss, log=r.log("s6_slotgrid_detect.log"))
        plan = read_plan(r)
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

    for tid in raised:
        sig, hh = sigs[tid]
        q = turn_row(tid, signal=sig_field(sig), hedge_hits=hh,
                     rule=" · ".join(["답의 unsure: true" if s == "unsure" else f"8-3 신호 1 확신 말({s[6:]})" for s in sig]))
        (hidden if q["impact_summary"]["zero"] else asked).append(q)
    for q in result_jobs(r):
        g = q["game"]
        d = defs[g]
        if q["kind"] == "yesno":
            q["clip"] = {"t0": hms_of(to_ms(cfg.recording["date"], d["t_end_play"]) - 25000), "t1": hms_of(to_ms(cfg.recording["date"], d["t_reveal"]) + 5000)}
        else:
            q["clip"] = {"t0": d["t_reveal"], "t1": hms_of(to_ms(cfg.recording["date"], d["t_reveal"]) + 15000)}
        q["impact_summary"] = summarize_impact(q.get("impact") or [])
        (hidden if q["impact_summary"]["zero"] else asked).append(q)
    for key in ("questions_s0", "questions_s1", "questions_w5", "questions_s4", "questions_s5"):   # s0 · w5 = 앱 기록 우선 반장만(3반장은 없음)
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
    for q in hidden:
        q.setdefault("hidden_reason", "hidden_zero_impact")

    def rank(q):
        s = q.get("impact_summary") or {}
        return (0 if s.get("result_changed") else 1, -(s.get("max_hand_turns") or 0), q["id"])
    # 신호 2 — 영향 큰 차례 표본(8-2절): 질문에 안 오른 차례(신호 1 · unsure 아님) 모두, 후보 중 가장 큰 "바뀌는 순 수" 로 줄 세워 판마다 위 2차례.
    # 같으면 순이 이른 차례. 영향을 못 잰 차례(후보 규칙 없음 · 후보 모두 조립 실패)는 줄에 못 서므로 표본에서 빼고 보고서에 수 · 까닭.
    # 8-3(v2): 바뀌는 순 수가 0 인 차례는 줄에 못 선다(판마다 많아야 2 — 모자라면 모자란 대로). 뺀 수는 zero_pool 에.
    raised_set = set(raised)
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
    r.state["signals"] = {"turns_total": len(all_ids), "raised": len(raised), "by_signal": dict(sig_count),
                          "raised_ids": {t: sig_field(sigs[t][0]) for t in raised},
                          "asked_turns": sorted(t for t in raised if t in qids), "samples": [q["id"] for q in samples],
                          "no_impact": no_impact, "sample_zero_excluded": zero_pool, "impact_s": t_imp, "rule": "8-3 v2"}
    r.state["human_compare"] = {"turns": {t: {**imp[t], "summary": summarize_impact(imp[t]["impact"]), "unsure": answers[t].get("unsure"),
                                              "signal": sig_field(sigs[t][0]) if sigs[t][0] else None,
                                              "in_asked": t in qids, "in_sample": t in sids, "in_hidden": t in hid,
                                              "hidden_reason": (hid.get(t) or {}).get("hidden_reason"),
                                              "hidden_sample": bool((hid.get(t) or {}).get("sample"))} for t in human.get("turns", [])}}
    r.state.pop("sample", None)   # 1단계의 무작위 표본(씨앗 1124)은 8-2 로 바꿈
    r.done("S9", asked=len(asked), samples=len(samples), hidden=len(hidden), s=round(time.time() - t0, 1))
    write_report(r, asked, hidden, samples)
    return []


# ------------------------------------------------------------------ 보고서
def write_report(r: Run, asked, hidden, samples=None):
    cfg = r.cfg()
    st = r.state["stages"]
    samples = samples or []
    sg = r.state.get("signals") or {}
    human_turns = set(((r.state.get("human_picked_1123") or {}).get("turns")) or [])
    L = [f"# 자동 패보 실행 보고서 — {cfg.label} (`{cfg.id}`)", "",
         f"- 실행 폴더: `{rel(r.d)}` · 원래 설정: `{r.state['source_cfg']}` · 만든 때 {r.state['created']} · 보고서 {now()}",
         f"- 재사용(S2): `{r.state.get('reuse')}` · 손 설정(S5): `{r.state.get('hand_settings')}`",
         f"- **사용자가 볼 양: 질문 {len(asked)}개 + 표본 {len(samples)}개 = {len(asked) + len(samples)}개**(`questions.jsonl` · `samples.jsonl` — 표본은 질문 수와 따로 셈, 설계서 8-2 · 8-3절)", ""]
    if len(asked) > 10:
        L += [f"**질문이 많음({len(asked)}개 > 10) — 원인:** 아래 질문 목록의 stage · rule · signal 칸을 볼 것(설계서 5절 실패 신호).", ""]
    L += ["## 단계", "", "| 단계 | 상태 | 요약 |", "|---|---|---|"]
    for s in STAGES:
        v = st.get(s) or {}
        keep = {k: v[k] for k in v if k not in ("status", "detail", "checks", "plan", "slotgrid", "history", "games", "same_as_reuse", "final_bad", "summary", "verify", "call_turns")}
        L.append(f"| {s} {STAGE_NAME[s]} | {v.get('status')} | {json.dumps(keep, ensure_ascii=False)[:300]} |")
    L += ["", "## 판마다", "", "| 판 | 읽은 차례 | 질문 | 표본 | 영향 0 숨김 | 사용자 답 숨김 | 기록 불확실(S5) | 다시 읽기 |", "|---|---|---|---|---|---|---|---|"]
    plan = st["S6"].get("plan") or {"hand": {}, "call": []}
    for g in r.games():
        n = len(plan["hand"].get(g, [])) + sum(1 for t in plan["call"] if cfg.game_of(t) == g)
        L.append(f"| {g} | {n} | {sum(1 for q in asked if q.get('game') == g)} | {sum(1 for q in samples if q.get('game') == g)} | "
                 f"{sum(1 for q in hidden if q.get('game') == g and q.get('hidden_reason') == 'hidden_zero_impact')} | "
                 f"{sum(1 for q in hidden if q.get('game') == g and q.get('hidden_reason') == '사용자 답(apply)')} | "
                 f"{sum(1 for q in asked + hidden if q.get('game') == g and q.get('kind') == 'record')} | {r.state['reread'].get(g, 0)} |")
    bs = sg.get("by_signal") or {}
    L += ["", "## 차례 질문 신호(설계서 8-3절 v2 — 규칙은 적용 전에 고정)", "",
          f"- 읽은 차례 {sg.get('turns_total')} 중 오른 것 {sg.get('raised')}: unsure 만 {bs.get('unsure', 0)} · hedge 만 {bs.get('hedge', 0)} · 둘 다 {bs.get('both', 0)}",
          f"- 그중 질문 목록에 남은 차례 {len(sg.get('asked_turns') or [])} (나머지는 영향 0 · 사용자 답으로 숨김)",
          f"- 영향 계산: 차례 {sg.get('turns_total')} 모두, {sg.get('impact_s')}초 · 영향을 못 잰 차례 {len(sg.get('no_impact') or {})}"
          + (": " + " · ".join(f"{k} {v}" for k, v in Counter(sg['no_impact'].values()).items()) if sg.get("no_impact") else ""), ""]
    L += [f"## 질문 목록({len(asked)}개, `questions.jsonl`)", "", "| id | 종류 | 신호 | 지금 답 | 후보 | 영향(바뀌는 손패 순 최대 · 결과) | 영상 구간 | 근거 규칙 |", "|---|---|---|---|---|---|---|---|"]
    for q in asked:
        s = q.get("impact_summary") or {}
        c = q.get("clip") or {}
        L.append(f"| {q['id']} | {q['kind']} | {json.dumps(q.get('signal'), ensure_ascii=False) if q.get('signal') else '—'} | {json.dumps(q.get('current'), ensure_ascii=False)} | "
                 f"{json.dumps(q.get('candidates'), ensure_ascii=False)} | {s.get('max_hand_turns')} · {'바뀜' if s.get('result_changed') else '같음'} | {c.get('t0')} ~ {c.get('t1')} | {q.get('rule') or q.get('why')} |")
    L += ["", f"## 영향 큰 차례 표본({len(samples)}개, `samples.jsonl` — 신호 2, 판마다 {SAMPLE_PER_GAME})", "",
          "| 판 | id | 줄 순위(줄 크기) | 바뀌는 손패 순 최대 | 결과 | 후보 | 영상 구간 |", "|---|---|---|---|---|---|---|"]
    for q in samples:
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
    L += ["", "## 정답", "", "정답 없음 — 읽기끼리의 일치와 앞뒤 검사. 재생은 LLM 호출 0 · 하위 에이전트 0 · 토큰 0.", ""]
    wt(r.d / "report.md", "\n".join(L))


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
    for s in STAGES:
        v = st.get(s) or {}
        keep = {k: v[k] for k in v if k not in ("status", "detail", "checks", "plan", "slotgrid", "history", "games", "same_as_reuse", "final_bad", "summary", "verify", "call_turns", "app", "how", "advance", "error")}
        L.append(f"| {s} {STAGE_NAME[s]} | {v.get('status')} | {json.dumps(keep, ensure_ascii=False)[:300]} |")
    qn = {k: len(r.state.get(k) or []) for k in ("questions_s0", "questions_s1", "questions_w5", "questions_s4", "questions_s5")}
    L += ["", f"- 지금까지 질문 후보: {qn}(S9 에서 questions.jsonl 로 모음 — W5 것은 w5_questions.jsonl 에 먼저 씀, S5 가 W5 의 record 질문을 대신함)", ""]
    L += app_report_lines(r)
    L += ["", "## 정답", "", "정답 없음. 이 보고서까지 LLM 호출 0 · 하위 에이전트 0.", ""]
    wt(r.d / "report.md", "\n".join(L))


# ------------------------------------------------------------------ next · replay · apply · status
STEP = {"S0": s0, "S1": s1, "S2": s2, "S3": s3, "S4": s4, "S5": s5, "S6": s6, "S7": s7, "S8": s8, "S9": s9}


def cmd_next(a):
    r = Run(a.run)
    if r.state is None:
        raise SystemExit("init 먼저")
    redo = getattr(a, "redo", None)
    if redo:
        # --redo S9: 그 단계와 뒤 단계만 다시(앞 단계 결과 · S6 재료는 그대로 — S9 만 고쳤을 때 488초짜리 S6 를 다시 안 돌림)
        for s in STAGES[STAGES.index(redo):]:
            r.state["stages"][s] = {"status": "todo"}
            r.state["timing"].pop(s, None)
        r.state["events"].append({"at": now(), "redo": redo})
        r.save()
    for s in STAGES:
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
    """pending.json 의 꾸러미에 3반장의 이미 있는 답을 넣는다(LLM 0). 답이 없는 꾸러미는 비워 두고 보고."""
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
        if p["stage"] == "S4":
            g = p["id"].split("_", 1)[1].rsplit("_", 1)[0]
            f = src / g / "result_read.json"
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


def user_turn_answer(u: dict, cur: dict) -> dict:
    """정답 입력 페이지 답(answers_user.json 한 칸) → 읽기 답 꼴(kind · k · j · end_order)."""
    out = {"id": cur.get("id"), "kind": u["kind"], "unsure": False, "user": True, "user_note": u.get("note"), "user_saved_at": u.get("saved_at")}
    if u["kind"] == "hand":
        out.update(k=u["k"], j=u.get("j_closed"), end_order=[str(x) for x in u["order"]])
    elif u["kind"] == "tsumogiri":
        n = len([x for x in cur.get("end_order") or [] if x != "D"]) or 13
        out.update(k=None, j=None, end_order=[str(i) for i in range(1, n + 1)])
    else:
        out.update({k: u.get(k) for k in ("k", "gone", "end_order")})
    return out


def cmd_apply(a):
    r = Run(a.run)
    cfg = r.cfg()
    applied, notq = [], []
    def lines(f):
        return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()] if f.exists() else []
    qids = {q["id"] for q in lines(r.d / "questions.jsonl")}
    sids = {q["id"] for q in lines(r.d / "samples.jsonl")}
    for af in a.answers:
        ans = jl(af)
        for k, u in ans.items():
            if k.startswith("_"):
                continue
            if "kind" in u and u["kind"] in ("hand", "tsumogiri", "call"):
                f = active_answer(r, k)
                if not f.exists():
                    notq.append(f"{k}: 읽기 답 없음")
                    continue
                cur = jl(f)
                keep = r.read / k / "answer_before_apply.json"
                if not keep.exists():
                    shutil.copyfile(f, keep)
                new = user_turn_answer(u, cur)
                same = [str(x) for x in (cur.get("end_order") or [])] == new["end_order"] and cur.get("kind") == new["kind"]
                wj(f, {**cur, **new})
                applied.append({"id": k, "kind": "turn", "same_as_before": same, "was_question": k in qids, "was_sample": k in sids})
            elif "value" in u:
                pre, what = k.split("_", 1)
                g = cfg.game_of(pre)
                f = r.d / g / "result_read.json"
                rr = jl(f)
                keep = r.d / g / "result_read_before_apply.json"
                if not keep.exists():
                    shutil.copyfile(f, keep)
                if what == "ura":
                    same = (rr.get("ura_indicators") or [None])[0] == u["value"]
                    if not same:
                        rr["ura_indicators"] = [u["value"]] + list((rr.get("ura_indicators") or [])[1:])
                elif what == "haitei":
                    chk = jl(r.paifu / "_check.json")[g]
                    cur = chk.get("wall_left_end") == 0
                    want = u["value"] == "yes"
                    same = cur == want
                    if not same:
                        rr["last_tile"] = want
                else:
                    notq.append(f"{k}: 모르는 항목")
                    continue
                if not same:
                    wj(f, rr)
                applied.append({"id": k, "kind": what, "same_as_before": same, "was_question": k in qids, "was_sample": k in sids})
    r.state["answered"] = sorted(set(r.state.get("answered") or []) | {x["id"] for x in applied})
    for s in ("S7", "S8", "S9"):
        r.state["stages"][s] = {"status": "todo"}
        r.state["timing"].pop(s, None)   # 걸린 시간은 이번 바퀴 것만(옛 코드는 누적)
    r.state["reread"] = {}
    r.state["events"].append({"at": now(), "apply": applied, "skipped": notq, "files": [rel(x) for x in a.answers]})
    r.save()
    print(f"apply: {len(applied)}칸 (전과 같음 {sum(x['same_as_before'] for x in applied)}) · 건너뜀 {notq}")
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
    r.state["events"].append({"at": now(), "unapply": back, "answered_was": r.state.get("answered")})
    r.state["answered"] = []
    for s in ("S7", "S8", "S9"):
        r.state["stages"][s] = {"status": "todo"}
        r.state["timing"].pop(s, None)
    r.state["reread"] = {}
    r.save()
    print(f"unapply: {len(back)}개 되돌림 {back}")
    cmd_next(argparse.Namespace(run=a.run))


def cmd_status(a):
    r = Run(a.run)
    for s in STAGES:
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
