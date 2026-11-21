/// 재생 화면의 "손패 복원 (Claude API)" 창들(`docs/paifu_hand_restore_api_1121.md` 3-7): API 키 → 확인(차례 수 · 어림 비용 · 한도)
/// → 진행(차례 i/N · 누적 달러 · 취소) → 결과. 단추를 그리는 곳은 `lib/ui/paifu/paifu_screen.dart`.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../paifu.dart';
import 'claude_client.dart';
import 'restorer.dart';
import 'turn_agent.dart';
import 'turns.dart';

bool _dirExists(String dir) {
  try {
    return Directory(dir).existsSync();
  } catch (_) {
    return false;
  }
}

HandRestoreRunner _realRunner(String apiKey) =>
    HandRestorer(reader: TurnAgent(client: ClaudeClient(httpClient: http.Client(), apiKey: apiKey)));

/// 바꿔 끼울 수 있는 것(시험): 녹화 폴더가 있는지, 키로 실행기 만들기.
class HandRestoreSetup {
  final bool Function(String dir) dirExists;
  final HandRestoreRunner Function(String apiKey) runnerFor;
  const HandRestoreSetup({this.dirExists = _dirExists, this.runnerFor = _realRunner});
}

/// 버튼을 낼 수 없는 까닭. 낼 수 있으면 null. 손패가 이미 있는 판은 부르지 않는다.
String? restoreBlocker(Paifu p, HandRestoreSetup setup) {
  if (endRowOf(p) == null) return '끝 손패가 없는 판이라 손패를 복원할 수 없습니다';
  final f = p.frames;
  if (f == null) return '헤드 녹화를 받아 저장하던 판이 아니라 손패를 복원할 수 없습니다';
  if (!setup.dirExists(f.dir)) return '녹화 폴더가 이 기기에 없어 손패를 복원할 수 없습니다';
  return null;
}

/// 확인 창 글(설계서 3-7 의 어림 비용 글 그대로).
String restorePlanText(List<RestoreTurn> turns, {double gameLimit = 10, double turnLimit = 5}) {
  final api = turns.where((t) => t.usesApi).length;
  final rule = turns.where((t) => t.kind == RestoreTurnKind.rule).length;
  final guess = turns.where((t) => t.kind == RestoreTurnKind.afterCall).length;
  final bad = turns.where((t) => t.kind == RestoreTurnKind.unsupported).length;
  return [
    'API 로 읽을 차례 $api · 규칙 차례(리치 뒤 쯔모기리) $rule${guess > 0 ? ' · 짐작 차례(울기 뒤) $guess' : ''}'
        '${bad > 0 ? ' · 복원 못 하는 차례 $bad' : ''}',
    '어림 비용: 차례당 0.1 ~ 1.7달러, 판당 약 3달러(11-14 실험) — 이 판은 약 ${(api * 0.1).toStringAsFixed(1)} ~ ${(api * 1.7).toStringAsFixed(1)}달러',
    '한도: 차례당 ${turnLimit.toStringAsFixed(0)}달러 · 판 ${gameLimit.toStringAsFixed(0)}달러(넘기 전에 멈춤)',
    '뒤 차례부터 읽고, 끝 손패에서 거꾸로 복원합니다. 이 앱 v1 의 정확도는 잰 적이 없습니다.',
  ].join('\n');
}

/// 키 입력 창. 넣은 키(빈 값이면 null).
Future<String?> askApiKey(BuildContext context) async {
  final v = await showDialog<String>(context: context, builder: (_) => const _KeyDialog());
  return v == null || v.isEmpty ? null : v;
}

class _KeyDialog extends StatefulWidget {
  const _KeyDialog();

  @override
  State<_KeyDialog> createState() => _KeyDialogState();
}

class _KeyDialogState extends State<_KeyDialog> {
  final _c = TextEditingController();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Claude API 키'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('이 기기에만 저장합니다. 저장한 뒤에는 다시 보여 주지 않습니다.'),
            TextField(
              key: const ValueKey('restore-key-field'),
              controller: _c,
              obscureText: true,
              autocorrect: false,
              enableSuggestions: false,
              decoration: const InputDecoration(hintText: 'sk-ant-...'),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('취소')),
          FilledButton(
            key: const ValueKey('restore-key-save'),
            onPressed: () => Navigator.pop(context, _c.text.trim()),
            child: const Text('저장'),
          ),
        ],
      );
}

/// 확인 → 진행 → 결과. 손패를 채워 저장했으면 그 패보, 아니면 null.
Future<Paifu?> runHandRestore(BuildContext context, {required Paifu paifu, required String gameId, required HandRestoreSetup setup}) async {
  var key = await ClaudeKeyStore.load();
  if (!context.mounted) return null;
  if (key == null) {
    key = await askApiKey(context);
    if (key == null || !context.mounted) return null;
    await ClaudeKeyStore.save(key);
    if (!context.mounted) return null;
  }
  final turns = planTurns(paifu);
  final go = await showDialog<String>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('손패 복원 (Claude API)'),
      content: Text(restorePlanText(turns), key: const ValueKey('restore-plan')),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx, 'key'), child: const Text('API 키 지우기')),
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('취소')),
        FilledButton(
          key: const ValueKey('restore-start'),
          onPressed: () => Navigator.pop(ctx, 'go'),
          child: const Text('시작'),
        ),
      ],
    ),
  );
  if (go == 'key') {
    await ClaudeKeyStore.clear();
    return null;
  }
  if (go != 'go' || !context.mounted) return null;
  final runner = setup.runnerFor(key);
  final res = await showDialog<({RestoreOutcome? outcome, String? error})>(
    context: context,
    barrierDismissible: false,
    builder: (_) => _ProgressDialog(run: (onProgress, cancelled) => runner.run(paifu, onProgress: onProgress, cancelled: cancelled)),
  );
  if (res == null || !context.mounted) return null;
  final o = res.outcome;
  Paifu? saved;
  if (o?.paifu != null) {
    await RestoreStore.save(gameId, paifu, o!.paifu!);
    saved = o.paifu;
  }
  if (!context.mounted) return saved;
  await showDialog<void>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(saved != null ? '손패 복원 끝' : '손패를 복원하지 못했습니다'),
      content: Text(res.error != null ? '오류: ${res.error}' : restoreResultText(o!), key: const ValueKey('restore-result')),
      actions: [FilledButton(onPressed: () => Navigator.pop(ctx), child: const Text('확인'))],
    ),
  );
  return saved;
}

String restoreResultText(RestoreOutcome o) {
  final rb = o.rebuild;
  final total = rb.memo.length;
  return [
    '복원한 차례 ${rb.restored} / $total${rb.complete ? ' (시작 손패까지)' : ''}',
    if (rb.failedTurn != null) '멈춘 차례: ${rb.failedTurn! + 1}번째 버림 — ${rb.failReason}',
    if (o.unsureTurns.isNotEmpty) '확신 낮은 차례: ${o.unsureTurns.map((t) => '$t번째').join(' · ')}',
    if (o.guessTurns > 0) '짐작으로 끼운 차례(울기 뒤): ${o.guessTurns}',
    '비용 약 ${o.usd.toStringAsFixed(2)}달러',
    if (o.stopReason != null) '읽기를 멈춘 까닭: ${o.stopReason}',
  ].join('\n');
}

class _ProgressDialog extends StatefulWidget {
  final Future<RestoreOutcome> Function(void Function(RestoreProgress) onProgress, bool Function() cancelled) run;
  const _ProgressDialog({required this.run});

  @override
  State<_ProgressDialog> createState() => _ProgressDialogState();
}

class _ProgressDialogState extends State<_ProgressDialog> {
  RestoreProgress? _p;
  bool _cancel = false;

  @override
  void initState() {
    super.initState();
    _start();
  }

  Future<void> _start() async {
    ({RestoreOutcome? outcome, String? error}) r;
    try {
      final o = await widget.run((p) {
        if (mounted) setState(() => _p = p);
      }, () => _cancel);
      r = (outcome: o, error: null);
    } catch (e) {
      r = (outcome: null, error: '$e');
    }
    if (mounted) Navigator.of(context).pop(r);
  }

  @override
  Widget build(BuildContext context) {
    final p = _p;
    return PopScope(
      canPop: false,
      child: AlertDialog(
        title: const Text('손패 복원 중'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            LinearProgressIndicator(value: p == null || p.total == 0 ? null : p.done / p.total),
            const SizedBox(height: 8),
            Text(
              p == null
                  ? '준비 중'
                  : '차례 ${p.done}/${p.total} · 누적 ${p.usd.toStringAsFixed(2)}달러${p.message.isEmpty ? '' : '\n${p.message}'}',
              key: const ValueKey('restore-progress'),
            ),
            if (_cancel) const Text('취소하는 중 — 지금 차례 호출이 끝나면 멈춥니다'),
          ],
        ),
        actions: [
          TextButton(
            key: const ValueKey('restore-cancel'),
            onPressed: _cancel ? null : () => setState(() => _cancel = true),
            child: const Text('취소'),
          ),
        ],
      ),
    );
  }
}
