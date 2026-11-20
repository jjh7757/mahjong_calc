import 'package:flutter/material.dart';

import '../../paifu/paifu.dart';
import '../kiosk.dart';
import '../tile_view.dart';

/// 시작 손패 13장을 고르는 창. 돌려주는 값: null = 취소, 빈 목록 = 지우기, 13장 = 적용.
Future<List<PaifuTile>?> showStartHandSheet(BuildContext context, {List<PaifuTile> initial = const [], String who = ''}) =>
    showAdaptiveSheet<List<PaifuTile>>(context, builder: (_) => StartHandPicker(initial: initial, who: who));

class StartHandPicker extends StatefulWidget {
  final List<PaifuTile> initial;
  final String who;
  const StartHandPicker({super.key, this.initial = const [], this.who = ''});

  @override
  State<StartHandPicker> createState() => _StartHandPickerState();
}

class _StartHandPickerState extends State<StartHandPicker> {
  late final List<PaifuTile> _picked = [...widget.initial];

  /// 팔레트 한 줄: 수패 1~9 + 적5, 자패 7종.
  static final List<List<PaifuTile>> _rows = [
    for (var s = 0; s < 3; s++) [for (var n = 0; n < 9; n++) PaifuTile(s * 9 + n), PaifuTile(s * 9 + 4, red: true)],
    [for (var z = 27; z < 34; z++) PaifuTile(z)],
  ];

  static int _order(PaifuTile t) => t.tile * 2 + (t.red ? 0 : 1);

  /// 같은 패는 4장까지(적5 포함), 적5 는 종류마다 한 장.
  bool _canAdd(PaifuTile t) {
    if (_picked.length >= 13) return false;
    if (_picked.where((x) => x.tile == t.tile).length >= 4) return false;
    return !t.red || !_picked.contains(t);
  }

  void _add(PaifuTile t) {
    if (!_canAdd(t)) return;
    setState(() => _picked
      ..add(t)
      ..sort((a, b) => _order(a).compareTo(_order(b))));
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 12),
        child: LayoutBuilder(
          builder: (context, box) {
            final tw = ((box.maxWidth / 10) - 4).clamp(22.0, 46.0);
            return Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('시작 손패 입력${widget.who.isEmpty ? '' : ' · ${widget.who}'}', style: theme.textTheme.titleMedium),
                const SizedBox(height: 2),
                Text(
                  '배패 13장을 고릅니다(첫 쯔모 전). 고른 패를 누르면 빠집니다.',
                  style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                ),
                const SizedBox(height: 8),
                // 고른 패
                SizedBox(
                  height: tw * 1.4 + 6,
                  child: _picked.isEmpty
                      ? Align(
                          alignment: Alignment.centerLeft,
                          child: Text('아직 고른 패가 없습니다', style: theme.textTheme.bodyMedium),
                        )
                      : SingleChildScrollView(
                          scrollDirection: Axis.horizontal,
                          child: Row(
                            key: const ValueKey('start-picked'),
                            children: [
                              for (final (i, t) in _picked.indexed)
                                Padding(
                                  padding: const EdgeInsets.only(right: 2),
                                  child: TileView(
                                    t.tile,
                                    red: t.red,
                                    width: tw * 0.86,
                                    onTap: () => setState(() => _picked.removeAt(i)),
                                  ),
                                ),
                            ],
                          ),
                        ),
                ),
                Text('${_picked.length} / 13', key: const ValueKey('start-count'), style: theme.textTheme.bodySmall),
                const Divider(height: 14),
                // 팔레트
                for (final row in _rows)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 4),
                    child: Row(
                      children: [
                        for (final t in row)
                          Padding(
                            padding: const EdgeInsets.only(right: 4),
                            child: TileView(
                              key: ValueKey('start-pick-${t.code}'),
                              t.tile,
                              red: t.red,
                              width: tw,
                              dimmed: !_canAdd(t),
                              onTap: () => _add(t),
                            ),
                          ),
                      ],
                    ),
                  ),
                const SizedBox(height: 6),
                Row(
                  children: [
                    TextButton(
                      key: const ValueKey('start-clear'),
                      onPressed: () => Navigator.pop(context, const <PaifuTile>[]),
                      child: const Text('시작 손패 지우기'),
                    ),
                    const Spacer(),
                    TextButton(onPressed: () => Navigator.pop(context), child: const Text('취소')),
                    const SizedBox(width: 8),
                    FilledButton(
                      key: const ValueKey('start-apply'),
                      onPressed: _picked.length == 13 ? () => Navigator.pop(context, [..._picked]) : null,
                      child: const Text('패보에 적용'),
                    ),
                  ],
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}
