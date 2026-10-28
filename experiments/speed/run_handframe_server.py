"""로컬 인식 서버를 HANDONLY_FRAME=1(손패 전용도 자리 틀 + 조각 읽기, 실험)로 띄운다. 나머지는 run_local_server.py 와 같다.

  python experiments/speed/run_handframe_server.py [--port 8032]   (launch.json "recognizer-handframe")
"""
import os
import runpy
import sys
from pathlib import Path

os.environ["HANDONLY_FRAME"] = "1"
if "--port" not in sys.argv:
    sys.argv += ["--port", "8032"]
runpy.run_path(str(Path(__file__).parents[1] / "yolo" / "run_local_server.py"), run_name="__main__")
