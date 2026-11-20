# 독립 검토용 무작위 손 생성기(시드 고정). Dart·Go 양쪽 입력을 따로 계산해 둔다.
import json, random, sys

SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 20261120
N = int(sys.argv[2]) if len(sys.argv) > 2 else 260
OUT = sys.argv[3] if len(sys.argv) > 3 else 'hands.json'
MODE = sys.argv[4] if len(sys.argv) > 4 else 'mix'
rng = random.Random(SEED)

def dora_of(ind):
    if ind < 27:
        return ind - ind % 9 + (ind % 9 + 1) % 9
    if ind < 31:
        return 27 + (ind - 27 + 1) % 4
    return 31 + (ind - 31 + 1) % 3

def take(wall, t):
    if wall[t] <= 0:
        return False
    wall[t] -= 1
    return True

def rand_from(wall):
    pool = [t for t in range(34) for _ in range(wall[t])]
    return rng.choice(pool)

def make_case(idx):
    wall = [4] * 34
    r = rng.random()
    nm = 0 if r < (0.4 if MODE=='tenpai' else 0.55) else (1 if r < 0.8 else 2)
    melds = []
    meld_tiles = []
    for _ in range(nm):
        for _try in range(50):
            typ = rng.choices(['chi', 'pon', 'ankan', 'minkan'], [5, 4, 1, 1])[0]
            if typ == 'chi':
                s = rng.randrange(3); n = rng.randrange(7); t0 = s * 9 + n
                ts = [t0, t0 + 1, t0 + 2]
            else:
                t0 = rng.randrange(27,34) if (MODE=='yaku' and rng.random()<0.5) else rng.randrange(34)
                ts = [t0] * (3 if typ == 'pon' else 4)
            need = {}
            for t in ts: need[t] = need.get(t, 0) + 1
            if all(wall[t] >= c for t, c in need.items()):
                for t in ts: wall[t] -= 1
                melds.append({'type': typ, 'tiles': ts})
                meld_tiles += ts
                break
    ncl = 14 - 3 * len(melds)
    # 구조 손: 몸통+머리를 만들고 k 장을 무작위로 바꿔 샹텐을 섞는다
    hand = []
    if MODE == 'yaku':
        k = rng.choices([0, 1], [3, 2])[0]
    elif MODE == 'tenpai':
        k = rng.choices([0, 1, 2], [2, 6, 1])[0]
    elif MODE == 'deep':
        k = rng.choices([2, 3, 4, 5], [2, 4, 3, 1])[0]
    else:
        k = rng.choices([0, 1, 2, 3, 4, 6, 14], [6, 25, 25, 20, 12, 6, 6])[0]
    bodies = (ncl - 2) // 3
    tries = 0
    while len(hand) < ncl and tries < 500:
        tries += 1
        hand = []
        w2 = wall[:]
        ok = True
        # 색 편중(혼일 등)이 가끔 나오게
        suit_bias = rng.random() < 0.2
        bsuit = rng.randrange(4)
        for _ in range(bodies):
            if rng.random() < 0.65:
                s = bsuit if (suit_bias and bsuit < 3 and rng.random() < 0.8) else rng.randrange(3)
                n = rng.randrange(7); t0 = s * 9 + n; ts = [t0, t0 + 1, t0 + 2]
            else:
                t0 = (bsuit * 9 + rng.randrange(9)) if (suit_bias and bsuit < 3 and rng.random() < 0.8) else (rng.randrange(27,34) if (MODE=='yaku' and rng.random()<0.5) else rng.randrange(34))
                ts = [t0] * 3
            for t in ts:
                if not take(w2, t): ok = False
            hand += ts
        t0 = rng.randrange(27,34) if (MODE=='yaku' and rng.random()<0.5) else rng.randrange(34)
        for t in [t0, t0]:
            if not take(w2, t): ok = False
        hand += [t0, t0]
        if not ok or len(hand) != ncl:
            hand = []; continue
        # k 장 바꾸기
        rng.shuffle(hand)
        kk = min(k, ncl)
        for i in range(kk):
            w2[hand[i]] += 1
            hand[i] = rand_from(w2)
            w2[hand[i]] -= 1
        wall = w2
    hand34 = [0] * 34
    for t in hand: hand34[t] += 1
    # 도라 표시패
    nind = rng.choices([0, 1, 2, 3], [1, 6, 2, 1])[0]
    inds = []
    for _ in range(nind):
        t = rand_from(wall); wall[t] -= 1; inds.append(t)
    # 자기 버림, 다른 보이는 패
    nd = rng.choices([0, 3, 6, 9, 12, 15], [3, 4, 4, 3, 2, 1])[0] if MODE!='yaku' else rng.choice([0,0,1,2,3])
    discards = []
    for _ in range(nd):
        t = rand_from(wall); wall[t] -= 1; discards.append(t)
    nv = rng.choices([0, 10, 25, 45], [3, 4, 3, 2])[0]
    other = []
    for _ in range(nv):
        t = rand_from(wall); wall[t] -= 1; other.append(t)
    visible34 = [0] * 34
    for t in meld_tiles + inds + discards + other: visible34[t] += 1
    # 적5: 손패/울기의 5 가운데 각 수트 0~1장
    red = [0, 0, 0]
    for s in range(3):
        f = s * 9 + 4
        have = hand34[f] + meld_tiles.count(f)
        if have > 0 and rng.random() < 0.5:
            red[s] = 1
    rw = rng.choice([27, 27, 28])
    if MODE == 'tenpai' and rng.random() < 0.3:
        # 바람 패 머리/몸통이 많게
        pass
    sw = rng.choice([27, 28, 29, 30])
    if MODE=='yaku' and rng.random()<0.4: sw = rw
    parent = sw == 27
    left34 = [max(0, min(4, 4 - hand34[t] - visible34[t])) for t in range(34)]
    return {
        'id': f'r{idx:03d}',
        'k': k,
        'dart': {'hand34': hand34, 'melds': melds, 'visible34': visible34,
                 'dora_indicators': inds, 'red_fives': red, 'discards': discards,
                 'round_wind': rw, 'seat_wind': sw, 'is_dealer': parent},
        'input': {'hand34': hand34, 'melds': melds, 'dora_tiles': [dora_of(i) for i in inds],
                  'red_fives': red, 'left34': left34, 'discards': discards,
                  'round_wind': rw, 'self_wind': sw, 'is_parent': parent},
    }

cases = [make_case(i) for i in range(N)]
json.dump({'seed': SEED, 'cases': cases}, open(OUT, 'w', encoding='utf-8'))
print('cases', len(cases))
