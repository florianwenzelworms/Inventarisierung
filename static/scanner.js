/**Quagga initialiser starts here*/

$(function() {
    var value;
    var App = {
        init : function() {
            Quagga.init(this.state, function(err) {
                if (err) {
                    console.log(err);
                    return;
                }
                App.attachListeners();
                Quagga.start();
            });
        },
        initCameraSelection: function(){
            var streamLabel = Quagga.CameraAccess.getActiveStreamLabel();

            return Quagga.CameraAccess.enumerateVideoDevices()
                .then(function(devices) {
                    function pruneText(text) {
                        return text.length > 30 ? text.substr(0, 30) : text;
                    }
                    var $deviceSelection = document.getElementById("deviceSelection");
                    while ($deviceSelection.firstChild) {
                        $deviceSelection.removeChild($deviceSelection.firstChild);
                    }
                    devices.forEach(function(device) {
                        var $option = document.createElement("option");
                        $option.value = device.deviceId || device.id;
                        $option.appendChild(document.createTextNode(pruneText(device.label || device.deviceId || device.id)));
                        $option.selected = streamLabel === device.label;
                        $deviceSelection.appendChild($option);
                    });
                });
        },
        querySelectedReaders: function() {
            return Array.prototype.slice.call(document.querySelectorAll('.readers input[type=checkbox]'))
                .filter(function(element) {
                    return !!element.checked;
                })
                .map(function(element) {
                    return element.getAttribute("name");
                });
        },
        attachListeners: function() {
            var self = this;

            self.initCameraSelection();
            $(".controls").on("click", "button.stop", function(e) {
                e.preventDefault();
                Quagga.stop();
            });

            $(".controls .reader-config-group").on("change", "input, select", function(e) {
                e.preventDefault();
                var $target = $(e.target);
                // value = $target.attr("type") === "checkbox" ? $target.prop("checked") : $target.val(),
                value =  $target.attr("type") === "checkbox" ? this.querySelectedReaders() : $target.val();
                var  name = $target.attr("name"),
                    state = self._convertNameToState(name);

                console.log("Value of "+ state + " changed to " + value);
                self.setState(state, value);
            });
        },
        _accessByPath: function(obj, path, val) {
            var parts = path.split('.'),
                depth = parts.length,
                setter = (typeof val !== "undefined") ? true : false;

            return parts.reduce(function(o, key, i) {
                if (setter && (i + 1) === depth) {
                    if (typeof o[key] === "object" && typeof val === "object") {
                        Object.assign(o[key], val);
                    } else {
                        o[key] = val;
                    }
                }
                return key in o ? o[key] : {};
            }, obj);
        },
        _convertNameToState: function(name) {
            return name.replace("_", ".").split("-").reduce(function(result, value) {
                return result + value.charAt(0).toUpperCase() + value.substring(1);
            });
        },
        detachListeners: function() {
            $(".controls").off("click", "button.stop");
            $(".controls .reader-config-group").off("change", "input, select");
        },
        setState: function(path, value) {
            var self = this;

            if (typeof self._accessByPath(self.inputMapper, path) === "function") {
                value = self._accessByPath(self.inputMapper, path)(value);
            }

            self._accessByPath(self.state, path, value);

            console.log(JSON.stringify(self.state));
            App.detachListeners();
            Quagga.stop();
            App.init();
        },
        inputMapper: {
            inputStream: {
                constraints: function(value){
                    if (/^(\d+)x(\d+)$/.test(value)) {
                        var values = value.split('x');
                        return {
                            width: {min: parseInt(values[0])},
                            height: {min: parseInt(values[1])}
                        };
                    }
                    return {
                        deviceId: value
                    };
                }
            },
            numOfWorkers: function(value) {
                return parseInt(value);
            },
            decoder: {
                readers: function(value) {
                    if (value === 'ean_extended') {
                        return [{
                            format: "ean_reader",
                            config: {
                                supplements: [
                                    'ean_5_reader', 'ean_2_reader'
                                ]
                            }
                        }];
                    }
                    console.log("value before format :"+value);
                    return [{
                        format: value + "_reader",
                        config: {}
                    }];
                }
            }
        },
        state: {
            inputStream: {
                type : "LiveStream",
                constraints: {
                    width: {min: 480},
                    height: {min: 320},
                    aspectRatio: {min: 1, max: 100},
                    facingMode: "environment" // or user
                }
            },
            locator: {
                patchSize: "large",
                halfSample: true
            },
            numOfWorkers: 4,
            decoder: {
                readers : ["code_39_reader","code_128_reader"]
            },
            locate: true,
            multiple:true
        },
        lastResult : [],
        mailContent: []
    };

    //value =  App.querySelectedReaders() ;
    App.init();

    $(".controls").on("click", "button.start", function(e) {
        e.preventDefault();
        App.init();
    });

    $(".controls").on("click", "button.reset", function(e) {
        e.preventDefault();
        document.getElementsByClassName("thumbnails")[0].innerHTML = "";
        App.lastResult = [];
        App.mailContent = [];
    });

    $(".controls").on("click", "button.send", function(e) {
        if (document.getElementById("raumfeld").value === "") {
            alert("Noch keine Rauminformation eingegeben");
            return;
        } else if (App.lastResult.length === 0) {
            alert("Noch keine Geräte gescannt");
            return;
        } else {
            if (!App.mailContent[0].hasOwnProperty('Text')) {
                App.mailContent.unshift({"Text": document.getElementById("raumfeld").value});
            } else {
                App.mailContent[0]["Text"] = document.getElementById("raumfeld").value;
            }
            console.log(App.mailContent);
            jQuery.ajax ({
                url: "/save",
                type: "POST",
                data: JSON.stringify(App.mailContent),
                dataType: "json",
                contentType: "application/json; charset=utf-8",
                complete: function(){
                    document.getElementsByClassName("thumbnails")[0].innerHTML = "";
                    document.getElementById("raumfeld").value = "";
                    App.lastResult = [];
                    App.mailContent = [];
                }
            });
        }
    });

    Quagga.onProcessed(function(result) {
        var drawingCtx = Quagga.canvas.ctx.overlay,
            drawingCanvas = Quagga.canvas.dom.overlay;

        if (result) {
            if (result.boxes) {
                drawingCtx.clearRect(0, 0, parseInt(drawingCanvas.getAttribute("width")), parseInt(drawingCanvas.getAttribute("height")));
                result.boxes.filter(function (box) {
                    return box !== result.box;
                }).forEach(function (box) {
                    Quagga.ImageDebug.drawPath(box, {x: 0, y: 1}, drawingCtx, {color: "green", lineWidth: 2});
                });
            }

            if (result.box) {
                Quagga.ImageDebug.drawPath(result.box, {x: 0, y: 1}, drawingCtx, {color: "#00F", lineWidth: 2});
            }

            if (result.codeResult && result.codeResult.code) {
                Quagga.ImageDebug.drawPath(result.line, {x: 'x', y: 'y'}, drawingCtx, {color: 'red', lineWidth: 3});
            }
        }
    });

    Quagga.onDetected(function(result) {
        var code = result.codeResult.code;

        if (App.lastResult.includes(code) === false) {
            App.lastResult.push(code);
            var $node = null, canvas = Quagga.canvas.dom.image;
            $node = $('<li><div class="thumbnail"><div class="imgWrapper"><img /></div><div class="caption"><h4 class="code"></h4></div></div></li>');
            $node.find("img").attr("src", canvas.toDataURL());
            $node.find("h4.code").html(code);
            $("#result_strip ul.thumbnails").prepend($node);
            App.mailContent.push({"code":code, "img":canvas.toDataURL()})
        }
    });
});