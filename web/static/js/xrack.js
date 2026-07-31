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

let recorderMonitoring = false;

// Gerät/Kanäle dürfen während keiner laufenden Aufnahme,
// Pegelprüfung oder Wiedergabe (Soundcheck oder Musik) geändert
// werden.
function isAudioBusy(data) {
    return data.recording || data.recorder_monitoring || data.playback_active || data.music_playing;
}

// ============================================================
// 2. CORE UI UPDATES
// ============================================================

async function refreshDashboard() {
    await updateStatus();
}

async function updateStatus() {
    const response = await fetch("/api/status");
    const data = await response.json();

    selectedAudioDevice = data.selected_audio_device;

    updateSystemStats(data);
    updateAudioStatus(data);
    updateAudioDeviceSelectState(data);
    updateRecorder(data);
    updateMusicPlayer(data);
}

function updateSystemStats(data) {
    document.getElementById("hostname").textContent = data.hostname;
    document.getElementById("cpu").textContent = data.cpu + " %";
    document.getElementById("ram").textContent = data.ram + " %";
    document.getElementById("disk").textContent = data.disk + " %";
}

function updateAudioStatus(data) {
    const audioState = document.getElementById("audio-state");
    audioState.textContent = data.audio_connected
        ? "🟢 " + data.audio_device
        : "🔴 " + data.audio_device;

    const audioInfo = document.getElementById("audio-info");
    if (data.audio_connected) {
        audioInfo.textContent =
            `${data.audio_channels} Ch • ` +
            `${data.audio_sample_rate / 1000} kHz • ` +
            `${data.audio_sample_bits} Bit • ` +
            data.audio_formats.join(", ");
    } else {
        audioInfo.textContent = "Audio Interface";
    }
}

function updateAudioDeviceSelectState(data) {
    const select = document.getElementById("audio-device-select");
    if (select) select.disabled = isAudioBusy(data);

    const rescanButton = document.getElementById("audio-rescan");
    if (rescanButton) rescanButton.disabled = isAudioBusy(data);
}

// ============================================================
// 3. RECORDER UI
// ============================================================

function updateRecorder(data) {
    playbackActive = data.playback_active;
    recorderMonitoring = data.recorder_monitoring;

    updateRecorderStatus(data);
    updateAudioCoreStatus(data);
    updateRecordingInfo(data);
    updateRecordChannels(data);
    updateRecordingList(data.recordings);
    updateSoundcheckButton(data);
    updateLevelCheckButton(data);
}

function updateRecorderStatus(data) {
    document.getElementById("recorder-status").textContent = data.recorder;
}

function updateAudioCoreStatus(data) {
    document.getElementById("engine-status").textContent =
        data.audio_core_open ? "🟢 geöffnet" : "⚪ geschlossen";
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

function showRecordingInfo(filename, duration, size, channels, sampleRate, bitsPerSample) {
    document.getElementById("recorder-file").textContent = filename ?? "-";
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
        list.innerHTML = `<div class="text-muted text-center py-3">Keine Aufnahmen vorhanden.</div>`;
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

        item.innerHTML = recording === selectedRecording
            ? `<i class="bi bi-check-circle-fill me-2"></i>${recording}`
            : recording;

        item.onclick = async () => {
            selectedRecording = recording;
            await loadRecordingInfo();
            updateRecordingList(recordings);

            const button = document.getElementById("btn-recorder-play");
            if (button && !playbackActive) {
                button.disabled = false;
            }
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
        option.textContent = channels + " Kanäle";
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
        option.textContent = device.description;
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
        button.innerHTML = `<i class="bi bi-stop-circle me-2"></i>Stop`;
        button.classList.remove("btn-success");
        button.classList.add("btn-warning");
        button.disabled = false;
    } else {
        button.innerHTML = `<i class="bi bi-play-circle me-2"></i>Soundcheck`;
        button.classList.remove("btn-warning");
        button.classList.add("btn-success");
        button.disabled = !selectedRecording || data.recording || data.music_playing;
    }
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
        button.innerHTML = `<i class="bi bi-soundwave me-2"></i>Pegel (läuft mit der Aufnahme)`;
        button.classList.remove("btn-outline-info");
        button.classList.add("btn-info");
        button.disabled = true;
    } else if (data.recorder_monitoring) {
        button.innerHTML = `<i class="bi bi-soundwave me-2"></i>Pegel testen (Stop)`;
        button.classList.remove("btn-outline-info");
        button.classList.add("btn-info");
        button.disabled = false;
    } else {
        button.innerHTML = `<i class="bi bi-soundwave me-2"></i>Pegel testen`;
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
        container.innerHTML = `<div class="text-muted text-center py-2"><small>Kein Signal - "Pegel testen" oder Aufnahme starten.</small></div>`;
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
        console.log(result);
    }
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
                    ${isSelected ? '<span class="badge text-bg-primary ms-2">Für Soundcheck ausgewählt</span>' : ''}
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
                <button class="btn btn-outline-success btn-sm" title="Für Soundcheck auswählen" data-action="choose" data-filename="${recording.filename}">
                    <i class="bi bi-play-circle"></i>
                </button>
                <button class="btn btn-outline-primary btn-sm" title="Download" data-action="download" data-filename="${recording.filename}">
                    <i class="bi bi-download"></i>
                </button>
                <button class="btn btn-outline-danger btn-sm" title="Löschen" data-action="delete" data-filename="${recording.filename}">
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
    }
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
    if (!confirm(`"${filename}" wirklich löschen?`)) return;

    const response = await fetch(`/api/recordings/${encodeURIComponent(filename)}`, {
        method: "DELETE"
    });

    if (!response.ok) {
        alert("Aufnahme konnte nicht gelöscht werden.");
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
        Ausgewählte löschen (${selectedRecordings.size})
    `;
}

async function deleteSelectedRecordings() {
    if (selectedRecordings.size === 0) {
        return;
    }

    if (!confirm(`${selectedRecordings.size} Aufnahme(n) wirklich löschen?`)) {
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
        alert("Aufnahmen konnten nicht gelöscht werden.");
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
}

function updateMusicChannels(data) {
    const select = document.getElementById("music-channels");
    if (!select) return;

    if (select.dataset.built !== String(data.audio_channels)) {
        select.innerHTML = "";

        for (let start = 1; start + 1 <= data.audio_channels; start += 2) {
            const option = document.createElement("option");
            option.value = start;
            option.textContent = `Kanal ${start}+${start + 1}`;
            select.appendChild(option);
        }

        select.dataset.built = String(data.audio_channels);
    }

    if (data.music_playing) {
        select.value = data.music_start_channel + 1;
    }

    select.disabled = isAudioBusy(data);
}

function updateMusicStatus(data) {
    const status = document.getElementById("player-status");
    if (status) {
        status.textContent = data.music_paused
            ? "pausiert"
            : (data.music_playing ? "Wiedergabe läuft" : "gestoppt");
    }

    const title = document.getElementById("player-title");
    if (title) {
        title.textContent = data.music_playing ? (data.music_track || "-") : "-";
    }

    const mode = document.getElementById("player-mode");
    if (mode) {
        mode.textContent = data.music_playing
            ? (data.music_folder_mode ? "Ordner (Zufall/Schleife)" : "Einzeltitel")
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
            pauseButton.innerHTML = `<i class="bi bi-play-circle me-2"></i>Fortsetzen`;
        } else {
            pauseButton.innerHTML = `<i class="bi bi-pause-circle me-2"></i>Pause`;
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
musicModal.addEventListener("show.bs.modal", () => loadMusicBrowse(""));

document.getElementById("btn-play-current-folder")
    .addEventListener("click", () => playMusicFolder(musicCurrentPath));

async function loadMusicBrowse(path) {
    try {
        const response = await fetch(`/api/music/browse?path=${encodeURIComponent(path)}`);

        if (!response.ok) {
            throw new Error("API-Fehler");
        }

        const listing = await response.json();

        musicCurrentPath = listing.path;

        renderMusicBreadcrumb(listing.path);
        renderMusicList(listing);
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
        rootItem.textContent = "Musik";
    } else {
        const link = document.createElement("a");
        link.href = "#";
        link.textContent = "Musik";
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
        container.innerHTML = `<div class="text-muted text-center py-3">Keine Musikdateien gefunden.</div>`;
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
            <button class="btn btn-outline-success btn-sm" title="Diesen Ordner zufällig abspielen">
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
            <span><i class="bi bi-file-earmark-music me-2"></i>${file}</span>
            <div class="btn-group btn-group-sm">
                <button class="btn btn-outline-primary btn-sm" title="Datei abspielen">
                    <i class="bi bi-play-fill"></i>
                </button>
                <button class="btn btn-outline-danger btn-sm" title="Löschen">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
        `;

        const buttons = item.querySelectorAll("button");
        buttons[0].onclick = () => playMusicFile(filePath);
        buttons[1].onclick = () => deleteMusicFile(filePath, file);

        container.appendChild(item);
    });
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
        alert("Wiedergabe konnte nicht gestartet werden.");
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
        alert("Wiedergabe konnte nicht gestartet werden.");
        return;
    }

    bootstrap.Modal.getOrCreateInstance(musicModal).hide();
    await refreshDashboard();
}

async function deleteMusicFile(path, displayName) {
    if (!confirm(`"${displayName}" wirklich löschen?`)) return;

    const response = await fetch("/api/music/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path })
    });
    const result = await response.json();

    if (!result.success) {
        alert("Datei konnte nicht gelöscht werden.");
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
    const name = prompt("Name des neuen Ordners:");
    if (!name) return;

    const response = await fetch("/api/music/create-folder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: musicCurrentPath, name })
    });
    const result = await response.json();
    console.log(result);

    if (!result.success) {
        alert("Ordner konnte nicht angelegt werden (existiert er schon?).");
        return;
    }

    await loadMusicBrowse(musicCurrentPath);
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

    const response = await fetch("/api/music/upload", {
        method: "POST",
        body: formData
    });
    const result = await response.json();
    console.log(result);

    input.value = "";

    if (result.count === 0) {
        alert("Es wurden keine Dateien hochgeladen (unterstütztes Format?).");
    }

    await loadMusicBrowse(musicCurrentPath);
}

// ============================================================
// 11c. SYSTEM
// ============================================================

async function shutdownSystem() {
    if (!confirm(
        "Raspberry Pi wirklich herunterfahren?\n\n" +
        "Laufende Aufnahmen/Wiedergaben werden dabei beendet, und " +
        "das Webinterface ist danach nicht mehr erreichbar, bis " +
        "der Pi manuell wieder eingeschaltet wird."
    )) {
        return;
    }

    const button = document.getElementById("btn-shutdown");
    if (button) {
        button.disabled = true;
        button.innerHTML = `<i class="bi bi-power me-2"></i>Fährt herunter...`;
    }

    const response = await fetch("/api/system/shutdown", { method: "POST" });
    const result = await response.json();
    console.log(result);

    if (!result.success) {
        alert("Herunterfahren fehlgeschlagen. Ist die sudo-Berechtigung eingerichtet (install.sh)?");
        if (button) {
            button.disabled = false;
            button.innerHTML = `<i class="bi bi-power me-2"></i>Raspberry Pi herunterfahren`;
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
