import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/foundation.dart' show compute;
import 'package:flutter/material.dart';

import '../../table/mount_check.dart';
import '../kiosk.dart';

/// 거치 점검 창: 지금 카메라 사진 한 장으로 탁자 전체·기울기·패 크기를 재서 보여 준다(`lib/table/mount_check.dart`).
/// [fetch] = 지금 카메라 사진(JPEG). [live] 면 창이 떠 있는 동안 [interval] 마다 다시 잰다(카메라 헤드 — 셔터 없이 받는 경우만).
/// 카메라를 움직이면서 화면을 보고 맞추라고 만든 것이라, 창을 닫으면 아무것도 돌지 않는다.
Future<void> showMountCheck(
  BuildContext context, {
  required Future<Uint8List?> Function() fetch,
  int? captureLongSide,
  bool live = false,
  Duration interval = const Duration(seconds: 3),
  Future<MountCheck> Function(Uint8List jpeg, int? captureLongSide)? check,
}) =>
    showDialog<void>(
      context: context,
      builder: (ctx) => kioskWrap(
        ctx,
        MountCheckDialog(fetch: fetch, captureLongSide: captureLongSide, live: live, interval: interval, check: check),
        scale: 1.1,
      ),
    );

Color mountLevelColor(MountLevel l) => switch (l) {
      MountLevel.ok => const Color(0xFF66BB6A),
      MountLevel.caution => const Color(0xFFFFB300),
      MountLevel.bad => const Color(0xFFEF5350),
      MountLevel.unknown => Colors.grey,
    };

IconData mountLevelIcon(MountLevel l) => switch (l) {
      MountLevel.ok => Icons.check_circle,
      MountLevel.caution => Icons.warning_amber_rounded,
      MountLevel.bad => Icons.error,
      MountLevel.unknown => Icons.help_outline,
    };

String mountLevelLabel(MountLevel l) => switch (l) {
      MountLevel.ok => '거치 좋음',
      MountLevel.caution => '쓸 수 있음 — 주의할 점이 있습니다',
      MountLevel.bad => '거치를 고치세요',
      MountLevel.unknown => '판정하지 못했습니다',
    };

class MountCheckDialog extends StatefulWidget {
  final Future<Uint8List?> Function() fetch;
  final int? captureLongSide;
  final bool live;
  final Duration interval;

  /// 테스트에서 바꿔 끼운다. 기본은 `compute(mountCheckOfJpeg, …)`.
  final Future<MountCheck> Function(Uint8List jpeg, int? captureLongSide)? check;

  const MountCheckDialog({super.key, required this.fetch, this.captureLongSide, this.live = false, this.interval = const Duration(seconds: 3), this.check});

  @override
  State<MountCheckDialog> createState() => _MountCheckDialogState();
}

class _MountCheckDialogState extends State<MountCheckDialog> {
  Uint8List? _photo;
  MountCheck? _result;
  String? _error;
  bool _busy = false;
  late bool _live = widget.live;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    unawaited(_run());
    _arm();
  }

  void _arm() {
    _timer?.cancel();
    _timer = _live ? Timer.periodic(widget.interval, (_) => unawaited(_run())) : null;
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _run() async {
    if (_busy || !mounted) return;
    setState(() => _busy = true);
    try {
      final jpeg = await widget.fetch();
      if (!mounted) return;
      if (jpeg == null) {
        setState(() => _error = '사진을 받지 못했습니다');
        return;
      }
      final check = widget.check ?? (Uint8List b, int? long) => compute(mountCheckOfJpeg, (b, long));
      final r = await check(jpeg, widget.captureLongSide);
      if (!mounted) return;
      setState(() {
        _photo = jpeg;
        _result = r;
        _error = null;
      });
    } catch (e) {
      if (mounted) setState(() => _error = '점검 실패: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final r = _result;
    final wide = MediaQuery.sizeOf(context).width >= 760;
    final photo = _photoView(r);
    final list = _list(r);
    return AlertDialog(
      key: const ValueKey('mount-check-dialog'),
      title: Row(
        children: [
          const Expanded(child: Text('거치 점검')),
          if (_busy) const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
        ],
      ),
      content: SizedBox(
        width: wide ? 820 : 360,
        child: wide
            ? Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [Expanded(flex: 5, child: photo), const SizedBox(width: 16), Expanded(flex: 6, child: list)],
              )
            : SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [photo, const SizedBox(height: 12), list])),
      ),
      actions: [
        if (widget.live)
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('계속 재기'),
              Switch(
                key: const ValueKey('mount-check-live'),
                value: _live,
                onChanged: (v) => setState(() {
                  _live = v;
                  _arm();
                }),
              ),
            ],
          ),
        TextButton(key: const ValueKey('mount-check-again'), onPressed: _busy ? null : _run, child: const Text('다시 재기')),
        FilledButton(key: const ValueKey('mount-check-close'), onPressed: () => Navigator.pop(context), child: const Text('닫기')),
      ],
    );
  }

  Widget _photoView(MountCheck? r) {
    final p = _photo;
    if (p == null) {
      return AspectRatio(
        aspectRatio: 4 / 3,
        child: ColoredBox(color: Colors.black26, child: Center(child: Text(_error ?? '사진 받는 중…'))),
      );
    }
    return ClipRRect(
      borderRadius: BorderRadius.circular(6),
      child: Stack(
        children: [
          Image.memory(p, gaplessPlayback: true, fit: BoxFit.contain),
          if (r != null) Positioned.fill(child: CustomPaint(painter: _MountPainter(r))),
        ],
      ),
    );
  }

  Widget _list(MountCheck? r) {
    // 아직 결과가 없으면: 오류는 사진 칸에 이미 보이므로 여기엔 다시 쓰지 않는다.
    if (r == null) return _error == null ? const Text('재는 중…') : const SizedBox.shrink();
    final level = r.level;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          key: ValueKey('mount-check-level-${level.name}'),
          children: [
            Icon(mountLevelIcon(level), color: mountLevelColor(level), size: 28),
            const SizedBox(width: 8),
            Expanded(child: Text(mountLevelLabel(level), style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 17))),
          ],
        ),
        if (_error != null) Padding(padding: const EdgeInsets.only(top: 6), child: Text(_error!, style: const TextStyle(color: Color(0xFFEF5350)))),
        const SizedBox(height: 10),
        for (final i in r.items)
          Padding(
            key: ValueKey('mount-check-item-${i.key}-${i.level.name}'),
            padding: const EdgeInsets.symmetric(vertical: 5),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(mountLevelIcon(i.level), color: mountLevelColor(i.level), size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${i.title}: ${i.value}'),
                      for (final line in [i.advice, i.note])
                        if (line.isNotEmpty)
                          Text(line, style: TextStyle(fontSize: 12.5, color: Theme.of(context).colorScheme.onSurfaceVariant)),
                    ],
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

/// 사진 위에 펠트 네 모서리(판정 색)와 펠트가 잘린 변(빨간 띠)을 그린다.
class _MountPainter extends CustomPainter {
  final MountCheck r;
  _MountPainter(this.r);

  @override
  void paint(Canvas canvas, Size size) {
    final frame = r.items.where((i) => i.key == 'frame').firstOrNull?.level ?? MountLevel.unknown;
    final q = r.quad;
    if (q != null) {
      final path = Path();
      final c = q.corners;
      path.moveTo(c[0].x * size.width, c[0].y * size.height);
      for (var i = 1; i < 4; i++) {
        path.lineTo(c[i].x * size.width, c[i].y * size.height);
      }
      path.close();
      canvas.drawPath(
          path,
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = 3
            ..color = mountLevelColor(frame));
    }
    // 펠트가 잘린 쪽(사진 변에 닿은 쪽)만 빨간 띠. 흰 테두리만 밖인 쪽은 글로만 알린다.
    final cut = <int>{
      for (var i = 0; i < 4; i++)
        if ((r.touch?[i] ?? 0) >= mountTouchMin) i,
    };
    final bar = Paint()..color = mountLevelColor(MountLevel.bad).withValues(alpha: 0.85);
    const t = 6.0;
    for (final i in cut) {
      canvas.drawRect(
          switch (i) {
            0 => Rect.fromLTWH(0, 0, size.width, t),
            1 => Rect.fromLTWH(size.width - t, 0, t, size.height),
            2 => Rect.fromLTWH(0, size.height - t, size.width, t),
            _ => Rect.fromLTWH(0, 0, t, size.height),
          },
          bar);
    }
  }

  @override
  bool shouldRepaint(_MountPainter old) => old.r != r;
}
