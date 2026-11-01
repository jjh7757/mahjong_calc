"""점수 엔진 교차 검증: tool/engine_diff_corpus.dart 가 만든 답을 PyPI mahjong 과 비교한다.

    pip install mahjong==2.1.0
    C:\\Users\\jjh7757\\flutter\\bin\\dart run tool/engine_diff_corpus.dart 20000 1
    python tool/engine_diff.py [build/engine_diff/corpus.jsonl] [--show 5]

차이는 우리 버그일 수도 저쪽 버그·룰 차이일 수도 있다. 어느 쪽이 맞는지는 손으로 가린다.
점수·화료 여부 차이가 있으면 종료 코드 1. 역 이름만 다른 것은 보고만 한다.
"""
import argparse
import collections
import json
import sys

from mahjong.hand_calculating.hand import HandCalculator
from mahjong.hand_calculating.hand_config import HandConfig, HandConstants, OptionalRules
from mahjong.meld import Meld

# 우리 Yaku enum 이름 → mahjong 의 역 이름. 바람은 자풍·장풍을 자리별 클래스로 나눠 따로 맞춘다.
YAKU = {
    "riichi": "Riichi", "doubleRiichi": "Double Riichi", "ippatsu": "Ippatsu",
    "menzenTsumo": "Menzen Tsumo", "pinfu": "Pinfu", "tanyao": "Tanyao", "iipeikou": "Iipeiko",
    "haku": "Yakuhai (haku)", "hatsu": "Yakuhai (hatsu)", "chun": "Yakuhai (chun)",
    "haitei": "Haitei Raoyue", "houtei": "Houtei Raoyui", "rinshan": "Rinshan Kaihou",
    "chankan": "Chankan", "chanta": "Chantai", "ittsu": "Ittsu",
    "sanshokuDoujun": "Sanshoku Doujun", "sanshokuDoukou": "Sanshoku Doukou", "toitoi": "Toitoi",
    "sanankou": "San Ankou", "sankantsu": "San Kantsu", "chiitoitsu": "Chiitoitsu",
    "honroutou": "Honroutou", "shousangen": "Shou Sangen", "honitsu": "Honitsu",
    "junchan": "Junchan", "ryanpeikou": "Ryanpeikou", "chinitsu": "Chinitsu", "dora": "Dora",
    "akaDora": "Aka Dora", "uraDora": "Ura Dora", "kokushi": "Kokushi Musou",
    "kokushi13": "Kokushi Musou Juusanmen Matchi", "suuankou": "Suu Ankou",
    "suuankouTanki": "Suu Ankou Tanki", "daisangen": "Daisangen", "shousuushi": "Shousuushii",
    "daisuushi": "Dai Suushii", "tsuuiisou": "Tsuu Iisou", "chinroutou": "Chinroutou",
    "ryuuiisou": "Ryuuiisou", "chuuren": "Chuuren Poutou",
    "chuuren9": "Daburu Chuuren Poutou", "suukantsu": "Suu Kantsu", "tenhou": "Tenhou",
    "chiihou": "Chiihou",
}


def t34(code):
    n, s = int(code[0]), code[1]
    return {"m": 0, "p": 9, "s": 18, "z": 27}[s] + n - 1


class Ids:
    """34칸 → 136칸 번호. mahjong 은 5의 0번(16·52·88)을 적도라로 치므로, 적5 아닌 5에는 안 준다."""

    def __init__(self, reds):
        self.reds = set(reds)
        self.used = collections.defaultdict(set)

    def hand(self, t):
        order = [0, 1, 2, 3]
        if t in (4, 13, 22):
            order = [1, 2, 3, 0] if t not in self.reds else [0, 1, 2, 3]
        return self._take(t, order)

    def indicator(self, t):
        return self._take(t, [3, 2, 1, 0])

    def _take(self, t, order):
        for i in order:
            if i not in self.used[t]:
                self.used[t].add(i)
                return t * 4 + i
        raise ValueError(f"tile {t} over 4")


def reference(e, win_code=None):
    sit, rules = e["sit"], e["rules"]
    ids = Ids([t34(c) for c in e["reds"]])
    win = t34(win_code or e["win"])
    meld_tiles = []
    melds = []
    # 묶음의 패를 먼저 잡지 않는다: 적5 는 손패든 묶음이든 먼저 온 쪽에 간다(세는 값은 같다).
    tiles136 = []
    win136 = None
    for code in e["closed"]:
        t = t34(code)
        i = ids.hand(t)
        tiles136.append(i)
        if t == win and win136 is None:
            win136 = i
    for m in e["melds"]:
        first = t34(m["first"])
        if m["type"] == "chi":
            kinds, kind, opened = [first, first + 1, first + 2], Meld.CHI, True
        elif m["type"] == "pon":
            kinds, kind, opened = [first] * 3, Meld.PON, True
        else:
            kinds, kind, opened = [first] * 4, Meld.KAN, m["type"] == "openKan"
        got = [ids.hand(t) for t in kinds]
        meld_tiles.extend(got)
        melds.append(Meld(meld_type=kind, tiles=got, opened=opened))
    tiles136.extend(meld_tiles)
    dora = [ids.indicator(t34(c)) for c in sit["dora"]]
    ura = [ids.indicator(t34(c)) for c in sit["ura"]]
    dealer = sit["seat"] == "1z"
    config = HandConfig(
        is_tsumo=sit["tsumo"],
        is_riichi=sit["riichi"],
        is_daburu_riichi=sit["doubleRiichi"],
        is_ippatsu=sit["ippatsu"],
        is_haitei=sit["lastTile"] and sit["tsumo"],
        is_houtei=sit["lastTile"] and not sit["tsumo"],
        is_rinshan=sit["rinshan"],
        is_chankan=sit["chankan"],
        is_tenhou=sit["firstTurnWin"] and dealer,
        is_chiihou=sit["firstTurnWin"] and not dealer,
        player_wind=t34(sit["seat"]),
        round_wind=t34(sit["round"]),
        tsumi_number=sit["honba"],
        options=OptionalRules(
            has_open_tanyao=rules["kuitan"],
            has_aka_dora=rules["redDora"],
            has_double_yakuman=rules["doubleYakuman"],
            kiriage=rules["kiriage"],
            kazoe_limit=HandConstants.KAZOE_LIMITED if rules["kazoe"] else HandConstants.KAZOE_SANBAIMAN,
            fu_for_open_pinfu=True,
            fu_for_pinfu_tsumo=False,
        ),
    )
    return HandCalculator.estimate_hand_value(
        tiles136, win136, melds=melds or None, dora_indicators=dora,
        ura_dora_indicators=ura, config=config,
    )


def best_reference(e):
    """천화·지화는 우리 엔진처럼 모든 장을 화료패로 시험해 가장 높은 값을 고른다."""
    if not e["sit"]["firstTurnWin"]:
        return reference(e)
    results = [reference(e, c) for c in sorted(set(e["closed"]))]
    valid = [r for r in results if r.error is None]
    if not valid:
        return results[0]
    return max(valid, key=lambda r: (r.cost["total"], r.han, r.fu))


def payments(r, tsumo, dealer):
    c = r.cost
    if not tsumo:
        return {"ron": c["main"] + c["main_bonus"], "fromDealer": 0, "fromNonDealer": 0, "total": c["total"]}
    if dealer:
        return {"ron": 0, "fromDealer": 0, "fromNonDealer": c["main"] + c["main_bonus"], "total": c["total"]}
    return {"ron": 0, "fromDealer": c["main"] + c["main_bonus"],
            "fromNonDealer": c["additional"] + c["additional_bonus"], "total": c["total"]}


def our_yaku_names(ours):
    out = []
    for y in ours["yaku"]:
        if y in ("seatWind", "roundWind"):
            out.append(y)
        else:
            out.append(YAKU[y])
    return collections.Counter(out)


# 더블 역만을 끄면 우리는 1배 이름으로 바꾸고 mahjong 은 이름만 그대로 둔다(둘 다 1배로 계산).
SINGLE_YAKUMAN = {
    "Suu Ankou Tanki": "Suu Ankou",
    "Daburu Chuuren Poutou": "Chuuren Poutou",
    "Kokushi Musou Juusanmen Matchi": "Kokushi Musou",
}


def ref_yaku_names(r, double_yakuman):
    out = []
    for y in r.yaku or []:
        name = y.name
        if not double_yakuman:
            name = SINGLE_YAKUMAN.get(name, name)
        low = name.lower()
        if "yakuhai" in low and ("seat" in low or "round" in low):
            out.append("seatWind" if "seat" in low else "roundWind")
        else:
            out.append(name)
    return collections.Counter(out)


def compare(e):
    """(분류, 설명) 또는 None(일치)."""
    ours = e["ours"]
    r = best_reference(e)
    ref_valid = r.error is None
    if ours["valid"] != ref_valid:
        return "validity", f"ours={ours['error'] or 'OK'} ref={r.error or 'OK'}"
    if not ref_valid:
        ours_kind = "no_yaku" if ours["error"] == "역이 없습니다" else "hand_not_winning"
        if ours_kind != r.error:
            return "fail-reason", f"ours={ours['error']} ref={r.error}"
        return None
    sit = e["sit"]
    pay = payments(r, sit["tsumo"], sit["seat"] == "1z")
    diffs = [f"{k}: ours={ours[k]} ref={v}" for k, v in pay.items() if ours[k] != v]
    if diffs:
        return "payment", "; ".join(diffs) + f" | ours {ours['han']}han {ours['fu']}fu ref {r.han}han {r.fu}fu"
    yakuman = ours["yakuman"]
    if not yakuman and (ours["han"], ours["fu"]) != (r.han, r.fu):
        return "same-payment-breakdown", f"ours {ours['han']}han {ours['fu']}fu ref {r.han}han {r.fu}fu"
    a, b = our_yaku_names(ours), ref_yaku_names(r, e["rules"]["doubleYakuman"])
    if a != b:
        return "yaku", f"only ours={sorted((a - b).elements())} only ref={sorted((b - a).elements())}"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus", nargs="?", default="build/engine_diff/corpus.jsonl")
    ap.add_argument("--show", type=int, default=5, help="분류별로 보여 줄 예")
    ap.add_argument("--diffs", help="차이 전체를 JSONL 로 저장")
    args = ap.parse_args()

    total = valid = 0
    kinds = collections.Counter()
    yaku_seen = collections.Counter()
    by_kind = collections.defaultdict(list)
    out = open(args.diffs, "w", encoding="utf-8") if args.diffs else None
    with open(args.corpus, encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            total += 1
            valid += e["ours"]["valid"]
            yaku_seen.update(e["ours"]["yaku"])
            try:
                d = compare(e)
            except Exception as ex:  # 저쪽이 못 받는 입력도 분류해서 본다
                d = ("crash", repr(ex))
            if d is None:
                continue
            kinds[d[0]] += 1
            by_kind[d[0]].append((d[1], e))
            if out:
                out.write(json.dumps({"kind": d[0], "detail": d[1], **e}, ensure_ascii=False) + "\n")
    if out:
        out.close()

    print(f"전체 {total}건, 우리 쪽 화료 {valid}건, 일치 {total - sum(kinds.values())}건")
    print("차이:", dict(kinds) if kinds else "없음")
    missing = sorted(set(YAKU) - set(yaku_seen))
    print("코퍼스에 안 나온 역:", missing if missing else "없음")
    print("적게 나온 역:", yaku_seen.most_common()[:-9:-1])
    for kind, items in by_kind.items():
        print(f"\n== {kind} ({len(items)}건)")
        for detail, e in items[: args.show]:
            melds = " ".join(f"{m['type']}:{m['first']}" for m in e["melds"])
            s = e["sit"]
            flags = [k for k in ("riichi", "doubleRiichi", "ippatsu", "lastTile", "rinshan", "chankan", "firstTurnWin") if s[k]]
            print(f"  #{e['id']} [{e['profile']}] {' '.join(e['closed'])} win={e['win']} {melds} reds={e['reds']}")
            print(f"     {'tsumo' if s['tsumo'] else 'ron'} seat={s['seat']} round={s['round']} {flags} dora={s['dora']} ura={s['ura']} honba={s['honba']} rules={e['rules']}")
            print(f"     ours={e['ours']['yaku']}")
            print(f"     {detail}")
    hard = sum(v for k, v in kinds.items() if k in ("validity", "payment", "crash"))
    sys.exit(1 if hard else 0)


if __name__ == "__main__":
    main()
