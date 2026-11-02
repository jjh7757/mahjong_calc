// 다른 마작 탁자에서 펠트 격자가 어떻게 되는지 본다(2026-11-02, API 없음). 전체 테스트에는 안 들어간다. 이 결과로 규칙을 고치지 않는다.
//   flutter test tool/felt_grid_other_test.dart  → experiments/tile_classifier/data/zone_points/other_tables.json
// ① 다른 탁자가 찍혔을 수 있는 사진 그대로 ② 재료 사진을 편집한 탁자(펠트 색·테두리 색·기기 크기·기기 없음). 패·손 위치는 그대로다.
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/felt_grid.dart';
import 'package:mahjong_calc/table/rectify.dart' show FeltQuad;

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

/// 사진 비율 좌표 → 편 좌표(단위 정사각형 네 꼭짓점 대응의 역변환, 뉴턴 없이 8원 일차방정식).
class _Inverse {
  final List<double> h;
  _Inverse(this.h);
  static _Inverse of(FeltQuad q) {
    // q → 단위 정사각형 사영 변환을 푼다.
    final src = q.corners;
    const dst = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]];
    final a = List.generate(8, (_) => List<double>.filled(9, 0));
    for (var i = 0; i < 4; i++) {
      final x = src[i].x, y = src[i].y, u = dst[i][0], v = dst[i][1];
      a[2 * i] = [x, y, 1, 0, 0, 0, -u * x, -u * y, u];
      a[2 * i + 1] = [0, 0, 0, x, y, 1, -v * x, -v * y, v];
    }
    for (var c = 0; c < 8; c++) {
      var p = c;
      for (var r = c + 1; r < 8; r++) {
        if (a[r][c].abs() > a[p][c].abs()) p = r;
      }
      final t = a[c];
      a[c] = a[p];
      a[p] = t;
      for (var r = 0; r < 8; r++) {
        if (r == c) continue;
        final f = a[r][c] / a[c][c];
        for (var k = c; k < 9; k++) {
          a[r][k] -= f * a[c][k];
        }
      }
    }
    return _Inverse([for (var i = 0; i < 8; i++) a[i][8] / a[i][i]]);
  }

  (double, double) at(double x, double y) {
    final w = h[6] * x + h[7] * y + 1;
    return ((h[0] * x + h[1] * y + h[2]) / w, (h[3] * x + h[4] * y + h[5]) / w);
  }
}

bool _green(num r, num g, num b) => g > r * 1.15 && g > b * 1.05 && g > 35;
bool _whiteish(num r, num g, num b) {
  final mx = math.max(r, math.max(g, b)), mn = math.min(r, math.min(g, b));
  return mx > 130 && mx - mn < 45;
}

int _c(num v) => v.round().clamp(0, 255);

/// 펠트·테두리·기기를 바꾼 사진. [felt] = 펠트 색 배율 대신 대상 색, [frame] = 흰 테두리 대상 색, [device] 1 이면 그대로, 0 이면 없앰, 그 밖이면 크기 배수.
img.Image _edit(img.Image s, FeltQuad q, {List<int>? felt, List<int>? frame, double device = 1}) {
  final o = img.Image.from(s);
  final inv = _Inverse.of(q);
  final w = o.width, h = o.height;
  const base = [28, 100, 68]; // 이 탁자 펠트 어림
  final fc = felt ?? base;
  final hw = 0.0985, hh = 0.097;
  for (final p in o) {
    final (u, v) = inv.at(p.x / w, p.y / h);
    final inFelt = u >= 0 && u <= 1 && v >= 0 && v <= 1;
    if (inFelt) {
      final du = (u - 0.5).abs(), dv = (v - 0.5).abs();
      final inDev = du < hw && dv < hh;
      final g = _green(p.r, p.g, p.b);
      if (g) {
        // 무늬를 살려 색만 옮긴다.
        final k = p.g / base[1];
        p.r = _c(fc[0] * k);
        p.g = _c(fc[1] * k);
        p.b = _c(fc[2] * k);
      }
      if (device == 0 && du < hw * 1.05 && dv < hh * 1.05) {
        p.r = _c(fc[0]);
        p.g = _c(fc[1]);
        p.b = _c(fc[2]);
      } else if (device < 1 && inDev && (du > hw * device || dv > hh * device)) {
        p.r = _c(fc[0]);
        p.g = _c(fc[1]);
        p.b = _c(fc[2]);
      } else if (device > 1 && !inDev && du < hw * device && dv < hh * device && (g || felt != null && (p.r - fc[0]).abs() < 40)) {
        p.r = 30;
        p.g = 34;
        p.b = 70;
      }
    } else if (frame != null && u > -0.11 && u < 1.11 && v > -0.11 && v < 1.11 && _whiteish(p.r, p.g, p.b)) {
      final k = p.r / 220;
      p.r = _c(frame[0] * k);
      p.g = _c(frame[1] * k);
      p.b = _c(frame[2] * k);
    }
  }
  return o;
}

void main() {
  const dir = 'experiments/tile_classifier/data/zone_points';
  test('다른 탁자', () {
    final out = <String, Object?>{};
    final real = <String, Object?>{};
    final files = <File>[
      for (final d in ['experiments/vlm/samples_real', 'experiments/vlm/samples_real2', 'experiments/vlm/samples_broadcast', 'experiments/vlm/samples_phone', 'experiments/vlm/samples_game'])
        if (Directory(d).existsSync()) ...Directory(d).listSync().whereType<File>().where((f) => RegExp(r'\.(jpe?g|png)$', caseSensitive: false).hasMatch(f.path)),
      for (final n in ['KakaoTalk_20261023_110025744.jpg', 'MM85_tanyao15151153_TP_V.jpg'])
        if (File('${Platform.environment['USERPROFILE']}/Downloads/$n').existsSync()) File('${Platform.environment['USERPROFILE']}/Downloads/$n'),
    ];
    for (final f in files) {
      final im = img.decodeImage(f.readAsBytesSync());
      if (im == null) continue;
      real[f.path] = _row(readFelt(im)) ?? {'none': true};
    }
    out['real'] = real;

    final labels = jsonDecode(File('$dir/labels.json').readAsStringSync()) as Map<String, dynamic>;
    const photos = ['20261031_123140', '20261031_124654', '20261031_125839', '20261031_130743', '20261031_131411', '20261031_134815', '20261031_142535', '20261031_165043', '20261031_171505', 'k16', 'k25', 'k15'];
    final variants = <String, img.Image Function(img.Image, FeltQuad)>{
      '그대로': (s, q) => s,
      '파란 펠트': (s, q) => _edit(s, q, felt: [30, 60, 130]),
      '붉은 펠트': (s, q) => _edit(s, q, felt: [125, 35, 40]),
      '보라 펠트': (s, q) => _edit(s, q, felt: [80, 50, 120]),
      '회색 펠트': (s, q) => _edit(s, q, felt: [95, 98, 100]),
      '검은 펠트': (s, q) => _edit(s, q, felt: [38, 38, 42]),
      '남색 펠트(기기와 비슷)': (s, q) => _edit(s, q, felt: [28, 36, 88]),
      '검은 테두리': (s, q) => _edit(s, q, frame: [30, 30, 32]),
      '나무 테두리': (s, q) => _edit(s, q, frame: [120, 80, 45]),
      '초록 테두리(펠트와 비슷)': (s, q) => _edit(s, q, frame: [35, 110, 75]),
      '기기 없음': (s, q) => _edit(s, q, device: 0),
      '기기 0.7배': (s, q) => _edit(s, q, device: 0.7),
      '기기 1.3배': (s, q) => _edit(s, q, device: 1.3),
      '파란 펠트 + 검은 테두리 + 기기 0.7배': (s, q) => _edit(s, q, felt: [30, 60, 130], frame: [30, 30, 32], device: 0.7),
    };
    final edited = <String, Map<String, Object?>>{for (final k in variants.keys) k: {}};
    for (final n in photos) {
      final r = labels[n] as Map<String, dynamic>;
      final base = img.copyResize(img.decodeJpg(File(r['src'] as String).readAsBytesSync())!, width: 1020, height: 765, interpolation: img.Interpolation.linear);
      final f = [for (final p in r['felt'] as List) math.Point<double>(((p as List)[0] as num).toDouble(), (p[1] as num).toDouble())];
      final q = FeltQuad(f[0], f[1], f[2], f[3]);
      for (final v in variants.entries) {
        final im = v.value(base, q);
        edited[v.key]![n] = _row(readFelt(im));
        if (n == '20261031_131411') {
          File('$dir/other_${v.key.replaceAll(RegExp(r'[^0-9a-zA-Z가-힣.]'), '_')}.jpg').writeAsBytesSync(img.encodeJpg(im, quality: 80));
        }
      }
    }
    out['edited'] = edited;
    File('$dir/other_tables.json').writeAsStringSync(jsonEncode(out));
  }, timeout: const Timeout(Duration(minutes: 20)));
}
