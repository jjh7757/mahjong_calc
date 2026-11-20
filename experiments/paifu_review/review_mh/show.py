import json,sys
cid=sys.argv[1]; side=sys.argv[2]
d=json.load(open(sys.argv[-1]))['out'][cid]
for f in sys.argv[3:]:
    g=json.load(open(f))[cid]
    print(f,[x['tile'] for x in g[side]])
print('dart',[x['tile'] for x in d[side]])
for x in d[side]:
    print(x['tile'],x['shanten'],x['waits_count'],round(x['avg_improve'] or 0,4),round(x['avg_next'] or 0,4),round(x['speed'] or 0,4),x['agari_rate'],x['dama'],x['riichi'],x['round_point'],x['furiten_rate'],x['improve_kinds'],x['improve_way'],x['is_part_wait'],x['dora_count'])
