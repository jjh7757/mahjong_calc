import 'package:flutter/material.dart';

import '../../engine/calculator.dart';
import '../../engine/score.dart' show payment;
import '../../game/game.dart';
import '../../game/game_store.dart';
import '../kiosk.dart' show showAdaptiveSheet;
import 'game_screen.dart' show notifyIfOver;

/// 기록한 화료의 확정 값. [roundLabel]·[honba] 는 기록 직전(국이 넘어가기 전) 값이다.
class WinOutcome {
  final int winner;
  final int? loser;
  final bool isTsumo;
  final String roundLabel;
  final int honba;

  /// 이 국에서 리치한 자리 전부(점수판 기록 + 자동 반영).
  final Set<int> riichiSeats;

  /// 이번 기록에서 자동으로 넣은 리치 자리.
  final Set<int> autoRiichiSeats;

  /// 동시 론(더블론·트리플론)의 다른 화료자.
  final List<int> otherWinners;
  const WinOutcome({
    required this.winner,
    required this.loser,
    required this.isTsumo,
    required this.roundLabel,
    required this.honba,
    this.riichiSeats = const {},
    this.autoRiichiSeats = const {},
    this.otherWinners = const [],
  });
}

/// 동시 론의 다른 화료자. [basePoints] 가 있으면(계산기·사진에서 계산한 손패) 판·부 입력을 건너뛴다.
class ExtraWin {
  final int winner;
  final int? basePoints;
  final String summary;

  /// 그 손패를 리치로 계산했는지. [basePoints] 가 없으면 모른다(사진 리치를 그대로 쓴다).
  final bool riichi;
  const ExtraWin({required this.winner, this.basePoints, this.summary = '', this.riichi = false});
}

/// 화료 입력: 화료자, 론/쯔모, 방총자, 판·부(또는 역만).
/// [basePoints] 가 주어지면(계산기에서 넘어온 경우) 판·부 입력을 건너뛴다.
/// [winner] 가 주어지면 화료자를 그 자리로 미리 고른다. 기록했으면 확정 값, 취소면 null.
///
/// 론이고 규칙이 동시 론을 인정하면([GameSettings.maxRonWinners]) "함께 론한 사람" 을 더할 수 있다.
/// [extraWins] 는 미리 채울 다른 화료자(거치 촬영에서 둘 이상 읽은 경우). 본장·공탁은 방총자에게서 가까운 화료자에게.
///
/// 리치봉 자동 반영: 점수판에 리치 기록이 없는데 [photoRiichiSeats](사진) 에 있는 자리와,
/// [winnerRiichi](계산한 손패가 리치) 면 화료자를, 칩으로 미리 켜 두고 기록할 때 1000점씩 공탁에 넣는다.
/// 칩을 끄면 넣지 않는다. 점수가 1000점 미만인 자리는 리치할 수 없으니 뺀다.
/// [paoBase] 는 파오(책임지불) 대상 역만(대삼원·대사희)의 기본점(`paoBasePoints`). 0 이 아니면 "파오한 사람" 칩이 뜬다.
/// 판·부를 직접 고를 때는 역만을 고르면 그 역만 전체를 파오 몫으로 본다.
Future<WinOutcome?> showWinSheet(BuildContext context, Game game,
    {int? basePoints,
    bool? isTsumo,
    String summary = '',
    int? winner,
    int? loser,
    Set<int> photoRiichiSeats = const {},
    bool winnerRiichi = false,
    List<ExtraWin> extraWins = const [],
    int paoBase = 0}) {
  // 폰은 바텀시트, 키오스크는 가운데 큰 패널.
  return showAdaptiveSheet<WinOutcome>(
    context,
    builder: (_) => _WinSheet(
        game: game,
        basePoints: basePoints,
        isTsumo: isTsumo,
        summary: summary,
        winner: winner,
        loser: loser,
        photoRiichiSeats: photoRiichiSeats,
        winnerRiichi: winnerRiichi,
        extraWins: extraWins,
        paoBase: paoBase),
  );
}

/// 시트 없이 바로 기록한다(거치 촬영 자동 반영). 화료자 한 명, 파오 없음. 자동 리치 후보는 모두 넣는다
/// (시트에서 칩을 하나도 안 끈 것과 같다). 기록 문구 끝에 "(자동)".
WinOutcome recordWinDirect({
  required int basePoints,
  required bool isTsumo,
  required String summary,
  required int winner,
  int? loser,
  Set<int> photoRiichiSeats = const {},
  bool winnerRiichi = false,
}) {
  final g = gameStore.current!;
  final auto = g.autoRiichiCandidates(photoRiichiSeats, winner: winner, winnerRiichi: winnerRiichi).toList()..sort();
  final outcome = WinOutcome(
    winner: winner,
    loser: isTsumo ? null : loser,
    isTsumo: isTsumo,
    roundLabel: g.roundLabel,
    honba: g.honba,
    riichiSeats: {...g.riichiSeats, ...auto},
    autoRiichiSeats: auto.toSet(),
  );
  final p = payment(
      basePoints, Situation(isTsumo: isTsumo, seatWind: winner == g.dealer ? Tiles.east : Tiles.south, honba: g.honba));
  gameStore.mutate((g) {
    for (final s in auto) {
      g.declareRiichi(s, fromPhoto: true);
    }
    g.win(winner: winner, loser: isTsumo ? null : loser, isTsumo: isTsumo, payment: p, summary: '$summary ${p.display} (자동)');
  });
  return outcome;
}

class _WinSheet extends StatefulWidget {
  final Game game;
  final int? basePoints;
  final bool? isTsumo;
  final String summary;
  final int? winner;
  final int? loser;
  final Set<int> photoRiichiSeats;
  final bool winnerRiichi;
  final List<ExtraWin> extraWins;
  final int paoBase;
  const _WinSheet(
      {required this.game,
      this.basePoints,
      this.isTsumo,
      required this.summary,
      this.winner,
      this.loser,
      this.photoRiichiSeats = const {},
      this.winnerRiichi = false,
      this.extraWins = const [],
      this.paoBase = 0});

  @override
  State<_WinSheet> createState() => _WinSheetState();
}

/// 시트 안에서 고치는 화료 한 건(판·부는 [basePoints] 가 없을 때만 쓴다).
class _Entry {
  int winner;
  final int? basePoints;
  final String summary;
  final bool? riichi;
  int han = 1;
  int fu = 30;
  int yakuman = 0; // 0 이면 일반
  _Entry(this.winner, {this.basePoints, this.summary = '', this.riichi});

  String get label => basePoints != null
      ? summary
      : yakuman > 0
          ? (yakuman >= 2 ? '$yakuman배 역만' : '역만')
          : '$han판 $fu부';

  Payment pay({required bool isDealer, required bool isTsumo, required int honba}) {
    if (basePoints != null) {
      return payment(
          basePoints!, Situation(isTsumo: isTsumo, seatWind: isDealer ? Tiles.east : Tiles.south, honba: honba));
    }
    if (yakuman > 0) {
      return yakumanPaymentFor(count: yakuman, isDealer: isDealer, isTsumo: isTsumo, honba: honba);
    }
    return paymentFor(han: han, fu: fu, isDealer: isDealer, isTsumo: isTsumo, honba: honba);
  }
}

class _WinSheetState extends State<_WinSheet> {
  late final _Entry main = _Entry(widget.winner ?? 0,
      basePoints: widget.basePoints, summary: widget.summary, riichi: widget.winnerRiichi);
  late final List<_Entry> extras = [
    for (final e in widget.extraWins)
      _Entry(e.winner, basePoints: e.basePoints, summary: e.summary, riichi: e.basePoints != null ? e.riichi : null),
  ];
  late int? loser = widget.loser;
  late bool isTsumo = widget.isTsumo ?? false;

  Game get g => widget.game;
  int get winner => main.winner;

  /// 동시 론으로 기록하는가.
  bool get _multi => !isTsumo && extras.isNotEmpty;
  Set<int> get _winners => {main.winner, if (_multi) ...extras.map((e) => e.winner)};

  /// 사용자가 끈 자동 리치 칩.
  final Set<int> _riichiOff = {};

  /// 파오(책임지불)한 자리. null 이면 없음.
  int? paoSeat;

  /// 파오 몫 기본점: 계산해 온 손패면 대상 역만 몫, 직접 고른 역만이면 그 역만 전체.
  int get _paoBase => widget.basePoints != null ? widget.paoBase : (main.yakuman > 0 ? 8000 * main.yakuman : 0);

  /// 파오 칩을 보여 줄 때: 동시 론이 아니고 파오 몫이 있을 때.
  bool get _paoAvailable => !_multi && _paoBase > 0;

  /// 실제로 적용되는 파오(화료자·방총자 자신이면 없음).
  int? get _effectivePao {
    final s = paoSeat;
    if (!_paoAvailable || s == null || s == winner || (!isTsumo && s == loser)) return null;
    return s;
  }

  Payment _paoPayment() => payment(
      _paoBase, Situation(isTsumo: isTsumo, seatWind: winner == g.dealer ? Tiles.east : Tiles.south, honba: 0));

  /// 자동으로 넣을 수 있는 리치 자리(점수판에 아직 없는 것만).
  Set<int> get _riichiCandidates => g.autoRiichiCandidates(widget.photoRiichiSeats,
      winner: winner,
      winnerRiichi: widget.winnerRiichi,
      otherWinners: {
        if (_multi)
          for (final e in extras)
            if (e.riichi != null) e.winner: e.riichi!,
      });

  List<int> get _autoRiichi =>
      (_riichiCandidates.difference(_riichiOff).toList()..sort());

  Payment _payment() => main.pay(isDealer: winner == g.dealer, isTsumo: isTsumo, honba: g.honba);

  /// 동시 론의 화료자별 지불액(본장 제외 — 본장은 [Game.multiRon] 이 가까운 쪽에 붙인다).
  Map<int, Payment> _multiPayments() => {
        for (final e in [main, ...extras]) e.winner: e.pay(isDealer: e.winner == g.dealer, isTsumo: false, honba: 0),
      };

  void _toast(String m) => ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  void _submit() {
    if (!isTsumo && loser == null) {
      _toast('방총자를 고르세요');
      return;
    }
    final auto = _autoRiichi;
    if (_multi && _winners.length != extras.length + 1) {
      _toast('함께 론한 사람이 겹칩니다');
      return;
    }
    if (_multi && _winners.contains(loser)) {
      _toast('방총자는 화료자가 아니어야 합니다');
      return;
    }
    final outcome = WinOutcome(
      winner: winner,
      loser: isTsumo ? null : loser,
      isTsumo: isTsumo,
      roundLabel: g.roundLabel,
      honba: g.honba,
      riichiSeats: {...g.riichiSeats, ...auto},
      autoRiichiSeats: auto.toSet(),
      otherWinners: _multi ? [for (final e in extras) e.winner] : const [],
    );
    if (_multi) {
      final pays = _multiPayments();
      gameStore.mutate((g) {
        for (final s in auto) {
          g.declareRiichi(s, fromPhoto: true);
        }
        g.multiRon(loser: loser!, payments: pays, summaries: {
          for (final e in [main, ...extras]) e.winner: e.label,
        });
      });
    } else {
      final p = _payment();
      final paoS = _effectivePao;
      final paoP = paoS == null ? null : _paoPayment();
      gameStore.mutate((g) {
        // 리치봉을 먼저 공탁에 넣고 화료한다(공탁은 화료자가 가져간다).
        for (final s in auto) {
          g.declareRiichi(s, fromPhoto: true);
        }
        g.win(
          winner: winner,
          loser: isTsumo ? null : loser,
          isTsumo: isTsumo,
          payment: p,
          summary: '${main.label} ${p.display}',
          paoSeat: paoS,
          pao: paoP,
        );
      });
    }
    notifyIfOver(context);
    Navigator.of(context).pop(outcome);
  }

  /// 판·부(또는 역만) 고르기.
  Widget _hanFu(_Entry e) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const SizedBox(width: 40, child: Text('판', style: TextStyle(fontSize: 12))),
            Expanded(
              child: Wrap(
                spacing: 4,
                children: [
                  for (final h in [1, 2, 3, 4, 5, 6, 8, 11])
                    ChoiceChip(
                      label: Text('$h'),
                      selected: e.yakuman == 0 && e.han == h,
                      onSelected: (_) => setState(() {
                        e.han = h;
                        e.yakuman = 0;
                      }),
                      visualDensity: VisualDensity.compact,
                    ),
                  ChoiceChip(
                    label: const Text('역만'),
                    selected: e.yakuman == 1,
                    onSelected: (_) => setState(() => e.yakuman = 1),
                    visualDensity: VisualDensity.compact,
                  ),
                  ChoiceChip(
                    label: const Text('더블'),
                    selected: e.yakuman == 2,
                    onSelected: (_) => setState(() => e.yakuman = 2),
                    visualDensity: VisualDensity.compact,
                  ),
                ],
              ),
            ),
          ],
        ),
        if (e.yakuman == 0 && e.han <= 4) ...[
          const SizedBox(height: 6),
          Row(
            children: [
              const SizedBox(width: 40, child: Text('부', style: TextStyle(fontSize: 12))),
              Expanded(
                child: Wrap(
                  spacing: 4,
                  children: [
                    for (final f in [20, 25, 30, 40, 50, 60, 70, 80, 90, 100, 110])
                      ChoiceChip(
                        label: Text('$f'),
                        selected: e.fu == f,
                        onSelected: (_) => setState(() => e.fu = f),
                        visualDensity: VisualDensity.compact,
                      ),
                  ],
                ),
              ),
            ],
          ),
        ],
      ],
    );
  }

  /// 함께 론한 사람 한 명: 자리 고르기 + 판·부(계산해 온 손패면 요약).
  Widget _extraCard(int i, ColorScheme scheme) {
    final e = extras[i];
    final taken = {main.winner, loser, for (var j = 0; j < extras.length; j++) if (j != i) extras[j].winner};
    return Card(
      key: ValueKey('extra-win-$i'),
      margin: const EdgeInsets.only(top: 8),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(10, 6, 4, 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Text('함께 론', style: TextStyle(fontSize: 12)),
                const Spacer(),
                IconButton(
                  tooltip: '빼기',
                  icon: const Icon(Icons.close, size: 18),
                  onPressed: () => setState(() => extras.removeAt(i)),
                ),
              ],
            ),
            Wrap(
              spacing: 6,
              children: [
                for (var s = 0; s < 4; s++)
                  if (s == e.winner || !taken.contains(s))
                    ChoiceChip(
                      label: Text('${Tiles.name(g.seatWindOf(s))} ${g.names[s]}'),
                      selected: e.winner == s,
                      onSelected: (_) => setState(() => e.winner = s),
                    ),
              ],
            ),
            const SizedBox(height: 6),
            if (e.basePoints == null) _hanFu(e) else Text(e.summary, style: TextStyle(color: scheme.outline)),
          ],
        ),
      ),
    );
  }

  void _addExtra() {
    final taken = {main.winner, loser, ...extras.map((e) => e.winner)};
    final free = [for (var s = 0; s < 4; s++) if (!taken.contains(s)) s];
    if (free.isEmpty) {
      _toast(loser == null ? '화료자를 먼저 고르세요' : '남은 자리가 없습니다');
      return;
    }
    setState(() => extras.add(_Entry(free.first)));
  }

  String _paymentText() {
    final sticks = g.riichiSticks + _autoRiichi.length;
    if (!_multi) {
      final p = _payment();
      final paoS = _effectivePao;
      final paoText = paoS == null
          ? ''
          : isTsumo
              ? '  · 파오 ${g.names[paoS]} 가 ${_paoPayment().total} 전액'
              : '  · 파오 ${g.names[paoS]} 가 ${_paoPayment().ron ~/ 2} (절반)';
      return '지불: ${p.display}'
          '${g.honba > 0 ? '  (본장 ${g.honba} 포함)' : ''}'
          '${sticks > 0 ? '  +공탁 ${sticks * 1000}' : ''}'
          '$paoText';
    }
    final pays = _multiPayments();
    final order = loser == null ? pays.keys.toList() : Game.ronOrder(loser!, pays.keys);
    final head = loser == null ? null : order.first;
    return [
      for (final w in order)
        '${g.names[w]} ${pays[w]!.ron + (w == head ? g.honba * 300 : 0)}'
            '${w == head && g.honba > 0 ? '(본장 포함)' : ''}'
            '${w == head && sticks > 0 ? ' +공탁 ${sticks * 1000}' : ''}',
    ].join('  /  ');
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final canAddRon = !isTsumo && 1 + extras.length < g.settings.maxRonWinners;
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(16, 12, 16, 16 + MediaQuery.of(context).viewInsets.bottom),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('화료 — ${g.roundLabel}', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 10),
              const Text('화료자', style: TextStyle(fontSize: 12)),
              Wrap(
                spacing: 6,
                children: [
                  for (var s = 0; s < 4; s++)
                    ChoiceChip(
                      label: Text('${Tiles.name(g.seatWindOf(s))} ${g.names[s]}'),
                      selected: winner == s,
                      onSelected: (_) => setState(() {
                        main.winner = s;
                        if (loser == s) loser = null;
                      }),
                    ),
                ],
              ),
              const SizedBox(height: 8),
              SegmentedButton<bool>(
                showSelectedIcon: false,
                segments: const [
                  ButtonSegment(value: false, label: Text('론')),
                  ButtonSegment(value: true, label: Text('쯔모')),
                ],
                selected: {isTsumo},
                onSelectionChanged: (v) => setState(() => isTsumo = v.first),
              ),
              if (!isTsumo) ...[
                const SizedBox(height: 8),
                const Text('방총자', style: TextStyle(fontSize: 12)),
                Wrap(
                  spacing: 6,
                  children: [
                    for (var s = 0; s < 4; s++)
                      if (!_winners.contains(s))
                        ChoiceChip(
                          label: Text(g.names[s]),
                          selected: loser == s,
                          onSelected: (_) => setState(() => loser = s),
                        ),
                  ],
                ),
              ],
              if (widget.basePoints == null) ...[
                const SizedBox(height: 10),
                _hanFu(main),
              ] else ...[
                const SizedBox(height: 8),
                Text(widget.summary, style: TextStyle(color: scheme.outline)),
              ],
              if (!isTsumo) ...[
                for (var i = 0; i < extras.length; i++) _extraCard(i, scheme),
                if (canAddRon)
                  Align(
                    alignment: Alignment.centerLeft,
                    child: TextButton.icon(
                      key: const ValueKey('add-extra-win'),
                      icon: const Icon(Icons.group_add_outlined, size: 18),
                      label: Text(extras.isEmpty ? '함께 론한 사람 (더블론)' : '함께 론한 사람 추가 (트리플론)'),
                      onPressed: _addExtra,
                    ),
                  ),
              ],
              if (_paoAvailable) ...[
                const SizedBox(height: 10),
                const Text('파오(책임지불) — 대삼원·대사희를 확정시킨 울기를 준 사람', style: TextStyle(fontSize: 12)),
                Wrap(
                  spacing: 6,
                  children: [
                    ChoiceChip(
                      key: const ValueKey('pao-none'),
                      label: const Text('없음'),
                      selected: paoSeat == null,
                      onSelected: (_) => setState(() => paoSeat = null),
                    ),
                    for (var s = 0; s < 4; s++)
                      if (s != winner)
                        ChoiceChip(
                          key: ValueKey('pao-$s'),
                          label: Text(g.names[s]),
                          selected: paoSeat == s,
                          onSelected: (_) => setState(() => paoSeat = s),
                        ),
                  ],
                ),
                if (paoSeat != null && _effectivePao == null)
                  const Padding(
                    padding: EdgeInsets.only(top: 2),
                    child: Text('방총자 본인이 파오면 평소대로 전액입니다', style: TextStyle(fontSize: 11)),
                  ),
              ],
              if (_riichiCandidates.isNotEmpty) ...[
                const SizedBox(height: 10),
                const Text('리치봉 자동 반영 (점수판에 없던 리치, 1000점씩 공탁)', style: TextStyle(fontSize: 12)),
                Wrap(
                  spacing: 6,
                  children: [
                    for (final s in (_riichiCandidates.toList()..sort()))
                      FilterChip(
                        key: ValueKey('auto-riichi-$s'),
                        label: Text('${g.names[s]} 리치'),
                        selected: !_riichiOff.contains(s),
                        onSelected: (on) => setState(() => on ? _riichiOff.remove(s) : _riichiOff.add(s)),
                      ),
                  ],
                ),
              ],
              const SizedBox(height: 12),
              Text(_paymentText(), style: const TextStyle(fontWeight: FontWeight.w600)),
              const SizedBox(height: 12),
              FilledButton(onPressed: _submit, child: Text(_multi ? '${extras.length + 1}명 론 기록' : '기록')),
            ],
          ),
        ),
      ),
    );
  }
}
