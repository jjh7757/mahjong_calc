"""카메라 헤드 미리보기를 일정 간격으로 받아 저장한다(추적 문턱 확인용 실제 프레임).

  python experiments/tracking/grab_frames.py http://<헤드IP>:8765 <출력 폴더> --token <QR 의 t> [--n 20] [--gap 3]
"""
import argparse
import os
import time

import requests

ap = argparse.ArgumentParser()
ap.add_argument("url")
ap.add_argument("out")
ap.add_argument("--token", default="")
ap.add_argument("--n", type=int, default=20)
ap.add_argument("--gap", type=float, default=3.0)
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
for i in range(a.n):
    t0 = time.time()
    r = requests.get(f"{a.url.rstrip('/')}/preview", headers={"X-Head-Token": a.token}, timeout=10)
    r.raise_for_status()
    with open(os.path.join(a.out, f"f{i:02d}.jpg"), "wb") as f:
        f.write(r.content)
    print(i, len(r.content), r.headers.get("X-Frame-Size"), flush=True)
    time.sleep(max(0.0, a.gap - (time.time() - t0)))
