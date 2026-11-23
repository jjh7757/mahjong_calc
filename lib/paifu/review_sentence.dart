/// 패보 복기 화면의 글: 수 말풍선(제목 · 두 줄 비교 · 구석 숫자 · 한 문장)과 단계 말풍선.
///
/// 규격은 `docs/paifu_review_ui_design_1121.md` 3-3 · 3-4 · 3-8. 전부 순수 함수다 — [TurnReview] 의 값을 그대로 글에 넣고,
/// 화면과 떼어 시험하며, LLM 해설이 검증에서 떨어졌을 때의 대체 문장으로도 같이 쓴다.
/// 용어는 마작 용어(유효패 · N샹텐 · 텐파이 · 대기, 9절 ①). 텐파이(버린 뒤 샹텐 0)에서는 "유효패" 를 "대기" 로 쓴다.
library;

import '../engine/efficiency.dart';
import '../engine/tile.dart';
import 'paifu.dart';
import 'paifu_review.dart';

// ── 낱말 ──

/// 등급 이름(4절).
String gradeName(ReviewGrade g) => switch (g) {
      ReviewGrade.best => '최선',
      ReviewGrade.good => '좋음',
      ReviewGrade.inaccuracy => '부정확',
      ReviewGrade.mistake => '실수',
      ReviewGrade.blunder => '큰 실수',
    };

/// 등급이 없는 상태의 짧은 이름. graded 는 등급 이름을 쓰므로 여기서는 '평가'.
String statusName(ReviewStatus s) => switch (s) {
      ReviewStatus.graded => '평가',
      ReviewStatus.forced => '리치 중',
      ReviewStatus.defense => '수비',
      ReviewStatus.complete => '화료 형태',
      ReviewStatus.unknownHand || ReviewStatus.inconsistent => '손패 모름',
      ReviewStatus.guessed => '짐작 손패',
    };

/// −1 화료 형태 · 0 텐파이 · n "n샹텐".
String shantenText(int s) => switch (s) {
      < 0 => '화료 형태',
      0 => '텐파이',
      _ => '$s샹텐',
    };

/// 버린 뒤 샹텐이 0 이하(텐파이)면 "대기", 아니면 "유효패".
String ukeireWord(int shantenAfter) => shantenAfter <= 0 ? '대기' : '유효패';

/// 패 이름(적5 는 "적5삭").
String tileText(PaifuTile t) => t.red ? '적${Tiles.name(t.tile)}' : Tiles.name(t.tile);

/// 끝 글자에 받침이 있으면 "을", 없으면 "를"을 붙인다(한글이 아니면 "을").
String withEul(String word) {
  if (word.isEmpty) return word;
  final c = word.codeUnitAt(word.length - 1);
  if (c < 0xAC00 || c > 0xD7A3) return '$word을';
  return (c - 0xAC00) % 28 == 0 ? '$word를' : '$word을';
}

/// 1,000 단위 쉼표.
String formatPoints(int n) {
  final s = n.abs().toString();
  final b = StringBuffer(n < 0 ? '-' : '');
  for (var i = 0; i < s.length; i++) {
    if (i > 0 && (s.length - i) % 3 == 0) b.write(',');
    b.write(s[i]);
  }
  return b.toString();
}

// ── 최선 후보(동률 포함) ──

/// 최선과 샹텐 · 유효패 수가 같은 후보의 패(options 순서 = 패 번호 순). 숫자 없는 차례는 빈 목록.
List<int> bestTiles(TurnReview t) {
  final b = t.best;
  if (b == null) return const [];
  return [
    for (final o in t.options)
      if (o.shanten == b.shanten && o.ukeire.total == b.ukeire.total) o.tile,
  ];
}

/// 최선 패 이름. 동률이 여럿이면 둘까지: "3만(또는 6만)". [paren] 이 false 면 "3만 또는 6만".
String bestLabel(TurnReview t, {bool paren = true}) {
  final tiles = bestTiles(t);
  if (tiles.isEmpty) return '';
  final first = Tiles.name(tiles.first);
  if (tiles.length == 1) return first;
  final second = Tiles.name(tiles[1]);
  return paren ? '$first(또는 $second)' : '$first 또는 $second';
}

/// "3만(또는 6만)을" — 조사는 괄호 앞 낱말에 맞춘다.
String _bestEul(TurnReview t) {
  final tiles = bestTiles(t);
  final first = Tiles.name(tiles.first);
  final rest = tiles.length > 1 ? '(또는 ${Tiles.name(tiles[1])})' : '';
  final withP = withEul(first);
  return '$first$rest${withP.substring(first.length)}';
}

// ── 수 말풍선(3-3) ──

/// 제목 줄: "4만 버림 · 실수" / 최선이면 "4만 버림 · 최선입니다" / 등급이 없으면 "4만 버림 · 리치 중".
String reviewTitle(TurnReview t) {
  final head = '${tileText(t.discard)} 버림';
  final g = t.grade;
  if (t.status == ReviewStatus.graded && g != null) {
    return g == ReviewGrade.best ? '$head · 최선입니다' : '$head · ${gradeName(g)}';
  }
  return '$head · ${statusName(t.status)}';
}

/// 두 줄 비교: "내 버림 4만 · 유효패 10장" / "최선 3만 · 유효패 15장". 큰 실수는 장수 대신 샹텐.
/// 최선이면 첫 줄만, 등급이 없는 걸음은 빈 목록.
List<String> reviewCompareLines(TurnReview t) {
  final a = t.actual;
  final b = t.best;
  final g = t.grade;
  if (t.status != ReviewStatus.graded || g == null || a == null || b == null) return const [];
  final mine = tileText(t.discard);
  if (g == ReviewGrade.blunder) {
    return ['내 버림 $mine · ${shantenText(a.shanten)}', '최선 ${bestLabel(t)} · ${shantenText(b.shanten)}'];
  }
  final first = '내 버림 $mine · ${ukeireWord(a.shanten)} ${a.ukeire.total}장';
  if (g == ReviewGrade.best) return [first];
  return [first, '최선 ${bestLabel(t)} · ${ukeireWord(b.shanten)} ${b.ukeire.total}장'];
}

/// 구석의 숫자 하나: "−5장", 샹텐이 뒤로 갔으면 "샹텐 후퇴"(2 이상이면 "2샹텐 후퇴"). 최선 · 등급 없음은 null.
String? reviewCorner(TurnReview t) {
  final g = t.grade;
  if (t.status != ReviewStatus.graded || g == null || g == ReviewGrade.best) return null;
  final sl = t.shantenLoss ?? 0;
  if (sl > 0) return sl >= 2 ? '$sl샹텐 후퇴' : '샹텐 후퇴';
  return '−${t.ukeireLoss ?? 0}장';
}

// ── 밀기 · 접기(설계서 docs/push_fold_design_1122.md 6절) ──
//
// 판정은 [TurnReview.pushFold](규칙 R3)가 있을 때만. 민 것은 "참고" 문구(지표 3 = 65.2% < 70%, metrics 표 16-15) —
// "틀렸다 · 실수 · 접었어야" 같은 지적 말은 쓰지 않는다. 접은 것은 지표 4 = 97.2% ≥ 90% 라 "잘 접었습니다.".
// 그 사이(중간)는 아무 말도 붙이지 않는다.

/// 밀기 · 접기 앞말. 밂 → "보통은 접는 자리입니다. 강한 AI 는 이런 자리의 약 94% 에서 접습니다." · 접음 → "잘 접었습니다."
/// · 중간 · 판정 없음 → null.
String? pushFoldHeadline(TurnReview t) => switch (t.pushFold?.action) {
      PushFoldAction.push =>
        '보통은 접는 자리입니다. 강한 AI 는 이런 자리의 약 $pushFoldAiFoldPct% 에서 접습니다.',
      PushFoldAction.fold => '잘 접었습니다.',
      _ => null,
    };

/// 위험 % 글의 기본 꼴: 엔진 값 소수 한 자리에 "약"(재생 화면 위험 줄 "이 패 방총 위험 약 1.7%" 와 같은 꼴).
String _riskPlain(int tile, double risk) => '약 ${risk.toStringAsFixed(1)}%';

/// 근거 숫자(6절: 내 손 몇 샹텐 · 버린 패의 방총 위험 · 가장 안전했던 패와 그 위험):
/// "내 손 3샹텐 · 방총 위험: 버린 7만(약 9.6%), 가장 안전 5통(약 0.0%)". 버린 패가 가장 안전한 패면
/// "… 버린 5통(약 0.0%) = 가장 안전". 앞말이 없는 차례(중간 · 판정 없음)는 null.
/// [riskText] 는 패 하나의 위험 글(기본 [_riskPlain] — 엔진 값). 화면은 보정값 글을 넘긴다.
/// [safest] 는 "가장 안전" 으로 적을 패. 없거나 [PushFoldSpot.safest] 밖이면: 버린 패가 그 안에 있으면 버린 패, 아니면
/// 첫째(번호 작은 패).
String? pushFoldEvidence(TurnReview t, {String Function(int tile, double risk)? riskText, int? safest}) {
  final s = t.pushFold;
  if (s == null || pushFoldHeadline(t) == null) return null;
  final rt = riskText ?? _riskPlain;
  final safe = safest != null && s.safest.contains(safest)
      ? safest
      : (s.safest.contains(s.discard) ? s.discard : s.safest.first);
  final mine = '버린 ${tileText(t.discard)}(${rt(s.discard, s.discardRisk)})';
  final tail = safe == s.discard ? '$mine = 가장 안전' : '$mine, 가장 안전 ${Tiles.name(safe)}(${rt(safe, s.minRisk)})';
  return '내 손 ${shantenText(s.shantenBefore)} · 방총 위험: $tail';
}

/// 앞말 + 근거: "잘 접었습니다. 내 손 3샹텐 · 방총 위험: …". 중간 · 판정 없음은 null.
String? pushFoldSentence(TurnReview t, {String Function(int tile, double risk)? riskText, int? safest}) {
  final head = pushFoldHeadline(t);
  if (head == null) return null;
  return '$head ${pushFoldEvidence(t, riskText: riskText, safest: safest)}';
}

/// 본문 한 문장(3-8 의 틀). LLM 해설이 없을 때 쓰는 코드 문장.
/// 수비 차례가 "접는 자리"(밂 · 접음)면 끝에 [pushFoldSentence] 를 붙인다. [withPushFold] 가 거짓이면 붙이지 않는다
/// (재생 말풍선은 그 글을 제목 아래 따로 보인다).
String reviewSentence(TurnReview t, {bool withPushFold = true}) {
  switch (t.status) {
    case ReviewStatus.forced:
      return '리치 중이라 뽑은 패를 그대로 버립니다.';
    case ReviewStatus.defense:
      final g = t.genbutsu;
      final tail = g == null ? '현물인지 판단하지 않습니다.' : (g ? '버린 패는 현물입니다.' : '버린 패는 현물이 아닙니다.');
      final pf = withPushFold ? pushFoldSentence(t) : null;
      return '다른 자리가 리치 중입니다. $tail${pf == null ? '' : ' $pf'}';
    case ReviewStatus.complete:
      return '화료 형태에서 버렸습니다. 화료하지 않은 까닭은 판단하지 않습니다.';
    case ReviewStatus.unknownHand:
      return '이 순은 손패 기록이 없어 평가하지 않습니다.';
    case ReviewStatus.inconsistent:
      return '이 순은 손패 기록이 앞뒤가 맞지 않아 평가하지 않습니다.';
    case ReviewStatus.guessed:
      return '이 순의 손패는 짐작이라 평가하지 않습니다.';
    case ReviewStatus.graded:
      break;
  }
  final g = t.grade;
  final b = t.best;
  if (g == null || b == null) return '이 순은 손패 기록이 없어 평가하지 않습니다.';
  final word = ukeireWord(b.shanten);
  final loss = t.ukeireLoss ?? 0;
  return switch (g) {
    ReviewGrade.best => '$word가 가장 많은 버림입니다.',
    ReviewGrade.good => '최선(${bestLabel(t, paren: false)})과 $loss장 차이로 거의 같습니다.',
    ReviewGrade.inaccuracy => '${_bestEul(t)} 버렸다면 $word가 $loss장 더 많았습니다.',
    ReviewGrade.mistake => '${_bestEul(t)} 버렸다면 $word가 $loss장 더 많았습니다. 차이가 큽니다.',
    ReviewGrade.blunder => '샹텐이 ${t.shantenLoss ?? 0} 늘었습니다. ${_bestEul(t)} 버리면 그대로였습니다.',
  };
}

/// 요약 화면 · 배울 장면 줄의 손실: "유효패 −5장" / "대기 −2장" / 큰 실수는 "샹텐 후퇴".
String lessonLossText(TurnReview t) {
  if ((t.shantenLoss ?? 0) > 0) return reviewCorner(t) ?? '샹텐 후퇴';
  final b = t.best;
  return '${ukeireWord(b?.shanten ?? 1)} −${t.ukeireLoss ?? 0}장';
}

/// 최선 보기 막대를 눌렀을 때 한 줄: "3만을 버리면 유효패: 1만 4만 2삭 5삭 (15장)".
/// 샹텐이 뒤로 가는 후보면 "… 버리면 2샹텐 · 유효패: …". 그 패가 후보에 없으면 null.
String? barInfoLine(TurnReview t, int tile) {
  DiscardOption? o;
  for (final x in t.options) {
    if (x.tile == tile) o = x;
  }
  final b = t.best;
  if (o == null || b == null) return null;
  final name = withEul(Tiles.name(tile));
  final back = o.shanten > b.shanten ? '${shantenText(o.shanten)} · ' : '';
  final live = [
    for (final u in o.ukeire.tiles)
      if (u.left > 0) Tiles.name(u.tile),
  ];
  final word = ukeireWord(o.shanten);
  if (live.isEmpty) return '$name 버리면 $back$word가 남아 있지 않습니다 (0장)';
  return '$name 버리면 $back$word: ${live.join(' ')} (${o.ukeire.total}장)';
}

// ── 단계 말풍선(3-4) ──

/// 단계 이름: 배패 · 리치 · 끝.
String stageName(ReviewStageKind k) => switch (k) {
      ReviewStageKind.start => '배패',
      ReviewStageKind.riichi => '리치',
      ReviewStageKind.end => '끝',
    };

/// 끝 결과 한 줄: "론 · 8,000점" / "쯔모 · 3,900점" / "유국" / "결과 기록 없음". [points] 가 null 이면 점수 없이.
String endResultText(PaifuResult? r, {int? points}) {
  if (r == null) return '결과 기록 없음';
  final pts = points == null ? '' : ' · ${formatPoints(points)}점';
  return switch (r.type) {
    'ron' => '론$pts',
    'tsumo' => '쯔모$pts',
    _ => '유국',
  };
}

/// 단계 문장. [seatLabel] 은 남의 리치 자리 이름("남 플레이어 1"), 끝 단계는 [result](예 [endResultText])와
/// [efficiencyPct] 를 받는다(끝은 두 줄: 결과 줄 + "이 판 패효율 94").
String stageSentence(
  ReviewStage s, {
  String Function(int seat)? seatLabel,
  String? result,
  int? efficiencyPct,
}) {
  switch (s.kind) {
    case ReviewStageKind.start:
      final n = s.startShanten ?? 0;
      return n <= 0 ? '배패 텐파이였습니다.' : '배패는 $n샹텐이었습니다.';
    case ReviewStageKind.riichi:
      if (s.heroRiichi) {
        final tail = s.afterRiichi > 0 ? ' 그 뒤 ${s.afterRiichi}번은 뽑은 패를 그대로 버렸습니다.' : '';
        return '${s.riichiTurn}순에 리치했습니다.$tail';
      }
      final seat = s.seat ?? 0;
      final who = seatLabel?.call(seat) ?? '${seat + 1}번';
      return '$who 자리가 리치했습니다. 여기부터 수비 판단은 평가하지 않습니다.';
    case ReviewStageKind.end:
      final pct = efficiencyPct == null ? '이 판은 평가한 버림이 없습니다' : '이 판 패효율 $efficiencyPct';
      return '${result ?? '결과 기록 없음'}\n$pct';
  }
}
