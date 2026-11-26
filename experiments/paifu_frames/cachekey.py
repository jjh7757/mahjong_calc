"""코드 계산 저장분의 입력 지문(설계서 8-25 의 2, 점검 M4 — 11-26 밤).

"파일이 있으면 그냥 씀" 저장분은 규칙 · 설정이 바뀌어도 옛 결과를 써서 틀린 값이 조용히 섞인다. 8-23 의 LLM 결과 대체와 같은 규칙 —
입력 지문이 같을 때만 다시 쓴다 — 을 코드 계산 저장분에도 쓴다. 부르는 곳 연결은 아직 안 함(8-25 의 2 "대상" 표).

  k, parts = cachekey.key_parts(inputs, code_files)      # 또는 cachekey.key(...) — 열쇠만
  if not cachekey.fresh(out, k):
      cachekey.log_rebuild(run_dir, out, cachekey.why(out, k, parts))
      ...계산 · 저장...
      cachekey.stamp(out, k, {"band": cfg["band"]}, parts)

열쇠 = sha256(정규 JSON{"v": 1, "parts": {이름: sha256}}).
  inputs 의 칸 하나마다 "in.<이름>" = 그 값의 정규 JSON sha256. 값 안의 pathlib.Path 는 **파일 바이트 sha256**(경로 글자는 안 넣음 —
  실행 폴더를 베껴도 같은 열쇠). 없는 파일은 "missing". 폴더는 안의 파일 (상대 경로, 바이트 sha) 목록. 경로 글자를 넣고 싶으면 str 로.
  code_files 하나마다 "code.<파일 이름>" = 바이트 sha256(같은 이름이 둘이면 "code.<이름>#2").
정규 JSON: 열쇠 정렬 · dict 열쇠는 글로 · tuple → list · set → 정렬 목록 · float 은 repr · numpy 값은 .tolist() — PYTHONHASHSEED 와 무관.
옆 파일: <path>.key.json = {"key", "parts", "inputs", "made"} (path 가 폴더면 폴더 옆에 같은 이름 + .key.json).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

VERSION = 1


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def file_sha(p: Path) -> str:
    """파일 바이트 sha256 · 폴더면 안의 파일 (상대 경로, sha) 목록의 sha · 없으면 "missing"."""
    p = Path(p)
    if p.is_dir():
        rows = sorted((q.relative_to(p).as_posix(), file_sha(q)) for q in p.rglob("*") if q.is_file())
        return "dir:" + _sha_bytes(json.dumps(rows, separators=(",", ":")).encode("utf-8"))
    if not p.exists():
        return "missing"
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def _norm(x):
    """정규 꼴(JSON 으로 옮길 수 있고 프로세스 · 해시 씨앗과 무관)."""
    if isinstance(x, Path):
        return {"__file__": file_sha(x)}
    if isinstance(x, dict):
        return {str(k): _norm(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_norm(v) for v in x]
    if isinstance(x, (set, frozenset)):
        items = [_norm(v) for v in x]
        return sorted(items, key=lambda v: json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
    if isinstance(x, bytes):
        return {"__bytes__": _sha_bytes(x)}
    if hasattr(x, "tolist") and type(x).__module__ == "numpy":
        return _norm(x.tolist())
    if x is None or isinstance(x, (bool, int, float, str)):
        return x
    raise TypeError(f"cachekey: 열쇠에 넣을 수 없는 값 {type(x).__name__}")


def _canon(x) -> str:
    return json.dumps(_norm(x), sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=True)


def parts_of(inputs: dict, code_files: list) -> dict:
    """{"in.<이름>": sha, "code.<파일 이름>": sha} — 어느 칸이 바뀌었는지 why 가 말할 수 있게."""
    parts = {f"in.{k}": _sha_bytes(_canon(v).encode("utf-8")) for k, v in (inputs or {}).items()}
    seen: dict = {}
    for f in code_files or []:
        f = Path(f)
        name = f.name
        seen[name] = seen.get(name, 0) + 1
        parts[f"code.{name}" + (f"#{seen[name]}" if seen[name] > 1 else "")] = file_sha(f)
    return parts


def key_of_parts(parts: dict) -> str:
    return _sha_bytes(json.dumps({"v": VERSION, "parts": parts}, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def key_parts(inputs: dict, code_files: list) -> tuple[str, dict]:
    parts = parts_of(inputs, code_files)
    return key_of_parts(parts), parts


def key(inputs: dict, code_files: list) -> str:
    """입력 값 · 입력 파일 바이트(값 안의 Path) · 코드 파일 바이트의 sha256(64자)."""
    return key_parts(inputs, code_files)[0]


def key_file(path) -> Path:
    path = Path(path)
    return path.with_name(path.name + ".key.json")


def _read_key(path) -> dict | None:
    kf = key_file(path)
    try:
        return json.loads(kf.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def fresh(path, key: str) -> bool:
    """저장분이 있고 옆 열쇠 파일의 열쇠가 같으면 True(다시 써도 됨)."""
    path = Path(path)
    if not path.exists():
        return False
    k = _read_key(path)
    return k is not None and k.get("key") == key


def stamp(path, key: str, inputs_summary=None, parts: dict | None = None):
    """옆 열쇠 파일을 쓴다(사람이 읽을 입력 요약 포함). 저장분을 다 쓴 뒤에 부른다 — 쓰다 죽으면 열쇠가 없어 다음에 다시 셈."""
    kf = key_file(path)
    kf.parent.mkdir(parents=True, exist_ok=True)
    o = {"key": key, "made": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "parts": parts, "inputs": _summ(inputs_summary)}
    tmp = kf.with_name(kf.name + f".tmp{os.getpid()}")
    tmp.write_bytes(json.dumps(o, ensure_ascii=False, indent=1).encode("utf-8"))
    os.replace(tmp, kf)


def _summ(x):
    try:
        json.dumps(x)
        return x
    except TypeError:
        return json.loads(json.dumps(x, default=lambda v: v.as_posix() if isinstance(v, Path) else repr(v)))


def why(path, key: str, parts: dict | None = None) -> str:
    """다시 세는 까닭 한 줄(fresh 가 False 일 때)."""
    path = Path(path)
    if not path.exists():
        return "저장분 없음"
    k = _read_key(path)
    if k is None:
        return "열쇠 파일 없음(옛 저장분 — 지문 없이 만든 것)"
    if k.get("key") == key:
        return "같음"
    old = k.get("parts") or {}
    if parts is None:
        return "열쇠 다름(칸별 값 없음)"
    ch = sorted(n for n in set(old) | set(parts) if old.get(n) != parts.get(n))
    return "열쇠 다름: " + (", ".join(ch) if ch else "판(VERSION)")


def log_rebuild(run_dir, path, reason: str, log_name: str = "cache.log"):
    """실행 <run_dir>/logs/cache.log 에 한 줄: 시각 · 저장분(실행 폴더 기준 상대 경로) · 까닭."""
    run_dir, path = Path(run_dir), Path(path)
    try:
        rel = path.resolve().relative_to(run_dir.resolve()).as_posix()
    except ValueError:
        rel = path.as_posix()
    f = run_dir / "logs" / log_name
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')}\t{rel}\t{reason}\n")


def check(path, inputs: dict, code_files: list, run_dir=None) -> tuple[bool, str, dict]:
    """한 번에: (다시 써도 되나, 열쇠, 칸별 값). 아니면 run_dir 가 있을 때 까닭을 cache.log 에. 계산 뒤 stamp(path, 열쇠, …, 칸별 값)."""
    k, parts = key_parts(inputs, code_files)
    ok = fresh(path, k)
    if not ok and run_dir is not None:
        log_rebuild(run_dir, path, why(path, k, parts))
    return ok, k, parts
