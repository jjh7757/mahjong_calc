/// 이미지 기준 자리([Side]) ↔ 대국 자리(0~3) 변환.
///
/// 위에서 내려다본 사진에서 차례는 반시계 방향(아래→오른쪽→위→왼쪽)이고,
/// 대국 자리는 기동 동가가 0 이고 차례대로 1·2·3 이다. 그래서 아래쪽 자리만 알면 나머지가 정해진다.
library;

import 'table_layout.dart';

class SeatMap {
  /// 사진 아래쪽 변에 앉은 사람의 자리.
  final int bottomSeat;

  const SeatMap(this.bottomSeat) : assert(bottomSeat >= 0 && bottomSeat < 4);

  int seatOf(Side side) => (bottomSeat + side.index) % 4;

  Side sideOf(int seat) => Side.values[((seat - bottomSeat) % 4 + 4) % 4];
}
