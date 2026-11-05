"""운영 서버에서 앱 흐름이 느린 원인: 호출을 따로 보낼 때 vs 앱처럼 한꺼번에 보낼 때, 업로드만 할 때 시간을 나눈다.
  python -I -X utf8 prod_overlap.py <저장소 루트> [장수]
"""
import io, json, sys, time, uuid, statistics, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(sys.argv[1])
N = int(sys.argv[2]) if len(sys.argv) > 2 else 8
sys.path.insert(0, str(ROOT / "experiments" / "speed"))
import seat_grow as sg  # noqa: E402
from PIL import Image  # noqa: E402

r429 = [0]
URL = "https://mahjong.ai-agent-develop.cloud"
KEY = (ROOT / ".recognizer_key").read_text().strip()


def body(files):
    b = uuid.uuid4().hex
    out = b""
    for name, data in files:
        out += (f"--{b}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"p.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n").encode() + data + b"\r\n"
    return out + f"--{b}--\r\n".encode(), b


def post(path, files, query=None):
    data, b = body(files)
    qs = "&".join(f"{k}={v}" for k, v in (query or {}).items())
    req = urllib.request.Request(f"{URL}{path}?{qs}", data=data, headers={"Content-Type": f"multipart/form-data; boundary={b}", "x-api-key": KEY})
    for _ in range(120):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read()), time.perf_counter() - t0
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(max(10.0, float(e.headers.get("Retry-After") or 5))); r429[0] += 1; continue
            if e.code == 422:
                return {"status": 422}, time.perf_counter() - t0
            raise
    raise RuntimeError("429")


def river_crops(im, g):
    # 강 끝 크롭 흉내: 격자 가운데 칸을 네 변 쪽 띠로(크기만 앱과 비슷하게, 판독 답은 안 봄)
    W, H = im.size
    x1, x2, y1, y2 = (g[k] * (W if k[0] == "x" else H) / 1000 for k in ("x1", "x2", "y1", "y2"))
    w, h = x2 - x1, y2 - y1
    boxes = [(x1, y2 - h * .35, x2, y2), (x1, y1, x2, y1 + h * .35), (x1, y1, x1 + w * .35, y2), (x2 - w * .35, y1, x2, y2)]
    out = []
    for bx in boxes:
        buf = io.BytesIO(); im.crop(tuple(int(v) for v in bx)).save(buf, "JPEG", quality=90); out.append(("images", buf.getvalue()))
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    scenes = [s for s in sg.eval_scenes() if s["name"].startswith("2026") and s["hand"] is not None][:N]
    rows = []
    for s in scenes:
        jpeg = Path(s["path"]).read_bytes()
        g = s["grid"]
        im = Image.open(io.BytesIO(jpeg)).convert("RGB")
        rc = river_crops(im, g)
        q = {"side": s["side"], "x1": g["x1"], "x2": g["x2"], "y1": g["y1"], "y2": g["y2"], "mode": "hybrid"}
        roles = lambda: post("/v2/localroles", [("image", jpeg)], q)
        dora = lambda: post("/v2/localdora", [("image", jpeg)])
        last3 = lambda: post("/v2/locallast3", rc)
        r = {"name": s["name"], "bytes": len(jpeg), "river_bytes": sum(len(d) for _, d in rc)}
        _, r["upload_only"] = post("/v2/localroles", [("image", jpeg)], {"side": "bad", "x1": 1, "x2": 2, "y1": 1, "y2": 2})
        buf = io.BytesIO(); sg.crop(im, sg.seat_box(g, s["side"], 40), s["side"]).save(buf, "JPEG", quality=92)
        seat = lambda: post("/v2/localseat", [("image", buf.getvalue())], {"hand_frac": f"{sg.hand_frac(g, s['side']):.4f}"})
        for k, fn in (("roles", roles), ("dora", dora), ("last3", last3), ("seat", seat)):
            o, t = fn(); r[k] = t; r[k + "_srv"] = o.get("ms", {}).get("total") if isinstance(o.get("ms"), dict) else None
            if k == "roles":
                r["roles_ms"] = o.get("ms")
            time.sleep(1)
        with ThreadPoolExecutor(3) as ex:  # 예전 앱(33f60ee): localseat 크롭 + dora + last3
            t0 = time.perf_counter()
            fs = [ex.submit(fn) for fn in (seat, dora, last3)]
            [f.result() for f in fs]
            r["old3_wall"] = time.perf_counter() - t0
        time.sleep(1)
        with ThreadPoolExecutor(3) as ex:
            t0 = time.perf_counter()
            fs = {k: ex.submit(fn) for k, fn in (("roles", roles), ("dora", dora), ("last3", last3))}
            res = {k: f.result() for k, f in fs.items()}
            r["all3_wall"] = time.perf_counter() - t0
        for k, (o, t) in res.items():
            r["c_" + k] = t; r["c_" + k + "_srv"] = o.get("ms", {}).get("total") if isinstance(o.get("ms"), dict) else None
        r["n429"] = r429[0]; print(json.dumps(r, ensure_ascii=False), flush=True)
        rows.append(r)
        time.sleep(32)
    print("== 중앙(초) ==")
    for k in rows[0]:
        if k in ("name",):
            continue
        v = [x[k] for x in rows if isinstance(x.get(k), (int, float))]
        if v:
            v = [x / 1000 if k.endswith("_srv") else x for x in v]
            print(f"{k:16s} {statistics.median(v):8.2f}  max {max(v):.2f}")


main()
