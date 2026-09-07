import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import sys
import os
from matplotlib.backends.backend_pdf import PdfPages
from datetime import datetime


def GetResourcePath(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)

    return os.path.join(os.path.dirname(__file__), relative_path)


def create_report(report_date_str=None):
    """
    Generates a PDF report from 'inference_report.csv', with corrected date filtering.
    """
    try:
        # print("\n--- Starting Report Generation ---")  # DEBUG
        csv_path = GetResourcePath("inference_report.csv")
        if not os.path.isfile(csv_path):
            return False, f"Report file not found: '{csv_path}'"

        df = pd.read_csv(csv_path)
        # print(f"Initial data loaded. Shape: {df.shape}")  # DEBUG

        df["timestamp"] = pd.to_datetime(df["timestamp"])

        report_title_date = "All Time"

        # --- CORRECTED Date Filtering Logic ---
        if report_date_str:
            # print(f"Attempting to filter for date: {report_date_str}")  # DEBUG

            # Create a temporary column with the date as a string 'YYYY-MM-DD'
            df["report_day"] = df["timestamp"].dt.strftime("%Y-%m-%d")

            # Filter by comparing the string dates
            df = df[df["report_day"] == report_date_str].drop(columns=["report_day"])

            report_title_date = report_date_str
            # print(f"Filtering complete. New shape: {df.shape}")  # DEBUG
        else:
            print("No date provided. Using all data.")  # DEBUG

        if df.empty:
            # print("DataFrame is empty after filtering. Aborting.")  # DEBUG
            return False, f"No data found for the selected date: {report_title_date}"
        # --- End of Filtering ---

        required_columns = [
            "timestamp",
            "labels_detected",
            "confidences",
            "result_status",
            "model_type",
        ]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return (
                False,
                f"The report file is invalid. Missing columns: {', '.join(missing_columns)}",
            )

        df["num_labels"] = df["labels_detected"].apply(lambda x: len(str(x).split("|")))
        df["avg_conf"] = df["confidences"].apply(
            lambda x: sum(map(float, str(x).split("|"))) / len(str(x).split("|"))
        )
        df["result_status"] = df["result_status"].str.upper()

        date_suffix = report_title_date.replace("-", "")
        now_str = datetime.now().strftime("%H%M%S")
        pdf_filename = f"inference_report_{date_suffix}_{now_str}.pdf"

        # --- PDF Generation (No changes here) ---
        with PdfPages(pdf_filename) as pdf:
            plt.figure(figsize=(8, 8))
            df["result_status"].value_counts().plot.pie(
                autopct="%1.1f%%", startangle=90, legend=True
            )
            plt.title(f"Pass/Fail Distribution ({report_title_date})")
            plt.ylabel("")
            pdf.savefig(bbox_inches="tight")
            plt.close()

            plt.figure(figsize=(10, 6))
            sns.histplot(df["avg_conf"], bins=10, kde=True)
            plt.title(f"Average Confidence Distribution ({report_title_date})")
            plt.xlabel("Average Confidence")
            plt.ylabel("Frequency")
            pdf.savefig(bbox_inches="tight")
            plt.close()

            plt.figure(figsize=(12, 7))
            sns.countplot(data=df, x="model_type", hue="result_status")
            plt.title(f"Model-wise Outcome ({report_title_date})")
            plt.xlabel("Model Type")
            plt.ylabel("Count")
            plt.xticks(rotation=10)
            pdf.savefig(bbox_inches="tight")
            plt.close()

            # Note: This specific chart will only show one bar when filtering by date.
            df["date"] = df["timestamp"].dt.date
            plt.figure(figsize=(12, 7))
            df.groupby("date").size().plot(kind="bar")
            plt.title(f"Images Processed Per Day ({report_title_date})")
            plt.xlabel("Date")
            plt.ylabel("Number of Images")
            plt.xticks(rotation=45, ha="right")
            plt.tight_layout()
            pdf.savefig()
            plt.close()

        print("--- Report Generation Successful ---")  # DEBUG
        return True, f"Report generated successfully: {pdf_filename}"

    except Exception as e:
        print(f"--- AN ERROR OCCURRED: {e} ---")  # DEBUG
        return (
            False,
            f"An unexpected error occurred while processing the report: {str(e)}",
        )


# This allows the script to still be run standalone from the command line
if __name__ == "__main__":
    success, message = create_report()
    print(message)
    if not success:
        sys.exit(1)
