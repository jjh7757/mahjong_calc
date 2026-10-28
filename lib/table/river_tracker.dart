/// 판 상태 추적 2단계: 게임 중 강(버림패)과 리치봉을 미리 본다. 순수 Dart, I/O 없음.
///
/// - **강:** 자리별 강 띠([GridZones.riverBand])의 흰 면이 패 1장 분량 늘고 두 프레임 안정이면 "버림"([Discard]) 으로
///   기록하고, 새로 흰 블록이 된 자리([ZoneSnapshot.newWhite])를 그 패의 위치로 둔다. Gemini 호출 없음. 화료 때 가장 최근
///   버림이 있는 자리가 **방총자 후보**이고 그 상자가 **론 패 위치**다(테스트 세트에서 강 끝 YOLO 틀이 2삭을 8/8 못 찾던 것의 대안).
///   흰 면이 패 1장 줄면 울기로 가져간 것(taken), 2장 넘게 줄면 새 판(cleared)으로 본다.
/// - **리치봉(기본 끔, [RiverTrackerConfig.trackSticks]):** 기기 가장자리 띠([GridZones.stickStrip])의 밝기 블록이 기준과
///   달라지고 안정이면 `/v2/sticks` 를 읽게 하고([RiverAction.readSticks]), 다른 프레임의 두 읽기가 같으면 확정([riichi]).
///   울기 추적과 같은 틀.
///
/// 쓰는 쪽(거치 화면)이 3초마다 [TableFrameStats] 의 강·띠 스냅샷을 [onFrame] 에 넣고, 돌려받은 행동을 처리해
/// [onSticksRead] 로 알려 준다. 화료 때는 [lastDiscard]·[riichi] 를 판독에 힌트로 넘긴다.
/// 설계: docs/state_tracking_design.md 6절.
library;

import 'grid_zones.dart';
import 'river_change.dart';
import 'table_layout.dart';
import 'tracker.dart' show TrackerEvent;

/// 게임 중 감지한 버림 하나. [box] 는 새로 흰 면이 된 곳(이미지 기준 0~1000, 패 하나 크기 안팎), 못 찾았으면 null.
class Discard {
  final Side side;
  final NormBox? box;
  final int seq;
  final DateTime at;
  final double tiles;
  const Discard({required this.side, required this.box, required this.seq, required this.at, required this.tiles});

  Map<String, dynamic> toJson() =>
      {'side': side.name, 'box': box?.toList(), 'seq': seq, 'at': at.toIso8601String(), 'tiles': tiles};

  @override
  String toString() => '${side.name}#$seq ${box ?? '위치 모름'}';
}

/// "리치봉 띠를 지금 프레임 기준으로 읽어라".
class RiverAction {
  final int frame;
  const RiverAction.readSticks(this.frame);

  @override
  String toString() => 'readSticks@$frame';
}

class RiverTrackerConfig {
  /// 연속 프레임 밝기 블록 차이가 이 이상이면 움직이는 중(손·팔).
  final double moveThreshold;

  /// 변화로 보려면 같은 프레임이 몇 번 이어져야 하나.
  final int stableFrames;

  /// 기준 대비 흰 면이 패 몇 장 이상 늘면 버림.
  final double discardTiles;

  /// 기준 대비 흰 면이 패 몇 장 이상 줄면 새 판(강 비움).
  final double clearTiles;

  /// 리치봉 띠의 기준 대비 밝기 차이가 이 이상이면 읽기.
  final double stickDiff;

  final Duration stickMinGap;
  final int stickMaxReads;
  final int stickConfirmReads;

  /// 리치봉 띠를 추적할지(기본 끔, 2026-10-28 사용자 결정). 화료 판독이 `/v2/sticks` 를 자리 판독과 나란히 늘 부르므로
  /// 미리 봐도 시간은 줄지 않고, 추적 결과는 판독에 더하기만 해서(합집합) 게임 중 서버 호출과 잘못 확정할 위험만 는다.
  /// 켜면 화료 사진에서 놓친 리치봉을 메울 수 있다(효과는 아직 못 잼).
  final bool trackSticks;

  const RiverTrackerConfig({
    this.trackSticks = false,
    this.moveThreshold = 0.03,
    this.stableFrames = 2,
    this.discardTiles = 0.6,
    this.clearTiles = 2.0,
    this.stickDiff = 0.04,
    this.stickMinGap = const Duration(seconds: 5),
    this.stickMaxReads = 3,
    this.stickConfirmReads = 2,
  });
}

class RiverSeatState {
  ZoneSnapshot? baseline;
  ZoneSnapshot? last;
  int stable = 0;
  int discards = 0;
  Discard? lastDiscard;
}

enum StickStatus { idle, moving, changed, reading, confirmed, unconfirmed }

class StickState {
  StickStatus status = StickStatus.idle;
  final Map<Side, ZoneSnapshot> baseline = {};
  final Map<Side, ZoneSnapshot> last = {};
  int stable = 0;
  int reads = 0;
  Set<Side>? candidate;
  DateTime? lastReadAt;
  int? pendingFrame;
  Map<Side, ZoneSnapshot>? atRead;
}

class RiverTracker {
  final RiverTrackerConfig config;

  /// 자리별 패 한 장의 강 띠 비율([riverTileFracOf]).
  final Map<Side, double> tileFrac;

  final Map<Side, RiverSeatState> rivers = {for (final s in Side.values) s: RiverSeatState()};
  final StickState sticks = StickState();
  final List<TrackerEvent> events = [];
  int frame = 0;
  int _seq = 0;

  /// 확정한 리치봉 자리.
  Set<Side> riichi = {};

  RiverTracker({required this.tileFrac, this.config = const RiverTrackerConfig()});

  /// 가장 최근 버림(네 자리 중). 없으면 null.
  Discard? get lastDiscard {
    Discard? best;
    for (final r in rivers.values) {
      final d = r.lastDiscard;
      if (d != null && (best == null || d.seq > best.seq)) best = d;
    }
    return best;
  }

  /// 자리별 감지한 버림 수(기록·표시용).
  Map<Side, int> get discardCounts => {for (final e in rivers.entries) e.key: e.value.discards};

  List<RiverAction> onFrame(Map<Side, ZoneSnapshot> riverSnaps, Map<Side, ZoneSnapshot> stripSnaps, DateTime now) {
    frame++;
    for (final e in riverSnaps.entries) {
      _riverFrame(e.key, e.value, now);
    }
    return config.trackSticks ? _stickFrame(stripSnaps, now) : const [];
  }

  void _riverFrame(Side side, ZoneSnapshot cur, DateTime now) {
    final r = rivers[side]!;
    final prev = r.last;
    r.last = cur;
    if (r.baseline == null || prev == null) {
      r.baseline = cur;
      r.stable = 1;
      return;
    }
    if (cur.diff(prev) > config.moveThreshold) {
      r.stable = 0;
      return;
    }
    r.stable++;
    if (r.stable < config.stableFrames - 1) return;
    final frac = tileFrac[side] ?? 0;
    if (frac <= 0) return;
    final delta = (cur.whiteFrac - r.baseline!.whiteFrac) / frac;
    if (delta >= config.discardTiles) {
      final box = cur.newWhite(r.baseline!);
      r.discards++;
      r.lastDiscard = Discard(side: side, box: box, seq: ++_seq, at: now, tiles: delta);
      _log(now, side, 'discard', '${delta.toStringAsFixed(1)}장 ${box ?? '(위치 모름)'}');
      r.baseline = cur;
    } else if (delta <= -config.discardTiles) {
      // 흰 면이 줄어듦. 손이 강 위에 잠깐 머문 것일 수 있어(합성 프레임에서 손이 6초 멈추자 taken·cleared 로 오인)
      // 늘어남보다 한 프레임 더 기다린다.
      if (r.stable < config.stableFrames) return;
      if (delta <= -config.clearTiles) {
        _log(now, side, 'cleared', '${(-delta).toStringAsFixed(1)}장 줄어듦');
        r.discards = 0;
      } else {
        // 패가 하나 사라짐 = 다른 사람이 울어 가져감. 마지막 버림이 사라진 것이니 론 패 후보에서 뺀다.
        _log(now, side, 'taken', '${(-delta).toStringAsFixed(1)}장');
      }
      r.lastDiscard = null;
      r.baseline = cur;
    } else if (cur.diff(r.baseline!) > config.moveThreshold) {
      // 장수는 그대로인데 블록이 달라짐(패를 밀어 정리). 기준만 바꾼다.
      r.baseline = cur;
    }
  }

  List<RiverAction> _stickFrame(Map<Side, ZoneSnapshot> snaps, DateTime now) {
    final st = sticks;
    if (st.baseline.isEmpty || st.last.isEmpty) {
      st.baseline.addAll(snaps);
      st.last
        ..clear()
        ..addAll(snaps);
      st.stable = 1;
      return const [];
    }
    var moving = false;
    for (final e in snaps.entries) {
      final prev = st.last[e.key];
      if (prev != null && e.value.diff(prev) > config.moveThreshold) moving = true;
    }
    st.last
      ..clear()
      ..addAll(snaps);
    if (moving) {
      st.stable = 0;
      if (st.status != StickStatus.reading && st.status != StickStatus.changed) st.status = StickStatus.moving;
      return const [];
    }
    st.stable++;
    if (st.stable < config.stableFrames - 1 || st.status == StickStatus.reading) return const [];

    var changed = false;
    for (final e in snaps.entries) {
      final base = st.baseline[e.key];
      if (base != null && e.value.diff(base) > config.stickDiff) changed = true;
    }
    final pending = st.status == StickStatus.changed || (st.status == StickStatus.unconfirmed && st.candidate != null);
    if (!changed && !pending) {
      if (st.status == StickStatus.moving) st.status = riichi.isEmpty ? StickStatus.idle : StickStatus.confirmed;
      return const [];
    }
    if (!pending) {
      st.reads = 0;
      st.candidate = null;
      st.status = StickStatus.changed;
      _log(now, Side.bottom, 'sticks_changed', '');
    }
    if (st.lastReadAt != null && now.difference(st.lastReadAt!) < config.stickMinGap) return const [];
    if (st.reads >= config.stickMaxReads) {
      if (st.status != StickStatus.unconfirmed) _log(now, Side.bottom, 'sticks_unconfirmed', '읽기 ${st.reads}번 불일치');
      st.status = StickStatus.unconfirmed;
      return const [];
    }
    st.status = StickStatus.reading;
    st.pendingFrame = frame;
    st.atRead = Map.of(snaps);
    st.lastReadAt = now;
    st.reads++;
    return [RiverAction.readSticks(frame)];
  }

  /// [frame] 프레임 요청의 `/v2/sticks` 결과(자리별 리치봉 유무). 다른 프레임의 늦은 답은 무시한다.
  void onSticksRead(int frame, Map<Side, bool> read, DateTime now) {
    final st = sticks;
    if (st.status != StickStatus.reading || st.pendingFrame != frame) return;
    final seen = {
      for (final e in read.entries)
        if (e.value) e.key,
    };
    final agree = st.candidate != null && _same(st.candidate!, seen);
    if (agree || config.stickConfirmReads <= 1) {
      riichi = seen;
      st.status = StickStatus.confirmed;
      st.baseline
        ..clear()
        ..addAll(st.atRead ?? st.last);
      st.candidate = null;
      st.reads = 0;
      _log(now, Side.bottom, 'sticks_confirmed', seen.isEmpty ? '없음' : seen.map((s) => s.name).join(' '));
      return;
    }
    st.candidate = seen;
    _log(now, Side.bottom, 'sticks_candidate', seen.isEmpty ? '없음' : seen.map((s) => s.name).join(' '));
    st.status = st.reads >= config.stickMaxReads ? StickStatus.unconfirmed : StickStatus.changed;
    if (st.status == StickStatus.unconfirmed) _log(now, Side.bottom, 'sticks_unconfirmed', '읽기 ${st.reads}번 불일치');
  }

  void onSticksReadFailed(int frame, DateTime now, [String reason = '']) {
    final st = sticks;
    if (st.status != StickStatus.reading || st.pendingFrame != frame) return;
    _log(now, Side.bottom, 'sticks_failed', reason);
    st.status = st.reads >= config.stickMaxReads ? StickStatus.unconfirmed : StickStatus.changed;
  }

  /// 새 판(화료·유국 기록 뒤). 버림·리치봉을 비우고 다음 프레임을 새 기준으로.
  void reset(DateTime now, [String reason = '새 판']) {
    for (final s in Side.values) {
      rivers[s] = RiverSeatState();
    }
    sticks
      ..status = StickStatus.idle
      ..baseline.clear()
      ..last.clear()
      ..stable = 0
      ..reads = 0
      ..candidate = null
      ..lastReadAt = null
      ..pendingFrame = null
      ..atRead = null;
    riichi = {};
    events.add(TrackerEvent(now, Side.bottom, 'reset', reason));
  }

  /// 장면 전체가 바뀌었다(카메라 움직임·조명, [SceneShiftGate]). 감지한 버림·확정한 리치봉은 두고 픽셀 기준과
  /// 진행 중인 리치봉 읽기만 버린다 — 다음 프레임이 새 기준.
  void cameraMoved(DateTime now) {
    for (final r in rivers.values) {
      r
        ..baseline = null
        ..last = null
        ..stable = 0;
    }
    sticks
      ..status = riichi.isEmpty ? StickStatus.idle : StickStatus.confirmed
      ..baseline.clear()
      ..last.clear()
      ..stable = 0
      ..reads = 0
      ..candidate = null
      ..pendingFrame = null
      ..atRead = null;
    events.add(TrackerEvent(now, Side.bottom, 'rebase', '장면 전체 변화'));
  }

  Map<String, dynamic> toJson() => {
        'frame': frame,
        'rivers': {
          for (final e in rivers.entries)
            e.key.name: {'discards': e.value.discards, 'last': e.value.lastDiscard?.toJson()},
        },
        'riichi': [for (final s in riichi) s.name],
        'sticks': {'status': sticks.status.name, 'reads': sticks.reads},
        'events': [for (final e in events) e.toJson()],
      };

  void _log(DateTime now, Side side, String kind, String detail) => events.add(TrackerEvent(now, side, kind, detail));

  static bool _same(Set<Side> a, Set<Side> b) => a.length == b.length && a.containsAll(b);
}
