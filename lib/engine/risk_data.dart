// Ported from EndlessCheng/mahjong-helper (MIT) util/risk_data.go
// Copyright (c) 2018 Σndless — MIT License, see third_party/mahjong-helper/LICENSE
// 원본 커밋 514bb97c5a6d157fa2ed1ac804a53cb9b559d7d0. 숫자는 손대지 않고 그대로 옮겼다.
//
// 방총률 표(순목 × 19종). 출처는 원본 주석대로 「科学する麻雀」·통계 자료.
library;

/// 위험 종류. [riskRate] 의 열 번호와 1:1 (원본 `tileType`, iota 순서 그대로).
/// 오른쪽 숫자는 원본 주석의 9순째 값.
abstract final class RiskTileType {
  static const int noSuji5 = 0; // 12.8
  static const int noSuji46 = 1; // 13.1
  static const int noSuji37 = 2; // 9.5
  static const int noSuji28 = 3; // 8.6
  static const int noSuji19 = 4; // 7.4
  static const int halfSuji5 = 5; // 7.4
  static const int halfSuji46A = 6; // 7.2 현물이 19 쪽
  static const int halfSuji46B = 7; // 7.9 현물이 73 쪽
  static const int suji37 = 8; // 5.5
  static const int suji28 = 9; // 3.9
  static const int suji19 = 10; // 1.8
  static const int doubleSuji5 = 11; // 2.2
  static const int doubleSuji46 = 12; // 2.3
  static const int yakuHaiLeft3 = 13; // 4.6 자패-역패-남은 3
  static const int yakuHaiLeft2 = 14; // 1.9 자패-역패-남은 2
  static const int yakuHaiLeft1 = 15; // 0.3 자패-역패-남은 1
  static const int otakazeLeft3 = 16; // 4.0 자패-객풍-남은 3
  static const int otakazeLeft2 = 17; // 1.8 자패-객풍-남은 2
  static const int otakazeLeft1 = 18; // 0.2 자패-객풍-남은 1
}

/// `RiskRate[순목][종류]` (%). 0행은 비어 있다(원본 그대로). 순목 1~19.
const List<List<double>> riskRate = [
  [],
  [5.7, 5.7, 5.8, 4.7, 3.4, 2.5, 2.5, 3.1, 5.6, 3.8, 1.8, 0.8, 2.6, 2.1, 1.2, 0.5, 2.4, 1.4, 1.2], // 1
  [6.6, 6.9, 6.3, 5.2, 4.0, 3.5, 3.5, 4.1, 5.3, 3.5, 1.9, 0.8, 2.6, 2.3, 1.2, 0.5, 2.7, 1.3, 0.4],
  [7.7, 8.0, 6.7, 5.8, 4.6, 4.3, 4.1, 4.9, 5.2, 3.6, 1.8, 1.6, 2.0, 2.4, 1.2, 0.3, 2.6, 1.2, 0.3],
  [8.5, 8.9, 7.1, 6.2, 5.1, 4.8, 4.7, 5.6, 5.2, 3.8, 1.7, 1.6, 2.0, 2.6, 1.1, 0.2, 2.6, 1.2, 0.2],
  [9.4, 9.7, 7.5, 6.7, 5.5, 5.3, 5.1, 6.0, 5.3, 3.7, 1.7, 1.7, 2.0, 2.9, 1.2, 0.2, 2.8, 1.2, 0.2], // 5
  [10.2, 10.5, 7.9, 7.1, 5.9, 5.8, 5.6, 6.4, 5.2, 3.7, 1.7, 1.8, 2.0, 3.2, 1.3, 0.2, 2.9, 1.3, 0.2],
  [11.0, 11.3, 8.4, 7.5, 6.3, 6.3, 6.1, 6.8, 5.3, 3.7, 1.7, 2.0, 2.1, 3.6, 1.4, 0.2, 3.2, 1.4, 0.2],
  [11.9, 12.2, 8.9, 8.0, 6.8, 6.9, 6.6, 7.4, 5.3, 3.8, 1.7, 2.1, 2.2, 4.0, 1.6, 0.2, 3.5, 1.6, 0.2],
  [12.8, 13.1, 9.5, 8.6, 7.4, 7.4, 7.2, 7.9, 5.5, 3.9, 1.8, 2.2, 2.3, 4.6, 1.9, 0.3, 4.0, 1.8, 0.2], // 9
  [13.8, 14.1, 10.1, 9.2, 8.0, 8.0, 7.8, 8.5, 5.6, 4.0, 1.9, 2.4, 2.4, 5.3, 2.2, 0.3, 4.6, 2.1, 0.3],
  [14.9, 15.1, 10.8, 9.9, 8.7, 8.7, 8.5, 9.2, 5.7, 4.2, 2.0, 2.5, 2.6, 6.0, 2.6, 0.4, 5.1, 2.5, 0.3],
  [16.0, 16.3, 11.6, 10.6, 9.4, 9.4, 9.2, 9.9, 6.0, 4.4, 2.2, 2.7, 2.7, 6.8, 3.1, 0.4, 5.1, 2.5, 0.3],
  [17.2, 17.5, 12.4, 11.4, 10.2, 10.2, 10.0, 10.6, 6.2, 4.6, 2.4, 3.0, 3.0, 7.8, 3.7, 0.5, 6.6, 3.7, 0.5],
  [18.5, 18.8, 13.3, 12.3, 11.1, 11.0, 10.9, 11.4, 6.6, 4.9, 2.7, 3.2, 3.1, 8.8, 4.4, 0.7, 7.4, 4.4, 0.6],
  [19.9, 20.1, 14.3, 13.3, 12.0, 11.9, 11.8, 12.3, 7.0, 5.3, 3.0, 3.4, 3.4, 9.9, 5.2, 0.8, 8.4, 5.3, 0.8], // 15
  [21.3, 21.7, 15.4, 14.3, 13.1, 12.9, 12.8, 13.3, 7.4, 5.7, 3.3, 3.7, 3.6, 11.2, 6.2, 1.0, 9.4, 6.5, 0.9],
  [22.9, 23.2, 16.6, 15.4, 14.2, 14.0, 13.8, 14.4, 8.0, 6.1, 3.6, 3.9, 3.9, 12.4, 7.3, 1.3, 10.5, 7.7, 1.2],
  [24.7, 24.9, 17.9, 16.7, 15.4, 15.2, 15.0, 15.6, 8.5, 6.6, 4.0, 4.3, 4.2, 13.9, 8.5, 1.7, 11.8, 9.4, 1.6], // 18
  [27.5, 27.8, 20.4, 19.1, 17.8, 17.5, 17.5, 17.5, 9.8, 7.4, 5.0, 5.1, 5.1, 18.1, 12.1, 2.8, 14.7, 12.6, 2.1],
];

/// 원본 `MaxTurns = len(RiskRate) - 1` = 19.
final int maxRiskTurns = riskRate.length - 1;

/// 도라일 때의 배율: 방총률 비 × 실점 비를 합친 값(원본 주석: 9순째 자료 기준). [RiskTileType] 순서.
const List<double> fixedDoraRiskRateMulti = [
  14.9 / 12.8 * 78 / 58,
  15.0 / 13.1 * 78 / 58,
  12.1 / 9.5 * 75 / 56,
  10.3 / 8.6 * 75 / 54,
  8.9 / 7.4 * 77 / 53,
  //
  9.7 / 7.4 * 81 / 60,
  8.9 / 7.2 * 81 / 60,
  10.4 / 7.9 * 81 / 60,
  8.0 / 5.5 * 75 / 56,
  5.5 / 3.9 * 81 / 56,
  3.5 / 1.8 * 92 / 58,
  4.1 / 2.2 * 88 / 62,
  4.1 / 2.3 * 88 / 62,
  //
  5.2 / 4.6 * 96 / 67,
  2.9 / 1.9 * 96 / 67,
  1.1 / 0.3 * 96 / 67,
  5.1 / 4.0 * 92 / 56,
  3.0 / 1.8 * 92 / 56,
  0.8 / 0.2 * 92 / 56,
];

/// `[판단할 패 번호(0-8)][대응하는 현물 여부(0-1 또는 0-3)]`.
/// 123789: 현물 없음, 있음. 4: 17 둘 다 없음 / 1 없고 7 있음 / 1 있고 7 없음 / 둘 다. 56 도 같은 식.
const List<List<int>> tileTypeTable = [
  [RiskTileType.noSuji19, RiskTileType.suji19],
  [RiskTileType.noSuji28, RiskTileType.suji28],
  [RiskTileType.noSuji37, RiskTileType.suji37],
  [RiskTileType.noSuji46, RiskTileType.halfSuji46B, RiskTileType.halfSuji46A, RiskTileType.doubleSuji46],
  [RiskTileType.noSuji5, RiskTileType.halfSuji5, RiskTileType.halfSuji5, RiskTileType.doubleSuji5],
  [RiskTileType.noSuji46, RiskTileType.halfSuji46A, RiskTileType.halfSuji46B, RiskTileType.doubleSuji46],
  [RiskTileType.noSuji37, RiskTileType.suji37],
  [RiskTileType.noSuji28, RiskTileType.suji28],
  [RiskTileType.noSuji19, RiskTileType.suji19],
];

/// `[역패인가(0-1)][남은 장수-1]`.
const List<List<int>> honorTileType = [
  [RiskTileType.otakazeLeft1, RiskTileType.otakazeLeft2, RiskTileType.otakazeLeft3, RiskTileType.otakazeLeft3],
  [RiskTileType.yakuHaiLeft1, RiskTileType.yakuHaiLeft2, RiskTileType.yakuHaiLeft3, RiskTileType.yakuHaiLeft3],
];

// --- util/point_data.go 의 론 점수 평균(위험도 보정에 쓰는 것만) ---
// 원본 주석: 자(子) 론 점수 평균, 참고 「統計学」のマージャン戦術, 친은 ×1.5.
// TODO(원본): 남은 도라 수가 실점에 주는 영향.

/// 기준. 리치(일발 아님).
const double ronPointRiichiHiIppatsu = 5172.0;
const double ronPointRiichiIppatsu = 7445.0;

/// 원본 주석 `*fixed` (임시값).
const double ronPointOtherNaki = 3000.0;

/// TODO(원본): 더블 동의 영향 고려.
const double ronPointDama = 4536.0;

/// 원본 `RonPointOtherNakiWithDora`: 울기 상대의 대략적 타점.
/// 도라 0 3000 · 1 4200 · 2 5880 · 3 8232 · 4 10000 · 5 13000 (원본 주석, 친은 밖에서 ×1.5).
/// TODO(원본): 안깡이 타점을 얼마나 올리나?
double ronPointOtherNakiWithDora(int doraCount) {
  var point = ronPointOtherNaki;
  const doraMulti = 1.4; // TODO(원본): 조정 필요?
  for (var i = 0; i < (doraCount < 3 ? doraCount : 3); i++) {
    point *= doraMulti;
  }
  doraCount -= 3;
  if (doraCount <= 0) return point;
  const doraMulti2 = 1.3; // TODO(원본): 조정 필요?
  for (var i = 0; i < (doraCount < 2 ? doraCount : 2); i++) {
    point *= doraMulti2;
  }
  return point;
}
