async function updateStatus() {

    const response = await fetch("/api/status");
    const data = await response.json();

    document.getElementById("hostname").textContent = data.hostname;
    document.getElementById("cpu").textContent = data.cpu + " %";
    document.getElementById("ram").textContent = data.ram + " %";
    document.getElementById("disk").textContent = data.disk + " %";

    // Audio-Status aktualisieren
    const audioState = document.getElementById("audio-state");

    if (data.audio_connected) {
        audioState.textContent = "🟢 " + data.audio_device;
    } else {
        audioState.textContent = "🔴 " + data.audio_device;
    }
}


async function loadAudioDevices() {

    const response = await fetch("/api/audio/devices");
    const devices = await response.json();

    const select = document.getElementById("audio-device-select");

    // Aktuelle Auswahl merken
    const selected = select.value;

    // Liste leeren
    select.innerHTML = "";

    // Neue Einträge erzeugen
    devices.forEach(device => {

        const option = document.createElement("option");

        option.value = device.id;
        option.textContent = device.description;

        if (device.id === selected) {
            option.selected = true;
        }

        select.appendChild(option);

    });

    // Event nur einmal registrieren
    if (!select.dataset.initialized) {

        select.addEventListener("change", async function () {

            const response = await fetch(
                "/api/audio/select",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        device_id: this.value
                    })
                }
            );

            const result = await response.json();

            console.log(result);

            await refreshDashboard();

        });

        select.dataset.initialized = "true";
    }

}


// Beim Laden der Seite
async function refreshDashboard() {

    await updateStatus();
    await loadAudioDevices();

}

async function startRecorder() {

    const response = await fetch(
        "/api/recorder/start",
        {
            method: "POST"
        }
    );

    const result = await response.json();

    console.log(result);

    await refreshDashboard();
}


async function stopRecorder() {

    const response = await fetch(
        "/api/recorder/stop",
        {
            method: "POST"
        }
    );

    const result = await response.json();

    console.log(result);

    await refreshDashboard();
}

// Sofort aktualisieren
refreshDashboard();


// Danach jede Sekunde
setInterval(refreshDashboard, 1000);
