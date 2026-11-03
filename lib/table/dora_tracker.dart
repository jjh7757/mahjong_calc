/// 판 중 도라 표시패 확정: 배경 프레임을 자체 모델(`/v2/localdora`)로 읽은 관측을 모아 "이 판의 도라 표시패" 를 정한다. 순수 Dart.
///
/// 왜: 화료 사진 한 장에서 표시패를 읽으면 리치 화료는 탁자 위에 내놓은 짝을 찾아야 하고, 그 짝을 못 찾거나 다른 패를 짝으로
/// 잡으면 틀린 채 자동 반영된다(metrics 표 1-52: 손패 밖 틀린 자동 7 중 표시패 3). 표시패는 패산이 뒤집힌 뒤 판 내내 그대로
/// 있으니 판 중 프레임 여러 장의 투표로 미리 확정해 두면 화료 사진에서 읽은 답을 검증하고, 못 읽었을 때 채운다.
///
/// 규칙(`experiments/tile_classifier/dora_rounds.py` 의 DoraTracker 와 같아야 한다, metrics 표 1-53):
/// - 관측 1개 = 프레임 1장에서 서버가 고른 패산 위 앞면 패(상자 가운데, 패 폭, 종류, 확신도).
/// - 위치 묶음: 가운데가 패 [samePosTiles] 장 안이면 같은 묶음. 가운데는 느리게 따라간다(0.8·0.2).
/// - 지금 묶음 = 최근 [recent] 관측 안에서 가장 많이 본 묶음(같으면 최근 것), 그 수가 [minReads] 이상일 때만. 화료 순간 탁자에
///   내놓은 표시패 짝(관측 몇 개)이 판 내내 본 패산 표시패를 밀어내지 않고, 기록 없이 판이 바뀌어 옛 패산이 사라지면 새 묶음이 이긴다.
/// - 서버가 확신도 0.7(WALL_CONF) 아래면 표시패를 비워 보내므로 그런 프레임은 관측이 아니다.
/// - 확정 = 지금 묶음의 최근 [window] 관측 중 [minReads] 이상이 한 종류이고 확신도 합의 몫이 [minShare] 이상.
///   같은 자리에 새 판의 패산이 와 종류가 바뀌면 최근 창이 바꿔 준다.
/// - 판이 바뀌면(기록) [reset]. 전판 확정값과 같은 자리·같은 패의 관측은 아직 치우지 않은 전판 패산으로 보고 버린다.
library;

import 'table_reading.dart';

class DoraObservation {
  final double cx, cy;

  /// 패 폭(상자의 짧은 변, 프레임 픽셀). 위치 묶음 기준.
  final double tileWidth;
  final ReadTile tile;
  final DateTime at;
  const DoraObservation({required this.cx, required this.cy, required this.tileWidth, required this.tile, required this.at});

  /// 서버 `/v2/localdora` 응답(`box` = [x, y, w, h], `indicators[0]`)에서. 표시패를 못 찾았으면 null.
  static DoraObservation? fromJson(Map<String, dynamic> j, DateTime at) {
    final box = (j['box'] as List?)?.cast<num>();
    final inds = j['indicators'] as List?;
    if (box == null || box.length < 4 || inds == null || inds.isEmpty) return null;
    final tile = ReadTile.fromJson(inds.first as Map<String, dynamic>?);
    if (tile == null) return null;
    final w = box[2].toDouble(), h = box[3].toDouble();
    return DoraObservation(cx: box[0] + w / 2, cy: box[1] + h / 2, tileWidth: w < h ? w : h, tile: tile, at: at);
  }
}

class DoraCluster {
  double cx, cy;
  final List<DoraObservation> reads = [];

  /// 각 관측의 전체 순번(지금 묶음 고르기용).
  final List<int> seq = [];
  DoraCluster(this.cx, this.cy);

  /// 순번이 [after] 보다 큰 관측 수.
  int recentCount(int after) => seq.where((n) => n > after).length;

  Map<String, dynamic> toJson() => {
        'cx': cx.round(),
        'cy': cy.round(),
        'reads': [for (final r in reads) '${r.tile.code}@${r.tile.conf}'],
      };
}

/// 확정한 표시패와 근거.
class DoraConfirmed {
  final ReadTile tile;

  /// 최근 창에서 이 종류의 확신도 합 몫(0~1).
  final double share;

  /// 최근 창에서 이 종류로 읽힌 수.
  final int reads;
  final DateTime at;
  const DoraConfirmed(this.tile, {required this.share, required this.reads, required this.at});

  Map<String, dynamic> toJson() => {'tile': tile.code, 'conf': tile.conf, 'share': share, 'reads': reads, 'at': at.toIso8601String()};
}

class DoraTracker {
  final int window;
  final int minReads;
  final double minShare;
  final double samePosTiles;
  final int recent;
  DoraTracker({this.window = 5, this.minReads = 3, this.minShare = 0.6, this.samePosTiles = 1.5, this.recent = 20});

  final List<DoraCluster> clusters = [];
  DoraCluster? _current;
  int observations = 0;

  /// 전판에서 확정했던 위치·종류. 기록 직후 아직 치우지 않은 전판 패산이 새 판의 관측으로 들어오지 않게 같은 것은 버린다.
  DoraObservation? _stale;

  /// 프레임 1장의 관측. [DoraObservation.fromJson] 이 null(표시패 없음)이면 넣지 않는다.
  void observe(DoraObservation o) {
    if (_stale case final s? when (s.cx - o.cx).abs() <= samePosTiles * o.tileWidth && (s.cy - o.cy).abs() <= samePosTiles * o.tileWidth && s.tile.tile == o.tile.tile) {
      return;
    }
    observations++;
    var c = clusters.cast<DoraCluster?>().firstWhere(
          (k) => (k!.cx - o.cx).abs() <= samePosTiles * o.tileWidth && (k.cy - o.cy).abs() <= samePosTiles * o.tileWidth,
          orElse: () => null,
        );
    if (c == null) {
      c = DoraCluster(o.cx, o.cy);
      clusters.add(c);
    }
    c.reads.add(o);
    c.seq.add(observations);
    c.cx = c.cx * 0.8 + o.cx * 0.2;
    c.cy = c.cy * 0.8 + o.cy * 0.2;
    DoraCluster? best;
    var bestN = 0;
    for (final k in clusters) {
      final n = k.recentCount(observations - recent);
      if (n > bestN || (n == bestN && best != null && k.seq.last > best.seq.last)) {
        best = k;
        bestN = n;
      }
    }
    if (best != null && bestN >= minReads) _current = best;
  }

  /// 지금 확정된 표시패. 없으면 null.
  DoraConfirmed? get confirmed {
    final c = _current;
    if (c == null) return null;
    final recent = c.reads.length > window ? c.reads.sublist(c.reads.length - window) : c.reads;
    final votes = <int, double>{};
    for (final r in recent) {
      votes[r.tile.tile] = (votes[r.tile.tile] ?? 0) + r.tile.conf;
    }
    var bestTile = -1;
    var best = -1.0;
    var total = 0.0;
    for (final e in votes.entries) {
      total += e.value;
      if (e.value > best) {
        best = e.value;
        bestTile = e.key;
      }
    }
    if (bestTile < 0 || total <= 0) return null;
    final same = [for (final r in recent) if (r.tile.tile == bestTile) r];
    final share = best / total;
    if (same.length < minReads || share < minShare) return null;
    // 확정 시각 = 그 종류가 minReads 번째로 읽힌 때. 확신도는 같은 종류 관측의 최댓값.
    final all = [for (final r in c.reads) if (r.tile.tile == bestTile) r];
    var conf = 0.0;
    for (final r in same) {
      if (r.tile.conf > conf) conf = r.tile.conf;
    }
    return DoraConfirmed(ReadTile(bestTile, red: same.last.tile.red, conf: conf), share: share, reads: same.length, at: all[minReads - 1].at);
  }

  /// 새 판: 관측을 비운다. 전판 확정값은 [_stale] 로 남겨 같은 자리·같은 패의 관측을 거른다.
  void reset() {
    final c = _current;
    final got = confirmed;
    _stale = c == null || got == null ? null : DoraObservation(cx: c.cx, cy: c.cy, tileWidth: 0, tile: got.tile, at: got.at);
    clusters.clear();
    _current = null;
    observations = 0;
  }

  Map<String, dynamic> toJson() => {
        'observations': observations,
        'confirmed': confirmed?.toJson(),
        'clusters': [for (final c in clusters) c.toJson()],
      };
}
