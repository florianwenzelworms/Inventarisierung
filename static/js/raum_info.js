$(function() {
    const App = {
        audioContext: null,
        videoTrack: null,
        torchOn: false,
        scannedCustomId: null, // Speichert die zuletzt gescannte 6-stellige ID
        initialLocation: null, // Speichert das Ergebnis des ersten Scans
        assignRoomModal: new bootstrap.Modal(document.getElementById('assignRoomModal'))
    };

    const html5QrCode = new Html5Qrcode("reader");

    function playBeep() {
        try {
            if (!App.audioContext) App.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = App.audioContext.createOscillator();
            const gainNode = App.audioContext.createGain();
            oscillator.connect(gainNode);
            gainNode.connect(App.audioContext.destination);
            gainNode.gain.setValueAtTime(0, App.audioContext.currentTime);
            gainNode.gain.linearRampToValueAtTime(1, App.audioContext.currentTime + 0.01);
            oscillator.frequency.setValueAtTime(880, App.audioContext.currentTime);
            oscillator.start(App.audioContext.currentTime);
            oscillator.stop(App.audioContext.currentTime + 0.1);
        } catch(e) {}
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

        // GEÄNDERT: Die Anzeige der IDs wurde angepasst
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

    const onScanSuccess = (decodedText, decodedResult) => {
        html5QrCode.pause();
        playBeep();

        const codeFormat = decodedResult.result.format.formatName;
        if (codeFormat !== "QR_CODE" || decodedText.trim().length !== 6) {
            showNotification("Bitte einen gültigen 6-stelligen Raum-QR-Code scannen.");
            setTimeout(() => { if(html5QrCode.isScanning) html5QrCode.resume(); }, 1500);
            return;
        }

        const roomId = decodedText.trim();
        App.scannedCustomId = roomId; // Die gescannte ID speichern
        $("#assign-room-btn").prop('disabled', false); // Den Zuweisen-Button aktivieren
        $("#info-display").html('<div class="text-center"><div class="spinner-border text-primary"></div><p>Lade Details...</p></div>');

        $.ajax({
            url: `/get_location_details_by_id?id=${encodeURIComponent(roomId)}`,
            type: 'GET',
            success: function(response) {
                if (response.success) {
                    App.initialLocation = response.location; // Das gefundene Objekt speichern
                    displayLocationInfo(response.location);
                } else {
                    App.initialLocation = null;
                    // GEÄNDERT: Zeigt jetzt die spezifische Fehlermeldung an
                    $("#info-display").html(`<div class="alert alert-warning">${response.message}</div>`);
                }
            },
            error: function(jqXHR) {
                App.initialLocation = null;
                if (jqXHR.responseJSON && jqXHR.responseJSON.message) {
                    $("#info-display").html(`<div class="alert alert-warning">${jqXHR.responseJSON.message}</div>`);
                } else {
                    $("#info-display").html('<div class="alert alert-danger">Serverfehler beim Abrufen der Raumdetails.</div>');
                }
            },
            complete: function() {
                setTimeout(() => { if(html5QrCode.isScanning) html5QrCode.resume(); }, 1500);
            }
        });
    };

    function startCamera() {
        if (html5QrCode.isScanning) return;
        html5QrCode.start({ facingMode: "environment" }, { fps: 10, qrbox: { width: 250, height: 250 } }, onScanSuccess, () => {})
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
        $("#info-display").html('<div class="card"><div class="card-body text-center text-muted">Bitte scannen Sie einen Raum-QR-Code.</div></div>');
        $("#assign-room-btn").prop('disabled', true);
        App.scannedCustomId = null;
        App.initialLocation = null;
    });

    $("#torch-btn").on("click", function() {
        if (App.videoTrack) { App.torchOn = !App.torchOn; App.videoTrack.applyConstraints({ advanced: [{ torch: App.torchOn }] }); }
    });

    $("#assign-room-btn").on("click", function() {
        if (App.scannedCustomId) {
            $("#scanned-id-label").text(App.scannedCustomId);
            App.assignRoomModal.show();
        }
    });

    $("#confirm-assignment-btn").on("click", function() {
        const selectedLocationUuid = $("#room-select-dropdown").val();
        if (!selectedLocationUuid) {
            alert("Bitte wählen Sie einen Raum aus der Liste aus.");
            return;
        }

        let proceed = true;
        if (App.initialLocation) {
            proceed = confirm(`Die ID "${App.scannedCustomId}" ist bereits dem Raum "${App.initialLocation.name}" zugewiesen.\nMöchten Sie sie wirklich dem neu ausgewählten Raum zuweisen?`);
        }

        if (proceed) {
            const $feedback = $("#assign-feedback");
            $feedback.html('<div class="spinner-border spinner-border-sm"></div> Zuweisung wird gespeichert...').removeClass().addClass('alert alert-info').show();

            $.ajax({
                url: "/assign_custom_id_to_room",
                type: "POST",
                data: JSON.stringify({
                    location_uuid: selectedLocationUuid,
                    custom_room_id: App.scannedCustomId
                }),
                contentType: "application/json; charset=utf-8",
                dataType: "json",
                success: function(response) {
                    const alertClass = response.success ? 'alert-success' : 'alert-danger';
                    $feedback.removeClass('alert-info').addClass(alertClass).text(response.message);
                    if (response.success) {
                        showNotification("Zuweisung erfolgreich!", false);
                    }
                },
                error: function() {
                    $feedback.removeClass('alert-info').addClass('alert-danger').text("Ein Serverfehler ist aufgetreten.");
                },
                complete: function() {
                    App.assignRoomModal.hide();
                }
            });
        }
    });

    startCamera();
});
