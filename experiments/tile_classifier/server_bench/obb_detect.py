"""7회차 회전 상자(OBB) ONNX 를 서버 자리 판독 벤치에 끼우는 어댑터(2026-11-04, 노트북, API 없음).

OBB ONNX 출력은 1×(4+종류+1)×N = cx, cy, w, h, 앞면 점수, 뒷면 점수, 각도(라디안, 시계 방향 +).
서버 코드는 축 상자를 가정하므로 회전 상자를 감싸는 축 상자로 바꿔 넘긴다(A). rot_white=True 면 흰 비율 거르기
(river.keep_faces)를 축 상자 대신 회전 상자 안에서 잰다(B) — 기운 패(181209 9s)가 귀퉁이 펠트 때문에 버려지던 것을 고치는지.
  install(bench, lr, rv, rot_white)   — server_bench/bench.Det._detect, app.local_read.LocalReader.detect, app.river.keep_faces 를 바꾼다
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

IMG, CONF, IOU = 1280, 0.25, 0.7
RECTS: dict = {}  # 마지막 검출의 {축 상자: 회전 상자 ((cx, cy), (w, h), 각도°)} — keep_faces 가 바로 다음에 쓴다
ALL: dict = {}  # {(그림 지문, 축 상자): 회전 상자} — 크롭은 그림을 받으니 지문으로 찾는다(벤치 Det 은 같은 그림 검출을 memo 로 건너뛰어 RECTS 가 다른 그림 것일 수 있다)


FP_NEXT: list = []  # 검출에 넣는 그림이 원본과 다를 때(felt_only) 원본 지문 — run() 이 하나 꺼내 쓴다


def fingerprint(rgb: np.ndarray) -> tuple:
    return rgb.shape, hash(np.ascontiguousarray(rgb[::53, ::47]).tobytes())


def letterbox(rgb: np.ndarray) -> tuple[np.ndarray, float, int, int]:
    H, W = rgb.shape[:2]
    r = min(IMG / H, IMG / W)
    nw, nh = round(W * r), round(H * r)
    cw, ch = -(-nw // 32) * 32, -(-nh // 32) * 32
    left, top = round((cw - nw) / 2 - 0.1), round((ch - nh) / 2 - 0.1)
    canvas = np.full((ch, cw, 3), 114, np.uint8)
    canvas[top:top + nh, left:left + nw] = np.asarray(Image.fromarray(rgb).resize((nw, nh), Image.BILINEAR))
    return canvas.transpose(2, 0, 1)[None].astype(np.float32) / 255, r, left, top


def decode(out: np.ndarray, r: float, left: int, top: int, W: int, H: int, cls: int = 0) -> list[tuple]:
    """[(축 상자 x, y, w, h), 회전 상자] — 종류 cls(0 앞면, 1 뒷면)의 점수로, 감싸는 축 상자로 NMS."""
    keep = out[4 + cls] >= CONF
    cx, cy, w, h, c, ang = ((out[0] - left) / r)[keep], ((out[1] - top) / r)[keep], (out[2] / r)[keep], (out[3] / r)[keep], out[4 + cls][keep], out[-1][keep]
    rects, boxes = [], []
    for i in range(len(c)):
        rect = ((float(cx[i]), float(cy[i])), (float(w[i]), float(h[i])), float(np.degrees(ang[i])))
        p = cv2.boxPoints(rect)
        x0, y0 = max(0.0, float(p[:, 0].min())), max(0.0, float(p[:, 1].min()))
        x1, y1 = min(float(W), float(p[:, 0].max())), min(float(H), float(p[:, 1].max()))
        rects.append(rect)
        boxes.append((x0, y0, x1, y1))
    order, out_ = list(np.argsort(-c)), []
    while order:
        i = order.pop(0)
        out_.append(i)
        rest = []
        for j in order:
            a, b = boxes[i], boxes[j]
            ix, iy = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
            inter = max(0.0, ix) * max(0.0, iy)
            if inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter + 1e-9) <= IOU:
                rest.append(j)
        order = rest
    res = []
    for i in out_:
        x0, y0, x1, y1 = boxes[i]
        if x1 - x0 >= 2 and y1 - y0 >= 2:
            res.append(((int(x0), int(y0), int(x1 - x0), int(y1 - y0)), rects[i]))
    return res


SLIVER = False  # 서버 정리 1: 그림 끝에 닿은 가는 조각 버리기
KAN = False  # 서버 정리 2: 안깡(앞면 2 + 양끝 뒷면) 묶기
KAN_READ: dict = {}  # {(그림 지문, 뒷면 상자): 대신 읽을 앞면 상자}
KAN_LAST: set = set()  # 패 목록에 끼운 뒷면 상자(keep_faces 가 흰 비율로 버리지 않게) — 벤치 Det memo 때문에 지우지 않고 쌓는다


def slivers(res: list, W: int, H: int) -> list:
    """그림 가장자리(2px 안)에 닿아 있고 짧은 변이 다른 패 짧은 변 중앙값의 절반 미만 = 크롭에 잘린 패 조각(표 1-68 123140)."""
    if len(res) < 3:
        return res
    tw = float(np.median([min(rc[1]) for _, rc in res]))
    edge = lambda b: b[0] <= 2 or b[1] <= 2 or b[0] + b[2] >= W - 2 or b[1] + b[3] >= H - 2
    return [(b, rc) for b, rc in res if not (edge(b) and min(rc[1]) < 0.5 * tw)]


def kans(faces: list, backs: list) -> list[tuple]:
    """안깡 모양: 이웃한 앞면 두 장 A·B(중심 거리 ≤ 1.35 × 패 짧은 변) 의 줄 방향 양끝에 뒷면이 한 장씩(A − d, B + d 에서 0.45 × 짧은 변 안).
    [(뒷면 상자, 대신 읽을 앞면 상자)] 둘씩. 같은 패인지는 안 본다(안깡은 네 장이 같은 패라 앞면을 대신 읽는다)."""
    if len(faces) < 2 or not backs:
        return []
    tw = float(np.median([min(rc[1]) for _, rc in faces]))
    cen = lambda rc: np.array(rc[0], float)
    out, used = [], set()
    for i, (a, ra) in enumerate(faces):
        for j, (b, rb) in enumerate(faces):
            if j <= i:
                continue
            d = cen(rb) - cen(ra)
            if not 0.6 * tw <= np.linalg.norm(d) <= 1.35 * tw:
                continue
            ca = min(backs, key=lambda x: np.linalg.norm(cen(x[1]) - (cen(ra) - d)))
            cb = min(backs, key=lambda x: np.linalg.norm(cen(x[1]) - (cen(rb) + d)))
            if ca is cb or np.linalg.norm(cen(ca[1]) - (cen(ra) - d)) > 0.45 * tw or np.linalg.norm(cen(cb[1]) - (cen(rb) + d)) > 0.45 * tw:
                continue
            if {ca[0], cb[0]} & used:
                continue
            used |= {ca[0], cb[0]}
            out += [(ca, a), (cb, b)]
    return out


def run(session, rgb: np.ndarray) -> list:
    x, r, left, top = letterbox(rgb)
    out = session.run(None, {session.get_inputs()[0].name: x})[0][0]
    res = decode(out, r, left, top, rgb.shape[1], rgb.shape[0])
    if SLIVER:
        res = slivers(res, rgb.shape[1], rgb.shape[0])
    fp_orig = FP_NEXT.pop() if FP_NEXT else None
    if KAN and out.shape[0] >= 7:  # 2종(앞면·뒷면) 회전 상자 모델만
        fp0 = fp_orig or fingerprint(rgb)
        for (bb, rc), face in kans(res, decode(out, r, left, top, rgb.shape[1], rgb.shape[0], cls=1)):
            res.append((bb, rc))
            KAN_LAST.add(bb)
            KAN_READ[(fp0, bb)] = face
    RECTS.clear()
    RECTS.update({b: rect for b, rect in res})
    if len(ALL) > 50000:
        ALL.clear()
    fp = fp_orig or fingerprint(rgb)
    ALL.update({(fp, b): rect for b, rect in res})
    return [b for b, _ in res]


def upright(rgb: np.ndarray, rect, pad: float) -> Image.Image:
    """회전 상자를 가장 작은 회전으로 반듯하게 세워 자른다(긴 변 방향은 그대로 — 눕힌 패는 눕힌 채로, 뒤의 방향 판단이 축 상자 모양으로
    하기 때문). 여유는 서버 cut 과 같은 비율."""
    (cx, cy), (w, h), a = rect
    a = ((a + 45) % 90) - 45  # -45~45° 로 접고, 90° 넘겨 접었으면 w·h 를 바꾼다
    if round(((rect[2] - a) / 90)) % 2:
        w, h = h, w
    W2, H2 = w * (1 + 2 * pad), h * (1 + 2 * pad)
    R = int(np.ceil(np.hypot(W2, H2) / 2)) + 2
    H, W = rgb.shape[:2]
    x0, y0 = int(cx) - R, int(cy) - R
    part = np.full((2 * R, 2 * R, 3), 114, np.uint8)
    sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(W, x0 + 2 * R), min(H, y0 + 2 * R)
    part[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = rgb[sy0:sy1, sx0:sx1]
    M = cv2.getRotationMatrix2D((cx - x0, cy - y0), a, 1.0)
    rot = cv2.warpAffine(part, M, (2 * R, 2 * R), flags=cv2.INTER_LINEAR, borderValue=(114, 114, 114))
    c = (cx - x0, cy - y0)
    return Image.fromarray(rot[max(0, int(c[1] - H2 / 2)):int(c[1] + H2 / 2), max(0, int(c[0] - W2 / 2)):int(c[0] + W2 / 2)])


def install(bench, lr, rv, rot_white: bool, rot_cut: bool = False, sliver: bool = False, kan: bool = False) -> None:
    global SLIVER, KAN
    SLIVER, KAN = sliver, kan
    def det_detect(self, rgb):
        self.runs += 1
        return run(self.s, rgb)

    def lr_detect(self, rgb, low=True):
        det, _ = self._sessions()
        return self._run(lambda: run(det, rgb))

    bench.Det._detect = det_detect
    lr.LocalReader.detect = lr_detect
    if rot_white:
        old = rv.keep_faces

        def keep_faces(boxes, white, min_white=0.5):
            out = []
            for b in boxes:
                rect = RECTS.get(tuple(int(v) for v in b))
                if rect is None:  # 회전 상자를 모르는 상자(白 채우기 등)는 예전 방식
                    out += old([b], white, min_white)
                    continue
                m = np.zeros(white.shape, np.uint8)
                cv2.fillPoly(m, [np.round(cv2.boxPoints(rect)).astype(np.int32)], 1)
                inside = m > 0
                if inside.any() and float(white[inside].mean()) >= min_white:
                    out.append(b)
            return out

        rv.keep_faces = keep_faces
    if rot_cut:  # 분류기 크롭: 회전 상자대로 세워 자른다(상자를 모르면 예전 cut)
        for mod in (lr, bench):
            old_cut = mod.cut

            def cut(rgb, b, _old=old_cut, _pad=lr.PAD):
                rect = ALL.get((fingerprint(rgb), tuple(int(v) for v in b)))
                return upright(rgb, rect, _pad) if rect is not None else _old(rgb, b)

            mod.cut = cut
    if kan:  # 안깡: 끼운 뒷면 상자는 흰 비율 거르기를 건너뛰고, 읽을 때는 옆 앞면을 대신 읽는다
        prev_keep = rv.keep_faces

        def keep_faces_kan(boxes, white, min_white=0.5, _prev=prev_keep):
            kb = [b for b in boxes if tuple(int(v) for v in b) in KAN_LAST]
            return _prev([b for b in boxes if b not in kb], white, min_white) + kb

        rv.keep_faces = keep_faces_kan
        for mod in (lr, bench):
            prev_cut = mod.cut

            def cut_kan(rgb, b, _prev=prev_cut):
                face = KAN_READ.get((fingerprint(rgb), tuple(int(v) for v in b)))
                return _prev(rgb, face if face is not None else b)

            mod.cut = cut_kan
