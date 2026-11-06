import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../engine/tile.dart';
import '../game/game.dart';
import '../table/merge.dart';
import '../table/table_layout.dart' show Side;
import '../table/table_reader.dart';

/// 정답(label.json)을 기다리는 촬영. 같은 국에서 "대국에 반영" 하면 그 값을 정답으로 남긴다.
class PendingCapture {
  final String dir;

  /// [CaptureLog.roundKey] 값. 촬영한 국과 기록한 국이 같을 때만 정답으로 쓴다.
  final String roundKey;
  final DateTime at;
  const PendingCapture(this.dir, this.roundKey, this.at);
}

/// 거치 촬영 기록을 폰의 `Download/mahjong_calc/<시각>/` 에 남긴다(원본·축소본·크롭·서버 응답·병합 결과).
/// 매장에서 그냥 플레이하며 찍기만 해도 정확도 측정용 데이터셋이 쌓이게 하는 것이 목적이다.
/// "대국에 반영" 하면 확정 값을 같은 폴더의 `label.json` 으로 남겨, 사진마다 정답이 붙는다.
/// 파일 쓰기는 Android MediaStore(Downloads) 를 쓰는 MainActivity 의 채널로 한다(권한 불필요, API 29+).
/// 채널이 없는 데스크톱(노트북·키오스크)에서는 사용자 다운로드 폴더의 `mahjong_calc/<시각>/` 에 같은 파일을 쓴다.
class CaptureLog {
  static const MethodChannel _channel = MethodChannel('dev.jjh.mahjong_calc/files');
  static const String prefKey = 'captureLog.enabled';
  static const String rootDir = 'Download/mahjong_calc';

  /// 촬영 뒤 이 시간 안에 기록해야 정답으로 쓴다(엉뚱한 화료가 붙는 것을 막는다).
  static const Duration labelWindow = Duration(minutes: 20);

  static PendingCapture? _pending;

  static Future<bool> isEnabled() async => (await SharedPreferences.getInstance()).getBool(prefKey) ?? true;

  static Future<void> setEnabled(bool v) async => (await SharedPreferences.getInstance()).setBool(prefKey, v);

  static String _stamp(DateTime t) {
    String two(int n) => n.toString().padLeft(2, '0');
    return '${t.year}${two(t.month)}${two(t.day)}_${two(t.hour)}${two(t.minute)}${two(t.second)}';
  }

  /// 한 번의 촬영이 쓸 폴더 이름. 촬영을 시작할 때 정해 정답 대기에도 쓴다.
  static String newDir([DateTime? now]) => '$rootDir/${_stamp(now ?? DateTime.now())}';

  /// 국을 구분하는 키. 화료하면 국이나 본장이 바뀌므로 촬영 국과 기록 국을 맞춰 볼 수 있다.
  static String roundKey(String roundLabel, int honba) => '$roundLabel#$honba';

  /// 이 촬영이 정답을 기다린다고 표시한다. 다음 촬영이 오면 덮어쓴다.
  static void setPending(String dir, String roundKey, {DateTime? now}) {
    _pending = PendingCapture(dir, roundKey, now ?? DateTime.now());
  }

  /// 같은 국이고 [labelWindow] 안이면 대기 중인 폴더를 돌려주고 비운다. 아니면 null.
  static String? takePending(String roundKey, {DateTime? now}) {
    final p = _pending;
    if (p == null) return null;
    final t = now ?? DateTime.now();
    if (p.roundKey != roundKey || t.difference(p.at) > labelWindow) return null;
    _pending = null;
    return p.dir;
  }

  /// 테스트용.
  static void clearPending() => _pending = null;

  /// 기록 형식의 패 코드. 적도라는 `0m` 처럼 0 으로 쓴다.
  static String tileCode(int tile, {bool red = false}) {
    final c = Tiles.toCode(tile);
    return red ? '0${c[1]}' : c;
  }

  /// 한 번의 촬영을 [dir] 에 저장한다. 돌려주는 값은 폴더 이름, 저장할 수 없으면 null.
  /// [setup] 은 촬영 조건(출처·줌·높이 등)으로 meta.json 의 `setup` 에 들어간다.
  static Future<String?> save({
    required String dir,
    required Uint8List original,
    TableReadTrace? trace,
    TableMerge? merge,
    Game? game,
    String? error,
    List<String> warnings = const [],
    int? captureLongSide,
    Map<String, Object?> setup = const {},
  }) async {
    final now = DateTime.now();
    final files = <(String, Uint8List, String)>[
      ('original.jpg', original, 'image/jpeg'),
      if (trace?.small != null) ('locate_input.jpg', trace!.small!, 'image/jpeg'),
      if (trace?.handCrop != null) ('hand_${trace!.winnerSide?.name ?? 'x'}.jpg', trace.handCrop!, 'image/jpeg'),
      if (trace?.centerCrop != null) ('center.jpg', trace!.centerCrop!, 'image/jpeg'),
      for (final (i, m) in (trace?.meldCrops ?? const <Uint8List>[]).indexed) ('meld_$i.jpg', m, 'image/jpeg'),
      for (final e in (trace?.riverCrops ?? const <Side, Uint8List>{}).entries)
        ('river_${e.key.name}.jpg', e.value, 'image/jpeg'),
      if (trace?.observation != null) ('observation.json', jsonBytes(trace!.observation!.toJson()), 'application/json'),
      if (trace?.wallCrop != null) ('wall.jpg', trace!.wallCrop!, 'image/jpeg'),
      if (trace?.dealerDoraCrop != null) ('dora_dealer.jpg', trace!.dealerDoraCrop!, 'image/jpeg'),
      if (trace?.wall != null) ('wall.json', jsonBytes(trace!.wall!.toJson()), 'application/json'),
      if (trace?.layout != null) ('locate.json', jsonBytes(trace!.layout!.toJson()), 'application/json'),
      if (trace?.hand != null) ('hand.json', jsonBytes(trace!.hand!.toJson()), 'application/json'),
      if (trace?.center != null) ('center.json', jsonBytes(trace!.center!.toJson()), 'application/json'),
      if (trace?.wide != null) ('seatwide.json', jsonBytes(trace!.wide!), 'application/json'),
      if (trace != null && trace.shadow.isNotEmpty)
        ('shadow.json', jsonBytes({for (final e in trace.shadow.entries) e.key.name: e.value.toJson()}), 'application/json'),
      (
        'meta.json',
        jsonBytes(_meta(now, trace, merge, game, error, warnings, captureLongSide, setup)),
        'application/json',
      ),
    ];
    for (final (name, bytes, mime) in files) {
      if (!await saveFile(dir, name, bytes, mime)) return null;
    }
    return dir;
  }

  /// 파일 하나를 [dir] 에 쓴다. Android 채널이 없으면 데스크톱 폴더([desktopBase])에, 그것도 없거나 실패하면 false.
  /// Android 는 같은 이름이 있으면 `이름 (1)` 로 새로 만든다. [overwrite] 면 같은 이름 파일을 덮어쓴다(데스크톱은 늘 덮어씀).
  static Future<bool> saveFile(String dir, String name, Uint8List bytes, String mime, {bool overwrite = false}) async {
    try {
      await _channel.invokeMethod<String>(
          'save', {'dir': dir, 'name': name, 'bytes': bytes, 'mime': mime, 'overwrite': overwrite});
      return true;
    } on MissingPluginException {
      return _saveDesktop(dir, name, bytes);
    } on PlatformException {
      return false;
    }
  }

  /// 데스크톱 기록 폴더를 바꾼다(테스트용). null 이면 기본(사용자 다운로드 폴더).
  static String? desktopRootOverride;

  /// 데스크톱에서 `Download/...` 를 놓을 바탕 폴더. 데스크톱이 아니거나 `flutter test` 중이면 null
  /// (테스트가 실제 다운로드 폴더에 쓰지 않게 — 테스트는 [desktopRootOverride] 로 임시 폴더를 준다).
  static String? get desktopBase {
    if (desktopRootOverride != null) return desktopRootOverride;
    if (kIsWeb || !(Platform.isWindows || Platform.isLinux || Platform.isMacOS)) return null;
    if (Platform.environment.containsKey('FLUTTER_TEST')) return null;
    final home = Platform.environment[Platform.isWindows ? 'USERPROFILE' : 'HOME'];
    return home == null ? null : '$home/Downloads';
  }

  static Future<bool> _saveDesktop(String dir, String name, Uint8List bytes) async {
    final base = desktopBase;
    if (base == null) return false;
    // dir 은 Android 기준 'Download/mahjong_calc/<시각>' — 앞의 'Download/' 를 다운로드 폴더로 바꾼다.
    final rel = dir.startsWith('Download/') ? dir.substring('Download/'.length) : dir;
    try {
      final f = File('$base/$rel/$name');
      await f.parent.create(recursive: true);
      await f.writeAsBytes(bytes);
      return true;
    } on FileSystemException {
      return false;
    }
  }

  static Future<bool> saveLabel(String dir, Map<String, Object?> label) =>
      saveFile(dir, 'label.json', jsonBytes(label), 'application/json');

  static Uint8List jsonBytes(Object o) => Uint8List.fromList(utf8.encode(const JsonEncoder.withIndent(' ').convert(o)));

  static Map<String, dynamic> _meta(
    DateTime now,
    TableReadTrace? trace,
    TableMerge? merge,
    Game? game,
    String? error,
    List<String> warnings,
    int? captureLongSide,
    Map<String, Object?> setup,
  ) {
    return {
      'time': now.toIso8601String(),
      'capture_long_side_px': captureLongSide,
      'setup': setup,
      'game': game == null
          ? null
          : {
              'round': game.roundLabel,
              'names': game.names,
              'bottom_seat': game.settings.bottomSeat,
              'dealer': game.dealer,
              'honba': game.honba,
              'riichi_seats': game.riichiSeats.toList()..sort(),
            },
      'winner_side': trace?.winnerSide?.name,
      'timings_ms': trace?.timingsMs,
      'layout_mode': trace?.layoutMode,
      'tracked_mode': trace == null ? null : {for (final e in trace.trackedMode.entries) e.key.name: e.value},
      'call_ms': trace?.callMs,
      'server_timing': trace?.serverTiming,
      'local_shadow': trace?.localShadow,
      if (trace != null && trace.riverSideways.isNotEmpty)
        'river_sideways': {for (final e in trace.riverSideways.entries) e.key.name: e.value},
      if (trace?.autoMultiRon ?? false) 'auto_multi_ron': true,
      if (trace?.feltQuad case final q?) 'felt_quad': q.toJson(),  // 펴서 읽었으면 원본 사진의 펠트 네 모서리
      if (trace?.gridSrc case final s?) 'grid_src': s.query, // 서버에 보낸 격자 출처(8b-4a)
      if (trace?.lastFull ?? false) 'last_full': true, // 강 끝을 사진 전체로 보냄(grid_src none)
      'fixed_analysis': trace?.analysis?.toJson(),
      'warnings': warnings,
      'error': error,
      'merge': merge == null ? null : mergeJson(merge),
    };
  }

  /// 병합 결과를 label.json 과 같은 키로 적는다(집계 스크립트가 둘을 바로 비교한다).
  static Map<String, dynamic> mergeJson(TableMerge merge) => {
    'winner': merge.winner,
    'is_tsumo': merge.isTsumo,
    'loser': merge.loser,
    'closed': [for (final t in merge.closed) tileCode(t.tile, red: t.red)],
    'win_tile': merge.closed.isEmpty ? null : tileCode(merge.closed.last.tile, red: merge.closed.last.red),
    'melds': [for (final m in merge.melds) m.toString()],
    'red_count': merge.redCount,
    'hand_valid': merge.hand != null,
    if (merge.winCandidates.isNotEmpty) 'win_candidates': [for (final t in merge.winCandidates) tileCode(t)],
    'uncertain': merge.uncertain.toList()..sort(),
    'flags': [for (final f in merge.flags) f.toString()],
    'riichi': merge.situation.riichi,
    'double_riichi': merge.situation.doubleRiichi,
    'ippatsu': merge.situation.ippatsu,
    'riichi_seats_photo': merge.photoRiichiSeats.toList()..sort(),
    'dora_indicators': [for (final t in merge.situation.doraIndicators) tileCode(t)],
    'ura_indicators': [for (final t in merge.situation.uraIndicators) tileCode(t)],
  };
}
