// 손패 복원 도구 루프 · API 클라이언트 시험 — 실제 API 는 부르지 않는다(package:http/testing MockClient).
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/paifu/hand_restore/claude_client.dart';
import 'package:mahjong_calc/paifu/hand_restore/frames.dart';
import 'package:mahjong_calc/paifu/hand_restore/turn_agent.dart';

TurnFrames _frames(int count) {
  final jpg = img.encodeJpg(img.Image(width: 200, height: 60), quality: 60);
  return TurnFrames(
    ms: [for (var i = 0; i < count; i++) 1763700000000 + i * 200],
    jpegs: List<Uint8List>.filled(count, jpg),
    width: 200,
    height: 60,
  );
}

Map<String, dynamic> _use(String id, String name, Map<String, dynamic> input) =>
    {'type': 'tool_use', 'id': id, 'name': name, 'input': input};
Map<String, dynamic> _text(String t) => {'type': 'text', 'text': t};
Map<String, dynamic> _think(String t, String sig) => {'type': 'thinking', 'thinking': t, 'signature': sig};

Map<String, dynamic> _msg(List<Map<String, dynamic>> content,
        {String stop = 'tool_use', int input = 1000, int output = 200, int cacheRead = 0, int cacheWrite = 0}) =>
    {
      'id': 'msg_x',
      'type': 'message',
      'role': 'assistant',
      'model': claudeModel,
      'content': content,
      'stop_reason': stop,
      'stop_sequence': null,
      'usage': {
        'input_tokens': input,
        'output_tokens': output,
        'cache_read_input_tokens': cacheRead,
        'cache_creation_input_tokens': cacheWrite,
      },
    };

/// 최종 메시지를 SSE 로 쪼갠다(thinking · signature · 도구 입력 JSON 을 여러 조각으로).
String _sse(Map<String, dynamic> m) {
  final b = StringBuffer();
  void ev(String type, Map<String, dynamic> data) => b.write('event: $type\ndata: ${jsonEncode({'type': type, ...data})}\n\n');
  final usage = m['usage'] as Map<String, dynamic>;
  ev('message_start', {
    'message': {
      ...m,
      'content': [],
      'stop_reason': null,
      'usage': {...usage, 'output_tokens': 1},
    },
  });
  b.write(': ping\n\n');
  for (final (i, c) in (m['content'] as List).cast<Map<String, dynamic>>().indexed) {
    switch (c['type']) {
      case 'text':
        ev('content_block_start', {'index': i, 'content_block': {'type': 'text', 'text': ''}});
        final t = c['text'] as String;
        ev('content_block_delta', {'index': i, 'delta': {'type': 'text_delta', 'text': t.substring(0, t.length ~/ 2)}});
        ev('content_block_delta', {'index': i, 'delta': {'type': 'text_delta', 'text': t.substring(t.length ~/ 2)}});
      case 'thinking':
        ev('content_block_start', {'index': i, 'content_block': {'type': 'thinking', 'thinking': '', 'signature': ''}});
        ev('content_block_delta', {'index': i, 'delta': {'type': 'thinking_delta', 'thinking': c['thinking']}});
        final s = c['signature'] as String;
        ev('content_block_delta', {'index': i, 'delta': {'type': 'signature_delta', 'signature': s.substring(0, 3)}});
        ev('content_block_delta', {'index': i, 'delta': {'type': 'signature_delta', 'signature': s.substring(3)}});
      case 'tool_use':
        ev('content_block_start', {
          'index': i,
          'content_block': {'type': 'tool_use', 'id': c['id'], 'name': c['name'], 'input': {}},
        });
        final j = jsonEncode(c['input']);
        ev('content_block_delta', {'index': i, 'delta': {'type': 'input_json_delta', 'partial_json': j.substring(0, j.length ~/ 2)}});
        ev('content_block_delta', {'index': i, 'delta': {'type': 'input_json_delta', 'partial_json': j.substring(j.length ~/ 2)}});
    }
    ev('content_block_stop', {'index': i});
  }
  ev('message_delta', {
    'delta': {'stop_reason': m['stop_reason'], 'stop_sequence': null},
    'usage': {'output_tokens': usage['output_tokens']},
  });
  ev('message_stop', {});
  return b.toString();
}

/// 대본 응답을 차례로 내는 가짜 HTTP. 받은 요청(본문 JSON · 헤더)을 남긴다.
class _Script {
  final List<Object> replies; // Map(메시지) · int(오류 상태) · Exception(연결 오류)
  final bool sse;
  final bodies = <Map<String, dynamic>>[];
  final headers = <Map<String, String>>[];
  final sleeps = <Duration>[];
  _Script(this.replies, {this.sse = true});

  late final client = MockClient((req) async {
    bodies.add(jsonDecode(req.body) as Map<String, dynamic>);
    headers.add(req.headers);
    if (replies.isEmpty) throw StateError('대본이 끝났는데 또 부름');
    final r = replies.removeAt(0);
    if (r is Exception) throw r;
    if (r is int) {
      return http.Response.bytes(utf8.encode(jsonEncode({'type': 'error', 'error': {'type': 'x_error', 'message': '상태 $r'}})), r,
          headers: {'content-type': 'application/json'});
    }
    final m = r as Map<String, dynamic>;
    return sse
        ? http.Response.bytes(utf8.encode(_sse(m)), 200, headers: {'content-type': 'text/event-stream; charset=utf-8'})
        : http.Response.bytes(utf8.encode(jsonEncode(m)), 200, headers: {'content-type': 'application/json'});
  });

  TurnAgent agent({AgentLimits limits = const AgentLimits()}) => TurnAgent(
        client: ClaudeClient(httpClient: client, apiKey: 'test-key', sleep: (d) async => sleeps.add(d)),
        runner: directRunner,
        limits: limits,
      );
}

Map<String, dynamic> _answer(String id, {List<String>? order, String kind = 'hand', bool unsure = false}) => _use(id, 'answer', {
      'kind': kind,
      'k': 9,
      'j': 9,
      'end_order': order ?? ['1', '2', 'D', '4', '5'],
      'unsure': unsure,
      'why': '프레임 3 에서 D 를 3번 자리에 끼움',
    });

List<Map<String, dynamic>> _content(Map<String, dynamic> msg) => (msg['content'] as List).cast<Map<String, dynamic>>();

void main() {
  test('view → zoom(+잘못된 view) → answer 대본: 요청 꼴 · content 그대로 · tool_result 한 메시지 · is_error · k·j · 비용', () async {
    final r1 = _msg([
      _think('먼저 훑자', 'sig-abc-123'),
      _text('훑어보겠다.'),
      _use('t1', 'view', {'frames': [0, 2, 4]}),
    ]);
    final r2 = _msg([
      _think('3번 근처', 'sig-def-456'),
      _use('t2', 'zoom', {'frame': 2, 'x0': 0, 'x1': 100}),
      _use('t3', 'view', {'frames': 'x'}),
    ], cacheRead: 5000, cacheWrite: 2000);
    final r3 = _msg([_answer('t4')], stop: 'tool_use');
    final s = _Script([r1, r2, r3]);
    final res = await s.agent().read(_frames(5), 5);

    expect(s.bodies, hasLength(3));
    final b = s.bodies.first;
    expect(b['model'], 'claude-opus-5-5');
    expect(b['max_tokens'], 32000);
    expect(b['output_config'], {'effort': 'high'});
    expect(b['cache_control'], {'type': 'ephemeral'});
    expect(b['stream'], isTrue);
    expect(b.containsKey('thinking'), isFalse);
    expect(b.containsKey('tool_choice'), isFalse);
    expect(b.containsKey('temperature'), isFalse);
    final sys = (b['system'] as List).single as Map<String, dynamic>;
    expect(sys['cache_control'], {'type': 'ephemeral'});
    expect(sys['text'], contains('차례를 시작할 때 줄은 **5장**'));
    expect(sys['text'], contains('그림 크기 200 × 60'));
    expect(sys['text'], isNot(contains('events.txt')));
    final tools = (b['tools'] as List).cast<Map<String, dynamic>>();
    expect(tools.map((t) => t['name']), ['strip', 'view', 'zoom', 'answer']);
    expect(tools.last['strict'], isTrue);
    expect(jsonEncode(tools), isNot(contains('"kind":{"type":"string","enum":["color"')));
    expect((tools[1]['input_schema'] as Map)['required'], ['frames']);
    final first = _content((b['messages'] as List).single as Map<String, dynamic>);
    expect(first.map((x) => x['type']), ['text', 'image', 'text', 'image', 'text']);
    expect(first.first['text'], contains('프레임 5장'));
    expect(first.last['text'], firstTail);
    expect(s.headers.first['x-api-key'], 'test-key');
    expect(s.headers.first['anthropic-version'], '2023-06-01');
    expect(s.headers.first['content-type'], startsWith('application/json'));

    // 두 번째 요청: 응답 content 를 그대로(thinking 서명 조각까지 이어 붙여) assistant 로, tool_result 는 한 user 메시지.
    final m2 = (s.bodies[1]['messages'] as List).cast<Map<String, dynamic>>();
    expect(m2.map((m) => m['role']), ['user', 'assistant', 'user']);
    expect(m2[1]['content'], r1['content']);
    final tr = _content(m2[2]);
    expect(tr.single['type'], 'tool_result');
    expect(tr.single['tool_use_id'], 't1');
    final trc = (tr.single['content'] as List).cast<Map<String, dynamic>>();
    expect(trc.map((x) => x['type']), ['text', 'image', 'image', 'image']);
    expect(trc.first['text'], contains('프레임 002'));

    // 세 번째: zoom 결과 + 잘못된 view 는 is_error, 둘 다 한 메시지.
    final m3 = (s.bodies[2]['messages'] as List).cast<Map<String, dynamic>>();
    expect(m3, hasLength(5));
    expect(m3[3]['content'], r2['content']);
    final tr3 = _content(m3[4]);
    expect(tr3.map((x) => x['tool_use_id']), ['t2', 't3']);
    expect(tr3[0].containsKey('is_error'), isFalse);
    expect((tr3[0]['content'] as List).first['text'], contains('확대 x 0~100'));
    expect(tr3[1]['is_error'], isTrue);

    expect(res.kind, 'hand');
    expect((res.k, res.j), (3, 3)); // end_order 에서 셈(모델 k·j 9 는 버림)
    expect(res.orderOk, isTrue);
    expect(res.steps, 3);
    expect(res.error, isNull);
    // 입력 3000 · 출력 600 · 캐시 읽기 5000 · 쓰기 2000
    expect(res.usd, closeTo((3000 * 4 + 600 * 20 + 5000 * 0.2 + 2000 * 5) * 1e-6, 1e-9));
  });

  test('스트림이 아닌 JSON 응답도 받는다', () async {
    final s = _Script([_msg([_answer('a', kind: 'tsumogiri', order: ['1', '2', '3'])])], sse: false);
    final res = await s.agent().read(_frames(3), 3);
    expect(res.kind, 'tsumogiri');
    expect(res.k, 9); // 쯔모기리는 모델 값 그대로(복원은 순서를 씀)
  });

  test('재시도: 529 · 429 · 연결 오류는 10 · 20 · 30초 쉬고 다시, 400 은 바로 오류', () async {
    final s = _Script([529, 429, http.ClientException('끊김'), _msg([_answer('a')])]);
    final res = await s.agent().read(_frames(5), 5);
    expect(res.kind, 'hand');
    expect(s.sleeps, const [Duration(seconds: 10), Duration(seconds: 20), Duration(seconds: 30)]);
    expect(s.bodies, hasLength(4));

    final bad = _Script([400]);
    final r2 = await bad.agent().read(_frames(5), 5);
    expect(r2.answered, isFalse);
    expect(r2.error, contains('400'));
    expect(bad.sleeps, isEmpty);

    final down = _Script([500, 500, 500, 500]);
    final r3 = await down.agent().read(_frames(5), 5);
    expect(r3.error, contains('500'));
    expect(down.bodies, hasLength(4));
  });

  test('스트림 중 overloaded_error 도 다시', () async {
    var n = 0;
    final client = MockClient((req) async {
      n++;
      if (n == 1) {
        return http.Response.bytes(
            utf8.encode('event: error\ndata: {"type":"error","error":{"type":"overloaded_error","message":"busy"}}\n\n'), 200,
            headers: {'content-type': 'text/event-stream'});
      }
      return http.Response.bytes(utf8.encode(_sse(_msg([_answer('a')]))), 200, headers: {'content-type': 'text/event-stream'});
    });
    final sleeps = <Duration>[];
    final c = ClaudeClient(httpClient: client, apiKey: 'k', sleep: (d) async => sleeps.add(d));
    final m = await c.create({'model': claudeModel, 'messages': []});
    expect(m.content.single['name'], 'answer');
    expect(sleeps, const [Duration(seconds: 10)]);
  });

  test('비용 한도를 넘으면 마지막 단계 글을 tool_result 뒤에 붙이고, 그 뒤 도구는 is_error', () async {
    final s = _Script([
      _msg([_use('a', 'view', {'frames': [0]})], input: 2000000), // 8달러
      _msg([_use('b', 'view', {'frames': [1]})]),
      _msg([_answer('c', unsure: true)]),
    ]);
    final res = await s.agent().read(_frames(5), 5, maxUsd: 5);
    final m2 = (s.bodies[1]['messages'] as List).cast<Map<String, dynamic>>();
    final last = _content(m2.last);
    expect(last.map((x) => x['type']), ['tool_result', 'text']);
    expect(last.last['text'], finalText);
    final m3 = (s.bodies[2]['messages'] as List).cast<Map<String, dynamic>>();
    final tr = _content(m3.last).single;
    expect(tr['is_error'], isTrue);
    expect(tr['content'], contains('answer 만'));
    expect(res.kind, 'hand');
    expect(res.unsure, isTrue);
    expect(res.log.any((l) => l['final'] == '달러'), isTrue);
  });

  test('글로만 답하면 재촉하고, 세 번째에 멈춤(답 없음)', () async {
    final s = _Script([
      _msg([_text('음…')], stop: 'end_turn'),
      _msg([_text('더 보자')], stop: 'end_turn'),
      _msg([_text('모르겠다')], stop: 'end_turn'),
    ]);
    final res = await s.agent().read(_frames(5), 5);
    expect(s.bodies, hasLength(3));
    for (final b in s.bodies.skip(1)) {
      final msgs = (b['messages'] as List).cast<Map<String, dynamic>>();
      expect(_content(msgs.last).single['text'], nudgeText);
    }
    expect(res.answered, isFalse);
    expect(res.error, 'answer 없음');
  });

  test('단계 한도: 마지막 단계에 FINAL_TEXT, 글로만 답해도 마무리 2번 안에서 다시 묻고, 그래도 없으면 끝', () async {
    final s = _Script([
      _msg([_use('a', 'view', {'frames': [0]})]),
      _msg([_use('b', 'view', {'frames': [1]})]),
      _msg([_text('아직')], stop: 'end_turn'),
      _msg([_text('아직')], stop: 'end_turn'),
      _msg([_text('아직')], stop: 'end_turn'),
    ]);
    final res = await s.agent(limits: const AgentLimits(maxSteps: 3)).read(_frames(5), 5);
    // 단계 0 · 1 · 2(마지막 — FINAL_TEXT) · 3 · 4(마무리 2번) = 5번.
    expect(s.bodies, hasLength(5));
    final m3 = (s.bodies[2]['messages'] as List).cast<Map<String, dynamic>>();
    expect(_content(m3.last).last['text'], finalText);
    final m4 = (s.bodies[3]['messages'] as List).cast<Map<String, dynamic>>();
    expect(_content(m4.last).single['text'], finalText);
    expect(res.answered, isFalse);
  });

  test('refusal · max_tokens 는 오류로 끝', () async {
    final s = _Script([
      {..._msg([], stop: 'refusal'), 'stop_details': {'type': 'refusal', 'category': 'cyber'}},
    ]);
    final res = await s.agent().read(_frames(5), 5);
    expect(res.error, 'refusal (cyber)');
    final t = _Script([_msg([_text('…')], stop: 'max_tokens')]);
    expect((await t.agent().read(_frames(5), 5)).error, 'max_tokens(32000)');
  });

  test('strip: 8줄씩 · 32줄까지, 설명 글에 프레임 범위', () async {
    final s = _Script([
      _msg([_use('a', 'strip', {'start': 0, 'end': 39, 'step': 1, 'x0': 0, 'x1': 200})]),
      _msg([_answer('b')]),
    ]);
    await s.agent().read(_frames(40), 5);
    final tr = _content((s.bodies[1]['messages'] as List).cast<Map<String, dynamic>>().last).single;
    final c = (tr['content'] as List).cast<Map<String, dynamic>>();
    expect(c.where((x) => x['type'] == 'image'), hasLength(4));
    expect(c.first['text'], contains('strip 프레임 000~007(간격 1)'));
    expect(c.first['text'], contains('024~031'));
  });

  test('fromOrder: 온전한 순서만', () {
    expect(fromOrder(['1', '2', 'D', '4', '5'], 5), (k: 3, j: 3));
    expect(fromOrder(['1', '2', '3', '4', '5'], 5), isNull);
    expect(fromOrder(['1', '1', 'D', '4', '5'], 5), isNull);
    expect(fromOrder(['1', '2', 'D', '4'], 5), isNull);
  });
}
