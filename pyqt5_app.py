"""
pyqt5_app.py

Author: Kunal Kanojiya
Date: 05/05/25
Date modified: 01/08/25

Description:
    This script provides a graphical user interface (GUI) for configuring
    settings for a system that utilizes YOLOv5 and serial communication.
    Users can select display types, configure serial parameters, and specify
    file paths for the YOLOv5 model and data.

Functionality:
    - Allows users to select between LCD and LED display types.
    - Configures serial communication settings (COM port, baud rate, etc.).
    - Saves configuration settings to a 'config.py' file.
    - Starts and stops the corresponding pilot processes based on user input.
"""

import sys
import os
import time
import json
import threading
import importlib.util
import importlib
import cv2
import serial.tools.list_ports
import pandas as pd
import subprocess
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QDialog,
    QLabel,
    QRadioButton,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLineEdit,
    QFileDialog,
    QMessageBox,
    QSpinBox,
    QSplashScreen,
    QTextEdit,
    QGroupBox,
    QFormLayout,
    QMenuBar,
    QAction,
    QInputDialog,
    QButtonGroup,
    QWidget,
    QFrame,
    QComboBox,
    QMenu,
    QScrollArea,
    QCheckBox,
    QDesktopWidget,
)
from PyQt5.QtGui import QPixmap, QFont, QCursor, QIcon, QTextCursor, QImage
from PyQt5.QtCore import QTimer, Qt, QPoint, QObject, pyqtSignal, QThread

# Add project root (parent of 'general') to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# -----------------------------------------------------------------------------
from config_files.config import config, save_config
from general.EventStopTrigger import StopEventFlag
import generate_report

# import data

import re
import warnings

warnings.filterwarnings("ignore", category=UserWarning)


class ReportWorker(QObject):
    """
    A worker object that runs a task in a separate thread.
    The date for the report is passed during initialization.
    """

    finished = pyqtSignal(bool, str)

    def __init__(self, report_date=None):
        super().__init__()
        self.report_date = report_date

    def run(self):
        """This is the function that will be executed in the new thread."""
        success, message = generate_report.create_report(
            report_date_str=self.report_date
        )
        self.finished.emit(success, message)


class RedirectText(QObject):
    text_written = pyqtSignal(str)

    def __init__(self, text_edit):
        super().__init__()
        self.output = text_edit
        self.text_written.connect(self._append_text)

    def write(self, text):
        self.text_written.emit(text)

    def flush(self):
        pass

    def _append_text(self, text):
        self.output.moveCursor(QTextCursor.End)
        self.output.insertPlainText(text)
        self.output.ensureCursorVisible()


def GetResourcePath(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)

    return os.path.join(os.path.dirname(__file__), relative_path)


def load_config_json() -> dict:
    config_path = GetResourcePath("config_files\\config_data.json")
    with open(config_path, "r") as f:
        return json.load(f)


data = load_config_json()


def show_splash():
    splash_path = GetResourcePath("resources\\splash_img.png")
    pixmap = QPixmap(splash_path)
    splash = QSplashScreen(pixmap)
    splash.setWindowFlags(Qt.SplashScreen | Qt.WindowStaysOnTopHint)
    splash.show()
    QApplication.processEvents()
    time.sleep(2)  # Delay
    splash.close()


def crop_frame(image, x1, y1, x2, y2):
    """
    Crops the frame based on provided coordinates.
    """
    return image[y1:y2, x1:x2]


def rotate_image(image, angle):
    """
    Rotates the image to the desired angle without black borders.
    """
    h, w = image.shape[:2]
    cX, cY = (w // 2, h // 2)

    # Get rotation matrix
    M = cv2.getRotationMatrix2D((cX, cY), angle, 1.0)

    # Compute new bounding dimensions
    abs_cos = abs(M[0, 0])
    abs_sin = abs(M[0, 1])
    new_w = int(h * abs_sin + w * abs_cos)
    new_h = int(h * abs_cos + w * abs_sin)

    # Adjust the rotation matrix to center the image
    M[0, 2] += (new_w / 2) - cX
    M[1, 2] += (new_h / 2) - cY

    # Perform rotation
    return cv2.warpAffine(image, M, (new_w, new_h))


def StartCrop():
    camera = data["CAMERA"]
    # Initialize webcam
    cap = cv2.VideoCapture(camera["CAMERA_INDEX"], cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, camera["FRAME_WIDTH"])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, camera["FRAME_HEIGHT"])
    cap.set(cv2.CAP_PROP_SATURATION, camera["SATURATION"])
    cap.set(cv2.CAP_PROP_BRIGHTNESS, camera["BRIGHTNESS"])
    cap.set(cv2.CAP_PROP_SHARPNESS, camera["SHARPNESS"])
    cap.set(cv2.CAP_PROP_CONTRAST, camera["CONTRAST"])
    cap.set(cv2.CAP_PROP_HUE, camera["HUE"])

    if cap is None or not cap.isOpened():
        print("Error: Webcam not accessible!")
        return

    # Variables for cropping and rotation
    indx = 0
    cropping = False
    x_start, y_start, x_end, y_end = -1, -1, -1, -1

    config_path = GetResourcePath("config_files\\config_data.json")
    with open(config_path, "r") as f:
        config_data = json.load(f)

    angle = config_data.get("ROI", {}).get("ROTATION_ANGLE", 0.0)

    def mouse_crop(event, x, y, flags, param):
        """
        Mouse callback function for cropping.
        """
        nonlocal x_start, y_start, x_end, y_end, cropping

        if event == cv2.EVENT_LBUTTONDOWN:
            x_start, y_start, x_end, y_end = x, y, x, y
            cropping = True

        elif event == cv2.EVENT_MOUSEMOVE:
            if cropping:
                x_end, y_end = x, y

        elif event == cv2.EVENT_LBUTTONUP:
            x_end, y_end = x, y
            cropping = False

            # Draw rectangle on the image
            cv2.rectangle(frame, (x_start, y_start), (x_end, y_end), (0, 255, 0), 2)

    # Set mouse callback
    cv2.namedWindow("Webcam Feed")
    cv2.setMouseCallback("Webcam Feed", mouse_crop)
    TEMPLATE_PATH = GetResourcePath("template")
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Unable to fetch frame!")
            break

        # Rotate the frame
        rotated_frame = rotate_image(frame, angle)

        # Show live feed
        clone = rotated_frame.copy()
        if cropping and x_start != -1 and y_start != -1:
            cv2.rectangle(clone, (x_start, y_start), (x_end, y_end), (0, 255, 0), 2)

        cv2.imshow("Webcam Feed", clone)

        # Show processed feed (rotated)
        # cv2.imshow("Processed Frame", rotated_frame)

        # Keyboard controls
        key = cv2.waitKey(1) & 0xFF

        # Skip key processing if window is closed (key == -1)
        if key == -1:
            continue

        try:
            if key in [ord("r"), ord("R")]:
                angle += 0.5  # Increase rotation angle
            elif key in [ord("l"), ord("L")]:
                angle -= 0.5  # Decrease rotation angle
            elif key in [ord("c"), ord("C")]:
                if x_start != -1 and y_start != -1 and x_end != -1 and y_end != -1:
                    cropped = crop_frame(rotated_frame, x_start, y_start, x_end, y_end)
                    cv2.imshow("Cropped Frame", cropped)
                    cv2.imwrite(f"{TEMPLATE_PATH}/cropped_image{indx + 1}.jpg", cropped)
                    print(f"Cropped image saved as 'cropped_image{indx + 1}.jpg'.")
                    print(f"Rotation angle: {angle} degrees")
                    config_data["ROI"]["ROTATION_ANGLE"] = angle
                    with open(config_path, "w") as f:
                        json.dump(config_data, f, indent=4)
            elif key in [ord("q"), ord("Q")]:
                break

        except Exception as e:
            print(f"Error processing frame: {e}")
            break

    # Cleanup
    cap.release()
    cv2.destroyAllWindows()


def load_model_async(display_type, callback=None):
    def safe_start(target_function):
        def wrapped():
            try:
                target_function()
            except Exception as e:

                def show_error():
                    QMessageBox.critical(
                        None,
                        "Thread Error",
                        f"Error inside {display_type} thread:\n\n{e}",
                    )

                QTimer.singleShot(0, show_error)

        return wrapped  # Return the wrapped function

    try:
        module_name = (
            "loadmodel_lcd_flask" if display_type == "LCD" else "loadmodel_led_flask"
        )
        model_loader = None

        try:
            model_loader = importlib.import_module(module_name)
        except ModuleNotFoundError:
            base_path = (
                sys._MEIPASS if hasattr(sys, "_MEIPASS") else os.path.dirname(__file__)
            )
            module_path = os.path.join(base_path, f"general\\{module_name}.py")
            if not os.path.exists(module_path):
                raise FileNotFoundError(f"{module_name}.py not found in {module_path}")
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            model_loader = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(model_loader)

        # Load the model and assign the thread
        if display_type == "LCD":
            model_loader.LoadLCDModel()
            from general.pilot_lcd import StartLcd

            thread = threading.Thread(target=safe_start(StartLcd), daemon=True)
        else:
            model_loader.LoadLEDModel()
            from general.pilot_led import StartLed

            thread = threading.Thread(target=safe_start(StartLed), daemon=True)

        thread.start()
        if callback:
            callback(thread)

    except Exception as e:

        def show_outer_error():
            QMessageBox.critical(
                None, "Startup Error", f"Failed to start process:\n{e}"
            )

        QTimer.singleShot(0, show_outer_error)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(600, 700)

        # Outer layout
        self.main_layout = QVBoxLayout(self)

        # Scroll Area
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)

        # Scrollable inner widget and layout
        self.scroll_widget = QWidget()
        self.form_layout = QFormLayout(self.scroll_widget)
        self.scroll_area.setWidget(self.scroll_widget)

        # Add scroll area to main layout
        self.main_layout.addWidget(self.scroll_area)

        # Store inputs
        self.entries = {}
        self.load_data()

        # Apply Button
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self.apply_settings)
        self.main_layout.addWidget(apply_btn)

        # Apply some spacing and style
        self.form_layout.setVerticalSpacing(10)
        self.form_layout.setHorizontalSpacing(20)
        self.setStyleSheet("""
            QLineEdit {
                padding: 5px;
                font-size: 10pt;
            }
            QLabel {
                font-size: 10pt;
            }
            QPushButton {
                font-size: 10pt;
                padding: 6px 12px;
            }
        """)

    def load_data(self):
        config_path = GetResourcePath("config_files\\config_data.json")
        with open(config_path, "r") as f:
            self.config_data = json.load(f)

        # Flatten relevant keys for display in the GUI
        self.data_vars = {
            "CAMERA_INDEX": self.config_data["CAMERA"]["CAMERA_INDEX"],
            "FRAME_WIDTH": self.config_data["CAMERA"]["FRAME_WIDTH"],
            "FRAME_HEIGHT": self.config_data["CAMERA"]["FRAME_HEIGHT"],
            "RESIZED_FRAME_WIDTH": self.config_data["STANDARD_PROFILE"][
                "RESIZED_FRAME_WIDTH"
            ],
            "RESIZED_FRAME_HEIGHT": self.config_data["STANDARD_PROFILE"][
                "RESIZED_FRAME_HEIGHT"
            ],
            "SATURATION": self.config_data["CAMERA"]["SATURATION"],
            "BRIGHTNESS": self.config_data["CAMERA"]["BRIGHTNESS"],
            "SHARPNESS": self.config_data["CAMERA"]["SHARPNESS"],
            "CONTRAST": self.config_data["CAMERA"]["CONTRAST"],
            "HUE": self.config_data["CAMERA"]["HUE"],
            "SLAVE_ID": self.config_data["MODBUS"]["SLAVE_ID"],
            "SLAVE_ADD_CLS_QUANT": self.config_data["MODBUS"]["SLAVE_ADD_CLS_QUANT"],
            "SLAVE_ADD_RESULT": self.config_data["MODBUS"]["SLAVE_ADD_RESULT"],
            "FRAME_SKIP_INTERVAL": self.config_data["FRAME_SKIP_INTERVAL"],
            "BATCH_SIZE": self.config_data["BATCH_SIZE"],
            "SIGNIFICANT_DEVIATION": self.config_data["SIGNIFICANT_DEVIATION"],
            "OUTLIER_MAXVALUE": self.config_data.get("OUTLIER_MAXVALUE", 250),
            "MIN_CONTOUR_AREA": self.config_data["MIN_CONTOUR_AREA"],
            "ALPHA": self.config_data["STANDARD_PROFILE"]["ALPHA"],
            "BETA": self.config_data["STANDARD_PROFILE"]["BETA"],
            "THRESH_BLOCKSIZE": self.config_data["STANDARD_PROFILE"][
                "THRESH_BLOCKSIZE"
            ],
            "THRESH_C": self.config_data["STANDARD_PROFILE"]["THRESH_C"],
            "Q1_PERCENTILE": self.config_data["OUTLIER"]["Q1_PERCENTILE"],
            "Q3_PERCENTILE": self.config_data["OUTLIER"]["Q3_PERCENTILE"],
            "IQR_LOW_THRESHOLD_1": self.config_data["OUTLIER"]["IQR_LOW_THRESHOLD_1"],
            "IQR_LOW_THRESHOLD_2": self.config_data["OUTLIER"]["IQR_LOW_THRESHOLD_2"],
            "IQR_LOW_MULTIPLIER_1": self.config_data["OUTLIER"]["IQR_LOW_MULTIPLIER_1"],
            "IQR_LOW_MULTIPLIER_2": self.config_data["OUTLIER"]["IQR_LOW_MULTIPLIER_2"],
            "IQR_LOW_MULTIPLIER_3": self.config_data["OUTLIER"]["IQR_LOW_MULTIPLIER_3"],
            "MATCH_THRESHOLD": self.config_data["ROI"]["MATCH_THRESHOLD"],
            "i": self.config_data["LOCAL_VARS"]["i"],
            "flag1": self.config_data["LOCAL_VARS"]["flag1"],
            "counter": self.config_data["LOCAL_VARS"]["counter"],
            "LED_CONF": self.config_data["LED_CONF"],
            "LED_IOU": self.config_data["LED_IOU"],
            "LCD_CONF": self.config_data["LCD_CONF"],
            "LCD_IOU": self.config_data["LCD_IOU"],
            "LED_ACCURACY": self.config_data["LED_ACCURACY"],
            "LED_ALL_ON_COUNT": self.config_data["LED_ALL_ON_COUNT"],
        }

        for key, val in self.data_vars.items():
            entry = QLineEdit(str(val))
            self.entries[key] = entry
            self.form_layout.addRow(QLabel(key), entry)

    def apply_settings(self):
        try:
            config_path = GetResourcePath("config_files\\config_data.json")
            new_values = {k: v.text() for k, v in self.entries.items()}

            # Update the correct nested sections
            for key, val in new_values.items():
                val_cast = type(self.data_vars[key])(val)

                if key in [
                    "CAMERA_INDEX",
                    "FRAME_WIDTH",
                    "FRAME_HEIGHT",
                    "SATURATION",
                    "BRIGHTNESS",
                    "SHARPNESS",
                    "CONTRAST",
                    "HUE",
                ]:
                    self.config_data["CAMERA"][key] = val_cast
                elif key in ["SLAVE_ID", "SLAVE_ADD_CLS_QUANT", "SLAVE_ADD_RESULT"]:
                    self.config_data["MODBUS"][key] = val_cast
                elif key in [
                    "Q1_PERCENTILE",
                    "Q3_PERCENTILE",
                    "IQR_LOW_THRESHOLD_1",
                    "IQR_LOW_THRESHOLD_2",
                    "IQR_LOW_MULTIPLIER_1",
                    "IQR_LOW_MULTIPLIER_2",
                    "IQR_LOW_MULTIPLIER_3",
                ]:
                    self.config_data["OUTLIER"][key] = val_cast
                elif key in ["MATCH_THRESHOLD", "ROTATION_ANGLE"]:
                    self.config_data["ROI"][key] = val_cast
                elif key in ["i", "flag1", "counter"]:
                    self.config_data["LOCAL_VARS"][key] = val_cast
                elif key in [
                    "ALPHA",
                    "BETA",
                    "THRESH_BLOCKSIZE",
                    "THRESH_C",
                    "RESIZED_FRAME_WIDTH",
                    "RESIZED_FRAME_HEIGHT",
                ]:
                    self.config_data["STANDARD_PROFILE"][key] = val_cast
                else:
                    # Top-level keys
                    self.config_data[key] = val_cast

            # Save updated JSON
            with open(config_path, "w") as f:
                json.dump(self.config_data, f, indent=2)

            QMessageBox.information(self, "Success", "Settings saved successfully.")
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Display Utility V3.0")
        self.setFixedSize(700, 650)
        self.setWindowIcon(QIcon(GetResourcePath("resources\\splash_img.ico")))
        self.report_thread = None

        self.process = None
        self.click_count = 0

        self.central = QWidget()
        self.setCentralWidget(self.central)
        self.layout = QVBoxLayout(self.central)

        self.init_ui()
        self.redirect_logs()
        self.init_com_port_timer()

    def init_ui(self):
        # --- Hidden Click Area ---
        self.top_click_frame = QFrame()
        self.top_click_frame.setFixedHeight(10)
        self.top_click_frame.setStyleSheet("background-color: transparent;")
        self.top_click_frame.mousePressEvent = self.detect_clicks
        self.layout.addWidget(self.top_click_frame)

        # --- Display Selection ---
        display_group = QGroupBox("Select Display Type")
        radio_layout = QHBoxLayout()
        self.display_type = QButtonGroup(self)
        self.lcd_radio = QRadioButton("LCD Display")
        self.led_radio = QRadioButton("LED Display")
        self.display_type.addButton(self.lcd_radio)
        self.display_type.addButton(self.led_radio)
        radio_layout.addWidget(self.lcd_radio)
        radio_layout.addWidget(self.led_radio)
        display_group.setLayout(radio_layout)
        self.layout.addWidget(display_group)

        self.white_display_chk = QCheckBox("White Display")
        self.white_display_chk.setToolTip(
            "Check this if the display background is white and text is black."
        )
        self.layout.addWidget(self.white_display_chk)

        self.white_display_chk.setChecked(config.get("WHITE_DISPLAY", False))
        self.lcd_radio.toggled.connect(self.update_field_states)
        self.led_radio.toggled.connect(self.update_field_states)

        # --- Settings Area ---
        config_group = QGroupBox("Serial & File Configuration")
        grid = QGridLayout()

        self.com_port = QComboBox()
        self.baud_rate = QComboBox()
        self.baud_rate.addItems(["9600", "14400", "19200", "38400", "57600", "115200"])
        self.data_bits = QComboBox()
        self.data_bits.addItems(["7", "8"])
        self.parity = QComboBox()
        self.parity.addItems(["N", "E", "O"])
        self.stop_bits = QComboBox()
        self.stop_bits.addItems(["1", "2"])
        self.timeout = QLineEdit("0.02")
        # self.file_path = QLineEdit()
        self.page_count = QSpinBox()
        self.page_count.setRange(1, 20)
        # browse_btn = QPushButton("Browse"); browse_btn.clicked.connect(self.browse_path)

        items = [
            ("COM Port:", self.com_port),
            ("Baud Rate:", self.baud_rate),
            ("Data Bits:", self.data_bits),
            ("Parity:", self.parity),
            ("Stop Bits:", self.stop_bits),
            ("Timeout:", self.timeout),
            # ("File Path:", self.file_path), ("", browse_btn),
            ("Page Count:", self.page_count),
        ]
        for i, (label, widget) in enumerate(items):
            grid.addWidget(QLabel(label), i, 0)
            grid.addWidget(widget, i, 1)

        config_group.setLayout(grid)
        self.layout.addWidget(config_group)

        # --- Action Buttons ---
        button_layout = QHBoxLayout()
        start_btn = QPushButton("Start")
        start_btn.clicked.connect(self.start_process)
        stop_btn = QPushButton("Stop")
        stop_btn.clicked.connect(self.stop_process)
        crop_btn = QPushButton("Crop")
        crop_btn.clicked.connect(self.start_crop_in_thread)
        report_btn = QPushButton("Generate Report")
        report_btn.setObjectName("reportButton")
        report_btn.clicked.connect(self.generate_visual_report)

        for btn in [start_btn, stop_btn, crop_btn, report_btn]:
            button_layout.addWidget(btn)
        self.layout.addLayout(button_layout)

        # --- Log Area ---
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.layout.addWidget(self.log_output)

        # --- Menu ---
        self.menu_bar = self.menuBar()
        self.settings_menu = QMenu("Settings", self)
        self.settings_action = QAction("Open Settings", self)
        self.settings_action.triggered.connect(self.open_settings)
        self.settings_menu.addAction(self.settings_action)

        # Tools menu
        tools_menu = self.menu_bar.addMenu("Tools")
        webcam_action = QAction("Webcam Viewer", self)
        webcam_action.triggered.connect(self.open_webcam_viewer)
        tools_menu.addAction(webcam_action)

        # Ensure menu is hidden on launch
        if self.settings_menu in self.menu_bar.children():
            self.menu_bar.removeAction(self.settings_menu.menuAction())
        self.settings_menu_added = False
        self.click_count = 0

        self.com_port.setCurrentText(config.get("COM_PORT", "COM3"))
        self.baud_rate.setCurrentText(config.get("BAUD_RATE", "115200"))
        self.data_bits.setCurrentText(config.get("DATA_BITS", "8"))
        self.parity.setCurrentText(config.get("PARITY", "N"))
        self.stop_bits.setCurrentText(config.get("STOP_BITS", "2"))
        self.timeout.setText(config.get("TIMEOUT", "0.02"))
        # self.file_path.setText(config.get("FILE_NAME", ""))
        # display_type = config.get("DISPLAY_TYPE", "LCD")
        # if display_type == "LCD":
        #     self.lcd_radio.setChecked(True)
        # elif display_type == "LED":
        #     self.led_radio.setChecked(True)
        self.page_count.setValue(config.get("PAGE_COUNT", 7))

        self.apply_style()
        self.update_field_states()
        self.center_window()

    def detect_clicks(self, event):
        self.click_count += 1
        if self.click_count == 3 and not self.settings_menu_added:
            self.menu_bar.addMenu(self.settings_menu)
            self.settings_menu_added = True
            self.click_count = 0

    def open_settings(self):
        password, ok = QInputDialog.getText(
            self, "Enter Password", "Password:", echo=QLineEdit.Password
        )
        if ok and password == "5555":
            dialog = SettingsDialog(self)
            result = dialog.exec_()
            if result == QDialog.Accepted or result == QDialog.Rejected:
                # After settings dialog is closed, hide the menu again
                self.menu_bar.removeAction(self.settings_menu.menuAction())
                self.settings_menu_added = False
                self.click_count = 0
        else:
            QMessageBox.warning(self, "Access Denied", "Incorrect Password!")

    def update_field_states(self):
        is_enabled = self.lcd_radio.isChecked() or self.led_radio.isChecked()

        for widget in [
            self.com_port,
            self.baud_rate,
            self.data_bits,
            self.parity,
            self.stop_bits,
            self.timeout,
            self.page_count,
        ]:
            widget.setEnabled(is_enabled)

        for btn in self.findChildren(QPushButton):
            if btn.text() in ["Start", "Stop", "Crop"]:
                btn.setEnabled(is_enabled)

    def set_ui_enabled(self, enabled: bool):
        # Toggle all form fields
        for widget in [
            self.com_port,
            self.baud_rate,
            self.data_bits,
            self.parity,
            self.stop_bits,
            self.timeout,
            self.page_count,
        ]:
            widget.setEnabled(enabled)

        # Toggle Browse and Crop buttons
        for btn in self.findChildren(QPushButton):
            if btn.text() in ["Crop"]:
                btn.setEnabled(enabled)
            elif btn.text() == "Start":
                btn.setEnabled(enabled)
            elif btn.text() == "Stop":
                btn.setEnabled(not enabled)

    # def browse_path(self):
    #     folder = QFileDialog.getExistingDirectory(self, "Select Folder")
    #     if folder:
    #         self.file_path.setText(folder)

    def redirect_logs(self):
        self.redirector = RedirectText(self.log_output)
        sys.stdout = self.redirector
        sys.stderr = self.redirector

    def init_com_port_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_com_ports)
        self.timer.start(1000)

    def update_com_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        current = self.com_port.currentText()
        self.com_port.clear()
        self.com_port.addItems(ports)
        if current in ports:
            self.com_port.setCurrentText(current)

    def save_config_gui(self):
        new_conf = {
            "COM_PORT": self.com_port.currentText(),
            "BAUD_RATE": self.baud_rate.currentText(),
            "DATA_BITS": self.data_bits.currentText(),
            "PARITY": self.parity.currentText(),
            "STOP_BITS": self.stop_bits.currentText(),
            "TIMEOUT": self.timeout.text(),
            # "FILE_NAME": self.file_path.text(),
            "DISPLAY_TYPE": "LCD" if self.lcd_radio.isChecked() else "LED",
            "PAGE_COUNT": self.page_count.value(),
            "WHITE_DISPLAY": self.white_display_chk.isChecked(),
        }
        save_config(new_conf)
        config.update(new_conf)  # update global dict

    def start_process(self):
        if not self.lcd_radio.isChecked() and not self.led_radio.isChecked():
            QMessageBox.warning(
                self, "Input Error", "Please select LCD or LED display type."
            )
            return

        if self.process and self.process.is_alive():
            QMessageBox.information(self, "Running", "Process already running.")
            return

        self.save_config_gui()
        display_type = "LCD" if self.lcd_radio.isChecked() else "LED"

        def on_process_started(thread):
            self.process = thread
            print(f"{display_type} process started.")

        threading.Thread(
            target=load_model_async,
            args=(display_type, on_process_started),
            daemon=True,
        ).start()
        print("Loading model...")
        self.set_ui_enabled(False)

    def stop_process(self):
        if self.process and self.process.is_alive():
            StopEventFlag.set()
            self.process.join(timeout=8)
            if self.process.is_alive():
                # A hung camera/serial read (e.g. cap.read() has no timeout of
                # its own) can keep the worker thread alive past StopEventFlag.
                # Don't block the GUI forever waiting for it: leave the process
                # tracked and StopEventFlag set so it can still exit once
                # unblocked, and let the user retry Stop instead of freezing.
                QMessageBox.warning(
                    self,
                    "Still Stopping",
                    "The process is taking longer than expected to stop "
                    "(possibly a stuck camera or serial read). It will keep "
                    "trying to stop in the background. Avoid starting a new "
                    "process until it finishes — click Stop again to retry.",
                )
                return
            self.process = None
            QMessageBox.information(self, "Stopped", "Process stopped.")
        else:
            QMessageBox.information(
                self, "Not Running", "No process is currently running."
            )
        self.set_ui_enabled(True)
        time.sleep(1)
        StopEventFlag.clear()

    def apply_style(self):
        self.setStyleSheet("""
            QWidget {
                font-family: Segoe UI;
                font-size: 10pt;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #999;
                border-radius: 6px;
                margin-top: 10px;
                padding: 5px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 3px;
                background-color: #fab961;
            }
            QPushButton {
                background-color: #FF9E1B;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #f58e07;
            }
            QLineEdit, QComboBox, QSpinBox, QTextEdit {
                padding: 4px;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
        """)

    # Make the App center of the monitor screen
    def center_window(self):
        frame = self.frameGeometry()
        center_point = QDesktopWidget().availableGeometry().center()
        frame.moveCenter(center_point)
        self.move(frame.topLeft())

    def open_webcam_viewer(self):
        dlg = WebcamDialog(self)
        dlg.exec_()

    def start_crop_in_thread(self):
        """Launches the StartCrop function in a separate, non-blocking thread."""
        # print("Starting crop function in a separate thread...")
        crop_thread = threading.Thread(target=StartCrop, daemon=True)
        crop_thread.start()

    def generate_visual_report(self):
        """
        Prompts the user to select a date, then runs report generation
        in a background thread using the QThread/worker pattern.
        """
        # 1. Password Check
        password, ok = QInputDialog.getText(
            self, "Password Required", "Enter password:", QLineEdit.Password
        )
        if not ok or password != "786521":
            if ok:
                QMessageBox.warning(self, "Access Denied", "Incorrect password!")
            return

        # 2. Read CSV and Get Unique Dates for the Dialog
        try:
            csv_path = GetResourcePath("inference_report.csv")
            if not os.path.exists(csv_path):
                QMessageBox.warning(
                    self,
                    "No Data",
                    "The report file (inference_report.csv) does not exist.",
                )
                return

            df = pd.read_csv(csv_path)
            if df.empty:
                QMessageBox.warning(self, "No Data", "The report file is empty.")
                return

            df["timestamp"] = pd.to_datetime(df["timestamp"])
            unique_dates = sorted(
                [d.strftime("%Y-%m-%d") for d in df["timestamp"].dt.date.unique()],
                reverse=True,
            )

            if not unique_dates:
                QMessageBox.warning(
                    self,
                    "No Data",
                    "Could not find any valid dates in the report file.",
                )
                return

            choices = ["All Time"] + unique_dates
            selected_item, ok = QInputDialog.getItem(
                self,
                "Select Report Date",
                "Choose the date for the report:",
                choices,
                0,
                False,
            )

            if not ok:
                return  # User clicked cancel

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Reading Report",
                f"Could not read or parse the report file:\n{e}",
            )
            return

        # 3. Setup and Run the Worker Thread
        report_btn = self.findChild(QPushButton, "reportButton")
        if report_btn:
            report_btn.setEnabled(False)

        print(f"Generating report for: {selected_item}...")

        # --- CORRECTED PART ---
        date_to_pass = selected_item if selected_item != "All Time" else None

        self.thread = QThread()
        # Pass the date directly to the worker's constructor
        self.worker = ReportWorker(report_date=date_to_pass)
        # --- END OF CORRECTION ---

        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_report_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()

    def on_report_finished(self, success, message):
        """
        This slot receives the signal from the worker and updates the GUI.
        It runs safely in the main GUI thread.
        """
        # Find the button by its object name to re-enable it
        report_btn = self.findChild(QPushButton, "reportButton")
        if report_btn:
            report_btn.setEnabled(True)

        if success:
            QMessageBox.information(self, "Report Generated", message)
        else:
            QMessageBox.critical(
                self, "Report Failed", f"Could not generate report:\n\n{message}"
            )

        print(message)


class WebcamDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Webcam Viewer")
        self.setMinimumSize(640, 600)
        self.cap = None

        # UI components
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # Password Area
        self.pwd_label = QLabel("Enter Password:")
        self.pwd_input = QLineEdit()
        self.pwd_input.setEchoMode(QLineEdit.Password)
        self.show_pwd_chk = QCheckBox("Show Password")
        self.show_pwd_chk.stateChanged.connect(self.toggle_password_visibility)
        self.login_btn = QPushButton("Login")
        self.login_btn.clicked.connect(self.verify_password)

        self.layout.addWidget(self.pwd_label)
        self.layout.addWidget(self.pwd_input)
        self.layout.addWidget(self.show_pwd_chk)
        self.layout.addWidget(self.login_btn)

        # Video & Console (Hidden initially)
        self.video_label = QLabel()
        self.video_label.setFixedSize(480, 360)
        self.video_label.setStyleSheet(
            "background-color: black; border: 1px solid gray;"
        )
        self.video_label.setVisible(False)

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setVisible(False)

        # Control Buttons
        self.button_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Webcam")
        self.stop_btn = QPushButton("Stop Webcam")
        self.start_btn.clicked.connect(self.start_webcam)
        self.stop_btn.clicked.connect(self.stop_webcam)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)

        self.button_layout.addWidget(self.start_btn)
        self.button_layout.addWidget(self.stop_btn)

        self.layout.addWidget(self.video_label)
        self.layout.addWidget(self.console)
        self.layout.addLayout(self.button_layout)

        # Webcam Timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)

    def toggle_password_visibility(self):
        if self.show_pwd_chk.isChecked():
            self.pwd_input.setEchoMode(QLineEdit.Normal)
        else:
            self.pwd_input.setEchoMode(QLineEdit.Password)

    def verify_password(self):
        if self.pwd_input.text() == "5555":
            self.pwd_label.hide()
            self.pwd_input.hide()
            self.show_pwd_chk.hide()
            self.login_btn.hide()
            self.video_label.show()
            self.console.show()
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(True)
        else:
            QMessageBox.warning(self, "Error", "Incorrect password")

    def start_webcam(self):
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            QMessageBox.critical(self, "Webcam Error", "Could not open webcam.")
            return
        self.console.append("Webcam started")
        self.timer.start(30)

    def update_frame(self):
        if self.cap is None:
            return
        ret, frame = self.cap.read()
        if not ret:
            return
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = QImage(frame.data, frame.shape[1], frame.shape[0], QImage.Format_RGB888)
        self.video_label.setPixmap(QPixmap.fromImage(img))

    def stop_webcam(self):
        self.console.append("Webcam stopped")
        self.timer.stop()
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.video_label.clear()

    def closeEvent(self, event):
        self.stop_webcam()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    show_splash()
    window = MainApp()
    window.show()
    sys.exit(app.exec_())
