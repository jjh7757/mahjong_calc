import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/table/auto_record.dart';
import 'package:mahjong_calc/table/read_signals.dart';
import 'package:mahjong_calc/table/table_reading.dart';

void main() {
  const rules = [
    SignalRule('margin_min', '확률 차', below: 0.5),
    SignalRule('det_min', '검출 확신도', below: 0.4, block: false),
    SignalRule('cls2_diff', '분류기 2벌', atLeast: 1),
    SignalRule('role_diff', '역할 3씨드', atLeast: 2),
    SignalRule('jitter_diff', '입력 흔들기', atLeast: null),
  ];
  const red = {'m': 0.66, 'p': 0.5, 's': 0.47};

  test('신호가 없으면 아무것도 막지 않는다(운영 서버가 아직 안 냄)', () {
    final c = checkReadSignals(null, rules: rules, red: red);
    expect(c.blocks, isEmpty);
    expect(c.cautions, isEmpty);
  });

  test('문턱 밖이면 조용하다', () {
    final c = checkReadSignals({'margin_min': 0.9, 'det_min': 0.9, 'cls2_diff': 0, 'role_diff': 1, 'jitter_diff': 5, 'red': []}, rules: rules, red: red);
    expect(c.blocks, isEmpty);
    expect(c.cautions, isEmpty);
  });

  test('막음 신호와 경고 신호를 나눈다', () {
    final c = checkReadSignals({'margin_min': 0.3, 'det_min': 0.2, 'cls2_diff': 1, 'role_diff': 2}, rules: rules, red: red);
    expect(c.blocks, ['확률 차 0.30', '분류기 2벌 1', '역할 3씨드 2']);
    expect(c.cautions, ['검출 확신도 0.20']);
  });

  test('S6: 5 로 읽었는데 붉으면, 적5 로 읽었는데 안 붉으면', () {
    final s = {
      'red': [
        {'tile': '5m', 'ratio': 0.9},
        {'tile': '5p', 'ratio': 0.01},
        {'tile': '0s', 'ratio': 0.2},
        {'tile': '0p', 'ratio': 0.99},
        {'tile': '5s', 'ratio': null},
      ],
    };
    expect(redFiveMismatches(s, thresholds: red), ['5m→0m?', '0s→5s?']);
    expect(checkReadSignals(s, rules: rules, red: red, redBlock: true).blocks, ['적5 빨강 5m→0m? 0s→5s?']);
    expect(checkReadSignals(s, rules: rules, red: red, redBlock: false).cautions, ['적5 빨강 5m→0m? 0s→5s?']);
  });

  test('지금 고른 값(표 1-93): S1~S5 는 안 막고, S6 는 경고만', () {
    final c = checkReadSignals({
      'margin_min': 0.01,
      'det_min': 0.1,
      'cls2_diff': 9,
      'role_diff': 9,
      'jitter_diff': 9,
      'red': [
        {'tile': '5m', 'ratio': 0.95},
      ],
    });
    expect(c.blocks, isEmpty);
    expect(c.cautions, ['적5 빨강 5m→0m?']);
    expect(checkReadSignals({'red': [{'tile': '5m', 'ratio': 0.43}, {'tile': '0p', 'ratio': 0.98}]}).cautions, isEmpty);
  });

  test('HandReading 이 signals 를 받아 촬영 기록에 남긴다', () {
    final h = HandReading.fromJson({
      'tiles': [
        {'tile': '1m', 'conf': 0.9},
      ],
      'signals': {'margin_min': 0.2},
    });
    expect(h.signals, {'margin_min': 0.2});
    expect(h.toJson()['signals'], {'margin_min': 0.2});
    expect(h.withWinTile(const ReadTile(5)).signals, {'margin_min': 0.2});
    expect(HandReading.fromJson({'tiles': []}).toJson().containsKey('signals'), isFalse);
  });

  test('autoRecordBlocker·autoRecordCautions 가 신호를 받는다', () {
    String? block(List<String> s) => autoRecordBlocker(
          warnings: const [],
          issues: const [],
          otherWinners: 0,
          isTsumo: true,
          loser: null,
          resultValid: true,
          paoBase: 0,
          gameOver: false,
          signalBlocks: s,
        );
    expect(block(const []), isNull);
    expect(block(const ['확률 차 0.30']), '판독 신호: 확률 차 0.30');
    expect(autoRecordCautions(issues: const [], doraIndicators: 1, riichi: false, signalCautions: const ['x']), ['판독 신호']);
    expect(autoRecordCautions(issues: const [], doraIndicators: 1, riichi: false), isEmpty);
  });
}
