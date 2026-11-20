// lib/engine/risk.dart (EndlessCheng/mahjong-helper 위험도 옮김) 시험.
//
// 1) 원본 util/risk_base_test.go · util/risk_wall_test.go 의 기대값.
// 2) 손으로 셀 수 있는 장면(셈은 주석).
// 3) test/fixtures/mh_risk_cases.json: 장면마다 원본 Go(go) 출력과 맞대고, 지난 Dart 출력(dart)과도 맞댄다.
//    `MH_RISK_WRITE=1 flutter test test/risk_test.dart` 로 dart 출력을 다시 쓴다(go 는 experiments/paifu_review/mhgold_risk/ 의 main.go 가 원본 Go 로 씀).
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/risk.dart';
import 'package:mahjong_calc/engine/risk_data.dart';
import 'package:mahjong_calc/engine/tile.dart';

List<int> t(String s) => s.trim().isEmpty ? [] : parseTiles(s).tiles;

/// 원본 `InitLeftTiles34WithTiles34(MustStrToTiles34(s))`.
List<int> leftWith(String s) {
  final c = toCounts(t(s));
  return [for (var i = 0; i < 34; i++) 4 - c[i]];
}

List<bool> safeOf(String s) {
  final out = List<bool>.filled(34, false);
  for (final x in t(s)) {
    out[x] = true;
  }
  return out;
}

Set<int> tilesOfWall(List<WallSafeTile> l) => {for (final w in l) w.tile34};

MeldKind kindOf(String s) => MeldKind.values.byName(s);

RiskContext contextOf(Map<String, dynamic> c) {
  final discards = [
    for (final d in c['discards'] as List)
      RiskDiscard(d[0] as int, Tiles.parse(d[1] as String), tsumogiri: d[2] as bool?, riichi: d[3] as bool),
  ];
  final melds = [
    for (final m in c['melds'] as List)
      RiskMeld(
        m['seat'] as int,
        kindOf(m['kind'] as String),
        t(m['tiles'] as String),
        at: m['at'] as int,
        upgradedAt: m['upgraded_at'] as int?,
        red: m['red'] as bool? ?? false,
      ),
  ];
  return RiskContext(
    selfSeat: c['self'] as int,
    dealer: c['dealer'] as int,
    roundWindTile: Tiles.parse(c['round_wind'] as String),
    discards: discards,
    melds: melds,
    doraIndicators: t(c['dora_indicators'] as String),
    hand34: toCounts(t(c['hand'] as String)),
    ippatsu: (c['ippatsu'] as List?)?.cast<bool?>(),
    unknownTsumogiri: UnknownTsumogiri.values.byName(c['unknown_tsumogiri'] as String),
  );
}

double r6(double x) => (x * 1e6).round() / 1e6;

/// Go 하네스와 같은 꼴의 출력.
Map<String, dynamic> outputOf(RiskTable r) => {
      'seats': {
        for (final o in r.opponents)
          '${o.seat}': {
            'tenpai': r6(o.tenpaiRate),
            'turns': o.turns,
            'ron_point': r6(o.ronPoint),
            'riichi': o.riichi,
            'ippatsu': o.ippatsu,
            'safe': [
              for (var i = 0; i < 34; i++)
                if (o.safe34[i]) i,
            ],
            'risk34': [for (final x in o.risk34) r6(x)],
            'left_no_suji': o.leftNoSujiTiles,
          },
      },
      'mixed34': [for (final x in r.mixed34) r6(x)],
      'left34': r.left34,
    };

/// 두 출력의 차이(없으면 빈 목록). 숫자는 1e-6 안이면 같다.
List<String> diff(Object? a, Object? b, [String path = '']) {
  if (a is num && b is num) return (a - b).abs() <= 1e-6 ? [] : ['$path: $a != $b'];
  if (a is List && b is List) {
    if (a.length != b.length) return ['$path: 길이 ${a.length} != ${b.length}'];
    return [for (var i = 0; i < a.length; i++) ...diff(a[i], b[i], '$path[$i]')];
  }
  if (a is Map && b is Map) {
    final keys = {...a.keys, ...b.keys};
    return [for (final k in keys) ...diff(a[k], b[k], '$path.$k')];
  }
  return a == b ? [] : ['$path: $a != $b'];
}

void main() {
  group('원본 risk_wall_test.go', () {
    test('TestCalcDNCSafeTiles', () {
      expect(tilesOfWall(calcDNCSafeTiles(leftWith('8888s'))), t('9s').toSet());
      expect(tilesOfWall(calcDNCSafeTiles(leftWith('33336666s'))), t('1245s').toSet());
      expect(tilesOfWall(calcDNCSafeTiles(leftWith('33335555s'))), t('124s').toSet());
      expect(tilesOfWall(calcDNCSafeTiles(leftWith('33337777s'))), t('1289s').toSet());
      expect(tilesOfWall(calcDNCSafeTiles(leftWith('333355557777s'))), t('124689s').toSet());
    });

    test('TestCalcWallTiles 중 노찬스 부분(원찬스는 안 옮김)', () {
      // 원본 기대값 "189s"(NC+OC) 중 NC: 2222s 벽 → 1s, 888s 는 3 장이라 벽 아님 → 9s 는 OC 쪽.
      expect(tilesOfWall(calcNCSafeTiles(leftWith('2222777888s'))), t('1s').toSet());
      // "12589s": 3·7 벽 → 12 · 5(양쪽) · 89.
      expect(tilesOfWall(calcNCSafeTiles(leftWith('33337777s'))), t('12589s').toSet());
      expect(tilesOfWall(calcNCSafeTiles(leftWith('8888s'))), t('9s').toSet());
    });

    test('정렬: 끝쪽 먼저, 456 쪽 뒤', () {
      final l = calcNCSafeTiles(leftWith('33337777s'));
      expect(l.map((w) => Tiles.toCode(w.tile34)).toList(), ['1s', '9s', '2s', '8s', '5s']);
    });
  });

  group('원본 risk_base_test.go', () {
    test('TestCalculateRiskTiles34_SafeTile', () {
      var risk = calculateRiskTiles34(9, List.filled(34, false), leftWith('2222333377779999m 22228888p 333355557777s 4444z'), [], 27, 28);
      final zero1 = t('29m 4z').toSet();
      for (var i = 0; i < 34; i++) {
        expect(risk[i] == 0, zero1.contains(i), reason: Tiles.toCode(i));
      }
      risk = calculateRiskTiles34(9, safeOf('4m 5p 6s'), leftWith('111177778888m 1111222288889999p 222233339999s'), [], 27, 28);
      final zero2 = t('1478m 12589p 2369s').toSet();
      for (var i = 0; i < 34; i++) {
        expect(risk[i] == 0, zero2.contains(i), reason: Tiles.toCode(i));
      }
    });

    test('TestCalculateLeftNoSujiTiles', () {
      final none = List<bool>.filled(34, false);
      expect(calculateLeftNoSujiTiles(none, leftWith('')), t('123789m 123789p 123789s'));
      expect(calculateLeftNoSujiTiles(none, leftWith('33337777m 22228888p 5555s')), t('37p 1289s'));
      expect(calculateLeftNoSujiTiles(none, leftWith('11119999m 11119999p 11119999s')), t('2378m 2378p 2378s'));
      expect(calculateLeftNoSujiTiles(safeOf('123789m 123789p 123789s'), leftWith('')), isEmpty);
      expect(calculateLeftNoSujiTiles(safeOf('456m 456p 456s'), leftWith('')), isEmpty);
    });
  });

  group('조각 함수', () {
    test('OutsideTiles', () {
      expect(outsideTiles(t('3m')[0]), t('12m'));
      expect(outsideTiles(t('5p')[0]), t('37p'));
      expect(outsideTiles(t('7s')[0]), t('98s'));
      expect(outsideTiles(t('1m')[0]), isEmpty);
      expect(outsideTiles(Tiles.east), isEmpty);
    });

    test('울기 타점: 3000 × 1.4^min(3,도라) 뒤 × 1.3^min(2, 도라-3)', () {
      expect(ronPointOtherNakiWithDora(0), 3000);
      expect(ronPointOtherNakiWithDora(2), closeTo(5880, 1e-9));
      expect(ronPointOtherNakiWithDora(3), closeTo(8232, 1e-9));
      expect(ronPointOtherNakiWithDora(5), closeTo(8232 * 1.3 * 1.3, 1e-9));
      expect(ronPointOtherNakiWithDora(9), closeTo(8232 * 1.3 * 1.3, 1e-9));
    });

    test('도라 배율은 도라 목록에 든 만큼 거듭', () {
      // 9 순, 아무것도 안 보임: 5m 무스지5 12.8 × (14.9/12.8×78/58)² (5m 이 도라 둘)
      final left = leftWith('');
      final r = calculateRiskTiles34(9, List.filled(34, false), left, [4, 4], 27, 28);
      expect(r[4], closeTo(12.8 * fixedDoraRiskRateMulti[0] * fixedDoraRiskRateMulti[0], 1e-9));
    });
  });

  group('손으로 센 장면 (fixture 의 같은 이름 장면)', () {
    final doc = jsonDecode(File('test/fixtures/mh_risk_cases.json').readAsStringSync()) as Map<String, dynamic>;
    final cases = {for (final c in doc['cases'] as List) (c as Map<String, dynamic>)['name'] as String: c};
    RiskTable run(String name) => riskOf(contextOf(cases[name]!));
    double risk(RiskTable r, int seat, String tile) => r.bySeat[seat]!.risk34[Tiles.parse(tile)];

    test('리치 1명 · 9순 · 일발 아님 · 자', () {
      final r = run('riichi1_turn9_basic');
      final o = r.bySeat[1]!;
      expect(o.riichi, isTrue);
      expect(o.tenpaiRate, 100);
      expect(o.turns, 9);
      expect(o.ronPoint, 5172); // 배율 1
      expect(o.ippatsu, isFalse); // 선언 뒤 한 장 더 버림
      expect(risk(r, 1, '4m'), 0); // 현물
      expect(risk(r, 1, '1p'), 0); // 리치 뒤 상가가 낸 패
      expect(risk(r, 1, '1m'), closeTo(1.8, 1e-9)); // 4m 스지 → suji19, 9순 1.8
      expect(risk(r, 1, '7m'), closeTo(5.5, 1e-9)); // 4m 스지 → suji37 5.5
      expect(risk(r, 1, '5p'), closeTo(12.8, 1e-9)); // 2p·8p 둘 다 안전 아님 → 무스지5
      expect(risk(r, 1, '6m'), closeTo(13.1, 1e-9)); // 3m·9m 안전 아님 → 무스지46
      expect(risk(r, 1, '5s'), closeTo(7.4, 1e-9)); // 2s 현물 → 반스지5
      expect(risk(r, 1, '4s'), closeTo(7.2, 1e-9)); // 1s 현물 · 7s 아님 → 반스지46A
      expect(risk(r, 1, '5z'), closeTo(4.6, 1e-9)); // 백: 1장 보임 → 역패 남은3
      expect(risk(r, 1, '6z'), closeTo(1.9, 1e-9)); // 발: 2장 보임 → 역패 남은2
      expect(risk(r, 1, '2z'), closeTo(1.9, 1e-9)); // 남(하가 자풍): 2장 보임 → 역패 남은2
      // 다른 둘은 다마 9순 → 텐파이율 9 ≤ 15 라 합칠 때 빠진다 → 합친 위험 = 하가 위험 그대로
      expect(r.bySeat[2]!.tenpaiRate, 9);
      for (var i = 0; i < 34; i++) {
        expect(r.mixed34[i], closeTo(o.risk34[i], 1e-9));
      }
    });

    test('일발 ×7445/5172 · 친 ×1.5', () {
      final ip = run('riichi1_ippatsu').bySeat[1]!;
      expect(ip.ippatsu, isTrue);
      expect(ip.ronPoint, 7445);
      final dealer = run('riichi_dealer').bySeat[1]!;
      expect(dealer.ronPoint, 5172 * 1.5);
    });

    test('도라: 5p 무스지5 × 도라 배율', () {
      final r = run('riichi_dora');
      expect(risk(r, 1, '5p'), closeTo(12.8 * fixedDoraRiskRateMulti[RiskTileType.noSuji5], 1e-9));
    });

    test('벽: 8s 벽 → 9s 더블노찬스 스지19 1.8, 5m 벽 → 37m 스지37', () {
      final r = run('wall_nc_dnc');
      expect(r.left34[Tiles.parse('8s')], 0);
      expect(r.left34[Tiles.parse('5m')], 0);
      expect(risk(r, 1, '9s'), 0); // 9s 는 하가 현물
      expect(risk(r, 2, '9s'), closeTo(1.8 * 4536 / 5172, 1e-9)); // 대면은 다마 → ×4536/5172
      // 5m 벽은 먼저 37m 을 스지37(5.5)로 두지만, 같은 벽으로 3m·7m 이 노찬스가 되어 뒤에서 스지28(3.9)로 덮인다(원본 순서).
      expect(risk(r, 2, '3m'), closeTo(3.9 * 4536 / 5172, 1e-9));
      expect(risk(r, 2, '7m'), closeTo(3.9 * 4536 / 5172, 1e-9));
      expect(tilesOfWall(r.doubleNoChance), contains(Tiles.parse('9s')));
    });

    test('자패 남은 장수', () {
      final r = run('honor_left_counts');
      expect(risk(r, 1, '2z'), closeTo(0.3, 1e-9)); // 장풍·자풍 남, 남은1
      expect(risk(r, 1, '3z'), closeTo(0.2, 1e-9)); // 객풍 남은1
      expect(risk(r, 1, '4z'), closeTo(1.8, 1e-9)); // 객풍 남은2
      expect(risk(r, 1, '5z'), closeTo(1.9, 1e-9)); // 역패 남은2
      expect(risk(r, 1, '6z'), 0); // 4장 다 보임
    });

    test('리치 2명 합치기: r = r1 + r3 − r1·r3/100', () {
      final r = run('riichi2_mixed');
      final a = r.bySeat[1]!.risk34;
      final b = r.bySeat[3]!.risk34;
      for (var i = 0; i < 34; i++) {
        expect(r.mixed34[i], closeTo(a[i] + b[i] - a[i] * b[i] / 100, 1e-9));
      }
      // 6m: 둘 다 무스지46 13.1 → 13.1 + 13.1 − 13.1²/100 = 24.4839
      expect(r.mixed34[Tiles.parse('6m')], closeTo(24.4839, 1e-9));
    });

    test('울기 텐파이율 표 조회와 모르는 쯔모기리', () {
      expect(run('naki1_known').bySeat[2]!.tenpaiRate, 58.60); // 표[1][9][3]
      expect(run('naki1_unknown_tedashi').bySeat[2]!.tenpaiRate, 70.18); // 표[1][9][5]
      expect(run('naki1_unknown_tsumogiri').bySeat[2]!.tenpaiRate, 41.25); // 표[1][9][1]
      expect(run('naki1_unknown_firstColumn').bySeat[2]!.tenpaiRate, 30.11); // 표[1][9][0]
      expect(run('naki1_known').bySeat[2]!.ronPoint, 3000); // 도라 없는 울기
      final n3 = run('naki3_dora_red').bySeat[3]!;
      expect(n3.ronPoint, closeTo(5880, 1e-9)); // 5s 도라 1 + 적 1 → 3000×1.4²
      expect(n3.tenpaiRate, 94.75); // 표[3][10][2]
      final n4 = run('naki4_hadaka').bySeat[2]!;
      expect(n4.tenpaiRate, 100);
      expect(n4.leftNoSujiTiles, isEmpty);
    });

    test('다마: 텐파이율 = 버림 수, 15 이하는 합침에서 빠짐', () {
      final r12 = run('dama_turn12_excluded');
      expect(r12.opponents.map((o) => o.tenpaiRate), [12, 12, 12]);
      expect(r12.mixed34.every((x) => x == 0), isTrue);
      final r16 = run('dama_turn16_sameturn_furiten');
      expect(r16.opponents.map((o) => o.tenpaiRate), [16, 16, 16]);
      // 16순: 0 5s → 1 4s → 2 7m → 3 4m, 17순: 0 6s.
      // 하가(1)의 마지막 버림 4s 뒤에 대면이 낸 7m 은 하가에게 동순 후리텐으로 안전, 그보다 뒤에 버린 상가(3)에게는 아님.
      expect(r16.bySeat[1]!.safe34[Tiles.parse('7m')], isTrue);
      expect(r16.bySeat[3]!.safe34[Tiles.parse('7m')], isFalse);
      expect(r16.bySeat[1]!.risk34[Tiles.parse('7m')], 0);
      expect(r16.mixed34.any((x) => x > 0), isTrue); // 16 > 15 라 합침에 들어감
    });

    test('깡한 패 · 이른 바깥패 · 순목 19 · 쯔모기리 리치 · 가깡 일발', () {
      final k = run('kan_safe_tiles');
      expect(k.bySeat[1]!.safe34[Tiles.parse('5p')], isTrue);
      expect(k.bySeat[2]!.safe34[Tiles.parse('8m')], isTrue);
      final e = run('early_outside_stack');
      expect(risk(e, 1, '1m'), closeTo(1.8 * 0.4 * 0.4 * 0.4, 1e-9));
      expect(run('turns_clamped_19').bySeat[1]!.turns, 19);
      final tr = run('tsumogiri_riichi');
      expect(tr.bySeat[2]!.tsumogiriRiichi, isTrue);
      expect(tr.bySeat[1]!.tsumogiriRiichi, isNull);
      final kk = run('kakan_breaks_ippatsu');
      expect(kk.bySeat[1]!.ippatsu, isFalse);
      expect(kk.bySeat[2]!.safe34[Tiles.parse('8s')], isTrue);
    });
  });

  group('fixture: 원본 Go 와 맞대기', () {
    final file = File('test/fixtures/mh_risk_cases.json');
    final doc = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
    final cases = (doc['cases'] as List).cast<Map<String, dynamic>>();
    final write = Platform.environment['MH_RISK_WRITE'] == '1';

    test('장면 15개 이상', () => expect(cases.length, greaterThanOrEqualTo(15)));

    for (final c in cases) {
      test(c['name'], () {
        final out = outputOf(riskOf(contextOf(c)));
        expect(diff(out, c['go']), isEmpty, reason: 'Go 와 다름');
        if (write) {
          c['dart'] = out;
        } else {
          expect(diff(out, c['dart']), isEmpty, reason: '지난 Dart 출력과 다름');
        }
      });
    }

    if (write) {
      tearDownAll(() => file.writeAsStringSync('${const JsonEncoder.withIndent(' ').convert(doc)}\n'));
    }
  });
}
