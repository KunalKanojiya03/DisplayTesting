# general/report_logger.py
import os
import csv
from datetime import datetime
from general.functions_mod import GetResourcePath

# Define the report file name. This will be created in your project's root directory.
REPORT_FILE = GetResourcePath("inference_report.csv")

def initialize_report():
    """Creates the CSV file and writes the header if it doesn't exist."""
    if not os.path.exists(REPORT_FILE):
        try:
            with open(REPORT_FILE, "w", newline="") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([
                    "timestamp", "image_file", "model_type", "labels_detected",
                    "confidences", "result_summary", "required_class", "required_cnt","result_status"
                ])
        except IOError as e:
            print(f"Error initializing report file: {e}")

def append_to_report(file_name, model_type, labels, confidences, result_summary, required_class, required_cnt, passed):
    """Appends a new row with inference details to the CSV file."""
    try:
        with open(REPORT_FILE, "a", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                os.path.basename(file_name),
                model_type,
                "|".join(map(str, labels)) if isinstance(labels, list) else str(labels),
                "|".join(f"{conf:.2f}" for conf in confidences),
                result_summary.strip().replace("\n", ""),
                "|".join(map(str, required_class)) if isinstance(required_class, list) else str(required_class),
                required_cnt,
                "PASS" if passed else "FAIL"
            ])
    except IOError as e:
        print(f"Error appending to report file: {e}")