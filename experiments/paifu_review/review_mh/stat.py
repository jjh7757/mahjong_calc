import json,sys
from collections import Counter
d=json.load(open(sys.argv[1]))
print(Counter(v['shanten'] for v in d.values()))
