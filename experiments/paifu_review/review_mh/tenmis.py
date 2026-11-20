import json,sys
h={c['id']:c for c in json.load(open(sys.argv[1]))['cases']}
d=json.load(open(sys.argv[2]))['out']; g=json.load(open(sys.argv[3]))
N='mpsz'
def s(h34):
    out=''
    for su in range(4):
        x=''.join(str(i+1)*h34[su*9+i] for i in range(9 if su<3 else 7))
        if x: out+=x+N[su]
    return out
def code(t): return f"{t%9+1}{N[t//9]}"
for cid,v in d.items():
    pass
    for side in ('forward','backward'):
        gm={x['tile']:x for x in g[cid][side]}
        for x in v[side]:
            y=gm[x['tile']]
            if x['shanten']==0 and (abs((x['dama'] or 0)-(y['dama'] or 0))>1e-6 or abs((x['riichi'] or 0)-(y['riichi'] or 0))>1e-6):
                c=h[cid]['input']
                print(cid,'hand',s(c['hand34']),'melds',[(m['type'],code(m['tiles'][0])) for m in c['melds']],'dora',[code(t) for t in c['dora_tiles']],'red',c['red_fives'],'rw',code(c['round_wind']),'sw',code(c['self_wind']),'parent',c['is_parent'],'| discard',code(x['tile']),'waits',{code(int(k)):vv for k,vv in x['waits'].items()},'dama d/g',x['dama'],y['dama'],'riichi d/g',x['riichi'],y['riichi'])
