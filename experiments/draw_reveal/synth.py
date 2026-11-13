"""유국 공개 장면 합성(2026-11-13, 사용자 "합성으로 만들어줄래?"). API 없음.

평가 장면 40장(seat_grow.eval_scenes → scenes.json, 테스트 세트 B·C·D + 10-31 + 11-07 원본, 가림·사용자 문제 제외)은 모두 화료 사진이라
화료자 한 자리만 손패가 앞면이다. 유국 때는 텐파이한 자리만 손패를 앞으로 눕혀 공개하고 노텐은 세워 둔다. 이를 흉내 낸다.

- 패 상자: 앞면 = data/det/boxes_final.json, 뒷면 = data/det/backs/boxes.json(세운 손패는 한 장 한 상자).
  화료자 손패 = 역할 라벨 v2(labels_v2.json)의 hand·winner 상자, 라벨 없는 9장은 화료자 손패 칸 안의 앞면 상자.
  다른 자리 세운 손패 = 그 자리 손패 칸 안 뒷면 상자 중 바깥(그 사람 쪽) 끝에서 패 한 장 깊이 안에 드는 줄(패산은 더 안쪽).
- 공개(텐파이): 그 자리 세운 손패 자리를 펠트로 지우고, 같은 사진 화료자의 손패 줄을 90°씩 돌려 패 폭을 맞춰 붙인다.
  바깥 끝을 원래 손패 바깥 끝에 맞춰 가운데 쪽으로 눕힌 모양.
- 숨김(노텐): 화료자 손패를 펠트로 지우고, 다른 자리의 세운 손패 줄을 돌려 붙인다. 울기(손패 칸 밖·역할 meld)는 그대로.
- 펠트로 지우기 = 둘레 펠트 화소의 평균·표준편차로 채우고 살짝 흐림(inpaint 는 옆 흰 패를 끌어와 얼룩, 11-08 메모).
- 장면마다 6가지(텐파이 없음 / 화료자만(원본과 같은 공개) / 다른 한 자리 / 두 자리 / 세 자리 / 네 자리), 씨드 고정.
- 출력 out/<이름>__<자리 머리글자>.jpg(긴 변 2040), manifest.json(장면·격자·정답 텐파이 자리), sheet_*.jpg 눈 검수용.
  python -I -X utf8 experiments/draw_reveal/synth.py
"""
import json
import random
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
DET = HERE.parent / "tile_classifier" / "data" / "det"
ROLE = HERE.parent / "tile_classifier" / "data" / "role" / "v2" / "labels_v2.json"
OUT = HERE / "out"
SIDES = ["bottom", "right", "top", "left"]
LONG = 2040


def hand_cell_px(g, side, W, H):
    y0, x0, y1, x1 = {"bottom": (g["y2"], g["x1"], 1000, g["x2"]), "right": (g["y1"], g["x2"], g["y2"], 1000),
                      "top": (0, g["x1"], g["y1"], g["x2"]), "left": (g["y1"], 0, g["y2"], g["x1"])}[side]
    return x0 * W / 1000, y0 * H / 1000, x1 * W / 1000, y1 * H / 1000


def center(b):
    return b[0] + b[2] / 2, b[1] + b[3] / 2


def inside(b, c):
    x, y = center(b)
    return c[0] <= x <= c[2] and c[1] <= y <= c[3]


def outer_coord(b, side):
    """그 사람 쪽(사진 가장자리 쪽) 끝 좌표 — 클수록 바깥."""
    x, y, w, h = b
    return {"bottom": y + h, "top": -y, "right": x + w, "left": -x}[side]


def along_w(b, side):  # 줄 방향 패 폭
    return b[2] if side in ("bottom", "top") else b[3]


def union(bs, pad=0):
    x0 = min(b[0] for b in bs) - pad
    y0 = min(b[1] for b in bs) - pad
    x1 = max(b[0] + b[2] for b in bs) + pad
    y1 = max(b[1] + b[3] for b in bs) + pad
    return [int(x0), int(y0), int(x1), int(y1)]


def standing_row(backs, side, cell):
    bs = [b for b in backs if inside(b, cell)]
    if len(bs) < 4:
        return []
    depth = np.median([b[3] if side in ("bottom", "top") else b[2] for b in bs])
    top = max(outer_coord(b, side) for b in bs)
    row = [b for b in bs if outer_coord(b, side) >= top - 0.9 * depth]
    return row if len(row) >= 4 else []


def green_mask(im):
    b, g, r = [im[..., i].astype(np.int16) for i in range(3)]
    return (g > r + 20) & (g > b)


def erase(im, rect, green):
    x0, y0, x1, y1 = rect
    H, W = im.shape[:2]
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
    m = 40
    X0, Y0, X1, Y1 = max(0, x0 - m), max(0, y0 - m), min(W, x1 + m), min(H, y1 + m)
    ring = np.zeros((H, W), bool)
    ring[Y0:Y1, X0:X1] = True
    ring[y0:y1, x0:x1] = False
    ring &= green
    px = im[ring].astype(np.float32)
    if len(px) < 50:
        px = im[green].astype(np.float32)
    mu, sd = px.mean(0), px.std(0) * 0.5
    rng = np.random.default_rng(0)
    fill = rng.normal(mu, sd, (y1 - y0, x1 - x0, 3)).clip(0, 255).astype(np.uint8)
    fill = cv2.GaussianBlur(fill, (5, 5), 0)
    im[y0:y1, x0:x1] = fill
    # 테두리 섞기
    a = np.zeros((H, W), np.float32)
    a[y0:y1, x0:x1] = 1
    a = cv2.GaussianBlur(a, (0, 0), 3)
    return im, (x0, y0, x1, y1)


def rot_steps(src, dst):
    return (SIDES.index(dst) - SIDES.index(src)) % 4


def rotate(img, k):
    for _ in range(k):
        img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return img


def paste_strip(im, strip, smask, side, anchor_rect, tile_w_src, tile_w_dst):
    """strip(이미 dst 방향으로 돌림)을 패 폭 비율로 키워 anchor_rect 의 바깥 끝·줄 가운데에 맞춰 smask 화소만 붙인다."""
    s = tile_w_dst / tile_w_src
    strip = cv2.resize(strip, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    smask = cv2.resize(smask.astype(np.uint8), (strip.shape[1], strip.shape[0]), interpolation=cv2.INTER_NEAREST).astype(bool)
    h, w = strip.shape[:2]
    x0, y0, x1, y1 = anchor_rect
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if side == "bottom":
        X, Y = cx - w / 2, y1 - h
    elif side == "top":
        X, Y = cx - w / 2, y0
    elif side == "right":
        X, Y = x1 - w, cy - h / 2
    else:
        X, Y = x0, cy - h / 2
    X, Y = int(round(X)), int(round(Y))
    H, W = im.shape[:2]
    ax0, ay0, ax1, ay1 = max(0, X), max(0, Y), min(W, X + w), min(H, Y + h)
    if ax1 <= ax0 or ay1 <= ay0:
        return
    sub = strip[ay0 - Y:ay1 - Y, ax0 - X:ax1 - X]
    msk = smask[ay0 - Y:ay1 - Y, ax0 - X:ax1 - X]
    region = im[ay0:ay1, ax0:ax1]
    region[msk] = sub[msk]


def crop_strip(im, rect, green, boxes):
    """rect 를 오리고, 패 상자 안이면서 초록 아닌 화소만 마스크로(테두리·팔 등 상자 밖은 안 옮김)."""
    x0, y0, x1, y1 = rect
    c = im[y0:y1, x0:x1].copy()
    inb = np.zeros((y1 - y0, x1 - x0), bool)
    for bx, by, bw, bh in boxes:
        inb[max(0, int(by) - y0):max(0, int(by + bh) - y0), max(0, int(bx) - x0):max(0, int(bx + bw) - x0)] = True
    m = ~green[y0:y1, x0:x1] & inb
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)
    return c, m


def main():
    scenes = json.loads((HERE / "scenes.json").read_text(encoding="utf-8"))
    faces_all = json.loads((DET / "boxes_final.json").read_text(encoding="utf-8"))
    backs_all = json.loads((DET / "backs" / "boxes.json").read_text(encoding="utf-8"))
    roles = json.loads(ROLE.read_text(encoding="utf-8"))
    OUT.mkdir(exist_ok=True)
    rng = random.Random(1113)
    manifest, notes = [], {}
    for sc in scenes:
        name, win = sc["name"], sc["side"]
        im0 = cv2.imread(sc["path"])
        H, W = im0.shape[:2]
        g = sc["grid"]
        cells = {s: hand_cell_px(g, s, W, H) for s in SIDES}
        if name in roles:
            whand = [it["box"] for it in roles[name]["items"] if it["role"] == "hand" and it["owner"] == "winner"]
        else:
            fb = [b[:4] for b in faces_all[name]["boxes"]]
            whand = [b for b in fb if inside(b, cells[win])]
        backs = [b[:4] for b in (roles[name]["backs"] if name in roles else backs_all[name])]
        rows = {s: standing_row(backs, s, cells[s]) for s in SIDES if s != win}
        rows = {s: r for s, r in rows.items() if r}
        missing = [s for s in SIDES if s != win and s not in rows]
        notes[name] = dict(win_tiles=len(whand), rows={s: len(r) for s, r in rows.items()}, missing=missing)
        if len(whand) < 4 or missing:
            print("건너뜀", name, notes[name])
            continue
        green0 = green_mask(im0)
        wrect = union(whand, pad=6)
        wstrip, wmask = crop_strip(im0, wrect, green0, whand)
        wtile = float(np.median([along_w(b, win) for b in whand]))
        others = [s for s in SIDES if s != win]
        combos = [set(), {win}, {rng.choice(others)}, set(rng.sample(SIDES, 2)), set(rng.sample(SIDES, 3)), set(SIDES)]
        for tenpai in combos:
            im = im0.copy()
            green = green0
            for s in SIDES:
                if s == win:
                    if s in tenpai:
                        continue
                    # 노텐으로: 화료자 손패 지우고 세운 줄 붙이기(가장 긴 다른 자리 줄)
                    src = max(rows, key=lambda k: len(rows[k]))
                    srect = union(rows[src], pad=6)
                    st, sm = crop_strip(im0, srect, green0, rows[src])
                    k = rot_steps(src, s)
                    st, sm = rotate(st, k), rotate(sm.astype(np.uint8), k).astype(bool)
                    stile = float(np.median([along_w(b, src) for b in rows[src]]))
                    erase(im, wrect, green)
                    paste_strip(im, st, sm, s, wrect, stile, wtile)
                else:
                    if s not in tenpai:
                        continue
                    rrect = union(rows[s], pad=6)
                    dtile = float(np.median([along_w(b, s) for b in rows[s]]))
                    erase(im, rrect, green)
                    k = rot_steps(win, s)
                    st, sm = rotate(wstrip, k), rotate(wmask.astype(np.uint8), k).astype(bool)
                    paste_strip(im, st, sm, s, rrect, wtile, dtile)
            tag = "".join(s[0] for s in SIDES if s in tenpai) or "none"
            f = LONG / max(H, W)
            small = cv2.resize(im, (round(W * f), round(H * f)), interpolation=cv2.INTER_AREA)
            p = OUT / f"{name}__{tag}.jpg"
            cv2.imwrite(str(p), small, [cv2.IMWRITE_JPEG_QUALITY, 92])
            manifest.append(dict(file=str(p), scene=name, set=sc["set"], winner=win, tenpai=[s for s in SIDES if s in tenpai], grid=g))
    (HERE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    (HERE / "synth_notes.json").write_text(json.dumps(notes, ensure_ascii=False, indent=1), encoding="utf-8")
    # 눈 검수 그림: 장면마다 6장 한 줄
    by = {}
    for m in manifest:
        by.setdefault(m["scene"], []).append(m)
    names = list(by)
    for i in range(0, len(names), 7):
        rowsimg = []
        for n in names[i:i + 7]:
            ts = []
            for m in by[n]:
                t = cv2.resize(cv2.imread(m["file"]), (400, 300))
                cv2.putText(t, n[-6:] + " " + ("".join(x[0] for x in m["tenpai"]) or "none"), (6, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                ts.append(t)
            rowsimg.append(np.hstack(ts))
        cv2.imwrite(str(HERE / f"sheet_{i // 7}.jpg"), np.vstack(rowsimg), [cv2.IMWRITE_JPEG_QUALITY, 80])
    print("장면", len(by), "합성", len(manifest))


if __name__ == "__main__":
    main()
