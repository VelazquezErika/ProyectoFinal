document.addEventListener("DOMContentLoaded", () => {

    const fileInput      = document.getElementById("fileInput");
    const statusDiv      = document.getElementById("status");
    const statusText     = document.getElementById("status-text");
    const workersSection = document.getElementById("workers-section");
    const workersGrid    = document.getElementById("workers-grid");

    const WORKERS = {
        resize:    { label: "Redimensionar" },
        thumbnail: { label: "Miniatura"     },
        filter:    { label: "Filtro gris"   },
        convert:   { label: "Convertir PNG" }
    };

    function setStatus(msg, type = "") {
        statusText.textContent = msg;
        statusDiv.className = "";
        if (type) statusDiv.classList.add(type);
    }

    function renderWorkers(results) {
        workersSection.classList.add("visible");
        workersGrid.innerHTML = "";

        for (const [worker, info] of Object.entries(WORKERS)) {
            const val = results[worker] || null;

            let cardClass = "";
            let stateText = "Pendiente";

            if (val === "en proceso") {
                cardClass = "processing";
                stateText = "Procesando...";
            } else if (val && val.startsWith("completada")) {
                cardClass = "done";
                stateText = "Completado";
            } else if (val === "error") {
                cardClass = "error-state";
                stateText = "Error";
            }

            workersGrid.innerHTML += `
                <div class="worker-card ${cardClass}">
                    <div class="worker-info">
                        <div class="worker-name">${info.label}</div>
                        <div class="worker-state">
                            <span class="worker-dot"></span>
                            ${stateText}
                        </div>
                    </div>
                </div>`;
        }
    }

    fileInput.addEventListener("change", async (event) => {
        const file = event.target.files[0];
        if (!file) return;

        workersSection.classList.remove("visible");
        workersGrid.innerHTML = "";
        setStatus("Subiendo imagen a S3...", "processing");

        // 1. Pedir URL prefirmada al backend
        const response = await fetch("/api/presigned-post", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ file_name: file.name, file_type: file.type })
        });

        if (!response.ok) {
            setStatus("Error al obtener URL de subida", "error-state");
            return;
        }

        const data      = await response.json();
        const fileName  = data.file_name;
        const presigned = data.presigned;

        const formData = new FormData();
        Object.entries(presigned.fields).forEach(([k, v]) => formData.append(k, v));
        formData.append("file", file);

        const uploadResponse = await fetch(presigned.url, { method: "POST", body: formData });

        if (!uploadResponse.ok) {
            setStatus("Error al subir la imagen", "error-state");
            return;
        }

        console.log("Archivo subido:", fileName);
        setStatus("Esperando workers... (0/4 completados)", "processing");

        const source = new EventSource(`/events/${fileName}`);
        let done = false;

        source.onmessage = (event) => {
            const payload = JSON.parse(event.data);
            console.log("SSE:", payload);

            renderWorkers(payload.results);

            if (payload.all_done) {
                done = true;
                source.close();
                setStatus("Todas las tareas completadas", "done");
            } else {
                const n = payload.completed ? payload.completed.length : 0;
                setStatus(`Procesando... (${n}/4 completados)`, "processing");
            }
        };

        source.onerror = () => {
            console.log("SSE cerrado o error de conexión");
            if (!done) {
                source.close();
                setStatus("Se perdió la conexión con el servidor", "error-state");
            }
        };
    });
});