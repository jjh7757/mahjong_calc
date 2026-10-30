import 'package:flutter/material.dart';

/// 점수 이동판의 한 자리.
class CrossSeat {
  /// 자풍 0 동 ~ 3 북.
  final int wind;
  final String? name;

  /// 화료 전 점수(점수판이 없으면 null → 변화만 보여 준다).
  final int? before;
  final int delta;
  final bool winner;
  final bool loser;

  /// 이번 화료로 리치봉을 자동으로 넣는 자리.
  final bool autoRiichi;
  const CrossSeat({
    required this.wind,
    this.name,
    this.before,
    required this.delta,
    this.winner = false,
    this.loser = false,
    this.autoRiichi = false,
  });
}

/// 작혼 결과처럼 네 자리를 상하좌우에 놓고 점수 변화를 보여 준다.
/// [seats] 는 아래·오른쪽·위·왼쪽 순서(반시계, 오른쪽이 다음 차례).
/// [revealed] 가 true 가 되면 변화량이 0 에서 올라가고 점수가 바뀐다.
class ScoreCross extends StatelessWidget {
  final List<CrossSeat> seats;
  final bool revealed;

  /// 변화량을 0 에서 올리는 연출을 할지. false 면 바로 최종 값을 보여 준다.
  final bool countUp;

  /// 가운데 칸 글(국·본장·공탁 등).
  final List<String> center;

  /// 판 위쪽 안내(예: "방총자를 누르세요"). null 이면 없음.
  final String? prompt;

  /// 자리를 눌렀을 때. 인자는 [seats] 의 위치(0 아래 ~ 3 왼쪽).
  final void Function(int side)? onTapSide;

  const ScoreCross({
    super.key,
    required this.seats,
    this.revealed = true,
    this.countUp = true,
    this.center = const [],
    this.prompt,
    this.onTapSide,
  }) : assert(seats.length == 4);

  static const _winds = ['東', '南', '西', '北'];

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;

    Widget seat(int side) => _SeatBox(
          key: ValueKey('cross-seat-$side'),
          seat: seats[side],
          revealed: revealed,
          countUp: countUp,
          onTap: onTapSide == null ? null : () => onTapSide!(side),
        );

    final middle = Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 10),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (final c in center)
            Text(c, style: text.bodySmall, textAlign: TextAlign.center),
        ],
      ),
    );

    return Column(
      children: [
        if (prompt != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: Text(prompt!,
                key: const ValueKey('cross-prompt'),
                style: text.bodyMedium?.copyWith(color: scheme.primary, fontWeight: FontWeight.w600)),
          ),
        Row(children: [const Spacer(), Expanded(flex: 2, child: seat(2)), const Spacer()]),
        const SizedBox(height: 6),
        Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Expanded(flex: 2, child: seat(3)),
            const SizedBox(width: 6),
            Expanded(flex: 1, child: middle),
            const SizedBox(width: 6),
            Expanded(flex: 2, child: seat(1)),
          ],
        ),
        const SizedBox(height: 6),
        Row(children: [const Spacer(), Expanded(flex: 2, child: seat(0)), const Spacer()]),
      ],
    );
  }
}

class _SeatBox extends StatelessWidget {
  final CrossSeat seat;
  final bool revealed;
  final bool countUp;
  final VoidCallback? onTap;
  const _SeatBox({super.key, required this.seat, required this.revealed, required this.countUp, this.onTap});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    final s = seat;
    const plus = Color(0xFF2E7D32);
    const minus = Color(0xFFC62828);

    final tag = s.winner
        ? '화료'
        : s.loser
            ? '방총'
            : null;
    final border = s.winner
        ? scheme.primary
        : s.loser
            ? minus
            : scheme.outlineVariant;

    return Material(
      color: s.winner ? scheme.primaryContainer.withValues(alpha: 0.6) : scheme.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
        side: BorderSide(color: border, width: s.winner || s.loser ? 2 : 1),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 6),
          child: TweenAnimationBuilder<double>(
            // 변화량이 바뀌면(방총자를 다시 고르면) 처음부터 다시 올린다.
            key: ValueKey('${s.delta}-$revealed'),
            tween: Tween(begin: 0, end: revealed ? 1 : 0),
            duration: countUp ? const Duration(milliseconds: 900) : Duration.zero,
            curve: Curves.easeOutCubic,
            builder: (context, t, _) {
              final shown = (s.delta * t).round();
              final deltaText = s.delta == 0 ? '±0' : (shown >= 0 ? '+$shown' : '$shown');
              final deltaColor = s.delta > 0
                  ? plus
                  : s.delta < 0
                      ? minus
                      : scheme.outline;
              return Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(ScoreCross._winds[s.wind],
                          style: text.labelLarge?.copyWith(
                              color: s.wind == 0 ? minus : scheme.onSurface, fontWeight: FontWeight.w700)),
                      if (s.name != null) ...[
                        const SizedBox(width: 4),
                        Flexible(
                          child: Text(s.name!, overflow: TextOverflow.ellipsis, style: text.labelLarge),
                        ),
                      ],
                      if (tag != null) ...[
                        const SizedBox(width: 4),
                        _Tag(tag, s.winner ? scheme.primary : minus),
                      ],
                      if (s.autoRiichi) ...[
                        const SizedBox(width: 4),
                        _Tag('리치', scheme.tertiary),
                      ],
                    ],
                  ),
                  if (s.before != null)
                    Text('${s.before! + shown}',
                        style: text.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                  Opacity(
                    opacity: revealed ? 1 : 0,
                    child: Text(deltaText,
                        style: (s.before == null ? text.titleMedium : text.bodyMedium)
                            ?.copyWith(color: deltaColor, fontWeight: FontWeight.w700)),
                  ),
                ],
              );
            },
          ),
        ),
      ),
    );
  }
}

class _Tag extends StatelessWidget {
  final String label;
  final Color color;
  const _Tag(this.label, this.color);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
      decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(4)),
      child: Text(label, style: const TextStyle(fontSize: 10, color: Colors.white, fontWeight: FontWeight.w700)),
    );
  }
}
