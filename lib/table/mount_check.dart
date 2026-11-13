/// 거치 점검: 카메라(헤드)를 놓은 자리가 판독에 맞는지 사진 한 장으로 본다. 순수 Dart, API 호출 없음.
///
/// 보는 것은 셋 — 펠트 네 변이 사진 안에 다 들어왔나, 기울기, 패 크기(카메라 높이). 문턱은 테스트 세트 원본과 그 변형
/// (정사각형 자르기·회전·축소)에 이 점검을 돌려 판독 결과와 맞대 본 숫자에서만 가져왔다(metrics 표 13-1):
///  - 펠트가 사진 변에 닿은(잘린) 사진: 운영 모델 장면 틀림 3/44, 안 닿은 사진 0/76.
///  - 기울기 6° 미만 2/112, 6~15° 12/82, 15° 이상 35/39.
///  - 펠트 한 변 2172px 이상 0/80, 1629~1782px(0.6배 축소) 3/40.
/// 흰 테두리만 사진 밖인 것(지금 매장 거치의 위·아래)과 원근(갤러리 사진 변 길이 비 1.5)은 틀림이 없어 판정에 넣지 않고 알리기만 한다.
///
/// 펠트를 못 찾으면(다른 펠트 색·탁자 없음) 판정하지 않는다([MountLevel.unknown]) — 거치가 나쁘다는 증거가 아니다.
library;

import 'dart:math' as math;
import 'dart:typed_data';

import 'package:image/image.dart' as img;

import 'felt_grid.dart';
import 'fixed_layout.dart' show decodeSmall;
import 'rectify.dart' show FeltQuad, tableClipMargin, tableTilt;

enum MountLevel { ok, caution, bad, unknown }

/// 사진 변: 위·오른쪽·아래·왼쪽([FeltCoverage.touch]·[MountCheck.room] 의 순서).
const List<String> mountSideNames = ['위쪽', '오른쪽', '아래쪽', '왼쪽'];

/// 사진 변에 펠트가 이만큼(변 길이 비율) 닿으면 탁자가 그쪽으로 잘린 것. 틀린 사진 중 가장 작은 값이 0.057 이었다.
const double mountTouchMin = 0.05;

/// 탁자 바깥 끝(펠트 + 흰 테두리 [tableClipMargin])에서 사진 변까지 여유가 이보다 작으면 그쪽 테두리가 사진 밖(사진 비율).
/// 판정은 안 바꾸고 알리기만 한다 — 그쪽 테두리 위에 둔 울기는 잘린다.
const double mountRoomMin = -0.01;

/// 기울기(도): 미만이면 괜찮음 / 이상이면 나쁨, 그 사이는 주의.
const double mountTiltOk = 6, mountTiltBad = 15;

/// 촬영 사진에서 펠트 한 변(px): 이상이면 괜찮음(0.8배 축소까지 틀림 0) / 미만이면 나쁨(틀림이 나온 0.6배보다도 작음 — 잰 적 없는 범위).
/// 패 짧은 변은 대략 이 값의 [mountTilePerFelt] 배.
const double mountFeltPxOk = 2150, mountFeltPxBad = 1600;

/// 패 짧은 변 / 펠트 한 변. 기기 폭이 펠트의 [feltDeviceW] 이고 기기 반폭이 패 3.0~3.3장(구역표 참고값)이라 0.197 / 6.3.
/// 화면에 "패 약 N px" 로 보여 줄 때만 쓴다(판정은 펠트 px 로).
const double mountTilePerFelt = feltDeviceW / 6.3;

class MountItem {
  /// frame(탁자 전체) · tilt(기울기) · size(패 크기).
  final String key;
  final MountLevel level;
  final String title;

  /// 잰 값 한 줄.
  final String value;

  /// 고칠 방법(괜찮으면 빈 문자열).
  final String advice;

  /// 판정과 상관없이 알려 둘 것(없으면 빈 문자열).
  final String note;

  const MountItem(this.key, this.level, this.title, this.value, {this.advice = '', this.note = ''});
}

class MountCheck {
  /// 믿을 만한 펠트 네 모서리(못 찾았으면 null — 어느 쪽이 잘렸는지는 [touch] 로만 안다).
  final FeltQuad? quad;

  /// 사진 위·오른쪽·아래·왼쪽 변에 펠트가 닿은 비율. 펠트 색을 못 잡았으면 null.
  final List<double>? touch;

  /// 탁자 바깥 끝(펠트 + 테두리)에서 사진 위·오른쪽·아래·왼쪽 변까지 여유(사진 비율, 음수 = 사진 밖).
  final List<double>? room;

  /// 기울기(도, 시계 방향 +).
  final double? tilt;

  /// 마주 보는 변 길이 비(1 이상). 판정에는 안 쓴다(기록용).
  final double? perspective;

  /// 촬영 사진에서 펠트 한 변 평균(px). 촬영 크기를 모르면 null.
  final double? feltPx;

  final List<MountItem> items;

  const MountCheck({this.quad, this.touch, this.room, this.tilt, this.perspective, this.feltPx, required this.items});

  /// 가장 나쁜 항목. 판정한 항목이 없으면 unknown.
  MountLevel get level {
    var worst = MountLevel.unknown;
    for (final i in items) {
      if (i.level == MountLevel.unknown) continue;
      if (worst == MountLevel.unknown || i.level.index > worst.index) worst = i.level;
    }
    return worst;
  }

  /// 나쁨·주의 항목의 고칠 방법(나쁨 먼저).
  List<String> get advice => [
        for (final lv in [MountLevel.bad, MountLevel.caution])
          for (final i in items)
            if (i.level == lv && i.advice.isNotEmpty) i.advice,
      ];

  Map<String, Object?> toJson() => {
        'level': level.name,
        'felt': quad?.toJson(),
        'touch': touch == null ? null : [for (final t in touch!) double.parse(t.toStringAsFixed(3))],
        'room': room == null ? null : [for (final r in room!) double.parse(r.toStringAsFixed(3))],
        'tilt': tilt == null ? null : double.parse(tilt!.toStringAsFixed(2)),
        'perspective': perspective == null ? null : double.parse(perspective!.toStringAsFixed(3)),
        'felt_px': feltPx?.round(),
        'items': {for (final i in items) i.key: i.level.name},
      };
}

String _sides(Iterable<int> idx) => [for (final i in idx) mountSideNames[i]].join('·');

/// 사진 한 장의 거치 점검. [captureLongSide] = 화료 촬영 사진의 긴 변(px, 모르면 패 크기는 판정하지 않음).
MountCheck checkMount(img.Image src, {int? captureLongSide}) {
  final probe = probeFelt(src);
  final cover = probe.coverage;
  final reading = probe.reading;
  final quad = reading != null && reading.ok ? reading.quad : null;
  final touch = cover?.touch;
  final cut = touch == null
      ? const <int>[]
      : [
          for (var i = 0; i < 4; i++)
            if (touch[i] >= mountTouchMin) i,
        ];

  if (cover == null || (quad == null && cut.isEmpty)) {
    return MountCheck(touch: touch, items: const [
      MountItem('frame', MountLevel.unknown, '탁자 전체', '펠트를 못 찾음',
          note: '탁자가 화면 가운데에 오게 놓였는지 눈으로 확인하세요(펠트 색이 다른 탁자면 점검할 수 없습니다)'),
    ]);
  }

  final items = <MountItem>[];
  List<double>? room;
  double? tilt, feltPx;
  if (quad != null) {
    final c = quad.grown(1 + 2 * tableClipMargin).corners;
    room = [
      c.map((p) => p.y).reduce(math.min),
      1 - c.map((p) => p.x).reduce(math.max),
      1 - c.map((p) => p.y).reduce(math.max),
      c.map((p) => p.x).reduce(math.min),
    ];
  }

  // 1. 탁자 전체: 펠트가 사진 변에 닿았으면 잘린 것. 흰 테두리만 밖이면 알리기만.
  if (cut.isNotEmpty) {
    // 마주 보는 두 쪽이 다 잘렸으면 옮겨서는 안 되고 높여야 한다.
    final both = (cut.contains(0) && cut.contains(2)) || (cut.contains(1) && cut.contains(3));
    items.add(MountItem('frame', MountLevel.bad, '탁자 전체', '사진의 ${_sides(cut)} 펠트가 잘림',
        advice: both ? '카메라를 더 높여 펠트 네 변이 다 보이게 하세요' : '카메라를 사진의 ${_sides(cut)}으로 옮기거나 더 높여 펠트 네 변이 다 보이게 하세요'));
  } else {
    final edge = [
      for (var i = 0; i < 4; i++)
        if (room![i] < mountRoomMin) i,
    ];
    items.add(MountItem('frame', MountLevel.ok, '탁자 전체', '펠트 네 변 다 보임',
        note: edge.isEmpty ? '' : '흰 테두리는 사진의 ${_sides(edge)}이 밖입니다 — 그쪽 테두리 위에 둔 울기는 잘립니다'));
  }

  if (quad != null) {
    // 2. 기울기. 사진에서 탁자가 시계 방향으로 돌아 보이면(+) 카메라를 위에서 볼 때 시계 방향으로 돌려야 펴진다.
    final t = tilt = tableTilt(quad, aspect: src.width / src.height);
    final tv = '${t >= 0 ? '+' : ''}${t.toStringAsFixed(1)}°';
    items.add(t.abs() < mountTiltOk
        ? MountItem('tilt', MountLevel.ok, '기울기', tv)
        : MountItem('tilt', t.abs() >= mountTiltBad ? MountLevel.bad : MountLevel.caution, '기울기', tv,
            advice: '카메라를 위에서 볼 때 ${t > 0 ? '시계 방향' : '시계 반대 방향'}으로 ${t.abs().round()}° 돌려 탁자 변이 화면과 나란하게 하세요'));

    // 3. 패 크기(촬영 사진 기준).
    if (captureLongSide != null && captureLongSide > 0) {
      final long = math.max(src.width, src.height);
      final sx = captureLongSide * src.width / long, sy = captureLongSide * src.height / long;
      final cs = quad.corners;
      var sum = 0.0;
      for (var i = 0; i < 4; i++) {
        final a = cs[i], b = cs[(i + 1) % 4];
        final dx = (a.x - b.x) * sx, dy = (a.y - b.y) * sy;
        sum += math.sqrt(dx * dx + dy * dy);
      }
      final f = feltPx = sum / 4;
      final sv = '펠트 한 변 ${f.round()}px(패 약 ${(f * mountTilePerFelt).round()}px)';
      items.add(f >= mountFeltPxOk
          ? MountItem('size', MountLevel.ok, '패 크기', sv)
          : MountItem('size', f < mountFeltPxBad ? MountLevel.bad : MountLevel.caution, '패 크기', sv,
              advice: '카메라를 낮추거나 줌을 올려 탁자가 화면에 더 크게 차게 하세요'));
    }
  }
  return MountCheck(quad: quad, touch: touch, room: room, tilt: tilt, perspective: reading?.sideRatio, feltPx: feltPx, items: items);
}

/// JPEG 한 장 → 거치 점검. `compute()` 에 넘길 수 있다. 인자 = (JPEG, 촬영 사진 긴 변).
/// 긴 변이 null 이면 이 사진 자체가 촬영 크기일 때만(긴 변 2000 이상) 그 값으로 패 크기를 보고, 작은 미리보기면 패 크기는 건너뛴다.
MountCheck mountCheckOfJpeg((Uint8List, int?) args) {
  final im = decodeSmall(args.$1);
  final own = math.max(im.width, im.height);
  return checkMount(im, captureLongSide: args.$2 ?? (own >= 2000 ? own : null));
}
