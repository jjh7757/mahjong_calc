// 탁자 사실표(lib/paifu/table_facts.dart, 설계서 docs/postgame_review_chat_design_1124.md 3 · 4절) 시험.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/risk.dart' show riskOf;
import 'package:mahjong_calc/engine/tile.dart';
import 'package:mahjong_calc/paifu/agent_facts.dart' show riskLevel, riskLevels;
import 'package:mahjong_calc/paifu/mh_context.dart' show riskContextAt;
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/table_facts.dart';

Map<String, dynamic> d(int seat, String tile, {bool riichi = false}) =>
    {'type': 'discard', 'seat': seat, 'tile': tile, 'tsumogiri': null, 'riichi': riichi};

Map<String, dynamic> c(int seat, int from, List<String> tiles, {String kind = 'pon'}) =>
    {'type': 'call', 'seat': seat, 'kind': kind, 'from': from, 'tiles': tiles};

/// 손으로 만든 한 판(친 = 자리 0 → 0 동 · 1 남 · 2 서 · 3 북). 맨 앞 뽑기 사건은 step 에서 빠지는지 보려고 둔다.
/// 사건 인덱스(= step − 1)를 주석에 적는다.
Paifu sample() => Paifu.fromJson({
      'version': 1,
      'id': 'secret_id',
      'title': '비밀 제목',
      'round': '동1국',
      'honba': 1,
      'dealer': 0,
      'hero': 0,
      'names': ['가나다', '라마바', '사아자', '차카타'],
      'note': '메모 숨김',
      'start_scores': [25000, 24000, 26000, 25000],
      'dora_indicators': ['2s'],
      'events': [
        {'type': 'draw', 'seat': 0, 'tile': '1z', 'hand': null}, // 0
        d(0, '1z'), // 1
        d(1, '2s'), // 2
        c(2, 1, ['2s', '2s', '2s']), // 3  서가 남의 2s 를 퐁(강에서 빠짐)
        d(2, '9p'), // 4
        d(3, '6m', riichi: true), // 5  북 리치
        d(0, '4m'), // 6  vs 북: 현물 아님 · 스지 아님(1m · 7m 없음)
        d(1, '3m'), // 7  6m 이 북 현물 → 스지
        d(2, '6m'), // 8  북 현물, 보인 6m 1장
        d(3, '2z'), // 9
        d(0, '1m'), // 10 4m 이 리치 뒤 버림 → 스지
        c(1, 0, ['1m', '1m', '1m']), // 11 남이 동의 1m 을 퐁
        d(1, '1s'), // 12 2s 보인 4장(퐁 3 + 표시패 1) → 노찬스
        d(2, '1m'), // 13 리치 뒤 버린 1m → 현물, 보인 1m 3장(묶음 한 번만)
        d(3, '9m'), // 14
        d(0, '5z', riichi: true), // 15 동 리치(vs 북)
        d(1, '5m'), // 16 vs 동 · 북 둘 다(바람 순) — 이 패로 방총
      ],
      'result': {'type': 'ron', 'winner': 0, 'loser': 1, 'win_tile': '0m', 'hand': null, 'melds': []},
    });

List<Map<String, dynamic>> eventsOf(Map<String, dynamic> f) => (f['events'] as List).cast<Map<String, dynamic>>();

Map<String, dynamic> at(Map<String, dynamic> f, int step) => eventsOf(f).firstWhere((e) => e['step'] == step);

Map<String, dynamic> vsOf(Map<String, dynamic> ev, String wind) =>
    (ev['vs'] as List).cast<Map<String, dynamic>>().firstWhere((v) => v['wind'] == wind);

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

void main() {
  group('손으로 만든 판', () {
    final p = sample();
    final f = tableFacts(p);

    test('game · 이름 · id · note 없음', () {
      expect(f['version'], 1);
      expect(f['game'], {
        'round': '동1국',
        'honba': 1,
        'dealer_wind': '동',
        'dora_indicators': ['2s'],
        'scores': {'동': 25000, '남': 24000, '서': 26000, '북': 25000},
        'result': {'type': 'ron', 'winner': '동', 'loser': '남', 'win_tile': '5m'},
      });
      final all = strings(f).toSet();
      for (final s in ['secret_id', '비밀 제목', '가나다', '라마바', '사아자', '차카타', '메모 숨김']) {
        expect(all.contains(s), isFalse, reason: s);
      }
      expect(() => jsonEncode(f), returnsNormally);
    });

    test('사건: 뽑기 빼고 버림 · 울기만, step = 인덱스 + 1, turn_of_seat', () {
      final ev = eventsOf(f);
      expect(ev.length, 16);
      expect(ev.map((e) => e['step']), [for (var s = 2; s <= 17; s++) s]);
      expect(at(f, 2), {
        'step': 2,
        'wind': '동',
        'kind': 'discard',
        'tile': '1z',
        'turn_of_seat': 1,
        'riichi': false,
        'after_riichi_of': <String>[],
        'vs': <Map<String, dynamic>>[],
      });
      expect(at(f, 4), {'step': 4, 'wind': '서', 'kind': 'call', 'call': 'pon', 'from': '남', 'tiles': ['2s', '2s', '2s']});
      expect(at(f, 16)['turn_of_seat'], 4); // 동: 1z 4m 1m 5z
      expect(at(f, 16)['riichi'], isTrue);
      expect(at(f, 17)['turn_of_seat'], 4); // 남: 2s 3m 1s 5m(울려 간 2s 도 셈)
    });

    test('리치 뒤 표시: 리치 선언 버림 자신은 빠지고, 다른 리치 자리는 바람 순', () {
      expect(at(f, 6)['after_riichi_of'], isEmpty); // 북 리치 선언
      expect(at(f, 5)['after_riichi_of'], isEmpty); // 리치 전
      expect(at(f, 7)['after_riichi_of'], ['북']);
      expect(at(f, 10)['after_riichi_of'], isEmpty); // 북 자신의 리치 뒤 버림
      expect(at(f, 16)['after_riichi_of'], ['북']); // 동 리치 선언(북 리치 뒤)
      expect(at(f, 17)['after_riichi_of'], ['동', '북']);
      expect((at(f, 17)['vs'] as List).map((v) => v['wind']), ['동', '북']);
    });

    test('현물: 리치한 사람 버림 ∪ 리치 뒤 누구든 버린 패', () {
      expect(vsOf(at(f, 7), '북')['genbutsu'], isFalse); // 4m
      expect(vsOf(at(f, 9), '북')['genbutsu'], isTrue); // 6m: 북 버림
      expect(vsOf(at(f, 14), '북')['genbutsu'], isTrue); // 1m: 리치 뒤 동이 버림(울려 갔어도)
      expect(vsOf(at(f, 17), '북')['genbutsu'], isFalse); // 5m
      expect(vsOf(at(f, 17), '동')['genbutsu'], isFalse); // 동 버림 1z 4m 1m 5z
    });

    test('스지', () {
      expect(vsOf(at(f, 7), '북')['suji'], isFalse); // 4m: 1m · 7m 둘 다 필요
      expect(vsOf(at(f, 8), '북')['suji'], isTrue); // 3m: 6m
      expect(vsOf(at(f, 11), '북')['suji'], isTrue); // 1m: 4m(리치 뒤 동)
      expect(vsOf(at(f, 17), '북')['suji'], isFalse); // 5m: 2m · 8m 없음
      expect(vsOf(at(f, 16), '북')['suji'], isFalse); // 자패
    });

    test('보인 장수: 이번 패 빼고 · 울려 간 버림은 묶음 쪽 한 번만 · 표시패 포함', () {
      expect(vsOf(at(f, 7), '북')['visible'], 0); // 4m 자신은 안 셈
      expect(vsOf(at(f, 9), '북')['visible'], 1); // 6m: 북 강
      expect(vsOf(at(f, 11), '북')['visible'], 0); // 1m 처음
      expect(vsOf(at(f, 14), '북')['visible'], 3); // 1m: 퐁 3장(동 강의 1m 은 빠짐)
      expect(vsOf(at(f, 16), '북')['visible'], 0); // 5z
    });

    test('노찬스: 양면 모양이 모두 보인 4장에 막힘', () {
      expect(vsOf(at(f, 13), '북')['no_chance'], isTrue); // 1s: (2s, 3s) — 2s 퐁 3 + 표시패 1
      expect(vsOf(at(f, 13), '북')['visible'], 0);
      expect(vsOf(at(f, 7), '북')['no_chance'], isFalse);
      expect(vsOf(at(f, 16), '북')['no_chance'], isFalse); // 자패
    });

    test('단계: 버린 사람 시점 엔진 표의 R 한 사람 값, 현물이면 안전', () {
      for (final e in eventsOf(f)) {
        for (final v in (e['vs'] as List? ?? const []).cast<Map<String, dynamic>>()) {
          expect(riskLevels, contains(v['level']), reason: 'step ${e['step']}');
          if (v['genbutsu'] == true) expect(v['level'], '안전');
        }
      }
      // step 17(남이 5m, vs 동 · 북)을 엔진으로 따로 낸다.
      final i = 16;
      final v34 = List<int>.filled(Tiles.count, 0);
      final st = p.states[i];
      for (var s = 0; s < 4; s++) {
        for (final r in st.rivers[s]) {
          if (!r.called) v34[r.tile.tile]++;
        }
        for (final m in st.melds[s]) {
          for (final t in m.tiles) {
            v34[t.tile]++;
          }
        }
      }
      for (final t in p.doraIndicators) {
        v34[t.tile]++;
      }
      final table = riskOf(riskContextAt(p, i, selfSeat: 1, visible34: v34));
      final t = Tiles.parse('5m');
      for (final (seat, wind) in [(0, '동'), (3, '북')]) {
        final o = table.bySeat[seat]!;
        expect(vsOf(at(f, 17), wind)['level'], riskLevel(o.risk34[t] * o.tenpaiRate / 100, safeForAll: o.safe34[t]));
      }
    });

    test('장면: 방총 장면 · 리치 · 울기', () {
      final sc = (f['scenes_by_seat'] as Map).cast<String, dynamic>();
      expect(sc.keys, ['동', '남', '서', '북']);
      final nan = (sc['남'] as List).cast<Map<String, dynamic>>();
      expect(nan.first, {'step': 17, 'why': 'deal_in'});
      expect(nan.where((s) => s['why'] == 'call').single['step'], 12);
      expect(nan.map((s) => s['step']).toSet().length, nan.length);
      expect((sc['북'] as List).cast<Map<String, dynamic>>().single, {'step': 6, 'why': 'own_riichi'});
      final dong = (sc['동'] as List).cast<Map<String, dynamic>>();
      expect(dong.any((s) => s['why'] == 'own_riichi' && s['step'] == 16), isTrue);
      expect(dong.any((s) => s['why'] == 'deal_in'), isFalse);
      expect((sc['서'] as List).cast<Map<String, dynamic>>().where((s) => s['why'] == 'call').single['step'], 4);
    });
  });

  test('자리 바람 · 점수는 친 기준(친 = 자리 2), 점수 없으면 null, 결과 없으면 null', () {
    final p = Paifu.fromJson({
      'version': 1,
      'id': 'x',
      'dealer': 2,
      'hero': 0,
      'start_scores': [1000, 2000, 3000, 4000],
      'events': [d(2, '1p'), d(3, '2p'), d(0, '3p'), d(1, '4p')],
    });
    final f = tableFacts(p);
    expect(eventsOf(f).map((e) => e['wind']), ['동', '남', '서', '북']);
    expect((f['game'] as Map)['scores'], {'동': 3000, '남': 4000, '서': 1000, '북': 2000});
    expect((f['game'] as Map)['dealer_wind'], '동');
    expect((f['game'] as Map)['result'], isNull);
    final q = Paifu.fromJson({'version': 1, 'id': 'y', 'hero': 0, 'events': <Object>[]});
    expect((tableFacts(q)['game'] as Map)['scores'], isNull);
  });

  test('가깡은 앞 퐁 묶음을 바꾼다(퐁 3 + 가깡 4 로 겹쳐 세지 않음 — 재생 탁자와 같은 셈)', () {
    final p = Paifu.fromJson({
      'version': 1,
      'id': 'k',
      'hero': 0,
      'events': [
        d(0, '7p', riichi: true), // 1
        d(1, '3p'), // 2
        c(2, 1, ['3p', '3p', '3p']), // 3
        d(2, '1z'), // 4
        {'type': 'call', 'seat': 2, 'kind': 'kakan', 'from': 2, 'tiles': ['3p', '3p', '3p', '3p']}, // 5
        d(2, '1p'), // 6 vs 동: 1p 의 양면 (2p, 3p) — 3p 보인 4장
      ],
    });
    final f = tableFacts(p);
    expect(at(f, 5), {'step': 5, 'wind': '서', 'kind': 'call', 'call': 'kakan', 'from': null, 'tiles': ['3p', '3p', '3p', '3p']});
    final ev = at(f, 6);
    expect(vsOf(ev, '동')['no_chance'], isTrue);
    expect((ev['vs'] as List).length, 1);
  });

  group('장면 고르기(tableScenes)', () {
    Map<String, dynamic> dis(int step, String wind, String tile,
            {bool riichi = false, List<Map<String, dynamic>> vs = const []}) =>
        {'step': step, 'wind': wind, 'kind': 'discard', 'tile': tile, 'riichi': riichi, 'vs': vs};
    Map<String, dynamic> v(String level, {bool genbutsu = false, String wind = '북'}) =>
        {'wind': wind, 'genbutsu': genbutsu, 'level': level};
    final ron = {'type': 'ron', 'winner': '북', 'loser': '남', 'win_tile': '5p'};

    test('순서: 방총 → 위험(높은 단계 먼저, 같으면 앞 걸음) 둘 → 리치 → 울기, 상한 5', () {
      final events = [
        dis(3, '남', '1p', vs: [v('높음')]),
        dis(5, '남', '2p', vs: [v('높음')]),
        dis(7, '남', '3p', vs: [v('매우 높음', genbutsu: true)]), // 현물이면 빠짐
        dis(8, '남', '4p', vs: [v('보통'), v('높음', wind: '동')]), // R 중 하나라도 높음이면 후보
        dis(9, '남', '6p', vs: [v('매우 높음')]),
        dis(11, '남', '7p', riichi: true),
        {'step': 12, 'wind': '남', 'kind': 'call', 'call': 'pon', 'from': '동', 'tiles': ['1z', '1z', '1z']},
        {'step': 14, 'wind': '남', 'kind': 'call', 'call': 'chi', 'from': '동', 'tiles': ['1s', '2s', '3s']},
        dis(20, '남', '5p'),
      ];
      expect(tableScenes(events, '남', ron), [
        {'step': 20, 'why': 'deal_in'},
        {'step': 9, 'why': 'risky_after_riichi'},
        {'step': 3, 'why': 'risky_after_riichi'},
        {'step': 11, 'why': 'own_riichi'},
        {'step': 12, 'why': 'call'},
      ]);
      // 다른 자리 · 낮은 단계뿐인 자리는 빈 목록.
      expect(tableScenes(events, '서', ron), isEmpty);
    });

    test('같은 걸음은 한 번만, 마지막 버림이 화료패가 아니면 방총 장면 없음', () {
      final events = [
        dis(3, '남', '1p', vs: [v('높음')]),
        dis(9, '남', '5p', riichi: true, vs: [v('매우 높음')]),
        dis(15, '남', '9p'),
      ];
      // 리치 선언이 위험 장면과 같은 걸음 → own_riichi 는 빠진다. 마지막 버림 9p ≠ 5p → 방총 없음.
      expect(tableScenes(events, '남', ron), [
        {'step': 9, 'why': 'risky_after_riichi'},
        {'step': 3, 'why': 'risky_after_riichi'},
      ]);
      // 방총 걸음이 위험 후보와 같으면 위험 쪽이 빠지고 다음 후보로 채우지 않는다.
      final events2 = [
        dis(3, '남', '1p', vs: [v('높음')]),
        dis(4, '남', '2p', vs: [v('높음')]),
        dis(9, '남', '5p', vs: [v('매우 높음')]),
      ];
      expect(tableScenes(events2, '남', ron), [
        {'step': 9, 'why': 'deal_in'},
        {'step': 3, 'why': 'risky_after_riichi'},
      ]);
      expect(tableScenes(events2, '남', {'type': 'tsumo', 'winner': '북', 'loser': null, 'win_tile': '5p'}), [
        {'step': 9, 'why': 'risky_after_riichi'},
        {'step': 3, 'why': 'risky_after_riichi'},
      ]);
    });
  });

  test('예시 22판: 예외 없이 만들어지고 jsonEncode 되고 정의가 앞뒤 맞음', () {
    final files = [
      for (final dir in ['assets/paifu', 'assets/paifu_h3'])
        ...Directory(dir).listSync().whereType<File>().where((f) => f.path.endsWith('.json')),
    ];
    expect(files.length, 22);
    var withVs = 0;
    for (final file in files) {
      final p = Paifu.fromJson(jsonDecode(file.readAsStringSync(encoding: utf8)) as Map<String, dynamic>);
      final f = tableFacts(p);
      final text = jsonEncode(f);
      expect(jsonDecode(text), isA<Map<String, dynamic>>());
      final all = strings(f).toSet();
      expect(all.contains(p.id), isFalse, reason: file.path);
      for (final n in p.names.where((n) => n.isNotEmpty)) {
        expect(all.contains(n), isFalse, reason: '${file.path} $n');
      }
      final discards = p.events.where((e) => e.type == PaifuEventType.discard).length;
      expect(eventsOf(f).where((e) => e['kind'] == 'discard').length, discards, reason: file.path);
      for (final e in eventsOf(f)) {
        for (final v in (e['vs'] as List? ?? const []).cast<Map<String, dynamic>>()) {
          withVs++;
          expect(riskLevels, contains(v['level']), reason: '${file.path} step ${e['step']}');
          if (v['genbutsu'] == true) expect(v['level'], '안전');
        }
      }
      for (final sc in (f['scenes_by_seat'] as Map).values) {
        final l = (sc as List).cast<Map<String, dynamic>>();
        expect(l.length, lessThanOrEqualTo(tableScenesMax));
        expect(l.map((s) => s['step']).toSet().length, l.length);
      }
    }
    expect(withVs, greaterThan(0));
  });
}
