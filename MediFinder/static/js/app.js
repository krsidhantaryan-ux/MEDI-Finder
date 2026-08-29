/* ==========================================================================
   MediFinder — Core client behaviour v2
   UI-UX Pro Max: accessibility, touch 44px, focus not obscured, error handling
   Motion integration via motion.js (Framer Motion)
   ========================================================================== */
(function () {
    "use strict";

    /* ---------- Theme — respects system, persists, a11y ---------- */
    const saved = localStorage.getItem("mf-theme") ||
        (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.setAttribute("data-theme", saved);

    function syncThemeIcon() {
        const t = document.documentElement.getAttribute("data-theme");
        const btn = document.getElementById("themeToggle");
        if (btn) {
            btn.innerHTML = `<i class="bi bi-${t === "dark" ? "sun" : "moon-stars"}" aria-hidden="true"></i>`;
            btn.setAttribute("aria-pressed", t === "dark" ? "true" : "false");
            btn.setAttribute("aria-label", t === "dark" ? "Switch to light mode" : "Switch to dark mode");
        }
        // Update meta theme-color
        const meta = document.querySelector('meta[name="theme-color"]');
        if (meta) meta.content = t === "dark" ? "#0a3430" : "#145951";
    }
    document.addEventListener("DOMContentLoaded", syncThemeIcon);
    document.addEventListener("click", (e) => {
        if (e.target.closest("#themeToggle")) {
            const cur = document.documentElement.getAttribute("data-theme");
            const next = cur === "dark" ? "light" : "dark";
            document.documentElement.setAttribute("data-theme", next);
            localStorage.setItem("mf-theme", next);
            syncThemeIcon();
            document.dispatchEvent(new CustomEvent("themechange", { detail: next }));
        }
    });

    /* ---------- Mobile nav — focus management, escape ---------- */
    document.addEventListener("click", (e) => {
        const toggle = e.target.closest("#navToggle");
        const links = document.getElementById("navLinks");
        if (toggle && links) {
            const isOpen = links.classList.toggle("open");
            toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
            if (isOpen) {
                // Focus first link for keyboard users
                setTimeout(() => links.querySelector("a")?.focus(), 50);
            }
        } else if (!e.target.closest("#navLinks") && !e.target.closest("#navToggle")) {
            // Close when clicking outside
            const links = document.getElementById("navLinks");
            if (links?.classList.contains("open")) {
                links.classList.remove("open");
                document.getElementById("navToggle")?.setAttribute("aria-expanded","false");
            }
        }
    });
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            const links = document.getElementById("navLinks");
            if (links?.classList.contains("open")) {
                links.classList.remove("open");
                document.getElementById("navToggle")?.setAttribute("aria-expanded","false");
                document.getElementById("navToggle")?.focus();
            }
            // Close modal on escape
            const modal = document.getElementById("reserveModal");
            if (modal?.classList.contains("open")) {
                modal.classList.remove("open");
                document.getElementById("reserveTrigger")?.focus();
            }
        }
    });

    /* ---------- Toasts — aria-live polite, motion stack ---------- */
    window.MF = window.MF || {};
    MF.toast = function (message, type = "info", title) {
        let wrap = document.getElementById("toastWrap");
        if (!wrap) {
            wrap = document.createElement("div");
            wrap.id = "toastWrap";
            wrap.className = "toast-wrap";
            wrap.setAttribute("aria-live","polite");
            wrap.setAttribute("aria-atomic","false");
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
            <button class="modal-close" style="margin-left:auto;min-width:32px;min-height:32px" aria-label="Dismiss notification"><i class="bi bi-x" aria-hidden="true"></i></button>`;
        wrap.appendChild(el);
        // Dismiss button
        el.querySelector("button").addEventListener("click", ()=> {
            el.remove();
        });
        // Auto dismiss fallback if motion.js not handling
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

    /* ---------- Map helpers ---------- */
    MF.tileUrl = function () {
        const dark = document.documentElement.getAttribute("data-theme") === "dark";
        return dark
            ? "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            : "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png";
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
        document.addEventListener("themechange", () => {
            layer.setUrl(MF.tileUrl());
        });
        return layer;
    };

    /* ---------- Reservation modal — accessible, focus trap ---------- */
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
                        <p class="text-muted small mb-3" id="reserveSub"></p>
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
                        <div class="row mb-3" style="gap:.75rem">
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
                        <button class="btn btn-outline" data-close>Cancel</button>
                        <button class="btn btn-primary" id="reserveSubmit"><i class="bi bi-bag-check" aria-hidden="true"></i> Confirm hold</button>
                    </div>
                </div>`;
            document.body.appendChild(back);
            back.addEventListener("click", (e) => {
                if (e.target === back || e.target.closest("[data-close]")) closeReserve();
            });
            back.querySelector("#reserveSubmit").addEventListener("click", submitReservation);
            // Focus trap
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
        document.getElementById("reserveSub").innerHTML =
            `<i class="bi bi-capsule-pill text-teal" aria-hidden="true"></i> <strong>${medName}</strong> at <strong>${shopName}</strong>`;
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
        // Clear previous errors
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
                if (btn) { btn.classList.add("active"); const ic = btn.querySelector("i"); if (ic) ic.className = "bi bi-bookmark-check-fill"; btn.setAttribute("aria-label", `Remove ${medName} from favourites`); }
            } else if (r.status === 409) {
                await fetch("/api/favourites", {
                    method: "DELETE", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ med_name: medName, salt: salt || "" }),
                });
                MF.toast("Removed from favourites", "info");
                if (btn) { btn.classList.remove("active"); const ic = btn.querySelector("i"); if (ic) ic.className = "bi bi-bookmark"; btn.setAttribute("aria-label", `Save ${medName} to favourites`); }
            }
        } catch { MF.toast("Could not update favourites", "error"); }
        finally { if (btn) { btn.disabled = false; btn.classList.remove("is-loading"); } }
    };

    /* ---------- Generic helpers ---------- */
    MF.fmtMoney = function (n) {
        const v = Number(n || 0);
        return "₹" + v.toLocaleString("en-IN", { minimumFractionDigits: v % 1 ? 2 : 0, maximumFractionDigits: 2 });
    };
    MF.fmtDistance = function (km) {
        if (km == null) return "";
        if (km < 1) return Math.round(km * 1000) + " m away";
        return km.toFixed(1) + " km away";
    };

    /* Confirm for dangerous actions — accessible */
    document.addEventListener("submit", (e) => {
        const f = e.target.closest("form[data-confirm]");
        if (f && !confirm(f.dataset.confirm)) e.preventDefault();
    });

    /* Focus main after navigation for screen readers */
    document.addEventListener("DOMContentLoaded", ()=>{
        if (window.location.hash === "" ) {
            const main = document.getElementById("main");
            if (main) main.setAttribute("tabindex","-1");
        }
    });
})();
