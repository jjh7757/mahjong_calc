/// 우리 패보 한 국 → tenhou.net/6 JSON(천봉 형식). 외부 리뷰 도구에 넣어 보기 위한 변환기. 순수 Dart.
///
/// 규격: `docs/paifu_review_grader_design_1118.md` 부록 B.
/// 우리 패보에는 hero 한 명의 손패와 네 자리 버림 · 울기만 있으므로, 다른 세 자리의 배패 · 뽑은 패는
/// 안 보인 패에서 앞뒤가 맞게 지어 채운다(B-2). 지어 채운 것 · 가정은 [Tenhou6Export.assumptions] 에 남긴다.
/// 지원하지 않거나 앞뒤가 안 맞는 패보는 [Tenhou6ExportError] 로 거절한다(조용히 틀린 로그를 내지 않는다).
library;

import 'dart:math';

import '../engine/tile.dart';
import 'paifu.dart';
import 'paifu_score.dart' show roundWindOf;

/// 다른 자리 버림의 쯔모기리 여부가 패보에 없을(null) 때 어느 쪽으로 볼지.
enum UnknownDiscard { tedashi, tsumogiri }

class Tenhou6Export {
  /// B-1 꼴. `jsonEncode` 가능.
  final Map<String, dynamic> json;

  /// 리뷰 대상(hero)의 천봉 자리 0~3.
  final int heroIndex;

  /// 지어 채운 것 · 가정(B-2 의 번호 순, 사람 말 한 줄씩).
  final List<String> assumptions;

  const Tenhou6Export(this.json, this.heroIndex, this.assumptions);
}

class Tenhou6ExportError implements Exception {
  final String message;
  const Tenhou6ExportError(this.message);

  @override
  String toString() => 'Tenhou6ExportError: $message';
}

/// 패 → 천봉 패 번호. 만 11~19 · 통 21~29 · 삭 31~39 · 자패 41~47 · 적5 51/52/53.
int tenhouTileNumber(PaifuTile t) {
  if (t.tile < 0 || t.tile >= Tiles.count) throw Tenhou6ExportError('패 번호가 범위 밖: ${t.tile}');
  final suit = Tiles.suit(t.tile);
  if (t.red) {
    if (suit > 2 || Tiles.number(t.tile) != 5) throw Tenhou6ExportError('적5 가 아닌 패에 적 표시: ${t.code}');
    return 51 + suit;
  }
  if (suit == 3) return 41 + (t.tile - Tiles.east);
  return (suit + 1) * 10 + Tiles.number(t.tile);
}

/// 패 정렬 순서: 종류 순, 같은 종류면 보통 패 → 적5.
int _cmp(PaifuTile a, PaifuTile b) => a.tile != b.tile ? a.tile - b.tile : (a.red ? 1 : 0) - (b.red ? 1 : 0);

List<PaifuTile> _sorted(Iterable<PaifuTile> ts) => [...ts]..sort(_cmp);

String _codes(Iterable<PaifuTile> ts) => _sorted(ts).map((t) => t.code).join(' ');

/// 구성(적5 포함)이 같은가.
bool _sameTiles(List<PaifuTile> a, List<PaifuTile> b) {
  if (a.length != b.length) return false;
  final x = _sorted(a), y = _sorted(b);
  for (var i = 0; i < x.length; i++) {
    if (x[i] != y[i]) return false;
  }
  return true;
}

// ── 자리별 걸음(앞에서부터) ──

sealed class _Step {}

class _Draw extends _Step {
  PaifuTile? tile;
  _Draw(this.tile);
}

class _Call extends _Step {
  final String kind; // pon · chi
  final PaifuTile taken;
  final List<PaifuTile> own;
  final int from; // 우리 자리
  _Call(this.kind, this.taken, this.own, this.from);
}

class _Discard extends _Step {
  final PaifuTile tile;
  final bool riichi;
  final bool tsumogiri;
  _Discard(this.tile, {required this.riichi, required this.tsumogiri});
}

Tenhou6Export toTenhou6(Paifu p, {UnknownDiscard unknownAs = UnknownDiscard.tedashi, List<int>? scores, int seed = 0}) =>
    _Exporter(p, unknownAs, scores, seed).run();

class _Exporter {
  final Paifu p;
  final UnknownDiscard unknownAs;
  final List<int>? scores;
  final int seed;
  _Exporter(this.p, this.unknownAs, this.scores, this.seed);

  final steps = [for (var s = 0; s < 4; s++) <_Step>[]];

  Never fail(String m) => throw Tenhou6ExportError(m);

  Tenhou6Export run() {
    final hero = p.hero;

    // ── 국 · 자리 맞춤 ──
    final round = p.round.trim();
    if (!RegExp(r'^[동남서북]').hasMatch(round)) fail('국 이름에서 장풍을 못 읽음: "${p.round}"');
    final windIdx = roundWindOf(round) - Tiles.east;
    final m = RegExp(r'([1-4])\s*국').firstMatch(round);
    if (m == null) fail('국 이름에서 국 번호(1~4)를 못 읽음: "${p.round}"');
    final kyoku = windIdx * 4 + int.parse(m.group(1)!) - 1;
    if (p.dealer < 0 || p.dealer > 3) fail('dealer 는 0~3: ${p.dealer}');
    if (p.honba < 0) fail('본장이 음수: ${p.honba}');
    int ts(int s) => (s - p.dealer + kyoku % 4) % 4;
    final heroIndex = ts(hero);
    if (scores != null && scores!.length != 4) fail('scores 는 4개여야 함: ${scores!.length}개');

    // ── 사건을 앞에서부터: 자리별 걸음 쌓기 · hero 손패 검사 ──
    final afterCall = [false, false, false, false];
    final riichiDone = [false, false, false, false];
    final callCount = [0, 0, 0, 0];
    (int, PaifuTile)? lastDiscard; // 울 수 있는 직전 버림(자리, 패)

    List<PaifuTile>? heroHand = p.startHand == null ? null : [...p.startHand!];
    List<PaifuTile>? heroStart = heroHand == null ? null : [...heroHand];
    if (heroHand != null && heroHand.length != 13) fail('start_hand 가 ${heroHand.length}장(13장이어야 함)');
    var heroDrawn = false; // 뽑고 아직 안 버림
    _Draw? heroDrawStep;
    var heroAssumedTurns = 0; // 손패 모르는 앞 순(쯔모기리로 봄)
    var heroTurnNo = 0; // hero 뽑기 수
    var heroKnownFrom = 0; // 손패가 처음 적힌 hero 뽑기 번호(1부터, 0 = start_hand)
    var heroChecked = 0;

    // 다른 자리 버림 통계(assumptions 5).
    var oTrue = 0, oFalse = 0, oNull = 0, oNullAfterCall = 0, oNullAfterRiichi = 0, oNullPolicy = 0;
    var heroTg = 0, heroTd = 0;

    for (final (i, e) in p.events.indexed) {
      final at = '사건 #${i + 1}(자리 ${e.seat} ${e.type.name})';
      final s = e.seat;
      switch (e.type) {
        case PaifuEventType.draw:
          if (s != hero) fail('$at: hero 가 아닌 자리의 뽑기 사건은 지원하지 않음');
          if (heroDrawn) fail('$at: hero 가 뽑고 버리지 않은 채 또 뽑음');
          if (afterCall[s]) fail('$at: 울기 바로 뒤에 뽑기');
          heroTurnNo++;
          if (heroHand == null) {
            if (e.hand != null) {
              heroHand = [...e.hand!];
              heroStart = [...heroHand];
              heroKnownFrom = heroTurnNo;
              if (heroHand.length != 13) fail('$at: 처음 적힌 hero 손패가 ${heroHand.length}장(13장이어야 함)');
            }
          } else {
            if (e.hand == null) fail('$at: 손패가 적힌 뒤 hero 손패가 빔');
            if (!_sameTiles(e.hand!, heroHand)) {
              fail('$at: hero 뽑기 전 손패가 앞 차례에서 이어지지 않음 — 적힌 [${_codes(e.hand!)}] / 계산 [${_codes(heroHand)}]');
            }
          }
          if (heroHand != null && e.tile == null) fail('$at: 손패가 적힌 뒤 hero 가 뽑은 패가 빔');
          heroDrawStep = _Draw(e.tile);
          steps[s].add(heroDrawStep);
          heroDrawn = true;

        case PaifuEventType.discard:
          final d = e.tile!;
          if (riichiDone[s] && e.riichi) fail('$at: 리치를 두 번 선언함');
          if (s == hero) {
            if (!heroDrawn && !afterCall[s]) {
              // 뽑기 사건 없이 버림 → 뽑기가 있었다.
              if (heroHand != null) fail('$at: 손패가 적힌 뒤 hero 뽑기 사건이 빔');
              heroTurnNo++;
              heroDrawStep = _Draw(null);
              steps[s].add(heroDrawStep);
              heroDrawn = true;
            }
            bool tg;
            if (heroHand == null) {
              // B-2 의 2: 손패 모르는 앞 순은 쯔모기리.
              if (e.tsumogiri == false) fail('$at: 손패 모르는 앞 순인데 손에서 낸 버림(쯔모기리로 볼 수 없음)');
              if (e.hand != null) fail('$at: hero 손패가 뽑기 사건보다 먼저 버림에 적힘(지원 안 함)');
              final drew = heroDrawStep!.tile;
              if (drew != null && drew != d) fail('$at: 손패 모르는 앞 순인데 뽑은 패 ${drew.code} ≠ 버린 패 ${d.code}');
              heroDrawStep.tile = d;
              heroAssumedTurns++;
              tg = true;
            } else {
              final before = [...heroHand, if (heroDrawn) heroDrawStep!.tile!];
              if (!before.remove(d)) fail('$at: hero 가 손에 없는 패 ${d.code} 를 버림 — 손 [${_codes(before)}]');
              if (e.hand == null) fail('$at: 손패가 적힌 뒤 hero 버림 손패가 빔');
              if (!_sameTiles(e.hand!, before)) {
                fail('$at: hero 손패 + 뽑은 패 − 버린 패가 적힌 손패와 다름 — 적힌 [${_codes(e.hand!)}] / 계산 [${_codes(before)}]');
              }
              heroHand = before;
              heroChecked++;
              final drew = heroDrawn ? heroDrawStep!.tile : null;
              tg = drew != null && drew == d && e.tsumogiri != false;
              if (e.tsumogiri == true && !tg) fail('$at: 쯔모기리로 적혔는데 뽑은 패(${drew?.code ?? '없음'})와 버린 패 ${d.code} 가 다름');
              if (riichiDone[s] && !tg) fail('$at: 리치 뒤에 hero 가 손에서 냄');
            }
            if (tg) {
              heroTg++;
            } else {
              heroTd++;
            }
            steps[s].add(_Discard(d, riichi: e.riichi, tsumogiri: tg));
            heroDrawn = false;
          } else {
            bool tg;
            final t = e.tsumogiri;
            if (t == true) oTrue++;
            if (t == false) oFalse++;
            if (t == null) oNull++;
            if (afterCall[s]) {
              if (t == true) fail('$at: 울기 바로 뒤 버림이 쯔모기리로 적힘');
              tg = false;
              if (t == null) oNullAfterCall++;
            } else if (riichiDone[s]) {
              if (t == false) fail('$at: 리치 뒤에 손에서 낸 버림');
              tg = true;
              if (t == null) oNullAfterRiichi++;
            } else if (t != null) {
              tg = t;
            } else {
              tg = unknownAs == UnknownDiscard.tsumogiri;
              oNullPolicy++;
            }
            if (!afterCall[s]) steps[s].add(_Draw(null));
            steps[s].add(_Discard(d, riichi: e.riichi, tsumogiri: tg));
          }
          if (e.riichi) riichiDone[s] = true;
          afterCall[s] = false;
          lastDiscard = (s, d);

        case PaifuEventType.call:
          final raw = e.callKind ?? 'call';
          if (raw.contains('kan')) fail('$at: 깡($raw)은 지원하지 않음');
          final tiles = e.callTiles;
          if (raw == 'call' && tiles.length == 1) fail('$at: 종류 모르는 울기에 가져간 한 장만 적힘');
          if (tiles.length != 3) fail('$at: 울기 묶음이 ${tiles.length}장(3장이어야 함)');
          final sortedT = _sorted(tiles);
          final same = sortedT.every((x) => x.tile == sortedT.first.tile);
          final run = Tiles.suit(sortedT[0].tile) < 3 &&
              Tiles.suit(sortedT[0].tile) == Tiles.suit(sortedT[2].tile) &&
              sortedT[1].tile == sortedT[0].tile + 1 &&
              sortedT[2].tile == sortedT[0].tile + 2;
          final kind = switch (raw) {
            'pon' => same ? 'pon' : fail('$at: 퐁 묶음이 같은 패 3장이 아님 [${_codes(tiles)}]'),
            'chi' => run ? 'chi' : fail('$at: 치 묶음이 이어진 3장이 아님 [${_codes(tiles)}]'),
            'call' => same ? 'pon' : (run ? 'chi' : fail('$at: 종류 모르는 울기 묶음이 퐁도 치도 아님 [${_codes(tiles)}]')),
            _ => fail('$at: 모르는 울기 종류 "$raw"'),
          };
          final from = e.from;
          if (from == null || from < 0 || from > 3 || from == s) fail('$at: 울기의 from 이 잘못됨: $from');
          final ld = lastDiscard;
          if (ld == null || ld.$1 != from) fail('$at: 직전 버림이 자리 $from 의 것이 아님(울 패 없음)');
          if (kind == 'chi' && from != (s + 3) % 4) fail('$at: 치는 윗자리(자리 ${(s + 3) % 4})에서만 — from $from');
          if (riichiDone[s]) fail('$at: 리치한 자리가 울음');
          final own = [...tiles];
          if (!own.remove(ld.$2)) fail('$at: 묶음 [${_codes(tiles)}] 에 가져간 패 ${ld.$2.code} 가 없음');
          if (s == hero) {
            if (heroHand == null) fail('$at: 손패가 적히기 전 hero 울기(지원 안 함)');
            if (heroDrawn) fail('$at: hero 가 뽑은 뒤 울음');
            final after = [...heroHand];
            for (final o in own) {
              if (!after.remove(o)) fail('$at: hero 손에 울기에 쓸 ${o.code} 가 없음');
            }
            if (e.hand == null) fail('$at: 손패가 적힌 뒤 hero 울기 손패가 빔');
            if (!_sameTiles(e.hand!, after)) {
              fail('$at: hero 울기 뒤 손패가 다름 — 적힌 [${_codes(e.hand!)}] / 계산 [${_codes(after)}]');
            }
            heroHand = after;
          }
          steps[s].add(_Call(kind, ld.$2, own, from));
          callCount[s]++;
          afterCall[s] = true;
          lastDiscard = null;
      }
    }
    if (heroHand == null || heroStart == null) fail('hero(자리 $hero) 손패가 적힌 뽑기가 없음 — 배패를 정할 수 없음');
    if (afterCall.any((x) => x)) fail('울기 뒤 버림 없이 끝남');

    // ── 결과 ──
    final r = p.result;
    final rType = r?.type ?? 'draw';
    int? winner, loser;
    if (rType == 'ron' || rType == 'tsumo') {
      winner = r!.winner;
      if (winner == null || winner < 0 || winner > 3) fail('화료자가 잘못됨: $winner');
      if (rType == 'ron') {
        loser = r.loser;
        if (loser == null || loser < 0 || loser > 3 || loser == winner) fail('방총자가 잘못됨: $loser');
        final last = p.events.isEmpty ? null : p.events.last;
        if (last == null || last.type != PaifuEventType.discard || last.seat != loser) fail('론인데 마지막 사건이 방총자(자리 $loser)의 버림이 아님');
        if (r.winTile != null && r.winTile != last.tile) fail('론 화료패 ${r.winTile!.code} ≠ 방총자의 마지막 버림 ${last.tile!.code}');
        if (heroDrawn) fail('론으로 끝났는데 hero 가 뽑고 안 버림');
      } else {
        loser = winner;
        if (winner == hero) {
          if (!heroDrawn) fail('hero 쯔모 화료인데 마지막 hero 사건이 뽑기가 아님');
          if (r.winTile != null && r.winTile != heroDrawStep!.tile) fail('쯔모 화료패 ${r.winTile!.code} ≠ hero 가 마지막에 뽑은 ${heroDrawStep.tile!.code}');
        } else {
          if (heroDrawn) fail('자리 $winner 쯔모로 끝났는데 hero 가 뽑고 안 버림');
          steps[winner].add(_Draw(r.winTile));
        }
      }
      if (winner == hero && r.hand != null && !_sameTiles(r.hand!, heroHand)) {
        fail('결과의 hero 끝 손패 [${_codes(r.hand!)}] ≠ 사건으로 계산한 손패 [${_codes(heroHand)}]');
      }
      if (r.melds.any((x) => x.kind.contains('kan'))) fail('결과 울기에 깡이 있음(지원 안 함)');
      if (r.melds.length != callCount[winner]) fail('결과 울기 ${r.melds.length}개 ≠ 사건의 화료자 울기 ${callCount[winner]}개');
    } else if (rType == 'draw') {
      if (heroDrawn) fail('유국인데 hero 가 뽑고 안 버림');
    } else {
      fail('모르는 결과 종류: $rType');
    }

    // ── 안 보인 패 더미(B-2 의 6) ──
    final used = <PaifuTile, int>{};
    void use(Iterable<PaifuTile> ts) {
      for (final t in ts) {
        tenhouTileNumber(t);
        used[t] = (used[t] ?? 0) + 1;
      }
    }

    use(heroStart);
    for (final st in steps[hero]) {
      if (st is _Draw) use([st.tile!]);
    }
    final givenEnd = <int, List<PaifuTile>>{};
    for (var s = 0; s < 4; s++) {
      if (s == hero) continue;
      for (final st in steps[s]) {
        if (st is _Discard) use([st.tile]);
        if (st is _Call) use(st.own);
        if (st is _Draw && st.tile != null) use([st.tile!]); // 다른 자리 쯔모 화료패
      }
    }
    if (winner != null && winner != hero && r!.hand != null) {
      final need = 13 - 3 * callCount[winner];
      if (r.hand!.length != need) fail('자리 $winner 의 끝 손패가 ${r.hand!.length}장(울기 ${callCount[winner]}번이면 $need장)');
      givenEnd[winner] = [...r.hand!];
      use(r.hand!);
    }
    use(p.doraIndicators);
    use(p.uraIndicators);
    final pile = <PaifuTile>[];
    for (var k = 0; k < Tiles.count; k++) {
      final five = k < Tiles.east && Tiles.number(k) == 5;
      for (final red in [false, true]) {
        if (red && !five) continue;
        final cap = red ? 1 : (five ? 3 : 4);
        final t = PaifuTile(k, red: red);
        final n = used[t] ?? 0;
        if (n > cap) {
          fail(red
              ? '적5 ${t.code} 가 $n장 쓰임(한 수트에 한 장)'
              : '${t.code} 가 $n장 쓰임(최대 $cap장${five ? ' — 적5 한 장 + 보통 세 장' : ''}) — 같은 패 5장째');
        }
        for (var j = n; j < cap; j++) {
          pile.add(t);
        }
      }
    }
    final pileSize = pile.length;

    // ── 다른 자리 되감기 ──
    final rng = Random(seed);
    PaifuTile pick(List<PaifuTile> from) {
      if (from.isEmpty) fail('안 보인 패가 모자람');
      return from.removeAt(rng.nextInt(from.length));
    }

    final haipai = <int, List<PaifuTile>>{hero: _sorted(heroStart)};
    final endInfo = <String>[];
    for (var s = 0; s < 4; s++) {
      if (s == hero) continue;
      final st = steps[s];
      if (st.isNotEmpty && st.last is _Draw && (st.last as _Draw).tile == null) {
        (st.last as _Draw).tile = pick(pile); // 화료패가 안 적힌 쯔모 화료
      }
      final need = 13 - 3 * callCount[s];
      final h = givenEnd[s] ?? [for (var j = 0; j < need; j++) pick(pile)];
      endInfo.add('천봉 자리 ${ts(s)} 끝 손패 $need장${givenEnd.containsKey(s) ? '(패보에 적힌 것)' : ''}');
      var melds = callCount[s];
      _Discard? next;
      for (var j = st.length - 1; j >= 0; j--) {
        final x = st[j];
        switch (x) {
          case _Discard():
            assert(h.length == 13 - 3 * melds);
            h.add(x.tile);
            next = x;
          case _Draw():
            if (next == null) {
              // 쯔모 화료의 마지막 뽑기 — 손에 넣지 않는다.
              assert(j == st.length - 1);
              continue;
            }
            assert(h.length == 14 - 3 * melds);
            if (next.tsumogiri) {
              final ok = h.remove(next.tile);
              assert(ok);
              x.tile = next.tile;
            } else {
              final d = next.tile;
              var cand = [for (final c in h) if (c.tile != d.tile) c];
              if (cand.isEmpty) cand = [...h];
              final c = cand[rng.nextInt(cand.length)];
              h.remove(c);
              x.tile = c;
            }
            next = null;
          case _Call():
            assert(h.length == 14 - 3 * melds);
            // 울기 뒤 버림은 이미 되돌렸다. 울기를 되돌리면 내 패 둘이 손으로.
            h.addAll(x.own);
            melds--;
            next = null;
        }
      }
      if (h.length != 13) fail('자리 $s 배패를 되감았더니 ${h.length}장(13장이어야 함)');
      haipai[s] = _sorted(h);
    }

    // ── 천봉 목록 ──
    String callString(int s, _Call c) {
      final taken = tenhouTileNumber(c.taken);
      final own = _sorted(c.own).map(tenhouTileNumber).toList();
      if (c.kind == 'chi') return 'c$taken${own[0]}${own[1]}';
      return switch ((c.from - s) % 4) {
        3 => 'p$taken${own[0]}${own[1]}',
        2 => '${own[0]}p$taken${own[1]}',
        1 => '${own[0]}${own[1]}p$taken',
        _ => fail('퐁 방향이 잘못됨'),
      };
    }

    final draws = List<List<Object>>.generate(4, (_) => []);
    final discards = List<List<Object>>.generate(4, (_) => []);
    final hands = List<List<int>>.generate(4, (_) => []);
    for (var s = 0; s < 4; s++) {
      final t = ts(s);
      hands[t] = haipai[s]!.map(tenhouTileNumber).toList();
      for (final x in steps[s]) {
        switch (x) {
          case _Draw():
            draws[t].add(tenhouTileNumber(x.tile!));
          case _Call():
            draws[t].add(callString(s, x));
          case _Discard():
            final v = x.tsumogiri ? 60 : tenhouTileNumber(x.tile);
            discards[t].add(x.riichi ? 'r$v' : v);
        }
      }
    }

    final sc = scores ?? const [25000, 25000, 25000, 25000];
    final scoresT = List<int>.filled(4, 0);
    for (var s = 0; s < 4; s++) {
      scoresT[ts(s)] = sc[s];
    }
    final List<Object> resultJson = winner == null
        ? ['流局', [0, 0, 0, 0]]
        : ['和了', [0, 0, 0, 0], [ts(winner), ts(loser!), ts(winner), '']];

    final log = <Object>[
      [kyoku, p.honba, 0],
      scoresT,
      p.doraIndicators.map(tenhouTileNumber).toList(),
      p.uraIndicators.map(tenhouTileNumber).toList(),
      for (var t = 0; t < 4; t++) ...[hands[t], draws[t], discards[t]],
      resultJson,
    ];
    final json = <String, dynamic>{
      'title': ['', ''],
      'name': ['A', 'B', 'C', 'D'],
      'rule': {'disp': '般南喰赤', 'aka': 1},
      'log': [log],
    };

    // ── 스스로 재생해 본다(B-1 규칙). 안 맞으면 내보내지 않는다. ──
    final replayOrder = _selfReplay(hands, draws, discards, kyoku % 4, rType);
    final paifuOrder = [
      for (final e in p.events)
        if (e.type == PaifuEventType.discard) ts(e.seat),
    ];
    var orderDiff = 0, firstDiff = -1;
    for (var k = 0; k < paifuOrder.length; k++) {
      if (k >= replayOrder.length || replayOrder[k] != paifuOrder[k]) {
        orderDiff++;
        if (firstDiff < 0) firstDiff = k;
      }
    }

    // ── assumptions(B-2 의 번호 순) ──
    String seats(List<int> v) => v.join(', ');
    final as = <String>[
      scores == null
          ? '1. 점수: 인자로 안 줘서 네 자리 25000, 공탁 0'
          : '1. 점수: 인자 [${seats(scores!)}](우리 자리 순) → 천봉 자리 순 [${seats(scoresT)}], 공탁 0',
      p.startHand != null && heroKnownFrom == 0
          ? '2. hero 배패: start_hand 그대로(앞 순 지어 채움 없음)'
          : '2. hero 배패: hero 손패가 처음 적힌 것은 $heroKnownFrom번째 뽑기 — 그 앞 $heroAssumedTurns 차례는 쯔모기리로 봄(뽑은 패 = 버린 패, 버림 60), 배패 = 그 첫 손패',
      '3. hero 손패 검사: 손패가 적힌 뒤 버림 $heroChecked번 모두 손패 + 뽑은 패 − 버린 패 = 다음 손패(적5 포함)',
      '4. hero 버림 표기: 버린 패가 뽑은 패와 같고 패보가 손에서 냄(false)이라 하지 않으면 60 — 60 $heroTg장, 수 $heroTd장',
      '5. 다른 자리 버림 ${oTrue + oFalse + oNull}장: 패보에 쯔모기리 $oTrue · 손에서 냄 $oFalse · 모름 $oNull — '
          '모름 중 울기 바로 뒤 $oNullAfterCall장은 손에서 냄, 리치 뒤 $oNullAfterRiichi장은 60, '
          '나머지 $oNullPolicy장은 정책 unknownAs=${unknownAs.name} 로 ${unknownAs == UnknownDiscard.tedashi ? '손에서 냄(수)' : '쯔모기리(60)'}',
      '6. 다른 자리 배패 · 뽑은 패: 안 보인 패 $pileSize장에서 시드 $seed 로 지어 채움(${endInfo.join(' · ')}). '
          '사건을 거꾸로 되감아 배패를 만들었고, 손에서 낸 차례의 뽑은 패는 버린 패와 다른 종류를 우선으로 고름',
      p.doraIndicators.length > 1
          ? '7. 도라: 표시패 [${p.doraIndicators.map((t) => t.code).join(' ')}] 그대로 — 첫 장 ${p.doraIndicators.first.code} 만 도라 표시패로 쓰이고 나머지는 깡이 없어 안 쓰임(도라 + 뒷도라가 섞여 적혔을 수 있음, 구분이 없어 첫 장을 도라로 봄). 뒷도라 [${p.uraIndicators.map((t) => t.code).join(' ')}]'
          : '7. 도라: 표시패 [${p.doraIndicators.map((t) => t.code).join(' ')}] · 뒷도라 [${p.uraIndicators.map((t) => t.code).join(' ')}] 그대로',
      '결과: ${winner == null ? '流局(${r == null ? '패보에 결과 없음' : '유국'})' : '和了 — 화료 천봉 자리 ${ts(winner)}, ${rType == 'ron' ? '방총 천봉 자리 ${ts(loser!)}' : '쯔모'}'}, 점수 변화는 0 으로 둠',
      if (orderDiff > 0)
        '재생 순서: 천봉 재생의 버림 차례가 패보 사건 순서와 $orderDiff곳 다름(첫 곳: 패보 ${firstDiff + 1}번째 버림, 천봉 자리 ${paifuOrder[firstDiff]}) — 자리별 버림 · 울기 순서는 그대로',
    ];

    return Tenhou6Export(json, heroIndex, as);
  }

  /// B-1 규칙대로 돌려 본다. 버림이 일어난 자리 순서를 돌려준다.
  List<int> _selfReplay(List<List<int>> hands, List<List<Object>> draws, List<List<Object>> discards, int oya, String rType) {
    final hand = [for (final h in hands) [...h]];
    final di = [0, 0, 0, 0], xi = [0, 0, 0, 0];
    final order = <int>[];
    for (var t = 0; t < 4; t++) {
      if (hand[t].length != 13) fail('재생: 자리 $t 배패가 ${hand[t].length}장');
    }
    bool allDone() => [for (var t = 0; t < 4; t++) di[t] == draws[t].length && xi[t] == discards[t].length].every((x) => x);
    var actor = oya;
    (int, int)? last; // (자리, 패)
    for (var guard = 0; guard < 1000; guard++) {
      if (di[actor] >= draws[actor].length) fail('재생: 천봉 자리 $actor 차례인데 뽑기 목록이 다 씀');
      final take = draws[actor][di[actor]++];
      int? drawn;
      if (take is int) {
        if (take == 60) fail('재생: 뽑기 목록에 60');
        hand[actor].add(take);
        drawn = take;
      } else {
        final c = _parseCall(take as String, actor);
        if (last == null || last.$1 != c.$1 || last.$2 != c.$2) fail('재생: 천봉 자리 $actor 의 울기 $take 가 직전 버림과 안 맞음');
        for (final o in c.$3) {
          if (!hand[actor].remove(o)) fail('재생: 천봉 자리 $actor 손에 울기에 쓸 $o 가 없음');
        }
      }
      if (xi[actor] == discards[actor].length) {
        if (allDone() && rType == 'tsumo' && drawn != null) return order;
        fail('재생: 천봉 자리 $actor 버림 목록이 먼저 다 씀');
      }
      final dv = discards[actor][xi[actor]++];
      final s = dv is String ? dv.substring(1) : '$dv';
      var tile = int.parse(s);
      if (tile == 60) {
        if (drawn == null) fail('재생: 울기 뒤 60');
        tile = drawn;
      }
      if (!hand[actor].remove(tile)) fail('재생: 천봉 자리 $actor 손에 없는 $tile 를 버림');
      order.add(actor);
      last = (actor, tile);
      if (allDone()) {
        if (rType == 'tsumo') fail('재생: 쯔모인데 버림으로 끝남');
        return order;
      }
      var next = (actor + 1) % 4;
      for (var k = 1; k <= 3; k++) {
        final t = (actor + k) % 4;
        if (di[t] < draws[t].length && draws[t][di[t]] is String) {
          final c = _parseCall(draws[t][di[t]] as String, t);
          if (c.$1 == actor && c.$2 == tile) {
            next = t;
            break;
          }
        }
      }
      actor = next;
    }
    fail('재생: 끝나지 않음');
  }

  /// 울기 문자열 → (가져온 자리, 가져온 패, 내 패 둘).
  (int, int, List<int>) _parseCall(String s, int me) {
    int at(int i) => int.parse(s.substring(i, i + 2));
    if (s.length == 7 && s[0] == 'c') return ((me + 3) % 4, at(1), [at(3), at(5)]);
    if (s.length == 7) {
      final k = s.indexOf('p');
      if (k == 0) return ((me + 3) % 4, at(1), [at(3), at(5)]);
      if (k == 2) return ((me + 2) % 4, at(3), [at(0), at(5)]);
      if (k == 4) return ((me + 1) % 4, at(5), [at(0), at(2)]);
    }
    fail('재생: 모르는 울기 문자열 $s');
  }
}
