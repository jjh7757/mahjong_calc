/// 엔진 "방총 위험 %"(`RiskTable.mixed34`) → 실제 방총률 쪽 값(%)으로 바꾸는 보정표 (2026-11-23).
///
/// 설계: `docs/risk_calibration_design_1123.md`(2절 보정 방법 · 6절 앱 쪽 · 9절 고친 기준).
/// 근거: metrics 표 16-13(1단계 — 개발 200판으로 보정표를 만듦) · 표 16-14(새 시험 599판 한 번 채점, R · C 둘 다 통과).
/// 엔진 순서는 맞지만 값이 커서(5% 위로 실측의 1.3 ~ 1.9배, 표 16-11) 화면에 보일 때만 이 표를 거친다.
/// 엔진 계산(`riskOf`) · 복기 리뷰 칸(`TurnReview.riskOfActual` · `riskByKind` · `riskTable`) · 복기 에이전트 사실표는 원래 값 그대로다.
///
/// 위협 종류(설계서 1절): 위협 자리(`riskSeats`)가 있고 그중 리치한 자리가 하나 이상이면 [RiskThreat.riichi](R),
/// 리치 없이 울기 위협만이면 [RiskThreat.callOnly](C). 실험(`experiments/paifu_review/pushfold/risk_calibrate.py`)은
/// hero 아닌 리치 자리(`riichiSeats`)가 비었는지로 갈랐다 — 앱의 `TurnReview.riichiSeats` 와 같은 정의다.
///
/// 계산: 점 사이 직선 보간, 첫 점 아래는 첫 점 값, 마지막 점 위는 마지막 점 값(`np.interp` 와 같음). 단조라 순서는
/// 바뀌지 않는다(평평한 구간에서는 동률이 생길 수 있음). 모두에게 안전패(`RiskTable.safeForAll34`)는 표 밖이다 —
/// 실험에서 방총 0 이었고, 화면은 숫자 대신 "안전" 으로 보인다(부르는 쪽이 처리).
///
/// 점 목록 생성: 아래 "생성" 구간은 손으로 옮기지 않고
///   `python -X utf8 tool/gen_risk_calibration.py`
/// 가 `experiments/paifu_review/results/riskcal/table.json` 의 `R.points` · `C.points`(실제로 쓴 표)를 실수 그대로 적어
/// 만든다. 대조는 `python -X utf8 tool/gen_risk_calibration.py --check`(JSON 은 experiments/ 라 커밋되지 않아 시험은
/// 이 상수만 본다).
library;

/// 위험 표시 차례의 위협 종류.
enum RiskThreat {
  /// 위협 자리 중 리치한 자리가 하나 이상(R).
  riichi,

  /// 리치 없이 울기 위협만(C).
  callOnly,
}

/// 위협 종류에 맞는 보정표 점 목록.
List<(double, double)> riskCalPoints(RiskThreat threat) =>
    threat == RiskThreat.riichi ? riskCalPointsRiichi : riskCalPointsCallOnly;

/// 엔진 값 [enginePct](%) → 보정값(%). NaN · 무한대는 그대로 돌려준다.
double calibrateRisk(double enginePct, RiskThreat threat) => interpRiskPoints(enginePct, riskCalPoints(threat));

/// [pts] 로 직선 보간(`np.interp` 와 같은 양 끝 고정). [pts] 는 x 가 엄격히 증가해야 한다.
double interpRiskPoints(double x, List<(double, double)> pts) {
  if (!x.isFinite) return x;
  if (x <= pts.first.$1) return pts.first.$2;
  if (x >= pts.last.$1) return pts.last.$2;
  var lo = 0, hi = pts.length - 1; // pts[lo].x < x < pts[hi].x
  while (hi - lo > 1) {
    final mid = (lo + hi) >> 1;
    final mx = pts[mid].$1;
    if (mx == x) return pts[mid].$2;
    if (mx < x) {
      lo = mid;
    } else {
      hi = mid;
    }
  }
  final (x0, y0) = pts[lo];
  final (x1, y1) = pts[hi];
  return y0 + (x - x0) * (y1 - y0) / (x1 - x0);
}

// ── 생성: 시작 (tool/gen_risk_calibration.py — 손으로 고치지 말 것) ──
// 원본: experiments/paifu_review/results/riskcal/table.json (made 2026-11-23, mxfit/stage1 개발 200판, C_uses_R = false)
/// 리치 위협(R) 보정표: (엔진 값 %, 실제 방총률 %) 13점. x 는 엄격히 증가, y 는 줄지 않음.
const List<(double, double)> riskCalPointsRiichi = [
  (0.009772670760293548, 0.19212295869356388),
  (0.38867726757744864, 0.2159827213822894),
  (0.7504979611757229, 0.8403361344537815),
  (1.9714105442256298, 1.36986301369863),
  (3.050512675356184, 2.4630541871921183),
  (3.763872641467698, 3.0683403068340307),
  (5.680230553752653, 3.392705682782019),
  (7.561527702111082, 5.111821086261981),
  (9.19813165047292, 6.847545219638243),
  (11.617925860086496, 8.590308370044053),
  (13.823507472697807, 8.734939759036145),
  (17.17598231154879, 11.055276381909549),
  (25.185268684628266, 17.253521126760564),
];

/// 울기 위협만(C) 보정표: (엔진 값 %, 실제 방총률 %) 17점. x 는 엄격히 증가, y 는 줄지 않음.
const List<(double, double)> riskCalPointsCallOnly = [
  (0.02390728458973832, 0.14820303816228234),
  (0.4144911493370717, 0.3201024327784891),
  (0.6816147874489099, 0.4918032786885246),
  (0.9238160207519353, 0.6442376521116678),
  (1.18263519165414, 1.2477718360071302),
  (1.3116641292888498, 1.6129032258064515),
  (1.5829507658332147, 1.7699115044247788),
  (1.8390943508103694, 2.0833333333333335),
  (2.411854017585607, 2.55125284738041),
  (3.7356890036555206, 3.4738304770727186),
  (4.860110181965191, 4.40251572327044),
  (5.222260520220639, 5.042016806722689),
  (5.616448012618023, 5.341246290801187),
  (7.337028575892159, 5.689789555728761),
  (10.032439751115847, 6.451612903225806),
  (12.160595307030936, 7.647058823529412),
  (18.969695537629487, 12.76595744680851),
];
// ── 생성: 끝 ──
