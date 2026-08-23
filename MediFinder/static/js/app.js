/* ==========================================================================
   MediFinder — Core client behaviour
   Theme, toasts, nav, geolocation, map icons, reservations, favourites.
   ========================================================================== */
(function () {
    "use strict";

    /* ---------- Theme ---------- */
    const saved = localStorage.getItem("mf-theme") ||
        (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.setAttribute("data-theme", saved);

    function syncThemeIcon() {
        const t = document.documentElement.getAttribute("data-theme");
        const btn = document.getElementById("themeToggle");
        if (btn) btn.innerHTML = `<i class="bi bi-${t === "dark" ? "sun" : "moon-stars"}"></i>`;
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

    /* ---------- Mobile nav ---------- */
    document.addEventListener("click", (e) => {
        const t = e.target.closest("#navToggle");
        if (t) document.getElementById("navLinks")?.classList.toggle("open");
    });

    /* ---------- Toasts ---------- */
    window.MF = window.MF || {};
    MF.toast = function (message, type = "info", title) {
        let wrap = document.getElementById("toastWrap");
        if (!wrap) {
            wrap = document.createElement("div");
            wrap.id = "toastWrap";
            wrap.className = "toast-wrap";
            document.body.appendChild(wrap);
        }
        const icon = { success: "bi-check-circle-fill", error: "bi-exclamation-triangle-fill",
            warning: "bi-exclamation-circle-fill", info: "bi-info-circle-fill" }[type] || "bi-info-circle";
        const el = document.createElement("div");
        el.className = `toast ${type}`;
        el.innerHTML = `<i class="bi ${icon}"></i>
            <div>${title ? `<strong>${title}</strong>` : ""}<p>${message}</p></div>`;
        wrap.appendChild(el);
        setTimeout(() => {
            el.style.animation = "toastOut .3s ease forwards";
            setTimeout(() => el.remove(), 320);
        }, 3800);
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

    /* Reverse geocode via Nominatim (polite usage — one call per locate) */
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
        const glyph = variant === "user" ? "" : '<i class="bi bi-capsule-pill"></i>';
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

    /* ---------- Reservation modal (shared) ---------- */
    MF.openReserve = function (medId, medName, shopName) {
        let back = document.getElementById("reserveModal");
        if (!back) {
            back = document.createElement("div");
            back.id = "reserveModal";
            back.className = "modal-back";
            back.innerHTML = `
                <div class="modal" role="dialog" aria-modal="true">
                    <div class="modal-head">
                        <h3>Reserve medicine</h3>
                        <button class="modal-close" data-close>&times;</button>
                    </div>
                    <form class="modal-body" id="reserveForm">
                        <p class="text-muted small mb-3" id="reserveSub"></p>
                        <input type="hidden" name="med_id" id="reserveMedId">
                        <div class="mb-3">
                            <label class="form-label">Your name</label>
                            <input type="text" name="name" class="form-control" placeholder="Full name" required>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Phone number *</label>
                            <input type="tel" name="phone" class="form-control" placeholder="For the pharmacy to confirm pickup" required>
                        </div>
                        <div class="row mb-3" style="gap:.75rem">
                            <div style="flex:1">
                                <label class="form-label">Quantity</label>
                                <input type="number" name="quantity" class="form-control" value="1" min="1" max="99">
                            </div>
                        </div>
                        <div class="mb-2">
                            <label class="form-label">Note (optional)</label>
                            <textarea name="note" class="form-control" rows="2" placeholder="e.g. I'll collect around 6 PM"></textarea>
                        </div>
                        <small class="form-hint"><i class="bi bi-clock-history"></i> Stock is held for 2 hours. The pharmacy may call to confirm.</small>
                    </form>
                    <div class="modal-foot">
                        <button class="btn btn-outline" data-close>Cancel</button>
                        <button class="btn btn-primary" id="reserveSubmit"><i class="bi bi-bag-check"></i> Confirm hold</button>
                    </div>
                </div>`;
            document.body.appendChild(back);
            back.addEventListener("click", (e) => {
                if (e.target === back || e.target.closest("[data-close]")) back.classList.remove("open");
            });
            document.getElementById("reserveSubmit").addEventListener("click", submitReservation);
        }
        document.getElementById("reserveMedId").value = medId;
        document.getElementById("reserveSub").innerHTML =
            `<i class="bi bi-capsule-pill text-teal"></i> <strong>${medName}</strong> at <strong>${shopName}</strong>`;
        back.classList.add("open");
        setTimeout(() => back.querySelector("input[name=name]")?.focus(), 80);
    };

    async function submitReservation() {
        const form = document.getElementById("reserveForm");
        const data = Object.fromEntries(new FormData(form).entries());
        if (!data.phone || data.phone.trim().length < 7) {
            MF.toast("Enter a valid phone number", "error"); return;
        }
        const btn = document.getElementById("reserveSubmit");
        btn.disabled = true; btn.innerHTML = '<i class="bi bi-hourglass-split"></i> Holding...';
        try {
            const r = await fetch("/api/reserve", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify(data),
            });
            const j = await r.json();
            if (j.ok) {
                MF.toast(j.message, "success", "Reservation confirmed");
                document.getElementById("reserveModal").classList.remove("open");
                form.reset();
                document.dispatchEvent(new CustomEvent("reservation", { detail: j }));
            } else {
                MF.toast(j.error || "Could not reserve", "error");
            }
        } catch {
            MF.toast("Network error — please try again", "error");
        } finally {
            btn.disabled = false; btn.innerHTML = '<i class="bi bi-bag-check"></i> Confirm hold';
        }
    }

    /* ---------- Favourites ---------- */
    MF.toggleFavourite = async function (medName, salt, btn) {
        try {
            const r = await fetch("/api/favourites", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ med_name: medName, salt: salt || "" }),
            });
            if (r.status === 401) { MF.toast("Sign in to save favourites", "warning"); return; }
            if (r.ok) {
                MF.toast("Saved to your medicines", "success");
                if (btn) { btn.classList.add("active"); btn.querySelector("i").className = "bi bi-bookmark-check-fill"; }
            } else if (r.status === 409) {
                await fetch("/api/favourites", {
                    method: "DELETE", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ med_name: medName, salt: salt || "" }),
                });
                MF.toast("Removed from favourites", "info");
                if (btn) { btn.classList.remove("active"); btn.querySelector("i").className = "bi bi-bookmark"; }
            }
        } catch { MF.toast("Could not update favourites", "error"); }
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

    /* Confirm for dangerous actions */
    document.addEventListener("submit", (e) => {
        const f = e.target.closest("form[data-confirm]");
        if (f && !confirm(f.dataset.confirm)) e.preventDefault();
    });
})();
