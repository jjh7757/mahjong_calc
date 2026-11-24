import 'package:flutter/material.dart';

import '../../game/game.dart';
import '../../game/game_store.dart';
import '../../game/member_stats.dart';
import '../../game/member_store.dart';
import '../kiosk.dart';
import '../name_keyboard.dart';
import 'result_entry_screen.dart';
import 'settlement_screen.dart';

/// 등록 멤버의 누적 성적표. 지난 대국(직접 입력한 대국 + 앱으로 친 대국 중 이름이 명단과 같은 것)에서 센다.
class MemberRankingScreen extends StatelessWidget {
  const MemberRankingScreen({super.key});

  void _push(BuildContext context, Widget screen) =>
      Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: Listenable.merge([gameStore, memberStore]),
      builder: (context, _) {
        final stats = memberStats(gameStore.history, only: memberStore.members);
        final played = [for (final s in stats) if (s.games > 0) s];
        final unplayed = [for (final s in stats) if (s.games == 0) s];
        return kioskWrap(context, Scaffold(
          appBar: AppBar(title: const Text('멤버 순위')),
          body: kioskPage(context, SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    FilledButton.icon(
                      key: const ValueKey('members-entry'),
                      icon: const Icon(Icons.edit_note),
                      label: const Text('결과 입력'),
                      onPressed: () => _push(context, const ResultEntryScreen()),
                    ),
                    OutlinedButton.icon(
                      key: const ValueKey('members-manage'),
                      icon: const Icon(Icons.manage_accounts),
                      label: const Text('멤버 관리'),
                      onPressed: () => _push(context, const MemberManageScreen()),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  '앱으로 기록한 대국도 이름이 명단과 같으면 함께 셉니다.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                const SizedBox(height: 12),
                if (stats.isEmpty)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 32),
                    child: Center(child: Text('등록된 멤버가 없습니다. 멤버 관리에서 추가하세요.')),
                  )
                else
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: _table(context, played, unplayed),
                  ),
              ],
            ),
          )),
        ));
      },
    );
  }

  Widget _table(BuildContext context, List<MemberStat> played, List<MemberStat> unplayed) {
    final scheme = Theme.of(context).colorScheme;
    final faded = scheme.onSurface.withValues(alpha: 0.38);
    const tabular = [FontFeature.tabularFigures()];

    DataRow row(MemberStat s, int? rank) {
      final dim = s.games == 0;
      final base = TextStyle(color: dim ? faded : null, fontFeatures: tabular);
      Color? totalColor;
      if (!dim && s.total != 0) totalColor = s.total > 0 ? Colors.green.shade600 : scheme.error;
      String pct(double v) => dim ? '-' : '${(v * 100).round()}%';
      return DataRow(
        onSelectChanged: dim ? null : (_) => _push(context, MemberGamesScreen(name: s.name)),
        cells: [
          DataCell(Text(rank == null ? '-' : '$rank', style: base)),
          DataCell(Text(s.name, key: ValueKey('members-row-${s.name}'), style: base.copyWith(fontWeight: FontWeight.w700))),
          DataCell(Text('${s.games}', style: base)),
          DataCell(Text(dim ? '-' : fmtPt(s.total),
              style: base.copyWith(color: dim ? faded : totalColor, fontWeight: FontWeight.w700))),
          DataCell(Text(dim ? '-' : s.avgRank.toStringAsFixed(2), style: base)),
          DataCell(Text(s.best == null ? '-' : '${s.best}', key: ValueKey('members-best-${s.name}'), style: base)),
          DataCell(Text(dim ? '-' : '${s.stars}', key: ValueKey('members-stars-${s.name}'), style: base)),
          DataCell(Text(dim ? '-' : s.avgStars.toStringAsFixed(2), key: ValueKey('members-avgstars-${s.name}'), style: base)),
          DataCell(Text(pct(s.topRate), style: base)),
          DataCell(Text(pct(s.top2Rate), key: ValueKey('members-top2-${s.name}'), style: base)),
          DataCell(Text(pct(s.lastRate), style: base)),
          DataCell(Text(dim ? '-' : '${s.busts}', style: base)),
        ],
      );
    }

    return DataTable(
      key: const ValueKey('members-table'),
      showCheckboxColumn: false,
      columnSpacing: 18,
      horizontalMargin: 8,
      columns: const [
        DataColumn(label: Text('순위')),
        DataColumn(label: Text('이름')),
        DataColumn(label: Text('대국'), numeric: true),
        DataColumn(label: Text('합계 pt'), numeric: true),
        DataColumn(label: Text('평균 순위'), numeric: true),
        DataColumn(label: Text('최고점'), numeric: true),
        DataColumn(label: Text('별'), numeric: true),
        DataColumn(label: Text('평별'), numeric: true),
        DataColumn(label: Text('1위율'), numeric: true),
        DataColumn(label: Text('1,2위율'), numeric: true),
        DataColumn(label: Text('4위율'), numeric: true),
        DataColumn(label: Text('토비'), numeric: true),
      ],
      rows: [
        for (var i = 0; i < played.length; i++) row(played[i], i + 1),
        for (final s in unplayed) row(s, null),
      ],
    );
  }
}

/// 한 멤버가 나온 지난 대국 목록(최근 것부터). 누르면 정산 화면.
class MemberGamesScreen extends StatelessWidget {
  final String name;
  const MemberGamesScreen({super.key, required this.name});

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: gameStore,
      builder: (context, _) {
        final items = <(Game, Settlement)>[
          for (final g in gameStore.history)
            for (final r in g.settle())
              if (r.name == name) (g, r),
        ];
        final scheme = Theme.of(context).colorScheme;
        return kioskWrap(context, Scaffold(
          appBar: AppBar(title: Text('$name · 대국 ${items.length}')),
          body: kioskPage(context, items.isEmpty
              ? const Center(child: Text('이 멤버의 대국이 없습니다'))
              : ListView.separated(
                  itemCount: items.length,
                  separatorBuilder: (_, _) => const Divider(height: 1),
                  itemBuilder: (context, i) {
                    final (g, r) = items[i];
                    final d = g.startedAt;
                    final date = '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
                    return ListTile(
                      key: ValueKey('member-game-$i'),
                      leading: CircleAvatar(child: Text('${r.rank}위')),
                      title: Text('${r.points}점'),
                      subtitle: Text('$date${g.isManual ? ' · 직접 입력' : ''}${r.stars > 0 ? ' · ★${r.stars}' : ''}'),
                      trailing: Text(
                        fmtPt(r.score),
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                          color: r.score < 0 ? scheme.error : (r.score > 0 ? Colors.green.shade600 : null),
                        ),
                      ),
                      onTap: () => Navigator.of(context)
                          .push(MaterialPageRoute(builder: (_) => SettlementScreen(game: g))),
                    );
                  },
                )),
        ));
      },
    );
  }
}

/// 등록 멤버 명단 관리. 추가는 앱 안 키보드, 빼기는 길게 눌러 확인.
class MemberManageScreen extends StatelessWidget {
  const MemberManageScreen({super.key});

  Future<void> _add(BuildContext context) async {
    final v = await showNameKeyboard(context, title: '멤버 이름', initial: '');
    if (v == null || !context.mounted) return;
    final name = v.trim();
    if (name.isEmpty) return;
    if (!memberStore.add(name)) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('이미 있는 이름입니다: $name')));
    }
  }

  Future<void> _remove(BuildContext context, String name) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => kioskWrap(ctx, AlertDialog(
        title: Text('$name 을(를) 명단에서 뺄까요?'),
        content: const Text('명단에서만 빠지고 지난 기록은 남습니다.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('아니오')),
          FilledButton(
            key: const ValueKey('manage-remove-ok'),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('빼기'),
          ),
        ],
      )),
    );
    if (ok == true) memberStore.remove(name);
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: Listenable.merge([gameStore, memberStore]),
      builder: (context, _) {
        final list = memberStore.members;
        final counts = <String, int>{};
        for (final g in gameStore.history) {
          for (final n in g.names) {
            counts[n] = (counts[n] ?? 0) + 1;
          }
        }
        return kioskWrap(context, Scaffold(
          appBar: AppBar(
            title: const Text('멤버 관리'),
            actions: [
              TextButton.icon(
                key: const ValueKey('manage-add'),
                icon: const Icon(Icons.person_add_alt),
                label: const Text('추가'),
                onPressed: () => _add(context),
              ),
            ],
          ),
          body: kioskPage(context, list.isEmpty
              ? const Center(child: Text('등록된 멤버가 없습니다. 위의 추가를 누르세요.'))
              : ListView.separated(
                  itemCount: list.length + 1,
                  separatorBuilder: (_, _) => const Divider(height: 1),
                  itemBuilder: (context, i) {
                    if (i == list.length) {
                      return Padding(
                        padding: const EdgeInsets.all(16),
                        child: Text('길게 누르면 명단에서 뺍니다(지난 기록은 남음).',
                            style: Theme.of(context).textTheme.bodySmall),
                      );
                    }
                    final n = list[i];
                    return ListTile(
                      key: ValueKey('manage-member-$n'),
                      leading: const Icon(Icons.person_outline),
                      title: Text(n),
                      subtitle: Text('대국 ${counts[n] ?? 0}'),
                      onLongPress: () => _remove(context, n),
                    );
                  },
                )),
        ));
      },
    );
  }
}

/// 정산 점수 표시(+/− 부호, 정수면 소수 없이).
String fmtPt(double v) {
  final s = v == v.roundToDouble() ? v.toInt().toString() : v.toStringAsFixed(1);
  return v > 0 ? '+$s' : s;
}
