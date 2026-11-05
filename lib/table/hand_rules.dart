/// 마작 규칙 검증기(개선 계획 4단계, 2026-11-05). 순수 Dart, I/O 없음.
///
/// 사진을 보지 않는 규칙서 수준의 사실만 쓴다 — 명세·예제는 `test/fixtures/hand_rules.json` 하나이고
/// `experiments/speed/hand_rules.py` 가 같은 답을 내야 한다(양쪽 테스트가 같은 fixture 를 읽음).
/// - V1 같은 패 5장 이상(손패 + 화료패 + 울기 + 표시패 + 보이는 강, 적5 는 5 로) → 막음
/// - V2 적5 각 색 2장 이상 → 막음
/// - V4 울기 구성(치 = 같은 수패 색 연속 3, 퐁 = 같은 패 3, 깡 = 4) → 막음
/// - V5 장수(13·14 아님) → 사유만(지금 입력 화면 흐름 그대로)
/// - V3 화료형 아님 + 분류기 2순위로 한 장만 바꿔 화료형이 되는 결과가 정확히 하나 → 후보(자동 반영 금지, 사람이 확인)
/// 갤러리 연출 장면과 충돌한 "장면 상식"(표시패 수 R3 등)은 넣지 않는다.
library;

import 'merge.dart';
import 'table_reading.dart';

const _suits = 'mpsz';

String _norm(String code) => code[0] == '0' ? '5${code[1]}' : code;

int _idx(String code) {
  final c = _norm(code);
  return _suits.indexOf(c[1]) * 9 + int.parse(c[0]) - 1;
}

String _codeOf(int i) => '${i % 9 + 1}${_suits[i ~/ 9]}';

List<int> _counts(Iterable<String> codes) {
  final c = List<int>.filled(34, 0);
  for (final t in codes) {
    c[_idx(t)]++;
  }
  return c;
}

bool _sets(List<int> c, int k, [int i = 0]) {
  while (i < 34 && c[i] == 0) {
    i++;
  }
  if (i == 34) return k == 0;
  if (k == 0) return false;
  if (c[i] >= 3) {
    c[i] -= 3;
    final ok = _sets(c, k - 1, i);
    c[i] += 3;
    if (ok) return true;
  }
  if (i < 27 && i % 9 <= 6 && c[i + 1] > 0 && c[i + 2] > 0) {
    c[i]--;
    c[i + 1]--;
    c[i + 2]--;
    final ok = _sets(c, k - 1, i);
    c[i]++;
    c[i + 1]++;
    c[i + 2]++;
    if (ok) return true;
  }
  return false;
}

const _terminals = [0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33];

/// 멘젠 부분 [c](합 14 − 3 × [melds])가 화료형인가: 몸통 + 머리, 울기 0 이면 칠대자·국사무쌍도.
bool _complete(List<int> c, int melds) {
  if (c.fold(0, (a, b) => a + b) != 14 - 3 * melds) return false;
  for (var p = 0; p < 34; p++) {
    if (c[p] >= 2) {
      c[p] -= 2;
      final ok = _sets(c, 4 - melds);
      c[p] += 2;
      if (ok) return true;
    }
  }
  if (melds == 0) {
    if (c.where((x) => x == 2).length == 7) return true;
    if (_terminals.every((t) => c[t] >= 1) && _terminals.fold(0, (a, t) => a + c[t]) == 14) return true;
  }
  return false;
}

bool _tenpai(List<int> c, int melds) {
  for (var t = 0; t < 34; t++) {
    if (c[t] < 4) {
      c[t]++;
      final ok = _complete(c, melds);
      c[t]--;
      if (ok) return true;
    }
  }
  return false;
}

/// 장수 14 → 화료형, 13 → 텐파이(화료패를 모르는 입력).
bool _formOk(List<String> closed, int melds) {
  final c = _counts(closed);
  final n = closed.length + 3 * melds;
  return n == 14 ? _complete(c, melds) : (n == 13 ? _tenpai(c, melds) : false);
}

List<String> _excess(List<String> all) {
  final c = _counts(all);
  return [
    for (var i = 0; i < 34; i++)
      if (c[i] > 4) 'V1 ${_codeOf(i)}',
    for (final s in 'mps'.split(''))
      if (all.where((t) => t == '0$s').length > 1) 'V2 0$s',
  ];
}

/// 울기 묶음 하나(검사 입력). [type] 은 chi·pon·kan_open·kan_closed 또는 null(모양으로 판단).
class HandRuleMeld {
  final String? type;
  final List<String> tiles;
  const HandRuleMeld(this.type, this.tiles);

  factory HandRuleMeld.fromJson(Map<String, dynamic> j) =>
      HandRuleMeld(j['type'] as String?, [for (final t in (j['tiles'] as List<dynamic>?) ?? const []) t as String]);

  bool get ok {
    final ns = [for (final t in tiles) _idx(t)]..sort();
    final same = ns.toSet().length == 1;
    if (tiles.length == 4) return same && (type == null || type == 'kan_open' || type == 'kan_closed');
    if (tiles.length != 3) return false;
    final chi = ns[0] < 27 && ns[0] ~/ 9 == ns[2] ~/ 9 && ns[1] == ns[0] + 1 && ns[2] == ns[0] + 2;
    return switch (type) {
      'chi' => chi,
      'pon' => same,
      null => chi || same,
      _ => false,
    };
  }
}

/// 검사 입력(fixture `input` 과 같은 모양). [hand] 는 자리에서 읽은 멘젠 패(떼어 둔 패 포함), [win] 은 그 밖에서 온 화료패,
/// [river] 는 보이는 강 패(화료패로 가져간 론 패 한 장은 뺀 것), [alt]·[winAlt] 는 분류기 2순위 코드.
class HandRuleInput {
  final List<String> hand;
  final String? win;
  final List<HandRuleMeld> melds;
  final List<String> indicators;
  final List<String> river;
  final List<String?> alt;
  final String? winAlt;
  const HandRuleInput({
    required this.hand,
    this.win,
    this.melds = const [],
    this.indicators = const [],
    this.river = const [],
    this.alt = const [],
    this.winAlt,
  });

  factory HandRuleInput.fromJson(Map<String, dynamic> j) {
    List<String> codes(String k) => [for (final t in (j[k] as List<dynamic>?) ?? const []) t as String];
    return HandRuleInput(
      hand: codes('hand'),
      win: j['win'] as String?,
      melds: [for (final m in (j['melds'] as List<dynamic>?) ?? const []) HandRuleMeld.fromJson(m as Map<String, dynamic>)],
      indicators: codes('indicators'),
      river: codes('river'),
      alt: [for (final t in (j['alt'] as List<dynamic>?) ?? const []) t as String?],
      winAlt: j['win_alt'] as String?,
    );
  }

  List<String> get closed => [...hand, ?win];
}

/// V3 후보: [HandRuleInput.closed] 의 [index] 번째 [from] 을 [to] 로 바꾸면 화료형.
class HandCandidate {
  final int index;
  final String from;
  final String to;
  const HandCandidate(this.index, this.from, this.to);

  Map<String, dynamic> toJson() => {'index': index, 'from': from, 'to': to};
}

enum HandRuleKind { block, candidate, none }

class HandRuleResult {
  final HandRuleKind kind;

  /// 'V1 5p'·'V2 0m'·'V4 1s 2s 4s'·'V5 12'·'V3 6s→6p'(V1, V2, V4, V5, V3 순).
  final List<String> reasons;
  final HandCandidate? candidate;

  /// V3 을 해 봤으면 화료형이 되는 서로 다른 결과 수, 안 했으면 null.
  final int? v3;
  const HandRuleResult(this.kind, this.reasons, {this.candidate, this.v3});

  /// 자동 반영을 막는 사유(사람이 읽는 문구). 막지 않으면 빈 목록.
  List<String> get blockers => [
        for (final r in reasons)
          if (r.startsWith('V1 '))
            '같은 패 5장 이상(${r.substring(3)})'
          else if (r.startsWith('V2 '))
            '적5 2장 이상(${r.substring(3)})'
          else if (r.startsWith('V4 '))
            '울기 모양이 아님(${r.substring(3)})',
      ];

  Map<String, dynamic> toJson() => {
        'kind': kind.name,
        'reasons': reasons,
        'candidate': candidate?.toJson(),
        'v3': v3,
      };
}

/// 규칙 검사(명세는 `test/fixtures/hand_rules.json` spec).
HandRuleResult checkHandRules(HandRuleInput inp) {
  final closed = inp.closed;
  final others = [
    for (final m in inp.melds) ...m.tiles,
    ...inp.indicators,
    ...inp.river,
  ];
  final n = closed.length + 3 * inp.melds.length;
  final reasons = [
    ..._excess([...closed, ...others]),
    for (final m in inp.melds)
      if (!m.ok) 'V4 ${m.tiles.join(' ')}',
    if (n != 13 && n != 14) 'V5 $n',
  ];
  if (reasons.any((r) => r.startsWith('V1') || r.startsWith('V2') || r.startsWith('V4'))) {
    return HandRuleResult(HandRuleKind.block, reasons);
  }
  if ((n != 13 && n != 14) || _formOk(closed, inp.melds.length)) return HandRuleResult(HandRuleKind.none, reasons);
  final alts = <String?>[
    for (var i = 0; i < inp.hand.length; i++) i < inp.alt.length ? inp.alt[i] : null,
    if (inp.win != null) inp.winAlt,
  ];
  final found = <String, HandCandidate>{};
  for (var i = 0; i < closed.length; i++) {
    final a = alts[i];
    final t = closed[i];
    if (a == null || _norm(a) == _norm(t)) continue;
    final next = [...closed]..[i] = a;
    if (_excess([...next, ...others]).isNotEmpty || !_formOk(next, inp.melds.length)) continue;
    final key = ([for (final x in next) _idx(x)]..sort()).join(',');
    found.putIfAbsent(key, () => HandCandidate(i, t, a));
  }
  if (found.length == 1) {
    final c = found.values.single;
    return HandRuleResult(HandRuleKind.candidate, [...reasons, 'V3 ${c.from}→${c.to}'], candidate: c, v3: 1);
  }
  return HandRuleResult(HandRuleKind.none, reasons, v3: found.length);
}

/// 앱 판독 → 검사 입력. 손패·울기는 판독 원본([hand], 병합이 고치기 전), 화료패는 병합이 손패 밖에서 가져왔을 때만 [win] 으로,
/// 표시패는 병합이 쓴 것, 강은 [center] 의 보이는 강 패에서 론 패 한 장을 뺀 것(`hand_rules.py` `flow_input` 과 같은 규칙).
HandRuleInput handRuleInputOf({required HandReading hand, required TableMerge merge, CenterReading? center}) {
  final read = [...hand.tiles, ?hand.winTile];
  String code(MergedTile t) => ReadTile(t.tile, red: t.red).code;
  final win = merge.closed.length == read.length + 1 ? code(merge.closed.last) : null;
  final river = [
    for (final ts in center?.rivers.values ?? const <List<ReadTile>>[])
      for (final t in ts) t.code,
  ];
  if (win != null && !merge.isTsumo) {
    final i = river.indexWhere((t) => _norm(t) == _norm(win));
    if (i >= 0) river.removeAt(i);
  }
  return HandRuleInput(
    hand: [for (final t in read) t.code],
    win: win,
    melds: [for (final m in hand.melds) HandRuleMeld(m.typeName, [for (final t in m.tiles) t.code])],
    indicators: [
      for (final t in merge.situation.doraIndicators) ReadTile(t).code,
      for (final t in merge.situation.uraIndicators) ReadTile(t).code,
    ],
    river: river,
    alt: [for (final t in read) t.alt],
  );
}

/// V3 후보를 판독에 적용한 손패(다시 병합할 때 쓴다). [handRuleInputOf] 의 번호: 손패 → 떼어 둔 화료패 → 손패 밖 화료패.
HandReading applyHandCandidate(HandReading hand, HandCandidate c) {
  final to = ReadTile.fromCode(c.to, 0.5)!;
  final tiles = [...hand.tiles];
  var win = hand.winTile;
  if (c.index < tiles.length) {
    tiles[c.index] = to;
  } else {
    win = to;
  }
  return HandReading(
    tiles: tiles,
    melds: hand.melds,
    winTile: win,
    notes: hand.notes,
    model: hand.model,
    latencyMs: hand.latencyMs,
    usage: hand.usage,
  );
}
