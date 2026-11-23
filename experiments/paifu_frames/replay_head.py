"""저장 프레임을 찍힌 시각 간격대로 내주는 가짜 헤드 + 시험 조종 · 결과 받기(2026-11-17).

`integration_test/paifu_live_replay_test.dart` 가 거치 화면을 여기에 붙여 판 중 버림 기록기를 실제 속도로 돌린다.
프레임 · 목록은 `device_replay.py make` 가 만든 것(`experiments/ondevice/build/bench/p1114/`)을 쓴다.

  python -X utf8 experiments/paifu_frames/replay_head.py 8777        (127.0.0.1 — 태블릿은 `adb reverse tcp:8777 tcp:8777`)

  GET /ctl?unit=<묶음>   묶음을 걸어 둔다(시계는 그 뒤 첫 /preview 에서 시작). 답: 프레임 수 · 길이 · 격자(펠트로 고친 C) · 선 · 아래 자리 · 국
  GET /state             지난 시간 · 끝났는지(마지막 프레임 뒤 TAIL 초)
  GET /status /preview /capture   헤드와 같은 응답. /preview 는 w 가 없으면 긴 변 1020, w ≥ 1600 이면 저장된 바이트 그대로(실제 헤드가
                         그날 준 프레임), 그 밖엔 긴 변 w 로 줄여 q80. 프레임 = 지난 시간까지 찍힌 것 중 마지막.
  POST /result?name=<이름>   본문(JSON)을 results/device_1117/live/<이름>.json 으로
요청마다 results/device_1117/live/head_log.jsonl 에 한 줄.
"""
from __future__ import annotations

import io
import json
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import heldout_1114 as ho  # noqa: E402

STAGE = HERE.parents[1] / "experiments" / "ondevice" / "build" / "bench" / "p1114"
OUT = HERE / "results" / "device_1117" / "live"
TAIL = 20.0  # 마지막 프레임을 이만큼 더 보여 준 뒤 끝(15초마다 다시 읽기가 한 번은 걸리게)
port = int(sys.argv[1])
INDEX = json.loads((STAGE / "index.json").read_text(encoding="utf-8"))
ROUNDS = json.loads((ho.OUT / "rounds.json").read_text(encoding="utf-8"))
GRIDS = ho.grids_c()
WIND = {"r12": 0, "r13": 0, "r14": 0, "r15": 1, "r16": 1, "r17": 1, "r18": 1, "r19": 1, "r20": 0}
S = {"unit": None, "frames": [], "offs": [], "t0": None}
LOCK = threading.Lock()
OUT.mkdir(parents=True, exist_ok=True)


def log(**kw):
    with LOCK, open(OUT / "head_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(dict(at=datetime.now().isoformat(timespec="milliseconds"), unit=S["unit"], **kw), ensure_ascii=False) + "\n")


def arm(unit: str) -> dict:
    fr = INDEX[unit]["frames"]
    ts = [datetime.fromisoformat(f["at"]).timestamp() for f in fr]
    S.update(unit=unit, frames=fr, offs=[t - ts[0] for t in ts], t0=None)
    rd = ROUNDS[unit]
    g = GRIDS[f"20261114_{rd['track']}_track"]["C"]["grid"]
    return dict(unit=unit, n=len(fr), duration=S["offs"][-1], tail=TAIL, grid=g, bottom=rd["bottom"], dealer=rd["dealer"],
                dealer_side=rd["dealer_side"], round_wind=WIND[rd["rn"]], round_number=rd["dealer"] + 1, first_at=fr[0]["at"])


def elapsed() -> float:
    return 0.0 if S["t0"] is None else time.time() - S["t0"]


def current(start: bool) -> tuple[int, dict]:
    if S["t0"] is None and start:
        S["t0"] = time.time()
    el = elapsed()
    i = max(k for k, o in enumerate(S["offs"]) if o <= el)
    return i, S["frames"][i]


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, body=b"", ctype="application/json", extra=()):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, o, code=200):
        self._send(code, json.dumps(o, ensure_ascii=False).encode())

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/ctl":
            info = arm(q["unit"][0])
            log(path="/ctl", n=info["n"], duration=info["duration"])
            return self._json(info)
        if u.path == "/state":
            dur = S["offs"][-1] if S["offs"] else 0
            return self._json(dict(unit=S["unit"], started=S["t0"] is not None, elapsed=round(elapsed(), 1), duration=dur, done=S["t0"] is not None and elapsed() > dur + TAIL))
        if u.path in ("/", "/status"):
            return self._json({"ok": True, "auth": True, "captures": 0})
        if u.path in ("/preview", "/capture") and S["unit"]:
            i, f = current(start=u.path == "/preview")
            p = STAGE / f["stage"]
            w = int(q["w"][0]) if "w" in q else None
            if u.path == "/capture" or (w is not None and w >= 1600):
                data = p.read_bytes()
            else:
                im = Image.open(p).convert("RGB")
                im.thumbnail((w or 1020, w or 1020))
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=80)
                data = buf.getvalue()
            log(path=u.path, w=w, i=i, file=f["file"], el=round(elapsed(), 2), bytes=len(data))
            return self._send(200, data, "image/jpeg", (("X-Zoom", "1.00"), ("X-Frame-Size", f"{f['w']}x{f['h']}")))
        self._send(404)

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if u.path == "/result":
            name = q["name"][0].replace("/", "_")
            (OUT / f"{name}.json").write_bytes(body)
            log(path="/result", name=name, bytes=len(body))
            return self._json({"ok": True})
        self._send(404)

    def log_message(self, *a):
        pass


print("replay head", port, "묶음", list(INDEX), flush=True)
ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
