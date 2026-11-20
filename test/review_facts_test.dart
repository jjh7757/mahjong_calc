import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/shanten.dart';
import 'package:mahjong_calc/engine/tile.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';
import 'package:mahjong_calc/paifu/review_facts.dart';

/// '123m11z' → ['1m', '2m', '3m', '1z', '1z'].
List<String> h(String s) {
  final out = <String>[];
  final buf = <String>[];
  for (final ch in s.split('')) {
    if ('mpsz'.contains(ch)) {
      for (final d in buf) {
        out.add('$d$ch');
      }
      buf.clear();
    } else {
      buf.add(ch);
    }
  }
  return out;
}

/// '2334p' → 34칸 개수(장수는 맞추지 않는다 — shapeOf 는 장수를 보지 않음).
List<int> c(String s) {
  final out = List<int>.filled(Tiles.count, 0);
  for (final code in h(s)) {
    out[Tiles.parse(code)]++;
  }
  return out;
}

int t(String code) => Tiles.parse(code);

/// 덩어리 하나: ('ryanmen', '23p') → {"kind": "ryanmen", "tiles": ["2p", "3p"]}.
Map<String, dynamic> b(String kind, String tiles) => {'kind': kind, 'tiles': h(tiles)};

const files = ['r19_142013', 'r11_130921', 'r17_140450', 'r13_132644'];

Map<String, dynamic> raw(String id) =>
    jsonDecode(File('assets/paifu/$id.json').readAsStringSync(encoding: utf8)) as Map<String, dynamic>;

Paifu load(String id) => Paifu.fromJson(raw(id));

/// JSON 안의 문자열 전부.
Iterable<String> strings(Object? v) sync* {
  if (v is String) {
    yield v;
  } else if (v is Map) {
    for (final e in v.entries) {
      yield e.key as String;
      yield* strings(e.value);
    }
  } else if (v is List) {
    for (final x in v) {
      yield* strings(x);
    }
  }
}

bool ascending(List<int> xs) {
  for (var i = 1; i < xs.length; i++) {
    if (xs[i - 1] >= xs[i]) return false;
  }
  return true;
}

void main() {
  group('shapeOf — 부록 A-3', () {
    test('triplet: 333p 의 3p → 커쯔 + 또이쯔(3장이어도 pair 도 적음)', () {
      // 3p 3장, 이웃(2p·4p)·한 칸 건너(1p·5p) 없음.
      expect(shapeOf(c('333p'), t('3p')), [b('triplet', '333p'), b('pair', '33p')]);
    });

    test('pair: 55m 의 5m → 또이쯔만', () {
      expect(shapeOf(c('55m'), t('5m')), [b('pair', '55m')]);
    });

    test('sequence: 345s 의 4s → 순자 345 + 양면 34·45', () {
      // 4s: (2,3,4) 2s 없음 · (3,4,5) 됨 · (4,5,6) 6s 없음. 이웃 3s·5s → 양면 둘(1-2·8-9 아님). 2s·6s 없음 → 간짱 없음.
      expect(shapeOf(c('345s'), t('4s')), [b('sequence', '345s'), b('ryanmen', '34s'), b('ryanmen', '45s')]);
    });

    test('sequence 여럿: 34567m 의 5m → 345 · 456 · 567', () {
      // 순자 셋, 양면 45·56, 간짱 35·57.
      expect(shapeOf(c('34567m'), t('5m')), [
        b('sequence', '345m'),
        b('sequence', '456m'),
        b('sequence', '567m'),
        b('ryanmen', '45m'),
        b('ryanmen', '56m'),
        b('kanchan', '35m'),
        b('kanchan', '57m'),
      ]);
    });

    test('ryanmen: 67p 의 6p → 양면 67', () {
      expect(shapeOf(c('67p'), t('6p')), [b('ryanmen', '67p')]);
    });

    test('penchan: 12m 의 1m · 2m, 89s 의 9s · 8s', () {
      expect(shapeOf(c('12m'), t('1m')), [b('penchan', '12m')]);
      expect(shapeOf(c('12m'), t('2m')), [b('penchan', '12m')]);
      expect(shapeOf(c('89s'), t('9s')), [b('penchan', '89s')]);
      expect(shapeOf(c('89s'), t('8s')), [b('penchan', '89s')]);
    });

    test('2m 은 1m 쪽이 변짱, 3m 쪽이 양면 — 순서는 표 순(ryanmen 먼저)', () {
      // 123m 의 2m: 순자 123, 이웃 1m → 12(penchan), 이웃 3m → 23(ryanmen). 간짱: 0m 없음 · 4m 없음.
      expect(shapeOf(c('123m'), t('2m')), [b('sequence', '123m'), b('ryanmen', '23m'), b('penchan', '12m')]);
    });

    test('kanchan: 46p 의 4p · 6p', () {
      expect(shapeOf(c('46p'), t('4p')), [b('kanchan', '46p')]);
      expect(shapeOf(c('46p'), t('6p')), [b('kanchan', '46p')]);
    });

    test('isolated: 1m5p9s1z 의 5p → 뜬 패', () {
      expect(shapeOf(c('1m5p9s1z'), t('5p')), [b('isolated', '5p')]);
    });

    test('겹침: 2334p 의 3p → pair + sequence 234 + ryanmen 23·34', () {
      // 3p 2장 → pair. 순자 (1,2,3) 1p 없음 · (2,3,4) 됨 · (3,4,5) 5p 없음. 이웃 2p·4p → 양면 둘. 1p·5p 없음 → 간짱 없음.
      expect(shapeOf(c('2334p'), t('3p')), [b('pair', '33p'), b('sequence', '234p'), b('ryanmen', '23p'), b('ryanmen', '34p')]);
    });

    test('수트 경계: 9m 과 1p 는 이웃이 아님', () {
      // 89m12p: 9m 의 이웃은 8m 뿐(1p 는 다른 수트), 1p 의 이웃은 2p 뿐.
      expect(shapeOf(c('89m12p'), t('9m')), [b('penchan', '89m')]);
      expect(shapeOf(c('89m12p'), t('1p')), [b('penchan', '12p')]);
      // 9m1p 만: 서로 이웃 아님 → 둘 다 뜬 패. 8m·2p 와도 한 칸 건너가 아님(수트가 다름).
      expect(shapeOf(c('9m1p'), t('9m')), [b('isolated', '9m')]);
      expect(shapeOf(c('8m1p'), t('1p')), [b('isolated', '1p')]);
      // 9m 1p 2p: 수트를 넘는 순자(9m 1p 2p)가 생기지 않는다.
      expect(shapeOf(c('9m12p'), t('1p')), [b('penchan', '12p')]);
      // 9s(26) 와 1z(27) 는 번호로 붙어 있어도 이웃이 아님.
      expect(shapeOf(c('9s1z'), t('9s')), [b('isolated', '9s')]);
    });

    test('자패: triplet · pair · isolated 뿐', () {
      // 동동동 + 남 서: 자패는 순자·이웃이 없다.
      expect(shapeOf(c('11123z'), t('1z')), [b('triplet', '111z'), b('pair', '11z')]);
      expect(shapeOf(c('11123z'), t('2z')), [b('isolated', '2z')]);
      expect(shapeOf(c('55z'), t('5z')), [b('pair', '55z')]);
      expect(shapeOf(c('567z'), t('6z')), [b('isolated', '6z')]);
    });

    test('손에 없는 패는 빈 목록', () {
      expect(shapeOf(c('123m'), t('5p')), isEmpty);
    });
  });

  group('TurnReview.before', () {
    for (final id in files) {
      test(id, () {
        final r = reviewPaifu(load(id));
        for (final tr in r.turns) {
          if (tr.actual == null) {
            expect(tr.before, isNull, reason: '${tr.turn}번째');
          } else {
            final before = tr.before!;
            expect(before.length, Tiles.count);
            expect(before.fold<int>(0, (s, x) => s + x), 14 - 3 * tr.melds, reason: '${tr.turn}번째');
            expect(before[tr.discard.tile], greaterThan(0));
            expect(() => before[0] = 9, throwsUnsupportedError);
          }
        }
      });
    }
  });

  group('reviewFacts — 실제 판', () {
    // 11-20: r19 손패를 고친 정답으로 다시 만듦 — 옛 "5번째 큰 실수(2p 대신 3s 텐파이)" 는 고치기 전 손패에서 나온 것.
    test('r19: 해설할 차례는 6 · 7, 6번째 차례 사실', () {
      final p = load('r19_142013');
      final r = reviewPaifu(p);
      final f = reviewFacts(p, r);
      final turns = (f['turns'] as List).cast<Map<String, dynamic>>();
      expect([for (final x in turns) x['turn']], [6, 7]);

      final x = turns[0];
      final tr = r.turns[5];
      expect(tr.turn, 6);

      // hand: 패보의 hero 6번째 뽑기 사건(hand + tile)에서 직접.
      final j = raw('r19_142013');
      final draws = [
        for (final e in (j['events'] as List).cast<Map<String, dynamic>>())
          if (e['type'] == 'draw' && e['seat'] == j['hero']) e,
      ];
      final d6 = draws[5];
      expect(d6['tile'], '4m');
      final fromRaw = [...(d6['hand'] as List).cast<String>(), d6['tile'] as String]
        ..sort((u, v) => Tiles.parse(u) - Tiles.parse(v));
      expect(x['hand'], fromRaw);
      // 손으로 적은 값: 334m 789m 345p 33s 5s 88s(만 → 통 → 삭).
      expect(x['hand'], h('334789m345p33588s'));
      expect((x['hand'] as List).length, 14);
      expect(x['drawn'], '4m');
      expect(x['discard'], '4m');
      expect(x['grade'], 'mistake');
      expect(x['melds'], 0);

      final actual = x['actual'] as Map<String, dynamic>;
      final best = x['best'] as Map<String, dynamic>;
      expect(actual['discard'], '4m');
      expect(best['discard'], '3m');
      // 3m 버림: 34m 789m 345p 33s 5s 88s → 1샹텐, 2m · 5m(34m 양면) · 3s · 8s(또이쯔) · 4s(35s 간짱) 5종.
      expect(best['shanten'], 1);
      expect(best['kinds'], 5);
      expect([for (final u in best['tiles'] as List) (u as Map)['tile']], ['2m', '5m', '3s', '4s', '8s']);
      // 4m 버림(쯔모기리): 33m 789m 345p 33s 5s 88s → 1샹텐, 3m · 3s · 4s · 8s 4종 10장.
      expect(actual['shanten'], 1);
      expect(actual['total'], 10);
      for (final (m, o) in [(actual, tr.actual!), (best, tr.best!)]) {
        expect(m['shanten'], o.shanten);
        expect(m['total'], o.ukeire.total);
        expect(m['kinds'], o.ukeire.liveKinds);
        final tiles = (m['tiles'] as List).cast<Map<String, dynamic>>();
        expect(m['total'], tiles.fold<int>(0, (s, u) => s + (u['left'] as int)));
        expect(m['kinds'], tiles.where((u) => (u['left'] as int) > 0).length);
        expect([for (final u in tiles) u['tile']], [for (final u in o.ukeire.tiles) Tiles.toCode(u.tile)]);
      }
      expect(x['rank'], tr.rank);
      expect(x['shanten_loss'], 0);
      expect(x['shanten_loss'], tr.shantenLoss);
      expect(x['ukeire_loss'], 5);
      expect(x['ukeire_loss'], tr.ukeireLoss);

      final top = (x['top'] as List).cast<Map<String, dynamic>>();
      expect(top.length, 3);
      expect(top.first['discard'], best['discard']);
      expect(top.first.containsKey('tiles'), isFalse);

      // only_best · only_actual 을 tiles 로 다시 계산.
      Set<String> live(Map<String, dynamic> m) => {
            for (final u in (m['tiles'] as List).cast<Map<String, dynamic>>())
              if ((u['left'] as int) > 0) u['tile'] as String,
          };
      List<String> minus(Set<String> xs, Set<String> ys) =>
          [...xs.difference(ys)]..sort((u, v) => Tiles.parse(u) - Tiles.parse(v));
      expect(x['only_best'], minus(live(best), live(actual)));
      expect(x['only_actual'], minus(live(actual), live(best)));
      expect(x['only_best'], ['2m', '5m']);

      // 모양: 4m 은 34m 양면(5m · 6m 없어 순자 아님, 2m 없어 간짱 아님). 3m 은 33m 또이쯔 · 34m 양면.
      final shape = x['shape'] as Map<String, dynamic>;
      expect(shape['discard'], [b('ryanmen', '34m')]);
      expect(shape['best'], [b('pair', '33m'), b('ryanmen', '34m')]);

      // 뽑기 전 13장 33m 789m 345p 33s 5s 88s 는 1샹텐 — 789m · 345p 두 묶음 + 또이쯔 셋(하나는 머리) · 5s 한 장.
      // 4m 을 뽑아 34m 양면이 생겨도 덩어리 수가 이미 차 있어 1샹텐 그대로.
      expect(x['shanten_prev'], 1);
      expect(x['shanten_before'], 1);
      final keys = x.keys.toList();
      expect(keys.indexOf('shanten_prev') + 1, keys.indexOf('shanten_before'));
      expect(shape.keys, ['drawn', 'discard', 'best']);
      expect(shape['drawn'], [b('ryanmen', '34m')]);
      expect(shape['drawn'], shapeOf(tr.before!, t('4m')));

      expect(x['riichi_winds'], isEmpty);
      expect(x['genbutsu'], isNull);
      expect(x['safe_tiles'], isEmpty);

      final game = f['game'] as Map<String, dynamic>;
      expect(game['round'], '남4국');
      // dealer 3, hero 1 → (1 − 3) % 4 = 2 → 서.
      expect(game['hero_wind'], '서');
      expect(game['dora_indicators'], ['3z', '2m']);
      expect(game['efficiency_pct'], r.efficiencyPct);
    });

    test('r11: defense 차례 · riichi_winds · genbutsu · safe_tiles', () {
      final p = load('r11_130921');
      final r = reviewPaifu(p);
      final f = reviewFacts(p, r);
      final turns = (f['turns'] as List).cast<Map<String, dynamic>>();
      final defense = turns.where((x) => x['status'] == 'defense').toList();
      expect([for (final x in defense) x['turn']], containsAll([8, 9]));
      for (final x in turns) {
        final tr = r.turns.firstWhere((y) => y.turn == x['turn']);
        expect(x['riichi_winds'], [for (final s in tr.riichiSeats) ['동', '남', '서', '북'][p.windOf(s)]]);
        expect(x['genbutsu'], tr.genbutsu);
        expect(x['safe_tiles'], [for (final k in tr.safeTiles) Tiles.toCode(k)]);
      }
      // 자리 2 가 리치(dealer 0 → 서).
      expect(defense.first['riichi_winds'], ['서']);
      expect(defense.first['grade'], isNull);
    });

    test('r17: 2번째 9p 가 해설할 차례', () {
      final p = load('r17_140450');
      final f = reviewFacts(p, reviewPaifu(p));
      final turns = (f['turns'] as List).cast<Map<String, dynamic>>();
      final x = turns.firstWhere((y) => y['turn'] == 2);
      expect(x['discard'], '9p');
      expect(x['grade'], 'inaccuracy');
      // 손에 적5삭(0s)이 있지만 5s 로 적는다.
      expect(x['hand'], contains('5s'));
    });

    test('r20: hero 손패 없음 — turns 빈 목록, 숫자 칸 null', () {
      // 11-20: r13 · r14 · r18 에 손패를 넣어 손패 없는 판은 r20(3반장)뿐.
      final p = load('r20_143236');
      final r = reviewPaifu(p);
      final f = reviewFacts(p, r);
      expect(f['turns'], isEmpty);
      final timeline = (f['timeline'] as List).cast<Map<String, dynamic>>();
      final heroDiscards = p.events.where((e) => e.seat == p.hero && e.type == PaifuEventType.discard).length;
      expect(timeline.length, heroDiscards);
      for (final x in timeline) {
        expect(x['shanten_after'], isNull);
        expect(x['total'], isNull);
        expect(x['grade'], isNull);
      }
      expect((f['game'] as Map)['efficiency_pct'], isNull);
    });

    test('A-8 shanten_prev: r19 6번째 · r17 2번째 · r11 네 차례 — before − drawn 으로 다시 셈', () {
      final cases = {
        'r19_142013': [6],
        'r17_140450': [2],
        'r11_130921': [3, 4, 8, 9],
      };
      for (final MapEntry(key: id, value: want) in cases.entries) {
        final p = load(id);
        final r = reviewPaifu(p);
        final turns = (reviewFacts(p, r)['turns'] as List).cast<Map<String, dynamic>>();
        if (id == 'r11_130921') expect([for (final x in turns) x['turn']], want);
        for (final n in want) {
          final x = turns.firstWhere((y) => y['turn'] == n);
          final tr = r.turns.firstWhere((y) => y.turn == n);
          final drawn = tr.drawn!.tile;
          final prev = [...tr.before!];
          expect(prev[drawn], greaterThan(0), reason: '$id $n번째');
          prev[drawn]--;
          expect(prev.fold<int>(0, (s, v) => s + v), 13 - 3 * tr.melds, reason: '$id $n번째');
          final sp = x['shanten_prev'] as int;
          final sb = x['shanten_before'] as int;
          expect(sp, shanten(prev, melds: tr.melds), reason: '$id $n번째');
          expect(sb, lessThanOrEqualTo(sp), reason: '$id $n번째');
          expect(sp - sb, anyOf(0, 1), reason: '$id $n번째');
          expect((x['shape'] as Map)['drawn'], shapeOf(tr.before!, drawn), reason: '$id $n번째');
          expect((x['shape'] as Map)['drawn'], isNotEmpty, reason: '$id $n번째');
        }
      }
    });

    test('A-8: 퐁 뒤 버림(drawn null) — shanten_prev null · shape.drawn 빈 목록', () {
      // hero 0. 자리 1 이 5m 으로 리치, hero 가 그 5m 을 퐁하고 9p 를 버림 → 다른 자리 리치 중이라 defense.
      final p = Paifu.fromJson({
        'version': 1,
        'id': 'small',
        'round': '동1국',
        'dealer': 0,
        'hero': 0,
        'events': [
          {'type': 'draw', 'seat': 0, 'tile': '1z', 'hand': h('12355m456p789s19p')},
          {'type': 'discard', 'seat': 0, 'tile': '1z', 'tsumogiri': true, 'riichi': false, 'hand': h('12355m456p789s19p')},
          {'type': 'discard', 'seat': 1, 'tile': '5m', 'tsumogiri': false, 'riichi': true},
          {'type': 'call', 'seat': 0, 'kind': 'pon', 'from': 1, 'tiles': h('555m'), 'hand': h('123m456p789s19p')},
          {'type': 'discard', 'seat': 0, 'tile': '9p', 'tsumogiri': false, 'riichi': false, 'hand': h('123m456p789s1p')},
        ],
      });
      final r = reviewPaifu(p);
      final tr = r.turns.last;
      expect(tr.turn, 2);
      expect(tr.drawn, isNull);
      expect(tr.melds, 1);
      expect(tr.status, ReviewStatus.defense);
      final turns = (reviewFacts(p, r)['turns'] as List).cast<Map<String, dynamic>>();
      final x = turns.firstWhere((y) => y['turn'] == 2);
      expect(x['drawn'], isNull);
      expect(x.containsKey('shanten_prev'), isTrue);
      expect(x['shanten_prev'], isNull);
      // 123m 456p 789s + 1p · 9p, 퐁 하나 → 1p 단기 텐파이.
      expect(x['shanten_before'], 0);
      final shape = x['shape'] as Map<String, dynamic>;
      expect(shape.keys, ['drawn', 'discard', 'best']);
      expect(shape['drawn'], isEmpty);
      expect(shape['discard'], [b('isolated', '9p')]);
      expect(jsonDecode(jsonEncode(x)), x);
    });

    for (final id in files) {
      test('$id: JSON 왕복 · 패 표기 · 개인 정보 · 순서 · 개수 칸', () {
        final p = load(id);
        final r = reviewPaifu(p);
        final f = reviewFacts(p, r);
        final text = jsonEncode(f);
        expect(jsonDecode(text), f);

        for (final s in strings(f)) {
          expect(RegExp(r'^0[mps]$').hasMatch(s), isFalse, reason: s);
        }
        for (final s in ['"0m"', '"0p"', '"0s"']) {
          expect(text.contains(s), isFalse);
        }
        for (final s in [...p.names, p.id, p.title, p.note]) {
          if (s.isNotEmpty) expect(text.contains(s), isFalse, reason: s);
        }

        final timeline = (f['timeline'] as List).cast<Map<String, dynamic>>();
        final turns = (f['turns'] as List).cast<Map<String, dynamic>>();
        expect(timeline.length, r.turns.length);
        expect(ascending([for (final x in timeline) x['turn'] as int]), isTrue);
        expect(ascending([for (final x in turns) x['turn'] as int]), isTrue);

        final game = f['game'] as Map<String, dynamic>;
        expect((game['statuses'] as Map).keys, [for (final s in ReviewStatus.values) s.name]);
        expect((game['grades'] as Map).keys, [for (final g in ReviewGrade.values) g.name]);
        expect((game['statuses'] as Map).values.fold<int>(0, (s, v) => s + (v as int)), r.turns.length);
        expect(['동', '남', '서', '북'], contains(game['hero_wind']));

        // turns 는 정의대로 고른 차례 전부.
        final want = [
          for (final tr in r.turns)
            if ({ReviewGrade.inaccuracy, ReviewGrade.mistake, ReviewGrade.blunder}.contains(tr.grade) ||
                {ReviewStatus.defense, ReviewStatus.complete}.contains(tr.status))
              tr.turn,
        ];
        expect([for (final x in turns) x['turn']], want);
        for (final x in turns) {
          final tr = r.turns.firstWhere((y) => y.turn == x['turn']);
          expect((x['hand'] as List).length, 14 - 3 * tr.melds);
          final top = (x['top'] as List).cast<Map<String, dynamic>>();
          expect(top.length, tr.options.length < 3 ? tr.options.length : 3);
          expect(top.first['discard'], (x['best'] as Map)['discard']);
          if ((x['actual'] as Map)['discard'] == (x['best'] as Map)['discard']) {
            expect(x['only_best'], isEmpty);
            expect(x['only_actual'], isEmpty);
          }
        }
      });
    }
  });
}
