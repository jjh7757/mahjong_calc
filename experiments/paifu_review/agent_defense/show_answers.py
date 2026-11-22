"""실제 호출 결과를 질문 · 기대 · 답으로 나란히 — 사람이 읽어 채점할 때.

  python -X utf8 experiments/paifu_review/agent_defense/show_answers.py <질문 파일> <결과 폴더> [set]
"""
import json
import os
import sys

qs = json.load(open(sys.argv[1], encoding='utf-8'))['questions']
out = sys.argv[2]
only = sys.argv[3] if len(sys.argv) > 3 else ''
for q in qs:
    if only and q.get('set') != only:
        continue
    fp = os.path.join(out, q['id'] + '.json')
    if not os.path.exists(fp):
        print(f"\n## {q['id']} — 결과 없음")
        continue
    r = json.load(open(fp, encoding='utf-8'))
    tools = ' → '.join(f"{t['tool']}({','.join(f'{k}={v}' for k, v in (t.get('args') or {}).items())})" for t in r['tool_calls'])
    print(f"\n## {q['id']} [{q.get('kind', '')}{' · 판정 유도' if q.get('induce') else ''}] {q['q']}")
    print(f"   도구: {tools}")
    print(f"   결과: {r['outcome']} · 재시도 {r.get('retries')} · 위반 {r.get('violations')}")
    print(f"   답: {r['answer']}")
    print(f"   기대: {q['expect']}")
