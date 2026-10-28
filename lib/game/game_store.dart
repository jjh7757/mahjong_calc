import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'game.dart';

/// 진행 중인 대국과 끝난 대국 목록. 기기에 저장한다.
class GameStore extends ChangeNotifier {
  static const _currentKey = 'game.current';
  static const _historyKey = 'game.history';

  Game? current;
  List<Game> history = [];
  bool loaded = false;

  Future<void> load() async {
    final p = await SharedPreferences.getInstance();
    final c = p.getString(_currentKey);
    if (c != null) {
      try {
        current = Game.fromJson(jsonDecode(c) as Map<String, dynamic>);
      } catch (_) {
        current = null;
      }
    }
    final h = p.getStringList(_historyKey) ?? [];
    history = [];
    for (final s in h) {
      try {
        history.add(Game.fromJson(jsonDecode(s) as Map<String, dynamic>));
      } catch (_) {}
    }
    loaded = true;
    notifyListeners();
  }

  Future<void> _save() async {
    final p = await SharedPreferences.getInstance();
    if (current == null) {
      await p.remove(_currentKey);
    } else {
      await p.setString(_currentKey, jsonEncode(current!.toJson()));
    }
    await p.setStringList(_historyKey, history.map((g) => jsonEncode(g.toJson())).toList());
  }

  void start(List<String> names, GameSettings settings) {
    current = Game(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      startedAt: DateTime.now(),
      settings: settings,
      names: names,
    );
    _save();
    notifyListeners();
  }

  /// 진행 중이던 대국을 현재 국·점수부터 기록한다.
  void resume(
    List<String> names,
    GameSettings settings, {
    required List<int> scores,
    required int roundWind,
    required int roundNumber,
    int honba = 0,
    int riichiSticks = 0,
  }) {
    current = Game.resumed(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      startedAt: DateTime.now(),
      settings: settings,
      names: names,
      scores: scores,
      roundWind: roundWind,
      roundNumber: roundNumber,
      honba: honba,
      riichiSticks: riichiSticks,
    );
    _save();
    notifyListeners();
  }

  /// 현재 대국을 바꾸고 저장한다. 사건이 늘었으면(기록 하나) 바꾸기 직전 상태를 되돌리기 지점으로 남긴다.
  void mutate(void Function(Game g) change) {
    final g = current;
    if (g == null) return;
    final before = g.checkpoint();
    change(g);
    if (g.events.length > before.eventCount) {
      g.checkpoints.add(before);
      _redo = null;
    }
    _save();
    notifyListeners();
  }

  /// 되돌리기 직전 대국(JSON). "다시 실행" 한 번용, 새 기록을 넣으면 버린다. 저장하지 않는다.
  String? _redo;

  bool get canRedo => _redo != null && current != null;

  /// 지점 [to](없으면 마지막 기록 직전)로 되돌린다. 지운 사건들을 돌려준다.
  List<GameEvent> rewind([GameCheckpoint? to]) {
    final g = current;
    if (g == null || !g.canUndo) return const [];
    final c = to ?? g.checkpoints.last;
    final removed = g.eventsAfter(c);
    _redo = jsonEncode(g.toJson());
    g.rewindTo(c);
    _save();
    notifyListeners();
    return removed;
  }

  /// 마지막 되돌리기를 취소한다(같은 대국일 때만).
  void redo() {
    final s = _redo;
    if (s == null || current == null) return;
    final g = Game.fromJson(jsonDecode(s) as Map<String, dynamic>);
    if (g.id != current!.id) return;
    _redo = null;
    // 같은 객체를 고친다(화면들이 대국 객체를 들고 있다).
    current!.restoreFrom(g);
    _save();
    notifyListeners();
  }

  void finish() {
    final g = current;
    if (g == null) return;
    g.finished = true;
    g.checkpoints.clear(); // 끝난 대국은 되돌리지 않는다.
    _redo = null;
    history.insert(0, g);
    if (history.length > 100) history.removeRange(100, history.length);
    current = null;
    _save();
    notifyListeners();
  }

  void discardCurrent() {
    current = null;
    _save();
    notifyListeners();
  }

  void deleteHistory(String id) {
    history.removeWhere((g) => g.id == id);
    _save();
    notifyListeners();
  }
}

/// 앱 전체에서 하나만 쓴다.
final GameStore gameStore = GameStore();
