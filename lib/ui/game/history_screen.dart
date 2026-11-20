import 'package:flutter/material.dart';

import '../../game/game_store.dart';
import '../../paifu/paifu_store.dart';
import '../kiosk.dart';
import '../paifu/paifu_screen.dart';
import 'settlement_screen.dart';

/// 끝난 대국 목록.
class HistoryScreen extends StatelessWidget {
  const HistoryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: gameStore,
      builder: (context, _) {
        final list = gameStore.history;
        return kioskWrap(context, Scaffold(
          appBar: AppBar(
            title: const Text('지난 대국'),
            actions: [
              // 묶어 둔 예시 판(11-14 매장 2반장 동1국~남4국 · 3반장 동1국) 목록. 대국에서 적힌 패보는 대국 줄의 패보 단추로.
              TextButton.icon(
                icon: const Icon(Icons.slideshow),
                label: const Text('패보 예시'),
                onPressed: () =>
                    Navigator.of(context).push(MaterialPageRoute(builder: (_) => const PaifuAssetListScreen())),
              ),
            ],
          ),
          body: kioskPage(context, list.isEmpty
              ? const Center(child: Text('저장된 대국이 없습니다'))
              : ListView.separated(
                  itemCount: list.length,
                  separatorBuilder: (_, _) => const Divider(height: 1),
                  itemBuilder: (context, i) {
                    final g = list[i];
                    final rows = g.settle();
                    final d = g.startedAt;
                    final date = '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
                    return ListTile(
                      title: Text(rows.map((r) => '${r.name} ${_fmt(r.score)}').join('  ')),
                      subtitle: Text('$date · ${g.roundLabel} · ${g.events.length}건'),
                      trailing: IconButton(
                        tooltip: '패보',
                        icon: const Icon(Icons.slideshow),
                        onPressed: () => Navigator.of(context).push(
                            MaterialPageRoute(builder: (_) => PaifuListScreen(gameId: g.id, title: '패보 · $date'))),
                      ),
                      onTap: () => Navigator.of(context)
                          .push(MaterialPageRoute(builder: (_) => SettlementScreen(game: g))),
                      onLongPress: () async {
                        final ok = await showDialog<bool>(
                          context: context,
                          builder: (ctx) => kioskWrap(ctx, AlertDialog(
                            title: const Text('이 기록을 지울까요?'),
                            actions: [
                              TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('아니오')),
                              FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('지우기')),
                            ],
                          )),
                        );
                        if (ok == true) {
                          gameStore.deleteHistory(g.id);
                          PaifuStore.delete(g.id);
                        }
                      },
                    );
                  },
                )),
        ));
      },
    );
  }

  static String _fmt(double v) {
    final s = v == v.roundToDouble() ? v.toInt().toString() : v.toStringAsFixed(1);
    return v > 0 ? '+$s' : s;
  }
}
