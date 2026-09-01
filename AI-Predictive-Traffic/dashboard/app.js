const wsUrl = 'ws://127.0.0.1:8000/ws/state';
let socket;
let reconnectInterval;

const dom = {
    wsStatus: document.getElementById('ws-status'),
    wsDot: document.getElementById('ws-dot'),
    simStatus: document.getElementById('sim-status'),
    simDot: document.getElementById('sim-dot'),
    simTime: document.getElementById('sim-time'),
    
    ambId: document.getElementById('amb-id'),
    ambSpeed: document.getElementById('amb-speed'),
    ambEdge: document.getElementById('amb-edge'),
    ambCoord: document.getElementById('amb-coord'),
    ambDest: document.getElementById('amb-dest'),
    ambEta: document.getElementById('amb-eta'),
    
    trafficList: document.getElementById('traffic-list'),
    signalList: document.getElementById('signal-list'),
    decisionList: document.getElementById('decision-list'),
    
    ambMarker: document.getElementById('ambulance-marker')
};

function connect() {
    socket = new WebSocket(wsUrl);
    
    socket.onopen = () => {
        dom.wsStatus.textContent = 'CONNECTED';
        dom.wsDot.className = 'dot connected';
        clearInterval(reconnectInterval);
    };
    
    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        if (data.status === "simulation unavailable") {
            setSimulationOffline();
            return;
        }
        
        dom.simStatus.textContent = 'RUNNING';
        dom.simDot.className = 'dot running';
        dom.simTime.textContent = data.simulation_time.toFixed(1);
        
        updateAmbulance(data.ambulance);
        updateTraffic(data.traffic);
        updateSignals(data.signals);
        updateDecisions(data.decisions);
    };
    
    socket.onclose = () => {
        dom.wsStatus.textContent = 'DISCONNECTED';
        dom.wsDot.className = 'dot';
        setSimulationOffline();
        
        clearInterval(reconnectInterval);
        reconnectInterval = setInterval(connect, 2000);
    };
    
    socket.onerror = (err) => {
        socket.close();
    };
}

function setSimulationOffline() {
    dom.simStatus.textContent = 'OFFLINE';
    dom.simDot.className = 'dot';
}

function updateAmbulance(amb) {
    if (!amb) {
        dom.ambId.textContent = '-';
        dom.ambSpeed.textContent = '-';
        dom.ambEdge.textContent = '-';
        dom.ambCoord.textContent = '-';
        dom.ambDest.textContent = '-';
        dom.ambEta.textContent = '-';
        return;
    }
    
    dom.ambId.textContent = amb.vehicle_id || '-';
    dom.ambSpeed.textContent = amb.speed ? amb.speed.toFixed(2) + ' m/s' : '0.00 m/s';
    dom.ambEdge.textContent = amb.current_edge || '-';
    dom.ambCoord.textContent = (amb.latitude && amb.longitude) ? `${amb.latitude.toFixed(4)}, ${amb.longitude.toFixed(4)}` : '-';
    dom.ambDest.textContent = amb.destination || 'Highland Hospital';
    dom.ambEta.textContent = amb.eta ? amb.eta.toFixed(1) + 's' : '-';
    
    // Schematic movement logic
    // Max ETA assumed ~ 500s for a full route, map pos from 10% to 85%
    if (amb.eta && amb.eta > 0) {
        let maxEta = 500;
        let progress = Math.max(0, Math.min(1, 1 - (amb.eta / maxEta)));
        let leftPercent = 10 + (progress * 75);
        dom.ambMarker.style.left = leftPercent + '%';
    }
}

function updateTraffic(traffic) {
    dom.trafficList.innerHTML = '';
    if (!traffic || traffic.length === 0) {
        dom.trafficList.innerHTML = '<div class="card" style="color:var(--text-muted)">No active traffic data</div>';
        return;
    }
    
    traffic.forEach(t => {
        const card = document.createElement('div');
        card.className = 'card';
        card.innerHTML = `
            <strong>Edge:</strong> ${t.edge_id} <br/>
            <strong>Vehicles:</strong> ${t.vehicle_count} | 
            <strong>Speed:</strong> ${t.average_speed.toFixed(1)} m/s
        `;
        dom.trafficList.appendChild(card);
    });
}

function updateSignals(signals) {
    dom.signalList.innerHTML = '';
    if (!signals || signals.length === 0) {
        dom.signalList.innerHTML = '<div class="card" style="color:var(--text-muted)">No signal data</div>';
        return;
    }
    
    signals.forEach(s => {
        const card = document.createElement('div');
        card.className = 'card';
        card.innerHTML = `
            <strong>Junction:</strong> ${s.junction_id} <br/>
            <strong>Phase:</strong> ${s.phase} <br/>
            <span style="font-family:monospace;letter-spacing:2px;font-size:1.1rem;color:${s.state.includes('G') || s.state.includes('g') ?'var(--success)':'var(--danger)'}">
                ${s.state}
            </span>
        `;
        dom.signalList.appendChild(card);
    });
}

function updateDecisions(decisions) {
    dom.decisionList.innerHTML = '';
    if (!decisions || decisions.length === 0) {
        dom.decisionList.innerHTML = '<div style="color:var(--text-muted);font-size:0.9rem">Waiting for AI actions...</div>';
        return;
    }
    
    // Sort descending by timestamp to show latest on top
    const sorted = [...decisions].sort((a,b) => b.timestamp - a.timestamp);
    
    sorted.forEach(d => {
        const item = document.createElement('div');
        item.className = 'decision-item';
        
        let color = 'var(--accent-primary)';
        if (d.action === 'PREEMPT') color = 'var(--warning)';
        if (d.action === 'RESTORE') color = 'var(--success)';
        if (d.action === 'REROUTE') color = 'var(--danger)';
        
        item.innerHTML = `
            <div class="decision-action" style="color:${color}">${d.action}</div>
            <div class="decision-time">t=${d.timestamp.toFixed(1)}s</div>
            <div class="decision-details">${d.details}</div>
        `;
        dom.decisionList.appendChild(item);
    });
}

// Start connection
connect();

// API Interactions for Trip Controls
const startPointSelect = document.getElementById('startPointSelect');
const hospitalSelect = document.getElementById('hospitalSelect');
const startTripBtn = document.getElementById('startTripBtn');
const emergencyCheck = document.getElementById('emergencyCheck');

let startPointsData = [];

async function loadStartingPoints() {
    try {
        const res = await fetch('/api/starting-points');
        startPointsData = await res.json();
        startPointSelect.innerHTML = '';
        
        startPointsData.forEach(sp => {
            const opt = document.createElement('option');
            opt.value = sp.id;
            opt.textContent = sp.label;
            startPointSelect.appendChild(opt);
        });
        
        // Default to Base (1952656064)
        startPointSelect.value = "1952656064";
        loadHospitals();
    } catch (e) {
        console.error("Failed to load starting points", e);
    }
}

async function loadHospitals() {
    try {
        const startJunction = startPointSelect.value;
        const res = await fetch(`/api/hospitals${startJunction ? '?start_junction=' + startJunction : ''}`);
        const hospitals = await res.json();
        
        hospitalSelect.innerHTML = '';
        hospitals.forEach(h => {
            if (h.available) {
                const opt = document.createElement('option');
                opt.value = h.id;
                opt.textContent = h.distance_km != null ? `${h.name} (${h.distance_km} km)` : h.name;
                hospitalSelect.appendChild(opt);
            }
        });
    } catch (e) {
        console.error("Failed to load hospitals", e);
    }
}

startPointSelect.addEventListener('change', loadHospitals);

startTripBtn.addEventListener('click', async () => {
    const hospitalId = hospitalSelect.value;
    const startPointId = startPointSelect.value;
    const isEmergency = emergencyCheck.checked;
    
    if (!hospitalId) {
        alert("Please select a hospital");
        return;
    }
    
    const startObj = startPointsData.find(sp => sp.id === startPointId);
    const startEdge = startObj ? startObj.outgoing_edge : null;
    
    try {
        await fetch('/api/trip/start', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                emergency: isEmergency,
                hospital_id: hospitalId,
                start_edge: startEdge
            })
        });
        // Feedback could be handled via websocket updates
    } catch (e) {
        console.error("Failed to start trip", e);
    }
});

// Init
loadStartingPoints();

