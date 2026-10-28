"""YOLO26(HaseLab) 를 서버 환경(onnxruntime 만, torch·ultralytics 없음)에서 돌려 시간을 잰다(2026-10-26).

재는 것:
  grid    격자 자동 설정(auto_grid.py 와 같은 규칙): 사진 디코드 + 구역 모델 5번(그대로 1 + 자리마다 90° 회전 4)
  verify  검증기·단독 판독용: 자리 크롭에 패 모델 1번 + 잡힌 패 수만큼 ResNet-50 분류(배치 한 번)
결과는 한 줄 JSON(RESULT {...}) 과 요약. PC 에서 먼저 돌려 auto_grid.json 의 격자와 같은지 확인한다.

python bench.py [--repeat 3] [--threads 0] [--check auto_grid.json] [--parts grid,verify] [--cls-batch 2]
(서버 700MB 상한에서 ResNet-50 을 14장 한 번에 돌리면 OOM — 분류는 --cls-batch 장씩)
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

HERE = Path(__file__).resolve().parent
MODELS = HERE / "models"
PHOTOS = HERE / "photos"
CROPS = HERE / "crops"
SCENES = {"B": ["k25", "k28"], "C": ["k15", "k26"], "D": ["k12", "k16"]}
NAMES = ["self_hand", "discard_0", "discard_1", "discard_2", "discard_3", "meld_0", "meld_1", "meld_2", "meld_3",
         "dora", "riichi_0", "riichi_1", "riichi_2", "riichi_3"]
# 직사각형 입력(ultralytics 의 PyTorch 추론과 같게: 긴 변만 맞추고 짧은 변은 32 배수로 채움). 정사각형 고정 입력은 가는
# 손패 구역 크롭이 큰 회색 여백 속에 작게 들어가 패를 거의 못 찾았다(1~2장). 동적 입력 ONNX(*-dyn.onnx)가 필요.
RECT = False
MODEL_FILES = {"region": "regions-yolo-26n-1280.onnx", "tile": "tile-yolo-26n-1024.onnx", "cls": "classifier-resnet50.onnx"}
ROT = {"bottom": None, "right": cv2.ROTATE_90_CLOCKWISE, "top": cv2.ROTATE_180, "left": cv2.ROTATE_90_COUNTERCLOCKWISE}


def session(path: Path, threads: int):
    so = ort.SessionOptions()
    so.enable_cpu_mem_arena = False  # 메모리 2GB 서버: 미리 크게 잡아 두지 않게
    if threads:
        so.intra_op_num_threads = threads
    return ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])


def letterbox(img: np.ndarray, size: int):
    h, w = img.shape[:2]
    r = min(size / h, size / w)
    nh, nw = round(h * r), round(w * r)
    im = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    H, W = (-(-nh // 32) * 32, -(-nw // 32) * 32) if RECT else (size, size)
    top, left = (H - nh) // 2, (W - nw) // 2
    canvas = np.full((H, W, 3), 114, np.uint8)
    canvas[top:top + nh, left:left + nw] = im
    x = canvas[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255
    return np.ascontiguousarray(x), r, left, top


def nms(boxes: np.ndarray, scores: np.ndarray, iou: float) -> list[int]:
    order = scores.argsort()[::-1]
    keep = []
    while order.size:
        i = order[0]
        keep.append(int(i))
        if order.size == 1:
            break
        xx1 = np.maximum(boxes[i, 0], boxes[order[1:], 0]); yy1 = np.maximum(boxes[i, 1], boxes[order[1:], 1])
        xx2 = np.minimum(boxes[i, 2], boxes[order[1:], 2]); yy2 = np.minimum(boxes[i, 3], boxes[order[1:], 3])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        a = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
        b = (boxes[order[1:], 2] - boxes[order[1:], 0]) * (boxes[order[1:], 3] - boxes[order[1:], 1])
        order = order[1:][inter / (a + b - inter + 1e-9) <= iou]
    return keep


def detect(sess, img: np.ndarray, size: int, n_cls: int, conf=0.25, iou=0.7):
    """→ [(cls, conf, xyxy 원본 좌표)]. 상자만(마스크 계수는 버림), 클래스별 NMS(ultralytics 기본과 같게)."""
    x, r, left, top = letterbox(img, size)
    out = sess.run(None, {sess.get_inputs()[0].name: x})[0][0].T  # (N, 4 + n_cls + 32)
    sc = out[:, 4:4 + n_cls]
    cls = sc.argmax(1); cf = sc.max(1)
    m = cf > conf
    if not m.any():
        return []
    b = out[m, :4]; cls = cls[m]; cf = cf[m]
    xyxy = np.stack([b[:, 0] - b[:, 2] / 2, b[:, 1] - b[:, 3] / 2, b[:, 0] + b[:, 2] / 2, b[:, 1] + b[:, 3] / 2], 1)
    res = []
    for c in np.unique(cls):
        idx = np.nonzero(cls == c)[0]
        for k in nms(xyxy[idx], cf[idx], iou):
            j = idx[k]
            bb = (xyxy[j] - [left, top, left, top]) / r
            res.append((int(c), float(cf[j]), bb))
    return res


# ---------------------------------------------------------------- auto_grid.py 와 같은 규칙
def unrotate_box(b, seat, W, H):
    x0, y0, x1, y1 = b
    if seat == "bottom":
        return np.array([x0, y0, x1, y1])
    if seat == "top":
        return np.array([W - x1, H - y1, W - x0, H - y0])
    if seat == "right":
        return np.array([y0, H - x1, y1, H - x0])
    return np.array([W - y1, x0, W - y0, x1])


def union(boxes):
    boxes = [b for b in boxes if b is not None]
    if not boxes:
        return None
    a = np.array(boxes)
    return np.array([a[:, 0].min(), a[:, 1].min(), a[:, 2].max(), a[:, 3].max()])


def inter_frac(b, zone):
    ix = max(0.0, min(b[2], zone[2]) - max(b[0], zone[0])); iy = max(0.0, min(b[3], zone[3]) - max(b[1], zone[1]))
    return float(ix * iy / max(1e-9, (b[2] - b[0]) * (b[3] - b[1])))


def boxes_of(dets):
    out = {}
    for c, p, b in dets:
        out.setdefault(NAMES[c], []).append((p, b))
    return out


def auto_grid(sess, img, timings):
    H, W = img.shape[:2]
    t = time.perf_counter(); b0 = boxes_of(detect(sess, img, 1280, 14)); timings.append(time.perf_counter() - t)
    center = union([b for n, lst in b0.items() if n.startswith(("discard_", "riichi_")) for p, b in lst if p > 0.3])
    seats = {}
    for seat, rot in ROT.items():
        t = time.perf_counter()
        im = img if rot is None else cv2.rotate(img, rot)
        bx = boxes_of(detect(sess, im, 1280, 14))
        timings.append(time.perf_counter() - t)
        hand = max(bx.get("self_hand", []), key=lambda q: q[0], default=None)
        if hand is None:
            continue
        disc = max(bx.get("discard_0", []), key=lambda q: q[0], default=None)
        lim = disc[1][3] if disc else im.shape[0] * 0.6
        hb = hand[1]; hh = hb[3] - hb[1]
        melds, loose = [], []
        for p, b in bx.get("meld_0", []):
            if p <= 0.3 or (b[1] + b[3]) / 2 <= lim:
                continue
            (melds if b[3] >= hb[1] - 0.5 * hh else loose).append(b)
        seats[seat] = dict(box=unrotate_box(union([hb] + melds), seat, W, H), loose=[unrotate_box(b, seat, W, H) for b in loose])
    extra = [b for p, b in b0.get("dora", []) if p > 0.3] + [b for d in seats.values() for b in d["loose"]]
    for b in extra:
        if center is not None and all(inter_frac(b, d["box"]) < 0.05 for d in seats.values()):
            center = union([center, b])
    if center is None:
        return None
    m = 0.03
    g = {"y2": (center[3] + seats["bottom"]["box"][1]) / 2 if "bottom" in seats else center[3] + m * H,
         "y1": (center[1] + seats["top"]["box"][3]) / 2 if "top" in seats else center[1] - m * H,
         "x1": (center[0] + seats["left"]["box"][2]) / 2 if "left" in seats else center[0] - m * W,
         "x2": (center[2] + seats["right"]["box"][0]) / 2 if "right" in seats else center[2] + m * W}
    e = 0.005
    if "bottom" in seats:
        g["y2"] = min(g["y2"], seats["bottom"]["box"][1] - e * H)
    if "top" in seats:
        g["y1"] = max(g["y1"], seats["top"]["box"][3] + e * H)
    if "left" in seats:
        g["x1"] = max(g["x1"], seats["left"]["box"][2] + e * W)
    if "right" in seats:
        g["x2"] = min(g["x2"], seats["right"]["box"][0] - e * W)
    return {k: int(round(v / (W if k[0] == "x" else H) * 1000)) for k, v in g.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--check", default="")
    ap.add_argument("--parts", default="grid,verify")
    ap.add_argument("--cls-batch", type=int, default=2)
    ap.add_argument("--rect", action="store_true", help="직사각형 입력(동적 ONNX)")
    ap.add_argument("--models", default="", help="region=파일,tile=파일,cls=파일 (models/ 안)")
    a = ap.parse_args()
    global RECT
    RECT = a.rect
    files = dict(MODEL_FILES, **dict(kv.split("=") for kv in a.models.split(",") if kv))
    t = time.perf_counter()
    do_grid, do_verify = "grid" in a.parts, "verify" in a.parts
    region = session(MODELS / files["region"], a.threads) if do_grid else None
    tile = session(MODELS / files["tile"], a.threads) if do_verify else None
    cls = session(MODELS / files["cls"], a.threads) if do_verify else None
    load_s = time.perf_counter() - t
    info = dict(machine=platform.machine(), cpus=os.cpu_count(), ort=ort.__version__, threads=a.threads, load_s=round(load_s, 2),
                rect=a.rect, models=files)
    print("INFO " + json.dumps(info), flush=True)
    check = json.loads(Path(a.check).read_text(encoding="utf-8")) if a.check else {}

    # 준비 운동(첫 실행은 메모리 할당이 섞인다)
    dummy = np.zeros((3000, 4000, 3), np.uint8)
    if do_grid:
        detect(region, dummy, 1280, 14)
    if do_verify:
        detect(tile, dummy[:900, :2900], 1024, 1)
        cls.run(None, {"x": np.zeros((a.cls_batch, 3, 224, 224), np.float32)})

    rows = []
    for r in range(a.repeat):
        for s, ps in SCENES.items():
            for p in ps:
                t0 = time.perf_counter()
                img = cv2.imdecode(np.fromfile(str(PHOTOS / f"{p}.jpg"), np.uint8), cv2.IMREAD_COLOR)
                dec = time.perf_counter() - t0
                tim = []
                t1 = time.perf_counter()
                grid = auto_grid(region, img, tim) if do_grid else None
                gs = time.perf_counter() - t1
                if not do_verify:
                    ok = (check.get(f"{s}/{p}", {}).get("grid") == grid) if check else None
                    row = dict(run=r, scene=s, photo=p, decode_s=round(dec, 3), grid_s=round(gs, 3),
                               region_each_s=[round(v, 3) for v in tim], tile_s=0, n_tiles=0, classify_s=0, grid=grid, grid_matches_pc=ok)
                    rows.append(row)
                    print("RESULT " + json.dumps(row), flush=True)
                    continue
                # 검증기: 자리 크롭 하나 → 패 모델 → 잡힌 패마다 224 크롭 → ResNet-50 배치
                crop = cv2.imdecode(np.fromfile(str(CROPS / f"{s}_{p}.jpg"), np.uint8), cv2.IMREAD_COLOR)
                t2 = time.perf_counter()
                tiles = detect(tile, crop, 1024, 1)
                td = time.perf_counter() - t2
                # 분류는 손패 한 벌(14장) 기준으로 잰다: 자리 크롭을 패 모델에 바로 넣으면 1~2장만 잡혀(README 1절) 실제보다 짧게 나온다.
                # 잡힌 패 + 크롭을 14칸으로 나눈 조각으로 14장을 채운다.
                t3 = time.perf_counter()
                patches = []
                for _, _, b in tiles[:14]:
                    x0, y0, x1, y1 = [int(v) for v in b]
                    patches.append(crop[max(0, y0):max(y0 + 1, y1), max(0, x0):max(x0 + 1, x1)])
                w14 = crop.shape[1] // 14
                patches += [crop[:, i * w14:(i + 1) * w14] for i in range(14 - len(patches))]
                x = np.stack([cv2.resize(pc, (224, 224))[:, :, ::-1].astype(np.float32) / 255 for pc in patches])
                x = ((x - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]).transpose(0, 3, 1, 2).astype(np.float32)
                for i in range(0, len(x), a.cls_batch):
                    cls.run(None, {"x": x[i:i + a.cls_batch]})
                tc = time.perf_counter() - t3
                ok = (check.get(f"{s}/{p}", {}).get("grid") == grid) if check and do_grid else None
                row = dict(run=r, scene=s, photo=p, decode_s=round(dec, 3), grid_s=round(gs, 3),
                           region_each_s=[round(v, 3) for v in tim], tile_s=round(td, 3), n_tiles=len(tiles),
                           classify_s=round(tc, 3), grid=grid, grid_matches_pc=ok)
                rows.append(row)
                print("RESULT " + json.dumps(row), flush=True)

    med = lambda k: statistics.median(r[k] for r in rows)  # noqa: E731
    each = [v for r in rows for v in r["region_each_s"]] or [0]
    print("SUMMARY " + json.dumps(dict(
        info, n=len(rows),
        decode_med=round(med("decode_s"), 3),
        region_one_med=round(statistics.median(each), 3),
        grid_med=round(med("grid_s"), 3), grid_max=round(max(r["grid_s"] for r in rows), 3),
        tile_med=round(med("tile_s"), 3), classify_med=round(med("classify_s"), 3),
        verify_med=round(statistics.median(r["tile_s"] + r["classify_s"] for r in rows), 3),
        grid_matches_pc=None if not check else sum(bool(r["grid_matches_pc"]) for r in rows),
        peak_mem_mb=peak_mem())), flush=True)


def peak_mem():
    """컨테이너(cgroup v2) 최대 메모리 MB. 없으면 None."""
    f = Path("/sys/fs/cgroup/memory.peak")
    return round(int(f.read_text()) / 2**20) if f.exists() else None


if __name__ == "__main__":
    main()
