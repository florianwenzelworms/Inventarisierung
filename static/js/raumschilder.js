// static/js/raumschilder.js
$(document).ready(function() {

    const imageModal = new bootstrap.Modal(document.getElementById('imageModal'));
    const modalImage = document.getElementById('modalImage');

    $('tbody').on('click', '.qr-preview', function() {
        const imageSource = $(this).attr('src');
        $(modalImage).attr('src', imageSource);
        imageModal.show();
    });

    function downloadFile(url, filename) {
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }

    function generateQrCodes(roomsData, buttonElement) {
        if (roomsData.length === 0) {
            alert("Bitte wählen Sie mindestens einen Raum aus.");
            return;
        }
        const $feedbackArea = $("#feedback-area");
        const originalButtonHtml = buttonElement.html();
        buttonElement.prop('disabled', true).html('<span class="spinner-border spinner-border-sm"></span> Erstelle...');
        $feedbackArea.show().removeClass().addClass('alert alert-info').html('QR-Codes werden erstellt...');

        $.ajax({
            url: "/generate_qr_codes", type: "POST", data: JSON.stringify(roomsData), contentType: "application/json; charset=utf-8", dataType: "json",
            success: function(response) {
                let feedbackHtml = `<strong>${response.message}</strong>`;
                if (response.errors && response.errors.length > 0) {
                    feedbackHtml += '<ul>';
                    response.errors.forEach(err => feedbackHtml += `<li><small>${err}</small></li>`);
                    feedbackHtml += '</ul>';
                }

                if (response.success) {
                    $feedbackArea.removeClass('alert-info').addClass('alert-success').html(feedbackHtml);
                    setTimeout(() => window.location.reload(), 1500);
                } else {
                    $feedbackArea.removeClass('alert-info').addClass('alert-danger').html(feedbackHtml);
                }
            },
            error: function() {
                $feedbackArea.show().removeClass().addClass('alert alert-danger').text("Ein schwerwiegender Serverfehler ist aufgetreten.");
            },
            complete: function() {
                buttonElement.prop('disabled', false).html(originalButtonHtml);
            }
        });
    }

    function downloadAsZip(rows, zipFilename, buttonElement) {
        const $feedbackArea = $("#feedback-area");
        if (rows.length === 0) {
            alert("Keine erstellten Bilder für den Download ausgewählt.");
            return;
        }
        const originalButtonHtml = buttonElement.html();
        buttonElement.prop('disabled', true).html('<span class="spinner-border spinner-border-sm"></span> Zippe...');
        $feedbackArea.show().removeClass().addClass('alert alert-info').text(`Erstelle ZIP-Datei '${zipFilename}'...`);

        const zip = new JSZip();
        const promises = [];

        rows.each(function() {
            const $img = $(this).find('.qr-preview');
            if ($img.length) {
                const url = $img.attr('src');
                const roomData = $(this).data('room-json');
                const filename = roomData.filename;

                const promise = fetch(url)
                    .then(response => response.blob())
                    .then(blob => {
                        zip.file(filename, blob);
                    });
                promises.push(promise);
            }
        });

        Promise.all(promises).then(() => {
            zip.generateAsync({ type: "blob" }).then(function(content) {
                const url = URL.createObjectURL(content);
                downloadFile(url, zipFilename);
                URL.revokeObjectURL(url);
                $feedbackArea.removeClass('alert-info').addClass('alert-success').text(`ZIP-Datei '${zipFilename}' erfolgreich erstellt.`);
            });
        }).catch(err => {
            $feedbackArea.removeClass('alert-info').addClass('alert-danger').text("Fehler beim Erstellen der ZIP-Datei.");
        }).finally(() => {
            buttonElement.prop('disabled', false).html(originalButtonHtml);
        });
    }

    $('.generate-single-btn').on('click', function() {
        const roomData = $(this).closest('tr').data('room-json');
        generateQrCodes([roomData], $(this));
    });

    $('#generate-selected-btn').on('click', function() {
        const selectedRooms = $('.room-checkbox:checked').map(function() {
            return $(this).closest('tr').data('room-json');
        }).get();
        generateQrCodes(selectedRooms, $(this));
    });

    $('#generate-all-btn').on('click', function() {
        const allRooms = $('tbody tr').map(function() {
            return $(this).data('room-json');
        }).get();
        generateQrCodes(allRooms, $(this));
    });

    $('tbody').on('click', '.download-single-btn', function() {
        const $row = $(this).closest('tr');
        const $img = $row.find('.qr-preview');
        if($img.length) {
            const roomData = $row.data('room-json');
            downloadFile($img.attr('src'), roomData.filename);
        }
    });

    $('#download-selected-btn').on('click', function() {
        const selectedRows = $('.room-checkbox:checked').closest('tr');
        downloadAsZip(selectedRows, 'Raumschilder_Auswahl.zip', $(this));
    });

    $('#download-all-btn').on('click', function() {
        const allRows = $('tbody tr');
        downloadAsZip(allRows, 'Raumschilder_Alle.zip', $(this));
    });

    $('#select-all-checkbox').on('change', function() {
        $('.room-checkbox').prop('checked', $(this).prop('checked'));
    });
});
