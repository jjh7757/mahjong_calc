import json,sys,math
G=sys.argv[1]; fx=sys.argv[2]
golds=[json.load(open(f"{G}/gold{i}.json",encoding='utf-8')) for i in range(1,6)]
doc=json.load(open(fx,encoding='utf-8'))
FIELDS=['shanten','waits','waits_count','avg_improve','improve_kinds','improve_way','avg_next','speed','agari_rate','dama','riichi','round_point','furiten_rate','is_part_wait','dora_count']
def eq(a,b):
    if isinstance(a,(int,float)) and isinstance(b,(int,float)) and not isinstance(a,bool):
        return abs(a-b)<=1e-6*max(1,abs(a),abs(b))
    return a==b
def diffs(d,g):
    out=[]
    for k in ['shanten','best','recommend_backward']:
        if not eq(d[k],g[k]): out.append(f"{k}: dart {d[k]} go {g[k]}")
    for side in ['forward','backward']:
        do=[x['tile'] for x in d[side]]; go=[x['tile'] for x in g[side]]
        if do!=go: out.append(f"{side} order dart {do} go {go}")
        gm={x['tile']:x for x in g[side]}
        for x in d[side]:
            x.setdefault('code',str(x['tile']))
            y=gm.get(x['tile'])
            if y is None: out.append(f"{side} {x['tile']} missing in go"); continue
            for f in FIELDS:
                if not eq(x[f],y[f]): out.append(f"{side} {x['code']} {f}: dart {x[f]} go {y[f]}")
    return out
ok=0
for c in doc['cases']:
    i=c['id']; d=c['dart']
    var=[diffs(golds[0][i],gg[i]) for gg in golds[1:]]
    var=[v for v in var if v]
    best=None
    for gg in golds:
        df=diffs(d,gg[i])
        if best is None or len(df)<len(best[0]): best=(df,gg)
    if not best[0]: ok+=1
    print(f"== {i}: {'OK' if not best[0] else str(len(best[0]))+' diffs'}" + (f"  [go 실행마다 다름 {len(var)}/4]" if var else ""))
    for x in best[0][:12]: print("   ",x)
    if var:
        for x in var[0][:4]: print("    go-var:",x)
print(f"일치 {ok}/{len(doc['cases'])}")
