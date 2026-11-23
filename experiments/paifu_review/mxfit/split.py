"""mxfit 나눔 — waitsuit.load_split() 과 같은 개발 200판을 다시 만든다 (2026-11-21).

규칙(waitsuit.py 609~615 줄과 같음): riichi_records.json 의 판 ID 를 정렬 → np.random.default_rng(20261121).permutation
→ 앞 200 = 개발. 개발 200판을 ID 순으로 다시 정렬해 앞 160 = 맞춤, 뒤 40 = 검증. 0단계 = 개발 ID 순 앞 20판.
1단계(설계서 11-1): 개발 ID 순 앞 140 = 맞춤 / 다음 20 = 고르기 / 뒤 40 = 검증 → stage1_split(). 뒤 40 은 위 val_games() 와 같다.

개발 200판 밖(시험 판)의 패보 파일은 이 모듈이 열지 않는다(ID 목록만 돌려줌).
2단계(설계서 12절): test_games() = 개발 200판을 뺀 시험 799판(ID 순), test200_games() = 그 앞 200판.
test200_path() 는 시험 200판만 경로를 준다(그 밖이면 오류). log_path() 의 개발 판 보호는 그대로.

위험 보정 다시 재기(docs/risk_calibration_design_1123.md 8절, 11-23): test599_games() = 시험 799판 ID 순 뒤 599판,
test599_path() 는 그 599판만 경로를 준다(밖이면 오류).

쓰기: python -X utf8 split.py [--check] [--check599]   # --check: waitsuit.load_split() 과 dev 집합이 같은지 대조
                                                       # --check599: 새 시험 599판이 개발 200 · 시험 200 과 겹침 0 인지
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
REC = ROOT / 'experiments' / 'paifu_frames' / 'results' / 'handinfer' / 'waitsuit' / 'riichi_records.json'
LOGS = ROOT / 'experiments' / 'paifu_frames' / 'results' / 'handinfer' / 'tenhou_raw' / 'logs'
SPLIT_SEED = 20261121
N_DEV = 200
N_FIT = 160
N_STAGE0 = 20
N_S1_FIT = 140
N_S1_SELECT = 20
N_TEST200 = 200


def all_games() -> list[str]:
    recs = json.loads(REC.read_text(encoding='utf-8'))
    return sorted(set(r['id'] for r in recs))


def dev_games() -> list[str]:
    """개발 200판, ID 순."""
    games = all_games()
    rng = np.random.default_rng(SPLIT_SEED)
    perm = [games[i] for i in rng.permutation(len(games))]
    return sorted(perm[:N_DEV])


def fit_games() -> list[str]:
    return dev_games()[:N_FIT]


def val_games() -> list[str]:
    return dev_games()[N_FIT:]


def stage0_games() -> list[str]:
    return dev_games()[:N_STAGE0]


def stage1_split() -> dict[str, list[str]]:
    """1단계 나눔(설계서 11-1): ID 순 앞 140 맞춤 / 다음 20 고르기 / 뒤 40 검증."""
    dev = dev_games()
    a, b = N_S1_FIT, N_S1_FIT + N_S1_SELECT
    out = {'fit': dev[:a], 'select': dev[a:b], 'val': dev[b:]}
    assert len(out['val']) == N_DEV - b and out['val'] == val_games()
    return out


def stage1_part(game: str) -> str:
    """판 → 'fit' | 'select' | 'val' (개발 판이 아니면 오류)."""
    for k, v in stage1_split().items():
        if game in v:
            return k
    raise ValueError(f'개발 200판 밖의 판: {game}')


def log_path(game: str) -> Path:
    """개발 판만 경로를 준다(시험 판이면 오류)."""
    if game not in set(dev_games()):
        raise ValueError(f'개발 200판 밖의 판: {game}')
    return LOGS / f'{game}.json'


def test_games() -> list[str]:
    """시험 판(개발 200판을 뺀 나머지), ID 순 — ID 목록만, 파일은 열지 않는다."""
    dev = set(dev_games())
    return [g for g in all_games() if g not in dev]


def test200_games() -> list[str]:
    """2단계 시험 200판(설계서 12절): 시험 판을 ID 순 정렬한 앞 200판."""
    return test_games()[:N_TEST200]


def test200_path(game: str) -> Path:
    """시험 200판만 경로를 준다(그 밖 — 나머지 시험 599판 · 개발 판 — 이면 오류)."""
    if game not in set(test200_games()):
        raise ValueError(f'시험 200판 밖의 판: {game}')
    return LOGS / f'{game}.json'


def test599_games() -> list[str]:
    """위험 보정 다시 재기 새 시험 599판(docs/risk_calibration_design_1123.md 8절): 시험 799판 ID 순 뒤 599판."""
    return test_games()[N_TEST200:]


def test599_path(game: str) -> Path:
    """새 시험 599판만 경로를 준다(그 밖 — 시험 200판 · 개발 판 — 이면 오류)."""
    if game not in set(test599_games()):
        raise ValueError(f'새 시험 599판 밖의 판: {game}')
    return LOGS / f'{game}.json'


def check599() -> bool:
    """599판 나눔 검사: 599판 · 개발 200판 · 시험 200판과 겹침 0 · 셋 합이 전체."""
    dev, t200, t599, alls = set(dev_games()), set(test200_games()), test599_games(), all_games()
    s599 = set(t599)
    ok = (len(t599) == 599 and len(s599) == 599 and not (s599 & dev) and not (s599 & t200)
          and (s599 | dev | t200) == set(alls) and t599 == sorted(t599) and min(t599) > max(t200))
    print(f'새 시험 599판: {len(t599)}판({t599[0]} ~ {t599[-1]}) · 개발 200판과 교집합 {len(s599 & dev)} · '
          f'시험 200판과 교집합 {len(s599 & t200)} · 개발 + 시험 200 + 599 = 전체 {len(alls)}판 {(s599 | dev | t200) == set(alls)} · '
          f'시험 200판 뒤 {min(t599) > max(t200)} · 통과 {ok}')
    try:
        test599_path(sorted(t200)[0])
        print('  test599_path(시험 200판) 막힘: 아니오')
        ok = False
    except ValueError:
        print('  test599_path(시험 200판) 막힘: 예')
    try:
        test599_path(sorted(dev)[0])
        print('  test599_path(개발 판) 막힘: 아니오')
        ok = False
    except ValueError:
        print('  test599_path(개발 판) 막힘: 예')
    return ok


def main():
    dev = dev_games()
    print(f'전체 {len(all_games())}판 · 개발 {len(dev)}판 · 맞춤 {N_FIT} · 검증 {len(dev) - N_FIT} · 0단계 {N_STAGE0}')
    print('0단계:', ' '.join(stage0_games()))
    s1 = stage1_split()
    print('1단계: ' + ' · '.join(f'{k} {len(v)}판({v[0]} ~ {v[-1]})' for k, v in s1.items()))
    t200 = test200_games()
    print(f'2단계 시험 200판: {len(t200)}판({t200[0]} ~ {t200[-1]})')
    if '--check' in sys.argv:
        sys.path.insert(0, str(ROOT / 'experiments' / 'paifu_frames' / 'handinfer'))
        import waitsuit  # noqa: E402
        _recs, games, wdev = waitsuit.load_split()
        same = set(dev) == wdev
        print(f'waitsuit.load_split() 대조: 전체 {len(games)}판 · dev {len(wdev)}판 · 같음 {same} · '
              f'교집합 {len(set(dev) & wdev)}')
        wtest = sorted(g for g in games if g not in wdev)  # waitsuit 쪽에서 따로 만든 시험 판(ID 순)
        ok_test = wtest == test_games() and len(wtest) == 799
        ok_200 = t200 == wtest[:N_TEST200] and len(t200) == N_TEST200
        inter = len(set(t200) & wdev)
        print(f'시험 판: waitsuit 쪽 {len(wtest)}판 · test_games() 와 같음 {wtest == test_games()} · 799판 {len(wtest) == 799}')
        print(f'시험 200판 = waitsuit 시험 판 ID 순 앞 200: {ok_200} · 개발 200판과 교집합 {inter} · '
              f'1단계 나눔 판과 교집합 {len(set(t200) & {g for v in s1.values() for g in v})} · '
              f'뒤 599판과 교집합 {len(set(t200) & set(wtest[N_TEST200:]))}')
        if not (same and ok_test and ok_200 and inter == 0):
            sys.exit(1)
    if '--check599' in sys.argv:
        if not check599():
            sys.exit(1)


if __name__ == '__main__':
    main()
