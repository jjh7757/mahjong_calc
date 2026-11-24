"""헤드 녹화로 복구한 반장 패보를 앱 묶음 폴더로 옮긴다(처음은 11-14 매장 3반장 열한 판 → assets/paifu_h3/).

    python -X utf8 experiments/paifu_frames/han3_install.py [--hanchan <json>] [--src <폴더>] [--dst <폴더>]

반장 설정(handtrack/hanchan_cfg.py, 안 주면 hanchan/h3_1123.json)의 install.src(기본 paifu.out_dir — 3반장: results/han3_1123/_prep/paifu)
에서 <판 id>.json 을 읽어 id 를 <install.id_prefix><HHMMSS>(3반장: h3_<HHMMSS>)로 바꾸고 install.dst(3반장: assets/paifu_h3)
<새 id>.json 으로 쓴다(들여쓰기 1칸 · 한글 그대로 · UTF-8 · LF · 끝 개행). 다시 돌리면 덮어쓴다. 판 순서 = 설정 games(시간 순).
--src · --dst = 설정 대신(시험용 — 스크래치 폴더에 써 보기).
옮긴 뒤 시험(3반장): flutter test test/paifu_h3_test.dart
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'experiments/paifu_frames/handtrack'))
import hanchan_cfg as hcfg  # noqa: E402

# 아래 넷은 반장 설정에서(configure). 3반장 설정 값: SRC = results/han3_1123/_prep/paifu · DST = assets/paifu_h3 · PREFIX = 'h3_' ·
# GAMES = p01 ~ p03 · n01 ~ n08(시간 순).
SRC = DST = None
PREFIX = None
GAMES: list = []


def configure(cfg, src=None, dst=None):
    global SRC, DST, PREFIX, GAMES
    SRC = pathlib.Path(src).resolve() if src else cfg.install_src
    DST = pathlib.Path(dst).resolve() if dst else cfg.install_dst
    if DST is None:
        raise hcfg.HanchanError(f'{cfg.path.name}: install.dst 가 없다(또는 --dst 를 줘라)')
    PREFIX = cfg.install_prefix
    GAMES = list(cfg.games)


def new_id(gid: str) -> str:
    return PREFIX + gid.split('_', 1)[1]


def _show(p: pathlib.Path) -> str:
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def main() -> int:
    args = sys.argv[1:]
    cfg = hcfg.from_argv(args)
    configure(cfg, hcfg.pop_opt(args, '--src'), hcfg.pop_opt(args, '--dst'))
    if args:
        raise SystemExit(f'모르는 인자: {args}')
    DST.mkdir(parents=True, exist_ok=True)
    for gid in GAMES:
        src = SRC / f'{gid}.json'
        p = json.loads(src.read_text(encoding='utf-8'))
        nid = new_id(gid)
        p['id'] = nid  # 열쇠 순서는 그대로(id 는 제자리에서 바뀜)
        text = json.dumps(p, ensure_ascii=False, indent=1) + '\n'
        out = DST / f'{nid}.json'
        out.write_bytes(text.encode('utf-8'))
        print(f'{gid} -> {_show(out)}  {p.get("title")}')
    extra = sorted(f.name for f in DST.glob('*.json') if f.stem not in {new_id(g) for g in GAMES})
    if extra:
        print('주의: 목록에 없는 파일이 남아 있음:', extra)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
