import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/decompose.dart';
import 'package:mahjong_calc/engine/efficiency.dart';
import 'package:mahjong_calc/engine/hand.dart';
import 'package:mahjong_calc/engine/meld.dart';
import 'package:mahjong_calc/engine/shanten.dart';
import 'package:mahjong_calc/engine/tile.dart';

List<int> cnt(String s) => toCounts(parseTiles(s).tiles);

// ---------------------------------------------------------------------------
// 독립 판정(새 코드를 쓰지 않는다)

/// 화료인가 — 기존 [decompose] 로 판정. 울기는 닫힌 패와 합쳐 4장을 넘지 않게
/// 손에 1장 이하인 패의 가짜 펑으로 채운다(일반형 묶음 수만 맞추면 된다).
bool agariByDecompose(List<int> counts, int melds) {
  final tiles = <int>[
    for (var t = 0; t < 34; t++)
      for (var i = 0; i < counts[t]; i++) t,
  ];
  final fake = <Meld>[];
  for (var t = 0; t < 34 && fake.length < melds; t++) {
    if (counts[t] <= 1) fake.add(Meld.pon(t));
  }
  final hand = Hand(closedTiles: tiles, melds: fake, winTile: tiles.first);
  return decompose(hand).isNotEmpty;
}

/// 화료인가 — 테스트 안의 단순 재귀(완전 탐색용으로 빠르게).
bool agariFast(List<int> c, int melds) {
  if (melds == 0) {
    var pairs = 0;
    var ok = true;
    for (var t = 0; t < 34; t++) {
      if (c[t] == 2) {
        pairs++;
      } else if (c[t] != 0) {
        ok = false;
      }
    }
    if (ok && pairs == 7) return true;
    var pair = false;
    var kokushi = true;
    for (var t = 0; t < 34; t++) {
      final y = kokushiTiles.contains(t);
      if (!y && c[t] != 0) kokushi = false;
      if (y && c[t] == 0) kokushi = false;
      if (y && c[t] == 2) pair = true;
      if (y && c[t] > 2) kokushi = false;
    }
    if (kokushi && pair) return true;
  }
  for (var p = 0; p < 34; p++) {
    if (c[p] < 2) continue;
    c[p] -= 2;
    final ok = _sets(c);
    c[p] += 2;
    if (ok) return true;
  }
  return false;
}

bool _sets(List<int> c) {
  var i = 0;
  while (i < 34 && c[i] == 0) {
    i++;
  }
  if (i == 34) return true;
  if (c[i] >= 3) {
    c[i] -= 3;
    final ok = _sets(c);
    c[i] += 3;
    if (ok) return true;
  }
  if (i < 27 && i % 9 <= 6 && c[i + 1] > 0 && c[i + 2] > 0) {
    c[i]--;
    c[i + 1]--;
    c[i + 2]--;
    final ok = _sets(c);
    c[i]++;
    c[i + 1]++;
    c[i + 2]++;
    if (ok) return true;
  }
  return false;
}

bool tenpaiFast(List<int> c, int melds) {
  for (var t = 0; t < 34; t++) {
    if (c[t] >= 4) continue;
    c[t]++;
    final ok = agariFast(c, melds);
    c[t]--;
    if (ok) return true;
  }
  return false;
}

(int, int) keyOf(List<int> c) {
  var a = 0;
  var b = 0;
  for (var i = 0; i < 17; i++) {
    a = a * 5 + c[i];
    b = b * 5 + c[17 + i];
  }
  return (a, b);
}

/// 13 − 3m 장 손패의 샹텐을 "한 장 뽑고(손에 4장 미만) 한 장 버리기" 깊이 2 까지 탐색.
/// 0 / 1 / 2, 그보다 크면 3.
int bruteShanten(List<int> h, int melds) {
  var frontier = <List<int>>[
    [...h]
  ];
  final seen = <(int, int)>{keyOf(h)};
  for (var depth = 0; depth <= 2; depth++) {
    for (final x in frontier) {
      if (tenpaiFast(x, melds)) return depth;
    }
    if (depth == 2) break;
    final next = <List<int>>[];
    for (final x in frontier) {
      for (var t = 0; t < 34; t++) {
        if (x[t] >= 4) continue;
        x[t]++;
        for (var d = 0; d < 34; d++) {
          if (d == t || x[d] == 0) continue;
          x[d]--;
          if (seen.add(keyOf(x))) next.add([...x]);
          x[d]++;
        }
        x[t]--;
      }
    }
    frontier = next;
  }
  return 3;
}

// ---------------------------------------------------------------------------
// 손패 만들기(시드 고정)

/// 닫힌 패 14 − 3m 장 화료 손패(각 칸 4장 이하).
List<int> randomAgari(Random r, int melds) {
  while (true) {
    final c = List<int>.filled(34, 0);
    if (melds == 0 && r.nextInt(12) == 0) {
      final kinds = List<int>.generate(34, (i) => i)..shuffle(r);
      for (final t in kinds.take(7)) {
        c[t] = 2;
      }
      return c;
    }
    if (melds == 0 && r.nextInt(25) == 0) {
      for (final t in kokushiTiles) {
        c[t] = 1;
      }
      c[kokushiTiles[r.nextInt(13)]]++;
      return c;
    }
    c[r.nextInt(34)] += 2;
    for (var i = 0; i < 4 - melds; i++) {
      if (r.nextInt(3) > 0) {
        final s = r.nextInt(3) * 9 + r.nextInt(7);
        c[s]++;
        c[s + 1]++;
        c[s + 2]++;
      } else {
        c[r.nextInt(34)] += 3;
      }
    }
    if (c.every((x) => x <= 4)) return c;
  }
}

int randomHeld(Random r, List<int> c) {
  final tiles = <int>[
    for (var t = 0; t < 34; t++)
      for (var i = 0; i < c[t]; i++) t,
  ];
  return tiles[r.nextInt(tiles.length)];
}

/// 손에서 한 장을 빼고 4장 미만인 다른 패 한 장을 넣는다.
void changeOne(Random r, List<int> c) {
  final out = randomHeld(r, c);
  c[out]--;
  while (true) {
    final t = r.nextInt(34);
    if (t == out || c[t] >= 4) continue;
    c[t]++;
    return;
  }
}

/// 화료 근처: 화료 손패(14 − 3m)에서 [changes] 장 바꿈. [drop] 이면 한 장 빼서 13 − 3m 장.
List<int> nearAgari(Random r, int melds, int changes, {required bool drop}) {
  final c = randomAgari(r, melds);
  if (drop) c[randomHeld(r, c)]--;
  for (var i = 0; i < changes; i++) {
    changeOne(r, c);
  }
  return c;
}

/// 136장 패산에서 n 장.
List<int> randomHand(Random r, int n) {
  final wall = <int>[
    for (var t = 0; t < 34; t++) ...[t, t, t, t]
  ]..shuffle(r);
  return toCounts(wall.take(n));
}

void main() {
  group('샹텐 정답이 정해진 손패', () {
    void check(String s, int value, {int melds = 0}) {
      expect(shanten(cnt(s), melds: melds), value, reason: '$s melds=$melds');
    }

    test('설계에서 준 값', () {
      check('123m456p789s11222z', -1);
      check('123m456p789s1122z', 0);
      final k = shantenOf(cnt('19m19p19s1234567z'));
      expect(k.kokushi, 0);
      expect(k.value, 0);
      final c = shantenOf(cnt('1133m2255p4477s1z'));
      expect(c.chiitoitsu, 0);
      final w = shantenOf(cnt('147m258p369s1234z'));
      expect(w.standard, 8);
      expect(w.chiitoitsu, 6);
      expect(w.kokushi, 7);
      expect(w.value, 6);
      check('1112345678999m', 0);
      check('1111m', 1, melds: 3);
    });

    test('손으로 따진 값', () {
      // 묶음 4 + 머리 1, 순자 셋 + 123p 와 4p 단기
      check('123456789m1234p', 0);
      // 울기 1, 묶음 셋 + 1z 단기
      check('123m456p789s1z', 0, melds: 1);
      // 울기 1, 14 − 3 장 화료
      check('123m456p789s11z', -1, melds: 1);
      // 울기 1, 2345m 노베탄(234+5 / 345+2) + 678p + 111z
      check('2345m678p111z', 0, melds: 1);
      // 울기 1, 147 간격이라 묶음·머리 하나가 손패 하나씩만 덮음: 맞는 4장, 모자람 7
      check('147m147p147s1z', 6, melds: 1);
      // 울기 1, 1111m 은 111+1 로만 쓰이고 1m 머리는 5장이 돼 안 됨 → 모자람 3
      check('1111m2222p3z4z', 2, melds: 1);
      // 울기 2, 묶음 둘 + 7s 단기
      check('123m456p7s', 0, melds: 2);
      // 울기 2, 14 − 6 장: 묶음 둘 + 78s 중 하나 버리고 단기
      check('123m456p78s', 0, melds: 2);
      // 울기 2, 1m 4장이라 머리로 못 씀(5장) → 모자람 2
      check('1111m555p', 1, melds: 2);
      // 울기 2, 자패 낱장 7종: 커쯔 둘 2장씩 + 머리 1장 모자람
      check('1234567z', 4, melds: 2);
      // 울기 3, 111+2 단기 / 11+12 변짱
      check('1112m', 0, melds: 3);
      // 울기 3, 123+4 / 234+1 노베탄
      check('1234m', 0, melds: 3);
      // 울기 3, 2칸 간격 1357m 은 순자에 둘까지만 → 모자람 2
      check('1357m', 1, melds: 3);
      // 울기 3, 자패 낱장 넷: 커쯔 2장 + 머리 1장 모자람
      check('1234z', 2, melds: 3);
      // 울기 4, 1m 단기
      check('1m', 0, melds: 4);
      // 울기 4, 머리만 남은 화료
      check('11m', -1, melds: 4);
      // 울기 4, 14 − 12 장 서로 다른 둘 → 하나 버리고 단기
      check('12m', 0, melds: 4);
      // 치또이: 1m 4장은 한 쌍으로만 셈 → 쌍 5, 종류 6 → 6 − 5 + 1
      expect(shantenOf(cnt('1111m2233p4455s6z')).chiitoitsu, 2);
      // 국사: 요구패 12종 + 5m, 쌍 없음 → 13 − 12
      expect(shantenOf(cnt('19m19p19s123456z5m')).kokushi, 1);
    });

    test('울었으면 치또이·국사는 null', () {
      final s = shantenOf(cnt('123m456p789s1z'), melds: 1);
      expect(s.chiitoitsu, isNull);
      expect(s.kokushi, isNull);
      expect(s.value, s.standard);
    });

    test('입력 배열을 바꾸지 않음', () {
      final c = cnt('147m258p369s1234z');
      final copy = [...c];
      shantenOf(c);
      expect(c, copy);
    });
  });

  group('완전 탐색 대조', () {
    test('agariFast 와 decompose 가 같은 답', () {
      final r = Random(11);
      var n = 0;
      for (var m = 0; m <= 4; m++) {
        for (var i = 0; i < 300; i++) {
          final h = nearAgari(r, m, r.nextInt(3), drop: false);
          expect(agariFast(h, m), agariByDecompose(h, m));
          n++;
        }
      }
      expect(n, 1500);
    });

    test('화료 손패에서 0~3장 바꾼 13 − 3m 장, 뽑고 버리기 깊이 2', () {
      final r = Random(2026);
      final byMelds = List<int>.filled(5, 0);
      final byClass = <String, int>{};
      final sw = Stopwatch()..start();
      for (var i = 0; i < 400; i++) {
        final m = i % 5;
        final h = nearAgari(r, m, r.nextInt(4), drop: true);
        final brute = bruteShanten(h, m);
        final s = shanten(h, melds: m);
        expect(min(s, 3), brute, reason: 'h=$h melds=$m');
        byMelds[m]++;
        byClass['m$m/$brute'] = (byClass['m$m/$brute'] ?? 0) + 1;
      }
      // ignore: avoid_print
      print('완전 탐색 대조 ${sw.elapsedMilliseconds}ms, melds 별 $byMelds, '
          'melds/샹텐 ${(byClass.keys.toList()..sort()).map((k) => '$k:${byClass[k]}').join(' ')}');
    }, timeout: const Timeout(Duration(minutes: 10)));

    test('완전 무작위 13 − 3m 장(3 이상 쪽을 보려고), 뽑고 버리기 깊이 2', () {
      final r = Random(77);
      final byMelds = List<int>.filled(5, 0);
      final byClass = <String, int>{};
      final sw = Stopwatch()..start();
      for (var i = 0; i < 114; i++) {
        final m = i < 6 ? 0 : 1 + i % 4; // melds 0 은 탐색이 길어(장당 2초 안팎) 6개만
        final h = randomHand(r, 13 - 3 * m);
        final brute = bruteShanten(h, m);
        expect(min(shanten(h, melds: m), 3), brute, reason: 'h=$h melds=$m');
        byMelds[m]++;
        byClass['m$m/$brute'] = (byClass['m$m/$brute'] ?? 0) + 1;
      }
      // ignore: avoid_print
      print('완전 무작위 대조 ${sw.elapsedMilliseconds}ms, melds 별 $byMelds, '
          'melds/샹텐 ${(byClass.keys.toList()..sort()).map((k) => '$k:${byClass[k]}').join(' ')}');
    }, timeout: const Timeout(Duration(minutes: 10)));
  });

  group('성질 검사', () {
    // 완전 무작위와 화료 근처 손패를 melds 0~4 마다 같은 수씩
    Iterable<(List<int>, int)> hands(Random r, {required bool drop, int per = 200}) sync* {
      for (var m = 0; m <= 4; m++) {
        final n = (drop ? 13 : 14) - 3 * m;
        for (var i = 0; i < per; i++) {
          yield (randomHand(r, n), m);
          yield (nearAgari(r, m, r.nextInt(4), drop: drop), m);
        }
      }
    }

    test('14 − 3m 장: 샹텐 = 버림 후보 샹텐의 최솟값(화료면 최솟값은 0)', () {
      // 13 − 3m 장은 화료 형태까지 늘 1장 이상 모자라 샹텐이 0 아래로 안 간다.
      // 그래서 화료(−1) 손패에서는 최솟값이 0 이다(설계 문구의 예외, 보고함).
      var agari = 0;
      for (final (h, m) in hands(Random(1), drop: false)) {
        var best = 99;
        for (var d = 0; d < 34; d++) {
          if (h[d] == 0) continue;
          h[d]--;
          best = min(best, shanten(h, melds: m));
          h[d]++;
        }
        final s = shanten(h, melds: m);
        if (s == -1) {
          agari++;
          expect(best, 0, reason: 'h=$h melds=$m');
        } else {
          expect(s, best, reason: 'h=$h melds=$m');
        }
      }
      expect(agari, greaterThan(0));
    });

    test('13 − 3m 장: 한 장 뽑으면 샹텐이 그대로이거나 1 줄어듦', () {
      for (final (h, m) in hands(Random(2), drop: true)) {
        final s = shanten(h, melds: m);
        for (var t = 0; t < 34; t++) {
          if (h[t] >= 4) continue;
          h[t]++;
          final s2 = shanten(h, melds: m);
          h[t]--;
          expect(s2, inInclusiveRange(s - 1, s), reason: 'h=$h +$t melds=$m');
        }
      }
    });

    test('14 − 3m 장: 샹텐 −1 ⇔ 화료(decompose)', () {
      var agari = 0;
      var total = 0;
      for (final (h, m) in hands(Random(3), drop: false)) {
        final isAgari = agariByDecompose(h, m);
        expect(shanten(h, melds: m) == -1, isAgari, reason: 'h=$h melds=$m');
        if (isAgari) agari++;
        total++;
      }
      // ignore: avoid_print
      print('화료 판정 대조 $total 손패 중 화료 $agari');
      expect(agari, greaterThan(100));
    });

    test('13 − 3m 장, 샹텐 ≥ 0 이면 유효패가 1종 이상', () {
      for (final (h, m) in hands(Random(4), drop: true)) {
        final s = shanten(h, melds: m);
        expect(s, greaterThanOrEqualTo(0));
        expect(ukeireOf(h, melds: m).tiles, isNotEmpty, reason: 'h=$h melds=$m');
      }
    });
  });

  group('잘못된 입력', () {
    test('ArgumentError', () {
      // 장수
      expect(() => shanten(cnt('123m456p789s11z')), throwsArgumentError);
      expect(() => shanten(cnt('123m456p789s1z'), melds: 2), throwsArgumentError);
      // 5장
      final five = cnt('123m456p789s11z');
      five[0] = 5;
      five[1] = 0;
      expect(() => shanten(five), throwsArgumentError);
      // 음수
      final neg = cnt('123m456p789s1122z');
      neg[33] = -1;
      neg[32] = 1;
      expect(() => shanten(neg), throwsArgumentError);
      // 칸 수
      expect(() => shanten(List<int>.filled(33, 0)), throwsArgumentError);
      // 울기 수
      expect(() => shanten(cnt('1m'), melds: 5), throwsArgumentError);
      expect(() => shanten(cnt('123m456p789s1122z'), melds: -1),
          throwsArgumentError);
    });
  });
}
