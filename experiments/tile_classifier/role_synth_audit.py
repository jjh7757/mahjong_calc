"""합성 배치(role_synth, feat rot)와 실제 25장(labels.json)의 상자 분포 비교 (2026-11-08).

폭·폭 흩어짐·누운 상자·5° 넘게 기운 앞면·겹침(축 상자 근사 IoU>0.15)과, 합성에서 어떤 역할끼리 겹치는지.
python -I -X utf8 experiments/tile_classifier/role_synth_audit.py          # 지금 생성기(v2)
ROLE_SYNTH_V1=1 python -I -X utf8 experiments/tile_classifier/role_synth_audit.py   # 11-08 이전 생성기
"""
import sys, json, numpy as np
from collections import Counter
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import role_set as rs, role_synth as syn
labels = json.loads((rs.OUT / rs.LABELS).read_text(encoding='utf-8'))
backs = json.loads(rs.BACKS.read_text(encoding='utf-8'))
rects_all = json.loads(rs.RECTS.read_text(encoding='utf-8'))
grids = {s['name']: s['grid'] for s in rs.sg.scenes()}
real = []
for name, rec in labels.items():
    x, y = rs.scene_tokens(rec, grids[name], backs.get(name, []), True, 'rot', rs.scene_rects(name, rects_all))
    real.append((x, np.array(y)))
rng = np.random.default_rng(7)
synth = [syn.make(rng, 'rot') for _ in range(300)]
def stats(sc, tag):
    tw, cv, land, over, tilt = [], [], {}, [], []
    for x, y in sc:
        w, h = x[:, 2] / 10, x[:, 3] / 10
        face = x[:, 4] == 0
        up = face & (x[:, 5] == 0)
        if up.sum() > 3:
            tw.append(np.median(np.minimum(w[up], h[up])))
            ww = np.minimum(w[up], h[up]); cv.append(ww.std() / ww.mean())
        for name, m in (('강', (y == 2)), ('손패', (y == 0)), ('뒷면', (x[:, 4] == 1))):
            if m.sum(): land.setdefault(name, []).append(x[m, 5].mean())
        ang = np.degrees(np.arctan2(x[:, 9], x[:, 10]) / 2)
        tilt.append(np.mean(np.abs(ang[face]) > 5))
        # 겹침: 축 상자 근사로 다른 상자와 IoU>0.15
        b = np.stack([x[:, 0] - w / 2, x[:, 1] - h / 2, x[:, 0] + w / 2, x[:, 1] + h / 2], 1)
        n = len(b); cnt = 0
        for i in range(n):
            ix = np.clip(np.minimum(b[i, 2], b[:, 2]) - np.maximum(b[i, 0], b[:, 0]), 0, None)
            iy = np.clip(np.minimum(b[i, 3], b[:, 3]) - np.maximum(b[i, 1], b[:, 1]), 0, None)
            inter = ix * iy; uni = w[i] * h[i] + w * h - inter
            iou = inter / uni; iou[i] = 0
            cnt += iou.max() > 0.15
        over.append(cnt / n)
    print(f'[{tag}] 장면 {len(sc)}')
    print(f'  앞면 패 폭(펠트 폭 기준) 중앙 {np.median(tw):.4f}  장면 안 폭 흩어짐(변동계수) 중앙 {np.median(cv):.3f}')
    print('  누운 상자 비율 ' + ', '.join(f'{k} {np.mean(v):.1%}' for k, v in land.items()))
    print(f'  5° 넘게 기운 앞면 비율 {np.mean(tilt):.1%}')
    print(f'  다른 상자와 IoU>0.15 로 겹친 상자 비율 {np.mean(over):.1%}')
stats(real, '실제 25장')
stats(synth, "합성 300장 " + ("v1(ROLE_SYNTH_V1=1)" if syn.V1 else "v2"))

# --- 합성에서 겹친 역할 쌍
N = {-1: '역할없음(뒷면·남의 패)', 0: '손패', 1: '울기', 2: '강', 3: '표시패', 4: '짝', 5: '떼어둔패'}
rng = np.random.default_rng(7); c = Counter(); tot = 0; dup = 0
for _ in range(300):
    x, y = syn.make(rng, 'rot'); w, h = x[:, 2] / 10, x[:, 3] / 10
    b = np.stack([x[:, 0] - w / 2, x[:, 1] - h / 2, x[:, 0] + w / 2, x[:, 1] + h / 2], 1); tot += len(b)
    for i in range(len(b)):
        ix = np.clip(np.minimum(b[i, 2], b[:, 2]) - np.maximum(b[i, 0], b[:, 0]), 0, None)
        iy = np.clip(np.minimum(b[i, 3], b[:, 3]) - np.maximum(b[i, 1], b[:, 1]), 0, None)
        inter = ix * iy; iou = inter / (w[i] * h[i] + w * h - inter); iou[i] = 0
        j = int(iou.argmax())
        if iou[j] > 0.15:
            if iou[j] > 0.8: dup += 1
            # 강끼리면 같은 자리 강인지(중심 거리로 근사 불가) — 쌍 이름만
            c[tuple(sorted((N[int(y[i])], N[int(y[j])])))] += 1
print('겹친 상자', sum(c.values()), '/', tot, f'({sum(c.values())/tot:.1%}), 거의 같은 상자(IoU>0.8, 중복 검출 흉내) {dup}')
for k, v in c.most_common(8): print(f'  {k[0]} + {k[1]}: {v} ({v/tot:.1%})')
