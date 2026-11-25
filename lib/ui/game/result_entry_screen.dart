import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../game/game.dart';
import '../../game/game_store.dart';
import '../../game/member_store.dart';
import '../kiosk.dart';
import 'member_screens.dart';
import 'settlement_screen.dart';

/// 앱으로 기록하지 않고 친 대국의 결과(자리별 멤버·최종 점수)를 넣는다.
///
/// 이름은 등록 멤버 명단에서만 고른다. 점수 합이 시작점×4 와 맞아야 저장할 수 있고,
/// 저장하면 지난 대국에 넣고 정산 화면을 띄운다.
class ResultEntryScreen extends StatefulWidget {
  const ResultEntryScreen({super.key});

  @override
  State<ResultEntryScreen> createState() => _ResultEntryScreenState();
}

class _ResultEntryScreenState extends State<ResultEntryScreen> {
  /// 마지막으로 쓴 규칙(GameSettings.toJson).
  static const settingsKey = 'manual.settings';

  static const _seatLabels = ['동(기동)', '남', '서', '북'];
  static const _umaPresets = {'10-5': (10, 5), '20-10': (20, 10), '30-10': (30, 10)};

  final _picked = List<String?>.filled(4, null);
  final _scores = List.generate(4, (_) => TextEditingController());

  /// 자리별 별(하네만 1 · 배만 2 · 삼배만 3 · 역만 5 …를 사람이 세어 넣는다).
  final _stars = List.filled(4, 0);
  static const _maxStars = 99;

  int _start = 25000;
  int _ret = 30000;
  String _uma = '20-10';
  int _rounding = 1;
  bool _eastOnly = false;
  DateTime _date = DateTime.now();

  /// 저장된 규칙을 불러오기 전에 사용자가 규칙을 건드렸으면 덮어쓰지 않는다.
  bool _rulesTouched = false;

  @override
  void initState() {
    super.initState();
    _loadRules();
  }

  @override
  void dispose() {
    for (final c in _scores) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _loadRules() async {
    final p = await SharedPreferences.getInstance();
    final s = p.getString(settingsKey);
    if (s == null || !mounted || _rulesTouched) return;
    try {
      final g = GameSettings.fromJson(jsonDecode(s) as Map<String, dynamic>);
      final uma = _umaPresets.entries.where((e) => e.value == (g.umaBig, g.umaSmall)).map((e) => e.key).firstOrNull;
      setState(() {
        _start = g.startPoints;
        _ret = g.returnPoints;
        if (uma != null) _uma = uma;
        _rounding = g.roundingMode;
        _eastOnly = g.eastOnly;
      });
    } catch (_) {}
  }

  void _rules(VoidCallback f) => setState(() {
        _rulesTouched = true;
        f();
      });

  GameSettings get _settings {
    final uma = _umaPresets[_uma]!;
    return GameSettings(
      startPoints: _start,
      returnPoints: _ret,
      umaBig: uma.$1,
      umaSmall: uma.$2,
      eastOnly: _eastOnly,
      roundingMode: _rounding,
    );
  }

  /// 입력칸 점수(콤마 무시). 비었거나 숫자가 아니면 null.
  int? _score(int i) => int.tryParse(_scores[i].text.replaceAll(',', '').trim());

  /// 저장을 막는 문제들. 비었으면 저장할 수 있다.
  List<String> get _errors {
    final errs = <String>[];
    if (_picked.any((n) => n == null)) {
      errs.add('네 자리 모두 멤버를 고르세요');
    } else if (_picked.toSet().length < 4) {
      errs.add('같은 멤버가 두 자리에 있습니다');
    }
    final scores = [for (var i = 0; i < 4; i++) _score(i)];
    if (scores.any((s) => s == null)) {
      errs.add('네 자리 점수를 모두 넣으세요');
      return errs;
    }
    if (scores.any((s) => s! % 100 != 0)) errs.add('점수는 100점 단위여야 합니다');
    final sum = scores.fold<int>(0, (a, b) => a + b!);
    final expected = _start * 4;
    if (sum != expected) {
      errs.add('합계 $sum — 시작점×4 = $expected 이어야 합니다. 남은 공탁은 1위 점수에 더해 넣으세요');
    }
    return errs;
  }

  /// 검사를 통과했을 때 저장할 대국(미리보기에도 쓴다).
  Game _build(String id, DateTime playedAt) => Game.manual(
        id: id,
        playedAt: playedAt,
        settings: _settings,
        names: [for (final n in _picked) n!],
        scores: [for (var i = 0; i < 4; i++) _score(i)!],
        stars: List.of(_stars),
      );

  /// 고른 날짜 + 지금 시각(같은 날 여러 판이면 넣은 순서대로 정렬되게).
  DateTime get _playedAt {
    final now = DateTime.now();
    return DateTime(_date.year, _date.month, _date.day, now.hour, now.minute, now.second, now.millisecond);
  }

  Future<void> _save() async {
    if (_errors.isNotEmpty) return;
    final g = _build(DateTime.now().millisecondsSinceEpoch.toString(), _playedAt);
    try {
      final p = await SharedPreferences.getInstance();
      await p.setString(settingsKey, jsonEncode(_settings.toJson()));
    } catch (_) {}
    gameStore.addFinished(g);
    if (!mounted) return;
    Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => SettlementScreen(game: g)));
  }

  Future<void> _pickMember(int seat) async {
    final taken = {for (var i = 0; i < 4; i++) if (i != seat && _picked[i] != null) _picked[i]!};
    final choice = await showAdaptiveSheet<String>(
      context,
      builder: (ctx) => _MemberPickSheet(title: '${_seatLabels[seat]} 자리 멤버', taken: taken, current: _picked[seat]),
    );
    if (choice != null && mounted) setState(() => _picked[seat] = choice);
  }

  Future<void> _pickDate() async {
    final now = DateTime.now();
    final d = await showDatePicker(
      context: context,
      initialDate: _date.isAfter(now) ? now : _date,
      firstDate: DateTime(2000),
      lastDate: now,
    );
    if (d != null && mounted) setState(() => _date = d);
  }

  Widget _chips<T>(String label, List<(T, String)> options, T value, void Function(T) onSelected) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        children: [
          SizedBox(width: 72, child: Text(label)),
          Expanded(
            child: Wrap(
              spacing: 6,
              runSpacing: 4,
              children: [
                for (final (v, text) in options)
                  ChoiceChip(label: Text(text), selected: value == v, onSelected: (_) => onSelected(v)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _seatRow(BuildContext context, int i) {
    final scheme = Theme.of(context).colorScheme;
    final name = _picked[i];
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          SizedBox(width: 72, child: Text(_seatLabels[i], style: const TextStyle(fontWeight: FontWeight.w600))),
          Expanded(
            flex: 5,
            child: OutlinedButton.icon(
              key: ValueKey('entry-name-$i'),
              style: OutlinedButton.styleFrom(
                alignment: Alignment.centerLeft,
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
              ),
              icon: const Icon(Icons.person_outline),
              label: Text(
                name ?? '멤버 고르기',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(color: name == null ? scheme.outline : null),
              ),
              onPressed: () => _pickMember(i),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            flex: 4,
            child: TextField(
              key: ValueKey('entry-score-$i'),
              controller: _scores[i],
              keyboardType: const TextInputType.numberWithOptions(signed: true),
              inputFormatters: [FilteringTextInputFormatter.allow(RegExp('[-0-9,]'))],
              onChanged: (_) => setState(() {}),
              decoration: const InputDecoration(labelText: '최종 점수', border: OutlineInputBorder(), isDense: true),
            ),
          ),
        ],
      ),
    );
  }

  /// 자리 하나의 별 칸(−/+). 0 이상 정수.
  Widget _starsRow(BuildContext context, int i) {
    final n = _stars[i];
    return Padding(
      padding: const EdgeInsets.only(left: 72, bottom: 8),
      child: Row(
        children: [
          const Text('별'),
          IconButton(
            key: ValueKey('entry-stars-$i-minus'),
            visualDensity: VisualDensity.compact,
            icon: const Icon(Icons.remove_circle_outline),
            onPressed: n > 0 ? () => setState(() => _stars[i]--) : null,
          ),
          SizedBox(
            width: 28,
            child: Text(
              '$n',
              key: ValueKey('entry-stars-$i'),
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 16, fontFeatures: [FontFeature.tabularFigures()]),
            ),
          ),
          IconButton(
            key: ValueKey('entry-stars-$i-plus'),
            visualDensity: VisualDensity.compact,
            icon: const Icon(Icons.add_circle_outline),
            onPressed: n < _maxStars ? () => setState(() => _stars[i]++) : null,
          ),
        ],
      ),
    );
  }

  Widget _preview(BuildContext context) {
    final rows = _build('preview', _playedAt).settle();
    final theme = Theme.of(context);
    return Card(
      key: const ValueKey('entry-preview'),
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('정산 미리보기 (오카 ${_settings.oka})', style: theme.textTheme.titleSmall),
            const SizedBox(height: 6),
            for (final r in rows)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Row(
                  children: [
                    SizedBox(width: 40, child: Text('${r.rank}위', style: const TextStyle(fontWeight: FontWeight.w700))),
                    Expanded(
                      child: Text(
                        r.stars > 0 ? '${r.name} ★${r.stars}' : r.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    Text('${r.points}', style: const TextStyle(fontFeatures: [FontFeature.tabularFigures()])),
                    SizedBox(
                      width: 72,
                      child: Text(
                        _fmt(r.score),
                        textAlign: TextAlign.right,
                        style: TextStyle(
                          fontWeight: FontWeight.w700,
                          color: r.score < 0 ? theme.colorScheme.error : Colors.green.shade600,
                          fontFeatures: const [FontFeature.tabularFigures()],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final errors = _errors;
    final d = _date;
    final date = '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
    return kioskWrap(context, Scaffold(
      appBar: AppBar(title: const Text('대국 결과 입력')),
      body: kioskPage(context, Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('자리별 멤버와 최종 점수 (동 → 남 → 서 → 북)', style: kioskTextTheme(context).titleMedium),
                  const SizedBox(height: 4),
                  Text(
                    '동점이면 기동 자리에 가까운 사람이 위 순위입니다. 남은 공탁은 1위 점수에 더해 넣으세요. '
                    '별은 화료마다 하네만 1 · 배만 2 · 삼배만 3 · 역만 5(더블 10).',
                    style: kioskTextTheme(context).bodySmall,
                  ),
                  const SizedBox(height: 10),
                  for (var i = 0; i < 4; i++) ...[_seatRow(context, i), _starsRow(context, i)],
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      const SizedBox(width: 72, child: Text('대국 날짜')),
                      OutlinedButton.icon(
                        key: const ValueKey('entry-date'),
                        icon: const Icon(Icons.event),
                        label: Text(date),
                        onPressed: _pickDate,
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Text('규칙', style: kioskTextTheme(context).titleMedium),
                  const SizedBox(height: 8),
                  _chips<int>('시작점', const [(25000, '25000'), (30000, '30000')], _start, (v) => _rules(() => _start = v)),
                  _chips<int>('반환점', const [(25000, '25000'), (30000, '30000')], _ret, (v) => _rules(() => _ret = v)),
                  _chips<String>('우마', [for (final k in _umaPresets.keys) (k, k)], _uma, (v) => _rules(() => _uma = v)),
                  _chips<bool>('길이', const [(false, '반장전'), (true, '동풍전')], _eastOnly, (v) => _rules(() => _eastOnly = v)),
                  _chips<int>('반올림', const [(1, '오사육입'), (0, '소수 1자리')], _rounding, (v) => _rules(() => _rounding = v)),
                  if (errors.isEmpty) ...[
                    const SizedBox(height: 12),
                    _preview(context),
                  ],
                ],
              ),
            ),
          ),
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (errors.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Text(
                        errors.join('\n'),
                        key: const ValueKey('entry-error'),
                        style: TextStyle(fontSize: 13, color: Theme.of(context).colorScheme.error),
                      ),
                    ),
                  FilledButton(
                    key: const ValueKey('entry-save'),
                    style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 14)),
                    onPressed: errors.isEmpty ? _save : null,
                    child: const Text('저장하고 정산 보기'),
                  ),
                ],
              ),
            ),
          ),
        ],
      )),
    ));
  }
}

/// 자리 하나의 멤버 고르기. 다른 자리에서 이미 고른 멤버([taken])는 빼고 보여 준다.
class _MemberPickSheet extends StatelessWidget {
  final String title;
  final Set<String> taken;
  final String? current;
  const _MemberPickSheet({required this.title, required this.taken, required this.current});

  void _toManage(BuildContext context) {
    final nav = Navigator.of(context);
    nav.pop();
    nav.push(MaterialPageRoute(builder: (_) => const MemberManageScreen()));
  }

  @override
  Widget build(BuildContext context) {
    final all = memberStore.members;
    final list = [for (final n in all) if (!taken.contains(n)) n];
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(title, style: kioskTextTheme(context).titleMedium),
            const SizedBox(height: 8),
            if (all.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 16),
                child: Text('등록된 멤버가 없습니다. 멤버 관리로 가서 먼저 등록하세요.', key: ValueKey('entry-pick-empty')),
              )
            else if (list.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 16),
                child: Text('남은 멤버가 없습니다. 멤버 관리에서 더 등록하세요.'),
              )
            else
              Flexible(
                child: ListView(
                  shrinkWrap: true,
                  children: [
                    for (final n in list)
                      ListTile(
                        key: ValueKey('entry-pick-$n'),
                        leading: Icon(n == current ? Icons.check_circle : Icons.person_outline),
                        title: Text(n),
                        onTap: () => Navigator.of(context).pop(n),
                      ),
                  ],
                ),
              ),
            const SizedBox(height: 4),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                key: const ValueKey('entry-pick-manage'),
                icon: const Icon(Icons.manage_accounts),
                label: const Text('멤버 관리'),
                onPressed: () => _toManage(context),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

String _fmt(double v) {
  final s = v == v.roundToDouble() ? v.toInt().toString() : v.toStringAsFixed(1);
  return v > 0 ? '+$s' : s;
}
