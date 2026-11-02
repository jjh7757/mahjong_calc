// 펠트 격자가 재료 사진에 과적합됐는지 본다(2026-11-02, API 없음). 전체 테스트에는 안 들어간다. 이 결과로 규칙을 고치지 않는다.
//   flutter test tool/felt_grid_robust_test.dart  → experiments/tile_classifier/data/zone_points/robust.json, 표는 experiments/zone_points/robust_check.py
// ① 10-24 삼각대 사진: 규칙을 만들 때 안 본 사진을 그대로. ② 재료 사진 35장의 밝기·색을 바꾼 파생 사진.
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/felt_grid.dart';

Map<String, Object?>? _row(FeltReading? r) => r == null
    ? null
    : {
        'felt': [for (final p in r.quad.corners) [p.x, p.y]],
        'span': r.minSpan,
        'device': r.deviceShare,
        'edge': r.deviceEdge,
        'outside': r.outsideMax,
        'inside': r.insideMin,
        'off': r.offImage,
        'ratio': r.sideRatio,
        'ok': r.ok,
        'grid': gridFromFelt(r.quad)?.toJson(),
      };

int _c(num v) => v.round().clamp(0, 255);

/// 채널 배율(밝기·색온도).
img.Image _gain(img.Image s, double r, double g, double b) {
  final o = img.Image.from(s);
  for (final p in o) {
    p.r = _c(p.r * r);
    p.g = _c(p.g * g);
    p.b = _c(p.b * b);
  }
  return o;
}

/// 색상을 [deg] 돌리고 채도를 [sat] 배.
img.Image _hueSat(img.Image s, double deg, double sat) {
  final o = img.Image.from(s);
  final th = deg * math.pi / 180;
  final co = math.cos(th), si = math.sin(th);
  for (final p in o) {
    final r = p.r / 255.0, g = p.g / 255.0, b = p.b / 255.0;
    // YIQ 평면에서 돌린다.
    final y = 0.299 * r + 0.587 * g + 0.114 * b;
    var i = 0.596 * r - 0.274 * g - 0.322 * b, q = 0.211 * r - 0.523 * g + 0.312 * b;
    final i2 = (i * co - q * si) * sat, q2 = (i * si + q * co) * sat;
    i = i2;
    q = q2;
    p.r = _c(255 * (y + 0.956 * i + 0.621 * q));
    p.g = _c(255 * (y - 0.272 * i - 0.647 * q));
    p.b = _c(255 * (y - 1.106 * i + 1.703 * q));
  }
  return o;
}

void main() {
  const dir = 'experiments/tile_classifier/data/zone_points';
  test('삼각대 사진·파생 사진', () {
    final out = <String, Object?>{};
    final field = <String, Object?>{};
    final fieldDirs = Directory('experiments/field_20261024/captures').listSync().whereType<Directory>().toList()
      ..sort((a, b) => a.path.compareTo(b.path));
    for (final d in fieldDirs) {
      final f = File('${d.path}/original.jpg');
      if (!f.existsSync()) continue;
      field[d.path.split(RegExp(r'[\\/]')).last] = {'src': f.path, ..._row(readFelt(img.decodeJpg(f.readAsBytesSync())!)) ?? {'none': true}};
    }
    out['field'] = field;

    final rows = jsonDecode(File('$dir/proposals.json').readAsStringSync()) as Map<String, dynamic>;
    final variants = <String, img.Image Function(img.Image)>{
      '원본': (s) => s,
      '밝기 0.5': (s) => _gain(s, .5, .5, .5),
      '밝기 0.7': (s) => _gain(s, .7, .7, .7),
      '밝기 1.3': (s) => _gain(s, 1.3, 1.3, 1.3),
      '밝기 1.6': (s) => _gain(s, 1.6, 1.6, 1.6),
      '따뜻한 조명': (s) => _gain(s, 1.2, 1.0, .75),
      '차가운 조명': (s) => _gain(s, .8, 1.0, 1.25),
      '색상 -10°': (s) => _hueSat(s, -10, 1),
      '색상 +10°': (s) => _hueSat(s, 10, 1),
      '색상 -25°': (s) => _hueSat(s, -25, 1),
      '색상 +25°': (s) => _hueSat(s, 25, 1),
      '채도 0.7': (s) => _hueSat(s, 0, .7),
      '채도 0.45': (s) => _hueSat(s, 0, .45),
      '작은 사진 640': (s) => img.copyResize(s, width: 640, height: 480, interpolation: img.Interpolation.linear),
    };
    final derived = <String, Map<String, Object?>>{for (final k in variants.keys) k: {}};
    for (final e in rows.entries) {
      final r = e.value as Map<String, dynamic>;
      if (r['kind'] != 'photo') continue;
      final base = img.copyResize(img.decodeJpg(File(r['src'] as String).readAsBytesSync())!, width: 1020, height: 765, interpolation: img.Interpolation.linear);
      for (final v in variants.entries) {
        derived[v.key]![e.key] = _row(readFelt(v.value(base)));
      }
    }
    out['derived'] = derived;
    File('$dir/robust.json').writeAsStringSync(jsonEncode(out));
  }, timeout: const Timeout(Duration(minutes: 30)));
}
