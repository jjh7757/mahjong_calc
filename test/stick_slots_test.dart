import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/stick_slots.dart';
import 'package:mahjong_calc/table/table_layout.dart';

/// 리치봉 홈 픽셀 판정: 색과 무관(파랑·노랑·빨강), 버튼·가는 줄은 안 잡는다. 그림은 손으로 만든 120×114 기기.
void main() {
  const zone = NormBox(0, 0, 1000, 1000);

  img.Image device({List<(int, int, int, int, img.Color)> bars = const []}) {
    final im = img.Image(width: 120, height: 114);
    img.fill(im, color: img.ColorRgb8(30, 32, 40)); // 검은 기기
    // 빈 홈(더 검은 홈), 버튼들(짧은 진한 색 덩어리), 주사위 창(초록 펠트).
    img.fillRect(im, x1: 30, y1: 4, x2: 90, y2: 14, color: img.ColorRgb8(12, 12, 14));
    img.fillCircle(im, x: 32, y: 32, radius: 6, color: img.ColorRgb8(220, 30, 40)); // 빨간 버튼
    img.fillRect(im, x1: 80, y1: 26, x2: 92, y2: 38, color: img.ColorRgb8(30, 70, 220)); // 파란 마름모 버튼
    img.fillCircle(im, x: 60, y: 57, radius: 14, color: img.ColorRgb8(40, 140, 70)); // 펠트 초록 창
    for (final (x1, y1, x2, y2, c) in bars) {
      img.fillRect(im, x1: x1, y1: y1, x2: x2, y2: y2, color: c);
    }
    return im;
  }

  final blue = img.ColorRgb8(40, 80, 230), yellow = img.ColorRgb8(240, 200, 30), red = img.ColorRgb8(225, 35, 40);

  test('빈 기기(버튼·초록 창만)는 아무 자리도 아니다', () {
    expect(stickSlotsIn(device(), zone).values.where((v) => v), isEmpty);
  });

  test('파랑·노랑·빨강 봉 모두 그 홈 자리로 잡는다', () {
    for (final c in [blue, yellow, red]) {
      final got = stickSlotsIn(device(bars: [(36, 98, 86, 108, c)]), zone); // 아래 홈 50×10
      expect(got[Side.bottom], isTrue, reason: '$c');
      expect(got[Side.top], isFalse);
      final left = stickSlotsIn(device(bars: [(3, 32, 13, 82, c)]), zone); // 왼쪽 홈 10×50
      expect(left[Side.left], isTrue, reason: '$c');
      expect(left[Side.right], isFalse);
    }
  });

  test('구역 가장자리의 아주 가는 색 줄(길이/두께 > 9)은 봉이 아니다', () {
    final got = stickSlotsIn(device(bars: [(20, 109, 92, 113, red)]), zone); // 72×4
    expect(got[Side.bottom], isFalse);
  });

  test('짧은 덩어리(손에 반쯤 가린 봉)는 잡지 않는다 — 추적기가 다음 프레임에서 본다', () {
    final got = stickSlotsIn(device(bars: [(36, 98, 56, 108, blue)]), zone); // 20×10
    expect(got[Side.bottom], isFalse);
  });

  test('펠트 초록은 진한 색이어도 뺀다', () {
    expect(isStickColor(40, 140, 70), isFalse);
    expect(isStickColor(40, 80, 230), isTrue);
    expect(isStickColor(240, 200, 30), isTrue);
    expect(isStickColor(230, 230, 230), isFalse); // 흰 패
  });
}
