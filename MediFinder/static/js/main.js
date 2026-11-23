/* ==========================================================================
   MedFinder - Main JavaScript File
   ========================================================================== */

let searchMap = null;
let markersLayer = null;
let userMarker = null;
let userLat = null;
let userLng = null;

// --- 1. DARK / LIGHT THEME SYSTEM ---
function initTheme() {
    const savedTheme = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const targetTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', targetTheme);
    localStorage.setItem('theme', targetTheme);
    updateThemeIcon(targetTheme);
}

function updateThemeIcon(theme) {
    const btnIcon = document.getElementById('theme-toggle-icon');
    if (btnIcon) {
        btnIcon.className = theme === 'dark' ? 'bi bi-sun-fill text-warning' : 'bi bi-moon-stars-fill text-dark';
    }
}

// --- 2. GLASS TOAST NOTIFICATIONS ---
function showToast(message, type = 'success') {
    let container = document.querySelector('.toast-container-custom');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container-custom';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    const alertType = type === 'error' ? 'danger' : type;
    
    toast.className = `alert alert-${alertType} glass-card shadow-lg d-flex align-items-center gap-2 py-2 px-3 mb-2`;
    toast.style.minWidth = '280px';
    
    const iconClass = type === 'error' ? 'bi-exclamation-triangle-fill text-danger' : 'bi-check-circle-fill text-success';
    
    toast.innerHTML = `
        <i class="bi ${iconClass} fs-5"></i>
        <span class="fw-semibold small text-dark">${message}</span>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'all 0.4s ease';
        setTimeout(() => toast.remove(), 400);
    }, 3500);
}

// --- 3. PULSING MAP MARKERS ---
function createPulsingIcon() {
    return L.divIcon({
        className: 'custom-pulsing-pin',
        html: `<div class="pin-pulse"></div><div class="pin-core"></div>`,
        iconSize: [20, 20],
        iconAnchor: [10, 10],
        popupAnchor: [0, -10]
    });
}

function createUserLocationIcon() {
    return L.divIcon({
        className: 'custom-user-pin',
        html: `<div style="width:16px; height:16px; background:#dc3545; border:3px solid #fff; border-radius:50%; box-shadow:0 0 10px rgba(220,53,69,0.8);"></div>`,
        iconSize: [16, 16],
        iconAnchor: [8, 8]
    });
}

// --- 4. AUTOMATIC USER GEOLOCATION ---
function detectUserLocation(silent = false) {
    if (!navigator.geolocation) {
        if (!silent) showToast('Geolocation is not supported by your browser', 'error');
        return;
    }

    if (!silent) showToast('Detecting location...', 'info');

    navigator.geolocation.getCurrentPosition(
        (position) => {
            userLat = position.coords.latitude;
            userLng = position.coords.longitude;

            if (searchMap) {
                searchMap.setView([userLat, userLng], 13);

                if (userMarker) searchMap.removeLayer(userMarker);
                userMarker = L.marker([userLat, userLng], { icon: createUserLocationIcon() })
                    .addTo(searchMap)
                    .bindPopup('<b>Your Current Location</b>')
                    .openPopup();
            }

            // Reverse geocode to populate City / Area input box
            fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${userLat}&lon=${userLng}`)
                .then(res => res.json())
                .then(data => {
                    if (data && data.address) {
                        const cityName = data.address.city || data.address.town || data.address.village || data.address.suburb || data.address.county || "";
                        const cityInput = document.getElementById('city-input');
                        if (cityInput && cityName) {
                            cityInput.value = cityName;
                        }
                    }
                })
                .catch(() => {});

            if (!silent) showToast('Location detected successfully!');
        },
        (error) => {
            console.warn("Geolocation permission denied or timed out:", error.message);
            if (!silent) {
                showToast('Unable to detect location. Please type your city manually.', 'error');
            }
        },
        { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 }
    );
}

// --- 5. SKELETON LOADER ---
function showSearchSkeleton() {
    const container = document.getElementById('results-container');
    if (!container) return;
    
    container.innerHTML = Array(3).fill(0).map(() => `
        <div class="p-3 border-bottom">
            <div class="skeleton skeleton-title"></div>
            <div class="skeleton skeleton-text" style="width: 85%;"></div>
            <div class="skeleton skeleton-text" style="width: 45%;"></div>
        </div>
    `).join('');
}

// --- 6. SEARCH PAGE & API ENGINE ---
function initSearchPage() {
    const mapElement = document.getElementById('map');
    const searchForm = document.getElementById('search-form');

    if (!mapElement || !searchForm) return;

    // Default center
    const defaultLat = 25.5941;
    const defaultLng = 85.1376;
    
    searchMap = L.map('map').setView([defaultLat, defaultLng], 12);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '© OpenStreetMap contributors'
    }).addTo(searchMap);

    markersLayer = L.layerGroup().addTo(searchMap);

    // Auto detect user location on initial page load
    detectUserLocation(true);

    // Search form handler
    searchForm.addEventListener('submit', function (e) {
        e.preventDefault();
        const query = document.getElementById('query-input').value.trim();
        const city = document.getElementById('city-input').value.trim();

        if (!query) {
            showToast('Please enter a medicine or salt name', 'error');
            return;
        }

        executeSearch(query, city);
    });
}

function executeSearch(query, city) {
    showSearchSkeleton();
    
    const resultsContainer = document.getElementById('results-container');
    const resultsCount = document.getElementById('results-count');

    // Build URL with query parameters including lat/lng if detected
    let url = `/api/search?query=${encodeURIComponent(query)}`;
    if (city) url += `&city=${encodeURIComponent(city)}`;
    if (userLat && userLng) url += `&lat=${userLat}&lng=${userLng}`;

    fetch(url)
        .then(response => {
            if (!response.ok) {
                throw new Error(`Server returned HTTP ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            markersLayer.clearLayers();
            resultsContainer.innerHTML = '';

            // Ensure data is an array
            const results = Array.isArray(data) ? data : (data.results || []);

            if (results.length === 0) {
                if (resultsCount) resultsCount.textContent = '0 found';
                resultsContainer.innerHTML = `
                    <div class="text-center py-5 text-muted">
                        <i class="bi bi-emoji-frown fs-1 text-secondary opacity-50"></i>
                        <p class="mt-2 fw-semibold">No pharmacies found matching "${query}".</p>
                        <small>Try searching generic active ingredients (e.g. Paracetamol) or clear the city filter.</small>
                    </div>
                `;
                showToast('No matching inventory found', 'error');
                return;
            }

            if (resultsCount) resultsCount.textContent = `${results.length} found`;

            const bounds = [];

            results.forEach((item, index) => {
                const medName = item.med_name || item.name || 'Medicine';
                const price = parseFloat(item.price || 0).toFixed(2);
                const stock = item.stock_quantity ?? item.stock ?? 0;
                const shopName = item.shop_name || item.pharmacy_name || 'Pharmacy';
                const salt = item.salt_composition || item.salt || 'Generic Formula';

                const card = document.createElement('div');
                card.className = 'list-group-item list-group-item-action border-0 mb-3 glass-card p-3 rounded-3';
                card.style.animationDelay = `${index * 0.08}s`;
                
                card.innerHTML = `
                    <div class="d-flex justify-content-between align-items-start mb-2">
                        <div>
                            <h6 class="fw-bold text-primary mb-0">${medName}</h6>
                            <small class="text-muted">${item.dosage || 'Standard Dosage'}</small>
                        </div>
                        <span class="fs-5 fw-bold text-success">${price}</span>
                    </div>
                    <div class="mb-2">
                        <span class="badge bg-light text-dark border me-1"><i class="bi bi-capsule me-1"></i>${salt}</span>
                        <span class="badge bg-success-subtle text-success border border-success"><i class="bi bi-check2-circle me-1"></i>${stock} in stock</span>
                    </div>
                    <div class="d-flex justify-content-between align-items-center mt-3 pt-2 border-top">
                        <div>
                            <div class="fw-semibold text-dark small"><i class="bi bi-shop me-1 text-primary"></i>${shopName}</div>
                            <small class="text-muted d-block"><i class="bi bi-geo-alt me-1 text-danger"></i>${item.city || 'Location mapped'}</small>
                        </div>
                        <button class="btn btn-sm btn-outline-primary rounded-pill px-3 fw-semibold" onclick="requestHold(${item.id}, '${medName}')">
                            <i class="bi bi-handbag me-1"></i> Hold
                        </button>
                    </div>
                `;

                resultsContainer.appendChild(card);

                if (item.lat && item.lng) {
                    const lat = parseFloat(item.lat);
                    const lng = parseFloat(item.lng);
                    bounds.push([lat, lng]);

                    const marker = L.marker([lat, lng], { icon: createPulsingIcon() });
                    
                    marker.bindPopup(`
                        <div class="p-1 text-dark">
                            <h6 class="fw-bold text-primary mb-1">${shopName}</h6>
                            <p class="mb-1 small"><strong>${medName}</strong> - ${price}</p>
                            <p class="mb-2 text-muted extra-small">In Stock: ${stock}</p>
                            <button class="btn btn-sm btn-primary w-100 rounded-pill py-1 text-white" onclick="requestHold(${item.id}, '${medName}')">Request Hold</button>
                        </div>
                    `);

                    markersLayer.addLayer(marker);

                    card.addEventListener('mouseenter', () => {
                        searchMap.panTo([lat, lng]);
                        marker.openPopup();
                    });
                }
            });

            if (bounds.length > 0) {
                searchMap.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
            }

            showToast(`Found ${results.length} available listings`);
        })
        .catch(err => {
            console.error('Search fetch error:', err);
            resultsContainer.innerHTML = `
                <div class="alert alert-danger glass-card">
                    <i class="bi bi-exclamation-triangle-fill me-2"></i> Failed to process search. Verify backend route <code>/search</code> is active.
                </div>
            `;
            showToast('Search service unavailable', 'error');
        });
}

// --- 7. HOLD RESERVATION ENGINE ---
function requestHold(medId, medName) {
    const customerPhone = prompt(`Enter your phone number to place a 2-Hour Hold on ${medName}:`);
    
    if (!customerPhone || !customerPhone.trim()) {
        if (customerPhone !== null) {
            showToast('Phone number is required to place a hold', 'error');
        }
        return;
    }

    fetch('/api/reserve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        'med_id': medId,
        'phone': customerPhone.trim()
    })
})
    .then(res => res.json())
    .then(res => {
        if (res.status === 'success' || res.message) {
            showToast(res.message || 'Stock successfully held for 2 hours!');
        } else {
            showToast(res.error || 'Unable to place hold', 'error');
        }
    })
    .catch(() => {
        showToast('Error connecting to reservation system', 'error');
    });
}

// Global Initialization
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initSearchPage();
});