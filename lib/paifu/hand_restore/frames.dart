/// 손패 복원의 프레임 재료(`docs/paifu_hand_restore_api_1121.md` 3-2): 받아 둔 헤드 녹화에서 차례 창 안 프레임을 초당 5장으로 골라
/// hero 손패 구역을 잘라 그 사람 시점(아래 = 탁자 테두리)으로 돌린다. 도구(zoom · strip)용 그림 만들기와 보내기 전 줄이기도 여기.
///
/// 그림 일은 [ImageRunner] 로 돌린다 — 앱은 `compute`(다른 isolate), 시험은 바로 부르는 것을 넣는다.
/// 오프라인 판: `experiments/paifu_frames/handtrack/htcommon.py` `band_crop`(ROT), `geminiagent.py` `strip_images`, `claudeagent.py` `zoom_image` · `fit`.
library;

import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart' show compute;
import 'package:image/image.dart' as img;

/// 그림 일을 돌리는 함수(`compute` 와 같은 꼴).
typedef ImageRunner = Future<R> Function<M, R>(FutureOr<R> Function(M message) fn, M message);

/// 앱 기본: 다른 isolate 에서.
Future<R> computeRunner<M, R>(FutureOr<R> Function(M message) fn, M message) => compute(fn, message);

/// 시험 · 웹: 바로.
Future<R> directRunner<M, R>(FutureOr<R> Function(M message) fn, M message) async => fn(message);

/// 녹화 프레임 원천: 시각(ms) 목록과 그 프레임 JPEG.
abstract class HandFrameSource {
  /// 가진 프레임 시각(오름차순).
  Future<List<int>> list();
  Future<Uint8List> bytes(int ms);
}

/// `RecordPuller` 가 쓴 폴더(`<dir>/f_<ms>.jpg`).
class DirFrameSource implements HandFrameSource {
  final String dir;
  DirFrameSource(this.dir);

  static final _name = RegExp(r'^f_(\d+)\.jpg$');

  @override
  Future<List<int>> list() async {
    final d = Directory(dir);
    if (!await d.exists()) return const [];
    final out = <int>[];
    await for (final e in d.list()) {
      final m = _name.firstMatch(e.path.replaceAll('\\', '/').split('/').last);
      if (m != null) out.add(int.parse(m.group(1)!));
    }
    return out..sort();
  }

  @override
  Future<Uint8List> bytes(int ms) => File('$dir/f_$ms.jpg').readAsBytes();
}

/// 메모리 원천(시험).
class MemoryFrameSource implements HandFrameSource {
  final Map<int, Uint8List> frames;
  MemoryFrameSource(this.frames);

  @override
  Future<List<int>> list() async => frames.keys.toList()..sort();

  @override
  Future<Uint8List> bytes(int ms) async {
    final b = frames[ms];
    if (b == null) throw StateError('프레임 없음: $ms');
    return b;
  }
}

/// 창 [startMs, endMs] 안 프레임을 [stepMs] 간격(초당 5장)에 가장 가까운 것으로 고른다. [sorted] 는 오름차순.
List<int> pickFrames(List<int> sorted, int startMs, int endMs, {int stepMs = 200}) {
  final inside = [
    for (final f in sorted)
      if (f >= startMs && f <= endMs) f,
  ];
  if (inside.isEmpty) return const [];
  final out = <int>[];
  var j = 0;
  for (var t = inside.first; t <= inside.last; t += stepMs) {
    while (j + 1 < inside.length && (inside[j + 1] - t).abs() <= (inside[j] - t).abs()) {
      j++;
    }
    if (out.isEmpty || out.last != inside[j]) out.add(inside[j]);
  }
  return out;
}

/// hero 시점으로 돌리는 각도(시계 방향, `image` 의 copyRotate). 오른쪽에 앉은 사람은 시계 90°(그 사람 쪽 변이 아래로).
int rotationOf(String side) => switch (side) {
      'right' => 90,
      'top' => 180,
      'left' => 270,
      _ => 0,
    };

/// 한 차례 프레임 자르기 일감. [box] = [xmin, ymin, xmax, ymax](0~1000).
typedef CropJob = ({List<Uint8List> jpegs, List<int> box, String side, int quality});

/// 프레임마다 [CropJob.box] 를 잘라 돌린 JPEG. 읽지 못한 프레임은 빈 바이트.
List<Uint8List> cropFrames(CropJob job) => [for (final b in job.jpegs) cropOne(b, job.box, job.side, quality: job.quality)];

Uint8List cropOne(Uint8List jpeg, List<int> box, String side, {int quality = 90}) {
  final src = img.decodeJpg(jpeg);
  if (src == null) return Uint8List(0);
  final x0 = (box[0] / 1000 * src.width).round().clamp(0, src.width - 1);
  final y0 = (box[1] / 1000 * src.height).round().clamp(0, src.height - 1);
  final x1 = (box[2] / 1000 * src.width).round().clamp(x0 + 1, src.width);
  final y1 = (box[3] / 1000 * src.height).round().clamp(y0 + 1, src.height);
  var c = img.copyCrop(src, x: x0, y: y0, width: x1 - x0, height: y1 - y0);
  final a = rotationOf(side);
  if (a != 0) c = img.copyRotate(c, angle: a);
  return img.encodeJpg(c, quality: quality);
}

/// 한 차례 프레임(잘라 돌린 것). 번호 i = [ms] 의 i 번째.
class TurnFrames {
  final List<int> ms;
  final List<Uint8List> jpegs;
  final int width, height;
  const TurnFrames({required this.ms, required this.jpegs, required this.width, required this.height});

  int get length => ms.length;
}

/// 원천에서 창 안 프레임을 골라 잘라 돌린다. 고를 프레임이 없거나 첫 프레임을 못 읽으면 null.
Future<TurnFrames?> loadTurnFrames(
  HandFrameSource source, {
  required int startMs,
  required int endMs,
  required List<int> box,
  required String side,
  ImageRunner runner = computeRunner,
  int quality = 90,
  List<int>? all,
  int chunk = 30,
}) async {
  final picked = pickFrames(all ?? await source.list(), startMs, endMs);
  if (picked.length < 2) return null;
  // 원본(헤드 2040 화소 JPEG)을 한꺼번에 들고 있지 않게 몇십 장씩 읽어 자른다.
  final out = <Uint8List>[];
  for (var i = 0; i < picked.length; i += chunk) {
    final raw = <Uint8List>[for (final ms in picked.skip(i).take(chunk)) await source.bytes(ms)];
    out.addAll(await runner(cropFrames, (jpegs: raw, box: box, side: side, quality: quality)));
  }
  final keepMs = <int>[], keep = <Uint8List>[];
  for (var i = 0; i < picked.length; i++) {
    if (out[i].isEmpty) continue;
    keepMs.add(picked[i]);
    keep.add(out[i]);
  }
  if (keep.length < 2) return null;
  final first = img.decodeJpg(keep.first)!;
  return TurnFrames(ms: keepMs, jpegs: keep, width: first.width, height: first.height);
}

// ── 도구 그림 ──

/// 긴 변이 이보다 크면 보내기 전에 줄인다(Opus 5.5 의 원래 해상도 상한, claudeagent.py LONG_EDGE).
const int longEdge = 2576;

/// 긴 변이 [longEdge] 를 넘는 JPEG 만 줄이고 나머지는 그대로.
Uint8List fitJpeg(Uint8List jpeg) {
  final im = img.decodeJpg(jpeg);
  if (im == null) return jpeg;
  final m = im.width > im.height ? im.width : im.height;
  if (m <= longEdge) return jpeg;
  final sc = longEdge / m;
  final r = img.copyResize(im,
      width: (im.width * sc).floor().clamp(1, longEdge),
      height: (im.height * sc).floor().clamp(1, longEdge),
      interpolation: img.Interpolation.cubic);
  return img.encodeJpg(r, quality: 88);
}

typedef ZoomJob = ({Uint8List jpeg, int x0, int x1, int? y0, int? y1});

/// 한 프레임 일부를 잘라 키운다(배율 min(3, 1600 / 폭)). 돌려주는 좌표는 그림 안으로 맞춘 것.
({Uint8List jpeg, int x0, int x1, int y0, int y1}) zoomFrame(ZoomJob job) {
  final im = img.decodeJpg(job.jpeg)!;
  var xa = job.x0.clamp(0, im.width), xb = job.x1.clamp(0, im.width);
  if (xa > xb) (xa, xb) = (xb, xa);
  final y0 = (job.y0 ?? 0).clamp(0, im.height);
  final y1 = (job.y1 == null || job.y1 == 0 ? im.height : job.y1!).clamp(0, im.height);
  final w = (xb > xa + 8 ? xb : xa + 8) - xa, h = (y1 > y0 + 8 ? y1 : y0 + 8) - y0;
  final cr = img.copyCrop(im, x: xa, y: y0, width: w, height: h);
  final sc = (1600 / (cr.width < 1 ? 1 : cr.width)).clamp(0.0, 3.0);
  final out = img.copyResize(cr,
      width: (cr.width * sc).floor().clamp(1, 1 << 14),
      height: (cr.height * sc).floor().clamp(1, 1 << 14),
      interpolation: img.Interpolation.cubic);
  return (jpeg: img.encodeJpg(out, quality: 88), x0: xa, x1: xb, y0: y0, y1: y1);
}

const int stripRows = 8, stripMax = 32;

/// strip 일감: [jpegs] 는 [idx] 프레임들(같은 순서).
typedef StripJob = ({List<Uint8List> jpegs, List<int> idx, int x0, int x1, int? y0, int? y1, int width, int height});

/// 같은 영역을 프레임마다 잘라 위아래로 쌓은 그림들(한 장 [stripRows] 줄, 왼쪽에 프레임 번호). geminiagent.strip_images 와 같은 일.
List<({Uint8List jpeg, int from, int to, int x0, int x1, int y0, int y1})> stripSheets(StripJob job) {
  var xa = job.x0.clamp(0, job.width), xb = job.x1.clamp(0, job.width);
  if (xa > xb) (xa, xb) = (xb, xa);
  var y0 = (job.y0 ?? 0).clamp(0, job.height);
  var y1 = (job.y1 == null || job.y1 == 0 ? job.height : job.y1!).clamp(0, job.height);
  if (xb < xa + 8) xb = xa + 8;
  if (y1 < y0 + 8) y1 = y0 + 8;
  final sc = (1500 / (xb - xa)).clamp(0.0, 3.0);
  final cw = ((xb - xa) * sc).floor().clamp(1, 1 << 14), ch = ((y1 - y0) * sc).floor().clamp(1, 1 << 14);
  final out = <({Uint8List jpeg, int from, int to, int x0, int x1, int y0, int y1})>[];
  for (var g = 0; g < job.idx.length; g += stripRows) {
    final part = job.idx.sublist(g, (g + stripRows).clamp(0, job.idx.length));
    final sheet = img.Image(width: cw + 70, height: part.length * (ch + 4));
    img.fill(sheet, color: img.ColorRgb8(255, 255, 255));
    for (var r = 0; r < part.length; r++) {
      final im = img.decodeJpg(job.jpegs[g + r]);
      if (im == null) continue;
      final w = (xb.clamp(0, im.width) - xa.clamp(0, im.width)).clamp(1, im.width);
      final h = (y1.clamp(0, im.height) - y0.clamp(0, im.height)).clamp(1, im.height);
      final crop = img.copyCrop(im, x: xa.clamp(0, im.width - 1), y: y0.clamp(0, im.height - 1), width: w, height: h);
      final rs = img.copyResize(crop, width: cw, height: ch, interpolation: img.Interpolation.cubic);
      img.compositeImage(sheet, rs, dstX: 70, dstY: r * (ch + 4));
      img.drawString(sheet, part[r].toString().padLeft(3, '0'),
          font: img.arial24, x: 4, y: r * (ch + 4) + ch ~/ 2 - 12, color: img.ColorRgb8(0, 0, 0));
    }
    out.add((jpeg: img.encodeJpg(sheet, quality: 88), from: part.first, to: part.last, x0: xa, x1: xb, y0: y0, y1: y1));
  }
  return out;
}
