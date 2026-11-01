// 기기(에뮬레이터·폰) 위에서 거치 화면의 판독 흐름을 그대로 돌려 단계별 시간을 잰다.
// 사진 줄이기·앞면 판정·자르기는 앱처럼 isolate(compute)에서, 서버 호출(/v2/*)은 실제로, 병합·점수는 기기에서.
// 사진은 PC 에서 HTTP 로 받는다(측정 전에 받아 두므로 시간에 들어가지 않는다).
//
// PC: python -m http.server 8040 --bind 127.0.0.1 -d experiments/field_20261024/kakao_photos
//     (인식 서버는 127.0.0.1:8030)
// flutter drive --profile -d emulator-5554 --driver=test_driver/integration_test.dart \
//   --target=integration_test/read_grid_timing_test.dart \
//   --dart-define=PHOTO_URL=http://10.0.2.2:8040 --dart-define=RECOGNIZER_URL=http://10.0.2.2:8030 [--dart-define=REPEAT=2]
// 결과는 TIMING {...} 줄(JSON)로 찍힌다. 대국 정보·격자는 read_grid_test.dart 와 같다.
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart' show compute;
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:integration_test/integration_test.dart';
import 'package:mahjong_calc/engine/calculator.dart' as engine;
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/services/capture_log.dart';
import 'package:mahjong_calc/services/recognizer_client.dart';
import 'package:mahjong_calc/table/auto_record.dart';
import 'package:mahjong_calc/table/cropper.dart';
import 'package:mahjong_calc/table/fixed_layout.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/merge.dart';
import 'package:mahjong_calc/table/seat_map.dart';
import 'package:mahjong_calc/table/shot_image.dart';
import 'package:mahjong_calc/table/rectify.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/table_reader.dart';
import 'package:image/image.dart' as img;

const _photoUrl = String.fromEnvironment('PHOTO_URL', defaultValue: 'http://10.0.2.2:8040');
const _repeat = int.fromEnvironment('REPEAT', defaultValue: 2);

// 운영 서버는 분당 요청 제한이 있어 장면 사이에 쉰다(쉬는 시간은 재는 시간에 안 들어간다).
const _sleepS = int.fromEnvironment('SLEEP_S', defaultValue: 0);

// ALT_URL 을 주면 같은 사진을 기본 서버(RECOGNIZER_URL)와 이 서버에 **같은 순간** 보내 둘 다 잰다(TIMING 의 server 가
// "main"/"alt"). 운영 vs 로컬처럼 시간대 차이 없이 서버만 비교할 때. ALT_KEY 는 그 서버의 API 키(로컬은 비움).
// 두 판독이 기기 isolate 를 나눠 써서 기기 처리 시간은 혼자 잴 때보다 늘 수 있다 — 서버 판독(read) 단계로 비교한다.
// Gemini 호출이 장면마다 두 배라 분당 제한(20)을 넘지 않게 SLEEP_S 를 넉넉히(45) 준다.
const _altUrl = String.fromEnvironment('ALT_URL');
const _altKey = String.fromEnvironment('ALT_KEY');

// 화료패가 사진에 있는 장면 B·C·D(A·E 는 평가에서 뺀다). 격자는 5구역 측정과 같다.
const _bcd = {
  'B': (['k25', 'k28'], {'x1': 272, 'x2': 735, 'y1': 137, 'y2': 727}),
  'C': (['k15', 'k26'], {'x1': 320, 'x2': 760, 'y1': 142, 'y2': 717}),
  'D': (['k12', 'k16'], {'x1': 280, 'x2': 745, 'y1': 173, 'y2': 713}),
};

// SET=field: [참고·평가 밖] 10/24 매장 카메라 헤드 사진(captures/20261024_<시각>/original.jpg, PHOTO_URL 은 captures 폴더).
// 화료가 사진에 다 있는 장면만. 정답은 NOTES "촬영별".
// 13:18(131823)은 폰 EXIF 회전값이 바뀐 사진이라 뺌(앱은 헤드 사진 EXIF 를 무시하지만 여기선 원본 그대로 디코딩).
// 격자: 기본값(GridZones.initial = 손으로 찍은 갤러리 사진 D 에 그은 선)은 삼각대 사진(탁자가 약 25° 기움)에 안 맞아
// 화료자 손패가 가운데 칸에 들어갔다(첫 실행 손패 0/15). 앱에서 카메라를 놓고 격자를 한 번 맞추듯 삼각대 위치별로 맞춤
// (`FIELD_GRID=initial` 이면 기본값으로).
const _initialGrid = {'x1': 280, 'x2': 745, 'y1': 173, 'y2': 713};
const _useInitial = String.fromEnvironment('FIELD_GRID') == 'initial';
const _gridA = _useInitial ? _initialGrid : {'x1': 300, 'x2': 690, 'y1': 150, 'y2': 830}; // 12:29~13:51
const _gridA2 = _useInitial ? _initialGrid : {'x1': 300, 'x2': 720, 'y1': 150, 'y2': 830}; // 12:40(조금 움직임)
const _gridB1 = _useInitial ? _initialGrid : {'x1': 315, 'x2': 760, 'y1': 200, 'y2': 740}; // 13:59~14:09
const _gridB2 = _useInitial ? _initialGrid : {'x1': 355, 'x2': 760, 'y1': 200, 'y2': 740}; // 14:34
// FIELD_GRIDS="사진=x1,x2,y1,y2;…" 면 사진마다 그 격자(YOLO 자동 격자 비교용, experiments/yolo/auto_grid.py --set field).
const _fieldGrids = String.fromEnvironment('FIELD_GRIDS');
// BASE_GRIDS: 같은 형식. PAIR_GRID 의 "plain" 쪽 격자를 사진마다 정한다(매장 저장 격자 vs 사진에 맞춘 격자).
const _baseGrids = String.fromEnvironment('BASE_GRIDS');
Map<String, Object>? _gridOverride(String photo, [String grids = _fieldGrids]) {
  for (final e in grids.split(';')) {
    final [p, v] = e.split('=').length == 2 ? e.split('=') : ['', ''];
    if (p != photo) continue;
    final n = [for (final x in v.split(',')) int.parse(x)];
    // 8개면 뒤 4개는 리치봉 상자(ymin, xmin, ymax, xmax).
    return {'x1': n[0], 'x2': n[1], 'y1': n[2], 'y2': n[3], if (n.length >= 8) 'sticks': n.sublist(4, 8)};
  }
  return null;
}

const _field = {
  'F1229': (['122922'], _gridA),
  'F1240': (['124007'], _gridA2),
  'F대삼원': (['125053', '130533', '131210', '132647', '133011', '133620', '134323', '135148'], _gridA),
  'F1400': (['135912', '140302', '140750', '140918'], _gridB1),
  'F1434': (['143443'], _gridB2),
};
// 매장 장면의 대국 상황(촬영 기록 meta.json): 친 자리·본장.
const _fieldGame = {'F1229': (1, 0), 'F1240': (1, 1), 'F대삼원': (2, 0), 'F1400': (2, 0), 'F1434': (2, 0)};

// SET=bcdtilt: 개발용 합성 기울기(experiments/rectify/make_tilted.py, kakao_photos/tilted/<사진>_<a|b|c>.jpg).
const _bcdTilt = {
  'B': (['tilted/k25_a', 'tilted/k25_b', 'tilted/k25_c', 'tilted/k28_a', 'tilted/k28_b', 'tilted/k28_c'], _initialGrid),
  'C': (['tilted/k15_a', 'tilted/k15_b', 'tilted/k15_c', 'tilted/k26_a', 'tilted/k26_b', 'tilted/k26_c'], _initialGrid),
  'D': (['tilted/k12_a', 'tilted/k12_b', 'tilted/k12_c', 'tilted/k16_a', 'tilted/k16_b', 'tilted/k16_c'], _initialGrid),
};

// SET=visit: [평가 밖·매장 개발 세트] 10/31 매장 25회(PHOTO_URL 은 visit_20261031/captures). 격자는 FIELD_GRIDS 로(사진마다 다르다,
// experiments/speed/flow_visit.py 가 만든다). 정답은 visit_20261031/truth.json·label.json.
const _visit = {
  'V': (
    [
      '123140', '124654', '125839', '130743', '131411', '132239', '132954', '133030', '133826', '134815',
      '142535', '143104', '164501', '165043', '165614', '170105', '171025', '171245', '171505', '172424',
      '174020', '175951', '181209', '183022', '183627',
    ],
    _initialGrid,
  ),
};

const _set = String.fromEnvironment('SET', defaultValue: 'bcd');
const _scenes = _set == 'field' ? _field : (_set == 'bcdtilt' ? _bcdTilt : (_set == 'visit' ? _visit : _bcd));
String _photoPath(String p) => _set == 'field'
    ? '20261024_$p/original.jpg'
    : (_set == 'visit' ? '20261031_$p/original.jpg' : '$p.jpg');

// DUMP_DIR: 판독에 보낸 화료자 자리 크롭(seat.jpg)·리치봉 크롭(sticks.jpg)을 <DUMP_DIR>/<사진>/ 에 저장(추가 판독 실험용).
const _dumpDir = String.fromEnvironment('DUMP_DIR');

// RECTIFY=true: 펠트 네 모서리로 사진을 펴고(lib/table/rectify.dart) 표준 격자로 읽는다. 펠트를 못 찾으면 원래 격자.
// (예전 실험 방식: 펴서 JPEG 로 다시 인코딩한 뒤 readGrid. 앱은 readGrid(rectify:) 로 디코딩한 이미지를 바로 편다.)
const _rectifyOn = bool.fromEnvironment('RECTIFY');

// PAIR_RECTIFY=true: 같은 사진을 같은 순간 두 번 — 앱 흐름 그대로(server "plain")와 readGrid(rectify: true)("rect").
// 같은 서버(RECOGNIZER_URL)로. Gemini 호출이 두 배라 SLEEP_S 를 넉넉히.
const _pairRectify = bool.fromEnvironment('PAIR_RECTIFY');

// PAIR_DEALER=true: 같은 사진을 같은 순간 두 번 — 선 기준 도라 구역 없이("plain")와 있이("dealer", readGrid(dealer:)).
// 선 자리는 대국 기록(친 자리 → 사진 쪽), DEALER_SIDE(bottom|right|top|left)를 주면 그 쪽으로(B·C·D 는 사진에 친 정보가 없다).
const _pairDealer = bool.fromEnvironment('PAIR_DEALER');

// PAIR_GRID=true: 같은 사진을 같은 순간 두 번 — 장면 격자(사용자가 맞춘 것, "plain")와 FIELD_GRIDS 의 격자("auto",
// 예: experiments/speed/setup_frames.py 가 Gemini 틀로 제안한 격자). FIELD_GRIDS 에 없는 사진은 auto 도 장면 격자(grid_fallback).
const _pairGrid = bool.fromEnvironment('PAIR_GRID');
const _dealerSide = String.fromEnvironment('DEALER_SIDE');

// PAIR_WIDE=true: 같은 사진을 같은 순간 두 번 — 넓은 구역 판독 없이("plain")와 있이("wide", 앱 기본).
const _pairWide = bool.fromEnvironment('PAIR_WIDE');

// PAIR_EARLY=true: 같은 사진을 같은 순간 두 번 — 넓은 구역 판독을 필요할 때 뒤늦게("wide", 11-01 운영 앱 4800462)와 자리 판독과
// 같은 순간에 미리 보내기("early", `readGrid(wideEarly: true)`, 앱 기본). 둘 다 넓은 판독 있이. 그 밖의 측정은 앱 기본(미리 보내기).
const _pairEarly = bool.fromEnvironment('PAIR_EARLY');

// PAIR_IND=true: 같은 사진을 같은 순간 두 번 — 11-01 17시 앱(미리 보내기만, "early")과 그 뒤 규칙 셋을 더한 앱("ind", 앱 기본:
// 리치 화료의 표시패를 넓은 판독의 표시패 짝에서 `wideIndicators`, 미덥지 않은 울기를 넓은 줄과 대조, 강 끝 헤지 `lastHedge`).
const _pairInd = bool.fromEnvironment('PAIR_IND');

/// 펴기(isolate): 원본 → (편 JPEG, 모서리) 또는 펠트를 못 찾으면 (null, null).
(Uint8List?, Map<String, Object>?) _rectifyJob(Uint8List original) {
  final im = img.decodeJpg(original)!;
  final q = findFeltQuad(img.copyResize(im, width: 1000));
  if (q == null) return (null, null);
  return (img.encodeJpg(rectify(im, q, size: 3200), quality: 92), q.toJson());
}

// ONE_DECODE=false 면 예전처럼 축소본·크롭을 각각 compute 로(원본 두 번 디코딩) — 같은 시간대에 나란히 비교용(2026-10-26).
const _oneDecode = bool.fromEnvironment('ONE_DECODE', defaultValue: true);

// 거치 화면(mount_screen.dart)과 같은 isolate 이미지 처리.
const _isolateOps = ImageOps(
  shrink: _shrink,
  cropMany: _crop,
  analyze: _analyze,
  analyzeGrid: _analyzeGrid,
  openShot: _openShot,
);
Future<Uint8List> _shrink(Uint8List o) => compute(shrinkForLocate, o);
Future<List<Uint8List>> _crop(Uint8List o, List<CropSpec> s) => compute(cropMany, (o, s));
Future<ShotImage> _openShot(Uint8List o) async => _oneDecode ? await IsolateShotImage.open(o) : _TwoDecodeShot(o);

/// 예전 방식: 부를 때마다 compute 로 원본을 새로 디코딩.
class _TwoDecodeShot implements ShotImage {
  final Uint8List original;
  _TwoDecodeShot(this.original);
  @override
  Future<Uint8List> shrink() => _shrink(original);
  @override
  Future<List<Uint8List>> crop(List<CropSpec> specs) => _crop(original, specs);
  @override
  Future<FeltQuad?> rectify() async => null;
  @override
  Future<void> close() async {}
}

Future<ShotAnalysis> _analyze(Uint8List small, FixedTable f) => compute(analyzeShot, (small, f));
Future<ShotAnalysis> _analyzeGrid(Uint8List small, GridZones g) => compute(analyzeGridShot, (small, g));

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  for (final MapEntry(key: scene, value: (photos, gridJ)) in _scenes.entries) {
    final sceneGrid = GridZones.fromJson(gridJ)!;
    for (final photo in photos) {
      final override = _gridOverride(photo);
      final autoGrid = override == null ? sceneGrid : GridZones.fromJson(override)!;
      final base = _gridOverride(photo, _baseGrids);
      final grid = _pairGrid ? (base == null ? sceneGrid : GridZones.fromJson(base)!) : autoGrid;
      // FIELD_GRIDS 를 줬는데 그 사진 격자가 없으면(자동 격자 실패) 재지 않는다.
      // PAIR_GRID 면 FIELD_GRIDS 에 없는 사진도 잰다(auto 도 장면 격자, grid_fallback — 자동 맞추기 실패 → 사람이 맞춘 격자).
      final skip = !_pairGrid && _fieldGrids.isNotEmpty && override == null;
      for (var run = 1; run <= _repeat; run++) {
        testWidgets(skip: skip, '$scene $photo #$run', (tester) async {
          await tester.runAsync(() async {
            if (_sleepS > 0) await Future<void>.delayed(const Duration(seconds: _sleepS));
            final bytes = (await http.get(Uri.parse('$_photoUrl/${_photoPath(photo)}'))).bodyBytes;
            Future<void> measure(RecognizerClient client, String server,
                {bool rect = false, bool dealerBox = false, GridZones? useGridFor, bool wide = true, bool early = !_pairEarly, bool ind = !_pairInd}) async {
              final trace = TableReadTrace();
              final (dealer, honba) = _fieldGame[scene] ?? (0, 0);
              final game = Game(
                id: 'photo',
                startedAt: DateTime(2026, 10, 24),
                settings: const GameSettings(),
                names: const ['플레이어 1', '플레이어 2', '플레이어 3', '플레이어 4'],
                dealer: dealer,
                roundNumber: dealer + 1,
                honba: honba,
              );
              final out = <String, Object?>{
                'scene': scene,
                'photo': photo,
                'run': run,
                'server': server,
                'bytes': bytes.length,
              };
              final sw = Stopwatch()..start();
              try {
                var shot = bytes;
                var useGrid = useGridFor ?? grid;
                out['grid'] = useGrid.toJson()..remove('dora');
                if (useGridFor != null && override == null) out['grid_fallback'] = true;
                if (_rectifyOn) {
                  final (rect, quad) = await compute(_rectifyJob, bytes);
                  out['rectify_ms'] = sw.elapsedMilliseconds;
                  out['quad'] = quad;
                  if (rect != null) {
                    shot = rect;
                    useGrid = standardGrid;
                  }
                }
                final dealer = !dealerBox
                    ? null
                    : (SideX.parse(_dealerSide) ?? SeatMap(game.settings.bottomSeat).sideOf(game.dealer));
                if (dealer != null) out['dealer_side'] = dealer.name;
                final reading = await TableReader(client, ops: _isolateOps)
                    .readGrid(shot, useGrid, rectify: rect, dealer: dealer, trace: trace, useWide: wide, wideEarly: early,
                        wideIndicators: ind, lastHedge: ind ? const Duration(seconds: 12) : null);
                out['wide_called'] = trace.wide != null;
                out['wide_early'] = trace.wideEarly;
                out['wide_for_dora'] = trace.wideForDora;
                out['last_hedged'] = trace.lastHedged;
                if (rect) out['quad'] = trace.feltQuad?.toJson();
                if (_dumpDir.isNotEmpty) {
                  final d = Directory('$_dumpDir/${photo.replaceAll('/', '_')}')..createSync(recursive: true);
                  if (trace.handCrop case final c?) File('${d.path}/seat.jpg').writeAsBytesSync(c);
                  if (trace.centerCrop case final c?) File('${d.path}/sticks.jpg').writeAsBytesSync(c);
                }
                final t0 = sw.elapsedMilliseconds;
                final merge = mergeReading(
                  hand: reading.hand!,
                  center: reading.center,
                  winnerSide: reading.winnerSide!,
                  game: game,
                  seats: SeatMap(game.settings.bottomSeat),
                );
                final score = merge.hand == null ? null : engine.calculate(merge.hand!, merge.situation);
                out['merge_score_ms'] = sw.elapsedMilliseconds - t0;
                out['winner'] = reading.winnerSide!.name;
                out['points'] = score == null ? null : RegExp(r' (\d{3,6}) \[').firstMatch('$score')?.group(1);
                out['flags'] = [for (final f in merge.flags) f.issue.name];
                out['warnings'] = reading.warnings;
                out['dora'] = [for (final t in merge.situation.doraIndicators) engine.Tiles.name(t)];
                out['call_ms'] = trace.callMs;
                out['merge'] = CaptureLog.mergeJson(merge);
                // 확신도 분포를 보려고 판독 원본도(손패 패별 conf, 리치봉 자리별 conf, 도라 표시패 conf).
                out['hand_read'] = reading.hand?.toJson();
                out['center_read'] = reading.center?.toJson();
                // 거치 화면과 같은 자동 반영 조건(null 이면 자동 반영).
                out['auto_block'] = autoRecordBlocker(
                  warnings: reading.warnings,
                  issues: [for (final f in merge.flags) f.issue],
                  otherWinners: reading.others.length,
                  isTsumo: merge.isTsumo,
                  loser: merge.loser,
                  resultValid: score?.isValid ?? false,
                  paoBase: score != null && score.isValid ? engine.paoBasePoints(score) : 0,
                  gameOver: false,
                  doraIndicators: merge.situation.doraIndicators.length,
                  riichi: merge.situation.riichi,
                );
              } catch (e) {
                out['error'] = '$e';
              } finally {
                client.close();
              }
              out['total_ms'] = sw.elapsedMilliseconds;
              out['stages_ms'] = trace.timingsMs;
              // Android logcat 은 한 줄을 1000자 남짓에서 자른다 — 시간만 담은 짧은 줄을 먼저(2026-10-29 태블릿).
              // ignore: avoid_print
              print('TIMES ${jsonEncode({for (final k in ['scene', 'photo', 'run', 'server', 'points', 'winner', 'error', 'merge_score_ms', 'total_ms', 'stages_ms']) k: out[k]})}');
              // ignore: avoid_print
              print('TIMING ${jsonEncode(out)}');
            }

            await Future.wait([
              measure(RecognizerClient(), _pairRectify || _pairDealer || _pairGrid || _pairWide ? 'plain' : (_pairEarly ? 'wide' : (_pairInd ? 'early' : 'main')), wide: !_pairWide),
              if (_pairWide) measure(RecognizerClient(), 'wide'),
              if (_pairEarly) measure(RecognizerClient(), 'early', early: true),
              if (_pairInd) measure(RecognizerClient(), 'ind', ind: true),
              if (_pairGrid) measure(RecognizerClient(), 'auto', useGridFor: autoGrid),
              if (_pairRectify) measure(RecognizerClient(), 'rect', rect: true),
              if (_pairDealer) measure(RecognizerClient(), 'dealer', dealerBox: true),
              if (_altUrl.isNotEmpty) measure(RecognizerClient(baseUrl: _altUrl, apiKey: _altKey), 'alt'),
            ]);
          });
        }, timeout: const Timeout(Duration(minutes: 3)));
      }
    }
  }
}
