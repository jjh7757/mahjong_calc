import json, sys, os
from PIL import Image
import numpy as np
root=sys.argv[1]; out=sys.argv[2]
g=json.load(open(os.path.join(root,'grids.json')))
os.makedirs(out,exist_ok=True)
for k in g:
    p=os.path.join(root,'captures',k,'original.jpg')
    if not os.path.exists(p): print('missing',k); continue
    im=Image.open(p).convert('RGB'); a=np.asarray(im)
    h,w,_=a.shape
    im.save(f"{out}/{k}_4080.jpg",quality=75)
    avg=a[:h//2*2,:w//2*2].reshape(h//2,2,w//2,2,3).mean(axis=(1,3)).round().astype(np.uint8)
    Image.fromarray(avg).save(f"{out}/{k}_2040.jpg",quality=85)
    Image.fromarray(a[::4,::4]).save(f"{out}/{k}_1020.jpg",quality=75)
    print(k,w,h)
json.dump({k:v['grid'] for k,v in g.items()},open(f"{out}/grids.json","w"))
