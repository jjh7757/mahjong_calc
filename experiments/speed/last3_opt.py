"""강 끝 한 호출(/v2/last3) 프롬프트 변형을 B·C·D 로 나란히 잰다(프롬프트 최적화, 2026-10-26 밤).

  python experiments/speed/last3_opt.py [--runs 10]

변형(한 가지씩만 바꿈, 사진 특정 문구 없음):
  base   지금 서버 last_multi_prompt(3)
  guide  표기법의 통수·삭수 줄을 무늬 배치까지(bench.NOTATION_GUIDE)
  ref    통수·삭수 참고표(자리 판독과 같은 집 패 표)를 넷째 사진으로 붙임
같은 장면의 변형들을 같은 순간에 보낸다. 정답·크롭은 last3.py 와 같다. 결과는 results/last3_opt.json.
"""
from __future__ import annotations

import argparse
import json
import statistics
from concurrent.futures import ThreadPoolExecutor

import bench as b
import last3 as l3

ob = b.ob
REF_NOTE_LAST = """

넷째 사진은 이 패 세트의 통수(1p~9p)·삭수(1s~9s) 실물 참고표입니다(이름표가 위에 있음). 통수·삭수는 참고표와 무늬 개수·배치를 비교해 정합니다.
참고표는 강이 아니므로 답(photo1~photo3)은 앞의 사진 3장에 대해서만 적습니다."""
# 강 줄 세기: C 오른쪽 실패 분석에서 나온 일반 규칙. 셋째 줄 첫 패가 조금 아래로 처져 있으면 "가장 아래 줄의 가장 오른쪽" 이
# 그 처진 패가 된다(6통을 8삭으로). 줄은 6장씩이므로 위치가 아니라 순서로 끊어 센다.
COUNT6_NOTE = """
줄이 조금 어긋나 있거나 한 패만 아래로 처져 보여도 줄은 버린 순서대로 6장씩입니다. 첫 줄 왼쪽부터 6장씩 끊어 세고,
마지막 패는 그렇게 센 마지막 줄의 가장 오른쪽 패입니다. 처진 패 하나를 새 줄로 보지 않습니다."""
VARIANTS = ["base", "guide", "ref"]


def _count6(prompt: str) -> str:
    anchor = "그 패가 옆으로 눕혀져 있어도 그대로 마지막 패입니다."
    return prompt.replace(anchor, anchor + COUNT6_NOTE)


def base_prompt(n: int) -> str:
    """참고표 문단을 뺀 강 끝 프롬프트(이 실험의 base). 서버 프롬프트는 ref 변형을 채택해 참고표 문단을 담고 있다(2026-10-26)."""
    p = ob.last_multi_prompt(n)
    i = p.find("\n\n넷째 사진은 이 패 세트의") if n == 3 else -1
    return p if i < 0 else p[:i] + p[p.index("\n\n확신도(0~1)를 적어 주세요."):]


# "틀 먼저": 마지막 패 하나를 묻지 않고 강의 틀(줄·칸)을 적게 한 뒤 마지막 패는 코드가 고른다(2026-10-26, 사용자 제안).
# 둘 다 지금 서버 프롬프트(참고표 포함, = server)에서 마지막 패 설명과 답 칸만 바꾼다.
_LAST_RULE = ("각 줄은 왼쪽에서 오른쪽으로 버립니다. 따라서 마지막 패는 **가장 아래 줄의 가장 오른쪽 패**입니다.\n"
              "그 패가 옆으로 눕혀져 있어도 그대로 마지막 패입니다.")
_LAST_FIELDS = ("  - last_tile: 그 사진 아래쪽 플레이어 강의 마지막 패 한 장. 그 강이 보이지 않으면 null.\n"
                "  - tile_count: 그 강의 패 수.")
_FRAME_FIELDS = {
    "rows": "  - rows: 그 사진 아래쪽 플레이어 강의 패를 줄마다 왼쪽부터 적습니다(첫 줄 = 테이블 가운데 쪽). 줄은 버린 순서대로 6장씩이고\n"
            "    마지막 줄만 6장보다 적을 수 있습니다. 패가 조금 어긋나 놓여 있어도 위아래 줄과 칸을 맞춰 어느 줄인지 정합니다. 강이 보이지 않으면 빈 배열.",
    "grid": "  - tiles: 그 사진 아래쪽 플레이어 강의 패 전부. 패마다 code, row(테이블 가운데 쪽 첫 줄이 0), col(그 줄의 왼쪽 끝 칸 0 ~ 오른쪽 끝 칸 5)을 적습니다.\n"
            "    한 줄은 6칸입니다. 패가 조금 어긋나 놓여 있어도 위아래 줄의 패와 세로로 맞춰 몇 번째 칸인지 정합니다. 강이 보이지 않으면 빈 배열.",
}
_TILE = {"type": "string", "enum": ob.TILE_CODES}
_FRAME_PER = {
    "rows": {"type": "object", "properties": {"rows": {"type": "array", "items": {"type": "array", "items": _TILE}}},
             "required": ["rows"]},
    "grid": {"type": "object", "properties": {"tiles": {"type": "array", "items": {
        "type": "object", "properties": {"code": _TILE, "row": {"type": "integer"}, "col": {"type": "integer"}},
        "required": ["code", "row", "col"]}}}, "required": ["tiles"]},
}


def frame_prompt(kind: str, n: int) -> str:
    p = ob.last_multi_prompt(n)
    assert _LAST_RULE in p and _LAST_FIELDS in p
    return (p.replace(_LAST_RULE, "각 줄은 왼쪽에서 오른쪽으로 버립니다. 옆으로 눕혀진 패도 한 장입니다.")
            .replace(_LAST_FIELDS, _FRAME_FIELDS[kind]).replace("\n\n확신도(0~1)를 적어 주세요.", ""))


def frame_schema(kind: str, n: int) -> dict:
    keys = [f"photo{i + 1}" for i in range(n)]
    return {"type": "object", "properties": {**{k: _FRAME_PER[kind] for k in keys}, "notes": {"type": "string"}},
            "required": [*keys, "notes"]}


def last_from_rows(rows) -> tuple[str | None, bool]:
    """(마지막 패, 틀이 맞음 = 앞 줄은 모두 6장이고 마지막 줄 1~6장)."""
    rows = [[t for t in r if isinstance(t, str)] for r in rows or [] if r]
    if not rows:
        return None, False
    ok = all(len(r) == 6 for r in rows[:-1]) and 1 <= len(rows[-1]) <= 6
    return rows[-1][-1], ok


def last_from_grid(tiles) -> tuple[str | None, bool]:
    """줄마다 {칸: 패}. 덜 찬 줄 뒤에 줄이 있으면(앞 줄이 6장을 채우기 전엔 다음 줄이 없다) 칸이 겹치지 않을 때 앞 줄로 합친다.
    겹치면 틀을 못 정한 것(None, False)."""
    rows: dict[int, dict[int, str]] = {}
    for t in tiles or []:
        if isinstance(t, dict) and isinstance(t.get("row"), int) and isinstance(t.get("col"), int):
            rows.setdefault(t["row"], {})[t["col"]] = t.get("code")
    order = [rows[k] for k in sorted(rows)]
    i = 0
    while i < len(order) - 1:
        if len(order[i]) < 6:
            if set(order[i]) & set(order[i + 1]):
                return None, False
            order[i].update(order.pop(i + 1))
            continue
        i += 1
    if not order:
        return None, False
    last = order[-1]
    ok = all(len(r) == 6 for r in order[:-1])
    return last[max(last)], ok


def run(variant: str, crops: dict[str, bytes]) -> dict:
    sides = list(crops)
    datas = [crops[s] for s in sides]
    if variant in _FRAME_FIELDS:
        extra = [b.image_part(d, None) for d in datas[1:]] + [b.image_part(b.ref_sheet_set2(), None)]
        r = b.call(datas[0], frame_prompt(variant, len(sides)), frame_schema(variant, len(sides)), l3.MODEL, "low", None,
                   extra=extra)
        tiles, frame_ok = {}, {}
        for i, s in enumerate(sides):
            if "data" not in r:
                tiles[s], frame_ok[s] = "ERR", False
                continue
            ph = r["data"].get(f"photo{i + 1}") or {}
            t, ok = last_from_rows(ph.get("rows")) if variant == "rows" else last_from_grid(ph.get("tiles"))
            tiles[s], frame_ok[s] = t, ok
        return {"wall": r["s"], "tiles": tiles, "frame_ok": frame_ok,
                "calls": [{k: r.get(k) for k in ("s", "in", "out", "think", "error")}]}
    if variant == "server":  # 지금 서버 그대로
        r = b.call(datas[0], ob.last_multi_prompt(len(sides)), ob.last_multi_schema(len(sides)), l3.MODEL, "low", None,
                   extra=[b.image_part(d, None) for d in datas[1:]] + [b.image_part(b.ref_sheet_set2(), None)])
        tiles = {s: (l3.code((r["data"].get(f"photo{i + 1}") or {}).get("last_tile")) if "data" in r else "ERR")
                 for i, s in enumerate(sides)}
        return {"wall": r["s"], "tiles": tiles, "calls": [{k: r.get(k) for k in ("s", "in", "out", "think", "error")}]}
    prompt = base_prompt(len(sides))
    extra = [b.image_part(d, None) for d in datas[1:]]
    if variant == "guide":
        prompt = prompt.replace(ob.NOTATION, b.NOTATION_GUIDE)
    if variant in ("count6", "ref_count6"):
        prompt = _count6(prompt)
    if variant in ("ref", "ref_count6"):
        extra.append(b.image_part(b.ref_sheet_set2(), None))
        prompt = prompt.replace("\n\n확신도(0~1)를 적어 주세요.", REF_NOTE_LAST + "\n\n확신도(0~1)를 적어 주세요.")
    r = b.call(datas[0], prompt, ob.last_multi_schema(len(sides)), l3.MODEL, "low", None, extra=extra)
    tiles = {s: (l3.code((r["data"].get(f"photo{i + 1}") or {}).get("last_tile")) if "data" in r else "ERR")
             for i, s in enumerate(sides)}
    return {"wall": r["s"], "tiles": tiles, "calls": [{k: r.get(k) for k in ("s", "in", "out", "think", "error")}]}


def one(job):
    run_i, scene, photo = job
    d = b.G / scene / photo
    crops = {s: b.load(d / f"last_{s}.jpg", 1568) for s in l3.TRUTH[scene]}
    with ThreadPoolExecutor(len(VARIANTS)) as ex:
        futs = {v: ex.submit(run, v, crops) for v in VARIANTS}
        out = []
        for v, f in futs.items():
            r = f.result()
            ok = {s: r["tiles"][s] == t for s, t in l3.TRUTH[scene].items()}
            out.append({"run": run_i, "scene": scene, "photo": photo, "cond": v, **r, "ok": ok,
                        "all_ok": all(ok.values()), "ron_ok": ok[l3.RON[scene]]})
    print(f"{scene} {photo} #{run_i}  " + "  ".join(f"{o['cond']} {o['wall']:5.1f}s {sum(o['ok'].values())}/3" for o in out),
          flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--variants", default=",".join(VARIANTS))
    a = ap.parse_args()
    VARIANTS[:] = a.variants.split(",")
    path = b.OUT / "last3_opt.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    jobs = [(r, s, p) for r in range(a.runs) for s, ps in l3.PHOTOS.items() for p in ps]
    with ThreadPoolExecutor(a.workers) as ex:
        new = [o for out in ex.map(one, jobs) for o in out]
    old += new
    path.write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n변형    세 자리 모두  론 패   자리별      시간 중앙 / p90 / 최대   생각>0")
    for v in VARIANTS:
        rs = [r for r in new if r["cond"] == v]
        w = sorted(r["wall"] for r in rs)
        print(f"{v:6s} {sum(r['all_ok'] for r in rs):3d}/{len(rs)}  {sum(r['ron_ok'] for r in rs):3d}/{len(rs)}  "
              f"{sum(sum(r['ok'].values()) for r in rs):3d}/{3 * len(rs)}  {statistics.median(w):5.1f} / {w[int(.9 * len(w))]:5.1f} / {w[-1]:5.1f}   "
              f"{sum((r['calls'][0].get('think') or 0) > 0 for r in rs)}")
    print("\n틀린 답(변형·사진·자리: 읽은 것 → 정답)")
    from collections import Counter
    for v in VARIANTS:
        c = Counter((r["photo"], s, r["tiles"][s]) for r in new if r["cond"] == v for s, ok in r["ok"].items() if not ok)
        print(f"  {v}: " + ", ".join(f"{p} {s} {t}×{n}" for (p, s, t), n in sorted(c.items())))


if __name__ == "__main__":
    main()
