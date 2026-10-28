import '../engine/calculator.dart';

/// 결과 화면이 읽는 말 전부: 파일 이름(확장자 없음) → 말.
/// 미리 만든 음성 `assets/voice/<이름>.mp3` 가 있으면 그걸 틀고, 없으면 기기 TTS 로 읽는다.
/// 음성 파일은 `tool/make_voice.py` 가 이 목록(`dart run tool/voice_lines.dart` 의 JSON)으로 만든다.
/// 직접 녹음한 파일도 같은 이름으로 바꿔 넣으면 된다.
final Map<String, String> voiceLines = {
  'call_ron': '론',
  'call_tsumo': '쯔모',
  for (final y in Yaku.values)
    if (!_isDora(y)) 'yaku_${y.name}': y.label,
  for (var n = 1; n <= 12; n++) 'dora_$n': yakuSpeech(YakuHan(Yaku.dora, n)),
  for (var n = 1; n <= 4; n++) 'aka_$n': yakuSpeech(YakuHan(Yaku.akaDora, n)),
  for (var n = 1; n <= 12; n++) 'ura_$n': yakuSpeech(YakuHan(Yaku.uraDora, n)),
  for (final l in Limit.values)
    if (l != Limit.none && l != Limit.yakuman) 'grade_${l.name}': l.label,
  for (var n = 1; n <= 6; n++) 'yakuman_$n': _yakumanSpeech(n),
};

/// 설정에서 고를 수 있는 목소리: `assets/voice/<폴더>/` → 설명(Gemini TTS 목소리). 첫 번째가 기본.
/// 새 목소리는 `tool/make_voice.py` 의 VOICES 와 pubspec.yaml assets 에도 더한다.
const voiceChoices = {
  'Kore': '여성 · 또렷함',
  'Zephyr': '여성 · 밝음',
  'Leda': '여성 · 앳됨',
  'Puck': '남성 · 경쾌함',
  'Fenrir': '남성 · 힘참',
};

/// 음성 파일 대신 기기 TTS 로 읽는 선택.
const deviceVoice = 'tts';

/// 말 → 파일 이름.
final Map<String, String> voiceKeyOf = {for (final e in voiceLines.entries) e.value: e.key};

bool _isDora(Yaku y) => y == Yaku.dora || y == Yaku.akaDora || y == Yaku.uraDora;

/// 역 하나를 읽는 말. 도라 계열은 2장 이상이면 장 수를 붙인다(`도라 2`).
String yakuSpeech(YakuHan y) => _isDora(y.yaku) && y.han > 1 ? '${y.yaku.label} ${y.han}' : y.yaku.label;

/// 끝에 읽는 등급: 만관~헤아림 역만, 역만은 `역만`/`더블 역만`/`트리플 역만`/`4배 역만`. 등급이 없으면 빈 문자열.
String gradeSpeech(ScoreResult r) {
  if (!r.isValid) return '';
  if (r.isYakuman) return _yakumanSpeech(r.yakumanCount);
  return r.limit.label;
}

String _yakumanSpeech(int n) => switch (n) {
      <= 1 => '역만',
      2 => '더블 역만',
      3 => '트리플 역만',
      _ => '$n배 역만',
    };
