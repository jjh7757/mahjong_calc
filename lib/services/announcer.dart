import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'voice_lines.dart';

export 'voice_lines.dart' show yakuSpeech, gradeSpeech, voiceChoices, deviceVoice;

/// 작혼처럼 화료 결과(론·쯔모, 역, 도라, 등급)를 소리 내어 읽는다. 고른 목소리의 미리 만든 음성 파일
/// (`assets/voice/<목소리>/`, [voiceLines])이 있으면 그걸 틀고, 없거나 못 틀면 기기 TTS(Android·웹·Windows)로 읽는다.
/// 플러그인이 없는 곳(테스트)에서는 조용히 아무 일도 하지 않는다.
class Announcer {
  static const _key = 'voice.result';
  static const _voiceKey = 'voice.name';
  static FlutterTts? _tts;
  static AudioPlayer? _player;

  /// 음성 파일 하나(`<목소리>/<이름>`)를 끝까지 튼다. 못 틀면 false(그러면 TTS). 테스트가 바꿔 끼운다.
  static Future<bool> Function(String path) playClip = _playAsset;

  /// 고른 목소리([voiceChoices] 의 폴더 또는 [deviceVoice]). 기본은 [voiceChoices] 의 첫 번째.
  static Future<String> voice() async {
    try {
      final p = await SharedPreferences.getInstance();
      final v = p.getString(_voiceKey);
      if (v == deviceVoice || voiceChoices.containsKey(v)) return v!;
    } catch (_) {}
    return voiceChoices.keys.first;
  }

  static Future<void> setVoice(String v) async {
    final p = await SharedPreferences.getInstance();
    await p.setString(_voiceKey, v);
  }

  static int _previewRun = 0;

  /// 설정 화면의 미리 듣기: 예시 결과를 지금 목소리로 읽는다. 다시 누르면 앞의 것은 멈춘다.
  static Future<void> preview() async {
    final run = ++_previewRun;
    await stop();
    for (final t in const ['쯔모', '리치', '이페코', '도라 2', '하네만']) {
      if (run != _previewRun) return;
      await say(t);
    }
  }

  /// 결과 음성 켜짐(기본 켬).
  static Future<bool> enabled() async {
    try {
      final p = await SharedPreferences.getInstance();
      return p.getBool(_key) ?? true;
    } catch (_) {
      return false;
    }
  }

  static Future<void> setEnabled(bool on) async {
    final p = await SharedPreferences.getInstance();
    await p.setBool(_key, on);
    if (!on) await stop();
  }

  static Future<FlutterTts> _ready() async {
    if (_tts != null) return _tts!;
    final tts = FlutterTts();
    await tts.setLanguage('ko-KR');
    // speak 가 다 읽은 뒤에 끝나게 한다(결과 화면이 읽기에 맞춰 다음 줄을 띄운다).
    await tts.awaitSpeakCompletion(true);
    return _tts = tts;
  }

  static Future<bool> _playAsset(String path) async {
    try {
      final p = _player ??= AudioPlayer();
      await p.stop();
      final done = p.onPlayerComplete.first;
      await p.play(AssetSource('voice/$path.mp3'));
      // 끊으면(stop) 완료 알림이 오지 않아 시간 제한으로 넘어간다.
      await done.timeout(const Duration(seconds: 4));
      return true;
    } on TimeoutException {
      return true;
    } catch (_) {
      return false;
    }
  }

  /// [text] 를 읽고 다 읽으면 끝난다. 앞서 읽던 것은 끊는다. 못 읽으면(파일·플러그인·엔진 없음) false.
  /// 웹 TTS 는 끊긴 읽기의 완료를 알리지 않아, 너무 길면 시간 제한으로 넘어간다.
  static Future<bool> say(String text) async {
    if (text.isEmpty) return true;
    final key = voiceKeyOf[text];
    final v = await voice();
    if (key != null && v != deviceVoice && await playClip('$v/$key')) return true;
    try {
      final tts = await _ready();
      await tts.speak(text).timeout(const Duration(seconds: 5));
      return true;
    } on TimeoutException {
      return true;
    } catch (_) {
      return false;
    }
  }

  static Future<void> stop() async {
    try {
      await _player?.stop();
    } catch (_) {}
    try {
      await _tts?.stop();
    } catch (_) {}
  }
}
