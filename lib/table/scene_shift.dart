/// 판 상태 추적의 "장면 전체가 바뀜" 검사. 순수 Dart, API 호출 없음.
///
/// 카메라가 움직이거나(헤드를 놓거나 건드림) 조명·노출이 한꺼번에 바뀌면 모서리·강·리치봉 띠가 **동시에** 바뀐다.
/// 추적기는 칸마다 따로 보므로 이걸 울기·버림으로 읽어 서버를 부르고 헛 버림을 남겼다(2026-10-28 실기기, metrics 표 8:
/// 폰을 놓는 동안 2분 41초에 모서리 읽기 20회·헛 버림 16개, 고정하면 0회·4개). 그런 프레임이면 추적기는 사건을 내지 않고
/// 기준만 다시 잡는다([MeldTracker.cameraMoved]·[RiverTracker.cameraMoved]).
///
/// 손과 구별하는 법: 강 띠 네 개가 모두 탁자 가운데에서 시작해서, 가운데로 뻗은 손 하나가 강 4·리치봉 띠 4 를 한꺼번에
/// 건드릴 수 있다. 그래서 칸 수만 보지 않는다.
/// - **움직임:** 바뀐 칸이 [SceneShiftConfig.minZones] 이상이고, 그중 탁자 가장자리에 흩어진 **모서리 칸이
///   [SceneShiftConfig.minCorners] 개 이상**(손 하나는 모서리 하나밖에 못 가린다).
/// - **밝기:** 강 띠 안 블록 대부분([SceneShiftConfig.blockFrac])이 같은 방향으로 밝아지거나 어두워진 강 띠가
///   [SceneShiftConfig.minBrightRivers] 개 이상(손은 강 띠의 가운데 쪽 일부만 가린다).
/// 문턱은 `experiments/tracking/shift_check.dart` 로 잰 것(실제 폰 고정 프레임 + 합성 게임 시퀀스 = 헛 판정 0,
/// 장면 D·C 이동 0.5~4%·회전 1°·밝기 ±10% = 판정).
library;

import 'river_change.dart';
import 'table_layout.dart';

class SceneShiftConfig {
  /// 모서리 칸 하나가 바뀌었다고 보는 [CornerStats.diff](추적기 움직임 문턱과 같음).
  final double cornerMove;

  /// 강·리치봉 띠 하나가 바뀌었다고 보는 [ZoneSnapshot.diff](추적기 움직임 문턱과 같음).
  final double zoneMove;

  /// 12칸(모서리 4 + 강 4 + 리치봉 띠 4) 중 이만큼 함께 바뀌고, 모서리가 [minCorners] 개 이상이면 움직임.
  final int minZones;
  final int minCorners;

  /// 블록 하나의 밝기가 바뀌었다고 보는 차(0~255).
  final int blockDelta;

  /// 강 띠 하나의 블록 중 이 비율 이상이 같은 방향으로 바뀌면 그 띠는 밝기가 바뀐 것.
  final double blockFrac;

  /// 같은 방향으로 밝기가 바뀐 강 띠가 이만큼이면 조명·노출 변화.
  final int minBrightRivers;

  const SceneShiftConfig({
    this.cornerMove = 0.03,
    this.zoneMove = 0.03,
    this.minZones = 7,
    this.minCorners = 2,
    this.blockDelta = 3,
    this.blockFrac = 0.7,
    this.minBrightRivers = 3,
  });
}

/// 블록 중 밝아진 비율, 어두워진 비율(각각 [blockDelta] 이상). 모양이 다르면 (0, 0).
(double, double) blockShift(ZoneSnapshot prev, ZoneSnapshot cur, {int blockDelta = 3}) {
  if (prev.cols != cur.cols || prev.rows != cur.rows || cur.gray.isEmpty) return (0, 0);
  var up = 0, down = 0;
  for (var i = 0; i < cur.gray.length; i++) {
    final d = cur.gray[i] - prev.gray[i];
    if (d >= blockDelta) up++;
    if (d <= -blockDelta) down++;
  }
  return (up / cur.gray.length, down / cur.gray.length);
}

/// 같은 방향으로 밝기가 바뀐 강 띠 수(많은 쪽 방향, 0~4).
int brightShiftedRivers(TableFrameStats prev, TableFrameStats cur, {SceneShiftConfig config = const SceneShiftConfig()}) {
  var up = 0, down = 0;
  for (final s in Side.values) {
    final p = prev.rivers[s], c = cur.rivers[s];
    if (p == null || c == null) continue;
    final (u, d) = blockShift(p, c, blockDelta: config.blockDelta);
    if (u >= config.blockFrac) up++;
    if (d >= config.blockFrac) down++;
  }
  return up > down ? up : down;
}

/// 직전 프레임 대비 바뀐 모서리 칸 수(0~4).
int changedCorners(TableFrameStats prev, TableFrameStats cur, {SceneShiftConfig config = const SceneShiftConfig()}) {
  var n = 0;
  for (final s in Side.values) {
    final p = prev.corners[s], c = cur.corners[s];
    if (p != null && c != null && c.diff(p) > config.cornerMove) n++;
  }
  return n;
}

/// 직전 프레임 대비 바뀐 칸 수(0~12).
int changedZones(TableFrameStats prev, TableFrameStats cur, {SceneShiftConfig config = const SceneShiftConfig()}) {
  var n = changedCorners(prev, cur, config: config);
  for (final s in Side.values) {
    final pr = prev.rivers[s], cr = cur.rivers[s];
    if (pr != null && cr != null && cr.diff(pr) > config.zoneMove) n++;
    final ps = prev.strips[s], cs = cur.strips[s];
    if (ps != null && cs != null && cs.diff(ps) > config.zoneMove) n++;
  }
  return n;
}

/// 직전 프레임을 들고 있다가 새 프레임이 장면 전체 변화인지 알려 준다.
class SceneShiftGate {
  final SceneShiftConfig config;
  TableFrameStats? _prev;

  /// 마지막 검사의 바뀐 칸 수·모서리 수·밝기 바뀐 강 띠 수(기록용).
  int lastChanged = 0;
  int lastCorners = 0;
  int lastBright = 0;

  SceneShiftGate({this.config = const SceneShiftConfig()});

  /// 두 프레임이 장면 전체 변화인지(기록 없이).
  bool judge(TableFrameStats prev, TableFrameStats cur) {
    lastChanged = changedZones(prev, cur, config: config);
    lastCorners = changedCorners(prev, cur, config: config);
    lastBright = brightShiftedRivers(prev, cur, config: config);
    return (lastChanged >= config.minZones && lastCorners >= config.minCorners) ||
        lastBright >= config.minBrightRivers;
  }

  /// [cur] 를 다음 비교 기준으로 남기고, 직전 프레임 대비 장면 전체가 바뀌었으면 true. 첫 프레임은 false.
  bool check(TableFrameStats cur) {
    final prev = _prev;
    _prev = cur;
    if (prev == null) {
      lastChanged = lastCorners = lastBright = 0;
      return false;
    }
    return judge(prev, cur);
  }

  /// 격자를 바꾸면 비교 기준을 버린다.
  void reset() {
    _prev = null;
    lastChanged = lastCorners = lastBright = 0;
  }

  String get summary => '칸 $lastChanged·모서리 $lastCorners·밝기 강 $lastBright';
}
