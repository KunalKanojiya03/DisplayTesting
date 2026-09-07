# Display Utility V3.0

A PyQt5 desktop application for automated **LCD/LED display testing and verification**, using **YOLOv5** for computer-vision-based detection and **Modbus/Serial** communication to interface with connected hardware.

---

## Overview

Display Utility is used to visually inspect and validate LCD/LED displays via a webcam feed. It captures live frames, runs YOLOv5 inference to detect and read display content, and reports pass/fail results back over Modbus — with configurable camera, detection, and communication parameters, plus built-in reporting.

**Core capabilities:**
- 📷 Live camera capture with ROI cropping and rotation calibration
- 🧠 YOLOv5-based detection for both LCD and LED display types
- 🔌 Serial (COM port) and Modbus RTU communication with connected devices
- 📊 Inference logging (CSV) and PDF report generation
- 🖥️ PyQt5 GUI with password-protected settings and diagnostics panel
- 📦 Packaged as a standalone Windows `.exe` via PyInstaller

---

## Project Structure

```
├── pyqt5_app.py              # Main GUI application (entry point)
├── generate_report.py        # Builds PDF reports from inference_report.csv
├── intensity.py               # Display intensity analysis
├── checkdevice.py             # Device/COM port diagnostics
├── delete.py                  # Cleanup utility
│
├── general/                   # Core pilot & model-loading logic
│   ├── pilot_lcd.py            # LCD detection/testing loop
│   ├── pilot_led.py            # LED detection/testing loop
│   ├── loadmodel_lcd_flask.py  # LCD model loader
│   ├── loadmodel_led_flask.py  # LED model loader
│   └── EventStopTrigger.py     # Thread-safe stop-event flag
│
├── config_files/
│   ├── config.py               # Runtime config load/save
│   └── config_data.json        # Camera, Modbus, ROI & detection thresholds
│
├── models/                    # Trained YOLOv5 weights (.pt)
├── yolov5/                    # Bundled YOLOv5 (Ultralytics, AGPL-3.0)
├── template/                  # Reference ROI/crop templates
├── resources/                 # Icons, splash screen assets
│
├── CapturedImages/             # Runtime capture output
├── Captured_Img_LCD/           # Runtime capture output (LCD)
├── Captured_Img_LED/           # Runtime capture output (LED)
├── Captured_Img_LED_white/     # Runtime capture output (white-background LED)
├── Failed_images/failed_led/   # Failed-detection captures
│
├── DisplayUtilityV2.00.spec   # PyInstaller build spec
├── DisplayUtilityV2.01.spec   # PyInstaller build spec
├── build_exe.bat               # One-click Windows build script
└── requirements.txt            # Python dependencies
```

> Build output folders (`build/`, `dist/`, `output/`) are excluded from version control — see [Building the Executable](#building-the-executable).

---

## Prerequisites

- **Windows** (uses `pywin32`/COM-port-specific tooling and PyInstaller `.spec` files)
- **Python 3.9+**
- A connected **USB webcam**
- A device reachable over **Serial/Modbus RTU** (COM port), if testing live hardware
- ~2 GB free disk space (YOLOv5 + PyTorch dependencies)

---

## Installation

Clone the repository — YOLOv5 and model weights are included, so no separate downloads are needed:

```bash
git clone https://github.com/KunalKanojiya03/DisplayTesting.git
cd DisplayTesting
```

Create a virtual environment (recommended):

```bash
python -m venv venv
venv\Scripts\activate        # Windows
```

Install dependencies:

```bash
pip install -r requirements.txt
```

> If `requirements.txt` doesn't cover everything (PyQt5, pyserial, pandas, opencv-python are used by the app itself, separate from YOLOv5's own requirements), install any missing packages as prompted at runtime.

---

## Configuration

All runtime settings live in `config_files/config_data.json`, grouped by category:

| Section | Controls |
|---|---|
| `CAMERA` | Camera index, frame size, brightness/contrast/saturation/hue |
| `MODBUS` | Slave ID and register addresses for result reporting |
| `ROI` | Crop rotation angle, template match threshold |
| `STANDARD_PROFILE` | Resize dimensions, thresholding parameters (Alpha/Beta/Otsu block size) |
| `OUTLIER` | IQR-based outlier detection thresholds for reading validation |
| `LED_CONF` / `LCD_CONF` / `*_IOU` | YOLOv5 confidence & IoU thresholds per display type |

These can be edited directly in the JSON file, or via the in-app **Settings** dialog (triple-click the hidden top strip of the main window to reveal the Settings menu — password protected).

Serial/Modbus connection parameters (COM port, baud rate, parity, stop bits, timeout) are configured from the main window and persisted to `config_files/config.py` on **Start**.

---

## Usage

Run the application:

```bash
python pyqt5_app.py
```

**Basic workflow:**
1. Select display type — **LCD** or **LED**
2. Configure COM port, baud rate, and serial settings
3. (First-time setup) Use **Crop** to define the ROI and calibrate camera rotation against a live feed
4. Click **Start** to begin detection — the app loads the appropriate YOLOv5 model and starts the test loop in a background thread
5. Monitor live logs in the console panel
6. Click **Stop** to end the session
7. Use **Generate Report** to compile a PDF summary from logged inference results (password protected)

Additional tools are available under the **Tools** menu (e.g. Webcam Viewer for live feed diagnostics, password protected).

---

## Building the Executable

The app is packaged for distribution using PyInstaller:

```bash
build_exe.bat
```

This uses the `.spec` file matching the current version (`DisplayUtilityV2.01.spec`, etc.) and outputs a self-contained `.exe` with bundled dependencies (PyTorch, OpenCV, YOLOv5, etc.) to a `dist/` folder.

> ⚠️ Build output (`build/`, `dist/`, `output/`) is large (includes PyTorch/CUDA binaries and can exceed several hundred MB) and is intentionally excluded via `.gitignore`. Rebuild locally rather than expecting these folders in the repo.

---

## YOLOv5 & Licensing

This project bundles [Ultralytics YOLOv5](https://github.com/ultralytics/yolov5) directly under `yolov5/` for detection. YOLOv5 is licensed under **AGPL-3.0** — review the license terms before distributing this project commercially.

---

## Notes

- Settings and diagnostic tools are password-gated to prevent accidental changes to detection thresholds during production use.
- Detection thresholds (confidence, IoU, outlier bounds) are tuned per display type and may need recalibration for different hardware/lighting setups.

---

## Author

**Kunal Kanojiya**