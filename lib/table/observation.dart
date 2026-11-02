/// 관찰 JSON: 모델이 본 것만 담는다(서버 `/v2/*`). 리치·울기 종류·강 끝 패·도라 판단은 여기 코드가 한다. 순수 Dart.
///
/// ```json
/// {"players": {"bottom": {"hand": {"face_up": true, "tiles": [...], "separate_tile": null},
///                         "melds": [{"tiles": ["6z","6z","6z"], "sideways": [1], "face_down": []}],
///                         "river": [{"tile": "1p", "sideways": false}, ...], "riichi_stick": false}, ...},
///  "dora_indicators": ["9s", "5s"]}
/// ```
/// 판단은 [toHandReading]·[toCenterReading] 으로 기존 병합([mergeReading])에 넘긴다.
library;

import '../engine/calculator.dart' show Tiles;
import 'table_layout.dart';
import 'table_reading.dart';

/// 울기 묶음 하나. 종류는 [type] 이 패 구성으로 정한다.
class ObservedMeld {
  final List<ReadTile> tiles;
  final List<int> sideways;
  final List<int> faceDown;
  final double conf;
  const ObservedMeld(this.tiles, {this.sideways = const [], this.faceDown = const [], this.conf = 0});

  static ObservedMeld? fromJson(Map<String, dynamic> j) {
    final tiles = [
      for (final c in (j['tiles'] as List<dynamic>?) ?? const [])
        if (c is String) ?ReadTile.fromCode(c, 1),
    ];
    if (tiles.length != 3 && tiles.length != 4) return null;
    List<int> idx(String k) => [for (final i in (j[k] as List<dynamic>?) ?? const []) if (i is int) i];
    return ObservedMeld(tiles,
        sideways: idx('sideways'), faceDown: idx('face_down'), conf: ((j['conf'] as num?) ?? 0).toDouble());
  }

  /// 4장: 뒤집힌 패가 있으면 안깡, 없으면 명깡. 3장: 모두 같으면 퐁, 같은 수패의 연속이면 치.
  /// 어느 쪽도 아니면 퐁으로 두고 [consistent] 가 false — 병합이 확인 플래그를 단다.
  ReadMeldType get type {
    if (tiles.length == 4) return faceDown.isNotEmpty ? ReadMeldType.kanClosed : ReadMeldType.kanOpen;
    return _isChi ? ReadMeldType.chi : ReadMeldType.pon;
  }

  bool get _isChi {
    final t = [for (final x in tiles) x.tile]..sort();
    return Tiles.suit(t[0]) < 3 && Tiles.suit(t[0]) == Tiles.suit(t[2]) && t[1] == t[0] + 1 && t[2] == t[0] + 2;
  }

  bool get consistent => _isChi || tiles.every((t) => t.tile == tiles.first.tile);

  ReadMeld toReadMeld() => ReadMeld(type, tiles, conf: consistent ? conf : 0);

  Map<String, dynamic> toJson() => {
        'tiles': [for (final t in tiles) t.code],
        'sideways': sideways,
        'face_down': faceDown,
        'conf': conf,
      };
}

/// 패 한 장의 종류만 바꿔 퐁·치가 되면 고친 묶음을, 아니면 null. 고친 패와 묶음은 확신도 0(병합이 확인 플래그를 단다).
/// 가로로 놓인 패를 숫자는 맞게 읽고 종류만 틀리는 일이 있다(2026-10-30 갤러리 실험: 가로 6m → 6s·6z).
ObservedMeld? repairMeldSuit(ObservedMeld m) {
  if (m.tiles.length != 3 || m.consistent) return null;
  for (var i = 0; i < 3; i++) {
    final others = [for (var j = 0; j < 3; j++) if (j != i) m.tiles[j].tile];
    final suit = Tiles.suit(others[0]);
    if (suit >= 3 || suit != Tiles.suit(others[1])) continue;
    final t = m.tiles[i].tile;
    final digit = t < 27 ? Tiles.number(t) : t - 26; // 자패는 코드의 숫자(6z → 6)
    if (digit > 9) continue;
    final fixed = ObservedMeld(
      [for (var j = 0; j < 3; j++) j == i ? ReadTile(suit * 9 + digit - 1) : m.tiles[j]],
      sideways: m.sideways,
      faceDown: m.faceDown,
    );
    if (fixed.consistent) return fixed;
  }
  return null;
}

/// 읽은 묶음을 울기와 그 밖으로 나눈다. [handCount] 는 울기 뺀 손패 장수(화료패 포함).
/// 모양이 안 맞는 묶음은 보통 모서리에 둔 도라 표시패지만([stray], 4통 4통 7만 등), 그 묶음을 울기로 쳐야 장수가 맞으면
/// (손패 10장 + 3장) 표시패일 수 없다 — 종류만 고쳐 울기가 되면 고쳐 쓰고, 안 되면 어디에도 쓰지 않고 경고만 남긴다.
({List<ObservedMeld> melds, List<ReadTile> stray, List<String> notes}) sortMelds(List<ObservedMeld> read, int handCount) {
  final melds = [for (final m in read) if (m.consistent) m];
  final stray = <ReadTile>[];
  final notes = <String>[];
  for (final m in read) {
    if (m.consistent) continue;
    final codes = m.tiles.map((t) => t.code).join(' ');
    final need = 13 - 3 * (melds.length + 1);
    if (handCount != need && handCount != need + 1) {
      stray.addAll(m.tiles);
      notes.add('퐁·치·깡 모양이 아닌 묶음($codes)을 울기에서 뺐습니다');
      continue;
    }
    final fixed = repairMeldSuit(m);
    if (fixed == null) {
      notes.add('장수로 보면 울기인 묶음($codes)의 모양이 맞지 않습니다. 판독을 고쳐 주세요');
    } else {
      melds.add(fixed);
      notes.add('묶음 $codes 을(를) ${fixed.tiles.map((t) => t.code).join(' ')} 울기로 고쳐 읽었습니다. 확인하세요');
    }
  }
  return (melds: melds, stray: stray, notes: notes);
}

/// 눕힌 패를 못 찾아도 "없음" 으로 믿지 않는 기준: 다른 자리보다 이만큼 넘게 적게 잡힌 강은 틀을 잘못 잡은 것으로 본다
/// (울기로 패를 뺏겨도 이만큼 차이 나기는 드물다. B·C·D 화료자 강에서 17·18장 강 옆에 1장만 잡은 경우가 있었다).
const int riverShortBy = 4;

/// `/v2/last3` 응답([sent] 순서)에서 [sides] 자리 강에 눕힌 패(리치 선언패)가 있는지. 모르면 null(통째 읽기·틀 실패·너무 적게 잡힘).
/// Gemini 가 아니라 YOLO 틀의 모양으로 본 값이다(서버 `app/river.py`). 강 틀을 못 잡으면 응답 전체가 `method: whole` 이다.
Map<Side, bool?> riverSidewaysFrom(Map<String, dynamic>? j, List<Side> sent, Set<Side> sides) {
  final rivers = (j?['rivers'] as List<dynamic>?) ?? const [];
  final frame = j?['method'] == 'frame';
  Map<String, dynamic>? at(int i) => i < rivers.length ? rivers[i] as Map<String, dynamic>? : null;
  int? count(int i) => at(i)?['tile_count'] as int?;
  final most = [for (var i = 0; i < sent.length; i++) count(i) ?? 0].fold(0, (a, b) => a > b ? a : b);
  return {
    for (final s in sides)
      s: switch (sent.indexOf(s)) {
        final i when i >= 0 && frame && count(i) != null => ((at(i)!['sideways'] as List<dynamic>?) ?? const []).isNotEmpty
            ? true
            : (count(i)! < most - riverShortBy ? null : false),
        _ => null,
      },
  };
}

/// 강의 패 한 장과 가로로 놓였는지.
class RiverTile {
  final ReadTile tile;
  final bool sideways;
  const RiverTile(this.tile, {this.sideways = false});

  Map<String, dynamic> toJson() => {'tile': tile.code, 'sideways': sideways, 'conf': tile.conf};
}

class SeatObservation {
  /// 앞면으로 깐 손패인가(locate). false 면 [handTiles] 는 비어 있다.
  final bool faceUp;
  final List<ReadTile> handTiles;
  final ReadTile? separateTile;
  final List<ObservedMeld> melds;

  /// 버린 순서대로. 강을 못 찾은 자리는 null.
  final List<RiverTile>? river;
  final bool riichiStick;

  const SeatObservation({
    this.faceUp = false,
    this.handTiles = const [],
    this.separateTile,
    this.melds = const [],
    this.river,
    this.riichiStick = false,
  });

  /// 리치: 리치봉이 있거나 강에 가로로 놓인 패가 있다.
  bool get riichi => riichiStick || (river?.any((t) => t.sideways) ?? false);

  ReadTile? get lastDiscard => river == null || river!.isEmpty ? null : river!.last.tile;

  Map<String, dynamic> toJson() => {
        'hand': {
          'face_up': faceUp,
          'tiles': [for (final t in handTiles) t.code],
          'separate_tile': separateTile?.code,
        },
        'melds': [for (final m in melds) m.toJson()],
        'river': river == null ? null : [for (final t in river!) t.toJson()],
        'riichi_stick': riichiStick,
      };
}

class TableObservation {
  final Map<Side, SeatObservation> players;

  /// 왕패에 앞면으로 보인 표시패 전부(도라·뒷도라 구분 없음).
  final List<ReadTile> doraIndicators;

  /// [doraIndicators] 를 읽은 곳([CenterReading.doraFrom]).
  final DoraFrom? doraFrom;

  /// 화료자 손패 옆에 따로 놓인 앞면 패([CenterReading.handSideIndicators]).
  final List<ReadTile> handSideIndicators;

  /// 호출별 토큰 수. 비용 집계용(`hand`, `river_bottom`, `center`, `wall` ...).
  final Map<String, Map<String, int>> usage;

  const TableObservation({
    required this.players,
    this.doraIndicators = const [],
    this.doraFrom,
    this.handSideIndicators = const [],
    this.usage = const {},
  });

  SeatObservation seat(Side s) => players[s] ?? const SeatObservation();

  /// 화료자 손패 판독. 떨어뜨려 놓은 한 장이 화료패.
  HandReading toHandReading(Side winner) {
    final s = seat(winner);
    return HandReading(
      tiles: s.handTiles,
      melds: [for (final m in s.melds) m.toReadMeld()],
      winTile: s.separateTile,
      model: 'observe',
    );
  }

  /// 가운데 판독 모양으로. 리치와 강 끝 패는 여기서 코드로 정한다.
  CenterReading toCenterReading() => CenterReading(
        doraIndicators: doraIndicators,
        doraFrom: doraFrom,
        handSideIndicators: handSideIndicators,
        riichi: {for (final s in Side.values) s: seat(s).riichi},
        riichiConf: {for (final s in Side.values) s: seat(s).riichi ? 0.9 : 0.0},
        lastDiscards: {for (final s in Side.values) s: seat(s).lastDiscard},
        rivers: {
          for (final s in Side.values) s: [for (final t in seat(s).river ?? const <RiverTile>[]) t.tile],
        },
        model: 'observe',
      );

  Map<String, dynamic> toJson() => {
        'players': {for (final s in Side.values) s.name: seat(s).toJson()},
        'dora_indicators': [for (final t in doraIndicators) t.code],
        'hand_side_indicators': [for (final t in handSideIndicators) t.code],
        'usage': usage,
      };
}

// ---------------------------------------------------------------- 서버 응답(/v2/*) 해석

List<ReadTile> _tiles(Object? items) => [
      for (final t in (items as List<dynamic>?) ?? const [])
        if (t is Map<String, dynamic>) ?ReadTile.fromJson(t),
    ];

/// `/v2/hand` 응답.
({List<ReadTile> tiles, ReadTile? separate, List<ObservedMeld> melds}) parseHandV2(Map<String, dynamic> j) => (
      tiles: _tiles(j['tiles']),
      separate: ReadTile.fromJson(j['separate_tile'] as Map<String, dynamic>?),
      melds: [
        for (final m in (j['melds'] as List<dynamic>?) ?? const [])
          if (m is Map<String, dynamic>) ?ObservedMeld.fromJson(m),
      ],
    );

/// `/v2/meld` 응답. 3~4장이 아니면 null.
ObservedMeld? parseMeldV2(Map<String, dynamic> j) => ObservedMeld.fromJson(j);

/// `/v2/river` 응답.
({List<RiverTile> tiles, bool riichiStick}) parseRiverV2(Map<String, dynamic> j) => (
      tiles: [
        for (final t in (j['tiles'] as List<dynamic>?) ?? const [])
          if (t is Map<String, dynamic> && ReadTile.fromJson(t) != null)
            RiverTile(ReadTile.fromJson(t)!, sideways: t['sideways'] == true),
      ],
      riichiStick: j['riichi_stick'] == true,
    );

/// `/v2/corner` 응답(격자 모서리 칸): 울기 묶음 전부와 묶음 아닌 앞면 패.
({List<ObservedMeld> melds, List<ReadTile> loose}) parseCornerV2(Map<String, dynamic> j) => (
      melds: [
        for (final m in (j['melds'] as List<dynamic>?) ?? const [])
          if (m is Map<String, dynamic>) ?ObservedMeld.fromJson(m),
      ],
      loose: _tiles(j['loose']),
    );

/// 서버가 같은 자리를 여러 번 읽어 맞춰 본 결과. 모두 같지 않으면 서버가 다른 패의 확신도를 0 으로 낮춰 보낸다.
typedef SeatAgreement = ({int reads, int agree, bool unanimous, List<String> alternatives});

/// `/v2/seat` 응답(격자 자리 구역): 앞면 여부, 손패, 떨어진 한 장, 울기 전부, 따로 놓인 앞면 패,
/// 여러 번 읽어 맞춘 결과(없으면 null — 한 번만 읽는 서버).
typedef SeatV2 = ({
  bool faceUp,
  List<ReadTile> tiles,
  ReadTile? separate,
  List<ObservedMeld> melds,
  List<ReadTile> loose,
  SeatAgreement? agreement,
});

SeatV2 parseSeatV2(Map<String, dynamic> j) {
  final h = parseHandV2(j);
  final a = j['agreement'] as Map<String, dynamic>?;
  return (
    faceUp: j['face_up'] == true,
    tiles: h.tiles,
    separate: h.separate,
    melds: h.melds,
    loose: _tiles(j['loose']),
    agreement: a == null
        ? null
        : (
            reads: (a['reads'] as num?)?.toInt() ?? 0,
            agree: (a['agree'] as num?)?.toInt() ?? 0,
            unanimous: a['unanimous'] == true,
            alternatives: [for (final s in (a['alternatives'] as List<dynamic>?) ?? const []) '$s'],
          ),
  );
}

/// 왕패(도라 산) 상자와 그 패산이 놓인 자리(사진 기준). 크롭을 그 자리 쪽으로 세우면 표시패가 바로 선다.
typedef WallZone = ({NormBox box, Side side});

/// `/v2/wall` 응답 → 왕패 상자. 못 찾았으면 null. 자리를 모르면 아래(돌리지 않음).
WallZone? parseWallV2(Map<String, dynamic> j) {
  if (j['found'] != true) return null;
  final box = NormBox.fromList(j['box'] as List<dynamic>?);
  if (box == null) return null;
  return (box: box, side: SideX.parse(j['side'] as String?) ?? Side.bottom);
}

/// `/v2/last` 응답 또는 `/v2/last3` 의 `rivers` 한 칸: 그 자리 강의 마지막 패. 강이 없으면 null.
ReadTile? parseLastV2(Map<String, dynamic> j) => ReadTile.fromJson(j['last_tile'] as Map<String, dynamic>?);

/// `/v2/localdora` 응답의 `pairs`: 딱 2장 붙은 앞면 패 묶음(리치 화료의 탁자 위 표시패 후보).
List<List<ReadTile>> parseLocalPairs(Map<String, dynamic>? j) => [
      for (final p in (j?['pairs'] as List<dynamic>?) ?? const []) _tiles(p),
    ];

/// `/v2/locallast3` 응답 → 자리별 눕힌 패가 있는지. 보낸 순서대로.
Map<Side, bool> localSticksFrom(Map<String, dynamic>? j, List<Side> sent) {
  final rivers = (j?['rivers'] as List<dynamic>?) ?? const [];
  return {
    for (final (i, s) in sent.indexed)
      s: i < rivers.length && (((rivers[i] as Map<String, dynamic>?)?['sideways'] as List<dynamic>?) ?? const []).isNotEmpty,
  };
}

/// `/v2/center`·`/v2/sticks`·`/v2/dora` 응답(sticks 는 indicators 가, dora 는 riichi_sticks 가 없다).
({List<ReadTile> indicators, Map<Side, bool> sticks}) parseCenterV2(Map<String, dynamic> j) {
  final sticksJ = (j['riichi_sticks'] as Map<String, dynamic>?) ?? const {};
  return (
    indicators: _tiles(j['indicators']),
    sticks: {for (final s in Side.values) s: sticksJ[s.name] == true},
  );
}
