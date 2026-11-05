/// 거치 촬영 한 장을 끝까지 읽는다: locate → 화료자 자리 결정 → 구역 크롭 → 손패·중앙 병렬 호출.
/// 순수 Dart. 무거운 이미지 처리는 [ImageOps] 로 바꿔 끼워 isolate 에서 돌릴 수 있다.
library;

import 'dart:async';
import 'dart:typed_data';

import '../services/recognizer_client.dart';
import 'cropper.dart' as cropper;
import 'cropper.dart' show CropSpec;
import 'fixed_layout.dart';
import 'grid_zones.dart';
import 'observation.dart';
import 'rectify.dart' show FeltQuad, standardGrid;
import 'river_tracker.dart' show Discard;
import 'shot_image.dart';
import 'table_layout.dart';
import 'table_reading.dart';
import 'wide_seat.dart';

typedef ShrinkFn = Future<Uint8List> Function(Uint8List original);
typedef CropManyFn = Future<List<Uint8List>> Function(Uint8List original, List<CropSpec> specs);
typedef AnalyzeFn = Future<ShotAnalysis> Function(Uint8List small, FixedTable fixed);
typedef AnalyzeGridFn = Future<ShotAnalysis> Function(Uint8List small, GridZones grid);
typedef OpenShotFn = Future<ShotImage> Function(Uint8List original);

/// 자체 모델 표시패 찾기를 이 시간까지만 기다린다. 넘으면 Gemini 답을 쓴다.
const _localDoraTimeout = Duration(seconds: 10);

/// [openShot] 은 격자 판독([TableReader.readGrid])이 원본을 한 번만 디코딩해 축소본·크롭을 만들 때 쓴다.
class ImageOps {
  final ShrinkFn shrink;
  final CropManyFn cropMany;
  final AnalyzeFn analyze;
  final AnalyzeGridFn analyzeGrid;
  final OpenShotFn openShot;
  const ImageOps({
    required this.shrink,
    required this.cropMany,
    this.analyze = _analyzeSync,
    this.analyzeGrid = _analyzeGridSync,
    this.openShot = _openDirect,
  });

  static Future<Uint8List> _shrinkSync(Uint8List o) async => cropper.shrinkForLocate(o);
  static Future<List<Uint8List>> _cropSync(Uint8List o, List<CropSpec> s) async => cropper.cropMany((o, s));
  static Future<ShotAnalysis> _analyzeSync(Uint8List small, FixedTable f) async => analyzeShot((small, f));
  static Future<ShotAnalysis> _analyzeGridSync(Uint8List small, GridZones g) async => analyzeGridShot((small, g));
  static Future<ShotImage> _openDirect(Uint8List o) async => DirectShotImage(o);
  static const ImageOps direct = ImageOps(shrink: _shrinkSync, cropMany: _cropSync);
}

/// 같은 요청을 헤지로 한 번 더: [first] 가 [after] 안에 답하지 않거나 먼저 실패하면 [second] 를 보내고, 먼저 성공한 답을 쓴다.
/// 둘 다 실패하면 나중 오류. [after] 가 null 이면 [first] 만. 진 쪽의 결과·오류는 버린다(처리되지 않은 오류 없음).
Future<T> hedged<T>(Future<T> Function() first, Future<T> Function() second, Duration? after, {void Function()? onHedge}) {
  final f1 = first();
  if (after == null) return f1;
  final done = Completer<T>();
  Future<T>? f2;
  var failed = 0;
  void fail(Object e, StackTrace st) {
    failed++;
    if (failed == 2 && !done.isCompleted) done.completeError(e, st);
  }

  void start2() {
    if (f2 != null || done.isCompleted) return;
    onHedge?.call();
    f2 = second()
      ..then((v) {
        if (!done.isCompleted) done.complete(v);
      }, onError: fail);
  }

  final timer = Timer(after, start2);
  f1.then((v) {
    timer.cancel();
    if (!done.isCompleted) done.complete(v);
  }, onError: (Object e, StackTrace st) {
    timer.cancel();
    if (f2 == null) {
      // 먼저 실패했으면 바로 한 번 더. 그것도 실패하면 그 오류.
      failed++;
      start2();
      return;
    }
    fail(e, st);
  });
  return done.future;
}

/// 읽기 단계. 진행 표시용.
enum ReadStage { decoding, locating, cropping, reading }

extension ReadStageX on ReadStage {
  String get label => const ['사진 준비 중', '테이블 구역 찾는 중', '구역 자르는 중', '손패·중앙 읽는 중'][index];
}

/// 읽는 동안 생긴 중간 산출물. 촬영 기록 저장(데이터셋)과 디버깅용. 넘기면 채워진다.
class TableReadTrace {
  /// 봉이 남은 자리의 강에 눕힌 패가 있는지([TableReading.riverSideways]). 매장에서 맞는지 보려고 기록에 남긴다.
  Map<Side, bool?> riverSideways = const {};

  /// 넓은 구역 판독 응답(`/v2/seatwide`, 그 답을 썼을 때만). 미리 보냈는데 안 쓴 호출은 [callMs] 의 seatwide_* 에만 남는다.
  Map<String, dynamic>? wide;

  /// 넓은 구역 판독을 자리 판독과 같은 순간에 미리 보냈나(`readGrid(wideEarly:)`).
  bool wideEarly = false;

  /// 미리 보낸 넓은 판독 답을 손패엔 안 쓰고 리치 화료의 표시패를 위해 기다렸나(`readGrid(wideIndicators:)`).
  bool wideForDora = false;

  /// 강 끝 판독을 헤지로 한 번 더 보냈나(`readGrid(lastHedge:)`). 시간은 [callMs] 의 last3·last3_hedge.
  bool lastHedged = false;
  Uint8List? small;
  Uint8List? handCrop;
  Uint8List? centerCrop;

  /// 왕패(도라 표시패) 구역만 잘라 낸 것. locate 가 dead_wall 을 찾았을 때만.
  Uint8List? wallCrop;

  /// 선 기준 도라 구역 크롭([GridZones.doraZone], 선 쪽으로 세운 것). 없으면 null.
  Uint8List? dealerDoraCrop;

  /// 자체 모델 표시패 찾기 응답(`readGrid(localDora:)`). 부르지 않았거나 실패하면 null.
  Map<String, dynamic>? localDora;
  TableLayout? layout;
  Side? winnerSide;
  HandReading? hand;
  CenterReading? center;

  /// [wallCrop] 을 따로 읽은 결과(도라·뒷도라만 쓴다).
  CenterReading? wall;

  /// 화료자 울기 묶음 크롭(locate 의 melds 상자).
  List<Uint8List> meldCrops = const [];

  /// 자리별 강 크롭(그 자리 사람 방향으로 세운 것).
  Map<Side, Uint8List> riverCrops = const {};

  /// 모델이 본 것을 모은 관찰 JSON. 판단 전 원본.
  TableObservation? observation;

  /// 단계별 걸린 시간(ms): shrink, analyze(고정 구역), locate, pick, crop, read.
  final Map<String, int> timingsMs = {};

  /// 구역을 어디서 얻었나: locate · fixed(고정 구역, locate 생략) · fixed→locate(고정 구역으로 읽었는데 장수가 안 맞아 다시)
  /// · grid(미리 그은 격자, [TableReader.readGrid]).
  String layoutMode = 'locate';

  /// 고정 구역 픽셀 판정 결과.
  ShotAnalysis? analysis;

  /// 서버 호출별 걸린 시간(ms). 이름은 보낸 파일 이름(seat_bottom, handonly_bottom, last3 …).
  final Map<String, int> callMs = {};

  /// 서버 응답의 단계별 시간(`timing`: handler_ms·decode_ms·queue_ms·prep_ms·gate_ms·gemini_ms). 이름은 [callMs] 와 같다.
  final Map<String, Map<String, dynamic>> serverTiming = {};

  /// 서버 자체 모델 그림자 답(`local`, 판독에는 안 쓰고 다음 매장에서 Gemini 와 비교한다). 이름은 [callMs] 와 같다.
  final Map<String, Map<String, dynamic>> localShadow = {};

  void _recordCall(String name, int ms, Map<String, dynamic> response) {
    callMs[name] = ms;
    if (response['timing'] case final Map<String, dynamic> t) serverTiming[name] = t;
    if (response['local'] case final Map<String, dynamic> l) localShadow[name] = l;
  }

  /// 그림자 모드로 두 방식을 같이 읽은 자리의 두 답(기록용).
  final Map<Side, ShadowRead> shadow = {};

  /// 추적 자리를 어떻게 읽었나: handonly(손패 칸만) · fallback_seat(장수가 안 맞아 자리 전체를 다시 읽음).
  final Map<Side, String> trackedMode = {};

  /// 눕힌 손패 둘을 묻지 않고 더블론으로 정했는지([TableReader.readGrid] 의 acceptAll).
  bool autoMultiRon = false;

  /// 사진을 펴서 읽었으면 찾은 펠트 네 모서리(원본 사진 정규화 좌표). 펴기를 껐거나 펠트를 못 찾으면 null.
  FeltQuad? feltQuad;
}

/// 그림자 모드: 같은 사진의 한 자리를 손패 전용(/v2/handonly)과 자리 전체(/v2/seat)로 동시에 읽은 두 답. 기록용(설계 7절).
class ShadowRead {
  final Map<String, dynamic> handonly;
  final Map<String, dynamic> seat;
  final int? handonlyMs;
  final int? seatMs;
  const ShadowRead({required this.handonly, required this.seat, this.handonlyMs, this.seatMs});

  Map<String, dynamic> toJson() => {'handonly': handonly, 'seat': seat, 'handonly_ms': handonlyMs, 'seat_ms': seatMs};
}

/// 손패를 읽을 자리를 못 정했을 때. [layout] 은 그래도 돌려준다(화면에 상자를 그리기 위해).
class TableReadException implements Exception {
  final String message;
  final TableLayout? layout;
  const TableReadException(this.message, {this.layout});
  @override
  String toString() => message;
}

class TableReader {
  final RecognizerClient client;
  final ImageOps ops;
  const TableReader(this.client, {this.ops = ImageOps.direct});

  /// [winnerSide] 를 주면 그 자리를 읽고, 없으면 눕힌 자리가 하나일 때 자동, 둘 이상이면 [pickWinner] 로 묻는다.
  /// 중앙 읽기가 실패해도 손패만으로 계속하고 [TableReading.warnings] 에 남긴다.
  ///
  /// [fixed] 를 주면 locate 대신 그 구역을 쓴다([FixedTable]). 카메라가 움직였거나 앞면 손패를 못 찾았으면 locate 하고,
  /// 고정 구역으로 읽은 손패 장수가 안 맞으면 locate 로 한 번 더 읽는다.
  Future<TableReading> read(
    Uint8List original, {
    Side? winnerSide,
    Future<Side?> Function(List<Side> candidates)? pickWinner,
    void Function(ReadStage stage)? onStage,
    TableReadTrace? trace,
    FixedTable? fixed,
  }) async {
    if (fixed != null) {
      final r = await _read(original, winnerSide, pickWinner, onStage, trace, fixed);
      if (r != null) return r;
      trace?.layoutMode = 'fixed→locate';
    }
    return (await _read(original, winnerSide, pickWinner, onStage, trace, null))!;
  }

  /// 미리 그은 격자([GridZones]) 5구역으로 읽는다. locate 없이 구역마다 잘라 동시에 부른다.
  /// - 화료자 자리(손패 + 오른쪽 모서리) → /v2/seat: 앞면 여부, 손패, 떨어진 한 장, 울기 전부, 따로 놓인 앞면 패.
  ///   화료자는 자리 구역 픽셀(뒷면 연보라가 없는 자리)로 정하고, 못 정하면 네 자리를 모두 읽어 모델의 앞면 답으로 정한다.
  ///   그래도 하나가 아니면 [pickWinners] 로 묻는다. 여럿을 고르면(동시 론) 첫 자리가 대표, 나머지는 [TableReading.others].
  ///   둘일 때 [acceptAll] 이 두 자리의 판독을 받아들이면 묻지 않고 둘 다 화료자로 한다(더블론 자동 판정).
  /// - 가운데: 다른 자리 쪽을 각각 그 사람 방향으로 세워 강의 **마지막 패 한 장만**, 여러 자리를 한 번에 /v2/last3(누가 쏘였나).
  /// - 리치: 가운데 기기 둘레의 **리치봉만** /v2/sticks. 강의 가로 패는 보지 않는다.
  /// - 도라: 가운데 칸 전체를 /v2/dora 로 읽은 것과 화료자 자리의 따로 놓인 앞면 패(없으면 울기 모양이 아닌 묶음)를
  ///   둘 다 넘긴다. 리치 화료면 손패 옆, 아니면 가운데를 먼저 쓴다(merge, 매장 관행).
  ///
  /// [splitSeat] 이면 자리 구역을 손패 칸([GridZones.handCell], /v2/seat)과 오른쪽 모서리 칸([GridZones.cornerCell],
  /// /v2/corner)으로 나눠 따로 보낸다(실험: 크롭이 작아 패가 크게 들어가는 대신 경계에 걸친 패를 놓칠 수 있다).
  ///
  /// [tracked] 는 판 상태 추적이 게임 중에 확정한 자리별 울기. 그 자리는 손패 칸만 /v2/handonly 로 읽고 울기를 채운다.
  /// 손패 장수가 울기와 맞지 않으면 자리 전체를 /v2/seat 로 다시 읽는다(지금 방식으로 복귀). [shadow] 면 처음부터
  /// 둘 다 보내 두 답을 [TableReadTrace.shadow] 에 남긴다(결과는 손패 전용 쪽, 실험용 — 설계 docs/state_tracking_design.md 7절).
  ///
  /// [rectify] 면 먼저 펠트 네 모서리로 사진을 펴서 작탁(+ 둘레 흰 테두리)만 남기고 [standardGrid] 로 나눈다(사용자 제안
  /// 2026-10-28 "처음 자를 때 작탁만"; 기운 탁자도 축에 맞는 격자로). 펠트를 못 찾으면 [grid] 그대로. 편 사진에서는 원본 좌표인
  /// [trackedDiscard] 의 위치를 쓰지 않는다(자리만 방총자 힌트로).
  ///
  /// [useWide] 면 화료자를 알 때 테이블 절반도 잘라 두고, 자리 판독이 장수·패 모양으로 안 맞을 때 `/v2/seatwide` 로 떼어 둔 패·
  /// 모서리 울기를 찾는다(`wide_seat.dart`). [wideEarly] 면 그 호출을 자리 판독과 **같은 순간에 미리** 보내고 필요할 때만 답을 쓴다
  /// — 필요한 장면에서 넓은 판독 시간(운영 중앙 10초)이 자리·강 판독에 가려지는 대신, 안 필요한 장면은 호출 하나(입력 약 19k 토큰)를
  /// 버린다. 기본 켬(2026-11-01 같은 순간 비교, metrics 표 1-11: 매장 오후 중앙 16.2 → 10.3초·짝 차이 −5.6초, 정답은 같은 범위).
  /// [wideIndicators] 면 리치 화료자의 손패 옆에 따로 놓인 패가 없을 때 미리 보낸 넓은 판독의 표시패 짝(서버 `pair`, 2~4장)을 탁자에
  /// 내놓은 도라·뒷도라 표시패로 넘긴다([CenterReading.handSideIndicators], merge 가 리치면 먼저 쓴다).
  /// [lastHedge] 는 강 끝(`/v2/last3`) 헤지: 그 시간 안에 답이 없거나 먼저 실패하면 같은 요청을 한 번 더 보내 먼저 온 답을 쓴다
  /// (null 이면 안 함). 자리 판독에는 쓰지 않는다(경주는 손패 정확도를 깎았다, metrics 표 2-2).
  Future<TableReading> readGrid(
    Uint8List original,
    GridZones grid, {
    bool rectify = false,
    bool splitSeat = false,
    bool useWide = true,
    bool wideEarly = true,
    bool wideIndicators = true,
    Duration? lastHedge = const Duration(seconds: 12),
    Map<Side, List<ObservedMeld>> tracked = const {},
    bool shadow = false,
    Set<Side> trackedRiichi = const {},
    Set<Side> trackedDoubleRiichi = const {},
    Set<Side> trackedIppatsu = const {},
    Set<Side> carriedSticks = const {},
    Discard? trackedDiscard,
    Side? winnerSide,
    Side? dealer,
    // 판 중 프레임 투표로 확정한 도라 표시패(`DoraTracker.confirmed`). merge 로 넘겨 화료 사진 답을 검증·보충한다.
    ReadTile? trackedDora,
    bool localDora = true,
    bool localOnly = false,
    bool useRoles = false,
    bool geminiSticks = false,
    Future<List<Side>?> Function(List<Side> candidates)? pickWinners,
    bool Function(List<TableReading> readings)? acceptAll,
    void Function(ReadStage stage)? onStage,
    TableReadTrace? trace,
  }) async {
    final sw = Stopwatch()..start();
    void lap(String name) {
      trace?.timingsMs[name] = sw.elapsedMilliseconds;
      sw.reset();
    }

    trace?.layoutMode = 'grid';
    onStage?.call(ReadStage.decoding);
    // 원본은 한 번만 디코딩한다(축소본·크롭을 같은 이미지에서). 다 자르면 바로 놓는다.
    final shot = await ops.openShot(original);
    var rectified = false;
    if (rectify) {
      try {
        final q = await shot.rectify();
        trace?.feltQuad = q;
        if (q != null) {
          grid = standardGrid.copyWith(doraRel: grid.doraRel);
          rectified = true;
        }
      } catch (_) {
        // 펴기가 깨져도 원본 그대로 읽는다.
      }
      lap('rectify');
    }
    final Uint8List small;
    final ShotAnalysis a;
    final Map<Side, Uint8List> seatCrops, cornerCrops, lastCrops;
    Uint8List? sticksCrop, doraCrop, trackedCrop, dealerDoraCrop, wideCrop;
    // 역할 경로는 자리 크롭 대신 원본을 보내고, 자체 모델만이면 리치봉(geminiSticks 아니면)·도라 칸도 보내지 않으니 자르지 않는다.
    // 그만큼 강 끝 크롭이 빨리 끝나 장면 끝을 정하는 `/v2/locallast3` 가 먼저 나간다(metrics 표 1-81).
    final roleSeats = localOnly && useRoles;
    final needSticks = !localOnly || geminiSticks;
    final needDora = !localOnly;
    final trackedBox = rectified || localOnly ? null : trackedDiscard?.box;
    final trackSide = trackedDiscard?.side;
    final warnings = <String>[];
    final usage = <String, Map<String, int>>{};
    Future<Map<String, dynamic>?> call(String kind, Uint8List? bytes, String name,
        {bool required = false, Map<String, String>? query}) {
      if (bytes == null) return Future.value(null);
      final t = Stopwatch()..start();
      final f = client.observe(kind, bytes, filename: '$name.jpg', query: query).then<Map<String, dynamic>?>((j) {
        trace?._recordCall(name, t.elapsedMilliseconds, j);
        usage[name] = parseUsage(j['usage']);
        return j;
      });
      if (required) {
        // 나머지를 자르는 동안 먼저 실패하면(취소·네트워크) 아직 await 전이라 처리되지 않은 오류가 된다.
        // ignore 는 그 보고만 막고, 나중의 await 에는 오류가 그대로 온다(2026-10-30 점검).
        f.ignore();
        return f;
      }
      return f.catchError((Object e) {
        warnings.add('$name 을(를) 읽지 못했습니다: $e');
        return null;
      });
    }

    // 자체 모델 표시패 찾기(사진 전체, Gemini 없음). 실패하면(예전 서버 404, 시간 초과) 조용히 Gemini 답을 쓴다.
    Map<String, dynamic>? localDoraJ;
    Future<List<ReadTile>> readLocalDora() async {
      final t = Stopwatch()..start();
      try {
        final j = await client.observe('localdora', original, filename: 'local_dora.jpg').timeout(_localDoraTimeout);
        trace?._recordCall('local_dora', t.elapsedMilliseconds, j);
        trace?.localDora = j;
        localDoraJ = j;
        return parseCenterV2(j).indicators;
      } catch (_) {
        return const [];
      }
    }

    // 자체 모델만이면 사진 전체만 보내므로 디코딩·크롭을 기다리지 않고 맨 먼저 보낸다(metrics 표 1-81). Gemini 경로는 자리 판독을
    // 먼저 보내던 순서 그대로(아래).
    var localDoraF = localOnly ? readLocalDora() : Future<List<ReadTile>>.value(const []);

    // 자리 전체 크롭이면 손패 칸 폭 비율을 같이 보낸다 — 서버가 손패 틀을 못 잡으면 손패 칸·모서리 칸으로 나눠 한 번 더 잡는다
    // (먼 자리 B 틀 0/2 → 2/2, 검사 통과한 틀린 틀 0, metrics 표 2-3). 예전 서버는 모르는 쿼리를 무시한다.
    Map<String, String>? seatQuery(Side s) => splitSeat ? null : {'hand_frac': grid.handFrac(s).toStringAsFixed(3)};

    final Side? known;
    final List<Side> seatSides, lastSides, cornerSides, trackedSides;
    final Map<Side, Uint8List> handCrops;
    var layout = grid.toLayout(faceUp: const []);
    final Map<Side, Future<Map<String, dynamic>?>> seatF, cornerF, shadowF;
    Future<({Map<String, dynamic>? j, Object? error})>? wideF;
    ({Map<String, dynamic>? j, Object? error})? wideReady; // 미리 보낸 답이 이미 와 있으면(기다리지 않고 쓸 수 있게)
    final trackedMode = <Side, String>{};
    final started = <Future<Object?>>[];
    try {
      small = await shot.shrink();
      trace?.small = small;
      lap('shrink');
      a = await ops.analyzeGrid(small, grid);
      trace?.analysis = a;
      layout = grid.toLayout(faceUp: a.faceUp);
      trace?.layout = layout;
      lap('analyze');

      known = winnerSide ?? (a.faceUp.length == 1 ? a.faceUp.first : null);
      seatSides = known == null ? Side.values : [known];
      // 유국으로 봉이 남은 자리([carriedSticks])는 화료자여도 강을 같이 보낸다 — 눕힌 패로 이번 판 리치를 정한다. 호출은 그대로 하나.
      lastSides = [
        for (final s in Side.values)
          if (localOnly || s != known || carriedSticks.contains(s)) s,
      ];
      final useTracked = trackedBox != null && trackSide != null && lastSides.contains(trackSide);

      onStage?.call(ReadStage.cropping);
      cornerSides = splitSeat ? seatSides : const <Side>[];
      // 추적으로 울기를 이미 아는 자리는 손패 칸만 읽는다(/v2/handonly). 자리 전체 크롭도 잘라 둔다 —
      // 장수가 안 맞으면 그걸로 /v2/seat 를 다시 부르고, 그림자 모드면 처음부터 둘 다 보낸다.
      trackedSides = [
        for (final s in seatSides)
          if (!localOnly && !splitSeat && tracked.containsKey(s)) s,
      ];
      // 장면 시간은 자리 판독(3번 동시, 가장 느림)이 정하므로 자리 크롭을 먼저 잘라 먼저 보낸다.
      final seatCropSides = [
        for (final s in seatSides)
          if (!roleSeats || trackedSides.contains(s)) s,
      ];
      final seatList = await shot.crop([
        for (final s in seatCropSides) CropSpec(splitSeat ? grid.handCell(s) : grid.seatForRead(s), side: s),
        for (final s in cornerSides) CropSpec(grid.cornerCell(s), side: s),
        for (final s in trackedSides) CropSpec(grid.handCellForRead(s), side: s),
        // 화료자를 알면 테이블 절반도 잘라 둔다. 자리 판독으로 답을 못 정한 장면에서만 보낸다(사진은 곧 닫는다).
        if (known != null && !splitSeat && useWide && !localOnly) CropSpec(grid.seatHalf(known), side: known),
      ]);
      wideCrop = known != null && !splitSeat && useWide && !localOnly ? seatList.last : null;
      seatCrops = {for (final (i, s) in seatCropSides.indexed) s: seatList[i]};
      cornerCrops = {for (final (i, s) in cornerSides.indexed) s: seatList[seatCropSides.length + i]};
      handCrops = {
        for (final (i, s) in trackedSides.indexed) s: seatList[seatCropSides.length + cornerSides.length + i],
      };
      trace?.meldCrops = [...cornerCrops.values];
      onStage?.call(ReadStage.reading);
      // 손패 전용에는 확정한 울기 수를 같이 보낸다 — 서버가 손패 틀(YOLO + 조각 읽기)의 장수 검사(13·14)에 더한다.
      // 없으면 틀을 못 잡고 통째로 읽어 느려진다(B·D 60장면 p90 10.7 → 8.0초, metrics 표 2-1).
      seatF = {
        for (final s in seatSides)
          s: trackedSides.contains(s)
              ? call('handonly', handCrops[s], 'handonly_${s.name}',
                  required: known != null, query: {'melds': '${tracked[s]!.length}'})
              : roleSeats
                  // 자체 모델 새 경로: 자리 크롭 대신 사진 전체 + 격자를 보내 상자 배치 역할 모델이 그 자리 것만 고른다(/v2/localroles,
                  // 서버 app/roles.py, metrics 표 1-58~1-61). 답은 /v2/seat 모양 그대로.
                  ? call('localroles', original, 'roles_${s.name}', required: known != null, query: {
                      'side': s.name,
                      'x1': '${grid.x1}',
                      'x2': '${grid.x2}',
                      'y1': '${grid.y1}',
                      'y2': '${grid.y2}',
                      if (grid.sticks case final b?) 'sticks': b.toList().join(','),
                    })
                  : call(localOnly ? 'localseat' : 'seat', seatCrops[s], 'seat_${s.name}', required: known != null, query: seatQuery(s)),
      };
      shadowF = {
        for (final s in trackedSides)
          if (shadow) s: call('seat', seatCrops[s], 'seat_${s.name}', query: seatQuery(s)),
      };
      cornerF = {for (final s in cornerSides) s: call('corner', cornerCrops[s], 'corner_${s.name}')};
      // 넓은 구역 판독을 미리 보낸다. 실패는 그 답이 필요할 때만 경고로(안 쓰는 장면에서 자동 반영을 막지 않게).
      if (wideEarly && wideCrop != null && known != null) {
        trace?.wideEarly = true;
        wideF = call('seatwide', wideCrop, 'seatwide_${known.name}', required: true)
            .then<({Map<String, dynamic>? j, Object? error})>((j) => (j: j, error: null), onError: (Object e) => (j: null, error: e))
            .then((r) => wideReady = r);
      }
      started.addAll([...seatF.values, ...shadowF.values, ...cornerF.values, ?wideF]);
      if (localDora && !localOnly) localDoraF = readLocalDora();

      // 게임 중 추적이 본 마지막 버림패 위치가 있으면 그 패만 따로 잘라 한 번 더 읽는다(강 끝 틀을 못 잡을 때의 대안).
      final needDealer = dealer != null && !localOnly;
      final rest = await shot.crop([
        for (final s in lastSides) CropSpec(grid.lastZone(s), side: s),
        if (needSticks) CropSpec(grid.sticksZone),
        // 도라 크롭은 가운데 칸을 화료자 아닌 쪽으로 조금 넓혀 선에 걸친 표시패까지(화료자를 모르면 넓히지 않음).
        if (needDora) CropSpec(grid.doraSearchZone(except: seatSides.toSet())),
        if (dealer != null && needDealer) CropSpec(grid.doraZone(dealer), side: dealer),
        if (trackedBox != null && trackSide != null && useTracked) CropSpec(trackedBox, side: trackSide, pad: 0.6),
      ]);
      lastCrops = {for (final (i, s) in lastSides.indexed) s: rest[i]};
      trace?.riverCrops = lastCrops;
      var next = lastSides.length;
      Uint8List? take(bool want) => want ? rest[next++] : null;
      sticksCrop = take(needSticks);
      trace?.centerCrop = sticksCrop;
      doraCrop = take(needDora);
      trace?.wallCrop = doraCrop;
      dealerDoraCrop = take(needDealer);
      trace?.dealerDoraCrop = dealerDoraCrop;
      trackedCrop = take(useTracked);
      lap('crop');
    } catch (_) {
      // 자리 판독을 보낸 뒤 나머지를 자르다 실패하면, 보낸 요청의 오류가 처리되지 않은 채 남지 않게 한다.
      for (final f in started) {
        f.ignore();
      }
      rethrow;
    } finally {
      await shot.close();
    }

    // 강 끝은 자리마다 따로 부르지 않고 한 호출로 읽는다(/v2/last3). 따로 부르면 셋 중 하나가 생각을 길게 해 장면이 30초대로
    // 늘었고, 한 호출에선 모델이 생각을 건너뛰어 빠르다(B·C·D 60장면: 론 패 54 → 60/60, 중앙 8.5 → 5.9초, p90 32.7 → 14.4초).
    final lastSent = [
      for (final s in lastSides)
        if (lastCrops[s] != null) s,
    ];
    // 헤지: [lastHedge] 안에 답이 없거나 먼저 실패하면(503 등) 같은 요청을 한 번 더 보내 먼저 온 답을 쓴다. 강 끝은 한 호출에
    // 60/60 이라 정확도 손해 없이 Gemini 꼬리(같은 사진 5~60초)와 일시 오류를 자른다(10-25 시뮬 헤지 p90 34.6 → 17.6초, 표 2-2).
    Future<Map<String, dynamic>> lastOnce(String name) {
      final t = Stopwatch()..start();
      return client
          .observeLasts([for (final s in lastSent) (lastCrops[s]!, 'last_${s.name}.jpg')], path: localOnly ? '/v2/locallast3' : '/v2/last3')
          .then((j) {
        trace?._recordCall(name, t.elapsedMilliseconds, j);
        return j;
      });
    }

    final lastsF = lastSent.isEmpty
        ? Future<Map<String, dynamic>?>.value(null)
        : hedged(() => lastOnce('last3'), () => lastOnce('last3_hedge'), localOnly ? null : lastHedge, onHedge: () => trace?.lastHedged = true)
              .then<Map<String, dynamic>?>((j) {
                usage['last3'] = parseUsage(j['usage']);
                return j;
              })
              .catchError((Object e) {
                warnings.add('강 끝을 읽지 못했습니다: $e');
                return null;
              });
    final sticksF = call('sticks', localOnly && !geminiSticks ? null : sticksCrop, 'sticks');
    final doraF = call('dora', localOnly ? null : doraCrop, 'dora');
    final dealerDoraF = call('dora', dealerDoraCrop, 'dora_dealer');
    final trackedF = call('last', trackedCrop, 'last_tracked');

    final seats = <Side, SeatV2>{
      for (final e in seatF.entries)
        if (await e.value case final j?) e.key: parseSeatV2(j),
    };
    // 판독 불확실성 신호(`/v2/localroles` 의 signals, 개선 계획 5단계): 추적 자리(손패 전용 판독)에는 없다.
    final seatSignals = <Side, Map<String, dynamic>>{
      for (final e in seatF.entries)
        if (!trackedSides.contains(e.key))
          if (await e.value case final j?)
            if (j['signals'] case final Map<String, dynamic> sig) e.key: sig,
    };
    // 추적 자리: 손패 전용 판독에 미리 읽은 울기를 채우고 장수(14 − 3 × 울기)를 검사한다. 안 맞으면 자리 전체를 다시 읽는다.
    for (final s in trackedSides) {
      final h = seats[s];
      final melds = tracked[s]!;
      final shadowJ = shadow ? await shadowF[s] : null;
      final handonlyJ = await seatF[s];
      if (trace != null && handonlyJ != null && shadowJ != null) {
        trace.shadow[s] = ShadowRead(
          handonly: handonlyJ,
          seat: shadowJ,
          handonlyMs: trace.callMs['handonly_${s.name}'],
          seatMs: trace.callMs['seat_${s.name}'],
        );
      }
      if (h == null) continue;
      if (!h.faceUp && h.tiles.isEmpty) {
        // 뒷면(화료자가 아닌) 자리: 손패 0장이 맞다. 장수 검사를 하면 늘 "안 맞음" 이 되어 자리 전체를 다시 읽고 경고까지
        // 남겨 자동 반영이 막혔다(2026-10-30 점검, 화료자를 픽셀로 못 정한 판마다).
        seats[s] = (faceUp: false, tiles: h.tiles, separate: h.separate, melds: melds, loose: h.loose, agreement: h.agreement);
        trackedMode[s] = 'handonly';
        continue;
      }
      final count = h.tiles.length + (h.separate == null ? 0 : 1);
      // 쯔모·화료패를 손패 옆에 둔 론이면 14 − 3×울기, 론 패가 아직 방총자 강에 있으면 13 − 3×울기(merge 가 강 끝에서 더한다).
      final need = 13 - 3 * melds.length;
      if (h.faceUp && (count == need || count == need + 1)) {
        seats[s] = (faceUp: true, tiles: h.tiles, separate: h.separate, melds: melds, loose: h.loose, agreement: h.agreement);
        trackedMode[s] = 'handonly';
        continue;
      }
      final full = shadowJ ?? await call('seat', seatCrops[s], 'seat_${s.name}', query: seatQuery(s));
      trackedMode[s] = 'fallback_seat';
      warnings.add('${s.label} 자리: 미리 읽은 울기 ${melds.length}묶음과 손패 $count장이 맞지 않아 자리 전체를 다시 읽었습니다');
      seats[s] = full != null
          ? parseSeatV2(full)
          : (faceUp: h.faceUp, tiles: h.tiles, separate: h.separate, melds: melds, loose: h.loose, agreement: h.agreement);
    }
    trace?.trackedMode.addAll(trackedMode);
    // 나눠 읽었으면 모서리 칸의 울기·따로 놓인 패를 그 자리에 합친다. 손패 칸에서도 같은 묶음을 읽었으면 한 번만 센다.
    for (final e in cornerF.entries) {
      final c = await e.value;
      final h = seats[e.key];
      if (c == null || h == null) continue;
      final corner = parseCornerV2(c);
      String key(ObservedMeld m) => ([for (final t in m.tiles) t.tile]..sort()).join(',');
      final keys = {for (final m in corner.melds) key(m)};
      seats[e.key] = (
        faceUp: h.faceUp,
        tiles: h.tiles,
        separate: h.separate,
        melds: [
          ...corner.melds,
          for (final m in h.melds)
            if (!keys.contains(key(m))) m,
        ],
        loose: [...h.loose, ...corner.loose],
        agreement: h.agreement,
      );
    }
    final lastsJ = await lastsF;
    final rivers = (lastsJ?['rivers'] as List<dynamic>?) ?? const [];
    final riverSideways = riverSidewaysFrom(lastsJ, lastSent, carriedSticks);
    trace?.riverSideways = riverSideways;
    final lastJ = <Side, Map<String, dynamic>?>{
      for (final s in lastSides)
        s: switch (lastSent.indexOf(s)) {
          final i when i >= 0 && i < rivers.length => rivers[i] as Map<String, dynamic>?,
          _ => null,
        },
    };
    final sticksJ = await sticksF;
    final trackedJ = await trackedF;
    final trackedTile = trackedJ == null ? null : parseLastV2(trackedJ);
    // 자체 모델만 쓰면 리치봉을 읽지 않고 강의 눕힌 패로 리치를 본다. geminiSticks 면 Gemini 리치봉도 읽어 둘 중 하나라도 보이면 리치로.
    final geminiSeen = sticksJ == null ? const <Side, bool>{} : parseCenterV2(sticksJ).sticks;
    final sticks = localOnly
        ? {
            for (final e in localSticksFrom(lastsJ, lastSent).entries) e.key: e.value,
            for (final e in geminiSeen.entries)
              if (e.value) e.key: true,
          }
        : geminiSeen;
    // 리치 표시패 짝은 자체 모델이 다루지 않는다. 화료자에게 리치 증거가 없을 때만(화료자를 모르면 탁자 어디에도 없을 때만)
    // 자체 답을 쓰고, 그때는 Gemini 도라 답을 기다리지 않는다(요청은 이미 보냈고 실패는 call 이 처리한다).
    final localTiles = await localDoraF;
    final riichiSeen = known != null
        ? sticks[known] == true || trackedRiichi.contains(known)
        : sticks.values.any((v) => v) || trackedRiichi.isNotEmpty;
    final useLocal = localTiles.isNotEmpty && (localOnly || !riichiSeen);
    final doraJ = useLocal ? null : await doraF;
    final dealerDoraJ = useLocal ? null : await dealerDoraF;
    var wideDora = const <ReadTile>[];
    // 화료자 손패가 장수·패 모양으로 안 맞거나 화료패를 못 찾았으면 테이블 절반에서 다시 찾는다(`wide_seat.dart`). 그만큼 느려지지만 이 장면만.
    if (known case final side? when wideCrop != null && seats[side] != null) {
      final ends = [
        for (final e in lastJ.entries)
          if (e.key != side) e.value == null ? null : parseLastV2(e.value!),
        if (trackSide != side) trackedTile,
      ];
      WideRead? wideRead;
      final needs = seatNeedsWide(seats[side]!, ends);
      // 울기가 미덥지 않은 자리(엇갈림·확신도 0)는 미리 보낸 답이 있을 때만 대조한다(흩어진 손패를 울기로 묶은 틀린 계산 막기).
      final doubtful = trackedMode[side] != 'handonly' && meldsDoubtful(seats[side]!) && wideF != null;
      if (needs || doubtful) {
        final Map<String, dynamic>? j;
        if (wideF != null) {
          final r = await wideF;
          if (r.error case final e? when needs) warnings.add('seatwide_${side.name} 을(를) 읽지 못했습니다: $e');
          j = r.j;
        } else {
          j = await call('seatwide', wideCrop, 'seatwide_${side.name}');
        }
        if (j != null) {
          trace?.wide = j;
          wideRead = WideRead.fromJson(j);
          final scattered = doubtful ? applyScattered(seats[side]!, wideRead) : null;
          if (scattered != null) {
            seats[side] = scattered.seat;
            warnings.add(scattered.note);
          } else if (needs) {
            final r = applyWide(seats[side]!, wideRead, meldsKnown: trackedMode[side] == 'handonly');
            seats[side] = r.seat;
            if (r.note case final note?) warnings.add(note);
          }
        }
      }
      // 리치 화료의 표시패: 매장에선 도라·뒷도라 두 장을 탁자 위 빈 곳(손패 줄보다 위, 강 옆)에 내놓는다(리치 아니면 왕패에 그대로).
      // 자리 크롭 밖이라 손패 옆(loose)에 안 잡히면 미리 보낸 넓은 판독의 표시패 짝(서버 `pair`, 2~4장)을 쓴다. 리치봉이 보이거나
      // 추적이 확정한 화료자만 그 답을 기다린다(안 쓰는 장면은 기다리지 않음). 사용자 규칙 "탁자 위 표시패는 2장 이상" (2026-11-01).
      // 리치를 모르는 자리(추적 없음·봉을 이미 가져감)도 답이 이미 와 있으면 기다리지 않고 쓴다(merge 가 리치면 먼저 쓴다).
      final riichiSide = (sticks[side] ?? false) || trackedRiichi.contains(side);
      if (wideIndicators && seats[side]!.loose.isEmpty && (riichiSide || wideReady != null)) {
        if (wideRead == null && wideF != null) {
          final r = riichiSide ? await wideF : wideReady!;
          if (r.j case final j?) {
            wideRead = WideRead.fromJson(j);
            trace?.wideForDora = riichiSide;
          }
        }
        if (wideRead case final w? when w.pairs.length >= 2 && w.pairs.length <= 4) {
          wideDora = w.pairs;
        }
      }
    }
    // 자체 모델만 쓰는 리치 화료: 딱 2장 묶음이 하나면 그 둘을 탁자 위 표시패로. 여럿이거나 확신이 낮으면 고르지 않는다(확인으로).
    if (localOnly && known != null && riichiSeen) wideDora = localPairIndicators(localDoraJ, grid: grid, winner: known, trackedDora: trackedDora);
    lap('read');

    var sides = [?known];
    // 도라 표시패: 자체 모델이 사진 전체에서 찾은 것, 없으면 선 기준 도라 구역,
    // 그것도 없으면 가운데 칸. 둘을 나란히 불러 시간은 늘지 않는다. 리치 화료면 merge 가 화료자 손패 옆을 먼저 쓴다.
    final dealerDora = dealerDoraJ == null ? const <ReadTile>[] : parseCenterV2(dealerDoraJ).indicators;
    final centerDora = doraJ == null ? const <ReadTile>[] : parseCenterV2(doraJ).indicators;
    final dora = useLocal ? localTiles : (dealerDora.isNotEmpty ? dealerDora : centerDora);
    final doraFrom = useLocal
        ? DoraFrom.local
        : dealerDora.isNotEmpty
        ? DoraFrom.dealerZone
        : (centerDora.isNotEmpty ? DoraFrom.center : null);

    /// 화료자 [side] 하나의 판독. 강 끝·리치봉·도라는 같은 사진 것을 나눠 쓴다.
    TableReading build(Side side) {
      final h = seats[side]!;
      final ws = [...warnings];
      final who = sides.length > 1 ? '${side.label}: ' : '';
      final (:melds, :stray, :notes) = sortMelds(h.melds, h.tiles.length + (h.separate == null ? 0 : 1));
      ws.addAll(notes.map((n) => '$who$n'));
      // 서버가 여러 번 읽은 답이 모두 같지 않으면 자동으로 믿지 않는다. 엇갈린 패는 서버가 확신도 0 으로 보내 노란 테두리가 된다.
      if (h.agreement case (unanimous: false, :final reads, :final agree, :final alternatives)) {
        ws.add(
          '$who손패를 $reads번 읽어 $agree번만 같았습니다. 노란 패를 확인하세요'
          '${alternatives.isEmpty ? '' : ' (다른 답: ${alternatives.join(' / ')})'}',
        );
      }
      final lastTiles = <Side, ReadTile?>{
        for (final e in lastJ.entries)
          if (e.key != side) e.key: e.value == null ? null : parseLastV2(e.value!),
      };
      // 추적이 본 마지막 버림패: 강 끝 판독이 비면 채우고, 둘 다 있는데 다르면 확인을 묻는다(촬영 판독을 믿되 경고).
      if (trackedTile != null && trackSide != null && trackSide != side && lastTiles.containsKey(trackSide)) {
        final read = lastTiles[trackSide];
        if (read == null) {
          lastTiles[trackSide] = trackedTile;
        } else if (read.tile != trackedTile.tile) {
          ws.add('$who${trackSide.label} 강 끝: 촬영 판독 ${read.code} 과 게임 중 본 마지막 버림패 ${trackedTile.code} 이 다릅니다');
        }
      }
      final observation = TableObservation(
        players: {
          for (final s in Side.values)
            s: SeatObservation(
              faceUp: s == side || a.faceUp.contains(s) || (seats[s]?.faceUp ?? false),
              handTiles: s == side ? h.tiles : const [],
              separateTile: s == side ? h.separate : null,
              melds: s == side ? melds : const [],
              // 강은 마지막 패 한 장만 읽는다. 가로 여부는 리치 판단에 쓰지 않는다.
              river: lastTiles.containsKey(s) ? [if (lastTiles[s] case final t?) RiverTile(t)] : null,
              // 리치봉: 촬영 판독 ∪ 게임 중 추적이 확정한 것.
              riichiStick: (sticks[s] ?? false) || trackedRiichi.contains(s),
            ),
        },
        // 가운데(왕패)와 화료자 손패 옆을 따로 넘기고, 어느 쪽을 쓸지는 merge 가 리치 여부로 정한다.
        doraIndicators: dora,
        doraFrom: doraFrom,
        handSideIndicators: h.loose.isNotEmpty ? h.loose : (stray.isNotEmpty ? stray : (side == known ? wideDora : const [])),
        usage: usage,
      );
      if (side == sides.first) trace?.observation = observation;
      return TableReading(
        layout: layout,
        winnerSide: side,
        hand: observation.toHandReading(side).withSignals(seatSignals[side]),
        center: observation.toCenterReading(),
        warnings: ws,
        meldsTracked: trackedMode[side] == 'handonly',
        trackedDiscardSide: trackSide,
        trackedRiichi: trackedRiichi,
        trackedDoubleRiichi: trackedDoubleRiichi,
        trackedIppatsu: trackedIppatsu,
        riverSideways: riverSideways,
        trackedDora: trackedDora,
      );
    }

    if (sides.isEmpty) {
      // 손패 4장 이상을 앞면으로 읽은 자리. 패산 더미 때문에 픽셀로 못 정한 자리(장면 C·E 왼쪽)가 여기서 정해진다.
      final cands = [
        for (final s in Side.values)
          if (seats[s] case final v? when v.faceUp && v.tiles.length >= 4) s,
      ];
      layout = grid.toLayout(faceUp: cands);
      trace?.layout = layout;
      // 둘이고 [acceptAll] 이 두 판독을 받아들이면(같은 방총자·같은 화료패로 둘 다 화료형) 묻지 않고 더블론.
      if (cands.length == 2 && acceptAll != null) {
        sides = cands;
        if (acceptAll([for (final s in cands) build(s)])) {
          trace?.autoMultiRon = true;
        } else {
          sides = const [];
        }
      }
      // 아니면 동시 론일 수 있어 여럿을 고를 수 있게 묻는다(첫 자리가 대표 화료자).
      if (sides.isEmpty) {
        sides = cands.length == 1 ? cands : (await pickWinners?.call(cands.isEmpty ? Side.values : cands)) ?? const [];
      }
      if (sides.isEmpty) {
        throw TableReadException(
          cands.isEmpty ? '앞면으로 눕힌 손패를 못 찾았습니다. 누가 났는지 골라 주세요' : '눕힌 손패가 ${cands.length}자리입니다. 누가 났는지 골라 주세요',
          layout: layout,
        );
      }
    }
    lap('pick');
    final side = sides.first;
    trace?.winnerSide = side;
    trace?.handCrop = seatCrops[side];
    for (final s in sides) {
      if (seats[s] == null) {
        throw TableReadException('${s.label} 자리를 읽지 못했습니다. 다시 찍어 주세요', layout: layout);
      }
    }
    final first = build(side);
    trace?.hand = first.hand;
    trace?.center = first.center;
    return TableReading(
      layout: layout,
      winnerSide: side,
      hand: first.hand,
      center: first.center,
      warnings: first.warnings,
      others: [for (final s in sides.skip(1)) build(s)],
      meldsTracked: first.meldsTracked,
      trackedDiscardSide: first.trackedDiscardSide,
      trackedRiichi: first.trackedRiichi,
      trackedDoubleRiichi: first.trackedDoubleRiichi,
      trackedIppatsu: first.trackedIppatsu,
      riverSideways: first.riverSideways,
      trackedDora: first.trackedDora,
    );
  }

  /// [fixed] 로 읽다가 장수가 안 맞으면 null(그때 locate 로 다시 읽는다).
  Future<TableReading?> _read(
    Uint8List original,
    Side? winnerSide,
    Future<Side?> Function(List<Side> candidates)? pickWinner,
    void Function(ReadStage stage)? onStage,
    TableReadTrace? trace,
    FixedTable? fixed,
  ) async {
    final sw = Stopwatch()..start();
    void lap(String name) {
      trace?.timingsMs[name] = sw.elapsedMilliseconds;
      sw.reset();
    }

    onStage?.call(ReadStage.decoding);
    final small = await ops.shrink(original);
    trace?.small = small;
    lap('shrink');

    TableLayout? fixedLayout;
    if (fixed != null) {
      final a = await ops.analyze(small, fixed);
      trace?.analysis = a;
      lap('analyze');
      if (!a.moved && a.faceUp.isNotEmpty) fixedLayout = fixed.layoutFor(a);
    }
    if (fixed != null && fixedLayout == null) return null;
    final usingFixed = fixedLayout != null;
    if (usingFixed) trace?.layoutMode = 'fixed';

    final TableLayout layout;
    if (fixedLayout != null) {
      layout = fixedLayout;
    } else {
      onStage?.call(ReadStage.locating);
      layout = await client.locate(small);
      lap('locate');
    }
    trace?.layout = layout;

    var side = winnerSide;
    if (side == null) {
      final candidates = layout.faceUpSides;
      if (candidates.isEmpty) {
        throw TableReadException(
          layout.hands.isEmpty ? '손패 구역을 찾지 못했습니다. 테이블 전체가 보이게 찍었는지 확인하세요' : '앞면으로 눕힌 손패가 없습니다. 화료한 손패를 눕혀 주세요',
          layout: layout,
        );
      } else if (candidates.length == 1) {
        side = candidates.first;
      } else {
        side = await pickWinner?.call(candidates);
        if (side == null) {
          throw TableReadException('눕힌 손패가 ${candidates.length}자리입니다. 누가 났는지 골라 주세요', layout: layout);
        }
      }
    }
    lap('pick');
    trace?.winnerSide = side;
    final handZone = layout.hand(side);
    if (handZone == null) {
      throw TableReadException('${side.label} 자리의 손패 구역을 찾지 못했습니다', layout: layout);
    }

    onStage?.call(ReadStage.cropping);
    // 모델은 보이는 것만 적고(서버 /v2), 판단은 [TableObservation] 이 코드로 한다.
    // 크롭: 화료자 손패 · 자리별 강(그 사람 방향으로 세움) · 가운데 · 왕패.
    final specs = <CropSpec>[CropSpec.hand(handZone.box, side)];
    // 화료자의 울기: 손패 끝에서 그 사람 오른쪽 모서리까지([meldCorner])를 늘 따로 잘라 읽는다(묶음 하나까지).
    // locate 의 울기 상자는 호출마다 있다 없다 해서(갤러리 사진 A 안깡 2/2 → 0/2) 그것만 믿지 않는다.
    // locate 가 그 모서리 안에서 묶음을 둘 이상 찾았으면 모서리 대신 그 상자들을 하나씩 읽고, 모서리 밖의 오른쪽
    // 상자는 더해 읽는다. 손패가 이미지 끝에 붙어 모서리가 없으면 locate 상자만.
    final corner = meldCorner(handZone.box, side);
    final located = usingFixed ? const <SidedZone>[] : layout.meldsRightOf(side);
    final inCorner = [
      for (final m in located)
        if (corner.containsCenterOf(m.box)) m,
    ];
    final readCorner = inCorner.length < 2 && corner.width > 5 && corner.height > 5;
    final meldZones = [
      if (readCorner) SidedZone(side, corner) else ...inCorner,
      for (final m in located)
        if (!corner.containsCenterOf(m.box)) m,
    ];
    for (final (i, m) in meldZones.indexed) {
      specs.add(readCorner && i == 0 ? CropSpec(m.box, side: side, pad: 0.03) : CropSpec.meld(m.box, side));
    }
    final riverSides = [for (final r in layout.rivers) r.side];
    for (final r in layout.rivers) {
      specs.add(CropSpec.river(r.box, r.side));
    }
    final center = layout.center;
    if (center != null) specs.add(CropSpec.center(center));
    // 자동탁의 왕패는 보통 한 자리 앞 패산 끝에 있어 가운데 크롭에서 작게 잡히거나 빠진다. 따로 크게 잘라 읽는다.
    final wall = layout.deadWall?.box;
    if (wall != null) specs.add(CropSpec.wall(wall));
    final crops = await ops.cropMany(original, specs);
    trace?.handCrop = crops[0];
    final meldCrops = crops.sublist(1, 1 + meldZones.length);
    trace?.meldCrops = meldCrops;
    final r0 = 1 + meldZones.length;
    final riverCrops = {for (var i = 0; i < riverSides.length; i++) riverSides[i]: crops[r0 + i]};
    trace?.riverCrops = riverCrops;
    final centerCrop = center == null ? null : crops[r0 + riverSides.length];
    trace?.centerCrop = centerCrop;
    final wallCrop = wall == null ? null : crops.last;
    trace?.wallCrop = wallCrop;
    lap('crop');

    onStage?.call(ReadStage.reading);
    final warnings = <String>[];
    final usage = <String, Map<String, int>>{};
    Future<Map<String, dynamic>?> call(
      String kind,
      Uint8List? bytes,
      String name, {
      bool required = false,
      String? filename,
    }) {
      if (bytes == null) return Future.value(null);
      final f = client.observe(kind, bytes, filename: filename ?? '$name.jpg').then<Map<String, dynamic>?>((j) {
        usage[name] = parseUsage(j['usage']);
        return j;
      });
      if (required) {
        // 나머지를 자르는 동안 먼저 실패하면(취소·네트워크) 아직 await 전이라 처리되지 않은 오류가 된다.
        // ignore 는 그 보고만 막고, 나중의 await 에는 오류가 그대로 온다(2026-10-30 점검).
        f.ignore();
        return f;
      }
      return f.catchError((Object e) {
        warnings.add('$name 을(를) 읽지 못했습니다: $e');
        return null;
      });
    }

    final handF = call('hand', crops[0], 'hand', required: true, filename: 'hand_${side.name}.jpg');
    final meldF = [for (var i = 0; i < meldCrops.length; i++) call('meld', meldCrops[i], 'meld_$i')];
    final riverF = [for (final s in riverSides) call('river', riverCrops[s], 'river_${s.name}')];
    final centerF = call('center', centerCrop, 'center');
    final wallF = call('center', wallCrop, 'wall');
    if (center == null) warnings.add('중앙 구역을 찾지 못해 리치봉·도라는 강·왕패에서만 봅니다');

    final handJ = (await handF)!;
    final meldJ = await Future.wait(meldF);
    final riverJ = await Future.wait(riverF);
    final centerJ = await centerF;
    final wallJ = await wallF;

    final h = parseHandV2(handJ);
    final boxedMelds = [
      for (final j in meldJ)
        if (j != null) ?parseMeldV2(j),
    ];
    // 손패 크롭에서 읽은 울기(손패 옆에 붙여 둔 것)도 더하되, 모서리·울기 상자에서 같은 묶음을 읽었으면 한 번만 센다.
    String key(ObservedMeld m) => ([for (final t in m.tiles) t.tile]..sort()).join(',');
    final boxedKeys = {for (final m in boxedMelds) key(m)};
    final readMelds = [
      ...boxedMelds,
      for (final m in h.melds)
        if (!boxedKeys.contains(key(m))) m,
    ];
    // 퐁·치·깡 모양이 아닌 묶음(갤러리 사진의 4통4통7만 = 모서리에 둔 도라 표시패)은 울기로 쓰지 않고
    // 다른 데서 도라 표시패를 못 읽었을 때 그 후보로 쓴다. 장수로 보아 울기인 묶음은 표시패로 쓰지 않는다([sortMelds]).
    final (:melds, :stray, :notes) = sortMelds(readMelds, h.tiles.length + (h.separate == null ? 0 : 1));
    warnings.addAll(notes);
    // 고정 구역으로 읽은 장수가 안 맞으면(울기를 놓쳤거나 옆 패가 섞임) locate 로 다시.
    final count = h.tiles.length + (h.separate == null ? 0 : 1) + 3 * melds.length;
    if (usingFixed && count != 13 && count != 14) return null;
    final rivers = {
      for (var i = 0; i < riverSides.length; i++)
        if (riverJ[i] != null) riverSides[i]: parseRiverV2(riverJ[i]!),
    };
    final c = centerJ == null ? null : parseCenterV2(centerJ);
    final w = wallJ == null ? null : parseCenterV2(wallJ);
    final faceUp = layout.faceUpSides.toSet();
    final observation = TableObservation(
      players: {
        for (final s in Side.values)
          s: SeatObservation(
            faceUp: faceUp.contains(s),
            handTiles: s == side ? h.tiles : const [],
            separateTile: s == side ? h.separate : null,
            melds: s == side ? melds : const [],
            river: rivers[s]?.tiles,
            riichiStick: (rivers[s]?.riichiStick ?? false) || (c?.sticks[s] ?? false) || (w?.sticks[s] ?? false),
          ),
      },
      // 왕패를 따로 읽었으면 그쪽(크게 잘라 정확), 아니면 가운데.
      doraIndicators: (w != null && w.indicators.isNotEmpty)
          ? w.indicators
          : (c != null && c.indicators.isNotEmpty)
          ? c.indicators
          : stray,
      usage: usage,
    );
    final hand = observation.toHandReading(side);
    final centerReading = observation.toCenterReading();
    trace?.observation = observation;
    trace?.hand = hand;
    trace?.center = centerReading;
    lap('read');

    return TableReading(layout: layout, winnerSide: side, hand: hand, center: centerReading, warnings: warnings);
  }
}
