"""복기 에이전트 실제 호출 — 앱 질문 창 3단계 판(설계서 docs/paifu_review_agent_app_design_1122.md 6절). agent_run_1122.py 에
이어 묻기(history) · 질문마다 사실표 · --fake · --dry-run 을 더했다. 질문 파일의 질문을 서버 worktree 의 scripts/review_ask.py 로
파일에 적힌 순서대로 하나씩 돌린다.

  python -X utf8 experiments/paifu_review/agent_run_1122_app.py [--questions 파일] [--out 폴더] [--only a1,b2] [--set unseen4]
                                                               [--facts-dir 폴더] [--server 폴더] [--fake | --dry-run]

질문 항목: {"id", "q", "game"?, "facts"?, "after"?, "set"?, …}
- "facts": 사실표 파일 하나(저장소 뿌리 기준 상대 경로 또는 절대 경로). 없으면 --facts-dir(없으면 서버 fixture)/<game>.json.
- "after": ["앞 질문 id", …] — 같은 대화에서 앞서 한 질문들(순서대로). 결과 폴더의 그 id 응답(<id>.json)에서
  {"q": 그 질문의 q, "a": 응답 answer} 목록을 만들어 앱과 같게 최근 4쌍 · q · a 각 1000자(코드 포인트)로 자르고
  <id>.history.json 으로 결과 폴더에 쓴 뒤 review_ask.py --history 로 넘긴다. 앞 질문의 응답이 없으면(실패 · 질문 파일에 없음)
  그 질문은 돌리지 않고 rc -1 · 까닭(reason)을 행에 남긴다.
  이번 실행에서 돌리는 질문은 돌리기 전에 그 id 의 옛 응답 · history 를 지운다 — 이번에 실패한 앞 질문의 옛 응답을 잇지 않게.
  이번 실행에서 안 돌리는 앞 질문(--only · --set 로 빠진 것)은 결과 폴더에 이미 있는 응답을 쓴다.

키: 실제 모드에서만 GEMINI_API_KEY 를 .env 파일(HANDOFF "Gemini 키" 줄)에서 읽어 자식 프로세스 환경에만 넣는다 — 찍지 않고 복사하지 않는다.
--fake: review_ask.py --fake(대본 가짜 LLM)로 돌린다. .env 를 읽지 않고 자식 환경에서 GEMINI_API_KEY 를 뺀다(돈 0).
--dry-run: 아무것도 부르지 않고 쓰지 않는다 — 질문마다 돌릴 명령 · 사실표 경로 · history 유무만 찍는다(.env 도 안 읽음).
--server: review_ask.py 를 돌릴 서버 폴더(기본 SERVER). 지시문 판끼리 같은 시각에 번갈아 재려면 판마다 worktree 를 두고
  질문마다 --only <id> --server <판 폴더> --out <판마다 다른 폴더> 로 번갈아 부른다(11-23 a5 · a6). 질문에 facts 칸도
  --facts-dir 도 없으면 사실표는 그 서버의 fixture 에서 읽는다. 행 · summary 에 server · prompt_version 을 남긴다.
결과: results/<out>/<id>.json(응답) · <id>.log(도구 · 답 · 검증 기록) · <id>.history.json(넘긴 history) · summary.json.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]  # 저장소 뿌리(질문의 "facts" 상대 경로 기준)
SERVER = Path(r"C:\Users\jjh7757\dev\mahjong-recognizer-review")
ENV_FILE = Path(r"C:\Users\jjh7757\Downloads\부트캠프\.env")
OUT = HERE / "results" / "agent_1122app"
# 앱 lib/paifu/review_chat.dart 의 reviewHistoryMax · reviewHistoryTextMax(= 서버 HISTORY_MAX · HISTORY_TEXT_MAX).
HISTORY_MAX = 4
HISTORY_TEXT_MAX = 1000


def key() -> str:
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("GEMINI_API_KEY 없음")


def facts_path(q: dict, facts_dir: str) -> Path | None:
    if q.get("facts"):
        p = Path(q["facts"])
        return p if p.is_absolute() else ROOT / p
    if not q.get("game"):
        return None
    return (Path(facts_dir).resolve() if facts_dir else SERVER / "tests" / "fixtures" / "agent_facts") / f"{q['game']}.json"


def history(q: dict, by_id: dict) -> tuple[list[dict] | None, str]:
    """after 의 앞 질문들 → 앱과 같게 자른 history. 앞 질문 응답이 없으면 (None, 까닭)."""
    pairs = []
    for prev in q.get("after") or []:
        if prev not in by_id:
            return None, f"after 의 {prev} 가 질문 파일에 없음"
        res = OUT / f"{prev}.json"
        if not res.exists():
            return None, f"after 의 {prev} 응답이 결과 폴더에 없음(실패 또는 안 돌림)"
        pairs.append({"q": by_id[prev]["q"], "a": json.loads(res.read_text(encoding="utf-8"))["answer"]})
    recent = pairs[-HISTORY_MAX:]
    # 파이썬 str 의 길이 = 코드 포인트(앱 _cut 과 같은 셈). 앱은 질문 앞뒤 공백을 빼고 보내므로 q 도 strip.
    return [{"q": p["q"].strip()[:HISTORY_TEXT_MAX], "a": p["a"][:HISTORY_TEXT_MAX]} for p in recent], ""


def main() -> int:
    global OUT, SERVER
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--questions", default="agent_questions_1122_app.json", help="이 폴더 기준 상대 경로 또는 절대 경로")
    ap.add_argument("--out", default="agent_1122app", help="results/ 아래 폴더 이름")
    ap.add_argument("--facts-dir", default="", help="질문에 facts 칸이 없을 때의 사실표 폴더(없으면 서버 fixture). 파일 이름 = <game>.json")
    ap.add_argument("--set", default="", help="질문의 set 칸이 이 값인 것만")
    ap.add_argument("--server", default=str(SERVER), help="review_ask.py 를 돌릴 서버 폴더(기본: 지금 상수 SERVER)")
    ap.add_argument("--fake", action="store_true", help="review_ask.py --fake(가짜 LLM, 키 없이)")
    ap.add_argument("--dry-run", action="store_true", help="부르지 않고 명령 · 사실표 · history 유무만 찍음(--fake 와 같이 주면 가짜 명령을 찍음)")
    args = ap.parse_args()
    qs = json.loads((HERE / args.questions).read_text(encoding="utf-8"))["questions"]
    by_id = {q["id"]: q for q in qs}
    only = {x for x in args.only.split(",") if x}
    OUT = HERE / "results" / args.out
    SERVER = Path(args.server).resolve()
    if not (SERVER / "scripts" / "review_ask.py").exists():
        sys.exit(f"서버 폴더에 scripts/review_ask.py 가 없음: {SERVER}")
    run = [q for q in qs if (not only or q["id"] in only) and (not args.set or q.get("set") == args.set)]
    if args.dry_run:
        env = None
    else:
        OUT.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        if args.fake:
            env.pop("GEMINI_API_KEY", None)
        else:
            env["GEMINI_API_KEY"] = key()
        for q in run:  # 이번에 돌리는 질문의 옛 결과는 지운다(이번 실패를 옛 응답으로 잇지 않게).
            for suffix in (".json", ".history.json"):
                (OUT / f"{q['id']}{suffix}").unlink(missing_ok=True)
    rows = []
    ran = set()  # 이번 실행에서 앞서 돌린(돌렸을) id
    for q in run:
        facts = facts_path(q, args.facts_dir)
        out = OUT / f"{q['id']}.json"
        cmd = [sys.executable, "scripts/review_ask.py", str(facts), q["q"], "--out", str(out)]
        hist_file = OUT / f"{q['id']}.history.json"
        after = q.get("after") or []
        if args.dry_run:
            # 아무것도 안 부르므로 앞 질문의 답은 아직 없다 — 앞 질문마다 어디서 올지만 적는다.
            src = {a: ("질문 파일에 없음" if a not in by_id else "이번 실행에서 먼저 돎" if a in ran
                       else "결과 폴더에 있음" if (OUT / f"{a}.json").exists() else "없음(이번에 안 돌거나 뒤에 돎)")
                   for a in after}
            ok = all(v in ("이번 실행에서 먼저 돎", "결과 폴더에 있음") for v in src.values())
            if after and ok:
                cmd += ["--history", str(hist_file)]
            if args.fake:
                cmd.append("--fake")
            ran.add(q["id"])
            print(json.dumps({"id": q["id"], "server": str(SERVER), "cmd": cmd, "facts": str(facts), "facts_exists": bool(facts and facts.exists()),
                              "history": "없음" if not after else
                              (f"{min(len(after), HISTORY_MAX)}쌍 넘길 예정" if ok else "못 만듦 → rc -1 예정"),
                              "after": src}, ensure_ascii=False), flush=True)
            continue
        hist, why = (history(q, by_id) if after else ([], ""))
        if hist:
            cmd += ["--history", str(hist_file)]
        if args.fake:
            cmd.append("--fake")
        row = {"id": q["id"], "server": str(SERVER)}
        if facts is None or not facts.exists():
            row.update(rc=-1, reason=f"사실표 없음: {facts}", history_n=0)
        elif hist is None:
            row.update(rc=-1, reason=why, history_n=0)
        else:
            if hist:
                hist_file.write_text(json.dumps(hist, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
            t0 = time.time()
            p = subprocess.run(cmd, cwd=SERVER, env=env, capture_output=True)
            wall = round(time.time() - t0, 1)
            log = p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")
            (OUT / f"{q['id']}.log").write_text(log, encoding="utf-8", newline="\n")
            row.update(rc=p.returncode, wall_s=wall, history_n=len(hist))
            if p.returncode == 0 and out.exists():
                r = json.loads(out.read_text(encoding="utf-8"))
                row.update(prompt_version=r.get("prompt_version"), outcome=r["outcome"], retries=r.get("retries"), tools=len(r["tool_calls"]),
                           llm=r["usage"].get("llm_calls"), tin=r["usage"].get("input_tokens"),
                           tout=r["usage"].get("output_tokens"), elapsed=r["elapsed_s"])
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    if not args.dry_run:
        (OUT / "summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
