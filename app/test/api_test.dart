import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kartenkiste/core/api.dart';
import 'package:kartenkiste/core/format.dart';
import 'package:kartenkiste/core/token_store.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'fakes.dart';

/// Antwortet je nach Pfad; zählt Anfragen.
class ScriptedAdapter implements HttpClientAdapter {
  ScriptedAdapter(this.handler);

  final ResponseBody Function(RequestOptions options) handler;
  final requests = <String>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add('${options.method} ${options.path} ${options.headers['Authorization'] ?? '-'}');
    return handler(options);
  }

  @override
  void close({bool force = false}) {}
}

ResponseBody json(int status, Object body) => ResponseBody.fromString(
  jsonEncode(body),
  status,
  headers: {
    Headers.contentTypeHeader: [Headers.jsonContentType],
  },
);

Map<String, Object?> tokens(String access) => {
  'access_token': access,
  'refresh_token': 'r-$access',
  'expires_in': 900,
  'user': userJson(),
};

void main() {
  test('abgelaufenes Access-Token wird einmal erneuert, Anfrage wiederholt', () async {
    final store = MemoryTokenStore()..token = 'r-alt';
    final adapter = ScriptedAdapter((options) {
      if (options.path == '/auth/refresh') return json(200, tokens('neu'));
      final auth = options.headers['Authorization'];
      return auth == 'Bearer neu'
          ? json(200, userJson())
          : json(401, {
              'error': {'code': 'invalid_token', 'message': 'abgelaufen'},
            });
    });
    final dio = Dio()..httpClientAdapter = adapter;
    final api = Api(baseUrl: 'http://test', tokens: store, dio: dio);

    final user = await api.restoreSession();

    expect(user?.displayName, 'Sebastian');
    expect(store.token, 'r-neu');
    expect(adapter.requests.where((r) => r.contains('/auth/refresh')), hasLength(1));
  });

  test('Refresh scheitert → Sitzung beendet, Fehler mit deutscher Meldung', () async {
    final store = MemoryTokenStore()..token = 'r-alt';
    var expired = false;
    final adapter = ScriptedAdapter(
      (options) => json(401, {
        'error': {'code': 'invalid_token', 'message': 'Sitzung ungültig oder abgelaufen.'},
      }),
    );
    final api = Api(baseUrl: 'http://test', tokens: store, dio: Dio()..httpClientAdapter = adapter)
      ..onSessionExpired = () => expired = true;

    expect(await api.restoreSession(), isNull);
    expect(store.token, isNull);
    await expectLater(
      api.me(),
      throwsA(
        isA<ApiException>().having(
          (e) => e.message,
          'message',
          'Sitzung ungültig oder abgelaufen.',
        ),
      ),
    );
    expect(expired, isTrue); // App kehrt zur Anmeldung zurück
  });

  test('Fehlerformat, Validierungsfehler und Verbindungsfehler', () {
    final options = RequestOptions(path: '/x');
    ApiException map(int status, Object body) => ApiException.from(
      DioException(
        requestOptions: options,
        response: Response<dynamic>(requestOptions: options, statusCode: status, data: body),
        type: DioExceptionType.badResponse,
      ),
    );
    expect(
      map(429, {
        'error': {'code': 'rate_limited', 'message': 'Zu viele Scans.'},
      }).code,
      'rate_limited',
    );
    expect(map(422, {'detail': <Object>[]}).message, 'Eingabe ungültig – bitte prüfen.');
    expect(
      ApiException.from(
        DioException(requestOptions: options, type: DioExceptionType.connectionError),
      ).code,
      'offline',
    );
  });

  test('Formatierung deutsch', () async {
    await initializeDateFormatting('de_DE');
    expect(money('1805.9'), '1.805,90\u00a0€');
    expect(money(null), '–');
    expect(money('12.5', currency: 'USD'), '12,50\u00a0\$');
    expect(signedMoney('-3.5'), '−3,50\u00a0€');
    expect(signedMoney('51'), '+51,00\u00a0€');
    expect(normalizeAmount('1.234,50\u00a0€'), '1234.50');
    expect(normalizeAmount('12.50'), '12.50');
    expect(normalizeAmount(' '), isNull);
    expect(percent(0.856), '86 %');
    expect(languageTag('zh-tw'), 'ZH-TW');
  });
}
