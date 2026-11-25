import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/game/records_upload.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/ui/records_site_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 기록 사이트 올리기(docs/records_site_design_1125.md 6절): 본문 꼴, 대기열, 비우기(성공 · 실패 · 꺼짐), 올린 때 직렬화.
Game _game(String id, {List<int> scores = const [41000, 29000, 21000, 9000], DateTime? at}) => Game(
      id: id,
      startedAt: at ?? DateTime(2026, 11, 25, 14),
      settings: const GameSettings(),
      names: const ['가', '나', '다', '라'],
      scores: List.of(scores),
      finished: true,
      endedBy: '종료',
    );

Paifu _paifu(String id, String round) => Paifu(id: id, round: round, title: round, hero: 0, events: const []);

GameStore _store(List<Game> games) => GameStore()
  ..history = games
  ..loaded = true;

Future<void> _enable({String key = 'k-123', String? url}) async {
  await RecordsSettings.setEnabled(true);
  await RecordsSettings.setStoreKey(key);
  if (url != null) await RecordsSettings.setBaseUrl(url);
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  group('본문', () {
    test('game · 정산 4줄(순위 순) · 패보 · 앱 버전', () {
      final g = _game('g1', scores: [21000, 41000, 9000, 29000]);
      final body = recordsBody(g, [_paifu('p1', '동1국'), _paifu('p2', '동2국')]);
      expect(body.keys.toSet(), {'game', 'settlement', 'paifu', 'app_version'});
      expect((body['game'] as Map)['id'], 'g1');
      expect(body['game'], g.toJson());
      final rows = (body['settlement'] as List).cast<Map<String, dynamic>>();
      expect(rows, hasLength(4));
      for (final r in rows) {
        expect(r.keys.toSet(), {'seat', 'name', 'rank', 'points', 'score', 'stars'});
      }
      expect(rows.map((r) => r['rank']), [1, 2, 3, 4]);
      expect(rows.map((r) => r['seat']), [1, 3, 0, 2]);
      expect(rows.map((r) => r['name']), ['나', '라', '가', '다']);
      expect(rows.map((r) => r['points']), [41000, 29000, 21000, 9000]);
      // 기본 규칙 우마·오카로 정산 합은 0.
      expect(rows.fold<double>(0, (a, r) => a + (r['score'] as double)), closeTo(0, 1e-9));
      expect(rows.first['score'], g.settle().first.score);
      final paifu = (body['paifu'] as List).cast<Map<String, dynamic>>();
      expect(paifu.map((p) => p['id']), ['p1', 'p2']);
      expect(body['app_version'], recordsAppVersion);
      // JSON 으로 왕복해도 같다(서버가 받는 꼴).
      expect(jsonDecode(jsonEncode(body)), isA<Map<String, dynamic>>());
    });

    test('올린 때(recordsUploadedAt)는 본문에서 뺀다 — 다시 올려도 해시가 같게', () {
      final g = _game('g1');
      final before = jsonEncode(recordsBody(g, const []));
      g.recordsUploadedAt = DateTime(2026, 11, 25, 15);
      expect(g.toJson().containsKey('recordsUploadedAt'), isTrue);
      expect(jsonEncode(recordsBody(g, const [])), before);
    });

    test('앱 버전 상수는 pubspec.yaml 의 version 과 같다', () {
      final pubspec = File('pubspec.yaml').readAsLinesSync();
      final line = pubspec.firstWhere((l) => l.startsWith('version:'));
      expect(line.substring('version:'.length).trim(), recordsAppVersion);
    });
  });

  group('recordsUploadedAt 직렬화', () {
    test('왕복', () {
      final g = _game('g1')..recordsUploadedAt = DateTime(2026, 11, 25, 15, 30);
      final back = Game.fromJson(jsonDecode(jsonEncode(g.toJson())) as Map<String, dynamic>);
      expect(back.recordsUploadedAt, DateTime(2026, 11, 25, 15, 30));
    });

    test('옛 기록(칸 없음)은 null, 없으면 칸을 쓰지 않는다', () {
      final j = _game('g1').toJson();
      expect(j.containsKey('recordsUploadedAt'), isFalse);
      expect(Game.fromJson(j).recordsUploadedAt, isNull);
    });

    test('GameStore.markRecordsUploaded', () async {
      final store = _store([_game('a'), _game('b')]);
      expect(store.markRecordsUploaded('b', at: DateTime(2026, 11, 25)), isTrue);
      expect(store.history[1].recordsUploadedAt, DateTime(2026, 11, 25));
      expect(store.markRecordsUploaded('없음'), isFalse);
    });
  });

  group('설정', () {
    test('기본값: 꺼짐 · 기본 주소 · 키 없음', () async {
      final c = await RecordsSettings.load();
      expect(c.enabled, isFalse);
      expect(c.baseUrl, recordsDefaultBaseUrl);
      expect(c.storeKey, '');
      expect(c.uploadUri.toString(), '$recordsDefaultBaseUrl/api/v1/games');
    });

    test('주소 끝 / 는 떼고, http(s) 가 아니면 문제', () {
      expect(const RecordsConfig(baseUrl: 'https://x.test/records/', storeKey: 'k').uploadUri.toString(),
          'https://x.test/records/api/v1/games');
      expect(const RecordsConfig(baseUrl: 'ftp://x', storeKey: 'k').problem, isNotNull);
      expect(const RecordsConfig(storeKey: ' ').problem, contains('매장 키'));
      expect(const RecordsConfig(storeKey: 'k').problem, isNull);
    });
  });

  group('대기열', () {
    test('중복 없이 순서대로', () async {
      final up = RecordsUploader(store: _store([]));
      await up.enqueue(['a', 'b']);
      await up.enqueue(['b', 'c', 'a']);
      expect(await up.queue(), ['a', 'b', 'c']);
      expect(up.status.value.pending, 3);
    });

    test('지난 대국 모두: 오래된 것부터', () async {
      final store = _store([_game('new', at: DateTime(2026, 11, 25)), _game('old', at: DateTime(2026, 11, 1))]);
      final up = RecordsUploader(store: store);
      await up.enqueue(['new']);
      expect(await up.enqueueAllHistory(), 2);
      expect(await up.queue(), ['new', 'old']);
    });
  });

  group('비우기', () {
    test('꺼져 있으면 아무것도 안 한다(요청 없음 · 대기열 그대로)', () async {
      var calls = 0;
      final store = _store([_game('a')]);
      final up = RecordsUploader(
        store: store,
        client: () => MockClient((_) async {
          calls++;
          return http.Response('{"status":"created","id":1}', 200);
        }),
      );
      await up.enqueue(['a']);
      final r = await up.flush();
      expect(r.disabled, isTrue);
      expect(calls, 0);
      expect(await up.queue(), ['a']);
      expect(store.history.single.recordsUploadedAt, isNull);
    });

    test('꺼져 있으면 끝난 대국 알림도 대기열에 넣지 않는다', () async {
      final up = RecordsUploader(store: _store([_game('a')]), finishDelay: Duration.zero);
      up.onFinished(_game('a'));
      await pumpEventQueue();
      expect(await up.queue(), isEmpty);
    });

    test('성공: 머리 · 본문 확인, 대기열에서 빼고 올린 때 기록', () async {
      await _enable(url: 'https://records.test/records/');
      final reqs = <http.Request>[];
      final store = _store([_game('a'), _game('b')]);
      final paifuAsked = <String>[];
      final up = RecordsUploader(
        store: store,
        now: () => DateTime(2026, 11, 25, 16),
        paifuOf: (id) async {
          paifuAsked.add(id);
          return id == 'a' ? [_paifu('a1', '동1국')] : const [];
        },
        client: () => MockClient((req) async {
          reqs.add(req);
          return http.Response('{"status":"created","id":7}', 200);
        }),
      );
      await up.enqueue(['a', 'b']);
      final r = await up.flush();
      expect(r.sent, 2);
      expect(r.failed, 0);
      expect(r.pending, 0);
      expect(r.error, isNull);
      expect(await up.queue(), isEmpty);
      expect(paifuAsked, ['a', 'b']);
      expect(reqs, hasLength(2));
      final req = reqs.first;
      expect(req.method, 'POST');
      expect(req.url.toString(), 'https://records.test/records/api/v1/games');
      expect(req.headers['X-Store-Key'], 'k-123');
      expect(req.headers['Content-Type'], startsWith('application/json'));
      final body = jsonDecode(utf8.decode(req.bodyBytes)) as Map<String, dynamic>;
      expect((body['game'] as Map)['id'], 'a');
      expect((body['settlement'] as List), hasLength(4));
      expect((body['paifu'] as List).single['id'], 'a1');
      expect(body['app_version'], recordsAppVersion);
      expect(store.history.map((g) => g.recordsUploadedAt), [DateTime(2026, 11, 25, 16), DateTime(2026, 11, 25, 16)]);
      expect(up.status.value.lastError, isNull);
      expect(up.status.value.lastSuccessAt, DateTime(2026, 11, 25, 16));
      // 지난 대국 저장에도 남는다.
      final saved = (await SharedPreferences.getInstance()).getStringList('game.history')!;
      expect(saved.every((s) => s.contains('recordsUploadedAt')), isTrue);
    });

    test('서버 오류는 대기열에 남기고 다음 대국은 계속', () async {
      await _enable();
      final store = _store([_game('a'), _game('b')]);
      final up = RecordsUploader(
        store: store,
        paifuOf: (_) async => const [],
        client: () => MockClient((req) async {
          final id = (jsonDecode(req.body) as Map)['game']['id'];
          return id == 'a' ? http.Response('boom', 500) : http.Response('{"status":"unchanged","id":2}', 200);
        }),
      );
      await up.enqueue(['a', 'b']);
      final r = await up.flush();
      expect(r.sent, 1);
      expect(r.failed, 1);
      expect(await up.queue(), ['a']);
      expect(store.history[0].recordsUploadedAt, isNull);
      expect(store.history[1].recordsUploadedAt, isNotNull);
      expect(up.status.value.lastError, contains('500'));
      expect(up.status.value.pending, 1);
    });

    test('키가 틀리면(401) 멈추고 모두 남긴다', () async {
      await _enable();
      var calls = 0;
      final up = RecordsUploader(
        store: _store([_game('a'), _game('b')]),
        paifuOf: (_) async => const [],
        client: () => MockClient((_) async {
          calls++;
          return http.Response('{"detail":"bad key"}', 401);
        }),
      );
      await up.enqueue(['a', 'b']);
      final r = await up.flush();
      expect(calls, 1);
      expect(r.sent, 0);
      expect(await up.queue(), ['a', 'b']);
      expect(r.error, contains('매장 키'));
    });

    test('연결 실패면 멈추고 남긴다, 다음 비우기에서 올라간다', () async {
      await _enable();
      var online = false;
      final store = _store([_game('a'), _game('b')]);
      final up = RecordsUploader(
        store: store,
        paifuOf: (_) async => const [],
        client: () => MockClient((_) async {
          if (!online) throw const SocketException('Failed host lookup');
          return http.Response('{"status":"created","id":1}', 200);
        }),
      );
      await up.enqueue(['a', 'b']);
      final r1 = await up.flush();
      expect(r1.sent, 0);
      expect(r1.failed, 1);
      expect(await up.queue(), ['a', 'b']);
      expect(r1.error, contains('연결 실패'));
      online = true;
      final r2 = await up.flush();
      expect(r2.sent, 2);
      expect(await up.queue(), isEmpty);
      expect(up.status.value.lastError, isNull);
    });

    test('지운 대국 id 는 대기열에서 버린다', () async {
      await _enable();
      final up = RecordsUploader(
        store: _store([_game('a')]),
        paifuOf: (_) async => const [],
        client: () => MockClient((_) async => http.Response('{"status":"created","id":1}', 200)),
      );
      await up.enqueue(['gone', 'a']);
      final r = await up.flush();
      expect(r.sent, 1);
      expect(await up.queue(), isEmpty);
    });

    test('지난 대국을 아직 못 읽었으면 대기열을 건드리지 않는다', () async {
      await _enable();
      var calls = 0;
      final up = RecordsUploader(
        store: GameStore(),
        client: () => MockClient((_) async {
          calls++;
          return http.Response('{}', 200);
        }),
      );
      await up.enqueue(['a']);
      await up.flush();
      expect(calls, 0);
      expect(await up.queue(), ['a']);
    });

    test('동시에 두 번 부르면 한 번만 돈다', () async {
      await _enable();
      var calls = 0;
      final up = RecordsUploader(
        store: _store([_game('a')]),
        paifuOf: (_) async => const [],
        client: () => MockClient((_) async {
          calls++;
          await Future<void>.delayed(const Duration(milliseconds: 10));
          return http.Response('{"status":"created","id":1}', 200);
        }),
      );
      await up.enqueue(['a']);
      final f1 = up.flush();
      final f2 = up.flush();
      expect(identical(f1, f2), isTrue);
      final rs = await Future.wait([f1, f2]);
      expect(calls, 1);
      expect(rs.every((r) => r.sent == 1), isTrue);
    });

    test('켜져 있으면 끝난 대국 알림 → 대기열 → 올림(직접 입력은 바로)', () async {
      await _enable();
      final store = _store([]);
      final up = RecordsUploader(
        store: store,
        paifuOf: (_) async => const [],
        client: () => MockClient((_) async => http.Response('{"status":"created","id":1}', 200)),
      );
      store.onFinished = up.onFinished;
      store.addFinished(Game.manual(
        id: 'm1',
        playedAt: DateTime(2026, 11, 25),
        settings: const GameSettings(),
        names: const ['가', '나', '다', '라'],
        scores: const [40000, 30000, 20000, 10000],
      ));
      await pumpEventQueue();
      expect(await up.queue(), isEmpty);
      expect(store.history.single.recordsUploadedAt, isNotNull);
    });
  });

  group('설정 화면', () {
    testWidgets('키는 가려 보이고, 모두 올리기는 확인을 한 번 받는다', (tester) async {
      SharedPreferences.setMockInitialValues({
        RecordsSettings.enabledKey: true,
        RecordsSettings.storeKeyKey: 'secret-key',
      });
      var calls = 0;
      final up = RecordsUploader(
        store: _store([]),
        client: () => MockClient((_) async {
          calls++;
          return http.Response('{"status":"created","id":1}', 200);
        }),
      );
      await tester.pumpWidget(MaterialApp(home: RecordsSiteScreen(uploader: up)));
      await tester.pumpAndSettle();
      final key = tester.widget<TextField>(find.byKey(const ValueKey('records-key')));
      expect(key.obscureText, isTrue);
      expect(find.textContaining('대기 중 0개'), findsOneWidget);

      await tester.tap(find.byKey(const ValueKey('records-upload-all')));
      await tester.pumpAndSettle();
      expect(find.text('지난 대국을 모두 올릴까요?'), findsOneWidget);
      await tester.tap(find.text('아니오'));
      await tester.pumpAndSettle();
      expect(find.text('지난 대국을 모두 올릴까요?'), findsNothing);
      expect(calls, 0);
    });
  });
}
