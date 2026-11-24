"""대국 뒤 복기 대화 1단계 장면 고르기(설계서 docs/postgame_review_chat_design_1124.md "1단계 상세").
탁자 사실표(Dart 출력 results/table_facts/dart/*.json)의 scenes_by_seat 에서 방총(deal_in) 전부 + 리치 뒤 위험(risky_after_riichi)
중 씨 20261124 로 섞은 앞 8개 = 15장면. 결과: experiments/paifu_review/table_scenes_1124.json(커밋함 — 측정 재료 목록).
  python -I -X utf8 experiments/paifu_review/agent_defense/pick_table_scenes.py
"""
import json, random
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
D = ROOT / 'experiments/paifu_review/results/table_facts/dart'
deal, risky = [], []
for f in sorted(D.glob('*.json')):
    j = json.loads(f.read_text(encoding='utf-8'))
    for wind, scs in j['scenes_by_seat'].items():
        for s in scs:
            row = {'game': f.stem, 'wind': wind, 'step': s['step'], 'why': s['why']}
            (deal if s['why'] == 'deal_in' else risky if s['why'] == 'risky_after_riichi' else []).append(row)
random.Random(20261124).shuffle(risky)
pick = deal + risky[:8]
for i, r in enumerate(pick, 1):
    r['id'] = f'sc{i:02d}'
out = ROOT / 'experiments/paifu_review/table_scenes_1124.json'
out.write_text(json.dumps({'seed': 20261124, 'scenes': pick}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
print(len(deal), len(risky), '->', len(pick)); [print(r) for r in pick]
