import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/tenhou6_export.dart';

// ─────────────────────────────────────────────────────────────────────────────
// 재생 검사기: 변환기와 따로 짠 코드로 출력 JSON 을 B-1 규칙대로 돌린다.
// ─────────────────────────────────────────────────────────────────────────────

/// 패보 패 → 천봉 번호(변환기 것을 쓰지 않고 따로).
int _tn(PaifuTile t) {
  const suits = [10, 20, 30];
  if (t.red) return 51 + t.tile ~/ 9;
  if (t.tile >= 27) return 41 + t.tile - 27;
  return suits[t.tile ~/ 9] + t.tile % 9 + 1;
}

/// 천봉 번호의 종류(적5 → 보통 5).
int _kind(int n) => n >= 51 ? (n - 50) * 10 + 5 : n;

bool _validTile(int n) =>
    (n >= 11 && n <= 19) || (n >= 21 && n <= 29) || (n >= 31 && n <= 39) || (n >= 41 && n <= 47) || (n >= 51 && n <= 53);

class _CallRec {
  final String kind; // pon · chi
  final int from; // 천봉 자리
  final int taken;
  final List<int> own; // 정렬
  _CallRec(this.kind, this.from, this.taken, this.own);
  @override
  String toString() => '$kind<$from:$taken+$own';
  @override
  bool operator ==(Object o) => o is _CallRec && o.kind == kind && o.from == from && o.taken == taken && _listEq(o.own, own);
  @override
  int get hashCode => Object.hash(kind, from, taken, Object.hashAll(own));
}

bool _listEq<T>(List<T> a, List<T> b) {
  if (a.length != b.length) return false;
  for (var i = 0; i < a.length; i++) {
    if (a[i] != b[i]) return false;
  }
  return true;
}

class _Sim {
  final int kyoku, honba, kyotaku;
  final List<int> scores;
  final List<List<int>> haipai;
  final List<List<Object>> takes, outs;
  final List resultEntry;

  final hand = List.generate(4, (_) => <int>[]);
  final discarded = List.generate(4, (_) => <int>[]); // 실제 패
  final rawOut = List.generate(4, (_) => <Object>[]);
  final riichiIdx = List.generate(4, (_) => <int>[]);
  final calls = List.generate(4, (_) => <_CallRec>[]);
  final handsBeforeDraw = List.generate(4, (_) => <List<int>>[]);
  final order = <int>[]; // 버린 자리 순
  late String end; // tsumo · discard
  late int lastActor;

  _Sim._(this.kyoku, this.honba, this.kyotaku, this.scores, this.haipai, this.takes, this.outs, this.resultEntry);

  factory _Sim.run(Map<String, dynamic> json) {
    expect(json.keys.toList(), ['title', 'name', 'rule', 'log']);
    expect(json['rule'], {'disp': '般南喰赤', 'aka': 1});
    expect(json['name'], ['A', 'B', 'C', 'D']);
    final logs = json['log'] as List;
    expect(logs, hasLength(1));
    final log = logs.first as List;
    expect(log, hasLength(4 + 12 + 1), reason: '국 머리 4 + 자리 넷 × 3 + 결과');
    final head = (log[0] as List).cast<int>();
    final sim = _Sim._(
      head[0],
      head[1],
      head[2],
      (log[1] as List).cast<int>(),
      [for (var t = 0; t < 4; t++) (log[4 + 3 * t] as List).cast<int>()],
      [for (var t = 0; t < 4; t++) (log[5 + 3 * t] as List).cast<Object>()],
      [for (var t = 0; t < 4; t++) (log[6 + 3 * t] as List).cast<Object>()],
      log[16] as List,
    );
    sim._countTiles((log[2] as List).cast<int>(), (log[3] as List).cast<int>());
    sim._play();
    return sim;
  }

  /// 같은 패 4장 이하 · 적5 한 장 이하 · 보통 5 세 장 이하(배패 + 뽑은 패 + 도라 · 뒷도라 표시패).
  void _countTiles(List<int> dora, List<int> ura) {
    final all = <int>[
      for (final h in haipai) ...h,
      for (final d in takes) ...d.whereType<int>(),
      ...dora,
      ...ura,
    ];
    final byKind = <int, int>{}, exact = <int, int>{};
    for (final n in all) {
      expect(_validTile(n), isTrue, reason: '패 번호 $n');
      byKind[_kind(n)] = (byKind[_kind(n)] ?? 0) + 1;
      exact[n] = (exact[n] ?? 0) + 1;
    }
    byKind.forEach((k, c) => expect(c, lessThanOrEqualTo(4), reason: '패 $k 가 $c장'));
    for (final r in [51, 52, 53]) {
      expect(exact[r] ?? 0, lessThanOrEqualTo(1), reason: '적5 $r');
      expect(exact[_kind(r)] ?? 0, lessThanOrEqualTo(3), reason: '보통 ${_kind(r)}');
    }
  }

  static final _chi = RegExp(r'^c(\d\d)(\d\d)(\d\d)$');
  static final _ponL = RegExp(r'^p(\d\d)(\d\d)(\d\d)$');
  static final _ponM = RegExp(r'^(\d\d)p(\d\d)(\d\d)$');
  static final _ponR = RegExp(r'^(\d\d)(\d\d)p(\d\d)$');

  /// 울기 문자열을 읽는다(내 자리 me 기준).
  static _CallRec parse(String s, int me) {
    RegExpMatch? m;
    int g(int i) => int.parse(m!.group(i)!);
    if ((m = _chi.firstMatch(s)) != null) {
      final own = [g(2), g(3)];
      final ks = [_kind(g(1)), ...own.map(_kind)]..sort();
      expect(ks[0] ~/ 10, inInclusiveRange(1, 3), reason: '치 $s');
      expect(ks[1] == ks[0] + 1 && ks[2] == ks[0] + 2 && ks[0] ~/ 10 == ks[2] ~/ 10, isTrue, reason: '치 $s 이어진 패 아님');
      return _CallRec('chi', (me + 3) % 4, g(1), own..sort());
    }
    late int from, taken;
    late List<int> own;
    if ((m = _ponL.firstMatch(s)) != null) {
      (from, taken, own) = ((me + 3) % 4, g(1), [g(2), g(3)]);
    } else if ((m = _ponM.firstMatch(s)) != null) {
      (from, taken, own) = ((me + 2) % 4, g(2), [g(1), g(3)]);
    } else if ((m = _ponR.firstMatch(s)) != null) {
      (from, taken, own) = ((me + 1) % 4, g(3), [g(1), g(2)]);
    } else {
      fail('모르는 울기 문자열 $s');
    }
    expect({_kind(taken), ...own.map(_kind)}, hasLength(1), reason: '퐁 $s 같은 패 아님');
    return _CallRec('pon', from, taken, own..sort());
  }

  bool get _allUsed {
    for (var t = 0; t < 4; t++) {
      if (_ti[t] < takes[t].length || _oi[t] < outs[t].length) return false;
    }
    return true;
  }

  final _ti = [0, 0, 0, 0], _oi = [0, 0, 0, 0];

  void _play() {
    for (var t = 0; t < 4; t++) {
      expect(haipai[t], hasLength(13), reason: '자리 $t 배패');
      hand[t].addAll(haipai[t]);
    }
    var turn = kyoku % 4;
    int? lastFrom, lastTile;
    for (var steps = 0;; steps++) {
      expect(steps, lessThan(500));
      expect(_ti[turn], lessThan(takes[turn].length), reason: '자리 $turn 차례인데 뽑기 목록 끝');
      final item = takes[turn][_ti[turn]++];
      int? drew;
      if (item is int) {
        expect(item, isNot(60), reason: '뽑기 목록에 60');
        handsBeforeDraw[turn].add([...hand[turn]]..sort());
        hand[turn].add(item);
        drew = item;
      } else {
        final c = parse(item as String, turn);
        expect(lastFrom, c.from, reason: '울기 $item: 직전 버림 자리');
        expect(lastTile, c.taken, reason: '울기 $item: 직전 버림 패');
        for (final o in c.own) {
          expect(hand[turn].remove(o), isTrue, reason: '울기 $item: 손에 $o 없음');
        }
        calls[turn].add(c);
      }
      expect(hand[turn].length, 14 - 3 * calls[turn].length);
      if (_oi[turn] == outs[turn].length) {
        expect(drew, isNotNull, reason: '울기 뒤 버림 없이 끝남');
        expect(_allUsed, isTrue, reason: '자리 $turn 가 뽑고 끝났는데 다른 목록이 남음');
        end = 'tsumo';
        lastActor = turn;
        return;
      }
      final raw = outs[turn][_oi[turn]++];
      rawOut[turn].add(raw);
      int v;
      if (raw is String) {
        expect(raw.startsWith('r'), isTrue);
        riichiIdx[turn].add(discarded[turn].length);
        v = int.parse(raw.substring(1));
      } else {
        v = raw as int;
      }
      final tile = v == 60 ? drew : v;
      expect(tile, isNotNull, reason: '60 인데 직전에 뽑은 패 없음(자리 $turn)');
      expect(hand[turn].remove(tile), isTrue, reason: '자리 $turn 가 손에 없는 $tile 를 버림');
      discarded[turn].add(tile!);
      order.add(turn);
      lastFrom = turn;
      lastTile = tile;
      if (_allUsed) {
        end = 'discard';
        lastActor = turn;
        return;
      }
      var next = (turn + 1) % 4;
      for (var k = 1; k < 4; k++) {
        final o = (turn + k) % 4;
        if (_ti[o] < takes[o].length && takes[o][_ti[o]] is String) {
          final c = parse(takes[o][_ti[o]] as String, o);
          if (c.from == turn && c.taken == tile) {
            next = o;
            break;
          }
        }
      }
      turn = next;
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 작은 패보 만들기: hero 손패는 스크립트에서 계산해 적는다.
// ─────────────────────────────────────────────────────────────────────────────

/// 스크립트 줄:
///   `D 1p`             hero 뽑기
///   `X2 9m [t|h] [R]`  자리 2 버림(t 쯔모기리 · h 손에서 냄 · 없으면 null, R 리치)
///   `pon3<1 5z 5z 5z`  자리 3 이 자리 1 에게서 퐁(chi · call · kan 도 같은 꼴)
Map<String, dynamic> _game({
  String round = '동1국',
  int honba = 0,
  int dealer = 0,
  required int hero,
  required List<String> start,
  required List<String> script,
  Map<String, dynamic>? result,
  List<String> dora = const [],
  List<String> ura = const [],
}) {
  final cur = [...start];
  String? drawn;
  String? lastDiscard;
  final events = <Map<String, dynamic>>[];
  for (final line in script) {
    final w = line.split(' ');
    if (w[0] == 'D') {
      drawn = w[1];
      events.add({'type': 'draw', 'seat': hero, 'tile': w[1], 'hand': [...cur]});
    } else if (w[0].startsWith('X')) {
      final seat = int.parse(w[0].substring(1));
      final tg = w.contains('t') ? true : (w.contains('h') ? false : null);
      final e = <String, dynamic>{'type': 'discard', 'seat': seat, 'tile': w[1], 'tsumogiri': tg, 'riichi': w.contains('R')};
      if (seat == hero) {
        if (drawn != null) cur.add(drawn);
        expect(cur.remove(w[1]), isTrue, reason: '스크립트: hero 손에 ${w[1]} 없음');
        e['hand'] = [...cur];
        drawn = null;
      }
      lastDiscard = w[1];
      events.add(e);
    } else {
      final m = RegExp(r'^([a-z]+)(\d)<(\d)$').firstMatch(w[0])!;
      final seat = int.parse(m.group(2)!);
      final e = <String, dynamic>{'type': 'call', 'seat': seat, 'kind': m.group(1), 'from': int.parse(m.group(3)!), 'tiles': w.sublist(1)};
      if (seat == hero) {
        final own = [...w.sublist(1)]..remove(lastDiscard);
        for (final o in own) {
          expect(cur.remove(o), isTrue);
        }
        e['hand'] = [...cur];
      }
      events.add(e);
    }
  }
  return {
    'version': 1,
    'id': 'small',
    'round': round,
    'honba': honba,
    'dealer': dealer,
    'hero': hero,
    'dora_indicators': dora,
    'ura_indicators': ura,
    'events': events,
    'result': result,
  };
}

Paifu _p(Map<String, dynamic> j) => Paifu.fromJson(jsonDecode(jsonEncode(j)) as Map<String, dynamic>);

/// A: 다른 자리 퐁 세 방향 · 치, hero 쯔모기리(true · null · 적5) · 손에서 냄. 유국.
Map<String, dynamic> _gameA({String round = '동1국', int honba = 0, Map<String, dynamic>? result = const {'type': 'draw'}}) => _game(
      round: round,
      honba: honba,
      hero: 0,
      start: ['1m', '2m', '3m', '4m', '6m', '7m', '8m', '9p', '2s', '3s', '7s', '8s', '8s'],
      script: [
        'D 1p', 'X0 1p t', //
        'X1 5z',
        'pon3<1 5z 5z 5z', 'X3 9m', // 맞은편
        'D 2p', 'X0 9p h',
        'X1 6z',
        'pon2<1 6z 6z 6z', 'X2 7z', // 윗자리
        'X3 1z',
        'D 3p', 'X0 3p t',
        'X1 4s',
        'chi2<1 4s 5s 6s', 'X2 9s',
        'X3 2z',
        'D 4p', 'X0 4p',
        'X1 1s',
        'X2 7m',
        'pon1<2 7m 7m 7m', 'X1 8p', // 아랫자리
        'X2 3z',
        'X3 2z',
        'D 0m', 'X0 0m t',
      ],
      result: result,
    );

/// B: hero(자리 1) 퐁 뒤 버림, 다른 자리 리치(손에서 냄 / 정책), 리치 뒤 버림, hero 쯔모 화료.
Map<String, dynamic> _gameB() => _game(
      hero: 1,
      start: ['2p', '3p', '4p', '4m', '5m', '6m', '7z', '7z', '4s', '6s', '8s', '8s', '1p'],
      script: [
        'X0 1z',
        'D 9m', 'X1 9m t',
        'X2 3m',
        'X3 5p',
        'X0 7z',
        'pon1<0 7z 7z 7z', 'X1 1p',
        'X2 2z',
        'X3 4z R',
        'X0 2s',
        'D 3s', 'X1 3s t',
        'X2 9s',
        'X3 6s',
        'X0 9p',
        'D 5s',
      ],
      result: {
        'type': 'tsumo',
        'winner': 1,
        'win_tile': '5s',
        'hand': ['2p', '3p', '4p', '4m', '5m', '6m', '4s', '6s', '8s', '8s'],
        'melds': [
          {'kind': 'pon', 'tiles': ['7z', '7z', '7z']},
        ],
      },
    );

/// C: hero(자리 2) 쯔모기리 리치(r60), hero 론.
Map<String, dynamic> _gameC() => _game(
      hero: 2,
      start: ['2m', '3m', '4m', '6m', '7m', '8m', '2s', '3s', '4s', '7p', '8p', '9s', '9s'],
      script: [
        'X0 1z', 'X1 9m', 'D 1m', 'X2 1m t', 'X3 2z', //
        'X0 3z', 'X1 9p', 'D 4z', 'X2 4z t R', 'X3 9s',
        'X0 8m', 'X1 1p', 'D 7z', 'X2 7z', 'X3 5z',
        'X0 6p',
      ],
      result: {'type': 'ron', 'winner': 2, 'loser': 0, 'win_tile': '6p'},
    );

/// D: 남2국(kyoku 5) · 친 = 자리 3(≠ 5 % 4), hero(자리 0) 손에서 낸 리치, 다른 자리(1) 론 · 끝 손패 적힘.
const _handD = ['1m', '2m', '3m', '4m', '5m', '6m', '7p', '8p', '2s', '2s', '3s', '4s', '5s'];
Map<String, dynamic> _gameD() => _game(
      round: '남2국',
      honba: 2,
      dealer: 3,
      hero: 0,
      start: ['9m', '1s', '4p', '5p', '6s', '7s', '8s', '6m', '6m', '7m', '8m', '5z', '5z'],
      script: [
        'X3 1z', 'D 2p', 'X0 9m h', 'X1 9s', 'X2 4z', //
        'X3 2z', 'D 3p', 'X0 1s h R', 'X1 3m', 'X2 6p',
      ],
      result: {'type': 'ron', 'winner': 1, 'loser': 2, 'win_tile': '6p', 'hand': _handD, 'melds': []},
    );

/// E: 다른 자리(1) 쯔모 화료, 끝 손패 적힘.
const _handE = ['1m', '2m', '4m', '5m', '6m', '7p', '8p', '9p', '2s', '2s', '3s', '4s', '5s'];
Map<String, dynamic> _gameE() => _game(
      hero: 0,
      start: ['9m', '1s', '4p', '5p', '6s', '7s', '8s', '6m', '6m', '7m', '8m', '5z', '5z'],
      script: ['D 1p', 'X0 1p t', 'X1 9m', 'X2 9p', 'X3 9s', 'D 2p', 'X0 2p t'],
      result: {'type': 'tsumo', 'winner': 1, 'win_tile': '3m', 'hand': _handE, 'melds': []},
    );

// ─────────────────────────────────────────────────────────────────────────────
// 패보와 맞춰 보기
// ─────────────────────────────────────────────────────────────────────────────

int _kyokuOf(String round) {
  const winds = ['동', '남', '서', '북'];
  return winds.indexOf(round[0]) * 4 + int.parse(round[1]) - 1;
}

/// 재생 결과가 패보와 맞는지(자리별 버림 · 리치 · 울기 · hero 손패 · 쯔모기리 표기).
void _checkAgainstPaifu(Paifu p, Tenhou6Export out, _Sim sim, UnknownDiscard policy) {
  final kyoku = _kyokuOf(p.round);
  int ts(int s) => ((s - p.dealer + kyoku % 4) % 4 + 4) % 4;
  expect(sim.kyoku, kyoku);
  expect(sim.honba, p.honba);
  expect(sim.kyotaku, 0);
  expect(out.heroIndex, ts(p.hero));

  for (var s = 0; s < 4; s++) {
    final t = ts(s);
    final mine = [for (final e in p.events) if (e.seat == s) e];
    // 버림 · 리치 선언
    final ds = [for (final e in mine) if (e.type == PaifuEventType.discard) e];
    expect(sim.discarded[t], [for (final e in ds) _tn(e.tile!)], reason: '자리 $s 버림 순서');
    expect(sim.riichiIdx[t], [for (final (i, e) in ds.indexed) if (e.riichi) i], reason: '자리 $s 리치');
    // 울기
    final cs = <_CallRec>[];
    PaifuEvent? lastD;
    for (final e in p.events) {
      if (e.type == PaifuEventType.discard) lastD = e;
      if (e.type == PaifuEventType.call && e.seat == s) {
        final ks = [for (final x in e.callTiles) x.tile]..sort();
        final kind = e.callKind == 'chi' || (e.callKind == 'call' && ks[0] != ks[1]) ? 'chi' : 'pon';
        final own = [for (final x in e.callTiles) _tn(x)]..remove(_tn(lastD!.tile!));
        cs.add(_CallRec(kind, ts(e.from!), _tn(lastD.tile!), own..sort()));
      }
    }
    expect(sim.calls[t], cs, reason: '자리 $s 울기');

    // 쯔모기리 표기
    var afterCall = false, riichi = false, known = p.startHand != null;
    PaifuTile? drew;
    var k = 0;
    for (final e in mine) {
      switch (e.type) {
        case PaifuEventType.draw:
          drew = e.tile;
          if (e.hand != null) known = true;
        case PaifuEventType.call:
          afterCall = true;
        case PaifuEventType.discard:
          final raw = sim.rawOut[t][k++];
          final v = raw is String ? int.parse(raw.substring(1)) : raw as int;
          final bool expect60;
          if (s == p.hero) {
            expect60 = !known || (!afterCall && drew == e.tile && e.tsumogiri != false);
          } else if (e.tsumogiri != null) {
            expect60 = e.tsumogiri!;
          } else if (afterCall) {
            expect60 = false;
          } else if (riichi) {
            expect60 = true;
          } else {
            expect60 = policy == UnknownDiscard.tsumogiri;
          }
          expect(v == 60, expect60, reason: '자리 $s $k번째 버림 ${e.tile} (패보 쯔모기리 ${e.tsumogiri}) → $raw');
          if (!expect60) expect(v, _tn(e.tile!));
          if (e.riichi) riichi = true;
          afterCall = false;
          drew = null;
      }
    }
  }

  // hero 매 순 손패(뽑기 전)
  final hd = [for (final e in p.events) if (e.seat == p.hero && e.type == PaifuEventType.draw) e];
  final got = sim.handsBeforeDraw[out.heroIndex];
  expect(got, hasLength(hd.length), reason: 'hero 뽑기 수');
  var compared = 0;
  for (final (i, e) in hd.indexed) {
    if (e.hand == null) continue;
    expect(got[i], [for (final x in e.hand!) _tn(x)]..sort(), reason: 'hero ${i + 1}번째 뽑기 전 손패');
    compared++;
  }
  expect(compared, greaterThan(0));

  // 결과
  final r = p.result;
  if (r == null || r.type == 'draw') {
    expect(sim.resultEntry, ['流局', [0, 0, 0, 0]]);
    expect(sim.end, 'discard');
  } else {
    final w = ts(r.winner!);
    final l = r.type == 'ron' ? ts(r.loser!) : w;
    expect(sim.resultEntry, ['和了', [0, 0, 0, 0], [w, l, w, '']]);
    expect(sim.end, r.type == 'ron' ? 'discard' : 'tsumo');
    expect(sim.lastActor, l);
  }
}

Paifu _asset(String id) =>
    Paifu.fromJson(jsonDecode(File('assets/paifu/$id.json').readAsStringSync()) as Map<String, dynamic>);

void main() {
  test('패 번호', () {
    expect(tenhouTileNumber(PaifuTile.parse('1m')), 11);
    expect(tenhouTileNumber(PaifuTile.parse('9p')), 29);
    expect(tenhouTileNumber(PaifuTile.parse('5s')), 35);
    expect(tenhouTileNumber(PaifuTile.parse('1z')), 41);
    expect(tenhouTileNumber(PaifuTile.parse('7z')), 47);
    expect(tenhouTileNumber(PaifuTile.parse('0m')), 51);
    expect(tenhouTileNumber(PaifuTile.parse('0p')), 52);
    expect(tenhouTileNumber(PaifuTile.parse('0s')), 53);
  });

  group('실제 열 판', () {
    // 11-20: 유국 판 r13 · r15 · r16 · L16 은 텐파이 공개자 손패, r14 는 2순 정답 손패, r18 은 Opus 읽기 손패를 넣어 더함.
    // 녹화 전 순은 짐작으로 채워져(guess) L16 도 내보내짐.
    for (final id in ['r11_130921', 'r12_131655', 'r13_132644', 'r14_133610', 'r15_134151', 'r16_135321', 'L16_135321', 'r17_140450', 'r18_141259', 'r19_142013']) {
      for (final policy in UnknownDiscard.values) {
        test('$id · ${policy.name}', () {
          final p = _asset(id);
          final before = jsonEncode(p.toJson());
          final out = toTenhou6(p, unknownAs: policy);
          expect(jsonEncode(p.toJson()), before, reason: 'Paifu 를 바꾸지 않음');
          final sim = _Sim.run(jsonDecode(jsonEncode(out.json)) as Map<String, dynamic>);
          _checkAgainstPaifu(p, out, sim, policy);
          expect(sim.scores, [25000, 25000, 25000, 25000]);
          expect(out.assumptions.first, startsWith('1.'));
          expect(out.assumptions.any((a) => a.startsWith('7.')), isTrue);
        });
      }
    }
  });

  test('실제 네 판의 자리 맞춤(친 = kyoku_num % 4)', () {
    for (final (id, kyoku, hero) in [('r11_130921', 0, 3), ('r12_131655', 1, 2), ('r17_140450', 5, 2), ('r19_142013', 7, 1)]) {
      final out = toTenhou6(_asset(id));
      expect(((out.json['log'] as List).first as List).first, [kyoku, _asset(id).honba, 0], reason: id);
      expect(out.heroIndex, hero, reason: id);
    }
  });

  test('kyoku_num · honba', () {
    for (final (round, k) in [('동1국', 0), ('동2국', 1), ('남2국', 5), ('남4국', 7)]) {
      final out = toTenhou6(_p(_gameA(round: round, honba: 3)));
      final head = ((out.json['log'] as List).first as List).first;
      expect(head, [k, 3, 0], reason: round);
      // 자리 0 = 친 → 천봉 자리 k % 4.
      expect(out.heroIndex, k % 4, reason: round);
      _Sim.run(out.json);
    }
  });

  test('재생 검사기 자체: 망가뜨린 출력은 걸린다', () {
    Map<String, dynamic> fresh() => jsonDecode(jsonEncode(toTenhou6(_asset('r19_142013')).json)) as Map<String, dynamic>;
    List log(Map<String, dynamic> j) => (j['log'] as List).first as List;
    final ok = fresh();
    _Sim.run(ok);
    // 손에 없는 패를 버림
    final a = fresh();
    (log(a)[6 + 3 * 1] as List)[3] = 47;
    expect(() => _Sim.run(a), throwsA(isA<TestFailure>()));
    // 뽑기 목록 하나를 지움(끝에서 다 안 쓰임 · 차례 어긋남)
    final b = fresh();
    (log(b)[5 + 3 * 2] as List).removeLast();
    expect(() => _Sim.run(b), throwsA(isA<TestFailure>()));
    // 퐁의 방향을 바꿈(맞은편에서 가져온 것으로)
    final c = fresh();
    final takes0 = log(c)[5] as List;
    final i = takes0.indexWhere((x) => x is String);
    final s = takes0[i] as String;
    takes0[i] = 'p${s.replaceAll('p', '')}'; // 아랫자리 퐁 → 윗자리 퐁
    expect(takes0[i], isNot(s));
    expect(() => _Sim.run(c), throwsA(isA<TestFailure>()));
    // 같은 패 5장(도라 표시패로 더함)
    final d = fresh();
    final hero = log(d)[4 + 3] as List;
    log(d)[2] = [hero[0], hero[0], hero[0], hero[0]];
    expect(() => _Sim.run(d), throwsA(isA<TestFailure>()));
  });

  group('결정성', () {
    test('같은 시드 두 번 → 같은 JSON', () {
      for (final id in ['r11_130921', 'r19_142013']) {
        final a = jsonEncode(toTenhou6(_asset(id), seed: 7).json);
        final b = jsonEncode(toTenhou6(_asset(id), seed: 7).json);
        expect(a, b);
      }
    });

    test('시드를 바꾸면 다른 자리 배패만 달라짐', () {
      final p = _asset('r19_142013');
      final a = toTenhou6(p, seed: 0), b = toTenhou6(p, seed: 1);
      final la = (a.json['log'] as List).first as List, lb = (b.json['log'] as List).first as List;
      final h = a.heroIndex;
      expect(lb[4 + 3 * h], la[4 + 3 * h], reason: 'hero 배패');
      expect(lb[5 + 3 * h], la[5 + 3 * h], reason: 'hero 뽑기');
      for (var t = 0; t < 4; t++) {
        expect(lb[6 + 3 * t], la[6 + 3 * t], reason: '자리 $t 버림');
      }
      expect([for (var t = 0; t < 4; t++) if (t != h) jsonEncode(la[4 + 3 * t]) != jsonEncode(lb[4 + 3 * t])], contains(true));
      _Sim.run(b.json);
    });
  });

  group('작은 패보', () {
    test('A: 퐁 세 방향 · 치 · hero 쯔모기리 표기 · 유국', () {
      for (final policy in UnknownDiscard.values) {
        final p = _p(_gameA());
        final out = toTenhou6(p, unknownAs: policy);
        final sim = _Sim.run(out.json);
        _checkAgainstPaifu(p, out, sim, policy);
        final log = (out.json['log'] as List).first as List;
        expect(log[5 + 3 * 3], contains('45p4545'), reason: '자리 3 이 맞은편(1)에게서 퐁');
        expect(log[5 + 3 * 2], containsAllInOrder(['p464646', 'c343536']), reason: '자리 2 가 윗자리(1)에게서 퐁 · 치');
        expect(log[5 + 3 * 1], contains('1717p17'), reason: '자리 1 이 아랫자리(2)에게서 퐁');
        expect(log[5], [21, 22, 23, 24, 51], reason: 'hero 뽑기');
        expect(log[6], [60, 29, 60, 60, 60], reason: 'hero 버림: true → 60, false → 수, null 같은 패 → 60, 적5 쯔모기리 → 60');
        expect(log[16], ['流局', [0, 0, 0, 0]]);
      }
    });

    test('A 결과 없음(null) → 流局', () {
      final out = toTenhou6(_p(_gameA(result: null)));
      expect(_Sim.run(out.json).resultEntry, ['流局', [0, 0, 0, 0]]);
      expect(out.assumptions.join('\n'), contains('패보에 결과 없음'));
    });

    test('B: hero 퐁 뒤 버림 · 다른 자리 리치 · hero 쯔모(뽑기가 하나 많음)', () {
      for (final policy in UnknownDiscard.values) {
        final p = _p(_gameB());
        final out = toTenhou6(p, unknownAs: policy);
        final sim = _Sim.run(out.json);
        _checkAgainstPaifu(p, out, sim, policy);
        final log = (out.json['log'] as List).first as List;
        expect(log[5 + 3], [19, 'p474747', 33, 35], reason: 'hero 뽑기(퐁 포함) — 마지막이 화료패');
        expect(log[6 + 3], [60, 21, 60], reason: 'hero 퐁 뒤 버림은 수');
        expect((log[5 + 3] as List).length, (log[6 + 3] as List).length + 1);
        final x3 = log[6 + 9] as List;
        expect(x3[1], policy == UnknownDiscard.tedashi ? 'r44' : 'r60', reason: '리치 선언 표기');
        expect(x3[2], 60, reason: '리치 뒤 버림');
        expect(log[16], ['和了', [0, 0, 0, 0], [1, 1, 1, '']]);
      }
    });

    test('C: hero 쯔모기리 리치(r60) · hero 론', () {
      final p = _p(_gameC());
      final out = toTenhou6(p);
      final sim = _Sim.run(out.json);
      _checkAgainstPaifu(p, out, sim, UnknownDiscard.tedashi);
      final log = (out.json['log'] as List).first as List;
      expect(log[6 + 6], [60, 'r60', 60]);
      expect(log[16], ['和了', [0, 0, 0, 0], [2, 0, 2, '']]);
    });

    test('D: 친 ≠ kyoku_num % 4 자리 맞춤 · 손에서 낸 리치 · 다른 자리 론(끝 손패 남음) · scores', () {
      final p = _p(_gameD());
      final out = toTenhou6(p, scores: [10000, 20000, 30000, 40000]);
      final sim = _Sim.run(out.json);
      _checkAgainstPaifu(p, out, sim, UnknownDiscard.tedashi);
      // 남2국 → 5, 친(자리 3) → 천봉 자리 1, 우리 자리 s → (s + 2) % 4.
      expect(sim.kyoku, 5);
      expect(sim.honba, 2);
      expect(out.heroIndex, 2);
      expect(sim.scores, [30000, 40000, 10000, 20000]);
      final log = (out.json['log'] as List).first as List;
      expect(log[6 + 6], [19, 'r31']);
      expect(log[16], ['和了', [0, 0, 0, 0], [3, 0, 3, '']]);
      expect(sim.hand[3]..sort(), [for (final c in _handD) _tn(PaifuTile.parse(c))]..sort(), reason: '화료자 끝 손패');
      expect(out.assumptions.first, contains('[30000, 40000, 10000, 20000]'));
    });

    test('E: 다른 자리 쯔모(끝 손패 + 화료패 남음)', () {
      final p = _p(_gameE());
      final out = toTenhou6(p);
      final sim = _Sim.run(out.json);
      _checkAgainstPaifu(p, out, sim, UnknownDiscard.tedashi);
      final log = (out.json['log'] as List).first as List;
      expect((log[5 + 3] as List).last, 13);
      expect((log[5 + 3] as List).length, (log[6 + 3] as List).length + 1);
      expect(sim.hand[1]..sort(), [for (final c in [..._handE, '3m']) _tn(PaifuTile.parse(c))]..sort());
    });
  });

  group('오류', () {
    Matcher err(String part) => throwsA(isA<Tenhou6ExportError>().having((e) => e.message, 'message', contains(part)));

    test('hero 손패 없는 판(r20 — 3반장, 손패 없는 마지막 예시)', () {
      // 11-20: r13 · r15 · r16 · L16(텐파이 공개자) · r14(2순 정답) · r18(Opus 읽기)에 손패를 넣어 손패 없는 판은 r20 하나.
      expect(() => toTenhou6(_asset('r20_143236')), err('손패가 적힌 뽑기가 없음'));
    });

    test('손패가 적히기 전 hero 울기(L16 의 녹화 전 1순 짐작을 되돌림 — 1순 다음이 퐁)는 지원 안 함', () {
      // 11-20: 예시의 녹화 전 순은 짐작으로 채워져 L16 도 내보내짐(위 '실제 열 판'). 짐작 전 꼴로 되돌려 이 오류를 본다.
      final j = jsonDecode(File('assets/paifu/L16_135321.json').readAsStringSync()) as Map<String, dynamic>;
      for (final e in (j['events'] as List).cast<Map<String, dynamic>>()) {
        if (e['guess'] == true) {
          e['hand'] = null;
          if (e['type'] == 'draw') e['tile'] = null;
          if (e['type'] == 'discard') e['tsumogiri'] = null;
        }
      }
      expect(() => toTenhou6(Paifu.fromJson(j)), err('손패가 적히기 전 hero 울기'));
    });

    Map<String, dynamic> r19() => jsonDecode(File('assets/paifu/r19_142013.json').readAsStringSync()) as Map<String, dynamic>;
    List<Map<String, dynamic>> heroEv(Map<String, dynamic> j) =>
        [for (final e in (j['events'] as List).cast<Map<String, dynamic>>()) if (e['seat'] == j['hero'] && e['hand'] != null) e];

    test('손패가 적힌 뒤 중간이 빈 판', () {
      final j = r19();
      final draws = heroEv(j).where((e) => e['type'] == 'draw').toList();
      draws[3]['hand'] = null;
      expect(() => toTenhou6(Paifu.fromJson(j)), err('손패가 빔'));
      final k = r19();
      final ds = heroEv(k).where((e) => e['type'] == 'draw').toList();
      ds[3]['tile'] = null;
      expect(() => toTenhou6(Paifu.fromJson(k)), err('뽑은 패가 빔'));
    });

    test('hero 손패가 어긋난 판', () {
      final j = r19();
      final ds = heroEv(j).where((e) => e['type'] == 'discard').toList();
      final h = (ds[2]['hand'] as List).cast<String>();
      h[0] = h[0] == '1z' ? '2z' : '1z';
      expect(() => toTenhou6(Paifu.fromJson(j)), throwsA(isA<Tenhou6ExportError>()));
    });

    test('깡', () {
      final j = _gameA();
      final ev = (j['events'] as List).cast<Map<String, dynamic>>();
      final i = ev.indexWhere((e) => e['type'] == 'call' && e['seat'] == 3);
      ev[i] = {...ev[i], 'kind': 'kan', 'tiles': ['5z', '5z', '5z', '5z']};
      expect(() => toTenhou6(_p(j)), err('깡'));
    });

    test('종류 모름 + 한 장짜리 울기', () {
      final j = _gameA();
      final ev = (j['events'] as List).cast<Map<String, dynamic>>();
      final i = ev.indexWhere((e) => e['type'] == 'call' && e['seat'] == 3);
      ev[i] = {...ev[i], 'kind': 'call', 'tiles': ['5z']};
      expect(() => toTenhou6(_p(j)), err('한 장'));
    });

    test('종류 모름 + 세 장이면 퐁 · 치로 읽음', () {
      final j = _gameA();
      for (final e in (j['events'] as List).cast<Map<String, dynamic>>()) {
        if (e['type'] == 'call') e['kind'] = 'call';
      }
      final p = _p(j);
      final out = toTenhou6(p);
      final sim = _Sim.run(out.json);
      _checkAgainstPaifu(p, out, sim, UnknownDiscard.tedashi);
      expect(jsonEncode(out.json), jsonEncode(toTenhou6(_p(_gameA())).json));
    });

    test('같은 패 5장', () {
      final j = _gameA()..['dora_indicators'] = ['5z', '5z'];
      expect(() => toTenhou6(_p(j)), err('5장째'));
    });

    test('적5 두 장', () {
      final j = _gameA()..['dora_indicators'] = ['0m'];
      expect(() => toTenhou6(_p(j)), err('적5'));
    });
  });
}
