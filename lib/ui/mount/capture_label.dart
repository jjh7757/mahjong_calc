import '../../services/capture_log.dart';
import '../game/win_sheet.dart';
import '../hand_editor.dart';

/// "대국에 반영" 한 확정 값을 촬영 기록의 정답(label.json)으로 만든다.
/// 키는 meta.json 의 `merge` 와 같다(closed 는 화료패가 마지막, 적도라는 0).
/// 바로 반영했든 "판독 수정" 으로 고쳐서 반영했든, 기록한 순간의 입력 화면 값이 정답이다.
Map<String, Object?> captureLabelJson(HandEditor e, WinOutcome o, {DateTime? now}) {
  final winIdx = e.closed.isEmpty ? null : (e.winIndex ?? e.closed.length - 1);
  final win = winIdx == null ? null : e.closed[winIdx];
  return {
    'time': (now ?? DateTime.now()).toIso8601String(),
    'round': o.roundLabel,
    'honba': o.honba,
    'winner': o.winner,
    'is_tsumo': o.isTsumo,
    'loser': o.loser,
    'closed': [
      for (var i = 0; i < e.closed.length; i++)
        if (i != winIdx) CaptureLog.tileCode(e.closed[i].tile, red: e.closed[i].red),
      if (win != null) CaptureLog.tileCode(win.tile, red: win.red),
    ],
    'win_tile': win == null ? null : CaptureLog.tileCode(win.tile, red: win.red),
    'melds': [for (final m in e.melds) m.toString()],
    'red_count': e.redTotal,
    'riichi': e.hasRiichi,
    'dora_indicators': [for (final t in e.doraIndicators) CaptureLog.tileCode(t)],
    'ura_indicators': [for (final t in e.uraIndicators) CaptureLog.tileCode(t)],
    'riichi_seats': o.riichiSeats.toList()..sort(),
    'auto_riichi_seats': o.autoRiichiSeats.toList()..sort(),
  };
}

/// 정답을 기다리는 촬영이 같은 국에 있으면 label.json 을 쓴다. 쓴 폴더를 돌려준다.
/// 손패를 비우기 전에 불러야 한다(ResultScreen.onWinRecorded).
Future<String?> saveCaptureLabel(HandEditor e, WinOutcome o) async {
  final dir = CaptureLog.takePending(CaptureLog.roundKey(o.roundLabel, o.honba));
  if (dir == null) return null;
  final ok = await CaptureLog.saveLabel(dir, captureLabelJson(e, o));
  return ok ? dir : null;
}
