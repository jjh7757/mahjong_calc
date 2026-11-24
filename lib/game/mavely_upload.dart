import 'dart:convert';

import 'game.dart';

/// 동호회 기록 사이트 '마블리'의 대국 입력 페이지. 앱 안 WebView 로 열어 값을 채우고, '등록' 은 사용자가 누른다.
const mavelyNewUrl = 'https://mavely.isugame.com/new';

/// 마블리는 시작점 25000 고정이다(점수 합 + 공탁금 = 100000 을 검사한다).
const mavelyStartPoints = 25000;
const mavelyTotal = 4 * mavelyStartPoints;

/// 마블리에 올릴 값. 자리 순서는 기동 동·남·서·북(우리 자리 0~3 과 같다).
class MavelyEntry {
  final List<String> names;

  /// 최종 점수(남은 공탁을 1위에게 주기 전). 음수면 토비.
  final List<int> points;
  final List<int> stars;

  /// 공탁금(점). 동호회는 남은 공탁을 1위에게 주지 않고 따로 적는다.
  final int deposit;

  /// 올릴 수 없는 사유(시작점이 25000 이 아님, 합이 안 맞음 등). 올릴 수 있으면 null.
  final String? problem;

  const MavelyEntry({
    required this.names,
    required this.points,
    required this.stars,
    required this.deposit,
    this.problem,
  });

  bool get ok => problem == null;
}

/// 대국 [g] 에서 마블리에 올릴 값을 만든다.
///
/// - 끝날 때 남은 공탁을 1위에게 준 사건([Game.isLeftoverStickEvent])이 있으면 그 몫을 받은 자리에서 빼고 공탁금에 더한다.
/// - 아직 남아 있는 공탁([Game.riichiSticks], 끝나기 전 정산 등)도 공탁금에 더한다.
/// - 결과는 늘 점수 합 + 공탁금 = 100000 이어야 한다. 아니면(시작점 ≠ 25000, 수동 조정으로 합이 어긋남 등) [MavelyEntry.problem].
MavelyEntry mavelyEntryFor(Game g) {
  final points = List.of(g.scores);
  var deposit = g.riichiSticks * 1000;
  for (var i = 0; i < g.events.length; i++) {
    if (!Game.isLeftoverStickEvent(g.events, i)) continue;
    final d = g.events[i].delta;
    for (var s = 0; s < 4; s++) {
      points[s] -= d[s];
      deposit += d[s];
    }
  }
  final stars = [for (var s = 0; s < 4; s++) g.starsOf(s)];
  final names = List.of(g.names);

  String? problem;
  final start = g.settings.startPoints;
  final sum = points.fold(0, (a, b) => a + b);
  if (start != mavelyStartPoints) {
    problem = '마블리는 시작점 $mavelyStartPoints 고정입니다(이 대국 시작점 $start).';
  } else if (names.any((n) => n.trim().isEmpty)) {
    problem = '이름이 빈 자리가 있습니다.';
  } else if (names.map((n) => n.trim()).toSet().length != 4) {
    problem = '이름이 겹칩니다.';
  } else if (sum + deposit != mavelyTotal) {
    problem = '점수 합 $sum + 공탁금 $deposit = ${sum + deposit} 이 $mavelyTotal 이 아닙니다. 기록을 정정한 뒤 올리세요.';
  }
  return MavelyEntry(names: names, points: points, stars: stars, deposit: deposit, problem: problem);
}

/// JS 에서 마블리 쪽 결과를 앱으로 보내는 채널 이름(`MavelyBridge.postMessage(JSON)`).
const mavelyBridgeName = 'MavelyBridge';

/// 마블리 입력 페이지에 [e] 를 채우는 JavaScript.
///
/// Nuxt 2 + Vuetify 페이지에서 `$data` 에 `rate_is_minus` 가 있는 컴포넌트(입력 폼)를 `window.$nuxt` 아래에서 재귀로 찾는다.
/// 폼이 아직 없으면 200ms 마다 다시 찾는다(처음부터 10초까지).
///
/// 1. 폼을 찾으면 바로 `$set` 으로 rates(절댓값) · rate_is_minus · stars 를 넣고 deposit · isNewInput(반환 전 점수 = 최종 점수 그대로) 를 넣는다.
///    이름은 여기서 넣지 않는다.
/// 2. 이름은 멤버 목록(optionsMembers — 문자열 또는 `{name}`)이 로드된 뒤 넣는다. 목록에 있으면 그 이름, 없으면 `''`.
///    목록에 없는 이름을 넣으면 Vuetify 자동완성 칸은 빈칸처럼 보이는데 데이터엔 남아 그대로 등록될 수 있다(실제 사이트에서 확인).
///    `''` 이면 사이트 검사가 등록을 막으므로 사용자가 직접 고르게 된다.
///    처음부터 10초 안에 목록이 안 오면 확인할 수 없으므로 이름을 모두 `''` 로 둔다.
///
/// 끝나면 [mavelyBridgeName] 로 `{ok:true, unknownNames, membersLoaded}`(못 채우면 `{ok:false, error}`)를 보낸다.
/// - unknownNames: 멤버 목록에 없어서 `''` 로 비운 이름(= 비운 이름 목록, blankedNames 를 따로 두지 않는다).
/// - membersLoaded false: 목록을 못 불러와 이름을 **모두** 비웠다. 이때 unknownNames 는 `[]`(없다고 확인한 이름이 없으므로).
/// 값은 [jsonEncode] 로 넣는다(따옴표·한글 안전).
String mavelyFillScript(MavelyEntry e) {
  final data = {
    'names': e.names,
    'rates': [for (final p in e.points) p.abs()],
    'minus': [for (final p in e.points) p < 0],
    'stars': e.stars,
    'deposit': e.deposit,
  };
  // JSON 은 JS 식으로도 맞다. 옛 엔진에서 줄 끝으로 읽히는 U+2028·U+2029 만 따로 막는다.
  final json = jsonEncode(data).replaceAll('\u2028', r'\u2028').replaceAll('\u2029', r'\u2029');
  return '''
(function () {
  var data = $json;
  var deadline = Date.now() + 10000;
  function post(o) {
    try { $mavelyBridgeName.postMessage(JSON.stringify(o)); } catch (err) {}
  }
  function findForm(vm, depth) {
    if (!vm || depth > 60) return null;
    if (vm.\$data && Object.prototype.hasOwnProperty.call(vm.\$data, 'rate_is_minus')) return vm;
    var ch = vm.\$children || [];
    for (var i = 0; i < ch.length; i++) {
      var f = findForm(ch[i], depth + 1);
      if (f) return f;
    }
    return null;
  }
  function memberNames(vm) {
    var known = {};
    var count = 0;
    var opts = vm.optionsMembers || [];
    for (var j = 0; j < opts.length; j++) {
      var o = opts[j];
      if (typeof o === 'string') { known[o] = true; count++; }
      else if (o && typeof o.name === 'string') { known[o.name] = true; count++; }
    }
    return { known: known, count: count };
  }
  // 멤버 목록이 로드된 뒤 이름을 넣는다. 목록에 없는 이름 · 목록을 못 불러온 때는 ''(사이트가 등록을 막게).
  function fillNames(vm) {
    var m = memberNames(vm);
    if (m.count === 0 && Date.now() < deadline) { setTimeout(function () { fillNames(vm); }, 200); return; }
    var loaded = m.count > 0;
    var unknown = []; // 목록에 없어 비운 이름(blankedNames 와 같은 뜻). 목록을 못 불러왔으면 [] · membersLoaded false.
    var wanted = data.names.slice();
    for (var k = 0; k < 4; k++) {
      if (loaded && m.known[wanted[k]]) continue;
      if (loaded) unknown.push(wanted[k]);
      data.names[k] = '';
    }
    try {
      for (var i = 0; i < 4; i++) {
        vm.\$set(vm.names, i, data.names[i]);
      }
    } catch (err) {
      post({ ok: false, error: String(err) });
      return;
    }
    post({ ok: true, unknownNames: unknown, membersLoaded: loaded });
  }
  function fill() {
    var root = window.\$nuxt ? (window.\$nuxt.\$root || window.\$nuxt) : null;
    var vm = findForm(root, 0);
    if (!vm) {
      if (Date.now() < deadline) { setTimeout(fill, 200); }
      else { post({ ok: false, error: 'form-not-found' }); }
      return;
    }
    try {
      // 점수 · 부호 · 별 · 공탁금은 바로. 이름은 fillNames 에서(멤버 확인 뒤).
      vm.isNewInput = true;
      for (var i = 0; i < 4; i++) {
        vm.\$set(vm.rates, i, data.rates[i]);
        vm.\$set(vm.rate_is_minus, i, data.minus[i]);
        vm.\$set(vm.stars, i, data.stars[i]);
      }
      vm.deposit = data.deposit;
    } catch (err) {
      post({ ok: false, error: String(err) });
      return;
    }
    fillNames(vm);
  }
  fill();
})();
''';
}
