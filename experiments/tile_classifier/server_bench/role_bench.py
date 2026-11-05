"""자리 판독 단독 벤치에 역할 모델을 끼워 규칙과 나란히 잰다(2026-11-04, 노트북, API 없음). metrics 표 1-60.

같은 자리 크롭(crops/, meta.json, 격자 40 키움·자리 방향으로 세움)에 같은 검출기·분류기(ONNX)를 쓰고, 상자에서 손패·울기를 고르는 부분만 둘로:
  규칙 = bench.one(운영 st.frame → split2 + ok2, 표 1-26 흐름)
  모델 = 크롭 상자를 원본 좌표로 되돌려 펠트 격자 기준 벡터로 만들고(role_set.scene_tokens, 뒷면 없음) 역할 모델(합성 사전학습 pre_synth8k_nbc2.pt(뒷면 없음·자리 크롭 범위, role_set.py --no-backs --crop)를
         실제 25장 전부로 미세 조정, 3씨드 투표)로 hand·meld·loose 를 고른 뒤 SeatFrame 으로 묶는다. 白 은 서버와 같은 row_blanks 로 채운다.
채점은 score.py 와 같다(정답 = seat_grow.scenes, B·C·D 는 ×2 → /37).

  python -I -X utf8 experiments/tile_classifier/server_bench/role_bench.py [--threads 2] [--ft-epochs 100]
결과 data/role/bench/role_bench.json, 그림 data/role/bench/<이름>.jpg(크롭 위 역할 색 + 규칙·모델 답)
"""
from __future__ import annotations

import argparse
import io
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "speed"))
sys.path.insert(0, str(HERE.parents[1] / "yolo"))
import importlib.util

import hybrid as hy  # noqa: E402

_spec = importlib.util.spec_from_file_location("server_bench_bench", HERE / "bench.py")  # speed/bench.py 와 이름이 겹친다
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)
import role_set as rs  # noqa: E402
import seat_grow as sg  # noqa: E402
from app import local_read as lr  # noqa: E402
from rules_core import rv, st, strays  # noqa: E402

OUT = HERE.parent / "data" / "role" / "bench"
HYBRID = False  # --hybrid
COLORS = {"hand": "blue", "meld": "cyan", "river": "orange", "wall": "red", "pair": "magenta", "loose": "yellow"}


def unrotate(b, rot: int, cw: int, ch: int) -> tuple:
    """자리 방향으로 세운 크롭(sg.crop: rotate(-rot, expand))의 상자 → 돌리기 전 크롭 좌표. cw·ch = 돌리기 전 크기."""
    x, y, w, h = b
    pts = [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]
    if rot == 90:  # 시계 90°: (x, y) → (ch - y, x) 의 역
        back = [(py, ch - px) for px, py in pts]
    elif rot == 180:
        back = [(cw - px, ch - py) for px, py in pts]
    elif rot == 270:  # 반시계 90°: (x, y) → (y, cw - x) 의 역
        back = [(cw - py, px) for px, py in pts]
    else:
        back = pts
    xs, ys = [p[0] for p in back], [p[1] for p in back]
    return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def _check_unrotate() -> None:
    a = np.arange(6 * 4).reshape(4, 6).astype(np.uint8)  # ch=4, cw=6
    for rot in (90, 180, 270):
        r = np.asarray(Image.fromarray(a).rotate(-rot, expand=True))
        for yy in range(r.shape[0]):
            for xx in range(r.shape[1]):
                x0, y0, _, _ = unrotate((xx, yy, 1, 1), rot, 6, 4)
                assert a[int(y0), int(x0)] == r[yy, xx], (rot, xx, yy)


_check_unrotate()


def to_full(boxes: list, s: dict, W: int, H: int) -> list:
    ymin, xmin, ymax, xmax = sg.seat_box(s["grid"], s["side"], 40)
    x0, y0 = round(xmin * W / 1000), round(ymin * H / 1000)
    cw, ch = round(xmax * W / 1000) - x0, round(ymax * H / 1000) - y0
    out = []
    for b in boxes:
        x, y, w, h = unrotate(b, sg.ROT_CW[s["side"]], cw, ch)
        out.append((x + x0, y + y0, w, h))
    return out


def model_frame(rgb: np.ndarray, faces: list, s: dict, nets: list, full_size: tuple, split: int) -> tuple[st.SeatFrame | None, list, list]:
    """역할 모델로 틀 잡기. (틀, 역할 목록, 채운 白 상자)."""
    if not faces:
        return None, [], []
    W, H = full_size
    full = to_full(faces, s, W, H)
    rec = dict(size=[W, H], side=s["side"], items=[dict(box=list(b), role="other") for b in full])
    x, y = rs.scene_tokens(rec, s["grid"], [], False)
    sc = dict(name=s["name"], x=x, y=y)
    votes = [rs.predict(n, sc) for n in nets]
    roles = [Counter(v[i][0] for v in votes).most_common(1)[0][0] for i in range(len(faces))]
    if HYBRID:  # 모델이 이 자리 것으로 고른 상자(손패·울기·떼어 둔 패)만 서버 규칙 split_frame 에 넣는다. 실패하면 아래 모델 틀로
        mine = [f for f, r in zip(faces, roles) if r in ("hand", "meld", "loose")]
        fr = lr.split_frame(rgb, mine, split) if len(mine) >= 2 else None
        if fr is not None and lr.frame_ok(fr, rgb):
            added: list = []
            if fr.count < 13:
                added = lr.row_blanks(rgb, faces, fr, split)
                if fr.count + len(added) in (13, 14):
                    fr.hand = sorted(fr.hand + [tuple(b) for b in added], key=lambda b: b[0])
                else:
                    added = []
            return fr, roles, added
    up = [f for f in faces if f[3] > f[2]] or faces
    tw, th = statistics.median(f[2] for f in up), statistics.median(f[3] for f in up)
    hand = sorted([f for f, r in zip(faces, roles) if r == "hand"], key=lambda b: b[0])
    if len(hand) < 2:
        return None, roles, []
    a, c = lr._line(hand)
    loose = [f for f, r in zip(faces, roles) if r == "loose"]
    hx1 = hand[-1][0] + hand[-1][2]
    near = [f for f in loose if abs(f[1] + f[3] / 2 - (a * (f[0] + f[2] / 2) + c)) < th and 0 < f[0] - hx1 < st.SEP_DIST * tw]
    sep = near[0] if len(near) == 1 else None
    melds = []
    for g in st.cluster([f for f, r in zip(faces, roles) if r == "meld"], tw * st.GAP, th * 0.5):
        g = sorted(g, key=lambda b: b[0])
        if len(g) in (3, 4):
            melds.append(g)
        elif len(g) in st.SPLIT_MELD:  # 붙어 놓인 울기 둘: 위아래 두 줄이면 y 로, 아니면 x 로 나눈다(local_read.split_frame 과 같게)
            k = st.SPLIT_MELD[len(g)][0]
            by_y = sorted(g, key=lambda b: b[1] + b[3] / 2)
            if by_y[k][1] + by_y[k][3] / 2 - (by_y[k - 1][1] + by_y[k - 1][3] / 2) > 0.4 * th:
                melds += [sorted(by_y[:k], key=lambda b: b[0]), sorted(by_y[k:], key=lambda b: b[0])]
            else:
                melds += [g[:k], g[k:]]
    melds.sort(key=lambda m: m[0][0])
    fr = st.SeatFrame(hand, sep, melds, [f for f in loose if f is not sep], tw, th, len(faces), split=True)
    added: list = []
    if fr.count < 13:  # 서버 fill 과 같은 白 채우기(손패 줄 틈·양 끝의 무늬 없는 흰 칸)
        added = lr.row_blanks(rgb, faces, fr, split)
        if fr.count + len(added) in (13, 14):
            fr.hand = sorted(fr.hand + [tuple(b) for b in added], key=lambda b: b[0])
        else:
            added = []
    return fr, roles, added


def read_frame(fr: st.SeatFrame, rgb: np.ndarray, faces: list, cls, added: list) -> dict:
    filled = set(map(tuple, added))
    hand = ["5z" if tuple(b) in filled else cls.read([bench.cut(rgb, b)])[0] for b in fr.hand] + ([cls.read([bench.cut(rgb, fr.separate)])[0]] if fr.separate else [])
    melds = [" ".join(bench.read_meld_tile(cls, rgb, b) for b in m) for m in fr.melds]
    block = False
    if fr.count == 13 and not fr.separate:
        got = strays(fr, faces, rgb)
        if len(got) == 1:
            hand.append(bench.read_turned(cls, rgb, got[0], fr.tw, fr.th))
        elif got:
            block = True
    return dict(framed=True, hand=hand, melds=melds, block=block)


def judge(r: dict, s: dict) -> tuple[bool, bool]:
    key = lambda melds: sorted(" ".join(sorted(m.split())) for m in melds)
    ok = bool(r["hand"]) and sorted(r["hand"]) == sorted(s["hand"]) and key(r["melds"]) == key(s["melds"])
    auto = bool(r["hand"]) and not r["block"] and hy.check(r["hand"], [m.split() for m in r["melds"]])[0]
    return ok, auto


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--ft-epochs", type=int, default=100)
    ap.add_argument("--hybrid", action="store_true", help="모델이 고른 상자만 서버 규칙 split_frame 에 넣기")
    a = ap.parse_args()
    global HYBRID
    HYBRID = a.hybrid
    sys.stdout.reconfigure(encoding="utf-8")
    torch.set_num_threads(8)
    OUT.mkdir(parents=True, exist_ok=True)
    meta = json.loads((HERE / "meta.json").read_text(encoding="utf-8"))
    scenes = {s["name"]: s for s in sg.scenes()}
    # 역할 모델: 뒷면 없는 합성 사전학습 → 실제 25장 전부로 미세 조정(가중치 캐시)
    ckpt = rs.OUT / "role_nbc_all.pt"  # 뒷면 없음 + 자리 크롭 범위
    if ckpt.exists():
        nets = []
        for sd in torch.load(ckpt):
            n = rs.SetNet()
            n.load_state_dict(sd)
            nets.append(n.eval())
    else:
        labels = json.loads((rs.OUT / "labels.json").read_text(encoding="utf-8"))
        tr = []
        for name, rec in labels.items():
            x, y = rs.scene_tokens(rec, scenes[name]["grid"], [], False)
            x, y = rs.crop_filter(x, y)  # 서버가 보는 자리 크롭 범위만
            tr.append(dict(name=name, x=x, y=y))
        pre = []
        for sd in torch.load(rs.OUT / "pre_synth8k_nbc2.pt"):
            n = rs.SetNet()
            n.load_state_dict(sd)
            pre.append(n.eval())
        nets = [rs.train(tr, a.ft_epochs, seed, pre[seed], 3e-4) for seed in range(len(pre))]
        torch.save([n.state_dict() for n in nets], ckpt)
    print("역할 모델", len(nets), "벌", flush=True)
    dets, clss = {}, {}
    rows = {}
    tot = Counter()
    for p in meta["photos"]:
        s = scenes[p["name"]]
        if s["hand"] is None or p["name"] in sg.EXCLUDED:  # 가림·사용자 문제 사진은 채점에서 뺌(학습엔 씀)
            continue
        w = 2 if not p["name"].startswith("2026") else 1
        det = dets.setdefault(p["det"], bench.Det(HERE / "models" / f"det_fold_{p['det']}.onnx", a.threads))
        cls = clss.setdefault(p["part"], bench.Cls(HERE / "models" / f"cls_{p['part']}.onnx", meta, a.threads))
        jpeg = (HERE / "crops" / f"{p['name']}.jpg").read_bytes()
        det.memo = {}
        rule = bench.one(jpeg, det, cls, p["frac"])
        rgb = np.asarray(Image.open(io.BytesIO(jpeg)).convert("RGB"))
        faces = rv.dedupe(rv.keep_faces(det.detect(rgb), rv.white_mask(rgb)))
        full_size = Image.open(s["path"]).size
        t0 = time.perf_counter()
        fr, roles, added = model_frame(rgb, faces, s, nets, full_size, int(rgb.shape[1] * p["frac"]))
        t_frame = time.perf_counter() - t0
        model = read_frame(fr, rgb, faces, cls, added) if fr is not None else dict(framed=False, hand=[], melds=[], block=False)
        model["frame_ms"] = round(t_frame * 1000)
        model["filled"] = len(added)
        r_ok, r_auto = judge(rule, s)
        m_ok, m_auto = judge(model, s)
        rows[p["name"]] = dict(w=w, rule=dict(rule, ok=r_ok, auto=r_auto), model=dict(model, ok=m_ok, auto=m_auto, roles=roles))
        for k, v in (("rule_ok", r_ok), ("rule_auto", r_auto), ("rule_bad", r_auto and not r_ok), ("model_ok", m_ok), ("model_auto", m_auto), ("model_bad", m_auto and not m_ok),
                     ("rule_framed", rule["framed"]), ("model_framed", model["framed"])):
            tot[k] += w * v
        tot["n"] += w
        print(p["name"][-6:], s["side"], f"규칙 {'O' if r_ok else 'X'} {' '.join(rule['hand'])} {rule['melds']} | 모델 {'O' if m_ok else 'X'} {' '.join(model['hand'])} {model['melds']} 白{len(added)} {model['frame_ms']}ms", flush=True)
        im = Image.fromarray(rgb)
        d = ImageDraw.Draw(im)
        for f, r in zip(faces, roles):
            d.rectangle((f[0], f[1], f[0] + f[2], f[1] + f[3]), outline=COLORS.get(r, "gray"), width=5)
        for b in added:
            d.rectangle((b[0], b[1], b[0] + b[2], b[1] + b[3]), outline="white", width=5)
        d.text((10, 10), f"rule {'O' if r_ok else 'X'} / model {'O' if m_ok else 'X'}", fill="red")
        im.save(OUT / f"{p['name']}.jpg", quality=80)
    print(f"--- 정답(가중, B·C·D ×2) /{tot['n']}: 규칙 {tot['rule_ok']} 모델 {tot['model_ok']} | 자동 반영 규칙 {tot['rule_auto']}(틀림 {tot['rule_bad']}) 모델 {tot['model_auto']}(틀림 {tot['model_bad']}) | 틀 규칙 {tot['rule_framed']} 모델 {tot['model_framed']}")
    (OUT / f"role_bench{'_hybrid' if HYBRID else ''}.json").write_text(json.dumps(dict(total=dict(tot), rows=rows), ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
