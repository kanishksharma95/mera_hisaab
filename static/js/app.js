/* Mera Hisaab — front-end behaviour: toasts + animated stat counters. */
(function () {
  "use strict";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---- Theme (light/dark) ----------------------------------------------
  function currentTheme() {
    return document.documentElement.getAttribute("data-bs-theme") || "light";
  }
  function applyTheme(theme) {
    document.documentElement.setAttribute("data-bs-theme", theme);
    try { localStorage.setItem("mh-theme", theme); } catch (e) {}
    document.querySelectorAll("[data-theme-icon]").forEach(function (el) {
      el.className = "bi " + (theme === "dark" ? "bi-sun" : "bi-moon-stars");
    });
    document.querySelectorAll("[data-theme-label]").forEach(function (el) {
      el.textContent = theme === "dark" ? el.getAttribute("data-label-light") || "Light"
                                        : el.getAttribute("data-label-dark") || "Dark";
    });
  }
  // Exposed for onclick handlers on the toggle button.
  window.mhToggleTheme = function () {
    applyTheme(currentTheme() === "dark" ? "light" : "dark");
  };
  function initTheme() { applyTheme(currentTheme()); }

  // ---- Toasts ----------------------------------------------------------
  function initToasts() {
    if (!window.bootstrap) return;
    document.querySelectorAll(".mh-toast").forEach(function (el) {
      const toast = new bootstrap.Toast(el, { autohide: true });
      toast.show();
    });
  }

  // ---- Count-up animation for stat cards --------------------------------
  // Any element with [data-countup] animates from 0 to its numeric value.
  // Optional: data-prefix (e.g. "₹"), data-decimals.
  function formatNumber(value, decimals) {
    return value.toLocaleString("en-IN", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  }

  function animateCount(el) {
    const target = parseFloat(el.getAttribute("data-countup")) || 0;
    const prefix = el.getAttribute("data-prefix") || "";
    const decimals = parseInt(el.getAttribute("data-decimals") || "0", 10);

    if (reduceMotion || target === 0) {
      el.textContent = prefix + formatNumber(target, decimals);
      return;
    }

    const duration = 900;
    const start = performance.now();
    function tick(now) {
      const p = Math.min((now - start) / duration, 1);
      // easeOutCubic
      const eased = 1 - Math.pow(1 - p, 3);
      el.textContent = prefix + formatNumber(target * eased, decimals);
      if (p < 1) requestAnimationFrame(tick);
      else el.textContent = prefix + formatNumber(target, decimals);
    }
    requestAnimationFrame(tick);
  }

  function initCounters() {
    const els = document.querySelectorAll("[data-countup]");
    if (!els.length) return;
    if (!("IntersectionObserver" in window)) {
      els.forEach(animateCount);
      return;
    }
    const io = new IntersectionObserver(function (entries, obs) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          animateCount(entry.target);
          obs.unobserve(entry.target);
        }
      });
    }, { threshold: 0.4 });
    els.forEach(function (el) { io.observe(el); });
  }

  // ---- Form submit feedback --------------------------------------------
  // On submit, show a spinner in the submit button and guard against
  // double-submission. Progressive enhancement — works without HTMX.
  function initFormLoading() {
    document.addEventListener("submit", function (e) {
      const form = e.target;
      if (!(form instanceof HTMLFormElement)) return;
      const btn = form.querySelector('button[type="submit"], input[type="submit"]');
      if (!btn || btn.dataset.mhLoading) return;
      btn.dataset.mhLoading = "1";
      const label = btn.textContent.trim();
      btn.innerHTML =
        '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>' +
        '<span class="mh-btn-label">' + label + "</span>";
      // Disable after the current tick so the button's value still submits.
      setTimeout(function () { btn.setAttribute("disabled", "disabled"); }, 0);
    });
  }

  function init() {
    initTheme();
    initToasts();
    initCounters();
    initFormLoading();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
