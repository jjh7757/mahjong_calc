/// 서버 호출이 연결·시간 초과로 실패하면 한동안 부르지 않는다.
///
/// 판 중 리치봉 읽기(`/v2/sticks`)는 기기 판독이 없어 늘 서버로 간다. 매장에서 인터넷 없는 핫스팟으로 쓰면 읽기가
/// 실패하는데, 그동안 `_trackBusy` 라 버림 추적 프레임이 버려진다(2026-11-12 점검: 변화 한 번에 최대 3번 × 시간 제한).
/// 리치 자체는 픽셀 확정(`RiverTracker._localStickFrame`)이 따로 잡으니, 서버가 안 되면 쉬는 편이 낫다.
class ServerBackoff {
  final Duration rest;
  DateTime? _until;

  ServerBackoff({this.rest = const Duration(minutes: 2)});

  /// 지금 불러도 되나.
  bool ready(DateTime now) => _until == null || !now.isBefore(_until!);

  /// 실패를 알린다. 연결·시간 초과면 [rest] 동안 쉰다(서버가 답한 오류는 쉬지 않음).
  void failed(Object error, DateTime now) {
    if (isNetworkError(error)) _until = now.add(rest);
  }

  void succeeded() => _until = null;

  /// [RecognizerClient] 가 던지는 연결 실패·시간 초과 문구, 또는 소켓·타임아웃 예외.
  static bool isNetworkError(Object e) {
    final s = e.toString();
    return s.contains('서버에 연결할 수 없습니다') ||
        s.contains('응답이 없습니다') ||
        s.contains('네트워크 오류') ||
        s.contains('SocketException') ||
        s.contains('TimeoutException') ||
        s.contains('Failed host lookup');
  }
}
