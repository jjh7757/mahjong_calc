// 일발의 "리치 뒤 울기·버림" 을 패 인식(겹쳐 보기)으로 — 숫자는 11-14·11-07 매장 프레임 재생(`experiments/ondevice/overlay_ippatsu_replay.py`)에서 나온 값.
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/table/call_watch.dart';
import 'package:mahjong_calc/table/table_layout.dart';

TableCount count(int river, {Map<Side, int> own = const {}, Map<Side, int> melds = const {}}) => TableCount(
      river: river,
      ownRiver: {for (final s in Side.values) s: own[s] ?? 0},
      melds: {for (final s in Side.values) s: melds[s] ?? 0},
    );

void main() {
  group('TableCount.of', () {
    test('강 주인은 가운데 기기에서 본 사분면, 울기는 역할 모델의 자리', () {
      final c = TableCount.of(
        [
          (cx: 0.50, cy: 0.70, role: 'river', side: Side.left), // 기기 아래 → 아래 자리 강(역할 모델의 자리 답은 안 씀)
          (cx: 0.52, cy: 0.72, role: 'river', side: null),
          (cx: 0.70, cy: 0.50, role: 'river', side: null), // 오른쪽
          (cx: 0.50, cy: 0.30, role: 'river', side: null), // 위
          (cx: 0.05, cy: 0.05, role: 'meld', side: Side.top), // 테두리 모서리 위 울기
          (cx: 0.07, cy: 0.05, role: 'meld', side: Side.top),
          (cx: 0.09, cy: 0.05, role: 'meld', side: Side.top),
          (cx: 0.60, cy: 0.90, role: 'hand', side: Side.bottom),
          (cx: 0.20, cy: 0.20, role: 'wall', side: null),
        ],
        centerX: 0.5,
        centerY: 0.5,
      );
      expect(c.river, 4);
      expect(c.ownRiver, {Side.bottom: 2, Side.right: 1, Side.top: 1, Side.left: 0});
      expect(c.melds[Side.top], 3);
      expect(c.melds[Side.bottom], 0);
    });

    test('4:3 사진이면 가로 거리를 그만큼 늘려 사분면을 가른다', () {
      // 중심에서 가로 0.10(= 세로 0.133 분량)·세로 0.12 떨어진 패: 1:1 이면 아래, 4:3 이면 오른쪽.
      const t = (cx: 0.60, cy: 0.62, role: 'river', side: null);
      expect(TableCount.of([t], centerX: 0.5, centerY: 0.5).ownRiver[Side.bottom], 1);
      expect(TableCount.of([t], centerX: 0.5, centerY: 0.5, aspect: 4 / 3).ownRiver[Side.right], 1);
    });
  });

  group('CallWatch.verdict', () {
    test('기준이 없으면 null', () {
      expect(CallWatch().verdict(Side.bottom, count(10)), isNull);
    });

    test('11-14 동4국 1본장: 리치 뒤 버림 2장·울기 없음 → yes(떼어 둔 쯔모 패 1장은 울기로 안 침)', () {
      final w = CallWatch()
        ..addBaseline(Side.bottom, count(8, own: {Side.bottom: 2}))
        ..addBaseline(Side.bottom, count(9, own: {Side.bottom: 2, Side.right: 3}));
      final v = w.verdict(Side.bottom, count(11, own: {Side.bottom: 2, Side.right: 3}, melds: {Side.bottom: 1, Side.top: 1}))!;
      expect(v.answer, CallAnswer.yes);
      expect(v.riverDiff, 2);
      expect(v.ownDiff, 0);
      expect(v.calls, isEmpty);
      expect(v.selfGrew, isFalse);
    });

    test('11-07 15:40 판: 리치한 사람이 또 버림(자기 강 +2, 합 +9) → no', () {
      final w = CallWatch()..addBaseline(Side.top, count(36, own: {Side.top: 8}, melds: {Side.left: 3}));
      final v = w.verdict(Side.top, count(45, own: {Side.top: 10}, melds: {Side.left: 3, Side.top: 2}))!;
      expect(v.answer, CallAnswer.no);
      expect(v.ownDiff, 2);
      expect(v.calls, isEmpty); // 이미 있던 왼쪽 울기는 그대로
      expect(v.selfGrew, isTrue); // 자기 자리 2장 — merge 가 화료 사진의 안깡 유무로 가린다
    });

    test('버림이 한 바퀴(3장)를 넘으면 no, 3장까지는 yes', () {
      final w = CallWatch()..addBaseline(Side.left, count(20));
      expect(w.verdict(Side.left, count(23))!.answer, CallAnswer.yes);
      expect(w.verdict(Side.left, count(24))!.answer, CallAnswer.no);
    });

    test('다른 자리에 울기 3장이 새로 생기거나(테두리 위 퐁), 있던 울기에 더해지면(가깡) no', () {
      final w = CallWatch()..addBaseline(Side.bottom, count(20, melds: {Side.right: 3}));
      expect(w.verdict(Side.bottom, count(21, melds: {Side.right: 3, Side.top: 3}))!.calls, {Side.top});
      expect(w.verdict(Side.bottom, count(21, melds: {Side.right: 3, Side.top: 3}))!.answer, CallAnswer.no);
      expect(w.verdict(Side.bottom, count(21, melds: {Side.right: 4}))!.calls, {Side.right});
      // 낱장 1~2장(헛 검출)은 울기가 아니다.
      expect(w.verdict(Side.bottom, count(21, melds: {Side.right: 3, Side.top: 2}))!.answer, CallAnswer.yes);
    });

    test('강 상자가 기준보다 줄었으면(낡은 기준·가림) unknown', () {
      final w = CallWatch()..addBaseline(Side.left, count(55));
      expect(w.verdict(Side.left, count(30))!.answer, CallAnswer.unknown);
    });

    test('기준 읽기는 항목마다 최댓값으로 합친다(손이 가린 프레임은 수가 준다)', () {
      final w = CallWatch()
        ..addBaseline(Side.left, count(24, own: {Side.left: 6}, melds: {Side.top: 3}))
        ..addBaseline(Side.left, count(23, own: {Side.left: 5}));
      final b = w.baseline(Side.left)!;
      expect(b.river, 24);
      expect(b.ownRiver[Side.left], 6);
      expect(b.melds[Side.top], 3);
    });
  });

  group('기준 읽기 시점', () {
    final t0 = DateTime(2026, 11, 16, 12);
    DateTime at(int s) => t0.add(Duration(seconds: s));

    test('첫 읽기는 12초 안, 둘째는 6초 안에서 2장까지', () {
      final w = CallWatch();
      expect(w.wants(Side.top, t0, at(0)), isTrue);
      expect(w.wants(Side.top, t0, at(12)), isTrue);
      expect(w.wants(Side.top, t0, at(13)), isFalse); // 너무 늦음 — 기준 없이 픽셀 판정
      w.addBaseline(Side.top, count(10));
      expect(w.wants(Side.top, t0, at(3)), isTrue);
      expect(w.wants(Side.top, t0, at(7)), isFalse);
      w.addBaseline(Side.top, count(10));
      expect(w.wants(Side.top, t0, at(4)), isFalse);
    });

    test('prune 은 남길 자리 밖의 기준을 버린다(새 판)', () {
      final w = CallWatch()
        ..addBaseline(Side.top, count(10))
        ..addBaseline(Side.left, count(10));
      w.prune({Side.left});
      expect(w.baseline(Side.top), isNull);
      expect(w.baseline(Side.left), isNotNull);
      expect(w.wants(Side.top, t0, at(1)), isTrue); // 읽은 수도 지워짐
      w.prune(const {});
      expect(w.isEmpty, isTrue);
    });
  });
}
