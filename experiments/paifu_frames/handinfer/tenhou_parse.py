"""천봉 tenhou6 JSON → 리치 기록(계획서 docs/hand_infer_plan_1120.md 7절).

받은 파일(results/handinfer/tenhou_raw/logs/*.json)은 json.loads 로 데이터만 읽는다. 다시 돌리기:
    python -I -X utf8 experiments/paifu_frames/handinfer/tenhou_parse.py
→ results/handinfer/waitsuit/riichi_records.json, parse_stats.json

국마다 네 자리의 배패 · 뽑은 패(쯔모 줄) · 버린 패(60 = 쯔모기리, 'r' = 리치 선언) · 울기(c/p/m 은 쯔모 줄,
a/k 는 버림 줄) · 도라 표시패를 차례대로 재생해 손패를 따라간다. 리치 선언 버림 직후 그 자리의 손패(13장)가
텐파이인지 확인(아니면 파서 버그로 셈). 기록은 공개 부분(pub)과 숨은 부분(hid)으로 나눈다 —
추정 쪽은 pub 와 칸 관찰만 받는다.
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
RAW = os.path.join(ROOT, 'experiments', 'paifu_frames', 'results', 'handinfer', 'tenhou_raw', 'logs')
OUT = os.path.join(ROOT, 'experiments', 'paifu_frames', 'results', 'handinfer', 'waitsuit')
sys.path.insert(0, HERE)
from posinfer import fast_waits  # noqa: E402


def ttype(c):
    """tenhou 패 번호 → 34종(m 0-8, p 9-17, s 18-26, z 27-33). 적5(51/52/53) 는 5."""
    c = int(c)
    if c in (51, 52, 53):
        return (c - 51) * 9 + 4
    s, n = c // 10 - 1, c % 10
    assert 0 <= s <= 3 and 1 <= n <= (7 if s == 3 else 9), c
    return s * 9 + n - 1


def parse_call(s):
    """쯔모 줄의 울기 글자. 반환 (종류, 가져온 패 번호, 준 자리 상대(1=하가 2=대면 3=상가), 손에서 나간 패들)."""
    for ch in 'cpm':
        i = s.find(ch)
        if i >= 0:
            break
    else:
        raise ValueError('울기 글자 모름: ' + s)
    called = int(s[i + 1:i + 3])
    rest = s[:i] + s[i + 3:]
    others = [int(rest[x:x + 2]) for x in range(0, len(rest), 2)]
    if ch == 'c':
        rel = 3
    elif ch == 'p':
        rel = {0: 3, 2: 2, 4: 1}[i]
    else:
        rel = {0: 3, 2: 2, 6: 1}[i]
    return ch, called, rel, others


def parse_round(rnd, gid, ri):
    head = rnd[0]
    dealer = head[0] % 4
    dora_all = [ttype(x) for x in rnd[2]]
    hands = [list(rnd[4 + 3 * s]) for s in range(4)]
    takes = [rnd[5 + 3 * s] for s in range(4)]
    discs = [rnd[6 + 3 * s] for s in range(4)]
    haipai = [list(h) for h in hands]
    ti = [0] * 4
    di = [0] * 4
    melded = [False] * 4          # 울기(안깡 포함) 한 적 있는 자리
    river = []                    # (자리, 종류, 쯔모기리, 리치)
    meld_vis = []                 # 강에서 가져온 패 빼고 드러난 패
    nkan = 0
    riichi_done = [False] * 4
    seq = [[] for _ in range(4)]  # 자리마다 차례: draw(번호), disc(번호), tsumogiri, riichi
    recs, bad, kanr = [], [], []
    p = dealer
    need_draw = True
    last_draw = [None] * 4
    steps = 0
    while steps < 400:
        steps += 1
        if need_draw:
            if ti[p] >= len(takes[p]):
                break
            t = takes[p][ti[p]]
            if isinstance(t, str):
                raise ValueError(f'차례에 울기 글자 {t}')
            ti[p] += 1
            hands[p].append(t)
            last_draw[p] = t
        else:
            last_draw[p] = None
        if di[p] >= len(discs[p]):
            break
        d = discs[p][di[p]]
        di[p] += 1
        if isinstance(d, str) and ('a' in d or 'k' in d):
            ch = 'a' if 'a' in d else 'k'
            tiles = [int(d.replace(ch, '')[x:x + 2]) for x in range(0, len(d) - 1, 2)]
            if ch == 'a':
                for x in tiles:
                    hands[p].remove(x)
                meld_vis += [ttype(x) for x in tiles]
            else:
                i = d.find('k')
                added = int(d[i + 1:i + 3])
                hands[p].remove(added)
                meld_vis.append(ttype(added))
            melded[p] = True
            nkan += 1
            need_draw = True
            seq[p].append(dict(draw=last_draw[p], kan=d))
            continue
        if d == 0:                # 대명깡 뒤 자리 채움
            need_draw = True
            continue
        riichi = isinstance(d, str) and d.startswith('r')
        if riichi:
            d = int(d[1:])
        if d == 60:
            if last_draw[p] is None:
                raise ValueError('뽑지 않았는데 쯔모기리')
            tile, tsumo = last_draw[p], True
        else:
            tile, tsumo = int(d), False
        hands[p].remove(tile)
        river.append((p, ttype(tile), tsumo, riichi))
        seq[p].append(dict(draw=last_draw[p], disc=tile, tsumogiri=tsumo, riichi=riichi))
        if riichi:
            riichi_done[p] = True
            h = hands[p]
            cnt = [0] * 34
            for x in h:
                cnt[ttype(x)] += 1
            w = fast_waits(tuple(cnt)) if len(h) == 13 else ()
            ok = len(h) == 13 and bool(w)
            if melded[p]:
                kanr.append(dict(id=gid, round=ri, seat=p, n=len(h)))
            elif not ok:
                bad.append(dict(id=gid, round=ri, seat=p, n=len(h), melded=melded[p]))
            else:
                ndora = min(len(dora_all), 1 + nkan)
                own = [x for x in seq[p] if 'disc' in x]
                recs.append(dict(
                    id=gid, round=ri, kyoku=head, seat=p, dealer=dealer, melded=melded[p],
                    pub=dict(river=[list(r) for r in river], meld_vis=list(meld_vis), dora=dora_all[:ndora],
                             own=[[ttype(x['disc']), x['tsumogiri']] for x in own],
                             other_riichi=[s for s in range(4) if s != p and riichi_done[s]]),
                    hid=dict(haipai=haipai[p], turns=[[x['draw'], x['disc'], x['tsumogiri']] for x in own],
                             hand=sorted(h), waits=list(w))))
        # 울기 찾기(퐁 · 깡 먼저, 그다음 치)
        caller = None
        for q in sorted((x for x in range(4) if x != p), key=lambda x: 0 if x != (p + 1) % 4 else 1):
            if ti[q] < len(takes[q]) and isinstance(takes[q][ti[q]], str):
                ch, called, rel, others = parse_call(takes[q][ti[q]])
                if (q + rel) % 4 == p and called == tile:
                    caller = (q, ch, others)
                    break
        if caller:
            q, ch, others = caller
            ti[q] += 1
            for x in others:
                hands[q].remove(x)
            meld_vis += [ttype(x) for x in others]
            melded[q] = True
            if ch == 'm':
                nkan += 1
            p = q
            need_draw = False
        else:
            p = (p + 1) % 4
            need_draw = True
    return recs, bad, kanr


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    os.makedirs(OUT, exist_ok=True)
    raw = sys.argv[1] if len(sys.argv) > 1 else RAW
    files = sorted(glob.glob(os.path.join(raw, '*.json')))
    allrec, bad, errs, kans = [], [], [], []
    nround = 0
    for fp in files:
        gid = os.path.basename(fp)[:-5]
        j = json.loads(open(fp, 'rb').read().decode('utf-8'))
        for ri, rnd in enumerate(j['log']):
            nround += 1
            try:
                r, b, k = parse_round(rnd, gid, ri)
                allrec += r
                bad += b
                kans += k
            except Exception as ex:  # noqa
                errs.append(dict(id=gid, round=ri, err=repr(ex)[:200]))
    stats = dict(games=len(files), rounds=nround, riichi_tenpai_ok=len(allrec), riichi_not_tenpai=len(bad),
                 round_errors=len(errs), riichi_with_kan_before=len(kans), bad=bad[:20], errs=errs[:20])
    print(json.dumps({k: v for k, v in stats.items() if k not in ('bad', 'errs')}, ensure_ascii=False))
    if bad:
        print('텐파이 아님(파서 버그 의심) 예:', bad[:5])
    if errs:
        print('국 재생 오류 예:', errs[:5])
    json.dump(allrec, open(os.path.join(OUT, 'riichi_records.json'), 'w', encoding='utf-8'))
    json.dump(stats, open(os.path.join(OUT, 'parse_stats.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
