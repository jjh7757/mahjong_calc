import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart' show Situation;
import 'package:mahjong_calc/table/auto_record.dart';
import 'package:mahjong_calc/table/hand_rules.dart';
import 'package:mahjong_calc/table/merge.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/table_reading.dart';

/// 규칙 검증기 — Python(`experiments/speed/hand_rules.py test`)과 같은 fixture 를 통과해야 한다.
void main() {
  final fixture = jsonDecode(File('test/fixtures/hand_rules.json').readAsStringSync()) as Map<String, dynamic>;

  group('fixture', () {
    for (final c in (fixture['cases'] as List<dynamic>).cast<Map<String, dynamic>>()) {
      test(c['name'] as String, () {
        final got = checkHandRules(HandRuleInput.fromJson(c['input'] as Map<String, dynamic>));
        expect(jsonDecode(jsonEncode(got.toJson())), c['expect']);
      });
    }
  });

  test('막음 사유 문구', () {
    final r = checkHandRules(const HandRuleInput(
      hand: ['0m', '0m', '6m', '7m', '1p', '2p', '3p', '7s', '8s', '9s', '2z', '2z', '2z'],
      win: '4m',
      melds: [HandRuleMeld('pon', ['1s', '2s', '4s'])],
    ));
    expect(r.blockers, ['적5 2장 이상(0m)', '울기 모양이 아님(1s 2s 4s)']);
  });

  test('autoRecordBlocker 는 규칙 막음을 사유로 낸다', () {
    String? block(List<String> rules) => autoRecordBlocker(
          warnings: const [],
          issues: const [],
          otherWinners: 0,
          isTsumo: true,
          loser: null,
          resultValid: true,
          paoBase: 0,
          gameOver: false,
          ruleBlocks: rules,
        );
    expect(block(const []), isNull);
    expect(block(const ['같은 패 5장 이상(5p)']), '규칙: 같은 패 5장 이상(5p)');
  });

  test('판독 → 검사 입력: 론 패는 강에서 한 장 빼고, 2순위는 손패 순서대로', () {
    final hand = HandReading(tiles: [
      for (final c in ['1m', '2m', '3m', '4p', '5p', '6s', '7s', '8s', '9s', '2z', '2z', '5z', '5z'])
        ReadTile.fromJson({'tile': c, 'conf': 0.9, if (c == '6s') 'alt': '6p', if (c == '6s') 'conf2': 0.08})!,
    ]);
    final merge = TableMerge(
      winner: 0,
      winnerSide: Side.bottom,
      isTsumo: false,
      loser: 1,
      closed: [for (final t in [...hand.tiles, ReadTile.fromCode('5z', 0.9)!]) MergedTile(t.tile, red: t.red)],
      melds: const [],
      meldRed: const [],
      situation: const Situation(isTsumo: false, doraIndicators: [0]),
      hand: null,
      uncertain: const {},
      flags: const [],
    );
    final center = CenterReading(rivers: {
      Side.right: [ReadTile.fromCode('5z', 0.9)!],
      Side.top: [ReadTile.fromCode('9p', 0.9)!],
    });
    final inp = handRuleInputOf(hand: hand, merge: merge, center: center);
    expect(inp.win, '5z');
    expect(inp.river, ['9p']);
    expect(inp.indicators, ['1m']);
    expect(inp.alt[5], '6p');
    final r = checkHandRules(inp);
    expect(r.kind, HandRuleKind.candidate);
    final fixed = applyHandCandidate(hand, r.candidate!);
    expect(fixed.tiles[5].code, '6p');
  });
}
