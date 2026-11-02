import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/table/corner_change.dart';
import 'package:mahjong_calc/table/observation.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/table_reading.dart';
import 'package:mahjong_calc/table/tracker.dart';

/// 판 상태 추적 상태 기계. 프레임 통계와 읽기 결과를 손으로 넣는다(픽셀·서버 없음).
/// 프레임은 3초마다 온다고 치고, 모서리에 패가 놓이는 순간의 프레임은 직전과 크게 달라 "움직임" 으로 잡힌다.
void main() {
  const frac = 0.01; // 패 한 장 = 모서리 칸의 1%
  final fracs = {for (final s in Side.values) s: frac};
  CornerStats st(double white) => CornerStats(white: white, pattern: white / 10, cx: 0.5, cy: 0.5);
  Map<Side, CornerStats> frameOf(double bottomWhite) => {for (final s in Side.values) s: st(s == Side.bottom ? bottomWhite : 0)};
  ObservedMeld pon(String code) => ObservedMeld([for (var i = 0; i < 3; i++) ReadTile.fromCode(code, 1)!]);
  ObservedMeld chi(String a, String b, String c) => ObservedMeld([for (final x in [a, b, c]) ReadTile.fromCode(x, 1)!]);
  final t0 = DateTime(2026, 10, 27, 15);
  DateTime at(int sec) => t0.add(Duration(seconds: sec));

  /// 모서리가 [white] 로 바뀌어 두 프레임([sec], [sec]+3) 동안 그대로. 둘째 프레임의 행동을 돌려준다.
  List<TrackerAction> settle(MeldTracker tr, double white, int sec) {
    expect(tr.onFrame(frameOf(white), at(sec)), isEmpty, reason: '바뀐 첫 프레임은 움직임');
    return tr.onFrame(frameOf(white), at(sec + 3));
  }

  test('변화가 없으면 아무것도 읽지 않는다', () {
    final tr = MeldTracker(tileFrac: fracs);
    for (var i = 0; i < 5; i++) {
      expect(tr.onFrame(frameOf(0), at(i * 3)), isEmpty);
    }
    expect(tr.seat(Side.bottom).status, TrackStatus.idle);
    expect(tr.trackedMelds(Side.bottom), isNull);
  });

  test('손이 지나가기만 하면(크게 변했다 돌아옴) 읽지 않고 idle 로 돌아온다', () {
    final tr = MeldTracker(tileFrac: fracs);
    expect(tr.onFrame(frameOf(0), at(0)), isEmpty);
    expect(tr.onFrame(frameOf(0.2), at(3)), isEmpty);
    expect(tr.seat(Side.bottom).status, TrackStatus.moving);
    expect(settle(tr, 0, 6), isEmpty);
    expect(tr.seat(Side.bottom).status, TrackStatus.idle);
  });

  test('퐁을 놓으면 읽기를 요청하고, 읽은 장수가 픽셀 어림과 맞으면 한 번으로 확정한다', () {
    final tr = MeldTracker(tileFrac: fracs);
    tr.onFrame(frameOf(0), at(0));
    final a = settle(tr, 0.03, 3); // 패 3장 분량
    expect(a, hasLength(1));
    expect(a.first.side, Side.bottom);
    expect(tr.seat(Side.bottom).status, TrackStatus.reading);
    expect(tr.trackedMelds(Side.bottom), isNull);
    expect(tr.events.last.kind, 'changed');

    tr.onRead(Side.bottom, a.first.frame, [pon('5m')], at(7));
    expect(tr.seat(Side.bottom).status, TrackStatus.confirmed);
    expect(tr.trackedMelds(Side.bottom), hasLength(1));
    expect(tr.events.last.kind, 'confirmed');
    expect(tr.events.last.detail, contains('픽셀 장수 일치'));
    // 울기가 는 시각(일발 깨짐 판정용).
    expect(tr.seat(Side.bottom).grewAt, at(7));
    expect(tr.grewSince(at(6)), isTrue);
    expect(tr.grewSince(at(7)), isFalse);
    // 그 뒤 같은 프레임이 이어져도 다시 읽지 않는다.
    expect(tr.onFrame(frameOf(0.03), at(9)), isEmpty);
    expect(tr.onFrame(frameOf(0.03), at(12)), isEmpty);
    expect(tr.trackedMelds(Side.bottom), hasLength(1));
  });

  test('픽셀 지름길이 없으면 다른 프레임의 두 읽기가 같아야 확정하고, 읽기 간격을 지킨다', () {
    final tr = MeldTracker(tileFrac: fracs, config: const TrackerConfig(pixelShortcut: false));
    tr.onFrame(frameOf(0), at(0));
    final a1 = settle(tr, 0.03, 3); // 읽기 요청 시각 6초
    expect(a1, hasLength(1));
    tr.onRead(Side.bottom, a1.first.frame, [pon('5m')], at(7));
    expect(tr.seat(Side.bottom).status, TrackStatus.changed); // 후보만
    expect(tr.trackedMelds(Side.bottom), isNull);
    expect(tr.onFrame(frameOf(0.03), at(9)), isEmpty); // 5초 안 → 기다림
    final a2 = tr.onFrame(frameOf(0.03), at(12));
    expect(a2, hasLength(1));
    tr.onRead(Side.bottom, a2.first.frame, [pon('5m')], at(13));
    expect(tr.seat(Side.bottom).status, TrackStatus.confirmed);
    expect(tr.events.last.detail, contains('두 읽기 일치'));
  });

  test('세 번 읽어도 다 다르면 unconfirmed 가 되고 더 읽지 않는다', () {
    final tr = MeldTracker(tileFrac: fracs, config: const TrackerConfig(pixelShortcut: false));
    tr.onFrame(frameOf(0), at(0));
    var a = settle(tr, 0.03, 3);
    var now = 6;
    for (final m in [pon('5m'), pon('6m'), chi('1s', '2s', '3s')]) {
      expect(a, hasLength(1), reason: 'read at $now');
      tr.onRead(Side.bottom, a.first.frame, [m], at(now + 1));
      now += 6;
      a = tr.onFrame(frameOf(0.03), at(now));
    }
    expect(tr.seat(Side.bottom).status, TrackStatus.unconfirmed);
    expect(a, isEmpty);
    expect(tr.onFrame(frameOf(0.03), at(now + 6)), isEmpty);
    expect(tr.trackedMelds(Side.bottom), isNull);
  });

  test('확정 뒤 모서리가 또 바뀌면 확정값을 믿지 않고, 확정보다 적게 읽히면(가림) 받지 않는다', () {
    final tr = MeldTracker(tileFrac: fracs);
    tr.onFrame(frameOf(0), at(0));
    final a1 = settle(tr, 0.03, 3);
    tr.onRead(Side.bottom, a1.first.frame, [pon('5m')], at(7));
    expect(tr.trackedMelds(Side.bottom), hasLength(1));

    // 두 번째 울기(치)가 더 놓임: 6장 분량.
    final a2 = settle(tr, 0.06, 12);
    expect(a2, hasLength(1));
    expect(tr.trackedMelds(Side.bottom), isNull, reason: '바뀐 뒤엔 예전 확정을 안 씀');
    tr.onRead(Side.bottom, a2.first.frame, const [], at(16)); // 손이 가려 아무것도 못 읽음
    expect(tr.seat(Side.bottom).status, TrackStatus.changed);
    expect(tr.events.last.kind, 'fewer');

    final a3 = tr.onFrame(frameOf(0.06), at(21));
    expect(a3, hasLength(1));
    tr.onRead(Side.bottom, a3.first.frame, [pon('5m'), chi('1s', '2s', '3s')], at(22));
    expect(tr.seat(Side.bottom).status, TrackStatus.confirmed);
    expect(tr.trackedMelds(Side.bottom), hasLength(2));
  });

  test('적게 읽혀 unconfirmed 가 되면 모서리가 또 바뀌기 전엔 다시 읽지 않고(무한 재읽기 없음), 바뀌면 다시 읽는다', () {
    final tr = MeldTracker(tileFrac: fracs);
    tr.onFrame(frameOf(0), at(0));
    final a1 = settle(tr, 0.03, 3);
    tr.onRead(Side.bottom, a1.first.frame, [pon('5m')], at(7));
    expect(tr.trackedMelds(Side.bottom), hasLength(1));

    // 모서리가 또 바뀌었는데 서버는 세 번 다 "울기 없음"(확정보다 적음 = 가림·오독)으로 답한다.
    var acts = settle(tr, 0.06, 12);
    var sec = 16;
    for (var i = 0; i < 3; i++) {
      expect(acts, hasLength(1), reason: '${i + 1}번째 읽기');
      tr.onRead(Side.bottom, acts.first.frame, const [], at(sec));
      acts = tr.onFrame(frameOf(0.06), at(sec + 5));
      sec += 6;
    }
    expect(tr.seat(Side.bottom).status, TrackStatus.unconfirmed);
    expect(acts, isEmpty);

    // 같은 모서리가 5분 이어져도 더 읽지 않는다(예전엔 안정 프레임마다 "새 변화" 로 보고 5초마다 읽었다).
    var reads = 0;
    for (var s = sec; s < sec + 300; s += 3) {
      reads += tr.onFrame(frameOf(0.06), at(s)).length;
    }
    expect(reads, 0);
    expect(tr.trackedMelds(Side.bottom), isNull);

    // 모서리가 또 바뀌면(울기 하나 더) 새 변화로 읽고 확정한다.
    final a2 = settle(tr, 0.09, sec + 300);
    expect(a2, hasLength(1));
    tr.onRead(Side.bottom, a2.first.frame, [pon('5m'), chi('1s', '2s', '3s'), pon('9p')], at(sec + 304));
    expect(tr.seat(Side.bottom).status, TrackStatus.confirmed);
    expect(tr.trackedMelds(Side.bottom), hasLength(3));
  });

  test('후보를 들고 있는 동안 손이 지나가도 후보를 버리지 않고, 다음 안정 프레임의 두 번째 읽기로 확정한다', () {
    final tr = MeldTracker(tileFrac: fracs, config: const TrackerConfig(pixelShortcut: false));
    tr.onFrame(frameOf(0), at(0));
    final a1 = settle(tr, 0.03, 3);
    tr.onRead(Side.bottom, a1.first.frame, [pon('5m')], at(7)); // 후보
    expect(tr.onFrame(frameOf(0.2), at(9)), isEmpty); // 손
    expect(tr.seat(Side.bottom).status, TrackStatus.changed, reason: '움직임이 후보를 지우지 않는다');
    final a2 = settle(tr, 0.03, 12);
    expect(a2, hasLength(1));
    tr.onRead(Side.bottom, a2.first.frame, [pon('5m')], at(16));
    expect(tr.seat(Side.bottom).status, TrackStatus.confirmed);
    expect(tr.events.where((e) => e.kind == 'changed'), hasLength(1), reason: '같은 변화를 두 번 세지 않는다');
  });

  test('다른 프레임의 늦은 답은 무시하고, 읽기 실패는 다시 시도한다', () {
    final tr = MeldTracker(tileFrac: fracs);
    tr.onFrame(frameOf(0), at(0));
    final a = settle(tr, 0.03, 3);
    tr.onRead(Side.bottom, a.first.frame + 7, [pon('5m')], at(7));
    expect(tr.seat(Side.bottom).status, TrackStatus.reading);
    tr.onReadFailed(Side.bottom, a.first.frame, at(8), '시간 초과');
    expect(tr.seat(Side.bottom).status, TrackStatus.changed);
    final b = tr.onFrame(frameOf(0.03), at(12));
    expect(b, hasLength(1));
    tr.onRead(Side.bottom, b.first.frame, [pon('5m')], at(13));
    expect(tr.trackedMelds(Side.bottom), hasLength(1));
  });

  test('확정한 울기와 같게 읽히면 그 확정을 두 번째 읽기로 쳐 한 번에 확정한다', () {
    final tr = MeldTracker(tileFrac: fracs, config: const TrackerConfig(pixelShortcut: false));
    tr.onFrame(frameOf(0), at(0));
    final a1 = settle(tr, 0.03, 3);
    tr.onRead(Side.bottom, a1.first.frame, [pon('5m')], at(7));
    expect(tr.seat(Side.bottom).status, TrackStatus.changed, reason: '처음엔 두 읽기가 필요');
    final a2 = tr.onFrame(frameOf(0.03), at(12));
    tr.onRead(Side.bottom, a2.first.frame, [pon('5m')], at(13));
    expect(tr.seat(Side.bottom).status, TrackStatus.confirmed);
    // 모서리가 또 바뀌었지만 읽어 보니 같은 퐁 → 한 번에 확정(헛 변화).
    final a3 = settle(tr, 0.08, 15);
    expect(a3, hasLength(1));
    tr.onRead(Side.bottom, a3.first.frame, [pon('5m')], at(19));
    expect(tr.seat(Side.bottom).status, TrackStatus.confirmed);
    expect(tr.events.last.detail, contains('확정과 같음'));
    expect(tr.trackedMelds(Side.bottom), hasLength(1));
  });

  test('헛 변화(읽어 보니 울기 그대로)가 이어지면 다음 읽기를 두 배씩 미루고, 그동안 확정값은 믿지 않는다', () {
    // 2026-10-30 집 점검: 흰 천장의 노출 흔들림이 "패 1장 넘게 바뀜" 이 되어 30분에 모서리 읽기 28번.
    final tr = MeldTracker(tileFrac: fracs, config: const TrackerConfig(confirmReads: 1));
    expect(const TrackerConfig().idleBackoff(1), const Duration(seconds: 10));
    expect(const TrackerConfig().idleBackoff(3), const Duration(seconds: 40));
    expect(const TrackerConfig().idleBackoff(9), const Duration(minutes: 2));
    tr.onFrame(frameOf(0), at(0));
    final a1 = settle(tr, 0.04, 3);
    expect(a1, hasLength(1));
    tr.onRead(Side.bottom, a1.first.frame, const [], at(7)); // 헛 변화 1 → 10초 미룸(17초까지)
    expect(tr.seat(Side.bottom).idleStreak, 1);

    expect(settle(tr, 0.08, 9), isEmpty); // 또 바뀜(12초) — 미루는 중
    expect(tr.seat(Side.bottom).status, TrackStatus.changed);
    expect(tr.trackedMelds(Side.bottom), isNull, reason: '미루는 동안엔 확정값을 쓰지 않는다');
    expect(tr.onFrame(frameOf(0.08), at(15)), isEmpty);
    final a2 = tr.onFrame(frameOf(0.08), at(18));
    expect(a2, hasLength(1));
    tr.onRead(Side.bottom, a2.first.frame, const [], at(19)); // 헛 변화 2 → 20초(39초까지)
    expect(tr.seat(Side.bottom).idleStreak, 2);

    expect(settle(tr, 0.12, 21), isEmpty);
    for (var sec = 27; sec < 39; sec += 3) {
      expect(tr.onFrame(frameOf(0.12), at(sec)), isEmpty, reason: '$sec초');
    }
    final a3 = tr.onFrame(frameOf(0.12), at(39));
    expect(a3, hasLength(1));
    tr.onRead(Side.bottom, a3.first.frame, [pon('5m')], at(40)); // 진짜 울기 → 미루기 끝
    expect(tr.seat(Side.bottom).idleStreak, 0);
    expect(tr.seat(Side.bottom).backoffUntil, isNull);
    expect(tr.trackedMelds(Side.bottom), hasLength(1));
    // 다음 변화는 평소대로(읽기 간격 5초만) 바로 읽는다.
    expect(settle(tr, 0.2, 42), hasLength(1));
  });

  test('새 판이면 전부 비우고 다음 프레임을 기준으로 삼는다', () {
    final tr = MeldTracker(tileFrac: fracs);
    tr.onFrame(frameOf(0), at(0));
    final a = settle(tr, 0.03, 3);
    tr.onRead(Side.bottom, a.first.frame, [pon('5m')], at(7));
    tr.reset(at(30));
    expect(tr.trackedMelds(Side.bottom), isNull);
    expect(tr.seat(Side.bottom).status, TrackStatus.idle);
    // 울기가 치워진 빈 모서리가 새 기준.
    expect(settle(tr, 0, 33), isEmpty);
    expect(tr.seat(Side.bottom).status, TrackStatus.idle);
    expect(tr.events.where((e) => e.kind == 'reset'), hasLength(1));
    expect(tr.toJson()['seats'], isA<Map<String, dynamic>>());
  });

  test('pixelOnly: 읽기를 요청하지 않고 흰 면이 늘면 울기가 늘었다고 친다', () {
    final t = MeldTracker(tileFrac: {for (final s in Side.values) s: 0.1}, config: const TrackerConfig(pixelOnly: true));
    final t0 = DateTime(2026, 11, 2, 12);
    CornerStats st(double white) => CornerStats(white: white, pattern: 0, cx: 0.5, cy: 0.5);
    final actions = <TrackerAction>[];
    for (var i = 0; i < 4; i++) {
      actions.addAll(t.onFrame({Side.bottom: st(0.0)}, t0.add(Duration(seconds: 3 * i))));
    }
    final before = t0.add(const Duration(seconds: 10));
    for (var i = 4; i < 10; i++) {
      actions.addAll(t.onFrame({Side.bottom: st(0.3)}, t0.add(Duration(seconds: 3 * i))));
    }
    expect(actions, isEmpty);
    expect(t.grewSince(before), isTrue);
    expect(t.seat(Side.bottom).status, TrackStatus.idle);
    expect(t.trackedMelds(Side.bottom), isNull);
  });
}
