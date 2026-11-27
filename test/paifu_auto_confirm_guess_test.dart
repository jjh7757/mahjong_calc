// 설계서 docs/paifu_auto_agent_design_1124.md 8-26 끝 조건 5: 자동 확정(--confirm auto)이 짐작 표시(guess)를 단 패보를
// 앱이 그대로 읽어 그 순을 ReviewStatus.guessed(평가 안 함)로 두는지. 앱 코드는 안 고침 — 시험만.
// 입력은 실행 폴더의 패보(experiments/ 결과물은 커밋하지 않음)라 파일이 없으면 건너뜀.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';

const _path = 'experiments/paifu_frames/results/auto_h2_ac2/paifu/w15_134151.json';

/// hero 버림 차례 번호(1부터) 중 버림 사건 또는 바로 앞 hero 사건(뽑기)이 guess 인 것.
Set<int> _guessedTurns(Map<String, dynamic> j) {
  final hero = j['hero'] as int;
  final events = (j['events'] as List).cast<Map<String, dynamic>>();
  final out = <int>{};
  var turn = 0;
  for (var i = 0; i < events.length; i++) {
    final e = events[i];
    if (e['seat'] != hero || e['type'] != 'discard') continue;
    turn++;
    Map<String, dynamic>? prev;
    for (var k = i - 1; k >= 0; k--) {
      if (events[k]['seat'] == hero) {
        prev = events[k];
        break;
      }
    }
    if (e['guess'] == true || (prev != null && prev['type'] == 'draw' && prev['guess'] == true)) out.add(turn);
  }
  return out;
}

Set<int> _reviewGuessed(Map<String, dynamic> j) {
  final r = reviewPaifu(Paifu.fromJson(j));
  return {
    for (var i = 0; i < r.turns.length; i++)
      if (r.turns[i].status == ReviewStatus.guessed) i + 1,
  };
}

void main() {
  final f = File(_path);
  final skip = f.existsSync() ? false : '$_path 없음(자동 확정 실행 결과 — 커밋하지 않는 파일)';

  test('자동 확정이 단 순은 guessed, 나머지 순은 전처럼', () {
    final j = jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
    final ac = j['auto_confirm'] as Map<String, dynamic>;
    final autoTurns = {for (final k in (ac['turns'] as Map<String, dynamic>).keys) int.parse(k)};
    expect(autoTurns, isNotEmpty);
    // 앱이 guessed 로 둔 순 = JSON 에서 guess 가 달린 순, 그리고 자동 확정 순은 모두 그 안에.
    expect(_reviewGuessed(j), _guessedTurns(j));
    expect(_reviewGuessed(j).containsAll(autoTurns), isTrue);
    // 자동 확정이 단 표시(marked)를 걷으면 그 순(원래 짐작이 아닌 것)은 guessed 가 아님.
    final stripped = jsonDecode(jsonEncode(j)) as Map<String, dynamic>;
    final ev = (stripped['events'] as List).cast<Map<String, dynamic>>();
    for (final i in (ac['marked'] as List).cast<int>()) {
      ev[i].remove('guess');
    }
    final before = _reviewGuessed(stripped);
    final onlyAuto = autoTurns.difference(before);
    expect(onlyAuto, isNotEmpty);
    expect(before.intersection(onlyAuto), isEmpty);
    expect(_reviewGuessed(j).difference(before), onlyAuto);
  }, skip: skip);
}
