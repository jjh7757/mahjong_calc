import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../engine/calculator.dart';
import '../engine/score.dart' show payment;
import '../game/game.dart';
import '../game/game_store.dart';
import '../services/announcer.dart';
import 'game/win_sheet.dart';
import 'kiosk.dart';
import 'score_cross.dart';
import 'tile_view.dart';

part 'result_kiosk.dart';

/// 동시 론(더블론·트리플론)의 다른 화료자: 대국 자리, 계산 결과, 그 손패를 리치로 계산했는지.
/// [hand]·[situation] 이 있으면 결과 화면에서 그 사람 차례에 손패를 그리고 상황 칩으로 다시 계산한다.
class OtherWin {
  final int seat;
  final ScoreResult result;
  final bool riichi;
  final Hand? hand;
  final Situation? situation;
  const OtherWin(this.seat, this.result, {this.riichi = false, this.hand, this.situation});
}

/// 계산 결과 화면. 작혼처럼 역이 한 줄씩 나오고, 끝나면 네 자리 점수 이동을 보여 준다.
/// 태블릿 가로(키오스크)면 화료 연출 화면([_KioskResult])으로 그린다.
class ResultScreen extends StatefulWidget {
  final ScoreResult result;

  /// 계산한 손패·상황. 있으면 키오스크 화면에 손패(화료패 분리)·도라 표시패를 그린다.
  final Hand? hand;
  final Situation? situation;
  final bool isTsumo;

  /// 화료자의 자풍. 대국 기록이 없을 때 점수 이동판의 자리를 정하는 데 쓴다.
  final int seatWind;

  /// 대국에서 고른 손패 주인(자리). "대국에 반영"의 화료자로 미리 채운다.
  final int? gameSeat;

  /// 대국에 기록을 마쳤을 때 부른다(입력 화면이 손패를 비우는 데 쓴다).
  final VoidCallback? onRecorded;

  /// 대국에 기록한 확정 값. [onRecorded] 보다 먼저 부른다(손패를 비우기 전에 정답을 남기는 데 쓴다).
  final void Function(WinOutcome outcome)? onWinRecorded;

  /// 상황 칩으로 고친 뒤 다시 계산할 때마다(화료자 손패). 입력 화면 값(기록·label.json)을 계산과 맞추는 데 쓴다.
  final ValueChanged<Situation>? onSituationChanged;

  /// 거치 촬영에서 추정한 방총자. "대국에 반영" 시트에 미리 채운다.
  final int? loser;

  /// 거치 촬영 판독에서 확인이 필요한 것들. 요약 카드 아래에 보여준다.
  final List<String> flags;

  /// 거치 촬영 결과일 때 "판독 수정"(입력 화면으로 돌아가 고치기).
  final VoidCallback? onFix;

  /// 사진에서 리치가 보인 자리. "대국에 반영" 때 점수판에 없으면 리치봉을 자동으로 넣는다.
  final Set<int> photoRiichiSeats;

  /// 이 손패를 리치로 계산했는지. 점수판에 화료자 리치가 없으면 자동으로 넣는다.
  final bool winnerRiichi;

  /// 같은 패로 함께 론한 다른 화료자(거치 촬영에서 둘 이상 읽은 경우). 대국 기록이 있을 때만 쓴다.
  final List<OtherWin> otherWins;

  /// 거치 촬영 판독이 확실할 때 자동 반영: 연출이 끝나고 이 시간이 지나면 시트 없이 대국에 기록하고 닫는다.
  /// 그 전에 "취소" 하거나 점수 이동판에서 자리를 바꾸면 평소처럼 "대국에 반영" 을 직접 누른다. null 이면 끔.
  final Duration? autoRecordAfter;

  /// 자동 반영 전에 사람이 봐야 할 것(`autoRecordCautions`). 카운트다운 줄에 크게 띄우고 기록 문구에 남긴다.
  final List<String> autoCautions;

  /// 상황 칩으로 다시 계산할 때 쓰는 룰(입력 화면·거치 촬영의 룰 설정).
  final RuleSet rules;
  const ResultScreen({
    super.key,
    required this.result,
    this.hand,
    this.situation,
    this.isTsumo = false,
    this.seatWind = Tiles.east,
    this.gameSeat,
    this.onRecorded,
    this.onWinRecorded,
    this.onSituationChanged,
    this.loser,
    this.flags = const [],
    this.onFix,
    this.photoRiichiSeats = const {},
    this.winnerRiichi = false,
    this.otherWins = const [],
    this.autoRecordAfter,
    this.autoCautions = const [],
    this.rules = RuleSet.standard,
  });

  @override
  State<ResultScreen> createState() => _ResultScreenState();
}

class _ResultScreenState extends State<ResultScreen> with SingleTickerProviderStateMixin {
  static const _perYaku = 280; // ms
  static const _tail = 900; // 합계·점수가 나오는 시간

  late final AnimationController _reveal;

  /// 점수 이동판에서 고른 화료자·방총자(대국 기록이 있을 때 화료자도 바꿀 수 있다).
  late int? _winner = widget.gameSeat;
  late int? _loser = widget.loser;

  /// 상황 칩(리치·더블 리치·일발·해저/하저·영상개화/창깡)으로 고친 상황과 그 결과. 처음엔 넘어온 것 그대로.
  late Situation? _sit = widget.situation;

  /// 한 번 기록했으면 다시 기록하지 않는다(카운트다운 끝과 "지금 반영" 터치가 겹치면 두 번 기록되고 홈 화면까지 pop 됐다,
  /// 2026-10-30 점검).
  bool _recorded = false;
  late ScoreResult _result = widget.result;

  /// 동시 론이면 화료자마다 결과를 차례로 보여 준다(2026-10-29, 사용자: 더블론 결과 화면 연속 2개).
  /// 0 은 대표 화료자, k 는 [_pages] 의 k-1 번째. 점수 이동판·기록은 어느 쪽에서든 모두를 합쳐 계산한다.
  int _page = 0;

  /// 차례로 보여 줄 함께 론한 사람(계산이 된 사람만).
  List<OtherWin> get _pages => [for (final o in _others) if (o.result.isValid) o];

  /// 지금 보이는 함께 론한 사람. 대표 화료자 차례면 null.
  OtherWin? get _shown {
    final p = _pages;
    return _page >= 1 && _page <= p.length ? p[_page - 1] : null;
  }

  /// 지금 보이는 사람의 결과·손패·상황·자리.
  ScoreResult get result => _shown?.result ?? _result;
  Hand? get _hand => _shown == null ? widget.hand : _shown!.hand;
  Situation? get _shownSit => _shown == null ? _sit : _shown!.situation;
  int? get _shownSeat => _shown?.seat ?? _winner;

  /// 다음 차례 화료자(없으면 null, 그러면 이 화면에서 기록한다).
  OtherWin? get _nextWin {
    final p = _pages;
    return _page < p.length ? p[_page] : null;
  }

  /// "더블론 1/2" 같은 차례 표시. 동시 론이 아니면 null.
  String? get _pageLabel {
    final p = _pages;
    if (p.isEmpty) return null;
    final page = _page.clamp(0, p.length);
    return '${_others.length >= 2 ? '트리플론' : '더블론'} ${page + 1}/${p.length + 1}';
  }

  /// [page] 차례로 넘기고 그 사람의 연출(역·음성)을 처음부터 한다.
  Future<void> _goPage(int page) async {
    _playGen++;
    setState(() {
      _page = page;
      _skipped = false;
      _gradeSaid = false;
    });
    _reveal.duration = Duration(milliseconds: _perYaku * result.yaku.length + _tail);
    _reveal.value = 0;
    await Announcer.stop();
    if (mounted) _play();
  }

  /// 이 손패를 리치로 계산했는지(칩으로 바꿨으면 그것). "대국에 반영" 의 자동 리치봉에 쓴다.
  bool get _winnerRiichi => _sit == null ? widget.winnerRiichi : (_sit!.riichi || _sit!.doubleRiichi);
  Game? get _game => gameStore.current;

  /// 칩으로 상황을 고쳐 바로 다시 계산한다(2026-10-29, 사용자: 더블 리치·일발을 "판독 수정" 없이 결과 화면에서).
  /// 연출·음성은 건너뛰고, 10초 자동 반영은 멈춘다(사용자가 손댄 결과는 직접 반영).
  void _applySituation(Situation s, String what) {
    final hand = _hand;
    if (hand == null) return;
    _cancelAuto();
    _skipped = true;
    Announcer.stop();
    final shown = _shown;
    setState(() {
      final r = calculate(hand, s, rules: widget.rules);
      if (shown == null) {
        _sit = s;
        _result = r;
      } else {
        // 함께 론한 사람 차례면 그 사람 것만 고친다(기록·점수 이동판에도 반영).
        final i = _otherWins.indexOf(shown);
        _otherWins[i] = OtherWin(shown.seat, r, riichi: s.riichi || s.doubleRiichi, hand: hand, situation: s);
      }
    });
    if (shown == null) widget.onSituationChanged?.call(s);
    _reveal.value = 1;
    ScaffoldMessenger.maybeOf(context)
      ?..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text('$what(으)로 다시 계산했습니다'), duration: const Duration(seconds: 3)));
  }

  /// 상황 칩 줄. 손패·상황을 모르면(옛 호출) 없음. 울었으면 리치 칩은 뺀다.
  Widget? _situationChips({required bool kiosk}) {
    final hand = _hand;
    final s = _shownSit;
    if (hand == null || s == null) return null;
    const gold = Color(0xFFF2C14E);
    Widget chip(String key, String label, bool on, Situation Function(bool next) change) {
      final next = !on;
      final child = Text(
        label,
        style: TextStyle(
          fontSize: kiosk ? 16 : 13,
          fontWeight: FontWeight.w700,
          color: kiosk ? (on ? const Color(0xFF2A1F08) : Colors.white) : null,
        ),
      );
      if (!kiosk) {
        return FilterChip(
          key: ValueKey('result-chip-$key'),
          label: child,
          selected: on,
          onSelected: (_) => _applySituation(change(next), label),
        );
      }
      return InkWell(
        key: ValueKey('result-chip-$key'),
        borderRadius: BorderRadius.circular(20),
        onTap: () => _applySituation(change(next), label),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            color: on ? gold : const Color(0xE61B2640),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: on ? gold : const Color(0xFF5B6F99)),
          ),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            if (on)
              const Padding(
                padding: EdgeInsets.only(right: 6),
                child: Icon(Icons.check, size: 16, color: Color(0xFF2A1F08)),
              ),
            child,
          ]),
        ),
      );
    }

    final chips = <Widget>[
      if (hand.isClosed) ...[
        chip('riichi', '리치', s.riichi, (v) => s.copyWith(riichi: v, doubleRiichi: false, ippatsu: v && s.ippatsu)),
        chip('double-riichi', '더블 리치', s.doubleRiichi,
            (v) => s.copyWith(doubleRiichi: v, riichi: false, ippatsu: v && s.ippatsu)),
        chip('ippatsu', '일발', s.ippatsu, (v) => s.copyWith(ippatsu: v, riichi: v && !s.doubleRiichi ? true : s.riichi)),
      ],
      chip('last-tile', s.isTsumo ? '해저로월' : '하저로어', s.lastTile, (v) => s.copyWith(lastTile: v)),
      if (s.isTsumo)
        chip('rinshan', '영상개화', s.rinshan, (v) => s.copyWith(rinshan: v))
      else
        chip('chankan', '창깡', s.chankan, (v) => s.copyWith(chankan: v)),
    ];
    if (!kiosk) return Wrap(spacing: 6, runSpacing: 4, children: chips);
    return Container(
      key: const ValueKey('result-chips'),
      padding: const EdgeInsets.fromLTRB(14, 8, 8, 8),
      decoration: BoxDecoration(
        color: const Color(0xCC0E1526),
        borderRadius: BorderRadius.circular(28),
        border: Border.all(color: const Color(0xFF3B4C73)),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        const Padding(
          padding: EdgeInsets.only(right: 12),
          child: Text('상황 고치기', style: TextStyle(color: Colors.white70, fontSize: 14)),
        ),
        for (final c in chips) Padding(padding: const EdgeInsets.only(right: 8), child: c),
      ]),
    );
  }

  /// "한 명만 론" 을 눌렀으면 함께 론한 사람을 빼고 대표 화료자만 기록한다(더블론 자동 판정을 되돌림).
  bool _singleRon = false;

  /// 함께 론한 사람. 그 사람 차례에 상황 칩으로 고치면 바뀐다.
  late final List<OtherWin> _otherWins = List.of(widget.otherWins);

  /// 함께 론한 사람(대국 기록 중이고 론일 때만, 화료자·방총자와 겹치지 않는 것).
  List<OtherWin> get _others => _game == null || widget.isTsumo || _singleRon
      ? const []
      : [for (final o in _otherWins) if (o.seat != _winner && o.seat != _loser) o];

  /// 대표 화료자 차례가 아니면 "이전", 다음 화료자가 있으면 "다음: 이름" 버튼. [style] 은 키오스크용.
  List<Widget> _pageButtons({ButtonStyle? style, ButtonStyle? nextStyle}) {
    final next = _nextWin;
    return [
      if (_page > 0)
        OutlinedButton.icon(
          key: const ValueKey('result-prev-win'),
          style: style,
          icon: const Icon(Icons.chevron_left),
          label: const Text('이전'),
          onPressed: () => _goPage(_page - 1),
        ),
      if (next != null)
        FilledButton.icon(
          key: const ValueKey('result-next-win'),
          style: nextStyle,
          icon: const Icon(Icons.chevron_right),
          label: Text('다음: ${_game!.names[next.seat]} 결과'),
          onPressed: () => _goPage(_page + 1),
        ),
    ];
  }

  /// 함께 론한 사람 카드: 이름, 역 요약, 론 점수(본장 제외).
  Widget _othersCard(TextTheme text, ColorScheme scheme) {
    final g = _game!;
    return Card(
      key: const ValueKey('result-other-wins'),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(_others.length >= 2 ? '트리플론 — 함께 론한 사람' : '더블론 — 함께 론한 사람', style: text.titleSmall),
                ),
                _singleRonButton(),
              ],
            ),
            const SizedBox(height: 6),
            for (final o in _others)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        '${g.names[o.seat]}  ${o.result.isValid ? o.result.summary : o.result.error}',
                        style: text.bodyMedium,
                      ),
                    ),
                    if (o.result.isValid)
                      Text('${_ronOf(o.seat, o.result.basePoints).ron}점',
                          style: text.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }

  /// 함께 론한 사람을 빼고 [_winner] 한 명만 론으로 한다.
  Widget _singleRonButton({Color? color}) => TextButton(
        key: const ValueKey('result-single-ron'),
        style: color == null ? null : TextButton.styleFrom(foregroundColor: color),
        onPressed: () {
          _cancelAuto();
          setState(() => _singleRon = true);
        },
        child: Text(_winner == null ? '한 명만 론' : '한 명만 론 (${_game!.names[_winner!]})'),
      );

  /// 본장 없는 론 지불액(동시 론의 본장은 [Game.multiRonDelta] 가 가까운 쪽에 붙인다).
  Payment _ronOf(int seat, int base) {
    final g = _game!;
    return payment(base, Situation(isTsumo: false, seatWind: seat == g.dealer ? Tiles.east : Tiles.south));
  }

  @override
  void initState() {
    super.initState();
    final n = widget.result.isValid ? widget.result.yaku.length : 0;
    _reveal = AnimationController(
      vsync: this,
      duration: Duration(milliseconds: _perYaku * n + _tail),
    )..addStatusListener((s) {
        if (s == AnimationStatus.completed) {
          setState(() {});
          _startAuto();
        }
      });
    if (widget.result.isValid) _play();
  }

  /// 연출을 건너뛰었는지. 음성 연출 도중이면 읽기를 멈추고 등급만 읽는다.
  bool _skipped = false;
  bool _gradeSaid = false;
  bool _voice = false;

  /// 연출 차례 번호. 화료자 차례를 넘기면 늘려 앞 사람의 음성 연출을 멈춘다.
  int _playGen = 0;

  /// 작혼처럼 "론/쯔모" 를 외치고, 역 한 줄을 띄울 때마다 그 역을 읽고 다 읽으면 다음 줄을 띄운다.
  /// 마지막에 판·부와 등급 도장이 나올 때 등급을 읽는다. 옵션이 꺼져 있으면(기본) 연출 없이 바로 전부 보여 주고,
  /// 켰는데 못 읽으면 원래 시간표대로 띄운다.
  Future<void> _play() async {
    final gen = _playGen;
    bool stale() => !mounted || _skipped || gen != _playGen;
    _voice = await Announcer.enabled();
    if (stale()) return;
    if (!_voice) {
      _reveal.value = 1;
      return;
    }
    if (!await Announcer.say(widget.isTsumo ? '쯔모' : '론')) {
      _voice = false;
      if (!stale()) _reveal.forward();
      return;
    }
    final n = result.yaku.length;
    final total = _perYaku * n + _tail;
    for (var i = 0; i < n; i++) {
      if (stale()) return;
      _reveal.animateTo((_perYaku * i + 320) / total);
      await Announcer.say(yakuSpeech(result.yaku[i]));
    }
    if (stale()) return;
    _reveal.forward();
    _sayGrade();
  }

  void _sayGrade() {
    if (_gradeSaid) return;
    _gradeSaid = true;
    Announcer.say(gradeSpeech(result));
  }

  /// 카드(키오스크는 화면)를 누르면 연출을 건너뛴다.
  void _skip() {
    _skipped = true;
    _reveal.value = 1;
    if (!_voice) return;
    Announcer.stop().then((_) {
      if (mounted) _sayGrade();
    });
  }

  @override
  void dispose() {
    _autoTimer?.cancel();
    Announcer.stop();
    _reveal.dispose();
    super.dispose();
  }

  // ---------- 자동 반영 ----------

  Timer? _autoTimer;

  /// 자동 반영까지 남은 초. null 이면 카운트다운 중이 아님.
  int? _autoLeft;
  bool _autoCancelled = false;

  bool get _autoActive => _autoLeft != null;

  /// 연출이 끝나면 카운트다운을 시작한다(대국 기록 중, 화료자를 알고, 론이면 방총자도 알 때만).
  void _startAuto() {
    final after = widget.autoRecordAfter;
    if (after == null || _autoCancelled || _autoTimer != null || !_result.isValid) return;
    if (_game == null || _winner == null || (!widget.isTsumo && _loser == null) || _others.isNotEmpty) return;
    setState(() => _autoLeft = after.inSeconds);
    _autoTimer = Timer.periodic(const Duration(seconds: 1), (t) {
      if (!mounted) return t.cancel();
      final left = (_autoLeft ?? 1) - 1;
      if (left > 0) {
        setState(() => _autoLeft = left);
      } else {
        t.cancel();
        _recordAuto();
      }
    });
  }

  void _cancelAuto() {
    _autoTimer?.cancel();
    _autoCancelled = true;
    if (_autoLeft != null) setState(() => _autoLeft = null);
  }

  /// 카운트다운이 끝났거나 "지금 반영": 시트 없이 기록하고 닫는다.
  void _recordAuto() {
    _autoTimer?.cancel();
    if (!mounted || _recorded || _game == null || _winner == null) return;
    _recorded = true;
    final outcome = recordWinDirect(
      basePoints: _result.basePoints,
      isTsumo: widget.isTsumo,
      summary: _result.summary,
      winner: _winner!,
      loser: _loser,
      photoRiichiSeats: widget.photoRiichiSeats,
      winnerRiichi: _winnerRiichi,
      cautions: widget.autoCautions,
    );
    widget.onWinRecorded?.call(outcome);
    widget.onRecorded?.call();
    ScaffoldMessenger.maybeOf(context)
      ?..hideCurrentSnackBar()
      ..showSnackBar(const SnackBar(content: Text('대국에 자동 반영했습니다. 틀렸으면 기록의 "마지막 취소"')));
    Navigator.of(context).pop();
  }

  /// "N초 뒤 대국에 반영 · 취소 · 지금 반영" 줄. [kiosk] 면 크게.
  Widget _autoBar({required bool kiosk}) {
    final g = _game!;
    final size = kiosk ? 20.0 : 15.0;
    final row = Container(
      key: const ValueKey('result-auto-bar'),
      padding: EdgeInsets.symmetric(horizontal: kiosk ? 16 : 10, vertical: kiosk ? 6 : 2),
      decoration: BoxDecoration(
        color: kiosk ? kioskGoldDeep.withValues(alpha: 0.25) : Theme.of(context).colorScheme.primaryContainer,
        borderRadius: BorderRadius.circular(kiosk ? 14 : 10),
        border: kiosk ? Border.all(color: kioskGoldDeep) : null,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.timer_outlined, size: size + 4, color: kiosk ? Colors.white : null),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              kiosk ? '$_autoLeft초 뒤 대국에 반영 (${g.roundLabel})' : '$_autoLeft초 뒤 자동 반영',
              key: const ValueKey('result-auto-left'),
              style: TextStyle(fontSize: size, fontWeight: FontWeight.w700, color: kiosk ? Colors.white : null),
            ),
          ),
          const SizedBox(width: 8),
          TextButton(
            key: const ValueKey('result-auto-cancel'),
            style: kiosk ? TextButton.styleFrom(foregroundColor: Colors.white, minimumSize: const Size(0, 48)) : null,
            onPressed: _cancelAuto,
            child: Text('취소', style: TextStyle(fontSize: size)),
          ),
          FilledButton(
            key: const ValueKey('result-auto-now'),
            style: kiosk
                ? FilledButton.styleFrom(
                    backgroundColor: kioskGoldDeep, foregroundColor: Colors.white, minimumSize: const Size(0, 48))
                : null,
            onPressed: _recordAuto,
            child: Text('지금 반영', style: TextStyle(fontSize: size)),
          ),
        ],
      ),
    );
    if (widget.autoCautions.isEmpty) return row;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          key: const ValueKey('result-auto-caution'),
          padding: EdgeInsets.symmetric(horizontal: kiosk ? 14 : 10, vertical: kiosk ? 4 : 3),
          margin: const EdgeInsets.only(bottom: 4),
          decoration: BoxDecoration(color: Colors.orange.shade800, borderRadius: BorderRadius.circular(8)),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.warning_amber_rounded, size: size + 4, color: Colors.white),
              const SizedBox(width: 6),
              Flexible(
                child: Text(
                  '${widget.autoCautions.join(' · ')} 확인',
                  style: TextStyle(fontSize: size, fontWeight: FontWeight.w800, color: Colors.white),
                ),
              ),
            ],
          ),
        ),
        row,
      ],
    );
  }

  /// 연출 중 i 번째 역(합계는 n, 점수는 n+1)이 보이는 정도 0~1.
  Animation<double> _step(int i) {
    final n = result.yaku.length;
    final total = _perYaku * n + _tail;
    final start = i <= n ? _perYaku * i : _perYaku * n + 350;
    final end = (start + 320).clamp(0, total);
    return CurvedAnimation(
      parent: _reveal,
      curve: Interval(start / total, end / total, curve: Curves.easeOut),
    );
  }

  Widget _fadeIn(int i, Widget child, {bool stamp = false}) {
    final a = _step(i);
    return AnimatedBuilder(
      animation: a,
      builder: (_, c) => Opacity(
        opacity: a.value,
        child: Transform.translate(
          offset: stamp ? Offset.zero : Offset(24 * (1 - a.value), 0),
          child: stamp ? Transform.scale(scale: 1.8 - 0.8 * a.value, child: c) : c,
        ),
      ),
      child: child,
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;

    if (!result.isValid) {
      // 거치 촬영 판독이 화료 형태가 아니면 여기서 바로 고치러 갈 수 있어야 한다(고쳐서 반영해야 정답이 남는다).
      return Scaffold(
        appBar: AppBar(title: const Text('결과')),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.error_outline, size: 48, color: scheme.error),
                const SizedBox(height: 12),
                Text(result.error!, style: text.titleMedium, textAlign: TextAlign.center),
                if (widget.flags.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  for (final f in widget.flags) Text('• $f', style: text.bodySmall, textAlign: TextAlign.center),
                ],
                if (widget.onFix != null) ...[
                  const SizedBox(height: 20),
                  FilledButton.icon(
                    key: const ValueKey('result-fix'),
                    icon: const Icon(Icons.edit_outlined, size: 18),
                    label: const Text('판독 수정'),
                    onPressed: widget.onFix,
                  ),
                ],
              ],
            ),
          ),
        ),
      );
    }

    if (isKioskLayout(context)) return _kioskBody(context);

    final p = result.payment;
    final d = result.decomposition;
    final n = result.yaku.length;
    final stamp = result.isYakuman ? _yakumanTotal(result) : result.limit.label;
    final reds = RedMarks(_hand);

    final pageLabel = _pageLabel;
    return Scaffold(
      appBar: AppBar(
        title: Text(pageLabel == null ? '결과' : '${_game!.names[_shownSeat!]} 결과 · $pageLabel'),
        actions: [
          if (widget.onFix != null)
            TextButton.icon(
              icon: const Icon(Icons.edit_outlined, size: 18),
              label: const Text('판독 수정'),
              onPressed: widget.onFix,
            ),
        ],
      ),
      body: ListView(
        padding: EdgeInsets.fromLTRB(12, 12, 12, 12 + MediaQuery.paddingOf(context).bottom),
        children: [
          if (widget.flags.isNotEmpty)
            Card(
              color: scheme.tertiaryContainer,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      Icon(Icons.warning_amber_rounded, size: 18, color: scheme.onTertiaryContainer),
                      const SizedBox(width: 6),
                      Text('확인할 것', style: text.titleSmall),
                    ]),
                    const SizedBox(height: 4),
                    for (final f in widget.flags) Text('• $f', style: text.bodySmall),
                  ],
                ),
              ),
            ),
          Card(
            color: scheme.primaryContainer,
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              // 누르면 연출을 건너뛴다.
              onTap: _reveal.isCompleted ? null : _skip,
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (d != null && d.sets.isNotEmpty) ...[
                      Wrap(
                        spacing: 6,
                        runSpacing: 6,
                        children: [
                          for (final s in d.sets)
                            Container(
                              padding: const EdgeInsets.all(2),
                              decoration: s.isCalled
                                  ? BoxDecoration(
                                      border: Border.all(color: scheme.outline),
                                      borderRadius: BorderRadius.circular(6),
                                    )
                                  : null,
                              child: TileRow(s.tiles, width: 26, open: !s.isClosedKan, reds: reds.marks(s.tiles)),
                            ),
                        ],
                      ),
                      const SizedBox(height: 12),
                    ],
                    for (var i = 0; i < n; i++)
                      _fadeIn(
                        i,
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 3),
                          child: Row(
                            children: [
                              Expanded(
                                child: Text(result.yaku[i].yaku.label,
                                    style: text.titleMedium?.copyWith(fontWeight: FontWeight.w600)),
                              ),
                              Text(_hanLabel(result.yaku[i]),
                                  style: text.titleMedium?.copyWith(color: scheme.primary)),
                            ],
                          ),
                        ),
                      ),
                    const Divider(height: 20),
                    _fadeIn(
                      n,
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              result.isYakuman ? '' : '${result.han}판 ${result.fu.total}부',
                              style: text.titleMedium?.copyWith(fontWeight: FontWeight.w700),
                            ),
                          ),
                          if (stamp.isNotEmpty)
                            _fadeIn(
                              n + 1,
                              _Stamp(stamp, key: const ValueKey('result-stamp')),
                              stamp: true,
                            ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 6),
                    _fadeIn(
                      n + 1,
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${p.total}점',
                            style: text.displaySmall?.copyWith(fontWeight: FontWeight.w800),
                          ),
                          const SizedBox(height: 2),
                          Text(_paymentLine(p), style: text.bodyLarge),
                        ],
                      ),
                    ),
                    if (_game != null) ...[
                      const SizedBox(height: 10),
                      if (_autoActive)
                        _autoBar(kiosk: false)
                      else
                        // 동시 론이면 마지막 화료자 차례에서 모두 함께 기록한다.
                        Wrap(spacing: 8, runSpacing: 6, children: [
                          ..._pageButtons(),
                          if (_nextWin == null)
                            FilledButton.tonalIcon(
                              icon: const Icon(Icons.scoreboard_outlined, size: 18),
                              label: Text('대국에 반영 (${_game!.roundLabel})'),
                              onPressed: () => _record(context),
                            ),
                        ]),
                    ],
                  ],
                ),
              ),
            ),
          ),
          if (_others.isNotEmpty && _page == 0) _othersCard(text, scheme),
          const SizedBox(height: 8),
          if (_hand != null && _shownSit != null) _Section(title: '상황 고치기', child: _situationChips(kiosk: false)!),
          _Section(title: '점수 이동', child: _cross()),
          if (!result.isYakuman)
            _Section(
              title: '부수',
              child: Column(
                children: [
                  for (final f in result.fu.items)
                    Row(
                      children: [
                        Expanded(child: Text(f.label)),
                        Text('${f.fu}부'),
                      ],
                    ),
                  const Divider(),
                  Row(
                    children: [
                      const Expanded(child: Text('합계', style: TextStyle(fontWeight: FontWeight.w600))),
                      Text('${result.fu.total}부', style: const TextStyle(fontWeight: FontWeight.w600)),
                    ],
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  /// 네 자리 점수 이동판. 대국 기록이 있으면 점수판 값(이름·점수·본장·공탁·리치)으로,
  /// 없으면 화료자를 아래에 두고 변화만 보여 준다.
  Widget _cross({VoidCallback? onChanged}) {
    final g = _game;
    final tsumo = widget.isTsumo;
    void changed(VoidCallback f) {
      // 자리를 직접 고치면 자동 반영을 멈춘다(사용자가 확인하며 반영).
      _cancelAuto();
      setState(() {
        f();
        // 화료자·방총자를 바꿔 함께 론한 사람이 줄었으면 대표 화료자 차례로.
        if (_page > _pages.length) _page = 0;
      });
      onChanged?.call();
    }

    if (g == null) {
      final winner = widget.seatWind - Tiles.east; // 친(동)이 자리 0
      final delta = Game.winDelta(
          dealer: 0, winner: winner, payment: _result.payment, isTsumo: tsumo, loser: _loser);
      final seats = [
        for (var side = 0; side < 4; side++)
          () {
            final s = (winner + side) % 4;
            return CrossSeat(wind: s, delta: delta[s], winner: s == winner, loser: s == _loser);
          }(),
      ];
      return ScoreCross(
        seats: seats,
        revealed: _reveal.isCompleted,
        countUp: _voice,
        center: [tsumo ? '쯔모' : '론'],
        prompt: !tsumo && _loser == null ? '방총자 자리를 누르세요' : null,
        onTapSide: tsumo
            ? null
            : (side) {
                final s = (winner + side) % 4;
                if (s != winner) changed(() => _loser = s);
              },
      );
    }

    final bottom = g.settings.bottomSeat;
    final winner = _winner;
    var delta = List.filled(4, 0);
    var auto = <int>{};
    final others = _others;
    if (winner != null) {
      auto = g.autoRiichiCandidates(widget.photoRiichiSeats,
          winner: winner,
          winnerRiichi: _winnerRiichi,
          otherWinners: {for (final o in others) o.seat: o.riichi});
      if (others.isNotEmpty && _loser != null) {
        delta = Game.multiRonDelta(
          loser: _loser!,
          ron: {
            winner: _ronOf(winner, _result.basePoints).ron,
            for (final o in others)
              if (o.result.isValid) o.seat: _ronOf(o.seat, o.result.basePoints).ron,
          },
          honba: g.honba,
          sticks: g.riichiSticks,
          newRiichi: auto,
        );
      } else {
        final pay = payment(
          _result.basePoints,
          Situation(
              isTsumo: tsumo,
              seatWind: winner == g.dealer ? Tiles.east : Tiles.south,
              honba: g.honba),
        );
        delta = Game.winDelta(
          dealer: g.dealer,
          winner: winner,
          payment: pay,
          isTsumo: tsumo,
          loser: _loser,
          sticks: g.riichiSticks,
          newRiichi: auto,
        );
      }
    }
    final seats = [
      for (var side = 0; side < 4; side++)
        () {
          final s = (bottom + side) % 4;
          return CrossSeat(
            wind: g.seatWindOf(s) - Tiles.east,
            name: g.names[s],
            before: g.scores[s],
            delta: delta[s],
            winner: s == winner || others.any((o) => o.seat == s),
            loser: s == _loser,
            autoRiichi: auto.contains(s),
          );
        }(),
    ];
    final sticks = g.riichiSticks + auto.length;
    final String? prompt = winner == null
        ? '화료자 자리를 누르세요'
        : (!tsumo && _loser == null ? '방총자 자리를 누르세요' : null);
    return ScoreCross(
      seats: seats,
      revealed: _reveal.isCompleted && winner != null,
      countUp: _voice,
      center: [
        g.roundLabel,
        if (sticks > 0) '공탁 $sticks',
      ],
      prompt: prompt,
      onTapSide: (side) {
        final s = (bottom + side) % 4;
        changed(() {
          if (_winner == null) {
            _winner = s;
            if (_loser == s) _loser = null;
          } else if (s == _winner) {
            // 화료자를 다시 누르면 화료자부터 다시 고른다.
            _winner = null;
          } else if (!tsumo) {
            _loser = s;
          }
        });
      },
    );
  }

  Future<void> _record(BuildContext context) async {
    _cancelAuto();
    final outcome = await showWinSheet(
      context,
      _game!,
      basePoints: _result.basePoints,
      isTsumo: widget.isTsumo,
      summary: _result.summary,
      winner: _winner,
      loser: _loser == _winner ? null : _loser,
      photoRiichiSeats: widget.photoRiichiSeats,
      winnerRiichi: _winnerRiichi,
      paoBase: paoBasePoints(_result),
      extraWins: [
        for (final o in _others)
          if (o.result.isValid)
            ExtraWin(winner: o.seat, basePoints: o.result.basePoints, summary: o.result.summary, riichi: o.riichi),
      ],
    );
    if (outcome == null || !context.mounted || _recorded) return;
    _recorded = true;
    widget.onWinRecorded?.call(outcome);
    widget.onRecorded?.call();
    Navigator.of(context).pop();
  }

  String _paymentLine(Payment p) {
    if (p.ron > 0) return '론: 방총자 ${p.ron}점';
    if (p.tsumoFromDealer == 0) return '쯔모: 각 ${p.tsumoFromNonDealer}점';
    return '쯔모: 자 ${p.tsumoFromNonDealer}점 / 친 ${p.tsumoFromDealer}점';
  }

  String _hanLabel(YakuHan y) {
    if (y.yaku.isYakuman) return y.han >= 2 ? '더블 역만' : '역만';
    return '${y.han}판';
  }

  String _yakumanTotal(ScoreResult r) {
    final n = r.yakumanCount;
    return n >= 2 ? '$n배 역만' : '역만';
  }
}

/// 만관·하네만·역만 같은 등급 도장.
class _Stamp extends StatelessWidget {
  final String label;
  const _Stamp(this.label, {super.key});

  @override
  Widget build(BuildContext context) {
    const red = Color(0xFFC62828);
    return Transform.rotate(
      angle: -0.08,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          border: Border.all(color: red, width: 2.5),
          borderRadius: BorderRadius.circular(6),
        ),
        child: Text(label,
            style: const TextStyle(color: red, fontSize: 20, fontWeight: FontWeight.w900, letterSpacing: 2)),
      ),
    );
  }
}

class _Section extends StatelessWidget {
  final String title;
  final Widget child;
  const _Section({required this.title, required this.child});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            child,
          ],
        ),
      ),
    );
  }
}
