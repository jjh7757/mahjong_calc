# 무작위 위험도 장면(시드 고정). mh_risk_cases.json 과 같은 입력 꼴.
import json, random, sys
SEED=int(sys.argv[1]); N=int(sys.argv[2]); OUT=sys.argv[3]
rng=random.Random(SEED)
def code(t): return f"{t%9+1}{'mpsz'[t//9]}"
def scene(idx):
    wall=[4]*34
    def draw(pred=None):
        pool=[t for t in range(34) for _ in range(wall[t]) if (pred is None or pred(t))]
        if not pool: return None
        t=rng.choice(pool); wall[t]-=1; return t
    self_=rng.randrange(4); dealer=rng.randrange(4)
    rw=rng.choice(['1z','1z','2z'])
    inds=[draw()]
    unk=rng.choice(['tedashi','tsumogiri','firstColumn'])
    discards=[]; melds=[]
    riichi=[False]*4; naki=[False]*4; pons={s:[] for s in range(4)}
    nmeld=[0]*4
    T=rng.randint(3,18)
    target_riichi=rng.choice([0,1,1,2,2,3])
    turn=dealer
    cnt=[0]*4
    p_call=rng.choice([0.0,0.01,0.02,0.04])
    while cnt[self_]<T and len(discards)<75:
        s=turn
        # 안깡·가깡(상대·나 모두, 리치 전)
        if not riichi[s] and nmeld[s]<4:
            if rng.random()<0.006:
                q=[t for t in range(34) if wall[t]==4]
                if q:
                    t=rng.choice(q); wall[t]=0
                    melds.append({'seat':s,'kind':'ankan','tiles':code(t)*1 and ''.join(code(t) for _ in range(4)),'at':len(discards),'upgraded_at':None,'red':False})
                    nmeld[s]+=1; ni=draw();
                    if ni is not None: inds.append(ni)
            elif pons[s] and rng.random()<0.08:
                m=pons[s].pop(); t=m['_t']
                if wall[t]>=1:
                    wall[t]-=1; m['kind']='kakan'; m['tiles']=''.join(code(t) for _ in range(4)); m['upgraded_at']=len(discards)
                    ni=draw()
                    if ni is not None: inds.append(ni)
        t=draw()
        if t is None: break
        if s==self_: ts=False
        elif riichi[s]: ts=rng.random()<0.85
        else: ts=rng.random()<0.4
        if s!=self_ and rng.random()<0.3: ts=None
        rflag=False
        if s!=self_ and not riichi[s] and not naki[s] and sum(riichi)<target_riichi and cnt[s]>=2 and rng.random()<0.2:
            rflag=True; riichi[s]=True
        discards.append([s,code(t),ts,rflag]); cnt[s]+=1
        nxt=(s+1)%4
        # 울기
        called=False
        if rng.random()<p_call*3:
            cands=[c for c in range(4) if c!=s and not riichi[c] and nmeld[c]<4]
            rng.shuffle(cands)
            for c in cands:
                r=rng.random()
                if r<0.35 and wall[t]>=2:
                    wall[t]-=2; m={'seat':c,'kind':'pon','tiles':''.join(code(t) for _ in range(3)),'at':len(discards),'upgraded_at':None,'red':(t<27 and t%9==4 and rng.random()<0.4),'_t':t}
                    melds.append(m); pons[c].append(m)
                elif r<0.42 and wall[t]>=3:
                    wall[t]-=3; m={'seat':c,'kind':'minkan','tiles':''.join(code(t) for _ in range(4)),'at':len(discards),'upgraded_at':None,'red':(t<27 and t%9==4 and rng.random()<0.4)}
                    melds.append(m)
                    ni=draw()
                    if ni is not None: inds.append(ni)
                elif c==nxt and t<27:
                    n=t%9; opts=[]
                    for lo in (n-2,n-1,n):
                        if 0<=lo<=6:
                            others=[t-n+lo+k for k in range(3) if lo+k!=n]
                            if all(wall[o]>=1 for o in others): opts.append((lo,others))
                    if not opts: continue
                    lo,others=rng.choice(opts)
                    for o in others: wall[o]-=1
                    base=t-n+lo
                    melds.append({'seat':c,'kind':'chi','tiles':''.join(code(base+k) for k in range(3)),'at':len(discards),'upgraded_at':None,'red':(any((base+k)%9==4 for k in range(3)) and rng.random()<0.3)})
                else:
                    continue
                naki[c]=True; nmeld[c]+=1; turn=c; called=True
                break
        if not called: turn=nxt
    nself=nmeld[self_]
    hand=[draw() for _ in range(13-3*nself)]
    hand=[h for h in hand if h is not None]
    for m in melds: m.pop('_t',None)
    return {'name':f's{idx:03d}','self':self_,'dealer':dealer,'round_wind':rw,'hand':' '.join(code(h) for h in sorted(hand)),
            'dora_indicators':' '.join(code(i) for i in inds if i is not None),'unknown_tsumogiri':unk,'discards':discards,'melds':melds}
cases=[scene(i) for i in range(N)]
json.dump({'cases':cases},open(OUT,'w'))
from collections import Counter
print(len(cases),'riichi',Counter(sum(d[3] for d in c['discards']) for c in cases),'melds',Counter(len(c['melds']) for c in cases),
  'kinds',Counter(m['kind'] for c in cases for m in c['melds']))
