import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart' show Tiles;
import 'package:mahjong_calc/table/observation.dart';
import 'package:mahjong_calc/table/table_reading.dart';
import 'package:mahjong_calc/table/wide_seat.dart';

List<ReadTile> _t(String s) => [for (final c in s.split(' ')) if (c.isNotEmpty) ReadTile.fromCode(c, 0.9)!];
ReadTile _one(String c) => ReadTile.fromCode(c, 0.9)!;

SeatV2 _seat(String hand, {String? sep, List<String> melds = const []}) => (
      faceUp: true,
      tiles: _t(hand),
      separate: sep == null ? null : _one(sep),
      melds: [for (final m in melds) ObservedMeld(_t(m), conf: 0.9)],
      loose: const <ReadTile>[],
      agreement: (reads: 3, agree: 3, unanimous: true, alternatives: const <String>[]),
    );

WideRead _wide(String row, {String lone = '', String grouped = '', List<String> melds = const [], bool unanimous = true}) => WideRead(
      row: row.isEmpty ? null : _t(row),
      lone: _t(lone),
      grouped: _t(grouped),
      melds: [for (final m in melds) ObservedMeld(_t(m), conf: 0.9)],
      unanimous: unanimous,
    );

// 10-31 매장 장면 그대로
const h143104 = '5s 6s 6p 7p 8p 2m 3m 4m 7m 8m 9m 6z 6z'; // 떼어 둔 7s
const h133826 = '4p 5p 6p 2m 2m 3m 4m 5m 6s 5s 7s 8p 8p'; // 대기 2m·8p, 표시패 8m·8p

void main() {
  group('모양 검사', () {
    test('일반형·치또이·국사', () {
      expect(closedWins(_t('$h143104 7s').map((t) => t.tile).toList()), isTrue);
      expect(closedWins(_t('5z 5z 2p 2p 1s 1s 2s 2s 8s 8s 4m 4m 0s 5s').map((t) => t.tile).toList()), isTrue);
      expect(closedWins(_t('1m 9m 1p 9p 1s 9s 1z 2z 3z 4z 5z 6z 7z 7z').map((t) => t.tile).toList()), isTrue);
      expect(closedWins(_t('$h143104 9s').map((t) => t.tile).toList()), isFalse);
    });

    test('같은 패 5장은 화료형이 아니다', () {
      expect(closedWins(_t('1m 1m 1m 1m 1m 2m 3m').map((t) => t.tile).toList()), isFalse);
    });

    test('울기 뺀 패도 본다', () {
      expect(closedTenpai(_t('0m 5m 6m 7m 6p 7p 8p').map((t) => t.tile).toList()), isTrue);
      expect(closedTenpai(_t('1m 4m 7m 1p 4p 7p 1s').map((t) => t.tile).toList()), isFalse);
    });
  });

  group('넓은 구역을 부를지', () {
    test('14장 화료형이면 안 부른다', () {
      expect(seatNeedsWide(_seat(h143104, sep: '7s'), const []), isFalse);
    });

    test('13장 텐파이 + 강 끝 패로 화료되면 안 부른다(133826)', () {
      expect(seatNeedsWide(_seat(h133826), [_one('2m'), _one('9p')]), isFalse);
    });

    test('13장 텐파이인데 강 끝에 없으면 부른다', () {
      expect(seatNeedsWide(_seat(h143104), [_one('1z'), null]), isTrue);
    });

    test('장수·모양이 안 맞으면 부른다', () {
      expect(seatNeedsWide(_seat('3z 3z 3z 2p 3p 5p 5p 7p 8p 9p'), const []), isTrue); // 164501: 백 울기 놓침
      expect(seatNeedsWide(_seat('1m 2m 4m 7m 9m 1p 3p 5p 7p 9p 1s 3s 5s'), const []), isTrue); // 13장인데 노텐
    });
  });

  group('흩어진 손패를 울기로 묶은 답 바로잡기(175951)', () {
    const row = '4m 4m 6m 7m 9s 6s 3z 5s 3z 4s 7s 3z 8s'; // 넓은 줄 13장(론 패 8m 은 강에)
    SeatV2 doubtful() => (
          faceUp: true,
          tiles: _t('4m 4m 6m 7m'),
          separate: null,
          melds: [for (final m in ['2s 3s 4s', '6s 7s 8s', '4z 4z 4z']) ObservedMeld(_t(m), conf: 0)],
          loose: const <ReadTile>[],
          agreement: (reads: 3, agree: 1, unanimous: false, alternatives: const <String>[]),
        );

    test('엇갈리고 확신도 0 인 울기는 미덥지 않다, 만장일치·확신도 높으면 아니다', () {
      expect(meldsDoubtful(doubtful()), isTrue);
      expect(meldsDoubtful(_seat('4m 4m 6m 7m', melds: ['2s 3s 4s'])), isFalse);
      expect(meldsDoubtful(_seat(h143104)), isFalse);
    });

    test('넓은 줄이 울기 없이 손패·울기 패를 다 담은 텐파이 한 줄이면 그 줄을 손패로', () {
      final r = applyScattered(doubtful(), _wide('4m 4m 6m 7m 2s 3s 4s 6s 7s 8s 4z 4z 4z'));
      expect(r, isNotNull);
      expect(r!.seat.melds, isEmpty);
      expect(r.seat.tiles.length, 13);
      expect(r.note, contains('3묶음'));
    });

    test('줄 장수가 안 맞거나 패가 빠지거나 모양이 아니거나 넓은 판독에도 울기가 있으면 그대로', () {
      expect(applyScattered(doubtful(), _wide(row)), isNull, reason: '패 구성이 다르다(9s·5s…)');
      expect(applyScattered(doubtful(), _wide('4m 4m 6m 7m 2s 3s 4s 6s 7s 8s 4z 4z')), isNull, reason: '12장');
      expect(applyScattered(doubtful(), _wide('4m 4m 6m 7m 2s 3s 4s 6s 7s 8s', melds: ['4z 4z 4z'])), isNull, reason: '넓은 판독도 울기');
      expect(applyScattered(doubtful(), _wide('4m 4m 6m 7m 2s 3s 4s 6s 7s 9s 4z 4z 4z')), isNull, reason: '구성 다름');
    });
  });

  group('합치기', () {
    test('13장 + 외톨이로 화료형이면 떼어 둔 패(143104)', () {
      final r = applyWide(_seat(h143104), _wide(h143104, lone: '7s'));
      expect(r.seat.separate!.tile, Tiles.parse('7s'));
      expect(r.seat.tiles.length, 13);
      expect(r.seat.agreement!.unanimous, isTrue);
      expect(r.note, contains('7s'));
    });

    test('외톨이가 화료형을 못 만들거나 없거나 여럿이면 그대로(후보 창으로)', () {
      expect(applyWide(_seat(h143104), _wide(h143104, lone: '9p')).note, isNull);
      expect(applyWide(_seat(h143104), _wide(h143104)).note, isNull);
      expect(applyWide(_seat(h143104), _wide(h143104, lone: '7s 4s')).note, isNull);
    });

    test('넓은 줄에 붙어 읽힌 떼어 둔 패도 받는다(171505 3m)', () {
      const row = '6s 7s 8s 2p 2p 4m 5m 5p 6p 7p';
      final r = applyWide(_seat(row, melds: ['7z 7z 7z']), _wide('$row 3m', melds: ['7z 7z 7z']));
      expect(r.seat.separate!.code, '3m');
      expect(r.seat.tiles.length, 10);
      // 줄이 두 장 이상 다르면(오독) 받지 않는다.
      final w = applyWide(_seat(row, melds: ['7z 7z 7z']), _wide('6s 7s 8s 2p 2p 4m 5m 5p 6p 8p 3m'));
      expect(w.note, isNull);
    });

    test('외톨이와 줄 한 장이 다른 화료패를 가리키면 고르지 않는다', () {
      const row = '6s 7s 8s 2p 2p 4m 5m 5p 6p 7p';
      final r = applyWide(_seat(row, melds: ['7z 7z 7z']), _wide('$row 3m', lone: '6m'));
      expect(r.note, isNull);
    });

    test('붙어 있는 두 장(표시패)은 13장에 더하지 않는다(133826)', () {
      final r = applyWide(_seat(h133826), _wide(h133826, grouped: '8m 8p'));
      expect(r.note, isNull);
      expect(r.seat.separate, isNull);
    });

    test('줄 + 모서리 울기로 13장 텐파이(164501·171245)', () {
      const row = '3z 3z 3z 2p 3p 5p 5p 7p 8p 9p';
      final r = applyWide(_seat('3z 3z 3z 2p 3p 4p 5p 7p 8p 9p'), _wide(row, melds: ['5z 5z 5z']));
      expect([for (final t in r.seat.tiles) t.code].join(' '), row);
      expect(r.seat.separate, isNull);
      expect(r.seat.melds.single.tiles.first.code, '5z');
      expect(r.note, isNotNull);
    });

    test('줄 + 외톨이로 14장(171505: 울기 + 떼어 둔 3m)', () {
      final r = applyWide(
        _seat('6s 7s 8s 2p 2p 4m 5m 5p 6p 7p'),
        _wide('6s 7s 8s 2p 2p 4m 5m 5p 6p 7p', lone: '3m', melds: ['7z 7z 7z']),
      );
      expect(r.seat.separate!.code, '3m');
      expect(r.seat.tiles.length, 10);
      expect(r.seat.melds.length, 1);
    });

    test('흩어진 손패: 낱장 조합이 하나면 받는다(175951)', () {
      // 8s 하나는 표시패. 론이라 13장 텐파이가 답이고 떼어 둔 패는 없다.
      final r = applyWide(_seat('4m 4m 6m 7m'), _wide('4m 4m 6m 7m', grouped: '9s 6s 3z 5s 8s 3z 4s 7s 3z 8s'));
      expect(r.seat.tiles.length, 13);
      expect(r.seat.separate, isNull);
      expect(closedTenpai([for (final t in r.seat.tiles) t.tile]), isTrue);
      expect([for (final t in r.seat.loose) t.code], ['8s']);
    });

    test('떼어 둔 두 장이 붙어 있어도 장수가 모자라면 받는다(142535)', () {
      const row = '5z 5z 2p 2p 1s 1s 2s 2s 8s 8s 4m 4m';
      final r = applyWide(_seat(row), _wide(row, grouped: '0s 5s 4m 9p'));
      final codes = [for (final t in r.seat.tiles) t.code, if (r.seat.separate case final s?) s.code];
      expect(codes.length, 14);
      expect(codes, containsAll(['0s', '5s']));
      expect([for (final t in r.seat.loose) t.code]..sort(), ['4m', '9p']);
    });

    test('조합이 여럿이면 고르지 않는다', () {
      const row = '1m 2m 3m 4p 5p 6p 7s 8s 9s 1z 1z 2m'; // 12장
      final r = applyWide(_seat(row), _wide(row, grouped: '1m 3m 4m 2z'));
      expect(r.note, isNull);
    });

    test('넓은 구역이 뒷면 칸을 읽었거나 틀을 못 잡았으면 그대로', () {
      final j = {
        'row': [
          {'tile': '1m', 'conf': 0.9},
          null,
        ],
      };
      expect(WideRead.fromJson(j).row, isNull);
      expect(applyWide(_seat('1m 2m'), _wide('')).note, isNull);
    });

    test('추적으로 아는 울기는 자리 판독 것을 쓴다', () {
      final seat = _seat('1m 2m 3m 4p 5p 6p 7s 8s 9s 1z', melds: ['2z 2z 2z']);
      final r = applyWide((
        faceUp: seat.faceUp,
        tiles: _t('1m 2m 3m 4p 5p 6p 7s 8s 1z'),
        separate: null,
        melds: seat.melds,
        loose: seat.loose,
        agreement: seat.agreement,
      ), _wide('1m 2m 3m 4p 5p 6p 7s 8s 9s 1z', melds: ['3z 3z 3z']), meldsKnown: true);
      expect(r.seat.melds.single.tiles.first.code, '2z');
    });
  });

  test('응답 해석: lone·grouped 나누기, 적5', () {
    final w = WideRead.fromJson({
      'row': [
        {'tile': '0s', 'conf': 0.9},
      ],
      'singles': [
        {'tile': '7s', 'conf': 0.9, 'lone': true},
        {'tile': '8m', 'conf': 0.9, 'lone': false},
      ],
      'melds': [
        {'tiles': ['5z', '5z', '5z'], 'sideways': [], 'face_down': [], 'conf': 0.9},
      ],
      'agreement': {'unanimous': true},
    });
    expect(w.row!.single.red, isTrue);
    expect(w.lone.single.code, '7s');
    expect(w.grouped.single.code, '8m');
    expect(w.melds.single.tiles.length, 3);
    expect(w.unanimous, isTrue);
  });
}
