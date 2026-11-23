/// 패보 리뷰: hero 의 버림마다 패효율로 평가한다.
///
/// 버리기 전 닫힌 손패(`14 − 3 × 울기 수` 장)를 사건에서 되짚고, [discardOptions] 로 후보를 줄 세운 뒤
/// 실제로 버린 패와 비교한다. 수비는 현물만 본다(스지·적5·도라 가중은 하지 않음).
library;

import '../engine/discard_rank.dart' show RankedDiscard, analyzeDiscards;
import '../engine/efficiency.dart';
import '../engine/risk.dart' show MeldKind, RiskTable, riskOf;
import '../engine/risk_calibration.dart' show RiskThreat;
import '../engine/shanten.dart';
import '../engine/tile.dart';
import 'mh_context.dart';
import 'paifu.dart';

export '../engine/discard_rank.dart' show RankedDiscard;
export '../engine/risk.dart' show RiskTable;
export '../engine/risk_calibration.dart' show RiskThreat;

/// 등급 문턱(임시). 유효패 손실이 최선의 몇 % 이하인가.
class ReviewThresholds {
  final int goodPct;
  final int inaccuracyPct;
  const ReviewThresholds({this.goodPct = 10, this.inaccuracyPct = 30});
}

enum ReviewGrade { best, good, inaccuracy, mistake, blunder }

/// 평가 상태. 위에서부터 먼저 걸리는 것: 짐작 손패(guessed) → 손패 모름·어긋남 → 리치 뒤(forced) → 화료 형태(complete)
/// → 남의 리치(defense) → graded.
///
/// [guessed](2026-11-21, `docs/paifu_review_ui_design_1121.md` 3-6): 버림 사건 또는 그 직전 뽑기 사건에 `guess: true` 가
/// 적힌 차례. 손패가 짐작이라 등급을 매기지 않고 숫자도 내지 않는다. 화면 · 요약에서는 unknownHand · inconsistent 와
/// 함께 "손패 모름" 묶음으로 센다([PaifuReview.handUnknownCount]). 값을 맨 뒤에 더해 앞 값들의 순서는 그대로다.
enum ReviewStatus { graded, forced, defense, complete, unknownHand, inconsistent, guessed }

/// hero 의 버림 한 번.
class TurnReview {
  /// 이 버림 사건의 events 인덱스. 직전 탁자 = states[eventIndex], 버린 뒤 = states[eventIndex + 1].
  final int eventIndex;

  /// hero 의 몇 번째 버림인가(1부터).
  final int turn;
  final PaifuTile discard;

  /// 이 차례에 뽑은 패(뽑기 사건에 적혀 있으면).
  final PaifuTile? drawn;

  /// 사건에 적힌 값 그대로.
  final bool? tsumogiri;

  /// 이 버림이 리치 선언.
  final bool riichiDeclared;
  final ReviewStatus status;

  /// hero 울기 수.
  final int melds;
  final int? shantenBefore;

  /// 버림 후보(정렬은 [discardOptions] 그대로). 숫자 없으면 빈 목록.
  final List<DiscardOption> options;
  final DiscardOption? actual;
  final DiscardOption? best;
  final int? shantenLoss;
  final int? ukeireLoss;

  /// 1 + (실제보다 엄밀히 나은 후보 수). 동률은 같은 순위.
  final int? rank;

  /// graded 일 때만.
  final ReviewGrade? grade;

  /// hero 아닌 리치 중인 자리(오름차순).
  final List<int> riichiSeats;

  /// 버린 패가 모든 리치 자리에 현물인가. 리치 자리가 없으면 null.
  final bool? genbutsu;

  /// 버리기 전 손패 중 모든 리치 자리에 현물인 종류(오름차순). 리치 자리가 없거나 손패를 모르면 빈 목록.
  final List<int> safeTiles;

  /// 버리기 전 닫힌 패 34칸 개수(뽑은 패 포함, `14 − 3 × melds` 장). 숫자 있는 차례에만, 그 밖은 null.
  final List<int>? before;

  // ---- mahjong-helper 엔진(lib/engine/discard_rank.dart) — 등급과 상관없는 참고 칸 ----

  /// 이 차례의 [rankDiscards] 결과(원본 순서: 샹텐 지키는 버림 → 물러나는 버림).
  /// `reviewPaifu(withEngine: true)` 이고 손패를 아는 차례(graded · defense · forced · complete)에서만. 계산이 실패하면 null.
  final List<RankedDiscard>? mh;

  /// 엔진이 고르는 버림(원본 `simpleBestDiscardTile`, 후퇴 권장이면 후퇴 1위). 패 종류(0~33).
  final int? mhBest;

  /// 실제 버림의 엔진 순위(1부터). 순서는 [mhBest] 를 맨 앞에 두고 나머지는 [mh] 순서 그대로.
  /// 동률: 1 + (앞선 후보 중 실제와 값이 다른 후보 수). 원본 Sort 는 값이 모두 같으면 마지막에 패 위치(가운데 패 먼저 ·
  /// 수패 먼저 · 자패 위험 순)로만 가르는데, 그렇게만 갈린 후보는 같은 순위로 친다(값 비교는 [_mhTied]).
  /// 그래서 [mhBest] 와 다른 패를 버려도 순위가 1 일 수 있다.
  final int? mhRankOfActual;

  /// 엔진이 「샹텐 후퇴?」를 띄우는지(1샹텐 · 자기 버림 9장 미만 · 멘젠 · 1위 유효패 9장 미만 · 후퇴 속도가 더 높음).
  final bool? mhRecommendBackward;

  // ---- 방총 위험도(lib/engine/risk.dart) ----

  /// 남이 리치/울기로 위협 중인 자리(오름차순): 리치했거나 (안깡 아닌) 울기가 있고, 엔진 텐파이율 > 15%
  /// (원본 `mixedRiskTable` 이 합치는 문턱). `withEngine: true` 일 때만 채운다. 비어 있으면 아래 위험 칸은 null.
  final List<int> riskSeats;

  /// 이 차례 직전 탁자의 [riskOf] 결과. 위협이 있을 때만.
  final RiskTable? riskTable;

  /// 버린 패의 합친 위험(%, 0~100, 원본 `mixedRiskTable`). 위협이 있을 때만.
  final double? riskOfActual;

  /// 버리기 전 손패 종류 중 합친 위험이 가장 낮은 패(같으면 번호 작은 패). 위협이 있고 손패를 알 때만.
  final int? minRiskTile;

  /// 버리기 전 손패 종류 → 합친 위험(%). 위협이 있고 손패를 알 때만.
  final Map<int, double>? riskByKind;

  const TurnReview({
    required this.eventIndex,
    required this.turn,
    required this.discard,
    required this.drawn,
    required this.tsumogiri,
    required this.riichiDeclared,
    required this.status,
    required this.melds,
    this.shantenBefore,
    this.options = const [],
    this.actual,
    this.best,
    this.shantenLoss,
    this.ukeireLoss,
    this.rank,
    this.grade,
    this.riichiSeats = const [],
    this.genbutsu,
    this.safeTiles = const [],
    this.before,
    this.mh,
    this.mhBest,
    this.mhRankOfActual,
    this.mhRecommendBackward,
    this.riskSeats = const [],
    this.riskTable,
    this.riskOfActual,
    this.minRiskTile,
    this.riskByKind,
  });

  /// 실제 버림의 엔진 평가 항목. [mh] 가 없으면 null.
  RankedDiscard? get mhActual {
    final l = mh;
    if (l == null || !_valid(discard.tile)) return null;
    for (final d in l) {
      if (d.tile == discard.tile) return d;
    }
    return null;
  }

  /// 엔진 최선 버림 항목. [mh] 가 없으면 null.
  RankedDiscard? get mhBestEntry {
    final l = mh;
    final b = mhBest;
    if (l == null || b == null) return null;
    for (final d in l) {
      if (d.tile == b) return d;
    }
    return null;
  }

  /// 실제 버림의 개량 평균(원본 AvgImproveWaitsCount).
  double? get mhActualImprove => mhActual?.avgImproveWaitsCount;

  /// 실제 버림의 속도 점수(원본 MixedWaitsScore, NaN 일 수 있음).
  double? get mhActualSpeed => mhActual?.speedScore;

  /// 실제 버림 뒤 화료율(%, 텐파이일 때만 0 아님).
  double? get mhActualAgariRate => mhActual?.agariRate;

  /// 실제 버림 뒤 기대 타점: 멘젠이면 리치 기대 타점, 울었으면 다마(울기) 기대 타점.
  double? get mhActualPoint {
    final a = mhActual;
    if (a == null) return null;
    return a.raw.result13.isNaki ? a.damaPoint : a.riichiPoint;
  }

  /// 실제 버림의 국수지(원본 MixedRoundPoint).
  double? get mhActualRoundPoint => mhActual?.roundPoint;

  /// 화면 보정표(lib/engine/risk_calibration.dart)를 고르는 위협 종류. 위협 자리([riskSeats])가 없으면 null.
  /// [riichiSeats](hero 아닌 리치 자리)가 하나라도 있으면 리치 위협(R), 없으면 울기 위협만(C) — 실험
  /// (`tool/tenhou6_features.dart` 의 `riichiSeats` · `risk_calibrate.py` 의 `kind`)과 같은 정의.
  /// 리치 자리는 텐파이율 100 이라 언제나 [riskSeats] 에 든다.
  RiskThreat? get riskThreat =>
      riskSeats.isEmpty ? null : (riichiSeats.isNotEmpty ? RiskThreat.riichi : RiskThreat.callOnly);

  /// [tile] 이 모두에게 안전패인가(엔진 `RiskTable.safeForAll34` — 실험의 `safeAll` 칸과 같은 값). 위험표가 없으면 false.
  bool riskSafeForAll(int tile) {
    final tb = riskTable;
    return tb != null && _valid(tile) && tb.safeForAll34[tile];
  }
}

class PaifuReview {
  final List<TurnReview> turns;
  const PaifuReview(this.turns);

  int count(ReviewStatus s) => turns.where((t) => t.status == s).length;

  int gradeCount(ReviewGrade g) => turns.where((t) => t.grade == g).length;

  // ── 판 요약 화면(3-1)의 "평가 안 함" 네 묶음. 등급 개수 합 + 네 묶음 합 = hero 버림 수(turns.length). ──

  /// 리치 중(forced).
  int get forcedCount => count(ReviewStatus.forced);

  /// 수비(defense).
  int get defenseCount => count(ReviewStatus.defense);

  /// 화료 형태(complete).
  int get completeCount => count(ReviewStatus.complete);

  /// 손패 모름: unknownHand + inconsistent + guessed(짐작 손패).
  int get handUnknownCount =>
      count(ReviewStatus.unknownHand) + count(ReviewStatus.inconsistent) + count(ReviewStatus.guessed);

  /// 등급을 매긴 버림 수(graded).
  int get gradedCount => count(ReviewStatus.graded);

  /// 배울 장면(3-1): 최대 [max] 개. 큰 실수 → 실수 → 부정확 순. 같은 등급 안에서는 큰 실수는 shantenLoss 가 큰 것,
  /// 나머지는 ukeireLoss 가 큰 것이 먼저, 같으면 앞 순(turn 작은 것)이 먼저.
  List<TurnReview> lessons({int max = 3}) {
    const order = [ReviewGrade.blunder, ReviewGrade.mistake, ReviewGrade.inaccuracy];
    final out = <TurnReview>[];
    for (final g in order) {
      final same = turns.where((t) => t.status == ReviewStatus.graded && t.grade == g).toList()
        ..sort((a, b) {
          final la = g == ReviewGrade.blunder ? (a.shantenLoss ?? 0) : (a.ukeireLoss ?? 0);
          final lb = g == ReviewGrade.blunder ? (b.shantenLoss ?? 0) : (b.ukeireLoss ?? 0);
          if (la != lb) return lb - la;
          return a.turn - b.turn;
        });
      out.addAll(same);
    }
    return out.take(max).toList();
  }

  /// graded 인 차례들의 actual.total / best.total 평균 × 100 을 반올림한 0~100.
  /// blunder 는 0, best.total == 0 이면 100 으로 친다. graded 가 없으면 null.
  /// 분수로 정확히 더한 뒤 반올림한다(반은 올림).
  int? get efficiencyPct {
    var num = BigInt.zero;
    var den = BigInt.one;
    var n = 0;
    for (final t in turns) {
      if (t.status != ReviewStatus.graded) continue;
      n++;
      final BigInt a;
      final BigInt b;
      if (t.grade == ReviewGrade.blunder) {
        a = BigInt.zero;
        b = BigInt.one;
      } else if (t.best!.ukeire.total == 0) {
        a = BigInt.one;
        b = BigInt.one;
      } else {
        a = BigInt.from(t.actual!.ukeire.total);
        b = BigInt.from(t.best!.ukeire.total);
      }
      num = num * b + a * den;
      den = den * b;
      final g = num.gcd(den);
      if (g > BigInt.one) {
        num = num ~/ g;
        den = den ~/ g;
      }
    }
    if (n == 0) return null;
    // round(100 × num / (den × n)) = (200 × num + den × n) ~/ (2 × den × n)
    final d = den * BigInt.from(n);
    return ((BigInt.from(200) * num + d) ~/ (BigInt.two * d)).toInt();
  }
}

bool _valid(int t) => t >= 0 && t < Tiles.count;

bool _same(List<int> a, List<int> b) {
  for (var i = 0; i < a.length; i++) {
    if (a[i] != b[i]) return false;
  }
  return true;
}

/// 패 목록 → 34칸. 범위 밖 패가 있으면 null.
List<int>? _counts(Iterable<PaifuTile> ts) {
  final c = List<int>.filled(Tiles.count, 0);
  for (final t in ts) {
    if (!_valid(t.tile)) return null;
    c[t.tile]++;
  }
  return c;
}

/// 패보 한 판 → hero 버림마다 평가 한 건. 어떤 패보에도 예외를 던지지 않는다.
///
/// [withEngine] 이 true 면 mahjong-helper 엔진 칸([TurnReview.mh] · 위험도)도 채운다. 등급은 그대로다.
/// [gradeGuessed] 가 false(기본)면 짐작 손패 차례(버림 또는 직전 뽑기 사건이 `guess`)는 [ReviewStatus.guessed] 로 두고
/// 등급을 매기지 않는다(설계서 3-6). true 면 11-21 전처럼 짐작 손패도 평가한다(비교 · 되돌림용).
/// 엔진 버림 순위는 한 판에 수 초(JIT, 손패 있는 판 2~6초)가 걸려 기본은 끈다 — 재생 화면이 화면 스레드에서
/// 곧바로 부르기 때문(lib/ui/paifu/review_view.dart `PaifuReviewIndex.of`).
PaifuReview reviewPaifu(Paifu p,
    {ReviewThresholds thresholds = const ReviewThresholds(), bool withEngine = false, bool gradeGuessed = false}) {
  final hero = p.hero;
  List<PaifuState>? states;
  if (hero >= 0 && hero < 4) {
    try {
      states = p.states;
    } catch (_) {
      states = null;
    }
  }
  if (states == null) {
    // 탁자를 쌓을 수 없는 기록(울린 자리 번호가 범위 밖 등): 버림마다 어긋남으로.
    var n = 0;
    return PaifuReview([
      for (final (i, e) in p.events.indexed)
        if (e.seat == hero && e.type == PaifuEventType.discard && e.tile != null)
          TurnReview(
            eventIndex: i,
            turn: ++n,
            discard: e.tile!,
            drawn: null,
            tsumogiri: e.tsumogiri,
            riichiDeclared: e.riichi,
            status: ReviewStatus.inconsistent,
            melds: 0,
          ),
    ]);
  }

  // 자리별 리치 선언 버림의 사건 인덱스.
  final riichiAt = List<int?>.filled(4, null);
  final out = <TurnReview>[];
  var turn = 0;
  for (final (i, e) in p.events.indexed) {
    if (e.type == PaifuEventType.discard && e.seat == hero) {
      turn++;
      out.add(_review(p, states, i, turn, riichiAt, thresholds, withEngine, gradeGuessed));
    }
    if (e.type == PaifuEventType.discard && e.riichi && riichiAt[e.seat] == null) riichiAt[e.seat] = i;
  }
  return PaifuReview(List.unmodifiable(out));
}

TurnReview _review(Paifu p, List<PaifuState> states, int i, int turn, List<int?> riichiAt, ReviewThresholds th,
    bool engine, bool gradeGuessed) {
  final hero = p.hero;
  final e = p.events[i];
  final discard = e.tile!;
  final st = states[i];
  final melds = st.melds[hero].length;

  // 이 버림 앞 hero 사건: 직전 버림·울기까지 거슬러 올라가며 뽑기·울기를 찾는다.
  PaifuEvent? draw;
  PaifuEvent? call;
  for (var j = i - 1; j >= 0; j--) {
    final f = p.events[j];
    if (f.seat != hero) continue;
    if (f.type == PaifuEventType.draw) {
      draw = f;
    } else if (f.type == PaifuEventType.call) {
      call = f;
    }
    break;
  }

  // 리치 상대와 현물.
  final riichiSeats = [
    for (var s = 0; s < 4; s++)
      if (s != hero && st.riichi[s]) s,
  ];
  List<bool>? safeKinds;
  if (riichiSeats.isNotEmpty) {
    safeKinds = List<bool>.filled(Tiles.count, true);
    for (final s in riichiSeats) {
      final mine = List<bool>.filled(Tiles.count, false);
      for (final r in st.rivers[s]) {
        if (_valid(r.tile.tile)) mine[r.tile.tile] = true;
      }
      final from = riichiAt[s];
      if (from != null) {
        for (var j = from + 1; j < i; j++) {
          final f = p.events[j];
          final t = f.tile;
          if (f.type == PaifuEventType.discard && t != null && _valid(t.tile)) mine[t.tile] = true;
        }
      }
      for (var t = 0; t < Tiles.count; t++) {
        if (!mine[t]) safeKinds[t] = false;
      }
    }
  }
  final genbutsu = safeKinds == null ? null : (_valid(discard.tile) && safeKinds[discard.tile]);

  // 보이는 패: 강(울려 나간 것 빼고) + 모든 울기 묶음 + 도라 표시패.
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

  TurnReview bare(ReviewStatus status) {
    // 손패를 몰라도 버린 패의 위험은 낼 수 있다(남은 장수에 hero 손패가 빠짐). 어긋난 기록은 손패를 넣지 않는다.
    final rk = engine ? _riskAt(p, i, discard, null, visible) : _noRisk;
    return TurnReview(
      eventIndex: i,
      turn: turn,
      discard: discard,
      drawn: draw?.tile,
      tsumogiri: e.tsumogiri,
      riichiDeclared: e.riichi,
      status: status,
      melds: melds,
      riichiSeats: List.unmodifiable(riichiSeats),
      genbutsu: genbutsu,
      riskSeats: rk.seats,
      riskTable: rk.table,
      riskOfActual: rk.actual,
    );
  }

  // 3-6: 버림 사건 또는 그 직전 뽑기 사건의 손패가 짐작이면 평가하지 않는다.
  if (!gradeGuessed && (e.guess || (draw?.guess ?? false))) return bare(ReviewStatus.guessed);

  // 버리기 전 손패: 뽑기 쪽 → 울기 쪽 → 버림 쪽.
  List<int>? front;
  List<PaifuTile>? frontTiles;
  var bad = false;
  if (draw != null && draw.hand != null && draw.tile != null) {
    frontTiles = [...draw.hand!, draw.tile!];
    front = _counts(frontTiles);
    bad = front == null;
  } else if (call != null && call.hand != null) {
    frontTiles = call.hand!;
    front = _counts(frontTiles);
    bad = front == null;
  }
  List<int>? back;
  List<PaifuTile>? backTiles;
  if (e.hand != null) {
    backTiles = [...e.hand!, discard];
    back = _counts(backTiles);
    bad = bad || back == null;
  }
  if (bad || !_valid(discard.tile) || melds > 4) return bare(ReviewStatus.inconsistent);
  final before = front ?? back;
  // 적5 표시는 뽑기·울기 쪽 줄을 먼저 쓴다(구성은 위에서 같은지 본다).
  final beforeTiles = frontTiles ?? backTiles;
  if (before == null || beforeTiles == null) return bare(ReviewStatus.unknownHand);
  if (front != null && back != null && !_same(front, back)) return bare(ReviewStatus.inconsistent);
  var sum = 0;
  for (final c in before) {
    if (c > 4) return bare(ReviewStatus.inconsistent);
    sum += c;
  }
  if (sum != 14 - 3 * melds || before[discard.tile] == 0) return bare(ReviewStatus.inconsistent);

  final options = discardOptions(before, melds: melds, visible: visible);
  final best = options.first;
  final actual = options.firstWhere((o) => o.tile == discard.tile);
  final shantenBefore = shanten(before, melds: melds);
  final shantenLoss = actual.shanten - best.shanten;
  final ukeireLoss = best.ukeire.total - actual.ukeire.total;
  final rank = 1 +
      options
          .where((o) => o.shanten < actual.shanten || (o.shanten == actual.shanten && o.ukeire.total > actual.ukeire.total))
          .length;

  final ReviewStatus status;
  if (st.riichi[hero]) {
    status = ReviewStatus.forced;
  } else if (shantenBefore == -1) {
    status = ReviewStatus.complete;
  } else if (riichiSeats.isNotEmpty) {
    status = ReviewStatus.defense;
  } else {
    status = ReviewStatus.graded;
  }

  ReviewGrade? grade;
  if (status == ReviewStatus.graded) {
    final bt = best.ukeire.total;
    if (shantenLoss > 0) {
      grade = ReviewGrade.blunder;
    } else if (ukeireLoss <= 0) {
      grade = ReviewGrade.best;
    } else if (ukeireLoss * 100 <= th.goodPct * bt) {
      grade = ReviewGrade.good;
    } else if (ukeireLoss * 100 <= th.inaccuracyPct * bt) {
      grade = ReviewGrade.inaccuracy;
    } else {
      grade = ReviewGrade.mistake;
    }
  }

  final m = engine ? _mhAt(p, i, discard, beforeTiles, visible) : null;
  final rk = engine ? _riskAt(p, i, discard, beforeTiles, visible) : _noRisk;

  return TurnReview(
    eventIndex: i,
    turn: turn,
    discard: discard,
    drawn: draw?.tile,
    tsumogiri: e.tsumogiri,
    riichiDeclared: e.riichi,
    status: status,
    melds: melds,
    shantenBefore: shantenBefore,
    options: List.unmodifiable(options),
    actual: actual,
    best: best,
    shantenLoss: shantenLoss,
    ukeireLoss: ukeireLoss,
    rank: rank,
    grade: grade,
    riichiSeats: List.unmodifiable(riichiSeats),
    genbutsu: genbutsu,
    safeTiles: [
      if (safeKinds != null)
        for (var t = 0; t < Tiles.count; t++)
          if (before[t] > 0 && safeKinds[t]) t,
    ],
    before: List.unmodifiable(before),
    mh: m?.list,
    mhBest: m?.best,
    mhRankOfActual: m?.rank,
    mhRecommendBackward: m?.recommendBackward,
    riskSeats: rk.seats,
    riskTable: rk.table,
    riskOfActual: rk.actual,
    minRiskTile: rk.table == null ? null : _minRisk(rk.table!, before),
    riskByKind: rk.table == null
        ? null
        : Map.unmodifiable({
            for (var t = 0; t < Tiles.count; t++)
              if (before[t] > 0) t: rk.table!.mixed34[t],
          }),
  );
}

/// 엔진 버림 순위 한 차례.
class _Mh {
  final List<RankedDiscard> list;
  final int? best;
  final int? rank;
  final bool recommendBackward;
  const _Mh(this.list, this.best, this.rank, this.recommendBackward);
}

/// 손패를 아는 차례의 엔진 버림 순위. 실패하면 null(예외를 밖으로 내지 않음).
_Mh? _mhAt(Paifu p, int i, PaifuTile discard, List<PaifuTile> beforeTiles, List<int> visible) {
  try {
    final ctx = discardContextAt(p, i, handBefore: beforeTiles, visible34: visible);
    if (ctx == null) return null;
    final r = analyzeDiscards(ctx);
    final list = List<RankedDiscard>.unmodifiable(r.all);
    if (list.isEmpty) return _Mh(list, r.best, null, r.recommendBackward);
    // 결정 순서: 엔진 최선을 맨 앞, 나머지는 원본 순서.
    final order = [
      ?r.best,
      for (final d in list)
        if (d.tile != r.best) d.tile,
    ];
    final idx = order.indexOf(discard.tile);
    if (idx < 0) return _Mh(list, r.best, null, r.recommendBackward);
    final byTile = {for (final d in list) d.tile: d};
    final actual = byTile[discard.tile]!;
    var rank = 1;
    for (var k = 0; k < idx; k++) {
      if (!_mhTied(byTile[order[k]]!, actual)) rank++;
    }
    return _Mh(list, r.best, rank, r.recommendBackward);
  } catch (_) {
    return null;
  }
}

/// 원본 Sort 가 값으로는 가르지 못하고 마지막 「패 위치」(가운데 패 먼저 · 수패 먼저 · 자패 위험 순)로만 가르는 두 후보.
/// 후퇴 여부 · 샹텐 · 유효패 · 속도 · 전진 뒤 유효패 · 화료율 · 개량 · 국수지 · 버림 값이 모두 같으면(실수는 1e-5 안) 동률.
bool _mhTied(RankedDiscard a, RankedDiscard b) {
  bool eq(double x, double y) => (x.isNaN && y.isNaN) || (x - y).abs() < 1e-5;
  return a.isBackward == b.isBackward &&
      a.shanten == b.shanten &&
      a.waitsCount == b.waitsCount &&
      eq(a.speedScore, b.speedScore) &&
      eq(a.avgNextShantenWaitsCount, b.avgNextShantenWaitsCount) &&
      eq(a.agariRate, b.agariRate) &&
      eq(a.avgImproveWaitsCount, b.avgImproveWaitsCount) &&
      eq(a.roundPoint, b.roundPoint) &&
      a.raw.isIsolatedYaochuDiscardTile == b.raw.isIsolatedYaochuDiscardTile &&
      eq(a.raw.discardTileValue, b.raw.discardTileValue);
}

/// 방총 위험 한 차례.
class _Risk {
  final List<int> seats;
  final RiskTable? table;
  final double? actual;
  const _Risk(this.seats, this.table, this.actual);
}

const _noRisk = _Risk([], null, null);

/// 이 버림 직전 탁자의 위험. 위협(리치 또는 울기 + 텐파이율 > 15%)이 없거나 실패하면 빈 값.
_Risk _riskAt(Paifu p, int i, PaifuTile discard, List<PaifuTile>? beforeTiles, List<int> visible) {
  try {
    final table = riskOf(riskContextAt(p, i, handBefore: beforeTiles, visible34: visible));
    final ctxMelds = p.states[i].melds;
    final seats = [
      for (final o in table.opponents)
        if ((o.riichi ||
                ctxMelds[o.seat].any((m) => meldKindOf(m.kind, m.tiles, o.seat, m.from) != MeldKind.ankan)) &&
            o.tenpaiRate > 15)
          o.seat,
    ]..sort();
    if (seats.isEmpty) return _noRisk;
    final a = _valid(discard.tile) ? table.mixed34[discard.tile] : null;
    return _Risk(List.unmodifiable(seats), table, a);
  } catch (_) {
    return _noRisk;
  }
}

/// 손패 종류 중 합친 위험이 가장 낮은 패(같으면 번호 작은 패).
int? _minRisk(RiskTable table, List<int> before) {
  int? best;
  for (var t = 0; t < Tiles.count; t++) {
    if (before[t] == 0) continue;
    if (best == null || table.mixed34[t] < table.mixed34[best]) best = t;
  }
  return best;
}

// ── 단계(설계서 3-4): 배패 · 리치 · 끝. 복기 화면의 단계 말풍선이 쓴다. ──

enum ReviewStageKind { start, riichi, end }

/// 단계 하나. 문장은 `review_sentence.dart` 의 [stageSentence] 가 만든다.
class ReviewStage {
  final ReviewStageKind kind;

  /// 이 단계 말풍선이 붙는 걸음(재생 걸음 번호: 0 = 시작, i + 1 = events[i] 뒤).
  final int step;

  /// start: 배패 13장의 샹텐(0 = 텐파이).
  final int? startShanten;

  /// riichi: 리치한 자리.
  final int? seat;

  /// riichi 이고 hero 가 리치했을 때: hero 의 몇 번째 버림이 리치 선언인가(1부터).
  final int? riichiTurn;

  /// riichi 이고 hero 가 리치했을 때: 리치 선언 뒤 hero 버림 수(리치 뒤에는 뽑은 패를 그대로 버린다).
  final int afterRiichi;

  const ReviewStage({
    required this.kind,
    required this.step,
    this.startShanten,
    this.seat,
    this.riichiTurn,
    this.afterRiichi = 0,
  });

  bool get heroRiichi => kind == ReviewStageKind.riichi && riichiTurn != null;
}

/// 배패(시작 손패 13장). `start_hand` 가 있으면 그것, 없으면 hero 의 첫 사건이 손패가 적힌 뽑기일 때 그 뽑기 전 손패.
/// 그 뽑기가 짐작(`guess`)이거나 손패를 모르면 null — 배패 단계를 건너뛴다.
List<PaifuTile>? startHandOf(Paifu p) {
  bool ok(List<PaifuTile>? h) => h != null && h.length == 13 && h.every((t) => _valid(t.tile));
  if (p.startHand != null) return ok(p.startHand) ? p.startHand : null;
  for (final e in p.events) {
    if (e.seat != p.hero) continue;
    if (e.type == PaifuEventType.draw && !e.guess && ok(e.hand)) return e.hand;
    return null;
  }
  return null;
}

/// 한 판의 단계 걸음(걸음 순). 배패는 [startHandOf] 가 있을 때만, 리치는 hero 의 리치와 남의 첫 리치,
/// 끝은 마지막 걸음(걸음이 둘 이상일 때).
List<ReviewStage> reviewStages(Paifu p) {
  final out = <ReviewStage>[];
  final start = startHandOf(p);
  if (start != null) {
    final c = _counts(start);
    if (c != null) out.add(ReviewStage(kind: ReviewStageKind.start, step: 0, startShanten: shanten(c)));
  }
  var heroTurn = 0;
  int? heroStep, heroRiichiTurn, otherStep, otherSeat;
  var after = 0;
  for (final (i, e) in p.events.indexed) {
    if (e.type != PaifuEventType.discard) continue;
    if (e.seat == p.hero) {
      heroTurn++;
      if (heroStep != null) {
        after++;
      } else if (e.riichi) {
        heroStep = i + 1;
        heroRiichiTurn = heroTurn;
      }
    } else if (e.riichi && otherStep == null) {
      otherStep = i + 1;
      otherSeat = e.seat;
    }
  }
  if (heroStep != null) {
    out.add(ReviewStage(
      kind: ReviewStageKind.riichi,
      step: heroStep,
      seat: p.hero,
      riichiTurn: heroRiichiTurn,
      afterRiichi: after,
    ));
  }
  if (otherStep != null) out.add(ReviewStage(kind: ReviewStageKind.riichi, step: otherStep, seat: otherSeat));
  final last = p.stepCount - 1;
  if (last > 0 && !out.any((s) => s.step == last)) out.add(ReviewStage(kind: ReviewStageKind.end, step: last));
  out.sort((a, b) => a.step - b.step);
  return out;
}
