import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/ui/mount/grid_editor.dart';

void main() {
  setUp(() {
    final view = TestWidgetsFlutterBinding.instance.platformDispatcher.views.first;
    view.physicalSize = const Size(1000, 1000);
    view.devicePixelRatio = 1;
  });
  tearDown(() => TestWidgetsFlutterBinding.instance.platformDispatcher.views.first.reset());

  Future<GridZones> drag(WidgetTester t, Offset from, Offset by) async {
    var g = GridZones.initial;
    await t.pumpWidget(MaterialApp(
      home: Center(
        child: SizedBox(
          width: 1000,
          height: 1000,
          child: StatefulBuilder(
            builder: (context, set) => GridOverlay(grid: g, editing: true, onChanged: (v) => set(() => g = v)),
          ),
        ),
      ),
    ));
    final origin = t.getTopLeft(find.byType(GridOverlay));
    await t.dragFrom(origin + from, by);
    await t.pump();
    return g;
  }

  testWidgets('왼쪽 세로선을 끌면 x1 만 움직인다', (t) async {
    final g0 = GridZones.initial;
    final g = await drag(t, Offset(g0.x1.toDouble(), 500), const Offset(-60, 0));
    expect(g.x1, closeTo(g0.x1 - 60, 2));
    expect(g.x2, g0.x2);
    expect(g.y1, g0.y1);
  });

  testWidgets('오른쪽 세로선은 위 끝부터 아래 선까지만 있어 그 범위에서 잡힌다', (t) async {
    final g0 = GridZones.initial;
    final g = await drag(t, Offset(g0.x2.toDouble(), 80), const Offset(30, 0));
    expect(g.x2, closeTo(g0.x2 + 30, 2));
    // 왼쪽 세로선은 위 선 아래로만 그어져 있어, 위 선보다 위를 잡으면 아무것도 안 움직인다.
    final g2 = await drag(t, Offset(g0.x1.toDouble(), 60), const Offset(-60, 0));
    expect(g2, g0);
  });

  testWidgets('편집이 아니면 끌어도 그대로', (t) async {
    var changed = false;
    await t.pumpWidget(MaterialApp(
      home: SizedBox(
        width: 1000,
        height: 1000,
        child: GridOverlay(grid: GridZones.initial, onChanged: (_) => changed = true),
      ),
    ));
    await t.dragFrom(const Offset(280, 100), const Offset(-60, 0));
    expect(changed, isFalse);
    expect(Side.values, hasLength(4));
  });
}
