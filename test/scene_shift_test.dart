import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/corner_change.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/observation.dart';
import 'package:mahjong_calc/table/river_change.dart';
import 'package:mahjong_calc/table/river_tracker.dart';
import 'package:mahjong_calc/table/scene_shift.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/table_reading.dart';
import 'package:mahjong_calc/table/tracker.dart';

/// 장면 전체 변화(카메라 움직임·조명) 검사와 추적기 기준 다시 잡기. 합성 탁자 그림(무늬 있는 펠트 + 강·모서리 패).
void main() {
  const grid = GridZones.initial;
  const w = 1024, h = 768;

  img.Image table({Set<Side> extraDiscard = const {}, NormBox? hand, double bright = 1, double dx = 0}) {
    final rnd = math.Random(7);
    final im = img.Image(width: w, height: h);
    // 무늬 있는 펠트(카메라가 움직이면 블록 밝기가 바뀌도록).
    for (var y = 0; y < h; y++) {
      for (var x = 0; x < w; x++) {
        final v = rnd.nextInt(60);
        im.setPixelRgb(x, y, 30 + v ~/ 2, 90 + v, 50 + v ~/ 2);
      }
    }
    void tiles(NormBox b, int n) {
      final r = b.toPixels(w, h);
      final tw = (w * 0.025).round(), th = (h * 0.044).round();
      final perRow = math.max(1, (r.width - 8) ~/ (tw + 3));
      for (var i = 0; i < n; i++) {
        final x0 = r.x + 4 + (i % perRow) * (tw + 3), y0 = r.y + 4 + (i ~/ perRow) * (th + 4);
        if (y0 + th > r.y + r.height) break;
        img.fillRect(im, x1: x0, y1: y0, x2: x0 + tw, y2: y0 + th, color: img.ColorRgb8(235, 235, 230));
        img.fillRect(im, x1: x0 + 6, y1: y0 + 8, x2: x0 + tw - 6, y2: y0 + 14, color: img.ColorRgb8(40, 40, 40));
      }
    }

    for (final s in Side.values) {
      tiles(grid.riverBand(s), extraDiscard.contains(s) ? 6 : 5);
      tiles(grid.cornerCell(s), 30); // 모서리 칸은 실제 사진에서 손패·패산·울기로 절반쯤 흰 면
    }
    if (hand != null) {
      final r = hand.toPixels(w, h);
      img.fillRect(im, x1: r.x, y1: r.y, x2: r.x + r.width, y2: r.y + r.height, color: img.ColorRgb8(200, 150, 120));
    }
    var out = im;
    if (dx != 0) {
      final s = (w * dx).round();
      out = img.Image(width: w, height: h);
      for (var y = 0; y < h; y++) {
        for (var x = 0; x < w; x++) {
          out.setPixel(x, y, im.getPixel((x - s).clamp(0, w - 1), y));
        }
      }
    }
    if (bright != 1) {
      for (final p in out) {
        p
          ..r = (p.r * bright).clamp(0, 255)
          ..g = (p.g * bright).clamp(0, 255)
          ..b = (p.b * bright).clamp(0, 255);
      }
    }
    return out;
  }

  TableFrameStats statsOf(img.Image im) =>
      analyzeTableFrame((Uint8List.fromList(img.encodeJpg(im, quality: 90)), grid));

  final base = statsOf(table());

  group('SceneShiftGate', () {
    test('같은 장면·버림 한 장·손 하나는 장면 변화가 아니다', () {
      final g = SceneShiftGate();
      expect(g.check(base), isFalse); // 첫 프레임
      expect(g.check(statsOf(table())), isFalse);
      expect(g.check(statsOf(table(extraDiscard: {Side.bottom}))), isFalse);
      // 손: 아래 강 + 가운데 리치봉 띠를 가림.
      expect(g.check(statsOf(table(hand: const NormBox(430, 420, 700, 600)))), isFalse, reason: g.summary);
    });

    test('카메라가 5% 움직이거나 밝기가 10% 바뀌면 장면 변화', () {
      final g = SceneShiftGate()..check(base);
      expect(g.check(statsOf(table(dx: 0.05))), isTrue, reason: g.summary);
      final g2 = SceneShiftGate()..check(base);
      expect(g2.check(statsOf(table(bright: 0.9))), isTrue, reason: g2.summary);
    });

    test('reset 뒤 첫 프레임은 비교하지 않는다', () {
      final g = SceneShiftGate()..check(base);
      g.reset();
      expect(g.check(statsOf(table(dx: 0.04))), isFalse);
    });
  });

  group('추적기 cameraMoved', () {
    final t0 = DateTime(2026, 10, 28, 14);
    DateTime at(int sec) => t0.add(Duration(seconds: sec));

    /// 프레임을 3초 간격으로 넣고, [gate] 가 있으면 장면 변화 때 두 추적기 기준을 다시 잡는다. (모서리 읽기 요청 수, 리치봉 읽기 요청 수).
    (int, int) run(List<TableFrameStats> frames, MeldTracker mt, RiverTracker rt, {SceneShiftGate? gate}) {
      var corner = 0, sticks = 0;
      for (var i = 0; i < frames.length; i++) {
        final now = at(i * 3);
        if (gate != null && gate.check(frames[i])) {
          mt.cameraMoved(now);
          rt.cameraMoved(now);
        }
        corner += mt.onFrame(frames[i].corners, now).length;
        sticks += rt.onFrame(frames[i].rivers, frames[i].strips, now).length;
      }
      return (corner, sticks);
    }

    test('카메라가 움직여 자리 잡으면: 검사 없이는 헛 사건, 검사가 있으면 없음', () {
      final moved = statsOf(table(dx: 0.05, bright: 0.92));
      final frames = [base, base, base, moved, moved, moved, moved];

      final mt0 = MeldTracker(tileFrac: tileFracsOf(grid));
      final rt0 = RiverTracker(tileFrac: riverTileFracsOf(grid));
      final (c0, s0) = run(frames, mt0, rt0);
      final noisy = c0 + s0 + rt0.discardCounts.values.fold(0, (a, b) => a + b);
      expect(noisy, greaterThan(0), reason: '검사가 없으면 헛 사건이 나야 이 시험이 뜻이 있다');

      final mt = MeldTracker(tileFrac: tileFracsOf(grid));
      final rt = RiverTracker(tileFrac: riverTileFracsOf(grid));
      final (c, s) = run(frames, mt, rt, gate: SceneShiftGate());
      expect(c, 0);
      expect(s, 0);
      expect(rt.discardCounts.values.every((n) => n == 0), isTrue);
      expect(rt.lastDiscard, isNull);
    });

    test('기준을 다시 잡은 뒤에도 진짜 버림은 잡는다', () {
      final moved = statsOf(table(dx: 0.05));
      final movedDiscard = statsOf(table(dx: 0.05, extraDiscard: {Side.right}));
      final rt = RiverTracker(tileFrac: riverTileFracsOf(grid));
      final mt = MeldTracker(tileFrac: tileFracsOf(grid));
      run([base, base, moved, moved, movedDiscard, movedDiscard, movedDiscard], mt, rt, gate: SceneShiftGate());
      expect(rt.lastDiscard?.side, Side.right);
      expect(rt.discardCounts[Side.right], 1);
    });

    test('확정한 울기·버림·리치봉은 남기고 읽는 중인 요청은 버린다', () {
      final mt = MeldTracker(tileFrac: {for (final s in Side.values) s: 0.1});
      final seat = mt.seat(Side.bottom);
      final meld = ObservedMeld([for (final x in ['6m', '7m', '8m']) ReadTile.fromCode(x, 1)!]);
      seat
        ..melds = [meld]
        ..status = TrackStatus.confirmed;
      final left = mt.seat(Side.left)
        ..status = TrackStatus.reading
        ..pendingFrame = 5;
      mt.cameraMoved(at(0));
      expect(mt.trackedMelds(Side.bottom), [meld]);
      expect(left.status, TrackStatus.idle);
      mt.onRead(Side.left, 5, [meld], at(1)); // 늦게 온 답
      expect(mt.trackedMelds(Side.left), isNull);
      expect(mt.events.last.kind, 'rebase');

      final rt = RiverTracker(tileFrac: riverTileFracsOf(grid));
      final d = Discard(side: Side.top, box: null, seq: 1, at: at(0), tiles: 1);
      rt.rivers[Side.top]!
        ..lastDiscard = d
        ..discards = 3;
      rt.riichi = {Side.left};
      rt.sticks
        ..status = StickStatus.reading
        ..pendingFrame = 7;
      rt.cameraMoved(at(2));
      expect(rt.lastDiscard, d);
      expect(rt.discardCounts[Side.top], 3);
      expect(rt.riichi, {Side.left});
      expect(rt.sticks.status, StickStatus.confirmed);
      rt.onSticksRead(7, {Side.right: true}, at(3)); // 늦게 온 답
      expect(rt.riichi, {Side.left});
    });
  });

  test('밝기 바뀐 강 띠는 블록 대부분이 같은 방향일 때만 센다', () {
    expect(brightShiftedRivers(base, statsOf(table(bright: 0.85))), 4);
    expect(brightShiftedRivers(base, base), 0);
    // 가운데로 뻗은 손은 네 강 띠의 안쪽 끝만 가린다.
    expect(brightShiftedRivers(base, statsOf(table(hand: const NormBox(380, 420, 520, 600)))), 0);
  });
}
