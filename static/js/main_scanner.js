// static/js/main_scanner.js
$(function() {
    const App = {
        raumName: "",
        scannedItems: [],
        checklist: [],
        missingAssets: [],
        scannerState: null,
        importConfirmModal: new bootstrap.Modal(document.getElementById('importConfirmModal'))
    };

    const html5QrCode = new Html5Qrcode("reader");

    function renderScannedItems() {
        const $list = $(".thumbnails");
        $list.empty();
        if (App.scannedItems.length === 0) {
            $list.append('<li class="list-group-item text-muted">Noch keine Geräte gescannt.</li>');
            return;
        }
        App.scannedItems.forEach(code => {
            let $li = $(`<li class="list-group-item d-flex justify-content-between align-items-center"><span>${code}</span><button type="button" class="btn btn-outline-danger btn-sm" onclick="removeScan('${code}')">&times;</button></li>`);
            $list.prepend($li);
        });
    }

    function renderChecklistTable() {
        const $tableBody = $("#asset-checklist-body");
        $tableBody.empty();
        if (App.checklist.length === 0) {
            $tableBody.append('<tr><td colspan="3" class="text-center text-muted">Für diesen Raum sind keine Assets in TopDesk hinterlegt oder der Raum wurde nicht gefunden.</td></tr>');
            return;
        }
        App.checklist.forEach(asset => {
            const inventoryNumber = asset?.name || 'N/A';
            const description = asset['@@summary'] || 'N/A';
            const isScanned = App.scannedItems.includes(inventoryNumber);
            const rowClass = isScanned ? 'table-success' : 'table-danger';
            const rowHtml = `<tr class="${rowClass}"><td>${inventoryNumber}</td><td>${description}</td><td>${isScanned ? 'Gefunden ✔' : 'Fehlt ✖'}</td></tr>`;
            $tableBody.append(rowHtml);
        });
    }

    function addScannedItem(code) {
        if (code && !App.scannedItems.includes(code)) {
            App.scannedItems.push(code);
            renderScannedItems();
            renderChecklistTable();
        }
    }

    window.removeScan = function(code) {
        App.scannedItems = App.scannedItems.filter(item => item !== code);
        renderScannedItems();
        renderChecklistTable();
    };

    function fetchChecklist(roomName) {
        if (!roomName) {
            App.checklist = [];
            $("#asset-checklist-body").html('<tr><td colspan="3" class="text-center text-muted">Bitte zuerst einen Raum auswählen.</td></tr>');
            return;
        }
        const $tableBody = $("#asset-checklist-body");
        $tableBody.html('<tr><td colspan="3" class="text-center"><div class="spinner-border spinner-border-sm"></div> Lade...</td></tr>');
        $.ajax({
            url: `/get_assets_for_room?room=${encodeURIComponent(roomName)}`, type: "GET",
            success: function(response) {
                App.checklist = response.success ? (response.assets || []) : [];
                if (!response.success) $tableBody.html(`<tr><td colspan="3" class="text-center text-danger">Fehler: ${response.message}</td></tr>`);
                renderChecklistTable();
            },
            error: function() {
                App.checklist = [];
                $tableBody.html('<tr><td colspan="3" class="text-center text-danger">Serverfehler.</td></tr>');
            }
        });
    }

    function runImport(withRemove) {
        App.importConfirmModal.hide();
        const $button = $("#start-import-btn");
        $button.prop('disabled', true).html('<span class="spinner-border spinner-border-sm"></span> Importiere...');
        const payload = [{"Text": App.raumName}, ...App.scannedItems.map(code => ({"code": code}))];
        if (withRemove) {
            const missingIds = App.missingAssets.map(asset => asset.id || asset.unid).filter(id => id);
            if (missingIds.length > 0) payload.push({"missingAssetIds": missingIds});
        }
        $.ajax({
            url: "/direct_import", type: "POST", data: JSON.stringify(payload), contentType: "application/json; charset=utf-8", dataType: "json",
            success: function(response) {
                if (response.success && response.redirect_url) {
                    window.location.href = response.redirect_url;
                } else {
                    alert("Ein Fehler ist aufgetreten: " + (response.message || "Unbekannter Fehler"));
                    $button.prop('disabled', false).text('Import nach TopDesk starten');
                }
            },
            error: function() {
                alert("Ein schwerwiegender Serverfehler ist aufgetreten.");
                $button.prop('disabled', false).text('Import nach TopDesk starten');
            }
        });
    }

    const config = { fps: 10, qrbox: { width: 250, height: 250 } };

    const onScanSuccess = (decodedText, decodedResult) => {
        if (App.scannerState === 'PAUSED') return;
        App.scannerState = 'PAUSED';
        html5QrCode.pause();

        const codeFormat = decodedResult.result.format.formatName;

        if (codeFormat === "QR_CODE") {
            const roomId = decodedText;
            $("#raumfeld").val("Suche Raum...").prop('disabled', true);

            $.ajax({
                url: `/get_location_details_by_id?id=${encodeURIComponent(roomId)}`,
                type: 'GET',
                success: function(response) {
                    if (response.success && response.location) {
                        const locationData = response.location;
                        const buildingName = locationData.buildingZone?.name || '';
                        const roomName = locationData.name || '';
                        const displayText = buildingName ? `${buildingName} - ${roomName}` : roomName;
                        App.raumName = roomName;
                        $("#raumfeld").val(displayText);
                        fetchChecklist(App.raumName);
                    } else {
                        alert("Fehler: " + response.message);
                        $("#raumfeld").val("");
                    }
                },
                error: function(jqXHR) {
                    if (jqXHR.responseJSON && jqXHR.responseJSON.message) {
                        alert("Fehler: " + jqXHR.responseJSON.message);
                    } else {
                        alert("Serverfehler beim Abrufen der Raumdetails.");
                    }
                    $("#raumfeld").val("");
                },
                complete: function() {
                    $("#raumfeld").prop('disabled', false);
                    setTimeout(() => { if (html5QrCode.getState() === Html5QrcodeScannerState.PAUSED) html5QrCode.resume(); App.scannerState = 'SCANNING'; }, 1000);
                }
            });
        } else {
            addScannedItem(decodedText);
            setTimeout(() => { if (html5QrCode.getState() === Html5QrcodeScannerState.PAUSED) html5QrCode.resume(); App.scannerState = 'SCANNING'; }, 500);
        }
    };

    function startCamera() {
        if (html5QrCode.isScanning) return;
        html5QrCode.start({ facingMode: "environment" }, config, onScanSuccess, (e) => {})
            .then(() => { App.scannerState = 'SCANNING'; console.log("Kamera gestartet."); })
            .catch(err => $("#reader").html(`<div class="alert alert-danger">Kamerafehler: ${err}</div>`));
    }

    function stopCamera() {
        if (html5QrCode.isScanning) {
            html5QrCode.stop().then(() => { App.scannerState = 'STOPPED'; console.log("Kamera gestoppt."); });
        }
    }

    $(".controls").on("click", "button.start", startCamera);
    $(".controls").on("click", "button.stop", stopCamera);
    $("#raumfeld").on("keypress", e => { if (e.which === 13) { App.raumName = $(e.target).val(); fetchChecklist(App.raumName); }});
    $(".controls").on("click", "button.reset", () => {
        stopCamera();
        App.raumName = ""; App.scannedItems = []; App.checklist = [];
        $("#raumfeld").val(""); renderScannedItems();
        $("#asset-checklist-body").html('<tr><td colspan="3" class="text-center text-muted">Bitte zuerst einen Raum auswählen.</td></tr>');
    });

    $("#start-import-btn").on("click", function() {
        if (!App.raumName) {
            const manualEntry = $("#raumfeld").val().trim();
            if (manualEntry) {
                App.raumName = manualEntry;
            } else {
                alert("Bitte zuerst einen gültigen Raum scannen oder eingeben."); return;
            }
        }
        App.missingAssets = App.checklist.filter(asset => !App.scannedItems.includes(asset?.name || 'N/A'));
        if (App.missingAssets.length === 0) {
            runImport(false);
        } else {
            $("#missing-assets-count").text(App.missingAssets.length);
            const $list = $("#missing-assets-list");
            $list.empty();
            App.missingAssets.forEach(asset => $list.append(`<li class="list-group-item list-group-item-danger">${asset.name} - ${asset['@@summary']}</li>`));
            App.importConfirmModal.show();
        }
    });

    $("#import-update-only-btn").on("click", () => runImport(false));
    $("#import-remove-missing-btn").on("click", () => runImport(true));

    renderScannedItems();
    startCamera(); // Kamera automatisch starten
});
