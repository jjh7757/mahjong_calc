"""기기 판독 실험용 onnxruntime 흉내: 서버 app/ 이 쓰는 SessionOptions·InferenceSession(get_inputs·get_outputs·run)만.
실제 계산은 앱의 onnxruntime-android(Java API)가 한다 — Kotlin `dev.jjh.mahjong_calc.OrtBridge` 를 Chaquopy 로 부른다.
텐서는 float32 바이트(byte[])로 오간다. 스레드 수는 ORT_THREADS(기본 4, 태블릿 측정 표 4-1 에서 4가 가장 빠름)."""
from __future__ import annotations

import os

import numpy as np

__version__ = "android-bridge"
_THREADS = int(os.environ.get("ORT_THREADS", "4"))


class SessionOptions:
    def __init__(self):
        self.intra_op_num_threads = 0
        self.inter_op_num_threads = 0
        self.enable_cpu_mem_arena = True
        self.graph_optimization_level = None


class _Arg:
    def __init__(self, name: str, shape: list, type_: str = "tensor(float)"):
        self.name, self.shape, self.type = name, shape, type_


def _bridge():
    from java import jclass

    return jclass("dev.jjh.mahjong_calc.OrtBridge")


class InferenceSession:
    def __init__(self, path, sess_options=None, providers=None, **kw):
        self._b = _bridge()
        self._h = self._b.load(str(path), _THREADS)
        self._inputs = [_Arg(str(n), [None if d < 0 else int(d) for d in self._b.inputShape(self._h, i)])
                        for i, n in enumerate(self._b.inputNames(self._h))]
        self._outputs = [_Arg(str(n), []) for n in self._b.outputNames(self._h)]

    def get_inputs(self):
        return self._inputs

    def get_outputs(self):
        return self._outputs

    def run(self, output_names, input_feed, run_options=None):
        names = list(output_names) if output_names else [o.name for o in self._outputs]
        req = self._b.request(self._h)
        for k, v in input_feed.items():
            a = np.ascontiguousarray(v, dtype=np.float32)
            req.add(k, a.tobytes(), [int(d) for d in a.shape])
        req.run(names)
        out = []
        for i in range(len(names)):
            shape = tuple(int(d) for d in req.shape(i))
            out.append(np.frombuffer(bytes(req.data(i)), dtype="<f4").reshape(shape).copy())
        return out


def get_available_providers():
    return ["CPUExecutionProvider"]
