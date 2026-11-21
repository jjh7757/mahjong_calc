/// 한 차례 손패 줄 읽기 — Claude API(Opus 5.5) 도구 루프(`docs/paifu_hand_restore_api_1121.md` 3-4).
///
/// `experiments/paifu_frames/handtrack/claudeagent.py` `run_one` 을 옮긴 것: 같은 요청 앞부분(model · max_tokens · system 캐시 지점 ·
/// 도구 · `output_config.effort` · 최상위 cache_control, thinking 안 줌), 같은 한도(단계 60 + 마무리 2 · 차례당 5달러 · 그림 560장 ·
/// 120MB), 같은 마무리 글(FINAL_TEXT) · 재촉 글(NUDGE_TEXT). 다른 점: 도구에 kind 인자 · check 도구가 없다(원본만, SAM 2 없음),
/// answer 에 tracking_errors 가 없다, 지시문은 `opusread.py` `TASK_NOSAM` 을 도구 판으로 고친 것(사건 목록 문장은 뺌).
/// API 규칙(claudeagent.py 머리말): 응답 content 전체(thinking 포함)를 assistant 로 그대로 붙이고, 한 응답의 tool_result 들은 한
/// user 메시지에, 도구 오류는 is_error. forced tool_choice 는 400 이라 쓰지 않는다(answer 는 글로 재촉).
library;

import 'dart:convert';
import 'dart:typed_data';

import 'claude_client.dart';
import 'frames.dart';

const String claudeModel = 'claude-opus-5-5';

/// 100만 토큰당 달러: 입력 · 출력(생각 포함) · 캐시 읽기 · 캐시 쓰기(5분). claudeagent.py PRICE 와 같음.
const ({double input, double output, double cacheRead, double cacheWrite}) opusPrice =
    (input: 4.0, output: 20.0, cacheRead: 0.20, cacheWrite: 5.0);

const String finalText = '볼 수 있는 단계를 다 썼다. 지금까지 본 것으로 answer 를 불러라(확신이 낮으면 unsure 를 true 로).';
const String nudgeText = '도구로 더 보거나, 다 봤으면 answer 를 불러라.';
const String firstTail = '도구로 필요한 프레임을 보며 읽고, 다 보면 answer 를 불러라.';
const int maxView = 6;

/// 지시문(opusread.py TASK_NOSAM 을 도구 판으로). {n} 등은 [systemText] 가 채운다.
const String taskPrompt = '''# 손패 줄 한 차례 읽기

너는 위에서 내려다본 녹화에서 마작 대국자 한 사람의 **세운 손패 줄**을 한 차례 읽는다. 패는 세워져 있어 위에서는 등(색 띠)과 흰 면만 보이고 **모든 패가 똑같이 생겼다** — 읽는 것은 위치뿐이다.
이 차례 = 패산에서 한 장을 뽑아 오고(뽑은 패 = **D**), 한 장을 강에 버림. 차례를 시작할 때 줄은 **{n}장**이다. 첫 프레임의 줄 {n}장을 왼쪽부터 원래 번호 1 ~ {n} 으로 부른다.

## 재료(도구로 본다)
- 프레임 {F}장(초당 5장, 번호 0 ~ {last}). 번호 · 시각 목록은 첫 메시지에 있다. 그림은 그 사람 시점으로 돌려져 있다(그림 왼쪽 = 그 사람 왼손 쪽, 아래쪽 흰 띠 = 탁자 테두리). 다른 사람 팔이 지나가기도 한다. 그림에 색 · 숫자는 없다.

## 도구
- `view(frames)` — 프레임 여러 장(한 번에 {mv}장까지)을 본다.
- `zoom(frame, x0, x1, y0, y1)` — 한 프레임의 일부를 잘라 3배로 키워 본다(좌표는 그 프레임 그림의 화소, 그림 크기 {W} × {H}). y0 · y1 을 비우면 높이 전체.
- `strip(start, end, step, x0, x1, y0, y1)` — **같은 영역**을 start ~ end 프레임에서 step 장마다 잘라 시간순으로 위아래로 쌓아 본다(줄마다 왼쪽에 프레임 번호, 한 장에 {sr}줄씩 · 한 번에 {sm}줄까지). 패 하나가 손 밑에서 어떻게 움직였는지 이어서 볼 때 쓴다.
- `answer(...)` — 답을 낸다. 부르면 끝난다.

## 하는 법
- 프레임은 `view` 로 본다. 필요하면 `zoom` · `strip` 으로 원본 그림을 잘라 키워서 본다.
- 읽기 전에 **패가 실제로 움직인 때**(D 를 줄에 놓음 · 패를 뺌 · 버림 · 줄을 밂 · 끼움 · 옮김 · 맞바꿈)를 먼저 찾아 차례의 사건 순서를 세운다.
- **패는 사라지지 않는다.** 줄의 패 수는 {n} → D 를 줄에 놓으면 {n}+1 → 한 장 버리면 {n}. 손이 덮은 순간에는 원본을 확대해 손가락 밑 패까지 센다. 패 하나하나에 대해 "그 패는 지금 실제로 어디 있나" 를 원본에서 확인한다 — 말로 넘기지 않는다.
- 손이 덮은 동안 패를 옮겼다(끼움 · 맞바꿈)고 보려면 원본에서 그 동작의 흔적을 확인한다: 손이 패를 들고 움직임 · 칸이 비었다 참 · 끝 패가 그 자리에서 사라짐 · 줄 길이가 바뀜. 흔적을 못 찾으면 "움직이지 않음" 쪽에 무게를 두고, 그래도 옮겼다고 답하면 why 에 그 흔적을 프레임 번호로 적는다.
- D 를 끝에 붙여 두고 한 장을 버리는 사람, 버린 뒤 D 를 다시 집어 안쪽에 끼우는 사람, D 를 먼저 안쪽에 끼우고 버리는 사람, 버리기 전에 패를 옮기거나 맞바꾸는 사람, 뽑은 패를 그대로 버리는 사람(쯔모기리)이 다 있다. 끝 프레임까지 본다.

## 답(answer 도구)
- kind: "hand"(줄에 있던 패를 버림) 또는 "tsumogiri"(D 를 그대로 버림, 줄의 패는 안 바뀜)
- k: 버린 패가 원래 줄 {n}장에서 왼쪽부터 몇 번째였나(D 는 세지 않음, tsumogiri 면 null)
- j: 차례가 끝났을 때 D 가 줄({n}장)의 왼쪽부터 몇 번째인가(끝 그대로면 {n}, tsumogiri 면 null)
- end_order: 끝 줄 왼쪽부터 실제 패 — 원래 번호 "1" ~ "{n}" 또는 "D"(tsumogiri 면 "1" ~ "{n}")
- unsure: 맞을 가능성 70% 밑이면 true · why: 근거 3 ~ 5문장(시각 · 프레임 번호와 함께)
''';

String systemText({required int n, required int frames, required int width, required int height}) => taskPrompt
    .replaceAll('{n}', '$n')
    .replaceAll('{F}', '$frames')
    .replaceAll('{last}', '${frames - 1}')
    .replaceAll('{mv}', '$maxView')
    .replaceAll('{W}', '$width')
    .replaceAll('{H}', '$height')
    .replaceAll('{sr}', '$stripRows')
    .replaceAll('{sm}', '$stripMax');

/// 도구 정의(claudeagent._tool_defs_base 에서 kind 인자 · check 도구를 뺌, answer 에서 tracking_errors 를 뺌). 순서 strip · view · zoom · answer.
List<Map<String, dynamic>> toolDefs() {
  const it = {'type': 'integer'};
  const nint = {
    'anyOf': [
      {'type': 'integer'},
      {'type': 'null'},
    ],
  };
  return [
    {
      'name': 'strip',
      'description': '같은 영역을 여러 프레임에서 잘라 시간순으로 쌓아 본다',
      'input_schema': {
        'type': 'object',
        'properties': {'start': it, 'end': it, 'step': it, 'x0': it, 'x1': it, 'y0': it, 'y1': it},
        'required': ['start', 'end', 'step', 'x0', 'x1'],
        'additionalProperties': false,
      },
    },
    {
      'name': 'view',
      'description': '프레임 여러 장을 본다',
      'input_schema': {
        'type': 'object',
        'properties': {
          'frames': {'type': 'array', 'items': it},
        },
        'required': ['frames'],
        'additionalProperties': false,
      },
    },
    {
      'name': 'zoom',
      'description': '한 프레임의 일부를 잘라 3배로 키운다',
      'input_schema': {
        'type': 'object',
        'properties': {'frame': it, 'x0': it, 'x1': it, 'y0': it, 'y1': it},
        'required': ['frame', 'x0', 'x1'],
        'additionalProperties': false,
      },
    },
    {
      'name': 'answer',
      'description': '답을 낸다(부르면 끝)',
      'strict': true,
      'input_schema': {
        'type': 'object',
        'properties': {
          'kind': {
            'type': 'string',
            'enum': ['hand', 'tsumogiri'],
          },
          'k': nint,
          'j': nint,
          'end_order': {'type': 'array', 'items': {'type': 'string'}},
          'unsure': {'type': 'boolean'},
          'why': {'type': 'string'},
        },
        'required': ['kind', 'k', 'j', 'end_order', 'unsure', 'why'],
        'additionalProperties': false,
      },
    },
  ];
}

class AgentLimits {
  final String model;
  final String effort;
  final int maxTokens;
  final int maxSteps;
  final int finalExtra;
  final double maxUsd;
  final int maxImages;
  final int maxBytes;
  const AgentLimits({
    this.model = claudeModel,
    this.effort = 'high',
    this.maxTokens = 32000,
    this.maxSteps = 60,
    this.finalExtra = 2,
    this.maxUsd = 5.0,
    this.maxImages = 560,
    this.maxBytes = 120 << 20,
  });

  AgentLimits withMaxUsd(double usd) => AgentLimits(
        model: model,
        effort: effort,
        maxTokens: maxTokens,
        maxSteps: maxSteps,
        finalExtra: finalExtra,
        maxUsd: usd,
        maxImages: maxImages,
        maxBytes: maxBytes,
      );
}

/// 끝 줄 순서 → (k, j). 온전하지 않으면 null(sam2verify.from_order).
({int k, int j})? fromOrder(List<String>? order, int n) {
  if (order == null || order.length != n || order.where((x) => x == 'D').length != 1) return null;
  final nums = <int>[];
  for (final x in order) {
    if (x == 'D') continue;
    final v = int.tryParse(x);
    if (v == null) return null;
    nums.add(v);
  }
  if (nums.length != n - 1 || nums.toSet().length != n - 1 || nums.any((x) => x < 1 || x > n)) return null;
  var k = 1;
  while (nums.contains(k)) {
    k++;
  }
  return (k: k, j: order.indexOf('D') + 1);
}

/// 한 차례 읽기 결과.
class TurnReading {
  /// hand · tsumogiri, 답이 없으면 null.
  final String? kind;
  final int? k, j;
  final List<String>? endOrder;
  final bool unsure;
  final String? why;

  /// end_order 가 온전했나(k · j 를 거기서 셈).
  final bool orderOk;
  final double usd;
  final int steps;
  final Map<String, int> usage;
  final String? error;
  final List<Map<String, dynamic>> log;

  const TurnReading({
    this.kind,
    this.k,
    this.j,
    this.endOrder,
    this.unsure = false,
    this.why,
    this.orderOk = false,
    this.usd = 0,
    this.steps = 0,
    this.usage = const {},
    this.error,
    this.log = const [],
  });

  bool get answered => kind != null;

  Map<String, dynamic> toMemo() => {
        'kind': kind,
        'k': k,
        'j': j,
        'end_order': endOrder,
        'unsure': unsure,
        if (why != null) 'why': why,
        'usd': double.parse(usd.toStringAsFixed(3)),
        'steps': steps,
        if (error != null) 'error': error,
      };
}

/// 차례 읽기(실행기가 쓰는 꼴 — 시험은 가짜로 바꾼다).
abstract class TurnReader {
  Future<TurnReading> read(TurnFrames frames, int n, {double? maxUsd, bool Function()? cancelled});
}

String _clock(int ms) {
  final t = DateTime.fromMillisecondsSinceEpoch(ms);
  final s = t.second + t.millisecond / 1000;
  return '${t.minute.toString().padLeft(2, '0')}:${s.toStringAsFixed(1).padLeft(4, '0')}';
}

int _int(Object? v, String name) {
  if (v is num) return v.toInt();
  if (v is String) {
    final p = int.tryParse(v);
    if (p != null) return p;
  }
  throw FormatException('$name 가 정수가 아님: $v');
}

int? _intOrNull(Object? v) => v == null ? null : (v is num ? v.toInt() : int.tryParse('$v'));

class TurnAgent implements TurnReader {
  final ClaudeClient client;
  final ImageRunner runner;
  final AgentLimits limits;
  TurnAgent({required this.client, this.runner = computeRunner, this.limits = const AgentLimits()});

  /// 매 호출에 같은 앞부분(claudeagent.request_kw).
  Map<String, dynamic> requestHead(TurnFrames f, int n) => {
        'model': limits.model,
        'max_tokens': limits.maxTokens,
        'system': [
          {
            'type': 'text',
            'text': systemText(n: n, frames: f.length, width: f.width, height: f.height),
            'cache_control': {'type': 'ephemeral'},
          },
        ],
        'tools': toolDefs(),
        'output_config': {'effort': limits.effort},
        'cache_control': {'type': 'ephemeral'},
      };

  Future<Map<String, dynamic>> imageBlock(Uint8List jpeg) async {
    final fitted = await runner(fitJpeg, jpeg);
    return {
      'type': 'image',
      'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': base64Encode(fitted)},
    };
  }

  Future<List<Map<String, dynamic>>> firstContent(TurnFrames f, int n) async {
    final last = f.length - 1;
    final lst = [for (var i = 0; i < f.length; i++) '${i.toString().padLeft(3, '0')} ${_clock(f.ms[i])}'].join('\n');
    return [
      {'type': 'text', 'text': '차례를 시작할 때 줄은 $n장. 프레임 ${f.length}장(번호 · 시각):\n$lst\n\n첫 프레임:'},
      await imageBlock(f.jpegs.first),
      {'type': 'text', 'text': '끝 프레임 $last:'},
      await imageBlock(f.jpegs[last]),
      {'type': 'text', 'text': firstTail},
    ];
  }

  /// 도구 하나 → [(설명, jpeg)]. 실패하면 예외(부르는 쪽이 is_error 로).
  Future<List<(String, Uint8List)>> runTool(TurnFrames f, String name, Map<String, dynamic> args) async {
    final last = f.length - 1;
    int clampF(int i) => i.clamp(0, last);
    switch (name) {
      case 'view':
        final raw = args['frames'];
        if (raw is! List) throw const FormatException('frames 는 정수 목록');
        final fr = [for (final x in raw) _int(x, 'frames')].take(maxView).toList();
        if (fr.isEmpty) throw const FormatException('frames 가 비었음');
        return [
          for (final i in fr) ('프레임 ${i.toString().padLeft(3, '0')} ${_clock(f.ms[clampF(i)])}', f.jpegs[clampF(i)]),
        ];
      case 'zoom':
        final i = _int(args['frame'], 'frame');
        final z = await runner(zoomFrame, (
          jpeg: f.jpegs[clampF(i)],
          x0: _int(args['x0'], 'x0'),
          x1: _int(args['x1'], 'x1'),
          y0: _intOrNull(args['y0']),
          y1: _intOrNull(args['y1']),
        ));
        return [('프레임 ${i.toString().padLeft(3, '0')} 확대 x ${z.x0}~${z.x1} y ${z.y0}~${z.y1}', z.jpeg)];
      case 'strip':
        var st = clampF(_int(args['start'], 'start')), en = clampF(_int(args['end'], 'end'));
        final sp = (_intOrNull(args['step']) ?? 1) < 1 ? 1 : _intOrNull(args['step'])!;
        if (st > en) (st, en) = (en, st);
        final idx = [for (var i = st; i <= en; i += sp) i].take(stripMax).toList();
        final sheets = await runner(stripSheets, (
          jpegs: [for (final i in idx) f.jpegs[i]],
          idx: idx,
          x0: _int(args['x0'], 'x0'),
          x1: _int(args['x1'], 'x1'),
          y0: _intOrNull(args['y0']),
          y1: _intOrNull(args['y1']),
          width: f.width,
          height: f.height,
        ));
        return [
          for (final s in sheets)
            (
              'strip 프레임 ${s.from.toString().padLeft(3, '0')}~${s.to.toString().padLeft(3, '0')}(간격 $sp) x ${s.x0}~${s.x1} y ${s.y0}~${s.y1}',
              s.jpeg
            ),
        ];
    }
    throw FormatException('모르는 도구: $name');
  }

  static ({int n, int bytes}) countImages(List<Map<String, dynamic>> msgs) {
    var n = 0, size = 0;
    void walk(Object? blocks) {
      if (blocks is! List) return;
      for (final b in blocks) {
        if (b is! Map) continue;
        if (b['type'] == 'image') {
          n++;
          size += ((b['source'] as Map)['data'] as String).length;
        } else if (b['type'] == 'tool_result') {
          walk(b['content']);
        }
      }
    }

    for (final m in msgs) {
      walk(m['content']);
    }
    return (n: n, bytes: size);
  }

  @override
  Future<TurnReading> read(TurnFrames f, int n, {double? maxUsd, bool Function()? cancelled}) async {
    final lim = maxUsd == null ? limits : limits.withMaxUsd(maxUsd);
    final head = requestHead(f, n);
    final msgs = <Map<String, dynamic>>[
      {'role': 'user', 'content': await firstContent(f, n)},
    ];
    final log = <Map<String, dynamic>>[];
    final usage = {'in': 0, 'cache_read': 0, 'cache_write': 0, 'out': 0, 'calls': 0};
    Map<String, dynamic>? ans;
    String? error;
    var nudges = 0, usd = 0.0, isFinal = false, step = -1;
    while (true) {
      step++;
      if (step >= lim.maxSteps + lim.finalExtra) break;
      if (cancelled?.call() == true) {
        error = '취소';
        break;
      }
      final c = countImages(msgs);
      final whyFinal = step >= lim.maxSteps - 1
          ? '단계'
          : usd > lim.maxUsd
              ? '달러'
              : c.n > lim.maxImages
                  ? '그림 장수'
                  : c.bytes > lim.maxBytes
                      ? '요청 크기'
                      : null;
      if (whyFinal != null && !isFinal) {
        isFinal = true;
        log.add({'step': step, 'final': whyFinal});
        final lastMsg = msgs.last;
        if (lastMsg['role'] == 'user') {
          (lastMsg['content'] as List).add({'type': 'text', 'text': finalText});
        } else {
          msgs.add({
            'role': 'user',
            'content': [
              {'type': 'text', 'text': finalText},
            ],
          });
        }
      }
      final ClaudeMessage r;
      try {
        r = await client.create({...head, 'messages': msgs});
      } catch (e) {
        error = '$e';
        if (error.length > 400) error = error.substring(0, 400);
        break;
      }
      final ui = r.usageOf('input_tokens'), ucr = r.usageOf('cache_read_input_tokens');
      final ucw = r.usageOf('cache_creation_input_tokens'), uo = r.usageOf('output_tokens');
      usage['in'] = usage['in']! + ui;
      usage['cache_read'] = usage['cache_read']! + ucr;
      usage['cache_write'] = usage['cache_write']! + ucw;
      usage['out'] = usage['out']! + uo;
      usage['calls'] = usage['calls']! + 1;
      usd += (ui * opusPrice.input + uo * opusPrice.output + ucr * opusPrice.cacheRead + ucw * opusPrice.cacheWrite) * 1e-6;
      final content = r.content;
      msgs.add({'role': 'assistant', 'content': content}); // thinking 포함 그대로
      final uses = [
        for (final b in content)
          if (b['type'] == 'tool_use') b,
      ];
      log.add({'step': step, 'stop': r.stopReason, 'in': ui, 'cache_read': ucr, 'cache_write': ucw, 'out': uo});
      if (r.stopReason == 'refusal') {
        error = 'refusal${r.stopDetails['category'] == null ? '' : ' (${r.stopDetails['category']})'}';
        break;
      }
      if (r.stopReason == 'max_tokens') {
        error = 'max_tokens(${lim.maxTokens})';
        break;
      }
      if (uses.isEmpty) {
        if (isFinal) {
          msgs.add({
            'role': 'user',
            'content': [
              {'type': 'text', 'text': finalText},
            ],
          });
          continue;
        }
        nudges++;
        if (nudges > 2) break;
        msgs.add({
          'role': 'user',
          'content': [
            {'type': 'text', 'text': nudgeText},
          ],
        });
        continue;
      }
      final results = <Map<String, dynamic>>[];
      for (final b in uses) {
        final id = b['id'];
        final name = b['name'] as String?;
        final args = b['input'] is Map ? (b['input'] as Map).cast<String, dynamic>() : <String, dynamic>{};
        log.add({'step': step, 'tool': name, 'args': args});
        if (name == 'answer') {
          ans = args;
          results.add({'type': 'tool_result', 'tool_use_id': id, 'content': '받음'});
          continue;
        }
        if (isFinal) {
          results.add({
            'type': 'tool_result',
            'tool_use_id': id,
            'content': '볼 수 있는 단계를 다 썼다 — 이제 answer 만 부를 수 있다.',
            'is_error': true,
          });
          continue;
        }
        try {
          final imgs = await runTool(f, name ?? '', args);
          results.add({
            'type': 'tool_result',
            'tool_use_id': id,
            'content': [
              {'type': 'text', 'text': [for (final x in imgs) x.$1].join(' | ')},
              for (final x in imgs) await imageBlock(x.$2),
            ],
          });
        } catch (e) {
          var m = '$e';
          if (m.length > 200) m = m.substring(0, 200);
          results.add({'type': 'tool_result', 'tool_use_id': id, 'content': m, 'is_error': true});
        }
      }
      msgs.add({'role': 'user', 'content': results});
      if (ans != null) break;
    }
    if (ans == null) {
      return TurnReading(usd: usd, steps: usage['calls']!, usage: usage, error: error ?? 'answer 없음', log: log);
    }
    final kind = ans['kind'] == 'hand' || ans['kind'] == 'tsumogiri' ? ans['kind'] as String : null;
    final order = ans['end_order'] is List ? [for (final x in ans['end_order'] as List) '$x'] : null;
    final kj = fromOrder(order, n);
    final useOrder = kj != null && kind == 'hand';
    return TurnReading(
      kind: kind,
      k: useOrder ? kj.k : _intOrNull(ans['k']),
      j: useOrder ? kj.j : _intOrNull(ans['j']),
      endOrder: order,
      unsure: ans['unsure'] == true,
      why: ans['why'] as String?,
      orderOk: kj != null,
      usd: usd,
      steps: usage['calls']!,
      usage: usage,
      error: kind == null ? 'answer 의 kind 가 틀림: ${ans['kind']}' : error,
      log: log,
    );
  }
}
