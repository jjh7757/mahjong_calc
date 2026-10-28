// flutter drive 로 integration_test/ 를 profile 모드(실제 앱과 같은 AOT)로 돌릴 때 쓰는 드라이버.
// flutter drive --profile -d emulator-5554 --driver=test_driver/integration_test.dart \
//   --target=integration_test/read_grid_timing_test.dart --dart-define=...
import 'package:integration_test/integration_test_driver.dart';

Future<void> main() => integrationDriver();
