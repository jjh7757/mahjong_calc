import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/felt_grid.dart';
import 'package:mahjong_calc/table/mount_check.dart';
import 'package:mahjong_calc/table/rectify.dart' show FeltQuad;
import 'package:mahjong_calc/ui/mount/mount_check_dialog.dart';

math.Point<double> _pt(double x, double y) => math.Point(x, y);

/// 회색 바닥 위 초록 펠트(모서리 [felt], 비율 좌표 — 사진 밖으로 나가도 됨)와 남색 기기.
img.Image _photo(List<math.Point<double>> felt, {int w = 1020, int h = 765}) {
  final im = img.Image(width: w, height: h);
  img.fill(im, color: img.ColorRgb8(90, 90, 90));
  img.Point px(math.Point<double> p) => img.Point(p.x * w, p.y * h);
  img.fillPolygon(im, vertices: felt.map(px).toList(), color: img.ColorRgb8(25, 95, 65));
  final plane = FeltPlane.of(FeltQuad(felt[0], felt[1], felt[2], felt[3]))!;
  final dev = [plane.at(0.402, 0.403), plane.at(0.598, 0.403), plane.at(0.598, 0.597), plane.at(0.402, 0.597)];
  img.fillPolygon(im, vertices: dev.map(px).toList(), color: img.ColorRgb8(30, 40, 95));
  return im;
}

/// 가운데 (cx, cy), 한 변 [side](사진 세로 비율)인 정사각형 펠트를 [deg] 도 돌린 네 모서리(4:3 사진).
List<math.Point<double>> _square(double cx, double cy, double side, {double deg = 0}) {
  const aspect = 1020 / 765;
  final r = deg * math.pi / 180, hs = side / 2;
  return [
    for (final (dx, dy) in [(-hs, -hs), (hs, -hs), (hs, hs), (-hs, hs)])
      _pt(cx + (dx * math.cos(r) - dy * math.sin(r)) / aspect, cy + dx * math.sin(r) + dy * math.cos(r)),
  ];
}

MountItem _item(MountCheck c, String key) => c.items.firstWhere((i) => i.key == key);

void main() {
  group('거치 점검 판정', () {
    test('반듯하고 다 들어온 탁자: 전부 괜찮음', () {
      final c = checkMount(_photo(_square(0.5, 0.5, 0.74)), captureLongSide: 4080);
      expect(c.level, MountLevel.ok);
      expect(_item(c, 'frame').level, MountLevel.ok);
      expect(_item(c, 'frame').note, isEmpty);
      expect(c.tilt!.abs(), lessThan(0.5));
      // 한 변 = 세로의 0.74 → 3060 × 0.74 ≈ 2264px
      expect(c.feltPx, closeTo(2264, 30));
      expect(_item(c, 'size').level, MountLevel.ok);
      expect(c.advice, isEmpty);
    });

    test('펠트는 다 보이지만 흰 테두리가 사진 밖(지금 매장 거치): 괜찮음 + 알림', () {
      final c = checkMount(_photo(_square(0.5, 0.5, 0.92)), captureLongSide: 4080);
      expect(_item(c, 'frame').level, MountLevel.ok);
      expect(_item(c, 'frame').note, contains('위쪽·아래쪽'));
      expect(c.level, MountLevel.ok);
      expect(c.advice, isEmpty);
    });

    test('오른쪽이 사진 밖으로 잘림: 나쁨, 어느 쪽인지 말해 줌', () {
      final c = checkMount(_photo(_square(0.75, 0.5, 0.8)), captureLongSide: 4080);
      expect(c.touch![1], greaterThan(0.5));
      expect(c.touch![3], lessThan(mountTouchMin));
      final f = _item(c, 'frame');
      expect(f.level, MountLevel.bad);
      expect(f.value, contains('오른쪽'));
      expect(f.value, isNot(contains('왼쪽')));
      expect(c.level, MountLevel.bad);
      expect(c.advice.first, contains('오른쪽'));
    });

    test('탁자가 화면보다 큼(너무 가까움): 네 쪽 다 잘림', () {
      final c = checkMount(_photo(_square(0.5, 0.5, 1.6)), captureLongSide: 4080);
      expect(_item(c, 'frame').level, MountLevel.bad);
      expect(_item(c, 'frame').value, contains('위쪽·오른쪽·아래쪽·왼쪽'));
      expect(_item(c, 'frame').advice, startsWith('카메라를 더 높여'));
    });

    test('기울기: 6° 미만 괜찮음, 6~15° 주의, 15° 이상 나쁨 + 돌릴 방향', () {
      final a = checkMount(_photo(_square(0.5, 0.5, 0.6, deg: 4)));
      expect(a.tilt, closeTo(4, 0.5));
      expect(_item(a, 'tilt').level, MountLevel.ok);
      final b = checkMount(_photo(_square(0.5, 0.5, 0.6, deg: 10)));
      expect(b.tilt, closeTo(10, 0.5));
      expect(_item(b, 'tilt').level, MountLevel.caution);
      expect(_item(b, 'tilt').advice, contains('시계 방향'));
      expect(_item(b, 'tilt').advice, isNot(contains('반대')));
      final c = checkMount(_photo(_square(0.5, 0.5, 0.6, deg: -20)));
      expect(c.tilt, closeTo(-20, 0.7));
      expect(_item(c, 'tilt').level, MountLevel.bad);
      expect(_item(c, 'tilt').advice, contains('시계 반대 방향'));
      expect(c.level, MountLevel.bad);
    });

    test('패 크기: 촬영 크기를 알 때만, 작으면 주의·나쁨', () {
      final far = _photo(_square(0.5, 0.5, 0.6)); // 3060 × 0.6 = 1836px
      expect(checkMount(far).items.any((i) => i.key == 'size'), isFalse);
      final c = checkMount(far, captureLongSide: 4080);
      expect(c.feltPx, closeTo(1836, 30));
      expect(_item(c, 'size').level, MountLevel.caution);
      final tiny = checkMount(_photo(_square(0.5, 0.5, 0.45)), captureLongSide: 4080); // 1377px
      expect(_item(tiny, 'size').level, MountLevel.bad);
      // 정사각형 헤드(2992): 같은 비율이면 px 가 작다
      final sq = checkMount(_photo(_square(0.5, 0.5, 0.74), w: 1000, h: 1000), captureLongSide: 2992);
      expect(sq.feltPx, lessThan(2992 * 0.78));
    });

    test('펠트가 없으면 판정 안 함(나쁨이 아님)', () {
      final im = img.Image(width: 1020, height: 765);
      img.fill(im, color: img.ColorRgb8(90, 90, 90));
      final c = checkMount(im, captureLongSide: 4080);
      expect(c.level, MountLevel.unknown);
      expect(c.advice, isEmpty);
    });

    test('JPEG 입력: 긴 변을 안 주면 작은 미리보기는 패 크기를 건너뜀', () {
      final jpg = Uint8List.fromList(img.encodeJpg(_photo(_square(0.5, 0.5, 0.74)), quality: 90));
      expect(mountCheckOfJpeg((jpg, null)).items.any((i) => i.key == 'size'), isFalse);
      expect(mountCheckOfJpeg((jpg, 4080)).items.any((i) => i.key == 'size'), isTrue);
      expect(mountCheckOfJpeg((jpg, 4080)).toJson()['level'], 'ok');
    });
  });

  group('거치 점검 창', () {
    final jpg = Uint8List.fromList(img.encodeJpg(img.Image(width: 40, height: 30), quality: 80));
    MountCheck bad() => const MountCheck(touch: [0, 0.4, 0, 0], items: [
          MountItem('frame', MountLevel.bad, '탁자 전체', '사진의 오른쪽 쪽 펠트가 잘림', advice: '카메라를 사진의 오른쪽 쪽으로 옮기세요'),
        ]);
    MountCheck good() => const MountCheck(touch: [0, 0, 0, 0], items: [
          MountItem('frame', MountLevel.ok, '탁자 전체', '펠트 네 변 다 보임'),
          MountItem('tilt', MountLevel.ok, '기울기', '+0.4°'),
        ]);

    Future<void> open(WidgetTester tester, {required bool live, required Future<MountCheck> Function(Uint8List, int?) check}) async {
      await tester.pumpWidget(MaterialApp(
        home: Builder(
          builder: (ctx) => TextButton(
            onPressed: () => showMountCheck(ctx, fetch: () async => jpg, live: live, check: check),
            child: const Text('열기'),
          ),
        ),
      ));
      await tester.tap(find.text('열기'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));
    }

    testWidgets('결과와 고칠 방법을 보여 주고, 다시 재면 바뀐다', (tester) async {
      var n = 0;
      await open(tester, live: false, check: (_, _) async => n++ == 0 ? bad() : good());
      expect(find.byKey(const ValueKey('mount-check-level-bad')), findsOneWidget);
      expect(find.text('탁자 전체: 사진의 오른쪽 쪽 펠트가 잘림'), findsOneWidget);
      expect(find.text('카메라를 사진의 오른쪽 쪽으로 옮기세요'), findsOneWidget);
      expect(find.byKey(const ValueKey('mount-check-live')), findsNothing);

      await tester.tap(find.byKey(const ValueKey('mount-check-again')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));
      expect(find.byKey(const ValueKey('mount-check-level-ok')), findsOneWidget);
      expect(find.text('기울기: +0.4°'), findsOneWidget);

      await tester.tap(find.byKey(const ValueKey('mount-check-close')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('mount-check-dialog')), findsNothing);
    });

    testWidgets('계속 재기: 창이 떠 있는 동안만 3초마다, 끄면 멈춤', (tester) async {
      var n = 0;
      await open(tester, live: true, check: (_, _) async {
        n++;
        return good();
      });
      expect(n, 1);
      await tester.pump(const Duration(seconds: 3));
      await tester.pump(const Duration(milliseconds: 50));
      expect(n, 2);

      await tester.tap(find.byKey(const ValueKey('mount-check-live')));
      await tester.pump();
      await tester.pump(const Duration(seconds: 7));
      expect(n, 2);

      await tester.tap(find.byKey(const ValueKey('mount-check-close')));
      await tester.pumpAndSettle();
      await tester.pump(const Duration(seconds: 7));
      expect(n, 2);
    });

    testWidgets('사진을 못 받으면 안내', (tester) async {
      await tester.pumpWidget(MaterialApp(
        home: Builder(
          builder: (ctx) => TextButton(
            onPressed: () => showMountCheck(ctx, fetch: () async => null, check: (_, _) async => good()),
            child: const Text('열기'),
          ),
        ),
      ));
      await tester.tap(find.text('열기'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));
      expect(find.text('사진을 받지 못했습니다'), findsWidgets);
    });
  });
}
