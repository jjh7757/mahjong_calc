/// 패보 복기 질문 창(설계서 `docs/paifu_review_agent_app_design_1122.md` 3절 · 6절 2단계).
///
/// [ReviewAskController] 가 대화(질문 · 상태 · 답)를 쥐고, [ReviewAskPanel] 은 그것을 그리기만 한다. 대화는 화면
/// (`_PaifuScreenState`)이 쥔 controller 에 있어서 창을 닫았다 열어도 · 걸음을 옮겨도 남는다. 글(추천 질문 · 차례 붙이기 ·
/// 답 조각)은 `lib/paifu/review_chat.dart`, 서버 호출은 `lib/services/review_ask_client.dart`.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../../paifu/review_chat.dart';
import '../../services/review_ask_client.dart';
import 'review_view.dart' show EngineReviewStatus;

/// 질문 하나를 서버에 묻는 함수([ReviewAskClient.ask] 와 같은 꼴). 시험에서 가짜를 넣는다.
typedef ReviewAsker = Future<ReviewAnswer> Function({
  required Map<String, dynamic> facts,
  required String question,
  List<ReviewExchange> history,
});

/// 질문 창 문구(설계서 3-4).
const askNoKeyMessage = '이 빌드에는 서버 키가 없어 질문할 수 없습니다';
const askWaitEngineMessage = '참고값 계산이 끝나면 보냅니다';
const askFailedMessage = '질문에 실패했습니다.';
const askFallbackNote = '확인된 사실만 답했습니다';
const askNoRiskNote = '방총 위험 정보 없이 답했습니다';
const askHint = '질문을 쓰세요';

/// 대화 항목의 상태. waitEngine = 엔진 참고값 계산이 끝나기를 기다림(끝나면 저절로 보냄).
enum AskEntryState { waitEngine, pending, answered, failed }

/// 대화 한 항목(질문 하나와 그 답).
class AskEntry {
  /// 보낸 글 그대로(차례를 붙였으면 붙인 글).
  final String question;
  AskEntryState state;
  ReviewAnswer? answer;

  /// 실패 까닭 한 줄.
  String? error;

  /// 엔진 계산이 실패한 채로 보냄(수비 칸 없는 사실표).
  bool noRisk = false;

  /// 답을 기다린 초(1초마다 늘어남).
  int seconds = 0;

  AskEntry(this.question, this.state);
}

/// 질문 창의 대화 · 입력 줄 · 차례 칩 값. 한 번에 한 질문만 보낸다(답을 기다리는 동안 [busy]).
class ReviewAskController extends ChangeNotifier {
  /// 서버에 묻는 함수.
  final ReviewAsker asker;

  /// 보낼 때의 사실표(화면이 `agentFacts(_p, _review.review)` 를 캐시해 준다).
  final Map<String, dynamic> Function() facts;

  /// 지금 엔진 참고값 계산 상태. pending 이면 끝날 때까지 기다렸다가([engineSettled]) 보낸다.
  final EngineReviewStatus Function() engine;

  ReviewAskController({required this.asker, required this.facts, required this.engine});

  final List<AskEntry> _entries = [];
  List<AskEntry> get entries => List.unmodifiable(_entries);

  final input = TextEditingController();
  final inputFocus = FocusNode(debugLabel: 'paifu-ask-input');

  /// "N순에 대해" 칩. 걸음을 옮겨도 유지.
  bool turnOn = true;

  /// 대화를 비울 때마다 올린다 — 늦게 온 답이 이 값을 보고 버려진다.
  int _gen = 0;
  bool _disposed = false;
  Timer? _tick;

  /// 답을 기다리는 항목이 있는가(엔진 대기 포함). 이 동안 추천 질문 · 보내기 · "다시" 를 잠근다.
  bool get busy => _entries.any((e) => e.state == AskEntryState.waitEngine || e.state == AskEntryState.pending);

  void setTurnOn(bool on) {
    turnOn = on;
    notifyListeners();
  }

  /// 다 만든 글 [question] 을 새 항목으로 보낸다. 빈 글 · 기다리는 중이면 보내지 않고 false.
  bool send(String question) {
    final q = question.trim();
    if (_disposed || q.isEmpty || busy) return false;
    final e = AskEntry(q, AskEntryState.waitEngine);
    _entries.add(e);
    _start(e);
    return true;
  }

  /// 실패한 항목을 같은 글로 다시(새 항목을 만들지 않음).
  void retry(AskEntry e) {
    if (_disposed || busy || e.state != AskEntryState.failed || !_entries.contains(e)) return;
    _start(e);
  }

  void _start(AskEntry e) {
    e
      ..answer = null
      ..error = null
      ..noRisk = false
      ..seconds = 0;
    if (engine() == EngineReviewStatus.pending) {
      e.state = AskEntryState.waitEngine;
      notifyListeners();
      return;
    }
    _dispatch(e);
  }

  /// 화면이 엔진 계산이 끝났을 때(ready · failed) 부른다: 기다리던 질문을 보낸다.
  void engineSettled() {
    if (_disposed || engine() == EngineReviewStatus.pending) return;
    for (final e in [..._entries]) {
      if (e.state == AskEntryState.waitEngine) _dispatch(e);
    }
  }

  /// [e] 앞의 성공한 질문 · 답(순서대로). 실패 · 기다리는 중은 뺀다. 최근 4쌍으로 자르는 것은 [askBody].
  List<ReviewExchange> _historyBefore(AskEntry e) {
    final out = <ReviewExchange>[];
    for (final x in _entries) {
      if (identical(x, e)) break;
      final a = x.answer;
      if (x.state == AskEntryState.answered && a != null) out.add(ReviewExchange(x.question, a.answer));
    }
    return out;
  }

  Future<void> _dispatch(AskEntry e) async {
    final gen = _gen;
    e
      ..state = AskEntryState.pending
      ..seconds = 0
      ..noRisk = engine() == EngineReviewStatus.failed;
    final history = _historyBefore(e);
    _tick ??= Timer.periodic(const Duration(seconds: 1), (_) => _onTick());
    notifyListeners();
    try {
      final a = await asker(facts: facts(), question: e.question, history: history);
      if (gen != _gen) return;
      e
        ..state = AskEntryState.answered
        ..answer = a;
    } on ReviewAskException catch (x) {
      if (gen != _gen) return;
      e
        ..state = AskEntryState.failed
        ..error = x.message;
    } catch (_) {
      if (gen != _gen) return;
      e
        ..state = AskEntryState.failed
        ..error = askFailedMessage;
    }
    _stopTickIfIdle();
    notifyListeners();
  }

  void _onTick() {
    var any = false;
    for (final e in _entries) {
      if (e.state == AskEntryState.pending) {
        e.seconds++;
        any = true;
      }
    }
    if (!any) {
      _stopTickIfIdle();
      return;
    }
    notifyListeners();
  }

  void _stopTickIfIdle() {
    if (_entries.any((e) => e.state == AskEntryState.pending)) return;
    _tick?.cancel();
    _tick = null;
  }

  /// 패보가 바뀜: 대화를 비우고 오던 답은 버린다(차례 칩 값은 그대로).
  void clear() {
    _gen++;
    _tick?.cancel();
    _tick = null;
    _entries.clear();
    input.clear();
    notifyListeners();
  }

  @override
  void dispose() {
    _gen++;
    _disposed = true;
    _tick?.cancel();
    _tick = null;
    input.dispose();
    inputFocus.dispose();
    super.dispose();
  }
}

/// 질문 창: 머리 줄 → (키 없음 한 줄) → 대화 목록 → 추천 질문 → "N순에 대해" 칩 → 입력 줄.
class ReviewAskPanel extends StatefulWidget {
  final ReviewAskController controller;

  /// 서버 키가 있는가. 없으면 한 줄 알리고 추천 질문 · 입력 · 보내기를 잠근다.
  final bool configured;

  /// 지금 걸음의 추천 질문(`suggestedQuestions`). 누르면 그 글 그대로 보낸다.
  final List<String> suggestions;

  /// 지금 걸음이 내 버림 걸음이면 그 차례(아니면 null — 차례 칩이 없다).
  final int? turn;

  /// "N순 보기" 칩을 낼 차례인가(리뷰에 그 차례가 있는가).
  final bool Function(int turn) canGoto;
  final ValueChanged<int> onGoto;
  final VoidCallback onClose;

  /// 보낸 뒤(입력 줄을 비운 뒤) 부른다 — 화면이 글자판을 내리고 방향키 자리를 되돌린다.
  final VoidCallback? onSent;

  /// 높이를 다 쓴다(가로 패널 — 대화 목록이 남는 높이를 채우고 입력 줄은 아래에 붙음).
  /// false 면 내용만큼(세로 시트 — 바깥 최대 높이까지).
  final bool fill;

  /// 높이가 모자람(글자판이 올라옴): 추천 질문 줄을 숨긴다.
  final bool compact;

  const ReviewAskPanel({
    super.key,
    required this.controller,
    required this.configured,
    required this.suggestions,
    required this.turn,
    required this.canGoto,
    required this.onGoto,
    required this.onClose,
    this.onSent,
    this.fill = false,
    this.compact = false,
  });

  @override
  State<ReviewAskPanel> createState() => _ReviewAskPanelState();
}

class _ReviewAskPanelState extends State<ReviewAskPanel> {
  final _scroll = ScrollController();

  /// 대화 목록의 꼴(항목 수 · 상태). 바뀌면 끝으로 내린다(초가 늘 때마다 내리지는 않음).
  String _shape = '';

  ReviewAskController get _c => widget.controller;

  @override
  void initState() {
    super.initState();
    _shape = _shapeOf();
    _c.addListener(_changed);
    if (_c.entries.isNotEmpty) _toEnd();
  }

  @override
  void didUpdateWidget(covariant ReviewAskPanel old) {
    super.didUpdateWidget(old);
    if (!identical(old.controller, widget.controller)) {
      old.controller.removeListener(_changed);
      widget.controller.addListener(_changed);
      _shape = _shapeOf();
    }
  }

  @override
  void dispose() {
    _c.removeListener(_changed);
    _scroll.dispose();
    super.dispose();
  }

  String _shapeOf() => [for (final e in _c.entries) e.state.index].join(',');

  void _changed() {
    if (!mounted) return;
    final s = _shapeOf();
    final moved = s != _shape;
    _shape = s;
    setState(() {});
    if (moved) _toEnd();
  }

  void _toEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_scroll.hasClients) return;
      _scroll.jumpTo(_scroll.position.maxScrollExtent);
    });
  }

  bool get _canSend => widget.configured && !_c.busy;

  void _submit() {
    if (!_canSend || _c.input.text.trim().isEmpty) return; // 빈 글은 차례를 붙여도 보내지 않는다
    final turn = widget.turn != null && _c.turnOn ? widget.turn : null;
    final q = withTurnContext(_c.input.text, turn);
    if (!_c.send(q)) return;
    _c.input.clear();
    widget.onSent?.call();
  }

  void _ask(String q) {
    if (!_canSend) return;
    if (_c.send(q)) widget.onSent?.call();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final small = theme.textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant);
    final entries = _c.entries;
    final list = ListView.builder(
      key: const ValueKey('paifu-ask-list'),
      controller: _scroll,
      shrinkWrap: !widget.fill,
      padding: const EdgeInsets.symmetric(vertical: 4),
      itemCount: entries.isEmpty ? 1 : entries.length,
      itemBuilder: (context, i) => entries.isEmpty
          ? Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Text('자주 묻는 질문을 누르거나 직접 써서 물을 수 있습니다.', style: small),
            )
          : _entry(theme, entries[i], i),
    );
    final turn = widget.turn;
    // 높이가 아주 모자라면(작은 폰 + 글자판) 머리 줄도 숨긴다 — 닫기는 단추 줄의 "질문" 으로도 된다.
    return LayoutBuilder(builder: (context, box) => _column(theme, list, turn, header: box.maxHeight >= 140));
  }

  Widget _column(ThemeData theme, Widget list, int? turn, {required bool header}) {
    final scheme = theme.colorScheme;
    return Column(
      key: const ValueKey('paifu-ask-panel'),
      mainAxisSize: widget.fill ? MainAxisSize.max : MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (header)
          SizedBox(
            height: 36,
            child: Row(
              children: [
                Text('질문', style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
                const Spacer(),
                IconButton(
                  key: const ValueKey('paifu-ask-close'),
                  tooltip: '닫기',
                  visualDensity: VisualDensity.compact,
                  icon: const Icon(Icons.close),
                  onPressed: widget.onClose,
                ),
              ],
            ),
          ),
        if (!widget.configured)
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Text(
              askNoKeyMessage,
              key: const ValueKey('paifu-ask-nokey'),
              style: theme.textTheme.bodySmall?.copyWith(color: scheme.error),
            ),
          ),
        if (widget.fill) Expanded(child: list) else Flexible(child: list),
        if (!widget.compact && widget.suggestions.isNotEmpty)
          SizedBox(
            height: 40,
            child: SingleChildScrollView(
              key: const ValueKey('paifu-ask-suggest'),
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  for (var i = 0; i < widget.suggestions.length; i++)
                    Padding(
                      padding: const EdgeInsets.only(right: 6),
                      child: ActionChip(
                        key: ValueKey('paifu-ask-suggest-$i'),
                        label: Text(widget.suggestions[i]),
                        visualDensity: VisualDensity.compact,
                        materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                        onPressed: _canSend ? () => _ask(widget.suggestions[i]) : null,
                      ),
                    ),
                ],
              ),
            ),
          ),
        if (turn != null)
          Align(
            alignment: Alignment.centerLeft,
            child: FilterChip(
              key: const ValueKey('paifu-ask-turn-chip'),
              label: Text('$turn순에 대해'),
              selected: _c.turnOn,
              visualDensity: VisualDensity.compact,
              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
              onSelected: _c.setTurnOn,
            ),
          ),
        Padding(
          padding: const EdgeInsets.only(top: 4),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  key: const ValueKey('paifu-ask-input'),
                  controller: _c.input,
                  focusNode: _c.inputFocus,
                  enabled: widget.configured,
                  maxLength: reviewQuestionMax,
                  maxLines: 1,
                  textInputAction: TextInputAction.send,
                  decoration: const InputDecoration(
                    hintText: askHint,
                    isDense: true,
                    counterText: '',
                    border: OutlineInputBorder(),
                    contentPadding: EdgeInsets.symmetric(horizontal: 10, vertical: 10),
                  ),
                  onSubmitted: (_) => _submit(),
                ),
              ),
              const SizedBox(width: 6),
              IconButton.filled(
                key: const ValueKey('paifu-ask-send'),
                tooltip: '보내기',
                icon: const Icon(Icons.send),
                onPressed: _canSend ? _submit : null,
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _entry(ThemeData theme, AskEntry e, int i) {
    final scheme = theme.colorScheme;
    final small = theme.textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant);
    final a = e.answer;
    final Widget body;
    switch (e.state) {
      case AskEntryState.waitEngine:
        body = Text(askWaitEngineMessage, key: const ValueKey('paifu-ask-wait-engine'), style: small);
      case AskEntryState.pending:
        body = Text('답을 찾는 중… ${e.seconds}초', key: const ValueKey('paifu-ask-pending'), style: small);
      case AskEntryState.failed:
        body = Row(
          children: [
            Expanded(
              child: Text(
                e.error ?? askFailedMessage,
                key: const ValueKey('paifu-ask-error'),
                style: theme.textTheme.bodySmall?.copyWith(color: scheme.error),
              ),
            ),
            TextButton(
              key: const ValueKey('paifu-ask-retry'),
              onPressed: widget.configured && !_c.busy ? () => _c.retry(e) : null,
              child: const Text('다시'),
            ),
          ],
        );
      case AskEntryState.answered:
        final turns = [
          for (final n in a?.turns ?? const <int>[])
            if (widget.canGoto(n)) n,
        ];
        body = Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text.rich(
              TextSpan(
                children: [
                  for (final s in answerSpans(a?.answer ?? ''))
                    TextSpan(
                      text: s.text,
                      style: s.kind == AnswerSpanKind.text ? null : const TextStyle(fontWeight: FontWeight.w700),
                    ),
                ],
              ),
              key: ValueKey('paifu-ask-answer-$i'),
              style: theme.textTheme.bodyMedium,
            ),
            if (a != null && !a.verified)
              Text(askFallbackNote, key: const ValueKey('paifu-ask-fallback'), style: small),
            if (e.noRisk) Text(askNoRiskNote, key: const ValueKey('paifu-ask-norisk'), style: small),
            if (turns.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 2),
                child: Wrap(
                  spacing: 6,
                  children: [
                    for (final n in turns)
                      ActionChip(
                        key: ValueKey('paifu-ask-goto-$n'),
                        label: Text('$n순 보기'),
                        visualDensity: VisualDensity.compact,
                        materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                        onPressed: () => widget.onGoto(n),
                      ),
                  ],
                ),
              ),
          ],
        );
    }
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Align(
            alignment: Alignment.centerRight,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(color: scheme.primaryContainer, borderRadius: BorderRadius.circular(10)),
              child: Text(
                e.question,
                key: ValueKey('paifu-ask-q-$i'),
                style: theme.textTheme.bodyMedium?.copyWith(color: scheme.onPrimaryContainer),
              ),
            ),
          ),
          const SizedBox(height: 4),
          body,
        ],
      ),
    );
  }
}
