/* ==========================================================================
   MediFinder × Lithos — Core client
   Dark only, no light/dark toggle. Spotlight reveal + toasts + map
   ========================================================================== */
(function () {
  "use strict";

  /* ---------- Force dark, remove toggle ---------- */
  document.documentElement.setAttribute("data-theme", "dark");
  localStorage.setItem("mf-theme", "dark");

  /* ---------- Mobile nav — Vesper + Lithos compat ---------- */
  document.addEventListener("click", (e) => {
    const toggle = e.target.closest("#navToggle") || e.target.closest(".nav-lithos-burger") || e.target.closest(".burger");
    if (toggle) {
      const isOpen = document.body.classList.toggle("menu-open");
      toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
      toggle.setAttribute("aria-label", isOpen ? "Close menu" : "Open menu");
      // legacy navLinks
      const nl = document.getElementById("navLinks");
      if (nl) {
        if (isOpen) nl.classList.add("open");
        else nl.classList.remove("open");
      }
    } else if (!e.target.closest("#site-nav") && !e.target.closest(".mobile-nav") && !e.target.closest(".nav-lithos-burger") && !e.target.closest(".burger") && !e.target.closest("#navLinks")) {
      if (document.body.classList.contains("menu-open")) {
        document.body.classList.remove("menu-open");
        document.querySelectorAll(".nav-lithos-burger, .burger, #navToggle").forEach(b=>{b.setAttribute("aria-expanded","false");b.setAttribute("aria-label","Open menu")});
        const nl = document.getElementById("navLinks");
        if (nl) nl.classList.remove("open");
      }
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && document.body.classList.contains("menu-open")) {
      document.body.classList.remove("menu-open");
      document.querySelectorAll(".nav-lithos-burger, .burger, #navToggle").forEach(b=>{b.setAttribute("aria-expanded","false")});
      const nl = document.getElementById("navLinks");
      if (nl) nl.classList.remove("open");
      const modal = document.getElementById("reserveModal");
      if (modal?.classList.contains("open")) {
        modal.classList.remove("open");
        document.body.style.overflow = "";
      }
    }
  });
  window.addEventListener("resize", () => {
    if (window.matchMedia("(min-width: 901px)").matches && document.body.classList.contains("menu-open")) {
      document.body.classList.remove("menu-open");
    }
  });

  /* ---------- Toasts — dark glass ---------- */
  window.MF = window.MF || {};
  MF.toast = function (message, type = "info", title) {
    let wrap = document.getElementById("toastWrap");
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.id = "toastWrap";
      wrap.className = "toast-wrap";
      wrap.setAttribute("aria-live","polite");
      wrap.setAttribute("role","region");
      wrap.setAttribute("aria-label","Notifications");
      document.body.appendChild(wrap);
    }
    const iconMap = { success: "bi-check-circle-fill", error: "bi-exclamation-triangle-fill", warning: "bi-exclamation-circle-fill", info: "bi-info-circle-fill" };
    const icon = iconMap[type] || "bi-info-circle";
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.setAttribute("role","status");
    el.innerHTML = `<i class="bi ${icon}" aria-hidden="true"></i>
      <div>${title ? `<strong>${title}</strong>` : ""}<p>${message}</p></div>
      <button class="modal-close" style="margin-left:auto;min-width:32px;min-height:32px" aria-label="Dismiss"><i class="bi bi-x" aria-hidden="true"></i></button>`;
    wrap.appendChild(el);
    el.querySelector("button").addEventListener("click", ()=> el.remove());
    if (!window.MFMotion) {
      setTimeout(() => {
        el.style.transition = "opacity .28s ease, transform .28s ease";
        el.style.opacity = "0";
        el.style.transform = "translateX(16px)";
        setTimeout(() => el.remove(), 300);
      }, 4000);
    }
  };

  /* ---------- Geolocation ---------- */
  MF.userPos = null;
  MF.getUserLocation = function (opts = {}) {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) return reject(new Error("Geolocation not supported"));
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          MF.userPos = { lat: pos.coords.latitude, lng: pos.coords.longitude };
          resolve(MF.userPos);
        },
        (err) => reject(err),
        { enableHighAccuracy: true, timeout: 9000, maximumAge: 60000, ...opts }
      );
    });
  };
  MF.reverseGeocode = async function (lat, lng) {
    try {
      const r = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}&zoom=12`);
      const d = await r.json();
      const a = d.address || {};
      return a.city || a.town || a.village || a.suburb || a.county || a.state_district || "";
    } catch { return ""; }
  };

  /* ---------- Map helpers — dark ---------- */
  MF.tileUrl = function () {
    // Always dark for lithos
    return "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
  };
  MF.tileAttrib = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>';
  MF.makeIcon = function (variant = "teal") {
    const glyph = variant === "user" ? "" : '<i class="bi bi-capsule-pill" aria-hidden="true"></i>';
    return L.divIcon({
      className: "mf-pin",
      html: `<div class="pin pin-${variant}"><div class="pulse"></div><div class="pin-body">${glyph}</div><div class="pin-shadow"></div></div>`,
      iconSize: [34, 42],
      iconAnchor: [17, 40],
      popupAnchor: [0, -36],
    });
  };
  MF.addTileLayer = function (map) {
    const layer = L.tileLayer(MF.tileUrl(), { maxZoom: 19, attribution: MF.tileAttrib }).addTo(map);
    return layer;
  };

  /* ---------- Spotlight reveal — Lithos core mechanic ---------- */
  const SPOTLIGHT_R = 260;
  const BG_IMAGE_1 = "https://images.higgs.ai/?default=1&output=webp&url=https%3A%2F%2Fd8j0ntlcm91z4.cloudfront.net%2Fuser_38xzZboKViGWJOttwIXH07lWA1P%2Fhf_20260609_195923_b0ba8ace-1d1d-4f2c-9a28-1ab84b330680.png&w=1280&q=85";
  const BG_IMAGE_2 = "https://images.higgs.ai/?default=1&output=webp&url=https%3A%2F%2Fd8j0ntlcm91z4.cloudfront.net%2Fuser_38xzZboKViGWJOttwIXH07lWA1P%2Fhf_20260609_201152_bba90a12-bf12-459f-91f0-51f237dbaf3b.png&w=1280&q=85";

  function initSpotlight() {
    const hero = document.querySelector(".hero-lithos");
    if (!hero) return;
    const baseLayer = hero.querySelector(".base-layer");
    const revealLayer = hero.querySelector(".reveal-layer");
    const canvas = hero.querySelector(".reveal-canvas");
    if (!baseLayer || !revealLayer || !canvas) return;

    baseLayer.style.backgroundImage = `url("${BG_IMAGE_1}")`;
    revealLayer.style.backgroundImage = `url("${BG_IMAGE_2}")`;

    const ctx = canvas.getContext("2d", { willReadFrequently: false });
    if (!ctx) return;

    function resizeCanvas() {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    }
    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);

    const mouse = { x: -999, y: -999 };
    const smooth = { x: -999, y: -999 };
    let cursorPos = { x: -999, y: -999 };
    let rafRef = null;

    function onMouseMove(e) {
      mouse.x = e.clientX;
      mouse.y = e.clientY;
    }
    window.addEventListener("mousemove", onMouseMove, { passive: true });
    window.addEventListener("touchmove", (e) => {
      if (e.touches[0]) {
        mouse.x = e.touches[0].clientX;
        mouse.y = e.touches[0].clientY;
      }
    }, { passive: true });

    function renderMask() {
      // lerp smoothing 0.1
      smooth.x += (mouse.x - smooth.x) * 0.1;
      smooth.y += (mouse.y - smooth.y) * 0.1;
      cursorPos.x = smooth.x;
      cursorPos.y = smooth.y;

      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const gradient = ctx.createRadialGradient(cursorPos.x, cursorPos.y, 0, cursorPos.x, cursorPos.y, SPOTLIGHT_R);
      gradient.addColorStop(0, "rgba(255,255,255,1)");
      gradient.addColorStop(0.4, "rgba(255,255,255,1)");
      gradient.addColorStop(0.6, "rgba(255,255,255,0.75)");
      gradient.addColorStop(0.75, "rgba(255,255,255,0.4)");
      gradient.addColorStop(0.88, "rgba(255,255,255,0.12)");
      gradient.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(cursorPos.x, cursorPos.y, SPOTLIGHT_R, 0, Math.PI * 2);
      ctx.fill();

      try {
        const dataUrl = canvas.toDataURL();
        revealLayer.style.maskImage = `url(${dataUrl})`;
        revealLayer.style.webkitMaskImage = `url(${dataUrl})`;
        revealLayer.style.maskSize = "100% 100%";
        revealLayer.style.webkitMaskSize = "100% 100%";
        revealLayer.style.maskRepeat = "no-repeat";
        revealLayer.style.webkitMaskRepeat = "no-repeat";
      } catch {}

      rafRef = requestAnimationFrame(renderMask);
    }
    rafRef = requestAnimationFrame(renderMask);

    // cleanup on page hide
    window.addEventListener("beforeunload", () => {
      if (rafRef) cancelAnimationFrame(rafRef);
      window.removeEventListener("mousemove", onMouseMove);
    });
  }

  /* ---------- Reservation modal ---------- */
  let lastFocused = null;
  MF.openReserve = function (medId, medName, shopName) {
    lastFocused = document.activeElement;
    let back = document.getElementById("reserveModal");
    if (!back) {
      back = document.createElement("div");
      back.id = "reserveModal";
      back.className = "modal-back";
      back.setAttribute("role","presentation");
      back.innerHTML = `
        <div class="modal" role="dialog" aria-modal="true" aria-labelledby="reserveTitle" aria-describedby="reserveSub">
          <div class="modal-head">
            <h3 id="reserveTitle">Reserve medicine</h3>
            <button class="modal-close" data-close aria-label="Close dialog">&times;</button>
          </div>
          <form class="modal-body" id="reserveForm" novalidate>
            <p class="small mb-3" id="reserveSub" style="color:var(--muted)"></p>
            <input type="hidden" name="med_id" id="reserveMedId">
            <div class="mb-3">
              <label class="form-label required" for="reserveName">Your name</label>
              <input type="text" name="name" id="reserveName" class="form-control" placeholder="Full name" required autocomplete="name" aria-required="true">
              <div class="form-error" id="err-name" role="alert" hidden></div>
            </div>
            <div class="mb-3">
              <label class="form-label required" for="reservePhone">Phone number</label>
              <input type="tel" name="phone" id="reservePhone" class="form-control" placeholder="For the pharmacy to confirm pickup" required autocomplete="tel" inputmode="numeric" aria-required="true" aria-describedby="phoneHelp">
              <small class="form-hint" id="phoneHelp">We'll share this with the pharmacy only</small>
              <div class="form-error" id="err-phone" role="alert" hidden></div>
            </div>
            <div class="row mb-3" style="gap:12px">
              <div style="flex:1">
                <label class="form-label" for="reserveQty">Quantity</label>
                <input type="number" name="quantity" id="reserveQty" class="form-control" value="1" min="1" max="99" inputmode="numeric">
              </div>
            </div>
            <div class="mb-2">
              <label class="form-label" for="reserveNote">Note (optional)</label>
              <textarea name="note" id="reserveNote" class="form-control" rows="2" placeholder="e.g. I'll collect around 6 PM"></textarea>
            </div>
            <small class="form-hint"><i class="bi bi-clock-history" aria-hidden="true"></i> Stock is held for 2 hours. The pharmacy may call to confirm.</small>
          </form>
          <div class="modal-foot">
            <button class="btn btn-ghost" data-close>Cancel</button>
            <button class="btn btn-solid" id="reserveSubmit"><i class="bi bi-bag-check" aria-hidden="true"></i> Confirm hold</button>
          </div>
        </div>`;
      document.body.appendChild(back);
      back.addEventListener("click", (e) => {
        if (e.target === back || e.target.closest("[data-close]")) closeReserve();
      });
      back.querySelector("#reserveSubmit").addEventListener("click", submitReservation);
      back.addEventListener("keydown", (e)=>{
        if (e.key==="Tab") {
          const focusable = back.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
          const first = focusable[0], last = focusable[focusable.length-1];
          if (e.shiftKey && document.activeElement===first) { e.preventDefault(); last.focus(); }
          else if (!e.shiftKey && document.activeElement===last) { e.preventDefault(); first.focus(); }
        }
      });
    }
    document.getElementById("reserveMedId").value = medId;
    document.getElementById("reserveSub").innerHTML = `<i class="bi bi-capsule-pill" style="color:#fff" aria-hidden="true"></i> <strong>${medName}</strong> at <strong>${shopName}</strong>`;
    back.classList.add("open");
    document.body.style.overflow = "hidden";
    setTimeout(() => document.getElementById("reserveName")?.focus(), 80);
  };
  function closeReserve() {
    const back = document.getElementById("reserveModal");
    if (back) {
      back.classList.remove("open");
      document.body.style.overflow = "";
      if (lastFocused) lastFocused.focus();
    }
  }
  MF.closeReserve = closeReserve;
  async function submitReservation() {
    const form = document.getElementById("reserveForm");
    const data = Object.fromEntries(new FormData(form).entries());
    form.querySelectorAll(".form-error").forEach(el=>{ el.hidden=true; el.textContent=""; });
    form.querySelectorAll("[aria-invalid]").forEach(el=>el.removeAttribute("aria-invalid"));
    let hasError = false;
    if (!data.name || data.name.trim().length < 2) {
      const err = document.getElementById("err-name");
      err.textContent = "Please enter your full name (at least 2 characters).";
      err.hidden = false;
      document.getElementById("reserveName").setAttribute("aria-invalid","true");
      hasError = true;
    }
    if (!data.phone || data.phone.trim().length < 7) {
      const err = document.getElementById("err-phone");
      err.textContent = "Enter a valid phone number so the pharmacy can confirm pickup.";
      err.hidden = false;
      document.getElementById("reservePhone").setAttribute("aria-invalid","true");
      hasError = true;
    }
    if (hasError) {
      MF.toast("Please fix the highlighted fields", "error", "Check your details");
      const firstInvalid = form.querySelector("[aria-invalid]");
      firstInvalid?.focus();
      return;
    }
    const btn = document.getElementById("reserveSubmit");
    btn.disabled = true; btn.classList.add("is-loading");
    const origHtml = btn.innerHTML;
    btn.innerHTML = '<i class="bi bi-hourglass-split" aria-hidden="true"></i> Holding...';
    try {
      const r = await fetch("/api/reserve", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      const j = await r.json();
      if (j.ok) {
        MF.toast(j.message, "success", "Reservation confirmed");
        closeReserve();
        form.reset();
        document.dispatchEvent(new CustomEvent("reservation", { detail: j }));
      } else {
        MF.toast(j.error || "Could not reserve", "error");
      }
    } catch {
      MF.toast("Network error — please try again", "error");
    } finally {
      btn.disabled = false; btn.classList.remove("is-loading");
      btn.innerHTML = origHtml;
    }
  }

  /* ---------- Favourites ---------- */
  MF.toggleFavourite = async function (medName, salt, btn) {
    if (btn) { btn.disabled = true; btn.classList.add("is-loading"); }
    try {
      const r = await fetch("/api/favourites", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ med_name: medName, salt: salt || "" }),
      });
      if (r.status === 401) { MF.toast("Sign in to save favourites", "warning"); return; }
      if (r.ok) {
        MF.toast("Saved to your medicines", "success");
        if (btn) { btn.classList.add("active"); const ic = btn.querySelector("i"); if (ic) ic.className = "bi bi-bookmark-check-fill"; }
      } else if (r.status === 409) {
        await fetch("/api/favourites", {
          method: "DELETE", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ med_name: medName, salt: salt || "" }),
        });
        MF.toast("Removed from favourites", "info");
        if (btn) { btn.classList.remove("active"); const ic = btn.querySelector("i"); if (ic) ic.className = "bi bi-bookmark"; }
      }
    } catch { MF.toast("Could not update favourites", "error"); }
    finally { if (btn) { btn.disabled = false; btn.classList.remove("is-loading"); } }
  };

  MF.fmtMoney = function (n) {
    const v = Number(n || 0);
    return "₹" + v.toLocaleString("en-IN", { minimumFractionDigits: v % 1 ? 2 : 0, maximumFractionDigits: 2 });
  };
  MF.fmtDistance = function (km) {
    if (km == null) return "";
    if (km < 1) return Math.round(km * 1000) + " m away";
    return km.toFixed(1) + " km away";
  };

  document.addEventListener("submit", (e) => {
    const f = e.target.closest("form[data-confirm]");
    if (f && !confirm(f.dataset.confirm)) e.preventDefault();
  });

  document.addEventListener("DOMContentLoaded", () => {
    initSpotlight();
  });
})();
