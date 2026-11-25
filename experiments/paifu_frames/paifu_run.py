"""대국 뒤 자동 패보 — 실행기: 설정에서 확인 페이지까지 명령 하나씩(설계서 docs/paifu_auto_agent_design_1124.md 8-17 4-③, 2026-11-25 밤, LLM 0).

  python -X utf8 experiments/paifu_frames/paifu_run.py start  --visit <방문 폴더> [--game <대국>] --run <실행 폴더> [make 옵션] [init 옵션]
  python -X utf8 experiments/paifu_frames/paifu_run.py start  --hanchan <반장 설정 json> --run <실행 폴더> [init 옵션]
  python -X utf8 experiments/paifu_frames/paifu_run.py go     --run <실행 폴더> [시험용: --replay-from <폴더> [--before-user] [--replay-sup-from <실행>] [--replay-stages S4,…]]
  python -X utf8 experiments/paifu_frames/paifu_run.py page   --run <실행 폴더> [포트 8315] [--ans <답 파일>]
  python -X utf8 experiments/paifu_frames/paifu_run.py answer --run <실행 폴더>
(저장소 루트에서. 흐름 자체는 paifu_auto.py · 설정 만들기는 paifu_setup.py · 페이지는 paifu_confirm.py — 이 파일은 그 셋을 하위 프로세스로 부르는 고리다.
 page 만 paifu_confirm 을 이 프로세스 안에서 띄운다(끄면 서버도 같이 꺼짐).)

start  — 흐름은 아직 돌리지 않는다. 어떤 설정 · 옵션으로 시작하는지 <실행>/runner.json 에 적고 멈춘다("시작" 을 받는 자리).
         --visit = paifu_setup.py make(시작 보고 <실행>/start_report.md). --game 이 없으면 먼저 paifu_setup.py scan 표를 보이고, 대국이 여럿이면 멈춘다.
         --hanchan = 손으로 쓴 설정의 반장(3반장 — 앱 기록이 없어 방문 폴더에서 설정을 못 만듦).
         init 옵션(--reuse · --hand-settings · --verify-dump · --s6-games · --s6a-rules · --no-sup · --sup-games · --slotgrid-seed)은 그대로 적어 두었다가
         go 가 처음 init 할 때 넘긴다. 실행 폴더에 state.json 이 이미 있으면 멈춘다(이미 시작한 실행).
go     — (처음이면 paifu_auto init) → paifu_auto next 를 돌린다. 답이 안 찬 꾸러미가 있으면 그 목록을 JSON 한 덩어리로 표준 출력에 내고 멈춘다
         (종료 코드 3). 답이 다 찬 꾸러미는 멈추지 않고 next 를 다시 불러 다음 단계로. 끝(S9)까지 가면 확인 1차례 자료(paifu_confirm.py prep —
         그때의 questions.jsonl + samples.jsonl 을 <실행>/runner/round1_questions.jsonl 로 얼려 둠)를 만들고 질문 수 · 표본 수 · 보고서 경로 ·
         페이지 띄우는 명령을 JSON 으로(종료 코드 0). 꾸러미를 읽히는 것은 이 파일 밖이다(지금은 세션이 하위 에이전트로, 나중에는 API 실행기).
         시험용 --replay-from: 멈출 자리마다 paifu_auto.py replay 로 답을 채우고 이어 간다(LLM 0). S7s(판 supervisor) 꾸러미는 --replay-sup-from
         (없으면 --replay-from)에서. --replay-stages 를 주면 그 단계 꾸러미만 재생하고 나머지 단계에서는 목록을 내고 멈춘다.
page   — 지금 열린 확인 차례의 페이지(paifu_confirm.py serve — 띄운 채 머묾). 답 = <실행>/answers_user.json 하나(--ans 는 시험용).
answer — <실행>/answers_user.json 을 paifu_auto.py apply 하고 결과(반영 · 건너뜀 · 답 받음 · 반영 안 됨 · 추가 질문 수)를 JSON 으로.
         추가 질문 = 반영 뒤 questions.jsonl 에서 앞 차례 페이지에 올랐던 id 를 뺀 것(답했든 안 했든 다시 안 묻는다 — 표본은 질문이 아니라 넣지 않음).
         1차례 뒤 추가 질문이 있으면 그 줄만으로 둘째 차례 자료(<실행>/confirm_2)를 만들고 종료 코드 4(page 로 띄울 것). 0 이면 끝(종료 코드 0).
         둘째 answer 뒤에는 페이지를 만들지 않는다 — 남은 것(1차례 페이지에 없던 질문 가운데 아직 목록에 있는 것)을 report.md 맨 위에 적고 끝.
         답 반영 뒤 규칙은 paifu_auto 쪽: apply 뒤의 S7 은 다시 읽기 꾸러미를 내지 않고, 검사에 걸린 채 남은 판은 S9 가 <판>_s7_check 알림 질문으로 올린다.

출력: go · start · answer 는 표준 출력에 JSON 한 덩어리만(하위 명령의 출력은 <실행>/logs/runner_<번호>_<무엇>.log — JSON 의 log 칸).
종료 코드(EXIT): 0 끝(start: 시작 보고 · go: 확인 자료까지 · answer: 확인 끝) · 1 오류(하위 명령 실패 · 상태 이상) · 2 멈춤(start: 대국 고르기 ·
  make 멈춤 · 이미 시작한 실행 — argparse 의 잘못된 인자도 2) · 3 읽을 꾸러미 있음(go) · 4 확인 페이지 기다림(answer 뒤 추가 질문).
목록 JSON(go, 종료 코드 3): status "read" · run · stage · stage_name · filled(답이 찬 꾸러미 수) · total · pending_file · packages(답이 안 찬 꾸러미 —
  pending.json 의 꾸러미 칸 그대로 + spawns_workers(S7s 판 supervisor 만 참 — 다시 읽기 작업자를 스스로 띄움)) · replay(시험용 재생을 했으면) · log · next.
앱 예시(assets/paifu_*)에 올리는 일은 하지 않는다(사용자가 말할 때만).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import paifu_auto as pa  # noqa: E402  (jl · wj · wt · rel · jlines · answered · STAGE_NAME — 흐름은 하위 프로세스로 부름)

PY = sys.executable
AUTO = HERE / "paifu_auto.py"
SETUP = HERE / "paifu_setup.py"
CONFIRM = HERE / "paifu_confirm.py"
RUNNER = "runner.json"
PORT = 8315
EXIT = {"done": 0, "error": 1, "stop": 2, "read": 3, "page": 4}
MAX_STEPS = 80          # go 한 번에 next · replay 를 부르는 최대 횟수(같은 꾸러미가 답이 찼는데도 안 넘어가는 고장을 끊음)
SAME_LIMIT = 3          # 답이 다 찬 같은 꾸러미 목록으로 next 를 이만큼 불러도 그대로면 오류
MAX_ROUNDS = 2          # 확인 차례(1차례 + 추가 질문 한 번 — 설계서 3-11 정한 것 3)
MAKE_OPTS = ["--captures", "--head-rec", "--date", "--id-prefix", "--id-start", "--rerun-of", "--sticks", "--clock-offset-ms", "--sticks-source"]
MAKE_FLAGS = ["--no-replay"]
MAKE_MULTI = ["--sticks-by-track"]
INIT_OPTS = ["--reuse", "--hand-settings", "--verify-dump", "--s6-games", "--sup-games", "--slotgrid-seed"]
INIT_FLAGS = ["--s6a-rules", "--no-sup"]
PATH_OPTS = {"--reuse", "--hand-settings", "--slotgrid-seed", "--captures", "--head-rec"}   # 저장소 루트 기준으로 바꿔 넘기는 길


# ------------------------------------------------------------------ 작은 도구
def emit(o: dict, code: str):
    """표준 출력에 JSON 한 덩어리 + 종료 코드."""
    o = {"status": code, **o}
    sys.stdout.write(json.dumps(o, ensure_ascii=False, indent=1) + "\n")
    sys.stdout.flush()
    raise SystemExit(EXIT[code])


def absp(p: str) -> Path:
    return Path(p) if Path(p).is_absolute() else (Path.cwd() / p)


def rp(p) -> str:
    return pa.rel(p)


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Runner:
    def __init__(self, run: str):
        self.d = absp(run).resolve()
        self.f = self.d / RUNNER
        self.o = pa.jl(self.f) if self.f.exists() else None

    def save(self):
        pa.wj(self.f, self.o)

    def sub(self, what: str, args: list) -> tuple:
        """하위 프로세스(끝까지 기다림) — 출력은 <실행>/logs/runner_<번호>_<what>.log. (rc, stdout, 로그 경로)"""
        self.o["seq"] = self.o.get("seq", 0) + 1
        self.save()
        log = self.d / "logs" / f"runner_{self.o['seq']:03d}_{what}.log"
        e = dict(os.environ, PYTHONIOENCODING="utf-8")
        t0 = time.time()
        p = subprocess.run([PY, "-X", "utf8", *[str(a) for a in args]], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=e)
        pa.wt(log, " ".join(str(a) for a in args) + f"\n# rc {p.returncode} · {time.time() - t0:.1f}s\n" + p.stdout + ("\n--- stderr\n" + p.stderr if p.stderr else ""))
        self.o.setdefault("calls", []).append({"at": now(), "what": what, "rc": p.returncode, "s": round(time.time() - t0, 1), "log": rp(log)})
        self.save()
        return p.returncode, p.stdout + ("\n" + p.stderr if p.stderr else ""), log

    def state(self):
        f = self.d / "state.json"
        return pa.jl(f) if f.exists() else None

    def pending(self) -> tuple:
        f = self.d / "pending.json"
        if not f.exists():
            return None, []
        p = pa.jl(f)
        return p.get("stage"), list(p.get("packages") or [])


def tail(txt: str, n: int = 1500) -> str:
    return (txt or "")[-n:]


def opt_args(a, names: list, flags: list, multi: list = ()) -> list:
    out = []
    for n in names:
        v = getattr(a, n[2:].replace("-", "_"))
        if v is not None:
            out += [n, rp(absp(v)) if n in PATH_OPTS else str(v)]
    for n in flags:
        if getattr(a, n[2:].replace("-", "_")):
            out.append(n)
    for n in multi:
        for v in getattr(a, n[2:].replace("-", "_")) or []:
            out += [n, v]
    return out


# ------------------------------------------------------------------ start
def cmd_start(a):
    run = absp(a.run).resolve()
    if (run / "state.json").exists():
        emit({"run": rp(run), "why": "실행 폴더에 state.json 이 이미 있음(이미 시작한 실행) — 이어 가려면 go, 새로 하려면 새 실행 폴더"}, "stop")
    make_a = opt_args(a, MAKE_OPTS, MAKE_FLAGS, MAKE_MULTI)
    init_a = opt_args(a, INIT_OPTS, INIT_FLAGS)
    if a.hanchan and (make_a or a.game):
        emit({"run": rp(run), "why": f"--hanchan 에는 make 옵션 · --game 을 못 씀: {make_a + ([a.game] if a.game else [])}"}, "error")
    r = Runner(str(run))
    r.o = {"_note": "paifu_run.py 실행기 상태(설계서 8-17 4-③) — start 가 적은 설정 · init 옵션, go · answer 의 확인 차례, 하위 명령 기록",
           "made": now(), "seq": (r.o or {}).get("seq", 0), "init_args": init_a, "rounds": [], "finished": None}
    run.mkdir(parents=True, exist_ok=True)
    if a.hanchan:
        cfg_f = absp(a.hanchan).resolve()
        try:
            h = pa.hcfg.load(cfg_f)
        except BaseException as e:   # noqa: BLE001  (hanchan_cfg 의 겹침 오류 · 없는 파일)
            emit({"run": rp(run), "why": f"반장 설정을 못 읽음: {type(e).__name__}: {e}"}, "error")
        r.o.update(mode="hanchan", hanchan=rp(cfg_f))
        r.save()
        emit({"run": rp(run), "mode": "hanchan", "hanchan": rp(cfg_f), "label": h.label, "games": list(h.games), "init_args": init_a,
              "runner": rp(r.f), "next": f"python -X utf8 experiments/paifu_frames/paifu_run.py go --run {rp(run)}"}, "done")
    # --visit: (--game 이 없으면 scan 표) → paifu_setup make
    visit = absp(a.visit).resolve()
    r.o.update(mode="visit", visit=rp(visit), game=a.game, make_args=make_a, hanchan=rp(run / "hanchan_auto.json"))
    r.save()
    scan_txt = None
    if a.game is None:
        so_args = opt_args(a, ["--captures", "--head-rec", "--date"], [])
        rc, txt, log = r.sub("scan", [SETUP, "scan", "--visit", rp(visit), *so_args, "--out", run / "runner" / "scan.json"])
        if rc != 0:
            emit({"run": rp(run), "why": "paifu_setup scan 실패" if rc != 2 else "판이 0", "rc": rc, "log": rp(log), "out": tail(txt)}, "stop" if rc == 2 else "error")
        games = pa.jl(run / "runner" / "scan.json").get("games") or []
        scan_txt = txt
        if len(games) > 1:
            emit({"run": rp(run), "why": f"대국이 {len(games)}개 — --game <대국 id 또는 scan 순번> 으로 고를 것", "scan_table": txt.strip().splitlines(),
                  "games": [{"index": g["index"], "game": g["game"], "folders": g["folders"], "rounds": g["rounds"]} for g in games],
                  "scan": rp(run / "runner" / "scan.json"), "log": rp(log)}, "stop")
    rc, txt, log = r.sub("make", [SETUP, "make", "--visit", rp(visit), *(["--game", a.game] if a.game else []), "--run", rp(run), *make_a])
    if rc != 0:
        emit({"run": rp(run), "why": "paifu_setup make 가 멈춤(설정을 안 씀)" if rc in (2, 3) else "paifu_setup make 오류", "rc": rc, "log": rp(log),
              "out": tail(txt, 3000)}, "stop" if rc in (2, 3) else "error")
    rep = pa.jl(run / "start_report.json") if (run / "start_report.json").exists() else {}
    emit({"run": rp(run), "mode": "visit", "visit": rp(visit), "game": a.game, "hanchan": rp(run / "hanchan_auto.json"),
          "start_report": rp(run / "start_report.md"), "start_report_json": rp(run / "start_report.json"),
          "start_report_text": (run / "start_report.md").read_text(encoding="utf-8") if (run / "start_report.md").exists() else None,
          "summary": {k: rep[k] for k in ("games", "agents", "tokens", "warnings") if k in rep}, "scan_table": scan_txt.strip().splitlines() if scan_txt else None,
          "make_args": make_a, "init_args": init_a, "runner": rp(r.f), "log": rp(log),
          "next": f"python -X utf8 experiments/paifu_frames/paifu_run.py go --run {rp(run)}"}, "done")


# ------------------------------------------------------------------ go
def need_runner(a) -> Runner:
    r = Runner(a.run)
    if r.o is None:
        emit({"run": rp(r.d), "why": f"{RUNNER} 이 없음 — start 먼저"}, "error")
    return r


def pkg_view(p: dict) -> dict:
    return {**p, "answered": pa.answered(p), "spawns_workers": p.get("stage") == "S7s" or p.get("kind") == "supervisor"}


def read_list(r: Runner, stage, pk: list, log, replay=None) -> dict:
    todo = [pkg_view(p) for p in pk if not pa.answered(p)]
    return {"run": rp(r.d), "stage": stage, "stage_name": pa.STAGE_NAME.get(stage), "filled": len(pk) - len(todo), "total": len(pk),
            "pending_file": rp(r.d / "pending.json"), "packages": todo, **({"replay": replay} if replay else {}), "log": rp(log) if log else None,
            "next": f"꾸러미마다 task 를 읽혀 answer 에 쓴 뒤: python -X utf8 experiments/paifu_frames/paifu_run.py go --run {rp(r.d)}"}


def round_rows(r: Runner) -> list:
    """1차례 페이지 줄 = 지금 questions.jsonl(먼저) + samples.jsonl — paifu_confirm.load_rows 와 같은 순서 · 같은 id 하나로."""
    rows, seen = [], set()
    for q in pa.jlines(r.d / "questions.jsonl") + [{**q, "sample": True} for q in pa.jlines(r.d / "samples.jsonl")]:
        if q.get("id") and q["id"] not in seen:
            seen.add(q["id"])
            rows.append(q)
    return rows


def make_round(r: Runner, n: int, rows: list) -> dict:
    """확인 n차례 자료: 줄을 <실행>/runner/round<n>_questions.jsonl 로 얼리고 paifu_confirm prep(n=1 → <실행>/confirm · 2 → confirm_2)."""
    qf = r.d / "runner" / f"round{n}_questions.jsonl"
    pa.wt(qf, "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in rows))
    out = r.d / ("confirm" if n == 1 else f"confirm_{n}")
    rc, txt, log = r.sub(f"prep{n}", [CONFIRM, "prep", "--run", rp(r.d), "--questions", rp(qf), "--out", rp(out)])
    if rc != 0:
        emit({"run": rp(r.d), "why": f"확인 {n}차례 자료(paifu_confirm prep) 실패", "rc": rc, "log": rp(log), "out": tail(txt)}, "error")
    man = pa.jl(out / "manifest.json")
    rd = {"n": n, "ids": [q["id"] for q in rows], "questions": sum(1 for q in rows if not q.get("sample")), "samples": sum(1 for q in rows if q.get("sample")),
          "questions_file": rp(qf), "confirm": rp(out), "prepared_at": now(), "prep_log": rp(log),
          "turns": len(man.get("turns") or []), "turns_missing": man.get("turns_missing") or {}, "items": len(man.get("items") or []),
          "items_by_bundle": {b: sum(1 for x in man.get("items") or [] if x["bundle"] == b) for b in "ABC"},
          "videos": sum(1 for x in man.get("items") or [] if x.get("video")), "frames": sum(x.get("frames", 0) for x in man.get("turns") or []),
          "answered_at": None}
    r.o["rounds"].append(rd)
    r.save()
    return rd


def page_cmd(r: Runner) -> str:
    return f"python -X utf8 experiments/paifu_frames/paifu_run.py page --run {rp(r.d)} {PORT}"


def round_view(r: Runner, rd: dict) -> dict:
    return {"round": rd["n"], "page_rows": len(rd["ids"]), "questions": rd["questions"], "samples": rd["samples"], "turns": rd["turns"], "items": rd["items"],
            "items_by_bundle": rd["items_by_bundle"], "videos": rd["videos"], "frames": rd["frames"], "turns_missing": rd["turns_missing"],
            "questions_file": rd["questions_file"], "confirm": rd["confirm"], "prep_log": rd["prep_log"]}


def finished_view(r: Runner) -> dict:
    return {"run": rp(r.d), "finished": r.o["finished"], "rounds": [round_view(r, x) for x in r.o["rounds"]], "report": rp(r.d / "report.md")}


def cmd_go(a):
    r = need_runner(a)
    if r.o.get("finished"):
        emit({**finished_view(r), "why": "확인까지 끝난 실행 — 더 할 것 없음"}, "done")
    rstages = [x for x in (a.replay_stages or "").split(",") if x] or None
    if r.state() is None:
        rc, txt, log = r.sub("init", [AUTO, "init", "--hanchan", r.o["hanchan"], "--run", rp(r.d), *r.o.get("init_args", [])])
        if rc != 0 or r.state() is None:
            emit({"run": rp(r.d), "why": "paifu_auto init 실패", "rc": rc, "log": rp(log), "out": tail(txt)}, "error")
    last, same, log = None, 0, None
    for _ in range(MAX_STEPS):
        stage, pk = r.pending()
        todo = [p for p in pk if not pa.answered(p)]
        if todo:   # 읽을 꾸러미가 남음 — 시험용 재생이 있으면 채워 보고, 아니면 목록을 내고 멈춤
            if not a.replay_from or (rstages and stage not in rstages):
                emit(read_list(r, stage, pk, log), "read")
            src = a.replay_sup_from if (stage == "S7s" and a.replay_sup_from) else a.replay_from
            args = [AUTO, "replay", "--run", rp(r.d), "--from", rp(absp(src))] + (["--before-user"] if a.before_user and stage != "S7s" else [])
            rc, txt, log = r.sub(f"replay_{stage}", args)
            if rc != 0:
                emit({"run": rp(r.d), "why": f"paifu_auto replay 실패({stage})", "rc": rc, "log": rp(log), "out": tail(txt)}, "error")
            stage2, pk2 = r.pending()
            if any(not pa.answered(p) for p in pk2):
                emit(read_list(r, stage2, pk2, log, replay={"from": rp(absp(src)), "out": tail(txt, 600).strip()}), "read")
        key = (stage, tuple(p.get("id") for p in pk))
        if pk and key == last:
            same += 1
            if same >= SAME_LIMIT:
                emit({"run": rp(r.d), "why": f"답이 다 찬 꾸러미({stage} {len(pk)}개)로 next 를 {same}번 불러도 안 넘어감", "log": rp(log) if log else None}, "error")
        else:
            same = 0
        last = key
        rc, txt, log = r.sub("next", [AUTO, "next", "--run", rp(r.d)])
        if rc != 0:
            emit({"run": rp(r.d), "why": "paifu_auto next 오류로 멈춤", "rc": rc, "log": rp(log), "out": tail(txt, 3000),
                  "report": rp(r.d / "report.md")}, "error")
        stage, pk = r.pending()
        st = r.state()
        if not pk and (st["stages"].get("S9") or {}).get("status") == "done":
            break
        if not pk:
            emit({"run": rp(r.d), "why": "next 가 끝났는데 꾸러미도 없고 S9 도 안 끝남", "log": rp(log)}, "error")
    else:
        emit({"run": rp(r.d), "why": f"go 한 번에 {MAX_STEPS}걸음을 넘김"}, "error")
    # 끝(S9) — 확인 1차례 자료(처음 한 번만 — 그 뒤 go 는 열린 차례를 알림)
    if not r.o["rounds"]:
        rd = make_round(r, 1, round_rows(r))
    else:
        rd = r.o["rounds"][-1]
    st = r.state()
    q = pa.jlines(r.d / "questions.jsonl")
    sm = pa.jlines(r.d / "samples.jsonl")
    emit({"run": rp(r.d), "questions": len(q), "samples": len(sm), "question_ids": [x["id"] for x in q], "sample_ids": [x["id"] for x in sm],
          "report": rp(r.d / "report.md"), "open_round": round_view(r, rd) if rd.get("answered_at") is None else None,
          "timing": st.get("timing"), "answers_file": rp(r.d / "answers_user.json"),
          "page": page_cmd(r), "answer": f"python -X utf8 experiments/paifu_frames/paifu_run.py answer --run {rp(r.d)}"}, "done")


# ------------------------------------------------------------------ page
def cmd_page(a):
    r = need_runner(a)
    open_ = [x for x in r.o["rounds"] if x.get("answered_at") is None]
    if not open_:
        emit({**finished_view(r), "why": "열린 확인 차례가 없음" + (" — 확인까지 끝남" if r.o.get("finished") else " — go 를 끝까지 먼저")},
             "done" if r.o.get("finished") else "error")
    rd = open_[-1]
    import paifu_confirm as pc   # 이 프로세스 안에서 띄움(끄면 같이 꺼짐)
    ctx = pc.Ctx(str(r.d), str(ROOT / rd["confirm"]), str(ROOT / rd["questions_file"]))
    print(f"확인 {rd['n']}차례 — 줄 {len(rd['ids'])}(질문 {rd['questions']} · 표본 {rd['samples']}) · 답 → {rp(Path(a.ans).resolve()) if a.ans else rp(r.d / 'answers_user.json')}", flush=True)
    pc.serve(ctx, a.port, Path(a.ans) if a.ans else None)


# ------------------------------------------------------------------ answer
def report_block(r: Runner, remaining: list | None) -> list:
    st = r.state() or {}
    ua = st.get("user_answers") or {}
    L = ["## 실행기 확인 차례(paifu_run.py — 설계서 8-17 4-③)", ""]
    for rd in r.o["rounds"]:
        ap = rd.get("apply") or {}
        L.append(f"- 확인 {rd['n']}차례: 페이지 {len(rd['ids'])}줄(질문 {rd['questions']} · 표본 {rd['samples']}, `{rd['confirm']}`)"
                 + (f" → 답 반영 {rd['answered_at']}: 반영 {ap.get('applied')}(전과 같음 {ap.get('same')}) · 건너뜀 {ap.get('skipped')} · "
                    f"답 받음 · 반영 안 됨 {ap.get('unapplied')} · 추가 질문 {len(rd.get('extra') or [])}" if rd.get("answered_at") else " — 답 기다림"))
    if remaining is not None:
        L += ["", f"**확인 두 차례 뒤에도 남은 것 {len(remaining)}개(셋째 페이지 없음 — 설계서 3-11 정한 것 3):**" if r.o["rounds"][-1]["n"] >= MAX_ROUNDS
              else f"**추가 질문 0 — 확인 끝**"]
        for q in remaining:
            u = ua.get(q["id"]) or {}
            where = "둘째 페이지에 오름" if any(q["id"] in x["ids"] for x in r.o["rounds"][1:]) else "어느 페이지에도 안 오름(새로 생김)"
            ans = (f"답 {json.dumps(u.get('value'), ensure_ascii=False)}({u.get('value_name') or ''}) · {u.get('result')}" if u else "답 없음")
            L.append(f"  - {q['id']} ({q.get('kind')} · {where} · {ans}) — {(q.get('why') or q.get('rule') or '')[:300]}")
    return L + [""]


def put_report_block(r: Runner, remaining: list | None):
    f = r.d / "report.md"
    if not f.exists():
        return
    lines = f.read_text(encoding="utf-8").split("\n")
    head, rest = lines[:1], lines[1:]
    while rest and rest[0] == "":
        rest = rest[1:]
    pa.wt(f, "\n".join(head + [""] + report_block(r, remaining) + rest))


def cmd_answer(a):
    r = need_runner(a)
    open_ = [x for x in r.o["rounds"] if x.get("answered_at") is None]
    if not open_:
        emit({**finished_view(r), "why": "열린 확인 차례가 없음" + (" — 확인까지 끝남" if r.o.get("finished") else " — go 를 끝까지 먼저")}, "error")
    rd = open_[-1]
    af = r.d / "answers_user.json"
    if not af.exists():
        emit({"run": rp(r.d), "why": f"답 파일 없음: {rp(af)} — page 에서 저장하거나 그 꼴로 쓸 것"}, "error")
    st0 = r.state()
    n_ev = len(st0.get("events") or [])
    rc, txt, log = r.sub(f"apply{rd['n']}", [AUTO, "apply", "--run", rp(r.d), "--answers", rp(af)])
    if rc != 0:
        emit({"run": rp(r.d), "round": rd["n"], "why": "paifu_auto apply 오류", "rc": rc, "log": rp(log), "out": tail(txt, 3000)}, "error")
    st = r.state()
    ev = next((e for e in (st.get("events") or [])[n_ev:] if "apply" in e), {})
    stage, pk = r.pending()
    if any(not pa.answered(p) for p in pk):   # 답 반영 뒤 S7 은 꾸러미를 안 내야 함 — 나오면 알림(목록)
        emit({**read_list(r, stage, pk, log), "why": "답 반영 뒤 흐름이 읽을 꾸러미를 냄(예상 밖)"}, "read")
    if (st["stages"].get("S9") or {}).get("status") != "done":
        emit({"run": rp(r.d), "why": "답 반영 뒤 S9 가 안 끝남", "log": rp(log)}, "error")
    qs = pa.jlines(r.d / "questions.jsonl")
    shown = {i for x in r.o["rounds"] for i in x["ids"]}
    extra = [q for q in qs if q["id"] not in shown]
    applied = ev.get("apply") or []
    rd.update(answered_at=now(), apply_log=rp(log), extra=[q["id"] for q in extra],
              apply={"applied": len(applied), "same": sum(1 for x in applied if x.get("same_as_before")), "skipped": len(ev.get("skipped") or []),
                     "unapplied": len(ev.get("unapplied") or []), "skipped_why": ev.get("skipped") or [], "unapplied_ids": ev.get("unapplied") or [],
                     "applied_ids": [x["id"] for x in applied]})
    r.save()
    s7 = st["stages"].get("S7") or {}
    base = {"run": rp(r.d), "round": rd["n"], "apply": rd["apply"], "questions_after": len(qs), "samples_after": len(pa.jlines(r.d / "samples.jsonl")),
            "s7_bad": s7.get("bad") or [], "s7_after_user": bool(s7.get("after_user")), "s8_check_fail": sorted((st["stages"].get("S8") or {}).get("check_fail") or {}),
            "extra_ids": rd["extra"], "report": rp(r.d / "report.md"), "log": rp(log)}
    if extra and rd["n"] < MAX_ROUNDS:
        rd2 = make_round(r, rd["n"] + 1, extra)
        put_report_block(r, None)
        emit({**base, "extra": len(extra), "open_round": round_view(r, rd2), "page": page_cmd(r),
              "answer": f"python -X utf8 experiments/paifu_frames/paifu_run.py answer --run {rp(r.d)}"}, "page")
    first = set(r.o["rounds"][0]["ids"])
    remaining = [q for q in qs if q["id"] not in first] if rd["n"] >= MAX_ROUNDS else []
    r.o["finished"] = {"at": now(), "round": rd["n"], "remaining": [q["id"] for q in remaining],
                       "why": "추가 질문 0" if rd["n"] < MAX_ROUNDS else "둘째 차례 뒤 — 셋째 페이지 없음"}
    r.save()
    put_report_block(r, remaining)
    emit({**base, "extra": len(extra), "remaining": [q["id"] for q in remaining], "finished": r.o["finished"]}, "done")


def main():
    ap = argparse.ArgumentParser(description="대국 뒤 자동 패보 실행기(설계서 8-17 4-③)")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("start")
    p.add_argument("--run", required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--visit")
    g.add_argument("--hanchan")
    p.add_argument("--game")
    for n in MAKE_OPTS + INIT_OPTS:
        p.add_argument(n)
    for n in MAKE_FLAGS + INIT_FLAGS:
        p.add_argument(n, action="store_true")
    for n in MAKE_MULTI:
        p.add_argument(n, action="append")
    p = sp.add_parser("go")
    p.add_argument("--run", required=True)
    p.add_argument("--replay-from", help="시험용: 멈출 자리마다 paifu_auto.py replay --from 이 폴더(LLM 0)")
    p.add_argument("--before-user", action="store_true", help="시험용: replay --before-user(S7s 꾸러미에는 안 붙임)")
    p.add_argument("--replay-sup-from", help="시험용: S7s(판 supervisor) 꾸러미 재생 출처(마감된 sup/ 이 있는 실행)")
    p.add_argument("--replay-stages", help="시험용: 이 단계 꾸러미만 재생(쉼표) — 나머지 단계에서는 목록을 내고 멈춤")
    p = sp.add_parser("page")
    p.add_argument("--run", required=True)
    p.add_argument("port", nargs="?", type=int, default=PORT)
    p.add_argument("--ans", help="시험용: 답 파일(기본 <실행>/answers_user.json)")
    p = sp.add_parser("answer")
    p.add_argument("--run", required=True)
    a = ap.parse_args()
    {"start": cmd_start, "go": cmd_go, "page": cmd_page, "answer": cmd_answer}[a.cmd](a)


if __name__ == "__main__":
    main()
