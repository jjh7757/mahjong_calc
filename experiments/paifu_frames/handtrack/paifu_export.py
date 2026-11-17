"""한 판을 앱 패보 재생 화면용 JSON 으로 내보내기(2026-11-17).

  python -X utf8 paifu_export.py r11_130921      → assets/paifu/r11_130921.json

범위: hero(화료자) 한 사람의 매 순 손패 + 네 자리 모두의 버림.
- hero 손패: rebuild.py 와 같은 로직(사용자 정답 answers_user.json 으로 끝 손패에서 거꾸로 복원). 녹화 전 버림(first_i-1장)은 손패 모름.
- 다른 자리 강: 화료 사진 라벨(tile_classifier/data/v1114/dr/final/<판>.json 의 win_* 그림, role river·meld, seat=그림 쪽)
  상자 중심을 자리마다 (u = 중심→그 사람, v = 그 사람 왼→오른) 축으로 돌려 "줄(u 오름) → 줄 안(v 오름)" 으로 늘어놓음.
  hero 쪽 강(game.json river_final, 순서 앎)으로 방향 규칙을 먼저 검증.
- 울기: meld 라벨(누운 패 위치로 어느 자리에서 가져왔나), 울려 나간 패가 몇 번째 버림이었는지는 앞 프레임 라벨(울기 생기기 전·후 강 장수)로 정함.
- 시간 순서: 친부터 0,1,2,3 차례 규칙으로 엮고, 운 자리가 바로 버린 뒤 다음 자리로.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402

BASE = hc.WORK / "testtruth_1116"
DR = hc.EXP / "tile_classifier" / "data" / "v1114" / "dr" / "final"
ASSETS = hc.ROOT / "assets" / "paifu"

# 그림 쪽별 (u, v): u = 탁자 중심에서 그 쪽 사람으로(강 줄이 늘어나는 방향), v = 그 사람이 볼 때 왼→오른
UV = {"bottom": ((0, 1), (1, 0)), "right": ((1, 0), (0, -1)), "top": ((0, -1), (-1, 0)), "left": ((-1, 0), (0, 1))}
SIDES_CCW = ["bottom", "right", "top", "left"]  # 차례 순서(반시계) — bottom_seat 다음 자리가 right

# 판별 손 설정: 제목
TITLES = {"r11_130921": "2026-11-14 2반장 동1국"}


# ---------- hero 손패 복원(rebuild.py main 의 로직 그대로, 출력 대신 목록으로) ----------
def rebuild_turns(gid: str, game: dict):
    fh = game["final_hand"]
    g = next(x for x in hc.jload(BASE / "turns.json")["games"] if x["id"] == gid)
    ans = hc.jload(BASE / "answers_user.json")
    row = list(fh["closed"])
    out = []
    for t in reversed(g["turns"]):
        a = ans.get(t["id"]) or {}
        x = t["tile"]
        after = list(row)
        if a.get("kind") == "tsumogiri":
            out.append(dict(turn=t, tsumogiri=True, draw=x, discard=x, before=list(row), after=after))
            continue
        if a.get("kind") != "hand" or a.get("k") is None or a.get("j") is None:
            raise SystemExit(f"{t['id']}: 답이 '{a.get('kind')}' — 복원 끊김, 내보내기 중단")
        if a.get("insert_first"):
            r14 = row[:a["k"] - 1] + [x] + row[a["k"] - 1:]
            for m in reversed(a.get("moves") or []):
                i, j = m["swap"]
                r14[i - 1], r14[j - 1] = r14[j - 1], r14[i - 1]
            d = r14.pop(a["j"] - 1)
            row = r14
        else:
            jc = a.get("j_closed")
            d = row[jc - 1]
            rest = row[:jc - 1] + row[jc:]
            row = rest[:a["k"] - 1] + [x] + rest[a["k"] - 1:]
        out.append(dict(turn=t, tsumogiri=False, draw=d, discard=x, before=list(row), after=after))
    return list(reversed(out)), g["first_i"]


# ---------- 사진 라벨에서 자리별 강·울기 ----------
def is_sideways(b, side):
    w, h = b["rect"][1][:2]
    upright_wide = side in ("left", "right")  # 왼·오른 자리 패는 그림에서 가로로 긴 게 바로 놓인 것
    return (w > h) != upright_wide


def order_river(boxes, side, gap=45):
    (ux, uy), (vx, vy) = UV[side]
    pts = sorted(((b["rect"][0][0] * ux + b["rect"][0][1] * uy, b["rect"][0][0] * vx + b["rect"][0][1] * vy, b) for b in boxes), key=lambda p: p[0])
    rows, cur = [], []
    for p in pts:
        if cur and p[0] - cur[-1][0] > gap:
            rows.append(cur)
            cur = []
        cur.append(p)
    if cur:
        rows.append(cur)
    out = []
    for r in rows:
        r.sort(key=lambda p: p[1])
        out += [dict(tile=p[2]["tile"], sideways=is_sideways(p[2], side)) for p in r]
    return out


def side_boxes(im, role, side):
    return [b for b in im["boxes"] if b.get("role") == role and b.get("seat") == side]


def meld_from(im, side, side_to_seat):
    """울기 한 묶음: 패 목록(그 사람 왼→오른), 누운 패 위치 → 가져온 자리."""
    bs = side_boxes(im, "meld", side)
    if not bs:
        return None
    (vx, vy) = UV[side][1]
    bs.sort(key=lambda b: b["rect"][0][0] * vx + b["rect"][0][1] * vy)
    tiles = [b["tile"] for b in bs]
    sw = [i for i, b in enumerate(bs) if is_sideways(b, side)]
    assert len(sw) == 1, (side, tiles, sw)
    seat = side_to_seat[side]
    # 누운 패가 왼쪽 = 윗집(seat-1), 가운데 = 맞은편(seat+2), 오른쪽 = 아랫집(seat+1)  — 퐁 3장 기준
    rel = {0: 3, 1: 2, len(bs) - 1: 1}[sw[0]]
    kind = "pon" if len(bs) == 3 and len(set(tiles)) == 1 else ("kan" if len(bs) == 4 else "chi")
    return dict(seat=seat, kind=kind, frm=(seat + rel) % 4, tiles=tiles, called=tiles[sw[0]])


def norm(t):
    return t[0].replace("0", "5") + t[1]


def main():
    gid = sys.argv[1]
    game = hc.jload(hc.OUT / gid / "game.json")
    lab = game["label_sources"]["label_json"]["label"]
    meta = game["label_sources"]["label_json"]["meta_game"]
    bottom = meta["bottom_seat"]
    side_to_seat = {s: (bottom + i) % 4 for i, s in enumerate(SIDES_CCW)}
    seat_to_side = {v: k for k, v in side_to_seat.items()}
    hero = lab["winner"]
    assert seat_to_side[hero] == game["winner_side"], (seat_to_side, game["winner_side"])

    drj = hc.jload(DR / f"{gid}.json")
    ims = [im for im in drj["images"] if im["kind"] == "win"]
    assert len(ims) == 1
    win = ims[0]
    assert win["winner"] == seat_to_side[hero]

    # 1) 방향 규칙을 hero 강으로 검증
    hero_side = seat_to_side[hero]
    hr = order_river(side_boxes(win, "river", hero_side), hero_side)
    assert [x["tile"] for x in hr] == game["river_final"], ([x["tile"] for x in hr], game["river_final"])
    hr_side = [i for i, x in enumerate(hr) if x["sideways"]]
    assert [hr[i]["tile"] for i in hr_side] == [game["riichi_seen_in_river"]["tile"]], hr_side
    print(f"방향 규칙 검증: hero({hero_side}) 강 {len(hr)}장 순서 = game.json river_final, 누운 패 {hr[hr_side[0]]['tile']} = 리치 선언패 ✓")

    rivers = {side_to_seat[s]: order_river(side_boxes(win, "river", s), s) for s in SIDES_CCW}
    melds = [m for m in (meld_from(win, s, side_to_seat) for s in SIDES_CCW) if m]

    # 2) 울려 나간 패가 그 자리 몇 번째 버림이었나
    #    hero: game.json river_called_away 의 칸(row, col) → 그 칸 번호
    #    다른 자리: 프레임 라벨에서 울기가 처음 보인 프레임 직전·직후 강 장수(울려 나간 패는 강에 안 남음)
    frames_ = [im for im in drj["images"] if im["kind"] == "frame"]
    called_at = {}  # (from_seat) -> list of (index 1-based in that seat's discards, tile)
    for m in melds:
        fs = m["frm"]
        if fs == hero:
            ca = [c for c in game["river_called_away"] if c["tile"] == m["called"]]
            assert len(ca) == 1, ca
            idx = (ca[0]["row"] - 1) * 6 + ca[0]["col"]
            how = f"game.json river_called_away 칸 {ca[0]['row']}줄 {ca[0]['col']}번째"
        else:
            fside, mside = seat_to_side[fs], seat_to_side[m["seat"]]
            seen = [(im["id"], bool(side_boxes(im, "meld", mside)), len(side_boxes(im, "river", fside))) for im in frames_]
            k = next(i for i, x in enumerate(seen) if x[1])
            pre, post = seen[k - 1], seen[k]
            assert not pre[1] and pre[2] == post[2], (pre, post)
            idx = post[2] + 1  # 울기 직전 프레임과 직후 프레임의 강 장수가 같음 → 그 사이 버림은 울려 나간 그 한 장뿐
            how = f"프레임 {pre[0].split('/')[-1]} 강 {pre[2]}장·울기 없음 → {post[0].split('/')[-1]} 강 {post[2]}장·울기 있음"
        called_at.setdefault(fs, []).append((idx, m["called"]))
        print(f"울기: 자리 {m['seat']}({seat_to_side[m['seat']]}) {m['kind']} {' '.join(m['tiles'])} ← 자리 {fs} 의 {idx}번째 버림 ({how})")

    # 자리별 버림 목록(울려 나간 패 끼움)
    discards = {}
    for s in range(4):
        lst = [dict(tile=x["tile"], riichi=x["sideways"], called=False) for x in rivers[s]]
        for idx, t in sorted(called_at.get(s, [])):
            lst.insert(idx - 1, dict(tile=t, riichi=False, called=True))
        discards[s] = lst
        assert sum(x["riichi"] for x in lst) <= 1
        print(f"자리 {s}({seat_to_side[s]}) 버림 {len(lst)}장(강 {len(rivers[s])} + 울려 나감 {len(called_at.get(s, []))}): "
              + " ".join(x["tile"] + ("(리치)" if x["riichi"] else "") + ("(울림)" if x["called"] else "") for x in lst))
    # 리치 자리 = 라벨 riichi_seats
    assert sorted(s for s in range(4) if any(x["riichi"] for x in discards[s])) == sorted(lab["riichi_seats"])

    # 3) hero 차례별 손패
    turns, first_i = rebuild_turns(gid, game)
    hd = discards[hero]
    assert [x["tile"] for x in hd[first_i - 1:]] == [t["discard"] for t in turns], "hero 차례 목록 ≠ 강"
    assert [x["tile"] for x in hd[:first_i - 1]] == game["river_before_ready"]
    hero_info = [None] * (first_i - 1) + turns

    # 4) 차례 규칙으로 엮기
    events = []
    pos = {s: 0 for s in range(4)}
    riichi_done = {s: False for s in range(4)}
    seat = meta["dealer"]
    drew = True  # 다음 자리가 뽑고 버림(울면 False)
    loser, win_tile = lab["loser"], lab["win_tile"]
    total = sum(len(v) for v in discards.values())
    while sum(pos.values()) < total:
        assert pos[seat] < len(discards[seat]), f"자리 {seat} 차례인데 버림이 바닥남 — 장수 안 맞음 {pos}"
        d = discards[seat][pos[seat]]
        ev = {"type": "discard", "seat": seat, "tile": d["tile"]}
        if seat == hero:
            info = hero_info[pos[seat]]
            if drew:
                events.append({"type": "draw", "seat": hero, "tile": info["draw"] if info else None, "hand": info["before"] if info else None})
            ev["tsumogiri"] = info["tsumogiri"] if info else None
        else:
            ev["tsumogiri"] = True if riichi_done[seat] else None
        ev["riichi"] = d["riichi"]
        if seat == hero:
            ev["hand"] = info["after"] if info else None
        events.append(ev)
        if d["riichi"]:
            riichi_done[seat] = True
        pos[seat] += 1
        nxt = (seat + 1) % 4
        drew = True
        if d["called"]:
            m = next(m for m in melds if m["frm"] == seat and m["called"] == d["tile"])
            events.append({"type": "call", "seat": m["seat"], "kind": m["kind"], "from": seat, "tiles": m["tiles"]})
            nxt = m["seat"]
            drew = False
            if nxt == hero:
                raise SystemExit("hero 울기는 아직 안 다룸")
        seat = nxt
    last = events[-1]
    assert last["type"] == "discard" and last["seat"] == loser and last["tile"] == win_tile, last
    for s in range(4):
        assert pos[s] == len(discards[s])
    print(f"엮기: 버림 {total}장이 차례 규칙으로 남김없이 맞음, 마지막 = 자리 {loser} 의 {win_tile}(론) ✓")

    # 5) 검증
    for t in turns:
        c = Counter(t["before"]) + Counter([t["draw"]])
        c -= Counter([t["discard"]])
        assert c == Counter(t["after"]) and len(t["after"]) == 13, t["turn"]["id"]
    final = game["final_hand"]["closed"]
    assert turns[-1]["after"] == final
    hd_ev = [e for e in events if e["type"] == "discard" and e["seat"] == hero]
    ri = next(i for i, e in enumerate(hd_ev) if e["riichi"])
    assert all(e["tsumogiri"] is True for e in hd_ev[ri + 1:]), "리치 뒤 hero 버림 중 쯔모기리 아닌 것"
    cnt = Counter(norm(e["tile"]) for e in events if e["type"] == "discard")
    for m in melds:
        cnt += Counter(norm(t) for t in m["tiles"])
        cnt -= Counter([norm(m["called"])])  # 울린 패는 버림에서 이미 셈
    cnt += Counter(norm(t) for t in final)  # 화료패 8m 은 자리 0 버림에서 이미 셈
    cnt += Counter(norm(t) for t in lab["dora_indicators"] + lab["ura_indicators"])
    over = {k: v for k, v in cnt.items() if v > 4}
    assert not over, over
    reds = Counter(e["tile"] for e in events if e["type"] == "discard" and e["tile"][0] == "0") + Counter(t for t in final if t[0] == "0")
    assert all(v <= 1 for v in reds.values()), reds
    print(f"검증: hero 차례 {len(turns)}개 패 구성 ✓, 끝 손패 = result.hand ✓, 리치 뒤 hero 버림 {len(hd_ev) - ri - 1}장 모두 쯔모기리 ✓, 4장 넘는 패 없음(최대 {max(cnt.values())}) ✓")
    print("  4장 다 보이는 패:", " ".join(sorted(k for k, v in cnt.items() if v == 4)))

    out = {
        "version": 1,
        "id": gid,
        "title": TITLES.get(gid, f"{gid} {lab['round']}"),
        "round": lab["round"],
        "honba": lab["honba"],
        "dealer": meta["dealer"],
        "hero": hero,
        "names": meta["names"],
        "dora_indicators": lab["dora_indicators"],
        "ura_indicators": lab["ura_indicators"],
        "note": (f"내 손패는 사람이 적은 정답으로 복원한 것(첫 {first_i - 1}순은 녹화 전이라 없음). "
                 "다른 자리는 버린 패만 있고 서로의 순서는 차례 규칙으로 맞춤, 쯔모기리는 리치 뒤만 표시."),
        "events": events,
        "result": {"type": "tsumo" if lab["is_tsumo"] else "ron", "winner": hero, "loser": None if lab["is_tsumo"] else loser,
                   "win_tile": win_tile, "hand": final, "melds": lab["melds"]},
    }
    ASSETS.mkdir(parents=True, exist_ok=True)
    p = ASSETS / f"{gid}.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"쓴 파일: {p} (events {len(events)}개)")


if __name__ == "__main__":
    main()
