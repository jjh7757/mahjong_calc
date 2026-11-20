import json,sys
from collections import Counter,defaultdict
sc={c['name']:c for c in json.load(open(sys.argv[1]))['cases']}
g=json.load(open(sys.argv[2])); d=json.load(open(sys.argv[3]))
def eq(a,b):
    if isinstance(a,float) or isinstance(b,float): return abs(a-b)<=2e-6*max(1,abs(a))
    return a==b
cnt=Counter(); ex=defaultdict(list)
for n,c in sc.items():
    gg=g.get(n); dd=d.get(n)
    if gg is None: cnt['go_missing']+=1; continue
    if 'error' in dd: cnt['dart_error']+=1; ex['dart_error'].append((n,dd['error'][:200])); continue
    bad=[]
    if gg['left34']!=dd['left34']: bad.append(('left34',[(i,dd['left34'][i],gg['left34'][i]) for i in range(34) if dd['left34'][i]!=gg['left34'][i]]))
    for s,gs in gg['seats'].items():
        ds=dd['seats'][s]
        for k in ['tenpai','turns','ron_point','riichi','ippatsu','safe','left_no_suji']:
            if not (eq(gs[k],ds[k]) if not isinstance(gs[k],list) else gs[k]==ds[k]): bad.append((s,k,ds[k],gs[k]))
        rd=[(i,ds['risk34'][i],gs['risk34'][i]) for i in range(34) if not eq(ds['risk34'][i],gs['risk34'][i])]
        if rd: bad.append((s,'risk34',rd[:5]))
    md=[(i,dd['mixed34'][i],gg['mixed34'][i]) for i in range(34) if not eq(dd['mixed34'][i],gg['mixed34'][i])]
    if md: bad.append(('mixed',md[:4]))
    if not bad: cnt['ok']+=1
    else:
        keys=sorted({b[1] if isinstance(b[1],str) and b[0] not in('left34','mixed') else b[0] for b in bad})
        k=','.join(keys); cnt[k]+=1; ex[k].append((n,bad))
print(dict(cnt))
for k,v in ex.items():
    print('==',k,len(v))
    for n,b in v[:3]:
        c=sc[n]; print('  ',n,'self',c['self'],'dealer',c['dealer'],'unk',c['unknown_tsumogiri'],'melds',[(m['seat'],m['kind'],m['tiles'],m['at'],m['upgraded_at']) for m in c['melds']],str(b)[:700])
