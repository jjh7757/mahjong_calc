/// 패보 복기 화면의 버림 평가(리뷰) 위젯: 수 말풍선 · 단계 말풍선, 등급 아이콘, 수 띠, 펼침(후보 · 참고값 · 자세히 표),
/// 최선 보기 막대 재료. 설계는 `docs/paifu_review_ui_design_1121.md`(3-2 ~ 3-9).
///
/// 계산은 [reviewPaifu] 가 하고, 글은 `lib/paifu/review_sentence.dart` 가 만든다. 여기서는 걸음에 붙이고 그림으로 바꾸기만 한다.
/// mahjong-helper 엔진 참고값은 한 판에 수 초가 걸려 [computeEngineReview] 로 뒤에서 낸 뒤 "참고값" 펼침에 붙인다.
library;

import 'dart:convert';

import 'package:flutter/foundation.dart' show compute;
import 'package:flutter/material.dart';

import '../../engine/efficiency.dart';
import '../../engine/risk_calibration.dart' show calibrateRisk;
import '../../engine/tile.dart';
import '../../paifu/paifu.dart';
import '../../paifu/paifu_review.dart';
import '../../paifu/review_sentence.dart';
import '../tile_view.dart';

// ── 문구 ──

String reviewGradeName(ReviewGrade g) => gradeName(g);

String _tileName(PaifuTile t) => tileText(t);

// ── mahjong-helper 엔진 참고값 ──
//
// 등급 · 말풍선과 따로, "참고값" 단추를 눌렀을 때만 펼친다([EngineReviewFold], 11-21 설계서 3-9). 후퇴 권장
// (mhRecommendBackward)은 보이지 않는다 — 강한 AI 와 맞대 보니 6번 중 0번 맞았다(11-20). 그래서 추천은
// 「샹텐을 지키는 후보 중 엔진 1위」. 아래 engineLines 계열(실제 버림 · 추천 · 위험 줄)은 예전 상자의 글로, 시험과 사실 비교에 남긴다.

const engineReviewPending = '참고값 계산 중…';
const engineReviewTooltip = '화료율은 mahjong-helper 의 통계표로 낸 어림값입니다. '
    '방총 위험은 그 엔진 값을 천봉 고수 대국의 실제 방총률에 맞춰 고친 어림값이고, 모두에게 안전한 패는 "안전" 으로 적습니다. '
    '등급(패효율)과는 따로 셉니다. 국수지는 이 손의 화료 가치를 점수로 어림한 값입니다.';

/// 엔진 참고값 계산 상태. off = 계산하지 않는 판(숫자 있는 차례가 없음).
enum EngineReviewStatus { off, pending, ready, failed }

String _f1(double x) => x.toStringAsFixed(1);

bool _pos(double? x) => x != null && x.isFinite && x > 0;

/// 엔진 후보 하나의 숫자 요약. 텐파이면 개량 뒤 대기 · 화료율 · 기대 점수, 아니면 개량 뒤 유효패 · 속도.
/// [withRound] 면 국수지도.
String _mhStats(RankedDiscard d, {bool withRound = true}) {
  final tenpai = d.shanten <= 0;
  final parts = <String>[
    if (d.avgImproveWaitsCount.isFinite) '개량 뒤 ${tenpai ? '대기' : '유효패'} 평균 ${_f1(d.avgImproveWaitsCount)}장',
    if (!tenpai && d.speedScore.isFinite) '속도 ${_f1(d.speedScore)}',
    if (tenpai) '화료율 ${_f1(d.agariRate.isFinite ? d.agariRate : 0)}%',
    if (tenpai) ...[
      if (d.raw.result13.isNaki && _pos(d.damaPoint)) '기대 ${d.damaPoint.round()}점(다마)',
      if (!d.raw.result13.isNaki && _pos(d.riichiPoint)) '기대 ${d.riichiPoint.round()}점(리치 기준)',
    ],
    if (withRound && _pos(d.roundPoint)) '국수지 ${d.roundPoint.round()}',
  ];
  return parts.join(' · ');
}

/// 실제 버림 줄: "실제 버림 4만: 개량 뒤 유효패 평균 10.9장 · 속도 15.3 · 국수지 3132". 엔진 칸이 없으면 null.
String? engineActualLine(TurnReview t) {
  final a = t.mhActual;
  if (a == null) return null;
  final back = a.isBackward ? ' (샹텐 후퇴)' : '';
  return '실제 버림 ${_tileName(t.discard)}$back: ${_mhStats(a)}';
}

/// 「점수 · 화료까지 본 추천」 줄: 샹텐을 지키는 후보 중 엔진 1위. 실제 버림과 같으면 "실제 버림과 같음".
/// 엔진 칸이 없거나 지키는 후보가 없으면 null.
String? engineRecommendLine(TurnReview t) {
  final l = t.mh;
  if (l == null) return null;
  RankedDiscard? top;
  for (final d in l) {
    if (!d.isBackward) {
      top = d;
      break;
    }
  }
  if (top == null) return null;
  const head = '점수 · 화료까지 본 추천';
  if (top.tile == t.discard.tile) return '$head: 실제 버림과 같음';
  // 값이 모두 같고 원본이 패 위치로만 가른 동률이면 그렇게 적는다.
  final a = t.mhActual;
  if (a != null && _mhSameValues(top, a)) return '$head: ${Tiles.name(top.tile)} — 실제 버림과 값이 같음';
  return '$head: ${Tiles.name(top.tile)} (${_mhStats(top, withRound: false)})';
}

/// 원본 Sort 가 값으로는 가르지 못하는 두 후보(lib/paifu/paifu_review.dart `_mhTied` 와 같은 칸, 실수는 1e-5 안).
/// mhRankOfActual 은 후퇴 권장이 걸리면 후퇴 패를 1위로 두고 세어 여기 쓰지 않는다.
bool _mhSameValues(RankedDiscard a, RankedDiscard b) {
  bool eq(double x, double y) => (x.isNaN && y.isNaN) || (x - y).abs() < 1e-5;
  return a.isBackward == b.isBackward &&
      a.shanten == b.shanten &&
      a.waitsCount == b.waitsCount &&
      eq(a.speedScore, b.speedScore) &&
      eq(a.avgNextShantenWaitsCount, b.avgNextShantenWaitsCount) &&
      eq(a.agariRate, b.agariRate) &&
      eq(a.avgImproveWaitsCount, b.avgImproveWaitsCount) &&
      eq(a.roundPoint, b.roundPoint) &&
      a.raw.isIsolatedYaochuDiscardTile == b.raw.isIsolatedYaochuDiscardTile &&
      eq(a.raw.discardTileValue, b.raw.discardTileValue);
}

// ── 화면에 보이는 방총 위험(설계서 docs/risk_calibration_design_1123.md 6절) ──
//
// 엔진 값(TurnReview.riskOfActual · riskByKind)은 순서는 맞지만 값이 커서, 보일 때만 위협 종류(리치 / 울기만)별
// 보정표(lib/engine/risk_calibration.dart)를 거친다. 모두에게 안전패(RiskTable.safeForAll34)는 숫자 대신 "안전".
// "가장 안전" 패는 원래 값으로 고른다(보정이 단조라 순서가 같다). 복기 에이전트 사실표는 원래 값 그대로 쓴다.

/// 모두에게 안전패를 숫자 대신 적는 말.
const riskSafeWord = '안전';

/// 화면에 보이는 [tile] 의 방총 위험(%): 모두에게 안전패면 0, 아니면 엔진 값 [engine] 을 이 차례 위협 종류의 보정표로
/// 바꾼 값. 위협이 없는 차례(보정표를 못 고름)면 엔진 값 그대로.
double shownRisk(TurnReview t, int tile, double engine) {
  if (t.riskSafeForAll(tile)) return 0;
  final k = t.riskThreat;
  return k == null ? engine : calibrateRisk(engine, k);
}

/// 화면에 "가장 안전" 으로 보여 줄 패. 고르는 기준은 원래 값([TurnReview.minRiskTile] — 손 안에서 엔진 값이 가장 작은 패)
/// 그대로이고, 원래 값이 그와 같은 손 안 패들(동률 묶음) 중 모두에게 안전패가 있으면 그 패를 보여 준다 — 보정 뒤에는
/// 안전패만 0("안전")이고 나머지 엔진 0 패는 첫 점 값(0.1 ~ 0.2%)이라, 번호 순으로 고르면 "가장 안전: 2통 (0.2%)" 옆에
/// "안전" 패가 있는 모순이 생긴다(11-23). 안전패가 여럿이면 실제 버림을 먼저, 아니면 번호 작은 패. 안전패가 없으면
/// [TurnReview.minRiskTile]. minRiskTile · 사실표는 바꾸지 않는다(복기 에이전트는 원래 값으로 본다).
int? shownSafestTile(TurnReview t) {
  final m = t.minRiskTile;
  final byKind = t.riskByKind;
  if (m == null || byKind == null) return m;
  final w = byKind[m];
  if (w == null) return m;
  final d = t.discard.tile;
  if (byKind[d] == w && t.riskSafeForAll(d)) return d;
  if (t.riskSafeForAll(m)) return m;
  final ties = [
    for (final e in byKind.entries)
      if (e.value == w && t.riskSafeForAll(e.key)) e.key,
  ]..sort();
  return ties.isEmpty ? m : ties.first;
}

/// [shownRisk] 의 글: "안전" 또는 "1.2%".
String shownRiskText(TurnReview t, int tile, double engine) =>
    t.riskSafeForAll(tile) ? riskSafeWord : '${_f1(shownRisk(t, tile, engine))}%';

/// 위협 차례의 위험 줄들: "위협 자리: 동 가 · 이 패 방총 위험 약 1.2%"(모두에게 안전패면 "… · 이 패는 모두에게 안전"),
/// "가장 안전: 5통 (0.2%)"(모두에게 안전패면 "(모두에게 안전)"). 숫자는 보정값. 위협이 없으면 빈 목록.
List<String> engineRiskLines(TurnReview t, {String Function(int seat)? seatLabel}) {
  final r = t.riskOfActual;
  if (r == null) return const [];
  final label = seatLabel ?? (s) => '${s + 1}번 자리';
  final seats = t.riskSeats.map(label).join(', ');
  final out = <String>[
    t.riskSafeForAll(t.discard.tile)
        ? '위협 자리: $seats · 이 패는 모두에게 $riskSafeWord'
        : '위협 자리: $seats · 이 패 방총 위험 약 ${shownRiskText(t, t.discard.tile, r)}',
  ];
  final m = shownSafestTile(t);
  final w = m == null ? null : t.riskByKind?[m];
  if (m != null && w != null) {
    final v = t.riskSafeForAll(m) ? '모두에게 $riskSafeWord' : shownRiskText(t, m, w);
    out.add('가장 안전: ${Tiles.name(m)} ($v)${m == t.discard.tile ? ' — 실제 버림' : ''}');
  }
  return out;
}

/// 엔진 참고값 줄 전부(실제 버림 · 추천 · 위험). 보일 것이 없으면 빈 목록.
List<String> engineLines(TurnReview t, {String Function(int seat)? seatLabel}) => [
      ?engineActualLine(t),
      ?engineRecommendLine(t),
      ...engineRiskLines(t, seatLabel: seatLabel),
    ];

/// 엔진 포함 리뷰를 내는 함수(재생 화면이 받는다 — 시험에서 바꿔 끼움).
typedef EngineReviewRunner = Future<PaifuReview> Function(Paifu p);

/// 엔진 포함 리뷰를 [compute] 로 따로 돌린다. 패보는 JSON 글로 넘기고(Paifu.toJson → fromJson),
/// 결과 [PaifuReview] 는 그대로 받는다(평범한 값 객체라 isolate 사이로 보낼 수 있음).
/// 웹에서는 compute 가 같은 스레드에서 돌아 그동안 화면이 멈춘다 — 부르는 쪽이 첫 화면을 그린 뒤 부른다.
Future<PaifuReview> computeEngineReview(Paifu p) =>
    compute(_engineReviewJob, jsonEncode(p.toJson()), debugLabel: 'paifu-engine-review');

PaifuReview _engineReviewJob(String json) =>
    reviewPaifu(Paifu.fromJson(jsonDecode(json) as Map<String, dynamic>), withEngine: true);

// ── 걸음에 붙이기 ──

/// 한 판의 평가를 재생 걸음에 붙인 것. 평가 건은 hero 가 버린 걸음(`eventIndex + 1`)에 붙는다.
class PaifuReviewIndex {
  final PaifuReview review;

  /// 걸음 → 그 걸음의 버림 평가.
  final Map<int, TurnReview> byStep;

  /// 숫자 있는 차례(graded · forced · defense · complete)가 하나라도 있는가. 없으면 리뷰 위젯을 그리지 않는다.
  final bool hasNumbers;

  /// 등급이 부정확 · 실수 · 큰 실수인 걸음(오름차순).
  final List<int> flaggedSteps;

  /// hero 가 버린 걸음 전부(평가가 붙는 걸음, 오름차순).
  late final List<int> turnSteps = [...byStep.keys]..sort();

  PaifuReviewIndex._(this.review, this.byStep, this.hasNumbers, this.flaggedSteps);

  /// 엔진 없이(빠름) — 재생 화면이 처음 그릴 때.
  factory PaifuReviewIndex.of(Paifu p) => PaifuReviewIndex.fromReview(reviewPaifu(p));

  /// 이미 낸 평가(엔진 포함 등)를 걸음에 붙인다.
  factory PaifuReviewIndex.fromReview(PaifuReview r) {
    final by = {for (final t in r.turns) t.eventIndex + 1: t};
    const numbered = {ReviewStatus.graded, ReviewStatus.forced, ReviewStatus.defense, ReviewStatus.complete};
    const flagged = {ReviewGrade.inaccuracy, ReviewGrade.mistake, ReviewGrade.blunder};
    return PaifuReviewIndex._(
      r,
      by,
      r.turns.any((t) => numbered.contains(t.status)),
      [
        for (final t in r.turns)
          if (flagged.contains(t.grade)) t.eventIndex + 1,
      ]..sort(),
    );
  }

  /// [step] 뒤의 첫 지적 걸음. 뒤에 없으면 처음 것으로 돌아간다. 지적이 없으면 null.
  int? nextFlagged(int step) {
    if (flaggedSteps.isEmpty) return null;
    for (final s in flaggedSteps) {
      if (s > step) return s;
    }
    return flaggedSteps.first;
  }
}

// ── 배지 ──

/// 등급 배지 색(배경, 글자). 채운 배지라 밝은·어두운 테마 모두 같은 짝을 쓴다.
(Color, Color) gradeColors(ReviewGrade g) => switch (g) {
      ReviewGrade.best => (const Color(0xFF2E7D32), Colors.white),
      ReviewGrade.good => (const Color(0xFF7CB342), Colors.black),
      ReviewGrade.inaccuracy => (const Color(0xFFFBC02D), Colors.black),
      ReviewGrade.mistake => (const Color(0xFFF57C00), Colors.black),
      ReviewGrade.blunder => (const Color(0xFFC62828), Colors.white),
    };

/// 배지가 붙는 차례인가: graded(등급) · defense(수비) · complete(화료 형태).
bool hasReviewBadge(TurnReview t) =>
    t.status == ReviewStatus.graded || t.status == ReviewStatus.defense || t.status == ReviewStatus.complete;

/// 작은 배지. [hasReviewBadge] 가 거짓인 차례에는 빈 칸.
class ReviewBadge extends StatelessWidget {
  final TurnReview turn;
  const ReviewBadge(this.turn, {super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final t = turn;
    final grade = t.grade;
    final String label;
    final Color bg, fg;
    if (t.status == ReviewStatus.graded && grade != null) {
      label = reviewGradeName(grade);
      (bg, fg) = gradeColors(grade);
    } else if (t.status == ReviewStatus.defense) {
      (label, bg, fg) = ('수비', scheme.secondaryContainer, scheme.onSecondaryContainer);
    } else if (t.status == ReviewStatus.complete) {
      (label, bg, fg) = ('화료 형태', scheme.tertiaryContainer, scheme.onTertiaryContainer);
    } else {
      return const SizedBox.shrink();
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(4)),
      child: Text(
        label,
        maxLines: 1,
        style: theme.textTheme.labelSmall?.copyWith(color: fg, fontWeight: FontWeight.w700, height: 1.2),
      ),
    );
  }
}


// ── 등급 아이콘(4절) ──

/// 등급 아이콘 글자: 최선 ★ · 좋음 ✓ · 부정확 ?! · 실수 ? · 큰 실수 ??. ★ · ✓ 는 Material 아이콘으로 그린다.
String gradeGlyph(ReviewGrade g) => switch (g) {
      ReviewGrade.best => '★',
      ReviewGrade.good => '✓',
      ReviewGrade.inaccuracy => '?!',
      ReviewGrade.mistake => '?',
      ReviewGrade.blunder => '??',
    };

/// 등급 색 동그라미 + 모양(색만으로 가르지 않음).
class ReviewGradeIcon extends StatelessWidget {
  final ReviewGrade grade;
  final double size;
  const ReviewGradeIcon(this.grade, {super.key, this.size = 20});

  @override
  Widget build(BuildContext context) {
    final (bg, fg) = gradeColors(grade);
    final Widget glyph = switch (grade) {
      ReviewGrade.best => Icon(Icons.star, size: size * 0.72, color: fg),
      ReviewGrade.good => Icon(Icons.check, size: size * 0.72, color: fg),
      _ => Text(
          gradeGlyph(grade),
          textScaler: TextScaler.noScaling,
          style: TextStyle(fontSize: size * 0.5, height: 1, fontWeight: FontWeight.w900, color: fg),
        ),
    };
    return Semantics(
      label: gradeName(grade),
      child: Container(
        width: size,
        height: size,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: bg,
          shape: BoxShape.circle,
          border: Border.all(color: Colors.white, width: size * 0.06),
        ),
        child: glyph,
      ),
    );
  }
}

/// 단계 아이콘: 배패 깃발 · 리치 번개 · 끝 결승기.
IconData stageIcon(ReviewStageKind k) => switch (k) {
      ReviewStageKind.start => Icons.flag_outlined,
      ReviewStageKind.riichi => Icons.bolt,
      ReviewStageKind.end => Icons.sports_score,
    };

// ── 말풍선(3-3 · 3-4) ──

/// 탁자 위 말풍선. 높이가 늘 [heightOf] 라 걸음을 넘겨도 탁자가 흔들리지 않는다(글자 배율만 따름 — 태블릿 키오스크는 1.25배).
/// 줄은 제목 1 + 두 줄 비교 0~2 + 문장 최대 2(7절: 펼치기 전 다섯 줄 이하).
class ReviewBubble extends StatelessWidget {
  /// 다섯 줄(제목 줄 + 네 줄)이 들어가는 높이. 본문 한 줄 = 14 × 1.43(bodyMedium) × 글자 배율.
  static double heightOf(BuildContext context) {
    final line = MediaQuery.textScalerOf(context).scale(14) * 1.43;
    final titleRow = line > 22 ? line : 22.0;
    return (titleRow + 4 * line + 2 + 16 + 2 + 4).ceilToDouble();
  }

  /// 이 말풍선이 보이는 걸음(시험용).
  final int step;
  final Widget? icon;
  final String title;

  /// 구석의 숫자 하나("−5장" · "샹텐 후퇴"). null 이면 비움.
  final String? corner;
  final List<String> lines;
  final String? sentence;

  /// 내 버림이 아닌 걸음: 한 줄 회색.
  final bool muted;

  const ReviewBubble({
    super.key,
    required this.step,
    this.icon,
    required this.title,
    this.corner,
    this.lines = const [],
    this.sentence,
    this.muted = false,
  });

  /// 내 버림 걸음. [sentence] 를 주면(LLM 해설 등) 코드 문장 대신 그것을 쓴다.
  factory ReviewBubble.turn(TurnReview t, {Key? key, required int step, String? sentence}) => ReviewBubble(
        key: key,
        step: step,
        icon: t.status == ReviewStatus.graded && t.grade != null ? ReviewGradeIcon(t.grade!, size: 22) : null,
        title: reviewTitle(t),
        corner: reviewCorner(t),
        lines: reviewCompareLines(t),
        sentence: sentence ?? reviewSentence(t),
      );

  /// 단계 걸음.
  factory ReviewBubble.stage(ReviewStage s, {Key? key, required int step, required String sentence}) => ReviewBubble(
        key: key,
        step: step,
        icon: Icon(stageIcon(s.kind), size: 22),
        title: stageName(s.kind),
        sentence: sentence,
      );

  /// 남의 걸음 · 뽑는 걸음: 한 줄만 회색.
  factory ReviewBubble.plain(String text, {Key? key, required int step}) =>
      ReviewBubble(key: key, step: step, title: text, muted: true);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final body = theme.textTheme.bodyMedium;
    final muteStyle = body?.copyWith(color: scheme.onSurfaceVariant);
    final c = corner;
    return Container(
      key: const ValueKey('paifu-bubble'),
      height: heightOf(context),
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: scheme.outlineVariant),
      ),
      // 글꼴이 달라 한 줄이 넘쳐도 오류 대신 잘라 보인다(높이는 그대로).
      child: SingleChildScrollView(
        physics: const NeverScrollableScrollPhysics(),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                if (icon != null) ...[icon!, const SizedBox(width: 8)],
                Expanded(
                  child: Text(
                    title,
                    key: const ValueKey('paifu-bubble-title'),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: muted ? muteStyle : theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
                  ),
                ),
                if (c != null)
                  Container(
                    key: const ValueKey('paifu-bubble-corner'),
                    margin: const EdgeInsets.only(left: 6),
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(color: scheme.inverseSurface, borderRadius: BorderRadius.circular(6)),
                    child: Text(c,
                        style: theme.textTheme.labelMedium
                            ?.copyWith(color: scheme.onInverseSurface, fontWeight: FontWeight.w700)),
                  ),
              ],
            ),
            for (final (i, l) in lines.indexed)
              Text(l,
                  key: ValueKey('paifu-bubble-line-$i'),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: body?.copyWith(fontWeight: FontWeight.w500)),
            if (sentence != null)
              Padding(
                padding: const EdgeInsets.only(top: 2),
                child: Text(
                  sentence!,
                  key: const ValueKey('paifu-bubble-sentence'),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: body,
                ),
              ),
          ],
        ),
      ),
    );
  }
}

// ── 수 띠(3-5) ──

/// 띠의 한 칸. [grade] 는 등급이 매겨진 내 버림에만.
class StripEntry {
  final String label;
  final bool mine;
  final ReviewGrade? grade;
  const StripEntry(this.label, {this.mine = false, this.grade});
}

/// 띠의 칸 위젯(시험에서 지금 걸음을 찾을 때 [current] 를 본다).
class ReviewStripItem extends StatelessWidget {
  final int step;
  final StripEntry entry;
  final bool current;
  final VoidCallback onTap;
  const ReviewStripItem({super.key, required this.step, required this.entry, required this.current, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final e = entry;
    final style = theme.textTheme.labelMedium?.copyWith(
      fontWeight: e.mine ? FontWeight.w700 : FontWeight.w400,
      color: e.mine ? scheme.onSurface : scheme.onSurfaceVariant.withAlpha(160),
    );
    return InkWell(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          color: current ? scheme.primary.withAlpha(30) : null,
          border: Border(bottom: BorderSide(color: current ? scheme.primary : Colors.transparent, width: 3)),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 4),
        alignment: Alignment.center,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Flexible(child: Text(e.label, maxLines: 1, overflow: TextOverflow.clip, style: style)),
            if (e.grade != null) ...[const SizedBox(width: 3), ReviewGradeIcon(e.grade!, size: 16)],
          ],
        ),
      ),
    );
  }
}

/// 아래 가로 수 띠: ‹ [걸음들] › + 단계 아이콘 + "다음 지적". 지금 걸음은 가운데로 굴린다.
class ReviewMoveStrip extends StatefulWidget {
  static const itemWidth = 74.0;
  static const barHeight = 44.0;

  final List<StripEntry> entries;
  final int step;
  final ValueChanged<int> onGo;
  final List<ReviewStage> stages;
  final ValueChanged<ReviewStage> onStage;

  /// "다음 지적"(null 이면 비활성).
  final VoidCallback? onNextFlag;

  const ReviewMoveStrip({
    super.key,
    required this.entries,
    required this.step,
    required this.onGo,
    this.stages = const [],
    required this.onStage,
    this.onNextFlag,
  });

  @override
  State<ReviewMoveStrip> createState() => _ReviewMoveStripState();
}

class _ReviewMoveStripState extends State<ReviewMoveStrip> {
  final _scroll = ScrollController();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _center(animate: false));
  }

  @override
  void didUpdateWidget(covariant ReviewMoveStrip old) {
    super.didUpdateWidget(old);
    if (old.step != widget.step) WidgetsBinding.instance.addPostFrameCallback((_) => _center());
  }

  void _center({bool animate = true}) {
    if (!mounted || !_scroll.hasClients) return;
    final pos = _scroll.position;
    final target = (widget.step * ReviewMoveStrip.itemWidth + ReviewMoveStrip.itemWidth / 2 - pos.viewportDimension / 2)
        .clamp(0.0, pos.maxScrollExtent);
    if (animate) {
      _scroll.animateTo(target, duration: const Duration(milliseconds: 150), curve: Curves.easeOut);
    } else {
      _scroll.jumpTo(target);
    }
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final w = widget;
    final n = w.entries.length;
    // 단계 아이콘은 종류마다 하나(같은 종류가 둘이면 앞의 것).
    final byKind = <ReviewStageKind, ReviewStage>{};
    for (final s in w.stages) {
      byKind.putIfAbsent(s.kind, () => s);
    }
    const dense = VisualDensity(horizontal: -4, vertical: -4);
    return SizedBox(
      key: const ValueKey('paifu-strip'),
      height: ReviewMoveStrip.barHeight,
      child: Row(
        children: [
          IconButton(
            key: const ValueKey('paifu-strip-prev'),
            tooltip: '이전',
            visualDensity: dense,
            icon: const Icon(Icons.chevron_left),
            onPressed: w.step > 0 ? () => w.onGo(w.step - 1) : null,
          ),
          Expanded(
            child: ListView.builder(
              controller: _scroll,
              scrollDirection: Axis.horizontal,
              itemExtent: ReviewMoveStrip.itemWidth,
              itemCount: n,
              itemBuilder: (context, i) => ReviewStripItem(
                key: ValueKey('paifu-strip-$i'),
                step: i,
                entry: w.entries[i],
                current: i == w.step,
                onTap: () => w.onGo(i),
              ),
            ),
          ),
          IconButton(
            key: const ValueKey('paifu-strip-next'),
            tooltip: '다음 걸음',
            visualDensity: dense,
            icon: const Icon(Icons.chevron_right),
            onPressed: w.step < n - 1 ? () => w.onGo(w.step + 1) : null,
          ),
          for (final k in ReviewStageKind.values)
            if (byKind[k] != null)
              IconButton(
                key: ValueKey('paifu-stage-${k.name}'),
                tooltip: stageName(k),
                visualDensity: dense,
                iconSize: 20,
                icon: Icon(stageIcon(k)),
                onPressed: () => w.onStage(byKind[k]!),
              ),
          IconButton(
            key: const ValueKey('paifu-review-next'),
            tooltip: '다음 지적',
            visualDensity: dense,
            iconSize: 20,
            icon: const Icon(Icons.flag),
            onPressed: w.onNextFlag,
          ),
        ],
      ),
    );
  }
}

// ── 펼침: 후보(3-9) ──

/// 후보 목록: 위에서 3개 + 실제 버림이 그 안에 없으면 실제 버림. 패 · 샹텐 · 장수와 "실제" · "최선" 표시.
class ReviewCandidates extends StatelessWidget {
  final TurnReview? turn;
  const ReviewCandidates(this.turn, {super.key});

  static List<DiscardOption> candidatesOf(TurnReview t) {
    final top = t.options.take(3).toList();
    final a = t.actual;
    if (a != null && !top.any((o) => o.tile == a.tile)) top.add(a);
    return top;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final t = turn;
    final small = theme.textTheme.bodySmall;
    final head = Text('후보', style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700));
    if (t == null || t.options.isEmpty) {
      return Column(
        key: const ValueKey('paifu-fold-candidates'),
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [head, Text('이 걸음은 후보가 없습니다', style: small?.copyWith(color: scheme.onSurfaceVariant))],
      );
    }
    final bests = bestTiles(t).toSet();
    return Column(
      key: const ValueKey('paifu-fold-candidates'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        head,
        for (final o in candidatesOf(t))
          Padding(
            padding: const EdgeInsets.only(top: 3),
            child: Row(
              children: [
                TileView(o.tile,
                    red: o.tile == t.discard.tile && t.discard.red, width: 20, highlighted: o.tile == t.discard.tile),
                const SizedBox(width: 6),
                Flexible(
                  child: Text(
                    '${shantenText(o.shanten)} · ${ukeireWord(o.shanten)} ${o.ukeire.total}장',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: small?.copyWith(fontWeight: o.tile == t.discard.tile ? FontWeight.w700 : FontWeight.w400),
                  ),
                ),
                if (o.tile == t.discard.tile)
                  Padding(
                    padding: const EdgeInsets.only(left: 6),
                    child: Text('실제', style: small?.copyWith(color: scheme.primary, fontWeight: FontWeight.w700)),
                  ),
                if (bests.contains(o.tile))
                  Padding(
                    padding: const EdgeInsets.only(left: 6),
                    child: Text('최선',
                        style: small?.copyWith(color: const Color(0xFF2E7D32), fontWeight: FontWeight.w700)),
                  ),
              ],
            ),
          ),
      ],
    );
  }
}

// ── 펼침: 참고값(3-9) ──

/// 참고값 제목(공개 도구 이름 + 등급과 따로 셈).
const engineFoldTitle = '참고값 (공개 마작 도구 mahjong-helper 계산 · 등급과 따로 셈)';

/// 참고값 세 줄: 점수 · 화료까지 본 추천 / 이 패 방총 위험(위협이 있을 때 — 보정값, 모두에게 안전패면 "안전") /
/// 가장 안전한 패(위협이 있을 때).
/// 추천은 샹텐을 지키는 후보 중 엔진 1위(후퇴 권장은 보이지 않음 — [engineRecommendLine] 과 같은 고름).
/// 그 패가 말풍선의 최선(동률 포함)과 같으면 "말풍선의 최선과 같음". 엔진 칸이 없으면 빈 목록.
List<String> engineFoldLines(TurnReview t, {String Function(int seat)? seatLabel}) {
  final out = <String>[];
  final l = t.mh;
  if (l != null) {
    RankedDiscard? top;
    for (final d in l) {
      if (!d.isBackward) {
        top = d;
        break;
      }
    }
    if (top != null) {
      final note = bestTiles(t).contains(top.tile)
          ? ' — 말풍선의 최선과 같음'
          : (top.tile == t.discard.tile ? ' — 실제 버림과 같음' : '');
      out.add('점수 · 화료까지 본 추천: ${Tiles.name(top.tile)}$note');
    }
  }
  final r = t.riskOfActual;
  if (r != null) {
    final label = seatLabel ?? (s) => '${s + 1}번 자리';
    final v = t.riskSafeForAll(t.discard.tile) ? riskSafeWord : '약 ${shownRiskText(t, t.discard.tile, r)}';
    out.add('이 패 방총 위험: $v (위협: ${t.riskSeats.map(label).join(', ')})');
    final m = shownSafestTile(t);
    if (m != null) out.add('가장 안전한 패: ${Tiles.name(m)}${m == t.discard.tile ? ' — 실제 버림' : ''}');
  }
  return out;
}

/// "참고값" 펼침: 제목(누르면 도움말) + [engineFoldLines] + "자세히"(후보 표). 계산 중이면 한 줄.
class EngineReviewFold extends StatefulWidget {
  final TurnReview? turn;
  final EngineReviewStatus engine;
  final String Function(int seat)? seatLabel;
  const EngineReviewFold({super.key, required this.turn, required this.engine, this.seatLabel});

  @override
  State<EngineReviewFold> createState() => _EngineReviewFoldState();
}

class _EngineReviewFoldState extends State<EngineReviewFold> {
  bool _detail = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final small = theme.textTheme.bodySmall;
    final muted = small?.copyWith(color: scheme.onSurfaceVariant);
    final t = widget.turn;
    final children = <Widget>[
      Tooltip(
        message: engineReviewTooltip,
        triggerMode: TooltipTriggerMode.tap,
        child: Text.rich(
          TextSpan(children: [
            TextSpan(text: engineFoldTitle, style: small?.copyWith(fontWeight: FontWeight.w700)),
            WidgetSpan(
              alignment: PlaceholderAlignment.middle,
              child: Padding(
                padding: const EdgeInsets.only(left: 2),
                child: Icon(Icons.info_outline, size: 14, color: scheme.onSurfaceVariant),
              ),
            ),
          ]),
        ),
      ),
    ];
    var lines = const <String>[];
    if (t == null || t.status == ReviewStatus.forced) {
      children.add(Text('이 걸음은 참고값이 없습니다', style: muted));
    } else {
      switch (widget.engine) {
        case EngineReviewStatus.pending:
          children.add(Text(engineReviewPending, key: const ValueKey('paifu-review-engine-pending'), style: muted));
        case EngineReviewStatus.off:
        case EngineReviewStatus.failed:
          children.add(Text('이 걸음은 참고값이 없습니다', style: muted));
        case EngineReviewStatus.ready:
          lines = engineFoldLines(t, seatLabel: widget.seatLabel);
          if (lines.isEmpty) children.add(Text('이 걸음은 참고값이 없습니다', style: muted));
      }
    }
    for (final l in lines) {
      children.add(Padding(padding: const EdgeInsets.only(top: 2), child: Text(l, style: small)));
    }
    final mh = t?.mh;
    if (t != null && lines.isNotEmpty && mh != null && mh.isNotEmpty) {
      children.add(Align(
        alignment: Alignment.centerRight,
        child: TextButton(
          key: const ValueKey('paifu-engine-detail'),
          style: TextButton.styleFrom(visualDensity: VisualDensity.compact),
          onPressed: () => setState(() => _detail = !_detail),
          child: Text(_detail ? '자세히 접기' : '자세히'),
        ),
      ));
      if (_detail) children.add(EngineCandidateTable(t));
    }
    return Column(
      key: const ValueKey('paifu-review-engine'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: children,
    );
  }
}

/// "자세히": 엔진 후보마다 한 줄인 표(숙련자용). 열은 버릴 패 · 샹텐 · 유효패 · 개량 뒤 평균 · 화료율(텐파이 후보가
/// 있을 때) · 이 패 방총 위험(위협이 있을 때 — 보정값, 모두에게 안전패면 "안전") · 국수지. AI 선택 확률 열은 없다.
class EngineCandidateTable extends StatelessWidget {
  final TurnReview turn;
  const EngineCandidateTable(this.turn, {super.key});

  /// 머리 줄(시험용).
  static List<String> headOf(TurnReview t) {
    final list = t.mh ?? const <RankedDiscard>[];
    return [
      '버릴 패',
      '샹텐',
      '유효패',
      '개량 뒤 평균',
      if (list.any((d) => d.shanten <= 0)) '화료율',
      if (t.riskByKind != null) '방총 위험',
      '국수지',
    ];
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final small = theme.textTheme.bodySmall;
    final bold = small?.copyWith(fontWeight: FontWeight.w700);
    final t = turn;
    final list = t.mh ?? const <RankedDiscard>[];
    final tenpai = list.any((d) => d.shanten <= 0);
    final risk = t.riskByKind;
    String num1(double x) => x.isFinite ? _f1(x) : '—';
    Widget cell(String s, {TextStyle? style}) =>
        Padding(padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2), child: Text(s, style: style ?? small));
    return SingleChildScrollView(
      key: const ValueKey('paifu-engine-table'),
      scrollDirection: Axis.horizontal,
      child: Table(
        defaultColumnWidth: const IntrinsicColumnWidth(),
        children: [
          TableRow(children: [for (final h in headOf(t)) cell(h, style: bold)]),
          for (final d in list)
            TableRow(
              children: [
                cell('${Tiles.name(d.tile)}${d.tile == t.discard.tile ? ' (실제)' : ''}',
                    style: d.tile == t.discard.tile ? bold : null),
                cell('${shantenText(d.shanten)}${d.isBackward ? ' (후퇴)' : ''}'),
                cell('${d.waitsCount}장'),
                cell(num1(d.avgImproveWaitsCount)),
                if (tenpai) cell(d.shanten <= 0 ? '${num1(d.agariRate)}%' : '—'),
                if (risk != null) cell(risk[d.tile] == null ? '—' : shownRiskText(t, d.tile, risk[d.tile]!)),
                cell(d.roundPoint.isFinite && d.roundPoint > 0 ? '${d.roundPoint.round()}' : '—'),
              ],
            ),
        ],
      ),
    );
  }
}

// ── 최선 보기: 손패 위 막대(3-9) ──

/// 손패 한 종류 위 막대. [frac] 은 샹텐을 지키는 후보 중 가장 많은 유효패를 1 로 둔 비율(뒤로 가는 후보는 0).
class HandBar {
  final int tile;
  final int total;
  final double frac;

  /// 최선 후보(동률 모두).
  final bool best;

  /// 실제로 버린 패.
  final bool actual;

  /// 샹텐이 뒤로 가는 후보: 막대 대신 회색 점.
  final bool backward;

  const HandBar({
    required this.tile,
    required this.total,
    required this.frac,
    required this.best,
    required this.actual,
    required this.backward,
  });
}

/// 차례 하나의 막대들(패 종류 → 막대). 숫자 없는 차례는 빈 맵.
Map<int, HandBar> handBars(TurnReview t) {
  final b = t.best;
  if (b == null || t.options.isEmpty) return const {};
  var max = 0;
  for (final o in t.options) {
    if (o.shanten == b.shanten && o.ukeire.total > max) max = o.ukeire.total;
  }
  final bests = bestTiles(t).toSet();
  return {
    for (final o in t.options)
      o.tile: HandBar(
        tile: o.tile,
        total: o.ukeire.total,
        frac: o.shanten > b.shanten || max == 0 ? 0 : o.ukeire.total / max,
        best: bests.contains(o.tile),
        actual: o.tile == t.discard.tile,
        backward: o.shanten > b.shanten,
      ),
  };
}

/// 버리기 전 손패 줄: [row](손패 기록 순서, 적5 표시 그대로) + 떼어 둔 뽑은 패 [drawn] + 흐리게 되돌린 버림의 자리 [ghost]
/// (row 의 인덱스, −1 이면 [drawn]).
class BeforeHand {
  final List<PaifuTile> row;
  final PaifuTile? drawn;
  final int ghost;
  const BeforeHand(this.row, this.drawn, this.ghost);

  /// 그리는 순서대로 전부(row 다음 drawn).
  List<PaifuTile> get all => [...row, ?drawn];
}

/// 차례 [t] 의 버리기 전 손패 줄. 평가는 버린 뒤 걸음에 붙어 있어 그때 탁자 손패는 13장이라, 최선 보기 때는 이것으로
/// 바꿔 그린다. 줄은 직전 뽑기 사건(손패 + 뽑은 패) → 직전 울기 사건 → 버림 사건(버린 뒤 손패 + 버린 패를 오른쪽에)
/// 순으로 찾고, 적5 는 그 손패 기록의 표시를 그대로 쓴다. 기록 줄이 [TurnReview.before] 와 맞지 않으면 before 를 패 번호
/// 순으로 펴고 적5 는 버림 사건 쪽 기록에서 옮긴다. 숫자 없는 차례는 null.
BeforeHand? beforeHandOf(Paifu p, TurnReview t) {
  final before = t.before;
  if (before == null || t.eventIndex < 0 || t.eventIndex >= p.events.length) return null;
  final e = p.events[t.eventIndex];
  final d = t.discard;
  PaifuEvent? prev;
  for (var j = t.eventIndex - 1; j >= 0; j--) {
    if (p.events[j].seat == p.hero) {
      prev = p.events[j];
      break;
    }
  }
  List<PaifuTile>? row;
  PaifuTile? drawn;
  var rightIsDiscard = false;
  if (prev != null && prev.type == PaifuEventType.draw && prev.hand != null && prev.tile != null) {
    row = prev.hand;
    drawn = prev.tile;
  } else if (prev != null && prev.type == PaifuEventType.call && prev.hand != null) {
    row = prev.hand;
  } else if (e.hand != null) {
    row = e.hand;
    drawn = d;
    rightIsDiscard = true;
  }

  bool matches(List<PaifuTile> ts) {
    final c = List<int>.filled(Tiles.count, 0);
    for (final x in ts) {
      if (x.tile < 0 || x.tile >= Tiles.count) return false;
      c[x.tile]++;
    }
    for (var k = 0; k < Tiles.count; k++) {
      if (c[k] != before[k]) return false;
    }
    return true;
  }

  if (row == null || !matches([...row, ?drawn])) {
    // 기록 줄을 못 쓰면 34칸을 펴고, 적5 는 버린 뒤 손패 + 버린 패에서 옮긴다.
    final reds = <int>{
      for (final x in [...?e.hand, d])
        if (x.red) x.tile,
    };
    final flat = <PaifuTile>[
      for (var k = 0; k < Tiles.count; k++)
        for (var n = 0; n < before[k]; n++) PaifuTile(k, red: n == 0 && reds.contains(k)),
    ];
    var g = flat.indexWhere((x) => x == d);
    if (g < 0) g = flat.indexWhere((x) => x.tile == d.tile);
    return BeforeHand(flat, null, g);
  }

  if (rightIsDiscard) return BeforeHand(row, drawn, -1);
  // 버린 패의 자리: 쯔모기리(또는 쯔모기리 여부를 모르고 뽑은 패와 같음)면 뽑은 패, 아니면 손패 줄에서 같은 패.
  final dr = drawn;
  if (dr != null && dr.tile == d.tile && (e.tsumogiri == true || (e.tsumogiri == null && dr == d))) {
    return BeforeHand(row, drawn, -1);
  }
  var g = row.indexWhere((x) => x == d);
  if (g < 0) g = row.indexWhere((x) => x.tile == d.tile);
  if (g < 0 && dr != null && dr.tile == d.tile) return BeforeHand(row, drawn, -1);
  return BeforeHand(row, drawn, g);
}
