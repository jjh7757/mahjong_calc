"""picked.json 의 국에서 앱이 만들 질문 글을 낸다(설계서 docs/paifu_review_agent_app_design_1122.md 6절 3단계 A).

  python -X utf8 experiments/paifu_review/agent_defense/app_questions.py dx1 dx2 dx3 dx4      (저장소 뿌리에서)

id 마다 results/agent_defense/picked.json 에서 판 · 국 · 자리를 찾아(로그 경로는 pick_games.py 와 같이 mxfit/split.log_path)
tool/tenhou6_ask_questions.dart 를 돌려 results/agent_defense/app_questions/<id>.json 에 쓴다.
꼴: [{"turn": N|null, "kind": "suggested"|"typed", "q": "…"}] — 도구가 같은 판의 사실표(tenhouAgentFacts)와 대조한 뒤에만 낸다.
판마다 질문 수 · 추천 질문 갈래(차례 질문 = 글에 차례 번호가 있는 것, 판 전체 질문 = 없는 것)를 찍는다.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'mxfit'))
import split  # noqa: E402

RES = os.path.join(os.path.dirname(HERE), 'results', 'agent_defense')
OUT = os.path.join(RES, 'app_questions')
DART = r'C:\Users\jjh7757\flutter\bin\dart.bat'
# 서버 review_agent._QUESTION_TURN 과 같은 뜻(갈래 세기에만 씀).
TURN = re.compile(r'(\d+)\s?(?:순(?!위)|번째|차례|턴)')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ids = sys.argv[1:]
    if not ids:
        sys.exit('쓰는 법: python -X utf8 experiments/paifu_review/agent_defense/app_questions.py <id> [<id> …]')
    picked = {p['id']: p for p in json.load(open(os.path.join(RES, 'picked.json'), encoding='utf-8'))}
    missing = [i for i in ids if i not in picked]
    if missing:
        sys.exit(f'picked.json 에 없는 id: {missing}')
    os.makedirs(OUT, exist_ok=True)
    for i in ids:
        p = picked[i]
        out = os.path.join(OUT, f'{i}.json')
        r = subprocess.run([DART, 'run', 'tool/tenhou6_ask_questions.dart', str(split.log_path(p['game'])), str(p['kyoku']),
                            str(p['seat']), out], cwd=ROOT, capture_output=True)
        if r.returncode != 0 or not os.path.exists(out):
            sys.exit(f'{i} 질문 만들기 실패(종료 코드 {r.returncode}): ' + r.stderr.decode('utf-8', 'replace')[-600:])
        qs = json.load(open(out, encoding='utf-8'))
        sug = [q for q in qs if q['kind'] == 'suggested']
        turn_q = [q for q in sug if TURN.search(q['q'])]
        typed = [q for q in qs if q['kind'] == 'typed']
        print(f"{i} {p['set']} {p['group']} — 질문 {len(qs)}개: 추천 {len(sug)}(차례 질문 {len(turn_q)}"
              f" · 판 전체 질문 {len(sug) - len(turn_q)}, 서로 다른 판 전체 글 {len({q['q'] for q in sug if q not in turn_q})})"
              f" · 차례 붙인 직접 질문 {len(typed)} · {os.path.getsize(out)} B")


if __name__ == '__main__':
    main()
