import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mahjong_calc/paifu/review_chat.dart';
import 'package:mahjong_calc/services/recognizer_client.dart';
import 'package:mahjong_calc/services/review_ask_client.dart';

final facts = <String, dynamic>{'version': 2, 'game': <String, dynamic>{}, 'turns': <dynamic>[], 'others': <dynamic>[]};

Map<String, dynamic> okBody({String outcome = 'verified'}) => {
      'answer': "6순에 [3만]을 버렸다면 유효패가 15장이었다. 위험은 '보통'이다.",
      'outcome': outcome,
      'tool_calls': [
        {'tool': 'turn_info', 'args': {'turn': 6}},
        {'tool': 'discard_options', 'args': {'turn': 6}},
      ],
      'violations': <String>[],
      'retries': outcome == 'verified' ? 0 : 1,
      'retry_violations': <dynamic>[],
      'prompt_version': 'a5',
      'model': 'fake',
      'elapsed_s': 2.5,
      'usage': {'llm_calls': 3, 'input_tokens': 100, 'output_tokens': 20},
    };

http.Response jsonRes(Object body, int code, {Map<String, String> headers = const {}}) => http.Response.bytes(
      utf8.encode(jsonEncode(body)),
      code,
      headers: {'content-type': 'application/json', ...headers},
    );

/// 응답 하나를 돌려주는 가짜 서버. 받은 요청은 [seen] 에.
ReviewAskClient client(http.Response Function() respond, List<http.Request> seen,
        {String key = 'k-123', Duration timeout = const Duration(seconds: 75)}) =>
    ReviewAskClient(
      baseUrl: 'http://srv.test',
      apiKey: key,
      timeout: timeout,
      httpClient: MockClient((req) async {
        seen.add(req);
        return respond();
      }),
    );

Future<ReviewAskException> failOf(Future<ReviewAnswer> f) async {
  try {
    await f;
  } on ReviewAskException catch (e) {
    return e;
  }
  fail('ReviewAskException 이 나야 함');
}

void main() {
  test('define 이 없으면 복기 주소 = 사진 판독 주소, 키 없음', () {
    expect(ReviewConfig.baseUrl, RecognizerConfig.baseUrl);
    expect(ReviewConfig.baseUrl, 'https://mahjong.ai-agent-develop.cloud');
    expect(ReviewConfig.apiKey, RecognizerConfig.apiKey);
    expect(ReviewConfig.isConfigured, RecognizerConfig.isConfigured);
  });

  group('200', () {
    test('verified — 답 · 차례 · 걸린 초, 보낸 요청의 URL · 헤더 · 본문', () async {
      final seen = <http.Request>[];
      final c = client(() => jsonRes(okBody(), 200), seen);
      final a = await c.ask(facts: facts, question: '  6순에 4만 버린 게 왜 실수야? ');
      expect(a.answer, startsWith('6순에 [3만]'));
      expect(a.verified, isTrue);
      expect(a.turns, [6]);
      expect(a.retries, 0);
      expect(a.elapsedS, 2.5);
      expect(a.promptVersion, 'a5');
      expect(a.model, 'fake');
      expect(a.raw['usage'], isA<Map<String, dynamic>>());

      final r = seen.single;
      expect(r.method, 'POST');
      expect(r.url.toString(), 'http://srv.test/v2/review/ask');
      expect(r.headers['X-Api-Key'], 'k-123');
      expect(r.headers['Content-Type'], 'application/json; charset=utf-8');
      // 한글이 \u 이스케이프 없이 UTF-8 바이트 그대로.
      expect(utf8.decode(r.bodyBytes), contains('"question":"6순에 4만 버린 게 왜 실수야?"'));
      final sent = jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>;
      expect(sent.keys.toList(), ['facts', 'question']); // history 가 비면 키 없음
      expect(sent['facts'], facts);
      expect(r.bodyBytes, utf8.encode(jsonEncode(askBody(facts: facts, question: '6순에 4만 버린 게 왜 실수야?'))));
    });

    test('history 를 보내면 최근 4쌍', () async {
      final seen = <http.Request>[];
      final c = client(() => jsonRes(okBody(), 200), seen);
      await c.ask(facts: facts, question: 'q', history: [for (var i = 0; i < 6; i++) ReviewExchange('q$i', 'a$i')]);
      final sent = jsonDecode(utf8.decode(seen.single.bodyBytes)) as Map<String, dynamic>;
      expect(sent['history'], [
        for (var i = 2; i < 6; i++) {'q': 'q$i', 'a': 'a$i'},
      ]);
    });

    test('fallback → verified false', () async {
      final a = await client(() => jsonRes(okBody(outcome: 'fallback'), 200), []).ask(facts: facts, question: 'q');
      expect(a.verified, isFalse);
      expect(a.retries, 1);
    });

    test('charset 없는 응답도 UTF-8 로 읽음', () async {
      final res = http.Response.bytes(utf8.encode(jsonEncode(okBody())), 200, headers: {'content-type': 'application/json'});
      final a = await client(() => res, []).ask(facts: facts, question: 'q');
      expect(a.answer, contains('유효패'));
    });

    test('깨진 JSON · 객체 아님 · answer 가 글이 아님 → badResponse', () async {
      for (final res in [
        http.Response('{not json', 200),
        jsonRes([1, 2], 200),
        jsonRes({'outcome': 'verified'}, 200),
        jsonRes({'answer': 3}, 200),
        http.Response.bytes([0xff, 0xfe, 0x7b], 200),
      ]) {
        final e = await failOf(client(() => res, []).ask(facts: facts, question: 'q'));
        expect(e.kind, ReviewAskError.badResponse, reason: res.body);
        expect(e.statusCode, 200);
      }
    });
  });

  group('오류 코드', () {
    final cases = <int, (ReviewAskError, String)>{
      401: (ReviewAskError.auth, 'API 키가 맞지 않습니다.'),
      404: (ReviewAskError.unavailable, '이 서버에는 복기 질문 기능이 없습니다.'),
      413: (ReviewAskError.tooLarge, '이 판은 너무 길어 질문할 수 없습니다.'),
      422: (ReviewAskError.badRequest, '서버가 질문을 받지 못했습니다(규격 밖).'),
      502: (ReviewAskError.upstream, '답을 만드는 모델 호출이 실패했습니다. 다시 시도하세요.'),
      503: (ReviewAskError.unavailable, '서버에 복기 설정이 없습니다.'),
      500: (ReviewAskError.server, '질문 실패 (HTTP 500)'),
      418: (ReviewAskError.server, '질문 실패 (HTTP 418)'),
    };
    for (final e in cases.entries) {
      test('${e.key}', () async {
        final ex = await failOf(
            client(() => jsonRes({'detail': 'x'}, e.key), []).ask(facts: facts, question: 'q'));
        expect(ex.kind, e.value.$1);
        expect(ex.message, e.value.$2);
        expect(ex.toString(), e.value.$2);
        expect(ex.statusCode, e.key);
        expect(ex.retryAfter, isNull);
      });
    }

    test('429 + Retry-After 숫자', () async {
      final ex = await failOf(client(() => jsonRes({'detail': 'x'}, 429, headers: {'retry-after': '17'}), [])
          .ask(facts: facts, question: 'q'));
      expect(ex.kind, ReviewAskError.rateLimited);
      expect(ex.retryAfter, const Duration(seconds: 17));
      expect(ex.message, '요청이 많습니다. 17초 뒤에 다시 시도하세요.');
      expect(ex.statusCode, 429);
    });

    test('429 + Retry-After 없음 · 숫자 아님(날짜) → 잠시 뒤에', () async {
      for (final h in [<String, String>{}, {'retry-after': 'Wed, 21 Oct 2026 07:28:00 GMT'}]) {
        final ex = await failOf(client(() => jsonRes({'detail': 'x'}, 429, headers: h), []).ask(facts: facts, question: 'q'));
        expect(ex.kind, ReviewAskError.rateLimited);
        expect(ex.retryAfter, isNull);
        expect(ex.message, '요청이 많습니다. 잠시 뒤에 다시 시도하세요.');
      }
    });
  });

  group('서버까지 못 감', () {
    test('ClientException → network', () async {
      final c = ReviewAskClient(
          baseUrl: 'http://srv.test',
          apiKey: 'k',
          httpClient: MockClient((_) async => throw http.ClientException('Connection refused')));
      final ex = await failOf(c.ask(facts: facts, question: 'q'));
      expect(ex.kind, ReviewAskError.network);
      expect(ex.message, '서버에 연결할 수 없습니다. 네트워크를 확인하세요.');
      expect(ex.statusCode, isNull);
    });

    test('시간 초과 → timeout(초는 timeout 값에서)', () async {
      final never = Completer<http.Response>();
      final c = ReviewAskClient(
          baseUrl: 'http://srv.test',
          apiKey: 'k',
          timeout: const Duration(seconds: 1),
          httpClient: MockClient((_) => never.future));
      final ex = await failOf(c.ask(facts: facts, question: 'q'));
      expect(ex.kind, ReviewAskError.timeout);
      expect(ex.message, '응답이 없습니다(1초). 다시 시도하세요.');
    });

    test('기본 시간 제한 75초 · 문구', () {
      expect(ReviewAskClient(apiKey: 'k').timeout, const Duration(seconds: 75));
    });

    test('키 없음 → notConfigured, 서버를 부르지 않음', () async {
      final seen = <http.Request>[];
      final ex = await failOf(client(() => jsonRes(okBody(), 200), seen, key: '').ask(facts: facts, question: 'q'));
      expect(ex.kind, ReviewAskError.notConfigured);
      expect(ex.message, '이 빌드에는 서버 키가 없어 질문할 수 없습니다.');
      expect(seen, isEmpty);
    });

    test('빈 질문 · 301자 → badRequest, 차례 41 → tooLarge, 서버를 부르지 않음', () async {
      final seen = <http.Request>[];
      final c = client(() => jsonRes(okBody(), 200), seen);
      var ex = await failOf(c.ask(facts: facts, question: '  '));
      expect((ex.kind, ex.message), (ReviewAskError.badRequest, askEmptyMessage));
      ex = await failOf(c.ask(facts: facts, question: '가' * 301));
      expect((ex.kind, ex.message), (ReviewAskError.badRequest, askTooLongMessage));
      ex = await failOf(c.ask(facts: {...facts, 'turns': List.filled(41, <String, dynamic>{})}, question: 'q'));
      expect((ex.kind, ex.message), (ReviewAskError.tooLarge, askTooLargeMessage));
      expect(seen, isEmpty);
    });
  });
}
