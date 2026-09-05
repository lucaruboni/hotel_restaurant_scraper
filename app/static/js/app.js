/* Interazioni leggere: tema, polling job, conferme, autosize textarea.
   Nessuna dipendenza esterna: la CSP consente solo script self. */

(function () {
  "use strict";

  // --- Tema chiaro/scuro, memorizzato sul dispositivo ---------------------
  var STORAGE_KEY = "horeca-theme";

  function applicaTema(tema) {
    if (tema === "light" || tema === "dark") {
      document.documentElement.setAttribute("data-theme", tema);
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
  }

  function temaSalvato() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch (e) {
      return null;
    }
  }

  applicaTema(temaSalvato());

  document.addEventListener("click", function (evento) {
    var toggle = evento.target.closest("[data-theme-toggle]");
    if (!toggle) return;

    var corrente = document.documentElement.getAttribute("data-theme");
    var scuroDiSistema = window.matchMedia("(prefers-color-scheme: dark)").matches;
    if (!corrente) corrente = scuroDiSistema ? "dark" : "light";
    var nuovo = corrente === "dark" ? "light" : "dark";

    applicaTema(nuovo);
    try {
      localStorage.setItem(STORAGE_KEY, nuovo);
    } catch (e) {
      /* modalità privata: il tema resta valido per questa sessione */
    }
  });

  // --- Conferme per le azioni distruttive ---------------------------------
  document.addEventListener("submit", function (evento) {
    var form = evento.target;
    var messaggio = form.getAttribute("data-conferma");
    if (messaggio && !window.confirm(messaggio)) {
      evento.preventDefault();
    }
  });

  // --- Aggiornamento live della tabella dei job di scraping ---------------
  var contenitoreJob = document.getElementById("jobs-live");
  if (contenitoreJob) {
    var intervallo = setInterval(function () {
      fetch("/scrape/stato", { headers: { "X-Requested-With": "fetch" } })
        .then(function (r) {
          if (!r.ok) throw new Error("stato non disponibile");
          return r.text();
        })
        .then(function (html) {
          contenitoreJob.innerHTML = html;
          if (!contenitoreJob.querySelector("[data-job-attivo]")) {
            clearInterval(intervallo);
          }
        })
        .catch(function () {
          clearInterval(intervallo);
        });
    }, 3000);
  }

  // --- Textarea che cresce con il contenuto -------------------------------
  function autosize(el) {
    el.style.height = "auto";
    el.style.height = el.scrollHeight + "px";
  }
  document.querySelectorAll("textarea[data-autosize]").forEach(function (el) {
    autosize(el);
    el.addEventListener("input", function () {
      autosize(el);
    });
  });

  // --- Copia negli appunti (per incollare in chat con Claude) --------------
  function mostraEsitoCopia(bottone, testo, msDurata) {
    var originale = bottone.textContent;
    bottone.textContent = testo;
    bottone.disabled = true;
    setTimeout(function () {
      bottone.textContent = originale;
      bottone.disabled = false;
    }, msDurata || 1600);
  }

  function copiaTesto(testo, bottone) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(testo).then(
        function () { mostraEsitoCopia(bottone, "Copiato ✓"); },
        function () { mostraEsitoCopia(bottone, "Errore"); }
      );
      return;
    }
    // Fallback per contesti senza Clipboard API (es. pagina non servita in HTTPS).
    var area = document.createElement("textarea");
    area.value = testo;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    try {
      document.execCommand("copy");
      mostraEsitoCopia(bottone, "Copiato ✓");
    } catch (e) {
      mostraEsitoCopia(bottone, "Errore");
    }
    document.body.removeChild(area);
  }

  document.addEventListener("click", function (evento) {
    var bottone = evento.target.closest("[data-copy-text], [data-copy-url]");
    if (!bottone) return;
    evento.preventDefault();

    if (bottone.hasAttribute("data-copy-text")) {
      copiaTesto(bottone.getAttribute("data-copy-text"), bottone);
      return;
    }

    var url = bottone.getAttribute("data-copy-url");
    fetch(url, { headers: { "X-Requested-With": "fetch" } })
      .then(function (r) {
        if (!r.ok) throw new Error("richiesta fallita");
        return r.text();
      })
      .then(function (testo) { copiaTesto(testo, bottone); })
      .catch(function () { mostraEsitoCopia(bottone, "Errore"); });
  });

  // --- Categorie disponibili in base alla sorgente scelta ------------------
  var selettoreSorgente = document.querySelector("[data-categoria-sorgente]");
  if (selettoreSorgente) {
    var caselleCategoria = document.querySelectorAll('input[name="categorie"]');

    var aggiornaCategorie = function () {
      var sorgente = selettoreSorgente.value;
      caselleCategoria.forEach(function (casella) {
        var sorgentiSupportate = (casella.getAttribute("data-sorgenti") || "").split(",");
        var compatibile = sorgentiSupportate.indexOf(sorgente) !== -1;
        casella.disabled = !compatibile;
        if (!compatibile) casella.checked = false;
      });
    };

    selettoreSorgente.addEventListener("change", aggiornaCategorie);
    aggiornaCategorie();
  }

  // --- Submit rapido delle note con Cmd/Ctrl+Invio ------------------------
  document.addEventListener("keydown", function (evento) {
    if ((evento.metaKey || evento.ctrlKey) && evento.key === "Enter") {
      var form = evento.target.closest("form[data-quick-submit]");
      if (form) form.submit();
    }
  });
})();
