"""
loadmodel_lcd_v1.py

Author: Kunal Kanojiya
Date: 03/10/2024
Date modified: 26/06/25
Description:
    This script is responsible for sending images to a server for inference
    using a YOLO model. It handles the communication with the server, processes
    the inference results, and saves images based on the results.

Functionality:
    - Sends image paths to a specified server for inference.
    - Processes the returned labels and confidences to evaluate results.
    - Saves images to designated directories based on the outcome of the inference.
"""

import uuid
from datetime import datetime
import shutil
import cv2
import os
import torch
from collections import Counter
import pathlib
import sys
import json

# Add project root (parent of 'general') to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# -----------------------------------------------------------------------------

from config_files.config import *
from general import report_logger
import io
import contextlib


# Path fix for compatibility with Windows
temp = pathlib.PosixPath
pathlib.PosixPath = pathlib.WindowsPath


def GetResourcePath(relative_path):
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


def load_config_json() -> dict:
    config_path = GetResourcePath("config_files\\config_data.json")
    with open(config_path, "r") as f:
        return json.load(f)


data = load_config_json()

# Define the server address
# SERVER_URL = "http://127.0.0.1:5001/infer"  # Ensure this matches the server address and port
yolov5_dir = GetResourcePath("yolov5")
# icon_path = GetResourcePath("machine-learning.ico")
lcd_model_path = GetResourcePath(
    "models\\AdamW_yolov5n_lcd_170625.onnx"
)  # Path to LCD model

_lcdModel = None


def LoadLCDModel():
    global _lcdModel
    if _lcdModel is None:
        _lcdModel = torch.hub.load(
            yolov5_dir, "custom", path=lcd_model_path, source="local"
        )
        # Set the model parameters
        _lcdModel.iou = data["LCD_IOU"]  # Intersection over Union threshold
        _lcdModel.conf = data["LCD_CONF"]  # Confidence threshold for predictions
    return _lcdModel


# Define paths for saving results
saveFolderFail = GetResourcePath("Failed_images\\failed_lcd")

c = 0
# Function to send the image for inference to the server
# def SendInferenceRequest(imagePath):
#     data = {'imagePath': imagePath}
#     response = requests.post(SERVER_URL, json=data)

#     if response.status_code == 200:
#         result = response.json()
#         labels = result['labels']
#         confidences = result['confidences']
#         return labels, confidences
#     else:
#         print(f"Error: {response.status_code}, {response.text}")
#         return None, None


def result(file_name, label, count=None, unitCount=None):
    global c
    lcdModel = LoadLCDModel()

    # initialize the report logger
    report_logger.initialize_report()

    # Send image for inference to the YOLO server
    # labels, confidences = SendInferenceRequest(file_name)
    results = lcdModel(file_name)
    # results.show()

    # Capture the human-readable summary
    with io.StringIO() as buf, contextlib.redirect_stdout(buf):
        print(results)
        result_summary = buf.getvalue()
    # print(f"Result Summary complete: {result_summary}")
    #Extract the timing information from the results_summary
    result_summary = result_summary.split(" ")[7].strip() if result_summary else "No summary available"
    # print(f"Result Summary: {result_summary}")

    # Extract labels and confidences (handle empty / safe)
    try:
        labels = results.xyxyn[0][:, -1].numpy().tolist() if hasattr(results, "xyxyn") and len(results.xyxyn) > 0 else []
        confidences = results.xyxyn[0][:, 4].numpy().tolist() if hasattr(results, "xyxyn") and len(results.xyxyn) > 0 else []
    except Exception:
        labels = []
        confidences = []

    if labels is None:
        return False  # If inference failed

    img = cv2.imread(file_name, cv2.IMREAD_GRAYSCALE)

    # Process the results
    labels.sort()  # Sort the labels
    counter = Counter(labels)  # Count occurrences of each label
    maxCount = max(counter.values()) if counter else 0  # Find the maximum count of any label

    # Perform logic based on the received labels
    print(f"Max count: {maxCount} and Count:{count}")
    if maxCount == count:
        report_logger.append_to_report(
            file_name, "LCD", 0, confidences, result_summary, label, count, True
        )
        return True  # Inference successful
    else:
        try:
            # Build structured folder: Failed_images/failed_lcd/YYYY-MM-DD/unit_<unitCount>/expected_label_<label>_count_<count>/
            date_str = datetime.now().strftime("%Y-%m-%d")
            unit_folder = f"unit_{unitCount}" if unitCount is not None else "unit_unknown"
            expected_folder = f"expected_label_{label}_count_{count}" if (label is not None or count is not None) else "expected_unknown"
            target_dir = os.path.join(saveFolderFail, date_str, unit_folder, expected_folder)
            os.makedirs(target_dir, exist_ok=True)

            # Ask results to save annotated image into target_dir
            # results.save writes annotated image(s) into the provided directory
            results.save(save_dir=target_dir)

            # results.save will create files with original basenames inside target_dir (or under runs/ if not honored)
            # To guarantee unique filename and easy traceability, rename the most recently created file.
            uid = uuid.uuid4().hex[:8]
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_orig = os.path.splitext(os.path.basename(file_name))[0]

            # Find the saved annotated file inside target_dir.
            # We look for files that contain the original basename, or fallback to newest file in dir.
            annotated_candidate = None
            for fname in os.listdir(target_dir):
                if base_orig in fname:
                    annotated_candidate = os.path.join(target_dir, fname)
                    break

            if annotated_candidate is None:
                # fallback: pick the newest file in the directory
                entries = [os.path.join(target_dir, f) for f in os.listdir(target_dir)]
                if entries:
                    annotated_candidate = max(entries, key=os.path.getmtime)

            # If we found the file, rename it to include timestamp+uid
            annotated_path = None
            if annotated_candidate:
                ext = os.path.splitext(annotated_candidate)[1]
                new_name = f"failed_{base_orig}_{ts}_{uid}{ext}"
                annotated_path = os.path.join(target_dir, new_name)
                try:
                    shutil.move(annotated_candidate, annotated_path)
                except Exception:
                    # if move fails for any reason, keep candidate as-is
                    annotated_path = annotated_candidate

            # minimal metadata sidecar (optional but handy)
            try:
                meta = {
                    "original_file": file_name,
                    "saved_annotated": annotated_path,
                    "expected_label": label,
                    "expected_count": count,
                    "unitCount": unitCount,
                    "predicted_labels": labels,
                    "confidences": confidences,
                    "timestamp": datetime.now().isoformat(),
                }
                meta_fname = f"meta_{base_orig}_{ts}_{uid}.json"
                with open(os.path.join(target_dir, meta_fname), "w", encoding="utf-8") as mf:
                    json.dump(meta, mf, indent=2)
            except Exception as e:
                print(f"[result] Warning: could not write metadata: {e}")

            # Log to report and return False
            report_logger.append_to_report(
                file_name, "LCD", 0, confidences, result_summary, label , count, False
            )
        except Exception as e:
            print(f"[result] Error while saving failed image: {e}")
            # As last resort, try to save using cv2 if annotated save failed
            try:
                fallback_fname = os.path.join(saveFolderFail, f"failed_fallback_{base_orig}_{ts}_{uid}.jpg")
                cv2.imwrite(fallback_fname, img)
            except Exception:
                pass
        return False
        


if __name__ == "__main__":
    res = result("Batch\\img.jpg", 0, 224, 1)
    # print(res)
