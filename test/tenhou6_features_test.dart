// tool/tenhou6_features.dart 교차 검증 — 매장 손패 있는 네 판을 toTenhou6(남의 쯔모기리 모름 = tedashi)로 바꿔
// 값 뽑기에 넣고, 같은 판의 reviewPaifu(withEngine: true) 와 차례마다 맞댄다.
// 비교 범위: reviewPaifu 가 값을 낸 차례(status graded · defense · forced). 기대값은 reviewPaifu 쪽이다.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/tile.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';
import 'package:mahjong_calc/paifu/tenhou6_export.dart';

import '../tool/tenhou6_features.dart' as feat;

Paifu _load(String id) =>
    Paifu.fromJson(jsonDecode(File('assets/paifu/$id.json').readAsStringSync(encoding: utf8)) as Map<String, dynamic>);

bool _numEq(double? a, Object? b) {
  final x = (a == null || a.isNaN || !a.isFinite) ? null : a;
  final y = b == null ? null : (b as num).toDouble();
  if (x == null || y == null) return x == null && y == null;
  return (x - y).abs() < 1e-9;
}

void main() {
  const games = ['r11_130921', 'r12_131655', 'r17_140450', 'r19_142013'];
  const compared = [ReviewStatus.graded, ReviewStatus.defense, ReviewStatus.forced];

  for (final id in games) {
    test('$id: 값 뽑기 = reviewPaifu(withEngine) 차례마다', () {
      final p = _load(id);
      final ex = toTenhou6(p);
      final log = (ex.json['log'] as List).first as List;
      final rows = feat.kyokuSeatRows(log, ex.heroIndex, game: id, kyoku: 0, engineAfterRiichi: true);
      final review = reviewPaifu(p, withEngine: true);
      final off = (ex.heroIndex - p.hero) % 4; // 우리 자리 s → 천봉 자리 (s + off) % 4
      final mism = <String>[];
      var n = 0;
      if (rows.length != review.turns.length) {
        mism.add('hero 버림 수: 값 뽑기 ${rows.length} ≠ reviewPaifu ${review.turns.length}');
      }
      for (final t in review.turns) {
        if (!compared.contains(t.status)) continue;
        final k = t.turn - 1;
        if (k >= rows.length) {
          mism.add('차례 ${t.turn}: 값 뽑기 줄 없음');
          continue;
        }
        n++;
        final r = rows[k];
        void diff(String field, Object? want, Object? got) => mism.add('차례 ${t.turn}(${t.status.name}) $field: 기대 $want / 값 뽑기 $got');
        String? code(int? x) => x == null ? null : Tiles.toCode(x);
        if (Tiles.toCode(t.discard.tile) != r['actual']) diff('버린 패', Tiles.toCode(t.discard.tile), r['actual']);
        if (t.shantenBefore != r['shantenBefore']) diff('shantenBefore', t.shantenBefore, r['shantenBefore']);
        final b0 = (r['b0Order'] as List?)?.first;
        if (code(t.best?.tile) != b0) diff('B0 최선', code(t.best?.tile), b0);
        if (code(t.mhBest) != r['mhBest']) diff('mhBest', code(t.mhBest), r['mhBest']);
        if (t.mhRecommendBackward != r['recommendBackward']) diff('recommendBackward', t.mhRecommendBackward, r['recommendBackward']);
        final cands = (r['candidates'] as List? ?? const []).cast<Map<String, Object?>>();
        final ca = cands.where((c) => c['tile'] == Tiles.toCode(t.discard.tile)).firstOrNull;
        final a = t.mhActual;
        if (a == null || ca == null) {
          if (a != null || ca != null) diff('실제 버림 mh 항목', a == null ? '없음' : '있음', ca == null ? '없음' : '있음');
        } else {
          if (a.waitsCount != ca['waits']) diff('실제 waits', a.waitsCount, ca['waits']);
          if (!_numEq(a.speedScore, ca['speed'])) diff('실제 speed', a.speedScore, ca['speed']);
          if (!_numEq(a.avgImproveWaitsCount, ca['improve'])) diff('실제 improve', a.avgImproveWaitsCount, ca['improve']);
          if (!_numEq(a.agariRate, ca['agariRate'])) diff('실제 agariRate', a.agariRate, ca['agariRate']);
          if (!_numEq(a.roundPoint, ca['roundPoint'])) diff('실제 roundPoint', a.roundPoint, ca['roundPoint']);
        }
        if (!_numEq(t.riskOfActual, r['riskOfActual'])) diff('riskOfActual', t.riskOfActual, r['riskOfActual']);
        final wantSeats = [for (final s in t.riskSeats) (s + off) % 4]..sort();
        final gotSeats = (r['riskSeats'] as List? ?? const []).cast<int>();
        if (wantSeats.join(',') != gotSeats.join(',')) diff('riskSeats(천봉 자리)', wantSeats, gotSeats);
      }
      final report = '$id: 비교 $n차례 · 어긋남 ${mism.length}건${mism.isEmpty ? '' : '\n  ${mism.join('\n  ')}'}';
      // ignore: avoid_print
      print(report);
      expect(n, greaterThan(0));
      expect(mism, isEmpty, reason: report);
    });
  }
}
