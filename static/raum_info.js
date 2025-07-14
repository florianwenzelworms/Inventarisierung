// static/js/raum_info.js
$(function() {
    const App = {
        audioContext: null,
        videoTrack: null,
        torchOn: false
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

    function displayLocationInfo(location) {
        const $infoDisplay = $("#info-display");
        if (!location) {
            $infoDisplay.html('<div class="alert alert-danger">Raum nicht gefunden.</div>');
            return;
        }

        const building = location.buildingZone?.name || 'N/A';
        const branch = location.branch?.name || 'N/A';

        const infoHtml = `
            <div class="card">
                <div class="card-header bg-dark text-white">
                    <h5 class="mb-0">${location.name || 'Unbekannter Raum'}</h5>
                </div>
                <ul class="list-group list-group-flush">
                    <li class="list-group-item d-flex justify-content-between">
                        <strong>Gebäude:</strong>
                        <span>${building}</span>
                    </li>
                    <li class="list-group-item d-flex justify-content-between">
                        <strong>Raumnummer:</strong>
                        <span>${location.roomNumber || 'N/A'}</span>
                    </li>
                    <li class="list-group-item d-flex justify-content-between">
                        <strong>Niederlassung:</strong>
                        <span>${branch}</span>
                    </li>
                    <li class="list-group-item d-flex justify-content-between">
                        <strong>ID:</strong>
                        <code class="small">${location.id || 'N/A'}</code>
                    </li>
                </ul>
            </div>
        `;
        $infoDisplay.html(infoHtml);
    }

    const onScanSuccess = (decodedText, decodedResult) => {
        html5QrCode.pause();
        playBeep();

        const codeFormat = decodedResult.result.format.formatName;

        if (codeFormat === "QR_CODE") {
            const roomId = decodedText.trim();
            $("#info-display").html('<div class="text-center"><div class="spinner-border text-primary" role="status"></div><p>Lade Details...</p></div>');

            $.ajax({
                url: `/get_location_details_by_id?id=${encodeURIComponent(roomId)}`,
                type: 'GET',
                success: function(response) {
                    if (response.success) {
                        displayLocationInfo(response.location);
                    } else {
                        $("#info-display").html(`<div class="alert alert-danger">${response.message}</div>`);
                    }
                },
                error: function() {
                    $("#info-display").html('<div class="alert alert-danger">Serverfehler beim Abrufen der Raumdetails.</div>');
                },
                complete: function() {
                    setTimeout(() => { if(html5QrCode.isScanning) html5QrCode.resume(); }, 1500);
                }
            });
        } else {
            $("#info-display").html('<div class="alert alert-warning">Bitte scannen Sie einen gültigen Raum-QR-Code.</div>');
            setTimeout(() => { if(html5QrCode.isScanning) html5QrCode.resume(); }, 1500);
        }
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
        $("#info-display").html('<div class="card"><div class="card-body text-center text-muted">Bitte scannen Sie einen Raum-QR-Code, um die Details anzuzeigen.</div></div>');
    });

    $("#torch-btn").on("click", function() {
        if (App.videoTrack) { App.torchOn = !App.torchOn; App.videoTrack.applyConstraints({ advanced: [{ torch: App.torchOn }] }); }
    });

    startCamera();
});
