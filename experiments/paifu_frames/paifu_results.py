"""대국 뒤 자동 패보 — 순별 · 판별 결과 파일 한 꼴(설계서 docs/paifu_auto_agent_design_1124.md 8-23, 2026-11-26 밤, LLM 0).

두 꼴:
  순별 `paifu.turn/1` — <실행>/turns/<순>/<시도>.json(시도 = first · r1 · r2 · user, S7 다시 읽기는 s7r<k>).
      첫 읽기 · 다시 읽기 · 사용자 답 · 재생 · 세션 손 · api 손이 모두 같은 꼴. 옛 answer.json 은 그대로 두고 옆에 씀.
  판별 `paifu.game/1` — <실행>/games/<판>.json + 한눈 보기 games/index.json. 판 LLM 의 입력(초안)이자 출력(마감본), S9 가 판끼리 모을 때 재료.
여기 있는 것: 두 꼴 만들기 · 꼴 검사 · 옛 파일에서 만들기(export) · 판 결과 병합(build_game) · 캐시 찾기(입력 sha — 실행 폴더 경로를 <RUN> 으로 바꾼 바이트).

  python -X utf8 experiments/paifu_frames/paifu_results.py export   --run <실행> [--out <폴더>]   # 옛 실행에서 turns/ · games/ 를 만듦(--out 이면 그 아래에 — 원본은 읽기만)
  python -X utf8 experiments/paifu_frames/paifu_results.py validate --run <실행> | --dir <폴더>   # 꼴 검사(순 · 판 · index)
  python -X utf8 experiments/paifu_frames/paifu_results.py input    --run <실행> --pkg <꾸러미 폴더>   # 꾸러미 입력 sha(시험용)

캐시 대체의 "바이트 같음": TASK.md · 목록 파일 · 첫 메시지 글은 실행 폴더 경로(절대 · 저장소 기준 · 이름)를 <RUN> 으로 바꾼 뒤 바이트(실행마다
꾸러미 경로가 지시문에 들어가므로 — 8-21 --reuse-api-from 과 같은 규칙). 그림은 바이트 sha(파일마다). 지시문에 적힌 폴더(예: 녹화 프레임 폴더 전체)는
안의 이름 · 크기 목록의 sha(수만 장 바이트 해시를 피함 — 그 폴더의 그림을 실제로 고르는 것은 모델이고, 원본 녹화는 바뀌지 않음).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

SCHEMA_TURN = "paifu.turn/1"
SCHEMA_GAME = "paifu.game/1"
ANS_KEYS = ("k", "j", "end_order", "gone", "unsure", "p", "events_used", "why")   # 순 답 꼴(gone = 울기 답 칸 — 명세 예시에 없어 더함)
USER_KEYS = ("user", "user_note", "user_saved_at")
HANDS = ("api", "replay", "session", "user", "reuse", "unknown")   # reuse = 캐시에서 베낌(원래 손은 source.orig_hand) · unknown = export 에서 손 기록 없음
ATTEMPT_RE = re.compile(r"^(first|r\d+|s7r\d+|user)$")
IMG_EXT = {".jpg", ".jpeg", ".png"}
MODEL = "claude-opus-5-5"
EFFORT = "high"
LOCK = threading.Lock()
_SHA: dict = {}


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def jl(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def wj(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".tmp{os.getpid()}_{threading.get_ident()}")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(o, ensure_ascii=False, indent=1))
    os.replace(tmp, p)


def jlines(f) -> list:
    f = Path(f)
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()] if f.exists() else []


def rel_to(p, base) -> str | None:
    try:
        return Path(p).resolve().relative_to(Path(base).resolve()).as_posix()
    except ValueError:
        return None


def rel_root(p) -> str:
    return rel_to(p, ROOT) or Path(p).resolve().as_posix()


# ------------------------------------------------------------------ 정규화 · sha
def norm_text(text: str, run) -> str:
    """실행 폴더 경로(절대 posix · 절대 역슬래시 · JSON 안 이중 역슬래시 · 저장소 기준)와 실행 이름을 <RUN> 으로."""
    run = Path(run).resolve()
    reps = [run.as_posix(), str(run), str(run).replace("\\", "\\\\")]
    r2 = rel_to(run, ROOT)
    if r2:
        reps.append(r2)
    for s in sorted(set(reps), key=len, reverse=True):
        text = text.replace(s, "<RUN>")
    return re.sub(rf"(?<![\w-]){re.escape(run.name)}(?![\w-])", "<RUN>", text)


def sha_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def file_sha(p: Path) -> str:
    st = p.stat()
    k = (os.path.normcase(str(p.resolve())), st.st_size, st.st_mtime_ns)
    with LOCK:
        if k in _SHA:
            return _SHA[k]
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    with LOCK:
        _SHA[k] = h
    return h


def dir_listing_sha(d: Path) -> str:
    rows = []
    for n in sorted(os.listdir(d)):
        f = d / n
        rows.append(f"{n}\t{f.stat().st_size if f.is_file() else '/'}")
    return sha_text("\n".join(rows))


def pkg_input(run, p: dict, kind: str | None = None, frames=None, before: float | None = None) -> dict:
    """꾸러미 입력 — task_sha256(정규화한 TASK.md) · images_sha256(꾸러미가 보여 줄 수 있는 그림 목록 · 바이트) · inputs_sha256(꾸러미 폴더에서 모델이 읽을 수 있는
    파일 전부의 바이트 — 글은 실행 경로 정규화, files = 그 목록) · frames · model · effort. 캐시 열쇠는 세 sha 모두."""
    import paifu_apihand as ah
    run = Path(run).resolve()
    kind = kind or ah.kind_of(p)
    task = Path(p["task"]).read_bytes().decode("utf-8")
    G = ah.Guard(p, kind)
    rows = set()
    for root, dirs, files in os.walk(G.dir):
        if ah.under(root, G.work):
            dirs[:] = []
            continue
        if before is not None and Path(root).resolve() == Path(G.dir).resolve():   # 끝난 실행을 나중에 셀 때: 손 · 뒤 단계 출력 폴더(try/ · alt/)는 뺌(복사본이라 시각이 옛것일 수 있음)
            dirs[:] = [x for x in dirs if x not in ("try", "alt")]
        for f in files:
            q = Path(root) / f
            if before is not None and q.stat().st_mtime > before:   # 끝난 실행을 나중에 열쇠로 셀 때: 손이 채우기 시작한 뒤 생긴 파일(try/ · alt/ 등)은 뺌
                continue
            if q.suffix.lower() in IMG_EXT:
                rows.add(f"pkg:{q.relative_to(G.dir).as_posix()}\t{file_sha(q)}")
    lists = []
    for f in G.list_files_in_pkg():   # 목록 파일 글(정규화) — 그림 이름 · 시각 줄
        if before is not None and f.stat().st_mtime > before:   # 손이 채우며 만든 try/<n>/frames_turns.txt 등
            continue
        lists.append(f"list:{f.relative_to(G.dir).as_posix()}\t{sha_text(norm_text(f.read_text(encoding='utf-8', errors='replace'), run))}")
    for q in sorted(G.lists()["files"]) + sorted(G.task_files):
        q = Path(q)
        if q.suffix.lower() in IMG_EXT and q.exists():
            rows.add(f"file:{norm_text(q.resolve().as_posix(), run)}\t{file_sha(q)}")
    for d in G.task_dirs:
        rows.add(f"dir:{norm_text(d.as_posix(), run)}\t{dir_listing_sha(d)}")
    body = "\n".join(sorted(rows) + sorted(lists))
    # 11-26 밤 결정성 점검(세션): 열쇠를 꾸러미 폴더에서 모델이 읽을 수 있는 파일 전부(work/ · 답 파일 · 손 기록 · 숨김 파일 빼고)의 바이트로 넓힘 —
    # events.txt 처럼 TASK · 그림 밖의 글 파일이 실행마다 달라지면(slotgrid 정렬 — 같은 번호끼리 순서) 캐시에 안 걸리고 다시 부름
    files, frows = [], []
    for root, dirs, fs in os.walk(G.dir):
        if ah.under(root, G.work):
            dirs[:] = []
            continue
        if before is not None and Path(root).resolve() == Path(G.dir).resolve():   # 끝난 실행을 나중에 셀 때: 손 · 뒤 단계 출력 폴더(try/ · alt/)는 뺌(복사본이라 시각이 옛것일 수 있음)
            dirs[:] = [x for x in dirs if x not in ("try", "alt")]
        dirs.sort()
        for fn in sorted(fs):
            q = Path(root) / fn
            rl = q.relative_to(G.dir).as_posix()
            if os.path.normcase(str(q.resolve())) == os.path.normcase(str(G.answer)) or fn.endswith(".api_pending") or fn.startswith("api_log") \
                    or fn.startswith(".") or ".tmp" in fn:
                continue
            if before is not None and q.stat().st_mtime > before:
                continue
            if q.suffix.lower() in (".md", ".txt", ".json", ".jsonl", ".csv"):
                h = sha_text(norm_text(q.read_bytes().decode("utf-8", errors="replace"), run))
            else:
                h = file_sha(q)
            files.append(rl)
            frows.append(f"{rl}\t{h}")
    return {"task_sha256": sha_text(norm_text(task, run)), "images_sha256": sha_text(body), "inputs_sha256": sha_text("\n".join(frows)),
            "files": files if len(files) <= 400 else files[:200] + [f"…(+{len(files) - 400})"] + files[-200:],
            "frames": frames, "model": MODEL, "effort": EFFORT, "images": sum(1 for x in rows if not x.startswith("dir:"))}


# ------------------------------------------------------------------ 순별 꼴
def answer_part(a: dict, keep_user: bool = False) -> dict:
    """옛 answer.json → 순 답 꼴(고정 칸 + extra). id · kind 는 바깥으로, 사용자 칸은 user 시도에서만 extra 로."""
    out = {k: a.get(k) for k in ANS_KEYS}
    skip = {"id", "kind"} | (set() if keep_user else set(USER_KEYS))
    ex = {k: v for k, v in a.items() if k not in ANS_KEYS and k not in skip}
    out["extra"] = ex or None
    return out


def old_answer(doc: dict) -> dict:
    """순 결과 파일 → 옛 answer.json 꼴(칸 비교용 — null 칸은 뺌)."""
    a = {"id": doc["turn"], "kind": doc["kind"]}
    for k in ANS_KEYS:
        if doc["answer"].get(k) is not None:
            a[k] = doc["answer"][k]
    a.update(doc["answer"].get("extra") or {})
    return a


def cost_of_log(pkg_dir) -> dict:
    """꾸러미 api_log.jsonl 의 마지막 시도(마지막 start 줄 뒤) 합 — 없으면 0."""
    L = jlines(Path(pkg_dir) / "api_log.jsonl")
    i = max([k for k, x in enumerate(L) if "start" in x] or [-1])
    part = L[i + 1:] if i >= 0 else []
    calls = [x for x in part if "call" in x and "usd" in x and "tool" not in x]
    reused = any(x.get("reused") for x in part)
    end = next((x for x in reversed(part) if "end" in x), {})
    return {"calls": len(calls), "in": sum(x.get("in") or 0 for x in calls), "out": sum(x.get("out") or 0 for x in calls),
            "cache_read": sum(x.get("cache_read") or 0 for x in calls), "cache_write": sum(x.get("cache_write") or 0 for x in calls),
            "usd": round(sum(float(x.get("usd") or 0) for x in calls), 6), "seconds": float(end.get("s") or 0.0), "reused": reused}


def aborted_of_log(pkg_dir) -> dict | None:
    """꾸러미 api_log.jsonl 에서 마지막 시도 앞의 시도들(답 없이 끊김 — 실행 한도 · 죽음) 돈. 없으면 None.
    그 돈은 실행 돈 기록(graph/api_usage.jsonl)에 이미 한 번 들어가 있다 — 여기는 기록만(결과 파일 cost 에는 안 더함)."""
    L = jlines(Path(pkg_dir) / "api_log.jsonl")
    st = [k for k, x in enumerate(L) if "start" in x]
    if len(st) < 2:
        return None
    part = L[:st[-1]]
    calls = [x for x in part if "call" in x and "usd" in x and "tool" not in x]
    ends = [x.get("end") for x in part if "end" in x]
    return {"tries": len(st) - 1, "calls": len(calls), "usd": round(sum(float(x.get("usd") or 0) for x in calls), 6), "ends": ends,
            "stash": [x.get("stash") for x in part if x.get("restart")]}


def zero_cost(reused=False) -> dict:
    return {"calls": 0, "in": 0, "out": 0, "cache_read": 0, "cache_write": 0, "usd": 0.0, "seconds": 0.0, "reused": reused}


def turn_doc(run, game: str, turn: str, attempt: str, ans: dict, inp: dict | None, source: dict, cost: dict) -> dict:
    return {"schema": SCHEMA_TURN, "game": game, "turn": turn, "attempt": attempt, "kind": ans.get("kind"),
            "answer": answer_part(ans, keep_user=attempt == "user"), "input": inp, "source": source, "cost": cost, "at": now()}


def turn_file(run, turn: str, attempt: str) -> Path:
    return Path(run) / "turns" / turn / f"{attempt}.json"


def write_turn(run, game: str, turn: str, attempt: str, answer_path, *, hand: str, from_run=None, pkg_dir=None, inp=None,
               cost=None, orig_hand=None, note=None, aborted=None) -> Path:
    ans = jl(answer_path)
    src = {"hand": hand, "from_run": rel_root(from_run) if from_run else None, "pkg": rel_to(pkg_dir, run) if pkg_dir else None}
    if orig_hand:
        src["orig_hand"] = orig_hand
    if note:
        src["note"] = note
    if aborted:
        src["aborted"] = aborted
    doc = turn_doc(run, game, turn, attempt, ans, inp, src, cost or zero_cost())
    f = turn_file(run, turn, attempt)
    wj(f, doc)
    return f


def _t(v, *types):
    return isinstance(v, types) and not (bool not in types and isinstance(v, bool))


def validate_turn(doc: dict) -> list:
    e = []
    want = ("schema", "game", "turn", "attempt", "kind", "answer", "input", "source", "cost", "at")
    for k in want:
        if k not in doc:
            e.append(f"칸 없음 {k}")
    if e:
        return e
    if set(doc) - set(want):
        e.append(f"모르는 칸 {sorted(set(doc) - set(want))}")
    if doc["schema"] != SCHEMA_TURN:
        e.append(f"schema {doc['schema']}")
    for k in ("game", "turn", "at"):
        if not _t(doc[k], str):
            e.append(f"{k} 형")
    if not _t(doc["attempt"], str) or not ATTEMPT_RE.match(doc["attempt"]):
        e.append(f"attempt {doc['attempt']!r}")
    if doc["kind"] not in ("hand", "call", "tsumogiri"):
        e.append(f"kind {doc['kind']!r}")
    a = doc["answer"]
    if not isinstance(a, dict) or set(a) != set(ANS_KEYS) | {"extra"}:
        e.append(f"answer 칸 {sorted(a) if isinstance(a, dict) else a}")
    else:
        for k, ty in (("k", (int,)), ("j", (int,)), ("end_order", (list,)), ("gone", (list,)), ("unsure", (bool,)), ("p", (int, float)),
                      ("events_used", (str,)), ("why", (str,)), ("extra", (dict,))):
            v = a[k]
            if v is None:
                continue
            if k == "unsure":
                if not isinstance(v, bool):
                    e.append("answer.unsure 형")
            elif isinstance(v, bool) or not isinstance(v, ty):
                e.append(f"answer.{k} 형 {type(v).__name__}")
        if a.get("end_order") is None and doc["attempt"] != "user":
            e.append("answer.end_order 없음")
    inp = doc["input"]
    if inp is not None:
        if not isinstance(inp, dict) or set(inp) - {"task_sha256", "images_sha256", "inputs_sha256", "files", "frames", "model", "effort", "images"} or \
                not all(k in inp for k in ("task_sha256", "images_sha256", "frames", "model", "effort")):
            e.append(f"input 칸 {sorted(inp) if isinstance(inp, dict) else inp}")
        else:
            for k in [x for x in ("task_sha256", "images_sha256", "inputs_sha256") if x in inp]:
                if not (isinstance(inp[k], str) and re.fullmatch(r"[0-9a-f]{64}", inp[k])):
                    e.append(f"input.{k}")
    s = doc["source"]
    if not isinstance(s, dict) or not {"hand", "from_run", "pkg"} <= set(s):
        e.append("source 칸")
    elif s["hand"] not in HANDS:
        e.append(f"source.hand {s['hand']!r}")
    c = doc["cost"]
    ck = ("calls", "in", "out", "cache_read", "cache_write", "usd", "seconds", "reused")
    if not isinstance(c, dict) or set(c) != set(ck):
        e.append("cost 칸")
    else:
        for k in ck[:-1]:
            if isinstance(c[k], bool) or not isinstance(c[k], (int, float)):
                e.append(f"cost.{k} 형")
        if not isinstance(c["reused"], bool):
            e.append("cost.reused 형")
    return e


# ------------------------------------------------------------------ 판별 꼴
def strip_meta(o):
    """첫 메시지(판 LLM)에 넣을 판 결과 초안 — 출처 · 돈 · 입력 칸(실행마다 다른 값)을 뺌."""
    if isinstance(o, dict):
        return {k: strip_meta(v) for k, v in o.items() if k not in ("source", "cost", "input", "cost_total", "at", "files")}
    if isinstance(o, list):
        return [strip_meta(x) for x in o]
    return o


def fills_index(run) -> dict:
    """graph/fills.jsonl → 꾸러미 id → 마지막 filled 줄."""
    out = {}
    for x in jlines(Path(run) / "graph" / "fills.jsonl"):
        if x.get("event") == "filled":
            out[x["id"]] = x
    return out


def src_of_fill(run, pid: str, pkg_dir) -> tuple:
    """(source, cost) — 그래프 기록(fills.jsonl · api_log)에서. 기록이 없으면 hand unknown."""
    x = fills_index(run).get(pid)
    if not x:
        f = Path(run) / "graph" / "fills.jsonl"
        return {"hand": "unknown", "from_run": None, "pkg": rel_to(pkg_dir, run), "note": "손 기록 없음(그래프 밖에서 채움 · fork 로 베낌)" if f.exists() else "손 기록 없음(그래프 없는 실행)"}, zero_cost()
    h = x.get("hand") or "unknown"
    if h.startswith("reuse"):
        return {"hand": "reuse", "from_run": x.get("from_run"), "pkg": rel_to(pkg_dir, run), "orig_hand": x.get("orig_hand")}, zero_cost(True)
    if h.startswith("api"):
        c = cost_of_log(pkg_dir)
        s = {"hand": "api", "from_run": rel_root(x["src"]) if x.get("src") and "(reuse)" in h else None, "pkg": rel_to(pkg_dir, run)}
        ab = aborted_of_log(pkg_dir)
        if ab:
            s["aborted"] = ab
        if x.get("forked_from"):   # fork 가 베낀 꾸러미(11-26 밤): 이 실행이 쓴 돈이 아님 — 옛 돈은 orig_usd 로 기록만
            s.update(forked_from=x["forked_from"], orig_usd=c["usd"])
            return s, zero_cost(True)
        return s, c
    if h.startswith("session"):
        return {"hand": "session", "from_run": None, "pkg": rel_to(pkg_dir, run)}, zero_cost()
    fr = None
    if x.get("src") and x["src"] != "write":
        m = re.match(r"(experiments/paifu_frames/results/[^/]+)", x["src"])
        fr = m.group(1) if m else None
    return {"hand": "replay", "from_run": fr, "pkg": rel_to(pkg_dir, run)}, zero_cost()


def game_file(run, g: str) -> Path:
    return Path(run) / "games" / f"{g}.json"


def turn_attempts(run, tid: str) -> list:
    d = Path(run) / "turns" / tid
    order = {"first": 0, "user": 99}
    names = [f.stem for f in d.glob("*.json")] if d.exists() else []

    def key(n):
        if n in order:
            return (order[n], 0)
        m = re.match(r"(s7r|r)(\d+)$", n)
        return (1 if m and m.group(1) == "s7r" else 2, int(m.group(2)) if m else 0)
    return sorted((n for n in names if ATTEMPT_RE.match(n)), key=key)


def build_game(run, g: str, status: str | None = None, agent: dict | None = None) -> dict:
    """판 결과 파일을 실행 폴더의 지금 파일들(순 결과 파일 · 준비 · 판 결과 · 판 꾸러미 · 마지막 검사)에서 다시 만든다(판 LLM 은 agent 칸만 — 도구로)."""
    import paifu_auto as pa
    run = Path(run).resolve()
    r = pa.Run(run)
    old = jl(game_file(run, g)) if game_file(run, g).exists() else {}
    # 준비 읽기(S6a)
    prep = None
    pf = run / "s6a" / g / "answer.json"
    if pf.exists():
        prep = dict(jl(pf))
        s, c = src_of_fill(run, f"s6a_{g}", pf.parent)
        prep["source"], prep["cost"] = s, c
    # 판 결과(S4)
    result = None
    rf = run / g / "result_read.json"
    if rf.exists():
        result = dict(jl(rf))
        reads, srcs, cost = {}, [], zero_cost()
        reused_all, orig = True, 0.0
        for d in sorted((run / "s4" / g).glob("*")) if (run / "s4" / g).exists() else []:
            for nm in ("reveal_read.json", "result_read.json", "answer.json"):
                if (d / nm).exists() and (d / "TASK.md").exists():
                    reads[d.name] = jl(d / nm)
                    s, c = src_of_fill(run, f"s4_{g}_{d.name}", d)
                    srcs.append({"pkg_id": f"s4_{g}_{d.name}", **s})
                    reused_all = reused_all and bool(c.get("reused"))
                    orig += float(s.get("orig_usd") or 0)
                    for k in ("calls", "in", "out", "cache_read", "cache_write", "usd", "seconds"):
                        cost[k] = round(cost[k] + c[k], 6) if isinstance(cost[k], float) else cost[k] + c[k]
                    break
        if reads:
            result["_reads"] = reads   # S4 꾸러미 답(앱 기록 길의 공개 읽기) — 판 결과 글은 위 칸 그대로
        result["source"] = {"hand": srcs[0]["hand"] if len({x["hand"] for x in srcs}) == 1 else ("mixed" if srcs else "code"),
                            "packages": srcs, "from_run": None, "pkg": None}
        if srcs and reused_all:   # 모두 베낀 꾸러미(캐시 · fork) — 옛 돈은 기록만
            cost["reused"] = True
            result["source"]["orig_usd"] = round(orig, 6)
        result["cost"] = cost
    # 순
    tids = list(pa.game_answer_ids(r, g)) if r.state else []
    pack = run / "sup" / g
    draft = jl(pack / "draft.json") if (pack / "draft.json").exists() else None
    dec = jl(pack / "decision.json") if (pack / "decision.json").exists() else None
    last = (draft or {}).get("checks") or []
    last = last[-1] if last else None
    s7 = (r.stage("S7").get("checks") or [{}])[-1].get("result", {}).get(g) if r.state else None
    if last:
        rep = Path(last.get("report") or "")
        chk = {"ok": bool(last["passed"]), "notes": [f"supervisor check {last['n']}: {'통과' if last['passed'] else '통과 못 함'}"
                                                    + (f" · 처음과 다른 초안 {last.get('changed_turns')}" if last.get("changed_turns") else ""),
                                                    f"보고서 {rel_to(rep, run) or rep.as_posix()}"]}
    elif s7 is not None:
        bad = [k for k in ("missing", "hand_count_problems", "four") if s7.get(k)]
        chk = {"ok": bool(s7.get("ok") and s7.get("hands") and not bad), "notes": ["S7 검사(처음 답)" + (f" — {', '.join(bad)}" if bad else "") + (f" · 오류 {s7.get('error')}" if s7.get("error") else "")]}
    else:
        chk = {"ok": None, "notes": ["검사 기록 없음"]}
    asks = {q["turn"]: {"candidates": q.get("candidates"), "why": q.get("why")} for q in ((dec or {}).get("asks") or (draft or {}).get("asks") or [])}
    turns = {}
    for t in tids:
        af = r.read / t / "answer.json"
        if not af.exists():
            continue
        a = jl(af)
        atts = turn_attempts(run, t)
        if a.get("user") and "user" in atts:
            fin = "user"
        elif dec and t in (dec.get("turns") or {}):
            v = dec["turns"][t]
            fin = v.get("from") if v.get("applied") else "first"
        elif (r.read / t / "answer_r0.json").exists():   # S7 다시 읽기가 바꿈
            fin = next((x for x in reversed(atts) if x.startswith("s7r")), "first")
        else:
            fin = "first"
        tc = "ok" if chk["ok"] else ("; ".join(chk["notes"]) if chk["ok"] is False else "검사 기록 없음")
        turns[t] = {"final": fin, "answer": answer_part(a, keep_user=bool(a.get("user"))), "kind": a.get("kind"), "attempts": atts,
                    "unsure": a.get("unsure"), "p": pa.answer_p(a), "check": tc, "ask": asks.get(t)}
    ag = agent if agent is not None else old.get("agent")
    if status is None:
        status = old.get("status") or "draft"
    doc = {"schema": SCHEMA_GAME, "game": g, "status": status, "prep": prep, "result": result, "turns": turns, "check": chk,
           "agent": ag, "cost_total": None, "at": now()}
    doc["cost_total"] = cost_total(run, doc)
    return doc


def cost_total(run, doc: dict) -> dict:
    """새로 쓴 돈(usd = usd_new) · 베낀 돈(usd_reused — 캐시 · fork 로 베낀 결과의 원래 돈, 기록만) · 답 없이 끊긴 시도 돈(usd_aborted — 이 실행에서 썼지만
    답 파일 돈에는 안 들어간 것, 기록만. 실행 한도는 graph/api_usage.jsonl 로 셈)."""
    new = reused = aborted = 0.0
    n_reused = 0

    def add(src, c):
        nonlocal new, reused, n_reused, aborted
        if not c:
            return
        if (src or {}).get("aborted") and not (src or {}).get("forked_from"):
            aborted += float(src["aborted"].get("usd") or 0)
        if c.get("reused"):
            n_reused += 1
            reused += float((src or {}).get("orig_usd") or 0)
        else:
            new += float(c.get("usd") or 0)
    if doc.get("prep"):
        add(doc["prep"].get("source"), doc["prep"].get("cost"))
    if doc.get("result"):
        add(doc["result"].get("source"), doc["result"].get("cost"))
    for t in doc["turns"]:
        for at in doc["turns"][t]["attempts"]:
            f = turn_file(run, t, at)
            if f.exists():
                x = jl(f)
                add(x["source"], x["cost"])
    if doc.get("agent"):
        add(doc["agent"].get("source"), doc["agent"].get("cost"))
    return {"usd": round(new, 6), "usd_new": round(new, 6), "usd_reused": round(reused, 6), "reused_items": n_reused, "usd_aborted": round(aborted, 6)}


def write_game(run, g: str, status: str | None = None, agent: dict | None = None) -> dict:
    doc = build_game(run, g, status, agent)
    with IDX_LOCK:
        wj(game_file(run, g), doc)
        _write_index(run)
    return doc


IDX_LOCK = threading.RLock()


def write_index(run):
    with IDX_LOCK:
        _write_index(run)


def _write_index(run):
    run = Path(run)
    rows = {}
    for f in sorted((run / "games").glob("*.json")):
        if f.name == "index.json":
            continue
        try:
            x = jl(f)
        except (json.JSONDecodeError, OSError):
            continue
        rows[x["game"]] = {"status": x["status"], "turns": len(x["turns"]), "asks": sum(1 for v in x["turns"].values() if v.get("ask")),
                           "actions": len(((x.get("agent") or {}).get("actions")) or []), "usd": (x.get("cost_total") or {}).get("usd"),
                           "usd_reused": (x.get("cost_total") or {}).get("usd_reused"), "file": f"games/{f.name}"}
    wj(run / "games" / "index.json", {"schema": "paifu.games_index/1", "at": now(), "games": rows,
                                      "total": {"games": len(rows), "usd": round(sum(v["usd"] or 0 for v in rows.values()), 6),
                                                "asks": sum(v["asks"] for v in rows.values())}})


def validate_game(doc: dict) -> list:
    e = []
    want = ("schema", "game", "status", "prep", "result", "turns", "check", "agent", "cost_total", "at")
    for k in want:
        if k not in doc:
            e.append(f"칸 없음 {k}")
    if e:
        return e
    if set(doc) - set(want):
        e.append(f"모르는 칸 {sorted(set(doc) - set(want))}")
    if doc["schema"] != SCHEMA_GAME:
        e.append("schema")
    if doc["status"] not in ("draft", "done", "closed_by_limit"):
        e.append(f"status {doc['status']!r}")
    for k in ("prep", "result"):
        v = doc[k]
        if v is not None and (not isinstance(v, dict) or "source" not in v or "cost" not in v):
            e.append(f"{k} 꼴(source · cost)")
    if not isinstance(doc["turns"], dict):
        e.append("turns 형")
    else:
        for t, v in doc["turns"].items():
            for k in ("final", "answer", "attempts", "unsure", "p", "check", "ask"):
                if k not in v:
                    e.append(f"turns.{t}.{k} 없음")
            if v.get("final") not in ("first", "set", "user") and not re.match(r"^(r|s7r)\d+$", str(v.get("final"))):
                e.append(f"turns.{t}.final {v.get('final')!r}")
            if not isinstance(v.get("attempts"), list) or "first" not in (v.get("attempts") or []):
                e.append(f"turns.{t}.attempts {v.get('attempts')}")
            if isinstance(v.get("answer"), dict) and set(v["answer"]) != set(ANS_KEYS) | {"extra"}:
                e.append(f"turns.{t}.answer 칸")
    c = doc["check"]
    if not isinstance(c, dict) or set(c) != {"ok", "notes"} or not isinstance(c["notes"], list):
        e.append("check 꼴")
    ag = doc["agent"]
    if ag is not None:
        for k in ("actions", "finish_refused", "report", "source", "cost"):
            if k not in ag:
                e.append(f"agent.{k} 없음")
        for x in ag.get("actions") or []:
            if x.get("do") not in ("reread", "take", "ask", "set"):
                e.append(f"agent.actions do {x.get('do')!r}")
    ct = doc["cost_total"]
    if not isinstance(ct, dict) or not {"usd", "usd_new", "usd_reused"} <= set(ct):
        e.append("cost_total 꼴")
    if doc["status"] != "draft" and ag is None:
        e.append("마감인데 agent 칸이 없음")
    return e


# ------------------------------------------------------------------ 캐시 찾기
class ReuseIndex:
    """--reuse-from 실행들의 순 결과 파일(turns/*/*.json — input 이 있는 것) · 판 결과 파일 prep/result input · 판 LLM 호출 기록(agent/<판>/calls.jsonl)."""

    def __init__(self, runs: list):
        self.runs = [Path(x).resolve() for x in runs]
        self.turn = {}
        self.pkgs = {}
        self.calls = {}
        self.backfilled = []
        for rr in self.runs:
            for f in sorted((rr / "turns").glob("*/*.json")) if (rr / "turns").exists() else []:
                try:
                    x = jl(f)
                except (json.JSONDecodeError, OSError):
                    continue
                if x.get("schema") != SCHEMA_TURN or not x.get("input") or x["source"].get("hand") == "user":
                    continue
                if not x["input"].get("inputs_sha256"):
                    continue   # 열쇠를 넓히기 전 결과 파일 — 대체에 안 씀
                k = (x["input"]["task_sha256"], x["input"]["images_sha256"], x["input"]["inputs_sha256"])
                self.turn.setdefault(k, (rr, f, x))
            for f in sorted((rr / "graph").glob("pkg_inputs.jsonl")) if (rr / "graph").exists() else []:
                for x in jlines(f):
                    if not x.get("inputs_sha256"):
                        continue
                    k = (x["task_sha256"], x["images_sha256"], x["inputs_sha256"])
                    self.pkgs.setdefault(k, (rr, x))
            if not any(k[0] == rr for k in [(v[0],) for v in self.turn.values()] + [(v[0],) for v in self.pkgs.values()]):
                self._backfill(rr)
            for f in sorted((rr / "agent").glob("*/calls.jsonl")) if (rr / "agent").exists() else []:
                for x in jlines(f):
                    if x.get("prefix_sha") and x.get("response") is not None:
                        self.calls.setdefault(x["prefix_sha"], (rr, x))

    def _backfill(self, rr: Path):
        """8-23 전에 돈 실행(예: 진짜 API 결과 auto_h2_apiR1 — 순 결과 파일 · pkg_inputs 가 없음): api 손이 채운 꾸러미(api_log.jsonl 이 있는 S6 · S6a 꾸러미)를
        그 자리에서 열쇠로 셈(원본은 읽기만). 열쇠에는 그 꾸러미 api_log 의 첫 시작 시각 앞에 있던 파일만 넣는다(손이 채우며 만든 try/ · 뒤 단계가 만든 answer_r0 등은 뺌).
        답은 처음 답(answer_r0 · answer_before_apply → answer). 실패한 꾸러미 · 끝 줄이 없는 꾸러미는 안 씀."""
        import paifu_auto as pa
        try:
            r = pa.Run(rr)
            cfg = r.cfg() if r.state else None
        except Exception:  # noqa: BLE001
            return
        cands = []
        for lg in sorted((rr / "read").glob("*/api_log.jsonl")) if (rr / "read").exists() else []:
            d = lg.parent
            if not (d / "answer.json").exists():
                continue
            a0 = next((f for f in (d / "answer_r0.json", d / "answer_before_apply.json", d / "answer.json") if f.exists()), None)
            kind = (jl(a0).get("kind") or "hand")
            cands.append(({"id": f"s6_{d.name}", "stage": "S6", "kind": "call" if kind == "call" else "hand", "dir": d.as_posix(), "task": (d / "TASK.md").as_posix(),
                           "answer": (d / "answer.json").as_posix(), "game": cfg.game_of(d.name) if cfg else None, "turn": d.name}, a0, lg))
        for lg in sorted((rr / "s6a").glob("*/api_log.jsonl")) if (rr / "s6a").exists() else []:
            d = lg.parent
            if (d / "answer.json").exists():
                cands.append(({"id": f"s6a_{d.name}", "stage": "S6a", "kind": "ht_prep", "dir": d.as_posix(), "task": (d / "TASK.md").as_posix(),
                               "answer": (d / "answer.json").as_posix(), "game": d.name}, d / "answer.json", lg))
        for p, a0, lg in cands:
            L = jlines(lg)
            st = [x for x in L if "start" in x]
            ends = [x for x in L if "end" in x]
            if not st or not ends or ends[-1].get("end") not in ("ok", "done", "answer", None) and "answer" not in str(ends[-1].get("end")):
                continue
            try:
                t_start = datetime.strptime(st[0]["at"], "%Y-%m-%d %H:%M:%S").timestamp()
                inp = pkg_input(rr, p, None, None, before=t_start + 1)
            except Exception:  # noqa: BLE001
                continue
            k = (inp["task_sha256"], inp["images_sha256"], inp["inputs_sha256"])
            usd = round(sum(float(x.get("usd") or 0) for x in L if "call" in x and "usd" in x and "tool" not in x), 6)
            if p["stage"] == "S6":
                doc = {"schema": SCHEMA_TURN, "game": p["game"], "turn": p["turn"], "attempt": "first", "kind": p["kind"], "answer": answer_part(jl(a0)),
                       "input": inp, "source": {"hand": "api", "from_run": rel_root(rr), "pkg": rel_to(Path(p["dir"]), rr), "note": "8-23 전 실행 — 그 자리에서 열쇠를 셈",
                                                "answer_file": Path(a0).name},
                       "cost": {**zero_cost(), "usd": usd}, "at": None}
                self.turn.setdefault(k, (rr, a0, doc))
            else:
                self.pkgs.setdefault(k, (rr, {"answer_rel": rel_to(Path(p["answer"]), rr), "hand": "api", "usd": usd, "backfill": True}))
            self.backfilled.append({"run": rr.name, "pkg": p["id"], "key": k[2][:12]})

    def find_turn(self, inp: dict):
        return self.turn.get((inp["task_sha256"], inp["images_sha256"], inp.get("inputs_sha256")))

    def find_pkg(self, inp: dict):
        return self.pkgs.get((inp["task_sha256"], inp["images_sha256"], inp.get("inputs_sha256")))

    def find_call(self, prefix: str):
        return self.calls.get(prefix)


# ------------------------------------------------------------------ export(옛 실행 → turns/ · games/)
def export(run, out=None) -> dict:
    """옛 실행(그래프 없이 돈 것 포함)에서 순 결과 파일 · 판 결과 파일을 만든다. out 이 있으면 <out>/turns · <out>/games 에(원본은 읽기만)."""
    import paifu_auto as pa
    run = Path(run).resolve()
    dst = Path(out).resolve() if out else run
    r = pa.Run(run)
    cfg = r.cfg()
    fills = fills_index(run)
    n = Counter()
    answered = set(r.state.get("answered") or [])

    def put(g, t, att, f, pid, pkg_dir, note=None):
        if pid in fills:
            s, c = src_of_fill(run, pid, pkg_dir)
        else:
            s, c = {"hand": "unknown", "from_run": None, "pkg": rel_to(pkg_dir, run), "note": "export — 손 기록 없음"}, zero_cost()
        if note:
            s["note"] = note
        inp = None
        p = {"id": pid, "stage": "S6", "kind": "hand", "dir": Path(pkg_dir).as_posix(), "task": (Path(pkg_dir) / "TASK.md").as_posix(),
             "answer": (Path(pkg_dir) / "answer.json").as_posix()}
        if (Path(pkg_dir) / "TASK.md").exists():
            try:
                inp = pkg_input(run, p, "hand" if att == "first" else "reread")
            except Exception as e:  # noqa: BLE001
                s["note"] = (s.get("note") or "") + f" · input 못 셈({type(e).__name__}: {e})"
        doc = turn_doc(run, g, t, att, jl(f), inp, s, c)
        wj(dst / "turns" / t / f"{att}.json", doc)
        n[att if not att.startswith("r") else "reread"] += 1
    for g in r.games():
        for t in pa.game_answer_ids(r, g):
            d = r.read / t
            if not (d / "answer.json").exists():
                continue
            ff = pa.first_answer_file(r, t, cfg)
            put(g, t, "first", ff, f"s6_{t}", d)
            for f in sorted((run / "sup" / g / "reread").glob(f"{t}_r*/answer.json")) if (run / "sup" / g / "reread").exists() else []:
                k = int(f.parent.name.rsplit("_r", 1)[1])
                put(g, t, f"r{k}", f, f"rr_{t}_r{k}", f.parent)
            for f in sorted(run.glob(f"read_r*/{t}/answer.json")):
                k = int(f.parent.parent.name[len("read_r"):])
                put(g, t, f"s7r{k}", f, f"s7_r{k}_{t}", f.parent)
            cur = jl(d / "answer.json")
            if cur.get("user") or t in answered:
                doc = turn_doc(run, g, t, "user", cur, None, {"hand": "user", "from_run": None, "pkg": rel_to(d, run),
                                                             "note": "사용자 확인값(apply 뒤 answer.json)"}, zero_cost())
                wj(dst / "turns" / t / "user.json", doc)
                n["user"] += 1
    if out is None:
        for g in r.games():
            if pa.game_answer_ids(r, g):
                st = "done" if (run / "sup" / g / "decision.json").exists() else "draft"
                ag = export_agent(run, g) if st == "done" else None
                write_game(run, g, st, ag)
                n["games"] += 1
    else:   # 원본 읽기만 — games 는 out 에(build_game 은 원본 실행의 turns/ 를 보므로 attempts 는 out 쪽으로 다시 셈)
        for g in r.games():
            if not pa.game_answer_ids(r, g):
                continue
            st = "done" if (run / "sup" / g / "decision.json").exists() else "draft"
            doc = build_game(run, g, st, export_agent(run, g) if st == "done" else None)
            for t, v in doc["turns"].items():
                v["attempts"] = turn_attempts(dst, t)
                if v["final"] == "first" and (dst / "turns" / t / "user.json").exists() and jl(run / "read" / t / "answer.json").get("user"):
                    v["final"] = "user"
            wj(dst / "games" / f"{g}.json", doc)
            n["games"] += 1
        write_index(dst)
    return dict(n)


def export_agent(run, g: str) -> dict:
    """옛 판 supervisor 꾸러미(draft · decision)에서 agent 칸 — 행동 · 거절 · 보고."""
    pack = Path(run) / "sup" / g
    dr = jl(pack / "draft.json") if (pack / "draft.json").exists() else {}
    acts = []
    for x in dr.get("rereads") or []:
        acts.append({"do": "reread", "turn": x["turn"], "frames": x.get("frames") or None, "why": "옛 판 supervisor"})
    for x in dr.get("takes") or []:
        acts.append({"do": "take", "turn": x["turn"], "from": x["from"], "why": "옛 판 supervisor"})
    for x in dr.get("sets") or []:
        acts.append({"do": "set", "turn": x["turn"], "why": x.get("why") or ""})
    for x in dr.get("asks") or []:
        acts.append({"do": "ask", "turn": x["turn"], "candidates": x.get("candidates"), "why": x.get("why") or ""})
    refused = [x.get("out", "")[:600] for x in jlines(pack / "log.jsonl") if x.get("cmd") == "done" and not x.get("ok")]
    return {"actions": acts, "finish_refused": refused, "report": "export — 옛 판 supervisor(그래프 밖) 기록에서 만듦",
            "source": {"hand": "unknown", "from_run": None, "pkg": f"sup/{g}"}, "cost": zero_cost()}


# ------------------------------------------------------------------ 검사 CLI
def validate_dir(d) -> dict:
    d = Path(d)
    bad, n = {}, Counter()
    for f in sorted((d / "turns").glob("*/*.json")) if (d / "turns").exists() else []:
        x = jl(f)
        e = validate_turn(x)
        if x.get("turn") != f.parent.name or x.get("attempt") != f.stem:
            e.append("파일 자리와 turn · attempt 가 다름")
        n["turn"] += 1
        if e:
            bad[f.relative_to(d).as_posix()] = e
    for f in sorted((d / "games").glob("*.json")) if (d / "games").exists() else []:
        x = jl(f)
        if f.name == "index.json":
            n["index"] += 1
            if x.get("schema") != "paifu.games_index/1" or not isinstance(x.get("games"), dict):
                bad[f.relative_to(d).as_posix()] = ["index 꼴"]
            continue
        e = validate_game(x)
        n["game"] += 1
        if e:
            bad[f.relative_to(d).as_posix()] = e
    return {"counts": dict(n), "bad": bad}


def main():
    ap = argparse.ArgumentParser(description="순별 · 판별 결과 파일(설계서 8-23) — LLM 0")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("export")
    p.add_argument("--run", required=True)
    p.add_argument("--out")
    p = sp.add_parser("validate")
    p.add_argument("--run")
    p.add_argument("--dir")
    p = sp.add_parser("input")
    p.add_argument("--run", required=True)
    p.add_argument("--pkg", required=True)
    a = ap.parse_args()
    if a.cmd == "export":
        print(json.dumps(export(ROOT / a.run if not Path(a.run).is_absolute() else a.run, a.out), ensure_ascii=False, indent=1))
    elif a.cmd == "validate":
        d = a.dir or a.run
        print(json.dumps(validate_dir(ROOT / d if not Path(d).is_absolute() else d), ensure_ascii=False, indent=1))
    else:
        d = Path(a.pkg).resolve()
        p = {"id": d.name, "stage": "S6", "kind": "hand", "dir": d.as_posix(), "task": (d / "TASK.md").as_posix(), "answer": (d / "answer.json").as_posix()}
        print(json.dumps(pkg_input(ROOT / a.run if not Path(a.run).is_absolute() else a.run, p), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
