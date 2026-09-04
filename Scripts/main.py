import tkinter as tk
from tkinter import messagebox
import cv2
from PIL import Image, ImageTk
import requests
from requests.auth import HTTPBasicAuth
import threading
import time
import numpy as np
import subprocess


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
        global latest_frame

        WIDTH = 1920
        HEIGHT = 1080
        FRAME_SIZE = WIDTH * HEIGHT * 3

        # Start FFmpeg
        ffmpeg = subprocess.Popen(
            [
                "ffmpeg",
                "-loglevel", "error",
                "-f", "h264",
                "-i", "pipe:0",
                "-f", "rawvideo",
                "-pix_fmt", "bgr24",
                "pipe:1"
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            bufsize=10**8
        )

        print("FFmpeg started.")

        # Connect to ZEISS stream
        response = requests.get(
            STREAM_URL,
            auth=(USERNAME, PASSWORD),
            stream=True
        )

        print("Camera stream connected.")

        buffer = b""
        boundary = b"--boundarydonotcross"

        try:
            for chunk in response.iter_content(chunk_size=8192):
                buffer += chunk

                while boundary in buffer:

                    # Separate one multipart section
                    part, _, buffer = buffer.partition(boundary)

                    # Find the end of the HTTP headers
                    header_end = part.find(b"\r\n\r\n")

                    if header_end == -1:
                        continue

                    # Everything after the headers is H.264
                    h264_data = part[header_end + 4:]

                    if not h264_data:
                        continue

                    # Send H.264 to FFmpeg
                    ffmpeg.stdin.write(h264_data)
                    ffmpeg.stdin.flush()

                    # Read one decoded frame from FFmpeg
                    raw_frame = ffmpeg.stdout.read(FRAME_SIZE)

                    if len(raw_frame) != FRAME_SIZE:
                        continue

                    # Convert raw bytes to OpenCV image
                    frame = np.frombuffer(
                        raw_frame,
                        dtype=np.uint8
                    ).reshape((HEIGHT, WIDTH, 3))

                    # Store only the newest frame
                    with frame_lock:
                        latest_frame = frame

        except Exception as e:
            print("Camera loop error:", e)

        finally:
            response.close()

            ffmpeg.stdin.close()
            ffmpeg.stdout.close()
            ffmpeg.wait()

            print("Camera stream stopped.")


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