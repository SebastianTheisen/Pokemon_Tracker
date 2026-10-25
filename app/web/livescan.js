// Kartenkiste – Live-Kamera für den Scanner: Vorschau, Standbilder (JPEG) und eine kleine
// Bewegungsmessung, damit nur ruhige, neue Bilder zur Erkennung gehen.
(function () {
  'use strict';
  const SAMPLE = 32; // 32×32 Graustufen reichen, um Bewegung und Bildwechsel zu erkennen
  let video = null;
  let stream = null;
  let previous = null;
  let lastShot = null;
  const work = document.createElement('canvas');

  function sample() {
    if (!video || video.readyState < 2) return null;
    work.width = SAMPLE; work.height = SAMPLE;
    const context = work.getContext('2d', { willReadFrequently: true });
    context.drawImage(video, 0, 0, SAMPLE, SAMPLE);
    const data = context.getImageData(0, 0, SAMPLE, SAMPLE).data;
    const gray = new Uint8Array(SAMPLE * SAMPLE);
    for (let i = 0; i < gray.length; i++) {
      gray[i] = (data[i * 4] * 3 + data[i * 4 + 1] * 6 + data[i * 4 + 2]) / 10;
    }
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
      if (video) { video.srcObject = stream; video.play().catch(() => {}); }
      previous = null; lastShot = null;
      return 'ok';
    },
    stop: function () {
      if (stream) stream.getTracks().forEach((track) => track.stop());
      stream = null; previous = null; lastShot = null;
      if (video) video.srcObject = null;
    },
    /** "motion,change": Bewegung seit der letzten Messung und Abstand zum letzten Foto (0–255). */
    measure: function () {
      const current = sample();
      if (!current) return '255,0';
      const motion = difference(current, previous);
      const change = difference(current, lastShot);
      previous = current;
      return motion.toFixed(1) + ',' + change.toFixed(1);
    },
    /** Aktuelles Bild als JPEG (längste Seite höchstens 1600 px); merkt es als „letztes Foto“. */
    frame: function () {
      return new Promise((resolve) => {
        if (!video || video.readyState < 2) { resolve(null); return; }
        const scale = Math.min(1, 1600 / Math.max(video.videoWidth, video.videoHeight));
        const canvas = document.createElement('canvas');
        canvas.width = Math.round(video.videoWidth * scale);
        canvas.height = Math.round(video.videoHeight * scale);
        canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
        lastShot = sample();
        canvas.toBlob(async (blob) => {
          resolve(blob ? new Uint8Array(await blob.arrayBuffer()) : null);
        }, 'image/jpeg', 0.88);
      });
    },
  };
})();
