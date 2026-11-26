"""검출기 원본 출력(LocalReader._seat_raw)을 녹화 프레임 단위로 녹화 옆에 남겨 다시 쓰기(설계서 8-25 의 1, 점검 H1 — 11-26 밤).

비싼 계산은 프레임 전체를 보는 _seat_raw 하나다(손패 줄 구역과 무관). 같은 프레임 · 같은 검출기면 바이트로 같은 답이므로(표 12-143)
한 번 센 것을 녹화 옆에 두고, 거르기(boxes_view · back_row · bandcand)는 이것만 읽게 한다. 부르는 곳 연결은 아직 안 함(8-25 "바꿀 부르는 곳").

  python -X utf8 experiments/paifu_frames/handtrack/rawdet.py prefill --from <ms> --to <ms> [--step N] [--threads N]
  python -X utf8 experiments/paifu_frames/handtrack/rawdet.py stat [--all]
  python -X utf8 experiments/paifu_frames/handtrack/rawdet.py merge          # 남은 part 를 본 파일로 합치기만

자리: <녹화 뿌리의 부모>/<녹화 뿌리 이름>_det/<지문 12자>/<녹화 폴더>/b<묶음 3자리>.json.gz
  (11-14 매장이면 experiments/visit_20261114/head_rec_det/…). 묶음 = 녹화 안 프레임 순번 // 500.
  값 = {"<ms>": {"jpg_sha": <프레임 jpg 바이트 sha256>, "out": [res, backs, pairs, scores]}} — 상자 · 회전 상자는 목록으로,
  float 은 repr 그대로(json), scores 는 [[축 상자], 점수] 쌍 목록(넣은 순서 그대로). 읽을 때 원래 형(tuple · dict)으로 되돌린다.
여러 프로세스: 새로 센 것은 프로세스마다 b012.<pid>_<순번>.part.json.gz(쓴 뒤로는 안 바뀜)로 따로 쓰고, 읽기는 본 파일 + part 를 합친다.
  합치기(merge)는 b012.lock 을 잡은 프로세스 하나만 — 읽은 part 만 지우므로 그 사이 남이 쓴 part 는 남는다. 잠금을 못 잡으면 part 를 남겨 둔다.
지문 = 자리 판독 모델 파일 + mahjong-recognizer app/local_read.py · app/obb.py 바이트 + onnxruntime 판(문턱 · 해석 코드 · 런타임이 바뀌면 다른 폴더).
"""
from __future__ import annotations

import argparse
import atexit
import gzip
import hashlib
import io
import json
import os
import sys
import time
from bisect import bisect_left
from collections import OrderedDict
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402

REC = Path(r"C:\Users\jjh7757\dev\mahjong-recognizer")
if str(REC) not in sys.path:
    sys.path.insert(0, str(REC))

BUNDLE = 500            # 묶음 하나의 프레임 수(녹화 안 순번)
FLUSH_N = 200           # 새로 센 것이 이만큼 모이면 part 로 씀
FLUSH_S = 60.0          # 또는 마지막으로 쓴 뒤 이만큼 지나면
LRU_BUNDLES = 4         # 메모리에 들고 있을 묶음 수(묶음 하나 ≈ 프레임 500 × 상자 100)
LOCK_WAIT_S = 10.0      # 합치기 잠금을 기다리는 최대 시간
LOCK_STALE_S = 600.0    # 이보다 오래된 잠금 파일은 죽은 프로세스 것으로 보고 치움

_CFG = {"seat_model": None, "threads": 8}
_READER = {"r": None, "key": None}
_FP: dict = {}
_MEM: "OrderedDict[tuple, dict]" = OrderedDict()   # (지문, 녹화, 묶음) → {"e": {ms 글: 값}, "sig": 파일 서명}
_PENDING: dict = {}                                 # (지문, 녹화, 묶음) → {ms 글: 값} 아직 part 로 안 쓴 것
_SEQ = [0]
_LAST_FLUSH = [time.time()]
STATS = {"hit": 0, "computed": 0, "sha_mismatch": 0, "reload": 0, "parts_written": 0, "merged_parts": 0, "merge_skipped": 0}


# ------------------------------------------------------------------ 설정 · 지문
def configure(seat_model=None, threads: int | None = None):
    """검출기 모델 경로(시험 — 사본)와 스레드 수. 바꾸면 읽기 · 메모리 저장분을 비운다(쓰지 않은 것은 먼저 씀)."""
    flush()
    if seat_model is not None:
        _CFG["seat_model"] = Path(seat_model)
    if threads is not None:
        _CFG["threads"] = int(threads)
    _MEM.clear()


def _lr():
    from app import local_read as lr
    return lr


def seat_model_path() -> Path:
    return Path(_CFG["seat_model"] or _lr().SEAT_MODEL)


def _sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def fingerprint_parts() -> dict:
    """지문을 이루는 것 — {이름: sha256 | 판}. 모델 경로가 같으면 프로세스에 한 번만 잰다."""
    mp = seat_model_path()
    if str(mp) in _FP:
        return _FP[str(mp)]
    lr = _lr()
    from app import obb
    try:
        from importlib.metadata import version
        ort_v = version("onnxruntime")
    except Exception:  # noqa: BLE001
        ort_v = "?"
    parts = {"seat_model": _sha_file(mp), "local_read.py": _sha_file(Path(lr.__file__)), "obb.py": _sha_file(Path(obb.__file__)),
             "onnxruntime": ort_v}
    _FP[str(mp)] = parts
    return parts


def fingerprint() -> str:
    """검출기 지문(sha256 64자). 폴더 이름은 앞 12자."""
    s = json.dumps(fingerprint_parts(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def det_root() -> Path:
    """녹화 뿌리 옆 <이름>_det (11-14 매장이면 experiments/visit_20261114/head_rec_det)."""
    return hc.REC_ROOT.parent / f"{hc.REC_ROOT.name}_det"


def fp_dir() -> Path:
    return det_root() / fingerprint()[:12]


def _write_fp_note(d: Path):
    f = d / "fingerprint.json"
    if f.exists():
        return
    d.mkdir(parents=True, exist_ok=True)
    note = {"fingerprint": fingerprint(), "parts": fingerprint_parts(), "seat_model": seat_model_path().as_posix(),
            "_note": "handtrack/rawdet.py — LocalReader._seat_raw 원본 출력 저장분(설계서 8-25 의 1)"}
    _atomic_write(f, json.dumps(note, ensure_ascii=False, indent=1).encode("utf-8"))


# ------------------------------------------------------------------ 자리
def locate(ms: int) -> tuple[str, int]:
    """프레임 ms → (녹화 폴더 이름, 묶음 번호). 녹화에 없는 ms 면 KeyError."""
    rec = hc.rec_of(ms)
    f = hc.frames(rec)
    i = bisect_left(f, ms)
    if i >= len(f) or int(f[i]) != ms:
        raise KeyError(f"녹화 {rec} 에 프레임 {ms} 없음")
    return rec, i // BUNDLE


def bundle_dir(rec: str) -> Path:
    return fp_dir() / rec


def bundle_main(rec: str, b: int) -> Path:
    return bundle_dir(rec) / f"b{b:03d}.json.gz"


def _parts_of(rec: str, b: int) -> list[Path]:
    d = bundle_dir(rec)
    pre = f"b{b:03d}."
    try:
        names = [e.name for e in os.scandir(d) if e.name.startswith(pre) and e.name.endswith(".part.json.gz")]
    except FileNotFoundError:
        return []
    return [d / n for n in names]


def _sig(rec: str, b: int) -> tuple:
    out = []
    for p in [bundle_main(rec, b)] + _parts_of(rec, b):
        try:
            st = p.stat()
            out.append((p.name, st.st_mtime_ns, st.st_size))
        except FileNotFoundError:
            pass
    return tuple(sorted(out))


# ------------------------------------------------------------------ 파일 읽기 · 쓰기
def _gz_bytes(obj) -> bytes:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    bio = io.BytesIO()
    with gzip.GzipFile(fileobj=bio, mode="wb", compresslevel=6, mtime=0) as g:
        g.write(raw)
    return bio.getvalue()


def _gz_load(p: Path) -> dict:
    def rd():
        with open(p, "rb") as f:
            return f.read()
    data = _retry(rd, tries=20)
    return json.loads(gzip.decompress(data).decode("utf-8"))


def _retry(fn, tries: int = 60, wait: float = 0.1):
    """Windows: 남이 파일을 열고 있으면 이름 바꾸기 · 지우기가 PermissionError — 잠깐 기다려 다시."""
    for k in range(tries):
        try:
            return fn()
        except PermissionError:
            if k == tries - 1:
                raise
            time.sleep(wait)


def _atomic_write(p: Path, data: bytes):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".tmp{os.getpid()}")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    _retry(lambda: os.replace(tmp, p))


def _part_order(p: Path) -> tuple:
    try:
        return (p.stat().st_mtime_ns, p.name)
    except FileNotFoundError:
        return (0, p.name)


def _read_bundle(rec: str, b: int) -> tuple[dict, list[Path]]:
    """본 파일 + part(오래된 것부터, 뒤가 앞을 덮음) → ({ms 글: 값}, 읽은 part 목록). 읽는 사이 part 가 합쳐져 지워졌으면 다시 읽음."""
    for _ in range(5):
        parts = sorted(_parts_of(rec, b), key=_part_order)
        e: dict = {}
        main = bundle_main(rec, b)
        try:
            if main.exists():
                e.update(_gz_load(main))
            for p in parts:
                e.update(_gz_load(p))
            return e, parts
        except FileNotFoundError:
            continue
    raise RuntimeError(f"묶음 {rec}/b{b:03d} 를 읽는 동안 파일이 계속 바뀜")


def _bundle(rec: str, b: int, reload_if_changed: bool = False) -> dict:
    k = (fingerprint(), rec, b)
    m = _MEM.get(k)
    if m is not None and reload_if_changed and _sig(rec, b) != m["sig"]:
        STATS["reload"] += 1
        m = None
    if m is None:
        sig = _sig(rec, b)
        e, _ = _read_bundle(rec, b)
        e.update(_PENDING.get(k, {}))
        m = {"e": e, "sig": sig}
        _MEM[k] = m
        while len(_MEM) > LRU_BUNDLES:
            _MEM.popitem(last=False)
    _MEM.move_to_end(k)
    return m


def flush():
    """쓰지 않은 새 값을 묶음마다 part 파일 하나로(쓴 뒤 이름 바꿈 — 반쯤 쓴 파일은 안 보임)."""
    for k, ent in list(_PENDING.items()):
        if not ent:
            continue
        _fp, rec, b = k
        d = det_root() / _fp[:12] / rec
        _SEQ[0] += 1
        p = d / f"b{b:03d}.{os.getpid()}_{_SEQ[0]:05d}.part.json.gz"
        _atomic_write(p, _gz_bytes(ent))
        STATS["parts_written"] += 1
    _PENDING.clear()
    _LAST_FLUSH[0] = time.time()


def _maybe_flush():
    n = sum(len(v) for v in _PENDING.values())
    if n >= FLUSH_N or (n and time.time() - _LAST_FLUSH[0] >= FLUSH_S):
        flush()


class _Lock:
    def __init__(self, p: Path, wait: float):
        self.p, self.wait, self.ok = p, wait, False

    def __enter__(self):
        t0 = time.time()
        while True:
            try:
                fd = os.open(self.p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, f"{os.getpid()} {time.time():.0f}".encode())
                os.close(fd)
                self.ok = True
                return self
            except FileExistsError:
                try:
                    if time.time() - self.p.stat().st_mtime > LOCK_STALE_S:
                        os.remove(self.p)
                        continue
                except (FileNotFoundError, PermissionError):
                    pass
                if time.time() - t0 >= self.wait:
                    return self
                time.sleep(0.1)

    def __exit__(self, *a):
        if self.ok:
            try:
                _retry(lambda: os.remove(self.p))
            except (FileNotFoundError, PermissionError):
                pass


def merge_bundle(rec: str, b: int, wait: float = LOCK_WAIT_S, fp: str | None = None) -> bool:
    """묶음의 part 를 본 파일로 합친다. 잠금을 못 잡으면 False(part 는 그대로 — 읽기가 합쳐 읽음)."""
    d = det_root() / (fp or fingerprint())[:12] / rec
    if not d.exists():
        return True
    main = d / f"b{b:03d}.json.gz"
    with _Lock(d / f"b{b:03d}.lock", wait) as lk:
        if not lk.ok:
            STATS["merge_skipped"] += 1
            return False
        pre = f"b{b:03d}."
        parts = sorted((d / e.name for e in os.scandir(d) if e.name.startswith(pre) and e.name.endswith(".part.json.gz")), key=_part_order)
        if not parts:
            return True
        e = _gz_load(main) if main.exists() else {}
        for p in parts:
            e.update(_gz_load(p))
        _atomic_write(main, _gz_bytes(e))
        for p in parts:
            try:
                _retry(lambda p=p: os.remove(p), tries=20)
                STATS["merged_parts"] += 1
            except (FileNotFoundError, PermissionError):
                pass   # 남아도 본 파일과 같은 값 — 다음 합치기가 지움
    return True


def merge_all(wait: float = LOCK_WAIT_S, fp: str | None = None) -> dict:
    """지금 지문 폴더의 모든 녹화 · 묶음 part 를 합침 → {"merged": n, "skipped": n}."""
    root = det_root() / (fp or fingerprint())[:12]
    got = {"merged": 0, "skipped": 0}
    if not root.exists():
        return got
    for rd in sorted(x for x in root.iterdir() if x.is_dir()):
        bs = sorted({int(e.name[1:4]) for e in os.scandir(rd) if e.name.endswith(".part.json.gz")})
        for b in bs:
            got["merged" if merge_bundle(rd.name, b, wait, fp) else "skipped"] += 1
    return got


# ------------------------------------------------------------------ 값 옮기기
def _rect_enc(rc):
    return [[rc[0][0], rc[0][1]], [rc[1][0], rc[1][1]], rc[2]]


def _rect_dec(rc):
    return ((rc[0][0], rc[0][1]), (rc[1][0], rc[1][1]), rc[2])


def _br_enc(x):
    return [list(x[0]), _rect_enc(x[1])]


def _br_dec(x):
    return (tuple(x[0]), _rect_dec(x[1]))


def encode(out) -> list:
    """(res, backs, pairs, scores) → JSON 으로 옮길 목록."""
    res, backs, pairs, scores = out
    return [[_br_enc(x) for x in res], [_br_enc(x) for x in backs], [[_br_enc(bk), list(fb)] for bk, fb in pairs],
            [[list(k), v] for k, v in scores.items()]]


def decode(o) -> tuple[list, list, list, dict]:
    """encode 의 반대 — _seat_raw 와 같은 형: [(축 상자 tuple, 회전 상자 ((cx, cy), (w, h), 각도))], 안깡 짝 [(뒷면 (상자, 회전 상자), 앞면 상자)], {축 상자: 점수}."""
    res, backs, pairs, scores = o
    return ([_br_dec(x) for x in res], [_br_dec(x) for x in backs], [(_br_dec(bk), tuple(fb)) for bk, fb in pairs],
            {tuple(k): v for k, v in scores})


def type_sig(x):
    """값의 형 구조(tuple/list/dict · int/float …) — repr 이 같아도 형이 다른 것을 잡으려고."""
    if isinstance(x, (list, tuple)):
        return (type(x).__name__, [type_sig(v) for v in x])
    if isinstance(x, dict):
        return ("dict", [(type_sig(k), type_sig(v)) for k, v in x.items()])
    return type(x).__name__


def _check_roundtrip(out, enc):
    back = decode(json.loads(json.dumps(enc)))
    if repr(back) != repr(out) or type_sig(back) != type_sig(out):
        raise ValueError("rawdet: 저장 꼴로 옮기면 값 · 형이 달라짐 — 저장 안 함(검출기 출력 꼴이 바뀌었나?)")


# ------------------------------------------------------------------ 검출
def reader():
    r = _READER["r"]
    key = (str(seat_model_path()), _CFG["threads"])
    if r is None or _READER["key"] != key:
        lr = _lr()
        r = lr.LocalReader(threads=_CFG["threads"], seat_model=seat_model_path())
        r._sessions()
        if r._seat is None:
            raise RuntimeError(f"자리 판독 모델이 없음: {seat_model_path()}")
        _READER["r"], _READER["key"] = r, key
    return r


def _jpg(ms: int) -> tuple[bytes, str]:
    data = hc.path_of(ms).read_bytes()
    return data, hashlib.sha256(data).hexdigest()


def _compute(ms: int, data: bytes, sha: str, k: tuple) -> dict:
    rgb = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))   # hc.load 와 같은 해독(파일 대신 읽어 둔 바이트)
    out = reader()._seat_raw(rgb)
    enc = encode(out)
    _check_roundtrip(out, enc)
    v = {"jpg_sha": sha, "out": enc}
    _PENDING.setdefault(k, {})[str(ms)] = v
    STATS["computed"] += 1
    return v


def cached(ms: int, check_sha: bool = True):
    """저장분에 있으면 (res, backs, pairs, scores), 없거나 jpg 가 바뀌었으면 None — 세지 않음."""
    rec, b = locate(ms)
    m = _bundle(rec, b)
    v = m["e"].get(str(ms))
    if v is None:
        m = _bundle(rec, b, reload_if_changed=True)
        v = m["e"].get(str(ms))
    if v is None or (check_sha and v["jpg_sha"] != _jpg(ms)[1]):
        return None
    return decode(v["out"])


def seat_raw(ms: int) -> tuple[list, list, list, dict]:
    """L._seat_raw(hc.load(ms)) 와 같은 값 · 같은 형. 저장분에 있으면(jpg sha 같을 때) 읽고, 없으면 세고 저장(part)."""
    rec, b = locate(ms)
    k = (fingerprint(), rec, b)
    data, sha = _jpg(ms)
    m = _bundle(rec, b)
    v = m["e"].get(str(ms))
    if v is None:
        m = _bundle(rec, b, reload_if_changed=True)   # 다른 프로세스가 그 사이 채웠을 수 있음
        v = m["e"].get(str(ms))
    if v is not None and v["jpg_sha"] == sha:
        STATS["hit"] += 1
        return decode(v["out"])
    if v is not None:
        STATS["sha_mismatch"] += 1
    _write_fp_note(fp_dir())
    v = _compute(ms, data, sha, k)
    m["e"][str(ms)] = v
    _maybe_flush()
    return decode(v["out"])


def prefill(ms_list, threads: int = 8, log=print, merge: bool = True) -> dict:
    """없는 것(또는 jpg 가 바뀐 것)만 센다. 진행 줄 · 걸린 초를 찍고, 끝에 part 를 본 파일로 합침(잠금 실패면 남김)."""
    if threads != _CFG["threads"]:
        _CFG["threads"] = int(threads)
    t0 = time.time()
    ms_list = sorted({int(x) for x in ms_list})
    todo = []
    for ms in ms_list:
        rec, b = locate(ms)
        m = _bundle(rec, b, reload_if_changed=True)
        v = m["e"].get(str(ms))
        _data, sha = _jpg(ms)
        if v is None or v["jpg_sha"] != sha:
            todo.append(ms)
    t_scan = time.time() - t0
    log(f"rawdet prefill: {len(ms_list)}장 중 셀 것 {len(todo)}장(이미 있음 {len(ms_list) - len(todo)}) · 지문 {fingerprint()[:12]} · 훑기 {t_scan:.1f}s")
    sys.stdout.flush()
    t1 = time.time()
    for i, ms in enumerate(todo):
        seat_raw(ms)
        if i % 200 == 0 or i == len(todo) - 1:
            el = time.time() - t1
            log(f"  {i + 1}/{len(todo)} {hc.hms(ms)} {el:.0f}s 장당 {el / (i + 1) * 1000:.0f}ms")
            sys.stdout.flush()
    flush()
    got = merge_all() if merge else {"merged": 0, "skipped": 0}
    res = {"frames": len(ms_list), "computed": len(todo), "s_scan": round(t_scan, 1), "s_compute": round(time.time() - t1, 1),
           "s_total": round(time.time() - t0, 1), "merge": got}
    log(f"rawdet prefill 끝: 셈 {len(todo)}장 · {res['s_total']}s · 합치기 {got}")
    sys.stdout.flush()
    return res


@atexit.register
def _at_exit():
    try:
        if any(_PENDING.values()):
            flush()
            merge_all(wait=2.0)
    except Exception as e:  # noqa: BLE001
        print("rawdet: 끝날 때 쓰기 실패", e, file=sys.stderr)


# ------------------------------------------------------------------ 명령줄
def cmd_stat(a):
    root = det_root()
    cur = fingerprint()[:12]
    if not root.exists():
        print("저장분 없음:", root)
        return
    for fd in sorted(x for x in root.iterdir() if x.is_dir()):
        if not a.all and fd.name != cur:
            print(f"[{fd.name}] (지금 지문 아님 — --all 로 자세히)")
            continue
        print(f"[{fd.name}]{' 지금 지문' if fd.name == cur else ''}")
        for rd in sorted(x for x in fd.iterdir() if x.is_dir()):
            mains = sorted(rd.glob("b*.json.gz"))
            mains = [p for p in mains if not p.name.endswith(".part.json.gz")]
            parts = sorted(rd.glob("*.part.json.gz"))
            locks = sorted(rd.glob("*.lock"))
            frames, gz, raw = set(), 0, 0
            for p in mains + parts:
                gz += p.stat().st_size
                data = gzip.decompress(p.read_bytes())
                raw += len(data)
                frames |= set(json.loads(data))
            n = max(1, len(frames))
            print(f"  {rd.name}: 묶음 {len(mains)} · part {len(parts)} · 잠금 {len(locks)} · 프레임 {len(frames)} · "
                  f"압축 {gz / 1e6:.2f}MB(장당 {gz / n / 1024:.1f}KB) · 압축 전 {raw / 1e6:.2f}MB(장당 {raw / n / 1024:.1f}KB)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prefill")
    p.add_argument("--from", dest="t0", type=int, required=True)
    p.add_argument("--to", dest="t1", type=int, required=True)
    p.add_argument("--step", type=int, default=1)
    p.add_argument("--threads", type=int, default=8)
    s = sub.add_parser("stat")
    s.add_argument("--all", action="store_true")
    sub.add_parser("merge")
    a = ap.parse_args()
    if a.cmd == "prefill":
        prefill(hc.frame_range(a.t0, a.t1)[::max(1, a.step)], threads=a.threads)
    elif a.cmd == "stat":
        cmd_stat(a)
    else:
        print(merge_all())


if __name__ == "__main__":
    main()
