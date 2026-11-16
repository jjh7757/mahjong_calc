/// 일발 판정의 "리치 뒤 울기·버림" 을 패 인식(겹쳐 보기, 기기 안 검출 + 역할 모델)으로 본다. 순수 Dart, I/O 없음.
///
/// 픽셀 추적(흰 면 넓이)은 이 매장처럼 울기를 펠트 밖 흰 테두리 위에 놓으면 못 보고(자른 칸) 테두리 노출 흔들림을 울기로 잡았다(통째 칸).
/// 강 버림 수도 장면 전체 변화에 묻히거나 옆 자리 띠로 셌다(11-07 15:40 판). 겹쳐 보기는 패를 직접 읽어 자리별 울기 상자와
/// 강 상자를 준다 — 11-14 프레임에서 테두리 위 암깡·白 퐁을 자리까지 맞게 냈다(metrics 표 11-3, 2026-11-16 사용자 "겹쳐 보기로 바꾸기").
///
/// 쓰는 법(거치 화면): 리치봉이 처음 보였을 때·확정됐을 때 한 번씩 읽어 [CallWatch.addBaseline], 화료 사진을 한 번 읽어
/// [CallWatch.verdict]. 늘 켜 둘 필요가 없다. 판정이 [CallAnswer.unknown] 이거나 기준이 없으면 쓰는 쪽이 픽셀 판정으로 돌아간다.
library;

import 'table_layout.dart';

/// 패 인식 한 장면에서 센 수. [ownRiver] 는 가운데 기기에서 본 사분면으로 나눈 자리별 강 상자 수.
class TableCount {
  final int river;
  final Map<Side, int> ownRiver;
  final Map<Side, int> melds;
  const TableCount({required this.river, required this.ownRiver, required this.melds});

  /// [tiles] = 상자 중심(사진 비율 0~1)·역할·자리. [centerX]·[centerY] = 가운데 기기 중심(사진 비율), [aspect] = 사진 가로/세로.
  /// 강 주인은 역할 모델의 자리 답이 아니라 기기 중심에서 본 방향으로 정한다(자리 답은 강에서 격자 칸이라 못 맞춤, metrics 표 4-3).
  factory TableCount.of(
    Iterable<({double cx, double cy, String role, Side? side})> tiles, {
    required double centerX,
    required double centerY,
    double aspect = 1,
  }) {
    final own = {for (final s in Side.values) s: 0}, melds = {for (final s in Side.values) s: 0};
    var river = 0;
    for (final t in tiles) {
      if (t.role == 'river') {
        river++;
        final dx = (t.cx - centerX) * aspect, dy = t.cy - centerY;
        final side = dy.abs() >= dx.abs() ? (dy > 0 ? Side.bottom : Side.top) : (dx > 0 ? Side.right : Side.left);
        own[side] = own[side]! + 1;
      } else if (t.role == 'meld' && t.side != null) {
        melds[t.side!] = melds[t.side!]! + 1;
      }
    }
    return TableCount(river: river, ownRiver: own, melds: melds);
  }

  /// 항목마다 큰 쪽. 손·팔이 가린 프레임은 수가 줄기만 하므로 기준 읽기 여러 장은 최댓값으로 합친다.
  TableCount maxWith(TableCount o) => TableCount(
        river: river > o.river ? river : o.river,
        ownRiver: {for (final s in Side.values) s: _max(ownRiver[s] ?? 0, o.ownRiver[s] ?? 0)},
        melds: {for (final s in Side.values) s: _max(melds[s] ?? 0, o.melds[s] ?? 0)},
      );

  static int _max(int a, int b) => a > b ? a : b;

  Map<String, dynamic> toJson() => {
        'river': river,
        'own_river': {for (final e in ownRiver.entries) e.key.name: e.value},
        'melds': {for (final e in melds.entries) if (e.value > 0) e.key.name: e.value},
      };
}

enum CallAnswer {
  /// 리치 뒤 한 바퀴 안이고 아무도 안 울었다 → 일발 후보.
  yes,

  /// 리치한 사람이 또 버렸거나, 버림이 한 바퀴를 넘었거나, 다른 사람이 울었다.
  no,

  /// 강 상자가 기준보다 줄었다(기준이 낡았거나 가림) — 판단 못 함.
  unknown,
}

class CallVerdict {
  final CallAnswer answer;

  /// 끝 − 기준: 강 상자 수, 리치한 자리의 강 상자 수.
  final int riverDiff, ownDiff;

  /// 울기 상자가 늘어난 다른 자리.
  final Set<Side> calls;

  /// 리치한 자리 자신의 울기 상자가 [CallWatchConfig.selfGrow] 이상 늘었다(안깡 의심 — 화료 사진에 안깡이 있을 때만 일발을 지운다).
  final bool selfGrew;
  final TableCount base, last;
  const CallVerdict(this.answer, {required this.riverDiff, required this.ownDiff, required this.calls, required this.selfGrew, required this.base, required this.last});

  Map<String, dynamic> toJson() => {
        'answer': answer.name,
        'river_diff': riverDiff,
        'own_diff': ownDiff,
        'calls': [for (final s in calls) s.name],
        'self_grew': selfGrew,
        'base': base.toJson(),
        'final': last.toJson(),
      };
}

class CallWatchConfig {
  /// 리치 뒤 강 상자가 이 장수까지 늘어도 한 바퀴 안(다른 세 사람).
  final int maxDiscards;

  /// 한 자리의 울기 상자가 이 장수 미만이면 0장으로 친다 — 떼어 둔 화료패·테두리의 흰 홈 같은 낱장 헛 검출(metrics 표 11-3).
  final int meldMin;

  /// 리치한 자리의 울기 상자가 이만큼 늘면 [CallVerdict.selfGrew](떼어 둔 쯔모 패 1장은 뺀다).
  final int selfGrow;

  /// 기준 읽기는 봉이 처음 보인 뒤 이 시간 안의 것만 합친다([baseReads] 장까지). 늦은 읽기는 그 사이 버림이 섞여 판정이 헐거워진다.
  final Duration baseWindow;
  final int baseReads;

  /// 첫 기준 읽기는 이 시간 안이어야 한다(읽기가 밀렸을 때). 넘으면 기준 없이 픽셀 판정.
  final Duration baseLatest;

  const CallWatchConfig({
    this.maxDiscards = 3,
    this.meldMin = 3,
    this.selfGrow = 2,
    this.baseWindow = const Duration(seconds: 6),
    this.baseReads = 2,
    this.baseLatest = const Duration(seconds: 12),
  });
}

class CallWatch {
  final CallWatchConfig config;
  final Map<Side, TableCount> _base = {};
  final Map<Side, int> _reads = {};
  CallWatch({this.config = const CallWatchConfig()});

  bool get isEmpty => _base.isEmpty;
  TableCount? baseline(Side side) => _base[side];

  /// 그 자리의 기준 읽기가 더 필요한가. [seenAt] = 봉이 처음 보인 시각.
  bool wants(Side side, DateTime seenAt, DateTime now) {
    final n = _reads[side] ?? 0;
    final age = now.difference(seenAt);
    if (age.isNegative) return false;
    return n == 0 ? age <= config.baseLatest : (n < config.baseReads && age <= config.baseWindow);
  }

  void addBaseline(Side side, TableCount c) {
    final old = _base[side];
    _base[side] = old == null ? c : old.maxWith(c);
    _reads[side] = (_reads[side] ?? 0) + 1;
  }

  /// [keep] 밖 자리의 기준을 버린다(새 판·리치가 아니게 된 자리).
  void prune(Set<Side> keep) {
    _base.removeWhere((s, _) => !keep.contains(s));
    _reads.removeWhere((s, _) => !keep.contains(s));
  }

  /// 화료 때의 수 [last] 로 그 자리의 판정. 기준이 없으면 null.
  CallVerdict? verdict(Side side, TableCount last) {
    final base = _base[side];
    if (base == null) return null;
    int eff(int n) => n >= config.meldMin ? n : 0;
    final riverDiff = last.river - base.river;
    final ownDiff = (last.ownRiver[side] ?? 0) - (base.ownRiver[side] ?? 0);
    final calls = {
      for (final o in Side.values)
        if (o != side && eff(last.melds[o] ?? 0) > eff(base.melds[o] ?? 0)) o,
    };
    final selfGrew = (last.melds[side] ?? 0) - (base.melds[side] ?? 0) >= config.selfGrow;
    final answer = riverDiff < 0
        ? CallAnswer.unknown
        : (riverDiff > config.maxDiscards || ownDiff > 0 || calls.isNotEmpty ? CallAnswer.no : CallAnswer.yes);
    return CallVerdict(answer, riverDiff: riverDiff, ownDiff: ownDiff, calls: calls, selfGrew: selfGrew, base: base, last: last);
  }
}
