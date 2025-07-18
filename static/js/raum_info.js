$(function() {
    const App = {
        audioContext: null,
        videoTrack: null,
        torchOn: false,
        scannedCustomId: null, // Speichert die zuletzt verarbeitete 6-stellige ID
        initialLocation: null,
        assignRoomModal: new bootstrap.Modal(document.getElementById('assignRoomModal')),
        confirmationModal: new bootstrap.Modal(document.getElementById('confirmationModal')),
        newRoomModal: new bootstrap.Modal(document.getElementById('newRoomModal')),
        infoModal: new bootstrap.Modal(document.getElementById('infoModal'))
    };

    const html5QrCode = new Html5Qrcode("reader");

    function playBeep() {
        try {
            if (!audioContext) {
                audioContext = new (window.AudioContext || window.webkitAudioContext)();
            }
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

    function showNotification(message, isError = true) {
        const $notification = $("#scan-notification");
        $notification.text(message).css('color', isError ? 'red' : 'green');
        $notification.css('opacity', 1).show();
        setTimeout(() => { $notification.css('opacity', 0); }, 2000);
    }

    function displayLocationInfo(location) {
        const $infoDisplay = $("#info-display");
        if (!location) {
            $infoDisplay.html(`<div class="alert alert-warning">Raum mit ID <strong>${App.scannedCustomId}</strong> wurde nicht gefunden.</div>`);
            return;
        }
        const building = location.buildingZone?.name || 'N/A';
        const branch = location.branch?.name || 'N/A';
        const infoHtml = `
            <div class="card">
                <div class="card-header bg-dark text-white"><h5 class="mb-0">${location.name || 'Unbekannter Raum'}</h5></div>
                <ul class="list-group list-group-flush">
                    <li class="list-group-item d-flex justify-content-between"><strong>Gebäude:</strong><span>${building}</span></li>
                    <li class="list-group-item d-flex justify-content-between"><strong>Raumnummer:</strong><span>${location.roomNumber || 'N/A'}</span></li>
                    <li class="list-group-item d-flex justify-content-between"><strong>Niederlassung:</strong><span>${branch}</span></li>
                    <li class="list-group-item d-flex justify-content-between"><strong>Raum-ID:</strong><code class="small">${App.scannedCustomId || 'N/A'}</code></li>
                    <li class="list-group-item d-flex justify-content-between"><strong>Topdesk-ID:</strong><code class="small">${location.id || 'N/A'}</code></li>
                </ul>
            </div>`;
        $infoDisplay.html(infoHtml);
    }

    // Zentrale Funktion zur Auslösung der Suche
    function triggerSearch(id) {
        App.scannedCustomId = id;
        $("#assign-room-btn").prop('disabled', false);
        $("#info-display").html('<div class="text-center"><div class="spinner-border text-primary"></div><p>Lade Details...</p></div>');

        $.ajax({
            url: `/get_location_details_by_id?id=${encodeURIComponent(id)}`,
            type: 'GET',
            success: function(response) {
                App.initialLocation = response.success ? response.location : null;
                displayLocationInfo(App.initialLocation);
            },
            error: function(jqXHR) {
                App.initialLocation = null;
                const msg = jqXHR.responseJSON?.message || "Serverfehler beim Abrufen der Raumdetails.";
                $("#info-display").html(`<div class="alert alert-warning">${msg}</div>`);
            }
        });
    }

    // GEÄNDERT: Prüft jetzt explizit das Format des QR-Codes und gibt bei anderen Typen eine Meldung aus
    const onScanSuccess = (decodedText, decodedResult) => {
        const codeFormat = decodedResult.result.format.formatName;
        const scannedCode = decodedText.trim();

        // Nur fortfahren, wenn es ein QR-Code ist
        if (codeFormat === "QR_CODE") {
            // Validierung: Prüft, ob es ein 6-stelliger Code ist, der mit 1 beginnt.
            if (/^1\d{5}$/.test(scannedCode)) {
                html5QrCode.pause();
                playBeep();

                // Füllt das Textfeld und startet die Suche automatisch
                $("#qr-code-id-field").val(scannedCode);
                triggerSearch(scannedCode);

                setTimeout(() => { if(html5QrCode.isScanning) html5QrCode.resume(); }, 1500);
            } else {
                // Wenn der QR-Code nicht dem Format entspricht, zeige eine kurze Nachricht
                showNotification("Ungültiger QR-Code. Bitte nur Raum-IDs scannen.");
            }
        } else {
            // Wenn ein anderer Barcode-Typ gescannt wird
            showNotification("Falscher Code-Typ. Bitte nur QR-Codes scannen.");
        }
    };

    function startCamera() {
        if (html5QrCode.isScanning) return;

        const config = {
            fps: 10,
            qrbox: { width: 250, height: 250 }
        };

        html5QrCode.start({ facingMode: "environment" }, config, onScanSuccess, () => {})
            .then(() => {
                const videoElement = document.getElementById("reader").querySelector("video");
                if (videoElement && videoElement.srcObject) {
                    const track = videoElement.srcObject.getVideoTracks()[0];
                    if (track) {
                        const capabilities = track.getCapabilities();
                        if (capabilities.torch) { App.videoTrack = track; $("#torch-btn").show(); }
                    }
                }
            })
            .catch(err => $("#reader").html(`<div class="alert alert-danger">Kamerafehler: ${err}</div>`));
    }

    function stopCamera() {
        if (html5QrCode.isScanning) {
            if (App.torchOn && App.videoTrack) {
                App.videoTrack.applyConstraints({ advanced: [{ torch: false }] });
                App.torchOn = false;
            }
            html5QrCode.stop().then(() => { App.videoTrack = null; $("#torch-btn").hide(); });
        }
    }

    $(".controls").on("click", "button.start", startCamera);
    $(".controls").on("click", "button.stop", stopCamera);
    $(".controls").on("click", "button.reset", () => {
        $("#info-display").html('<div class="card"><div class="card-body text-center text-muted">Bitte scannen oder geben Sie eine Raum-ID ein.</div></div>');
        $("#assign-room-btn").prop('disabled', true);
        $("#qr-code-id-field").val("");
        App.scannedCustomId = null;
        App.initialLocation = null;
    });

    $("#torch-btn").on("click", function() {
        if (App.videoTrack) { App.torchOn = !App.torchOn; App.videoTrack.applyConstraints({ advanced: [{ torch: App.torchOn }] }); }
    });

    // Event-Listener für das manuelle Eingabefeld mit neuer Validierung
    $("#qr-code-id-field").on("keypress", function(e) {
        if (e.which === 13) { // Enter-Taste
            const manualId = $(this).val().trim();
            // Validierung auf 6-stellige Zahl, die mit 1 beginnt
            if (/^1\d{5}$/.test(manualId)) {
                triggerSearch(manualId);
            } else {
                showInfoModal("Ungültige Eingabe", "Bitte eine 6-stellige ID, die mit '1' beginnt, eingeben.");
            }
        }
    });

    $("#assign-room-btn").on("click", function() {
        const currentId = App.scannedCustomId || $("#qr-code-id-field").val().trim();
        if (currentId) {
            $("#scanned-id-label").text(currentId);
            App.assignRoomModal.show();
        }
    });

    $("#new-room-btn").on("click", function() {
        App.assignRoomModal.hide();
        App.newRoomModal.show();
    });

    $("#create-new-location-btn").on("click", function() {
        const branchJson = $("#branch-select").val();
        const buildingZoneJson = $("#building-zone-select").val();
        const roomNumber = $("#room-number-input").val().trim();
        if (!branchJson || !buildingZoneJson || !roomNumber) {
            showInfoModal("Fehlende Informationen", "Bitte füllen Sie alle Felder aus.");
            return;
        }
        const payload = {
            branch: JSON.parse(branchJson),
            buildingZone: JSON.parse(buildingZoneJson),
            roomNumber: roomNumber
        };
        const $feedback = $("#assign-feedback");
        $feedback.html('<div class="spinner-border spinner-border-sm"></div> Raum wird angelegt...').removeClass().addClass('alert alert-info').show();
        App.newRoomModal.hide();
        $.ajax({
            url: "/create_new_location", type: "POST", data: JSON.stringify(payload),
            contentType: "application/json; charset=utf-8", dataType: "json",
            success: function(response) {
                if (response.success && response.newLocation) {
                    const newLocationUuid = response.newLocation.id;
                    $feedback.html('<div class="spinner-border spinner-border-sm"></div> Raum angelegt. Weise jetzt ID zu...');
                    $.ajax({
                        url: "/assign_custom_id_to_room", type: "POST",
                        data: JSON.stringify({ location_uuid: newLocationUuid, custom_room_id: App.scannedCustomId }),
                        contentType: "application/json; charset=utf-8", dataType: "json",
                        success: function(assignResponse) {
                            const alertClass = assignResponse.success ? 'alert-success' : 'alert-danger';
                            $feedback.removeClass('alert-info').addClass(`alert ${alertClass}`).text(assignResponse.message);
                            if (assignResponse.success) showNotification("Raum angelegt und ID zugewiesen!", false);
                        },
                        error: function() { $feedback.removeClass('alert-info').addClass('alert alert-danger').text("Fehler bei der ID-Zuweisung."); }
                    });
                } else {
                    $feedback.removeClass('alert-info').addClass('alert alert-danger').text("Fehler: " + response.message);
                }
            },
            error: function() {
                $feedback.removeClass('alert-info').addClass('alert alert-danger').text("Ein schwerwiegender Serverfehler ist aufgetreten.");
            }
        });
    });

    function showInfoModal(title, message) {
        $("#infoModalLabel").text(title);
        $("#infoModalBody").text(message);
        App.infoModal.show();
    }

    function showConfirmationModal(message, onConfirm) {
        $("#confirmationModalBody").text(message);
        $("#confirm-overwrite-btn").one("click", function() {
            App.confirmationModal.hide();
            onConfirm();
        });
        App.confirmationModal.show();
    }

    $("#confirm-assignment-btn").on("click", function() {
        const selectedOptionValue = $("#room-select-dropdown").val();
        if (!selectedOptionValue) {
            showInfoModal("Auswahl fehlt", "Bitte wählen Sie einen Raum aus der Liste aus.");
            return;
        }
        const selectedRoom = JSON.parse(selectedOptionValue);
        const selectedLocationUuid = selectedRoom.id;
        const existingCustomId = selectedRoom.optionalFields1?.text1;
        const currentId = App.scannedCustomId || $("#qr-code-id-field").val().trim();

        const doAssignment = () => {
            const $feedback = $("#assign-feedback");
            $feedback.html('<div class="spinner-border spinner-border-sm"></div> Zuweisung wird gespeichert...').removeClass().addClass('alert alert-info').show();
            $.ajax({
                url: "/assign_custom_id_to_room", type: "POST",
                data: JSON.stringify({ location_uuid: selectedLocationUuid, custom_room_id: currentId }),
                contentType: "application/json; charset=utf-8", dataType: "json",
                success: function(response) {
                    const alertClass = response.success ? 'alert-success' : 'alert-danger';
                    $feedback.removeClass('alert-info').addClass(alertClass).text(response.message);
                    if (response.success) showNotification("Zuweisung erfolgreich!", false);
                },
                error: function() { $feedback.removeClass('alert-info').addClass('alert alert-danger').text("Ein Serverfehler ist aufgetreten."); },
                complete: function() { App.assignRoomModal.hide(); }
            });
        };

        const checkSourceAndAssign = () => {
            if (App.initialLocation && App.initialLocation.id !== selectedLocationUuid) {
                showConfirmationModal(
                    `Die ID "${currentId}" ist bereits dem Raum "${App.initialLocation.name}" zugewiesen. Wirklich dem Raum "${selectedRoom.name}" zuweisen?`,
                    doAssignment
                );
            } else {
                doAssignment();
            }
        };

        if (existingCustomId && existingCustomId.trim() !== '' && existingCustomId.trim() !== currentId) {
            showConfirmationModal(
                `Der Zielraum "${selectedRoom.name}" hat bereits die ID "${existingCustomId}". Wirklich mit "${currentId}" überschreiben?`,
                checkSourceAndAssign
            );
        } else {
            checkSourceAndAssign();
        }
    });

    startCamera();
});
