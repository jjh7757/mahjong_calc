import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/river_change.dart';
import 'package:mahjong_calc/table/river_tracker.dart';
import 'package:mahjong_calc/table/table_layout.dart';

/// 강·리치봉 추적기 상태 기계. 스냅샷은 손으로 만든다(블록 8×4, 패 한 장 = 블록 2개 = 띠의 1/16).
void main() {
  const grid = GridZones.initial;
  const cols = 8, rows = 4;
  final frac = {for (final s in Side.values) s: 2 / (cols * rows)};

  /// [whiteBlocks] 가 흰 블록, 나머지는 펠트(밝기 80). [brightAll] 이면 전부 그 밝기(손, 프레임마다 조금씩 다름).
  ZoneSnapshot snap(Side side, Set<int> whiteBlocks, {int? brightAll, int grayShift = 0}) {
    final gray = Uint8List(cols * rows);
    final white = Uint8List(cols * rows);
    for (var i = 0; i < gray.length; i++) {
      final w = whiteBlocks.contains(i);
      white[i] = w ? 1 : 0;
      gray[i] = brightAll ?? (w ? 240 : 80 + grayShift);
    }
    return ZoneSnapshot(
      box: grid.riverBand(side),
      cols: cols,
      rows: rows,
      gray: gray,
      white: white,
      whiteFrac: whiteBlocks.length / (cols * rows),
    );
  }

  Map<Side, ZoneSnapshot> rivers({Set<int> bottom = const {}, int? hand}) =>
      {for (final s in Side.values) s: snap(s, s == Side.bottom ? bottom : const {}, brightAll: s == Side.bottom ? hand : null)};
  Map<Side, ZoneSnapshot> strips({int shift = 0}) => {for (final s in Side.values) s: snap(s, const {}, grayShift: shift)};

  final t0 = DateTime(2026, 10, 28, 12);
  DateTime at(int sec) => t0.add(Duration(seconds: sec));

  test('패가 한 장 늘어 두 프레임 안정이면 버림으로 기록하고 위치 상자를 둔다', () {
    final tr = RiverTracker(tileFrac: frac);
    const two = {0, 1};
    tr.onFrame(rivers(bottom: two), strips(), at(0)); // 기준
    tr.onFrame(rivers(bottom: two), strips(), at(3));
    expect(tr.lastDiscard, isNull);
    const three = {0, 1, 2, 3};
    tr.onFrame(rivers(bottom: three), strips(), at(6)); // 바뀐 첫 프레임(직전과 다름 → 안정 0)
    expect(tr.lastDiscard, isNull);
    tr.onFrame(rivers(bottom: three), strips(), at(9)); // 두 프레임 안정
    final d = tr.lastDiscard!;
    expect(d.side, Side.bottom);
    expect(d.tiles, closeTo(1.0, 0.01));
    expect(d.box, isNotNull);
    expect(tr.discardCounts[Side.bottom], 1);
    // 기준이 갱신돼 같은 프레임이 이어져도 다시 세지 않는다.
    tr.onFrame(rivers(bottom: three), strips(), at(12));
    expect(tr.discardCounts[Side.bottom], 1);
  });

  test('손이 지나가는 동안은 세지 않고, 패가 사라지면 마지막 버림을 버린다', () {
    final tr = RiverTracker(tileFrac: frac);
    const two = {0, 1};
    tr.onFrame(rivers(bottom: two), strips(), at(0));
    tr.onFrame(rivers(bottom: two), strips(), at(3));
    tr.onFrame(rivers(bottom: two, hand:200), strips(), at(6));
    tr.onFrame(rivers(bottom: {0, 1, 2, 3}, hand:170), strips(), at(9)); // 손이 움직이는 중(밝기 다름)
    expect(tr.lastDiscard, isNull);
    tr.onFrame(rivers(bottom: {0, 1, 2, 3}), strips(), at(12));
    tr.onFrame(rivers(bottom: {0, 1, 2, 3}), strips(), at(15));
    expect(tr.lastDiscard, isNotNull);
    // 다른 사람이 울어 가져감(패 1장 줄어듦). 줄어듦은 손이 머문 것일 수 있어 한 프레임 더(3프레임) 기다린다.
    tr.onFrame(rivers(bottom: two), strips(), at(18));
    tr.onFrame(rivers(bottom: two), strips(), at(21));
    expect(tr.lastDiscard, isNotNull);
    tr.onFrame(rivers(bottom: two), strips(), at(24));
    expect(tr.lastDiscard, isNull);
    expect(tr.events.last.kind, 'taken');
  });

  test('강이 비면 새 판으로 보고 버림 수를 0 으로', () {
    final tr = RiverTracker(tileFrac: frac);
    const six = {0, 1, 2, 3, 4, 5};
    tr.onFrame(rivers(bottom: six), strips(), at(0));
    tr.onFrame(rivers(bottom: {0, 1, 2, 3, 4, 5, 6, 7}), strips(), at(3));
    tr.onFrame(rivers(bottom: {0, 1, 2, 3, 4, 5, 6, 7}), strips(), at(6));
    expect(tr.discardCounts[Side.bottom], 1);
    tr.onFrame(rivers(), strips(), at(9));
    tr.onFrame(rivers(), strips(), at(12));
    tr.onFrame(rivers(), strips(), at(15)); // 줄어듦은 3프레임
    expect(tr.discardCounts[Side.bottom], 0);
    expect(tr.events.last.kind, 'cleared');
  });

  const withSticks = RiverTrackerConfig();

  test('리치봉 추적은 기본으로 켜져 있고, 끄면 띠가 바뀌어도 읽지 않는다', () {
    expect(const RiverTrackerConfig().trackSticks, isTrue);
    final tr = RiverTracker(tileFrac: frac, config: const RiverTrackerConfig(trackSticks: false));
    for (var i = 0; i < 4; i++) {
      expect(tr.onFrame(rivers(), strips(shift: i < 2 ? 0 : 40), at(i * 3)), isEmpty);
    }
    expect(tr.sticks.status, StickStatus.idle);
  });

  test('첫 버림(자기 1장·전체 4장 이하) 뒤 리치봉이 확정되면 더블리치 후보, 세 번째 버림 뒤면 아니다', () {
    void run({required int discards, required bool expectCandidate}) {
      final tr = RiverTracker(tileFrac: frac, config: withSticks);
      tr.onFrame(rivers(), strips(), at(0));
      tr.onFrame(rivers(), strips(), at(3));
      var t = 6;
      var blocks = <int>{};
      for (var i = 0; i < discards; i++) {
        blocks = {...blocks, 2 * i, 2 * i + 1};
        tr.onFrame(rivers(bottom: blocks), strips(), at(t));
        tr.onFrame(rivers(bottom: blocks), strips(), at(t + 3));
        t += 6;
      }
      expect(tr.discardCounts[Side.bottom], discards);
      // 리치봉이 꽂힘 → 두 읽기로 확정.
      tr.onFrame(rivers(bottom: blocks), strips(shift: 40), at(t));
      final a1 = tr.onFrame(rivers(bottom: blocks), strips(shift: 40), at(t + 3));
      expect(a1.length, 1);
      tr.onSticksRead(a1.single.frame, {Side.bottom: true, Side.top: false, Side.left: false, Side.right: false}, at(t + 4));
      final a2 = tr.onFrame(rivers(bottom: blocks), strips(shift: 40), at(t + 9));
      expect(a2.length, 1);
      tr.onSticksRead(a2.single.frame, {Side.bottom: true, Side.top: false, Side.left: false, Side.right: false}, at(t + 10));
      expect(tr.riichi, {Side.bottom});
      expect(tr.riichiAt[Side.bottom]?.own, discards);
      expect(tr.doubleRiichiCandidates, expectCandidate ? {Side.bottom} : isEmpty);
      expect((tr.toJson()['double_riichi'] as List).isNotEmpty, expectCandidate);
      tr.reset(at(t + 20));
      expect(tr.riichiAt, isEmpty);
      expect(tr.doubleRiichiCandidates, isEmpty);
    }

    run(discards: 1, expectCandidate: true);
    run(discards: 3, expectCandidate: false);
  });

  /// 아래 자리 버림 [before] 장 뒤 리치. [tileLate] 면 선언패가 리치봉보다 한 프레임 늦게 잡힌다.
  /// 확정까지 마친 추적기와 다음 시각을 돌려준다.
  ({RiverTracker tr, int t, Set<int> blocks}) riichiAfter(int before, {bool tileLate = false}) {
    final tr = RiverTracker(tileFrac: frac, config: withSticks);
    tr.onFrame(rivers(), strips(), at(0));
    tr.onFrame(rivers(), strips(), at(3));
    var t = 6;
    var blocks = <int>{};
    for (var i = 0; i < before; i++) {
      blocks = {...blocks, 2 * i, 2 * i + 1};
      tr.onFrame(rivers(bottom: blocks), strips(), at(t));
      tr.onFrame(rivers(bottom: blocks), strips(), at(t + 3));
      t += 6;
    }
    // 선언패 + 리치봉.
    final withTile = {...blocks, 2 * before, 2 * before + 1};
    tr.onFrame(rivers(bottom: tileLate ? blocks : withTile), strips(shift: 40), at(t));
    final a1 = tr.onFrame(rivers(bottom: tileLate ? blocks : withTile), strips(shift: 40), at(t + 3));
    tr.onSticksRead(a1.single.frame, {Side.bottom: true, Side.top: false, Side.left: false, Side.right: false}, at(t + 4));
    if (tileLate) tr.onFrame(rivers(bottom: withTile), strips(shift: 40), at(t + 6)); // 손이 강 위에 남아 한 프레임 늦게
    final a2 = tr.onFrame(rivers(bottom: withTile), strips(shift: 40), at(t + 9));
    tr.onSticksRead(a2.single.frame, {Side.bottom: true, Side.top: false, Side.left: false, Side.right: false}, at(t + 10));
    expect(tr.riichi, {Side.bottom});
    return (tr: tr, t: t + 12, blocks: withTile);
  }

  test('리치 시점의 수는 확정이 아니라 띠가 바뀐 순간 것이고, 선언패가 늦게 잡혀도 선언패로 센다', () {
    for (final late in [false, true]) {
      final r = riichiAfter(0, tileLate: late);
      expect(r.tr.riichiAt[Side.bottom]!.own, 1, reason: 'tileLate=$late');
      expect(r.tr.doubleRiichiCandidates, {Side.bottom});
      expect(r.tr.ippatsuCandidates(), {Side.bottom});
    }
  });

  test('판 중간에 추적을 시작해 빈 강을 못 봤으면 버림 1장 뒤 리치여도 더블리치 후보가 아니다(일발은 그대로)', () {
    final tr = RiverTracker(tileFrac: frac, config: withSticks);
    const old = {0, 1, 2, 3, 4, 5}; // 이미 3장 버려진 강에서 시작
    tr.onFrame(rivers(bottom: old), strips(), at(0));
    tr.onFrame(rivers(bottom: old), strips(), at(3));
    const withTile = {0, 1, 2, 3, 4, 5, 6, 7};
    tr.onFrame(rivers(bottom: withTile), strips(shift: 40), at(6));
    final a1 = tr.onFrame(rivers(bottom: withTile), strips(shift: 40), at(9));
    tr.onSticksRead(a1.single.frame, {Side.bottom: true, Side.top: false, Side.left: false, Side.right: false}, at(10));
    final a2 = tr.onFrame(rivers(bottom: withTile), strips(shift: 40), at(15));
    tr.onSticksRead(a2.single.frame, {Side.bottom: true, Side.top: false, Side.left: false, Side.right: false}, at(16));
    expect(tr.riichiAt[Side.bottom]!.own, 1);
    expect(tr.riichiAt[Side.bottom]!.fresh, isFalse);
    expect(tr.doubleRiichiCandidates, isEmpty);
    expect(tr.ippatsuCandidates(), {Side.bottom});
  });

  test('일발 후보: 리치 뒤 그 자리가 또 버리거나, 누가 강에서 가져가거나, 울기가 늘면 아니다', () {
    // 또 버림.
    var r = riichiAfter(2);
    expect(r.tr.ippatsuCandidates(), {Side.bottom});
    expect(r.tr.doubleRiichiCandidates, isEmpty);
    final more = {...r.blocks, 6, 7};
    r.tr.onFrame(rivers(bottom: more), strips(shift: 40), at(r.t + 20));
    r.tr.onFrame(rivers(bottom: more), strips(shift: 40), at(r.t + 23));
    expect(r.tr.discardCounts[Side.bottom], 4);
    expect(r.tr.ippatsuCandidates(), isEmpty);
    expect(r.tr.riichi, {Side.bottom}); // 리치는 그대로

    // 다른 사람이 울어 감(강 패가 하나 줄어듦, 세 프레임).
    r = riichiAfter(2);
    final fewer = r.blocks.difference({4, 5});
    for (var i = 0; i < 3; i++) {
      r.tr.onFrame(rivers(bottom: fewer), strips(shift: 40), at(r.t + 20 + 3 * i));
    }
    expect(r.tr.events.last.kind, 'taken');
    expect(r.tr.ippatsuCandidates(), isEmpty);

    // 안깡 등 강에 안 보이는 울기: 울기 추적이 리치 뒤에 늘었다고 알려 주면 아니다.
    r = riichiAfter(2);
    final riichiTime = r.tr.riichiAt[Side.bottom]!.at;
    expect(r.tr.ippatsuCandidates(meldGrewSince: (t) => !t.isAfter(riichiTime)), isEmpty);
    expect(r.tr.ippatsuCandidates(meldGrewSince: (_) => false), {Side.bottom});
    expect((r.tr.toJson()['ippatsu'] as List), ['bottom']);
  });

  test('리치봉 띠가 바뀌면 읽기를 요청하고 두 읽기가 같으면 확정', () {
    final tr = RiverTracker(tileFrac: frac, config: withSticks);
    tr.onFrame(rivers(), strips(), at(0));
    expect(tr.onFrame(rivers(), strips(), at(3)), isEmpty);
    // 띠 밝기가 바뀜(막대가 꽂힘).
    expect(tr.onFrame(rivers(), strips(shift: 40), at(6)), isEmpty); // 직전과 다름 → 안정 0
    final a1 = tr.onFrame(rivers(), strips(shift: 40), at(9));
    expect(a1.length, 1);
    tr.onSticksRead(a1.single.frame, {Side.bottom: true, Side.top: false, Side.left: false, Side.right: false}, at(10));
    expect(tr.riichi, isEmpty); // 아직 한 번
    expect(tr.sticks.status, StickStatus.changed);
    // 5초 간격 뒤 두 번째 읽기.
    expect(tr.onFrame(rivers(), strips(shift: 40), at(12)), isEmpty); // 간격 미달
    final a2 = tr.onFrame(rivers(), strips(shift: 40), at(15));
    expect(a2.length, 1);
    tr.onSticksRead(a2.single.frame, {Side.bottom: true, Side.top: false, Side.left: false, Side.right: false}, at(16));
    expect(tr.riichi, {Side.bottom});
    expect(tr.sticks.status, StickStatus.confirmed);
    // 확정 뒤 같은 띠면 더 읽지 않는다.
    expect(tr.onFrame(rivers(), strips(shift: 40), at(20)), isEmpty);
    expect(tr.onFrame(rivers(), strips(shift: 40), at(23)), isEmpty);
  });

  test('띠 평균은 거의 그대로여도 몇 블록이 크게 바뀌면(홈에 꽂은 파란 리치봉) 읽기를 요청한다', () {
    Map<Side, ZoneSnapshot> stripsStick() => {
          for (final s in Side.values)
            s: () {
              final z = snap(s, const {});
              if (s == Side.right) {
                for (final i in [3, 11, 19]) {
                  z.gray[i] = 140; // 펠트 80 → 140, 3/32 블록
                }
              }
              return z;
            }(),
        };
    expect(stripsStick()[Side.right]!.diff(strips()[Side.right]!), lessThan(0.04));
    final tr = RiverTracker(tileFrac: frac, config: withSticks);
    tr.onFrame(rivers(), strips(), at(0));
    tr.onFrame(rivers(), strips(), at(3));
    // 평균 차이가 움직임 문턱보다 작아 첫 프레임부터 안정으로 보고 바로 읽는다.
    expect(tr.onFrame(rivers(), stripsStick(), at(6)), hasLength(1));
    // 블록 비율 문턱을 높이면 읽지 않는다(평균 차이만으로는 못 잡음).
    final off = RiverTracker(tileFrac: frac, config: const RiverTrackerConfig(stickChangedFrac: 0.5));
    off.onFrame(rivers(), strips(), at(0));
    off.onFrame(rivers(), strips(), at(3));
    expect(off.onFrame(rivers(), stripsStick(), at(6)), isEmpty);
    expect(off.onFrame(rivers(), stripsStick(), at(9)), isEmpty);
  });

  test('늦은 답·다른 프레임 답은 무시하고, 셋 다 다르면 미확정', () {
    final tr = RiverTracker(tileFrac: frac, config: withSticks);
    tr.onFrame(rivers(), strips(), at(0));
    tr.onFrame(rivers(), strips(), at(3));
    tr.onFrame(rivers(), strips(shift: 40), at(6));
    final a1 = tr.onFrame(rivers(), strips(shift: 40), at(9));
    tr.onSticksRead(a1.single.frame + 7, {Side.bottom: true}, at(10)); // 다른 프레임
    expect(tr.sticks.status, StickStatus.reading);
    tr.onSticksRead(a1.single.frame, {Side.bottom: true}, at(10));
    final a2 = tr.onFrame(rivers(), strips(shift: 40), at(15));
    tr.onSticksRead(a2.single.frame, {Side.top: true}, at(16));
    final a3 = tr.onFrame(rivers(), strips(shift: 40), at(21));
    expect(a3.length, 1);
    tr.onSticksRead(a3.single.frame, {Side.left: true}, at(22));
    expect(tr.sticks.status, StickStatus.unconfirmed);
    expect(tr.riichi, isEmpty);
    expect(tr.onFrame(rivers(), strips(shift: 40), at(27)), isEmpty);
  });

  test('reset 은 버림·리치봉을 비우고 기록을 남긴다', () {
    final tr = RiverTracker(tileFrac: frac);
    tr.onFrame(rivers(bottom: {0, 1}), strips(), at(0));
    tr.onFrame(rivers(bottom: {0, 1, 2, 3}), strips(), at(3));
    tr.onFrame(rivers(bottom: {0, 1, 2, 3}), strips(), at(6));
    expect(tr.lastDiscard, isNotNull);
    tr.riichi = {Side.top};
    tr.reset(at(9));
    expect(tr.lastDiscard, isNull);
    expect(tr.riichi, isEmpty);
    expect(tr.toJson()['events'], isNotEmpty);
  });
}
