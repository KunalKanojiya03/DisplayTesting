# Webcam Image Capture
#
# This script captures images from your webcam when you press the 'Enter' key
# and saves them into a directory named 'CapturedImages'.

# Import the necessary libraries
import cv2
import os

# --- Configuration ---
# Directory to save the captured images
SAVE_DIR = "CapturedImages"
# Key to press to capture an image (13 is the ASCII code for 'Enter')
CAPTURE_KEY = 13
# Key to press to exit the program (27 is the ASCII code for 'Esc')
EXIT_KEY = 27

# Camera properties
CAMERA = {
    "CAMERA_INDEX": 0,
    "FRAME_WIDTH": 640,
    "FRAME_HEIGHT": 480,
    "SATURATION": 90,
    "BRIGHTNESS": 40,
    "SHARPNESS": 5,
    "CONTRAST": 198,
}


def main():
    """
    Main function to run the webcam capture application.
    """
    # --- 1. Create the directory to save images ---
    # Check if the directory already exists
    if not os.path.exists(SAVE_DIR):
        # If it doesn't exist, create it
        os.makedirs(SAVE_DIR)
        print(f"Directory '{SAVE_DIR}' created.")

    # --- 2. Initialize the webcam ---
    # cv2.VideoCapture() accesses the webcam using the specified index.
    cap = cv2.VideoCapture(CAMERA["CAMERA_INDEX"])

    # Set camera properties
    # Note: Not all webcams support all properties.
    # The values are set, but the camera may not apply them if not supported.
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA["FRAME_WIDTH"])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA["FRAME_HEIGHT"])
    cap.set(cv2.CAP_PROP_SATURATION, CAMERA["SATURATION"])
    cap.set(cv2.CAP_PROP_BRIGHTNESS, CAMERA["BRIGHTNESS"])
    cap.set(cv2.CAP_PROP_SHARPNESS, CAMERA["SHARPNESS"])
    cap.set(cv2.CAP_PROP_CONTRAST, CAMERA["CONTRAST"])


    # Check if the webcam was opened successfully
    if not cap.isOpened():
        print("Error: Could not open webcam.")
        return

    # --- 3. Main application loop ---
    print("\nWebcam feed started.")
    print(f"Press 'Enter' to capture an image.")
    print(f"Press 'Esc' to exit.")

    img_counter = 0
    while True:
        # Read a frame from the webcam
        # 'ret' is a boolean that is True if the frame was read successfully
        # 'frame' is the captured image frame
        ret, frame = cap.read()

        # If the frame was not captured correctly, break the loop
        if not ret:
            print("Failed to grab frame.")
            break

        # Display the resulting frame in a window named 'Webcam'
        cv2.imshow("Webcam - Press 'Enter' to Capture, 'Esc' to Exit", frame)

        # Wait for a key press for 1 millisecond
        # This is crucial for displaying the video feed
        key_pressed = cv2.waitKey(1) & 0xFF

        # --- 4. Handle key presses ---
        # Check if the pressed key is the EXIT_KEY ('Esc')
        if key_pressed == EXIT_KEY:
            print("Exit key pressed. Closing application.")
            break
        # Check if the pressed key is the CAPTURE_KEY ('Enter')
        elif key_pressed == CAPTURE_KEY:
            # Construct the filename for the new image
            img_name = os.path.join(SAVE_DIR, f"image_{img_counter}.png")
            # Save the current frame to the specified file
            cv2.imwrite(img_name, frame)
            print(f"Image captured and saved as {img_name}")
            # Increment the image counter for the next capture
            img_counter += 1

    # --- 5. Release resources ---
    # When everything is done, release the webcam capture object
    cap.release()
    # Close all the OpenCV windows
    cv2.destroyAllWindows()
    print("Webcam released and windows closed.")


if __name__ == "__main__":
    # Before running, make sure you have the required library installed:
    # pip install opencv-python
    main()
