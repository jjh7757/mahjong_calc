import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'paifu.dart';

/// 대국마다 적힌 패보(국 단위)를 기기에 둔다. 한 국에 5KB 안팎이라 SharedPreferences 의 문자열 목록으로 충분하다.
class PaifuStore {
  static String _key(String gameId) => 'paifu.$gameId';

  /// 그 대국의 패보들(적힌 순서).
  static Future<List<Paifu>> list(String gameId) async {
    final p = await SharedPreferences.getInstance();
    final out = <Paifu>[];
    for (final s in p.getStringList(_key(gameId)) ?? const <String>[]) {
      try {
        out.add(Paifu.fromJson(jsonDecode(s) as Map<String, dynamic>));
      } catch (_) {
        // 읽지 못하는 옛 기록은 건너뛴다.
      }
    }
    return out;
  }

  /// 같은 [Paifu.id] 가 있으면 바꾸고(같은 국을 다시 찍음) 없으면 끝에 붙인다.
  static Future<void> put(String gameId, Paifu paifu) async {
    final p = await SharedPreferences.getInstance();
    final all = await list(gameId);
    final i = all.indexWhere((x) => x.id == paifu.id);
    if (i >= 0) {
      all[i] = paifu;
    } else {
      all.add(paifu);
    }
    await p.setStringList(_key(gameId), [for (final x in all) jsonEncode(x.toJson())]);
  }

  static Future<void> delete(String gameId) async {
    final p = await SharedPreferences.getInstance();
    await p.remove(_key(gameId));
  }
}
