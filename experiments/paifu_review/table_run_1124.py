"""대국 뒤 복기 대화 1단계 측정 드라이버 — 설계서 docs/postgame_review_chat_design_1124.md "1단계 상세".

대본(table_utterances_1124.json)의 말 하나마다 개발용 서버의 POST /v2/review/table 을 **한 번** 부른다(history 없음 — 장면마다
말 4꼴은 서로 이어지지 않는 따로인 말). 장면은 table_scenes_1124.json(game · wind · step), 사실표는
results/table_facts/dart/<game>.json(앱 Dart 출력, 0단계).

  python -X utf8 experiments/paifu_review/table_run_1124.py [--fake | --dry-run] [--only u01,u02] [--server URL] [--key KEY]
                                                            [--utterances 파일] [--force]

서버(서버 저장소 worktree mahjong-recognizer-table, feat/review-table)는 따로 띄운다:
  python scripts/review_dev_server.py --port 8331 [--fake]          (실제 Gemini 는 --env-file … — 사용자 허락 뒤에만)
요청 제한(REVIEW_RATE_PER_MIN 6 · BURST 3)에 걸리면(이 서버의 429 — LLM 을 부르기 전) Retry-After 만큼 쉬고 다시 보낸다.
Gemini 429(detail 에 upstream)는 다시 보내지 않고 그대로 적는다(LLM 이 이미 불렸을 수 있음).

결과: results/table_1124{_fake}/<id>.json = {utterance, scene, request_bytes, status, client_s, at, response},
돌린 순서는 같은 폴더의 runs.jsonl. 이미 결과가 있는 말은 건너뛴다(--force 면 다시 — 돈이 두 번 든다).
--fake: 결과 폴더만 _fake 로 나눈다(서버를 --fake 로 띄운 경우와 짝). --dry-run: 부르지 않고 순서 · 요청 크기만 찍는다.
대본 파일이 없으면 작은 가짜 대본 3개(FAKE_UTTERANCES)로 돈다(흐름 확인용).
채점: experiments/paifu_review/agent_defense/table_score.py.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
UTTER = HERE / "table_utterances_1124.json"
SCENES = HERE / "table_scenes_1124.json"
FACTS_DIR = HERE / "results" / "table_facts" / "dart"
LIMIT = 200 * 1024  # 서버 요청 한도(압축 JSON bytes)
FAKE_UTTERANCES = [
    {"id": "f01", "scene": "sc01", "kind": "false", "text": "남 자리 현물이라 생각했어",
     "gold": [{"type": "genbutsu", "tile": None, "wind": "남"}]},
    {"id": "f02", "scene": "sc01", "kind": "unverifiable", "text": "리치를 몰랐어. 안전패도 없었고",
     "gold": [{"type": "unaware_riichi", "tile": None, "wind": None}, {"type": "no_safe", "tile": None, "wind": None}]},
    {"id": "f03", "scene": "sc02", "kind": "verdict", "text": "내가 접었어야 했어?", "gold": []},
]


def load_utterances(path: Path) -> tuple[list[dict], bool]:
    if not path.is_file():
        print(f"대본 파일이 아직 없다: {path} — 가짜 대본 {len(FAKE_UTTERANCES)}개로 돈다")
        return FAKE_UTTERANCES, True
    return json.loads(path.read_text(encoding="utf-8"))["utterances"], False


def build_request(u: dict, scenes: dict) -> tuple[dict, dict]:
    sc = scenes[u["scene"]]
    facts = json.loads((FACTS_DIR / f"{sc['game']}.json").read_text(encoding="utf-8"))
    return {"facts": facts, "wind": sc["wind"], "step": sc["step"], "text": u["text"], "history": []}, sc


def post(url: str, key: str, body: bytes, timeout: float) -> tuple[int, dict | str, dict]:
    rq = urllib.request.Request(url, data=body, method="POST",
                                headers={"Content-Type": "application/json", "X-Api-Key": key})
    try:
        with urllib.request.urlopen(rq, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8")), dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            data = json.loads(raw)
        except ValueError:
            data = raw
        return e.code, data, dict(e.headers)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:8331")
    ap.add_argument("--key", default="dev-key")
    ap.add_argument("--utterances", type=Path, default=UTTER)
    ap.add_argument("--fake", action="store_true", help="결과 폴더를 table_1124_fake 로(서버를 --fake 로 띄웠을 때)")
    ap.add_argument("--dry-run", action="store_true", help="부르지 않고 순서 · 요청 크기만")
    ap.add_argument("--only", help="쉼표로 나눈 말 id")
    ap.add_argument("--force", action="store_true", help="결과가 있어도 다시 부름(돈이 두 번 든다)")
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--max-wait-429", type=int, default=8, help="이 서버의 요청 제한 429 를 기다려 다시 보낼 최대 횟수")
    args = ap.parse_args()

    utts, fake_script = load_utterances(args.utterances)
    scenes = {s["id"]: s for s in json.loads(SCENES.read_text(encoding="utf-8"))["scenes"]}
    if args.only:
        want = set(args.only.split(","))
        utts = [u for u in utts if u["id"] in want]
    out_dir = HERE / "results" / ("table_1124_fake" if args.fake else "table_1124")
    url = args.server.rstrip("/") + "/v2/review/table"
    print(f"말 {len(utts)}개 → {url}{' (DRY RUN)' if args.dry_run else ''} · 결과 {out_dir}"
          + (" · 가짜 대본" if fake_script else ""))
    bad = 0
    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
    for i, u in enumerate(utts):
        req, sc = build_request(u, scenes)
        body = json.dumps(req, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        head = f"[{i + 1}/{len(utts)}] {u['id']} {u['scene']}({sc['game']} {sc['wind']} {sc['step']}) {u['kind']:12} {len(body):6}B"
        if len(body) > LIMIT:
            print(f"{head}  서버 한도 초과")
            bad += 1
            continue
        dest = out_dir / f"{u['id']}.json"
        if args.dry_run:
            print(f"{head}  {u['text']}")
            continue
        if dest.exists() and not args.force:
            print(f"{head}  (이미 있음 — 건너뜀)")
            continue
        at = datetime.now().isoformat(timespec="seconds")
        for attempt in range(args.max_wait_429 + 1):
            t0 = time.perf_counter()
            status, data, headers = post(url, args.key, body, args.timeout)
            client_s = round(time.perf_counter() - t0, 3)
            local_429 = status == 429 and "upstream" not in json.dumps(data, ensure_ascii=False)
            if not local_429 or attempt == args.max_wait_429:
                break
            wait = int(headers.get("Retry-After") or headers.get("retry-after") or 10)
            print(f"{head}  요청 제한 429 — {wait}초 쉬고 다시")
            time.sleep(wait)
        rec = {"utterance": u, "scene": sc, "request_bytes": len(body), "status": status, "client_s": client_s, "at": at,
               "response": data}
        dest.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        line = {"id": u["id"], "at": at, "status": status, "client_s": client_s}
        if status == 200 and isinstance(data, dict):
            line.update(outcome=data.get("outcome"), retries=data.get("retries"),
                        llm_calls=(data.get("usage") or {}).get("llm_calls"), elapsed_s=data.get("elapsed_s"))
            print(f"{head}  {status} {data.get('outcome')} 재시도 {data.get('retries')} "
                  f"LLM {line['llm_calls']} {data.get('elapsed_s')}초")
        else:
            bad += 1
            print(f"{head}  {status} {str(data)[:120]}")
        with open(out_dir / "runs.jsonl", "a", encoding="utf-8", newline="\n") as fo:
            fo.write(json.dumps(line, ensure_ascii=False) + "\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
