/// 판 중 패 인식(겹쳐 보기) 장면을 차례로 받아 네 자리의 버림 순서·패·울려 나간 패를 적는다. 순수 Dart, I/O 없음.
///
/// 오프라인 시험 `experiments/paifu_frames/paifu_frames.py` 의 강 칸(슬롯) 방식 v2(`slot_round` + `--dealer-side --flip`,
/// metrics 표 12: 강 98/100 · 울어 감 6/6)를 장면이 올 때마다 한 걸음씩 도는 꼴로 옮긴 것이다. 규칙:
/// - 자리: 가운데 기기 중심에서 본 바람개비 띠([assignSide]). 좌표는 그 자리 기준 (u = 강이 늘어나는 쪽, v = 바깥쪽).
/// - 칸 잇기: 자리마다 칸의 마지막 위치를 기억하고 장면마다 위치로 잇는다. 강을 통째로 밀어도 따라가게 평균 이동량을 먼저 뺀다.
/// - 새 패: 어느 칸에도 안 붙는 패 → 새 칸. 혼자 옮겨진 패(안 보이는 칸과 같은 패)는 그 칸을 옮긴다.
/// - 울려 나감: 마지막 칸만 안 보이고 나머지는 다 보이는 장면이 [DiscardRecorderConfig.streakNeed] 번, 또는 마지막 칸이 확실한
///   다른 패로 두 장면 이어 읽힘(가져간 자리에 다음 패가 놓임).
/// - 시작: 선(親) 자리 강에 패가 두 장면 이어 보이기 전의 장면은 버린다(패 나누는 중의 헛 패).
/// - 국의 경계: 네 강이 모두 빈 장면이 두 번 이어지면 칸을 비우고 새로 적는다(기록기 하나를 대국 내내 쓴다).
/// - 한 장면만 보이고 사라진 패는 그 무렵 울기 상자가 늘었을 때만 울려 나간 버림으로 적는다(아니면 헛것).
/// - 울려 나간 패는 그 무렵 울기 상자가 늘어난 자리가 가져간 것이고, 늘어난 상자로 묶음(퐁 · 치 · 깡)을 적는다.
/// - 패 종류: 이어진 장면의 확신도 합 투표. 자리 안 순서 = 강 위치(줄·칸), 자리 사이 순서 = 처음 보인 장면, 같은 장면이면 차례.
library;

import 'dart:math' as math;

import '../engine/tile.dart';
import '../table/table_layout.dart' show Side;
import 'paifu.dart';

/// 한 장면에서 본 강의 패 한 장. [dx]·[dy] 는 가운데 기기 중심에서 상자 중심까지(사진 방향 그대로, 아래·오른쪽이 +),
/// [w]·[h] 는 상자 크기. 넷 다 같은 길이 단위여야 한다(가로·세로 비율을 맞춘 값).
class RiverSighting {
  final double dx, dy, w, h;
  final String tile;
  final double conf;
  const RiverSighting({required this.dx, required this.dy, required this.w, required this.h, required this.tile, required this.conf});
}

class DiscardRecorderConfig {
  /// 같은 칸으로 잇는 거리(기기 반 크기의 배수). 패 폭은 기기 반 크기의 약 0.3.
  final double tol;

  /// 줄을 나누는 바깥쪽 틈(기기 반 크기의 배수).
  final double rowGap;

  /// 이동량을 고를 때, 칸에 붙은 패가 그 칸에서 읽힌 적 있는 종류면 더하는 점수. 오프라인 시험(파이썬)은 0.5 였는데, 손이 강을
  /// 가려 몇 장만 보이는 장면에서 "한 칸씩 밀린" 맞춤이 새로 놓인 패 한 장 덕에 이겨 칸이 섞였다(11-14 r11 왼쪽 13:11:45:
  /// 제자리 3장 4.5점 < 밀린 4장 5.0점). 종류가 맞는 쪽이 장수보다 세도록 2 로.
  final double kindBonus;

  /// 마지막 칸만 안 보이는 장면이 이만큼 이어지면 울려 나감.
  final int streakNeed;

  /// 마지막 칸이 다른 패로 바뀌면 울려 나감으로 볼지, 그때 두 패 모두 넘어야 하는 확신도.
  final bool flip;
  final double flipConf;

  /// 네 강에 패가 하나도 없는 장면이 이만큼 이어지면 국이 바뀐 것으로 보고 칸을 비운다.
  final int emptyNeed;

  /// 한 장면에서만 보이고 사라진 패를 "울려 나감" 으로 인정하려면, 그 장면 앞 [meldBefore] 동안보다 뒤 [meldAfter] 동안에
  /// 어느 자리의 울기 상자가 이만큼 늘어야 한다. 손에 든 패가 강 근처에서 한 번 잡힌 것을 버림 → 울기로 적던 것을 거른다
  /// (11-14 r18 위 자리 1삭, metrics 표 12-36). 울기 상자 수를 안 받은 기록기는 예전처럼 다 인정한다.
  final int meldGrowMin;
  final Duration meldBefore;
  final Duration meldAfter;

  /// 눕힌 패(리치 선언패)로 치는 상자 가로/세로 비(그 자리에서 볼 때). 세운 패는 약 0.76, 눕힌 패는 약 1.3 이라 그 가운데.
  final double sidewaysRatio;

  const DiscardRecorderConfig({
    this.tol = 0.2,
    this.rowGap = 0.42 * 0.55,
    this.kindBonus = 2,
    this.streakNeed = 2,
    this.emptyNeed = 2,
    this.meldGrowMin = 2,
    this.meldBefore = const Duration(seconds: 24),
    this.meldAfter = const Duration(seconds: 36),
    this.flip = true,
    this.flipConf = 0.9,
    this.sidewaysRatio = 1.0,
  });
}

/// 적힌 버림 한 장.
class RecordedDiscard {
  final Side side;

  /// 그 자리의 몇 번째 버림인가(0부터).
  final int index;
  final String tile;

  /// 투표에서 [tile] 이 차지한 몫(0~1), 이어 본 장면 수.
  final double share;
  final int seen;
  final int firstFrame;
  final DateTime firstAt;

  /// 울려 나갔으면 그 장면.
  final int? takenFrame;
  final DateTime? takenAt;

  /// 눕혀 놓였다(리치 선언패).
  final bool sideways;

  /// 울려 나간 패를 가져간 자리 — 그 무렵 울기 상자가 늘어난 자리. 울기 상자로 못 정했으면 null(패보로 바꿀 때 다음에 버린 자리로 본다).
  final Side? calledBy;

  /// 그 묶음의 종류(pon · chi · kan)와 패(가져간 패 포함). 묶음은 생겼는데 모양을 못 읽었으면 종류 'call' · 패는 가져간 한 장.
  final String? meldKind;
  final List<String> meldTiles;

  const RecordedDiscard({
    required this.side,
    required this.index,
    required this.tile,
    required this.share,
    required this.seen,
    required this.firstFrame,
    required this.firstAt,
    required this.takenFrame,
    required this.takenAt,
    required this.sideways,
    this.calledBy,
    this.meldKind,
    this.meldTiles = const [],
  });

  bool get taken => takenFrame != null;

  Map<String, dynamic> toJson() => {
        'side': side.name,
        'i': index + 1,
        'tile': tile,
        'share': double.parse(share.toStringAsFixed(2)),
        'n': seen,
        'first_at': firstAt.toIso8601String(),
        'taken_at': takenAt?.toIso8601String(),
        if (sideways) 'sideways': true,
        if (calledBy != null) 'called_by': calledBy!.name,
        if (meldKind != null) 'meld': {'kind': meldKind, 'tiles': meldTiles},
      };
}

class _Sight {
  final double u, v;
  final String tile;
  final double conf;
  final bool sideways;
  const _Sight(this.u, this.v, this.tile, this.conf, this.sideways);
}

class _Slot {
  double u, v;
  int first, last;
  int? taken;
  int streak = 0;
  int missFrom = 0;
  final Map<String, double> votes;
  final Map<String, double> best;
  int n;
  String? flipTo;
  int flipFrom = 0;
  double flipC = 0;
  int sideways = 0;

  _Slot(this.u, this.v, this.first, this.last, this.votes, this.best, this.n);

  String? get top {
    String? k;
    var m = double.negativeInfinity;
    for (final e in votes.entries) {
      if (e.value > m) {
        m = e.value;
        k = e.key;
      }
    }
    return k;
  }
}

class _Frame {
  final int index;
  final Map<Side, List<_Sight>> bySide;
  const _Frame(this.index, this.bySide);
}

const _next = {Side.bottom: Side.right, Side.right: Side.top, Side.top: Side.left, Side.left: Side.bottom};

/// 사진 기준 (dx, dy) → 그 자리 기준 (u, v).
(double, double) toSeatFrame(Side side, double dx, double dy) => switch (side) {
      Side.bottom => (dx, dy),
      Side.right => (-dy, dx),
      Side.top => (-dx, -dy),
      Side.left => (dy, -dx),
    };

/// 강의 패가 어느 자리 것인가: 기기 바깥 한 변 띠(v 0.8~2.6)에 들고 u 가 기기 폭 안팎(−1.3~1.7)이면 그 자리.
/// 모서리에서 두 자리에 걸리면 u 넘침이 작은 쪽. 어느 띠에도 안 들면 null. 길이는 기기 반 크기 [hd] 의 배수로 본다.
(Side, double, double)? assignSide(double dx, double dy, double hd) {
  (Side, double, double)? best;
  var bestOver = double.infinity, bestV = double.infinity;
  for (final s in Side.values) {
    final (u, v) = toSeatFrame(s, dx, dy);
    if (v < hd * 0.8 || v > hd * 2.6 || u < -hd * 1.3 || u > hd * 1.7) continue;
    final over = u < 0 ? math.max(0.0, u.abs() - hd) : math.max(0.0, u - hd * 1.05);
    if (over < bestOver || (over == bestOver && v < bestV)) {
      bestOver = over;
      bestV = v;
      best = (s, u, v);
    }
  }
  return best;
}

/// 묶음을 놓인 꼴로: 가져온 패 [called] 를 준 자리 쪽 칸에(왼쪽 자리 = 첫 칸, 맞은편 = 가운데, 오른쪽 자리 = 끝 칸), 나머지는 작은 패부터.
/// [rel] = (준 자리 − 가져간 자리) mod 4: 3 = 왼쪽(상가), 2 = 맞은편, 1 = 오른쪽(하가).
List<PaifuTile> _meldOrder(List<PaifuTile> tiles, PaifuTile called, int rel) {
  final rest = [...tiles];
  var i = rest.indexOf(called);
  if (i < 0) i = rest.indexWhere((t) => t.tile == called.tile);
  if (i < 0) return rest;
  final c = rest.removeAt(i);
  rest.sort((a, b) => a.tile != b.tile ? a.tile.compareTo(b.tile) : (a.red ? 0 : 1).compareTo(b.red ? 0 : 1));
  final at = rel == 3 ? 0 : (rel == 2 ? (rest.isEmpty ? 0 : 1) : rest.length);
  return rest..insert(at, c);
}

/// 겹쳐 보기 한 장면의 강 상자(사진 비율 0~1) → [DiscardRecorder.add] 입력.
/// 중심·기기 반 크기는 리치봉 구역(사진 비율 0~1, 앱 `GridZones.sticksZone`)에서 잡는다. [aspect] = 사진 가로/세로.
/// 길이 단위는 사진 세로 = 1.
({List<RiverSighting> sightings, double hd}) sightingsOf(
  Iterable<({double x, double y, double w, double h, String tile, double conf})> river, {
  required double zoneXmin,
  required double zoneXmax,
  required double zoneYmin,
  required double zoneYmax,
  required double aspect,
}) {
  final cx = (zoneXmin + zoneXmax) / 2, cy = (zoneYmin + zoneYmax) / 2;
  return (
    sightings: [
      for (final t in river)
        RiverSighting(
          dx: (t.x + t.w / 2 - cx) * aspect,
          dy: t.y + t.h / 2 - cy,
          w: t.w * aspect,
          h: t.h,
          tile: t.tile,
          conf: t.conf,
        ),
    ],
    hd: ((zoneXmax - zoneXmin) * aspect + (zoneYmax - zoneYmin)) / 4 * deviceShareOfSticksZone,
  );
}

/// 가운데 기기 반 크기 / 리치봉 구역 반 크기. 11-07 저장 격자에서 구역 반 78 화소 · 화소로 잰 기기 반 68.4 화소(0.88),
/// 11-14 격자에서도 구역 반 311 화소 × 0.88 = 패 폭 82 화소 / 0.3 과 맞는다. 기록기의 문턱은 기기 반 크기의 배수다.
const double deviceShareOfSticksZone = 0.88;

/// 같은 패에 겹친 상자는 큰 상자 하나만 남긴다(작은 쪽 넓이의 70% 넘게 겹침 — 서버 `river.dedupe` 와 같은 규칙).
/// 비스듬히 놓인 패 하나에 겹쳐 보기 검출이 상자 서너 개를 낸다(11-07 R2 아래 첫 9통).
List<RiverSighting> dedupeSightings(Iterable<RiverSighting> sightings) {
  final sorted = [...sightings]..sort((a, b) => (b.w * b.h).compareTo(a.w * a.h));
  final keep = <RiverSighting>[];
  for (final b in sorted) {
    var dup = false;
    for (final k in keep) {
      final ix = math.max(0.0, math.min(b.dx + b.w / 2, k.dx + k.w / 2) - math.max(b.dx - b.w / 2, k.dx - k.w / 2));
      final iy = math.max(0.0, math.min(b.dy + b.h / 2, k.dy + k.h / 2) - math.max(b.dy - b.h / 2, k.dy - k.h / 2));
      if (ix * iy > 0.7 * math.min(b.w * b.h, k.w * k.h)) {
        dup = true;
        break;
      }
    }
    if (!dup) keep.add(b);
  }
  return keep;
}

class DiscardRecorder {
  final DiscardRecorderConfig config;

  /// 선(親)이 앉은 쪽. 주면 선의 첫 버림 전 장면을 버린다. 국이 바뀌면 쓰는 쪽이 바꿔 넣는다(다음 [add] 부터 쓰인다).
  Side? dealer;

  final List<DateTime> _at = [];

  /// 장면마다 자리별 울기 상자의 패 종류(안 받은 장면은 null, 수만 받았으면 '?' 로 채움).
  final List<Map<Side, List<String>>?> _melds = [];
  final Map<Side, List<_Slot>> _slots = {for (final s in Side.values) s: []};
  double _hd = 1;
  bool _started;
  _Frame? _held;
  int _emptyStreak = 0;
  int _resets = 0;
  DateTime? _resetAt;

  DiscardRecorder({this.dealer, this.config = const DiscardRecorderConfig()}) : _started = dealer == null;

  /// 받은 장면 수.
  int get frames => _at.length;

  /// 적힌 버림 수(울려 나간 패 포함).
  int get count => rivers().values.fold(0, (a, b) => a + b.length);

  /// 탁자가 비어 기록을 새로 시작한 횟수와 마지막으로 비운 시각.
  int get resets => _resets;
  DateTime? get resetAt => _resetAt;

  /// 한 장면. [hd] = 가운데 기기 반 크기([RiverSighting] 과 같은 단위).
  ///
  /// 국의 경계는 탁자로 안다: 네 강에 패가 하나도 없는 장면이 [DiscardRecorderConfig.emptyNeed] 번 이어지면 그때까지의 칸을
  /// 버리고 새로 적는다(지난 국의 강이 남은 채 시작해도, 화료를 늦게 기록해도 다음 국에 섞이지 않게 — 11-14 r12·r14·r19 는
  /// 지난 국 탁자에서 추적이 시작돼 그대로 넣으면 헛 버림이 10~59장 나왔다, metrics 표 12-29).
  ///
  /// [meldTiles] = 이 장면에서 패 인식이 울기(meld)로 본 상자의 패 종류(자리별). 주면 한 장면짜리 "울려 나감" 을 확인하고,
  /// 울려 나간 패를 누가 어떤 묶음(퐁 · 치 · 깡)으로 가져갔는지 적는다. 수만 알면 [melds] — 확인에만 쓴다.
  void add(
    DateTime at,
    Iterable<RiverSighting> sightings, {
    required double hd,
    Map<Side, int>? melds,
    Map<Side, List<String>>? meldTiles,
  }) {
    final bySide = {for (final s in Side.values) s: <_Sight>[]};
    for (final t in dedupeSightings(sightings)) {
      final a = assignSide(t.dx, t.dy, hd);
      if (a == null) continue;
      final (side, u, v) = a;
      // 눕힌 패: 그 자리에서 볼 때 가로가 더 길다(왼쪽·오른쪽 자리는 사진에서 세로가 더 김).
      final across = side == Side.bottom || side == Side.top ? t.w / t.h : t.h / t.w;
      bySide[side]!.add(_Sight(u, v, t.tile, t.conf, across > config.sidewaysRatio));
    }
    final f = _Frame(_at.length, bySide);
    _at.add(at);
    _melds.add(meldTiles ?? (melds == null ? null : {for (final e in melds.entries) e.key: List.filled(e.value, '?')}));
    _hd = hd;
    _emptyStreak = bySide.values.every((l) => l.isEmpty) ? _emptyStreak + 1 : 0;
    if (_emptyStreak >= config.emptyNeed) {
      if (_slots.values.any((l) => l.isNotEmpty)) {
        for (final l in _slots.values) {
          l.clear();
        }
        _resets++;
        _resetAt = at;
      }
      _started = dealer == null;
      _held = null;
      return;
    }
    if (dealer == null) _started = true;
    if (!_started) {
      final has = bySide[dealer]!.isNotEmpty;
      final held = _held;
      if (has && held != null && held.bySide[dealer]!.isNotEmpty) {
        _started = true;
        _held = null;
        _process(held);
      } else {
        _held = f;
        return;
      }
    }
    _process(f);
  }

  void _process(_Frame frame) {
    final f = frame.index;
    final tol = _hd * config.tol;
    for (final s in Side.values) {
      final slots = _slots[s]!;
      final seen = frame.bySide[s]!;
      final alive = [
        for (final sl in slots)
          if (sl.taken == null) sl,
      ];
      double dist(_Slot sl, _Sight t, double du, double dv) {
        final a = t.u - du - sl.u, b = t.v - dv - sl.v;
        return math.sqrt(a * a + b * b);
      }

      // 이동량: (0,0) 과 모든 (패 − 칸) 차이 가운데, 그만큼 옮겼을 때 붙는 칸이 가장 많은 것(같은 패로 읽힌 적 있으면 +0.5). 같으면 작은 이동.
      double score(double du, double dv) {
        var sc = 0.0;
        for (final sl in alive) {
          for (final t in seen) {
            if (dist(sl, t, du, dv) < tol) {
              sc += 1 + (sl.votes.containsKey(t.tile) ? config.kindBonus : 0);
              break;
            }
          }
        }
        return sc;
      }

      var ou = 0.0, ov = 0.0;
      var bestScore = score(0, 0), bestMove = 0.0;
      for (final sl in alive) {
        for (final t in seen) {
          final du = t.u - sl.u, dv = t.v - sl.v;
          final sc = score(du, dv), move = du.abs() + dv.abs();
          if (sc > bestScore || (sc == bestScore && move < bestMove)) {
            bestScore = sc;
            bestMove = move;
            ou = du;
            ov = dv;
          }
        }
      }
      final pairs = <(double, int, int)>[
        for (var i = 0; i < alive.length; i++)
          for (var j = 0; j < seen.length; j++) (dist(alive[i], seen[j], ou, ov), i, j),
      ]..sort((a, b) {
          final c = a.$1.compareTo(b.$1);
          if (c != 0) return c;
          final d = a.$2.compareTo(b.$2);
          return d != 0 ? d : a.$3.compareTo(b.$3);
        });
      final ms = <int, int>{}, mt = <int, int>{};
      for (final (d, i, j) in pairs) {
        if (d > tol || ms.containsKey(i) || mt.containsKey(j)) continue;
        ms[i] = j;
        mt[j] = i;
      }
      for (final e in ms.entries.toList()) {
        final sl = alive[e.key], t = seen[e.value];
        // 같은 자리 바뀜: 마지막 칸이 확실히 A 였는데 확실한 B 로 두 장면 이어 읽힘 → A 는 울려 나갔고 그 자리에 다음 패가 놓였다.
        if (config.flip && e.key == alive.length - 1 && sl.votes.isNotEmpty) {
          final a = sl.top!;
          if ((sl.best[a] ?? 0) >= config.flipConf && t.tile != a && t.conf >= config.flipConf) {
            if (sl.flipTo == t.tile) {
              sl.taken = sl.flipFrom;
              slots.add(_Slot(t.u, t.v, sl.flipFrom, f, {t.tile: t.conf + sl.flipC}, {}, 2)..sideways = t.sideways ? 1 : 0);
              continue;
            }
            sl.flipTo = t.tile;
            sl.flipFrom = f;
            sl.flipC = t.conf;
            sl.u = t.u;
            sl.v = t.v;
            sl.last = f;
            continue;
          }
          sl.flipTo = null;
        }
        sl.u = t.u;
        sl.v = t.v;
        sl.last = f;
        sl.votes[t.tile] = (sl.votes[t.tile] ?? 0) + t.conf;
        sl.best[t.tile] = math.max(sl.best[t.tile] ?? 0, t.conf);
        sl.n++;
        if (t.sideways) sl.sideways++;
      }
      // 마지막 칸만 빠졌나? 다른 칸도 안 보이면 가림이라 건너뛴다.
      if (alive.isNotEmpty) {
        final missing = [
          for (var i = 0; i < alive.length; i++)
            if (!ms.containsKey(i)) i,
        ];
        final lastSlot = alive.last;
        if (missing.length == 1 && missing.single == alive.length - 1) {
          lastSlot.streak++;
          if (lastSlot.streak == 1) lastSlot.missFrom = f;
          if (lastSlot.streak >= config.streakNeed) lastSlot.taken = lastSlot.missFrom;
        } else if (missing.isEmpty) {
          lastSlot.streak = 0;
        }
      }
      // 안 붙은 패: 혼자 옮겨진 패면 그 칸을 옮기고, 아니면 새 칸.
      for (var j = 0; j < seen.length; j++) {
        if (mt.containsKey(j)) continue;
        final t = seen[j];
        _Slot? lost;
        var lostAt = -1;
        for (var i = 0; i < alive.length - 1; i++) {
          if (!ms.containsKey(i) && alive[i].votes.isNotEmpty && alive[i].top == t.tile) {
            lost = alive[i];
            lostAt = i;
            break;
          }
        }
        if (lost != null) {
          lost.u = t.u;
          lost.v = t.v;
          lost.last = f;
          lost.votes[t.tile] = (lost.votes[t.tile] ?? 0) + t.conf;
          lost.n++;
          if (t.sideways) lost.sideways++;
          ms[lostAt] = j;
          continue;
        }
        slots.add(_Slot(t.u, t.v, f, f, {t.tile: t.conf}, {t.tile: t.conf}, 1)..sideways = t.sideways ? 1 : 0);
      }
    }
  }

  /// [frame] 장면 앞보다 뒤에 어느 자리든 울기 상자가 [DiscardRecorderConfig.meldGrowMin] 넘게 늘었나(구간 안 최댓값끼리 견줌).
  /// 뒤 구간에 받은 장면이 아직 없으면(방금 일어난 일) 늘었다고 본다 — 모르는 것을 지우지 않는다.
  bool _meldGrewAround(int frame) {
    final t0 = _at[frame];
    final before = {for (final s in Side.values) s: 0}, after = {for (final s in Side.values) s: 0};
    var seenAfter = false;
    for (var i = 0; i < _at.length; i++) {
      final m = _melds[i];
      if (m == null || i == frame) continue;
      final d = _at[i].difference(t0);
      final into = i < frame ? (d >= -config.meldBefore ? before : null) : (d <= config.meldAfter ? after : null);
      if (into == null) continue;
      if (i > frame) seenAfter = true;
      for (final s in Side.values) {
        final c = m[s]?.length ?? 0;
        if (c > into[s]!) into[s] = c;
      }
    }
    if (!seenAfter) return true;
    return Side.values.any((s) => after[s]! - before[s]! >= config.meldGrowMin);
  }

  /// 고른 장면들에서 그 자리의 울기 상자 묶음: 가장 많이 보인 장면들 가운데 가장 자주 나온 구성(가림 · 오독에 덜 흔들리게).
  List<String> _stableMeld(Side side, bool Function(int frame) pick) {
    final seen = <String, int>{}, lists = <String, List<String>>{};
    var most = 0;
    for (var i = 0; i < _at.length; i++) {
      final m = _melds[i];
      if (m == null || !pick(i)) continue;
      final l = [...?m[side]]..sort();
      if (l.length < most) continue;
      if (l.length > most) {
        most = l.length;
        seen.clear();
      }
      final key = l.join(' ');
      seen[key] = (seen[key] ?? 0) + 1;
      lists[key] = l;
    }
    if (seen.isEmpty) return const [];
    return lists[seen.entries.reduce((a, b) => b.value > a.value ? b : a).key]!;
  }

  /// 늘어난 울기 상자 [grown] 이 가져간 패 [tile] 로 만든 어떤 묶음인가. 그 패와 상관없는 상자뿐이면 null.
  static ({String kind, List<String> tiles})? _meldShape(List<String> grown, String tile) {
    int? kindOf(String c) {
      try {
        return Tiles.parse(c);
      } on FormatException {
        return null;
      }
    }

    final t = kindOf(tile);
    if (t == null) return null;
    final same = [
      for (final c in grown)
        if (kindOf(c) == t) c,
    ];
    if (same.length >= 4) return (kind: 'kan', tiles: same.take(4).toList());
    // 같은 패가 둘 넘게 늘었으면 퐁(치에는 같은 패가 한 장뿐). 한 장이 가려 둘만 보였으면 보통 패로 채운다.
    if (same.length >= 2) return (kind: 'pon', tiles: [...same.take(3), for (var i = same.length; i < 3; i++) Tiles.toCode(t)]);
    if (same.length == 1 && t < 27) {
      // 치: 가져간 패를 낀 이어진 세 장이 다 보여야.
      final n = Tiles.number(t), first = t - (n - 1);
      for (var start = n - 2; start <= n; start++) {
        if (start < 1 || start + 2 > 9) continue;
        final run = <String>[];
        for (var k = start; k <= start + 2; k++) {
          final c = k == n ? same.single : grown.where((c) => kindOf(c) == first + k - 1).firstOrNull;
          if (c == null) break;
          run.add(c);
        }
        if (run.length == 3) return (kind: 'chi', tiles: run);
      }
    }
    // 묶음은 생겼는데 모양을 못 읽음(가림 · 오독, 또는 상자 수만 받음): 가져간 자리만 안다.
    final unread = grown.every((c) => kindOf(c) == null);
    return same.isNotEmpty || unread ? (kind: 'call', tiles: [tile]) : null;
  }

  /// 울려 나간 칸 [sl](버린 자리 [from])을 누가 어떤 묶음으로 가져갔나: 그 패가 처음 보이기 전([DiscardRecorderConfig.meldBefore])의
  /// 묶음과, 처음 보인 뒤부터 사라진 뒤 [DiscardRecorderConfig.meldAfter] 까지의 묶음을 자리마다 견줘 늘어난 상자를 본다.
  ({Side side, String kind, List<String> tiles})? _calledBy(_Slot sl, Side from) {
    final tile = sl.top;
    if (tile == null || sl.taken == null) return null;
    final lo = _at[sl.first].subtract(config.meldBefore), hi = _at[sl.taken!].add(config.meldAfter);
    ({Side side, String kind, List<String> tiles})? best;
    for (final x in Side.values) {
      if (x == from) continue;
      final before = _stableMeld(x, (i) => i < sl.first && !_at[i].isBefore(lo));
      final grown = [..._stableMeld(x, (i) => i > sl.first && !_at[i].isAfter(hi))];
      for (final b in before) {
        grown.remove(b);
      }
      if (grown.length < config.meldGrowMin) continue;
      final shape = _meldShape(grown, tile);
      if (shape == null) continue;
      // 모양까지 읽힌 자리를 먼저.
      if (best == null || (best.kind == 'call' && shape.kind != 'call')) best = (side: x, kind: shape.kind, tiles: shape.tiles);
    }
    return best;
  }

  /// 한 자리의 칸을 강 순서로: 바깥쪽(v)으로 줄을 나누고 줄 안은 u 순.
  List<_Slot> _order(List<_Slot> tiles) {
    final gap = _hd * config.rowGap;
    final ts = [...tiles]..sort((a, b) => a.v.compareTo(b.v));
    final rows = <List<_Slot>>[];
    var cur = <_Slot>[];
    for (final t in ts) {
      if (cur.isNotEmpty && t.v - cur.last.v > gap) {
        rows.add(cur);
        cur = [];
      }
      cur.add(t);
    }
    if (cur.isNotEmpty) rows.add(cur);
    return [
      for (final r in rows) ...(r..sort((a, b) => a.u.compareTo(b.u))),
    ];
  }

  /// 지금까지 적힌 자리별 버림(순서대로, 울려 나간 패 포함).
  Map<Side, List<RecordedDiscard>> rivers() {
    final out = <Side, List<RecordedDiscard>>{};
    final lastFrame = _at.length - 1;
    final checkMelds = _melds.any((m) => m != null);
    for (final s in Side.values) {
      // 한 장면에서만 보이고 그 뒤 두 장면 넘게 안 보이는데 울려 나간 것도 아닌 칸은 헛것(손에 가린 장면의 어긋난 상자)이라 뺀다.
      // 강의 패는 울려 나가지 않는 한 끝까지 남는다. 한 장면만 보이고 울려 나간 진짜 버림(11-07 R3a 왼쪽 적5통)은 남는다.
      final slots = [
        for (final sl in _slots[s]!)
          if (!(sl.n == 1 && sl.taken == null && sl.last < lastFrame - 1))
            // 한 장면만 보이고 "울려 나간" 칸은 그 무렵 울기 상자가 늘었을 때만 남긴다(아니면 헛것 — 버림으로도 안 적는다).
            if (!(checkMelds && sl.n == 1 && sl.taken != null && !_meldGrewAround(sl.first))) sl,
      ];
      // 남은 칸은 강 위치 순서. 한 자리의 버림은 강 순서 = 시각 순서라, 칸이 엇갈려 이어졌으면 처음 보인 장면들을 정렬해
      // 강 순서대로 다시 붙인다.
      final ordered = _order([
        for (final sl in slots)
          if (sl.taken == null) sl,
      ]);
      final firsts = [for (final sl in ordered) sl.first]..sort();
      // 울려 나간 칸은 강에 자리가 없으니 제 "처음 보인 장면" 으로 그 사이에 끼운다. 예전에는 끼운 뒤에 시각을 다시 붙여,
      // 남은 칸의 시각이 엇갈린 판에서 울려 나간 패가 맨 끝으로 밀리고(처음 보인 시각이 사라진 시각보다 늦게 찍힘) 패보에서
      // 울기가 빠졌다(11-14 r13 위 8통).
      final gone = [
        for (final sl in slots)
          if (sl.taken != null) sl,
      ]..sort((a, b) => a.first.compareTo(b.first));
      for (final sl in gone) {
        var k = 0;
        for (var i = 0; i < ordered.length; i++) {
          if (firsts[i] <= sl.first) k = i + 1;
        }
        ordered.insert(k, sl);
        firsts.insert(k, sl.first);
      }
      final calls = {
        for (final sl in ordered)
          if (sl.taken != null && checkMelds) sl: _calledBy(sl, s),
      };
      out[s] = [
        for (final (i, sl) in ordered.indexed)
          RecordedDiscard(
            calledBy: calls[sl]?.side,
            meldKind: calls[sl]?.kind,
            meldTiles: calls[sl]?.tiles ?? const [],
            side: s,
            index: i,
            tile: sl.top ?? '?',
            share: sl.votes.isEmpty ? 0 : sl.votes[sl.top]! / sl.votes.values.reduce((a, b) => a + b),
            seen: sl.n,
            firstFrame: firsts[i],
            firstAt: _at[firsts[i]],
            takenFrame: sl.taken,
            takenAt: sl.taken == null ? null : _at[sl.taken!],
            sideways: sl.sideways * 2 > sl.n,
          ),
      ];
    }
    return out;
  }

  /// 네 자리 버림을 한 줄로: 처음 보인 장면 순, 같은 장면에서 여럿이면 차례(아래 → 오른쪽 → 위 → 왼쪽)로 한 장씩 돌린다.
  List<RecordedDiscard> timeline() {
    final all = [
      for (final r in rivers().values) ...r,
    ];
    final frames = {for (final d in all) d.firstFrame}.toList()..sort();
    final out = <RecordedDiscard>[];
    Side? last;
    for (final f in frames) {
      final pool = {
        for (final s in Side.values)
          s: [
            for (final d in all)
              if (d.firstFrame == f && d.side == s) d,
          ],
      };
      var left = pool.values.fold(0, (a, b) => a + b.length);
      // 첫 장면은 선부터. 선을 모르면 아래부터.
      var cur = last ?? (dealer == null ? Side.left : Side.values[(dealer!.index + 3) % 4]);
      while (left > 0) {
        cur = _next[cur]!;
        final q = pool[cur]!;
        if (q.isEmpty) continue;
        out.add(q.removeAt(0));
        last = cur;
        left--;
      }
    }
    return out;
  }

  /// 적힌 버림으로 패보를 만든다. [bottomSeat] = 사진 아래쪽에 앉은 자리 번호, 쪽 → 자리는 `(bottomSeat + side.index) % 4`.
  ///
  /// 울려 나간 패는 그 뒤에 바로 버린 자리가 가져간 것으로 본다(묶음 종류·나머지 패는 모름 → `kind: call`, 그 한 장만).
  /// 뒤에 버림이 없으면(론) 울기로 적지 않는다. 눕힌 패는 그 자리의 첫 장만 리치 선언패, 그 뒤 버림은 쯔모기리로 적는다.
  Paifu toPaifu({
    required String id,
    required int bottomSeat,
    required int dealerSeat,
    required int hero,
    String title = '',
    String round = '',
    int honba = 0,
    List<String> names = const ['', '', '', ''],
    List<PaifuTile> doraIndicators = const [],
    List<PaifuTile> uraIndicators = const [],
    String note = '',
    PaifuResult? result,
  }) {
    int seatOf(Side s) => (bottomSeat + s.index) % 4;
    final line = timeline();
    final events = <PaifuEvent>[];
    final declared = <int>{};
    for (final (i, d) in line.indexed) {
      final PaifuTile tile;
      try {
        tile = PaifuTile.parse(d.tile);
      } on FormatException {
        continue; // 종류를 못 읽은 칸
      }
      final seat = seatOf(d.side);
      final riichi = d.sideways && !declared.contains(seat);
      events.add(PaifuEvent(
        type: PaifuEventType.discard,
        seat: seat,
        tile: tile,
        tsumogiri: declared.contains(seat) ? true : null,
        riichi: riichi,
      ));
      if (riichi) declared.add(seat);
      // 뒤에 버림이 하나도 없으면 그 패는 쏘인 패다(론) — 화료자가 펼친 손패가 울기 상자로 읽혀도 울기로 안 적는다(11-07 R3a 위 6삭).
      if (d.taken && i + 1 < line.length) {
        // 가져간 자리: 울기 상자가 늘어난 자리, 못 정했으면 바로 다음에 버린 자리.
        final next = line[i + 1].side != d.side ? line[i + 1].side : null;
        final by = d.calledBy ?? next;
        if (by != null) {
          final caller = seatOf(by);
          events.add(PaifuEvent(
            type: PaifuEventType.call,
            seat: caller,
            callKind: d.meldKind ?? 'call',
            from: seat,
            callTiles: _meldOrder(d.meldTiles.isEmpty ? [tile] : [for (final c in d.meldTiles) PaifuTile.parse(c)], tile, (seat - caller) % 4),
          ));
        }
      }
    }
    return Paifu(
      id: id,
      title: title,
      round: round,
      honba: honba,
      dealer: dealerSeat,
      hero: hero,
      names: names,
      doraIndicators: doraIndicators,
      uraIndicators: uraIndicators,
      note: note,
      events: events,
      result: result,
    );
  }
}
