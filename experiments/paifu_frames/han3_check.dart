// 3반장 패보(han3_paifu.py 가 만든 것) 검사 — 앱 형식으로 읽히는지, Paifu.check(), 걸음 수, 점수(scoreOf)와 점수 이동(리치봉 · 노텐 벌점 제외).
// lib 는 import 만 한다(고치지 않음). 저장소 루트에서:
//   C:/Users/jjh7757/flutter/bin/dart.bat run experiments/paifu_frames/han3_check.dart <패보.json …>
// 출력: 표준 출력에 JSON 한 개 {"<id>": {...}} — han3_paifu.py 가 읽어 국 시작 점수를 굴린다.
import 'dart:convert';
import 'dart:io';

import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_score.dart';

void main(List<String> args) {
  final out = <String, dynamic>{};
  for (final path in args) {
    final Map<String, dynamic> j;
    try {
      j = jsonDecode(File(path).readAsStringSync()) as Map<String, dynamic>;
    } catch (e) {
      out[path] = {'error': '읽기 실패: $e'};
      continue;
    }
    final Paifu p;
    try {
      p = Paifu.fromJson(j);
    } catch (e) {
      out[path] = {'error': '앱 형식으로 못 읽음: $e'};
      continue;
    }
    final r = <String, dynamic>{
      'id': p.id,
      'events': p.events.length,
      'steps': p.states.length,
      'wall_left_end': p.states.last.wallLeft,
      'check': p.check(),
      'discards': [for (var s = 0; s < 4; s++) p.events.where((e) => e.seat == s && e.type == PaifuEventType.discard).length],
      'calls': p.events.where((e) => e.type == PaifuEventType.call).length,
      'riichi_seats': [for (final e in p.events) if (e.type == PaifuEventType.discard && e.riichi) e.seat],
    };
    final res = p.result;
    if (res != null && (res.type == 'ron' || res.type == 'tsumo')) {
      final sc = scoreOf(p);
      if (sc == null) {
        r['score_error'] = '점수 계산 못 함(scoreOf null — 손패 장수 · 형식)';
      } else {
        final s = sc.result;
        r['score'] = {
          'valid': s.isValid,
          'error': s.error,
          'summary': s.isValid ? s.summary : null,
          'han': s.han,
          'fu': s.fu.total,
          'yaku': [for (final y in s.yaku) '${y.yaku.label} ${y.han}'],
          'payment': s.payment.display,
          'total': s.payment.total,
        };
        if (s.isValid) {
          final w = res.winner!, d = p.dealer;
          final delta = List<int>.filled(4, 0);
          if (res.type == 'ron') {
            delta[res.loser!] -= s.payment.ron;
            delta[w] += s.payment.ron;
          } else {
            for (var q = 0; q < 4; q++) {
              if (q == w) continue;
              final pay = (w != d && q == d) ? s.payment.tsumoFromDealer : s.payment.tsumoFromNonDealer;
              delta[q] -= pay;
              delta[w] += pay;
            }
          }
          r['delta'] = delta;
        }
      }
    }
    out[p.id] = r;
  }
  stdout.writeln(const JsonEncoder.withIndent(' ').convert(out));
}
