/// 패보 복기 에이전트 서버 호출(`POST /v2/review/ask`): 사실표 + 질문 → 검증된 답.
///
/// 규격은 `docs/paifu_review_agent_app_design_1122.md` 1 · 4절, 서버는 mahjong-recognizer `app/main.py` `review_ask`.
/// 웹 빌드와 `dart run` 둘 다에서 돌아야 해서 `dart:io` · Flutter · `recognizer_client.dart`(dart:io 를 씀)를 쓰지 않는다.
/// 요청 본문 · 보내기 전 검사는 `lib/paifu/review_chat.dart`.
library;

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../paifu/review_chat.dart';

/// 복기 서버 설정. 따로 주지 않으면 사진 판독 서버(`RECOGNIZER_URL` · `RECOGNIZER_API_KEY`)와 같은 곳 · 같은 키.
/// 노트북 개발용 서버를 물릴 때만 `--dart-define=REVIEW_URL=http://...` · `REVIEW_API_KEY=...` 를 준다.
class ReviewConfig {
  static const String _url = String.fromEnvironment('REVIEW_URL');
  static const String _key = String.fromEnvironment('REVIEW_API_KEY');

  /// `RecognizerConfig.baseUrl` 과 같은 기본값(시험에서 같은지 확인).
  static const String _recognizerUrl = String.fromEnvironment(
    'RECOGNIZER_URL',
    defaultValue: 'https://mahjong.ai-agent-develop.cloud',
  );
  static const String _recognizerKey = String.fromEnvironment('RECOGNIZER_API_KEY');

  static const String baseUrl = _url == '' ? _recognizerUrl : _url;
  static const String apiKey = _key == '' ? _recognizerKey : _key;

  static bool get isConfigured => apiKey.isNotEmpty;
}

enum ReviewAskError {
  notConfigured,
  network,
  timeout,
  auth,
  tooLarge,
  badRequest,
  rateLimited,
  upstream,
  unavailable,
  server,
  badResponse,
}

/// 질문 실패. [message] 는 질문 창에 그대로 보일 한 줄.
class ReviewAskException implements Exception {
  final ReviewAskError kind;
  final String message;

  /// 429 의 `Retry-After`(초). 없거나 숫자가 아니면 null.
  final Duration? retryAfter;

  /// 서버가 답한 HTTP 상태(서버까지 못 갔으면 null).
  final int? statusCode;

  const ReviewAskException(this.kind, this.message, {this.retryAfter, this.statusCode});

  @override
  String toString() => message;
}

/// 서버의 답 하나.
class ReviewAnswer {
  final String answer;

  /// `outcome == 'verified'`. false 면 대체 답(검증에서 떨어져 코드가 만든 답, "확인된 사실만 답했습니다").
  final bool verified;

  /// "N순 보기" 칩에 쓸 차례(`answerTurns`).
  final List<int> turns;
  final int retries;
  final double? elapsedS;
  final String? promptVersion;
  final String? model;

  /// 응답 JSON 통째(기록 · 디버그용).
  final Map<String, dynamic> raw;

  const ReviewAnswer({
    required this.answer,
    required this.verified,
    required this.turns,
    required this.retries,
    required this.elapsedS,
    required this.promptVersion,
    required this.model,
    required this.raw,
  });

  /// 응답 JSON → 답. `answer` 가 글이 아니면 null.
  static ReviewAnswer? fromJson(Map<String, dynamic> j) {
    final a = j['answer'];
    if (a is! String) return null;
    final retries = j['retries'];
    final elapsed = j['elapsed_s'];
    final pv = j['prompt_version'];
    final model = j['model'];
    return ReviewAnswer(
      answer: a,
      verified: j['outcome'] == 'verified',
      turns: answerTurns(j),
      retries: retries is int ? retries : 0,
      elapsedS: elapsed is num ? elapsed.toDouble() : null,
      promptVersion: pv is String ? pv : null,
      model: model is String ? model : null,
      raw: j,
    );
  }
}

/// `POST /v2/review/ask` 를 부른다. 시험에서는 [httpClient] 로 가짜를 넣는다.
class ReviewAskClient {
  final String baseUrl;
  final String apiKey;

  /// 응답 본문까지 통째로의 시간 제한. 서버 한 질문 한도 60초 + 여유.
  final Duration timeout;
  final http.Client _http;

  ReviewAskClient({
    this.baseUrl = ReviewConfig.baseUrl,
    this.apiKey = ReviewConfig.apiKey,
    this.timeout = const Duration(seconds: 75),
    http.Client? httpClient,
  }) : _http = httpClient ?? http.Client();

  /// 질문 하나. 실패는 전부 [ReviewAskException].
  Future<ReviewAnswer> ask({
    required Map<String, dynamic> facts,
    required String question,
    List<ReviewExchange> history = const [],
  }) async {
    if (apiKey.isEmpty) {
      throw const ReviewAskException(ReviewAskError.notConfigured, '이 빌드에는 서버 키가 없어 질문할 수 없습니다.');
    }
    final body = askBody(facts: facts, question: question, history: history);
    // 서버가 거절할 요청은 보내지 않는다(호출 제한을 깎지 않게).
    final problem = askProblem(body);
    if (problem != null) {
      throw ReviewAskException(
          problem == askTooLargeMessage ? ReviewAskError.tooLarge : ReviewAskError.badRequest, problem);
    }
    final http.Response res;
    try {
      res = await _http
          .post(
            Uri.parse('$baseUrl/v2/review/ask'),
            headers: {'Content-Type': 'application/json; charset=utf-8', 'X-Api-Key': apiKey},
            body: utf8.encode(jsonEncode(body)),
          )
          .timeout(timeout);
    } on TimeoutException {
      throw ReviewAskException(ReviewAskError.timeout, '응답이 없습니다(${timeout.inSeconds}초). 다시 시도하세요.');
    } on http.ClientException {
      throw const ReviewAskException(ReviewAskError.network, '서버에 연결할 수 없습니다. 네트워크를 확인하세요.');
    } on Exception {
      // dart:io 를 안 써서 이름으로 못 잡는 연결 오류(TLS 등) — 사용자에게는 연결 실패와 같다.
      throw const ReviewAskException(ReviewAskError.network, '서버에 연결할 수 없습니다. 네트워크를 확인하세요.');
    }
    return _parse(res);
  }

  ReviewAnswer _parse(http.Response res) {
    final code = res.statusCode;
    switch (code) {
      case 200:
        break;
      case 401:
        throw const ReviewAskException(ReviewAskError.auth, 'API 키가 맞지 않습니다.', statusCode: 401);
      case 404:
        throw const ReviewAskException(ReviewAskError.unavailable, '이 서버에는 복기 질문 기능이 없습니다.', statusCode: 404);
      case 413:
        throw const ReviewAskException(ReviewAskError.tooLarge, askTooLargeMessage, statusCode: 413);
      case 422:
        throw const ReviewAskException(ReviewAskError.badRequest, '서버가 질문을 받지 못했습니다(규격 밖).', statusCode: 422);
      case 429:
        final s = int.tryParse((res.headers['retry-after'] ?? '').trim());
        final after = s != null && s >= 0 ? Duration(seconds: s) : null;
        final when = after == null ? '잠시 뒤에' : '$s초 뒤에';
        throw ReviewAskException(ReviewAskError.rateLimited, '요청이 많습니다. $when 다시 시도하세요.',
            retryAfter: after, statusCode: 429);
      case 502:
        throw const ReviewAskException(
            ReviewAskError.upstream, '답을 만드는 모델 호출이 실패했습니다. 다시 시도하세요.', statusCode: 502);
      case 503:
        throw const ReviewAskException(ReviewAskError.unavailable, '서버에 복기 설정이 없습니다.', statusCode: 503);
      default:
        throw ReviewAskException(ReviewAskError.server, '질문 실패 (HTTP $code)', statusCode: code);
    }
    const bad = ReviewAskException(ReviewAskError.badResponse, '서버 응답을 읽지 못했습니다.', statusCode: 200);
    final Object? j;
    try {
      // 헤더의 charset 과 상관없이 UTF-8(서버 JSON 은 UTF-8).
      j = jsonDecode(utf8.decode(res.bodyBytes));
    } on FormatException {
      throw bad;
    }
    if (j is! Map<String, dynamic>) throw bad;
    return ReviewAnswer.fromJson(j) ?? (throw bad);
  }

  void close() => _http.close();
}
