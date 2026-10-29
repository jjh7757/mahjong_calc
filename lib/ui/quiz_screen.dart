import 'dart:math';

import 'package:flutter/material.dart';
import 'kiosk.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../engine/calculator.dart';
import '../quiz/quiz_generator.dart';
import 'tile_view.dart';

/// 점수 계산 연습: 손패를 보고 판 → 부 → 점수를 차례로 맞힌다.
class QuizScreen extends StatefulWidget {
  final RuleSet rules;
  const QuizScreen({super.key, this.rules = RuleSet.standard});

  @override
  State<QuizScreen> createState() => _QuizScreenState();
}

enum _Stage { han, fu, score, review }

class _QuizScreenState extends State<QuizScreen> {
  late final QuizGenerator _gen = QuizGenerator(rules: widget.rules);
  final _rng = Random();
  late QuizProblem problem;
  late List<String> choices;
  _Stage stage = _Stage.han;
  int? pickedHan;
  int? pickedFu;
  String? pickedScore;
  int total = 0;
  int correct = 0;
  int streak = 0;

  static const fus = [20, 25, 30, 40, 50, 60, 70, 80, 90, 100, 110];

  @override
  void initState() {
    super.initState();
    _next();
    _loadStats();
  }

  Future<void> _loadStats() async {
    final p = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() {
      total = p.getInt('quiz.total') ?? 0;
      correct = p.getInt('quiz.correct') ?? 0;
    });
  }

  Future<void> _saveStats() async {
    final p = await SharedPreferences.getInstance();
    await p.setInt('quiz.total', total);
    await p.setInt('quiz.correct', correct);
  }

  void _next() {
    problem = _gen.next();
    choices = scoreChoices(problem, _rng, rules: widget.rules);
    stage = _Stage.han;
    pickedHan = null;
    pickedFu = null;
    pickedScore = null;
  }

  bool get hanOk => pickedHan == problem.answer.han;
  bool get fuSkipped => problem.answer.han >= 5;
  bool get fuOk => fuSkipped || pickedFu == problem.answer.fu.total;
  bool get scoreOk => pickedScore == problem.answer.payment.display;

  void _pickHan(int h) => setState(() {
        pickedHan = h;
        stage = fuSkipped ? _Stage.score : _Stage.fu;
      });

  void _pickFu(int f) => setState(() {
        pickedFu = f;
        stage = _Stage.score;
      });

  void _pickScore(String s) {
    setState(() {
      pickedScore = s;
      stage = _Stage.review;
      total++;
      if (hanOk && fuOk && scoreOk) {
        correct++;
        streak++;
      } else {
        streak = 0;
      }
    });
    _saveStats();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final a = problem.answer;
    return kioskWrap(context, Scaffold(
      appBar: AppBar(
        title: const Text('점수 계산 연습'),
        actions: [
          Center(
            child: Padding(
              padding: const EdgeInsets.only(right: 16),
              child: Text('$correct / $total  연속 $streak', style: const TextStyle(fontSize: 13)),
            ),
          ),
        ],
      ),
      body: ListView(
        padding: EdgeInsets.fromLTRB(12, 12, 12, 12 + MediaQuery.paddingOf(context).bottom),
        children: [
          _HandCard(problem: problem),
          const SizedBox(height: 12),
          if (stage == _Stage.han) _chips('몇 판?', [for (var h = 1; h <= 13; h++) h], (v) => _pickHan(v as int)),
          if (stage == _Stage.fu) _chips('몇 부?', fus, (v) => _pickFu(v as int)),
          if (stage == _Stage.score)
            _chips(problem.situation.isTsumo ? '점수? (자 / 친 또는 올)' : '점수? (방총자 지불)', choices,
                (v) => _pickScore(v as String)),
          if (stage == _Stage.review) ...[
            Card(
              color: (hanOk && fuOk && scoreOk) ? scheme.primaryContainer : scheme.errorContainer,
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text((hanOk && fuOk && scoreOk) ? '정답' : '오답',
                        style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: 6),
                    _line('판', '$pickedHan', '${a.han}', hanOk),
                    if (!fuSkipped) _line('부', '$pickedFu', '${a.fu.total}', fuOk),
                    _line('점수', pickedScore ?? '', a.payment.display, scoreOk),
                    if (fuSkipped)
                      Text('5판 이상이라 부수는 묻지 않았습니다 (${a.limit.label})',
                          style: TextStyle(fontSize: 12, color: scheme.outline)),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 8),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('역 ${a.han}판', style: const TextStyle(fontWeight: FontWeight.w600)),
                    for (final y in a.yaku) Text('${y.yaku.label} ${y.han}판'),
                    const SizedBox(height: 8),
                    Text('부수 ${a.fu.total}부', style: const TextStyle(fontWeight: FontWeight.w600)),
                    for (final f in a.fu.items) Text('${f.label} ${f.fu}'),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            FilledButton(onPressed: () => setState(_next), child: const Text('다음 문제')),
          ],
        ],
      ),
    ));
  }

  Widget _line(String label, String picked, String answer, bool ok) {
    return Row(
      children: [
        Icon(ok ? Icons.check_circle : Icons.cancel, size: 18,
            color: ok ? Colors.green : Theme.of(context).colorScheme.error),
        const SizedBox(width: 6),
        Text('$label: $picked'),
        if (!ok) Text('  → $answer', style: const TextStyle(fontWeight: FontWeight.w600)),
      ],
    );
  }

  Widget _chips(String title, List<Object> values, void Function(Object) onPick) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final v in values)
                  ActionChip(label: Text('$v'), onPressed: () => onPick(v)),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _HandCard extends StatelessWidget {
  final QuizProblem problem;
  const _HandCard({required this.problem});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final s = problem.situation;
    final h = problem.hand;
    // 화료패 한 장은 따로 보여준다
    final rest = [...h.closedTiles];
    rest.remove(h.winTile);
    final parts = <String>[
      '자풍 ${Tiles.name(s.seatWind)}',
      '장풍 ${Tiles.name(s.roundWind)}',
      s.isTsumo ? '쯔모' : '론',
      if (s.riichi) '리치',
      if (s.ippatsu) '일발',
      if (s.doraIndicators.isNotEmpty) '도라 표시 ${s.doraIndicators.map(Tiles.name).join('·')}',
      if (h.redCount > 0) '적도라 ${h.redCount}',
      if (s.honba > 0) '${s.honba}본장',
    ];
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(parts.join(' · '), style: const TextStyle(fontSize: 13)),
            const SizedBox(height: 10),
            Wrap(
              spacing: 3,
              runSpacing: 6,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                for (final t in rest) TileView(t, width: 30),
                const SizedBox(width: 10),
                TileView(h.winTile, width: 30, highlighted: true),
              ],
            ),
            if (h.melds.isNotEmpty) ...[
              const SizedBox(height: 8),
              Wrap(
                spacing: 10,
                children: [
                  for (final m in h.melds)
                    Container(
                      padding: const EdgeInsets.all(3),
                      decoration: BoxDecoration(
                        border: Border.all(color: scheme.outlineVariant),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: TileRow(m.tiles, width: 24, open: m.isOpen),
                    ),
                ],
              ),
            ],
            const SizedBox(height: 6),
            Text('초록 테두리가 화료패${h.melds.isNotEmpty ? ', 아래가 부른 묶음' : ''}',
                style: TextStyle(fontSize: 11, color: scheme.outline)),
          ],
        ),
      ),
    );
  }
}
