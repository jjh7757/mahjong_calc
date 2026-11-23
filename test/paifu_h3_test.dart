// 11-14 매장 3반장 열한 판(assets/paifu_h3/, 11-23 헤드 폰 녹화로 복구 — experiments/paifu_frames/han3_install.py 가 옮김).
// 손패 줄은 다시 읽힐 수 있어(울기 앞 순) 구체적인 손패에 기대지 않는다. 버림 · 결과 · 점수는 고정.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/paifu/agent_facts.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';
import 'package:mahjong_calc/paifu/paifu_score.dart';
import 'package:mahjong_calc/ui/paifu/paifu_screen.dart';

/// 시간 순 판 id.
const ids = [
  'h3_143158', 'h3_143539', 'h3_144427', 'h3_144748', 'h3_145625', 'h3_150528', //
  'h3_151410', 'h3_151953', 'h3_152545', 'h3_153010', 'h3_153825',
];

/// 판별 결과(results/han3_1123/_prep/paifu/_check.json 에서 옮김): (종류, 판, 부, 화료자가 받는 총액(본장 포함)).
/// 유국 판은 (draw, 텐파이 자리).
const wins = <String, (String, int, int, int)>{
  'h3_143158': ('ron', 3, 25, 3200), // 동1국 리치 치또이쯔
  'h3_144427': ('tsumo', 5, 30, 8300), // 동2국 1본장 만관
  'h3_144748': ('tsumo', 5, 20, 8000), // 동3국 만관(가깡 있음)
  'h3_145625': ('tsumo', 5, 20, 8000), // 동4국 만관
  'h3_150528': ('tsumo', 5, 30, 8000), // 남1국 만관(울음)
  'h3_151410': ('ron', 2, 30, 2900), // 남2국 백 · 도라(울음)
  'h3_151953': ('ron', 3, 30, 4200), // 남2국 1본장(울음)
  'h3_152545': ('tsumo', 5, 20, 12000), // 남3국 친 만관
  'h3_153010': ('tsumo', 1, 30, 1400), // 남3국 1본장 탕야오(울음)
  'h3_153825': ('ron', 3, 40, 7700), // 남4국
};
const draws = <String, List<int>>{
  'h3_143539': [1], // 동2국 유국, 자리 1(친) 텐파이
};

/// 마지막 판(남4국)이 끝난 뒤 점수(_scores.json 의 end_scores).
const finalScores = [19400, 9900, 40500, 30200];

Map<String, dynamic> raw(String id) =>
    jsonDecode(File('assets/paifu_h3/$id.json').readAsStringSync(encoding: utf8)) as Map<String, dynamic>;

Paifu load(String id) => Paifu.fromJson(raw(id));

/// 맵 안의 null 값 · 빈 목록 칸을 지운다(재귀).
Object? strip(Object? v) => switch (v) {
      Map() => {
          for (final e in v.entries)
            if (e.value != null && !(e.value is List && (e.value as List).isEmpty)) e.key: strip(e.value),
        },
      List() => [for (final x in v) strip(x)],
      _ => v,
    };

/// 한 국이 끝난 뒤 (점수, 남은 공탁 수). 리치 선언마다 1,000점 공탁, 화료자가 공탁 전부를 가져감,
/// 유국은 노텐 벌점 3,000점을 텐파이 자리끼리 나눔(본장 몫은 [Payment] 에 이미 들어 있음).
(List<int>, int) settle(Paifu p, {List<int> tenpai = const []}) {
  final sc = [...p.startScores!];
  var pot = p.kyotaku!;
  for (final e in p.events) {
    if (e.type == PaifuEventType.discard && e.riichi) {
      sc[e.seat] -= 1000;
      pot++;
    }
  }
  final r = p.result!;
  if (r.type == 'draw') {
    if (tenpai.isNotEmpty && tenpai.length < 4) {
      final get = 3000 ~/ tenpai.length, pay = 3000 ~/ (4 - tenpai.length);
      for (var s = 0; s < 4; s++) {
        sc[s] += tenpai.contains(s) ? get : -pay;
      }
    }
    return (sc, pot);
  }
  final pay = scoreOf(p)!.result.payment;
  final w = r.winner!;
  if (r.type == 'ron') {
    sc[r.loser!] -= pay.ron;
  } else {
    for (var s = 0; s < 4; s++) {
      if (s == w) continue;
      sc[s] -= s == p.dealer ? pay.tsumoFromDealer : pay.tsumoFromNonDealer;
    }
  }
  sc[w] += pay.total + pot * 1000;
  return (sc, 0);
}

/// assets/ 아래 파일을 디스크에서 읽는 묶음. 목록(AssetManifest.bin)은 [folders] 의 .json 으로 지어 낸다.
class _DiskBundle extends CachingAssetBundle {
  final List<String> folders;
  _DiskBundle(this.folders);

  @override
  Future<ByteData> load(String key) async {
    if (key == 'AssetManifest.bin') {
      final m = <String, Object>{
        for (final d in folders)
          for (final f in Directory(d).listSync().whereType<File>().where((f) => f.path.endsWith('.json')))
            '$d/${f.uri.pathSegments.last}': [
              {'asset': '$d/${f.uri.pathSegments.last}'},
            ],
        'assets/tiles/1m.png': [
          {'asset': 'assets/tiles/1m.png'},
        ],
      };
      return const StandardMessageCodec().encodeMessage(m)!;
    }
    final bytes = File(key).readAsBytesSync();
    return ByteData.sublistView(bytes);
  }
}

void main() {
  final files = Directory('assets/paifu_h3')
      .listSync()
      .whereType<File>()
      .where((f) => f.path.endsWith('.json'))
      .map((f) => f.uri.pathSegments.last)
      .toList()
    ..sort();

  test('열한 판 · id = 파일 이름 · 제목 "2026-11-14 3반장 "', () {
    expect(files, [for (final id in ids) '$id.json']);
    expect({...wins.keys, ...draws.keys}, ids.toSet());
    for (final id in ids) {
      final p = load(id);
      expect(p.id, id);
      expect(p.title, startsWith('2026-11-14 3반장 '), reason: id);
      expect(p.title, endsWith(p.round + (p.honba > 0 ? ' ${p.honba}본장' : '')), reason: id);
      expect(p.hasHeroHands, isTrue, reason: id);
    }
    expect({for (final id in ids) load(id).title}.length, ids.length, reason: '제목이 겹침');
  });

  for (final id in ids) {
    group(id, () {
      test('JSON 왕복 · check() · states', () {
        final j = raw(id);
        final p = Paifu.fromJson(j);
        // 맨 위 "source"(만든 방법 메모, 옛 예시 r20 에도 있음)는 형식(version 1) 밖이라 읽을 때 버려진다. 나머지는 그대로 돌아온다
        // (toJson 은 유국 결과에 빈 칸 — winner: null · melds: [] — 을 적으므로 null · 빈 목록은 없는 것과 같게 본다).
        expect(strip(jsonDecode(jsonEncode(p.toJson()))), strip({...j}..remove('source')));
        expect(jsonEncode(Paifu.fromJson(p.toJson()).toJson()), jsonEncode(p.toJson()));
        expect(p.check(), isEmpty);
        final st = p.states;
        expect(st, hasLength(p.stepCount));
        expect(st.last.finished, isTrue);
        expect(p.startScores, hasLength(4));
        expect(p.kyotaku, isNotNull);
      });

      test('결과 · 점수', () {
        final p = load(id);
        final r = p.result!;
        final s = scoreOf(p);
        final want = wins[id];
        if (want == null) {
          expect(r.type, 'draw');
          expect(s, isNull);
          return;
        }
        final (type, han, fu, total) = want;
        expect(r.type, type);
        expect(s, isNotNull);
        expect(s!.result.isValid, isTrue, reason: s.result.error);
        expect(s.result.han, han);
        expect(s.result.fu.total, fu);
        expect(s.result.payment.total, total);
        // 판 중 손패가 적힌 hero 가 화료자면: 마지막 사건 뒤 손패 = 결과의 끝 손패.
        if (r.winner == p.hero) expect(p.states[p.events.length].heroHand, r.hand);
      });

      test('패보 리뷰(엔진 끔 · 켬)와 사실표', () {
        final p = load(id);
        final heroDiscards = p.events.where((e) => e.seat == p.hero && e.type == PaifuEventType.discard).length;
        for (final engine in [false, true]) {
          final r = reviewPaifu(p, withEngine: engine);
          expect(r.turns, hasLength(heroDiscards), reason: 'engine $engine');
          final facts = agentFacts(p, r);
          expect(jsonDecode(jsonEncode(facts)), isA<Map<String, dynamic>>());
        }
      });
    });
  }

  test('국 시작 점수 · 공탁 · 본장 · 친이 판 순서대로 이어짐', () {
    final ps = [for (final id in ids) load(id)];
    expect(ps.first.startScores, [25000, 25000, 25000, 25000]);
    expect(ps.first.kyotaku, 0);
    expect(ps.first.round, '동1국');
    expect(ps.first.honba, 0);
    for (var i = 0; i < ps.length; i++) {
      final p = ps[i];
      final (end, pot) = settle(p, tenpai: draws[p.id] ?? const []);
      expect(end.reduce((a, b) => a + b) + pot * 1000, 100000, reason: '${p.id}: 점수 + 공탁 합');
      if (i == ps.length - 1) {
        expect(end, finalScores);
        expect(pot, 0);
        break;
      }
      final next = ps[i + 1];
      expect(next.startScores, end, reason: '${p.id} → ${next.id}');
      expect(next.kyotaku, pot, reason: '${p.id} → ${next.id}');
      // 친이 화료했거나 유국(친 텐파이)이면 연장 — 같은 친, 본장 +1. 아니면 친이 넘어가고 본장 0.
      final r = p.result!;
      final renchan = r.type == 'draw' ? (draws[p.id] ?? const []).contains(p.dealer) : r.winner == p.dealer;
      expect(next.dealer, renchan ? p.dealer : (p.dealer + 1) % 4, reason: next.id);
      expect(next.honba, renchan || r.type == 'draw' ? p.honba + 1 : 0, reason: next.id);
    }
  });

  group('예시 목록(PaifuAssetListScreen.load)', () {
    void checkList(List<Paifu> list) {
      final titles = [for (final p in list) p.title];
      expect(list, hasLength(21), reason: titles.join('\n'));
      expect(list.where((p) => p.title.startsWith('2026-11-14 2반장 ')), hasLength(10));
      expect([for (final p in list.skip(10)) p.id], ids);
      expect(list.any((p) => p.id == 'r20_143236'), isFalse);
      expect(titles.where((t) => t == '2026-11-14 3반장 동1국'), hasLength(1));
      expect(list.every((p) => p.hasHeroHands), isTrue);
    }

    test('디스크 묶음: 2반장 10 + 3반장 11, 버림만 r20 은 같은 제목 판에 가려짐', () async {
      checkList(await PaifuAssetListScreen.load(bundle: _DiskBundle(['assets/paifu', 'assets/paifu_h3'])));
      // 새 폴더가 없으면 r20 은 그대로 나온다(가리는 판이 없음).
      final old = await PaifuAssetListScreen.load(bundle: _DiskBundle(['assets/paifu']));
      expect(old, hasLength(11));
      expect(old.any((p) => p.id == 'r20_143236'), isTrue);
    });

    testWidgets('앱 묶음(pubspec assets)에서도 같다', (tester) async {
      final list = (await tester.runAsync(() => PaifuAssetListScreen.load()))!;
      checkList(list);
    });
  });
}
