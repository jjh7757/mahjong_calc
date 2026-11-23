// 엔진 "방총 위험 %" 화면 보정(lib/engine/risk_calibration.dart, 설계서 docs/risk_calibration_design_1123.md 6절).
// 점 목록이 table.json 과 같은지는 `python -X utf8 tool/gen_risk_calibration.py --check` 가 본다(JSON 은 experiments/ 라
// 커밋되지 않음). 여기서는 Dart 상수만 쓴다. 기대값 중 np.interp 값은 table.json 으로 Python 에서 따로 낸 것이다.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/risk_calibration.dart';
import 'package:mahjong_calc/engine/tile.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';
import 'package:mahjong_calc/ui/paifu/review_view.dart';

Paifu _load(String id) =>
    Paifu.fromJson(jsonDecode(File('assets/paifu/$id.json').readAsStringSync(encoding: utf8)) as Map<String, dynamic>);

void main() {
  const kinds = [RiskThreat.riichi, RiskThreat.callOnly];

  group('보정표 상수', () {
    test('점 개수(table.json 2026-11-23: R 13 · C 17), x 는 엄격히 증가 · y 는 줄지 않음, 범위 0 ~ 100', () {
      expect(riskCalPointsRiichi, hasLength(13));
      expect(riskCalPointsCallOnly, hasLength(17));
      for (final k in kinds) {
        final pts = riskCalPoints(k);
        for (var i = 1; i < pts.length; i++) {
          expect(pts[i].$1, greaterThan(pts[i - 1].$1), reason: '$k x[$i]');
          expect(pts[i].$2, greaterThanOrEqualTo(pts[i - 1].$2), reason: '$k y[$i]');
        }
        for (final (x, y) in pts) {
          expect(x, inInclusiveRange(0, 100));
          expect(y, inInclusiveRange(0, 100));
        }
      }
    });

    test('양 끝 점(생성 스크립트가 table.json 에서 그대로 옮긴 값)', () {
      expect(riskCalPointsRiichi.first, (0.009772670760293548, 0.19212295869356388));
      expect(riskCalPointsRiichi.last, (25.185268684628266, 17.253521126760564));
      expect(riskCalPointsCallOnly.first, (0.02390728458973832, 0.14820303816228234));
      expect(riskCalPointsCallOnly.last, (18.969695537629487, 12.76595744680851));
    });
  });

  group('calibrateRisk', () {
    test('점 위에서는 그 점의 y 그대로', () {
      for (final k in kinds) {
        for (final (x, y) in riskCalPoints(k)) {
          expect(calibrateRisk(x, k), y, reason: '$k x=$x');
        }
      }
    });

    test('점 사이는 직선: 두 점의 중간은 y 의 중간', () {
      for (final k in kinds) {
        final pts = riskCalPoints(k);
        for (var i = 0; i + 1 < pts.length; i++) {
          final (x0, y0) = pts[i];
          final (x1, y1) = pts[i + 1];
          expect(calibrateRisk((x0 + x1) / 2, k), closeTo((y0 + y1) / 2, 1e-12), reason: '$k 구간 $i');
          final q = x0 + (x1 - x0) / 4;
          expect(calibrateRisk(q, k), closeTo(y0 + (y1 - y0) / 4, 1e-12), reason: '$k 구간 $i 1/4');
        }
      }
    });

    test('첫 점 아래는 첫 점 값, 마지막 점 위는 마지막 점 값', () {
      for (final k in kinds) {
        final pts = riskCalPoints(k);
        for (final x in [-5.0, 0.0, pts.first.$1 / 2]) {
          expect(calibrateRisk(x, k), pts.first.$2, reason: '$k x=$x');
        }
        for (final x in [pts.last.$1 + 1e-9, 30.0, 58.68, 100.0, 1000.0]) {
          expect(calibrateRisk(x, k), pts.last.$2, reason: '$k x=$x');
        }
      }
    });

    test('np.interp 와 같은 값(table.json 으로 Python 에서 낸 값)', () {
      final want = {
        RiskThreat.riichi: {
          -1.0: 0.19212295869356388,
          0.0: 0.19212295869356388,
          1.0: 0.9485486615569164,
          2.5: 1.9053538729826038,
          5.0: 3.2775689236803722,
          10.0: 7.425059871702679,
          20.0: 13.240733610114383,
          50.0: 17.253521126760564,
          100.0: 17.253521126760564,
        },
        RiskThreat.callOnly: {
          -1.0: 0.14820303816228234,
          0.0: 0.14820303816228234,
          1.0: 0.8218892363475322,
          2.5: 2.6126815846312597,
          5.0: 4.649539350607484,
          10.0: 6.442444224244947,
          20.0: 12.76595744680851,
          50.0: 12.76595744680851,
          100.0: 12.76595744680851,
        },
      };
      want.forEach((k, m) => m.forEach((x, y) => expect(calibrateRisk(x, k), closeTo(y, 1e-12), reason: '$k x=$x')));
    });

    test('0 ~ 100 을 0.001 간격으로 촘촘히: 줄지 않음 · 마지막 점 위로 안 올라감', () {
      for (final k in kinds) {
        var prev = double.negativeInfinity;
        final top = riskCalPoints(k).last.$2;
        for (var i = 0; i <= 100000; i++) {
          final v = calibrateRisk(i / 1000, k);
          expect(v >= prev, isTrue, reason: '$k x=${i / 1000}: $v < $prev');
          expect(v <= top, isTrue);
          prev = v;
        }
      }
    });

    test('R · C 는 다른 표를 씀', () {
      expect(riskCalPoints(RiskThreat.riichi), same(riskCalPointsRiichi));
      expect(riskCalPoints(RiskThreat.callOnly), same(riskCalPointsCallOnly));
      expect(calibrateRisk(10, RiskThreat.riichi), isNot(calibrateRisk(10, RiskThreat.callOnly)));
      expect(calibrateRisk(10, RiskThreat.riichi), closeTo(7.425059871702679, 1e-12));
      expect(calibrateRisk(10, RiskThreat.callOnly), closeTo(6.442444224244947, 1e-12));
    });

    test('NaN · 무한대는 그대로', () {
      for (final k in kinds) {
        expect(calibrateRisk(double.nan, k).isNaN, isTrue);
        expect(calibrateRisk(double.infinity, k), double.infinity);
        expect(calibrateRisk(double.negativeInfinity, k), double.negativeInfinity);
      }
    });
  });

  group('예시 패보 화면 문구(보정값 · 엔진 값은 그대로)', () {
    late Map<String, PaifuReview> rv;
    setUpAll(() => rv = {for (final id in ['r11_130921', 'r18_141259', 'r19_142013']) id: reviewPaifu(_load(id), withEngine: true)});
    TurnReview at(String id, int step) => rv[id]!.turns.firstWhere((t) => t.eventIndex + 1 == step);

    test('r11 걸음 46(리치 위협 R, 두 자리): 엔진 15.1% → 보이는 값 약 9.6%', () {
      final t = at('r11_130921', 46);
      expect(t.riichiSeats, isNotEmpty);
      expect(t.riskThreat, RiskThreat.riichi);
      expect(t.riskOfActual, closeTo(15.0882, 1e-4)); // 엔진 원래 값은 그대로
      expect(calibrateRisk(t.riskOfActual!, RiskThreat.riichi), closeTo(9.6, 0.05));
      expect(engineRiskLines(t)[0], '위협 자리: 2번 자리, 3번 자리 · 이 패 방총 위험 약 9.6%');
      expect(engineFoldLines(t)[1], '이 패 방총 위험: 약 9.6% (위협: 2번 자리, 3번 자리)');
    });

    test('r19 걸음 29(울기 위협만 C): 엔진 1.8% → 보이는 값 약 2.1%(C 표는 낮은 쪽에서 엔진보다 조금 높음)', () {
      final t = at('r19_142013', 29);
      expect(t.riichiSeats, isEmpty);
      expect(t.riskThreat, RiskThreat.callOnly);
      expect(t.riskOfActual, closeTo(1.8466, 1e-4));
      expect(engineRiskLines(t)[0], '위협 자리: 1번 자리 · 이 패 방총 위험 약 2.1%');
      // 리치 표였다면 다른 값(1.3%) — 위협 종류로 표를 고른다.
      expect(calibrateRisk(t.riskOfActual!, RiskThreat.riichi).toStringAsFixed(1), '1.3');
    });

    test('r18 걸음 25: 모두에게 안전패(safeForAll34)는 숫자 대신 "안전"', () {
      final t = at('r18_141259', 25);
      expect(t.riskTable!.safeForAll34[t.discard.tile], isTrue);
      expect(t.riskSafeForAll(t.discard.tile), isTrue);
      expect(t.riskOfActual, 0);
      expect(engineRiskLines(t), ['위협 자리: 1번 자리 · 이 패는 모두에게 안전', '가장 안전: 2통 (모두에게 안전) — 실제 버림']);
      expect(engineFoldLines(t)[1], '이 패 방총 위험: 안전 (위협: 1번 자리)');
      expect(shownRiskText(t, t.discard.tile, 0), '안전');
      expect(shownRisk(t, t.discard.tile, 0), 0);
    });

    test('엔진 0 이지만 모두에게 안전패가 아니면 첫 점 값(R 0.2%) — "안전" 은 safeForAll34 만', () {
      final t = at('r11_130921', 46);
      final zero = t.riskByKind!.entries.where((e) => e.value == 0 && !t.riskSafeForAll(e.key)).firstOrNull;
      if (zero != null) expect(shownRiskText(t, zero.key, 0), '0.2%');
      expect(shownRiskText(t, t.discard.tile, 0), '0.2%'); // 버린 패(안전패 아님)에 0 을 넣어 봄
    });

    test('위협 없는 차례: riskThreat 는 null, 안전패 판정은 false', () {
      final t = at('r19_142013', 9);
      expect(t.riskSeats, isEmpty);
      expect(t.riskThreat, isNull);
      expect(t.riskSafeForAll(t.discard.tile), isFalse);
    });

    test('가장 안전 패는 원래 값으로 고르고(보정은 단조), 보이는 값은 손패 중 가장 작음', () {
      for (final r in rv.values) {
        for (final t in r.turns) {
          final m = t.minRiskTile;
          final byKind = t.riskByKind;
          if (m == null || byKind == null) continue;
          final k = t.riskThreat!;
          final shown = shownRisk(t, m, byKind[m]!);
          for (final e in byKind.entries) {
            expect(e.value, greaterThanOrEqualTo(byKind[m]!));
            if (!t.riskSafeForAll(m)) expect(calibrateRisk(e.value, k), greaterThanOrEqualTo(shown));
          }
        }
      }
    });
  });

  group('화면의 "가장 안전" 패(shownSafestTile — 동률 묶음 안 모두에게 안전패 먼저)', () {
    late Map<String, PaifuReview> all;
    setUpAll(() {
      final files = [
        ...Directory('assets/paifu').listSync(),
        ...Directory('assets/paifu_h3').listSync(),
      ].whereType<File>().where((f) => f.path.endsWith('.json')).toList()
        ..sort((a, b) => a.path.compareTo(b.path));
      all = {
        for (final f in files)
          f.uri.pathSegments.last.replaceAll('.json', ''): reviewPaifu(
              Paifu.fromJson(jsonDecode(f.readAsStringSync(encoding: utf8)) as Map<String, dynamic>),
              withEngine: true),
      };
    });
    TurnReview at(String id, int step) => all[id]!.turns.firstWhere((t) => t.eventIndex + 1 == step);

    test('예시 22판', () => expect(all, hasLength(22)));

    // 11-23 보고의 8차례 중 넷: 원래 고름(minRiskTile, 번호 작은 패)은 엔진 0 이지만 모두에게 안전패가 아니어서
    // "0.2%" 로 보였고, 같은 엔진 0 인 안전패가 손에 있었다.
    for (final (id, step) in [('r16_135321', 45), ('r16_135321', 60), ('r16_135321', 85), ('r17_140450', 59)]) {
      test('$id 걸음 $step: 가장 안전은 안전패로 보이고 minRiskTile 은 그대로', () {
        final t = at(id, step);
        final m = t.minRiskTile!;
        expect(t.riskSafeForAll(m), isFalse); // 원래 고름은 바꾸지 않음
        final s = shownSafestTile(t)!;
        expect(s, isNot(m));
        expect(t.riskSafeForAll(s), isTrue);
        expect(t.riskByKind![s], t.riskByKind![m]);
        expect(engineRiskLines(t)[1], startsWith('가장 안전: ${Tiles.name(s)} (모두에게 안전)'));
        expect(engineFoldLines(t).last, startsWith('가장 안전한 패: ${Tiles.name(s)}'));
      });
    }

    test('22판 위협 차례 전부: 보여 준 가장 안전 패의 보정값(안전 = 0) ≤ 손 안 다른 패의 보정값, 원래 값도 최소', () {
      var n = 0, fixed = 0, toActual = 0;
      for (final MapEntry(key: id, value: r) in all.entries) {
        for (final t in r.turns) {
          final byKind = t.riskByKind;
          final s = shownSafestTile(t);
          if (byKind == null || s == null) continue;
          n++;
          if (s != t.minRiskTile) {
            if (!t.riskSafeForAll(t.minRiskTile!)) fixed++;
            if (t.riskSafeForAll(t.minRiskTile!) && s == t.discard.tile) toActual++;
          }
          final v = shownRisk(t, s, byKind[s]!);
          expect(byKind[s], byKind[t.minRiskTile]!, reason: '$id 걸음 ${t.eventIndex + 1}: 원래 값이 최소가 아님');
          for (final e in byKind.entries) {
            expect(v, lessThanOrEqualTo(shownRisk(t, e.key, e.value)),
                reason: '$id 걸음 ${t.eventIndex + 1}: ${Tiles.name(s)} $v > ${Tiles.name(e.key)}');
          }
        }
      }
      expect(n, greaterThan(50));
      // ignore: avoid_print
      print('위협 차례 $n · 안전패로 바꿔 보인 차례 $fixed · 안전패끼리 동률이라 실제 버림을 보인 차례 $toActual');
      expect(fixed, 8); // 11-23 에 센 동률 모순 8차례(r16 셋 · r17 하나 · h3 넷)
    });
  });
}
