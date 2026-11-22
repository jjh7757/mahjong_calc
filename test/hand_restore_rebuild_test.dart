import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/paifu/hand_restore/rebuild.dart';
import 'package:mahjong_calc/paifu/hand_restore/turn_agent.dart';
import 'package:mahjong_calc/paifu/hand_restore/turns.dart';
import 'package:mahjong_calc/paifu/paifu.dart';

import 'hand_restore_fixtures.dart';

List<PaifuTile> _row(String s) => [for (final c in s.split(' ')) PaifuTile.parse(c)];
String _codes(List<PaifuTile>? r) => r == null ? '-' : r.map((t) => t.code).join(' ');

void main() {
  test('복원한 패보도 국 시작 점수 · 공탁 · 네 자리 구역을 잃지 않는다(copyWith 길 · JSON 왕복)', () {
    final orig = withEndHand(assetJson('r19_142013'));
    const boxes = {
      'bottom': [280, 713, 1000, 1000],
      'right': [745, 0, 1000, 713],
      'top': [0, 0, 745, 173],
      'left': [0, 173, 280, 1000],
    };
    final stripped = stripHands(orig).copyWith(
      startScores: [26000, 31000, 19000, 23000],
      kyotaku: 1,
      frames: const PaifuFrames(dir: '/rec', box: [280, 713, 1000, 1000], side: 'bottom', boxes: boxes),
    );
    final turns = planTurns(stripped);
    final truth = truthReadings(orig);
    final rb = rebuildHands(stripped, turns, {
      for (final t in turns)
        if (t.usesApi) t.index: truth[t.index]!,
    });
    expect(rb.restored, greaterThan(0));
    expect(rb.paifu, isNot(same(stripped)));
    expect(rb.paifu.startScores, [26000, 31000, 19000, 23000]);
    expect(rb.paifu.kyotaku, 1);
    expect(rb.paifu.frames!.boxes, boxes);
    final back = Paifu.fromJson(rb.paifu.toJson());
    expect(back.startScores, [26000, 31000, 19000, 23000]);
    expect(back.kyotaku, 1);
    expect(back.frames!.boxes, boxes);
  });

  group('거꾸로 한 차례(backRow)', () {
    final after = _row('1m 2m 3m 4m 5m');
    test('D 를 끼우고 3번을 버림 → 3번 자리에 강의 패', () {
      final b = backRow(after, ['1', '2', 'D', '4', '5'], PaifuTile.parse('9p'));
      expect(_codes(b.before), '1m 2m 9p 4m 5m');
      expect(b.drawn.code, '3m');
      expect(b.tsumogiri, isFalse);
    });
    test('순서 그대로 = 쯔모기리, 옮김(맞바꿈)도 되돌림', () {
      final t = backRow(after, ['1', '2', '3', '4', '5'], PaifuTile.parse('7z'));
      expect((_codes(t.before), t.drawn.code, t.tsumogiri), ('1m 2m 3m 4m 5m', '7z', true));
      final m = backRow(after, ['2', '1', '3', '4', '5'], PaifuTile.parse('7z'));
      expect(_codes(m.before), '2m 1m 3m 4m 5m');
    });
    test('모순 답(번호 겹침 · 장수 다름 · D 둘)은 FormatException', () {
      for (final o in [
        ['1', '1', 'D', '4', '5'],
        ['1', '2', 'D', '4'],
        ['D', '2', 'D', '4', '5'],
        ['1', '2', '3', '4', '9'],
      ]) {
        expect(() => backRow(after, o, PaifuTile.parse('9p')), throwsFormatException, reason: '$o');
      }
    });
  });

  group('예시 판에서 손패를 지우고 정답 end_order 로 복원', () {
    for (final name in ['r18_141259', 'r12_131655', 'r11_130921', 'r15_134151', 'r17_140450', 'r19_142013']) {
      test('$name: 원래 손패 · 뽑은 패 · 시작 손패가 그대로', () {
        final orig = withEndHand(assetJson(name));
        final stripped = stripHands(orig);
        expect(stripped.hasHeroHands, isFalse);
        final turns = planTurns(stripped);
        final truth = truthReadings(orig);
        final rb = rebuildHands(stripped, turns, {
          for (final t in turns)
            if (t.usesApi) t.index: truth[t.index]!,
        });
        expect(rb.failReason, isNull);
        expect(rb.complete, isTrue);
        expect(rb.restored, turns.length);
        final p = rb.paifu;
        expect(p.handSource, 'claude_api');
        expect(heroDiscardHands(p), heroDiscardHands(orig));
        final od = [for (final e in orig.events) if (e.type == PaifuEventType.draw && e.seat == orig.hero) '${e.tile} | ${_codes(e.hand)}'];
        final nd = [for (final e in p.events) if (e.type == PaifuEventType.draw && e.seat == p.hero) '${e.tile} | ${_codes(e.hand)}'];
        expect(nd, od);
        final firstDraw = orig.events.firstWhere((e) => e.type == PaifuEventType.draw && e.seat == orig.hero);
        expect(_codes(p.startHand), _codes(firstDraw.hand));
        // 뽑기 → 버림 장수 검사(Paifu.check 2) · 리치 뒤 쯔모기리(3)가 걸리지 않음.
        expect(p.check().where((x) => x.contains('hero') || x.contains('리치')), isEmpty);
        // 리치 뒤 차례는 API 를 부르지 않는 규칙 차례.
        expect(rb.memo.where((m) => m['src'] == 'rule'), isNotEmpty);
        expect(rb.memo.map((m) => m['src']).toSet().difference({'api', 'rule'}), isEmpty);
        // 다시 읽어도 같은 패보.
        expect(Paifu.fromJson(p.toJson()).toJson(), p.toJson());
      });
    }

    test('뽑기 사건이 남아 있는 꼴(뽑은 패만 지움)도 같은 답 — 사건 수가 그대로', () {
      final orig = withEndHand(assetJson('r18_141259'));
      final stripped = stripHands(orig, dropDraws: false);
      final turns = planTurns(stripped);
      expect(turns.every((t) => t.drawEvent != null), isTrue);
      final truth = truthReadings(orig);
      final rb = rebuildHands(stripped, turns, {for (final t in apiTurns(stripped)) t: truth[t]!});
      expect(rb.paifu.events.length, stripped.events.length);
      expect(heroDiscardHands(rb.paifu), heroDiscardHands(orig));
    });

    test('쯔모기리하며 줄을 바꾼 차례(r15 14순): tsumogiri + 1..n 순열 end_order 를 그대로 씀', () {
      final orig = withEndHand(assetJson('r15_134151'));
      final truth = truthReadings(orig);
      final moved = truth.values.where((r) => r.kind == 'tsumogiri' && r.endOrder!.join(',') != [for (var i = 1; i <= 13; i++) '$i'].join(','));
      expect(moved, isNotEmpty);
    });

    test('k · j 만 맞고 end_order 가 깨진 답은 k · j 로 짓는다', () {
      const r = TurnReading(kind: 'hand', k: 3, j: 5, endOrder: ['1', '2'], orderOk: false);
      expect(orderOf(r, 5), ['1', '2', '4', '5', 'D']);
      expect(orderOf(const TurnReading(kind: 'tsumogiri', endOrder: ['x']), 3), ['1', '2', '3']);
      expect(orderOf(const TurnReading(kind: 'hand', endOrder: ['1']), 3), isNull);
    });
  });

  group('멈춤 · 울기 · 모순', () {
    test('가운데 차례가 답 없음이면 그 차례부터 앞은 손패 없음, 뒤는 채움', () {
      final orig = withEndHand(assetJson('r18_141259'));
      final stripped = stripHands(orig);
      final turns = planTurns(stripped);
      final truth = truthReadings(orig);
      final api = apiTurns(stripped);
      final miss = api[api.length ~/ 2];
      final rb = rebuildHands(stripped, turns, {
        for (final t in api) t: t == miss ? const TurnReading(error: 'answer 없음') : truth[t]!,
      });
      expect(rb.complete, isFalse);
      expect(rb.failedTurn, miss);
      expect(rb.failReason, contains('답 없음'));
      expect(rb.paifu.startHand, isNull);
      final hands = heroDiscardHands(rb.paifu), want = heroDiscardHands(orig);
      for (var i = 0; i < hands.length; i++) {
        expect(hands[i], i < miss ? '-' : want[i], reason: '차례 $i');
      }
      expect(rb.memo[miss]['src'], 'failed');
      expect(rb.memo.take(miss).every((m) => m['src'] == 'skipped'), isTrue);
    });

    test('모순 답(번호 겹침)도 그 차례에서 멈춤', () {
      final orig = withEndHand(assetJson('r12_131655'));
      final stripped = stripHands(orig);
      final turns = planTurns(stripped);
      final truth = truthReadings(orig);
      final api = apiTurns(stripped);
      final bad = api.last;
      final rb = rebuildHands(stripped, turns, {
        for (final t in api) t: t == bad ? const TurnReading(kind: 'hand', endOrder: ['1', '1', 'D']) : truth[t]!,
      });
      expect(rb.failedTurn, bad);
      expect(rb.restored, turns.length - 1 - bad);
    });

    test('L16(퐁 뒤 버림): 울기 차례는 짐작(guess)으로 끼우고 묶음은 맞음, 그 앞도 이어서 복원', () {
      final orig = withEndHand(assetJson('L16_135321'));
      final stripped = stripHands(orig);
      final turns = planTurns(stripped);
      expect(turns.where((t) => t.kind == RestoreTurnKind.afterCall), hasLength(1));
      final truth = truthReadings(orig);
      final rb = rebuildHands(stripped, turns, {for (final t in apiTurns(stripped)) t: truth[t]!});
      expect(rb.complete, isTrue, reason: rb.failReason);
      final p = rb.paifu;
      final call = turns.firstWhere((t) => t.kind == RestoreTurnKind.afterCall);
      expect(p.events.where((e) => e.guess), isNotEmpty);
      expect(rb.memo[call.index]['src'], 'call_guess');
      List<String> sorted(String s) => s.split(' ')..sort();
      final got = heroDiscardHands(p), want = heroDiscardHands(orig);
      for (var i = 0; i < got.length; i++) {
        // 울기 뒤 차례부터는 순서까지, 그 앞은 묶음(패 구성)만 확실.
        if (i >= call.index) {
          expect(got[i], want[i], reason: '차례 $i');
        } else {
          expect(sorted(got[i]), sorted(want[i]), reason: '차례 $i');
        }
      }
      expect(sorted(_codes(p.startHand)), sorted(_codes(orig.events.first.hand)));
    });

    test('끝 손패가 없으면 복원하지 않음', () {
      final j = assetJson('r20_143236');
      final p = stripHands(Paifu.fromJson(j));
      final rb = rebuildHands(p, planTurns(p), const {});
      expect(rb.restored, 0);
      expect(rb.failReason, contains('끝 손패'));
      expect(identical(rb.paifu, p), isTrue);
    });
  });
}
