import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../engine/hand.dart';
import '../../engine/tile.dart';
import '../../paifu/agent_facts.dart';
import '../../paifu/hand_restore/restore_ui.dart';
import '../../paifu/hand_restore/restorer.dart';
import '../../paifu/paifu.dart';
import '../../paifu/paifu_review.dart';
import '../../paifu/paifu_score.dart';
import '../../paifu/paifu_store.dart';
import '../../paifu/review_chat.dart';
import '../../paifu/review_sentence.dart';
import '../../paifu/start_hand.dart';
import '../../services/review_ask_client.dart';
import '../kiosk.dart';
import '../result_screen.dart';
import '../settings_screen.dart';
import 'review_ask_panel.dart';
import 'review_summary_view.dart';
import 'review_view.dart';
import 'start_hand_sheet.dart';
import '../tile_view.dart';

const _winds = ['동', '남', '서', '북'];

/// 복기 · 재생 화면 단축키(→ ← ↓ ↑ space).
enum _ReviewKey { next, prev, heroNext, heroPrev, playPause }

class _ReviewKeyIntent extends Intent {
  final _ReviewKey key;
  const _ReviewKeyIntent(this.key);
}

/// 글을 쓰는 중([typing])이면 꺼져서 키가 글 입력으로 넘어간다(Shortcuts 가 꺼진 행동의 키는 삼키지 않음).
class _ReviewKeyAction extends Action<_ReviewKeyIntent> {
  final void Function(_ReviewKey) onKey;
  final bool Function() typing;
  _ReviewKeyAction({required this.onKey, required this.typing});

  @override
  bool isEnabled(_ReviewKeyIntent intent) => !typing();

  @override
  Object? invoke(_ReviewKeyIntent intent) {
    onKey(intent.key);
    return null;
  }
}

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

/// 패보 화면의 세 모습(설계서 `docs/paifu_review_ui_design_1121.md`).
/// summary = 판 요약(3-1), review = 복기(말풍선 · 탁자 · 수 띠 · 단추 줄, 3-2 · 3-7), play = 지금까지의 재생 화면
/// (자동 재생 · 사건 목록 · 시작 손패 입력 · 손패 복원 단추, 말풍선 없음).
enum PaifuView { summary, review, play }

/// 패보 재생: 한 사람(hero)의 매 순 손패 + 네 자리의 버림을 걸음마다 넘겨 본다.
///
/// 손패가 있는 패보(`Paifu.hasHeroHands`)는 판 요약을 먼저 띄우고(9절 ②), "복기 시작" 이면 복기 화면, "처음부터 보기" 면
/// 재생 화면으로 간다. 손패가 없는 판은 바로 재생 화면이다(시작 손패 입력 · 손패 복원 단추가 그 패널에 그대로 있다).
class PaifuScreen extends StatefulWidget {
  final Paifu paifu;

  /// 리뷰 카드의 엔진 참고값을 뒤에서 내는 함수(기본 [computeEngineReview]). 시험에서 바꿔 끼운다.
  final EngineReviewRunner engineReview;

  /// 이 패보가 든 대국([PaifuStore] 열쇠). 있으면(기기에 저장된 패보) 손패 복원 · 되돌리기를 낸다. 예시(asset)는 null.
  final String? gameId;

  /// 손패 복원(Claude API)에 쓰는 것(녹화 폴더 확인 · 실행기). 시험에서 바꿔 끼운다.
  final HandRestoreSetup restoreSetup;

  /// 복기 질문 창이 서버에 묻는 함수. null(기본)이면 화면이 [ReviewAskClient] 하나를 만들어 쓴다 — 그때 "키 있음" 은
  /// [ReviewConfig.isConfigured]. 시험에서 가짜를 넣으면 키가 있는 것으로 본다.
  final ReviewAsker? asker;
  const PaifuScreen({
    super.key,
    required this.paifu,
    this.engineReview = computeEngineReview,
    this.gameId,
    this.restoreSetup = const HandRestoreSetup(),
    this.asker,
  });

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

  /// 지금 보는 패보(손패 복원 · 되돌리기로 바뀜).
  late Paifu _paifu = widget.paifu;
  Paifu get _p => _paifu;
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

  // ── 복기 화면(설계서 3-1 ~ 3-9) ──

  /// 지금 보이는 모습. 손패가 있는 판은 요약부터.
  late PaifuView _view = _p.hasHeroHands ? PaifuView.summary : PaifuView.play;

  /// 단계 걸음(배패 · 리치 · 끝).
  late List<ReviewStage> _stages = reviewStages(_p);

  /// 단계 말풍선을 일부러 띄운 걸음("다음" · 단계 아이콘 · 복기 시작). 내 버림이 없는 단계 걸음은 이 값과 상관없이 단계 말풍선.
  int? _stageFor;

  /// 펼침: 최선 보기(막대) · 후보 · 참고값. 후보 · 참고값은 판을 보는 동안 펼친 채로 둔다.
  bool _bestView = false;
  bool _showCandidates = false;
  bool _showEngine = false;

  /// 최선 보기에서 누른 막대의 패 종류.
  int? _barTile;

  /// 수 띠 칸(리뷰가 바뀌면 다시 만든다).
  List<StripEntry>? _stripCache;
  PaifuReviewIndex? _stripFor;

  // ── 복기 질문 창(설계서 docs/paifu_review_agent_app_design_1122.md 3절) ──

  /// "질문" 펼침. 후보 · 참고값과 같은 자리를 써서 한 번에 하나만 켠다.
  bool _askOpen = false;

  /// [PaifuScreen.asker] 가 없을 때 쓰는 서버 클라이언트(dispose 에서 닫음).
  ReviewAskClient? _askClient;

  /// 대화(창을 닫았다 열어도 · 걸음을 옮겨도 남음, 패보가 바뀌면 비움).
  late final ReviewAskController _ask = ReviewAskController(
    asker: ({required facts, required question, history = const []}) =>
        (widget.asker ?? (_askClient ??= ReviewAskClient()).ask)(facts: facts, question: question, history: history),
    facts: _askFacts,
    engine: () => _engine,
  );

  /// 사실표 캐시: 같은 리뷰 객체면 다시 만들지 않는다.
  Map<String, dynamic>? _factsCache;
  PaifuReviewIndex? _factsFor;

  Map<String, dynamic> _askFacts() {
    final cached = _factsCache;
    if (cached != null && identical(_factsFor, _review)) return cached;
    _factsFor = _review;
    return _factsCache = agentFacts(_p, _review.review);
  }

  /// 글자판이 올라와 있는가(build 에서 셈). 세로 질문 시트를 탁자 영역 전체까지 키운다.
  bool _keyboardUp = false;

  bool get _askConfigured => widget.asker != null || ReviewConfig.isConfigured;

  /// 복기 · 재생 화면의 방향키 · space 를 받는 자리. 입력 줄에서 빠져나오면 이리 되돌린다.
  final _keysFocus = FocusNode(debugLabel: 'paifu-keys');
  late final _keyAction = _ReviewKeyAction(onKey: _onReviewKey, typing: _typing);

  @override
  void initState() {
    super.initState();
    if (widget.asker == null) _askClient = ReviewAskClient();
    _ask.inputFocus.addListener(_askFocusChanged);
    _loadRules();
    _loadStartHand();
    _startEngineReview();
    _loadRestoreState();
  }

  /// 입력 줄이 포커스를 잃었는데 다른 자리가 받지 않았으면(창을 닫음 · 보냄) 방향키 자리로 되돌린다.
  void _askFocusChanged() {
    if (_ask.inputFocus.hasFocus) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _ask.inputFocus.hasFocus) return;
      final f = FocusManager.instance.primaryFocus;
      if (f == null || f is FocusScopeNode) _keysFocus.requestFocus();
    });
  }

  /// 입력 줄에 글을 쓰는 중인가 — 그때는 복기 화면 단축키가 걸음을 옮기거나 재생을 켜지 않고 글 입력으로 넘긴다.
  bool _typing() {
    final f = FocusManager.instance.primaryFocus;
    if (f == null) return false;
    if (identical(f, _ask.inputFocus)) return true;
    final ctx = f.context;
    return ctx != null && (ctx.widget is EditableText || ctx.findAncestorStateOfType<EditableTextState>() != null);
  }

  void _onReviewKey(_ReviewKey k) {
    switch (k) {
      case _ReviewKey.next:
        _next();
      case _ReviewKey.prev:
        _go(_step - 1);
      case _ReviewKey.heroNext:
        _heroTurn(1);
      case _ReviewKey.heroPrev:
        _heroTurn(-1);
      case _ReviewKey.playPause:
        _playing ? _stop() : _play();
    }
  }

  void _setAskOpen(bool on) {
    setState(() {
      _askOpen = on;
      if (on) {
        _showCandidates = false;
        _showEngine = false;
      }
    });
    if (!on) _ask.inputFocus.unfocus();
  }

  /// 보낸 뒤: 글자판을 내려 답이 보이게 한다(방향키 자리는 [_askFocusChanged] 가 되돌림).
  void _askSent() => _ask.inputFocus.unfocus();

  /// "N순 보기": 그 차례의 걸음(창은 연 채로).
  void _askGoto(int turn) {
    final step = _askStepOf(turn);
    if (step == null) return;
    _stop();
    _go(step);
  }

  int? _askStepOf(int turn) {
    for (final t in _review.review.turns) {
      if (t.turn == turn) return t.eventIndex + 1;
    }
    return null;
  }

  /// 손패 복원: API 키가 있는지(키 자체는 다시 보여 주지 않음) · 되돌릴 원본이 있는지.
  bool _hasKey = false;
  bool _hasOriginal = false;
  bool _restoring = false;

  Future<void> _loadRestoreState() async {
    final gid = widget.gameId;
    if (gid == null) return;
    try {
      final key = await ClaudeKeyStore.load();
      final orig = await RestoreStore.hasOriginal(gid, _p.id);
      if (!mounted) return;
      setState(() {
        _hasKey = key != null;
        _hasOriginal = orig;
      });
    } catch (_) {}
  }

  /// 패보를 바꿔 끼우고(복원 · 되돌리기) 점수 · 리뷰 · 시작 손패를 다시 셈한다.
  void _replacePaifu(Paifu p) {
    setState(() => _resetFor(p));
    _loadRestoreState();
  }

  void _resetFor(Paifu p) {
    _engineTimer?.cancel();
    _engineTimer = null;
    _paifu = p;
    _step = _step.clamp(0, _last);
    _score = scoreOf(_p, rules: _rules);
    _review = PaifuReviewIndex.of(_p);
    _engine = EngineReviewStatus.off;
    _startHand = const [];
    _infer = null;
    // 복기 화면: 단계 · 수 띠를 다시 셈. 손패가 없어진 판이면 재생 화면으로(보던 모습은 그대로 둔다).
    _stages = reviewStages(p);
    _stageFor = null;
    _barTile = null;
    _stripCache = null;
    if (!p.hasHeroHands) _view = PaifuView.play;
    // 질문 창: 오던 답은 버리고 대화를 비운 뒤 닫는다.
    _askOpen = false;
    _factsCache = null;
    _factsFor = null;
    _ask.clear();
    _startEngineReview();
    _loadStartHand();
  }

  @override
  void didUpdateWidget(covariant PaifuScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.paifu, widget.paifu)) {
      _resetFor(widget.paifu);
      _loadRestoreState();
    }
  }

  Future<void> _restoreHands() async {
    final gid = widget.gameId;
    if (gid == null || _restoring) return;
    _stop();
    setState(() => _restoring = true);
    try {
      final p = await runHandRestore(context, paifu: _p, gameId: gid, setup: widget.restoreSetup);
      if (!mounted) return;
      if (p != null) _replacePaifu(p);
    } finally {
      if (mounted) setState(() => _restoring = false);
      await _loadRestoreState();
    }
  }

  Future<void> _revertRestore() async {
    final gid = widget.gameId;
    if (gid == null) return;
    _stop();
    final p = await RestoreStore.revert(gid, _p.id);
    if (!mounted) return;
    if (p != null) _replacePaifu(p);
    await _loadRestoreState();
  }

  /// 손패 복원 단추(또는 못 쓰는 까닭 한 줄). 기기에 저장된, 손패가 없는 패보에서만.
  Widget _restoreRow(ThemeData theme) {
    final why = restoreBlocker(_p, widget.restoreSetup);
    if (why != null) {
      return Text(why,
          key: const ValueKey('paifu-restore-why'),
          style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant));
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OutlinedButton.icon(
          key: const ValueKey('paifu-restore'),
          icon: const Icon(Icons.auto_fix_high),
          label: const Text('손패 복원 (Claude API)'),
          onPressed: _restoring ? null : _restoreHands,
        ),
        if (!_hasKey)
          Text('Claude API 키가 없습니다 — 누르면 넣습니다',
              key: const ValueKey('paifu-restore-nokey'), style: theme.textTheme.bodySmall),
      ],
    );
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
    final p = _p;
    try {
      final r = await widget.engineReview(p);
      // 그새 패보가 바뀌었으면(손패 복원 · 되돌리기) 옛 판의 결과는 버린다.
      if (!mounted || !identical(p, _p)) return;
      setState(() {
        _review = PaifuReviewIndex.fromReview(r);
        _engine = EngineReviewStatus.ready;
      });
    } catch (_) {
      if (mounted && identical(p, _p)) setState(() => _engine = EngineReviewStatus.failed);
    }
    // 계산을 기다리던 질문을 보낸다(ready 면 수비 칸이 든 새 리뷰로).
    if (mounted && identical(p, _p)) _ask.engineSettled();
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
    _ask.inputFocus.removeListener(_askFocusChanged);
    _ask.dispose(); // 오던 답은 버린다
    _askClient?.close();
    _keysFocus.dispose();
    super.dispose();
  }

  /// [step] 으로 간다. [stage] 가 그 걸음이면 단계 말풍선을 띄운다(복기 화면).
  void _go(int step, {int? stage}) {
    final s = step.clamp(0, _last);
    if (s == _step) {
      if (_stageFor != stage || _barTile != null) {
        setState(() {
          _stageFor = stage;
          _barTile = null;
        });
      }
      return;
    }
    setState(() {
      _step = s;
      _stageFor = stage;
      _barTile = null;
    });
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
    // Scaffold 가 본문 MediaQuery 에서 글자판 높이를 지우므로 여기(Scaffold 바깥)에서 본다.
    _keyboardUp = MediaQuery.viewInsetsOf(context).bottom > 0;
    final state = _p.states[_step];
    final title = _p.title.isNotEmpty ? _p.title : '패보';
    final view = _view;
    final Widget body;
    if (view == PaifuView.summary) {
      body = PaifuReviewSummary(
        paifu: _p,
        review: _review.review,
        result: _resultShort(),
        onStart: _startReview,
        onPlay: _startPlay,
        // 판 전체 질문(복기 화면의 내 버림 아닌 걸음과 같은 글). 키 없는 빌드면 줄을 그리지 않는다.
        questions: suggestedQuestions(_p, _review.review, null),
        onAsk: _askConfigured ? _askFromSummary : null,
        onLesson: (step) {
          setState(() => _view = PaifuView.review);
          _go(step);
        },
      );
    } else {
      // 방향키 · space. 질문 창 입력 줄에 글을 쓰는 중이면 행동을 끄고(_ReviewKeyAction.isEnabled) 키를 흘려보내
      // 글 입력 · 커서 이동(앱 위쪽의 기본 글 편집 단축키)이 받게 한다 — CallbackShortcuts 는 늘 키를 삼킨다.
      body = Shortcuts(
        shortcuts: const {
          SingleActivator(LogicalKeyboardKey.arrowRight): _ReviewKeyIntent(_ReviewKey.next),
          SingleActivator(LogicalKeyboardKey.arrowLeft): _ReviewKeyIntent(_ReviewKey.prev),
          SingleActivator(LogicalKeyboardKey.arrowDown): _ReviewKeyIntent(_ReviewKey.heroNext),
          SingleActivator(LogicalKeyboardKey.arrowUp): _ReviewKeyIntent(_ReviewKey.heroPrev),
          SingleActivator(LogicalKeyboardKey.space): _ReviewKeyIntent(_ReviewKey.playPause),
        },
        child: Actions(
          actions: {_ReviewKeyIntent: _keyAction},
          child: Focus(
            focusNode: _keysFocus,
            autofocus: true,
            child: SafeArea(
              child: LayoutBuilder(
                builder: (context, box) => view == PaifuView.review ? _reviewBody(context, state, box) : _playBody(context, state, box),
              ),
            ),
          ),
        ),
      );
    }
    return kioskWrap(
      context,
      Scaffold(
        appBar: AppBar(
          title: Text(view == PaifuView.play ? title : '복기'),
          actions: [
            if (view != PaifuView.summary && _p.hasHeroHands)
              TextButton(key: const ValueKey('paifu-open-summary'), onPressed: _openSummary, child: const Text('요약')),
            if (view == PaifuView.play && _p.hasHeroHands)
              TextButton(
                key: const ValueKey('paifu-open-review'),
                onPressed: () {
                  _stop();
                  setState(() => _view = PaifuView.review);
                },
                child: const Text('복기'),
              ),
            if (view == PaifuView.review)
              IconButton(
                key: const ValueKey('paifu-review-settings'),
                tooltip: '설정',
                icon: const Icon(Icons.settings_outlined),
                onPressed: _openSettings,
              ),
          ],
        ),
        body: body,
      ),
    );
  }

  /// 재생 화면(지금까지의 배치): 가로면 탁자 왼쪽 · 패널 오른쪽, 세로면 탁자 위 · 패널 아래.
  Widget _playBody(BuildContext context, PaifuState state, BoxConstraints box) {
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
  }

  // ── 복기 화면 ──

  /// 머리 줄 · 끝 띠에 쓰는 결과 한 낱말.
  String _resultShort() => switch (_p.result?.type) {
        'ron' => '론',
        'tsumo' => '쯔모',
        'draw' => '유국',
        null => '',
        _ => '유국',
      };

  int? get _points {
    final s = _score;
    return s != null && s.result.isValid ? s.result.payment.total : null;
  }

  void _openSummary() {
    _stop();
    setState(() => _view = PaifuView.summary);
  }

  /// 요약의 "복기 시작": 첫 걸음 + 배패 말풍선(있으면).
  void _startReview() {
    setState(() => _view = PaifuView.review);
    final s0 = _stageAt(0);
    _go(0, stage: s0 == null ? null : 0);
  }

  /// 요약의 질문 칩: "복기 시작" 과 같은 첫 걸음으로 가서 질문 창을 열고 그 글을 그대로 보낸다(판 전체 질문이라 차례를
  /// 붙이지 않음). 엔진 계산 중이면 컨트롤러가 기다렸다 보낸다. 글자판은 띄우지 않는다. 앞 답을 기다리는 중이면(busy)
  /// 보내지 않고 창만 연다.
  void _askFromSummary(String q) {
    _startReview();
    _setAskOpen(true);
    _ask.send(q);
  }

  /// 요약의 "처음부터 보기": 말풍선 없는 재생 화면의 첫 걸음.
  void _startPlay() {
    setState(() => _view = PaifuView.play);
    _go(0);
  }

  ReviewStage? _stageAt(int step) {
    for (final s in _stages) {
      if (s.step == step) return s;
    }
    return null;
  }

  /// 이 걸음에 단계 말풍선이 보이는가: 단계 걸음이고, 일부러 띄웠거나 그 걸음에 내 버림 평가가 없을 때.
  bool _stageVisible(int step) => _stageAt(step) != null && (_stageFor == step || _review.byStep[step] == null);

  /// 큰 "다음"(3-2): 다음 내 버림 걸음으로. 그 사이 단계 걸음이 있으면 거기서 먼저 멈추고, 단계 말풍선 위에서 한 번 더
  /// 누르면 그 걸음의 수 말풍선. 마지막 내 버림 뒤에는 끝 걸음, 끝에서는 점수 결과 화면.
  void _reviewNext() {
    _stop();
    final here = _stageAt(_step);
    if (here != null && _stageFor == _step && _review.byStep[_step] != null) {
      setState(() => _stageFor = null);
      return;
    }
    int? target;
    for (final s in _review.turnSteps) {
      if (s > _step) {
        target = s;
        break;
      }
    }
    final limit = target ?? _last;
    for (final g in _stages) {
      if (g.step > _step && g.step <= limit) {
        _go(g.step, stage: g.step);
        return;
      }
    }
    if (target != null) {
      _go(target);
    } else if (_step < _last) {
      _go(_last);
    } else {
      _showResult();
    }
  }

  void _goStage(ReviewStage s) {
    _stop();
    _go(s.step, stage: s.step);
  }

  void _nextFlag() {
    final n = _review.nextFlagged(_step);
    if (n != null) _go(n);
  }

  /// 수 띠 칸들(걸음마다 하나).
  List<StripEntry> get _strip {
    final cached = _stripCache;
    if (cached != null && identical(_stripFor, _review)) return cached;
    _stripFor = _review;
    return _stripCache = [for (final s in _p.states) _stripEntry(s)];
  }

  StripEntry _stripEntry(PaifuState s) {
    final e = s.event;
    if (e == null) return StripEntry(s.finished ? _resultShort() : '배패');
    final w = _winds[_p.windOf(e.seat)];
    switch (e.type) {
      case PaifuEventType.draw:
        return StripEntry(e.tile == null ? '뽑기' : '뽑기 ${_tileName(e.tile!)}');
      case PaifuEventType.discard:
        if (e.seat == _p.hero) {
          final t = _review.byStep[s.step];
          return StripEntry(
            '${t?.turn ?? ''}·${_tileName(e.tile!)}',
            mine: true,
            grade: t != null && t.status == ReviewStatus.graded ? t.grade : null,
          );
        }
        return StripEntry('$w ${_tileName(e.tile!)}${e.riichi ? ' 리치' : ''}');
      case PaifuEventType.call:
        final kind = switch (e.callKind) { 'chi' => '치', 'pon' => '퐁', 'call' => '울기', _ => '깡' };
        return StripEntry('$w $kind');
    }
  }

  /// 지금 걸음의 말풍선: 단계 → 내 버림 → 그 밖(한 줄 회색).
  Widget _bubble(PaifuState state) {
    final st = _stageAt(_step);
    if (st != null && _stageVisible(_step)) {
      return ReviewBubble.stage(
        st,
        step: _step,
        sentence: stageSentence(
          st,
          seatLabel: _seatLabel,
          result: endResultText(_p.result, points: _points),
          efficiencyPct: _review.review.efficiencyPct,
        ),
      );
    }
    final t = _review.byStep[_step];
    if (t != null) return ReviewBubble.turn(t, step: _step);
    return ReviewBubble.plain(_describe(state), step: _step);
  }

  /// 이 걸음에서 최선 보기를 켤 수 있는가(손패를 아는 내 버림 걸음).
  bool _bestAvailable(TurnReview? t) => t != null && t.options.isNotEmpty && t.before != null;

  void _toggleBest(TurnReview? t) {
    if (!_bestAvailable(t)) {
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(const SnackBar(content: Text('이 걸음은 손패 기록이 없습니다')));
      return;
    }
    setState(() {
      _bestView = !_bestView;
      _barTile = null;
    });
  }

  Widget _foldContent(TurnReview? t) => Column(
        key: const ValueKey('paifu-folds'),
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (_showCandidates) ReviewCandidates(t),
          if (_showCandidates && _showEngine) const Divider(height: 16),
          if (_showEngine) EngineReviewFold(turn: t, engine: _engine, seatLabel: _seatLabel),
        ],
      );

  /// 질문 창. 추천 질문 · 차례 칩은 지금 걸음에 맞춘다([t] = 지금 걸음의 내 버림 평가).
  Widget _askPanel(TurnReview? t, {bool fill = false, bool compact = false}) => ReviewAskPanel(
        controller: _ask,
        configured: _askConfigured,
        suggestions: suggestedQuestions(_p, _review.review, t),
        turn: t?.turn,
        canGoto: (n) => _askStepOf(n) != null,
        onGoto: _askGoto,
        onClose: () => _setAskOpen(false),
        onSent: _askSent,
        fill: fill,
        compact: compact,
      );

  Widget _barInfo(ThemeData theme, String text) => Container(
        key: const ValueKey('paifu-bar-info'),
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: theme.colorScheme.inverseSurface.withAlpha(235),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Text(text,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onInverseSurface)),
      );

  /// 단추 줄: 최선 보기 · 후보 · 참고값(펼침 토글) + 큰 "다음".
  Widget _reviewButtons(ThemeData theme, TurnReview? t) => SizedBox(
        height: 48,
        // 토글 넷이 기본 여백이면 시험 글꼴로 329px — 줄 폭이 440 보다 좁으면(폰 세로 · 가로 오른쪽 패널) 칩의 가로 여백만
        // 줄여 233px 로, "다음" 이 360 폭에서도 100px 넘게 남게 한다. 세로 여백은 기본값 그대로라 칩 높이는 넓은 폭과 같다.
        child: LayoutBuilder(builder: (context, box) => _reviewButtonRow(theme, t, tight: box.maxWidth < 440)),
      );

  Widget _reviewButtonRow(ThemeData theme, TurnReview? t, {required bool tight}) {
    final scheme = theme.colorScheme;
    // 좁을 때 가로 여백만 0 으로. 세로는 칩 기본(테마 값, 없으면 M3 기본 8)을 그대로 둔다 — EdgeInsets.zero 를 주면
    // 세로 여백까지 없어져 칩 높이가 34 → 30 으로 납작해졌다(11-23).
    EdgeInsets? tightPad;
    if (tight) {
      final base = (theme.chipTheme.padding ?? const EdgeInsets.all(8)).resolve(Directionality.of(context));
      tightPad = EdgeInsets.only(top: base.top, bottom: base.bottom);
    }
    Widget toggle(String label, Key key, bool on, VoidCallback onTap, {bool dim = false}) => Padding(
          padding: const EdgeInsets.only(right: 6),
          child: FilterChip(
            key: key,
            label: Text(label, style: dim ? TextStyle(color: scheme.onSurface.withAlpha(97)) : null),
            selected: on && !dim,
            showCheckmark: false,
            visualDensity: VisualDensity.compact,
            materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
            padding: tightPad,
            labelPadding: tight ? const EdgeInsets.symmetric(horizontal: 4) : null,
            onSelected: (_) => onTap(),
          ),
        );
    return SizedBox(
      height: 48,
      child: Row(
        children: [
          toggle('최선 보기', const ValueKey('paifu-best-view'), _bestView, () => _toggleBest(t), dim: !_bestAvailable(t)),
          // 후보 · 참고값을 켜면 질문 창은 닫는다(같은 자리).
          toggle('후보', const ValueKey('paifu-fold-candidates-btn'), _showCandidates, () {
            if (!_showCandidates) _setAskOpen(false);
            setState(() => _showCandidates = !_showCandidates);
          }),
          toggle('참고값', const ValueKey('paifu-fold-engine-btn'), _showEngine, () {
            if (!_showEngine) _setAskOpen(false);
            setState(() => _showEngine = !_showEngine);
          }),
          toggle('질문', const ValueKey('paifu-ask-btn'), _askOpen, () => _setAskOpen(!_askOpen)),
          if (_playing)
            IconButton(tooltip: '멈춤', icon: const Icon(Icons.pause), onPressed: _stop),
          Expanded(
            child: FilledButton(
              key: const ValueKey('paifu-review-go'),
              style: FilledButton.styleFrom(minimumSize: const Size(0, 44)),
              onPressed: _reviewNext,
              child: const Text('다음', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
            ),
          ),
        ],
      ),
    );
  }

  /// 복기 화면(3-2 세로 · 3-7 가로): 말풍선 → 탁자 → 수 띠 → 단추 줄. 가로는 탁자 왼쪽, 오른쪽 패널에 같은 순서.
  Widget _reviewBody(BuildContext context, PaifuState state, BoxConstraints box) {
    final theme = Theme.of(context);
    final t = _review.byStep[_step];
    final bestOn = _bestView && _bestAvailable(t);
    final before = bestOn ? beforeHandOf(_p, t!) : null;
    final table = PaifuTableView(
      paifu: _p,
      state: state,
      heroView: _infer?.viewAt(_p, state.step),
      lastGrade: t != null && t.status == ReviewStatus.graded ? t.grade : null,
      before: before,
      bars: before == null ? null : handBars(t!),
      selectedBar: _barTile,
      onBarTap: (tile) => setState(() => _barTile = _barTile == tile ? null : tile),
    );
    final info = before != null && _barTile != null ? barInfoLine(t!, _barTile!) : null;
    final folded = !_showCandidates && !_showEngine;
    final strip = ReviewMoveStrip(
      entries: _strip,
      step: _step,
      onGo: (s) {
        _stop();
        _go(s);
      },
      stages: _stages,
      onStage: _goStage,
      onNextFlag: _review.nextFlagged(_step) == null ? null : _nextFlag,
    );
    final buttons = _reviewButtons(theme, t);
    final wide = box.maxWidth > box.maxHeight * 1.2;
    if (wide) {
      final panelW = (box.maxWidth * 0.34).clamp(320.0, 460.0);
      // 질문 창 + 글자판: 패널이 짧아지므로 말풍선 · 막대 설명 · 수 띠를 숨기고 추천 질문 줄도 접는다(단추 줄은 남김).
      final typing = _askOpen && _keyboardUp;
      return Row(
        children: [
          Expanded(child: Padding(padding: const EdgeInsets.all(8), child: Center(child: table))),
          SizedBox(
            width: panelW,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(4, 8, 12, 8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (!typing) _bubble(state),
                  if (!typing && info != null)
                    Padding(padding: const EdgeInsets.only(top: 6), child: _barInfo(theme, info)),
                  // 키: 위아래 칸이 빠졌다 돌아와도 이 칸(질문 창 입력 줄)을 새로 만들지 않아 포커스 · 글자판이 유지된다.
                  Expanded(
                    key: const ValueKey('paifu-wide-main'),
                    child: _askOpen
                        ? Padding(
                            padding: const EdgeInsets.only(top: 8),
                            child: _askPanel(t, fill: true, compact: typing),
                          )
                        : folded
                        ? const SizedBox.shrink()
                        : SingleChildScrollView(
                            key: const ValueKey('paifu-fold-scroll'),
                            padding: const EdgeInsets.only(top: 8),
                            child: _foldContent(t),
                          ),
                  ),
                  if (!typing) strip,
                  buttons,
                ],
              ),
            ),
          ),
        ],
      );
    }
    return Column(
      children: [
        Padding(padding: const EdgeInsets.fromLTRB(8, 6, 8, 0), child: _bubble(state)),
        Expanded(
          child: LayoutBuilder(
            builder: (context, area) => Stack(
              children: [
                Positioned.fill(child: Padding(padding: const EdgeInsets.all(6), child: Center(child: table))),
                if (info != null) Positioned(top: 4, left: 8, right: 8, child: _barInfo(theme, info)),
                // 펼친 후보 · 참고값은 탁자를 밀어내지 않고 위를 덮는 아래 시트로.
                if (!folded)
                  Positioned(
                    left: 0,
                    right: 0,
                    bottom: 0,
                    child: ConstrainedBox(
                      constraints: BoxConstraints(maxHeight: area.maxHeight * 0.6),
                      child: Material(
                        elevation: 6,
                        color: theme.colorScheme.surfaceContainer,
                        borderRadius: const BorderRadius.vertical(top: Radius.circular(12)),
                        child: SingleChildScrollView(
                          key: const ValueKey('paifu-fold-scroll'),
                          padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
                          child: _foldContent(t),
                        ),
                      ),
                    ),
                  ),
                // 질문 창: 같은 자리의 아래 시트. 대화 목록이 따로 스크롤하고 입력 줄은 아래에 붙도록 fold-scroll 밖에 둔다.
                // 글자판이 올라오면(본문이 줄어든 만큼) 탁자 영역 전체까지 쓴다.
                if (_askOpen)
                  Positioned(
                    left: 0,
                    right: 0,
                    bottom: 0,
                    child: ConstrainedBox(
                      constraints: BoxConstraints(maxHeight: area.maxHeight * (_keyboardUp ? 1.0 : 0.7)),
                      child: Material(
                        key: const ValueKey('paifu-ask-sheet'),
                        elevation: 6,
                        color: theme.colorScheme.surfaceContainer,
                        borderRadius: const BorderRadius.vertical(top: Radius.circular(12)),
                        child: Padding(
                          padding: const EdgeInsets.fromLTRB(12, 2, 8, 8),
                          child: _askPanel(t, compact: _keyboardUp),
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
        Padding(padding: const EdgeInsets.symmetric(horizontal: 4), child: strip),
        Padding(padding: const EdgeInsets.fromLTRB(8, 0, 8, 6), child: buttons),
      ],
    );
  }

  /// 복기 화면 ⚙: 처음 · 이전/다음 내 차례 · 끝, 사건 목록, 재생 화면(자동 재생)으로, 손패 복원 되돌리기.
  Future<void> _openSettings() async {
    _stop();
    final canRevert = widget.gameId != null && _p.handSource == 'claude_api' && _hasOriginal;
    await showModalBottomSheet<void>(
      context: context,
      builder: (ctx) {
        void run(VoidCallback f) {
          Navigator.of(ctx).pop();
          f();
        }

        return SafeArea(
          child: Column(
            key: const ValueKey('paifu-settings-sheet'),
            mainAxisSize: MainAxisSize.min,
            children: [
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text('$_step / $_last', style: Theme.of(ctx).textTheme.bodySmall),
              ),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: [
                  IconButton(tooltip: '처음', icon: const Icon(Icons.first_page), onPressed: () => run(() => _go(0))),
                  IconButton(
                      tooltip: '이전 내 차례', icon: const Icon(Icons.fast_rewind), onPressed: () => run(() => _heroTurn(-1))),
                  IconButton(
                      tooltip: '다음 내 차례', icon: const Icon(Icons.fast_forward), onPressed: () => run(() => _heroTurn(1))),
                  IconButton(tooltip: '끝', icon: const Icon(Icons.last_page), onPressed: () => run(() => _go(_last))),
                ],
              ),
              ListTile(
                key: const ValueKey('paifu-settings-log'),
                leading: const Icon(Icons.list),
                title: const Text('사건 목록'),
                onTap: () => run(_openLog),
              ),
              ListTile(
                key: const ValueKey('paifu-settings-play'),
                leading: const Icon(Icons.play_circle_outline),
                title: const Text('재생 화면으로 (자동 재생)'),
                onTap: () => run(() => setState(() => _view = PaifuView.play)),
              ),
              if (canRevert)
                ListTile(
                  key: const ValueKey('paifu-settings-revert'),
                  leading: const Icon(Icons.undo),
                  title: const Text('손패 복원 되돌리기'),
                  onTap: () => run(_revertRestore),
                ),
            ],
          ),
        );
      },
    );
  }

  /// ⚙ → 사건 목록(세로, 지금의 사건 목록과 같은 줄). 누르면 그 걸음으로.
  Future<void> _openLog() async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) {
        final theme = Theme.of(ctx);
        final scheme = theme.colorScheme;
        return SizedBox(
          height: MediaQuery.of(ctx).size.height * 0.6,
          child: ListView.builder(
            key: const ValueKey('paifu-log-sheet'),
            itemExtent: _rowH,
            itemCount: _p.states.length,
            itemBuilder: (context, i) {
              final s = _p.states[i];
              final mine = s.event?.seat == _p.hero;
              final turn = _review.byStep[i];
              return InkWell(
                onTap: () {
                  Navigator.of(ctx).pop();
                  _go(i);
                },
                child: Container(
                  color: i == _step ? scheme.primary.withAlpha(46) : null,
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  child: Row(
                    children: [
                      SizedBox(width: 34, child: Text('$i', style: theme.textTheme.bodySmall)),
                      Expanded(
                        child: Text(
                          _describe(s),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: theme.textTheme.bodyMedium?.copyWith(
                            fontWeight: mine ? FontWeight.w700 : FontWeight.w400,
                            color: mine ? scheme.primary : null,
                          ),
                        ),
                      ),
                      if (turn != null && hasReviewBadge(turn)) ReviewBadge(turn),
                    ],
                  ),
                ),
              );
            },
          ),
        );
      },
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
                  if (widget.gameId != null) ...[
                    const SizedBox(height: 4),
                    _restoreRow(theme),
                  ],
                ],
              ),
            ),
          if (widget.gameId != null && _p.handSource == 'claude_api' && _hasOriginal)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: OutlinedButton.icon(
                key: const ValueKey('paifu-restore-revert'),
                icon: const Icon(Icons.undo),
                label: const Text('손패 복원 되돌리기'),
                onPressed: _revertRestore,
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
  /// 최소 폭 300) 위 칸을 그 폭으로 그려 줄여 보인다.
  /// 리뷰 없는 판(손패 없는 판 — 시작 손패 입력 단추가 더 붙는다)도 높이 상한 + 스크롤만은 같게 건다: 400×800 세로에서
  /// r20 이 아래로 37px 넘쳤다(11-23). 다 들어가는 화면에서는 위 칸이 제 높이 그대로라 모양이 같다. 폭 줄이기는 리뷰 판만.
  Widget _fitPanel(Column panel) {
    const minW = 340.0;
    final n = panel.children.length;
    assert(panel.children.last is Expanded, '패널의 마지막 칸은 사건 목록(Expanded)이어야 합니다');
    final head = panel.children.sublist(0, n - 2);
    final tail = panel.children.sublist(n - 2);
    return LayoutBuilder(
      builder: (context, box) {
        final minLog = (box.maxHeight * 0.2).clamp(2 * _rowH, 4 * _rowH);
        Widget top = Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: head);
        if (_review.hasNumbers && box.maxWidth < minW) {
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

  /// 복기 화면: 방금 버린 hero 패(강의 마지막 패)에 붙이는 등급 아이콘(3절 탁자 배지). null 이면 없음.
  final ReviewGrade? lastGrade;

  /// 복기 화면 "최선 보기"(3-9): 손패 줄을 버리기 전 줄로 바꿔 그리고(버린 패는 제자리에 흐리게) [bars] 를 세운다.
  final BeforeHand? before;
  final Map<int, HandBar>? bars;

  /// 눌린 막대(패 종류)와 막대를 누를 때.
  final int? selectedBar;
  final ValueChanged<int>? onBarTap;

  const PaifuTableView({
    super.key,
    required this.paifu,
    required this.state,
    this.heroView,
    this.lastGrade,
    this.before,
    this.bars,
    this.selectedBar,
    this.onBarTap,
  });

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
            // hero 손패 띠는 맨 위 층에 바닥에 붙여 그린다: 최선 보기 막대가 띠 위(강 쪽)로 올라가도 탁자 크기는 그대로이고,
            // 막대를 누를 수 있게(띠의 칸 밖이면 눌리지 않음) 탁자 전체 층 안에 둔다.
            child: Stack(
              children: [
                Column(
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
                    SizedBox(height: 2.2 * w),
                  ],
                ),
                Positioned(left: 0, right: 0, bottom: 0, child: _heroStrip(w)),
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
    // 복기 화면 배지: hero 가 방금 버린 걸음의 hero 강 마지막 패에만.
    final heroJustDiscarded = markLast &&
        seat == paifu.hero &&
        e != null &&
        e.type == PaifuEventType.discard &&
        e.seat == seat &&
        lastGrade != null;
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
                    child: _riverTile(
                      shown[i],
                      w,
                      markLast && i == shown.length - 1,
                      badge: heroJustDiscarded && i == shown.length - 1 ? lastGrade : null,
                    ),
                  ),
              ],
            ),
          ),
      ],
    );
  }

  Widget _riverTile(PaifuRiverTile r, double w, bool last, {ReviewGrade? badge}) {
    Widget t = TileView(r.tile.tile, red: r.tile.red, width: w, highlighted: last);
    if (r.tsumogiri == true) {
      t = Container(
        foregroundDecoration: BoxDecoration(color: const Color(0x52000000), borderRadius: BorderRadius.circular(w * 0.14)),
        child: t,
      );
    }
    if (last) t = _glow(t, w);
    if (badge != null) {
      t = Stack(
        clipBehavior: Clip.none,
        children: [
          t,
          Positioned(
            top: -0.32 * w,
            right: -0.32 * w,
            child: ReviewGradeIcon(badge, key: const ValueKey('paifu-river-badge'), size: 0.72 * w),
          ),
        ],
      );
    }
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

  /// 최선 보기 막대 하나(3-9): 위에서부터 ★ · "버림" 표시, 유효패 수, 막대(샹텐이 뒤로 가면 회색 점). 폭은 패 한 장.
  Widget _bar(HandBar h, double w, double tw, double barH) {
    final Color color;
    if (h.best) {
      color = const Color(0xFF2E7D32);
    } else if (h.actual) {
      color = lastGrade != null ? gradeColors(lastGrade!).$1 : const Color(0xFFB0BEC5);
    } else {
      color = const Color(0xFF9E9E9E);
    }
    final labelH = 0.42 * w;
    final labels = [if (h.best) '★', if (h.actual) '버림'];
    final maxBar = barH - 3 * labelH - 0.1 * w;
    final selected = selectedBar == h.tile;
    Widget label(String s, {Color c = Colors.white}) => SizedBox(
          width: tw,
          height: labelH,
          child: FittedBox(
            fit: BoxFit.scaleDown,
            child: Text(s, style: TextStyle(fontSize: 0.36 * w, height: 1.1, fontWeight: FontWeight.w800, color: c)),
          ),
        );
    return GestureDetector(
      key: ValueKey('paifu-bar-${h.tile}'),
      behavior: HitTestBehavior.opaque,
      onTap: onBarTap == null ? null : () => onBarTap!(h.tile),
      child: SizedBox(
        width: tw,
        height: barH,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            for (final l in labels) label(l, c: l == '★' ? const Color(0xFF9CE59F) : Colors.white),
            if (h.backward)
              Container(
                width: 0.32 * w,
                height: 0.32 * w,
                margin: EdgeInsets.only(bottom: 0.1 * w),
                decoration: const BoxDecoration(color: Color(0xFF9E9E9E), shape: BoxShape.circle),
              )
            else ...[
              label('${h.total}'),
              Container(
                width: tw * 0.72,
                height: (h.frac * maxBar).clamp(0.08 * w, maxBar),
                decoration: BoxDecoration(
                  color: color,
                  borderRadius: BorderRadius.vertical(top: Radius.circular(0.1 * w)),
                  border: selected ? Border.all(color: kioskGold, width: 0.08 * w) : null,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  /// hero 손패(앞면, 크게). 뽑은 패는 오른쪽에 떼어 둔다. 손패를 모르는 걸음은 뒷면.
  /// [before] 가 있으면(최선 보기) 버리기 전 줄을 그리고, 버린 패는 제자리에 흐리게, 같은 종류의 맨 오른쪽 패 위에 막대.
  Widget _heroStrip(double w) {
    final tw = 1.38 * w;
    final seat = paifu.hero;
    final melds = _meldsOf(seat);
    final hand = state.heroHand;
    final r = paifu.result;
    final won = state.finished && r != null && r.winner == seat ? r.winTile : null;
    final b = before;
    final barMap = b == null ? null : bars;
    final barH = barMap == null ? 0.0 : 2.6 * w;
    Widget face(PaifuTile t, {bool mark = false, bool ghost = false}) => Padding(
          padding: EdgeInsets.only(right: tw * 0.05),
          child: ghost
              ? TileView(t.tile, red: t.red, width: tw, dimmed: true)
              : mark
                  ? _glow(TileView(t.tile, red: t.red, width: tw, highlighted: true), tw * 0.6)
                  : TileView(t.tile, red: t.red, width: tw),
        );
    // 막대 칸 + 패. 막대는 그 종류의 맨 오른쪽 패 위에만([barKind] 가 null 이면 빈 칸).
    Widget slot(Widget tile, int? barKind) {
      final h = barKind == null ? null : barMap?[barKind];
      return Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(width: tw, height: barH, child: h == null ? null : _bar(h, w, tw, barH)),
          tile,
        ],
      );
    }

    final List<Widget> tiles;
    if (b != null) {
      final all = b.all;
      final rightmost = <int, int>{for (final (i, t) in all.indexed) t.tile: i};
      tiles = [
        for (final (i, t) in b.row.indexed) slot(face(t, ghost: b.ghost == i), rightmost[t.tile] == i ? t.tile : null),
        if (b.drawn != null) ...[
          SizedBox(width: tw * 0.35),
          slot(
            face(b.drawn!, mark: b.ghost != -1, ghost: b.ghost == -1),
            rightmost[b.drawn!.tile] == b.row.length ? b.drawn!.tile : null,
          ),
        ],
      ];
    } else {
      tiles = _heroTiles(w, tw, hand, melds, won, face);
    }
    return SizedBox(
      height: 2.2 * w + barH,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: Stack(
              alignment: Alignment.bottomCenter,
              children: [
                if (barH > 0)
                  Positioned(
                    top: 0,
                    left: 0,
                    right: 0,
                    height: barH,
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        color: const Color(0xC0000000),
                        borderRadius: BorderRadius.circular(0.3 * w),
                      ),
                    ),
                  ),
                Row(
                  key: const ValueKey('paifu-hero-hand'),
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: tiles,
                ),
                if (b == null && hand == null && paifu.hasHeroHands)
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

  /// 평소의 hero 손패 줄(앞면 · 헤아린 손패 · 뒷면 + 뽑은 패 · 화료패).
  List<Widget> _heroTiles(double w, double tw, List<PaifuTile>? hand, List<PaifuMeld> melds, PaifuTile? won,
      Widget Function(PaifuTile t, {bool mark, bool ghost}) face) {
    return <Widget>[
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
  late Future<List<Paifu>> _list = PaifuStore.list(widget.gameId);

  /// 재생 화면에서 손패를 복원 · 되돌렸을 수 있어 돌아오면 다시 읽는다.
  void _reload() => setState(() => _list = PaifuStore.list(widget.gameId));

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
                itemBuilder: (context, i) => _PaifuTile(list[i], gameId: widget.gameId, onReturn: _reload),
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

  /// 기기에 저장된 패보면 그 대국(재생 화면에 넘겨 손패 복원을 낸다). 예시는 null.
  final String? gameId;
  final VoidCallback? onReturn;
  const _PaifuTile(this.p, {this.gameId, this.onReturn});

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
      subtitle: Text('버림 $discards장 · $end · ${p.hasHeroHands ? (p.handSource == 'claude_api' ? '손패 복원함' : '손패 있음') : '버림만'}'),
      onTap: () async {
        await Navigator.of(context).push(MaterialPageRoute(builder: (_) => PaifuScreen(paifu: p, gameId: gameId)));
        onReturn?.call();
      },
    );
  }
}

/// 앱에 묶어 둔 패보 예시(assets/paifu/*.json · assets/paifu_h3/*.json) 목록.
class PaifuAssetListScreen extends StatefulWidget {
  const PaifuAssetListScreen({super.key});

  /// 패보 예시를 담은 묶음 폴더. 경로 순으로 읽으므로 2반장(assets/paifu/) 뒤에 3반장(assets/paifu_h3/, 11-23 헤드 녹화로 복구).
  static const folders = ['assets/paifu/', 'assets/paifu_h3/'];

  /// 묶음에 든 패보를 경로 순으로 읽는다. 못 읽는 파일은 건너뛴다.
  /// 같은 제목의 패보가 여럿이고 그중 손패가 있는 판이 있으면 손패 없는(버림만) 판은 뺀다
  /// — 옛 버림만 3반장 동1국(r20_143236)이 손패까지 복구한 판에 가려진다.
  static Future<List<Paifu>> load({AssetBundle? bundle}) async {
    final b = bundle ?? rootBundle;
    final manifest = await AssetManifest.loadFromAssetBundle(b);
    final paths = [
      for (final a in manifest.listAssets())
        if (a.endsWith('.json') && folders.any(a.startsWith)) a,
    ]..sort();
    final out = <Paifu>[];
    for (final a in paths) {
      try {
        out.add(await PaifuAssetScreen.load(a, bundle: b));
      } catch (_) {}
    }
    final withHands = {
      for (final p in out)
        if (p.title.isNotEmpty && p.hasHeroHands) p.title,
    };
    return [
      for (final p in out)
        if (p.hasHeroHands || !withHands.contains(p.title)) p,
    ];
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
