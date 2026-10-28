import 'dart:async';

import 'package:flutter/material.dart';

import '../../game/game.dart';
import '../../game/game_store.dart';
import '../kiosk.dart';
import 'record_edit.dart';

/// 대국 종료(정산) 화면. 작혼의 종국 화면 구조를 따른다(그림·글꼴은 우리 것).
///
/// 가로로 넓으면 왼쪽에 1위 패널(작혼은 1위 캐릭터 자리), 오른쪽에 순위 띠가 계단식으로 쌓인다.
/// 띠마다 순위·이름·최종 점수·우마/오카 포함 득점. 폰 세로면 띠만 위아래로.
/// 띠가 1위부터 차례로 들어오고 점수가 올라간다(아무 데나 누르면 건너뜀).
/// 진행 중 대국이면 "저장하고 종료", 지난 대국이면 "확인".
class SettlementScreen extends StatefulWidget {
  final Game game;
  const SettlementScreen({super.key, required this.game});

  @override
  State<SettlementScreen> createState() => _SettlementScreenState();
}

class _SettlementScreenState extends State<SettlementScreen> with SingleTickerProviderStateMixin {
  static const _bg = Color(0xFF14161F);

  late final AnimationController _reveal =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 2200))..forward();

  // 되돌리기·정정으로 점수가 바뀌면 다시 그린다.
  void _onStore() => setState(() {});

  @override
  void initState() {
    super.initState();
    gameStore.addListener(_onStore);
  }

  @override
  void dispose() {
    gameStore.removeListener(_onStore);
    _reveal.dispose();
    super.dispose();
  }

  Animation<double> _step(double start, double end) =>
      CurvedAnimation(parent: _reveal, curve: Interval(start, end, curve: Curves.easeOutCubic));

  @override
  Widget build(BuildContext context) {
    final g = widget.game;
    final rows = g.settle();
    final live = !g.finished;
    final title = g.isOver ? g.endLabel : (live ? '중간 정산' : '대국 종료');
    final stats = _GameStats.of(g);

    return Theme(
      data: kioskDarkTheme().copyWith(scaffoldBackgroundColor: _bg),
      child: Scaffold(
        body: Stack(
          fit: StackFit.expand,
          children: [
            const DecoratedBox(
              decoration: BoxDecoration(
                gradient: RadialGradient(
                  center: Alignment(-0.6, -0.2),
                  radius: 1.2,
                  colors: [Color(0xFF2B2A3A), _bg],
                ),
              ),
            ),
            SafeArea(
              child: GestureDetector(
                behavior: HitTestBehavior.translucent,
                onTap: _reveal.isCompleted ? null : () => _reveal.value = 1,
                child: LayoutBuilder(builder: (context, c) {
                  final wide = c.maxWidth >= 900 && c.maxWidth > c.maxHeight;
                  return Padding(
                    padding: EdgeInsets.fromLTRB(wide ? 24 : 12, 8, wide ? 24 : 12, 12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        _header(context, title, wide),
                        Expanded(
                          child: wide
                              ? Row(
                                  children: [
                                    Expanded(flex: 4, child: _winnerPanel(g, rows.first, stats)),
                                    const SizedBox(width: 16),
                                    Expanded(flex: 7, child: Center(child: _banners(g, rows, stats, wide: true))),
                                  ],
                                )
                              : SingleChildScrollView(
                                  padding: const EdgeInsets.only(top: 12),
                                  child: _banners(g, rows, stats, wide: false),
                                ),
                        ),
                        const SizedBox(height: 8),
                        _footer(context, g, live, wide),
                      ],
                    ),
                  );
                }),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _header(BuildContext context, String title, bool wide) {
    final g = widget.game;
    final d = g.startedAt;
    return Row(
      children: [
        IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white70),
          onPressed: () => Navigator.of(context).maybePop(),
        ),
        Expanded(
          child: Text(
            title,
            key: const ValueKey('settle-title'),
            textAlign: wide ? TextAlign.center : TextAlign.start,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: wide ? 34 : 20,
              fontWeight: FontWeight.w800,
              color: Colors.white,
              letterSpacing: 2,
              shadows: const [Shadow(color: Color(0x99000000), blurRadius: 8, offset: Offset(0, 2))],
            ),
          ),
        ),
        Text(
          '${g.roundLabel} · ${d.month}/${d.day} ${d.hour}:${d.minute.toString().padLeft(2, '0')}',
          style: TextStyle(fontSize: wide ? 15 : 12, color: Colors.white60),
        ),
        const SizedBox(width: 8),
      ],
    );
  }

  /// 작혼에서 1위 캐릭터가 서는 자리. 우리는 트로피 + 1위 이름·점수·득점.
  Widget _winnerPanel(Game g, Settlement top, _GameStats stats) {
    final a = _step(0.7, 1.0);
    return AnimatedBuilder(
      animation: a,
      builder: (_, child) => Opacity(
        opacity: a.value,
        child: Transform.scale(scale: 0.9 + 0.1 * a.value, child: child),
      ),
      child: Column(
        key: const ValueKey('settle-winner'),
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 150,
            height: 150,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: const RadialGradient(colors: [Color(0x66E2C178), Color(0x00E2C178)]),
              border: Border.all(color: kioskGold.withValues(alpha: 0.6), width: 2),
            ),
            child: const Icon(Icons.emoji_events, size: 88, color: kioskGold),
          ),
          const SizedBox(height: 12),
          const Text('1위', style: TextStyle(fontSize: 20, color: kioskGold, fontWeight: FontWeight.w700, letterSpacing: 4)),
          const SizedBox(height: 4),
          Text(
            top.name,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 44, fontWeight: FontWeight.w900, color: Colors.white, height: 1.1),
          ),
          const SizedBox(height: 8),
          Text(
            '${top.points}점  ${_fmt(top.score)}',
            style: const TextStyle(fontSize: 22, color: Colors.white70, fontFeatures: [FontFeature.tabularFigures()]),
          ),
          const SizedBox(height: 4),
          Text(
            stats.line(top.seat),
            style: const TextStyle(fontSize: 15, color: Colors.white54),
          ),
        ],
      ),
    );
  }

  /// 순위 띠 넷. 아래로 갈수록 오른쪽으로 들여 계단처럼.
  Widget _banners(Game g, List<Settlement> rows, _GameStats stats, {required bool wide}) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final r in rows)
          Padding(
            padding: EdgeInsets.only(left: (r.rank - 1) * (wide ? 36.0 : 12.0), bottom: wide ? 14 : 10),
            child: _slideIn(r.rank - 1, _RankBanner(
              key: ValueKey('settle-rank-${r.rank}'),
              row: r,
              seatLabel: '기동 ${Game.windNames[r.seat]}',
              stats: stats.line(r.seat),
              start: g.settings.startPoints,
              countUp: _step(0.1, 0.75),
              scoreIn: _step(0.7, 0.85),
              wide: wide,
            )),
          ),
      ],
    );
  }

  Widget _slideIn(int i, Widget child) {
    final a = _step(i * 0.12, 0.3 + i * 0.12);
    return AnimatedBuilder(
      animation: a,
      builder: (_, child) => Opacity(
        opacity: a.value,
        child: FractionalTranslation(translation: Offset(0.4 * (1 - a.value), 0), child: child),
      ),
      child: child,
    );
  }

  Widget _footer(BuildContext context, Game g, bool live, bool wide) {
    final s = g.settings;
    final rules = Text(
      '시작 ${s.startPoints} · 반환 ${s.returnPoints} · 우마 ${s.umaBig}-${s.umaSmall} · 오카 ${s.oka}'
      ' · ${s.roundingMode == 1 ? '오사육입' : '소수 1자리'} · 기록 ${g.events.length}건',
      style: TextStyle(fontSize: wide ? 14 : 11, color: Colors.white54),
    );
    final buttonStyle = FilledButton.styleFrom(
      padding: EdgeInsets.symmetric(horizontal: wide ? 36 : 20, vertical: wide ? 18 : 12),
      textStyle: TextStyle(fontSize: wide ? 20 : 16, fontWeight: FontWeight.w700),
    );
    final buttons = Wrap(
      spacing: 12,
      runSpacing: 8,
      alignment: WrapAlignment.end,
      children: [
        if (live) ...[
          // 잘못 기록해서 끝났으면 바로 되돌린다(종료가 풀리면 이 화면을 닫는다).
          if (g.canUndo && identical(gameStore.current, g))
            TextButton.icon(
              key: const ValueKey('settle-undo'),
              style: TextButton.styleFrom(
                padding: EdgeInsets.symmetric(horizontal: wide ? 20 : 12, vertical: wide ? 18 : 12),
                textStyle: TextStyle(fontSize: wide ? 18 : 15),
              ),
              icon: const Icon(Icons.undo),
              label: const Text('마지막 기록 취소'),
              onPressed: () async {
                if (await confirmRewind(context) && context.mounted && !g.isOver) Navigator.of(context).pop();
              },
            ),
          OutlinedButton(
            style: OutlinedButton.styleFrom(
              padding: EdgeInsets.symmetric(horizontal: wide ? 28 : 16, vertical: wide ? 18 : 12),
              textStyle: TextStyle(fontSize: wide ? 18 : 15),
            ),
            onPressed: () => Navigator.of(context).maybePop(),
            child: const Text('돌아가기'),
          ),
          FilledButton(
            key: const ValueKey('settle-finish'),
            style: buttonStyle,
            onPressed: () {
              gameStore.finish();
              Navigator.of(context).pop();
            },
            child: const Text('저장하고 종료'),
          ),
        ] else
          FilledButton(
            style: buttonStyle,
            onPressed: () => Navigator.of(context).maybePop(),
            child: const Text('확인'),
          ),
      ],
    );
    if (!wide) {
      return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [rules, const SizedBox(height: 8), buttons]);
    }
    return Row(children: [Expanded(child: rules), buttons]);
  }
}

/// 순위 띠 하나(사선 평행사변형). 순위 · 이름(기동 자리·화료 기록) · 최종 점수 · 득점.
class _RankBanner extends StatelessWidget {
  final Settlement row;
  final String seatLabel;
  final String stats;
  final int start;
  final Animation<double> countUp;
  final Animation<double> scoreIn;
  final bool wide;

  const _RankBanner({
    super.key,
    required this.row,
    required this.seatLabel,
    required this.stats,
    required this.start,
    required this.countUp,
    required this.scoreIn,
    required this.wide,
  });

  static const _colors = [
    [Color(0xFFF0D48C), Color(0xFFB8913E)],
    [Color(0xFF8FA3B8), Color(0xFF4F6075)],
    [Color(0xFFB98A60), Color(0xFF6F4A2C)],
    [Color(0xFF4A4D57), Color(0xFF2B2D34)],
  ];

  @override
  Widget build(BuildContext context) {
    final first = row.rank == 1;
    final ink = first ? const Color(0xFF2A1F08) : Colors.white;
    final sub = first ? const Color(0xB32A1F08) : Colors.white70;
    final busted = row.points < 0;
    final h = wide ? (first ? 104.0 : 86.0) : (first ? 78.0 : 66.0);
    final skew = h * 0.3;
    final pos = first ? const Color(0xFF1B5E20) : const Color(0xFF8CE6A6);
    final neg = first ? const Color(0xFFB71C1C) : const Color(0xFFFF8A80);

    return SizedBox(
      height: h,
      child: Stack(
        children: [
          Positioned.fill(
            child: ClipPath(
              clipper: _SlantClipper(skew),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(colors: _colors[row.rank - 1]),
                  boxShadow: const [BoxShadow(color: Color(0x80000000), blurRadius: 10)],
                ),
              ),
            ),
          ),
          Padding(
            padding: EdgeInsets.fromLTRB(skew * 0.6, 0, skew + 8, 0),
            child: Row(
              children: [
                SizedBox(
                  width: wide ? 72 : 48,
                  child: Text.rich(
                    TextSpan(children: [
                      TextSpan(
                        text: '${row.rank}',
                        style: TextStyle(fontSize: wide ? (first ? 60 : 48) : 36, fontWeight: FontWeight.w900, fontStyle: FontStyle.italic),
                      ),
                      TextSpan(text: '위', style: TextStyle(fontSize: wide ? 18 : 13, fontWeight: FontWeight.w700)),
                    ]),
                    style: TextStyle(color: ink, height: 1, shadows: first ? null : const [Shadow(color: Color(0x80000000), blurRadius: 6)]),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        row.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(fontSize: wide ? 24 : 18, fontWeight: FontWeight.w800, color: ink),
                      ),
                      Text(
                        stats.isEmpty ? seatLabel : '$seatLabel · $stats',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(fontSize: wide ? 14 : 11, color: sub),
                      ),
                    ],
                  ),
                ),
                if (busted)
                  Container(
                    margin: const EdgeInsets.only(right: 8),
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(color: const Color(0xFFC62828), borderRadius: BorderRadius.circular(4)),
                    child: Text('토비', style: TextStyle(fontSize: wide ? 14 : 11, color: Colors.white, fontWeight: FontWeight.w800)),
                  ),
                AnimatedBuilder(
                  animation: countUp,
                  builder: (_, _) => Text(
                    '${(start + (row.points - start) * countUp.value).round()}',
                    style: TextStyle(
                      fontSize: wide ? (first ? 46 : 38) : 26,
                      fontWeight: FontWeight.w900,
                      color: busted ? neg : ink,
                      fontFeatures: const [FontFeature.tabularFigures()],
                    ),
                  ),
                ),
                SizedBox(
                  width: wide ? 110 : 66,
                  child: FadeTransition(
                    opacity: scoreIn,
                    child: Text(
                      _fmt(row.score),
                      key: ValueKey('settle-score-${row.rank}'),
                      textAlign: TextAlign.right,
                      style: TextStyle(
                        fontSize: wide ? 26 : 17,
                        fontWeight: FontWeight.w800,
                        color: row.score < 0 ? neg : pos,
                        fontFeatures: const [FontFeature.tabularFigures()],
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SlantClipper extends CustomClipper<Path> {
  final double skew;
  const _SlantClipper(this.skew);

  @override
  Path getClip(Size s) => Path()
    ..moveTo(skew, 0)
    ..lineTo(s.width, 0)
    ..lineTo(s.width - skew, s.height)
    ..lineTo(0, s.height)
    ..close();

  @override
  bool shouldReclip(_SlantClipper old) => old.skew != skew;
}

/// 자리별 화료 횟수·가장 큰 화료(본장·공탁 포함 받은 점수). 기록의 'win' 사건에서 센다.
class _GameStats {
  final List<int> wins;
  final List<int> best;
  const _GameStats(this.wins, this.best);

  factory _GameStats.of(Game g) {
    final wins = List.filled(4, 0);
    final best = List.filled(4, 0);
    for (final e in g.events) {
      if (e.kind != 'win') continue;
      for (var s = 0; s < 4; s++) {
        if (e.delta[s] <= 0) continue;
        wins[s]++;
        if (e.delta[s] > best[s]) best[s] = e.delta[s];
      }
    }
    return _GameStats(wins, best);
  }

  String line(int seat) => wins[seat] == 0 ? '화료 없음' : '화료 ${wins[seat]} · 최고 +${best[seat]}';
}

String _fmt(double v) {
  final s = v == v.roundToDouble() ? v.toInt().toString() : v.toStringAsFixed(1);
  return v > 0 ? '+$s' : s;
}

/// 작혼처럼 대국이 끝나면 종료 화면을 자동으로 띄운다.
///
/// 진행 중이던 대국이 끝난 순간(토비·아가리야메·종료…) 이 화면이 맨 위면 바로, 시트·결과 화면 아래에 있으면
/// 그것들이 닫혀 이 화면으로 돌아올 때 띄운다. 처음부터 끝난 채 불러온 대국은 띄우지 않는다(점수판의 "정산" 버튼).
/// 한 대국에 한 번만.
final gameRouteObserver = RouteObserver<ModalRoute<void>>();

class GameEndWatcher extends StatefulWidget {
  final Widget child;
  const GameEndWatcher({super.key, required this.child});

  @override
  State<GameEndWatcher> createState() => _GameEndWatcherState();
}

class _GameEndWatcherState extends State<GameEndWatcher> with RouteAware {
  /// 진행 중(끝나지 않은)으로 본 적 있는 대국, 종료 화면을 이미 띄운 대국.
  static final _seenLive = <String>{};
  static final _shown = <String>{};

  ModalRoute<void>? _route;

  @override
  void initState() {
    super.initState();
    gameStore.addListener(_check);
    _check();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final r = ModalRoute.of(context);
    if (r != null && r != _route) {
      if (_route != null) gameRouteObserver.unsubscribe(this);
      _route = r;
      gameRouteObserver.subscribe(this, r);
    }
  }

  @override
  void dispose() {
    gameStore.removeListener(_check);
    gameRouteObserver.unsubscribe(this);
    super.dispose();
  }

  @override
  void didPopNext() => _check();

  void _check() {
    final g = gameStore.current;
    if (g == null) return;
    if (!g.isOver) {
      _seenLive.add(g.id);
      _shown.remove(g.id); // 되돌리기로 다시 진행 중이 되면, 다시 끝날 때 또 띄운다.
      return;
    }
    if (!_seenLive.contains(g.id) || _shown.contains(g.id)) return;
    // 기록하는 시트·결과 화면이 닫힌 뒤(이 화면이 맨 위일 때) 띄운다.
    scheduleMicrotask(() {
      if (!mounted || _shown.contains(g.id)) return;
      if (!(_route?.isCurrent ?? true)) return;
      if (gameStore.current?.id != g.id) return;
      _shown.add(g.id);
      Navigator.of(context).push(MaterialPageRoute(builder: (_) => SettlementScreen(game: g)));
    });
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
