import 'dart:math' as math;

import 'package:flutter/gestures.dart' show DragStartBehavior;
import 'package:flutter/material.dart';

import '../../table/grid_zones.dart';
import '../../table/table_layout.dart';

/// 미리보기(촬영 사진과 같은 좌표계) 위에 격자 5구역(자리 4 + 가운데)을 겹쳐 그린다.
/// [editing] 이면 경계선 네 개를 끌어 옮길 수 있다. 선은 바람개비 모양이라 각각 한쪽 끝까지만 그어진다.
/// [dealer](선 자리)를 주면 선 기준 도라 구역([GridZones.doraZone])을 주황 상자로 그린다. 편집 중엔 상자 안을 끌어 옮기고
/// 오른쪽 아래 모서리를 끌어 크기를 바꾼다(선이 다른 자리로 가면 상자도 그 자리 쪽으로 돌아간다).
/// [wallBox](그 판의 왕패 상자, 판 시작 때 찾은 것)가 있으면 선 기준 구역 대신 그것을 그리고, 편집 중에 끌어 고칠 수
/// 있다([onWallChanged]). 편집 중이 아니면 어떤 터치도 받지 않는다(잘못 터치 방지, 2026-10-29 "편집 on/off" 결정).
/// 격자에 리치봉 상자([GridZones.sticks])가 있으면 빨간 상자로 그린다. 편집 중엔 안을 끌어 옮기고, 모서리로 크기를 바꾸고,
/// 위쪽 동그라미를 끌어 돌린다(기운 탁자의 기기에 맞추기).
class GridOverlay extends StatefulWidget {
  final GridZones grid;
  final bool editing;
  final Side? dealer;
  final NormBox? wallBox;
  final ValueChanged<GridZones>? onChanged;
  final ValueChanged<NormBox>? onWallChanged;
  const GridOverlay({
    super.key,
    required this.grid,
    this.editing = false,
    this.dealer,
    this.wallBox,
    this.onChanged,
    this.onWallChanged,
  });

  @override
  State<GridOverlay> createState() => _GridOverlayState();
}

/// 끌고 있는 선.
enum _Handle { x1, x2, y1, y2 }

/// 도라 상자를 끄는 방식.
enum _DoraDrag { move, resize }

/// 리치봉 상자를 끄는 방식.
enum _StickDrag { move, resize, rotate }

/// 리치봉 상자의 화면 좌표: 한가운데, 폭, 높이, 각도(라디안).
typedef _StickGeom = ({Offset c, double w, double h, double a});

_StickGeom? _stickGeom(GridZones g, Size size) {
  final b = g.sticks;
  if (b == null) return null;
  return (
    c: Offset((b.xmin + b.xmax) / 2 * size.width / 1000, (b.ymin + b.ymax) / 2 * size.height / 1000),
    w: b.width * size.width / 1000,
    h: b.height * size.height / 1000,
    a: g.sticksAngle * math.pi / 180,
  );
}

Offset _rot(Offset v, double a) => Offset(v.dx * math.cos(a) - v.dy * math.sin(a), v.dx * math.sin(a) + v.dy * math.cos(a));

/// 돌리는 손잡이(상자 위쪽 변에서 바깥으로 이만큼, px).
const double _knobGap = 26;

/// 선분(0~1000 좌표): 고정 좌표와 뻗는 범위.
({bool vertical, int at, int from, int to}) _segment(GridZones g, _Handle h) => switch (h) {
      _Handle.x1 => (vertical: true, at: g.x1, from: g.y1, to: 1000),
      _Handle.x2 => (vertical: true, at: g.x2, from: 0, to: g.y2),
      _Handle.y1 => (vertical: false, at: g.y1, from: 0, to: g.x2),
      _Handle.y2 => (vertical: false, at: g.y2, from: g.x1, to: 1000),
    };

class _GridOverlayState extends State<GridOverlay> {
  _Handle? _drag;
  _DoraDrag? _doraDrag;
  _StickDrag? _stickDrag;
  NormBox? _startBox;
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

  /// 도라 상자: 오른쪽 아래 모서리 가까이면 크기, 상자 안이면 옮기기. 선을 먼저 잡는다(상자가 선에 걸쳐 있어서).
  String get _doraLabel => widget.wallBox != null ? '도라 산' : '도라 (선 ${widget.dealer?.label ?? ''})';

  /// 지금 그리는 도라 상자: 그 판의 왕패 상자, 없으면 선 기준 구역.
  NormBox? get _doraBox {
    final dealer = widget.dealer;
    return widget.wallBox ?? (dealer == null ? null : widget.grid.doraZone(dealer));
  }

  _DoraDrag? _hitDora(Offset p, Size size) {
    final b = _doraBox;
    if (b == null) return null;
    final corner = Offset(b.xmax * size.width / 1000, b.ymax * size.height / 1000);
    if ((p - corner).distance < _touch) return _DoraDrag.resize;
    if (widget.editing && _hit(p, size) != null) return null;
    final x = p.dx * 1000 / size.width, y = p.dy * 1000 / size.height;
    return x >= b.xmin && x <= b.xmax && y >= b.ymin && y <= b.ymax ? _DoraDrag.move : null;
  }

  NormBox _moveBox(NormBox b, _DoraDrag d, int dx, int dy) {
    if (d == _DoraDrag.move) {
      final mx = dx.clamp(-b.xmin, 1000 - b.xmax), my = dy.clamp(-b.ymin, 1000 - b.ymax);
      return NormBox(b.ymin + my, b.xmin + mx, b.ymax + my, b.xmax + mx);
    }
    return NormBox(b.ymin, b.xmin, (b.ymax + dy).clamp(b.ymin + _gap, 1000), (b.xmax + dx).clamp(b.xmin + _gap, 1000));
  }

  /// 리치봉 상자: 돌리는 손잡이 → 모서리(크기) → 상자 안(옮기기). 편집 중에만.
  _StickDrag? _hitSticks(Offset p, Size size) {
    final s = _stickGeom(widget.grid, size);
    if (s == null || !widget.editing) return null;
    final knob = s.c + _rot(Offset(0, -s.h / 2 - _knobGap), s.a);
    if ((p - knob).distance < _touch) return _StickDrag.rotate;
    final corner = s.c + _rot(Offset(s.w / 2, s.h / 2), s.a);
    if ((p - corner).distance < _touch) return _StickDrag.resize;
    final local = _rot(p - s.c, -s.a);
    return local.dx.abs() <= s.w / 2 && local.dy.abs() <= s.h / 2 ? _StickDrag.move : null;
  }

  GridZones _moveSticks(GridZones g, _StickDrag d, Offset start, Offset now, Size size) {
    final s = _stickGeom(g, size)!;
    var c = s.c, w = s.w, h = s.h, deg = g.sticksAngle;
    switch (d) {
      case _StickDrag.move:
        c = s.c + (now - start);
      case _StickDrag.resize: // 한가운데는 두고 돌린 축 방향으로 양쪽을 같이
        final l = _rot(now - start, -s.a);
        w = math.max(20, s.w + 2 * l.dx);
        h = math.max(20, s.h + 2 * l.dy);
      case _StickDrag.rotate:
        final v = now - s.c;
        deg = (math.atan2(v.dx, -v.dy) * 180 / math.pi).round();
    }
    int nx(double x) => (x * 1000 / size.width).round().clamp(0, 1000);
    int ny(double y) => (y * 1000 / size.height).round().clamp(0, 1000);
    return g.copyWith(
      sticks: NormBox(ny(c.dy - h / 2), nx(c.dx - w / 2), ny(c.dy + h / 2), nx(c.dx + w / 2)),
      sticksAngle: deg,
    );
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
      final paint = CustomPaint(
        painter: _GridPainter(widget.grid, editing: widget.editing, doraBox: _doraBox, doraLabel: _doraLabel),
        size: size,
      );
      if (!widget.editing) return IgnorePointer(child: paint);
      return GestureDetector(
        behavior: HitTestBehavior.opaque,
        // 잡은 곳은 손가락이 처음 닿은 자리로 판정한다(움직이기 시작한 자리면 선에서 벗어날 수 있다).
        dragStartBehavior: DragStartBehavior.down,
        onPanStart: (d) {
          _stickDrag = _hitSticks(d.localPosition, size);
          _doraDrag = _stickDrag == null ? _hitDora(d.localPosition, size) : null;
          _drag = _stickDrag == null && _doraDrag == null && widget.editing ? _hit(d.localPosition, size) : null;
          _startBox = _doraBox;
          _start = d.localPosition;
          _startGrid = widget.grid;
        },
        // 시작할 때 격자에 지금까지 끈 거리를 한 번에 더한다. 프레임 사이에 갱신이 여러 번 와도
        // (부모가 아직 다시 그리지 않아 widget.grid 가 옛값이어도) 움직임을 잃지 않는다.
        onPanUpdate: (d) {
          final h = _drag, dd = _doraDrag, sd = _stickDrag, start = _start, g = _startGrid;
          if ((h == null && dd == null && sd == null) || start == null || g == null) return;
          if (sd != null) {
            widget.onChanged?.call(_moveSticks(g, sd, start, d.localPosition, size));
            return;
          }
          final dx = ((d.localPosition.dx - start.dx) * 1000 / size.width).round();
          final dy = ((d.localPosition.dy - start.dy) * 1000 / size.height).round();
          if (dd != null) {
            final moved = _moveBox(_startBox!, dd, dx, dy);
            if (widget.wallBox != null) {
              widget.onWallChanged?.call(moved);
            } else {
              widget.onChanged?.call(g.withDoraZone(widget.dealer!, moved));
            }
          } else {
            widget.onChanged?.call(_move(g, h!, dx, dy));
          }
        },
        onPanEnd: (_) {
          _drag = null;
          _doraDrag = null;
          _stickDrag = null;
        },
        child: paint,
      );
    });
  }
}

class _GridPainter extends CustomPainter {
  final GridZones grid;
  final bool editing;
  final NormBox? doraBox;
  final String doraLabel;
  _GridPainter(this.grid, {required this.editing, this.doraBox, this.doraLabel = ''});

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
    final st = _stickGeom(grid, size);
    if (st != null) {
      final red = Paint()
        ..style = PaintingStyle.stroke
        ..color = Colors.redAccent.withValues(alpha: editing ? 0.95 : 0.5)
        ..strokeWidth = editing ? 3 : 1.5;
      canvas.save();
      canvas.translate(st.c.dx, st.c.dy);
      canvas.rotate(st.a);
      canvas.drawRect(Rect.fromCenter(center: Offset.zero, width: st.w, height: st.h), red);
      if (editing) {
        final fill = Paint()..color = Colors.redAccent;
        canvas.drawRect(Rect.fromCenter(center: Offset(st.w / 2, st.h / 2), width: 16, height: 16), fill);
        canvas.drawLine(Offset(0, -st.h / 2), Offset(0, -st.h / 2 - _knobGap), red);
        canvas.drawCircle(Offset(0, -st.h / 2 - _knobGap), 9, fill);
      }
      canvas.restore();
    }
    final dora = doraBox;
    if (dora != null) {
      final r = Rect.fromLTRB(sx(dora.xmin), sy(dora.ymin), sx(dora.xmax), sy(dora.ymax));
      canvas.drawRect(
        r,
        Paint()
          ..style = PaintingStyle.stroke
          ..color = Colors.orangeAccent.withValues(alpha: editing ? 0.95 : 0.6)
          ..strokeWidth = editing ? 3 : 1.5,
      );
      if (editing || doraLabel == '도라 산') {
        canvas.drawRect(Rect.fromCenter(center: r.bottomRight, width: 16, height: 16), Paint()..color = Colors.orangeAccent);
      }
    }
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
    // 그 판의 왕패 상자는 편집 중이 아니어도 이름을 단다(끌어 고칠 수 있는 상자라서).
    if (!editing) {
      if (dora != null && doraLabel == '도라 산') label(doraLabel, mid(dora));
      return;
    }
    for (final s in Side.values) {
      label('${s.label} 자리 (손패+울기)', mid(grid.seat(s)));
    }
    label(grid.sticks == null ? '가운데 (강 끝·리치봉·도라)' : '가운데 (패산·강·도라)', mid(grid.center));
    if (st != null) label('리치봉', st.c + Offset(0, st.h / 2 + 12));
    if (dora != null) label(doraLabel, mid(dora));
  }

  @override
  bool shouldRepaint(_GridPainter old) =>
      old.grid != grid || old.editing != editing || old.doraBox != doraBox || old.doraLabel != doraLabel;
}
