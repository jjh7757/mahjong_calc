// lib/engine/discard_rank.dart 시험: 원본 EndlessCheng/mahjong-helper(514bb97)와 맞대기.
//
// test/fixtures/mh_cases.json 의 손마다 "go" 칸은 원본 Go 를 실제로 돌린 출력
// (experiments/paifu_review/mhgold/main.go, 5회 실행 · merge.py 로 합침).
// - 순서: 원본이 5회 사이에 순서를 바꾼 쪽(go_order_varies — Sort 의 동률을 Go map
//   순회 순서가 가른다)은 값만 맞대고 순서는 저장된 Dart 순서와 비교한다.
// - known_diffs: 원인을 확인하고 남겨 둔 값 차이. 그 칸만 저장된 Dart 값과 비교.
// 원본 shanten_improve_test.go 의 「최선 버림」 기대값도 함께 본다.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/discard_rank.dart';
import 'package:mahjong_calc/engine/meld.dart';
import 'package:mahjong_calc/engine/tile.dart';

const fields = [
  'shanten', 'waits', 'waits_count', 'avg_improve', 'improve_kinds', 'improve_way',
  'avg_next', 'speed', 'agari_rate', 'dama', 'riichi', 'round_point', 'furiten_rate',
  'is_part_wait', 'dora_count',
];

Object? _f(double v) => v.isFinite ? v : null;

Map<String, Object?> _one(RankedDiscard d) => {
      'tile': d.tile,
      'shanten': d.shanten,
      'waits': {for (final e in d.waits.entries) '${e.key}': e.value},
      'waits_count': d.waitsCount,
      'avg_improve': _f(d.avgImproveWaitsCount),
      'improve_kinds': d.improveKinds,
      'improve_way': d.improveWayCount,
      'avg_next': _f(d.avgNextShantenWaitsCount),
      'speed': _f(d.speedScore),
      'agari_rate': _f(d.agariRate),
      'dama': _f(d.damaPoint),
      'riichi': _f(d.riichiPoint),
      'round_point': _f(d.roundPoint),
      'furiten_rate': d.furitenRate,
      'is_part_wait': d.raw.result13.isPartWait,
      'dora_count': d.raw.result13.doraCount,
    };

Matcher _same(Object? want) {
  if (want is num) return closeTo(want, 1e-6 * (want.abs() > 1 ? want.abs() : 1));
  return equals(want);
}

DiscardContext _ctx(Map<String, Object?> input) {
  List<int> ints(String k) => (input[k] as List).cast<int>();
  return DiscardContext(
    hand34: ints('hand34'),
    melds: [
      for (final m in (input['melds'] as List).cast<Map<String, Object?>>())
        switch (m['type']) {
          'chi' => Meld.chi((m['tiles'] as List).first as int),
          'pon' => Meld.pon((m['tiles'] as List).first as int),
          'ankan' => Meld.closedKan((m['tiles'] as List).first as int),
          _ => Meld.openKan((m['tiles'] as List).first as int),
        }
    ],
    visible34: ints('visible34'),
    doraIndicators: ints('dora_indicators'),
    redFives: ints('red_fives'),
    roundWind: input['round_wind'] as int,
    seatWind: input['self_wind'] as int,
    isDealer: input['is_parent'] as bool,
    selfDiscards: ints('discards'),
  );
}

/// 원본 shanten_improve_test.go 의 「최선 버림」 기대값. 원본 Go 도 틀리는 것은
/// 원본 실제 출력과 맞춘다(fixture 의 note 참고).
const originalBest = {
  // TestBestDiscard
  'best_c3q5': '4m', 'best_c3q5_dora5p': '4m', 'best_c3q4_55z': '7m', 'best_c3q4_44z': '6m',
  'best_c3q8': '4s', 'best_c3q10': '1m', 'best_c3q15': '5s', 'best_c3q17_8m': '7m',
  'best_c3q17_3z': '8m', 'best_c3q18': '7m', 'best_3sh_2p': '8p', 'best_3sh_8p': '2p',
  // 'best_3sh': '2p' — 원본도 2p/8p 동률(실행마다 다름), 이쪽은 2p
  'best_3sh': '2p',
  // TestBest2
  'best2_a': '5z',
  // TestFuritenBestDiscard
  'furiten_c3q6': '5s', 'furiten_9m': '6p',
  // TestQ300(원본이 통과하는 것)
  'q001': '2s', 'q002': '5s', 'q004': '5s', 'q005': '9p', 'q006': '8p', 'q008': '2p',
  'q009': '5m', 'q010': '3p', 'q011': '1m', 'q013': '2p', 'q030': '8p',
};

/// 원본 시험 기대값과 원본 Go 실제 출력이 다른 것(원본도 실패): 원본 실제 출력.
const originalFailsInGo = {
  'best2_b': '5p', // 기대 8p
  'q003': '2s', // 기대 8p 「尚未考虑自摸时的三暗刻」
  'q007': '4m', // 기대 1p
  'q033': '6m', // 기대 3m(「6m 也可以」)
  'q037': '9p', // 기대 1p(「3m 也可以」)
  'q058': '4p', // 기대 8s 「考虑改良的影响」
  // q012: 기대 2s, 원본은 6p 또는 4p(실행마다) — 이쪽 4p
};

void main() {
  final doc = jsonDecode(File('test/fixtures/mh_cases.json').readAsStringSync())
      as Map<String, Object?>;
  final cases = (doc['cases'] as List).cast<Map<String, Object?>>();

  test('대조 손은 20 손 이상, 0~2샹텐·텐파이·울기·도라 포함', () {
    expect(cases.length, greaterThanOrEqualTo(20));
    final shanten = {for (final c in cases) (c['go'] as Map)['shanten']};
    expect(shanten, containsAll([-1, 0, 1, 2, 3]));
    expect(cases.where((c) => ((c['input'] as Map)['melds'] as List).isNotEmpty), isNotEmpty);
    expect(cases.where((c) => ((c['input'] as Map)['dora_tiles'] as List).isNotEmpty), isNotEmpty);
  });

  group('원본 Go 출력과 맞대기', () {
    for (final c in cases) {
      final id = c['id'] as String;
      test(id, () {
        final go = (c['go'] as Map).cast<String, Object?>();
        final dartSaved = (c['dart'] as Map).cast<String, Object?>();
        final varies = (c['go_order_varies'] as Map).cast<String, Object?>();
        final known = [
          for (final k in (c['known_diffs'] as List? ?? const []))
            (k as Map).cast<String, Object?>()
        ];
        final r = analyzeDiscards(_ctx((c['input'] as Map).cast<String, Object?>()));

        expect(r.shanten, go['shanten']);
        expect(r.recommendBackward, go['recommend_backward']);
        expect(r.best, varies['best'] == true ? dartSaved['best'] : go['best'],
            reason: '$id best');

        for (final side in ['forward', 'backward']) {
          final mine = [for (final d in side == 'forward' ? r.forward : r.backward) _one(d)];
          final theirs = (go[side] as List).cast<Map<String, Object?>>();
          final order = [for (final x in mine) x['tile']];
          if (varies[side] == true) {
            // 원본 Sort 의 동률(원본 순서가 실행마다 다름): 값만 원본과, 순서는 저장값과
            expect(order, [for (final x in (dartSaved[side] as List)) (x as Map)['tile']],
                reason: '$id $side 순서(저장값)');
            expect(order.toSet(), {for (final x in theirs) x['tile']});
          } else {
            expect(order, [for (final x in theirs) x['tile']], reason: '$id $side 순서');
          }
          final byTile = {for (final x in theirs) x['tile']: x};
          final savedByTile = {
            for (final x in (dartSaved[side] as List).cast<Map<String, Object?>>()) x['tile']: x
          };
          for (final x in mine) {
            final y = byTile[x['tile']]!;
            for (final f in fields) {
              final isKnown = known.any(
                  (k) => k['side'] == side && k['tile'] == x['tile'] && k['field'] == f);
              final want = isKnown ? savedByTile[x['tile']]![f] : y[f];
              expect(x[f], _same(want),
                  reason: '$id $side ${Tiles.toCode(x['tile'] as int)} $f'
                      '${isKnown ? '(known_diffs: 저장된 Dart 값)' : ''}');
            }
          }
        }
      });
    }
  });

  group('원본 shanten_improve_test.go 최선 버림', () {
    final byId = {for (final c in cases) c['id']: c};
    for (final e in {...originalBest, ...originalFailsInGo}.entries) {
      test('${e.key} → ${e.value}', () {
        final c = byId[e.key]!;
        final r = analyzeDiscards(_ctx((c['input'] as Map).cast<String, Object?>()));
        expect(Tiles.toCode(r.best!), e.value);
      });
    }
  });

  group('API', () {
    test('rankDiscards 는 지키는 버림 다음 물러나는 버림, isBest 는 하나', () {
      final r = rankDiscards(DiscardContext(hand34: toCounts(parseTiles('134m 123567p 12355s').tiles)));
      expect(r.first.isBackward, isFalse);
      expect(r.last.isBackward, isTrue);
      expect(r.where((d) => d.isBest).map((d) => Tiles.toCode(d.tile)), ['4m']);
    });

    test('화료형 14장: 지키는 버림이 없으면 후퇴 1위가 최선', () {
      final r = analyzeDiscards(DiscardContext(hand34: toCounts(parseTiles('123456789m 123p 55s').tiles)));
      expect(r.shanten, -1);
      expect(r.forward, isEmpty);
      expect(r.best, r.backward.first.tile);
      expect(r.backward.first.isBest, isTrue);
    });

    test('손패 칸 수가 34 가 아니면 거부', () {
      expect(() => DiscardContext(hand34: [1, 2, 3]), throwsArgumentError);
    });
  });
}
