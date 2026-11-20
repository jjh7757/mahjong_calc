# Dart 출력과 Go 여러 번 출력을 비교. 순서는 Go 실행 중 하나와 맞으면 통과,
# 값은 패별로 비교. 동률(정렬 키가 같은 후보)끼리 순서만 다르면 'tie_order'.
import json,sys,glob
from collections import Counter, defaultdict
hands=json.load(open(sys.argv[1]))
dart=json.load(open(sys.argv[2]))['out']
golds=[json.load(open(f)) for f in sys.argv[3:]]
FIELDS=['shanten','waits','waits_count','avg_improve','improve_kinds','improve_way','avg_next','speed','agari_rate','dama','riichi','round_point','furiten_rate','is_part_wait','dora_count']
def eq(a,b):
    if isinstance(a,(int,float)) and isinstance(b,(int,float)) and not isinstance(a,bool) and not isinstance(b,bool):
        return abs(a-b)<=1e-6*max(1,abs(a),abs(b))
    return a==b
def valdiffs(d,g):
    out=[]
    for side in ['forward','backward']:
        gm={x['tile']:x for x in g[side]}; dm={x['tile']:x for x in d[side]}
        if set(gm)!=set(dm): out.append((side,'set',sorted(dm),sorted(gm)))
        for t,x in dm.items():
            y=gm.get(t)
            if y is None: continue
            for f in FIELDS:
                if not eq(x[f],y[f]): out.append((side,f,t,x[f],y[f]))
    return out
cnt=Counter(); bytype=defaultdict(list); bysh=Counter(); okbysh=Counter()
caseinfo={c['id']:c for c in hands['cases']}
for cid,d in dart.items():
    gs=[g[cid] for g in golds]
    sh=gs[0]['shanten']; bysh[sh]+=1
    if 'error' in d:
        cnt['dart_error']+=1; bytype['dart_error'].append((cid,d['error'])); continue
    issues=[]
    if d['shanten']!=sh: issues.append(('shanten14',d['shanten'],sh))
    vds=[valdiffs(d,g) for g in gs]
    vd=[x for x in vds[0] if all(x in v for v in vds)]
    if vds[0] and not vd: cnt['go_value_varies_dart_matches_some']+=1
    if vd: issues.append(('values',vd))
    else:
        orders_ok=any([x['tile'] for x in d[s]]==[x['tile'] for x in g[s]] for g in gs for s in ['forward']) and \
                  any([x['tile'] for x in d['backward']]==[x['tile'] for x in g['backward']] for g in gs)
        best_ok=any(d['best']==g['best'] for g in gs)
        govar=len({json.dumps([[x['tile'] for x in g['forward']],[x['tile'] for x in g['backward']]]) for g in gs})>1
        if not best_ok: issues.append(('best',d['best'],[g['best'] for g in gs],govar))
        if not orders_ok: issues.append(('order',[x['tile'] for x in d['forward']],[x['tile'] for x in gs[0]['forward']],[x['tile'] for x in d['backward']],[x['tile'] for x in gs[0]['backward']],govar))
        if d['recommend_backward']!=gs[0]['recommend_backward'] and all(d['recommend_backward']!=g['recommend_backward'] for g in gs): issues.append(('rec',))
    if not issues:
        cnt['ok']+=1; okbysh[sh]+=1
    else:
        for it in issues:
            key=it[0] if it[0]!='values' else 'values:'+','.join(sorted({x[1] for x in it[1]}))
            cnt[key]+=1; bytype[key].append((cid,it))
print('총',len(dart),'샹텐분포',dict(bysh),'완전일치',cnt['ok'],dict(okbysh))
for k,v in cnt.items():
    if k=='ok': continue
    print('==',k,v)
    for cid,it in bytype[k][:3]:
        c=caseinfo[cid]['input']
        print('  ',cid,'melds',c['melds'],'k',caseinfo[cid]['k'],str(it)[:600])
