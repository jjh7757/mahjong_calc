"""서버 판독 흐름을 "추론만 태블릿" 으로: robust_suite run(서버 app.roles.read_roles hybrid = /v2/localroles 경로)을 그대로 돌리되
onnxruntime.InferenceSession.run 을 태블릿 ort_daemon(adb forward tcp:9555)으로 보낸다. 전처리·NMS·후처리는 PC Python 그대로.

    python -I -X utf8 experiments/ondevice/run_flow.py --tag <TAG> [--pc]  [robust_suite run 인수(--only orig 기본)]

--pc 면 바꿔 끼우지 않고(같은 시각 비교용) 똑같이 돈다. --cv2shim 이면 cv2 를 기기용 흉내로. --prepskip 이면 prepare_image 를 기기의 재저장 생략과 같게. 사진마다 태블릿 추론 합·왕복 합·호출 수를 results/flow_<TAG>.json 에 남긴다.
결과 채점 JSON 은 robust_suite 가 experiments/speed/results/robust_prod_<TAG>.json 으로 쓴다.
"""
from __future__ import annotations

import json
import os
import socket
import struct
import sys
import threading
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "speed"))
PORT = int(os.environ.get("ORT_DAEMON_PORT", "9555"))

STATS = {"calls": 0, "infer": 0.0, "rtt": 0.0, "by_model": {}}


class _Conn:
    lock = threading.Lock()
    sock: socket.socket | None = None

    @classmethod
    def get(cls) -> socket.socket:
        if cls.sock is None:
            s = socket.create_connection(("127.0.0.1", PORT))
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            cls.sock = s
        return cls.sock


def _recv(s: socket.socket, n: int) -> bytes:
    b = bytearray()
    while len(b) < n:
        k = s.recv(n - len(b))
        if not k:
            raise ConnectionError("데몬 연결 끊김")
        b += k
    return bytes(b)


def _str(x: str) -> bytes:
    e = x.encode()
    return struct.pack("<I", len(e)) + e


def remote_run(model: str, feed: dict, outs: list[str]) -> tuple[list[np.ndarray], float]:
    parts = [_str(model), struct.pack("<I", len(feed))]
    for k, v in feed.items():
        a = np.ascontiguousarray(v, dtype=np.float32)
        parts += [_str(k), struct.pack("<I", a.ndim), struct.pack(f"<{a.ndim}q", *a.shape), a.tobytes()]
    parts.append(struct.pack("<I", len(outs)))
    parts += [_str(o) for o in outs]
    with _Conn.lock:
        s = _Conn.get()
        s.sendall(b"".join(parts))
        st = struct.unpack("<I", _recv(s, 4))[0]
        if st != 0:
            n = struct.unpack("<I", _recv(s, 4))[0]
            raise RuntimeError("태블릿: " + _recv(s, n).decode(errors="replace"))
        secs, nout = struct.unpack("<dI", _recv(s, 12))
        res = []
        for _ in range(nout):
            nd = struct.unpack("<I", _recv(s, 4))[0]
            shape = struct.unpack(f"<{nd}q", _recv(s, 8 * nd)) if nd else ()
            cnt = int(np.prod(shape)) if nd else 1
            res.append(np.frombuffer(_recv(s, 4 * cnt), np.float32).reshape(shape).copy())
    return res, secs


def patch() -> None:
    import onnxruntime as ort

    Real = ort.InferenceSession

    class TabletSession:
        """메타데이터(get_inputs 등)는 PC 세션에서, run 은 태블릿에서."""

        def __init__(self, path, sess_options=None, providers=None, **kw):
            self._real = Real(str(path), providers=["CPUExecutionProvider"])
            self._model = Path(path).name

        def get_inputs(self):
            return self._real.get_inputs()

        def get_outputs(self):
            return self._real.get_outputs()

        def get_modelmeta(self):
            return self._real.get_modelmeta()

        def run(self, output_names, input_feed, run_options=None):
            names = list(output_names) if output_names else [o.name for o in self._real.get_outputs()]
            t0 = time.perf_counter()
            outs, secs = remote_run(self._model, input_feed, names)
            rtt = time.perf_counter() - t0
            STATS["calls"] += 1
            STATS["infer"] += secs
            STATS["rtt"] += rtt
            m = STATS["by_model"].setdefault(self._model, {"calls": 0, "infer": 0.0})
            m["calls"] += 1
            m["infer"] += secs
            return outs

    ort.InferenceSession = TabletSession


def main() -> None:
    args = sys.argv[1:]
    pc = "--pc" in args
    if "--cv2shim" in args:  # 기기용 cv2 흉내(android/app/src/main/python/cv2)를 진짜 대신
        sys.path.insert(0, str(ROOT / "android" / "app" / "src" / "main" / "python"))
        sys.modules.pop("cv2", None)
    prepskip = "--prepskip" in args  # 기기 판독의 재저장 생략(ondevice.py PREP="skip")과 같게 prepare_image 를 바꿔 끼움
    args = [a for a in args if a not in ("--pc", "--cv2shim", "--prepskip")]
    tag = args[args.index("--tag") + 1]
    if "--only" not in args:
        args += ["--only", "orig"]
    if not pc:
        patch()
    import robust_suite as rs
    from app import recognizer, roles

    if prepskip:
        import io

        from PIL import Image

        real_prep = recognizer.prepare_image
        STATS["prep_skip"] = {"skip": 0, "prep": 0}

        def skip_prep(data: bytes, max_side: int = 1568) -> bytes:
            """android/app/src/main/python/ondevice.py _prepare_now(PREP="skip") 와 같은 조건."""
            img = Image.open(io.BytesIO(data))
            if img.format == "JPEG" and max(img.size) <= max_side and img.getexif().get(0x0112, 1) in (None, 1) and img.mode == "RGB":
                STATS["prep_skip"]["skip"] += 1
                return data
            STATS["prep_skip"]["prep"] += 1
            return real_prep(data, max_side)

        recognizer.prepare_image = skip_prep

    real_read = roles.read_roles
    per = []

    def timed_read(*a, **kw):
        c0, i0, r0 = STATS["calls"], STATS["infer"], STATS["rtt"]
        t0 = time.perf_counter()
        try:
            return real_read(*a, **kw)
        finally:
            per.append({"secs": time.perf_counter() - t0, "calls": STATS["calls"] - c0, "infer": STATS["infer"] - i0, "rtt": STATS["rtt"] - r0})

    roles.read_roles = timed_read
    sys.argv = ["robust_suite.py", "run", "--models", "prod", *args]
    rs.main()
    out = HERE / "results" / f"flow_{tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"tablet": not pc, "prep_skip": STATS.get("prep_skip"), "per": per, "by_model": STATS["by_model"]}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("→", out)


if __name__ == "__main__":
    main()
