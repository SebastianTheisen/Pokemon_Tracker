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
    /** Aktuelles Bild als JPEG (längste Seite höchstens 1600 px); merkt es als „letztes Foto“. */
    frame: function () {
      return new Promise((resolve) => {
        const source = active();
        if (!source) { resolve(null); return; }
        const scale = Math.min(1, 1600 / Math.max(source.videoWidth, source.videoHeight));
        const canvas = document.createElement('canvas');
        canvas.width = Math.round(source.videoWidth * scale);
        canvas.height = Math.round(source.videoHeight * scale);
        canvas.getContext('2d').drawImage(source, 0, 0, canvas.width, canvas.height);
        lastShot = sample();
        canvas.toBlob(async (blob) => {
          resolve(blob ? new Uint8Array(await blob.arrayBuffer()) : null);
        }, 'image/jpeg', 0.88);
      });
    },
  };
})();
