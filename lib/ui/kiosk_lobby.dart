import 'package:flutter/material.dart';

import '../game/game.dart';
import '../game/game_store.dart';
import 'game/game_screen.dart';
import 'game/history_screen.dart';
import 'game/settlement_screen.dart';
import 'hand_editor.dart';
import 'input_screen.dart';
import 'kiosk.dart';
import 'mount/camera_head_screen.dart';
import 'quiz_screen.dart';
import 'score_table_screen.dart';
import 'settings_screen.dart';
import 'survey_qr.dart';

/// 키오스크(태블릿 가로)에서 진행 중 대국이 없을 때의 첫 화면(작혼의 로비 자리).
///
/// 왼쪽: 큰 "대국 시작"(설정 폼 → 시작하면 테이블 화면) + 최근 대국 한 판(누르면 종료 화면).
/// 오른쪽: 점수 계산·지난 대국·점수표·연습·룰 설정·카메라 헤드 타일.
class KioskLobby extends StatelessWidget {
  final HandEditor editor;
  const KioskLobby({super.key, required this.editor});

  void _push(BuildContext context, Widget screen) =>
      Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: kioskDarkTheme(),
      child: Scaffold(
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(32, 24, 32, 24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  children: [
                    const Icon(Icons.grid_view_rounded, color: kioskGold, size: 30),
                    const SizedBox(width: 12),
                    const Text(
                      '마작 점수 계산기',
                      style: TextStyle(fontSize: 28, fontWeight: FontWeight.w800, color: Colors.white, letterSpacing: 1),
                    ),
                    const Spacer(),
                    OutlinedButton.icon(
                      key: const ValueKey('lobby-survey'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: kioskGold,
                        side: const BorderSide(color: kioskGold),
                        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
                        textStyle: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
                      ),
                      icon: const Icon(Icons.qr_code_2),
                      label: const Text('설문 참여'),
                      onPressed: () => showSurveyQr(context),
                    ),
                  ],
                ),
                const SizedBox(height: 24),
                Expanded(
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Expanded(
                        flex: 11,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Expanded(flex: 3, child: _startCard(context)),
                            const SizedBox(height: 16),
                            Expanded(flex: 2, child: _recentCard(context)),
                          ],
                        ),
                      ),
                      const SizedBox(width: 24),
                      Expanded(flex: 9, child: _menuGrid(context)),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _startCard(BuildContext context) {
    final g = gameStore.current;
    if (g != null) return _continueCard(context, g);
    return Material(
      key: const ValueKey('lobby-start'),
      borderRadius: BorderRadius.circular(24),
      clipBehavior: Clip.antiAlias,
      child: Ink(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xFFF0D48C), kioskGoldDeep],
          ),
        ),
        child: InkWell(
          onTap: () => _push(context, const GameScreen()),
          child: const Padding(
            padding: EdgeInsets.symmetric(horizontal: 36, vertical: 24),
            child: Row(
              children: [
                Icon(Icons.play_circle_fill_rounded, size: 96, color: Color(0xFF2A1F08)),
                SizedBox(width: 28),
                Expanded(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '대국 시작',
                        style: TextStyle(fontSize: 52, fontWeight: FontWeight.w900, color: Color(0xFF2A1F08), height: 1.1),
                      ),
                      SizedBox(height: 10),
                      Text(
                        '이름·룰을 정하면 테이블 화면으로 넘어갑니다.\n중간부터 기록하려면 시작 화면에서 고르세요.',
                        style: TextStyle(fontSize: 17, color: Color(0xCC2A1F08), height: 1.4),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// 대국 중에 테이블의 "홈" 으로 나왔을 때: 누르면 테이블로 돌아가고, "대국 종료" 는 중간 정산 → 저장하고 종료.
  Widget _continueCard(BuildContext context, Game g) {
    const ink = Color(0xFF2A1F08);
    return Material(
      key: const ValueKey('lobby-continue'),
      borderRadius: BorderRadius.circular(24),
      clipBehavior: Clip.antiAlias,
      child: Ink(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xFFF0D48C), kioskGoldDeep],
          ),
        ),
        child: InkWell(
          onTap: () => kioskLobbyFor.value = null,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 36, vertical: 24),
            child: Row(
              children: [
                const Icon(Icons.play_circle_fill_rounded, size: 96, color: ink),
                const SizedBox(width: 28),
                Expanded(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        '대국 이어 하기',
                        style: TextStyle(fontSize: 48, fontWeight: FontWeight.w900, color: ink, height: 1.1),
                      ),
                      const SizedBox(height: 10),
                      Text(
                        '${g.roundLabel}  ·  '
                        '${[for (var s = 0; s < 4; s++) '${g.names[s]} ${g.scores[s]}'].join('  ')}',
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 17, color: Color(0xCC2A1F08), height: 1.4),
                      ),
                      const SizedBox(height: 14),
                      OutlinedButton.icon(
                        key: const ValueKey('lobby-end-game'),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: ink,
                          side: const BorderSide(color: ink),
                          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
                          textStyle: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
                        ),
                        icon: const Icon(Icons.stop_circle_outlined),
                        label: const Text('대국 종료 (정산)'),
                        onPressed: () => _push(context, SettlementScreen(game: g)),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// 가장 최근에 끝난 대국 한 판(순위·이름·점수). 없으면 안내.
  Widget _recentCard(BuildContext context) {
    return ListenableBuilder(
      listenable: gameStore,
      builder: (context, _) {
        final Game? last = gameStore.history.isEmpty ? null : gameStore.history.first;
        return Material(
          key: const ValueKey('lobby-recent'),
          color: kioskSurface,
          borderRadius: BorderRadius.circular(20),
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            onTap: last == null ? null : () => _push(context, SettlementScreen(game: last)),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(24, 16, 16, 16),
              child: last == null
                  ? const Center(
                      child: Text('아직 기록한 대국이 없습니다', style: TextStyle(fontSize: 18, color: Colors.white54)),
                    )
                  : _recentBody(context, last),
            ),
          ),
        );
      },
    );
  }

  Widget _recentBody(BuildContext context, Game g) {
    final rows = g.settle();
    final d = g.startedAt;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            const Text('최근 대국', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700, color: Colors.white)),
            const SizedBox(width: 12),
            Text(
              '${d.month}/${d.day} ${d.hour}:${d.minute.toString().padLeft(2, '0')} · ${g.roundLabel}',
              style: const TextStyle(fontSize: 14, color: Colors.white54),
            ),
            const Spacer(),
            TextButton(
              onPressed: () => _push(context, const HistoryScreen()),
              child: const Text('전체 보기', style: TextStyle(fontSize: 15)),
            ),
          ],
        ),
        const SizedBox(height: 4),
        Expanded(
          child: Row(
            children: [
              for (final r in rows)
                Expanded(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(
                        '${r.rank}위',
                        style: TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w700,
                          color: r.rank == 1 ? kioskGold : Colors.white54,
                        ),
                      ),
                      Text(
                        r.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: Colors.white),
                      ),
                      Text(
                        '${r.points} (${_fmt(r.score)})',
                        style: TextStyle(fontSize: 14, color: r.score < 0 ? const Color(0xFFFF8A80) : const Color(0xFF8CE6A6)),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _menuGrid(BuildContext context) {
    final items = <(String, IconData, String, Widget Function())>[
      ('calc', Icons.calculate_outlined, '점수 계산', () => InputScreen(editor: editor)),
      ('history', Icons.history, '지난 대국', () => const HistoryScreen()),
      ('table', Icons.table_chart_outlined, '점수표', () => ScoreTableScreen(rules: editor.rules)),
      ('quiz', Icons.school_outlined, '점수 계산 연습', () => QuizScreen(rules: editor.rules)),
      ('settings', Icons.tune, '룰 설정', () => SettingsScreen(editor: editor)),
      ('head', Icons.videocam_outlined, '카메라 헤드', () => const CameraHeadScreen()),
    ];
    return LayoutBuilder(builder: (context, c) {
      const gap = 16.0;
      final w = (c.maxWidth - gap) / 2;
      final h = (c.maxHeight - gap * 2) / 3;
      return Wrap(
        spacing: gap,
        runSpacing: gap,
        children: [
          for (final (key, icon, label, screen) in items)
            SizedBox(
              width: w,
              height: h,
              child: Material(
                key: ValueKey('lobby-$key'),
                color: kioskSurface,
                borderRadius: BorderRadius.circular(20),
                clipBehavior: Clip.antiAlias,
                child: InkWell(
                  onTap: () => _push(context, screen()),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(icon, size: 44, color: kioskGold),
                      const SizedBox(height: 10),
                      Text(label, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600, color: Colors.white)),
                    ],
                  ),
                ),
              ),
            ),
        ],
      );
    });
  }
}

String _fmt(double v) {
  final s = v == v.roundToDouble() ? v.toInt().toString() : v.toStringAsFixed(1);
  return v > 0 ? '+$s' : s;
}
