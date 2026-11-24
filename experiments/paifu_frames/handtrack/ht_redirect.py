"""손 추적 판별 출력 자리 바꾸기(2026-11-24, 자동 패보 S6a · S6b).

공용 모듈(features · segment · river · game · bandfit · turncut · slotgrid · sam2track · opusread · rebuild_opus · pixtrack · truthprep)은
판별 설정 · 출력을 공용 자리에서 바로 읽고 쓴다:
  handtrack/config/<판>.json · results/handtrack/<판>/… · results/handtrack/_work/<판>_feat.npz
그 모듈들을 고치지 않고, 반장 설정 handtrack.games 의 판만 실행 중에 handtrack.dir(실행 폴더 안) 아래로 돌린다:
  <dir>/config/<판>.json · <dir>/<판>/… · <dir>/_work/<판>_feat.npz
바꾸는 것(install, 한 프로세스에 한 번): htcommon.jload · jsave · out_dir, numpy.load · savez_compressed.
han3.py 는 htcommon.jload 를 자기 것으로 바꾸므로 그 안에서 remap 을 직접 부른다.
handtrack.dir 이 없으면(3반장 · 손 설정) 아무것도 바꾸지 않는다 — install(hc, None, ...) 은 돌리던 자리를 비운다.
"""
from __future__ import annotations

from pathlib import Path

_ST = {"dir": None, "games": frozenset(), "hc": None, "installed": False}


def active() -> bool:
    return _ST["dir"] is not None


def games() -> frozenset:
    return _ST["games"] if active() else frozenset()


def remap(p):
    """공용 자리의 판별 설정 · 출력 경로 → 실행 폴더 경로(대상 판만). 그 밖은 그대로."""
    d, hc = _ST["dir"], _ST["hc"]
    if d is None or hc is None or p is None:
        return p
    try:
        pp = Path(p)
    except TypeError:
        return p
    gs = _ST["games"]
    par, name = pp.parent, pp.name
    if par == hc.CONFIG and name.endswith(".json") and name[:-5] in gs:
        return d / "config" / name
    if par == hc.WORK and name.endswith("_feat.npz") and name[:-9] in gs:
        return d / "_work" / name
    try:
        rel = pp.relative_to(hc.OUT)
    except ValueError:
        return p
    if rel.parts and rel.parts[0] in gs:
        return d.joinpath(*rel.parts)
    return p


def install(hc, d, gs):
    """hc = htcommon 모듈. d = 실행 폴더의 손 추적 자리(Path · 없으면 None), gs = 판 id 목록."""
    import numpy as np
    _ST.update(dir=Path(d).resolve() if d else None, games=frozenset(gs or []), hc=hc)
    if _ST["installed"]:
        return
    _ST["installed"] = True
    jload, jsave, out_dir = hc.jload, hc.jsave, hc.out_dir
    npload, npsave = np.load, np.savez_compressed

    def r_jload(p):
        return jload(remap(p))

    def r_jsave(p, obj, indent=1):
        return jsave(remap(p), obj, indent=indent)

    def r_out_dir(gid):
        if active() and gid in _ST["games"]:
            q = _ST["dir"] / gid
            q.mkdir(parents=True, exist_ok=True)
            return q
        return out_dir(gid)

    def r_npload(f, *a, **k):
        return npload(remap(f), *a, **k)

    def r_npsave(f, *a, **k):
        q = remap(f)
        if q is not f:
            Path(q).parent.mkdir(parents=True, exist_ok=True)
        return npsave(q, *a, **k)
    hc.jload, hc.jsave, hc.out_dir = r_jload, r_jsave, r_out_dir
    np.load, np.savez_compressed = r_npload, r_npsave
