"""대국 뒤 자동 패보 — 그래프의 `api` 손: 꾸러미(TASK.md + 답 파일)를 Claude API 로 채운다(설계서 docs/paifu_auto_agent_design_1124.md 8-21, 2026-11-26 오후).

원칙: 꾸러미의 TASK.md 를 바이트 그대로 첫 사용자 메시지로 보낸다(하위 에이전트 읽기와 같은 지시). Claude Code 도구 이름("Read 로 연다" ·
"Python(PIL)으로 잘라 키워" · "명령을 돌린다")은 고정 system 글 한 벌(SYSTEM)이 아래 도구로 옮겨 말한다. 코드 실행 도구는 없다.
도구(모든 종류가 같은 한 벌 — 종류마다 켠 것만 요청에 싣는다): list_files · read_text · view_image · view_strip · write_file · prep_try.
호출 꼴은 handtrack/claudeagent.py(11-19 실제로 돌린 고리)를 따른다: 모델 claude-opus-5-5 · output_config.effort high · thinking 안 줌(= adaptive) ·
tool_choice 안 줌(auto) · 스트리밍 + get_final_message · 수동 고리(응답 content 통째로 assistant 에 · 한 응답의 tool_result 는 한 user 메시지에) ·
캐싱(system 끝 블록 + 최상위 자동 cache_control) · 그림 긴 변 2576 · 요청당 그림 560장 · 120MB. fallbacks 는 넣지 않는다(한 모델의 읽기를 재는 실험).

진짜 호출 막기: 진짜 클라이언트는 real_client() 하나에서만 만들고, allow_real(True)(= paifu_graph 의 --i-mean-it)가 없으면 거절한다.
가짜 모드(arm_fake)는 .env · ANTHROPIC_API_KEY 를 읽지 않고, 이 프로세스의 ANTHROPIC_API_KEY 를 지우고, anthropic.Anthropic · AsyncAnthropic 을
부르면 예외가 나는 것으로 바꿔 둔다. 이 파일의 CLI(dry · fake · imgtest)는 진짜 호출 길이 없다.

  python -X utf8 experiments/paifu_frames/paifu_apihand.py dry     --pkg <종류>=<꾸러미 폴더> [...] --out <폴더>
  python -X utf8 experiments/paifu_frames/paifu_apihand.py fake    --pkg <종류>=<꾸러미 폴더> --answer-from <파일> [--script normal|guard]
                                                                    [--out-tokens 300] [--usage-dir <폴더>] [--max-usd 15]
  python -X utf8 experiments/paifu_frames/paifu_apihand.py imgtest --out <폴더>
종류: hand · call · reread · ht_prep · app_draw_reveal · result_read · boundary_read · manager.
기록: 꾸러미마다 <꾸러미>/api_log.jsonl(호출마다 토큰 · 달러 · 도구 이름 · 초, 도구 오류, 끝 줄), 실행마다 <실행>/graph/api_usage.jsonl ·
한도 <실행>/graph/api_limit.json.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HT = HERE / "handtrack"
_sp = list(sys.path)
sys.path.append(str(HT))
import claudeagent as ca  # noqa: E402  (모듈 맨 위에서 anthropic · dotenv 를 부르지 않음 — 단가 · 그림 한도 · .env 경로 · fit 만 씀)
sys.path[:] = _sp + [str(HT)]   # claudeagent 가 sys.path 맨 앞에 넣은 handtrack 을 뒤로(이름 겹침 막기)

MODEL = ca.MODEL                 # claude-opus-5-5
EFFORT = "high"                  # 하위 에이전트 Opus 높음과 맞춤
MAX_TOKENS = 32000               # claudeagent 기본과 같음(스트리밍)
PRICE = ca.PRICE                 # (입력, 출력, 캐시 읽기, 캐시 쓰기) 100만 토큰당 달러 — claudeagent.PRICE 그대로
LONG_EDGE = ca.LONG_EDGE         # 2576
MAX_IMAGES = ca.MAX_IMAGES       # 560
MAX_BYTES = ca.MAX_BYTES         # 120MB
ENV = ca.ENV
RUN_USD_DEFAULT = 15.0
PKG_USD = {"hand": 3.0, "call": 3.0, "reread": 3.0, "ht_prep": 6.0, "app_draw_reveal": 3.0, "result_read": 3.0, "boundary_read": 3.0, "manager": 3.0}
KINDS = tuple(PKG_USD)
MAX_CALLS = 150                  # 꾸러미 하나의 호출 수 안전띠(돈 한도가 먼저 걸리는 것이 보통)
FINAL_EXTRA = 2                  # 마지막 단계 글 뒤에 답을 기다려 줄 호출 수(claudeagent 와 같음)
RETRY_WAIT = 30.0                # 429 · 529 · 연결 오류: SDK 재시도 2번 뒤 이만큼 쉬고 한 번 더
STRIP_MAX = 32
TOOL_ORDER = ("list_files", "read_text", "view_image", "view_strip", "write_file", "prep_try")
IMG_TOOLS = ("view_image", "view_strip")
READ_EXT = {".md", ".txt", ".json", ".jsonl", ".csv", ".jpg", ".jpeg", ".png"}
IMG_EXT = {".jpg", ".jpeg", ".png"}
PATH_RE = re.compile(r"[A-Za-z]:[\\/][^\s`'\"<>|*?()\[\]{},;]+")
LIST_RE = re.compile(r"^(frames.*|events)\.txt$")
ANSWER_RE = re.compile(r"^(answer.*|reveal_read.*|result_read.*|decision.*)\.json$")
WALK_SKIP = {"raw", "prep", "rec", "overview", "logs", "work"}   # 목록 파일을 찾을 때 안 내려가는 폴더(그림 · 판별 출력 — try/<n>/frames_turns.txt 는 try/<n>/ 바로 밑)
MS_RE = re.compile(r"^f_(\d{13})\.(jpg|jpeg|png)$")
FINAL_TEXT = "볼 수 있는 단계를 다 썼다. 이제 그림 도구는 거절된다 — 지금까지 본 것으로 답 파일을 지시문의 꼴대로 write_file 로 쓰고 끝내라(확신이 낮은 칸은 지시문이 말하는 자리에 적는다)."
LOCK = threading.Lock()

SYSTEM = """너는 대국 뒤 패보 흐름의 작업자 하나다. 첫 사용자 메시지가 이 꾸러미의 지시문(TASK.md) 전부다. 그 지시대로 일해 답 파일 하나를 쓰고 끝낸다.
지시문은 Claude Code 하위 에이전트용으로 쓰여 있어 그쪽 도구 이름이 나온다. 여기에는 그 대신 아래 도구가 있다(이 요청에 실린 도구만 쓸 수 있다):

| 지시문의 말 | 여기서 쓰는 도구 |
|---|---|
| 글 파일을 연다 · 읽는다 | `read_text(path, offset, limit)` — 줄 번호가 붙어 온다 |
| 그림을 `Read` 로 연다 | `view_image(path)` |
| Python(PIL)으로 잘라 키운다 · 돌린다 · 선 · 상자 · 눈금을 그린다 | `view_image(path, crop, scale, rotate, boxes, grid)` — 그려서 바로 보여 준다(저장하지 않아도 된다) |
| 여러 프레임을 같은 자리로 잘라 이어 붙인다 | `view_strip(paths, crop, scale, cols, rotate)` — 한 장으로 이어 붙이고 칸마다 순번 · 프레임 번호 · 시각을 박는다 |
| `ls` · Glob · `os.listdir` 로 이름을 읽어 정렬하고 이분 탐색으로 고른다 | `list_files(dir, name_from, name_to, contains, offset, limit)` — 이름 순. 이름 범위로 자를 수 있고, 이름이 `f_<epoch ms>.jpg` 이면 이 PC 현지 시각(KST)이 붙는다 |
| 파일을 쓴다(초안 · 메모 · 답) | `write_file(path, text)` — 꾸러미의 `work/` 아래와 답 파일 경로에만 쓸 수 있다 |
| `python -X utf8 …/handtrack_prep.py try --pack <꾸러미> --answer <초안>` 를 돌린다 | `prep_try(draft)` — 초안(`work/` 아래 JSON)으로 그 명령을 그대로 돌리고 표준 출력을 돌려준다(횟수 한도 · 거절도 그 명령 그대로) |

- 그 밖의 명령 · 스크립트를 돌리는 도구는 없다. 지시문이 스크립트로 하라는 일(자르기 · 키우기 · 돌리기 · 이어 붙이기 · 선 · 눈금 그리기)은 위 그림 도구로 한다.
- 그림 좌표는 모두 그 그림 파일의 원본 화소 `[x0, y0, x1, y1]`(왼쪽 위 (0, 0)). `view_image` 는 원본에 grid(그 화소 간격의 눈금 · 좌표 글자) · boxes 를 그린 뒤 crop 으로 자르고, rotate(도 — PIL `Image.rotate(각, expand=True)` 와 같은 반시계)로 돌리고, scale 배로 키운다. `view_strip` 도 같은 순서(눈금 · 상자 없음). 보내는 그림은 긴 변이 2576 화소를 넘지 않게 줄어든다(돌려주는 글에 실제 배율이 적힌다).
- 경로는 절대 경로 또는 이 꾸러미 폴더 기준 상대 경로. 읽을 수 있는 곳은 이 꾸러미 폴더, 그리고 지시문 · 프레임 목록 파일에 적힌 경로다. 그 밖은 도구가 거절한다. 지시문이 "열지 않는다 · 보면 안 된다" 고 한 것은 읽을 수 있는 곳 안이라도 그대로 지킨다.
- 끝: 답 파일을 지시문의 꼴대로 `write_file` 로 쓴 뒤, 지시문이 말하는 마지막 답변을 도구 없이 글로 낸다.
"""


class ApiStop(Exception):
    """실행 한도(--max-usd)에 걸림 — 그래프가 stop(종료 코드 2)으로 멈춘다."""


class ApiFail(Exception):
    """꾸러미 하나가 실패(꾸러미 한도 · refusal · 오류 · 답 없음) — 그래프가 error 로 멈추고 사람에게 보고."""


# ------------------------------------------------------------------ 진짜 호출 막기
_REAL = {"ok": False, "client": None}
FAKE = {"on": False}


class _Forbidden:
    def __init__(self, *a, **k):
        raise RuntimeError("가짜 모드에서 진짜 Anthropic 클라이언트를 만들려 함 — 막음(paifu_apihand.arm_fake)")


def arm_fake():
    """가짜 모드: 진짜 클라이언트 · 키 읽기 길을 이 프로세스에서 닫는다."""
    FAKE["on"] = True
    _REAL["ok"] = False
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
    import anthropic
    anthropic.Anthropic = _Forbidden
    anthropic.AsyncAnthropic = _Forbidden
    anthropic.Client = _Forbidden


def allow_real(flag: bool):
    if flag and FAKE["on"]:
        raise RuntimeError("가짜 모드와 --i-mean-it 을 같이 쓸 수 없음")
    _REAL["ok"] = bool(flag)


def real_client():
    """진짜 클라이언트(프로세스에 하나). allow_real(True) 가 없거나 가짜 모드면 거절. 키는 claudeagent 와 같은 .env 에서 읽어 클라이언트에만 넘긴다."""
    if FAKE["on"]:
        raise RuntimeError("가짜 모드에서 real_client 를 부름 — 막음")
    if not _REAL["ok"]:
        raise RuntimeError("진짜 API 호출은 --i-mean-it 이 있어야 함")
    with LOCK:
        if _REAL["client"] is None:
            from dotenv import load_dotenv
            load_dotenv(ENV)
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise ApiFail(f"ANTHROPIC_API_KEY 가 .env({ENV})에 없음")
            import anthropic
            _REAL["client"] = anthropic.Anthropic(max_retries=2)
    return _REAL["client"]


# ------------------------------------------------------------------ 작은 도구
def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def nc(p) -> str:
    return os.path.normcase(str(Path(p).resolve()))


def under(child, parent) -> bool:
    c, p = nc(child), nc(parent)
    return c == p or c.startswith(p.rstrip("\\/") + os.sep)


def append(f: Path, o: dict):
    f.parent.mkdir(parents=True, exist_ok=True)
    with LOCK:
        with open(f, "a", encoding="utf-8", newline="\n") as h:
            h.write(json.dumps(o, ensure_ascii=False) + "\n")


def jlines(f: Path) -> list:
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()] if f.exists() else []


def kst(ms: int) -> str:
    dt = datetime.fromtimestamp(ms / 1000)
    return f"{dt:%H:%M:%S}.{dt.microsecond // 100000}"


def jpg(im: Image.Image, q: int = 88) -> bytes:
    b = io.BytesIO()
    im.save(b, "JPEG", quality=q)
    return b.getvalue()


def font(sz: int):
    for f in ("malgunbd.ttf", "malgun.ttf", "arialbd.ttf"):
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            continue
    return ImageFont.load_default()


def short(v, n=300):
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    return s if len(s) <= n else s[:n] + f"…(+{len(s) - n}자)"


def kind_of(p: dict) -> str:
    st, k = p.get("stage"), p.get("kind")
    if st == "manager" or k == "manager":
        return "manager"
    if st == "S6a":
        return "ht_prep"
    if st == "S4":
        return "app_draw_reveal" if k == "app_draw_reveal" else "result_read"
    if st == "S1":
        return "boundary_read"
    if st == "S6":
        return "call" if k == "call" else "hand"
    if st in ("S7", "sup_reread"):
        return "reread"
    if k in KINDS:
        return k
    raise ApiFail(f"api 손이 모르는 꾸러미 종류: stage {st} · kind {k}")


def tools_on(kind: str) -> list:
    on = ["list_files", "read_text", "write_file"]
    if kind != "manager":
        on += list(IMG_TOOLS)
    if kind == "ht_prep":
        on.append("prep_try")
    return [t for t in TOOL_ORDER if t in on]


# ------------------------------------------------------------------ 길 지키기
class Guard:
    """읽을 수 있는 곳 · 쓸 수 있는 곳(설계서 8-21 "읽을 수 있는 곳" — 정한 규칙은 아래).
    읽기: ① 꾸러미 폴더 안 전부(답 파일은 아직 안 넘긴 사본을 보여 줌 · 손 기록 api_log · 사본은 숨김)
          ② TASK.md 에 적힌 절대 경로 — 폴더면 그 아래 전부, 파일이면 그 파일(글 · 그림 확장자만, .py 는 안 됨).
             없는 경로는 바로 위 폴더 하나만 봄(예 `…\\rec_…\\f_<epoch ms>.jpg` → 프레임 폴더). 꾸러미 폴더를 품는 폴더(실행 폴더 등) · 저장소 루트 위는 넣지 않음.
          ③ 꾸러미 안 목록 파일(frames*.txt · events.txt — 어느 깊이든, work/ 안은 빼고 · try/*/frames_turns.txt 포함)에 적힌 절대 경로 — 그 파일만.
          관리자가 아닌 종류는 꾸러미 밖의 답 파일(answer* · reveal_read* · result_read* · decision*) · 남의 work/ 를 ② 안이라도 거절
          (다시 읽기 TASK 가 처음 읽기 폴더를 적어 두기 때문 — 독립 읽기를 지킴).
    쓰기: 꾸러미의 work/ 아래 · 답 파일 경로(답은 끝날 때까지 사본 `.<이름>.api_pending` 에 — 끝에 한 번 넘김)."""

    def __init__(self, p: dict, kind: str):
        self.kind = kind
        self.dir = Path(p["dir"]).resolve()
        self.answer = Path(p["answer"]).resolve()
        self.task = Path(p["task"]).resolve()
        self.work = self.dir / "work"
        self.pending = self.answer.with_name("." + self.answer.name + ".api_pending")
        self.task_dirs, self.task_files = [], set()
        for tok in PATH_RE.findall(self.task.read_text(encoding="utf-8")):
            self._add_task(tok)
        self._lists = {"sig": None, "files": set(), "labels": {}}

    def _add_task(self, tok: str):
        tok = tok.rstrip(".,:;`'")
        q = Path(tok.replace("\\", "/"))
        if not q.exists():
            if q.parent.exists() and q.parent.is_dir() and q.parent != q:
                q = q.parent
            else:
                return
        q = q.resolve()
        if q.is_dir():
            if under(self.dir, q) or under(ROOT, q) or under(q, self.dir):
                return   # 꾸러미를 품는 폴더 · 저장소 루트 위 · 꾸러미 안(이미 됨)
            if not any(nc(q) == nc(d) for d in self.task_dirs):
                self.task_dirs.append(q)
        elif q.suffix.lower() in READ_EXT:
            self.task_files.add(nc(q))

    def list_files_in_pkg(self) -> list:
        out = []
        for root, dirs, files in os.walk(self.dir):
            if under(root, self.work):
                dirs[:] = []
                continue
            dirs[:] = [x for x in dirs if x not in WALK_SKIP]
            for f in files:
                if LIST_RE.match(f):
                    out.append(Path(root) / f)
        return sorted(out)

    def lists(self) -> dict:
        fs = self.list_files_in_pkg()
        sig = tuple((str(f), f.stat().st_mtime_ns, f.stat().st_size) for f in fs)
        if sig != self._lists["sig"]:
            files, labels = set(), {}
            for f in fs:
                for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
                    m = PATH_RE.search(ln)
                    if not m:
                        continue
                    q = Path(m.group(0).rstrip(".,:;").replace("\\", "/"))
                    files.add(nc(q))
                    lab = ln[:m.start()].strip().replace("\t", " ")
                    if lab and nc(q) not in labels:
                        labels[nc(q)] = lab
            self._lists = {"sig": sig, "files": files, "labels": labels}
        return self._lists

    def resolve(self, path) -> Path:
        if not isinstance(path, str) or not path.strip():
            raise ValueError("경로가 비었음")
        q = Path(path.strip().replace("\\", "/"))
        if not q.is_absolute():
            q = self.dir / q
        return q.resolve()

    def hidden(self, q: Path) -> bool:
        return under(q, self.dir) and (q.name.endswith(".api_pending") or q.name.startswith("api_log"))

    def read_target(self, path) -> Path:
        """읽어도 되면 실제로 열 경로(답 파일이면 사본), 아니면 PermissionError · 없으면 FileNotFoundError."""
        q = self.resolve(path)
        if nc(q) == nc(self.answer):
            if self.pending.exists():
                return self.pending
            raise FileNotFoundError(f"아직 안 쓴 답 파일: {q.as_posix()}")
        if self.hidden(q):
            raise PermissionError(f"손 기록 파일은 읽지 않는다: {q.as_posix()}")
        ok = under(q, self.dir)
        if not ok:
            if self.kind != "manager":
                if ANSWER_RE.match(q.name):
                    raise PermissionError(f"다른 꾸러미의 답 파일은 읽을 수 없다: {q.as_posix()}")
                if "work" in [x.lower() for x in q.parts]:
                    raise PermissionError(f"다른 꾸러미의 작업 폴더는 읽을 수 없다: {q.as_posix()}")
            ok = any(under(q, d) for d in self.task_dirs) or nc(q) in self.task_files or nc(q) in self.lists()["files"]
        if not ok:
            raise PermissionError(f"읽을 수 있는 곳 밖: {q.as_posix()} — 이 꾸러미 폴더와 지시문 · 프레임 목록에 적힌 경로만")
        if not q.exists():
            raise FileNotFoundError(f"없는 파일: {q.as_posix()}")
        return q

    def write_target(self, path) -> Path:
        q = self.resolve(path)
        if nc(q) == nc(self.answer):
            return self.pending
        if under(q, self.work) and nc(q) != nc(self.work):
            return q
        raise PermissionError(f"쓸 수 있는 곳 밖: {q.as_posix()} — 이 꾸러미의 work/ 아래와 답 파일({self.answer.as_posix()})만")

    def label(self, q: Path) -> str:
        lab = self.lists()["labels"].get(nc(q))
        m = MS_RE.match(q.name)
        if m and not lab:
            lab = kst(int(m.group(1)))
        return lab or q.name


# ------------------------------------------------------------------ 도구
def tool_defs(kind: str) -> list:
    num = {"type": "number"}
    it = {"type": "integer"}
    box4 = {"type": "array", "items": num, "minItems": 4, "maxItems": 4}
    D = {
        "list_files": {"name": "list_files", "description": "폴더 안 이름 · 크기(이름 순). name_from · name_to 로 이름 범위, contains 로 글자 포함, offset · limit(기본 200, 최대 1000)으로 자른다. f_<epoch ms>.jpg 는 KST 시각이 붙는다.",
                       "input_schema": {"type": "object", "properties": {"dir": {"type": "string"}, "name_from": {"type": "string"}, "name_to": {"type": "string"},
                                                                         "contains": {"type": "string"}, "offset": it, "limit": it},
                                        "required": ["dir"], "additionalProperties": False}},
        "read_text": {"name": "read_text", "description": "글 파일을 줄 번호와 함께 읽는다(offset = 시작 줄 1부터, limit = 줄 수 기본 2000).",
                      "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "offset": it, "limit": it},
                                       "required": ["path"], "additionalProperties": False}},
        "view_image": {"name": "view_image", "description": "그림 한 장을 본다. 원본에 grid(눈금 간격 화소) · boxes 를 그리고 → crop [x0,y0,x1,y1](원본 화소) → rotate(반시계 도, expand) → scale 배.",
                       "input_schema": {"type": "object", "properties": {
                           "path": {"type": "string"}, "crop": box4, "scale": num, "rotate": num, "grid": it,
                           "boxes": {"type": "array", "items": {"type": "object", "properties": {"box": box4, "color": {"type": "string"}, "label": {"type": "string"}},
                                                                "required": ["box"], "additionalProperties": False}}},
                           "required": ["path"], "additionalProperties": False}},
        "view_strip": {"name": "view_strip", "description": "여러 그림을 같은 crop · rotate · scale 로 잘라 한 장에 이어 붙인다(cols 열, 칸마다 순번 · 프레임 번호 · 시각). 한 번에 32장까지.",
                       "input_schema": {"type": "object", "properties": {"paths": {"type": "array", "items": {"type": "string"}}, "crop": box4, "scale": num,
                                                                         "cols": it, "rotate": num},
                                        "required": ["paths"], "additionalProperties": False}},
        "write_file": {"name": "write_file", "description": "글 파일을 쓴다(UTF-8, 통째로 덮어씀). 꾸러미의 work/ 아래와 답 파일 경로에만.",
                       "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "text": {"type": "string"}},
                                        "required": ["path", "text"], "additionalProperties": False}},
        "prep_try": {"name": "prep_try", "description": "handtrack_prep.py try --pack <이 꾸러미> --answer <draft> 를 그대로 돌리고 표준 출력을 돌려준다. draft 는 work/ 아래 JSON.",
                     "input_schema": {"type": "object", "properties": {"draft": {"type": "string"}}, "required": ["draft"], "additionalProperties": False}},
    }
    return [D[t] for t in tools_on(kind)]


_LISTDIR: dict = {}


def t_list_files(G: Guard, a: dict) -> str:
    q = G.read_target(a["dir"])
    if not q.is_dir():
        raise NotADirectoryError(f"폴더가 아님: {q.as_posix()}")
    st = q.stat().st_mtime_ns
    k = nc(q)
    if _LISTDIR.get(k, (None,))[0] != st:
        _LISTDIR[k] = (st, sorted(os.listdir(q)))
    names = [n for n in _LISTDIR[k][1] if not G.hidden(q / n)]
    lo, hi, has = a.get("name_from"), a.get("name_to"), a.get("contains")
    sel = [n for n in names if (lo is None or n >= lo) and (hi is None or n <= hi) and (not has or has in n)]
    off = max(0, int(a.get("offset") or 0))
    lim = max(1, min(1000, int(a.get("limit") or 200)))
    part = sel[off:off + lim]
    rows = []
    for n in part:
        f = q / n
        if f.is_dir():
            rows.append(f"{n}/")
            continue
        m = MS_RE.match(n)
        rows.append(f"{n}\t{f.stat().st_size}" + (f"\t{kst(int(m.group(1)))}" if m else ""))
    head = f"{q.as_posix()} — 전체 {len(names)}개 · 조건에 맞는 것 {len(sel)}개 · 보여 줌 {off + 1 if part else 0}~{off + len(part)}"
    return head + "\n" + "\n".join(rows)


def t_read_text(G: Guard, a: dict) -> str:
    q = G.read_target(a["path"])
    if q.is_dir():
        raise IsADirectoryError(f"폴더임 — list_files: {q.as_posix()}")
    if q.suffix.lower() in IMG_EXT:
        raise ValueError(f"그림 파일 — view_image 로 연다: {q.as_posix()}")
    L = q.read_bytes().decode("utf-8", errors="replace").split("\n")
    off = max(1, int(a.get("offset") or 1))
    lim = max(1, min(5000, int(a.get("limit") or 2000)))
    out, size = [], 0
    for i in range(off - 1, min(len(L), off - 1 + lim)):
        ln = L[i] if len(L[i]) <= 3000 else L[i][:3000] + "…(줄 잘림)"
        out.append(f"{i + 1:6d}\t{ln}")
        size += len(ln)
        if size > 120_000:
            out.append(f"…(12만 자에서 잘림 — offset {i + 2} 로 이어 읽어라)")
            break
    return f"{(G.answer if q == G.pending else q).as_posix()} — 전체 {len(L)}줄\n" + "\n".join(out)


def _crop_box(im: Image.Image, crop) -> tuple:
    if not crop:
        return (0, 0, im.width, im.height)
    x0, y0, x1, y1 = [int(round(float(v))) for v in crop]
    x0, x1 = sorted((max(0, min(im.width, x0)), max(0, min(im.width, x1))))
    y0, y1 = sorted((max(0, min(im.height, y0)), max(0, min(im.height, y1))))
    if x1 - x0 < 4 or y1 - y0 < 4:
        raise ValueError(f"crop 이 너무 작거나 그림 밖: {crop} (그림 {im.width}×{im.height})")
    return (x0, y0, x1, y1)


def _transform(im: Image.Image, crop, rotate, scale) -> tuple:
    """crop → rotate → scale. 긴 변이 LONG_EDGE 를 넘을 배율은 미리 낮춤(→ 실제 배율 · 설명)."""
    b = _crop_box(im, crop)
    im = im.crop(b)
    r = float(rotate or 0) % 360
    if r:
        im = im.rotate(r, expand=True, resample=Image.BICUBIC, fillcolor=(255, 255, 255))
    s_req = float(scale or 1)
    if not (0.05 <= s_req <= 10):
        raise ValueError(f"scale {s_req} — 0.05 ~ 10 만")
    s = min(s_req, LONG_EDGE / max(im.size))
    if abs(s - 1) > 1e-6:
        im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    return im, b, r, s_req, s


COLORS = {"red": (230, 30, 30), "green": (20, 180, 40), "blue": (30, 90, 240), "yellow": (250, 210, 0), "cyan": (0, 200, 230),
          "magenta": (230, 0, 200), "white": (255, 255, 255), "black": (0, 0, 0), "orange": (255, 140, 0)}


def t_view_image(G: Guard, a: dict) -> list:
    q = G.read_target(a["path"])
    if q.suffix.lower() not in IMG_EXT:
        raise ValueError(f"그림 파일이 아님: {q.as_posix()}")
    im = Image.open(q).convert("RGB")
    W, H = im.size
    if a.get("grid") or a.get("boxes"):
        dr = ImageDraw.Draw(im)
        g = int(a.get("grid") or 0)
        if g:
            if g < 10:
                raise ValueError("grid 는 10 화소 이상")
            ft = font(max(12, min(W, H) // 80))
            for x in range(0, W, g):
                dr.line([(x, 0), (x, H)], fill=(255, 255, 0), width=1)
                dr.text((x + 2, 2), str(x), fill=(255, 255, 0), font=ft)
            for y in range(0, H, g):
                dr.line([(0, y), (W, y)], fill=(255, 255, 0), width=1)
                dr.text((2, y + 2), str(y), fill=(255, 255, 0), font=ft)
        ft = font(max(14, min(W, H) // 60))
        for bx in a.get("boxes") or []:
            c = COLORS.get(str(bx.get("color") or "red").lower(), (230, 30, 30))
            x0, y0, x1, y1 = [float(v) for v in bx["box"]]
            dr.rectangle([min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)], outline=c, width=max(2, W // 500))
            if bx.get("label"):
                dr.text((min(x0, x1) + 3, min(y0, y1) + 3), str(bx["label"]), fill=c, font=ft)
    out, b, r, s_req, s = _transform(im, a.get("crop"), a.get("rotate"), a.get("scale"))
    desc = (f"{q.as_posix()} 원본 {W}×{H} · crop {list(b)} · rotate {r:g} · scale {s_req:g}" + (f"→{s:.3g}(긴 변 {LONG_EDGE})" if abs(s - s_req) > 1e-6 else "")
            + f" → 보낸 그림 {out.width}×{out.height}" + (f" · 눈금 {a['grid']}" if a.get("grid") else "") + (f" · 상자 {len(a['boxes'])}" if a.get("boxes") else ""))
    return [(desc, jpg(out))]


def t_view_strip(G: Guard, a: dict) -> list:
    paths = list(a.get("paths") or [])
    if not paths:
        raise ValueError("paths 가 비었음")
    if len(paths) > STRIP_MAX:
        raise ValueError(f"한 번에 {STRIP_MAX}장까지(받은 {len(paths)}장)")
    qs = [G.read_target(x) for x in paths]
    tiles, labels = [], []
    for k, q in enumerate(qs):
        if q.suffix.lower() not in IMG_EXT:
            raise ValueError(f"그림 파일이 아님: {q.as_posix()}")
        im, b, r, s_req, s = _transform(Image.open(q).convert("RGB"), a.get("crop"), a.get("rotate"), a.get("scale"))
        tiles.append(im)
        labels.append(f"#{k + 1} {G.label(q)}")
    cols = max(1, min(len(tiles), int(a.get("cols") or 1)))
    rows = (len(tiles) + cols - 1) // cols
    tw, th = max(t.width for t in tiles), max(t.height for t in tiles)
    bar = 30
    sheet = Image.new("RGB", (cols * (tw + 4), rows * (th + bar + 4)), (255, 255, 255))
    dr = ImageDraw.Draw(sheet)
    ft = font(20)
    for k, (t, lab) in enumerate(zip(tiles, labels)):
        x, y = (k % cols) * (tw + 4), (k // cols) * (th + bar + 4)
        dr.text((x + 4, y + 4), lab, fill=(0, 0, 0), font=ft)
        sheet.paste(t, (x, y + bar))
    s2 = min(1.0, LONG_EDGE / max(sheet.size))
    if s2 < 1:
        sheet = sheet.resize((max(1, int(sheet.width * s2)), max(1, int(sheet.height * s2))), Image.LANCZOS)
    desc = (f"strip {len(tiles)}장 · {cols}열 · crop {a.get('crop')} · rotate {float(a.get('rotate') or 0):g} · scale {float(a.get('scale') or 1):g}"
            + (f"(칸 실제 {s:.3g})" if abs(s - float(a.get('scale') or 1)) > 1e-6 else "") + (f" · 한 장 줄임 {s2:.3g}" if s2 < 1 else "")
            + f" → 보낸 그림 {sheet.width}×{sheet.height} | " + " · ".join(labels))
    return [(desc, jpg(sheet))]


def form_error(kind: str, text: str):
    """답 꼴 검사 — 맞으면 None. 차례 읽기 · 다시 읽기는 paifu_auto.answer_form_error, 관리자는 games 칸, 나머지는 JSON 객체."""
    try:
        o = json.loads(text)
    except json.JSONDecodeError as e:
        return f"JSON 이 아님: {e}"
    if not isinstance(o, dict):
        return "JSON 객체가 아님"
    if kind in ("hand", "call", "reread"):
        import paifu_auto as pa
        return pa.answer_form_error(o)
    if kind == "manager":
        g = o.get("games")
        if not isinstance(g, dict) or not all(isinstance(v, list) for v in g.values()):
            return "games 칸(판 → 결정 목록)이 없음"
    return None


def t_write_file(G: Guard, a: dict) -> str:
    q = G.write_target(a["path"])
    text = a.get("text")
    if not isinstance(text, str):
        raise ValueError("text 는 글")
    b = text.encode("utf-8")
    if len(b) > 4 * 2 ** 20:
        raise ValueError("4MB 넘는 글은 쓰지 않음")
    q.parent.mkdir(parents=True, exist_ok=True)
    q.write_bytes(b)
    if q == G.pending:
        why = form_error(G.kind, text)
        return f"답 파일 {G.answer.as_posix()} 를 썼다({len(b)}바이트) · 답 꼴 검사: " + ("통과" if why is None else f"문제 — {why}")
    return f"{q.as_posix()} 를 썼다({len(b)}바이트)"


def t_prep_try(G: Guard, a: dict) -> str:
    q = G.resolve(a["draft"])
    if not (under(q, G.work) and nc(q) != nc(G.work)):
        raise PermissionError(f"초안은 work/ 아래에만: {q.as_posix()}")
    if not q.exists():
        raise FileNotFoundError(f"없는 초안: {q.as_posix()}")
    cmd = [sys.executable, "-X", "utf8", str(HERE / "handtrack_prep.py"), "try", "--pack", G.dir.as_posix(), "--answer", q.as_posix()]
    t0 = time.time()
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800,
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    out = p.stdout or ""
    if len(out) > 40_000:
        out = out[:20_000] + "\n…(가운데 잘림)…\n" + out[-20_000:]
    err = ("\n--- stderr(끝)\n" + (p.stderr or "")[-3000:]) if p.returncode else ""
    return f"handtrack_prep.py try 끝 — rc {p.returncode} · {time.time() - t0:.0f}초\n{out}{err}"


TOOL_FN = {"list_files": t_list_files, "read_text": t_read_text, "view_image": t_view_image, "view_strip": t_view_strip,
           "write_file": t_write_file, "prep_try": t_prep_try}


# ------------------------------------------------------------------ 돈 셈
class Meter:
    """실행 하나의 돈 — <graph>/api_usage.jsonl(호출마다 한 줄)을 처음에 한 번 더해 두고 더해 감. 한도 = <graph>/api_limit.json max_usd."""

    def __init__(self, gd: Path):
        self.gd = Path(gd)
        self.f = self.gd / "api_usage.jsonl"
        self.lim = self.gd / "api_limit.json"
        self.total = sum(float(x.get("usd") or 0) for x in jlines(self.f))
        self.calls = len(jlines(self.f))

    def limit(self) -> float:
        if self.lim.exists():
            return float(json.loads(self.lim.read_text(encoding="utf-8")).get("max_usd") or RUN_USD_DEFAULT)
        return RUN_USD_DEFAULT

    def check(self, pid: str):
        with LOCK:
            t, lim = self.total, self.limit()
        if t >= lim:
            raise ApiStop(f"실행 한도 {lim:g}달러에 닿음(쓴 돈 {t:.4f}달러) — {pid} 앞에서 멈춤. 이어 가려면 resume --max-usd <더 큰 값>")

    def add(self, row: dict):
        append(self.f, row)
        with LOCK:
            self.total += float(row.get("usd") or 0)
            self.calls += 1


_METERS: dict = {}


def meter_of(gd: Path) -> Meter:
    k = nc(gd)
    with LOCK:
        if k not in _METERS:
            _METERS[k] = None
    if _METERS[k] is None:
        _METERS[k] = Meter(gd)
    return _METERS[k]


def set_limit(gd: Path, usd: float):
    gd.mkdir(parents=True, exist_ok=True)
    with open(gd / "api_limit.json", "w", encoding="utf-8", newline="\n") as h:
        h.write(json.dumps({"max_usd": float(usd), "at": now()}, ensure_ascii=False))


def usd_of(u, model=MODEL) -> tuple:
    p_in, p_out, p_cr, p_cw = PRICE[model]
    ui, uo = u.input_tokens or 0, u.output_tokens or 0
    cr, cw = u.cache_read_input_tokens or 0, u.cache_creation_input_tokens or 0
    return (ui * p_in + uo * p_out + cr * p_cr + cw * p_cw) * 1e-6, {"in": ui, "out": uo, "cache_read": cr, "cache_write": cw}


def usage_summary(gd: Path) -> dict:
    L = jlines(Path(gd) / "api_usage.jsonl")
    by = {}
    for x in L:
        b = by.setdefault(x.get("pkg"), {"calls": 0, "usd": 0.0, "kind": x.get("kind")})
        b["calls"] += 1
        b["usd"] = round(b["usd"] + float(x.get("usd") or 0), 6)
    lim = Path(gd) / "api_limit.json"
    return {"calls": len(L), "usd": round(sum(float(x.get("usd") or 0) for x in L), 6),
            "max_usd": json.loads(lim.read_text(encoding="utf-8")).get("max_usd") if lim.exists() else None, "packages": by}


# ------------------------------------------------------------------ 요청 · 고리
def build_request(p: dict, kind: str) -> tuple:
    """첫 요청의 (매 호출 같은 앞부분 kw, messages). TASK.md 는 바이트 그대로(UTF-8 풀기만)."""
    task = Path(p["task"]).read_bytes().decode("utf-8")
    kw = {"model": MODEL, "max_tokens": MAX_TOKENS,
          "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
          "tools": tool_defs(kind), "output_config": {"effort": EFFORT}, "cache_control": {"type": "ephemeral"}}
    return kw, [{"role": "user", "content": [{"type": "text", "text": task}]}]


def call(client, kw: dict, msgs: list):
    """스트리밍 + get_final_message. 429 · 5xx(529 포함) · 연결 오류는 SDK 재시도(2번) 뒤 RETRY_WAIT 초 쉬고 한 번 더. 그 밖(400 등)은 바로 올림."""
    import anthropic
    err = None
    for attempt in (0, 1):
        try:
            with client.messages.stream(messages=msgs, **kw) as st:
                return st.get_final_message(), attempt
        except anthropic.APIConnectionError as e:
            err = e
        except anthropic.APIStatusError as e:
            if e.status_code != 429 and e.status_code < 500:
                raise
            err = e
        if attempt == 0:
            time.sleep(RETRY_WAIT)
    raise err


def run_package(p: dict, client, meter: Meter, kind: str | None = None) -> dict:
    """꾸러미 하나를 끝까지. → {"status": ok | budget | refusal | no_answer | max_tokens | error, ...}. 실행 한도는 ApiStop 으로 올림."""
    kind = kind or kind_of(p)
    G = Guard(p, kind)
    log = G.dir / "api_log.jsonl"
    limit = PKG_USD[kind]
    on = tools_on(kind)
    kw, msgs = build_request(p, kind)
    if G.pending.exists():
        G.pending.unlink()   # 앞에서 끊긴 시도의 사본(새 대화로 처음부터)
    append(log, {"at": now(), "start": p["id"], "kind": kind, "model": MODEL, "effort": EFFORT, "tools": on, "pkg_usd_limit": limit,
                 "task_bytes": len(Path(p["task"]).read_bytes())})
    usd, calls, nudged, final, final_left, t0 = 0.0, 0, False, None, FINAL_EXTRA, time.time()
    status, why = None, None
    while True:
        try:
            meter.check(p["id"])
        except ApiStop as e:
            append(log, {"at": now(), "end": "run_limit", "why": str(e), "usd": round(usd, 6), "calls": calls, "s": round(time.time() - t0, 1)})
            raise
        if usd >= limit:
            status, why = "budget", f"꾸러미 한도 {limit:g}달러에 닿음({usd:.4f}) — 한도로 멈춤"
            break
        n_img, n_bytes = ca.count_images(msgs)
        reason = ("호출 수" if calls >= MAX_CALLS else "그림 장수" if n_img > MAX_IMAGES else "요청 크기" if n_bytes > MAX_BYTES else None)
        if reason and final is None:
            final = reason
            last = msgs[-1]
            if last["role"] == "user" and isinstance(last["content"], list):
                last["content"].append({"type": "text", "text": FINAL_TEXT})
            else:
                msgs.append({"role": "user", "content": [{"type": "text", "text": FINAL_TEXT}]})
            append(log, {"at": now(), "final": reason, "images": n_img, "bytes": n_bytes})
        if final is not None:
            if final_left <= 0:
                status, why = "no_answer", f"마지막 단계({final}) 뒤에도 끝나지 않음"
                break
            final_left -= 1
        t1 = time.time()
        try:
            r, retried = call(client, kw, msgs)
        except Exception as e:  # noqa: BLE001
            status, why = "error", f"{type(e).__name__}: {e}"[:600]
            break
        calls += 1
        c_usd, tok = usd_of(r.usage)
        usd += c_usd
        uses = [b for b in r.content if b.type == "tool_use"]
        row = {"at": now(), "call": calls, **tok, "usd": round(c_usd, 6), "usd_pkg": round(usd, 6), "tools": [b.name for b in uses],
               "stop": r.stop_reason, "s": round(time.time() - t1, 2), "images_in_request": n_img, **({"retried": True} if retried else {})}
        txt = " ".join(b.text for b in r.content if b.type == "text")
        if txt:
            row["text"] = txt[:400]
        append(log, row)
        meter.add({"at": row["at"], "pkg": p["id"], "kind": kind, "call": calls, **tok, "usd": round(c_usd, 6)})
        msgs.append({"role": "assistant", "content": r.content})   # thinking 포함 그대로
        if r.stop_reason == "refusal":
            sd = r.stop_details
            status, why = "refusal", json.dumps({"category": getattr(sd, "category", None), "explanation": getattr(sd, "explanation", None)} if sd else None, ensure_ascii=False)
            break
        if r.stop_reason == "max_tokens":
            status, why = "max_tokens", f"max_tokens({MAX_TOKENS}) — 잘린 도구 입력은 돌리지 않음"
            break
        if not uses:
            bad = None if G.pending.exists() and form_error(kind, G.pending.read_text(encoding="utf-8")) is None else \
                ("답 파일이 없음" if not G.pending.exists() else form_error(kind, G.pending.read_text(encoding="utf-8")))
            if bad is None:
                status = "ok"
                break
            if not nudged:
                nudged = True
                msgs.append({"role": "user", "content": [{"type": "text", "text": f"답 파일을 써라: `{G.answer.as_posix()}` — 지시문의 답 꼴대로 write_file 로({bad})."}]})
                append(log, {"at": now(), "nudge": bad})
                continue
            if G.pending.exists():
                status, why = "ok", f"답 꼴 문제를 남긴 채 끝냄 — {bad}(그래프 work 마디가 한 번 다시 냄)"
            else:
                status, why = "no_answer", "답 파일 없이 끝냄(한 번 더 일렀는데도)"
            break
        results = []
        for b in uses:
            args = dict(b.input or {})
            t2 = time.time()
            ent = {"at": now(), "call": calls, "tool": b.name, "args": short(args)}
            try:
                if b.name not in TOOL_FN:
                    raise ValueError(f"모르는 도구: {b.name}")
                if b.name not in on:
                    raise PermissionError(f"이 꾸러미({kind})에서 꺼진 도구: {b.name}")
                if final is not None and b.name in IMG_TOOLS:
                    raise PermissionError("볼 수 있는 단계를 다 썼다 — 이제 답 파일만 쓸 수 있다")
                out = TOOL_FN[b.name](G, args)
                if isinstance(out, list):
                    content = [{"type": "text", "text": " | ".join(d for d, _ in out)}] + [ca.img_block(x) for _, x in out]
                    ent["images"] = len(out)
                    ent["result"] = short(" | ".join(d for d, _ in out), 200)
                else:
                    content = out
                    ent["result"] = short(out, 200)
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": content})
                ent["ok"] = True
            except Exception as e:  # noqa: BLE001
                msg = f"{type(e).__name__}: {e}"[:600]
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": msg, "is_error": True})
                ent.update(ok=False, error=msg)
            ent["s"] = round(time.time() - t2, 2)
            append(log, ent)
        msgs.append({"role": "user", "content": results})
    if status == "ok":
        os.replace(G.pending, G.answer)
    res = {"id": p["id"], "kind": kind, "status": status, "why": why, "usd": round(usd, 6), "calls": calls, "s": round(time.time() - t0, 1),
           "answer": G.answer.as_posix() if status == "ok" else None}
    append(log, {"at": now(), "end": status, "why": why, "usd": round(usd, 6), "calls": calls, "s": res["s"]})
    return res


# ------------------------------------------------------------------ 앞 실행의 API 답 다시 쓰기(--reuse-api-from)
def norm_task(text: str, run: Path) -> str:
    run = Path(run).resolve()
    for s in (run.as_posix(), str(run), run.relative_to(ROOT).as_posix() if under(run, ROOT) else None):
        if s:
            text = text.replace(s, "<RUN>")
    return re.sub(rf"(?<![\w-]){re.escape(run.name)}(?![\w-])", "<RUN>", text)


def try_reuse(run: Path, p: dict, src_run: Path):
    """앞 실행에서 API 손이 끝까지 채운(api_log.jsonl 의 마지막 end 가 ok) 같은 자리 꾸러미이고, TASK.md 가 실행 폴더 경로만 빼고 바이트 같으면 답을 베낌."""
    run, src_run = Path(run).resolve(), Path(src_run).resolve()
    try:
        rel_d = Path(p["dir"]).resolve().relative_to(run)
        rel_a = Path(p["answer"]).resolve().relative_to(run)
        rel_t = Path(p["task"]).resolve().relative_to(run)
    except ValueError:
        return None
    sd = src_run / rel_d
    ends = [x for x in jlines(sd / "api_log.jsonl") if "end" in x]
    if not ends or ends[-1]["end"] != "ok" or not (src_run / rel_a).exists() or not (src_run / rel_t).exists():
        return None
    a = norm_task((src_run / rel_t).read_bytes().decode("utf-8"), src_run)
    b = norm_task(Path(p["task"]).read_bytes().decode("utf-8"), run)
    if a != b:
        append(Path(p["dir"]) / "api_log.jsonl", {"at": now(), "reuse_skip": (src_run / rel_d).as_posix(), "why": "TASK.md 가 다름(실행 폴더 경로를 뺀 뒤)"})
        return None
    txt = (src_run / rel_a).read_bytes().decode("utf-8")
    for s_old, s_new in ((src_run.as_posix(), run.as_posix()), (str(src_run), str(run))):
        txt = txt.replace(s_old, s_new)
    Path(p["answer"]).parent.mkdir(parents=True, exist_ok=True)
    Path(p["answer"]).write_bytes(txt.encode("utf-8"))
    append(Path(p["dir"]) / "api_log.jsonl", {"at": now(), "start": p["id"], "kind": kind_of(p), "reused_from": (src_run / rel_d).as_posix()})
    append(Path(p["dir"]) / "api_log.jsonl", {"at": now(), "end": "ok", "why": "앞 실행 API 답을 베낌(돈 0)", "usd": 0, "calls": 0, "s": 0, "reused": True})
    return {"id": p["id"], "kind": kind_of(p), "status": "ok", "usd": 0.0, "calls": 0, "reused_from": (src_run / rel_d).as_posix(), "answer": p["answer"]}


# ------------------------------------------------------------------ 가짜 클라이언트(SDK 응답 꼴 흉내 — API 0)
class _Stream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.msg


def _jsonable(o):
    if hasattr(o, "model_dump"):
        return o.model_dump()
    return str(o)


def est_tokens(kw: dict, msgs: list) -> int:
    """가짜 usage 용 어림: 글 3.5자 = 1토큰 · 그림 한 장 1600토큰(실제 토크나이저 아님)."""
    n_img, _ = ca.count_images(msgs)
    s = json.dumps({k: v for k, v in kw.items()}, ensure_ascii=False, default=_jsonable)
    s += json.dumps(msgs, ensure_ascii=False, default=_jsonable)
    s = re.sub(r'"data": "[A-Za-z0-9+/=]+"', '"data": ""', s)
    return int(len(s) / 3.5) + 1600 * n_img


class FakeClient:
    """messages.stream(messages=…, **kw) 가 정해 둔 걸음(script)을 차례로 내는 anthropic.types.Message 를 돌려줌.
    걸음: {"text": 글, "tools": [(이름, 입력)…]} · {"refusal": True} · {"raise": "529" | "conn" | "400"}. usage 는 요청 크기 어림(캐시 흉내: 앞 요청까지는 읽기, 늘어난 만큼 쓰기)."""

    def __init__(self, script: list, out_tokens: int = 300, model: str = MODEL):
        self.script = list(script)
        self.out_tokens = out_tokens
        self.model = model
        self.requests = []
        self.prev = 0
        self.n = 0

    @property
    def messages(self):
        return self

    def stream(self, messages, **kw):
        import anthropic
        from anthropic.types import Message, RefusalStopDetails, TextBlock, ToolUseBlock, Usage
        if FAKE["on"] is False:
            raise RuntimeError("가짜 클라이언트는 arm_fake() 뒤에만")
        self.requests.append({"kw_keys": sorted(kw), "n_messages": len(messages), "images": ca.count_images(messages)[0]})
        if not self.script:
            raise RuntimeError("가짜 걸음이 다 떨어짐")
        st = self.script.pop(0)
        if st.get("raise"):
            req = __import__("httpx").Request("POST", "https://fake.invalid/v1/messages")
            if st["raise"] == "conn":
                raise anthropic.APIConnectionError(request=req)
            code = int(st["raise"])
            raise anthropic.APIStatusError(f"가짜 {code}", response=__import__("httpx").Response(code, request=req), body=None)
        tot = est_tokens(kw, messages)
        cr = min(self.prev, tot)
        u = Usage(input_tokens=20, output_tokens=self.out_tokens, cache_read_input_tokens=cr, cache_creation_input_tokens=max(0, tot - cr - 20))
        self.prev = tot
        blocks = []
        if st.get("text"):
            blocks.append(TextBlock(type="text", text=st["text"]))
        for name, inp in st.get("tools") or []:
            self.n += 1
            blocks.append(ToolUseBlock(type="tool_use", id=f"toolu_fake_{self.n:04d}", name=name, input=inp))
        stop = "refusal" if st.get("refusal") else ("tool_use" if st.get("tools") else "end_turn")
        m = Message(id=f"msg_fake_{len(self.requests):04d}", type="message", role="assistant", model=self.model, content=blocks, stop_reason=stop,
                    stop_details=RefusalStopDetails(type="refusal", category="cyber", explanation="가짜 거절") if st.get("refusal") else None, usage=u)
        return _Stream(m)


def _first_images(G: Guard, n: int = 4) -> list:
    imgs = []
    for f in G.list_files_in_pkg():
        for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
            m = PATH_RE.search(ln)
            if m and Path(m.group(0)).suffix.lower() in IMG_EXT:
                imgs.append(m.group(0))
                if len(imgs) >= n:
                    return imgs
    for d in G.task_dirs:
        try:
            names = sorted(x for x in os.listdir(d) if Path(x).suffix.lower() in IMG_EXT)
        except OSError:
            continue
        imgs += [(d / x).as_posix() for x in names[:n]]
        if imgs:
            return imgs[:n]
    for root, _, files in os.walk(G.dir):
        for x in sorted(files):
            if Path(x).suffix.lower() in IMG_EXT and not under(root, G.work):
                imgs.append((Path(root) / x).as_posix())
                if len(imgs) >= n:
                    return imgs
    return imgs


def fake_script(p: dict, kind: str, answer_text: str, mode: str = "normal") -> list:
    """가짜 걸음: 재료 보기 → (그림) → (ht_prep: 초안 · prep_try) → 답 쓰기 → 끝 글. mode guard 는 앞에 길 지키기 시험 걸음을 넣음."""
    G = Guard(p, kind)
    d, ans = G.dir.as_posix(), G.answer.as_posix()
    S = []
    if mode == "guard":
        bad = [("read_text", {"path": (ROOT / "HANDOFF.md").as_posix()}),                         # 폴더 밖 읽기
               ("read_text", {"path": "work/../../../../../../HANDOFF.md"}),                      # 상대 경로로 빠져나가기
               ("list_files", {"dir": (ROOT / "docs").as_posix()}),                               # 폴더 밖 목록
               ("write_file", {"path": (G.dir / "x_outside_work.json").as_posix(), "text": "{}"}),  # work/ 밖 쓰기(꾸러미 안)
               ("write_file", {"path": (ROOT / "p_should_not_exist.txt").as_posix(), "text": "x"}),  # 폴더 밖 쓰기
               ("read_text", {"path": "no_such_file.txt"}),                                       # 없는 파일
               ("view_image", {"path": "raw/99999.jpg"}),                                         # 없는 그림
               ("prep_try" if kind != "ht_prep" else "frobnicate", {"draft": "work/x.json"}),      # 꺼진 도구 · 모르는 도구
               ("read_text", {"path": (G.dir / "api_log.jsonl").as_posix()})]                     # 손 기록 숨김
        if kind == "manager":
            bad.append(("view_image", {"path": (G.dir / "summary.md").as_posix()}))               # 관리자: 그림 도구 꺼짐
        rr = [t for t in G.task_dirs if (t / "answer.json").exists()]
        if kind != "manager" and rr:
            bad.append(("read_text", {"path": (rr[0] / "answer.json").as_posix()}))              # 다른 꾸러미 답
        S.append({"text": "(가짜) 길 지키기 시험 걸음", "tools": bad})
    S.append({"text": "(가짜) 재료를 본다.", "tools": [("list_files", {"dir": d}), ("read_text", {"path": "TASK.md", "limit": 30})]})
    if kind == "manager":
        packs = [x for x in G.task_dirs if (x / "game.md").exists()]
        S.append({"tools": [("read_text", {"path": "summary.md", "limit": 60})] + ([("read_text", {"path": (packs[0] / "game.md").as_posix(), "limit": 40})] if packs else [])})
    else:
        imgs = _first_images(G)
        if imgs:
            im = Image.open(Path(imgs[0]))
            t = [("view_image", {"path": imgs[0], "crop": [0, 0, im.width // 2, im.height // 2], "scale": 2})]
            if len(imgs) >= 2:
                t.append(("view_strip", {"paths": imgs[:4], "cols": 2, "scale": 0.5}))
            S.append({"text": "(가짜) 그림을 본다.", "tools": t})
    if kind == "ht_prep":
        dr = (G.work / "draft_1.json").as_posix()
        S.append({"tools": [("write_file", {"path": dr, "text": answer_text})]})
        S.append({"text": "(가짜) try 를 돌린다.", "tools": [("prep_try", {"draft": dr})]})
    S.append({"tools": [("write_file", {"path": ans, "text": answer_text})]})
    S.append({"text": "(가짜 손) 답을 썼다."})
    return S


def parse_fake(spec: str) -> dict:
    """--api-fake 글: "replay" 또는 "replay:out=50000"(호출마다 출력 토큰)."""
    o = {"mode": "replay", "out": 300}
    head, _, rest = (spec or "replay").partition(":")
    o["mode"] = head or "replay"
    for kv in [x for x in rest.split(",") if x]:
        k, _, v = kv.partition("=")
        if k == "out":
            o["out"] = int(v)
    return o


def fill_graph_pkg(run, p: dict, opts: dict, answer_text_fn) -> dict:
    """그래프 work · manager 마디가 부름: --reuse-api-from 이면 먼저 베끼기, 아니면 (가짜 | 진짜) 클라이언트로 run_package.
    ok 가 아니면 ApiFail(실행 한도는 ApiStop). answer_text_fn() = 가짜 손이 쓸 답 글(재생 답)."""
    run = Path(run).resolve()
    kind = kind_of(p)
    if opts.get("reuse_api_from"):
        src = Path(opts["reuse_api_from"])
        src = src if src.is_absolute() else ROOT / src
        r = try_reuse(run, p, src)
        if r:
            return r
    meter = meter_of(run / "graph")
    if opts.get("api_fake"):
        if not FAKE["on"]:
            raise RuntimeError("가짜 손인데 arm_fake 가 안 됨")
        fo = parse_fake(opts["api_fake"])
        txt = answer_text_fn()
        if txt is None:
            raise ApiFail(f"{p['id']}: 가짜 손이 쓸 재생 답이 없음")
        client = FakeClient(fake_script(p, kind, txt), out_tokens=fo["out"])
    else:
        client = real_client()
    res = run_package(p, client, meter, kind)
    if res["status"] != "ok":
        raise ApiFail(f"{p['id']}({kind}) {res['status']}: {res['why']} — 기록 {Path(p['dir']).as_posix()}/api_log.jsonl")
    return res


# ------------------------------------------------------------------ CLI(진짜 호출 길 없음)
ANS_NAME = {"hand": "answer.json", "call": "answer.json", "reread": "answer.json", "ht_prep": "answer.json", "app_draw_reveal": "reveal_read.json",
            "result_read": "result_read.json", "boundary_read": "answer.json", "manager": "decision.json"}
STAGE_OF = {"hand": "S6", "call": "S6", "reread": "sup_reread", "ht_prep": "S6a", "app_draw_reveal": "S4", "result_read": "S4", "boundary_read": "S1", "manager": "manager"}


def pkg_of(spec: str) -> dict:
    kind, _, d = spec.partition("=")
    if kind not in KINDS:
        raise SystemExit(f"--pkg 종류 {kind!r} — {KINDS}")
    d = Path(d).resolve()
    return {"id": f"{kind}_{d.name}", "stage": STAGE_OF[kind], "kind": kind if kind in ("app_draw_reveal", "manager", "hand", "call", "ht_prep") else None,
            "dir": d.as_posix(), "task": (d / "TASK.md").as_posix(), "answer": (d / ANS_NAME[kind]).as_posix()}


def cmd_dry(a):
    """첫 요청 모양(API 0): 종류마다 <out>/<종류>_request.json(본문 그대로) · <종류>_check.json(검사)."""
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for spec in a.pkg:
        p = pkg_of(spec)
        kind = kind_of(p)
        kw, msgs = build_request(p, kind)
        body = {**kw, "messages": msgs}
        (out / f"{kind}_request.json").write_bytes(json.dumps(body, ensure_ascii=False, indent=1).encode("utf-8"))
        task_b = Path(p["task"]).read_bytes()
        G = Guard(p, kind)
        chk = {"kind": kind, "pkg": p["dir"], "model": kw["model"], "effort": kw["output_config"]["effort"], "max_tokens": kw["max_tokens"],
               "thinking": kw.get("thinking", "안 줌(= adaptive)"), "tool_choice": kw.get("tool_choice", "안 줌(= auto)"), "fallbacks": kw.get("fallbacks", "안 줌"),
               "system_blocks": len(kw["system"]), "system_cache_control_on_last": kw["system"][-1].get("cache_control"),
               "top_level_cache_control": kw.get("cache_control"), "tools": [t["name"] for t in kw["tools"]],
               "first_message_blocks": [b["type"] for b in msgs[0]["content"]], "images_in_first_request": ca.count_images(msgs)[0],
               "first_text_equals_task_bytes": msgs[0]["content"][0]["text"].encode("utf-8") == task_b, "task_bytes": len(task_b),
               "system_chars": len(SYSTEM), "request_bytes": len(json.dumps(body, ensure_ascii=False).encode("utf-8")),
               "readable_task_dirs": [x.as_posix() for x in G.task_dirs], "readable_task_files": sorted(G.task_files),
               "list_files": [x.as_posix() for x in G.list_files_in_pkg()], "listed_paths": len(G.lists()["files"]), "pkg_usd_limit": PKG_USD[kind]}
        (out / f"{kind}_check.json").write_bytes(json.dumps(chk, ensure_ascii=False, indent=1).encode("utf-8"))
        rows.append({k: chk[k] for k in ("kind", "tools", "first_text_equals_task_bytes", "images_in_first_request", "system_cache_control_on_last", "top_level_cache_control")})
    (out / "SYSTEM.txt").write_bytes(SYSTEM.encode("utf-8"))
    print(json.dumps(rows, ensure_ascii=False, indent=1))


def cmd_fake(a):
    """꾸러미 하나를 가짜 클라이언트로 끝까지(API 0)."""
    arm_fake()
    p = pkg_of(a.pkg)
    kind = kind_of(p)
    txt = Path(a.answer_from).read_bytes().decode("utf-8")
    gd = Path(a.usage_dir) if a.usage_dir else Path(p["dir"]) / "_fake_usage"
    if a.max_usd is not None:
        set_limit(gd, a.max_usd)
    global RETRY_WAIT
    RETRY_WAIT = a.retry_wait
    script = fake_script(p, kind, txt, a.script)
    if a.prepend:
        script = json.loads(Path(a.prepend).read_text(encoding="utf-8")) + script
    cl = FakeClient(script, out_tokens=a.out_tokens)
    try:
        res = run_package(p, cl, meter_of(gd), kind)
    except ApiStop as e:
        res = {"status": "run_limit(ApiStop)", "why": str(e)}
    res["fake_requests"] = cl.requests
    res["usage"] = usage_summary(gd)
    print(json.dumps(res, ensure_ascii=False, indent=1))


def cmd_imgtest(a):
    """그림 도구 점검(API 0): 2반장 원본 프레임(1496²) · 차례 그림으로 view_image · view_strip 을 돌려 보낼 그림을 파일로 남김."""
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    src = ROOT / "experiments/paifu_frames/results/auto_h2_g3c"
    ps = [pkg_of(f"ht_prep={(src / 's6a/w11_130921').as_posix()}"), pkg_of(f"hand={(src / 'read/w11_d03').as_posix()}"),
          pkg_of(f"app_draw_reveal={(src / 's4/w13_132644/a').as_posix()}")]
    G6, Gh, Ga = Guard(ps[0], "ht_prep"), Guard(ps[1], "hand"), Guard(ps[2], "app_draw_reveal")
    fr = [ln.split("\t")[1] for ln in (src / "s6a/w11_130921/frames_ready.txt").read_text(encoding="utf-8").splitlines()[1200:1240:5]]
    hf = [ln.split(" ")[2] for ln in (src / "read/w11_d03/frames.txt").read_text(encoding="utf-8").splitlines()[20:44:3]]
    tests = [("1_raw_1496", G6, "view_image", {"path": fr[0]}),
             ("2_scale3_full", G6, "view_image", {"path": fr[0], "scale": 3}),
             ("3_band_rot270_x4", G6, "view_image", {"path": fr[0], "crop": [1274, 428, 1368, 1103], "rotate": 270, "scale": 4}),
             ("4_grid_boxes", G6, "view_image", {"path": fr[0], "grid": 100, "boxes": [{"box": [1274, 428, 1368, 1103], "color": "yellow", "label": "band"},
                                                                                       {"box": [891, 633, 1100, 928], "color": "cyan", "label": "river"}]}),
             ("5_strip_turn_frames", Gh, "view_strip", {"paths": hf, "crop": [0, 150, 904, 401], "scale": 1, "cols": 2}),
             ("6_strip_head_kst_rot", G6, "view_strip", {"paths": fr, "crop": [1250, 400, 1400, 1130], "rotate": 270, "scale": 2, "cols": 1}),
             ("7_list_head_dir", Ga, "list_files", {"dir": "C:/Users/jjh7757/dev/mahjong_calc/experiments/visit_20261114/head_rec/rec_20261114_125617",
                                                     "name_from": "f_1794630890000", "name_to": "f_1794630892000"})]
    rows = []
    for name, G, tool, args in tests:
        o = TOOL_FN[tool](G, args)
        if isinstance(o, str):
            (out / f"{name}.txt").write_bytes(o.encode("utf-8"))
            rows.append({"test": name, "tool": tool, "text_head": o[:300]})
            continue
        for k, (desc, b) in enumerate(o):
            sent = base64.standard_b64decode(ca.img_block(b)["source"]["data"])
            (out / f"{name}.jpg").write_bytes(sent)
            w, h = Image.open(io.BytesIO(sent)).size
            rows.append({"test": name, "tool": tool, "sent": f"{w}×{h}", "long_edge_ok": max(w, h) <= LONG_EDGE, "kb": len(sent) // 1024, "desc": desc[:400]})
    (out / "imgtest.json").write_bytes(json.dumps(rows, ensure_ascii=False, indent=1).encode("utf-8"))
    print(json.dumps(rows, ensure_ascii=False, indent=1))


def main():
    ap = argparse.ArgumentParser(description="그래프 api 손(설계서 8-21) — 이 CLI 는 API 를 부르지 않는다(dry · fake · imgtest)")
    sp = ap.add_subparsers(dest="cmd", required=True)
    q = sp.add_parser("dry")
    q.add_argument("--pkg", action="append", required=True, help="<종류>=<꾸러미 폴더>")
    q.add_argument("--out", required=True)
    q = sp.add_parser("fake")
    q.add_argument("--pkg", required=True)
    q.add_argument("--answer-from", required=True, help="가짜 손이 쓸 답 글 파일")
    q.add_argument("--script", default="normal", choices=["normal", "guard"])
    q.add_argument("--prepend", help="가짜 걸음 JSON 목록 파일(앞에 붙임 — 예 [{\"raise\": \"529\"}])")
    q.add_argument("--out-tokens", type=int, default=300)
    q.add_argument("--usage-dir", help="api_usage.jsonl · api_limit.json 자리(기본 <꾸러미>/_fake_usage)")
    q.add_argument("--max-usd", type=float)
    q.add_argument("--retry-wait", type=float, default=RETRY_WAIT)
    q = sp.add_parser("imgtest")
    q.add_argument("--out", required=True)
    a = ap.parse_args()
    {"dry": cmd_dry, "fake": cmd_fake, "imgtest": cmd_imgtest}[a.cmd](a)


if __name__ == "__main__":
    main()
