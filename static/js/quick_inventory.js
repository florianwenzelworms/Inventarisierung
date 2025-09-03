// static/js/quick_inventory.js
$(function() {
    const App = {
        inventory: [],
        activeRowIndex: -1,
        nextField: 'id',
        audioContext: null,
        videoTrack: null,
        torchOn: false
    };

    const html5QrCode = new Html5Qrcode("reader");

    function renderTable() {
        const $table = $(".table");
        const $tableHead = $table.find("thead");
        const $tableBody = $table.find("tbody");
        $tableHead.empty();
        $tableBody.empty();

        const selectedDeviceType = $("#model-name-select").val();
        const showMacColumn = ['Computer', 'Laptop', 'Telefon'].includes(selectedDeviceType);

        let headerHtml = '<tr><th>Geräte-ID</th><th>Seriennummer</th>';
        if (showMacColumn) {
            headerHtml += '<th>MAC-Adresse</th>';
        }
        headerHtml += '<th style="width: 50px;"></th></tr>';
        $tableHead.html(headerHtml);

        App.inventory.forEach((item, index) => {
            const idInputClass = (index === App.activeRowIndex && App.nextField === 'id') ? 'form-control form-control-sm bg-info-subtle' : 'form-control form-control-sm';
            const serialInputClass = (index === App.activeRowIndex && App.nextField === 'serial') ? 'form-control form-control-sm bg-info-subtle' : 'form-control form-control-sm';
            const macInputClass = (index === App.activeRowIndex && App.nextField === 'mac') ? 'form-control form-control-sm bg-info-subtle' : 'form-control form-control-sm';

            let rowHtml = `
                <tr>
                    <td><div class="input-group"><input type="text" class="${idInputClass}" value="${item.id}" data-index="${index}" data-field="id" placeholder="ID"><button class="btn btn-outline-secondary btn-sm na-btn" type="button" data-index="${index}" data-field="id">n/a</button></div></td>
                    <td><div class="input-group"><input type="text" class="${serialInputClass}" value="${item.serial}" data-index="${index}" data-field="serial" placeholder="Seriennr."><button class="btn btn-outline-secondary btn-sm na-btn" type="button" data-index="${index}" data-field="serial">n/a</button></div></td>`;

            if (showMacColumn) {
                rowHtml += `<td><div class="input-group"><input type="text" class="${macInputClass}" value="${item.mac}" data-index="${index}" data-field="mac" placeholder="MAC"><button class="btn btn-outline-secondary btn-sm na-btn" type="button" data-index="${index}" data-field="mac">n/a</button></div></td>`;
            }

            rowHtml += `<td><button class="btn btn-danger btn-sm delete-btn" data-index="${index}">&times;</button></td></tr>`;
            $tableBody.append(rowHtml);
        });
    }

    function playBeep() {
        try {
            if (!App.audioContext) App.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = App.audioContext.createOscillator();
            const gainNode = App.audioContext.createGain();
            oscillator.connect(gainNode);
            gainNode.connect(App.audioContext.destination);
            gainNode.gain.setValueAtTime(0, App.audioContext.currentTime);
            gainNode.gain.linearRampToValueAtTime(1, App.audioContext.currentTime + 0.01);
            let freq = 660;
            if (App.nextField === 'serial') freq = 880;
            if (App.nextField === 'mac') freq = 1046;
            oscillator.frequency.setValueAtTime(freq, App.audioContext.currentTime);
            oscillator.start(App.audioContext.currentTime);
            oscillator.stop(App.audioContext.currentTime + 0.1);
        } catch(e) {}
    }

    function showNotification(message, isError = true) {
        const $notification = $("#scan-notification");
        $notification.text(message).css('color', isError ? 'red' : 'green');
        $notification.css('opacity', 1).show();
        setTimeout(() => { $notification.css('opacity', 0); }, 1500);
    }

    function findAndSetNextTarget() {
        const showMacColumn = ['Computer', 'Laptop', 'Telefon'].includes($("#model-name-select").val());
        for (let i = 0; i < App.inventory.length; i++) {
            if (App.inventory[i].id.trim() === '') { App.activeRowIndex = i; App.nextField = 'id'; return; }
            if (App.inventory[i].serial.trim() === '') { App.activeRowIndex = i; App.nextField = 'serial'; return; }
            if (showMacColumn && App.inventory[i].mac.trim() === '') { App.activeRowIndex = i; App.nextField = 'mac'; return; }
        }
        App.inventory.push({ id: '', serial: '', mac: '' });
        App.activeRowIndex = App.inventory.length - 1;
        App.nextField = 'id';
    }

    const onScanSuccess = (decodedText, decodedResult) => {
        html5QrCode.pause();
        const currentItem = App.inventory[App.activeRowIndex];
        const currentIndex = App.activeRowIndex;
        if ((App.nextField === 'serial' && currentItem.id === decodedText) || (App.nextField === 'mac' && (currentItem.id === decodedText || currentItem.serial === decodedText))) {
            showNotification("Wert in dieser Zeile bereits vorhanden!");
            setTimeout(() => html5QrCode.resume(), 500);
            return;
        }
        playBeep();
        if (App.nextField === 'id') { currentItem.id = decodedText; App.nextField = 'serial';
        } else if (App.nextField === 'serial') { currentItem.serial = decodedText;
            if (['Computer', 'Laptop', 'Telefon'].includes($("#model-name-select").val())) {
                App.nextField = 'mac';
            } else {
                checkDuplicateAndProceed(currentItem, currentIndex);
            }
        } else if (App.nextField === 'mac') {
            currentItem.mac = decodedText;
            checkDuplicateAndProceed(currentItem, currentIndex);
        }
        renderTable();
        setTimeout(() => html5QrCode.resume(), 500);
    };

    function checkDuplicateAndProceed(currentItem, currentIndex) {
        let isDuplicate = false;
        const showMacColumn = ['Computer', 'Laptop', 'Telefon'].includes($("#model-name-select").val());
        const idOk = currentItem.id.trim() && currentItem.id !== 'n/a';
        const serialOk = currentItem.serial.trim() && currentItem.serial !== 'n/a';
        const macOk = !showMacColumn || (currentItem.mac.trim() && currentItem.mac !== 'n/a');
        if (idOk && serialOk && macOk) {
             for (let i = 0; i < App.inventory.length; i++) {
                if (i === currentIndex) continue;
                const otherItem = App.inventory[i];
                const idMatch = otherItem.id === currentItem.id;
                const serialMatch = otherItem.serial === currentItem.serial;
                const macMatch = !showMacColumn || (otherItem.mac === currentItem.mac);
                if (idMatch && serialMatch && macMatch) {
                    isDuplicate = true; break;
                }
            }
        }
        if (isDuplicate) {
            showNotification("Gerät bereits erfasst!");
            currentItem.id = ''; currentItem.serial = ''; currentItem.mac = '';
            App.nextField = 'id';
        } else {
            findAndSetNextTarget();
        }
    }

    function startCamera() {
        if (html5QrCode.isScanning) return;
        html5QrCode.start({ facingMode: "environment" }, { fps: 10, qrbox: { width: 250, height: 250 },advanced: [{focusMode: "manual"}] }, onScanSuccess, () => {})
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
        stopCamera();
        App.inventory = [];
        $("#model-name-select").val("");
        $("#model-name-field").val("");
        findAndSetNextTarget();
        renderTable();
    });

    $("#torch-btn").on("click", function() {
        if (App.videoTrack) { App.torchOn = !App.torchOn; App.videoTrack.applyConstraints({ advanced: [{ torch: App.torchOn }] }); }
    });

    $("#model-name-select").on("change", function() {
        renderTable();
    });

    $("#inventory-table-body").on("click", "input", function() {
        const index = $(this).data("index");
        const field = $(this).data("field");
        App.activeRowIndex = index;
        App.nextField = field;
        renderTable();
    });

    $("#inventory-table-body").on("click", ".na-btn", function() {
        const index = $(this).data("index");
        const field = $(this).data("field");
        App.inventory[index][field] = "n/a";
        const item = App.inventory[index];
        const showMacColumn = ['Computer', 'Laptop', 'Telefon'].includes($("#model-name-select").val());
        if (item.id && item.serial && (item.mac || !showMacColumn)) {
            findAndSetNextTarget();
        }
        renderTable();
    });

    $("#inventory-table-body").on("click", ".delete-btn", function() {
        const index = $(this).data("index");
        App.inventory.splice(index, 1);
        if (App.inventory.length === 0) {
            findAndSetNextTarget();
        } else if (App.activeRowIndex >= index) {
            findAndSetNextTarget();
        }
        renderTable();
    });

    $("#inventory-table-body").on("change", "input", function() {
        const index = $(this).data("index");
        const field = $(this).data("field");
        App.inventory[index][field] = $(this).val();
    });

    $("#save-inventory-btn").on("click", function() {
        const $button = $(this);
        const $feedback = $("#save-feedback");
        const showMacColumn = ['Computer', 'Laptop', 'Telefon'].includes($("#model-name-select").val());

        const finalInventory = App.inventory.filter(item => {
            const idOk = item.id.trim();
            const serialOk = item.serial.trim();
            if (showMacColumn) {
                return idOk && serialOk && item.mac.trim();
            }
            return idOk && serialOk;
        });

        if (finalInventory.length === 0) {
            alert("Bitte erfassen Sie mindestens ein vollständiges Gerät.");
            return;
        }

        const deviceType = $("#model-name-select").val() || '';
        const modelName = $("#model-name-field").val().trim();
        const payload = { assets: finalInventory, deviceType: deviceType, modelName: modelName };

        $button.prop('disabled', true).text('Speichere...');
        $feedback.empty().removeClass();

        $.ajax({
            url: "/save_new_assets", type: "POST",
            data: JSON.stringify(payload),
            contentType: "application/json; charset=utf-8", dataType: "json",
            success: function(response) {
                $feedback.addClass('alert alert-success').html(`<h6>${response.message}</h6>`);
                $(".controls button.reset").trigger("click");
            },
            error: function(response) {
                const errorMsg = response.responseJSON ? response.responseJSON.message : "Ein Serverfehler ist aufgetreten.";
                $feedback.addClass('alert alert-danger').text(errorMsg);
            },
            complete: function() {
                $button.prop('disabled', false).text('Inventur speichern');
            }
        });
    });

    function initialize() {
        App.inventory = [];
        findAndSetNextTarget();
        renderTable();
        startCamera(); // Kamera automatisch starten
    }

    initialize();
});
