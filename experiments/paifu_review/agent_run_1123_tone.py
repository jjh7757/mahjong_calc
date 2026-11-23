"""지시문 a5 대 a6 말투 비교 — 같은 질문을 두 서버에 같은 시각에 번갈아 1회씩(설계서 docs/paifu_review_agent_app_design_1122.md
맨 위 "진행(11-23 오후)" 의 기준). 질문마다 agent_run_1122_app.py 를 --only <id> --server <폴더> 로 부른다.
짝수 번째 질문은 a5 → a6, 홀수 번째는 a6 → a5 순서(먼저 부르는 쪽이 늘 같지 않게).

  python -X utf8 experiments/paifu_review/agent_run_1123_tone.py [--fake | --dry-run] [--only id,…]

결과: results/agent_1123tone{_fake}/{a5,a6}/<id>.json · .log, 돌린 순서 · 시각 · rc 는 results/agent_1123tone{_fake}/runs.jsonl.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
QFILE = "agent_questions_1123_tone.json"
SERVERS = {
    "a5": r"C:\Users\jjh7757\dev\mahjong-recognizer-a5",
    "a6": r"C:\Users\jjh7757\dev\mahjong-recognizer-review",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    qs = json.loads((HERE / QFILE).read_text(encoding="utf-8"))["questions"]
    only = {s for s in args.only.split(",") if s}
    base = "agent_1123tone" + ("_fake" if args.fake else "")
    log = HERE / "results" / base / "runs.jsonl"
    if not args.dry_run:
        log.parent.mkdir(parents=True, exist_ok=True)
    for i, q in enumerate(qs):
        if only and q["id"] not in only:
            continue
        order = ["a5", "a6"] if i % 2 == 0 else ["a6", "a5"]
        for ver in order:
            cmd = [sys.executable, "-X", "utf8", str(HERE / "agent_run_1122_app.py"), "--questions", QFILE,
                   "--only", q["id"], "--server", SERVERS[ver], "--out", f"{base}/{ver}"]
            if args.fake:
                cmd.append("--fake")
            if args.dry_run:
                cmd.append("--dry-run")
            t0 = time.time()
            p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            row = {"i": i, "id": q["id"], "ver": ver, "rc": p.returncode, "start": time.strftime("%H:%M:%S", time.localtime(t0)),
                   "wall_s": round(time.time() - t0, 2)}
            print(json.dumps(row, ensure_ascii=False), flush=True)
            if args.dry_run:
                print(p.stdout.strip()[-400:])
                continue
            if p.returncode != 0:
                row["stderr"] = p.stderr[-800:]
            with log.open("a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
