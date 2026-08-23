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

let sampleRateMismatchDismissed = false;
let sampleRateMismatchSuggestion = 0;

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
        updateSampleRateMismatchBanner(data);
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

function updateSampleRateMismatchBanner(data) {
    const banner = document.getElementById("sample-rate-mismatch-banner");
    if (!banner) return;

    if (!data.sample_rate_mismatch) {
        sampleRateMismatchDismissed = false;
        banner.classList.add("d-none");
        return;
    }

    sampleRateMismatchSuggestion = data.sample_rate_suggested;

    if (sampleRateMismatchDismissed) return;

    document.getElementById("sample-rate-mismatch-text").textContent =
        I18N.sample_rate_mismatch_message
            .replace("{configured}", data.audio_sample_rate)
            .replace("{measured}", data.sample_rate_measured)
            .replace("{suggested}", data.sample_rate_suggested);

    banner.classList.remove("d-none");
}

document.getElementById("btn-sample-rate-mismatch-dismiss").addEventListener("click", () => {
    sampleRateMismatchDismissed = true;
    document.getElementById("sample-rate-mismatch-banner").classList.add("d-none");
});

document.getElementById("btn-sample-rate-apply-suggestion").addEventListener("click", async () => {
    if (!sampleRateMismatchSuggestion) return;

    await fetch("/api/settings/sample_rate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sample_rate: sampleRateMismatchSuggestion })
    });

    sampleRateMismatchDismissed = true;
    document.getElementById("sample-rate-mismatch-banner").classList.add("d-none");
});

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
    audioInfo.classList.remove("text-secondary", "text-warning");
    audioInfo.classList.add(data.sample_rate_mismatch ? "text-warning" : "text-secondary");
    if (data.audio_connected) {
        let measuredPart = "";
        if (data.sample_rate_measured) {
            const measuredKhz = (data.sample_rate_measured / 1000).toFixed(1);
            measuredPart = ` (${I18N.audio_info_measured_rate_label}: ${measuredKhz} kHz)`;
        }
        audioInfo.textContent =
            `${data.audio_channels} Ch • ` +
            `${data.audio_sample_rate / 1000} kHz${measuredPart} • ` +
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
    } else {
        button.innerHTML = `<i class="bi bi-record-circle fs-3"></i><small>${I18N.btn_recording_start}</small>`;
        button.classList.remove("btn-secondary");
        button.classList.add("btn-danger");
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
        button.innerHTML = `<i class="bi bi-play-circle fs-3"></i><small>${I18N.btn_soundcheck}</small>`;
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
            option.textContent = I18N.channel_option.replace("{a}", start).replace("{b}", start + 1);
            select.appendChild(option);
        }

        select.dataset.built = String(data.audio_channels);

        // Zuletzt genutzten Kanal vorbelegen (nur beim (Neu-)Aufbau
        // der Optionen, nicht bei jeder Statusabfrage - sonst
        // würde eine manuelle Auswahl ständig überschrieben).
        select.value = data.music_preferred_start_channel;
    }

    if (data.music_playing) {
        select.value = data.music_start_channel + 1;
    }

    select.disabled = isAudioBusy(data);

    select.onchange = () => {
        setMusicChannelPreference(Number(select.value));
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
    } catch (error) {
        console.error("Fehler beim Laden der Einstellungen:", error);
    }
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

    const shareNotConfigured = document.getElementById("settings-share-not-configured");
    const shareField = document.getElementById("settings-share-field");

    if (wlan.share_configured) {
        shareNotConfigured.classList.add("d-none");
        shareField.classList.remove("d-none");
        document.getElementById("settings-share-toggle").checked = wlan.share_enabled;
    } else {
        shareNotConfigured.classList.remove("d-none");
        shareField.classList.add("d-none");
    }

    const consoleIpField = document.getElementById("settings-console-ip-field");

    if (wlan.bridge_enabled || wlan.share_enabled) {
        document.getElementById("settings-console-ip-value").textContent =
            wlan.console_ip || I18N.settings_console_ip_not_found;
        consoleIpField.classList.remove("d-none");
    } else {
        consoleIpField.classList.add("d-none");
    }

    const portForwardNotAvailable = document.getElementById("settings-port-forward-not-configured");
    const portForwardField = document.getElementById("settings-port-forward-field");

    if (wlan.console_ip || wlan.port_forward_enabled) {
        portForwardNotAvailable.classList.add("d-none");
        portForwardField.classList.remove("d-none");
        document.getElementById("settings-port-forward-toggle").checked = wlan.port_forward_enabled;
    } else {
        portForwardNotAvailable.classList.remove("d-none");
        portForwardField.classList.add("d-none");
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
document.getElementById("settings-share-toggle").addEventListener("change", toggleShare);
document.getElementById("settings-port-forward-toggle").addEventListener("change", togglePortForward);

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

async function toggleShare(event) {
    const enabled = event.target.checked;
    const confirmText = enabled ? I18N.confirm_share_on : I18N.confirm_share_off;

    if (!confirm(confirmText)) {
        event.target.checked = !enabled;
        return;
    }

    const response = await fetch("/api/settings/share", {
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
    // Schließt sich mit der Ethernet+AP-Bridge aus - deren Schalter
    // kann sich dabei im Hintergrund mit geändert haben.
    await loadSettings();
}

async function togglePortForward(event) {
    const enabled = event.target.checked;
    const confirmText = enabled ? I18N.confirm_port_forward_on : I18N.confirm_port_forward_off;

    if (!confirm(confirmText)) {
        event.target.checked = !enabled;
        return;
    }

    const response = await fetch("/api/settings/port_forward", {
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
}

function updateBluetoothChannels(data) {
    const select = document.getElementById("bluetooth-channels");
    if (!select) return;

    if (select.dataset.built !== String(data.audio_channels)) {
        select.innerHTML = "";

        for (let start = 1; start + 1 <= data.audio_channels; start += 2) {
            const option = document.createElement("option");
            option.value = start;
            option.textContent = I18N.channel_option.replace("{a}", start).replace("{b}", start + 1);
            select.appendChild(option);
        }

        select.dataset.built = String(data.audio_channels);
        select.value = bluetoothSlowStatus.preferred_start_channel || 1;
    }

    select.onchange = () => {
        setBluetoothChannelPreference(Number(select.value));
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
