"""분류기 입력 크기 실험: 나눔 분류기 clsr<N>_<part>.onnx 를 그 나눔의 홀드아웃 크롭으로 채점 + 크롭 한 장 추론 시간(2026-11-10).
CLS_SIZE 환경 변수를 <N> 과 같게 주고 부른다(train.SIZE 가 import 때 읽음).
  CLS_SIZE=96 python -I -X utf8 experiments/speed/clssize_holdout.py 96 <TAG>  → results/clssize_holdout_<TAG>.json 에 덧붙임
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tile_classifier"))
import train  # noqa: E402

n, tag = int(sys.argv[1]), sys.argv[2]
assert train.SIZE == n, f"CLS_SIZE({train.SIZE}) 와 {n} 이 다름"
res = train.holdout_eval((f"clsr{n}",))
# 추론 시간: 세운 크롭 64장 묶음 한 번(서버처럼 2 스레드), 다섯 번 중 중앙
import onnxruntime as ort  # noqa: E402

opts = ort.SessionOptions()
opts.intra_op_num_threads = 2
sess = ort.InferenceSession(str(train.MODELS / f"clsr{n}_all.onnx"), sess_options=opts, providers=["CPUExecutionProvider"])
x = np.random.rand(64, 3, n, n).astype(np.float32)
sess.run(None, {"x": x})
ts = []
for _ in range(5):
    t = time.perf_counter()
    sess.run(None, {"x": x})
    ts.append(time.perf_counter() - t)
res["ms_per_64"] = round(sorted(ts)[2] * 1000, 1)
out = HERE / "results" / f"clssize_holdout_{tag}.json"
d = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
d[str(n)] = res
out.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
print(n, json.dumps(res, ensure_ascii=False))
