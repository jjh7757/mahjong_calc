"""화료 판독의 세 요청(localroles·localdora·locallast3)을 앱처럼 동시에 보낼 때와 하나씩 보낼 때 서버 시간 비교(2026-11-05, metrics 표 1-84).

운영 앱 흐름에서 localroles 가 서버 단독 1.69초인데 앱 흐름에선 5.4초(표 1-82) — 세 요청이 2 vCPU 에서 겹치는지 가른다.
입력은 앱 흐름 덤프(`read_grid_timing_test.dart` DUMP_DIR: 사진마다 last_<자리>.jpg)와 그 로그의 TIMING 줄(격자·화료자).
  python -I -X utf8 experiments/tile_classifier/server_bench/contention_bench.py URL TAG [--key] [--sleep 초] [--modes together,serial] [--n 장면수]
결과 experiments/speed/results/contention_<TAG>.json 과 요약 출력.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RES = ROOT / "experiments" / "speed" / "results"
PHOTOS = {"bcd": ROOT / "experiments/field_20261024/kakao_photos", "visit": ROOT / "experiments/visit_20261031/captures"}

ap = argparse.ArgumentParser()
ap.add_argument("url")
ap.add_argument("tag")
ap.add_argument("--key", action="store_true", help="운영: .recognizer_key 를 x-api-key 로")
ap.add_argument("--sleep", type=float, default=2.0, help="장면 사이 쉼(운영 요청 제한)")
ap.add_argument("--modes", default="together,serial")
ap.add_argument("--n", type=int, default=0, help="앞에서 이 수만(0 = 전부)")
ap.add_argument("--dump", default=str(RES / "dump_1105prodlike"))
ap.add_argument("--logs", default="1105prodlike")
a = ap.parse_args()
KEY = (ROOT / ".recognizer_key").read_text().strip() if a.key else ""


def multipart(files: list[tuple[str, str, bytes]]) -> tuple[bytes, str]:
    b = uuid.uuid4().hex
    out = b""
    for field, name, data in files:
        out += f"--{b}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{name}\"\r\nContent-Type: image/jpeg\r\n\r\n".encode() + data + b"\r\n"
    return out + f"--{b}--\r\n".encode(), b


def post(path: str, files, query: dict | None = None) -> float:
    body, b = multipart(files)
    qs = "&".join(f"{k}={v}" for k, v in (query or {}).items())
    req = urllib.request.Request(f"{a.url}{path}{'?' + qs if qs else ''}", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={b}", **({"x-api-key": KEY} if KEY else {})})
    for _ in range(10):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                r.read()
                return time.perf_counter() - t0
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            time.sleep(float(e.headers.get("Retry-After", "5")))
    raise RuntimeError("429 계속")


def scenes() -> list[dict]:
    out, seen = [], set()
    for part in ("bcd", "am", "pm"):
        for line in (RES / f"log_flow_zone_saved_{a.logs}_{part}.txt").read_text(encoding="utf-8").splitlines():
            if not line.startswith("TIMING "):
                continue
            t = json.loads(line[7:])
            if t["photo"] in seen or t.get("error"):
                continue
            seen.add(t["photo"])
            d = Path(a.dump) / t["photo"].replace("/", "_")
            lasts = sorted(d.glob("last_*.jpg"))
            g = t["grid"]
            q = {"side": t["winner"], **{k: g[k] for k in ("x1", "x2", "y1", "y2")}}
            if g.get("sticks"):
                s = g["sticks"]
                q["sticks"] = ",".join(str(round(v)) for v in (s if isinstance(s, list) else [s[k] for k in ("ymin", "xmin", "ymax", "xmax")]))
            photo = (PHOTOS["bcd" if part == "bcd" else "visit"] / f"{t['photo']}.jpg").read_bytes()
            out.append({"photo": t["photo"], "orig": photo, "lasts": [(p.stem, p.read_bytes()) for p in lasts], "q": q})
    return out[: a.n] if a.n else out


def calls(s: dict) -> dict:
    return {
        "roles": lambda: post("/v2/localroles", [("image", "p.jpg", s["orig"])], s["q"]),
        "dora": lambda: post("/v2/localdora", [("image", "local_dora.jpg", s["orig"])]),
        "last3": lambda: post("/v2/locallast3", [("images", f"{n}.jpg", b) for n, b in s["lasts"]]),
    }


def run(s: dict, mode: str) -> dict:
    c = calls(s)
    t0 = time.perf_counter()
    if mode == "together":
        with ThreadPoolExecutor(3) as ex:
            fut = {k: ex.submit(f) for k, f in c.items()}
            each = {k: f.result() for k, f in fut.items()}
    else:
        each = {k: f() for k, f in c.items()}
    return {"wall": time.perf_counter() - t0, **each}


ss = scenes()
modes = a.modes.split(",")
rows = []
for s in ss:
    for i, mode in enumerate(modes if len(rows) % 2 == 0 else modes[::-1]):  # 장면마다 순서를 바꿔 시간 흐름 치우침 줄이기
        r = run(s, mode)
        rows.append({"photo": s["photo"], "mode": mode, **r})
        print(s["photo"], mode, " ".join(f"{k} {v:.2f}" for k, v in r.items()), flush=True)
        time.sleep(a.sleep)


def q(v):
    v = sorted(v)
    return f"{statistics.median(v):.2f} / {v[min(len(v) - 1, round(0.9 * (len(v) - 1)))]:.2f} / {v[-1]:.2f}"


print(f"\n{a.url} 장면 {len(ss)}")
for mode in modes:
    rs = [r for r in rows if r["mode"] == mode]
    print(mode, " · ".join(f"{k} {q([r[k] for r in rs])}" for k in ("wall", "roles", "dora", "last3")))
(RES / f"contention_{a.tag}.json").write_text(json.dumps({"url": a.url, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
