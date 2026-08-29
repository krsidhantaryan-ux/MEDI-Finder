/* ==========================================================================
   MediFinder — Core client behaviour
   Theme, toasts, nav, geolocation, map icons, reservations, favourites.
   ========================================================================== */
(function () {
    "use strict";

    /* ---------- Theme ---------- */
    let saved = "light";
    try {
        saved = localStorage.getItem("mf-theme") ||
            (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    } catch {
        saved = document.documentElement.getAttribute("data-theme") || "light";
    }
    document.documentElement.setAttribute("data-theme", saved);

    function syncThemeIcon() {
        const t = document.documentElement.getAttribute("data-theme");
        const btn = document.getElementById("themeToggle");
        if (btn) btn.innerHTML = `<i class="bi bi-${t === "dark" ? "sun" : "moon-stars"}"></i>`;
    }
    document.addEventListener("DOMContentLoaded", () => {
        syncThemeIcon();
        document.body.classList.add("app-ready");
    });
    document.addEventListener("click", (e) => {
        if (e.target.closest("#themeToggle")) {
            const cur = document.documentElement.getAttribute("data-theme");
            const next = cur === "dark" ? "light" : "dark";
            document.documentElement.setAttribute("data-theme", next);
            try { localStorage.setItem("mf-theme", next); } catch {}
            syncThemeIcon();
            window.MF?.motion?.pulse?.(document.getElementById("themeToggle"));
            document.dispatchEvent(new CustomEvent("themechange", { detail: next }));
        }
    });

    /* ---------- Mobile nav ---------- */
    document.addEventListener("click", (e) => {
        const t = e.target.closest("#navToggle");
        if (t) {
            const links = document.getElementById("navLinks");
            links?.classList.toggle("open");
            t.setAttribute("aria-expanded", links?.classList.contains("open") ? "true" : "false");
        } else if (!e.target.closest(".nav") && document.getElementById("navLinks")?.classList.contains("open")) {
            document.getElementById("navLinks")?.classList.remove("open");
            document.getElementById("navToggle")?.setAttribute("aria-expanded", "false");
        }
    });
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            document.getElementById("navLinks")?.classList.remove("open");
            document.getElementById("navToggle")?.setAttribute("aria-expanded", "false");
            document.querySelectorAll(".modal-back.open").forEach((m) => m.classList.remove("open"));
        }
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
        const safe = (value) => String(value ?? "").replace(/[&<>'\"]/g, (ch) => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", "\"": "&quot;"
        })[ch]);
        const el = document.createElement("div");
        el.className = `toast ${type}`;
        el.innerHTML = `<i class="bi ${icon}"></i>
            <div>${title ? `<strong>${safe(title)}</strong>` : ""}<p>${safe(message)}</p></div>`;
        wrap.appendChild(el);
        MF.motion?.toast?.(el);
        setTimeout(() => {
            el.style.animation = "toastOut .3s ease forwards";
            setTimeout(() => el.remove(), 320);
        }, 3800);
    };

    /* ---------- Geolocation ---------- */
    MF.userPos = null;
    function hasCoord(value) {
        return value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
    }
    MF.location = {
        key: "mf-location",
        load() {
            try {
                const raw = localStorage.getItem(this.key);
                if (!raw) return null;
                const loc = JSON.parse(raw);
                if (!loc || (!loc.city && (!hasCoord(loc.lat) || !hasCoord(loc.lng)))) return null;
                return loc;
            } catch { return null; }
        },
        save(loc) {
            try {
                const current = this.load() || {};
                const next = { ...current, ...loc, saved_at: Date.now() };
                localStorage.setItem(this.key, JSON.stringify(next));
                return next;
            } catch { return loc; }
        },
        clear() { try { localStorage.removeItem(this.key); } catch {} }
    };
    const savedLocation = MF.location.load();
    MF.userPos = savedLocation && hasCoord(savedLocation.lat) && hasCoord(savedLocation.lng)
        ? { lat: +savedLocation.lat, lng: +savedLocation.lng, approximate: !!savedLocation.approximate, source: savedLocation.source || "saved" }
        : null;
    MF.getUserLocation = function (opts = {}) {
        return new Promise((resolve, reject) => {
            if (!navigator.geolocation) return reject(new Error("Geolocation not supported"));
            navigator.geolocation.getCurrentPosition(
                (pos) => {
                    MF.userPos = { lat: pos.coords.latitude, lng: pos.coords.longitude, approximate: false, source: "browser" };
                    MF.location.save(MF.userPos);
                    resolve(MF.userPos);
                },
                (err) => reject(err),
                { enableHighAccuracy: true, timeout: 4500, maximumAge: 60000, ...opts }
            );
        });
    };

    MF.getApproxLocation = async function (city = "") {
        const r = await fetch(`/api/location/estimate?city=${encodeURIComponent(city || "")}`);
        const data = await r.json();
        if (!data.ok) throw new Error(data.error || "Location unavailable");
        MF.userPos = { lat: +data.lat, lng: +data.lng, approximate: true, source: data.source || "fallback" };
        MF.location.save({ ...MF.userPos, city: data.city || city || "Patna" });
        return { ...MF.userPos, city: data.city || city || "Patna" };
    };

    MF.detectLocation = async function (options = {}) {
        const city = options.city || "";
        try {
            const exact = await MF.getUserLocation(options.geo || {});
            return { ...exact, city, approximate: false };
        } catch (err) {
            if (options.fallback === false) throw err;
            return MF.getApproxLocation(city);
        }
    };

    /* Reverse geocode through our server proxy to the public OpenStreetMap/Nominatim API. */
    MF.reverseGeocode = async function (lat, lng) {
        try {
            const r = await fetch(`/api/reverse-geocode?lat=${encodeURIComponent(lat)}&lng=${encodeURIComponent(lng)}`);
            const d = await r.json();
            return d.ok ? (d.city || "") : "";
        } catch { return ""; }
    };

    MF.geocode = async function (query) {
        const r = await fetch(`/api/geocode?q=${encodeURIComponent(query || "")}`);
        const d = await r.json();
        if (!d.ok) throw new Error(d.error || "Location not found");
        return d.results || [];
    };

    /* ---------- Local map engine (OpenStreetMap tile API + no CDN JS dependency) ---------- */
    function ensureStaticLeafletFallback() {
        if (window.L) return;

        const TILE_SIZE = 256;
        const SUBDOMAINS = ["a", "b", "c"];
        const DEFAULT_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
        function clamp(n, min, max) { return Math.max(min, Math.min(max, n)); }
        function toLatLng(value) {
            if (Array.isArray(value)) return { lat: +value[0], lng: +value[1] };
            return { lat: +(value?.lat ?? 0), lng: +(value?.lng ?? value?.lon ?? 0) };
        }
        function tileX(lng, z) { return ((lng + 180) / 360) * Math.pow(2, z); }
        function tileY(lat, z) {
            const rad = clamp(lat, -85.0511, 85.0511) * Math.PI / 180;
            return (1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2 * Math.pow(2, z);
        }
        function lngFromTile(x, z) { return x / Math.pow(2, z) * 360 - 180; }
        function latFromTile(y, z) {
            const n = Math.PI - 2 * Math.PI * y / Math.pow(2, z);
            return Math.atan(Math.sinh(n)) * 180 / Math.PI;
        }
        function resolveTileUrl(tpl, x, y, z) {
            const n = Math.pow(2, z);
            const wrappedX = ((x % n) + n) % n;
            const s = SUBDOMAINS[Math.abs(wrappedX + y + z) % SUBDOMAINS.length];
            return (tpl || DEFAULT_TILE_URL)
                .replace("{s}", s)
                .replace("{z}", z)
                .replace("{x}", wrappedX)
                .replace("{y}", y)
                .replace("{r}", "");
        }
        function zoomForSpan(latSpan, lngSpan, maxZoom = 15) {
            const span = Math.max(Math.abs(latSpan), Math.abs(lngSpan));
            if (span > 2) return 8;
            if (span > 1) return 9;
            if (span > .55) return 10;
            if (span > .25) return 11;
            if (span > .12) return 12;
            if (span > .055) return 13;
            if (span > .025) return 14;
            return Math.min(15, maxZoom);
        }

        class StaticMap {
            constructor(id, options = {}) {
                this.el = typeof id === "string" ? document.getElementById(id) : id;
                this.options = options || {};
                this.center = { lat: 25.611, lng: 85.143 };
                this.zoom = 12;
                this.minZoom = this.options.minZoom || 4;
                this.maxZoom = this.options.maxZoom || 19;
                this.bounds = null;
                this.markers = [];
                this.handlers = {};
                this.tileUrl = DEFAULT_TILE_URL;
                this.activePopupMarker = null;
                this._dragState = null;
                this._suppressClickUntil = 0;
                if (!this.el) throw new Error("Map container not found");
                this.el.classList.add("static-map", "static-map-interactive");
                this.el.setAttribute("tabindex", this.el.getAttribute("tabindex") || "0");
                this.el.setAttribute("role", this.el.getAttribute("role") || "application");
                const wheelHint = this.options.scrollWheelZoom === false
                    ? "Drag map · use +/− to zoom"
                    : "Drag map · scroll or use +/− to zoom";
                this.el.setAttribute("aria-label", this.el.getAttribute("aria-label") || `${wheelHint}. Interactive OpenStreetMap pharmacy map.`);
                this.el.innerHTML = `<div class="static-map-grid" aria-label="OpenStreetMap preview">
                    <div class="static-map-tiles" aria-hidden="true"></div>
                    <div class="static-map-roads" aria-hidden="true"></div>
                    <div class="static-map-pins"></div>
                    <div class="static-map-popup" hidden></div>
                    <div class="static-map-note"><i class="bi bi-map"></i> ${wheelHint} · © OpenStreetMap</div>
                    <div class="static-map-controls"><button type="button" data-zoom="in" aria-label="Zoom in">+</button><button type="button" data-zoom="out" aria-label="Zoom out">−</button></div>
                </div>`;
                this.grid = this.el.querySelector(".static-map-grid");
                this.tileLayer = this.el.querySelector(".static-map-tiles");
                this.pinLayer = this.el.querySelector(".static-map-pins");
                this.popup = this.el.querySelector(".static-map-popup");
                this.el.querySelector(".static-map-controls")?.addEventListener("click", (e) => {
                    const z = e.target.closest("[data-zoom]");
                    if (!z) return;
                    e.preventDefault();
                    const rect = this.el.getBoundingClientRect();
                    this.zoomBy(z.dataset.zoom === "in" ? 1 : -1, {
                        clientX: rect.left + rect.width / 2,
                        clientY: rect.top + rect.height / 2,
                    });
                });
                this.el.addEventListener("click", (e) => {
                    if (performance.now() < this._suppressClickUntil) return;
                    if (e.target.closest(".static-pin, .static-map-popup, .static-map-controls")) return;
                    this.popup.hidden = true;
                    this.activePopupMarker = null;
                    this.handlers.click?.({ latlng: this.eventToLatLng(e) });
                });
                this.bindInteractions();
                if (window.ResizeObserver) new ResizeObserver(() => this.render()).observe(this.el);
                else window.addEventListener("resize", () => this.render(), { passive: true });
            }
            setTileUrl(url) { this.tileUrl = url || DEFAULT_TILE_URL; this.renderTiles(); return this; }
            setView(center, zoom) {
                this.center = toLatLng(center);
                if (zoom) this.zoom = clamp(Math.round(zoom), this.minZoom, this.maxZoom);
                this.bounds = null;
                this.render();
                return this;
            }
            setZoom(zoom) {
                this.zoom = clamp(Math.round(zoom), this.minZoom, this.maxZoom);
                this.bounds = null;
                this.render();
                return this;
            }
            fitBounds(bounds, options = {}) {
                const pts = Array.from(bounds || []).map(toLatLng).filter(p => hasCoord(p.lat) && hasCoord(p.lng));
                if (!pts.length) return this;
                const minLat = Math.min(...pts.map(p => p.lat));
                const maxLat = Math.max(...pts.map(p => p.lat));
                const minLng = Math.min(...pts.map(p => p.lng));
                const maxLng = Math.max(...pts.map(p => p.lng));
                this.center = { lat: (minLat + maxLat) / 2, lng: (minLng + maxLng) / 2 };
                this.zoom = Math.min(options.maxZoom || this.maxZoom, zoomForSpan(maxLat - minLat, maxLng - minLng, options.maxZoom || this.maxZoom));
                this.bounds = pts;
                this.render();
                return this;
            }
            panTo(center) { this.center = toLatLng(center); this.bounds = null; this.render(); return this; }
            panBy(offset) {
                const dx = Array.isArray(offset) ? +offset[0] : +(offset?.x || 0);
                const dy = Array.isArray(offset) ? +offset[1] : +(offset?.y || 0);
                const z = clamp(Math.round(this.zoom), this.minZoom, this.maxZoom);
                const cX = tileX(this.center.lng, z) + dx / TILE_SIZE;
                const cY = tileY(this.center.lat, z) + dy / TILE_SIZE;
                this.center = this.tilePointToLatLng(cX, cY, z);
                this.bounds = null;
                this.render();
                return this;
            }
            flyTo(center, zoom) { return this.setView(center, zoom || this.zoom); }
            invalidateSize() { this.render(); return this; }
            on(type, cb) { this.handlers[type] = cb; return this; }
            removeLayer(layer) { layer?.remove?.(); return this; }
            size() {
                return { width: this.el.clientWidth || 760, height: this.el.clientHeight || 460 };
            }
            tilePointToLatLng(x, y, z) {
                const n = Math.pow(2, z);
                const wrappedX = ((x % n) + n) % n;
                const clampedY = clamp(y, 0, n);
                return { lat: latFromTile(clampedY, z), lng: lngFromTile(wrappedX, z) };
            }
            screenOffset(clientX, clientY) {
                const rect = this.el.getBoundingClientRect();
                return {
                    dx: clientX - rect.left - rect.width / 2,
                    dy: clientY - rect.top - rect.height / 2,
                    rect,
                };
            }
            project(latlng) {
                const p = toLatLng(latlng);
                const z = clamp(Math.round(this.zoom), this.minZoom, this.maxZoom);
                const cX = tileX(this.center.lng, z), cY = tileY(this.center.lat, z);
                const { width, height } = this.size();
                const px = width / 2 + (tileX(p.lng, z) - cX) * TILE_SIZE;
                const py = height / 2 + (tileY(p.lat, z) - cY) * TILE_SIZE;
                return { x: (px / width) * 100, y: (py / height) * 100, px, py };
            }
            pointToLatLng(clientX, clientY, z = this.zoom, center = this.center) {
                const { dx, dy } = this.screenOffset(clientX, clientY);
                const zoom = clamp(Math.round(z), this.minZoom, this.maxZoom);
                const cX = tileX(center.lng, zoom), cY = tileY(center.lat, zoom);
                return this.tilePointToLatLng(cX + dx / TILE_SIZE, cY + dy / TILE_SIZE, zoom);
            }
            eventToLatLng(event) {
                return this.pointToLatLng(event.clientX, event.clientY);
            }
            zoomAt(clientX, clientY, zoom) {
                const oldZoom = clamp(Math.round(this.zoom), this.minZoom, this.maxZoom);
                const nextZoom = clamp(Math.round(zoom), this.minZoom, this.maxZoom);
                if (nextZoom === oldZoom) return this;
                const focus = this.pointToLatLng(clientX, clientY, oldZoom, this.center);
                const { dx, dy } = this.screenOffset(clientX, clientY);
                const cX = tileX(focus.lng, nextZoom) - dx / TILE_SIZE;
                const cY = tileY(focus.lat, nextZoom) - dy / TILE_SIZE;
                this.zoom = nextZoom;
                this.center = this.tilePointToLatLng(cX, cY, nextZoom);
                this.bounds = null;
                this.popup.hidden = true;
                this.activePopupMarker = null;
                this.render();
                this.handlers.zoomend?.({ target: this });
                return this;
            }
            zoomBy(delta, origin) {
                const rect = this.el.getBoundingClientRect();
                const point = origin || { clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2 };
                return this.zoomAt(point.clientX, point.clientY, this.zoom + delta);
            }
            setDragTransform(dx, dy) {
                const transform = `translate(${dx}px, ${dy}px)`;
                if (this.tileLayer) this.tileLayer.style.transform = transform;
                if (this.pinLayer) this.pinLayer.style.transform = transform;
            }
            clearDragTransform() {
                if (this.tileLayer) this.tileLayer.style.transform = "";
                if (this.pinLayer) this.pinLayer.style.transform = "";
            }
            bindInteractions() {
                const startDrag = (e) => {
                    if (this._dragState) return;
                    if (e.button != null && e.button !== 0) return;
                    if (e.target.closest(".static-pin, .static-map-popup, .static-map-controls")) return;
                    const z = clamp(Math.round(this.zoom), this.minZoom, this.maxZoom);
                    this._dragState = {
                        pointerId: e.pointerId,
                        x: e.clientX,
                        y: e.clientY,
                        startTileX: tileX(this.center.lng, z),
                        startTileY: tileY(this.center.lat, z),
                        zoom: z,
                        moved: false,
                    };
                    this.popup.hidden = true;
                    this.activePopupMarker = null;
                    this.el.classList.add("is-dragging");
                    try { this.el.focus({ preventScroll: true }); } catch { this.el.focus(); }
                    try { this.el.setPointerCapture(e.pointerId); } catch {}
                    e.preventDefault();
                };
                const moveDrag = (e) => {
                    const state = this._dragState;
                    if (!state || state.pointerId !== e.pointerId) return;
                    const dx = e.clientX - state.x;
                    const dy = e.clientY - state.y;
                    if (Math.abs(dx) + Math.abs(dy) > 3) state.moved = true;
                    this.setDragTransform(dx, dy);
                    e.preventDefault();
                };
                const endDrag = (e) => {
                    const state = this._dragState;
                    if (!state || state.pointerId !== e.pointerId) return;
                    const dx = e.clientX - state.x;
                    const dy = e.clientY - state.y;
                    this._dragState = null;
                    this.el.classList.remove("is-dragging");
                    this.clearDragTransform();
                    try { this.el.releasePointerCapture(e.pointerId); } catch {}
                    this._suppressClickUntil = performance.now() + 280;
                    if (state.moved) {
                        this.center = this.tilePointToLatLng(
                            state.startTileX - dx / TILE_SIZE,
                            state.startTileY - dy / TILE_SIZE,
                            state.zoom,
                        );
                        this.bounds = null;
                        this.render();
                        this.handlers.moveend?.({ target: this });
                    } else {
                        this.handlers.click?.({ latlng: this.eventToLatLng(e) });
                    }
                    e.preventDefault();
                };
                this.el.addEventListener("pointerdown", startDrag);
                this.el.addEventListener("pointermove", moveDrag);
                this.el.addEventListener("pointerup", endDrag);
                this.el.addEventListener("pointercancel", endDrag);
                if (this.options.scrollWheelZoom !== false) {
                    this.el.addEventListener("wheel", (e) => {
                        if (e.target.closest(".static-map-popup")) return;
                        e.preventDefault();
                        this.zoomBy(e.deltaY < 0 ? 1 : -1, e);
                    }, { passive: false });
                }
                if (this.options.doubleClickZoom !== false) {
                    this.el.addEventListener("dblclick", (e) => {
                        if (e.target.closest(".static-pin, .static-map-popup, .static-map-controls")) return;
                        e.preventDefault();
                        this.zoomBy(e.shiftKey ? -1 : 1, e);
                    });
                }
                this.el.addEventListener("keydown", (e) => {
                    if (e.target !== this.el) return;
                    const pan = 90;
                    const actions = {
                        ArrowLeft: () => this.panBy([-pan, 0]),
                        ArrowRight: () => this.panBy([pan, 0]),
                        ArrowUp: () => this.panBy([0, -pan]),
                        ArrowDown: () => this.panBy([0, pan]),
                        "+": () => this.zoomBy(1),
                        "=": () => this.zoomBy(1),
                        "-": () => this.zoomBy(-1),
                        "_": () => this.zoomBy(-1),
                    };
                    const action = actions[e.key];
                    if (action) { e.preventDefault(); action(); }
                });
            }
            renderTiles() {
                if (!this.tileLayer) return;
                const z = clamp(Math.round(this.zoom), this.minZoom, this.maxZoom);
                const { width, height } = this.size();
                const cX = tileX(this.center.lng, z), cY = tileY(this.center.lat, z);
                const startX = Math.floor(cX), startY = Math.floor(cY);
                const rangeX = Math.ceil(width / TILE_SIZE / 2) + 1;
                const rangeY = Math.ceil(height / TILE_SIZE / 2) + 1;
                const frag = document.createDocumentFragment();
                const max = Math.pow(2, z);
                for (let dx = -rangeX; dx <= rangeX; dx++) {
                    for (let dy = -rangeY; dy <= rangeY; dy++) {
                        const x = startX + dx;
                        const y = startY + dy;
                        if (y < 0 || y >= max) continue;
                        const img = document.createElement("img");
                        img.className = "static-map-tile";
                        img.loading = "lazy";
                        img.decoding = "async";
                        img.draggable = false;
                        img.src = resolveTileUrl(this.tileUrl, x, y, z);
                        img.style.left = `${Math.round(width / 2 + (x - cX) * TILE_SIZE)}px`;
                        img.style.top = `${Math.round(height / 2 + (y - cY) * TILE_SIZE)}px`;
                        img.onerror = () => { img.remove(); this.grid?.classList.add("tiles-failed"); };
                        frag.appendChild(img);
                    }
                }
                this.tileLayer.replaceChildren(frag);
            }
            render() {
                this.renderTiles();
                this.markers.forEach(m => m.render());
                if (this.activePopupMarker && !this.popup.hidden) this.positionPopup(this.activePopupMarker);
                return this;
            }
            positionPopup(marker) {
                if (!marker?.popupHtml || !this.popup) return;
                const p = this.project(marker.latlng);
                this.popup.style.left = `${clamp(p.x, 6, 94)}%`;
                this.popup.style.top = `${clamp(p.y - 2, 8, 96)}%`;
            }
            showPopup(marker) {
                if (!marker.popupHtml || !this.popup) return;
                this.activePopupMarker = marker;
                this.popup.innerHTML = marker.popupHtml;
                this.popup.hidden = false;
                this.positionPopup(marker);
            }
        }

        class StaticLayer {
            constructor() { this.map = null; this.markers = []; }
            addTo(map) { this.map = map; return this; }
            clearLayers() { this.markers.slice().forEach(m => m.remove()); this.markers = []; return this; }
        }

        class StaticMarker {
            constructor(latlng, options = {}) {
                this.latlng = toLatLng(latlng);
                this.options = options;
                this.handlers = {};
                this.el = null;
                this.popupHtml = "";
                this.map = null;
                this.parentLayer = null;
            }
            addTo(target) {
                const map = target instanceof StaticLayer ? target.map : target;
                if (!map) return this;
                this.map = map;
                this.parentLayer = target instanceof StaticLayer ? target : null;
                if (this.parentLayer) this.parentLayer.markers.push(this);
                map.markers.push(this);
                this.el = document.createElement("button");
                this.el.type = "button";
                this.el.className = "static-pin";
                this.el.setAttribute("aria-label", this.options.title || "Map marker");
                this.el.innerHTML = this.options.icon?.html || '<div class="pin pin-teal"><div class="pin-body"><i class="bi bi-capsule-pill"></i></div><div class="pin-shadow"></div></div>';
                this.el.addEventListener("click", (e) => {
                    e.stopPropagation();
                    this.openPopup();
                    this.handlers.click?.({ target: this, latlng: this.latlng });
                });
                if (this.options.draggable) this.enableDrag();
                map.pinLayer.appendChild(this.el);
                this.render();
                return this;
            }
            enableDrag() {
                this.el?.addEventListener("pointerdown", (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const move = (ev) => {
                        this.latlng = this.map.eventToLatLng(ev);
                        this.render();
                    };
                    const up = (ev) => {
                        document.removeEventListener("pointermove", move);
                        document.removeEventListener("pointerup", up);
                        this.latlng = this.map.eventToLatLng(ev);
                        this.render();
                        this.handlers.dragend?.({ target: this, latlng: this.latlng });
                    };
                    document.addEventListener("pointermove", move);
                    document.addEventListener("pointerup", up, { once: true });
                });
            }
            bindPopup(html) { this.popupHtml = html; return this; }
            openPopup() { this.map?.showPopup(this); return this; }
            on(type, cb) { this.handlers[type] = cb; return this; }
            getLatLng() { return { ...this.latlng }; }
            setLatLng(latlng) { this.latlng = toLatLng(latlng); this.render(); return this; }
            render() {
                if (!this.map || !this.el) return;
                const p = this.map.project(this.latlng);
                this.el.style.left = `${p.x}%`;
                this.el.style.top = `${p.y}%`;
            }
            remove() {
                this.el?.remove();
                if (this.map) this.map.markers = this.map.markers.filter(m => m !== this);
                if (this.parentLayer) this.parentLayer.markers = this.parentLayer.markers.filter(m => m !== this);
            }
        }

        window.L = {
            _medifinderFallback: true,
            map: (id, options) => new StaticMap(id, options),
            tileLayer: (url) => ({ addTo(map) { this.map = map; map.setTileUrl(url || DEFAULT_TILE_URL); return this; }, setUrl(url) { this.map?.setTileUrl(url || DEFAULT_TILE_URL); return this; } }),
            layerGroup: () => new StaticLayer(),
            marker: (latlng, options) => new StaticMarker(latlng, options),
            divIcon: (options) => options || {},
        };
        window.dispatchEvent(new CustomEvent("medifinder:static-map-ready"));
    }
    ensureStaticLeafletFallback();

    /* ---------- Map helpers ---------- */
    MF.tileUrl = function () {
        // Public, keyless OpenStreetMap raster tile API. If tiles are blocked,
        // the local map engine keeps the grid, pins and list visible.
        return "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
    };
    MF.tileAttrib = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';

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
    MF.openReserve = function (medId, medName, shopName, quantity = 1) {
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
                            <label class="form-label">Phone number <span class="req">required</span></label>
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
        const qtyInput = back.querySelector("input[name=quantity]");
        if (qtyInput) qtyInput.value = Math.max(1, Math.min(99, Number(quantity) || 1));
        document.getElementById("reserveSub").innerHTML =
            `<i class="bi bi-capsule-pill text-teal"></i> <strong>${MF.escapeHtml(medName)}</strong> at <strong>${MF.escapeHtml(shopName)}</strong>`;
        back.classList.add("open");
        MF.motion?.modal?.(back.querySelector(".modal"));
        setTimeout(() => back.querySelector("input[name=name]")?.focus(), 80);
    };

    async function submitReservation() {
        const form = document.getElementById("reserveForm");
        const data = Object.fromEntries(new FormData(form).entries());
        if (!data.phone || data.phone.trim().length < 7) {
            MF.toast("Enter a valid phone number", "error"); return;
        }
        const btn = document.getElementById("reserveSubmit");
        btn.disabled = true; btn.innerHTML = '<i class="bi bi-hourglass-split"></i> Holding…';
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
    MF.escapeHtml = function (value) {
        return String(value ?? "").replace(/[&<>'\"]/g, (ch) => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", "\"": "&quot;"
        })[ch]);
    };
    MF.fmtDistance = function (km) {
        if (km == null) return "";
        if (km < 1) return Math.round(km * 1000) + " m away";
        return km.toFixed(1) + " km away";
    };

    MF.parseUtc = function (value) {
        if (!value) return null;
        if (value instanceof Date) return value;
        const s = String(value).trim();
        return new Date((s.includes("T") ? s : s.replace(" ", "T")) + (/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? "" : "Z"));
    };

    function updateCountdowns() {
        const now = Date.now();
        document.querySelectorAll("[data-held-until]").forEach((el) => {
            const d = MF.parseUtc(el.dataset.heldUntil);
            if (!d || Number.isNaN(d.getTime())) return;
            const ms = d.getTime() - now;
            if (ms <= 0) {
                el.textContent = "Hold expired";
                el.classList.add("expired");
                return;
            }
            const mins = Math.ceil(ms / 60000);
            const h = Math.floor(mins / 60);
            const m = mins % 60;
            el.textContent = h ? `${h}h ${m}m left` : `${m}m left`;
        });
    }
    document.addEventListener("DOMContentLoaded", () => {
        updateCountdowns();
        if (document.querySelector("[data-held-until]")) setInterval(updateCountdowns, 60000);
    });

    /* Confirm for dangerous actions + account page API forms */
    document.addEventListener("submit", async (e) => {
        const apiDelete = e.target.closest("form[data-api-delete]");
        if (apiDelete) {
            e.preventDefault();
            if (apiDelete.dataset.confirm && !confirm(apiDelete.dataset.confirm)) return;
            const id = apiDelete.dataset.apiDelete;
            try {
                const r = await fetch(apiDelete.action || "/api/favourites", {
                    method: "DELETE",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ id }),
                });
                const j = await r.json().catch(() => ({}));
                if (!r.ok || j.ok === false) throw new Error(j.error || "Remove failed");
                apiDelete.closest(".medication-card, tr, .ops-item")?.remove();
                MF.toast("Removed from saved medicines", "info");
            } catch {
                MF.toast("Could not remove saved medicine", "error");
            }
            return;
        }
        const f = e.target.closest("form[data-confirm]");
        if (f && !confirm(f.dataset.confirm)) e.preventDefault();
    });
})();
