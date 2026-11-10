/// 판 상태 추적 2단계: 게임 중 강(버림패)과 리치봉을 미리 본다. 순수 Dart, I/O 없음.
///
/// - **강:** 자리별 강 띠([GridZones.riverBand])의 흰 면이 패 1장 분량 늘고 두 프레임 안정이면 "버림"([Discard]) 으로
///   기록하고, 새로 흰 블록이 된 자리([ZoneSnapshot.newWhite])를 그 패의 위치로 둔다. Gemini 호출 없음. 화료 때 가장 최근
///   버림이 있는 자리가 **방총자 후보**이고 그 상자가 **론 패 위치**다(테스트 세트에서 강 끝 YOLO 틀이 2삭을 8/8 못 찾던 것의 대안).
///   흰 면이 패 1장 줄면 울기로 가져간 것(taken), 2장 넘게 줄면 새 판(cleared)으로 본다. 강 띠는 가운데 기기까지 덮지만
///   매장(AMOS) 리치봉은 파란 막대라 흰 면에 안 잡힌다(2026-10-29 사용자 확인). 흰 리치봉을 쓰는 곳이면 홈의 봉이 버림으로 잡힌다.
/// - **리치봉([RiverTrackerConfig.trackSticks], 2026-10-29 부터 기본 켬):** 기기 가장자리 띠([GridZones.stickStrip])의 밝기 블록이 기준과
///   달라지고 안정이면 `/v2/sticks` 를 읽게 하고([RiverAction.readSticks]), 다른 프레임의 두 읽기가 같으면 확정([riichi]).
///   울기 추적과 같은 틀. 띠가 처음 바뀐 순간의 버림 수로 더블리치·일발 후보를 낸다.
///   **2026-11-10 부터 격자에 리치봉 상자가 있으면** 서버 읽기 대신 프레임 픽셀 판정([TableFrameStats.sticksSeen], 색 무관)을
///   자리별로 [RiverTrackerConfig.localConfirmFrames] 프레임 이어 보면 확정한다(서버 호출 없음, 리치 뒤 약 6초).
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

  /// 또는 밝기가 크게 바뀐 블록이 띠의 이 비율 이상이면 읽기. 매장 리치봉은 홈에 꽂는 파란 막대라 띠 평균으로는
  /// 묽어진다(합성: 리치봉 상자 격자에서 평균 0.018 · 바뀐 블록 0.11, 손이 지나간 프레임 0.03, 고정 폰 0).
  final double stickChangedFrac;

  final Duration stickMinGap;
  final int stickMaxReads;
  final int stickConfirmReads;

  /// 리치봉 띠를 추적할지. 10-28 에 껐다(화료 판독이 `/v2/sticks` 를 늘 부르니 시간은 안 줄고 게임 중 호출만 는다).
  /// 10-29 다시 기본 켬(사용자 결정): 리치 시점을 알아야 더블리치·일발을 자동으로 낼 수 있다. 장면 전체 변화 검사 뒤
  /// 헛 리치봉 읽기는 고정·움직인 폰 모두 0회(metrics 표 8).
  final bool trackSticks;

  /// 리치봉 띠 변화를 본 뒤 이 시간 안에 그 자리에서 잡힌 버림은 리치 선언패(횡치)로 본다 — 패를 놓고 봉을 꽂으니
  /// 같은 프레임이나 한 프레임 늦게 잡힌다. 리치한 사람의 다음 버림은 세 사람이 돈 뒤라 이보다 늦다.
  final Duration riichiTileLag;

  /// 강 띠의 흰 면이 패 이 장수 미만이면 빈 강으로 본다(더블리치는 빈 강을 본 판에서만).
  final double emptyTiles;

  /// 리치봉을 프레임 픽셀로 판정([TableFrameStats.sticksSeen], 색 무관, 2026-11-10). 켜져 있고 프레임에 판정이 있으면
  /// `/v2/sticks` 를 부르지 않는다. 격자에 리치봉 상자가 없으면(판정 없음) 예전처럼 Gemini 읽기.
  /// Projection Mahjong(2026)의 "자리별 리치 구역 + 연속 감지 + 한 사람당 한 번" 을 3초 프레임에 맞춘 것.
  final bool localSticks;

  /// 그 자리 홈에 봉이 이 프레임 수만큼 이어 보이면 리치(손이 지나가는 프레임은 끊김으로 안 셈).
  final int localConfirmFrames;

  /// 홈이 이 프레임 수만큼 이어 비어 보인 자리만 리치 시점을 적는다(판 처음부터 꽂혀 있던 봉 = 전판 유국 공탁 등은 시점 모름).
  final int localEmptyFrames;

  const RiverTrackerConfig({
    this.trackSticks = true,
    this.localSticks = true,
    this.localConfirmFrames = 2,
    this.localEmptyFrames = 2,
    this.riichiTileLag = const Duration(seconds: 6),
    this.emptyTiles = 0.5,

    this.moveThreshold = 0.03,
    this.stableFrames = 2,
    this.discardTiles = 0.6,
    this.clearTiles = 2.0,
    this.stickDiff = 0.04,
    this.stickChangedFrac = 0.06,
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

  /// 새 판(추적기 생성·[RiverTracker.reset]) 뒤 이 강이 빈 것을 본 적이 있다. 판 중간에 추적을 시작하면 버림 수가
  /// 그때부터라 "첫 버림" 을 믿을 수 없다.
  bool seenEmpty = false;

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

  /// 리치한 순간의 그 자리 버림 수(선언패 포함)·전체 버림 수·그때까지 '울어 가져감'(taken) 수·시각. 확정은 두 읽기
  /// 뒤라 10초쯤 늦으므로 띠가 처음 바뀐 순간([_changeAt])의 수를 쓴다. 더블리치·일발 추론용(2026-10-29) — 버림을
  /// 놓치거나 카메라가 움직였을 수 있으니 결과는 "확인" 플래그와 함께 쓴다.
  /// [fresh] = 그 순간까지 네 강이 모두 빈 것을 본 적이 있다(버림 수가 판 처음부터 센 것).
  final Map<Side, ({int own, int total, int taken, DateTime at, bool fresh})> riichiAt = {};
  int _taken = 0;

  /// 리치봉 띠가 바뀐 순간의 자리별 버림 수(확정되면 [riichiAt] 으로 옮긴다).
  ({Map<Side, int> own, int total, int taken, DateTime at, bool fresh})? _changeAt;

  /// 이번 변화(확정 전까지)에서 띠가 실제로 바뀐 자리. 리치 시점은 이 자리에만 적는다 — 추적 전부터 꽂혀 있던 봉은
  /// 확정 읽기에 같이 나오지만 언제 리치했는지 모른다(태블릿 통합 테스트 10-29: 장면 D 의 위·아래 봉이 방금 리치로 적힘).
  final Set<Side> _changedSides = {};

  bool get _fresh => rivers.values.every((r) => r.seenEmpty);

  /// 첫 순 리치(더블리치 후보): 판 처음부터 셌고, 자기 버림 1장(선언패를 못 잡았으면 0)·전체 4장 이하·가져감 0.
  Set<Side> get doubleRiichiCandidates => {
        for (final e in riichiAt.entries)
          if (e.value.fresh && e.value.own <= 1 && e.value.total <= 4 && e.value.taken == 0) e.key,
      };

  /// 일발 후보: 리치 뒤 그 자리가 더 버리지 않았고(다음 쯔모까지) 아무도 강에서 울어 가져가지 않았다.
  /// 안깡·가깡은 강에 안 보이니 쓰는 쪽이 [meldGrewSince](울기 추적)로 거른다.
  Set<Side> ippatsuCandidates({bool Function(DateTime since)? meldGrewSince}) => {
        for (final e in riichiAt.entries)
          if (rivers[e.key]!.discards == e.value.own &&
              _taken == e.value.taken &&
              !(meldGrewSince?.call(e.value.at) ?? false))
            e.key,
      };

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

  /// [sticksSeen] = 그 프레임의 자리별 홈 픽셀 판정([TableFrameStats.sticksSeen]). 있고 [RiverTrackerConfig.localSticks]
  /// 면 리치봉은 그것으로만 정하고 읽기 요청을 내지 않는다.
  List<RiverAction> onFrame(Map<Side, ZoneSnapshot> riverSnaps, Map<Side, ZoneSnapshot> stripSnaps, DateTime now,
      {Map<Side, bool>? sticksSeen}) {
    frame++;
    for (final e in riverSnaps.entries) {
      _riverFrame(e.key, e.value, now);
    }
    if (!config.trackSticks) return const [];
    if (config.localSticks && sticksSeen != null && sticksSeen.isNotEmpty) {
      _localStickFrame(sticksSeen, stripSnaps, now);
      return const [];
    }
    return _stickFrame(stripSnaps, now);
  }

  // 픽셀 판정 상태(자리별): 봉이 이어 보인 프레임 수, 처음 보인 순간의 버림 수, 이어 빈 프레임 수, 띠 직전 스냅샷.
  final Map<Side, int> _seenRun = {};
  final Map<Side, ({int own, int total, int taken, DateTime at, bool fresh})> _firstSeen = {};
  final Map<Side, int> _emptyRun = {};
  final Map<Side, ZoneSnapshot> _localLast = {};

  /// 자리별로 봉이 [RiverTrackerConfig.localConfirmFrames] 프레임 이어 보이면 리치(판 끝까지 유지). 손이 지나가는
  /// 프레임(그 자리 리치봉 띠가 직전과 크게 다름)에서 안 보이는 것은 끊김으로 치지 않는다 — 가림.
  void _localStickFrame(Map<Side, bool> seen, Map<Side, ZoneSnapshot> strips, DateTime now) {
    for (final s in Side.values) {
      final cur = strips[s], prev = _localLast[s];
      final moving = cur != null && prev != null && cur.diff(prev) > config.moveThreshold;
      if (cur != null) _localLast[s] = cur;
      if (riichi.contains(s)) continue;
      if (seen[s] ?? false) {
        _emptyRun[s] = 0;
        final run = (_seenRun[s] ?? 0) + 1;
        _seenRun[s] = run;
        if (run == 1) {
          _firstSeen[s] = (own: rivers[s]!.discards, total: _totalDiscards, taken: _taken, at: now, fresh: _fresh);
          _log(now, s, 'sticks_seen', '');
        }
        if (run >= config.localConfirmFrames) {
          riichi = {...riichi, s};
          final f = _firstSeen[s];
          if (f != null && _slotWasEmpty.contains(s)) riichiAt[s] = f;
          _log(now, s, 'sticks_confirmed', '픽셀 $run프레임${_slotWasEmpty.contains(s) ? '' : '(처음부터 꽂힘, 시점 모름)'}');
        }
      } else if (!moving) {
        _seenRun[s] = 0;
        _firstSeen.remove(s);
        final e = (_emptyRun[s] ?? 0) + 1;
        _emptyRun[s] = e;
        if (e >= config.localEmptyFrames) _slotWasEmpty.add(s);
      }
    }
    sticks.status = riichi.isEmpty ? StickStatus.idle : StickStatus.confirmed;
  }

  /// 이번 판에 홈이 빈 것을 본 자리(리치 시점을 적을 수 있는 자리).
  final Set<Side> _slotWasEmpty = {};

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
    if (cur.whiteFrac / frac < config.emptyTiles) r.seenEmpty = true;
    final delta = (cur.whiteFrac - r.baseline!.whiteFrac) / frac;
    if (delta >= config.discardTiles) {
      final box = cur.newWhite(r.baseline!);
      r.discards++;
      r.lastDiscard = Discard(side: side, box: box, seq: ++_seq, at: now, tiles: delta);
      _log(now, side, 'discard', '${delta.toStringAsFixed(1)}장 ${box ?? '(위치 모름)'}');
      _lateRiichiTile(side, now);
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
        _taken++;
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
      // 읽는 중·후보가 남은 동안은 상태를 그대로 둔다(손이 지나가도 후보를 이어서 확인).
      if (st.status != StickStatus.reading && st.status != StickStatus.changed && st.candidate == null) {
        st.status = StickStatus.moving;
      }
      return const [];
    }
    st.stable++;
    if (st.stable < config.stableFrames - 1 || st.status == StickStatus.reading) return const [];

    final changedNow = <Side>{
      for (final e in snaps.entries)
        if (st.baseline[e.key] case final base?)
          if (e.value.diff(base) > config.stickDiff || e.value.changedFrac(base) >= config.stickChangedFrac) e.key,
    };
    final changed = changedNow.isNotEmpty;
    final pending = st.status == StickStatus.changed || (st.status == StickStatus.unconfirmed && st.candidate != null);
    if (!changed && !pending) {
      if (st.status == StickStatus.moving) st.status = riichi.isEmpty ? StickStatus.idle : StickStatus.confirmed;
      return const [];
    }
    if (!pending) {
      st.reads = 0;
      st.candidate = null;
      st.status = StickStatus.changed;
      _changedSides
        ..clear()
        ..addAll(changedNow);
      _changeAt = (
        own: {for (final e in rivers.entries) e.key: e.value.discards},
        total: _totalDiscards,
        taken: _taken,
        at: now,
        fresh: _fresh,
      );
      _log(now, Side.bottom, 'sticks_changed', '');
    }
    _changedSides.addAll(changedNow);
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
  ///
  /// 확정은 **자리별**이다(2026-11-10, 11-07 실제 대국 리치 추적 0/5 대책 — Projection Mahjong 의 자리별 리치 구역·
  /// 한 사람당 한 번 참고): 아직 리치가 아닌 자리가 앞 읽기(후보)와 이번 읽기에 모두 봉이 있으면 그 자리만 리치로 넣는다.
  /// 다른 자리 답이 엇갈려도(손이 다른 홈을 가림) 그 자리 확정은 막지 않는다. 한 번 넣은 리치는 판이 끝날 때([reset])까지
  /// 빼지 않는다 — 봉은 판 중에 빠지지 않으니, 나중 읽기의 "없음"(손이 봉을 가림)이 리치를 지우면 안 된다.
  /// 리치 밖 자리의 답이 두 번 같으면(없음 포함) 이번 변화를 끝내고 띠 기준을 새로 잡는다.
  void onSticksRead(int frame, Map<Side, bool> read, DateTime now) {
    final st = sticks;
    if (st.status != StickStatus.reading || st.pendingFrame != frame) return;
    final seen = {
      for (final e in read.entries)
        if (e.value) e.key,
    };
    final fresh = seen.difference(riichi);
    final prev = st.candidate?.difference(riichi);
    final single = config.stickConfirmReads <= 1;
    final agreed = single ? fresh : (prev == null ? <Side>{} : fresh.intersection(prev));
    if (agreed.isNotEmpty) {
      final c = _changeAt;
      for (final s in agreed) {
        if (!_changedSides.contains(s)) continue;
        riichiAt[s] = c != null
            ? (own: c.own[s] ?? 0, total: c.total, taken: c.taken, at: c.at, fresh: c.fresh)
            : (own: rivers[s]!.discards, total: _totalDiscards, taken: _taken, at: now, fresh: _fresh);
      }
      riichi = {...riichi, ...agreed};
    }
    final rest = fresh.difference(agreed);
    if (single || (prev != null && _same(prev.difference(agreed), rest))) {
      st.status = StickStatus.confirmed;
      st.baseline
        ..clear()
        ..addAll(st.atRead ?? st.last);
      st.candidate = null;
      st.reads = 0;
      _log(now, Side.bottom, 'sticks_confirmed', riichi.isEmpty ? '없음' : riichi.map((s) => s.name).join(' '));
      return;
    }
    if (agreed.isNotEmpty) _log(now, Side.bottom, 'sticks_confirmed', riichi.map((s) => s.name).join(' '));
    st.candidate = rest;
    _log(now, Side.bottom, 'sticks_candidate', rest.isEmpty ? '없음' : rest.map((s) => s.name).join(' '));
    st.status = st.reads >= config.stickMaxReads ? StickStatus.unconfirmed : StickStatus.changed;
    if (st.status == StickStatus.unconfirmed) _log(now, Side.bottom, 'sticks_unconfirmed', '읽기 ${st.reads}번 불일치');
  }

  void onSticksReadFailed(int frame, DateTime now, [String reason = '']) {
    final st = sticks;
    if (st.status != StickStatus.reading || st.pendingFrame != frame) return;
    _log(now, Side.bottom, 'sticks_failed', reason);
    st.status = st.reads >= config.stickMaxReads ? StickStatus.unconfirmed : StickStatus.changed;
  }

  /// [riichi] 에서 전판 유국으로 남은 봉([carried], 대국 기록이 아는 주인)을 뺀 것. 그 자리는 이번 판에 띠가 바뀐 것을
  /// 봤을 때([riichiAt])만 남긴다. 기록에 없는데 처음부터 꽂혀 있던 봉은 추적 전에 한 리치로 보고 그대로 둔다.
  Set<Side> riichiExcept(Set<Side> carried) => {
        for (final s in riichi)
          if (!carried.contains(s) || riichiAt.containsKey(s)) s,
      };

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
    riichiAt.clear();
    _changeAt = null;
    _changedSides.clear();
    _taken = 0;
    _seenRun.clear();
    _firstSeen.clear();
    _emptyRun.clear();
    _localLast.clear();
    _slotWasEmpty.clear();
    events.add(TrackerEvent(now, Side.bottom, 'reset', reason));
  }

  /// 장면 전체가 바뀌었다(카메라 움직임·조명, [SceneShiftGate]). 감지한 버림·확정한 리치봉은 두고 픽셀 기준만
  /// 버린다 — 다음 프레임이 새 기준.
  ///
  /// 진행 중인 리치봉 읽기·후보는 **남긴다**(2026-11-10). 실제 대국에선 손·팔 때문에 장면 전체 변화가 12~23초마다
  /// 나서(11-07: 2차 대국 프레임의 약 40%), 읽기(7~10초)가 끝나기 전에 후보를 지워 리치가 한 번도 확정되지 않았다
  /// (metrics 표 11 11-07 줄). 읽기는 서버가 그 순간 사진으로 하므로 픽셀 기준이 바뀌어도 답은 그대로 쓸 수 있다.
  /// 읽기 횟수 한도에 걸린 후보는 새 기회를 준다(새 장면이니).
  void cameraMoved(DateTime now) {
    for (final r in rivers.values) {
      r
        ..baseline = null
        ..last = null
        ..stable = 0;
    }
    // 픽셀 판정은 프레임마다 새로 보니 이어 본 수는 남기고, 움직임 비교용 띠만 버린다.
    _localLast.clear();
    final st = sticks;
    final keep = st.candidate != null || st.status == StickStatus.reading || st.status == StickStatus.changed;
    st
      ..baseline.clear()
      ..last.clear()
      ..stable = 0
      ..atRead = null;
    if (!keep) {
      st
        ..status = riichi.isEmpty ? StickStatus.idle : StickStatus.confirmed
        ..reads = 0
        ..candidate = null
        ..pendingFrame = null;
    } else if (st.status == StickStatus.unconfirmed) {
      st
        ..status = StickStatus.changed
        ..reads = 0;
    }
    events.add(TrackerEvent(now, Side.bottom, 'rebase', '장면 전체 변화'));
  }

  Map<String, dynamic> toJson() => {
        'frame': frame,
        'rivers': {
          for (final e in rivers.entries)
            e.key.name: {'discards': e.value.discards, 'last': e.value.lastDiscard?.toJson()},
        },
        'riichi': [for (final s in riichi) s.name],
        'riichi_at': {
          for (final e in riichiAt.entries)
            e.key.name: {
              'own': e.value.own,
              'total': e.value.total,
              'taken': e.value.taken,
              'at': e.value.at.toIso8601String(),
              'fresh': e.value.fresh,
            },
        },
        'double_riichi': [for (final s in doubleRiichiCandidates) s.name],
        'ippatsu': [for (final s in ippatsuCandidates()) s.name],
        'sticks': {
          'status': sticks.status.name,
          'reads': sticks.reads,
          if (_seenRun.isNotEmpty) 'seen_run': {for (final e in _seenRun.entries) e.key.name: e.value},
        },
        'events': [for (final e in events) e.toJson()],
      };


  int get _totalDiscards => rivers.values.fold(0, (a, r) => a + r.discards);

  /// 리치봉 띠 변화 직후 그 자리에서 잡힌 버림은 선언패다 — 변화 순간의 수에 넣는다(아직 확정 전이면 [_changeAt],
  /// 이미 확정했으면 [riichiAt]).
  void _lateRiichiTile(Side side, DateTime now) {
    // 픽셀 판정: 봉을 처음 본 순간 뒤 늦게 잡힌 선언패.
    final f = _firstSeen[side];
    if (f != null && now.difference(f.at) <= config.riichiTileLag) {
      _firstSeen[side] = (own: f.own + 1, total: f.total + 1, taken: f.taken, at: f.at, fresh: f.fresh);
      final r = riichiAt[side];
      if (r != null && r.at == f.at) {
        riichiAt[side] = (own: r.own + 1, total: r.total + 1, taken: r.taken, at: r.at, fresh: r.fresh);
      }
      return;
    }
    final c = _changeAt;
    if (c == null || now.difference(c.at) > config.riichiTileLag) return;
    final own = {...c.own, side: (c.own[side] ?? 0) + 1};
    _changeAt = (own: own, total: c.total + 1, taken: c.taken, at: c.at, fresh: c.fresh);
    final r = riichiAt[side];
    if (r != null && r.at == c.at) {
      riichiAt[side] = (own: r.own + 1, total: r.total + 1, taken: r.taken, at: r.at, fresh: r.fresh);
    }
  }

  void _log(DateTime now, Side side, String kind, String detail) => events.add(TrackerEvent(now, side, kind, detail));

  static bool _same(Set<Side> a, Set<Side> b) => a.length == b.length && a.containsAll(b);
}
