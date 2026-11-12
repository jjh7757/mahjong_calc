import json,sys,statistics as st
d=json.load(open(sys.argv[1],encoding='utf-8'))
def q(a,p): a=sorted(a); return a[min(len(a)-1,int(p*(len(a)-1)+0.5))]
for r,t in d['times_ms'].items(): print('time',r,'med',st.median(t),'p90',q(t,.9),'max',max(t))
for pair in ('1020_vs_2040','1020_vs_4080','2040_vs_4080'):
    vals={}
    for row in d['rows']:
        for s,v in row[pair].items():
            for k,x in v.items(): vals.setdefault(k,[]).append((x,row['key'],s))
    print('==',pair)
    for k,l in vals.items():
        if k=='river_tiles': continue
        xs=[x for x,_,_ in l]
        if isinstance(xs[0],bool): print(' ',k,'same',sum(xs),'/',len(xs),[f'{a}:{b}' for x,a,b in l if not x][:4]); continue
        mx=max(l)
        print(' ',k,'med',round(st.median(xs),4),'p90',round(q(xs,.9),4),'max',round(mx[0],4),mx[1],mx[2])
