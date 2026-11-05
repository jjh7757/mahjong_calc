/// 프레임 투표(개선 계획 6단계, 2026-11-06): 화료 사진 판독 뒤 자동 반영 **직전에만** 카메라 헤드의 다른 프레임 1장을
/// `/v2/localroles` 로 한 번 더 읽어, 화료자 손패·떼어 둔 패·울기가 같을 때만 자동 반영한다. 순수 Dart.
///
/// 왜: 자체 모델은 같은 입력이면 같은 답이라 같은 사진을 여러 번 읽는 투표는 무의미하다. 다른 프레임은 JPEG·노출·초점이
/// 조금씩 달라 진짜 독립 표본이다(오프라인 시연 `experiments/speed/frame_vote.py`, 정의 `FRAME_VOTE.md`, metrics 표 1-94).
/// 한계: 네 장 모두 같은 오답(테스트 F1400 적5만 → 5만, 개발 143104 화료패 누락)처럼 **체계적 오류는 못 잡는다**.
///
/// 규칙(Python `frame_vote.py` 의 `read_key`·`vote` 와 같아야 한다, 명세 `test/fixtures/frame_vote.json`):
/// - 같음 = 손패 다중집합(적5 는 `0m` 처럼 따로)·떼어 둔 패·울기 다중집합(울기 안 정렬 + 안깡 표시)이 모두 같음.
/// - 두 번째 판독이 없으면(정지 아님·헤드·서버 실패) [FrameVoteResult.none] — 투표가 없던 때처럼 지금 규칙대로 반영한다.
/// - 정지 판정([judgeStill]): 화료 사진과 두 번째 프레임 사이에 장면 전체 변화([SceneShiftGate.judge])가 없고, 화료자 모서리 칸이
///   그대로이고, 두 번째 프레임에서도 화료자 손패가 앞면(눕힘)일 때만 두 번째 판독을 쓴다.
library;

import 'observation.dart';
import 'river_change.dart';
import 'scene_shift.dart';
import 'table_layout.dart';

/// 투표에 쓰는 판독 하나(화료자 자리 `/v2/localroles` 답).
class VoteMeld {
  final List<String> tiles;
  final bool closed;
  const VoteMeld(this.tiles, {this.closed = false});

  String get key => '${(List.of(tiles)..sort()).join(' ')}${closed ? '*' : ''}';
  Map<String, dynamic> toJson() => {'tiles': tiles, 'closed': closed};
}

class VoteRead {
  final List<String> tiles;
  final String? separate;
  final List<VoteMeld> melds;
  const VoteRead({required this.tiles, this.separate, this.melds = const []});

  /// 명세(fixture)·촬영 기록 모양: `{"tiles": [...], "separate": "3m"|null, "melds": [{"tiles": [...], "closed": bool}]}`.
  static VoteRead fromJson(Map<String, dynamic> j) => VoteRead(
        tiles: [for (final t in (j['tiles'] as List<dynamic>?) ?? const []) '$t'],
        separate: j['separate'] as String?,
        melds: [
          for (final m in (j['melds'] as List<dynamic>?) ?? const [])
            if (m is Map<String, dynamic>)
              VoteMeld([for (final t in (m['tiles'] as List<dynamic>?) ?? const []) '$t'], closed: m['closed'] == true),
        ],
      );

  /// 서버 `/v2/localroles` 응답(= `/v2/seat` 모양)에서.
  static VoteRead fromSeat(SeatV2 s) => VoteRead(
        tiles: [for (final t in s.tiles) t.code],
        separate: s.separate?.code,
        melds: [for (final m in s.melds) VoteMeld([for (final t in m.tiles) t.code], closed: m.faceDown.isNotEmpty)],
      );

  static VoteRead fromSeatJson(Map<String, dynamic> j) => fromSeat(parseSeatV2(j));

  /// 비교 열쇠: 정렬한 손패 | 떼어 둔 패 | 정렬한 울기 열쇠들.
  String get key => [
        (List.of(tiles)..sort()).join(' '),
        separate ?? '-',
        ([for (final m in melds) m.key]..sort()).join(' / '),
      ].join(' | ');

  Map<String, dynamic> toJson() => {'tiles': tiles, 'separate': separate, 'melds': [for (final m in melds) m.toJson()]};
}

enum FrameVoteResult { agree, mismatch, none }

/// 두 판독의 투표. [second] 가 없으면 none.
FrameVoteResult frameVote(VoteRead first, VoteRead? second) {
  if (second == null) return FrameVoteResult.none;
  return first.key == second.key ? FrameVoteResult.agree : FrameVoteResult.mismatch;
}

/// 자동 반영을 막는 경고 문구(불일치일 때만).
const frameMismatchWarning = '프레임 불일치';

/// 정지 판정 결과. [reason] 은 정지가 아닐 때 이유(기록용).
class FrameStill {
  final bool still;
  final String? reason;
  final int changedZones;
  const FrameStill(this.still, {this.reason, this.changedZones = 0});
  Map<String, dynamic> toJson() => {'still': still, 'reason': ?reason, 'changed_zones': changedZones};
}

/// 화료 사진([before])과 두 번째 프레임([after])이 "손패 눕힘 + 정지" 로 이어지는지.
FrameStill judgeStill({
  required TableFrameStats before,
  required TableFrameStats after,
  required Side winner,
  required bool winnerFaceUp,
  SceneShiftConfig config = const SceneShiftConfig(),
}) {
  final gate = SceneShiftGate(config: config);
  final shifted = gate.judge(before, after);
  final changed = gate.lastChanged;
  if (shifted) return FrameStill(false, reason: '장면 전체 변화(${gate.summary})', changedZones: changed);
  final b = before.corners[winner], a = after.corners[winner];
  if (b != null && a != null && a.diff(b) > config.cornerMove) {
    return FrameStill(false, reason: '화료자 모서리 바뀜', changedZones: changed);
  }
  if (!winnerFaceUp) return FrameStill(false, reason: '화료자 손패가 앞면이 아님', changedZones: changed);
  return FrameStill(true, changedZones: changed);
}

/// 촬영 기록 `frame_vote.json` 한 건.
class FrameVoteRecord {
  final FrameVoteResult result;
  final VoteRead first;
  final VoteRead? second;
  final FrameStill? still;

  /// 두 번째 프레임 받기·정지 판정·`/v2/localroles` 왕복·투표 전체(ms)와 그중 localroles 호출(ms).
  final int totalMs;
  final int? secondCallMs;

  /// 투표를 못 한 이유(none 일 때).
  final String? reason;
  const FrameVoteRecord({
    required this.result,
    required this.first,
    this.second,
    this.still,
    required this.totalMs,
    this.secondCallMs,
    this.reason,
  });

  /// 자동 반영을 막는 이유. 불일치면 [frameMismatchWarning], 아니면 null(일치·투표 못 함은 지금 규칙대로).
  String? get blocker => result == FrameVoteResult.mismatch ? frameMismatchWarning : null;

  Map<String, dynamic> toJson() => {
        'result': result.name,
        'first': first.toJson(),
        'second': second?.toJson(),
        'still': still?.toJson(),
        'total_ms': totalMs,
        'second_ms': secondCallMs,
        'reason': ?reason,
      };
}
