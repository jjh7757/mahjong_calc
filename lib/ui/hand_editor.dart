import 'package:flutter/foundation.dart';

import '../engine/calculator.dart' as engine;
import '../engine/calculator.dart' show Hand, Meld, RuleSet, ScoreResult, Situation, Tiles;
import '../game/game.dart';
import '../table/merge.dart';

/// 팔레트에서 패를 누르면 어디에 들어가는지.
enum InputTarget { hand, dora, ura }

/// 손패 한 장. 적도라 여부를 같이 가진다.
class HandTile {
  final int tile;
  final bool red;
  const HandTile(this.tile, {this.red = false});
}

/// 입력 화면 상태. 손패·부른 묶음·상황·룰을 모두 들고 있다.
class HandEditor extends ChangeNotifier {
  final List<HandTile> closed = [];
  final List<Meld> melds = [];

  /// 각 묶음에 들어 있는 적도라 수.
  final List<int> meldRed = [];

  /// 화료패 위치([closed] 인덱스). null 이면 마지막 패.
  int? winIndex;

  /// 사진 인식 결과 중 확신도가 낮은 패의 인덱스. 손패를 손대면 비운다.
  final Set<int> uncertain = {};

  InputTarget target = InputTarget.hand;

  bool isTsumo = false;
  int seatWind = Tiles.east;
  int roundWind = Tiles.east;
  bool riichi = false;
  bool doubleRiichi = false;
  bool ippatsu = false;
  bool lastTile = false;
  bool rinshan = false;
  bool chankan = false;
  bool firstTurnWin = false;
  final List<int> doraIndicators = [];
  final List<int> uraIndicators = [];
  int honba = 0;

  RuleSet rules = RuleSet.standard;

  /// 진행 중인 대국에서 이 손패가 누구 것인지(자리 0~3). null 이면 안 고른 것.
  int? gameSeat;

  /// 거치 촬영 사진에서 리치가 보인 자리. 화료 기록 때 리치봉을 자동으로 넣는 데 쓴다.
  final Set<int> photoRiichiSeats = {};

  /// 마지막으로 대국 값을 가져온 시점의 국 상태. 같은 상태면 다시 덮어쓰지 않는다.
  String? _syncedGameKey;

  static const int maxIndicators = 5;

  int get maxClosed => 14 - 3 * melds.length;
  bool get isClosed => melds.every((m) => !m.isOpen);
  bool get hasRiichi => riichi || doubleRiichi;
  bool get isDealer => seatWind == Tiles.east;

  int get effectiveWinIndex {
    if (closed.isEmpty) return -1;
    final i = winIndex;
    if (i == null || i < 0 || i >= closed.length) return closed.length - 1;
    return i;
  }

  HandTile? get winTile =>
      closed.isEmpty ? null : closed[effectiveWinIndex];

  int get redTotal =>
      closed.where((t) => t.red).length + meldRed.fold(0, (a, b) => a + b);

  /// 손패·묶음·도라 표시패를 모두 합친 같은 패의 수.
  int countOf(int tile) {
    var n = closed.where((t) => t.tile == tile).length;
    for (final m in melds) {
      n += m.tiles.where((t) => t == tile).length;
    }
    n += doraIndicators.where((t) => t == tile).length;
    n += uraIndicators.where((t) => t == tile).length;
    return n;
  }

  bool _redUsed(int suit) =>
      closed.any((t) => t.red && Tiles.suit(t.tile) == suit);

  /// 추가할 수 없으면 이유를 돌려준다.
  String? cannotAdd(int tile, {bool red = false}) {
    if (countOf(tile) >= 4) return '${Tiles.name(tile)}은(는) 이미 4장입니다';
    switch (target) {
      case InputTarget.hand:
        if (closed.length >= maxClosed) return '손패는 $maxClosed장까지입니다';
        if (red && _redUsed(Tiles.suit(tile))) return '적도라는 색마다 한 장입니다';
        return null;
      case InputTarget.dora:
        if (doraIndicators.length >= maxIndicators) {
          return '도라 표시패는 $maxIndicators장까지입니다';
        }
        return null;
      case InputTarget.ura:
        if (!hasRiichi) return '뒷도라는 리치했을 때만 셉니다';
        if (uraIndicators.length >= maxIndicators) {
          return '뒷도라 표시패는 $maxIndicators장까지입니다';
        }
        return null;
    }
  }

  void add(int tile, {bool red = false}) {
    if (cannotAdd(tile, red: red) != null) return;
    switch (target) {
      case InputTarget.hand:
        closed.add(HandTile(tile, red: red));
        winIndex = closed.length - 1;
        // 손패가 다 찼으면 다음은 도라 표시패 차례다.
        if (closed.length == maxClosed) target = InputTarget.dora;
        break;
      case InputTarget.dora:
        doraIndicators.add(tile);
        break;
      case InputTarget.ura:
        uraIndicators.add(tile);
        break;
    }
    notifyListeners();
  }

  /// 사진 인식 결과로 손패를 채운다. 기존 손패는 지운다.
  /// 돌려주는 값은 사용자에게 보여줄 안내 문구(잘린 패, 4장 초과 등).
  String setFromRecognition(List<({String code, double confidence})> tiles,
      {double uncertainBelow = 0.6}) {
    closed.clear();
    uncertain.clear();
    winIndex = null;
    final notes = <String>[];
    var dropped = 0;
    for (final t in tiles) {
      final red = t.code[0] == '0';
      final tile = Tiles.parse(t.code);
      if (closed.length >= maxClosed) {
        dropped++;
        continue;
      }
      if (countOf(tile) >= 4 || (red && _redUsed(Tiles.suit(tile)))) {
        dropped++;
        continue;
      }
      closed.add(HandTile(tile, red: red));
      if (t.confidence < uncertainBelow) uncertain.add(closed.length - 1);
    }
    if (dropped > 0) notes.add('$dropped장은 넣지 못했습니다(장수 초과 또는 4장 초과)');
    if (uncertain.isNotEmpty) notes.add('노란 테두리 ${uncertain.length}장은 확신이 낮으니 확인하세요');
    notifyListeners();
    return notes.join('. ');
  }

  /// 거치 촬영 판독([TableMerge])으로 손패·울기·상황을 통째로 채운다.
  /// 대국 동기화 키를 맞춰 두어 화면이 다시 그려져도 값이 덮이지 않는다.
  /// 장수가 넘치면 앞에서부터 들어갈 만큼만 넣는다.
  void setFromMerge(TableMerge m, Game g) {
    clear();
    melds.addAll(m.melds);
    meldRed.addAll(m.meldRed);
    for (var i = 0; i < m.closed.length && closed.length < maxClosed; i++) {
      final t = m.closed[i];
      closed.add(HandTile(t.tile, red: t.red));
      if (m.uncertain.contains(i)) uncertain.add(closed.length - 1);
    }
    winIndex = closed.isEmpty ? null : closed.length - 1;
    isTsumo = m.isTsumo;
    seatWind = m.situation.seatWind;
    roundWind = m.situation.roundWind;
    riichi = m.situation.riichi;
    honba = m.situation.honba.clamp(0, 20);
    doraIndicators.addAll(m.situation.doraIndicators.take(maxIndicators));
    uraIndicators.addAll(m.situation.uraIndicators.take(maxIndicators));
    gameSeat = m.winner;
    photoRiichiSeats.addAll(m.photoRiichiSeats);
    _syncedGameKey = _gameKey(g);
    notifyListeners();
  }

  void removeClosedAt(int index) {
    uncertain.clear();
    closed.removeAt(index);
    // 손패를 고치려는 것이니 도라 탭에 있었으면 손패 탭으로 돌아간다.
    if (target == InputTarget.dora) target = InputTarget.hand;
    final w = winIndex;
    if (w != null) {
      if (w == index) {
        winIndex = null;
      } else if (w > index) {
        winIndex = w - 1;
      }
    }
    notifyListeners();
  }

  void setWin(int index) {
    winIndex = index;
    notifyListeners();
  }

  void removeDoraAt(int index) {
    doraIndicators.removeAt(index);
    notifyListeners();
  }

  void removeUraAt(int index) {
    uraIndicators.removeAt(index);
    notifyListeners();
  }

  /// 묶음을 추가한다. 실패하면 이유를 돌려준다.
  String? addMeld(Meld meld, {int red = 0}) {
    if (melds.length >= 4) return '묶음은 4개까지입니다';
    for (final t in meld.tiles.toSet()) {
      final need = meld.tiles.where((x) => x == t).length;
      if (countOf(t) + need > 4) return '${Tiles.name(t)}이(가) 4장을 넘습니다';
    }
    final newMax = 14 - 3 * (melds.length + 1);
    if (closed.length > newMax) {
      return '손패가 $newMax장을 넘습니다. 손패를 먼저 줄여 주세요';
    }
    melds.add(meld);
    meldRed.add(red);
    firstTurnWin = false;
    if (closed.length == maxClosed && target == InputTarget.hand) {
      target = InputTarget.dora;
    }
    notifyListeners();
    return null;
  }

  void removeMeldAt(int index) {
    melds.removeAt(index);
    meldRed.removeAt(index);
    notifyListeners();
  }

  /// 뒷도라 탭은 리치했을 때만 뜻이 있으니, 리치가 꺼져 있으면 같이 켠다(멘젠일 때만).
  void setTarget(InputTarget t) {
    if (t == InputTarget.ura && !hasRiichi) {
      if (!isClosed) return;
      riichi = true;
    }
    target = t;
    notifyListeners();
  }

  void setTsumo(bool v) {
    isTsumo = v;
    if (!v) {
      rinshan = false;
      firstTurnWin = false;
    }
    if (v) chankan = false;
    notifyListeners();
  }

  void setSeatWind(int w) {
    seatWind = w;
    notifyListeners();
  }

  void setRoundWind(int w) {
    roundWind = w;
    notifyListeners();
  }

  void setRiichi(bool v) {
    riichi = v;
    if (v) doubleRiichi = false;
    if (!hasRiichi) _clearRiichiOnly();
    notifyListeners();
  }

  void setDoubleRiichi(bool v) {
    doubleRiichi = v;
    if (v) riichi = false;
    if (!hasRiichi) _clearRiichiOnly();
    notifyListeners();
  }

  /// 리치가 꺼지면 리치에 딸린 것(일발·뒷도라·뒷도라 탭)을 같이 끈다.
  void _clearRiichiOnly() {
    ippatsu = false;
    uraIndicators.clear();
    if (target == InputTarget.ura) target = InputTarget.hand;
  }

  /// 일발은 리치 뒤에만 있으니, 리치가 꺼져 있으면 같이 켠다(멘젠일 때만).
  void setIppatsu(bool v) {
    if (v && !hasRiichi) {
      if (!isClosed) return;
      riichi = true;
    }
    ippatsu = v;
    notifyListeners();
  }

  void setLastTile(bool v) {
    lastTile = v;
    notifyListeners();
  }

  /// 영상개화는 쯔모뿐이라 켜면 쯔모로 바꾼다.
  void setRinshan(bool v) {
    rinshan = v;
    if (v) {
      isTsumo = true;
      chankan = false;
    }
    notifyListeners();
  }

  /// 창깡은 론뿐이라 켜면 론으로 바꾼다.
  void setChankan(bool v) {
    chankan = v;
    if (v) {
      isTsumo = false;
      rinshan = false;
      firstTurnWin = false;
    }
    notifyListeners();
  }

  /// 천화·지화는 쯔모뿐이라 켜면 쯔모로 바꾼다.
  void setFirstTurnWin(bool v) {
    firstTurnWin = v && melds.isEmpty;
    if (firstTurnWin) {
      isTsumo = true;
      chankan = false;
    }
    notifyListeners();
  }

  void setHonba(int v) {
    honba = v.clamp(0, 20);
    notifyListeners();
  }

  static String _gameKey(Game g) =>
      '${g.id}:${g.roundWind}:${g.roundNumber}:${g.honba}:${g.dealer}:${(g.riichiSeats.toList()..sort()).join(',')}';

  /// 진행 중인 대국의 국 상태(장풍·본장, 자리를 골랐으면 자풍·리치)를 상황 입력에 채운다.
  /// 국이 바뀌지 않았으면 아무것도 하지 않아 사용자가 손으로 고친 값을 지키고,
  /// 대국이 없으면 자리 선택만 지운다. 알림은 보내지 않는다(빌드 중에 불러도 된다).
  /// 돌려주는 값은 실제로 채웠는지.
  bool syncFromGame(Game? g) {
    if (g == null) {
      gameSeat = null;
      _syncedGameKey = null;
      return false;
    }
    final key = _gameKey(g);
    if (key == _syncedGameKey) return false;
    _syncedGameKey = key;
    _fillFromGame(g);
    return true;
  }

  /// 대국에서 손패 주인을 고른다. 자풍·장풍·본장·리치가 그 자리 값으로 바뀐다.
  void setGameSeat(Game g, int? seat) {
    gameSeat = seat;
    _syncedGameKey = _gameKey(g);
    _fillFromGame(g);
    notifyListeners();
  }

  void _fillFromGame(Game g) {
    roundWind = g.roundWindTile;
    honba = g.honba.clamp(0, 20);
    final seat = gameSeat;
    if (seat == null) return;
    seatWind = g.seatWindOf(seat);
    if (isClosed) {
      final r = g.riichiSeats.contains(seat);
      riichi = r;
      if (!r) {
        doubleRiichi = false;
        ippatsu = false;
        uraIndicators.clear();
      }
    }
  }

  void setRules(RuleSet r) {
    rules = r;
    notifyListeners();
  }

  void clear() {
    closed.clear();
    uncertain.clear();
    melds.clear();
    meldRed.clear();
    winIndex = null;
    doraIndicators.clear();
    uraIndicators.clear();
    riichi = false;
    doubleRiichi = false;
    ippatsu = false;
    lastTile = false;
    rinshan = false;
    chankan = false;
    firstTurnWin = false;
    honba = 0;
    target = InputTarget.hand;
    gameSeat = null;
    photoRiichiSeats.clear();
    _syncedGameKey = null;
    notifyListeners();
  }

  Situation get situation => Situation(
        isTsumo: isTsumo,
        seatWind: seatWind,
        roundWind: roundWind,
        riichi: riichi,
        doubleRiichi: doubleRiichi,
        ippatsu: ippatsu,
        lastTile: lastTile,
        rinshan: rinshan,
        chankan: chankan,
        firstTurnWin: firstTurnWin,
        doraIndicators: List.unmodifiable(doraIndicators),
        uraIndicators: List.unmodifiable(uraIndicators),
        honba: honba,
      );

  /// 천화·지화를 켜고 손패를 비워 두면 손패 없이 바로 점수를 낸다.
  bool get firstTurnWinOnly => firstTurnWin && closed.isEmpty && melds.isEmpty;

  /// 지금 손패(장수가 다 찼을 때만). 결과 화면에서 패를 그리는 데도 쓴다.
  Hand? get hand => closed.length != maxClosed || winTile == null
      ? null
      : Hand(
          closedTiles: closed.map((t) => t.tile).toList(),
          melds: List.of(melds),
          winTile: winTile!.tile,
          redCount: redTotal,
        );

  ScoreResult calculate() {
    if (firstTurnWinOnly) return engine.firstTurnWinOnly(situation);
    final h = hand;
    if (h == null) {
      return ScoreResult.failure(
          '손패가 $maxClosed장이어야 합니다 (현재 ${closed.length}장)');
    }
    return engine.calculate(h, situation, rules: rules);
  }
}
