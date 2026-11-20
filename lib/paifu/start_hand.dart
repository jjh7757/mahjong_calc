/// 시작 손패를 받아 버림만 적힌 패보에 hero 의 매 순 손패를 헤아려 넣는다. 순수 Dart.
///
/// 아는 것: 시작 손패 13장, hero 의 버림(순서대로, 리치 뒤는 쯔모기리), 그리고 화료로 끝났으면 끝 손패.
/// 그러면 뽑은 패 묶음 = 끝 손패 + 버린 패 − 시작 손패 로 **종류는 다 정해지지만**, 손에서 낸 차례 사이에 무엇을 언제 뽑았는지는
/// 일부만 정해진다(`docs/paifu_review_plan_1113.md` 3-1). 그래서 가능한 뽑기 순서를 모두 따져,
/// 그 순에 어느 순서로 봐도 손에 있는 패만 "확정" 으로 내고 나머지는 "모름"(뒷면) + 후보 종류로 낸다. 틀린 손패를 확정처럼 내지 않는다.
/// 끝 손패가 없는 판(유국·결과 없음)은 "시작 손패에서 아직 안 버린 패" 만 확정이다.
library;

import '../engine/tile.dart';
import 'paifu.dart';

const int _kinds = 37; // 34종 + 적5만·적5통·적5삭

int _id(PaifuTile t) => t.red ? 34 + Tiles.suit(t.tile) : t.tile;

PaifuTile _tileOf(int id) => id < 34 ? PaifuTile(id) : PaifuTile((id - 34) * 9 + 4, red: true);

/// 늘어놓는 순서: 만·통·삭·자, 적5 는 5 바로 앞.
int _order(int id) => id < 34 ? id * 2 + 1 : ((id - 34) * 9 + 4) * 2;

List<int> _counts(Iterable<PaifuTile> tiles) {
  final c = List<int>.filled(_kinds, 0);
  for (final t in tiles) {
    c[_id(t)]++;
  }
  return c;
}

List<PaifuTile> _expand(List<int> counts) {
  final ids = [
    for (var k = 0; k < _kinds; k++)
      for (var i = 0; i < counts[k]; i++) k,
  ]..sort((a, b) => _order(a).compareTo(_order(b)));
  return [for (final k in ids) _tileOf(k)];
}

String _name(int id) => id < 34 ? Tiles.name(id) : '적${Tiles.name((id - 34) * 9 + 4)}';

/// 어느 순의 hero 손패: 확정 패 + 모르는 장수.
class HeroHandView {
  /// 어느 뽑기 순서로 봐도 손에 있는 패(정렬).
  final List<PaifuTile> known;

  /// 종류가 안 정해지는 장수.
  final int unknown;

  /// 모르는 칸에 올 수 있는 패 종류(정렬, 겹침 없음).
  final List<PaifuTile> candidates;

  /// 이 순에 뽑은 패가 하나로 정해지면 그 패(시작 걸음은 null).
  final PaifuTile? drew;

  /// 이 순의 버림이 쯔모기리인지 정해지면 그 값.
  final bool? tsumogiri;

  const HeroHandView({required this.known, required this.unknown, this.candidates = const [], this.drew, this.tsumogiri});

  bool get complete => unknown == 0;
}

class StartHandInference {
  /// 적용할 수 없으면 까닭(사람이 읽는 말). 그때 [after] 는 비어 있다.
  final String? error;

  /// [k] = hero 가 k 번 버린 뒤의 손패(0 = 시작 손패).
  final List<HeroHandView> after;

  /// 끝 손패까지 써서 따졌는가. false 면 "아직 안 버린 시작 패" 만 확정이다.
  final bool exact;

  /// 뽑은 패 묶음(끝 손패가 있을 때, 정렬).
  final List<PaifuTile> draws;

  const StartHandInference._({this.error, this.after = const [], this.exact = false, this.draws = const []});

  /// 손패가 다 정해진 순의 수(시작 걸음 제외)와 전체 순.
  int get completeTurns => after.skip(1).where((v) => v.complete).length;
  int get turns => after.isEmpty ? 0 : after.length - 1;

  /// 재생 걸음 [step](= 사건 [step] 개까지 반영) 때의 손패. 적용 못 한 경우 null.
  HeroHandView? viewAt(Paifu p, int step) {
    if (after.isEmpty) return null;
    var k = 0;
    for (final e in p.events.take(step)) {
      if (e.type == PaifuEventType.discard && e.seat == p.hero) k++;
    }
    return after[k < after.length ? k : after.length - 1];
  }

  static StartHandInference infer(Paifu p, List<PaifuTile> start) {
    if (start.length != 13) return const StartHandInference._(error: '시작 손패는 13장이어야 합니다');
    final hero = p.hero;
    if (p.events.any((e) => e.type == PaifuEventType.call && e.seat == hero)) {
      return const StartHandInference._(error: '이 자리가 운 판은 아직 시작 손패를 적용할 수 없습니다');
    }
    final discards = [
      for (final e in p.events)
        if (e.type == PaifuEventType.discard && e.seat == hero) e,
    ];
    final n = discards.length;
    final s = _counts(start);
    final r = p.result;
    final fin = r != null && r.winner == hero && r.hand != null && r.hand!.length == 13 ? r.hand! : null;
    if (fin == null) return _bounds(s, discards);

    // 뽑은 패 묶음 = 끝 손패 + 버린 패 − 시작 손패.
    final f = _counts(fin), d = List<int>.filled(_kinds, 0);
    for (var k = 0; k < _kinds; k++) {
      d[k] = f[k] - s[k];
    }
    for (final e in discards) {
      d[_id(e.tile!)]++;
    }
    final gone = [
      for (var k = 0; k < _kinds; k++)
        if (d[k] < 0) '${_name(k)}${d[k] < -1 ? ' ${-d[k]}장' : ''}',
    ];
    if (gone.isNotEmpty) {
      return StartHandInference._(error: '시작 손패의 ${gone.join(' · ')} 이(가) 버린 패에도 끝 손패에도 없습니다(적5 는 5 와 따로 셉니다)');
    }

    // 상태 = 아직 안 뽑은 패 묶음. 종류별 장수를 5진수로 묶어 열쇠로 쓴다.
    final dk = [
      for (var k = 0; k < _kinds; k++)
        if (d[k] > 0) k,
    ];
    final m = dk.length;
    final pow5 = [1];
    for (var i = 0; i < m; i++) {
      pow5.add(pow5.last * 5);
    }
    List<int> decode(int key) => [for (var i = 0; i < m; i++) (key ~/ pow5[i]) % 5];
    var startKey = 0;
    for (var i = 0; i < m; i++) {
      startKey += d[dk[i]] * pow5[i];
    }
    // 버림 누적.
    final prefix = [List<int>.filled(_kinds, 0)];
    for (final e in discards) {
      prefix.add([...prefix.last]..[_id(e.tile!)] += 1);
    }
    // i 번 버린 뒤, 남은 뽑기가 [rest] 일 때 손에 든 [kind] 의 장수.
    int inHand(int i, List<int> rest, int kind) {
      var c = s[kind] - prefix[i][kind];
      final j = dk.indexOf(kind);
      if (j >= 0) c += d[kind] - rest[j];
      return c;
    }

    /// (i+1)번째 차례에 [j] 번째 종류를 뽑을 수 있나: 그 버림이 손에 있어야 하고, 쯔모기리 여부가 적혀 있으면 맞아야 한다.
    bool canDraw(int i, List<int> rest, int j) {
      final e = discards[i];
      final dis = _id(e.tile!);
      final has = inHand(i, rest, dis) > 0;
      final same = dk[j] == dis;
      if (e.tsumogiri == true && !same) return false;
      if (e.tsumogiri == false && !has) return false;
      return has || same;
    }

    final memo = [for (var i = 0; i <= n; i++) <int, bool>{}];
    bool ok(int i, int key) {
      if (i == n) return key == 0;
      final hit = memo[i][key];
      if (hit != null) return hit;
      final rest = decode(key);
      var any = false;
      for (var j = 0; j < m && !any; j++) {
        if (rest[j] > 0 && canDraw(i, rest, j)) any = ok(i + 1, key - pow5[j]);
      }
      return memo[i][key] = any;
    }

    if (!ok(0, startKey)) {
      return const StartHandInference._(error: '이 시작 손패로는 적힌 버림 순서가 나올 수 없습니다(뽑기 전에 버린 패가 있습니다)');
    }
    // 끝까지 이어지는 상태만 앞에서부터 모은다.
    final live = [
      {startKey},
      for (var i = 0; i < n; i++) <int>{},
    ];
    final drawn = [for (var i = 0; i <= n; i++) <int>{}];
    final giri = [for (var i = 0; i <= n; i++) <bool>{}];
    for (var i = 0; i < n; i++) {
      final dis = _id(discards[i].tile!);
      for (final key in live[i]) {
        final rest = decode(key);
        for (var j = 0; j < m; j++) {
          if (rest[j] == 0 || !canDraw(i, rest, j) || !ok(i + 1, key - pow5[j])) continue;
          live[i + 1].add(key - pow5[j]);
          drawn[i + 1].add(dk[j]);
          final has = inHand(i, rest, dis) > 0;
          if (dk[j] != dis) {
            giri[i + 1].add(false);
          } else {
            giri[i + 1].add(true);
            if (has) giri[i + 1].add(false); // 같은 패를 뽑았고 손에도 있었다 — 어느 쪽인지 모른다
          }
        }
      }
    }
    final views = <HeroHandView>[HeroHandView(known: _expand(s), unknown: 0)];
    for (var i = 1; i <= n; i++) {
      final lo = List<int>.filled(_kinds, 99), hi = List<int>.filled(_kinds, 0);
      for (final key in live[i]) {
        final rest = decode(key);
        for (var k = 0; k < _kinds; k++) {
          final c = inHand(i, rest, k);
          if (c < lo[k]) lo[k] = c;
          if (c > hi[k]) hi[k] = c;
        }
      }
      final known = _expand(lo);
      views.add(HeroHandView(
        known: known,
        unknown: 13 - known.length,
        candidates: _expand([for (var k = 0; k < _kinds; k++) hi[k] > lo[k] ? 1 : 0]),
        drew: drawn[i].length == 1 ? _tileOf(drawn[i].single) : null,
        tsumogiri: giri[i].length == 1 ? giri[i].single : null,
      ));
    }
    return StartHandInference._(after: views, exact: true, draws: _expand(d));
  }

  /// 끝 손패를 모를 때: 시작 손패에서 아직 안 버린 패만 확정. 쯔모기리로 적힌 버림(리치 뒤)은 손패를 안 바꾼다.
  static StartHandInference _bounds(List<int> s, List<PaifuEvent> discards) {
    final left = [...s];
    final views = <HeroHandView>[HeroHandView(known: _expand(s), unknown: 0)];
    for (final e in discards) {
      final k = _id(e.tile!);
      if (e.tsumogiri != true && left[k] > 0) left[k]--;
      final known = _expand(left);
      views.add(HeroHandView(known: known, unknown: 13 - known.length, tsumogiri: e.tsumogiri));
    }
    return StartHandInference._(after: views);
  }
}
