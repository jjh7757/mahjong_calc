// tenhou.net/6 한 판 → 국마다 · 자리마다(그 자리를 hero 로) 재생해 hero 버림마다 엔진 값 JSON 한 줄.
// 설계서 docs/mxplainer_fit_design_1121.md 7절 1번(①값 뽑기). 화면 없이 도는 순수 Dart(Flutter 를 쓰지 않음).
//
//   dart run tool/tenhou6_features.dart <tenhou6.json> [--seats 0,1,2,3] [--out <파일.jsonl>]
//
// 엔진 입력은 lib/paifu/mh_context.dart · paifu_review.dart 와 같은 뜻이 되게, 천봉 한 국을 hero 시점의 [Paifu] 로
// 바꿔(hero 손패 · 뽑기 · 네 자리 버림(쯔모기리 · 리치 진짜 값) · 울기) [discardContextAt] · [riskContextAt] 를 그대로 쓴다.
// 보이는 패 셈 · 위협 자리 규칙은 paifu_review.dart 의 `_review` · `_riskAt`(비공개) 을 옮겨 적었다.
//
// - 깡이 든 국(뽑기 줄에 `m` 든 문자열, 버림 줄에 `a` · `k` 든 문자열)은 통째로 건너뛴다.
// - 재생 중 검사(손패 장수 = 14 − 3 × 울기, 버리는 패가 손에 있음, 같은 종류 보이는 패 + 손패 ≤ 4)가 어긋나면
//   그 국 · 자리를 오류로 세고 줄을 내지 않는다.
// - 끝에 `{"summary": …}` 한 줄.
import 'dart:convert';
import 'dart:io';

import 'package:mahjong_calc/engine/discard_rank.dart';
import 'package:mahjong_calc/engine/efficiency.dart';
import 'package:mahjong_calc/engine/risk.dart';
import 'package:mahjong_calc/engine/shanten.dart';
import 'package:mahjong_calc/engine/tile.dart';
import 'package:mahjong_calc/paifu/mh_context.dart';
import 'package:mahjong_calc/paifu/paifu.dart';

/// 재생 · 검사 실패.
class ReplayError implements Exception {
  final String message;
  const ReplayError(this.message);
  @override
  String toString() => 'ReplayError: $message';
}

/// 천봉 패 번호 → 패.
PaifuTile tenhouTile(int code) {
  if (code == 51 || code == 52 || code == 53) return PaifuTile((code - 51) * 9 + 4, red: true);
  final s = code ~/ 10, n = code % 10;
  if (s >= 1 && s <= 3 && n >= 1 && n <= 9) return PaifuTile((s - 1) * 9 + n - 1);
  if (s == 4 && n >= 1 && n <= 7) return PaifuTile(Tiles.east + n - 1);
  throw ReplayError('모르는 천봉 패 번호 $code');
}

/// 패 코드, 적5 는 5 로 접음(`5m`).
String foldCode(int tile) => Tiles.toCode(tile);

/// 깡이 든 국인가.
bool hasKan(List log) {
  for (var p = 0; p < 4; p++) {
    for (final t in log[5 + 3 * p] as List) {
      if (t is String && t.contains('m')) return true;
    }
    for (final d in log[6 + 3 * p] as List) {
      if (d is String && (d.contains('a') || d.contains('k'))) return true;
    }
  }
  return false;
}

/// 울기 문자열 → (글자, 글자 위치, 묶음 패 번호들, 가져온 패 번호). mortal_local.py `split_call` 과 같음.
(String, int, List<int>, int) _splitCall(String s) {
  var pos = -1;
  for (var i = 0; i < s.length; i++) {
    final c = s.codeUnitAt(i);
    if ((c >= 65 && c <= 90) || (c >= 97 && c <= 122)) {
      pos = i;
      break;
    }
  }
  if (pos < 0) throw ReplayError('울기 문자열에 글자가 없음: $s');
  final nums = s.substring(0, pos) + s.substring(pos + 1);
  final tiles = [for (var k = 0; k + 1 < nums.length; k += 2) int.parse(nums.substring(k, k + 2))];
  final called = int.parse(s.substring(pos + 1, pos + 3));
  return (s[pos], pos, tiles, called);
}

int _norm(int x) => switch (x) { 51 => 15, 52 => 25, 53 => 35, _ => x };

String _roundName(int kidx) => '${const ['동', '남', '서', '북'][(kidx ~/ 4) % 4]}${kidx % 4 + 1}국';

/// 천봉 한 국(log 한 칸) → hero 시점 [Paifu]. 남의 손패 · 뽑은 패는 넣지 않는다.
/// 차례 규칙은 mortal_local.py `to_mjai` 와 같다(버림 뒤 울기 찾기는 퐁 · 깡이 치보다 먼저).
Paifu kyokuToPaifu(List log, int hero, {String id = ''}) {
  final head = log[0] as List;
  final kidx = head[0] as int, honba = head[1] as int;
  final doras = [for (final d in log[2] as List) tenhouTile(d as int)];
  final hai = [for (var p = 0; p < 4; p++) log[4 + 3 * p] as List];
  final takes = [for (var p = 0; p < 4; p++) log[5 + 3 * p] as List];
  final discs = [for (var p = 0; p < 4; p++) log[6 + 3 * p] as List];
  final oya = kidx % 4;
  final hand = [for (final t in hai[hero]) tenhouTile(t as int)];
  if (hand.length != 13) throw ReplayError('hero 배패가 ${hand.length}장');
  final events = <PaifuEvent>[];
  final ti = [0, 0, 0, 0], di = [0, 0, 0, 0];
  var actor = oya;
  var calledIn = false;
  for (var guard = 0; guard < 400; guard++) {
    int? drawn;
    if (!calledIn) {
      if (ti[actor] >= takes[actor].length) break; // 유국 등
      final t = takes[actor][ti[actor]++];
      if (t is String) throw ReplayError('순서 어긋남: 자리 $actor 의 뽑기 자리에 울기 $t');
      drawn = t as int;
      if (actor == hero) {
        final dt = tenhouTile(drawn);
        events.add(PaifuEvent(type: PaifuEventType.draw, seat: hero, tile: dt, hand: List.unmodifiable(hand)));
        hand.add(dt);
      }
    }
    if (di[actor] >= discs[actor].length) break; // 쯔모 화료 · 구종구패
    var d = discs[actor][di[actor]++];
    var reach = false;
    if (d is String) {
      if (!d.startsWith('r')) throw ReplayError('지원 안 하는 버림 표기 $d(깡)');
      reach = true;
      d = int.parse(d.substring(1));
    }
    final int pai;
    final bool tg;
    if (d == 60) {
      if (drawn == null) throw ReplayError('울기 뒤 60(자리 $actor)');
      pai = drawn;
      tg = true;
    } else {
      pai = d as int;
      tg = false;
    }
    final pt = tenhouTile(pai);
    if (actor == hero) {
      if (!hand.remove(pt)) throw ReplayError('hero 가 손에 없는 ${pt.code} 를 버림');
    }
    events.add(PaifuEvent(
      type: PaifuEventType.discard,
      seat: actor,
      tile: pt,
      tsumogiri: tg,
      riichi: reach,
      hand: actor == hero ? List.unmodifiable(hand) : null,
    ));
    // 울기 찾기(퐁 · 깡이 치보다 먼저).
    (int, String, List<int>, int)? caller;
    for (var off = 1; off <= 3; off++) {
      final p = (actor + off) % 4;
      if (ti[p] < takes[p].length && takes[p][ti[p]] is String) {
        final (letter, pos, tiles, called) = _splitCall(takes[p][ti[p]] as String);
        final src = letter != 'c' ? const {0: 3, 2: 2, 4: 1, 6: 1}[pos] : 3;
        if (src == null) throw ReplayError('울기 문자열 위치가 이상함: ${takes[p][ti[p]]}');
        if ((p + src) % 4 == actor && _norm(called) == _norm(pai)) {
          if (caller == null || letter != 'c') caller = (p, letter, tiles, called);
        }
      }
    }
    if (caller != null) {
      final (p, letter, tiles, called) = caller;
      ti[p]++;
      if (letter != 'c' && letter != 'p') throw ReplayError('지원 안 하는 울기 $letter');
      final consumed = [...tiles]..remove(called);
      if (p == hero) {
        for (final c in consumed) {
          if (!hand.remove(tenhouTile(c))) throw ReplayError('hero 손에 울기에 쓸 ${tenhouTile(c).code} 가 없음');
        }
      }
      events.add(PaifuEvent(
        type: PaifuEventType.call,
        seat: p,
        callKind: letter == 'c' ? 'chi' : 'pon',
        callTiles: [for (final t in tiles) tenhouTile(t)],
        from: actor,
        hand: p == hero ? List.unmodifiable(hand) : null,
      ));
      actor = p;
      calledIn = true;
      continue;
    }
    final nxt = (actor + 1) % 4;
    if (ti[nxt] >= takes[nxt].length) break; // 이 버림으로 론(또는 유국)
    actor = nxt;
    calledIn = false;
  }
  return Paifu(
    id: id,
    round: _roundName(kidx),
    honba: honba,
    dealer: oya,
    hero: hero,
    doraIndicators: doras,
    events: events,
  );
}

/// NaN · 무한은 null.
double? _fin(double? x) => x == null || !x.isFinite ? null : x;

bool _valid(int t) => t >= 0 && t < Tiles.count;

/// 보이는 패(paifu_review.dart `_review` 와 같은 셈): 강(울려 나간 것 빼고) + 모든 울기 묶음 + 도라 표시패.
List<int> visibleAt(Paifu p, PaifuState st) {
  final visible = List<int>.filled(Tiles.count, 0);
  void see(PaifuTile t) {
    if (_valid(t.tile)) visible[t.tile]++;
  }

  for (var s = 0; s < 4; s++) {
    for (final r in st.rivers[s]) {
      if (!r.called) see(r.tile);
    }
    for (final m in st.melds[s]) {
      m.tiles.forEach(see);
    }
  }
  p.doraIndicators.forEach(see);
  return visible;
}

/// 위협 자리(paifu_review.dart `_riskAt` 규칙): (리치 또는 안깡 아닌 울기) 그리고 텐파이율 > 15.
List<int> riskSeatsOf(RiskTable table, PaifuState st) => [
      for (final o in table.opponents)
        if ((o.riichi || st.melds[o.seat].any((m) => meldKindOf(m.kind, m.tiles, o.seat, m.from) != MeldKind.ankan)) &&
            o.tenpaiRate > 15)
          o.seat,
    ]..sort();

/// 한 국 · 한 자리의 hero 버림마다 한 줄. [engineAfterRiichi] 면 hero 리치 뒤 버림에도 엔진 값을 채운다(시험용).
/// 검사가 어긋나면 [ReplayError].
List<Map<String, Object?>> kyokuSeatRows(List log, int hero,
    {required String game, required int kyoku, bool engineAfterRiichi = false}) {
  final p = kyokuToPaifu(log, hero, id: game);
  final states = p.states;
  final head = log[0] as List;
  final kidx = head[0] as int;
  final scores = [for (final s in log[1] as List) s as int];
  final roundWind = Tiles.east + (kidx ~/ 4) % 4;
  final seatWind = Tiles.east + p.windOf(hero);
  final doraTiles = [for (final t in p.doraIndicators) Tiles.doraFromIndicator(t.tile)];
  final rows = <Map<String, Object?>>[];
  var k = 0;
  for (final (i, e) in p.events.indexed) {
    if (e.type != PaifuEventType.discard || e.seat != hero) continue;
    final sw = Stopwatch()..start();
    final st = states[i];
    final discard = e.tile!;
    final melds = st.melds[hero].length;
    // 이 버림 앞 hero 사건(뽑기 또는 울기).
    PaifuEvent? prev;
    for (var j = i - 1; j >= 0; j--) {
      final f = p.events[j];
      if (f.seat != hero) continue;
      if (f.type == PaifuEventType.draw || f.type == PaifuEventType.call) prev = f;
      break;
    }
    if (prev == null) throw ReplayError('hero $k번째 버림 앞에 뽑기 · 울기가 없음');
    final afterCall = prev.type == PaifuEventType.call;
    final beforeTiles = afterCall ? [...prev.hand!] : [...prev.hand!, prev.tile!];
    final before = List<int>.filled(Tiles.count, 0);
    for (final t in beforeTiles) {
      before[t.tile]++;
    }
    final sum = before.fold(0, (a, b) => a + b);
    if (sum != 14 - 3 * melds) throw ReplayError('hero $k번째 버림: 손패 $sum장 ≠ ${14 - 3 * melds}');
    if (before[discard.tile] == 0) throw ReplayError('hero $k번째 버림: ${discard.code} 가 손에 없음');
    final visible = visibleAt(p, st);
    for (var t = 0; t < Tiles.count; t++) {
      if (visible[t] + before[t] > 4) {
        throw ReplayError('hero $k번째 버림: ${Tiles.toCode(t)} 보이는 패 ${visible[t]} + 손패 ${before[t]} > 4');
      }
    }
    final afterRiichi = st.riichi[hero];
    final riichiSeats = [
      for (var s = 0; s < 4; s++)
        if (s != hero && st.riichi[s]) s,
    ];
    final row = <String, Object?>{
      'game': game,
      'kyoku': kyoku,
      'kyokuNum': kidx,
      'honba': head[1],
      'seat': hero,
      'k': k,
      'afterCall': afterCall,
      'afterRiichi': afterRiichi,
      'riichiDeclared': e.riichi,
      'actual': foldCode(discard.tile),
      'actualRed': discard.red,
      'drawn': afterCall ? null : foldCode(prev.tile!.tile),
      'junme': k + 1,
      'wallLeft': st.wallLeft,
      'heroMelds': melds,
      'menzen': melds == 0,
      'dealer': hero == p.dealer,
      'scores': scores,
      'riichiSeats': riichiSeats,
    };
    k++;
    if (afterRiichi && !engineAfterRiichi) {
      rows.add(row);
      continue;
    }
    final shantenBefore = shanten(before, melds: melds);
    final options = discardOptions(before, melds: melds, visible: visible);
    final ctx = discardContextAt(p, i, handBefore: beforeTiles, visible34: visible);
    if (ctx == null) throw ReplayError('hero $k번째 버림: DiscardContext 를 만들 수 없음');
    final r = analyzeDiscards(ctx);
    final table = riskOf(riskContextAt(p, i, handBefore: beforeTiles, visible34: visible));
    final rSeats = riskSeatsOf(table, st);
    sw.stop();
    final byTile = {for (final d in r.all) d.tile: d};
    final optBy = {for (final o in options) o.tile: o};
    final mhForwardBest = r.forward.isNotEmpty ? r.forward.first.tile : r.best;
    final mhOrder = [
      ?r.best,
      for (final d in r.all)
        if (d.tile != r.best) d.tile,
    ];
    var maxTenpai = 0.0;
    for (final o in table.opponents) {
      if (o.tenpaiRate > maxTenpai) maxTenpai = o.tenpaiRate;
    }
    final redHeld = [false, false, false];
    for (final t in beforeTiles) {
      if (t.red && t.tile < 27 && t.tile % 9 == 4) redHeld[t.tile ~/ 9] = true;
    }
    final cands = <Map<String, Object?>>[];
    for (var t = 0; t < Tiles.count; t++) {
      if (before[t] == 0) continue;
      final d = byTile[t];
      final o = optBy[t]!;
      var yakuhai = 0;
      if (Tiles.isDragon(t)) yakuhai = 1;
      if (t == roundWind) yakuhai++;
      if (t == seatWind) yakuhai++;
      cands.add({
        'tile': Tiles.toCode(t),
        'n': before[t],
        'shanten': d?.shanten,
        'backward': d?.isBackward,
        'waits': d?.waitsCount,
        'improve': _fin(d?.avgImproveWaitsCount),
        'nextWaits': _fin(d?.avgNextShantenWaitsCount),
        'speed': _fin(d?.speedScore),
        'agariRate': _fin(d?.agariRate),
        'roundPoint': _fin(d?.roundPoint),
        'damaPoint': _fin(d?.damaPoint),
        'riichiPoint': _fin(d?.riichiPoint),
        'furitenRate': _fin(d?.furitenRate),
        'b0Shanten': o.shanten,
        'b0Ukeire': o.ukeire.total,
        'risk': _fin(table.mixed34[t]),
        'safeAll': table.safeForAll34[t],
        'dora': doraTiles.where((x) => x == t).length,
        'red': t < 27 && t % 9 == 4 && redHeld[t ~/ 9],
        'yakuhai': yakuhai,
        'guestWind': Tiles.isWind(t) && t != roundWind && t != seatWind,
        'terminal': Tiles.isTerminal(t),
        'honor': Tiles.isHonor(t),
      });
    }
    row.addAll({
      'shantenBefore': shantenBefore,
      'riskSeats': rSeats,
      'maxTenpaiRate': _fin(maxTenpai),
      'riskOfActual': rSeats.isEmpty ? null : _fin(table.mixed34[discard.tile]),
      'b0Order': [for (final o in options) Tiles.toCode(o.tile)],
      'mhBest': r.best == null ? null : Tiles.toCode(r.best!),
      'mhForwardBest': mhForwardBest == null ? null : Tiles.toCode(mhForwardBest),
      'mhOrder': [for (final t in mhOrder) Tiles.toCode(t)],
      'recommendBackward': r.recommendBackward,
      'secs': sw.elapsedMicroseconds / 1e6,
      'candidates': cands,
    });
    rows.add(row);
  }
  return rows;
}

/// 한 판 전체. [onRows] 에 국 · 자리마다 줄을 넘기고 요약을 돌려준다.
Map<String, Object?> gameFeatures(Map<String, dynamic> json,
    {required String game, List<int> seats = const [0, 1, 2, 3], void Function(List<Map<String, Object?>>)? onRows}) {
  final logs = json['log'] as List;
  var kanSkipped = 0, errors = 0, rowsN = 0;
  final errorList = <String>[];
  final ksSecs = <double>[];
  final total = Stopwatch()..start();
  for (final (ki, log) in logs.indexed) {
    final l = log as List;
    if (hasKan(l)) {
      kanSkipped++;
      continue;
    }
    for (final seat in seats) {
      final sw = Stopwatch()..start();
      try {
        final rows = kyokuSeatRows(l, seat, game: game, kyoku: ki);
        rowsN += rows.length;
        onRows?.call(rows);
      } on ReplayError catch (err) {
        errors++;
        errorList.add('국 $ki 자리 $seat: ${err.message}');
      } catch (err) {
        // 엔진 · 패보 쪽 예외도 그 국 · 자리를 오류로 센다(종류를 남김).
        errors++;
        errorList.add('국 $ki 자리 $seat: 예외 ${err.runtimeType}: $err');
      }
      ksSecs.add(sw.elapsedMicroseconds / 1e6);
    }
  }
  return {
    'game': game,
    'kyokus': logs.length,
    'kanSkipped': kanSkipped,
    'kyokuSeats': ksSecs.length,
    'errors': errors,
    'errorList': errorList,
    'rows': rowsN,
    'kyokuSeatSecs': ksSecs,
    'secs': total.elapsedMicroseconds / 1e6,
  };
}

const _usage = '쓰는 법: dart run tool/tenhou6_features.dart <tenhou6.json> [--seats 0,1,2,3] [--out <파일.jsonl>]';

Future<void> main(List<String> args) async {
  String? src, out;
  var seats = [0, 1, 2, 3];
  for (var i = 0; i < args.length; i++) {
    final a = args[i];
    if (a == '--seats' || a == '--out') {
      if (i + 1 >= args.length) {
        stderr.writeln('$a 뒤에 값이 없습니다\n$_usage');
        exitCode = 64;
        return;
      }
      final v = args[++i];
      if (a == '--out') {
        out = v;
      } else {
        final s = [for (final x in v.split(',')) int.tryParse(x.trim())];
        if (s.isEmpty || s.any((x) => x == null || x < 0 || x > 3)) {
          stderr.writeln('--seats 는 0~3 쉼표 목록: $v');
          exitCode = 64;
          return;
        }
        seats = [for (final x in s) x!];
      }
    } else if (src == null) {
      src = a;
    } else {
      stderr.writeln('인자가 너무 많습니다\n$_usage');
      exitCode = 64;
      return;
    }
  }
  if (src == null) {
    stderr.writeln(_usage);
    exitCode = 64;
    return;
  }
  final f = File(src);
  if (!f.existsSync()) {
    stderr.writeln('파일이 없습니다: $src');
    exitCode = 66;
    return;
  }
  final json = jsonDecode(f.readAsStringSync(encoding: utf8)) as Map<String, dynamic>;
  var game = f.uri.pathSegments.last;
  if (game.endsWith('.json')) game = game.substring(0, game.length - 5);
  final IOSink sink = out == null ? stdout : File(out).openWrite(encoding: utf8);
  final summary = gameFeatures(json, game: game, seats: seats, onRows: (rows) {
    for (final r in rows) {
      sink.add(utf8.encode('${jsonEncode(r)}\n'));
    }
  });
  sink.add(utf8.encode('${jsonEncode({'summary': summary})}\n'));
  if (out != null) {
    await sink.close();
  } else {
    await stdout.flush();
  }
}
