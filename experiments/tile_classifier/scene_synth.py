"""개선 계획 7-2(2026-11-06): 장면 합성 — 실제 패 크롭을 펠트 위에 마작 규칙대로 놓고 카메라로 찍은 것처럼 만든다.
검출기(YOLO OBB: 앞면 0·뒷면 1, 네 꼭짓점) 사전학습 장면과 분류기(세워 자른 크롭 + 종류) 사전학습 크롭을 같은 그리기 함수로 낸다.

재료(`mat`, 노트북에서 한 번): data/synth/mat/
  faces/  data/harvest_obb 1,168장의 전수 조사 회전 상자(data/det/obb/rects.json)를 서버 app.obb.upright(pad 0)로 몸통만 세워 자르고 turn 으로 바로 세움
  backs/  rects.json 뒷면 상자(cls 1)를 같은 방법으로, 긴 변 세로
  felt/   data/zone_points/labels.json 펠트 사각형 안, 패 상자(30% 키움)·살색과 안 겹치는 256px 정사각형 조각(사진당 최대 14)
  index.json  {faces: [{file, tile, photo, part}], backs: [{file, photo, part, tone}], felt: [{file, photo, part}]}
나눔(누수 금지, 계획서 7-1 검토 ⑦): 재료마다 사진의 part(bcd·am·pm·other, det_rim_aug.part 와 같은 규칙)를 적고, 풀(pool)은 홀드아웃 사진의 재료를 뺀다.
  a     = am + other   → 검출기 fold_a(시험 오후·B·C·D) 사전학습, 분류기 cls_pm(시험 오후)
  b     = pm + other   → 검출기 fold_b(시험 오전·B·C·D), 분류기 cls_am(시험 오전)
  nobcd = am + pm      → 분류기 cls_bcd(시험 B·C·D, 'other' 도 뺀다 — det_eval.classifiers 가 B·C·D 나눔에서 'other' 를 뺀 것과 같게)
  all   = 전부          → 검출기 final, 분류기 cls_all(운영)
장면(마작 규칙): 자리 넷 — 화료자 손패 줄 13/14(떼어 둔 화료패 ±30~60° 또는 틈), 다른 자리 세운 뒷면 줄·공개·없음, 모서리 울기 3장(한 장 눕힘)·명깡 4장·
  안깡(뒷면 2 + 앞면 2), 강 6장 줄(리치 눕힘), 패산 2단 뒷면, 왕패 7줄(3번째 위 표시패 앞면), 떨어진 낱장, 가운데 기계·리치봉·종이(라벨 없음).
카메라: 호모그래피(기울기 0~30°, 방향 아무, 평면 회전, 초점), 크기 0.6~1.2, 패 옆면·그림자, 조명(노출·기울기·비네팅·화이트밸런스 ±15%)·그림자·손 가림·
  흐림 σ 0~3px(사진 해상도)·노이즈·JPEG q35~95. 분류기 크롭만 "빨강 채도 낮은 조명"(7-1 검토 ⑤). 시험용 색(테두리 검정·펠트 파랑·뒷면 노랑)은 안 쓴다(표 1-69).
  python -I -X utf8 experiments/tile_classifier/scene_synth.py mat
  python -I -X utf8 experiments/tile_classifier/scene_synth.py sheet [--pool all]           # data/synth/sheet_det.jpg·sheet_cls.jpg(눈 확인)
  python -I -X utf8 experiments/tile_classifier/scene_synth.py det --pool a --n 8000 --out DIR [--start 0] [--workers 4]   # 캐글 커널이 부름
  python -I -X utf8 experiments/tile_classifier/scene_synth.py cls --pool a --n 8000 [--per 3] [--workers 14]              # data/synth/cls_<pool>.npz
캐글에서는 이 파일 + data/synth/mat 만 올리고(--mat DIR) det 만 부른다(서버 코드 import 없음). cls 는 서버 app.obb.upright·local_read.PAD 를 import.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
SYNTH = HERE / "data" / "synth"
REPO = os.environ.get("RECOGNIZER_REPO", "C:/Users/jjh7757/dev/mahjong-recognizer")
BCD = {"k25", "k28", "k15", "k26", "k12", "k16"}
POOLS = {"a": {"am", "other"}, "b": {"pm", "other"}, "nobcd": {"am", "pm"}, "all": {"bcd", "am", "pm", "other"}}
CLASSES = [f"{n}{s}" for s in "mps" for n in range(1, 10)] + ["0m", "0p", "0s"] + [f"{n}z" for n in range(1, 8)]
# 팔레트(BGR) — det_build_fb 에서 시험용 색(뒷면 노랑 (40,170,240)·펠트 파랑 (140,70,30)·테두리 검정 (25,25,25))을 뺀 것 + 펠트·테두리 몇 가지
BACKS = [(200, 90, 30), (28, 25, 25), (70, 130, 40), (40, 40, 170), (90, 40, 20), (40, 70, 110), (230, 180, 120), None, None]
FELTS = [(125, 120, 0), (120, 50, 80), (40, 30, 130), (120, 120, 120), (35, 35, 35), (60, 85, 110), (70, 110, 40), None, None, None]
RIMS = [(232, 234, 236), (225, 228, 230), (200, 205, 208), (170, 175, 178), (60, 110, 170), (40, 60, 90), (70, 70, 70), (190, 215, 225)]
TEST = dict(back=(40, 170, 240), felt=(140, 70, 30), rim=(25, 25, 25))
TW, TH = 88.0, 118.0  # 평면 단위(= 원본 사진 px, 크기 1) 패 앞면 폭·높이
PW, PH = 4080, 3060  # 원본 사진 크기


def part(name: str) -> str:
    if name in BCD:
        return "bcd"
    if name.startswith("k"):
        return "other"
    return "am" if name < "20261031_14" else "pm"


# ---------------------------------------------------------------- 재료
def build_mats() -> None:
    sys.path.insert(0, REPO)
    from app import obb

    out = SYNTH / "mat"
    for d in ("faces", "backs", "felt"):
        (out / d).mkdir(parents=True, exist_ok=True)
    rects = json.loads((HERE / "data/det/obb/rects.json").read_text(encoding="utf-8"))
    hv = json.loads((HERE / "data/harvest_obb/index.json").read_text(encoding="utf-8"))
    felts = {k: v["felt"] for k, v in json.loads((HERE / "data/zone_points/labels.json").read_text(encoding="utf-8")).items() if v.get("felt")}
    by_photo: dict = {}
    for x in hv:
        by_photo.setdefault(x["photo"], []).append(x)
    idx: dict = {"faces": [], "backs": [], "felt": []}
    rng = random.Random(20261106)
    for name, r in sorted(rects.items()):
        bgr = cv2.imread(r["path"])
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        H, W = rgb.shape[:2]
        pt = part(name)
        items = {it["key"]: it for it in r["items"]}
        for x in by_photo.get(name, []):
            it = items[x["key"]]
            rect = (tuple(it["rect"][0]), tuple(it["rect"][1]), it["rect"][2])
            im = obb.upright(rgb, rect, 0.0)
            if x["turn"] % 360:
                im = im.rotate(x["turn"], expand=True)
            f = f"{x['id']:05d}.jpg"
            im.save(out / "faces" / f, quality=95)
            idx["faces"].append(dict(file=f, tile=x["tile"], photo=name, part=pt, src=x["id"]))
        nb = 0
        for it in r["items"]:
            if it["cls"] != 1:
                continue
            rect = (tuple(it["rect"][0]), tuple(it["rect"][1]), it["rect"][2])
            im = obb.upright(rgb, rect, 0.0)
            if im.width > im.height:
                im = im.rotate(90, expand=True)
            if im.width < 20 or im.height < 20:
                continue
            a = np.asarray(im)
            hsv = cv2.cvtColor(a, cv2.COLOR_RGB2HSV)
            sat = hsv[..., 1] > 40
            tone = [int(v) for v in np.median(a[sat], axis=0)[::-1]] if sat.sum() > 30 else [200, 200, 200]  # BGR
            f = f"{name}_{nb:03d}.jpg"
            im.save(out / "backs" / f, quality=95)
            idx["backs"].append(dict(file=f, photo=name, part=pt, tone=tone))
            nb += 1
        if name in felts:
            m = np.zeros((H, W), np.uint8)
            p = np.array([[x * W, y * H] for x, y in felts[name]], np.float32)
            c = p.mean(axis=0)
            cv2.fillPoly(m, [np.round(c + (p - c) * 0.96).astype(np.int32)], 255)
            for it in r["items"]:
                (cx, cy), (w, h), a = it["rect"]
                pts = cv2.boxPoints(((cx, cy), (w * 1.6 + 30, h * 1.6 + 30), a)).astype(np.int32)
                cv2.fillPoly(m, [pts], 0)
            hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
            skin = ((hsv[..., 0] <= 25) & (hsv[..., 1] >= 40) & (hsv[..., 2] >= 80)) | (hsv[..., 2] > 200) | (hsv[..., 2] < 25)
            m[cv2.dilate(skin.astype(np.uint8), np.ones((15, 15), np.uint8)) > 0] = 0
            ii = cv2.integral(m // 255)
            S = 256
            got = 0
            for _ in range(600):
                x0, y0 = rng.randint(0, W - S - 1), rng.randint(0, H - S - 1)
                s = ii[y0 + S, x0 + S] - ii[y0, x0 + S] - ii[y0 + S, x0] + ii[y0, x0]
                if s < 0.995 * S * S:
                    continue
                f = f"{name}_{got:02d}.jpg"
                cv2.imwrite(str(out / "felt" / f), bgr[y0:y0 + S, x0:x0 + S], [cv2.IMWRITE_JPEG_QUALITY, 95])
                idx["felt"].append(dict(file=f, photo=name, part=pt))
                m[max(0, y0 - S // 2):y0 + S + S // 2, max(0, x0 - S // 2):x0 + S + S // 2] = 0
                ii = cv2.integral(m // 255)
                got += 1
                if got >= 14:
                    break
        print(name, pt, "앞면", len(by_photo.get(name, [])), "뒷면", nb, "펠트", got if name in felts else 0, flush=True)
    (out / "index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=0), encoding="utf-8")
    from collections import Counter

    for k in ("faces", "backs", "felt"):
        print(k, len(idx[k]), dict(Counter(x["part"] for x in idx[k])))


class Mats:
    """풀 하나의 재료(BGR). faces_by[종류] = [그림], backs = [(그림, 색조)], felt = [그림]."""

    def __init__(self, root: Path, pool: str):
        idx = json.loads((root / "index.json").read_text(encoding="utf-8"))
        keep = POOLS[pool]
        self.pool = pool
        self.faces_by: dict = {}
        self.photos: set = set()
        for x in idx["faces"]:
            if x["part"] in keep:
                self.faces_by.setdefault(x["tile"], []).append(cv2.imread(str(root / "faces" / x["file"])))
                self.photos.add(x["photo"])
        self.backs = [(cv2.imread(str(root / "backs" / x["file"])), tuple(x["tone"]), x["photo"]) for x in idx["backs"] if x["part"] in keep]
        self.felt = [cv2.imread(str(root / "felt" / x["file"])) for x in idx["felt"] if x["part"] in keep]
        self.photos |= {x["photo"] for x in idx["backs"] + idx["felt"] if x["part"] in keep}
        self.kinds = sorted(self.faces_by)
        self.parts = sorted({x["part"] for k in ("faces", "backs", "felt") for x in idx[k] if x["part"] in keep})
        assert self.kinds and self.backs and self.felt, (pool, len(self.kinds), len(self.backs), len(self.felt))

    def summary(self) -> dict:
        return dict(pool=self.pool, parts=self.parts, faces=sum(map(len, self.faces_by.values())), kinds=len(self.kinds), backs=len(self.backs), felt=len(self.felt),
                    photos=len(self.photos))


# ---------------------------------------------------------------- 배치(평면 단위, 탁자 가운데 = 0, 자리 0 = 아래)
class Tile:
    __slots__ = ("c", "u", "w", "h", "kind", "tile", "img", "tone", "vis", "quad", "occ", "z")

    def __init__(self, c, u, w, h, kind, tile, img, tone):
        self.c, self.u, self.w, self.h = np.asarray(c, np.float64), np.asarray(u, np.float64), w, h
        self.kind, self.tile, self.img, self.tone = kind, tile, img, tone  # kind 0 앞면 1 뒷면
        self.vis, self.quad, self.occ, self.z = 1.0, None, 0.0, 1  # z = 쌓인 층 수(패산 2단 = 2, 옆면 두께)

    def corners(self) -> np.ndarray:
        """바로 선 패의 왼위·오른위·오른아래·왼아래(평면 단위)."""
        u = self.u
        r = np.array([-u[1], u[0]])
        hu, hr = u * self.h / 2, r * self.w / 2
        return np.array([self.c + hu - hr, self.c + hu + hr, self.c - hu + hr, self.c - hu - hr])


SEAT = [np.array(m, np.float64) for m in ([[1, 0], [0, 1]], [[0, 1], [-1, 0]], [[-1, 0], [0, -1]], [[0, -1], [1, 0]])]


def rot(v, deg):
    a = math.radians(deg)
    return np.array([v[0] * math.cos(a) - v[1] * math.sin(a), v[0] * math.sin(a) + v[1] * math.cos(a)])


class Layout:
    def __init__(self, rng: random.Random, mats: Mats):
        self.rng, self.m = rng, mats
        s = rng.uniform(0.92, 1.08)
        self.tw, self.th = TW * s, TH * s
        self.Fh = self.tw * rng.uniform(15.0, 17.0)
        self.rim = self.tw * rng.uniform(1.6, 2.8)
        self.dev = self.tw * rng.uniform(2.9, 3.4) if rng.random() < 0.85 else 0.0
        self.tiles: list[Tile] = []
        self.sticks: list = []
        self.papers: list = []
        self.back_color = rng.choice(BACKS)
        # 한 장면의 뒷면은 한 색: 재색칠하면 그 색, 아니면 사진 하나의 뒷면만 쓴다
        ph = rng.choice(sorted({b[2] for b in mats.backs}))
        self.backs = mats.backs if self.back_color is not None else [b for b in mats.backs if b[2] == ph]
        self.back_tone = self.back_color if self.back_color is not None else tuple(int(v) for v in np.median([b[1] for b in self.backs], axis=0))

    def face(self, tile: str | None = None):
        k = tile if tile in self.m.faces_by else self.rng.choice(self.m.kinds)
        return k, self.rng.choice(self.m.faces_by[k])

    def back(self):
        img, tone, _ = self.rng.choice(self.backs)
        return img, tone

    def add(self, seat: int, x: float, y: float, kind: int, tile: str | None = None, side: bool = False, ang: float = 0.0, jit: float = 1.0, z: int = 1) -> Tile:
        rng = self.rng
        M = SEAT[seat]
        c = M @ np.array([x + rng.gauss(0, 0.03 * self.tw) * jit, y + rng.gauss(0, 0.03 * self.tw) * jit])
        a = ang + rng.gauss(0, 1.2) * jit + (90.0 if side else 0.0)  # 눕힌 패 = 위가 왼쪽(반시계 90°)
        u = M @ rot(np.array([0.0, -1.0]), -a)
        if kind == 0:
            k, img = self.face(tile)
            t = Tile(c, u, self.tw, self.th, 0, k, img, None)
        else:
            img, tone = self.back()
            t = Tile(c, u, self.tw, self.th, 1, None, img, tone)
        t.z = z
        self.tiles.append(t)
        return t

    def row(self, seat, x0, y, n, kind, step=None, skew=0.0, tiles=None):
        step = step or self.tw * 1.01
        out = []
        for i in range(n):
            out.append(self.add(seat, x0 + i * step, y + i * step * math.tan(math.radians(skew)), kind, tiles[i] if tiles else None, ang=skew))
        return out

    def meld(self, seat, x_right, y_bottom, kind_of: str):
        """모서리 울기 하나를 오른쪽 끝 x_right 에서 왼쪽으로. 돌려준 값 = 다음 울기의 오른쪽 끝."""
        rng, tw, th = self.rng, self.tw, self.th
        t = rng.choice(self.m.kinds)
        typ = rng.choices(["pon", "chi", "minkan", "ankan"], [0.45, 0.3, 0.12, 0.13])[0]
        if typ == "chi" and t[1] in "mps" and t[0] in "1234567":
            ks = [f"{int(t[0]) + i}{t[1]}" for i in range(3)]
        else:
            ks = [t] * (4 if typ in ("minkan", "ankan") else 3)
        side_at = -1 if typ == "ankan" else rng.randrange(len(ks))
        x = x_right
        for i in reversed(range(len(ks))):
            if i == side_at:
                w = th
                self.add(seat, x - w / 2, y_bottom - tw / 2, 0, ks[i], side=True, jit=0.6)
            else:
                w = tw
                back = typ == "ankan" and i in (0, 3)
                self.add(seat, x - w / 2, y_bottom - th / 2, 1 if back else 0, ks[i], jit=0.6)
            x -= w + tw * 0.02
        return x - tw * rng.uniform(0.15, 0.5)

    def build(self) -> None:
        rng, tw, th, Fh = self.rng, self.tw, self.th, self.Fh
        winner = rng.randrange(4)
        dead_seat = rng.randrange(4)
        for s in range(4):
            win = s == winner
            yb = Fh - rng.uniform(0.15, 0.5) * th  # 손패·울기 아래 끝
            skew = rng.gauss(0, 1.5)
            # 울기(모서리)
            nm = rng.choices([0, 1, 2, 3], [0.45, 0.3, 0.17, 0.08] if win else [0.6, 0.28, 0.12, 0.0])[0]
            xr = Fh - rng.uniform(0.2, 1.2) * tw
            for _ in range(nm):
                xr = self.meld(s, xr, yb, "")
            # 손패
            mode = "face" if win else rng.choices(["back", "face", "none"], [0.6, 0.15, 0.25])[0]
            n = 14 - 3 * nm if win else 13 - 3 * nm
            if mode != "none" and n > 0:
                n_row = n - 1 if win else n
                x0 = min(xr - n_row * tw * 1.01 - tw * rng.uniform(0.3, 1.5), -n_row * tw / 2 + rng.uniform(-2, 2) * tw)
                x0 = max(x0, -Fh + tw)
                kind = 0 if mode == "face" else 1
                self.row(s, x0 + tw / 2, yb - th / 2, n_row, kind, skew=skew)
                if win:  # 화료패: 틈을 두거나 떼어 비스듬히
                    xe = x0 + n_row * tw * 1.01 + tw / 2
                    if rng.random() < 0.4:
                        self.add(s, xe + tw * rng.uniform(0.9, 1.8), yb - th * rng.uniform(0.6, 1.6), 0,
                                 ang=rng.choice([-1, 1]) * rng.uniform(30, 60), jit=1.5)
                    else:
                        self.add(s, xe + tw * rng.uniform(0.2, 0.8), yb - th / 2, 0)
            # 강(6장 줄, 리치 눕힘)
            nr = rng.randint(0, 20)
            y = max(self.dev, tw * 2.0) + th * rng.uniform(0.25, 0.6) + th / 2
            riichi = rng.randrange(nr) if nr and rng.random() < 0.3 else -1
            k, x, rowi = 0, -3 * tw, 0
            while k < nr:
                per = 6 if rowi < 2 else 99
                xs = -3 * tw + tw * rng.gauss(0, 0.1)
                x = xs
                for _ in range(per):
                    if k >= nr:
                        break
                    if k == riichi:
                        self.add(s, x + th / 2, y + (th - tw) / 2, 0, side=True)
                        x += th + tw * 0.02
                    else:
                        self.add(s, x + tw / 2, y, 0)
                        x += tw * 1.01
                    k += 1
                y += th * 1.02
                rowi += 1
            # 패산(2단 뒷면), 왕패
            if rng.random() < 0.55 or s == dead_seat:
                ns = rng.randint(4, 17) if s != dead_seat else rng.randint(7, 17)
                yw = min(y + th * rng.uniform(0.3, 1.0), yb - th * 1.9) if rng.random() < 0.5 else yb - th * rng.uniform(1.7, 2.6)
                xw = -ns * tw / 2 + rng.uniform(-1.5, 1.5) * tw
                dora_at = rng.randrange(0, ns - 6) + 2 if s == dead_seat and ns >= 7 else -1
                for i in range(ns):  # 위에서 보면 윗단만 보이고 아랫단은 옆면 → 한 장 + 옆면 두께 2배(전수 조사도 반 넘게 가린 아랫단은 지움)
                    xi = xw + i * tw * 1.01 + tw / 2
                    face = i == dora_at or (dora_at >= 0 and i == dora_at + 1 and rng.random() < 0.2)
                    self.add(s, xi, yw, 0 if face else 1, jit=0.5, z=2 if rng.random() < 0.92 or face else 1)
        # 떨어진 낱장(±45°)
        for _ in range(rng.choices([0, 1, 2], [0.6, 0.3, 0.1])[0]):
            self.add(0, rng.uniform(-0.8, 0.8) * Fh, rng.uniform(-0.8, 0.8) * Fh, rng.choice([0, 0, 1]), ang=rng.uniform(-60, 60), jit=2)
        # 리치봉(파란·흰 막대, 라벨 없음)·종이
        for _ in range(rng.choices([0, 1, 2, 3], [0.4, 0.3, 0.2, 0.1])[0]):
            self.sticks.append((np.array([rng.uniform(-0.6, 0.6) * Fh, rng.uniform(-0.6, 0.6) * Fh]), rng.uniform(0, 180),
                                rng.choice([(200, 120, 40), (210, 140, 60), (235, 235, 235), (60, 60, 200)])))
        for _ in range(rng.choices([0, 1, 2], [0.7, 0.2, 0.1])[0]):
            self.papers.append((np.array([rng.uniform(-1.1, 1.1) * Fh, rng.uniform(-1.1, 1.1) * Fh]), rng.uniform(0, 180),
                                th * rng.uniform(0.9, 3.5), rng.random() < 0.5))
        # 겹침 거르기: 앞서 놓인 패와 가운데가 너무 가까우면 뺀다
        keep: list[Tile] = []
        for t in self.tiles:
            if all(np.hypot(*(t.c - q.c)) > 0.6 * tw for q in keep):
                keep.append(t)
        self.tiles = [t for t in keep if max(abs(t.c[0]), abs(t.c[1])) < Fh - 0.3 * tw]


# ---------------------------------------------------------------- 카메라
class Camera:
    def __init__(self, rng: random.Random, view: str):
        self.tilt = rng.uniform(0, 10) if rng.random() < 0.5 else rng.uniform(10, 30)
        self.yaw = rng.uniform(0, 360)
        r = rng.random()
        self.roll = rng.gauss(0, 2.5) if r < 0.6 else rng.uniform(-25, 25) if r < 0.9 else rng.uniform(0, 360)
        self.roll += 90 * rng.randrange(4) if rng.random() < 0.3 else 0
        self.s = rng.uniform(0.6, 1.2)
        self.f = PW * rng.uniform(0.8, 1.3)
        self.cx = PW / 2 + rng.uniform(-0.08, 0.08) * PW
        self.cy = PH / 2 + rng.uniform(-0.08, 0.08) * PH
        a, t = math.radians(self.yaw), math.radians(self.tilt)
        ax = np.array([math.cos(a), math.sin(a), 0.0])
        Kx = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
        Rt = np.eye(3) + math.sin(t) * Kx + (1 - math.cos(t)) * Kx @ Kx
        g = math.radians(self.roll)
        Rz = np.array([[math.cos(g), -math.sin(g), 0], [math.sin(g), math.cos(g), 0], [0, 0, 1]])
        self.R = Rt @ Rz
        self.T = np.array([0, 0, self.f / self.s])
        K = np.array([[self.f, 0, self.cx], [0, self.f, self.cy], [0, 0, 1]])
        self.H = K @ np.column_stack([self.R[:, 0], self.R[:, 1], self.T])  # 평면 단위 → 원본 사진 px
        C = -self.R.T @ self.T  # 평면 좌표의 카메라 위치(z<0 = 위)
        self.foot, self.height = C[:2], abs(C[2])
        # 보기: whole = 사진 통째(긴 변 1280), window = 2040×1530 토막
        self.view = view

    def side(self, c: np.ndarray, thick: float) -> np.ndarray:
        """패 옆면이 보이는 방향·길이(평면 단위): 패에서 카메라 발 쪽으로 두께 × 수평 거리 / 높이."""
        v = self.foot - c
        d = np.hypot(*v)
        return np.zeros(2) if d < 1e-6 else v / d * thick * d / self.height


def apply_h(H: np.ndarray, pts: np.ndarray) -> np.ndarray:
    p = np.c_[pts, np.ones(len(pts))] @ H.T
    return p[:, :2] / p[:, 2:3]


# ---------------------------------------------------------------- 그리기
def recolor_lab(img: np.ndarray, mask: np.ndarray | None, bgr, keep_l: float = 1.0) -> np.ndarray:
    """mask(0~1 float) 안 색을 목표 색으로(밝기 무늬는 유지). det_build_fb.repaint 와 같은 생각."""
    if bgr is None:
        return img
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    t = cv2.cvtColor(np.uint8([[bgr]]), cv2.COLOR_BGR2LAB)[0, 0].astype(np.float32)
    m = np.ones(img.shape[:2], np.float32) if mask is None else mask
    sel = m > 0.5
    if sel.sum() < 20:
        return img
    mean = float(np.median(lab[..., 0][sel]))
    want = [np.clip((lab[..., 0] - mean) * (0.6 if t[0] < 60 else keep_l) + t[0], 0, 255), np.full_like(m, t[1]), np.full_like(m, t[2])]
    for i in range(3):
        lab[..., i] = lab[..., i] * (1 - m) + want[i] * m
    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


def noise_field(shape, rng: random.Random, scales=(3, 12, 40), amp=1.0) -> np.ndarray:
    nr = np.random.default_rng(rng.randrange(1 << 30))
    h, w = shape
    out = np.zeros((h, w), np.float32)
    for s in scales:
        sh, sw = max(2, h // s), max(2, w // s)
        out += cv2.resize(nr.standard_normal((sh, sw)).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
    return out * amp / len(scales)


def back_img(t: Tile, lay: Layout, cache: dict) -> np.ndarray:
    key = id(t.img)
    if key not in cache:
        img = t.img
        if lay.back_color is not None:
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            m = cv2.GaussianBlur(((hsv[..., 1] > 40) & (hsv[..., 2] > 40)).astype(np.float32), (0, 0), 1.2)
            img = recolor_lab(img, m, lay.back_color)
        cache[key] = img
    return cache[key]


def round_alpha(h: int, w: int, r: float) -> np.ndarray:
    a = np.zeros((h, w), np.uint8)
    rr = max(1, int(r))
    cv2.rectangle(a, (rr, 0), (w - 1 - rr, h - 1), 255, -1)
    cv2.rectangle(a, (0, rr), (w - 1, h - 1 - rr), 255, -1)
    for cx, cy in ((rr, rr), (w - 1 - rr, rr), (rr, h - 1 - rr), (w - 1 - rr, h - 1 - rr)):
        cv2.circle(a, (cx, cy), rr, 255, -1)
    return cv2.GaussianBlur(a, (0, 0), 0.7).astype(np.float32) / 255


def paste_quad(dst: np.ndarray, src: np.ndarray, quad: np.ndarray, alpha: np.ndarray | None = None, gain: float = 1.0) -> None:
    """src(바로 선 그림)를 dst 의 quad(왼위·오른위·오른아래·왼아래, px)로 아핀 붙이기. 제자리."""
    H, W = dst.shape[:2]
    x0, y0 = np.floor(quad.min(0)).astype(int) - 2
    x1, y1 = np.ceil(quad.max(0)).astype(int) + 2
    X0, Y0, X1, Y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
    if X1 <= X0 or Y1 <= Y0:
        return
    h, w = src.shape[:2]
    M = cv2.getAffineTransform(np.float32([[0, 0], [w, 0], [0, h]]), np.float32([quad[0] - [X0, Y0], quad[1] - [X0, Y0], quad[3] - [X0, Y0]]))
    size = (X1 - X0, Y1 - Y0)
    tile = cv2.warpAffine(src, M, size, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE).astype(np.float32) * gain
    a = cv2.warpAffine(alpha if alpha is not None else np.ones((h, w), np.float32), M, size, flags=cv2.INTER_LINEAR, borderValue=0)[..., None]
    roi = dst[Y0:Y1, X0:X1].astype(np.float32)
    dst[Y0:Y1, X0:X1] = np.clip(roi * (1 - a) + tile * a, 0, 255).astype(np.uint8)


def render(rng: random.Random, mats: Mats, view: str, cls_light: bool = False):
    """장면 하나. view = whole(사진 통째 → 1280×960) | window(2040×1530 토막 → 1280×960) | cls(2040×1530 토막, 원본 해상도).
    돌려줌: (BGR 그림, 패 목록 — quad(그림 px)·vis(남는 비율)·occ(손 가림 비율)·kind·tile·up(그림 좌표 위 방향), 메타)."""
    lay = Layout(rng, mats)
    lay.build()
    cam = Camera(rng, view)
    if view == "whole":
        k, ow, oh = 1280 / PW, 1280, 960
        ox = oy = 0.0
    else:
        k = 1280 / 2040 if view == "window" else 1.0
        ow, oh = (1280, 960) if view == "window" else (2040, 1530)
        # 토막 위치: 탁자 안쪽이 들어오게(실제 토막처럼 9칸 중 하나 + 흔들기)
        ox = rng.choice([0, (PW - 2040) / 2, PW - 2040]) + rng.uniform(-200, 200)
        oy = rng.choice([0, (PH - 1530) / 2, PH - 1530]) + rng.uniform(-150, 150)
        ox, oy = float(np.clip(ox, 0, PW - 2040)), float(np.clip(oy, 0, PH - 1530))
    A = np.array([[k, 0, -ox * k], [0, k, -oy * k], [0, 0, 1]])
    Hout = A @ cam.H  # 평면 단위 → 출력 px
    # 출력 네 귀퉁이를 평면으로 되돌려 그릴 범위
    inv = np.linalg.inv(Hout)
    corners = apply_h(inv, np.array([[0, 0], [ow, 0], [ow, oh], [0, oh]], np.float64))
    ext = 2.4 * lay.Fh
    lo = np.clip(corners.min(0) - lay.tw * 2, -ext, ext)
    hi = np.clip(corners.max(0) + lay.tw * 2, -ext, ext)
    rho = min(1.0, 1.05 * k * cam.s)
    pw_, ph_ = int((hi[0] - lo[0]) * rho) + 1, int((hi[1] - lo[1]) * rho) + 1
    if pw_ * ph_ > 4600 * 4600:
        rho *= 4600 / math.sqrt(pw_ * ph_)
        pw_, ph_ = int((hi[0] - lo[0]) * rho) + 1, int((hi[1] - lo[1]) * rho) + 1
    P = np.array([[rho, 0, -lo[0] * rho], [0, rho, -lo[1] * rho], [0, 0, 1]])  # 평면 단위 → 평면 그림 px
    to_px = lambda pts: apply_h(P, pts)

    # 바탕(탁자 밖)
    base = np.array(rng.choice([(60, 60, 60), (90, 100, 110), (150, 160, 170), (40, 45, 60), (70, 100, 130), (120, 110, 100)]), np.float32)
    img = np.clip(base[None, None, :] * (1 + 0.25 * noise_field((ph_, pw_), rng, (4, 16))[..., None]) + 0, 0, 255).astype(np.uint8)
    def box(half):  # 평면 가운데 정사각형(반 변 half) → 평면 그림 px 범위(잘림)
        a = to_px(np.array([[-half, -half], [half, half]]))
        x0, y0 = np.clip(np.round(a[0]).astype(int), 0, [pw_, ph_])
        x1, y1 = np.clip(np.round(a[1]).astype(int), 0, [pw_, ph_])
        return x0, y0, x1, y1
    # 테두리(평면에서 축 정렬 사각형)
    rc = np.array(rng.choice(RIMS), np.float32)
    x0, y0, x1, y1 = box(lay.Fh + lay.rim)
    if x1 > x0 and y1 > y0:
        shade = 1 + 0.04 * noise_field((y1 - y0, x1 - x0), rng, (6, 30))
        img[y0:y1, x0:x1] = np.clip(rc[None, None, :] * shade[..., None], 0, 255).astype(np.uint8)
    if rng.random() < 0.6:  # 테두리 홈(어두운 회색 칸)
        for s in range(4):
            for _ in range(rng.randint(1, 3)):
                a = rng.uniform(-0.8, 0.8) * lay.Fh
                L = lay.tw * rng.uniform(2, 6)
                pts = np.array([[a - L / 2, lay.Fh + lay.rim * 0.25], [a + L / 2, lay.Fh + lay.rim * 0.25], [a + L / 2, lay.Fh + lay.rim * 0.8], [a - L / 2, lay.Fh + lay.rim * 0.8]])
                pts = pts @ SEAT[s].T
                cv2.fillPoly(img, [np.round(to_px(pts)).astype(np.int32)], tuple(int(v) for v in np.array([55, 55, 60]) * rng.uniform(0.8, 1.3)))
    # 펠트: 실사 조각을 깔고 한 색으로 맞춘 뒤 재색칠 + 임의 질감
    x0, y0, x1, y1 = box(lay.Fh)
    if x1 > x0 and y1 > y0:
        fw, fh = x1 - x0, y1 - y0
        S = max(16, int(256 * rho * rng.uniform(0.8, 1.6)))
        canvas = np.zeros((fh + S, fw + S, 3), np.float32)
        ref = None
        for yi in range(0, fh, S):
            for xi in range(0, fw, S):
                p = rng.choice(mats.felt)
                p = cv2.rotate(p, rng.choice([cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180, cv2.ROTATE_90_COUNTERCLOCKWISE])) if rng.random() < 0.75 else p
                p = cv2.resize(p, (S, S), interpolation=cv2.INTER_AREA).astype(np.float32)
                m = p.reshape(-1, 3).mean(0)
                ref = m if ref is None else ref
                canvas[yi:yi + S, xi:xi + S] = p - m + ref
        canvas = canvas[:fh, :fw]
        canvas += noise_field((fh, fw), rng, (8, 40, 160), amp=rng.uniform(2, 7))[..., None]
        fc = rng.choice(FELTS)
        canvas = np.clip(canvas, 0, 255).astype(np.uint8)
        canvas = recolor_lab(canvas, None, fc, keep_l=rng.uniform(0.8, 1.4)) if fc is not None else canvas
        img[y0:y1, x0:x1] = canvas
        if rng.random() < 0.6:  # 강 안내선
            for _ in range(rng.randint(1, 4)):
                h_ = rng.uniform(lay.dev + lay.th, lay.Fh - 1.5 * lay.th)
                pts = np.array([[-h_, -h_], [h_, -h_], [h_, h_], [-h_, h_]])
                col = tuple(int(v) for v in np.clip(canvas.reshape(-1, 3).mean(0) * rng.uniform(1.15, 1.35), 0, 255))
                cv2.polylines(img, [np.round(to_px(pts)).astype(np.int32)], True, col, max(1, int(2.5 * rho)), cv2.LINE_AA)
    # 가운데 기계
    if lay.dev:
        d = lay.dev
        dc = np.array(rng.choice([(60, 40, 30), (50, 50, 55), (90, 60, 40), (40, 40, 40), (120, 120, 125)]), np.float32)
        pts = to_px(np.array([[-d, -d], [d, -d], [d, d], [-d, d]]))
        cv2.fillPoly(img, [np.round(pts).astype(np.int32)], tuple(int(v) for v in dc))
        cv2.circle(img, tuple(int(v) for v in to_px(np.zeros((1, 2)))[0]), int(d * 0.45 * rho), tuple(int(v) for v in dc * 1.6), -1, cv2.LINE_AA)
        for _ in range(rng.randint(2, 6)):
            p = to_px(np.array([[rng.uniform(-0.8, 0.8) * d, rng.uniform(-0.8, 0.8) * d]]))[0]
            cv2.circle(img, (int(p[0]), int(p[1])), int(d * rng.uniform(0.06, 0.12) * rho), rng.choice([(40, 40, 200), (200, 100, 40), (200, 200, 200)]), -1, cv2.LINE_AA)
    # 리치봉·종이(라벨 없음)
    for c, ang, col in lay.sticks:
        u = rot(np.array([1.0, 0.0]), ang)
        r = np.array([-u[1], u[0]])
        L, Wd = lay.tw * rng.uniform(5, 7), lay.tw * 0.35
        pts = np.array([c - u * L / 2 - r * Wd / 2, c + u * L / 2 - r * Wd / 2, c + u * L / 2 + r * Wd / 2, c - u * L / 2 + r * Wd / 2])
        cv2.fillPoly(img, [np.round(to_px(pts)).astype(np.int32)], col, cv2.LINE_AA)
    for c, ang, L, plain in lay.papers:
        u = rot(np.array([1.0, 0.0]), ang)
        r = np.array([-u[1], u[0]])
        Wd = L / rng.uniform(1.3, 3.0)
        q = np.array([c - u * L / 2 - r * Wd / 2, c + u * L / 2 - r * Wd / 2, c + u * L / 2 + r * Wd / 2, c - u * L / 2 + r * Wd / 2])
        pap = np.full((64, int(64 * L / Wd) or 64, 3), rng.choice([(240, 245, 245), (215, 228, 240), (222, 222, 238)]), np.uint8)
        if not plain:
            for _ in range(rng.randint(3, 8)):
                yv = rng.randint(5, 58)
                cv2.line(pap, (rng.randint(3, pap.shape[1] // 3), yv), (rng.randint(pap.shape[1] // 2, pap.shape[1] - 3), yv), rng.choice([(40, 40, 40), (90, 60, 200)]), 2)
        qq = to_px(q)
        paste_quad(img, cv2.rotate(pap, cv2.ROTATE_90_CLOCKWISE), np.array([qq[3], qq[0], qq[1], qq[2]]))

    # 패: 그림자 → 옆면 → 앞면, 가림은 낮은 해상도 주인 지도로
    thick = 0.75 * lay.tw
    light = rot(np.array([1.0, 0.0]), rng.uniform(0, 360)) * lay.tw * rng.uniform(0.08, 0.25)
    shadow = np.zeros((ph_, pw_), np.float32)
    sides = []
    lay.tiles.sort(key=lambda t: -float(np.hypot(*(t.c - cam.foot))))  # 먼 패부터(가까운 패가 먼 패의 옆면·앞면을 가린다)
    for t in lay.tiles:
        q = t.corners()
        v = cam.side(t.c, thick * t.z)
        hull = cv2.convexHull(np.float32(np.r_[q, q + v])).reshape(-1, 2)
        sides.append((q, v, hull))
        cv2.fillPoly(shadow, [np.round(to_px(hull + v * 0.3 + light)).astype(np.int32)], 1.0, cv2.LINE_AA)
    sh_s = max(1.0, 0.15 * lay.tw * rho)
    shadow = cv2.GaussianBlur(shadow, (0, 0), sh_s) * rng.uniform(0.2, 0.45)
    img = np.clip(img.astype(np.float32) * (1 - shadow[..., None]), 0, 255).astype(np.uint8)
    lowf = 0.25
    owner = np.full((int(ph_ * lowf) + 1, int(pw_ * lowf) + 1), -1, np.int32)
    cache: dict = {}
    ivory = np.array(rng.choice([(222, 228, 230), (210, 220, 225), (230, 232, 232)]), np.float32)
    al_cache: dict = {}
    for i, (t, (q, v, hull)) in enumerate(zip(lay.tiles, sides)):
        tone = np.array(lay.back_tone, np.float32)  # 옆면의 뒷면 층 색 = 이 장면 뒷면 색
        near, far = (ivory, tone) if t.kind == 0 else (tone, ivory)
        if np.hypot(*v) * rho > 0.8:
            h_far = cv2.convexHull(np.float32(np.r_[q + v * 0.5, q + v])).reshape(-1, 2)
            h_near = cv2.convexHull(np.float32(np.r_[q, q + v * 0.55])).reshape(-1, 2)
            cv2.fillPoly(img, [np.round(to_px(h_far)).astype(np.int32)], tuple(int(c) for c in far * 0.82), cv2.LINE_AA)
            cv2.fillPoly(img, [np.round(to_px(h_near)).astype(np.int32)], tuple(int(c) for c in near * 0.88), cv2.LINE_AA)
        src = t.img if t.kind == 0 else back_img(t, lay, cache)
        key = src.shape[:2]
        if key not in al_cache:
            al_cache[key] = round_alpha(key[0], key[1], 0.08 * key[1])
        paste_quad(img, src, to_px(q), al_cache[key], gain=rng.uniform(0.94, 1.06))
        cv2.fillPoly(owner, [np.round(to_px(hull) * lowf).astype(np.int32)], i)
    # 앞면이 나중 패에 덮인 비율(낮은 해상도 주인 지도, 패 둘레 범위만)
    vis_cnt = np.zeros(len(lay.tiles))
    total = np.ones(len(lay.tiles))
    for i, (t, (q, v, hull)) in enumerate(zip(lay.tiles, sides)):
        fp = to_px(q) * lowf
        bx0, by0 = np.maximum(np.floor(fp.min(0)).astype(int) - 1, 0)
        bx1, by1 = np.minimum(np.ceil(fp.max(0)).astype(int) + 2, [owner.shape[1], owner.shape[0]])
        if bx1 <= bx0 or by1 <= by0:
            continue
        fq = np.zeros((by1 - by0, bx1 - bx0), np.uint8)
        cv2.fillPoly(fq, [np.round(fp - [bx0, by0]).astype(np.int32)], 1)
        total[i] = max(1, fq.sum())
        vis_cnt[i] = ((owner[by0:by1, bx0:bx1] == i) & (fq > 0)).sum()
    # 평면 → 출력
    M = Hout @ np.linalg.inv(P)
    out = cv2.warpPerspective(img, M, (ow, oh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    res = []
    rect = np.float32([[0, 0], [ow, 0], [ow, oh], [0, oh]])
    for i, t in enumerate(lay.tiles):
        quad = apply_h(Hout, t.corners())
        area = abs(cv2.contourArea(np.float32(quad)))
        if area < 1:
            continue
        inter, _ = cv2.intersectConvexConvex(np.float32(quad), rect)
        inside = inter / area
        if inside < 0.5:
            continue
        up = apply_h(Hout, np.array([t.c + t.u * t.h / 2]))[0] - apply_h(Hout, np.array([t.c - t.u * t.h / 2]))[0]
        res.append(dict(quad=quad, kind=t.kind, tile=t.tile, vis=float(vis_cnt[i] / total[i]), inside=float(inside), occ=0.0, up=up))
    # 사진 단계 효과: 손 가림 → 그림자 → 조명 → 흐림·노이즈 → JPEG
    out = out.astype(np.float32)
    hand = np.zeros((oh, ow), np.float32)
    if rng.random() < 0.3:
        for _ in range(rng.randint(1, 2)):
            e = rng.randrange(4)
            L = rng.uniform(0.25, 0.6) * min(ow, oh)
            wd = L * rng.uniform(0.25, 0.4)
            p0 = [(rng.uniform(0, ow), 0), (ow, rng.uniform(0, oh)), (rng.uniform(0, ow), oh), (0, rng.uniform(0, oh))][e]
            ctr = np.array([ow / 2, oh / 2]) + np.array([rng.uniform(-0.3, 0.3) * ow, rng.uniform(-0.3, 0.3) * oh])
            d = ctr - p0
            d /= np.hypot(*d) + 1e-6
            tip = np.array(p0) + d * L
            arm = np.zeros((oh, ow), np.uint8)
            cv2.line(arm, tuple(int(v) for v in p0), tuple(int(v) for v in tip), 255, int(wd))
            cv2.ellipse(arm, (int(tip[0]), int(tip[1])), (int(wd * 0.8), int(wd * 0.6)), math.degrees(math.atan2(d[1], d[0])), 0, 360, 255, -1)
            hand = np.maximum(hand, cv2.GaussianBlur(arm.astype(np.float32) / 255, (0, 0), max(1, wd * 0.05)))
        skin = np.array(rng.choice([(150, 175, 220), (120, 150, 200), (90, 120, 170), (170, 190, 225)]), np.float32)
        tex = 1 + 0.08 * noise_field((oh, ow), rng, (4, 20))
        shade = np.linspace(0.85, 1.1, ow)[None, :] if rng.random() < 0.5 else np.linspace(0.85, 1.1, oh)[:, None]
        out = out * (1 - hand[..., None]) + (skin[None, None, :] * (tex * shade)[..., None]) * hand[..., None]
        for r in res:
            qx0, qy0 = np.maximum(np.floor(r["quad"].min(0)).astype(int), 0)
            qx1, qy1 = np.minimum(np.ceil(r["quad"].max(0)).astype(int) + 1, [ow, oh])
            if qx1 <= qx0 or qy1 <= qy0:
                continue
            m = np.zeros((qy1 - qy0, qx1 - qx0), np.uint8)
            cv2.fillPoly(m, [np.round(r["quad"] - [qx0, qy0]).astype(np.int32)], 1)
            n = m.sum()
            r["occ"] = float((hand[qy0:qy1, qx0:qx1][m > 0] > 0.5).sum() / n) if n else 1.0
    if rng.random() < 0.4:  # 팔·물건 그림자
        sm = np.zeros((oh, ow), np.uint8)
        pts = np.array([[rng.uniform(-0.2, 1.2) * ow, rng.uniform(-0.2, 1.2) * oh] for _ in range(rng.randint(3, 6))], np.int32)
        cv2.fillPoly(sm, [cv2.convexHull(pts)], 255)
        sm = cv2.GaussianBlur(sm.astype(np.float32) / 255, (0, 0), 0.03 * ow) * rng.uniform(0.15, 0.4)
        out *= 1 - sm[..., None]
    gain = rng.uniform(0.75, 1.25)
    gx, gy = rng.uniform(-0.2, 0.2), rng.uniform(-0.2, 0.2)
    yy, xx = np.mgrid[0:oh, 0:ow].astype(np.float32)
    ramp = 1 + gx * (xx / ow - 0.5) + gy * (yy / oh - 0.5)
    vig = 1 - rng.uniform(0, 0.25) * (((xx / ow - 0.5) ** 2 + (yy / oh - 0.5) ** 2) / 0.5)
    wb = np.array([rng.uniform(0.87, 1.13), rng.uniform(0.95, 1.05), rng.uniform(0.87, 1.13)], np.float32)
    out = out * (gain * ramp * vig)[..., None] * wb[None, None, :]
    out = np.clip(out, 0, 255).astype(np.uint8)
    if cls_light and rng.random() < 0.15:  # 빨강 채도 낮은 조명(분류기 크롭만, 7-1 검토 ⑤)
        hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.float32)
        red = (hsv[..., 0] < 12) | (hsv[..., 0] > 168)
        hsv[..., 1][red] *= rng.uniform(0.3, 0.7)
        out = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR)
    sig = rng.uniform(0.3, 3.0) * k if rng.random() < 0.5 else 0.0  # 사진 해상도 σ → 출력 해상도
    if sig > 0.2:
        out = cv2.GaussianBlur(out, (0, 0), sig)
    if rng.random() < 0.1:
        L = max(3, int(rng.uniform(3, 9) * k * 2) | 1)
        kern = np.zeros((L, L), np.float32)
        kern[L // 2] = 1 / L
        kern = cv2.warpAffine(kern, cv2.getRotationMatrix2D((L / 2 - 0.5, L / 2 - 0.5), rng.uniform(0, 180), 1), (L, L))
        out = cv2.filter2D(out, -1, kern / max(kern.sum(), 1e-6))
    nz = rng.uniform(0, 4)
    if nz > 0.5:
        out = np.clip(out.astype(np.float32) + np.random.default_rng(rng.randrange(1 << 30)).normal(0, nz, out.shape), 0, 255).astype(np.uint8)
    q = rng.randint(35, 95)
    out = cv2.imdecode(cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, q])[1], cv2.IMREAD_COLOR)
    meta = dict(view=view, tilt=round(cam.tilt, 1), roll=round(cam.roll, 1), s=round(cam.s, 3), jpeg=q, blur=round(sig, 2), hand=bool(hand.any()),
                back=lay.back_color, n=len(lay.tiles))
    return out, res, meta


def det_lines(res: list, ow: int, oh: int) -> list[str]:
    """YOLO OBB 라벨(det_build.label_lines 와 같은 규칙: 절반 이상 들어온 것, 꼭짓점은 그림 안으로 자름). 나중 패에 절반 넘게 덮이거나 손에 절반 넘게 가린 패는 뺀다."""
    out = []
    for r in res:
        if r["vis"] < 0.5 or r["occ"] > 0.5:
            continue
        pts = np.clip(r["quad"] / [ow, oh], 0, 1)
        out.append(f"{r['kind']} " + " ".join(f"{v:.6f}" for v in pts.reshape(-1)))
    return out


# ---------------------------------------------------------------- 출력
def _det_one(args):
    i, pool, mat, out, seed = args
    m = _MATS.get(pool) or _MATS.setdefault(pool, Mats(Path(mat), pool))
    rng = random.Random(seed * 1_000_003 + i)
    view = "whole" if rng.random() < 0.3 else "window"
    img, res, meta = render(rng, m, view)
    name = f"syn{pool}_{i:05d}"
    cv2.imwrite(str(Path(out) / "images" / f"{name}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    lines = det_lines(res, img.shape[1], img.shape[0])
    (Path(out) / "labels" / f"{name}.txt").write_text("\n".join(lines), encoding="utf-8")
    return len(lines)


_MATS: dict = {}
SEEDS = {"a": 7201, "b": 7202, "nobcd": 7203, "all": 7204}


def make_det(pool: str, n: int, out: Path, mat: Path, start: int = 0, workers: int = 4, seed_add: int = 0) -> None:
    from multiprocessing import Pool

    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)
    print("재료", Mats(mat, pool).summary(), flush=True)
    jobs = [(i, pool, str(mat), str(out), SEEDS[pool] + seed_add) for i in range(start, start + n)]
    tot = 0
    with Pool(workers) as p:
        for k, c in enumerate(p.imap_unordered(_det_one, jobs, chunksize=8)):
            tot += c
            if (k + 1) % 1000 == 0:
                print("합성", pool, k + 1, "/", n, "상자", tot, flush=True)
    print("합성 끝", pool, n, "상자", tot, flush=True)


def _canon(crop, up: np.ndarray, a: float):
    """upright 가 a° 돌린 뒤 패 위쪽이 어디를 향하는지 보고 바로 세운다(PIL rotate 는 반시계)."""
    M = cv2.getRotationMatrix2D((0, 0), a, 1.0)[:, :2]
    u = M @ up
    ang = math.degrees(math.atan2(-u[1], u[0]))  # 화면 위 = 90
    turn = int(round((90 - ang) / 90)) % 4  # 반시계 몇 번
    return crop.rotate(90 * turn, expand=True) if turn else crop


def _cls_one(args):
    i, pool, mat, per, seed = args
    sys.path.insert(0, REPO)
    from app import obb
    from app.local_read import PAD

    m = _MATS.get(pool) or _MATS.setdefault(pool, Mats(Path(mat), pool))
    rng = random.Random(seed * 1_000_003 + i)
    img, res, meta = render(rng, m, "cls", cls_light=True)
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    good = [r for r in res if r["kind"] == 0 and r["vis"] > 0.95 and r["occ"] < 0.05 and r["inside"] > 0.999]
    rng.shuffle(good)
    out = []
    for r in good[:per]:
        rect = cv2.minAreaRect(np.float32(r["quad"]))
        if min(rect[1]) < 12:
            continue
        crop = obb.upright(rgb, rect, PAD)
        a = ((rect[2] + 45) % 90) - 45
        crop = _canon(crop, r["up"], a)
        sq = crop.copy()
        sq.thumbnail((128, 128))
        from PIL import Image

        canvas = Image.new("RGB", (128, 128), (114, 114, 114))
        canvas.paste(sq, ((128 - sq.width) // 2, (128 - sq.height) // 2))
        out.append((np.asarray(canvas), CLASSES.index(r["tile"])))
    return out


def _one_thread() -> None:
    """작업자마다 OpenCV·numpy 스레드 1개(노트북 14 작업자 × 여러 스레드가 겹쳐 2.5배 느려졌다). 그림은 같다."""
    cv2.setNumThreads(1)


def make_cls(pool: str, n: int, per: int, mat: Path, workers: int) -> Path:
    from multiprocessing import Pool

    print("재료", Mats(mat, pool).summary(), flush=True)
    jobs = [(i, pool, str(mat), per, SEEDS[pool] + 100) for i in range(n)]
    X, Y = [], []
    with Pool(workers, initializer=_one_thread) as p:
        for k, got in enumerate(p.imap(_cls_one, jobs, chunksize=16)):
            for x, y in got:
                X.append(x)
                Y.append(y)
            if (k + 1) % 1000 == 0:
                print("크롭", pool, k + 1, "/", n, len(Y), flush=True)
    dst = SYNTH / f"cls_{pool}.npz"
    np.savez(dst, x=np.stack(X), y=np.array(Y, np.int16))
    from collections import Counter

    print("크롭 끝", pool, len(Y), "종류", len(set(Y)), Counter(CLASSES[y] for y in Y).most_common()[-5:], flush=True)
    return dst


def sheet(pool: str, mat: Path) -> None:
    m = Mats(mat, pool)
    print(m.summary())
    tiles = []
    for i in range(12):
        rng = random.Random(900 + i)
        view = ["whole", "window", "window"][i % 3]
        img, res, meta = render(rng, m, view)
        vis = img.copy()
        for r in res:
            ok = r["vis"] >= 0.5 and r["occ"] <= 0.5
            col = ((0, 0, 255) if r["kind"] == 0 else (255, 80, 0)) if ok else (0, 255, 255)
            cv2.polylines(vis, [np.round(r["quad"]).astype(np.int32)], True, col, 2)
        cv2.putText(vis, f"{view} tilt {meta['tilt']} roll {meta['roll']} s {meta['s']} q{meta['jpeg']} blur {meta['blur']}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (255, 255, 255), 2)
        tiles.append(cv2.resize(vis, (640, 480)))
    rows = [np.hstack(tiles[r * 3:r * 3 + 3]) for r in range(4)]
    cv2.imwrite(str(SYNTH / "sheet_det.jpg"), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])
    crops = []
    for i in range(60):
        for x, y in _cls_one((i, pool, str(mat), 3, 4242)):
            crops.append((x, CLASSES[y]))
    cols = 16
    S = np.full((((len(crops) + cols - 1) // cols) * 150, cols * 130, 3), 255, np.uint8)
    for j, (x, t) in enumerate(crops[:cols * 10]):
        r, c = divmod(j, cols)
        S[r * 150:r * 150 + 128, c * 130:c * 130 + 128] = x[..., ::-1]
        cv2.putText(S, t, (c * 130 + 4, r * 150 + 145), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 200), 1)
    cv2.imwrite(str(SYNTH / "sheet_cls.jpg"), S[:min(len(S), 10 * 150)], [cv2.IMWRITE_JPEG_QUALITY, 90])
    print("표본", SYNTH / "sheet_det.jpg", SYNTH / "sheet_cls.jpg", len(crops))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["mat", "sheet", "det", "cls", "time"])
    ap.add_argument("--pool", default="all")
    ap.add_argument("--n", type=int, default=8000)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--per", type=int, default=3)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed-add", type=int, default=0)
    ap.add_argument("--out", default="")
    ap.add_argument("--mat", default=str(SYNTH / "mat"))
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.cmd == "mat":
        build_mats()
    elif a.cmd == "sheet":
        sheet(a.pool, Path(a.mat))
    elif a.cmd == "det":
        make_det(a.pool, a.n, Path(a.out), Path(a.mat), a.start, a.workers, a.seed_add)
    elif a.cmd == "cls":
        make_cls(a.pool, a.n, a.per, Path(a.mat), a.workers)
    else:
        import time

        m = Mats(Path(a.mat), a.pool)
        for view in ("whole", "window", "cls"):
            t0 = time.perf_counter()
            for i in range(5):
                render(random.Random(i), m, view)
            print(view, round((time.perf_counter() - t0) / 5, 3), "초/장")


if __name__ == "__main__":
    main()
