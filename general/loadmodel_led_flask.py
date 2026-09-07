"""
loadmodel_led_v1.py

Author: Kunal Kanojiya
Date: 03/10/2024
Date modified: 26/06/25

Description:
    Sends images to a YOLO server for inference, checks results against criteria,
    and saves images based on the outcome. Handles communication with the server
    and processes returned labels and confidences.

Functionality:
    - Sends image paths to a specified server for inference.
    - Processes returned labels and confidences to evaluate results.
    - Saves images to designated directories based on inference outcome.
"""

import os
import sys
import cv2
import torch
import json
import pathlib
from datetime import datetime
from collections import Counter
import numpy as np

# -------------------------------------------------------------------------
# Project Imports & Path Setup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config_files.config import *
from general import report_logger
import io
import contextlib

# Path fix for compatibility with Windows
temp = pathlib.PosixPath
pathlib.PosixPath = pathlib.WindowsPath

# -------------------------------------------------------------------------
# Utility Functions

# --- ITALIC 7-Segment Geometry Blueprint ---
# Adjusted for displays that lean to the right.
SEGMENT_GEOMETRY = {
    "a": (0.00, 0.20, 0.30, 0.90),  # Top bar (Shifted Right)
    "b": (0.00, 0.50, 0.80, 1.00),  # Top Right (Shifted Right)
    "c": (0.50, 1.00, 0.65, 0.95),  # Bottom Right (Shifted Left)
    "d": (0.75, 1.00, 0.10, 0.70),  # Bottom bar (Shifted Left)
    "e": (0.50, 1.00, 0.00, 0.20),  # Bottom Left (Shifted Left)
    "f": (0.00, 0.50, 0.15, 0.40),  # Top Left (Shifted Right)
    "g": (0.35, 0.65, 0.20, 0.80),  # Middle bar (Centered)
}

# Strictly limited to the 3 master test digits
DIGIT_TRUTH_TABLE = {
    2: ["a", "b", "g", "e", "d"],
    5: ["a", "f", "g", "c", "d"],
    8: ["a", "b", "c", "d", "e", "f", "g"],
}
# --------------------------------------------


def GetResourcePath(relative_path: str) -> str:
    """
    Get absolute path to resource, works for both bundled and unbundled applications.
    """
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    else:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        return os.path.join(base_dir, relative_path)


def load_config_json() -> dict:
    config_path = GetResourcePath("config_files\\config_data.json")
    with open(config_path, "r") as f:
        return json.load(f)


# -------------------------------------------------------------------------
# Model Loading

yolov5_dir = GetResourcePath("yolov5")
led_model_path = GetResourcePath("models\\best110825_7seg.onnx")
data = load_config_json()
_ledModel = None


def LoadLEDModel():
    global _ledModel
    if _ledModel is None:
        _ledModel = torch.hub.load(
            yolov5_dir, "custom", path=led_model_path, source="local"
        )
        _ledModel.iou = data["LED_IOU"]
        _ledModel.conf = data["LED_CONF"]
    return _ledModel


# -------------------------------------------------------------------------
# Inference & Result Processing

saveFolderFail = GetResourcePath("Failed_images\\failed_led")
passLabelsInt = list(range(13))  # [0, 1, ..., 12]


def verify_digit_segments(
    image_path: str, bbox_coords: list, digit_class: int, tolerance_pct: float = 0.60
) -> tuple:
    """
    Dynamically checks segment brightness.
    A segment must be at least 'tolerance_pct' (e.g., 60%) as bright as the brightest required segment.
    """
    if digit_class not in DIGIT_TRUTH_TABLE:
        return True, "Class ignored by cv2 check"

    img = cv2.imread(image_path)
    if img is None:
        return False, "Failed to load image for cv2"

    x1, y1, x2, y2 = map(int, bbox_coords)

    height_img, width_img = img.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(width_img, x2), min(height_img, y2)

    digit_crop = img[y1:y2, x1:x2]
    if digit_crop.size == 0:
        return False, "Empty bounding box crop"

    height, width = digit_crop.shape[:2]
    gray_crop = cv2.cvtColor(digit_crop, cv2.COLOR_BGR2GRAY)

    required_segments = DIGIT_TRUTH_TABLE[digit_class]
    segment_brightness_scores = {}

    # --- PASS 1: Gather brightness for all required segments ---
    for seg in required_segments:
        y1_pct, y2_pct, x1_pct, x2_pct = SEGMENT_GEOMETRY[seg]

        roi_y1, roi_y2 = int(height * y1_pct), int(height * y2_pct)
        roi_x1, roi_x2 = int(width * x1_pct), int(width * x2_pct)

        segment_slice = gray_crop[roi_y1:roi_y2, roi_x1:roi_x2]
        avg_brightness = np.mean(segment_slice) if segment_slice.size > 0 else 0

        segment_brightness_scores[seg] = avg_brightness

    # --- PASS 2: Calculate Dynamic Threshold ---
    # Use the median to ignore camera glare/hotspots on a single segment
    baseline_brightness = (
        np.median(list(segment_brightness_scores.values()))
        if segment_brightness_scores
        else 0
    )

    # Calculate the dynamic threshold (e.g., 60% of the max brightness)
    dynamic_threshold = baseline_brightness * tolerance_pct

    # Optional Safety Net: If the whole digit is completely off, the max might be like 5.
    # We enforce a hard absolute minimum so we don't accidentally pass a completely dead display.
    absolute_minimum_floor = 15
    if baseline_brightness < absolute_minimum_floor:
        return (
            False,
            f"Display completely dead (Baseline brightness: {baseline_brightness:.1f})",
        )

    # --- PASS 3: Verify ---
    for seg, brightness in segment_brightness_scores.items():
        if brightness < dynamic_threshold:
            return (
                False,
                f"Segment '{seg}' dim/dead. (Score: {brightness:.1f}, Threshold: {dynamic_threshold:.1f})",
            )

    return True, "All required segments present and bright"


# def result(fileName: str, dclass, count: int) -> bool:
#     global _ledModel
#     ledModel = LoadLEDModel()

#     # Initialize the report logger
#     report_logger.initialize_report()

#     results = ledModel(fileName)
#     # results.show()
#     # print(f"Results: {results}")

#     # Capture the human-readable summary
#     with io.StringIO() as buf, contextlib.redirect_stdout(buf):
#         print(results)
#         result_summary = buf.getvalue()
#     result_summary = (
#         result_summary.split(" ")[7].strip()
#         if result_summary
#         else "No summary available"
#     )

#     labels = [int(label) for label in results.xyxyn[0][:, -1].numpy().tolist()]
#     labels.sort()
#     confidences = results.xyxyn[0][:, 4].numpy().flatten().tolist()
#     confidences.sort()
#     # print(f"Labels: {labels}, Confidences: {confidences}")

#     if labels is None or confidences is None:
#         return False

#     if not os.path.exists(saveFolderFail):
#         os.makedirs(saveFolderFail)
#     save_path_fail = os.path.join(f"{saveFolderFail}", os.path.basename(fileName))

#     if not isinstance(dclass, list):
#         dclass = [dclass]

#     # actual_label_names = [int(class_names[lbl]) for lbl in labels]
#     median_confidence = np.median(confidences)
#     mean_confidences = np.average(confidences)

#     # print(f"Mean Confidence: {mean_confidences}")
#     # print(f"Median Confidence: {median_confidence}")

#     # median - max confidence
#     median_max_confidence = max(confidences) - median_confidence
#     # print(f"Median - Max Confidence: {median_max_confidence}")

#     labelClass = all(lbl in dclass for lbl in labels)
#     condition = (
#         (median_confidence - 0.03) <= conf <= (median_confidence + 0.03)
#         for conf in confidences
#     )
#     condition_all_on = (
#         (median_max_confidence - 0.2) <= conf <= (median_max_confidence + 0.2)
#         for conf in confidences
#     )
#     labelCheck = set(labels).issubset(set(passLabelsInt))
#     labelCountMatch = len(labels) == count

#     if count == data["LED_ALL_ON_COUNT"]:
#         if labelCheck and labelCountMatch and condition_all_on:
#             report_logger.append_to_report(
#                 fileName,
#                 "LED",
#                 labels,
#                 confidences,
#                 result_summary,
#                 dclass,
#                 count,
#                 True,
#             )

#             return True
#         else:
#             results.save(save_dir=save_path_fail)
#             report_logger.append_to_report(
#                 fileName,
#                 "LED",
#                 labels,
#                 confidences,
#                 result_summary,
#                 dclass,
#                 count,
#                 False,
#             )
#             # results.show()
#             return False
#     else:
#         if labelCheck and labelCountMatch and condition and labelClass:
#             report_logger.append_to_report(
#                 fileName,
#                 "LED",
#                 labels,
#                 confidences,
#                 result_summary,
#                 dclass,
#                 count,
#                 True,
#             )
#             results.save()
#             return True
#         else:
#             results.save(save_dir=save_path_fail)
#             report_logger.append_to_report(
#                 fileName,
#                 "LED",
#                 labels,
#                 confidences,
#                 result_summary,
#                 dclass,
#                 count,
#                 False,
#             )
#             return False


def result(fileName: str, dclass, count: int) -> bool:
    global _ledModel
    ledModel = LoadLEDModel()

    report_logger.initialize_report()
    results = ledModel(fileName)

    with io.StringIO() as buf, contextlib.redirect_stdout(buf):
        print(results)
        result_summary = buf.getvalue()
    result_summary = (
        result_summary.split(" ")[7].strip()
        if result_summary
        else "No summary available"
    )

    labels = [int(label) for label in results.xyxyn[0][:, -1].numpy().tolist()]
    labels.sort()
    confidences = results.xyxyn[0][:, 4].numpy().flatten().tolist()
    confidences.sort()

    if not labels or not confidences:
        return False

    if not os.path.exists(saveFolderFail):
        os.makedirs(saveFolderFail)
    save_path_fail = os.path.join(f"{saveFolderFail}", os.path.basename(fileName))

    if not isinstance(dclass, list):
        dclass = [dclass]

    # --- 1. OPENCV PIXEL VALIDATION (The heavy lifter) ---
    cv2_passed = True
    xyxy_boxes = results.xyxy[0].numpy()

    for box in xyxy_boxes:
        xmin, ymin, xmax, ymax, conf, cls = box
        lbl = int(cls)

        # Uses your dynamic threshold function!
        is_valid, reason = verify_digit_segments(
            fileName, [xmin, ymin, xmax, ymax], lbl, tolerance_pct=0.60
        )

        if not is_valid:
            cv2_passed = False
            result_summary = f"FAIL: {reason}"
            break
    # -----------------------------------------------------

    # --- 2. BASIC SANITY CHECKS ---
    labelClass = all(lbl in dclass for lbl in labels)
    labelCheck = set(labels).issubset(set(passLabelsInt))
    labelCountMatch = len(labels) == count

    # --- 3. DIAGNOSTIC LOGGER ---
    failure_reasons = []

    if count == data["LED_ALL_ON_COUNT"]:
        if not labelCheck:
            failure_reasons.append("Invalid Labels Detected")
        if not labelCountMatch:
            failure_reasons.append(
                f"Count Mismatch (Expected {count}, Got {len(labels)})"
            )
        if not cv2_passed:
            failure_reasons.append(result_summary)
    else:
        if not labelCheck:
            failure_reasons.append("Invalid Labels Detected")
        if not labelCountMatch:
            failure_reasons.append(
                f"Count Mismatch (Expected {count}, Got {len(labels)})"
            )
        if not labelClass:
            failure_reasons.append(f"Class Mismatch (Expected {dclass}, Got {labels})")
        if not cv2_passed:
            failure_reasons.append(result_summary)

    passed = len(failure_reasons) == 0

    # --- 4. FINAL VERDICT ---
    if passed:
        report_logger.append_to_report(
            fileName, "LED", labels, confidences, "PASS", dclass, count, True
        )
        return True
    else:
        detailed_fail_msg = " | ".join(failure_reasons)
        print(
            f"\n[DEBUG] {os.path.basename(fileName)} failed because: {detailed_fail_msg}\n"
        )

        results.save(save_dir=save_path_fail)
        report_logger.append_to_report(
            fileName,
            "LED",
            labels,
            confidences,
            detailed_fail_msg,
            dclass,
            count,
            False,
        )
        return False


def debug_segment_mapping(
    image_path: str,
    bbox_coords: list,
    digit_class: int,
    tolerance_pct: float = 0.60,
    output_filename: str = "debug_output.jpg",
):
    """
    Creates a visual representation of the segment mapping using dynamic thresholds.
    """
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Could not load {image_path}")
        return

    x1, y1, x2, y2 = map(int, bbox_coords)

    # Safety bounds
    height_img, width_img = img.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(width_img, x2), min(height_img, y2)

    digit_crop = img[y1:y2, x1:x2]
    if digit_crop.size == 0:
        print("Error: Empty crop")
        return

    height, width = digit_crop.shape[:2]
    gray_crop = cv2.cvtColor(digit_crop, cv2.COLOR_BGR2GRAY)

    # Scale up the image by 5x so we can easily read the text and see the boxes
    scale = 5
    debug_img = cv2.resize(
        digit_crop, (width * scale, height * scale), interpolation=cv2.INTER_NEAREST
    )

    required_segments = DIGIT_TRUTH_TABLE.get(digit_class, [])

    # If it's a class we don't check (like 1), skip drawing the cv2 debug boxes
    if not required_segments:
        print(f"Class {digit_class} ignored by cv2 check.")
        return

    # --- PASS 1: Calculate Dynamic Threshold ---
    segment_brightness_scores = {}
    for seg in required_segments:
        y1_pct, y2_pct, x1_pct, x2_pct = SEGMENT_GEOMETRY[seg]
        roi_y1, roi_y2 = int(height * y1_pct), int(height * y2_pct)
        roi_x1, roi_x2 = int(width * x1_pct), int(width * x2_pct)

        segment_slice = gray_crop[roi_y1:roi_y2, roi_x1:roi_x2]
        segment_brightness_scores[seg] = (
            np.mean(segment_slice) if segment_slice.size > 0 else 0
        )

    max_brightness = (
        max(segment_brightness_scores.values()) if segment_brightness_scores else 0
    )
    dynamic_threshold = max_brightness * tolerance_pct
    absolute_minimum_floor = 15

    # --- Print the Math on the Image ---
    # Adds a yellow text overlay so you know exactly what baseline it chose
    info_text = f"Max: {int(max_brightness)} | Thr: {int(dynamic_threshold)}"
    cv2.putText(
        debug_img, info_text, (5, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1
    )

    # --- PASS 2: Draw the Boxes ---
    # Loop through ALL segments in the geometry blueprint
    for seg, (y1_pct, y2_pct, x1_pct, x2_pct) in SEGMENT_GEOMETRY.items():
        roi_y1, roi_y2 = int(height * y1_pct), int(height * y2_pct)
        roi_x1, roi_x2 = int(width * x1_pct), int(width * x2_pct)

        segment_slice = gray_crop[roi_y1:roi_y2, roi_x1:roi_x2]
        avg_brightness = np.mean(segment_slice) if segment_slice.size > 0 else 0

        # Scale coordinates for drawing on our enlarged image
        dx1, dy1 = roi_x1 * scale, roi_y1 * scale
        dx2, dy2 = roi_x2 * scale, roi_y2 * scale

        # Color coding logic
        if seg in required_segments:
            if max_brightness < absolute_minimum_floor:
                color = (0, 0, 255)  # RED: Display completely dead
            elif avg_brightness >= dynamic_threshold:
                color = (0, 255, 0)  # GREEN: Required and ON (Pass)
            else:
                color = (0, 0, 255)  # RED: Required but OFF (Fail)
        else:
            color = (255, 0, 0)  # BLUE: Not required for this digit (Ignore)

        # Draw the rectangle
        cv2.rectangle(debug_img, (dx1, dy1), (dx2, dy2), color, 2)

        # Put the segment letter and its actual brightness score text
        label = f"{seg.upper()}:{int(avg_brightness)}"

        # Add a black background to text for readability
        (text_width, text_height), _ = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1
        )
        cv2.rectangle(
            debug_img,
            (dx1, dy1),
            (dx1 + text_width, dy1 + text_height + 4),
            (0, 0, 0),
            -1,
        )

        # Draw the text
        cv2.putText(
            debug_img,
            label,
            (dx1 + 2, dy1 + text_height + 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (255, 255, 255),
            1,
        )

    cv2.imwrite(output_filename, debug_img)
    print(f"Saved visual X-Ray to {output_filename}")


# -------------------------------------------------------------------------
# Main Execution

if __name__ == "__main__":
    # filename = "Captured_Img_LED\\img1 - Copy.jpg"
    # dclass = 2
    # count = 3
    # print(result(filename, dclass, count))

    # test_image = "Captured_Img_LED\\img11 - Copy.jpg"

    # # The exact output array YOLO gave you
    # yolo_results = [
    #     [493.63, 0, 545.08, 90.135, 0.96965, 5],
    #     [422.1, 0, 470.68, 91.137, 0.96496, 5],
    #     [349.61, 6.4085, 397.67, 92.362, 0.95336, 5],
    #     [278.31, 8.9206, 324.68, 93.617, 0.9528, 5],
    # ]

    # # Loop through every box YOLO found
    # for i, box in enumerate(yolo_results):
    #     # Unpack the 6 values from the row
    #     xmin, ymin, xmax, ymax, conf, cls = box

    #     # Package the coordinates for our function
    #     bbox_coords = [xmin, ymin, xmax, ymax]
    #     digit_class = int(cls)

    #     # Create a unique filename so they don't overwrite each other
    #     output_name = f"debug_digit_{i}.jpg"

    #     print(f"Analyzing Box {i} -> Class: {digit_class}, Confidence: {conf:.2f}")

    #     # Run the visual debugger
    #     debug_segment_mapping(
    #         image_path=test_image,
    #         bbox_coords=bbox_coords,
    #         digit_class=digit_class,
    #         tolerance_pct=0.60,  # Tweak this up or down based on the results!
    #         output_filename=output_name,
    #     )

    # print("Done! Check your project folder for the 3 debug images.")

    dclass = [
        1,
        1,
        2,
        2,
        2,
        5,
        5,
        8,
        10,
        1,
        2,
        5,
        8,
        10,
        0,
        5,
        8,
        10,
        11,
        12,
        11,
        12,
        1,
    ]  # Example class list
    count = [3, 3, 3, 3, 4, 3, 4, 4, 4, 4, 4, 4, 4, 4, 37, 3, 3, 2, 3, 5, 3, 5, 4]
    try:
        directory = GetResourcePath("Captured_Img_LED")
        for filename, d, c in zip(os.listdir(directory), dclass, count):
            if filename.endswith((".jpg", ".png")):
                file_path = os.path.join(directory, filename)
                print(f"Processing {filename} with class={d}, count={c}...")
                result(file_path, d, c)
    except Exception as e:
        print(f"An error occurred: {e}")
