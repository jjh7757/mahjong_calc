import 'package:flutter/gestures.dart' show DragStartBehavior;
import 'package:flutter/material.dart';

import '../../table/grid_zones.dart';
import '../../table/table_layout.dart';

/// 미리보기(촬영 사진과 같은 좌표계) 위에 격자 5구역(자리 4 + 가운데)을 겹쳐 그린다.
/// [editing] 이면 경계선 네 개를 끌어 옮길 수 있다. 선은 바람개비 모양이라 각각 한쪽 끝까지만 그어진다.
class GridOverlay extends StatefulWidget {
  final GridZones grid;
  final bool editing;
  final ValueChanged<GridZones>? onChanged;
  const GridOverlay({super.key, required this.grid, this.editing = false, this.onChanged});

  @override
  State<GridOverlay> createState() => _GridOverlayState();
}

/// 끌고 있는 선.
enum _Handle { x1, x2, y1, y2 }

/// 선분(0~1000 좌표): 고정 좌표와 뻗는 범위.
({bool vertical, int at, int from, int to}) _segment(GridZones g, _Handle h) => switch (h) {
      _Handle.x1 => (vertical: true, at: g.x1, from: g.y1, to: 1000),
      _Handle.x2 => (vertical: true, at: g.x2, from: 0, to: g.y2),
      _Handle.y1 => (vertical: false, at: g.y1, from: 0, to: g.x2),
      _Handle.y2 => (vertical: false, at: g.y2, from: g.x1, to: 1000),
    };

class _GridOverlayState extends State<GridOverlay> {
  _Handle? _drag;
  Offset? _start;
  GridZones? _startGrid;

  /// 손가락이 닿았다고 볼 거리(px).
  static const double _touch = 28;

  /// 선 사이 최소 간격(0~1000).
  static const int _gap = 40;

  _Handle? _hit(Offset p, Size size) {
    double best = _touch;
    _Handle? hit;
    for (final h in _Handle.values) {
      final s = _segment(widget.grid, h);
      final (along, across, scaleAlong, scaleAcross) =
          s.vertical ? (p.dy, p.dx, size.height, size.width) : (p.dx, p.dy, size.width, size.height);
      final a0 = s.from * scaleAlong / 1000, a1 = s.to * scaleAlong / 1000;
      final da = along < a0 ? a0 - along : (along > a1 ? along - a1 : 0.0);
      final dc = (across - s.at * scaleAcross / 1000).abs();
      final d = da > dc ? da : dc;
      if (d < best) {
        best = d;
        hit = h;
      }
    }
    return hit;
  }

  GridZones _move(GridZones g, _Handle h, int dx, int dy) {
    int c(int v, int lo, int hi) => v.clamp(lo, hi < lo ? lo : hi);
    return switch (h) {
      _Handle.x1 => g.copyWith(x1: c(g.x1 + dx, 1, g.x2 - _gap)),
      _Handle.x2 => g.copyWith(x2: c(g.x2 + dx, g.x1 + _gap, 999)),
      _Handle.y1 => g.copyWith(y1: c(g.y1 + dy, 1, g.y2 - _gap)),
      _Handle.y2 => g.copyWith(y2: c(g.y2 + dy, g.y1 + _gap, 999)),
    };
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, box) {
      final size = box.biggest;
      final paint = CustomPaint(painter: _GridPainter(widget.grid, editing: widget.editing), size: size);
      if (!widget.editing) return IgnorePointer(child: paint);
      return GestureDetector(
        behavior: HitTestBehavior.opaque,
        // 잡은 곳은 손가락이 처음 닿은 자리로 판정한다(움직이기 시작한 자리면 선에서 벗어날 수 있다).
        dragStartBehavior: DragStartBehavior.down,
        onPanStart: (d) {
          _drag = _hit(d.localPosition, size);
          _start = d.localPosition;
          _startGrid = widget.grid;
        },
        // 시작할 때 격자에 지금까지 끈 거리를 한 번에 더한다. 프레임 사이에 갱신이 여러 번 와도
        // (부모가 아직 다시 그리지 않아 widget.grid 가 옛값이어도) 움직임을 잃지 않는다.
        onPanUpdate: (d) {
          final h = _drag, start = _start, g = _startGrid;
          if (h == null || start == null || g == null) return;
          final dx = ((d.localPosition.dx - start.dx) * 1000 / size.width).round();
          final dy = ((d.localPosition.dy - start.dy) * 1000 / size.height).round();
          widget.onChanged?.call(_move(g, h, dx, dy));
        },
        onPanEnd: (_) => _drag = null,
        child: paint,
      );
    });
  }
}

class _GridPainter extends CustomPainter {
  final GridZones grid;
  final bool editing;
  _GridPainter(this.grid, {required this.editing});

  @override
  void paint(Canvas canvas, Size size) {
    double sx(int v) => v * size.width / 1000;
    double sy(int v) => v * size.height / 1000;
    final line = Paint()
      ..color = (editing ? Colors.cyanAccent : Colors.white).withValues(alpha: editing ? 0.95 : 0.55)
      ..strokeWidth = editing ? 3 : 1.5;
    for (final h in _Handle.values) {
      final s = _segment(grid, h);
      final (a, b) = s.vertical
          ? (Offset(sx(s.at), sy(s.from)), Offset(sx(s.at), sy(s.to)))
          : (Offset(sx(s.from), sy(s.at)), Offset(sx(s.to), sy(s.at)));
      canvas.drawLine(a, b, line);
    }
    if (!editing) return;
    void label(String text, Offset at) {
      final tp = TextPainter(
        text: TextSpan(
          text: text,
          style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w600, backgroundColor: Colors.black54),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, at - Offset(tp.width / 2, tp.height / 2));
    }

    Offset mid(NormBox n) => Offset(sx((n.xmin + n.xmax) ~/ 2), sy((n.ymin + n.ymax) ~/ 2));
    for (final s in Side.values) {
      label('${s.label} 자리 (손패+울기)', mid(grid.seat(s)));
    }
    label('가운데 (강 끝·리치봉·도라)', mid(grid.center));
  }

  @override
  bool shouldRepaint(_GridPainter old) => old.grid != grid || old.editing != editing;
}
