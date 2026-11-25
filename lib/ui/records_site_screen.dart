import 'package:flutter/material.dart';

import '../game/game_store.dart';
import '../game/records_upload.dart';
import 'kiosk.dart';

/// 기록 사이트 설정(룰 설정 화면에서 연다): 주소 · 매장 키 · 켜기/끄기, 지금 올리기 · 지난 대국 모두 올리기, 대기 · 오류 표시.
/// 지우기 같은 위험한 동작은 없다. 일괄 올리기만 확인을 한 번 받는다(서버가 멱등이라 여러 번 눌러도 된다).
class RecordsSiteScreen extends StatefulWidget {
  final RecordsUploader? uploader;
  const RecordsSiteScreen({super.key, this.uploader});

  @override
  State<RecordsSiteScreen> createState() => _RecordsSiteScreenState();
}

class _RecordsSiteScreenState extends State<RecordsSiteScreen> {
  final _url = TextEditingController();
  final _key = TextEditingController();
  bool? _enabled;
  bool _showKey = false;

  RecordsUploader get _up => widget.uploader ?? recordsUploader;

  @override
  void initState() {
    super.initState();
    RecordsSettings.load().then((c) {
      if (!mounted) return;
      setState(() {
        _enabled = c.enabled;
        _url.text = c.baseUrl;
        _key.text = c.storeKey;
      });
    });
    _up.refreshStatus();
  }

  @override
  void dispose() {
    _url.dispose();
    _key.dispose();
    super.dispose();
  }

  RecordsConfig get _config => RecordsConfig(enabled: _enabled ?? false, baseUrl: _url.text, storeKey: _key.text);

  Future<void> _flush() async {
    final r = await _up.flush();
    if (!mounted) return;
    final msg = r.disabled
        ? '꺼져 있습니다'
        : r.error == null
            ? (r.sent == 0 ? '올릴 대국이 없습니다' : '${r.sent}개 올렸습니다')
            : '${r.sent}개 올림 · ${r.error}';
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  Future<void> _uploadAll() async {
    final n = gameStore.history.where((g) => g.finished).length;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => kioskWrap(ctx, AlertDialog(
        title: const Text('지난 대국을 모두 올릴까요?'),
        content: Text('지난 대국 $n개를 기록 사이트에 올립니다. 이미 올린 대국은 서버에서 그대로 둡니다(바뀐 것만 고쳐 씀).'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('아니오')),
          FilledButton(
              key: const ValueKey('records-upload-all-ok'),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('올리기')),
        ],
      )),
    );
    if (ok != true || !mounted) return;
    await _up.enqueueAllHistory();
    await _flush();
  }

  static String _time(DateTime d) =>
      '${d.month}/${d.day} ${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';

  @override
  Widget build(BuildContext context) {
    final text = kioskTextTheme(context);
    final enabled = _enabled;
    return kioskWrap(context, Scaffold(
      appBar: AppBar(title: const Text('기록 사이트')),
      body: kioskPage(context, enabled == null
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.symmetric(vertical: 8),
              children: [
                SwitchListTile(
                  key: const ValueKey('records-enabled'),
                  title: const Text('끝난 대국 올리기'),
                  subtitle: const Text('대국이 끝나면 결과 · 국별 기록 · 패보를 기록 사이트에 올림. 인터넷이 없으면 쌓아 두었다가 다음에'),
                  value: enabled,
                  onChanged: (v) {
                    setState(() => _enabled = v);
                    RecordsSettings.setEnabled(v);
                  },
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
                  child: TextField(
                    key: const ValueKey('records-url'),
                    controller: _url,
                    keyboardType: TextInputType.url,
                    autocorrect: false,
                    decoration: const InputDecoration(labelText: '주소', hintText: recordsDefaultBaseUrl, border: OutlineInputBorder()),
                    onChanged: (v) {
                      setState(() {});
                      RecordsSettings.setBaseUrl(v);
                    },
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
                  child: TextField(
                    key: const ValueKey('records-key'),
                    controller: _key,
                    obscureText: !_showKey,
                    autocorrect: false,
                    enableSuggestions: false,
                    decoration: InputDecoration(
                      labelText: '매장 키',
                      helperText: '관리자 화면에서 발급한 키',
                      border: const OutlineInputBorder(),
                      suffixIcon: IconButton(
                        tooltip: _showKey ? '가리기' : '보기',
                        icon: Icon(_showKey ? Icons.visibility_off : Icons.visibility),
                        onPressed: () => setState(() => _showKey = !_showKey),
                      ),
                    ),
                    onChanged: (v) {
                      setState(() {});
                      RecordsSettings.setStoreKey(v);
                    },
                  ),
                ),
                if (enabled && _config.problem != null)
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: Text(_config.problem!, style: text.bodyMedium?.copyWith(color: Theme.of(context).colorScheme.error)),
                  ),
                ValueListenableBuilder<RecordsStatus>(
                  valueListenable: _up.status,
                  builder: (context, s, _) {
                    final busy = s.running || !enabled || _config.problem != null;
                    return Padding(
                      padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '대기 중 ${s.pending}개'
                            '${s.running ? ' · 올리는 중…' : ''}'
                            '${s.lastSuccessAt != null ? ' · 마지막 성공 ${_time(s.lastSuccessAt!)}' : ''}',
                            key: const ValueKey('records-status'),
                            style: text.bodyLarge,
                          ),
                          if (s.lastError != null)
                            Padding(
                              padding: const EdgeInsets.only(top: 4),
                              child: Text('마지막 오류: ${s.lastError}',
                                  key: const ValueKey('records-error'),
                                  style: text.bodyMedium?.copyWith(color: Theme.of(context).colorScheme.error)),
                            ),
                          const SizedBox(height: 12),
                          Wrap(
                            spacing: 12,
                            runSpacing: 8,
                            children: [
                              FilledButton.icon(
                                key: const ValueKey('records-flush'),
                                icon: const Icon(Icons.cloud_upload_outlined),
                                label: const Text('지금 올리기'),
                                onPressed: busy ? null : _flush,
                              ),
                              OutlinedButton.icon(
                                key: const ValueKey('records-upload-all'),
                                icon: const Icon(Icons.history),
                                label: const Text('지난 대국 모두 올리기'),
                                onPressed: busy ? null : _uploadAll,
                              ),
                            ],
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ],
            ), maxWidth: 820),
    ));
  }
}
