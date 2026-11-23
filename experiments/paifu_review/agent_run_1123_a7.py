"""지시문 a7 · 사실표 3 측정(설계서 docs/review_agent_foldspot_scores_design_1123.md 5절 — 묶음 F 12 · G 10 · H 38 = 60).
서버 하나(mahjong-recognizer-review, a7)에 질문 파일 순서대로 하나씩 1회. 질문마다 agent_run_1122_app.py 를
--questions agent_questions_1123_a7.json --only <id> --server <서버> --out <결과 폴더> 로 부른다(agent_run_1123_tone.py 와 같은 방식,
이어 묻기 history 도 그 드라이버가 결과 폴더의 앞 질문 응답으로 만든다). 사실표는 질문의 facts 칸(results/agent_1123a7/facts/).

  python -X utf8 experiments/paifu_review/agent_run_1123_a7.py [--fake | --dry-run] [--only id,…] [--set a7F|a7G|a7H]

--dry-run: 아무것도 부르지 않는다(자식도 --dry-run) — 질문마다 돌릴 순서 · 사실표 유무 · history 를 찍고, 끝에 사실표마다
  크기(파일 bytes · 압축 JSON bytes)와 서버 한도 200KB 안인지를 찍는다. 사실표가 없거나 한도를 넘으면 종료 코드 1.
결과: results/agent_1123a7{_fake}/<id>.json · .log · .history.json, 돌린 순서 · 시각 · rc 는 results/agent_1123a7{_fake}/runs.jsonl.
모델 · 생각 수준은 서버 review_ask.py 의 기본값(이 드라이버는 정하지 않음 — 설계서 5절은 gemini-3.8-flash · low).
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
QFILE = "agent_questions_1123_a7.json"
SERVER = r"C:\Users\jjh7757\dev\mahjong-recognizer-review"
LIMIT = 200 * 1024  # 서버 사실표 한도(압축 JSON bytes)


def facts_file(q: dict) -> Path:
    p = Path(q["facts"])
    return p if p.is_absolute() else ROOT / p


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--set", default="")
    args = ap.parse_args()
    qs = json.loads((HERE / QFILE).read_text(encoding="utf-8"))["questions"]
    only = {s for s in args.only.split(",") if s}
    run = [q for q in qs if (not only or q["id"] in only) and (not args.set or q.get("set") == args.set)]
    base = "agent_1123a7" + ("_fake" if args.fake else "")
    log = HERE / "results" / base / "runs.jsonl"
    if not args.dry_run:
        log.parent.mkdir(parents=True, exist_ok=True)
    bad = 0
    for i, q in enumerate(run):
        cmd = [sys.executable, "-X", "utf8", str(HERE / "agent_run_1122_app.py"), "--questions", QFILE,
               "--only", q["id"], "--server", SERVER, "--out", base]
        if args.fake:
            cmd.append("--fake")
        if args.dry_run:
            cmd.append("--dry-run")
        t0 = time.time()
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        row = {"i": i, "id": q["id"], "set": q.get("set"), "rc": p.returncode,
               "start": time.strftime("%H:%M:%S", time.localtime(t0)), "wall_s": round(time.time() - t0, 2)}
        if args.dry_run:
            try:
                child = json.loads(p.stdout.strip().splitlines()[-1])
            except (ValueError, IndexError):
                child = {}
            ok = bool(child.get("facts_exists"))
            bad += 0 if ok and p.returncode == 0 else 1
            # 자식은 질문 하나만 보므로 앞 질문 응답이 없다고 찍는다 — 실제 실행에서는 앞 질문이 이 순서로 먼저 돌아
            # 결과 폴더에 응답이 생긴다. 여기서는 앞 질문이 이번 목록에서 먼저 오는지만 본다.
            after = q.get("after") or []
            earlier = {x["id"] for x in run[:i]}
            hist = "없음" if not after else (f"앞 질문 {'·'.join(after)} 응답으로 만듦(목록에서 먼저 돎)" if all(a in earlier for a in after)
                                             else f"앞 질문 {'·'.join(after)} 가 이번 목록에서 먼저 안 돎 — 결과 폴더의 옛 응답이 없으면 rc -1")
            print(json.dumps(dict(row, facts=q["facts"], facts_exists=ok, history=hist,
                                  after=q.get("after") or None, q=q["q"]), ensure_ascii=False), flush=True)
            if p.returncode != 0:
                print("  자식 stderr:", p.stderr.strip()[-400:])
            continue
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if p.returncode != 0:
            row["stderr"] = p.stderr[-800:]
        with log.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    if args.dry_run:
        print(f"\n질문 {len(run)}개 · 묶음별 " + " · ".join(f"{s} {sum(1 for q in run if q.get('set') == s)}"
                                                    for s in sorted({q.get('set') for q in run})))
        files = sorted({q["facts"] for q in run})
        print(f"사실표 {len(files)}개(파일 bytes · 압축 JSON bytes · 한도 {LIMIT} 안):")
        for rel in files:
            fp = ROOT / rel
            if not fp.exists():
                print(f"  {rel}: 없음")
                bad += 1
                continue
            d = json.loads(fp.read_text(encoding="utf-8"))
            comp = len(json.dumps(d, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            ok = comp <= LIMIT and fp.stat().st_size <= LIMIT
            bad += 0 if ok else 1
            print(f"  {rel}: {fp.stat().st_size} · {comp} · version {d.get('version')} · {'안' if ok else '넘음'}")
        print("확인:", "통과" if bad == 0 else f"문제 {bad}")
        return 0 if bad == 0 else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
