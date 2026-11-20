// reviewPaifu 의 mahjong-helper 엔진 칸(mh · mhBest · mhRankOfActual · 위험도) 시험.
// assets/paifu/ 의 손패 있는 판 넷과 손패 없는 판에서 본다. 등급 칸은 test/paifu_review_test.dart 가 본다.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/risk.dart';
import 'package:mahjong_calc/paifu/mh_context.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';

import '../tool/paifu_review_dump.dart' as dump;

Paifu load(String id) =>
    Paifu.fromJson(jsonDecode(File('assets/paifu/$id.json').readAsStringSync(encoding: utf8)) as Map<String, dynamic>);

void main() {
  const withHands = ['r11_130921', 'r12_131655', 'r17_140450', 'r19_142013'];

  for (final id in withHands) {
    group(id, () {
      final p = load(id);
      final r = reviewPaifu(p, withEngine: true);

      test('graded 차례마다 mh 가 채워지고 mhBest 는 그 차례 손패 안의 패', () {
        final graded = r.turns.where((t) => t.status == ReviewStatus.graded).toList();
        expect(graded, isNotEmpty);
        for (final t in graded) {
          expect(t.mh, isNotNull, reason: '${t.turn}번째 버림');
          expect(t.mh, isNotEmpty);
          final best = t.mhBest!;
          expect(t.before![best], greaterThan(0), reason: '${t.turn}번째 버림 mhBest');
          // 후보는 손패 종류마다 하나씩.
          final kinds = {for (var k = 0; k < 34; k++) if (t.before![k] > 0) k};
          expect({for (final d in t.mh!) d.tile}, kinds);
          expect(t.mhRankOfActual, inInclusiveRange(1, t.mh!.length));
          expect(t.mhActual?.tile, t.discard.tile);
          expect(t.mhRecommendBackward, isNotNull);
          // 최선을 버렸으면 1위.
          if (t.discard.tile == best) expect(t.mhRankOfActual, 1);
        }
      });

      test('손패를 아는 차례(graded · defense · forced · complete)는 모두 mh 가 있음', () {
        for (final t in r.turns) {
          final known = const [ReviewStatus.graded, ReviewStatus.defense, ReviewStatus.forced, ReviewStatus.complete]
              .contains(t.status);
          if (known) {
            expect(t.mh, isNotNull, reason: '${t.turn}번째 버림 ${t.status}');
          } else {
            expect(t.mh, isNull);
          }
        }
      });

      test('리치 · 울기 상대가 있는 차례에 riskOfActual 은 0~100, 손패 위험표도 0~100', () {
        // r17 · r19 는 리치가 hero 뿐이라 남의 리치가 없다 — 울기 위협(텐파이율 > 15%) 차례도 함께 본다.
        final threatened = r.turns.where((t) => t.riichiSeats.isNotEmpty || t.riskSeats.isNotEmpty).toList();
        expect(threatened, isNotEmpty);
        for (final t in threatened) {
          expect(t.riskSeats, containsAll(t.riichiSeats), reason: '${t.turn}번째 버림: 리치 자리는 위협 자리');
          expect(t.riskOfActual, isNotNull);
          expect(t.riskOfActual, inInclusiveRange(0, 100));
          if (t.before != null) {
            expect(t.minRiskTile, isNotNull);
            expect(t.before![t.minRiskTile!], greaterThan(0));
            for (final v in t.riskByKind!.values) {
              expect(v, inInclusiveRange(0, 100));
            }
            expect(t.riskByKind![t.minRiskTile!], t.riskByKind!.values.reduce((a, b) => a < b ? a : b));
          }
          // 리치 자리의 현물을 버렸으면 그 자리 위험은 0.
          if (t.genbutsu == true) {
            for (final s in t.riichiSeats) {
              expect(t.riskTable!.bySeat[s]!.risk34[t.discard.tile], 0);
            }
          }
        }
      });

      test('위협이 없으면 위험 칸은 비어 있음', () {
        for (final t in r.turns.where((t) => t.riskSeats.isEmpty)) {
          expect(t.riskOfActual, isNull);
          expect(t.minRiskTile, isNull);
          expect(t.riskTable, isNull);
        }
      });

      test('덤프 도구가 차례마다 한 줄', () {
        final d = dump.dumpPaifu(p);
        final turns = d['turns'] as List;
        expect(turns.length, r.turns.length);
        for (final row in turns.cast<Map<String, Object?>>()) {
          for (final k in ['turn', 'eventIndex', 'discard', 'drawn', 'status', 'grade', 'shantenBefore', 'ourBest',
            'ourRank', 'mhBest', 'mhRank', 'mhTop5', 'recommendBackward', 'riichiDeclared', 'riskOfActual',
            'minRiskTile']) {
            expect(row.containsKey(k), isTrue, reason: k);
          }
          final top = row['mhTop5'] as List?;
          if (top != null) {
            expect(top.length, lessThanOrEqualTo(5));
            expect((top.first as Map)['tile'], row['mhBest']);
          }
        }
        // JSON 으로 바로 쓸 수 있어야 한다(NaN 없음).
        expect(() => jsonEncode(d), returnsNormally);
      });
    });
  }

  test('손패 없는 판(r20): 예외 없이 mh 는 비고, 리치 상대가 있으면 위험은 나옴', () {
    final p = load('r20_143236');
    expect(p.hasHeroHands, isFalse);
    final r = reviewPaifu(p, withEngine: true);
    expect(r.turns, isNotEmpty);
    for (final t in r.turns) {
      expect(t.status, ReviewStatus.unknownHand);
      expect(t.mh, isNull);
      expect(t.mhBest, isNull);
      expect(t.minRiskTile, isNull);
      if (t.riskOfActual != null) expect(t.riskOfActual, inInclusiveRange(0, 100));
    }
    expect(() => jsonEncode(dump.dumpPaifu(p)), returnsNormally);
  });

  test('assets/paifu 의 모든 판에서 예외 없음', () {
    for (final f in Directory('assets/paifu').listSync().whereType<File>().where((f) => f.path.endsWith('.json'))) {
      final p = Paifu.fromJson(jsonDecode(f.readAsStringSync(encoding: utf8)) as Map<String, dynamic>);
      expect(() => reviewPaifu(p, withEngine: true), returnsNormally, reason: f.path);
    }
  });

  test('riskContextAt: 가깡은 앞선 퐁을 바꾸고 at · upgradedAt 을 단다, 안깡은 from 없는 kan', () {
    Map<String, dynamic> d(int seat, String tile) => {'type': 'discard', 'seat': seat, 'tile': tile, 'riichi': false};
    final p = Paifu.fromJson({
      'version': 1,
      'id': 'k',
      'hero': 0,
      'events': [
        d(0, '1m'),
        d(1, '5z'),
        {'type': 'call', 'seat': 2, 'kind': 'pon', 'from': 1, 'tiles': ['5z', '5z', '5z']},
        d(2, '9m'),
        d(3, '9p'),
        {'type': 'call', 'seat': 2, 'kind': 'kakan', 'from': 2, 'tiles': ['5z']},
        {'type': 'call', 'seat': 3, 'kind': 'kan', 'tiles': ['1s', '1s', '1s', '1s']},
        d(3, '2p'),
      ],
    });
    final ctx = riskContextAt(p, p.events.length);
    expect(ctx.discards.length, 5);
    expect(ctx.melds.length, 2);
    final k = ctx.melds.firstWhere((m) => m.seat == 2);
    expect(k.kind, MeldKind.kakan);
    expect(k.at, 2);
    expect(k.upgradedAt, 4);
    expect(k.tiles, List.filled(4, 31));
    final a = ctx.melds.firstWhere((m) => m.seat == 3);
    expect(a.kind, MeldKind.ankan);
    expect(a.at, 4);
  });

  test('discardContextAt: 적5 는 손패 + 울기에서 세고 장풍은 국 이름에서', () {
    final p = Paifu.fromJson({
      'version': 1,
      'id': 'red',
      'round': '남2국',
      'dealer': 1,
      'hero': 0,
      'dora_indicators': ['4m'],
      'ura_indicators': ['9s'],
      'events': <Map<String, dynamic>>[
        {'type': 'discard', 'seat': 3, 'tile': '0p', 'riichi': false},
        {'type': 'call', 'seat': 0, 'kind': 'chi', 'from': 3, 'tiles': ['0p', '4p', '6p'],
          'hand': ['1m', '2m', '3m', '0m', '6m', '7m', '1s', '2s', '3s', '9s', '9s']},
        {'type': 'discard', 'seat': 0, 'tile': '1s', 'riichi': false,
          'hand': ['1m', '2m', '3m', '0m', '6m', '7m', '2s', '3s', '9s', '9s']},
      ],
    });
    final before = p.events[1].hand!;
    final ctx = discardContextAt(p, 2, handBefore: before, visible34: List.filled(34, 0))!;
    expect(ctx.redFives, [1, 1, 0]);
    expect(ctx.melds.length, 1);
    expect(ctx.roundWind, 28); // 남
    expect(ctx.seatWind, 30); // 자리 0, 친 1 → 북
    expect(ctx.isDealer, isFalse);
    expect(ctx.doraIndicators, [3]); // 뒷도라 빠짐
    expect(reviewPaifu(p).turns.single.mh, isNull); // 기본은 엔진을 끈다
    final r = reviewPaifu(p, withEngine: true);
    expect(r.turns.single.mh, isNotNull);
  });
}
