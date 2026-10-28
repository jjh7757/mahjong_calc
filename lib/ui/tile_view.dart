import 'package:flutter/material.dart';

import '../engine/tile.dart';

/// 패 한 장. 그림은 assets/tiles/ (CC0 패 세트).
class TileView extends StatelessWidget {
  final int tile;
  final bool red;
  final double width;
  final bool highlighted;
  final bool dimmed;

  /// 인식 확신이 낮은 패: 노란 테두리.
  final bool uncertain;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;

  const TileView(
    this.tile, {
    super.key,
    this.red = false,
    this.width = 36,
    this.highlighted = false,
    this.dimmed = false,
    this.uncertain = false,
    this.onTap,
    this.onLongPress,
  });

  /// 패 그림 경로. 적도라 5 는 `0m` 처럼 0 으로.
  static String assetFor(int tile, {bool red = false}) {
    final code = Tiles.isHonor(tile)
        ? '${tile - Tiles.east + 1}z'
        : '${red && Tiles.number(tile) == 5 ? 0 : Tiles.number(tile)}'
            '${const ['m', 'p', 's'][Tiles.suit(tile)]}';
    return 'assets/tiles/$code.png';
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final height = width * 1.4;
    final radius = BorderRadius.circular(width * 0.14);
    final border = highlighted
        ? scheme.primary
        : (uncertain ? const Color(0xFFF9A825) : const Color(0xFFB8B2A6));
    final dpr = MediaQuery.devicePixelRatioOf(context);

    // 그림은 600x800 투명 PNG. 패 몸통(크림색 면 + 아래쪽 두께)은 직접 그린다.
    final face = Padding(
      padding: EdgeInsets.fromLTRB(
          width * 0.1, width * 0.12, width * 0.1, width * 0.2),
      child: Image.asset(
        assetFor(tile, red: red),
        fit: BoxFit.contain,
        cacheWidth: (width * dpr).ceil(),
        filterQuality: FilterQuality.medium,
      ),
    );

    return Opacity(
      opacity: dimmed ? 0.3 : 1,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          onLongPress: onLongPress,
          borderRadius: radius,
          child: Container(
            width: width,
            height: height,
            decoration: BoxDecoration(
              borderRadius: radius,
              border: Border.all(
                color: border,
                width: (highlighted || uncertain) ? 2.5 : 1,
              ),
              // 위는 패 면, 맨 아래는 패 두께처럼 어둡게.
              gradient: const LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Color(0xFFFFFFFF),
                  Color(0xFFF6F2EA),
                  Color(0xFFE6DFD2),
                  Color(0xFFD3CABA),
                ],
                stops: [0, 0.86, 0.87, 1],
              ),
              boxShadow: const [
                BoxShadow(
                  color: Color(0x33000000),
                  blurRadius: 2,
                  offset: Offset(0, 1),
                ),
              ],
            ),
            child: face,
          ),
        ),
      ),
    );
  }
}

/// 패 여러 장을 한 줄로.
class TileRow extends StatelessWidget {
  final List<int> tiles;
  final double width;
  final bool open;

  const TileRow(this.tiles, {super.key, this.width = 24, this.open = true});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final t in tiles)
          Padding(
            padding: const EdgeInsets.only(right: 2),
            child: TileView(t, width: width, dimmed: !open),
          ),
      ],
    );
  }
}
