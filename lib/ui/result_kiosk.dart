part of 'result_screen.dart';

/// 키오스크(태블릿 가로) 화료 연출 화면. 작혼 화료 화면의 배치·분위기를 따른다(캐릭터·그림·글꼴은 안 씀, 2026-10-27 사용자).
///
/// 폭 1280 캔버스(높이는 화면 비율대로, 16:9 면 720)에 그리고 화면에 맞춰 키운다. 위쪽 것은 위에서, 아래쪽 것은
/// 아래에서 잰 자리라 16:10 태블릿에서도 띠가 화면 끝까지 차고 배치가 같다.
/// 바탕: 남색 + 파란 사선 띠(위아래 구리색 줄, 옅은 꽃무늬). 위: 손패(화료패는 떼어 둠) + 오른쪽 위 론/쯔모 도장.
/// 그 아래 붓 글씨 이름표의 도라·뒷도라 줄(빈 자리는 뒷면). 가운데: 역이 붓 밑줄 + 판 동그라미로 두 줄에 지그재그,
/// 판·부 큰 원. 아래 왼쪽 큰 등급 글씨(하네만…), 오른쪽 큰 점수, 맨 아래 오른쪽 작은 버튼들.
extension _KioskResult on _ResultScreenState {
  static const _w = 1280.0;
  static const _base = Color(0xFF111A2C);
  static const _gold = Color(0xFFF2C14E);
  static const _seal = Color(0xFFC8102E);

  Widget _kioskBody(BuildContext context) {
    final n = result.yaku.length;
    final stamp = result.isYakuman ? _yakumanTotal(result) : result.limit.label;

    return Theme(
      data: kioskDarkTheme().copyWith(scaffoldBackgroundColor: _base),
      child: Scaffold(
        body: GestureDetector(
          behavior: HitTestBehavior.translucent,
          // 아무 데나 누르면 연출을 건너뛴다.
          onTap: _reveal.isCompleted ? null : _skip,
          child: LayoutBuilder(
            builder: (context, box) => FittedBox(
              child: SizedBox(
                width: _w,
                height: (_w * box.maxHeight / box.maxWidth).clamp(600.0, 960.0),
                child: Stack(
                  clipBehavior: Clip.none,
                  children: [
                    const Positioned.fill(child: CustomPaint(painter: _BandPainter())),
                    _topBar(context),
                    Positioned(left: 150, top: 70, right: 170, child: _handRow()),
                    Positioned(right: 48, top: 44, child: _sealMark(widget.isTsumo ? '쯔모' : '론')),
                    ..._doraRows(),
                    ..._yakuRows(n),
                    Positioned(left: 690, top: 300, child: _fadeIn(n, _hanFuCircle())),
                    if (stamp.isNotEmpty)
                      Positioned(
                        left: 70,
                        bottom: 18,
                        child: _fadeIn(n + 1, _gradeText(stamp), stamp: true),
                      ),
                    Positioned(right: 56, bottom: 92, child: _fadeIn(n + 1, _scoreBlock(context))),
                    Positioned(right: 40, bottom: 22, child: _buttons(context)),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  /// 왼쪽 위: 뒤로, 화료자·국, 확인할 것.
  Widget _topBar(BuildContext context) {
    final g = _game;
    return Positioned(
      left: 12,
      top: 8,
      width: 560,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              IconButton(
                icon: const Icon(Icons.arrow_back, color: Colors.white70),
                onPressed: () => Navigator.of(context).maybePop(),
              ),
              if (g != null && _winner != null)
                Text(
                  '${g.names[_winner!]} · ${g.roundLabel}',
                  style: const TextStyle(fontSize: 18, color: Colors.white70, fontWeight: FontWeight.w600),
                ),
            ],
          ),
          if (widget.flags.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(left: 12),
              child: Text(
                '확인할 것: ${widget.flags.join(' / ')}',
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 14, color: Color(0xFFFFB74D)),
              ),
            ),
        ],
      ),
    );
  }

  /// 손패: 화료패를 뺀 나머지를 정렬해 늘어놓고, 화료패는 오른쪽에 떼어 둔다. 그 뒤에 울기. 칸에 맞게 패 크기를 줄인다.
  Widget _handRow() {
    final hand = widget.hand;
    final d = result.decomposition;
    if (hand == null) {
      // 손패 없이 계산(천화·지화)이면 분해만 보여 준다.
      if (d == null || d.sets.isEmpty) return const SizedBox(height: 8);
      return Wrap(
        spacing: 10,
        children: [for (final s in d.sets) TileRow(s.tiles, width: 50, open: !s.isClosedKan)],
      );
    }
    final rest = List.of(hand.closedTiles)..sort();
    final i = rest.indexOf(hand.winTile);
    if (i >= 0) rest.removeAt(i);
    final count = rest.length + 1 + hand.melds.fold<int>(0, (s, m) => s + m.tiles.length);
    final gaps = 28.0 + 22 * hand.melds.length;
    final tw = ((_w - 320 - gaps) / count - 2).clamp(30.0, 58.0);
    return FittedBox(
      alignment: Alignment.centerLeft,
      fit: BoxFit.scaleDown,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          for (final t in rest) Padding(padding: const EdgeInsets.only(right: 2), child: TileView(t, width: tw)),
          const SizedBox(width: 28),
          TileView(hand.winTile, width: tw, highlighted: true),
          for (final m in hand.melds) ...[
            const SizedBox(width: 22),
            TileRow(m.tiles, width: tw * 0.9, open: m.isOpen),
          ],
        ],
      ),
    );
  }

  /// 도라 줄(왼쪽)과 뒷도라 줄(오른쪽, 리치 화료이거나 뒷도라가 있을 때).
  List<Widget> _doraRows() {
    final sit = widget.situation;
    if (sit == null) return const [];
    final ura = sit.riichi || sit.doubleRiichi || sit.uraIndicators.isNotEmpty;
    return [
      Positioned(left: 300, top: 196, child: _doraRow('도라', sit.doraIndicators)),
      if (ura) Positioned(left: 760, top: 166, child: _doraRow('뒷도라', sit.uraIndicators)),
    ];
  }

  /// 붓 이름표 + 표시패 + 남은 자리는 뒷면(5칸).
  Widget _doraRow(String label, List<int> tiles) {
    const tw = 38.0;
    return Row(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        CustomPaint(
          painter: const _BrushPainter(color: Color(0xFFB3122A)),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(18, 4, 14, 4),
            child: Text(label, style: _brushStyle(22)),
          ),
        ),
        const SizedBox(width: 8),
        for (final t in tiles) Padding(padding: const EdgeInsets.only(right: 2), child: TileView(t, width: tw)),
        for (var k = tiles.length; k < 5; k++)
          const Padding(padding: EdgeInsets.only(right: 2), child: _TileBack(width: tw)),
      ],
    );
  }

  /// 역 줄: 왼쪽 칸에 먼저(최대 4줄 기준), 넘치면 판·부 원 오른쪽 칸으로. 줄마다 조금씩 어긋나게(지그재그).
  List<Widget> _yakuRows(int n) {
    final leftCount = n <= 4 ? n : (n + 1) ~/ 2;
    final rightCount = n - leftCount;
    final rows = leftCount > rightCount ? leftCount : rightCount;
    final step = rows <= 4 ? 64.0 : 256.0 / rows;
    final scale = (step / 64).clamp(0.62, 1.0);
    const zig = [0.0, -34.0, -14.0, 30.0];
    return [
      for (var i = 0; i < n; i++)
        () {
          final right = i >= leftCount;
          final row = right ? i - leftCount : i;
          final top = (right ? 250.0 : 290.0) + step * row;
          final edge = (right ? 1150.0 : 640.0) + (right ? 26.0 * row : zig[row % zig.length]);
          return Positioned(
            right: _w - edge,
            top: top,
            child: _fadeIn(i, _yakuRow(result.yaku[i], scale)),
          );
        }(),
    ];
  }

  /// 역 이름(붓 밑줄) + 판 동그라미.
  Widget _yakuRow(YakuHan y, double scale) {
    final yakuman = y.yaku.isYakuman;
    final d = 54.0 * scale;
    return Row(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        CustomPaint(
          painter: const _BrushPainter(color: Color(0xCC0B1222), underline: true),
          child: Padding(
            padding: EdgeInsets.fromLTRB(60 * scale, 2, 18 * scale, 8 * scale),
            child: Text(y.yaku.label, style: _brushStyle(30 * scale)),
          ),
        ),
        const SizedBox(width: 6),
        Container(
          width: d,
          height: d,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: const Color(0xFF0B0F1A),
            border: Border.all(color: Colors.white24, width: 1.5),
            boxShadow: const [BoxShadow(color: Color(0x66000000), blurRadius: 6)],
          ),
          child: yakuman
              ? Text(_hanLabel(y),
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 13 * scale, height: 1.1, fontWeight: FontWeight.w900, color: _gold))
              : Text.rich(
                  TextSpan(children: [
                    TextSpan(text: '${y.han}', style: TextStyle(fontSize: 28 * scale, fontWeight: FontWeight.w900)),
                    TextSpan(text: '판', style: TextStyle(fontSize: 12 * scale, fontWeight: FontWeight.w800)),
                  ]),
                  style: const TextStyle(color: _gold, height: 1),
                ),
        ),
      ],
    );
  }

  /// 판·부 큰 원(부는 원 왼쪽 아래). 역만이면 원 안에 "역만".
  Widget _hanFuCircle() {
    final yakuman = result.isYakuman;
    return SizedBox(
      width: 210,
      height: 170,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Positioned(
            left: 40,
            top: 0,
            child: Container(
              width: 160,
              height: 160,
              alignment: Alignment.center,
              decoration: const BoxDecoration(
                shape: BoxShape.circle,
                gradient: RadialGradient(colors: [Color(0xFF151B2A), Color(0xEE05070D)]),
                boxShadow: [BoxShadow(color: Color(0x88000000), blurRadius: 18, spreadRadius: 2)],
              ),
              child: yakuman
                  ? Text(
                      _yakumanTotal(result),
                      textAlign: TextAlign.center,
                      style: const TextStyle(fontSize: 34, height: 1.1, fontWeight: FontWeight.w900, color: _gold),
                    )
                  : Text.rich(
                      TextSpan(children: [
                        TextSpan(text: '${result.han}', style: const TextStyle(fontSize: 76)),
                        const TextSpan(text: '판', style: TextStyle(fontSize: 30)),
                      ]),
                      style: const TextStyle(color: _gold, fontWeight: FontWeight.w900, height: 1),
                    ),
            ),
          ),
          if (!yakuman)
            Positioned(
              left: -18,
              top: 96,
              child: Text(
                '${result.fu.total}부',
                style: const TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.w800,
                  color: Colors.white,
                  shadows: [Shadow(color: Colors.black, blurRadius: 6)],
                ),
              ),
            ),
        ],
      ),
    );
  }

  /// 큰 등급 글씨: 검은 테두리 + 빨강→주황 그라데이션.
  Widget _gradeText(String stamp) {
    final size = stamp.length >= 5 ? 92.0 : 124.0;
    // 줄 높이를 꽉 맞추면(1.0) 글자 아래 끝이 그라데이션 칠 바깥으로 나가 흰 조각이 남는다.
    final style = TextStyle(fontSize: size, height: 1.3, fontWeight: FontWeight.w900, letterSpacing: 6);
    return Transform.rotate(
      angle: -0.04,
      child: Stack(
        children: [
          Text(
            stamp,
            style: style.copyWith(
              foreground: Paint()
                ..style = PaintingStyle.stroke
                ..strokeWidth = 12
                ..strokeJoin = StrokeJoin.round
                ..color = const Color(0xFF1A0505),
            ),
          ),
          ShaderMask(
            shaderCallback: (r) => const LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [Color(0xFFFF7A3C), Color(0xFFE0262B), Color(0xFF9E0D18)],
              stops: [0, 0.55, 1],
            ).createShader(r),
            child: Text(stamp, key: const ValueKey('result-stamp'), style: style.copyWith(color: Colors.white)),
          ),
        ],
      ),
    );
  }

  /// 큰 점수 + 지불 내역(+ 함께 론한 사람).
  Widget _scoreBlock(BuildContext context) {
    final p = result.payment;
    const shadow = [
      Shadow(color: Color(0xFF0A0F1C), offset: Offset(4, 5), blurRadius: 0),
      Shadow(color: Color(0x99000000), blurRadius: 18),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Text.rich(
          TextSpan(children: [
            TextSpan(text: '${p.total}', style: const TextStyle(fontSize: 112)),
            const TextSpan(text: '점', style: TextStyle(fontSize: 56)),
          ]),
          style: const TextStyle(
            height: 1,
            fontWeight: FontWeight.w900,
            fontStyle: FontStyle.italic,
            color: Colors.white,
            letterSpacing: 2,
            fontFeatures: [FontFeature.tabularFigures()],
            shadows: shadow,
          ),
        ),
        const SizedBox(height: 4),
        Text(_paymentLine(p), style: const TextStyle(fontSize: 20, color: Colors.white70)),
        if (_others.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(
              '${_others.length >= 2 ? '트리플론' : '더블론'}: '
              '${_others.map((o) => '${_game!.names[o.seat]} ${o.result.isValid ? '${_ronOf(o.seat, o.result.basePoints).ron}점' : o.result.error}').join(' · ')}',
              key: const ValueKey('result-other-wins'),
              style: const TextStyle(fontSize: 18, color: _gold, fontWeight: FontWeight.w700),
            ),
          ),
      ],
    );
  }

  /// 맨 아래 오른쪽 작은 버튼들(작혼의 "확인" 상자처럼). 자동 반영 중이면 그 줄.
  Widget _buttons(BuildContext context) {
    final g = _game;
    final style = OutlinedButton.styleFrom(
      foregroundColor: Colors.white,
      backgroundColor: const Color(0xE61B2640),
      side: const BorderSide(color: Color(0xFF5B6F99)),
      minimumSize: const Size(0, 50),
      padding: const EdgeInsets.symmetric(horizontal: 18),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
      textStyle: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
    );
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (widget.onFix != null) ...[
          OutlinedButton.icon(
            key: const ValueKey('result-fix'),
            style: style,
            icon: const Icon(Icons.edit_outlined, size: 20),
            label: const Text('판독 수정'),
            onPressed: widget.onFix,
          ),
          const SizedBox(width: 10),
        ],
        OutlinedButton(style: style, onPressed: () => _showDetails(context), child: const Text('부수·점수 이동')),
        const SizedBox(width: 10),
        if (_autoActive)
          _autoBar(kiosk: true)
        else
          OutlinedButton.icon(
            style: style.copyWith(
              backgroundColor: const WidgetStatePropertyAll(Color(0xFF2B3D66)),
              side: const WidgetStatePropertyAll(BorderSide(color: _gold, width: 1.5)),
            ),
            icon: Icon(g != null ? Icons.scoreboard_outlined : Icons.check, size: 22),
            label: Text(g != null ? '대국에 반영 (${g.roundLabel})' : '확인'),
            onPressed: g != null ? () => _record(context) : () => Navigator.of(context).maybePop(),
          ),
      ],
    );
  }

  /// 오른쪽 위 붉은 꽃 도장(론/쯔모).
  Widget _sealMark(String text) {
    return SizedBox(
      width: 96,
      height: 96,
      child: CustomPaint(
        painter: const _FlowerPainter(color: _seal),
        child: Center(
          child: Text(
            text,
            style: TextStyle(
              fontSize: text.length > 1 ? 24 : 32,
              fontWeight: FontWeight.w900,
              color: const Color(0xFF3A0008),
            ),
          ),
        ),
      ),
    );
  }

  TextStyle _brushStyle(double size) => TextStyle(
        fontSize: size,
        height: 1.1,
        fontWeight: FontWeight.w800,
        color: Colors.white,
        letterSpacing: 1,
        shadows: const [Shadow(color: Color(0xCC000000), blurRadius: 4, offset: Offset(1, 2))],
      );

  /// 부수 내역과 네 자리 점수 이동판을 시트로.
  Future<void> _showDetails(BuildContext context) {
    return showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSheet) => SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _Section(title: '점수 이동', child: _cross(onChanged: () => setSheet(() {}))),
              if (!result.isYakuman)
                _Section(
                  title: '부수',
                  child: Column(
                    children: [
                      for (final f in result.fu.items)
                        Row(children: [Expanded(child: Text(f.label)), Text('${f.fu}부')]),
                      const Divider(),
                      Row(children: [
                        const Expanded(child: Text('합계', style: TextStyle(fontWeight: FontWeight.w600))),
                        Text('${result.fu.total}부', style: const TextStyle(fontWeight: FontWeight.w600)),
                      ]),
                    ],
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// 패 뒷면(도라 빈 자리).
class _TileBack extends StatelessWidget {
  final double width;
  const _TileBack({required this.width});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: width * 1.4,
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFFF6B23C), Color(0xFFE08A1E)],
        ),
        borderRadius: BorderRadius.circular(width * 0.14),
        border: Border.all(color: const Color(0xFFB86A12)),
        boxShadow: const [BoxShadow(color: Color(0x55000000), blurRadius: 3, offset: Offset(0, 2))],
      ),
    );
  }
}

/// 바탕: 남색 + 파란 사선 띠(위아래 구리색 줄) + 띠 안의 옅은 꽃무늬. 폭 1280 기준, 아래 경계는 아래에서 잰다.
class _BandPainter extends CustomPainter {
  const _BandPainter();

  // 띠 위 경계: (0, 385) → (1280, 45), 아래 경계: (300, 바닥) → (1280, 바닥-250).
  static double _top(double x) => 385 - 0.2656 * x;
  static double _bottom(double x, double h) => h - 0.2551 * (x - 300);

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width, h = size.height;
    canvas.drawRect(
      Offset.zero & size,
      Paint()
        ..shader = const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF0E1626), Color(0xFF1A2540), Color(0xFF0E1424)],
        ).createShader(Offset.zero & size),
    );
    // 위쪽 어두운 파랑(손패 뒤).
    final upper = Path()
      ..moveTo(0, _top(0) - 300)
      ..lineTo(w, _top(w) - 300)
      ..lineTo(w, _top(w))
      ..lineTo(0, _top(0))
      ..close();
    canvas.drawPath(upper, Paint()..color = const Color(0x5523365A));

    final band = Path()
      ..moveTo(0, _top(0))
      ..lineTo(w, _top(w))
      ..lineTo(w, _bottom(w, h))
      ..lineTo(300, h)
      ..lineTo(0, h)
      ..close();
    canvas.drawPath(
      band,
      Paint()
        ..shader = const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFF3D5F94), Color(0xFF2C4876)],
        ).createShader(Offset.zero & size),
    );
    canvas.save();
    canvas.clipPath(band);
    const flowers = [
      (60.0, 520.0, 70.0), (210.0, 430.0, 46.0), (130.0, 660.0, 52.0), (420.0, 330.0, 40.0),
      (560.0, 470.0, 64.0), (700.0, 250.0, 54.0), (860.0, 520.0, 44.0), (980.0, 330.0, 70.0),
      (1120.0, 200.0, 50.0), (1220.0, 420.0, 60.0), (330.0, 600.0, 36.0), (760.0, 400.0, 30.0),
    ];
    for (final (x, y, r) in flowers) {
      // 720 기준 자리: 아래 절반은 바닥에서 잰다.
      final yy = y > 360 ? h - (720 - y) : y;
      _FlowerPainter.drawFlower(canvas, Offset(x, yy), r, const Color(0x2E9DC3F2));
    }
    canvas.restore();

    // 아래쪽 어두운 남색(점수 뒤).
    final lower = Path()
      ..moveTo(300, h)
      ..lineTo(w, _bottom(w, h))
      ..lineTo(w, h)
      ..close();
    canvas.drawPath(lower, Paint()..color = const Color(0xFF151D30));

    final copper = Paint()
      ..color = const Color(0xFFC9773A)
      ..strokeWidth = 7;
    canvas.drawLine(Offset(0, _top(0)), Offset(w, _top(w)), copper);
    canvas.drawLine(Offset(300, h), Offset(w, _bottom(w, h)), copper..strokeWidth = 9);
  }

  @override
  bool shouldRepaint(_BandPainter old) => false;
}

/// 꽃잎 다섯 장 꽃(바탕 무늬·도장).
class _FlowerPainter extends CustomPainter {
  final Color color;
  const _FlowerPainter({required this.color});

  static void drawFlower(Canvas canvas, Offset c, double r, Color color) {
    final paint = Paint()..color = color;
    final path = Path();
    for (var k = 0; k < 5; k++) {
      final a = -math.pi / 2 + k * 2 * math.pi / 5;
      final p = c + Offset(math.cos(a), math.sin(a)) * r * 0.52;
      path.addOval(Rect.fromCircle(center: p, radius: r * 0.5));
    }
    path.addOval(Rect.fromCircle(center: c, radius: r * 0.45));
    canvas.drawPath(path, paint);
  }

  @override
  void paint(Canvas canvas, Size size) {
    drawFlower(canvas, size.center(Offset.zero), size.shortestSide / 2, color);
  }

  @override
  bool shouldRepaint(_FlowerPainter old) => old.color != color;
}

/// 붓 자국: [underline] 이면 글자 아래로 얇아지는 밑줄, 아니면 글자 뒤 두툼한 띠.
class _BrushPainter extends CustomPainter {
  final Color color;
  final bool underline;
  const _BrushPainter({required this.color, this.underline = false});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..color = color;
    final w = size.width, h = size.height;
    final path = Path();
    if (underline) {
      // 왼쪽 끝은 가늘게, 오른쪽은 두툼하게 끝나는 밑줄(글자 아래 1/3).
      final y = h * 0.78;
      path
        ..moveTo(0, y + 2)
        ..quadraticBezierTo(w * 0.4, y - h * 0.10, w, y - h * 0.16)
        ..lineTo(w - 2, y + h * 0.14)
        ..quadraticBezierTo(w * 0.45, y + h * 0.14, 0, y + 4)
        ..close();
    } else {
      path
        ..moveTo(w * 0.06, h * 0.22)
        ..quadraticBezierTo(w * 0.5, h * 0.02, w, h * 0.12)
        ..lineTo(w * 0.94, h * 0.9)
        ..quadraticBezierTo(w * 0.45, h * 1.02, 0, h * 0.8)
        ..close();
    }
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(_BrushPainter old) => old.color != color || old.underline != underline;
}
