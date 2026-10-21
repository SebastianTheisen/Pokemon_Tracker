// HTTP-Client für das Backend (/api/v1).
//
// * Hängt das Access-Token an jede Anfrage.
// * Läuft es ab (401), wird einmal per Refresh-Token erneuert und die Anfrage
//   wiederholt. Parallele Anfragen teilen sich dabei eine Erneuerung.
// * Fehler kommen einheitlich als [ApiException] mit deutscher Meldung.
import 'dart:async';
import 'dart:typed_data';

import 'package:dio/dio.dart';

import '../models/models.dart';
import 'token_store.dart';

class ApiException implements Exception {
  const ApiException(this.message, {this.code = 'error', this.statusCode});

  final String message;
  final String code;
  final int? statusCode;

  bool get isUnauthorized => statusCode == 401;

  @override
  String toString() => message;

  static ApiException from(Object error) {
    if (error is ApiException) return error;
    if (error is DioException) {
      final response = error.response;
      final data = response?.data;
      if (data is Map<String, dynamic>) {
        final body = data['error'];
        if (body is Map<String, dynamic>) {
          return ApiException(
            body['message'] as String? ?? 'Unbekannter Fehler.',
            code: body['code'] as String? ?? 'error',
            statusCode: response?.statusCode,
          );
        }
        if (response?.statusCode == 422) {
          return ApiException(
            'Eingabe ungültig – bitte prüfen.',
            code: 'validation_error',
            statusCode: 422,
          );
        }
      }
      return switch (error.type) {
        DioExceptionType.connectionTimeout ||
        DioExceptionType.receiveTimeout ||
        DioExceptionType.sendTimeout => const ApiException(
          'Zeitüberschreitung – ist der Server erreichbar?',
          code: 'timeout',
        ),
        DioExceptionType.connectionError => const ApiException(
          'Keine Verbindung zum Server. Ist Tailscale verbunden?',
          code: 'offline',
        ),
        _ => ApiException(
          'Serverfehler (${response?.statusCode ?? 'unbekannt'}).',
          statusCode: response?.statusCode,
        ),
      };
    }
    return ApiException('$error');
  }
}

/// Bild für den Upload (Scanner).
class UploadImage {
  const UploadImage({required this.bytes, required this.filename});

  final Uint8List bytes;
  final String filename;
}

class Api {
  Api({required String baseUrl, required this.tokens, Dio? dio}) : _dio = dio ?? Dio() {
    _dio.options
      ..baseUrl = '$baseUrl/api/v1'
      ..connectTimeout = const Duration(seconds: 15)
      ..receiveTimeout = const Duration(seconds: 60);
    _dio.interceptors.add(
      InterceptorsWrapper(onRequest: _attachToken, onError: _refreshOnUnauthorized),
    );
  }

  final Dio _dio;
  final TokenStore tokens;
  String? _accessToken;
  Future<bool>? _refreshing;

  /// Wird aufgerufen, wenn die Sitzung endgültig abgelaufen ist.
  void Function()? onSessionExpired;

  bool get hasSession => _accessToken != null;

  void _attachToken(RequestOptions options, RequestInterceptorHandler handler) {
    final token = _accessToken;
    if (token != null && options.extra['auth'] != false) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }

  Future<void> _refreshOnUnauthorized(DioException error, ErrorInterceptorHandler handler) async {
    final options = error.requestOptions;
    final retryable =
        error.response?.statusCode == 401 &&
        options.extra['auth'] != false &&
        options.extra['retried'] != true;
    if (!retryable) return handler.next(error);
    if (!await _refreshSession()) {
      onSessionExpired?.call();
      return handler.next(error);
    }
    try {
      options.extra['retried'] = true;
      options.headers['Authorization'] = 'Bearer $_accessToken';
      handler.resolve(await _dio.fetch<dynamic>(options));
    } on DioException catch (retryError) {
      handler.next(retryError);
    }
  }

  Future<bool> _refreshSession() => _refreshing ??= () async {
    try {
      final refresh = await tokens.readRefreshToken();
      if (refresh == null) return false;
      final response = await _dio.post<Json>(
        '/auth/refresh',
        data: {'refresh_token': refresh},
        options: Options(extra: {'auth': false}),
      );
      await _store(TokenPair.fromJson(response.data!));
      return true;
    } on DioException {
      await _forget();
      return false;
    } finally {
      _refreshing = null;
    }
  }();

  Future<User> _store(TokenPair pair) async {
    _accessToken = pair.accessToken;
    await tokens.writeRefreshToken(pair.refreshToken);
    return pair.user;
  }

  Future<void> _forget() async {
    _accessToken = null;
    await tokens.clear();
  }

  Future<T> _call<T>(Future<T> Function() request) async {
    try {
      return await request();
    } catch (error) {
      throw ApiException.from(error);
    }
  }

  Future<Json> _get(String path, {Map<String, Object?>? query}) => _call(() async {
    final response = await _dio.get<Json>(path, queryParameters: _clean(query));
    return response.data!;
  });

  Future<List<dynamic>> _getList(String path, {Map<String, Object?>? query}) => _call(() async {
    final response = await _dio.get<List<dynamic>>(path, queryParameters: _clean(query));
    return response.data!;
  });

  Future<Object?> _send(
    String method,
    String path, {
    Object? body,
    Map<String, Object?>? query,
    bool auth = true,
  }) => _call(() async {
    final response = await _dio.request<dynamic>(
      path,
      data: body,
      queryParameters: _clean(query),
      options: Options(method: method, extra: {'auth': auth}),
    );
    return response.data;
  });

  static Map<String, Object?>? _clean(Map<String, Object?>? query) => query == null
      ? null
      : {
          for (final entry in query.entries)
            if (entry.value != null && entry.value != '') entry.key: entry.value,
        };

  // ---------------------------------------------------------------- Auth

  /// Beim App-Start: gespeicherte Sitzung wiederherstellen (oder `null`).
  Future<User?> restoreSession() async {
    if (!await _refreshSession()) return null;
    return me();
  }

  Future<User> login(String email, String password) async {
    final data = await _send(
      'POST',
      '/auth/login',
      body: {'email': email, 'password': password},
      auth: false,
    );
    return _store(TokenPair.fromJson(data! as Json));
  }

  Future<User> register({
    required String inviteCode,
    required String email,
    required String password,
    required String displayName,
  }) async {
    final data = await _send(
      'POST',
      '/auth/register',
      body: {
        'invite_code': inviteCode,
        'email': email,
        'password': password,
        'display_name': displayName,
      },
      auth: false,
    );
    return _store(TokenPair.fromJson(data! as Json));
  }

  Future<void> resetPassword(String code, String newPassword) => _send(
    'POST',
    '/auth/reset-password',
    body: {'code': code, 'new_password': newPassword},
    auth: false,
  );

  Future<void> logout() async {
    final refresh = await tokens.readRefreshToken();
    try {
      if (refresh != null) {
        await _send('POST', '/auth/logout', body: {'refresh_token': refresh}, auth: false);
      }
    } on ApiException {
      // Abmelden klappt lokal auch ohne Server.
    } finally {
      await _forget();
    }
  }

  // ---------------------------------------------------------------- Konto

  Future<User> me() async => User.fromJson(await _get('/me'));

  Future<User> updateMe(String displayName) async =>
      User.fromJson((await _send('PATCH', '/me', body: {'display_name': displayName}))! as Json);

  Future<void> changePassword(String current, String next) =>
      _send('POST', '/me/password', body: {'current_password': current, 'new_password': next});

  Future<List<SessionInfo>> sessions() async =>
      parseList(await _getList('/me/sessions'), SessionInfo.fromJson);

  Future<void> endSession(String id) => _send('DELETE', '/me/sessions/$id');

  Future<UserSettings> settings() async => UserSettings.fromJson(await _get('/me/settings'));

  Future<UserSettings> updateSettings({
    Map<String, double>? factors,
    bool resetFactors = false,
    Map<String, double>? languageFactors,
    bool resetLanguageFactors = false,
    String? defaultLanguage,
  }) async => UserSettings.fromJson(
    (await _send(
          'PATCH',
          '/me/settings',
          body: {
            'condition_factors': ?factors,
            if (resetFactors) 'reset_condition_factors': true,
            'language_factors': ?languageFactors,
            if (resetLanguageFactors) 'reset_language_factors': true,
            'default_language': ?defaultLanguage,
          },
        ))!
        as Json,
  );

  /// Verkaufte Artikel von ebay.de über Apify holen (gemerkt: kostenlos). [grading] z. B.
  /// „PSA 10“; ohne = Rohkarte. Auswerten/Speichern danach wie beim Lesezeichen ([ebaySold]).
  Future<EbayFetch> ebayFetch(String cardId, {String? grading, bool force = false}) async =>
      EbayFetch.fromJson(
        (await _send(
              'POST',
              '/cards/$cardId/ebay-sold/fetch',
              body: {'grading': ?grading, 'force': force},
            ))!
            as Json,
      );

  /// Ist der eBay-Abruf eingerichtet? Mit Monatsverbrauch und Budget (US-Dollar).
  Future<ApifyStatus> apifyStatus() async => ApifyStatus.fromJson(await _get('/apify/status'));

  /// Ausgelesene eBay-Verkäufe auswerten (Vorschlag) bzw. die gewählten speichern.
  Future<EbaySoldResult> ebaySold(
    String cardId, {
    required String pageUrl,
    required List<Json> rows,
    List<int>? selected,
    bool save = false,
  }) async => EbaySoldResult.fromJson(
    (await _send(
          'POST',
          '/cards/$cardId/ebay-sold',
          body: {'page_url': pageUrl, 'rows': rows, 'selected': ?selected, 'save': save},
        ))!
        as Json,
  );

  /// Karte merken, für die gerade „Preis holen“ geöffnet wird (für das Lesezeichen).
  Future<void> setPriceTarget(String cardId) async =>
      _send('PUT', '/me/price-target', body: {'card_id': cardId});

  /// Zuletzt zum Preisholen geöffnete Karte (höchstens 2 Stunden alt) oder `null`.
  Future<String?> priceTarget() async => (await _get('/me/price-target')).strOrNull('card_id');

  /// Ausgelesene Cardmarket-Angebote auswerten (`save: false` = Vorschau) bzw. speichern.
  Future<CardmarketOffersResult> cardmarketOffers(
    String cardId, {
    required String pageUrl,
    required List<CardmarketOfferRow> rows,
    bool save = false,
    bool rememberPage = false,
  }) async => CardmarketOffersResult.fromJson(
    (await _send(
          'POST',
          '/cards/$cardId/cardmarket-offers',
          body: {
            'page_url': pageUrl,
            'rows': [for (final row in rows) row.toJson()],
            'save': save,
            'remember_page': rememberPage,
          },
        ))!
        as Json,
  );

  // ---------------------------------------------------------------- Katalog

  Future<List<SearchHit>> search(String query, {String? language, int limit = 30}) async =>
      parseList(
        await _getList('/cards/search', query: {'q': query, 'language': language, 'limit': limit}),
        SearchHit.fromJson,
      );

  Future<CardInfo> card(String id) async => CardInfo.fromJson(await _get('/cards/$id'));

  /// Versiegelte Produkte im Cardmarket-Katalog (englische Namen) mit Preis.
  Future<List<SealedOffer>> searchSealed(String query) async =>
      parseList(await _getList('/cardmarket/sealed', query: {'q': query}), SealedOffer.fromJson);

  /// Produkt zum Cardmarket-Eintrag in einer Sprache (vorhanden oder neu angelegt).
  Future<Product> productFromCardmarket(int cardmarketProductId, String language) async =>
      Product.fromJson(
        (await _send(
              'POST',
              '/products/from-cardmarket',
              body: {'cardmarket_product_id': cardmarketProductId, 'language': language},
            ))!
            as Json,
      );

  Future<CardPrices> prices(String cardId) async =>
      CardPrices.fromJson(await _get('/cards/$cardId/prices'));

  /// Cardmarket-Produkt der Karte und dieselbe Karte in anderen Sprachfassungen.
  Future<CardmarketChoice> cardmarketChoice(String cardId) async =>
      CardmarketChoice.fromJson(await _get('/cards/$cardId/cardmarket'));

  /// Richtiges Cardmarket-Produkt wählen; eine andere Sprachfassung gilt für das ganze Set.
  Future<CardmarketChoice> chooseCardmarket(String cardId, int productId) async =>
      CardmarketChoice.fromJson(
        (await _send('PUT', '/cards/$cardId/cardmarket', body: {'product_id': productId}))! as Json,
      );

  /// Bezeichnung einer Cardmarket-Ausgabe setzen (leer = entfernen).
  Future<void> labelCardmarketExpansion(int expansionId, String label) async =>
      _send('PUT', '/cardmarket/expansions/$expansionId', body: {'label': label});

  Future<PriceHistory> priceHistory(
    String cardId, {
    String source = 'cardmarket',
    String variant = 'normal',
    String metric = 'trend',
    int days = 365,
  }) async => PriceHistory.fromJson(
    await _get(
      '/cards/$cardId/price-history',
      query: {'source': source, 'variant': variant, 'metric': metric, 'days': days},
    ),
  );

  // ---------------------------------------------------------------- Sammlung

  Future<CollectionSummary> dashboard() async =>
      CollectionSummary.fromJson(await _get('/dashboard'));

  Future<CollectionHistory> collectionHistory({int days = 90}) async =>
      CollectionHistory.fromJson(await _get('/collection/history', query: {'days': days}));

  Future<List<Folder>> folders() async => parseList(await _getList('/folders'), Folder.fromJson);

  Future<Folder> createFolder(String name) async =>
      Folder.fromJson((await _send('POST', '/folders', body: {'name': name}))! as Json);

  Future<Folder> renameFolder(String id, String name) async =>
      Folder.fromJson((await _send('PATCH', '/folders/$id', body: {'name': name}))! as Json);

  Future<void> deleteFolder(String id, {String? moveTo}) =>
      _send('DELETE', '/folders/$id', query: {'move_to': moveTo});

  Future<ItemPage> items({
    String? folderId,
    String? kind,
    String? query,
    String sort = 'value_desc',
    int limit = 500,
    int offset = 0,
  }) async => ItemPage.fromJson(
    await _get(
      '/collection/items',
      query: {
        'folder_id': folderId,
        'kind': kind,
        'q': query,
        'sort': sort,
        'limit': limit,
        'offset': offset,
      },
    ),
  );

  Future<CollectionItem> addItem(Map<String, Object?> body) async =>
      CollectionItem.fromJson((await _send('POST', '/collection/items', body: body))! as Json);

  Future<CollectionItem> updateItem(String id, Map<String, Object?> changes) async =>
      CollectionItem.fromJson(
        (await _send('PATCH', '/collection/items/$id', body: changes))! as Json,
      );

  Future<void> deleteItem(String id) => _send('DELETE', '/collection/items/$id');

  Future<List<SetOverview>> collectionSets() async =>
      parseList(await _getList('/collection/sets'), SetOverview.fromJson);

  Future<String> exportCsv() async => _call(() async {
    final response = await _dio.get<String>(
      '/collection/export.csv',
      options: Options(responseType: ResponseType.plain),
    );
    return response.data!;
  });

  Future<List<WishlistEntry>> wishlist() async =>
      parseList(await _getList('/wishlist'), WishlistEntry.fromJson);

  Future<void> addToWishlist({String? cardId, String? productId}) =>
      _send('POST', '/wishlist', body: {'card_id': ?cardId, 'product_id': ?productId});

  Future<void> removeFromWishlist(String entryId) => _send('DELETE', '/wishlist/$entryId');

  Future<CardInfo> createCard({
    required String name,
    required String number,
    required String language,
    String? setName,
  }) async => CardInfo.fromJson(
    (await _send(
          'POST',
          '/cards',
          body: {'name': name, 'number': number, 'language': language, 'set_name': ?setName},
        ))!
        as Json,
  );

  // ---------------------------------------------------------------- Scanner

  static MultipartFile _file(UploadImage image) =>
      MultipartFile.fromBytes(image.bytes, filename: image.filename);

  Future<ScanResult> scan(UploadImage image, {String? language}) async => ScanResult.fromJson(
    (await _send(
          'POST',
          '/scan',
          body: FormData.fromMap({'file': _file(image)}),
          query: {'language': language},
        ))!
        as Json,
  );

  Future<List<BatchItem>> scanBatch(List<UploadImage> images, {String? language}) async =>
      parseList(
        await _send(
          'POST',
          '/scan/batch',
          body: FormData.fromMap({
            'files': [for (final image in images) _file(image)],
          }),
          query: {'language': language},
        ),
        BatchItem.fromJson,
      );

  Future<BinderResult> scanBinder(UploadImage image, {String layout = 'auto'}) async =>
      BinderResult.fromJson(
        (await _send(
              'POST',
              '/scan/binder',
              body: FormData.fromMap({'file': _file(image)}),
              query: {'layout': layout},
            ))!
            as Json,
      );

  Future<ConfirmResult> confirmScan(
    String scanId,
    String cardId, {
    bool saveReference = true,
  }) async => ConfirmResult.fromJson(
    (await _send(
          'POST',
          '/scan/$scanId/confirm',
          body: {'card_id': cardId, 'save_reference': saveReference},
        ))!
        as Json,
  );

  // ---------------------------------------------------------------- Admin

  Future<List<User>> adminUsers() async => parseList(await _getList('/admin/users'), User.fromJson);

  Future<User> adminUpdateUser(String id, {bool? isActive, String? role}) async => User.fromJson(
    (await _send('PATCH', '/admin/users/$id', body: {'is_active': ?isActive, 'role': ?role}))!
        as Json,
  );

  Future<ResetCode> adminResetCode(String userId) async =>
      ResetCode.fromJson((await _send('POST', '/admin/users/$userId/password-reset'))! as Json);

  Future<List<Invite>> invites() async =>
      parseList(await _getList('/admin/invites'), Invite.fromJson);

  Future<Invite> createInvite({String? note, int? days}) async => Invite.fromJson(
    (await _send('POST', '/admin/invites', body: {'note': ?note, 'ttl_days': ?days}))! as Json,
  );

  Future<void> revokeInvite(String id) => _send('DELETE', '/admin/invites/$id');

  Future<CollectionSummary> adminUserSummary(String userId) async =>
      CollectionSummary.fromJson(await _get('/admin/users/$userId/collection/summary'));

  Future<ItemPage> adminUserItems(String userId) async =>
      ItemPage.fromJson(await _get('/admin/users/$userId/collection/items'));
}
