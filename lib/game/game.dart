/// 대국 점수 기록 모델. 순수 Dart, UI 의존 없음.
///
/// 점수 이동(론·쯔모·리치·유국), 본장·공탁, 친 교체, 우마·오카 정산을 다룬다.
library;

import '../engine/calculator.dart';
import '../engine/score.dart' show basePoints, payment, yakumanPoints;

/// 정산 규칙.
class GameSettings {
  final int startPoints;

  /// 반환점. 오카 = (반환점 - 시작점) × 4 를 1위가 받는다.
  final int returnPoints;

  /// 우마 (천점 단위). [umaBig] 는 1·4위, [umaSmall] 은 2·3위.
  final int umaBig;
  final int umaSmall;

  /// 동풍전이면 true, 반장전이면 false.
  final bool eastOnly;

  /// 정산 시 천점 단위 반올림(오사육입). false 면 소수 한 자리.
  final int roundingMode; // 0: 소수 한 자리, 1: 오사육입

  /// 거치 촬영 모드에서 사진 아래쪽 변에 앉은 사람의 자리(0~3). 자리 순서는 반시계(아래→오른쪽→위→왼쪽).
  final int bottomSeat;

  /// 같은 패로 여럿이 론했을 때. [multiRonDouble] 더블론 인정·트리플론 유국(기본),
  /// [multiRonHeadBump] 머리치기(방총자 다음 차례에 가장 가까운 한 명만), [multiRonTriple] 트리플론까지 인정.
  final int multiRon;

  /// 올라스에서 친이 화료해 1위면 연장하지 않고 끝낸다(아가리야메). 작혼식: 친의 선택 없이 자동.
  final bool agariYame;

  /// 올라스 유국에서 친이 텐파이이고(벌점 정산 뒤) 1위면 끝낸다(텐파이야메). 작혼식: 자동.
  final bool tenpaiYame;

  /// 서입(동풍전은 남입): 올라스가 끝났는데 1위가 반환점 미만이면 연장전으로 이어가고, 매 국 끝에 누군가
  /// 반환점 이상이면 끝낸다(서든데스, 서4국까지·북입 없음). false 면 올라스에서 무조건 끝낸다. 작혼식.
  final bool overtime;

  static const multiRonDouble = 0;
  static const multiRonHeadBump = 1;
  static const multiRonTriple = 2;
  static const multiRonLabels = ['더블론 · 트리플론 유국', '머리치기', '트리플론까지'];

  const GameSettings({
    this.startPoints = 25000,
    this.returnPoints = 30000,
    this.umaBig = 20,
    this.umaSmall = 10,
    this.eastOnly = false,
    this.roundingMode = 1,
    this.bottomSeat = 0,
    this.multiRon = multiRonDouble,
    this.agariYame = true,
    this.tenpaiYame = true,
    this.overtime = true,
  });

  int get oka => (returnPoints - startPoints) * 4 ~/ 1000;

  /// 함께 인정하는 론 화료자 수(머리치기면 1).
  int get maxRonWinners => switch (multiRon) {
        multiRonHeadBump => 1,
        multiRonTriple => 3,
        _ => 2,
      };

  /// 셋이 동시에 론하면 유국인가.
  bool get tripleRonDraws => multiRon == multiRonDouble;

  GameSettings copyWith({int? bottomSeat}) => GameSettings(
        startPoints: startPoints,
        returnPoints: returnPoints,
        umaBig: umaBig,
        umaSmall: umaSmall,
        eastOnly: eastOnly,
        roundingMode: roundingMode,
        bottomSeat: bottomSeat ?? this.bottomSeat,
        multiRon: multiRon,
        agariYame: agariYame,
        tenpaiYame: tenpaiYame,
        overtime: overtime,
      );

  Map<String, dynamic> toJson() => {
        'startPoints': startPoints,
        'returnPoints': returnPoints,
        'umaBig': umaBig,
        'umaSmall': umaSmall,
        'eastOnly': eastOnly,
        'roundingMode': roundingMode,
        'bottomSeat': bottomSeat,
        'multiRon': multiRon,
        'agariYame': agariYame,
        'tenpaiYame': tenpaiYame,
        'overtime': overtime,
      };

  factory GameSettings.fromJson(Map<String, dynamic> j) => GameSettings(
        startPoints: j['startPoints'] as int,
        returnPoints: j['returnPoints'] as int,
        umaBig: j['umaBig'] as int,
        umaSmall: j['umaSmall'] as int,
        eastOnly: j['eastOnly'] as bool,
        roundingMode: j['roundingMode'] as int,
        bottomSeat: (j['bottomSeat'] as int?) ?? 0,
        multiRon: (j['multiRon'] as int?) ?? multiRonDouble,
        agariYame: (j['agariYame'] as bool?) ?? true,
        tenpaiYame: (j['tenpaiYame'] as bool?) ?? true,
        overtime: (j['overtime'] as bool?) ?? true,
      );
}

/// 한 국의 사건 기록.
class GameEvent {
  final String kind; // win | riichi | draw | adjust
  final String description;
  final List<int> delta; // 4명 점수 변화
  final String roundLabel;

  const GameEvent(this.kind, this.description, this.delta, this.roundLabel);

  Map<String, dynamic> toJson() =>
      {'kind': kind, 'description': description, 'delta': delta, 'round': roundLabel};

  factory GameEvent.fromJson(Map<String, dynamic> j) => GameEvent(
        j['kind'] as String,
        j['description'] as String,
        (j['delta'] as List).cast<int>(),
        j['round'] as String,
      );
}

/// 기록 하나(화료·유국·리치·정정 — 한 번에 들어간 사건 묶음)를 넣기 직전의 판 상태.
/// 되돌리기는 이 상태로 돌아가고 그 뒤 사건을 지운다. 사건은 뒤에 붙기만 하므로 사건 수로 자른다.
class GameCheckpoint {
  final int eventCount;
  final List<int> scores;
  final int roundWind;
  final int roundNumber;
  final int honba;
  final int riichiSticks;
  final int dealer;
  final Set<int> riichiSeats;
  final String? endedBy;

  const GameCheckpoint({
    required this.eventCount,
    required this.scores,
    required this.roundWind,
    required this.roundNumber,
    required this.honba,
    required this.riichiSticks,
    required this.dealer,
    required this.riichiSeats,
    required this.endedBy,
  });

  Map<String, dynamic> toJson() => {
        'eventCount': eventCount,
        'scores': scores,
        'roundWind': roundWind,
        'roundNumber': roundNumber,
        'honba': honba,
        'riichiSticks': riichiSticks,
        'dealer': dealer,
        'riichiSeats': riichiSeats.toList()..sort(),
        'endedBy': endedBy,
      };

  factory GameCheckpoint.fromJson(Map<String, dynamic> j) => GameCheckpoint(
        eventCount: j['eventCount'] as int,
        scores: (j['scores'] as List).cast<int>(),
        roundWind: j['roundWind'] as int,
        roundNumber: j['roundNumber'] as int,
        honba: j['honba'] as int,
        riichiSticks: j['riichiSticks'] as int,
        dealer: j['dealer'] as int,
        riichiSeats: (j['riichiSeats'] as List).cast<int>().toSet(),
        endedBy: j['endedBy'] as String?,
      );
}

/// 정산 결과 한 줄.
class Settlement {
  final int seat;
  final String name;
  final int rank;
  final int points;

  /// 천점 단위 최종값(우마·오카 포함).
  final double score;

  const Settlement(this.seat, this.name, this.rank, this.points, this.score);
}

class Game {
  final String id;
  final DateTime startedAt;
  GameSettings settings;
  final List<String> names;
  final List<int> scores;

  /// 장풍 0 동, 1 남, 2 서, 3 북.
  int roundWind;

  /// 국 번호 1~4.
  int roundNumber;
  int honba;

  /// 공탁 리치봉 개수.
  int riichiSticks;

  /// 현재 친의 자리(0~3). 자리 0 이 기동 동가.
  int dealer;

  /// 이번 국에 리치를 선언한 자리. 국이 끝나면 비운다.
  final Set<int> riichiSeats;
  final List<GameEvent> events;

  /// 되돌리기 지점(기록마다 하나, 오래된 것부터). [GameStore.mutate] 가 사건이 늘어난 변경마다 넣는다.
  final List<GameCheckpoint> checkpoints;
  bool finished;

  /// 끝난 이유: '종료'(올라스 뒤 1위가 반환점 이상, 또는 서입 없음), '연장전 종료', '아가리야메', '텐파이야메'.
  /// 끝난 뒤에는 정산만 할 수 있다(토비는 [anyBusted]).
  String? endedBy;

  Game({
    required this.id,
    required this.startedAt,
    required this.settings,
    required this.names,
    List<int>? scores,
    this.roundWind = 0,
    this.roundNumber = 1,
    this.honba = 0,
    this.riichiSticks = 0,
    this.dealer = 0,
    Set<int>? riichiSeats,
    List<GameEvent>? events,
    List<GameCheckpoint>? checkpoints,
    this.finished = false,
    this.endedBy,
  })  : scores = scores ?? List.filled(4, settings.startPoints),
        riichiSeats = riichiSeats ?? {},
        events = events ?? [],
        checkpoints = checkpoints ?? [] {
    if (names.length != 4) throw ArgumentError('4명이어야 합니다');
  }

  /// 중간부터 기록을 시작한다. 자리 순서가 기동 동→남→서→북이므로 친은 국 번호로 정해진다.
  /// 시작 시점의 점수 차이는 '중간부터 시작' 사건으로 남긴다.
  factory Game.resumed({
    required String id,
    required DateTime startedAt,
    required GameSettings settings,
    required List<String> names,
    required List<int> scores,
    required int roundWind,
    required int roundNumber,
    int honba = 0,
    int riichiSticks = 0,
  }) {
    if (roundNumber < 1 || roundNumber > 4) throw ArgumentError('국은 1~4');
    final g = Game(
      id: id,
      startedAt: startedAt,
      settings: settings,
      names: names,
      scores: List.of(scores),
      roundWind: roundWind,
      roundNumber: roundNumber,
      honba: honba,
      riichiSticks: riichiSticks,
      dealer: roundNumber - 1,
    );
    final delta = [for (var s = 0; s < 4; s++) scores[s] - settings.startPoints];
    g.events.add(GameEvent(
        'adjust',
        '중간부터 기록 시작${riichiSticks > 0 ? ' (공탁 $riichiSticks)' : ''}',
        delta,
        g.roundLabel));
    return g;
  }

  static const windNames = ['동', '남', '서', '북'];

  String get roundLabel => '${windNames[roundWind]}$roundNumber국'
      '${honba > 0 ? ' $honba본장' : ''}';

  /// 자리 [seat] 의 현재 자풍.
  int seatWindOf(int seat) => Tiles.east + ((seat - dealer) % 4 + 4) % 4;

  int get roundWindTile => Tiles.east + roundWind;

  bool get isLastRound => roundWind == (settings.eastOnly ? 0 : 1) && roundNumber == 4;

  /// 정규 국수를 넘겼는지(연장 구간).
  bool get isOvertime => roundWind > (settings.eastOnly ? 0 : 1);

  /// 토비: 누구든 점수가 0 미만이면 대국이 끝난다(점수는 마이너스 그대로 두고 정산한다).
  bool get anyBusted => scores.any((s) => s < 0);

  /// 토비로 끝났으면 마이너스인 자리들(점수 낮은 순).
  List<int> get bustedSeats =>
      [for (var s = 0; s < 4; s++) if (scores[s] < 0) s]..sort((a, b) => scores[a].compareTo(scores[b]));

  /// 도중 유국 사유(점수판 "유국" 창). 트리플론은 거치 촬영 흐름이 따로 넣는다.
  static const abortiveReasons = ['구종구패', '사풍연타', '사깡산료', '사가리치'];

  /// 대국이 끝났는가(토비 또는 아가리야메·텐파이야메). 끝나면 점수판은 정산만 남긴다.
  bool get isOver => anyBusted || endedBy != null;

  /// 끝난 이유 한 줄(점수판 배너·스낵바).
  String get endNote {
    if (anyBusted) {
      return '토비: ${bustedSeats.map((s) => '${names[s]} ${scores[s]}').join(', ')}. 대국이 끝났습니다. 정산으로 가세요.';
    }
    final top = topSeat;
    return switch (endedBy) {
      '아가리야메' || '텐파이야메' => '$endedBy: ${names[dealer]} 1위로 끝났습니다. 정산으로 가세요.',
      '연장전 종료' => '연장전 종료: ${names[top]} ${scores[top]} 1위. 정산으로 가세요.',
      _ => '대국 종료: ${names[top]} ${scores[top]} 1위. 정산으로 가세요.',
    };
  }

  /// 점수판 머리글의 짧은 표시.
  String get endLabel => anyBusted
      ? '토비 — 종료'
      : switch (endedBy) {
          '종료' => '대국 종료',
          '연장전 종료' => '연장전 종료',
          _ => '$endedBy — 종료',
        };

  /// 1위 자리(동점은 기동 자리 순).
  int get topSeat => [for (var s = 0; s < 4; s++) s].firstWhere((s) => rankOf(s) == 1);

  bool get _someoneReachedReturn => scores.any((s) => s >= settings.returnPoints);

  /// 현재 순위(1~4). 동점은 기동 자리 순(정산과 같다).
  int rankOf(int seat) =>
      1 + [for (var s = 0; s < 4; s++) if (scores[s] > scores[seat] || (scores[s] == scores[seat] && s < seat)) s].length;

  /// 올라스에서 친이 1위면 연장하지 않고 끝내는가(작혼식: 자동). 반환점 이상이어야 끝난다(서입과 같은 조건).
  bool _yameNow({required bool tenpai}) {
    if (!isLastRound || !(tenpai ? settings.tenpaiYame : settings.agariYame)) return false;
    return rankOf(dealer) == 1 && scores[dealer] >= settings.returnPoints;
  }

  void _endBy(String kind) {
    endedBy = kind;
    riichiSeats.clear();
    final who = kind == '아가리야메' || kind == '텐파이야메' ? '${names[dealer]} 1위로 종료' : '1위 ${names[topSeat]} ${scores[topSeat]}';
    events.add(GameEvent('end', '$kind — $who', List.filled(4, 0), roundLabel));
    // 남은 공탁은 1위가 가져간다(작혼·텐호).
    if (riichiSticks > 0) {
      final top = topSeat;
      final delta = List.filled(4, 0)..[top] = riichiSticks * 1000;
      _apply(delta);
      events.add(GameEvent('adjust', '남은 공탁 $riichiSticks → 1위 ${names[top]}', delta, roundLabel));
      riichiSticks = 0;
    }
  }

  /// 한 국이 끝났다. 작혼식 종료 판정 뒤 다음 국으로:
  /// - 정규 올라스가 끝나면(친 교체) 누군가 반환점 이상이면 '종료', 아니면 서입(설정이 꺼져 있으면 '종료').
  /// - 연장전에서는 매 국 끝에 누군가 반환점 이상이면 '연장전 종료', 마지막 국(서4국)이 친 교체로 끝나도 종료(북입 없음).
  /// 친이 연장하는 올라스는 끝난 것이 아니라 판정하지 않는다(아가리야메·텐파이야메는 따로 본다).
  void _endHand({required bool dealerKeeps, required bool incrementHonba}) {
    if (isOvertime) {
      if (_someoneReachedReturn || (!dealerKeeps && roundNumber == 4)) return _endBy('연장전 종료');
    } else if (isLastRound && !dealerKeeps) {
      if (_someoneReachedReturn || !settings.overtime) return _endBy('종료');
      _advance(dealerKeeps: false, incrementHonba: incrementHonba);
      final top = topSeat;
      events.add(GameEvent('note', '${settings.eastOnly ? '남입' : '서입'} — 1위 ${names[top]} ${scores[top]} < 반환점 ${settings.returnPoints}',
          List.filled(4, 0), roundLabel));
      return;
    }
    _advance(dealerKeeps: dealerKeeps, incrementHonba: incrementHonba);
  }

  // ---------- 사건 ----------

  /// [fromPhoto] 면 점수판에서 누른 게 아니라 화료 사진에서 읽어 자동으로 넣은 리치다.
  void declareRiichi(int seat, {bool fromPhoto = false}) {
    final delta = List.filled(4, 0);
    delta[seat] = -1000;
    _apply(delta);
    riichiSticks++;
    riichiSeats.add(seat);
    events.add(GameEvent('riichi', '${names[seat]} 리치${fromPhoto ? ' (자동)' : ''}', delta, roundLabel));
  }

  /// 화료 한 번의 점수 변화(4명). 점수판 없이도 쓴다(결과 화면 미리보기).
  /// [sticks] 는 이미 공탁에 있는 리치봉, [newRiichi] 는 이번에 새로 넣는 리치 자리(1000점씩 내고 화료자가 가져간다).
  /// 론인데 [loser] 가 없으면 방총자 몫은 빼고 돌려준다.
  ///
  /// 파오(책임지불, 작혼식 — 대삼원·대사희): [paoSeat] 가 있으면 [pao](그 역만 몫만, 본장 없음)를
  /// 쯔모면 파오한 사람이 전액, 론이면 파오한 사람과 방총자가 절반씩 낸다. 겹친 다른 역만·본장은 평소대로.
  /// 파오한 사람이 방총자이거나 화료자면 평소대로.
  static List<int> winDelta({
    required int dealer,
    required int winner,
    required Payment payment,
    required bool isTsumo,
    int? loser,
    int sticks = 0,
    Iterable<int> newRiichi = const [],
    int? paoSeat,
    Payment? pao,
  }) {
    final delta = List.filled(4, 0);
    final hasPao = paoSeat != null && pao != null && paoSeat != winner && paoSeat != loser;
    if (isTsumo) {
      for (var s = 0; s < 4; s++) {
        if (s == winner) continue;
        var pays = s == dealer ? payment.tsumoFromDealer : payment.tsumoFromNonDealer;
        if (hasPao) pays -= s == dealer ? pao.tsumoFromDealer : pao.tsumoFromNonDealer;
        delta[s] -= pays;
        delta[winner] += pays;
      }
      if (hasPao) {
        delta[paoSeat] -= pao.total;
        delta[winner] += pao.total;
      }
    } else if (loser != null) {
      final half = hasPao ? pao.ron ~/ 2 : 0;
      delta[loser] -= payment.ron - half;
      if (hasPao) delta[paoSeat] -= half;
      delta[winner] += payment.ron;
    }
    for (final s in newRiichi) {
      delta[s] -= 1000;
    }
    delta[winner] += (sticks + newRiichi.length) * 1000;
    return delta;
  }

  /// 화료 때 자동으로 넣을 리치 자리: 사진에 보인 자리 + (계산한 손패가 리치면) 화료자.
  /// [otherWinners] 는 동시 론의 다른 화료자와 그 손패의 리치 여부(화료자 리치는 사진보다 손패 계산을 따른다).
  /// 점수판에 이미 있는 자리와 1000점 미만인 자리는 뺀다.
  Set<int> autoRiichiCandidates(Set<int> photoRiichiSeats,
      {required int winner, required bool winnerRiichi, Map<int, bool> otherWinners = const {}}) {
    final winners = {winner: winnerRiichi, ...otherWinners};
    final c = <int>{...photoRiichiSeats}..removeAll(winners.keys);
    for (final e in winners.entries) {
      if (e.value) c.add(e.key);
    }
    c.removeAll(riichiSeats);
    c.removeWhere((s) => scores[s] < 1000);
    return c;
  }

  /// 동시 론의 화료자를 방총자 다음 차례부터 가까운 순으로. 첫 사람이 본장·공탁을 가져가고, 머리치기면 혼자 인정된다.
  static List<int> ronOrder(int loser, Iterable<int> winners) {
    int dist(int w) => ((w - loser) % 4 + 4) % 4;
    return winners.toList()..sort((a, b) => dist(a).compareTo(dist(b)));
  }

  /// 동시 론 한 번의 점수 변화. [ron] 은 화료자별 론 점수(본장 제외).
  /// 본장(300 × [honba])·공탁([sticks] + [newRiichi])은 [ronOrder] 첫 사람이 가져간다.
  static List<int> multiRonDelta({
    required int loser,
    required Map<int, int> ron,
    int honba = 0,
    int sticks = 0,
    Iterable<int> newRiichi = const [],
  }) {
    final delta = List.filled(4, 0);
    for (final e in ron.entries) {
      delta[loser] -= e.value;
      delta[e.key] += e.value;
    }
    final head = ronOrder(loser, ron.keys).first;
    delta[loser] -= honba * 300;
    delta[head] += honba * 300;
    for (final s in newRiichi) {
      delta[s] -= 1000;
    }
    delta[head] += (sticks + newRiichi.length) * 1000;
    return delta;
  }

  /// 동시 론(더블론·트리플론). [payments] 는 본장을 **빼고** 계산한 지불액(Situation.honba 0)이다.
  /// 본장·공탁은 방총자에게서 가까운 화료자가 가져가고, 친이 화료자 중에 있으면 연장(본장 +1)한다.
  void multiRon({
    required int loser,
    required Map<int, Payment> payments,
    Map<int, String> summaries = const {},
  }) {
    if (payments.isEmpty) throw ArgumentError('화료자가 없습니다');
    if (payments.containsKey(loser)) throw ArgumentError('방총자는 화료자일 수 없습니다');
    final sticks = riichiSticks;
    final delta = multiRonDelta(
      loser: loser,
      ron: {for (final e in payments.entries) e.key: e.value.ron},
      honba: honba,
      sticks: sticks,
    );
    riichiSticks = 0;
    _apply(delta);
    final order = ronOrder(loser, payments.keys);
    final kind = switch (order.length) { 2 => '더블론', 3 => '트리플론', _ => '론' };
    events.add(GameEvent(
        'win',
        '$kind(${names[loser]}) '
            '${order.map((w) => [names[w], ?summaries[w], '${payments[w]!.ron}'].join(' ')).join(' / ')}'
            '${honba > 0 ? ' +본장 ${names[order.first]}' : ''}'
            '${sticks > 0 ? ' +공탁 $sticks ${names[order.first]}' : ''}',
        delta,
        roundLabel));
    final dealerWon = payments.containsKey(dealer);
    if (dealerWon && _yameNow(tenpai: false)) return _endBy('아가리야메');
    _endHand(dealerKeeps: dealerWon, incrementHonba: dealerWon);
  }

  /// 도중 유국(트리플론을 유국으로 하는 규칙 등): 점수 이동 없음, 친 유지, 본장 +1, 공탁은 다음 국으로.
  void abortiveDraw(String reason) {
    events.add(GameEvent('draw', '도중 유국 ($reason)', List.filled(4, 0), roundLabel));
    _endHand(dealerKeeps: true, incrementHonba: true);
  }

  /// 사가리치: 점수판에 아직 없는 리치를 먼저 공탁에 넣고(1000점 미만이면 못 넣음) 도중 유국한다.
  void fourRiichiDraw() {
    for (var s = 0; s < 4; s++) {
      if (!riichiSeats.contains(s) && scores[s] >= 1000) declareRiichi(s);
    }
    abortiveDraw('사가리치');
  }

  /// 화료. [payment] 는 본장을 포함한 지불액이어야 한다 (Situation.honba 로 계산).
  /// 론이면 [loser] 필수.
  /// 파오(책임지불)면 [paoSeat] 와 그 역만 몫 [pao](본장 없음)를 준다([winDelta]).
  void win({
    required int winner,
    required Payment payment,
    required bool isTsumo,
    int? loser,
    String summary = '',
    int? paoSeat,
    Payment? pao,
  }) {
    if (!isTsumo && loser == null) throw ArgumentError('론은 방총자가 필요합니다');
    final delta = winDelta(
        dealer: dealer,
        winner: winner,
        payment: payment,
        isTsumo: isTsumo,
        loser: loser,
        sticks: riichiSticks,
        paoSeat: paoSeat,
        pao: pao);
    final sticks = riichiSticks;
    riichiSticks = 0;
    _apply(delta);
    final how = isTsumo ? '쯔모' : '론(${names[loser!]})';
    final paoNote = paoSeat != null && pao != null && paoSeat != winner && paoSeat != loser ? ' 파오(${names[paoSeat]})' : '';
    events.add(GameEvent(
        'win',
        '${names[winner]} $how $summary$paoNote${sticks > 0 ? ' +공탁 $sticks' : ''}',
        delta,
        roundLabel));
    if (winner == dealer && _yameNow(tenpai: false)) return _endBy('아가리야메');
    _endHand(dealerKeeps: winner == dealer, incrementHonba: winner == dealer);
  }

  /// 유국. [tenpai] 는 텐파이한 자리 집합.
  /// [nagashi] 는 유국만관 자리: 만관 쯔모만큼 받고(본장 없음, 공탁은 그대로) 노텐 벌점은 없다.
  /// 친 연장·본장은 보통 유국과 같다(친이 텐파이면 연장).
  void draw(Set<int> tenpai, {Set<int> nagashi = const {}}) {
    final delta = List.filled(4, 0);
    final n = tenpai.length;
    if (nagashi.isNotEmpty) {
      for (final w in nagashi) {
        for (var s = 0; s < 4; s++) {
          if (s == w) continue;
          final pays = w == dealer || s == dealer ? 4000 : 2000;
          delta[s] -= pays;
          delta[w] += pays;
        }
      }
    } else if (n > 0 && n < 4) {
      final gain = 3000 ~/ n;
      final pay = 3000 ~/ (4 - n);
      for (var s = 0; s < 4; s++) {
        delta[s] = tenpai.contains(s) ? gain : -pay;
      }
    }
    _apply(delta);
    final who = tenpai.isEmpty ? '전원 노텐' : tenpai.map((s) => names[s]).join('·');
    final label = nagashi.isEmpty
        ? '유국'
        : '유국만관 ${(nagashi.toList()..sort()).map((s) => names[s]).join('·')}';
    events.add(GameEvent('draw', '$label (텐파이: $who)', delta, roundLabel));
    if (tenpai.contains(dealer) && _yameNow(tenpai: true)) return _endBy('텐파이야메');
    _endHand(dealerKeeps: tenpai.contains(dealer), incrementHonba: true);
  }

  /// 수동 보정(실수 정정 등).
  void adjust(List<int> delta, String reason) {
    _apply(delta);
    events.add(GameEvent('adjust', reason, List.of(delta), roundLabel));
  }

  /// 기록 정정: 점수 보정과 본장·공탁 고치기를 사건 하나로 남긴다(되돌리기 가능).
  void correct({required List<int> delta, int? honba, int? riichiSticks, required String reason}) {
    final notes = <String>[
      if (honba != null && honba != this.honba) '본장 ${this.honba}→$honba',
      if (riichiSticks != null && riichiSticks != this.riichiSticks) '공탁 ${this.riichiSticks}→$riichiSticks',
    ];
    _apply(delta);
    if (honba != null) this.honba = honba;
    if (riichiSticks != null) this.riichiSticks = riichiSticks;
    events.add(GameEvent('adjust', notes.isEmpty ? reason : '$reason (${notes.join(', ')})', List.of(delta), roundLabel));
  }

  // ---------- 되돌리기 ----------

  GameCheckpoint checkpoint() => GameCheckpoint(
        eventCount: events.length,
        scores: List.of(scores),
        roundWind: roundWind,
        roundNumber: roundNumber,
        honba: honba,
        riichiSticks: riichiSticks,
        dealer: dealer,
        riichiSeats: Set.of(riichiSeats),
        endedBy: endedBy,
      );

  bool get canUndo => checkpoints.isNotEmpty;

  /// 사건 [eventIndex] 를 지우려면 돌아갈 지점(그 사건이 들어간 기록의 직전). 지점이 없는 사건
  /// (중간부터 시작, 되돌리기 전에 저장된 옛 기록)이면 null.
  GameCheckpoint? checkpointBefore(int eventIndex) {
    for (final c in checkpoints.reversed) {
      if (c.eventCount <= eventIndex) return c;
    }
    return null;
  }

  /// [c] 로 돌아가면 지워질 사건들(오래된 것부터).
  List<GameEvent> eventsAfter(GameCheckpoint c) => events.sublist(c.eventCount);

  /// [c] 상태로 돌아가고 그 뒤 사건·지점을 지운다.
  void rewindTo(GameCheckpoint c) {
    scores.setAll(0, c.scores);
    roundWind = c.roundWind;
    roundNumber = c.roundNumber;
    honba = c.honba;
    riichiSticks = c.riichiSticks;
    dealer = c.dealer;
    riichiSeats
      ..clear()
      ..addAll(c.riichiSeats);
    endedBy = c.endedBy;
    events.removeRange(c.eventCount, events.length);
    checkpoints.removeWhere((x) => x.eventCount >= c.eventCount);
  }

  /// 같은 대국의 다른 시점 [o] 로 판 상태·기록을 바꾼다("다시 실행"). 설정·이름은 그대로.
  void restoreFrom(Game o) {
    scores.setAll(0, o.scores);
    roundWind = o.roundWind;
    roundNumber = o.roundNumber;
    honba = o.honba;
    riichiSticks = o.riichiSticks;
    dealer = o.dealer;
    riichiSeats
      ..clear()
      ..addAll(o.riichiSeats);
    endedBy = o.endedBy;
    events
      ..clear()
      ..addAll(o.events);
    checkpoints
      ..clear()
      ..addAll(o.checkpoints);
  }

  void _apply(List<int> delta) {
    for (var s = 0; s < 4; s++) {
      scores[s] += delta[s];
    }
  }

  void _advance({required bool dealerKeeps, required bool incrementHonba}) {
    honba = incrementHonba ? honba + 1 : 0;
    riichiSeats.clear();
    if (dealerKeeps) return;
    dealer = (dealer + 1) % 4;
    roundNumber++;
    if (roundNumber > 4) {
      roundNumber = 1;
      roundWind = (roundWind + 1) % 4;
    }
  }

  // ---------- 정산 ----------

  List<Settlement> settle() {
    final order = List.generate(4, (i) => i)
      ..sort((a, b) {
        final c = scores[b].compareTo(scores[a]);
        return c != 0 ? c : a.compareTo(b); // 동점은 기동 자리 순
      });
    final uma = [settings.umaBig, settings.umaSmall, -settings.umaSmall, -settings.umaBig];
    final result = <Settlement>[];
    for (var rank = 0; rank < 4; rank++) {
      final seat = order[rank];
      var base = _thousands(scores[seat] - settings.returnPoints);
      base += uma[rank];
      if (rank == 0) base += settings.oka;
      result.add(Settlement(seat, names[seat], rank + 1, scores[seat], base));
    }
    return result;
  }

  double _thousands(int points) {
    if (settings.roundingMode == 1) {
      // 오사육입: 500 이하 버림, 600 이상 올림
      final sign = points < 0 ? -1 : 1;
      final abs = points.abs();
      final q = abs ~/ 1000;
      final r = abs % 1000;
      return (sign * (r >= 600 ? q + 1 : q)).toDouble();
    }
    return (points / 1000 * 10).round() / 10;
  }

  // ---------- 직렬화 ----------

  Map<String, dynamic> toJson() => {
        'id': id,
        'startedAt': startedAt.toIso8601String(),
        'settings': settings.toJson(),
        'names': names,
        'scores': scores,
        'roundWind': roundWind,
        'roundNumber': roundNumber,
        'honba': honba,
        'riichiSticks': riichiSticks,
        'dealer': dealer,
        'riichiSeats': riichiSeats.toList()..sort(),
        'events': events.map((e) => e.toJson()).toList(),
        'checkpoints': checkpoints.map((c) => c.toJson()).toList(),
        'finished': finished,
        'endedBy': endedBy,
      };

  factory Game.fromJson(Map<String, dynamic> j) => Game(
        id: j['id'] as String,
        startedAt: DateTime.parse(j['startedAt'] as String),
        settings: GameSettings.fromJson(j['settings'] as Map<String, dynamic>),
        names: (j['names'] as List).cast<String>(),
        scores: (j['scores'] as List).cast<int>(),
        roundWind: j['roundWind'] as int,
        roundNumber: j['roundNumber'] as int,
        honba: j['honba'] as int,
        riichiSticks: j['riichiSticks'] as int,
        dealer: j['dealer'] as int,
        riichiSeats: ((j['riichiSeats'] as List?) ?? const []).cast<int>().toSet(),
        events: (j['events'] as List)
            .map((e) => GameEvent.fromJson(e as Map<String, dynamic>))
            .toList(),
        checkpoints: ((j['checkpoints'] as List?) ?? const [])
            .map((c) => GameCheckpoint.fromJson(c as Map<String, dynamic>))
            .toList(),
        finished: j['finished'] as bool,
        endedBy: j['endedBy'] as String?,
      );
}

/// 판·부로 지불액을 만든다 (화면에서 직접 입력할 때).
Payment paymentFor({
  required int han,
  required int fu,
  required bool isDealer,
  required bool isTsumo,
  required int honba,
  RuleSet rules = RuleSet.standard,
}) {
  final bp = basePoints(han, fu, rules);
  return payment(bp.base, Situation(
    isTsumo: isTsumo,
    seatWind: isDealer ? Tiles.east : Tiles.south,
    honba: honba,
  ));
}

/// 역만 지불액.
Payment yakumanPaymentFor({
  required int count,
  required bool isDealer,
  required bool isTsumo,
  required int honba,
}) {
  final bp = yakumanPoints(count);
  return payment(bp.base, Situation(
    isTsumo: isTsumo,
    seatWind: isDealer ? Tiles.east : Tiles.south,
    honba: honba,
  ));
}
