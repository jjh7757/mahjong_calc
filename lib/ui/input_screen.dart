import 'package:flutter/material.dart';

import '../engine/calculator.dart';
import '../game/game.dart';
import '../game/game_store.dart';
import 'hand_editor.dart';
import 'game/game_screen.dart';
import 'kiosk.dart';
import 'meld_sheet.dart';
import 'mount/camera_head_screen.dart';
import 'mount/capture_label.dart';
import 'photo_input.dart';
import 'quiz_screen.dart';
import 'result_screen.dart';
import 'score_table_screen.dart';
import 'settings_screen.dart';
import 'survey_qr.dart';
import 'tile_view.dart';
import 'waits_sheet.dart';

part 'kiosk_input.dart';

/// 패 입력 + 상황 입력 화면.
class InputScreen extends StatelessWidget {
  final HandEditor editor;

  /// 대국 테이블 화면에서 연 계산 화면이면 true: "대국에 반영" 하면 이 화면도 닫고 테이블로 돌아간다.
  final bool popAfterRecord;
  const InputScreen({super.key, required this.editor, this.popAfterRecord = false});

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: Listenable.merge([editor, gameStore]),
      builder: (context, _) {
        // 국이 바뀌었으면 상황 입력을 대국 값으로 채운다(알림 없음).
        editor.syncFromGame(gameStore.current);
        if (isKioskLayout(context)) {
          return _KioskInput(editor: editor, onCalculate: () => _calculate(context), onOpen: (v) => _open(context, v));
        }
        return Scaffold(
          appBar: AppBar(
            title: const Text('마작 점수 계산기'),
            actions: [
              IconButton(
                tooltip: '대국 기록',
                icon: const Icon(Icons.scoreboard_outlined),
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const GameScreen()),
                ),
              ),
              IconButton(
                tooltip: '전부 지우기',
                icon: const Icon(Icons.delete_outline),
                onPressed: editor.closed.isEmpty && editor.melds.isEmpty
                    ? null
                    : editor.clear,
              ),
              PopupMenuButton<String>(
                tooltip: '더보기',
                onSelected: (v) => _open(context, v),
                // 거치 촬영은 대국 중 첫 화면(테이블)이라 여기서 따로 열지 않는다(2026-10-29, 열면 카메라 화면이 두 겹).
                itemBuilder: (_) => [
                  const PopupMenuItem(value: 'head', child: Text('카메라 헤드 (다른 기기에서 조작)')),
                  const PopupMenuItem(value: 'table', child: Text('점수표')),
                  const PopupMenuItem(value: 'quiz', child: Text('점수 계산 연습')),
                  const PopupMenuItem(value: 'settings', child: Text('룰 설정')),
                  const PopupMenuItem(value: 'survey', child: Text('설문 참여 (QR)')),
                ],
              ),
            ],
          ),
          body: SingleChildScrollView(
            padding: EdgeInsets.fromLTRB(12, 8, 12, 16 + MediaQuery.paddingOf(context).bottom),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _HandSection(editor: editor),
                const SizedBox(height: 12),
                _TargetSection(editor: editor),
                const SizedBox(height: 8),
                _Palette(editor: editor),
                const SizedBox(height: 12),
                _SituationSection(editor: editor),
              ],
            ),
          ),
          bottomNavigationBar: SafeArea(
            minimum: const EdgeInsets.fromLTRB(12, 0, 12, 12),
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 16),
              ),
              icon: Icon(editor.closed.length == editor.maxClosed - 1
                  ? Icons.search
                  : Icons.calculate_outlined),
              label: Text(
                editor.closed.length == editor.maxClosed - 1 ? '대기패 보기' : '점수 계산',
                style: const TextStyle(fontSize: 18),
              ),
              onPressed: () => _calculate(context),
            ),
          ),
        );
      },
    );
  }

  /// 메뉴 항목 열기.
  void _open(BuildContext context, String v) {
    if (v == 'survey') {
      showSurveyQr(context);
      return;
    }
    final Widget screen = switch (v) {
      'game' => const GameScreen(),
      'table' => ScoreTableScreen(rules: editor.rules),
      'quiz' => QuizScreen(rules: editor.rules),
      'settings' => SettingsScreen(editor: editor),
      _ => const CameraHeadScreen(),
    };
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));
  }

  Future<void> _calculate(BuildContext context) async {
    if (editor.closed.isEmpty && !editor.firstTurnWinOnly) {
      _toast(context, '손패를 먼저 입력하세요');
      return;
    }
    if (editor.closed.length == editor.maxClosed - 1) {
      showWaitsSheet(context, editor, onPick: (tile, tsumo) {
        // 대기패 한 줄에서 론·쯔모를 고르면 그 패를 넣고 바로 결과로 간다.
        editor.setTarget(InputTarget.hand);
        final reason = editor.cannotAdd(tile);
        if (reason != null) {
          _toast(context, reason);
          return;
        }
        editor.add(tile);
        editor.setTsumo(tsumo);
        _showResult(context);
      });
      return;
    }
    await _showResult(context);
  }

  Future<void> _showResult(BuildContext context) async {
    final result = editor.calculate();
    var recorded = false;
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => ResultScreen(
          result: result,
          hand: editor.hand,
          situation: editor.situation,
          isTsumo: editor.isTsumo,
          seatWind: editor.seatWind,
          gameSeat: editor.gameSeat,
          photoRiichiSeats: Set.of(editor.photoRiichiSeats),
          winnerRiichi: editor.hasRiichi,
          rules: editor.rules,
          onWinRecorded: (o) => saveCaptureLabel(editor, o),
          onSituationChanged: editor.applySituation,
          onRecorded: () {
            editor.clear();
            recorded = true;
          },
        ),
      ),
    );
    if (recorded && popAfterRecord && context.mounted) Navigator.of(context).pop();
  }
}

void _toast(BuildContext context, String message) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(
      content: Text(message),
      duration: const Duration(seconds: 2),
    ));
}

class _SectionTitle extends StatelessWidget {
  final String text;
  final Widget? trailing;
  const _SectionTitle(this.text, {this.trailing});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Text(text,
              style: Theme.of(context).textTheme.titleMedium,
              overflow: TextOverflow.ellipsis),
        ),
        ?trailing,
      ],
    );
  }
}

final ButtonStyle _compactButton = TextButton.styleFrom(
  padding: const EdgeInsets.symmetric(horizontal: 8),
  visualDensity: VisualDensity.compact,
);

class _HandSection extends StatelessWidget {
  final HandEditor editor;
  const _HandSection({required this.editor});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final winIdx = editor.effectiveWinIndex;
    final win = editor.winTile;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _SectionTitle(
              '손패 ${editor.closed.length}/${editor.maxClosed}',
              trailing: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextButton.icon(
                    key: const ValueKey('photo-input'),
                    style: _compactButton,
                    icon: const Icon(Icons.photo_camera_outlined, size: 18),
                    label: const Text('사진'),
                    onPressed: () => showPhotoInput(context, editor),
                  ),
                  TextButton.icon(
                    style: _compactButton,
                    icon: const Icon(Icons.call_split, size: 18),
                    label: const Text('부르기'),
                    onPressed: editor.melds.length >= 4
                        ? null
                        : () => showMeldSheet(context, editor),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 4),
            if (editor.closed.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 16),
                child: Text(
                  editor.firstTurnWinOnly
                      ? '${editor.isDealer ? '천화' : '지화'}는 손패 없이 바로 계산합니다\n(다른 역만이 겹치면 손패를 넣으세요)'
                      : '아래 팔레트에서 패를 눌러 넣으세요',
                  style: TextStyle(color: scheme.outline),
                ),
              )
            else
              Wrap(
                spacing: 4,
                runSpacing: 6,
                children: [
                  for (var i = 0; i < editor.closed.length; i++)
                    TileView(
                      editor.closed[i].tile,
                      red: editor.closed[i].red,
                      width: 40,
                      highlighted: i == winIdx && !editor.firstTurnWin,
                      uncertain: editor.uncertain.contains(i),
                      onTap: () => editor.removeClosedAt(i),
                      onLongPress: () => editor.setWin(i),
                    ),
                ],
              ),
            if (editor.closed.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(
                editor.firstTurnWin
                    ? '화료패는 고르지 않아도 됩니다   (탭: 빼기)'
                    : '화료패: ${Tiles.name(win!.tile)}   (탭: 빼기 · 길게 누르기: 화료패 지정)',
                style: TextStyle(fontSize: 12, color: scheme.outline),
              ),
            ],
            if (editor.melds.isNotEmpty) ...[
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 6,
                children: [
                  for (var i = 0; i < editor.melds.length; i++)
                    _MeldChip(
                      meld: editor.melds[i],
                      red: editor.meldRed[i],
                      onDelete: () => editor.removeMeldAt(i),
                    ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _MeldChip extends StatelessWidget {
  final Meld meld;
  final int red;
  final VoidCallback onDelete;
  const _MeldChip({required this.meld, required this.red, required this.onDelete});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final label = switch (meld.type) {
      MeldType.chi => '치',
      MeldType.pon => '퐁',
      MeldType.kan => meld.isOpen ? '깡' : '안깡',
    };
    return Container(
      padding: const EdgeInsets.fromLTRB(8, 4, 2, 4),
      decoration: BoxDecoration(
        border: Border.all(color: scheme.outlineVariant),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(label, style: const TextStyle(fontSize: 12)),
          const SizedBox(width: 6),
          TileRow(meld.tiles, width: 26, open: meld.isOpen),
          if (red > 0)
            Padding(
              padding: const EdgeInsets.only(left: 4),
              child: Text('적$red', style: const TextStyle(fontSize: 11, color: Color(0xFFD32F2F))),
            ),
          IconButton(
            visualDensity: VisualDensity.compact,
            iconSize: 18,
            icon: const Icon(Icons.close),
            onPressed: onDelete,
          ),
        ],
      ),
    );
  }
}

class _TargetSection extends StatelessWidget {
  final HandEditor editor;
  const _TargetSection({required this.editor});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SegmentedButton<InputTarget>(
          showSelectedIcon: false,
          segments: [
            const ButtonSegment(value: InputTarget.hand, label: Text('손패')),
            const ButtonSegment(value: InputTarget.dora, label: Text('도라 표시패')),
            ButtonSegment(
              value: InputTarget.ura,
              label: const Text('뒷도라'),
              enabled: editor.isClosed,
            ),
          ],
          selected: {editor.target},
          onSelectionChanged: (s) => editor.setTarget(s.first),
        ),
        if (editor.doraIndicators.isNotEmpty || editor.uraIndicators.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Wrap(
              spacing: 12,
              runSpacing: 6,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                if (editor.doraIndicators.isNotEmpty)
                  _IndicatorRow(
                    label: '도라 표시',
                    tiles: editor.doraIndicators,
                    onRemove: editor.removeDoraAt,
                  ),
                if (editor.uraIndicators.isNotEmpty)
                  _IndicatorRow(
                    label: '뒷도라 표시',
                    tiles: editor.uraIndicators,
                    onRemove: editor.removeUraAt,
                  ),
                Text(
                  '표시패를 넣습니다 (실제 도라는 다음 패)',
                  style: TextStyle(fontSize: 11, color: scheme.outline),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class _IndicatorRow extends StatelessWidget {
  final String label;
  final List<int> tiles;
  final void Function(int index) onRemove;
  const _IndicatorRow({required this.label, required this.tiles, required this.onRemove});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('$label ', style: const TextStyle(fontSize: 12)),
        for (var i = 0; i < tiles.length; i++)
          Padding(
            padding: const EdgeInsets.only(right: 2),
            child: TileView(tiles[i], width: 26, onTap: () => onRemove(i)),
          ),
      ],
    );
  }
}

class _Palette extends StatelessWidget {
  final HandEditor editor;
  const _Palette({required this.editor});

  static const _rows = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8],
    [9, 10, 11, 12, 13, 14, 15, 16, 17],
    [18, 19, 20, 21, 22, 23, 24, 25, 26],
    [27, 28, 29, 30, 31, 32, 33],
  ];

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        const gap = 4.0;
        final width = ((constraints.maxWidth - gap * 8) / 9).clamp(24.0, 44.0);
        Widget tileButton(int t, {bool red = false}) {
          final reason = editor.cannotAdd(t, red: red);
          return TileView(
            t,
            key: ValueKey(red ? 'palette-red-$t' : 'palette-$t'),
            red: red,
            width: width,
            dimmed: reason != null,
            onTap: () {
              if (reason != null) {
                _toast(context, reason);
              } else {
                editor.add(t, red: red);
              }
            },
          );
        }

        return Column(
          children: [
            for (final row in _rows)
              Padding(
                padding: const EdgeInsets.only(bottom: gap),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.start,
                  children: [
                    for (var i = 0; i < row.length; i++)
                      Padding(
                        padding: EdgeInsets.only(right: i == row.length - 1 ? 0 : gap),
                        child: tileButton(row[i]),
                      ),
                  ],
                ),
              ),
            if (editor.rules.redDora)
              Row(
                children: [
                  const Padding(
                    padding: EdgeInsets.only(right: 8),
                    child: Text('적도라', style: TextStyle(fontSize: 12)),
                  ),
                  for (final t in [4, 13, 22])
                    Padding(
                      padding: const EdgeInsets.only(right: gap),
                      child: tileButton(t, red: true),
                    ),
                ],
              ),
          ],
        );
      },
    );
  }
}

class _SituationSection extends StatelessWidget {
  final HandEditor editor;
  const _SituationSection({required this.editor});

  static const _winds = [Tiles.east, Tiles.south, Tiles.west, Tiles.north];

  @override
  Widget build(BuildContext context) {
    final e = editor;
    final game = gameStore.current;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const _SectionTitle('상황'),
            const SizedBox(height: 8),
            if (game != null) ...[
              _GameSeatPicker(editor: e, game: game),
              const SizedBox(height: 10),
            ],
            SegmentedButton<bool>(
              showSelectedIcon: false,
              segments: const [
                ButtonSegment(value: false, label: Text('론')),
                ButtonSegment(value: true, label: Text('쯔모')),
              ],
              selected: {e.isTsumo},
              onSelectionChanged: (s) => e.setTsumo(s.first),
            ),
            const SizedBox(height: 12),
            _WindPicker(
              label: '자풍',
              value: e.seatWind,
              winds: _winds,
              onChanged: e.setSeatWind,
            ),
            const SizedBox(height: 6),
            _WindPicker(
              label: '장풍',
              value: e.roundWind,
              winds: _winds,
              onChanged: e.setRoundWind,
            ),
            const SizedBox(height: 10),
            Wrap(spacing: 6, runSpacing: 2, children: _situationChips(e)),
            const SizedBox(height: 10),
            const SizedBox(height: 8),
            _HonbaStepper(editor: e),
          ],
        ),
      ),
    );
  }
}

/// 리치·일발 같은 상황 칩(폰·키오스크 공용).
List<Widget> _situationChips(HandEditor e) => [
    FilterChip(
      label: const Text('리치'),
      selected: e.riichi,
      onSelected: e.isClosed ? e.setRiichi : null,
    ),
    FilterChip(
      label: const Text('더블 리치'),
      selected: e.doubleRiichi,
      onSelected: e.isClosed ? e.setDoubleRiichi : null,
    ),
    FilterChip(
      label: const Text('일발'),
      selected: e.ippatsu,
      onSelected: e.isClosed ? e.setIppatsu : null,
    ),
    FilterChip(
      label: Text(e.isTsumo ? '해저로월' : '하저로어'),
      selected: e.lastTile,
      onSelected: e.setLastTile,
    ),
    FilterChip(
      label: const Text('영상개화'),
      selected: e.rinshan,
      onSelected: e.setRinshan,
    ),
    FilterChip(
      label: const Text('창깡'),
      selected: e.chankan,
      onSelected: e.setChankan,
    ),
    FilterChip(
      label: Text(e.seatWind == Tiles.east ? '천화' : '지화'),
      selected: e.firstTurnWin,
      onSelected: e.melds.isEmpty ? e.setFirstTurnWin : null,
    ),
    ];

class _HonbaStepper extends StatelessWidget {
  final HandEditor editor;
  const _HonbaStepper({required this.editor});

  @override
  Widget build(BuildContext context) {
    final e = editor;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Text('본장'),
        IconButton(
          icon: const Icon(Icons.remove_circle_outline),
          onPressed: e.honba > 0 ? () => e.setHonba(e.honba - 1) : null,
        ),
        Text('${e.honba}', style: const TextStyle(fontSize: 16)),
        IconButton(
          icon: const Icon(Icons.add_circle_outline),
          onPressed: () => e.setHonba(e.honba + 1),
        ),
      ],
    );
  }
}

/// 진행 중인 대국이 있을 때: 이 손패가 누구 것인지 고르면 자풍·장풍·본장·리치가 채워진다.
class _GameSeatPicker extends StatelessWidget {
  final HandEditor editor;
  final Game game;
  const _GameSeatPicker({required this.editor, required this.game});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final g = game;
    final seat = editor.gameSeat;
    return Container(
      padding: const EdgeInsets.fromLTRB(10, 8, 10, 8),
      decoration: BoxDecoration(
        color: scheme.secondaryContainer.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.scoreboard_outlined, size: 16, color: scheme.onSecondaryContainer),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  '대국 ${g.roundLabel}'
                  '${g.riichiSticks > 0 ? ' · 공탁 ${g.riichiSticks}' : ''}'
                  ' - 누구 손패?',
                  style: TextStyle(fontSize: 13, color: scheme.onSecondaryContainer),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6,
            runSpacing: 2,
            children: [
              for (var s = 0; s < 4; s++)
                ChoiceChip(
                  key: ValueKey('game-seat-$s'),
                  label: Text(
                    '${Tiles.name(g.seatWindOf(s))} ${g.names[s]}'
                    '${g.riichiSeats.contains(s) ? ' 리치' : ''}',
                  ),
                  showCheckmark: false,
                  visualDensity: VisualDensity.compact,
                  selected: seat == s,
                  onSelected: (sel) => editor.setGameSeat(g, sel ? s : null),
                ),
            ],
          ),
          if (seat != null)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                '자풍·장풍·본장${g.riichiSeats.contains(seat) ? '·리치' : ''}를 '
                '점수판 값으로 채웠습니다. 아래에서 고칠 수 있습니다.',
                style: TextStyle(fontSize: 11, color: scheme.outline),
              ),
            ),
        ],
      ),
    );
  }
}

class _WindPicker extends StatelessWidget {
  final String label;
  final int value;
  final List<int> winds;
  final void Function(int) onChanged;
  const _WindPicker({
    required this.label,
    required this.value,
    required this.winds,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 6,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        SizedBox(width: 40, child: Text(label)),
        for (final w in winds)
          ChoiceChip(
            label: Text('${Tiles.name(w)}풍'),
            showCheckmark: false,
            padding: const EdgeInsets.symmetric(horizontal: 4),
            labelPadding: const EdgeInsets.symmetric(horizontal: 4),
            selected: value == w,
            onSelected: (_) => onChanged(w),
          ),
      ],
    );
  }
}
