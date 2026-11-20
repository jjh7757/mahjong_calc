# gold1~5.json(원본 Go 5회 실행)을 test/fixtures/mh_cases.json 의 "go" 칸으로 합친다.
#   python experiments/paifu_review/mhgold/merge.py experiments/paifu_review/mhgold test/fixtures/mh_cases.json
# - go: 1회째 출력
# - go_order_varies: 5회 사이에 순서(또는 best)가 달라진 쪽 — 원본 Sort 의 동률을 Go map 순회 순서가 가른다
# - known_diffs: 원인을 확인하고 남겨 둔 값 차이(시험은 이 칸만 Dart 저장값과 비교)
import json, sys
G, fx = sys.argv[1], sys.argv[2]
golds = [json.load(open(f"{G}/gold{i}.json", encoding='utf-8')) for i in range(1, 6)]
raw = open(fx, 'rb').read().decode('utf-8')
doc = json.loads(raw)
KNOWN = {
    'ankan_1m': [{'side': 'backward', 'tile': 23, 'field': 'round_point',
                  'reason': '원본 winTable 이 11장(안깡) 손의 이페코를 표시하지 않아(DivideTiles34 IsIipeikou=false) '
                            '234p 789789s 55z+안깡 1m 다마를 역 없음으로 본다. 우리 calculator 는 이페코를 센다. '
                            '9s·7s 쯔모 뒤 자식 국수지가 달라져 가중평균이 4637.59(이쪽) / 4525.93(원본).'}],
}
for c in doc['cases']:
    i = c['id']
    runs = [g[i] for g in golds]
    varies = {}
    for side in ['forward', 'backward']:
        orders = {tuple(x['tile'] for x in r[side]) for r in runs}
        varies[side] = len(orders) > 1
    varies['best'] = len({r['best'] for r in runs}) > 1
    c['go'] = runs[0]
    c['go_order_varies'] = varies
    if i in KNOWN:
        c['known_diffs'] = KNOWN[i]
    else:
        c.pop('known_diffs', None)
open(fx, 'wb').write((json.dumps(doc, ensure_ascii=False, indent=1) + '\n').encode('utf-8'))
print('merged', len(doc['cases']))
