import json,sys
h={c['id']:c for c in json.load(open(sys.argv[1]))['cases']}
d=json.load(open(sys.argv[2]))['out']; g=json.load(open(sys.argv[3]))
tot=0; iip=0; other=[]
for cid,v in d.items():
    for side in ('forward','backward'):
        gm={x['tile']:x for x in g[cid][side]}
        for x in v[side]:
            y=gm[x['tile']]
            if x['shanten']==0 and abs((x['dama'] or 0)-(y['dama'] or 0))+abs((x['riichi'] or 0)-(y['riichi'] or 0))>1e-6:
                tot+=1
                hh=list(h[cid]['input']['hand34']); hh[x['tile']]-=1
                ok=False
                for w,l in x['waits'].items():
                    if l==0: continue
                    a=hh[:]; a[int(w)]+=1
                    if any(s%9<=6 and s<27 and min(a[s],a[s+1],a[s+2])>=2 for s in range(27)): ok=True
                iip+=ok
                if not ok: other.append((cid,x['tile']))
print('tenpai dama/riichi mismatch',tot,'iipeikou-shape',iip,'other',other[:5])
