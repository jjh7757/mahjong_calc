/// 패보 판 요약 화면(설계서 `docs/paifu_review_ui_design_1121.md` 3-1): 패효율 큰 숫자, 등급별 개수 세로 표,
/// 평가 안 함 네 묶음, 배울 장면(최대 3), 판 전체 질문 칩(묻는 곳이 있을 때만), "복기 시작" · "처음부터 보기".
///
/// 손패가 있는 패보를 열면 재생 화면보다 먼저 보인다(9절 ②). 계산은 [PaifuReview] 의 getter 가 하고 여기서는 그리기만 한다.
library;

import 'package:flutter/material.dart';

import '../../paifu/paifu.dart';
import '../../paifu/paifu_review.dart';
import '../../paifu/review_sentence.dart';
import 'review_view.dart';

/// 판 요약 화면의 몸통(앱 막대는 재생 화면 쪽이 그린다).
class PaifuReviewSummary extends StatelessWidget {
  final Paifu paifu;
  final PaifuReview review;

  /// 머리 줄 끝의 결과("론" · "쯔모" · "유국"). 빈 글이면 적지 않는다.
  final String result;

  /// 등급 문턱(도움말 "임시 기준" 줄에 그대로 적는다).
  final ReviewThresholds thresholds;

  /// 복기 시작(첫 걸음 + 배패 말풍선부터).
  final VoidCallback onStart;

  /// 처음부터 보기(말풍선 없는 재생 화면).
  final VoidCallback onPlay;

  /// 배울 장면을 눌렀을 때: 그 걸음(버린 뒤 걸음 = eventIndex + 1).
  final ValueChanged<int> onLesson;

  /// 판 전체 질문(복기 질문 창의 추천 질문과 같은 글). [onAsk] 가 있고 비어 있지 않을 때만 칩 줄을 그린다.
  final List<String> questions;

  /// 질문 칩을 눌렀을 때: 그 글(복기 화면의 질문 창에서 답한다). null 이면(키 없는 빌드) 칩 줄을 그리지 않는다.
  final ValueChanged<String>? onAsk;

  const PaifuReviewSummary({
    super.key,
    required this.paifu,
    required this.review,
    this.result = '',
    this.thresholds = const ReviewThresholds(),
    required this.onStart,
    required this.onPlay,
    required this.onLesson,
    this.questions = const [],
    this.onAsk,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final r = review;
    final pct = r.efficiencyPct;
    final muted = theme.textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant);
    final head = paifu.title.isNotEmpty ? paifu.title : paifu.round;
    final lessons = r.lessons();
    final ask = onAsk;

    Widget gradeRow(ReviewGrade g) {
      final n = r.gradeCount(g);
      final row = Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(
          children: [
            SizedBox(width: 72, child: Text(gradeName(g), style: theme.textTheme.bodyLarge)),
            ReviewGradeIcon(g, size: 24),
            const Spacer(),
            Text(
              '$n',
              key: ValueKey('paifu-summary-count-${g.name}'),
              style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
            ),
          ],
        ),
      );
      // 0 인 줄도 지우지 않고 흐리게(판마다 표 모양이 같게).
      return Opacity(key: ValueKey('paifu-summary-grade-${g.name}'), opacity: n == 0 ? 0.38 : 1, child: row);
    }

    return SingleChildScrollView(
      key: const ValueKey('paifu-summary'),
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(result.isEmpty ? head : '$head · $result',
                  style: theme.textTheme.bodyMedium?.copyWith(color: scheme.onSurfaceVariant)),
              const SizedBox(height: 12),
              Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Text('패효율', style: theme.textTheme.titleLarge),
                  const Spacer(),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 8),
                    decoration: BoxDecoration(
                      color: scheme.surfaceContainerHigh,
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: scheme.outlineVariant),
                    ),
                    child: Text(
                      pct == null ? '—' : '$pct',
                      key: const ValueKey('paifu-summary-pct'),
                      style: theme.textTheme.displaySmall?.copyWith(fontWeight: FontWeight.w800),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                pct == null ? '평가할 버림이 없습니다' : '버림 ${r.turns.length}번 가운데 ${r.gradedCount}번을 평가했습니다.',
                key: const ValueKey('paifu-summary-evaluated'),
                style: theme.textTheme.bodyMedium,
              ),
              Text('유효패 수만 본 값입니다. 수비와 점수 판단은 들어 있지 않습니다.', style: theme.textTheme.bodyMedium),
              Text(
                '등급 기준(최선보다 유효패가 ${thresholds.goodPct}% 이하로 적으면 좋음, '
                '${thresholds.inaccuracyPct}% 이하면 부정확, 그보다 많으면 실수)은 임시 기준입니다.',
                key: const ValueKey('paifu-summary-threshold'),
                style: muted,
              ),
              const Divider(height: 24),
              for (final g in ReviewGrade.values) gradeRow(g),
              const Divider(height: 24),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(width: 72, child: Text('평가 안 함', style: muted)),
                  Expanded(
                    child: Text(
                      '리치 중 ${r.forcedCount} · 수비 ${r.defenseCount} · '
                      '화료 형태 ${r.completeCount} · 손패 모름 ${r.handUnknownCount}',
                      key: const ValueKey('paifu-summary-skip'),
                      style: muted,
                    ),
                  ),
                ],
              ),
              const Divider(height: 24),
              Text('배울 장면', style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
              const SizedBox(height: 4),
              if (lessons.isEmpty)
                Text('이 판은 유효패 수에서 지적할 곳이 없습니다',
                    key: const ValueKey('paifu-summary-nolesson'), style: theme.textTheme.bodyMedium)
              else
                for (final (i, t) in lessons.indexed)
                  InkWell(
                    key: ValueKey('paifu-summary-lesson-$i'),
                    onTap: () => onLesson(t.eventIndex + 1),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      child: Row(
                        children: [
                          ReviewGradeIcon(t.grade!, size: 22),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text('${t.turn}순 ${tileText(t.discard)} 버림',
                                maxLines: 1, overflow: TextOverflow.ellipsis, style: theme.textTheme.bodyLarge),
                          ),
                          Text(lessonLossText(t), style: theme.textTheme.bodyMedium),
                          const Icon(Icons.chevron_right),
                        ],
                      ),
                    ),
                  ),
              if (ask != null && questions.isNotEmpty) ...[
                const SizedBox(height: 16),
                Column(
                  key: const ValueKey('paifu-summary-ask'),
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text('질문', style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
                    const SizedBox(height: 6),
                    Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      children: [
                        for (final (i, q) in questions.indexed)
                          ActionChip(
                            key: ValueKey('paifu-summary-ask-$i'),
                            label: Text(q),
                            visualDensity: VisualDensity.compact,
                            onPressed: () => ask(q),
                          ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text('누르면 복기 화면의 질문 창에서 답합니다.', style: muted),
                  ],
                ),
              ],
              const SizedBox(height: 20),
              FilledButton(
                key: const ValueKey('paifu-summary-start'),
                style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52)),
                onPressed: onStart,
                child: const Text('복기 시작', style: TextStyle(fontSize: 18)),
              ),
              const SizedBox(height: 4),
              TextButton(
                key: const ValueKey('paifu-summary-play'),
                onPressed: onPlay,
                child: const Text('처음부터 보기'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
