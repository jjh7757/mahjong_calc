/// 판 상태 추적 1단계: 자리별 울기 묶음을 게임 중에 미리 읽어 둔다. 순수 Dart, I/O 없음.
///
/// 쓰는 쪽(거치 화면)이 3초마다 모서리 통계([CornerStats])를 [MeldTracker.onFrame] 에 넣으면 "이 자리 모서리를 읽어라"
/// ([TrackerAction])를 돌려주고, 읽은 결과를 [MeldTracker.onRead] 에 넣으면 확정 규칙에 따라 상태를 바꾼다.
/// 화료 때는 [MeldTracker.trackedMelds] 가 null 이 아닌 자리만 손패 전용 읽기를 쓰고, 나머지는 지금 방식으로 간다.
///
/// 자리 하나의 상태:
/// ```
/// idle ──(연속 프레임 차이 큼)──▶ moving ──(두 프레임 안정)──▶ 기준과 패 1장 이상 다름? ──예──▶ changed
///   ▲                                                              │아니오                       │읽기 요청
///   └──────────────────────────────────────────────────────────────┘                       ▼
/// confirmed ◀──(두 읽기 일치, 또는 픽셀 장수와 맞음)── reading ──(불일치)──▶ changed(다시) ──(3번 다 다름)──▶ unconfirmed
/// ```
/// 확정 규칙(설계 1절): 다른 프레임의 두 읽기가 같아야 확정. 비용을 줄이려고(사용자 지적: 울 때마다 호출이 는다)
/// 읽은 장수가 픽셀 어림과 맞으면 한 번으로 확정한다([TrackerConfig.pixelShortcut]). 확정된 묶음 수보다 적게 읽히면
/// 가림으로 보고 받지 않는다(울기는 판 안에서 사라지지 않는다).
/// 설계: docs/state_tracking_design.md.
library;

import 'corner_change.dart';
import 'observation.dart';
import 'table_layout.dart';

enum TrackStatus { idle, moving, changed, reading, confirmed, unconfirmed }

class TrackerConfig {
  /// 연속 프레임 차이([CornerStats.diff])가 이 이상이면 움직이는 중(손·팔).
  final double moveThreshold;

  /// 기준(마지막 확정 때) 대비 흰 면 변화가 패 몇 장 이상이면 "변화".
  final double changeTiles;

  /// 변화로 보려면 같은 프레임이 몇 번 이어져야 하나.
  final int stableFrames;

  /// 같은 자리 읽기 사이 최소 간격(호출 예산).
  final Duration minReadGap;

  /// 한 변화에 읽기 최대 몇 번. 넘으면 unconfirmed.
  final int maxReadsPerChange;

  /// 일치해야 하는 읽기 수. 1 이면 한 번에 확정.
  final int confirmReads;

  /// 읽은 패 장수가 픽셀 어림([CornerStats.tiles])과 [shortcutTolerance] 안이면 한 번으로 확정.
  final bool pixelShortcut;
  final double shortcutTolerance;

  final int maxMelds;

  const TrackerConfig({
    this.moveThreshold = 0.03,
    this.changeTiles = 1.0,
    this.stableFrames = 2,
    this.minReadGap = const Duration(seconds: 5),
    this.maxReadsPerChange = 3,
    this.confirmReads = 2,
    this.pixelShortcut = true,
    this.shortcutTolerance = 0.75,
    this.maxMelds = 4,
  });
}

/// "이 자리 모서리를 지금 프레임 기준으로 읽어라". [frame] 은 [MeldTracker.onRead] 에 그대로 돌려준다.
class TrackerAction {
  final Side side;
  final int frame;
  const TrackerAction(this.side, this.frame);

  @override
  String toString() => 'read(${side.name}@$frame)';
}

/// 기록용 사건(촬영 기록 폴더에 남긴다).
class TrackerEvent {
  final DateTime at;
  final Side side;
  final String kind;
  final String detail;
  const TrackerEvent(this.at, this.side, this.kind, this.detail);

  Map<String, dynamic> toJson() => {'at': at.toIso8601String(), 'side': side.name, 'kind': kind, 'detail': detail};

  @override
  String toString() => '${side.name} $kind $detail';
}

class TrackedSeat {
  TrackStatus status = TrackStatus.idle;

  /// 마지막으로 확정한 울기.
  List<ObservedMeld> melds = const [];
  DateTime? confirmedAt;

  /// 확정 뒤 모서리가 또 바뀌었다(아직 새로 확정 못 함). 그동안 [melds] 는 믿지 않는다.
  bool changedSinceConfirm = false;

  CornerStats? baseline;
  CornerStats? last;
  int stable = 0;
  int readsForChange = 0;
  List<ObservedMeld>? candidate;
  DateTime? lastReadAt;
  int? pendingFrame;
  CornerStats? statsAtRead;

  int get readTileCount => melds.fold(0, (a, m) => a + m.tiles.length);
}

class MeldTracker {
  final TrackerConfig config;

  /// 자리별 패 한 장의 모서리 칸 비율([tileFracOf]).
  final Map<Side, double> tileFrac;

  final Map<Side, TrackedSeat> seats = {for (final s in Side.values) s: TrackedSeat()};
  final List<TrackerEvent> events = [];
  int frame = 0;

  MeldTracker({required this.tileFrac, this.config = const TrackerConfig()});

  TrackedSeat seat(Side side) => seats[side]!;

  /// 화료 때 믿고 쓸 울기. 확정됐고 그 뒤 변화가 없을 때만. 아니면 null(지금 방식으로 자리 전체를 읽는다).
  List<ObservedMeld>? trackedMelds(Side side) {
    final t = seat(side);
    return t.status == TrackStatus.confirmed && !t.changedSinceConfirm ? t.melds : null;
  }

  /// 새 프레임의 통계. 돌려준 행동마다 모서리를 읽어 [onRead]/[onReadFailed] 로 알려 준다.
  List<TrackerAction> onFrame(Map<Side, CornerStats> stats, DateTime now) {
    frame++;
    final actions = <TrackerAction>[];
    for (final e in stats.entries) {
      final side = e.key, cur = e.value, t = seat(side);
      final prev = t.last;
      t.last = cur;
      if (t.baseline == null || prev == null) {
        // 첫 프레임이 기준. 이미 울기가 있어도 "변화 없음" 으로 시작한다(지금 방식이 화료 때 읽는다).
        t.baseline = cur;
        t.stable = 1;
        continue;
      }
      if (cur.diff(prev) > config.moveThreshold) {
        t.stable = 0;
        // 읽는 중이거나 후보를 들고 있는 변화(changed)는 그대로 둔다 — 손이 지나갔다고 후보를 버리면
        // 같은 울기를 처음부터 다시 세어 확정이 한 번 더 늦어진다(노트북 흐름 확인에서 발견).
        if (t.status != TrackStatus.reading && t.status != TrackStatus.changed) t.status = TrackStatus.moving;
        continue;
      }
      // stable = 직전 프레임과 같았던 횟수. 1 이면 이미 두 프레임이 같다.
      t.stable++;
      if (t.stable < config.stableFrames - 1 || t.status == TrackStatus.reading) continue;

      final frac = tileFrac[side] ?? 0;
      final changeTiles = frac <= 0 ? 0.0 : (cur.white - t.baseline!.white).abs() / frac;
      final pendingChange = t.status == TrackStatus.changed || (t.status == TrackStatus.unconfirmed && t.candidate != null);
      if (changeTiles < config.changeTiles && !pendingChange) {
        // 손이 지나갔을 뿐. 이전 상태로.
        if (t.status == TrackStatus.moving) {
          t.status = t.melds.isNotEmpty && !t.changedSinceConfirm ? TrackStatus.confirmed : TrackStatus.idle;
        }
        continue;
      }
      if (t.status == TrackStatus.unconfirmed && changeTiles < config.changeTiles) continue;

      if (!pendingChange) {
        // 새 변화.
        t.readsForChange = 0;
        t.candidate = null;
        if (t.status == TrackStatus.confirmed || t.melds.isNotEmpty) t.changedSinceConfirm = true;
        t.status = TrackStatus.changed;
        _log(now, side, 'changed', '${changeTiles.toStringAsFixed(1)}장 분량');
      }
      if (t.lastReadAt != null && now.difference(t.lastReadAt!) < config.minReadGap) continue;
      if (t.readsForChange >= config.maxReadsPerChange) {
        if (t.status != TrackStatus.unconfirmed) _log(now, side, 'unconfirmed', '읽기 ${t.readsForChange}번 불일치');
        t.status = TrackStatus.unconfirmed;
        continue;
      }
      t.status = TrackStatus.reading;
      t.pendingFrame = frame;
      t.statsAtRead = cur;
      t.lastReadAt = now;
      t.readsForChange++;
      actions.add(TrackerAction(side, frame));
    }
    return actions;
  }

  /// [frame] 프레임 요청의 읽기 결과. 다른 프레임의 늦은 답은 무시한다.
  void onRead(Side side, int frame, List<ObservedMeld> read, DateTime now) {
    final t = seat(side);
    if (t.status != TrackStatus.reading || t.pendingFrame != frame) return;
    final melds = read.take(config.maxMelds).toList();
    final key = _key(melds);
    final stats = t.statsAtRead ?? t.last ?? CornerStats.empty;
    final frac = tileFrac[side] ?? 0;

    // 울기는 판 안에서 사라지지 않는다: 확정된 것보다 적게 읽혔으면 가림·오독으로 보고 다시 읽는다.
    final fewer = t.changedSinceConfirm && melds.length < t.melds.length;
    final agree = t.candidate != null && _key(t.candidate!) == key;
    final readTiles = melds.fold(0, (a, m) => a + m.tiles.length);
    final pixelTiles = frac <= 0 ? -1.0 : stats.tiles(frac);
    final shortcut = config.pixelShortcut && pixelTiles >= 0 && (readTiles - pixelTiles).abs() <= config.shortcutTolerance;
    final enough = agree || config.confirmReads <= 1 || shortcut;

    if (!fewer && enough) {
      t.melds = melds;
      t.confirmedAt = now;
      t.status = TrackStatus.confirmed;
      t.changedSinceConfirm = false;
      t.baseline = stats;
      t.candidate = null;
      t.readsForChange = 0;
      _log(now, side, 'confirmed', '$key (${agree ? '두 읽기 일치' : shortcut ? '픽셀 장수 일치 ${pixelTiles.toStringAsFixed(1)}' : '한 번'})');
      return;
    }
    t.candidate = fewer ? null : melds;
    _log(now, side, fewer ? 'fewer' : 'candidate', key);
    t.status = t.readsForChange >= config.maxReadsPerChange ? TrackStatus.unconfirmed : TrackStatus.changed;
    if (t.status == TrackStatus.unconfirmed) _log(now, side, 'unconfirmed', '읽기 ${t.readsForChange}번 불일치');
  }

  void onReadFailed(Side side, int frame, DateTime now, [String reason = '']) {
    final t = seat(side);
    if (t.status != TrackStatus.reading || t.pendingFrame != frame) return;
    _log(now, side, 'failed', reason);
    t.status = t.readsForChange >= config.maxReadsPerChange ? TrackStatus.unconfirmed : TrackStatus.changed;
  }

  /// 사용자가 칩을 눌러 다시 읽기를 요청. 다음 안정 프레임에서 읽고, 그동안 예전 확정값은 믿지 않는다.
  void requestReread(Side side, DateTime now) {
    final t = seat(side);
    if (t.status == TrackStatus.reading) return;
    t.status = TrackStatus.changed;
    t.candidate = null;
    t.readsForChange = 0;
    t.lastReadAt = null;
    if (t.melds.isNotEmpty) t.changedSinceConfirm = true;
    _log(now, side, 'reread', '사용자 요청');
  }

  /// 사용자가 지움: 그 자리 추적을 버리고 다음 프레임을 새 기준으로.
  void clear(Side side, DateTime now) {
    seats[side] = TrackedSeat();
    _log(now, side, 'clear', '사용자');
  }

  /// 새 판(화료·유국 기록 뒤). 네 자리 모두 비우고 다음 프레임을 새 기준으로 삼는다.
  void reset(DateTime now, [String reason = '새 판']) {
    for (final s in Side.values) {
      seats[s] = TrackedSeat();
    }
    events.add(TrackerEvent(now, Side.bottom, 'reset', reason));
  }

  /// 카메라가 움직였다(펠트 IoU 검사). 추적을 버린다.
  void cameraMoved(DateTime now) => reset(now, '카메라 움직임');

  Map<String, dynamic> toJson() => {
        'frame': frame,
        'seats': {
          for (final e in seats.entries)
            e.key.name: {
              'status': e.value.status.name,
              'melds': [for (final m in e.value.melds) m.toJson()],
              'confirmed_at': e.value.confirmedAt?.toIso8601String(),
              'changed_since_confirm': e.value.changedSinceConfirm,
              'reads_for_change': e.value.readsForChange,
            },
        },
        'events': [for (final e in events) e.toJson()],
      };

  void _log(DateTime now, Side side, String kind, String detail) => events.add(TrackerEvent(now, side, kind, detail));

  /// 묶음 목록을 비교용 문자열로(순서 무관, 묶음 안 패는 정렬).
  static String _key(List<ObservedMeld> melds) {
    final parts = [
      for (final m in melds) '${m.type.name}:${([for (final t in m.tiles) t.code]..sort()).join()}',
    ]..sort();
    return parts.join(' ');
  }
}
