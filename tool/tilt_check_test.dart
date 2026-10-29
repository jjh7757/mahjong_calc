// 작탁 기울기 추정(`rectify.dart` tableTilt) 확인: 개발 세트 B·C·D 원본·합성 기울기(a +25°, b −18°, c +10°)와
// [참고·평가 밖] 매장 삼각대 15장. 합성은 원본 기울기에 더해진 각도라 "합성 − 원본" 이 넣은 각도와 맞는지 본다.
//   flutter test tool/tilt_check_test.dart
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/rectify.dart';

const _kakao = 'experiments/field_20261024/kakao_photos';
const _field = 'experiments/field_20261024/captures';
const _added = {'a': 25.0, 'b': -18.0, 'c': 10.0};

double? _tilt(String path) {
  final im = img.decodeJpg(File(path).readAsBytesSync())!;
  final small = img.copyResize(img.bakeOrientation(im), width: 1000);
  final q = findFeltQuad(small);
  return q == null ? null : tableTilt(q, aspect: small.width / small.height);
}

void main() {
  test('tilt', () {
    final out = <String, double?>{};
    final base = <String, double?>{};
    for (final p in ['k25', 'k28', 'k15', 'k26', 'k12', 'k16']) {
      base[p] = _tilt('$_kakao/$p.jpg');
      out[p] = base[p];
      // ignore: avoid_print
      print('원본 $p ${base[p]?.toStringAsFixed(1)}°');
    }
    for (final p in base.keys) {
      for (final MapEntry(key: v, value: add) in _added.entries) {
        final t = _tilt('$_kakao/tilted/${p}_$v.jpg');
        out['tilted/${p}_$v'] = t;
        final d = t == null || base[p] == null ? null : t - base[p]!;
        // ignore: avoid_print
        print('합성 ${p}_$v ${t?.toStringAsFixed(1)}° (원본과 차 ${d?.toStringAsFixed(1)}°, 넣은 각 $add°, 오차 ${d == null ? '-' : (d - add).toStringAsFixed(1)}°)');
      }
    }
    for (final p in ['122922', '124007', '125053', '130533', '131210', '132647', '133011', '133620', '134323', '135148',
                     '135912', '140302', '140750', '140918', '143443']) {
      // ignore: avoid_print
      out[p] = _tilt('$_field/20261024_$p/original.jpg');
      // ignore: avoid_print
      print('매장 $p ${out[p]?.toStringAsFixed(1)}°');
    }
    File('experiments/rectify/results/tilt.json').writeAsStringSync(jsonEncode(out));
  });
}
