const PHASE_NAMES = {
    kanalkampf: "Kanalkampf",
    adlerangriff: "Adlerangriff",
    airfield_attacks: "Airfield Attacks",
    london_blitz: "London Blitz",
};

const WEATHER_ICONS = {
    clear: "☀️", fair: "🌤️", partly_cloudy: "⛅",
    cloudy: "☁️", overcast: "🌥️", rain: "🌧️",
    fog: "🌫️", storm: "⛈️",
};

let state = null;
let playerSide = "raf";
let autoAdvance = false;
let autoInterval = null;
let canvas, ctx;

const MAP_BOUNDS = { minLat: 49.0, maxLat: 56.0, minLon: -5.5, maxLon: 4.0 };

document.addEventListener("DOMContentLoaded", init);

function init() {
    canvas = document.getElementById("map-canvas");
    ctx = canvas.getContext("2d");

    document.querySelectorAll(".side-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".side-btn").forEach(b => b.classList.remove("selected"));
            btn.classList.add("selected");
            playerSide = btn.dataset.side;
        });
    });

    document.getElementById("start-btn").addEventListener("click", startGame);
    document.getElementById("advance-btn").addEventListener("click", advanceTurn);
    document.getElementById("auto-btn").addEventListener("click", toggleAuto);
    document.getElementById("scramble-btn").addEventListener("click", scramble);
    document.getElementById("launch-raid-btn").addEventListener("click", launchRaid);

    document.getElementById("time-scale").addEventListener("change", e => {
        fetch("/api/set_time_scale", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ hours: parseFloat(e.target.value) }),
        });
    });

    document.querySelectorAll(".tab-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
            document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
            btn.classList.add("active");
            document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
        });
    });

    document.getElementById("sqn-filter-group").addEventListener("change", updateSquadronList);
    document.getElementById("sqn-filter-state").addEventListener("change", updateSquadronList);
    document.getElementById("pilot-filter-side").addEventListener("change", loadPilots);
    document.getElementById("pilot-sort").addEventListener("change", loadPilots);
    document.getElementById("pilot-aces-only").addEventListener("change", loadPilots);

    window.addEventListener("resize", resizeCanvas);
    resizeCanvas();
}

async function startGame() {
    const res = await fetch("/api/new_game", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ side: playerSide }),
    });
    state = await res.json();

    document.getElementById("setup-screen").classList.remove("active");
    document.getElementById("game-screen").classList.add("active");

    if (playerSide === "raf") {
        document.getElementById("raf-orders").style.display = "block";
        document.getElementById("lw-orders").style.display = "none";
    } else {
        document.getElementById("raf-orders").style.display = "none";
        document.getElementById("lw-orders").style.display = "block";
    }

    resizeCanvas();
    updateUI();
}

async function advanceTurn() {
    const res = await fetch("/api/advance", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
    });
    const turnResult = await res.json();

    const fullRes = await fetch("/api/state");
    state = await fullRes.json();
    updateUI();
}

function toggleAuto() {
    autoAdvance = !autoAdvance;
    const btn = document.getElementById("auto-btn");
    if (autoAdvance) {
        btn.classList.add("active");
        btn.textContent = "Stop ■";
        autoInterval = setInterval(advanceTurn, 1500);
    } else {
        btn.classList.remove("active");
        btn.textContent = "Auto ▶▶";
        clearInterval(autoInterval);
    }
}

async function scramble() {
    const sqnId = document.getElementById("scramble-sqn").value;
    const raidId = document.getElementById("scramble-raid").value;
    if (!sqnId) return;

    const res = await fetch("/api/scramble", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ squadron_id: sqnId, raid_id: raidId || null }),
    });
    const result = await res.json();

    const fullRes = await fetch("/api/state");
    state = await fullRes.json();
    updateUI();
}

async function launchRaid() {
    const bombers = Array.from(document.getElementById("raid-bombers").selectedOptions).map(o => o.value);
    const escorts = Array.from(document.getElementById("raid-escorts").selectedOptions).map(o => o.value);
    const target = document.getElementById("raid-target").value;

    if (!bombers.length || !target) return;

    const [targetId, targetType] = target.split("|");
    const res = await fetch("/api/launch_raid", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            bomber_ids: bombers,
            escort_ids: escorts,
            target_id: targetId,
            target_type: targetType,
        }),
    });

    const fullRes = await fetch("/api/state");
    state = await fullRes.json();
    updateUI();
}

function updateUI() {
    if (!state) return;
    const s = state.summary;

    document.getElementById("current-date").textContent = s.date;
    document.getElementById("current-time").textContent = s.time;
    document.getElementById("current-phase").textContent = PHASE_NAMES[s.phase] || s.phase;
    document.getElementById("current-weather").textContent =
        (WEATHER_ICONS[s.weather] || "") + " " + s.weather.replace(/_/g, " ");
    document.getElementById("current-turn").textContent = s.turn;

    document.getElementById("raf-squadrons").textContent = s.raf.squadrons;
    document.getElementById("raf-aircraft-ready").textContent = s.raf.aircraft_ready;
    document.getElementById("raf-aircraft-total").textContent = s.raf.aircraft_total;
    document.getElementById("raf-pilots").textContent = s.raf.pilots_available;
    document.getElementById("raf-radar").textContent = s.raf.radar_stations;
    document.getElementById("raf-airfields").textContent = s.raf.airfields_operational;

    document.getElementById("lw-squadrons").textContent = s.luftwaffe.squadrons;
    document.getElementById("lw-aircraft-ready").textContent = s.luftwaffe.aircraft_ready;
    document.getElementById("lw-aircraft-total").textContent = s.luftwaffe.aircraft_total;
    document.getElementById("lw-pilots").textContent = s.luftwaffe.pilots_available;

    document.getElementById("raf-fighters-lost").textContent = s.raf.stats.fighters_lost;
    document.getElementById("raf-pilots-killed").textContent = s.raf.stats.pilots_killed;
    document.getElementById("lw-fighters-lost").textContent = s.luftwaffe.stats.fighters_lost;
    document.getElementById("lw-bombers-lost").textContent = s.luftwaffe.stats.bombers_lost;
    document.getElementById("lw-pilots-killed").textContent = s.luftwaffe.stats.pilots_killed;
    document.getElementById("lw-pilots-captured").textContent = s.luftwaffe.stats.pilots_captured;

    updateSquadronList();
    updateOrdersPanel();
    updateEventLog();
    updateTopPilots();
    drawMap();
}

function updateSquadronList() {
    if (!state) return;
    const container = document.getElementById("squadron-list");
    const groupFilter = document.getElementById("sqn-filter-group").value;
    const stateFilter = document.getElementById("sqn-filter-state").value;

    let squadrons = Object.values(state.squadrons);

    if (groupFilter !== "all") {
        squadrons = squadrons.filter(s => s.group === groupFilter);
    }
    if (stateFilter !== "all") {
        squadrons = squadrons.filter(s => s.state === stateFilter);
    }

    squadrons.sort((a, b) => {
        if (a.side !== b.side) return a.side === playerSide ? -1 : 1;
        return (a.number || 0) - (b.number || 0);
    });

    container.innerHTML = squadrons.map(sqn => {
        const acType = state.aircraft_types[sqn.aircraft_type];
        const typeName = acType ? acType.name : sqn.aircraft_type;
        const stateClass = "state-" + sqn.state;
        const sideClass = sqn.side === "raf" ? "raf-card" : "lw-card";

        return `<div class="sqn-item ${sideClass}">
            <div class="sqn-header">
                <span class="sqn-name">${sqn.name}</span>
                <span class="sqn-state ${stateClass}">${sqn.state}</span>
            </div>
            <div class="sqn-details">
                <span>${typeName}</span>
                <span>AC: ${sqn.operational_aircraft ?? "?"}/${sqn.aircraft_count}</span>
                <span>Pilots: ${sqn.available_pilots ?? "?"}/${sqn.pilot_count}</span>
            </div>
        </div>`;
    }).join("");
}

function updateOrdersPanel() {
    if (!state) return;

    if (playerSide === "raf") {
        const scrambleSelect = document.getElementById("scramble-sqn");
        const readySquadrons = Object.values(state.squadrons)
            .filter(s => s.side === "raf" && s.can_scramble);

        scrambleSelect.innerHTML = readySquadrons.map(s =>
            `<option value="${s.id}">${s.name} (${s.sortie_strength} ac)</option>`
        ).join("");

        const raidSelect = document.getElementById("scramble-raid");
        raidSelect.innerHTML = '<option value="">Patrol (no target)</option>';
        if (state.active_raids) {
            state.active_raids.forEach(r => {
                if (r.detected) {
                    raidSelect.innerHTML += `<option value="${r.id}">Raid on ${r.target_name} (~${r.estimated_size || "?"} ac)</option>`;
                }
            });
        }
    } else {
        const bomberSelect = document.getElementById("raid-bombers");
        const escortSelect = document.getElementById("raid-escorts");
        const targetSelect = document.getElementById("raid-target");

        const bomberUnits = Object.values(state.squadrons).filter(s =>
            s.side === "luftwaffe" && s.state === "ready" &&
            state.aircraft_types[s.aircraft_type] &&
            ["bomber", "dive_bomber"].includes(state.aircraft_types[s.aircraft_type].role)
        );

        const escortUnits = Object.values(state.squadrons).filter(s =>
            s.side === "luftwaffe" && s.state === "ready" &&
            state.aircraft_types[s.aircraft_type] &&
            state.aircraft_types[s.aircraft_type].role === "fighter"
        );

        bomberSelect.innerHTML = bomberUnits.map(s =>
            `<option value="${s.id}">${s.name} (${s.operational_aircraft ?? "?"} ac)</option>`
        ).join("");

        escortSelect.innerHTML = escortUnits.map(s =>
            `<option value="${s.id}">${s.name} (${s.operational_aircraft ?? "?"} ac)</option>`
        ).join("");

        const targets = Object.values(state.airfields)
            .filter(a => a.side === "raf")
            .map(a => `<option value="${a.id}|airfield">${a.name} (Airfield)</option>`)
            .concat(
                Object.values(state.radar_stations)
                    .filter(r => r.operational)
                    .map(r => `<option value="${r.id}|radar_station">${r.name} (Radar)</option>`)
            );

        targetSelect.innerHTML = targets.join("");
    }
}

function updateEventLog() {
    if (!state || !state.events) return;
    const container = document.getElementById("event-log");
    const events = [...state.events].reverse();

    container.innerHTML = events.map(e => {
        const sideClass = e.side ? `event-${e.side}` : "";
        return `<div class="event-item ${sideClass}">
            <div class="event-time">${e.time} (Turn ${e.turn})</div>
            <div class="event-message">${e.message}</div>
        </div>`;
    }).join("");
}

function resizeCanvas() {
    if (!canvas) return;
    const container = document.getElementById("map-panel");
    if (!container) return;
    canvas.width = container.clientWidth;
    canvas.height = container.clientHeight;
    if (state) drawMap();
}

function latLonToCanvas(lat, lon) {
    const x = (lon - MAP_BOUNDS.minLon) / (MAP_BOUNDS.maxLon - MAP_BOUNDS.minLon) * canvas.width;
    const y = (1 - (lat - MAP_BOUNDS.minLat) / (MAP_BOUNDS.maxLat - MAP_BOUNDS.minLat)) * canvas.height;
    return { x, y };
}

function drawMap() {
    if (!ctx || !state) return;
    const w = canvas.width;
    const h = canvas.height;

    ctx.fillStyle = "#0a1628";
    ctx.fillRect(0, 0, w, h);

    drawCoastline();
    drawGrid();

    if (state.radar_stations) {
        Object.values(state.radar_stations).forEach(rs => {
            if (!rs.operational) return;
            const pos = latLonToCanvas(rs.lat, rs.lon);
            const rangePixels = rs.range_miles * w / ((MAP_BOUNDS.maxLon - MAP_BOUNDS.minLon) * 55);

            ctx.beginPath();
            ctx.arc(pos.x, pos.y, rangePixels, 0, Math.PI * 2);
            ctx.fillStyle = "rgba(0, 230, 118, 0.03)";
            ctx.fill();
            ctx.strokeStyle = "rgba(0, 230, 118, 0.15)";
            ctx.lineWidth = 0.5;
            ctx.stroke();
        });
    }

    if (state.airfields) {
        Object.values(state.airfields).forEach(af => {
            const pos = latLonToCanvas(af.lat, af.lon);
            const isRAF = af.side === "raf";
            const size = af.type === "sector_station" ? 6 : 4;

            ctx.beginPath();
            if (isRAF) {
                ctx.fillStyle = af.is_operational ? "#42a5f5" : "#ef5350";
                ctx.strokeStyle = "#1565c0";
            } else {
                ctx.fillStyle = "#fdd835";
                ctx.strokeStyle = "#f9a825";
            }

            if (af.type === "sector_station") {
                ctx.rect(pos.x - size/2, pos.y - size/2, size, size);
            } else {
                ctx.arc(pos.x, pos.y, size/2, 0, Math.PI * 2);
            }
            ctx.fill();
            ctx.lineWidth = 1;
            ctx.stroke();

            if (af.under_attack) {
                ctx.beginPath();
                ctx.arc(pos.x, pos.y, size + 4, 0, Math.PI * 2);
                ctx.strokeStyle = "#ef5350";
                ctx.lineWidth = 2;
                ctx.setLineDash([3, 3]);
                ctx.stroke();
                ctx.setLineDash([]);
            }
        });
    }

    if (state.radar_stations) {
        Object.values(state.radar_stations).forEach(rs => {
            const pos = latLonToCanvas(rs.lat, rs.lon);
            ctx.beginPath();
            ctx.moveTo(pos.x, pos.y - 5);
            ctx.lineTo(pos.x + 4, pos.y + 3);
            ctx.lineTo(pos.x - 4, pos.y + 3);
            ctx.closePath();
            ctx.fillStyle = rs.operational ? "#00e676" : "#ef5350";
            ctx.fill();
        });
    }

    if (state.active_raids) {
        state.active_raids.forEach(raid => {
            if (!raid.lat || !raid.lon) return;
            const pos = latLonToCanvas(raid.lat, raid.lon);

            ctx.beginPath();
            ctx.arc(pos.x, pos.y, 8, 0, Math.PI * 2);
            ctx.fillStyle = "rgba(239, 83, 80, 0.3)";
            ctx.fill();
            ctx.strokeStyle = "#ef5350";
            ctx.lineWidth = 2;
            ctx.stroke();

            ctx.fillStyle = "#ef5350";
            ctx.font = "bold 9px monospace";
            ctx.textAlign = "center";
            ctx.fillText("✈", pos.x, pos.y + 3);

            if (raid.detected && raid.target_name) {
                ctx.fillStyle = "#ef5350";
                ctx.font = "9px monospace";
                ctx.fillText(raid.target_name, pos.x, pos.y - 12);
            }
        });
    }

    drawLabels();
}

function drawCoastline() {
    const coastEnglandSouth = [
        [50.75, -1.30], [50.72, -1.15], [50.63, -0.92], [50.77, -0.67],
        [50.78, -0.25], [50.78, 0.05], [50.82, 0.27], [50.90, 0.57],
        [50.92, 0.78], [50.95, 0.98], [51.05, 1.15], [51.12, 1.30],
        [51.15, 1.38], [51.37, 1.43], [51.45, 1.35],
    ];
    const coastEnglandEast = [
        [51.45, 1.35], [51.50, 1.10], [51.55, 0.90], [51.58, 0.78],
        [51.72, 0.72], [51.85, 1.00], [51.95, 1.25],
        [52.10, 1.45], [52.40, 1.60], [52.60, 1.72],
        [52.92, 1.30], [53.10, 0.70], [53.30, 0.20],
        [53.55, -0.10], [53.70, -0.05], [53.85, 0.00],
        [54.00, -0.15], [54.10, -0.18], [54.50, -1.10],
        [54.60, -1.20], [55.00, -1.45], [55.40, -1.60],
        [55.75, -1.80], [55.95, -2.10],
    ];
    const coastEnglandWest = [
        [50.75, -1.30], [50.72, -1.55], [50.68, -1.80],
        [50.62, -2.45], [50.55, -3.00], [50.40, -3.50],
        [50.35, -4.10], [50.42, -4.50], [50.50, -5.00],
        [50.70, -5.10], [50.85, -5.05], [51.00, -4.50],
        [51.20, -4.00], [51.45, -3.50], [51.55, -3.20],
        [51.60, -2.95], [51.45, -2.65], [51.50, -2.60],
        [51.60, -2.60], [51.85, -3.10], [52.00, -3.20],
        [52.30, -3.40], [52.50, -3.10], [52.80, -3.30],
        [53.00, -3.10], [53.20, -3.15], [53.35, -3.40],
        [53.40, -3.10], [53.55, -3.10], [53.80, -3.20],
        [54.00, -3.15], [54.20, -3.30], [54.50, -3.55],
        [54.80, -3.40], [55.00, -3.50], [55.35, -3.25],
        [55.85, -3.40], [55.95, -3.10], [55.95, -2.10],
    ];

    const coastFrance = [
        [49.0, -1.80], [49.10, -1.50], [49.20, -1.20],
        [49.30, -0.80], [49.35, -0.50], [49.43, -0.20],
        [49.45, 0.10], [49.48, 0.40], [49.70, 0.80],
        [49.85, 0.95], [50.00, 1.20], [50.10, 1.40],
        [50.30, 1.55], [50.50, 1.60], [50.75, 1.60],
        [50.90, 1.75], [50.95, 1.90], [51.05, 2.10],
        [51.10, 2.35], [51.15, 2.55], [51.22, 2.80],
        [51.30, 3.10], [51.38, 3.30], [51.45, 3.50],
    ];

    ctx.lineWidth = 1.5;

    ctx.beginPath();
    drawPath(coastEnglandSouth);
    ctx.strokeStyle = "#2a4a3a";
    ctx.stroke();

    ctx.beginPath();
    drawPath(coastEnglandEast);
    ctx.strokeStyle = "#2a4a3a";
    ctx.stroke();

    ctx.beginPath();
    drawPath(coastEnglandWest);
    ctx.strokeStyle = "#2a4a3a";
    ctx.stroke();

    fillLand(coastEnglandSouth, coastEnglandEast, coastEnglandWest);

    ctx.beginPath();
    drawPath(coastFrance);
    ctx.strokeStyle = "#3a3a2a";
    ctx.stroke();

    fillFrance(coastFrance);
}

function drawPath(points) {
    points.forEach((p, i) => {
        const pos = latLonToCanvas(p[0], p[1]);
        if (i === 0) ctx.moveTo(pos.x, pos.y);
        else ctx.lineTo(pos.x, pos.y);
    });
}

function fillLand(south, east, west) {
    ctx.beginPath();
    south.forEach((p, i) => {
        const pos = latLonToCanvas(p[0], p[1]);
        if (i === 0) ctx.moveTo(pos.x, pos.y);
        else ctx.lineTo(pos.x, pos.y);
    });
    east.slice(1).forEach(p => {
        const pos = latLonToCanvas(p[0], p[1]);
        ctx.lineTo(pos.x, pos.y);
    });
    const topRight = latLonToCanvas(56, 4);
    const topLeft = latLonToCanvas(56, -5.5);
    ctx.lineTo(topRight.x, topRight.y);
    ctx.lineTo(topLeft.x, topLeft.y);
    west.slice().reverse().forEach(p => {
        const pos = latLonToCanvas(p[0], p[1]);
        ctx.lineTo(pos.x, pos.y);
    });
    ctx.closePath();
    ctx.fillStyle = "#0d2818";
    ctx.fill();
}

function fillFrance(coast) {
    ctx.beginPath();
    coast.forEach((p, i) => {
        const pos = latLonToCanvas(p[0], p[1]);
        if (i === 0) ctx.moveTo(pos.x, pos.y);
        else ctx.lineTo(pos.x, pos.y);
    });
    const br = latLonToCanvas(49, 4);
    const bl = latLonToCanvas(49, -1.8);
    ctx.lineTo(br.x, br.y);
    ctx.lineTo(bl.x, bl.y);
    ctx.closePath();
    ctx.fillStyle = "#1a1a0d";
    ctx.fill();
}

function drawGrid() {
    ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
    ctx.lineWidth = 0.5;

    for (let lat = Math.ceil(MAP_BOUNDS.minLat); lat <= MAP_BOUNDS.maxLat; lat++) {
        const p1 = latLonToCanvas(lat, MAP_BOUNDS.minLon);
        const p2 = latLonToCanvas(lat, MAP_BOUNDS.maxLon);
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();
    }

    for (let lon = Math.ceil(MAP_BOUNDS.minLon); lon <= MAP_BOUNDS.maxLon; lon++) {
        const p1 = latLonToCanvas(MAP_BOUNDS.minLat, lon);
        const p2 = latLonToCanvas(MAP_BOUNDS.maxLat, lon);
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();
    }
}

function drawLabels() {
    ctx.font = "10px monospace";
    ctx.textAlign = "center";

    const labels = [
        { text: "LONDON", lat: 51.50, lon: -0.12, color: "#666" },
        { text: "ENGLISH CHANNEL", lat: 50.15, lon: -0.30, color: "#1a3a5a" },
        { text: "NORTH SEA", lat: 53.0, lon: 2.0, color: "#1a3a5a" },
        { text: "FRANCE", lat: 49.5, lon: 0.5, color: "#4a4a2a" },
    ];

    labels.forEach(l => {
        const pos = latLonToCanvas(l.lat, l.lon);
        ctx.fillStyle = l.color;
        ctx.fillText(l.text, pos.x, pos.y);
    });

    ctx.font = "8px monospace";
    ctx.fillStyle = "rgba(255,255,255,0.15)";
    const groupLabels = [
        { text: "11 GROUP", lat: 51.3, lon: 0.5 },
        { text: "10 GROUP", lat: 51.0, lon: -2.5 },
        { text: "12 GROUP", lat: 52.5, lon: -0.5 },
        { text: "13 GROUP", lat: 54.5, lon: -2.0 },
    ];
    groupLabels.forEach(l => {
        const pos = latLonToCanvas(l.lat, l.lon);
        ctx.fillText(l.text, pos.x, pos.y);
    });
}

const MEDAL_DISPLAY = {
    distinguished_flying_cross: "DFC",
    bar_to_dfc: "DFC & Bar",
    distinguished_service_order: "DSO",
    distinguished_flying_medal: "DFM",
    victoria_cross: "VC",
    iron_cross_2nd_class: "EK2",
    iron_cross_1st_class: "EK1",
    ritterkreuz: "RK",
    ritterkreuz_with_oak_leaves: "RK+EL",
    ritterkreuz_with_swords: "RK+Sw",
    mentioned_in_despatches: "MiD",
};

function updateTopPilots() {
    if (!state || !state.top_pilots) return;
    const container = document.getElementById("pilot-list");
    if (!container) return;
    if (document.getElementById("tab-pilots").classList.contains("active") && container.children.length > 0) return;
}

async function loadPilots() {
    const side = document.getElementById("pilot-filter-side").value;
    const sort = document.getElementById("pilot-sort").value;
    const acesOnly = document.getElementById("pilot-aces-only").checked;

    let url = `/api/pilots?sort=${sort}&limit=100`;
    if (side !== "all") url += `&side=${side}`;
    if (acesOnly) url += `&aces=true`;

    const res = await fetch(url);
    const pilots = await res.json();
    renderPilotList(pilots);
}

function renderPilotList(pilots) {
    const container = document.getElementById("pilot-list");
    container.innerHTML = pilots.map((p, idx) => {
        const sideClass = p.side === "raf" ? "raf-card" : "lw-card";
        const aceMarker = p.is_ace ? '<span class="ace-star">*</span>' : "";
        const histMarker = p.historical ? '<span class="hist-marker">[H]</span>' : "";
        const medals = (p.medals || []).map(m => MEDAL_DISPLAY[m] || m).join(", ");
        const rank = p.rank.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
        const statusClass = p.status === "available" ? "" :
            p.status === "killed" ? "status-kia" :
            p.status === "captured" ? "status-pow" :
            p.status === "wounded" ? "status-wia" : "status-other";

        return `<div class="pilot-item ${sideClass} ${statusClass}" onclick="showPilotDetail('${p.id}')">
            <div class="pilot-header">
                <span class="pilot-rank">${rank}</span>
                <span class="pilot-name">${p.name} ${aceMarker}${histMarker}</span>
            </div>
            <div class="pilot-stats">
                <span>Kills: <b>${p.kills}</b></span>
                <span>Sorties: ${p.sorties}</span>
                <span>Exp: ${Math.round(p.experience * 100)}%</span>
                <span class="pilot-status-badge">${p.status}</span>
            </div>
            ${medals ? `<div class="pilot-medals">${medals}</div>` : ""}
        </div>`;
    }).join("");
}

async function showPilotDetail(pilotId) {
    const res = await fetch(`/api/pilot/${pilotId}`);
    const p = await res.json();
    if (p.error) return;

    const detail = document.getElementById("pilot-detail");
    const medals = (p.medals || []).map(m => MEDAL_DISPLAY[m] || m).join(", ") || "None";
    const rank = p.rank.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
    const role = p.command_role.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
    const traits = p.traits || {};

    detail.innerHTML = `
        <div class="detail-header">
            <h3>${rank} ${p.name}</h3>
            <button class="close-btn" onclick="document.getElementById('pilot-detail').style.display='none'">&times;</button>
        </div>
        <div class="detail-body">
            <div class="detail-row"><span>Status:</span><span>${p.status}</span></div>
            <div class="detail-row"><span>Role:</span><span>${role}</span></div>
            <div class="detail-row"><span>Squadron:</span><span>${p.squadron_name || p.squadron_id}</span></div>
            <div class="detail-row"><span>Aircraft:</span><span>${p.aircraft_name || p.aircraft_type || ""}</span></div>
            <div class="detail-row"><span>Nationality:</span><span>${p.nationality}</span></div>
            <div class="detail-row"><span>Kills:</span><span><b>${p.kills}</b>${p.is_ace ? " (ACE)" : ""}</span></div>
            <div class="detail-row"><span>Sorties:</span><span>${p.sorties}</span></div>
            <div class="detail-row"><span>Medals:</span><span>${medals}</span></div>
            <div class="detail-row"><span>Fatigue:</span><span>${Math.round(p.fatigue * 100)}%</span></div>
            <div class="detail-row"><span>Morale:</span><span>${Math.round(p.morale * 100)}%</span></div>
            <h4>Traits</h4>
            <div class="traits-grid">
                ${Object.entries(traits).map(([k, v]) =>
                    `<div class="trait-bar">
                        <span class="trait-name">${k.replace(/_/g, " ")}</span>
                        <div class="trait-fill-bg"><div class="trait-fill" style="width:${v * 100}%"></div></div>
                        <span class="trait-val">${Math.round(v * 100)}</span>
                    </div>`
                ).join("")}
            </div>
            ${p.historical_notes ? `<div class="hist-notes">${p.historical_notes}</div>` : ""}
            ${p.missions_log && p.missions_log.length > 0 ? `
                <h4>Recent Missions</h4>
                <div class="missions-log">
                    ${p.missions_log.slice(-5).reverse().map(m =>
                        `<div class="mission-entry">${m.date} — ${m.type}${m.kills > 0 ? ` (${m.kills} kills)` : ""}</div>`
                    ).join("")}
                </div>
            ` : ""}
        </div>
    `;
    detail.style.display = "block";
}

canvas && canvas.addEventListener("mousemove", e => {
    if (!state) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    let tooltip = document.querySelector(".map-tooltip");
    let found = false;

    const checkItems = (items, formatter) => {
        for (const item of Object.values(items || {})) {
            if (item.lat == null || item.lon == null) continue;
            const pos = latLonToCanvas(item.lat, item.lon);
            const dist = Math.sqrt((pos.x - mx) ** 2 + (pos.y - my) ** 2);
            if (dist < 12) {
                if (!tooltip) {
                    tooltip = document.createElement("div");
                    tooltip.className = "map-tooltip";
                    document.getElementById("map-panel").appendChild(tooltip);
                }
                tooltip.innerHTML = formatter(item);
                tooltip.style.left = (mx + 15) + "px";
                tooltip.style.top = (my - 10) + "px";
                tooltip.style.display = "block";
                found = true;
                return true;
            }
        }
        return false;
    };

    found = checkItems(state.airfields, af =>
        `<h4>${af.name}</h4>
         <p>Type: ${af.type}</p>
         <p>Runway: ${Math.round(af.runway_condition * 100)}%</p>
         <p>Fuel: ${Math.round(af.fuel_pct * 100)}% | Ammo: ${Math.round(af.ammo_pct * 100)}%</p>
         <p>Squadrons: ${af.squadron_ids.length}</p>`
    );

    if (!found) {
        found = checkItems(state.radar_stations, rs =>
            `<h4>${rs.name}</h4>
             <p>Type: ${rs.type.replace(/_/g, " ")}</p>
             <p>Range: ${rs.range_miles} mi</p>
             <p>Condition: ${Math.round(rs.condition * 100)}%</p>
             <p>Status: ${rs.operational ? "Operational" : "Down"}</p>`
        );
    }

    if (!found && tooltip) {
        tooltip.style.display = "none";
    }
});
