import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../engine/calculator.dart';
import '../../game/game.dart';
import '../../game/game_store.dart';
import '../kiosk.dart';
import '../name_keyboard.dart';
import 'history_screen.dart';
import 'record_edit.dart';
import 'settlement_screen.dart';
import 'win_sheet.dart';

/// 대국 화면. 진행 중인 대국이 없으면 설정 폼, 있으면 점수판.
class GameScreen extends StatelessWidget {
  const GameScreen({super.key});

  @override
  Widget build(BuildContext context) {
    // 화료·유국 기록으로 대국이 끝나면 종료 화면을 띄운다.
    return GameEndWatcher(child: ListenableBuilder(
      listenable: gameStore,
      builder: (context, _) {
        final g = gameStore.current;
        // 키오스크면 어두운 테마·큰 글자로 가운데 모아 보여 준다(폰 화면은 그대로).
        return kioskWrap(context, Scaffold(
          appBar: AppBar(
            title: Text(g == null ? '대국 시작' : '대국 ${g.roundLabel}'),
            actions: [
              IconButton(
                tooltip: '지난 대국',
                icon: const Icon(Icons.history),
                onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const HistoryScreen())),
              ),
            ],
          ),
          body: kioskPage(context, g == null ? const _SetupForm() : _Board(game: g)),
        ));
      },
    ));
  }
}

// ---------------- 설정 ----------------

class _SetupForm extends StatefulWidget {
  const _SetupForm();

  @override
  State<_SetupForm> createState() => _SetupFormState();
}

class _SetupFormState extends State<_SetupForm> {
  final _names = List.generate(4, (i) => TextEditingController(text: '플레이어 ${i + 1}'));
  int _start = 25000;
  int _ret = 30000;
  String _uma = '20-10';
  bool _eastOnly = false;
  int _rounding = 1;
  int _multiRon = GameSettings.multiRonDouble;
  bool _agariYame = true;
  bool _tenpaiYame = true;
  bool _overtime = true;

  // 중간부터 시작
  bool _resume = false;
  int _roundWind = 0;
  int _roundNumber = 1;
  int _honba = 0;
  int _sticks = 0;
  final _scores = List.generate(4, (_) => TextEditingController(text: '25000'));

  static const _umaPresets = {'10-5': (10, 5), '20-10': (20, 10), '30-10': (30, 10)};

  @override
  void dispose() {
    for (final c in _names) {
      c.dispose();
    }
    for (final c in _scores) {
      c.dispose();
    }
    super.dispose();
  }

  GameSettings get _settings {
    final uma = _umaPresets[_uma]!;
    return GameSettings(
      startPoints: _start,
      returnPoints: _ret,
      umaBig: uma.$1,
      umaSmall: uma.$2,
      eastOnly: _eastOnly,
      roundingMode: _rounding,
      multiRon: _multiRon,
      agariYame: _agariYame,
      tenpaiYame: _tenpaiYame,
      overtime: _overtime,
    );
  }

  List<String> get _nameList => _names.map((c) => c.text.trim().isEmpty ? '?' : c.text.trim()).toList();

  List<int> get _scoreList => _scores.map((c) => int.tryParse(c.text.replaceAll(',', '').trim()) ?? 0).toList();

  /// 점수 합이 시작점×4 − 공탁 과 맞는지. 맞지 않으면 기대값을 돌려준다.
  int? get _scoreMismatch {
    final expected = _start * 4 - _sticks * 1000;
    final sum = _scoreList.fold(0, (a, b) => a + b);
    return sum == expected ? null : expected;
  }

  Future<void> _editName(int i) async {
    final cur = _names[i].text;
    final v = await showNameKeyboard(
      context,
      title: '${Game.windNames[i]}가 이름',
      initial: cur,
      replaceOnType: cur == '플레이어 ${i + 1}',
    );
    if (v != null && mounted) setState(() => _names[i].text = v);
  }

  void _setStart(int v) {
    setState(() {
      final old = _start;
      _start = v;
      for (final c in _scores) {
        if (c.text == '$old') c.text = '$v';
      }
    });
  }

  void _start0() {
    if (_resume) {
      gameStore.resume(
        _nameList,
        _settings,
        scores: _scoreList,
        roundWind: _roundWind,
        roundNumber: _roundNumber,
        honba: _honba,
        riichiSticks: _sticks,
      );
    } else {
      gameStore.start(_nameList, _settings);
    }
    // 키오스크는 대국 중 첫 화면이 테이블 화면이므로 바로 그리로 간다.
    if (isKioskLayout(context)) Navigator.of(context).popUntil((r) => r.isFirst);
  }

  Widget _stepper(String label, int value, void Function(int) onChanged, {int max = 20}) {
    return Row(
      children: [
        SizedBox(width: 72, child: Text(label)),
        IconButton(
          icon: const Icon(Icons.remove_circle_outline),
          onPressed: value > 0 ? () => onChanged(value - 1) : null,
        ),
        Text('$value', style: const TextStyle(fontSize: 16)),
        IconButton(
          icon: const Icon(Icons.add_circle_outline),
          onPressed: value < max ? () => onChanged(value + 1) : null,
        ),
      ],
    );
  }

  List<Widget> _resumeFields(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final mismatch = _scoreMismatch;
    final dealer = _roundNumber - 1;
    final names = _nameList;
    return [
      const SizedBox(height: 8),
      Row(
        children: [
          const SizedBox(width: 72, child: Text('장풍')),
          Wrap(
            spacing: 6,
            children: [
              for (var w = 0; w < 4; w++)
                ChoiceChip(
                  label: Text(Game.windNames[w]),
                  selected: _roundWind == w,
                  onSelected: (_) => setState(() => _roundWind = w),
                ),
            ],
          ),
        ],
      ),
      const SizedBox(height: 6),
      Row(
        children: [
          const SizedBox(width: 72, child: Text('국')),
          Wrap(
            spacing: 6,
            children: [
              for (var n = 1; n <= 4; n++)
                ChoiceChip(
                  key: ValueKey('resume-round-$n'),
                  label: Text('$n국'),
                  selected: _roundNumber == n,
                  onSelected: (_) => setState(() => _roundNumber = n),
                ),
            ],
          ),
        ],
      ),
      Padding(
        padding: const EdgeInsets.only(left: 72, top: 4),
        child: Text(
          '친: ${names[dealer]} (${Game.windNames[dealer]}가 자리)',
          style: TextStyle(fontSize: 12, color: scheme.outline),
        ),
      ),
      _stepper('본장', _honba, (v) => setState(() => _honba = v)),
      _stepper('공탁', _sticks, (v) => setState(() => _sticks = v), max: 8),
      const SizedBox(height: 4),
      Text('현재 점수', style: Theme.of(context).textTheme.titleSmall),
      const SizedBox(height: 6),
      for (var i = 0; i < 4; i++)
        Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: TextField(
            key: ValueKey('resume-score-$i'),
            controller: _scores[i],
            keyboardType: const TextInputType.numberWithOptions(signed: true),
            inputFormatters: [FilteringTextInputFormatter.allow(RegExp('[-0-9]'))],
            onChanged: (_) => setState(() {}),
            decoration: InputDecoration(labelText: names[i], border: const OutlineInputBorder(), isDense: true),
          ),
        ),
      if (mismatch != null)
        Text(
          '점수 합이 ${_scoreList.fold(0, (a, b) => a + b)} 입니다. '
          '시작점×4 − 공탁 = $mismatch 이어야 맞습니다 (그대로 시작할 수는 있습니다)',
          style: TextStyle(fontSize: 12, color: scheme.error),
        ),
    ];
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('자리 순서 (동 → 남 → 서 → 북)', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        for (var i = 0; i < 4; i++)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            // 누르면 앱 안 키보드 패널(기기 키보드 없이 터치만으로).
            child: TextField(
              key: ValueKey('setup-name-$i'),
              controller: _names[i],
              readOnly: true,
              showCursor: false,
              onTap: () => _editName(i),
              decoration: InputDecoration(
                labelText: '${Game.windNames[i]}가',
                border: const OutlineInputBorder(),
                isDense: true,
                suffixIcon: const Icon(Icons.keyboard),
              ),
            ),
          ),
        const SizedBox(height: 8),
        Text('규칙', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Row(
          children: [
            const SizedBox(width: 72, child: Text('시작점')),
            Wrap(
              spacing: 6,
              children: [
                for (final v in [25000, 30000])
                  ChoiceChip(label: Text('$v'), selected: _start == v, onSelected: (_) => _setStart(v)),
              ],
            ),
          ],
        ),
        const SizedBox(height: 6),
        Row(
          children: [
            const SizedBox(width: 72, child: Text('반환점')),
            Wrap(
              spacing: 6,
              children: [
                for (final v in [25000, 30000])
                  ChoiceChip(label: Text('$v'), selected: _ret == v, onSelected: (_) => setState(() => _ret = v)),
              ],
            ),
          ],
        ),
        const SizedBox(height: 6),
        Row(
          children: [
            const SizedBox(width: 72, child: Text('우마')),
            Wrap(
              spacing: 6,
              children: [
                for (final k in _umaPresets.keys)
                  ChoiceChip(label: Text(k), selected: _uma == k, onSelected: (_) => setState(() => _uma = k)),
              ],
            ),
          ],
        ),
        const SizedBox(height: 6),
        Row(
          children: [
            const SizedBox(width: 72, child: Text('길이')),
            Wrap(
              spacing: 6,
              children: [
                ChoiceChip(
                  label: const Text('반장전'),
                  selected: !_eastOnly,
                  onSelected: (_) => setState(() => _eastOnly = false),
                ),
                ChoiceChip(
                  label: const Text('동풍전'),
                  selected: _eastOnly,
                  onSelected: (_) => setState(() => _eastOnly = true),
                ),
              ],
            ),
          ],
        ),
        const SizedBox(height: 6),
        Row(
          children: [
            const SizedBox(width: 72, child: Text('반올림')),
            Wrap(
              spacing: 6,
              children: [
                ChoiceChip(
                  label: const Text('오사육입'),
                  selected: _rounding == 1,
                  onSelected: (_) => setState(() => _rounding = 1),
                ),
                ChoiceChip(
                  label: const Text('소수 1자리'),
                  selected: _rounding == 0,
                  onSelected: (_) => setState(() => _rounding = 0),
                ),
              ],
            ),
          ],
        ),
        const SizedBox(height: 6),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Padding(
              padding: EdgeInsets.only(top: 8),
              child: SizedBox(width: 72, child: Text('동시 론')),
            ),
            Expanded(
              child: Wrap(
                spacing: 6,
                children: [
                  for (var m = 0; m < GameSettings.multiRonLabels.length; m++)
                    ChoiceChip(
                      key: ValueKey('multi-ron-$m'),
                      label: Text(GameSettings.multiRonLabels[m]),
                      selected: _multiRon == m,
                      onSelected: (_) => setState(() => _multiRon = m),
                    ),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: 6),
        // 작혼식: 올라스 뒤 1위가 반환점 이상이면 종료, 아니면 서입(매 국 끝에 반환점을 넘기면 종료, 서4국까지).
        SwitchListTile(
          key: const ValueKey('overtime-switch'),
          contentPadding: EdgeInsets.zero,
          dense: true,
          title: Text(_eastOnly ? '남입(연장전)' : '서입(연장전)'),
          subtitle: const Text('올라스 뒤 1위가 반환점 미만이면 연장, 반환점을 넘기면 종료'),
          value: _overtime,
          onChanged: (v) => setState(() => _overtime = v),
        ),
        // 작혼식: 올라스에 친이 1위(반환점 이상)면 친의 선택 없이 자동으로 끝난다.
        SwitchListTile(
          key: const ValueKey('agari-yame-switch'),
          contentPadding: EdgeInsets.zero,
          dense: true,
          title: const Text('아가리야메'),
          subtitle: const Text('올라스에 친이 화료해 1위면 연장 없이 종료'),
          value: _agariYame,
          onChanged: (v) => setState(() => _agariYame = v),
        ),
        SwitchListTile(
          key: const ValueKey('tenpai-yame-switch'),
          contentPadding: EdgeInsets.zero,
          dense: true,
          title: const Text('텐파이야메'),
          subtitle: const Text('올라스 유국에 친이 텐파이·1위면 연장 없이 종료'),
          value: _tenpaiYame,
          onChanged: (v) => setState(() => _tenpaiYame = v),
        ),
        Text(
          '오카 ${(_ret - _start) * 4 ~/ 1000} (1위에게)',
          style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.outline),
        ),
        const SizedBox(height: 8),
        SwitchListTile(
          key: const ValueKey('resume-switch'),
          contentPadding: EdgeInsets.zero,
          title: const Text('중간부터 기록 시작'),
          subtitle: const Text('이미 진행 중인 대국의 현재 국·점수부터 적습니다'),
          value: _resume,
          onChanged: (v) => setState(() => _resume = v),
        ),
        if (_resume) ..._resumeFields(context),
        const SizedBox(height: 20),
        FilledButton(onPressed: _start0, child: Text(_resume ? '여기서부터 기록' : '대국 시작')),
      ],
    );
  }
}

// ---------------- 점수판 ----------------

class _Board extends StatelessWidget {
  final Game game;
  const _Board({required this.game});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final g = game;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
          child: Row(
            children: [
              Text(g.roundLabel, style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(width: 12),
              Text('공탁 ${g.riichiSticks}', style: TextStyle(color: scheme.outline)),
              const Spacer(),
              if (g.isOver)
                Text(
                  g.endLabel,
                  style: TextStyle(color: scheme.error, fontWeight: FontWeight.w600),
                )
              else if (g.isOvertime)
                Text(
                  '연장',
                  style: TextStyle(color: scheme.error, fontWeight: FontWeight.w600),
                )
              else if (g.isLastRound)
                Text(
                  '올라스',
                  style: TextStyle(color: scheme.primary, fontWeight: FontWeight.w600),
                ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.all(12),
          child: Card(
            child: Column(
              children: [
                for (var s = 0; s < 4; s++)
                  ListTile(
                    dense: true,
                    leading: CircleAvatar(
                      radius: 16,
                      backgroundColor: s == g.dealer ? scheme.primary : scheme.surfaceContainerHighest,
                      child: Text(
                        Tiles.name(g.seatWindOf(s)),
                        style: TextStyle(fontSize: 13, color: s == g.dealer ? scheme.onPrimary : scheme.onSurface),
                      ),
                    ),
                    title: Text(g.names[s]),
                    subtitle: s == g.dealer ? const Text('친', style: TextStyle(fontSize: 11)) : null,
                    trailing: Text(
                      '${g.scores[s]}',
                      style: TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.w600,
                        color: g.scores[s] < 0 ? scheme.error : null,
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
        // 대국 종료(토비 또는 아가리야메·텐파이야메): 점수는 그대로 두고 정산만 할 수 있다.
        if (g.isOver)
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
            child: Card(
              key: const ValueKey('game-over-banner'),
              color: g.anyBusted ? scheme.errorContainer : scheme.primaryContainer,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
                child: Row(
                  children: [
                    Icon(Icons.flag, size: 18, color: g.anyBusted ? scheme.onErrorContainer : scheme.onPrimaryContainer),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        g.endNote,
                        style: TextStyle(
                            fontSize: 13, color: g.anyBusted ? scheme.onErrorContainer : scheme.onPrimaryContainer),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12),
          child: Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              if (g.isOver)
                FilledButton.icon(
                  icon: const Icon(Icons.calculate_outlined, size: 18),
                  label: const Text('정산'),
                  onPressed: () =>
                      Navigator.of(context).push(MaterialPageRoute(builder: (_) => SettlementScreen(game: g))),
                )
              else ...[
                FilledButton.icon(
                  icon: const Icon(Icons.emoji_events_outlined, size: 18),
                  label: const Text('화료'),
                  onPressed: () => showWinSheet(context, g),
                ),
                OutlinedButton.icon(
                  icon: const Icon(Icons.flag_outlined, size: 18),
                  label: const Text('리치'),
                  onPressed: () => showRiichiPicker(context, g),
                ),
                OutlinedButton.icon(
                  icon: const Icon(Icons.block, size: 18),
                  label: const Text('유국'),
                  onPressed: () => showDrawDialog(context, g),
                ),
                OutlinedButton.icon(
                  icon: const Icon(Icons.calculate_outlined, size: 18),
                  label: const Text('정산'),
                  onPressed: () =>
                      Navigator.of(context).push(MaterialPageRoute(builder: (_) => SettlementScreen(game: g))),
                ),
              ],
              OutlinedButton.icon(
                key: const ValueKey('game-undo'),
                icon: const Icon(Icons.undo, size: 18),
                label: const Text('마지막 취소'),
                onPressed: g.canUndo ? () => confirmRewind(context) : null,
              ),
              OutlinedButton.icon(
                key: const ValueKey('game-correct'),
                icon: const Icon(Icons.edit_outlined, size: 18),
                label: const Text('점수 정정'),
                onPressed: () => showScoreCorrection(context),
              ),
              TextButton(onPressed: () => _confirmDiscard(context), child: const Text('취소')),
            ],
          ),
        ),
        const SizedBox(height: 8),
        Expanded(
          child: g.events.isEmpty
              ? Center(
                  child: Text('기록 없음', style: TextStyle(color: scheme.outline)),
                )
              : ListView.builder(
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  itemCount: g.events.length,
                  itemBuilder: (_, i) {
                    final idx = g.events.length - 1 - i;
                    final e = g.events[idx];
                    return ListTile(
                      key: ValueKey('game-event-$idx'),
                      dense: true,
                      // 누르면 이 기록부터 되돌리기·점수 정정.
                      onTap: () => showEventActions(context, idx),
                      leading: Text(e.roundLabel, style: const TextStyle(fontSize: 12)),
                      title: Text(e.description, style: const TextStyle(fontSize: 13)),
                      subtitle: Text(
                        List.generate(
                          4,
                          (s) => '${g.names[s]} ${e.delta[s] >= 0 ? '+' : ''}${e.delta[s]}',
                        ).where((t) => !t.endsWith(' +0')).join('  '),
                        style: const TextStyle(fontSize: 11),
                      ),
                    );
                  },
                ),
        ),
      ],
    );
  }
}

// ---------------- 점수판·테이블 화면 공용 대화상자 ----------------

/// 리치한 자리를 골라 리치봉을 공탁에 넣는다.
Future<void> showRiichiPicker(BuildContext context, Game g) => _pickSeat(context, g, '누가 리치?', (s) {
      gameStore.mutate((g) => g.declareRiichi(s));
    });

Future<void> _pickSeat(BuildContext context, Game g, String title, void Function(int seat) onPick) async {
  final seat = await showDialog<int>(
    context: context,
    builder: (ctx) => kioskWrap(ctx, SimpleDialog(
      title: Text(title),
      children: [
        for (var s = 0; s < 4; s++)
          SimpleDialogOption(
            onPressed: () => Navigator.pop(ctx, s),
            child: Text('${Tiles.name(g.seatWindOf(s))}  ${g.names[s]}'),
          ),
      ],
    )),
  );
  if (seat != null) onPick(seat);
}

/// 유국: 텐파이한 자리를 고르고, 텐파이한 자리는 리치 여부도 고른다. 유국만관도 여기서 고른다.
/// 점수판에서 이미 리치한 자리는 텐파이·리치를 켜 둔다. 점수판에 없던 리치는 1000점씩 공탁에 넣는다.
/// 도중 유국(구종구패·사풍연타·사깡산료·사가리치)을 고르면 텐파이와 관계없이 점수 이동 없이 친 유지·본장 +1.
Future<void> showDrawDialog(BuildContext context, Game g) async {
  final tenpai = <int>{...g.riichiSeats};
  final newRiichi = <int>{};
  final nagashi = <int>{};
  String? abortive;
  final kiosk = isKioskLayout(context);
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => kioskWrap(ctx, StatefulBuilder(
      builder: (ctx, setState) => AlertDialog(
        title: Text(abortive == null ? '유국 — 텐파이한 사람' : '도중 유국 — $abortive'),
        content: SizedBox(
          width: kiosk ? 620 : 340,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  const Text('도중 유국', style: TextStyle(fontSize: 13)),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Wrap(
                      spacing: 4,
                      runSpacing: 2,
                      children: [
                        for (final r in Game.abortiveReasons)
                          ChoiceChip(
                            key: ValueKey('draw-abortive-$r'),
                            visualDensity: VisualDensity.compact,
                            label: Text(r),
                            selected: abortive == r,
                            onSelected: (on) => setState(() => abortive = on ? r : null),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
              if (abortive != null) ...[
                const SizedBox(height: 8),
                Text(
                  abortive == '사가리치'
                      ? '점수 이동 없음 · 친 유지 · 본장 +1. 점수판에 없는 리치는 1000점씩 공탁에 넣습니다'
                      : '점수 이동 없음 · 친 유지 · 본장 +1 · 공탁 유지',
                  style: const TextStyle(fontSize: 12),
                ),
              ] else ...[
              const Divider(height: 20),
              for (var s = 0; s < 4; s++)
                CheckboxListTile(
                  key: ValueKey('draw-tenpai-$s'),
                  dense: true,
                  controlAffinity: ListTileControlAffinity.leading,
                  title: Text(g.names[s]),
                  value: tenpai.contains(s),
                  onChanged: (v) => setState(() {
                    if (v == true) {
                      tenpai.add(s);
                    } else {
                      tenpai.remove(s);
                      newRiichi.remove(s);
                    }
                  }),
                  secondary: tenpai.contains(s)
                      ? FilterChip(
                          key: ValueKey('draw-riichi-$s'),
                          label: const Text('리치'),
                          selected: g.riichiSeats.contains(s) || newRiichi.contains(s),
                          // 점수판에 있는 리치는 이미 공탁에 들어가 있어 끌 수 없다.
                          onSelected: g.riichiSeats.contains(s) || g.scores[s] < 1000
                              ? null
                              : (on) => setState(() => on ? newRiichi.add(s) : newRiichi.remove(s)),
                        )
                      : null,
                ),
              const SizedBox(height: 4),
              Text(
                newRiichi.isEmpty ? '텐파이한 사람은 리치 여부도 골라 주세요' : '새 리치 ${newRiichi.length}명: 1000점씩 공탁 (다음 화료자가 가져감)',
                style: const TextStyle(fontSize: 12),
              ),
              const Divider(height: 20),
              Row(
                children: [
                  const Text('유국만관', style: TextStyle(fontSize: 13)),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Wrap(
                      spacing: 4,
                      runSpacing: 2,
                      children: [
                        for (var s = 0; s < 4; s++)
                          FilterChip(
                            key: ValueKey('draw-nagashi-$s'),
                            visualDensity: VisualDensity.compact,
                            label: Text(g.names[s]),
                            selected: nagashi.contains(s),
                            onSelected: (on) => setState(() => on ? nagashi.add(s) : nagashi.remove(s)),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
              if (nagashi.isNotEmpty)
                const Padding(
                  padding: EdgeInsets.only(top: 4),
                  child: Text('만관 쯔모만큼 받음 · 노텐 벌점 없음 · 본장 없음', style: TextStyle(fontSize: 12)),
                ),
              ],
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('취소')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('확인')),
        ],
      ),
    )),
  );
  if (ok != true) return;
  final reason = abortive;
  gameStore.mutate((g) {
    if (reason == '사가리치') {
      g.fourRiichiDraw();
    } else if (reason != null) {
      g.abortiveDraw(reason);
    } else {
      // 리치봉을 먼저 공탁에 넣고 유국 처리한다(공탁은 다음 국으로 넘어간다).
      for (final s in (newRiichi.toList()..sort())) {
        g.declareRiichi(s);
      }
      g.draw(tenpai, nagashi: nagashi);
    }
  });
  if (context.mounted) notifyIfOver(context);
}

/// 대국이 끝났으면(토비·아가리야메·텐파이야메) 알린다. 화료·유국을 기록한 직후 부른다.
void notifyIfOver(BuildContext context) {
  final g = gameStore.current;
  if (g == null || !g.isOver) return;
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(
      content: Text('${g.endNote} (점수판)'),
      duration: const Duration(seconds: 5),
    ));
}

Future<void> _confirmDiscard(BuildContext context) async {
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => kioskWrap(ctx, AlertDialog(
      title: const Text('대국을 저장하지 않고 버릴까요?'),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('아니오')),
        FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('버리기')),
      ],
    )),
  );
  if (ok == true) gameStore.discardCurrent();
}
