/// 패보 한 시점 → mahjong-helper 옮긴 엔진의 입력.
///
/// - [discardContextAt]: hero 버림 직전 → [DiscardContext](lib/engine/discard_rank.dart, 버림 순위).
/// - [riskContextAt]: hero 버림 직전 → [RiskContext](lib/engine/risk.dart, 방총 위험도).
///
/// 패보에 없어서 기본값을 쓰는 입력(바꾸면 결과가 달라질 수 있음):
/// - **장풍**: 패보에 칸이 없어 국 이름("남2국")의 첫 글자로 읽는다([roundWindOf]). 못 읽으면 동.
/// - **도라 표시패**: [Paifu.doraIndicators] 만 쓴다(뒷도라 [Paifu.uraIndicators] 는 넣지 않음 — 버릴 때는 안 보임).
///   패보는 표시패가 **언제 열렸는지** 적지 않아, 국 중간에 깡으로 열린 깡도라도 처음부터 보였던 것으로 친다.
/// - **남은 쯔모 수**(DiscardContext.leftDrawTiles): 패보에 없다. `wallLeft ~/ 4` 로 어림한다(엔진은 출력에 싣기만 함).
/// - **남의 쯔모기리**: 패보에서 대부분 null. RiskContext 의 [UnknownTsumogiri] 정책(기본 tedashi — 손에서 낸 것으로 셈)에 맡긴다.
/// - **일발**: 따로 넣지 않고(ippatsu = null) 엔진이 버림·울기 순서에서 헤아리게 둔다.
/// - **울기 종류를 모름**(kind = "call"): 묶음 패로 가늠한다 — 같은 패 3장 퐁, 연속 3장 치, 같은 패 4장 대명깡.
///   그 밖(가져간 한 장만 적힌 경우 등): hero 울기면 DiscardContext 를 만들지 않고(null), 남의 울기면 위험도에는 퐁으로 넣는다.
/// - **안깡**: kind "ankan", 또는 kind "kan" 인데 from 이 없거나 자기 자리면 안깡으로 본다.
/// - **가깡 묶음 패가 한 장만 적힌 경우**: 깡 종류는 패 종류 하나로 정해지므로 4장으로 채운다(위험도 쪽). 보이는 패 세기는
///   지금 평가기([reviewPaifu])와 같은 값을 받아 쓴다.
library;

import '../engine/discard_rank.dart';
import '../engine/meld.dart';
import '../engine/risk.dart';
import '../engine/tile.dart';
import 'paifu.dart';
import 'paifu_score.dart' show roundWindOf;

bool _valid(int t) => t >= 0 && t < Tiles.count;

/// 패보 울기 한 묶음의 종류(엔진 [MeldKind] 로). 가늠할 수 없으면 null.
///
/// [seat] 은 운 자리, [from] 은 가져온 자리(없으면 null).
MeldKind? meldKindOf(String kind, List<PaifuTile> tiles, int seat, int? from) {
  switch (kind) {
    case 'chi':
      return MeldKind.chi;
    case 'pon':
      return MeldKind.pon;
    case 'ankan':
      return MeldKind.ankan;
    case 'minkan':
      return MeldKind.minkan;
    case 'kakan':
      return MeldKind.kakan;
    case 'kan':
      return (from == null || from == seat) ? MeldKind.ankan : MeldKind.minkan;
  }
  // 'call'(종류 모름) 등: 묶음 패로 가늠.
  final ts = [for (final t in tiles) t.tile]..sort();
  if (ts.length == 4 && ts.every((t) => t == ts.first)) return MeldKind.minkan;
  if (ts.length == 3 && ts.every((t) => t == ts.first)) return MeldKind.pon;
  if (ts.length == 3 &&
      ts.first < 27 &&
      ts[1] == ts[0] + 1 &&
      ts[2] == ts[0] + 2 &&
      Tiles.suit(ts[0]) == Tiles.suit(ts[2])) {
    return MeldKind.chi;
  }
  return null;
}

/// 패보 울기 → 엔진 [Meld](DiscardContext 용). 만들 수 없으면 null.
Meld? engineMeldOf(PaifuMeld m, int seat) {
  if (m.tiles.isEmpty || m.tiles.any((t) => !_valid(t.tile))) return null;
  final kind = meldKindOf(m.kind, m.tiles, seat, m.from);
  if (kind == null) return null;
  final ts = [for (final t in m.tiles) t.tile]..sort();
  try {
    return switch (kind) {
      MeldKind.chi => ts.length == 3 ? Meld.chi(ts.first) : null,
      MeldKind.pon => Meld.pon(ts.first),
      MeldKind.ankan => Meld.closedKan(ts.first),
      MeldKind.minkan || MeldKind.kakan => Meld.openKan(ts.first),
    };
  } on ArgumentError {
    return null;
  }
}

/// hero 의 [eventIndex] 번 버림 직전 → [DiscardContext].
///
/// - [handBefore]: 버리기 전 닫힌 손패(뽑은 패 포함, `14 − 3 × 울기` 장). 적5 수를 여기서 센다.
/// - [visible34]: 손패 밖에 보이는 패(강 — 울려 나간 것 빼고, 모든 울기 묶음, 도라 표시패). 지금 평가기와 같은 값.
///
/// hero 울기를 엔진 묶음으로 바꿀 수 없으면 null.
DiscardContext? discardContextAt(
  Paifu p,
  int eventIndex, {
  required List<PaifuTile> handBefore,
  required List<int> visible34,
}) {
  final hero = p.hero;
  final st = p.states[eventIndex];
  final hand34 = List<int>.filled(Tiles.count, 0);
  final red = [0, 0, 0];
  void countRed(PaifuTile t) {
    if (t.red && t.tile < 27 && t.tile % 9 == 4) red[t.tile ~/ 9]++;
  }

  for (final t in handBefore) {
    if (!_valid(t.tile)) return null;
    hand34[t.tile]++;
    countRed(t);
  }
  final melds = <Meld>[];
  for (final m in st.melds[hero]) {
    final e = engineMeldOf(m, hero);
    if (e == null) return null;
    melds.add(e);
    m.tiles.forEach(countRed);
  }
  return DiscardContext(
    hand34: hand34,
    melds: melds,
    visible34: List.of(visible34),
    doraIndicators: [
      for (final t in p.doraIndicators)
        if (_valid(t.tile)) t.tile,
    ],
    redFives: red,
    roundWind: roundWindOf(p.round),
    seatWind: Tiles.east + p.windOf(hero),
    isDealer: hero == p.dealer,
    selfDiscards: [
      for (final r in st.rivers[hero])
        if (_valid(r.tile.tile)) r.tile.tile,
    ],
    leftDrawTiles: st.wallLeft ~/ 4,
  );
}

/// [eventIndex] 번 사건 직전(그 사건은 넣지 않음) 탁자 → [RiskContext]. 나 = hero.
///
/// - 버림: 네 자리 버림 사건을 실제 순서대로(쯔모기리 bool? · 리치 선언 표시 그대로).
/// - 울기: 시점 `at` = 그 울기 앞에 놓인 버림 수. 가깡은 앞서 한 퐁을 찾아 kind = kakan · `at` = 퐁한 때 ·
///   `upgradedAt` = 가깡한 때로 바꾼다(퐁을 못 찾으면 가깡한 때를 `at` 으로). 적5 는 묶음 안의 적5 표시.
/// - [handBefore]: hero 닫힌 손패(뽑은 패 포함). 모르면 null — 그러면 남은 장수에 hero 손패가 빠진다.
/// - [visible34]: hero 손패 밖에 보이는 패(지금 평가기와 같은 셈). 주면 `hand + visible` 을 엔진에 직접 넘긴다.
RiskContext riskContextAt(
  Paifu p,
  int eventIndex, {
  List<PaifuTile>? handBefore,
  List<int>? visible34,
  UnknownTsumogiri unknownTsumogiri = UnknownTsumogiri.tedashi,
}) {
  final discards = <RiskDiscard>[];
  final melds = <RiskMeld>[];
  for (var j = 0; j < eventIndex && j < p.events.length; j++) {
    final e = p.events[j];
    switch (e.type) {
      case PaifuEventType.draw:
        break;
      case PaifuEventType.discard:
        final t = e.tile;
        if (t == null || !_valid(t.tile)) continue;
        discards.add(RiskDiscard(e.seat, t.tile, tsumogiri: e.tsumogiri, riichi: e.riichi));
      case PaifuEventType.call:
        final tiles = [
          for (final t in e.callTiles)
            if (_valid(t.tile)) t,
        ];
        if (tiles.isEmpty) continue;
        final kind = meldKindOf(e.callKind ?? 'pon', tiles, e.seat, e.from) ?? MeldKind.pon;
        final red = tiles.any((t) => t.red);
        final first = tiles.first.tile;
        final at = discards.length;
        if (kind == MeldKind.kakan) {
          final pon = melds.indexWhere((m) => m.seat == e.seat && m.kind == MeldKind.pon && m.tiles.first == first);
          if (pon >= 0) {
            final old = melds[pon];
            melds[pon] = RiskMeld(e.seat, MeldKind.kakan, List.filled(4, first),
                at: old.at, upgradedAt: at, red: old.red || red);
            continue;
          }
        }
        final List<int> ts;
        if (kind.isKan) {
          ts = List.filled(4, first);
        } else if (kind == MeldKind.pon && tiles.length != 3) {
          ts = [for (final t in tiles) t.tile]; // 가져간 한 장만 적힌 '종류 모름' 울기: 지어내지 않는다.
        } else {
          ts = [for (final t in tiles) t.tile]..sort();
        }
        melds.add(RiskMeld(e.seat, kind, ts, at: at, red: red));
    }
  }
  List<int>? hand34;
  if (handBefore != null) {
    hand34 = List<int>.filled(Tiles.count, 0);
    for (final t in handBefore) {
      if (_valid(t.tile)) hand34[t.tile]++;
    }
  }
  List<int>? v;
  if (visible34 != null) {
    v = [for (var t = 0; t < Tiles.count; t++) visible34[t] + (hand34?[t] ?? 0)];
  }
  return RiskContext(
    selfSeat: p.hero,
    dealer: p.dealer,
    roundWindTile: roundWindOf(p.round),
    discards: discards,
    melds: melds,
    doraIndicators: [
      for (final t in p.doraIndicators)
        if (_valid(t.tile)) t.tile,
    ],
    hand34: hand34,
    visible34: v,
    unknownTsumogiri: unknownTsumogiri,
  );
}
