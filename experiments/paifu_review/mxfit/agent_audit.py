"""문제 푼 하위 에이전트 12개의 기록 감사 — 어떤 도구를 어떤 대상에 썼는지만 뽑는다(기록 본문은 읽지 않음)."""
import glob
import json
import os

IDS = {'acd633889e00df6da': '01', 'abaf0337e35164691': '02', 'a75846d19afa5395c': '03', 'a632785df319b9381': '04',
       'a6b14e45c6933d3c5': '05', 'aced97b879167c668': '06', 'a766309ab262dc26e': '07', 'a05c80824aa0cdf81': '08',
       'a0382e9199370aa91': '09', 'ad4c69b2145d64625': '10', 'a381e884b1460ab90': '11', 'ae23da382901ee8a1': '12'}
roots = [os.path.expanduser(r'~\.claude\projects\C--Users-jjh7757-dev-mahjong-calc'),
         r'C:\Users\jjh7757\AppData\Local\Temp\claude\a10a5a4bd0f0181b\92c48b30-19b1-4e95-b7d0-1226b777417b\tasks']
files = []
for root in roots:
    for dp, _, fns in os.walk(root):
        for fn in fns:
            for aid in IDS:
                if aid in fn and (fn.endswith('.jsonl') or fn.endswith('.output')):
                    files.append((aid, os.path.join(dp, fn)))
print('찾은 기록 파일', len(files))
seen = {}
for aid, fp in sorted(files, key=lambda x: IDS[x[0]]):
    size = os.path.getsize(fp)
    uses = []
    model = set()
    if size:
        for line in open(fp, encoding='utf-8', errors='replace'):
            try:
                o = json.loads(line)
            except Exception:
                continue
            msg = o.get('message') or {}
            if isinstance(msg, dict):
                if msg.get('model'):
                    model.add(msg['model'])
                for c in (msg.get('content') or []) if isinstance(msg.get('content'), list) else []:
                    if isinstance(c, dict) and c.get('type') == 'tool_use':
                        inp = c.get('input') or {}
                        target = inp.get('file_path') or inp.get('path') or inp.get('pattern') or inp.get('command') or inp.get('query') or ''
                        uses.append((c.get('name'), str(target)[-60:]))
    if size and (aid not in seen or len(uses) > len(seen[aid][1])):
        seen[aid] = (fp, uses, model, size)
    print(f"  {IDS[aid]} {os.path.basename(os.path.dirname(fp))}/{os.path.basename(fp)} {size}B 도구 {len(uses)}")
print()
bad = 0
for aid, nn in sorted(IDS.items(), key=lambda x: x[1]):
    if aid not in seen:
        print(nn, '기록 없음(내용 있는 파일을 못 찾음)')
        bad += 1
        continue
    fp, uses, model, size = seen[aid]
    ok = (len(uses) == 2 and uses[0][0] == 'Read' and uses[0][1].endswith(f'quiz\\batch_{nn}.md')
          and uses[1][0] == 'Write' and uses[1][1].endswith(f'answers\\batch_{nn}.json'))
    bad += not ok
    print(nn, '통과' if ok else '확인 필요', sorted(model), uses)
print('확인 필요', bad)
