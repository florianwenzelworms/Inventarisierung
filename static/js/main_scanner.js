// static/js/main_scanner.js
$(function() {
    const App = {
        raumName: "",
        scannedItems: [],
        checklist: [],
        missingAssets: [],
        scannerState: null,
        importConfirmModal: new bootstrap.Modal(document.getElementById('importConfirmModal')),
        newAssetsModal: new bootstrap.Modal(document.getElementById('newAssetsModal')),
        // NEU: AudioContext für den Beep-Ton hinzugefügt
        audioContext: null
    };

    // NEU: Funktion zum Abspielen des Beep-Tons
    function playBeep() {
        // Prüft, ob der AudioContext bereit ist.
        if (!audioContext) {
            console.warn("AudioContext not initialized. Cannot play beep. Please click anywhere on the page first.");
            return;
        }
        try {
            const oscillator = audioContext.createOscillator();
            oscillator.type = 'sine'; // Ein weicherer, angenehmerer Ton
            oscillator.frequency.setValueAtTime(900, audioContext.currentTime); // Eine klare, mittlere Frequenz
            oscillator.connect(audioContext.destination);
            oscillator.start();
            oscillator.stop(audioContext.currentTime + 0.1); // Dauer des Tons: 100ms
        } catch(e) {
            console.error("Beep konnte nicht abgespielt werden:", e);
        }
    }

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
            url: "/direct_import",
            type: "POST",
            data: JSON.stringify(payload),
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            success: function(response) {
                console.log("Antwort vom Server empfangen:", response);

                if (response.not_found_codes && response.not_found_codes.length > 0) {
                    populateNewAssetsModal(response.not_found_codes);
                    App.newAssetsModal.show();
                    $("#new-assets-modal-submit").data('redirect-url', response.redirect_url);
                } else {
                    if (response.redirect_url) {
                        window.location.href = response.redirect_url;
                    }
                }
            },
            error: function() {
                alert("Ein schwerwiegender Serverfehler ist aufgetreten.");
                $button.prop('disabled', false).text('Import nach TopDesk starten');
            }
        });
    }

    function populateNewAssetsModal(codes) {
        const $modalBody = $("#new-assets-modal-body");
        const $templateSelect = $("#asset-type-template");
        $modalBody.empty();
        codes.forEach(code => {
            const rowHtml = `
                <div class="row mb-2 align-items-center">
                    <div class="col-5">
                        <label class="form-label mb-0">${code}</label>
                    </div>
                    <div class="col-7">
                        <select class="form-select form-select-sm asset-type-select" data-asset-code="${code}">
                            ${$templateSelect.html()}
                        </select>
                    </div>
                </div>
            `;
            $modalBody.append(rowHtml);
        });
    }

    const html5QrCode = new Html5Qrcode("reader");
    const config = { fps: 10, qrbox: { width: 250, height: 250 } };

    const onScanSuccess = (decodedText, decodedResult) => {
        if (App.scannerState === 'PAUSED') return;
        App.scannerState = 'PAUSED';
        html5QrCode.pause();

        // NEU: Beep-Ton wird hier abgespielt
        playBeep();

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

    $("#new-assets-modal-submit").on("click", function() {
        const newAssets = [];
        $(".asset-type-select").each(function() {
            newAssets.push({
                code: $(this).data('asset-code'),
                type: $(this).val()
            });
        });

        const $button = $(this);
        $button.prop('disabled', true);

        $.ajax({
            url: "/send_new_asset_report",
            type: "POST",
            data: JSON.stringify({ new_assets: newAssets, room_name: App.raumName }),
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            success: function(response) {
                if (response.success) {
                    const redirectUrl = $("#new-assets-modal-submit").data('redirect-url');
                    if (redirectUrl) {
                        window.location.href = redirectUrl;
                    }
                } else {
                    alert("Fehler beim Senden des Berichts: " + response.message);
                }
            },
            error: function() {
                alert("Serverfehler beim Senden des Berichts.");
            },
            complete: function() {
                $button.prop('disabled', false);
                App.newAssetsModal.hide();
            }
        });
    });

    $("#import-update-only-btn").on("click", () => runImport(false));
    $("#import-remove-missing-btn").on("click", () => runImport(true));

    renderScannedItems();
    startCamera();
});
