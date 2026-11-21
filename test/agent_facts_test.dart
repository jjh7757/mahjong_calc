import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/tile.dart';
import 'package:mahjong_calc/paifu/agent_facts.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';
import 'package:mahjong_calc/paifu/review_facts.dart';

/// '123m11z' → ['1m', '2m', '3m', '1z', '1z'].
List<String> h(String s) {
  final out = <String>[];
  final buf = <String>[];
  for (final ch in s.split('')) {
    if ('mpsz'.contains(ch)) {
      for (final d in buf) {
        out.add('$d$ch');
      }
      buf.clear();
    } else {
      buf.add(ch);
    }
  }
  return out;
}

/// 예시 11판 전부(assets/paifu).
const games = [
  'L16_135321',
  'r11_130921',
  'r12_131655',
  'r13_132644',
  'r14_133610',
  'r15_134151',
  'r16_135321',
  'r17_140450',
  'r18_141259',
  'r19_142013',
  'r20_143236',
];

/// 설계서 2절 목표: 한 판 60KB 이하(압축 JSON = 서버로 보내는 꼴).
/// 2026-11-21 잰 값(bytes): L16 27,205 · r11 25,485 · r12 21,223 · r13 27,575 · r14 2,271 · r15 32,063 · r16 32,611 ·
/// r17 16,757 · r18 17,950 · r19 15,131 · r20 2,529. 유효패를 `[{"tile", "left"}]` 목록으로 두었을 때는 r15 60,799 ·
/// r16 63,315 로 목표를 넘어 `{"1m": 3}` 맵으로 바꿨다(agent_facts.dart `_option`).
const maxBytes = 60 * 1024;

Map<String, dynamic> raw(String id) =>
    jsonDecode(File('assets/paifu/$id.json').readAsStringSync(encoding: utf8)) as Map<String, dynamic>;

Paifu load(String id) => Paifu.fromJson(raw(id));

/// 적5(0m) → 5m.
String norm(String code) => code.startsWith('0') ? '5${code[1]}' : code;

const winds = ['동', '남', '서', '북'];

/// JSON 안의 문자열 전부(키 포함).
Iterable<String> strings(Object? v) sync* {
  if (v is String) {
    yield v;
  } else if (v is Map) {
    for (final e in v.entries) {
      yield e.key as String;
      yield* strings(e.value);
    }
  } else if (v is List) {
    for (final x in v) {
      yield* strings(x);
    }
  }
}

List<Map<String, dynamic>> turnsOf(Map<String, dynamic> f) => (f['turns'] as List).cast<Map<String, dynamic>>();

void main() {
  group('agentFacts — 예시 11판 전부', () {
    for (final id in games) {
      test(id, () {
        final j = raw(id);
        final p = Paifu.fromJson(j);
        final r = reviewPaifu(p);
        final f = agentFacts(p, r);

        // JSON 왕복 · 크기.
        final text = jsonEncode(f);
        expect(jsonDecode(text), f);
        expect(utf8.encode(text).length, lessThanOrEqualTo(maxBytes), reason: '$id 압축 크기');
        expect(f['version'], 1);
        expect(f.keys, ['version', 'game', 'turns', 'others']);

        // 패 표기(적5 도 5m) · 개인 정보 없음.
        for (final s in strings(f)) {
          expect(RegExp(r'^0[mps]$').hasMatch(s), isFalse, reason: s);
        }
        for (final s in [...p.names, p.id, p.title, p.note]) {
          if (s.isNotEmpty) expect(text.contains(s), isFalse, reason: s);
        }

        // game: 해설 사실표와 같은 칸은 같은 값.
        final game = f['game'] as Map<String, dynamic>;
        final rf = reviewFacts(p, r);
        final rg = rf['game'] as Map<String, dynamic>;
        for (final k in ['round', 'honba', 'hero_wind', 'dora_indicators', 'efficiency_pct', 'grades', 'statuses']) {
          expect(game[k], rg[k], reason: k);
        }

        // 결과: 패보 JSON 의 result 에서 직접.
        final res = j['result'] as Map<String, dynamic>?;
        if (res == null) {
          expect(game['result'], isNull);
        } else {
          final g = game['result'] as Map<String, dynamic>;
          expect(g['type'], res['type']);
          final dealer = j['dealer'] as int;
          String? w(Object? seat) => seat == null ? null : winds[((seat as int) - dealer) % 4];
          if (res['type'] == 'draw') {
            expect(g['winner'], isNull);
            expect(g['win_tile'], isNull);
          } else {
            expect(g['winner'], w(res['winner']));
            expect(g['win_tile'], norm(res['win_tile'] as String));
          }
          expect(g['loser'], res['type'] == 'ron' ? w(res['loser']) : null);
        }

        // turns: hero 버림 전부, 걸러내지 않음.
        final turns = turnsOf(f);
        final events = (j['events'] as List).cast<Map<String, dynamic>>();
        final hero = j['hero'] as int;
        final heroDiscards = [
          for (final (i, e) in events.indexed)
            if (e['type'] == 'discard' && e['seat'] == hero) i,
        ];
        expect(turns.length, heroDiscards.length);
        expect(turns.length, r.turns.length);
        expect((game['statuses'] as Map).values.fold<int>(0, (s, v) => s + (v as int)), turns.length);

        // 해설 사실표에 있는 차례는 손패 · shanten_prev 가 같아야 한다(같은 계산을 두 곳에 둔 것의 대조).
        final explained = {for (final x in (rf['turns'] as List).cast<Map<String, dynamic>>()) x['turn']: x};

        for (final (k, x) in turns.indexed) {
          final tr = r.turns[k];
          final why = '$id ${x['turn']}번째';
          expect(x['turn'], k + 1, reason: why);
          // step = 재생 걸음 = 그 버림 사건의 인덱스 + 1.
          expect(x['step'], heroDiscards[k] + 1, reason: why);
          final ev = events[heroDiscards[k]];
          expect(x['discard'], norm(ev['tile'] as String), reason: why);
          expect(x['tsumogiri'], ev['tsumogiri'], reason: why);
          expect(x['riichi_declared'], ev['riichi'] ?? false, reason: why);
          expect(x['status'], tr.status.name, reason: why);
          expect(x['grade'], tr.grade?.name, reason: why);
          expect(x['melds'], tr.melds, reason: why);

          // options: reviewPaifu 의 options 와 같은 순서 · 같은 값.
          final opts = (x['options'] as List).cast<Map<String, dynamic>>();
          expect(opts.length, tr.options.length, reason: why);
          for (final (n, o) in opts.indexed) {
            final e = tr.options[n];
            expect(o['discard'], Tiles.toCode(e.tile), reason: why);
            expect(o['shanten'], e.shanten, reason: why);
            expect(o['total'], e.ukeire.total, reason: why);
            expect(o['kinds'], e.ukeire.liveKinds, reason: why);
            final tiles = (o['tiles'] as Map).cast<String, int>();
            expect(tiles.keys.toList(), [for (final u in e.ukeire.tiles) Tiles.toCode(u.tile)], reason: why);
            expect(tiles.values.toList(), [for (final u in e.ukeire.tiles) u.left], reason: why);
            // 맵 값만으로 total · kinds 를 다시 셈.
            expect(o['total'], tiles.values.fold<int>(0, (s, v) => s + v), reason: why);
            expect(o['kinds'], tiles.values.where((v) => v > 0).length, reason: why);
          }

          if (opts.isEmpty) {
            // 숫자 없는 차례: 손패 · 후보 · 최선 · 실제 · 샹텐 전부 없음.
            expect(tr.status, isIn([ReviewStatus.unknownHand, ReviewStatus.inconsistent, ReviewStatus.guessed]), reason: why);
            expect(x['hand'], isNull, reason: why);
            expect(x['actual'], isNull, reason: why);
            expect(x['best'], isEmpty, reason: why);
            for (final key in ['shanten_prev', 'shanten_before', 'shanten_loss', 'ukeire_loss']) {
              expect(x[key], isNull, reason: '$why $key');
            }
            expect(x['safe_tiles'], isEmpty, reason: why);
            continue;
          }

          // 숫자 있는 차례.
          final hand = (x['hand'] as List).cast<String>();
          expect(hand.length, 14 - 3 * tr.melds, reason: why);
          expect(hand, contains(x['discard']), reason: why);
          expect([for (final c in hand) Tiles.parse(c)], orderedEquals([...hand.map(Tiles.parse)]..sort()), reason: why);
          expect(x['actual'], x['discard'], reason: why);
          expect([for (final o in opts) o['discard']], contains(x['actual']), reason: why);
          // best = 맨 앞 후보와 샹텐 · 유효패 장수가 같은 후보 전부(옵션 순서).
          final first = opts.first;
          expect(x['best'], [
            for (final o in opts)
              if (o['shanten'] == first['shanten'] && o['total'] == first['total']) o['discard'],
          ], reason: why);
          expect((x['best'] as List).first, Tiles.toCode(tr.best!.tile), reason: why);
          final actual = opts.firstWhere((o) => o['discard'] == x['actual']);
          expect(x['shanten_loss'], (actual['shanten'] as int) - (first['shanten'] as int), reason: why);
          expect(x['ukeire_loss'], (first['total'] as int) - (actual['total'] as int), reason: why);
          expect(x['shanten_before'], tr.shantenBefore, reason: why);
          final e = explained[x['turn']];
          if (e != null) {
            expect(x['hand'], e['hand'], reason: why);
            expect(x['shanten_prev'], e['shanten_prev'], reason: why);
            expect(x['shanten_before'], e['shanten_before'], reason: why);
            expect(x['riichi_winds'], e['riichi_winds'], reason: why);
            expect(x['genbutsu'], e['genbutsu'], reason: why);
            expect(x['safe_tiles'], e['safe_tiles'], reason: why);
          }
          if (x['drawn'] == null) expect(x['shanten_prev'], isNull, reason: why);
        }

        // others: hero 아닌 자리의 리치 선언 버림 · 울기, 그리고 hero 아닌 화료 — 패보 JSON 에서 직접 셈.
        final others = (f['others'] as List).cast<Map<String, dynamic>>();
        final dealer = j['dealer'] as int;
        final want = <Map<String, Object?>>[
          for (final (i, e) in events.indexed)
            if (e['seat'] != hero && e['type'] == 'discard' && e['riichi'] == true)
              {'step': i + 1, 'wind': winds[((e['seat'] as int) - dealer) % 4], 'kind': 'riichi'}
            else if (e['seat'] != hero && e['type'] == 'call')
              {'step': i + 1, 'wind': winds[((e['seat'] as int) - dealer) % 4], 'kind': 'call'},
          if (res != null && res['type'] != 'draw' && res['winner'] != hero)
            {'step': events.length + 1, 'wind': winds[((res['winner'] as int) - dealer) % 4], 'kind': res['type']},
        ];
        expect([for (final o in others) {'step': o['step'], 'wind': o['wind'], 'kind': o['kind']}], want);
        for (final o in others.where((o) => o['kind'] == 'riichi')) {
          expect(o['tile'], norm(events[(o['step'] as int) - 1]['tile'] as String));
        }
      });
    }
  });

  test('r19 6번째: 손으로 적은 값 · 설계서 2절 예시의 best ["3m", "3s"]', () {
    final p = load('r19_142013');
    final f = agentFacts(p, reviewPaifu(p));
    final game = f['game'] as Map<String, dynamic>;
    expect(game['round'], '남4국');
    // dealer 3, hero 1 → (1 − 3) % 4 = 2 → 서.
    expect(game['hero_wind'], '서');
    expect(game['dora_indicators'], ['3z', '2m']);

    final x = turnsOf(f)[5];
    expect(x['turn'], 6);
    // 뽑기 전 13장 33m 789m 345p 33s 5s 88s + 뽑은 4m.
    expect(x['hand'], h('334789m345p33588s'));
    expect(x['drawn'], '4m');
    expect(x['discard'], '4m');
    expect(x['tsumogiri'], isTrue);
    expect(x['status'], 'graded');
    expect(x['grade'], 'mistake');
    expect(x['shanten_prev'], 1);
    expect(x['shanten_before'], 1);
    expect(x['shanten_loss'], 0);
    expect(x['ukeire_loss'], 5);
    // [3m] 을 버리면 34m 789m 345p 33s 5s 88s → 2m · 5m(34m) · 3s · 8s(또이쯔) · 4s(35s), [3s] 를 버리면 334m 789m 345p 3s 5s 88s
    // → 2m · 5m · 3m · 4s · 8s. 손에 3m · 3s 가 2장씩이라 3m · 3s 남은 장수가 같고(둘 다 2) 두 후보 모두 15장 → 동률 최선.
    expect(x['best'], ['3m', '3s']);
    final opts = (x['options'] as List).cast<Map<String, dynamic>>();
    final o3m = opts.firstWhere((o) => o['discard'] == '3m');
    final o3s = opts.firstWhere((o) => o['discard'] == '3s');
    final o4m = opts.firstWhere((o) => o['discard'] == '4m');
    expect((o3m['tiles'] as Map).keys, ['2m', '5m', '3s', '4s', '8s']);
    expect((o3s['tiles'] as Map).keys, ['2m', '3m', '5m', '4s', '8s']);
    expect((o3m['tiles'] as Map)['3s'], 2);
    expect((o3s['tiles'] as Map)['3m'], 2);
    expect([o3m['shanten'], o3m['total']], [1, 15]);
    expect([o3s['shanten'], o3s['total']], [1, 15]);
    // 4m 버림(쯔모기리): 33m 789m 345p 33s 5s 88s → 3m · 3s · 4s · 8s 4종 10장.
    expect([o4m['shanten'], o4m['total'], o4m['kinds']], [1, 10, 4]);
    expect((o4m['tiles'] as Map).keys, ['3m', '3s', '4s', '8s']);

    // 1번째는 짐작 손패: 숫자 없음.
    final first = turnsOf(f)[0];
    expect(first['status'], 'guessed');
    expect(first['options'], isEmpty);
    expect(first['hand'], isNull);
  });

  test('r11: 서 자리 리치 뒤 8 · 9번째는 defense, others 에 서 리치', () {
    final p = load('r11_130921');
    final f = agentFacts(p, reviewPaifu(p));
    final turns = turnsOf(f);
    for (final n in [8, 9]) {
      final x = turns[n - 1];
      expect(x['status'], 'defense');
      expect(x['grade'], isNull);
      // 자리 2 가 리치(dealer 0 → 서).
      expect(x['riichi_winds'], ['서']);
      expect(x['options'], isNotEmpty);
    }
    final riichi = (f['others'] as List).cast<Map<String, dynamic>>().where((o) => o['kind'] == 'riichi').toList();
    expect([for (final o in riichi) o['wind']], ['서']);
  });

  test('r20: hero 손패 없음 — 모든 차례 숫자 없음, 패효율 null', () {
    final p = load('r20_143236');
    final f = agentFacts(p, reviewPaifu(p));
    expect((f['game'] as Map)['efficiency_pct'], isNull);
    for (final x in turnsOf(f)) {
      expect(x['status'], 'unknownHand');
      expect(x['options'], isEmpty);
      expect(x['best'], isEmpty);
    }
  });

  test('작은 판: others(울기 · 리치 · 남의 론)와 result, hero 울기는 others 에 없음, 동률 최선 셋', () {
    // hero 0 · dealer 0(동). 자리 1 = 남, 2 = 서, 3 = 북.
    final p = Paifu.fromJson({
      'version': 1,
      'id': 'small-id',
      'title': '작은 판 제목',
      'names': ['가', '나', '다', '라'],
      'round': '동1국',
      'dealer': 0,
      'hero': 0,
      'events': [
        {'type': 'draw', 'seat': 0, 'tile': '1z', 'hand': h('123m11456p789s23z')},
        {'type': 'discard', 'seat': 0, 'tile': '1z', 'tsumogiri': true, 'riichi': false, 'hand': h('123m11456p789s23z')},
        {'type': 'discard', 'seat': 1, 'tile': '5z', 'tsumogiri': false, 'riichi': false},
        {'type': 'call', 'seat': 2, 'kind': 'pon', 'from': 1, 'tiles': h('555z')},
        {'type': 'discard', 'seat': 2, 'tile': '9p', 'tsumogiri': false, 'riichi': false},
        {'type': 'discard', 'seat': 3, 'tile': '2s', 'tsumogiri': false, 'riichi': true},
      ],
      'result': {'type': 'ron', 'winner': 3, 'loser': 2, 'win_tile': '9p', 'hand': null, 'melds': []},
    });
    final f = agentFacts(p, reviewPaifu(p));
    final text = jsonEncode(f);
    for (final s in ['small-id', '작은 판 제목', '"가"', '"라"']) {
      expect(text.contains(s), isFalse, reason: s);
    }
    expect((f['game'] as Map)['result'], {'type': 'ron', 'winner': '북', 'loser': '서', 'win_tile': '9p'});
    expect(f['others'], [
      {'step': 4, 'wind': '서', 'kind': 'call', 'call': 'pon', 'tiles': ['5z', '5z', '5z'], 'from': '남'},
      {'step': 6, 'wind': '북', 'kind': 'riichi', 'tile': '2s'},
      {'step': 7, 'wind': '북', 'kind': 'ron', 'tile': '9p', 'from': '서'},
    ]);
    final x = turnsOf(f).single;
    expect(x['step'], 2);
    expect(x['status'], 'graded');
    // 123m 456p 789s 11p 머리 + 동 · 남 · 서 낱장: 셋 중 어느 자패를 버려도 1샹텐이고, 보이는 패가 없어 남은 두 자패가
    // 3장씩 남는 대칭 — 동률 최선 셋(패 번호 순).
    expect(x['best'], ['1z', '2z', '3z']);
    expect(x['actual'], '1z');
    expect(x['grade'], 'best');
    expect(x['ukeire_loss'], 0);
  });
}
