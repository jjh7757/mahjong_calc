"""판 하나를 처음부터 끝까지: features → segment → river → game → sheets.

  python -X utf8 run.py <판 id> [시작 단계]
단계 이름: features segment river game sheets (시작 단계를 주면 그 단계부터).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEPS = ["features", "segment", "river", "game", "sheets"]


def main():
    gid = sys.argv[1]
    start = STEPS.index(sys.argv[2]) if len(sys.argv) > 2 else 0
    for st in STEPS[start:]:
        print(f"== {st} {gid}", flush=True)
        r = subprocess.run([sys.executable, "-X", "utf8", str(HERE / f"{st}.py"), gid])
        if r.returncode:
            sys.exit(r.returncode)


if __name__ == "__main__":
    main()
