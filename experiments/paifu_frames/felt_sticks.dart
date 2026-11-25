// ignore_for_file: avoid_print
// 프레임 묶음(추적 zip 또는 헤드 녹화 jpg 목록) → 펠트 격자의 리치봉 구역(2026-11-25, 자동 패보 설계서 8-12 (가) — 구현 2-②).
// 프레임마다 앱 코드 그대로 펠트를 읽고(`readFelt` — 긴 변 1020 으로 줄여 읽음, 믿을 만한 판독 `ok` 만), 그 모서리들의 중앙값(`medianFelt`)으로
// `gridFromFelt` 격자를 만들어 리치봉 구역(1000 분율 ymin,xmin,ymax,xmax — 기록기 --sticks 꼴)을 낸다. 견줄 격자(앱 저장 값)를 주면 `gridShiftOf`.
// 앱 코드(lib/)는 읽기만 한다 — experiments/tracking/replay_rounds.dart(11-16)의 프레임 풀기 · 펠트 읽기를 본으로 삼음.
//   dart run experiments/paifu_frames/felt_sticks.dart <spec.json> <out.json>
// spec = {"jobs": [{"id", "kind": "zip" | "jpg", "zips": [...] | "files": [...], "from", "to"(zip 만 — 프레임 at 글 'YYYY-MM-DDTHH:MM:SS' 로 거름, 태블릿 시계), "n"(zip 만 — 고르게 뽑을 수),
//                   "app_grid": {x1, x2, y1, y2, dora, sticks}(선택 — 없고 zip 이면 zip 의 frames.json grid 중 프레임이 가장 많은 것)}]}
// out = {"jobs": {id: {"frames": [{file, at, ok, sticks}], "read", "ok", "failed", "sticks"(중앙 모서리 격자), "sticks_median_each"(프레임별 값의 좌표별 중앙값),
//                      "spread"(프레임별 값의 좌표별 최대 − 최소 중 큰 값), "app_sticks", "shift"(gridShiftOf(앱, 펠트)), "shift_max"(feltGridShiftMax), "grid"}}}
import 'dart:convert';
import 'dart:io';
import 'dart:math' as m;
import 'dart:typed_data';

import 'package:archive/archive.dart';
import 'package:mahjong_calc/table/felt_grid.dart';
import 'package:mahjong_calc/table/fixed_layout.dart' show decodeSmall;
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/rectify.dart' show FeltQuad;

int _med(List<int> v) {
  final s = [...v]..sort();
  final n = s.length;
  return n.isOdd ? s[n ~/ 2] : ((s[n ~/ 2 - 1] + s[n ~/ 2]) / 2).round();
}

/// 고르게 n 개(양 끝을 빼고 n + 1 등분한 점에 가장 가까운 것).
List<T> _even<T>(List<T> xs, int n) {
  if (xs.length <= n) return xs;
  return [for (var k = 1; k <= n; k++) xs[((xs.length - 1) * k / (n + 1)).round()]];
}

Map<String, Object?> _one(String file, String? at, Uint8List bytes, GridZones? keep) {
  final im = decodeSmall(bytes);
  final r = readFelt(im);
  final row = <String, Object?>{'file': file, 'at': at, 'w': im.width, 'h': im.height, 'ok': r != null && r.ok};
  if (r != null) {
    row['reading'] = {
      'min_span': r.minSpan, 'device': r.deviceShare, 'device_edge': r.deviceEdge, 'outside_max': r.outsideMax,
      'inside_min': r.insideMin, 'off_image': r.offImage, 'side_ratio': r.sideRatio,
    };
  }
  if (r != null && r.ok) {
    final g = gridFromFelt(r.quad, keep: keep);
    row['sticks'] = g?.sticks?.toList();
    row['quad'] = [for (final p in r.quad.corners) [p.x, p.y]];
  }
  return row;
}

void main(List<String> a) {
  final spec = jsonDecode(File(a[0]).readAsStringSync()) as Map<String, dynamic>;
  final out = <String, Object?>{'_note': 'felt_sticks.dart — 프레임별 펠트 판독 → 중앙 모서리 격자의 리치봉 구역(ymin,xmin,ymax,xmax)', 'jobs': <String, Object?>{}};
  final jobs = out['jobs'] as Map<String, Object?>;
  for (final j in (spec['jobs'] as List).cast<Map<String, dynamic>>()) {
    final id = j['id'] as String;
    final sw = Stopwatch()..start();
    GridZones? app = j['app_grid'] == null ? null : GridZones.fromJson((j['app_grid'] as Map).cast<String, dynamic>());
    final rows = <Map<String, Object?>>[];
    if (j['kind'] == 'zip') {
      final from = j['from'] as String?, to = j['to'] as String?;
      final n = (j['n'] as num?)?.toInt() ?? 15;
      final cand = <(String, String, ArchiveFile)>[];
      final grids = <String, (int, Map<String, dynamic>)>{};
      for (final z in (j['zips'] as List).cast<String>()) {
        final ar = ZipDecoder().decodeBytes(File(z).readAsBytesSync());
        final m = jsonDecode(utf8.decode(ar.findFile('frames.json')!.content as List<int>)) as Map<String, dynamic>;
        final gj = (m['grid'] as Map).cast<String, dynamic>();
        final key = jsonEncode(gj);
        var used = 0;
        for (final f in (m['frames'] as List).cast<Map<String, dynamic>>()) {
          final t = f['at'] as String;   // 태블릿 시계 글(시간대 없음) — 같은 꼴 글끼리 견줌
          if ((from != null && t.compareTo(from) < 0) || (to != null && t.compareTo(to) > 0)) continue;
          final file = ar.findFile(f['file'] as String);
          if (file != null) {
            cand.add((t, f['at'] as String, file));
            used++;
          }
        }
        final old = grids[key];
        grids[key] = ((old?.$1 ?? 0) + used, gj);
      }
      if (app == null && grids.isNotEmpty) {
        final best = grids.values.reduce((x, y) => x.$1 >= y.$1 ? x : y);
        app = GridZones.fromJson(best.$2);
      }
      cand.sort((x, y) => x.$1.compareTo(y.$1));
      for (final c in _even(cand, n)) {
        rows.add(_one(c.$3.name, c.$2, Uint8List.fromList(c.$3.content as List<int>), app));
      }
      jobs[id] = <String, Object?>{'kind': 'zip', 'candidates': cand.length, 'app_grids': [for (final v in grids.values) {'frames': v.$1, 'grid': v.$2}]};
    } else {
      for (final f in (j['files'] as List).cast<String>()) {
        rows.add(_one(f, null, File(f).readAsBytesSync(), app));
      }
      jobs[id] = <String, Object?>{'kind': 'jpg'};
    }
    final okRows = rows.where((r) => r['ok'] == true && r['sticks'] != null).toList();
    final res = jobs[id] as Map<String, Object?>;
    res['frames'] = rows;
    res['read'] = rows.length;
    res['ok'] = okRows.length;
    res['failed'] = rows.length - okRows.length;
    if (okRows.isNotEmpty) {
      final quads = [
        for (final r in okRows)
          () {
            final q = (r['quad'] as List).cast<List>();
            m.Point<double> pt(List v) => m.Point((v[0] as num).toDouble(), (v[1] as num).toDouble());
            return FeltQuad(pt(q[0]), pt(q[1]), pt(q[2]), pt(q[3]));
          }()
      ];
      final g = gridFromFelt(medianFelt(quads), keep: app);
      res['grid'] = g?.toJson();
      res['sticks'] = g?.sticks?.toList();
      final each = [for (var k = 0; k < 4; k++) _med([for (final r in okRows) ((r['sticks'] as List)[k] as num).toInt()])];
      res['sticks_median_each'] = each;
      var spread = 0;
      for (var k = 0; k < 4; k++) {
        final v = [for (final r in okRows) ((r['sticks'] as List)[k] as num).toInt()];
        final d = v.reduce((x, y) => x > y ? x : y) - v.reduce((x, y) => x < y ? x : y);
        if (d > spread) spread = d;
      }
      res['spread'] = spread;
      if (app != null && g != null) {
        res['app_sticks'] = app.sticks?.toList();
        res['shift'] = gridShiftOf(app, g);
      }
    } else if (app != null) {
      res['app_sticks'] = app.sticks?.toList();
    }
    res['shift_max'] = feltGridShiftMax;
    res['ms'] = sw.elapsedMilliseconds;
    stderr.writeln('$id ${res['kind']} 읽음 ${res['read']} · 믿을 판독 ${res['ok']} · 리치봉 ${res['sticks']} · 퍼짐 ${res['spread']} · 앱 ${res['app_sticks']} · shift ${res['shift']} · ${sw.elapsedMilliseconds}ms');
  }
  File(a[1]).writeAsStringSync(const JsonEncoder.withIndent(' ').convert(out));
}
