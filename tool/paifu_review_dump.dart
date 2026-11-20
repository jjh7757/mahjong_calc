// 패보 한 판 → hero 버림마다 지금 평가기(efficiency)와 mahjong-helper 엔진(discard_rank · risk)의 결정을 나란히.
//
//   dart run tool/paifu_review_dump.dart <패보.json>
//
// 표준출력에 JSON(들여쓰기 2칸, UTF-8). 패 표기는 PaifuTile code(`5m` · 적5 `0m` · 자패 `1z`~`7z`).
// 엔진이 낸 패(mhBest · mhTop5 · minRiskTile)는 종류만 알므로 적5 표시가 없다.
// 화면 없이 도는 순수 Dart(Flutter 를 쓰지 않음).
import 'dart:convert';
import 'dart:io';

import 'package:mahjong_calc/engine/tile.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';

/// 소수 셋째 자리까지. NaN · 무한은 null.
double? _num(double? x) => x == null || !x.isFinite ? null : (x * 1000).round() / 1000;

String? _code(int? t) => t == null ? null : Tiles.toCode(t);

Map<String, Object?> _entry(RankedDiscard d) => {
      'tile': Tiles.toCode(d.tile),
      'shanten': d.shanten,
      'speed': _num(d.speedScore),
      'waits': d.waitsCount,
      'improve': _num(d.avgImproveWaitsCount),
      'agariRate': _num(d.agariRate),
      'roundPoint': _num(d.roundPoint),
      if (d.isBackward) 'backward': true,
    };

/// 엔진 결정 순서(최선 먼저, 나머지 원본 순서)의 앞 다섯.
List<Map<String, Object?>>? _top5(TurnReview t) {
  final l = t.mh;
  if (l == null) return null;
  final best = t.mhBestEntry;
  final order = [?best, for (final d in l) if (d != best) d];
  return [for (final d in order.take(5)) _entry(d)];
}

Map<String, Object?> dumpTurn(TurnReview t) => {
      'turn': t.turn,
      'eventIndex': t.eventIndex,
      'discard': t.discard.code,
      'drawn': t.drawn?.code,
      'status': t.status.name,
      'grade': t.grade?.name,
      'shantenBefore': t.shantenBefore,
      'ourBest': _code(t.best?.tile),
      'ourRank': t.rank,
      'mhBest': _code(t.mhBest),
      'mhRank': t.mhRankOfActual,
      'mhTop5': _top5(t),
      'recommendBackward': t.mhRecommendBackward,
      'riichiDeclared': t.riichiDeclared,
      'riskSeats': t.riskSeats,
      'riskOfActual': _num(t.riskOfActual),
      'minRiskTile': _code(t.minRiskTile),
    };

Map<String, Object?> dumpPaifu(Paifu p) {
  final r = reviewPaifu(p, withEngine: true);
  return {
    'id': p.id,
    'round': p.round,
    'hero': p.hero,
    'dealer': p.dealer,
    'turns': [for (final t in r.turns) dumpTurn(t)],
  };
}

void main(List<String> args) {
  if (args.length != 1) {
    stderr.writeln('쓰는 법: dart run tool/paifu_review_dump.dart <패보.json>');
    exitCode = 64;
    return;
  }
  final src = File(args[0]);
  if (!src.existsSync()) {
    stderr.writeln('패보 파일이 없습니다: ${args[0]}');
    exitCode = 66;
    return;
  }
  final p = Paifu.fromJson(jsonDecode(src.readAsStringSync(encoding: utf8)) as Map<String, dynamic>);
  stdout.add(utf8.encode('${const JsonEncoder.withIndent('  ').convert(dumpPaifu(p))}\n'));
}
