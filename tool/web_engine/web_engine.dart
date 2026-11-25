// 기록 사이트(mahjong-records)용 엔진 묶음의 진입점. `dart compile js` 로 묶는다(사이트 저장소 scripts/build_engine.sh).
//
// 전역 `mjEngine` 을 만든다:
//   mjEngine.score(paifuJson: string): string             — 끝 결과의 역 · 부 · 점수 · 지불(engine_api.dart scoreJson)
//   mjEngine.review(paifuJson: string, options?: string): string — 걸음별 평가 + 판 요약 + 단계 글(reviewJson)
//   mjEngine.version: string                               — 엔진 판 · 앱 저장소 sha(컴파일 때 -D 로 넣음)
//   mjEngine.apiVersion: number                            — 출력 꼴 판(engine_api.dart engineApiVersion)
// 입력은 앱 Paifu.toJson 꼴 JSON 글, 출력은 JSON 글. 실패하면 던지지 않고 `{"error": "…"}` 를 돌려준다.
// 다 만들면 전역 `mjEngineOnReady` 가 함수일 때 그것을 부른다(지연 로드하는 쪽이 기다릴 수 있게).
import 'dart:convert';
import 'dart:js_interop';
import 'dart:js_interop_unsafe';

import 'engine_api.dart';

const _sha = String.fromEnvironment('ENGINE_SHA', defaultValue: 'dev');

String _safe(String Function() f) {
  try {
    return f();
  } catch (e) {
    return jsonEncode({'error': 'engine: $e'});
  }
}

void main() {
  final o = JSObject();
  o['score'] = ((JSAny? json) => _safe(() => scoreJson(_str(json))).toJS).toJS;
  o['review'] = ((JSAny? json, [JSAny? options]) =>
      _safe(() => reviewJson(_str(json), options.isA<JSString>() ? (options as JSString).toDart : null)).toJS).toJS;
  o['version'] = 'mahjong_calc@$_sha'.toJS;
  o['apiVersion'] = engineApiVersion.toJS;
  globalContext['mjEngine'] = o;
  final ready = globalContext['mjEngineOnReady'];
  if (ready.isA<JSFunction>()) (ready as JSFunction).callAsFunction();
}

/// 글이 아니면 FormatException(→ {error}).
String _str(JSAny? v) {
  if (v.isA<JSString>()) return (v as JSString).toDart;
  throw const FormatException('패보 JSON 글을 넘기세요');
}
