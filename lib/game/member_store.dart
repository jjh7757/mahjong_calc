import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 등록 멤버 명단. 대국 결과 직접 입력에서 이름은 이 명단에서만 고른다(오타로 다른 사람이 되지 않게).
///
/// 명단에서 빼도 지난 대국 기록(이름)은 그대로 남는다. 다시 같은 이름으로 넣으면 순위에 다시 잡힌다.
class MemberStore extends ChangeNotifier {
  static const _key = 'members.list';

  final List<String> _members = [];
  bool loaded = false;

  /// 등록 순.
  List<String> get members => List.unmodifiable(_members);

  Future<void> load() async {
    final p = await SharedPreferences.getInstance();
    _members
      ..clear()
      ..addAll(p.getStringList(_key) ?? const []);
    loaded = true;
    notifyListeners();
  }

  Future<void> _save() async {
    final p = await SharedPreferences.getInstance();
    await p.setStringList(_key, List.of(_members));
  }

  /// 이름을 앞뒤 공백을 떼고 넣는다. 빈 이름이거나 이미 있으면 false.
  bool add(String name) {
    final n = name.trim();
    if (n.isEmpty || _members.contains(n)) return false;
    _members.add(n);
    _save();
    notifyListeners();
    return true;
  }

  /// 명단에서만 뺀다(지난 대국 기록은 그대로).
  void remove(String name) {
    if (!_members.remove(name)) return;
    _save();
    notifyListeners();
  }
}

/// 앱 전체에서 하나만 쓴다.
final MemberStore memberStore = MemberStore();
