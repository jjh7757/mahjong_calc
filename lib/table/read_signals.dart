/// 판독 불확실성 신호의 문턱(개선 계획 5단계, 2026-11-05). 순수 Dart.
///
/// 서버 `/v2/localroles` 가 자리 판독마다 `signals` 를 낸다(mahjong-recognizer feat/cls-alt `app/signals.py`, 답은 안 바꿈).
/// 문턱은 `experiments/speed/select_thresholds.py` 가 개발 세트(회귀 고정 21변형 fold·prod + 개발 32회 앱 흐름)로만 골랐다 —
/// "경고 없는 틀린 자동 0" 을 지키면서 맞는 자동 반영을 가장 적게 막는 값(metrics 표 1-93). 테스트 15장은 끝에 한 번만 적용했다.
/// 신호가 없으면(운영 서버가 아직 안 냄) 아무것도 막지 않는다.
library;

/// 신호 하나의 문턱과 쓰임(막음 = 자동 반영을 막음, 경고 = 경고와 함께 20초 기다림).
class SignalRule {
  final String key;
  final String label;
  final double? below; // 값 < below 이면 켜짐(확률 차·검출 확신도)
  final int? atLeast; // 값 >= atLeast 이면 켜짐(다른 패·상자 수)
  final bool block;
  const SignalRule(this.key, this.label, {this.below, this.atLeast, this.block = true});
}

/// 고른 문턱(select_thresholds.py → experiments/speed/results/thresholds.json). null 문턱 = 안 씀.
/// 2026-11-05 결과: S1~S5 는 **모두 안 씀**. 개발 입력(회귀 21변형 fold·prod 1,344행 + 개발 32회 앱 흐름)에서 경고 없는 틀린 자동이
/// 화료패 누락(떼어 둔 화료패를 못 찾아 13장 텐파이 — 읽은 패에 붙는 신호로는 원리상 못 잡음) 말고는 0 이라 막을 근거가 없었다.
/// 경고 있는 틀린 자동까지 막으려면 S1 < 0.998 이 필요하고 맞는 자동 143개를 막는다(참고 계산, thresholds_all.json).
/// 값은 서버가 계속 내므로(촬영 기록 hand_read.signals) 다음 매장 사진으로 다시 고를 수 있다.
const readSignalRules = <SignalRule>[
  SignalRule('margin_min', '확률 차', below: null),
  SignalRule('det_min', '검출 확신도', below: null),
  SignalRule('cls2_diff', '분류기 2벌', atLeast: null),
  SignalRule('role_diff', '역할 3씨드', atLeast: null),
  SignalRule('jitter_diff', '입력 흔들기', atLeast: null),
];

/// S6 5 패 빨강 검사 문턱(색마다): 5 로 읽었는데 붉은 잉크 비율 ≥ 문턱이면 적5 같음, 적5 로 읽었는데 < 문턱이면 보통 5 같음.
/// 개발 크롭(적5·보통 5 양쪽)의 보통 5 최댓값과 적5 최솟값 가운데.
/// 개발 크롭 보통 5 최대 / 적5 최소: 만 0.430 / 0.888, 통 0.037 / 0.977, 삭 0.108 / 0.830. 개발 입력 전체에서 한 번도 안 켜짐(헛경보 0).
/// 잡은 틀린 자동이 없어 막지 않고 경고(20초)로 둔다.
const redFiveThreshold = <String, double>{'m': 0.659, 'p': 0.507, 's': 0.469};
const redFiveBlock = false;

/// 신호 판정 결과: 자동 반영을 막는 이유와 경고(짧은 말).
class ReadSignalCheck {
  final List<String> blocks;
  final List<String> cautions;
  const ReadSignalCheck(this.blocks, this.cautions);
  static const none = ReadSignalCheck([], []);
  Map<String, dynamic> toJson() => {'blocks': blocks, 'cautions': cautions};
}

/// 빨강 검사가 어긋난 패 코드들(`5m` 인데 붉음 → `5m→0m?`).
List<String> redFiveMismatches(Map<String, dynamic> signals, {Map<String, double> thresholds = redFiveThreshold}) {
  final out = <String>[];
  for (final x in (signals['red'] as List<dynamic>?) ?? const []) {
    if (x is! Map) continue;
    final tile = x['tile'] as String?;
    final r = (x['ratio'] as num?)?.toDouble();
    if (tile == null || r == null || tile.length != 2) continue;
    final th = thresholds[tile[1]];
    if (th == null) continue;
    if (tile[0] == '5' && r >= th) out.add('$tile→0${tile[1]}?');
    if (tile[0] == '0' && r < th) out.add('$tile→5${tile[1]}?');
  }
  return out;
}

/// 서버 신호 → 막음·경고. [rules]·[red] 는 시험용으로 바꿀 수 있다.
ReadSignalCheck checkReadSignals(
  Map<String, dynamic>? signals, {
  List<SignalRule> rules = readSignalRules,
  Map<String, double> red = redFiveThreshold,
  bool redBlock = redFiveBlock,
}) {
  if (signals == null) return ReadSignalCheck.none;
  final blocks = <String>[], cautions = <String>[];
  for (final r in rules) {
    final v = (signals[r.key] as num?)?.toDouble();
    if (v == null) continue;
    final on = (r.below != null && v < r.below!) || (r.atLeast != null && v >= r.atLeast!);
    if (!on) continue;
    final s = '${r.label} ${r.below != null ? v.toStringAsFixed(2) : v.toInt()}';
    (r.block ? blocks : cautions).add(s);
  }
  final reds = redFiveMismatches(signals, thresholds: red);
  if (reds.isNotEmpty) (redBlock ? blocks : cautions).add('적5 빨강 ${reds.join(' ')}');
  return ReadSignalCheck(blocks, cautions);
}
