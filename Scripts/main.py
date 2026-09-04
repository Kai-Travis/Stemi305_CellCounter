import tkinter as tk
from tkinter import messagebox

import cv2
from PIL import Image, ImageTk

import requests
from requests.auth import HTTPBasicAuth

import threading
import time
import numpy as np


# ============================================================
# Camera settings
# ============================================================

CAMERA_IP = "192.168.20.26"
USERNAME = "admin"
PASSWORD = "ZEISS1846"

STREAM_URL = f"http://{CAMERA_IP}:8080/?action=stream"
SNAPSHOT_URL = f"http://{CAMERA_IP}:8080/?action=snapshot"


# ============================================================
# GUI settings
# ============================================================

PREVIEW_WIDTH = 640
PREVIEW_HEIGHT = 360

# How often the GUI updates the displayed image
# 0.10 seconds = approximately 10 FPS
GUI_UPDATE_INTERVAL = 100


class StemiApp:

    def __init__(self, root):

        self.root = root

        self.root.title("Stemi Cell Counter")
        self.root.geometry("1100x700")

        # ----------------------------------------------------
        # State
        # ----------------------------------------------------

        self.running = True

        # Most recent camera frame
        self.current_frame = None

        # Lock protects current_frame between threads
        self.frame_lock = threading.Lock()

        # ----------------------------------------------------
        # Layout
        # ----------------------------------------------------

        self.video_label = tk.Label(
            root,
            width=PREVIEW_WIDTH,
            height=PREVIEW_HEIGHT,
            bg="black"
        )

        self.video_label.pack(
            side="left",
            padx=20,
            pady=20
        )

        self.button_frame = tk.Frame(root)

        self.button_frame.pack(
            side="right",
            padx=40
        )

        self.count_button = tk.Button(
            self.button_frame,
            text="COUNT CELLS",
            font=("Arial", 24, "bold"),
            width=12,
            height=3,
            command=self.count_cells
        )

        self.count_button.pack()

        # ----------------------------------------------------
        # Start camera thread
        # ----------------------------------------------------

        self.camera_thread = threading.Thread(
            target=self.camera_loop,
            daemon=True
        )

        self.camera_thread.start()

        # ----------------------------------------------------
        # Start GUI update loop
        # ----------------------------------------------------

        self.update_video()

        # ----------------------------------------------------
        # Window close event
        # ----------------------------------------------------

        self.root.protocol(
            "WM_DELETE_WINDOW",
            self.close
        )


    # ========================================================
    # Camera acquisition
    # ========================================================

    def camera_loop(self):

        print("Connecting to Stemi camera...")

        try:

            response = requests.get(
                STREAM_URL,
                auth=HTTPBasicAuth(
                    USERNAME,
                    PASSWORD
                ),
                stream=True,
                timeout=10
            )

            response.raise_for_status()

            print("Camera stream connected.")

            buffer = b""

            for chunk in response.iter_content(
                chunk_size=4096
            ):

                if not self.running:
                    break

                buffer += chunk

                # Find JPEG start
                start = buffer.find(b"\xff\xd8")

                # Find JPEG end
                end = buffer.find(
                    b"\xff\xd9",
                    start + 2
                )

                if start != -1 and end != -1:

                    jpeg = buffer[
                        start:end + 2
                    ]

                    buffer = buffer[
                        end + 2:
                    ]

                    # Decode JPEG
                    frame = cv2.imdecode(
                        np.frombuffer(
                            jpeg,
                            dtype=np.uint8
                        ),
                        cv2.IMREAD_COLOR
                    )

                    if frame is not None:

                        # Only keep newest frame
                        with self.frame_lock:

                            self.current_frame = frame

        except Exception as e:

            print(
                f"Camera stream error: {e}"
            )

        finally:

            try:
                response.close()
            except:
                pass

            print("Camera stream closed.")


    # ========================================================
    # GUI video update
    # ========================================================

    def update_video(self):

        if not self.running:
            return

        frame = None

        # Get the newest frame
        with self.frame_lock:

            if self.current_frame is not None:

                frame = self.current_frame.copy()

        if frame is not None:

            # ------------------------------------------------
            # Resize BEFORE converting to PIL
            # ------------------------------------------------

            frame = cv2.resize(
                frame,
                (PREVIEW_WIDTH, PREVIEW_HEIGHT),
                interpolation=cv2.INTER_AREA
            )

            # OpenCV BGR -> RGB
            frame_rgb = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2RGB
            )

            # Convert to PIL
            image = Image.fromarray(frame_rgb)

            # Convert to Tkinter image
            photo = ImageTk.PhotoImage(image)

            # Display
            self.video_label.configure(
                image=photo
            )

            # Keep reference
            self.video_label.image = photo

        # Schedule next GUI update
        self.root.after(
            GUI_UPDATE_INTERVAL,
            self.update_video
        )


    # ========================================================
    # Count cells
    # ========================================================

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


    # ========================================================
    # Cell counting
    # ========================================================

    def run_counting(self):

        try:

            print("Taking high-resolution snapshot...")

            # ------------------------------------------------
            # Get high-resolution snapshot
            # ------------------------------------------------

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

            # ------------------------------------------------
            # Decode JPEG
            # ------------------------------------------------

            image_array = cv2.imdecode(
                np.frombuffer(
                    image_data,
                    dtype=np.uint8
                ),
                cv2.IMREAD_COLOR
            )

            if image_array is None:

                raise RuntimeError(
                    "Could not decode camera image."
                )

            print(
                f"Snapshot received: "
                f"{image_array.shape[1]} x "
                f"{image_array.shape[0]}"
            )

            # ------------------------------------------------
            # YOUR CELL COUNTING ALGORITHM
            # ------------------------------------------------

            # Replace this with your actual algorithm.
            #
            # Example:
            #
            # count = count_cells(image_array)

            count = "TEST"

            # ------------------------------------------------
            # Show result
            # ------------------------------------------------

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


    # ========================================================
    # Display result
    # ========================================================

    def show_result(self, result):

        self.count_button.config(
            text=f"CELLS: {result}",
            state="normal"
        )


    # ========================================================
    # Display error
    # ========================================================

    def show_error(self, error):

        messagebox.showerror(
            "Error",
            error
        )

        self.count_button.config(
            text="COUNT CELLS",
            state="normal"
        )


    # ========================================================
    # Close application
    # ========================================================

    def close(self):

        print("Closing application...")

        self.running = False

        self.root.destroy()


# ============================================================
# Start application
# ============================================================

root = tk.Tk()

app = StemiApp(root)

root.mainloop()