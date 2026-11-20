// lib/engine/tenpai_rate.dart (EndlessCheng/mahjong-helper util/tenpai_rate.go 옮김) 시험.
// 앞의 여섯은 원본 util/tenpai_rate_test.go `TestCalcTenpaiRate` 의 기대값 그대로.
// 버림 인코딩도 원본 그대로: 손에서 낸 패 = 패 번호, 쯔모기리 = ~패 번호(음수, 예: -4 = ~3).
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/tenpai_rate.dart';

void main() {
  const chi = MeldKind.chi; // 원본 시험의 `model.Meld{}` 는 MeldType 0 = 치

  group('원본 TestCalcTenpaiRate', () {
    test('울기 없음 · 버림 없음 → 0', () => expect(calcTenpaiRate([], [], []), 0.0));
    test('안깡만 → 울기 아님(다마) → 버림 수 0', () => expect(calcTenpaiRate([MeldKind.ankan], [], []), 0.0));
    test('울기 4개 → 100', () => expect(calcTenpaiRate([chi, chi, chi, chi], [], []), 100.0));
    test('1울기 5순, 울기 뒤 버림 [3]=4 [4]=5 데다시 2 → 표[1][5][2]', () {
      expect(calcTenpaiRate([chi], [1, 2, 3, 4, 5], [2]), closeTo(19.88, 1e-3));
    });
    test('2울기 5순, 마지막 울기 뒤 버림 없음 → 표[2][5][0]', () {
      expect(calcTenpaiRate([chi, chi], [1, 2, 3, 4, 5], [2, 4]), closeTo(23.24, 1e-3));
    });
    test('3울기 12순, 마지막 울기(6) 뒤 12 -4 -6 7 2 → 데다시 3 → 표[3][12][3]', () {
      expect(calcTenpaiRate([chi, chi, chi], [1, 2, 3, 4, 5, 23, 16, 12, -4, -6, 7, 2], [2, 4, 6]), closeTo(98.26, 1e-3));
    });
  });

  group('범위 밖 처리(원본 그대로)', () {
    test('다마는 순목 수 그대로(자르지 않음)', () {
      expect(calcTenpaiRate([], List.filled(21, 0), []), 21.0);
      expect(calcTenpaiRate([MeldKind.ankan, MeldKind.ankan], List.filled(9, 0), [3]), 9.0);
    });

    test('순목은 18 에서 자름: 1울기 20순 → 표[1][18]', () {
      // 표[1][18] = [69.02, 84.51, 84.51], 울기 뒤 데다시 5 → 마지막 열 2
      final d = List.filled(20, 0);
      expect(calcTenpaiRate([MeldKind.pon], d, [14]), 84.51);
    });

    test('데다시 수는 행 길이 - 1 에서 자름: 1울기 9순 데다시 8 이상 → 80.23', () {
      expect(calcTenpaiRate([MeldKind.pon], List.filled(9, 1), [0]), 80.23); // 데다시 8 = 마지막 열
      expect(calcTenpaiRate([MeldKind.pon], List.filled(9, 1), [0]), tenpaiRateTable[1][9].last);
    });

    test('쯔모기리 0번 패(1m)는 ~0 = -1 로 센다', () {
      // 1울기 5순, 울기 뒤 [3] 1m 쯔모기리, [4] 1m 손 → 데다시 1 → 표[1][5][1]
      expect(calcTenpaiRate([MeldKind.pon], [9, 9, 9, ~0, 0], [2]), 14.42);
    });

    test('울기 뒤 버림 표시가 아직 없으면 0 열', () {
      expect(calcTenpaiRate([MeldKind.pon], [1, 2, 3], []), tenpaiRateTable[1][3][0]);
    });

    test('3인 근사 rate × (2 − rate/100)', () {
      expect(tenpaiRate3(50), 75);
      expect(tenpaiRate3(100), 100);
    });
  });
}
