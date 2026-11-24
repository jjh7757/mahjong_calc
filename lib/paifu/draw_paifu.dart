/// 보통 유국(황패 유국) 국의 패보 — 거치 화면 유국 창이 확인된 뒤 남긴다(`docs/postgame_review_chat_design_1124.md` 10절 ②,
/// 대국 뒤 복기 대화에서 리치 받고 버틴 판을 장면으로 쓰려고). 순수 Dart, I/O 없음.
///
/// 화료 패보([DiscardRecorder.toPaifu] + 화료 판독)와 달리 손패 · 화료패 · 뒷도라가 없다. 도중 유국(구종구패 · 사가리치 등) ·
/// 트리플론 유국은 다루지 않는다(거치 화면이 저장하지 않음).
library;

import 'paifu.dart';

/// 유국 패보에 쓰는 메모.
const String drawPaifuNote = '버림만 자동으로 적은 기록(실험). 유국 — 손패 없음, 텐파이 자리는 유국 창에서 고른 값.';

/// 유국 패보의 hero: 텐파이 자리 중 가장 작은 번호, 아무도 텐파이가 아니면 친([dealer]).
/// 버림만 적은 판이라 판 중 손패가 없어 hero 는 재생 화면이 아래에 둘 자리(보는 시점)일 뿐이다 — 텐파이 자리를 아래에 두면
/// 유국 때 손을 지킨 사람 쪽에서 강을 보게 된다.
int drawHero(Iterable<int> tenpai, int dealer) {
  final seats = _seats(tenpai);
  return seats.isEmpty ? dealer : seats.first;
}

/// 0~3 만, 겹침 없이, 오름차순.
List<int> _seats(Iterable<int> tenpai) => ({...tenpai.where((s) => s >= 0 && s <= 3)}.toList()..sort());

/// 버림 사건([events], 보통 [DiscardRecorder.toPaifu] 의 사건) → 유국 패보. 버림이 하나도 없으면 null(저장할 것 없음).
///
/// - result: `type: 'draw'`, winner · loser · winTile · hand null, flags null, [PaifuResult.tenpai] = [tenpai] 자리 순.
/// - hero: [drawHero].
/// - 도라 표시패: 판 중 확정한 표시패([dora]) 하나, 없으면 빈 목록. 뒷도라는 빈 목록(유국엔 화료 판독이 없다).
Paifu? drawPaifu({
  required List<PaifuEvent> events,
  required String id,
  required int dealerSeat,
  required Iterable<int> tenpai,
  String round = '',
  int honba = 0,
  List<String> names = const ['', '', '', ''],
  List<int>? startScores,
  int? kyotaku,
  PaifuTile? dora,
}) {
  if (!events.any((e) => e.type == PaifuEventType.discard)) return null;
  final seats = _seats(tenpai);
  return Paifu(
    id: id,
    title: '$round${honba > 0 ? ' $honba본장' : ''}',
    round: round,
    honba: honba,
    dealer: dealerSeat,
    hero: drawHero(seats, dealerSeat),
    names: names,
    doraIndicators: [?dora],
    note: drawPaifuNote,
    events: events,
    startScores: startScores,
    kyotaku: kyotaku,
    result: PaifuResult(type: 'draw', tenpai: seats),
  );
}
