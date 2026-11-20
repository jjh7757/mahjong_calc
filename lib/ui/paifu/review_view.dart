/// 패보 재생 화면의 버림 평가(리뷰): 사건 목록 배지, 지금 걸음의 평가 카드, 판 요약 줄.
///
/// 계산은 [reviewPaifu] 가 하고, 여기서는 걸음에 붙이고 문구·그림으로 바꾸기만 한다.
/// mahjong-helper 엔진 참고값은 한 판에 수 초가 걸려 [computeEngineReview] 로 뒤에서 낸 뒤 카드에 붙인다.
library;

import 'dart:convert';

import 'package:flutter/foundation.dart' show compute;
import 'package:flutter/material.dart';

import '../../engine/efficiency.dart';
import '../../engine/tile.dart';
import '../../paifu/paifu.dart';
import '../../paifu/paifu_review.dart';
import '../tile_view.dart';

// ── 문구 ──

String reviewGradeName(ReviewGrade g) => switch (g) {
      ReviewGrade.best => '최선',
      ReviewGrade.good => '좋음',
      ReviewGrade.inaccuracy => '부정확',
      ReviewGrade.mistake => '실수',
      ReviewGrade.blunder => '큰 실수',
    };

/// −1 화료 형태 · 0 텐파이 · n n샹텐.
String shantenLabel(int s) => switch (s) {
      < 0 => '화료 형태',
      0 => '텐파이',
      _ => '$s샹텐',
    };

String _tileName(PaifuTile t) => t.red ? '적${Tiles.name(t.tile)}' : Tiles.name(t.tile);

/// "1샹텐 · 유효패 10장(5종)" / "텐파이 · 대기 4장(2종)".
String optionSummary(DiscardOption o) =>
    '${shantenLabel(o.shanten)} · ${o.shanten <= 0 ? '대기' : '유효패'} ${o.ukeire.total}장(${o.ukeire.liveKinds}종)';

/// "2통 버림 → 1샹텐 · 유효패 10장(5종)". 숫자 없는 차례는 버린 패만.
String actualLine(TurnReview t) {
  final a = t.actual;
  return a == null ? '${_tileName(t.discard)} 버림' : '${_tileName(t.discard)} 버림 → ${optionSummary(a)}';
}

/// 최선과 차이. 실제가 최선(rank 1)이거나 숫자가 없으면 null.
String? bestLine(TurnReview t) {
  final b = t.best;
  final rank = t.rank;
  if (b == null || rank == null || rank <= 1) return null;
  final name = Tiles.name(b.tile);
  if ((t.shantenLoss ?? 0) > 0) {
    return '최선은 $name → ${shantenLabel(b.shanten)} · ${b.shanten <= 0 ? '대기' : '유효패'} ${b.ukeire.total}장';
  }
  return '최선은 $name → ${b.ukeire.total}장 (${t.ukeireLoss}장 적음)';
}

/// 수비 차례의 현물 줄.
String genbutsuLine(TurnReview t) {
  final mine = t.genbutsu == true ? '버린 패는 현물' : '버린 패는 현물이 아님';
  final safe = t.safeTiles.isEmpty ? '손 안에 현물 없음' : '손 안 현물: ${t.safeTiles.map(Tiles.name).join(' ')}';
  return '$mine · $safe';
}

/// 판 요약: "패효율 80 · 최선 5 · 실수 1 · 큰 실수 1".
String reviewSummaryLine(PaifuReview r) {
  final pct = r.efficiencyPct;
  return [
    pct == null ? '패효율 —' : '패효율 $pct',
    for (final g in ReviewGrade.values)
      if (r.gradeCount(g) > 0) '${reviewGradeName(g)} ${r.gradeCount(g)}',
  ].join(' · ');
}

const _noReviewText = {
  ReviewStatus.unknownHand: '이 순은 손패 기록이 없어 평가하지 않음',
  ReviewStatus.inconsistent: '이 순은 손패 기록이 앞뒤가 안 맞아 평가하지 않음',
};

// ── mahjong-helper 엔진 참고값 ──
//
// 등급·기존 문구와 따로, 카드 아래 작은 묶음으로만 보인다. 후퇴 권장(mhRecommendBackward)은 보이지 않는다 —
// 강한 AI 와 맞대 보니 6번 중 0번 맞았다(11-20). 그래서 추천은 「샹텐을 지키는 후보 중 엔진 1위」.
// 카드(ReviewCard) 안이 아니라 그 아래 상자([EngineReviewBox])에 그린다.

const engineReviewTitle = '참고값 (mahjong-helper 기준)';
const engineReviewNote = '화료율 · 위험도는 통계표 어림';
const engineReviewPending = '참고값 계산 중…';
const engineReviewTooltip = '화료율과 방총 위험은 mahjong-helper 의 통계표로 낸 어림값입니다. '
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

/// 위협 차례의 위험 줄들: "위협 자리: 동 가 · 이 패 방총 위험 약 1.7%", "가장 안전: 5통 (0.9%)". 위협이 없으면 빈 목록.
List<String> engineRiskLines(TurnReview t, {String Function(int seat)? seatLabel}) {
  final r = t.riskOfActual;
  if (r == null) return const [];
  final label = seatLabel ?? (s) => '${s + 1}번 자리';
  final out = <String>[
    '위협 자리: ${t.riskSeats.map(label).join(', ')} · 이 패 방총 위험 약 ${_f1(r)}%',
  ];
  final m = t.minRiskTile;
  final w = m == null ? null : t.riskByKind?[m];
  if (m != null && w != null) {
    out.add('가장 안전: ${Tiles.name(m)} (${_f1(w)}%)${m == t.discard.tile ? ' — 실제 버림' : ''}');
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
(Color, Color) _gradeColors(ReviewGrade g) => switch (g) {
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
      (bg, fg) = _gradeColors(grade);
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

// ── 패널: 요약 줄 + 카드 ──

/// 패널에 들어가는 리뷰 묶음: 요약 줄(늘) + 지금 걸음의 카드 또는 "평가하지 않음" 줄.
/// 숫자 있는 차례가 있는 판에서만 쓴다([PaifuReviewIndex.hasNumbers]).
class PaifuReviewPanel extends StatelessWidget {
  final PaifuReviewIndex index;
  final int step;

  /// "다음 지적" 으로 갈 걸음을 받는다.
  final ValueChanged<int> onGo;

  /// 엔진 참고값 계산 상태(카드에 넘긴다).
  final EngineReviewStatus engine;

  /// 위협 자리 표시(예: "동 가"). 없으면 "n번 자리".
  final String Function(int seat)? seatLabel;

  const PaifuReviewPanel({
    super.key,
    required this.index,
    required this.step,
    required this.onGo,
    this.engine = EngineReviewStatus.off,
    this.seatLabel,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final turn = index.byStep[step];
    final next = index.nextFlagged(step);
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            key: const ValueKey('paifu-review-summary'),
            children: [
              Expanded(
                child: Text(
                  reviewSummaryLine(index.review),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
                ),
              ),
              TextButton.icon(
                key: const ValueKey('paifu-review-next'),
                style: TextButton.styleFrom(visualDensity: VisualDensity.compact),
                icon: const Icon(Icons.flag_outlined, size: 18),
                label: const Text('다음 지적'),
                onPressed: next == null ? null : () => onGo(next),
              ),
            ],
          ),
          if (turn != null && _noReviewText[turn.status] != null)
            Text(
              _noReviewText[turn.status]!,
              key: const ValueKey('paifu-review-none'),
              style: theme.textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
            )
          else if (turn != null)
            ReviewCard(turn, key: const ValueKey('paifu-review-card')),
          if (turn != null && _noReviewText[turn.status] == null)
            EngineReviewBox(turn, engine: engine, seatLabel: seatLabel),
        ],
      ),
    );
  }
}

/// 지금 걸음의 평가 카드. forced 는 한 줄, 그 밖(graded · defense · complete)은 머리 · 최선과 차이 · 상황 · 후보.
class ReviewCard extends StatelessWidget {
  final TurnReview turn;
  const ReviewCard(this.turn, {super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final t = turn;
    final small = theme.textTheme.bodySmall;
    final muted = small?.copyWith(color: scheme.onSurfaceVariant);

    final List<Widget> lines;
    if (t.status == ReviewStatus.forced) {
      lines = [Text('리치 중 — 고를 수 없는 버림', style: theme.textTheme.bodyMedium)];
    } else {
      final best = bestLine(t);
      lines = [
        Row(
          children: [
            if (hasReviewBadge(t)) ...[ReviewBadge(t), const SizedBox(width: 6)],
            Expanded(
              child: Text(
                actualLine(t),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
              ),
            ),
          ],
        ),
        if (best != null) Padding(padding: const EdgeInsets.only(top: 2), child: Text(best, style: small)),
        if (t.status == ReviewStatus.defense) ...[
          Text('다른 자리 리치 중 — 패효율 등급은 매기지 않음', style: muted),
          Text(genbutsuLine(t), style: small),
        ],
        if (t.status == ReviewStatus.complete)
          Text('화료 형태에서 버림 — 화료하지 않은 까닭(역 없음 등)은 판단하지 않음', style: muted),
        const SizedBox(height: 4),
        for (final o in _candidates(t)) _option(context, t, o),
      ];
    }
    return Container(
      margin: const EdgeInsets.only(top: 4),
      padding: const EdgeInsets.fromLTRB(8, 6, 8, 6),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, mainAxisSize: MainAxisSize.min, children: lines),
    );
  }

  /// 위에서 3개 + 실제 버림이 그 안에 없으면 실제 버림.
  static List<DiscardOption> _candidates(TurnReview t) {
    final top = t.options.take(3).toList();
    final a = t.actual;
    if (a != null && !top.any((o) => o.tile == a.tile)) top.add(a);
    return top;
  }

  Widget _option(BuildContext context, TurnReview t, DiscardOption o) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final isActual = o.tile == t.discard.tile;
    final style = theme.textTheme.bodySmall?.copyWith(fontWeight: isActual ? FontWeight.w700 : FontWeight.w400);
    return Padding(
      padding: const EdgeInsets.only(top: 2),
      child: Row(
        children: [
          TileView(o.tile, red: isActual && t.discard.red, width: 18, highlighted: isActual),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              '${shantenLabel(o.shanten)} · ${o.ukeire.total}장',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: style,
            ),
          ),
          if (isActual)
            Padding(
              padding: const EdgeInsets.only(left: 6),
              child: Text('실제', style: style?.copyWith(color: scheme.primary)),
            ),
        ],
      ),
    );
  }
}

/// 카드 바로 아래 엔진 참고값 묶음(카드와 같은 꾸밈의 작은 상자). [engine] 이 pending 이면 "계산 중" 한 줄,
/// ready 면 제목(통계표 어림 안내, 누르면 설명) + 숫자 줄, off · failed 면 없음.
/// forced(리치 뒤)는 고를 수 없는 버림이라 붙이지 않는다. 패는 글자로만(카드의 「최선은 …」 줄과 같은 이름).
/// 카드 안이 아니라 아래에 두는 까닭: 폰 세로(400×800)에선 위 칸 스크롤 창이 200px 남짓이라 카드 안에 넣으면
/// 카드 하나가 창보다 커진다 — 카드는 그대로 한눈에 보이고, 참고값은 조금 더 스크롤해서 본다.
class EngineReviewBox extends StatelessWidget {
  final TurnReview turn;
  final EngineReviewStatus engine;
  final String Function(int seat)? seatLabel;
  const EngineReviewBox(this.turn, {super.key, required this.engine, this.seatLabel});

  @override
  Widget build(BuildContext context) {
    final t = turn;
    if (t.status == ReviewStatus.forced) return const SizedBox.shrink();
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final small = theme.textTheme.bodySmall;
    final muted = small?.copyWith(color: scheme.onSurfaceVariant);
    final Widget body;
    final Key key;
    switch (engine) {
      case EngineReviewStatus.off:
      case EngineReviewStatus.failed:
        return const SizedBox.shrink();
      case EngineReviewStatus.pending:
        key = const ValueKey('paifu-review-engine-pending');
        body = Text(engineReviewPending, style: muted);
      case EngineReviewStatus.ready:
        final lines = engineLines(t, seatLabel: seatLabel);
        if (lines.isEmpty) return const SizedBox.shrink();
        key = const ValueKey('paifu-review-engine');
        body = Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            Tooltip(
              message: engineReviewTooltip,
              triggerMode: TooltipTriggerMode.tap,
              child: Text.rich(
                TextSpan(children: [
                  TextSpan(text: engineReviewTitle, style: small?.copyWith(fontWeight: FontWeight.w600)),
                  TextSpan(text: ' · $engineReviewNote', style: muted),
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
            for (final l in lines) Padding(padding: const EdgeInsets.only(top: 2), child: Text(l, style: small)),
          ],
        );
    }
    return Container(
      key: key,
      margin: const EdgeInsets.only(top: 4),
      padding: const EdgeInsets.fromLTRB(8, 6, 8, 6),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: body,
    );
  }
}
