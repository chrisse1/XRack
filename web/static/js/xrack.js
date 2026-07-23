async function updateStatus() {

    const response = await fetch("/api/status");
    const data = await response.json();

    document.getElementById("hostname").textContent = data.hostname;
    document.getElementById("cpu").textContent = data.cpu + " %";
    document.getElementById("ram").textContent = data.ram + " %";
    document.getElementById("disk").textContent = data.disk + " %";
}

// Beim Laden der Seite einmal aktualisieren
updateStatus();

// Danach jede Sekunde aktualisieren
setInterval(updateStatus, 1000);
