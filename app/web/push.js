// Kartenkiste – Brücke zwischen der Flutter-App und Web-Push des Browsers.
//
// Die App ruft window.kartenkistePush.* auf (siehe lib/core/push_web.dart). Alles liefert
// Promises mit einfachen Werten (Text), damit die Dart-Seite schlank bleibt.
(function () {
  'use strict';

  const WORKER = 'push_sw.js';

  function supported() {
    return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  }

  // iPhone/iPad: Web-Push gibt es nur in der App vom Home-Bildschirm (ab iOS 16.4).
  function isIos() {
    return /iPad|iPhone|iPod/.test(navigator.userAgent) ||
      (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  }

  function standalone() {
    return window.matchMedia('(display-mode: standalone)').matches ||
      window.navigator.standalone === true;
  }

  function base64UrlToBytes(text) {
    const padded = (text + '='.repeat((4 - (text.length % 4)) % 4))
      .replace(/-/g, '+').replace(/_/g, '/');
    const raw = atob(padded);
    const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
    return bytes;
  }

  async function registration() {
    return navigator.serviceWorker.register(WORKER, { scope: './' });
  }

  async function currentSubscription() {
    if (!supported()) return null;
    const reg = await navigator.serviceWorker.getRegistration('./');
    return reg ? reg.pushManager.getSubscription() : null;
  }

  window.kartenkistePush = {
    // 'unsupported' | 'install' (iPhone: erst zum Home-Bildschirm) | 'denied' | 'granted' | 'default'
    status: async function () {
      if (isIos() && !standalone()) return 'install';
      if (!supported()) return 'unsupported';
      return Notification.permission;
    },

    // Endpunkt dieses Geräts, falls angemeldet (sonst '').
    endpoint: async function () {
      const sub = await currentSubscription();
      return sub ? sub.endpoint : '';
    },

    // Erlaubnis holen und anmelden → JSON des Abos (endpoint + keys) oder Fehlertext 'error:…'.
    subscribe: async function (publicKey) {
      try {
        if (!supported()) return 'error:unsupported';
        const permission = await Notification.requestPermission();
        if (permission !== 'granted') return 'error:' + permission;
        const reg = await registration();
        await navigator.serviceWorker.ready;
        const key = base64UrlToBytes(publicKey);
        let sub = await reg.pushManager.getSubscription();
        // Anderer Server-Schlüssel (z. B. neu erzeugt) → altes Abo ersetzen.
        if (sub && sub.options && sub.options.applicationServerKey) {
          const old = new Uint8Array(sub.options.applicationServerKey);
          if (old.length !== key.length || old.some((b, i) => b !== key[i])) {
            await sub.unsubscribe();
            sub = null;
          }
        }
        if (!sub) {
          sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
        }
        return JSON.stringify(sub.toJSON());
      } catch (e) {
        return 'error:' + (e && e.message ? e.message : String(e));
      }
    },

    // Abmelden → bisheriger Endpunkt (für den Server) oder ''.
    unsubscribe: async function () {
      const sub = await currentSubscription();
      if (!sub) return '';
      const endpoint = sub.endpoint;
      await sub.unsubscribe();
      return endpoint;
    },
  };
})();
