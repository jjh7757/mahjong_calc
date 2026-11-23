"""lib/engine/risk_calibration.dart 의 점 목록을 보정표 JSON 에서 그대로 만든다 (2026-11-23).

  python -X utf8 tool/gen_risk_calibration.py           # table.json → lib/engine/risk_calibration.dart 의 점 목록 다시 씀
  python -X utf8 tool/gen_risk_calibration.py --check   # 다시 쓰지 않고 대조만: Dart 상수 = table.json 의 R · C 점(실수 그대로)

보정표: experiments/paifu_review/results/riskcal/table.json (risk_calibrate.py fit, 개발 200판 — experiments/ 결과물이라 커밋 안 됨).
쓰는 것: table['R']['points'] · table['C']['points'] (C 는 "실제로 쓴 표" — C_uses_R 이면 R 과 같은 점).
Dart 파일에서 `// ── 생성: 시작 ──` 과 `// ── 생성: 끝 ──` 사이만 바꾼다. 실수는 Python repr(가장 짧은 되돌림 표기)로 적어
Dart 가 같은 double 로 읽는다. --check 는 ① 지금 파일의 그 구간이 다시 만든 글과 바이트까지 같은지, ② 파일의 숫자를 읽어
float 로 바꾼 값이 JSON 값과 == 로 같은지(점 개수 · 순서 포함)를 본다. 어긋나면 종료 코드 1.
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLE = os.path.join(ROOT, 'experiments', 'paifu_review', 'results', 'riskcal', 'table.json')
DART = os.path.join(ROOT, 'lib', 'engine', 'risk_calibration.dart')
BEGIN = '// ── 생성: 시작 (tool/gen_risk_calibration.py — 손으로 고치지 말 것) ──\n'
END = '// ── 생성: 끝 ──\n'


def load_points():
    t = json.load(open(TABLE, encoding='utf-8'))
    out = {}
    for k in ('R', 'C'):
        pts = [(float(x), float(y)) for x, y in t[k]['points']]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        assert all(b > a for a, b in zip(xs, xs[1:])), f'{k}: x 가 엄격히 늘지 않음'
        assert all(b >= a for a, b in zip(ys, ys[1:])), f'{k}: y 가 줄어듦'
        out[k] = pts
    return t, out


def block(t, pts):
    lines = [BEGIN]
    lines.append(f"// 원본: {os.path.relpath(TABLE, ROOT).replace(os.sep, '/')} (made {t.get('made')}, {t.get('source')}, "
                 f"C_uses_R = {str(bool(t.get('C_uses_R'))).lower()})\n")
    for k, name, what in (('R', 'riskCalPointsRiichi', '리치 위협(R)'), ('C', 'riskCalPointsCallOnly', '울기 위협만(C)')):
        if k == 'C':
            lines.append('\n')
        lines.append(f'/// {what} 보정표: (엔진 값 %, 실제 방총률 %) {len(pts[k])}점. x 는 엄격히 증가, y 는 줄지 않음.\n')
        lines.append(f'const List<(double, double)> {name} = [\n')
        for x, y in pts[k]:
            lines.append(f'  ({x!r}, {y!r}),\n')
        lines.append('];\n')
    lines.append(END)
    return ''.join(lines)


def split_file(src):
    i = src.find(BEGIN)
    j = src.find(END)
    if i < 0 or j < 0 or j < i:
        raise SystemExit(f'{DART}: 생성 구간 표시를 못 찾음')
    return src[:i], src[i:j + len(END)], src[j + len(END):]


def parse_points(seg, name):
    m = re.search(r'const List<\(double, double\)> ' + name + r' = \[\n(.*?)\];', seg, re.S)
    if not m:
        return None
    return [(float(a), float(b)) for a, b in re.findall(r'\(([-0-9.eE+]+), ([-0-9.eE+]+)\)', m.group(1))]


def main():
    check = '--check' in sys.argv[1:]
    t, pts = load_points()
    src = open(DART, encoding='utf-8', newline='').read()
    head, seg, tail = split_file(src)
    want = block(t, pts)
    if not check:
        if seg != want:
            with open(DART, 'w', encoding='utf-8', newline='\n') as f:
                f.write(head + want + tail)
            print(f'다시 씀: {DART}')
        else:
            print('바뀐 것 없음')
        return 0
    bad = []
    if seg != want:
        bad.append('생성 구간 글이 다시 만든 글과 다름')
    for k, name in (('R', 'riskCalPointsRiichi'), ('C', 'riskCalPointsCallOnly')):
        got = parse_points(seg, name)
        if got != pts[k]:
            bad.append(f'{name}: Dart {got and len(got)}점 ≠ table.json {k} {len(pts[k])}점 (또는 값이 다름)')
    if bad:
        print('어긋남:\n  ' + '\n  '.join(bad))
        return 1
    print(f"같음: R {len(pts['R'])}점 · C {len(pts['C'])}점 (table.json made {t.get('made')}, C_uses_R = {t.get('C_uses_R')})")
    return 0


if __name__ == '__main__':
    sys.exit(main())
