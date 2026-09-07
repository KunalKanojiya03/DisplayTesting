import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QSlider
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap

class ContourDetector(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("7-Segment Contour Detector")

        # Hardcoded camera settings
        camera = {
            "FRAME_WIDTH": 640,
            "FRAME_HEIGHT": 480,
            "SATURATION": 90,
            "BRIGHTNESS": 40,
            "SHARPNESS": 3,   # Note: SHARPNESS may not be supported by all webcams
            "CONTRAST": 198
        }

        # Initialize camera
        self.video = cv2.VideoCapture(0)
        self.video.set(cv2.CAP_PROP_FRAME_WIDTH, camera["FRAME_WIDTH"])
        self.video.set(cv2.CAP_PROP_FRAME_HEIGHT, camera["FRAME_HEIGHT"])
        self.video.set(cv2.CAP_PROP_SATURATION, camera["SATURATION"])
        self.video.set(cv2.CAP_PROP_BRIGHTNESS, camera["BRIGHTNESS"])
        self.video.set(cv2.CAP_PROP_CONTRAST, camera["CONTRAST"])
        self.video.set(cv2.CAP_PROP_SHARPNESS, camera["SHARPNESS"])  # May be ignored on some webcams

        # Store SHARPNESS separately for software sharpening
        self.sharpness_level = camera["SHARPNESS"]

        # UI elements
        self.image_label = QLabel()
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(255)
        self.slider.setValue(100)
        self.slider.setTickInterval(10)
        self.slider.setTickPosition(QSlider.TicksBelow)
        self.threshold_label = QLabel(f"Threshold: {self.slider.value()}")

        layout = QVBoxLayout()
        layout.addWidget(self.image_label)
        layout.addWidget(QLabel("Intensity Threshold"))
        layout.addWidget(self.slider)
        layout.addWidget(self.threshold_label)
        self.slider.valueChanged.connect(self.update_threshold_label)


        self.setLayout(layout)

        # Start timer for video update
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)

    # def apply_software_sharpness(self, frame):
    #     # Apply manual sharpening using convolution
    #     kernel = np.array([[-1, -1, -1],
    #                        [-1, 9 * self.sharpness_level, -1],
    #                        [-1, -1, -1]])
    #     return cv2.filter2D(frame, -1, kernel)

    def update_threshold_label(self):
        self.threshold_label.setText(f"Threshold: {self.slider.value()}")

    def update_frame(self):
        ret, frame = self.video.read()
        if ret:
            # Resize to match expected resolution (optional if camera returns correctly)
            frame = cv2.resize(frame, (640, 480))

            # # Apply software sharpness
            # frame = self.apply_software_sharpness(frame)

            # Detect contours using slider threshold
            threshold = self.slider.value()
            processed = self.detect_contours(frame, threshold)

            # Convert and display
            rgb_image = cv2.cvtColor(processed, cv2.COLOR_BGR2RGB)
            height, width, channel = rgb_image.shape
            bytes_per_line = channel * width
            qt_image = QImage(rgb_image.data, width, height, bytes_per_line, QImage.Format_RGB888)
            self.image_label.setPixmap(QPixmap.fromImage(qt_image))

    def detect_contours(self, frame, threshold):
        # Step 1: Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Step 2: Apply CLAHE to normalize lighting
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)

        # Step 3: Apply Gaussian blur to reduce noise
        gray_blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Step 4: Apply adaptive thresholding
        binary = cv2.adaptiveThreshold(
            gray_blurred, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            11, 2
        )

        # Step 5: Find contours
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for i, contour in enumerate(contours):
            if cv2.contourArea(contour) > 50:
                x, y, w, h = cv2.boundingRect(contour)
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

                # Create mask to calculate mean intensity
                mask = np.zeros(gray.shape, dtype=np.uint8)
                cv2.drawContours(mask, [contour], -1, 255, -1)
                mean_val = cv2.mean(gray, mask=mask)[0]

                # Display contour index and intensity
                cv2.putText(frame, f"{i}", (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
                cv2.putText(frame, f"{mean_val:.1f}", (x, y - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

        return frame


    def closeEvent(self, event):
        self.video.release()
        event.accept()

if __name__ == '__main__':
    import sys
    app = QApplication(sys.argv)
    detector = ContourDetector()
    detector.resize(800, 600)
    detector.show()
    sys.exit(app.exec_())
