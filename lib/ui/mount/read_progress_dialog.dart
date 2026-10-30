import 'dart:async';

import 'package:flutter/material.dart';

import '../../table/table_reader.dart';
import '../kiosk.dart';

/// 판독 진행 창: 단계와 경과 초, "취소하고 직접 입력". [done] 이 끝나면 스스로 닫힌다.
/// [slowAfter] 가 지나면 안내를 바꾸고 버튼을 강조한다. 화면을 저절로 넘기지는 않는다 — 곧 끝날 판독을 버리지 않게.
/// Gemini 지연은 가끔 30초를 넘어(2026-10-30 태블릿 66·90초), 그때 기다리고만 있지 않게 한다.
class ReadProgressDialog extends StatefulWidget {
  final ValueNotifier<ReadStage> stage;
  final Future<void> done;
  final VoidCallback onCancel;
  final Duration slowAfter;
  const ReadProgressDialog({
    super.key,
    required this.stage,
    required this.done,
    required this.onCancel,
    this.slowAfter = const Duration(seconds: 20),
  });

  @override
  State<ReadProgressDialog> createState() => _ReadProgressDialogState();
}

class _ReadProgressDialogState extends State<ReadProgressDialog> {
  int _elapsed = 0;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() => _elapsed++);
    });
    widget.done.whenComplete(() {
      debugPrint('[read] 진행 창 done mounted=$mounted');
      if (mounted) Navigator.of(context).pop();
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // 키오스크(테이블 화면 위)에서는 멀리서도 보이게 크게.
    final kiosk = isKioskLayout(context);
    final slow = _elapsed >= widget.slowAfter.inSeconds;
    const label = Text('취소하고 직접 입력');
    const key = ValueKey('read-cancel');
    return kioskWrap(
      context,
      AlertDialog(
        content: SizedBox(
          width: kiosk ? 520 : null,
          child: ValueListenableBuilder<ReadStage>(
            valueListenable: widget.stage,
            builder: (_, s, _) => Row(
              children: [
                SizedBox(
                  width: kiosk ? 48 : 28,
                  height: kiosk ? 48 : 28,
                  child: CircularProgressIndicator(strokeWidth: kiosk ? 4 : 3),
                ),
                SizedBox(width: kiosk ? 24 : 16),
                Expanded(
                  child: Text(
                    '${s.label} ($_elapsed초)\n'
                    '${slow ? '평소보다 오래 걸립니다. 더 기다리거나 직접 입력하세요' : '보통 10~15초 걸립니다'}',
                    style: kiosk ? const TextStyle(fontSize: 20, height: 1.4) : null,
                  ),
                ),
              ],
            ),
          ),
        ),
        actions: [
          if (slow)
            FilledButton(key: key, onPressed: widget.onCancel, child: label)
          else
            TextButton(key: key, onPressed: widget.onCancel, child: label),
        ],
      ),
    );
  }
}
