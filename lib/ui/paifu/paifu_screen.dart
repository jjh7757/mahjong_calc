import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../engine/hand.dart';
import '../../engine/tile.dart';
import '../../paifu/paifu.dart';
import '../../paifu/paifu_score.dart';
import '../../paifu/paifu_store.dart';
import '../../paifu/start_hand.dart';
import '../kiosk.dart';
import '../result_screen.dart';
import '../settings_screen.dart';
import 'review_view.dart';
import 'start_hand_sheet.dart';
import '../tile_view.dart';

const _winds = ['동', '남', '서', '북'];
const _tableFelt = Color(0xFF1F4D3A);
const _centerBg = Color(0xFF12241D);
const _backColor = Color(0xFFD8A23A);

String _tileName(PaifuTile t) => t.red ? '적${Tiles.name(t.tile)}' : Tiles.name(t.tile);

/// 묶음 그림(assets)에 든 패보 한 판을 읽어 재생 화면으로 연다.
class PaifuAssetScreen extends StatefulWidget {
  final String asset;
  const PaifuAssetScreen({super.key, required this.asset});

  static Future<Paifu> load(String asset, {AssetBundle? bundle}) async =>
      Paifu.fromJson(jsonDecode(await (bundle ?? rootBundle).loadString(asset)) as Map<String, dynamic>);

  @override
  State<PaifuAssetScreen> createState() => _PaifuAssetScreenState();
}

class _PaifuAssetScreenState extends State<PaifuAssetScreen> {
  late final Future<Paifu> _paifu = PaifuAssetScreen.load(widget.asset);

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Paifu>(
      future: _paifu,
      builder: (context, snap) {
        if (snap.hasData) return PaifuScreen(paifu: snap.data!);
        return kioskWrap(
          context,
          Scaffold(
            appBar: AppBar(title: const Text('패보')),
            body: Center(
              child: snap.hasError ? Text('패보를 읽지 못했습니다\n${snap.error}') : const CircularProgressIndicator(),
            ),
          ),
        );
      },
    );
  }
}

/// 패보 재생: 한 사람(hero)의 매 순 손패 + 네 자리의 버림을 걸음마다 넘겨 본다.
class PaifuScreen extends StatefulWidget {
  final Paifu paifu;

  /// 리뷰 카드의 엔진 참고값을 뒤에서 내는 함수(기본 [computeEngineReview]). 시험에서 바꿔 끼운다.
  final EngineReviewRunner engineReview;
  const PaifuScreen({super.key, required this.paifu, this.engineReview = computeEngineReview});

  @override
  State<PaifuScreen> createState() => _PaifuScreenState();
}

class _PaifuScreenState extends State<PaifuScreen> {
  static const _rowH = 40.0;
  static const _speeds = [(2000, '느리게'), (1000, '보통'), (400, '빠르게')];

  int _step = 0;
  Timer? _timer;
  int _intervalMs = 1000;
  final _log = ScrollController();

  Paifu get _p => widget.paifu;
  int get _last => _p.states.length - 1;
  bool get _playing => _timer != null;

  /// 끝 걸음의 점수 계산(화료로 끝났고 끝 손패가 적힌 패보만). 룰 설정을 읽으면 그 룰로 다시 낸다.
  RuleSet _rules = RuleSet.standard;
  late PaifuScore? _score = scoreOf(_p);
  bool _resultOpen = false;

  /// hero 버림마다의 평가. 숫자 있는 차례가 없는 판이면 리뷰 위젯을 그리지 않는다.
  /// 처음엔 엔진 없이(빠름) 그리고, 뒤에서 낸 엔진 포함 평가가 오면 바꾼다(등급은 같고 참고값만 더해짐).
  late PaifuReviewIndex _review = PaifuReviewIndex.of(_p);
  EngineReviewStatus _engine = EngineReviewStatus.off;
  Timer? _engineTimer;

  @override
  void initState() {
    super.initState();
    _loadRules();
    _loadStartHand();
    _startEngineReview();
  }

  /// 엔진 참고값 계산(한 판 수 초). 첫 화면을 그린 뒤 조금 있다 시작한다 — 웹은 compute 가 같은 스레드에서 돈다.
  /// 실패하면 조용히 "계산 중" 줄만 지우고, 화면을 떠났으면 결과를 버린다.
  void _startEngineReview() {
    if (!_review.hasNumbers) return;
    _engine = EngineReviewStatus.pending;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _engineTimer = Timer(const Duration(milliseconds: 100), _runEngineReview);
    });
  }

  Future<void> _runEngineReview() async {
    _engineTimer = null;
    try {
      final r = await widget.engineReview(_p);
      if (!mounted) return;
      setState(() {
        _review = PaifuReviewIndex.fromReview(r);
        _engine = EngineReviewStatus.ready;
      });
    } catch (_) {
      if (mounted) setState(() => _engine = EngineReviewStatus.failed);
    }
  }

  /// 시작 손패(사람이 넣음)와 그것으로 헤아린 매 순 손패. 판 중 손패가 이미 적힌 패보에는 쓰지 않는다.
  List<PaifuTile> _startHand = const [];
  StartHandInference? _infer;
  String get _startKey => 'paifu.startHand.${_p.id}';

  Future<void> _loadStartHand() async {
    if (_p.hasHeroHands) return;
    try {
      final saved = (await SharedPreferences.getInstance()).getString(_startKey);
      if (saved == null || saved.isEmpty || !mounted) return;
      _applyStartHand([for (final c in saved.split(' ')) PaifuTile.parse(c)], save: false);
    } catch (_) {
      // 저장소를 못 읽거나 옛 값이 깨졌으면 없는 것으로.
    }
  }

  void _applyStartHand(List<PaifuTile> tiles, {bool save = true}) {
    setState(() {
      _startHand = tiles;
      _infer = tiles.isEmpty ? null : StartHandInference.infer(_p, tiles);
    });
    if (save) _saveStartHand(tiles);
  }

  Future<void> _saveStartHand(List<PaifuTile> tiles) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      if (tiles.isEmpty) {
        await prefs.remove(_startKey);
      } else {
        await prefs.setString(_startKey, [for (final t in tiles) t.code].join(' '));
      }
    } catch (_) {}
  }

  Future<void> _editStartHand() async {
    _stop();
    final picked = await showStartHandSheet(context, initial: _startHand, who: _seatLabel(_p.hero));
    if (picked == null || !mounted) return;
    _applyStartHand(picked);
  }

  /// 지금 걸음의 손패 요약: 확정·모름·후보, 이 순에 뽑은 패(정해지면), 전체에서 다 정해진 순.
  String _startSummary(PaifuState state) {
    final inf = _infer!;
    final v = inf.viewAt(_p, state.step)!;
    final e = state.event;
    final mine = e != null && e.type == PaifuEventType.discard && e.seat == _p.hero;
    final parts = [
      v.complete ? '손패 13장 확정' : '확정 ${v.known.length}장 · 모름 ${v.unknown}장',
      if (v.candidates.isNotEmpty) '후보 ${v.candidates.map(_tileName).join(' ')}',
      if (mine && v.drew != null) '이 순에 뽑은 패 ${_tileName(v.drew!)}',
    ];
    final all = inf.exact
        ? '${inf.turns}순 중 ${inf.completeTurns}순은 손패가 다 정해짐'
        : '끝 손패가 없는 판이라 시작 패 가운데 아직 안 버린 패만 확정';
    return '${parts.join(' · ')}\n$all';
  }

  Future<void> _loadRules() async {
    try {
      final r = await RulesStore.load();
      if (!mounted) return;
      setState(() {
        _rules = r;
        _score = scoreOf(_p, rules: r);
      });
    } catch (_) {
      // 저장소를 못 읽으면 기본 룰 그대로.
    }
  }

  /// 점수 결과 화면(점수 계산기와 같은 화면, 보기 전용 — 지금 대국에 반영하지 않는다).
  Future<void> _showResult() async {
    final s = _score;
    // 화료형이 아니거나 역이 없는 기록(오독 등)은 결과 화면을 띄우지 않고 까닭만 옆에 적는다.
    if (s == null || !s.result.isValid || _resultOpen || !mounted) return;
    _resultOpen = true;
    await Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ResultScreen(
        result: s.result,
        hand: s.hand,
        situation: s.situation,
        isTsumo: s.situation.isTsumo,
        seatWind: s.situation.seatWind,
        winnerRiichi: s.situation.riichi || s.situation.doubleRiichi,
        rules: _rules,
        viewOnly: true,
      ),
    ));
    _resultOpen = false;
  }

  /// 한 걸음 앞으로. 이미 끝이면 점수 결과 화면.
  void _next() => _step == _last ? _showResult() : _go(_step + 1);

  @override
  void dispose() {
    _timer?.cancel();
    _engineTimer?.cancel();
    _log.dispose();
    super.dispose();
  }

  void _go(int step) {
    final s = step.clamp(0, _last);
    if (s == _step) return;
    setState(() => _step = s);
    if (s == _last) {
      // 자동 재생이 끝까지 가면 점수를 계산해 결과 화면을 띄운다. 손으로 넘겨 온 끝 걸음에서는 단추·"다음" 으로.
      final played = _playing;
      _stop();
      if (played) _showResult();
    }
    if (_log.hasClients) {
      final target = ((s - 2) * _rowH).clamp(0.0, _log.position.maxScrollExtent);
      _log.animateTo(target, duration: const Duration(milliseconds: 150), curve: Curves.easeOut);
    }
  }

  void _stop() {
    if (_timer == null) return;
    _timer!.cancel();
    setState(() => _timer = null);
  }

  void _play() {
    _timer?.cancel();
    setState(() {
      if (_step == _last) _step = 0;
      _timer = Timer.periodic(Duration(milliseconds: _intervalMs), (_) => _go(_step + 1));
    });
  }

  void _setSpeed(int ms) {
    setState(() => _intervalMs = ms);
    if (_playing) _play();
  }

  /// 내 차례(hero 가 뽑은 걸음) 단위로 넘긴다.
  void _heroTurn(int dir) {
    final steps = _p.heroTurnSteps;
    if (dir > 0) {
      final next = steps.where((s) => s > _step);
      _go(next.isEmpty ? _last : next.first);
    } else {
      final prev = steps.where((s) => s < _step);
      _go(prev.isEmpty ? 0 : prev.last);
    }
  }

  String _seatLabel(int seat) {
    final name = _p.names[seat];
    return '${_winds[_p.windOf(seat)]}${name.isEmpty ? '' : ' $name'}';
  }

  /// 걸음 한 줄 설명.
  String _describe(PaifuState s) {
    final e = s.event;
    if (e == null) {
      if (!s.finished) return '시작';
      final r = _p.result!;
      final win = r.winTile == null ? '' : ' (${_tileName(r.winTile!)})';
      return switch (r.type) {
        'ron' => '론$win — ${_seatLabel(r.winner!)} ← ${_seatLabel(r.loser!)}',
        'tsumo' => '쯔모$win — ${_seatLabel(r.winner!)}',
        _ => '유국',
      };
    }
    final who = _seatLabel(e.seat);
    switch (e.type) {
      case PaifuEventType.draw:
        return '$who · ${e.tile == null ? '패' : _tileName(e.tile!)} 뽑음';
      case PaifuEventType.discard:
        final how = e.tsumogiri == null ? '' : (e.tsumogiri! ? ' (쯔모기리)' : ' (손에서)');
        return '$who · ${_tileName(e.tile!)} 버림$how${e.riichi ? ' · 리치' : ''}';
      case PaifuEventType.call:
        final kind = switch (e.callKind) { 'chi' => '치', 'pon' => '퐁', 'call' => '울기', _ => '깡' };
        return '$who · $kind ${e.callTiles.map(_tileName).join(' ')}';
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = _p.states[_step];
    final title = _p.title.isNotEmpty ? _p.title : '패보';
    return kioskWrap(
      context,
      Scaffold(
        appBar: AppBar(title: Text(title)),
        body: CallbackShortcuts(
          bindings: {
            const SingleActivator(LogicalKeyboardKey.arrowRight): _next,
            const SingleActivator(LogicalKeyboardKey.arrowLeft): () => _go(_step - 1),
            const SingleActivator(LogicalKeyboardKey.arrowDown): () => _heroTurn(1),
            const SingleActivator(LogicalKeyboardKey.arrowUp): () => _heroTurn(-1),
            const SingleActivator(LogicalKeyboardKey.space): () => _playing ? _stop() : _play(),
          },
          child: Focus(
            autofocus: true,
            child: SafeArea(
              child: LayoutBuilder(
                builder: (context, box) {
                  final table = PaifuTableView(paifu: _p, state: state, heroView: _infer?.viewAt(_p, state.step));
                  final wide = box.maxWidth > box.maxHeight * 1.2;
                  if (wide) {
                    final panelW = (box.maxWidth * 0.34).clamp(300.0, 460.0);
                    return Row(
                      children: [
                        Expanded(child: Padding(padding: const EdgeInsets.all(8), child: Center(child: table))),
                        SizedBox(width: panelW, child: _panel(context, state)),
                      ],
                    );
                  }
                  return Column(
                    children: [
                      Padding(
                        padding: const EdgeInsets.all(6),
                        child: SizedBox(height: box.maxHeight * 0.56, child: Center(child: table)),
                      ),
                      Expanded(child: _panel(context, state)),
                    ],
                  );
                },
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _panel(BuildContext context, PaifuState state) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 8, 12, 8),
      child: _fitPanel(Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            '${_p.round}${_p.honba > 0 ? ' ${_p.honba}본장' : ''} · ${state.turn}순 · ${_p.hasHeroHands ? '내 자리' : '아래 자리'} ${_seatLabel(_p.hero)}',
            style: theme.textTheme.bodyMedium?.copyWith(color: scheme.onSurfaceVariant),
          ),
          const SizedBox(height: 4),
          Text(
            _describe(state),
            key: const ValueKey('paifu-now'),
            style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
          Slider(
            value: _step.toDouble(),
            max: _last.toDouble(),
            divisions: _last > 0 ? _last : null,
            label: '$_step',
            onChanged: (v) => _go(v.round()),
          ),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              IconButton(tooltip: '처음', icon: const Icon(Icons.first_page), onPressed: () => _go(0)),
              IconButton(tooltip: '이전 내 차례', icon: const Icon(Icons.fast_rewind), onPressed: () => _heroTurn(-1)),
              IconButton(
                key: const ValueKey('paifu-prev'),
                tooltip: '이전',
                icon: const Icon(Icons.chevron_left),
                onPressed: () => _go(_step - 1),
              ),
              IconButton.filled(
                key: const ValueKey('paifu-play'),
                tooltip: _playing ? '멈춤' : '자동 재생',
                icon: Icon(_playing ? Icons.pause : Icons.play_arrow),
                onPressed: _playing ? _stop : _play,
              ),
              IconButton(
                key: const ValueKey('paifu-next'),
                tooltip: '다음',
                icon: const Icon(Icons.chevron_right),
                onPressed: _next,
              ),
              IconButton(tooltip: '다음 내 차례', icon: const Icon(Icons.fast_forward), onPressed: () => _heroTurn(1)),
              IconButton(tooltip: '끝', icon: const Icon(Icons.last_page), onPressed: () => _go(_last)),
            ],
          ),
          Row(
            children: [
              Text('$_step / $_last', style: theme.textTheme.bodySmall),
              const Spacer(),
              for (final (ms, label) in _speeds)
                Padding(
                  padding: const EdgeInsets.only(left: 4),
                  child: ChoiceChip(
                    label: Text(label),
                    selected: _intervalMs == ms,
                    visualDensity: VisualDensity.compact,
                    onSelected: (_) => _setSpeed(ms),
                  ),
                ),
            ],
          ),
          if (_review.hasNumbers) PaifuReviewPanel(index: _review, step: _step, onGo: _go, engine: _engine, seatLabel: _seatLabel),
          if (!_p.hasHeroHands)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  OutlinedButton.icon(
                    key: const ValueKey('paifu-start-hand'),
                    icon: const Icon(Icons.style_outlined),
                    label: Text(_startHand.isEmpty ? '시작 손패 입력' : '시작 손패 고치기'),
                    onPressed: _editStartHand,
                  ),
                  if (_infer?.error != null)
                    Text(
                      _infer!.error!,
                      key: const ValueKey('paifu-start-error'),
                      style: theme.textTheme.bodySmall?.copyWith(color: scheme.error),
                    )
                  else if (_infer != null)
                    Text(
                      _startSummary(state),
                      key: const ValueKey('paifu-start-summary'),
                      style: theme.textTheme.bodySmall,
                    ),
                ],
              ),
            ),
          if (state.finished && _score != null)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: _score!.result.isValid
                  ? FilledButton.icon(
                      key: const ValueKey('paifu-score'),
                      icon: const Icon(Icons.emoji_events_outlined),
                      label: Text('점수 결과 보기 · ${_score!.result.payment.total}점'),
                      onPressed: _showResult,
                    )
                  : Text(
                      '점수를 계산할 수 없는 기록입니다 — ${_score!.result.error}',
                      key: const ValueKey('paifu-score-error'),
                      style: theme.textTheme.bodySmall?.copyWith(color: scheme.error),
                    ),
            ),
          const SizedBox(height: 4),
          Text(
            '어두운 패 = 쯔모기리 · 누운 패 = 리치 선언 · 테두리 = 방금 버린 패',
            style: theme.textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
          ),
          if (_p.note.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                _p.note,
                style: theme.textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          const Divider(height: 12),
          Expanded(
            child: ListView.builder(
              controller: _log,
              itemExtent: _rowH,
              itemCount: _p.states.length,
              itemBuilder: (context, i) {
                final s = _p.states[i];
                final mine = s.event?.seat == _p.hero;
                final now = i == _step;
                return InkWell(
                  onTap: () => _go(i),
                  child: Container(
                    color: now ? scheme.primary.withAlpha(46) : null,
                    padding: const EdgeInsets.symmetric(horizontal: 8),
                    alignment: Alignment.centerLeft,
                    child: Row(
                      children: [
                        SizedBox(
                          width: 34,
                          child: Text('$i', style: theme.textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant)),
                        ),
                        Expanded(
                          child: Text(
                            _describe(s),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: theme.textTheme.bodyMedium?.copyWith(
                              fontWeight: now || mine ? FontWeight.w700 : FontWeight.w400,
                              color: mine ? scheme.primary : null,
                            ),
                          ),
                        ),
                        if (_review.hasNumbers && _review.byStep[i] != null && hasReviewBadge(_review.byStep[i]!))
                          Padding(
                            padding: const EdgeInsets.only(left: 4),
                            child: ReviewBadge(_review.byStep[i]!, key: ValueKey('paifu-badge-$i')),
                          ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      )),
    );
  }

  /// 리뷰가 붙는 판: 패널의 끝 두 칸(구분선 + 사건 목록 Expanded) 위의 칸들을 높이 상한 + 스크롤로 묶는다.
  /// 카드가 들어가도 좁은 화면에서 넘치지 않고(위 칸을 스크롤해 카드에 닿음), 사건 목록은 적어도 두세 줄 남는다.
  /// 다 들어가면 위 칸은 제 높이 그대로라 스크롤이 생기지 않는다. 패널 폭이 단추 7개 줄보다 좁으면(넓은 배치의
  /// 최소 폭 300) 위 칸을 그 폭으로 그려 줄여 보인다. 리뷰 없는 판은 [panel] 그대로.
  Widget _fitPanel(Column panel) {
    if (!_review.hasNumbers) return panel;
    const minW = 340.0;
    final n = panel.children.length;
    assert(panel.children.last is Expanded, '패널의 마지막 칸은 사건 목록(Expanded)이어야 합니다');
    final head = panel.children.sublist(0, n - 2);
    final tail = panel.children.sublist(n - 2);
    return LayoutBuilder(
      builder: (context, box) {
        final minLog = (box.maxHeight * 0.2).clamp(2 * _rowH, 4 * _rowH);
        Widget top = Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: head);
        if (box.maxWidth < minW) {
          top = FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.topLeft,
            child: SizedBox(width: minW, child: top),
          );
        }
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ConstrainedBox(
              constraints: BoxConstraints(maxHeight: (box.maxHeight - 12 - minLog).clamp(0.0, double.infinity)),
              child: SingleChildScrollView(key: const ValueKey('paifu-panel-scroll'), child: top),
            ),
            ...tail,
          ],
        );
      },
    );
  }
}

/// 탁자 그림: 가운데 판 정보, 네 자리의 강·리치봉·울기, 아래에 hero 손패.
///
/// 주어진 칸 안에서 가장 크게 그린다(가로 22.5 : 세로 23.6 단위).
class PaifuTableView extends StatelessWidget {
  final Paifu paifu;
  final PaifuState state;

  /// 시작 손패로 헤아린 hero 손패(확정 패 + 모르는 장수). 패보에 그 걸음의 손패가 적혀 있으면 그쪽을 쓴다.
  final HeroHandView? heroView;
  const PaifuTableView({super.key, required this.paifu, required this.state, this.heroView});

  int _seatAt(int side) => (paifu.hero + side) % 4;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, box) {
        // w = 강의 패 한 장 너비. 판 전체는 21.9w × 23w + 여백 0.3w.
        final byW = box.maxWidth.isFinite ? box.maxWidth / 22.5 : double.infinity;
        final byH = box.maxHeight.isFinite ? box.maxHeight / 23.6 : double.infinity;
        var w = byW < byH ? byW : byH;
        if (!w.isFinite) w = 28;
        final core = 19.7 * w;
        return MediaQuery(
          data: MediaQuery.of(context).copyWith(textScaler: TextScaler.noScaling),
          child: Container(
            width: 22.5 * w,
            height: 23.6 * w,
            padding: EdgeInsets.all(0.3 * w),
            decoration: BoxDecoration(color: _tableFelt, borderRadius: BorderRadius.circular(0.5 * w)),
            child: Column(
              children: [
                SizedBox(
                  height: 1.1 * w,
                  child: Center(child: RotatedBox(quarterTurns: 2, child: _sideStrip(_seatAt(2), w, core))),
                ),
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    RotatedBox(quarterTurns: 1, child: _sideStrip(_seatAt(3), w, core)),
                    _core(w, core),
                    RotatedBox(quarterTurns: 3, child: _sideStrip(_seatAt(1), w, core)),
                  ],
                ),
                _heroStrip(w),
              ],
            ),
          ),
        );
      },
    );
  }

  // ── 가운데 정사각형: 판 정보 + 네 자리의 강 ──

  Widget _core(double w, double side) {
    final c = 6.6 * w;
    return SizedBox(
      width: side,
      height: side,
      child: Stack(
        children: [
          for (var s = 0; s < 4; s++)
            Positioned.fill(
              // 아래 자리 기준으로 그린 층을 자리 쪽으로 돌린다(오른쪽 = 반시계 90°).
              child: RotatedBox(quarterTurns: (4 - s) % 4, child: _riverLayer(_seatAt(s), w, side, c)),
            ),
          Positioned(left: (side - c) / 2, top: (side - c) / 2, width: c, height: c, child: _center(w, c)),
        ],
      ),
    );
  }

  Widget _riverLayer(int seat, double w, double side, double c) {
    return Stack(
      children: [
        if (state.riichi[seat])
          Positioned(
            top: side / 2 + c / 2 + 0.15 * w,
            left: (side - 3.4 * w) / 2,
            width: 3.4 * w,
            height: 0.3 * w,
            child: _stick(w),
          ),
        Positioned(top: side / 2 + c / 2 + 0.6 * w, left: (side - c) / 2, child: _river(seat, w)),
      ],
    );
  }

  Widget _stick(double w) => Container(
        decoration: BoxDecoration(
          color: const Color(0xFFF4F1EA),
          borderRadius: BorderRadius.circular(0.15 * w),
          boxShadow: const [BoxShadow(color: Color(0x55000000), blurRadius: 2, offset: Offset(0, 1))],
        ),
        alignment: Alignment.center,
        child: Container(
          width: 0.16 * w,
          height: 0.16 * w,
          decoration: const BoxDecoration(color: kioskRed, shape: BoxShape.circle),
        ),
      );

  Widget _river(int seat, double w) {
    final all = state.rivers[seat];
    final shown = [
      for (final r in all)
        if (!r.called) r,
    ];
    final e = state.event;
    final r = paifu.result;
    // 방금 버린 패(울려 나가지 않았을 때), 또는 론 당한 패.
    final markLast = all.isNotEmpty &&
        !all.last.called &&
        ((e != null && e.type == PaifuEventType.discard && e.seat == seat) ||
            (state.finished && r != null && r.type == 'ron' && r.loser == seat));
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var row = 0; row * 6 < shown.length; row++)
          Padding(
            padding: EdgeInsets.only(bottom: 0.05 * w),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                for (var i = row * 6; i < shown.length && i < row * 6 + 6; i++)
                  Padding(
                    padding: EdgeInsets.only(right: 0.04 * w),
                    child: _riverTile(shown[i], w, markLast && i == shown.length - 1),
                  ),
              ],
            ),
          ),
      ],
    );
  }

  Widget _riverTile(PaifuRiverTile r, double w, bool last) {
    Widget t = TileView(r.tile.tile, red: r.tile.red, width: w, highlighted: last);
    if (r.tsumogiri == true) {
      t = Container(
        foregroundDecoration: BoxDecoration(color: const Color(0x52000000), borderRadius: BorderRadius.circular(w * 0.14)),
        child: t,
      );
    }
    if (last) t = _glow(t, w);
    if (r.riichi) t = RotatedBox(quarterTurns: 1, child: t);
    return t;
  }

  /// 방금 움직인 패에 두르는 금색 빛.
  Widget _glow(Widget tile, double width) => DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(width * 0.14),
          boxShadow: [BoxShadow(color: kioskGold, blurRadius: width * 0.22, spreadRadius: width * 0.07)],
        ),
        child: tile,
      );

  Widget _center(double w, double c) {
    final acting = state.event?.seat;
    final r = paifu.result;
    Widget label(int side) {
      final seat = _seatAt(side);
      final on = acting == seat || (state.finished && r?.winner == seat);
      final name = paifu.names[seat];
      return ConstrainedBox(
        constraints: BoxConstraints(maxWidth: c - 1.6 * w),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 0.62 * w,
              height: 0.62 * w,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: paifu.dealer == seat ? kioskRed : const Color(0xFF3A4A43),
                borderRadius: BorderRadius.circular(0.12 * w),
              ),
              child: Text(
                _winds[paifu.windOf(seat)],
                style: TextStyle(fontSize: 0.4 * w, height: 1, fontWeight: FontWeight.w700, color: Colors.white),
              ),
            ),
            SizedBox(width: 0.15 * w),
            Flexible(
              child: Text(
                seat == paifu.hero && paifu.hasHeroHands ? (name.isEmpty ? '나' : '$name(나)') : name,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 0.36 * w,
                  height: 1.1,
                  fontWeight: on ? FontWeight.w800 : FontWeight.w500,
                  color: on ? kioskGold : const Color(0xFFCFD8D3),
                ),
              ),
            ),
          ],
        ),
      );
    }

    Widget indicators(String title, List<PaifuTile> tiles) => Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('$title ', style: TextStyle(fontSize: 0.32 * w, color: const Color(0xFF9FB0A8))),
            for (final t in tiles)
              Padding(
                padding: EdgeInsets.only(right: 0.04 * w),
                child: TileView(t.tile, red: t.red, width: 0.66 * w),
              ),
          ],
        );

    final resultText = !state.finished || r == null
        ? null
        : switch (r.type) { 'ron' => '론', 'tsumo' => '쯔모', _ => '유국' };

    return Container(
      decoration: BoxDecoration(
        color: _centerBg,
        borderRadius: BorderRadius.circular(0.35 * w),
        border: Border.all(color: const Color(0xFF2F5C49), width: 0.06 * w),
      ),
      padding: EdgeInsets.all(0.14 * w),
      child: Stack(
        children: [
          Align(alignment: Alignment.bottomCenter, child: label(0)),
          Align(alignment: Alignment.topCenter, child: label(2)),
          Align(alignment: Alignment.centerRight, child: RotatedBox(quarterTurns: 3, child: label(1))),
          Align(alignment: Alignment.centerLeft, child: RotatedBox(quarterTurns: 1, child: label(3))),
          Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  '${paifu.round}${paifu.honba > 0 ? ' ${paifu.honba}본장' : ''}',
                  style: TextStyle(fontSize: 0.56 * w, height: 1.15, fontWeight: FontWeight.w800, color: kioskGold),
                ),
                Text(
                  resultText ?? '남은 패 ${state.wallLeft}',
                  key: const ValueKey('paifu-wall'),
                  style: TextStyle(
                    fontSize: (resultText != null ? 0.5 : 0.34) * w,
                    height: 1.3,
                    fontWeight: resultText != null ? FontWeight.w800 : FontWeight.w500,
                    color: resultText != null ? Colors.white : const Color(0xFFCFD8D3),
                  ),
                ),
                SizedBox(height: 0.12 * w),
                if (paifu.doraIndicators.isNotEmpty) indicators('도라', paifu.doraIndicators),
                if (state.finished && paifu.uraIndicators.isNotEmpty)
                  Padding(
                    padding: EdgeInsets.only(top: 0.08 * w),
                    child: indicators('뒷도라', paifu.uraIndicators),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ── 가장자리: 손패·울기 ──

  /// 그 자리의 울기. 끝 걸음의 화료자는 결과에 적힌 묶음으로(버림만 적은 패보는 판 중 울기가 가져간 한 장뿐이다).
  List<PaifuMeld> _meldsOf(int seat) {
    final r = paifu.result;
    if (state.finished && r != null && r.winner == seat && r.melds.isNotEmpty) {
      return [
        for (final m in r.melds) PaifuMeld(m.kind, m.tiles, m.kind == 'ankan' ? seat : (seat + 3) % 4),
      ];
    }
    return state.melds[seat];
  }

  Widget _back(double width) => Container(
        width: width,
        height: width * 1.4,
        margin: EdgeInsets.only(right: width * 0.06),
        decoration: BoxDecoration(
          color: _backColor,
          borderRadius: BorderRadius.circular(width * 0.14),
          border: Border.all(color: const Color(0xFF8A6A1F), width: 1),
        ),
      );

  /// 울기 묶음. 가져온 패는 준 자리 쪽 칸에 눕힌다. 안깡은 양 끝을 덮는다.
  Widget _meld(PaifuMeld m, int seat, double width) {
    final n = m.tiles.length;
    final from = m.from;
    final closed = from == null || from == seat;
    // 준 자리가 왼쪽(상가)이면 첫 칸, 맞은편이면 가운데, 오른쪽(하가)이면 끝 칸.
    final lay = closed
        ? -1
        : switch ((from - seat) % 4) { 3 => 0, 2 => n > 1 ? 1 : 0, _ => n - 1 };
    return Padding(
      padding: EdgeInsets.only(left: width * 0.3),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          for (final (i, t) in m.tiles.indexed)
            if (closed && n == 4 && (i == 0 || i == 3))
              _back(width)
            else
              Padding(
                padding: EdgeInsets.only(right: width * 0.06),
                child: i == lay
                    ? RotatedBox(quarterTurns: 1, child: TileView(t.tile, red: t.red, width: width))
                    : TileView(t.tile, red: t.red, width: width),
              ),
        ],
      ),
    );
  }

  /// 다른 자리의 가장자리 띠(아래 자리 기준으로 그리고 밖에서 돌린다). 손패는 뒷면, 끝 공개 손패가 있으면 앞면.
  Widget _sideStrip(int seat, double w, double length) {
    final tw = 0.62 * w;
    final melds = _meldsOf(seat);
    final r = paifu.result;
    final open = state.finished && r != null && r.winner == seat && seat != paifu.hero ? r.hand : null;
    final count = 13 - 3 * melds.length;
    return SizedBox(
      width: length,
      height: 1.1 * w,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
            child: Center(
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (open != null)
                    for (final t in open)
                      Padding(
                        padding: EdgeInsets.only(right: tw * 0.06),
                        child: TileView(t.tile, red: t.red, width: tw),
                      )
                  else
                    for (var i = 0; i < count; i++) _back(tw),
                ],
              ),
            ),
          ),
          for (final m in melds) _meld(m, seat, tw),
        ],
      ),
    );
  }

  /// hero 손패(앞면, 크게). 뽑은 패는 오른쪽에 떼어 둔다. 손패를 모르는 걸음은 뒷면.
  Widget _heroStrip(double w) {
    final tw = 1.38 * w;
    final seat = paifu.hero;
    final melds = _meldsOf(seat);
    final hand = state.heroHand;
    final r = paifu.result;
    final won = state.finished && r != null && r.winner == seat ? r.winTile : null;
    Widget face(PaifuTile t, {bool mark = false}) => Padding(
          padding: EdgeInsets.only(right: tw * 0.05),
          child: mark
              ? _glow(TileView(t.tile, red: t.red, width: tw, highlighted: true), tw * 0.6)
              : TileView(t.tile, red: t.red, width: tw),
        );
    final tiles = <Widget>[
      if (hand != null)
        for (final t in hand) face(t)
      else if (heroView != null) ...[
        // 어느 뽑기 순서로 봐도 있는 패는 앞면, 그 순에 안 정해지는 패는 뒷면.
        for (final t in heroView!.known) face(t),
        for (var i = 0; i < heroView!.unknown; i++) _back(tw),
      ] else
        for (var i = 0; i < 13 - 3 * melds.length; i++) _back(tw),
      if (state.hasDrawn || won != null) SizedBox(width: tw * 0.35),
      if (won != null)
        face(won, mark: true)
      else if (state.hasDrawn)
        state.drawn != null ? face(state.drawn!, mark: true) : _back(tw),
    ];
    return SizedBox(
      height: 2.2 * w,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: Stack(
              alignment: Alignment.bottomCenter,
              children: [
                Row(
                  key: const ValueKey('paifu-hero-hand'),
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: tiles,
                ),
                if (hand == null && paifu.hasHeroHands)
                  Positioned(
                    bottom: tw * 0.5,
                    child: Container(
                      padding: EdgeInsets.symmetric(horizontal: 0.3 * w, vertical: 0.08 * w),
                      decoration: BoxDecoration(color: const Color(0xCC000000), borderRadius: BorderRadius.circular(0.2 * w)),
                      child: Text(
                        '이 순의 손패는 기록에 없습니다',
                        style: TextStyle(fontSize: 0.4 * w, color: Colors.white),
                      ),
                    ),
                  ),
              ],
            ),
          ),
          for (final m in melds) _meld(m, seat, 1.05 * w),
        ],
      ),
    );
  }
}

/// 한 대국에 적힌 패보(국 단위) 목록. 고르면 재생 화면.
class PaifuListScreen extends StatefulWidget {
  final String gameId;
  final String title;
  const PaifuListScreen({super.key, required this.gameId, this.title = '패보'});

  @override
  State<PaifuListScreen> createState() => _PaifuListScreenState();
}

class _PaifuListScreenState extends State<PaifuListScreen> {
  late final Future<List<Paifu>> _list = PaifuStore.list(widget.gameId);

  @override
  Widget build(BuildContext context) {
    return kioskWrap(
      context,
      Scaffold(
        appBar: AppBar(title: Text(widget.title)),
        body: kioskPage(
          context,
          FutureBuilder<List<Paifu>>(
            future: _list,
            builder: (context, snap) {
              final list = snap.data;
              if (list == null) return const Center(child: CircularProgressIndicator());
              if (list.isEmpty) {
                return const Center(
                  child: Padding(
                    padding: EdgeInsets.all(24),
                    child: Text('이 대국에는 적힌 패보가 없습니다\n(테이블 화면 더보기 → "패보: 버림 기록" 을 켜고 둔 판만 남습니다)', textAlign: TextAlign.center),
                  ),
                );
              }
              return ListView.separated(
                itemCount: list.length,
                separatorBuilder: (_, _) => const Divider(height: 1),
                itemBuilder: (context, i) => _PaifuTile(list[i]),
              );
            },
          ),
        ),
      ),
    );
  }
}

/// 목록의 한 줄: 제목, 버림 수 · 결과 · 손패 기록이 있는지. 누르면 재생 화면.
class _PaifuTile extends StatelessWidget {
  final Paifu p;
  const _PaifuTile(this.p);

  @override
  Widget build(BuildContext context) {
    final r = p.result;
    final discards = p.events.where((e) => e.type == PaifuEventType.discard).length;
    String who(int? seat) => seat == null || p.names[seat].isEmpty ? '' : ' ${p.names[seat]}';
    final end = r == null
        ? '결과 기록 없음'
        : switch (r.type) {
            'ron' => '론${who(r.winner)}',
            'tsumo' => '쯔모${who(r.winner)}',
            _ => '유국',
          };
    return ListTile(
      leading: const Icon(Icons.slideshow),
      title: Text(p.title.isNotEmpty ? p.title : p.round),
      subtitle: Text('버림 $discards장 · $end · ${p.hasHeroHands ? '손패 있음' : '버림만'}'),
      onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => PaifuScreen(paifu: p))),
    );
  }
}

/// 앱에 묶어 둔 패보 예시(assets/paifu/*.json) 목록.
class PaifuAssetListScreen extends StatefulWidget {
  const PaifuAssetListScreen({super.key});

  /// 묶음에 든 패보를 파일 이름 순으로 읽는다. 못 읽는 파일은 건너뛴다.
  static Future<List<Paifu>> load({AssetBundle? bundle}) async {
    final b = bundle ?? rootBundle;
    final manifest = await AssetManifest.loadFromAssetBundle(b);
    final paths = [
      for (final a in manifest.listAssets())
        if (a.startsWith('assets/paifu/') && a.endsWith('.json')) a,
    ]..sort();
    final out = <Paifu>[];
    for (final a in paths) {
      try {
        out.add(await PaifuAssetScreen.load(a, bundle: b));
      } catch (_) {}
    }
    return out;
  }

  @override
  State<PaifuAssetListScreen> createState() => _PaifuAssetListScreenState();
}

class _PaifuAssetListScreenState extends State<PaifuAssetListScreen> {
  late final Future<List<Paifu>> _list = PaifuAssetListScreen.load();

  @override
  Widget build(BuildContext context) {
    return kioskWrap(
      context,
      Scaffold(
        appBar: AppBar(title: const Text('패보 예시')),
        body: kioskPage(
          context,
          FutureBuilder<List<Paifu>>(
            future: _list,
            builder: (context, snap) {
              final list = snap.data;
              if (list == null) return const Center(child: CircularProgressIndicator());
              if (list.isEmpty) return const Center(child: Text('묶어 둔 패보가 없습니다'));
              return ListView.separated(
                itemCount: list.length,
                separatorBuilder: (_, _) => const Divider(height: 1),
                itemBuilder: (context, i) => _PaifuTile(list[i]),
              );
            },
          ),
        ),
      ),
    );
  }
}
