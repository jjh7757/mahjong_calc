import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/tile.dart';
import 'package:mahjong_calc/paifu/agent_facts.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';
import 'package:mahjong_calc/paifu/review_facts.dart';
import 'package:mahjong_calc/paifu/tenhou6_export.dart';

import '../tool/tenhou6_agent_facts.dart' as t6;
import '../tool/tenhou6_features.dart' show ReplayError;

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
/// 2026-11-22 v2(엔진 켬, defense, 리치 중 차례 stance · efficient null): 가장 큰 판 r11 32,942(v1 25,485) · r16 32,881 · r15 32,319.
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
        expect(f['version'], 3);
        // 2반장 예시 11판에는 국 시작 점수가 없다 → game.scores 는 칸은 있고 null(v3).
        expect((f['game'] as Map).containsKey('scores'), isTrue);
        expect((f['game'] as Map)['scores'], isNull);
        // 엔진 없이 만든 리뷰: defense 는 전부 null(v2).
        for (final x in turnsOf(f)) {
          expect(x.containsKey('defense'), isTrue);
          expect(x['defense'], isNull, reason: '$id ${x['turn']}번째 — 엔진 없는 리뷰');
        }
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

  // ── v3 game.scores(설계서 1123 2-2) ──

  group('game.scores(사실표 3)', () {
    /// 작은 판(hero 0 · dealer [dealer])에 국 시작 점수 · 공탁만 바꿔 넣은 사실표의 game.scores.
    Map<String, dynamic>? scoresOf({int dealer = 0, int hero = 0, List<int>? sc, int? kyotaku}) {
      final p = Paifu.fromJson({
        'version': 1,
        'id': 's',
        'round': '동1국',
        'dealer': dealer,
        'hero': hero,
        'start_scores': ?sc,
        'kyotaku': ?kyotaku,
        'events': [
          {'type': 'draw', 'seat': hero, 'tile': '1z', 'hand': h('123m11456p789s23z')},
          {'type': 'discard', 'seat': hero, 'tile': '1z', 'tsumogiri': true, 'riichi': false, 'hand': h('123m11456p789s23z')},
        ],
      });
      final f = agentFacts(p, reviewPaifu(p));
      expect(jsonDecode(jsonEncode(f)), f);
      expect(f['version'], 3);
      return (f['game'] as Map<String, dynamic>)['scores'] as Map<String, dynamic>?;
    }

    test('점수 없음 → null(칸은 있음) · 4개가 아니면 null', () {
      expect(scoresOf(), isNull);
      expect(scoresOf(sc: [25000, 25000, 25000]), isNull);
      expect(scoresOf(sc: [25000, 25000, 25000, 25000, 0]), isNull);
      expect(scoresOf(kyotaku: 2), isNull, reason: '공탁만 있고 점수가 없으면 null');
    });

    test('설계서 2-2 예시: 서 22000(3위) · 동 25000 · 남 31000 · 북 22000(같은 점수 같은 순위) · 공탁 1', () {
      // dealer 2 → 자리 2 동 · 3 남 · 0 서 · 1 북. hero 0 = 서.
      expect(scoresOf(dealer: 2, hero: 0, sc: [22000, 22000, 25000, 31000], kyotaku: 1), {
        'hero': {'wind': '서', 'score': 22000, 'rank': 3},
        'others': [
          {'wind': '동', 'score': 25000, 'rank': 2, 'gap': 3000, 'ahead': true},
          {'wind': '남', 'score': 31000, 'rank': 1, 'gap': 9000, 'ahead': true},
          {'wind': '북', 'score': 22000, 'rank': 3, 'gap': 0, 'ahead': false},
        ],
        'kyotaku': 1,
      });
    });

    test('넷 다 같은 점수 → 모두 1위 · 차 0 · ahead 없음, 공탁 모르면 null', () {
      final s = scoresOf(dealer: 1, hero: 3, sc: [25000, 25000, 25000, 25000])!;
      expect(s['hero'], {'wind': '서', 'score': 25000, 'rank': 1});
      expect(s['others'], [
        for (final w in ['동', '남', '북']) {'wind': w, 'score': 25000, 'rank': 1, 'gap': 0, 'ahead': false},
      ]);
      expect(s.containsKey('kyotaku'), isTrue);
      expect(s['kyotaku'], isNull);
    });

    test('others 순서는 동 · 남 · 서 · 북(hero 빼고) — dealer · hero 모든 짝', () {
      for (var dealer = 0; dealer < 4; dealer++) {
        for (var hero = 0; hero < 4; hero++) {
          final sc = [10000, 20000, 30000, 40000];
          final s = scoresOf(dealer: dealer, hero: hero, sc: sc, kyotaku: 0)!;
          final why = 'dealer $dealer hero $hero';
          final heroWind = winds[(hero - dealer) % 4];
          expect(s['hero'], {'wind': heroWind, 'score': sc[hero], 'rank': 4 - hero}, reason: why);
          final others = (s['others'] as List).cast<Map<String, dynamic>>();
          expect([for (final o in others) o['wind']], [for (final w in winds) if (w != heroWind) w], reason: why);
          for (final o in others) {
            final seat = (dealer + winds.indexOf(o['wind'] as String)) % 4;
            expect(o, {
              'wind': o['wind'],
              'score': sc[seat],
              'rank': 4 - seat,
              'gap': (sc[seat] - sc[hero]).abs(),
              'ahead': seat > hero,
            }, reason: '$why ${o['wind']}');
          }
          expect(s['kyotaku'], 0, reason: why);
        }
      }
    });

    test('3반장 h3_145625(남4국 · dealer 3 · hero 2 = 북) 손으로 본 값', () {
      final p = Paifu.fromJson(
          jsonDecode(File('assets/paifu_h3/h3_145625.json').readAsStringSync(encoding: utf8)) as Map<String, dynamic>);
      expect([p.dealer, p.hero, p.startScores, p.kyotaku], [3, 2, [30900, 24100, 17900, 27100], 0]);
      final f = agentFacts(p, reviewPaifu(p));
      expect((f['game'] as Map)['hero_wind'], '북');
      // 자리 3 동 27100 · 0 남 30900 · 1 서 24100 · 2 북(hero) 17900.
      expect((f['game'] as Map)['scores'], {
        'hero': {'wind': '북', 'score': 17900, 'rank': 4},
        'others': [
          {'wind': '동', 'score': 27100, 'rank': 2, 'gap': 9200, 'ahead': true},
          {'wind': '남', 'score': 30900, 'rank': 1, 'gap': 13000, 'ahead': true},
          {'wind': '서', 'score': 24100, 'rank': 3, 'gap': 6200, 'ahead': true},
        ],
        'kyotaku': 0,
      });
    });

    test('판 2 의 다른 칸은 그대로: 점수를 넣어도 game 의 scores 밖 · turns · others 같음', () {
      final p = load('r19_142013');
      final q = p.copyWith(startScores: [25000, 31000, 19000, 25000], kyotaku: 2);
      final a = agentFacts(p, reviewPaifu(p)), b = agentFacts(q, reviewPaifu(q));
      expect({...(b['game'] as Map)}..remove('scores'), {...(a['game'] as Map)}..remove('scores'));
      expect(b['turns'], a['turns']);
      expect(b['others'], a['others']);
      expect((b['game'] as Map).keys.last, 'scores');
      expect((b['game'] as Map)['scores'], isNotNull);
    });
  });

  // ── v2 defense(설계서 1122 2절) ──

  group('defense 단계 · stance 경계(순수 함수)', () {
    test('위험 단계: 3 · 8 · 18 미만', () {
      expect(riskLevel(0, safeForAll: true), '안전');
      expect(riskLevel(25, safeForAll: true), '안전'); // 모두에게 안전패면 값과 상관없이
      expect(riskLevel(0, safeForAll: false), '낮음');
      expect(riskLevel(2.99, safeForAll: false), '낮음');
      expect(riskLevel(3.0, safeForAll: false), '보통');
      expect(riskLevel(7.99, safeForAll: false), '보통');
      expect(riskLevel(8.0, safeForAll: false), '높음');
      expect(riskLevel(17.99, safeForAll: false), '높음');
      expect(riskLevel(18.0, safeForAll: false), '매우 높음');
      expect(riskLevel(100, safeForAll: false), '매우 높음');
      expect([riskLevelLowBelow, riskLevelMidBelow, riskLevelHighBelow], [3.0, 8.0, 18.0]);
    });
    test('stance: 차 2 미만 · 같은 구간이면 folded, 5 이상 pushed', () {
      expect(defenseStance(0, 0), 'folded');
      expect(defenseStance(1.99, 0), 'folded');
      expect(defenseStance(2.0, 0), 'between');
      expect(defenseStance(4.99, 0), 'between');
      expect(defenseStance(5.0, 0), 'pushed');
      expect(defenseStance(12.0, 7.0), 'pushed');
      expect(defenseStance(10.0, 8.5), 'folded');
      expect([stancePushedAtLeast, stanceFoldedBelow], [5.0, 2.0]);
    });
    test('stance: 구간 경계(a4 F1 — 차 2 미만이라도 구간이 다르면 between)', () {
      // (버린 패, 가장 낮은 위험) 꼴로 적는다. 함수 인자 순서는 (actual, min).
      expect(defenseStance(8.5, 7.5), 'between'); // 보통 → 높음(전에는 folded)
      expect(defenseStance(7.9, 7.0), 'folded'); // 둘 다 보통
      expect(defenseStance(1.9, 0), 'folded'); // 둘 다 낮음
      expect(defenseStance(3.5, 2.5), 'between'); // 낮음 → 보통
      expect(defenseStance(14, 9), 'pushed'); // 차 5
      for (final v in [0.0, 2.99, 3.0, 8.0, 17.99, 18.0, 40.0]) {
        expect(defenseStance(v, v), 'folded', reason: '같은 값 $v');
      }
      expect(defenseStance(18.5, 17.5), 'between'); // 높음 → 매우 높음
      expect(defenseStance(19.9, 18.0), 'folded'); // 둘 다 매우 높음
    });
  });

  group('defense — 예시 11판(엔진 켬)', () {
    // 2026-11-22 잰 값: 채워진 차례 L16 2 · r11 9 · r12 5(그중 수비 L16 2 · r11 2, 나머지는 리치 중 차례) = 16.
    var filled = 0, stanceFilled = 0;
    for (final id in games) {
      test(id, () {
        final p = load(id);
        final r = engineReview(p, id);
        final f = agentFacts(p, r);
        final text = jsonEncode(f);
        expect(jsonDecode(text), f);
        final bytes = utf8.encode(text).length;
        // ignore: avoid_print
        print('$id 엔진 켠 사실표 압축 $bytes bytes');
        expect(bytes, lessThanOrEqualTo(maxBytes), reason: '$id 압축 크기');
        expect(f['version'], 3);

        // 엔진 켠 리뷰 · 끈 리뷰의 다른 칸은 같다(defense 만 다름).
        final plain = agentFacts(p, reviewPaifu(p));
        final a = [for (final x in turnsOf(f)) {...x}..remove('defense')];
        final b = [for (final x in turnsOf(plain)) {...x}..remove('defense')];
        expect(a, b, reason: id);

        for (final (k, x) in turnsOf(f).indexed) {
          final tr = r.turns[k];
          final why = '$id ${x['turn']}번째';
          final d = x['defense'] as Map<String, dynamic>?;
          final byKind = tr.riskByKind;
          final want = tr.riichiSeats.isNotEmpty && tr.before != null && tr.riskTable != null && byKind != null;
          if (!want) {
            expect(d, isNull, reason: why);
            continue;
          }
          expect(d, isNotNull, reason: why);
          filled++;
          expect(d!.keys, ['threat_winds', 'tiles', 'actual', 'safest', 'efficient', 'stance', 'fold_spot'], reason: why);
          // % 값은 넣지 않는다: defense 안에 실수가 없다.
          void noDouble(Object? v) {
            if (v is Map) v.values.forEach(noDouble);
            if (v is List) v.forEach(noDouble);
            expect(v is double, isFalse, reason: '$why defense 안의 실수 $v');
          }

          noDouble(d);
          // v3: 접는 자리(pushFold)일 때만 객체. 예시 11판에는 접는 자리가 없어(설계서 1123 6절) 전부 null.
          expect(d['fold_spot'],
              tr.pushFold == null ? isNull : {'shanten': tr.pushFold!.shantenBefore, 'ai_fold_pct': pushFoldAiFoldPct},
              reason: why);
          expect(tr.pushFold, isNull, reason: why);
          expect(d['threat_winds'], [for (final s in tr.riskSeats) winds[p.windOf(s)]], reason: why);

          // tiles: 손의 패 종류 전부, 합친 위험 오름차순 · 같으면 패 번호 순. 단계는 문턱을 여기서 다시 적어 맞댐.
          final kinds = byKind.keys.toList()..sort((u, v) => byKind[u] != byKind[v] ? byKind[u]!.compareTo(byKind[v]!) : u - v);
          expect(kinds.toSet(), {for (var t = 0; t < Tiles.count; t++) if (tr.before![t] > 0) t}, reason: why);
          String lv(int t) {
            if (tr.riskTable!.safeForAll34[t]) return '안전';
            final v = byKind[t]!;
            return v < 3 ? '낮음' : v < 8 ? '보통' : v < 18 ? '높음' : '매우 높음';
          }

          final tiles = (d['tiles'] as List).cast<Map<String, dynamic>>();
          expect([for (final e in tiles) e['tile']], [for (final t in kinds) Tiles.toCode(t)], reason: why);
          expect([for (final e in tiles) e['level']], [for (final t in kinds) lv(t)], reason: why);
          expect([for (final e in tiles) e['genbutsu']], [for (final t in kinds) tr.safeTiles.contains(t)], reason: why);
          // 사실표의 safe_tiles 와 같은 뜻.
          expect({for (final e in tiles) if (e['genbutsu'] == true) e['tile']}, (x['safe_tiles'] as List).toSet(),
              reason: why);

          // actual · safest · stance.
          final act = tr.discard.tile;
          final ra = byKind[act]!;
          final minR = byKind[kinds.first]!;
          expect(d['actual'], {
            'tile': Tiles.toCode(act),
            'level': lv(act),
            'rank': 1 + kinds.where((t) => byKind[t]! < ra).length,
            'of': kinds.length,
          }, reason: why);
          expect(d['actual']['tile'], x['discard'], reason: why);
          expect(tr.riskOfActual, ra, reason: why);
          expect(d['safest'], [for (final t in kinds) if (byKind[t] == minR) Tiles.toCode(t)], reason: why);
          expect((d['safest'] as List).first, Tiles.toCode(tr.minRiskTile!), reason: why);
          // 내가 리치 중(forced)인 차례는 고를 수 없었다 — stance · efficient 는 null(11-22 보완).
          if (tr.status == ReviewStatus.forced) {
            expect(d['stance'], isNull, reason: why);
            expect(d['efficient'], isNull, reason: why);
            continue;
          }
          stanceFilled++;
          // stance(a4 F1): 차 5 이상 pushed · 차 2 미만이고 같은 구간(3 · 8 · 18, '안전' 표시와 상관없이 숫자로) folded.
          final diff = ra - minR;
          int band(double v) => v < 3 ? 0 : v < 8 ? 1 : v < 18 ? 2 : 3;
          expect(d['stance'], diff >= 5 ? 'pushed' : diff < 2 && band(ra) == band(minR) ? 'folded' : 'between',
              reason: why);

          // efficient: 엔진 순위에서 샹텐을 물리지 않는 첫 후보(없으면 mhBest).
          final mh = tr.mh;
          if (mh == null) {
            expect(d['efficient'], isNull, reason: why);
          } else {
            final e = mh.where((m) => !m.isBackward).firstOrNull?.tile ?? tr.mhBest!;
            expect(d['efficient'], {'tile': Tiles.toCode(e), 'level': lv(e)}, reason: why);
          }
        }
      });
    }
    test('채워진 차례 수(위 11판 뒤)', () {
      // ignore: avoid_print
      print('defense 채워진 차례 $filled · stance 채워진 차례 $stanceFilled');
      expect(filled, 16);
      // 수비 상태 L16 17 · 18, r11 8 · 9 만 stance 가 있다(나머지 12차례는 리치 중).
      expect(stanceFilled, 4);
    });
  });

  test('defense: 리치 중 차례는 stance · efficient null, 수비 차례는 채워짐(r11 · r12)', () {
    for (final id in ['r11_130921', 'r12_131655']) {
      final p = load(id);
      for (final x in turnsOf(agentFacts(p, engineReview(p, id)))) {
        final d = x['defense'] as Map<String, dynamic>?;
        if (d == null) continue;
        final why = '$id ${x['turn']}번째 ${x['status']}';
        if (x['status'] == 'forced') {
          expect(d['stance'], isNull, reason: why);
          expect(d['efficient'], isNull, reason: why);
          // 버린 패의 위험(사실)은 남는다.
          expect(d['actual']['tile'], x['discard'], reason: why);
          expect(d['tiles'], isNotEmpty, reason: why);
          expect(d['safest'], isNotEmpty, reason: why);
          expect(d.containsKey('fold_spot'), isTrue, reason: why);
        } else {
          expect(x['status'], 'defense', reason: why);
          expect(d['stance'], isIn(['pushed', 'folded', 'between']), reason: why);
          expect(d['efficient'], isNotNull, reason: why);
        }
      }
    }
    final p = load('r12_131655');
    final f = turnsOf(agentFacts(p, engineReview(p, 'r12_131655')));
    expect([for (final x in f) if (x['defense'] != null) x['status']], List.filled(5, 'forced'));
    final r11 = turnsOf(agentFacts(load('r11_130921'), engineReview(load('r11_130921'), 'r11_130921')));
    expect([r11[7]['defense']['stance'], r11[8]['defense']['stance']], ['pushed', 'pushed']);
  });

  test('defense: 리치 없는 판 · 리치 전 차례는 엔진을 켜도 null', () {
    // r19: 남의 리치가 없다.
    final p = load('r19_142013');
    final f = agentFacts(p, engineReview(p, 'r19_142013'));
    expect(turnsOf(f).every((x) => x['defense'] == null && (x['riichi_winds'] as List).isEmpty), isTrue);
    // r11: 서 리치 전 1~7번째는 null, 8번째부터 채워짐.
    final q = load('r11_130921');
    final g = turnsOf(agentFacts(q, engineReview(q, 'r11_130921')));
    expect([for (final x in g) x['defense'] != null], [for (final x in g) (x['riichi_winds'] as List).isNotEmpty]);
    expect(g.indexWhere((x) => x['defense'] != null), 7);
  });

  test('defense: r11 8번째(수비) 손으로 본 값', () {
    final p = load('r11_130921');
    final x = turnsOf(agentFacts(p, engineReview(p, 'r11_130921')))[7];
    expect(x['status'], 'defense');
    final d = x['defense'] as Map<String, dynamic>;
    // 현물은 [6만] 하나(사실표 safe_tiles) — 모두에게 안전패라 가장 안전.
    expect(d['safest'], ['6m']);
    expect((d['tiles'] as List).first, {'tile': '6m', 'level': '안전', 'genbutsu': true});
    expect(d['actual']['tile'], '9p');
    expect(d['actual']['of'], 13);
  });

  group('천봉 길(tool/tenhou6_agent_facts.dart) = 직접 낸 사실표', () {
    // 매장 판을 toTenhou6(남의 쯔모기리 모름 = tedashi)로 바꿔 천봉 길로 다시 낸 사실표가, 손패를 아는 차례에서 같은가.
    // step 은 비교하지 않는다(천봉 길은 남의 뽑기 사건이 없어 사건 번호가 다를 수 있음).
    for (final id in ['r11_130921', 'L16_135321']) {
      test(id, () {
        final p = load(id);
        final direct = agentFacts(p, engineReview(p, id));
        final ex = toTenhou6(p);
        final viaT6 = t6.tenhouAgentFacts(jsonDecode(jsonEncode(ex.json)) as Map<String, dynamic>, 0, ex.heroIndex);
        expect(viaT6['version'], 3);
        final g1 = direct['game'] as Map<String, dynamic>, g2 = viaT6['game'] as Map<String, dynamic>;
        for (final k in ['round', 'honba', 'hero_wind']) {
          expect(g2[k], g1[k], reason: k);
        }
        final r1 = g1['result'] as Map?, r2 = g2['result'] as Map?;
        expect(r2?['type'], r1?['type']);
        expect(r2?['winner'], r1?['winner']);
        expect(r2?['loser'], r1?['loser']);
        final t1 = turnsOf(direct), t2 = turnsOf(viaT6);
        expect(t2.length, t1.length);
        var compared = 0, defense = 0;
        for (final (k, a) in t1.indexed) {
          if ((a['options'] as List).isEmpty) continue;
          compared++;
          if (a['defense'] != null) defense++;
          final b = t2[k];
          for (final key in a.keys) {
            if (key == 'step') continue;
            expect(b[key], a[key], reason: '$id ${a['turn']}번째 $key');
          }
        }
        // ignore: avoid_print
        print('$id 천봉 길 비교 $compared차례(수비 칸 $defense)');
        expect(compared, greaterThan(0));
        expect(defense, greaterThan(0));
        // 이름 · 판 ID 없음.
        final text = jsonEncode(viaT6);
        for (final s in [...p.names, p.id, p.title]) {
          if (s.isNotEmpty) expect(text.contains(s), isFalse, reason: s);
        }
      });
    }
    test('점수 없는 판을 천봉으로 내보내면 25000 넷 · 공탁 0 이 실려 game.scores 가 채워짐', () {
      final p = load('r19_142013');
      final ex = toTenhou6(p);
      final f = t6.tenhouAgentFacts(jsonDecode(jsonEncode(ex.json)) as Map<String, dynamic>, 0, ex.heroIndex);
      final s = (f['game'] as Map)['scores'] as Map<String, dynamic>;
      expect(s['hero'], {'wind': '서', 'score': 25000, 'rank': 1});
      expect([for (final o in s['others'] as List) o['score']], [25000, 25000, 25000]);
      expect(s['kyotaku'], 0);
    });

    // 3반장(국 시작 점수 · 공탁 있음, dealer ≠ 0): 패보 → toTenhou6(우리 자리 → 천봉 자리로 돌림) → 천봉 길(log[1] 을 그대로
    // 천봉 자리 = kyokuToPaifu 의 자리로) 의 game.scores 가 직접 낸 것과 같은가 — 두 자리 매김이 서로 맞는지의 대조.
    for (final id in ['h3_144427', 'h3_145625', 'h3_153825']) {
      test('$id: 천봉 길 game.scores = 직접', () {
        final p = Paifu.fromJson(
            jsonDecode(File('assets/paifu_h3/$id.json').readAsStringSync(encoding: utf8)) as Map<String, dynamic>);
        final direct = (agentFacts(p, reviewPaifu(p))['game'] as Map)['scores'];
        expect(direct, isNotNull);
        final ex = toTenhou6(p);
        final log = (ex.json['log'] as List).first as List;
        expect((log[0] as List)[2], p.kyotaku ?? 0);
        final viaT6 = t6.tenhouAgentFacts(jsonDecode(jsonEncode(ex.json)) as Map<String, dynamic>, 0, ex.heroIndex);
        expect((viaT6['game'] as Map)['scores'], direct, reason: id);
        expect((viaT6['game'] as Map)['hero_wind'], (agentFacts(p, reviewPaifu(p))['game'] as Map)['hero_wind']);
      });
    }

    test('천봉 국 머리 → start_scores · kyotaku(꼴이 다르면 null)', () {
      expect(t6.tenhouStartScores([[3, 1, 2], [25000, 26000, 24000, 23000]]), [25000, 26000, 24000, 23000]);
      expect(t6.tenhouKyotaku([[3, 1, 2], [25000, 26000, 24000, 23000]]), 2);
      expect(t6.tenhouStartScores([[3, 1, 2], [25000, 26000, 24000]]), isNull);
      expect(t6.tenhouStartScores([[3, 1, 2], 'x']), isNull);
      expect(t6.tenhouKyotaku([[3, 1], [25000, 26000, 24000, 23000]]), isNull);
    });

    test('깡 든 국은 거절', () {
      final p = load('r19_142013');
      final j = jsonDecode(jsonEncode(toTenhou6(p).json)) as Map<String, dynamic>;
      final log = (j['log'] as List).first as List;
      // 아무 자리의 버림 줄에 안깡 표기를 하나 넣는다.
      (log[6] as List).add('a111111');
      expect(() => t6.tenhouAgentFacts(j, 0, 0), throwsA(isA<ReplayError>()));
      expect(() => t6.tenhouAgentFacts(j, 5, 0), throwsA(isA<ReplayError>()));
    });
  });
}

/// 엔진 켠 리뷰는 한 판 수 초라 판마다 한 번만.
final _engineCache = <String, PaifuReview>{};

PaifuReview engineReview(Paifu p, String id) => _engineCache[id] ??= reviewPaifu(p, withEngine: true);
