"""손 관절(MediaPipe Hands 모델)을 내장 GPU(OpenVINO)로 — 집기 · 놓기 · 밀기를 손 동작으로 읽어 보기(2026-11-20).

사용자 "이 모델로 무슨 행동했는지 유추안되나" → "내장 gpu로 테스트해봐". MediaPipe Python 은 Windows 에서 GPU 를 못 써서
모델 파일(hand_landmarker.task 안의 tflite 둘)을 OpenVINO 로 읽어 Intel Arc iGPU 에서 돌리고, 앞뒤 처리는 MediaPipe 그래프 상수를 옮겨 직접 함.
같은 프레임을 MediaPipe CPU(Tasks API)로도 돌려 맞는지 대조한다.

  venvs/hands/Scripts/python.exe -X utf8 handpose.py ov r16_d13 [--dev GPU]   # → _work/hands_1120/<id>/ov.json
  venvs/hands/Scripts/python.exe -X utf8 handpose.py mp r16_d13               # → mp.json (MediaPipe CPU, 대조)
  venvs/hands/Scripts/python.exe -X utf8 handpose.py cmp r16_d13              # 두 결과의 관절점 차이
환경: venvs/hands(mediapipe 1.2.3 · openvino 2026.4), 모델 venvs/hands_models. 프레임은 handdump.py 가 만든 것.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

WORK = Path(r"C:\Users\jjh7757\dev\mahjong_calc\experiments\paifu_frames\results\handtrack\_work\hands_1120")
MODELS = Path(r"C:\Users\jjh7757\dev\venvs\hands_models")
DET_SIZE, LM_SIZE = 192, 224
MIN_SCORE, NMS_IOU = float(__import__("os").environ.get("HAND_MIN_SCORE", "0.5")), 0.3   # 손 찾기 기준(11-20: r17 시험에 0.3)
PRESENCE = 0.5


def anchors() -> np.ndarray:
    """SsdAnchorsCalculator(palm): 층 4 · 보폭 8,16,16,16 · 고정 크기 → (2016, 2) 중심."""
    out = []
    strides = [8, 16, 16, 16]
    i = 0
    while i < len(strides):
        s = strides[i]
        same = 0
        while i < len(strides) and strides[i] == s:
            same += 1
            i += 1
        fm = math.ceil(DET_SIZE / s)
        for y in range(fm):
            for x in range(fm):
                for _ in range(2 * same):     # 층마다 aspect 1.0 + 보간 크기 = 2개
                    out.append(((x + 0.5) / fm, (y + 0.5) / fm))
    a = np.array(out, np.float32)
    assert len(a) == 2016, len(a)
    return a


ANCH = anchors()


def letterbox(img: np.ndarray):
    h, w = img.shape[:2]
    s = DET_SIZE / max(h, w)
    nw, nh = round(w * s), round(h * s)
    im = np.asarray(Image.fromarray(img).resize((nw, nh), Image.BILINEAR), np.float32) / 255.0
    pad = np.zeros((DET_SIZE, DET_SIZE, 3), np.float32)
    ox, oy = (DET_SIZE - nw) // 2, (DET_SIZE - nh) // 2
    pad[oy:oy + nh, ox:ox + nw] = im
    return pad, (ox / DET_SIZE, oy / DET_SIZE, nw / DET_SIZE, nh / DET_SIZE)


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -100, 100)))


def decode(raw: np.ndarray, sc: np.ndarray, lb) -> list:
    """TensorsToDetections + 가중 NMS + 레터박스 벗기기 → [(score, cx, cy, w, h, kps(7,2))] 원본 정규 좌표."""
    score = sigmoid(sc[:, 0])
    keep = np.nonzero(score >= MIN_SCORE)[0]
    dets = []
    for k in keep:
        r = raw[k]
        ax, ay = ANCH[k]
        cx, cy = r[0] / DET_SIZE + ax, r[1] / DET_SIZE + ay
        w, h = r[2] / DET_SIZE, r[3] / DET_SIZE
        kp = np.array([[r[4 + 2 * j] / DET_SIZE + ax, r[5 + 2 * j] / DET_SIZE + ay] for j in range(7)], np.float32)
        dets.append([score[k], cx, cy, w, h, kp])
    dets.sort(key=lambda d: -d[0])
    out = []
    used = [False] * len(dets)
    for i, d in enumerate(dets):           # 가중 NMS(겹친 것들의 점수 가중 평균)
        if used[i]:
            continue
        grp = [j for j in range(i, len(dets)) if not used[j] and iou(d, dets[j]) > NMS_IOU]
        for j in grp:
            used[j] = True
        ws = np.array([dets[j][0] for j in grp])
        cx = sum(dets[j][1] * w for j, w in zip(grp, ws)) / ws.sum()
        cy = sum(dets[j][2] * w for j, w in zip(grp, ws)) / ws.sum()
        bw = sum(dets[j][3] * w for j, w in zip(grp, ws)) / ws.sum()
        bh = sum(dets[j][4] * w for j, w in zip(grp, ws)) / ws.sum()
        kp = sum(dets[j][5] * w for j, w in zip(grp, ws)) / ws.sum()
        out.append([d[0], cx, cy, bw, bh, kp])
    ox, oy, sx, sy = lb
    res = []
    for s, cx, cy, bw, bh, kp in out:
        res.append((float(s), (cx - ox) / sx, (cy - oy) / sy, bw / sx, bh / sy, (kp - [ox, oy]) / [sx, sy]))
    return res


def iou(a, b):
    ax0, ay0, ax1, ay1 = a[1] - a[3] / 2, a[2] - a[4] / 2, a[1] + a[3] / 2, a[2] + a[4] / 2
    bx0, by0, bx1, by1 = b[1] - b[3] / 2, b[2] - b[4] / 2, b[1] + b[3] / 2, b[2] + b[4] / 2
    iw, ih = max(0, min(ax1, bx1) - max(ax0, bx0)), max(0, min(ay1, by1) - max(ay0, by0))
    inter = iw * ih
    return inter / max(1e-9, a[3] * a[4] + b[3] * b[4] - inter)


def roi_of(det, W: int, H: int):
    """DetectionsToRects(손목 0 → 가운뎃손가락 2 가 위로 오게) + RectTransformation(2.6배 · 위로 0.5 · 정사각) → 픽셀 (cx, cy, size, rot)."""
    _, cx, cy, bw, bh, kp = det
    x0, y0 = kp[0][0] * W, kp[0][1] * H
    x1, y1 = kp[2][0] * W, kp[2][1] * H
    rot = math.pi / 2 - math.atan2(-(y1 - y0), x1 - x0)
    rot = (rot + math.pi) % (2 * math.pi) - math.pi
    w, h = bw * W, bh * H
    sx, sy = 0.0, -0.5
    cxp = cx * W + (w * sx * math.cos(rot) - h * sy * math.sin(rot))
    cyp = cy * H + (w * sx * math.sin(rot) + h * sy * math.cos(rot))
    size = max(w, h) * 2.6
    return cxp, cyp, size, rot


def crop(img: np.ndarray, cx, cy, size, rot):
    """돌린 정사각 ROI 를 224² 로(바깥은 0). 반환: 입력 텐서와 224 좌표 → 원본 픽셀 변환."""
    c, s = math.cos(rot), math.sin(rot)
    # 출력 (u, v) ∈ [0, 224) → 원본: p = center + R · ((u/224 - 0.5)·size, (v/224 - 0.5)·size)
    a = size / LM_SIZE
    # PIL AFFINE 은 출력 → 입력 계수 (a, b, c, d, e, f): x = a·u + b·v + c, y = d·u + e·v + f
    coef = (a * c, -a * s, cx - 0.5 * size * c + 0.5 * size * s,
            a * s, a * c, cy - 0.5 * size * s - 0.5 * size * c)
    im = Image.fromarray(img).transform((LM_SIZE, LM_SIZE), Image.AFFINE, coef, resample=Image.BILINEAR, fillcolor=(0, 0, 0))
    x = np.asarray(im, np.float32) / 255.0

    def back(uv):
        u, v = uv[..., 0], uv[..., 1]
        return np.stack([coef[0] * u + coef[1] * v + coef[2], coef[3] * u + coef[4] * v + coef[5]], -1)
    return x, back


def roi_from_landmarks(pts: np.ndarray):
    """MediaPipe 추적(HandLandmarksToRect): 손목 0 → 가운뎃손가락 뿌리 9 가 위로 · 관절 둘레 상자 · 2배 · 위로 0.1 → (cx, cy, size, rot)."""
    x0, y0 = pts[0]
    x1, y1 = pts[9]
    rot = math.pi / 2 - math.atan2(-(y1 - y0), x1 - x0)
    rot = (rot + math.pi) % (2 * math.pi) - math.pi
    c, s = math.cos(-rot), math.sin(-rot)
    sel = pts[[0, 1, 2, 3, 5, 6, 9, 10, 13, 14, 17, 18]]
    ctr = sel.mean(0)
    rel = sel - ctr
    rx = rel[:, 0] * c - rel[:, 1] * s
    ry = rel[:, 0] * s + rel[:, 1] * c
    w, h = rx.max() - rx.min(), ry.max() - ry.min()
    mx, my = (rx.max() + rx.min()) / 2, (ry.max() + ry.min()) / 2
    c2, s2 = math.cos(rot), math.sin(rot)
    cx = ctr[0] + mx * c2 - my * s2
    cy = ctr[1] + mx * s2 + my * c2
    sy = -0.1
    cx += -h * sy * math.sin(rot)
    cy += h * sy * math.cos(rot)
    return cx, cy, max(w, h) * 2.0, rot


def pinch(lm: np.ndarray) -> float:
    """엄지 끝(4) 과 검지 끝(8) · 가운뎃손가락 끝(12) 중 가까운 쪽 거리 / 손 크기(손목 0 ~ 가운뎃손가락 뿌리 9)."""
    size = np.linalg.norm(lm[0] - lm[9]) + 1e-6
    return float(min(np.linalg.norm(lm[4] - lm[8]), np.linalg.norm(lm[4] - lm[12])) / size)


def run_ov(tid: str, dev: str = "GPU", tag: str = ""):
    """tag = "_w220" 이면 handdump --margin 220 의 넓힌 그림을 읽고, 저장하는 관절점은 원래 band2 그림 좌표로 옮김(+ dx, dy)."""
    import openvino as ov
    core = ov.Core()
    det_m = core.compile_model(core.read_model(str(MODELS / "hand_detector.tflite")), dev)
    lm_m = core.compile_model(core.read_model(str(MODELS / "hand_landmarks_detector.tflite")), dev)
    dreq, lreq = det_m.create_infer_request(), lm_m.create_infer_request()
    meta = json.loads((WORK / tid / f"frames{tag}.json").read_text(encoding="utf-8"))
    fdir = WORK / tid / meta.get("dir", "frames")
    dx, dy = meta.get("dx", 0), meta.get("dy", 0)
    out = []
    t0 = time.perf_counter()
    t_inf = 0.0
    prev = []   # 앞 프레임 손들의 관절점 — MediaPipe VIDEO 모드처럼 다음 ROI 로(추적)
    for r in meta["frames"]:
        img = np.asarray(Image.open(fdir / f"{r['i']:05d}.jpg").convert("RGB"))
        H, W = img.shape[:2]
        x, lb = letterbox(img)
        a = time.perf_counter()
        dreq.infer({0: x[None]})
        t_inf += time.perf_counter() - a
        raw = dreq.get_output_tensor(0).data[0]
        sc = dreq.get_output_tensor(1).data[0]
        rois = [("track", roi_from_landmarks(p)) for p in prev]
        for det in decode(raw, sc, lb)[:4]:   # 추적 중인 손과 겹치는 새 검출은 버림(같은 손)
            roi = roi_of(det, W, H)
            if all(math.hypot(roi[0] - t[0], roi[1] - t[1]) > 0.5 * max(roi[2], t[2]) for _, t in rois):
                rois.append(("det", roi))
        hands = []
        for src, (cx, cy, size, rot) in rois[:4]:
            det = [1.0] if src == "track" else [0.0]
            xin, back = crop(img, cx, cy, size, rot)
            a = time.perf_counter()
            lreq.infer({0: xin[None]})
            t_inf += time.perf_counter() - a
            lmk = lreq.get_output_tensor(0).data[0].reshape(21, 3)
            pres = float(lreq.get_output_tensor(1).data[0][0])
            pres = pres if 0 <= pres <= 1 else float(sigmoid(pres))
            hd = float(lreq.get_output_tensor(2).data[0][0])
            hd = hd if 0 <= hd <= 1 else float(sigmoid(hd))
            if pres < PRESENCE:
                continue
            pts = back(lmk[:, :2])
            hands.append({"src": src, "presence": round(pres, 3), "right": round(hd, 3),
                          "lm": [[round(float(p[0]), 1), round(float(p[1]), 1)] for p in pts], "pinch": round(pinch(pts), 3)})
        # 같은 손이 둘(추적 + 검출)로 잡히면 하나만
        uniq = []
        for h in hands:
            p = np.array(h["lm"])
            if all(np.linalg.norm(np.array(u["lm"]) - p, axis=1).mean() > 0.3 * (np.linalg.norm(p[0] - p[9]) + 1e-6) for u in uniq):
                uniq.append(h)
        hands = uniq
        prev = [np.array(h["lm"], np.float32) for h in hands]
        if dx or dy:   # 저장은 원래 band2 그림 좌표로(추적은 넓힌 그림 좌표 그대로)
            hands = [{**h, "lm": [[round(p[0] + dx, 1), round(p[1] + dy, 1)] for p in h["lm"]]} for h in hands]
        out.append({"i": r["i"], "t": r["t"], "hands": hands})
    sec = time.perf_counter() - t0
    (WORK / tid / f"ov_{dev}{tag}.json").write_text(json.dumps({"id": tid, "dev": dev, "tag": tag, "dx": dx, "dy": dy, "sec": round(sec, 1),
                                                                "infer_sec": round(t_inf, 2), "frames": out}), encoding="utf-8")
    nh = sum(bool(f["hands"]) for f in out)
    print(f"{tid} {dev}: {len(out)}장 · 손 잡힌 프레임 {nh} · 전체 {sec:.1f}초(추론만 {t_inf:.2f}초, 장당 {1000 * sec / len(out):.1f}ms)")


def run_mp(tid: str):
    import mediapipe as mp
    from mediapipe.tasks import python as mpt
    from mediapipe.tasks.python import vision
    opts = vision.HandLandmarkerOptions(base_options=mpt.BaseOptions(model_asset_path=str(MODELS / "hand_landmarker.task")),
                                        running_mode=vision.RunningMode.VIDEO, num_hands=4,
                                        min_hand_detection_confidence=MIN_SCORE, min_hand_presence_confidence=PRESENCE, min_tracking_confidence=0.5)
    lmk = vision.HandLandmarker.create_from_options(opts)
    meta = json.loads((WORK / tid / "frames.json").read_text(encoding="utf-8"))
    out = []
    t0 = time.perf_counter()
    for r in meta["frames"]:
        img = np.asarray(Image.open(WORK / tid / "frames" / f"{r['i']:05d}.jpg").convert("RGB"))
        H, W = img.shape[:2]
        res = lmk.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(img)), int(r["i"] * 100))
        hands = []
        for k, h in enumerate(res.hand_landmarks):
            pts = np.array([[p.x * W, p.y * H] for p in h], np.float32)
            side = res.handedness[k][0].category_name if res.handedness else "?"
            hands.append({"side": side, "lm": [[round(float(p[0]), 1), round(float(p[1]), 1)] for p in pts], "pinch": round(pinch(pts), 3)})
        out.append({"i": r["i"], "t": r["t"], "hands": hands})
    sec = time.perf_counter() - t0
    (WORK / tid / "mp.json").write_text(json.dumps({"id": tid, "dev": "mediapipe-cpu", "sec": round(sec, 1), "frames": out}), encoding="utf-8")
    print(f"{tid} MediaPipe CPU: {len(out)}장 · 손 잡힌 프레임 {sum(bool(f['hands']) for f in out)} · {sec:.1f}초(장당 {1000 * sec / len(out):.1f}ms)")


def cmp(tid: str, dev: str = "GPU"):
    a = json.loads((WORK / tid / f"ov_{dev}.json").read_text(encoding="utf-8"))["frames"]
    b = json.loads((WORK / tid / "mp.json").read_text(encoding="utf-8"))["frames"]
    both = only_a = only_b = 0
    errs = []
    for fa, fb in zip(a, b):
        if fa["hands"] and fb["hands"]:
            both += 1
            for hb in fb["hands"]:   # mp 손마다 가장 가까운 ov 손의 관절 평균 거리(손 크기로 나눔)
                pb = np.array(hb["lm"])
                size = np.linalg.norm(pb[0] - pb[9]) + 1e-6
                d = min(np.linalg.norm(np.array(ha["lm"]) - pb, axis=1).mean() / size for ha in fa["hands"])
                errs.append(d)
        elif fa["hands"]:
            only_a += 1
        elif fb["hands"]:
            only_b += 1
    e = np.array(errs) if errs else np.array([np.nan])
    print(f"{tid}: 둘 다 손 {both} · OpenVINO 만 {only_a} · MediaPipe 만 {only_b} · 관절 평균 차(손 크기 대비) 중앙 {np.nanmedian(e):.3f} · p90 {np.nanpercentile(e, 90):.3f}")


if __name__ == "__main__":
    mode, tid = sys.argv[1], sys.argv[2]
    dev = sys.argv[sys.argv.index("--dev") + 1] if "--dev" in sys.argv else "GPU"
    tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else ""
    {"ov": lambda: run_ov(tid, dev, tag), "mp": lambda: run_mp(tid), "cmp": lambda: cmp(tid, dev)}[mode]()
