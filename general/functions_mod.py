"""
functions.py

Author: Kunal Kanojiya
Date: 07/25/2025
Date modified: 13/05/25 (Original)
               23/05/25 (Improved)

Description:
    This module contains functions for image processing, template matching,
    outlier detection, and batch inference related to LCD and LED image analysis.
    It utilizes OpenCV for image manipulation and communicates with hardware components
    via a specific protocol.

Dependencies:
    - OpenCV (cv2)
    - NumPy (numpy)
    - crcmod
    - serial
    - threading
    - time
    - sys
    - os
    - importlib
    - loadmodel_led_flask
    - loadmodel_lcd_flask
"""

# Standard library imports
import os
import sys
import time
import json
import threading
import pythoncom  # Required to initialize COM in threads
import win32com.client

import logging
from datetime import datetime
from typing import Tuple, List, Optional, Union, Dict, Any
from dataclasses import dataclass
from collections import deque

# Third-party imports
import cv2
import numpy as np
import crcmod
import serial

# Add project root (parent of 'general') to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# -----------------------------------------------------------------------------

# Local imports
from config_files.config import config
from general.EventStopTrigger import StopEventFlag

# These will be imported dynamically
# import loadmodel_led_flask
# import loadmodel_lcd_flask

# -----------------------------------------------------------------------------
# Utility Functions
# -----------------------------------------------------------------------------


def GetResourcePath(relative_path: str) -> str:
    """
    Get the absolute path to the resource, works for both bundled and unbundled applications.

    Args:
        relative_path (str): Path to the resource relative to the base directory.

    Returns:
        str: Absolute path to the resource.
    """
    if hasattr(sys, "_MEIPASS"):
        # When running from a bundled executable
        return os.path.join(sys._MEIPASS, relative_path)
    else:
        # When running in the normal environment
        first_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        return os.path.join(first_path, relative_path)


# Dynamically import data.py
# dataPath = GetResourcePath('data.py')
# spec = importlib.util.spec_from_file_location("data", dataPath)
# data = importlib.util.module_from_spec(spec)
# spec.loader.exec_module(data)


def load_config_json() -> dict:
    config_path = GetResourcePath("config_files\\config_data.json")
    with open(config_path, "r") as f:
        return json.load(f)


data = load_config_json()

# Import the model modules
try:
    import general.loadmodel_led_flask
    import general.loadmodel_lcd_flask
except ImportError as e:
    print(f"Warning: Could not import model modules: {e}")

# -----------------------------------------------------------------------------
# Global Variables
# -----------------------------------------------------------------------------
modbus = data["MODBUS"]
camera = data["CAMERA"]
outlier = data["OUTLIER"]
roi = data["ROI"]
# # Camera initialization
# try:
#     cap = safe_open_camera(0)
#     if cap is None:
#         print("Could not open webcam. Aborting.")

#     # Set camera properties based on the configuration
#     cap.set(cv2.CAP_PROP_FRAME_WIDTH, data.FRAME_WIDTH)
#     cap.set(cv2.CAP_PROP_FRAME_HEIGHT, data.FRAME_HEIGHT)
#     cap.set(cv2.CAP_PROP_SATURATION, data.SATURATION)
#     cap.set(cv2.CAP_PROP_BRIGHTNESS, data.BRIGHTNESS)
#     cap.set(cv2.CAP_PROP_SHARPNESS, data.SHARPNESS)
#     cap.set(cv2.CAP_PROP_CONTRAST, data.CONTRAST)
# except Exception as e:
#     print(f"Error initializing camera: {e}")
#     cap = None

cap = None
ser = None
F9flag = None


def safe_open_camera(index=0, retries=3, delay=0.5):
    global cap
    for i in range(retries):
        with cap_lock:
            cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            opened = cap is not None and cap.isOpened()
            if opened:
                print(f"✅ Webcam opened on attempt {i+1}")

                # Set camera properties
                try:
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, camera["FRAME_WIDTH"])
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, camera["FRAME_HEIGHT"])
                    cap.set(cv2.CAP_PROP_SATURATION, camera["SATURATION"])
                    cap.set(cv2.CAP_PROP_BRIGHTNESS, camera["BRIGHTNESS"])
                    cap.set(cv2.CAP_PROP_CONTRAST, camera["CONTRAST"])
                    cap.set(cv2.CAP_PROP_SHARPNESS, camera["SHARPNESS"])
                    cap.set(cv2.CAP_PROP_BACKLIGHT, 1)
                    cap.set(cv2.CAP_PROP_HUE, camera["HUE"])
                except Exception as e:
                    print(f"⚠️ Warning setting camera properties: {e}")

                # --- ADD THIS ---
                # Read a few throw-away frames to let Auto-Exposure settle
                for _ in range(5):
                    cap.read()

                camera_update_enabled.set()  # Enable camera updates   171125 modified
                return cap

            if cap:
                cap.release()

        print(f"[Retry {i+1}] Failed to open webcam. Retrying in {delay}s...")
        time.sleep(delay)

    print("❌ Failed to open webcam after all retries.")
    return None


# Serial port initialization
def safe_open_serial(config, retries=3, delay=0.5) -> Optional[serial.Serial]:
    """
    Safely initializes and opens the serial port with retry logic.

    Args:
        config (dict): Serial port configuration parameters.
        retries (int): Number of retry attempts on failure.
        delay (float): Delay between retries in seconds.

    Returns:
        serial.Serial or None: The opened serial port object or None on failure.
    """
    global ser
    for i in range(retries):
        with ser_lock:
            try:
                ser = serial.Serial(
                    port=config["COM_PORT"],
                    baudrate=int(config["BAUD_RATE"]),
                    bytesize=int(config["DATA_BITS"]),
                    parity=config["PARITY"],
                    stopbits=int(config["STOP_BITS"]),
                    timeout=float(config["TIMEOUT"]),
                )
                if ser.is_open:
                    print(f"✅ Serial port opened on attempt {i+1} ({config['COM_PORT']})")
                    return ser
            except Exception as e:
                print(f"[Retry {i+1}] ⚠️ Error opening serial port: {e}")

            if ser and ser.is_open:
                ser.close()

        time.sleep(delay)

    print("❌ Failed to open serial port after all retries.")
    return None


# Thread safety for serial operations
ser_lock = threading.Lock()
# Thread safety for camera operations (cap is touched by UpdateFrame's thread,
# get_valid_frame/CaptureImage* on the pilot thread, and safe_open_camera itself,
# so it needs the same protection ser already had via ser_lock). RLock because
# get_valid_frame() calls safe_open_camera() which also acquires this lock.
cap_lock = threading.RLock()
camera_update_enabled = threading.Event()  # 171125 modified
camera_update_enabled.set()  # Initially enabled

# Global variables for image processing
latestFrame = None
frameLock = threading.Lock()
running = True
topLeft = None
bottomRight = None
is_testing_active = False

# Global variables for result handling
batchImages = []
batchAlpha = []
resutlsTh = []
imagesResults = []

# File paths
TEMPLATE_FOLDER_PATH = GetResourcePath("template")
ALPHA_IMAGE_FOLDER = GetResourcePath("Alpha_Image")
BATCH_FOLDER = GetResourcePath("Batch")
CAPTURED_IMG_LED = GetResourcePath("Captured_Img_LED")
CAPTURED_IMG_LCD = GetResourcePath("Captured_Img_LCD")
# -----------------------------------------------------------------------------
# Serial Communication Functions
# -----------------------------------------------------------------------------


def ResetSerial():
    """
    Reset and reopen the serial connection with the configured parameters.
    Thread-safe implementation.
    """
    global ser
    with ser_lock:
        try:
            if ser and ser.is_open:
                ser.close()
            ser = serial.Serial(
                port=config["COM_PORT"],
                baudrate=int(config["BAUD_RATE"]),
                bytesize=int(config["DATA_BITS"]),
                parity=config["PARITY"],
                stopbits=int(config["STOP_BITS"]),
                timeout=float(config["TIMEOUT"]),
            )
            return True
        except Exception as e:
            print(f"Error resetting serial connection: {e}")
            return False


def SafeSerialWrite(data: bytes) -> bool:
    """
    Thread-safe writing to the serial port.

    Args:
        data (bytes): Data to write to the serial port.

    Returns:
        bool: True if write was successful, False otherwise.
    """
    with ser_lock:
        try:
            if ser and ser.is_open:
                ser.write(data)
                return True
            return False
        except Exception as e:
            print(f"Error writing to serial port: {e}")
            return False


def SafeSerialRead() -> bytes:
    """
    Thread-safe reading from the serial port.

    Returns:
        bytes: Data read from the serial port.
    """
    with ser_lock:
        try:
            if ser and ser.is_open:
                return ser.readall()
            return b""
        except Exception as e:
            print(f"Error reading from serial port: {e}")
            return b""


def ComputeCrc(data: bytes) -> int:
    """
    Computes the CRC-16 checksum for the given data using a specified polynomial.

    Args:
        data (bytes): The input data for which the CRC-16 checksum needs to be calculated.

    Returns:
        int: The computed CRC-16 checksum as an integer.
    """
    crc16 = crcmod.mkCrcFun(0x18005, rev=True, initCrc=0xFFFF, xorOut=0x0000)
    return crc16(data)


def Modbus(status: Optional[int] = None) -> Optional[dict]:
    """
    Unified Modbus function that returns:
    - {'type': 'F9', 'flag': int, 'slave_id': int, 'address': int}
    - {'type': 'DATA', 'label': int, 'count': int, 'slave_id': int, 'address': int}
    - {'type': 'RESULT_READ', 'slave_id': int, 'address': int}
    Or None if invalid/incomplete message is received.
    """
    response_data = b""

    while not StopEventFlag.is_set():
        if ser and ser.is_open:
            try:
                response_data = SafeSerialRead()

                # <--- FIX: Add a minimum length check for any Modbus RTU frame.
                # A minimal valid frame (e.g., exception response) is 5 bytes.
                if len(response_data) < 5:
                    continue

                # Basic parsing
                receivedSlaveId = response_data[0]
                function_code = response_data[1]
                receivedSlaveAddress = int.from_bytes(response_data[2:4], "big")
                receivedCrc = response_data[-2:]
                calculatedCrc = ComputeCrc(response_data[:-2])
                calculatedCrcBytes = calculatedCrc.to_bytes(2, byteorder="little")

                if receivedCrc != calculatedCrcBytes:
                    continue  # Skip invalid CRC

                if status is None:
                    # Only process messages for our slave ID
                    if receivedSlaveId != modbus["SLAVE_ID"]:
                        continue

                    # Handle label/count message (Preset Multiple Registers, 0x10)
                    if function_code == modbus["PRESET_MULTIPLE_REGISTER"]:
                        # <--- FIX: Check for the expected length of this specific frame.
                        # SlaveID(1) + FC(1) + Addr(2) + NumRegs(2) + ByteCount(1) + Data(4) + CRC(2) = 13 bytes
                        if len(response_data) < 13:
                            continue

                        label = int.from_bytes(response_data[7:9], "big")
                        count = int.from_bytes(response_data[9:11], "big")

                        # Acknowledge
                        firstSixBytes = response_data[:6]
                        crcBytes = ComputeCrc(firstSixBytes).to_bytes(2, "little")
                        SafeSerialWrite(firstSixBytes + crcBytes)

                        return {
                            "type": "DATA",
                            "label": label,
                            "count": count,
                            "slave_id": receivedSlaveId,
                            "address": receivedSlaveAddress,
                        }

                    # Handle F9 flag message (Preset Single Register, 0x06)
                    elif function_code == modbus["PRESET_SINGLE_REGISTER"]:
                        # <--- FIX: Check for the expected length of this specific frame.
                        # SlaveID(1) + FC(1) + RegAddr(2) + Value(2) + CRC(2) = 8 bytes
                        if len(response_data) < 8:
                            continue

                        flag = int.from_bytes(response_data[4:6], "big")

                        firstSixBytes = response_data[:6]
                        crcBytes = ComputeCrc(firstSixBytes).to_bytes(2, "little")
                        SafeSerialWrite(firstSixBytes + crcBytes)

                        return {
                            "type": "F9",
                            "flag": flag,
                            "slave_id": receivedSlaveId,
                            "address": receivedSlaveAddress,
                        }

                    # Handle PLC read request for result (Read Holding Registers, 0x03)
                    elif function_code == 0x03:
                        # <--- FIX: Check for the expected length of this specific frame.
                        # SlaveID(1) + FC(1) + StartAddr(2) + NumRegs(2) + CRC(2) = 8 bytes
                        if len(response_data) < 8:
                            continue

                        return {
                            "type": "RESULT_READ",
                            "slave_id": receivedSlaveId,
                            "address": receivedSlaveAddress,
                        }

                else:
                    # Handle response to result read (when status is provided)
                    if function_code == modbus["READ_HOLDING_REGISTER"]:
                        byte_count = (2).to_bytes(1, "big")
                        data_bytes = status.to_bytes(2, "big")

                        response = response_data[0:2] + byte_count + data_bytes
                        crc = ComputeCrc(response).to_bytes(2, "little")
                        SafeSerialWrite(response + crc)

                    return None

            except Exception as e:
                print(f"Error during Modbus communication: {e}")
                break

    return None


# -----------------------------------------------------------------------------
# Image Processing Functions
# -----------------------------------------------------------------------------


def RotateImage(image: np.ndarray, angle: float) -> np.ndarray:
    """
    Rotates the image to the desired angle without black borders.

    Args:
        image (np.ndarray): The image to rotate.
        angle (float): The rotation angle in degrees.

    Returns:
        np.ndarray: The rotated image.
    """
    if image is None:
        return None

    (h, w) = image.shape[:2]
    (cX, cY) = (w // 2, h // 2)

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


def ProcessImage(image_path: str) -> Tuple[np.ndarray, np.ndarray]:
    """
    Processes an image for analysis by applying various transformations.

    Args:
        image_path (str): The path to the image to be processed.

    Returns:
        tuple: A tuple containing:
            - morph (np.ndarray): The morphologically processed image.
            - final (np.ndarray): The final thresholded image.
    """
    try:
        # Read the image in grayscale
        image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError(f"Could not read image from {image_path}")

        # Apply contrast and brightness adjustments
        profile = (
            data["WHITE_DISPLAY_PROFILE"]
            if data.get("WHITE_DISPLAY")
            else data["STANDARD_PROFILE"]
        )
        # print(f"Processing image with profile: {profile}")
        contrasted = cv2.convertScaleAbs(
            image, alpha=profile["ALPHA"], beta=profile["BETA"]
        )

        # Resize image to match FRAME_WIDTH and FRAME_HEIGHT from config
        resized_img = cv2.resize(
            contrasted,
            dsize=(profile["RESIZED_FRAME_WIDTH"], profile["RESIZED_FRAME_HEIGHT"]),
            interpolation=cv2.INTER_CUBIC,
        )

        bilateral = cv2.bilateralFilter(resized_img, 10, 25, 55)
        # cv2.imshow("bilateral", bilateral)
        # cv2.waitKey(0)

        # Apply Gaussian Blur
        blurred = cv2.GaussianBlur(bilateral, (5, 5), 0)

        # Adaptive Thresholding
        thresh = cv2.adaptiveThreshold(
            blurred,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            profile["THRESH_BLOCKSIZE"],
            profile["THRESH_C"],
        )

        # Invert image
        # inverted = cv2.bitwise_not(thresh)
        if not data.get("WHITE_DISPLAY", False):
            # print(config["WHITE_DISPLAY"])
            inverted = cv2.bitwise_not(thresh)
        else:
            inverted = thresh  # Use original thresholded output

        # cv2.imshow("inverted", inverted)

        # Morphological operations
        kernel = np.ones((5, 5), np.uint8)
        morph = cv2.morphologyEx(inverted, cv2.MORPH_CLOSE, kernel)
        morph = cv2.morphologyEx(morph, cv2.MORPH_OPEN, kernel)

        # Final thresholding
        _, final = cv2.threshold(morph, 0, 255, cv2.THRESH_BINARY)

        return morph, final
    except Exception as e:
        print(f"Error processing image {image_path}: {e}")
        return None, None


def FindOutliers(
    dataset: List[float],
) -> Tuple[Optional[List[float]], Optional[float], Optional[float]]:
    """
    Identifies Outliers in a dataset using the Interquartile Range (IQR) method.

    Args:
        dataset (list): A list of numerical values to be analyzed for Outliers.

    Returns:
        tuple: A tuple containing:
            - list: A list of Outliers detected in the data. If no Outliers, returns None.
            - float: The calculated lower bound for outlier detection.
            - float: The calculated upper bound for outlier detection.
    """
    if (
        not dataset or len(dataset) < 4
    ):  # Need at least 4 points for meaningful quartiles
        return None, None, None

    Q1 = np.percentile(dataset, outlier["Q1_PERCENTILE"])
    Q3 = np.percentile(dataset, outlier["Q3_PERCENTILE"])
    IQR = Q3 - Q1

    # Determine thresholds based on IQR
    if IQR <= outlier["IQR_LOW_THRESHOLD_1"]:
        lowerBound = Q1 - outlier["IQR_LOW_MULTIPLIER_1"] * IQR
        upperBound = Q3 + outlier["IQR_LOW_MULTIPLIER_1"] * IQR
    elif outlier["IQR_LOW_THRESHOLD_1"] < IQR <= outlier["IQR_LOW_THRESHOLD_2"]:
        lowerBound = Q1 - outlier["IQR_LOW_MULTIPLIER_2"] * IQR
        upperBound = Q3 + outlier["IQR_LOW_MULTIPLIER_2"] * IQR
    else:
        lowerBound = Q1 - outlier["IQR_LOW_MULTIPLIER_3"] * IQR
        upperBound = Q3 + outlier["IQR_LOW_MULTIPLIER_3"] * IQR

    lowerBound = round(lowerBound)
    upperBound = round(upperBound)

    # Identify Outliers in the data
    Outliers = [x for x in dataset if x < lowerBound or x > upperBound]

    if Outliers:
        return Outliers, lowerBound, upperBound
    else:
        return None, None, None


def DetectRoiFromTemplate(
    cap, timeout_seconds=30
) -> Tuple[Optional[Tuple[int, int]], Optional[Tuple[int, int]]]:
    """
    Detects a Region of Interest (ROI) in a video stream using template matching.

    Args:
        cap: Video capture object from which frames are read.

    Returns:
        tuple: A tuple containing:
            - topLeft (tuple): The top-left coordinates of the detected ROI.
            - bottomRight (tuple): The bottom-right coordinates of the detected ROI.
            Returns (None, None) if no ROI is detected.
    """
    templates = []
    start_time = time.time()

    try:
        # Check if template folder exists
        if not os.path.exists(TEMPLATE_FOLDER_PATH):
            print(f"[ERROR] Template folder not found: {TEMPLATE_FOLDER_PATH}")
            return None, None

        for filename in os.listdir(TEMPLATE_FOLDER_PATH):
            if filename.lower().endswith((".png", ".jpg", ".jpeg")):
                template_path = os.path.join(TEMPLATE_FOLDER_PATH, filename)
                template = cv2.imread(template_path)
                if template is not None:
                    templates.append(template)
                    print(f"[DEBUG] Loaded template: {filename}")
                else:
                    print(f"[WARNING] Failed to load template: {filename}")

        if not templates:
            print("[ERROR] No valid templates found in folder.")
            return None, None

        print(f"[INFO] Starting ROI detection with {len(templates)} templates...")
        frame_count = 0
        max_frames_to_check = 300

        while not StopEventFlag.is_set():
            elapsed_time = time.time() - start_time
            if elapsed_time > timeout_seconds:
                print(
                    f"[WARNING] ROI detection timed out after {elapsed_time:.2f} seconds"
                )
                return None, None

            if frame_count >= max_frames_to_check:
                print(
                    f"[WARNING] ROI detection reached max frame check limit ({max_frames_to_check})"
                )
                return None, None

            ret, frame = cap.read()
            if not ret or frame is None:
                print("[ERROR] Could not read frame from camera")
                time.sleep(0.1)
                continue

            if frame_count % data["FRAME_SKIP_INTERVAL"] == 0:
                try:
                    frame = RotateImage(frame, roi["ROTATION_ANGLE"])
                except Exception as e:
                    print(f"[ERROR] Error preprocessing frame: {str(e)}")
                    continue

                best_match_val = 0
                best_match_loc = None
                best_template_size = None
                best_template_name = None

                for i, template in enumerate(templates):
                    try:
                        if (
                            template.shape[0] > frame.shape[0]
                            or template.shape[1] > frame.shape[1]
                        ):
                            print(
                                f"[WARNING] Template {i} too large for current frame, skipping"
                            )
                            continue

                        template_height, template_width = template.shape[:2]
                        result = cv2.matchTemplate(
                            frame, template, cv2.TM_CCOEFF_NORMED
                        )
                        _, max_val, _, max_loc = cv2.minMaxLoc(result)

                        if max_val > best_match_val:
                            best_match_val = max_val
                            best_match_loc = max_loc
                            best_template_size = (template_width, template_height)
                            best_template_name = f"Template {i}"
                    except Exception as e:
                        print(f"[ERROR] Error matching template {i}: {str(e)}")

                if (
                    best_match_val > roi["MATCH_THRESHOLD"]
                    and best_match_loc
                    and best_template_size
                ):
                    top_left = best_match_loc
                    bottom_right = (
                        top_left[0] + best_template_size[0],
                        top_left[1] + best_template_size[1],
                    )
                    print(
                        f"[INFO] ROI detected with {best_template_name}, match: {best_match_val:.4f}, "
                        f"position: {top_left} to {bottom_right}"
                    )

                    roi_width = bottom_right[0] - top_left[0]
                    roi_height = bottom_right[1] - top_left[1]
                    min_size = 20
                    if roi_width < min_size or roi_height < min_size:
                        print(
                            f"[WARNING] Rejected too small ROI: {roi_width}x{roi_height} pixels"
                        )
                        continue

                    return top_left, bottom_right

                if frame_count % 20 == 0:
                    print(
                        f"[DEBUG] Still searching... Best match so far: {best_match_val:.4f}"
                    )

            frame_count += 1
            time.sleep(0.05)

        print("[WARNING] ROI detection stopped by StopEventFlag")
        return None, None

    except Exception as e:
        print(f"[ERROR] Error during ROI detection: {str(e)}")
        return None, None


# -----------------------------------------------------------------------------
# Camera Functions
# -----------------------------------------------------------------------------


def is_camera_connected(device_name_substring="USB Camera"):
    """
    Checks if any connected device contains the specified string in its name.
    """
    wmi = win32com.client.GetObject("winmgmts:")
    for device in wmi.InstancesOf("Win32_PnPEntity"):
        name = device.Name
        if name and device_name_substring.lower() in name.lower():
            return True
    return False


def CameraWatchdog(timeout=5.0, check_interval=1.0):

    pythoncom.CoInitialize()

    global cap
    disconnected_start = None
    print("[CAM-WATCHDOG] Started")

    while not StopEventFlag.is_set():
        try:
            if not is_camera_connected(
                "USB2.0 PC CAMERA"
            ):  # 👈 Replace with actual name if needed
                now = time.time()
                if disconnected_start is None:
                    disconnected_start = now
                    print("[CAM-WATCHDOG] Camera device missing. Starting timer...")
                elif time.time() - disconnected_start > timeout:
                    print(
                        "[CAM-WATCHDOG] Camera hardware gone. Triggering StopEventFlag."
                    )
                    StopEventFlag.set()
                    break
            else:
                disconnected_start = None  # Reset if present

        except Exception as e:
            print(f"[CAM-WATCHDOG] Exception: {e}")

        time.sleep(check_interval)


def is_frame_valid(frame: Optional[np.ndarray], min_std: float = 1.5) -> bool:
    """
    Rejects frames that carry no usable display information: fully saturated
    (blown-out white from extreme exposure) or fully dead/black frames with
    almost zero pixel variance. Deliberately conservative — a legitimately
    bright white LCD background still has texture/noise, so only near-perfectly
    flat frames are rejected.
    """
    if frame is None or frame.size == 0:
        return False

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    mean_val, std_val = cv2.meanStdDev(gray)
    mean_val, std_val = float(mean_val[0][0]), float(std_val[0][0])

    if std_val < min_std and (mean_val > 253 or mean_val < 2):
        return False

    return True


def get_valid_frame(timeout=10.0, retry_interval=1.0) -> Optional[np.ndarray]:
    """
    Attempts to return a valid frame from the webcam. If the camera is disconnected,
    it retries until it reconnects or until timeout is reached. Frames that are
    structurally broken (blank/fully saturated) are rejected and retried rather
    than being handed to the processing pipeline.

    Args:
        timeout (float): Maximum time to wait for camera to reconnect (in seconds).
        retry_interval (float): Delay between retry attempts.

    Returns:
        frame (np.ndarray) or None if unavailable after timeout.
    """
    global cap
    start_time = time.time()

    while time.time() - start_time < timeout and not StopEventFlag.is_set():
        with cap_lock:
            if cap is None or not cap.isOpened():
                print("[CAM] Camera not available. Attempting reconnect...")
                cap = safe_open_camera(index=camera["CAMERA_INDEX"])

            ret, frame = cap.read() if cap is not None else (False, None)

            if not ret or frame is None:
                if cap is not None:
                    cap.release()
                cap = None

        if not ret or frame is None:
            print("[CAM] Failed to read frame. Reinitializing camera...")
            time.sleep(retry_interval)
            continue

        if not is_frame_valid(frame):
            print(
                "[CAM] Frame rejected: blank/saturated with no usable display "
                "data. Retrying..."
            )
            time.sleep(retry_interval)
            continue

        return frame

    print("[CAM] Camera unavailable after retries.")
    return None


def UpdateFrame():
    global latestFrame, running, cap
    retry_interval = 1.0  # seconds

    while running and not StopEventFlag.is_set():
        # Wait here until the event is set (i.e., not paused)
        camera_update_enabled.wait()

        try:
            with cap_lock:
                if cap is None or not cap.isOpened():
                    ret, frame = False, None
                else:
                    ret, frame = cap.read()

            if not ret or frame is None:
                # Camera is released or the read failed. Don't try to
                # reconnect/release here — let the main process handle it.
                print("[CAM] Frame read failed in UpdateFrame.")
                time.sleep(retry_interval)
                continue

            with frameLock:
                latestFrame = frame

        except Exception as e:
            print(f"[UpdateFrame] Error: {e}")
            time.sleep(retry_interval)

        time.sleep(0.01)


def analyze_digit_intensities(gray_image, bounding_boxes):
    """
    Analyzes segment intensities and returns a list of results for each segment.
    This version is robust and always returns a list of dictionaries.
    """
    # 1. First pass: Calculate all mean intensities
    all_intensities = []
    for x, y, w, h in bounding_boxes:
        # Crop the specific segment
        segment_roi = gray_image[y : y + h, x : x + w]
        if segment_roi.size == 0:
            continue

        # Create a mask of only the lit pixels
        _, mask = cv2.threshold(
            segment_roi, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        # Calculate the mean intensity of the lit pixels
        if cv2.countNonZero(mask) > 0:
            mean_intensity = cv2.mean(segment_roi, mask=mask)[0]
            all_intensities.append({"intensity": mean_intensity, "box": (x, y, w, h)})

    # 2. Early exit if not enough segments to compare
    if len(all_intensities) < 2:
        return []

    # 3. Second pass: Determine the outlier threshold using IQR
    intensity_values = [item["intensity"] for item in all_intensities]
    Q1 = np.percentile(intensity_values, 25)
    Q3 = np.percentile(intensity_values, 75)
    IQR = Q3 - Q1
    lower_bound = Q1 - (2.1 * IQR)

    # 4. Final pass: Build the final results list
    final_results = []
    for item in all_intensities:
        is_outlier = item["intensity"] < lower_bound
        final_results.append(
            {
                "is_outlier": is_outlier,
                "intensity": item["intensity"],
                "box": item["box"],
            }
        )

    return final_results


def filter_contours_by_location(
    contours: list, max_distance_multiplier: float = 2.0
) -> list:
    """
    Filters a list of contours to keep only the main spatial cluster.

    Args:
        contours (list): A list of contours detected by OpenCV.
        max_distance_multiplier (float): A multiplier for the IQR to determine the max distance.

    Returns:
        list: A filtered list of contours belonging to the main cluster.
    """
    # Need at least 3 contours to form a meaningful cluster
    if len(contours) < 3:
        return contours

    # 1. Calculate the centroid for each contour's bounding box
    centroids = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        cx = x + w // 2
        cy = y + h // 2
        centroids.append((cx, cy))

    centroids = np.array(centroids)

    # 2. Find the median centroid (the "heart" of the cluster)
    median_cx = np.median(centroids[:, 0])
    median_cy = np.median(centroids[:, 1])
    median_centroid = np.array([median_cx, median_cy])

    # 3. Calculate the distance of each centroid from the median
    distances = np.sqrt(np.sum((centroids - median_centroid) ** 2, axis=1))

    # 4. Use IQR on the distances to find the outlier threshold
    Q1 = np.percentile(distances, 25)
    Q3 = np.percentile(distances, 75)
    IQR = Q3 - Q1

    # Any contour further than this distance from the center is an outlier
    max_distance = Q3 + (IQR * max_distance_multiplier)

    # 5. Filter the original contours
    filtered_contours = []
    for i, cnt in enumerate(contours):
        if distances[i] <= max_distance:
            filtered_contours.append(cnt)

    num_discarded = len(contours) - len(filtered_contours)
    # if num_discarded > 0:
    # print(f"Spatial filter discarded {num_discarded} outlier contour(s).")

    return filtered_contours


def filter_nested_contours(contours: list, hierarchy: np.ndarray) -> list:
    """
    Filters out contours that are nested inside others, keeping only the parent contours.

    Args:
        contours (list): The list of contours from cv2.findContours.
        hierarchy (np.ndarray): The hierarchy output from cv2.findContours.

    Returns:
        list: A new list containing only the outermost (parent) contours.
    """
    if hierarchy is None or len(hierarchy) == 0:
        return contours

    # The hierarchy is a 3D array, so we access the first plane.
    # Each entry is [Next, Previous, First_Child, Parent]
    # We want to keep contours where the Parent index is -1.
    hierarchy = hierarchy[0]

    filtered_contours = []
    for i, contour in enumerate(contours):
        # Check if the contour has a parent
        parent_index = hierarchy[i][3]
        if parent_index == -1:
            # This contour is not inside another one, so we keep it.
            filtered_contours.append(contour)

    return filtered_contours


# --- MODIFICATION: New helper function for intensity check on a single image ---
def perform_intensity_check_on_image(image_path: str) -> bool:
    """
    Performs the full intensity check pipeline on a saved image file.
    Returns True if the check passes (no outliers), False otherwise.
    """
    try:
        image = cv2.imread(image_path)
        if image is None:
            print(f"Failed to read image for intensity check: {image_path}")
            return False

        gray_frame = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray_frame, (7, 7), 0)
        _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        contours, hierarchy = cv2.findContours(
            binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
        )
        contours = filter_nested_contours(contours, hierarchy)
        filtered_contours = filter_contours_by_location(contours)

        bounding_boxes = []
        for cnt in filtered_contours:
            if (
                cv2.contourArea(cnt) > data["MIN_CONTOUR_AREA"]
            ):  # Use a reasonable area filter
                bounding_boxes.append(cv2.boundingRect(cnt))

        if not bounding_boxes:
            print("Warning: No bounding boxes found for intensity check.")
            return True  # Pass if no digits are found to check

        intensity_results = analyze_digit_intensities(gray_frame, bounding_boxes)

        for result in intensity_results:
            if result["is_outlier"]:
                print(
                    f"Dim digit detected in {os.path.basename(image_path)} with intensity {result['intensity']:.2f}"
                )
                return False  # Outlier found, fail the check

        return True  # No outliers found, pass the check
    except Exception as e:
        print(f"Error during intensity check for {image_path}: {e}")
        return False

    # def ShowLiveFeed(topLeft: int, bottomRight: int) -> None:
    """
    Continuously displays the live feed from the camera, with ROI detection applied.
    """
    try:
        cv2.namedWindow("Live Feed", cv2.WINDOW_NORMAL)
        while not StopEventFlag.is_set():
            with frameLock:
                frame = latestFrame.copy() if latestFrame is not None else None

            if frame is not None:
                # Apply ROI (if detected)
                frame = RotateImage(frame, roi["ROTATION_ANGLE"])
                if topLeft is not None and bottomRight is not None:
                    frame = frame[
                        topLeft[1] : bottomRight[1], topLeft[0] : bottomRight[0]
                    ]

                    if (
                        config.get("DISPLAY_TYPE") == "LED"
                    ):  # Show contours only in WHITE_DISPLAY mode
                        output_image = frame.copy()
                        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                        blurred = cv2.GaussianBlur(gray_frame, (5, 5), 0)
                        _, binary = cv2.threshold(
                            blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
                        )
                        # --- MODIFICATION STARTS HERE ---

                        # 1. Find ALL contours initially
                        contours, hierarchy = cv2.findContours(
                            binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
                        )

                        contours = filter_nested_contours(contours, hierarchy)

                        # 2. Apply the new spatial filter to remove noise contours
                        filtered_contours = filter_contours_by_location(contours)

                        # 3. Proceed with the filtered contours
                        bounding_boxes = []
                        for cnt in filtered_contours:
                            if cv2.contourArea(cnt) > 150 or cv2.contourArea(cnt) < 30:
                                bounding_boxes.append(cv2.boundingRect(cnt))

                        # --- Call the local function here ---
                        intensity_results = analyze_digit_intensities(
                            gray_frame, bounding_boxes
                        )

                        for result in intensity_results:
                            x, y, w, h = result["box"]
                            intensity = result["intensity"]
                            color = (0, 0, 255) if result["is_outlier"] else (0, 255, 0)

                            cv2.rectangle(
                                output_image, (x, y), (x + w, y + h), color, 2
                            )
                            cv2.putText(
                                output_image,
                                f"{intensity:.1f}",
                                (x, y - 10),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.5,
                                color,
                                2,
                            )

                        cv2.imshow("Live Feed", output_image)
                    else:
                        cv2.imshow("Live Feed", frame)

            # Handle key events
            if cv2.waitKey(1) & 0xFF == 27:  # Exit on 'ESC' key
                break

            time.sleep(0.03)  # Limit update rate to reduce CPU usage

    except Exception as e:
        print(f"Error in live feed display: {e}")
    finally:
        cv2.destroyAllWindows()


def ShowLiveFeed(topLeft: int, bottomRight: int) -> None:
    """
    Continuously displays the live feed from the camera, with ROI detection applied.
    Includes temporal smoothing to reduce flicker. (Corrected Version)
    """
    # Variables for flicker reduction
    contour_memory = {}
    history_length = 5
    fail_threshold = 3
    max_distance_tracking = 30

    try:
        cv2.namedWindow("Live Feed", cv2.WINDOW_NORMAL)
        while not StopEventFlag.is_set():
            with frameLock:
                frame = latestFrame.copy() if latestFrame is not None else None

            if frame is not None:
                frame = RotateImage(frame, roi["ROTATION_ANGLE"])
                if topLeft is not None and bottomRight is not None:
                    frame = frame[
                        topLeft[1] : bottomRight[1], topLeft[0] : bottomRight[0]
                    ]

                    if config.get("DISPLAY_TYPE") == "LED" and is_testing_active:
                        output_image = frame.copy()
                        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        # --- MODIFICATION STARTS HERE ---
                        # Check if the screen is black before doing any processing.
                        # Calculate the average intensity of the grayscale ROI.
                        avg_intensity = np.mean(gray_frame)

                        # This threshold determines what is considered a "black" screen.
                        # You may need to tune this value based on camera/lighting.
                        BLACK_SCREEN_INTENSITY_THRESHOLD = 3.5

                        # print(f"Avg Intensity: {avg_intensity:.2f}")

                        # If the average intensity is below the threshold, skip processing.
                        if avg_intensity < BLACK_SCREEN_INTENSITY_THRESHOLD:
                            # Just show the unprocessed frame and continue to the next loop iteration.
                            cv2.imshow("Live Feed", frame)
                            if cv2.waitKey(1) & 0xFF == 27:
                                break
                            time.sleep(0.03)
                            continue  # Skip the rest of the loop
                        # --- MODIFICATION ENDS HERE ---

                        blurred = cv2.GaussianBlur(gray_frame, (7, 7), 0)
                        _, binary = cv2.threshold(
                            blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
                        )

                        contours, hierarchy = cv2.findContours(
                            binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
                        )
                        contours = filter_nested_contours(contours, hierarchy)
                        filtered_contours = filter_contours_by_location(contours)

                        bounding_boxes = []
                        current_centroids = (
                            {}
                        )  # Maps current centroid -> current bounding box
                        for cnt in filtered_contours:
                            if 10 < cv2.contourArea(cnt):
                                x, y, w, h = cv2.boundingRect(cnt)
                                bounding_boxes.append((x, y, w, h))
                                cx, cy = x + w // 2, y + h // 2
                                current_centroids[(cx, cy)] = (x, y, w, h)

                        intensity_results = analyze_digit_intensities(
                            gray_frame, bounding_boxes
                        )

                        # Debounce/flicker reduction logic
                        unmatched_memory = list(contour_memory.keys())

                        for centroid, box in current_centroids.items():
                            best_match = None
                            min_dist = max_distance_tracking

                            for mem_centroid in unmatched_memory:
                                dist = np.sqrt(
                                    (centroid[0] - mem_centroid[0]) ** 2
                                    + (centroid[1] - mem_centroid[1]) ** 2
                                )
                                if dist < min_dist:
                                    min_dist = dist
                                    best_match = mem_centroid

                            fail_status = 0
                            for res in intensity_results:
                                if res["box"] == box and res["is_outlier"]:
                                    fail_status = 1
                                    break

                            if best_match:
                                contour_memory[best_match]["history"].append(
                                    fail_status
                                )
                                contour_memory[best_match][
                                    "last_seen_centroid"
                                ] = centroid
                                contour_memory[best_match]["frames_since_seen"] = 0
                                unmatched_memory.remove(best_match)
                            else:
                                contour_memory[centroid] = {
                                    "history": deque(
                                        [fail_status], maxlen=history_length
                                    ),
                                    "last_seen_centroid": centroid,
                                    "frames_since_seen": 0,
                                }

                        stale_keys = []
                        for key, data in contour_memory.items():
                            data["frames_since_seen"] += 1
                            if data["frames_since_seen"] > history_length * 2:
                                stale_keys.append(key)
                        for key in stale_keys:
                            del contour_memory[key]

                        # --- MODIFICATION STARTS HERE ---
                        # Draw boxes based on smoothed history
                        for data in contour_memory.values():
                            # Get the most recent centroid of the tracked digit
                            last_centroid = data["last_seen_centroid"]

                            # Check if this digit is visible in the CURRENT frame
                            box = current_centroids.get(last_centroid)

                            if box:  # Only draw if the box exists in the current frame
                                x, y, w, h = box

                                # Determine color from history
                                color = (
                                    (0, 0, 255)
                                    if sum(data["history"]) >= fail_threshold
                                    else (0, 255, 0)
                                )

                                cv2.rectangle(
                                    output_image, (x, y), (x + w, y + h), color, 2
                                )
                        # --- MODIFICATION ENDS HERE ---

                        cv2.imshow("Live Feed", output_image)
                    else:
                        cv2.imshow("Live Feed", frame)

            if cv2.waitKey(1) & 0xFF == 27:
                break

            time.sleep(0.03)

    except Exception as e:
        print(f"Error in live feed display: {e}")
    finally:
        cv2.destroyAllWindows()


def Cleanup():
    """
    Clean up resources before exiting.
    """
    global running, ser, cap
    running = False

    # Close camera
    with cap_lock:
        if cap:
            cap.release()
            cap = None

    # Close serial port
    with ser_lock:
        if ser and ser.is_open:
            try:
                ser.close()
            except:
                pass

    # Close OpenCV windows
    cv2.destroyAllWindows()


# -----------------------------------------------------------------------------
# LED Section Functions
# -----------------------------------------------------------------------------


def CaptureImageLed(index: int) -> Optional[str]:
    """
    Captures the latest frame from the video feed and saves it as an image.

    Args:
        index (int): The index to be used in the image filename for saving.

    Returns:
        str or None: The filename of the captured image if successful;
                      otherwise, returns None if capturing the image failed.
    """
    global latestFrame, topLeft, bottomRight

    try:
        frame = get_valid_frame(timeout=10)

        if frame is None:
            print("Failed to capture image.")
            return None

        if topLeft and bottomRight:
            # Crop the frame using the detected ROI
            cropped_frame = frame[
                topLeft[1] : bottomRight[1], topLeft[0] : bottomRight[0]
            ]
            # Create directory if it doesn't exist
            os.makedirs(CAPTURED_IMG_LED, exist_ok=True)
            # Save the frame
            file_name = f"{CAPTURED_IMG_LED}/img{index}.jpg"
            cv2.imwrite(file_name, cropped_frame)
            print(f"Image {index + 1} captured.")
            return file_name
        else:
            print("ROI not detected. Cannot capture image.")
            return None
    except Exception as e:
        print(f"Error capturing LED image: {e}")
        return None


def RunModelLed(
    images: List[str], dclasses: List[int], counts: List[int]
) -> List[bool]:
    """
    Runs the LED model on a list of images and collects results.

    Args:
        images (list): A list of images to be processed by the model.
        dclasses (list): A list of detected classes corresponding to the images.
        counts (list): A list of counts of detected objects corresponding to the images.

    Returns:
        list: A list of results from the model for each processed image.
    """
    results = []

    try:
        for image, dclass, count in zip(images, dclasses, counts):
            result = general.loadmodel_led_flask.result(image, dclass, count)
            results.append(result)
        return results
    except Exception as e:
        print(f"Error running LED model: {e}")
        return [False] * len(images)  # Return failure for all images on error


def ProcessLed(unit_count: int) -> Optional[str]:
    """
    Processes LED units by capturing images and running the detection model.

    Args:
        unit_count (int): The number of units to be processed.


    Returns:
        str or None: "Pass" if all images pass detection, "Fail" if any fail,
                    None if processing was interrupted or failed.
    """

    # --- ADD THIS BLOCK ---
    global cap, camera_update_enabled
    print(f"Resetting camera for new unit {unit_count}...")
    camera_update_enabled.clear()  # Pause the live feed thread
    time.sleep(0.1)  # Allow a moment for the thread to pause

    with cap_lock:
        if cap and cap.isOpened():
            cap.release()
        cap = None
    print("Camera released. Waiting for Modbus trigger...")
    # --- END OF BLOCK ---

    global process_start, is_testing_active
    is_testing_active = True
    print(f"Processing unit {unit_count}")
    images = []  # List to hold image file names
    dclasses = []  # List to hold detected classes
    counts = []  # List to hold counts of detected objects
    labels_counts = []  # List to hold tuples of labels and counts
    intensity_results_list = []
    index = 0  # Initialize the index for capturing images
    termination_reason = None  # To track why processing was terminated

    try:

        while index < int(config["PAGE_COUNT"]) and not StopEventFlag.is_set():
            try:
                # Get communication response
                modbus_data = Modbus()

                if modbus_data is None:
                    continue  # Skip to the next iteration if no data received

                # Check F9 pressed
                if (
                    modbus_data["type"] == "F9"
                    and modbus_data["flag"] == 1
                    and modbus_data["address"] == modbus["F9_STOP_ADDRESS"]
                ):
                    termination_reason = "F9 pressed."
                    break

                # Check for data message
                elif (
                    modbus_data["type"] == "DATA"
                    and modbus_data["slave_id"] == modbus["SLAVE_ID"]
                    and modbus_data["address"] == modbus["SLAVE_ADD_CLS_QUANT"]
                ):
                    label = modbus_data["label"]
                    count = modbus_data["count"]

                    if None in (label, count):
                        continue  # Skip if data is invalid

                    file_name = CaptureImageLed(index)

                    if file_name is None:
                        print("Skipping to next unit due to capture failure.")
                        break

                    # --- MODIFICATION: Perform intensity check on the captured image ---
                    intensity_pass = perform_intensity_check_on_image(file_name)
                    intensity_results_list.append(intensity_pass)
                    # --- End of modification ---

                    # Store the captured data
                    images.append(file_name)
                    dclasses.append(label)
                    counts.append(count)
                    labels_counts.append((label, count))
                    index += 1
                else:
                    # time.sleep(0.01)  # Small delay to reduce CPU load````
                    continue
            except Exception as e:
                termination_reason = f"PROCESSING_ERROR: {str(e)}"
                break

        if images and not termination_reason and not StopEventFlag.is_set():
            try:
                print("All images captured. Running detection on the batch...")
                process_start = time.time()
                model_results = RunModelLed(images, dclasses, counts)

                if not model_results:
                    print("Error: No results returned from model")
                    return None

                final_results = []
                for i, (label, count) in enumerate(labels_counts):
                    # --- MODIFICATION: Combine model and intensity results ---
                    model_pass = model_results[i]
                    intensity_pass = intensity_results_list[i]
                    final_pass = model_pass and intensity_pass
                    final_results.append(final_pass)

                    print(
                        f"Image {label} with count {count}: Model={'Pass' if model_pass else 'Fail'}, "
                        f"Intensity={'Pass' if intensity_pass else 'Fail'} -> FINAL: {'Pass' if final_pass else 'Fail'}"
                    )
                # Wait for response from slave device
                # timeout_start = time.time()
                while not StopEventFlag.is_set():
                    modbus_data = Modbus()

                    if modbus_data is None:
                        continue

                    if (
                        modbus_data["type"] == "F9"
                        and modbus_data["flag"] == 1
                        and modbus_data["address"] == modbus["F9_STOP_ADDRESS"]
                    ):
                        termination_reason = "F9 pressed during result stage."
                        print(termination_reason)
                        break

                    elif (
                        modbus_data["type"] == "RESULT_READ"
                        and modbus_data["address"] == modbus["SLAVE_ADD_RESULT"]
                    ):
                        if all(final_results):
                            print("Pass")
                            Modbus(status=1)  # Send result response to PLC
                            resutlsTh.clear()
                            return "Pass"
                        else:
                            print("Fail")
                            Modbus(status=2)
                            resutlsTh.clear()
                            return "Fail"
            except Exception as e:
                termination_reason = f"MODEL_ERROR: {str(e)}"
                print(termination_reason)
        else:
            while not StopEventFlag.is_set():
                modbus_data = Modbus()

                if modbus_data is None:
                    continue

                if (
                    modbus_data["type"] == "RESULT_READ"
                    and modbus_data["address"] == modbus["SLAVE_ADD_RESULT"]
                ):
                    print("Fail")
                    Modbus(status=2)
                    resutlsTh.clear()
                    return "Fail"

    finally:
        is_testing_active = False
        # Guaranteed cleanup
        if termination_reason:
            print(f"Processing terminated: {termination_reason}")
    return None


def MainLed(timeout=60, roi_retry_attempts=3, roi_retry_delay=2):
    """
    Main loop for processing LED units.
    """
    global topLeft, bottomRight, running, process_start
    process_start = 0.0
    start_time = time.time()
    unitCount = 0
    liveFeedThread = None
    running = True

    try:
        ser = safe_open_serial(config)
        if not ser or not ser.is_open:
            print("Error: Could not open serial port")
            return -1

        cap = safe_open_camera(index=camera["CAMERA_INDEX"])
        if not cap or not cap.isOpened():
            print("Error: Could not open webcam.")
            return -1

        watchdog_thread = threading.Thread(target=CameraWatchdog, daemon=True)
        watchdog_thread.start()

        print("Webcam initialized successfully")

        # Attempt ROI detection with retry mechanism
        topLeft, bottomRight = None, None
        for attempt in range(roi_retry_attempts):

            print(f"ROI detection attempt {attempt+1}/{roi_retry_attempts}")
            try:
                topLeft, bottomRight = DetectRoiFromTemplate(cap)
                if topLeft is not None and bottomRight is not None:
                    print(
                        f"ROI detected at coordinates: Top Left {topLeft}, Bottom Right {bottomRight}"
                    )
                    break
                else:
                    print("ROI detection failed, retrying...")
                    time.sleep(roi_retry_delay)
            except Exception as e:
                print(f"ROI detection error: {str(e)}")
                if attempt < roi_retry_attempts - 1:  # Don't sleep on the last attempt
                    time.sleep(roi_retry_delay)

        # Check final ROI detection status
        if topLeft is None or bottomRight is None:
            print("ROI could not be detected after all attempts. Exiting.")
            return -1

        # Start live feed in a separate thread
        try:
            liveFeedThread = threading.Thread(
                target=lambda: ShowLiveFeed(topLeft=topLeft, bottomRight=bottomRight),
                daemon=True,
            )
            liveFeedThread.start()
            print("Live feed thread started successfully")
            # Start frame update thread
            frame_thread = threading.Thread(target=lambda: UpdateFrame(), daemon=True)
            frame_thread.start()

        except Exception as e:
            print(f"Failed to start live feed thread: {str(e)}")
            # Continue execution even if live feed fails

        # Main processing loop
        while not StopEventFlag.is_set():
            # Check for timeout
            # if time.time() - start_time > timeout:
            #     print(f"Session timeout reached ({timeout} seconds)")
            #     break

            try:
                # Process the current unit with timeout protection

                results = ProcessLed(unitCount + 1)  # Pass the next unit number
                process_duration = time.time() - process_start

                if results is not None:
                    unitCount += 1
                    print(
                        f"Unit {unitCount} processed successfully in {process_duration:.2f} seconds."
                    )

                    # Optional: Add delay between processing units if needed
                    # time.sleep(0.5)
                else:
                    print("Processing returned no results, attempting next cycle")

            except KeyboardInterrupt:
                print("Processing interrupted by user")
                break
            except Exception as e:
                print(f"Error processing unit {unitCount + 1}: {str(e)}")
                # Consider implementing a retry mechanism here if appropriate
                time.sleep(1)  # Prevent CPU spinning on repeated errors

        print(f"Processing complete. Processed {unitCount} units successfully.")
        return unitCount

    except KeyboardInterrupt:
        print("Operation interrupted by user")
        return unitCount
    except Exception as e:
        print(f"Unexpected error in MainLcd: {str(e)}")
        return -1
    finally:
        # Ensure proper cleanup happens in all cases
        try:
            # Signal threads to stop
            StopEventFlag.set()

            # Wait for live feed thread to terminate with timeout
            if liveFeedThread and liveFeedThread.is_alive():
                liveFeedThread.join(timeout=2.0)

            # Call cleanup function to release resources
            Cleanup()
            print("Resources cleaned up successfully")
        except Exception as e:
            print(f"Error during cleanup: {str(e)}")


# -----------------------------------------------------------------------------
# LCD Section Functions
# -----------------------------------------------------------------------------


def CaptureImageLcd(index: int) -> Optional[str]:
    """
    Captures an image from the latest frame, processes it by rotating,
    and crops it based on detected ROI coordinates.

    Args:
        index (int): The index used to generate the filename for the saved image.

    Returns:
        str or None: The filename where the image is saved, or None if the capture failed.
    """
    global latestFrame, topLeft, bottomRight

    try:
        frame = get_valid_frame(timeout=10)

        if frame is None:
            print("Failed to capture image.")
            return None

        frame = RotateImage(frame, roi["ROTATION_ANGLE"])

        if topLeft and bottomRight:
            # Crop the frame using the detected ROI
            cropped_frame = frame[
                topLeft[1] : bottomRight[1], topLeft[0] : bottomRight[0]
            ]

            # Ensure directory exists
            os.makedirs(CAPTURED_IMG_LCD, exist_ok=True)

            # Save the cropped frame to a file
            file_name = f"{CAPTURED_IMG_LCD}/img{index}.jpg"
            cv2.imwrite(file_name, cropped_frame)
            print(f"Image {index + 1} captured")
            return file_name
        else:
            print("ROI not detected. Cannot capture image.")
            return None
    except Exception as e:
        print(f"Error capturing LCD image: {e}")
        return None


def Outliers(img_path: str, unit_count: int, index: int) -> List:
    """
    Identifies Outliers in image contours by processing the input image and analyzing contour perimeters.

    The function performs the following steps:
    1. Processes the image to prepare it for contour detection.
    2. Applies Gaussian blur and thresholding to create an inverted image.
    3. Finds contours and calculates their perimeters.
    4. Groups contours into clusters based on position and identifies perimeter Outliers.
    5. Highlights and saves the contours that are identified as Outliers.

    Args:
        img_path (str): The path to the image file to be processed.
        unit_count (int): Identifier used for naming the output images.

    Returns:
        list: A list of Outliers detected in the image contours.
    """
    try:
        # Define constants locally if they're not available in a config file
        MIN_CONTOUR_AREA = data["MIN_CONTOUR_AREA"]
        SIGNIFICANT_DEVIATION = data["SIGNIFICANT_DEVIATION"]  # Default if not defined
        OUTLIER_MAXVALUE = data["OUTLIER_MAXVALUE"]  # Default if not defined

        # Create required directories if they don't exist
        os.makedirs(ALPHA_IMAGE_FOLDER, exist_ok=True)

        # Use a counter that's specific to this function call
        counter = 0
        outliers_results = []

        # Process the image
        try:
            processed_image, _ = ProcessImage(img_path)
            if index == 0:
                subfolder = "T"
            elif index == 1:
                subfolder = "H"
            else:
                subfolder = None

            if subfolder:
                alpha_path = os.path.join(ALPHA_IMAGE_FOLDER, subfolder)
                os.makedirs(alpha_path, exist_ok=True)
                filter_img_path = os.path.join(alpha_path, "img.jpg")
            else:
                filter_img_path = None

            if filter_img_path:
                cv2.imwrite(filter_img_path, processed_image)

        except Exception as e:
            print(f"Error processing image {img_path}: {str(e)}")
            return []

        # Read and preprocess the image
        try:
            gray = cv2.imread(filter_img_path, cv2.IMREAD_GRAYSCALE)
            if gray is None:
                print(f"Failed to read image at {filter_img_path}")
                return []

            bilateral = cv2.bilateralFilter(gray, 10, 25, 55)
            blurred = cv2.GaussianBlur(bilateral, (5, 5), 0)
            _, inverted_image = cv2.threshold(
                blurred, OUTLIER_MAXVALUE, 255, cv2.THRESH_BINARY_INV
            )
            # cv2.imshow("inverted_image", inverted_image)
            # cv2.imwrite("inverted_image.jpg", inverted_image)
        except Exception as e:
            print(f"Error preprocessing image {filter_img_path}: {str(e)}")
            return []

        # Find contours
        try:
            contours, _ = cv2.findContours(
                inverted_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            contour_image = cv2.cvtColor(inverted_image, cv2.COLOR_GRAY2BGR)
            cv2.drawContours(contour_image, contours, -1, (0, 255, 0), 1)
            # cv2.imshow("contour image", contour_image)
        except Exception as e:
            print(f"Error finding contours: {str(e)}")
            return []

        # Calculate contour areas only for filtering purposes
        deviated_contours = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > MIN_CONTOUR_AREA:
                deviated_contours.append(contour)

        # Process deviated contours
        deviation_image = cv2.cvtColor(inverted_image, cv2.COLOR_GRAY2BGR)
        for contour in deviated_contours:
            x, y, w, h = cv2.boundingRect(contour)
            remove_height = int(SIGNIFICANT_DEVIATION * h)
            cv2.rectangle(
                deviation_image, (x, y), (x + w, y + remove_height), (0, 0, 0), -1
            )

        deviation_image = cv2.cvtColor(deviation_image, cv2.COLOR_BGR2GRAY)

        # Find contours on the modified image
        try:
            contours, _ = cv2.findContours(
                deviation_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            contour_image = cv2.cvtColor(deviation_image, cv2.COLOR_GRAY2BGR)
            cv2.drawContours(contour_image, contours, -1, (0, 255, 0), 1)
            # cv2.imshow("counter_image", contour_image)
        except Exception as e:
            print(f"Error finding contours on modified image: {str(e)}")
            return []

        # Store all contours with their perimeters and positions      ------------------------------------------modified 110625----------------------------
        contours_with_data = (
            []
        )  # this will store (perimeter, cX, cY, contour)                                             #contours_with_perimeters = []
        ##        original_contours = []  # Keep track of original contours for later reference

        for i, contour in enumerate(contours):
            area = cv2.contourArea(contour)

            if area > MIN_CONTOUR_AREA:
                perimeter = round(cv2.arcLength(contour, True), 2)

                # Calculate centroid
                M = cv2.moments(contour)
                if M["m00"] != 0:
                    cX = int(M["m10"] / M["m00"])
                    cY = int(M["m01"] / M["m00"])
                else:
                    cX, cY = contour[0][0]

                # Store the contour with its perimeter and position , AND the contour itself
                contours_with_data.append((perimeter, cX, cY, contour))
                ##                contours_with_perimeters.append((perimeter, cX, cY))
                ##                original_contours.append(contour)

                # Add label to the image (only perimeter)
                cv2.putText(
                    contour_image,
                    f"{int(perimeter)}",
                    (cX - 20, cY),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.4,
                    (0, 0, 255),
                    1,
                    cv2.LINE_AA,
                )

        if not contours_with_data:
            print("No valid contours found after filtering")
            return []

        # Sort contours by the x-coordinate (left to right)
        contours_with_data.sort(key=lambda x: x[1])  # Sort by cX

        # Extract sorted data
        sorted_perimeters = [data[0] for data in contours_with_data]
        sorted_contours = [
            data[3] for data in contours_with_data
        ]  # the actual contours
        perimeter_arr = np.array(sorted_perimeters)

        # Determine number of clusters (using 4 as in original code, or fewer if not enough contours)
        num_clusters = min(4, len(perimeter_arr))
        print(f"num_clusters:{num_clusters}")
        if num_clusters < 1:
            print(f"Not enough contours found in {img_path} for clustering")
            return []

        # Determine cluster size
        cluster_size = max(1, len(perimeter_arr) // num_clusters)

        # Assign clusters
        clusters = np.zeros(len(perimeter_arr), dtype=int)
        for i in range(num_clusters):
            start_idx = i * cluster_size
            end_idx = (
                len(perimeter_arr) if i == num_clusters - 1 else (i + 1) * cluster_size
            )
            clusters[start_idx:end_idx] = i

        # Store final results image for later when saving
        final_result_image = contour_image.copy()

        any_outlier_found = False
        # Process each cluster to find Outliers
        for cluster_num in range(num_clusters):
            try:
                # Get indices of elements in this cluster
                cluster_indices = np.where(clusters == cluster_num)[0]

                # Extract perimeter values for this cluster
                cluster_perimeters = [perimeter_arr[i] for i in cluster_indices]

                if not cluster_perimeters:
                    continue

                # Store contours corresponding to this cluster(now correctly mapped)
                cluster_contours = [sorted_contours[i] for i in cluster_indices]
                # print(perimeter_arr)
                ##                print(f"Cluster perimeters:{cluster_perimeters}")
                # Find Outliers in the cluster
                Outliers, lower_bound, upper_bound = FindOutliers(cluster_perimeters)

                if Outliers:
                    any_outlier_found = True
                    outliers_results.append(Outliers)

                    ##                    cluster_info = list(zip(cluster_perimeters, cluster_indices)) #perimeter and origianl indices
                    # For each outlier, find its index and draw a bounding box
                    for outlier in Outliers:
                        # Get all instances of this outlier value (there could be multiple with same perimeter)
                        outlier_positions = [
                            i for i, p in enumerate(cluster_perimeters) if p == outlier
                        ]

                        ##                        matched =  [idx for perim, idx in cluster_info if perim == outlier]
                        ##                        print(f"matched:{matched}")
                        for pos in outlier_positions:
                            if pos < len(cluster_contours):
                                # Get the corresponding contour
                                outlier_contour = cluster_contours[pos]

                                # Draw bounding box around the outlier
                                x, y, w, h = cv2.boundingRect(outlier_contour)
                                cv2.rectangle(
                                    final_result_image,
                                    (x, y),
                                    (x + w, y + h),
                                    (0, 0, 255),
                                    2,
                                )
                                print(
                                    f"Outlier found in cluster {cluster_num}: "
                                    f"perimeter={outlier}, bounding box at ({x}, {y}, {w}, {h})"
                                )

                    # Save the image with detected Outliers
                    try:
                        SAVE_FOLDER_FAIL = GetResourcePath(
                            f"Failed_images\\failed_lcd\\{unit_count}"
                        )
                        os.makedirs(SAVE_FOLDER_FAIL, exist_ok=True)

                        # Create a unique filename
                        base_name = os.path.basename(img_path).split(".")[0]
                        unique_filename = f"{base_name}_{unit_count}.jpg"
                        save_path_fail = os.path.join(SAVE_FOLDER_FAIL, unique_filename)

                        cv2.imwrite(save_path_fail, final_result_image)
                        counter += 1
                        # print(f"Outliers:{Outliers}")
                    except Exception as e:
                        print(f"Error saving outlier image: {str(e)}")

            except Exception as e:
                print(f"Error processing cluster {cluster_num}: {str(e)}")
        if not any_outlier_found:
            print("Pass")

        return outliers_results

    except Exception as e:
        print(f"Unexpected error in Outliers function: {str(e)}")
        return []


# def FindOutliers(
#     dataset: List[Union[float, int]],
#     q1_percentile: Optional[float] = None,
#     q3_percentile: Optional[float] = None,
#     iqr_threshold_1: Optional[float] = None,
#     iqr_threshold_2: Optional[float] = None,
#     iqr_multiplier_1: Optional[float] = None,
#     iqr_multiplier_2: Optional[float] = None,
#     iqr_multiplier_3: Optional[float] = None,
# ) -> Tuple[Optional[List[float]], Optional[float], Optional[float]]:
#     """
#     Enhanced IQR-based outlier detection with configurable thresholds and NaN handling.

#     Args:
#         dataset: Input numerical data (NaNs are automatically filtered)
#         q1_percentile: Override for Q1 percentile (default: data.Q1_PERCENTILE)
#         q3_percentile: Override for Q3 percentile (default: data.Q3_PERCENTILE)
#         iqr_threshold_1/2: Custom IQR threshold values
#         iqr_multiplier_1/2/3: Custom IQR multipliers

#     Returns:
#         Tuple: (Outliers, lower_bound, upper_bound) or (None, None, None) if no Outliers

#     Example:
#         >>> data = [1, 2, 3, 100]
#         >>> FindOutliers(data, iqr_multiplier_1=1.5)
#         ([100], 0.25, 4.75)
#     """
#     # Configure logging
#     logging.basicConfig(level=logging.WARNING)
#     logger = logging.getLogger(__name__)

#     # Early return for empty input
#     if not dataset:
#         logger.warning("Empty dataset provided")
#         return None, None, None

#     try:
#         # Clean data and convert to numpy array
#         clean_data = np.array([x for x in dataset if not np.isnan(x)], dtype=np.float64)
#         if len(clean_data) == 0:
#             logger.warning("All values are NaN")
#             return None, None, None

#         # Use provided parameters or fall back to module defaults
#         Q1 = np.percentile(clean_data, q1_percentile if q1_percentile is not None else data.Q1_PERCENTILE)
#         Q3 = np.percentile(clean_data, q3_percentile if q3_percentile is not None else data.Q3_PERCENTILE)
#         IQR = Q3 - Q1

#         # Determine dynamic bounds with configurable thresholds
#         thresholds = [
#             (iqr_threshold_1 if iqr_threshold_1 is not None else data.IQR_LOW_THRESHOLD_1,
#              iqr_multiplier_1 if iqr_multiplier_1 is not None else data.IQR_LOW_MULTIPLIER_1),

#             (iqr_threshold_2 if iqr_threshold_2 is not None else data.IQR_LOW_THRESHOLD_2,
#              iqr_multiplier_2 if iqr_multiplier_2 is not None else data.IQR_LOW_MULTIPLIER_2),

#             (float('inf'),  # Catch-all for larger IQR values
#              iqr_multiplier_3 if iqr_multiplier_3 is not None else data.IQR_LOW_MULTIPLIER_3)
#         ]

#         for threshold, multiplier in thresholds:
#             if IQR <= threshold:
#                 lower_bound = Q1 - multiplier * IQR
#                 upper_bound = Q3 + multiplier * IQR
#                 break

#         # Round bounds (maintain precision for small values)
#         lower_bound = round(lower_bound, 2) if lower_bound is not None else None
#         upper_bound = round(upper_bound, 2) if upper_bound is not None else None

#         # Vectorized outlier detection (faster for large datasets)
#         outlier_mask = (clean_data < lower_bound) | (clean_data > upper_bound)
#         Outliers = clean_data[outlier_mask].tolist()

#         return (Outliers, lower_bound, upper_bound) if Outliers else (None, None, None)

#     except Exception as e:
#         logger.error(f"Outlier detection failed: {str(e)}", exc_info=True)
#         return None, None, None


def RunBatchInference(
    image_path: str,
    label: int,
    count: int,
    unit_count: int,
    output_dir: str,
) -> Tuple[Optional[Any], Optional[str]]:
    """Run batch inference on an image with enhanced error handling and resource management.

    Args:
        image_path: Path to the input image.
        label: Associated label for inference.
        count: Associated count for inference.
        unit_count: Number of units for model inference.
        output_dir: Directory to save processed images (default: "batch_output").

    Returns:
        Tuple containing:
            - Inference result (None if failed)
            - Path to saved image (None if failed)
    """
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    try:
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        # Process the image
        morph, processed_image = ProcessImage(image_path)
        if (
            processed_image is None
            or not isinstance(processed_image, np.ndarray)
            or processed_image.size == 0
        ):
            logger.error(f"Image processing failed for {image_path}")
            return None

        # Generate unique filename with timestamp
        ##        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(output_dir, "img.jpg")

        # Save processed image
        if not cv2.imwrite(output_path, processed_image):
            logger.error(f"Failed to save processed image to {output_path}")
            return None

        # Run inference
        try:
            result = general.loadmodel_lcd_flask.result(
                output_path, label, count, unit_count
            )
            # logger.info(f"Inference successful for {image_path}")
            return result
        except Exception as inference_error:
            logger.error(f"Inference failed: {str(inference_error)}")
            return None

    except Exception as e:
        logger.error(f"Batch inference failed: {str(e)}", exc_info=True)
        return None


def ProcessLcd(unitCount: int) -> Optional[Any]:
    """Processes LCD unit images with fail-fast outlier detection and guaranteed resource cleanup.

    Args:
        unitCount: The unit number being processed.

    Returns:
        Final detection result or None if terminated early.

    Raises:
        RuntimeError: If critical failures occur during processing.
    """
    # --- ADD THIS BLOCK ---
    global cap, camera_update_enabled
    print(f"Resetting camera for new unit {unitCount}...")
    camera_update_enabled.clear()  # Pause the live feed thread
    time.sleep(0.1)  # Allow a moment for the thread to pause

    with cap_lock:
        if cap and cap.isOpened():
            cap.release()
        cap = None
    print("Camera released. Waiting for Modbus trigger...")
    # --- END OF BLOCK ---

    global i, flag1, batchImages, batchAlpha, resutlsTh, imagesResults, process_start
    # Initialize state
    print(f"Processing unit: {unitCount}")
    flag1 = 0
    i = 0
    imagesResults = []
    termination_reason = None

    try:

        while i < int(config["PAGE_COUNT"]) and not StopEventFlag.is_set():
            try:
                # Unified Modbus read
                modbus_data = Modbus()

                if modbus_data is None:
                    continue

                # Check F9 pressed
                if (
                    modbus_data["type"] == "F9"
                    and modbus_data["flag"] == 1
                    and modbus_data["address"] == modbus["F9_STOP_ADDRESS"]
                ):
                    termination_reason = "F9 pressed."
                    break

                # Check label/count data
                elif (
                    modbus_data["type"] == "DATA"
                    and modbus_data["slave_id"] == modbus["SLAVE_ID"]
                    and modbus_data["address"] == modbus["SLAVE_ADD_CLS_QUANT"]
                ):
                    label = modbus_data["label"]
                    count = modbus_data["count"]

                    if None in (label, count):
                        continue  # Skip if data is invalid

                    # Proceed with image capture
                    fileName = CaptureImageLcd(i)
                    if fileName is None:
                        print("Skipping to next unit due to capture failure.")
                        break

                    batchImages.append((fileName, label, count))

                    # Outlier detection (first 2 only)
                    if flag1 == 0 and i < 2:
                        try:
                            batchAlphaRes = Outliers(
                                img_path=fileName, unit_count=unitCount, index=i
                            )
                            resutlsTh.append(not batchAlphaRes)  # True = no outlier

                            if len(resutlsTh) == 2:
                                if not all(resutlsTh):
                                    termination_reason = "OUTLIER_DETECTED"
                                    break
                                flag1 = 1
                        except Exception as e:
                            termination_reason = f"OUTLIER_CHECK_FAILED: {str(e)}"
                            break

                    i += 1

            except Exception as e:
                termination_reason = f"PROCESSING_ERROR: {str(e)}"
                break

        # Process remaining images if no early termination
        if flag1 == 1 and not termination_reason:
            try:
                print("All images captured, running detection model...")
                process_start = time.time()
                for image, label, count in batchImages[2:]:
                    result = RunBatchInference(
                        image, label, count, unitCount, output_dir=BATCH_FOLDER
                    )
                    imagesResults.append(result)

                while not StopEventFlag.is_set():
                    modbus_data = Modbus()

                    if modbus_data is None:
                        continue

                    if (
                        modbus_data["type"] == "F9"
                        and modbus_data["flag"] == 1
                        and modbus_data["address"] == modbus["F9_STOP_ADDRESS"]
                    ):
                        termination_reason = "F9 pressed during result stage."
                        print(termination_reason)
                        break

                    elif (
                        modbus_data["type"] == "RESULT_READ"
                        and modbus_data["address"] == modbus["SLAVE_ADD_RESULT"]
                    ):
                        if all(imagesResults) and all(resutlsTh):
                            print("Pass")
                            Modbus(status=1)  # Send result response to PLC
                            resutlsTh.clear()
                            return "Pass"
                        else:
                            print("Fail")
                            Modbus(status=2)
                            resutlsTh.clear()
                            return "Fail"

            except Exception as e:
                termination_reason = f"DETECTION_FAILED: {str(e)}"
        else:
            while not StopEventFlag.is_set():
                modbus_data = Modbus()

                if modbus_data is None:
                    continue

                if (
                    modbus_data["type"] == "RESULT_READ"
                    and modbus_data["address"] == modbus["SLAVE_ADD_RESULT"]
                ):
                    print("Fail")
                    Modbus(status=2)
                    resutlsTh.clear()
                    return "Fail"

    finally:
        # Guaranteed cleanup
        if termination_reason:
            print(f"Processing terminated: {termination_reason}")

        batchImages.clear()
        resutlsTh.clear()

        # Reset global state
        i = 0
        flag1 = 0

    return None


@dataclass
class ProcessingConfig:
    timeout: int = 60
    roi_retry_attempts: int = 3
    roi_retry_delay: int = 2


def MainLcd(
    timeout: int = 60, roi_retry_attempts: int = 3, roi_retry_delay: int = 2
) -> int:
    """Main communication and processing loop for handling LCD image capture and analysis.

    This function initializes the webcam, detects the Region of Interest (ROI) using a template,
    and continuously processes units of images until terminated or timeout is reached.

    Args:
        timeout (int): Maximum runtime in seconds before auto-termination (default: 60)
        roi_retry_attempts (int): Number of attempts to detect ROI (default: 3)
        roi_retry_delay (int): Delay between ROI detection attempts in seconds (default: 2)

    Returns:
        int: Number of units processed successfully, or -1 on error

    Raises:
        RuntimeError: If webcam or serial port initialization fails
        TimeoutError: If ROI detection attempts exceed maximum retries
    """
    global topLeft, bottomRight, running, process_start
    start_time = time.time()
    process_start = 0.0
    unitCount = 0
    liveFeedThread = None
    running = True
    # Initialize logger

    try:
        ser = safe_open_serial(config)
        if not ser or not ser.is_open:
            print("Error: Could not open serial port")
            return -1

        cap = safe_open_camera(index=camera["CAMERA_INDEX"])
        if not cap or not cap.isOpened():
            print("Error: Could not open webcam.")
            return -1

        watchdog_thread = threading.Thread(target=CameraWatchdog, daemon=True)
        watchdog_thread.start()

        print("Webcam initialized successfully")

        # Attempt ROI detection with retry mechanism
        topLeft, bottomRight = None, None
        for attempt in range(roi_retry_attempts):
            print(f"ROI detection attempt {attempt+1}/{roi_retry_attempts}")
            try:
                topLeft, bottomRight = DetectRoiFromTemplate(cap)
                if topLeft is not None and bottomRight is not None:
                    print(
                        f"ROI detected at coordinates: Top Left {topLeft}, Bottom Right {bottomRight}"
                    )
                    break
                else:
                    print("ROI detection failed, retrying...")
                    time.sleep(roi_retry_delay)
            except Exception as e:
                print(f"ROI detection error: {str(e)}")
                if attempt < roi_retry_attempts - 1:  # Don't sleep on the last attempt
                    time.sleep(roi_retry_delay)

        # Check final ROI detection status
        if topLeft is None or bottomRight is None:
            print("ROI could not be detected after all attempts. Exiting.")
            return -1

        # Start live feed in a separate thread
        try:
            liveFeedThread = threading.Thread(
                target=lambda: ShowLiveFeed(topLeft=topLeft, bottomRight=bottomRight),
                daemon=True,
            )
            liveFeedThread.start()
            print("Live feed thread started successfully")
            # Start frame update thread
            frame_thread = threading.Thread(target=lambda: UpdateFrame(), daemon=True)
            frame_thread.start()
        except Exception as e:
            print(f"Failed to start live feed thread: {str(e)}")
            # Continue execution even if live feed fails

        # Main processing loop
        while not StopEventFlag.is_set():
            # Check for timeout
            # if time.time() - start_time > timeout:
            #     print(f"Session timeout reached ({timeout} seconds)")
            #     break

            try:
                # Process the current unit with timeout protection
                results = ProcessLcd(unitCount + 1)  # Pass the next unit number
                process_duration = time.time() - process_start

                if results is not None:
                    unitCount += 1
                    print(
                        f"Unit {unitCount} processed successfully in {process_duration:.2f} seconds"
                    )

                    # Optional: Add delay between processing units if needed
                    # time.sleep(0.5)
                else:
                    print("Processing returned no results, attempting next cycle")

            except KeyboardInterrupt:
                print("Processing interrupted by user")
                break
            except Exception as e:
                print(f"Error processing unit {unitCount + 1}: {str(e)}")
                # Consider implementing a retry mechanism here if appropriate
                time.sleep(1)  # Prevent CPU spinning on repeated errors

        print(f"Processing complete. Processed {unitCount} units successfully.")
        return unitCount

    except KeyboardInterrupt:
        print("Operation interrupted by user")
        return unitCount
    except Exception as e:
        print(f"Unexpected error in MainLcd: {str(e)}")
        return -1
    finally:
        # Ensure proper cleanup happens in all cases
        try:
            # Signal threads to stop
            StopEventFlag.set()

            # Wait for live feed thread to terminate with timeout
            if liveFeedThread and liveFeedThread.is_alive():
                liveFeedThread.join(timeout=2.0)

            # Call cleanup function to release resources
            Cleanup()
            print("Resources cleaned up successfully")
        except Exception as e:
            print(f"Error during cleanup: {str(e)}")


if __name__ == "__main__":
    import time
    from config_files.config import config

    try:
        # result = Outliers("Captured_Img_LED_white\img0.jpg", 1, 1)  # use forward slash
        result = RunBatchInference(
            "Captured_Img_LED_white\\img2.jpg", 0, 224, 1, BATCH_FOLDER
        )
        print("Image processed successfully.")
        # if result:
        #     print(f"Outliers detected: {result}")
        # Optional: Display or save img
        # cv2.imshow("Processed", result)
        # cv2.imshow("_", morph)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    except Exception as e:
        print(f"Error processing image: {e}")

    time.sleep(2)  # Pause so terminal doesn't close instantly
