/* ==========================================================================
   MedFinder - Main JavaScript File
   ========================================================================== */

let searchMap = null;
let markersLayer = null;
let osmLayer = null;
let routeLayer = null;
let userLayer = null;
let osmLayerVisible = true;
let osmPharmaciesCache = [];
let verifiedShopCoords = [];
let lastOsmFetchCoords = null;
let osmFetchDebounceTimer = null;
let userMarker = null;
let userAccuracyCircle = null;
let userLat = null;
let userLng = null;
let userLocationLabel = '';
let userTypedCityManually = false;
let lastSearchQuery = '';
let activeRouteTarget = null;
let holdModalInstance = null;
let medInfoModalInstance = null;
let locationRequestSeq = 0;
let hasRealGpsLock = false;
let activeGeoWatchId = null;
let geoWatchStopTimer = null;
let coarseHoldTimer = null;
let bestAccuracyMeters = Infinity;
let lastEnvCoords = null;
let autocompleteDebounceTimer = null;

// Clear any stale coarse coordinates cached by older builds
try {
    localStorage.removeItem('medfinder_saved_user_loc');
} catch (_) {}

// Multi-provider tile stack compatible with embedded preview iframes and all browsers
const TILE_PROVIDERS = [
    {
        name: 'Street Map',
        url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
        options: {
            maxZoom: 19,
            attribution: '&copy; OpenStreetMap contributors, Tiles &copy; Esri'
        }
    },
    {
        name: 'Clean Voyager',
        url: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
        options: {
            subdomains: 'abcd',
            maxZoom: 19,
            attribution: '&copy; OpenStreetMap contributors &copy; CARTO'
        }
    },
    {
        name: 'Detailed Map',
        url: 'https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png',
        options: {
            subdomains: 'abc',
            maxZoom: 19,
            attribution: '&copy; OpenStreetMap contributors, Humanitarian OSM Team'
        }
    }
];

const KNOWN_PLACE_COORDS = {
    'boring road': { lat: 25.6148, lng: 85.1125, label: 'Boring Road, Patna' },
    'sri krishna puri': { lat: 25.6139, lng: 85.1154, label: 'Sri Krishna Puri, Patna' },
    'patliputra': { lat: 25.6258, lng: 85.1072, label: 'Patliputra Colony, Patna' },
    'bailey road': { lat: 25.6093, lng: 85.0908, label: 'Bailey Road, Patna' },
    'ashiana nagar': { lat: 25.6085, lng: 85.0772, label: 'Ashiana Nagar, Patna' },
    'saguna more': { lat: 25.6226, lng: 85.0419, label: 'Saguna More, Danapur' },
    'gola road': { lat: 25.6164, lng: 85.0532, label: 'Gola Road, Danapur' },
    'rps more': { lat: 25.6138, lng: 85.0615, label: 'RPS More, Danapur' },
    'rukanpura': { lat: 25.6105, lng: 85.0718, label: 'Rukanpura, Patna' },
    'sheikhpura': { lat: 25.6082, lng: 85.0875, label: 'Sheikhpura, Patna' },
    'khagaul': { lat: 25.5826, lng: 85.0468, label: 'Khagaul, Danapur' },
    'danapur cantt': { lat: 25.6352, lng: 85.0439, label: 'Danapur Cantt, Patna' },
    '801503': { lat: 25.6226, lng: 85.0445, label: 'Danapur (801503), Patna' },
    '801105': { lat: 25.5826, lng: 85.0468, label: 'Khagaul (801105), Patna' },
    '800014': { lat: 25.6093, lng: 85.0908, label: 'Bailey Road (800014), Patna' },
    '800001': { lat: 25.6078, lng: 85.1378, label: 'Patna GPO (800001), Patna' },
    '800020': { lat: 25.5975, lng: 85.1616, label: 'Kankarbagh (800020), Patna' },
    '800013': { lat: 25.6258, lng: 85.1072, label: 'Patliputra (800013), Patna' },
    'danapur': { lat: 25.6208, lng: 85.0472, label: 'Danapur, Patna' },
    'phulwari sharif': { lat: 25.5764, lng: 85.0715, label: 'Phulwari Sharif, Patna' },
    'anisabad': { lat: 25.5812, lng: 85.0968, label: 'Anisabad, Patna' },
    'gardanibagh': { lat: 25.5895, lng: 85.1190, label: 'Gardanibagh, Patna' },
    'fraser road': { lat: 25.6078, lng: 85.1378, label: 'Fraser Road, Patna' },
    'exhibition road': { lat: 25.6098, lng: 85.1438, label: 'Exhibition Road, Patna' },
    'gandhi maidan': { lat: 25.6184, lng: 85.1419, label: 'Gandhi Maidan, Patna' },
    'ashok rajpath': { lat: 25.6195, lng: 85.1665, label: 'Ashok Rajpath, Patna' },
    'rajendra nagar': { lat: 25.6032, lng: 85.1585, label: 'Rajendra Nagar, Patna' },
    'kankarbagh': { lat: 25.5975, lng: 85.1616, label: 'Kankarbagh, Patna' },
    'patna': { lat: 25.5941, lng: 85.1376, label: 'Patna' },
    'gaya': { lat: 24.7955, lng: 85.0002, label: 'Gaya' },
    'muzaffarpur': { lat: 26.1209, lng: 85.3647, label: 'Muzaffarpur' },
    'bhagalpur': { lat: 25.2425, lng: 86.9842, label: 'Bhagalpur' },
    'ranchi': { lat: 23.3441, lng: 85.3096, label: 'Ranchi' },
    'delhi': { lat: 28.6139, lng: 77.2090, label: 'New Delhi' },
    'new delhi': { lat: 28.6139, lng: 77.2090, label: 'New Delhi' },
    'mumbai': { lat: 19.0760, lng: 72.8777, label: 'Mumbai' },
    'kolkata': { lat: 22.5726, lng: 88.3639, label: 'Kolkata' },
    'bengaluru': { lat: 12.9716, lng: 77.5946, label: 'Bengaluru' },
    'bangalore': { lat: 12.9716, lng: 77.5946, label: 'Bengaluru' },
    'hyderabad': { lat: 17.3850, lng: 78.4867, label: 'Hyderabad' },
    'chennai': { lat: 13.0827, lng: 80.2707, label: 'Chennai' },
    'pune': { lat: 18.5204, lng: 73.8567, label: 'Pune' },
    'lucknow': { lat: 26.8467, lng: 80.9462, label: 'Lucknow' }
};

function attachResilientTileLayer(mapInstance) {
    const layers = TILE_PROVIDERS.map(p => ({
        name: p.name,
        layer: L.tileLayer(p.url, p.options)
    }));

    let activeIndex = 0;
    const errorCounts = new Array(layers.length).fill(0);

    layers.forEach((entry, idx) => {
        if (entry.layer && typeof entry.layer.on === 'function') {
            entry.layer.on('tileerror', () => {
                if (idx !== activeIndex) return;
                errorCounts[idx] += 1;
                if (errorCounts[idx] >= 2 && activeIndex + 1 < layers.length && mapInstance) {
                    const prev = layers[activeIndex].layer;
                    activeIndex += 1;
                    try {
                        if (typeof mapInstance.removeLayer === 'function') {
                            mapInstance.removeLayer(prev);
                        }
                    } catch (_) {}
                    layers[activeIndex].layer.addTo(mapInstance);
                }
            });
        }
    });

    layers[0].layer.addTo(mapInstance);

    if (L.control && typeof L.control.layers === 'function' && mapInstance && typeof mapInstance.addControl === 'function') {
        const baseMaps = {};
        layers.forEach(entry => {
            baseMaps[entry.name] = entry.layer;
        });
        L.control.layers(baseMaps, null, { position: 'topright' }).addTo(mapInstance);
    }

    return layers[0].layer;
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function computeHaversineKm(lat1, lng1, lat2, lng2) {
    const toRad = d => (d * Math.PI) / 180;
    const R = 6371.0;
    const dLat = toRad(lat2 - lat1);
    const dLng = toRad(lng2 - lng1);
    const a =
        Math.sin(dLat / 2) ** 2 +
        Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function formatDistanceMeters(meters) {
    if (!Number.isFinite(meters) || meters < 0) return '0 m';
    if (meters < 1000) return `${Math.max(10, Math.round(meters))} m`;
    return `${(meters / 1000).toFixed(2)} km`;
}

function formatDurationSeconds(seconds) {
    if (!Number.isFinite(seconds) || seconds <= 0) return '~1 min';
    const mins = Math.max(1, Math.round(seconds / 60));
    if (mins < 60) return `~${mins} min`;
    const hrs = Math.floor(mins / 60);
    const rem = mins % 60;
    return rem > 0 ? `~${hrs}h ${rem}m` : `~${hrs}h`;
}

// --- GEOCODING HELPERS (LOCAL AREA + CITY) ---
function cleanDistrictName(raw) {
    return String(raw || '')
        .replace(/\s+(District|Subdistrict|Tehsil|Taluka|Block|Division)$/i, '')
        .trim();
}

function isUsablePlaceToken(val) {
    const s = String(val || '').trim();
    if (!s || s.length < 2) return false;
    if (/^[\d\s\-+/,.]+$/.test(s)) return false;
    if (/^(india|asia|indian subcontinent)$/i.test(s)) return false;
    if (s.includes('/')) return false;
    return true;
}

function buildAreaCityLabel(area, city) {
    const cleanArea = isUsablePlaceToken(area) ? String(area).trim() : '';
    const cleanCity = isUsablePlaceToken(city) ? String(city).trim() : '';
    if (cleanArea && cleanCity && cleanArea.toLowerCase() !== cleanCity.toLowerCase()) {
        if (cleanArea.toLowerCase().includes(cleanCity.toLowerCase())) {
            return cleanArea;
        }
        return `${cleanArea}, ${cleanCity}`;
    }
    return cleanArea || cleanCity || '';
}

function pickFirstDistinct(candidates, excludeLower = '') {
    for (const item of candidates) {
        if (!isUsablePlaceToken(item)) continue;
        const trimmed = String(item).trim();
        if (excludeLower && trimmed.toLowerCase() === excludeLower) continue;
        return trimmed;
    }
    return '';
}

function extractLocalNameFromNominatim(data) {
    const addr = (data && data.address) || {};
    const namedPlace = (data && data.name && isUsablePlaceToken(data.name)) ? data.name : '';

    const localCandidates = [
        addr.neighbourhood,
        addr.suburb,
        addr.quarter,
        addr.locality,
        addr.residential,
        addr.hamlet,
        addr.road,
        addr.city_district,
        namedPlace,
        addr.village,
        addr.town
    ];

    const bestLocal = pickFirstDistinct(localCandidates);
    const cityCandidates = [
        addr.city,
        addr.town,
        addr.municipality,
        addr.village,
        cleanDistrictName(addr.state_district),
        cleanDistrictName(addr.county)
    ];
    const bestCity = pickFirstDistinct(cityCandidates, bestLocal.toLowerCase());
    return buildAreaCityLabel(bestLocal, bestCity);
}

function extractLocalNameFromBigDataCloud(data) {
    if (!data) return '';
    const adminList = Array.isArray(data.localityInfo && data.localityInfo.administrative)
        ? [...data.localityInfo.administrative].sort((a, b) => (b.adminLevel || b.order || 0) - (a.adminLevel || a.order || 0))
        : [];
    const infoList = Array.isArray(data.localityInfo && data.localityInfo.informative)
        ? [...data.localityInfo.informative].sort((a, b) => (b.order || 0) - (a.order || 0))
        : [];

    const stateLower = String(data.principalSubdivision || '').trim().toLowerCase();

    const districtEntry = adminList.find(e => (e.adminLevel === 5 || e.adminLevel === 6) && isUsablePlaceToken(e.name));
    const bestCity = pickFirstDistinct([
        data.city,
        districtEntry && cleanDistrictName(districtEntry.name),
        data.locality
    ]);

    const fineAdmin = adminList
        .filter(e => (e.adminLevel || 0) >= 7 && isUsablePlaceToken(e.name) && String(e.name).trim().toLowerCase() !== stateLower)
        .map(e => cleanDistrictName(e.name));
    const fineInfo = infoList
        .filter(e => {
            const desc = String(e.description || '').toLowerCase();
            if (desc.includes('time zone') || desc.includes('continent') || desc.includes('country') || desc.includes('fips') || desc.includes('iso')) {
                return false;
            }
            return isUsablePlaceToken(e.name) && String(e.name).trim().toLowerCase() !== stateLower;
        })
        .map(e => String(e.name).trim());

    const bestLocal = pickFirstDistinct(
        [data.locality, ...fineAdmin, ...fineInfo],
        bestCity.toLowerCase()
    );

    return buildAreaCityLabel(bestLocal, bestCity || cleanDistrictName(data.principalSubdivision));
}

function findNearestKnownArea(lat, lng) {
    let bestLabel = '';
    let bestKm = Infinity;
    for (const info of Object.values(KNOWN_PLACE_COORDS)) {
        const km = computeHaversineKm(lat, lng, info.lat, info.lng);
        if (km < bestKm) {
            bestKm = km;
            bestLabel = info.label;
        }
    }
    return bestKm <= 4.0 ? bestLabel : '';
}

function reverseGeocodeCity(lat, lng) {
    // 1. Nominatim (zoom=18 neighborhood detail) -> 2. Esri ArcGIS -> 3. Photon (OSM CORS-friendly) -> 4. BigDataCloud -> 5. Nearest known area / coords
    return fetch(`https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lng}&zoom=18&addressdetails=1&accept-language=en`)
        .then(res => {
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return res.json();
        })
        .then(data => {
            const label = extractLocalNameFromNominatim(data);
            if (!label) throw new Error('Empty Nominatim label');
            return label;
        })
        .catch(() =>
            fetch(`https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/reverseGeocode?f=json&location=${encodeURIComponent(lng + ',' + lat)}&langCode=EN`)
                .then(res => {
                    if (!res.ok) throw new Error(`HTTP ${res.status}`);
                    return res.json();
                })
                .then(data => {
                    if (!data || data.error) throw new Error('ArcGIS token/service error');
                    const a = data.address || {};
                    const bestLocal = pickFirstDistinct([a.Neighborhood, a.District, a.PlaceName, a.StreetName, a.Address]);
                    const bestCity = pickFirstDistinct([a.City, cleanDistrictName(a.Subregion)], bestLocal.toLowerCase());
                    const label = buildAreaCityLabel(bestLocal, bestCity);
                    if (!label) throw new Error('Empty ArcGIS label');
                    return label;
                })
                .catch(() =>
                    fetch(`https://photon.komoot.io/reverse?lat=${lat}&lon=${lng}&lang=en`)
                        .then(res => {
                            if (!res.ok) throw new Error(`HTTP ${res.status}`);
                            return res.json();
                        })
                        .then(data => {
                            const props = data && data.features && data.features[0] && data.features[0].properties;
                            if (!props) throw new Error('Empty Photon result');
                            const bestLocal = pickFirstDistinct([
                                props.district,
                                props.locality,
                                props.suburb,
                                props.street,
                                props.osm_value !== 'city' ? props.name : ''
                            ]);
                            const bestCity = pickFirstDistinct(
                                [props.city, props.town, cleanDistrictName(props.county)],
                                bestLocal.toLowerCase()
                            );
                            const label = buildAreaCityLabel(bestLocal, bestCity);
                            if (!label) throw new Error('Empty Photon label');
                            return label;
                        })
                        .catch(() =>
                            fetch(`https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=${lat}&longitude=${lng}&localityLanguage=en`)
                                .then(res => {
                                    if (!res.ok) throw new Error(`HTTP ${res.status}`);
                                    return res.json();
                                })
                                .then(data => {
                                    const label = extractLocalNameFromBigDataCloud(data);
                                    if (!label) throw new Error('Empty BDC label');
                                    return label;
                                })
                                .catch(() => findNearestKnownArea(lat, lng) || `${Number(lat).toFixed(4)}, ${Number(lng).toFixed(4)}`)
                        )
                )
        );
}

function resolveIndianPincodeLabel(pin) {
    const cleanPin = String(pin || '').trim();
    if (!/^\d{6}$/.test(cleanPin)) return Promise.resolve(null);
    return fetch(`https://api.postalpincode.in/pincode/${encodeURIComponent(cleanPin)}`)
        .then(res => (res.ok ? res.json() : null))
        .then(data => {
            const entry = Array.isArray(data) ? data[0] : null;
            const offices = entry && Array.isArray(entry.PostOffice) ? entry.PostOffice : [];
            if (!offices.length) return null;
            const first = offices[0];
            const area = first.Name || '';
            const district = cleanDistrictName(first.District || '');
            const state = first.State || '';
            return {
                label: buildAreaCityLabel(area, district) || `${cleanPin}, ${district}`,
                searchQuery: [area, district, state, cleanPin, 'India'].filter(Boolean).join(', '),
                offices: offices.slice(0, 5)
            };
        })
        .catch(() => null);
}

function forwardGeocodeAddress(query) {
    const trimmed = String(query || '').trim();
    if (!trimmed) return Promise.resolve(null);

    if (/^\d{6}$/.test(trimmed)) {
        if (KNOWN_PLACE_COORDS[trimmed]) {
            const known = KNOWN_PLACE_COORDS[trimmed];
            return Promise.resolve({ lat: known.lat, lng: known.lng, label: known.label });
        }
        return resolveIndianPincodeLabel(trimmed).then(pinInfo => {
            const targetQ = (pinInfo && pinInfo.searchQuery) || `${trimmed}, India`;
            return runStandardForwardGeocode(targetQ).then(coords => {
                if (coords && pinInfo && pinInfo.label) {
                    coords.label = pinInfo.label;
                }
                return coords;
            });
        });
    }

    return runStandardForwardGeocode(trimmed);
}

function runStandardForwardGeocode(query) {
    return fetch('https://nominatim.openstreetmap.org/search?format=json&limit=1&q=' + encodeURIComponent(query))
        .then(res => {
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return res.json();
        })
        .then(data => {
            if (Array.isArray(data) && data.length > 0) {
                return { lat: parseFloat(data[0].lat), lng: parseFloat(data[0].lon) };
            }
            throw new Error('No Nominatim match');
        })
        .catch(() =>
            fetch('https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates?f=json&maxLocations=1&SingleLine=' + encodeURIComponent(query))
                .then(res => {
                    if (!res.ok) throw new Error(`HTTP ${res.status}`);
                    return res.json();
                })
                .then(data => {
                    const cand = data && !data.error && data.candidates && data.candidates[0];
                    if (cand && cand.location) {
                        return { lat: parseFloat(cand.location.y), lng: parseFloat(cand.location.x) };
                    }
                    throw new Error('No ArcGIS candidate');
                })
                .catch(() =>
                    fetch('https://photon.komoot.io/api/?limit=1&q=' + encodeURIComponent(query))
                        .then(res => {
                            if (!res.ok) throw new Error(`HTTP ${res.status}`);
                            return res.json();
                        })
                        .then(data => {
                            const feat = data && data.features && data.features[0];
                            const coords = feat && feat.geometry && feat.geometry.coordinates;
                            if (Array.isArray(coords) && coords.length >= 2) {
                                return { lat: parseFloat(coords[1]), lng: parseFloat(coords[0]) };
                            }
                            throw new Error('No Photon match');
                        })
                        .catch(() => {
                            const lower = String(query || '').toLowerCase();
                            for (const [key, val] of Object.entries(KNOWN_PLACE_COORDS)) {
                                if (lower.includes(key)) return { lat: val.lat, lng: val.lng, label: val.label };
                            }
                            return null;
                        })
                )
        );
}

// --- LIVE LOCATION & PIN AUTOCOMPLETE (PHOTON + NOMINATIM + INDIA POST PIN API) ---
function fetchPlaceSuggestions(rawQuery) {
    const q = String(rawQuery || '').trim();
    if (q.length < 2) return Promise.resolve([]);
    const lower = q.toLowerCase();

    const localMatches = [];
    const seenLabels = new Set();
    for (const [key, val] of Object.entries(KNOWN_PLACE_COORDS)) {
        const displayLabel = val.label || key;
        if (key.includes(lower) || displayLabel.toLowerCase().includes(lower)) {
            const norm = displayLabel.toLowerCase();
            if (!seenLabels.has(norm)) {
                seenLabels.add(norm);
                localMatches.push({
                    label: displayLabel,
                    subtitle: /^\d{6}$/.test(key) ? `PIN ${key} · Verified Area` : 'Quick Local Match',
                    lat: val.lat,
                    lng: val.lng
                });
            }
        }
        if (localMatches.length >= 4) break;
    }

    if (/^\d{6}$/.test(q)) {
        return resolveIndianPincodeLabel(q).then(pinInfo => {
            if (!pinInfo || !Array.isArray(pinInfo.offices)) return localMatches;
            const pinItems = pinInfo.offices.slice(0, 4).map(po => {
                const label = buildAreaCityLabel(po.Name, cleanDistrictName(po.District)) || `${po.Name}, ${q}`;
                return {
                    label,
                    subtitle: `PIN ${q} · ${po.State || 'India'}`,
                    lat: localMatches[0] ? localMatches[0].lat : null,
                    lng: localMatches[0] ? localMatches[0].lng : null,
                    searchQuery: [po.Name, cleanDistrictName(po.District), po.State, q, 'India'].filter(Boolean).join(', ')
                };
            });
            return [...localMatches, ...pinItems].slice(0, 6);
        });
    }

    return fetch(`https://photon.komoot.io/api/?limit=5&lang=en&q=${encodeURIComponent(q)}`)
        .then(res => {
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return res.json();
        })
        .then(data => {
            const feats = (data && Array.isArray(data.features)) ? data.features : [];
            const remote = [];
            feats.forEach(f => {
                const props = f && f.properties;
                const coords = f && f.geometry && f.geometry.coordinates;
                if (!props || !Array.isArray(coords) || coords.length < 2) return;
                const primary = pickFirstDistinct([props.name, props.street, props.district, props.locality]);
                const secondary = pickFirstDistinct(
                    [props.city, props.town, cleanDistrictName(props.county), props.state],
                    primary.toLowerCase()
                );
                const label = buildAreaCityLabel(primary, secondary);
                if (!label) return;
                const norm = label.toLowerCase();
                if (seenLabels.has(norm)) return;
                seenLabels.add(norm);
                remote.push({
                    label,
                    subtitle: [props.state, props.country].filter(Boolean).join(', '),
                    lat: parseFloat(coords[1]),
                    lng: parseFloat(coords[0])
                });
            });
            return [...localMatches, ...remote].slice(0, 6);
        })
        .catch(() => localMatches);
}

// --- LIVE LOCAL WEATHER, AQI & STORAGE ADVISORY (OPEN-METEO PUBLIC API) ---
function updateLocalEnvironmentBar(lat, lng, labelText = '') {
    const barEl = document.getElementById('local-env-bar');
    if (!barEl || lat === null || lng === null || Number.isNaN(Number(lat)) || Number.isNaN(Number(lng))) return;

    const numLat = Number(lat);
    const numLng = Number(lng);
    if (lastEnvCoords && computeHaversineKm(lastEnvCoords.lat, lastEnvCoords.lng, numLat, numLng) < 0.8) {
        if (labelText) {
            const locEl = document.getElementById('env-location-label');
            if (locEl) locEl.innerHTML = `<i class="bi bi-broadcast-pin me-1"></i>${escapeHtml(labelText)}`;
        }
        return;
    }
    lastEnvCoords = { lat: numLat, lng: numLng };

    const weatherUrl = `https://api.open-meteo.com/v1/forecast?latitude=${numLat.toFixed(4)}&longitude=${numLng.toFixed(4)}&current=temperature_2m,relative_humidity_2m`;
    const aqiUrl = `https://air-quality-api.open-meteo.com/v1/air-quality?latitude=${numLat.toFixed(4)}&longitude=${numLng.toFixed(4)}&current=us_aqi,pm2_5`;

    Promise.all([
        fetch(weatherUrl).then(r => (r.ok ? r.json() : null)).catch(() => null),
        fetch(aqiUrl).then(r => (r.ok ? r.json() : null)).catch(() => null)
    ]).then(([weatherData, aqiData]) => {
        const currentW = weatherData && weatherData.current;
        if (!currentW || currentW.temperature_2m === undefined) return;

        const temp = Number(currentW.temperature_2m);
        const humidity = Number(currentW.relative_humidity_2m || 0);
        const aqi = aqiData && aqiData.current && aqiData.current.us_aqi !== undefined
            ? Math.round(Number(aqiData.current.us_aqi))
            : null;

        const locEl = document.getElementById('env-location-label');
        const tempEl = document.getElementById('env-temp-val');
        const humEl = document.getElementById('env-humidity-val');
        const aqiPill = document.getElementById('env-aqi-pill');
        const aqiVal = document.getElementById('env-aqi-val');
        const tipText = document.getElementById('env-health-tip-text');

        if (locEl) {
            const displayLoc = labelText || userLocationLabel || 'Local Conditions';
            locEl.innerHTML = `<i class="bi bi-broadcast-pin me-1"></i>${escapeHtml(displayLoc)}`;
        }
        if (tempEl) tempEl.textContent = `${temp.toFixed(1)}°C`;
        if (humEl) humEl.textContent = `${Math.round(humidity)}% RH`;

        if (aqi !== null && Number.isFinite(aqi) && aqiPill && aqiVal) {
            const aqiBand = aqi <= 50 ? 'Good' : aqi <= 100 ? 'Moderate' : aqi <= 150 ? 'Sensitive' : 'Poor';
            aqiVal.textContent = `AQI ${aqi} · ${aqiBand}`;
            aqiPill.classList.remove('d-none');
        }

        if (tipText) {
            if (temp >= 30) {
                tipText.textContent = `Warm (${temp.toFixed(1)}°C) — keep insulin, eye drops & syrups below 25°C away from heat.`;
            } else if (aqi !== null && aqi > 135) {
                tipText.textContent = `Elevated AQI (${aqi}) — N95 masks, saline sprays & prescribed inhalers advised outdoors.`;
            } else if (humidity >= 80) {
                tipText.textContent = `High humidity (${Math.round(humidity)}%) — keep tablet strips sealed in a dry box.`;
            } else {
                tipText.textContent = `Live local conditions (${temp.toFixed(1)}°C) — store medicines in a cool, dry cabinet.`;
            }
        }

        barEl.classList.remove('d-none');
    }).catch(() => {});
}

function setLocateButtonLoading(isLoading) {
    const icon = document.getElementById('detect-location-icon');
    if (!icon) return;
    if (isLoading) {
        icon.classList.add('locating-spin');
    } else {
        icon.classList.remove('locating-spin');
    }
}

function requestBrowserPosition(onSuccess, onError) {
    if (!navigator.geolocation) {
        onError({ code: 0, message: 'Geolocation is not supported by your browser' });
        return;
    }

    // Request a fresh high-accuracy GPS / Wi-Fi triangulation fix (maximumAge: 0 avoids stale coarse caches).
    navigator.geolocation.getCurrentPosition(
        onSuccess,
        (err) => {
            if (err && (err.code === 2 || err.code === 3)) {
                navigator.geolocation.getCurrentPosition(
                    onSuccess,
                    onError,
                    { enableHighAccuracy: false, timeout: 10000, maximumAge: 0 }
                );
                return;
            }
            onError(err);
        },
        { enableHighAccuracy: true, timeout: 18000, maximumAge: 0 }
    );
}

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

    const iconClass = type === 'error'
        ? 'bi-exclamation-triangle-fill text-danger'
        : (type === 'info' ? 'bi-geo-alt-fill text-primary' : 'bi-check-circle-fill text-success');

    const iconEl = document.createElement('i');
    iconEl.className = `bi ${iconClass} fs-5`;

    const spanEl = document.createElement('span');
    spanEl.className = 'fw-semibold small text-dark';
    spanEl.textContent = message;

    toast.appendChild(iconEl);
    toast.appendChild(spanEl);
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

function createLocalOsmIcon() {
    return L.divIcon({
        className: 'custom-osm-pin',
        html: `<div class="osm-pin-core">+</div>`,
        iconSize: [18, 18],
        iconAnchor: [9, 9],
        popupAnchor: [0, -10]
    });
}

function buildClaimStoreUrl(osmShop) {
    const params = new URLSearchParams();
    if (osmShop.name) params.set('name', osmShop.name);
    if (osmShop.area) params.set('city', osmShop.area);
    if (Number.isFinite(osmShop.lat)) params.set('lat', Number(osmShop.lat).toFixed(6));
    if (Number.isFinite(osmShop.lng)) params.set('lng', Number(osmShop.lng).toFixed(6));
    if (osmShop.phone) params.set('phone', osmShop.phone);
    if (osmShop.opening_hours) params.set('hours', osmShop.opening_hours);
    return `/register?${params.toString()}`;
}

function toggleOsmPharmaciesLayer() {
    osmLayerVisible = !osmLayerVisible;
    const btn = document.getElementById('toggle-osm-layer-btn');
    if (btn) {
        btn.classList.toggle('opacity-50', !osmLayerVisible);
    }
    if (!searchMap || !osmLayer) return;
    if (osmLayerVisible) {
        osmLayer.addTo(searchMap);
        renderOsmLayerMarkers();
    } else {
        try { searchMap.removeLayer(osmLayer); } catch (_) {}
    }
}

function renderOsmLayerMarkers() {
    if (!osmLayer || typeof osmLayer.clearLayers !== 'function') return;
    osmLayer.clearLayers();
    if (!osmLayerVisible || !Array.isArray(osmPharmaciesCache)) return;

    const refLat = userLat !== null ? userLat : (searchMap ? searchMap.getCenter().lat : null);
    const refLng = userLng !== null ? userLng : (searchMap ? searchMap.getCenter().lng : null);

    osmPharmaciesCache.forEach(osmShop => {
        if (!Number.isFinite(osmShop.lat) || !Number.isFinite(osmShop.lng)) return;
        const distKm = (refLat !== null && refLng !== null)
            ? computeHaversineKm(refLat, refLng, osmShop.lat, osmShop.lng).toFixed(2)
            : null;
        const marker = L.marker([osmShop.lat, osmShop.lng], { icon: createLocalOsmIcon() });

        const popupEl = document.createElement('div');
        popupEl.className = 'p-1 text-dark';
        popupEl.style.minWidth = '210px';
        const claimUrl = buildClaimStoreUrl(osmShop);
        const waUrl = osmShop.phone ? buildWhatsAppInquiryUrl(osmShop.phone, osmShop.name, lastSearchQuery || 'medicine') : '';
        popupEl.innerHTML = `
            <div class="mb-1"><span class="osm-unverified-badge"><i class="bi bi-geo-alt-fill"></i>Local Pharmacy (OSM) · Stock Unverified</span></div>
            <h6 class="fw-bold text-dark mb-1">${escapeHtml(osmShop.name)}</h6>
            <p class="mb-1 small text-muted"><i class="bi bi-signpost-2 text-warning me-1"></i>${escapeHtml(osmShop.area || 'Neighborhood Medical Store')}${distKm ? ` · ${distKm} km` : ''}</p>
            ${osmShop.opening_hours ? `<p class="mb-1 small text-muted"><i class="bi bi-clock me-1"></i>${escapeHtml(osmShop.opening_hours)}</p>` : ''}
            ${osmShop.phone ? `<p class="mb-2 small"><i class="bi bi-telephone text-success me-1"></i><a href="tel:${escapeHtml(osmShop.phone)}" class="text-decoration-none">${escapeHtml(osmShop.phone)}</a></p>` : ''}
            <div class="d-flex flex-wrap gap-1 mt-2">
                <button type="button" class="btn btn-sm btn-outline-primary rounded-pill py-1 px-2 flex-grow-1 osm-popup-dir-btn">
                    <i class="bi bi-sign-turn-right-fill me-1"></i>Directions
                </button>
                ${waUrl ? `<a href="${escapeHtml(waUrl)}" target="_blank" rel="noopener" class="btn btn-sm whatsapp-inquiry-btn rounded-pill py-1 px-2" title="WhatsApp Inquiry"><i class="bi bi-whatsapp"></i></a>` : ''}
                <a href="${escapeHtml(claimUrl)}" class="btn btn-sm btn-warning text-dark rounded-pill py-1 px-2 fw-semibold" title="Pharmacy owner? Claim store &amp; publish live stock">
                    <i class="bi bi-patch-plus me-1"></i>Claim
                </a>
            </div>
        `;
        popupEl.querySelector('.osm-popup-dir-btn')?.addEventListener('click', () => {
            showDirectionsOnMap(osmShop.lat, osmShop.lng, osmShop.name);
        });
        marker.bindPopup(popupEl);
        osmLayer.addLayer(marker);
    });
}

function discoverNearbyOsmPharmacies(lat, lng, radiusMeters = 4500) {
    const numLat = Number(lat);
    const numLng = Number(lng);
    if (!Number.isFinite(numLat) || !Number.isFinite(numLng)) return Promise.resolve([]);

    if (lastOsmFetchCoords && computeHaversineKm(lastOsmFetchCoords.lat, lastOsmFetchCoords.lng, numLat, numLng) < 0.65 && osmPharmaciesCache.length > 0) {
        renderOsmLayerMarkers();
        return Promise.resolve(osmPharmaciesCache);
    }
    lastOsmFetchCoords = { lat: numLat, lng: numLng };

    const overpassQuery = `[out:json][timeout:14];(node["amenity"="pharmacy"](around:${radiusMeters},${numLat.toFixed(5)},${numLng.toFixed(5)});way["amenity"="pharmacy"](around:${radiusMeters},${numLat.toFixed(5)},${numLng.toFixed(5)});node["healthcare"="pharmacy"](around:${radiusMeters},${numLat.toFixed(5)},${numLng.toFixed(5)});node["shop"="chemist"](around:${radiusMeters},${numLat.toFixed(5)},${numLng.toFixed(5)}););out center 60;`;
    const endpoints = [
        'https://overpass-api.de/api/interpreter',
        'https://overpass.kumi.systems/api/interpreter'
    ];

    const badgeEl = document.getElementById('osm-nearby-count-badge');

    const tryOverpass = (idx) => {
        if (idx >= endpoints.length) return Promise.resolve([]);
        return fetch(`${endpoints[idx]}?data=${encodeURIComponent(overpassQuery)}`)
            .then(r => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                return r.json();
            })
            .then(data => {
                const elements = (data && Array.isArray(data.elements)) ? data.elements : [];
                const parsed = [];
                const seenKeys = new Set();

                elements.forEach(el => {
                    const elLat = Number(el.lat ?? (el.center && el.center.lat));
                    const elLng = Number(el.lon ?? (el.center && el.center.lon));
                    if (!Number.isFinite(elLat) || !Number.isFinite(elLng)) return;

                    // Deduplicate against verified partner stores within 60 meters
                    const nearVerified = verifiedShopCoords.some(v => computeHaversineKm(v.lat, v.lng, elLat, elLng) < 0.06);
                    if (nearVerified) return;

                    const tags = el.tags || {};
                    const rawName = (tags.name || tags['name:en'] || tags.brand || tags.operator || '').trim();
                    const displayName = rawName || 'Local Medical & Chemist Store';
                    const dedupKey = `${displayName.toLowerCase()}_${elLat.toFixed(3)}_${elLng.toFixed(3)}`;
                    if (seenKeys.has(dedupKey)) return;
                    seenKeys.add(dedupKey);

                    const areaParts = [
                        tags['addr:street'],
                        tags['addr:suburb'] || tags['addr:neighbourhood'],
                        tags['addr:city'] || userLocationLabel || ''
                    ].filter(Boolean);

                    parsed.push({
                        osm_id: `${el.type || 'node'}/${el.id}`,
                        name: displayName,
                        lat: elLat,
                        lng: elLng,
                        area: areaParts.slice(0, 2).join(', ') || (userLocationLabel || 'Local Area'),
                        phone: (tags.phone || tags['contact:phone'] || tags['contact:mobile'] || '').trim(),
                        opening_hours: (tags.opening_hours || '').trim()
                    });
                });

                parsed.sort((a, b) => computeHaversineKm(numLat, numLng, a.lat, a.lng) - computeHaversineKm(numLat, numLng, b.lat, b.lng));
                osmPharmaciesCache = parsed.slice(0, 45);
                if (badgeEl) badgeEl.textContent = String(osmPharmaciesCache.length);
                renderOsmLayerMarkers();
                return osmPharmaciesCache;
            })
            .catch(() => tryOverpass(idx + 1));
    };

    return tryOverpass(0);
}

function scheduleNearbyOsmDiscovery(lat, lng) {
    if (osmFetchDebounceTimer) clearTimeout(osmFetchDebounceTimer);
    osmFetchDebounceTimer = setTimeout(() => {
        discoverNearbyOsmPharmacies(lat, lng);
    }, 320);
}

function createUserLocationIcon() {
    return L.divIcon({
        className: 'custom-user-pin',
        html: `<div class="user-pin-pulse"></div><div class="user-pin-core"></div>`,
        iconSize: [22, 22],
        iconAnchor: [11, 11],
        popupAnchor: [0, -12]
    });
}

function buildUserPopupHtml(placeText, accuracyMeters) {
    const locLine = placeText
        ? `<div class="small fw-semibold text-primary mt-1"><i class="bi bi-geo-alt-fill text-danger me-1"></i>${escapeHtml(placeText)}</div>`
        : '';
    const accLine = (accuracyMeters && Number.isFinite(accuracyMeters))
        ? `<small class="text-muted d-block">Accuracy: ±${Math.round(accuracyMeters)}m · Drag pin to adjust</small>`
        : `<small class="text-muted d-block">Drag red pin to fine-tune</small>`;
    return `<div class="p-1 text-dark"><b>Your Current Location</b>${locLine}${accLine}</div>`;
}

function buildUserTooltipHtml(placeText) {
    const text = placeText || 'Your Current Location';
    return `<i class="bi bi-geo-alt-fill text-danger me-1"></i>${escapeHtml(text)}`;
}

function updateLocationSearchBox(localName, forceOverwrite = false) {
    const cityInput = document.getElementById('city-input');
    if (!cityInput || !localName) return;
    const userActivelyEditing = userTypedCityManually && document.activeElement === cityInput;
    if (forceOverwrite || !userActivelyEditing) {
        cityInput.value = localName;
        cityInput.placeholder = 'Location / Area';
    }
}

// --- 4. ACCURATE USER GEOLOCATION (PROGRESSIVE HIGH-ACCURACY GPS LOCK) ---
function stopActiveGeoWatch() {
    if (coarseHoldTimer) {
        clearTimeout(coarseHoldTimer);
        coarseHoldTimer = null;
    }
    if (geoWatchStopTimer) {
        clearTimeout(geoWatchStopTimer);
        geoWatchStopTimer = null;
    }
    if (activeGeoWatchId !== null && navigator.geolocation && typeof navigator.geolocation.clearWatch === 'function') {
        try { navigator.geolocation.clearWatch(activeGeoWatchId); } catch (_) {}
    }
    activeGeoWatchId = null;
}

function chooseZoomForAccuracy(accuracyMeters) {
    if (!Number.isFinite(accuracyMeters) || accuracyMeters <= 0) return 15;
    if (accuracyMeters <= 150) return 16;
    if (accuracyMeters <= 600) return 15;
    return 14;
}

function placeOrUpdateUserMarker(lat, lng, placeText = '', accuracyMeters = null, centerMap = true, openBubble = true, zoomLevel = null) {
    userLat = lat;
    userLng = lng;
    if (placeText) userLocationLabel = placeText;

    if (!searchMap) return;

    const targetHost = userLayer || searchMap;
    if (typeof searchMap.invalidateSize === 'function') {
        try { searchMap.invalidateSize(false); } catch (_) {}
    }

    const effectiveZoom = zoomLevel !== null ? zoomLevel : chooseZoomForAccuracy(accuracyMeters);
    if (centerMap) {
        searchMap.setView([userLat, userLng], effectiveZoom);
    }

    if (userLayer && typeof userLayer.clearLayers === 'function') {
        userLayer.clearLayers();
        userAccuracyCircle = null;
        userMarker = null;
    } else {
        if (userAccuracyCircle) {
            try { searchMap.removeLayer(userAccuracyCircle); } catch (_) {}
            userAccuracyCircle = null;
        }
        if (userMarker) {
            try { searchMap.removeLayer(userMarker); } catch (_) {}
            userMarker = null;
        }
    }

    if (accuracyMeters && Number.isFinite(accuracyMeters) && accuracyMeters <= 10000 && typeof L.circle === 'function') {
        userAccuracyCircle = L.circle([userLat, userLng], {
            radius: Math.max(12, accuracyMeters),
            color: '#dc3545',
            weight: 1.3,
            fillColor: '#dc3545',
            fillOpacity: 0.09,
            interactive: false
        }).addTo(targetHost);
    }

    userMarker = L.marker([userLat, userLng], {
        icon: createUserLocationIcon(),
        draggable: true,
        zIndexOffset: 1200
    })
        .addTo(targetHost)
        .bindPopup(buildUserPopupHtml(userLocationLabel, accuracyMeters));

    if (userMarker && typeof userMarker.bindTooltip === 'function') {
        userMarker.bindTooltip(buildUserTooltipHtml(userLocationLabel), {
            permanent: true,
            direction: 'bottom',
            offset: [0, 12],
            className: 'user-location-tooltip'
        });
    }

    if (userMarker && typeof userMarker.on === 'function') {
        userMarker.on('dragend', () => {
            const pos = userMarker.getLatLng();
            if (!pos) return;
            stopActiveGeoWatch();
            hasRealGpsLock = true;
            bestAccuracyMeters = 10;
            userLat = pos.lat;
            userLng = pos.lng;
            userTypedCityManually = false;
            const reqId = ++locationRequestSeq;
            reverseGeocodeCity(userLat, userLng).then(resolvedArea => {
                if (reqId !== locationRequestSeq) return;
                userLocationLabel = resolvedArea;
                updateLocationSearchBox(resolvedArea, true);
                if (userMarker) {
                    if (typeof userMarker.setPopupContent === 'function') {
                        userMarker.setPopupContent(buildUserPopupHtml(resolvedArea, null));
                    } else {
                        userMarker.bindPopup(buildUserPopupHtml(resolvedArea, null));
                    }
                    if (typeof userMarker.setTooltipContent === 'function') {
                        userMarker.setTooltipContent(buildUserTooltipHtml(resolvedArea));
                    }
                }
                if (activeRouteTarget) {
                    showDirectionsOnMap(activeRouteTarget.lat, activeRouteTarget.lng, activeRouteTarget.shopName, true);
                } else if (lastSearchQuery) {
                    const cityVal = document.getElementById('city-input')?.value.trim() || '';
                    executeSearch(lastSearchQuery, cityVal, true, true);
                }
            });
        });
    }

    if (openBubble && userMarker) {
        userMarker.openPopup();
    }

    updateLocalEnvironmentBar(userLat, userLng, userLocationLabel || placeText);
    scheduleNearbyOsmDiscovery(userLat, userLng);
}

function applyDetectedLocation(lat, lng, silent, accuracyMeters = null) {
    const reqId = ++locationRequestSeq;
    const shouldCenterImmediately = !activeRouteTarget && !lastSearchQuery;
    const zoomTarget = chooseZoomForAccuracy(accuracyMeters);

    document.getElementById('gps-iframe-notice')?.classList.add('d-none');

    // 1. Immediately place/update the pulsing red marker at the exact GPS coordinates
    placeOrUpdateUserMarker(
        lat,
        lng,
        userLocationLabel,
        accuracyMeters,
        shouldCenterImmediately,
        shouldCenterImmediately,
        zoomTarget
    );

    const cityInput = document.getElementById('city-input');
    if (cityInput && (!silent || !userTypedCityManually) && !cityInput.value.trim()) {
        cityInput.placeholder = 'Resolving street / area...';
    }

    // 2. Reverse-geocode the exact street/colony + city name into #city-input and marker badge
    reverseGeocodeCity(lat, lng).then(localName => {
        if (reqId !== locationRequestSeq) return;
        setLocateButtonLoading(false);
        userLocationLabel = localName;

        if (!silent || !userTypedCityManually) {
            updateLocationSearchBox(localName, !silent);
        }

        if (userMarker) {
            if (typeof userMarker.setPopupContent === 'function') {
                userMarker.setPopupContent(buildUserPopupHtml(localName, accuracyMeters));
            } else {
                userMarker.bindPopup(buildUserPopupHtml(localName, accuracyMeters));
            }
            if (typeof userMarker.setTooltipContent === 'function') {
                userMarker.setTooltipContent(buildUserTooltipHtml(localName));
            } else if (typeof userMarker.bindTooltip === 'function') {
                userMarker.bindTooltip(buildUserTooltipHtml(localName), {
                    permanent: true,
                    direction: 'bottom',
                    offset: [0, 12],
                    className: 'user-location-tooltip'
                });
            }
            if (shouldCenterImmediately) {
                userMarker.openPopup();
            }
        }

        updateLocalEnvironmentBar(lat, lng, localName);

        if (activeRouteTarget) {
            showDirectionsOnMap(activeRouteTarget.lat, activeRouteTarget.lng, activeRouteTarget.shopName, true);
        } else if (lastSearchQuery) {
            const cityVal = document.getElementById('city-input')?.value.trim() || localName || '';
            executeSearch(lastSearchQuery, cityVal, true, false);
        }
    });

    if (!silent) {
        showToast('Accurate GPS location locked on map & Search Nearby box!');
    }
}

function detectUserLocation(silent = false) {
    const cityInput = document.getElementById('city-input');
    if (!navigator.geolocation) {
        if (cityInput && !cityInput.value.trim()) cityInput.placeholder = 'Location / Area';
        if (!silent) showToast('Geolocation is not supported by your browser', 'error');
        return;
    }

    stopActiveGeoWatch();
    if (!silent) {
        bestAccuracyMeters = Infinity;
        hasRealGpsLock = false;
        userTypedCityManually = false;
        showToast('Locking onto your accurate GPS location...', 'info');
    } else if (cityInput && !cityInput.value.trim()) {
        cityInput.placeholder = 'Detecting accurate location...';
    }

    setLocateButtonLoading(true);

    let pendingCoarseFix = null;
    let receivedAnyFix = false;

    const commitFix = (pos, isManualTrigger) => {
        const lat = pos.coords.latitude;
        const lng = pos.coords.longitude;
        const acc = Number.isFinite(pos.coords.accuracy) ? pos.coords.accuracy : null;

        hasRealGpsLock = true;
        if (acc !== null && acc < bestAccuracyMeters) {
            bestAccuracyMeters = acc;
        }
        applyDetectedLocation(lat, lng, !isManualTrigger, acc);

        // Once building/street-level precision (<= 25m) is reached, stop continuous radio polling
        if (acc !== null && acc <= 25) {
            stopActiveGeoWatch();
            setLocateButtonLoading(false);
        }
    };

    const onGeoSuccess = (position) => {
        if (!position || !position.coords) return;
        receivedAnyFix = true;
        const acc = Number.isFinite(position.coords.accuracy) ? position.coords.accuracy : 100;

        // Sharp street/neighborhood fix (<= 600m): apply immediately and discard any coarse buffer
        if (acc <= 600) {
            if (coarseHoldTimer) {
                clearTimeout(coarseHoldTimer);
                coarseHoldTimer = null;
            }
            pendingCoarseFix = null;

            const movedKm = (userLat !== null && userLng !== null)
                ? computeHaversineKm(userLat, userLng, position.coords.latitude, position.coords.longitude)
                : Infinity;
            const isMuchSharper = acc < bestAccuracyMeters * 0.85;
            const movedMeaningfully = movedKm > 0.025 && acc <= Math.max(120, bestAccuracyMeters);

            if (!hasRealGpsLock || isMuchSharper || movedMeaningfully) {
                commitFix(position, !silent);
            }
            return;
        }

        // Coarse initial network/IP estimate (> 600m): hold briefly (2.5s) in case Wi-Fi/GNSS
        // finishes scanning right behind it, avoiding jumping the pin to a coarse town centroid.
        if (!hasRealGpsLock) {
            if (!pendingCoarseFix || acc < pendingCoarseFix.coords.accuracy) {
                pendingCoarseFix = position;
            }
            if (!coarseHoldTimer) {
                coarseHoldTimer = setTimeout(() => {
                    coarseHoldTimer = null;
                    if (!hasRealGpsLock && pendingCoarseFix) {
                        commitFix(pendingCoarseFix, !silent);
                    }
                }, 2500);
            }
        } else if (acc < bestAccuracyMeters * 0.8) {
            commitFix(position, !silent);
        }
    };

    const onGeoError = (error) => {
        if (receivedAnyFix || hasRealGpsLock) return;

        // Only try non-high-accuracy fallback if high-accuracy hardware timed out (3) or was unavailable (2)
        if (error && (error.code === 2 || error.code === 3)) {
            stopActiveGeoWatch();
            navigator.geolocation.getCurrentPosition(
                (fallbackPos) => {
                    commitFix(fallbackPos, !silent);
                    setLocateButtonLoading(false);
                },
                (finalErr) => handleFinalGeoFailure(finalErr),
                { enableHighAccuracy: false, timeout: 10000, maximumAge: 0 }
            );
            return;
        }
        handleFinalGeoFailure(error);
    };

    const handleFinalGeoFailure = (error) => {
        stopActiveGeoWatch();
        setLocateButtonLoading(false);
        if (cityInput && !cityInput.value.trim()) {
            cityInput.placeholder = 'Location / Area';
        }
        const msg = String((error && error.message) || '');
        console.warn('Geolocation unavailable:', msg);
        if (msg.toLowerCase().includes('permissions policy')) {
            document.getElementById('gps-iframe-notice')?.classList.remove('d-none');
            if (!silent) {
                showToast('Preview iframe restricts exact GPS — click Open Full Tab on the map or click your street directly.', 'error');
            }
        } else if (!silent) {
            if (error && error.code === 1) {
                showToast('Location permission denied. Allow browser location access or click your street on the map.', 'error');
            } else {
                showToast('Unable to lock GPS position. Please try again or click your street on the map.', 'error');
            }
        }
    };

    const highAccOpts = { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 };

    if (typeof navigator.geolocation.watchPosition === 'function') {
        activeGeoWatchId = navigator.geolocation.watchPosition(onGeoSuccess, onGeoError, highAccOpts);
        geoWatchStopTimer = setTimeout(() => {
            stopActiveGeoWatch();
            setLocateButtonLoading(false);
        }, 25000);
    } else {
        navigator.geolocation.getCurrentPosition(onGeoSuccess, onGeoError, highAccOpts);
    }
}

// --- 5. IN-MAP DIRECTIONS & ROUTE PATH ENGINE ---
function fetchRoadRoute(fromLat, fromLng, toLat, toLng) {
    const coordPair = `${fromLng},${fromLat};${toLng},${toLat}`;
    const osrmUrls = [
        `https://router.project-osrm.org/route/v1/driving/${coordPair}?overview=full&geometries=geojson`,
        `https://routing.openstreetmap.de/routed-car/route/v1/driving/${coordPair}?overview=full&geometries=geojson`
    ];

    const tryEndpoint = (idx) => {
        if (idx >= osrmUrls.length) {
            const straightKm = computeHaversineKm(fromLat, fromLng, toLat, toLng);
            const meters = straightKm * 1000;
            const seconds = (straightKm / 24) * 3600;
            return Promise.resolve({
                coords: [[fromLat, fromLng], [toLat, toLng]],
                distanceMeters: meters,
                durationSeconds: seconds,
                isFallback: true
            });
        }

        return fetch(osrmUrls[idx])
            .then(res => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then(data => {
                const route = data && data.routes && data.routes[0];
                const rawCoords = route && route.geometry && route.geometry.coordinates;
                if (!Array.isArray(rawCoords) || rawCoords.length < 2) {
                    throw new Error('Empty route geometry');
                }
                const latLngs = rawCoords.map(pt => [pt[1], pt[0]]);
                return {
                    coords: latLngs,
                    distanceMeters: Number(route.distance || 0),
                    durationSeconds: Number(route.duration || 0),
                    isFallback: false
                };
            })
            .catch(() => tryEndpoint(idx + 1));
    };

    return tryEndpoint(0);
}

function clearMapRoute() {
    activeRouteTarget = null;
    if (routeLayer && typeof routeLayer.clearLayers === 'function') {
        routeLayer.clearLayers();
    }
    const banner = document.getElementById('route-info-banner');
    if (banner) banner.classList.add('d-none');
}

function renderRouteOnMap(originLat, originLng, destLat, destLng, shopName, routeData, silentToast = false) {
    if (!searchMap || !routeLayer) return;

    routeLayer.clearLayers();

    const pathCoords = routeData.coords;
    const distText = formatDistanceMeters(routeData.distanceMeters);
    const durText = formatDurationSeconds(routeData.durationSeconds);

    if (typeof L.polyline === 'function') {
        L.polyline(pathCoords, {
            color: '#ffffff',
            weight: 9,
            opacity: 0.92,
            lineCap: 'round',
            lineJoin: 'round'
        }).addTo(routeLayer);

        L.polyline(pathCoords, {
            color: '#0369a1',
            weight: 5,
            opacity: 0.96,
            dashArray: routeData.isFallback ? '8, 8' : null,
            lineCap: 'round',
            lineJoin: 'round'
        }).addTo(routeLayer);

        const firstRoadPt = pathCoords[0];
        const lastRoadPt = pathCoords[pathCoords.length - 1];
        L.polyline([[originLat, originLng], firstRoadPt], {
            color: '#dc2626',
            weight: 3,
            dashArray: '4, 6',
            opacity: 0.8
        }).addTo(routeLayer);
        L.polyline([lastRoadPt, [destLat, destLng]], {
            color: '#0f766e',
            weight: 3,
            dashArray: '4, 6',
            opacity: 0.8
        }).addTo(routeLayer);
    }

    const midPt = pathCoords[Math.floor(pathCoords.length / 2)] || [(originLat + destLat) / 2, (originLng + destLng) / 2];
    const midIcon = L.divIcon({
        className: 'route-midpoint-wrapper',
        html: `<div class="route-midpoint-badge"><i class="bi bi-signpost-split-fill"></i><span>${escapeHtml(distText)} · ${escapeHtml(durText)}</span></div>`,
        iconSize: [0, 0],
        iconAnchor: [0, 0]
    });
    L.marker(midPt, { icon: midIcon, interactive: false, zIndexOffset: 1000 }).addTo(routeLayer);

    const banner = document.getElementById('route-info-banner');
    const titleEl = document.getElementById('route-dest-title');
    const distEl = document.getElementById('route-distance-text');
    const durEl = document.getElementById('route-duration-text');
    const extLink = document.getElementById('route-external-link');

    if (titleEl) titleEl.textContent = `Directions to ${shopName || 'Pharmacy'}`;
    if (distEl) distEl.textContent = distText;
    if (durEl) durEl.textContent = routeData.isFallback ? `${durText} (direct)` : `${durText} drive`;
    if (extLink) {
        extLink.href = `https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(originLat + ',' + originLng)}&destination=${encodeURIComponent(destLat + ',' + destLng)}`;
    }
    if (banner) banner.classList.remove('d-none');

    const boundsPts = [[originLat, originLng], [destLat, destLng], ...pathCoords];
    searchMap.fitBounds(boundsPts, { padding: [55, 55], maxZoom: 16 });

    const mapEl = document.getElementById('map');
    if (mapEl && typeof mapEl.scrollIntoView === 'function' && window.innerWidth < 992) {
        mapEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    if (!silentToast) {
        showToast(`Route to ${shopName || 'pharmacy'}: ${distText} (${durText})`);
    }
}

function showDirectionsOnMap(destLat, destLng, shopName = 'Pharmacy', silentToast = false) {
    const targetLat = parseFloat(destLat);
    const targetLng = parseFloat(destLng);
    if (Number.isNaN(targetLat) || Number.isNaN(targetLng) || !searchMap) {
        showToast('Pharmacy map coordinates are unavailable', 'error');
        return;
    }

    activeRouteTarget = { lat: targetLat, lng: targetLng, shopName };

    const executeFromOrigin = (origLat, origLng) => {
        if (!userMarker) {
            placeOrUpdateUserMarker(origLat, origLng, userLocationLabel || '', null, false, false);
        }
        fetchRoadRoute(origLat, origLng, targetLat, targetLng).then(routeData => {
            renderRouteOnMap(origLat, origLng, targetLat, targetLng, shopName, routeData, silentToast);
        });
    };

    if (userLat !== null && userLng !== null) {
        executeFromOrigin(userLat, userLng);
        return;
    }

    if (!silentToast) showToast('Locating you to calculate route...', 'info');

    requestBrowserPosition(
        (pos) => {
            applyDetectedLocation(pos.coords.latitude, pos.coords.longitude, false, pos.coords.accuracy);
            executeFromOrigin(pos.coords.latitude, pos.coords.longitude);
        },
        () => {
            const typedCity = document.getElementById('city-input')?.value.trim() || '';
            if (typedCity) {
                forwardGeocodeAddress(typedCity).then(coords => {
                    if (coords) {
                        placeOrUpdateUserMarker(coords.lat, coords.lng, typedCity, null, false, false);
                        executeFromOrigin(coords.lat, coords.lng);
                    } else {
                        const center = searchMap.getCenter();
                        placeOrUpdateUserMarker(center.lat, center.lng, 'Map Start Point', null, false, false);
                        executeFromOrigin(center.lat, center.lng);
                    }
                });
            } else {
                const center = searchMap.getCenter();
                placeOrUpdateUserMarker(center.lat, center.lng, 'Map Start Point (drag red pin to adjust)', null, false, false);
                executeFromOrigin(center.lat, center.lng);
            }
        }
    );
}

// --- 6. SKELETON LOADER ---
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

// --- 7. SEARCH PAGE & API ENGINE ---
function quickSearch(term) {
    const queryInput = document.getElementById('query-input');
    const cityInput = document.getElementById('city-input');
    if (!queryInput) return;
    queryInput.value = term;
    executeSearch(term, cityInput ? cityInput.value.trim() : '');
}

function initSearchPage() {
    const mapElement = document.getElementById('map');
    const searchForm = document.getElementById('search-form');

    if (!mapElement || !searchForm) return;

    const defaultLat = 25.5941;
    const defaultLng = 85.1376;

    searchMap = L.map('map').setView([defaultLat, defaultLng], 12);
    attachResilientTileLayer(searchMap);

    routeLayer = L.layerGroup().addTo(searchMap);
    osmLayer = L.layerGroup().addTo(searchMap);
    markersLayer = L.layerGroup().addTo(searchMap);
    userLayer = L.layerGroup().addTo(searchMap);

    // Ensure Leaflet recalculates container dimensions after initial CSS fade animation and resizes
    setTimeout(() => {
        if (searchMap && typeof searchMap.invalidateSize === 'function') searchMap.invalidateSize(false);
    }, 150);
    setTimeout(() => {
        if (searchMap && typeof searchMap.invalidateSize === 'function') searchMap.invalidateSize(false);
    }, 600);
    window.addEventListener('resize', () => {
        if (searchMap && typeof searchMap.invalidateSize === 'function') searchMap.invalidateSize(false);
    });

    // Allow 1-click manual street pinpointing on the map if browser GPS is blocked or not yet locked
    if (typeof searchMap.on === 'function') {
        searchMap.on('click', (ev) => {
            if (hasRealGpsLock || !ev || !ev.latlng) return;
            stopActiveGeoWatch();
            hasRealGpsLock = true;
            bestAccuracyMeters = 10;
            userTypedCityManually = false;
            document.getElementById('gps-iframe-notice')?.classList.add('d-none');
            applyDetectedLocation(ev.latlng.lat, ev.latlng.lng, true, null);
            showToast('Exact pin set on map!');
        });
    }

    const cityInput = document.getElementById('city-input');
    const suggestionsBox = document.getElementById('location-suggestions');

    const hideSuggestions = () => {
        if (suggestionsBox) suggestionsBox.classList.add('d-none');
    };

    const selectPlaceSuggestion = (item) => {
        if (!item) return;
        hideSuggestions();
        stopActiveGeoWatch();
        hasRealGpsLock = true;
        bestAccuracyMeters = 20;
        userTypedCityManually = false;
        document.getElementById('gps-iframe-notice')?.classList.add('d-none');

        const commitCoords = (lat, lng, label) => {
            userLocationLabel = label;
            updateLocationSearchBox(label, true);
            placeOrUpdateUserMarker(lat, lng, label, null, true, true, 16);
            if (activeRouteTarget) {
                showDirectionsOnMap(activeRouteTarget.lat, activeRouteTarget.lng, activeRouteTarget.shopName, true);
            } else if (lastSearchQuery) {
                executeSearch(lastSearchQuery, label, true, false);
            }
        };

        if (item.lat !== null && item.lng !== null && !Number.isNaN(Number(item.lat)) && !Number.isNaN(Number(item.lng))) {
            commitCoords(Number(item.lat), Number(item.lng), item.label);
        } else {
            forwardGeocodeAddress(item.searchQuery || item.label).then(coords => {
                if (coords) {
                    commitCoords(coords.lat, coords.lng, item.label);
                }
            });
        }
    };

    const renderSuggestions = (items) => {
        if (!suggestionsBox) return;
        if (!Array.isArray(items) || items.length === 0) {
            hideSuggestions();
            return;
        }
        suggestionsBox.innerHTML = '';
        items.forEach(item => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'location-autocomplete-item';
            btn.innerHTML = `
                <i class="bi bi-geo-alt-fill text-danger flex-shrink-0"></i>
                <div class="overflow-hidden">
                    <div class="fw-semibold text-truncate">${escapeHtml(item.label)}</div>
                    ${item.subtitle ? `<div class="text-muted text-truncate" style="font-size: 0.72rem;">${escapeHtml(item.subtitle)}</div>` : ''}
                </div>
            `;
            btn.addEventListener('mousedown', (e) => {
                e.preventDefault();
                selectPlaceSuggestion(item);
            });
            suggestionsBox.appendChild(btn);
        });
        suggestionsBox.classList.remove('d-none');
    };

    if (cityInput) {
        cityInput.addEventListener('input', (ev) => {
            const val = cityInput.value.trim();
            if (ev && ev.isTrusted && document.activeElement === cityInput) {
                userTypedCityManually = val.length > 0;
            }
            if (autocompleteDebounceTimer) clearTimeout(autocompleteDebounceTimer);
            if (val.length < 2) {
                hideSuggestions();
                return;
            }
            autocompleteDebounceTimer = setTimeout(() => {
                fetchPlaceSuggestions(val).then(items => {
                    if (document.activeElement === cityInput || (ev && !ev.isTrusted)) {
                        renderSuggestions(items);
                    }
                });
            }, 240);
        });
        cityInput.addEventListener('keydown', (ev) => {
            if (ev.key === 'Escape') hideSuggestions();
        });
        cityInput.addEventListener('blur', () => {
            setTimeout(hideSuggestions, 180);
        });
        cityInput.addEventListener('change', (ev) => {
            const val = cityInput.value.trim();
            if (val && ev && ev.isTrusted && userTypedCityManually) {
                forwardGeocodeAddress(val).then(coords => {
                    if (coords) {
                        stopActiveGeoWatch();
                        hasRealGpsLock = true;
                        bestAccuracyMeters = 25;
                        const resolvedLabel = coords.label || val;
                        if (coords.label) updateLocationSearchBox(resolvedLabel, true);
                        document.getElementById('gps-iframe-notice')?.classList.add('d-none');
                        placeOrUpdateUserMarker(coords.lat, coords.lng, resolvedLabel, null, true, true, 15);
                    }
                });
            }
        });
    }

    // Show verified pharmacies on map initially before any medicine query is submitted
    fetch('/api/shops')
        .then(r => (r.ok ? r.json() : []))
        .then(shops => {
            if (Array.isArray(shops)) {
                verifiedShopCoords = shops
                    .map(s => ({ lat: parseFloat(s.lat), lng: parseFloat(s.lng) }))
                    .filter(s => !Number.isNaN(s.lat) && !Number.isNaN(s.lng));
            }
            discoverNearbyOsmPharmacies(
                userLat !== null ? userLat : defaultLat,
                userLng !== null ? userLng : defaultLng
            );
            if (lastSearchQuery || !Array.isArray(shops)) return;
            shops.forEach(shop => {
                const lat = parseFloat(shop.lat);
                const lng = parseFloat(shop.lng);
                if (Number.isNaN(lat) || Number.isNaN(lng)) return;
                const marker = L.marker([lat, lng], { icon: createPulsingIcon() });

                const popupEl = document.createElement('div');
                popupEl.className = 'p-1 text-dark';
                popupEl.innerHTML = `
                    <h6 class="fw-bold text-primary mb-1">${escapeHtml(shop.name)}</h6>
                    <p class="mb-1 small text-muted"><i class="bi bi-geo-alt text-danger me-1"></i>${escapeHtml(shop.city || 'Verified Pharmacy')}</p>
                    <div class="mb-2"><span class="badge bg-success-subtle text-success border border-success">${Number(shop.medicine_count || 0)} medicines listed</span></div>
                    <button type="button" class="btn btn-sm btn-outline-primary w-100 rounded-pill py-1 shop-directions-btn">
                        <i class="bi bi-sign-turn-right-fill me-1"></i> Directions
                    </button>
                `;
                const dirBtn = popupEl.querySelector('.shop-directions-btn');
                if (dirBtn) {
                    dirBtn.addEventListener('click', () => {
                        showDirectionsOnMap(lat, lng, shop.name);
                    });
                }

                marker.bindPopup(popupEl);
                markersLayer.addLayer(marker);
            });
        })
        .catch(() => {});

    // Automatically lock onto exact hardware / Wi-Fi GPS location on page load
    detectUserLocation(true);
    if (navigator.permissions && typeof navigator.permissions.query === 'function') {
        navigator.permissions.query({ name: 'geolocation' })
            .then(permStatus => {
                permStatus.onchange = () => {
                    if (permStatus.state === 'granted' && !hasRealGpsLock) {
                        detectUserLocation(true);
                    }
                };
            })
            .catch(() => {});
    }

    // Search form handler
    searchForm.addEventListener('submit', function (e) {
        e.preventDefault();
        const query = document.getElementById('query-input').value.trim();
        const city = document.getElementById('city-input').value.trim();

        if (!query) {
            showToast('Please enter a medicine or salt name', 'error');
            return;
        }

        if (city && userLat === null && userLng === null) {
            forwardGeocodeAddress(city).then(coords => {
                if (coords) {
                    placeOrUpdateUserMarker(coords.lat, coords.lng, city, null, false, false);
                }
                executeSearch(query, city);
            });
            return;
        }

        executeSearch(query, city);
    });

    // Optional sort, in-stock, & open-now filter controls
    const sortSelect = document.getElementById('sort-select');
    const inStockCheckbox = document.getElementById('in-stock-filter');
    const openNowCheckbox = document.getElementById('open-now-filter');
    const refreshIfSearched = () => {
        const query = document.getElementById('query-input')?.value.trim() || lastSearchQuery;
        const city = document.getElementById('city-input')?.value.trim() || '';
        if (query) executeSearch(query, city, true);
    };
    if (sortSelect) sortSelect.addEventListener('change', refreshIfSearched);
    if (inStockCheckbox) inStockCheckbox.addEventListener('change', refreshIfSearched);
    if (openNowCheckbox) openNowCheckbox.addEventListener('change', refreshIfSearched);

    // Live Medicine & Salt Autocomplete on #query-input
    initMedicineAutocomplete();

    // Hold, Clinical Reference, My Holds, & Multi-Med Rx Matcher modal setup
    const holdModalEl = document.getElementById('holdModal');
    if (holdModalEl && window.bootstrap) {
        holdModalInstance = new window.bootstrap.Modal(holdModalEl);
    }
    const medInfoModalEl = document.getElementById('medInfoModal');
    if (medInfoModalEl && window.bootstrap) {
        medInfoModalInstance = new window.bootstrap.Modal(medInfoModalEl);
    }
    const holdForm = document.getElementById('hold-form');
    if (holdForm) {
        holdForm.addEventListener('submit', submitHoldForm);
    }
    initMyHoldsAndRxModals();

    // Load live Open-Meteo local weather & storage advisory for the map area
    updateLocalEnvironmentBar(defaultLat, defaultLng, 'Patna');
}

function renderCatalogAndLocalOsmCards(resultsContainer, query, catalogItems, hasVerifiedResults) {
    if (!resultsContainer) return;
    const topCat = Array.isArray(catalogItems) && catalogItems.length > 0 ? catalogItems[0] : null;

    if (topCat) {
        const catCard = document.createElement('div');
        catCard.className = 'catalog-ref-card mb-3';
        const rxBadge = topCat.rx_required
            ? `<span class="rx-pill-badge ms-1"><i class="bi bi-prescription2"></i>Rx Required</span>`
            : '';
        const genBadge = topCat.is_generic
            ? `<span class="badge bg-success text-white rounded-pill ms-1">PMBJP Jan Aushadhi</span>`
            : `<span class="badge bg-primary-subtle text-primary border border-primary-subtle rounded-pill ms-1">Official Indian Catalog</span>`;
        catCard.innerHTML = `
            <div class="d-flex justify-content-between align-items-start gap-2">
                <div>
                    <div class="d-flex flex-wrap align-items-center gap-1 mb-1">
                        <span class="fw-bold text-primary">${escapeHtml(topCat.med_name)}</span>
                        ${genBadge}
                        ${rxBadge}
                    </div>
                    <div class="small text-dark"><i class="bi bi-capsule me-1 text-primary"></i><strong>Salt:</strong> ${escapeHtml(topCat.salt_composition || 'Standard Composition')}</div>
                    <small class="text-muted d-block">${escapeHtml(topCat.manufacturer || topCat.source || 'Indian Pharma')}${topCat.pack_size ? ` · ${escapeHtml(topCat.pack_size)}` : ''}</small>
                </div>
                <div class="text-end flex-shrink-0">
                    <div class="fw-bold text-success fs-5">₹${Number(topCat.mrp || 0).toFixed(2)}</div>
                    <small class="text-muted d-block" style="font-size: 0.7rem;">Ref. MRP</small>
                    <div class="d-inline-flex gap-1 mt-1">
                        <button type="button" class="btn btn-sm btn-outline-primary rounded-pill py-0 px-2 cat-rx-btn" title="Add to Rx Matcher">+ Rx</button>
                        <button type="button" class="btn btn-sm btn-outline-info rounded-pill py-0 px-2 cat-info-btn" title="Clinical Info"><i class="bi bi-info-circle-fill"></i></button>
                    </div>
                </div>
            </div>
        `;
        catCard.querySelector('.cat-rx-btn')?.addEventListener('click', () => addMedicineToRxList(topCat.med_name));
        catCard.querySelector('.cat-info-btn')?.addEventListener('click', () => {
            openMedicineInfoModal(topCat.med_name, topCat.salt_composition || '', topCat.pack_size || '');
        });
        resultsContainer.prepend(catCard);
    }

    if (!Array.isArray(osmPharmaciesCache) || osmPharmaciesCache.length === 0) return;

    const refLat = userLat !== null ? userLat : (searchMap ? searchMap.getCenter().lat : 25.5941);
    const refLng = userLng !== null ? userLng : (searchMap ? searchMap.getCenter().lng : 85.1376);
    const sortedLocal = [...osmPharmaciesCache]
        .map(s => ({ ...s, distKm: computeHaversineKm(refLat, refLng, s.lat, s.lng) }))
        .sort((a, b) => a.distKm - b.distKm)
        .slice(0, hasVerifiedResults ? 4 : 6);

    if (sortedLocal.length === 0) return;

    const sectionWrap = document.createElement('div');
    sectionWrap.className = 'mt-3 pt-3 border-top';
    const refMedTitle = topCat ? topCat.med_name : query;
    const refPriceNote = topCat && Number(topCat.mrp) > 0 ? ` · Ref. MRP ₹${Number(topCat.mrp).toFixed(2)}` : '';
    sectionWrap.innerHTML = `
        <div class="d-flex flex-wrap justify-content-between align-items-center gap-1 mb-2">
            <div class="fw-bold small text-dark">
                <i class="bi bi-geo-alt-fill text-warning me-1"></i>Nearby Local Pharmacies on Map
            </div>
            <span class="osm-unverified-badge">OpenStreetMap · Confirm Stock</span>
        </div>
        <small class="text-muted d-block mb-2" style="font-size: 0.76rem;">
            Real neighborhood medical stores near you that may carry <strong>${escapeHtml(refMedTitle)}</strong>${escapeHtml(refPriceNote)}. Live counter stock is not yet linked — get directions, inquire, or claim if this is your shop.
        </small>
        <div class="d-flex flex-column gap-2 local-osm-cards-list"></div>
    `;

    const listHost = sectionWrap.querySelector('.local-osm-cards-list');
    sortedLocal.forEach(localShop => {
        const claimUrl = buildClaimStoreUrl(localShop);
        const waUrl = localShop.phone ? buildWhatsAppInquiryUrl(localShop.phone, localShop.name, refMedTitle) : '';
        const itemEl = document.createElement('div');
        itemEl.className = 'local-osm-shop-card d-flex flex-wrap justify-content-between align-items-center gap-2';
        itemEl.innerHTML = `
            <div class="overflow-hidden">
                <div class="fw-semibold text-dark small text-truncate"><i class="bi bi-shop-window text-warning me-1"></i>${escapeHtml(localShop.name)}</div>
                <small class="text-muted d-block text-truncate">${escapeHtml(localShop.area)} · <strong>${localShop.distKm.toFixed(2)} km</strong>${localShop.opening_hours ? ` · ${escapeHtml(localShop.opening_hours)}` : ''}</small>
            </div>
            <div class="d-flex align-items-center gap-1 flex-shrink-0">
                ${waUrl ? `<a href="${escapeHtml(waUrl)}" target="_blank" rel="noopener" class="btn btn-sm whatsapp-inquiry-btn rounded-pill py-1 px-2" title="Ask on WhatsApp"><i class="bi bi-whatsapp"></i></a>` : ''}
                ${localShop.phone ? `<a href="tel:${escapeHtml(localShop.phone)}" class="btn btn-sm btn-outline-success rounded-pill py-1 px-2" title="Call Store"><i class="bi bi-telephone"></i></a>` : ''}
                <button type="button" class="btn btn-sm btn-outline-secondary rounded-pill py-1 px-2 local-osm-dir-btn" title="Show road route on map">
                    <i class="bi bi-sign-turn-right-fill me-1"></i>${localShop.distKm.toFixed(1)} km
                </button>
                <a href="${escapeHtml(claimUrl)}" class="btn btn-sm btn-outline-warning text-dark rounded-pill py-1 px-2 fw-semibold" title="Claim store &amp; list live stock">Claim</a>
            </div>
        `;
        itemEl.querySelector('.local-osm-dir-btn')?.addEventListener('click', () => {
            showDirectionsOnMap(localShop.lat, localShop.lng, localShop.name);
        });
        listHost?.appendChild(itemEl);
    });

    resultsContainer.appendChild(sectionWrap);
}

function executeSearch(query, city, silentToast = false, keepUserView = false) {
    lastSearchQuery = query;
    hideMedicineAutocomplete();
    if (!keepUserView) {
        clearMapRoute();
    }
    showSearchSkeleton();

    const resultsContainer = document.getElementById('results-container');
    const resultsCount = document.getElementById('results-count');
    const sortBy = document.getElementById('sort-select')?.value || 'distance';
    const inStockOnly = document.getElementById('in-stock-filter')?.checked || false;
    const openNowOnly = document.getElementById('open-now-filter')?.checked || false;

    let url = `/api/search?query=${encodeURIComponent(query)}`;
    if (city) url += `&city=${encodeURIComponent(city)}`;
    if (userLat !== null && userLng !== null) url += `&lat=${userLat}&lng=${userLng}`;
    if (sortBy) url += `&sort=${encodeURIComponent(sortBy)}`;
    if (inStockOnly) url += `&in_stock=1`;
    if (openNowOnly) url += `&open_now=1`;

    const catalogPromise = fetch(`/api/catalog?q=${encodeURIComponent(query)}&limit=3`)
        .then(r => (r.ok ? r.json() : []))
        .catch(() => []);

    Promise.all([
        fetch(url).then(response => {
            if (!response.ok) {
                throw new Error(`Server returned HTTP ${response.status}`);
            }
            return response.json();
        }),
        catalogPromise
    ])
        .then(([data, catalogItems]) => {
            markersLayer.clearLayers();
            resultsContainer.innerHTML = '';

            const results = Array.isArray(data) ? data : (data.results || []);

            if (results.length === 0) {
                if (resultsCount) resultsCount.textContent = '0 verified';
                hideSubstitutesPanel();
                resultsContainer.innerHTML = `
                    <div class="text-center py-4 text-muted">
                        <i class="bi bi-shop fs-2 text-secondary opacity-50"></i>
                        <p class="mt-2 mb-1 fw-semibold">No verified partner stores currently list live stock for "${escapeHtml(query)}".</p>
                        <small>See official catalog MRP, generic substitutes, and real nearby local pharmacies on the map below.</small>
                        <div id="rxnorm-suggestions-box" class="mt-3"></div>
                    </div>
                `;
                renderCatalogAndLocalOsmCards(resultsContainer, query, catalogItems, false);
                const fallbackSaltHits = Array.isArray(catalogItems) && catalogItems.length > 0
                    ? [{ med_name: catalogItems[0].med_name, salt_composition: catalogItems[0].salt_composition, price: catalogItems[0].mrp }]
                    : [];
                fetchAndRenderSubstitutes(query, fallbackSaltHits);
                fetchRxNormSpellingSuggestions(query).then(suggestions => {
                    const box = document.getElementById('rxnorm-suggestions-box');
                    if (!box || !Array.isArray(suggestions) || suggestions.length === 0) return;
                    const chipsHtml = suggestions
                        .map(s => `<button type="button" class="quick-chip rxnorm-suggest-chip" data-term="${escapeHtml(s)}">${escapeHtml(s)}</button>`)
                        .join(' ');
                    box.innerHTML = `<div class="small text-primary fw-semibold mb-2"><i class="bi bi-stars me-1"></i>RxNorm Did you mean:</div><div class="d-flex flex-wrap justify-content-center gap-1">${chipsHtml}</div>`;
                    box.querySelectorAll('.rxnorm-suggest-chip').forEach(btn => {
                        btn.addEventListener('click', () => {
                            const term = btn.getAttribute('data-term') || '';
                            if (term) quickSearch(term);
                        });
                    });
                });
                if (!silentToast && (!Array.isArray(catalogItems) || catalogItems.length === 0)) {
                    showToast('No matching partner inventory found — showing nearby local shops', 'info');
                }
                return;
            }

            if (resultsCount) resultsCount.textContent = `${results.length} verified`;
            fetchAndRenderSubstitutes(query, results);

            const bounds = [];
            if (userLat !== null && userLng !== null) {
                bounds.push([userLat, userLng]);
            }

            results.forEach((item, index) => {
                const medId = item.med_id ?? item.id;
                const medName = item.med_name || item.name || 'Medicine';
                const price = parseFloat(item.price || 0).toFixed(2);
                const totalStock = Number(item.stock_quantity ?? item.stock ?? 0);
                const activeHolds = Number(item.active_holds ?? 0);
                const availStock = Number(item.available_quantity ?? Math.max(0, totalStock - activeHolds));
                const shopName = item.shop_name || item.pharmacy_name || 'Pharmacy';
                const salt = item.salt_composition || item.salt || 'Generic Formula';
                const dosage = item.dosage || 'Standard Dosage';
                const cityLabel = item.city || 'Location mapped';
                const rxRequired = Boolean(item.rx_required);
                const is24x7 = Boolean(item.is_24x7);
                const isOpenNow = Boolean(item.is_open_now);
                const hasCoords = item.lat !== null && item.lat !== undefined && item.lng !== null && item.lng !== undefined && item.lat !== '' && item.lng !== '';
                const distanceBadge = (item.distance_km !== null && item.distance_km !== undefined)
                    ? `<span class="badge bg-primary-subtle text-primary border border-primary-subtle me-1"><i class="bi bi-signpost-2 me-1"></i>${escapeHtml(item.distance_km)} km</span>`
                    : '';
                const stockBadge = availStock > 0
                    ? `<span class="badge bg-success-subtle text-success border border-success me-1"><i class="bi bi-check2-circle me-1"></i>${availStock} available</span>`
                    : `<span class="badge bg-danger-subtle text-danger border border-danger me-1"><i class="bi bi-x-circle me-1"></i>Out of stock</span>`;
                const holdInfoBadge = activeHolds > 0
                    ? `<span class="badge bg-warning-subtle text-warning border border-warning me-1"><i class="bi bi-hourglass-split me-1"></i>${activeHolds} held</span>`
                    : '';
                const rxBadge = rxRequired
                    ? `<span class="rx-pill-badge" title="Schedule H Prescription Required at Pickup"><i class="bi bi-prescription2"></i>Rx Required</span>`
                    : '';
                const openBadge = is24x7
                    ? `<span class="open-24x7-badge"><i class="bi bi-lightning-charge-fill"></i>24&times;7 Open</span>`
                    : (isOpenNow ? `<span class="open-24x7-badge"><i class="bi bi-clock-fill"></i>Open Now</span>` : '');
                const phoneLine = item.shop_phone
                    ? `<small class="text-muted d-block"><i class="bi bi-telephone me-1 text-success"></i><a href="tel:${escapeHtml(item.shop_phone)}" class="text-decoration-none text-reset">${escapeHtml(item.shop_phone)}</a></small>`
                    : '';
                const hoursLine = item.opening_hours
                    ? `<small class="text-muted d-block"><i class="bi bi-clock me-1 text-info"></i>${escapeHtml(item.opening_hours)}</small>`
                    : '';
                const waUrl = buildWhatsAppInquiryUrl(item.shop_phone, shopName, medName);
                const whatsappBtn = waUrl
                    ? `<a href="${escapeHtml(waUrl)}" target="_blank" rel="noopener" class="btn btn-sm whatsapp-inquiry-btn rounded-pill px-2 card-wa-btn" title="1-Tap WhatsApp Stock &amp; Prescription Inquiry" aria-label="WhatsApp ${escapeHtml(shopName)}"><i class="bi bi-whatsapp"></i></a>`
                    : '';
                const directionsBtn = hasCoords
                    ? `<button type="button" class="btn btn-sm btn-outline-secondary rounded-pill px-2 card-directions-btn" title="Show route &amp; distance on map"><i class="bi bi-sign-turn-right-fill me-1"></i>Directions</button>`
                    : '';

                const card = document.createElement('div');
                card.className = 'list-group-item list-group-item-action border-0 mb-3 glass-card p-3 rounded-3';
                card.style.animationDelay = `${index * 0.08}s`;

                card.innerHTML = `
                    <div class="d-flex justify-content-between align-items-start mb-2 gap-2">
                        <div>
                            <div class="d-flex flex-wrap align-items-center gap-1">
                                <h6 class="fw-bold text-primary mb-0">${escapeHtml(medName)}</h6>
                                ${rxBadge}
                            </div>
                            <small class="text-muted">${escapeHtml(dosage)}</small>
                        </div>
                        <span class="fs-5 fw-bold text-success flex-shrink-0">₹${escapeHtml(price)}</span>
                    </div>
                    <div class="mb-2 d-flex flex-wrap align-items-center gap-1">
                        <span class="badge bg-light text-dark border"><i class="bi bi-capsule me-1"></i>${escapeHtml(salt)}</span>
                        ${stockBadge}
                        ${holdInfoBadge}
                        ${distanceBadge}
                        ${openBadge}
                    </div>
                    <div class="d-flex flex-wrap justify-content-between align-items-center mt-3 pt-2 border-top gap-2">
                        <div>
                            <div class="fw-semibold text-dark small"><i class="bi bi-shop me-1 text-primary"></i>${escapeHtml(shopName)}</div>
                            <small class="text-muted d-block"><i class="bi bi-geo-alt me-1 text-danger"></i>${escapeHtml(cityLabel)}</small>
                            ${phoneLine}
                            ${hoursLine}
                        </div>
                        <div class="d-flex flex-wrap align-items-center gap-1 flex-shrink-0">
                            <button type="button" class="btn btn-sm btn-outline-primary rounded-pill px-2 card-rx-add-btn" title="Add to Multi-Medicine Prescription Matcher">+ Rx</button>
                            <button type="button" class="btn btn-sm btn-outline-info rounded-pill px-2 card-info-btn" title="Clinical uses, salt &amp; safety info (RxNorm + openFDA)" aria-label="Clinical reference for ${escapeHtml(medName)}"><i class="bi bi-info-circle-fill"></i></button>
                            ${whatsappBtn}
                            ${directionsBtn}
                            <button type="button" class="btn btn-sm ${availStock > 0 ? 'btn-outline-primary' : 'btn-outline-secondary'} rounded-pill px-3 fw-semibold hold-trigger-btn" ${availStock <= 0 ? 'disabled' : ''}>
                                <i class="bi bi-handbag me-1"></i> ${availStock > 0 ? 'Hold' : 'Unavailable'}
                            </button>
                        </div>
                    </div>
                `;

                const cardRxBtn = card.querySelector('.card-rx-add-btn');
                if (cardRxBtn) {
                    cardRxBtn.addEventListener('click', (ev) => {
                        ev.stopPropagation();
                        addMedicineToRxList(medName);
                    });
                }

                const cardWaBtn = card.querySelector('.card-wa-btn');
                if (cardWaBtn) {
                    cardWaBtn.addEventListener('click', (ev) => ev.stopPropagation());
                }

                const cardInfoBtn = card.querySelector('.card-info-btn');
                if (cardInfoBtn) {
                    cardInfoBtn.addEventListener('click', (ev) => {
                        ev.stopPropagation();
                        openMedicineInfoModal(medName, salt, dosage);
                    });
                }

                const cardDirBtn = card.querySelector('.card-directions-btn');
                if (cardDirBtn && hasCoords) {
                    cardDirBtn.addEventListener('click', (ev) => {
                        ev.stopPropagation();
                        showDirectionsOnMap(item.lat, item.lng, shopName);
                    });
                }

                const holdBtn = card.querySelector('.hold-trigger-btn');
                if (holdBtn && availStock > 0) {
                    holdBtn.addEventListener('click', (ev) => {
                        ev.stopPropagation();
                        requestHold(medId, medName, availStock, shopName, price, rxRequired);
                    });
                }

                resultsContainer.appendChild(card);

                if (hasCoords) {
                    const lat = parseFloat(item.lat);
                    const lng = parseFloat(item.lng);
                    if (!Number.isNaN(lat) && !Number.isNaN(lng)) {
                        bounds.push([lat, lng]);

                        const marker = L.marker([lat, lng], { icon: createPulsingIcon() });

                        const popupEl = document.createElement('div');
                        popupEl.className = 'p-1 text-dark';
                        popupEl.innerHTML = `
                            <h6 class="fw-bold text-primary mb-1">${escapeHtml(shopName)}</h6>
                            <p class="mb-1 small"><strong>${escapeHtml(medName)}</strong> — ₹${escapeHtml(price)}</p>
                            <p class="mb-2 text-muted small">Available: ${availStock}${item.distance_km !== null && item.distance_km !== undefined ? ` · ${escapeHtml(item.distance_km)} km` : ''}</p>
                            <div class="d-flex gap-1">
                                <button type="button" class="btn btn-sm btn-primary flex-grow-1 rounded-pill py-1 text-white popup-hold-btn" ${availStock <= 0 ? 'disabled' : ''}>
                                    ${availStock > 0 ? 'Request Hold' : 'Out of Stock'}
                                </button>
                                <button type="button" class="btn btn-sm btn-outline-primary rounded-pill py-1 px-2 popup-directions-btn" title="Show route &amp; distance on map">
                                    <i class="bi bi-sign-turn-right-fill"></i>
                                </button>
                            </div>
                        `;
                        const popupHoldBtn = popupEl.querySelector('.popup-hold-btn');
                        if (popupHoldBtn && availStock > 0) {
                            popupHoldBtn.addEventListener('click', () => {
                                requestHold(medId, medName, availStock, shopName, price, rxRequired);
                            });
                        }
                        const popupDirBtn = popupEl.querySelector('.popup-directions-btn');
                        if (popupDirBtn) {
                            popupDirBtn.addEventListener('click', () => {
                                showDirectionsOnMap(lat, lng, shopName);
                            });
                        }

                        marker.bindPopup(popupEl);
                        markersLayer.addLayer(marker);

                        card.addEventListener('mouseenter', () => {
                            if (!activeRouteTarget) {
                                searchMap.panTo([lat, lng]);
                            }
                            marker.openPopup();
                        });
                    }
                }
            });

            renderCatalogAndLocalOsmCards(resultsContainer, query, catalogItems, true);

            if (bounds.length > 0 && !keepUserView && !activeRouteTarget) {
                searchMap.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
            }

            if (!silentToast) showToast(`Found ${results.length} verified listing${results.length === 1 ? '' : 's'}`);
        })
        .catch(err => {
            console.error('Search fetch error:', err);
            resultsContainer.innerHTML = `
                <div class="alert alert-danger glass-card">
                    <i class="bi bi-exclamation-triangle-fill me-2"></i> Failed to process search. Verify backend route <code>/api/search</code> is active.
                </div>
            `;
            showToast('Search service unavailable', 'error');
        });
}

// --- 8. HOLD RESERVATION ENGINE ---
function getCsrfHeaders(extra = {}) {
    const headers = Object.assign({ 'Content-Type': 'application/json' }, extra);
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) {
        headers['X-CSRF-Token'] = meta.content;
    }
    return headers;
}

function requestHold(medId, medName, availableQty = 1, shopName = 'Selected Pharmacy', price = null, rxRequired = false) {
    if (medId === undefined || medId === null) {
        showToast('Unable to identify medicine listing', 'error');
        return;
    }

    const modalEl = document.getElementById('holdModal');
    if (modalEl && holdModalInstance) {
        document.getElementById('hold-med-id').value = medId;
        document.getElementById('hold-med-title').textContent = medName || 'Medicine';
        document.getElementById('hold-shop-title').textContent = shopName || 'Verified Pharmacy';
        document.getElementById('hold-med-price').textContent = price !== null ? `₹${parseFloat(price).toFixed(2)}` : '';
        document.getElementById('hold-med-avail').textContent = `${availableQty} available`;

        const rxAlert = document.getElementById('hold-rx-alert');
        if (rxAlert) rxAlert.classList.toggle('d-none', !rxRequired);

        // Reset modal back to input state
        document.getElementById('hold-form-fields')?.classList.remove('d-none');
        document.getElementById('hold-confirmation-box')?.classList.add('d-none');
        document.getElementById('hold-submit-btn')?.classList.remove('d-none');
        document.getElementById('hold-view-all-btn')?.classList.add('d-none');

        const savedPhone = localStorage.getItem('medfinder_customer_phone') || '';
        const savedName = localStorage.getItem('medfinder_customer_name') || '';
        const phoneInput = document.getElementById('hold-phone');
        const nameInput = document.getElementById('hold-customer-name');
        if (phoneInput && savedPhone && !phoneInput.value) phoneInput.value = savedPhone;
        if (nameInput && savedName && !nameInput.value) nameInput.value = savedName;

        const qtyInput = document.getElementById('hold-quantity');
        if (qtyInput) {
            qtyInput.max = Math.min(20, Math.max(1, Number(availableQty) || 1));
            qtyInput.value = 1;
        }
        holdModalInstance.show();
        setTimeout(() => document.getElementById('hold-phone')?.focus(), 200);
        return;
    }

    const customerPhone = prompt(`Enter your phone number to place a 2-Hour Hold on ${medName}:`);
    if (!customerPhone || !customerPhone.trim()) {
        if (customerPhone !== null) {
            showToast('Phone number is required to place a hold', 'error');
        }
        return;
    }
    sendReservationRequest({ med_id: medId, phone: customerPhone.trim(), quantity: 1 });
}

function submitHoldForm(e) {
    e.preventDefault();
    const medId = document.getElementById('hold-med-id')?.value;
    const phone = document.getElementById('hold-phone')?.value.trim() || '';
    const customerName = document.getElementById('hold-customer-name')?.value.trim() || '';
    const quantity = parseInt(document.getElementById('hold-quantity')?.value || '1', 10) || 1;

    if (!phone) {
        showToast('Phone number is required to place a hold', 'error');
        return;
    }

    try {
        localStorage.setItem('medfinder_customer_phone', phone);
        if (customerName) localStorage.setItem('medfinder_customer_name', customerName);
    } catch (_) {}

    sendReservationRequest(
        { med_id: Number(medId), phone, customer_name: customerName, quantity },
        (body) => {
            const fieldsEl = document.getElementById('hold-form-fields');
            const confirmBox = document.getElementById('hold-confirmation-box');
            const codeEl = document.getElementById('hold-confirmed-code');
            const msgEl = document.getElementById('hold-confirmed-msg');
            const warnBox = document.getElementById('hold-safety-warnings');

            if (fieldsEl && confirmBox && codeEl) {
                fieldsEl.classList.add('d-none');
                confirmBox.classList.remove('d-none');
                codeEl.textContent = body.pickup_code || `MF-${1000 + ((body.reservation_id || 1) * 7919) % 9000}`;
                if (msgEl) msgEl.textContent = body.message || 'Reserved for 2 hours! Show this code at the counter.';
                document.getElementById('hold-submit-btn')?.classList.add('d-none');
                document.getElementById('hold-view-all-btn')?.classList.remove('d-none');

                if (warnBox) {
                    const html = renderSafetyWarningsHtml(body.safety_warnings || []);
                    warnBox.innerHTML = html;
                    warnBox.classList.toggle('d-none', !html);
                }
            } else if (holdModalInstance) {
                holdModalInstance.hide();
            }
            refreshMyHoldsBadgeCount(phone);
        }
    );
}

function sendReservationRequest(payload, onSuccess) {
    const submitBtn = document.getElementById('hold-submit-btn');
    if (submitBtn) submitBtn.disabled = true;

    fetch('/api/reserve', {
        method: 'POST',
        headers: getCsrfHeaders(),
        body: JSON.stringify(payload)
    })
        .then(res => res.json().then(body => ({ ok: res.ok, body })))
        .then(({ ok, body }) => {
            if (ok && (body.success || body.status === 'success')) {
                showToast(body.message || 'Stock successfully held for 2 hours!');
                if (typeof onSuccess === 'function') onSuccess(body);
                if (lastSearchQuery) {
                    const cityVal = document.getElementById('city-input')?.value.trim() || '';
                    executeSearch(lastSearchQuery, cityVal, true, true);
                }
            } else {
                showToast(body.error || 'Unable to place hold', 'error');
            }
        })
        .catch(() => {
            showToast('Error connecting to reservation system', 'error');
        })
        .finally(() => {
            if (submitBtn) submitBtn.disabled = false;
        });
}

// --- 9. CLINICAL DRUG INTELLIGENCE (NIH RXNORM + OPENFDA PUBLIC APIS) ---
const BRAND_TO_GENERIC_MAP = {
    'dolo 650': 'Acetaminophen',
    'dolo': 'Acetaminophen',
    'calpol': 'Acetaminophen',
    'crocin': 'Acetaminophen',
    'pcm': 'Acetaminophen',
    'paracetamol': 'Acetaminophen',
    'glycomed': 'Metformin',
    'glucophage': 'Metformin',
    'azithral': 'Azithromycin',
    'azee': 'Azithromycin',
    'ecosprin': 'Aspirin',
    'disprin': 'Aspirin',
    'pantocid': 'Pantoprazole',
    'pan 40': 'Pantoprazole',
    'augmentin': 'Amoxicillin',
    'amoxyclav': 'Amoxicillin',
    'okacet': 'Cetirizine',
    'cetzine': 'Cetirizine',
    'brufen': 'Ibuprofen',
    'combiflam': 'Ibuprofen'
};

const CLINICAL_FALLBACK_DB = {
    acetaminophen: {
        salt: 'Paracetamol / Acetaminophen',
        rxcui: '161',
        indications: 'Temporary relief of fever (antipyretic) and mild-to-moderate pain including headache, toothache, body ache, and cold/flu discomfort.',
        dosage: 'Adults typically take 500 mg – 650 mg every 4–6 hours as needed. Do not exceed 4,000 mg (4 g) in 24 hours unless directed by a physician.',
        warnings: 'Avoid combining with other paracetamol-containing cold remedies or alcohol due to liver toxicity risk. Store below 25°C in a dry place.'
    },
    aspirin: {
        salt: 'Acetylsalicylic Acid (Aspirin)',
        rxcui: '1191',
        indications: 'Analgesic, anti-inflammatory, antipyretic, and low-dose antiplatelet therapy for cardiovascular protection under medical supervision.',
        dosage: 'Take with food or water as prescribed by your physician (low-dose 75–150 mg once daily for cardiac care, or higher strengths for acute pain).',
        warnings: 'Not recommended in children/teenagers with viral fever (Reye syndrome risk), active peptic ulcers, or bleeding disorders. Store in an airtight dry pack.'
    },
    metformin: {
        salt: 'Metformin Hydrochloride',
        rxcui: '6809',
        indications: 'First-line oral antihyperglycemic agent used alongside diet and exercise to improve blood glucose control in Type 2 Diabetes Mellitus.',
        dosage: 'Commonly taken with meals (500 mg – 1,000 mg) to minimize gastrointestinal discomfort, strictly per prescription schedule.',
        warnings: 'Monitor kidney function periodically; seek medical attention for unusual muscle pain or weakness. Store away from moisture and heat.'
    },
    azithromycin: {
        salt: 'Azithromycin Dihydrate',
        rxcui: '18631',
        indications: 'Macrolide antibiotic indicated for susceptible bacterial respiratory, ENT, skin, and soft-tissue infections.',
        dosage: 'Prescription antibiotic — complete the full prescribed course (commonly once daily for 3–5 days) even if symptoms improve early.',
        warnings: 'Do not use for viral colds/flu without medical advice. Inform your doctor if you have liver conditions or heart rhythm disorders.'
    },
    cetirizine: {
        salt: 'Cetirizine Hydrochloride',
        rxcui: '20610',
        indications: 'Second-generation antihistamine for allergic rhinitis, sneezing, watery eyes, itching, and urticaria (hives).',
        dosage: 'Typically 10 mg once daily for adults (or as directed by a physician).',
        warnings: 'May cause mild drowsiness in some individuals — exercise caution when driving. Store in a cool, dry place.'
    },
    pantoprazole: {
        salt: 'Pantoprazole Sodium',
        rxcui: '40790',
        indications: 'Proton pump inhibitor (PPI) for acid reflux (GERD), gastritis, and peptic ulcer protection.',
        dosage: 'Usually taken 30 minutes before breakfast (commonly 40 mg once daily) per physician guidance.',
        warnings: 'Swallow delayed-release tablets whole; do not crush or chew. Consult a doctor if symptoms persist beyond 2 weeks.'
    },
    ibuprofen: {
        salt: 'Ibuprofen',
        rxcui: '5640',
        indications: 'NSAID for inflammatory pain, dental pain, dysmenorrhea, sprains, arthritis, and fever.',
        dosage: 'Take after food/milk at the lowest effective dose for the shortest duration advised by your doctor.',
        warnings: 'Avoid in active stomach ulcers, severe kidney disease, or late pregnancy. Store below 25°C.'
    }
};

function normalizeLookupTerm(medName, salt) {
    const rawSalt = String(salt || '').trim().toLowerCase();
    const rawMed = String(medName || '').trim().toLowerCase();

    for (const [key, mapped] of Object.entries(BRAND_TO_GENERIC_MAP)) {
        if (rawMed.includes(key) || rawSalt.includes(key)) {
            return mapped;
        }
    }
    const cleanSalt = String(salt || '')
        .split(/[+/,(]/)[0]
        .replace(/\b(\d+\s*(mg|mcg|g|ml)|ip|bp|usp|generic formula|standard)\b/gi, '')
        .trim();
    if (cleanSalt && cleanSalt.length >= 3) return cleanSalt;

    return String(medName || '')
        .replace(/\b(\d+\s*(mg|mcg|g|ml)?|forte|plus|ds|sr|xr|tab|tablet|cap|syrup)\b/gi, '')
        .trim();
}

function truncateClinicalText(arrOrStr, maxChars = 340) {
    const raw = Array.isArray(arrOrStr) ? arrOrStr.join(' ') : String(arrOrStr || '');
    const cleaned = raw.replace(/\s+/g, ' ').trim();
    if (!cleaned) return '';
    if (cleaned.length <= maxChars) return cleaned;
    return cleaned.slice(0, maxChars).replace(/\s+\S*$/, '') + '…';
}

function fetchRxNormData(term) {
    const q = String(term || '').trim();
    if (!q) return Promise.resolve(null);
    return fetch(`https://rxnav.nlm.nih.gov/REST/approximateTerm.json?term=${encodeURIComponent(q)}&maxEntries=1`)
        .then(r => (r.ok ? r.json() : null))
        .then(data => {
            const cand = data && data.approximateGroup && Array.isArray(data.approximateGroup.candidate)
                ? data.approximateGroup.candidate[0]
                : null;
            if (!cand || !cand.rxcui) return null;
            const rxcui = String(cand.rxcui);
            return fetch(`https://rxnav.nlm.nih.gov/REST/rxcui/${encodeURIComponent(rxcui)}/related.json?tty=IN`)
                .then(r => (r.ok ? r.json() : null))
                .then(rel => {
                    const groups = rel && rel.relatedGroup && Array.isArray(rel.relatedGroup.conceptGroup)
                        ? rel.relatedGroup.conceptGroup
                        : [];
                    let ingredient = '';
                    groups.forEach(g => {
                        if (!ingredient && Array.isArray(g.conceptProperties) && g.conceptProperties[0]) {
                            ingredient = g.conceptProperties[0].name || '';
                        }
                    });
                    return { rxcui, ingredient: ingredient || cand.name || q };
                })
                .catch(() => ({ rxcui, ingredient: cand.name || q }));
        })
        .catch(() => null);
}

function fetchOpenFdaLabel(term) {
    const q = String(term || '').trim();
    if (!q) return Promise.resolve(null);
    const searchExpr = `openfda.generic_name:"${q}"+openfda.brand_name:"${q}"`;
    return fetch(`https://api.fda.gov/drug/label.json?search=${encodeURIComponent(searchExpr)}&limit=1`)
        .then(r => (r.ok ? r.json() : null))
        .then(data => {
            const hit = data && Array.isArray(data.results) ? data.results[0] : null;
            if (!hit) return null;
            return {
                indications: truncateClinicalText(hit.indications_and_usage || hit.purpose),
                dosage: truncateClinicalText(hit.dosage_and_administration),
                warnings: truncateClinicalText(hit.warnings || hit.boxed_warning || hit.storage_and_handling)
            };
        })
        .catch(() => null);
}

function openMedicineInfoModal(medName, salt, dosage = '') {
    const modalEl = document.getElementById('medInfoModal');
    if (!modalEl) return;
    if (!medInfoModalInstance && window.bootstrap) {
        medInfoModalInstance = new window.bootstrap.Modal(modalEl);
    }

    const titleEl = document.getElementById('clinical-med-title');
    const saltEl = document.getElementById('clinical-med-salt');
    const rxcuiBadge = document.getElementById('clinical-rxcui-badge');
    const loadingEl = document.getElementById('clinical-loading');
    const bodyEl = document.getElementById('clinical-body');
    const indEl = document.getElementById('clinical-indications');
    const dosEl = document.getElementById('clinical-dosage');
    const warnEl = document.getElementById('clinical-warnings');

    const lookupTerm = normalizeLookupTerm(medName, salt);
    const fallbackKey = lookupTerm.toLowerCase();
    const fallbackEntry = CLINICAL_FALLBACK_DB[fallbackKey] || null;

    if (titleEl) titleEl.textContent = medName || 'Medicine Reference';
    if (saltEl) {
        saltEl.textContent = [salt || (fallbackEntry && fallbackEntry.salt) || lookupTerm, dosage].filter(Boolean).join(' · ');
    }
    if (rxcuiBadge) {
        rxcuiBadge.innerHTML = `<i class="bi bi-capsule me-1"></i>${fallbackEntry && fallbackEntry.rxcui ? `RxNorm #${escapeHtml(fallbackEntry.rxcui)} · ${escapeHtml(lookupTerm)}` : `Salt: ${escapeHtml(lookupTerm || salt || medName)}`}`;
    }

    if (loadingEl) loadingEl.classList.remove('d-none');
    if (bodyEl) bodyEl.classList.add('d-none');
    if (medInfoModalInstance) medInfoModalInstance.show();

    Promise.all([
        fetchRxNormData(lookupTerm),
        fetchOpenFdaLabel(lookupTerm)
    ]).then(([rxData, fdaData]) => {
        if (rxData && rxData.rxcui && rxcuiBadge) {
            rxcuiBadge.innerHTML = `<i class="bi bi-capsule me-1"></i>RxNorm #${escapeHtml(rxData.rxcui)} · ${escapeHtml(rxData.ingredient || lookupTerm)}`;
        }
        const finalFallback = fallbackEntry || CLINICAL_FALLBACK_DB[String(rxData && rxData.ingredient || '').toLowerCase()] || null;

        if (indEl) {
            indEl.textContent = (fdaData && fdaData.indications)
                || (finalFallback && finalFallback.indications)
                || `Formulation containing ${salt || lookupTerm}. Consult your physician or pharmacist for condition-specific indications.`;
        }
        if (dosEl) {
            dosEl.textContent = (fdaData && fdaData.dosage)
                || (finalFallback && finalFallback.dosage)
                || `Dosage form: ${dosage || 'As labeled'}. Follow the exact strength and schedule prescribed by a registered medical practitioner.`;
        }
        if (warnEl) {
            warnEl.textContent = (fdaData && fdaData.warnings)
                || (finalFallback && finalFallback.warnings)
                || 'Keep out of reach of children. Store in a cool, dry place below 25°C away from direct sunlight and check expiry before use.';
        }

        if (loadingEl) loadingEl.classList.add('d-none');
        if (bodyEl) bodyEl.classList.remove('d-none');
    });
}

function fetchRxNormSpellingSuggestions(rawQuery) {
    const q = String(rawQuery || '').trim();
    if (q.length < 3) return Promise.resolve([]);

    const localKnown = ['Paracetamol', 'Dolo 650', 'Aspirin', 'Glycomed', 'Azithral', 'Metformin', 'Azithromycin', 'PCM'];
    const lower = q.toLowerCase();
    const localHits = localKnown.filter(item => {
        const il = item.toLowerCase();
        return il !== lower && (il.startsWith(lower.slice(0, 3)) || lower.startsWith(il.slice(0, 3)));
    });

    return fetch(`https://rxnav.nlm.nih.gov/REST/spellingsuggestions.json?name=${encodeURIComponent(q)}`)
        .then(r => (r.ok ? r.json() : null))
        .then(data => {
            const list = data && data.suggestionGroup && data.suggestionGroup.suggestionList && data.suggestionGroup.suggestionList.suggestion;
            const remote = Array.isArray(list) ? list.slice(0, 4) : [];
            const merged = [];
            const seen = new Set([lower]);
            [...localHits, ...remote].forEach(s => {
                const clean = String(s || '').trim();
                if (clean && !seen.has(clean.toLowerCase())) {
                    seen.add(clean.toLowerCase());
                    merged.push(clean);
                }
            });
            return merged.slice(0, 4);
        })
        .catch(() => localHits.slice(0, 4));
}

function autoFillSaltFromRxNorm() {
    const medInput = document.getElementById('add-med-name-input');
    const saltInput = document.getElementById('add-salt-input');
    if (!medInput || !saltInput) return;

    const medName = medInput.value.trim();
    if (!medName) {
        showToast('Enter a Medicine Brand Name first to detect its active salt', 'error');
        medInput.focus();
        return;
    }

    fetch(`/api/catalog?q=${encodeURIComponent(medName)}&limit=1`)
        .then(r => (r.ok ? r.json() : []))
        .then(catRows => {
            if (Array.isArray(catRows) && catRows.length > 0 && catRows[0].salt_composition) {
                const hit = catRows[0];
                saltInput.value = hit.salt_composition;
                const dosageEl = document.getElementById('add-dosage-input');
                const priceEl = document.getElementById('add-price-input');
                const rxEl = document.getElementById('add-rx-required');
                if (dosageEl && !dosageEl.value && hit.pack_size) dosageEl.value = hit.pack_size;
                if (priceEl && !priceEl.value && Number(hit.mrp) > 0) priceEl.value = Number(hit.mrp).toFixed(2);
                if (rxEl && hit.rx_required) rxEl.checked = true;
                showToast(`Matched official catalog: ${hit.salt_composition}`);
                return;
            }

            const mapped = BRAND_TO_GENERIC_MAP[medName.toLowerCase()];
            if (mapped) {
                const displaySalt = mapped === 'Acetaminophen' ? 'Paracetamol (Acetaminophen)' : mapped;
                saltInput.value = displaySalt;
                showToast(`Active salt set: ${displaySalt}`);
                return;
            }

            const lookup = normalizeLookupTerm(medName, '');
            showToast('Querying NIH RxNorm for active ingredient...', 'info');
            fetchRxNormData(lookup).then(rxData => {
                if (rxData && rxData.ingredient) {
                    const formatted = rxData.ingredient.charAt(0).toUpperCase() + rxData.ingredient.slice(1);
                    saltInput.value = formatted;
                    showToast(`RxNorm detected salt: ${formatted}`);
                } else {
                    showToast('Could not auto-detect salt — please enter the composition manually', 'error');
                }
            });
        })
        .catch(() => {});
}

// --- 10. AUTOCOMPLETE, GENERIC SUBSTITUTES, MY HOLDS, RX MATCHER, SAFETY & PWA ---
let medAutocompleteTimer = null;
let myHoldsModalInstance = null;
let rxListModalInstance = null;
let myHoldsCountdownInterval = null;
let rxSelectedItems = [];

function buildWhatsAppInquiryUrl(rawPhone, shopName, medName) {
    const digits = String(rawPhone || '').replace(/\D/g, '');
    if (digits.length < 10) return '';
    const intl = digits.length === 10 ? `91${digits}` : digits;
    const msg = `Hello ${shopName || 'Pharmacy'}, checking via MedFinder: is ${medName || 'this medicine'} currently available for counter pickup?`;
    return `https://wa.me/${intl}?text=${encodeURIComponent(msg)}`;
}

function renderSafetyWarningsHtml(warnings) {
    if (!Array.isArray(warnings) || warnings.length === 0) return '';
    const itemsHtml = warnings
        .map(w => `
            <div class="d-flex align-items-start gap-2 mb-1">
                <i class="bi bi-exclamation-octagon-fill text-danger mt-1 flex-shrink-0"></i>
                <div>
                    <span class="badge bg-danger text-white rounded-pill me-1">${escapeHtml(w.severity || 'Alert')}</span>
                    <span>${escapeHtml(w.message || '')}</span>
                </div>
            </div>
        `)
        .join('');
    return `
        <div class="safety-warning-box">
            <div class="fw-bold mb-1"><i class="bi bi-shield-exclamation me-1"></i>Clinical Duplicate-Salt / Interaction Check</div>
            ${itemsHtml}
        </div>
    `;
}

function hideMedicineAutocomplete() {
    const menu = document.getElementById('query-suggestions');
    if (menu) {
        menu.classList.add('d-none');
        menu.innerHTML = '';
    }
}

function initMedicineAutocomplete() {
    const input = document.getElementById('query-input');
    const menu = document.getElementById('query-suggestions');
    if (!input || !menu) return;

    input.addEventListener('input', () => {
        const q = input.value.trim();
        if (medAutocompleteTimer) clearTimeout(medAutocompleteTimer);
        if (q.length < 1) {
            hideMedicineAutocomplete();
            return;
        }
        medAutocompleteTimer = setTimeout(() => {
            fetch(`/api/autocomplete?q=${encodeURIComponent(q)}`)
                .then(r => (r.ok ? r.json() : []))
                .then(items => {
                    if (!Array.isArray(items) || items.length === 0 || document.activeElement !== input) {
                        hideMedicineAutocomplete();
                        return;
                    }
                    menu.innerHTML = '';
                    items.forEach(sug => {
                        const btn = document.createElement('button');
                        btn.type = 'button';
                        btn.className = 'location-suggestion-item d-flex justify-content-between align-items-center w-100 text-start';
                        const rxTag = sug.rx_required ? `<span class="rx-pill-badge ms-1">Rx</span>` : '';
                        const inStockCount = Number(sug.in_stock_stores || 0);
                        const priceTag = sug.min_price > 0
                            ? (inStockCount > 0 ? `From ₹${Number(sug.min_price).toFixed(2)}` : `MRP ₹${Number(sug.min_price).toFixed(2)}`)
                            : '';
                        const storeSubtext = inStockCount > 0
                            ? `${inStockCount} verified store${inStockCount === 1 ? '' : 's'}`
                            : (sug.is_generic ? 'Jan Aushadhi Catalog' : 'Official Catalog');
                        btn.innerHTML = `
                            <div class="overflow-hidden me-2">
                                <div class="fw-bold text-primary small text-truncate">${escapeHtml(sug.med_name)}${rxTag}</div>
                                <small class="text-muted text-truncate d-block">${escapeHtml(sug.salt_composition || sug.manufacturer || 'Official Medicine Catalog')}</small>
                            </div>
                            <div class="text-end flex-shrink-0">
                                <div class="small fw-bold text-success">${escapeHtml(priceTag)}</div>
                                <small class="${inStockCount > 0 ? 'text-success fw-semibold' : 'text-muted'}">${escapeHtml(storeSubtext)}</small>
                            </div>
                        `;
                        btn.addEventListener('click', () => {
                            input.value = sug.med_name;
                            hideMedicineAutocomplete();
                            const cityVal = document.getElementById('city-input')?.value.trim() || '';
                            executeSearch(sug.med_name, cityVal);
                        });
                        menu.appendChild(btn);
                    });
                    menu.classList.remove('d-none');
                })
                .catch(() => hideMedicineAutocomplete());
        }, 160);
    });

    document.addEventListener('click', (ev) => {
        if (!menu.contains(ev.target) && ev.target !== input) {
            hideMedicineAutocomplete();
        }
    });
}

function hideSubstitutesPanel() {
    const panel = document.getElementById('substitutes-panel');
    const list = document.getElementById('substitutes-list');
    if (panel) panel.classList.add('d-none');
    if (list) list.innerHTML = '';
}

function fetchAndRenderSubstitutes(query, primaryResults) {
    const panel = document.getElementById('substitutes-panel');
    const listEl = document.getElementById('substitutes-list');
    const saltBadge = document.getElementById('substitutes-salt-badge');
    if (!panel || !listEl) return;

    const firstHit = Array.isArray(primaryResults) && primaryResults.length > 0 ? primaryResults[0] : null;
    const salt = firstHit ? (firstHit.salt_composition || '') : '';
    const refPrice = firstHit ? parseFloat(firstHit.price || 0) : '';
    const excludeMed = firstHit ? (firstHit.med_name || query) : query;

    let url = `/api/substitutes?query=${encodeURIComponent(query)}&exclude_med_name=${encodeURIComponent(excludeMed)}`;
    if (salt) url += `&salt=${encodeURIComponent(salt)}`;
    if (refPrice) url += `&ref_price=${encodeURIComponent(refPrice)}`;
    if (userLat !== null && userLng !== null) url += `&lat=${userLat}&lng=${userLng}`;

    fetch(url)
        .then(r => (r.ok ? r.json() : null))
        .then(data => {
            const subs = data && Array.isArray(data.substitutes) ? data.substitutes : [];
            if (subs.length === 0) {
                hideSubstitutesPanel();
                return;
            }
            if (saltBadge && data.salt) {
                saltBadge.textContent = data.salt;
            }
            listEl.innerHTML = '';
            subs.slice(0, 5).forEach(sub => {
                const isCatalogRef = Boolean(sub.is_catalog_reference) || sub.med_id === null || sub.med_id === undefined;
                const savingsBadge = sub.savings_pct > 0
                    ? `<span class="savings-pill"><i class="bi bi-arrow-down-short"></i>Save ${sub.savings_pct}% (₹${Number(sub.savings_amount).toFixed(2)})</span>`
                    : `<span class="badge bg-success-subtle text-success border border-success rounded-pill">Same Active Salt</span>`;
                const rxBadge = sub.rx_required ? `<span class="rx-pill-badge ms-1">Rx</span>` : '';
                const distText = (sub.distance_km !== null && sub.distance_km !== undefined) ? ` · ${sub.distance_km} km` : '';
                const subLine = isCatalogRef
                    ? `<i class="bi bi-award text-success me-1"></i>${escapeHtml(sub.shop_name || 'PMBJP Jan Aushadhi / Catalog')} · ${escapeHtml(sub.dosage || 'Reference MRP')}`
                    : `<i class="bi bi-shop me-1"></i>${escapeHtml(sub.shop_name)} (${escapeHtml(sub.city || 'Verified')})${escapeHtml(distText)} · ${sub.available_quantity} in stock`;
                const actionBtns = isCatalogRef
                    ? `<button type="button" class="btn btn-sm btn-outline-success rounded-pill py-0 px-2 fw-semibold sub-check-btn">Check Nearby</button>`
                    : `
                        ${sub.lat && sub.lng ? `<button type="button" class="btn btn-sm btn-outline-secondary rounded-pill py-0 px-2 sub-dir-btn" title="Directions"><i class="bi bi-sign-turn-right-fill"></i></button>` : ''}
                        <button type="button" class="btn btn-sm btn-outline-primary rounded-pill py-0 px-2 fw-semibold sub-hold-btn">Hold</button>
                    `;
                const card = document.createElement('div');
                card.className = 'substitute-card d-flex justify-content-between align-items-center gap-2';
                card.innerHTML = `
                    <div class="overflow-hidden">
                        <div class="d-flex flex-wrap align-items-center gap-1">
                            <span class="fw-bold text-primary small">${escapeHtml(sub.med_name)}</span>
                            ${rxBadge}
                            ${savingsBadge}
                        </div>
                        <small class="text-muted d-block text-truncate">${subLine}</small>
                    </div>
                    <div class="text-end flex-shrink-0">
                        <div class="fw-bold text-success">₹${Number(sub.price || 0).toFixed(2)}</div>
                        <div class="d-inline-flex gap-1 mt-1">${actionBtns}</div>
                    </div>
                `;
                card.querySelector('.sub-dir-btn')?.addEventListener('click', () => {
                    showDirectionsOnMap(sub.lat, sub.lng, sub.shop_name);
                });
                card.querySelector('.sub-hold-btn')?.addEventListener('click', () => {
                    requestHold(sub.med_id, sub.med_name, sub.available_quantity, sub.shop_name, sub.price, Boolean(sub.rx_required));
                });
                card.querySelector('.sub-check-btn')?.addEventListener('click', () => {
                    quickSearch(sub.med_name);
                });
                listEl.appendChild(card);
            });
            panel.classList.remove('d-none');
        })
        .catch(() => hideSubstitutesPanel());
}

function formatCountdownSeconds(secs) {
    const s = Math.max(0, Number(secs) || 0);
    if (s <= 0) return 'Expired';
    const hrs = Math.floor(s / 3600);
    const mins = Math.floor((s % 3600) / 60);
    const rem = s % 60;
    if (hrs > 0) return `${hrs}h ${String(mins).padStart(2, '0')}m ${String(rem).padStart(2, '0')}s`;
    return `${mins}m ${String(rem).padStart(2, '0')}s`;
}

function startMyHoldsCountdownTicker() {
    if (myHoldsCountdownInterval) clearInterval(myHoldsCountdownInterval);
    myHoldsCountdownInterval = setInterval(() => {
        document.querySelectorAll('[data-hold-seconds]').forEach(el => {
            const next = Math.max(0, (parseInt(el.getAttribute('data-hold-seconds') || '0', 10) || 0) - 1);
            el.setAttribute('data-hold-seconds', String(next));
            const label = el.querySelector('.countdown-text');
            if (label) label.textContent = formatCountdownSeconds(next);
        });
    }, 1000);
}

function refreshMyHoldsBadgeCount(phoneOverride = '') {
    const badge = document.getElementById('my-holds-count-badge');
    if (!badge) return;
    const phone = phoneOverride || localStorage.getItem('medfinder_customer_phone') || '';
    if (phone.replace(/\D/g, '').length < 7) {
        badge.classList.add('d-none');
        return;
    }
    fetch(`/api/my-holds?phone=${encodeURIComponent(phone)}`)
        .then(r => (r.ok ? r.json() : null))
        .then(data => {
            const count = data && Number(data.active_count || 0);
            if (count > 0) {
                badge.textContent = String(count);
                badge.classList.remove('d-none');
            } else {
                badge.classList.add('d-none');
            }
        })
        .catch(() => {});
}

function openMyHoldsModal() {
    const modalEl = document.getElementById('myHoldsModal');
    if (!modalEl || !window.bootstrap) return;
    if (!myHoldsModalInstance) {
        myHoldsModalInstance = new window.bootstrap.Modal(modalEl);
    }
    const phoneInput = document.getElementById('my-holds-phone-input');
    const savedPhone = localStorage.getItem('medfinder_customer_phone') || '';
    if (phoneInput && savedPhone && !phoneInput.value) {
        phoneInput.value = savedPhone;
    }
    myHoldsModalInstance.show();
    if (phoneInput && phoneInput.value.trim()) {
        loadMyHolds(phoneInput.value.trim());
    }
}

function switchHoldToMyHolds() {
    if (holdModalInstance) holdModalInstance.hide();
    setTimeout(() => openMyHoldsModal(), 220);
}

function loadMyHolds(phone) {
    const container = document.getElementById('my-holds-results');
    const safetyBanner = document.getElementById('my-holds-safety-banner');
    if (!container) return;

    try { localStorage.setItem('medfinder_customer_phone', phone); } catch (_) {}
    container.innerHTML = `<div class="text-center py-4 text-muted small">Loading active holds…</div>`;

    fetch(`/api/my-holds?phone=${encodeURIComponent(phone)}`)
        .then(r => r.json().then(body => ({ ok: r.ok, body })))
        .then(({ ok, body }) => {
            if (!ok || !body.success) {
                container.innerHTML = `<div class="alert alert-warning rounded-3 small mb-0">${escapeHtml(body.error || 'Could not look up holds.')}</div>`;
                return;
            }
            refreshMyHoldsBadgeCount(phone);
            if (safetyBanner) {
                const warnHtml = renderSafetyWarningsHtml(body.safety_warnings || []);
                safetyBanner.innerHTML = warnHtml;
                safetyBanner.classList.toggle('d-none', !warnHtml);
            }

            const holds = body.holds || [];
            if (holds.length === 0) {
                container.innerHTML = `<div class="text-center py-4 text-muted small">No holds found for <strong>${escapeHtml(phone)}</strong>.</div>`;
                return;
            }

            container.innerHTML = '';
            holds.forEach(h => {
                const isPending = h.status === 'Pending';
                const rxBadge = h.rx_required ? `<span class="rx-pill-badge ms-1">Rx Required</span>` : '';
                const waUrl = buildWhatsAppInquiryUrl(h.shop_phone, h.shop_name, `${h.med_name} (Hold Code ${h.pickup_code})`);
                const card = document.createElement('div');
                card.className = 'hold-item-card';
                card.innerHTML = `
                    <div class="d-flex flex-wrap justify-content-between align-items-start gap-2">
                        <div>
                            <div class="d-flex flex-wrap align-items-center gap-2 mb-1">
                                <span class="pickup-code-pill">${escapeHtml(h.pickup_code)}</span>
                                <span class="fw-bold text-primary">${escapeHtml(h.med_name)} &times; ${h.quantity}</span>
                                ${rxBadge}
                            </div>
                            <small class="text-muted d-block"><i class="bi bi-shop me-1"></i>${escapeHtml(h.shop_name)} (${escapeHtml(h.city || 'Verified')}) · Total ₹${Number(h.total_price || 0).toFixed(2)}</small>
                        </div>
                        <div class="text-end">
                            ${isPending
                                ? `<span class="countdown-pill" data-hold-seconds="${h.seconds_remaining}"><i class="bi bi-stopwatch"></i><span class="countdown-text">${formatCountdownSeconds(h.seconds_remaining)}</span></span>`
                                : `<span class="badge bg-secondary rounded-pill">${escapeHtml(h.status)}</span>`}
                        </div>
                    </div>
                    ${isPending ? `
                    <div class="d-flex flex-wrap justify-content-end gap-1 mt-2 pt-2 border-top">
                        ${waUrl ? `<a href="${escapeHtml(waUrl)}" target="_blank" rel="noopener" class="btn btn-sm whatsapp-inquiry-btn rounded-pill px-3"><i class="bi bi-whatsapp me-1"></i>WhatsApp Store</a>` : ''}
                        ${h.lat && h.lng ? `<button type="button" class="btn btn-sm btn-outline-primary rounded-pill px-3 hold-dir-btn"><i class="bi bi-sign-turn-right-fill me-1"></i>Directions</button>` : ''}
                        <button type="button" class="btn btn-sm btn-outline-danger rounded-pill px-3 hold-cancel-btn"><i class="bi bi-x-circle me-1"></i>Cancel Hold</button>
                    </div>` : ''}
                `;
                card.querySelector('.hold-dir-btn')?.addEventListener('click', () => {
                    myHoldsModalInstance?.hide();
                    showDirectionsOnMap(h.lat, h.lng, h.shop_name);
                });
                card.querySelector('.hold-cancel-btn')?.addEventListener('click', () => {
                    cancelMyHold(h.reservation_id, phone);
                });
                container.appendChild(card);
            });

            startMyHoldsCountdownTicker();
        })
        .catch(() => {
            container.innerHTML = `<div class="alert alert-danger rounded-3 small mb-0">Network error loading holds.</div>`;
        });
}

function cancelMyHold(resId, phone) {
    fetch(`/api/my-holds/${encodeURIComponent(resId)}/cancel`, {
        method: 'POST',
        headers: getCsrfHeaders(),
        body: JSON.stringify({ phone })
    })
        .then(r => r.json().then(body => ({ ok: r.ok, body })))
        .then(({ ok, body }) => {
            if (ok && body.success) {
                showToast(body.message || 'Hold cancelled');
                loadMyHolds(phone);
                if (lastSearchQuery) {
                    const cityVal = document.getElementById('city-input')?.value.trim() || '';
                    executeSearch(lastSearchQuery, cityVal, true, true);
                }
            } else {
                showToast(body.error || 'Could not cancel hold', 'error');
            }
        })
        .catch(() => showToast('Network error cancelling hold', 'error'));
}

function updateRxBadgeCount() {
    const badge = document.getElementById('rx-list-count-badge');
    if (!badge) return;
    if (rxSelectedItems.length > 0) {
        badge.textContent = String(rxSelectedItems.length);
        badge.classList.remove('d-none');
    } else {
        badge.classList.add('d-none');
    }
}

function renderRxPills() {
    const wrap = document.getElementById('rx-selected-pills');
    updateRxBadgeCount();
    if (!wrap) return;
    if (rxSelectedItems.length === 0) {
        wrap.innerHTML = `<span class="small text-muted">No medicines added yet. Add 2+ medicines to find your best single-stop pharmacy.</span>`;
        return;
    }
    wrap.innerHTML = '';
    rxSelectedItems.forEach((name, idx) => {
        const pill = document.createElement('span');
        pill.className = 'rx-pill-item';
        pill.innerHTML = `
            <i class="bi bi-capsule"></i>
            <span>${escapeHtml(name)}</span>
            <button type="button" class="btn-close" style="font-size: 0.6rem;" aria-label="Remove ${escapeHtml(name)}"></button>
        `;
        pill.querySelector('button')?.addEventListener('click', () => {
            rxSelectedItems.splice(idx, 1);
            saveRxListState();
            renderRxPills();
            if (rxSelectedItems.length > 0) runPrescriptionMatch();
            else {
                const safetyEl = document.getElementById('rx-safety-panel');
                if (safetyEl) { safetyEl.classList.add('d-none'); safetyEl.innerHTML = ''; }
            }
        });
        wrap.appendChild(pill);
    });
}

function saveRxListState() {
    try { localStorage.setItem('medfinder_rx_list', JSON.stringify(rxSelectedItems)); } catch (_) {}
}

function addMedicineToRxList(rawName) {
    const clean = String(rawName || '').trim();
    if (!clean) return;
    if (!rxSelectedItems.some(x => x.toLowerCase() === clean.toLowerCase())) {
        rxSelectedItems.push(clean);
        saveRxListState();
        showToast(`Added "${clean}" to Rx Matcher (${rxSelectedItems.length} item${rxSelectedItems.length === 1 ? '' : 's'})`);
    }
    renderRxPills();
    const modalEl = document.getElementById('rxListModal');
    if (modalEl && modalEl.classList.contains('show')) {
        runPrescriptionMatch();
    }
}

function openRxListModal() {
    const modalEl = document.getElementById('rxListModal');
    if (!modalEl || !window.bootstrap) return;
    if (!rxListModalInstance) {
        rxListModalInstance = new window.bootstrap.Modal(modalEl);
    }
    renderRxPills();
    rxListModalInstance.show();
    if (rxSelectedItems.length > 0) {
        runPrescriptionMatch();
    }
}

function runPrescriptionMatch() {
    const out = document.getElementById('rx-match-results');
    const safetyPanel = document.getElementById('rx-safety-panel');
    if (!out) return;

    if (rxSelectedItems.length === 0) {
        out.innerHTML = `<div class="text-center py-4 text-muted small">Add at least one medicine above to compare pharmacies.</div>`;
        return;
    }

    out.innerHTML = `<div class="text-center py-4 text-muted small">Ranking verified pharmacies &amp; checking clinical interactions…</div>`;
    fetch('/api/prescription-match', {
        method: 'POST',
        headers: getCsrfHeaders(),
        body: JSON.stringify({
            items: rxSelectedItems,
            lat: userLat,
            lng: userLng
        })
    })
        .then(r => r.json().then(body => ({ ok: r.ok, body })))
        .then(({ ok, body }) => {
            if (!ok || !body.success) {
                out.innerHTML = `<div class="alert alert-warning rounded-3 small mb-0">${escapeHtml(body.error || 'Could not match prescription.')}</div>`;
                return;
            }
            if (safetyPanel) {
                const warnHtml = renderSafetyWarningsHtml(body.safety_warnings || []);
                safetyPanel.innerHTML = warnHtml;
                safetyPanel.classList.toggle('d-none', !warnHtml);
            }

            const shops = body.pharmacies || [];
            if (shops.length === 0) {
                out.innerHTML = `<div class="text-center py-4 text-muted small">No verified pharmacies currently stock these medicines.</div>`;
                return;
            }

            out.innerHTML = '';
            shops.forEach((shop, idx) => {
                const coverageBadge = shop.complete_match
                    ? `<span class="badge bg-success text-white rounded-pill"><i class="bi bi-check2-all me-1"></i>All ${shop.matched_count}/${shop.requested_count} in stock</span>`
                    : `<span class="badge bg-warning text-dark rounded-pill">${shop.matched_count}/${shop.requested_count} in stock</span>`;
                const openTag = shop.is_24x7
                    ? `<span class="open-24x7-badge ms-1">24&times;7</span>`
                    : (shop.is_open_now ? `<span class="open-24x7-badge ms-1">Open</span>` : '');
                const distStr = (shop.distance_km !== null && shop.distance_km !== undefined) ? ` · ${shop.distance_km} km` : '';
                const matchedLines = (shop.matched_items || [])
                    .map(m => `<span class="badge bg-light text-dark border me-1 mb-1">${escapeHtml(m.med_name)} (₹${Number(m.price).toFixed(2)})</span>`)
                    .join('');
                const missingLine = (shop.missing_items && shop.missing_items.length > 0)
                    ? `<div class="small text-danger mt-1">Missing: ${escapeHtml(shop.missing_items.join(', '))}</div>`
                    : '';
                const waUrl = buildWhatsAppInquiryUrl(shop.shop_phone, shop.shop_name, rxSelectedItems.join(', '));

                const card = document.createElement('div');
                card.className = 'rx-shop-rank-card';
                card.innerHTML = `
                    <div class="d-flex flex-wrap justify-content-between align-items-start gap-2 mb-2">
                        <div>
                            <div class="d-flex flex-wrap align-items-center gap-1">
                                <span class="badge bg-primary rounded-pill">#${idx + 1}</span>
                                <span class="fw-bold text-primary">${escapeHtml(shop.shop_name)}</span>
                                ${coverageBadge}
                                ${openTag}
                            </div>
                            <small class="text-muted">${escapeHtml(shop.city || 'Verified')}${escapeHtml(distStr)}${shop.opening_hours ? ` · ${escapeHtml(shop.opening_hours)}` : ''}</small>
                        </div>
                        <div class="text-end">
                            <div class="fw-bold text-success fs-6">₹${Number(shop.total_price || 0).toFixed(2)}</div>
                            <small class="text-muted">Est. Basket</small>
                        </div>
                    </div>
                    <div class="mb-2">${matchedLines}${missingLine}</div>
                    <div class="d-flex justify-content-end gap-1">
                        ${waUrl ? `<a href="${escapeHtml(waUrl)}" target="_blank" rel="noopener" class="btn btn-sm whatsapp-inquiry-btn rounded-pill px-3"><i class="bi bi-whatsapp me-1"></i>WhatsApp Rx</a>` : ''}
                        ${shop.lat && shop.lng ? `<button type="button" class="btn btn-sm btn-primary rounded-pill px-3 rx-dir-btn"><i class="bi bi-sign-turn-right-fill me-1"></i>Route on Map</button>` : ''}
                    </div>
                `;
                card.querySelector('.rx-dir-btn')?.addEventListener('click', () => {
                    rxListModalInstance?.hide();
                    showDirectionsOnMap(shop.lat, shop.lng, shop.shop_name);
                });
                out.appendChild(card);
            });
        })
        .catch(() => {
            out.innerHTML = `<div class="alert alert-danger rounded-3 small mb-0">Failed to run prescription match.</div>`;
        });
}

function initMyHoldsAndRxModals() {
    try {
        const savedRx = JSON.parse(localStorage.getItem('medfinder_rx_list') || '[]');
        if (Array.isArray(savedRx)) rxSelectedItems = savedRx.slice(0, 15);
    } catch (_) {
        rxSelectedItems = [];
    }
    updateRxBadgeCount();
    refreshMyHoldsBadgeCount();

    const lookupForm = document.getElementById('my-holds-lookup-form');
    if (lookupForm) {
        lookupForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const phone = document.getElementById('my-holds-phone-input')?.value.trim() || '';
            if (phone) loadMyHolds(phone);
        });
    }

    const rxForm = document.getElementById('rx-add-item-form');
    if (rxForm) {
        rxForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const inp = document.getElementById('rx-item-input');
            if (inp && inp.value.trim()) {
                inp.value.split(',').forEach(part => {
                    if (part.trim()) addMedicineToRxList(part.trim());
                });
                inp.value = '';
            }
        });
    }
}

function registerPwaServiceWorker() {
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/sw.js').catch(() => {});
        });
    }
}

function initDashboardCatalogAutocomplete() {
    const input = document.getElementById('add-med-name-input');
    const menu = document.getElementById('dashboard-catalog-suggestions');
    if (!input || !menu) return;

    let timer = null;
    const hideMenu = () => {
        menu.classList.add('d-none');
        menu.innerHTML = '';
    };

    input.addEventListener('input', () => {
        const q = input.value.trim();
        if (timer) clearTimeout(timer);
        if (q.length < 2) {
            hideMenu();
            return;
        }
        timer = setTimeout(() => {
            fetch(`/api/catalog?q=${encodeURIComponent(q)}&limit=8`)
                .then(r => (r.ok ? r.json() : []))
                .then(items => {
                    if (!Array.isArray(items) || items.length === 0 || document.activeElement !== input) {
                        hideMenu();
                        return;
                    }
                    menu.innerHTML = '';
                    items.forEach(item => {
                        const btn = document.createElement('button');
                        btn.type = 'button';
                        btn.className = 'location-suggestion-item d-flex justify-content-between align-items-center w-100 text-start';
                        btn.innerHTML = `
                            <div class="overflow-hidden me-2">
                                <div class="fw-bold text-primary small text-truncate">${escapeHtml(item.med_name)}</div>
                                <small class="text-muted text-truncate d-block">${escapeHtml(item.salt_composition || item.manufacturer || '')}</small>
                            </div>
                            <div class="text-end flex-shrink-0">
                                <div class="small fw-bold text-success">₹${Number(item.mrp || 0).toFixed(2)}</div>
                                <small class="text-muted">${item.is_generic ? 'Jan Aushadhi' : 'Branded'}</small>
                            </div>
                        `;
                        btn.addEventListener('mousedown', (e) => {
                            e.preventDefault();
                            input.value = item.med_name;
                            const saltEl = document.getElementById('add-salt-input');
                            const dosageEl = document.getElementById('add-dosage-input');
                            const priceEl = document.getElementById('add-price-input');
                            const rxEl = document.getElementById('add-rx-required');
                            if (saltEl) saltEl.value = item.salt_composition || '';
                            if (dosageEl) dosageEl.value = item.pack_size || '';
                            if (priceEl && Number(item.mrp) > 0) priceEl.value = Number(item.mrp).toFixed(2);
                            if (rxEl) rxEl.checked = Boolean(item.rx_required);
                            hideMenu();
                            showToast(`Auto-filled ${item.med_name} (₹${Number(item.mrp || 0).toFixed(2)})`);
                        });
                        menu.appendChild(btn);
                    });
                    menu.classList.remove('d-none');
                })
                .catch(() => hideMenu());
        }, 160);
    });

    document.addEventListener('click', (ev) => {
        if (!menu.contains(ev.target) && ev.target !== input) hideMenu();
    });
}

// Global Initialization
let mediFinderBooted = false;
function bootMediFinder() {
    if (mediFinderBooted) return;
    mediFinderBooted = true;
    initTheme();
    initSearchPage();
    initDashboardCatalogAutocomplete();
    registerPwaServiceWorker();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootMediFinder);
} else {
    bootMediFinder();
}
