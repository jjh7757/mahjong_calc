/// 서버가 읽어 준 결과 모델: 손패(`/v1/recognize`)와 테이블 중앙(`/v1/table`). 순수 Dart.
library;

import '../engine/tile.dart';
import 'table_layout.dart';

/// 읽은 패 한 장. 적도라 코드(`0m`)는 5 로 바꾸고 [red] 를 켠다.
class ReadTile {
  final int tile;
  final bool red;
  final double conf;

  /// 분류기 2순위 패 코드(`0m` 처럼 적5 그대로)와 그 확신도. 서버 `/v2/localroles`·`/v2/localseat` 가 낼 때만(개선 계획 4단계,
  /// 2026-11-05). 답은 [tile] 그대로이고 규칙 검증기 V3(`hand_rules.dart`)가 후보를 찾는 데만 쓴다.
  final String? alt;
  final double conf2;
  const ReadTile(this.tile, {this.red = false, this.conf = 0, this.alt, this.conf2 = 0});

  static ReadTile? fromCode(String? code, num? conf) {
    if (code == null) return null;
    try {
      return ReadTile(
        Tiles.parse(code),
        red: Tiles.isRedCode(code),
        conf: (conf ?? 0).toDouble(),
      );
    } on FormatException {
      return null;
    }
  }

  static ReadTile? fromJson(Map<String, dynamic>? j) {
    if (j == null) return null;
    final t = fromCode(j['tile'] as String?, j['conf'] as num?);
    final alt = j['alt'] as String?;
    if (t == null || alt == null || fromCode(alt, 0) == null) return t;
    return ReadTile(t.tile, red: t.red, conf: t.conf, alt: alt, conf2: ((j['conf2'] as num?) ?? 0).toDouble());
  }

  String get code => red ? '0${Tiles.toCode(tile)[1]}' : Tiles.toCode(tile);

  Map<String, dynamic> toJson() => {'tile': code, 'conf': conf, if (alt != null) 'alt': alt, if (alt != null) 'conf2': conf2};

  @override
  String toString() => code;
}

enum ReadMeldType { chi, pon, kanOpen, kanClosed }

ReadMeldType? _meldType(String? s) => switch (s) {
  'chi' => ReadMeldType.chi,
  'pon' => ReadMeldType.pon,
  'kan_open' => ReadMeldType.kanOpen,
  'kan_closed' => ReadMeldType.kanClosed,
  _ => null,
};

/// 읽은 울기 그룹. 서버가 정합성이 틀리면 conf 0 으로 보낸다.
class ReadMeld {
  final ReadMeldType type;
  final List<ReadTile> tiles;
  final double conf;
  const ReadMeld(this.type, this.tiles, {this.conf = 0});

  static ReadMeld? fromJson(Map<String, dynamic> j) {
    final type = _meldType(j['type'] as String?);
    if (type == null) return null;
    final tiles = <ReadTile>[];
    for (final c in (j['tiles'] as List<dynamic>?) ?? const []) {
      final t = ReadTile.fromCode(c as String?, 1);
      if (t == null) return null;
      tiles.add(t);
    }
    final need = type == ReadMeldType.chi || type == ReadMeldType.pon ? 3 : 4;
    if (tiles.length != need) return null;
    return ReadMeld(type, tiles, conf: ((j['conf'] as num?) ?? 0).toDouble());
  }

  bool get isOpen => type != ReadMeldType.kanClosed;

  String get typeName => switch (type) {
    ReadMeldType.chi => 'chi',
    ReadMeldType.pon => 'pon',
    ReadMeldType.kanOpen => 'kan_open',
    ReadMeldType.kanClosed => 'kan_closed',
  };

  Map<String, dynamic> toJson() => {
    'type': typeName,
    'tiles': [for (final t in tiles) t.code],
    'conf': conf,
  };
}

/// `/v1/recognize` 응답.
class HandReading {
  final List<ReadTile> tiles;
  final List<ReadMeld> melds;
  final ReadTile? winTile;
  final String notes;
  final String model;
  final int latencyMs;

  /// 서버가 알려 준 토큰 수(input_tokens·output_tokens). 비용 집계용.
  final Map<String, int> usage;

  /// 판독 불확실성 신호(`/v2/localroles` 의 `signals`, 개선 계획 5단계 — 서버 feat/cls-alt). 답은 안 바꾸는 부가 정보이고,
  /// 문턱은 `read_signals.dart` 가 갖는다. 서버가 안 내면 null(그러면 신호로 막지 않는다).
  final Map<String, dynamic>? signals;

  const HandReading({
    this.tiles = const [],
    this.melds = const [],
    this.winTile,
    this.notes = '',
    this.model = '',
    this.latencyMs = 0,
    this.usage = const {},
    this.signals,
  });

  factory HandReading.fromJson(Map<String, dynamic> j) {
    final tiles = <ReadTile>[];
    for (final t in (j['tiles'] as List<dynamic>?) ?? const []) {
      final r = t is Map<String, dynamic> ? ReadTile.fromJson(t) : null;
      if (r != null) tiles.add(r);
    }
    final melds = <ReadMeld>[];
    for (final m in (j['melds'] as List<dynamic>?) ?? const []) {
      final r = m is Map<String, dynamic> ? ReadMeld.fromJson(m) : null;
      if (r != null) melds.add(r);
    }
    return HandReading(
      tiles: tiles,
      melds: melds,
      winTile: ReadTile.fromJson(j['win_tile'] as Map<String, dynamic>?),
      notes: (j['notes'] as String?) ?? '',
      model: (j['model'] as String?) ?? '',
      latencyMs: ((j['latency_ms'] as num?) ?? 0).toInt(),
      usage: parseUsage(j['usage']),
      signals: j['signals'] as Map<String, dynamic>?,
    );
  }

  /// 서버 자리 판독의 불확실성 신호를 붙인 사본(관찰 → 손패 판독으로 바꿀 때 `table_reader.dart` 가 쓴다).
  HandReading withSignals(Map<String, dynamic>? s) => HandReading(
    tiles: tiles,
    melds: melds,
    winTile: winTile,
    notes: notes,
    model: model,
    latencyMs: latencyMs,
    usage: usage,
    signals: s,
  );

  /// 화료패를 사용자가 후보에서 골랐을 때의 손패(다시 병합할 때 쓴다).
  HandReading withWinTile(ReadTile win) => HandReading(
    tiles: tiles,
    melds: melds,
    winTile: win,
    notes: notes,
    model: model,
    latencyMs: latencyMs,
    usage: usage,
    signals: signals,
  );

  /// 서버 응답과 같은 모양. 촬영 기록 저장용.
  Map<String, dynamic> toJson() => {
    'tiles': [for (final t in tiles) t.toJson()],
    'count': tiles.length,
    'melds': [for (final m in melds) m.toJson()],
    'win_tile': winTile?.toJson(),
    'notes': notes,
    'model': model,
    'latency_ms': latencyMs,
    'usage': usage,
    if (signals != null) 'signals': signals,
  };

  /// 손패·화료패·울기까지 합친 장수(깡은 4장).
  int get totalTiles =>
      tiles.length +
      (winTile == null ? 0 : 1) +
      melds.fold(0, (a, m) => a + m.tiles.length);
}

/// 도라 표시패를 어디서 읽었나(격자 판독). 리치 화료면 merge 가 화료자 손패 옆([CenterReading.handSideIndicators])을 먼저 쓴다.
/// - wall: 왕패 상자(지금은 쓰지 않음, 예전 촬영 기록을 읽으려고 남김)
/// - dealerZone: 왕패 상자가 없어 선 기준 도라 구역에서
/// - center: 왕패 상자가 없어 가운데 칸 전체에서(예비)
/// - local: 화료 사진 전체에서 자체 모델이 패산 위 표시패를 찾아 읽음(`/v2/localdora`)
/// - tracked: 화료 사진에서는 못 읽고 판 중 프레임 투표로 확정한 표시패([DoraTracker])를 씀
enum DoraFrom { wall, dealerZone, center, local, tracked }

/// `/v1/table` 응답.
class CenterReading {
  final List<ReadTile> doraIndicators;

  /// [doraIndicators] 를 읽은 곳(격자 판독만). 모르면 null(예전 locate 흐름).
  final DoraFrom? doraFrom;

  /// 리치 화료 뒤 공개한 뒷도라 표시패. 공개 전 사진이면 비어 있다.
  final List<ReadTile> uraIndicators;

  /// 화료자 손패 옆에 따로 놓인 앞면 패(격자 판독의 자리 구역). 매장에서는 리치 화료면 화료자가 도라·뒷도라 표시패를
  /// 자기 자리로 가져가 계산하고, 리치가 아니면 왕패에 그대로 둔다(2026-10-26 사용자 관찰) → merge 가 리치 여부로
  /// [doraIndicators]·[uraIndicators] 와 이것 중 어느 쪽을 표시패로 쓸지 고른다.
  final List<ReadTile> handSideIndicators;
  final Map<Side, bool> riichi;
  final Map<Side, double> riichiConf;
  final Map<Side, ReadTile?> lastDiscards;

  /// 자리별 버림패(강) 전체, 버린 순서대로. 서버가 안 주면 비어 있다.
  final Map<Side, List<ReadTile>> rivers;
  final String notes;
  final String model;
  final int latencyMs;

  /// 서버가 알려 준 토큰 수(input_tokens·output_tokens). 비용 집계용.
  final Map<String, int> usage;

  const CenterReading({
    this.doraIndicators = const [],
    this.doraFrom,
    this.uraIndicators = const [],
    this.handSideIndicators = const [],
    this.riichi = const {},
    this.riichiConf = const {},
    this.lastDiscards = const {},
    this.rivers = const {},
    this.notes = '',
    this.model = '',
    this.latencyMs = 0,
    this.usage = const {},
  });

  factory CenterReading.fromJson(Map<String, dynamic> j) {
    List<ReadTile> tiles(String key) => [
          for (final t in (j[key] as List<dynamic>?) ?? const [])
            if (t is Map<String, dynamic>) ?ReadTile.fromJson(t),
        ];
    final dora = tiles('dora_indicators');
    final riichiJ = (j['riichi'] as Map<String, dynamic>?) ?? const {};
    final riichiConfJ = (j['riichi_conf'] as Map<String, dynamic>?) ?? const {};
    final lastJ = (j['last_discards'] as Map<String, dynamic>?) ?? const {};
    final lastConfJ =
        (j['last_discards_conf'] as Map<String, dynamic>?) ?? const {};
    final riversJ = (j['rivers'] as Map<String, dynamic>?) ?? const {};
    final riichi = <Side, bool>{};
    final riichiConf = <Side, double>{};
    final last = <Side, ReadTile?>{};
    final rivers = <Side, List<ReadTile>>{};
    for (final s in Side.values) {
      rivers[s] = [
        for (final c in (riversJ[s.name] as List<dynamic>?) ?? const [])
          if (c is String) ?ReadTile.fromCode(c, 1),
      ];
      riichi[s] = riichiJ[s.name] == true;
      riichiConf[s] = ((riichiConfJ[s.name] as num?) ?? 0).toDouble();
      last[s] = ReadTile.fromCode(
        lastJ[s.name] as String?,
        lastConfJ[s.name] as num?,
      );
    }
    return CenterReading(
      doraIndicators: dora,
      doraFrom: DoraFrom.values.asNameMap()[j['dora_from']],
      uraIndicators: tiles('ura_dora_indicators'),
      handSideIndicators: tiles('hand_side_indicators'),
      riichi: riichi,
      riichiConf: riichiConf,
      lastDiscards: last,
      rivers: rivers,
      notes: (j['notes'] as String?) ?? '',
      model: (j['model'] as String?) ?? '',
      latencyMs: ((j['latency_ms'] as num?) ?? 0).toInt(),
      usage: parseUsage(j['usage']),
    );
  }

  bool riichiAt(Side s) => riichi[s] ?? false;

  /// 마지막 버림패. 따로 못 읽었으면 강 전체의 마지막 장.
  ReadTile? lastDiscardAt(Side s) {
    final last = lastDiscards[s];
    if (last != null) return last;
    final river = rivers[s];
    return river == null || river.isEmpty ? null : river.last;
  }

  /// 왕패만 따로 잘라 읽은 [wall] 의 도라·뒷도라로 바꾼 사본. 크게 잘라 읽은 쪽이 더 정확하다.
  /// [wall] 에 도라 표시패가 없으면 그대로 둔다.
  CenterReading withWall(CenterReading wall) => wall.doraIndicators.isEmpty
      ? this
      : CenterReading(
          doraIndicators: wall.doraIndicators,
          doraFrom: DoraFrom.wall,
          uraIndicators: wall.uraIndicators,
          handSideIndicators: handSideIndicators,
          riichi: riichi,
          riichiConf: riichiConf,
          lastDiscards: lastDiscards,
          rivers: rivers,
          notes: notes,
          model: model,
          latencyMs: latencyMs,
          usage: usage,
        );

  /// 서버 응답과 같은 모양. 촬영 기록 저장용.
  Map<String, dynamic> toJson() => {
    'dora_indicators': [for (final t in doraIndicators) t.toJson()],
    'dora_from': doraFrom?.name,
    'ura_dora_indicators': [for (final t in uraIndicators) t.toJson()],
    'hand_side_indicators': [for (final t in handSideIndicators) t.toJson()],
    'riichi': {for (final s in Side.values) s.name: riichiAt(s)},
    'riichi_conf': {for (final s in Side.values) s.name: riichiConf[s] ?? 0},
    'last_discards': {
      for (final s in Side.values) s.name: lastDiscards[s]?.code,
    },
    'last_discards_conf': {
      for (final s in Side.values) s.name: lastDiscards[s]?.conf ?? 0,
    },
    'rivers': {
      for (final s in Side.values) s.name: [for (final t in rivers[s] ?? const <ReadTile>[]) t.code],
    },
    'notes': notes,
    'model': model,
    'latency_ms': latencyMs,
    'usage': usage,
  };
}

/// 한 번의 거치 촬영에서 얻은 것 전부.
class TableReading {
  final TableLayout layout;
  final Side? winnerSide;
  final HandReading? hand;
  final CenterReading? center;

  /// 계속 진행은 했지만 알려야 할 것(중앙 읽기 실패 등).
  final List<String> warnings;

  /// 동시 론으로 함께 고른 다른 화료자의 판독(같은 사진). 각자 [winnerSide]·[hand]·[center] 를 가진다.
  final List<TableReading> others;

  /// [hand] 의 울기가 판 상태 추적으로 게임 중에 미리 읽어 둔 것(화료 사진은 손패 칸만 읽음).
  final bool meldsTracked;

  /// 게임 중 강 추적이 본 "가장 최근에 버린 자리". 강 끝 패가 여럿 화료될 때 merge 가 방총자로 고른다(`loserHint`).
  final Side? trackedDiscardSide;

  /// 게임 중 리치봉 추적이 확정한 자리(촬영 판독과 합쳐 [center] 의 riichi 에 이미 들어 있음, 기록용).
  final Set<Side> trackedRiichi;

  /// 추적이 "첫 순 리치" 로 본 자리(더블리치 후보, `RiverTracker.doubleRiichiCandidates`). merge 가 확인 플래그와 함께 쓴다.
  final Set<Side> trackedDoubleRiichi;

  /// 추적이 "리치 뒤 아직 안 버림·울기 없음" 으로 본 자리(일발 후보, `RiverTracker.ippatsuCandidates`). merge 가 확인 플래그와 함께 쓴다.
  final Set<Side> trackedIppatsu;

  /// 유국으로 봉이 남은 자리의 강에 눕힌 패가 있는지(모르면 null). 그 자리만 잰다. merge 가 이번 판 리치를 이걸로 정한다.
  final Map<Side, bool?> riverSideways;

  /// 판 중 프레임 투표로 확정한 도라 표시패([DoraTracker]). merge 가 화료 사진의 표시패 답을 이것으로 검증·보충한다. 없으면 null.
  final ReadTile? trackedDora;
  const TableReading({
    required this.layout,
    this.winnerSide,
    this.hand,
    this.center,
    this.warnings = const [],
    this.others = const [],
    this.meldsTracked = false,
    this.trackedDiscardSide,
    this.trackedRiichi = const {},
    this.trackedDoubleRiichi = const {},
    this.trackedIppatsu = const {},
    this.riverSideways = const {},
    this.trackedDora,
  });
}
