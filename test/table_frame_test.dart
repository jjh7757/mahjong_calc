import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/table/table_frame.dart';
import 'package:mahjong_calc/table/table_layout.dart';

/// 탁자 기준점·패 단위 구역표 — Python(`experiments/zone_points/table_frame.py --test`)과 같은 fixture 를 통과해야 한다.
/// 기대 출력은 Python 이 만들었다. 점·상자 0.5px, 각도 1e-3°, norm ±1, 바람개비 칸은 같아야 함.
void main() {
  final table = ZoneTable.fromJson(
      jsonDecode(File('assets/table_frame/zones.json').readAsStringSync()) as Map<String, dynamic>);
  final fixture = jsonDecode(File('test/fixtures/table_frame.json').readAsStringSync()) as Map<String, dynamic>;
  const tol = 0.5;

  test('구역표: 규칙 몫과 탁자 프로필이 따로', () {
    expect(table.rules.containsKey('zones'), isTrue);
    expect(table.rules.containsKey('wall_half_per_device'), isFalse);
    expect(table.profile()['wall_half_per_device'], 3.85);
    expect(table.profile('amos')['u_per_back_short'], 0.87);
    expect(table.zoneNames,
        containsAll(['seat', 'hand', 'corner', 'river', 'stick_strip', 'dead_wall', 'center', 'device', 'sticks', 'dora_search']));
  });

  group('cases', () {
    for (final c in (fixture['cases'] as List<dynamic>).cast<Map<String, dynamic>>()) {
      test(c['name'] as String, () {
        final frame = TableFrame.fromJson(c['frame'] as Map<String, dynamic>);
        final size = (c['size'] as List<dynamic>).cast<num>();
        final w = size[0].toDouble(), h = size[1].toDouble();
        final except = {for (final s in (c['except'] as List<dynamic>)) Side.values.byName(s as String)};
        final exp = c['expect'] as Map<String, dynamic>;
        final z = TableZones(table, frame, w, h);
        expect(z.r, closeTo(exp['R'] as num, 1e-3));
        expect(z.edge, closeTo(exp['edge'] as num, 1e-3));
        final rects = z.allRects(except: except);
        final want = exp['rects'] as Map<String, dynamic>;
        expect(rects.keys.toSet(), want.keys.toSet());
        for (final MapEntry(:key, :value) in want.entries) {
          final g = rects[key]!;
          if (value == null) {
            expect(g.isEmpty, isTrue, reason: '$key 빈 구역');
            continue;
          }
          final e = value as Map<String, dynamic>;
          final pts = (e['pts'] as List<dynamic>).cast<List<dynamic>>();
          expect(g.pts.length, 4, reason: key);
          for (var i = 0; i < 4; i++) {
            expect(g.pts[i].x, closeTo(pts[i][0] as num, tol), reason: '$key pts[$i].x');
            expect(g.pts[i].y, closeTo(pts[i][1] as num, tol), reason: '$key pts[$i].y');
          }
          final dAng = ((g.angleDeg - (e['angle_deg'] as num) + 180) % 360 - 180).abs();
          expect(dAng, lessThan(1e-3), reason: '$key angle');
          final b = g.bbox(w, h);
          if (e['bbox'] == null) {
            expect(b, isNull, reason: '$key bbox');
          } else {
            final eb = (e['bbox'] as List<dynamic>).cast<num>();
            expect(b, isNotNull, reason: '$key bbox');
            expect([b!.x0, b.y0, b.x1, b.y1], [for (final v in eb) closeTo(v, tol)], reason: '$key bbox');
          }
          final n = g.norm(w, h);
          if (e['norm'] == null) {
            expect(n, isNull, reason: '$key norm');
          } else {
            expect(n!.toList(), [for (final v in (e['norm'] as List<dynamic>).cast<num>()) closeTo(v, 1)], reason: '$key norm');
          }
        }
        final pts = (c['points'] as List<dynamic>).cast<List<dynamic>>();
        final zoneOf = [for (final p in pts) z.zoneOf((p[0] as num).toDouble(), (p[1] as num).toDouble())?.name ?? 'center'];
        expect(zoneOf, exp['zone_of']);
      });
    }
  });

  group('from_wall', () {
    for (final wcase in (fixture['from_wall'] as List<dynamic>).cast<Map<String, dynamic>>()) {
      test(wcase['name'] as String, () {
        final i = wcase['input'] as Map<String, dynamic>;
        final size = (i['size'] as List<dynamic>).cast<num>();
        final f = TableFrame.fromWall(
          cx: (i['cx'] as num).toDouble(),
          cy: (i['cy'] as num).toDouble(),
          theta: (i['theta'] as num).toDouble(),
          backShortPx: (i['back_short_px'] as num).toDouble(),
          wallHalfPx: (i['wall_half_px'] as num).toDouble(),
          width: size[0].toDouble(),
          height: size[1].toDouble(),
          profile: table.profile(),
        );
        final e = wcase['expect'] as Map<String, dynamic>;
        expect(f.u, closeTo(e['u'] as num, 1e-3));
        expect(f.d, closeTo(e['D'] as num, 1e-3));
        expect(f.source.name, e['source']);
      });
    }
  });

  group('moved', () {
    for (final m in (fixture['moved'] as List<dynamic>).cast<Map<String, dynamic>>()) {
      test(m['name'] as String, () {
        final a = TableFrame.fromJson(m['a'] as Map<String, dynamic>), b = TableFrame.fromJson(m['b'] as Map<String, dynamic>);
        expect(a.movedFrom(b, table), m['expect']);
      });
    }
  });

  test('JSON 왕복·사진 크기 옮기기', () {
    const f = TableFrame(cx: 510, cy: 382, theta: 0.02, u: 21, d: 3.1, width: 1020, height: 764, source: FrameSource.wall, at: '2026-10-31T18:06:58');
    final g = TableFrame.fromJson(jsonDecode(jsonEncode(f.toJson())) as Map<String, dynamic>);
    expect(g.toJson(), f.toJson());
    final s = f.scaledTo(4080, 3060);
    expect([s.cx, s.cy, s.u, s.d, s.theta], [2040, 1528, 84, 3.1, 0.02]);
    // 같은 점은 어느 크기에서 재도 같은 구역
    final z1 = TableZones(table, f, 1020, 764), z4 = TableZones(table, f, 4080, 3060);
    expect(z4.r, closeTo(z1.r, 1e-9));
    expect(z4.zoneOf(4 * 300, 4 * 700), z1.zoneOf(300, 700));
  });

  test('리치봉 띠는 리치봉 상자 안, 손패 띠는 자리 칸 안', () {
    const f = TableFrame(cx: 2000, cy: 1500, theta: 0.05, u: 80, d: 3.2, width: 4000, height: 3000);
    final z = TableZones(table, f, 4000, 3000);
    Pt mid(RotRect r) => (x: r.pts.map((p) => p.x).reduce((a, b) => a + b) / 4, y: r.pts.map((p) => p.y).reduce((a, b) => a + b) / 4);
    for (final s in Side.values) {
      final st = z.stickStrip(s);
      expect(st.r1, closeTo(z.sticks.r1, 1e-9));
      final m = mid(st);
      expect(z.inside('sticks', m.x, m.y), isTrue);
      expect(z.inside('device', m.x, m.y), isTrue);
      final h = mid(z.hand(s));
      expect(z.zoneOf(h.x, h.y), s);
    }
  });
}
