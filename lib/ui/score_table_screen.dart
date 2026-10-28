import 'package:flutter/material.dart';
import 'kiosk.dart';

import '../engine/calculator.dart';
import '../engine/score.dart' show basePoints, payment;

/// 판 × 부 점수표. 자/친, 론/쯔모를 전환해서 본다.
class ScoreTableScreen extends StatefulWidget {
  final RuleSet rules;
  const ScoreTableScreen({super.key, this.rules = RuleSet.standard});

  @override
  State<ScoreTableScreen> createState() => _ScoreTableScreenState();
}

class _ScoreTableScreenState extends State<ScoreTableScreen> {
  bool dealer = false;
  bool tsumo = false;

  static const fus = [20, 25, 30, 40, 50, 60, 70, 80, 90, 100, 110];

  Situation get _sit => Situation(isTsumo: tsumo, seatWind: dealer ? Tiles.east : Tiles.south);

  /// 실제로 나올 수 없는 조합은 null.
  String? _cell(int han, int fu) {
    if (fu == 20 && (!tsumo || han == 1)) return null; // 20부는 핑후 쯔모(2판 이상)뿐
    if (fu == 25 && (han == 1 || (tsumo && han == 2))) return null; // 치또이 2판, 쯔모면 3판부터
    final bp = basePoints(han, fu, widget.rules);
    final p = payment(bp.base, _sit);
    return bp.limit == Limit.none ? p.display : '${p.display}\n${bp.limit.label}';
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final limits = [
      ('만관 (5판)', basePoints(5, 30, widget.rules)),
      ('하네만 (6~7판)', basePoints(6, 30, widget.rules)),
      ('배만 (8~10판)', basePoints(8, 30, widget.rules)),
      ('삼배만 (11~12판)', basePoints(11, 30, widget.rules)),
      ('역만', basePoints(13, 30, widget.rules)),
    ];
    return kioskWrap(context, Scaffold(
      appBar: AppBar(title: const Text('점수표')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
            child: Row(
              children: [
                SegmentedButton<bool>(
                  showSelectedIcon: false,
                  segments: const [
                    ButtonSegment(value: false, label: Text('자')),
                    ButtonSegment(value: true, label: Text('친')),
                  ],
                  selected: {dealer},
                  onSelectionChanged: (s) => setState(() => dealer = s.first),
                ),
                const SizedBox(width: 12),
                SegmentedButton<bool>(
                  showSelectedIcon: false,
                  segments: const [
                    ButtonSegment(value: false, label: Text('론')),
                    ButtonSegment(value: true, label: Text('쯔모')),
                  ],
                  selected: {tsumo},
                  onSelectionChanged: (s) => setState(() => tsumo = s.first),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Text(
              tsumo
                  ? (dealer ? '쯔모: 세 명이 각각 내는 금액' : '쯔모: 자 / 친 이 내는 금액')
                  : '론: 방총자가 내는 금액',
              style: TextStyle(fontSize: 12, color: scheme.outline),
            ),
          ),
          Expanded(
            child: SingleChildScrollView(
              child: SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.all(12),
                child: DataTable(
                  columnSpacing: 14,
                  headingRowHeight: 36,
                  dataRowMinHeight: 44,
                  dataRowMaxHeight: 56,
                  columns: [
                    const DataColumn(label: Text('판\\부')),
                    for (final fu in fus) DataColumn(label: Text('$fu')),
                  ],
                  rows: [
                    for (var han = 1; han <= 4; han++)
                      DataRow(cells: [
                        DataCell(Text('$han판', style: const TextStyle(fontWeight: FontWeight.w600))),
                        for (final fu in fus)
                          DataCell(Text(
                            _cell(han, fu) ?? '-',
                            style: TextStyle(
                              fontSize: 12,
                              color: _cell(han, fu) == null ? scheme.outlineVariant : null,
                            ),
                          )),
                      ]),
                  ],
                ),
              ),
            ),
          ),
          Card(
            margin: const EdgeInsets.fromLTRB(12, 0, 12, 12),
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                children: [
                  for (final (label, bp) in limits)
                    Row(
                      children: [
                        Expanded(child: Text(label)),
                        Text(payment(bp.base, _sit).display,
                            style: const TextStyle(fontWeight: FontWeight.w600)),
                      ],
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    ));
  }
}
