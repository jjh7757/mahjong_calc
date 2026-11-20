import json
g=json.load(open('go_out.json',encoding='utf-8'))
for n in ['riichi1_turn9_basic','naki1_known','naki1_unknown_tedashi','naki1_unknown_tsumogiri','naki1_unknown_firstColumn','early_outside_stack','honor_left_counts','riichi1_ippatsu','kakan_breaks_ippatsu','naki3_dora_red','turns_clamped_19','dama_turn16_sameturn_furiten']:
  o=g[n]; print(n, {k:(v['tenpai'],v['turns'],v['ron_point'],v['ippatsu']) for k,v in o['seats'].items()})
o=g['riichi1_turn9_basic']['seats']['1']['risk34']
print([ (i,o[i]) for i in [0,3,6,15,13,22,21,31,32,28,9]])
print(g['early_outside_stack']['seats']['1']['risk34'][:27])
print(g['honor_left_counts']['left34'][27:], g['honor_left_counts']['seats']['1']['risk34'][27:])
