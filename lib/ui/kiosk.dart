import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 키오스크(갤럭시탭 가로 고정) 화면 공용 값.
///
/// 폭이 넓은 가로 화면이면 키오스크 배치를 쓴다. 대국 중에는 테이블 화면(거치 촬영)이 첫 화면이고,
/// 점수 계산은 따로 열었다가 "대국에 반영" 하면 테이블 화면으로 돌아온다(작혼의 대국 → 결산 → 대국 흐름).
/// 폰(이 크기가 아닌 화면)도 같은 흐름이고 배치만 폰용이다(로비 `KioskLobby._phone`, 테이블 `MountScreen._phoneBody`, 2026-10-29).
bool isKioskSize(Size s) => s.width >= 1000 && s.width > s.height;

/// 전체 화면(상태 표시줄·작업 표시줄 숨김, 테이블 화면 더보기에서 켜고 끔). 앱 전체에 걸린다. 가장자리를 쓸면 잠깐
/// 나왔다가 다시 숨는다(immersiveSticky). 다른 앱(QR·갤러리)에서 돌아오면 시스템이 막대를 되살릴 수 있어 앱이
/// 다시 켜질 때마다 [apply] 한다. 기본 끔(2026-10-29 사용자: 작업 표시줄은 키오스크 설정으로 없애기).
class FullscreenMode {
  static const pref = 'kiosk.fullscreen';
  static final enabled = ValueNotifier<bool>(false);

  static Future<void> load() async {
    try {
      final p = await SharedPreferences.getInstance();
      enabled.value = p.getBool(pref) ?? false;
    } catch (_) {}
    await apply();
  }

  static Future<void> set(bool on) async {
    enabled.value = on;
    await apply();
    try {
      final p = await SharedPreferences.getInstance();
      await p.setBool(pref, on);
    } catch (_) {}
  }

  static Future<void> apply() =>
      SystemChrome.setEnabledSystemUIMode(enabled.value ? SystemUiMode.immersiveSticky : SystemUiMode.edgeToEdge);
}

bool isKioskLayout(BuildContext context) => isKioskSize(MediaQuery.sizeOf(context));

/// 대국 중인데 로비(홈)를 보고 있으면 그 대국의 id. 테이블 화면의 "홈" 이 넣고, 로비의 "대국 이어 하기" 가 비운다.
/// 새 대국은 id 가 달라서 시작하면 바로 테이블 화면이 된다.
final kioskLobbyFor = ValueNotifier<String?>(null);

const kioskBg = Color(0xFF1C1916);
const kioskSurface = Color(0xFF2A2521);
const kioskGold = Color(0xFFE2C178);
const kioskGoldDeep = Color(0xFFB8913E);
const kioskRed = Color(0xFFC62828);
const kioskFelt = Color(0xFF1F4D3A);
const kioskPanel = Color(0xFFF7F4EE);

/// 키오스크에서는 시트·대화상자·보조 화면을 어두운 테마 + 글자 1.25배로 키운다. 폰이면 그대로.
Widget kioskWrap(BuildContext context, Widget child, {double scale = 1.25}) {
  if (!isKioskLayout(context)) return child;
  final mq = MediaQuery.of(context);
  return Theme(
    data: kioskDarkTheme(),
    child: MediaQuery(data: mq.copyWith(textScaler: TextScaler.linear(scale)), child: child),
  );
}

/// 폰이면 바텀시트, 키오스크면 가운데 큰 패널(어두운 테마). 안의 위젯은 같다.
Future<T?> showAdaptiveSheet<T>(BuildContext context, {required WidgetBuilder builder, double kioskMaxWidth = 760}) {
  if (!isKioskLayout(context)) {
    return showModalBottomSheet<T>(context: context, isScrollControlled: true, builder: builder);
  }
  return showDialog<T>(
    context: context,
    builder: (ctx) => kioskWrap(
      ctx,
      Dialog(
        backgroundColor: kioskSurface,
        insetPadding: const EdgeInsets.all(24),
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: kioskMaxWidth, maxHeight: MediaQuery.sizeOf(ctx).height - 48),
          child: Builder(builder: builder),
        ),
      ),
    ),
  );
}

/// 키오스크에서 폰용 세로 화면(설정 폼·정산·지난 대국)을 가운데 [maxWidth] 로 모아 보여 준다.
Widget kioskPage(BuildContext context, Widget body, {double maxWidth = 820}) {
  if (!isKioskLayout(context)) return body;
  return Center(child: ConstrainedBox(constraints: BoxConstraints(maxWidth: maxWidth), child: body));
}

/// 키오스크 어두운 테마(금색 강조).
ThemeData kioskDarkTheme() {
  final base = ThemeData(
    colorScheme: ColorScheme.fromSeed(seedColor: kioskGold, brightness: Brightness.dark)
        .copyWith(primary: kioskGold, onPrimary: const Color(0xFF2A1F08), surface: kioskSurface),
    scaffoldBackgroundColor: kioskBg,
    useMaterial3: true,
  );
  return base.copyWith(
    appBarTheme: const AppBarTheme(
      backgroundColor: kioskBg,
      foregroundColor: Colors.white,
      centerTitle: true,
      titleTextStyle: TextStyle(fontSize: 24, fontWeight: FontWeight.w700, color: Colors.white, letterSpacing: 1),
    ),
  );
}
