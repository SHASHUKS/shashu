let html5QrCode = null;
let statusBar = null;

document.addEventListener("DOMContentLoaded", function() {
    statusBar = document.getElementById('status-bar');

    if (typeof Html5Qrcode === "undefined") {
        if (statusBar) {
            statusBar.innerHTML = "⚠️ QR Library failed to load. Check internet connection.";
            statusBar.style.backgroundColor = "#fee2e2";
            statusBar.style.color = "#991b1b";
        }
        return;
    }

    html5QrCode = new Html5Qrcode("reader");

    // Start Camera Button Listener
    const btnStart = document.getElementById('btn-start');
    if (btnStart) {
        btnStart.addEventListener('click', () => {
            startCamera();
        });
    }

    // Stop Camera Button Listener
    const btnStop = document.getElementById('btn-stop');
    if (btnStop) {
        btnStop.addEventListener('click', () => {
            if (html5QrCode && html5QrCode.isScanning) {
                html5QrCode.stop().then(() => {
                    if (statusBar) {
                        statusBar.innerHTML = "⏸️ Camera paused. Click 'Start Camera' to resume.";
                        statusBar.style.backgroundColor = "#e0e7ff";
                        statusBar.style.color = "#3730a3";
                    }
                }).catch(() => {});
            }
        });
    }

    // Upload Button Listener
    const btnUpload = document.getElementById('btn-upload');
    const qrInputFile = document.getElementById('qr-input-file');

    if (btnUpload && qrInputFile) {
        btnUpload.addEventListener('click', () => qrInputFile.click());

        qrInputFile.addEventListener('change', (e) => {
            if (e.target.files.length === 0) return;

            const processImageFile = () => {
                if (statusBar) {
                    statusBar.innerHTML = "⏳ Decoding uploaded QR image...";
                    statusBar.style.backgroundColor = "#e0e7ff";
                    statusBar.style.color = "#3730a3";
                }

                html5QrCode.scanFile(e.target.files[0], false).then(decodedText => {
                    handleSuccessfulScan(decodedText);
                }).catch(() => {
                    if (statusBar) {
                        statusBar.innerHTML = "⚠️ No readable QR code found in this image.";
                        statusBar.style.backgroundColor = "#fee2e2";
                        statusBar.style.color = "#991b1b";
                    }
                });
                
                e.target.value = '';
            };

            if (html5QrCode && html5QrCode.isScanning) {
                html5QrCode.stop().then(processImageFile).catch(processImageFile);
            } else {
                processImageFile();
            }
        });
    }
});

// ---------------------------------------------------------
// START CAMERA FUNCTION
// ---------------------------------------------------------
function startCamera() {
    if (statusBar) {
        statusBar.innerHTML = "⏳ Requesting camera access...";
        statusBar.style.backgroundColor = "#fef3c7";
        statusBar.style.color = "#92400e";
    }

    const config = { fps: 10, qrbox: { width: 250, height: 250 } };
    
    if (!html5QrCode) return;

    // Stop existing stream if running, then start fresh
    const runScan = () => {
        html5QrCode.start({ facingMode: "environment" }, config, handleSuccessfulScan, () => {})
        .then(() => {
            if (statusBar) {
                statusBar.innerHTML = "📷 Camera active. Point at a track fitting QR code.";
                statusBar.style.backgroundColor = "#ccfbf1";
                statusBar.style.color = "#0f766e";
            }
        })
        .catch(err => {
            // Fallback to front camera
            html5QrCode.start({ facingMode: "user" }, config, handleSuccessfulScan, () => {})
            .then(() => {
                if (statusBar) {
                    statusBar.innerHTML = "📷 Front camera active.";
                    statusBar.style.backgroundColor = "#ccfbf1";
                    statusBar.style.color = "#0f766e";
                }
            })
            .catch(err2 => {
                if (statusBar) {
                    statusBar.innerHTML = "⚠️ Camera Blocked or In Use. Please use 'Upload Image'.";
                    statusBar.style.backgroundColor = "#fee2e2";
                    statusBar.style.color = "#991b1b";
                }
            });
        });
    };

    if (html5QrCode.isScanning) {
        html5QrCode.stop().then(runScan).catch(runScan);
    } else {
        runScan();
    }
}

// ---------------------------------------------------------
// SUCCESSFUL SCAN HANDLER
// ---------------------------------------------------------
function handleSuccessfulScan(decodedText) {
    const cleanText = decodedText.trim();
    const assetInput = document.getElementById('asset_id');
    if (assetInput) {
        assetInput.value = cleanText;
    }

    if (statusBar) {
        statusBar.innerHTML = `✅ Asset Found: <b>${cleanText}</b>.<br>Select an inspector grade below to run AI prediction.`;
        statusBar.style.backgroundColor = "#ccfbf1";
        statusBar.style.color = "#0f766e";
    }

    if (html5QrCode && html5QrCode.isScanning) {
        html5QrCode.stop().catch(() => {});
    }
}

// ---------------------------------------------------------
// MACHINE LEARNING API PREDICTION
// ---------------------------------------------------------
function runAIPrediction(gradeInput) {
    const assetInput = document.getElementById('asset_id');
    const asset_id = assetInput ? assetInput.value.trim() : "";
    
    if (!asset_id) {
        alert("Please scan or upload a valid track fitting QR code first!");
        return;
    }

    let rustGrade = 1;
    if (typeof gradeInput === 'string') {
        const match = gradeInput.match(/\d+/);
        if (match) rustGrade = parseInt(match[0]);
    } else if (typeof gradeInput === 'number') {
        rustGrade = gradeInput;
    }

    // Dynamic Zone and GPS Detection
    const zoneElement = document.getElementById('zone-select') || document.getElementById('selected-zone');
    const zoneValue = zoneElement ? (zoneElement.value || zoneElement.innerText) : "Southern Railway (HQ: Chennai Central)";

    const gpsElement = document.getElementById('gps-coords');
    const gpsValue = gpsElement ? gpsElement.innerText.replace(/Coords:\s*/i, '').trim() : '12.800058, 77.706495';

    if (statusBar) {
        statusBar.innerHTML = "⏳ Running Random Forest AI Prediction...";
        statusBar.style.backgroundColor = "#fef3c7";
        statusBar.style.color = "#92400e";
    }

    fetch('/api/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            asset_id: asset_id,
            rust_grade: rustGrade,
            zone: zoneValue,
            location: gpsValue
        }) 
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`Server returned HTTP ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (data.error) {
            if (statusBar) {
                statusBar.innerHTML = "⚠️ ML Error: " + data.error;
                statusBar.style.backgroundColor = "#fee2e2";
                statusBar.style.color = "#991b1b";
            }
        } else {
            const isGood = (data.status === 'Good' || data.status === 'Healthy');
            const displayStatus = data.status === 'Healthy' ? 'Good' : data.status;

            if (statusBar) {
                statusBar.style.backgroundColor = isGood ? "#d1fae5" : "#fee2e2";
                statusBar.style.color = isGood ? "#065f46" : "#991b1b";
                
                statusBar.innerHTML = `🎯 <b>AI Analysis Complete!</b><br>
                Asset: <b>${data.asset_id}</b><br>
                Live Conditions: <b>${data.weather}</b> | <b>${data.traffic_load}</b><br>
                Predicted Lifespan: <b style="font-size: 16px;">${data.predicted_rul} Years Remaining</b><br>
                System Status: <b>${displayStatus}</b>`;
            }
        }
    })
    .catch(err => {
        if (statusBar) {
            statusBar.innerHTML = "❌ Server Connection Error: " + err.message;
            statusBar.style.backgroundColor = "#fee2e2";
            statusBar.style.color = "#991b1b";
        }
    });
}