/// 패보: 한 국의 기록.
///
/// 범위(2026-11-17 사용자 결정): **한 사람(hero)의 매 순 손패 + 네 자리 모두의 버림.**
/// 다른 세 자리의 손패·뽑은 패는 기록하지 않는다(위 카메라가 세운 패의 면을 못 봄).
///
/// 자리 번호 0~3 은 차례 순서(0 → 1 → 2 → 3 → 0). 패 코드는 `5m`·`3p`·`9s`·`1z`~`7z`, 적5 는 `0m`·`0p`·`0s`.
///
/// JSON(version 1):
/// ```
/// { "version": 1, "id", "title", "round": "동1국", "honba": 0, "dealer": 0, "hero": 3,
///   "names": [4], "dora_indicators": [], "ura_indicators": [], "note": "",
///   "start_hand": [13] | 없음,
///   "events": [
///     {"type": "draw",    "seat": hero, "tile": "6s" | null, "hand": [뽑기 전 손패 줄] | null},
///     {"type": "discard", "seat": s, "tile": "1p", "tsumogiri": true | false | null, "riichi": false,
///                         "hand": [버린 뒤 손패 줄] | null   ← hero 만},
///     {"type": "call",    "seat": s, "kind": "pon" | "chi" | "kan" | "call"(종류 모름), "from": 버린 자리, "tiles": [묶음 — 모르면 가져간 한 장],
///                         "hand": [...] | null              ← hero 만}
///   ],
///   "result": {"type": "ron" | "tsumo" | "draw", "winner", "loser", "win_tile", "hand": [끝 손패 줄],
///              "melds": [{"kind": "chi" | "pon" | "kan" | "ankan", "tiles": [...]}], "flags": {"riichi": true, ...} | 없음,
///              "tenpai": [자리] | 없음   ← 유국만} }
/// ```
/// 선택 칸(2026-11-21, 손패 복원 `docs/paifu_hand_restore_api_1121.md` — 없어도 같은 버전 1):
/// - 사건 `"at"`: 버림 기록기가 그 패를 처음 본 시각(epoch ms). `"guess": true`: 그 사건의 손패 · 뽑은 패가 짐작(울기 뒤 순서 등).
/// - `"frames"`: `{"dir", "box": [xmin, ymin, xmax, ymax](0~1000), "side", "start_ms", "end_ms"}` — 태블릿에 받아 둔 헤드 녹화와
///   hero 손패 구역. 거치 화면이 녹화를 받아 저장하던 판에만 있다.
/// - `"hand_source"`(손패를 채운 방법, 예 `"claude_api"`)와 `"restore"`(차례별 복원 메모 — 답 · 확신 · 규칙 차례 표시).
///
/// 선택 칸(2026-11-22, 국 시작 점수 · 공탁 `docs/paifu_fill_scores_tsumogiri_design_1122.md` 4절 — 없어도 같은 버전 1):
/// - `"start_scores"`: [4] 자리 순 국 시작 점수(이 국에서 리치봉을 내기 전). `"kyotaku"`: 국 시작 때 걸려 있던 리치봉 수
///   (앞 국에서 넘어온 것). 둘 다 없으면 모름(옛 파일 · 점수판 없이 적은 판).
/// - `"frames"` 의 `"boxes"`: `{"bottom" | "right" | "top" | "left": [xmin, ymin, xmax, ymax](0~1000)}` — 저장 때 격자의 네 자리 구역
///   (B4, 설계서 5절). `box` · `side` 는 그대로 화료자 자리. 없으면 옛 패보.
///
/// 선택 칸(2026-11-24, 유국 저장 `docs/postgame_review_chat_design_1124.md` 10절 ② — 없어도 같은 버전 1):
/// - `"result"` 의 `"tenpai"`: [자리 번호, 오름차순] — 보통 유국(`"type": "draw"`)에서 텐파이한 자리(유국 창에서 고른 값).
///   모두 노텐이면 빈 목록. 없으면 모름(화료 패보 · 옛 파일).
/// hero 의 사건은 그때의 손패 줄(`hand`)을 싣는다. null 이면 "그때 손패를 모름"(녹화 전 등)이다.
library;

import '../engine/tile.dart';

/// 패 한 장(적5 구분 포함).
class PaifuTile {
  final int tile;
  final bool red;
  const PaifuTile(this.tile, {this.red = false});

  factory PaifuTile.parse(String code) => PaifuTile(Tiles.parse(code), red: Tiles.isRedCode(code));

  String get code => red ? '0${Tiles.toCode(tile)[1]}' : Tiles.toCode(tile);

  @override
  bool operator ==(Object other) => other is PaifuTile && other.tile == tile && other.red == red;

  @override
  int get hashCode => tile * 2 + (red ? 1 : 0);

  @override
  String toString() => code;
}

List<PaifuTile> _tiles(Object? v) => [for (final c in (v as List? ?? const [])) PaifuTile.parse(c as String)];

List<PaifuTile>? _tilesOrNull(Object? v) => v == null ? null : _tiles(v);

enum PaifuEventType { draw, discard, call }

class PaifuEvent {
  final PaifuEventType type;
  final int seat;

  /// draw: 뽑은 패(모르면 null), discard: 버린 패.
  final PaifuTile? tile;

  /// 쯔모기리면 true, 손에서 냈으면 false, 모르면 null.
  final bool? tsumogiri;

  /// 리치 선언패.
  final bool riichi;

  /// hero 의 손패 줄. draw 는 뽑기 전(뽑은 패 제외), discard·call 은 그 뒤. null = 모름.
  final List<PaifuTile>? hand;

  /// call: 종류(pon·chi·kan), 버린 자리, 묶음 전체.
  final String? callKind;
  final int? from;
  final List<PaifuTile> callTiles;

  /// 버림 기록기가 이 패를 처음 본 시각(epoch ms). 모르면 null.
  final int? at;

  /// 이 사건의 손패(· 뽑은 패)가 짐작인가(울기 뒤 끼운 자리 · 녹화 전 순 등).
  final bool guess;

  const PaifuEvent({
    required this.type,
    required this.seat,
    this.tile,
    this.tsumogiri,
    this.riichi = false,
    this.hand,
    this.callKind,
    this.from,
    this.callTiles = const [],
    this.at,
    this.guess = false,
  });

  /// 몇 칸만 바꾼 사본. [clearHand] 면 손패를 지운다(null).
  PaifuEvent copyWith({PaifuTile? tile, bool? tsumogiri, List<PaifuTile>? hand, bool clearHand = false, int? at, bool? guess}) => PaifuEvent(
        type: type,
        seat: seat,
        tile: tile ?? this.tile,
        tsumogiri: tsumogiri ?? this.tsumogiri,
        riichi: riichi,
        hand: clearHand ? null : (hand ?? this.hand),
        callKind: callKind,
        from: from,
        callTiles: callTiles,
        at: at ?? this.at,
        guess: guess ?? this.guess,
      );

  factory PaifuEvent.fromJson(Map<String, dynamic> j) {
    final type = switch (j['type']) {
      'draw' => PaifuEventType.draw,
      'discard' => PaifuEventType.discard,
      'call' => PaifuEventType.call,
      final t => throw FormatException('알 수 없는 사건: $t'),
    };
    final seat = j['seat'] as int;
    if (seat < 0 || seat > 3) throw FormatException('자리는 0~3: $seat');
    final tile = j['tile'] as String?;
    if (type == PaifuEventType.discard && tile == null) throw const FormatException('버림에 패가 없습니다');
    return PaifuEvent(
      type: type,
      seat: seat,
      tile: tile == null ? null : PaifuTile.parse(tile),
      tsumogiri: j['tsumogiri'] as bool?,
      riichi: j['riichi'] as bool? ?? false,
      hand: _tilesOrNull(j['hand']),
      callKind: j['kind'] as String?,
      from: j['from'] as int?,
      callTiles: _tiles(j['tiles']),
      at: (j['at'] as num?)?.toInt(),
      guess: j['guess'] == true,
    );
  }

  Map<String, dynamic> toJson() => {
        'type': type.name,
        'seat': seat,
        if (type != PaifuEventType.call) 'tile': tile?.code,
        if (type == PaifuEventType.discard) ...{'tsumogiri': tsumogiri, 'riichi': riichi},
        if (type == PaifuEventType.call) ...{'kind': callKind, 'from': from, 'tiles': [for (final t in callTiles) t.code]},
        if (hand != null || type == PaifuEventType.draw) 'hand': hand == null ? null : [for (final t in hand!) t.code],
        if (at != null) 'at': at,
        if (guess) 'guess': true,
      };
}

/// 태블릿에 받아 둔 헤드 녹화(`rec_pull/<폴더>/f_<ms>.jpg`)와 hero 손패 구역. 손패 복원(`hand_restore/`)이 읽는다.
class PaifuFrames {
  /// 녹화 폴더 절대 경로.
  final String dir;

  /// hero 자리 손패 구역 [xmin, ymin, xmax, ymax], 사진 비율 0~1000.
  final List<int> box;

  /// hero 가 사진에서 앉은 쪽: bottom · right · top · left.
  final String side;
  final int? startMs, endMs;

  /// 네 자리 구역(쪽 이름 → [xmin, ymin, xmax, ymax], [box] 와 같은 좌표). 이 칸이 생기기 전 패보면 null.
  final Map<String, List<int>>? boxes;

  const PaifuFrames({required this.dir, required this.box, required this.side, this.startMs, this.endMs, this.boxes});

  static const sides = ['bottom', 'right', 'top', 'left'];

  /// 상자 하나: 숫자 넷, 0~1000 으로 자르고, 넓이가 있어야 한다. 아니면 null.
  static List<int>? _box(Object? box) {
    if (box is! List || box.length != 4 || box.any((v) => v is! num)) return null;
    final b = [for (final v in box) (v as num).round().clamp(0, 1000)];
    if (b[0] >= b[2] || b[1] >= b[3]) return null;
    return b;
  }

  /// 꼴이 틀리면(옛 촬영 기록의 `"frames": 장수` 등) null. `boxes` 는 꼴이 맞는 쪽만 남기고, 하나도 없으면 null.
  static PaifuFrames? fromJson(Object? j) {
    if (j is! Map) return null;
    final dir = j['dir'], side = j['side'];
    final b = _box(j['box']);
    if (dir is! String || dir.isEmpty || b == null || side is! String || !sides.contains(side)) return null;
    final raw = j['boxes'];
    final boxes = raw is Map
        ? {
            for (final s in sides) s: ?_box(raw[s]),
          }
        : null;
    return PaifuFrames(
      dir: dir,
      box: b,
      side: side,
      startMs: (j['start_ms'] as num?)?.toInt(),
      endMs: (j['end_ms'] as num?)?.toInt(),
      boxes: boxes == null || boxes.isEmpty ? null : boxes,
    );
  }

  Map<String, dynamic> toJson() => {
        'dir': dir,
        'box': box,
        'side': side,
        if (startMs != null) 'start_ms': startMs,
        if (endMs != null) 'end_ms': endMs,
        if (boxes != null)
          'boxes': {
            for (final s in sides) s: ?boxes![s],
          },
      };
}

/// 화료자의 울기 묶음 하나. [kind] = chi · pon · kan(대명깡·가깡) · ankan.
class PaifuResultMeld {
  final String kind;
  final List<PaifuTile> tiles;
  const PaifuResultMeld(this.kind, this.tiles);

  /// `{"kind": "pon", "tiles": [...]}`. 패 목록만 있으면(옛 꼴) 장수·종류로 가늠한다.
  static PaifuResultMeld? fromJson(Object? j) {
    if (j is Map) return PaifuResultMeld(j['kind'] as String? ?? 'pon', _tiles(j['tiles']));
    if (j is List && j.isNotEmpty) {
      final t = _tiles(j);
      final same = t.every((x) => x.tile == t.first.tile);
      return PaifuResultMeld(t.length == 4 ? 'kan' : (same ? 'pon' : 'chi'), t);
    }
    return null;
  }

  Map<String, dynamic> toJson() => {'kind': kind, 'tiles': [for (final t in tiles) t.code]};
}

class PaifuResult {
  /// ron · tsumo · draw(유국)
  final String type;
  final int? winner;
  final int? loser;
  final PaifuTile? winTile;

  /// 화료자의 끝 손패 줄(화료패 제외).
  final List<PaifuTile>? hand;

  /// 화료자의 울기 묶음(점수 계산·끝 걸음 표시).
  final List<PaifuResultMeld> melds;

  /// 화료 상황(riichi · double_riichi · ippatsu · last_tile · rinshan · chankan · first_turn). 앱이 화료 사진을 읽을 때 정한 값.
  /// null 이면 재생할 때 사건에서 헤아린다(`paifu_score.dart` [situationOf]).
  final Map<String, bool>? flags;

  /// 유국(draw)에서 텐파이한 자리(오름차순, 모두 노텐이면 빈 목록). 모르면 null(화료 · 옛 파일).
  final List<int>? tenpai;

  const PaifuResult({required this.type, this.winner, this.loser, this.winTile, this.hand, this.melds = const [], this.flags, this.tenpai});

  factory PaifuResult.fromJson(Map<String, dynamic> j) => PaifuResult(
        type: j['type'] as String,
        winner: j['winner'] as int?,
        loser: j['loser'] as int?,
        winTile: j['win_tile'] == null ? null : PaifuTile.parse(j['win_tile'] as String),
        hand: _tilesOrNull(j['hand']),
        melds: [
          for (final m in (j['melds'] as List? ?? const [])) ?PaifuResultMeld.fromJson(m),
        ],
        flags: j['flags'] == null ? null : {for (final e in (j['flags'] as Map).entries) e.key as String: e.value == true},
        tenpai: j['tenpai'] is List ? [for (final v in j['tenpai'] as List) (v as num).toInt()] : null,
      );

  Map<String, dynamic> toJson() => {
        'type': type,
        'winner': winner,
        'loser': loser,
        'win_tile': winTile?.code,
        'hand': hand == null ? null : [for (final t in hand!) t.code],
        'melds': [for (final m in melds) m.toJson()],
        if (flags != null) 'flags': flags,
        if (tenpai != null) 'tenpai': tenpai,
      };
}

/// 강에 놓인 패 한 장.
class PaifuRiverTile {
  final PaifuTile tile;
  final bool? tsumogiri;
  final bool riichi;

  /// 다른 자리가 울어 가서 강에서 빠진 패.
  final bool called;

  const PaifuRiverTile(this.tile, {this.tsumogiri, this.riichi = false, this.called = false});

  PaifuRiverTile asCalled() => PaifuRiverTile(tile, tsumogiri: tsumogiri, riichi: riichi, called: true);
}

class PaifuMeld {
  final String kind;
  final List<PaifuTile> tiles;
  final int? from;
  const PaifuMeld(this.kind, this.tiles, this.from);
}

/// 어느 걸음에서 본 탁자.
class PaifuState {
  /// 0 = 시작, i = events[i-1] 까지 반영, 마지막(+1) = 결과.
  final int step;
  final List<List<PaifuRiverTile>> rivers;
  final List<List<PaifuMeld>> melds;
  final List<bool> riichi;

  /// hero 손패 줄. null = 모름.
  final List<PaifuTile>? heroHand;

  /// hero 가 방금 뽑아 아직 안 버린 상태. [drawn] 이 null 이면 뽑은 패 종류를 모름.
  final bool hasDrawn;
  final PaifuTile? drawn;

  /// 이 걸음을 만든 사건(시작·결과 걸음은 null).
  final PaifuEvent? event;
  final bool finished;

  /// 패산에서 뽑힌 장수(버림에서 거꾸로 셈 — 퐁·치 뒤 버림은 안 셈).
  final int draws;

  const PaifuState({
    required this.step,
    required this.rivers,
    required this.melds,
    required this.riichi,
    required this.heroHand,
    required this.hasDrawn,
    required this.drawn,
    required this.event,
    required this.finished,
    required this.draws,
  });

  int get wallLeft => (70 - draws).clamp(0, 70);

  /// 자리의 버림 수(울려 나간 패 포함).
  int discards(int seat) => rivers[seat].length;

  /// 몇 순째인가: 가장 많이 버린 자리의 버림 수.
  int get turn => [for (var s = 0; s < 4; s++) discards(s)].reduce((a, b) => a > b ? a : b);
}

class Paifu {
  final String id;
  final String title;
  final String round;
  final int honba;
  final int dealer;
  final int hero;
  final List<String> names;
  final List<PaifuTile> doraIndicators;
  final List<PaifuTile> uraIndicators;
  final String note;
  final List<PaifuTile>? startHand;
  final List<PaifuEvent> events;
  final PaifuResult? result;

  /// 받아 둔 헤드 녹화(손패 복원 재료). 없으면 null.
  final PaifuFrames? frames;

  /// 판 중 손패를 채운 방법(`"claude_api"` 등). 기록에 처음부터 있던 손패면 null.
  final String? handSource;

  /// 손패 복원의 차례별 메모(JSON 그대로).
  final List<Map<String, dynamic>>? restore;

  /// 국 시작 점수(자리 순 4개, 이 국의 리치봉을 내기 전). 모르면 null.
  final List<int>? startScores;

  /// 국 시작 때 걸려 있던 리치봉 수(앞 국에서 넘어온 공탁). 모르면 null.
  final int? kyotaku;

  Paifu({
    required this.id,
    this.title = '',
    this.round = '',
    this.honba = 0,
    this.dealer = 0,
    required this.hero,
    this.names = const ['', '', '', ''],
    this.doraIndicators = const [],
    this.uraIndicators = const [],
    this.note = '',
    this.startHand,
    required this.events,
    this.result,
    this.frames,
    this.handSource,
    this.restore,
    this.startScores,
    this.kyotaku,
  });

  /// 몇 칸만 바꾼 사본. 주지 않은 칸(국 시작 점수 · 공탁 포함)은 그대로 둔다.
  Paifu copyWith({
    List<PaifuTile>? startHand,
    List<PaifuEvent>? events,
    PaifuFrames? frames,
    String? handSource,
    List<Map<String, dynamic>>? restore,
    List<int>? startScores,
    int? kyotaku,
  }) =>
      Paifu(
        id: id,
        title: title,
        round: round,
        honba: honba,
        dealer: dealer,
        hero: hero,
        names: names,
        doraIndicators: doraIndicators,
        uraIndicators: uraIndicators,
        note: note,
        startHand: startHand ?? this.startHand,
        events: events ?? this.events,
        result: result,
        frames: frames ?? this.frames,
        handSource: handSource ?? this.handSource,
        restore: restore ?? this.restore,
        startScores: startScores ?? this.startScores,
        kyotaku: kyotaku ?? this.kyotaku,
      );

  factory Paifu.fromJson(Map<String, dynamic> j) {
    final version = j['version'] as int? ?? 1;
    if (version != 1) throw FormatException('모르는 패보 버전: $version');
    final hero = j['hero'] as int;
    if (hero < 0 || hero > 3) throw FormatException('hero 는 0~3: $hero');
    final names = [for (final n in (j['names'] as List? ?? const [])) n as String];
    return Paifu(
      id: j['id'] as String? ?? '',
      title: j['title'] as String? ?? '',
      round: j['round'] as String? ?? '',
      honba: j['honba'] as int? ?? 0,
      dealer: j['dealer'] as int? ?? 0,
      hero: hero,
      names: [for (var s = 0; s < 4; s++) s < names.length ? names[s] : ''],
      doraIndicators: _tiles(j['dora_indicators']),
      uraIndicators: _tiles(j['ura_indicators']),
      note: j['note'] as String? ?? '',
      startHand: _tilesOrNull(j['start_hand']),
      events: [for (final e in (j['events'] as List? ?? const [])) PaifuEvent.fromJson(e as Map<String, dynamic>)],
      result: j['result'] == null ? null : PaifuResult.fromJson(j['result'] as Map<String, dynamic>),
      frames: PaifuFrames.fromJson(j['frames']),
      handSource: j['hand_source'] as String?,
      restore: j['restore'] is List
          ? [
              for (final m in j['restore'] as List)
                if (m is Map) m.cast<String, dynamic>(),
            ]
          : null,
      // 장수 · 100의 배수는 읽을 때 거르지 않고 [check] 가 적는다.
      startScores: j['start_scores'] is List ? [for (final v in j['start_scores'] as List) (v as num).toInt()] : null,
      kyotaku: (j['kyotaku'] as num?)?.toInt(),
    );
  }

  Map<String, dynamic> toJson() => {
        'version': 1,
        'id': id,
        'title': title,
        'round': round,
        'honba': honba,
        'dealer': dealer,
        'hero': hero,
        'names': names,
        if (startScores != null) 'start_scores': startScores,
        if (kyotaku != null) 'kyotaku': kyotaku,
        'dora_indicators': [for (final t in doraIndicators) t.code],
        'ura_indicators': [for (final t in uraIndicators) t.code],
        'note': note,
        if (startHand != null) 'start_hand': [for (final t in startHand!) t.code],
        'events': [for (final e in events) e.toJson()],
        if (result != null) 'result': result!.toJson(),
        if (frames != null) 'frames': frames!.toJson(),
        if (handSource != null) 'hand_source': handSource,
        if (restore != null) 'restore': restore,
      };

  /// 자리의 바람(0 동 · 1 남 · 2 서 · 3 북).
  int windOf(int seat) => (seat - dealer) % 4;

  /// hero 를 아래에 뒀을 때 자리가 놓이는 쪽(0 아래 · 1 오른쪽 · 2 위 · 3 왼쪽).
  int sideOf(int seat) => (seat - hero) % 4;

  /// hero 의 판 중 손패가 한 순이라도 적혀 있는가. 버림만 적은 패보면 false.
  late final bool hasHeroHands = startHand != null || events.any((e) => e.seat == hero && e.hand != null);

  /// 걸음 수(시작 + 사건 수 + 결과).
  int get stepCount => events.length + 1 + (result != null ? 1 : 0);

  late final List<PaifuState> states = _build();

  List<PaifuState> _build() {
    final rivers = [for (var s = 0; s < 4; s++) <PaifuRiverTile>[]];
    final melds = [for (var s = 0; s < 4; s++) <PaifuMeld>[]];
    final riichi = [false, false, false, false];
    List<PaifuTile>? hand = startHand;
    var hasDrawn = false;
    PaifuTile? drawn;
    var draws = 0;
    var afterOpenCall = false; // 퐁·치 직후(다음 버림은 뽑지 않고 냄)

    PaifuState snap(int step, PaifuEvent? e, {bool finished = false}) => PaifuState(
          step: step,
          rivers: [for (final r in rivers) List.unmodifiable(r)],
          melds: [for (final m in melds) List.unmodifiable(m)],
          riichi: List.unmodifiable(riichi),
          heroHand: hand,
          hasDrawn: hasDrawn,
          drawn: drawn,
          event: e,
          finished: finished,
          draws: draws,
        );

    final out = <PaifuState>[snap(0, null)];
    for (final (i, e) in events.indexed) {
      switch (e.type) {
        case PaifuEventType.draw:
          // 뽑기 사건은 hero 것만 쓴다(다른 자리는 버림에서 센다).
          if (e.seat == hero) {
            draws++;
            hand = e.hand;
            hasDrawn = true;
            drawn = e.tile;
          }
        case PaifuEventType.discard:
          rivers[e.seat].add(PaifuRiverTile(e.tile!, tsumogiri: e.tsumogiri, riichi: e.riichi));
          if (e.riichi) riichi[e.seat] = true;
          if (e.seat == hero) {
            // hero 는 뽑기 사건이 따로 있다. 없이 버렸으면(울기 뒤가 아닌데) 여기서 센다.
            if (!hasDrawn && !afterOpenCall) draws++;
            hand = e.hand;
            hasDrawn = false;
            drawn = null;
          } else if (!afterOpenCall) {
            draws++;
          }
          afterOpenCall = false;
        case PaifuEventType.call:
          final from = e.from;
          if (from != null && from != e.seat && rivers[from].isNotEmpty) {
            rivers[from][rivers[from].length - 1] = rivers[from].last.asCalled();
          }
          final kind = e.callKind ?? 'pon';
          final meld = PaifuMeld(kind, e.callTiles, from);
          // 가깡은 앞서 한 퐁을 깡으로 바꾼다.
          final pon = kind == 'kakan' && e.callTiles.isNotEmpty
              ? melds[e.seat].indexWhere((m) => m.kind == 'pon' && m.tiles.first.tile == e.callTiles.first.tile)
              : -1;
          if (pon >= 0) {
            melds[e.seat][pon] = meld;
          } else {
            melds[e.seat].add(meld);
          }
          // 깡은 영상패를 뽑고 버리므로 다음 버림이 뽑은 장수에 들어간다. 종류를 모르는 울기('call')는 퐁·치로 본다.
          afterOpenCall = !kind.contains('kan');
          if (e.seat == hero) {
            hand = e.hand;
            hasDrawn = false;
            drawn = null;
          }
      }
      out.add(snap(i + 1, e));
    }
    final r = result;
    if (r != null) {
      if (r.winner == hero && r.hand != null) hand = r.hand;
      hasDrawn = false;
      drawn = null;
      out.add(snap(events.length + 1, null, finished: true));
    }
    return out;
  }

  /// hero 가 뽑은 걸음(= 내 차례 시작)들. "다음 내 차례" 이동에 쓴다. 뽑기가 안 적힌 패보(버림만)는 hero 가 버린 걸음들.
  late final List<int> heroTurnSteps = () {
    List<int> of(PaifuEventType type) => [
          for (final s in states)
            if (s.event != null && s.event!.type == type && s.event!.seat == hero) s.step,
        ];
    final draws = of(PaifuEventType.draw);
    return draws.isNotEmpty ? draws : of(PaifuEventType.discard);
  }();

  /// 기록이 앞뒤가 맞는지 본다. 문제마다 한 줄, 없으면 빈 목록.
  List<String> check() {
    final problems = <String>[];
    // 1) 같은 패는 4장까지(적5 는 같은 패로 셈).
    final seen = List<int>.filled(Tiles.count, 0);
    void add(Iterable<PaifuTile> ts) {
      for (final t in ts) {
        seen[t.tile]++;
      }
    }

    // 끝 탁자에서 센다: 강에 남은 패 + 울기 묶음(울려 나간 버림은 묶음 쪽에서 한 번만).
    final end = states.last;
    for (var s = 0; s < 4; s++) {
      add([
        for (final r in end.rivers[s])
          if (!r.called) r.tile,
      ]);
      for (final m in end.melds[s]) {
        add(m.tiles);
      }
    }
    add(doraIndicators);
    add(uraIndicators);
    final r = result;
    if (r?.hand != null) add(r!.hand!);
    if (r != null && r.type == 'tsumo' && r.winTile != null) add([r.winTile!]);
    for (var t = 0; t < Tiles.count; t++) {
      if (seen[t] > 4) problems.add('${Tiles.name(t)} 이(가) ${seen[t]}장 보임');
    }

    // 2) hero 손패: 뽑기 전 + 뽑은 패 − 버린 패 = 버린 뒤(구성만 비교).
    List<PaifuTile>? before;
    PaifuTile? drew;
    var n = 0;
    for (final e in events) {
      if (e.seat != hero) continue;
      if (e.type == PaifuEventType.draw) {
        before = e.hand;
        drew = e.tile;
      } else if (e.type == PaifuEventType.discard) {
        n++;
        final after = e.hand;
        if (before != null && drew != null && after != null) {
          final a = toCounts([...before.map((t) => t.tile), drew.tile]);
          a[e.tile!.tile]--;
          final b = toCounts(after.map((t) => t.tile));
          if (!_same(a, b)) problems.add('hero $n번째 버림: 뽑기 전 + 뽑은 패 − 버린 패가 버린 뒤 손패와 다름');
          if (e.tsumogiri == true && drew.tile != e.tile!.tile) problems.add('hero $n번째 버림: 쯔모기리인데 뽑은 패와 버린 패가 다름');
        }
        before = null;
        drew = null;
      }
    }

    // 3) 리치 뒤 버림은 쯔모기리.
    for (var s = 0; s < 4; s++) {
      var declared = false;
      for (final e in events) {
        if (e.seat != s || e.type != PaifuEventType.discard) continue;
        if (declared && e.tsumogiri == false) problems.add('자리 $s: 리치 뒤에 손에서 낸 버림(${e.tile})');
        if (e.riichi) declared = true;
      }
    }

    // 4) 국 시작 점수 · 공탁(있을 때만). 합계는 시작 점수 설정을 몰라 보지 않는다.
    final sc = startScores;
    if (sc != null) {
      if (sc.length != 4) {
        problems.add('국 시작 점수가 ${sc.length}개(4개여야 함)');
      } else if (sc.any((v) => v % 100 != 0)) {
        problems.add('국 시작 점수가 100의 배수가 아님: [${sc.join(', ')}]');
      }
    }
    final k = kyotaku;
    if (k != null && k < 0) problems.add('공탁이 음수: $k');
    return problems;
  }

  static bool _same(List<int> a, List<int> b) {
    for (var i = 0; i < a.length; i++) {
      if (a[i] != b[i]) return false;
    }
    return true;
  }
}
