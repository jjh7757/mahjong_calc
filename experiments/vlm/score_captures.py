"""거치 촬영 기록(Download/mahjong_calc/<시각>/)을 모아 높이·줌별 정확도를 낸다.

각 촬영 폴더에는 앱이 남긴 meta.json(판독·병합 결과, 촬영 조건 setup)과,
"대국에 반영" 했다면 label.json(확정 값 = 정답)이 있다. 둘은 같은 키를 쓴다.

용법:
  python score_captures.py <폴더>                      이미 받아 둔 기록 집계
  python score_captures.py <폴더> --adb emulator-5554  기기에서 먼저 받아 온 뒤 집계
  python score_captures.py <폴더> --since 20261024_1300 --csv shots.csv

출력은 마크다운(RESULTS.md 에 그대로 붙인다).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path

DEVICE_DIR = '/sdcard/Download/mahjong_calc'
DEFAULT_ADB = r'C:\Users\jjh7757\dev\android-sdk\platform-tools\adb.exe'

# 사용자가 고르는 시간(화료자 선택)은 지연에서 뺀다.
USER_WAIT_KEYS = {'pick'}


# ---------------- 패 정규화 ----------------

def norm(code: str) -> str:
    """적도라 0m → 5m."""
    return '5' + code[1] if code and code[0] == '0' else code


def meld_tiles(m: str) -> list[str]:
    """'[7z 7z 7z]' / '(6z 6z 6z 6z)' → 패 목록."""
    return m.strip('[]() ').split()


def all_tiles(o: dict) -> list[str]:
    tiles = list(o.get('closed') or [])
    for m in o.get('melds') or []:
        tiles += meld_tiles(m)
    return [norm(t) for t in tiles]


def win_tile(o: dict) -> str | None:
    w = o.get('win_tile')
    if w is None and o.get('closed'):
        w = o['closed'][-1]  # 옛 기록: 화료패가 마지막
    return norm(w) if w else None


def tile_errors(pred: dict, truth: dict) -> tuple[int, list[str], list[str]]:
    """틀린 장수와 (빠진 패, 더 읽은 패)."""
    p, t = Counter(all_tiles(pred)), Counter(all_tiles(truth))
    missing = sorted((t - p).elements())
    extra = sorted((p - t).elements())
    return max(len(missing), len(extra)), missing, extra


def sorted_melds(o: dict) -> list[str]:
    out = []
    for m in o.get('melds') or []:
        kind = '(' if m.strip().startswith('(') else '['
        out.append(kind + ' '.join(sorted(norm(t) for t in meld_tiles(m))))
    return sorted(out)


def dora(o: dict, key: str = 'dora_indicators') -> list[str]:
    return sorted(norm(str(t)) for t in o.get(key) or [])


# ---------------- 한 장 채점 ----------------

def score_shot(meta: dict, label: dict | None) -> dict:
    pred = meta.get('merge')
    setup = meta.get('setup') or {}
    timings = meta.get('timings_ms') or {}
    r = {
        # 판독 방식: grid(미리 그은 격자) · locate · fixed(고정 구역) · fixed→locate. 예전 기록은 locate.
        'mode': meta.get('layout_mode') or 'locate',
        'height_cm': setup.get('height_cm'),
        'zoom': setup.get('zoom'),
        'source': setup.get('source'),
        'error': meta.get('error'),
        'read': pred is not None,
        'valid': bool(pred and pred.get('hand_valid')),
        'flags': (pred or {}).get('flags') or [],
        'latency_ms': sum(v for k, v in timings.items() if k not in USER_WAIT_KEYS) if timings else None,
        'labeled': label is not None,
    }
    if label is None:
        return r
    p = pred or {}
    errs, missing, extra = tile_errors(p, label)
    checks = {
        'hand': errs == 0 and win_tile(p) == win_tile(label) and sorted_melds(p) == sorted_melds(label),
        'red': p.get('red_count') == label.get('red_count'),
        'winner': p.get('winner') == label.get('winner'),
        'tsumo': p.get('is_tsumo') == label.get('is_tsumo'),
        'loser': p.get('loser') == label.get('loser'),
        'riichi': p.get('riichi') == label.get('riichi'),
        'dora': dora(p) == dora(label),
    }
    r.update(checks)
    r['all'] = all(checks.values())
    # 리치 4자리: 사진 판독(riichi_seats_photo) 과 확정(riichi_seats). 둘 다 있는 기록만.
    if 'riichi_seats' in label and 'riichi_seats_photo' in p:
        r['riichi4'] = sorted(p['riichi_seats_photo']) == sorted(label['riichi_seats'])
    else:
        r['riichi4'] = None
    r['all'] = r['all'] and r['riichi4'] is not False
    # 뒷도라: 리치 화료(정답 기준)일 때만 잰다. 예전 기록(ura_indicators 없음)은 None.
    if label.get('riichi') and 'ura_indicators' in label and 'ura_indicators' in p:
        r['ura'] = dora(p, 'ura_indicators') == dora(label, 'ura_indicators')
    else:
        r['ura'] = None
    r['all'] = r['all'] and r['ura'] is not False
    r['tile_errors'] = errs
    r['missing'] = missing
    r['extra'] = extra
    r['win_pred'] = win_tile(p)
    r['win_true'] = win_tile(label)
    return r


# ---------------- 모으기 ----------------

def pull(adb: str, serial: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, MSYS_NO_PATHCONV='1')
    cmd = [adb, '-s', serial, 'pull', DEVICE_DIR + '/.', str(dest)]
    print(f'<!-- {" ".join(cmd)} -->', file=sys.stderr)
    subprocess.run(cmd, check=True, env=env)


def load_shots(root: Path, since: str | None) -> list[tuple[str, dict, dict | None]]:
    shots = []
    for meta_path in sorted(root.rglob('meta.json')):
        d = meta_path.parent
        if since and d.name < since:
            continue
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        lp = d / 'label.json'
        label = json.loads(lp.read_text(encoding='utf-8')) if lp.exists() else None
        shots.append((d.name, meta, label))
    return shots


def pct(n: int, d: int) -> str:
    return '-' if d == 0 else f'{n}/{d} ({round(100 * n / d)}%)'


def fmt_zoom(z) -> str:
    if z is None:
        return '?'
    return f'{z:g}x'


def report(rows: list[tuple[str, dict]]) -> str:
    out = []
    n = len(rows)
    labeled = [r for _, r in rows if r['labeled']]
    errors = Counter(r['error'] for _, r in rows if r['error'])
    out.append(f'촬영 {n}장, 정답 있음 {len(labeled)}장, 판독 실패 {sum(errors.values())}장')
    out.append('')

    groups: dict[tuple, list[dict]] = {}
    for _, r in rows:
        groups.setdefault((r['mode'], r['height_cm'], r['zoom']), []).append(r)

    out.append('| 방식 | 높이 | 줌 | 촬영 | 판독 성공 | 손패 장수 맞음 | 정답 있음 | 손패 정답 | 평균 틀린 패 | 화료자 | 론/쯔모 | 방총자 | 리치 | 리치 4자리 | 도라 | 뒷도라 | 적도라 | 전부 정답 | 지연 중앙값 |')
    out.append('|' + '---|' * 19)

    def key(k):
        m, h, z = k
        return (m, h is None, h or 0, z is None, z or 0)

    for (m, h, z) in sorted(groups, key=key):
        g = groups[(m, h, z)]
        lab = [r for r in g if r['labeled']]
        lat = [r['latency_ms'] for r in g if r['latency_ms']]
        def c(k):
            have = [r for r in lab if r.get(k) is not None]
            return pct(sum(1 for r in have if r[k]), len(have))
        mean_err = f'{statistics.mean(r["tile_errors"] for r in lab):.1f}' if lab else '-'
        out.append('| ' + ' | '.join([
            m,
            f'{h}cm' if h is not None else '?',
            fmt_zoom(z),
            str(len(g)),
            pct(sum(1 for r in g if r['read']), len(g)),
            pct(sum(1 for r in g if r['valid']), len(g)),
            str(len(lab)),
            c('hand'), mean_err, c('winner'), c('tsumo'), c('loser'), c('riichi'), c('riichi4'), c('dora'), c('ura'), c('red'), c('all'),
            f'{statistics.median(lat) / 1000:.1f}초' if lat else '-',
        ]) + ' |')

    if errors:
        out.append('')
        out.append('판독 실패 사유:')
        for e, k in errors.most_common():
            out.append(f'- {k}장: {e}')

    wrong = [(name, r) for name, r in rows if r['labeled'] and not r['all']]
    if wrong:
        out.append('')
        out.append('틀린 촬영:')
        for name, r in wrong:
            cond = f'{r["mode"]} {r["height_cm"] or "?"}cm {fmt_zoom(r["zoom"])}'
            if not r['read']:
                out.append(f'- `{name}` ({cond}): 판독 실패 — {r["error"] or "병합 결과 없음"}')
                continue
            bad = [k for k in ('hand', 'red', 'winner', 'tsumo', 'loser', 'riichi', 'riichi4', 'dora', 'ura') if r.get(k) is False]
            detail = []
            if r['missing'] or r['extra']:
                detail.append(f'빠짐 {" ".join(r["missing"]) or "-"} / 더 읽음 {" ".join(r["extra"]) or "-"}')
            if r['win_pred'] != r['win_true']:
                detail.append(f'화료패 {r["win_pred"]}→정답 {r["win_true"]}')
            out.append(f'- `{name}` ({cond}): {", ".join(bad)}' + (f' — {"; ".join(detail)}' if detail else ''))
    return '\n'.join(out)


def write_csv(path: Path, rows: list[tuple[str, dict]]) -> None:
    cols = ['shot', 'mode', 'height_cm', 'zoom', 'source', 'read', 'valid', 'labeled', 'hand', 'tile_errors', 'red',
            'winner', 'tsumo', 'loser', 'riichi', 'riichi4', 'dora', 'ura', 'all', 'latency_ms', 'error', 'missing', 'extra']
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(cols)
        for name, r in rows:
            row = {**r, 'shot': name}
            w.writerow([' '.join(row[c]) if isinstance(row.get(c), list) else row.get(c, '') for c in cols])


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('folder', type=Path, help='촬영 폴더들이 들어 있는 폴더')
    ap.add_argument('--adb', metavar='SERIAL', help=f'{DEVICE_DIR} 를 먼저 받아 온다(예: emulator-5554)')
    ap.add_argument('--adb-path', default=os.environ.get('ADB') or (DEFAULT_ADB if Path(DEFAULT_ADB).exists() else shutil.which('adb') or 'adb'))
    ap.add_argument('--since', help='이 이름(yyyyMMdd_HHmmss) 이후 폴더만')
    ap.add_argument('--csv', type=Path, help='촬영별 결과를 CSV 로도 남긴다')
    a = ap.parse_args()

    if a.adb:
        pull(a.adb_path, a.adb, a.folder)
    shots = load_shots(a.folder, a.since)
    if not shots:
        sys.exit(f'{a.folder} 에 meta.json 이 있는 촬영 폴더가 없습니다')
    rows = [(name, score_shot(meta, label)) for name, meta, label in shots]
    print(report(rows))
    if a.csv:
        write_csv(a.csv, rows)


if __name__ == '__main__':
    main()
