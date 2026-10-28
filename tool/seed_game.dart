// 노트북 시험용: 진행 중 대국 하나를 shared_preferences 값(JSON 문자열)으로 찍는다.
// 사용: dart run tool/seed_game.dart
import 'dart:convert';

import 'package:mahjong_calc/game/game.dart';

void main() {
  final g = Game(
    id: DateTime.now().millisecondsSinceEpoch.toString(),
    startedAt: DateTime.now(),
    settings: const GameSettings(),
    names: const ['A', 'B', 'C', 'D'],
  );
  // ignore: avoid_print
  print(jsonEncode(g.toJson()));
}
