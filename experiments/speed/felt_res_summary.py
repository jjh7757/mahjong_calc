import json, statistics as st, sys
sys.stdout.reconfigure(encoding="utf-8")
d = json.load(open(sys.argv[1]))
r = d['rows']
print('found 1020', sum(x['found_1020'] for x in r), '2040', sum(x['found_2040'] for x in r), '/', len(r))
print('found differ', [x['name'] for x in r if x['found_1020'] != x['found_2040']])
cm = [x['corner_max'] for x in r if x['corner_max'] is not None]
print('corner max (0~1) med', round(st.median(cm), 4), 'max', round(max(cm), 4))
gd = [max(x['grid_diff'].values()) for x in r if x['grid_diff']]
print('grid line max diff (0~1000) med', st.median(gd), 'max', max(gd), 'n', len(gd))
print('sameFelt', sum(1 for x in r if x['same_felt']), '/', sum(1 for x in r if x['same_felt'] is not None))
for k, v in d['ms'].items():
    v = sorted(v); print(k, 'ms med', v[len(v) // 2], 'max', v[-1])
print([(x['name'], x['corner_max'], x['grid_diff']) for x in r if x['same_felt'] is False])
