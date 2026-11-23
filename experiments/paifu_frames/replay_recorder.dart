// ignore_for_file: avoid_print
// 앱의 버림 기록기(`lib/paifu/discard_recorder.dart`)에 저장된 장면을 차례로 넣어 `score.py` 가 읽는 꼴(slot json)로 낸다(2026-11-17).
//   dart run experiments/paifu_frames/replay_recorder.dart det     <results/R4/det.json>          <선 쪽> <out.json>
//   dart run experiments/paifu_frames/replay_recorder.dart overlay <results/R4/overlay_dump.json> <선 쪽> <out.json> [paifu.json bottomSeat] [--sticks y0,x0,y1,x1]
// det     = 오프라인 시험이 저장한 검출(가운데 크롭 검출 + read_small, 기기 중심·반 크기 포함) → 파이썬 `slot_round` v2 와 같은 답이 나와야 한다(옮김 확인).
// overlay = 앱 겹쳐 보기 출력(`overlay_dump.py`) → 앱과 같은 길: 앞면 상자 전부(역할 안 봄, `--river-role` 이면 river 만), 중심·반 크기는 저장 격자의 리치봉 구역.
// overlay-small = 같은 상자·역할에 종류만 키워 읽은 값(t2). 추적 프레임(1020)은 겹쳐 보기 분류가 거의 다 白 으로 읽어서(앱은 4080 을 읽는다).
// 채점: python score.py <out.json> truth.json <판>
// 헛 칸 처리(docs/recorder_ghost_slot_plan_1121.md): [--min-new-conf x](후보 B, 미채택) [--drop-unconfirmed | --no-drop-unconfirmed]
//   — DiscardRecorderConfig.minNewSlotConf · dropUnconfirmed. 옵션이 없으면 기록기 기본값(C 켬). --no-drop-unconfirmed = 옛 동작.
// [--min-side N] overlay 모드에서 긴 변이 N 미만인 프레임을 건너뜀(기본 1600, 앱과 같음). 헤드 녹화 1496 프레임은 0(11-23, headrec_run.py).
import 'dart:convert';
import 'dart:io';

import 'package:mahjong_calc/paifu/discard_recorder.dart';
import 'package:mahjong_calc/table/table_layout.dart';

String hms(DateTime t) => t.toIso8601String().substring(11, 19);

double median(List<double> v) {
  final s = [...v]..sort();
  return s.length.isOdd ? s[s.length ~/ 2] : (s[s.length ~/ 2 - 1] + s[s.length ~/ 2]) / 2;
}

void main(List<String> args) {
  final mode = args[0];
  final j = jsonDecode(File(args[1]).readAsStringSync());
  final dealer = Side.values.asNameMap()[args[2]];
  // 헛 칸 처리(11-21, docs/recorder_ghost_slot_plan_1121.md): --min-new-conf x(후보 B, 미채택) · --drop-unconfirmed(후보 C 명시적 켬)
  // · --no-drop-unconfirmed(옛 동작). 없으면 기록기 기본값(C 켬, B 끔).
  const base = DiscardRecorderConfig();
  final mi = args.indexOf('--min-new-conf');
  final on = args.contains('--drop-unconfirmed'), off = args.contains('--no-drop-unconfirmed');
  if (on && off) throw ArgumentError('--drop-unconfirmed 와 --no-drop-unconfirmed 는 같이 못 씀');
  final rec = DiscardRecorder(
    dealer: dealer,
    config: DiscardRecorderConfig(
      minNewSlotConf: mi < 0 ? base.minNewSlotConf : double.parse(args[mi + 1]),
      dropUnconfirmed: on ? true : (off ? false : base.dropUnconfirmed),
    ),
  );
  if (mode == 'det') {
    final det = (j as List).cast<Map<String, dynamic>>();
    final hd = median([for (final d in det) ((d['dev'] as List)[2] as num).toDouble()]);
    for (final d in det) {
      final dev = (d['dev'] as List).cast<num>();
      rec.add(
        DateTime.parse(d['at'] as String),
        [
          for (final t in (d['tiles'] as List).cast<Map<String, dynamic>>())
            () {
              final b = (t['box'] as List).cast<num>();
              return RiverSighting(
                dx: b[0] + b[2] / 2 - dev[0],
                dy: b[1] + b[3] / 2 - dev[1],
                w: b[2].toDouble(),
                h: b[3].toDouble(),
                tile: t['t'] as String,
                conf: (t['c'] as num).toDouble(),
              );
            }(),
        ],
        hd: hd,
      );
    }
  } else {
    final grid = (j['grid'] as Map).cast<String, dynamic>();
    final frames = ((j['frames']) as List).cast<Map<String, dynamic>>();
    // --sticks y0,x0,y1,x1 : 저장 격자 대신 쓸 리치봉 구역(펠트로 고친 격자 — 11-14 2반장은 저장 격자가 카메라 이동 전 것).
    final si = args.indexOf('--sticks');
    final sticksArg = si < 0 ? null : [for (final v in args[si + 1].split(',')) num.parse(v)];
    // --river-role : 역할 모델이 river 라고 한 상자만(처음 방식). 기본은 역할을 안 보고 위치(바람개비 띠)만 본다 —
    // 판 초반 강의 첫 패들을 역할 모델이 wall 로 오락가락 읽어 칸이 깜박였다(11-14 r11 아래 자리).
    final anyRole = !args.contains('--river-role');
    final small = mode == 'overlay-small'; // 종류는 키워 읽은 값(t2)으로
    // --min-side N : 이보다 긴 변이 짧은 프레임은 건너뜀(기본 1600 = 앱과 같은 지금 동작). 헤드 녹화 1496 프레임을 그대로 쓸 땐 0(11-23).
    final ms = args.indexOf('--min-side');
    final minSide = ms < 0 ? 1600.0 : double.parse(args[ms + 1]);
    var skipped = 0;
    for (final f in frames) {
      final w = (f['w'] as num).toDouble(), h = (f['h'] as num).toDouble();
      // 앱은 원래 크기 프레임에서만 패 인식을 돌린다(긴 변 1600 미만이면 안 함). 줄인 프레임이 섞인 묶음(11-14)은 그 프레임을 건너뛴다.
      // overlay-small(1020 프레임을 키워 읽은 종류)은 그대로 다 쓴다.
      if (!small && (w > h ? w : h) < minSide) {
        skipped++;
        continue;
      }
      // 앱 `GridZones.sticksZone` 과 같은 값: 저장된 리치봉 구역(ymin, xmin, ymax, xmax 1000 분율), 없으면 가운데 칸 0.7.
      final List<num> s;
      if (sticksArg != null) {
        s = sticksArg;
      } else if (grid['sticks'] != null) {
        s = (grid['sticks'] as List).cast<num>();
      } else {
        final x1 = grid['x1'] as num, x2 = grid['x2'] as num, y1 = grid['y1'] as num, y2 = grid['y2'] as num;
        final cx = (x1 + x2) / 2, cy = (y1 + y2) / 2, hw = (x2 - x1) * 0.35, hh = (y2 - y1) * 0.35;
        s = [cy - hh, cx - hw, cy + hh, cx + hw];
      }
      final g = sightingsOf(
        [
          for (final t in (f['tiles'] as List).cast<Map<String, dynamic>>())
            if (anyRole || t['r'] == 'river')
              (
                x: ((t['b'] as List)[0] as num).toDouble(),
                y: ((t['b'] as List)[1] as num).toDouble(),
                w: ((t['b'] as List)[2] as num).toDouble(),
                h: ((t['b'] as List)[3] as num).toDouble(),
                tile: (small ? t['t2'] : t['t']) as String,
                conf: ((small ? t['tc2'] : t['tc']) as num).toDouble(),
              ),
        ],
        zoneXmin: s[1] / 1000,
        zoneXmax: s[3] / 1000,
        zoneYmin: s[0] / 1000,
        zoneYmax: s[2] / 1000,
        aspect: w / h,
      );
      // 앱과 같이 울기 상자 수(자리별)를 같이 넘긴다. `--no-melds` 면 안 넘긴다(예전 동작과 견주기).
      final melds = {for (final s in Side.values) s: <String>[]};
      for (final t in (f['tiles'] as List).cast<Map<String, dynamic>>()) {
        final s = Side.values.asNameMap()[t['s']];
        if (t['r'] == 'meld' && s != null) melds[s]!.add((small ? t['t2'] : t['t']) as String);
      }
      rec.add(DateTime.parse(f['at'] as String), g.sightings, hd: g.hd, meldTiles: args.contains('--no-melds') ? null : melds);
    }
    if (skipped > 0) print('줄인 프레임 $skipped장 건너뜀');
  }
  if (rec.resets > 0) print('빈 탁자로 새로 시작 ${rec.resets}번(마지막 ${hms(rec.resetAt!)})');
  final rivers = rec.rivers();
  final out = {
    for (final s in Side.values)
      s.name: {
        'slots': [
          for (final d in rivers[s]!)
            {
              'i': d.index + 1,
              'tile': d.tile,
              'share': double.parse(d.share.toStringAsFixed(2)),
              'n': d.seen,
              'first_at': hms(d.firstAt),
              'taken_at': d.takenAt == null ? null : hms(d.takenAt!),
              'sideways': d.sideways,
              if (d.calledBy != null) 'called_by': d.calledBy!.name,
              if (d.meldKind != null) 'meld': {'kind': d.meldKind, 'tiles': d.meldTiles},
            },
        ],
      },
  };
  File(args[3]).writeAsStringSync(const JsonEncoder.withIndent(' ').convert(out));
  // 한 줄로 엮은 순서는 따로(score.py 는 자리 키만 읽는다).
  File(args[3].replaceAll('.json', '_timeline.json')).writeAsStringSync(const JsonEncoder.withIndent(' ')
      .convert([for (final d in rec.timeline()) '${d.side.name} ${d.tile}${d.taken ? '*' : ''}${d.sideways ? '=' : ''}']));
  for (final s in Side.values) {
    print('${s.name.padRight(6)} ${[for (final d in rivers[s]!) '${d.tile}${d.taken ? '*' : ''}${d.sideways ? '=' : ''}'].join(' ')}');
  }
  if (args.length > 5 && !args[4].startsWith('--')) {
    final bottomSeat = int.parse(args[5]);
    final p = rec.toPaifu(
      id: args[1],
      bottomSeat: bottomSeat,
      dealerSeat: dealer == null ? 0 : (bottomSeat + dealer.index) % 4,
      hero: bottomSeat,
      note: '버림만 기록(재생 시험)',
    );
    File(args[4]).writeAsStringSync(const JsonEncoder.withIndent(' ').convert(p.toJson()));
    print('패보 ${args[4]}: 사건 ${p.events.length}, 검사 ${p.check()}');
  }
}
