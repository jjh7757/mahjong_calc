"""헤드 부하 흉내(2026-11-12 발열 시험): 태블릿 대국 화면처럼 [간격]초마다 작은 미리보기 + 4080 미리보기를 받아
걸린 시간·크기·오류를 한 줄 JSON 으로.

  python -I experiments/speed/head_load.py <헤드 주소 http://host:port> <토큰> <출력.jsonl> <초> [간격=3]
"""
import json, sys, time, urllib.request

BASE, TOK, OUT, DUR = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3], float(sys.argv[4])
GAP = float(sys.argv[5]) if len(sys.argv) > 5 else 3


def get(q):
    t = time.time()
    try:
        with urllib.request.urlopen(f"{BASE}/preview?t={TOK}{q}", timeout=20) as r:
            n = len(r.read())
            return {"ok": True, "s": round(time.time() - t, 3), "bytes": n, "size": r.headers.get("X-Frame-Size")}
    except Exception as e:
        return {"ok": False, "s": round(time.time() - t, 3), "err": str(e)[:120]}


end = time.time() + DUR
with open(OUT, "a", encoding="utf-8") as f:
    while time.time() < end:
        t0 = time.time()
        row = {"t": round(t0, 1), "small": get(""), "full": get("&w=4080")}
        f.write(json.dumps(row) + "\n")
        f.flush()
        time.sleep(max(0, GAP - (time.time() - t0)))
