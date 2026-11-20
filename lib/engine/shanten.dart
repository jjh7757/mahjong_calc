import 'tile.dart';

/// 샹텐수. 화료 −1, 텐파이 0.
///
/// 정의: (화료 형태까지 모자란 최소 장수) − 1.
/// 화료 형태는 닫힌 패 `14 − 3 × 울기 수` 장짜리 묶음으로, 패 종류마다 4장 이하다.
/// 4장 제한은 닫힌 손패 안에서만 본다(울기·강·도라 표시패는 보지 않는다).
/// 13장 쪽이든 14장 쪽이든 같은 식을 쓴다.
class Shanten {
  /// 일반형(묶음 4 − 울기 수 + 머리).
  final int standard;

  /// 치또이. 울었으면 null.
  final int? chiitoitsu;

  /// 국사. 울었으면 null.
  final int? kokushi;

  const Shanten(this.standard, {this.chiitoitsu, this.kokushi});

  /// 셋 중 최소.
  int get value {
    var v = standard;
    final c = chiitoitsu;
    final k = kokushi;
    if (c != null && c < v) v = c;
    if (k != null && k < v) v = k;
    return v;
  }

  @override
  String toString() =>
      'Shanten($value: 일반 $standard, 치또이 $chiitoitsu, 국사 $kokushi)';
}

/// [counts] 는 34칸 닫힌 손패 개수, 합이 `13 − 3 × melds` 또는 `14 − 3 × melds`.
Shanten shantenOf(List<int> counts, {int melds = 0}) {
  _check(counts, melds);
  final standard = _standard(counts, melds);
  if (melds > 0) return Shanten(standard);
  return Shanten(standard,
      chiitoitsu: _chiitoitsu(counts), kokushi: _kokushi(counts));
}

/// [shantenOf] 의 최소값.
int shanten(List<int> counts, {int melds = 0}) =>
    shantenOf(counts, melds: melds).value;

void _check(List<int> counts, int melds) {
  if (melds < 0 || melds > 4) {
    throw ArgumentError('울기 수는 0~4: $melds');
  }
  if (counts.length != Tiles.count) {
    throw ArgumentError('개수 배열은 34칸이어야 합니다 (현재 ${counts.length})');
  }
  var sum = 0;
  for (var t = 0; t < Tiles.count; t++) {
    final c = counts[t];
    if (c < 0 || c > 4) {
      throw ArgumentError('${Tiles.name(t)} 개수가 0~4 를 벗어남: $c');
    }
    sum += c;
  }
  final full = 14 - 3 * melds;
  if (sum != full && sum != full - 1) {
    throw ArgumentError('닫힌 패는 ${full - 1} 또는 $full 장이어야 합니다 (현재 $sum 장)');
  }
}

const int _inf = 99;

/// 치또이: 6 − (2장 이상인 종류) + max(0, 7 − 가진 종류).
int _chiitoitsu(List<int> counts) {
  var pairs = 0;
  var kinds = 0;
  for (final c in counts) {
    if (c > 0) kinds++;
    if (c >= 2) pairs++;
  }
  return 6 - pairs + (kinds < 7 ? 7 - kinds : 0);
}

const _yaochu = [0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33];

/// 국사: 13 − (가진 요구패 종류) − (요구패 중 2장 이상이 있으면 1).
int _kokushi(List<int> counts) {
  var kinds = 0;
  var pair = false;
  for (final t in _yaochu) {
    if (counts[t] > 0) kinds++;
    if (counts[t] >= 2) pair = true;
  }
  return 13 - kinds - (pair ? 1 : 0);
}

/// 일반형: 수트별 need 를 합쳐 묶음 4 − melds, 머리 1 의 최소 모자란 장수 − 1.
int _standard(List<int> counts, int melds) {
  var acc = _suitNeed(counts, 0, false);
  for (var s = 1; s < 4; s++) {
    final next = _suitNeed(counts, s * 9, s == 3);
    final merged = List<int>.filled(10, _inf);
    for (var k1 = 0; k1 <= 4; k1++) {
      for (var p1 = 0; p1 <= 1; p1++) {
        final a = acc[k1 * 2 + p1];
        if (a >= _inf) continue;
        for (var k2 = 0; k1 + k2 <= 4; k2++) {
          for (var p2 = 0; p1 + p2 <= 1; p2++) {
            final b = next[k2 * 2 + p2];
            if (b >= _inf) continue;
            final i = (k1 + k2) * 2 + p1 + p2;
            if (a + b < merged[i]) merged[i] = a + b;
          }
        }
      }
    }
    acc = merged;
  }
  return acc[(4 - melds) * 2 + 1] - 1;
}

/// 수트 개수 배열(5진수 키) → need 10칸. 수패·자패 따로.
final Map<int, List<int>> _numberCache = {};
final Map<int, List<int>> _honorCache = {};

/// 수트 하나의 need[k * 2 + p]: 그 수트 안에서 묶음 k개 + 머리 p개를 만들 때
/// 모자란 최소 장수(목표 각 칸 4장 이하). 만들 수 없으면 [_inf].
List<int> _suitNeed(List<int> counts, int start, bool honor) {
  final len = honor ? 7 : 9;
  var key = 0;
  for (var i = 0; i < len; i++) {
    key = key * 5 + counts[start + i];
  }
  final cache = honor ? _honorCache : _numberCache;
  final hit = cache[key];
  if (hit != null) return hit;

  final h = List<int>.generate(len, (i) => counts[start + i]);
  final result = _suitDp(h, honor);
  cache[key] = result;
  return result;
}

/// 자리 순서 DP. 상태 = (i−2 에서 시작한 순자 수 x, i−1 에서 시작한 순자 수 y, 묶음 k, 머리 p).
/// 자리 i 에서 순자 z개·커쯔 t개(0/1)·머리 q개(0/1)를 고르고, 그 칸 목표
/// x + y + z + 3t + 2q 가 4 이하일 때만 쓴다. 비용은 그 칸 max(0, 목표 − 가진 수).
List<int> _suitDp(List<int> h, bool honor) {
  final len = h.length;
  int idx(int x, int y, int k, int p) => ((x * 5 + y) * 5 + k) * 2 + p;
  var dp = List<int>.filled(250, _inf);
  dp[idx(0, 0, 0, 0)] = 0;
  for (var i = 0; i < len; i++) {
    final ndp = List<int>.filled(250, _inf);
    final canStart = !honor && i <= len - 3;
    for (var x = 0; x <= 4; x++) {
      for (var y = 0; x + y <= 4; y++) {
        for (var k = 0; k <= 4; k++) {
          for (var p = 0; p <= 1; p++) {
            final cur = dp[idx(x, y, k, p)];
            if (cur >= _inf) continue;
            final maxZ = canStart ? 4 - x - y : 0;
            for (var z = 0; z <= maxZ; z++) {
              for (var t = 0; t <= 1; t++) {
                for (var q = 0; q + p <= 1; q++) {
                  final target = x + y + z + 3 * t + 2 * q;
                  if (target > 4) continue;
                  final nk = k + z + t;
                  if (nk > 4) continue;
                  final miss = target > h[i] ? target - h[i] : 0;
                  final j = idx(y, z, nk, p + q);
                  if (cur + miss < ndp[j]) ndp[j] = cur + miss;
                }
              }
            }
          }
        }
      }
    }
    dp = ndp;
  }
  return List<int>.unmodifiable([
    for (var k = 0; k <= 4; k++)
      for (var p = 0; p <= 1; p++) dp[idx(0, 0, k, p)],
  ]);
}
