// mh_cases.json 만들기: 버림 평가 이식(lib/engine/discard_rank.dart)을 원본
// EndlessCheng/mahjong-helper 와 맞대려고 쓰는 손패 목록과 Dart 출력.
//
//   dart run test/fixtures/mh_cases_gen.dart
//
// 원본 출력("go" · "go_order_varies" · "known_diffs")은
// experiments/paifu_review/mhgold 의 Go 프로그램(main.go)이 같은 파일의 input 으로
// 내고 merge.py 가 합쳐 넣는다. 이 스크립트는 그 칸들을 그대로 둔다.
import 'dart:convert';
import 'dart:io';

import 'package:mahjong_calc/engine/discard_rank.dart';
import 'package:mahjong_calc/engine/meld.dart';
import 'package:mahjong_calc/engine/tile.dart';

/// 도라 → 표시패(원본 시험의 「도라 패를 바로 준」 경우를 표시패로 바꿀 때).
int indicatorOf(int dora) {
  for (var i = 0; i < 34; i++) {
    if (Tiles.doraFromIndicator(i) == dora) return i;
  }
  throw ArgumentError('$dora');
}

class Case {
  final String id;
  final String hand; // 0 = 적5
  final List<String> melds; // 'pon:6z' 'chi:3m'(가장 낮은 패) 'ankan:1m' 'minkan:5z'
  final String doraIndicators;
  final String doraTiles; // 원본 시험처럼 도라를 바로 줄 때(표시패는 보이는 패에 안 넣음)
  final bool indicatorsVisible; // 표시패를 보이는 패에 넣는지(원본 bestHumanDiscardTile2)
  final String visible; // 그 밖에 보이는 패
  final String discards; // 자기 버림(보이는 패에도 넣는다)
  final int round, seat;
  final bool dealer;
  final String note;

  const Case(this.id, this.hand,
      {this.melds = const [],
      this.doraIndicators = '',
      this.doraTiles = '',
      this.indicatorsVisible = true,
      this.visible = '',
      this.discards = '',
      this.round = Tiles.east,
      this.seat = Tiles.east,
      this.dealer = false,
      this.note = ''});
}

List<int> _tiles(String s) => s.isEmpty ? [] : parseTiles(s).tiles;

Meld _meld(String spec) {
  final p = spec.split(':');
  final t = Tiles.parse(p[1]);
  switch (p[0]) {
    case 'pon':
      return Meld.pon(t);
    case 'chi':
      return Meld.chi(t);
    case 'ankan':
      return Meld.closedKan(t);
    case 'minkan':
      return Meld.openKan(t);
  }
  throw ArgumentError(spec);
}

const cases = <Case>[
  // 원본 TestBestDiscard(도라를 바로 줌, 자풍·장풍 동, 자)
  Case('best_c3q5', '134m 123567p 12355s', note: 'C3Q5 기대 4m'),
  Case('best_c3q5_dora5p', '134m 123567p 12355s', doraTiles: '5p', note: 'C3Q5 기대 4m'),
  Case('best_c3q4_55z', '123667m 234p 345s 55z', note: 'C3Q4 기대 7m'),
  Case('best_c3q4_44z', '123667m 234p 345s 44z', note: 'C3Q4 기대 6m'),
  Case('best_c3q8', '234456m 11567p 468s', note: 'C3Q8 기대 4s'),
  Case('best_c3q10', '1234m 345789p 567s 3z', doraTiles: '3z', note: 'C3Q10 기대 1m'),
  Case('best_c3q15', '345m 345789p 3455s 4z', note: 'C3Q15 기대 5s'),
  Case('best_c3q17_8m', '234788m 234567s 33z', doraTiles: '8m', note: 'C3Q17 기대 7m'),
  Case('best_c3q17_3z', '234788m 234567s 33z', doraTiles: '3z', note: 'C3Q17 기대 8m'),
  Case('best_c3q18', '334557m 222p 789s 33z', doraTiles: '9s', note: 'C3Q18 기대 7m'),
  Case('best_3sh_2p', '23668m 258p 4678s 77z', doraTiles: '2p', note: '3샹텐 기대 8p'),
  Case('best_3sh_8p', '23668m 258p 4678s 77z', doraTiles: '8p', note: '3샹텐 기대 2p'),
  Case('best_3sh', '23668m 258p 4678s 77z', note: '3샹텐 기대 2p'),
  // 원본 TestBest2(표시패, 적5)
  Case('best2_a', '789m 23678p 1235s 25z', doraIndicators: '3z', note: '기대 5z'),
  Case('best2_b', '24668m 2078p 23457s', doraIndicators: '3z', note: '원본 기대 8p(원본도 5p 로 실패)'),
  // 원본 TestFuritenBestDiscard
  Case('furiten_c3q6', '11456678m 567p 235s', doraTiles: '8m', discards: '1s', note: 'C3Q6 기대 5s'),
  Case('furiten_9m', '455678m 11566p 234s', discards: '9m', note: '기대 6p'),
  // 원본 TestQ300(표시패, 적5)
  Case('q001', '06778p 1122345s 77z', doraIndicators: '2z', note: '기대 2s'),
  Case('q002', '66778p 1122345s 77z', doraIndicators: '2z', note: '기대 5s'),
  Case('q003', '67778p 1122345s 77z', doraIndicators: '2z', note: '원본 기대 8p(원본도 실패)'),
  Case('q004', '12388m 455679p 556s', doraIndicators: '2z', note: '기대 5s'),
  Case('q005', '23488m 455679p 556s', doraIndicators: '2z', note: '기대 9p'),
  Case('q006', '33455m 668p 345667s', doraIndicators: '2p', note: '기대 8p'),
  Case('q007', '4406m 134556p 3478s', doraIndicators: '2z', note: '원본 기대 1p(원본도 실패)'),
  Case('q008', '135m 11240667p 789s', doraIndicators: '9s', note: '기대 2p'),
  Case('q009', '135m 12399p 123667s', doraIndicators: '2z', note: '기대 5m'),
  Case('q010', '40699m 1133p 34567s', doraIndicators: '1m', note: '기대 3p'),
  Case('q011', '1234m 5678p 122233s', doraIndicators: '8s', note: '기대 1m'),
  Case('q012', '55678m 3467p 24668s', doraIndicators: '6p', note: '원본 기대 2s(원본도 실패)'),
  Case('q013', '678m 123306p 12378s', doraIndicators: '2z', note: '기대 2p'),
  Case('q030', '23468p 130777s 444z', doraIndicators: '1p', note: '기대 8p'),
  Case('q033', '3356m 23478p 56777s', doraIndicators: '7p', note: '원본 기대 3m(원본도 실패)'),
  Case('q037', '3456m 137899p 4578s', doraIndicators: '1m', note: '원본 기대 1p(원본도 실패)'),
  Case('q058', '34056m 2224p 23468s', doraIndicators: '8m', note: '원본 기대 8s(원본도 실패)'),
  // 원본 벤치마크 손
  Case('bench_3sh', '12688m 33579p 24s 56z'),
  // 울기
  Case('open_pon6z_tenpai', '6888m 678p 5678s', melds: ['pon:6z'], note: '원본 TestCalculateShantenWithImproves14Open'),
  Case('open_pon5z_1sh', '234m 67p 3456s 88s', melds: ['pon:5z'], doraIndicators: '4s'),
  Case('open_chi_tanyao', '2344m 456p 778s 1z', melds: ['chi:3p']),
  Case('open_two_melds', '56m 678p 99s 4z', melds: ['pon:1z', 'chi:2s'], round: Tiles.east, seat: Tiles.south),
  Case('open_kuitan_part', '3445m 66p 45678s', melds: ['chi:6s'], visible: '2m2m5m'),
  Case('ankan_1m', '234p 567s 889s 55z', melds: ['ankan:1m'], doraIndicators: '9m'),
  // 친·바람·보이는 패
  Case('dealer_south_double', '123m 456p 789s 22z 34m 5z', round: Tiles.south, seat: Tiles.south, dealer: false),
  Case('dealer_east', '23455m 345p 345689s', dealer: true, doraIndicators: '4m'),
  Case('visible_heavy', '12388m 455679p 556s', visible: '3p3p3p6p6p8m4s4s7s', discards: '1z2z'),
  Case('tenpai_furiten_choice', '234567m 345p 23479s', discards: '1m9p', doraIndicators: '6s'),
  // 치또이·화료·국사꼴
  Case('chiitoi_1sh', '1199m 1122p 3344s 56z'),
  Case('agari14', '123456789m 123p 55s', note: '화료형: 지키는 버림 없음'),
  Case('kokushi_shape', '19m 19p 19s 1234567z 1m', note: '국사는 원본·이쪽 모두 안 봄'),
  // 후퇴 권장 후보(1샹텐, 버림 적음)
  Case('backward_1', '1245m 12789p 34588s', discards: '1z'),
  Case('backward_2', '2389m 4566p 2289s 44z', discards: '7z'),
  Case('backward_3', '466m 234467p 77s 123s'),
  Case('red_tenpai', '340m 678p 22567s 667z', doraIndicators: '5z'),
];

Object? _f(double v) => v.isFinite ? v : null;

Map<String, Object?> _out(DiscardRanking r) {
  Map<String, Object?> one(RankedDiscard d) => {
        'tile': d.tile,
        'code': Tiles.toCode(d.tile),
        'shanten': d.shanten,
        'waits': {for (final e in d.waits.entries) '${e.key}': e.value},
        'waits_count': d.waitsCount,
        'avg_improve': _f(d.avgImproveWaitsCount),
        'improve_kinds': d.improveKinds,
        'improve_way': d.improveWayCount,
        'avg_next': _f(d.avgNextShantenWaitsCount),
        'speed': _f(d.speedScore),
        'agari_rate': _f(d.agariRate),
        'dama': _f(d.damaPoint),
        'riichi': _f(d.riichiPoint),
        'round_point': _f(d.roundPoint),
        'furiten_rate': d.furitenRate,
        'is_part_wait': d.raw.result13.isPartWait,
        'dora_count': d.raw.result13.doraCount,
      };
  return {
    'shanten': r.shanten,
    'best': r.best,
    'recommend_backward': r.recommendBackward,
    'forward': [for (final d in r.forward) one(d)],
    'backward': [for (final d in r.backward) one(d)],
  };
}

void main() {
  final path = 'test/fixtures/mh_cases.json';
  final old = <String, Map<String, Object?>>{};
  final f = File(path);
  if (f.existsSync()) {
    for (final c in (jsonDecode(f.readAsStringSync()) as Map)['cases'] as List) {
      final m = c as Map<String, Object?>;
      old[m['id'] as String] = {
        for (final k in const ['go', 'go_order_varies', 'known_diffs'])
          if (m[k] != null) k: m[k],
      };
    }
  }
  final out = <Map<String, Object?>>[];
  for (final c in cases) {
    final parsed = parseTiles(c.hand);
    final hand34 = toCounts(parsed.tiles);
    final red = [0, 0, 0];
    // 적5 위치: 원본 시험처럼 수트별로 센다
    final norm = c.hand.replaceAll(' ', '');
    var buf = <String>[];
    for (final ch in norm.split('')) {
      if ('mpsz'.contains(ch)) {
        final s = 'mps'.indexOf(ch);
        if (s >= 0) red[s] += buf.where((d) => d == '0').length;
        buf = [];
      } else {
        buf.add(ch);
      }
    }
    final melds = [for (final m in c.melds) _meld(m)];
    final indicators = [
      ..._tiles(c.doraIndicators),
      for (final d in _tiles(c.doraTiles)) indicatorOf(d),
    ];
    final discards = _tiles(c.discards);
    final visible = List<int>.filled(34, 0);
    for (final m in melds) {
      for (final t in m.tiles) {
        visible[t]++;
      }
    }
    if (c.indicatorsVisible) {
      for (final t in _tiles(c.doraIndicators)) {
        visible[t]++;
      }
    }
    for (final t in [..._tiles(c.visible), ...discards]) {
      visible[t]++;
    }
    final ctx = DiscardContext(
      hand34: hand34,
      melds: melds,
      visible34: visible,
      doraIndicators: indicators,
      redFives: red,
      roundWind: c.round,
      seatWind: c.seat,
      isDealer: c.dealer,
      selfDiscards: discards,
    );
    final sw = Stopwatch()..start();
    final r = analyzeDiscards(ctx);
    final ms = sw.elapsedMilliseconds;
    final pi = ctx.toPlayerInfo();
    stdout.writeln('${c.id}: ${r.shanten}샹텐 best ${r.best == null ? '-' : Tiles.toCode(r.best!)} ${ms}ms');
    out.add({
      'id': c.id,
      'note': c.note,
      'hand': c.hand,
      'melds': c.melds,
      'dora_indicators': [for (final t in indicators) Tiles.toCode(t)],
      'self_discards': c.discards,
      'input': {
        'hand34': hand34,
        'melds': [
          for (final m in melds)
            {
              'type': m.type == MeldType.chi
                  ? 'chi'
                  : m.type == MeldType.pon
                      ? 'pon'
                      : (m.isOpen ? 'minkan' : 'ankan'),
              'tiles': m.tiles,
            }
        ],
        'visible34': visible,
        'dora_indicators': indicators,
        'dora_tiles': pi.doraTiles,
        'red_fives': red,
        'left34': pi.leftTiles34,
        'discards': discards,
        'round_wind': c.round,
        'self_wind': c.seat,
        'is_parent': c.dealer,
      },
      'dart': _out(r),
      ...?old[c.id],
    });
  }
  const enc = JsonEncoder.withIndent(' ');
  f.writeAsStringSync('${enc.convert({
        'about': 'EndlessCheng/mahjong-helper 버림 평가 이식 대조용. input 은 두 쪽이 같이 쓰는 수치 입력, '
            'dart 는 lib/engine/discard_rank.dart 출력, go 는 원본(514bb97) CalculateShantenWithImproves14 + '
            'simpleBestDiscardTile 출력. NaN 은 null.',
        'cases': out,
      })}\n');
}
