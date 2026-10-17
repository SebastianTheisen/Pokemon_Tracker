// Kleine Helfer zum sicheren Lesen von JSON (strict-casts).
typedef Json = Map<String, dynamic>;

extension JsonRead on Json {
  String str(String key) => this[key] as String;
  String? strOrNull(String key) => this[key] as String?;
  int integer(String key) => (this[key] as num).toInt();
  int? intOrNull(String key) => (this[key] as num?)?.toInt();
  double number(String key) => (this[key] as num).toDouble();
  bool flag(String key) => this[key] as bool;
  DateTime time(String key) => DateTime.parse(this[key] as String);
  DateTime? timeOrNull(String key) {
    final value = this[key] as String?;
    return value == null ? null : DateTime.parse(value);
  }

  Json obj(String key) => this[key] as Json;
  Json? objOrNull(String key) => this[key] as Json?;

  List<T> list<T>(String key, T Function(Json) parse) => [
    for (final item in (this[key] as List<dynamic>? ?? const [])) parse(item as Json),
  ];

  List<String> strings(String key) => [
    for (final item in this[key] as List<dynamic>) item as String,
  ];
}

List<T> parseList<T>(Object? data, T Function(Json) parse) => [
  for (final item in data! as List<dynamic>) parse(item as Json),
];
