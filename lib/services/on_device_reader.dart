import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 기기 판독 실험(exp/on-device-read, 2026-11-11): 서버 자체 판독 세 엔드포인트를 앱 안 Python(Chaquopy, `OnDeviceReader.kt`)으로.
/// 켜져 있으면 [RecognizerClient.observe]·[RecognizerClient.observeLasts] 가 [kinds] 를 서버 대신 여기로 보낸다(응답 JSON 은 서버와 같은 모양
/// + `ondevice` 기기 시간). 끄면 서버 그대로 — 되돌리기는 거치 화면 더보기 스위치.
class OnDeviceReader {
  static const String pref = 'mount.onDeviceRead';
  static const Set<String> kinds = {'localroles', 'localdora', 'locallast3'};
  static const MethodChannel _ch = MethodChannel('dev.jjh.mahjong_calc/ondevice');

  /// 지금 켜져 있는지(안드로이드에서만 의미). [load]·[setEnabled] 가 정한다.
  static bool enabled = false;

  /// 테스트에서 안드로이드인 척할 때만.
  @visibleForTesting
  static bool? debugSupported;

  static bool get supported => debugSupported ?? (!kIsWeb && Platform.isAndroid);

  static bool handles(String kind) => enabled && supported && kinds.contains(kind);

  /// 켜져 있으면 서버는 아예 부르지 않는다(2026-11-12 사용자 결정). 매장 핫스팟엔 인터넷이 없어, 서버 호출은 실패를 기다리는
  /// 동안 판 중 추적을 막기만 했다(리치봉 읽기 `_trackBusy`). 기기에 없는 판독은 서버가 안 될 때와 같은 길로 간다.
  static bool get blocksServer => enabled && supported;

  static Future<void> load() async {
    try {
      final p = await SharedPreferences.getInstance();
      enabled = p.getBool(pref) ?? false;
    } catch (_) {}
  }

  static Future<void> setEnabled(bool on) async {
    enabled = on;
    try {
      final p = await SharedPreferences.getInstance();
      await p.setBool(pref, on);
    } catch (_) {}
  }

  /// 서버 `/v2/{kind}?query` 와 같은 답. 실패하면 [PlatformException].
  static Future<Map<String, dynamic>> observe(String kind, List<Uint8List> images, Map<String, String>? query) async {
    final s = await _ch.invokeMethod<String>('observe', {'kind': kind, 'images': images, 'query': query ?? const <String, String>{}});
    return jsonDecode(s!) as Map<String, dynamic>;
  }

  /// 판 중 겹쳐 보기(실험): 사진 전체의 앞면 패마다 상자(0~1)·종류·역할. [grid] 는 역할을 자리별로 고를 때 쓴다(x1·x2·y1·y2, 1000 분율).
  static Future<TileOverlay> overlay(Uint8List image, Map<String, String> grid) async {
    final s = await _ch.invokeMethod<String>('overlay', {'image': image, 'query': grid});
    return TileOverlay.fromJson(jsonDecode(s!) as Map<String, dynamic>);
  }

  /// 측정용: 기기 판독의 prepare 방식("server" = 서버처럼 q90 재저장 | "skip" = 받은 JPEG 그대로).
  static Future<String?> setPrep(String v) => _ch.invokeMethod<String>('setPrep', v);

  /// Python·모델을 미리 올린다. 걸린 시간 JSON(import_ms·total_ms).
  static Future<Map<String, dynamic>> warmup() async {
    final s = await _ch.invokeMethod<String>('warmup');
    return jsonDecode(s!) as Map<String, dynamic>;
  }
}

/// 겹쳐 보기 한 장면: 패마다 상자(사진 비율 0~1)·종류·확신도·역할·자리.
class OverlayTile {
  final double x, y, w, h;
  final String tile, role, side;
  final double tileConf, roleConf;
  const OverlayTile(this.x, this.y, this.w, this.h, this.tile, this.tileConf, this.role, this.roleConf, this.side);
}

class TileOverlay {
  final List<OverlayTile> tiles;
  final Map<String, int> ms;
  final DateTime at;
  TileOverlay(this.tiles, this.ms, this.at);

  factory TileOverlay.fromJson(Map<String, dynamic> j) => TileOverlay(
        [
          for (final t in (j['tiles'] as List).cast<Map<String, dynamic>>())
            OverlayTile(
              ((t['b'] as List)[0] as num).toDouble(),
              ((t['b'] as List)[1] as num).toDouble(),
              ((t['b'] as List)[2] as num).toDouble(),
              ((t['b'] as List)[3] as num).toDouble(),
              t['t'] as String,
              (t['tc'] as num).toDouble(),
              t['r'] as String,
              (t['rc'] as num).toDouble(),
              t['s'] as String,
            ),
        ],
        {for (final e in (j['ms'] as Map).entries) e.key as String: (e.value as num).toInt()},
        DateTime.now(),
      );
}
