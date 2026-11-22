"""복기 에이전트 실제 호출(11-22 판 — --facts-dir · --set 추가, 나머지는 agent_run_1121.py 와 같음): 질문 파일의 질문을 서버 worktree 의 scripts/review_ask.py 로 하나씩 돌린다.

  python -X utf8 agent_run_1121.py [--only w1,f2]

키: GEMINI_API_KEY 를 .env 파일(HANDOFF "Gemini 키" 줄)에서 읽어 자식 프로세스 환경에만 넣는다 — 찍지 않고 복사하지 않는다.
결과: results/agent_1121/<id>.json(응답) · <id>.log(도구 · 답 · 검증 기록) · summary.json.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVER = Path(r"C:\Users\jjh7757\dev\mahjong-recognizer-review")
ENV_FILE = Path(r"C:\Users\jjh7757\Downloads\부트캠프\.env")
OUT = HERE / "results" / "agent_1121"


def key() -> str:
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("GEMINI_API_KEY 없음")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--questions", default="agent_questions_1121.json")
    ap.add_argument("--out", default="agent_1121", help="results/ 아래 폴더 이름")
    ap.add_argument("--facts-dir", default="", help="사실표 폴더(없으면 서버 fixture). 파일 이름 = <game>.json")
    ap.add_argument("--set", default="", help="질문의 set 칸이 이 값인 것만(seen / unseen)")
    args = ap.parse_args()
    qs = json.loads((HERE / args.questions).read_text(encoding="utf-8"))["questions"]
    only = {x for x in args.only.split(",") if x}
    global OUT
    OUT = HERE / "results" / args.out
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, GEMINI_API_KEY=key(), PYTHONIOENCODING="utf-8")
    rows = []
    for q in qs:
        if only and q["id"] not in only:
            continue
        if args.set and q.get("set") != args.set:
            continue
        facts = (Path(args.facts_dir).resolve() if args.facts_dir else SERVER / "tests" / "fixtures" / "agent_facts") / f"{q['game']}.json"
        out = OUT / f"{q['id']}.json"
        t0 = time.time()
        p = subprocess.run([sys.executable, "scripts/review_ask.py", str(facts), q["q"], "--out", str(out)],
                           cwd=SERVER, env=env, capture_output=True)
        wall = round(time.time() - t0, 1)
        log = p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")
        (OUT / f"{q['id']}.log").write_text(log, encoding="utf-8", newline="\n")
        row = {"id": q["id"], "rc": p.returncode, "wall_s": wall}
        if p.returncode == 0 and out.exists():
            r = json.loads(out.read_text(encoding="utf-8"))
            row.update(outcome=r["outcome"], retries=r.get("retries"), tools=len(r["tool_calls"]),
                       llm=r["usage"].get("llm_calls"), tin=r["usage"].get("input_tokens"),
                       tout=r["usage"].get("output_tokens"), elapsed=r["elapsed_s"])
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    (OUT / "summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
