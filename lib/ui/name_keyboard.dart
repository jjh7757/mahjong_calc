import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'kiosk.dart';

/// 이름 칸을 누르면 뜨는 앱 안 키보드(두벌식 한글 · 영문 · 숫자). 기기 키보드 없이 터치만으로 이름을 고친다.
/// 확인하면 새 이름, 취소하면 null. [replaceOnType] 이면 처음 누른 글자가 기존 이름을 지우고 들어간다(기본 이름용).
Future<String?> showNameKeyboard(BuildContext context,
    {required String title, required String initial, bool replaceOnType = false}) {
  return showAdaptiveSheet<String>(
    context,
    kioskMaxWidth: 820,
    builder: (_) => _NameKeyboard(title: title, initial: initial, replaceOnType: replaceOnType),
  );
}

/// 누른 키(자모·글자) 목록에서 글자를 조합한다. 지우기는 마지막 키 하나를 지운다("한" → "하" → "ㅎ").
/// 처음부터 있던 글자는 한 글자씩 지워진다.
class NameComposer {
  NameComposer([String initial = '']) : _keys = initial.split('');

  static const maxLength = 12;

  final List<String> _keys;

  String get text => _compose(_keys);

  /// [key] 를 넣는다. 이름이 [maxLength] 를 넘게 되면 넣지 않고 false.
  bool type(String key) {
    _keys.add(key);
    if (text.length > maxLength) {
      _keys.removeLast();
      return false;
    }
    return true;
  }

  void backspace() {
    if (_keys.isNotEmpty) _keys.removeLast();
  }

  void clear() => _keys.clear();

  static const _cho = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ';
  static const _jung = 'ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ';
  // 0 번은 받침 없음.
  static const _jong = ' ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ';
  static const _vowelPairs = {
    'ㅗㅏ': 'ㅘ', 'ㅗㅐ': 'ㅙ', 'ㅗㅣ': 'ㅚ', 'ㅜㅓ': 'ㅝ', 'ㅜㅔ': 'ㅞ', 'ㅜㅣ': 'ㅟ', 'ㅡㅣ': 'ㅢ', //
  };
  static const _jongPairs = {
    'ㄱㅅ': 'ㄳ', 'ㄴㅈ': 'ㄵ', 'ㄴㅎ': 'ㄶ', 'ㄹㄱ': 'ㄺ', 'ㄹㅁ': 'ㄻ', 'ㄹㅂ': 'ㄼ', //
    'ㄹㅅ': 'ㄽ', 'ㄹㅌ': 'ㄾ', 'ㄹㅍ': 'ㄿ', 'ㄹㅎ': 'ㅀ', 'ㅂㅅ': 'ㅄ',
  };

  static bool _isConsonant(String k) => k.length == 1 && _cho.contains(k);
  static bool _isVowel(String k) => k.length == 1 && _jung.contains(k);

  static String _compose(List<String> keys) {
    final out = StringBuffer();
    String? cho;
    String? jung;
    var jong = <String>[]; // 겹받침이면 두 개(모음이 오면 뒤의 것이 다음 글자로 넘어간다).
    void flush() {
      if (cho != null && jung != null) {
        final j = jong.isEmpty ? 0 : _jong.indexOf(jong.length == 2 ? _jongPairs[jong.join()]! : jong[0]);
        out.writeCharCode(0xAC00 + (_cho.indexOf(cho!) * 21 + _jung.indexOf(jung!)) * 28 + j);
      } else if (cho != null) {
        out.write(cho);
      } else if (jung != null) {
        out.write(jung);
      }
      cho = null;
      jung = null;
      jong = [];
    }

    for (final k in keys) {
      if (_isConsonant(k)) {
        if (cho != null && jung != null) {
          // ㄸ·ㅃ·ㅉ 은 받침이 될 수 없다.
          if (jong.isEmpty && _jong.contains(k)) {
            jong = [k];
            continue;
          }
          if (jong.length == 1 && _jongPairs.containsKey(jong[0] + k)) {
            jong.add(k);
            continue;
          }
        }
        flush();
        cho = k;
      } else if (_isVowel(k)) {
        if (jong.isNotEmpty) {
          final moved = jong.removeLast();
          flush();
          cho = moved;
          jung = k;
        } else if (jung != null && _vowelPairs.containsKey(jung! + k)) {
          jung = _vowelPairs[jung! + k];
        } else if (cho != null && jung == null) {
          jung = k;
        } else {
          flush();
          jung = k;
        }
      } else {
        flush();
        out.write(k);
      }
    }
    flush();
    return out.toString();
  }
}

const _korRows = ['ㅂㅈㄷㄱㅅㅛㅕㅑㅐㅔ', 'ㅁㄴㅇㄹㅎㅗㅓㅏㅣ', 'ㅋㅌㅊㅍㅠㅜㅡ'];
const _engRows = ['qwertyuiop', 'asdfghjkl', 'zxcvbnm'];
const _korShift = {'ㅂ': 'ㅃ', 'ㅈ': 'ㅉ', 'ㄷ': 'ㄸ', 'ㄱ': 'ㄲ', 'ㅅ': 'ㅆ', 'ㅐ': 'ㅒ', 'ㅔ': 'ㅖ'};

class _NameKeyboard extends StatefulWidget {
  const _NameKeyboard({required this.title, required this.initial, required this.replaceOnType});

  final String title;
  final String initial;
  final bool replaceOnType;

  @override
  State<_NameKeyboard> createState() => _NameKeyboardState();
}

class _NameKeyboardState extends State<_NameKeyboard> {
  late final _composer = NameComposer(widget.initial);
  late bool _replace = widget.replaceOnType && widget.initial.isNotEmpty;
  bool _korean = true;
  bool _shift = false;

  String get _text => _composer.text;

  void _type(String k) {
    setState(() {
      if (_replace) _composer.clear();
      _replace = false;
      _composer.type(k);
      _shift = false;
    });
  }

  void _backspace() {
    setState(() {
      if (_replace) _composer.clear();
      _replace = false;
      _composer.backspace();
    });
  }

  void _clear() {
    setState(() {
      _replace = false;
      _composer.clear();
    });
  }

  void _done() {
    final t = _text.trim();
    if (t.isNotEmpty) Navigator.of(context).pop(t);
  }

  /// 붙은 실제 키보드(노트북·블루투스)로도 영문·숫자를 칠 수 있게.
  KeyEventResult _onKey(FocusNode _, KeyEvent e) {
    if (e is! KeyDownEvent && e is! KeyRepeatEvent) return KeyEventResult.ignored;
    if (e.logicalKey == LogicalKeyboardKey.backspace) {
      _backspace();
      return KeyEventResult.handled;
    }
    if (e.logicalKey == LogicalKeyboardKey.enter || e.logicalKey == LogicalKeyboardKey.numpadEnter) {
      _done();
      return KeyEventResult.handled;
    }
    final c = e.character;
    if (c != null && c.length == 1 && c.codeUnitAt(0) >= 0x20) {
      _type(c);
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final text = _text;
    final rows = _korean ? _korRows : _engRows;
    String label(String k) {
      if (!_shift) return k;
      return _korean ? (_korShift[k] ?? k) : k.toUpperCase();
    }

    Widget keys(String row) => Row(children: [
          for (final k in row.split('')) _Key(flex: 2, label: label(k), onTap: () => _type(label(k))),
        ]);

    return Focus(
      autofocus: true,
      onKeyEvent: _onKey,
      child: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 12),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(widget.title, style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 10),
              Container(
                key: const ValueKey('name-kb-preview'),
                padding: const EdgeInsets.only(left: 16),
                decoration: BoxDecoration(
                  border: Border.all(color: scheme.primary, width: 2),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Container(
                        alignment: Alignment.centerLeft,
                        child: Text(
                          text.isEmpty ? '이름' : text,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 28,
                            fontWeight: FontWeight.w600,
                            color: text.isEmpty ? scheme.outline : scheme.onSurface,
                            backgroundColor: _replace ? scheme.primary.withValues(alpha: 0.3) : null,
                          ),
                        ),
                      ),
                    ),
                    IconButton(
                      key: const ValueKey('name-kb-clear'),
                      tooltip: '모두 지우기',
                      iconSize: 28,
                      onPressed: text.isEmpty ? null : _clear,
                      icon: const Icon(Icons.cancel),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              keys('1234567890'),
              keys(rows[0]),
              Row(children: [
                const Spacer(),
                for (final k in rows[1].split('')) _Key(flex: 2, label: label(k), onTap: () => _type(label(k))),
                const Spacer(),
              ]),
              Row(children: [
                _Key(
                  flex: 3,
                  icon: _shift ? Icons.keyboard_capslock : Icons.arrow_upward,
                  highlight: _shift,
                  onTap: () => setState(() => _shift = !_shift),
                ),
                for (final k in rows[2].split('')) _Key(flex: 2, label: label(k), onTap: () => _type(label(k))),
                _Key(key: const ValueKey('name-kb-backspace'), flex: 3, icon: Icons.backspace_outlined, onTap: _backspace),
              ]),
              Row(children: [
                _Key(
                  key: const ValueKey('name-kb-lang'),
                  flex: 4,
                  label: _korean ? 'ABC' : '한글',
                  onTap: () => setState(() {
                    _korean = !_korean;
                    _shift = false;
                  }),
                ),
                _Key(flex: 16, icon: Icons.space_bar, onTap: () => _type(' ')),
              ]),
              const SizedBox(height: 12),
              Row(
                children: [
                  TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('취소')),
                  const Spacer(),
                  FilledButton(
                    key: const ValueKey('name-kb-done'),
                    onPressed: text.trim().isEmpty ? null : _done,
                    style: FilledButton.styleFrom(minimumSize: const Size(140, 52)),
                    child: const Text('확인', style: TextStyle(fontSize: 18)),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Key extends StatelessWidget {
  const _Key({super.key, required this.flex, this.label, this.icon, this.highlight = false, required this.onTap});

  final int flex;
  final String? label;
  final IconData? icon;
  final bool highlight;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Expanded(
      flex: flex,
      child: Padding(
        padding: const EdgeInsets.all(3),
        child: Material(
          color: highlight ? scheme.primaryContainer : scheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(8),
          child: InkWell(
            borderRadius: BorderRadius.circular(8),
            onTap: onTap,
            child: SizedBox(
              height: 54,
              child: Center(
                child: icon != null
                    ? Icon(icon, size: 24)
                    : Text(label!, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w500)),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
