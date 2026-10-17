// Navigation (go_router). Ohne Sitzung führt jeder Weg zur Anmeldung.
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'app.dart';
import 'core/providers.dart';
import 'features/admin/admin_screens.dart';
import 'features/auth/auth_screens.dart';
import 'features/card/card_detail_screen.dart';
import 'features/collection/collection_screen.dart';
import 'features/dashboard/dashboard_screen.dart';
import 'features/more/more_screen.dart';
import 'features/scan/scan_screens.dart';
import 'features/search/search_screen.dart';
import 'features/shell/home_shell.dart';
import 'features/wishlist/wishlist_screen.dart';

const _publicPaths = {'/login', '/register', '/reset'};

final routerProvider = Provider<GoRouter>((ref) {
  // Router nur einmal bauen; Sitzungswechsel lösen ein erneutes Prüfen der Weiterleitung aus.
  final refresh = ValueNotifier<int>(0);
  ref
    ..listen(sessionProvider, (_, _) => refresh.value++)
    ..onDispose(refresh.dispose);

  return GoRouter(
    initialLocation: '/home',
    refreshListenable: refresh,
    redirect: (context, state) {
      final session = ref.read(sessionProvider);
      if (session.isLoading && !session.hasValue) return '/splash';
      final loggedIn = session.value != null;
      final path = state.matchedLocation;
      final public = _publicPaths.contains(path);
      if (!loggedIn) return public ? null : '/login';
      if (public || path == '/splash') return '/home';
      if (path.startsWith('/admin') && !(session.value?.isAdmin ?? false)) return '/home';
      return null;
    },
    routes: [
      GoRoute(path: '/splash', builder: (_, _) => const SplashScreen()),
      GoRoute(path: '/login', builder: (_, _) => const LoginScreen()),
      GoRoute(path: '/register', builder: (_, _) => const RegisterScreen()),
      GoRoute(path: '/reset', builder: (_, _) => const ResetPasswordScreen()),
      StatefulShellRoute.indexedStack(
        builder: (_, _, shell) => HomeShell(shell: shell),
        branches: [
          StatefulShellBranch(
            routes: [GoRoute(path: '/home', builder: (_, _) => const DashboardScreen())],
          ),
          StatefulShellBranch(
            routes: [GoRoute(path: '/collection', builder: (_, _) => const CollectionScreen())],
          ),
          StatefulShellBranch(
            routes: [GoRoute(path: '/search', builder: (_, _) => const SearchScreen())],
          ),
          StatefulShellBranch(
            routes: [GoRoute(path: '/lists', builder: (_, _) => const WishlistScreen())],
          ),
          StatefulShellBranch(
            routes: [GoRoute(path: '/more', builder: (_, _) => const MoreScreen())],
          ),
        ],
      ),
      GoRoute(
        path: '/card/:id',
        builder: (_, state) => CardDetailScreen(cardId: state.pathParameters['id']!),
      ),
      GoRoute(path: '/scan', builder: (_, _) => const ScanScreen()),
      GoRoute(path: '/scan/batch', builder: (_, _) => const BatchScanScreen()),
      GoRoute(path: '/scan/binder', builder: (_, _) => const BinderScanScreen()),
      GoRoute(path: '/settings', builder: (_, _) => const SettingsScreen()),
      GoRoute(path: '/sessions', builder: (_, _) => const SessionsScreen()),
      GoRoute(path: '/sets', builder: (_, _) => const SetOverviewScreen()),
      GoRoute(path: '/admin/users', builder: (_, _) => const AdminUsersScreen()),
      GoRoute(path: '/admin/invites', builder: (_, _) => const AdminInvitesScreen()),
      GoRoute(
        path: '/admin/users/:id',
        builder: (_, state) => AdminUserCollectionScreen(
          userId: state.pathParameters['id']!,
          name: state.uri.queryParameters['name'] ?? 'Nutzer',
        ),
      ),
    ],
  );
});
