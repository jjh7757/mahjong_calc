"""사실표 한 판을 차례마다 한 줄로 — 질문 · 기대 답을 적을 때 보는 용도.

  python -X utf8 experiments/paifu_review/agent_defense/show_facts.py <사실표.json> [...]
"""
import json
import sys

for path in sys.argv[1:]:
    d = json.load(open(path, encoding='utf-8'))
    g = d['game']
    print(f"\n=== {path.replace(chr(92), '/').split('/')[-1]} · {g.get('round')} {g.get('honba')}본장 · 나 {g.get('hero_wind')} · 도라 표시 {g.get('dora_indicators')} · 결과 {json.dumps(g.get('result'), ensure_ascii=False)}")
    for o in d.get('others', []):
        print(f"   남: 걸음 {o['step']} {o['wind']} {o['kind']} {o.get('tile') or ' '.join(o.get('tiles', []))} {('← ' + str(o.get('from'))) if o.get('from') else ''}")
    for t in d['turns']:
        df = t.get('defense')
        base = f" {t['turn']:2d}번째(걸음 {t['step']}) {t['status']:<9} {str(t.get('grade') or ''):<10} 버림 {t['discard']:<3} 샹텐 {t.get('shanten_before')} 리치 {''.join(t.get('riichi_winds') or []) or '-'}"
        if df:
            a = df['actual']
            eff = df.get('efficient')
            lv = ' '.join(f"{x['tile']}{'*' if x['genbutsu'] else ''}:{x['level']}" for x in df['tiles'])
            base += (f" | 위협 {''.join(df['threat_winds'])} · 버린 패 '{a['level']}' {a['rank']}/{a['of']} · {df.get('stance')} · 가장 안전 {df['safest']}"
                     f" · 효율 {eff['tile'] + ' ' + eff['level'] if eff else '-'}\n       손: {lv}")
        print(base)
