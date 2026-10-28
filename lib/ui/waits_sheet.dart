import 'package:flutter/material.dart';

import '../engine/calculator.dart';
import '../engine/waits.dart';
import 'hand_editor.dart';
import 'kiosk.dart' show showAdaptiveSheet;
import 'tile_view.dart';

/// 13장 손패의 대기패와 각 대기의 점수를 보여준다.
/// [onPick] 이 있으면 줄의 "론"·"쯔모" 를 눌러 그 패로 바로 계산할 수 있다(시트는 닫힌다).
Future<void> showWaitsSheet(BuildContext context, HandEditor editor,
    {void Function(int tile, bool tsumo)? onPick}) {
  final closed = editor.closed.map((t) => t.tile).toList();
  List<Wait> waits;
  String? error;
  try {
    waits = findWaits(closed, editor.melds, editor.situation,
        rules: editor.rules, redCount: editor.redTotal);
  } catch (e) {
    waits = const [];
    error = e.toString();
  }

  return showAdaptiveSheet(
    context,
    kioskMaxWidth: 640,
    builder: (ctx) {
      final scheme = Theme.of(ctx).colorScheme;
      return SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                error != null
                    ? '대기패를 구할 수 없습니다'
                    : waits.isEmpty
                        ? '노텐입니다'
                        : '대기 ${waits.length}종',
                style: Theme.of(ctx).textTheme.titleMedium,
              ),
              if (error != null)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(error, style: TextStyle(color: scheme.error, fontSize: 12)),
                ),
              if (waits.isEmpty && error == null)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text('13장이 화료 한 장 전 형태가 아닙니다',
                      style: TextStyle(color: scheme.outline, fontSize: 12)),
                ),
              const SizedBox(height: 8),
              Flexible(
                child: ListView.separated(
                  shrinkWrap: true,
                  itemCount: waits.length,
                  separatorBuilder: (_, _) => const Divider(height: 1),
                  itemBuilder: (_, i) => _WaitRow(
                    waits[i],
                    onPick: onPick == null
                        ? null
                        : (tsumo) {
                            Navigator.of(ctx).pop();
                            onPick(waits[i].tile, tsumo);
                          },
                  ),
                ),
              ),
              const SizedBox(height: 4),
              Text(
                onPick == null
                    ? '점수는 현재 상황(자풍·장풍·리치·도라) 기준'
                    : '점수는 현재 상황(자풍·장풍·리치·도라) 기준 · 론/쯔모를 누르면 그 패로 계산',
                style: TextStyle(fontSize: 11, color: scheme.outline),
              ),
            ],
          ),
        ),
      );
    },
  );
}

class _WaitRow extends StatelessWidget {
  final Wait wait;
  final void Function(bool tsumo)? onPick;
  const _WaitRow(this.wait, {this.onPick});

  String _line(ScoreResult r) {
    if (!r.isValid) return '역 없음';
    final yaku = r.yaku.map((y) => y.yaku.label).join('·');
    return '${r.summary} ${r.payment.display}  ($yaku)';
  }

  /// "론"·"쯔모" 한 줄. [onPick] 이 있으면 눌러서 그 패로 계산한다.
  Widget _row(BuildContext context, String label, ScoreResult r, bool tsumo) {
    final scheme = Theme.of(context).colorScheme;
    final pick = onPick;
    final text = Text('$label  ${_line(r)}',
        style: TextStyle(fontSize: 13, color: r.isValid ? null : scheme.outline));
    if (pick == null) return text;
    return InkWell(
      key: ValueKey('wait-${Tiles.toCode(wait.tile)}-${tsumo ? 'tsumo' : 'ron'}'),
      borderRadius: BorderRadius.circular(6),
      onTap: () => pick(tsumo),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 3, horizontal: 4),
        child: Row(
          children: [
            Expanded(child: text),
            Icon(Icons.chevron_right, size: 16, color: scheme.outline),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          TileView(wait.tile, width: 36),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _row(context, '론', wait.ron, false),
                _row(context, '쯔모', wait.tsumo, true),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
