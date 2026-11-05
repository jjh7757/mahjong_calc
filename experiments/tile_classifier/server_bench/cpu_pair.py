"""한 판에 서버가 하는 일(localroles + localdora 같은 원본)을 차례로: 나눔 끔(캐시 매번 비움 = 전) vs 켬(후). 노트북, ONNX 2 스레드."""
import statistics as st, sys, time
from pathlib import Path
sys.path.insert(0, r"C:\Users\jjh7757\dev\mahjong-recognizer")
sys.path.insert(0, r"C:\Users\jjh7757\dev\mahjong_calc\experiments\speed")
from app import local_read as lr, roles, main as server
import seat_grow as sg

rd = lr.LocalReader()
sc = [s for s in sg.eval_scenes() if s["name"].startswith("2026") and s["hand"] is not None][:10]


def pair(raw, s, share):
    if not share:
        server._prepared.clear(); lr._decoded.clear()
    j = server._prepare_shared(raw, 4080)
    roles.read_roles(rd, j, s["side"], s["grid"])
    if not share:
        server._prepared.clear(); lr._decoded.clear()
    j2 = server._prepare_shared(raw, 4080)
    rd.read_wall(j2)


T = {False: [], True: []}
for s in sc:
    raw = Path(s["path"]).read_bytes()
    pair(raw, s, False)  # 데움
    for share in (False, True, False, True):
        server._prepared.clear(); lr._decoded.clear()
        t = time.perf_counter(); pair(raw, s, share); T[share].append(time.perf_counter() - t)
for k, v in T.items():
    print("나눔", "켬" if k else "끔", f"중앙 {st.median(v)*1000:.0f} ms  최대 {max(v)*1000:.0f}")
