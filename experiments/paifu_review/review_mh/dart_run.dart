// 독립 검토: hands.json 의 dart 입력으로 analyzeDiscards 를 돌려 JSON 출력.
import 'dart:convert';
import 'dart:io';

import 'package:mahjong_calc/engine/discard_rank.dart';
import 'package:mahjong_calc/engine/meld.dart';

Object? _f(double v) => v.isFinite ? v : null;

Meld _meld(Map m) {
  final ts = (m['tiles'] as List).cast<int>();
  switch (m['type']) {
    case 'chi':
      return Meld.chi(ts[0]);
    case 'pon':
      return Meld.pon(ts[0]);
    case 'ankan':
      return Meld.closedKan(ts[0]);
    default:
      return Meld.openKan(ts[0]);
  }
}

void main(List<String> args) {
  final doc = jsonDecode(File(args[0]).readAsStringSync()) as Map;
  final only = args.length > 1 ? args[1].split(',').toSet() : null;
  final out = <String, Object?>{};
  final times = <String, int>{};
  for (final c in doc['cases'] as List) {
    final id = c['id'] as String;
    if (only != null && !only.contains(id)) continue;
    final d = c['dart'] as Map;
    final ctx = DiscardContext(
      hand34: (d['hand34'] as List).cast<int>(),
      melds: [for (final m in d['melds'] as List) _meld(m as Map)],
      visible34: (d['visible34'] as List).cast<int>(),
      doraIndicators: (d['dora_indicators'] as List).cast<int>(),
      redFives: (d['red_fives'] as List).cast<int>(),
      roundWind: d['round_wind'] as int,
      seatWind: d['seat_wind'] as int,
      isDealer: d['is_dealer'] as bool,
      selfDiscards: (d['discards'] as List).cast<int>(),
    );
    final sw = Stopwatch()..start();
    Map<String, Object?> one(RankedDiscard x) => {
          'tile': x.tile,
          'shanten': x.shanten,
          'waits': {for (final e in x.waits.entries) '${e.key}': e.value},
          'waits_count': x.waitsCount,
          'avg_improve': _f(x.avgImproveWaitsCount),
          'improve_kinds': x.improveKinds,
          'improve_way': x.improveWayCount,
          'avg_next': _f(x.avgNextShantenWaitsCount),
          'speed': _f(x.speedScore),
          'agari_rate': _f(x.agariRate),
          'dama': _f(x.damaPoint),
          'riichi': _f(x.riichiPoint),
          'round_point': _f(x.roundPoint),
          'furiten_rate': x.furitenRate,
          'is_part_wait': x.raw.result13.isPartWait,
          'dora_count': x.raw.result13.doraCount,
        };
    try {
      final r = analyzeDiscards(ctx);
      out[id] = {
        'shanten': r.shanten,
        'best': r.best,
        'recommend_backward': r.recommendBackward,
        'forward': [for (final x in r.forward) one(x)],
        'backward': [for (final x in r.backward) one(x)],
      };
    } catch (e, st) {
      out[id] = {'error': '$e', 'stack': '$st'.split('\n').take(6).join('\n')};
    }
    times[id] = sw.elapsedMilliseconds;
    stderr.writeln('$id ${times[id]}ms');
  }
  stdout.write(jsonEncode({'out': out, 'ms': times}));
}
