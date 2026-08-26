// ============================================================
// 1. STATE MANAGEMENT
// ============================================================

let selectedRecording = null;
const selectedRecordings = new Set();
let selectedRecordingInfo = null;
let selectedAudioDevice = "";
let playbackActive = false;
let musicPlaying = false;
let musicPaused = false;
let musicCurrentPath = "";
let musicSeekDragging = false;
const selectedMusicFiles = new Set();

let usbConnected = false;

let recorderMonitoring = false;

// Gerät/Kanäle dürfen während keiner laufenden Aufnahme,
// Pegelprüfung oder Wiedergabe (Soundcheck oder Musik) geändert
// werden.
function isAudioBusy(data) {
    return data.recording || data.recorder_monitoring || data.playback_active || data.music_playing || data.bluetooth_streaming;
}

let lastStatusData = {};

// Verbindungsüberwachung: Ein Modal poppt auf, sobald das Statuspoll
// (alle 1s) für mindestens CONNECTION_LOST_THRESHOLD_MS am Stück
// fehlschlägt, und verschwindet automatisch beim nächsten Erfolg.
const CONNECTION_LOST_THRESHOLD_MS = 5000;
const STATUS_FETCH_TIMEOUT_MS = 3000;
let lastSuccessfulUpdate = Date.now();
let connectionLostModalShown = false;

// ============================================================
// 2. CORE UI UPDATES
// ============================================================

async function refreshDashboard() {
    await updateStatus();
}

async function updateStatus() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), STATUS_FETCH_TIMEOUT_MS);

        let response;
        try {
            response = await fetch("/api/status", { signal: controller.signal });
        } finally {
            clearTimeout(timeoutId);
        }

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();

        lastSuccessfulUpdate = Date.now();
        hideConnectionLostModal();

        lastStatusData = data;

        selectedAudioDevice = data.selected_audio_device;

        updateSystemStats(data);
        updateAudioStatus(data);
        updateAudioDeviceSelectState(data);
        updateUsbEjectButton(data);
        updateRecorder(data);
        updateMusicPlayer(data);
        updateBluetooth(data);
    } catch (error) {
        if (Date.now() - lastSuccessfulUpdate >= CONNECTION_LOST_THRESHOLD_MS) {
            showConnectionLostModal();
        }
    }
}

function showConnectionLostModal() {
    if (connectionLostModalShown) return;
    connectionLostModalShown = true;

    const modalElement = document.getElementById("connectionLostModal");
    bootstrap.Modal.getOrCreateInstance(modalElement).show();
}

function hideConnectionLostModal() {
    if (!connectionLostModalShown) return;
    connectionLostModalShown = false;

    const modalElement = document.getElementById("connectionLostModal");
    bootstrap.Modal.getOrCreateInstance(modalElement).hide();
}

function updateSystemStats(data) {
    document.getElementById("hostname").textContent = data.hostname;
    document.getElementById("cpu").textContent = data.cpu + " %";
    document.getElementById("ram").textContent = data.ram + " %";
    document.getElementById("disk").textContent = data.disk + " %";
}

function updateAudioStatus(data) {
    const audioState = document.getElementById("audio-state");
    audioState.innerHTML = data.audio_connected
        ? `<i class="bi bi-check-circle-fill text-success"></i> ${data.audio_device}`
        : `<i class="bi bi-x-circle-fill text-danger"></i> ${data.audio_device}`;

    const audioInfo = document.getElementById("audio-info");
    if (data.audio_connected) {
        audioInfo.textContent =
            `${data.audio_channels} Ch • ` +
            `${data.audio_sample_rate / 1000} kHz • ` +
            `${data.audio_sample_bits} Bit • ` +
            data.audio_formats.join(", ");
    } else {
        audioInfo.textContent = I18N.audio_interface_fallback;
    }
}

function updateAudioDeviceSelectState(data) {
    const select = document.getElementById("audio-device-select");
    if (select) select.disabled = isAudioBusy(data);

    const rescanButton = document.getElementById("audio-rescan");
    if (rescanButton) rescanButton.disabled = isAudioBusy(data);
}

function updateUsbEjectButton(data) {
    const button = document.getElementById("btn-usb-eject");
    if (button) button.classList.toggle("d-none", !data.usb_connected);
}

document.getElementById("btn-usb-eject").addEventListener("click", ejectUsb);

async function ejectUsb() {
    if (!confirm(I18N.confirm_usb_eject)) return;

    const response = await fetch("/api/usb/eject", { method: "POST" });
    const result = await response.json();

    if (!result.success) {
        alert(result.message === "busy" ? I18N.alert_usb_eject_busy : I18N.alert_usb_eject_failed);
        return;
    }

    alert(I18N.alert_usb_eject_success);
}

// ============================================================
// 3. RECORDER UI
// ============================================================

let recorderRecording = false;

function updateRecorder(data) {
    playbackActive = data.playback_active;
    recorderMonitoring = data.recorder_monitoring;
    recorderRecording = data.recording;

    updateRecorderStatus(data);
    updateRecordingInfo(data);
    updateRecordChannels(data);
    updateRecordingList(data.recordings);
    updateSoundcheckButton(data);
    updateLevelCheckButton(data);
    updateRecorderToggleButton(data);
}

function updateRecorderToggleButton(data) {
    const button = document.getElementById("btn-recorder-toggle");
    if (!button) return;

    if (data.recording) {
        button.innerHTML = `<i class="bi bi-stop-circle fs-3"></i><small>${I18N.btn_recording_stop}</small>`;
        button.classList.remove("btn-danger");
        button.classList.add("btn-secondary");
        button.disabled = false;
    } else {
        button.innerHTML = `<i class="bi bi-record-circle fs-3"></i><small>${I18N.btn_recording_start}</small>`;
        button.classList.remove("btn-secondary");
        button.classList.add("btn-danger");
        button.disabled = data.playback_active;
    }
}

const RECORDER_STATE_LABELS = {
    idle: () => I18N.state_idle,
    recording: () => I18N.state_recording,
    playback: () => I18N.state_playback,
    monitoring: () => I18N.state_monitoring,
};

function updateRecorderStatus(data) {
    const label = RECORDER_STATE_LABELS[data.recorder];
    document.getElementById("recorder-status").textContent = label ? label() : data.recorder;
}

function updateRecordingInfo(data) {
    if (data.recording) {
        showRecordingInfo(
            data.current_filename,
            data.duration,
            data.mb_written * 1024 * 1024,
            data.record_channels,
            data.record_sample_rate,
            data.record_bits_per_sample
        );
    } else if (data.playback_active) {
        showRecordingInfo(
            data.playback_filename,
            data.playback_duration,
            selectedRecordingInfo ? selectedRecordingInfo.size : 0,
            data.playback_channels,
            selectedRecordingInfo ? selectedRecordingInfo.sample_rate : 0,
            selectedRecordingInfo ? selectedRecordingInfo.bits_per_sample : 0
        );
    } else if (selectedRecordingInfo) {
        showRecordingInfo(
            selectedRecordingInfo.filename,
            selectedRecordingInfo.duration,
            selectedRecordingInfo.size,
            selectedRecordingInfo.channels,
            selectedRecordingInfo.sample_rate,
            selectedRecordingInfo.bits_per_sample
        );
    } else {
        clearRecordingInfo();
    }
}

function basename(path) {
    if (!path) return path;
    return path.split("/").pop();
}

function showRecordingInfo(filename, duration, size, channels, sampleRate, bitsPerSample) {
    document.getElementById("recorder-file").textContent = filename ? basename(filename) : "-";
    document.getElementById("recorder-duration").textContent = formatDuration(duration);
    document.getElementById("recorder-size").textContent = formatFileSize(size);
    document.getElementById("recorder-format").textContent =
        `Wave64 • ${channels} Ch • ${sampleRate / 1000} kHz • ${bitsPerSample} Bit`;
}

function clearRecordingInfo() {
    document.getElementById("recorder-file").textContent = "-";
    document.getElementById("recorder-duration").textContent = "-";
    document.getElementById("recorder-size").textContent = "-";
    document.getElementById("recorder-format").textContent = "Wave64";
}

// ============================================================
// 4. RECORDING LIST
// ============================================================

function updateRecordingList(recordings) {
    const list = document.getElementById("recording-list");
    list.innerHTML = "";

    if (recordings.length === 0) {
        list.innerHTML = `<div class="text-muted text-center py-3">${I18N.no_recordings}</div>`;
        return;
    }

    const group = document.createElement("div");
    group.className = "list-group";

    recordings.slice(0, 3).forEach((recording) => {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "list-group-item list-group-item-action";

        if (recording === selectedRecording) {
            item.classList.add("active");
        }

        const badge = kindBadge(kindFromFilename(recording));

        item.innerHTML = recording === selectedRecording
            ? `<i class="bi bi-check-circle-fill me-2"></i>${recording} ${badge}`
            : `${recording} ${badge}`;

        item.onclick = async () => {
            selectedRecording = recording;
            await loadRecordingInfo();
            updateRecordingList(recordings);

            const button = document.getElementById("btn-recorder-play");
            if (button && !playbackActive) {
                button.disabled = false;
            }

            //
            // Sofort auffrischen, damit die Beschriftung des
            // Abspielbuttons ("Soundcheck"/"Üben") gleich zur neuen
            // Auswahl passt und nicht erst beim nächsten Poll.
            //
            await refreshDashboard();
        };

        group.appendChild(item);
    });

    list.appendChild(group);
}

// ============================================================
// 5. RECORD CHANNELS
// ============================================================

function updateRecordChannels(data) {
    const select = document.getElementById("record-channels");
    select.innerHTML = "";

    for (let channels = 2; channels <= data.audio_channels; channels += 2) {
        const option = document.createElement("option");
        option.value = channels;
        option.textContent = I18N.channels_option.replace("{n}", channels);
        if (channels === data.record_channels) {
            option.selected = true;
        }
        select.appendChild(option);
    }

    select.onchange = () => {
        setRecordChannels(Number(select.value));
    };

    select.disabled = isAudioBusy(data);
}

async function setRecordChannels(channels) {
    const response = await fetch("/api/recorder/channels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channels })
    });
    const result = await response.json();
    console.log(result);
    await refreshDashboard();
}

// ============================================================
// 6. AUDIO DEVICES
// ============================================================

async function loadAudioDevices() {
    const response = await fetch("/api/audio/devices");
    const devices = await response.json();

    const select = document.getElementById("audio-device-select");
    select.innerHTML = "";

    devices.forEach(device => {
        const option = document.createElement("option");
        option.value = device.id;
        option.textContent = device.name;
        if (device.id === selectedAudioDevice) {
            option.selected = true;
        }
        select.appendChild(option);
    });

    if (!select.dataset.initialized) {
        select.addEventListener("change", async function () {
            const response = await fetch("/api/audio/select", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ device_id: this.value })
            });
            const result = await response.json();
            console.log(result);
            await refreshDashboard();
        });
        select.dataset.initialized = "true";
    }
}

async function rescanAudioDevices() {
    const button = document.getElementById("audio-rescan");
    button.disabled = true;

    const response = await fetch("/api/audio/rescan", { method: "POST" });
    const result = await response.json();
    console.log(result);

    await loadAudioDevices();
    await refreshDashboard();
    button.disabled = false;
}

// ============================================================
// 7. RECORDER CONTROL
// ============================================================

async function toggleRecording() {
    if (recorderRecording) {
        await stopRecorder();
    } else {
        await startRecorder();
    }
}

async function startRecorder() {
    const response = await fetch("/api/recorder/start", { method: "POST" });
    const result = await response.json();
    console.log(result);
    selectedRecording = null;
    selectedRecordingInfo = null;
    await refreshDashboard();
}

async function stopRecorder() {
    const response = await fetch("/api/recorder/stop", { method: "POST" });
    const result = await response.json();
    console.log(result);
    await refreshDashboard();
}

// ============================================================
// 7b. SOUNDCHECK (Wiedergabe einer Aufnahme)
// ============================================================

function updateSoundcheckButton(data) {
    const button = document.getElementById("btn-recorder-play");
    if (!button) return;

    if (data.playback_active) {
        button.innerHTML = `<i class="bi bi-stop-circle fs-3"></i><small>${I18N.btn_stop}</small>`;
        button.classList.remove("btn-success");
        button.classList.add("btn-warning");
        button.disabled = false;
    } else {
        //
        // Beschriftung richtet sich nach der ausgewählten Datei:
        // "Soundcheck" für eine Aufnahme, "Üben" für einen Übungsmix.
        // Die Aktion selbst bleibt identisch - der Player spielt jede
        // Datei auf den Kanälen ab, auf denen sie liegt.
        //
        const label = selectedRecordingInfo && isPracticeMix(selectedRecordingInfo.kind)
            ? I18N.btn_practice
            : I18N.btn_soundcheck;

        button.innerHTML = `<i class="bi bi-play-circle fs-3"></i><small>${label}</small>`;
        button.classList.remove("btn-warning");
        button.classList.add("btn-success");
        button.disabled = !selectedRecording || data.recording || data.music_playing;
    }

    updateRecorderKindBadge();
}

async function toggleSoundcheck() {
    if (playbackActive) {
        await stopSoundcheck();
    } else {
        await startSoundcheck();
    }
}

async function startSoundcheck() {
    if (!selectedRecording) return;

    const response = await fetch("/api/recorder/soundcheck/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: selectedRecording })
    });
    const result = await response.json();
    console.log(result);
    await refreshDashboard();
}

async function stopSoundcheck() {
    const response = await fetch("/api/recorder/soundcheck/stop", { method: "POST" });
    const result = await response.json();
    console.log(result);
    await refreshDashboard();
}

// ============================================================
// 7c. PEGELANZEIGE (Level Meter)
// ============================================================

function updateLevelCheckButton(data) {
    const button = document.getElementById("btn-recorder-monitor");
    if (!button) return;

    if (data.recording) {
        button.innerHTML = `<i class="bi bi-soundwave me-2"></i>${I18N.btn_level_check_recording}`;
        button.classList.remove("btn-outline-info");
        button.classList.add("btn-info");
        button.disabled = true;
    } else if (data.recorder_monitoring) {
        button.innerHTML = `<i class="bi bi-soundwave me-2"></i>${I18N.btn_level_check_stop}`;
        button.classList.remove("btn-outline-info");
        button.classList.add("btn-info");
        button.disabled = false;
    } else {
        button.innerHTML = `<i class="bi bi-soundwave me-2"></i>${I18N.btn_level_check}`;
        button.classList.remove("btn-info");
        button.classList.add("btn-outline-info");
        button.disabled = false;
    }
}

async function toggleLevelCheck() {
    if (recorderMonitoring) {
        await stopLevelCheck();
    } else {
        await startLevelCheck();
    }
}

async function startLevelCheck() {
    const response = await fetch("/api/recorder/monitor/start", { method: "POST" });
    const result = await response.json();
    console.log(result);
    await refreshDashboard();
}

async function stopLevelCheck() {
    const response = await fetch("/api/recorder/monitor/stop", { method: "POST" });
    const result = await response.json();
    console.log(result);
    await refreshDashboard();
}

// Untere Anzeigegrenze in dBFS (alles darunter zeigt als "aus").
// Es geht nur darum, ob überhaupt Signal ankommt - keine präzise
// Pegelmessung (die macht das Mischpult).
const LEVEL_METER_MIN_DB = -50;
const LEVEL_METER_YELLOW_DB = -12;
const LEVEL_METER_RED_DB = -3;

function levelToDb(level) {
    if (level <= 0) return -Infinity;
    return 20 * Math.log10(level);
}

function levelToPercent(level) {
    const db = Math.max(LEVEL_METER_MIN_DB, Math.min(0, levelToDb(level)));
    return ((db - LEVEL_METER_MIN_DB) / -LEVEL_METER_MIN_DB) * 100;
}

function levelColorClass(level) {
    const db = levelToDb(level);
    if (db >= LEVEL_METER_RED_DB) return "level-fill-red";
    if (db >= LEVEL_METER_YELLOW_DB) return "level-fill-yellow";
    return "";
}

function renderLevelMeters(levels) {
    const container = document.getElementById("level-meters");
    if (!container) return;

    if (!levels || levels.length === 0) {
        container.className = "mb-2";
        container.innerHTML = `<div class="text-muted text-center py-2"><small>${I18N.level_no_signal}</small></div>`;
        return;
    }

    if (container.children.length !== levels.length) {
        container.className = "level-grid mb-2";
        container.innerHTML = "";

        levels.forEach((_, index) => {
            const cell = document.createElement("div");
            cell.className = "level-cell";
            cell.innerHTML = `
                <small class="level-label">${index + 1}</small>
                <div class="level-track">
                    <div class="level-fill"></div>
                </div>
            `;
            container.appendChild(cell);
        });
    }

    levels.forEach((level, index) => {
        const fill = container.children[index].querySelector(".level-fill");
        fill.style.width = levelToPercent(level) + "%";

        fill.classList.remove("level-fill-yellow", "level-fill-red");
        const colorClass = levelColorClass(level);
        if (colorClass) fill.classList.add(colorClass);
    });
}

async function pollLevels() {
    try {
        const response = await fetch("/api/recorder/levels");
        const data = await response.json();
        renderLevelMeters(data.monitoring ? data.levels : []);
    } catch (error) {
        console.error("Fehler beim Abrufen der Pegel:", error);
    }
}

// ============================================================
// 7d. KANALFADER DER KONSOLE
// ============================================================

//
// Die Fader sind bewusst gesperrt, bis man sie über das Schloss-Symbol
// freigibt - damit beim Hantieren mit dem Gerät nichts verrutscht.
//
// Die Sperre dient zugleich als Verkehrsbremse: Nur im entsperrten
// Zustand wird das Pult überhaupt abgefragt. Gesperrt (der Normalfall)
// entsteht kein einziges UDP-Paket.
//
let fadersUnlocked = false;
let faderPollTimer = null;
let faderChannels = [];

//
// Kanal, an dem gerade gezogen wird - der wird vom Auffrischen
// ausgenommen, sonst springt der Regler unter dem Finger weg.
//
let faderDragging = null;

//
// Beim Ziehen entstehen sonst hunderte Anfragen pro Sekunde.
//
const FADER_SEND_INTERVAL = 50;
let faderLastSent = 0;

const FADER_MIN_DB = -90;
const FADER_MAX_DB = 10;

//
// Automatische Sperre. Sie laeuft auf Ruhe seit der letzten
// Beruehrung, nicht ab dem Entsperren: Wer gerade mischt, soll nicht
// mitten im Zug ausgesperrt werden.
//
const fadersAutolock = window.FADERS_AUTOLOCK || { enabled: false, seconds: 60 };
let faderAutolockTimer = null;

function resetFaderAutolock() {
    if (faderAutolockTimer) {
        clearTimeout(faderAutolockTimer);
        faderAutolockTimer = null;
    }

    if (!fadersAutolock.enabled || !fadersUnlocked) return;

    faderAutolockTimer = setTimeout(() => {
        //
        // Nicht mitten in einer Zieh-Geste zuschnappen - das waere
        // genau der Moment, in dem eine Sperre schadet statt zu
        // schuetzen. Stattdessen die Frist neu beginnen.
        //
        if (faderDragging !== null) {
            resetFaderAutolock();
            return;
        }

        if (fadersUnlocked) toggleFaderLock();

    }, fadersAutolock.seconds * 1000);
}

function formatDb(db) {
    if (db === null || db === undefined || db <= FADER_MIN_DB) {
        return "-∞";
    }
    return (db > 0 ? "+" : "") + db.toFixed(1);
}

function toggleFaderLock() {
    fadersUnlocked = !fadersUnlocked;

    const button = document.getElementById("btn-faders-lock");
    button.innerHTML = fadersUnlocked
        ? `<i class="bi bi-unlock-fill"></i>`
        : `<i class="bi bi-lock-fill"></i>`;
    button.title = fadersUnlocked ? I18N.faders_lock : I18N.faders_unlock;
    button.classList.toggle("btn-outline-secondary", !fadersUnlocked);
    button.classList.toggle("btn-warning", fadersUnlocked);

    //
    // Die Sperre muss beides erfassen - ein Mute-Knopf, der trotz
    // Schloss reagiert, wäre eine Lücke genau dort, wo die Sperre
    // schützen soll.
    //
    document.querySelectorAll(".fader-input, .fader-mute").forEach((element) => {
        element.disabled = !fadersUnlocked;
    });

    document.querySelectorAll(".fader-cell").forEach((cell) => {
        cell.classList.toggle("is-locked", !fadersUnlocked);
    });

    const hint = document.getElementById("faders-hint");
    if (hint) hint.classList.toggle("d-none", fadersUnlocked);

    if (fadersUnlocked) {
        loadFaders();
        if (faderPollTimer) clearInterval(faderPollTimer);
        faderPollTimer = setInterval(loadFaders, 2000);
    } else if (faderPollTimer) {
        clearInterval(faderPollTimer);
        faderPollTimer = null;
    }

    resetFaderAutolock();
}

// ------------------------------------------------------------
// Schnellregler in der Musikspieler- und Bluetooth-Karte
//
// Regelt das Stereopaar, das in der jeweiligen Karte gewaehlt ist -
// damit man zum Lautermachen nicht bis zur Kanalzug-Karte scrollen
// muss. Beide Karten teilen sich diese Logik; der Unterschied ist nur
// das Namenspraefix ("music" oder "bluetooth").
// ------------------------------------------------------------

//
// Zwei Bausteine, die sich Kanalzuege und Schnellregler teilen. Sie
// standen vorher in beiden Wegen getrennt - ein geaenderter
// Knopf-Stil oder eine vergessene Fehlerbehandlung waere nur an einer
// der beiden Stellen angekommen.
//

//
// Stumm wird als gefuellter roter Knopf gezeigt, sonst nur als Umriss
// - auf einen Blick erkennbar, welche Kanaele liegen.
//
function renderMuteButton(button, muted) {
    if (!button) return;

    button.classList.toggle("btn-danger", muted);
    button.classList.toggle("btn-outline-secondary", !muted);
}

//
// Ein Befehl ans Pult. Faellt er aus, ist das kein Grund, die
// Oberflaeche anzuhalten: Beim naechsten Auffrischen steht ohnehin
// wieder der echte Wert vom Pult da.
//
async function sendToConsole(url, payload, was) {
    try {
        await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
    } catch (error) {
        console.error(`${was} fehlgeschlagen:`, error);
    }
}

const pairFaders = {
    music: { start: null, dragging: false, lastSent: 0, lastPoll: 0, available: false },
    bluetooth: { start: null, dragging: false, lastSent: 0, lastPoll: 0, available: false },
};

//
// Solange die Quelle laeuft, oefter nachsehen - jemand koennte am Pult
// oder in der Kanalzug-Karte drehen. Steht sie still, reicht ein
// gelegentlicher Blick, damit der Regler auftaucht, sobald das Pult
// erreichbar wird.
//
const PAIR_POLL_ACTIVE = 3000;
const PAIR_POLL_IDLE = 15000;

function pairElements(prefix) {
    return {
        box: document.getElementById(`${prefix}-pair`),
        input: document.getElementById(`${prefix}-pair-input`),
        mute: document.getElementById(`${prefix}-pair-mute`),
        readout: document.getElementById(`${prefix}-pair-db`),
    };
}

//
// Wird aus den Statusaktualisierungen beider Karten aufgerufen.
// "start" ist der erste Kanal des gewaehlten Paars, "active" sagt, ob
// gerade gespielt bzw. verbunden ist.
//
function refreshPairFader(prefix, start, active) {
    const state = pairFaders[prefix];
    const { box } = pairElements(prefix);

    if (!box) return;

    if (!start) {
        box.classList.add("d-none");
        return;
    }

    //
    // Kanalwechsel: sofort neu lesen, nicht auf das naechste
    // Zeitfenster warten - sonst zeigt der Regler kurz den Pegel des
    // vorherigen Paars.
    //
    const changed = state.start !== start;
    state.start = start;

    if (state.dragging) return;

    const interval = state.available && active ? PAIR_POLL_ACTIVE : PAIR_POLL_IDLE;
    const now = Date.now();

    if (!changed && now - state.lastPoll < interval) return;

    state.lastPoll = now;

    loadPairFader(prefix);
}

async function loadPairFader(prefix) {
    const state = pairFaders[prefix];
    const { box, input, mute, readout } = pairElements(prefix);

    if (!box || !state.start) return;

    let data;

    try {
        data = await (await fetch(`/api/console/pair?start=${state.start}`)).json();
    } catch (error) {
        box.classList.add("d-none");
        state.available = false;
        return;
    }

    state.available = Boolean(data.available);
    state.natural = Boolean(data.natural);
    state.linked = Boolean(data.linked);
    state.linkedByXrack = Boolean(data.linked_by_xrack);

    box.classList.toggle("d-none", !data.available);

    if (!data.available) return;

    //
    // Nicht ueberschreiben, waehrend der Finger am Regler ist.
    //
    if (!state.dragging) {
        input.value = data.db === null ? FADER_MIN_DB : data.db;
        readout.textContent = formatDb(data.db);
    }

    renderMuteButton(mute, data.muted);
}

["music", "bluetooth"].forEach((prefix) => {
    const { input, mute } = pairElements(prefix);

    if (!input || !mute) return;

    const state = pairFaders[prefix];

    input.addEventListener("pointerdown", () => {
        state.dragging = true;
    });

    input.addEventListener("input", async () => {
        const db = parseFloat(input.value);

        pairElements(prefix).readout.textContent =
            formatDb(db <= FADER_MIN_DB ? null : db);

        //
        // Drosseln wie bei den Kanalzuegen: "input" feuert beim Ziehen
        // pro Pixel.
        //
        const now = Date.now();
        if (now - state.lastSent < FADER_SEND_INTERVAL) return;
        state.lastSent = now;

        await sendPairFader(prefix, db);
    });

    mute.addEventListener("click", () => togglePairMute(prefix));
});

//
// Wie bei den Kanalzuegen auf Dokumentebene: Ein Handler direkt am
// Regler wuerde beim Loslassen zuerst laufen und den letzten Wert
// verschlucken.
//
document.addEventListener("pointerup", finishPairDrag);
document.addEventListener("pointercancel", finishPairDrag);

async function finishPairDrag() {
    for (const prefix of ["music", "bluetooth"]) {
        const state = pairFaders[prefix];

        if (!state.dragging) continue;

        state.dragging = false;

        const { input } = pairElements(prefix);

        if (input) await sendPairFader(prefix, parseFloat(input.value));
    }
}

async function sendPairFader(prefix, db) {
    const state = pairFaders[prefix];

    if (!state.start) return;

    await sendToConsole(
        "/api/console/pair/fader",
        { start: state.start, db: db <= FADER_MIN_DB ? null : db },
        "Pegel"
    );
}

async function togglePairMute(prefix) {
    const state = pairFaders[prefix];
    const { mute } = pairElements(prefix);

    if (!state.start || !mute) return;

    const muted = !mute.classList.contains("btn-danger");

    renderMuteButton(mute, muted);

    await sendToConsole(
        "/api/console/pair/mute",
        { start: state.start, muted },
        "Stummschaltung"
    );
}

//
// Beim Wechsel des Stereopaars: erst fragen, ob das alte Paar wieder
// entkoppelt werden soll, dann, ob das neue gekoppelt werden soll.
//
// Zwei Ausnahmen, ohne die das Fragen laestig oder schlicht falsch
// waere:
//
// - Natuerliche Stereopaare (beim X-Air 17+18 auf dem Aux-Rueckweg)
//   haben ohnehin nur einen Fader. Da gibt es nichts zu koppeln.
// - Entkoppelt wird nur, was XRack selbst gekoppelt hat. Eine
//   Kopplung, die am Pult eingerichtet wurde, gehoert dem Nutzer -
//   die darf XRack nicht ungefragt aufloesen, und auch nicht anbieten.
//
async function handlePairChange(prefix, previous, next) {
    const state = pairFaders[prefix];

    if (previous && previous !== next && state.available) {

        if (!state.natural && state.linked && state.linkedByXrack) {

            const frage = I18N.pair_unlink_confirm
                .replace("{a}", previous)
                .replace("{b}", previous + 1);

            if (confirm(frage)) await setPairLink(previous, false);
        }
    }

    //
    // Zustand des neuen Paars holen - erst danach steht fest, ob es
    // ueberhaupt etwas zu koppeln gibt.
    //
    state.start = next;
    await loadPairFader(prefix);

    if (!state.available || state.natural || state.linked) return;

    const frage = I18N.pair_link_confirm
        .replace("{a}", next)
        .replace("{b}", next + 1);

    if (confirm(frage)) {
        await setPairLink(next, true);
        await loadPairFader(prefix);
    }
}

async function setPairLink(start, linked) {
    try {
        await fetch("/api/console/pair/link", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ start, linked }),
        });
    } catch (error) {
        console.error("Kopplung konnte nicht geaendert werden:", error);
    }
}

//
// Gesperrt wird nicht gepollt - das ist Absicht, im Ruhezustand soll
// kein einziges Paket ins Netz gehen. Der Preis: Die Karte zeigt dann
// den Stand vom letzten Laden. Wer zwei Geraete nebeneinander legt,
// sieht deshalb womoeglich zwei verschiedene Meldungen fuer dieselbe
// Lage - genau das ist einmal passiert.
//
// Kompromiss ohne Dauerverkehr: einmal nachfragen, sobald die Seite
// wieder sichtbar wird. Also genau dann, wenn jemand hinsieht.
//
document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") loadFaders();
});

async function loadFaders() {
    let data;

    try {
        const response = await fetch("/api/console/channels");
        data = await response.json();
    } catch (error) {
        console.error("Fehler beim Abrufen der Fader:", error);
        return;
    }

    const unavailable = document.getElementById("faders-unavailable");
    const grid = document.getElementById("faders-grid");
    const hint = document.getElementById("faders-hint");
    if (!unavailable || !grid) return;

    if (!data.available) {
        unavailable.textContent = data.reason === "no_response"
            ? I18N.faders_no_response.replace("{ip}", data.host || "?")
            : I18N.faders_no_connection;
        unavailable.classList.remove("d-none");
        grid.classList.add("d-none");
        if (hint) hint.classList.add("d-none");
        faderChannels = [];
        return;
    }

    unavailable.classList.add("d-none");
    grid.classList.remove("d-none");

    //
    // Beim ersten Laden sind die Fader gesperrt - dann gehört der
    // Hinweis sichtbar, sonst wirkt die Karte kaputt.
    //
    if (hint) hint.classList.toggle("d-none", fadersUnlocked);

    renderFaders(data.channels);
}

function renderFaders(channels) {
    const grid = document.getElementById("faders-grid");

    //
    // Struktur nur neu bauen, wenn sich Kanalzahl oder Beschriftungen
    // geändert haben - sonst nur Werte setzen (Muster wie bei der
    // Pegelanzeige). Die Ausrichtung waagerecht/senkrecht macht allein
    // das CSS, hier gibt es dafür keine Fallunterscheidung.
    //
    const signature = channels
        .map((c) => `${c.label}|${c.name}|${c.is_main}`)
        .join(";");

    if (grid.dataset.signature !== signature) {
        grid.dataset.signature = signature;
        grid.className = "fader-grid";
        grid.innerHTML = "";

        channels.forEach((channel) => {
            const cell = document.createElement("div");
            cell.className =
                "fader-cell"
                + (fadersUnlocked ? "" : " is-locked")
                + (channel.is_main ? " is-main" : "");
            cell.innerHTML = `
                <span class="fader-name" title="${channel.name || ""}">
                    <span class="fader-number">${channel.label}</span>${channel.name || ""}
                </span>
                <button
                    type="button"
                    class="btn btn-outline-secondary fader-mute"
                    data-channel="${channel.channel}"
                    title="${I18N.faders_mute}"
                    ${fadersUnlocked ? "" : "disabled"}
                >M</button>
                <input
                    type="range"
                    class="form-range fader-input"
                    min="${FADER_MIN_DB}"
                    max="${FADER_MAX_DB}"
                    step="0.5"
                    data-channel="${channel.channel}"
                    ${fadersUnlocked ? "" : "disabled"}
                >
                <span class="fader-db"></span>
            `;

            cell.querySelector(".fader-mute")
                .addEventListener("click", () => toggleMute(channel.channel));

            const input = cell.querySelector(".fader-input");
            input.addEventListener("input", onFaderInput);
            input.addEventListener("pointerdown", () => {
                faderDragging = channel.channel;
                resetFaderAutolock();
            });

            //
            // Das Loslassen behandelt bewusst nur der Zuhörer am
            // Dokument (weiter unten): Ein eigener pointerup hier
            // liefe durch das Bubbling zuerst, würde faderDragging
            // leeren - und der Endwert käme nie beim Pult an.
            //

            grid.appendChild(cell);
        });
    }

    faderChannels = channels;

    channels.forEach((channel, index) => {
        if (faderDragging === channel.channel) return;

        const cell = grid.children[index];
        const input = cell.querySelector(".fader-input");
        const readout = cell.querySelector(".fader-db");
        const mute = cell.querySelector(".fader-mute");

        const db = channel.db === null ? FADER_MIN_DB : channel.db;

        input.value = db;
        readout.textContent = formatDb(channel.db);

        renderMuteButton(mute, channel.muted);
    });
}

async function toggleMute(channel) {
    const cell = document.querySelector(
        `.fader-mute[data-channel="${channel}"]`
    )?.closest(".fader-cell");

    if (!cell) return;

    const button = cell.querySelector(".fader-mute");
    const muted = !button.classList.contains("btn-danger");

    resetFaderAutolock();

    //
    // Sofort umschalten, damit die Rückmeldung nicht erst beim
    // nächsten Auffrischen kommt.
    //
    renderMuteButton(button, muted);

    await sendToConsole(
        "/api/console/mute",
        { channel, muted },
        "Stummschaltung"
    );
}

async function onFaderInput(event) {
    const input = event.target;
    const readout = input.closest(".fader-cell").querySelector(".fader-db");

    //
    // Jede Beruehrung schiebt die Frist nach hinten - auch die
    // Tastaturbedienung, die kein pointerdown ausloest.
    //
    resetFaderAutolock();

    const db = parseFloat(input.value);
    readout.textContent = formatDb(db <= FADER_MIN_DB ? null : db);

    //
    // Drosseln: Beim Ziehen feuert "input" pro Pixel, das würde das
    // Pult mit UDP-Paketen überschwemmen.
    //
    const now = Date.now();
    if (now - faderLastSent < FADER_SEND_INTERVAL) return;
    faderLastSent = now;

    await sendFader(parseInt(input.dataset.channel, 10), db);
}

async function sendFader(channel, db) {
    await sendToConsole(
        "/api/console/fader",
        { channel, db: db <= FADER_MIN_DB ? null : db },
        "Fader"
    );
}

//
// Beim Loslassen den Endwert noch einmal sicher schicken - die
// Drosselung oben könnte genau die letzte Bewegung verschluckt haben.
//
function finishFaderDrag() {
    if (faderDragging === null) return;

    const input = document.querySelector(
        `.fader-input[data-channel="${faderDragging}"]`
    );

    if (input) {
        sendFader(faderDragging, parseFloat(input.value));
    }

    faderDragging = null;
}

document.addEventListener("pointerup", finishFaderDrag);
document.addEventListener("pointercancel", finishFaderDrag);

//
// Einmal beim Laden prüfen, ob überhaupt ein Steuerweg besteht - dann
// steht dort gleich der passende Hinweis statt einer leeren Karte.
//
loadFaders();

// ============================================================
// 8. RECORDING INFO LOADING
// ============================================================

async function loadRecordingInfo() {
    if (!selectedRecording) return;

    const response = await fetch("/api/recording/info", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: selectedRecording })
    });

    const result = await response.json();
    if (result.success) {
        selectedRecordingInfo = result;
        updateRecorderKindBadge();
        console.log(result);
    }
}

// ------------------------------------------------------------
// Art der Datei: Soundcheck-Aufnahme oder Übungsmix
// (siehe core/recording_kind.py - das Kürzel steckt im Dateinamen)
// ------------------------------------------------------------

function isPracticeMix(kind) {
    return kind === "practice";
}

//
// Spiegelt kind_from_filename() aus core/recording_kind.py.
//
// Nötig, weil die Kurzliste auf der Karte aus dem Dashboard-Status
// gespeist wird, der aus Performancegründen nur Dateinamen überträgt
// (er wird im Sekundentakt abgerufen). Wird das Kürzel dort jemals
// geändert, muss es hier mitgeändert werden.
//
function kindFromFilename(filename) {
    const stem = filename.replace(/\.[^.]*$/, "");
    return stem.endsWith("_p") ? "practice" : "soundcheck";
}

function kindLabel(kind) {
    return isPracticeMix(kind)
        ? I18N.badge_kind_practice
        : I18N.badge_kind_soundcheck;
}

function kindBadge(kind) {
    const style = isPracticeMix(kind) ? "text-bg-info" : "text-bg-secondary";
    const icon = isPracticeMix(kind) ? "bi-people" : "bi-sliders";

    return `<span class="badge ${style}"><i class="bi ${icon} me-1"></i>${kindLabel(kind)}</span>`;
}

function updateRecorderKindBadge() {
    const element = document.getElementById("recorder-kind");
    if (!element) return;

    element.innerHTML = selectedRecording && selectedRecordingInfo
        ? kindBadge(selectedRecordingInfo.kind)
        : "";
}

// ============================================================
// 9. RECORDINGS MODAL
// ============================================================

const recordingsModal = document.getElementById("recordingsModal");
recordingsModal.addEventListener("show.bs.modal", loadRecordings);

async function loadRecordings()
{
    try
    {
        const response = await fetch("/api/recordings");

        if (!response.ok)
        {
            throw new Error("API-Fehler");
        }

        const recordings = await response.json();

        // Ausgewählte Aufnahmen bereinigen
        selectedRecordings.forEach(filename =>
        {
            if (!recordings.some(recording => recording.filename === filename))
            {
                selectedRecordings.delete(filename);
            }
        });

        updateDeleteSelectedButton();

        try
        {
            const usbResponse = await fetch("/api/usb/status");
            const usbData = await usbResponse.json();
            usbConnected = Boolean(usbData.connected);
        }
        catch (error)
        {
            usbConnected = false;
        }

        renderRecordings(recordings);
    }
    catch (error)
    {
        console.error(
            "Fehler beim Laden der Aufnahmen:",
            error
        );
    }
}
function renderRecordings(recordings) {
    const container = document.getElementById("recordingsList");
    container.innerHTML = "";
    for (const recording of recordings) {
        container.appendChild(createRecordingCard(recording));
    }
}

function createRecordingCard(recording) {
    const isSelected = recording.filename === selectedRecording;

    const card = document.createElement("div");
    card.className = "card mb-2" + (isSelected ? " border-primary" : "");
    card.innerHTML = `
        <div class="card-body d-flex justify-content-between align-items-start">
            <div class="form-check mt-2">
                <input class="form-check-input" type="checkbox" data-action="select" data-filename="${recording.filename}">
            </div>
            <div class="flex-grow-1">
                <h6 class="card-title mb-2">
                    <i class="bi bi-music-note-beamed me-2"></i>
                    ${recording.filename}
                    <span class="ms-2">${kindBadge(recording.kind)}</span>
                    ${isSelected ? `<span class="badge text-bg-primary ms-2">${I18N.badge_selected_for_soundcheck}</span>` : ''}
                </h6>
                <small class="text-body-secondary">
                    ${recording.channels} Ch •
                    ${recording.sample_rate / 1000} kHz •
                    ${recording.bits_per_sample} Bit •
                    ${formatDuration(recording.duration)} •
                    ${formatFileSize(recording.size)}
                </small>
            </div>
            <div class="btn-group btn-group-sm">
                <button class="btn btn-outline-success btn-sm" title="${I18N.title_choose_for_soundcheck}" data-action="choose" data-filename="${recording.filename}">
                    <i class="bi bi-play-circle"></i>
                </button>
                <button class="btn btn-outline-primary btn-sm" title="${I18N.title_download}" data-action="download" data-filename="${recording.filename}">
                    <i class="bi bi-download"></i>
                </button>
                ${usbConnected ? `
                <button class="btn btn-outline-secondary btn-sm" title="${I18N.title_copy_to_usb}" data-action="copy-usb" data-filename="${recording.filename}">
                    <i class="bi bi-usb-drive"></i>
                </button>
                ` : ''}
                <button class="btn btn-outline-danger btn-sm" title="${I18N.title_delete}" data-action="delete" data-filename="${recording.filename}">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
        </div>
    `;
    return card;
}

// ============================================================
// 10. RECORDING ACTIONS (Download, Delete, Select)
// ============================================================

document.getElementById("recordingsList").addEventListener("click", handleRecordingAction);
document.getElementById("deleteSelectedButton").addEventListener("click", deleteSelectedRecordings);

async function handleRecordingAction(event) {
    const element = event.target.closest("[data-action]");
    if (!element) return;

    const filename = element.dataset.filename;

    switch (element.dataset.action) {
        case "download":
            downloadRecording(filename);
            break;
        case "delete":
            await deleteRecording(filename);
            break;
        case "select":
            toggleRecordingSelection(filename, element.checked);
            break;
        case "choose":
            await chooseRecordingForPlayback(filename);
            break;
        case "copy-usb":
            await copyRecordingToUsb(filename);
            break;
    }
}

let usbCopyPollTimer = null;

async function copyRecordingToUsb(filename) {
    const response = await fetch("/api/recordings/copy_to_usb", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename })
    });
    const result = await response.json();

    if (!result.success) {
        switch (result.status) {
            case "busy":
                alert(I18N.alert_usb_copy_busy);
                break;
            case "no_usb":
                alert(I18N.alert_usb_copy_no_usb);
                break;
            default:
                alert(I18N.alert_usb_copy_failed);
        }
        return;
    }

    showUsbCopyProgress(filename);
    pollUsbCopyProgress();
}

function showUsbCopyProgress(filename) {
    document.getElementById("usbCopyProgressLabel").textContent = filename;
    document.getElementById("usbCopyProgressPercent").textContent = "0%";
    document.getElementById("usbCopyProgressBar").style.width = "0%";
    document.getElementById("usbCopyProgress").classList.remove("d-none");
}

function hideUsbCopyProgress() {
    document.getElementById("usbCopyProgress").classList.add("d-none");
}

function pollUsbCopyProgress() {
    if (usbCopyPollTimer) clearInterval(usbCopyPollTimer);

    usbCopyPollTimer = setInterval(async () => {
        let data;

        try {
            const response = await fetch("/api/usb/copy_status");
            data = await response.json();
        } catch (error) {
            clearInterval(usbCopyPollTimer);
            usbCopyPollTimer = null;
            hideUsbCopyProgress();
            return;
        }

        const percent = data.total > 0 ? Math.round((data.copied / data.total) * 100) : 0;
        document.getElementById("usbCopyProgressPercent").textContent = `${percent}%`;
        document.getElementById("usbCopyProgressBar").style.width = `${percent}%`;

        if (data.active) return;

        clearInterval(usbCopyPollTimer);
        usbCopyPollTimer = null;
        hideUsbCopyProgress();

        if (!data.success) {
            alert(I18N.alert_usb_copy_failed);
        } else if (data.already_exists) {
            alert(I18N.alert_usb_copy_already_exists);
        } else {
            alert(I18N.alert_usb_copy_success);
        }
    }, 300);
}

async function chooseRecordingForPlayback(filename) {
    selectedRecording = filename;
    await loadRecordingInfo();

    const button = document.getElementById("btn-recorder-play");
    if (button && !playbackActive) {
        button.disabled = false;
    }

    const modalElement = document.getElementById("recordingsModal");
    const modal = bootstrap.Modal.getOrCreateInstance(modalElement);
    modal.hide();

    await refreshDashboard();
}

function downloadRecording(filename) {
    window.location.href = `/api/recordings/${encodeURIComponent(filename)}`;
}

async function deleteRecording(filename) {
    if (!confirm(I18N.confirm_delete_file.replace("{name}", filename))) return;

    const response = await fetch(`/api/recordings/${encodeURIComponent(filename)}`, {
        method: "DELETE"
    });

    if (!response.ok) {
        alert(I18N.alert_recording_delete_failed);
        return;
    }

    if (filename === selectedRecording) {
        selectedRecording = null;
        selectedRecordingInfo = null;
    }

    await loadRecordings();
    await refreshDashboard();
}

function toggleRecordingSelection(filename, selected) {
    if (selected) {
        selectedRecordings.add(filename);
    } else {
        selectedRecordings.delete(filename);
    }
    updateDeleteSelectedButton();
}

function updateDeleteSelectedButton() {
    const button = document.getElementById("deleteSelectedButton");
    if (!button) return;

    button.disabled = selectedRecordings.size === 0;
    button.innerHTML = `
        <i class="bi bi-trash"></i>
        ${I18N.btn_delete_selected} (${selectedRecordings.size})
    `;
}

async function deleteSelectedRecordings() {
    if (selectedRecordings.size === 0) {
        return;
    }

    if (!confirm(I18N.confirm_delete_multi.replace("{count}", selectedRecordings.size))) {
        return;
    }

    const response = await fetch("/api/recordings/delete", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            filenames: Array.from(selectedRecordings),
        }),
    });

    if (!response.ok) {
        alert(I18N.alert_recordings_delete_failed);
        return;
    }

    if (selectedRecording && selectedRecordings.has(selectedRecording)) {
        selectedRecording = null;
        selectedRecordingInfo = null;
    }

    selectedRecordings.clear();
    updateDeleteSelectedButton();
    await loadRecordings();
    await refreshDashboard();
}

// ------------------------------------------------------------
// Aufnahmen hochladen (.w64)
// ------------------------------------------------------------

document.getElementById("recording-upload-input").addEventListener("change", uploadRecordingFiles);

function uploadRecordingsWithProgress(formData) {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", "/api/recordings/upload");

        xhr.upload.addEventListener("progress", (event) => {
            if (event.lengthComputable) {
                updateRecordingUploadProgress(event.loaded, event.total);
            }
        });

        xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                try {
                    resolve(JSON.parse(xhr.responseText));
                } catch (error) {
                    reject(error);
                }
            } else {
                reject(new Error(`Upload fehlgeschlagen (${xhr.status})`));
            }
        };

        xhr.onerror = () => reject(new Error("Netzwerkfehler beim Upload"));

        xhr.send(formData);
    });
}

function updateRecordingUploadProgress(loaded, total) {
    const wrapper = document.getElementById("recordingUploadProgressWrapper");
    const bar = document.getElementById("recordingUploadProgressBar");
    const label = document.getElementById("recordingUploadProgressLabel");
    if (!wrapper || !bar) return;

    wrapper.classList.remove("d-none");

    const percent = total > 0 ? Math.round((loaded / total) * 100) : 0;
    bar.style.width = percent + "%";

    if (label) {
        label.textContent = `${formatFileSize(loaded)} / ${formatFileSize(total)} (${percent}%)`;
    }
}

function hideRecordingUploadProgress() {
    const wrapper = document.getElementById("recordingUploadProgressWrapper");
    if (wrapper) wrapper.classList.add("d-none");
}

async function uploadRecordingFiles(event) {
    const input = event.target;
    const files = input.files;
    if (!files || files.length === 0) return;

    const formData = new FormData();
    for (const file of files) {
        formData.append("files", file);
    }

    updateRecordingUploadProgress(0, 1);

    try {
        const result = await uploadRecordingsWithProgress(formData);
        console.log(result);

        if (result.uploaded.length === 0) {
            alert(I18N.alert_no_files_uploaded);
        }
    } catch (error) {
        console.error("Upload fehlgeschlagen:", error);
        alert(I18N.alert_upload_failed);
    } finally {
        input.value = "";
        hideRecordingUploadProgress();
        await loadRecordings();
        await refreshDashboard();
    }
}

// ------------------------------------------------------------
// Übungsmix (mehrere Stems zu einer Mehrkanal-Aufnahme kombinieren)
// ------------------------------------------------------------

const STEM_COMBINE_MAX_FILES = 8;
let stemCombineRowCount = 0;
let stemCombinePollTimer = null;

function addStemCombineRow() {
    if (stemCombineRowCount >= STEM_COMBINE_MAX_FILES) return;

    stemCombineRowCount++;
    const a = stemCombineRowCount * 2 - 1;
    const b = stemCombineRowCount * 2;

    const row = document.createElement("div");
    row.className = "mb-2";
    row.innerHTML = `
        <label class="form-label small mb-1">
            ${I18N.stem_combine_channel_label.replace("{a}", a).replace("{b}", b)}
        </label>
        <input type="file" class="form-control form-control-sm stem-combine-file-input" accept=".wav,.w64">
    `;

    document.getElementById("stem-combine-files").appendChild(row);

    const addButton = document.getElementById("btn-stem-combine-add-file");
    if (addButton) addButton.disabled = stemCombineRowCount >= STEM_COMBINE_MAX_FILES;
}

function resetStemCombineModal() {
    document.getElementById("stem-combine-name").value = "";
    document.getElementById("stem-combine-files").innerHTML = "";
    document.getElementById("stemCombineProgressWrapper").classList.add("d-none");
    document.getElementById("stemCombineError").classList.add("d-none");

    const submitButton = document.getElementById("btn-stem-combine-submit");
    if (submitButton) submitButton.disabled = false;

    const addButton = document.getElementById("btn-stem-combine-add-file");
    if (addButton) addButton.disabled = false;

    stemCombineRowCount = 0;
    addStemCombineRow();
    addStemCombineRow();
}

function showStemCombineError(message) {
    const box = document.getElementById("stemCombineError");
    box.textContent = message;
    box.classList.remove("d-none");
}

document.getElementById("btn-stem-combine-add-file").addEventListener("click", addStemCombineRow);

document.getElementById("btn-open-stem-combine").addEventListener("click", () => {
    const recordingsModalElement = document.getElementById("recordingsModal");
    bootstrap.Modal.getOrCreateInstance(recordingsModalElement).hide();

    resetStemCombineModal();

    const modalElement = document.getElementById("stemCombineModal");
    bootstrap.Modal.getOrCreateInstance(modalElement).show();
});

document.getElementById("stemCombineModal").addEventListener("hidden.bs.modal", () => {
    const recordingsModalElement = document.getElementById("recordingsModal");
    bootstrap.Modal.getOrCreateInstance(recordingsModalElement).show();
});

document.getElementById("btn-stem-combine-submit").addEventListener("click", submitStemCombine);

async function submitStemCombine() {
    const name = document.getElementById("stem-combine-name").value.trim();
    document.getElementById("stemCombineError").classList.add("d-none");

    if (!name) {
        showStemCombineError(I18N.stem_combine_name_required);
        return;
    }

    const files = Array.from(
        document.querySelectorAll("#stem-combine-files .stem-combine-file-input")
    )
        .map((input) => input.files[0])
        .filter((file) => !!file);

    if (files.length < 2) {
        showStemCombineError(I18N.stem_combine_files_required);
        return;
    }

    const formData = new FormData();
    formData.append("name", name);
    for (const file of files) {
        formData.append("files", file);
    }

    document.getElementById("btn-stem-combine-submit").disabled = true;

    let result;
    try {
        const response = await fetch("/api/recordings/combine", {
            method: "POST",
            body: formData,
        });
        result = await response.json();
    } catch (error) {
        console.error("Übungsmix-Upload fehlgeschlagen:", error);
        document.getElementById("btn-stem-combine-submit").disabled = false;
        showStemCombineError(I18N.stem_combine_failed);
        return;
    }

    if (!result.success) {
        document.getElementById("btn-stem-combine-submit").disabled = false;
        showStemCombineError(result.message || I18N.stem_combine_failed);
        return;
    }

    document.getElementById("stemCombineProgressWrapper").classList.remove("d-none");
    pollStemCombineStatus();
}

function pollStemCombineStatus() {
    if (stemCombinePollTimer) clearInterval(stemCombinePollTimer);

    stemCombinePollTimer = setInterval(async () => {
        let data;

        try {
            const response = await fetch("/api/recordings/combine/status");
            data = await response.json();
        } catch (error) {
            clearInterval(stemCombinePollTimer);
            stemCombinePollTimer = null;
            document.getElementById("btn-stem-combine-submit").disabled = false;
            document.getElementById("stemCombineProgressWrapper").classList.add("d-none");
            showStemCombineError(I18N.stem_combine_failed);
            return;
        }

        if (data.active) return;

        clearInterval(stemCombinePollTimer);
        stemCombinePollTimer = null;
        document.getElementById("stemCombineProgressWrapper").classList.add("d-none");
        document.getElementById("btn-stem-combine-submit").disabled = false;

        if (!data.success) {
            showStemCombineError(data.error || I18N.stem_combine_failed);
            return;
        }

        const modalElement = document.getElementById("stemCombineModal");
        bootstrap.Modal.getOrCreateInstance(modalElement).hide();

        await loadRecordings();
        await refreshDashboard();
    }, 300);
}

// ============================================================
// 11. UTILITY FUNCTIONS
// ============================================================

function formatDuration(seconds) {
    seconds = Math.round(seconds);
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(2) + " MB";
    return (bytes / 1024 / 1024 / 1024).toFixed(2) + " GB";
}

// ============================================================
// 11b. MUSIC PLAYER
// ============================================================

function updateMusicPlayer(data) {
    musicPlaying = data.music_playing;
    musicPaused = data.music_paused;

    updateMusicChannels(data);
    updateMusicStatus(data);
    updateMusicButtons(data);
    updateMusicSeek(data);

    const select = document.getElementById("music-channels");

    refreshPairFader(
        "music",
        select ? Number(select.value) : null,
        data.music_playing
    );
}

//
// Die Kanalauswahl sieht in beiden Karten gleich aus: Stereopaare ab
// dem ersten Kanal, immer ungerade beginnend (1+2, 3+4, ...). Genau
// deshalb laesst sich jedes waehlbare Paar am Pult auch koppeln - der
// Fall "2+3" kann gar nicht erst entstehen.
//
// Neu aufgebaut wird nur, wenn sich die Kanalzahl geaendert hat. Sonst
// wuerde die Auswahl bei jeder Statusabfrage zurueckspringen.
//
function buildChannelOptions(select, channels, preferred) {
    if (select.dataset.built === String(channels)) return false;

    select.innerHTML = "";

    for (let start = 1; start + 1 <= channels; start += 2) {
        const option = document.createElement("option");
        option.value = start;
        option.textContent = I18N.channel_option
            .replace("{a}", start)
            .replace("{b}", start + 1);
        select.appendChild(option);
    }

    select.dataset.built = String(channels);
    select.value = preferred;

    return true;
}

function updateMusicChannels(data) {
    const select = document.getElementById("music-channels");
    if (!select) return;

    //
    // Vorbelegt wird mit dem zuletzt genutzten Kanal - nur beim
    // Neuaufbau, damit eine Auswahl von Hand nicht ueberschrieben wird.
    //
    buildChannelOptions(
        select,
        data.audio_channels,
        data.music_preferred_start_channel
    );

    if (data.music_playing) {
        select.value = data.music_start_channel + 1;
    }

    select.disabled = isAudioBusy(data);

    select.onchange = () => {
        const vorher = pairFaders.music.start;
        const nachher = Number(select.value);

        setMusicChannelPreference(nachher);
        handlePairChange("music", vorher, nachher);
    };
}

async function setMusicChannelPreference(startChannel) {
    const response = await fetch("/api/music/channel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ start_channel: startChannel })
    });
    const result = await response.json();
    console.log(result);
}

function formatTrackLabel(data) {
    if (data.music_track_title) {
        return data.music_track_artist
            ? `${data.music_track_artist} - ${data.music_track_title}`
            : data.music_track_title;
    }

    return data.music_track || "-";
}

function updateMusicStatus(data) {
    const status = document.getElementById("player-status");
    if (status) {
        status.textContent = data.music_paused
            ? I18N.status_paused
            : (data.music_playing ? I18N.status_playing : I18N.status_stopped);
    }

    const title = document.getElementById("player-title");
    if (title) {
        title.textContent = data.music_playing ? formatTrackLabel(data) : "-";
    }

    const mode = document.getElementById("player-mode");
    if (mode) {
        mode.textContent = data.music_playing
            ? (data.music_folder_mode ? I18N.mode_folder : I18N.mode_single)
            : "-";
    }
}

function updateMusicButtons(data) {
    const stopButton = document.getElementById("btn-music-stop");
    if (stopButton) stopButton.disabled = !data.music_playing;

    const skipButton = document.getElementById("btn-music-skip");
    if (skipButton) skipButton.disabled = !data.music_playing || !data.music_folder_mode;

    const browseButton = document.getElementById("btn-music-browse");
    if (browseButton) browseButton.disabled = data.playback_active;

    const pauseButton = document.getElementById("btn-music-pause");
    if (pauseButton) {
        pauseButton.disabled = !data.music_playing;

        if (data.music_paused) {
            pauseButton.innerHTML = `<i class="bi bi-play-circle me-2"></i>${I18N.btn_resume}`;
        } else {
            pauseButton.innerHTML = `<i class="bi bi-pause-circle me-2"></i>${I18N.btn_pause}`;
        }
    }
}

async function toggleMusicPause() {
    if (musicPaused) {
        await resumeMusic();
    } else {
        await pauseMusic();
    }
}

async function pauseMusic() {
    const response = await fetch("/api/music/pause", { method: "POST" });
    const result = await response.json();
    console.log(result);
    await refreshDashboard();
}

async function resumeMusic() {
    const response = await fetch("/api/music/resume", { method: "POST" });
    const result = await response.json();
    console.log(result);
    await refreshDashboard();
}

function updateMusicSeek(data) {
    const slider = document.getElementById("music-seek");
    const positionLabel = document.getElementById("music-position");
    const durationLabel = document.getElementById("music-duration");
    if (!slider) return;

    const duration = data.music_duration || 0;

    slider.max = duration > 0 ? duration : 100;
    slider.disabled = !data.music_playing || duration <= 0;

    if (!musicSeekDragging) {
        slider.value = data.music_playing ? data.music_position : 0;
    }

    if (positionLabel) positionLabel.textContent = formatDuration(data.music_playing ? data.music_position : 0);
    if (durationLabel) durationLabel.textContent = formatDuration(duration);
}

async function seekMusic(position) {
    const response = await fetch("/api/music/seek", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ position })
    });
    const result = await response.json();
    console.log(result);
    await refreshDashboard();
}

const musicSeekSlider = document.getElementById("music-seek");
musicSeekSlider.addEventListener("mousedown", () => { musicSeekDragging = true; });
musicSeekSlider.addEventListener("touchstart", () => { musicSeekDragging = true; });
musicSeekSlider.addEventListener("change", async (event) => {
    musicSeekDragging = false;
    await seekMusic(Number(event.target.value));
});

function getSelectedMusicChannel() {
    const select = document.getElementById("music-channels");
    return select ? Number(select.value) : 1;
}

async function stopMusic() {
    const response = await fetch("/api/music/stop", { method: "POST" });
    const result = await response.json();
    console.log(result);
    await refreshDashboard();
}

async function skipMusic() {
    const response = await fetch("/api/music/skip", { method: "POST" });
    const result = await response.json();
    console.log(result);
    await refreshDashboard();
}

// ------------------------------------------------------------
// Musikbibliothek (Ordner-Browser im Modal)
// ------------------------------------------------------------

const musicModal = document.getElementById("musicModal");
musicModal.addEventListener("show.bs.modal", () => {
    selectedMusicFiles.clear();
    loadMusicBrowse("");
});

document.getElementById("btn-play-current-folder")
    .addEventListener("click", () => playMusicFolder(musicCurrentPath));

document.getElementById("btn-music-select-all")
    .addEventListener("click", selectAllMusicFiles);

document.getElementById("deleteSelectedMusicButton")
    .addEventListener("click", deleteSelectedMusicFiles);

async function loadMusicBrowse(path) {
    try {
        const response = await fetch(`/api/music/browse?path=${encodeURIComponent(path)}`);

        if (!response.ok) {
            throw new Error("API-Fehler");
        }

        const listing = await response.json();

        // Auswahl bezieht sich immer nur auf den gerade angezeigten
        // Ordner - beim Navigieren verschwinden die Checkboxen ja
        // ohnehin aus dem DOM.
        if (listing.path !== musicCurrentPath) {
            selectedMusicFiles.clear();
        }

        musicCurrentPath = listing.path;

        renderMusicBreadcrumb(listing.path);
        renderMusicList(listing);
        updateDeleteSelectedMusicButton();
    } catch (error) {
        console.error("Fehler beim Laden der Musikbibliothek:", error);
    }
}

function renderMusicBreadcrumb(path) {
    const breadcrumb = document.getElementById("musicBreadcrumb");
    breadcrumb.innerHTML = "";

    const segments = path ? path.split("/") : [];

    const rootItem = document.createElement("li");
    rootItem.className = "breadcrumb-item" + (segments.length === 0 ? " active" : "");

    if (segments.length === 0) {
        rootItem.textContent = I18N.music_root_breadcrumb;
    } else {
        const link = document.createElement("a");
        link.href = "#";
        link.textContent = I18N.music_root_breadcrumb;
        link.onclick = (event) => { event.preventDefault(); loadMusicBrowse(""); };
        rootItem.appendChild(link);
    }
    breadcrumb.appendChild(rootItem);

    let accumulated = "";

    segments.forEach((segment, index) => {
        accumulated = accumulated ? `${accumulated}/${segment}` : segment;
        const isLast = index === segments.length - 1;

        const item = document.createElement("li");
        item.className = "breadcrumb-item" + (isLast ? " active" : "");

        if (isLast) {
            item.textContent = segment;
        } else {
            const target = accumulated;
            const link = document.createElement("a");
            link.href = "#";
            link.textContent = segment;
            link.onclick = (event) => { event.preventDefault(); loadMusicBrowse(target); };
            item.appendChild(link);
        }

        breadcrumb.appendChild(item);
    });
}

function renderMusicList(listing) {
    const container = document.getElementById("musicList");
    container.innerHTML = "";

    if (listing.folders.length === 0 && listing.files.length === 0) {
        container.innerHTML = `<div class="text-muted text-center py-3">${I18N.no_music_files}</div>`;
        return;
    }

    listing.folders.forEach((folder) => {
        const childPath = listing.path ? `${listing.path}/${folder}` : folder;

        const item = document.createElement("div");
        item.className = "list-group-item d-flex justify-content-between align-items-center";
        item.innerHTML = `
            <span style="cursor: pointer;">
                <i class="bi bi-folder-fill me-2 text-warning"></i>${folder}
            </span>
            <button class="btn btn-outline-success btn-sm" title="${I18N.btn_play_folder_shuffle}">
                <i class="bi bi-shuffle"></i>
            </button>
        `;

        item.querySelector("span").onclick = () => loadMusicBrowse(childPath);
        item.querySelector("button").onclick = (event) => {
            event.stopPropagation();
            playMusicFolder(childPath);
        };

        container.appendChild(item);
    });

    listing.files.forEach((file) => {
        const filePath = listing.path ? `${listing.path}/${file}` : file;

        const item = document.createElement("div");
        item.className = "list-group-item d-flex justify-content-between align-items-center";
        item.innerHTML = `
            <div class="d-flex align-items-center gap-2">
                <input
                    class="form-check-input mt-0 music-file-checkbox"
                    type="checkbox"
                    data-path="${filePath}"
                    ${selectedMusicFiles.has(filePath) ? "checked" : ""}
                >
                <span><i class="bi bi-file-earmark-music me-2"></i>${file}</span>
            </div>
            <div class="btn-group btn-group-sm">
                <button class="btn btn-outline-primary btn-sm" title="${I18N.title_play_file}">
                    <i class="bi bi-play-fill"></i>
                </button>
                <button class="btn btn-outline-danger btn-sm" title="${I18N.title_delete}">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
        `;

        item.querySelector(".music-file-checkbox").onchange = (event) => {
            toggleMusicFileSelection(filePath, event.target.checked);
        };

        const buttons = item.querySelectorAll("button");
        buttons[0].onclick = () => playMusicFile(filePath);
        buttons[1].onclick = () => deleteMusicFile(filePath, file);

        container.appendChild(item);
    });
}

function toggleMusicFileSelection(path, selected) {
    if (selected) {
        selectedMusicFiles.add(path);
    } else {
        selectedMusicFiles.delete(path);
    }
    updateDeleteSelectedMusicButton();
}

function updateDeleteSelectedMusicButton() {
    const button = document.getElementById("deleteSelectedMusicButton");
    if (!button) return;

    button.disabled = selectedMusicFiles.size === 0;
    button.innerHTML = `
        <i class="bi bi-trash"></i>
        ${I18N.btn_delete_selected} (${selectedMusicFiles.size})
    `;
}

function selectAllMusicFiles() {
    document.querySelectorAll("#musicList .music-file-checkbox").forEach((checkbox) => {
        checkbox.checked = true;
        selectedMusicFiles.add(checkbox.dataset.path);
    });

    updateDeleteSelectedMusicButton();
}

async function deleteSelectedMusicFiles() {
    if (selectedMusicFiles.size === 0) return;

    if (!confirm(I18N.confirm_delete_music_multi.replace("{count}", selectedMusicFiles.size))) {
        return;
    }

    const response = await fetch("/api/music/delete-multi", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paths: Array.from(selectedMusicFiles) })
    });

    if (!response.ok) {
        alert(I18N.alert_music_files_delete_failed);
        return;
    }

    selectedMusicFiles.clear();
    await loadMusicBrowse(musicCurrentPath);
}

async function playMusicFolder(path) {
    const response = await fetch("/api/music/play-folder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, start_channel: getSelectedMusicChannel() })
    });
    const result = await response.json();
    console.log(result);

    if (!result.success) {
        alert(I18N.alert_playback_start_failed);
        return;
    }

    bootstrap.Modal.getOrCreateInstance(musicModal).hide();
    await refreshDashboard();
}

async function playMusicFile(path) {
    const response = await fetch("/api/music/play-file", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, start_channel: getSelectedMusicChannel() })
    });
    const result = await response.json();
    console.log(result);

    if (!result.success) {
        alert(I18N.alert_playback_start_failed);
        return;
    }

    bootstrap.Modal.getOrCreateInstance(musicModal).hide();
    await refreshDashboard();
}

async function deleteMusicFile(path, displayName) {
    if (!confirm(I18N.confirm_delete_file.replace("{name}", displayName))) return;

    const response = await fetch("/api/music/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path })
    });
    const result = await response.json();

    if (!result.success) {
        alert(I18N.alert_music_delete_failed);
        return;
    }

    await loadMusicBrowse(musicCurrentPath);
}

// ------------------------------------------------------------
// Ordner anlegen / Musik hochladen
// ------------------------------------------------------------

document.getElementById("btn-new-folder").addEventListener("click", createMusicFolder);
document.getElementById("music-upload-input").addEventListener("change", uploadMusicFiles);

async function createMusicFolder() {
    const name = prompt(I18N.prompt_new_folder_name);
    if (!name) return;

    const response = await fetch("/api/music/create-folder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: musicCurrentPath, name })
    });
    const result = await response.json();
    console.log(result);

    if (!result.success) {
        alert(I18N.alert_folder_create_failed);
        return;
    }

    await loadMusicBrowse(musicCurrentPath);
}

function uploadWithProgress(formData) {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", "/api/music/upload");

        xhr.upload.addEventListener("progress", (event) => {
            if (event.lengthComputable) {
                updateUploadProgress(event.loaded, event.total);
            }
        });

        xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                try {
                    resolve(JSON.parse(xhr.responseText));
                } catch (error) {
                    reject(error);
                }
            } else {
                reject(new Error(`Upload fehlgeschlagen (${xhr.status})`));
            }
        };

        xhr.onerror = () => reject(new Error("Netzwerkfehler beim Upload"));

        xhr.send(formData);
    });
}

function updateUploadProgress(loaded, total) {
    const wrapper = document.getElementById("uploadProgressWrapper");
    const bar = document.getElementById("uploadProgressBar");
    const label = document.getElementById("uploadProgressLabel");
    if (!wrapper || !bar) return;

    wrapper.classList.remove("d-none");

    const percent = total > 0 ? Math.round((loaded / total) * 100) : 0;
    bar.style.width = percent + "%";

    if (label) {
        label.textContent = `${formatFileSize(loaded)} / ${formatFileSize(total)} (${percent}%)`;
    }
}

function hideUploadProgress() {
    const wrapper = document.getElementById("uploadProgressWrapper");
    if (wrapper) wrapper.classList.add("d-none");
}

async function uploadMusicFiles(event) {
    const input = event.target;
    const files = input.files;
    if (!files || files.length === 0) return;

    const formData = new FormData();
    formData.append("path", musicCurrentPath);
    for (const file of files) {
        formData.append("files", file);
    }

    updateUploadProgress(0, 1);

    try {
        const result = await uploadWithProgress(formData);
        console.log(result);

        if (result.count === 0) {
            alert(I18N.alert_no_files_uploaded);
        }
    } catch (error) {
        console.error("Upload fehlgeschlagen:", error);
        alert(I18N.alert_upload_failed);
    } finally {
        input.value = "";
        hideUploadProgress();
        await loadMusicBrowse(musicCurrentPath);
    }
}

// ============================================================
// 11c. SYSTEM
// ============================================================

async function shutdownSystem() {
    if (!confirm(I18N.shutdown_confirm)) {
        return;
    }

    const button = document.getElementById("btn-shutdown");
    if (button) {
        button.disabled = true;
        button.innerHTML = `<i class="bi bi-power me-2"></i>${I18N.btn_shutdown_progress}`;
    }

    const response = await fetch("/api/system/shutdown", { method: "POST" });
    const result = await response.json();
    console.log(result);

    if (!result.success) {
        alert(I18N.shutdown_failed);
        if (button) {
            button.disabled = false;
            button.innerHTML = `<i class="bi bi-power me-2"></i>${I18N.btn_shutdown}`;
        }
    }
}

// ============================================================
// 12. INITIALIZATION
// ============================================================

async function initializeDashboard() {
    await loadAudioDevices();
    await refreshDashboard();
    document.getElementById("audio-rescan").addEventListener("click", rescanAudioDevices);
}

initializeDashboard();
setInterval(refreshDashboard, 1000);
setInterval(pollLevels, 150);

// ============================================================
// 13. EINSTELLUNGEN (Sprache, Port, WLAN, Bridge)
// ============================================================

const settingsModal = document.getElementById("settingsModal");
settingsModal.addEventListener("show.bs.modal", loadSettings);

async function loadSettings() {
    document.getElementById("btn-settings-restart").classList.add("d-none");

    try {
        const response = await fetch("/api/settings");
        const data = await response.json();

        document.getElementById("settings-language").value = data.language;
        document.getElementById("settings-sample-rate").value = data.sample_rate;
        document.getElementById("settings-port").value = data.port;
        document.getElementById("settings-recording-prefix").value = data.record_name_prefix;

        document.getElementById("settings-pin-current-field")
            .classList.toggle("d-none", !data.pin_protected);
        document.getElementById("settings-pin-current").value = "";
        document.getElementById("settings-pin-new").value = "";
        document.getElementById("settings-pin-new-confirm").value = "";

        applyWlanSettings(data.wlan);
        applyConsoleHost(data);
        applyFadersAutolock(data.faders_autolock);
    } catch (error) {
        console.error("Fehler beim Laden der Einstellungen:", error);
    }

    await loadUpdateInfo();
    await loadDiagnosticsStatus();
}

// ------------------------------------------------------------
// Diagnose-Aufzeichnung
// ------------------------------------------------------------

async function loadDiagnosticsStatus() {
    const toggle = document.getElementById("settings-diagnostics-toggle");
    const download = document.getElementById("btn-diagnostics-download");
    const size = document.getElementById("settings-diagnostics-size");
    if (!toggle || !download) return;

    try {
        const status = await (await fetch("/api/diagnostics/status")).json();

        toggle.checked = status.enabled;

        //
        // Herunterladen nur anbieten, wenn auch etwas drinsteht - ein
        // Knopf, der eine leere Datei liefert, verwirrt nur.
        //
        download.classList.toggle("disabled", status.size === 0);

        if (size) {
            size.textContent = status.size > 0
                ? formatFileSize(status.size)
                : I18N.settings_diagnostics_empty;
        }
    } catch (error) {
        console.error("Diagnose-Status konnte nicht geladen werden:", error);
    }
}

document.getElementById("settings-diagnostics-toggle")
    .addEventListener("change", async (event) => {
        const enabled = event.target.checked;

        try {
            const result = await (await fetch("/api/diagnostics", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ enabled }),
            })).json();

            if (!result.success) {
                event.target.checked = !enabled;
                alert(I18N.alert_change_failed);
                return;
            }
        } catch (error) {
            console.error("Diagnose konnte nicht umgeschaltet werden:", error);
            event.target.checked = !enabled;
            return;
        }

        await loadDiagnosticsStatus();
    });

// ------------------------------------------------------------
// Update über USB-Stick
// ------------------------------------------------------------

let updatePollTimer = null;
let updatePackageName = "";

//
// Steht auf true, sobald ein abgeschlossenes Update-Ergebnis im Modal
// steht. Beim Schliessen wird es quittiert - sonst begruesst einen
// "Update erfolgreich" noch Tage spaeter.
//
let updateResultShown = false;

async function loadUpdateInfo() {
    const packageBox = document.getElementById("settings-update-package");
    const button = document.getElementById("btn-settings-update");
    if (!packageBox || !button) return;

    try {
        const response = await fetch("/api/update/info");
        const data = await response.json();

        document.getElementById("settings-update-version").textContent = data.version || "-";
        updatePackageName = data.package || "";

        if (data.package) {
            packageBox.className = "small mb-2 text-success";
            packageBox.textContent = I18N.settings_update_found
                .replace("{name}", data.package)
                .replace("{size}", formatFileSize(data.size));
            button.disabled = false;
        } else {
            packageBox.className = "small mb-2 text-body-secondary";
            packageBox.textContent = data.usb_connected
                ? I18N.settings_update_no_package
                : I18N.settings_update_no_usb;
            button.disabled = true;
        }

        //
        // Ein Update, das beim letzten Öffnen lief, kann inzwischen
        // durch sein - Ergebnis anzeigen statt es zu verschlucken.
        //
        if (data.status && data.status.state !== "idle") {
            showUpdateResult(data.status);
        }
    } catch (error) {
        console.error("Fehler beim Laden der Update-Informationen:", error);
    }
}

function updateStepLabel(status) {
    if (status.state === "rolling_back") {
        return I18N.settings_update_step_rueckfall;
    }

    const key = "settings_update_step_" + (status.step || "start")
        .replace(/ü/g, "ue")
        .replace(/ä/g, "ae")
        .replace(/ö/g, "oe");

    return I18N[key] || I18N.settings_update_running;
}

function showUpdateResult(status) {
    const box = document.getElementById("settings-update-result");
    if (!box) return;

    if (status.state === "running" || status.state === "rolling_back") {
        box.classList.add("d-none");
        return;
    }

    const style = {
        success: "alert-success",
        rolled_back: "alert-warning",
        failed: "alert-danger",
    }[status.state];

    if (!style) {
        box.classList.add("d-none");
        return;
    }

    box.className = `alert ${style} py-2 px-3 small mt-3`;
    box.textContent = status.message || I18N.settings_update_failed;
    box.classList.remove("d-none");

    updateResultShown = true;
}

//
// Beim Schliessen des Modals gilt das Ergebnis als gesehen. Der Server
// merkt sich dazu den Zeitstempel; ein spaeteres Update hat einen
// anderen und wird deshalb wieder angezeigt.
//
settingsModal.addEventListener("hidden.bs.modal", async () => {
    if (!updateResultShown) return;

    updateResultShown = false;

    const box = document.getElementById("settings-update-result");
    if (box) box.classList.add("d-none");

    try {
        await fetch("/api/update/acknowledge", { method: "POST" });
    } catch (error) {
        console.error("Update-Ergebnis konnte nicht quittiert werden:", error);
    }
});

document
    .getElementById("btn-settings-update")
    .addEventListener("click", () => startUpdate("usb"));

//
// Der Online-Knopf braucht keinen Stick und bleibt deshalb immer
// bedienbar. Ob wirklich Internet da ist, laesst sich von hier aus
// nicht sagen - der Versuch meldet im Zweifel selbst, dass die
// Verbindung fehlt.
//
document
    .getElementById("btn-settings-update-online")
    .addEventListener("click", () => startUpdate("github"));

//
// Beide Knoepfe gehoeren zusammen: Waehrend ein Update laeuft, darf
// keiner von beiden noch einmal ausloesen.
//
function setUpdateButtons(disabled) {
    ["btn-settings-update", "btn-settings-update-online"].forEach((id) => {
        const button = document.getElementById(id);
        if (button) button.disabled = disabled;
    });
}

//
// Nach einem Fehlschlag darf der USB-Knopf nur zurueckkommen, wenn
// ueberhaupt ein Paket auf dem Stick liegt - sonst laedt er zu einem
// Klick ein, der nichts tun kann.
//
function restoreUpdateButtons() {
    setUpdateButtons(false);

    const usb = document.getElementById("btn-settings-update");
    if (usb) usb.disabled = !updatePackageName;
}

async function startUpdate(source) {
    if (source === "usb" && !updatePackageName) return;

    const frage = source === "github"
        ? I18N.settings_update_confirm_online
        : I18N.settings_update_confirm.replace("{name}", updatePackageName);

    if (!confirm(frage)) return;

    const result = document.getElementById("settings-update-result");

    setUpdateButtons(true);
    result.classList.add("d-none");
    updateResultShown = false;

    let response;
    try {
        response = await (await fetch("/api/update/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ source }),
        })).json();
    } catch (error) {
        console.error("Update konnte nicht gestartet werden:", error);
        restoreUpdateButtons();
        showUpdateResult({ state: "failed", message: I18N.settings_update_failed });
        return;
    }

    if (!response.success) {
        restoreUpdateButtons();
        showUpdateResult({ state: "failed", message: response.message });
        return;
    }

    showUpdateProgress(I18N.settings_update_step_start);
    pollUpdateStatus();
}

function showUpdateProgress(label) {
    const wrapper = document.getElementById("settings-update-progress");
    const text = document.getElementById("settings-update-progress-label");

    if (text) text.textContent = label;
    if (wrapper) wrapper.classList.remove("d-none");
}

function hideUpdateProgress() {
    const wrapper = document.getElementById("settings-update-progress");
    if (wrapper) wrapper.classList.add("d-none");
}

function pollUpdateStatus() {
    if (updatePollTimer) clearInterval(updatePollTimer);

    //
    // Der Dienst startet sich mitten im Update selbst neu. Abgerissene
    // Anfragen sind hier also der Normalfall und kein Fehler - einfach
    // weiterfragen, bis er wieder antwortet. Deshalb steht hier auch
    // kein Abbruch nach n Fehlversuchen: aufzugeben, während der Pi
    // gerade neu startet, wäre genau das Falsche.
    //
    updatePollTimer = setInterval(async () => {
        let status;

        try {
            status = await (await fetch("/api/update/status")).json();
        } catch (error) {
            showUpdateProgress(I18N.settings_update_reconnecting);
            return;
        }

        if (status.state === "running" || status.state === "rolling_back") {
            showUpdateProgress(updateStepLabel(status));
            return;
        }

        clearInterval(updatePollTimer);
        updatePollTimer = null;

        hideUpdateProgress();
        showUpdateResult(status);

        //
        // Nach einem erfolgreichen Update läuft eine neue Fassung -
        // die Seite muss neu geladen werden, damit JavaScript und
        // Übersetzungen dazu passen.
        //
        if (status.state === "success") {
            setTimeout(() => window.location.reload(), 4000);
        } else {
            restoreUpdateButtons();
        }
    }, 1500);
}

document.querySelectorAll(".pin-input").forEach((input) => {
    input.addEventListener("input", () => {
        input.value = input.value.replace(/\D/g, "").slice(0, 4);
    });
});

// ------------------------------------------------------------
// PIN-Schutz: Abfrage vor dem Öffnen, Ändern im Modal selbst
// ------------------------------------------------------------

const btnSettings = document.getElementById("btn-settings");
const settingsPinModalEl = document.getElementById("settingsPinModal");
const settingsPinModal = bootstrap.Modal.getOrCreateInstance(settingsPinModalEl);
let pinVerifiedPendingOpen = false;

btnSettings.addEventListener("click", openSettingsGate);

async function openSettingsGate() {
    let protectedByPin = false;

    try {
        const response = await fetch("/api/settings/pin/status");
        const data = await response.json();
        protectedByPin = Boolean(data.protected);
    } catch (error) {
        console.error("Fehler beim Prüfen des PIN-Schutzes:", error);
    }

    if (protectedByPin) {
        document.getElementById("settings-pin-input").value = "";
        document.getElementById("settings-pin-error").classList.add("d-none");
        settingsPinModal.show();
    } else {
        bootstrap.Modal.getOrCreateInstance(settingsModal).show();
    }
}

settingsPinModalEl.addEventListener("hidden.bs.modal", () => {
    if (pinVerifiedPendingOpen) {
        pinVerifiedPendingOpen = false;
        bootstrap.Modal.getOrCreateInstance(settingsModal).show();
    }
});

document.getElementById("btn-settings-pin-confirm").addEventListener("click", confirmSettingsPin);
document.getElementById("settings-pin-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter") confirmSettingsPin();
});

async function confirmSettingsPin() {
    const pin = document.getElementById("settings-pin-input").value;

    const response = await fetch("/api/settings/pin/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin })
    });
    const result = await response.json();

    if (!result.success) {
        document.getElementById("settings-pin-error").classList.remove("d-none");
        return;
    }

    pinVerifiedPendingOpen = true;
    settingsPinModal.hide();
}

document.getElementById("btn-settings-pin-save").addEventListener("click", saveSettingsPin);

async function saveSettingsPin() {
    const currentPin = document.getElementById("settings-pin-current").value;
    const newPin = document.getElementById("settings-pin-new").value;
    const newPinConfirm = document.getElementById("settings-pin-new-confirm").value;

    if (!/^\d{4}$/.test(newPin)) {
        alert(I18N.alert_settings_pin_invalid);
        return;
    }

    if (newPin !== newPinConfirm) {
        alert(I18N.alert_settings_pin_mismatch);
        return;
    }

    const response = await fetch("/api/settings/pin/change", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_pin: currentPin, new_pin: newPin })
    });
    const result = await response.json();

    if (!result.success) {
        alert(I18N.alert_settings_change_failed.replace("{message}", result.message || ""));
        return;
    }

    alert(I18N.settings_saved);

    await loadSettings();
}

function applyWlanSettings(wlan) {
    const unavailable = document.getElementById("settings-wlan-unavailable");
    const sections = document.getElementById("settings-wlan-sections");

    if (!wlan || !wlan.available) {
        unavailable.classList.remove("d-none");
        sections.classList.add("d-none");
        return;
    }

    unavailable.classList.add("d-none");
    sections.classList.remove("d-none");

    toggleConfiguredSection("home", wlan.home_ssid);
    if (wlan.home_ssid) {
        document.getElementById("settings-home-ssid").value = wlan.home_ssid;
        document.getElementById("settings-home-password").value = "";
        document.getElementById("settings-home-password-confirm").value = "";
    }

    toggleConfiguredSection("ap", wlan.ap_ssid);
    if (wlan.ap_ssid) {
        document.getElementById("settings-ap-ssid").value = wlan.ap_ssid;
        document.getElementById("settings-ap-password").value = "";
        document.getElementById("settings-ap-password-confirm").value = "";
    }

    const bridgeNotConfigured = document.getElementById("settings-bridge-not-configured");
    const bridgeField = document.getElementById("settings-bridge-field");

    if (wlan.bridge_configured) {
        bridgeNotConfigured.classList.add("d-none");
        bridgeField.classList.remove("d-none");
        document.getElementById("settings-bridge-toggle").checked = wlan.bridge_enabled;
    } else {
        bridgeNotConfigured.classList.remove("d-none");
        bridgeField.classList.add("d-none");
    }

    const accessNotConfigured = document.getElementById("settings-console-access-not-configured");
    const accessField = document.getElementById("settings-console-access-field");

    if (wlan.console_access_configured) {
        accessNotConfigured.classList.add("d-none");
        accessField.classList.remove("d-none");
        document.getElementById("settings-console-access-toggle").checked =
            wlan.console_access_enabled;
    } else {
        accessNotConfigured.classList.remove("d-none");
        accessField.classList.add("d-none");
    }

    //
    // Die beiden IPs zeigen wir nur, wenn der Weg übers Heimnetz aktiv
    // ist - beim Access-Point-Weg trägt man in der App die Konsolen-IP
    // direkt ein, da gibt es keine Weiterleitung.
    //
    const ipBox = document.getElementById("settings-console-access-ips");
    const waitingBox = document.getElementById("settings-console-access-waiting");

    const ready = wlan.console_access_enabled && wlan.console_ip && wlan.home_ip;

    ipBox.classList.toggle("d-none", !ready);
    waitingBox.classList.toggle(
        "d-none",
        !(wlan.console_access_enabled && !ready)
    );

    if (ready) {
        document.getElementById("settings-app-ip-value").textContent = wlan.home_ip;
        document.getElementById("settings-console-ip-value").textContent = wlan.console_ip;
    }
}

//
// Zeigt, welche IP fuer das Pult benutzt wird und woher sie stammt -
// von Hand eingetragen, am Pi angemeldet oder im Netz gefunden. Ohne
// diese Rueckmeldung raet man beim Eintragen ins Blaue.
//
function applyConsoleHost(data) {
    const field = document.getElementById("settings-console-host");
    const found = document.getElementById("settings-console-host-found");

    if (!field || !found) return;

    field.value = data.console_ip_manual || "";

    if (!data.console_host) {
        found.className = "small mt-1 text-body-secondary";
        found.textContent = I18N.settings_console_host_none;
        return;
    }

    const key = "settings_console_host_" + data.console_host_source;

    found.className = "small mt-1 text-success";
    found.textContent = (I18N[key] || "{ip}").replace("{ip}", data.console_host);
}

document
    .getElementById("btn-settings-console-host")
    .addEventListener("click", saveConsoleHost);

async function saveConsoleHost() {
    const field = document.getElementById("settings-console-host");
    const found = document.getElementById("settings-console-host-found");

    const button = document.getElementById("btn-settings-console-host");

    button.disabled = true;

    try {
        const response = await fetch("/api/console/host", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ip: field.value.trim() }),
        });

        const data = await response.json();

        if (!data.success) {
            found.className = "small mt-1 text-danger";
            found.textContent = data.message || I18N.settings_console_host_invalid;
            return;
        }

        //
        // Einstellungen neu laden: Erst danach steht fest, welche IP
        // jetzt tatsaechlich benutzt wird - beim Leeren des Feldes
        // greift ja wieder die Automatik.
        //
        const settings = await (await fetch("/api/settings")).json();
        applyConsoleHost(settings);

    } catch (error) {
        console.error("Pult-IP konnte nicht gespeichert werden:", error);
        found.className = "small mt-1 text-danger";
        found.textContent = I18N.settings_console_host_invalid;
    } finally {
        button.disabled = false;
    }
}

// ------------------------------------------------------------
// Automatische Sperre der Kanalzuege
// ------------------------------------------------------------

function applyFadersAutolock(einstellung) {
    if (!einstellung) return;

    const toggle = document.getElementById("settings-faders-autolock-toggle");
    const seconds = document.getElementById("settings-faders-autolock-seconds");

    if (!toggle || !seconds) return;

    toggle.checked = einstellung.enabled;
    seconds.value = einstellung.seconds;
    seconds.disabled = !einstellung.enabled;

    document.getElementById("settings-faders-autolock-result").textContent = "";
}

document
    .getElementById("settings-faders-autolock-toggle")
    .addEventListener("change", (event) => {
        //
        // Das Feld nur ausgrauen, nicht leeren - der gemerkte Wert
        // soll beim Wiedereinschalten noch dastehen.
        //
        document.getElementById("settings-faders-autolock-seconds").disabled =
            !event.target.checked;
    });

document
    .getElementById("btn-settings-faders-autolock")
    .addEventListener("click", saveFadersAutolock);

async function saveFadersAutolock() {
    const toggle = document.getElementById("settings-faders-autolock-toggle");
    const seconds = document.getElementById("settings-faders-autolock-seconds");
    const result = document.getElementById("settings-faders-autolock-result");

    const button = document.getElementById("btn-settings-faders-autolock");

    button.disabled = true;

    try {
        const response = await fetch("/api/settings/faders-autolock", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                enabled: toggle.checked,
                seconds: parseInt(seconds.value, 10) || 0,
            }),
        });

        const data = await response.json();

        if (!data.success) {
            result.className = "small mt-1 text-danger";
            result.textContent = data.message;
            return;
        }

        //
        // Sofort wirksam machen, ohne die Seite neu zu laden: Die
        // Fader-Karte liest ihre Einstellung beim Laden aus der Seite,
        // also hier dasselbe Objekt nachziehen und die laufende Frist
        // neu setzen.
        //
        fadersAutolock.enabled = data.faders_autolock.enabled;
        fadersAutolock.seconds = data.faders_autolock.seconds;

        resetFaderAutolock();

        applyFadersAutolock(data.faders_autolock);

        result.className = "small mt-1 text-success";
        result.textContent = I18N.settings_faders_autolock_saved;

    } catch (error) {
        console.error("Automatische Sperre konnte nicht gespeichert werden:", error);
    } finally {
        button.disabled = false;
    }
}

function toggleConfiguredSection(prefix, configured) {
    document.getElementById(`settings-${prefix}-not-configured`)
        .classList.toggle("d-none", Boolean(configured));
    document.getElementById(`settings-${prefix}-fields`)
        .classList.toggle("d-none", !configured);
}

// ------------------------------------------------------------
// Sprache
// ------------------------------------------------------------

document.getElementById("btn-settings-language-save").addEventListener("click", saveLanguage);

async function saveLanguage() {
    const language = document.getElementById("settings-language").value;

    const response = await fetch("/api/settings/language", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ language })
    });
    const result = await response.json();

    if (!result.success) {
        alert(I18N.alert_change_failed);
        return;
    }

    window.location.reload();
}

// ------------------------------------------------------------
// Mischpult-Samplerate
// ------------------------------------------------------------

document.getElementById("btn-settings-sample-rate-save").addEventListener("click", saveSampleRate);

async function saveSampleRate() {
    const sample_rate = Number(document.getElementById("settings-sample-rate").value);

    const response = await fetch("/api/settings/sample_rate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sample_rate })
    });
    const result = await response.json();

    if (!result.success) {
        alert(I18N.alert_change_failed);
        return;
    }

    alert(I18N.settings_saved);
}

// ------------------------------------------------------------
// Port
// ------------------------------------------------------------

document.getElementById("btn-settings-port-save").addEventListener("click", savePort);
document.getElementById("btn-settings-restart").addEventListener("click", restartService);

async function savePort() {
    const port = Number(document.getElementById("settings-port").value);

    const response = await fetch("/api/settings/port", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ port })
    });
    const result = await response.json();

    if (!result.success) {
        alert(I18N.alert_change_failed);
        return;
    }

    alert(I18N.settings_saved_restart_needed);
    document.getElementById("btn-settings-restart").classList.remove("d-none");
}

async function restartService() {
    if (!confirm(I18N.confirm_restart)) return;

    const newPort = Number(document.getElementById("settings-port").value);

    const response = await fetch("/api/system/restart", { method: "POST" });
    const result = await response.json();
    console.log(result);

    if (!result.success) {
        alert(I18N.alert_change_failed);
        return;
    }

    setTimeout(() => {
        window.location.href = `${window.location.protocol}//${window.location.hostname}:${newPort}/`;
    }, 5000);
}

// ------------------------------------------------------------
// Aufnahmename
// ------------------------------------------------------------

document.getElementById("btn-settings-recording-save").addEventListener("click", saveRecordingPrefix);

async function saveRecordingPrefix() {
    const prefix = document.getElementById("settings-recording-prefix").value;

    const response = await fetch("/api/settings/recording", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prefix })
    });
    const result = await response.json();

    if (!result.success) {
        alert(I18N.alert_change_failed);
        return;
    }

    alert(I18N.settings_saved);
}

// ------------------------------------------------------------
// WLAN: Heimnetz / Access Point / Bridge
// ------------------------------------------------------------

document.getElementById("btn-settings-home-save").addEventListener("click", saveHomeWifi);
document.getElementById("btn-settings-ap-save").addEventListener("click", saveApWifi);
document.getElementById("settings-bridge-toggle").addEventListener("change", toggleBridge);
document.getElementById("settings-console-access-toggle")
    .addEventListener("change", toggleConsoleAccess);

document.querySelectorAll(".settings-password-toggle").forEach((button) => {
    button.addEventListener("click", () => togglePasswordVisibility(button));
});

function togglePasswordVisibility(button) {
    const input = document.getElementById(button.dataset.target);
    const icon = button.querySelector("i");

    if (input.type === "password") {
        input.type = "text";
        icon.classList.remove("bi-eye");
        icon.classList.add("bi-eye-slash");
    } else {
        input.type = "password";
        icon.classList.remove("bi-eye-slash");
        icon.classList.add("bi-eye");
    }
}

async function saveHomeWifi() {
    const ssid = document.getElementById("settings-home-ssid").value;
    const password = document.getElementById("settings-home-password").value;
    const passwordConfirm = document.getElementById("settings-home-password-confirm").value;

    if (password !== passwordConfirm) {
        alert(I18N.alert_password_mismatch);
        return;
    }

    if (!confirm(I18N.confirm_home_wifi_change)) return;

    await submitWifiChange("/api/settings/wifi/home", ssid, password);
}

async function saveApWifi() {
    const ssid = document.getElementById("settings-ap-ssid").value;
    const password = document.getElementById("settings-ap-password").value;
    const passwordConfirm = document.getElementById("settings-ap-password-confirm").value;

    if (password !== passwordConfirm) {
        alert(I18N.alert_password_mismatch);
        return;
    }

    if (!confirm(I18N.confirm_ap_wifi_change)) return;

    await submitWifiChange("/api/settings/wifi/ap", ssid, password);
}

async function submitWifiChange(url, ssid, password) {
    const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ssid, password })
    });
    const result = await response.json();

    if (!result.success) {
        alert(I18N.alert_settings_change_failed.replace("{message}", result.message || ""));
        return;
    }

    alert(I18N.settings_saved);
    await loadSettings();
}

async function toggleBridge(event) {
    const enabled = event.target.checked;
    const confirmText = enabled ? I18N.confirm_bridge_on : I18N.confirm_bridge_off;

    if (!confirm(confirmText)) {
        event.target.checked = !enabled;
        return;
    }

    const response = await fetch("/api/settings/bridge", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled })
    });
    const result = await response.json();

    if (!result.success) {
        alert(I18N.alert_settings_change_failed.replace("{message}", result.message || ""));
        event.target.checked = !enabled;
        return;
    }

    alert(I18N.settings_saved);
    // Schließt sich mit der Heimnetz-Freigabe aus - deren Schalter
    // kann sich dabei im Hintergrund mit geändert haben.
    await loadSettings();
}

async function toggleConsoleAccess(event) {
    const enabled = event.target.checked;
    const confirmText = enabled
        ? I18N.confirm_console_access_on
        : I18N.confirm_console_access_off;

    if (!confirm(confirmText)) {
        event.target.checked = !enabled;
        return;
    }

    const response = await fetch("/api/settings/console_access", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled })
    });
    const result = await response.json();

    if (!result.success) {
        alert(I18N.alert_settings_change_failed.replace("{message}", result.message || ""));
        event.target.checked = !enabled;
        return;
    }

    alert(I18N.settings_saved);

    //
    // Schließt sich mit dem Access-Point-Weg aus - dessen Schalter kann
    // sich dabei im Hintergrund mit geändert haben. Außerdem braucht
    // die Konsole einen Moment für ihre DHCP-Lease, die IPs erscheinen
    // also erst beim nächsten Öffnen bzw. Nachladen.
    //
    await loadSettings();
}

// ============================================================
// 14. BLUETOOTH
// ============================================================

// Schnelle Werte (streaming/device-name) kommen mit jedem 1s-
// Statuspoll (siehe updateStatus/lastStatusData). Power/Discoverable/
// gekoppeltes Gerät erfordern dagegen einen bluetoothctl-Aufruf im
// Backend - dafür ein eigener, langsamerer Poll, damit nicht jede
// Sekunde unnötig bluetoothctl aufgerufen wird.
let bluetoothSlowStatus = {
    available: false,
    powered: false,
    discoverable: false,
    paired_devices: [],
    preferred_start_channel: 1,
};

function updateBluetooth(data) {
    updateBluetoothChannels(data);
    updateBluetoothStatusText(data);
    updateBluetoothControlsState(data);

    const select = document.getElementById("bluetooth-channels");

    refreshPairFader(
        "bluetooth",
        select ? Number(select.value) : null,
        data.bluetooth_streaming
    );
}

function updateBluetoothChannels(data) {
    const select = document.getElementById("bluetooth-channels");
    if (!select) return;

    buildChannelOptions(
        select,
        data.audio_channels,
        bluetoothSlowStatus.preferred_start_channel || 1
    );

    select.onchange = () => {
        const vorher = pairFaders.bluetooth.start;
        const nachher = Number(select.value);

        setBluetoothChannelPreference(nachher);
        handlePairChange("bluetooth", vorher, nachher);
    };
}

function updateBluetoothStatusText(data) {
    const label = document.getElementById("bluetooth-status");
    if (!label) return;

    if (data.bluetooth_streaming) {
        label.textContent = I18N.bluetooth_status_connected.replace("{name}", data.bluetooth_device_name || "");
    } else if (bluetoothSlowStatus.discoverable) {
        label.textContent = I18N.bluetooth_status_pairing;
    } else if (bluetoothSlowStatus.powered) {
        label.textContent = I18N.bluetooth_status_ready;
    } else {
        label.textContent = I18N.bluetooth_status_off;
    }
}

function updateBluetoothControlsState(data) {
    const toggle = document.getElementById("bluetooth-power-toggle");
    if (toggle && document.activeElement !== toggle) {
        toggle.checked = bluetoothSlowStatus.powered;
    }

    // Anders als bei Aufnahme-/Musikkanälen ist die Bluetooth-
    // Kanalwahl auch während einer laufenden Wiedergabe änderbar -
    // BluetoothPlayer verbindet dafür selbst kurz neu (siehe
    // player/bluetooth_player.py), die Hardware muss also nicht erst
    // freigegeben werden.
    const select = document.getElementById("bluetooth-channels");
    if (select) select.disabled = !bluetoothSlowStatus.powered;

    const pairButton = document.getElementById("btn-bluetooth-pair");
    if (pairButton) pairButton.disabled = !bluetoothSlowStatus.powered;
}

function renderBluetoothDevicesList(devices) {
    const container = document.getElementById("bluetoothDevicesList");
    if (!container) return;

    container.innerHTML = "";

    if (!devices || devices.length === 0) {
        const empty = document.createElement("div");
        empty.className = "text-muted small p-2";
        empty.textContent = I18N.bluetooth_no_paired_devices;
        container.appendChild(empty);
        return;
    }

    for (const device of devices) {
        const item = document.createElement("div");
        item.className = "list-group-item d-flex justify-content-between align-items-center gap-2";

        const info = document.createElement("div");
        info.className = "text-break";

        const name = document.createElement("div");
        name.textContent = device.name;
        info.appendChild(name);

        if (device.connected) {
            const badge = document.createElement("span");
            badge.className = "badge text-bg-success";
            badge.textContent = I18N.badge_bluetooth_connected;
            info.appendChild(badge);
        }

        item.appendChild(info);

        const actions = document.createElement("div");
        actions.className = "btn-group btn-group-sm flex-shrink-0";

        if (device.connected) {
            const disconnectButton = document.createElement("button");
            disconnectButton.className = "btn btn-outline-warning";
            disconnectButton.title = I18N.title_bluetooth_disconnect_device;
            disconnectButton.innerHTML = '<i class="bi bi-bluetooth"></i>';
            disconnectButton.addEventListener("click", () => disconnectBluetoothDevice(device.mac, device.name));
            actions.appendChild(disconnectButton);
        }

        const forgetButton = document.createElement("button");
        forgetButton.className = "btn btn-outline-danger";
        forgetButton.title = I18N.title_bluetooth_forget_device;
        forgetButton.innerHTML = '<i class="bi bi-trash"></i>';
        forgetButton.addEventListener("click", () => forgetBluetoothDevice(device.mac, device.name));
        actions.appendChild(forgetButton);

        item.appendChild(actions);

        container.appendChild(item);
    }
}

async function refreshBluetoothStatus() {
    try {
        const response = await fetch("/api/bluetooth/status");
        const data = await response.json();

        bluetoothSlowStatus = data;

        const unavailable = document.getElementById("bluetooth-unavailable");
        const fields = document.getElementById("bluetooth-fields");
        if (unavailable && fields) {
            unavailable.classList.toggle("d-none", data.available);
            fields.classList.toggle("d-none", !data.available);
        }

        renderBluetoothDevicesList(data.paired_devices);
        updateBluetoothStatusText(lastStatusData);
    } catch (error) {
        console.error("Fehler beim Laden des Bluetooth-Status:", error);
    }
}

setInterval(refreshBluetoothStatus, 3000);
refreshBluetoothStatus();

document.getElementById("bluetooth-power-toggle").addEventListener("change", toggleBluetoothPower);

async function toggleBluetoothPower(event) {
    const enabled = event.target.checked;

    const response = await fetch("/api/bluetooth/power", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled })
    });
    const result = await response.json();

    if (!result.success) {
        alert(I18N.alert_settings_change_failed.replace("{message}", result.message || ""));
        event.target.checked = !enabled;
        return;
    }

    await refreshBluetoothStatus();
}

async function startBluetoothPairing() {
    const response = await fetch("/api/bluetooth/pair", { method: "POST" });
    const result = await response.json();

    if (!result.success) {
        alert(I18N.alert_settings_change_failed.replace("{message}", result.message || ""));
        return;
    }

    alert(I18N.alert_bluetooth_pairing_started);
    await refreshBluetoothStatus();
}

async function forgetBluetoothDevice(mac, name) {
    if (!confirm(I18N.confirm_bluetooth_forget_device.replace("{name}", name))) return;

    const response = await fetch("/api/bluetooth/forget", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mac })
    });
    const result = await response.json();

    if (!result.success) {
        alert(I18N.alert_settings_change_failed.replace("{message}", result.message || ""));
        return;
    }

    await refreshBluetoothStatus();
}

async function disconnectBluetoothDevice(mac, name) {
    if (!confirm(I18N.confirm_bluetooth_disconnect_device.replace("{name}", name))) return;

    const response = await fetch("/api/bluetooth/disconnect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mac })
    });
    const result = await response.json();

    if (!result.success) {
        alert(I18N.alert_settings_change_failed.replace("{message}", result.message || ""));
        return;
    }

    await refreshBluetoothStatus();
}

document.getElementById("bluetoothDevicesModal")
    .addEventListener("show.bs.modal", refreshBluetoothStatus);

async function setBluetoothChannelPreference(startChannel) {
    const response = await fetch("/api/bluetooth/channel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ start_channel: startChannel })
    });
    const result = await response.json();
    console.log(result);
}
