"""대국 뒤 자동 패보 — 반장 관리자 하나 + 읽기 작업자 여럿, 상태는 LangGraph(설계서 docs/paifu_auto_agent_design_1124.md 8-20, 2026-11-26 오후, LLM 0).

  python -X utf8 experiments/paifu_frames/paifu_graph.py start  --run <실행> (--visit <방문> [--game <대국>] | --hanchan <설정>) [init 옵션]
  python -X utf8 experiments/paifu_frames/paifu_graph.py go     --run <실행> --hands replay|session|api [--replay-from <실행>] [--replay-sup-from <실행>]
                                                                 [--before-user] [--max-concurrency 8] [--confirm auto|page]
                                                                 [api 손: --api-games <판>[,…][,manager] · --reuse-api-from <앞 실행> · --max-usd 15 ·
                                                                  --api-fake replay[:out=<출력 토큰>](가짜 클라이언트 — API 0) | --i-mean-it(진짜 API)]
  python -X utf8 experiments/paifu_frames/paifu_graph.py resume --run <실행> [--answers <답 파일>] [--max-usd <새 한도>] [--i-mean-it]
  python -X utf8 experiments/paifu_frames/paifu_graph.py status --run <실행>
  python -X utf8 experiments/paifu_frames/paifu_graph.py fork   --from <끝난 실행> --at <단계> --run <새 실행>   # 베껴 그 단계부터만 다시(이어서 go)
  python -X utf8 experiments/paifu_frames/paifu_graph.py fork   --from <반장 실행> --at <단계> --games <판>[,…]|all --run <새 반장>   # 판 실행 <반장>__<판> 을 그 단계에서
                                                                 # <새 반장>__<판> 으로(새 반장은 --at S4) — 이어서 go --run <새 반장> --games <판> …
11-26 밤 이어 가기 고침: 판 LLM 이 실행 한도 · 죽음으로 끊긴 뒤 같은 go(--games) · resume 을 다시 걸면 ① 판 꾸러미 draft.json 의 다시 읽기 가운데 답이 없는 것을
  판 LLM 을 부르기 전에 먼저 채우고(도중 찌꺼기 work/ · 답 사본은 graph/aborted/<꾸러미>/<k>/ 로 · 앞 시도 돈은 api_usage 에 이미 한 번 — 결과 파일은 source.aborted 기록만)
  ② 판 LLM 은 첫 메시지(agent/<판>/first_message.md — 첫 시도 것 고정) · 앞 호출(calls.jsonl) · 이미 실행한 도구 결과(conv.jsonl)로 앞 대화를 그대로 잇고
  끊긴 응답의 도구만 실행해 그 결과(다시 읽기 답)를 돌려줌. 판 실행 폴더를 S4 뒤에서 fork 하면 판 실행 그대로(state.unit 유지) — 그 폴더에 바로 go 도 됨.
  fork 가 베낀 순 결과 · 꾸러미의 돈은 이 실행이 쓴 돈이 아님(cost.reused · source.orig_usd — 실행 한도 --max-usd 는 graph/api_usage.jsonl 의 새 돈만 셈).
8-23(11-26 밤) — 기본 꼴 --layout game: 판마다 판 LLM 하나(orchestrator-workers, 관리자 LLM 없음 — 판 LLM 지시문 템플릿 paifu_game_task.md, 도구
  read_game · read_turn · reread · take · ask · check · finish 는 GameRun 이 실행), 순별 결과 파일 turns/<순>/<시도>.json(paifu.turn/1) · 판별 결과 파일
  games/<판>.json(paifu.game/1) — 꼴 · 검사 · 병합 · export 는 paifu_results.py. 캐시 대체 go --reuse-from <실행>[,…]: 꾸러미 입력(정규화 TASK · 그림 ·
  꾸러미에서 모델이 읽을 수 있는 파일 전부 = task · images · inputs sha 셋)이 같은 순 · 꾸러미 결과와 판 LLM 호출(앞 메시지 사슬 sha)을 베낌. 8-23 전 실행
  (예: 진짜 API auto_h2_apiR1)은 api 손 꾸러미를 그 자리에서 열쇠로 셈(paifu_results.ReuseIndex._backfill). 옛 꼴은 --layout manager(8-20 — 옛 실행 재현용).
  실행도 판 단위: go --run <반장 실행> --games <판>[,…]|all — 판마다 판 실행 폴더 <반장 실행>__<판>(반장 실행을 --at S4 로 베끼고 state 의 판만 좁힘)에서
  판 몫 단계(S4 → S5 판 몫 → S6a → S6b → S6 → S7 → 판 LLM)를 --unit-parallel 개씩 나란히(동시 LLM 수는 --max-concurrency 하나가 모든 판 실행에 걸쳐 셈),
  <판 실행>/games/<판>.json 에서 멈춤. 11-27: 처음 시작한 반장(start 만 — state.json 없음 또는 S0 ~ S3 가 안 끝남)에 go --games 를 걸면 먼저 반장 공통 앞 단계
  (paifu_auto init + next 를 한 단계씩 — S4 앞에서 끊는 감싸개 _next_upto, 꾸러미는 이 go 의 손)를 그래프 thread <실행>#prefix 로 돌린 뒤 판 실행으로 이어짐
  (끊기면 같은 go — 끝난 단계는 state.json 으로 건너뜀, 기록 graph/prefix.json). 모든 판의 판 실행이 끝나면 반장 조립(assemble — 판 몫 파일 · 반장 한 파일의 판 줄 · state 합침) → 반장 S5(판 사이
  이어지는 값: 공탁 · 국 · 본장 검사 · 아래 자리) → S8 · S9 → 자동 확정(기본) 또는 확인 멈춤(--confirm page).
11-27 설계서 8-26: S9 뒤 갈림 하나 — 기본 --confirm auto 는 확인 페이지 없이 paifu_run.auto_confirm(paifu_auto.py autoconfirm — 질문감 · 낮은 확신 순의
  뽑기 · 버림 사건에 guess · 판 정보 질문은 패보 머리 estimates · paifu_source 출처 · report.md 절)으로 done. --confirm page 는 옛 길(확인 페이지 멈춤).
  판 실행 · 반장 조립 · fork 뒤 go · resume 모두 graph 상태의 opts.confirm(없으면 auto)을 따름. 이미 확인 차례를 연 실행(옛 page 멈춤)을 resume 하면 옛 길 그대로.
(저장소 루트에서. 시험용 옵션 go · resume: --hand-delay <초>(손이 꾸러미 하나를 채우기 전에 쉼 — 동시 수를 보려고) · --die-after <k>(이 프로세스에서
 k번째 꾸러미를 채운 바로 뒤 os._exit — 재개 시험).)

세 층 — 띄우는 곳은 이 그래프 하나뿐, 띄워진 것은 아무것도 띄우지 않는다:
  그래프(코드) — 단계 순서(paifu_auto.py next 를 그대로 부름) · 꾸러미 나눠 내기(Send) · 동시 수(config max_concurrency) · 단계마다 저장(SqliteSaver,
                 <실행>/graph.sqlite, thread_id = 실행 폴더 이름)과 재개 · 관리자 결정 실행(paifu_sup.py 명령) · 검사 · 사용자 확인 멈춤(interrupt).
  관리자(LLM 역할 하나, 라운드마다 한 번) — mgr/round_<n>/summary.md · TASK.md 를 보고 mgr/round_<n>/decision.json 을 씀. 영상 · 프레임을 안 열고 아무것도 안 띄움.
  작업자 — S4 · S6a · S6 · S7 꾸러미와 관리자 reread 가 만든 다시 읽기 꾸러미(TASK.md + 답 파일, 지금 꾸러미 그대로).
  손(꾸러미를 채우는 것) — replay(옛 실행의 답을 베낌, LLM 0) · session(멈춰서 꾸러미 목록을 냄 → 세션이 채우고 resume) ·
  api(설계서 8-21 — paifu_apihand.py: TASK.md 를 그대로 첫 메시지로 Claude API 가 도구로 채움. --api-games 면 고른 판의 꾸러미만 api · 나머지 replay
  (관리자 꾸러미는 판이 여럿이라 "manager" 를 적을 때만 api). --api-fake 는 가짜 클라이언트(재생 답을 같은 도구 걸음으로 씀 · API 0),
  진짜 호출은 go · resume 마다 --i-mean-it 이 있어야 함. 돈: 꾸러미 한도(paifu_apihand.PKG_USD) · 실행 한도 --max-usd(넘으면 stop, resume --max-usd 로 이어 감)).

마디: stage(paifu_auto next — 꾸러미가 있으면 work 로 Send, S7s 판 supervisor 꾸러미는 손에 안 보내고 관리자 고리로) · work(꾸러미 하나를 손으로) ·
  join(답 꼴 검사 — 차례 답은 paifu_auto.answer_form_error, 틀리면 한 번 다시 냄) · mgr_prep(열린 판 요약 · 관리자 지시문) · manager(관리자 꾸러미를 손으로) ·
  mgr_apply(결정 → paifu_sup reread · take · ask · (재생만) set — 다시 읽기는 work 로 Send) · mgr_close(손댄 판 check → accept 판 done → 열린 판이 남으면 다음
  라운드, MAX_ROUNDS 넘으면 마감 검사 ① 대상 차례를 ask 로 올리고 done) · confirm(기본 = 자동 확정 · --confirm page = paifu_confirm prep 뒤 interrupt) · answer(paifu_run.py answer 와 같은 일 —
  그것을 부름, 추가 질문이 있으면 confirm 으로 한 번 더).
관리자 재생(replay 손): 옛 실행의 판 꾸러미 sup/<판>/log.jsonl 명령 순서를 라운드로 자름(연달아 나온 reread 묶음이 끝나는 곳이 경계, status · check · pack 은 버림,
  done → accept, set → replay_set, 로그가 paifu_sup replay 뿐이면 그 출처 꾸러미를 따라감). 글(set 답 · 근거 · 까닭, ask 후보 · 까닭)은 그 꾸러미 draft.json 에서
  순서대로. 다시 읽기 답은 그 꾸러미 reread/<차례>_r<n>/answer.json. 계획은 <실행>/graph/replay_plan.json(관리자 꾸러미 mgr/ 밖).
기록: <실행>/graph/fills.jsonl(손이 꾸러미를 채운 줄 — filled · already · still_empty · badform_*) · events.jsonl(마디 일) · mgr/round_<n>/applied.jsonl
  (그 라운드에 실행한 명령 — 재개 때 같은 명령을 두 번 안 부름).
출력: go · resume 은 표준 출력에 JSON 한 덩어리 — status read(채울 꾸러미 목록, session 손은 한 번에 max_concurrency 개까지) · page(사용자 확인) · done · error ·
  stop. 종료 코드는 paifu_run.py 와 같은 표: 0 done · 1 error · 2 stop · 3 read · 4 page.
paifu_auto.py · paifu_sup.py · paifu_run.py · paifu_confirm.py 는 고치지 않고 하위 프로세스(또는 paifu_run 의 확인 차례 함수)로 부른다.
"""
from __future__ import annotations

import argparse
import json
import operator
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Annotated, TypedDict

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import paifu_apihand as ah  # noqa: E402
import paifu_auto as pa  # noqa: E402
import paifu_results as pr  # noqa: E402
import paifu_run as prun  # noqa: E402

from langgraph.checkpoint.sqlite import SqliteSaver  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402
from langgraph.types import Command, Send, interrupt  # noqa: E402

PY = sys.executable
AUTO = HERE / "paifu_auto.py"
SUP = HERE / "paifu_sup.py"
RUN_PY = HERE / "paifu_run.py"
EXIT = prun.EXIT
MAX_ROUNDS = 3          # 관리자 라운드 한도(8-20 마디 5)
MC_DEFAULT = 8
MC_MAX = 20
DB = "graph.sqlite"
HANDS = ("replay", "session", "api")
MGR_DO = ("reread", "take", "ask", "accept", "replay_set")
TAKE_FROM = ("first", "r1", "r2")
DROP_CMDS = {"status", "check", "pack", "score"}
TURN_STAGES = ("S6", "S7", "sup_reread")      # 답 꼴 검사를 answer_form_error 로 하는 꾸러미
KIND_OF_STAGE = {"S1": "boundary_read", "S4": "result_read", "S6a": "prep_read", "S6": "turn_read", "S7": "turn_reread", "sup_reread": "reread"}

LOCK = threading.Lock()       # 기록 파일 · 동시 수 셈
FILL_LOCK = threading.Lock()  # 답 넣기 + 기록(죽이기 시험이 그 사이에 끼지 않게)
CONC = {"n": 0, "max": 0}
PLAN_LOCK = threading.Lock()  # 재생 계획 파일(graph/replay_plan.json)
SLOT = {"sem": None}          # game 꼴: 판 LLM · 그 다시 읽기 순 호출이 함께 쓰는 자리(max_concurrency 개)
LAYOUTS = ("game", "manager")
GAME_TASK = HERE / "paifu_game_task.md"   # 판 LLM 지시문 템플릿(설계서 8-23 — 8-10 판 supervisor 판단 기준을 옮김)
TEST = {"hand_delay": 0.0, "die_after": None, "fills": 0, "die_after_stage": None}
_CACHE = {}


class GraphError(Exception):
    pass


# ------------------------------------------------------------------ 작은 도구
def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def rp(p) -> str:
    return pa.rel(p)


def absp(p) -> Path:
    return pa.hcfg._p(p).resolve()


def posix(p) -> str:
    return Path(p).resolve().as_posix()


def append(f: Path, o: dict):
    f.parent.mkdir(parents=True, exist_ok=True)
    with LOCK:
        with open(f, "a", encoding="utf-8", newline="\n") as h:
            h.write(json.dumps(o, ensure_ascii=False) + "\n")


def gdir(run) -> Path:
    return Path(run) / "graph"


def ev(run, what: str, **kw):
    append(gdir(run) / "events.jsonl", {"at": now(), "what": what, **kw})


def emit(o: dict, code: str):
    sys.stdout.write(json.dumps({"status": code, **o}, ensure_ascii=False, indent=1) + "\n")
    sys.stdout.flush()
    raise SystemExit(EXIT[code])


def runner(run) -> prun.Runner:
    r = prun.Runner(str(run))
    if r.o is None:
        raise GraphError(f"{prun.RUNNER} 이 없음 — start 먼저")
    return r


def is_turn_pkg(p: dict) -> bool:
    return p.get("stage") in TURN_STAGES and bool(p.get("turn"))


def pkg_view(p: dict) -> dict:
    return {"id": p["id"], "kind": p.get("kind") if p.get("stage") != "sup_reread" else "reread",
            "stage": p.get("stage"), "game": p.get("game"), "turn": p.get("turn"), "task": p.get("task"), "answer": p.get("answer"), "dir": p.get("dir"),
            **({"reread": p["reread"]} if p.get("reread") else {})}


def tok_est(s: str) -> int:
    """어림 토큰 = 한글 음절 1자 ≈ 1토큰 + 그 밖의 글자 3.5자 ≈ 1토큰(세지 않은 어림 — 실제 토크나이저 아님)."""
    h = sum(1 for ch in s if "가" <= ch <= "힣")
    return round(h + (len(s) - h) / 3.5)


def sub(run, what: str, args: list) -> tuple:
    """하위 프로세스 — paifu_run.Runner.sub 와 같은 꼴(로그 <실행>/logs/runner_<번호>_<what>.log · runner.json calls)."""
    r = runner(run)
    return r.sub(what, args)


# ------------------------------------------------------------------ 손 — replay(옛 실행의 답을 베낌, LLM 0)
def src_cfg_of(run) -> object:
    k = ("src_cfg", str(run))
    with LOCK:
        if k not in _CACHE:
            r = pa.Run(Path(run))
            _CACHE[k] = pa.hcfg.load(r.state["source_cfg"], check=False)
        return _CACHE[k]


def first_answer_of(src: Path, tid: str):
    """옛 실행 폴더(state.json 이 있는 곳)의 처음 답 — paifu_auto.first_answer_file(판 supervisor 꾸러미 사본 → answer_r0 → answer_before_apply → 지금 답)."""
    k = ("src_run", str(src))
    with LOCK:
        if k not in _CACHE:
            sr = pa.Run(src)
            _CACHE[k] = (sr, sr.cfg()) if sr.state is not None else (None, None)
        sr, cfg = _CACHE[k]
    if sr is None:
        return None
    f = pa.first_answer_file(sr, tid, cfg)
    return f if f.exists() else None


def replay_source(run, p: dict, opts: dict):
    """꾸러미 하나의 재생 답: ("copy", 파일) · ("write", 내용) · None(답 없음).
    S1 · S4 · S6a · S6 · S7 은 paifu_auto.cmd_replay 와 같은 출처 — S6 · S7 은 그 출처(<설정 read_root>/<차례>)에 없으면 --replay-from 실행 폴더의 처음 답
    (first_answer_file). 판 supervisor 다시 읽기(sup_reread)는 관리자 재생 계획의 꾸러미 reread/<차례>_r<n>/answer.json."""
    stage = p["stage"]
    dst = Path(p["answer"])
    if stage == "sup_reread":
        plan = load_plan(run)
        g = (plan or {}).get("games", {}).get(p["game"])
        if not g:
            return None
        f = Path(g["src_pack"]) / "reread" / f"{p['turn']}_r{p['reread']}" / "answer.json"
        return ("copy", f) if f.exists() else None
    if not opts.get("replay_from"):
        return None
    src = pa.hcfg._p(opts["replay_from"])
    if stage == "S1":
        rpf = src / "rounds_p.json"
        if not rpf.exists():
            return None
        r = pa.Run(Path(run))
        rp_ = pa.jl(rpf)
        have = {x["id"]: x for x in rp_["rounds"]}
        v = {x["id"]: x for x in pa.jl(pa.V1114_ROUNDS)["rounds"]}
        lst = [have.get(g) or v.get(g) for g in r.games()]
        if any(x is None for x in lst):
            return None
        return ("write", {"source": rp_.get("source"), "_replay": f"{pa.rel(rpf)}(p 판) + {pa.rel(pa.V1114_ROUNDS)}(그 밖의 판 — 11-23 headrec_rounds.json 의 출처)",
                          "rounds": lst})
    f = None
    if stage == "S4" and p.get("kind") == "app_draw_reveal":
        f = src / "s4" / p["game"] / p["id"].rsplit("_", 1)[1] / "reveal_read.json"
    elif stage == "S4":
        g = p["id"].split("_", 1)[1].rsplit("_", 1)[0]
        f = src / g / "result_read.json"
    elif stage == "S6a":
        g = p["game"]
        f = next((c for c in (src / "s6a" / g / "answer.json", src / g / "answer.json", src / f"{g}.json") if c.exists()), None)
    elif stage in ("S6", "S7"):
        tid = p["turn"]
        d = pa.hcfg.WORK / src_cfg_of(run).read_root / tid
        f = d / "answer.json"
        if opts.get("before_user"):
            b = sorted(d.glob("answer_opus_before_user_*.json"))
            if b:
                f = b[0]
        if not f.exists() or f.resolve() == dst.resolve():
            f = first_answer_of(src, tid)
    if f is None or not Path(f).exists():
        return None
    return ("copy", Path(f))


def put_answer(p: dict, how):
    dst = Path(p["answer"])
    dst.parent.mkdir(parents=True, exist_ok=True)
    if how[0] == "copy":
        shutil.copyfile(how[1], dst)
    else:
        pa.wj(dst, how[1])


def replay_text(run, p: dict, opts: dict):
    """가짜 api 손(--api-fake replay)이 write_file 로 쓸 답 글 = replay 손이 넣을 바이트 그대로(없으면 None)."""
    how = replay_source(run, p, opts)
    if how is None:
        return None
    if how[0] == "copy":
        return Path(how[1]).read_bytes().decode("utf-8")
    return json.dumps(how[1], ensure_ascii=False, indent=1)


def fill_like_replay(run, p: dict, opts: dict) -> str | None:
    """세션 손 시험 스크립트도 쓰는 것: replay 손과 같은 출처로 꾸러미 하나를 채움. 채웠으면 출처 글, 없으면 None."""
    if pa.answered(p):
        return "이미 있음"
    how = replay_source(run, p, opts)
    if how is None:
        return None
    put_answer(p, how)
    return rp(how[1]) if how[0] == "copy" else "S1 재생 글"


# ------------------------------------------------------------------ 결과 파일 · 캐시(설계서 8-23 — paifu_results)
def attempt_of(p: dict) -> str | None:
    """순 결과 파일의 시도 이름: S6 → first · 판 다시 읽기 → r<n> · S7 다시 읽기 → s7r<k>. 순 꾸러미가 아니면 None."""
    st = p.get("stage")
    if not p.get("turn"):
        return None
    if st == "S6":
        return "first"
    if st == "sup_reread":
        return f"r{p['reread']}"
    if st == "S7":
        return f"s7r{p['reread']}"
    return None


def reuse_index(opts: dict):
    rf = opts.get("reuse_from") or []
    if not rf:
        return None
    k = ("reuse", tuple(rf))
    with LOCK:
        if k not in _CACHE:
            _CACHE[k] = pr.ReuseIndex([absp(x) for x in rf])
        return _CACHE[k]


def copy_answer_text(src_run: Path, src_f: Path, run: Path, dst: Path):
    """캐시에서 답 베끼기 — 답 글 안의 옛 실행 경로를 새 실행 경로로(8-21 try_reuse 와 같은 바꿈)."""
    src_run, run = Path(src_run).resolve(), Path(run).resolve()
    txt = Path(src_f).read_bytes().decode("utf-8")
    for a, b in ((src_run.as_posix(), run.as_posix()), (str(src_run), str(run)), (str(src_run).replace("\\", "\\\\"), str(run).replace("\\", "\\\\")),
                 (rp(src_run), rp(run))):
        txt = txt.replace(a, b)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(txt.encode("utf-8"))


def pkg_inp(run, p: dict) -> dict | None:
    """꾸러미 입력 sha(정규화한 TASK · 그림 목록). 못 세면 None(캐시 대체 안 함)."""
    try:
        fr = None
        if p.get("stage") == "sup_reread":
            m = re.search(r"## 이번 읽기에서 더 볼 곳\n([^\n]+)", Path(p["task"]).read_text(encoding="utf-8"))
            fr = m.group(1).strip() if m else None
        return pr.pkg_input(run, p, None if p.get("stage") != "sup_reread" else "reread", fr)
    except Exception as e:  # noqa: BLE001
        ev(run, "input_fail", pkg=p["id"], why=f"{type(e).__name__}: {e}"[:300])
        return None


def try_reuse_from(run, p: dict, opts: dict, inp: dict | None):
    """--reuse-from: 입력 sha 가 같은 결과(순 결과 파일 · 꾸러미 입력 기록)가 있으면 답을 베낌 → (출처 실행, 원래 손, 원래 돈) · 없으면 None."""
    ix = reuse_index(opts)
    if ix is None or inp is None:
        return None
    run = Path(run).resolve()
    if attempt_of(p):
        hit = ix.find_turn(inp)
        if not hit:
            return None
        rr, f, doc = hit
        src_ans = rr / (doc["source"].get("pkg") or "") / (doc["source"].get("answer_file") or Path(p["answer"]).name)   # 8-23 전 실행(backfill)은 처음 답 파일
        if doc["source"].get("pkg") and src_ans.exists():
            copy_answer_text(rr, src_ans, run, Path(p["answer"]))
        else:
            pa.wj(Path(p["answer"]), pr.old_answer(doc))
        oh = doc["source"].get("orig_hand") if doc["source"].get("hand") == "reuse" else doc["source"].get("hand")
        ou = doc["source"].get("orig_usd") if (doc["source"].get("hand") == "reuse" or doc["cost"].get("reused")) else doc["cost"].get("usd")   # fork 가 베낀 결과도 원래 돈
        return rr, oh, ou
    hit = ix.find_pkg(inp)
    if not hit:
        return None
    rr, x = hit
    src_ans = rr / x["answer_rel"]
    if not src_ans.exists():
        return None
    copy_answer_text(rr, src_ans, run, Path(p["answer"]))
    return rr, (x.get("orig_hand") if x.get("hand") == "reuse" else x.get("hand")), (x.get("orig_usd") if x.get("hand") == "reuse" else x.get("usd"))


def record_result(run, p: dict, hand: str, inp: dict | None, *, from_run=None, orig_hand=None, orig_usd=None, res: dict | None = None):
    """답이 찬 꾸러미 하나의 결과 기록: 순 꾸러미 → turns/<순>/<시도>.json, 그 밖(S1 · S4 · S6a) → graph/pkg_inputs.jsonl(캐시 재료)."""
    run = Path(run).resolve()
    att = attempt_of(p)
    h = "reuse" if from_run else ("api" if hand.startswith("api") else "session" if hand.startswith("session") else "replay")
    if att:
        if h == "api":
            cost = pr.cost_of_log(p["dir"])
        else:
            cost = pr.zero_cost(reused=h == "reuse")
        fr = from_run
        if h == "replay":
            fr = (load_plan(run) or {}).get("source_run") if p.get("stage") == "sup_reread" else None
            fr = fr or ((opts_of(run) or {}).get("replay_from"))
        src_extra = {}
        pr.write_turn(run, p.get("game"), p["turn"], att, p["answer"], hand=h, from_run=fr, pkg_dir=p["dir"], inp=inp, cost=cost,
                      orig_hand=orig_hand, note=None, aborted=pr.aborted_of_log(p["dir"]) if h == "api" else None)
        if h == "reuse":
            f = pr.turn_file(run, p["turn"], att)
            d = pr.jl(f)
            d["source"]["orig_usd"] = orig_usd
            pr.wj(f, d)
        return
    if inp is None:
        return
    append(gdir(run) / "pkg_inputs.jsonl", {"at": now(), "id": p["id"], "stage": p.get("stage"), "game": p.get("game"), **inp,
                                            "answer_rel": pr.rel_to(p["answer"], run), "hand": h, "from_run": rp(from_run) if from_run else None,
                                            "orig_hand": orig_hand, "orig_usd": orig_usd, "usd": (res or {}).get("usd", 0.0)})


def opts_of(run):
    f = gdir(run) / "graph.json"
    return pa.jl(f) if f.exists() else None


# ------------------------------------------------------------------ 관리자 재생 계획(옛 sup/<판>/log.jsonl → 라운드)
def plan_file(run) -> Path:
    return gdir(run) / "replay_plan.json"


def load_plan(run):
    f = plan_file(run)
    return pa.jl(f) if f.exists() else None


def log_lines(f: Path) -> list:
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()] if f.exists() else []


def plan_game(pack: Path) -> dict:
    """판 꾸러미 하나의 명령 기록 → 라운드 목록. 로그가 paifu_sup replay 뿐인 꾸러미는 그 출처를 따라감."""
    chain = []
    for _ in range(5):
        L = log_lines(pack / "log.jsonl")
        acts = [x for x in L if x.get("ok") and x["cmd"] in ("reread", "take", "set", "ask")]
        rep = [x for x in L if x.get("ok") and x["cmd"] == "replay"]
        if rep and not acts:
            chain.append(posix(pack))
            pack = Path(rep[-1]["args"]["src"]).resolve()
            continue
        break
    L = log_lines(pack / "log.jsonl")
    if not L:
        return {"src_pack": posix(pack), "chain": chain, "rounds": [], "note": "명령 기록 없음"}
    draft = pa.jl(pack / "draft.json")
    sets_q, asks_q = list(draft.get("sets") or []), list(draft.get("asks") or [])
    rounds, cur, in_rr, notes = [], [], False, []
    cnt = Counter()
    for x in L:
        if not x.get("ok") or x["cmd"] in DROP_CMDS:
            continue
        c, a = x["cmd"], x.get("args") or {}
        if c == "reread":
            act = {"do": "reread", "turn": a["turn"], "frames": a.get("frames"), "why": "재생 — 옛 판 supervisor 의 다시 읽기"}
            if a.get("note"):
                notes.append(f"{a['turn']}: 옛 version 1 다시 읽기 주의 글(note)은 지금 paifu_sup reread 가 받지 않아 뺌(frames 없음)")
            cur.append(act)
            in_rr = True
            cnt[c] += 1
            continue
        if in_rr:
            rounds.append(cur)
            cur, in_rr = [], False
        if c == "take":
            act = {"do": "take", "turn": a["turn"], "from": a["src"], "why": "재생 — 옛 take"}
        elif c == "set":
            s0 = sets_q.pop(0)
            if s0["turn"] != a["turn"]:
                raise GraphError(f"재생 계획: {pack.name} set 순서가 draft 와 다름({s0['turn']} ≠ {a['turn']})")
            act = {"do": "replay_set", "turn": a["turn"], "answer": s0["answer"], "evidence": s0.get("evidence") or "", "why": s0.get("why") or ""}
        elif c == "ask":
            q = asks_q.pop(0)
            if q["turn"] != a["turn"]:
                raise GraphError(f"재생 계획: {pack.name} ask 순서가 draft 와 다름({q['turn']} ≠ {a['turn']})")
            act = {"do": "ask", "turn": a["turn"], "candidates": q.get("candidates") or "", "why": q.get("why") or ""}
        elif c == "done":
            act = {"do": "accept", "why": "재생 — 옛 done"}
        else:
            continue
        cnt[c] += 1
        cur.append(act)
    if cur:
        rounds.append(cur)
    return {"src_pack": posix(pack), "chain": chain, "rounds": rounds, "counts": dict(cnt), "notes": notes}


def ensure_plan(run, sup_src, games: list) -> dict:
    f = plan_file(run)
    if f.exists():
        return pa.jl(f)
    src = pa.hcfg._p(sup_src)
    plan = {"_note": "paifu_graph.py 관리자 재생 계획(LLM 0) — 옛 판 supervisor 꾸러미의 명령 기록을 라운드로 자름. 관리자 꾸러미(mgr/)에는 안 넣음.",
            "made": now(), "source_run": rp(src), "games": {}}
    for g in games:
        plan["games"][g] = plan_game(src / "sup" / g)
    pa.wj(f, plan)
    return plan


def replay_decision(run, n: int, open_games: list, opts: dict) -> dict:
    plan = ensure_plan(run, opts.get("replay_sup_from") or opts.get("replay_from"), list(open_games))
    games = {}
    for g in open_games:
        rs = (plan["games"].get(g) or {}).get("rounds") or []
        if len(rs) >= n:
            games[g] = rs[n - 1]
    return {"games": games, "note": f"재생(LLM 0) — 옛 판 supervisor 명령 기록의 라운드 {n}", "replay": True}


# ------------------------------------------------------------------ 상태
def _max(a, b):
    return max(a or 0, b or 0)


class GS(TypedDict, total=False):
    run: str
    opts: dict
    phase: str             # work · mgr · mgr_work · confirm · answer · done
    stage: str
    todo_all: list         # 이번에 나눠 낼 꾸러미 전부
    batch: list            # 지금 낸 꾸러미(session 손이면 max_concurrency 개까지)
    retried: list          # 답 꼴이 틀려 한 번 다시 낸 꾸러미 id
    join_next: str
    mgr: dict
    mgr_next: str
    answers_file: str
    answer: dict
    log: Annotated[list, operator.add]
    max_conc: Annotated[int, _max]


def eff_hand(opts: dict, stage, p: dict | None = None) -> str:
    """꾸러미 단계의 손 — --session-stages 에 든 단계(S7s = 관리자 결정 · 판 supervisor 다시 읽기)는 session, 나머지는 --hands.
    --hands api + --api-games(8-21 "한 판 먼저"): 고른 판의 꾸러미만 api, 나머지는 replay. 관리자 꾸러미는 판이 여럿이라 api_games 에 "manager" 가 있을 때만 api."""
    st = "S7s" if stage in ("sup_reread", "manager", "S7s", "game") else stage
    if st in (opts.get("session_stages") or []):
        return "session"
    h = opts["hands"]
    ag = opts.get("api_games")
    if h == "api" and ag is not None:
        if stage == "manager":
            return "api" if "manager" in ag else "replay"
        return "api" if p is not None and p.get("game") in ag else "replay"
    return h


def cut(batch: list, opts: dict) -> list:
    return batch[:opts["max_concurrency"]] if any(eff_hand(opts, p.get("stage"), p) == "session" for p in batch) else batch


# ------------------------------------------------------------------ 마디: stage
def n_stage(s: GS):
    run = s["run"]
    r = runner(run)
    if r.state() is None:
        rc, txt, log = r.sub("init", [AUTO, "init", "--hanchan", r.o["hanchan"], "--run", rp(r.d), *r.o.get("init_args", [])])
        if rc != 0 or r.state() is None:
            raise GraphError(f"paifu_auto init 실패(rc {rc}) — {rp(log)}: {prun.tail(txt, 800)}")
    last, same = None, 0
    until = s["opts"].get("until")   # 11-27: 이 단계 앞에서 멈춤 — "S4" = 처음 시작한 반장의 공통 앞 단계(S0 ~ S3) · "S6a" = 판 실행 앞부분(S4 · S5, 다음 판이 쓸 고친 기록)
    for _ in range(prun.MAX_STEPS):
        if until and until_done(run, until):
            ev(run, "stage", stage=until, to="until_end")
            return {"phase": "until_end", "stage": until, "todo_all": [], "batch": []}
        if s["opts"].get("games") and ((r.state()["stages"].get("S7s") or {}).get("status") == "done"):   # 8-23 판 실행: 판 몫 단계 뒤(반장 마무리 전)에서 멈춤
            ev(run, "stage", stage="S8", to="games_end", games=s["opts"]["games"])
            return {"phase": "games_end", "stage": "S8", "todo_all": [], "batch": []}
        stage, pk = r.pending()
        todo = [p for p in pk if not pa.answered(p)]
        if stage == "S7s" and todo and s["opts"].get("layout", "manager") == "game":   # 8-23: 판마다 판 LLM 하나(나란히) — 관리자 없음
            src_ = s["opts"].get("replay_sup_from") or s["opts"].get("replay_from")
            if src_:   # 재생 계획은 판 LLM 들이 나란히 돌기 전에 한 번에(그 뒤로는 읽기만)
                with PLAN_LOCK:
                    plan_ = ensure_plan(run, src_, [p["game"] for p in pk])
                    miss_ = [p["game"] for p in pk if p["game"] not in plan_["games"]]
                    if miss_:
                        for g_ in miss_:
                            plan_["games"][g_] = plan_game(pa.hcfg._p(src_) / "sup" / g_)
                        pa.wj(plan_file(run), plan_)
            ev(run, "stage", stage=stage, to="games", games=[p["game"] for p in todo])
            return {"phase": "games", "stage": stage, "todo_all": [], "batch": [p["game"] for p in todo], "retried": []}
        if stage == "S7s" and todo:
            ev(run, "stage", stage=stage, to="mgr", games=[p["game"] for p in todo])
            return {"phase": "mgr", "stage": stage, "todo_all": [], "batch": [], "retried": []}
        if todo:
            b = cut(todo, s["opts"])
            ev(run, "stage", stage=stage, to="work", todo=len(todo), sent=len(b))
            return {"phase": "work", "stage": stage, "todo_all": todo, "batch": b, "retried": []}
        key = (stage, tuple(p.get("id") for p in pk))
        if pk and key == last:
            same += 1
            if same >= prun.SAME_LIMIT:
                raise GraphError(f"답이 다 찬 꾸러미({stage} {len(pk)}개)로 next 를 {same}번 불러도 안 넘어감")
        else:
            same = 0
        last = key
        if until:   # until 앞 단계는 한 번에 한 단계씩(paifu_auto next 를 그 단계 뒤에서 끊는 감싸개 _next_upto — paifu_auto 는 안 고침)
            up = next(x for x in stages_before(run, until) if (r.state()["stages"].get(x) or {}).get("status") != "done")
            rc, txt, log = r.sub(f"next_{up}", [Path(__file__).resolve(), "_next_upto", "--run", rp(r.d), "--upto", up])
            if rc != 0:
                raise GraphError(f"paifu_auto next({up} 까지) 오류(rc {rc}) — {rp(log)}: {prun.tail(txt, 1500)}")
            if (r.state()["stages"].get(up) or {}).get("status") == "done":
                ev(run, "upto_stage", stage=up, until=until, s=(r.state().get("timing") or {}).get(up))
                if TEST.get("die_after_stage") == up and until == PREFIX_UNTIL:   # 시험: 공통 앞 단계 하나가 끝난 바로 뒤 죽음(재개 시험)
                    ev(run, "test_die", after_stage=up)
                    sys.stdout.flush()
                    os._exit(137)
            continue
        rc, txt, log = r.sub("next", [AUTO, "next", "--run", rp(r.d)])
        if rc != 0:
            raise GraphError(f"paifu_auto next 오류(rc {rc}) — {rp(log)}: {prun.tail(txt, 1500)}")
        stage, pk = r.pending()
        st = r.state()
        if not pk and s["opts"].get("games") and (st["stages"].get("S7s") or {}).get("status") == "done":   # 8-23 판 실행: next 가 S7s 뒤에서 멈춤
            ev(run, "stage", stage="S8", to="games_end", games=s["opts"]["games"])
            return {"phase": "games_end", "stage": "S8", "todo_all": [], "batch": []}
        if not pk and (st["stages"].get("S9") or {}).get("status") == "done":
            ev(run, "stage", stage="S9", to="confirm")
            return {"phase": "confirm", "stage": "S9", "todo_all": [], "batch": []}
        if not pk:
            raise GraphError("next 가 끝났는데 꾸러미도 없고 S9 도 안 끝남")
    raise GraphError(f"stage 한 번에 {prun.MAX_STEPS}걸음을 넘김")


def sends(s: GS) -> list:
    return [Send("work", {"pkg": p, "opts": s["opts"], "run": s["run"]}) for p in s["batch"]]


def r_stage(s: GS):
    if s["phase"] == "work":
        return sends(s)
    if s["phase"] == "games":
        return [Send("game", {"game": g, "opts": s["opts"], "run": s["run"]}) for g in s["batch"]]
    if s["phase"] in ("games_end", "until_end"):
        return END
    return "mgr_prep" if s["phase"] == "mgr" else "confirm"


# ------------------------------------------------------------------ 마디: work(꾸러미 하나를 손으로)
def fill_rec(run, p: dict, event: str, hand: str, conc: int, **kw):
    append(gdir(run) / "fills.jsonl", {"at": now(), "id": p["id"], "stage": p.get("stage"), "kind": pkg_view(p)["kind"], "game": p.get("game"),
                                       "turn": p.get("turn"), "event": event, "hand": hand, "conc": conc, "pid": os.getpid(), **kw})


def asked_flag(run, pid: str) -> Path:
    """session 손에 낸 꾸러미 표시 — 재개 때 답이 찬 것을 '그 손이 채움(filled)' 으로, 표시 없이 이미 찬 것은 'already' 로 가름."""
    return gdir(run) / "asked" / f"{pid}.flag"


def n_work(x: dict):
    if SLOT.get("units") and SLOT["sem"] is not None:   # 8-23 판 실행 나란히: 동시 수는 모든 판 실행이 같이 셈
        SLOT["sem"].acquire()
        try:
            return _n_work(x)
        finally:
            SLOT["sem"].release()
    return _n_work(x)


def _n_work(x: dict):
    p, opts, run = x["pkg"], x["opts"], x["run"]
    hand = eff_hand(opts, p.get("stage"), p)
    with LOCK:
        CONC["n"] += 1
        CONC["max"] = max(CONC["max"], CONC["n"])
        c = CONC["n"]
    try:
        if p.get("stage") == "S7s":
            raise GraphError(f"S7s 꾸러미가 손에 옴({p['id']}) — 판 supervisor 는 관리자 고리로만")
        mk = asked_flag(run, p["id"])
        if pa.answered(p) and not mk.exists():
            fill_rec(run, p, "already", hand, c)
            att = attempt_of(p)
            if att and not pr.turn_file(run, p["turn"], att).exists():   # 결과 파일이 없으면(옛 실행 · 끊김) 지금 답으로 씀
                record_result(run, p, hand, pkg_inp(run, p))
            return {"log": [{"id": p["id"], "event": "already"}], "max_conc": c}
        if opts.get("test_touch_task") and p["id"] in opts["test_touch_task"] and not (Path(p["dir"]) / ".touched").exists():   # 시험(8-23 끝 조건 6)
            tf = Path(p["task"])
            tf.write_bytes(tf.read_bytes() + b"\n")
            (Path(p["dir"]) / ".touched").write_text(now(), encoding="utf-8")
            ev(run, "test_touch_task", pkg=p["id"])
        inp = pkg_inp(run, p) if (opts.get("reuse_from") or attempt_of(p) or p.get("stage") in ("S1", "S4", "S6a")) else None
        hit = try_reuse_from(run, p, opts, inp) if opts.get("reuse_from") else None
        if hit:   # 8-23 캐시 대체 — 입력 sha 가 같은 결과를 베낌(돈 0)
            with FILL_LOCK:
                record_result(run, p, hand, inp, from_run=hit[0], orig_hand=hit[1], orig_usd=hit[2])
                fill_rec(run, p, "filled", "reuse", c, from_run=rp(hit[0]), orig_hand=hit[1])
            return {"log": [{"id": p["id"], "event": "filled"}], "max_conc": c}
        if hand == "api":   # 8-21: 꾸러미 하나를 Claude API(또는 가짜 클라이언트)로 — 답은 끝날 때 한 번에 넘어옴(paifu_apihand 사본)
            res = ah.fill_graph_pkg(run, p, opts, lambda: replay_text(run, p, opts))
            with FILL_LOCK:
                record_result(run, p, "api", inp, from_run=None, res=res)
                fill_rec(run, p, "filled", "api(reuse)" if res.get("reused_from") else "api", c, usd=res["usd"], calls=res["calls"],
                         **({"src": rp(res["reused_from"])} if res.get("reused_from") else {}))
                TEST["fills"] += 1
                if TEST["die_after"] and TEST["fills"] >= TEST["die_after"]:
                    ev(run, "test_die", after=TEST["fills"], pkg=p["id"])
                    sys.stdout.flush()
                    os._exit(137)
            return {"log": [{"id": p["id"], "event": "filled"}], "max_conc": c}
        how = replay_source(run, p, opts) if hand == "replay" and not mk.exists() else None
        if how is None:   # session 손 — 또는 replay 인데 옛 답이 없음: 꾸러미를 내고 멈춤(재개 때 이 마디가 처음부터 다시 돌면 interrupt 는 곧바로 돌아옴)
            mk.parent.mkdir(parents=True, exist_ok=True)
            mk.touch()
            interrupt({"why": "read", "pkg": pkg_view(p), "replay_miss": hand == "replay"})
            mk.unlink(missing_ok=True)
            if not pa.answered(p):
                fill_rec(run, p, "still_empty", hand, c)
                return {"log": [{"id": p["id"], "event": "still_empty"}], "max_conc": c}
            record_result(run, p, "session", pkg_inp(run, p) if (attempt_of(p) or p.get("stage") in ("S1", "S4", "S6a")) else None)
            fill_rec(run, p, "filled", "session" if hand == "session" else "session(replay 빈 곳)", c)
            return {"log": [{"id": p["id"], "event": "filled"}], "max_conc": c}
        if TEST["hand_delay"]:
            time.sleep(TEST["hand_delay"])
        with FILL_LOCK:
            put_answer(p, how)
            record_result(run, p, "replay", inp)
            fill_rec(run, p, "filled", "replay", c, src=rp(how[1]) if how[0] == "copy" else "write")
            TEST["fills"] += 1
            if TEST["die_after"] and TEST["fills"] >= TEST["die_after"]:
                ev(run, "test_die", after=TEST["fills"], pkg=p["id"])
                sys.stdout.flush()
                os._exit(137)
        return {"log": [{"id": p["id"], "event": "filled"}], "max_conc": c}
    finally:
        with LOCK:
            CONC["n"] -= 1


# ------------------------------------------------------------------ 마디: join(답 꼴 검사 · 한 번 다시 냄 · 다음 묶음)
def n_join(s: GS):
    run = s["run"]
    retried = list(s.get("retried") or [])
    for p in s.get("batch") or []:
        if not pa.answered(p) or not is_turn_pkg(p):
            continue
        why = pa.answer_form_error(pa.jl(p["answer"]))
        if not why:
            continue
        if p["id"] not in retried:
            f = Path(p["answer"])
            k = 1
            while f.with_name(f"answer_badform_{k}.json").exists():
                k += 1
            shutil.move(str(f), str(f.with_name(f"answer_badform_{k}.json")))
            retried.append(p["id"])
            fill_rec(run, p, "badform_retry", s["opts"]["hands"], 0, why=why)
        else:
            fill_rec(run, p, "badform_kept", s["opts"]["hands"], 0, why=why)
    remaining = [p for p in s.get("todo_all") or [] if not pa.answered(p)]
    if remaining:
        b = cut(remaining, s["opts"])
        ev(run, "join", resend=len(b), remaining=len(remaining))
        return {"retried": retried, "batch": b, "join_next": "work"}
    return {"retried": retried, "batch": [], "join_next": "stage" if s["phase"] == "work" else "mgr_close"}


def r_join(s: GS):
    return sends(s) if s["join_next"] == "work" else s["join_next"]


# ------------------------------------------------------------------ 관리자 고리
def mgr_d(run) -> Path:
    return Path(run) / "mgr"


def round_d(run, n: int) -> Path:
    return mgr_d(run) / f"round_{n}"


def init_mgr(run) -> dict:
    r = runner(run)
    stage, pk = r.pending()
    games = {}
    for p in pk:
        if p.get("stage") != "S7s":
            continue
        games[p["game"]] = {"status": "done" if pa.answered(p) else "open", "pack": p["dir"], "rounds": 0, "notes": [], "closed_by": None, "checks": 0}
    m = {"round": 1, "games": games, "rounds": [], "form_retry": {}, "cur": None, "closed_by_limit": []}
    ev(run, "mgr_init", games=list(games))
    return m


def applied_keys(run, n: int) -> dict:
    return {x["key"]: x for x in log_lines(round_d(run, n) / "applied.jsonl")}


def sup_cmd(run, n: int, key: str, what: str, args: list) -> dict:
    """paifu_sup 명령 하나(라운드 기록으로 재개 때 두 번 안 부름) — {"rc", "out", "log"}."""
    done = applied_keys(run, n)
    if key in done:
        return done[key]
    rc, txt, log = sub(run, what, [SUP, *args])
    o = {"key": key, "at": now(), "what": what, "rc": rc, "out": (txt or "").strip()[-2500:], "log": rp(log)}
    append(round_d(run, n) / "applied.jsonl", o)
    if rc not in (0, 2):
        raise GraphError(f"paifu_sup {what} 오류(rc {rc}) — {rp(log)}: {prun.tail(txt, 800)}")
    return o


def reject_text(o: dict) -> str:
    m = re.search(r"거절: (.*)", o.get("out") or "", re.S)
    return (m.group(1) if m else o.get("out") or "").strip()[:1500]


TASK_MGR = """# 반장 관리자 — 라운드 @N@ / @MAX@ (`@RUN@`)

## 1. 하는 일
이 반장의 아직 마감 안 된 판마다, 차례 답들 가운데 틀렸을 수 있는 것을 가려서 무엇을 할지 정한다 — 다시 읽기(`reread`) · 고르기(`take`) · 사용자 질문(`ask`) · 확정(`accept`).
정한 것은 결정 파일 하나(`@DEC@`)에만 쓴다. 명령 실행 · 다시 읽기 작업자 띄우기 · 복원 검사(check)는 코드가 한다. 차례를 처음부터 다시 다 읽지 않는다.

## 2. 읽을 것(읽기만)
- 이번 라운드 요약: `@SUM@` — 판마다 절이 나뉘어 있다(판 상태 · 마지막 검사 · 앞 라운드에서 거절된 것 · 판 요약 · 매 순 손패).
- 판마다 더 볼 것: 그 판 꾸러미의 `game.md` · `hands.md` · `turns/<차례>/answer.json`(처음 답 — kind · k · j · end_order · unsure · p · events_used · why),
  다시 읽기 답 `reread/<차례>_r<n>/answer.json`, 검사 보고 `try/<n>/report.md`. 꾸러미 폴더:
@PACKS@

## 3. 결정 꼴(`decision.json` — JSON 하나)
```json
{"games": {"<판>": [{"do": "reread", "turn": "<차례>", "frames": "053-058" , "why": "<글>"},
                    {"do": "take", "turn": "<차례>", "from": "first|r1|r2", "why": "<글>"},
                    {"do": "ask", "turn": "<차례>", "candidates": "<후보>", "why": "<글>"},
                    {"do": "accept", "why": "<글>"}]},
 "note": "<라운드 전체 한 줄>"}
```
- `reread`: 그 차례를 독립으로 다시 읽힌다. `frames` 는 더 볼 프레임 번호 범위(예 `"053-058"` · `"053-058,060-068"`, 3개까지) 또는 `null`. 작업자에게는 이 범위만 간다(앞 답 · 칸 번호 · 패는 안 감).
- `take`: 그 차례 초안을 처음 답(`first`) 또는 답이 온 다시 읽기(`r1` · `r2`)로 고른다.
- `ask`: 사용자 질문 한 줄(후보 · 까닭).
- `accept`: 그 판 확정. 같은 판에 이번 라운드 `reread` 가 있으면 accept 는 실행하지 않는다 — 다시 읽기 답을 본 다음 라운드에 다시 accept 한다.
- 결정이 없는 판은 이번 라운드에 아무것도 하지 않는다. 판 하나의 결정은 적힌 차례대로 실행되고 accept 는 맨 뒤에 한다.
- 프레임을 보고 답을 직접 정하는 일(set)은 없다. 다시 읽기가 처음 답과 갈리면 셋째 읽기(`frames` 를 준 `reread`)로 둘 이상이 같게 하거나 `ask`.

## 4. 한도
- 라운드 @MAX@번. 이번이 @N@째. 마지막 라운드 뒤에도 마감 안 된 판은 코드가 아래 마감 검사 ① 대상 차례를 모두 질문으로 올리고 닫는다.
- 다시 읽기: 판마다 ⌈읽은 차례 수 ÷ 2⌉개 · 차례당 2번(요약의 판 상태 줄). 넘으면 명령이 거절하고 그 글이 다음 요약에 들어간다 — 남은 의심 차례는 `ask` 로.
- 복원 검사(check)는 판마다 @CHECK@번까지 — 코드가 손댄 판에 라운드마다 부른다.

## 5. accept 할 때 코드가 보는 것(마감 검사)
① 처음 답이 `unsure: true` 이거나 @P_COND@판 요약의 "창 흔들림" 차례는 다시 읽기 · 질문 가운데 하나를 거쳐야 한다.
② 초안이 처음 답과 다른 차례가 있으면, 지금 초안 그대로 돈 마지막 검사가 통과해야 한다. 통과 못 했으면 그 차례들을 모두 `ask` 로 — 그러면 처음 답으로 반영되고 초안은 질문 줄에 남는다.
③ 답이 안 온 다시 읽기가 없어야 한다.
④ 한도 안.
⑤ 다시 읽기 답이 초안과 다른 차례는 `ask` 가 있거나, 초안이 독립 읽기(처음 답 + 다시 읽기들) 가운데 둘 이상과 같아야 한다.
거절되면 그 까닭이 다음 라운드 요약의 "앞 라운드에서 거절된 것" 에 들어간다.

@JUDGE@
## 8. 지킬 것
- 프레임 · 영상 · 다른 실행 폴더 · 정답 · 사용자 확인값 · 옛 손 설정 · 메모를 열지 않는다. 위 2 의 파일만 읽는다.
- 에이전트를 띄우지 않는다. `paifu_sup.py` 를 직접 부르지 않는다 — 결정은 파일로만.
- 판끼리 섞지 않는다 — 한 판의 결정은 그 판 절과 그 판 꾸러미만 보고 정한다.
- 답은 `@DEC@` 한 파일만 쓴다.
"""


def low_p_acts() -> bool:
    """설계서 8-22: 낮은 p 가 판단(마감 검사 ① · 한도로 닫을 때 질문 대상)에 끼나 — paifu_auto.LOW_P_ACTS, 없으면 False(낮은 p 는 기록만)."""
    return bool(getattr(pa, "LOW_P_ACTS", False))


def judge_text() -> str:
    """판 supervisor 지시문(8-10, paifu_sup.TASK_TMPL)의 판단 기준 — 3 은 그대로, 4 는 set(프레임 보고 근거 적기) 줄을 빼고 고침."""
    import paifu_sup as ps
    t = ps.TASK_TMPL
    a, b = t.index("## 3. 의심으로 볼 것"), t.index("## 4. 풀었다고 볼 때")
    s3 = t[a:b].replace("## 3.", "## 6.").replace("@P_LOW@", str(ps.P_LOW))
    s4 = ("## 7. 풀었다고 볼 때\n독립 다시 읽기가 처음 답과 같음, 또는 독립 읽기(처음 답 + 다시 읽기들) 가운데 둘 이상이 같음. 둘 다 아니면 `ask`.\n\n")
    return s3 + s4


def last_check(pack: Path) -> str:
    dr = pa.jl(pack / "draft.json")
    if not dr.get("checks"):
        return "- 아직 없음"
    c = dr["checks"][-1]
    f = Path(c.get("report") or "")
    if not f.exists():
        return f"- check {c.get('n')}: {'통과' if c.get('passed') else '통과 못 함'}"
    L = f.read_text(encoding="utf-8").split("\n")
    head = [x for x in L[:6] if x.strip()]
    rows = []
    for x in L[6:]:
        if not x.startswith("  - "):
            if rows:
                break
            continue
        rows.append(x)
    return "\n".join(head + rows)


def n_mgr_prep(s: GS):
    run = s["run"]
    m = s.get("mgr") or init_mgr(run)
    for g, v in m["games"].items():   # 재개 때 이미 마감된 판
        if v["status"] == "open" and (Path(v["pack"]) / "decision.json").exists():
            v["status"] = "done"
    n = m["round"]
    d = round_d(run, n)
    d.mkdir(parents=True, exist_ok=True)
    open_g = [g for g, v in m["games"].items() if v["status"] == "open"]
    S = [f"# 관리자 라운드 {n} 요약 — `{Path(run).name}`", "",
         f"- 마감 안 된 판 {len(open_g)}개: {', '.join(open_g)}" + (f" · 마감된 판: {', '.join(g for g, v in m['games'].items() if v['status'] != 'open')}" if len(open_g) < len(m["games"]) else ""),
         f"- 라운드 한도 {MAX_ROUNDS} · 결정 파일 `{(d / 'decision.json').as_posix()}`", ""]
    for g in open_g:
        v = m["games"][g]
        pack = Path(v["pack"])
        o = sup_cmd(run, n, f"status:{g}", f"mgr_status_{g}", ["status", "--pack", pack.as_posix()])
        S += [f"## 판 `{g}`", "", f"꾸러미: `{pack.as_posix()}`", "", "### 판 상태(코드)", "", "```", o["out"], "```", "",
              "### 마지막 검사", "", last_check(pack), "", "### 앞 라운드에서 거절된 것", ""]
        S += [f"- {x}" for x in v["notes"]] or ["- 없음"]
        S += ["", "### 판 요약(game.md)", "", (pack / "game.md").read_text(encoding="utf-8").strip(), "",
              "### 매 순 손패(hands.md)", "", (pack / "hands.md").read_text(encoding="utf-8").strip(), ""]
    summary = "\n".join(S) + "\n"
    pa.wt(d / "summary.md", summary)
    import paifu_sup as ps
    packs = "\n".join(f"  - `{g}`: `{Path(m['games'][g]['pack']).as_posix()}`" for g in open_g)
    task = (TASK_MGR.replace("@N@", str(n)).replace("@MAX@", str(MAX_ROUNDS)).replace("@RUN@", Path(run).name)
            .replace("@DEC@", (d / "decision.json").as_posix()).replace("@SUM@", (d / "summary.md").as_posix()).replace("@PACKS@", packs)
            .replace("@CHECK@", str(ps.CHECK_PER_GAME)).replace("@P_COND@", f"`p` 가 {ps.P_LOW} 밑이거나 " if low_p_acts() else "").replace("@P_LOW@", str(ps.P_LOW)).replace("@JUDGE@", judge_text()))
    pa.wt(d / "TASK.md", task)
    row = {"n": n, "games": open_g, "summary": rp(d / "summary.md"), "task": rp(d / "TASK.md"), "decision": rp(d / "decision.json"),
           "summary_chars": len(summary), "summary_tokens_est": tok_est(summary), "task_chars": len(task), "task_tokens_est": tok_est(task)}
    m["rounds"] = [x for x in m["rounds"] if x["n"] != n] + [row]
    ev(run, "mgr_prep", round=n, games=open_g, chars=len(summary), tokens_est=row["summary_tokens_est"])
    return {"mgr": m}


def n_manager(s: GS):
    run, opts, m = s["run"], s["opts"], s["mgr"]
    n = m["round"]
    d = round_d(run, n)
    dec = d / "decision.json"
    pk = {"id": f"mgr_r{n}", "kind": "manager", "stage": "manager", "task": (d / "TASK.md").as_posix(), "answer": dec.as_posix(), "dir": d.as_posix()}
    mk = asked_flag(run, pk["id"])
    if pa.answered(pk) and not mk.exists():
        fill_rec(run, pk, "already", eff_hand(opts, "manager"), 0)
        return {}
    if eff_hand(opts, "manager") == "api":
        open_g = [g for g in m["rounds"][-1]["games"]]
        res = ah.fill_graph_pkg(run, pk, opts, lambda: json.dumps(replay_decision(run, n, open_g, opts), ensure_ascii=False, indent=1))
        fill_rec(run, pk, "filled", "api(reuse)" if res.get("reused_from") else "api", 0, usd=res["usd"], calls=res["calls"])
        return {}
    if eff_hand(opts, "manager") == "replay":
        open_g = [g for g in m["rounds"][-1]["games"]]
        pa.wj(dec, replay_decision(run, n, open_g, opts))
        fill_rec(run, pk, "filled", "replay", 0)
        return {}
    mk.parent.mkdir(parents=True, exist_ok=True)
    mk.touch()
    interrupt({"why": "read", "pkg": pk})
    mk.unlink(missing_ok=True)
    fill_rec(run, pk, "filled" if pa.answered(pk) else "still_empty", "session", 0)
    return {}


def r_manager(s: GS):
    return "mgr_apply" if (round_d(s["run"], s["mgr"]["round"]) / "decision.json").exists() else "manager"


def decision_errors(d, open_g: list, m: dict) -> list:
    """결정 꼴 검사. replay_set(옛 set 재생)은 재생 계획이 만든 결정("replay": true)에서만 받는다 — 관리자 결정에는 set 이 없음."""
    if not isinstance(d, dict) or not isinstance(d.get("games"), dict):
        return ["games 칸(판 → 결정 목록)이 없음"]
    replay = d.get("replay") is True
    errs = []
    for g, acts in d["games"].items():
        if g not in m["games"]:
            errs.append(f"{g}: 이 반장의 판이 아님")
            continue
        if not isinstance(acts, list):
            errs.append(f"{g}: 결정이 목록이 아님")
            continue
        turns = set(pa.jl(Path(m["games"][g]["pack"]) / "pack.json")["turns"])
        for i, a in enumerate(acts):
            do = a.get("do") if isinstance(a, dict) else None
            if do not in MGR_DO or (do == "replay_set" and not replay):
                errs.append(f"{g}[{i}]: do {do!r}(reread · take · ask · accept 만)")
                continue
            if do != "accept" and a.get("turn") not in turns:
                errs.append(f"{g}[{i}]: turn {a.get('turn')!r} 가 이 판의 읽은 차례가 아님")
            if do == "take" and a.get("from") not in TAKE_FROM:
                errs.append(f"{g}[{i}]: from {a.get('from')!r}")
            if do == "reread" and a.get("frames") is not None and not isinstance(a.get("frames"), str):
                errs.append(f"{g}[{i}]: frames 는 글 또는 null")
            if do == "ask" and not str(a.get("candidates") or "").strip():
                errs.append(f"{g}[{i}]: candidates 가 비었음")
    return errs


def n_mgr_apply(s: GS):
    run, opts = s["run"], s["opts"]
    m = s["mgr"]
    n = m["round"]
    d = round_d(run, n)
    open_g = [g for g, v in m["games"].items() if v["status"] == "open"]
    try:
        dec = pa.jl(d / "decision.json")
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        dec = None
        errs = [f"JSON 아님: {e}"]
    else:
        errs = decision_errors(dec, open_g, m)
    if errs:
        k = str(n)
        if not m["form_retry"].get(k):
            m["form_retry"][k] = 1
            shutil.move(str(d / "decision.json"), str(d / "decision_bad_1.json"))
            pa.wt(d / "decision_bad_1.why.txt", "\n".join(errs) + "\n")
            ev(run, "mgr_form_retry", round=n, errors=errs)
            return {"mgr": m, "mgr_next": "manager"}
        ev(run, "mgr_form_fail", round=n, errors=errs)
        m["cur"] = {"touched": [], "accept": [], "rereads": [], "force": open_g, "why_force": "결정 꼴이 두 번 틀림"}
        return {"mgr": m, "mgr_next": "mgr_close"}
    touched, accept, rereads, acted = [], [], [], []
    for g in open_g:
        acts = (dec["games"].get(g) or [])
        if acts:
            acted.append(g)
        pack = Path(m["games"][g]["pack"])
        sc = pack / "scratch"
        rr_here = False
        for i, a in enumerate(acts):
            do, t = a["do"], a.get("turn")
            key = f"{g}#{i}:{do}:{t or ''}"
            if do == "accept":
                continue
            if do == "reread":
                o = sup_cmd(run, n, key, f"mgr_reread_{g}", ["reread", "--pack", pack.as_posix(), "--turn", t, *(["--frames", a["frames"]] if a.get("frames") else [])])
                if o["rc"] == 0:   # paifu_sup reread 가 찍은 "→ <폴더>"(재개 때도 같은 줄 — 한 차례를 한 라운드에 두 번 읽혀도 어긋나지 않게)
                    mm = re.search(r"→ (\S+_r(\d+))\s", o["out"] + "\n")
                    if not mm:
                        raise GraphError(f"reread 출력에서 폴더를 못 찾음: {o['out'][:300]}")
                    dd, k_ = Path(mm.group(1)), int(mm.group(2))
                    rereads.append(pa.pkg("sup_reread", f"rr_{t}_r{k_}", dd, dd / "TASK.md", dd / "answer.json", game=g, turn=t, reread=k_, kind="reread"))
                    rr_here = True
            elif do == "take":
                o = sup_cmd(run, n, key, f"mgr_take_{g}", ["take", "--pack", pack.as_posix(), "--turn", t, "--from", a["from"]])
            elif do == "ask":
                cf, wf = sc / f"mgr_r{n}_{i}_ask_candidates.txt", sc / f"mgr_r{n}_{i}_ask_why.txt"
                pa.wt(cf, str(a.get("candidates") or ""))
                pa.wt(wf, str(a.get("why") or ""))
                o = sup_cmd(run, n, key, f"mgr_ask_{g}", ["ask", "--pack", pack.as_posix(), "--turn", t, "--candidates-file", cf.as_posix(), "--why-file", wf.as_posix()])
            elif do == "replay_set":   # 재생에서만(표시 replay_set) — 관리자 결정에는 set 이 없음
                af, ef, wf = sc / f"mgr_r{n}_{i}_set_answer.json", sc / f"mgr_r{n}_{i}_set_evidence.txt", sc / f"mgr_r{n}_{i}_set_why.txt"
                pa.wj(af, a["answer"])
                pa.wt(ef, str(a.get("evidence") or ""))
                pa.wt(wf, str(a.get("why") or ""))
                o = sup_cmd(run, n, key, f"mgr_set_{g}", ["set", "--pack", pack.as_posix(), "--turn", t, "--answer", af.as_posix(),
                                                         "--evidence-file", ef.as_posix(), "--why-file", wf.as_posix()])
            if o["rc"] == 2:
                m["games"][g]["notes"].append(f"라운드 {n} {do} {t}: 거절 — {reject_text(o)}")
            elif do in ("reread", "take", "replay_set") and g not in touched:
                touched.append(g)
        if any(a["do"] == "accept" for a in acts):
            if rr_here:
                m["games"][g]["notes"].append(f"라운드 {n}: accept 를 미룸 — 같은 라운드에 다시 읽기가 있어 그 답을 본 다음 라운드에 다시 accept 할 것")
            else:
                accept.append(g)
    for g in acted:
        m["games"][g]["rounds"] += 1
    m["cur"] = {"touched": touched, "accept": accept, "rereads": [p["id"] for p in rereads], "force": [], "acted": acted}
    ev(run, "mgr_apply", round=n, acted=acted, touched=touched, accept=accept, rereads=len(rereads))
    if rereads:
        return {"mgr": m, "phase": "mgr_work", "todo_all": rereads, "batch": cut(rereads, opts), "retried": [], "mgr_next": "work"}
    return {"mgr": m, "mgr_next": "mgr_close"}


def r_mgr_apply(s: GS):
    return sends(s) if s["mgr_next"] == "work" else s["mgr_next"]


def force_close(run, n: int, g: str, m: dict, why: str):
    """라운드 한도 · 결정 꼴 두 번 틀림: 마감 검사 ① 대상 차례를 모두 ask 로 올리고 done. 거절 글에 차례가 나오면 그 차례도 ask 로(세 번까지)."""
    v = m["games"][g]
    pack = Path(v["pack"])
    meta = pa.jl(pack / "pack.json")
    tgt = list(meta.get("unsure_first") or []) + ([t for t in meta.get("low_p_first") or [] if t not in (meta.get("unsure_first") or [])] if low_p_acts() else [])
    tgt += [t for t in meta["turns"] if t in (meta.get("window_shift") or {}) and t not in tgt]
    sc = pack / "scratch"
    asked = {q["turn"] for q in pa.jl(pack / "draft.json")["asks"]}
    tries = []
    for k in range(3):
        for t in [t for t in tgt if t not in asked]:
            cf, wf = sc / f"mgr_limit_{t}_candidates.txt", sc / f"mgr_limit_{t}_why.txt"
            pa.wt(cf, "지금 초안 · 처음 답 · 다시 읽기 답 가운데(관리자가 풀지 못함)")
            pa.wt(wf, f"{why} — 관리자 라운드 {n} 뒤에도 마감 안 됨, 마감 검사 대상 차례를 코드가 질문으로 올림")
            sup_cmd(run, n, f"force:{g}:ask:{t}", f"mgr_force_ask_{g}", ["ask", "--pack", pack.as_posix(), "--turn", t, "--candidates-file", cf.as_posix(), "--why-file", wf.as_posix()])
            asked.add(t)
        o = sup_cmd(run, n, f"force:{g}:done:{k}", f"mgr_force_done_{g}", ["done", "--pack", pack.as_posix()])
        tries.append(o["rc"])
        if o["rc"] == 0:
            v.update(status="limit", closed_by=why)
            m["closed_by_limit"].append({"game": g, "round": n, "why": why, "asked": sorted(asked)})
            return
        tgt = [t for t in meta["turns"] if re.search(rf"\b{re.escape(t)}\b", reject_text(o))]
        if not [t for t in tgt if t not in asked]:
            break
    raise GraphError(f"{g}: 한도로 닫기 실패(done 거절 {tries}) — {reject_text(o)}")


def n_mgr_close(s: GS):
    run = s["run"]
    m = s["mgr"]
    n = m["round"]
    cur = m.get("cur") or {"touched": [], "accept": [], "force": []}
    for g in cur["touched"]:
        o = sup_cmd(run, n, f"close:{g}:check", f"mgr_check_{g}", ["check", "--pack", m["games"][g]["pack"]])
        m["games"][g]["checks"] += 1 if o["rc"] == 0 else 0
        if o["rc"] == 2:
            m["games"][g]["notes"].append(f"라운드 {n} check: 거절 — {reject_text(o)}")
    for g in cur["accept"]:
        o = sup_cmd(run, n, f"close:{g}:done", f"mgr_done_{g}", ["done", "--pack", m["games"][g]["pack"]])
        if o["rc"] == 0:
            m["games"][g]["status"] = "done"
        else:
            m["games"][g]["notes"].append(f"라운드 {n} accept: 마감 거절 — {reject_text(o)}")
    for g in cur.get("force") or []:
        force_close(run, n, g, m, cur.get("why_force") or "결정 꼴")
    open_g = [g for g, v in m["games"].items() if v["status"] == "open"]
    if open_g and n >= MAX_ROUNDS:
        for g in open_g:
            force_close(run, n, g, m, f"라운드 한도 {MAX_ROUNDS}")
        open_g = []
    m["cur"] = None
    ev(run, "mgr_close", round=n, open=open_g, status={g: v["status"] for g, v in m["games"].items()})
    if open_g:
        m["round"] = n + 1
        return {"mgr": m, "mgr_next": "mgr_prep", "phase": "mgr"}
    pa.wj(mgr_d(run) / "report.json", {"_note": "paifu_graph.py 관리자 고리 결과", "at": now(), "rounds": m["rounds"],
                                       "games": {g: {k: v[k] for k in ("status", "rounds", "checks", "closed_by", "notes")} for g, v in m["games"].items()},
                                       "closed_by_limit": m["closed_by_limit"]})
    return {"mgr": m, "mgr_next": "stage", "phase": "stage"}


def r_mgr_close(s: GS):
    return s["mgr_next"]


# ------------------------------------------------------------------ game 꼴(설계서 8-23): 판마다 판 LLM 하나(지휘자) — 관리자 없음
class Slot:
    """판 LLM · 다시 읽기 순 호출이 함께 쓰는 동시 자리(max_concurrency 개). 잡으면 CONC 를 셈."""

    def __enter__(self):
        if SLOT["sem"] is not None:
            SLOT["sem"].acquire()
        with LOCK:
            CONC["n"] += 1
            CONC["max"] = max(CONC["max"], CONC["n"])
            self.c = CONC["n"]
        return self

    def __exit__(self, *a):
        with LOCK:
            CONC["n"] -= 1
        if SLOT["sem"] is not None:
            SLOT["sem"].release()
        return False


def game_hand(opts: dict, g: str) -> str:
    h = eff_hand(opts, "game", {"game": g, "stage": "game"})
    return h


def game_task_text(g: str, pack: Path) -> str:
    import paifu_sup as ps
    meta = pa.jl(pack / "pack.json")
    lim = meta["limits"]
    t = GAME_TASK.read_text(encoding="utf-8")
    return (t.replace("@GAME@", g).replace("@RR_GAME@", str(lim["reread_game"])).replace("@RR_TURN@", str(lim["reread_turn"]))
            .replace("@CHECK@", str(lim["check"])).replace("@TOOL_MAX@", str(ah.GAME_TOOL_MAX))
            .replace("@P_LINE@", f"- 답의 `p`(읽기가 스스로 적은 맞을 가능성)가 {ps.P_LOW} 밑\n" if low_p_acts() else "")
            .replace("@P_COND@", f"`p` 가 {ps.P_LOW} 밑이거나 " if low_p_acts() else ""))


def game_first_message(run, g: str, pack: Path) -> str:
    draft = pr.build_game(run, g, "draft", None)
    body = json.dumps(pr.strip_meta(draft), ensure_ascii=False, indent=1)
    return game_task_text(g, pack) + "\n## 판 결과 파일 초안\n\n```json\n" + body + "\n```\n"


def game_reread_text(run, p: dict, opts: dict):
    """판 다시 읽기 꾸러미의 재생 · 가짜 답 글: 재생 계획(옛 판 supervisor 다시 읽기 답) → 없으면 가짜 손만 그 차례 처음 답(rr=alt 면 다른 후보로 바꾼 답)."""
    fo = ah.parse_fake(opts.get("api_fake") or "replay") if opts.get("api_fake") else {}
    if not fo.get("rr_alt") and not fo.get("rr_first"):
        t = replay_text(run, p, opts)
        if t is not None:
            return t
    if not opts.get("api_fake"):
        return None
    first = pa.jl(Path(run) / "sup" / p["game"] / "turns" / p["turn"] / "answer.json")
    if fo.get("rr_alt"):
        n = len([x for x in first.get("end_order") or [] if x != "D"]) + 1
        for kj, v in pa.alt_candidates(first, n)[0]:
            va = pa.variant_answer(first, kj, v)
            if va is not None:
                return json.dumps(va, ensure_ascii=False, indent=1)
    return json.dumps(first, ensure_ascii=False, indent=1)


class GameRun:
    """판 하나의 판 LLM 도구 실행기(그래프 코드). 판 LLM(api 손) · 재생 손이 같은 도구 함수를 부른다."""

    def __init__(self, run, g: str, opts: dict):
        self.run, self.g, self.opts = Path(run), g, opts
        self.pack = self.run / "sup" / g
        self.adir = self.run / "agent" / g
        self.meta = pa.jl(self.pack / "pack.json")
        self.turns = list(self.meta["turns"])
        st = pa.jl(self.adir / "state.json") if (self.adir / "state.json").exists() else {}
        self.actions = st.get("actions") or []
        self.refused = st.get("finish_refused") or []
        self.report = st.get("report")
        self.finished = (self.pack / "decision.json").exists()

    def save(self, **kw):
        pa.wj(self.adir / "state.json", {"game": self.g, "actions": self.actions, "finish_refused": self.refused, "report": self.report, **kw})

    def sup(self, key: str, what: str, args: list) -> dict:
        f = self.adir / "applied.jsonl"
        done = {x["key"]: x for x in log_lines(f)}
        if key in done:
            return done[key]
        rc, txt, log = self.sub(what, [SUP, *args])
        o = {"key": key, "at": now(), "what": what, "rc": rc, "out": (txt or "").strip()[-4000:], "log": rp(log)}
        append(f, o)
        if rc not in (0, 2):
            raise GraphError(f"paifu_sup {what} 오류(rc {rc}) — {rp(log)}: {prun.tail(txt, 800)}")
        return o

    def sub(self, what: str, args: list) -> tuple:
        """하위 프로세스 — 판마다 따로 기록(<실행>/logs/game_<판>/<번호>_<what>.log). runner.json 은 안 건드림(판 LLM 이 나란히 돌면 runner.json 을 같이 고쳐 깨짐)."""
        d = self.run / "logs" / f"game_{self.g}"
        d.mkdir(parents=True, exist_ok=True)
        n = len(list(d.glob("*.log"))) + 1
        log = d / f"{n:03d}_{what}.log"
        t0 = time.time()
        p = subprocess.run([PY, "-X", "utf8", *[str(x) for x in args]], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        pa.wt(log, " ".join(str(x) for x in args) + f"\n# rc {p.returncode} · {time.time() - t0:.1f}s\n" + p.stdout + ("\n--- stderr\n" + p.stderr if p.stderr else ""))
        return p.returncode, p.stdout + ("\n" + p.stderr if p.stderr else ""), log

    def act(self, a: dict):
        if not any(x.get("key") == a.get("key") for x in self.actions):
            self.actions.append(a)
            self.save()

    # --- 도구
    def t_read_game(self, a, key):
        doc = pr.build_game(self.run, self.g, "draft" if not self.finished else None, None)
        dr = pa.jl(self.pack / "draft.json")
        last = (dr.get("checks") or [None])[-1]
        rep = Path(last["report"]).read_text(encoding="utf-8") if last and Path(last.get("report") or "").exists() else "(아직 check 없음)"
        return ("## 판 결과 파일(지금)\n```json\n" + json.dumps(pr.strip_meta(doc), ensure_ascii=False, indent=1) + "\n```\n\n## game.md\n"
                + (self.pack / "game.md").read_text(encoding="utf-8") + "\n## hands.md\n" + (self.pack / "hands.md").read_text(encoding="utf-8")
                + "\n## 마지막 검사\n" + rep), False

    def t_read_turn(self, a, key):
        t = str(a.get("turn") or "")
        if t not in self.turns:
            return f"이 판의 차례가 아님: {t!r} — 이 판 차례: {', '.join(self.turns)}", True
        out = []
        for at in pr.turn_attempts(self.run, t):
            out.append(pr.strip_meta(pr.jl(pr.turn_file(self.run, t, at))))
        return json.dumps(out, ensure_ascii=False, indent=1), False

    def t_take(self, a, key):
        t = str(a.get("turn") or "")
        if t not in self.turns:
            return f"이 판의 차례가 아님: {t!r}", True
        o = self.sup(key, "game_take", ["take", "--pack", self.pack.as_posix(), "--turn", t, "--from", str(a.get("from"))])
        if o["rc"] == 0:
            self.act({"key": key, "do": "take", "turn": t, "from": a.get("from"), "why": a.get("why") or ""})
        return o["out"], o["rc"] != 0

    def t_ask(self, a, key):
        t = str(a.get("turn") or "")
        if t not in self.turns:
            return f"이 판의 차례가 아님: {t!r}", True
        sc = self.pack / "scratch"
        cf, wf = sc / f"game_{key}_ask_candidates.txt", sc / f"game_{key}_ask_why.txt"
        pa.wt(cf, str(a.get("candidates") or ""))
        pa.wt(wf, str(a.get("why") or ""))
        o = self.sup(key, "game_ask", ["ask", "--pack", self.pack.as_posix(), "--turn", t, "--candidates-file", cf.as_posix(), "--why-file", wf.as_posix()])
        if o["rc"] == 0:
            self.act({"key": key, "do": "ask", "turn": t, "candidates": a.get("candidates"), "why": a.get("why") or ""})
        return o["out"], o["rc"] != 0

    def t_set(self, a, key):   # 재생 손만(옛 set — 판 LLM 도구에는 없음)
        sc = self.pack / "scratch"
        af, ef, wf = sc / f"game_{key}_set_answer.json", sc / f"game_{key}_set_evidence.txt", sc / f"game_{key}_set_why.txt"
        pa.wj(af, a["answer"])
        pa.wt(ef, str(a.get("evidence") or ""))
        pa.wt(wf, str(a.get("why") or ""))
        o = self.sup(key, "game_set", ["set", "--pack", self.pack.as_posix(), "--turn", a["turn"], "--answer", af.as_posix(), "--evidence-file", ef.as_posix(),
                                       "--why-file", wf.as_posix()])
        if o["rc"] == 0:
            self.act({"key": key, "do": "set", "turn": a["turn"], "why": a.get("why") or ""})
        return o["out"], o["rc"] != 0

    def t_check(self, a, key):
        o = self.sup(key, "game_check", ["check", "--pack", self.pack.as_posix()])
        return o["out"], o["rc"] != 0

    def t_finish(self, a, key):
        if self.finished:
            return "이미 마감함", True
        o = self.sup(key, "game_done", ["done", "--pack", self.pack.as_posix()])
        if o["rc"] == 0:
            self.finished = True
            self.report = str(a.get("report") or "")
            self.save()
            return o["out"], False
        txt = reject_text(o)
        if txt not in self.refused:
            self.refused.append(txt)
            self.save()
        return "거절: " + txt, True

    def reread_make(self, a, key):
        """paifu_sup reread → 다시 읽기 꾸러미(채우기 전). (꾸러미, None) 또는 (None, (글, True))."""
        t = str(a.get("turn") or "")
        if t not in self.turns:
            return None, (f"이 판의 차례가 아님: {t!r}", True)
        fr = a.get("frames")
        o = self.sup(key, "game_reread", ["reread", "--pack", self.pack.as_posix(), "--turn", t, *(["--frames", fr] if fr else [])])
        if o["rc"] != 0:
            return None, (o["out"], True)
        mm = re.search(r"→ (\S+_r(\d+))\s", o["out"] + "\n")
        if not mm:
            raise GraphError(f"reread 출력에서 폴더를 못 찾음: {o['out'][:300]}")
        dd, k_ = Path(mm.group(1)), int(mm.group(2))
        p = pa.pkg("sup_reread", f"rr_{t}_r{k_}", dd, dd / "TASK.md", dd / "answer.json", game=self.g, turn=t, reread=k_, kind="reread")
        self.act({"key": key, "do": "reread", "turn": t, "frames": fr, "why": a.get("why") or "", "attempt": f"r{k_}"})
        return p, None

    def reread_fill(self, p: dict) -> tuple:
        """다시 읽기 꾸러미 하나를 채움(캐시 → 손) — 자리 하나를 잡고. → (글, is_error)."""
        run, opts = self.run, self.opts
        with Slot() as s:
            c = s.c
            att = attempt_of(p)
            if pa.answered(p):
                fill_rec(run, p, "already", "game", c)
                if not pr.turn_file(run, p["turn"], att).exists():
                    record_result(run, p, "replay", pkg_inp(run, p))
            else:
                if opts.get("test_touch_task") and p["id"] in opts["test_touch_task"] and not (Path(p["dir"]) / ".touched").exists():   # 시험(8-23 끝 조건 6)
                    tf = Path(p["task"])
                    tf.write_bytes(tf.read_bytes() + b"\n")
                    (Path(p["dir"]) / ".touched").write_text(now(), encoding="utf-8")
                    ev(run, "test_touch_task", pkg=p["id"])
                inp = pkg_inp(run, p)
                hit = try_reuse_from(run, p, opts, inp) if opts.get("reuse_from") else None
                hand = eff_hand(opts, "sup_reread", p)
                if hit:
                    with FILL_LOCK:
                        record_result(run, p, hand, inp, from_run=hit[0], orig_hand=hit[1], orig_usd=hit[2])
                        fill_rec(run, p, "filled", "reuse", c, from_run=rp(hit[0]), orig_hand=hit[1])
                elif hand == "api":
                    res = ah.fill_graph_pkg(run, p, opts, lambda: game_reread_text(run, p, opts))
                    with FILL_LOCK:
                        record_result(run, p, "api", inp, res=res)
                        fill_rec(run, p, "filled", "api", c, usd=res["usd"], calls=res["calls"])
                elif hand == "replay":
                    txt = game_reread_text(run, p, opts)
                    if txt is None:
                        raise GraphError(f"{p['id']}: 재생 손인데 옛 다시 읽기 답이 없음(재생 계획 {rp(plan_file(run))})")
                    if TEST["hand_delay"]:
                        time.sleep(TEST["hand_delay"])
                    with FILL_LOCK:
                        how = replay_source(run, p, opts)
                        put_answer(p, how) if how else pa.wt(Path(p["answer"]), txt)
                        record_result(run, p, "replay", inp)
                        fill_rec(run, p, "filled", "replay", c, src=rp(how[1]) if how else "game_reread_text")
                else:
                    raise GraphError(f"game 꼴에서 다시 읽기 손 {hand} 은 아직 안 됨(replay · api 만) — --layout manager 로")
        bad = pa.answer_form_error(pa.jl(p["answer"]))
        doc = pr.jl(pr.turn_file(run, p["turn"], att))
        return json.dumps(pr.strip_meta(doc), ensure_ascii=False, indent=1) + (f"\n(답 꼴 이상: {bad})" if bad else ""), False

    # --- 이어 가기(11-26 밤 고침): 요청됐으나 답이 없는 다시 읽기 꾸러미를 판 LLM 을 부르기 전에 다시 냄
    def pending_rereads(self) -> list:
        """판 꾸러미 draft.json 의 다시 읽기(paifu_sup reread 가 만든 것 — 결과 파일이 기준, 판 LLM state 가 아님) 가운데 answer.json 이 없는 것."""
        dr = pa.jl(self.pack / "draft.json") if (self.pack / "draft.json").exists() else {}
        out = []
        for x in dr.get("rereads") or []:
            dd = Path(x["dir"])
            p = pa.pkg("sup_reread", f"rr_{x['turn']}_r{x['n']}", dd, dd / "TASK.md", dd / "answer.json", game=self.g, turn=x["turn"], reread=int(x["n"]),
                       kind="reread")
            if not pa.answered(p):
                out.append(p)
        return out

    def stash_partial(self, p: dict) -> dict | None:
        """도중에 끊긴 시도의 찌꺼기(work/ · 답 사본 .api_pending)를 <실행>/graph/aborted/<꾸러미>/<k>/ 로 옮김 — 새 시도가 옛 초안을 읽지 않게(독립 읽기).
        api_log.jsonl 은 꾸러미에 그대로 둠(모델에게 숨김 · 돈 기록 — 그 돈은 graph/api_usage.jsonl 에 이미 한 번 셈, 결과 파일 cost 는 마지막 시도만)."""
        d = Path(p["dir"])
        pend = Path(p["answer"]).with_name("." + Path(p["answer"]).name + ".api_pending")
        things = [x for x in (d / "work", pend) if x.exists()]
        log = d / "api_log.jsonl"
        if not things and not log.exists():
            return None
        base = gdir(self.run) / "aborted" / p["id"]
        k = 1
        while (base / str(k)).exists():
            k += 1
        dst = base / str(k)
        dst.mkdir(parents=True, exist_ok=True)
        moved = []
        for x in things:
            shutil.move(str(x), str(dst / x.name))
            moved.append(x.name)
        L = pr.jlines(log)
        o = {"pkg": p["id"], "stash": rp(dst), "moved": moved, "starts": sum(1 for x in L if "start" in x),
             "ends": [x.get("end") for x in L if "end" in x], "usd_so_far": round(sum(float(x.get("usd") or 0) for x in L if "call" in x and "usd" in x and "tool" not in x), 6)}
        if log.exists():
            append(log, {"at": now(), "restart": True, "stash": rp(dst), "why": "앞 시도가 답 없이 끊김(실행 한도 · 죽음) — 새 시도로 처음부터. 앞 시도 돈은 graph/api_usage.jsonl 에 이미 셈"})
        pa.wj(dst / "stash.json", {**o, "at": now()})
        return o

    def refill_pending(self) -> list:
        """답 없는 다시 읽기를 먼저 채움(손이 api 면 다시 호출) — reread_fill(다시 읽기 꾸러미의 work 길: 캐시 → 손, 자리 하나씩)을 나란히."""
        pk = self.pending_rereads()
        if not pk:
            return []
        stashed = [s for s in (self.stash_partial(p) for p in pk) if s]
        ev(self.run, "reread_refill", game=self.g, pkgs=[p["id"] for p in pk], stashed=stashed)
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=len(pk)) as ex:
            futs = [ex.submit(self.reread_fill, p) for p in pk]
            for fu in futs:
                fu.result()
        return [p["id"] for p in pk]

    TOOLS = ("read_game", "read_turn", "reread", "take", "check", "ask", "finish")

    def exec_tools(self, uses: list, state: dict, slot=None) -> list:
        """한 응답의 도구 호출들을 차례대로. 이어진 reread 는 꾸러미를 차례로 만든 뒤 자리를 놓고 나란히 채움(판 LLM 은 기다림)."""
        out = [None] * len(uses)
        i = 0
        while i < len(uses):
            b = uses[i]
            name, a, key = b["name"], dict(b.get("input") or {}), b["id"]
            if name == "reread":
                j = i
                made = []
                while j < len(uses) and uses[j]["name"] == "reread":
                    bj = uses[j]
                    if self.finished:
                        out[j] = ("이미 마감함", True)
                    else:
                        p, err = self.reread_make(dict(bj.get("input") or {}), bj["id"])
                        if err:
                            out[j] = err
                        else:
                            made.append((j, p))
                    j += 1
                if made:
                    if slot is not None:
                        slot.__exit__(None, None, None)
                    try:
                        from concurrent.futures import ThreadPoolExecutor
                        with ThreadPoolExecutor(max_workers=len(made)) as ex:
                            futs = [(j2, ex.submit(self.reread_fill, p)) for j2, p in made]
                            for j2, fu in futs:
                                out[j2] = fu.result()
                    finally:
                        if slot is not None:
                            slot.__enter__()
                i = j
                continue
            try:
                if name not in self.TOOLS and not (name == "set" and state.get("replay")):
                    out[i] = (f"모르는 도구 또는 이 판 LLM 에 없는 도구: {name}(프레임 · 파일 열기 도구는 없음)", True)
                elif self.finished and name != "read_game" and name != "read_turn":
                    out[i] = ("이미 마감함 — 더 할 일 없음", True)
                else:
                    out[i] = getattr(self, f"t_{name}")(a, key)
            except GraphError:
                raise
            except Exception as e:  # noqa: BLE001
                out[i] = (f"{type(e).__name__}: {e}"[:600], True)
            if name == "finish" and self.finished:
                state["finished"] = True
            i += 1
        return out

    # --- 한도로 닫기(8-20 force_close 와 같은 뜻 — 판 하나)
    def force_close(self, why: str):
        meta = self.meta
        tgt = list(meta.get("unsure_first") or []) + ([t for t in meta.get("low_p_first") or [] if t not in (meta.get("unsure_first") or [])] if low_p_acts() else [])
        tgt += [t for t in meta["turns"] if t in (meta.get("window_shift") or {}) and t not in tgt]
        asked = {q["turn"] for q in pa.jl(self.pack / "draft.json")["asks"]}
        tries = []
        for k in range(3):
            for t in [t for t in tgt if t not in asked]:
                self.t_ask({"turn": t, "candidates": "지금 초안 · 처음 답 · 다시 읽기 답 가운데(판 LLM 이 풀지 못함)",
                            "why": f"{why} — 판 LLM 이 마감 못 함, 마감 검사 대상 차례를 코드가 질문으로 올림"}, f"limit_ask_{t}")
                asked.add(t)
            o = self.sup(f"limit_done_{k}", "game_force_done", ["done", "--pack", self.pack.as_posix()])
            tries.append(o["rc"])
            if o["rc"] == 0:
                self.finished = True
                self.report = (self.report or "") + f" [코드가 닫음: {why}]"
                self.save(closed_by=why)
                return
            tgt = [t for t in meta["turns"] if re.search(rf"\b{re.escape(t)}\b", reject_text(o))]
            if not [t for t in tgt if t not in asked]:
                break
        raise GraphError(f"{self.g}: 한도로 닫기 실패(done 거절 {tries}) — {reject_text(o)}")

    # --- 재생 손(LLM 0): 옛 판 supervisor 기록의 라운드를 8-20 관리자 재생과 같은 차례로 도구로 실행
    def replay_script(self) -> list:
        with PLAN_LOCK:   # 판 LLM 이 나란히 돌므로 계획 파일 만들기 · 더하기는 하나씩
            plan = ensure_plan(self.run, self.opts.get("replay_sup_from") or self.opts.get("replay_from"), [self.g])
            if self.g not in plan["games"]:   # 계획 파일이 다른 판만 담고 있음 — 이 판 몫을 더함
                src = pa.hcfg._p(self.opts.get("replay_sup_from") or self.opts.get("replay_from"))
                plan["games"][self.g] = plan_game(src / "sup" / self.g)
                pa.wj(plan_file(self.run), plan)
        rounds = (plan["games"].get(self.g) or {}).get("rounds") or []
        steps = [{"text": "(재생) 판 결과를 본다.", "tools": [("read_game", {})]}]
        for n, acts in enumerate(rounds, 1):
            calls = []
            for a in acts:
                if a["do"] == "reread":
                    calls.append(("reread", {"turn": a["turn"], "frames": a.get("frames"), "why": a.get("why") or ""}))
                elif a["do"] == "take":
                    calls.append(("take", {"turn": a["turn"], "from": a["from"], "why": a.get("why") or ""}))
                elif a["do"] == "ask":
                    calls.append(("ask", {"turn": a["turn"], "candidates": a.get("candidates") or "", "why": a.get("why") or ""}))
                elif a["do"] == "replay_set":
                    calls.append(("set", {"turn": a["turn"], "answer": a["answer"], "evidence": a.get("evidence") or "", "why": a.get("why") or ""}))
            if calls:
                steps.append({"round": n, "tools": calls})
            if any(a["do"] in ("reread", "take", "replay_set") for a in acts):
                steps.append({"round": n, "tools": [("check", {})], "if_touched": True})
            if any(a["do"] == "accept" for a in acts) and not any(a["do"] == "reread" for a in acts):
                steps.append({"round": n, "tools": [("finish", {"report": "재생 — 옛 판 supervisor 의 done"})], "finish": True})
        return steps

    def run_replay(self, slot=None):
        """재생 손: 걸음마다 도구를 실행(8-20 과 같은 sup 명령 차례 — check 는 그 라운드에 손댄 것(성공한 reread · take · set)이 있을 때만)."""
        state = {"replay": True}
        touched = False
        k = 0
        for st in self.replay_script():
            if self.finished:
                break
            uses = []
            for name, inp in st["tools"]:
                k += 1
                uses.append({"type": "tool_use", "id": f"replay_{k:03d}", "name": name, "input": inp})
            if st.get("if_touched"):
                if not touched:
                    continue
                touched = False
            outs = self.exec_tools(uses, state, slot)
            for u, (txt, err) in zip(uses, outs):
                if u["name"] in ("reread", "take", "set") and not err:
                    touched = True
                if err and u["name"] != "finish":
                    ev(self.run, "game_replay_reject", game=self.g, tool=u["name"], out=txt[:500])
        if not self.finished:
            self.force_close(f"재생 라운드 {MAX_ROUNDS} 뒤에도 마감 안 됨")
            return "closed_by_limit"
        return "done"

    def fake_script(self, step: int = 1) -> list:
        """가짜 판 LLM 걸음(--api-fake) — step 번째 호출부터(새 클라이언트를 만든 때). game=test 면 끝 조건 4 시험 걸음, game=multi 면 아래, 아니면 재생 계획을
        도구 호출로(set 이 있으면 거절). multi 는 step > 1(재개 · --reuse-from 으로 앞 호출을 베낀 뒤)이면 지금 판 꾸러미를 보고 남은 의심 차례를 ask → finish."""
        fo = ah.parse_fake(self.opts.get("api_fake") or "replay")
        if fo.get("game") == "multi" and step > 1:
            meta = self.meta
            tgt = list(meta.get("unsure_first") or []) + ([t for t in meta.get("low_p_first") or []] if low_p_acts() else [])
            tgt += [t for t in meta["turns"] if t in (meta.get("window_shift") or {})]
            dr = pa.jl(self.pack / "draft.json")
            done_ = {x["turn"] for x in dr.get("rereads") or []} | {q["turn"] for q in dr.get("asks") or []}
            rest = [t for k, t in enumerate(tgt) if t not in tgt[:k] and t not in done_]
            S = []
            if rest:
                S.append({"text": "(가짜 multi · 이어 감) 남은 의심 차례는 묻는다.",
                          "tools": [("ask", {"turn": t, "candidates": "처음 답 · 다른 후보", "why": "가짜 multi — 다시 읽기 한도 밖"}) for t in rest]})
            S.append({"text": "(가짜) 마감.", "tools": [("finish", {"report": f"가짜 판 LLM multi(이어 감) — 다시 읽기 {len(dr.get('rereads') or [])} · 질문 더함 {len(rest)}"})]})
            return S
        return self._fake_script(fo)[step - 1:]

    def _fake_script(self, fo: dict) -> list:
        if fo.get("game") == "test":
            t = self.turns[0]
            other = next((x for x in pa.Run(self.run).games() if x != self.g), None)
            other_t = (pa.game_answer_ids(pa.Run(self.run), other) or [f"{other}_d01"])[0] if other else "x_d01"
            frame = sorted((self.run / "read" / t / "raw").glob("*.jpg"))
            S = [{"text": "(가짜 판 LLM) 판을 본다 · 길 지키기 걸음.", "tools": [
                    ("read_game", {}), ("read_turn", {"turn": t}),
                    ("read_turn", {"turn": other_t}),                                               # 다른 판 차례
                    ("read_turn", {"turn": f"../../read/{t}/raw/00000.jpg"}),                      # 경로로 프레임
                    ("view_image", {"path": frame[0].as_posix() if frame else "raw/00000.jpg"}),   # 없는 도구(프레임 열기)
                    ("read_text", {"path": (self.run / "sup" / (other or "x") / "game.md").as_posix()})]},   # 없는 도구(다른 판 파일)
                 {"text": "(가짜) 다시 읽힌다.", "tools": [("reread", {"turn": t, "frames": None, "why": "가짜 시험 — 확인"})]},
                 {"tools": [("check", {})]},
                 {"text": "(가짜) 마감해 본다.", "tools": [("finish", {"report": "가짜 — 첫 마감 시도"})]},
                 {"tools": [("reread", {"turn": t, "frames": None, "why": "가짜 — 한도 넘김 시험"})]},
                 {"tools": [("ask", {"turn": t, "candidates": "처음 답 · r1", "why": "가짜 — 다시 읽기가 처음과 다름"})]},
                 {"tools": [("finish", {"report": "가짜 판 LLM 보고 — w14 한 차례를 다시 읽혔고 처음과 달라 질문으로 남김(도구 시험)."})]}]
            return S
        if fo.get("game") == "multi":   # 11-26 밤 시험(이어 가기): 의심 차례(unsure · 낮은 p · 창 흔들림)를 판 한도까지 한 응답에 다시 읽히고 나머지는 ask → finish
            meta = self.meta
            tgt = list(meta.get("unsure_first") or []) + ([t for t in meta.get("low_p_first") or []] if low_p_acts() else [])
            tgt += [t for t in meta["turns"] if t in (meta.get("window_shift") or {})]
            tgt = [t for k, t in enumerate(tgt) if t not in tgt[:k]]
            lim = int(meta["limits"]["reread_game"])
            rr, rest = tgt[:lim], tgt[lim:]
            S = [{"text": "(가짜 판 LLM multi) 판을 본다.", "tools": [("read_game", {})]},
                 {"text": "(가짜) 의심 차례를 한꺼번에 다시 읽힌다.", "tools": [("reread", {"turn": t, "frames": None, "why": "가짜 multi — 의심 차례"}) for t in rr]}]
            if rest:
                S.append({"text": "(가짜) 한도 밖 차례는 묻는다.", "tools": [("ask", {"turn": t, "candidates": "처음 답 · 다른 후보", "why": "가짜 multi — 다시 읽기 한도 밖"})
                                                               for t in rest]})
            S.append({"text": "(가짜) 마감.", "tools": [("finish", {"report": f"가짜 판 LLM multi — 다시 읽기 {len(rr)} · 질문 {len(rest)}"})]})
            return S
        steps = self.replay_script()
        out = []
        for st in steps:
            if any(nm == "set" for nm, _ in st["tools"]):
                raise ah.ApiFail(f"{self.g}: 재생 계획에 set 이 있어 가짜 판 LLM 이 따라 할 수 없음(판 LLM 도구에 set 없음) — 이 판은 --api-games 에서 빼라")
            out.append({"text": st.get("text") or "(가짜 판 LLM)", "tools": st["tools"]})
        return out

    def run_api(self):
        opts = self.opts
        fm = self.adir / "first_message.md"
        own = [x for x in pr.jlines(self.adir / "calls.jsonl") if x.get("response") is not None] if (self.adir / "calls.jsonl").exists() else []
        if fm.exists() and own:   # 이어 가기(11-26 밤 고침): 앞 시도의 첫 메시지 그대로 — 다시 만들면 앞 시도가 바꾼 판 상태(다시 읽기 시도 목록)가 들어가 대화가 처음부터 감
            first = fm.read_bytes().decode("utf-8")
            ev(self.run, "game_resume", game=self.g, calls_before=len(own), first_sha=pr.sha_text(first)[:16])
        else:
            first = game_first_message(self.run, self.g, self.pack)
            fm.parent.mkdir(parents=True, exist_ok=True)
            fm.write_bytes(first.encode("utf-8"))
        norm = lambda s: pr.norm_text(s, self.run)   # noqa: E731
        ix = reuse_index(opts)

        def lookup(prefix):
            h = ix.find_call(prefix) if ix else None
            return (h[0], h[1]) if h else None

        if opts.get("api_fake"):
            def client_fn(step):
                cl = ah.FakeClient(self.fake_script(step), out_tokens=ah.parse_fake(opts["api_fake"])["out"])
                cl.n = 1000 * step
                return cl
        else:
            def client_fn(step):
                return ah.real_client()
        meter = ah.meter_of(gdir(self.run))
        slot = Slot().__enter__()
        try:
            res = ah.run_game_agent(pid=f"game_{self.g}", first_text=first, exec_tools=lambda uses, st: self.exec_tools(uses, st, slot), client_fn=client_fn,
                                    meter=meter, adir=self.adir, reuse_lookup=lookup, norm=norm)
        finally:
            slot.__exit__(None, None, None)
        self.save(result=res)
        if res["status"] == "ok":
            return "done", res
        if res["status"] in ("budget", "tool_limit", "no_finish", "calls"):
            self.force_close(f"판 LLM {res['status']}: {res['why']}")
            return "closed_by_limit", res
        raise ah.ApiFail(f"game_{self.g} {res['status']}: {res['why']} — 기록 {rp(self.adir)}/api_log.jsonl")

    def agent_doc(self, res: dict | None, hand: str) -> dict:
        cost = pr.zero_cost()
        src = {"hand": hand, "from_run": None, "pkg": pr.rel_to(self.adir, self.run)}
        if res:
            calls = pr.jlines(self.adir / "calls.jsonl")
            new = [x for x in calls if not x.get("reused")]
            cost = {"calls": len(new), "in": sum(x.get("in") or 0 for x in new), "out": sum(x.get("out") or 0 for x in new),
                    "cache_read": sum(x.get("cache_read") or 0 for x in new), "cache_write": sum(x.get("cache_write") or 0 for x in new),
                    "usd": round(sum(float(x.get("usd") or 0) for x in new), 6), "seconds": float(res.get("s") or 0), "reused": bool(res.get("reused_calls")) and not new}
            if res.get("reused_calls"):
                src["reused_calls"] = res["reused_calls"]
                src["orig_usd"] = res.get("orig_usd")
                fr = {x.get("from_run") for x in calls if x.get("reused") and x.get("from_run") != "이 실행(재개)"}
                src["from_run"] = pr.rel_root(sorted(fr)[0]) if fr else None
        if hand == "replay":
            src["from_run"] = (load_plan(self.run) or {}).get("source_run")
        acts = [{k: v for k, v in a.items() if k != "key"} for a in self.actions]
        return {"actions": acts, "finish_refused": list(self.refused), "report": self.report, "source": src, "cost": cost}


def n_game(x: dict):
    """판 하나의 판 LLM(또는 재생) — 끝나면 games/<판>.json 마감본."""
    g, opts, run = x["game"], x["opts"], Path(x["run"])
    hand = game_hand(opts, g)
    G = GameRun(run, g, opts)
    if G.finished:
        st = pa.jl(G.adir / "state.json") if (G.adir / "state.json").exists() else {}
        pr.write_game(run, g, "closed_by_limit" if st.get("closed_by") else "done", G.agent_doc(st.get("result"), hand if hand != "api" else "api"))
        ev(run, "game_already", game=g)
        return {"log": [{"game": g, "event": "already"}], "max_conc": 0}
    pr.write_game(run, g, "draft", None)
    ev(run, "game_start", game=g, hand=hand)
    if hand in ("replay", "api"):   # 이어 가기(11-26 밤 고침): 앞 시도에서 요청됐으나 답이 없는 다시 읽기를 판 LLM 을 부르기 전에 먼저 채움
        G.refill_pending()
    res = None
    if hand == "replay":
        slot = Slot().__enter__()
        try:
            status = G.run_replay(slot)
        finally:
            slot.__exit__(None, None, None)
    elif hand == "api":
        status, res = G.run_api()
        c = CONC["max"]
    else:
        raise GraphError(f"game 꼴의 판 LLM 손 {hand} 은 안 됨(replay · api 만) — session 손은 --layout manager 로")
    st = pa.jl(G.adir / "state.json") if (G.adir / "state.json").exists() else {}
    G.save(result=res, closed_by=st.get("closed_by"), status=status)
    pr.write_game(run, g, status, G.agent_doc(res, hand))
    ev(run, "game_done", game=g, status=status, actions=len(G.actions), refused=len(G.refused))
    return {"log": [{"game": g, "event": status}], "max_conc": CONC["max"]}


def n_games_join(s: GS):
    ev(s["run"], "games_join", conc_max=CONC["max"])
    return {"phase": "stage"}


# ------------------------------------------------------------------ 확인 멈춤 · 답 반영
def refresh_games(run, opts: dict):
    """game 꼴: S8 · S9 뒤 · 사용자 답 뒤 판 결과 파일을 지금 파일들로 다시 만듦(상태 · agent 칸은 그대로)."""
    if opts.get("layout", "manager") != "game":
        return
    for f in sorted((Path(run) / "games").glob("*.json")):
        if f.name != "index.json":
            pr.write_game(run, f.stem)


def write_user_turns(run):
    """사용자 답이 반영된 차례(state.answered 의 차례 id)마다 turns/<순>/user.json."""
    r = pa.Run(Path(run))
    cfg = r.cfg()
    for t in r.state.get("answered") or []:
        af = r.read / t / "answer.json"
        g = cfg.game_of(t)
        if g and af.exists() and pa.jl(af).get("user"):
            d = pa.jl(af)
            doc = pr.turn_doc(run, g, t, "user", d, None, {"hand": "user", "from_run": None, "pkg": pr.rel_to(af.parent, run),
                                                        "note": "사용자 확인값(apply 뒤 answer.json)"}, pr.zero_cost())
            pr.wj(pr.turn_file(run, t, "user"), doc)


def confirm_mode(opts: dict) -> str:
    """설계서 8-26: S9 뒤 갈림 — auto(기본 · opts 에 칸이 없는 옛 그래프 기록도) = 자동 확정, page = 확인 페이지 멈춤(옛 길)."""
    return (opts or {}).get("confirm") or "auto"


def n_confirm(s: GS):
    run = s["run"]
    refresh_games(run, s["opts"])
    r = runner(run)
    if r.o.get("finished"):
        return {"phase": "done"}
    if confirm_mode(s["opts"]) == "auto" and not r.o["rounds"]:   # 8-26 자동 확정(확인 차례를 이미 연 실행 — 옛 page 멈춤에서 resume — 은 옛 길 그대로)
        try:
            summ = prun.auto_confirm(r)
        except RuntimeError as e:
            raise GraphError(f"자동 확정 실패 — {e}")
        ev(run, "auto_confirm", events_marked=summ["events_marked"], events_already=summ["events_already"], turns=summ["turns"],
           estimates=summ["estimates"], unmapped=summ["unmapped"])
        return {"phase": "done", "answer": {"auto": {k: summ[k] for k in ("events_marked", "events_already", "turns", "estimates", "unmapped")}}}
    if not r.o["rounds"]:
        try:
            prun.make_round(r, 1, prun.round_rows(r))
        except SystemExit as e:
            raise GraphError(f"확인 1차례 자료(paifu_confirm prep) 실패 — {e}")
        r = runner(run)
    rd = r.o["rounds"][-1]
    if rd.get("answered_at") is not None:
        return {"phase": "done"}
    q, sm = pa.jlines(r.d / "questions.jsonl"), pa.jlines(r.d / "samples.jsonl")
    v = interrupt({"why": "page", "round": prun.round_view(r, rd), "questions": len(q), "samples": len(sm), "question_ids": [x["id"] for x in q],
                   "sample_ids": [x["id"] for x in sm], "report": rp(r.d / "report.md"), "page": prun.page_cmd(r), "answers_file": rp(r.d / "answers_user.json"),
                   "resume": f"python -X utf8 experiments/paifu_frames/paifu_graph.py resume --run {rp(r.d)} --answers <답 파일>"})
    return {"phase": "answer", "answers_file": (v or {}).get("answers") if isinstance(v, dict) else v}


def r_confirm(s: GS):
    return END if s["phase"] == "done" else "answer"


def n_answer(s: GS):
    run = s["run"]
    r = runner(run)
    dst = r.d / "answers_user.json"
    af = s.get("answers_file")
    if af and absp(af) != dst.resolve():
        shutil.copyfile(absp(af), dst)
    log = r.d / "logs" / f"graph_answer_{len(r.o['rounds'])}.log"
    e = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([PY, "-X", "utf8", str(RUN_PY), "answer", "--run", rp(r.d)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=e)
    pa.wt(log, f"paifu_run.py answer --run {rp(r.d)}\n# rc {p.returncode}\n" + p.stdout + ("\n--- stderr\n" + p.stderr if p.stderr else ""))
    try:
        res = json.loads(p.stdout)
    except json.JSONDecodeError:
        res = {"out": prun.tail(p.stdout + p.stderr, 1500)}
    ev(run, "answer", rc=p.returncode, extra=res.get("extra"), apply=res.get("apply"))
    write_user_turns(run)
    refresh_games(run, s["opts"])
    if p.returncode == EXIT["page"]:
        return {"phase": "confirm", "answer": res}
    if p.returncode == EXIT["done"]:
        return {"phase": "done", "answer": res}
    raise GraphError(f"paifu_run answer rc {p.returncode} — {rp(log)}: {json.dumps(res, ensure_ascii=False)[:1500]}")


def r_answer(s: GS):
    return "confirm" if s["phase"] == "confirm" else END


# ------------------------------------------------------------------ 그래프
def build(run: Path):
    g = StateGraph(GS)
    for name, fn in (("stage", n_stage), ("work", n_work), ("join", n_join), ("mgr_prep", n_mgr_prep), ("manager", n_manager),
                     ("mgr_apply", n_mgr_apply), ("mgr_close", n_mgr_close), ("confirm", n_confirm), ("answer", n_answer)):
        g.add_node(name, fn)
    g.add_edge(START, "stage")
    g.add_node("game", n_game)
    g.add_node("games_join", n_games_join)
    g.add_conditional_edges("stage", r_stage, ["work", "mgr_prep", "confirm", "game", END])
    g.add_edge("game", "games_join")
    g.add_edge("games_join", "stage")
    g.add_edge("work", "join")
    g.add_conditional_edges("join", r_join, ["work", "stage", "mgr_close"])
    g.add_edge("mgr_prep", "manager")
    g.add_conditional_edges("manager", r_manager, ["mgr_apply", "manager"])
    g.add_conditional_edges("mgr_apply", r_mgr_apply, ["work", "mgr_close", "manager"])
    g.add_conditional_edges("mgr_close", r_mgr_close, ["mgr_prep", "stage"])
    g.add_conditional_edges("confirm", r_confirm, ["answer", END])
    g.add_conditional_edges("answer", r_answer, ["confirm", END])
    conn = sqlite3.connect(str(run / DB), check_same_thread=False)
    return g.compile(checkpointer=SqliteSaver(conn)), conn


def thread_of(run: Path) -> str:
    """thread_id — graph.json 에 적힌 것(go --again 이면 새 이름), 없으면 실행 폴더 이름. 상태의 기준은 결과 파일이고 checkpoint 는 보조(8-20 덧붙임)."""
    f = gdir(run) / "graph.json"
    if f.exists():
        try:
            return pa.jl(f).get("thread_id") or run.name
        except (json.JSONDecodeError, OSError):
            pass
    return run.name


def cfg_of(run: Path, mc: int) -> dict:
    return {"configurable": {"thread_id": thread_of(run)}, "max_concurrency": mc, "recursion_limit": 5000}


def fills_summary(run: Path) -> dict:
    L = log_lines(gdir(run) / "fills.jsonl")
    filled = Counter(x["id"] for x in L if x["event"] == "filled")
    return {"lines": len(L), "events": dict(Counter(x["event"] for x in L)), "filled_packages": len(filled),
            "filled_twice": sorted(k for k, c in filled.items() if c > 1), "by_kind": dict(Counter(x["kind"] for x in L if x["event"] == "filled")),
            "s7s_to_hand": sum(1 for x in L if x.get("stage") == "S7s"), "max_conc_seen": max([x.get("conc") or 0 for x in L if not x.get("forked_from")] or [0]),
            "forked_lines": sum(1 for x in L if x.get("forked_from"))}


def out_view(run: Path, st) -> dict:
    v = st.values or {}
    m = v.get("mgr") or {}
    return {"run": rp(run), "thread_id": run.name, "hands": (v.get("opts") or {}).get("hands"), "max_concurrency": (v.get("opts") or {}).get("max_concurrency"),
            "max_conc": v.get("max_conc"), "phase": v.get("phase"), "stage": v.get("stage"),
            "mgr": {"round": m.get("round"), "games": {g: {k: x.get(k) for k in ("status", "rounds", "checks", "closed_by")} for g, x in (m.get("games") or {}).items()},
                    "rounds": m.get("rounds"), "closed_by_limit": m.get("closed_by_limit")} if m else None,
            "fills": fills_summary(run),
            **({"api": ah.usage_summary(gdir(run))} if (gdir(run) / "api_usage.jsonl").exists() or (gdir(run) / "api_limit.json").exists() else {})}


def drive(run: Path, inp, mc: int):
    SLOT["sem"] = threading.BoundedSemaphore(mc)
    app, conn = build(run)
    cfg = cfg_of(run, mc)
    t0 = time.time()
    try:
        app.invoke(inp, cfg, durability="sync")
    except ah.ApiStop as e:   # 실행 한도(8-21 돈 지키기) — resume --max-usd 로 이어 감
        st = app.get_state(cfg)
        ev(run, "api_stop", why=str(e)[:2000])
        emit({**out_view(run, st), "why": str(e)[:3000], "s": round(time.time() - t0, 1),
              "next": f"한도를 올려: python -X utf8 experiments/paifu_frames/paifu_graph.py resume --run {rp(run)} --max-usd <새 한도>"}, "stop")
    except ah.ApiFail as e:   # 꾸러미 하나 실패(꾸러미 한도 · refusal · 오류 · 답 없음) — 사람에게 보고
        st = app.get_state(cfg)
        ev(run, "api_fail", why=str(e)[:2000])
        emit({**out_view(run, st), "why": str(e)[:3000], "s": round(time.time() - t0, 1),
              "next": f"까닭을 본 뒤: python -X utf8 experiments/paifu_frames/paifu_graph.py resume --run {rp(run)}"}, "error")
    except GraphError as e:
        st = app.get_state(cfg)
        ev(run, "error", why=str(e)[:2000])
        emit({**out_view(run, st), "why": str(e)[:3000], "s": round(time.time() - t0, 1),
              "next": f"고친 뒤: python -X utf8 experiments/paifu_frames/paifu_graph.py resume --run {rp(run)}"}, "error")
    except Exception as e:   # noqa: BLE001
        st = app.get_state(cfg)
        ev(run, "error", why=f"{type(e).__name__}: {e}"[:2000])
        emit({**out_view(run, st), "why": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-3000:], "s": round(time.time() - t0, 1)}, "error")
    st = app.get_state(cfg)
    base = {**out_view(run, st), "s": round(time.time() - t0, 1)}
    if st.interrupts:
        vals = [i.value for i in st.interrupts]
        pg = [x for x in vals if x.get("why") == "page"]
        if pg:
            emit({**base, **pg[0]}, "page")
        pk = [x["pkg"] for x in vals if x.get("why") == "read"]
        emit({**base, "packages": pk, "count": len(pk), "replay_miss": [x["pkg"]["id"] for x in vals if x.get("replay_miss")],
              "next": f"꾸러미마다 task 를 읽혀 answer 에 쓴 뒤: python -X utf8 experiments/paifu_frames/paifu_graph.py resume --run {rp(run)}"}, "read")
    if st.next:
        emit({**base, "why": f"멈췄는데 interrupt 가 없음 — 다음 마디 {list(st.next)}"}, "error")
    r = runner(run)
    if (st.values or {}).get("phase") == "games_end":
        idx = pa.jl(run / "games" / "index.json") if (run / "games" / "index.json").exists() else None
        emit({**base, "games_only": (st.values.get("opts") or {}).get("games"), "games_index": idx, "why": "판 실행(--games) — 판 몫 단계 끝, 반장 마무리(S8 · S9 · 확인)는 안 함"}, "done")
    emit({**base, "finished": r.o.get("finished"), "rounds": [prun.round_view(r, x) for x in r.o["rounds"]],
          "answer": (st.values or {}).get("answer"), "report": rp(run / "report.md")}, "done")


def set_api(run: Path, opts: dict, a) -> None:
    """api 손 준비: 가짜면 진짜 호출 길을 닫고(arm_fake), 진짜면 --i-mean-it 을 요구. --max-usd 는 <실행>/graph/api_limit.json 에."""
    if opts.get("hands") != "api":
        return
    if opts.get("api_fake"):
        if getattr(a, "i_mean_it", False):
            emit({"run": rp(run), "why": "--api-fake 와 --i-mean-it 을 같이 줄 수 없음"}, "stop")
        ah.arm_fake()
    else:
        if not getattr(a, "i_mean_it", False):
            emit({"run": rp(run), "why": "진짜 Claude API 호출 — 이 명령에 --i-mean-it 을 붙여야 함(크레딧 · 한도 확인 뒤). 시험은 --api-fake replay"}, "stop")
        ah.allow_real(True)
    if getattr(a, "max_usd", None) is not None:
        ah.set_limit(gdir(run), a.max_usd)
        ev(run, "api_limit", max_usd=a.max_usd)
    elif not (gdir(run) / "api_limit.json").exists():
        ah.set_limit(gdir(run), ah.RUN_USD_DEFAULT)


def set_test(a):
    TEST["hand_delay"] = float(a.hand_delay or 0)
    TEST["die_after"] = int(a.die_after) if a.die_after else None
    TEST["die_after_stage"] = getattr(a, "die_after_stage", None)


def has_thread(run: Path) -> bool:
    if not (run / DB).exists():
        return False
    app, conn = build(run)
    st = app.get_state(cfg_of(run, MC_DEFAULT))
    conn.close()
    return bool(st.values)


# ------------------------------------------------------------------ 판 실행(8-23 "실행도 판 단위") — 판 하나 = 실행 폴더 하나 · 반장 조립
UNIT_SEP = "__"
UNIT_PAR_DEFAULT = 3
UNIT_MERGE_STAGES = ("S4", "S6a", "S6b", "S6", "S7", "S7s")       # 조립이 판 실행 state 를 합쳐 끝난 것으로 적는 단계(S5 는 조립에서 반장 전체로 다시 — H2)
UNIT_SKIP_TOP = {"logs", "graph", "graph.sqlite", "graph.sqlite-shm", "graph.sqlite-wal", "state.json", "runner.json", "runner", "pending.json", "report.md",
                 "start_report.json", "start_report.md", "confirm", "mgr"}
UNIT_RERUN_TOP = {"rounds_meta.json", "recorder_fix.json", "s5", "_inner"}   # 반장 조립의 S5 가 반장 전체로 다시 씀(판 실행 것은 안 씀) · _inner = 하위 프로세스 스크립트(부를 때마다 새로)


def unit_dir(run: Path, g: str) -> Path:
    """판 실행 폴더 — 반장 실행 옆 <반장 실행>__<판>(실행 이름을 판 id 만으로 두면 결과 파일 정규화(<RUN>)가 판 id 를 지움)."""
    return Path(run).parent / f"{Path(run).name}{UNIT_SEP}{g}"


def units_file(run: Path) -> Path:
    return gdir(run) / "units.json"


# ------------------------------------------------------------------ 반장 공통 앞 단계(11-27 — 처음 시작한 반장에서 판 실행으로 잇는 길)
PREFIX_UNTIL = "S4"   # 판 실행이 반장 실행을 베끼는 자리(run_units → fork_run(run, U, "S4")) — 그 앞(S0 ~ S3)이 반장 공통 앞 단계(설계서 8-23)


def prefix_stages() -> list:
    return pa.STAGES[:pa.STAGES.index(PREFIX_UNTIL)]


def stages_before(run, until: str) -> list:
    """이 실행의 단계 목록(paifu_auto.stage_list — S7s 꺼짐 반영)에서 until 앞 단계들. state.json 이 없으면 STAGES 기준."""
    stl = pa.stage_list(pa.Run(Path(run))) if (Path(run) / "state.json").exists() else pa.STAGES
    return stl[:stl.index(until)]


def until_done(run, until: str) -> bool:
    """until 앞 단계가 다 끝났나 — 기준은 결과 파일(state.json 의 단계 상태, 설계서 8-20)."""
    f = Path(run) / "state.json"
    if not f.exists():
        return False
    st = pa.jl(f)
    return all((st["stages"].get(x) or {}).get("status") == "done" for x in stages_before(run, until))


def prefix_done(run) -> bool:
    """반장 공통 앞 단계(S0 ~ S3)가 끝났나. fork --at S4 로 만든 반장은 늘 참."""
    return until_done(run, PREFIX_UNTIL)


def prefix_thread(run: Path) -> str:
    """공통 앞 단계 그래프 thread — 반장 실행의 본 thread(조립 뒤 마무리 · thread_of)와 따로(본 thread 가 있으면 go --games 가 조립을 막음)."""
    return f"{Path(run).name}#prefix"


def next_upto_main(argv: list):
    """하위 프로세스: paifu_auto next 를 --upto 단계까지만(그 뒤 단계 함수를 부르기 직전에 끊음). paifu_auto 는 안 고치고 이 프로세스 안에서만 STEP 를 바꿈.
    끊었으면 next 가 끝에 하듯 pending.json 을 비움(앞 단계 꾸러미가 남아 그래프가 같은 꾸러미로 next 를 거듭 부르지 않게)."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--upto", required=True, choices=pa.STAGES)
    a = ap.parse_args(argv)
    stl = pa.stage_list(pa.Run(Path(a.run)))

    class _Stop(BaseException):   # paifu_auto cmd_next 는 SystemExit 만 잡음 — 이것은 그대로 지나감
        pass

    def _stop(r):
        raise _Stop()
    keep = stl[:stl.index(a.upto) + 1]
    for k in list(pa.STEP):
        if k not in keep:
            pa.STEP[k] = _stop
    try:
        pa.cmd_next(argparse.Namespace(run=a.run, redo=None))
    except _Stop:
        f = pa.Run(a.run).d / "pending.json"
        if f.exists():
            pa.wj(f, {"stage": None, "at": now(), "packages": []})
        print(f"{a.upto} 까지 — 다음 단계 앞에서 멈춤(paifu_graph _next_upto)")
    raise SystemExit(0)


def drive_prefix(run: Path, opts: dict, a, mc: int, go_cmd: str) -> dict:
    """처음 시작한 반장(state.json 없음 또는 S0 ~ S3 가 안 끝남)에 go --games: 공통 앞 단계를 그래프(thread <실행>#prefix)로 S4 앞까지.
    꾸러미(S1 등)는 이 go 의 손으로. 끊기면 같은 go 를 다시 — 늘 새 입력으로 stage 부터 걸고, 끝난 단계 · 답이 찬 꾸러미는 결과 파일로 건너뜀(8-20)."""
    po = {**opts, "until": PREFIX_UNTIL, "games": None}
    set_api(run, po, a)
    SLOT["sem"] = threading.BoundedSemaphore(mc)
    app, conn = build(run)
    cfg = {"configurable": {"thread_id": prefix_thread(run)}, "max_concurrency": mc, "recursion_limit": 5000}
    st0 = app.get_state(cfg)
    how = "new" if not st0.values else ("after_read" if st0.interrupts else ("after_break" if st0.next else "again"))
    t0 = time.time()
    st_before = {x: ((pa.jl(run / "state.json")["stages"].get(x) or {}).get("status") if (run / "state.json").exists() else None) for x in prefix_stages()}
    ev(run, "go_prefix", how=how, thread=prefix_thread(run), before=st_before, **{k: po.get(k) for k in ("hands", "replay_from", "api_games", "api_fake")})
    base = {"run": rp(run), "prefix": {"thread": prefix_thread(run), "how": how, "stages_before": st_before}}
    nxt = f"까닭을 본 뒤 같은 명령: {go_cmd}"
    try:
        app.invoke({"run": posix(run), "opts": po, "phase": "stage", "log": [], "max_conc": 0}, cfg, durability="sync")
    except ah.ApiStop as e:
        conn.close()
        ev(run, "api_stop", why=str(e)[:2000], where="prefix")
        emit({**base, "why": f"공통 앞 단계에서 실행 한도 — {str(e)[:2000]}", "next": f"한도를 올려 같은 명령(--max-usd <새 한도>): {go_cmd}"}, "stop")
    except (ah.ApiFail, GraphError) as e:
        conn.close()
        ev(run, "error", why=str(e)[:2000], where="prefix")
        emit({**base, "why": f"공통 앞 단계 — {str(e)[:3000]}", "next": nxt}, "error")
    except Exception as e:  # noqa: BLE001
        conn.close()
        ev(run, "error", why=f"{type(e).__name__}: {e}"[:2000], where="prefix")
        emit({**base, "why": f"공통 앞 단계 — {type(e).__name__}: {e}", "trace": traceback.format_exc()[-3000:], "next": nxt}, "error")
    st = app.get_state(cfg)
    conn.close()
    s = round(time.time() - t0, 1)
    if st.interrupts:   # replay 손에 옛 답이 없는 꾸러미 — 답을 채운 뒤 같은 go(새 입력으로 다시 걸면 찬 꾸러미는 건너뜀)
        vals = [i.value for i in st.interrupts]
        emit({**base, "s": s, "packages": [x["pkg"] for x in vals if x.get("why") == "read"], "replay_miss": [x["pkg"]["id"] for x in vals if x.get("replay_miss")],
              "next": f"꾸러미마다 task 를 읽혀 answer 에 쓴 뒤 같은 명령: {go_cmd}"}, "read")
    if not prefix_done(run):
        emit({**base, "s": s, "why": f"공통 앞 단계가 안 끝났는데 그래프가 멈춤(phase {(st.values or {}).get('phase')} · 다음 마디 {list(st.next)})", "next": nxt}, "error")
    tm = {x: (pa.jl(run / "state.json").get("timing") or {}).get(x) for x in prefix_stages()}
    f = gdir(run) / "prefix.json"
    rec = pa.jl(f) if f.exists() else {"_note": "paifu_graph go --games 가 처음 시작한 반장에서 돈 공통 앞 단계(S0 ~ S3) 기록 — 11-27", "thread_id": prefix_thread(run), "runs": []}
    rec["runs"].append({"at": now(), "how": how, "s": s, "stages_before": st_before, "timing": tm, "hands": po.get("hands")})
    pa.wj(f, rec)
    ev(run, "prefix_done", s=s, timing=tm)
    return {"how": how, "s": s, "timing": tm, "stages_before": st_before}


def unit_owned(rel_parts: tuple, prefix: str) -> bool:
    """판 몫 파일인가 — 경로 마디 하나라도 이 판의 차례 접두사(<접두사>_ — 판 id · 차례 id · det_<판> · <판>_feat 등)를 품으면."""
    rx = re.compile(rf"(?<![A-Za-z0-9]){re.escape(prefix)}_")
    return any(rx.search(x) for x in rel_parts)


def unit_fork_at(U: Path) -> float:
    """판 실행이 반장 실행에서 베껴진 때 = 처음 games_only(판 좁히기) 바로 앞의 fork. 판 실행을 다시 판 실행으로 베낀 것(fork --at S7s 등 — 11-26 밤)도
    그 처음 시각을 씀(뒤 fork 시각을 쓰면 베껴 온 S4 ~ S7 파일이 조립에서 빠짐). games_only 가 없으면 마지막 fork."""
    ev_ = [e for e in pa.jl(U / "state.json").get("events") or [] if isinstance(e, dict)]
    gi = next((k for k, e in enumerate(ev_) if e.get("games_only")), None)
    cand = ev_[:gi] if gi is not None else ev_
    for e in reversed(cand):
        if e.get("fork"):
            return datetime.strptime(e["at"], "%Y-%m-%d %H:%M:%S").timestamp()
    return 0.0


def merge_games_list(base, parts: dict, order: list) -> dict:
    """{"games": [{"id": …}, …], …} 꼴 반장 파일 — 판 실행마다 자기 판 줄만 가져와 반장 판 순서로(나머지 칸은 base → 없으면 첫 판 실행 것)."""
    first = next(iter(parts.values()))
    out = dict(base or first)
    have = {x["id"]: x for x in (base or {}).get("games") or []}
    for g, d in parts.items():
        row = next((x for x in d.get("games") or [] if x["id"] == g), None)
        if row is None:
            have.pop(g, None)
        else:
            have[g] = row
    out["games"] = [have[g] for g in order if g in have] + [v for k, v in have.items() if k not in order]
    return out


def merge_by_owner(base, parts: dict, cfg) -> dict:
    """turn_fix 꼴(차례 id 칸 + __insert__ + __ 칸) — 판마다 그 판 몫을 판 실행 것으로 바꿈(han3 rturns 와 같은 차례: 판 순서로 지우고 덧붙임)."""
    fx = dict(base or {})
    for g, d in parts.items():
        fx = {k: v for k, v in fx.items() if k.startswith("__") or not cfg.owns(k, g)}
        if "__insert__" in fx:
            fx["__insert__"] = [x for x in fx["__insert__"] if not cfg.owns(x["id"], g)]
        for k, v in d.items():
            if k == "__insert__":
                fx.setdefault("__insert__", []).extend([x for x in v if cfg.owns(x["id"], g)])
            elif not k.startswith("__") and cfg.owns(k, g):
                fx[k] = v
            elif k.startswith("__") and k not in fx:
                fx[k] = v
    return fx


def merge_tid_list(base, parts: dict, cfg) -> list:
    out = [x for x in (base or []) if not any(cfg.owns(x.get("tid") or "", g) for g in parts)]
    for g, d in parts.items():
        out += [x for x in d or [] if cfg.owns(x.get("tid") or "", g)]
    return out


def _is_game_keyed(d: dict, games: list, cfg) -> bool:
    return bool(d) and all(k in games or cfg.game_of(k) in games for k in d)


def merge_stage(stage: str, ents: dict, games: list, cfg) -> dict:
    """판 실행들의 state.stages[<단계>] 를 반장 하나로(판 순서). 판 · 차례 이름 칸 dict 는 합치고, list 는 판 순서로 잇고, 수는 더하고, 글은 첫 판 것."""
    out = {}
    vals = [ents[g] for g in games if g in ents]
    keys = []
    for v in vals:
        keys += [k for k in v if k not in keys]
    for k in keys:
        xs = [v[k] for v in vals if k in v]
        x0 = xs[0]
        if k == "done_at":
            out[k] = max(xs)
        elif stage == "S6" and k == "plan":
            out[k] = {"hand": {g: h for x in xs for g, h in x["hand"].items()}, "call": [t for x in xs for t in x["call"]],
                      **({"only": x0["only"]} if "only" in x0 else {})}
        elif stage == "S6" and k == "call_turns":
            auto = [t for x in xs for t in x["auto"]]
            out[k] = {"auto": auto, "setting": x0["setting"], "same": sorted(auto) == sorted(x0["setting"])}
        elif stage == "S7" and k == "checks":   # 마지막 검사 = 판 실행마다 마지막 검사의 판 결과를 합친 것(build_game · S9 가 [-1] 을 봄)
            lasts = [x[-1] for x in xs if x]
            out[k] = [c for x in xs for c in x[:-1]] + ([{"at": max(c["at"] for c in lasts), "s": round(sum(c.get("s") or 0 for c in lasts), 1),
                                                          "result": {g: v for c in lasts for g, v in (c.get("result") or {}).items()},
                                                          "merged_from_units": len(lasts)}] if lasts else [])
        elif isinstance(x0, (bool, str)) or x0 is None:
            out[k] = x0
        elif isinstance(x0, (int, float)):
            nums = [x for x in xs if isinstance(x, (int, float)) and not isinstance(x, bool)]
            out[k] = round(sum(nums), 1) if isinstance(x0, float) else sum(nums)
        elif isinstance(x0, list):
            out[k] = [y for x in xs for y in x]
        elif isinstance(x0, dict):
            if all(_is_game_keyed(x, games, cfg) or not x for x in xs):
                out[k] = {kk: vv for x in xs for kk, vv in x.items()}
            elif all(isinstance(vv, (int, float)) and not isinstance(vv, bool) for x in xs for vv in x.values()):
                c = Counter()
                for x in xs:
                    c.update(x)
                out[k] = dict(c)
            else:
                out[k] = x0
        else:
            out[k] = x0
    return out


def assemble(run: Path, units: dict) -> dict:
    """반장 조립(판 결과 모으기): 판 실행 폴더마다 ① 그 판 몫 파일(경로 마디에 판 접두사)을 반장 실행에 베낌 ② 반장 한 파일(차례 목록 · turn_fix · 칸 자르기 ·
    기록 검사 · 시작 줄 · 끝 줄)은 판 몫 줄만 합침(H3) ③ state 의 S4 · S6a · S6b · S6 · S7 · S7s 를 판 순서로 합쳐 끝난 것으로, S5 · S8 · S9 는 todo — 반장 S5 가
    판 사이 이어지는 값(공탁 · 국 · 본장 검사 · 아래 자리)을 반장 전체로 다시 셈(H2) ④ 손 기록(fills · pkg_inputs)을 이어 붙임. 돌리지는 않음(이어서 그래프 stage)."""
    t0 = time.time()
    r = pa.Run(run)
    cfg = r.cfg()
    allg = list(r.state["game_ids"])
    miss = [g for g in allg if g not in units]
    if miss:
        raise GraphError(f"조립: 판 실행이 없는 판 {miss}")
    rep = {"at": now(), "units": {g: rp(units[g]) for g in allg}, "copied": {}, "unhandled": {}, "merged_files": [], "s": None}
    hfile = {cfg.turns_file: "games", cfg.cut_file: "games", cfg.fix_file: "owner", cfg.prep_dir / "turns_record_check.json": "keyed",
             cfg.prep_dir / "anchor_relaxed.json": "tid", cfg.prep_dir / "end_fallback.json": "tid"}
    hrel = {}
    for f, how in hfile.items():
        try:
            hrel[Path(f).resolve().relative_to(run.resolve()).as_posix()] = how
        except ValueError:
            pass
    parts = {k: {} for k in hrel}
    ht_games = []
    for g in allg:
        U = Path(units[g])
        pre = cfg.prefix_of(g)
        fat = unit_fork_at(U) + 1   # fork 가 끝난 뒤(판 실행이 만든 · 고친 파일만 — fork 가 경로만 바꾼 옛 파일은 반장 실행에 이미 있음)
        rw = path_rewriter(U, run)   # 판 실행이 쓴 글 파일 안의 판 실행 경로 → 반장 실행 경로(fork 와 같은 바꿈)
        n_copy, unh = 0, []
        for f in U.rglob("*"):
            if not f.is_file():
                continue
            rl = f.relative_to(U)
            if rl.parts[0] in UNIT_SKIP_TOP or ".tmp" in f.name or f.stat().st_mtime < fat:
                continue
            rs = rl.as_posix()
            if rs in hrel:
                parts[rs][g] = json.loads(rw(f.read_bytes().decode("utf-8")))
                continue
            if rs == "hanchan.json":   # S6a 가 handtrack.games 를 그 판으로 씀 — 조립이 판 순서로 합침(아래)
                ht_games += [x for x in ((pa.jl(f).get("handtrack") or {}).get("games") or []) if x not in ht_games]
                continue
            if rs == "games/index.json" or rl.parts[0] in UNIT_RERUN_TOP:
                continue
            dst = run / rl
            if unit_owned(rl.parts, pre) or (rs == "s6a/_dump_regions.json" and not dst.exists()):   # 판 몫 · 반장 전체 판에서 만든 상자(판 실행마다 같음)
                if copy_rewritten(f, dst, rw):
                    n_copy += 1
                continue
            if dst.exists() and dst.read_bytes() == rw_bytes(f, rw):
                continue
            unh.append(rs)
        rep["copied"][g] = n_copy
        if unh:
            rep["unhandled"][g] = unh[:40] + ([f"…(+{len(unh) - 40})"] if len(unh) > 40 else [])
    for rs, how in hrel.items():
        if not parts[rs]:
            continue
        hf = run / rs
        base = pa.jl(hf) if hf.exists() else None
        ps = {g: parts[rs][g] for g in allg if g in parts[rs]}
        if how == "games":
            out = merge_games_list(base, ps, allg)
        elif how == "owner":
            out = merge_by_owner(base, ps, cfg)
        elif how == "keyed":
            out = dict(base or {})
            for g, d in ps.items():
                if g in d:
                    out[g] = d[g]
                else:
                    out.pop(g, None)
            out = {**{g: out[g] for g in allg if g in out}, **{k: v for k, v in out.items() if k not in allg}}
        else:
            out = merge_tid_list(base, ps, cfg)
        pa.wj(hf, out)
        rep["merged_files"].append({"file": rs, "how": how, "from": sorted(ps)})
    if ht_games:   # hanchan.json handtrack(S6a — paifu_auto s6a_frame 과 같은 꼴, 판은 반장 판 순서)
        raw = pa.jl(r.cfg_f)
        want = {"dir": pa.rel(run / "handtrack"), "games": [g for g in allg if g in ht_games],
                "_note": "paifu_auto S6a: 이 판들의 손 추적 판별 설정 · 출력은 dir 아래(config/ · <판>/ · _work/) — handtrack/ht_redirect.py 가 실행 중에 경로를 돌림"}
        if raw.get("handtrack") != want:
            raw["handtrack"] = want
            pa.wj(r.cfg_f, raw)
            rep["merged_files"].append({"file": "hanchan.json", "how": "handtrack.games", "games": want["games"]})
    # state
    us = {g: json.loads(path_rewriter(Path(units[g]), run)((Path(units[g]) / "state.json").read_bytes().decode("utf-8"))) for g in allg}   # 경로는 반장 실행으로
    for s in UNIT_MERGE_STAGES:
        bad = [g for g in allg if (us[g]["stages"].get(s) or {}).get("status") != "done"]
        if bad:
            raise GraphError(f"조립: {s} 가 안 끝난 판 실행 {bad}")
        r.state["stages"][s] = merge_stage(s, {g: us[g]["stages"][s] for g in allg}, allg, cfg)
        r.state["timing"][s] = round(sum(us[g].get("timing", {}).get(s, 0) for g in allg), 1)
    for k in ("questions_s4", "questions_s6a", "questions_s6"):
        r.state[k] = [q for g in allg for q in us[g].get(k) or []]
    r.state["reread"] = {kk: vv for g in allg for kk, vv in (us[g].get("reread") or {}).items()}
    for s in ("S5", "S8", "S9"):
        r.state["stages"][s] = {"status": "todo"}
        r.state["timing"].pop(s, None)
    r.state["events"].append({"at": now(), "assembled": {"units": [rp(units[g]) for g in allg]}})
    r.save()
    # 손 기록(판 실행이 채운 줄 — fork 로 옮긴 줄은 뺌)
    for nm in ("fills.jsonl", "pkg_inputs.jsonl"):
        for g in allg:
            for x in log_lines(gdir(Path(units[g])) / nm):
                if not x.get("forked_from"):
                    append(gdir(run) / nm, {**x, "unit": rp(units[g])})
    pr.write_index(run)
    rep["s"] = round(time.time() - t0, 1)
    pa.wj(gdir(run) / "assemble.json", rep)
    ev(run, "assemble", copied=rep["copied"], unhandled={g: len(v) for g, v in rep["unhandled"].items()}, s=rep["s"])
    return rep


def path_rewriter(src: Path, dst: Path):
    """fork 와 같은 경로 바꿈(절대 posix · 절대 · JSON 이중 역슬래시 · 저장소 기준 · 따옴표 안 실행 이름) — 한 번에, 뒤에 이름 글자가 붙은 것은 안 바꿈."""
    src, dst = Path(src).resolve(), Path(dst).resolve()
    reps = [(src.as_posix(), dst.as_posix()), (str(src), str(dst)), (str(src).replace("\\", "\\\\"), str(dst).replace("\\", "\\\\")), (rp(src), rp(dst)),
            (f'"{src.name}"', f'"{dst.name}"')]
    rmap = dict(reps)
    rx = re.compile("|".join(re.escape(x) + ("" if x.endswith('"') else r"(?![\w\-])") for x in sorted(rmap, key=len, reverse=True)))
    return lambda t: rx.sub(lambda m: rmap[m.group(0)], t)


def rw_bytes(f: Path, rw) -> bytes:
    b = f.read_bytes()
    if f.suffix.lower() not in FORK_TEXT or len(b) > 64 * 2 ** 20:
        return b
    try:
        return rw(b.decode("utf-8")).encode("utf-8")
    except UnicodeDecodeError:
        return b


def copy_rewritten(f: Path, dst: Path, rw) -> bool:
    """판 실행 파일을 반장 실행으로(글 파일은 경로를 바꿔서). 이미 같으면 안 씀 → 썼으면 True."""
    b = rw_bytes(f, rw)
    if dst.exists() and dst.stat().st_size == len(b) and dst.read_bytes() == b:
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if b is None or f.suffix.lower() not in FORK_TEXT:
        shutil.copy2(f, dst)
    else:
        dst.write_bytes(b)
    return True


def unit_opts(opts: dict, g: str) -> dict:
    return {**opts, "games": [g], "unit_games": None}


def drive_unit(U: Path, opts: dict, mc: int, until: str | None = None) -> dict:
    """판 실행 하나를 이 프로세스의 스레드에서 판 몫 끝(games_end)까지. 동시 자리(SLOT · CONC)는 모든 판 실행이 같이 씀 — 동시 수는 이 그래프 프로세스 하나가 셈.
    until(11-27) = 그 단계 앞에서 멈춤(따로 thread <판 실행>#upto_<단계> · 늘 새 입력 — 끝난 단계는 state.json 으로 건너뜀). 판 실행 앞부분(S4 · S5)만 먼저 돌려
    다음 판이 쓸 고친 기록(_prep/rec/<판>/paifu_rec.json)을 만들 때."""
    t0 = time.time()
    app, conn = build(U)
    cfg = {"configurable": {"thread_id": f"{U.name}#upto_{until}"}, "max_concurrency": mc, "recursion_limit": 5000} if until else cfg_of(U, mc)
    st0 = app.get_state(cfg)
    err, code = None, None
    try:
        if until:
            if not until_done(U, until):
                app.invoke({"run": posix(U), "opts": {**opts, "until": until}, "phase": "stage", "log": [], "max_conc": 0}, cfg, durability="sync")
        elif st0.values and not st0.next and (st0.values or {}).get("phase") == "games_end":
            pass   # 이미 끝난 판 실행
        elif st0.values:
            app.invoke(None, cfg, durability="sync")   # 끊긴 판 실행을 이어 감(마지막 저장부터 — 끝난 꾸러미 · 판은 결과 파일로 건너뜀)
        else:
            app.invoke({"run": posix(U), "opts": opts, "phase": "stage", "log": [], "max_conc": 0}, cfg, durability="sync")
    except ah.ApiStop as e:
        err, code = str(e)[:2000], "stop"
    except ah.ApiFail as e:
        err, code = str(e)[:2000], "error"
    except GraphError as e:
        err, code = str(e)[:2000], "error"
    except Exception as e:  # noqa: BLE001
        err, code = f"{type(e).__name__}: {e}"[:2000], "error"
        ev(U, "error", why=err, trace=traceback.format_exc()[-2000:])
    st = app.get_state(cfg)
    conn.close()
    phase = (st.values or {}).get("phase")
    if code is None and until:
        code = "until_end" if until_done(U, until) else ("read" if st.interrupts else "error")
        if code != "until_end":
            err = f"판 실행 앞부분이 {until} 앞에 안 닿음 — phase {phase} · 다음 마디 {list(st.next)} · interrupt {len(st.interrupts)}(판 실행은 replay · api 손만)"
    elif code is None:
        code = "games_end" if phase == "games_end" and not st.next else ("read" if st.interrupts else "error")
        if code != "games_end":
            err = f"판 실행이 판 몫 끝(games_end)에 안 닿음 — phase {phase} · 다음 마디 {list(st.next)} · interrupt {len(st.interrupts)}(판 실행은 replay · api 손만)"
    if err:
        ev(U, "unit_error", why=err, until=until)
    g = (opts.get("games") or ["?"])[0]
    gf = U / "games" / f"{g}.json"
    return {"game": g, "run": rp(U), "status": code, "why": err, "s": round(time.time() - t0, 1), "fills": fills_summary(U),
            **({"until": until} if until else {}),
            "game_file": rp(gf) if gf.exists() else None, "game_status": pa.jl(gf)["status"] if gf.exists() else None,
            **({"api": ah.usage_summary(gdir(U))} if (gdir(U) / "api_usage.jsonl").exists() else {})}


# 11-27 판 실행끼리 이어지는 것(설계서 8-23 · r_unit_audit M1): 판 실행의 S6a 준비 창 시작(prev_last_ms)은 반장 판 순서의 앞 판 고친 기록
# _prep/rec/<앞 판>/paifu_rec.json(앞 판 S5 결과)의 마지막 버림 시각(paifu_auto.unit_prev_last). 끝난 실행을 fork --at S4 한 반장은 옛 실행의 그 파일이
# 베껴져 있어 판 실행에도 있지만, 처음 시작한 반장(공통 앞 단계만 돈 것)에는 없다 → 없으면 앞 판 판 실행을 S5 까지(S6a 앞) 먼저 돌려 그 파일을 넣는다.
UNIT_PRE_UNTIL = "S6a"


def rec_rel(g: str) -> str:
    return f"_prep/rec/{g}/paifu_rec.json"


def prev_rec_need(U: Path, g: str, allg: list):
    """판 실행 U(판 g)의 S6a 가 쓸 앞 판 고친 기록 — unit_prev_last 와 같은 길로 앞 판을 거꾸로 봄: 기록이 있고 버림 시각이 있으면 None(채워짐),
    기록이 없는 판을 먼저 만나면 그 판(채워야 함). 앞 판이 없거나 다 버림이 없으면 None."""
    for pg in reversed(allg[:allg.index(g)] if g in allg else []):
        f = U / rec_rel(pg)
        if not f.exists():
            return pg
        if any(e["type"] == "discard" and e.get("at") is not None for e in pa.jl(f)["events"]):
            return None
    return None


def rec_source(run: Path, pg: str):
    """앞 판 고친 기록의 출처: 반장 실행(조립 · 옛 fork 사본) → 그 판의 판 실행(S5 가 끝난 것). 없으면 None."""
    if (run / rec_rel(pg)).exists():
        return run, run / rec_rel(pg)
    V = unit_dir(run, pg)
    if (V / "state.json").exists() and (pa.jl(V / "state.json")["stages"].get("S5") or {}).get("status") == "done" and (V / rec_rel(pg)).exists():
        return V, V / rec_rel(pg)
    return None


def unit_setup(run: Path, g: str, opts: dict, a, made: dict):
    """판 실행 폴더 준비 — 없으면 반장 실행을 --at S4 로 베끼고(state 의 판만 좁힘) graph.json · api 설정."""
    U = unit_dir(run, g)
    if not U.exists():
        fo = fork_run(run, U, "S4")
        made[g] = {"fork_s": fo["s"], "rewritten": fo["rewritten"]}
    if not has_thread(U):
        games_setup(U, [g])
        uo = unit_opts(opts, g)
        gdir(U).mkdir(parents=True, exist_ok=True)
        set_api(U, uo, a)
        pa.wj(gdir(U) / "graph.json", {"_note": "paifu_graph.py 판 실행(설계서 8-23 실행도 판 단위) — 반장 실행 go --games 가 만듦", "at": now(), **uo,
                                      "thread_id": U.name, "db": rp(U / DB), "unit_of": rp(run)})
        ev(U, "go", **uo, unit_of=rp(run))
    else:
        set_api(U, pa.jl(gdir(U) / "graph.json"), a)


def fill_prev_recs(run: Path, games: list, opts: dict, a, mc: int, par: int, made: dict) -> tuple:
    """판 실행마다 S6a 앞에 앞 판 고친 기록을 채움(없는 앞 판은 그 판 실행을 S6a 앞까지 먼저 — 나란히). → (넣은 것, 앞부분 실행 결과, 못 채운 판 {판: 까닭})."""
    from concurrent.futures import ThreadPoolExecutor
    allg = list(pa.Run(run).state["game_ids"])
    put, pre_res, blocked = {}, {}, {}
    for _ in range(len(allg)):
        need = {}
        for g in games:
            U = unit_dir(run, g)
            if g in blocked or (pa.jl(U / "state.json")["stages"].get("S6a") or {}).get("status") == "done":
                continue
            pg = prev_rec_need(U, g, allg)
            if pg:
                need[g] = pg
        if not need:
            break
        todo = sorted({pg for pg in need.values() if rec_source(run, pg) is None and pg not in pre_res}, key=allg.index)
        if todo:
            for pg in todo:
                unit_setup(run, pg, opts, a, made)
            ev(run, "unit_pre", games=todo, why="앞 판 고친 기록(S5) — 다음 판 S6a 준비 창", until=UNIT_PRE_UNTIL)
            with ThreadPoolExecutor(max_workers=max(1, min(par, len(todo)))) as ex:
                futs = {pg: ex.submit(drive_unit, unit_dir(run, pg), unit_opts(opts, pg), mc, UNIT_PRE_UNTIL) for pg in todo}
                for pg, fu in futs.items():
                    pre_res[pg] = fu.result()
        for g, pg in need.items():
            src = rec_source(run, pg)
            if src is None:
                why = (pre_res.get(pg) or {}).get("why") or "출처 없음"
                blocked[g] = f"앞 판 {pg} 의 고친 기록({rec_rel(pg)})을 못 만듦 — 앞 판 판 실행 앞부분(S4 · S5): {(pre_res.get(pg) or {}).get('status')} · {why}"
                continue
            U = unit_dir(run, g)
            copy_rewritten(src[1], U / rec_rel(pg), path_rewriter(src[0], U))
            put[g] = put.get(g, []) + [{"prev": pg, "from": rp(src[1])}]
            ev(U, "prev_rec", prev=pg, src=rp(src[1]))
    return put, pre_res, blocked


def run_units(run: Path, games: list, opts: dict, a, mc: int, par: int) -> dict:
    """판 실행들: 없으면 반장 실행을 --at S4 로 베껴 판 실행 폴더를 만들고(state 의 판만 좁힘) 나란히(par 개씩) 판 몫 단계를 돌림.
    11-27: 앞 판 고친 기록이 없는 판 실행은 먼저 앞 판 판 실행을 S6a 앞까지 돌려 그 기록을 넣음(fill_prev_recs — fork 로 만든 반장은 이미 있어 안 거침)."""
    made = {}
    for g in games:
        unit_setup(run, g, opts, a, made)
    reg = pa.jl(units_file(run)) if units_file(run).exists() else {"_note": "반장 실행의 판 실행 목록(paifu_graph go --games — 설계서 8-23)", "units": {}}
    for g in games:
        reg["units"][g] = rp(unit_dir(run, g))
    pa.wj(units_file(run), reg)
    SLOT["units"] = True
    from concurrent.futures import ThreadPoolExecutor
    t0 = time.time()
    put, pre_res, blocked = fill_prev_recs(run, games, opts, a, mc, par, made)
    t_pre = round(time.time() - t0, 1)
    res = {g: {"game": g, "run": rp(unit_dir(run, g)), "status": "error", "why": blocked[g], "s": 0.0} for g in games if g in blocked}
    go_g = [g for g in games if g not in blocked]
    if go_g:
        with ThreadPoolExecutor(max_workers=max(1, min(par, len(go_g)))) as ex:
            futs = {g: ex.submit(drive_unit, unit_dir(run, g), unit_opts(opts, g), mc) for g in go_g}
            for g, fu in futs.items():
                res[g] = fu.result()
    res = {g: res[g] for g in games}
    SLOT["units"] = False
    out = {"units": res, "forked": made, "s": round(time.time() - t0, 1), "conc_max": CONC["max"], "unit_parallel": par,
           **({"prev_rec": put, "pre_units": pre_res, "pre_s": t_pre} if (put or pre_res) else {})}
    reg = pa.jl(units_file(run))
    for pg in pre_res:
        reg["units"].setdefault(pg, rp(unit_dir(run, pg)))
    reg.setdefault("runs", []).append({"at": now(), "games": games, "status": {g: v["status"] for g, v in res.items()}, "s": out["s"], "conc_max": CONC["max"],
                                       "max_concurrency": mc, "unit_parallel": par,
                                       **({"pre_units": {pg: v["status"] for pg, v in pre_res.items()}, "pre_s": t_pre, "prev_rec": put} if (put or pre_res) else {})})
    pa.wj(units_file(run), reg)
    ev(run, "units", games=games, status={g: v["status"] for g, v in res.items()}, s=out["s"], conc_max=CONC["max"],
       pre_units={pg: v["status"] for pg, v in pre_res.items()} or None)
    return out


# ------------------------------------------------------------------ 명령
def cmd_start(rest: list):
    p = subprocess.run([PY, "-X", "utf8", str(RUN_PY), "start", *rest], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    sys.stdout.write(p.stdout)
    if p.stderr:
        sys.stderr.write(p.stderr)
    raise SystemExit(p.returncode)


def games_setup(run: Path, games: list):
    """판 실행 폴더(8-23 "실행도 판 단위")의 state.json game_ids 를 그 판으로 좁힘. hanchan.json 은 그대로 둔다(11-26 밤 — 좁히면 hanchan_cfg 겹침 검사 ④ 가
    같은 반장의 다른 설정과 판 id 가 겹친다고 멈춤(sv6g)). paifu_auto 는 state.game_ids(r.games())로 돌고, 반장 한 파일을 쓰는 han3 명령(rturns · rcheck · link)에는
    판 실행이면 판을 인자로 줌. state.unit = {games, all_games} — 반장 전체 판 순서가 필요한 곳(강 · 울기 상자 dump_regions · 앞 판 마지막 버림 prev_last ·
    S5 아래 자리)에서 씀(paifu_auto.unit_on · all_games · unit_prev_last). 원래 값은 graph/games_only.json."""
    r = pa.Run(run)
    if r.state is None:
        emit({"run": rp(run), "why": "--games: state.json 이 없음 — fork --at S4 로 만든 실행에서"}, "stop")
    allg = list(r.state["game_ids"])
    bad = [g for g in games if g not in allg]
    if bad:
        emit({"run": rp(run), "why": f"--games: 이 실행에 없는 판 {bad}"}, "stop")
    f = gdir(run) / "games_only.json"
    if not f.exists():
        hc = pa.jl(r.cfg_f)
        pa.wj(f, {"_note": "paifu_graph go --games — 판 실행으로 좁히기 전 값", "at": now(), "games": games, "orig_game_ids": allg, "orig_cfg_games": hc.get("games"),
                  "orig_handtrack_games": (hc.get("handtrack") or {}).get("games")})
        r.state["game_ids"] = [g for g in allg if g in games]
        r.state["unit"] = {"games": list(r.state["game_ids"]), "all_games": allg, "note": "paifu_graph go --games(설계서 8-23 판 실행)"}
        r.state["events"].append({"at": now(), "games_only": games})
        r.save()


def cmd_go(a):
    run = absp(a.run)
    if a.max_concurrency > MC_MAX or a.max_concurrency < 1:
        emit({"run": rp(run), "why": f"--max-concurrency {a.max_concurrency} — 1 ~ {MC_MAX} 만(8-20)"}, "stop")
    if a.hands == "replay" and not a.replay_from:
        emit({"run": rp(run), "why": "--hands replay 에는 --replay-from 이 있어야 함"}, "stop")
    if a.hands != "api" and (a.api_games or a.reuse_api_from or a.api_fake or a.i_mean_it or a.max_usd is not None):
        emit({"run": rp(run), "why": "--api-games · --reuse-api-from · --api-fake · --i-mean-it · --max-usd 는 --hands api 에서만"}, "stop")
    if a.hands == "api" and (a.api_games or a.api_fake) and not a.replay_from:
        emit({"run": rp(run), "why": "--api-games(나머지는 재생) · --api-fake(재생 답을 씀) 에는 --replay-from 이 있어야 함"}, "stop")
    if a.reuse_api_from and not absp(a.reuse_api_from).is_dir():
        emit({"run": rp(run), "why": f"--reuse-api-from 폴더 없음: {a.reuse_api_from}"}, "stop")
    if not (run / prun.RUNNER).exists():
        emit({"run": rp(run), "why": f"{prun.RUNNER} 이 없음 — start 먼저"}, "error")
    if a.layout == "game" and a.session_stages and "S7s" in a.session_stages.split(","):
        emit({"run": rp(run), "why": "--layout game 의 판 LLM · 판 다시 읽기는 session 손을 아직 못 씀 — --layout manager 로"}, "stop")
    if a.layout == "game" and a.hands == "session":
        emit({"run": rp(run), "why": "--layout game 에서 --hands session 은 아직 안 됨(판 LLM 은 replay · api 만) — --layout manager 로"}, "stop")
    for x in (a.reuse_from or "").split(","):
        if x and not absp(x).is_dir():
            emit({"run": rp(run), "why": f"--reuse-from 폴더 없음: {x}"}, "stop")
    thread = run.name
    if has_thread(run):
        if not a.again:
            emit({"run": rp(run), "why": f"이미 go 한 실행(그래프 기록 {rp(run / DB)} · thread {thread_of(run)}) — 이어 가려면 resume(또는 go --again: 새 thread 로 처음부터 — 끝난 꾸러미 · 판은 결과 파일만 보고 건너뜀)"}, "stop")
        k = 1
        while True:
            thread = f"{run.name}#again{k}"
            app0, c0 = build(run)
            have = bool(app0.get_state({"configurable": {"thread_id": thread}}).values)
            c0.close()
            if not have:
                break
            k += 1
    set_test(a)
    games_only = [x for x in (a.games or "").split(",") if x]
    if games_only and a.layout != "game":
        emit({"run": rp(run), "why": "--games(판 실행)는 --layout game 에서만"}, "stop")
    if games_only and (run / "state.json").exists() and (pa.Run(run).state or {}).get("unit"):
        emit({"run": rp(run), "why": "--games: 이 폴더는 판 실행 폴더 — 반장 실행 폴더에 go --games 를 걸 것"}, "stop")
    opts = {"hands": a.hands, "replay_from": rp(absp(a.replay_from)) if a.replay_from else None,
            "replay_sup_from": rp(absp(a.replay_sup_from)) if a.replay_sup_from else None, "before_user": bool(a.before_user),
            "max_concurrency": a.max_concurrency, "session_stages": [x for x in (a.session_stages or "").split(",") if x],
            "api_games": [x for x in a.api_games.split(",") if x] if a.api_games else None,
            "reuse_api_from": rp(absp(a.reuse_api_from)) if a.reuse_api_from else None, "api_fake": a.api_fake or None,
            "layout": a.layout, "again": bool(a.again), "games": None, "unit_games": games_only or None,
            "reuse_from": [rp(absp(x)) for x in (a.reuse_from or "").split(",") if x],
            "test_touch_task": [x for x in (a.test_touch_task or "").split(",") if x],
            "confirm": a.confirm}
    gdir(run).mkdir(parents=True, exist_ok=True)
    pre_o = None
    if games_only and not prefix_done(run):   # 11-27: 처음 시작한 반장 — 공통 앞 단계(S0 ~ S3)를 먼저 그래프로 돌리고 S4 앞에서 멈춘 뒤 판 실행으로
        pre_o = drive_prefix(run, opts, a, a.max_concurrency, "python -X utf8 experiments/paifu_frames/paifu_graph.py " + " ".join(sys.argv[1:]))
    if games_only:
        r0 = pa.Run(run)
        if r0.state is None:
            emit({"run": rp(run), "why": "--games: state.json 이 없음(공통 앞 단계 뒤에도)"}, "error")
        allg0 = list(r0.state["game_ids"])
        if games_only == ["all"]:
            games_only = allg0
        bad = [g for g in games_only if g not in allg0]
        if bad:
            emit({"run": rp(run), "why": f"--games: 이 실행에 없는 판 {bad}"}, "stop")
        opts["unit_games"] = games_only
    r_u = pa.Run(run) if (run / "state.json").exists() else None
    if not games_only and r_u is not None and r_u.state and r_u.state.get("unit"):   # 11-26 밤: 판 실행 폴더(fork --at S7s 등으로 만든 것)에 바로 go — 그 판 몫 끝에서 멈춤
        if a.layout != "game":
            emit({"run": rp(run), "why": "판 실행 폴더는 --layout game 만"}, "stop")
        opts["games"] = list(r_u.state["unit"]["games"])
    if games_only:   # 8-23 실행도 판 단위: 판 실행(판마다 폴더 하나 · 나란히) → 모든 판이 판 몫 끝에 닿았으면 반장 조립 → 반장 마무리
        SLOT["sem"] = threading.BoundedSemaphore(a.max_concurrency)
        ev(run, "go_units", **opts, unit_parallel=a.unit_parallel, hand_delay=TEST["hand_delay"], die_after=TEST["die_after"])
        uo = run_units(run, games_only, opts, a, a.max_concurrency, a.unit_parallel)
        reg = pa.jl(units_file(run))
        ok_all = {g: unit_dir(run, g) for g in allg0 if (unit_dir(run, g) / "state.json").exists()
                  and (pa.jl(unit_dir(run, g) / "state.json").get("stages", {}).get("S7s") or {}).get("status") == "done"}
        bad_u = {g: v for g, v in uo["units"].items() if v["status"] != "games_end"}
        base = {"run": rp(run), "units": uo["units"], "unit_parallel": a.unit_parallel, "max_concurrency": a.max_concurrency, "conc_max": uo["conc_max"],
                "units_s": uo["s"], "registry": rp(units_file(run)), "prefix": pre_o, **{k: uo[k] for k in ("prev_rec", "pre_units", "pre_s") if k in uo}}
        if bad_u:
            emit({**base, "why": f"판 실행이 판 몫 끝에 못 닿음 {sorted(bad_u)} — 까닭은 units.<판>.why",
                  "next": f"고친 뒤 같은 명령(끝난 판 실행은 건너뜀): python -X utf8 experiments/paifu_frames/paifu_graph.py go --run {rp(run)} --games {a.games} …"},
                 "stop" if any(v["status"] == "stop" for v in bad_u.values()) else "error")
        if len(ok_all) < len(allg0) or a.no_assemble:
            emit({**base, "games_only": games_only, "assembled": False,
                  "why": "판 실행만(--games) — 판 몫 단계 끝(판마다 <판 실행>/games/<판>.json), 반장 조립 · 마무리(S5 반장 · S8 · S9 · 확인)는 모든 판 실행이 끝난 뒤"
                         + (f"(아직 없는 판 {[g for g in allg0 if g not in ok_all]})" if len(ok_all) < len(allg0) else "(--no-assemble)")}, "done")
        if has_thread(run):
            emit({**base, "why": f"반장 실행에 이미 그래프 기록이 있음({rp(run / DB)}) — 조립은 한 번만. 이어 가려면 resume"}, "stop")
        try:
            asm = assemble(run, ok_all)
        except GraphError as e:
            emit({**base, "why": f"반장 조립 실패 — {e}"}, "error")
        ev(run, "assembled", units=len(ok_all), unhandled=asm["unhandled"])
        pa.wj(gdir(run) / "graph.json", {"_note": "paifu_graph.py go 설정(설계서 8-20 · 8-23) — 반장 실행(판 실행 조립 뒤 마무리)", "at": now(), **opts,
                                       "thread_id": thread, "db": rp(run / DB), "units": {g: rp(v) for g, v in ok_all.items()}})
        set_api(run, opts, a)
        SLOT["units"] = False
        drive(run, {"run": posix(run), "opts": opts, "phase": "stage", "log": [], "max_conc": 0}, a.max_concurrency)
    set_api(run, opts, a)
    pa.wj(gdir(run) / "graph.json", {"_note": "paifu_graph.py go 설정(설계서 8-20 · 8-23)", "at": now(), **opts, "thread_id": thread, "db": rp(run / DB)})
    ev(run, "go", **opts, hand_delay=TEST["hand_delay"], die_after=TEST["die_after"])
    drive(run, {"run": posix(run), "opts": opts, "phase": "stage", "log": [], "max_conc": 0}, a.max_concurrency)


def cmd_resume(a):
    run = absp(a.run)
    if not (run / DB).exists():
        emit({"run": rp(run), "why": "그래프 기록이 없음 — go 먼저"}, "error")
    set_test(a)
    app, conn = build(run)
    st = app.get_state(cfg_of(run, MC_DEFAULT))
    if not st.values:
        emit({"run": rp(run), "why": "그래프 기록이 비었음 — go 먼저"}, "error")
    mc = st.values["opts"]["max_concurrency"]
    set_api(run, st.values["opts"], a)
    ev(run, "resume", answers=a.answers, interrupts=len(st.interrupts), next=list(st.next), hand_delay=TEST["hand_delay"], die_after=TEST["die_after"])
    if st.interrupts:
        res = {}
        for i in st.interrupts:
            if i.value.get("why") == "page":
                if not a.answers and not (run / "answers_user.json").exists():
                    emit({"run": rp(run), "why": "확인 페이지 멈춤 — --answers <답 파일> 이 있어야 함(또는 <실행>/answers_user.json)"}, "stop")
                res[i.id] = {"answers": rp(absp(a.answers)) if a.answers else None}
            else:
                res[i.id] = {"filled": True}
        conn.close()
        drive(run, Command(resume=res), mc)
    if not st.next:
        conn.close()
        r = runner(run)
        emit({**out_view(run, st), "finished": r.o.get("finished"), "why": "그래프가 이미 끝남"}, "done")
    conn.close()
    drive(run, None, mc)   # 죽은 뒤 이어 감 — 마지막 저장(superstep)부터


# ------------------------------------------------------------------ fork — 끝난 실행을 베껴 어느 단계부터만 다시(11-26 사용자: 코드 단계는 같은 입력이면 같은 출력)
FORK_ALWAYS_SKIP = {"graph.sqlite", "graph.sqlite-shm", "graph.sqlite-wal", "graph", "mgr", "confirm", "runner", "logs", "pending.json",
                    "answers_user.json", "questions.jsonl", "questions_hidden.jsonl", "samples.jsonl", "report.md"}
FORK_STAGE_SKIP = {"S4": ["s4"], "S6a": ["s6a"], "S6": ["read", "turns"], "S7s": ["sup", "agent", "games"], "S8": ["paifu"],
                   "S9": ["paifu_source", "_impact"]}   # 11-26 밤: paifu/ 는 S8 결과 — 옛 표는 S9 에 두어 fork --at S9 가 S8 패보를 안 베껴 S9 가 깨짐(sv1u)   # 그 단계부터 다시면 안 베낌(꾸러미 답 · 결과)
FORK_TEXT = {".json", ".jsonl", ".md", ".txt", ".csv", ".yaml", ".yml"}


def cmd_fork(a):
    try:
        if a.games:
            o = fork_hanchan_units(absp(a.src), absp(a.run), a.at, a.games)
        else:
            o = fork_run(absp(a.src), absp(a.run), a.at)
    except GraphError as e:
        emit({"run": rp(absp(a.run)), "why": str(e)}, "stop")
    emit(o, "done")


def fork_hanchan_units(src: Path, dst: Path, at: str, games_arg: str) -> dict:
    """fork --from <반장 실행> --at <단계> --games <판>[,…]|all --run <새 반장 실행>(11-26 밤): 새 반장 실행 = 반장 실행을 --at S4 로 베낌(go --games 가 판 실행을
    만들 때와 같은 자리) + 판마다 <옛 반장>__<판> 판 실행을 <단계> 에서 <새 반장>__<판> 으로 베낌(판 좁히기 유지 · 글 안 옛 반장 경로도 새 반장으로).
    그다음 go --run <새 반장> --games <판> … 이 그 판 실행을 그 단계부터만 돌림(판 실행 폴더가 이미 있으면 go 는 새로 베끼지 않음)."""
    if dst.exists():
        raise GraphError("새 반장 실행 폴더가 이미 있음 — 다른 이름으로")
    r0 = pa.Run(src)
    if r0.state is None or r0.state.get("unit"):
        raise GraphError(f"--games: --from 은 반장 실행(판 실행 폴더 옆의 <반장>)이어야 함 — {rp(src)}")
    allg = list(r0.state["game_ids"])
    games = allg if games_arg == "all" else [x for x in games_arg.split(",") if x]
    bad = [g for g in games if g not in allg or not (unit_dir(src, g) / "state.json").exists()]
    if bad:
        raise GraphError(f"--games: 판 실행 폴더가 없는 판 {bad}(있어야 할 곳 {rp(unit_dir(src, '<판>'))})")
    clash = [rp(unit_dir(dst, g)) for g in games if unit_dir(dst, g).exists()]
    if clash:
        raise GraphError(f"새 판 실행 폴더가 이미 있음 {clash}")
    out = {"status": "done", "run": rp(dst), "from": rp(src), "at": at, "games": games, "hanchan": None, "units": {}}
    out["hanchan"] = {k: v for k, v in fork_run(src, dst, "S4").items() if k in ("at", "redo_stages", "rewritten", "old_name_left_count", "s")}
    for g in games:
        o = fork_run(unit_dir(src, g), unit_dir(dst, g), at, extra_reps=[(src, dst)])
        out["units"][g] = {k: v for k, v in o.items() if k in ("run", "from", "at", "redo_stages", "rewritten", "old_name_left_count", "kept_unit", "forked_costs", "s")}
    out["next"] = (f"python -X utf8 experiments/paifu_frames/paifu_graph.py go --run {rp(dst)} --games {','.join(games) if games_arg != 'all' else 'all'} "
                   f"--hands <replay|api> …(판 실행은 {at} 부터만)")
    return out


def fork_run(src: Path, dst: Path, at: str, extra_reps: list | None = None) -> dict:
    """fork --from <실행> --at <단계> --run <새 실행>: 끝까지(또는 그 단계 뒤까지) 돈 실행 폴더를 베끼고 state 를 <단계> 부터 todo 로 되감음(paifu_auto next --redo 와 같은 되감기 —
    돌리지는 않음). 안 베끼는 것: 그래프 기록(graph.sqlite · graph/) · 관리자(mgr/) · 확인 쪽(confirm/ · runner/ · questions* · samples · answers_user · report.md) · logs/ ·
    <단계> 와 뒤 단계의 꾸러미 · 결과 폴더(FORK_STAGE_SKIP). 글 파일(json · jsonl · md · txt · csv · yaml) 안의 옛 실행 경로는 새 실행 경로로 바꿈(옛 폴더에 쓰지 않게).
    runner.json 은 확인 차례 · 끝 표시를 비움. 원본은 읽기만. 그다음 go 로 이어 감(예: --hands api --i-mean-it)."""
    if not (src / "state.json").exists() or not (src / prun.RUNNER).exists():
        raise GraphError(f"--from {rp(src)}: state.json · {prun.RUNNER} 가 있는 실행 폴더가 아님")
    if dst.exists():
        raise GraphError("새 실행 폴더가 이미 있음 — 다른 이름으로")
    sr = pa.Run(src)
    stl = pa.stage_list(sr)
    if at not in stl:
        raise GraphError(f"--at {at}: 이 실행의 단계가 아님({stl})")
    if (sr.state["stages"].get(stl[stl.index(at) - 1]) or {}).get("status") != "done" if stl.index(at) > 0 else False:
        raise GraphError(f"원본에서 {at} 앞 단계가 안 끝남 — 베낄 수 없음")
    later = stl[stl.index(at):]
    skip = set(FORK_ALWAYS_SKIP)
    for s in later:
        skip.update(FORK_STAGE_SKIP.get(s, []))
    t0 = time.time()
    shutil.copytree(src, dst, ignore=lambda d, names: [n for n in names if Path(d).resolve() == src and n in skip])
    reps = [(src.as_posix(), dst.as_posix()), (str(src), str(dst)), (str(src).replace("\\", "\\\\"), str(dst).replace("\\", "\\\\")), (rp(src), rp(dst)),
            (f'"{src.name}"', f'"{dst.name}"')]   # 반장 설정 id 처럼 실행 이름만 든 칸
    for s2, d2 in extra_reps or []:   # 판 실행을 새 반장 옆으로 베낄 때: 글 안의 옛 반장 경로도 새 반장으로(옛 반장은 읽기만)
        s2, d2 = Path(s2).resolve(), Path(d2).resolve()
        reps += [(s2.as_posix(), d2.as_posix()), (str(s2), str(d2)), (str(s2).replace("\\", "\\\\"), str(d2).replace("\\", "\\\\")), (rp(s2), rp(d2)),
                 (f'"{s2.name}"', f'"{d2.name}"')]
    rmap = dict(reps)
    rx_rep = re.compile("|".join(re.escape(x) + ("" if x.endswith('"') else r"(?![\w\-])") for x in sorted(rmap, key=len, reverse=True)))
    n_txt = n_rew = 0
    for f in dst.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in FORK_TEXT or f.stat().st_size > 64 * 2 ** 20:
            continue
        n_txt += 1
        b = f.read_bytes()
        try:
            t = b.decode("utf-8")
        except UnicodeDecodeError:
            continue
        t2 = rx_rep.sub(lambda m: rmap[m.group(0)], t)   # 한 번에(11-26 밤: 차례로 바꾸면 새 이름이 옛 이름을 품을 때(<실행>__<판>) 두 번 바뀜 — sv8)
        if t2 != t:
            st_ = f.stat()
            f.write_bytes(t2.encode("utf-8"))
            os.utime(f, ns=(st_.st_atime_ns, st_.st_mtime_ns))   # 11-26 밤: 경로만 바꾼 파일은 원래 시각 그대로(copy2 와 같음) — 판 실행 조립이 시각으로 "판 실행이 만든 파일" 을 가름
            n_rew += 1
    # 8-23 구현 중 찾은 fork 틈: read/ 를 베끼는 fork(--at S7 · S7s · S8 · S9)는 원본에서 뒤 단계가 바꾼 답을 그대로 가져왔다 — 되돌림.
    #   사용자 답(apply)은 늘 되돌림(answer_before_apply → answer · result_read_before_apply → result_read · state.answered 비움),
    #   S7 · S7s 를 다시 돌면 S7 다시 읽기 · 판 supervisor done 이 바꾼 답도(answer_r0 → answer, sup.json 지움).
    restored = Counter()
    for f in sorted(dst.glob("read/*/answer_before_apply.json")):
        os.replace(f, f.with_name("answer.json"))
        restored["answer_before_apply"] += 1
    for f in sorted(dst.glob("*/result_read_before_apply.json")):
        os.replace(f, f.with_name("result_read.json"))
        restored["result_read_before_apply"] += 1
    if "S7" in later or "S7s" in later:
        for f in sorted(dst.glob("read/*/answer_r0.json")):
            os.replace(f, f.with_name("answer.json"))
            restored["answer_r0"] += 1
        for f in sorted(dst.glob("read/*/sup.json")):
            f.unlink()
            restored["sup.json"] += 1
    # 8-23 결과 파일: 다시 돌 단계의 순 시도 파일은 지움(S7 → s7r* · S7s → r* · 늘 user), 앞 단계 손 기록(fills · pkg_inputs)은 그 단계 줄만 옮김
    forked_costs = Counter()
    for f in sorted(dst.glob("turns/*/*.json")):
        if f.stem == "user" or ("S7s" in later and re.match(r"^r\d+$", f.stem)) or ("S7" in later and f.stem.startswith("s7r")):
            f.unlink()
            continue
        # 11-26 밤: 베낀 순 결과 파일의 돈은 이 실행이 쓴 돈이 아님 — 옛 돈은 source.orig_usd 로 기록만(판 결과 cost_total 이 베낀 돈으로 셈)
        try:
            d = pr.jl(f)
        except (json.JSONDecodeError, OSError):
            continue
        if d.get("schema") == pr.SCHEMA_TURN and isinstance(d.get("cost"), dict) and not d["cost"].get("reused"):
            d["source"]["orig_usd"] = float(d["cost"].get("usd") or 0)
            d["source"]["forked_from"] = rp(src)
            d["cost"] = pr.zero_cost(True)
            pr.wj(f, d)
            forked_costs["turn_files"] += 1
            forked_costs["usd"] = round(forked_costs["usd"] + d["source"]["orig_usd"], 6)
    for nm in ("fills.jsonl", "pkg_inputs.jsonl"):
        L = [x for x in log_lines(src / "graph" / nm) if x.get("stage") not in later and x.get("stage") not in ("sup_reread", "manager")]
        for x in L:
            x["forked_from"] = rp(src)
            append(gdir(dst) / nm, x)
    r = pa.Run(dst)
    if restored.get("answer_before_apply") or restored.get("result_read_before_apply"):
        for k in ("answered", "user_answers", "user_final"):
            r.state.pop(k, None)
    for s in later:
        r.state["stages"][s] = {"status": "todo"}
        r.state["timing"].pop(s, None)
    kept_unit = bool(r.state.get("unit")) and at != "S4"
    if kept_unit:   # 11-26 밤: 판 실행 폴더를 S4 뒤에서 베끼면 판 실행 그대로(state.unit · graph/games_only.json 유지) — 이어서 go(그 판 몫 끝에서 멈춤) 또는 새 반장의 go --games
        gq = src / "graph" / "games_only.json"
        if gq.exists():
            gdir(dst).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(gq, gdir(dst) / "games_only.json")
    else:
        r.state.pop("unit", None)   # 판 실행을 S4 에서 베끼면 좁힌 것은 안 가져감(go --games 가 다시 좁힘)
    r.state["events"].append({"at": now(), "fork": {"from": rp(src), "at": at, **({"unit_kept": True} if kept_unit else {})}})
    r.save()
    ro = json.loads((dst / prun.RUNNER).read_text(encoding="utf-8"))
    ro.update(rounds=[], finished=None, forked={"from": rp(src), "at": at, "made": now()})
    pa.wj(dst / prun.RUNNER, ro)
    left = sorted(str(p.relative_to(dst)) for p in dst.rglob("*") if p.is_file() and p.suffix.lower() in FORK_TEXT and p.stat().st_size <= 64 * 2 ** 20
                  and re.search(rf"(?<![\w\-]){re.escape(src.name)}(?![\w\-])", p.read_bytes().decode("utf-8", errors="replace")))
    return {"status": "done", "run": rp(dst), "from": rp(src), "at": at, "redo_stages": later, "skipped": sorted(skip), "text_files": n_txt, "rewritten": n_rew,
            "old_name_left_in": left[:30], "old_name_left_count": len(left), "restored": dict(restored), "kept_unit": kept_unit,
            "forked_costs": dict(forked_costs), "s": round(time.time() - t0, 1),
            "next": f"python -X utf8 experiments/paifu_frames/paifu_graph.py go --run {rp(dst)} --hands <replay|session|api> …"}


def cmd_status(a):
    run = absp(a.run)
    if not (run / DB).exists():
        emit({"run": rp(run), "why": "그래프 기록이 없음"}, "error")
    app, conn = build(run)
    st = app.get_state(cfg_of(run, MC_DEFAULT))
    r = runner(run)
    emit({**out_view(run, st), "next_nodes": list(st.next), "interrupts": [{"why": i.value.get("why"), "id": (i.value.get("pkg") or {}).get("id")} for i in st.interrupts],
          "runner_rounds": [prun.round_view(r, x) for x in r.o["rounds"]], "finished": r.o.get("finished")}, "done")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "start":
        cmd_start(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] in ("_next_upto", "_next_prefix"):   # 안쪽 하위 명령(n_stage 가 부름 — until 앞 단계를 한 단계씩)
        next_upto_main(sys.argv[2:])
    ap = argparse.ArgumentParser(description="대국 뒤 자동 패보 — LangGraph 그래프(설계서 8-20)")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("start", help="paifu_run.py start 와 같은 인자(그것을 부름)")
    p = sp.add_parser("go")
    p.add_argument("--run", required=True)
    p.add_argument("--hands", required=True, choices=HANDS)
    p.add_argument("--replay-from")
    p.add_argument("--replay-sup-from", help="관리자 재생 출처(판 supervisor 꾸러미 sup/<판>/ 이 있는 실행 — 없으면 --replay-from)")
    p.add_argument("--before-user", action="store_true")
    p.add_argument("--max-concurrency", type=int, default=MC_DEFAULT)
    p.add_argument("--session-stages", help="시험용: 이 단계 꾸러미만 session 손(쉼표, S7s = 관리자 결정 · 판 supervisor 다시 읽기) — 나머지는 --hands")
    p.add_argument("--api-games", help="api 손: 이 판(쉼표)의 꾸러미만 api, 나머지는 replay(--replay-from). manager 를 적으면 관리자 꾸러미도 api")
    p.add_argument("--reuse-api-from", help="api 손: 앞 실행에서 api 손이 채운 같은 자리 꾸러미(TASK.md 가 실행 폴더 경로만 빼고 같음)는 답을 베낌 — 돈 0")
    p.add_argument("--api-fake", help="api 손 시험: 가짜 클라이언트(replay 또는 replay:out=<호출마다 출력 토큰>[,game=test][,rr=alt]) — API 0")
    p.add_argument("--again", action="store_true", help="이미 go 한 실행을 새 thread 로 처음부터 다시 걸기 — 끝난 꾸러미 · 판은 결과 파일(답 · decision · turns · games)만 보고 건너뜀")
    p.add_argument("--games", help="8-23 판 실행: 이 판(쉼표 · all)마다 판 실행 폴더(<실행>__<판> — 이 반장 실행을 --at S4 로 베끼고 state 의 판만 좁힘)를 "
                                    "만들어 나란히 판 몫 단계(S4 → S5 판 몫 → S6a → S6b → S6 → S7 → 판 LLM)를 돌리고 <판 실행>/games/<판>.json 에서 멈춤. "
                                    "모든 판의 판 실행이 끝났으면 반장 조립(판 몫 파일 · 반장 한 파일의 판 줄 · state 합침) → 반장 S5(판 사이 이어지는 값) → S8 · S9 → 확인. "
                                    "반장 공통 앞 단계(S0 ~ S3)가 안 끝난 실행(start 만 한 것)이면 먼저 그것을 그래프(thread <실행>#prefix)로 돌려 S4 앞에서 멈춘 뒤 "
                                    "판 실행으로(11-27, 끊기면 같은 명령) · fork --at S4 로 만든 실행은 바로 판 실행")
    p.add_argument("--unit-parallel", type=int, default=UNIT_PAR_DEFAULT, help="--games: 판 실행을 동시에 몇 개(계산 단계가 무거움 — 기본 3). LLM 동시 수는 --max-concurrency 하나가 모든 판 실행에 걸쳐 셈")
    p.add_argument("--no-assemble", action="store_true", help="--games: 모든 판이 끝나도 반장 조립 · 마무리를 안 함")
    p.add_argument("--layout", choices=LAYOUTS, default="game", help="game = 판마다 판 LLM(8-23, 기본) · manager = 반장 관리자 하나(8-20 — 옛 실행 재현용)")
    p.add_argument("--reuse-from", help="8-23 캐시 대체: 이 실행들(쉼표)에 입력 sha(정규화 TASK · 그림)가 같은 순 결과 · 꾸러미 · 판 LLM 호출이 있으면 베낌(손 가리지 않음)")
    p.add_argument("--test-touch-task", help="시험용(8-23 끝 조건 6): 이 꾸러미 id(쉼표)의 TASK.md 끝에 한 바이트(줄바꿈)를 더한 뒤 채움")
    p.add_argument("--confirm", choices=prun.CONFIRM_MODES, default="auto",
                   help="설계서 8-26: auto(기본) = S9 뒤 확인 페이지 없이 자동 확정(질문감 · 낮은 확신 순에 짐작 표시 → done) · "
                        "page = 옛 길(확인 페이지 멈춤 → resume --answers — 개발 · 정답 만들기용). 판 실행 · 반장 조립 · resume 은 이 값(없으면 auto)을 따름")
    for q in (p, sp.add_parser("resume")):
        if q is not p:
            q.add_argument("--run", required=True)
            q.add_argument("--answers")
        q.add_argument("--max-usd", type=float, help="api 손: 실행 한도(달러, 기본 15) — resume 에 주면 한도를 바꿔 이어 감")
        q.add_argument("--i-mean-it", action="store_true", help="api 손: 진짜 Claude API 를 부른다(이 인자 없이는 진짜 호출 0)")
        q.add_argument("--hand-delay", type=float, default=0.0, help="시험용: 손이 꾸러미 하나를 채우기 전에 쉬는 초")
        q.add_argument("--die-after", type=int, help="시험용: 이 프로세스에서 k번째 꾸러미를 채운 바로 뒤 os._exit(137)")
        q.add_argument("--die-after-stage", choices=["S0", "S1", "S2", "S3"], help="시험용(go --games 공통 앞 단계): 이 단계가 끝난 바로 뒤 os._exit(137)")
    p = sp.add_parser("status")
    p.add_argument("--run", required=True)
    p = sp.add_parser("fork", help="끝난 실행을 베껴 어느 단계부터만 다시(state 되감기 — 돌리지 않음, 이어서 go)")
    p.add_argument("--from", dest="src", required=True)
    p.add_argument("--at", required=True, choices=pa.STAGES)
    p.add_argument("--run", required=True)
    p.add_argument("--games", help="11-26 밤: --from 이 반장 실행이면 새 반장(--at S4 로 베낌) + 이 판(쉼표 · all)의 판 실행 <옛 반장>__<판> 을 --at 에서 <새 반장>__<판> 으로 "
                                    "베낌 — 이어서 go --run <새 반장> --games <판> 이 그 단계부터만")
    a = ap.parse_args()
    {"go": cmd_go, "resume": cmd_resume, "status": cmd_status, "fork": cmd_fork}[a.cmd](a)


if __name__ == "__main__":
    main()
