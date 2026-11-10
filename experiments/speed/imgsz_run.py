"""검출 입력 크기(서버 app.local_read.IMG, 운영 1280)·분류기 입력 크기(CLS_SIZE, 운영 128)만 바꿔 다른 측정 스크립트를 그대로 돌린다(2026-11-10, 해상도 실험).

  [CLS_SIZE=<분류기 크기>] python -I -X utf8 experiments/speed/imgsz_run.py <IMG> <스크립트.py> [그 스크립트 인자...]
  예) ROBUST_CLS=cls6 ROBUST_ROLE=tile-roles-v3r15d python -I -X utf8 experiments/speed/imgsz_run.py 1920 experiments/speed/robust_suite.py run --models fold --tag img1920_1110

IMG 는 _letterbox·detect 가 부를 때마다 읽는 모듈 상수라, 자리 판독 회전 상자 검출기(det_r8)와 강·표시패 검출기(2회차) 모두 바뀐다.
검출기 ONNX 입력은 높이·너비가 동적이라 모델은 그대로 쓴다(1280 으로 학습한 모델). 분류기 ONNX 는 크기가 고정이라
CLS_SIZE 를 바꾸면 그 크기로 학습한 분류기(train.py 를 같은 CLS_SIZE 로)를 줘야 한다. SMALL_TILE(작은 패 키워 읽기 문턱 96)은 그대로 둔다.
"""
import os
import runpy
import sys
from pathlib import Path

img, script, rest = int(sys.argv[1]), Path(sys.argv[2]).resolve(), sys.argv[3:]
repo = os.environ.get("RECOGNIZER_REPO", "C:/Users/jjh7757/dev/mahjong-recognizer")
sys.path.insert(0, repo)
sys.path.insert(0, str(script.parent))
from app import local_read  # noqa: E402

local_read.IMG = img
if os.environ.get("CLS_SIZE"):
    local_read.CLS_SIZE = int(os.environ["CLS_SIZE"])
print(f"[imgsz_run] app.local_read.IMG = {local_read.IMG}, CLS_SIZE = {local_read.CLS_SIZE}", flush=True)
sys.argv = [str(script), *rest]
runpy.run_path(str(script), run_name="__main__")
