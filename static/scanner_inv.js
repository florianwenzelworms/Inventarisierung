$(function () {
    // Zentraler Speicher für den Zustand der aktuellen Session
    const App = {
        raum: "",
        items: [] // Eine Liste von Objekten, z.B. { code: '12345' }
    };

    // --- TEIL 1: FUNKTIONEN ZUR DARSTELLUNG (VIEW) ---

    // Diese Funktion zeichnet die Tabelle basierend auf dem App.items-Array neu
    function renderTable() {
        const $tableBody = $("#scan-table-body");
        $tableBody.empty(); // Leert die bestehende Tabelle

        if (App.items.length === 0) {
            $tableBody.append('<tr><td colspan="2" class="text-center text-muted">Noch keine Geräte gescannt.</td></tr>');
        } else {
            App.items.forEach((item, index) => {
                const rowHtml = `
                    <tr data-index="${index}">
                        <td>
                            <input type="text" class="form-control form-control-sm code-input" value="${item.code}" placeholder="Code eingeben...">
                        </td>
                        <td>
                            <button class="btn btn-outline-danger btn-sm delete-row-btn">&times;</button>
                        </td>
                    </tr>
                `;
                $tableBody.append(rowHtml);
            });
        }
    }

    // --- TEIL 2: FUNKTIONEN ZUR DATENVERÄNDERUNG (CONTROLLER) ---

    function addScan(code) {
        // Prüfe NUR bei nicht-leeren Codes auf Duplikate
        if (code && App.items.some(item => item.code === code)) {
            console.log(`Code ${code} ist bereits in der Liste.`);
            return; // Breche ab, wenn ein Duplikat gescannt wird
        }

        // Füge den Code hinzu, wenn er neu ist ODER wenn er leer ist (vom Plus-Button)
        App.items.push({code: code});
        renderTable(); // Zeichne die Tabelle in jedem Fall neu
    }

    function updateScan(index, newCode) {
        if (App.items[index]) {
            App.items[index].code = newCode;
        }
    }

    function deleteScan(index) {
        App.items.splice(index, 1);
        renderTable(); // Tabelle neu zeichnen
    }

    function setRaum(raumName) {
        App.raum = raumName;
        $("#raumfeld").val(raumName);
        $("#raumfeld").css('background-color', '#d4edda').animate({backgroundColor: ''}, 1000);
    }

    // --- TEIL 3: SCANNER-LOGIK ---

    const html5QrCode = new Html5Qrcode("reader");
    const config = {fps: 10, qrbox: {width: 250, height: 250}, rememberLastUsedCamera: true};

    const onScanSuccess = (decodedText, decodedResult) => {
        html5QrCode.pause();
        try {
            const qrData = JSON.parse(decodedText);
            if (qrData && qrData.raum) {
                setRaum(qrData.raum);
            } else {
                addScan(decodedText);
            }
        } catch (e) {
            addScan(decodedText);
        }
        setTimeout(() => {
            if (html5QrCode.getState() !== 'NOT_SCANNING') html5QrCode.resume();
        }, 1000);
    };

    // --- TEIL 4: EVENT-LISTENER ---

    // Kamera-Steuerung
    $(".controls").on("click", "button.start", () => html5QrCode.start({facingMode: "environment"}, config, onScanSuccess, (e) => {
    }));
    $(".controls").on("click", "button.stop", () => {
        if (html5QrCode.isScanning) html5QrCode.stop();
    });

    // Manuelles Hinzufügen
    $("#add-row-btn").on("click", () => addScan(""));

    // Tabelle bearbeiten (Löschen und Editieren)
    $("#scan-table-body").on("click", ".delete-row-btn", function () {
        const index = $(this).closest("tr").data("index");
        deleteScan(index);
    });
    $("#scan-table-body").on("change", ".code-input", function () {
        const index = $(this).closest("tr").data("index");
        updateScan(index, $(this).val());
    });

    // Raumfeld manuell ändern
    $("#raumfeld").on("change", function () {
        App.raum = $(this).val();
    });

    // Import-Button
    $("#start-import-btn").on("click", function () {
        App.raum = $("#raumfeld").val(); // Sicherstellen, dass der letzte Wert übernommen wird
        if (!App.raum) {
            alert("Bitte einen Raum angeben oder scannen.");
            return;
        }
        if (App.items.length === 0) {
            alert("Bitte mindestens ein Gerät scannen oder hinzufügen.");
            return;
        }

        const $feedback = $("#import-feedback");
        $feedback.html('<div class="spinner-border spinner-border-sm" role="status"></div> Import wird verarbeitet...').removeClass().addClass('alert alert-info');

        // Bereinigen der Items (leere Einträge entfernen)
        const finalItems = App.items.filter(item => item.code.trim() !== "");
        const payload = [
            {"Text": App.raum},
            ...finalItems
        ];

        $.ajax({
            url: "/direct_import",
            type: "POST",
            data: JSON.stringify(payload),
            dataType: "json",
            contentType: "application/json; charset=utf-8",
            success: function (response) {
                if (response.success) {
                    $feedback.removeClass().addClass('alert alert-success').text(response.message);
                    // Alles zurücksetzen nach Erfolg
                    App.items = [];
                    App.raum = "";
                    $("#raumfeld").val("");
                    renderTable();
                } else {
                    $feedback.removeClass().addClass('alert alert-danger').text("Fehler: " + response.message);
                }
            },
            error: function () {
                $feedback.removeClass().addClass('alert alert-danger').text("Ein schwerwiegender Serverfehler ist aufgetreten.");
            }
        });
    });
    // Import-Button
    $("#start-import-btn").on("click", function () {
        App.raum = $("#raumfeld").val(); // Sicherstellen, dass der letzte Wert übernommen wird
        if (!App.raum) {
            alert("Bitte einen Raum angeben oder scannen.");
            return;
        }
        if (App.items.length === 0) {
            alert("Bitte mindestens ein Gerät scannen oder hinzufügen.");
            return;
        }

        const $feedback = $("#import-feedback");
        const $button = $(this);
        $button.prop('disabled', true); // Button deaktivieren während der Verarbeitung
        $feedback.html('<div class="spinner-border spinner-border-sm" role="status"></div> Import wird verarbeitet...').removeClass().addClass('alert alert-info');

        const finalItems = App.items.filter(item => item.code.trim() !== "");
        const payload = [
            {"Text": App.raum},
            ...finalItems
        ];

        // Der Ajax-Call zeigt jetzt auf den neuen Endpunkt '/direct_import'
        $.ajax({
            url: "/direct_import", // GEÄNDERT
            type: "POST",
            data: JSON.stringify(payload),
            dataType: "json",
            contentType: "application/json; charset=utf-8",
            success: function (response) {
                // Die detaillierte Antwort vom Server verarbeiten und anzeigen
                let reportHtml = `<h6>${response.message}</h6>`;
                if (response.report) {
                    reportHtml += '<ul>';
                    if (response.report.successful) response.report.successful.forEach(msg => reportHtml += `<li class="text-success">✔ ${msg}</li>`);
                    if (response.report.not_found) response.report.not_found.forEach(msg => reportHtml += `<li class="text-warning">⚠ ${msg}</li>`);
                    if (response.report.errors) response.report.errors.forEach(msg => reportHtml += `<li class="text-danger">✖ ${msg}</li>`);
                    reportHtml += '</ul>';
                }

                if (response.success) {
                    $feedback.removeClass().addClass('alert alert-success').html(reportHtml);
                    // Alles zurücksetzen nach Erfolg
                    App.items = [];
                    App.raum = "";
                    $("#raumfeld").val("");
                    renderTable(); // renderTable() ist die Funktion, die die Tabelle zeichnet
                } else {
                    $feedback.removeClass().addClass('alert alert-danger').text("Fehler: " + response.message);
                }
            },
            error: function () {
                $feedback.removeClass().addClass('alert alert-danger').text("Ein schwerwiegender Serverfehler ist aufgetreten.");
            },
            complete: function () {
                $button.prop('disabled', false); // Button wieder aktivieren
            }
        });
    });
    // Initiales Rendern der leeren Tabelle
    renderTable();
});