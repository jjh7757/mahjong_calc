// 밀기 · 접기(설계서 docs/push_fold_design_1122.md) 앱 판정을 천봉 판에 돌려 측정 줄과 맞대기 위한 값 뽑기.
//
//   dart run tool/pushfold_check.dart <tenhou6.json>... [--out <파일.jsonl>]
//
// 판마다 깡 없는 국(측정과 같음 — tool/tenhou6_features.dart `hasKan`) · 네 자리를 hero 로 [kyokuToPaifu] 해서
// reviewPaifu(withEngine: true) 를 돌리고, 수비(defense) 차례마다 한 줄: 판 · 국 · 자리(천봉) · k(그 국 hero 버림 순번,
// 0부터 — 측정 줄의 k) · 울기 직후 · 샹텐 · 효율 패 차 · 앱 판정(pushFold 의 행동, 없으면 null).
// 대조(같은 game · kyoku · seat · k 의 R3 · player)는 이 출력과 experiments/paifu_review/results/pushfold/stage1_rows.jsonl 로.
// 시험 판(test599 · test200)은 넣지 말 것 — 개발 판(mxfit/split.py stage1 select · val)만.
import 'dart:convert';
import 'dart:io';

import 'package:mahjong_calc/engine/tile.dart';
import 'package:mahjong_calc/paifu/paifu.dart' show PaifuEventType;
import 'package:mahjong_calc/paifu/paifu_review.dart';

import 'tenhou6_features.dart' show ReplayError, hasKan, kyokuToPaifu;

Future<void> main(List<String> args) async {
  final srcs = <String>[];
  String? out;
  for (var i = 0; i < args.length; i++) {
    if (args[i] == '--out' && i + 1 < args.length) {
      out = args[++i];
    } else {
      srcs.add(args[i]);
    }
  }
  if (srcs.isEmpty) {
    stderr.writeln('쓰는 법: dart run tool/pushfold_check.dart <tenhou6.json>... [--out <파일.jsonl>]');
    exitCode = 64;
    return;
  }
  final IOSink sink = out == null ? stdout : File(out).openWrite(encoding: utf8);
  for (final src in srcs) {
    final f = File(src);
    var game = f.uri.pathSegments.last;
    if (game.endsWith('.json')) game = game.substring(0, game.length - 5);
    final logs = (jsonDecode(f.readAsStringSync(encoding: utf8)) as Map<String, dynamic>)['log'] as List;
    var errors = 0, spots = 0, defense = 0;
    final sw = Stopwatch()..start();
    for (final (ki, log) in logs.indexed) {
      final l = log as List;
      if (hasKan(l)) continue;
      for (var seat = 0; seat < 4; seat++) {
        try {
          final p = kyokuToPaifu(l, seat, id: game);
          final r = reviewPaifu(p, withEngine: true);
          for (final t in r.turns) {
            if (t.status != ReviewStatus.defense) continue;
            defense++;
            // 이 버림 앞 hero 사건이 울기인가(측정의 afterCall).
            var afterCall = false;
            for (var j = t.eventIndex - 1; j >= 0; j--) {
              final e = p.events[j];
              if (e.seat != seat) continue;
              afterCall = e.type == PaifuEventType.call;
              break;
            }
            final eff = pushFoldEfficientTile(t.mh, t.mhBest);
            final byKind = t.riskByKind;
            double? gapEff;
            if (eff != null && byKind != null && byKind.containsKey(eff)) {
              final mn = byKind.values.map((v) => v.isFinite ? v : 0.0).reduce((a, b) => a < b ? a : b);
              gapEff = (byKind[eff]!.isFinite ? byKind[eff]! : 0.0) - mn;
            }
            final s = t.pushFold;
            if (s != null) spots++;
            sink.add(utf8.encode('${jsonEncode({
                  'game': game,
                  'kyoku': ki,
                  'seat': seat,
                  'k': t.turn - 1,
                  'afterCall': afterCall,
                  'kinds': byKind?.length,
                  'shantenBefore': t.shantenBefore,
                  'effTile': eff == null ? null : Tiles.toCode(eff),
                  'gapEff': gapEff,
                  'actualTile': Tiles.toCode(t.discard.tile),
                  'spot': s != null,
                  'action': s == null ? null : (s.action == PushFoldAction.between ? 'mid' : s.action.name),
                  'gapActual': s?.discardGap,
                })}\n'));
          }
        } on ReplayError catch (e) {
          errors++;
          stderr.writeln('$game 국 $ki 자리 $seat: ${e.message}');
        }
      }
    }
    stderr.writeln('$game: 수비 차례 $defense · 접는 자리 $spots · 재생 오류 $errors · ${(sw.elapsedMilliseconds / 1000).toStringAsFixed(1)}초');
  }
  if (out != null) await sink.close();
}
