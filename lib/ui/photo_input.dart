import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../services/recognizer_client.dart';
import 'hand_editor.dart';
import 'kiosk.dart';

/// 사진으로 손패 입력: 카메라/갤러리 선택 → 서버 인식 → 손패 채우기.
Future<void> showPhotoInput(BuildContext context, HandEditor editor) async {
  if (!RecognizerConfig.isConfigured) {
    _toast(context, '인식 서버 키가 설정되지 않은 빌드입니다');
    return;
  }

  final source = await showModalBottomSheet<ImageSource>(
    context: context,
    builder: (ctx) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 16, 16, 4),
            child: Text(
              '손패를 눕혀 한 줄로 놓고, 위에서 손패만 보이게 찍으세요.\n'
              '패 한 장이 화면 폭의 1/15 보다 크게 나와야 읽힙니다.',
              style: TextStyle(fontSize: 13),
            ),
          ),
          ListTile(
            leading: const Icon(Icons.photo_camera_outlined),
            title: const Text('카메라로 찍기'),
            onTap: () => Navigator.pop(ctx, ImageSource.camera),
          ),
          ListTile(
            leading: const Icon(Icons.photo_library_outlined),
            title: const Text('갤러리에서 고르기'),
            onTap: () => Navigator.pop(ctx, ImageSource.gallery),
          ),
          const SizedBox(height: 8),
        ],
      ),
    ),
  );
  if (source == null || !context.mounted) return;

  final XFile? picked;
  try {
    picked = await ImagePicker().pickImage(
      source: source,
      maxWidth: 1600,
      maxHeight: 1600,
      imageQuality: 88,
    );
  } catch (e) {
    if (context.mounted) _toast(context, '사진을 가져오지 못했습니다: $e');
    return;
  }
  if (picked == null || !context.mounted) return;

  final client = RecognizerClient();
  final result = await showDialog<Object>(
    context: context,
    barrierDismissible: false,
    builder: (ctx) => kioskWrap(ctx, _RecognizingDialog(
      future: client.recognize(File(picked!.path)),
      onCancel: client.close,
    )),
  );
  client.close();
  if (!context.mounted) return;

  if (result is RecognizeResult) {
    final secs = (result.latencyMs / 1000).toStringAsFixed(0);
    if (result.tiles.isEmpty) {
      final retry = await _showNotFound(context, result.notes, secs);
      if (retry && context.mounted) await showPhotoInput(context, editor);
      return;
    }
    final note = editor.setFromRecognition(
      result.tiles.map((t) => (code: t.code, confidence: t.confidence)).toList(),
    );
    final n = result.tiles.length;
    final parts = <String>['$n장 인식 ($secs초). 틀린 패는 눌러서 고치세요.'];
    if (note.isNotEmpty) parts.add(note);
    // 13·14장이 아니거나 서버가 특이사항을 적었으면 그 이유를 같이 보여준다.
    if ((n != 13 && n != 14) || result.notes.isNotEmpty) {
      final reason = result.notes.isNotEmpty ? '서버: ${result.notes}' : '';
      if (n != 13 && n != 14) parts.add('손패 장수(13·14)와 다릅니다. 사진에 다른 패가 섞였거나 일부를 못 읽었을 수 있습니다.');
      if (reason.isNotEmpty) parts.add(reason);
      _toast(context, parts.join(' '), long: true);
    } else {
      _toast(context, parts.join(' '));
    }
  } else if (result is RecognizerException) {
    _toast(context, result.message, long: true);
  } else if (result != null) {
    _toast(context, '인식 중 오류: $result', long: true);
  }
}

/// 0장일 때: 서버가 적은 이유(notes)와 촬영 안내를 보여주고 다시 찍을지 묻는다.
Future<bool> _showNotFound(BuildContext context, String notes, String secs) async {
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => kioskWrap(ctx, AlertDialog(
      title: const Text('패를 찾지 못했습니다'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (notes.isNotEmpty) ...[
            Text('서버 설명: $notes'),
            const SizedBox(height: 12),
          ],
          Text(
            '확인할 것\n'
            '• 손패가 앞면으로 눕혀져 있나요? (세워 둔 패·뒤집힌 패는 안 읽힙니다)\n'
            '• 테이블 전체가 아니라 손패만 크게 찍었나요?\n'
            '• 모니터·TV 화면을 찍은 사진은 패가 작아 거의 안 읽힙니다\n'
            '($secs초 걸림)',
            style: Theme.of(ctx).textTheme.bodySmall,
          ),
        ],
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('닫기')),
        FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('다시 찍기')),
      ],
    )),
  );
  return ok ?? false;
}

class _RecognizingDialog extends StatefulWidget {
  final Future<RecognizeResult> future;
  final VoidCallback onCancel;
  const _RecognizingDialog({required this.future, required this.onCancel});

  @override
  State<_RecognizingDialog> createState() => _RecognizingDialogState();
}

class _RecognizingDialogState extends State<_RecognizingDialog> {
  int _elapsed = 0;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() => _elapsed++);
    });
    widget.future.then(
      (r) {
        if (mounted) Navigator.of(context).pop(r);
      },
      onError: (Object e) {
        if (mounted) Navigator.of(context).pop(e);
      },
    );
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // 또렷한 손패 사진은 5~15초. 읽을 게 없거나 흐리면 모델이 오래 고민해 1분까지 간다.
    final hint = _elapsed < 15
        ? '보통 5~15초 걸립니다'
        : '읽기 어려운 사진이면 1분 가까이 걸릴 수 있습니다';
    return AlertDialog(
      content: Row(
        children: [
          const SizedBox(width: 28, height: 28, child: CircularProgressIndicator(strokeWidth: 3)),
          const SizedBox(width: 16),
          Expanded(child: Text('패를 읽는 중 ($_elapsed초)\n$hint')),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () {
            widget.onCancel();
            Navigator.of(context).pop();
          },
          child: const Text('취소'),
        ),
      ],
    );
  }
}

void _toast(BuildContext context, String message, {bool long = false}) {
  final messenger = ScaffoldMessenger.of(context)..hideCurrentSnackBar();
  messenger.showSnackBar(SnackBar(
    content: Text(message),
    duration: Duration(seconds: long ? 12 : 4),
    persist: false, // 액션이 있어도 duration 뒤 사라지게(Flutter 3.29+ 기본은 남음)
    action: long ? SnackBarAction(label: '닫기', onPressed: messenger.hideCurrentSnackBar) : null,
  ));
}
