import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../table/table_layout.dart';
import '../table/table_reading.dart';

/// 인식 서버 설정. 키는 빌드 시 `--dart-define=RECOGNIZER_API_KEY=...` 로 넣는다.
class RecognizerConfig {
  static const String baseUrl = String.fromEnvironment(
    'RECOGNIZER_URL',
    defaultValue: 'https://mahjong.ai-agent-develop.cloud',
  );
  static const String apiKey = String.fromEnvironment('RECOGNIZER_API_KEY');

  static bool get isConfigured => apiKey.isNotEmpty;
}

class RecognizedTile {
  final String code;
  final double confidence;
  const RecognizedTile(this.code, this.confidence);
}

/// `/v1/recognize` 결과. [tiles] 는 손패 입력 화면이 쓰는 평면 목록, [reading] 은 울기·화료패까지 담은 모델.
class RecognizeResult {
  final List<RecognizedTile> tiles;
  final String notes;
  final String model;
  final int latencyMs;
  final HandReading reading;
  const RecognizeResult(this.tiles, this.notes, this.model, this.latencyMs, {this.reading = const HandReading()});
}

class RecognizerException implements Exception {
  final String message;
  const RecognizerException(this.message);
  @override
  String toString() => message;
}

/// 인식 서버 호출. 세 엔드포인트 모두 multipart `image` 하나를 보낸다.
///
/// - [recognize] / [recognizeBytes]: 눕힌 손패 크롭 → [RecognizeResult]
/// - [locate]: 줄인 전경 → [TableLayout]
/// - [readTable]: 중앙 크롭 → [CenterReading]
class RecognizerClient {
  final String baseUrl;
  final String apiKey;
  final Duration timeout;
  final http.Client _http;

  RecognizerClient({
    this.baseUrl = RecognizerConfig.baseUrl,
    this.apiKey = RecognizerConfig.apiKey,
    this.timeout = const Duration(seconds: 90),
    http.Client? httpClient,
  }) : _http = httpClient ?? http.Client();

  Future<RecognizeResult> recognize(File image) async =>
      recognizeBytes(await image.readAsBytes(), filename: image.uri.pathSegments.last);

  Future<RecognizeResult> recognizeBytes(Uint8List bytes, {String filename = 'hand.jpg'}) async {
    final json = await _post('/v1/recognize', bytes, filename);
    final reading = HandReading.fromJson(json);
    final tiles = ((json['tiles'] as List<dynamic>?) ?? const [])
        .whereType<Map<String, dynamic>>()
        .map((t) => RecognizedTile(t['tile'] as String, ((t['conf'] as num?) ?? 0).toDouble()))
        .toList();
    return RecognizeResult(tiles, reading.notes, reading.model, reading.latencyMs, reading: reading);
  }

  Future<TableLayout> locate(Uint8List bytes, {String filename = 'table.jpg'}) async =>
      TableLayout.fromJson(await _post('/v1/locate', bytes, filename));

  Future<CenterReading> readTable(Uint8List bytes, {String filename = 'center.jpg'}) async =>
      CenterReading.fromJson(await _post('/v1/table', bytes, filename));

  /// 관찰 전용 판독 `/v2/{kind}` (hand · river · center). 응답 JSON 그대로.
  Future<Map<String, dynamic>> observe(String kind, Uint8List bytes, {String? filename}) =>
      _post('/v2/$kind', bytes, filename ?? '$kind.jpg');

  /// 강 끝 여러 자리를 한 번에 `/v2/last3`(multipart `images` 여러 개, 1~4장). 응답 `rivers` 는 보낸 순서.
  Future<Map<String, dynamic>> observeLasts(List<(Uint8List, String)> images) => _postFiles('/v2/last3', [
    for (final (bytes, filename) in images) http.MultipartFile.fromBytes('images', bytes, filename: filename),
  ]);

  Future<Map<String, dynamic>> _post(String path, Uint8List bytes, String filename) =>
      _postFiles(path, [http.MultipartFile.fromBytes('image', bytes, filename: filename)]);

  Future<Map<String, dynamic>> _postFiles(String path, List<http.MultipartFile> files) async {
    final req = http.MultipartRequest('POST', Uri.parse('$baseUrl$path'))
      ..headers['X-Api-Key'] = apiKey
      ..files.addAll(files);

    final http.StreamedResponse streamed;
    try {
      streamed = await _http.send(req).timeout(timeout);
    } on SocketException {
      throw const RecognizerException('서버에 연결할 수 없습니다. 네트워크를 확인하세요.');
    } on HttpException catch (e) {
      throw RecognizerException('네트워크 오류: ${e.message}');
    } catch (e) {
      if (e.toString().contains('TimeoutException')) {
        throw RecognizerException('응답이 없습니다(${timeout.inSeconds}초). 다시 시도하세요.');
      }
      rethrow;
    }
    final body = await streamed.stream.bytesToString();

    switch (streamed.statusCode) {
      case 200:
        break;
      case 400:
        throw const RecognizerException('사진 파일을 읽을 수 없습니다.');
      case 401:
        throw const RecognizerException('API 키가 맞지 않습니다.');
      case 413:
        throw const RecognizerException('사진이 너무 큽니다(4MB 초과).');
      case 429:
        throw const RecognizerException('요청이 너무 잦습니다. 잠시 후 다시 시도하세요.');
      case 502:
        throw const RecognizerException('인식 모델 호출이 실패했습니다. 다시 시도하세요.');
      case 503:
        throw const RecognizerException('서버에 인식 설정이 없습니다.');
      default:
        throw RecognizerException('인식 실패 (HTTP ${streamed.statusCode})');
    }

    try {
      return jsonDecode(body) as Map<String, dynamic>;
    } on FormatException {
      throw const RecognizerException('서버 응답을 읽을 수 없습니다.');
    }
  }

  void close() => _http.close();
}
