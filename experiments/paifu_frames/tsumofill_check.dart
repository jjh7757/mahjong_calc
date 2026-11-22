// B4 확인 ③ ④ — 채운 패보 사본(tsumofill.py fill)이 앱 형식으로 읽히고 check() 를 통과하는가, 채우기 전 · 후로 hero 수비 차례의 위험 단계가 얼마나 바뀌나.
// lib 는 import 만 한다(고치지 않음). 저장소 루트에서:
//   C:\Users\jjh7757\flutter\bin\dart.bat run experiments/paifu_frames/tsumofill_check.dart <판 id…> > <out.json>
// 원본 = assets/paifu/<판>.json, 사본 = experiments/paifu_frames/results/handtrack/_work/tsumo_b4_1122/filled/<판>.json.
// 수비 차례 = 다른 자리 리치가 있고(riichiSeats) · 손패를 알고(before) · 엔진 위험표가 있는(riskTable · riskByKind) hero 차례 — agent_facts._defense 와 같은 조건.
// 위험 단계 = agent_facts.riskLevel(모두에게 안전패면 '안전', 아니면 3 · 8 · 18 문턱). 가장 안전한 패 = 위험이 최저인 종류 묶음.
import 'dart:convert';
import 'dart:io';

import 'package:mahjong_calc/paifu/agent_facts.dart' show riskLevel;
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';

Paifu load(String path) => Paifu.fromJson(jsonDecode(File(path).readAsStringSync()) as Map<String, dynamic>);

bool isDefense(TurnReview t) =>
    t.riichiSeats.isNotEmpty && t.before != null && t.riskTable != null && t.riskByKind != null && t.riskByKind!.isNotEmpty;

Set<int> safest(Map<int, double> m) {
  final lo = m.values.reduce((a, b) => a < b ? a : b);
  return {for (final e in m.entries) if ((e.value - lo).abs() < 1e-9) e.key};
}

void main(List<String> argv) {
  // 선택: --filled <폴더>(저장소 루트 기준) — 사본 폴더를 바꿈(기본 tsumo_b4_1122/filled, merge-read 는 filled_read).
  var filledDir = 'experiments/paifu_frames/results/handtrack/_work/tsumo_b4_1122/filled';
  final args = <String>[];
  for (var i = 0; i < argv.length; i++) {
    if (argv[i] == '--filled' && i + 1 < argv.length) {
      filledDir = argv[++i];
    } else {
      args.add(argv[i]);
    }
  }
  final out = <String, dynamic>{};
  var tot = {'turns': 0, 'tiles': 0, 'tiles_changed': 0, 'safest_changed': 0, 'actual_changed': 0, 'risk_changed_turns': 0};
  for (final g in args) {
    final pb = load('assets/paifu/$g.json');
    final pa = load('$filledDir/$g.json');
    final cb = pb.check(), ca = pa.check();
    final rb = reviewPaifu(pb, withEngine: true), ra = reviewPaifu(pa, withEngine: true);
    final byIdx = {for (final t in ra.turns) t.eventIndex: t};
    var turns = 0, tiles = 0, tilesChanged = 0, safestChanged = 0, actualChanged = 0, riskChangedTurns = 0;
    final detail = <Map<String, dynamic>>[];
    for (final b in rb.turns) {
      final a = byIdx[b.eventIndex];
      if (a == null || !isDefense(b) || !isDefense(a)) continue;
      turns++;
      final mb = b.riskByKind!, ma = a.riskByKind!;
      String lv(TurnReview t, int k) => riskLevel(t.riskByKind![k]!, safeForAll: t.riskTable!.safeForAll34[k]);
      var changedHere = 0;
      final ch = <String>[];
      for (final k in mb.keys) {
        if (!ma.containsKey(k)) continue;
        tiles++;
        if (lv(b, k) != lv(a, k)) {
          tilesChanged++;
          changedHere++;
          ch.add('$k:${lv(b, k)}→${lv(a, k)}');
        }
      }
      final sb = safest(mb), sa = safest(ma);
      final sChanged = !(sb.length == sa.length && sb.containsAll(sa));
      if (sChanged) safestChanged++;
      final d = b.discard.tile;
      final aChanged = mb.containsKey(d) && ma.containsKey(d) && lv(b, d) != lv(a, d);
      if (aChanged) actualChanged++;
      final riskDiff = mb.keys.any((k) => ma.containsKey(k) && (mb[k]! - ma[k]!).abs() > 1e-9);
      if (riskDiff) riskChangedTurns++;
      if (changedHere > 0 || sChanged || aChanged || riskDiff) {
        detail.add({'event': b.eventIndex, 'turn': b.turn, 'level_changes': ch, 'safest_before': sb.toList()..sort(), 'safest_after': sa.toList()..sort(),
          'actual_changed': aChanged, 'risk_number_changed': riskDiff});
      }
    }
    out[g] = {
      'check_before': cb,
      'check_after': ca,
      'check_added': [for (final x in ca) if (!cb.contains(x)) x],
      'check_removed': [for (final x in cb) if (!ca.contains(x)) x],
      'defense_turns': turns,
      'tiles': tiles,
      'tiles_level_changed': tilesChanged,
      'safest_changed_turns': safestChanged,
      'actual_level_changed_turns': actualChanged,
      'risk_number_changed_turns': riskChangedTurns,
      'detail': detail,
    };
    tot = {
      'turns': tot['turns']! + turns,
      'tiles': tot['tiles']! + tiles,
      'tiles_changed': tot['tiles_changed']! + tilesChanged,
      'safest_changed': tot['safest_changed']! + safestChanged,
      'actual_changed': tot['actual_changed']! + actualChanged,
      'risk_changed_turns': tot['risk_changed_turns']! + riskChangedTurns,
    };
  }
  out['total'] = tot;
  stdout.writeln(const JsonEncoder.withIndent(' ').convert(out));
}
