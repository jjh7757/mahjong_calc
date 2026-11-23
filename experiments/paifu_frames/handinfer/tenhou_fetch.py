"""천봉(tenhou.net) 공개 패보 내려받기 — 계획서 docs/hand_infer_plan_1120.md 7절.

공식 목록만 쓴다: https://tenhou.net/sc/raw/list.cgi?old (연도 폴더의 일별 목록 이름) →
https://tenhou.net/sc/raw/dat/<연>/scc<날짜>.html.gz (鳳凰卓 일별 목록) → 四鳳南喰赤 줄의 로그 ID →
ID 순 정렬 · 고정 씨로 1,000판 → https://tenhou.net/5/mjlog2json.cgi?<ID> (tenhou6 JSON).

- 요청은 순서대로 하나씩, 매 요청 사이 1초 쉼. User-Agent 는 일반 이름(개인정보 없음).
- 받은 파일은 OUT(새 빈 폴더)에 저장만 하고 데이터로만 읽는다(gzip 풀기 · json.loads · 정규식뿐, 실행 없음).
- 이어 받기: 이미 있는 파일은 건너뜀. 실패는 fail.json 에 적고 건너뜀.

다시 돌리기(저장소 뿌리에서):
    python -I experiments/paifu_frames/handinfer/tenhou_fetch.py lists     # 일별 목록 받기
    python -I experiments/paifu_frames/handinfer/tenhou_fetch.py pick      # ID 모아 1,000판 고르기 → picked.json
    python -I experiments/paifu_frames/handinfer/tenhou_fetch.py logs      # 고른 판 JSON 받기
"""
import gzip
import json
import os
import random
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
OUT = os.path.join(ROOT, 'experiments', 'paifu_frames', 'results', 'handinfer', 'tenhou_raw')
UA = 'Mozilla/5.0 (compatible; paifu-stats-script)'
YEAR = '2026'          # 목록에 있는 2026 년치(1-1 ~ 목록 끝) 鳳凰卓 일별 목록
N_PICK = 1000
SEED = 20261121
GAP = 1.0
ID_RE = re.compile(r'log=(\d{10}gm-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{8})')

_last = [0.0]


def get(url):
    wait = GAP - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    finally:
        _last[0] = time.time()


def cmd_lists():
    os.makedirs(os.path.join(OUT, 'lists'), exist_ok=True)
    lp = os.path.join(OUT, 'list_old.js')
    if not os.path.exists(lp):
        st, b = get('https://tenhou.net/sc/raw/list.cgi?old')
        with open(lp, 'wb') as f:
            f.write(b)
    txt = open(lp, 'rb').read().decode('utf-8', 'replace')
    names = sorted(set(re.findall(r"file:'(%s/scc%s\d{4}\.html\.gz)'" % (YEAR, YEAR), txt)))
    print(f'{YEAR} 鳳凰卓 일별 목록 {len(names)}개', flush=True)
    fail = []
    for i, n in enumerate(names):
        p = os.path.join(OUT, 'lists', os.path.basename(n))
        if os.path.exists(p):
            continue
        try:
            st, b = get('https://tenhou.net/sc/raw/dat/' + n)
            gzip.decompress(b)          # 내용 확인(풀리는지)만
            with open(p, 'wb') as f:
                f.write(b)
        except Exception as ex:  # noqa
            fail.append((n, repr(ex)))
        if i % 20 == 0:
            print(f'  목록 {i + 1}/{len(names)}', flush=True)
    print(f'목록 실패 {len(fail)}', fail[:5], flush=True)


def cmd_pick():
    ids = set()
    days = 0
    for fn in sorted(os.listdir(os.path.join(OUT, 'lists'))):
        txt = gzip.decompress(open(os.path.join(OUT, 'lists', fn), 'rb').read()).decode('utf-8', 'replace')
        days += 1
        for line in txt.splitlines():
            if '四鳳南喰赤' not in line:
                continue
            m = ID_RE.search(line)
            if m:
                ids.add(m.group(1))
    ids = sorted(ids)
    rng = random.Random(SEED)
    pick = sorted(rng.sample(ids, N_PICK))
    with open(os.path.join(OUT, 'picked.json'), 'w', encoding='utf-8') as f:
        json.dump(dict(year=YEAR, days=days, n_ids=len(ids), seed=SEED, picked=pick), f, indent=0)
    print(f'일별 목록 {days}개, 四鳳南喰赤 ID {len(ids)}개 → {N_PICK}판 고름(씨 {SEED})', flush=True)


def cmd_logs():
    d = json.load(open(os.path.join(OUT, 'picked.json'), encoding='utf-8'))
    os.makedirs(os.path.join(OUT, 'logs'), exist_ok=True)
    fp = os.path.join(OUT, 'fail.json')
    fail = json.load(open(fp, encoding='utf-8')) if os.path.exists(fp) else {}
    got = 0
    t0 = time.time()
    for i, lid in enumerate(d['picked']):
        p = os.path.join(OUT, 'logs', lid + '.json')
        if os.path.exists(p):
            got += 1
            continue
        err = None
        for attempt in range(2):
            try:
                st, b = get('https://tenhou.net/5/mjlog2json.cgi?' + lid)
                j = json.loads(b.decode('utf-8'))
                if not isinstance(j, dict) or 'log' not in j:
                    raise ValueError('log 없음')
                with open(p, 'wb') as f:
                    f.write(b)
                got += 1
                err = None
                fail.pop(lid, None)
                break
            except Exception as ex:  # noqa
                err = repr(ex)[:200]
                time.sleep(5)
        if err:
            fail[lid] = err
        if i % 25 == 0:
            print(f'  {i + 1}/{len(d["picked"])} 받음 {got} 실패 {len(fail)} ({time.time() - t0:.0f}s)', flush=True)
            json.dump(fail, open(fp, 'w', encoding='utf-8'), indent=0)
    json.dump(fail, open(fp, 'w', encoding='utf-8'), indent=0)
    print(f'끝: 받음 {got}/{len(d["picked"])}, 실패 {len(fail)}', flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    {'lists': cmd_lists, 'pick': cmd_pick, 'logs': cmd_logs}[sys.argv[1]]()
