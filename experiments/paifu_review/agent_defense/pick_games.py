"""수비 질문 평가에 쓸 천봉 국 8개 고르기(본 판 4 · 안 본 판 4) → 사실표 만들기. 설계서 docs/paifu_review_agent_defense_design_1122.md 3 · 5절.

  python -X utf8 experiments/paifu_review/agent_defense/pick_games.py        (저장소 뿌리에서)

고르는 규칙(답을 보기 전에 고정, 2026-11-22):
- 후보 = results/agent_defense/candidates.json 중 hero 가 그 국에서 리치하지 않았고(n_forced 0) 남이 리치한 뒤 hero 버림이 4 ~ 8번.
- 두 묶음: A = 고른 패로 방총한 국(dealt_on_choice), B = 안 쏘였고 그 버림들 중 2샹텐 이상인 차례가 있는 국.
- random.Random(20261122) 로 각 묶음을 섞어, 판이 겹치지 않게 본 판 A 2 · B 2, 이어서 안 본 판 A 2 · B 2.
- 사실표는 tool/tenhou6_agent_facts.dart 로. 파일 이름은 익명(ds1..ds4 본 판, du1..du4 안 본 판), 판 ID 는 picked.json 에만.
  덧붙인 묶음(같은 씨 · 같은 규칙의 다음 차례, 앞 묶음은 그대로): dv · dw(안 본 판 2 · 3), dx(안 본 판 4 — 앱 질문 창 3단계).
  후보가 모자라면 사실표 · picked.json 을 쓰기 전에 멈춘다.
검증 40판(개발 판)만 쓴다 — 로그는 mxfit/split.log_path 로 연다.
"""
import json
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'mxfit'))
import split  # noqa: E402

RES = os.path.join(os.path.dirname(HERE), 'results', 'agent_defense')
FACTS = os.path.join(RES, 'facts')
DART = r'C:\Users\jjh7757\flutter\bin\dart.bat'


def main():
    cands = json.load(open(os.path.join(RES, 'candidates.json'), encoding='utf-8'))['candidates']
    base = sorted((c for c in cands if c['n_forced'] == 0 and 4 <= c['n_discards'] <= 8 and not c['kan']),
                  key=lambda c: (c['game'], c['kyoku'], c['seat']))
    a = [c for c in base if c['dealt_on_choice']]
    b = [c for c in base if not c['dealt_in'] and max(c['shanten']) >= 2]
    rng = random.Random(20261122)
    rng.shuffle(a)
    rng.shuffle(b)
    print(f'후보 {len(base)} · A(고른 패로 방총) {len(a)} · B(안 쏘임 · 2샹텐 이상 차례 있음) {len(b)}')
    used, picked = set(), []
    ia = ib = 0
    # dv = a4 재기용, dw = a5 재기용 새 안 본 판(11-22 덧붙임, 같은 씨 · 같은 규칙에서 다음 차례 국들 — 앞의 것은 그대로).
    # dx = 앱 질문 창 3단계 A 묶음용 새 안 본 판(11-22 덧붙임, 설계서 docs/paifu_review_agent_app_design_1122.md 6절 — 앞의 것은 그대로).
    sets = {'ds': 'seen', 'du': 'unseen', 'dv': 'unseen2', 'dw': 'unseen3', 'dx': 'unseen4'}
    for label in sets:
        n = 0
        for pool, name in ((a, 'A'), (b, 'B')):
            got = 0
            idx = ia if name == 'A' else ib
            while got < 2:
                if idx >= len(pool):
                    sys.exit(f'{label} 묶음 {name} 후보가 모자람(남은 후보 없음, {name} {len(pool)}개 중 {got}개만 고름)')
                c = pool[idx]
                idx += 1
                if c['game'] in used:
                    continue
                used.add(c['game'])
                n += 1
                picked.append(dict(c, id=f'{label}{n}', group=name, set=sets[label]))
                got += 1
            if name == 'A':
                ia = idx
            else:
                ib = idx
    os.makedirs(FACTS, exist_ok=True)
    for p in picked:
        out = os.path.join(FACTS, f"{p['id']}.json")
        r = subprocess.run([DART, 'run', 'tool/tenhou6_agent_facts.dart', str(split.log_path(p['game'])), str(p['kyoku']), str(p['seat']), out],
                           cwd=ROOT, capture_output=True)
        if r.returncode != 0 or not os.path.exists(out):
            sys.exit(f"{p['id']} 사실표 실패: " + (r.stderr.decode('utf-8', 'replace')[-600:]))
        print(p['id'], p['set'], p['group'], '버림', p['n_discards'], '샹텐', p['shanten'], '방총' if p['dealt_in'] else '안 쏘임', '·', os.path.getsize(out), 'B')
    open(os.path.join(RES, 'picked.json'), 'wb').write(json.dumps(picked, ensure_ascii=False, indent=1).encode('utf-8'))


if __name__ == '__main__':
    main()
