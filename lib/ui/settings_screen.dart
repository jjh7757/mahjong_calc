import 'package:flutter/material.dart';
import 'kiosk.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../engine/calculator.dart';
import '../services/announcer.dart';
import 'hand_editor.dart';

/// 룰 설정을 기기에 저장·복원한다.
class RulesStore {
  static const _kuitan = 'rules.kuitan';
  static const _kiriage = 'rules.kiriageMangan';
  static const _kazoe = 'rules.kazoeYakuman';
  static const _double = 'rules.doubleYakuman';
  static const _windPair = 'rules.doubleWindPairFu';
  static const _red = 'rules.redDora';

  static Future<RuleSet> load() async {
    final p = await SharedPreferences.getInstance();
    const d = RuleSet.standard;
    return RuleSet(
      kuitan: p.getBool(_kuitan) ?? d.kuitan,
      kiriageMangan: p.getBool(_kiriage) ?? d.kiriageMangan,
      kazoeYakuman: p.getBool(_kazoe) ?? d.kazoeYakuman,
      doubleYakuman: p.getBool(_double) ?? d.doubleYakuman,
      doubleWindPairFu: p.getInt(_windPair) ?? d.doubleWindPairFu,
      redDora: p.getBool(_red) ?? d.redDora,
    );
  }

  static Future<void> save(RuleSet r) async {
    final p = await SharedPreferences.getInstance();
    await p.setBool(_kuitan, r.kuitan);
    await p.setBool(_kiriage, r.kiriageMangan);
    await p.setBool(_kazoe, r.kazoeYakuman);
    await p.setBool(_double, r.doubleYakuman);
    await p.setInt(_windPair, r.doubleWindPairFu);
    await p.setBool(_red, r.redDora);
  }
}

/// 거치 촬영 판독이 확실하면 결과 화면에서 10초 뒤 대국에 자동 반영하고 닫을지(기본 켬).
/// 룰 설정과 거치 화면 더보기가 같은 값을 쓴다.
class AutoRecordStore {
  static const key = 'mount.autoRecord';

  static Future<bool> load() async {
    try {
      final p = await SharedPreferences.getInstance();
      // 기본 끔: 자체 모델만 쓰는 판독을 실제 대국에서 확인할 때까지(2026-11-02). 켠 사람의 값은 그대로.
      return p.getBool(key) ?? false;
    } catch (_) {
      return false;
    }
  }

  static Future<void> save(bool on) async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.setBool(key, on);
    } catch (_) {}
  }
}

/// 룰 설정 화면.
class SettingsScreen extends StatelessWidget {
  final HandEditor editor;
  const SettingsScreen({super.key, required this.editor});

  void _update(RuleSet r) {
    editor.setRules(r);
    RulesStore.save(r);
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: editor,
      builder: (context, _) {
        final r = editor.rules;
        return kioskWrap(context, Scaffold(
          appBar: AppBar(title: const Text('룰 설정')),
          body: kioskPage(context, ListView(
            children: [
              const _VoiceSwitch(),
              const _AutoRecordSwitch(),
              const Divider(height: 1),
              SwitchListTile(
                title: const Text('쿠이탄'),
                subtitle: const Text('울고 탕야오 인정'),
                value: r.kuitan,
                onChanged: (v) => _update(r.copyWith(kuitan: v)),
              ),
              SwitchListTile(
                title: const Text('끌어올림 만관'),
                subtitle: const Text('4판 30부, 3판 60부를 만관으로'),
                value: r.kiriageMangan,
                onChanged: (v) => _update(r.copyWith(kiriageMangan: v)),
              ),
              SwitchListTile(
                title: const Text('헤아림 역만'),
                subtitle: const Text('13판 이상을 역만으로'),
                value: r.kazoeYakuman,
                onChanged: (v) => _update(r.copyWith(kazoeYakuman: v)),
              ),
              SwitchListTile(
                title: const Text('더블 역만'),
                subtitle: const Text('국사 13면·사암각 단기·대사희·순정 구련'),
                value: r.doubleYakuman,
                onChanged: (v) => _update(r.copyWith(doubleYakuman: v)),
              ),
              SwitchListTile(
                title: const Text('적도라'),
                subtitle: const Text('적5 사용'),
                value: r.redDora,
                onChanged: (v) => _update(r.copyWith(redDora: v)),
              ),
              ListTile(
                title: const Text('연풍패 머리 부수'),
                subtitle: const Text('자풍과 장풍이 같은 머리'),
                trailing: SegmentedButton<int>(
                  showSelectedIcon: false,
                  segments: const [
                    ButtonSegment(value: 2, label: Text('2부')),
                    ButtonSegment(value: 4, label: Text('4부')),
                  ],
                  selected: {r.doubleWindPairFu},
                  onSelectionChanged: (s) =>
                      _update(r.copyWith(doubleWindPairFu: s.first)),
                ),
              ),
            ],
          ), maxWidth: 820),
        ));
      },
    );
  }
}

/// 자동 반영 켜고 끄기([AutoRecordStore]).
class _AutoRecordSwitch extends StatefulWidget {
  const _AutoRecordSwitch();

  @override
  State<_AutoRecordSwitch> createState() => _AutoRecordSwitchState();
}

class _AutoRecordSwitchState extends State<_AutoRecordSwitch> {
  bool? _on;

  @override
  void initState() {
    super.initState();
    AutoRecordStore.load().then((v) {
      if (mounted) setState(() => _on = v);
    });
  }

  @override
  Widget build(BuildContext context) {
    return SwitchListTile(
      key: const ValueKey('auto-record-switch'),
      title: const Text('판독 후 자동 반영'),
      subtitle: const Text('거치 촬영 판독이 확실하면 결과 화면에서 10초 뒤 대국에 기록하고 테이블로 돌아감. '
          '끄면 "대국에 반영"을 직접 누름'),
      value: _on ?? true,
      onChanged: _on == null
          ? null
          : (v) {
              setState(() => _on = v);
              AutoRecordStore.save(v);
            },
    );
  }
}

/// 결과 화면에서 역을 하나씩 띄우며 소리 내어 읽을지, 어떤 목소리로 읽을지(기기 저장).
/// 목소리를 고르면 그 목소리로 예시를 바로 읽어 준다.
class _VoiceSwitch extends StatefulWidget {
  const _VoiceSwitch();

  @override
  State<_VoiceSwitch> createState() => _VoiceSwitchState();
}

class _VoiceSwitchState extends State<_VoiceSwitch> {
  bool? _on;
  String? _voice;

  @override
  void initState() {
    super.initState();
    Future.wait([Announcer.enabled(), Announcer.voice()]).then((v) {
      if (mounted) {
        setState(() {
          _on = v[0] as bool;
          _voice = v[1] as String;
        });
      }
    });
  }

  @override
  void dispose() {
    Announcer.stop();
    super.dispose();
  }

  Future<void> _pick(String v) async {
    setState(() => _voice = v);
    await Announcer.setVoice(v);
    Announcer.preview();
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SwitchListTile(
          key: const ValueKey('voice-switch'),
          title: const Text('결과 연출·음성'),
          subtitle: const Text('역을 하나씩 띄우며 읽어 줌 (예: 리치, 이페코, 도라 2, 하네만). 끄면 결과를 바로 보여 줌'),
          value: _on ?? false,
          onChanged: _on == null
              ? null
              : (v) {
                  setState(() => _on = v);
                  Announcer.setEnabled(v);
                },
        ),
        if (_on == true && _voice != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text('목소리', style: text.titleSmall),
                    const Spacer(),
                    TextButton.icon(
                      key: const ValueKey('voice-preview'),
                      icon: const Icon(Icons.play_arrow_rounded),
                      label: const Text('미리 듣기'),
                      onPressed: Announcer.preview,
                    ),
                  ],
                ),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final e in {...voiceChoices, deviceVoice: '기기 음성'}.entries)
                      ChoiceChip(
                        key: ValueKey('voice-${e.key}'),
                        label: Text(e.key == deviceVoice ? e.value : '${e.key} · ${e.value}'),
                        selected: _voice == e.key,
                        onSelected: (_) => _pick(e.key),
                      ),
                  ],
                ),
              ],
            ),
          ),
      ],
    );
  }
}
