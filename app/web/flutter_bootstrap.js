{{flutter_js}}
{{flutter_build_config}}
// Bewusst ohne Flutters Service Worker: Er ist veraltet, meldet sich beim Start selbst wieder
// ab und würde dabei den Push-Worker (push_sw.js, gleiche Adresse „/“) mit abmelden.
_flutter.loader.load();
