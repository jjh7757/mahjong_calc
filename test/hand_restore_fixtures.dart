/// 손패 복원 시험의 공용 재료: 예시 패보 읽기 · 손패 지우기 · 정답 손패로 만든 읽기(end_order).
library;

import 'dart:convert';
import 'dart:io';

import 'package:mahjong_calc/paifu/hand_restore/turn_agent.dart';
import 'package:mahjong_calc/paifu/hand_restore/turns.dart';
import 'package:mahjong_calc/paifu/paifu.dart';

Map<String, dynamic> assetJson(String name) =>
    jsonDecode(File('assets/paifu/$name.json').readAsStringSync()) as Map<String, dynamic>;

/// 예시 판. 유국이라 끝 손패가 없으면 마지막 hero 버림 뒤 손패를 결과 손패로 넣는다(텐파이 공개와 같음).
Paifu withEndHand(Map<String, dynamic> j) {
  final hero = j['hero'] as int;
  final r = (j['result'] as Map?)?.cast<String, dynamic>() ?? {'type': 'draw'};
  if (r['hand'] == null) {
    final last = (j['events'] as List).cast<Map<String, dynamic>>().lastWhere((e) => e['type'] == 'discard' && e['seat'] == hero);
    r['hand'] = last['hand'];
  }
  return Paifu.fromJson({...j, 'result': r});
}

/// hero 손패를 지운 패보(버림만). [dropDraws] 면 hero 뽑기 사건도 뺀다(버림 기록기 패보와 같은 꼴), 아니면 뽑은 패만 지운다.
/// 쯔모기리 표시도 리치 뒤만 남긴다(기록기처럼). 버림 시각이 없으면 12초 간격으로 붙인다.
Paifu stripHands(Paifu p, {bool dropDraws = true}) {
  final out = <PaifuEvent>[];
  var t = 1000000;
  final declared = <int>{};
  for (final e in p.events) {
    if (e.type == PaifuEventType.draw && e.seat == p.hero) {
      if (dropDraws) continue;
      out.add(PaifuEvent(type: PaifuEventType.draw, seat: e.seat));
      continue;
    }
    if (e.type == PaifuEventType.discard) {
      t += 3000;
      out.add(PaifuEvent(
        type: e.type,
        seat: e.seat,
        tile: e.tile,
        tsumogiri: declared.contains(e.seat) ? true : null,
        riichi: e.riichi,
        at: e.at ?? t,
      ));
      if (e.riichi) declared.add(e.seat);
      continue;
    }
    out.add(PaifuEvent(type: e.type, seat: e.seat, callKind: e.callKind, from: e.from, callTiles: e.callTiles));
  }
  return Paifu(
    id: p.id,
    title: p.title,
    round: p.round,
    honba: p.honba,
    dealer: p.dealer,
    hero: p.hero,
    names: p.names,
    events: out,
    result: p.result,
    frames: const PaifuFrames(dir: '/rec', box: [0, 700, 1000, 1000], side: 'bottom'),
  );
}

/// hero 버림마다(차례 번호 → 읽기): 원본 손패에서 지은 정답 end_order.
Map<int, TurnReading> truthReadings(Paifu orig) {
  final hero = orig.hero;
  final out = <int, TurnReading>{};
  List<PaifuTile>? before;
  PaifuTile? drawn;
  var turn = 0;
  for (final e in orig.events) {
    if (e.seat != hero) continue;
    if (e.type == PaifuEventType.draw) {
      before = e.hand;
      drawn = e.tile;
    } else if (e.type == PaifuEventType.call) {
      before = null;
      drawn = null;
    } else if (e.type == PaifuEventType.discard) {
      final after = e.hand!;
      if (before != null && drawn != null) {
        out[turn] = _reading(before, drawn, after, e);
      }
      before = after;
      drawn = null;
      turn++;
    }
  }
  return out;
}

TurnReading _reading(List<PaifuTile> before, PaifuTile drawn, List<PaifuTile> after, PaifuEvent e) {
  final n = before.length;
  final labels = <(String, PaifuTile)>[for (var i = 0; i < n; i++) ('${i + 1}', before[i]), ('D', drawn)];
  // 버린 패 고르기: 쯔모기리면 D, 아니면 줄의 같은 패(마지막), 없으면 D.
  int gone;
  if (e.tsumogiri == true) {
    gone = n;
  } else {
    gone = labels.lastIndexWhere((l) => l.$1 != 'D' && l.$2 == e.tile);
    if (gone < 0) gone = n;
  }
  final left = [...labels]..removeAt(gone);
  final used = List<bool>.filled(left.length, false);
  final order = <String>[];
  for (final t in after) {
    final i = [for (var k = 0; k < left.length; k++) k].firstWhere((k) => !used[k] && left[k].$2 == t,
        orElse: () => throw StateError('정답 손패가 앞뒤가 안 맞음: $before + $drawn → $after'));
    used[i] = true;
    order.add(left[i].$1);
  }
  final tsumo = gone == n;
  return TurnReading(kind: tsumo ? 'tsumogiri' : 'hand', endOrder: order, orderOk: !tsumo, why: '정답');
}

/// hero 버림의 손패만(사건 순서).
List<String> heroDiscardHands(Paifu p) => [
      for (final e in p.events)
        if (e.type == PaifuEventType.discard && e.seat == p.hero) e.hand?.map((t) => t.code).join(' ') ?? '-',
    ];

/// API 차례 번호들.
List<int> apiTurns(Paifu p) => [
      for (final t in planTurns(p))
        if (t.usesApi) t.index,
    ];
