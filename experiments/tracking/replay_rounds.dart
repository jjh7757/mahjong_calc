// ignore_for_file: avoid_print
// 판(추적 폴더)마다 프레임을 앱 흐름(mount_screen `_trackFrame`·`_watchFelt`)대로 다시 넣어 리치 추적·일발 후보·울기 픽셀 추적의
// "늘어남" 을 세 조건으로 낸다(2026-11-16, 일발 누락 원인 둘을 고친 것의 앞뒤 비교). 프레임은 한 번만 푼다.
//   A = 그날 저장 격자 + 예전 일발 판정(모서리 칸 통째, 어느 자리든 늘면 일발 지움)
//   B = 펠트 첫 기준과 견줘 고친 격자(`gridShiftOf` ≥ `feltGridShiftMax` 면 펠트 격자) + 예전 일발 판정
//   C = B 격자 + 펠트 안쪽으로 자른 모서리 칸 + 새 일발 판정(다른 세 자리만, 자기 모서리는 따로)
// 펠트는 앱처럼 프레임 2장마다 읽어 `FeltWatch` 에 넣는다: 처음 기준을 잡으면 저장 격자와 견주고, 그 뒤 카메라가 옮겨지면 다시 맞춘다
// (다시 맞추면 앱 `_saveGrid` 처럼 추적기를 새로 만든다). 같은 저장 격자가 이어지는 폴더끼리는 펠트 기준·고친 격자를 이어받는다.
//   dart run experiments/tracking/replay_rounds.dart <out.json> <auto 0|1> <추적 폴더>...
// auto 1 = 저장 격자가 펠트 없이 자동으로 맞춘 것(앱 `gridCheckFeltPref`) → 첫 기준과 어긋나면 다시 맞춘다(11-14 2반장 = localsetup).
// auto 0 = 손으로 맞춰 저장한 격자(10-31·11-07) → 첫 기준에서는 안 고치고, 그 뒤 카메라가 옮겨졌을 때만(예전부터 있던 동작).
// 화료 시각·정답 리치 자리는 같은 captures 폴더의 그 판 화료 기록(meta.json)에서 읽는다.
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:archive/archive.dart';
import 'package:mahjong_calc/table/corner_change.dart';
import 'package:mahjong_calc/table/felt_grid.dart';
import 'package:mahjong_calc/table/fixed_layout.dart' show decodeSmall, whiteMask;
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/river_change.dart';
import 'package:mahjong_calc/table/river_tracker.dart';
import 'package:mahjong_calc/table/scene_shift.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/tracker.dart';

String hms(DateTime t) => t.toIso8601String().substring(11, 19);

DateTime? stamp(String name) {
  final m = RegExp(r'^(\d{4})(\d\d)(\d\d)_(\d\d)(\d\d)(\d\d)').firstMatch(name);
  if (m == null) return null;
  final v = [for (var i = 1; i <= 6; i++) int.parse(m.group(i)!)];
  return DateTime(v[0], v[1], v[2], v[3], v[4], v[5]);
}

class Run {
  final String name;
  final double aspect;
  GridZones grid;
  final bool newRule;
  late RiverTracker rt;
  late MeldTracker mt;
  var gate = SceneShiftGate();
  final grew = <List<Object>>[];
  final lastGrew = <Side, DateTime?>{};
  int shifts = 0;
  Run(this.name, this.grid, this.aspect, {required this.newRule}) {
    rt = RiverTracker(tileFrac: riverTileFracsOf(grid, aspect: aspect));
    mt = MeldTracker(tileFrac: tileFracsOf(grid, aspect: aspect), config: const TrackerConfig(pixelOnly: true));
  }

  /// 격자를 바꾼다. [meldOnly] 면 울기 추적기만 새로(펠트 상자만 채운 경우), 아니면 앱 `_saveGrid` 처럼 둘 다.
  void regrid(GridZones g, {bool meldOnly = false}) {
    if (g == grid) return;
    grid = g;
    mt = MeldTracker(tileFrac: tileFracsOf(grid, aspect: aspect), config: const TrackerConfig(pixelOnly: true));
    lastGrew.clear();
    if (meldOnly) return;
    rt = RiverTracker(tileFrac: riverTileFracsOf(grid, aspect: aspect));
    gate = SceneShiftGate();
  }

  void frame(TableFrameStats stats, DateTime t) {
    if (gate.check(stats)) {
      shifts++;
      mt.cameraMoved(t);
      rt.cameraMoved(t);
    }
    mt.onFrame(stats.watchCorners, t);
    rt.onFrame(stats.rivers, stats.strips, t, sticksSeen: stats.sticksSeen);
    for (final s in Side.values) {
      final g = mt.seat(s).grewAt;
      if (g != null && g != lastGrew[s]) grew.add([hms(t), s.name]);
      lastGrew[s] = g;
    }
  }

  Map<String, Object?> result() {
    final selfGrew = {
      for (final e in rt.riichiAt.entries)
        if (mt.seat(e.key).grewAt?.isAfter(e.value.at) ?? false) e.key,
    };
    final ipp = newRule
        ? rt.ippatsuCandidates(meldGrewSince: (t, s) => mt.grewSince(t, except: s))
        : rt.ippatsuCandidates(meldGrewSince: (t, s) => mt.grewSince(t));
    return {
      'grid': grid.toJson(),
      'riichi': [for (final s in rt.riichi) s.name],
      'riichi_at': {
        for (final e in rt.riichiAt.entries)
          e.key.name: {'own': e.value.own, 'total': e.value.total, 'taken': e.value.taken, 'at': hms(e.value.at)},
      },
      'ippatsu_river': [for (final s in rt.ippatsuCandidates()) s.name],
      'ippatsu': [for (final s in ipp) s.name],
      'self_grew': [for (final s in selfGrew) s.name],
      'grew': grew,
      'shifts': shifts,
      'discards': {for (final e in rt.discardCounts.entries) e.key.name: e.value},
      // 마지막으로 격자를 바꾼 뒤의 강 사건(장면 전체 변화 포함).
      'river_events': [for (final e in rt.events) '${hms(e.at)} ${e.side.name} ${e.kind} ${e.detail}'],
    };
  }
}

void main(List<String> a) {
  final out = a[0];
  final auto = a[1] == '1';
  final result = <String, Object?>{};
  // 폴더 사이에 이어받는 것(같은 저장 격자가 이어질 때): 펠트 기준과 고친 격자.
  var watch = FeltWatch();
  GridZones? prevSaved, gB, gC;
  for (final dir in a.skip(2)) {
    final d = Directory(dir);
    final name = d.uri.pathSegments.where((s) => s.isNotEmpty).last;
    final start = stamp(name)!;
    // 이 판의 화료 기록: 이 추적 폴더 뒤, 다음 추적 폴더 전.
    final sib = d.parent.listSync().whereType<Directory>().map((x) => x.uri.pathSegments.where((s) => s.isNotEmpty).last).toList()..sort();
    final nextTrack = sib.where((n) => n.endsWith('_track') && stamp(n) != null && stamp(n)!.isAfter(start)).map((n) => stamp(n)!).fold<DateTime?>(
        null, (m, t) => m == null || t.isBefore(m) ? t : m);
    DateTime? win;
    final truth = <String>{};
    String? winner;
    final caps = <String>[];
    for (final n in sib) {
      if (!RegExp(r'^\d{8}_\d{6}$').hasMatch(n)) continue;
      final t = stamp(n)!;
      if (!t.isAfter(start) || (nextTrack != null && t.isAfter(nextTrack))) continue;
      final mf = File('${d.parent.path}/$n/meta.json');
      if (!mf.existsSync()) continue;
      final m = jsonDecode(mf.readAsStringSync()) as Map<String, dynamic>;
      final merge = m['merge'];
      if (merge is! Map || merge['riichi_seats_photo'] == null) continue;
      win ??= t;
      caps.add(n);
      final bottom = ((m['game'] as Map)['bottom_seat'] as num).toInt();
      truth
        ..clear()
        ..addAll([for (final s in merge['riichi_seats_photo'] as List) Side.values[((s as num).toInt() - bottom) % 4].name]);
      winner = m['winner_side'] as String?;
    }

    final zips = d.listSync().whereType<File>().where((f) => RegExp(r'frames_\d+\.zip$').hasMatch(f.path)).toList()
      ..sort((x, y) => x.path.compareTo(y.path));
    final frames = <(DateTime, ArchiveFile)>[];
    GridZones? saved;
    for (final z in zips) {
      final ar = ZipDecoder().decodeBytes(z.readAsBytesSync());
      final j = jsonDecode(utf8.decode(ar.findFile('frames.json')!.content as List<int>)) as Map<String, dynamic>;
      saved ??= GridZones.fromJson(j['grid'] as Map<String, dynamic>);
      for (final f in j['frames'] as List) {
        final file = ar.findFile(f['file'] as String);
        if (file != null) frames.add((DateTime.parse(f['at'] as String), file));
      }
    }
    if (saved == null || frames.isEmpty) continue;
    frames.sort((x, y) => x.$1.compareTo(y.$1));
    final g0 = saved.withFeltBox(null);

    if (prevSaved != g0) {
      watch = FeltWatch();
      gB = g0;
      gC = g0;
      prevSaved = g0;
    }
    final regrids = <List<Object?>>[];
    Run? rA, rB, rC;
    for (var i = 0; i < frames.length; i++) {
      final t = frames[i].$1;
      if (win != null && t.isAfter(win)) break;
      final im = decodeSmall(Uint8List.fromList(frames[i].$2.content as List<int>));
      final white = whiteMask(im);
      if (rA == null) {
        final aspect = im.width / im.height;
        rA = Run('A', g0, aspect, newRule: false);
        rB = Run('B', gB!, aspect, newRule: false);
        rC = Run('C', gC!, aspect, newRule: true);
      }
      for (final r in [rA, rB!, rC!]) {
        r.frame(tableFrameStatsOf(im, white, r.grid), t);
      }
      if (i.isEven) continue;
      final fr = readFelt(im);
      var moved = watch.add(fr != null && fr.ok ? fr.quad : null);
      if (moved == null && watch.adoptedFirst) {
        final basis = watch.basis!;
        final fromFelt = gridFromFelt(basis, keep: rC.grid);
        if (fromFelt == null) continue;
        final shift = gridShiftOf(rC.grid, fromFelt);
        if (shift < feltGridShiftMax || !auto) {
          regrids.add([hms(t), 'first-keep', shift]);
          gC = rC.grid.withFeltBox(shift < feltGridShiftMax ? feltBoxOf(basis) : null);
          rC.regrid(gC, meldOnly: true);
          continue;
        }
        regrids.add([hms(t), 'first-regrid', shift]);
        moved = basis;
      } else if (moved != null) {
        regrids.add([hms(t), 'moved', null]);
      }
      if (moved == null) continue;
      final g = gridFromFelt(moved, keep: rC.grid);
      if (g == null) continue;
      gB = g.withFeltBox(null);
      gC = g;
      rB.regrid(gB);
      rC.regrid(gC);
    }
    if (rA == null) continue;
    final runs = [rA, rB!, rC!];
    result[name] = {
      'frames': frames.length,
      'from': hms(frames.first.$1),
      'win': win == null ? null : hms(win),
      'captures': caps,
      'winner': winner,
      'truth_riichi': truth.toList(),
      'regrids': regrids,
      for (final r in runs) r.name: r.result(),
    };
    final c = runs[2].result(), a0 = runs[0].result();
    stderr.writeln('$name 정답 ${truth.toList()} 격자 $regrids | A 리치 ${a0['riichi']} 일발 ${a0['ippatsu']} 늘어남 ${(a0['grew'] as List).length}'
        ' | C 리치 ${c['riichi']} 일발(강) ${c['ippatsu_river']} 일발 ${c['ippatsu']} 자기 ${c['self_grew']} 늘어남 ${(c['grew'] as List).length}');
    File(out).writeAsStringSync(const JsonEncoder.withIndent(' ').convert(result));
  }
}
