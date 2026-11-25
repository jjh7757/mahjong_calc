import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'game.dart';

/// 진행 중인 대국과 끝난 대국 목록. 기기에 저장한다.
class GameStore extends ChangeNotifier {
  static const _currentKey = 'game.current';
  static const _historyKey = 'game.history';

  /// 지난 대국을 몇 개까지 남기나. 멤버 순위가 오래된 기록을 잃지 않게 넉넉히 둔다(옛 100).
  static const maxHistory = 1000;

  Game? current;
  List<Game> history = [];
  bool loaded = false;

  /// 대국이 끝나 지난 대국에 들어간 직후([finish] · [addFinished]) 부르는 고리. 앱은 기록 사이트 올리기를 단다
  /// (`recordsUploader.onFinished`, main.dart). 저장 뒤에 부르고, 던져도 대국 흐름은 막지 않는다.
  void Function(Game g)? onFinished;

  void _notifyFinished(Game g) {
    final f = onFinished;
    if (f == null) return;
    try {
      f(g);
    } catch (e) {
      debugPrint('[records] 끝난 대국 알림 실패: $e');
    }
  }

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
    _trimHistory();
    current = null;
    _save();
    notifyListeners();
    _notifyFinished(g);
  }

  /// 앱 밖에서 친 대국(직접 입력, [Game.manual])처럼 이미 끝난 대국을 지난 대국에 넣는다.
  /// 진행 중 대국은 건드리지 않는다. 목록은 시작 시각 내림차순 자리에 끼운다(같은 시각이면 앞에).
  void addFinished(Game g) {
    g.finished = true;
    g.checkpoints.clear();
    var i = history.indexWhere((h) => !h.startedAt.isAfter(g.startedAt));
    if (i < 0) i = history.length;
    history.insert(i, g);
    _trimHistory();
    _save();
    notifyListeners();
    _notifyFinished(g);
  }

  void _trimHistory() {
    if (history.length > maxHistory) history.removeRange(maxHistory, history.length);
  }

  /// 대국 [gameId](지난 대국 또는 진행 중 대국)에 '마블리에 올림' 표시를 남긴다([Game.mavelyUploadedAt]).
  /// 찾으면 저장·알림하고 true, 없으면 false.
  bool markMavelyUploaded(String gameId, {DateTime? at}) {
    Game? g;
    for (final h in history) {
      if (h.id == gameId) {
        g = h;
        break;
      }
    }
    if (g == null && current?.id == gameId) g = current;
    if (g == null) return false;
    g.mavelyUploadedAt = at ?? DateTime.now();
    _save();
    notifyListeners();
    return true;
  }

  /// 지난 대국 [gameId] 에 '기록 사이트에 올림' 표시를 남긴다([Game.recordsUploadedAt]). 찾으면 true.
  /// [save] 가 false 면 저장하지 않는다 — 여러 대국을 한꺼번에 올릴 때 매번 지난 대국 전체를 쓰지 않게, 끝에 [persist] 한 번.
  bool markRecordsUploaded(String gameId, {DateTime? at, bool save = true}) {
    Game? g;
    for (final h in history) {
      if (h.id == gameId) {
        g = h;
        break;
      }
    }
    if (g == null) return false;
    g.recordsUploadedAt = at ?? DateTime.now();
    if (save) _save();
    notifyListeners();
    return true;
  }

  /// 지금 상태를 저장한다([markRecordsUploaded] 를 save: false 로 부른 뒤).
  Future<void> persist() => _save();

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
