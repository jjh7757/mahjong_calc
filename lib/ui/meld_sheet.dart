import 'package:flutter/material.dart';

import '../engine/calculator.dart';
import 'hand_editor.dart';
import 'kiosk.dart' show showAdaptiveSheet;
import 'tile_view.dart';

enum _MeldKind { chi, pon, kan, closedKan }

/// 부르기 입력 시트. 종류를 고르고 패를 누르면 묶음이 추가된다.
Future<void> showMeldSheet(BuildContext context, HandEditor editor) {
  return showAdaptiveSheet(
    context,
    kioskMaxWidth: 640,
    builder: (_) => _MeldSheet(editor: editor),
  );
}

class _MeldSheet extends StatefulWidget {
  final HandEditor editor;
  const _MeldSheet({required this.editor});

  @override
  State<_MeldSheet> createState() => _MeldSheetState();
}

class _MeldSheetState extends State<_MeldSheet> {
  _MeldKind kind = _MeldKind.pon;
  bool withRed = false;

  Meld _build(int tile) {
    switch (kind) {
      case _MeldKind.chi:
        return Meld.chi(tile);
      case _MeldKind.pon:
        return Meld.pon(tile);
      case _MeldKind.kan:
        return Meld.openKan(tile);
      case _MeldKind.closedKan:
        return Meld.closedKan(tile);
    }
  }

  bool _containsFive(int tile) {
    if (Tiles.isHonor(tile)) return false;
    final n = Tiles.number(tile);
    if (kind == _MeldKind.chi) return n >= 3 && n <= 5;
    return n == 5;
  }

  List<List<int>> get _rows {
    if (kind == _MeldKind.chi) {
      return [
        [0, 1, 2, 3, 4, 5, 6],
        [9, 10, 11, 12, 13, 14, 15],
        [18, 19, 20, 21, 22, 23, 24],
      ];
    }
    return const [
      [0, 1, 2, 3, 4, 5, 6, 7, 8],
      [9, 10, 11, 12, 13, 14, 15, 16, 17],
      [18, 19, 20, 21, 22, 23, 24, 25, 26],
      [27, 28, 29, 30, 31, 32, 33],
    ];
  }

  void _pick(int tile) {
    final meld = _build(tile);
    final red = withRed && _containsFive(tile) ? 1 : 0;
    final error = widget.editor.addMeld(meld, red: red);
    if (error != null) {
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: Text(error)));
      return;
    }
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final editor = widget.editor;
    final scheme = Theme.of(context).colorScheme;
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('부르기', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            SegmentedButton<_MeldKind>(
              showSelectedIcon: false,
              segments: const [
                ButtonSegment(value: _MeldKind.chi, label: Text('치')),
                ButtonSegment(value: _MeldKind.pon, label: Text('퐁')),
                ButtonSegment(value: _MeldKind.kan, label: Text('깡')),
                ButtonSegment(value: _MeldKind.closedKan, label: Text('안깡')),
              ],
              selected: {kind},
              onSelectionChanged: (s) => setState(() => kind = s.first),
            ),
            const SizedBox(height: 6),
            Text(
              kind == _MeldKind.chi ? '가장 낮은 패를 고르세요 (예: 3-4-5면 3)' : '패를 고르세요',
              style: TextStyle(fontSize: 12, color: scheme.outline),
            ),
            const SizedBox(height: 8),
            LayoutBuilder(
              builder: (context, c) {
                const gap = 4.0;
                final width = ((c.maxWidth - gap * 8) / 9).clamp(24.0, 44.0);
                return Column(
                  children: [
                    for (final row in _rows)
                      Padding(
                        padding: const EdgeInsets.only(bottom: gap),
                        child: Row(
                          children: [
                            for (final t in row)
                              Padding(
                                padding: const EdgeInsets.only(right: gap),
                                child: TileView(
                                  t,
                                  width: width,
                                  dimmed: _cannot(editor, t),
                                  onTap: () => _pick(t),
                                ),
                              ),
                          ],
                        ),
                      ),
                  ],
                );
              },
            ),
            if (editor.rules.redDora)
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                dense: true,
                controlAffinity: ListTileControlAffinity.leading,
                title: const Text('적도라 5 포함'),
                value: withRed,
                onChanged: (v) => setState(() => withRed = v ?? false),
              ),
          ],
        ),
      ),
    );
  }

  bool _cannot(HandEditor editor, int tile) {
    final meld = _build(tile);
    for (final t in meld.tiles.toSet()) {
      final need = meld.tiles.where((x) => x == t).length;
      if (editor.countOf(t) + need > 4) return true;
    }
    return false;
  }
}
