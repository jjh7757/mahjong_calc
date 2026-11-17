"""시험 판 정답 확인 페이지 서버(2026-11-16 밤, 계획서 3단계 "추가 8"). 내 컴퓨터 안에서만 돈다(127.0.0.1).

  python -X utf8 truthserver.py [포트 8311] [--ans <답 파일>]   # --ans: 시험용 — 진짜 answers_user.json 대신 다른 파일에 씀
프레임·차례 목록은 truthprep.py 가 만든 _work/testtruth_1116/ 에서 읽고, 답은 같은 폴더 answers_user.json 에 그때그때 쓴다
(바뀔 때마다 answers_log.jsonl 에도 한 줄 — 덮어써도 되돌릴 수 있게).
"""
from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import htcommon as hc  # noqa: E402

BASE = hc.WORK / "testtruth_1116"
ANS = BASE / "answers_user.json"
LOCK = threading.Lock()


def load_answers() -> dict:
    return json.loads(ANS.read_text(encoding="utf-8")) if ANS.exists() else {}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 조용히
        pass

    def send(self, code, body: bytes, ctype: str, cache=False):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=86400" if cache else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self.send(200, (HERE / "truthpage.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/turns.json":
            return self.send(200, (BASE / "turns.json").read_bytes(), "application/json")
        if path == "/answers":
            with LOCK:
                return self.send(200, json.dumps(load_answers(), ensure_ascii=False).encode(), "application/json")
        if path.startswith("/f/"):
            parts = path.split("/")
            if len(parts) == 4 and parts[2].replace("_", "").isalnum() and parts[3].replace(".jpg", "").isdigit():
                f = BASE / "frames" / parts[2] / parts[3]
                if f.exists():
                    return self.send(200, f.read_bytes(), "image/jpeg", cache=True)
        self.send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path != "/save":
            return self.send(404, b"not found", "text/plain")
        try:
            d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            tid, ans = str(d["id"]), d["answer"]
            assert isinstance(ans, dict) and len(tid) < 20
        except Exception:  # noqa: BLE001
            return self.send(400, b"bad request", "text/plain")
        ans["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with LOCK:
            a = load_answers()
            a[tid] = ans
            tmp = ANS.with_suffix(".tmp")
            tmp.write_text(json.dumps(a, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(ANS)
            with open(ANS.parent / ("answers_log.jsonl" if ANS.parent == BASE else ANS.stem + "_log.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps({"id": tid, **ans}, ensure_ascii=False) + "\n")
        self.send(200, b'{"ok":true}', "application/json")


def main():
    global ANS
    args = sys.argv[1:]
    if "--ans" in args:
        i = args.index("--ans")
        ANS = Path(args[i + 1]).resolve()
        del args[i:i + 2]
    port = int(args[0]) if args else 8311
    BASE.mkdir(parents=True, exist_ok=True)
    print(f"http://127.0.0.1:{port}  (답 → {ANS})", flush=True)
    ThreadingHTTPServer.request_queue_size = 128  # 기본 5 — 프레임 요청이 몰리면 접속을 거절해 그림이 깨졌다(11-17)
    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


if __name__ == "__main__":
    main()
