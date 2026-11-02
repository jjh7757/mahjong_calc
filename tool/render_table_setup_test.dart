// 테이블 화면(키오스크)에 자동 맞추기 결과(격자 선·리치봉 상자·도라 산 상자)가 적용된 모습을 PNG 로 그린다(눈 확인용, 전체 테스트에는 안 들어감).
// 사진을 줄여 운영 `/v2/setup`·`/v2/wall` 을 실제로 부르고 앱과 같은 `proposeGrid`·`parseWallV2` 로 격자·상자를 만든 뒤,
// 앱의 `GridOverlay`·`TableScorePanel` 을 사진 위에 얹고 오른쪽 버튼 칸을 흉내 내어 1280×800 으로 저장한다.
//   PHOTO=<jpg> OUT=build/table_setup.png flutter test tool/render_table_setup_test.dart --dart-define=RECOGNIZER_API_KEY=<키>
// 키가 없으면(또는 NO_SERVER=1) 격자 기본값·상자 없음으로 그린다.
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/services/recognizer_client.dart';
import 'package:mahjong_calc/table/cropper.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/observation.dart';
import 'package:mahjong_calc/table/seat_map.dart';
import 'package:mahjong_calc/ui/kiosk.dart';
import 'package:mahjong_calc/ui/mount/grid_editor.dart';
import 'package:mahjong_calc/ui/mount/score_panel.dart';
import 'package:shared_preferences/shared_preferences.dart';

Future<void> _font(String family, List<String> files) async {
  final l = FontLoader(family);
  for (final f in files) {
    final b = File(f).readAsBytesSync();
    l.addFont(Future.value(ByteData.view(b.buffer)));
  }
  await l.load();
}

void main() {
  testWidgets('render table setup', (tester) async {
    // ignore: invalid_use_of_visible_for_testing_member
    SharedPreferences.setMockInitialValues({});
    // flutter test 는 모든 HTTP 를 400 으로 막는 가짜 클라이언트를 깐다 → 실제 서버를 부르려면 걷어낸다.
    HttpOverrides.global = null;
    await tester.runAsync(() async {
      await _font('Roboto', [r'C:\Windows\Fonts\malgun.ttf', r'C:\Windows\Fonts\malgunbd.ttf']);
    });
    final photo = Platform.environment['PHOTO'] ?? r'experiments\field_20261024\kakao_photos\synth_wall\k15.jpg';
    final out = Platform.environment['OUT'] ?? 'build/table_setup.png';
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    final bytes = File(photo).readAsBytesSync();
    var grid = GridZones.initial;
    WallZone? wall;
    var note = '서버 호출 없음(격자 기본값)';
    if (RecognizerConfig.isConfigured && Platform.environment['NO_SERVER'] != '1') {
      await tester.runAsync(() async {
        final small = shrinkForLocate(bytes);
        final client = RecognizerClient();
        final sw = Stopwatch()..start();
        try {
          final setupF = client.observe('setup', small, filename: 'setup.jpg');
          final wallF = client.observe('wall', small, filename: 'wall.jpg').then<Map<String, dynamic>?>((j) => j,
              onError: (Object _) => null);
          final setup = await setupF;
          final wallJ = await wallF;
          final proposed = proposeGrid(setup, keep: grid);
          if (proposed != null) grid = proposed;
          wall = wallJ == null ? null : parseWallV2(wallJ);
          note = '자동 맞추기 ${(sw.elapsedMilliseconds / 1000).toStringAsFixed(1)}초: '
              '격자 ${proposed == null ? '못 맞춤' : '맞춤'}, 도라 산 ${wall == null ? '못 찾음' : '찾음'}';
        } finally {
          client.close();
        }
      });
    }
    // ignore: avoid_print
    print('[render] $note grid=${grid.toJson()} wall=${wall?.box.toList()} ${wall?.side.name}');

    final game = Game(
      id: 'render',
      startedAt: DateTime(2026, 10, 29),
      settings: const GameSettings(),
      names: const ['A', 'B', 'C', 'D'],
    );
    final seats = SeatMap(game.settings.bottomSeat);
    final key = GlobalKey();
    Widget big(String label, IconData icon, {bool primary = false}) {
      final child = FittedBox(
        fit: BoxFit.scaleDown,
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon, size: 26),
          const SizedBox(width: 10),
          Text(label, style: const TextStyle(fontSize: 20)),
        ]),
      );
      final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(14));
      return SizedBox(
        height: primary ? 96 : 68,
        child: primary
            ? FilledButton(style: FilledButton.styleFrom(shape: shape), onPressed: () {}, child: child)
            : OutlinedButton(
                style: OutlinedButton.styleFrom(shape: shape, foregroundColor: Colors.white),
                onPressed: () {},
                child: child,
              ),
      );
    }

    await tester.pumpWidget(RepaintBoundary(
      key: key,
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: kioskDarkTheme(),
        home: Scaffold(
          backgroundColor: Colors.black,
          body: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(
                child: Container(
                  color: Colors.black,
                  alignment: Alignment.center,
                  child: AspectRatio(
                    aspectRatio: 4 / 3,
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        Image.memory(bytes, fit: BoxFit.fill, cacheWidth: 1200),
                        GridOverlay(grid: grid, dealer: seats.sideOf(game.dealer)),
                        LayoutBuilder(
                          builder: (context, c) => Center(
                            child: TableScorePanel(
                              game: game,
                              seats: seats,
                              size: (c.biggest.shortestSide * 0.45).clamp(170.0, 340.0),
                            ),
                          ),
                        ),
                        Positioned(
                          left: 0,
                          right: 0,
                          bottom: 12,
                          child: Center(
                            child: Material(
                              color: const Color(0xFF323232),
                              borderRadius: BorderRadius.circular(4),
                              child: Padding(
                                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                                child: Text(
                                  '대국 시작 자동 맞추기: 손패+울기 띠와 리치봉 상자를 맞췄습니다. '
                                  '${wall == null ? '도라 산은 못 찾았습니다' : '도라 산을 찾았습니다'}. 틀렸으면 더보기 "구역 격자 맞추기" 에서 고치세요',
                                  style: const TextStyle(color: Colors.white, fontSize: 13),
                                ),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              Container(
                width: 320,
                color: kioskSurface,
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    big('화료 촬영', Icons.camera_alt, primary: true),
                    const SizedBox(height: 12),
                    big('직접 계산', Icons.calculate_outlined),
                    const SizedBox(height: 12),
                    Row(children: [
                      Expanded(child: big('리치', Icons.flag_outlined)),
                      const SizedBox(width: 12),
                      Expanded(child: big('유국', Icons.block)),
                    ]),
                    const SizedBox(height: 12),
                    Row(children: [
                      Expanded(child: big('천화', Icons.auto_awesome)),
                      const SizedBox(width: 12),
                      Expanded(child: big('지화', Icons.auto_awesome_outlined)),
                    ]),
                    const SizedBox(height: 12),
                    Row(children: [
                      Expanded(child: big('갤러리', Icons.photo_library_outlined)),
                      const SizedBox(width: 12),
                      Expanded(child: big('기록', Icons.scoreboard_outlined)),
                    ]),
                    const SizedBox(height: 12),
                    const Text('기록', style: TextStyle(color: Colors.white70, fontSize: 13, fontWeight: FontWeight.w600)),
                    const Expanded(child: Text('기록 없음', style: TextStyle(color: Colors.white38, fontSize: 13))),
                    const Text(
                      '아래 A · 오른쪽 B\n위 C · 왼쪽 D\n카메라 헤드 (배경은 헤드 미리보기) · 도라 산 잡음',
                      style: TextStyle(fontSize: 12, color: Colors.white60),
                    ),
                    const SizedBox(height: 8),
                    Wrap(children: [
                      TextButton(onPressed: () {}, child: const Text('점수표')),
                      TextButton(onPressed: () {}, child: const Text('룰 설정')),
                      TextButton.icon(
                        onPressed: () {},
                        icon: const Icon(Icons.grid_4x4, size: 16),
                        label: const Text('격자 편집'),
                      ),
                      TextButton.icon(
                        onPressed: () {},
                        icon: const Icon(Icons.view_week_outlined, size: 16),
                        label: Text(wall == null ? '도라 산 찾기' : '도라 산 다시 찾기'),
                      ),
                      TextButton.icon(
                        onPressed: () {},
                        style: TextButton.styleFrom(foregroundColor: const Color(0xFF66BB6A)),
                        icon: const Icon(Icons.videocam, size: 16),
                        label: const Text('헤드 연결됨'),
                      ),
                    ]),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.runAsync(() async {
      for (final e in find.byType(Image).evaluate()) {
        await precacheImage((e.widget as Image).image, e);
      }
    });
    await tester.pumpAndSettle();
    await tester.runAsync(() async {
      final boundary = key.currentContext!.findRenderObject() as RenderRepaintBoundary;
      final img = await boundary.toImage();
      final png = await img.toByteData(format: ui.ImageByteFormat.png);
      File(out).writeAsBytesSync(png!.buffer.asUint8List());
    });
    // ignore: avoid_print
    print('[render] → $out');
  });
}
