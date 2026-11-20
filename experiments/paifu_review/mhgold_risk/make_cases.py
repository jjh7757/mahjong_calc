"""mh_risk_cases.json 의 입력을 만든다(강을 자리별로 적고, 동가부터 차례로 섞는다).

토큰: "5m" 쯔모기리 모름(null) · "5m-" 쯔모기리 · "5m+" 손에서 냄 · 끝에 "r" 이 붙으면 리치 선언.
울기 "after": [자리, k] = 그 자리의 k 번째 버림(1부터) 바로 뒤. at = 그 버림의 전체 위치 + 1.
"""
import json
import re
import sys

SUITS = "mpsz"


def parse_group(s):
    out = []
    for m in re.finditer(r"(\d+)([mpsz])", s.replace(" ", "")):
        for d in m.group(1):
            d = int(d)
            su = SUITS.index(m.group(2))
            if d == 0:
                d = 5
            out.append(su * 9 + d - 1)
    return out


def parse_token(tok):
    m = re.fullmatch(r"(\d[mpsz])([+-]?)(r?)", tok)
    if not m:
        raise ValueError(tok)
    tile = m.group(1)
    tsumo = {"": None, "-": True, "+": False}[m.group(2)]
    return tile, tsumo, m.group(3) == "r"


def build(scene):
    dealer = scene["dealer"]
    rivers = {int(k): v.split() for k, v in scene["rivers"].items()}
    order = scene.get("order")
    discards = []
    pos = {}  # (seat, k) -> global index
    if order:
        # 명시 순서: 자리 번호 줄
        cnt = {s: 0 for s in range(4)}
        for s in order:
            tile, ts, r = parse_token(rivers[s][cnt[s]])
            cnt[s] += 1
            pos[(s, cnt[s])] = len(discards)
            discards.append([s, tile, ts, r])
        for s in range(4):
            assert cnt[s] == len(rivers.get(s, [])), (scene["name"], s)
    else:
        rounds = max(len(v) for v in rivers.values())
        for r_ in range(rounds):
            for i in range(4):
                s = (dealer + i) % 4
                lst = rivers.get(s, [])
                if r_ < len(lst):
                    tile, ts, r = parse_token(lst[r_])
                    pos[(s, r_ + 1)] = len(discards)
                    discards.append([s, tile, ts, r])
    melds = []
    for m in scene.get("melds", []):
        fs, k = m["after"]
        at = pos[(fs, k)] + 1
        d = {"seat": m["seat"], "kind": m["kind"], "tiles": m["tiles"], "at": at}
        if "upgraded_after" in m:
            us, uk = m["upgraded_after"]
            d["upgraded_at"] = pos[(us, uk)] + 1
        if m.get("red"):
            d["red"] = True
        melds.append(d)
    out = {
        "name": scene["name"],
        "note": scene.get("note", ""),
        "self": scene["self"],
        "dealer": dealer,
        "round_wind": scene.get("round_wind", "1z"),
        "hand": scene["hand"],
        "dora_indicators": scene.get("dora", ""),
        "unknown_tsumogiri": scene.get("unknown", "tedashi"),
        "discards": discards,
        "melds": melds,
    }
    if "ippatsu" in scene:
        out["ippatsu"] = scene["ippatsu"]
    # 장수 검사
    vis = [0] * 34
    for t in parse_group(out["hand"]):
        vis[t] += 1
    called = {m["at"] - 1 for m in melds if m["kind"] != "ankan"}
    for g, d in enumerate(discards):
        if g not in called:
            vis[parse_group(d[1])[0]] += 1
    for m in melds:
        for t in parse_group(m["tiles"]):
            vis[t] += 1
    for t in parse_group(out["dora_indicators"]):
        vis[t] += 1
    bad = [i for i in range(34) if vis[i] > 4]
    if bad:
        raise SystemExit(f"{scene['name']}: 5 장 이상 {bad} {vis}")
    for m in melds:
        if m["kind"] != "ankan":
            cd = discards[m["at"] - 1]
            if parse_group(cd[1])[0] not in parse_group(m["tiles"]):
                raise SystemExit(f"{scene['name']}: 울기 패가 가져온 버림과 다름 {m} {cd}")
    return out


S = []

# 1. 리치 1 명, 9 순, 일발 아님, 자(子). 손으로 셈(risk_test.dart).
S.append(dict(
    name="riichi1_turn9_basic", self=0, dealer=0,
    note="하가(1) 8번째 리치 → 9번째 쯔모기리, 순목 9, 배율 1. 4m 현물 0, 1m 스지19 1.8, 7m 스지37 5.5, 5p 무스지5 12.8, 6m 무스지46 13.1, 5s 반스지5 7.4, 4s 반스지46A 7.2, 백 역패 남은3 4.6, 발 역패 남은2 1.9, 1p 리치 뒤 통과 0",
    hand="23678m 34567p 2399s",
    rivers={
        0: "1z+ 9m+ 8p+ 2z+ 7p+ 1p+ 3z+ 2p+",
        1: "1z 9p 1s 9s 3z 4m+ 6p+ 2s+r 7z-",
        2: "2z 1m 4z 9m 5z 3s 8s 4p 4z",
        3: "9p 3z 6z 1s 2m 6z 7s 4z 1p",
    },
))

# 2. 리치 선언패가 마지막 버림 → 일발(7445/5172).
S.append(dict(
    name="riichi1_ippatsu", self=0, dealer=0,
    note="하가가 9번째에 리치, 그 뒤 울기 없음 → 일발 ×7445/5172",
    hand="23678m 34567p 2399s",
    rivers={
        0: "1z+ 9m+ 8p+ 2z+ 7p+ 1p+ 3z+ 2p+ 1m+",
        1: "1z 9p 1s 9s 3z 4m+ 6p+ 2s+ 7z+r",
        2: "2z 1m 4z 9m 5z 3s 8s 4p",
        3: "9p 3z 6z 1s 2m 6z 7s 4z",
    },
))

# 3. 리치한 사람이 친 → ×1.5.
S.append(dict(
    name="riichi_dealer", self=0, dealer=1,
    note="하가(1)가 친이고 리치 → ×1.5, 자풍 동",
    hand="2367m 345p 23499s 66z",
    rivers={
        1: "1z 9p 1s 9s 3z 4m+ 6p+ 2s+r 7z- 2z-",
        2: "2z 1m 4z 9m 5z 3s 8s 4p 4z 8m",
        3: "9p 3z 6z 1s 2m 6z 7s 4z 1p 7m",
        0: "1z+ 9m+ 8p+ 2z+ 7p+ 1p+ 3z+ 2p+ 9s+",
    },
))

# 4. 도라 배율.
S.append(dict(
    name="riichi_dora", self=0, dealer=0, dora="4p 6z",
    note="도라 5p(무스지5 ×14.9/12.8×78/58) · 중(역패)",
    hand="23678m 3467p 2399s",
    rivers={
        0: "1z+ 9m+ 8p+ 2z+ 7p+ 1p+ 3z+ 2p+",
        1: "1z 9p 1s 9s 3z 4m+ 6p+ 2s+r 1m-",
        2: "2z 1m 4z 9m 5z 3s 8s 4p 4z",
        3: "9p 3z 6z 1s 2m 6z 7s 2z 1p",
    },
))

# 5. 벽: 8s 4장 보임 → 9s NC·DNC, 5m 4장 → 37m 스지37.
S.append(dict(
    name="wall_nc_dnc", self=0, dealer=0,
    note="8s 벽(내 손 2 + 강 2) → 9s, 5m 벽 → 3m 7m 스지37",
    hand="12355m 345p 88s 666z",
    rivers={
        0: "1z+ 9m+ 8p+ 2z+ 7p+ 1p+ 3z+ 2p+",
        1: "1z 9p 1s 9s 3z 8s+ 5m+ 2s+r 4z-",
        2: "2z 1m 4z 9m 5z 5m 8s 4p 4z",
        3: "9p 3z 7z 1s 2m 7z 7s 2z 1p",
    },
))

# 6. 자패 남은 장수: 역패·객풍.
S.append(dict(
    name="honor_left_counts", self=0, dealer=0, round_wind="2z",
    note="장풍 남. 하가(1)는 남 자풍. 보이는 장수 동3 남3 서3 북2 백2 발4 중1 → 남(역패) 남은1 0.3, 서(객풍) 남은1 0.2, 북(객풍) 남은2 1.8, 백 남은2 1.9, 발 0, 동·중 현물 0",
    hand="234m 456p 2z 33z 4z 55z 66z",
    rivers={
        0: "1m+ 9m+ 8p+ 9p+ 7p+ 1p+ 6z+ 2p+",
        1: "1z 9p 1s 9s 6z 4m+ 6p+ 2s+r 7z-",
        2: "2z 1m 1z 9m 2z 3s 8s 4p 4m",
        3: "9p 3z 1s 1z 2m 7s 4z 1s 1p",
    },
))

# 7. 리치 2 명 합치기.
S.append(dict(
    name="riichi2_mixed", self=0, dealer=0,
    note="하가(1)·상가(3) 리치. r = r1 + r2 − r1·r2/100",
    hand="23678m 34567p 2399s",
    rivers={
        0: "1z+ 9m+ 8p+ 2z+ 7p+ 1p+ 3z+ 2p+",
        1: "1z 9p 1s 9s 3z 4m+ 6p+ 2s+r 7z-",
        2: "2z 1m 4z 9m 5z 3s 8s 4p 4z",
        3: "9p 3z 6z 1s 2m 6z 7s+r 4z- 1p-",
    },
))

# 8. 울기 1 개, 데다시를 앎.
S.append(dict(
    name="naki1_known", self=0, dealer=0,
    note="대면(2)이 0의 3번째 버림 중을 퐁. 퐁 뒤 첫 버림 4z(3번째) 다음 9m+ 5z+ 3s- 8s- 4p+ 4z- → 데다시 3. 9순 1울기 → 표[1][9][3]=58.60",
    hand="23678m 34567p 2399s",
    rivers={
        0: "1z+ 9m+ 7z+ 2z+ 7p+ 1p+ 3z+ 2p+ 8p+",
        1: "1z 9p 1s 9s 3z 4m 6p 2s 4z",
        2: "2z 1m 4z 9m+ 5z+ 3s- 8s- 4p+ 4z-",
        3: "9p 3z 6z 1s 2m 6z 7s 2z 1p",
    },
    melds=[dict(seat=2, kind="pon", tiles="777z", after=[0, 3])],
))

# 9~11. 같은 장면, 데다시 모름 처리 셋.
base_unknown = dict(
    self=0, dealer=0,
    hand="23678m 34567p 2399s",
    rivers={
        0: "1z+ 9m+ 7z+ 2z+ 7p+ 1p+ 3z+ 2p+ 8p+",
        1: "1z 9p 1s 9s 3z 4m 6p 2s 4z",
        2: "2z 1m 4z 9m 5z 3s 8s- 4p+ 4z",
        3: "9p 3z 6z 1s 2m 6z 7s 2z 1p",
    },
    melds=[dict(seat=2, kind="pon", tiles="777z", after=[0, 3])],
)
for pol, note in [
    ("tedashi", "퐁 뒤 9m? 5z? 3s? 8s- 4p+ 4z? — 모름 → 데다시: 5 → 표[1][9][5]=70.18"),
    ("tsumogiri", "모름 → 쯔모기리: 알려진 데다시 4p+ 하나 → 표[1][9][1]=41.25"),
    ("firstColumn", "모름이 있으면 0열 → 표[1][9][0]=30.11"),
]:
    S.append(dict(base_unknown, name=f"naki1_unknown_{pol}", unknown=pol, note=note))

# 12. 울기 3 개 + 도라 + 적5.
S.append(dict(
    name="naki3_dora_red", self=0, dealer=0, dora="4s",
    note="상가(3) 치 3-4-5s(적, 도라 5s) · 퐁 백 · 치 678p, 타점 3000×1.4^2=5880",
    hand="23678m 3457p 2399s",
    rivers={
        0: "1z+ 9m+ 3s+ 2z+ 5z+ 8p+ 3z+ 2p+ 1m+",
        1: "1z 9p 1s 9s 3z 4m 6p 2s 4z 2z",
        2: "2z 1m 4z 9m 1z 3s 8s 8p 4z 9p",
        3: "9p 3z 6z 1s 2m+ 6z+ 7s+ 7z+ 1p+ 6s+",
    },
    melds=[
        dict(seat=3, kind="chi", tiles="345s", after=[2, 6], red=True),
        dict(seat=3, kind="pon", tiles="555z", after=[0, 5]),
        dict(seat=3, kind="chi", tiles="678p", after=[2, 8]),
    ],
))

# 13. 울기 4 개(대명 단기) → 텐파이율 100, 무스지 빈 목록.
S.append(dict(
    name="naki4_hadaka", self=0, dealer=0,
    note="대면(2) 울기 4개 → 100",
    hand="2367m 3457p 239s 11z",
    rivers={
        0: "9m+ 1p+ 2z+ 5z+ 3z+ 6z+ 7z+ 8p+ 4m+ 1s+",
        1: "1z 9p 1s 9s 3z 4m 6p 2s 4z 5s",
        2: "2z 1m+ 4z+ 9m+ 2s+ 3s+",
        3: "9p 3z 6z 1s 2m 8m 7s 7z 1p 6s",
    },
    melds=[
        dict(seat=2, kind="pon", tiles="555z", after=[0, 4]),
        dict(seat=2, kind="pon", tiles="666z", after=[0, 6]),
        dict(seat=2, kind="pon", tiles="777z", after=[0, 7]),
        dict(seat=2, kind="chi", tiles="567s", after=[1, 10]),
    ],
))

# 14. 다마(멘젠 비리치) 12 순: 텐파이율 12 → 합칠 때 빠짐(≤15).
S.append(dict(
    name="dama_turn12_excluded", self=0, dealer=0,
    note="아무도 리치·울기 없음. 다마 텐파이율 = 버림 수 → 12·12·12, 합친 위험 0",
    hand="23678m 34567p 2399s",
    rivers={
        0: "1z+ 9m+ 8p+ 2z+ 7p+ 1p+ 3z+ 2p+ 1m+ 5z+ 7z+ 4z+",
        1: "1z 9p 1s 9s 3z 4m 6p 2s 7z 1m 6z 4z",
        2: "2z 1m 4z 9m 5z 3s 8s 4p 2z 7s 5z 8m",
        3: "9p 3z 6z 1s 2m 6z 7s 1z 1p 7z 2z 5z",
    },
))

# 15. 다마 16 순 → 텐파이율 16 > 15 로 합침에 들어감. 동순 후리텐(리치 아님) 안전패.
S.append(dict(
    name="dama_turn16_sameturn_furiten", self=0, dealer=0,
    note="16순 다마 → 합침에 들어감. 상가(3)의 마지막 버림 뒤 0 의 버림은 상가에게 안전(동순 후리텐)",
    hand="23678m 3456p 239s 5m",
    rivers={
        0: "1z+ 9m+ 8p+ 2z+ 7p+ 1p+ 3z+ 2p+ 1m+ 5z+ 7z+ 4z+ 9p+ 6z+ 3s+ 5s+ 6s+",
        1: "1z 9p 1s 9s 3z 4m 6p 2s 7z 1m 6z 4z 5z 9s 8m 4s",
        2: "2z 1m 4z 9m 5z 3s 8s 4p 2z 7s 5z 8m 6z 4s 1s 7m",
        3: "9p 3z 6z 1s 2m 3m 7s 1z 1p 7z 2z 8s 9s 8m 1z 4m",
    },
))

# 16. 깡한 패는 안전패(대명깡 · 안깡).
S.append(dict(
    name="kan_safe_tiles", self=0, dealer=0,
    note="하가(1) 안깡 5p · 대면(2) 대명깡 8m. 깡 패는 그 사람에게 안전, 남은 0 장",
    hand="23677m 3467p 2399s",
    rivers={
        0: "1z+ 9m+ 8m+ 2z+ 7p+ 1p+ 3z+ 2p+ 4z+",
        1: "1z 9p 1s 9s 3z 4m 6p 2s 7z",
        2: "2z 1m 4z 9m 5z 3s 8s 4p 6z",
        3: "9p 3z 6z 1s 2m 6z 7s 2z 1p",
    },
    melds=[
        dict(seat=1, kind="ankan", tiles="5555p", after=[1, 4]),
        dict(seat=2, kind="minkan", tiles="8888m", after=[0, 3]),
    ],
))

# 17. 이른 바깥패 겹침(×0.4 거듭).
S.append(dict(
    name="early_outside_stack", self=0, dealer=0,
    note="하가(1)가 1~5순에 3m 4m 7p 5s 2m → 바깥패 12m 123m 98p 37s 1m: 1m 스지19 1.8×0.4³=0.1152, 8p 9p 3s 7s ×0.4 (2m 3m 은 현물이라 0)",
    hand="56789m 3456p 2399s",
    rivers={
        0: "1z+ 9m+ 8m+ 2z+ 7p+ 1p+ 3z+ 2p+",
        1: "3m 4m 7p 5s 2m 6z+ 1z+ 4z+r 9s-",
        2: "2z 1m 4z 9m 5z 3s 8s 4p 6z",
        3: "9p 3z 6z 1s 2m 7z 7s 2z 1p",
    },
))

# 18. 순목 19 넘음 → 19 로 자름.
S.append(dict(
    name="turns_clamped_19", self=0, dealer=0,
    note="하가(1) 버림 20장, 13번째 리치 → 순목 19",
    hand="2367m 345p 2345s 7z",
    rivers={
        0: "1z+ 9m+ 8p+ 2z+ 7p+ 1p+ 3z+ 2p+ 1m+ 5z+ 6z+ 4z+ 9p+ 6z+ 3s+ 5s+ 6s+ 7s+ 8s+",
        1: "1z 9p 1s 9s 3z 4m 6p 2s 1m 6z 4z 9s 5z+r 8m- 4s- 7m- 2m- 5m- 8p- 1s-",
        2: "2z 1m 4z 9m 5z 3s 8s 4p 2z 7s 5z 8m 6z 4s 1s 7m 1p 3p 5m 9s",
        3: "9p 3z 1z 1s 2m 3z 7s 1z 1p 2z 6p 8s 9s 8m 4p 4m 3p 3m 4z 5m",
    },
))

# 19. 쯔모기리 리치 표시.
S.append(dict(
    name="tsumogiri_riichi", self=0, dealer=0,
    note="대면(2) 선언패 쯔모기리(true) · 하가(1) 선언패 모름(null)",
    hand="23678m 34567p 2399s",
    rivers={
        0: "1z+ 9m+ 8p+ 2z+ 7p+ 1p+ 3z+ 2p+",
        1: "1z 9p 1s 9s 3z 4m 6p 2sr 7z-",
        2: "2z 1m 4z 9m 5z 3s 8s 4p-r 4z-",
        3: "9p 3z 6z 1s 2m 6z 7s 2z 1p",
    },
))

# 20. 가깡이 일발을 끊음.
S.append(dict(
    name="kakan_breaks_ippatsu", self=0, dealer=0,
    note="하가(1) 9번째 리치. 그 뒤 대면(2) 가깡 → 일발 끊김(5172). 가깡 8s 는 대면에게 안전",
    hand="23678m 34567p 239s 2z",
    rivers={
        0: "1z+ 9m+ 8p+ 8s+ 7p+ 1p+ 3z+ 2p+ 1m+",
        1: "1z 9p 1s 9s 3z 4m+ 6p+ 2s+ 7z+r",
        2: "2z 1m 4z 9m 5z 3s 4p 2z",
        3: "9p 3z 6z 1s 2m 6z 7s 4z",
    },
    melds=[dict(seat=2, kind="kakan", tiles="8888s", after=[0, 4], upgraded_after=[1, 9])],
))

# 21. 내가 남가(자리 2), 친 3, 장풍 남 — 자리 번호 돌림 확인.
S.append(dict(
    name="self_seat2_rotation", self=2, dealer=3, round_wind="2z",
    note="나는 자리 2. 리치는 자리 0(친 3 기준 남가 → 자풍 남 = 장풍, 남은 역패)",
    hand="23678m 34567p 2399s",
    rivers={
        3: "1z 9m 8p 2z 7p 1p 3z 2p 6z",
        0: "1z 9p 1s 9s 3z+ 4m+ 6p+ 2s+r 7z-",
        1: "2z 1m 4z 9m 5z 3s 8s 4p 4z",
        2: "9p+ 3z+ 6z+ 1s+ 2m+ 6z+ 7s+ 4z+",
    },
))

cases = [build(s) for s in S]
doc = {
    "about": "Ported risk/tenpai (EndlessCheng/mahjong-helper 514bb97) 장면. 입력은 make_cases.py 로 만들었고, dart 는 lib/engine/risk.dart 출력, go 는 원본 util 함수 + core.go 상대별 계산을 옮긴 Go(mhgold_risk) 출력.",
    "schema": {
        "discards": "[자리, 패, 쯔모기리(true/false/null), 리치 선언] — 실제 순서",
        "melds": "at = 울었을 때까지의 전체 버림 수(치·퐁·대명깡은 discards[at-1] 을 가져감, 가깡은 처음 퐁한 때), upgraded_at = 가깡한 때",
        "risk34": "34칸 위험(%), 소수 6자리",
    },
    "cases": cases,
}
out = sys.argv[1]
# 기존 출력(dart/go)이 있으면 지키지 않고 입력만 새로 쓴다.
with open(out, "w", encoding="utf-8", newline="\n") as f:
    json.dump(doc, f, ensure_ascii=False, indent=1)
print(len(cases), "cases")
