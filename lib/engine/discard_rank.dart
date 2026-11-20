// Ported from EndlessCheng/mahjong-helper (MIT)
//   analysis.go(simpleBestDiscardTile 21–25 줄 · 샹텐 후퇴 권장),
//   cli.go(alertBackwardToShanten2), util/shanten_improve.go(CalculateShantenWithImproves14 811–823)
// Copyright (c) 2018 Σndless
// 원본 LICENSE 전문: third_party/mahjong-helper/LICENSE
//
// 버림 평가의 바깥 API. 손·문맥을 받아 원본 순서대로 버림 후보를 돌려준다.
// 계산은 improve.dart(개량·속도·탐색·정렬), agari_rate.dart(화료율),
// hand_value.dart(기대 타점·국수지)에 있다.
//
// 원본 규칙 가정(우리 쪽과 다를 수 있는 것은 각 파일 머리 참고):
// - 쿠이탕 있음, 적5 는 도라 1(우리 RuleSet.standard 와 같음).
// - 리치 기대 타점은 일발·쯔모·뒷도라를 표 보정(fixedRiichiPoint)으로만 넣는다.
// - 화료율 표는 6~10순 통계 하나뿐(순목을 보지 않음).
// - 후퇴 권장은 「1샹텐 · 자기 버림 9장 미만 · 멘젠 · 1위 유효패 9장 미만 ·
//   후퇴 1위 속도 점수가 더 높음」. 원본은 순목 대신 자기 버림 수를 센다.

import 'calculator.dart';
import 'improve.dart';

export 'improve.dart'
    show Hand13AnalysisResult, Hand14AnalysisResult, Improves14, MhWaits;

/// 버림 평가 입력.
class DiscardContext {
  /// 닫힌 손패 34칸. 버리기 전이라 `14 − 3 × 울기 수` 장.
  final List<int> hand34;

  /// 내 울기(안깡 포함).
  final List<Meld> melds;

  /// 내 닫힌 손패 밖에 보이는 패 34칸: 네 자리 강, 모든 울기 묶음(내 것 포함),
  /// 도라 표시패. 남은 장수 = max(0, 4 − 손패 − 이것).
  final List<int> visible34;

  /// 도라 표시패(실제 도라가 아님).
  final List<int> doraIndicators;

  /// 만·통·삭 적5 개수(손패 + 내 울기).
  final List<int> redFives;

  final int roundWind;
  final int seatWind;

  /// 친인지. 원본처럼 자풍과 따로 받는다.
  final bool isDealer;

  /// 자기 버림(후리텐 · 스지 종류 · 후퇴 권장의 「9장 미만」).
  final List<int> selfDiscards;

  /// 남은 쯔모 수(출력에 실어 보내기만 한다).
  final int leftDrawTiles;

  DiscardContext({
    required this.hand34,
    this.melds = const [],
    List<int>? visible34,
    this.doraIndicators = const [],
    List<int>? redFives,
    this.roundWind = Tiles.east,
    this.seatWind = Tiles.east,
    this.isDealer = false,
    this.selfDiscards = const [],
    this.leftDrawTiles = 0,
  })  : visible34 = visible34 ?? List<int>.filled(34, 0),
        redFives = redFives ?? const [0, 0, 0] {
    if (hand34.length != 34 || this.visible34.length != 34) {
      throw ArgumentError('손패·보이는 패는 34칸이어야 합니다');
    }
    if (this.redFives.length != 3) throw ArgumentError('적5 는 만·통·삭 3칸');
  }

  /// 원본 `PlayerInfo` 로. 남은 장수는 0 아래로 내려가지 않게 자른다.
  MhPlayerInfo toPlayerInfo() => MhPlayerInfo(
        handTiles34: List.of(hand34),
        melds: melds,
        doraIndicators: doraIndicators,
        numRedFives: redFives,
        roundWindTile: roundWind,
        selfWindTile: seatWind,
        isParent: isDealer,
        discardTiles: selfDiscards,
        leftTiles34: [
          for (var t = 0; t < 34; t++)
            (4 - hand34[t] - visible34[t]).clamp(0, 4),
        ],
        leftDrawTilesCount: leftDrawTiles,
      );
}

/// 버림 후보 하나의 평가.
class RankedDiscard {
  final int tile;

  /// 버린 뒤 샹텐.
  final int shanten;

  /// 버린 뒤 유효패(패 → 남은 장수, 남은 0 인 종류 포함).
  final Map<int, int> waits;

  /// 유효패 남은 장수 합.
  final int waitsCount;

  /// 개량 평균(원본 AvgImproveWaitsCount).
  final double avgImproveWaitsCount;

  /// 개량 종류 수(원본 len(Improves)).
  final int improveKinds;

  /// 원본 ImproveWayCount.
  final int improveWayCount;

  /// 전진 뒤 유효패 가중평균(원본 AvgNextShantenWaitsCount).
  final double avgNextShantenWaitsCount;

  /// 속도 점수(원본 MixedWaitsScore). NaN 일 수 있다(원본과 같음).
  final double speedScore;

  /// 화료율(%), 텐파이일 때만.
  final double agariRate;

  /// 다마·울기 기대 타점.
  final double damaPoint;

  /// 리치 기대 타점.
  final double riichiPoint;

  /// 국수지(텐파이: 직접, 1·2샹텐: 자식 최선값 가중평균).
  final double roundPoint;

  /// 후리텐 가능성 0 / 0.5 / 1.
  final double furitenRate;

  /// 샹텐이 물러나는 버림인지.
  final bool isBackward;

  /// 이 후보가 원본이 고르는 「최선」인지([DiscardRanking.best]).
  final bool isBest;

  /// 원본 분석 결과 그대로.
  final Hand14AnalysisResult raw;

  RankedDiscard._(this.raw, {required this.isBackward, required this.isBest})
      : tile = raw.discardTile,
        shanten = raw.result13.shanten,
        waits = raw.result13.waits.toMap(),
        waitsCount = raw.result13.waits.allCount,
        avgImproveWaitsCount = raw.result13.avgImproveWaitsCount,
        improveKinds = raw.result13.improves.length,
        improveWayCount = raw.result13.improveWayCount,
        avgNextShantenWaitsCount = raw.result13.avgNextShantenWaitsCount,
        speedScore = raw.result13.mixedWaitsScore,
        agariRate = raw.result13.avgAgariRate,
        damaPoint = raw.result13.damaPoint,
        riichiPoint = raw.result13.riichiPoint,
        roundPoint = raw.result13.mixedRoundPoint,
        furitenRate = raw.result13.furitenRate;

  /// 후퇴 권장으로 1위가 된 후퇴 버림인지.
  bool get recommendBackward => isBackward && isBest;

  @override
  String toString() =>
      '${isBackward ? '(후퇴) ' : ''}${Tiles.toCode(tile)} 버림: ${raw.result13}';
}

/// 버림 평가 전체.
class DiscardRanking {
  /// 버리기 전(14장 쪽) 샹텐.
  final int shanten;

  /// 샹텐을 지키는 버림, 원본 Sort 순서.
  final List<RankedDiscard> forward;

  /// 샹텐이 물러나는 버림, 원본 Sort 순서.
  final List<RankedDiscard> backward;

  /// 원본 `simpleBestDiscardTile` 의 답. 후보가 없으면 null.
  final int? best;

  /// 원본이 「샹텐 후퇴?」를 띄우는지.
  final bool recommendBackward;

  const DiscardRanking(this.shanten, this.forward, this.backward, this.best,
      this.recommendBackward);

  /// 원본 출력 순서: 지키는 버림 다음 물러나는 버림.
  List<RankedDiscard> get all => [...forward, ...backward];
}

/// 원본 `CalculateShantenWithImproves14` + `simpleBestDiscardTile`.
DiscardRanking analyzeDiscards(DiscardContext ctx) {
  final pi = ctx.toPlayerInfo();
  final r = calculateShantenWithImproves14(pi);
  final results = r.results, inc = r.incShantenResults;

  int? best;
  var backwardBest = false;
  if (results.isNotEmpty) {
    best = results[0].discardTile;
  } else if (inc.isNotEmpty) {
    best = inc[0].discardTile;
    backwardBest = true;
  }
  // 1샹텐 초·중반(자기 버림 9장 미만) 멘젠: 1위 유효패가 9장 미만이고 후퇴 1위
  // 속도 점수가 높으면 후퇴(울었을 때 후퇴는 원본도 아직 안 봄).
  var recommend = false;
  if (r.shanten == 1 &&
      pi.discardTiles.length < 9 &&
      results.isNotEmpty &&
      inc.isNotEmpty &&
      !pi.isNaki) {
    if (results[0].result13.waits.allCount < 9 &&
        results[0].result13.mixedWaitsScore <
            inc[0].result13.mixedWaitsScore) {
      best = inc[0].discardTile;
      backwardBest = true;
      recommend = true;
    }
  }

  final forward = <RankedDiscard>[
    for (var i = 0; i < results.length; i++)
      RankedDiscard._(results[i],
          isBackward: false, isBest: !backwardBest && i == 0),
  ];
  final backward = <RankedDiscard>[
    for (var i = 0; i < inc.length; i++)
      RankedDiscard._(inc[i], isBackward: true, isBest: backwardBest && i == 0),
  ];
  return DiscardRanking(r.shanten, forward, backward, best, recommend);
}

/// 원본 순서(지키는 버림 → 물러나는 버림)의 평가 목록.
List<RankedDiscard> rankDiscards(DiscardContext ctx) =>
    analyzeDiscards(ctx).all;
