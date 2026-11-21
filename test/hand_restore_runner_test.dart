import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/paifu/hand_restore/frames.dart';
import 'package:mahjong_calc/paifu/hand_restore/restorer.dart';
import 'package:mahjong_calc/paifu/hand_restore/turn_agent.dart';
import 'package:mahjong_calc/paifu/hand_restore/turns.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'hand_restore_fixtures.dart';

/// 정답 읽기를 내는 가짜 읽기. 어느 차례인지는 창의 첫 프레임 시각으로 찾는다.
class _FakeReader implements TurnReader {
  final Map<int, TurnReading> byTurn;
  final List<RestoreTurn> turns;
  final double usdEach;
  final Set<int> fail;
  final calls = <int>[];
  final maxUsds = <double?>[];
  _FakeReader(this.byTurn, this.turns, {this.usdEach = 0.5, this.fail = const {}});

  @override
  Future<TurnReading> read(TurnFrames frames, int n, {double? maxUsd, bool Function()? cancelled}) async {
    final t = turns.lastWhere((t) => t.usesApi && t.startMs! <= frames.ms.first);
    calls.add(t.index);
    maxUsds.add(maxUsd);
    expect(n, t.n);
    if (fail.contains(t.index)) return TurnReading(usd: usdEach, steps: 60, error: 'answer 없음');
    final r = byTurn[t.index]!;
    return TurnReading(kind: r.kind, endOrder: r.endOrder, orderOk: r.orderOk, usd: usdEach, steps: 4, unsure: t.index.isEven);
  }
}

MemoryFrameSource _source(Paifu p) {
  final jpg = Uint8List.fromList(img.encodeJpg(img.Image(width: 40, height: 20), quality: 50));
  final ats = [for (final e in p.events) ?e.at];
  final lo = ats.reduce((a, b) => a < b ? a : b) - 25000, hi = ats.reduce((a, b) => a > b ? a : b) + 10000;
  return MemoryFrameSource({for (var t = lo; t <= hi; t += 500) t: jpg});
}

void main() {
  final orig = withEndHand(assetJson('r18_141259'));
  final stripped = stripHands(orig);
  final turns = planTurns(stripped);
  final truth = truthReadings(orig);
  final api = apiTurns(stripped);

  HandRestorer restorer(_FakeReader r, {double limit = 10}) =>
      HandRestorer(reader: r, sourceOf: (_) => _source(stripped), runner: directRunner, gameLimitUsd: limit);

  test('뒤 차례부터 읽어 끝까지 복원 · 진행 알림 · 확신 낮은 차례', () async {
    final r = _FakeReader(truth, turns);
    final seen = <RestoreProgress>[];
    final o = await restorer(r).run(stripped, onProgress: seen.add);
    expect(r.calls, api.reversed.toList());
    expect(o.stopReason, isNull);
    expect(o.rebuild.complete, isTrue);
    expect(heroDiscardHands(o.paifu!), heroDiscardHands(orig));
    expect(o.usd, closeTo(0.5 * api.length, 1e-9));
    expect(o.apiTurns, api.length);
    expect(o.ruleTurns, turns.where((t) => t.kind == RestoreTurnKind.rule).length);
    expect(o.unsureTurns, [for (final t in api) if (t.isEven) t + 1]);
    expect(seen.last.done, api.length);
    expect(seen.last.total, api.length);
    expect(o.paifu!.restore!.where((m) => m['src'] == 'api'), hasLength(api.length));
  });

  test('판 한도: 남은 돈으로 차례 한도를 줄이고, 다 쓰면 그 앞은 읽지 않음 — 뒤쪽 차례는 채움', () async {
    final r = _FakeReader(truth, turns, usdEach: 4);
    final o = await restorer(r, limit: 10).run(stripped);
    expect(r.calls, hasLength(3));
    expect(r.maxUsds, [5, 5, 2]);
    expect(o.stopReason, contains('판 한도'));
    expect(o.rebuild.complete, isFalse);
    expect(o.paifu, isNotNull);
    expect(o.rebuild.failedTurn, api.reversed.elementAt(3));
  });

  test('취소 · 답 없는 차례에서 멈춤(그 앞은 부르지 않음)', () async {
    var n = 0;
    final r = _FakeReader(truth, turns);
    final o = await restorer(r).run(stripped, cancelled: () => n++ >= 2);
    expect(o.cancelled, isTrue);
    expect(r.calls, hasLength(2));

    final bad = api.reversed.elementAt(1);
    final r2 = _FakeReader(truth, turns, fail: {bad});
    final o2 = await restorer(r2).run(stripped);
    expect(r2.calls, api.reversed.take(2).toList());
    expect(o2.stopReason, contains('답 없음'));
    expect(o2.rebuild.failedTurn, bad);
  });

  test('녹화 정보 · 프레임이 없으면 읽지 않음', () async {
    final r = _FakeReader(truth, turns);
    final noFrames = Paifu.fromJson({...stripped.toJson()}..remove('frames'));
    final o = await HandRestorer(reader: r, sourceOf: (_) => MemoryFrameSource({}), runner: directRunner).run(noFrames);
    expect(o.stopReason, contains('녹화 정보'));
    final o2 = await HandRestorer(reader: r, sourceOf: (_) => MemoryFrameSource({}), runner: directRunner).run(stripped);
    expect(o2.stopReason, contains('프레임이 없음'));
    expect(r.calls, isEmpty);
    // API 없이도 끝의 리치 뒤(규칙) 차례만은 채운다 — 돈이 안 든다.
    final rule = turns.reversed.takeWhile((t) => t.kind == RestoreTurnKind.rule).length;
    expect(rule, greaterThan(0));
    expect(o2.rebuild.restored, rule);
    expect(o2.rebuild.failReason, '읽지 않은 차례');
    expect(o2.paifu, isNull); // 그것만으로는 저장하지 않음
  });

  test('저장: 같은 id 로 바꿔 끼우고 원본은 따로 — 되돌리면 원본', () async {
    SharedPreferences.setMockInitialValues({});
    await PaifuStore.put('g1', stripped);
    final o = await restorer(_FakeReader(truth, turns)).run(stripped);
    await RestoreStore.save('g1', stripped, o.paifu!);
    var list = await PaifuStore.list('g1');
    expect(list.single.handSource, 'claude_api');
    expect(list.single.hasHeroHands, isTrue);
    expect(await RestoreStore.hasOriginal('g1', stripped.id), isTrue);
    // 두 번 복원해도 원본은 처음 것.
    await RestoreStore.save('g1', o.paifu!, o.paifu!);
    final back = await RestoreStore.revert('g1', stripped.id);
    expect(back!.hasHeroHands, isFalse);
    list = await PaifuStore.list('g1');
    expect(list.single.hasHeroHands, isFalse);
    expect(list.single.frames, isNotNull);
    expect(await RestoreStore.hasOriginal('g1', stripped.id), isFalse);
    expect(await RestoreStore.revert('g1', stripped.id), isNull);
  });

  test('API 키 저장소', () async {
    SharedPreferences.setMockInitialValues({});
    expect(await ClaudeKeyStore.load(), isNull);
    await ClaudeKeyStore.save('  sk-test  ');
    expect(await ClaudeKeyStore.load(), 'sk-test');
    expect((await SharedPreferences.getInstance()).getString('claude.apiKey'), 'sk-test');
    await ClaudeKeyStore.clear();
    expect(await ClaudeKeyStore.load(), isNull);
  });
}
