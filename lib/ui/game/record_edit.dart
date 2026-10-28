import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../game/game.dart';
import '../../game/game_store.dart';
import '../kiosk.dart';

/// 대국 기록 되돌리기·정정(점수판·테이블 화면·종료 화면 공용).
///
/// 되돌리기: 기록 하나(화료·유국·리치·정정)를 넣기 직전 상태로 돌아가고 그 뒤 기록을 지운다.
/// 지난 기록을 고치려면 그 기록부터 되돌리고 다시 넣는다(뒤 국의 친·본장이 앞 기록에 달려 있어서).
/// 점수만 틀렸으면 점수 정정(사건 하나로 남고, 이것도 되돌릴 수 있다).

String _roundLabelOf(GameCheckpoint c) =>
    '${Game.windNames[c.roundWind]}${c.roundNumber}국${c.honba > 0 ? ' ${c.honba}본장' : ''}';

/// 되돌리기 확인 창. [eventIndex] 가 있으면 그 기록부터, 없으면 마지막 기록. 되돌렸으면 true.
Future<bool> confirmRewind(BuildContext context, {int? eventIndex}) async {
  final g = gameStore.current;
  if (g == null || !g.canUndo) return false;
  final c = eventIndex == null ? g.checkpoints.last : g.checkpointBefore(eventIndex);
  if (c == null) return false;
  final removed = g.eventsAfter(c);
  final changed = [for (var s = 0; s < 4; s++) if (g.scores[s] != c.scores[s]) s];
  final roundNow = g.roundLabel;
  final roundThen = _roundLabelOf(c);

  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => kioskWrap(ctx, AlertDialog(
      title: Text(eventIndex == null ? '마지막 기록을 취소할까요?' : '이 기록부터 되돌릴까요?'),
      content: SizedBox(
        width: 460,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('지울 기록 ${removed.length}건', style: const TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 4),
              for (final e in removed)
                Padding(
                  padding: const EdgeInsets.only(bottom: 2),
                  child: Text('· ${e.roundLabel}  ${e.description}', style: const TextStyle(fontSize: 13)),
                ),
              const SizedBox(height: 12),
              if (changed.isNotEmpty) ...[
                const Text('점수', style: TextStyle(fontWeight: FontWeight.w700)),
                for (final s in changed)
                  Text('${g.names[s]}  ${g.scores[s]} → ${c.scores[s]}', key: ValueKey('rewind-score-$s')),
                const SizedBox(height: 8),
              ],
              if (roundNow != roundThen || g.riichiSticks != c.riichiSticks)
                Text('$roundNow 공탁 ${g.riichiSticks} → $roundThen 공탁 ${c.riichiSticks}'),
              if (g.isOver && c.endedBy == null) const Text('대국 종료도 풀립니다.'),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('아니오')),
        FilledButton(
          key: const ValueKey('rewind-confirm'),
          onPressed: () => Navigator.pop(ctx, true),
          child: const Text('되돌리기'),
        ),
      ],
    )),
  );
  if (ok != true || !context.mounted) return false;
  final gone = gameStore.rewind(c);
  ScaffoldMessenger.maybeOf(context)
    ?..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(
      content: Text('기록 ${gone.length}건을 되돌렸습니다'),
      duration: const Duration(seconds: 8),
      // 액션이 있는 스낵바는 기본으로 안 사라진다(Flutter 3.29+). 8초 뒤 사라지게.
      persist: false,
      action: SnackBarAction(label: '다시 실행', onPressed: gameStore.redo),
    ));
  return true;
}

/// 기록 한 줄을 눌렀을 때: 그 기록부터 되돌리기 / 점수 정정.
Future<void> showEventActions(BuildContext context, int eventIndex) async {
  final g = gameStore.current;
  if (g == null || eventIndex >= g.events.length) return;
  final e = g.events[eventIndex];
  final canRewind = g.checkpointBefore(eventIndex) != null;
  final pick = await showDialog<String>(
    context: context,
    builder: (ctx) => kioskWrap(ctx, SimpleDialog(
      title: Text('${e.roundLabel}  ${e.description}'),
      children: [
        SimpleDialogOption(
          key: const ValueKey('event-rewind'),
          onPressed: canRewind ? () => Navigator.pop(ctx, 'rewind') : null,
          child: Text(
            canRewind ? '이 기록부터 되돌리기 (뒤 기록도 지움)' : '되돌릴 수 없는 기록입니다 (시작 기록·옛 기록)',
            style: canRewind ? null : TextStyle(color: Theme.of(ctx).disabledColor),
          ),
        ),
        SimpleDialogOption(
          key: const ValueKey('event-correct'),
          onPressed: () => Navigator.pop(ctx, 'correct'),
          child: const Text('점수 정정 (점수·본장·공탁 고치기)'),
        ),
      ],
    )),
  );
  if (!context.mounted) return;
  if (pick == 'rewind') {
    await confirmRewind(context, eventIndex: eventIndex);
  } else if (pick == 'correct') {
    await showScoreCorrection(context);
  }
}

/// 점수 정정 창: 자리별 새 점수와 본장·공탁을 고친다. 바뀐 것이 있으면 사건 하나로 기록.
Future<void> showScoreCorrection(BuildContext context) async {
  final g = gameStore.current;
  if (g == null) return;
  final ctrls = [for (var s = 0; s < 4; s++) TextEditingController(text: '${g.scores[s]}')];
  final reason = TextEditingController(text: '점수 정정');
  var honba = g.honba;
  var sticks = g.riichiSticks;

  List<int>? deltas() {
    final out = <int>[];
    for (var s = 0; s < 4; s++) {
      final v = int.tryParse(ctrls[s].text.trim());
      if (v == null) return null;
      out.add(v - g.scores[s]);
    }
    return out;
  }

  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => kioskWrap(ctx, StatefulBuilder(builder: (ctx, setState) {
      final d = deltas();
      final sum = d?.fold<int>(0, (a, b) => a + b);
      final changed = d != null && (d.any((x) => x != 0) || honba != g.honba || sticks != g.riichiSticks);
      Widget stepper(String label, int v, void Function(int) set) => Row(
            children: [
              SizedBox(width: 56, child: Text(label)),
              IconButton(onPressed: v > 0 ? () => setState(() => set(v - 1)) : null, icon: const Icon(Icons.remove_circle_outline)),
              Text('$v', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
              IconButton(onPressed: () => setState(() => set(v + 1)), icon: const Icon(Icons.add_circle_outline)),
            ],
          );
      return AlertDialog(
        title: const Text('점수 정정'),
        content: SizedBox(
          width: 460,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (var s = 0; s < 4; s++)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Row(
                      children: [
                        SizedBox(width: 90, child: Text(g.names[s], overflow: TextOverflow.ellipsis)),
                        Expanded(
                          child: TextField(
                            key: ValueKey('correct-score-$s'),
                            controller: ctrls[s],
                            keyboardType: const TextInputType.numberWithOptions(signed: true),
                            inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'^-?\d*'))],
                            decoration: const InputDecoration(isDense: true, border: OutlineInputBorder()),
                            onChanged: (_) => setState(() {}),
                          ),
                        ),
                        SizedBox(
                          width: 80,
                          child: Text(
                            d == null || d[s] == 0 ? '' : '${d[s] > 0 ? '+' : ''}${d[s]}',
                            textAlign: TextAlign.right,
                            style: TextStyle(color: (d?[s] ?? 0) < 0 ? Colors.redAccent : Colors.green),
                          ),
                        ),
                      ],
                    ),
                  ),
                stepper('본장', honba, (v) => honba = v),
                stepper('공탁', sticks, (v) => sticks = v),
                if (sum != null && sum != 0)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text(
                      '점수 합계가 ${sum > 0 ? '+' : ''}$sum 바뀝니다. 공탁(1000점) 이동이 아니면 합계는 0 이어야 합니다.',
                      style: const TextStyle(fontSize: 12, color: Colors.orange),
                    ),
                  ),
                const SizedBox(height: 8),
                TextField(
                  controller: reason,
                  decoration: const InputDecoration(labelText: '사유', isDense: true, border: OutlineInputBorder()),
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('취소')),
          FilledButton(
            key: const ValueKey('correct-confirm'),
            onPressed: changed ? () => Navigator.pop(ctx, true) : null,
            child: const Text('기록'),
          ),
        ],
      );
    })),
  );
  final d = deltas();
  if (ok == true && d != null) {
    final why = reason.text.trim().isEmpty ? '점수 정정' : reason.text.trim();
    gameStore.mutate((g) => g.correct(delta: d, honba: honba, riichiSticks: sticks, reason: why));
  }
  // 컨트롤러는 닫히는 애니메이션 동안 아직 쓰이므로 여기서 dispose 하지 않는다(네이티브 자원 없음).
}
