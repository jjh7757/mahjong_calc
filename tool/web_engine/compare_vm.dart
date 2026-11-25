// 대조용: 패보 파일마다 engine_api.dart 의 scoreJson · reviewJson 을 Dart VM 으로 돌려 한 줄 JSON 으로 적는다.
//
//   dart run tool/web_engine/compare_vm.dart <출력.jsonl> <패보.json>...
//
// 같은 입력으로 컴파일된 JS(compare_js.mjs)가 낸 줄과 compare.mjs 가 비교한다.
import 'dart:convert';
import 'dart:io';

import 'engine_api.dart';

void main(List<String> args) {
  if (args.length < 2) {
    stderr.writeln('쓰는 법: dart run tool/web_engine/compare_vm.dart <출력.jsonl> <패보.json>...');
    exit(2);
  }
  final out = File(args.first).openSync(mode: FileMode.write);
  final sw = Stopwatch()..start();
  for (final path in args.skip(1)) {
    final raw = File(path).readAsStringSync();
    final t0 = sw.elapsedMicroseconds;
    final score = scoreJson(raw);
    final review = reviewJson(raw);
    final ms = (sw.elapsedMicroseconds - t0) / 1000;
    out.writeStringSync('${jsonEncode({'file': path.replaceAll('\\', '/').split('/').last, 'score': score, 'review': review, 'ms': ms})}\n');
  }
  out.closeSync();
}
