/// 유국 때 손패를 앞면으로 공개한 자리(= 텐파이 신고) 찾기. 순수 Dart, API 없음.
///
/// 화료자 고르기([faceUpByPattern])는 "1등 넓이의 1/2 이상" 비율을 써서 여러 자리가 공개하면 작게 찍힌 먼 자리를 떨군다.
/// 유국용은 비율 없이 자리마다 절대 넓이 [drawRevealMinArea] 로 보고, 펠트 사각형([readFelt])을 [drawRevealFeltPad] 만큼
/// 넓힌 밖의 흰색을 지워 자동탁 흰 테두리 속 검은 홈·화면이 무늬로 세어지지 않게 한다.
/// 유국 공개 합성 216장(테스트 원본 36장 × 텐파이 0~4자리)에서 장면 207/216·자리 855/864(지금 화료자 규칙은 179/216),
/// metrics 표 5-1, problem_log 58. 펠트를 못 찾으면 지우지 않고 잰다.
/// 노텐은 세워 둔 채든 엎든 무늬가 거의 없어 둘 다 노텐으로 본다(2026-11-13 사용자 "앞면 여부만 확인").
library;

import 'dart:math' as math;
import 'dart:typed_data';

import 'cropper.dart' show shrinkForLocate;
import 'felt_grid.dart' show readFelt;
import 'fixed_layout.dart' show decodeSmall, tilePatternArea, whiteMask;
import 'grid_zones.dart';
import 'table_layout.dart';

/// 공개 손패로 볼 손패 칸 무늬 넓이 하한(긴 변 1024 기준 픽셀). 합성에서 노텐 최대 298·418·539px, 공개 대부분 1,000px 넘음.
const int drawRevealMinArea = 500;

/// 펠트 사각형을 바깥으로 넓히는 거리(사진 정규화). 0.01 이면 펠트 끝에 걸친 공개 손패까지 지웠다(합성 200/216).
const double drawRevealFeltPad = 0.05;

class DrawReveal {
  /// 공개한 자리(무늬 많은 순).
  final List<Side> revealed;

  /// 자리별 무늬 넓이(축소본 픽셀, 펠트 밖 지운 뒤).
  final Map<Side, int> patterns;

  /// 펠트를 찾아 밖을 지웠는가.
  final bool feltMasked;

  const DrawReveal(this.revealed, this.patterns, {required this.feltMasked});

  Map<String, Object?> toJson() => {
        'revealed': [for (final s in revealed) s.name],
        'patterns': {for (final e in patterns.entries) e.key.name: e.value},
        'felt_masked': feltMasked,
      };
}

/// 사각형 꼭짓점을 무게중심에서 [pad](정규화)만큼 바깥으로.
List<math.Point<double>> _grow(List<math.Point<double>> c, double pad) {
  final cx = c.map((p) => p.x).reduce((a, b) => a + b) / 4, cy = c.map((p) => p.y).reduce((a, b) => a + b) / 4;
  return [
    for (final p in c)
      () {
        final dx = p.x - cx, dy = p.y - cy, d = math.sqrt(dx * dx + dy * dy);
        return d == 0 ? p : math.Point(p.x + dx / d * pad, p.y + dy / d * pad);
      }()
  ];
}

bool _inQuad(List<math.Point<double>> q, double x, double y) {
  var pos = 0, neg = 0;
  for (var i = 0; i < 4; i++) {
    final a = q[i], b = q[(i + 1) % 4];
    final cr = (b.x - a.x) * (y - a.y) - (b.y - a.y) * (x - a.x);
    if (cr > 0) pos++;
    if (cr < 0) neg++;
  }
  return pos == 0 || neg == 0;
}

/// [jpeg](헤드 프레임, 크기 상관없음 — 긴 변 1024 로 줄여 잰다)와 [grid] 로 공개 손패 자리. `compute()` 에 넘길 수 있다.
DrawReveal findDrawReveal((Uint8List, GridZones) args) {
  final (jpeg, grid) = args;
  final im = decodeSmall(shrinkForLocate(jpeg));
  final white = whiteMask(im);
  final felt = readFelt(im);
  if (felt != null) {
    final q = _grow(felt.quad.corners, drawRevealFeltPad);
    var i = 0;
    for (var y = 0; y < im.height; y++) {
      for (var x = 0; x < im.width; x++, i++) {
        if (white[i] == 1 && !_inQuad(q, (x + 0.5) / im.width, (y + 0.5) / im.height)) white[i] = 0;
      }
    }
  }
  final patterns = {for (final s in Side.values) s: tilePatternArea(im, white, grid.handCell(s))};
  final scale = (im.width > im.height ? im.width : im.height) / 1024;
  final min = drawRevealMinArea * scale * scale;
  final revealed = patterns.keys.where((s) => patterns[s]! >= min).toList()..sort((a, b) => patterns[b]!.compareTo(patterns[a]!));
  return DrawReveal(revealed, patterns, feltMasked: felt != null);
}
