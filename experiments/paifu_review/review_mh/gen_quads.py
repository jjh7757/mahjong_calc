# 닫힌 손에 같은 패 4장(깡 안 한 넉 장)이 있는 손: 원본 샹텐 알고리즘과 우리 shanten.dart 차이 찾기
import json,random,sys
rng=random.Random(99)
src=json.load(open(sys.argv[1]))['cases']; out=[]
for c in src+src:
    c=json.loads(json.dumps(c))
    d=c['dart']; h=d['hand34']; vis=d['visible34']
    cand=[t for t in range(34) if h[t]>=2 and h[t]+vis[t]<=4 and vis[t]==0]
    if not cand: continue
    t=rng.choice(cand)
    need=4-h[t]
    others=[x for x in range(34) for _ in range(h[x]) if x!=t]
    rng.shuffle(others)
    for x in others[:need]: h[x]-=1
    h[t]=4
    c['input']['hand34']=h
    c['input']['left34']=[max(0,min(4,4-h[i]-vis[i])) for i in range(34)]
    # 적5 를 손·울기에 맞게 다시
    mt=[x for m in d['melds'] for x in m['tiles']]
    for s in range(3):
        if h[s*9+4]+mt.count(s*9+4)==0: d['red_fives'][s]=0
    c['input']['red_fives']=d['red_fives']
    c['id']='q'+c['id']+str(len(out))
    out.append(c)
json.dump({'cases':out},open(sys.argv[2],'w')); print(len(out))
