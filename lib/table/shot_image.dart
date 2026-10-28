/// 촬영 한 장을 **한 번만 디코딩**해 들고 있으면서 축소본·구역 크롭을 여러 번 만든다.
///
/// 예전에는 축소본([shrinkForLocate])과 크롭([cropMany])을 각각 `compute()` 로 돌려 12MP 원본을 두 번 디코딩했다
/// (`compute()` 는 매번 새 isolate 를 만들고 버려서, 디코딩된 이미지(약 36MB)를 넘기려면 복사가 일어난다).
/// [IsolateShotImage] 는 isolate 하나를 띄워 디코딩한 이미지를 그 안에 두고 메시지로 일을 시킨다. 다 쓰면 [close].
/// 웹은 isolate 를 오래 띄울 수 없어 [DirectShotImage](같은 스레드)를 쓴다.
library;

import 'dart:async';
import 'dart:isolate';
import 'dart:typed_data';

import 'cropper.dart';

abstract class ShotImage {
  /// 판정·locate 용 축소 JPEG(긴 변 [locateMaxSide]). [shrinkForLocate] 와 같은 바이트.
  Future<Uint8List> shrink();

  /// 구역별 크롭 JPEG(순서 유지). [cropMany] 와 같은 바이트.
  Future<List<Uint8List>> crop(List<CropSpec> specs);

  /// 들고 있는 이미지를 놓는다. 여러 번 불러도 된다.
  Future<void> close();
}

/// 같은 isolate 에서 바로(테스트·웹). 처음 쓸 때 디코딩한다.
class DirectShotImage implements ShotImage {
  final Uint8List original;
  TableImage? _image;
  DirectShotImage(this.original);

  TableImage get _im => _image ??= TableImage.decode(original);

  @override
  Future<Uint8List> shrink() async => _im.shrunkJpeg();

  @override
  Future<List<Uint8List>> crop(List<CropSpec> specs) async => [
    for (final s in specs) _im.cropJpeg(s.box, side: s.side, pad: s.pad),
  ];

  @override
  Future<void> close() async => _image = null;
}

/// isolate 하나에 디코딩한 이미지를 두고 일을 시킨다. 요청은 보낸 순서대로 처리된다.
class IsolateShotImage implements ShotImage {
  final Isolate _isolate;
  final SendPort _port;
  bool _closed = false;
  IsolateShotImage._(this._isolate, this._port);

  /// isolate 를 띄우고 원본을 넘긴다. 디코딩은 isolate 안에서 첫 요청 전에 한다.
  static Future<IsolateShotImage> open(Uint8List original) async {
    final ready = ReceivePort();
    final isolate = await Isolate.spawn(_worker, (ready.sendPort, original), errorsAreFatal: true);
    final port = await ready.first as SendPort;
    return IsolateShotImage._(isolate, port);
  }

  Future<Object?> _ask(String cmd, [Object? arg]) async {
    if (_closed) throw StateError('촬영 이미지를 이미 닫았습니다');
    final reply = ReceivePort();
    _port.send((cmd, arg, reply.sendPort));
    final res = await reply.first;
    if (res case ('error', final String message)) throw FormatException(message);
    return res;
  }

  @override
  Future<Uint8List> shrink() async => await _ask('shrink') as Uint8List;

  @override
  Future<List<Uint8List>> crop(List<CropSpec> specs) async => (await _ask('crop', specs) as List).cast<Uint8List>();

  @override
  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    _isolate.kill(priority: Isolate.immediate);
  }

  static void _worker((SendPort, Uint8List) args) {
    final (ready, original) = args;
    final inbox = ReceivePort();
    ready.send(inbox.sendPort);
    final shot = DirectShotImage(original);
    inbox.listen((msg) async {
      final (cmd, arg, reply) = msg as (String, Object?, SendPort);
      try {
        reply.send(switch (cmd) {
          'shrink' => await shot.shrink(),
          'crop' => await shot.crop((arg as List).cast<CropSpec>()),
          _ => ('error', '모르는 요청: $cmd'),
        });
      } catch (e) {
        reply.send(('error', '$e'));
      }
    });
  }
}
