// Kartenkiste – Live-Kamera für den Scanner: Vorschau, Standbilder (JPEG) und eine kleine
// Bewegungsmessung, damit nur ruhige, neue Bilder zur Erkennung gehen.
(function () {
  'use strict';
  const SAMPLE = 32; // 32×32 Graustufen reichen, um Bewegung und Bildwechsel zu erkennen
  const BLOCK = 4; // je Messpunkt 4×4 Pixel mitteln: Kamerarauschen (iPhone innen) zählt nicht
  // Alle erzeugten <video>: Flutter kann die Ansicht mehrfach anlegen (iOS). Gemessen wird am
  // sichtbaren, laufenden – nicht am zuletzt erzeugten, das evtl. nie Bilder liefert.
  const videos = [];
  let video = null;
  let stream = null;
  let previous = null;
  let lastShot = null;
  const work = document.createElement('canvas');

  /** Video mit Bild: bevorzugt eines, das im Dokument hängt. */
  function active() {
    const ready = videos.filter((v) => v.readyState >= 2 && v.videoWidth > 0);
    return ready.find((v) => v.isConnected) || ready[0] || null;
  }

  function sample() {
    const source = active();
    if (!source) return null;
    const size = SAMPLE * BLOCK;
    work.width = size; work.height = size;
    const context = work.getContext('2d', { willReadFrequently: true });
    context.drawImage(source, 0, 0, size, size);
    const data = context.getImageData(0, 0, size, size).data;
    const gray = new Float32Array(SAMPLE * SAMPLE);
    for (let y = 0; y < size; y++) {
      for (let x = 0; x < size; x++) {
        const i = (y * size + x) * 4;
        const cell = Math.floor(y / BLOCK) * SAMPLE + Math.floor(x / BLOCK);
        gray[cell] += (data[i] * 3 + data[i + 1] * 6 + data[i + 2]) / 10;
      }
    }
    for (let i = 0; i < gray.length; i++) gray[i] /= BLOCK * BLOCK;
    return gray;
  }

  function difference(a, b) {
    if (!a || !b) return 255;
    let sum = 0;
    for (let i = 0; i < a.length; i++) sum += Math.abs(a[i] - b[i]);
    return sum / a.length;
  }

  window.kartenkisteCamera = {
    createVideo: function () {
      video = document.createElement('video');
      videos.push(video);
      video.setAttribute('playsinline', '');
      video.muted = true;
      video.autoplay = true;
      video.style.width = '100%';
      video.style.height = '100%';
      video.style.objectFit = 'cover';
      if (stream) { video.srcObject = stream; video.play().catch(() => {}); }
      return video;
    },
    /** 'ok' | 'denied' | 'unsupported' */
    start: async function () {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return 'unsupported';
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } },
        });
      } catch (e) {
        return e && (e.name === 'NotAllowedError' || e.name === 'SecurityError') ? 'denied' : 'unsupported';
      }
      videos.forEach((v) => { v.srcObject = stream; v.play().catch(() => {}); });
      previous = null; lastShot = null;
      return 'ok';
    },
    stop: function () {
      if (stream) stream.getTracks().forEach((track) => track.stop());
      stream = null; previous = null; lastShot = null;
      videos.forEach((v) => { v.srcObject = null; });
      // Abgehängte Elemente vergessen (Bildschirm geschlossen), sichtbare behalten.
      const kept = videos.filter((v) => v.isConnected);
      videos.length = 0; videos.push(...kept);
    },
    /** "motion,change": Bewegung seit der letzten Messung und Abstand zum letzten Foto (0–255);
     *  "-1,-1", solange die Kamera kein Bild liefert. */
    measure: function () {
      const current = sample();
      if (!current) return '-1,-1';
      const motion = difference(current, previous);
      const change = difference(current, lastShot);
      previous = current;
      return motion.toFixed(1) + ',' + change.toFixed(1);
    },
    /** Aktuelles Bild als JPEG (längste Seite höchstens 1600 px); merkt es als „letztes Foto“.
     *  Mit Rahmen (Anteile der sichtbaren Ansicht, Breite > 0) nur dieser Ausschnitt plus Rand –
     *  umgerechnet über object-fit: cover. */
    frame: function (centerX, centerY, widthFraction, aspect, margin) {
      return new Promise((resolve) => {
        const source = active();
        if (!source) { resolve(null); return; }
        const vw = source.videoWidth, vh = source.videoHeight;
        let sx = 0, sy = 0, sw = vw, sh = vh;
        const ew = source.clientWidth, eh = source.clientHeight;
        if (widthFraction > 0 && ew > 0 && eh > 0) {
          const scale = Math.max(ew / vw, eh / vh); // cover
          const offsetX = (ew - vw * scale) / 2, offsetY = (eh - vh * scale) / 2;
          const gw = ew * widthFraction * (1 + 2 * margin);
          const gh = ew * widthFraction * aspect * (1 + 2 * margin);
          const gx = ew * centerX - gw / 2, gy = eh * centerY - gh / 2;
          sx = Math.max(0, (gx - offsetX) / scale);
          sy = Math.max(0, (gy - offsetY) / scale);
          sw = Math.min(vw - sx, gw / scale);
          sh = Math.min(vh - sy, gh / scale);
          if (sw < 16 || sh < 16) { sx = 0; sy = 0; sw = vw; sh = vh; }
        }
        const factor = Math.min(1, 1600 / Math.max(sw, sh));
        const canvas = document.createElement('canvas');
        canvas.width = Math.round(sw * factor);
        canvas.height = Math.round(sh * factor);
        canvas.getContext('2d').drawImage(source, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
        lastShot = sample();
        canvas.toBlob(async (blob) => {
          resolve(blob ? new Uint8Array(await blob.arrayBuffer()) : null);
        }, 'image/jpeg', 0.9);
      });
    },
  };
})();
