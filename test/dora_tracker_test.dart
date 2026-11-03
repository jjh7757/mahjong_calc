import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/table/dora_tracker.dart';
import 'package:mahjong_calc/table/table_reading.dart';

/// 판 중 도라 표시패 확정(프레임 투표). 서버 없이 관측을 손으로 넣는다. 규칙은 experiments/tile_classifier/dora_rounds.py 와 같다.
void main() {
  final t0 = DateTime(2026, 11, 3, 10);
  DoraObservation obs(String code, double conf, {double cx = 400, double cy = 300, int sec = 0}) =>
      DoraObservation(cx: cx, cy: cy, tileWidth: 30, tile: ReadTile.fromCode(code, conf)!, at: t0.add(Duration(seconds: sec)));

  test('같은 자리에서 같은 패가 3번 읽히면 확정, 그 전엔 없음', () {
    final tr = DoraTracker();
    tr.observe(obs('5s', 0.9, sec: 0));
    expect(tr.confirmed, isNull);
    tr.observe(obs('5s', 0.8, sec: 10));
    expect(tr.confirmed, isNull);
    tr.observe(obs('5s', 0.95, sec: 20));
    final c = tr.confirmed!;
    expect(c.tile.code, '5s');
    expect(c.reads, 3);
    expect(c.share, 1.0);
    expect(c.at, t0.add(const Duration(seconds: 20)), reason: '세 번째 관측 때 확정');
    expect(c.tile.conf, 0.95, reason: '같은 종류 관측의 최댓값');
  });

  test('헛 관측 하나(손·다른 패)는 다수를 바꾸지 못하고, 몫이 60% 아래면 확정하지 않는다', () {
    final tr = DoraTracker();
    for (final c in ['5s', '6s', '5s', '5s']) {
      tr.observe(obs(c, 0.9));
    }
    expect(tr.confirmed!.tile.code, '5s');
    final split = DoraTracker();
    for (final c in ['5s', '6s', '5s', '6s', '5s']) {
      split.observe(obs(c, c == '5s' ? 0.7 : 0.95));
    }
    expect(split.confirmed, isNull, reason: '최근 5개 중 5s 3(2.1)·6s 2(1.9): 수는 되지만 몫 0.525 라 0.6 이 안 됨');
  });

  test('다른 위치의 관측은 다른 묶음: 최근 20 관측에서 더 많이 본 묶음이 지금 묶음', () {
    final tr = DoraTracker();
    for (var i = 0; i < 3; i++) {
      tr.observe(obs('5s', 0.9, cx: 400));
    }
    expect(tr.confirmed!.tile.code, '5s');
    tr.observe(obs('1z', 0.9, cx: 700));
    tr.observe(obs('1z', 0.9, cx: 700));
    expect(tr.confirmed!.tile.code, '5s', reason: '새 자리 관측 2개로는 안 바뀜');
    tr.observe(obs('1z', 0.9, cx: 700));
    expect(tr.confirmed!.tile.code, '1z', reason: '3 대 3 이면 최근 관측 쪽');
    expect(tr.clusters.length, 2);
  });

  test('화료 순간 탁자에 내놓은 짝(관측 3개)은 판 내내 본 패산 표시패(관측 10개)를 밀어내지 못한다', () {
    final tr = DoraTracker();
    for (var i = 0; i < 10; i++) {
      tr.observe(obs('7m', 0.9, cx: 300, cy: 400));
    }
    for (var i = 0; i < 3; i++) {
      tr.observe(obs('5s', 0.93, cx: 750, cy: 710));
    }
    expect(tr.confirmed!.tile.code, '7m');
  });

  test('기록 없이 판이 바뀌어 옛 패산이 더 안 보이면 새 묶음이 이긴다', () {
    final tr = DoraTracker(recent: 6);
    for (var i = 0; i < 10; i++) {
      tr.observe(obs('7m', 0.9, cx: 300));
    }
    for (var i = 0; i < 4; i++) {
      tr.observe(obs('1z', 0.9, cx: 700));
    }
    expect(tr.confirmed!.tile.code, '1z', reason: '최근 6 관측: 1z 4 · 7m 2');
  });

  test('같은 자리에 새 판의 패산이 오면 최근 창이 종류를 바꿔 준다', () {
    final tr = DoraTracker();
    for (var i = 0; i < 6; i++) {
      tr.observe(obs('5s', 0.9));
    }
    for (var i = 0; i < 2; i++) {
      tr.observe(obs('9p', 0.9));
    }
    expect(tr.confirmed!.tile.code, '5s', reason: '최근 5개: 5s 3·9p 2');
    tr.observe(obs('9p', 0.9));
    expect(tr.confirmed!.tile.code, '9p', reason: '최근 5개: 5s 2·9p 3');
  });

  test('reset 은 전부 비우고, 전판과 같은 자리·같은 패(아직 안 치운 패산)는 새 판 관측으로 받지 않는다', () {
    final tr = DoraTracker();
    for (var i = 0; i < 3; i++) {
      tr.observe(obs('5s', 0.9));
    }
    tr.reset();
    expect(tr.confirmed, isNull);
    expect(tr.clusters, isEmpty);
    expect(tr.observations, 0);
    for (var i = 0; i < 3; i++) {
      tr.observe(obs('5s', 0.9));
    }
    expect(tr.confirmed, isNull, reason: '전판 패산 그대로');
    for (var i = 0; i < 3; i++) {
      tr.observe(obs('7m', 0.9));
    }
    expect(tr.confirmed!.tile.code, '7m', reason: '같은 자리라도 패가 다르면 새 판');
    for (var i = 0; i < 3; i++) {
      tr.observe(obs('5s', 0.9, cx: 700));
    }
    expect(tr.clusters.length, 2, reason: '다른 자리의 5s 는 받는다');
  });

  test('서버 응답에서 관측 만들기: box 와 indicators 가 있어야 하고 짧은 변이 패 폭', () {
    final o = DoraObservation.fromJson({
      'indicators': [{'tile': '0s', 'conf': 0.93}],
      'box': [898, 1670, 127, 93],
    }, t0)!;
    expect(o.cx, 898 + 127 / 2);
    expect(o.cy, 1670 + 93 / 2);
    expect(o.tileWidth, 93);
    expect(o.tile.code, '0s');
    expect(o.tile.red, isTrue);
    expect(DoraObservation.fromJson({'indicators': [], 'box': null}, t0), isNull);
    expect(DoraObservation.fromJson({'indicators': [], 'box': [1, 2, 3, 4]}, t0), isNull, reason: '확신이 낮아 비운 답');
  });
}
