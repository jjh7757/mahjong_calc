import json,sys
d=json.load(open(sys.argv[1]))['out'];g=json.load(open(sys.argv[2]))
out=[]
for k,v in d.items():
  gm={x['tile']:x for s in ('forward','backward') for x in g[k][s]}
  if any(abs((x['round_point'] or 0)-(gm[x['tile']]['round_point'] or 0))>1e-6 for s in ('forward','backward') for x in v[s]): out.append(k)
print(','.join(out[:3]))
