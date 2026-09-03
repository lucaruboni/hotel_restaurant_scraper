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

  // --- Submit rapido delle note con Cmd/Ctrl+Invio ------------------------
  document.addEventListener("keydown", function (evento) {
    if ((evento.metaKey || evento.ctrlKey) && evento.key === "Enter") {
      var form = evento.target.closest("form[data-quick-submit]");
      if (form) form.submit();
    }
  });
})();
