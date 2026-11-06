import 'package:flutter/material.dart';

import '../table/seat_map.dart';
import '../table/table_layout.dart';

/// 카메라 사진 기준으로 누가 어느 변에 앉았는지 맞추는 탁자 그림([GameSettings.bottomSeat]).
///
/// 위에서 내려다본 사진에서 차례는 반시계(아래→오른쪽→위→왼쪽)라, 실제 자리는 네 자리를 통째로 돌린 것 중
/// 하나뿐이다. 그래서 가운데 돌리기 버튼 둘로만 바꾼다(변을 누르는 건 뜻이 헷갈리고 잘못 닿기 쉬움).
/// 그림 아래 변 = 사진 아래쪽.
class SeatSidePicker extends StatelessWidget {
  /// 자리(0~3)마다 그 변에 쓸 글자(예: "동 철수").
  final List<String> labels;
  final int bottomSeat;
  final ValueChanged<int> onChanged;
  final double size;

  const SeatSidePicker({
    super.key,
    required this.labels,
    required this.bottomSeat,
    required this.onChanged,
    this.size = 240,
  });

  /// 화면에서 시계 방향으로 한 칸(아래 사람 → 왼쪽): 새 아래쪽 = 원래 오른쪽 사람.
  static int rotatedClockwise(int bottomSeat) => (bottomSeat + 1) % 4;

  /// 반시계 방향으로 한 칸(아래 사람 → 오른쪽): 새 아래쪽 = 원래 왼쪽 사람.
  static int rotatedCounterClockwise(int bottomSeat) => (bottomSeat + 3) % 4;

  @override
  Widget build(BuildContext context) {
    final seats = SeatMap(bottomSeat);
    final scheme = Theme.of(context).colorScheme;
    Widget chip(Side side) {
      final seat = seats.seatOf(side);
      return Container(
        key: ValueKey('seat-side-${side.name}'),
        constraints: BoxConstraints(maxWidth: size * 0.42),
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(
          color: seat == 0 ? scheme.primaryContainer : scheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Text(
          labels[seat],
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontWeight: FontWeight.w600,
            color: seat == 0 ? scheme.onPrimaryContainer : scheme.onSurface,
          ),
        ),
      );
    }

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          width: size,
          height: size * 0.8,
          child: Stack(
            children: [
              Positioned.fill(
                child: Container(
                  margin: const EdgeInsets.all(18),
                  decoration: BoxDecoration(
                    color: const Color(0xFF1F5E3A),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: const Color(0xFF3B2A1C), width: 4),
                  ),
                ),
              ),
              Align(alignment: Alignment.bottomCenter, child: chip(Side.bottom)),
              Align(alignment: Alignment.centerRight, child: chip(Side.right)),
              Align(alignment: Alignment.topCenter, child: chip(Side.top)),
              Align(alignment: Alignment.centerLeft, child: chip(Side.left)),
              Center(
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    IconButton.filledTonal(
                      key: const ValueKey('seat-rotate-ccw'),
                      tooltip: '반시계로 한 칸',
                      icon: const Icon(Icons.rotate_left),
                      onPressed: () => onChanged(rotatedCounterClockwise(bottomSeat)),
                    ),
                    const SizedBox(width: 4),
                    IconButton.filledTonal(
                      key: const ValueKey('seat-rotate-cw'),
                      tooltip: '시계로 한 칸',
                      icon: const Icon(Icons.rotate_right),
                      onPressed: () => onChanged(rotatedClockwise(bottomSeat)),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 2),
        Text('▼ 카메라 사진 아래쪽', style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }
}
