# 지정 사례에서 버림 t 뒤 쯔모 w 한 14장 손(자식)을 새 사례로 만든다(2단까지).
import json,sys
hands={c['id']:c for c in json.load(open(sys.argv[1]))['cases']}
dart=json.load(open(sys.argv[2]))['out']
ids=sys.argv[4].split(',')
out=[]
def child(c,t,w,tag):
    c=json.loads(json.dumps(c))
    for k in ('dart','input'):
        h=c[k]['hand34']; h[t]-=1; h[w]+=1
        c[k]['discards'].append(t)
    c['dart']['visible34'][t]+=1
    c['input']['left34'][w]-=1
    # dart 쪽 left 는 4-hand-visible 이라 자동으로 1 줄어든다(hand 에 들어왔으니)
    c['id']=tag
    return c
for cid in ids:
    c=hands[cid]
    for side in ('forward','backward'):
        for x in dart[cid][side]:
            t=x['tile']
            for w,l in x['waits'].items():
                if l>0: out.append(child(c,t,int(w),f'{cid}_{side[0]}{t}_{w}'))
json.dump({'cases':out},open(sys.argv[3],'w'))
print(len(out))
