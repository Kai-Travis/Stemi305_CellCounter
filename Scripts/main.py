import tkinter as tk
from tkinter import messagebox
import cv2
from PIL import Image, ImageTk
import requests
from requests.auth import HTTPBasicAuth
import threading
import io

CAMERA_IP = "192.168.20.26"
USERNAME = "admin"
PASSWORD = "ZEISS1846"

STREAM_URL = f"http://{CAMERA_IP}:8080/?action=stream"
SNAPSHOT_URL = f"http://{CAMERA_IP}:8080/?action=snapshot"

class StemiApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Stemi Cell Counter")
        self.root.geometry("1100x700")

        self.running = True
        self.current_frame = None

        # -------------------------
        # Layout
        # -------------------------

        self.video_label = tk.Label(root)
        self.video_label.pack(side="left", padx=20, pady=20)

        self.button_frame = tk.Frame(root)
        self.button_frame.pack(side="right", padx=40)

        self.count_button = tk.Button(
            self.button_frame,
            text="COUNT CELLS",
            font=("Arial", 24, "bold"),
            width=12,
            height=3,
            command=self.count_cells
        )

        self.count_button.pack()

        # Start camera thread
        self.camera_thread = threading.Thread(
            target=self.camera_loop,
            daemon=True
        )
        self.camera_thread.start()

        self.root.protocol("WM_DELETE_WINDOW", self.close)

    # -------------------------
    # Live camera
    # -------------------------

    def camera_loop(self):

        cap = cv2.VideoCapture(
            STREAM_URL,
            cv2.CAP_FFMPEG
        )

        if not cap.isOpened():
            print("Could not open camera stream")
            return

        while self.running:

            ret, frame = cap.read()

            if not ret:
                continue

            self.current_frame = frame.copy()

            # Convert OpenCV BGR → RGB
            frame_rgb = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2RGB
            )

            image = Image.fromarray(frame_rgb)

            # Resize for GUI
            image.thumbnail((800, 600))

            photo = ImageTk.PhotoImage(image)

            self.root.after(
                0,
                self.update_video,
                photo
            )

        cap.release()

    def update_video(self, photo):

        self.video_label.configure(image=photo)

        # Keep reference so Tkinter doesn't delete it
        self.video_label.image = photo

    # -------------------------
    # Count cells
    # -------------------------

    def count_cells(self):

        self.count_button.config(
            text="COUNTING...",
            state="disabled"
        )

        thread = threading.Thread(
            target=self.run_counting,
            daemon=True
        )

        thread.start()

    def run_counting(self):

        try:

            # Get high-resolution snapshot
            response = requests.get(
                SNAPSHOT_URL,
                auth=HTTPBasicAuth(
                    USERNAME,
                    PASSWORD
                ),
                timeout=10
            )

            response.raise_for_status()

            image_data = response.content

            image_array = cv2.imdecode(
                __import__("numpy").frombuffer(
                    image_data,
                    dtype="uint8"
                ),
                cv2.IMREAD_COLOR
            )

            if image_array is None:
                raise RuntimeError(
                    "Could not decode camera image"
                )

            # ---------------------------------
            # YOUR CELL COUNTING ALGORITHM HERE
            # ---------------------------------

            # Example:
            #
            # count = count_cells(image_array)

            count = "TEST"

            self.root.after(
                0,
                self.show_result,
                count
            )

        except Exception as e:

            self.root.after(
                0,
                self.show_error,
                str(e)
            )

    def show_result(self, result):

        self.count_button.config(
            text=f"CELLS: {result}",
            state="normal"
        )

    def show_error(self, error):

        messagebox.showerror(
            "Error",
            error
        )

        self.count_button.config(
            text="COUNT CELLS",
            state="normal"
        )

    # -------------------------
    # Close
    # -------------------------

    def close(self):

        self.running = False
        self.root.destroy()


root = tk.Tk()

app = StemiApp(root)

root.mainloop()