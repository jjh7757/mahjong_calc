import json, sys
doc = json.load(open(sys.argv[1], encoding='utf-8'))
go = json.load(open(sys.argv[2], encoding='utf-8'))
old = {}
try:
    for c in json.load(open(sys.argv[3], encoding='utf-8'))['cases']:
        if 'dart' in c: old[c['name']] = c['dart']
except FileNotFoundError:
    pass
for c in doc['cases']:
    c['go'] = go[c['name']]
    if c['name'] in old: c['dart'] = old[c['name']]
with open(sys.argv[3], 'w', encoding='utf-8', newline='\n') as f:
    json.dump(doc, f, ensure_ascii=False, indent=1)
print('merged', len(doc['cases']))
