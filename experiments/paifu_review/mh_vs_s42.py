"""평가기 최선(지금 유효패 순 · mahjong-helper 순)을 Mortal-S42 첫째 버림과 맞대기 (2026-11-20 밤).

입력: experiments/paifu_review/mhdump/<판>.json (tool/paifu_review_dump.dart 출력)
      experiments/paifu_review/mortal/<판>_<가정>_s42.txt (mortal_local.py 출력)
쓰기: python mh_vs_s42.py [tedashi|tsumogiri]

맞추기: hero 의 k번째 버림 ↔ S42 의 k번째 "tsumo:hero" 결정(실제가 Riichi 면 다음 reach 줄의 버림).
S42 최선 버림 = 그 tsumo 줄 후보 중 Riichi · Hora 를 뺀 가장 높은 Q 의 패(다마로 버린다면의 첫째).
비교 대상 = status graded(우리 등급을 매긴 차례). 적5 는 5 로 접어 비교.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
GAMES = ['r11_130921', 'r12_131655', 'r17_140450', 'r19_142013']
HON = {'E': '1z', 'S': '2z', 'W': '3z', 'N': '4z', 'P': '5z', 'F': '6z', 'C': '7z'}


def norm_mjai(t: str) -> str:
    if t in HON:
        return HON[t]
    return t[:2]  # '5sr' → '5s'


def norm_ours(t: str) -> str:
    return '5' + t[1] if t and t[0] == '0' else t


def s42_rows(path: Path):
    rows = []
    for line in path.read_text(encoding='utf-8').splitlines():
        m = re.match(r'\s*\d+ \(x\d+\) sh(\S+) (\S+)\s+실제 (\S+)\s+(\S+)\s+(\S+)\s+\| (.*)', line)
        if not m:
            continue
        sh, trig, act, rank, p, top = m.groups()
        cands = []
        for c in top.split():
            n, q, pr = c.rsplit('/', 2)
            cands.append((n, float(q), float(pr)))
        rows.append({'trig': trig, 'actual': act, 'rank': rank, 'cands': cands, 'sh': sh})
    return rows


def main():
    var = sys.argv[1] if len(sys.argv) > 1 else 'tedashi'
    sdir = sys.argv[2] if len(sys.argv) > 2 else 'mortal_1120'  # 11-20 20:20 판본 패보로 다시 만든 S42 결과
    tot = {'n': 0, 'ours': 0, 'mh': 0, 'both': 0, 'neither': 0, 'player': 0, 'mh_top2': 0}
    detail = []
    for g in GAMES:
        dump = json.loads((HERE / 'mhdump' / f'{g}.json').read_text(encoding='utf-8'))
        rows = s42_rows(HERE / sdir / f'{g}_{var}_s42.txt')
        hero = dump['hero']
        decs = []  # hero 버림 결정 순서대로
        for i, r in enumerate(rows):
            if r['trig'].startswith('tsumo:'):
                act = r['actual']
                if act == 'Riichi' and i + 1 < len(rows) and rows[i + 1]['trig'].startswith('reach:'):
                    act = rows[i + 1]['actual']
                if act in ('Hora',):
                    continue
                disc = [c for c in r['cands'] if c[0] not in ('Riichi', 'Hora', 'Ryukyoku', 'Pass')]
                decs.append({'actual': norm_mjai(act), 'best': norm_mjai(disc[0][0]) if disc else None,
                             'second': norm_mjai(disc[1][0]) if len(disc) > 1 else None, 'n': len(r['cands'])})
        turns = dump['turns']
        if len(decs) != len(turns):
            print(f'!! {g}: S42 버림 결정 {len(decs)} ≠ 덤프 차례 {len(turns)}')
        for t, d in zip(turns, decs):
            if norm_ours(t['discard']) != d['actual']:
                print(f"!! {g} 차례 {t['turn']}: 버린 패 어긋남 덤프 {t['discard']} S42 {d['actual']}")
                continue
            if t['status'] != 'graded':
                continue
            ours, mh, s = norm_ours(t['ourBest']), norm_ours(t['mhBest'] or ''), d['best']
            tot['n'] += 1
            tot['ours'] += ours == s
            tot['mh'] += mh == s
            tot['both'] += ours == s and mh == s
            tot['neither'] += ours != s and mh != s
            tot['player'] += norm_ours(t['discard']) == s
            top5 = t.get('mhTop5') or []
            top2 = [norm_ours(x['tile']) for x in top5[:2]]
            tot['mh_top2'] += s in top2
            # 후퇴 권장을 끈 mahjong-helper: 샹텐을 지키는 후보 중 첫째(원본 Sort 의 앞쪽 목록 첫째)
            fwd = next((norm_ours(x['tile']) for x in top5 if x['shanten'] <= t['shantenBefore']), mh)
            tot['mh_fwd'] = tot.get('mh_fwd', 0) + (fwd == s)
            if t.get('recommendBackward'):
                tot['bk_n'] = tot.get('bk_n', 0) + 1
                tot['bk_hit'] = tot.get('bk_hit', 0) + (mh == s)
            if ours != s or mh != s:
                detail.append(f"{g} 차례{t['turn']:>2} sh{t['shantenBefore']} 실제 {t['discard']:<3} 우리 {t['ourBest']:<3} mh {t['mhBest']:<3} S42 {s:<3}(둘째 {d['second']}) mh후퇴권장 {t.get('recommendBackward')}")
    n = tot['n']
    print(f"[{var}] graded {n}차례 — S42 첫째 버림과 같음: 지금 평가기 {tot['ours']}/{n} · mahjong-helper {tot['mh']}/{n} "
          f"(둘 다 {tot['both']}, 둘 다 아님 {tot['neither']}) · mh 1~2위 안 {tot['mh_top2']}/{n} · 플레이어 실제 {tot['player']}/{n}\n"
          f"   후퇴 권장 끈 mahjong-helper {tot.get('mh_fwd', 0)}/{n} · 후퇴 권장 차례에서 S42 가 후퇴 패를 고름 {tot.get('bk_hit', 0)}/{tot.get('bk_n', 0)}")
    for x in detail:
        print('  ', x)


if __name__ == '__main__':
    main()
