// Kartenkiste – Datei aus der App speichern (z. B. CSV-Export). iPhone: öffnet die Vorschau
// mit „Teilen“ → „In Dateien sichern“.
(function () {
  'use strict';
  window.kartenkisteDownload = function (filename, text, mime) {
    const blob = new Blob([text], { type: mime || 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    return true;
  };
})();
