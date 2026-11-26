"""대국 뒤 자동 패보 — 반장 관리자 하나 + 읽기 작업자 여럿, 상태는 LangGraph(설계서 docs/paifu_auto_agent_design_1124.md 8-20, 2026-11-26 오후, LLM 0).

  python -X utf8 experiments/paifu_frames/paifu_graph.py start  --run <실행> (--visit <방문> [--game <대국>] | --hanchan <설정>) [init 옵션]
  python -X utf8 experiments/paifu_frames/paifu_graph.py go     --run <실행> --hands replay|session|api [--replay-from <실행>] [--replay-sup-from <실행>]
                                                                 [--before-user] [--max-concurrency 8]
                                                                 [api 손: --api-games <판>[,…][,manager] · --reuse-api-from <앞 실행> · --max-usd 15 ·
                                                                  --api-fake replay[:out=<출력 토큰>](가짜 클라이언트 — API 0) | --i-mean-it(진짜 API)]
  python -X utf8 experiments/paifu_frames/paifu_graph.py resume --run <실행> [--answers <답 파일>] [--max-usd <새 한도>] [--i-mean-it]
  python -X utf8 experiments/paifu_frames/paifu_graph.py status --run <실행>
  python -X utf8 experiments/paifu_frames/paifu_graph.py fork   --from <끝난 실행> --at <단계> --run <새 실행>   # 베껴 그 단계부터만 다시(이어서 go)
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
  라운드, MAX_ROUNDS 넘으면 마감 검사 ① 대상 차례를 ask 로 올리고 done) · confirm(paifu_confirm prep 뒤 interrupt) · answer(paifu_run.py answer 와 같은 일 —
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
TEST = {"hand_delay": 0.0, "die_after": None, "fills": 0}
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
    st = "S7s" if stage in ("sup_reread", "manager", "S7s") else stage
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
    for _ in range(prun.MAX_STEPS):
        stage, pk = r.pending()
        todo = [p for p in pk if not pa.answered(p)]
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
        rc, txt, log = r.sub("next", [AUTO, "next", "--run", rp(r.d)])
        if rc != 0:
            raise GraphError(f"paifu_auto next 오류(rc {rc}) — {rp(log)}: {prun.tail(txt, 1500)}")
        stage, pk = r.pending()
        st = r.state()
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
    return "mgr_prep" if s["phase"] == "mgr" else "confirm"


# ------------------------------------------------------------------ 마디: work(꾸러미 하나를 손으로)
def fill_rec(run, p: dict, event: str, hand: str, conc: int, **kw):
    append(gdir(run) / "fills.jsonl", {"at": now(), "id": p["id"], "stage": p.get("stage"), "kind": pkg_view(p)["kind"], "game": p.get("game"),
                                       "turn": p.get("turn"), "event": event, "hand": hand, "conc": conc, "pid": os.getpid(), **kw})


def asked_flag(run, pid: str) -> Path:
    """session 손에 낸 꾸러미 표시 — 재개 때 답이 찬 것을 '그 손이 채움(filled)' 으로, 표시 없이 이미 찬 것은 'already' 로 가름."""
    return gdir(run) / "asked" / f"{pid}.flag"


def n_work(x: dict):
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
            return {"log": [{"id": p["id"], "event": "already"}], "max_conc": c}
        if hand == "api":   # 8-21: 꾸러미 하나를 Claude API(또는 가짜 클라이언트)로 — 답은 끝날 때 한 번에 넘어옴(paifu_apihand 사본)
            res = ah.fill_graph_pkg(run, p, opts, lambda: replay_text(run, p, opts))
            with FILL_LOCK:
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
            fill_rec(run, p, "filled", "session" if hand == "session" else "session(replay 빈 곳)", c)
            return {"log": [{"id": p["id"], "event": "filled"}], "max_conc": c}
        if TEST["hand_delay"]:
            time.sleep(TEST["hand_delay"])
        with FILL_LOCK:
            put_answer(p, how)
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


# ------------------------------------------------------------------ 확인 멈춤 · 답 반영
def n_confirm(s: GS):
    run = s["run"]
    r = runner(run)
    if r.o.get("finished"):
        return {"phase": "done"}
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
    g.add_conditional_edges("stage", r_stage, ["work", "mgr_prep", "confirm"])
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


def cfg_of(run: Path, mc: int) -> dict:
    return {"configurable": {"thread_id": run.name}, "max_concurrency": mc, "recursion_limit": 5000}


def fills_summary(run: Path) -> dict:
    L = log_lines(gdir(run) / "fills.jsonl")
    filled = Counter(x["id"] for x in L if x["event"] == "filled")
    return {"lines": len(L), "events": dict(Counter(x["event"] for x in L)), "filled_packages": len(filled),
            "filled_twice": sorted(k for k, c in filled.items() if c > 1), "by_kind": dict(Counter(x["kind"] for x in L if x["event"] == "filled")),
            "s7s_to_hand": sum(1 for x in L if x.get("stage") == "S7s"), "max_conc_seen": max([x.get("conc") or 0 for x in L] or [0])}


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


def has_thread(run: Path) -> bool:
    if not (run / DB).exists():
        return False
    app, conn = build(run)
    st = app.get_state(cfg_of(run, MC_DEFAULT))
    conn.close()
    return bool(st.values)


# ------------------------------------------------------------------ 명령
def cmd_start(rest: list):
    p = subprocess.run([PY, "-X", "utf8", str(RUN_PY), "start", *rest], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    sys.stdout.write(p.stdout)
    if p.stderr:
        sys.stderr.write(p.stderr)
    raise SystemExit(p.returncode)


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
    if has_thread(run):
        emit({"run": rp(run), "why": f"이미 go 한 실행(그래프 기록 {rp(run / DB)} · thread {run.name}) — 이어 가려면 resume"}, "stop")
    set_test(a)
    opts = {"hands": a.hands, "replay_from": rp(absp(a.replay_from)) if a.replay_from else None,
            "replay_sup_from": rp(absp(a.replay_sup_from)) if a.replay_sup_from else None, "before_user": bool(a.before_user),
            "max_concurrency": a.max_concurrency, "session_stages": [x for x in (a.session_stages or "").split(",") if x],
            "api_games": [x for x in a.api_games.split(",") if x] if a.api_games else None,
            "reuse_api_from": rp(absp(a.reuse_api_from)) if a.reuse_api_from else None, "api_fake": a.api_fake or None}
    gdir(run).mkdir(parents=True, exist_ok=True)
    set_api(run, opts, a)
    pa.wj(gdir(run) / "graph.json", {"_note": "paifu_graph.py go 설정(설계서 8-20)", "at": now(), **opts, "thread_id": run.name, "db": rp(run / DB)})
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
FORK_STAGE_SKIP = {"S4": ["s4"], "S6a": ["s6a"], "S6": ["read"], "S7s": ["sup"], "S9": ["paifu", "paifu_source", "_impact"]}   # 그 단계부터 다시면 안 베낌(꾸러미 답 · 결과)
FORK_TEXT = {".json", ".jsonl", ".md", ".txt", ".csv", ".yaml", ".yml"}


def cmd_fork(a):
    """fork --from <실행> --at <단계> --run <새 실행>: 끝까지(또는 그 단계 뒤까지) 돈 실행 폴더를 베끼고 state 를 <단계> 부터 todo 로 되감음(paifu_auto next --redo 와 같은 되감기 —
    돌리지는 않음). 안 베끼는 것: 그래프 기록(graph.sqlite · graph/) · 관리자(mgr/) · 확인 쪽(confirm/ · runner/ · questions* · samples · answers_user · report.md) · logs/ ·
    <단계> 와 뒤 단계의 꾸러미 · 결과 폴더(FORK_STAGE_SKIP). 글 파일(json · jsonl · md · txt · csv · yaml) 안의 옛 실행 경로는 새 실행 경로로 바꿈(옛 폴더에 쓰지 않게).
    runner.json 은 확인 차례 · 끝 표시를 비움. 원본은 읽기만. 그다음 go 로 이어 감(예: --hands api --i-mean-it)."""
    src, dst = absp(a.src), absp(a.run)
    if not (src / "state.json").exists() or not (src / prun.RUNNER).exists():
        emit({"run": rp(dst), "why": f"--from {a.src}: state.json · {prun.RUNNER} 가 있는 실행 폴더가 아님"}, "stop")
    if dst.exists():
        emit({"run": rp(dst), "why": "새 실행 폴더가 이미 있음 — 다른 이름으로"}, "stop")
    sr = pa.Run(src)
    stl = pa.stage_list(sr)
    if a.at not in stl:
        emit({"run": rp(dst), "why": f"--at {a.at}: 이 실행의 단계가 아님({stl})"}, "stop")
    if (sr.state["stages"].get(stl[stl.index(a.at) - 1]) or {}).get("status") != "done" if stl.index(a.at) > 0 else False:
        emit({"run": rp(dst), "why": f"원본에서 {a.at} 앞 단계가 안 끝남 — 베낄 수 없음"}, "stop")
    later = stl[stl.index(a.at):]
    skip = set(FORK_ALWAYS_SKIP)
    for s in later:
        skip.update(FORK_STAGE_SKIP.get(s, []))
    t0 = time.time()
    shutil.copytree(src, dst, ignore=lambda d, names: [n for n in names if Path(d).resolve() == src and n in skip])
    reps = [(src.as_posix(), dst.as_posix()), (str(src), str(dst)), (str(src).replace("\\", "\\\\"), str(dst).replace("\\", "\\\\")), (rp(src), rp(dst)),
            (f'"{src.name}"', f'"{dst.name}"')]   # 반장 설정 id 처럼 실행 이름만 든 칸
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
        t2 = t
        for x, y in reps:
            t2 = t2.replace(x, y)
        if t2 != t:
            f.write_bytes(t2.encode("utf-8"))
            n_rew += 1
    r = pa.Run(dst)
    for s in later:
        r.state["stages"][s] = {"status": "todo"}
        r.state["timing"].pop(s, None)
    r.state["events"].append({"at": now(), "fork": {"from": rp(src), "at": a.at}})
    r.save()
    ro = json.loads((dst / prun.RUNNER).read_text(encoding="utf-8"))
    ro.update(rounds=[], finished=None, forked={"from": rp(src), "at": a.at, "made": now()})
    pa.wj(dst / prun.RUNNER, ro)
    left = sorted(str(p.relative_to(dst)) for p in dst.rglob("*") if p.is_file() and p.suffix.lower() in FORK_TEXT and p.stat().st_size <= 64 * 2 ** 20
                  and src.name in p.read_bytes().decode("utf-8", errors="replace"))
    emit({"run": rp(dst), "from": rp(src), "at": a.at, "redo_stages": later, "skipped": sorted(skip), "text_files": n_txt, "rewritten": n_rew,
          "old_name_left_in": left[:30], "old_name_left_count": len(left), "s": round(time.time() - t0, 1),
          "next": f"python -X utf8 experiments/paifu_frames/paifu_graph.py go --run {rp(dst)} --hands <replay|session|api> …"}, "done")


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
    p.add_argument("--api-fake", help="api 손 시험: 가짜 클라이언트(replay 또는 replay:out=<호출마다 출력 토큰>) — API 0")
    for q in (p, sp.add_parser("resume")):
        if q is not p:
            q.add_argument("--run", required=True)
            q.add_argument("--answers")
        q.add_argument("--max-usd", type=float, help="api 손: 실행 한도(달러, 기본 15) — resume 에 주면 한도를 바꿔 이어 감")
        q.add_argument("--i-mean-it", action="store_true", help="api 손: 진짜 Claude API 를 부른다(이 인자 없이는 진짜 호출 0)")
        q.add_argument("--hand-delay", type=float, default=0.0, help="시험용: 손이 꾸러미 하나를 채우기 전에 쉬는 초")
        q.add_argument("--die-after", type=int, help="시험용: 이 프로세스에서 k번째 꾸러미를 채운 바로 뒤 os._exit(137)")
    p = sp.add_parser("status")
    p.add_argument("--run", required=True)
    p = sp.add_parser("fork", help="끝난 실행을 베껴 어느 단계부터만 다시(state 되감기 — 돌리지 않음, 이어서 go)")
    p.add_argument("--from", dest="src", required=True)
    p.add_argument("--at", required=True, choices=pa.STAGES)
    p.add_argument("--run", required=True)
    a = ap.parse_args()
    {"go": cmd_go, "resume": cmd_resume, "status": cmd_status, "fork": cmd_fork}[a.cmd](a)


if __name__ == "__main__":
    main()
