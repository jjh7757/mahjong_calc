"""배포 뒤 확인: 운영 /v2/localroles(hybrid)·/v2/localseat 에 개발 세트(sg.eval_scenes, 가림·사용자 문제 제외)를 보내 채점한다(2026-11-05).
role_full_bench.py --native 와 같은 채점(judge). 앱 흐름(flutter drive)이 아니라 서버 단독이다.
  python -I -X utf8 experiments/tile_classifier/server_bench/prod_roles_check.py [URL]
결과 data/role/bench/prod_roles_<git_sha 앞 7>.json
"""
from __future__ import annotations

import io
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "speed"))
sys.path.insert(0, str(HERE.parents[1] / "yolo"))
import hybrid as hy  # noqa: E402
import seat_grow as sg  # noqa: E402
from PIL import Image  # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else "https://mahjong.ai-agent-develop.cloud"
KEY = (HERE.parents[2] / ".recognizer_key").read_text().strip()
OUT = HERE.parent / "data" / "role" / "bench"


def post(path: str, jpeg: bytes, query: dict) -> tuple[dict, float]:
    b = uuid.uuid4().hex
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"p.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n").encode() + jpeg + f"\r\n--{b}--\r\n".encode()
    qs = "&".join(f"{k}={v}" for k, v in query.items())
    req = urllib.request.Request(f"{URL}{path}?{qs}", data=body, headers={"Content-Type": f"multipart/form-data; boundary={b}", "x-api-key": KEY})
    for _ in range(10):  # 운영 요청 제한(429): Retry-After 만큼 쉬고 다시
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read()), time.perf_counter() - t0
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            time.sleep(float(e.headers.get("Retry-After") or 5))
    raise RuntimeError("429 가 계속됨")


def judge(hand: list[str], melds: list[str], block: bool, s: dict) -> tuple[bool, bool]:
    key = lambda ms: sorted(" ".join(sorted(m.split())) for m in ms)
    ok = bool(hand) and sorted(hand) == sorted(s["hand"]) and key(melds) == key(s["melds"])
    auto = bool(hand) and not block and hy.check(hand, [m.split() for m in melds])[0]
    return ok, auto


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    with urllib.request.urlopen(URL + "/") as r:
        sha = json.loads(r.read())["git_sha"][:7]
    rows, tot, secs = {}, dict(n=0, roles_ok=0, roles_bad=0, seat_ok=0, seat_bad=0), {"roles": [], "seat": []}
    for s in sg.eval_scenes():
        if s["hand"] is None:
            continue
        w = 1 if s["name"].startswith("2026") else 2
        jpeg = Path(s["path"]).read_bytes()
        g = s["grid"]
        o, t = post("/v2/localroles", jpeg, {"side": s["side"], "x1": g["x1"], "x2": g["x2"], "y1": g["y1"], "y2": g["y2"], "mode": "hybrid"})
        hand = [x["tile"] for x in o["tiles"]] + ([o["separate_tile"]["tile"]] if o["separate_tile"] else [])
        melds = [" ".join(m["tiles"]) for m in o["melds"]]
        r_ok, r_auto = judge(hand, melds, o.get("block", False), s)
        secs["roles"].append(o["ms"]["total"] / 1000)
        crop = sg.crop(Image.open(io.BytesIO(jpeg)).convert("RGB"), sg.seat_box(g, s["side"], 40), s["side"])
        buf = io.BytesIO()
        crop.save(buf, "JPEG", quality=92)
        q, _ = post("/v2/localseat", buf.getvalue(), {"hand_frac": f"{sg.hand_frac(g, s['side']):.4f}"})
        qh = [x["tile"] for x in q["tiles"]] + ([q["separate_tile"]["tile"]] if q["separate_tile"] else [])
        qm = [" ".join(m["tiles"]) for m in q["melds"]]
        q_ok, q_auto = judge(qh, qm, False, s)
        secs["seat"].append(q["ms"]["total"] / 1000)
        tot["n"] += w
        tot["roles_ok"] += w * r_ok
        tot["roles_bad"] += w * (r_auto and not r_ok)
        tot["seat_ok"] += w * q_ok
        tot["seat_bad"] += w * (q_auto and not q_ok)
        rows[s["name"]] = dict(w=w, roles=dict(hand=hand, melds=melds, ok=r_ok, auto=r_auto, ms=o["ms"], http_s=round(t, 2)), seat=dict(hand=qh, melds=qm, ok=q_ok, auto=q_auto, ms=q["ms"]))
        print(s["name"][-6:], "roles", "O" if r_ok else "X", "seat", "O" if q_ok else "X", f"{o['ms']['total']}ms / http {t:.1f}s", flush=True)

    def stat(v: list) -> str:
        v = sorted(v)
        return f"{statistics.median(v):.2f} / {v[int(0.9 * (len(v) - 1))]:.2f} / {v[-1]:.2f}"

    print(f"--- {sha} /{tot['n']}: localroles {tot['roles_ok']}(틀린 자동 {tot['roles_bad']}) 서버 {stat(secs['roles'])}초 | localseat {tot['seat_ok']}(틀린 자동 {tot['seat_bad']}) 서버 {stat(secs['seat'])}초")
    (OUT / f"prod_roles_{sha}.json").write_text(json.dumps(dict(sha=sha, total=tot, rows=rows), ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
