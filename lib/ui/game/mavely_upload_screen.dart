import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../../game/game.dart';
import '../../game/game_store.dart';
import '../../game/mavely_upload.dart';

/// 마블리 입력 페이지(https://mavely.isugame.com/new)를 앱 안 WebView 로 열어 이름·점수·별·공탁금을 채운다.
///
/// 마지막 '등록' 은 사용자가 페이지에서 직접 누른다(앱은 누르지도, 직접 POST 하지도 않는다).
/// 페이지의 confirm("후원 및 역만 입력하셨나요?")·alert 는 Flutter 대화상자로 띄운다(안 받으면 Android 에서 confirm 이 false 가 돼 등록이 안 된다).
/// confirm 에 '예' 를 받은 뒤 주소가 /history 로 바뀌면 등록 성공으로 보고 [GameStore.markMavelyUploaded] · 스낵바 · 닫기.
class MavelyUploadScreen extends StatefulWidget {
  final Game game;
  const MavelyUploadScreen({super.key, required this.game});

  @override
  State<MavelyUploadScreen> createState() => _MavelyUploadScreenState();
}

class _MavelyUploadScreenState extends State<MavelyUploadScreen> {
  late final MavelyEntry _entry = mavelyEntryFor(widget.game);
  late final WebViewController _web;

  /// 채우기 스크립트를 보냈는가. 처음 로드 때만 채운다(사용자가 고친 값을 덮지 않게). 폼을 못 찾았으면 다음 로드 때 다시.
  bool _fillSent = false;

  /// 채우기 결과: null 아직, true 채움, false 못 채움.
  bool? _filled;
  String? _fillError;
  List<String> _unknownNames = const [];
  bool _membersLoaded = true;

  /// 페이지 confirm 에 '예' 를 받았는가(등록 버튼 → 검사 통과 → confirm). 이 뒤 /history 로 가면 등록 성공.
  bool _submitConfirmed = false;
  bool _done = false;
  int _progress = 0;

  @override
  void initState() {
    super.initState();
    _web = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..addJavaScriptChannel(mavelyBridgeName, onMessageReceived: _onBridge)
      ..setNavigationDelegate(NavigationDelegate(
        onProgress: (p) {
          if (mounted) setState(() => _progress = p);
        },
        onPageFinished: _onPageFinished,
        onUrlChange: (c) => _checkUrl(c.url),
      ))
      ..setOnJavaScriptAlertDialog(_onAlert)
      ..setOnJavaScriptConfirmDialog(_onConfirm)
      ..loadRequest(Uri.parse(mavelyNewUrl));
  }

  static String _path(String? url) => url == null ? '' : (Uri.tryParse(url)?.path ?? '');

  Future<void> _onPageFinished(String url) async {
    if (_checkUrl(url)) return;
    if (_fillSent || !_path(url).startsWith('/new')) return;
    _fillSent = true;
    try {
      await _web.runJavaScript(mavelyFillScript(_entry));
    } catch (e) {
      _fillSent = false;
      if (mounted) {
        setState(() {
          _filled = false;
          _fillError = '$e';
        });
      }
    }
  }

  void _onBridge(JavaScriptMessage m) {
    Map<String, dynamic> j;
    try {
      j = jsonDecode(m.message) as Map<String, dynamic>;
    } catch (_) {
      return;
    }
    if (!mounted) return;
    setState(() {
      if (j['ok'] == true) {
        _filled = true;
        _fillError = null;
        _unknownNames = ((j['unknownNames'] as List?) ?? const []).map((e) => '$e').toList();
        _membersLoaded = j['membersLoaded'] != false;
      } else {
        _filled = false;
        _fillError = '${j['error'] ?? '알 수 없음'}';
        _fillSent = false; // 다시 로드되면 한 번 더 채워 본다.
      }
    });
  }

  /// 주소가 /history 면(등록 confirm 뒤) 성공 처리. 처리했으면 true.
  bool _checkUrl(String? url) {
    if (_done || !_submitConfirmed || !_path(url).startsWith('/history')) return false;
    _done = true;
    gameStore.markMavelyUploaded(widget.game.id);
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('마블리에 올렸습니다')));
      Navigator.of(context).maybePop(true);
    }
    return true;
  }

  Future<void> _onAlert(JavaScriptAlertDialogRequest r) async {
    // alert 는 검사 실패·등록 실패 때 뜬다 → 등록 흐름이 끝난 것으로 본다.
    _submitConfirmed = false;
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('마블리'),
        content: Text(r.message),
        actions: [FilledButton(onPressed: () => Navigator.pop(ctx), child: const Text('확인'))],
      ),
    );
  }

  Future<bool> _onConfirm(JavaScriptConfirmDialogRequest r) async {
    if (!mounted) return false;
    final ok = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        title: const Text('마블리'),
        content: Text(r.message),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('취소')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('확인')),
        ],
      ),
    );
    _submitConfirmed = ok == true;
    return ok == true;
  }

  Widget _summary(BuildContext context) {
    final e = _entry;
    final t = Theme.of(context).textTheme;
    final seats = [
      for (var s = 0; s < 4; s++)
        '${const ['東', '南', '西', '北'][s]} ${e.names[s]} ${e.points[s]}${e.stars[s] > 0 ? ' ★${e.stars[s]}' : ''}',
    ];
    final warn = <String>[
      if (_filled == false) '자동으로 채우지 못했습니다($_fillError). 아래 페이지에 직접 넣으세요.',
      // 스크립트는 멤버 목록에 없는 이름을 '' 로 비운다(unknownNames = 비운 이름). 목록을 못 불러오면 이름을 모두 비운다.
      if (_filled == true && _membersLoaded && _unknownNames.isNotEmpty)
        '마블리 멤버에 없는 이름은 비워 두었습니다: ${_unknownNames.join(', ')} — 사이트에서 직접 고르세요',
      if (_filled == true && !_membersLoaded) '마블리 멤버 목록을 못 불러와 이름을 비워 두었습니다 — 직접 고르세요',
    ];
    return Material(
      key: const ValueKey('mavely-summary'),
      color: Theme.of(context).colorScheme.surfaceContainerHigh,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${seats.join('   ')}   공탁 ${e.deposit}',
                style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700, fontFeatures: const [FontFeature.tabularFigures()])),
            const SizedBox(height: 4),
            Text(
              _filled == null ? '마블리 페이지를 여는 중… 채워지면 값을 확인하고 아래 \'등록\' 을 직접 누르세요.' : '값을 확인하고 아래 \'등록\' 을 직접 누르세요.',
              style: t.bodyMedium,
            ),
            for (final w in warn)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(w, style: t.bodyMedium?.copyWith(color: Theme.of(context).colorScheme.error, fontWeight: FontWeight.w700)),
              ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('마블리에 올리기'),
        actions: [
          IconButton(
            tooltip: '새로 고침(값을 다시 채움)',
            icon: const Icon(Icons.refresh),
            onPressed: () {
              setState(() {
                _fillSent = false;
                _filled = null;
              });
              _web.loadRequest(Uri.parse(mavelyNewUrl));
            },
          ),
        ],
      ),
      body: Column(
        children: [
          _summary(context),
          if (_progress < 100) LinearProgressIndicator(value: _progress / 100),
          Expanded(child: WebViewWidget(controller: _web)),
        ],
      ),
    );
  }
}
