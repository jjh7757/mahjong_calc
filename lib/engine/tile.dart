/// 패 표현.
///
/// 패는 0~33 정수로 다룬다.
///   0~8   만수 1~9
///   9~17  통수 1~9
///   18~26 삭수 1~9
///   27~33 자패: 동 남 서 북 백 발 중
///
/// 문자열 코드는 `5m`, `3p`, `9s`, `1z`(동)~`7z`(중) 형식이고,
/// `0m` `0p` `0s` 는 적도라 5 를 뜻한다.
class Tiles {
  Tiles._();

  static const int man1 = 0;
  static const int pin1 = 9;
  static const int sou1 = 18;
  static const int east = 27;
  static const int south = 28;
  static const int west = 29;
  static const int north = 30;
  static const int white = 31;
  static const int green = 32;
  static const int red = 33;
  static const int count = 34;

  static const List<String> _suitChars = ['m', 'p', 's', 'z'];

  /// 0 만수, 1 통수, 2 삭수, 3 자패
  static int suit(int t) => t ~/ 9;

  /// 수패는 1~9, 자패는 0
  static int number(int t) => t < 27 ? t % 9 + 1 : 0;

  static bool isHonor(int t) => t >= 27;
  static bool isWind(int t) => t >= east && t <= north;
  static bool isDragon(int t) => t >= white;
  static bool isTerminal(int t) => t < 27 && (t % 9 == 0 || t % 9 == 8);
  static bool isTerminalOrHonor(int t) => isHonor(t) || isTerminal(t);
  static bool isSimple(int t) => !isTerminalOrHonor(t);

  /// 녹일색에 쓰이는 패: 2,3,4,6,8삭 + 발
  static bool isGreen(int t) =>
      t == green || (suit(t) == 2 && const [2, 3, 4, 6, 8].contains(number(t)));

  /// 도라 표시패 → 실제 도라
  static int doraFromIndicator(int indicator) {
    if (indicator < 27) {
      final s = suit(indicator);
      final n = number(indicator);
      return s * 9 + (n == 9 ? 0 : n);
    }
    if (isWind(indicator)) {
      return indicator == north ? east : indicator + 1;
    }
    return indicator == red ? white : indicator + 1;
  }

  /// `5m` 같은 코드를 정수로. `0m`은 5m으로 해석한다.
  static int parse(String code) {
    if (code.length != 2) {
      throw FormatException('패 코드는 두 글자여야 합니다: $code');
    }
    final n = int.tryParse(code[0]);
    final s = _suitChars.indexOf(code[1]);
    if (n == null || s < 0) throw FormatException('잘못된 패 코드: $code');
    if (s == 3) {
      if (n < 1 || n > 7) throw FormatException('자패는 1z~7z: $code');
      return 27 + n - 1;
    }
    if (n == 0) return s * 9 + 4;
    if (n < 1 || n > 9) throw FormatException('잘못된 패 코드: $code');
    return s * 9 + n - 1;
  }

  static bool isRedCode(String code) => code.length == 2 && code[0] == '0';

  static String toCode(int t) {
    if (t < 27) return '${number(t)}${_suitChars[suit(t)]}';
    return '${t - 27 + 1}z';
  }

  static const List<String> _names = [
    '1만', '2만', '3만', '4만', '5만', '6만', '7만', '8만', '9만',
    '1통', '2통', '3통', '4통', '5통', '6통', '7통', '8통', '9통',
    '1삭', '2삭', '3삭', '4삭', '5삭', '6삭', '7삭', '8삭', '9삭',
    '동', '남', '서', '북', '백', '발', '중',
  ];

  static String name(int t) => _names[t];
}

/// 마작 표기법 파싱 결과.
class ParsedTiles {
  final List<int> tiles;
  final int redCount;
  const ParsedTiles(this.tiles, this.redCount);
}

/// `123m456p0s11z` 또는 `1m 2m 3m` 형식을 패 목록으로 바꾼다.
/// 숫자 `0`은 적도라 5다.
ParsedTiles parseTiles(String text) {
  final tiles = <int>[];
  var red = 0;
  final cleaned = text.replaceAll(RegExp(r'\s+'), '');
  final buffer = <int>[];
  for (final ch in cleaned.split('')) {
    final digit = int.tryParse(ch);
    if (digit != null) {
      buffer.add(digit);
      continue;
    }
    final suit = const ['m', 'p', 's', 'z'].indexOf(ch);
    if (suit < 0) throw FormatException('알 수 없는 문자: $ch');
    if (buffer.isEmpty) throw FormatException('수트 앞에 숫자가 없습니다: $ch');
    for (final d in buffer) {
      if (d == 0) {
        if (suit == 3) throw FormatException('자패에는 적도라가 없습니다');
        red++;
      }
      tiles.add(Tiles.parse('$d$ch'));
    }
    buffer.clear();
  }
  if (buffer.isNotEmpty) throw FormatException('마지막 숫자에 수트가 없습니다');
  return ParsedTiles(tiles, red);
}

/// 패 목록을 34칸 개수 배열로.
List<int> toCounts(Iterable<int> tiles) {
  final counts = List<int>.filled(Tiles.count, 0);
  for (final t in tiles) {
    counts[t]++;
  }
  return counts;
}
