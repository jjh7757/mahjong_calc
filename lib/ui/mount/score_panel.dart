import 'dart:async';

import 'package:flutter/material.dart';

import '../../engine/tile.dart';
import '../../game/game.dart';
import '../../table/seat_map.dart';
import '../../table/table_layout.dart';

/// 테이블 사진 가운데에 겹치는 점수 상자(작혼의 가운데 점수판처럼).
///
/// 가운데에 국·본장·공탁, 네 변에 그 쪽에 앉은 사람의 바람·점수·이름·리치봉.
/// - 점수를 누르면 몇 초 동안 다른 사람과의 점수 차를 보여 준다.
/// - 기록이 늘면(화료·유국·리치) 몇 초 동안 점수 변화(+/−)를 보여 준다.
class TableScorePanel extends StatefulWidget {
  final Game game;
  final SeatMap seats;
  final double size;

  const TableScorePanel({super.key, required this.game, required this.seats, this.size = 280});

  @override
  State<TableScorePanel> createState() => _TableScorePanelState();
}

class _TableScorePanelState extends State<TableScorePanel> {
  late String _gameId;
  late int _seenEvents;

  /// 방금 기록의 점수 변화와 설명. null 이면 보여 주지 않는다.
  List<int>? _delta;
  String? _deltaText;
  Timer? _deltaTimer;

  /// 점수 차 기준 자리. null 이면 보통 표시.
  int? _diffFrom;
  Timer? _diffTimer;

  @override
  void initState() {
    super.initState();
    _gameId = widget.game.id;
    _seenEvents = widget.game.events.length;
  }

  @override
  void didUpdateWidget(TableScorePanel old) {
    super.didUpdateWidget(old);
    final g = widget.game;
    if (g.id != _gameId) {
      _gameId = g.id;
      _seenEvents = g.events.length;
      return;
    }
    if (g.events.length > _seenEvents) {
      // 동시 론처럼 한 번에 여러 건이 늘면 합쳐서 보여 준다.
      final fresh = g.events.sublist(_seenEvents);
      _seenEvents = g.events.length;
      _delta = [for (var s = 0; s < 4; s++) fresh.fold(0, (a, e) => a + e.delta[s])];
      _deltaText = fresh.map((e) => e.description).join(' / ');
      _deltaTimer?.cancel();
      _deltaTimer = Timer(const Duration(seconds: 6), () {
        if (mounted) setState(() => _delta = null);
      });
    } else if (g.events.length < _seenEvents) {
      _seenEvents = g.events.length;
    }
  }

  @override
  void dispose() {
    _deltaTimer?.cancel();
    _diffTimer?.cancel();
    super.dispose();
  }

  void _showDiff(int seat) {
    _diffTimer?.cancel();
    setState(() => _diffFrom = _diffFrom == seat ? null : seat);
    _diffTimer = Timer(const Duration(seconds: 5), () {
      if (mounted) setState(() => _diffFrom = null);
    });
  }

  @override
  Widget build(BuildContext context) {
    final g = widget.game;
    final size = widget.size;
    final edge = size * 0.25;
    return SizedBox(
      width: size,
      height: size,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: const Color(0xE6141210),
          borderRadius: BorderRadius.circular(size * 0.06),
          border: Border.all(color: const Color(0x66E2C178), width: 1.5),
          boxShadow: const [BoxShadow(color: Color(0x66000000), blurRadius: 12)],
        ),
        child: Stack(
          children: [
            Positioned.fill(
              left: edge,
              right: edge,
              top: edge,
              bottom: edge,
              child: _center(g),
            ),
            for (final side in Side.values) _seatCell(g, side, edge),
          ],
        ),
      ),
    );
  }

  Widget _center(Game g) {
    final delta = _delta;
    final s = widget.size / 280;
    return Center(
      child: FittedBox(
        fit: BoxFit.scaleDown,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              '${Game.windNames[g.roundWind]} ${g.roundNumber}국',
              style: TextStyle(fontSize: 26 * s, fontWeight: FontWeight.w800, color: Colors.white),
            ),
            const SizedBox(height: 4),
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                _counter('${g.honba}', '본장'),
                const SizedBox(width: 10),
                _counter('${g.riichiSticks}', '공탁'),
              ],
            ),
            if (delta != null && _deltaText != null)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: SizedBox(
                  width: widget.size * 0.45,
                  child: Text(
                    _deltaText!,
                    textAlign: TextAlign.center,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 11 * s, color: const Color(0xFFE2C178)),
                  ),
                ),
              )
            else if (g.isOvertime || g.isLastRound)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text(
                  g.isOvertime ? '연장' : '올라스',
                  style: TextStyle(fontSize: 13 * s, fontWeight: FontWeight.w700, color: const Color(0xFFFF8A65)),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _counter(String value, String label) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(label, style: const TextStyle(fontSize: 11, color: Colors.white60)),
        const SizedBox(width: 3),
        Text(value, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: Colors.white)),
      ],
    );
  }

  /// 한 변의 칸. 그 변에 앉은 사람 정보를 글자를 세운 채로 그 변 가까이에 둔다.
  Widget _seatCell(Game g, Side side, double edge) {
    // 왼쪽·오른쪽 칸은 좁으므로 바람 글자를 점수 위에 쌓는다.
    final cell = _seatContent(g, widget.seats.seatOf(side), stacked: side == Side.left || side == Side.right);
    return switch (side) {
      Side.bottom => Positioned(left: edge, right: edge, bottom: 0, height: edge, child: cell),
      Side.top => Positioned(left: edge, right: edge, top: 0, height: edge, child: cell),
      Side.left => Positioned(left: 0, top: edge * 0.6, bottom: edge * 0.6, width: edge, child: cell),
      Side.right => Positioned(right: 0, top: edge * 0.6, bottom: edge * 0.6, width: edge, child: cell),
    };
  }

  Widget _seatContent(Game g, int seat, {bool stacked = false}) {
    final s = widget.size / 280;
    final dealer = seat == g.dealer;
    final wind = Tiles.name(g.seatWindOf(seat));
    final delta = _delta?[seat];
    final from = _diffFrom;
    final String scoreText;
    Color scoreColor = g.scores[seat] < 0 ? const Color(0xFFFF6E6E) : Colors.white;
    if (from != null && from != seat) {
      final d = g.scores[seat] - g.scores[from];
      scoreText = '${d > 0 ? '+' : ''}$d';
      scoreColor = d >= 0 ? const Color(0xFF7CE38B) : const Color(0xFFFF6E6E);
    } else {
      scoreText = '${g.scores[seat]}';
    }
    return InkWell(
      key: ValueKey('table-score-$seat'),
      onTap: () => _showDiff(seat),
      borderRadius: BorderRadius.circular(8),
      child: FittedBox(
        fit: BoxFit.scaleDown,
        child: Padding(
          padding: const EdgeInsets.all(4),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Flex(
                direction: stacked ? Axis.vertical : Axis.horizontal,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 22 * s,
                    height: 22 * s,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: dealer ? const Color(0xFFE2C178) : Colors.white12,
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      wind,
                      style: TextStyle(
                        fontSize: 14 * s,
                        fontWeight: FontWeight.w800,
                        color: dealer ? const Color(0xFF2A1F08) : Colors.white,
                      ),
                    ),
                  ),
                  const SizedBox(width: 6, height: 2),
                  Text(
                    scoreText,
                    style: TextStyle(
                      fontSize: 20 * s,
                      fontWeight: FontWeight.w700,
                      color: from == seat ? const Color(0xFFE2C178) : scoreColor,
                      fontFeatures: const [FontFeature.tabularFigures()],
                    ),
                  ),
                ],
              ),
              Text(
                g.names[seat],
                style: TextStyle(fontSize: 11 * s, color: Colors.white70),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              if (delta != null && delta != 0)
                Text(
                  '${delta > 0 ? '+' : ''}$delta',
                  style: TextStyle(
                    fontSize: 16 * s,
                    fontWeight: FontWeight.w800,
                    color: delta > 0 ? const Color(0xFF7CE38B) : const Color(0xFFFF6E6E),
                  ),
                )
              else if (g.riichiSeats.contains(seat))
                // 리치봉: 흰 막대 가운데 빨간 점.
                Container(
                  margin: const EdgeInsets.only(top: 3),
                  width: 44 * s,
                  height: 6 * s,
                  decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(3)),
                  alignment: Alignment.center,
                  child: Container(
                    width: 4 * s,
                    height: 4 * s,
                    decoration: const BoxDecoration(color: Color(0xFFD32F2F), shape: BoxShape.circle),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
