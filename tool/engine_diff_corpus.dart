// 점수 엔진 교차 검증용 손패 묶음을 만든다. 우리 엔진의 답을 같이 적고, tool/engine_diff.py 가 PyPI mahjong 과 비교한다.
//
//   dart run tool/engine_diff_corpus.dart [장수=20000] [시드=1] [출력=build/engine_diff/corpus.jsonl]
//
// 완전 무작위 패는 거의 화료가 안 되고 희귀 역이 안 나와서, 역을 노린 모양(profile)으로 화료형을 먼저 만들고
// 일부만 한 장 바꿔 화료가 아닌 손패도 섞는다. 시드가 같으면 묶음도 같다.
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:mahjong_calc/engine/calculator.dart';

const _man = 0, _pin = 9, _sou = 18;

/// 면자 하나. [seq] 면 슌쯔(가장 낮은 패), 아니면 커쯔.
class _Group {
  final int tile;
  final bool seq;
  const _Group(this.tile, this.seq);
  List<int> get tiles => seq ? [tile, tile + 1, tile + 2] : [tile, tile, tile];
}

/// 면자 4개 + 머리. 모양을 못 맞추면 null 을 돌려 다시 뽑는다.
class _Shape {
  final List<_Group> groups;
  final int pair;
  const _Shape(this.groups, this.pair);
}

class _Gen {
  final Random r;
  _Gen(this.r);

  T pick<T>(List<T> xs) => xs[r.nextInt(xs.length)];
  bool chance(double p) => r.nextDouble() < p;

  List<int> get suits => const [_man, _pin, _sou];
  List<_Group> seqs(int suit, [Iterable<int> numbers = const [1, 2, 3, 4, 5, 6, 7]]) =>
      [for (final n in numbers) _Group(suit + n - 1, true)];
  List<_Group> triplets(Iterable<int> tiles) => [for (final t in tiles) _Group(t, false)];
  List<int> get allTiles => List.generate(Tiles.count, (i) => i);
  List<int> get honors => List.generate(7, (i) => Tiles.east + i);
  List<int> get terminals => [for (final s in suits) ...[s, s + 8]];
  List<int> get simples => [for (var t = 0; t < 27; t++) if (Tiles.isSimple(t)) t];
  List<_Group> get anySeq => [for (final s in suits) ...seqs(s)];

  /// [fixed] 에 [pool] 에서 뽑은 면자를 더해 4개를 채운다. 장수가 넘치면 null.
  _Shape? fill(List<_Group> fixed, List<_Group> pool, List<int> pairs) {
    final groups = [...fixed];
    while (groups.length < 4) {
      groups.add(pick(pool));
    }
    final pair = pick(pairs);
    final counts = toCounts([for (final g in groups) ...g.tiles, pair, pair]);
    return counts.any((c) => c > 4) ? null : _Shape(groups, pair);
  }

  /// 역별로 모양을 노린다. 이름은 코퍼스의 profile 칸에 남아 어느 쪽에서 차이가 났는지 보인다.
  _Shape? shape(String profile) {
    final s = pick(suits);
    switch (profile) {
      case 'any':
        return fill([], [...anySeq, ...triplets(allTiles)], allTiles);
      case 'pinfu':
        return fill([], anySeq, [...simples, for (final t in honors) t]);
      case 'simple':
        final pool = [
          for (final x in suits) ...seqs(x, const [2, 3, 4, 5, 6]),
          ...triplets(simples)
        ];
        return fill([], pool, simples);
      case 'oneSuit':
        return fill([], [...seqs(s), ...triplets(List.generate(9, (i) => s + i))],
            List.generate(9, (i) => s + i));
      case 'halfFlush':
        final tiles = [...List.generate(9, (i) => s + i), ...honors];
        return fill([], [...seqs(s), ...triplets(tiles)], tiles);
      case 'chanta':
        final ends = [...terminals, ...honors];
        return fill([], [for (final x in suits) ...seqs(x, const [1, 7]), ...triplets(ends)], ends);
      case 'junchan':
        return fill([], [for (final x in suits) ...seqs(x, const [1, 7]), ...triplets(terminals)],
            terminals);
      case 'honroutou':
        final ends = [...terminals, ...honors];
        return fill([], triplets(ends), ends);
      case 'chinroutou':
        return fill([], triplets(terminals), terminals);
      case 'toitoi':
        return fill([], triplets(allTiles), allTiles);
      case 'sanshoku':
        final n = 1 + r.nextInt(7);
        return fill([for (final x in suits) _Group(x + n - 1, true)],
            [...anySeq, ...triplets(allTiles)], allTiles);
      case 'sanshokuDoukou':
        final n = r.nextInt(9);
        return fill([for (final x in suits) _Group(x + n, false)],
            [...anySeq, ...triplets(allTiles)], allTiles);
      case 'ittsu':
        return fill(seqs(s, const [1, 4, 7]), [...anySeq, ...triplets(allTiles)], allTiles);
      case 'iipeikou':
        final g = pick(anySeq);
        return fill([g, g], [...anySeq, ...triplets(allTiles)], allTiles);
      case 'ryanpeikou':
        final a = pick(anySeq), b = pick(anySeq);
        return fill([a, a, b, b], const [], allTiles);
      case 'dragons':
        final d = [...honors.sublist(4)]..shuffle(r);
        return fill(triplets(d.take(1 + r.nextInt(3))), [...anySeq, ...triplets(allTiles)],
            [...d, ...allTiles]);
      case 'shousangen':
        final d = [...honors.sublist(4)]..shuffle(r);
        return fill(triplets(d.take(2)), [...anySeq, ...triplets(allTiles)], [d[2]]);
      case 'winds':
        final w = [...honors.sublist(0, 4)]..shuffle(r);
        return fill(triplets(w.take(3)), [...anySeq, ...triplets(allTiles)], [w[3], ...w]);
      case 'daisuushi':
        return fill(triplets(honors.sublist(0, 4)), const [], allTiles);
      case 'tsuuiisou':
        return fill([], triplets(honors), honors);
      case 'green':
        final greens = allTiles.where(Tiles.isGreen).toList();
        return fill([], [_Group(_sou + 1, true), ...triplets(greens)], greens);
    }
    throw ArgumentError(profile);
  }
}

const _shapeProfiles = [
  'any', 'any', 'any', 'pinfu', 'pinfu', 'simple', 'oneSuit', 'halfFlush', 'chanta', 'junchan',
  'honroutou', 'chinroutou', 'toitoi', 'sanshoku', 'sanshokuDoukou', 'ittsu', 'iipeikou',
  'ryanpeikou', 'dragons', 'shousangen', 'winds', 'daisuushi', 'tsuuiisou', 'green',
];

/// 면자 일부를 울기로 돌린다. 깡은 넷째 패가 남을 때만.
({List<int> closed, List<Meld> melds}) _callSome(_Gen g, _Shape s, double callRate, double kanRate) {
  final melds = <Meld>[];
  final closed = <int>[s.pair, s.pair];
  final used = toCounts([for (final x in s.groups) ...x.tiles, s.pair, s.pair]);
  for (final x in s.groups) {
    if (x.seq) {
      if (g.chance(callRate)) {
        melds.add(Meld.chi(x.tile));
      } else {
        closed.addAll(x.tiles);
      }
      continue;
    }
    if (g.chance(kanRate) && used[x.tile] < 4) {
      used[x.tile]++;
      melds.add(g.chance(0.5) ? Meld.closedKan(x.tile) : Meld.openKan(x.tile));
    } else if (g.chance(callRate)) {
      melds.add(Meld.pon(x.tile));
    } else {
      closed.addAll(x.tiles);
    }
  }
  return (closed: closed, melds: melds);
}

/// 모양 없는 멘젠 형태: 치또이·국사·구련.
List<int>? _closedForm(_Gen g, String profile) {
  switch (profile) {
    case 'chiitoi':
      final pool = g.chance(0.3)
          ? g.chance(0.5) ? g.honors : [...g.terminals, ...g.honors]
          : g.chance(0.3)
              ? List.generate(9, (i) => g.pick(g.suits) + i)
              : g.allTiles;
      final kinds = pool.toSet().toList()..shuffle(g.r);
      if (kinds.length < 7) return null;
      return [for (final t in kinds.take(7)) ...[t, t]];
    case 'kokushi':
      final ends = [...g.terminals, ...g.honors];
      return [...ends, g.pick(ends)];
    case 'chuuren':
      final s = g.pick(g.suits);
      return [
        for (final n in const [1, 1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 9, 9]) s + n - 1,
        s + g.r.nextInt(9),
      ];
  }
  throw ArgumentError(profile);
}

/// 표시패는 손패와 합쳐 패마다 4장을 넘지 않게 고른다.
List<int> _indicators(_Gen g, List<int> counts, int n) {
  final out = <int>[];
  for (var i = 0; i < n * 3 && out.length < n; i++) {
    final t = g.r.nextInt(Tiles.count);
    if (counts[t] < 4) {
      counts[t]++;
      out.add(t);
    }
  }
  return out;
}

Situation _situation(_Gen g, Hand hand) {
  final tsumo = g.chance(0.5);
  final hasKan = hand.melds.any((m) => m.isKan);
  final closed = hand.isClosed;
  final double_ = closed && g.chance(0.05);
  final riichi = closed && !double_ && g.chance(0.4);
  final any = riichi || double_;
  final rinshan = tsumo && hasKan && g.chance(0.3);
  final chankan = !tsumo && g.chance(0.03);
  final last = !rinshan && !chankan && g.chance(0.05);
  final counts = toCounts(hand.allTiles);
  final kans = hand.melds.where((m) => m.isKan).length;
  final dora = _indicators(g, counts, g.chance(0.5) ? 1 + kans : 0);
  final ura = any && g.chance(0.5) ? _indicators(g, counts, 1 + kans) : <int>[];
  return Situation(
    isTsumo: tsumo,
    seatWind: Tiles.east + g.r.nextInt(4),
    roundWind: Tiles.east + (g.chance(0.8) ? g.r.nextInt(2) : g.r.nextInt(4)),
    riichi: riichi,
    doubleRiichi: double_,
    ippatsu: any && !rinshan && g.chance(0.3),
    lastTile: last,
    rinshan: rinshan,
    chankan: chankan,
    doraIndicators: dora,
    uraIndicators: ura,
    honba: g.chance(0.3) ? 1 + g.r.nextInt(5) : 0,
  );
}

/// 앱 룰 설정에서 바꿀 수 있는 값. 연풍 머리 2부는 mahjong 패키지에 없어 4부로 고정.
RuleSet _rules(_Gen g) {
  if (g.chance(0.6)) return RuleSet.standard;
  return RuleSet(
    kuitan: g.chance(0.7),
    kiriageMangan: g.chance(0.5),
    kazoeYakuman: g.chance(0.7),
    doubleYakuman: g.chance(0.7),
    redDora: g.chance(0.8),
  );
}

/// 적도라 칸: 패마다 있는 5 중 일부. 5가 4장이면 실제 패산에선 하나가 반드시 적5다.
List<int> _reds(_Gen g, List<int> all) {
  final counts = toCounts(all);
  return [
    for (final s in const [_man, _pin, _sou])
      if (counts[s + 4] == 4 || (counts[s + 4] > 0 && g.chance(0.3))) s + 4,
  ];
}

Map<String, dynamic>? _entry(_Gen g, int id) {
  final roll = g.r.nextDouble();
  final String profile;
  List<int> closed;
  var melds = <Meld>[];
  if (roll < 0.06) {
    profile = 'chiitoi';
  } else if (roll < 0.09) {
    profile = 'kokushi';
  } else if (roll < 0.12) {
    profile = 'chuuren';
  } else {
    profile = g.pick(_shapeProfiles);
  }
  if (const {'chiitoi', 'kokushi', 'chuuren'}.contains(profile)) {
    final c = _closedForm(g, profile);
    if (c == null) return null;
    closed = c;
  } else {
    final s = g.shape(profile);
    if (s == null) return null;
    final callRate = g.chance(0.5) ? 0.0 : 0.4;
    final kanRate = g.chance(0.15) ? 0.7 : 0.07;
    final split = _callSome(g, s, callRate, kanRate);
    closed = split.closed;
    melds = split.melds;
  }
  // 일부는 한 장 바꿔 화료가 아닌 손패로.
  final mutated = g.chance(0.04);
  if (mutated) {
    closed = [...closed];
    closed[g.r.nextInt(closed.length)] = g.r.nextInt(Tiles.count);
  }
  final win = g.pick(closed);
  final allForRed = [...closed, for (final m in melds) ...m.tiles];
  final reds = _reds(g, allForRed);
  final Hand hand;
  try {
    hand = Hand(closedTiles: closed, melds: melds, winTile: win, redCount: reds.length);
  } on ArgumentError {
    return null; // 바꾼 패가 4장을 넘음
  }
  var sit = _situation(g, hand);
  // 천화·지화: 멘젠 쯔모일 때 드물게. 우리 엔진은 화료패를 모든 장으로 시험하므로 비교도 그렇게 한다.
  if (hand.melds.isEmpty && sit.isTsumo && g.chance(0.02)) {
    sit = sit.copyWith(
        firstTurnWin: true, riichi: false, doubleRiichi: false, ippatsu: false,
        lastTile: false, rinshan: false, uraIndicators: const []);
  }
  final rules = _rules(g);
  final res = calculate(hand, sit, rules: rules);
  return {
    'id': id,
    'profile': profile,
    'closed': hand.closedTiles.map(Tiles.toCode).toList(),
    'win': Tiles.toCode(hand.winTile),
    'melds': [
      for (final m in hand.melds)
        {'type': m.isKan ? (m.isOpen ? 'openKan' : 'closedKan') : m.type.name, 'first': Tiles.toCode(m.first)},
    ],
    'reds': reds.map(Tiles.toCode).toList(),
    'sit': {
      'tsumo': sit.isTsumo,
      'seat': Tiles.toCode(sit.seatWind),
      'round': Tiles.toCode(sit.roundWind),
      'riichi': sit.riichi,
      'doubleRiichi': sit.doubleRiichi,
      'ippatsu': sit.ippatsu,
      'lastTile': sit.lastTile,
      'rinshan': sit.rinshan,
      'chankan': sit.chankan,
      'firstTurnWin': sit.firstTurnWin,
      'dora': sit.doraIndicators.map(Tiles.toCode).toList(),
      'ura': sit.uraIndicators.map(Tiles.toCode).toList(),
      'honba': sit.honba,
    },
    'rules': {
      'kuitan': rules.kuitan,
      'kiriage': rules.kiriageMangan,
      'kazoe': rules.kazoeYakuman,
      'doubleYakuman': rules.doubleYakuman,
      'redDora': rules.redDora,
    },
    'ours': {
      'valid': res.isValid,
      'error': res.error,
      'yaku': [for (final y in res.yaku) y.yaku.name],
      'han': res.han,
      'fu': res.fu.total,
      'yakuman': res.isYakuman,
      'yakumanCount': res.yakumanCount,
      'ron': res.payment.ron,
      'fromDealer': res.payment.tsumoFromDealer,
      'fromNonDealer': res.payment.tsumoFromNonDealer,
      'total': res.payment.total,
    },
  };
}

void main(List<String> args) {
  final n = args.isNotEmpty ? int.parse(args[0]) : 20000;
  final seed = args.length > 1 ? int.parse(args[1]) : 1;
  final path = args.length > 2 ? args[2] : 'build/engine_diff/corpus.jsonl';
  final g = _Gen(Random(seed));
  File(path).parent.createSync(recursive: true);
  final out = StringBuffer();
  var id = 0;
  while (id < n) {
    final e = _entry(g, id);
    if (e == null) continue;
    out.writeln(jsonEncode(e));
    id++;
  }
  File(path).writeAsStringSync(out.toString());
  stdout.writeln('$n 건 → $path (시드 $seed)');
}
