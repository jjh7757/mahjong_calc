// 거치 점검 창을 실제 사진으로 그려 PNG 로 남긴다(눈 확인용, 전체 테스트에는 안 들어감, API 없음).
//   PHOTO=<jpg> OUT=build/mount_check.png flutter test tool/render_mount_check_test.dart
// 사진은 헤드 미리보기처럼 긴 변 1020 으로 줄여 넣고, 패 크기는 원본 긴 변으로 환산한다(앱과 같음).
import 'dart:io';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/mount_check.dart';
import 'package:mahjong_calc/ui/kiosk.dart';
import 'package:mahjong_calc/ui/mount/mount_check_dialog.dart';

Future<void> _font(String family, List<String> files) async {
  final l = FontLoader(family);
  for (final f in files) {
    final b = File(f).readAsBytesSync();
    l.addFont(Future.value(ByteData.view(b.buffer)));
  }
  await l.load();
}

void main() {
  testWidgets('render mount check', (tester) async {
    await tester.runAsync(() async {
      await _font('Roboto', [r'C:\Windows\Fonts\malgun.ttf', r'C:\Windows\Fonts\malgunbd.ttf']);
      await _font('MaterialIcons', [
        '${Platform.environment['FLUTTER_ROOT'] ?? r'C:\Users\jjh7757\flutter'}/bin/cache/artifacts/material_fonts/MaterialIcons-Regular.otf',
      ]);
    });
    final photo = Platform.environment['PHOTO'] ?? r'experiments\visit_20261107\captures\20261107_154417\original.jpg';
    final out = Platform.environment['OUT'] ?? 'build/mount_check.png';
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    final src = img.decodeJpg(File(photo).readAsBytesSync())!;
    final long = math.max(src.width, src.height);
    final small = img.copyResize(src, width: (src.width * 1020 / long).round(), height: (src.height * 1020 / long).round());
    final jpg = Uint8List.fromList(img.encodeJpg(small, quality: 85));
    final result = checkMount(small, captureLongSide: long);
    // ignore: avoid_print
    print('[render] ${result.toJson()}');

    final key = GlobalKey();
    await tester.pumpWidget(RepaintBoundary(
      key: key,
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: kioskDarkTheme(),
        home: Scaffold(
          backgroundColor: kioskBg,
          body: Builder(
            builder: (ctx) => kioskWrap(
              ctx,
              MountCheckDialog(fetch: () async => jpg, live: true, interval: const Duration(days: 1), check: (_, _) async => result),
              scale: 1.1,
            ),
          ),
        ),
      ),
    ));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.runAsync(() async {
      for (final e in find.byType(Image).evaluate()) {
        await precacheImage((e.widget as Image).image, e);
      }
    });
    await tester.pump(const Duration(milliseconds: 100));
    await tester.runAsync(() async {
      final boundary = key.currentContext!.findRenderObject() as RenderRepaintBoundary;
      final image = await boundary.toImage();
      final png = await image.toByteData(format: ui.ImageByteFormat.png);
      File(out).writeAsBytesSync(png!.buffer.asUint8List());
    });
    // ignore: avoid_print
    print('[render] → $out');
    await tester.pumpWidget(const SizedBox());
  });
}
