"""자체 YOLO26n + 분류기 자리 판독을 서버 환경(onnxruntime 만, torch·ultralytics 없음)에서 잰다(2026-11-02). 표 1-23 마지막 규칙과 같은 흐름.
크롭을 디코드 → 운영 st.frame, 안 되면 통째 검출 + 규칙 → 패마다 분류. 결과 RESULT 줄(JSON)과 요약. score.py 가 torch 판 결과와 맞춰 본다.
  python bench.py [--threads 2] [--repeat 3] [--one]    --one 은 검출기·분류기 한 벌만(운영 모양, 메모리 재기, 답은 안 맞춤)
"""
from __future__ import annotations

import argparse
import io
import json
import os
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from rules_core import ANGLES, ok2, rv, split2, st, strays  # noqa: E402

O = {"이웃", "두단", "옅음", "백", "떼어둠", "줄"}
IMG = 1280


def session(path: Path, threads: int) -> ort.InferenceSession:
    so = ort.SessionOptions()
    so.enable_cpu_mem_arena = False
    so.intra_op_num_threads = threads
    return ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])


class Det:
    """ultralytics 예측과 같게: 긴 변 1280, 짧은 변은 32 배수로 가운데 패딩, conf 0.25, NMS 0.7. 같은 그림은 다시 돌리지 않는다."""

    def __init__(self, path: Path, threads: int):
        self.s = session(path, threads)
        self.memo: dict = {}
        self.runs = 0

    def detect(self, rgb: np.ndarray, low: bool = False) -> list:
        key = (rgb.shape, hash(rgb.tobytes()))
        if key not in self.memo:
            self.memo = {key: self._detect(rgb)} | dict(list(self.memo.items())[-4:])
        return self.memo[key]

    def _detect(self, rgb: np.ndarray) -> list:
        self.runs += 1
        H, W = rgb.shape[:2]
        r = min(IMG / H, IMG / W)
        nw, nh = round(W * r), round(H * r)
        cw, ch = -(-nw // 32) * 32, -(-nh // 32) * 32
        left, top = round((cw - nw) / 2 - 0.1), round((ch - nh) / 2 - 0.1)
        canvas = np.full((ch, cw, 3), 114, np.uint8)
        canvas[top:top + nh, left:left + nw] = np.asarray(Image.fromarray(rgb).resize((nw, nh), Image.BILINEAR))
        x = canvas.transpose(2, 0, 1)[None].astype(np.float32) / 255
        out = self.s.run(None, {self.s.get_inputs()[0].name: x})[0][0]
        keep = out[4] >= 0.25
        cx, cy, w, h, c = out[0][keep], out[1][keep], out[2][keep], out[3][keep], out[4][keep]
        x0, y0, x1, y1 = (cx - w / 2 - left) / r, (cy - h / 2 - top) / r, (cx + w / 2 - left) / r, (cy + h / 2 - top) / r
        order, boxes = list(np.argsort(-c)), []
        while order:
            i = order.pop(0)
            boxes.append((max(0.0, float(x0[i])), max(0.0, float(y0[i])), min(float(W), float(x1[i])), min(float(H), float(y1[i]))))
            rest = []
            for j in order:
                ix, iy = min(x1[i], x1[j]) - max(x0[i], x0[j]), min(y1[i], y1[j]) - max(y0[i], y0[j])
                inter = max(0.0, ix) * max(0.0, iy)
                if inter / ((x1[i] - x0[i]) * (y1[i] - y0[i]) + (x1[j] - x0[j]) * (y1[j] - y0[j]) - inter + 1e-9) <= 0.7:
                    rest.append(j)
            order = rest
        return [(int(a), int(b), int(c2 - a), int(d - b)) for a, b, c2, d in boxes if c2 - a >= 2 and d - b >= 2]


class Cls:
    def __init__(self, path: Path, meta: dict, threads: int):
        self.s = session(path, threads)
        self.classes, self.size = meta["classes"], meta["size"]
        self.mean, self.std = np.array(meta["mean"], np.float32)[:, None, None], np.array(meta["std"], np.float32)[:, None, None]

    def tensor(self, im: Image.Image) -> np.ndarray:
        im = im.copy()
        im.thumbnail((self.size, self.size))
        out = Image.new("RGB", (self.size, self.size), (114, 114, 114))
        out.paste(im, ((self.size - im.width) // 2, (self.size - im.height) // 2))
        return (np.asarray(out, np.float32).transpose(2, 0, 1) / 255 - self.mean) / self.std

    def probs(self, ims: list[Image.Image]) -> np.ndarray:
        y = self.s.run(None, {"x": np.stack([self.tensor(i) for i in ims])})[0]
        e = np.exp(y - y.max(1, keepdims=True))
        return e / e.sum(1, keepdims=True)

    def read(self, ims: list[Image.Image]) -> list[str]:
        return [self.classes[int(k)] for k in self.probs(ims).argmax(1)] if ims else []


PAD = 0.12


def cut(rgb: np.ndarray, b) -> Image.Image:
    x, y, w, h = b
    H, W = rgb.shape[:2]
    px, py = int(w * PAD), int(h * PAD)
    return Image.fromarray(rgb[max(0, y - py):min(H, y + h + py), max(0, x - px):min(W, x + w + px)])


def read_turned(c: Cls, rgb: np.ndarray, b, tw: float, th: float) -> str:
    cx, cy, r = b[0] + b[2] / 2, b[1] + b[3] / 2, int(max(b[2], b[3], th))
    H, W = rgb.shape[:2]
    part = Image.fromarray(rgb).crop((max(0, int(cx - r)), max(0, int(cy - r)), min(W, int(cx + r)), min(H, int(cy + r))))
    m = part.width / 2, part.height / 2
    box = (int(m[0] - tw / 2), int(m[1] - th / 2), int(m[0] + tw / 2), int(m[1] + th / 2))
    p = c.probs([part.rotate(a).crop(box) for a in ANGLES])
    return c.classes[int(p.max(0).argmax())]


def read_meld_tile(c: Cls, rgb: np.ndarray, b) -> str:
    """울기는 눕힌 패가 있어 방향을 고른다(harvest.label). 세운 패는 그대로."""
    im = cut(rgb, b)
    if b[2] <= 1.15 * b[3]:
        return c.read([im])[0]
    ims = [im.rotate(90 * k, expand=True) for k in (1, 3)]
    p = c.probs(ims)
    return c.classes[int(p[int(p.max(1).argmax())].argmax())]


def one(jpeg: bytes, det: Det, cls: Cls, frac: float) -> dict:
    t = time.perf_counter()
    rgb = np.asarray(Image.open(io.BytesIO(jpeg)).convert("RGB"))
    t_decode = time.perf_counter() - t
    t = time.perf_counter()
    split = int(rgb.shape[1] * frac)
    fr = st.frame(rgb, det, hand_frac=frac)
    faces = rv.dedupe(rv.keep_faces(det.detect(rgb), rv.white_mask(rgb)))
    if fr is None and faces:
        b = split2(rgb, faces, split, O)
        fr = b if b is not None and ok2(b, rgb, O) else None
    t_frame = time.perf_counter() - t
    t = time.perf_counter()
    hand, melds, block = [], [], False
    if fr is not None:
        hand = cls.read([cut(rgb, b) for b in fr.hand] + ([cut(rgb, fr.separate)] if fr.separate else []))
        melds = [" ".join(read_meld_tile(cls, rgb, b) for b in m) for m in fr.melds]
        if fr.count == 13 and not fr.separate:
            got = strays(fr, faces, rgb)
            if len(got) == 1:
                hand = hand + [read_turned(cls, rgb, got[0], fr.tw, fr.th)]
            elif got:
                block = True
    t_read = time.perf_counter() - t
    return dict(framed=fr is not None, hand=hand, melds=melds, block=block, decode_ms=round(t_decode * 1000), frame_ms=round(t_frame * 1000), read_ms=round(t_read * 1000))


def rss_mb() -> float:
    try:
        import resource
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
    except ImportError:
        import psutil
        return round(psutil.Process(os.getpid()).memory_info().peak_wset / 2**20)


def q(a: list) -> str:
    a = sorted(a)
    return f"{a[len(a) // 2] / 1000:.2f} / {a[min(len(a) - 1, int(.9 * len(a)))] / 1000:.2f} / {a[-1] / 1000:.2f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--one", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    meta = json.loads((HERE / "meta.json").read_text(encoding="utf-8"))
    t0 = time.perf_counter()
    dets, clss = {}, {}
    if a.one:
        d, c = Det(HERE / "models" / "det_final.onnx", a.threads), Cls(HERE / "models" / "cls_pm.onnx", meta, a.threads)
    print("모델 올림", round(time.perf_counter() - t0, 2), "초, 메모리", rss_mb(), "MB", flush=True)
    rows = []
    for rep in range(a.repeat):
        for p in meta["photos"]:
            if a.one:
                det, cls = d, c
            else:
                det = dets.setdefault(p["det"], Det(HERE / "models" / f"det_fold_{p['det']}.onnx", a.threads)) if p["det"] not in dets else dets[p["det"]]
                cls = clss.setdefault(p["part"], Cls(HERE / "models" / f"cls_{p['part']}.onnx", meta, a.threads)) if p["part"] not in clss else clss[p["part"]]
            jpeg = (HERE / "crops" / f"{p['name']}.jpg").read_bytes()
            det.memo = {}
            r = one(jpeg, det, cls, p["frac"])
            r |= dict(name=p["name"], rep=rep, total_ms=r["decode_ms"] + r["frame_ms"] + r["read_ms"])
            rows.append(r)
            print("RESULT", json.dumps(r, ensure_ascii=False), flush=True)
    late = [r for r in rows if r["rep"] > 0] or rows
    print("--- 사진", len(meta["photos"]), "× 회", a.repeat, "스레드", a.threads, "(첫 회 뺀 값)")
    for k in ("decode_ms", "frame_ms", "read_ms", "total_ms"):
        print(k, q([r[k] for r in late]))
    print("틀 잡은 사진만 전체", q([r["total_ms"] for r in late if r["framed"]]), "틀 못 잡은 사진", q([r["total_ms"] for r in late if not r["framed"]]) if any(not r["framed"] for r in late) else "—")
    print("최대 메모리", rss_mb(), "MB")


if __name__ == "__main__":
    main()
