part of 'input_screen.dart';

/// 키오스크(태블릿 가로) 점수 계산 화면.
/// 왼쪽은 패 판과 상황(어두운 바탕), 오른쪽은 담은 패(손패·울기·도라)와 큰 계산 버튼.
/// 오른쪽 칸(손패·도라 표시패·뒷도라)을 누르면 그 칸이 패 판의 입력 대상이 된다.
class _KioskInput extends StatelessWidget {
  final HandEditor editor;
  final VoidCallback onCalculate;
  final void Function(String menu) onOpen;
  const _KioskInput({required this.editor, required this.onCalculate, required this.onOpen});

  @override
  Widget build(BuildContext context) {
    final game = gameStore.current;
    final canPop = Navigator.of(context).canPop();
    Widget menu(String value, IconData icon, String label) => TextButton.icon(
          style: TextButton.styleFrom(
            foregroundColor: Colors.white70,
            padding: const EdgeInsets.symmetric(horizontal: 12),
            minimumSize: const Size(0, 48),
          ),
          icon: Icon(icon, size: 20),
          label: Text(label, style: const TextStyle(fontSize: 15)),
          onPressed: () => onOpen(value),
        );
    return Theme(
      data: kioskDarkTheme(),
      child: Scaffold(
        appBar: AppBar(
          toolbarHeight: 64,
          title: Text(game == null ? '마작 점수 계산기' : '점수 계산 · ${game.roundLabel}'),
          // 테이블 화면에서 열었으면 왼쪽 위 뒤로 가기로 돌아간다. 첫 화면이면 메뉴를 늘어놓는다.
          leadingWidth: canPop ? 56 : 0,
          actions: [
            if (!canPop) ...[
              menu('game', Icons.scoreboard_outlined, '대국'),
              menu('table', Icons.table_chart_outlined, '점수표'),
              menu('quiz', Icons.school_outlined, '연습'),
              menu('settings', Icons.tune, '룰 설정'),
              PopupMenuButton<String>(
                tooltip: '더보기',
                onSelected: onOpen,
                itemBuilder: (_) => [
                  PopupMenuItem(
                    value: 'mount',
                    enabled: game != null,
                    child: Text(game != null ? '거치 촬영' : '거치 촬영 (대국 기록 중에만)'),
                  ),
                  const PopupMenuItem(value: 'head', child: Text('카메라 헤드 (다른 기기에서 조작)')),
                ],
              ),
            ],
            const SizedBox(width: 8),
          ],
        ),
        body: SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(
                  child: SingleChildScrollView(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        _KioskPalette(editor: editor),
                        const SizedBox(height: 12),
                        _KioskSituation(editor: editor),
                      ],
                    ),
                  ),
                ),
                const SizedBox(width: 16),
                SizedBox(
                  width: 400,
                  // 오른쪽 담은 패 칸은 밝은 바탕이라 앱 기본 테마로 그린다.
                  child: Theme(
                    data: Theme.of(context),
                    child: _KioskCart(editor: editor, onCalculate: onCalculate),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

BoxDecoration _kioskBox() => BoxDecoration(
      color: Colors.white.withValues(alpha: 0.05),
      borderRadius: BorderRadius.circular(16),
      border: Border.all(color: Colors.white12),
    );

/// 34종을 한눈에(종류별 한 줄). 적도라를 쓰면 수패 줄 끝에 적5.
class _KioskPalette extends StatelessWidget {
  final HandEditor editor;
  const _KioskPalette({required this.editor});

  static const _suits = [('만수', 0), ('통수', 9), ('삭수', 18)];

  @override
  Widget build(BuildContext context) {
    final e = editor;
    return LayoutBuilder(
      builder: (context, c) {
        const gap = 8.0;
        const labelW = 56.0;
        // 한 줄에 9장 + 적5(간격 조금 더) 가 들어가게.
        final width = ((c.maxWidth - 32 - labelW - gap * 10 - 8) / 10).clamp(40.0, 70.0);
        Widget tile(int t, {bool red = false}) {
          final reason = e.cannotAdd(t, red: red);
          return TileView(
            t,
            key: ValueKey(red ? 'palette-red-$t' : 'palette-$t'),
            red: red,
            width: width,
            dimmed: reason != null,
            onTap: () => reason != null ? _toast(context, reason) : e.add(t, red: red),
          );
        }

        Widget row(String label, List<Widget> tiles, {Widget? red}) => Padding(
              padding: const EdgeInsets.only(bottom: gap),
              child: Row(
                children: [
                  SizedBox(
                    width: labelW,
                    child: Text(label,
                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: kioskGold)),
                  ),
                  for (final t in tiles) Padding(padding: const EdgeInsets.only(right: gap), child: t),
                  if (red != null) Padding(padding: const EdgeInsets.only(left: 8), child: red),
                ],
              ),
            );

        final target = switch (e.target) {
          InputTarget.hand => '손패',
          InputTarget.dora => '도라 표시패',
          InputTarget.ura => '뒷도라 표시패',
        };
        return Container(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
          decoration: _kioskBox(),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Text.rich(
                  TextSpan(children: [
                    const TextSpan(text: '누르면 '),
                    TextSpan(
                      text: target,
                      style: const TextStyle(color: kioskGold, fontWeight: FontWeight.w700),
                    ),
                    TextSpan(text: e.target == InputTarget.hand ? '에 넣습니다' : '에 넣습니다 (실제 도라는 다음 패)'),
                  ]),
                  style: const TextStyle(fontSize: 15, color: Colors.white70),
                ),
              ),
              for (final (label, base) in _suits)
                row(
                  label,
                  [for (var n = 0; n < 9; n++) tile(base + n)],
                  red: e.rules.redDora ? tile(base + 4, red: true) : null,
                ),
              row('자패', [for (var t = Tiles.east; t <= Tiles.red; t++) tile(t)]),
            ],
          ),
        );
      },
    );
  }
}

/// 상황 입력을 가로로 촘촘하게.
class _KioskSituation extends StatelessWidget {
  final HandEditor editor;
  const _KioskSituation({required this.editor});

  @override
  Widget build(BuildContext context) {
    final e = editor;
    final game = gameStore.current;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: _kioskBox(),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (game != null) ...[
            _GameSeatPicker(editor: e, game: game),
            const SizedBox(height: 12),
          ],
          Wrap(
            spacing: 24,
            runSpacing: 10,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              SegmentedButton<bool>(
                showSelectedIcon: false,
                segments: const [
                  ButtonSegment(value: false, label: Text('론', style: TextStyle(fontSize: 16))),
                  ButtonSegment(value: true, label: Text('쯔모', style: TextStyle(fontSize: 16))),
                ],
                selected: {e.isTsumo},
                onSelectionChanged: (s) => e.setTsumo(s.first),
              ),
              _WindPicker(label: '자풍', value: e.seatWind, winds: _SituationSection._winds, onChanged: e.setSeatWind),
              _WindPicker(label: '장풍', value: e.roundWind, winds: _SituationSection._winds, onChanged: e.setRoundWind),
              _HonbaStepper(editor: e),
            ],
          ),
          const SizedBox(height: 10),
          Wrap(spacing: 8, runSpacing: 6, children: _situationChips(e)),
        ],
      ),
    );
  }
}

/// 오른쪽 담은 패 칸 + 계산 버튼(키오스크의 주문 내역 자리).
class _KioskCart extends StatelessWidget {
  final HandEditor editor;
  final VoidCallback onCalculate;
  const _KioskCart({required this.editor, required this.onCalculate});

  @override
  Widget build(BuildContext context) {
    final e = editor;
    final outline = Theme.of(context).colorScheme.outline;
    final waits = e.closed.length == e.maxClosed - 1;
    final winIdx = e.effectiveWinIndex;
    final win = e.winTile;
    final hint = TextStyle(fontSize: 13, color: outline);

    // Material 로 감싸야 글자색도 밝은 테마 기본값이 된다(바깥은 어두운 테마).
    return Material(
      color: kioskPanel,
      borderRadius: BorderRadius.circular(16),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Expanded(
            child: ListView(
              padding: const EdgeInsets.all(12),
              children: [
                _CartSection(
                  title: '손패 ${e.closed.length}/${e.maxClosed}',
                  active: e.target == InputTarget.hand,
                  onTap: () => e.setTarget(InputTarget.hand),
                  trailing: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      TextButton.icon(
                        key: const ValueKey('photo-input'),
                        style: _compactButton,
                        icon: const Icon(Icons.photo_camera_outlined, size: 18),
                        label: const Text('사진'),
                        onPressed: () => showPhotoInput(context, e),
                      ),
                      TextButton.icon(
                        style: _compactButton,
                        icon: const Icon(Icons.call_split, size: 18),
                        label: const Text('부르기'),
                        onPressed: e.melds.length >= 4 ? null : () => showMeldSheet(context, e),
                      ),
                    ],
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (e.closed.isEmpty)
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          child: Text(
                            e.firstTurnWinOnly
                                ? '${e.isDealer ? '천화' : '지화'}는 손패 없이 바로 계산합니다'
                                : '왼쪽 패 판에서 패를 눌러 넣으세요',
                            style: hint,
                          ),
                        )
                      else ...[
                        Wrap(
                          spacing: 4,
                          runSpacing: 6,
                          children: [
                            for (var i = 0; i < e.closed.length; i++)
                              TileView(
                                e.closed[i].tile,
                                red: e.closed[i].red,
                                width: 44,
                                highlighted: i == winIdx && !e.firstTurnWin,
                                uncertain: e.uncertain.contains(i),
                                onTap: () => e.removeClosedAt(i),
                                onLongPress: () => e.setWin(i),
                              ),
                          ],
                        ),
                        const SizedBox(height: 6),
                        Text(
                          e.firstTurnWin
                              ? '화료패는 고르지 않아도 됩니다 (탭: 빼기)'
                              : '화료패 ${Tiles.name(win!.tile)} · 탭: 빼기 · 길게: 화료패',
                          style: hint,
                        ),
                      ],
                      if (e.melds.isNotEmpty) ...[
                        const SizedBox(height: 10),
                        Wrap(
                          spacing: 8,
                          runSpacing: 6,
                          children: [
                            for (var i = 0; i < e.melds.length; i++)
                              _MeldChip(meld: e.melds[i], red: e.meldRed[i], onDelete: () => e.removeMeldAt(i)),
                          ],
                        ),
                      ],
                    ],
                  ),
                ),
                _CartSection(
                  title: '도라 표시패',
                  active: e.target == InputTarget.dora,
                  onTap: () => e.setTarget(InputTarget.dora),
                  child: _indicators(e.doraIndicators, e.removeDoraAt, hint, '눌러서 고른 뒤 패 판에서 넣으세요'),
                ),
                _CartSection(
                  title: '뒷도라 표시패',
                  active: e.target == InputTarget.ura,
                  // 멘젠이면 누를 수 있고, 누르면 리치가 같이 켜진다(HandEditor.setTarget).
                  enabled: e.isClosed,
                  onTap: () => e.setTarget(InputTarget.ura),
                  child: _indicators(e.uraIndicators, e.removeUraAt, hint,
                      e.hasRiichi ? '리치 화료일 때만' : (e.isClosed ? '누르면 리치도 켭니다' : '울면 뒷도라가 없습니다')),
                ),
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
            decoration: const BoxDecoration(border: Border(top: BorderSide(color: Color(0xFFE3DDD2)))),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(_situationSummary(e), style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
                const SizedBox(height: 12),
                Row(
                  children: [
                    SizedBox(
                      width: 76,
                      height: 76,
                      child: FilledButton(
                        style: FilledButton.styleFrom(
                          backgroundColor: kioskRed,
                          shape: const CircleBorder(),
                          padding: EdgeInsets.zero,
                        ),
                        onPressed: e.closed.isEmpty && e.melds.isEmpty ? null : e.clear,
                        child: const Text('전부\n지우기', textAlign: TextAlign.center, style: TextStyle(fontSize: 13)),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: SizedBox(
                        height: 76,
                        child: FilledButton.icon(
                          style: FilledButton.styleFrom(
                            backgroundColor: kioskGoldDeep,
                            foregroundColor: Colors.white,
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                          ),
                          icon: Icon(waits ? Icons.search : Icons.calculate_outlined, size: 28),
                          label: Text(waits ? '대기패 보기' : '점수 계산', style: const TextStyle(fontSize: 22)),
                          onPressed: onCalculate,
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _indicators(List<int> tiles, void Function(int) onRemove, TextStyle hint, String empty) {
    if (tiles.isEmpty) return Text(empty, style: hint);
    return Wrap(
      spacing: 4,
      children: [
        for (var i = 0; i < tiles.length; i++) TileView(tiles[i], width: 36, onTap: () => onRemove(i)),
      ],
    );
  }

  static String _situationSummary(HandEditor e) => [
        e.isTsumo ? '쯔모' : '론',
        '${Tiles.name(e.roundWind)}장 ${Tiles.name(e.seatWind)}가',
        if (e.doubleRiichi)
          '더블 리치'
        else if (e.riichi)
          '리치',
        if (e.ippatsu) '일발',
        if (e.honba > 0) '${e.honba}본장',
      ].join(' · ');
}

/// 담은 패 칸 하나. 누르면 그 칸이 입력 대상이 되고 금색 테두리가 생긴다.
class _CartSection extends StatelessWidget {
  final String title;
  final bool active;
  final bool enabled;
  final VoidCallback onTap;
  final Widget? trailing;
  final Widget child;
  const _CartSection({
    required this.title,
    required this.active,
    required this.onTap,
    required this.child,
    this.enabled = true,
    this.trailing,
  });

  @override
  Widget build(BuildContext context) {
    final radius = BorderRadius.circular(12);
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Opacity(
        opacity: enabled ? 1 : 0.45,
        child: Material(
          color: Colors.white,
          borderRadius: radius,
          child: InkWell(
            borderRadius: radius,
            onTap: enabled ? onTap : null,
            child: Container(
              padding: const EdgeInsets.fromLTRB(12, 8, 8, 12),
              decoration: BoxDecoration(
                borderRadius: radius,
                border: Border.all(
                  color: active ? kioskGoldDeep : const Color(0xFFE3DDD2),
                  width: active ? 2.5 : 1,
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      if (active) const Icon(Icons.arrow_right, color: kioskGoldDeep),
                      Expanded(
                        child: Text(title, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
                      ),
                      ?trailing,
                    ],
                  ),
                  const SizedBox(height: 6),
                  child,
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
