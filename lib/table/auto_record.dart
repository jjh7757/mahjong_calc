/// 거치 촬영 판독을 사람 확인 없이 대국에 반영해도 되는지(자동 반영 조건). 순수 Dart.
///
/// 확실하다고 보는 것: 판독 경고가 없음(자리 판독 3번 만장일치 등), 병합 플래그가 설명용뿐,
/// 화료 형태로 계산됐고, 화료자 한 명(동시 론 아님), 론이면 방총자를 앎, 파오 대상 역만이 아님(사용자가 골라야 함).
library;

import 'merge.dart';

/// 판독이 정한 근거를 알려 주기만 하는 병합 플래그. 이것만 있으면 자동 반영한다.
/// - winFromDiscard: 화료되는 강 끝이 한 자리뿐이라 그 자리 론
/// - riichiImpossible: 울린 손패라 사진 리치를 무시
/// - riichiMismatch: 사진·기록 리치가 다름(사진에 있으면 리치봉 자동 반영, 기록에 있으면 기록대로)
/// - meldTracked: 게임 중 두 번 읽어 확정한 울기
/// - riichiFromRiver: 유국으로 남은 봉 주인의 리치를 강의 눕힌 패로 정함(사용자 결정: 입력을 줄인다, 2026-10-30)
/// 나머지(방총자 후보 여럿, 화료패·론/쯔모 추정, 장수·울기·확신도 문제, 동시 론)는 사람이 본다.
const infoOnlyIssues = {
  MergeIssue.winFromDiscard,
  MergeIssue.riichiImpossible,
  MergeIssue.riichiMismatch,
  MergeIssue.meldTracked,
  MergeIssue.riichiFromRiver,
};

/// 자동 반영을 막는 이유. 반영해도 되면 null.
/// [warnings] 는 판독 경고(자리 판독이 엇갈림 등)와 동시 론 고르기 플래그, [issues] 는 화료자 병합 플래그 종류.
///
/// 도라 표시패 검사(2026-10-27, 매장 테스트 세트에서 리치·뒷도라·적도라를 놓친 채 자동 반영된 2건 뒤에 추가):
/// 판독 확신도로는 막을 수 없었다 — 개발 세트에서 리치봉은 있으면 늘 0.9·없으면 답이 없고(0), 5 패는 적5든 아니든 0.99.
/// 그래서 규칙에서 나온 장수만 본다: 표시패가 하나도 안 읽혔으면([doraIndicators] 0), 리치 화료인데 뒷도라까지
/// 2장이 안 보이면(촬영 순서: 화료 → 리치면 뒷도라 뒤집기 → 촬영) 사람이 본다. 개발 세트 36회 중 1회 막힘.
/// "리치가 아닌데 표시패가 1 + 깡 수보다 많음" 은 갤러리 장면이 연출이라(D 는 리치 없이 표시패 3장) 개발 세트로 확인할 수 없어 넣지 않았다.
String? autoRecordBlocker({
  required List<String> warnings,
  required List<MergeIssue> issues,
  required int otherWinners,
  required bool isTsumo,
  required int? loser,
  required bool resultValid,
  required int paoBase,
  required bool gameOver,
  required int doraIndicators,
  required bool riichi,
}) {
  if (gameOver) return '대국이 이미 끝남';
  if (!resultValid) return '화료 형태가 아님';
  if (warnings.isNotEmpty) return '판독 경고 ${warnings.length}개';
  final open = issues.where((i) => !infoOnlyIssues.contains(i)).toList();
  if (open.isNotEmpty) return '확인할 것: ${open.map((i) => i.name).join(', ')}';
  if (otherWinners > 0) return '동시 론';
  if (!isTsumo && loser == null) return '방총자를 모름';
  if (paoBase > 0) return '파오 대상 역만';
  if (doraIndicators == 0) return '도라 표시패를 못 읽음';
  if (riichi && doraIndicators < 2) return '리치 화료인데 뒷도라 표시패가 안 보임';
  return null;
}
