/// 판 상태 추적의 배경 프레임(3초마다 받는 헤드 미리보기)을 변화 주변만 골라 모아 두고 zip 하나로 묶는다.
///
/// 추적이 변화를 놓쳤거나 잘못 잡았을 때 뒤에 원인을 보려고(2026-10-29, 사용자). 모든 프레임을 남기면 한 시간에
/// 1,200장(S25 헤드 기본 미리보기 720×540 약 16~30KB)이라 파일 수가 문제라서:
/// - 쓰는 쪽이 이 프레임에 무슨 일이 있었는지([add] 의 `why`, 예: 모서리 움직임·리치봉 변화·장면 이동)를 주면
///   그 프레임과 앞 [before] 장, 뒤 [after] 장을 남긴다.
/// - 아무 일도 없어도 [every] 장마다 한 장은 남긴다(시간 흐름을 보려고).
/// - 판이 바뀌거나 [maxFrames] 장이 차면 쓰는 쪽이 [take] 로 꺼내 [encodeFramesZip] 으로 묶어 저장한다.
/// - [keepAll] 이면 받은 프레임을 전부 남긴다(매장 실험 때 녹화 대신, 2026-11-05 사용자: 휴대폰이 헤드 한 대뿐).
///   헤드가 하는 일은 그대로고 태블릿 저장 공간만 더 쓴다.
library;

import 'dart:collection';
import 'dart:convert';
import 'dart:typed_data';

import 'package:archive/archive.dart';

import 'river_tracker.dart';
import 'tracker.dart';

class RecordedFrame {
  /// 판 안에서 받은 순서(1부터, 남기지 않은 프레임도 센다).
  final int index;
  final DateTime at;
  final Uint8List jpeg;

  /// 남긴 까닭. 변화 프레임이면 그 내용, 아니면 'before'·'after'·'sample'.
  final List<String> why;
  const RecordedFrame(this.index, this.at, this.jpeg, this.why);

  String get fileName {
    String two(int n) => n.toString().padLeft(2, '0');
    return 'f${index.toString().padLeft(4, '0')}_${two(at.hour)}${two(at.minute)}${two(at.second)}.jpg';
  }

  Map<String, dynamic> toJson() => {'index': index, 'at': at.toIso8601String(), 'file': fileName, 'why': why};
}

/// 이 프레임에 추적이 본 변화(비어 있으면 아무 일 없음). [meldEventsFrom]·[riverEventsFrom] 은 앞 프레임까지 본
/// 기록 수로, 그 뒤에 새로 생긴 기록을 적는다. 버림패(`discard`)는 판 내내 3초마다 생겨 그것만으로는 남기지 않는다.
List<String> frameChanges({
  required MeldTracker melds,
  required RiverTracker river,
  required int meldEventsFrom,
  required int riverEventsFrom,
  bool sceneShift = false,
}) {
  // 추적기를 새로 만들었으면(격자 변경) 기록이 처음부터라 앞 수가 더 크다 → 처음부터 본다.
  final meldFrom = meldEventsFrom > melds.events.length ? 0 : meldEventsFrom;
  final riverFrom = riverEventsFrom > river.events.length ? 0 : riverEventsFrom;
  const busy = {TrackStatus.moving, TrackStatus.changed, TrackStatus.reading};
  const sticksBusy = {StickStatus.moving, StickStatus.changed, StickStatus.reading};
  return [
    if (sceneShift) 'scene_shift',
    for (final e in melds.seats.entries)
      if (busy.contains(e.value.status)) 'corner_${e.key.name}_${e.value.status.name}',
    if (sticksBusy.contains(river.sticks.status)) 'sticks_${river.sticks.status.name}',
    for (final e in melds.events.skip(meldFrom)) 'corner_${e.side.name}_${e.kind}',
    for (final e in river.events.skip(riverFrom))
      if (e.kind != 'discard') 'river_${e.side.name}_${e.kind}',
  ];
}

class FrameRecorder {
  final int before;
  final int after;
  final int every;
  final int maxFrames;

  FrameRecorder({this.before = 2, this.after = 2, this.every = 10, this.maxFrames = 150, this.keepAll = false});

  /// 받은 프레임을 전부 남긴다(변화 프레임은 까닭을 그대로, 나머지는 'all').
  bool keepAll;

  final ListQueue<RecordedFrame> _ring = ListQueue();
  final List<RecordedFrame> _kept = [];
  int _count = 0;
  int _afterLeft = 0;

  /// 받은 프레임 수와 남긴 프레임 수(기록·표시용).
  int get seen => _count;
  int get keptCount => _kept.length;

  /// [maxFrames] 장이 찼다(쓰는 쪽이 [take] 해서 저장할 때).
  bool get isFull => _kept.length >= maxFrames;

  /// 프레임 한 장. [why] 가 비어 있지 않으면 변화 프레임. 남겼으면 true.
  bool add(Uint8List jpeg, DateTime at, {List<String> why = const []}) {
    _count++;
    if (why.isNotEmpty) {
      _kept.addAll(_ring);
      _ring.clear();
      _kept.add(RecordedFrame(_count, at, jpeg, why));
      _afterLeft = after;
      return true;
    }
    if (keepAll) {
      _afterLeft = 0;
      _kept.add(RecordedFrame(_count, at, jpeg, const ['all']));
      return true;
    }
    if (_afterLeft > 0) {
      _afterLeft--;
      _kept.add(RecordedFrame(_count, at, jpeg, const ['after']));
      return true;
    }
    if (every > 0 && _count % every == 0) {
      _ring.clear(); // 바로 앞 프레임은 다음 변화의 'before' 로 다시 넣지 않는다(이 장과 겹친다).
      _kept.add(RecordedFrame(_count, at, jpeg, const ['sample']));
      return true;
    }
    _ring.add(RecordedFrame(_count, at, jpeg, const ['before']));
    while (_ring.length > before) {
      _ring.removeFirst();
    }
    return false;
  }

  /// 추적을 거치지 않은 프레임(격자 확인 전·격자 편집 중·추적 꺼짐 등). [keepAll] 일 때만 'untracked' 로 남긴다.
  bool addUntracked(Uint8List jpeg, DateTime at) {
    if (!keepAll) return false;
    _count++;
    _kept.add(RecordedFrame(_count, at, jpeg, const ['untracked']));
    return true;
  }

  /// 남긴 프레임을 꺼내고 비운다(앞 프레임 버퍼·뒤 남은 수는 그대로 — 저장 뒤에도 같은 판이 이어질 수 있다).
  List<RecordedFrame> take() {
    final out = List.of(_kept);
    _kept.clear();
    return out;
  }

  /// 새 판: 모두 비우고 번호도 1부터.
  void reset() {
    _ring.clear();
    _kept.clear();
    _count = 0;
    _afterLeft = 0;
  }
}

/// 프레임들과 `frames.json`(번호·시각·남긴 까닭 + [meta])을 zip 하나로. JPEG 는 더 줄지 않아 압축하지 않는다.
/// compute 로 부를 수 있게 인자를 하나로 받는다.
Uint8List encodeFramesZip((List<RecordedFrame>, Map<String, dynamic>) args) {
  final (frames, meta) = args;
  final archive = Archive();
  for (final f in frames) {
    archive.addFile(ArchiveFile.noCompress(f.fileName, f.jpeg.length, f.jpeg));
  }
  final index = utf8.encode(const JsonEncoder.withIndent(' ').convert({
    ...meta,
    'frames': [for (final f in frames) f.toJson()],
  }));
  archive.addFile(ArchiveFile.bytes('frames.json', index));
  return ZipEncoder().encodeBytes(archive);
}
