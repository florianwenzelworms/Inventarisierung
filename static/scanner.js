var _scannerIsRunning = false;

function startScanner() {
    Quagga.init({
        inputStream: {
            name: "Live",
            type: "LiveStream",
            target: document.querySelector('#scanner-container'),
            constraints: {
                width: 480,
                height: 320,
                facingMode: "environment"
            },
        },
        decoder: {
            reader: "code_128_reader",
            debug: {
                showCanvas: true,
                showPatches: true,
                showFoundPatches: true,
                showSkeleton: true,
                showLabels: true,
                showPatchLabels: true,
                showRemainingPatchLabels: true,
                boxFromPatches: {
                    showTransformed: true,
                    showTransformedBox: true,
                    showBB: true
                }
            }
        },

    }, function (err) {
        if (err) {
            console.log(err);
            return
        }

        console.log("Initialization finished. Ready to start");
        Quagga.start();

        // Set flag to is running
        _scannerIsRunning = true;
    });

    Quagga.onProcessed(function (result) {
        var drawingCtx = Quagga.canvas.ctx.overlay,
        drawingCanvas = Quagga.canvas.dom.overlay;

        if (result) {
            if (result.boxes) {
                drawingCtx.clearRect(0, 0, parseInt(drawingCanvas.getAttribute("width")), parseInt(drawingCanvas.getAttribute("height")));
                result.boxes.filter(function (box) {
                    return box !== result.box;
                }).forEach(function (box) {
                    Quagga.ImageDebug.drawPath(box, { x: 0, y: 1 }, drawingCtx, { color: "green", lineWidth: 2 });
                });
            }

            if (result.box) {
                Quagga.ImageDebug.drawPath(result.box, { x: 0, y: 1 }, drawingCtx, { color: "#00F", lineWidth: 2 });
            }

            if (result.codeResult && result.codeResult.code) {
                Quagga.ImageDebug.drawPath(result.line, { x: 'x', y: 'y' }, drawingCtx, { color: 'red', lineWidth: 3 });
            }
        }
    });

    function isRoom(item_id) {
        return item_id.includes("Raum");
    }

    Quagga.onDetected(function (result) {
        var item_id = result.codeResult.code;
        console.log("Barcode detected and processed : [" + item_id + "]", result);
        alert("Barcode detected and processed : [" + item_id + "]");
        if (isRoom(item_id)) {
            document.getElementById("raumfeld").value = result.codeResult.code;
        } else {
            document.getElementById("nummerfeld").value = result.codeResult.code;
        }

    });
}


// Start/stop scanner
//startScanner();
document.getElementById("btn").addEventListener("click", function () {
if (_scannerIsRunning) {
    Quagga.stop();
    _scannerIsRunning = false;
    document.getElementById("scanner-container").innerHTML = "";
} else {
    startScanner();
    _scannerIsRunning = true;
    }
}, false);