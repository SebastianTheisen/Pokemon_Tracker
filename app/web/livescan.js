// Kartenkiste – Live-Kamera für den Scanner: Vorschau, Standbilder (JPEG), eine kleine
// Bewegungsmessung und eine Kartenprüfung im Rahmen, damit nur ruhige, neue Bilder MIT Karte
// zur Erkennung gehen.
(function () {
  'use strict';
  const SAMPLE = 32; // 32×32 Graustufen reichen, um Bewegung und Bildwechsel zu erkennen
  const BLOCK = 4; // je Messpunkt 4×4 Pixel mitteln: Kamerarauschen (iPhone innen) zählt nicht
  // Kartenprüfung: Rahmenbereich auf 96 px Breite (je 2×2 gemittelt), dann vier gerade Kanten
  // im Kartenformat suchen. Gemessen an iPhone-Bildern und Testfotos (scratch detect/bench.py):
  // 0 von 18 leeren Bildern lösen aus (Boden, Stoff, halbe Karte, Binder-Stege).
  const CARD_W = 96;
  const CARD = { ratio: 2.0, cover: 0.6, aspectMin: 0.55, aspectMax: 0.88, size: 0.5 };
  // Alle erzeugten <video>: Flutter kann die Ansicht mehrfach anlegen (iOS). Gemessen wird am
  // sichtbaren, laufenden – nicht am zuletzt erzeugten, das evtl. nie Bilder liefert.
  const videos = [];
  let video = null;
  let stream = null;
  let previous = null;
  let lastShot = null;
  let lastCrop = null;
  const work = document.createElement('canvas');
  const cardCanvas = document.createElement('canvas');

  /** Video mit Bild: bevorzugt eines, das im Dokument hängt. */
  function active() {
    const ready = videos.filter((v) => v.readyState >= 2 && v.videoWidth > 0);
    return ready.find((v) => v.isConnected) || ready[0] || null;
  }

  function sample(source) {
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

  /** Rahmen (Anteile der sichtbaren Ansicht) plus Rand → Rechteck im Videobild
   *  (umgerechnet über object-fit: cover). Breite 0 = ganzes Bild. */
  function guideRect(source, guide) {
    const vw = source.videoWidth, vh = source.videoHeight;
    const full = { x: 0, y: 0, w: vw, h: vh };
    const ew = source.clientWidth, eh = source.clientHeight;
    if (!guide || !(guide.widthFraction > 0) || ew <= 0 || eh <= 0) return full;
    const scale = Math.max(ew / vw, eh / vh);
    const offsetX = (ew - vw * scale) / 2, offsetY = (eh - vh * scale) / 2;
    const gw = ew * guide.widthFraction * (1 + 2 * guide.margin);
    const gh = ew * guide.widthFraction * guide.aspect * (1 + 2 * guide.margin);
    const gx = ew * guide.centerX - gw / 2, gy = eh * guide.centerY - gh / 2;
    const x = Math.max(0, (gx - offsetX) / scale), y = Math.max(0, (gy - offsetY) / scale);
    const w = Math.min(vw - x, gw / scale), h = Math.min(vh - y, gh / scale);
    return w < 16 || h < 16 ? full : { x: x, y: y, w: w, h: h };
  }

  function strongest(profile, from, to) {
    let index = from;
    for (let i = from; i < to; i++) if (profile[i] > profile[index]) index = i;
    return index;
  }

  function median(values) {
    const sorted = Float32Array.from(values).sort();
    return sorted.length ? sorted[sorted.length >> 1] : 0;
  }

  /** Liegt eine Karte im Rahmen? Vier gerade, durchgehende Kanten (links/rechts/oben/unten)
   *  im Kartenformat (auch Slab), mindestens halb so breit wie der Rahmen. */
  function cardInFrame(source, rect) {
    const W = CARD_W, H = Math.max(8, Math.round(CARD_W * rect.h / rect.w));
    cardCanvas.width = W * 2; cardCanvas.height = H * 2;
    const context = cardCanvas.getContext('2d', { willReadFrequently: true });
    context.drawImage(source, rect.x, rect.y, rect.w, rect.h, 0, 0, W * 2, H * 2);
    const data = context.getImageData(0, 0, W * 2, H * 2).data;
    const g = new Float32Array(W * H);
    for (let y = 0; y < H * 2; y++) {
      for (let x = 0; x < W * 2; x++) {
        const i = (y * W * 2 + x) * 4;
        g[(y >> 1) * W + (x >> 1)] += (data[i] * 0.3 + data[i + 1] * 0.6 + data[i + 2] * 0.1) / 4;
      }
    }
    const gx = new Float32Array(W * H), gy = new Float32Array(W * H);
    for (let y = 0; y < H; y++) {
      for (let x = 1; x < W - 1; x++) gx[y * W + x] = Math.abs(g[y * W + x + 1] - g[y * W + x - 1]);
    }
    for (let y = 1; y < H - 1; y++) {
      for (let x = 0; x < W; x++) gy[y * W + x] = Math.abs(g[(y + 1) * W + x] - g[(y - 1) * W + x]);
    }
    const y0 = Math.floor(0.15 * H), y1 = Math.floor(0.85 * H);
    const x0 = Math.floor(0.15 * W), x1 = Math.floor(0.85 * W);
    const col = new Float32Array(W), row = new Float32Array(H);
    const gxInner = [], gyInner = [];
    for (let y = y0; y < y1; y++) {
      for (let x = 0; x < W; x++) { col[x] += gx[y * W + x] / (y1 - y0); gxInner.push(gx[y * W + x]); }
    }
    for (let y = 0; y < H; y++) {
      for (let x = x0; x < x1; x++) { row[y] += gy[y * W + x] / (x1 - x0); gyInner.push(gy[y * W + x]); }
    }
    const baseC = median(col) + 1, baseR = median(row) + 1;
    const left = strongest(col, 2, Math.floor(0.4 * W)), right = strongest(col, Math.floor(0.6 * W), W - 2);
    const top = strongest(row, 2, Math.floor(0.4 * H)), bottom = strongest(row, Math.floor(0.6 * H), H - 2);
    const limitX = Math.max(8, 2.5 * median(gxInner)), limitY = Math.max(8, 2.5 * median(gyInner));
    const coverCol = (x) => {
      let hits = 0;
      for (let y = y0; y < y1; y++) {
        let best = 0;
        for (let d = -1; d <= 1; d++) if (x + d >= 0 && x + d < W) best = Math.max(best, gx[y * W + x + d]);
        if (best > limitX) hits++;
      }
      return hits / (y1 - y0);
    };
    const coverRow = (y) => {
      let hits = 0;
      for (let x = x0; x < x1; x++) {
        let best = 0;
        for (let d = -1; d <= 1; d++) if (y + d >= 0 && y + d < H) best = Math.max(best, gy[(y + d) * W + x]);
        if (best > limitY) hits++;
      }
      return hits / (x1 - x0);
    };
    const ratio = Math.min(col[left] / baseC, col[right] / baseC, row[top] / baseR, row[bottom] / baseR);
    const cover = Math.min(coverCol(left), coverCol(right), coverRow(top), coverRow(bottom));
    const aspect = (right - left) / Math.max(1, bottom - top);
    const size = (right - left) / W;
    return ratio >= CARD.ratio && cover >= CARD.cover && aspect >= CARD.aspectMin &&
      aspect <= CARD.aspectMax && size >= CARD.size;
  }

  function toJpeg(canvas, quality) {
    return new Promise((resolve) => canvas.toBlob(async (blob) => {
      resolve(blob ? new Uint8Array(await blob.arrayBuffer()) : null);
    }, 'image/jpeg', quality));
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
      previous = null; lastShot = null; lastCrop = null;
      return 'ok';
    },
    stop: function () {
      if (stream) stream.getTracks().forEach((track) => track.stop());
      stream = null; previous = null; lastShot = null; lastCrop = null;
      videos.forEach((v) => { v.srcObject = null; });
      // Abgehängte Elemente vergessen (Bildschirm geschlossen), sichtbare behalten.
      const kept = videos.filter((v) => v.isConnected);
      videos.length = 0; videos.push(...kept);
    },
    /** "motion,change,card": Bewegung seit der letzten Messung, Abstand zum letzten Foto
     *  (0–255) und 1/0 für „Karte im Rahmen“; "-1,-1,0", solange die Kamera kein Bild liefert. */
    measure: function (centerX, centerY, widthFraction, aspect, margin) {
      const source = active();
      if (!source) return '-1,-1,0';
      const current = sample(source);
      const motion = difference(current, previous);
      const change = difference(current, lastShot);
      previous = current;
      const guide = { centerX, centerY, widthFraction, aspect, margin };
      const card = widthFraction > 0 && cardInFrame(source, guideRect(source, guide)) ? 1 : 0;
      return motion.toFixed(1) + ',' + change.toFixed(1) + ',' + card;
    },
    /** Ganzes Bild als JPEG (längste Seite höchstens 1600 px) zur Erkennung – wie beim
     *  normalen Foto-Scan; der Rahmenausschnitt (Bestätigung) liegt danach in lastCrop().
     *  Merkt das Bild als „letztes Foto“. */
    frame: function (centerX, centerY, widthFraction, aspect, margin) {
      const source = active();
      if (!source) return Promise.resolve(null);
      const vw = source.videoWidth, vh = source.videoHeight;
      const factor = Math.min(1, 1600 / Math.max(vw, vh));
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(vw * factor);
      canvas.height = Math.round(vh * factor);
      canvas.getContext('2d').drawImage(source, 0, 0, canvas.width, canvas.height);
      const rect = guideRect(source, { centerX, centerY, widthFraction, aspect, margin });
      const crop = document.createElement('canvas');
      const cropFactor = Math.min(1, 480 / Math.max(rect.w, rect.h));
      crop.width = Math.round(rect.w * cropFactor);
      crop.height = Math.round(rect.h * cropFactor);
      crop.getContext('2d').drawImage(source, rect.x, rect.y, rect.w, rect.h, 0, 0, crop.width, crop.height);
      lastShot = sample(source);
      return Promise.all([toJpeg(canvas, 0.88), toJpeg(crop, 0.8)]).then(([full, small]) => {
        lastCrop = small;
        return full;
      });
    },
    /** Rahmenausschnitt des letzten Fotos (klein, für die Bestätigung). */
    lastCrop: function () { return lastCrop; },
    /** Nur für Messungen: Kartenprüfung auf einem ganzen Bild (<img>/<canvas>). */
    cardInImage: function (image) {
      return cardInFrame(image, { x: 0, y: 0, w: image.naturalWidth || image.width, h: image.naturalHeight || image.height });
    },
  };
})();
