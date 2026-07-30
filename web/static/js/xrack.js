// ============================================================
// 1. STATE MANAGEMENT
// ============================================================

let selectedRecording = null;
const selectedRecordings = new Set();
let selectedRecordingInfo = null;
let selectedAudioDevice = "";

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
    updateRecorder(data);
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

// ============================================================
// 3. RECORDER UI
// ============================================================

function updateRecorder(data) {
    updateRecorderStatus(data);
    updateAudioCoreStatus(data);
    updateRecordingInfo(data);
    updateRecordChannels(data);
    updateRecordingList(data.recordings);
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
    await refreshDashboard();
}

async function stopRecorder() {
    const response = await fetch("/api/recorder/stop", { method: "POST" });
    const result = await response.json();
    console.log(result);
    await refreshDashboard();
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
    const card = document.createElement("div");
    card.className = "card mb-2";
    card.innerHTML = `
        <div class="card-body d-flex justify-content-between align-items-start">
            <div class="form-check mt-2">
                <input class="form-check-input" type="checkbox" data-action="select" data-filename="${recording.filename}">
            </div>
            <div class="flex-grow-1">
                <h6 class="card-title mb-2">
                    <i class="bi bi-music-note-beamed me-2"></i>
                    ${recording.filename}
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
    }
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

    await loadRecordings();
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

    selectedRecordings.clear();
    updateDeleteSelectedButton();
    await loadRecordings();
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
// 12. INITIALIZATION
// ============================================================

async function initializeDashboard() {
    await loadAudioDevices();
    await refreshDashboard();
    document.getElementById("audio-rescan").addEventListener("click", rescanAudioDevices);
}

initializeDashboard();
setInterval(refreshDashboard, 1000);
