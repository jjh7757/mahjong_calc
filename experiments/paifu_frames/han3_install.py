"""11-14 매장 3반장 열한 판(헤드 폰 녹화로 복구한 패보)을 앱 묶음 assets/paifu_h3/ 로 옮긴다.

    python -X utf8 experiments/paifu_frames/han3_install.py

results/han3_1123/_prep/paifu/<판 id>.json 을 읽어 id 를 h3_<HHMMSS> 로 바꾸고
assets/paifu_h3/h3_<HHMMSS>.json 으로 쓴다(들여쓰기 1칸 · 한글 그대로 · UTF-8 · LF · 끝 개행). 다시 돌리면 덮어쓴다.
옮긴 뒤 시험: flutter test test/paifu_h3_test.dart
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / 'experiments/paifu_frames/results/han3_1123/_prep/paifu'
DST = ROOT / 'assets/paifu_h3'

# 시간 순서.
GAMES = [
    'p01_143158', 'p02_143539', 'p03_144427',
    'n01_144748', 'n02_145625', 'n03_150528', 'n04_151410', 'n05_151953',
    'n06_152545', 'n07_153010', 'n08_153825',
]


def new_id(gid: str) -> str:
    return 'h3_' + gid.split('_', 1)[1]


def main() -> int:
    DST.mkdir(parents=True, exist_ok=True)
    for gid in GAMES:
        src = SRC / f'{gid}.json'
        p = json.loads(src.read_text(encoding='utf-8'))
        nid = new_id(gid)
        p['id'] = nid  # 열쇠 순서는 그대로(id 는 제자리에서 바뀜)
        text = json.dumps(p, ensure_ascii=False, indent=1) + '\n'
        out = DST / f'{nid}.json'
        out.write_bytes(text.encode('utf-8'))
        print(f'{gid} -> {out.relative_to(ROOT).as_posix()}  {p.get("title")}')
    extra = sorted(f.name for f in DST.glob('*.json') if f.stem not in {new_id(g) for g in GAMES})
    if extra:
        print('주의: 목록에 없는 파일이 남아 있음:', extra)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
