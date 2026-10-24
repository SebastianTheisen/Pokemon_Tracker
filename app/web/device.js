// Kartenkiste – Gerätefunktionen für die Web-App: Neigung (Holo-Effekt), Teilen von Bildern,
// Installieren als App (Android-Abfrage, iPhone-Hinweis).
(function () {
  'use strict';
  let installEvent = null;
  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault(); // eigener Knopf in der App statt Browser-Leiste
    installEvent = event;
  });
  window.addEventListener('appinstalled', () => { installEvent = null; });

  let tiltHandler = null;

  window.kartenkisteDevice = {
    /** iPhone verlangt eine Erlaubnis (nur nach einem Tipp); andere Browser liefern direkt. */
    tiltPermission: async function () {
      if (typeof DeviceOrientationEvent === 'undefined') return false;
      if (typeof DeviceOrientationEvent.requestPermission === 'function') {
        try { return (await DeviceOrientationEvent.requestPermission()) === 'granted'; }
        catch (e) { return false; }
      }
      return true;
    },
    tiltStart: function (callback) {
      window.kartenkisteDevice.tiltStop();
      tiltHandler = (e) => callback(e.beta || 0, e.gamma || 0);
      window.addEventListener('deviceorientation', tiltHandler);
    },
    tiltStop: function () {
      if (tiltHandler) window.removeEventListener('deviceorientation', tiltHandler);
      tiltHandler = null;
    },
    /** 'shared' | 'downloaded' | 'cancelled' */
    shareImage: async function (bytes, filename, text) {
      const file = new File([bytes], filename, { type: 'image/png' });
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        try { await navigator.share({ files: [file], text: text }); return 'shared'; }
        catch (e) { return e && e.name === 'AbortError' ? 'cancelled' : 'failed'; }
      }
      const url = URL.createObjectURL(file);
      const link = document.createElement('a');
      link.href = url; link.download = filename;
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
      return 'downloaded';
    },
    /** 'installed' | 'prompt' (Android/Chrome) | 'ios' (Safari: Teilen → Home-Bildschirm) | 'none' */
    installState: function () {
      const standalone = window.matchMedia('(display-mode: standalone)').matches ||
        window.navigator.standalone === true;
      if (standalone) return 'installed';
      if (installEvent) return 'prompt';
      const ua = navigator.userAgent || '';
      const ios = /iPhone|iPad|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
      return ios ? 'ios' : 'none';
    },
    install: async function () {
      if (!installEvent) return false;
      installEvent.prompt();
      const choice = await installEvent.userChoice;
      installEvent = null;
      return choice && choice.outcome === 'accepted';
    },
  };
})();
