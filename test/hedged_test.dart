import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/table/table_reader.dart' show hedged;

/// 강 끝 판독 헤지([hedged]): 늦으면 한 번 더, 먼저 실패하면 바로 한 번 더, 먼저 온 성공을 쓴다.
void main() {
  test('시간 안에 답하면 두 번째는 안 보낸다', () async {
    var second = 0;
    final v = await hedged(() async => 'a', () async {
      second++;
      return 'b';
    }, const Duration(milliseconds: 50));
    await Future<void>.delayed(const Duration(milliseconds: 80));
    expect(v, 'a');
    expect(second, 0);
  });

  test('늦으면 두 번째를 보내고 먼저 온 답을 쓴다, 진 쪽 답·오류는 버린다', () async {
    var hedges = 0;
    final slow = Completer<String>();
    final v = await hedged(() => slow.future, () async => 'b', const Duration(milliseconds: 20), onHedge: () => hedges++);
    expect(v, 'b');
    expect(hedges, 1);
    slow.completeError(StateError('late')); // 처리되지 않은 오류가 되면 테스트가 실패한다
    await Future<void>.delayed(const Duration(milliseconds: 10));
  });

  test('먼저 실패하면 기다리지 않고 바로 한 번 더, 그것도 실패하면 그 오류', () async {
    final sw = Stopwatch()..start();
    final v = await hedged(() async => throw StateError('503'), () async => 'b', const Duration(seconds: 5));
    expect(v, 'b');
    expect(sw.elapsedMilliseconds, lessThan(1000));
    await expectLater(
      hedged(() async => throw StateError('one'), () async => throw StateError('two'), const Duration(seconds: 5)),
      throwsA(isA<StateError>().having((e) => e.message, 'message', 'two')),
    );
  });

  test('after 가 null 이면 헤지 없음', () async {
    var second = 0;
    expect(await hedged(() async => 'a', () async => '${second++}', null), 'a');
    expect(second, 0);
  });
}
