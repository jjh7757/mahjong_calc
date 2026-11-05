"""가짜 카메라 헤드: /status·/preview·/capture 를 사진 폴더로 응답한다(웹·노트북 확인용, CORS 포함).

사용:
  python -I fake_head.py <사진 폴더> <포트>                       # 사진을 요청마다 차례로(배경이 바뀌는 것 확인)
  python -I fake_head.py <시퀀스 폴더> <포트> --seq --hold 12,6     # f0.jpg,f1.jpg,… 를 시간순으로 재생(판 상태 추적 확인)
  python -I fake_head.py <사진 폴더> <포트> --after-capture          # 첫 사진만 보여 주다가 /capture 마다 다음 사진(프레임 투표 확인:
                                                                     #   화료 촬영 = 첫 사진, 그 뒤 프레임 = 같은 판의 둘째 사진)
  --raw-full: /preview?w= 가 원본 긴 변 이상이면 다시 저장하지 않고 원본 바이트(기본은 늘 q80 으로 다시 저장 = 실제 헤드 YUV→JPEG 흉내)
--seq: 첫 요청 시각부터 hold 초씩 f0, f1, … 을 보여 주고 마지막 프레임은 계속. /preview 는 긴 변 w(기본 960)로 줄이고
X-Frame-Size 에 원 크기를 적는다. /capture 는 현재 프레임 원본.
"""
import io, sys, os, json, time, itertools
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from PIL import Image

folder, port = sys.argv[1], int(sys.argv[2])
SEQ = "--seq" in sys.argv
AFTER_CAPTURE = "--after-capture" in sys.argv
RAW_FULL = "--raw-full" in sys.argv  # /preview?w= 가 원본 긴 변 이상이면 q80 다시 저장 없이 원본 바이트(프레임 투표 확인)
HOLD = [float(x) for x in (sys.argv[sys.argv.index("--hold") + 1].split(",") if "--hold" in sys.argv else ["10"])]
photos = sorted(f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".jpeg")) and "thumb" not in f)
cycle = itertools.cycle(photos)
TOKEN = "local"
count = {"cap": 0, "prev": 0}
t0 = {"t": None}


def current() -> str:
    if AFTER_CAPTURE:
        return photos[min(count["cap"], len(photos) - 1)]
    if not SEQ:
        return next(cycle)
    if t0["t"] is None:
        t0["t"] = time.time()
    el = time.time() - t0["t"]
    acc = 0.0
    for i, h in enumerate(HOLD):
        acc += h
        if el < acc:
            return photos[min(i, len(photos) - 1)]
    return photos[-1]


class H(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "X-Head-Token")
        self.send_header("Access-Control-Expose-Headers", "X-Frame-Size, X-Zoom")
        self.send_header("Cache-Control", "no-store")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _auth(self, q):
        return self.headers.get("X-Head-Token") == TOKEN or q.get("t", [None])[0] == TOKEN

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        path = u.path
        if path in ("/", "/status"):
            body = json.dumps({"ok": True, "auth": self._auth(q), "captures": count["cap"]}).encode()
            self.send_response(200); self._cors()
            self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body); return
        if path in ("/preview", "/capture"):
            if not self._auth(q):
                self.send_response(401); self._cors(); self.end_headers(); return
            name = current()
            full = os.path.join(folder, name)
            if path == "/capture":
                data = open(full, "rb").read()
                size = Image.open(full).size
                count["cap"] += 1
            else:
                im = Image.open(full).convert("RGB")
                size = im.size
                w = int(q.get("w", ["960"])[0])
                if RAW_FULL and max(size) <= w:
                    data = open(full, "rb").read()  # 줄일 필요가 없으면 원본 그대로(--raw-full, 다시 저장하지 않음)
                else:
                    im.thumbnail((w, w))
                    buf = io.BytesIO(); im.save(buf, "JPEG", quality=80); data = buf.getvalue()
                count["prev"] += 1
            self.send_response(200); self._cors()
            self.send_header("Content-Type", "image/jpeg"); self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Zoom", "1.00"); self.send_header("X-Frame-Size", f"{size[0]}x{size[1]}")
            self.end_headers(); self.wfile.write(data)
            print(f"{time.strftime('%H:%M:%S')} {path} {name} w={q.get('w', ['-'])[0]} -> {len(data)}B", flush=True)
            return
        self.send_response(404); self._cors(); self.end_headers()

    def log_message(self, *a):
        pass


print("photos", photos, "after-capture" if AFTER_CAPTURE else "seq" if SEQ else "cycle", HOLD, flush=True)
ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
