// 독립 검토: 무작위 위험 장면을 riskOf 로 돌려 Go 하네스와 같은 꼴로 출력.
import 'dart:convert';
import 'dart:io';

import 'package:mahjong_calc/engine/risk.dart';
import 'package:mahjong_calc/engine/tile.dart';

List<int> t(String s) => s.trim().isEmpty ? [] : parseTiles(s).tiles;
double r6(double x) => (x * 1e6).round() / 1e6;

void main(List<String> args) {
  final doc = jsonDecode(File(args[0]).readAsStringSync()) as Map<String, dynamic>;
  final res = <String, Object?>{};
  for (final c in (doc['cases'] as List).cast<Map<String, dynamic>>()) {
    try {
      final ctx = RiskContext(
        selfSeat: c['self'] as int,
        dealer: c['dealer'] as int,
        roundWindTile: Tiles.parse(c['round_wind'] as String),
        discards: [
          for (final d in c['discards'] as List)
            RiskDiscard(d[0] as int, Tiles.parse(d[1] as String), tsumogiri: d[2] as bool?, riichi: d[3] as bool),
        ],
        melds: [
          for (final m in c['melds'] as List)
            RiskMeld(m['seat'] as int, MeldKind.values.byName(m['kind'] as String), t(m['tiles'] as String),
                at: m['at'] as int, upgradedAt: m['upgraded_at'] as int?, red: m['red'] as bool? ?? false),
        ],
        doraIndicators: t(c['dora_indicators'] as String),
        hand34: toCounts(t(c['hand'] as String)),
        unknownTsumogiri: UnknownTsumogiri.values.byName(c['unknown_tsumogiri'] as String),
      );
      final r = riskOf(ctx);
      res[c['name'] as String] = {
        'seats': {
          for (final o in r.opponents)
            '${o.seat}': {
              'tenpai': r6(o.tenpaiRate),
              'turns': o.turns,
              'ron_point': r6(o.ronPoint),
              'riichi': o.riichi,
              'ippatsu': o.ippatsu,
              'safe': [for (var i = 0; i < 34; i++) if (o.safe34[i]) i],
              'risk34': [for (final x in o.risk34) r6(x)],
              'left_no_suji': o.leftNoSujiTiles,
            },
        },
        'mixed34': [for (final x in r.mixed34) r6(x)],
        'left34': r.left34,
      };
    } catch (e, st) {
      res[c['name'] as String] = {'error': '$e $st'.substring(0, 400)};
    }
  }
  stdout.write(jsonEncode(res));
}
