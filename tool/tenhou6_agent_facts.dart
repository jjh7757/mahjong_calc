// 천봉(tenhou.net/6) 한 국 · 한 자리 → 복기 에이전트 사실표(v3, 엔진 켬). 설계서 docs/paifu_review_agent_defense_design_1122.md 3절
// · 사실표 3 은 docs/review_agent_foldspot_scores_design_1123.md 2절.
//
//   dart run tool/tenhou6_agent_facts.dart [--compact] <tenhou6.json> <국 번호(log 배열 0부터)> <자리(천봉 0~3)> [출력.json]
//
// 그 국을 그 자리(hero) 시점의 [Paifu] 로 바꾸고(tool/tenhou6_features.dart 의 kyokuToPaifu 를 그대로 씀) agentFacts 를 낸다.
// - 판 ID · 플레이어 이름은 사실표에 넣지 않는다(Paifu 의 id · names 를 비워 둠, agentFacts 도 넣지 않음).
// - 깡이 든 국은 오류로 거절한다(종료 코드 65). 재생 검사가 어긋나도 오류.
// - 결과(和了 · 流局)는 log 끝 칸에서 읽어 [PaifuResult] 로 붙인다(화료자 · 방총자 · 화료패). 더블 론은 첫 화료자만.
//   kyokuToPaifu 는 결과를 넣지 않으므로 이 도구가 더한다(사실표의 game.result · others 의 화료 줄).
// - 국 시작 점수(`log[1]`) · 공탁(`log[0][2]`)도 패보의 start_scores · kyotaku 로 싣는다(사실표 3 의 game.scores).
// 출력 경로가 없으면 stdout. 기본은 들여쓰기 2칸, --compact 면 한 줄. UTF-8 · LF. 화면 없이 도는 순수 Dart.
import 'dart:convert';
import 'dart:io';

import 'package:mahjong_calc/paifu/agent_facts.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';

import 'tenhou6_features.dart' show ReplayError, hasKan, kyokuToPaifu, tenhouTile;

/// 천봉 한 국의 결과 칸 → [PaifuResult]. 모르는 꼴이면 null.
/// 和了: `['和了', [점수 변화], [화료자, 방총자, …], …]` — 화료자 = 방총자면 쯔모. 화료패는 론이면 마지막 버림,
/// 쯔모면 화료자의 마지막 뽑기.
PaifuResult? tenhouResult(List log, Paifu p) {
  final res = log.last;
  if (res is! List || res.isEmpty || res[0] is! String) return null;
  // 流局 · 全員聴牌 · 九種九牌 · 流し満貫 … — 和了 이 아닌 끝은 모두 유국으로.
  if (res[0] != '和了') return const PaifuResult(type: 'draw');
  if (res.length < 3 || res[2] is! List || (res[2] as List).length < 2) return null;
  final info = res[2] as List;
  final winner = info[0] as int, from = info[1] as int;
  if (winner == from) {
    final takes = log[5 + 3 * winner] as List;
    final last = takes.isEmpty ? null : takes.last;
    return PaifuResult(type: 'tsumo', winner: winner, winTile: last is int ? tenhouTile(last) : null);
  }
  PaifuTile? win;
  for (final e in p.events.reversed) {
    if (e.type == PaifuEventType.discard) {
      win = e.tile;
      break;
    }
  }
  return PaifuResult(type: 'ron', winner: winner, loser: from, winTile: win);
}

/// 천봉 한 국의 국 시작 점수(`log[1]`, 천봉 자리 순 4개) → 패보 `start_scores`. 꼴이 다르면 null.
/// kyokuToPaifu 는 천봉 자리 번호를 그대로 패보 자리로 쓴다(dealer = 국 번호 % 4 — `toTenhou6` 의
/// `ts(s) = (s − dealer + 국 번호 % 4) % 4` 가 항등이 되는 자리 매김) — 그래서 돌리지 않고 그대로 싣는다.
List<int>? tenhouStartScores(List log) {
  final sc = log.length > 1 ? log[1] : null;
  if (sc is! List || sc.length != 4 || sc.any((v) => v is! num)) return null;
  return [for (final v in sc) (v as num).toInt()];
}

/// 천봉 한 국의 공탁(`log[0][2]`, 국 시작 때 걸려 있던 리치봉 수) → 패보 `kyotaku`. 없으면 null.
int? tenhouKyotaku(List log) {
  final head = log.isEmpty ? null : log[0];
  if (head is! List || head.length < 3 || head[2] is! num) return null;
  return (head[2] as num).toInt();
}

/// 천봉 한 판(JSON) · 국 번호 · 자리 → 사실표. 깡이 든 국 · 범위 밖 · 재생 실패는 [ReplayError].
Map<String, dynamic> tenhouAgentFacts(Map<String, dynamic> json, int kyoku, int seat) {
  final logs = json['log'] as List;
  if (kyoku < 0 || kyoku >= logs.length) throw ReplayError('국 번호 $kyoku 가 범위 밖(0~${logs.length - 1})');
  if (seat < 0 || seat > 3) throw ReplayError('자리는 0~3: $seat');
  final log = logs[kyoku] as List;
  if (hasKan(log)) throw ReplayError('깡이 든 국은 지원하지 않는다(국 $kyoku)');
  final bare = kyokuToPaifu(log, seat);
  final p = Paifu(
    id: '',
    round: bare.round,
    honba: bare.honba,
    dealer: bare.dealer,
    hero: bare.hero,
    doraIndicators: bare.doraIndicators,
    events: bare.events,
    result: tenhouResult(log, bare),
    startScores: tenhouStartScores(log),
    kyotaku: tenhouKyotaku(log),
  );
  return agentFacts(p, reviewPaifu(p, withEngine: true));
}

const _usage = '쓰는 법: dart run tool/tenhou6_agent_facts.dart [--compact] <tenhou6.json> <국 번호> <자리> [출력.json]';

void main(List<String> argv) {
  final compactOut = argv.contains('--compact');
  final args = [for (final a in argv) if (a != '--compact') a];
  if (args.length < 3 || args.length > 4) {
    stderr.writeln(_usage);
    exitCode = 64;
    return;
  }
  final src = File(args[0]);
  final kyoku = int.tryParse(args[1]), seat = int.tryParse(args[2]);
  if (kyoku == null || seat == null) {
    stderr.writeln('국 번호 · 자리는 정수\n$_usage');
    exitCode = 64;
    return;
  }
  if (!src.existsSync()) {
    stderr.writeln('파일이 없습니다: ${args[0]}');
    exitCode = 66;
    return;
  }
  final Map<String, dynamic> facts;
  try {
    facts = tenhouAgentFacts(jsonDecode(src.readAsStringSync(encoding: utf8)) as Map<String, dynamic>, kyoku, seat);
  } on ReplayError catch (e) {
    stderr.writeln('거절: ${e.message}');
    exitCode = 65;
    return;
  }
  final compact = jsonEncode(facts);
  final text = '${compactOut ? compact : const JsonEncoder.withIndent('  ').convert(facts)}\n';
  if (args.length == 4) {
    File(args[3]).writeAsBytesSync(utf8.encode(text));
    final turns = (facts['turns'] as List).cast<Map<String, dynamic>>();
    final withDefense = turns.where((t) => t['defense'] != null).length;
    stderr.writeln('${args[3]} — 버림 ${turns.length}번, 수비 칸 $withDefense, 압축 ${utf8.encode(compact).length} bytes');
  } else {
    stdout.add(utf8.encode(text));
  }
}
